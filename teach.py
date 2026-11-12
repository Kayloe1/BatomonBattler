"""Teach the reader the glyphs and sprites of captures whose content is known.

    python teach.py

Rebuilds templates/glyphs.json and adds to templates/sprites/ from the labelled
captures listed in LESSONS. To teach a new glyph or monster, add a capture
with its true text here and run this again.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

import glyphs
import reader
import window

ROOT = Path(__file__).resolve().parent

# For each capture: the true text of each region. In "rank_bar" a "*" stands for
# a rarity gem. Card text is "<name>|<price>". Stat badges are listed as the
# digits of every badge in the slot, left to right, run together.
LESSONS = [
    {
        "file": "captures/capture_20261111_101154_435562.png",
        "text": {
            "lives": "10", "day": "DAY2", "badges": "1/10", "trainer": "RICH LADY",
            "hp": "500", "rank_bar": "Rank4*67%*30%*3%*0%*0%", "money": "$40", "reroll": "$3",
            "shop0": "Dribblet|$10", "shop1": "Pebbler|$15", "shop2": "Brawlmantis|$30",
            "shop3": "Berroon|$20", "shop4": "Gray Chip|$0",
        },
        "shop_badges": {0: "20", 1: "20", 2: "50", 3: "40"},
        # slot: (name, level, badge digits). Names are Claude's identification
        # from the stats in data/batomon_pantra.csv; Venopuff is the least certain.
        "team": {1: ("Venopuff", "1", "54"), 4: ("Mosslug", "1", "530"), 5: ("Panbud", "1", "25")},
        "bench": {},
    },
    {   # after using the Gray Chip: its slot refilled with Puffloon (heal 10, poison 1)
        "file": "captures/shop_day2_puffloon.png",
        "text": {"shop4": "Puffloon|$30"},
        "shop_badges": {4: "101"},
    },
    {   # after buying Brawlmantis: it sits in team slot 3 and covers part of its level label
        "file": "captures/shop_day2_bought.png",
        "team": {3: ("Brawlmantis", "1", "50")},
    },
    {   # day 3 after a win: new digits, a Rare (blue) card, "x2" multicast badges, a burn badge
        "file": "captures/shop_day3.png",
        "text": {
            "day": "DAY3", "badges": "2/10", "hp": "800", "money": "$75",
            "rank_bar": "Rank5*55%*30%*15%*0%*0%",
            "shop0": "Guardiant|$15", "shop1": "Magmite|$15", "shop2": "Aristobat|$25",
            "shop3": "Velocect|$15", "shop4": "Lucky Coin|$0",
        },
        "shop_badges": {0: "15", 1: "404", 2: "4x2", 3: "15x2"},
        "team": {0: ("Brawlmantis", "1", "60"), 1: ("Venopuff", "1", "154"), 2: ("Dribblet", "1", "1020"),
                 4: ("Mosslug", "1", "1530"), 5: ("Panbud", "1", "35")},
    },
    {   # after using Lucky Coin (+$3): the item slot refilled with another item
        "file": "captures/shop_day3_coupon.png",
        "text": {"money": "$78", "shop4": "Coupon|$0"},
    },
    {   # day 4 after a loss (10 -> 8 lives)
        "file": "captures/shop_day4.png",
        "text": {"day": "DAY4", "hp": "1400", "money": "$98", "rank_bar": "Rank6*45%*32%*20%*3%*0%",
                 "shop4": "Apex Bait|$20"},
        "team": {3: ("Electranade", "1", "25")},
    },
    {   # day 5 after a win
        "file": "captures/shop_day5.png",
        "text": {"day": "DAY5", "hp": "2400"},
        "team": {0: ("Brawlmantis", "1", "70")},
    },
    {   # day 6 after a loss (8 -> 5 lives); a Super Rare (purple) item with a long name
        "file": "captures/shop_day6.png",
        "text": {"day": "DAY6", "hp": "3800", "rank_bar": "Rank8*25%*30%*35%*10%*0%",
                 "shop0": "Formiqueen|$25", "shop1": "Scorchimp|$10", "shop2": "Magmalith|$30",
                 "shop3": "Craghorn|$25", "shop4": "Recruiting Flyer|$90"},
    },
    {   # day 7 after a loss (5 -> 2 lives); a Legendary (orange) item
        "file": "captures/shop_day7.png",
        "text": {"day": "DAY7", "hp": "5700", "rank_bar": "Rank9*20%*25%*38%*15%*2%",
                 "shop0": "Shelldra|$40", "shop1": "Magmite|$15", "shop2": "Boomagon|$30",
                 "shop3": "Dracana|$40", "shop4": "Rare Candy|$40"},
    },
    {   # after selling Electranade (bought for $25) for $13
        "file": "captures/shop_day7_sold.png",
        "text": {"money": "$316"},
    },
    {   # after a reroll ($3): Gaiadrasil costs $60 (data/names.json says 60)
        "file": "captures/shop_day7_reroll.png",
        "text": {"shop1": "Gaiadrasil|$60"},
    },
    {   # three-digit badges: the foot of the "1" reaches under the next digit
        "file": "captures/shop_day7_runerock.png",
        "shop_badges": {0: "140", 1: "125x2", 2: "100", 3: "6"},
    },
    {   # day 8 (1 life left), shop rank 10
        "file": "captures/shop_day8.png",
        "text": {"day": "DAY8", "rank_bar": "Rank10*15%*20%*40%*20%*5%"},
    },
    {   # trainer pick screen: card headers use the same font as the shop's trainer name
        "file": "captures/trainer_pick.png",
        "trainer_cards": ["WITCH", "PAINTER", "MONSTER RANGER"],
    },
    {   # day 1 of a new Casual run as Monster Ranger (starts with an Electranade)
        "file": "captures/shop_day1.png",
        "text": {"day": "DAY1"},
    },
    {   # second run, day 2: shop rank 2 is 90% Common, 10% Uncommon
        "file": "captures/shop_r2_day2.png",
        "text": {"rank_bar": "Rank2*90%*10%*0%*0%*0%"},
    },
    {   # second run, day 1 after two buys: sprites of Pebbler and Velocect
        "file": "captures/shop_day1_broke.png",
        "team": {3: ("Pebbler", "1", "20"), 4: ("Velocect", "1", "15x2")},
    },
    {   # a level 2 monster (silver label) and a burn badge raised to 9 by the Fire Bell trinket
        "file": "captures/shop_r2_day2_level2.png",
        "shop_badges": {2: "409"},
        "team": {5: ("Electranade", "2", "50")},
    },
    {   # second run, day 3: shop rank 3 is 75% Common, 25% Uncommon
        "file": "captures/shop_r2_day3.png",
        "text": {"rank_bar": "Rank3*75%*25%*0%*0%*0%"},
    },
    {   # a level 3 monster (gold label)
        "file": "captures/shop_r2_day7.png",
        "team": {5: ("Electranade", "3", "75")},
    },
    {   # Youngster day 1: "REROLL FREE (3)" (3 free rerolls a day) and a $0 Cake on a grey card
        "file": "captures/shop_day1_youngster_free_reroll.png",
        "text": {"reroll": "FREE(3)", "shop4": "Cake|$0"},
    },
    {   # Chef day 5: level 2 Magmite with shield 80 (first "8" in the badge font)
        "file": "captures/shop_chef_day5_badge8.png",
        "team": {5: ("Magmite", "2", "8010")},
    },
    {   # Chef day 6: shop rank 6 is 54% / 27% / 17% / 3% / 0% (first "7" in the rank bar)
        "file": "captures/shop_chef_day6_rank6.png",
        "text": {"rank_bar": "Rank6*54%*27%*17%*3%*0%"},
    },
    {   # Chef day 8: shop rank 8 is 38% / 25% / 29% / 8% / 0%
        "file": "captures/shop_chef_day8_rank8.png",
        "text": {"rank_bar": "Rank8*38%*25%*29%*8%*0%"},
    },
    {   # Chef day 9: trainer HP 11600
        "file": "captures/shop_chef_day9.png",
        "text": {"day": "DAY9", "hp": "11600"},
    },
    {   # Stats window, day 2: lines per card, as (header, slot): [text of each line]
        "file": "captures/stats_day2.png",
        "stats": {
            (0, 0): ["Dealt 150 damage", "Triggered 3 time(s)"],
            (0, 1): ["Dealt 25 damage", "Inflicted 20 Poison", "Triggered 5 time(s)"],
            (0, 2): ["Healed 120 HP", "Triggered 6 time(s)"],
            (0, 4): ["Dealt 75 damage", "Healed 90 HP", "Triggered 3 time(s)"],
            (0, 5): ["Dealt 75 damage", "Triggered 3 time(s)"],
            (1, 0): ["Dealt 1 damage", "Triggered 1 time(s)"],
        },
    },
    {   # Chef day 10 (first "0" in the title font)
        "file": "captures/shop_chef_day10.png",
        "text": {"day": "DAY10"},
    },
]


def _teach_digits(store: glyphs.GlyphStore, font: str, bitmaps: list[np.ndarray], digits: str, where: str) -> None:
    if len(bitmaps) != len(digits):
        raise ValueError(f"{where}: expected {len(digits)} digits, image has {len(bitmaps)}")
    for ch, bm in zip(digits, bitmaps):
        store.add(font, ch, bm)


def teach_stats(store: glyphs.GlyphStore, pic: np.ndarray, lesson: dict) -> None:
    """Stats window glyphs: digits of the number words, letters of the others."""
    for (h, slot), lines in lesson.get("stats", {}).items():
        bands = reader._stats_bands(reader.stats_card_images(pic)[(h, slot)])
        if len(bands) != len(lines):
            raise ValueError(f"stats ({h},{slot}): {len(lines)} lines expected, image has {len(bands)}")
        for (kind, words), text in zip(bands, lines):
            texts = text.split(" ")
            if len(texts) != len(words):
                raise ValueError(f"stats ({h},{slot}): '{text}' does not split into {len(words)} words")
            for w, (word, gl) in enumerate(zip(texts, words)):
                if len(word) != len(gl):
                    raise ValueError(f"stats ({h},{slot}): '{word}' has {len(gl)} glyphs")
                font = "statsdigit" if w == 1 else "statsword"
                for ch, g in zip(word, gl):
                    store.add(font, ch, g.bitmap)


def main() -> None:
    if glyphs.TEMPLATE_FILE.exists():
        glyphs.TEMPLATE_FILE.unlink()
    # Sprites are NOT wiped: hands.py saves new ones while playing (it knows what it
    # just bought), and those cannot be rebuilt from the lessons here.
    store = glyphs.GlyphStore()
    reader._store = store        # the reader's own helpers must see glyphs as they are taught
    for lesson in LESSONS:
        pic = np.asarray(window.canonical_picture(Image.open(ROOT / lesson["file"])))
        masks = reader.text_masks(pic)
        for key, truth in lesson.get("text", {}).items():
            font, mask, _ = masks[key]
            if "|" in truth:
                name, price = truth.split("|")
                left, right = reader._split_name_price(mask)
                store.teach(font, left, name)
                store.teach(font, right, price)
            else:
                store.teach(font, mask, truth)
        teach_stats(store, pic, lesson)
        for i, name in enumerate(lesson.get("trainer_cards", [])):
            store.teach("caps", glyphs.white(reader.crop(pic, reader._trainer_card_name(i))), name)
        for i, digits in lesson.get("shop_badges", {}).items():
            _teach_digits(store, "badge", reader.badge_digit_glyphs(pic, reader._card_badges(i)), digits, f"shop {i}")
        for kind, box_of in (("team", reader.team_slot), ("bench", reader.bench_slot)):
            for i, (name, level, digits) in lesson.get(kind, {}).items():
                x0, y0, x1, y1 = box_of(i)
                rgb = pic[y0:y1, x0:x1]
                store.add("level", level, glyphs.segment(reader.level_mask(rgb))[-1].bitmap)
                _teach_digits(store, "badge", reader.badge_digit_glyphs(pic, reader.owned_badge_band(box_of(i))),
                              digits, f"{kind} {i}")
                reader.learn_sprite(name, rgb)
    store.save()
    reader.reload_templates()
    for font, entries in sorted(store.fonts.items()):
        print(f"{font:8s} {len(entries):3d} glyphs: {''.join(sorted(set(l for l, _ in entries)))}")
    print("sprites:", sorted(p.stem for p in reader.SPRITE_DIR.glob('*.png')))


if __name__ == "__main__":
    main()
