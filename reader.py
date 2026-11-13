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
    # Main menu while a run is open: Continue / New Run / Batopedia / Settings / Quit (five red buttons)
    "main_menu_continue": [(900, 696, RED), (900, 848, RED), (900, 1000, RED), (900, 1152, RED), (900, 1304, RED),
                           (25, 1118, (21, 157, 216)), (25, 1238, (21, 157, 216))],
    # Main menu with no run open: New Run / Batopedia / Settings / Quit (four buttons, lower down).
    # The rows are different in the two menus, so neither can be taken for the other.
    "main_menu": [(900, 772, RED), (900, 924, RED), (900, 1076, RED), (900, 1228, RED),
                  (25, 1118, (21, 157, 216)), (25, 1238, (21, 157, 216))],
    # After Continue on the main menu: a panel with the saved run (mode, day, lives, badges, team) and
    # Cancel / Confirm. The hamburger button top right is greyed out while it shows.
    "continue_confirm": [(600, 1215, RED), (1900, 1215, RED), (850, 900, (231, 231, 231)), (1250, 850, (255, 255, 255)),
                         (2480, 110, (123, 123, 123)), (25, 1118, (21, 157, 216)), (25, 1238, (21, 157, 216))],
    # "Select a target": an event effect needs a monster. BENCH and MY TEAM panels sit in the middle,
    # Confirm (grey until a monster is clicked) and Back below them.
    "select_target": [(1500, 410, (255, 189, 8)), (1500, 760, PINK), (1350, 1330, RED), (1700, 1330, RED),
                      (400, 210, (255, 189, 8))],
    # Title screen: the logo, the dragon silhouette and the dark "PRESS ANY KEY TO START" label
    "title": [(768, 240, (237, 103, 250)), (1408, 240, (67, 249, 245)), (1280, 739, (111, 49, 71)),
              (890, 1045, (55, 55, 55)), (1650, 1045, (55, 55, 55))],
    # "Cash In": a trinket dialog (blue header, white body) with one red button, shop dimmed behind it
    "cash_in": [(1280, 255, (0, 132, 189)), (1280, 560, (255, 255, 255)), (1152, 1020, RED),
                (1408, 1046, RED), (25, 1315, (22, 22, 23))],
    # Battle: the two trainer portraits in the bottom corners (their frames do not move)
    "battle": [(30, 1160, (156, 156, 173)), (2530, 1160, (156, 156, 173)), (30, 1420, (255, 255, 255)),
               (2530, 1420, (255, 255, 255))],
}

FAST_FORWARD: Box = (1300, 15, 1420, 125)   # top centre of the battle screen; red when on


def fast_forward_on(pic: np.ndarray) -> bool:
    return bool(_near(pic[65, 1325], RED, 45))

# Buttons on the other screens
RESULT_CONFIRM: Box = BATTLE_BUTTON
TARGET_CONFIRM: Box = (850, 1290, 1225, 1385)
TARGET_BACK: Box = (1335, 1290, 1715, 1385)


def target_team_slot(i: int) -> Box:
    """Team slot i on the "Select a target" screen (same order as the shop: 0-2 top row, 3-5 bottom)."""
    col, row = i % TEAM_COLS, i // TEAM_COLS
    return (868 + 288 * col, 812 + 232 * row, 1108 + 288 * col, 996 + 232 * row)


def target_bench_slot(i: int) -> Box:
    return (708 + 288 * i, 456, 948 + 288 * i, 640)


def read_select_target(pic: np.ndarray) -> dict:
    """Team and bench on the "Select a target" screen, and whether Confirm can be pressed yet."""
    problems: list[str] = []
    team = [_read_owned_slot(pic, target_team_slot(i), f"target team {i}", problems)
            for i in range(TEAM_COLS * TEAM_ROWS)]
    bench = [_read_owned_slot(pic, target_bench_slot(i), f"target bench {i}", problems) for i in range(BENCH_SLOTS)]
    x0, y0, x1, y1 = TARGET_CONFIRM
    enabled = bool(_near(pic[y0:y1, x0:x1], RED, 40).mean() > 0.5)
    # badge reading problems here are not fatal: a slot can still be clicked
    return {"team": team, "bench": bench, "confirm_enabled": enabled, "problems": [], "notes": problems}


