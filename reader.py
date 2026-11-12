"""Read the game state from a capture of the Batomon Showdown window.

    state = read_state(image)      # image: PIL image of the client area

Read-only: nothing here sends input to the game.

Everything is measured in canonical picture pixels: the 16:9 game picture
(black bars removed) scaled to 2560 x 1440. box_to_frac() converts a box to the
picture fractions that window.frac_to_screen() expects.

A value the reader is not sure about is returned as None (never a guess), and
the reason is added to state["problems"]. The hands must stop when that list
is not empty.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

import glyphs
import window

ROOT = Path(__file__).resolve().parent
SPRITE_DIR = ROOT / "templates" / "sprites"

Box = tuple[int, int, int, int]          # x0, y0, x1, y1 in canonical pixels

# ---------------------------------------------------------------- layout ----

LIVES: Box = (925, 30, 1040, 110)
DAY: Box = (1060, 20, 1500, 120)
BADGES: Box = (1620, 30, 1800, 110)
TRAINER: Box = (30, 180, 530, 235)
HP: Box = (120, 985, 530, 1035)
RANK_BAR: Box = (510, 1075, 1100, 1140)
MONEY: Box = (1185, 1085, 1370, 1155)
REROLL_PRICE: Box = (60, 1320, 360, 1410)

# Buttons (for the hands)
REROLL_BUTTON: Box = (24, 1200, 392, 1416)
LOCK_BUTTON: Box = (1840, 1076, 2050, 1142)
BATTLE_BUTTON: Box = (2168, 1200, 2536, 1416)
SELL_BAR: Box = (496, 1256, 2064, 1416)   # drag a monster here to sell it

SHOP_SLOTS = 5
TEAM_COLS, TEAM_ROWS = 3, 2
BENCH_SLOTS = 4


def shop_card(i: int) -> Box:
    """Whole shop card i (0 = leftmost)."""
    return (504 + 312 * i, 1264, 804 + 312 * i, 1408)


def _card_text(i: int) -> Box:
    return (512 + 312 * i, 1350, 796 + 312 * i, 1402)


def _card_badges(i: int) -> Box:
    return (512 + 312 * i, 1290, 796 + 312 * i, 1364)


def team_slot(i: int) -> Box:
    """Inside of team slot i. 0-2 = top row left to right, 3-5 = bottom row."""
    col, row = i % TEAM_COLS, i // TEAM_COLS
    return (815 + 288 * col, 599 + 232 * row, 1055 + 288 * col, 783 + 232 * row)


def bench_slot(i: int) -> Box:
    return (659 + 288 * i, 267, 899 + 288 * i, 451)


def box_to_frac(box: Box) -> tuple[float, float]:
    """Centre of a box as fractions of the game picture (for clicking)."""
    x0, y0, x1, y1 = box
    return ((x0 + x1) / 2 / (window.CANON_W - 1), (y0 + y1) / 2 / (window.CANON_H - 1))


# Screen signatures: every listed pixel must have its colour (within TOL).
# Add a signature for each new screen as it is captured.
SCREEN_TOL = 28
YELLOW, PINK, RED, BLUE = (255, 200, 4), (255, 74, 107), (239, 66, 107), (49, 198, 247)
SCREENS: dict[str, list[tuple[int, int, tuple[int, int, int]]]] = {
    # Stats window (opened from the result screen); it covers everything else
    "stats": [(1200, 140, PINK), (1200, 270, YELLOW), (2300, 1215, (89, 89, 89))],
    # "Searching for opponent.." / "Opponent Found!": the shop with a dialog over the shop bar
    "matchmaking": [(1300, 215, YELLOW), (1500, 545, PINK), (460, 1300, PINK)],
    "shop": [
        (1300, 215, YELLOW),            # BENCH header
        (1500, 545, PINK),              # MY TEAM header
        (60, 1000, (248, 176, 0)),      # "HP" label
        # (the REROLL button is not used: it turns grey when you cannot afford a reroll.
        #  Matchmaking is told apart by its dialog and is checked first.)
        (2300, 1215, RED),              # BATTLE! button
    ],
    # "You won!" box with HIDE (left) and CONFIRM (right)
    "result": [(100, 1215, BLUE), (460, 1300, PINK), (2300, 1215, RED)],
    # Event with up to three choices: SHOW TEAM (left), nothing on the right
    "event": [(100, 1215, BLUE), (460, 1300, PINK), (2300, 1215, (14, 14, 14)), (300, 600, (14, 14, 14))],
    # "<monster> leveled up! ... gives you a gift.": a gift box over the dimmed shop
    "gift_box": [(100, 1215, (19, 19, 21)), (2300, 1215, (19, 19, 21)), (460, 1300, PINK), (1300, 215, (55, 41, 2))],
    # "Select a trinket.": trinket cards over the dimmed shop, HIDE on the left
    "trinket_pick": [(100, 1215, BLUE), (2300, 1215, (19, 19, 21)), (460, 1300, PINK), (1300, 215, (55, 41, 2))],
    # Trainer pick: three yellow card headers over the "Select a trainer" box
    "trainer_pick": [(820, 222, YELLOW), (1483, 222, YELLOW), (2146, 222, YELLOW), (460, 1300, PINK),
                     (100, 1215, (14, 14, 14))],
    # "This journey ends here.": camera (left), New Run and Main Menu (right)
    "run_over": [(60, 1310, (255, 206, 0)), (1300, 1300, RED), (1900, 1300, RED), (1280, 60, (14, 14, 14))],
    # Battle: the two trainer portraits in the bottom corners (their frames do not move)
    "battle": [(30, 1160, (156, 156, 173)), (2530, 1160, (156, 156, 173)), (30, 1420, (255, 255, 255)),
               (2530, 1420, (255, 255, 255))],
}

FAST_FORWARD: Box = (1300, 15, 1420, 125)   # top centre of the battle screen; red when on


def fast_forward_on(pic: np.ndarray) -> bool:
    return bool(_near(pic[65, 1325], RED, 45))

# Buttons on the other screens
RESULT_CONFIRM: Box = BATTLE_BUTTON
RESULT_STATS: Box = (19, 330, 448, 451)
STATS_CLOSE: Box = (2240, 125, 2310, 200)
EVENT_CHOICE_COLUMN = 1500              # x that crosses every choice box
EVENT_CHOICE_ROWS = (630, 1075)         # y range the choice boxes can be in


def event_choices(pic: np.ndarray) -> list[Box]:
    """The white choice boxes of an event screen, top to bottom."""
    y0, y1 = EVENT_CHOICE_ROWS
    col = pic[y0:y1, EVENT_CHOICE_COLUMN].min(axis=1) >= 240
    boxes, y = [], 0
    while y < len(col):
        if col[y]:
            start = y
            while y < len(col) and col[y]:
                y += 1
            if y - start >= 70:
                boxes.append((800, y0 + start + 8, 1760, y0 + y - 8))
        else:
            y += 1
    return boxes


# Stat badge colours seen so far -> what the number means.
STAT_COLORS: dict[str, tuple[int, int, int]] = {
    "damage": (239, 66, 107),
    "heal": (24, 165, 222),
    "shield": (184, 208, 232),
    "poison": (132, 90, 189),
    "burn": (255, 156, 49),
    "shock": (255, 206, 0),
}
# Card frame colour -> rarity (same colours as the gems in the rank bar).
FRAME_RARITY: dict[str, tuple[int, int, int]] = {
    "Common": (90, 90, 99),
    "Uncommon": (74, 181, 0),
    "Rare": (0, 132, 189),
    "Super Rare": (160, 64, 160),
    "Legendary": (212, 124, 0),
}
STAT_HUE_TOL = 22           # degrees of hue (+ saturation penalty)

RARITIES = ["Common", "Uncommon", "Rare", "Super Rare", "Legendary"]

BADGE_OUTLINE = (74, 66, 66)
# letters of the "LV. n" label: bronze at level 1, silver at 2, gold at 3 (4 not seen yet)
LEVEL_FILLS = [(165, 112, 51), (173, 189, 222), (255, 239, 99)]
SPRITE_MATCH_MAX = 45.0     # mean colour difference allowed for a sprite match

# ----------------------------------------------------------------- names ----

_names = json.loads((ROOT / "data" / "names.json").read_text(encoding="utf-8"))
MONSTER_NAMES: list[str] = list(_names["pantra_batomon_base_price"]) + list(_names["evolved_forms_seen"])
ITEM_NAMES: list[str] = list(_names["items"])
with open(ROOT / "data" / "trainers.csv", newline="", encoding="utf-8") as _f:
    TRAINER_NAMES: list[str] = [row["name"] for row in csv.DictReader(_f)]


def resolve(text: str, candidates: list[str], ignore_case: bool = False) -> str | None:
    """Match text that may contain unknown glyphs ("?") to one known name.

    Returns the name only if exactly one candidate fits; otherwise None.
    """
    if not text:
        return None
    # capital I and lowercase l are the same glyph in the card font
    key = (lambda s: s.upper()) if ignore_case else (lambda s: s.replace("I", "l"))
    t = key(text)
    hits = []
    for cand in candidates:
        c = key(cand)
        if len(c) == len(t) and all(a == b or a == glyphs.UNKNOWN for a, b in zip(t, c)):
            hits.append(cand)
    known = sum(ch != glyphs.UNKNOWN and ch != " " for ch in t)
    if len(hits) == 1 and known * 2 >= len(t.replace(" ", "")):
        return hits[0]
    return None


# --------------------------------------------------------------- helpers ----

_store: glyphs.GlyphStore | None = None


def store() -> glyphs.GlyphStore:
    global _store
    if _store is None:
        _store = glyphs.GlyphStore()
    return _store


def reload_templates() -> None:
    global _store, _sprites
    _store = None
    _sprites = None


def crop(pic: np.ndarray, box: Box) -> np.ndarray:
    x0, y0, x1, y1 = box
    return pic[y0:y1, x0:x1]


def _near(rgb: np.ndarray, colour: tuple[int, int, int], tol: int) -> np.ndarray:
    return np.abs(rgb.astype(int) - np.array(colour)).max(axis=-1) <= tol


def _to_int(text: str) -> int | None:
    return int(text) if text.isdigit() else None


# ---- New Run dialog: region cards, Ranked Mode / Casual Mode, CANCEL, CONFIRM ----
# The selected mode button is blue and the other grey; the selected region card
# has a pink header and the other a grey one. (Checked by clicking both modes.)
NEW_RUN_RANKED: Box = (672, 1194, 1254, 1302)
NEW_RUN_CASUAL: Box = (1303, 1194, 1888, 1302)
NEW_RUN_PANTRA: Box = (829, 662, 1210, 1123)
NEW_RUN_JINTO: Box = (1345, 662, 1730, 1123)
NEW_RUN_CONFIRM: Box = BATTLE_BUTTON
NEW_RUN_CANCEL: Box = REROLL_BUTTON
RUN_OVER_NEW_RUN: Box = (1250, 1290, 1850, 1400)
MODE_GREY, REGION_GREY = (123, 123, 123), (132, 132, 132)


def _button_colour(pic: np.ndarray, points: list[tuple[int, int]], colour: tuple[int, int, int]) -> bool:
    return all(_near(pic[y, x], colour, 20) for x, y in points)


def read_new_run(pic: np.ndarray) -> dict:
    """Which mode and region are selected. None = not exactly one clear selection."""
    ranked_pts, casual_pts = [(700, 1215), (1230, 1215)], [(1330, 1215), (1860, 1215)]
    ranked_on = _button_colour(pic, ranked_pts, BLUE)
    ranked_off = _button_colour(pic, ranked_pts, MODE_GREY)
    casual_on = _button_colour(pic, casual_pts, BLUE)
    casual_off = _button_colour(pic, casual_pts, MODE_GREY)
    mode = "casual" if casual_on and ranked_off else "ranked" if ranked_on and casual_off else None
    pantra_pts, jinto_pts = [(860, 700), (1180, 700)], [(1380, 700), (1700, 700)]
    pantra_on = _button_colour(pic, pantra_pts, PINK)
    jinto_on = _button_colour(pic, jinto_pts, PINK)
    pantra_off = _button_colour(pic, pantra_pts, REGION_GREY)
    jinto_off = _button_colour(pic, jinto_pts, REGION_GREY)
    region = "Pantra" if pantra_on and jinto_off else "Jinto" if jinto_on and pantra_off else None
    problems = []
    if mode is None:
        problems.append("new run: cannot tell which mode is selected")
    if region is None:
        problems.append("new run: cannot tell which region is selected")
    return {"mode": mode, "region": region, "problems": problems}


def _is_new_run(pic: np.ndarray) -> bool:
    if not (_near(pic[1215, 100], RED, SCREEN_TOL) and _near(pic[1215, 2300], RED, SCREEN_TOL)):
        return False
    # both mode buttons must be there, each either blue or grey
    return all(_near(pic[1215, x], BLUE, 20) or _near(pic[1215, x], MODE_GREY, 20) for x in (700, 1230, 1330, 1860))


# ---- Gift box and trinket choice ----
GIFT_BOX: Box = (1100, 600, 1460, 950)
with open(ROOT / "data" / "trinkets.csv", newline="", encoding="utf-8") as _f:
    TRINKET_NAMES: list[str] = [row["name"] for row in csv.DictReader(_f)]


def trinket_card(i: int) -> Box:
    return (250 + 720 * i, 330, 870 + 720 * i, 990)


def read_trinket_pick(pic: np.ndarray) -> dict:
    """How many trinket cards are offered, and their names where readable."""
    names = []
    for i in range(3):
        x0 = 250 + 720 * i
        if not _near(pic[345, x0 + 350], (255, 255, 255), 10):
            continue                       # no card here
        mask = glyphs.white(crop(pic, (x0 + 14, 266, x0 + 610, 320)))
        gl = glyphs.segment(mask)
        # header is "<NAME>      <RARITY>": keep what is left of the widest gap
        cut = mask.shape[1]
        if len(gl) > 1:
            gap, k = max((gl[k + 1].x0 - gl[k].x1, k) for k in range(len(gl) - 1))
            if gap >= 40:
                cut = gl[k].x1 + 1
        text = store().read("caps", mask[:, :cut], space_gap=6)
        names.append(resolve(text, TRINKET_NAMES, ignore_case=True))
    return {"trinkets": names, "problems": [] if names else ["trinket pick: no cards found"]}


# ---- Trainer pick: three trainer cards, click one ----
TRAINER_CARDS = 3


def trainer_card(i: int) -> Box:
    return (350 + 663 * i, 190, 880 + 663 * i, 1050)


def _trainer_card_name(i: int) -> Box:
    return (366 + 663 * i, 208, 862 + 663 * i, 256)


def read_trainer_pick(pic: np.ndarray) -> dict:
    """Names of the offered trainers (None where the name cannot be resolved yet)."""
    names = []
    for i in range(TRAINER_CARDS):
        text = store().read("caps", glyphs.white(crop(pic, _trainer_card_name(i))), space_gap=6)
        names.append(resolve(text, TRAINER_NAMES, ignore_case=True))
    return {"trainers": names, "problems": []}


def detect_screen(pic: np.ndarray) -> str:
    if pic.max() < 40:
        return "blank"                    # fade between screens
    if _is_new_run(pic):
        return "new_run"
    for name, points in SCREENS.items():
        if all(_near(pic[y, x], colour, SCREEN_TOL) for x, y, colour in points):
            return name
    return "unknown"


# ---------------------------------------------------------- text regions ----

def text_masks(pic: np.ndarray) -> dict[str, tuple[str, np.ndarray, dict]]:
    """Every fixed text region of the shop screen: name -> (font, mask, read options).

    Shared by the reader and by teach.py so both cut the text the same way.
    """
    out = {
        "lives": ("chunky", glyphs.white(crop(pic, LIVES)), {}),
        "day": ("title", glyphs.white(crop(pic, DAY)), {}),
        "badges": ("chunky", glyphs.white(crop(pic, BADGES)), {}),
        "trainer": ("caps", glyphs.white(crop(pic, TRAINER)), {"space_gap": 6}),
        "hp": ("hp", glyphs.white(crop(pic, HP)), {}),
        "rank_bar": ("rankbar", glyphs.inked(crop(pic, RANK_BAR)), {}),
        "money": ("chunky", glyphs.white(crop(pic, MONEY)), {}),
        "reroll": ("chunky", glyphs.white(crop(pic, REROLL_PRICE)), {}),
    }
    for i in range(SHOP_SLOTS):
        out[f"shop{i}"] = ("card", card_text_mask(crop(pic, _card_text(i))), {"space_gap": 7})
    return out


CARD_GREY = (182, 182, 182)     # name on a card you cannot afford
CARD_RED = (255, 74, 107)       # price on a card you cannot afford
SOLD_GREY = (231, 231, 231)     # a shop slot whose card was bought


def card_text_mask(rgb: np.ndarray) -> np.ndarray:
    """Text on a shop card: white, or grey name + red price when it costs too much."""
    grey = _near(rgb, CARD_GREY, 4)
    if grey.sum() < 300:
        return glyphs.white(rgb)
    # same share of the anti-aliased edge as the white rule keeps (215/255)
    v = rgb.astype(int)
    soft_grey = (v.min(axis=2) >= 153) & (v.max(axis=2) - v.min(axis=2) <= 12)
    soft_red = (v[..., 0] >= 215) & (v[..., 1] <= 120) & (v[..., 2] <= 150)
    soft_red[:6] = False              # lower edge of a red or orange stat badge
    mask = soft_grey | soft_red
    return mask


def _split_name_price(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """A card's text line is "<name>   <price>": cut it before the last "$".

    (A long name such as "Recruiting Flyer" leaves almost no gap before the price.)
    If no "$" is recognised, cut at the widest gap.
    """
    gl = glyphs.segment(mask)
    if len(gl) < 2:
        return None
    dollars = [k for k, g in enumerate(gl) if k > 0 and store().classify("card", g.bitmap)[0] == "$"]
    if dollars:
        k = dollars[-1] - 1
    else:
        gap, k = max((gl[k + 1].x0 - gl[k].x1, k) for k in range(len(gl) - 1))
        if gap < 24:
            return None
    cut = (gl[k].x1 + gl[k + 1].x0) // 2
    return mask[:, :cut], mask[:, cut:]


# ---------------------------------------------------------------- badges ----

def _hue(colour: tuple[int, int, int]) -> float:
    """Hue in degrees. Shading changes a tile's brightness but not its hue."""
    px = np.uint8([[colour]])
    return float(cv2.cvtColor(px, cv2.COLOR_RGB2HSV_FULL)[0, 0, 0]) * 360 / 256


