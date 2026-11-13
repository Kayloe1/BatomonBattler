"""Learning a monster the bot cannot name from the game's hover panel."""
import csv
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

import learn_monsters
import reader
import window

ROOT = Path(__file__).resolve().parent.parent


class InfoPanel(unittest.TestCase):
    def test_pyrokami_panel(self):
        p = ROOT / "captures" / "info_panel_pyrokami.png"
        if not p.exists():
            self.skipTest("capture not here")
        r = reader.read_info_panel(np.asarray(window.canonical_picture(Image.open(p))))
        self.assertEqual((r["name"], r["rarity"], r["type"], r["cooldown"]), ("Pyrokami", "Rare", "Fire", 3.6))
        self.assertEqual(r["stats"], {"damage": 5, "burn": 5})

    def test_no_panel_on_other_screens(self):
        p = ROOT / "captures" / "stats_day2.png"
        self.assertFalse(reader.is_info_panel(np.asarray(window.canonical_picture(Image.open(p)))))

    def test_type_with_unknown_letters(self):
        self.assertEqual(reader._match_masked("? ?IRE", reader.TYPE_NAMES), "Fire")
        self.assertIsNone(reader._match_masked("???", reader.TYPE_NAMES))


class Learning(unittest.TestCase):
    def test_a_new_monster_is_added_once(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "foreign.csv"
            shutil.copy(learn_monsters.FOREIGN, path)
            panel = {"name": "Testmon", "rarity": "Super Rare", "type": "Ice", "cooldown": 4.5,
                     "stats": {"damage": 40, "shock": 10}, "capture": "captures/info_panels/x.png"}
            self.assertTrue(learn_monsters.add_monster(panel, path))
            self.assertFalse(learn_monsters.add_monster(panel, path))
            row = [r for r in csv.DictReader(open(path, newline="", encoding="utf-8")) if r["name"] == "Testmon"][0]
            self.assertEqual((row["cost"], row["cooldown_s"], row["active"]), ("40", "4.5", "Deal 40 damage; Shock 10"))
            self.assertEqual(row["passive"], "")
            self.assertIn("x.png", row["source"])

    def test_unnamed_slots_skip_the_dragon_egg(self):
        state = {"team": [{"name": None, "level": 1, "stats": [{"stat": "damage", "value": 1}]},
                          {"name": None, "level": 1, "stats": [{"stat": "burn", "value": 5}]}, None],
                 "bench": [{"name": "Mosslug", "level": 1, "stats": [{"stat": "heal", "value": 30}]}]}
        self.assertEqual(learn_monsters.unnamed_slots(state), [("team", 1)])


if __name__ == "__main__":
    unittest.main()