CONTINUE_CONFIRM: Box = (1300, 1160, 1955, 1265)
CONTINUE_CANCEL: Box = (590, 1160, 1245, 1265)
CONTINUE_MODE_LABEL: Box = (580, 600, 1000, 680)      # "CASUAL MODE", top left of the panel
CONTINUE_MODE_GREY = (126, 126, 126)
CASUAL_LABEL_FILE = ROOT / "templates" / "continue_casual_mode.png"


def continue_mode_mask(pic: np.ndarray) -> np.ndarray | None:
    """The mode label of the continue panel as a trimmed text mask (None if nothing is there)."""
    m = _near(crop(pic, CONTINUE_MODE_LABEL), CONTINUE_MODE_GREY, 10)
    ys, xs = np.nonzero(m)
    if len(ys) < 50:
        return None
    return m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def continue_mode(pic: np.ndarray) -> str | None:
    """"casual" only when the label is, pixel for pixel, the saved "CASUAL MODE" label; else None.

    Anything else (a Ranked label, a label never seen, a shifted picture) is None, and the bot
    then refuses to press Confirm. There is deliberately no way for this to return "ranked".
    """
    m = continue_mode_mask(pic)
    if m is None or not CASUAL_LABEL_FILE.exists():
        return None
    tpl = np.asarray(Image.open(CASUAL_LABEL_FILE).convert("L")) > 127
    if abs(m.shape[0] - tpl.shape[0]) > 1 or abs(m.shape[1] - tpl.shape[1]) > 1:
        return None
    h, w = min(m.shape[0], tpl.shape[0]), min(m.shape[1], tpl.shape[1])
    a, b = m[:h, :w], tpl[:h, :w]
    iou = np.logical_and(a, b).sum() / max(np.logical_or(a, b).sum(), 1)
    return "casual" if iou >= 0.97 else None


TITLE_ANYWHERE: Box = (1180, 1300, 1380, 1400)     # empty sky under the label
MAIN_MENU_NEW_RUN: Box = (845, 730, 1715, 815)        # only on the four-button menu
MAIN_MENU_CONTINUE: Box = (845, 654, 1715, 738)       # only on the five-button menu
CASH_IN_BUTTON: Box = (1088, 989, 1472, 1104)
RESULT_STATS: Box = (19, 330, 448, 451)
STATS_CLOSE: Box = (2240, 125, 2310, 200)
EVENT_CHOICE_COLUMN = 1500              # x that crosses every choice box
EVENT_CHOICE_ROWS = (630, 1075)         # y range the choice boxes can be in


def event_choices(pic: np.ndarray) -> list[Box]:
    """The white choice boxes of an event screen, top to bottom."""
    y0, y1 = EVENT_CHOICE_ROWS
    # white at either column: coloured words in a long effect line can cross one of them
    col = (pic[y0:y1, EVENT_CHOICE_COLUMN].min(axis=1) >= 240) | (pic[y0:y1, 1745].min(axis=1) >= 240)
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


EVENT_TEXT = (82, 82, 90)                # the effect line of a choice (its title above is paler grey)
# Effect lines seen so far. A line with glyphs the reader does not know yet is matched to these.
KNOWN_EVENT_EFFECTS = [
    "Turn a monster SHINY", "Gain Rainbow Berry", "Gain $20", "Gain $40", "Gain $60",
    "Gain Talonite", "Gain Winged Fossil", "Get a Super Rare trinket gift", "Get a Rare trinket gift",
    "Gain a random level 2 Super Rare monster", "Gain Mysterious Charm", "Gain Dragon Egg",
    "Gain Hero's Sword", "Randomly transform your monsters 1 rarity higher (max Mythical rarity)",
    "Give a monster Electric typing and +5 Shock", "Gain Gold-o-matic",
    "Gain a foreign Rare monster. It can now appear in your shop.", "Gain Kaleidoscope",
    "Gain Fake Diamond", "Gain Ignit", "Level up a monster (max level 4)", "Gain Research Notes",
]


def event_effect_mask(pic: np.ndarray, box: Box) -> np.ndarray:
    """Text mask of a choice's effect line: dark text plus its coloured words (Rare, $40, ...)."""
    x0, y0, x1, y1 = box
    v = pic[y0 + 44:y1, x0:x1].astype(int)
    mx, mn = v.max(axis=2), v.min(axis=2)
    return (np.abs(v - np.array(EVENT_TEXT)).max(axis=2) <= 14) | ((mx - mn >= 70) & (mn <= 170))