def _hue_gap(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def _saturation(colour: tuple[int, int, int]) -> float:
    return (max(colour) - min(colour)) / max(max(colour), 1)


def stat_name(colour: tuple[int, int, int]) -> str | None:
    """Which stat a badge tile colour stands for (hue and saturation both count)."""
    best, best_d = None, STAT_HUE_TOL
    for name, ref in STAT_COLORS.items():
        d = _hue_gap(_hue(colour), _hue(ref)) + 60 * abs(_saturation(colour) - _saturation(ref))
        if d < best_d:
            best, best_d = name, d
    return best


def read_stat_badges(pic: np.ndarray, band: Box) -> list[dict]:
    """Find the small coloured number badges inside a band, left to right.

    A badge is a coloured tile with a dark outline and white digits. Badges that
    touch share one outline, so digits are grouped by the tile colour around them.
    """
    region = crop(pic, band)
    outline = _near(region, BADGE_OUTLINE, 10)
    # inside of a badge = pixels the outline fences off from the band's edge
    n, labels, stats, _ = cv2.connectedComponentsWithStats((~outline).astype(np.uint8), connectivity=4)
    edge = set(labels[0]) | set(labels[-1]) | set(labels[:, 0]) | set(labels[:, -1])
    inside = np.isin(labels, [k for k in range(1, n) if k not in edge])
    # close the gaps left by the digits' own dark outlines so a tile is one piece
    tiles = cv2.morphologyEx(inside.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(tiles, connectivity=8)
    found = []
    for k in range(1, n):
        x, y, w, h, _area = stats[k]
        if not (24 <= w <= 260 and 20 <= h <= 60):
            continue
        tile = labels[y:y + h, x:x + w] == k
        inner = region[y:y + h, x:x + w]
        digits = glyphs.white(inner, 235) & tile
        coloured = tile & ~digits & ~outline[y:y + h, x:x + w] & (inner.max(axis=2) > 90)
        current = None
        for g in glyphs.segment_blobs(digits):
            # tile colour beside the digit (its rows only: the tile's lower edge is shaded)
            near = coloured[g.y0:g.y1, max(g.x0 - 6, 0):g.x1 + 6]
            px = inner[g.y0:g.y1, max(g.x0 - 6, 0):g.x1 + 6][near]
            ch = store().classify("badge", g.bitmap)[0]
            # digits of one badge sit close together; the tile colour is taken from
            # the first digit (a tile is lighter on its left side)
            if current and g.x0 - current["_x1"] <= 10:
                current["raw"] += ch
                current["_x1"] = g.x1
            elif len(px):
                colour = tuple(int(v) for v in np.median(px.reshape(-1, 3), axis=0))
                current = {"raw": ch, "_colour": colour, "_x1": g.x1, "_x": int(band[0] + x + g.x0)}
                found.append(current)
    found.sort(key=lambda b: b["_x"])
    out = []
    for b in found:
        raw = b["raw"]
        if raw.startswith("x"):           # "x2": the ability is cast that many times
            out.append({"value": _to_int(raw[1:]), "raw": raw, "stat": "multicast"})
        else:
            out.append({"value": _to_int(raw), "raw": raw, "stat": stat_name(b["_colour"])})
        out[-1]["color"] = "#%02x%02x%02x" % b["_colour"]
    return out


def badge_digit_glyphs(pic: np.ndarray, band: Box) -> list[np.ndarray]:
    """The digit bitmaps of all badges in a band, left to right (for teach.py)."""
    region = crop(pic, band)
    outline = _near(region, BADGE_OUTLINE, 10)
    n, labels, _, _ = cv2.connectedComponentsWithStats((~outline).astype(np.uint8), connectivity=4)
    edge = set(labels[0]) | set(labels[-1]) | set(labels[:, 0]) | set(labels[:, -1])
    inside = np.isin(labels, [k for k in range(1, n) if k not in edge])
    return [g.bitmap for g in glyphs.segment_blobs(glyphs.white(region, 235) & inside)]


# --------------------------------------------------------------- sprites ----

_sprites: list[tuple[str, np.ndarray]] | None = None


def _sprite_templates() -> list[tuple[str, np.ndarray]]:
    global _sprites
    if _sprites is None:
        _sprites = []
        if SPRITE_DIR.exists():
            for p in sorted(SPRITE_DIR.glob("*.png")):
                name = p.stem.split("__")[0]
                _sprites.append((name, np.asarray(Image.open(p).convert("RGB"))))
    return _sprites


def sprite_patch(slot_rgb: np.ndarray) -> np.ndarray:
    """The part of a team/bench slot that shows only the monster (no label, no badges)."""
    return slot_rgb[36:140, 40:200]


def match_sprite(slot_rgb: np.ndarray) -> tuple[str | None, float]:
    """Name the monster in a team/bench slot from the saved sprites.

    Sprites move a little (idle animation), so the same monster scores about
    5-15 and a different one 75 or more. The best match must also be clearly
    better than the best match under any other name.
    """
    patch = sprite_patch(slot_rgb).astype(int)
    by_name: dict[str, float] = {}
    for name, tpl in _sprite_templates():
        if tpl.shape != patch.shape:
            continue
        d = float(np.abs(patch - tpl).mean())
        by_name[name] = min(d, by_name.get(name, 1e9))
    if not by_name:
        return None, 1e9
    ranked = sorted(by_name.items(), key=lambda kv: kv[1])
    best, best_d = ranked[0]
    if best_d > SPRITE_MATCH_MAX or (len(ranked) > 1 and best_d * 2 > ranked[1][1]):
        return None, best_d
    return best, best_d


def learn_sprite(name: str, slot_rgb: np.ndarray) -> Path:
    """Save the sprite in a team/bench slot under a monster name."""
    SPRITE_DIR.mkdir(parents=True, exist_ok=True)
    known, dist = match_sprite(slot_rgb)
    if known == name and dist < 3:
        return SPRITE_DIR / f"{name}.png"      # this exact frame is already saved
    k = 0
    while True:
        path = SPRITE_DIR / (f"{name}.png" if k == 0 else f"{name}__{k}.png")
        if not path.exists():
            break
        k += 1
    Image.fromarray(sprite_patch(slot_rgb)).save(path)
    global _sprites
    _sprites = None                   # reread the sprite folder next time
    return path


# ------------------------------------------------------------ slot reads ----

def owned_badge_band(box: Box) -> Box:
    """Where the stat badges of a team/bench slot sit (they straddle its lower edge)."""
    x0, _, x1, y1 = box
    return (x0 - 8, y1 - 44, x1 + 8, y1 + 28)


def level_mask(slot_rgb: np.ndarray) -> np.ndarray:
    # exact letter colour, so a big sprite reaching into the corner is ignored
    label = slot_rgb[0:40, 0:110]
    mask = np.zeros(label.shape[:2], dtype=bool)
    for fill in LEVEL_FILLS:
        mask |= _near(label, fill, 14)
    return mask


def _read_owned_slot(pic: np.ndarray, box: Box, where: str, problems: list[str]) -> dict | None:
    """A team or bench slot. None = empty."""
    rgb = crop(pic, box)
    if (rgb.min(axis=2) < 200).mean() < 0.01:
        return None
    x0, y0, x1, y1 = box
    # "LV. n" label, top left: coloured letters with a black outline
    fill = level_mask(rgb)
    parts = glyphs.segment(fill)          # "LV", ".", digit
    level_text = store().classify("level", parts[-1].bitmap)[0] if len(parts) >= 3 else ""
    level = _to_int(level_text)
    if level is None:
        problems.append(f"{where}: cannot read level ('{level_text}')")
    badges = read_stat_badges(pic, owned_badge_band(box))
    if any(b["value"] is None for b in badges):
        problems.append(f"{where}: cannot read a stat badge")
    name, dist = match_sprite(rgb)
    return {"name": name, "level": level, "stats": badges, "sprite_distance": round(dist, 1) if dist < 1e8 else None}


def _read_shop_slot(pic: np.ndarray, i: int, masks: dict, problems: list[str]) -> dict | None:
    font, mask, _ = masks[f"shop{i}"]
    text_rgb = crop(pic, _card_text(i))
    if _near(text_rgb, SOLD_GREY, 6).mean() > 0.8:
        return None                       # bought: the slot is an empty grey box
    if mask.sum() < 20:
        problems.append(f"shop {i}: no text found")
        return {"name": None, "price": None, "kind": None, "raw": ""}
    parts = _split_name_price(mask)
    if parts is None:
        problems.append(f"shop {i}: cannot split name and price")
        return {"name": None, "price": None, "kind": None, "raw": store().read(font, mask, space_gap=7)}
    raw_name = store().read(font, parts[0], space_gap=7)
    raw_price = store().read(font, parts[1])
    kind = None
    name = resolve(raw_name, MONSTER_NAMES)
    if name:
        kind = "monster"
    else:
        name = resolve(raw_name, ITEM_NAMES)
        if name:
            kind = "item"
    price = _to_int(raw_price[1:]) if raw_price.startswith("$") else None
    if name is None:
        problems.append(f"shop {i}: unknown name '{raw_name}'")
    if price is None:
        problems.append(f"shop {i}: cannot read price '{raw_price}'")
    stats = read_stat_badges(pic, _card_badges(i))
    if any(b["value"] is None for b in stats):
        problems.append(f"shop {i}: cannot read a stat badge")
    frame = pic[1300, 507 + 312 * i]
    rarity = next((r for r, c in FRAME_RARITY.items() if _near(frame, c, 20)), None)
    greyed = bool(_near(text_rgb, CARD_GREY, 4).sum() >= 300)
    return {"name": name, "price": price, "kind": kind, "stats": stats,
            "rarity": rarity, "greyed": greyed, "raw": raw_name}


# ------------------------------------------------------------- shop read ----

def read_shop(pic: np.ndarray) -> dict:
    problems: list[str] = []
    masks = text_masks(pic)
    st = store()

    def text(key: str) -> str:
        font, mask, opts = masks[key]
        return st.read(font, mask, **opts)

    def number(key: str, prefix: str = "") -> int | None:
        t = text(key)
        v = _to_int(t[len(prefix):]) if t.startswith(prefix) else None
        if v is None:
            problems.append(f"{key}: cannot read '{t}'")
        return v

    state: dict = {}
    state["lives"] = number("lives")
    state["day"] = number("day", "DAY")

    b = text("badges")
    won, _, goal = b.partition("/")
    state["badges"] = _to_int(won)
    state["badges_goal"] = _to_int(goal)
    if state["badges"] is None or state["badges_goal"] is None:
        problems.append(f"badges: cannot read '{b}'")

    t = text("trainer")
    state["trainer"] = resolve(t, TRAINER_NAMES, ignore_case=True)
    if state["trainer"] is None:
        problems.append(f"trainer: unknown name '{t}'")

    state["trainer_hp"] = number("hp")
    state["money"] = number("money", "$")

    # "Rank 4 *67% *30% *3% *0% *0%"   (* = the rarity gem)
    r = text("rank_bar")
    head, *odds = r.split("*")
    state["shop_rank"] = _to_int(head[4:]) if head.startswith("Rank") else None
    values = [_to_int(o[:-1]) if o.endswith("%") else None for o in odds]
    if state["shop_rank"] is None or not values or None in values or len(values) > len(RARITIES):
        problems.append(f"rank bar: cannot read '{r}'")
        state["shop_odds"] = None
    else:
        state["shop_odds"] = dict(zip(RARITIES, values))

    if text("reroll").startswith("FREE"):     # trainers with free rerolls: "FREE (3)"
        state["reroll_price"] = 0
    else:
        state["reroll_price"] = number("reroll", "$")
    # The button says LOCK (label 92 px wide) or, when the shop is locked, UNLOCK (138 px).
    label = glyphs.white(crop(pic, LOCK_BUTTON)).any(axis=0)
    cols = np.nonzero(label)[0]
    width = int(cols.max() - cols.min()) if len(cols) else 0
    state["locked"] = False if 82 <= width <= 102 else True if 128 <= width <= 148 else None
    if state["locked"] is None:
        problems.append(f"lock button: unknown look (label {width} px wide)")

    state["shop"] = [_read_shop_slot(pic, i, masks, problems) for i in range(SHOP_SLOTS)]
    state["team"] = [_read_owned_slot(pic, team_slot(i), f"team {i}", problems)
                     for i in range(TEAM_COLS * TEAM_ROWS)]
    state["bench"] = [_read_owned_slot(pic, bench_slot(i), f"bench {i}", problems)
                      for i in range(BENCH_SLOTS)]
    state["problems"] = problems
    return state


def read_state(image: Image.Image) -> dict:
    """Detect the screen and, on the shop screen, read everything on it."""
    pic = np.asarray(window.canonical_picture(image))
    state: dict = {"screen": detect_screen(pic)}
    if state["screen"] == "shop":
        state.update(read_shop(pic))
    elif state["screen"] in ("result", "stats", "matchmaking", "blank", "battle", "run_over"):
        state["problems"] = []            # recognised; nothing on them is read yet
    elif state["screen"] == "gift_box":
        state["problems"] = []
    elif state["screen"] == "trinket_pick":
        state.update(read_trinket_pick(pic))
    elif state["screen"] == "trainer_pick":
        state.update(read_trainer_pick(pic))
    elif state["screen"] == "new_run":
        state.update(read_new_run(pic))
    elif state["screen"] == "event":
        state["choices"] = len(event_choices(pic))
        state["problems"] = [] if state["choices"] else ["event: no choice boxes found"]
    else:
        state["problems"] = [f"screen '{state['screen']}' cannot be read yet"]
    size = window.crop_picture(image).size
    if size != (window.CANON_W, window.CANON_H):
        # The glyph templates were cut at this size; a scaled picture reads unreliably.
        state["problems"].append(
            f"game picture is {size[0]}x{size[1]}, templates need {window.CANON_W}x{window.CANON_H}")
    return state


def comparable(state: dict) -> dict:
    """A state without the fields that change from frame to frame (for tests and expected files)."""
    state = json.loads(json.dumps(state))
    state.pop("saved_capture", None)
    for slot in state.get("team", []) + state.get("bench", []):
        if slot:
            slot.pop("sprite_distance", None)
    return state


def main() -> int:
    """python reader.py [capture.png [--expect]]

    No argument: read the live game window. With --expect, also write
    <capture>.expected.json, which turns the capture into a test. Check the
    printed values against the picture by eye before keeping that file.
    """
    args = [a for a in sys.argv[1:] if a != "--expect"]
    if args:
        img = Image.open(args[0])
    else:
        hwnd = window.find_window()
        if hwnd is None or window.is_minimized(hwnd):
            print("Game window not found or minimized.")
            return 1
        img = window.capture_client(hwnd)
    state = read_state(img)
    print(json.dumps(state, indent=1))
    if args and "--expect" in sys.argv:
        out = Path(args[0]).with_suffix(".expected.json")
        out.write_text(json.dumps(comparable(state), indent=1), encoding="utf-8")
        print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
