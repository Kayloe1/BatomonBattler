r"""Tests for the checks in hands.py. No input is sent and the game is not needed."""
import copy
import json
import sys
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hands  # noqa: E402
import reader  # noqa: E402
import window  # noqa: E402

CAPTURE = ROOT / "captures" / "capture_20261111_101154_435562.png"
BEFORE = json.loads(CAPTURE.with_name(CAPTURE.stem + ".expected.json").read_text(encoding="utf-8"))


def after_buying(i, into=("team", 3)):
    s = copy.deepcopy(BEFORE)
    card = s["shop"][i]
    s["money"] -= card["price"]
    if card["kind"] == "monster":
        s[into[0]][into[1]] = {"name": None, "level": 1, "stats": card["stats"]}
    s["shop"][i] = None
    return s


class Checks(unittest.TestCase):
    def test_buy_ok(self):
        self.assertIsNone(hands.check_buy(BEFORE, after_buying(2), 2))

    def test_buy_item_ok(self):
        self.assertIsNone(hands.check_buy(BEFORE, after_buying(4), 4))

    def test_buy_nothing_happened(self):
        self.assertIsNotNone(hands.check_buy(BEFORE, BEFORE, 2))

    def test_buy_wrong_money(self):
        s = after_buying(2)
        s["money"] += 5
        self.assertIn("money", hands.check_buy(BEFORE, s, 2))

    def test_buy_left_the_shop(self):
        self.assertIn("screen", hands.check_buy(BEFORE, {"screen": "unknown"}, 2))

    def test_move_to_empty_slot(self):
        s = copy.deepcopy(BEFORE)
        s["team"][0], s["team"][4] = s["team"][4], None
        self.assertIsNone(hands.check_move(BEFORE, s, ("team", 4), ("team", 0)))
        self.assertIsNotNone(hands.check_move(BEFORE, BEFORE, ("team", 4), ("team", 0)))

    def test_swap_two_monsters(self):
        s = copy.deepcopy(BEFORE)
        s["team"][4], s["team"][5] = s["team"][5], s["team"][4]
        self.assertIsNone(hands.check_move(BEFORE, s, ("team", 4), ("team", 5)))

    def test_sell(self):
        s = copy.deepcopy(BEFORE)
        s["team"][5] = None
        self.assertIn("money", hands.check_sell(BEFORE, s, ("team", 5)))
        s["money"] += 5
        self.assertIsNone(hands.check_sell(BEFORE, s, ("team", 5)))

    def test_reroll(self):
        s = copy.deepcopy(BEFORE)
        self.assertIsNotNone(hands.check_reroll(BEFORE, s))
        s["money"] -= 3
        self.assertIsNone(hands.check_reroll(BEFORE, s))


class ClickTargets(unittest.TestCase):
    """The centre of every box the hands click must be on the right thing."""

    @classmethod
    def setUpClass(cls):
        cls.pic = window.canonical_picture(Image.open(CAPTURE))

    def centre(self, box):
        return self.pic.getpixel(((box[0] + box[2]) // 2, (box[1] + box[3]) // 2))

    def near(self, box, colour, tol=40, dy=0):
        x, y = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2 + dy
        px = self.pic.getpixel((x, y))
        self.assertTrue(all(abs(a - b) <= tol for a, b in zip(px, colour)), (box, px, colour))

    def test_buttons(self):
        self.near(reader.REROLL_BUTTON, (255, 206, 0), dy=-95)      # yellow, above the letters
        self.near(reader.BATTLE_BUTTON, (239, 66, 107), dy=-80)     # red
        self.near(reader.LOCK_BUTTON, (255, 206, 0), dy=-28)        # yellow

    def test_park_spot_is_plain_background(self):
        r, g, b = self.centre(hands.PARK)
        self.assertTrue(r < 80 and 80 < g < 180 and 90 < b < 200, (r, g, b))

    def test_slot_centres_are_inside_white_slots(self):
        for i in (0, 2, 3):                 # empty team slots in this capture
            self.assertEqual(self.centre(reader.team_slot(i)), (255, 255, 255))
        for i in range(reader.BENCH_SLOTS):
            self.assertEqual(self.centre(reader.bench_slot(i)), (255, 255, 255))

    def test_cards_do_not_overlap_and_sit_in_the_shop_bar(self):
        boxes = [reader.shop_card(i) for i in range(reader.SHOP_SLOTS)]
        for a, b in zip(boxes, boxes[1:]):
            self.assertLess(a[2], b[0])
        bar = reader.SELL_BAR
        for x0, y0, x1, y1 in boxes:
            self.assertTrue(bar[0] <= x0 and x1 <= bar[2] and bar[1] <= y0 and y1 <= bar[3] + 8)


if __name__ == "__main__":
    unittest.main()