def read_event(pic: np.ndarray) -> dict:
    """The choices of an event: {"choices": n, "effects": [text or None], "raw": [...]}.

    An effect that cannot be read is None; that is not a "problem" (the bot can still pick by
    its fallback rule), and the raw reading is kept for teaching.
    """
    boxes = event_choices(pic)
    effects, raws = [], []
    for box in boxes:
        raw = store().read("event", event_effect_mask(pic, box), space_gap=7)
        raws.append(raw)
        # capital I and lowercase l are one glyph: a known line gives the right spelling
        known = resolve(raw, KNOWN_EVENT_EFFECTS)
        effects.append(known or (raw if raw and glyphs.UNKNOWN not in raw else None))
    return {"choices": len(boxes), "effects": effects, "raw": raws,
            "problems": [] if boxes else ["event: no choice boxes found"]}


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
    # capital I and lowercase l are the same glyph in the card font, and so are capital O and zero
    key = (lambda s: s.upper()) if ignore_case else (lambda s: s.replace("I", "l").replace("O", "0"))
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


def fill_number(text: str, expected: int | None) -> int | None:
    """A number read with unknown digits ("24?00"), completed from the value the game data expects.

    Only when the length fits, every digit that was read agrees, and at least half were read.
    The reader still never invents a value: the expected one must match what is on screen.
    """
    if expected is None or glyphs.UNKNOWN not in text:
        return None
    e = str(expected)
    known = sum(ch != glyphs.UNKNOWN for ch in text)
    if len(e) == len(text) and known * 2 >= len(text) and all(a == b or a == glyphs.UNKNOWN for a, b in zip(text, e)):
        return expected
    return None


def _list_cost(name: str | None, kind: str | None) -> int | None:
    try:
        from engine import data
        if kind == "monster":
            return data.roster()[name].cost
        if kind == "item":
            return data.items()[name]["cost"]
    except Exception:
        pass
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
    # A Shiny copy has its own templates ("Name@shiny"); the "clearly better" test is only
    # against other species, since a Shiny and a normal copy of one species look alike.
    others = [d for n, d in ranked[1:] if species_of(n) != species_of(best)]
    if best_d > SPRITE_MATCH_MAX or (others and best_d * 2 > others[0]):
        return None, best_d
    sp = species_of(best)
    if sp + SHINY_SUFFIX in by_name and sp in by_name:
        # Shape says which species; colour says whether it is the Shiny palette. The mean pixel
        # difference cannot tell (idle animation moves the sprite), a colour histogram can.
        h = _colour_hist(patch)
        d_norm = min(_hist_dist(h, _colour_hist(t)) for n, t in _sprite_templates()
                     if n == sp and t.shape == patch.shape)
        d_shiny = min(_hist_dist(h, _colour_hist(t)) for n, t in _sprite_templates()
                      if n == sp + SHINY_SUFFIX and t.shape == patch.shape)
        best = sp + SHINY_SUFFIX if d_shiny < d_norm else sp
        best_d = by_name[best]
    return best, best_d


def _colour_hist(patch: np.ndarray) -> np.ndarray:
    """Coarse colour histogram of the sprite's pixels (white background and black outline left out)."""
    px = patch.reshape(-1, 3).astype(int)
    keep = (px.min(axis=1) < 225) & (px.max(axis=1) > 40)
    px = px[keep] // 64
    if len(px) == 0:
        return np.zeros(64)
    h = np.bincount(px[:, 0] * 16 + px[:, 1] * 4 + px[:, 2], minlength=64).astype(float)
    return h / h.sum()


def _hist_dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.abs(a - b).sum())


SHINY_SUFFIX = "@shiny"


def species_of(sprite_name: str | None) -> str | None:
    """'Stingarde@shiny' -> 'Stingarde'."""
    if sprite_name is None:
        return None
    return sprite_name[:-len(SHINY_SUFFIX)] if sprite_name.endswith(SHINY_SUFFIX) else sprite_name


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


# ------------------------------------------------------------ battle screen ----
#
# At battle start both teams stand on the field: yours on the left facing right, the
# opponent's on the right, mirrored. Each monster has the same "LV. n" label, sprite and
# stat badges as on the shop screen, at the same offsets from its label, so a battle slot
# is a box of the same size as a team slot. The bottom row is shifted 80 px towards the
# back. Measured on captures/battle_day2.png.

BATTLE_ROW_Y = (479, 719)


