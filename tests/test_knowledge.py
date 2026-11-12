"""Tests for knowledge.py (pure rules, no game needed)."""
import csv
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import knowledge as k  # noqa: E402


def names(csv_name):
    with open(ROOT / "data" / csv_name, encoding="utf-8") as f:
        return {row["name"] for row in csv.DictReader(f)}


class Positions(unittest.TestCase):
    def test_behind_is_left_and_in_front_is_right(self):
        self.assertEqual(k.position_targets(1, "behind"), [0])
        self.assertEqual(k.position_targets(1, "in front"), [2])
        self.assertEqual(k.position_targets(0, "behind"), [])
        self.assertEqual(k.position_targets(5, "in front"), [])

    def test_above_and_below(self):
        self.assertEqual(k.position_targets(4, "above"), [1])
        self.assertEqual(k.position_targets(1, "above"), [])
        self.assertEqual(k.position_targets(1, "below"), [4])

    def test_adjacent_has_no_diagonals(self):
        self.assertEqual(sorted(k.position_targets(1, "adjacent")), [0, 2, 4])
        self.assertEqual(sorted(k.position_targets(3, "adjacent")), [0, 4])
        self.assertEqual(sorted(k.position_targets(4, "adjacent")), [1, 3, 5])

    def test_top_middle_is_the_carry_slot(self):
        self.assertEqual(k.neighbour_count(k.BEST_CARRY_SLOT), 3)
        self.assertEqual(max(k.neighbour_count(s) for s in range(3)), 3)

    def test_helper_slots_around_top_middle(self):
        self.assertEqual(k.helper_slot_for(1, "in front"), 0)   # Saberhorn left of the carry
        self.assertEqual(k.helper_slot_for(1, "behind"), 2)     # Boomagon right of the carry
        self.assertEqual(k.helper_slot_for(1, "above"), 4)      # Cicadence below the carry
        self.assertIsNone(k.helper_slot_for(4, "above"))        # bottom-row carry: no slot below
        for word in ("in front", "behind", "above"):
            self.assertIn(1, k.position_targets(k.helper_slot_for(1, word), word))

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            k.position_targets(6, "behind")
        with self.assertRaises(ValueError):
            k.position_targets(0, "diagonal")


class Lists(unittest.TestCase):
    def test_names_exist_in_the_data(self):
        monsters, items, trainers = names("batomon_pantra.csv"), names("items.csv"), names("trainers.csv")
        for n in list(k.NEVER_FIELD) + list(k.SELF_KNOCKOUT) + list(k.NEEDS_SUPPORT):
            if n != "Talonite":  # event monster (winged fossil), not in the shop roster
                self.assertIn(n, monsters)
        for n in list(k.ITEM_AUTO_OK) + list(k.ITEM_DECISIONS) + list(k.TICKETS):
            if n != "Upgrade Disc":  # comes from gifts, not the shop
                self.assertIn(n, items)
        for n in list(k.AVOID_TRAINERS) + k.TRAINER_PREFERENCE:
            self.assertIn(n, trainers)
        self.assertFalse(set(k.AVOID_TRAINERS) & set(k.TRAINER_PREFERENCE))

    def test_item_policy(self):
        self.assertEqual(k.item_policy("Coupon"), "auto")
        self.assertEqual(k.item_policy("Red Coin"), "decide")
        self.assertEqual(k.item_policy("Blue Ticket"), "decide")
        self.assertEqual(k.item_policy("Something New"), "decide")

    def test_eggs(self):
        self.assertTrue(k.is_egg("Dragon Egg"))
        self.assertTrue(k.is_egg("Purple Egg"))
        self.assertFalse(k.is_egg("Guardiant"))
        self.assertFalse(k.is_egg(None))

    def test_no_hard_numbers_in_rules(self):
        import re
        for rule in k.PLANNER_RULES:
            self.assertIsNone(re.search(r"\d", rule), rule)


if __name__ == "__main__":
    unittest.main()