def battle_slot(side: int, i: int) -> Box:
    """Battle slot i (0-2 top row, 3-5 bottom row, column 0 = the back) of side 0 (you) or 1."""
    col, row = i % TEAM_COLS, i // TEAM_COLS
    if side == 0:
        x0 = (543 if row == 0 else 463) + 240 * col
    else:
        x0 = (1775 if row == 0 else 1855) - 240 * col
    y0 = BATTLE_ROW_Y[row]
    return (x0, y0, x0 + 240, y0 + 184)


CARD_SPRITE_DIR = ROOT / "templates" / "card_sprites"
CARD_SPRITE_ROWS = (1186, 1290)     # the picture part of a shop card, above its badges
CARD_SPRITES_PER_NAME = 3
BATTLE_SPRITE_MAX = 45.0   # RMS colour difference over the sprite's own pixels
BATTLE_SEARCH = 24         # sprites bob and sit a little differently; search this far around

_battle_tpls: list[tuple[str, np.ndarray, np.ndarray]] | None = None


def card_sprite(pic: np.ndarray, i: int) -> tuple[np.ndarray, np.ndarray] | None:
    """The monster drawn on shop card i, as (rgb, mask). The card's coloured panel is
    removed by flood-filling from the edges up to the sprite's dark outline."""
    x0, _, x1, _ = shop_card(i)
    r = pic[CARD_SPRITE_ROWS[0]:CARD_SPRITE_ROWS[1], x0 + 8:x1 - 8]
    outline = r.max(axis=2) < 70
    n, lab = cv2.connectedComponents((~outline).astype(np.uint8), connectivity=4)
    edge = (set(lab[0]) | set(lab[:, 0]) | set(lab[:, -1])) - {0}
    mask = ~(np.isin(lab, list(edge)) & ~outline)
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if n < 2:
        return None
    mask = lab == 1 + int(np.argmax(st[1:, 4]))
    ys, xs = np.nonzero(mask)
    if len(xs) < 300:
        return None
    y0, y1, xa, xb = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return r[y0:y1, xa:xb].copy(), mask[y0:y1, xa:xb]


def learn_card_sprites(pic: np.ndarray, state: dict) -> list[Path]:
    """Save the sprites of named monster cards in a shop (up to a few per name).

    These let read_battle() name opponent monsters the bot has never owned.
    """
    saved = []
    CARD_SPRITE_DIR.mkdir(parents=True, exist_ok=True)
    for i, card in enumerate(state.get("shop") or []):
        if not card or card.get("kind") != "monster" or not card.get("name"):
            continue
        if card.get("shiny"):
            continue                      # a Shiny palette would teach a wrong colour for the species
        name = card["name"]
        have = list(CARD_SPRITE_DIR.glob(f"{name}.png")) + list(CARD_SPRITE_DIR.glob(f"{name}__*.png"))
        if len(have) >= CARD_SPRITES_PER_NAME:
            continue
        cs = card_sprite(pic, i)
        if cs is None:
            continue
        rgb, mask = cs
        if any(_same_sprite(rgb, mask, p) for p in have):
            continue
        k = 0
        while True:
            path = CARD_SPRITE_DIR / (f"{name}.png" if k == 0 else f"{name}__{k}.png")
            if not path.exists():
                break
            k += 1
        rgba = np.dstack([rgb, (mask * 255).astype(np.uint8)])
        Image.fromarray(rgba, "RGBA").save(path)
        saved.append(path)
    if saved:
        global _battle_tpls
        _battle_tpls = None
    return saved


def _same_sprite(rgb: np.ndarray, mask: np.ndarray, path: Path) -> bool:
    old = np.asarray(Image.open(path).convert("RGBA"))
    if old.shape[:2] != rgb.shape:
        return False
    return bool(np.abs(old[..., :3].astype(int) - rgb.astype(int))[mask].mean() < 3)


def _battle_templates() -> list[tuple[str, np.ndarray, np.ndarray]]:
    """(name, rgb, mask) from the team-slot sprites (white background) and the card sprites."""
    global _battle_tpls
    if _battle_tpls is None:
        _battle_tpls = []
        for name, tpl in _sprite_templates():
            mask = np.abs(tpl.astype(int) - 255).sum(axis=2) > 60
            if mask.sum() >= 50:
                _battle_tpls.append((name, tpl, mask))
        if CARD_SPRITE_DIR.exists():
            for p in sorted(CARD_SPRITE_DIR.glob("*.png")):
                a = np.asarray(Image.open(p).convert("RGBA"))
                _battle_tpls.append((p.stem.split("__")[0], a[..., :3].copy(), a[..., 3] > 127))
    return _battle_tpls


def match_battle_sprite(pic: np.ndarray, box: Box, mirrored: bool) -> tuple[str | None, float]:
    """Name a monster on the battle field from the saved sprites.

    The field is grass, not the white slot, so only the template's own pixels are
    compared (a masked template match). The opponent's monsters face the other way.
    Same monster: about 0-30; a different one: 75 or more.
    """
    x0, y0, x1, y1 = box
    m = BATTLE_SEARCH
    region = pic[max(y0 - m, 0):y0 + 150, max(x0 - m, 0):x1 + m].astype(np.float32)
    by_name: dict[str, float] = {}
    for name, rgb, mask in _battle_templates():
        t, k = (rgb[:, ::-1], mask[:, ::-1]) if mirrored else (rgb, mask)
        if t.shape[0] > region.shape[0] or t.shape[1] > region.shape[1]:
            continue
        m3 = np.repeat(k[..., None], 3, axis=2).astype(np.float32)
        res = cv2.matchTemplate(region, np.ascontiguousarray(t, dtype=np.float32), cv2.TM_SQDIFF, mask=m3)
        d = float(np.sqrt(max(res.min(), 0.0) / m3.sum()))
        by_name[name] = min(d, by_name.get(name, 1e9))
    if not by_name:
        return None, 1e9
    ranked = sorted(by_name.items(), key=lambda kv: kv[1])
    best, best_d = ranked[0]
    if best_d > BATTLE_SPRITE_MAX or (len(ranked) > 1 and best_d * 2 > ranked[1][1]):
        return None, best_d
    return best, best_d


def _read_battle_slot(pic: np.ndarray, side: int, i: int, problems: list[str]) -> dict | None:
    box = battle_slot(side, i)
    rgb = crop(pic, box)
    fill = level_mask(rgb)
    if fill.sum() < 20:
        return None                       # no "LV." label: empty slot
    where = f"{'my' if side == 0 else 'opponent'} slot {i}"
    parts = glyphs.segment(fill)
    level_text = store().classify("level", parts[-1].bitmap)[0] if len(parts) >= 3 else ""
    level = _to_int(level_text)
    if level is None:
        problems.append(f"{where}: cannot read level ('{level_text}')")
    badges = read_stat_badges(pic, owned_badge_band(box))
    if any(b["value"] is None for b in badges):
        problems.append(f"{where}: cannot read a stat badge")
    name, dist = match_battle_sprite(pic, box, mirrored=side == 1)
    return {"name": name, "level": level, "stats": badges,
            "sprite_distance": round(dist, 1) if dist < 1e8 else None}


def read_battle(pic: np.ndarray) -> dict:
    """Both teams on the battle screen. Read it at the start, before badges change.

    Monster names come from the sprites the bot has saved; an unknown monster has name
    None (its level, badges and slot are still read). Unknown names are not problems:
    the battle can go on, and the capture is kept so the name can be taught later.
    """
    problems: list[str] = []
    teams = [[_read_battle_slot(pic, side, i, problems) for i in range(TEAM_COLS * TEAM_ROWS)]
             for side in (0, 1)]
    return {"my_team": teams[0], "opponent_team": teams[1], "problems": problems}


# ------------------------------------------------ Stats window and end HP ----
# The Stats window (opened from the result box) lists, for each of the 6 slots of "MY TEAM" and
# of "OPPONENT TEAM", lines such as "Dealt 150 damage", "Healed 120 HP", "Inflicted 20 Poison"
# and "Triggered 3 time(s)". Each kind of line has its own colour. The opponent team sits below
# the window's edge until it is scrolled.

STATS_LINE_COLOURS = {"dealt": (239, 66, 107), "inflicted": (123, 87, 161),
                      "healed": (87, 138, 201), "triggered": (121, 174, 208)}
STATS_BORDER = (156, 156, 173)
STATS_VIEW_Y = (250, 1318)       # the part of the window that shows cards (the rest is frame)
STATS_CARD_TOP_GAP, STATS_CARD_H, STATS_ROW_PITCH = 19, 237, 260
STATS_SPRITE_W = 170             # left part of a card, where the monster's picture sits
STATS_WORD_GAP = 7               # columns of empty space that separate words
STATS_SCROLL_POINT: Box = (1200, 700, 1300, 760)
KNOWN_STATUSES = ["Poison", "Shock", "Burn"]


def stats_headers(pic: np.ndarray) -> list[tuple[int, int]]:
    """y ranges of the yellow section headers (MY TEAM, OPPONENT TEAM) that are visible."""
    col = _near(pic[STATS_VIEW_Y[0] - 60:STATS_VIEW_Y[1], 1500], YELLOW, 12)
    out, y = [], 0
    while y < len(col):
        if col[y]:
            start = y
            while y < len(col) and col[y]:
                y += 1
            if y - start >= 30:
                out.append((STATS_VIEW_Y[0] - 60 + start, STATS_VIEW_Y[0] - 60 + y))
        else:
            y += 1
    return out


def _stats_cell_edges(pic: np.ndarray, top: int) -> list[tuple[int, int]]:
    """x ranges of the cards in the row whose top is at y=top (found from their grey borders)."""
    band = _near(pic[top + 40:top + STATS_CARD_H - 40, 250:2290], STATS_BORDER, 10)
    cols = band.mean(axis=0) >= 0.9
    lines, x = [], 0
    while x < len(cols):
        if cols[x]:
            s = x
            while x < len(cols) and cols[x]:
                x += 1
            lines.append((250 + s, 250 + x))
        else:
            x += 1
    # a card has a left and a right line; neighbouring cards have a gap between their lines
    cells = [(a[1], b[0]) for a, b in zip(lines, lines[1:]) if b[0] - a[1] > 300]
    return cells


def _stats_bands(rgb: np.ndarray) -> list[tuple[str, list[list[glyphs.Glyph]]]]:
    """The text lines of one card (the part right of the picture) as (kind, words of glyphs)."""
    anyline = np.zeros(rgb.shape[:2], dtype=bool)
    for c in STATS_LINE_COLOURS.values():
        anyline |= _near(rgb, c, 12)
    rows = np.nonzero(anyline.any(axis=1))[0]
    if not len(rows):
        return []
    bands, start, prev = [], rows[0], rows[0]
    for y in rows[1:]:
        if y - prev > 3:
            bands.append((start, prev + 1))
            start = y
        prev = y
    bands.append((start, prev + 1))
    out = []
    for y0, y1 in bands:
        band = rgb[y0:y1]
        kind = max(STATS_LINE_COLOURS, key=lambda k: _near(band, STATS_LINE_COLOURS[k], 12).sum())
        mask = _near(band, STATS_LINE_COLOURS[kind], 12)
        words, cur = [], []
        for g in glyphs.segment(mask, min_pixels=4):
            if cur and g.x0 - cur[-1].x1 >= STATS_WORD_GAP:
                words.append(cur)
                cur = []
            cur.append(g)
        if cur:
            words.append(cur)
        out.append((kind, words))
    return out


def stats_card_images(pic: np.ndarray) -> dict[tuple[int, int], np.ndarray]:
    """(header, slot) -> the text part of each visible card (used by teach.py)."""
    out = {}
    heads = stats_headers(pic)
    for h, (hy0, hy1) in enumerate(heads):
        for row in range(2):
            top = hy1 + STATS_CARD_TOP_GAP + STATS_ROW_PITCH * row
            if top < STATS_VIEW_Y[0] or top + STATS_CARD_H > STATS_VIEW_Y[1]:
                continue
            for col, (x0, x1) in enumerate(_stats_cell_edges(pic, top)):
                out[(h, row * 3 + col)] = pic[top + 8:top + STATS_CARD_H - 8, x0 + 8 + STATS_SPRITE_W:x1 - 8]
    return out


def _stats_lines(rgb: np.ndarray, problems: list[str], where: str) -> dict:
    """Read the text lines of one card (the part right of the monster picture)."""
    out: dict = {}
    for kind, words in _stats_bands(rgb):
        if len(words) < 2:
            problems.append(f"{where}: cannot split a '{kind}' line into words")
            continue
        digits = "".join(store().classify("statsdigit", g.bitmap)[0] for g in words[1])
        value = _to_int(digits)
        if value is None:
            problems.append(f"{where}: cannot read the number of a '{kind}' line ('{digits}')")
        if kind == "inflicted":
            raw = "".join(store().classify("statsword", g.bitmap)[0] for g in words[2]) if len(words) > 2 else ""
            status = resolve(raw, KNOWN_STATUSES, ignore_case=True) or (raw if raw and "?" not in raw else None)
            if status is None:
                problems.append(f"{where}: unknown status word '{raw}'")
                status = raw or "?"
            out.setdefault("inflicted", {})[status] = value
        else:
            out[kind] = value
    return out


def read_stats_window(pic: np.ndarray) -> dict:
    """Every card visible in the Stats window: {"cells": [{"section", "row", "col", "present",
    "lines"}], "headers": n, "problems": [...]}.

    section is "my" for cards under the first header and "opponent" for cards under the last one
    (the window starts scrolled to the top, so the first header seen there is MY TEAM; once scrolled
    down only the opponent's header is left, which read_stats() relies on).
    """
    problems: list[str] = []
    heads = stats_headers(pic)
    cells = []
    for h, (hy0, hy1) in enumerate(heads):
        for row in range(2):
            top = hy1 + STATS_CARD_TOP_GAP + STATS_ROW_PITCH * row
            if top < STATS_VIEW_Y[0] or top + STATS_CARD_H > STATS_VIEW_Y[1]:
                continue                       # off the visible part of the window
            nxt = heads[h + 1][0] if h + 1 < len(heads) else 10 ** 9
            if top + STATS_CARD_H > nxt:
                continue
            edges = _stats_cell_edges(pic, top)
            if len(edges) != 3:
                problems.append(f"stats: found {len(edges)} cards (not 3) in row {row} under header {h}")
                continue
            for col, (x0, x1) in enumerate(edges):
                card = pic[top + 8:top + STATS_CARD_H - 8, x0 + 8:x1 - 8]
                sprite = card[:, :STATS_SPRITE_W]
                present = bool((sprite.min(axis=2) < 215).mean() > 0.02)
                where = f"stats header {h} row {row} col {col}"
                lines = _stats_lines(card[:, STATS_SPRITE_W:], problems, where)
                cells.append({"header": h, "headers": len(heads), "row": row, "col": col,
                              "slot": row * 3 + col, "present": present or bool(lines), "lines": lines})
    return {"cells": cells, "headers": len(heads), "problems": problems}


def read_stats(top_pic: np.ndarray, scrolled_pic: np.ndarray | None) -> dict:
    """Both teams' stats: {"my_team": [6 x lines-or-None], "opponent_team": [...], "problems": [...]}.

    top_pic is the window as it opens, scrolled_pic the same window scrolled to the bottom.
    My team is read from the first header of top_pic; the opponent's from the last header of
    scrolled_pic (both rows are visible there), or from top_pic if scrolling failed and the row fits.
    """
    a = read_stats_window(top_pic)
    problems = list(a["problems"])
    my: list = [None] * 6
    opp: list = [None] * 6
    for c in a["cells"]:
        if c["header"] == 0 and c["headers"] >= 1:
            my[c["slot"]] = c["lines"] if c["present"] else None
    sources = [read_stats_window(scrolled_pic)] if scrolled_pic is not None else []
    sources.append(a)
    got = set()
    for src in sources:
        problems += [p for p in src["problems"] if p not in problems]
        for c in src["cells"]:
            last = c["header"] == c["headers"] - 1 and (c["headers"] >= 2 or src is not a)
            if last and c["slot"] not in got:
                opp[c["slot"]] = c["lines"] if c["present"] else None
                got.add(c["slot"])
        if len(got) == 6:
            break
    if len(got) < 6:
        problems.append(f"stats: opponent slots seen {sorted(got)} of 0-5 (scroll may have failed)")
    return {"my_team": my, "opponent_team": opp, "problems": problems}


# End of battle: the HP bars on the (dimmed) result screen. The bar fills from the left.
RESULT_BARS = {"me": (564, 1160), "opponent": (1488, 2084)}      # x range of each bar's track
RESULT_BAR_Y = 336


def read_result_hp(pic: np.ndarray) -> dict:
    """Fraction of HP each trainer has left at the end of the battle (0.0 to 1.0).

    Measured as the width of the coloured part of the bar; multiply by the trainer's HP.
    """
    out = {}
    row = pic[RESULT_BAR_Y].astype(int)
    for side, (x0, x1) in RESULT_BARS.items():
        seg = row[x0:x1]
        neutral = (seg.max(axis=1) - seg.min(axis=1)) <= 3          # empty track is plain grey
        filled = ~neutral
        n = 0
        while n < len(filled) and filled[n]:
            n += 1
        out[side] = round(n / (x1 - x0), 3)
    return out


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
    slot = {"name": species_of(name), "level": level, "stats": badges,
            "sprite_distance": round(dist, 1) if dist < 1e8 else None}
    if name and name.endswith(SHINY_SUFFIX):
        slot["shiny"] = True
    return slot


def _read_shop_slot(pic: np.ndarray, i: int, masks: dict, problems: list[str],
                    notes: list[str] | None = None) -> dict | None:
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
    if price is None and raw_price.startswith("$"):
        price = fill_number(raw_price[1:], _list_cost(name, kind))
        if price is not None and notes is not None:
            notes.append(f"shop {i}: price '{raw_price}' completed to ${price}, the list price of {name}")
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
    card = {"name": name, "price": price, "kind": kind, "stats": stats,
            "rarity": rarity, "greyed": greyed, "raw": raw_name}
    if kind == "monster" and shiny_tag_score(pic, i) >= SHINY_TAG_MIN:
        card["shiny"] = True
    return card


# A Shiny shop card has a pastel "SHINY" word with a thick black outline at its top right. Its
# outline mask (cut from captures/manual_shop_glimmer_all_shiny_cards.png) scores 0.95-1.0 on
# Shiny cards and at most 0.23 on the plain cards of 50+ saved shop captures.
SHINY_TAG_MIN = 0.6
_shiny_tag: np.ndarray | None = None


def shiny_tag_score(pic: np.ndarray, i: int) -> float:
    global _shiny_tag
    if _shiny_tag is None:
        _shiny_tag = (np.asarray(Image.open(ROOT / "templates" / "shiny_tag.png")) > 127).astype(np.float32)
    x0 = shop_card(i)[0]
    region = pic[1152:1230, x0 + 142:x0 + 318]
    dark = (region.max(axis=2) < 60).astype(np.float32)
    if dark.shape[0] < _shiny_tag.shape[0] or dark.shape[1] < _shiny_tag.shape[1] or dark.sum() == 0:
        return 0.0
    return float(cv2.matchTemplate(dark, _shiny_tag, cv2.TM_CCOEFF_NORMED).max())


# ------------------------------------------------------------- shop read ----

def read_shop(pic: np.ndarray) -> dict:
    problems: list[str] = []
    notes: list[str] = []     # values completed from the game data; not a reason to stop
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

    state["money"] = number("money", "$")
    hp_text = text("hp")
    state["trainer_hp"] = _to_int(hp_text)
    if state["trainer_hp"] is None and state["day"] is not None:
        from engine import data
        state["trainer_hp"] = fill_number(hp_text, data.hp_for_day(state["day"]))
        if state["trainer_hp"] is not None:
            notes.append(f"hp: '{hp_text}' completed to {state['trainer_hp']}, the HP of day {state['day']}")
    if state["trainer_hp"] is None:
        problems.append(f"hp: cannot read '{hp_text}'")

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

    state["shop"] = [_read_shop_slot(pic, i, masks, problems, notes) for i in range(SHOP_SLOTS)]
    state["team"] = [_read_owned_slot(pic, team_slot(i), f"team {i}", problems)
                     for i in range(TEAM_COLS * TEAM_ROWS)]
    state["bench"] = [_read_owned_slot(pic, bench_slot(i), f"bench {i}", problems)
                      for i in range(BENCH_SLOTS)]
    state["problems"] = problems
    state["notes"] = notes
    return state


def read_state(image: Image.Image) -> dict:
    """Detect the screen and, on the shop screen, read everything on it."""
    pic = np.asarray(window.canonical_picture(image))
    state: dict = {"screen": detect_screen(pic)}
    if state["screen"] == "shop":
        state.update(read_shop(pic))
    elif state["screen"] in ("result", "stats", "matchmaking", "blank", "battle", "run_over", "main_menu", "main_menu_continue", "cash_in", "title"):
        # recognised. The battle field is read with read_battle() only on request: it takes
        # a few seconds, too slow for every frame while waiting.
        state["problems"] = []            # recognised; nothing on them is read yet
    elif state["screen"] == "continue_confirm":
        state["mode"] = continue_mode(pic)
        state["problems"] = []            # an unreadable mode is not a reading error: hands refuses to confirm
    elif state["screen"] == "select_target":
        state.update(read_select_target(pic))
    elif state["screen"] == "gift_box":
        state["problems"] = []
    elif state["screen"] == "trinket_pick":
        state.update(read_trinket_pick(pic))
    elif state["screen"] == "trainer_pick":
        state.update(read_trainer_pick(pic))
    elif state["screen"] == "new_run":
        state.update(read_new_run(pic))
    elif state["screen"] == "event":
        state.update(read_event(pic))
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
    if not state.get("notes"):
        state.pop("notes", None)          # expected files written before notes existed
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
