"""The Stats window, the end-of-battle HP bars, and logging them for the simulator check."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

import reader
import window
from sim import from_logs

ROOT = Path(__file__).resolve().parent.parent


def pic(name: str) -> np.ndarray:
    return np.asarray(window.canonical_picture(Image.open(ROOT / "captures" / name)))


class StatsWindow(unittest.TestCase):
    def test_visible_cards_are_read(self):
        r = reader.read_stats_window(pic("stats_day2.png"))
        self.assertEqual(r["problems"], [])
        by = {(c["header"], c["slot"]): c for c in r["cells"]}
        self.assertEqual(by[(0, 0)]["lines"], {"dealt": 150, "triggered": 3})
        self.assertEqual(by[(0, 1)]["lines"], {"dealt": 25, "inflicted": {"Poison": 20}, "triggered": 5})
        self.assertEqual(by[(0, 2)]["lines"], {"healed": 120, "triggered": 6})
        self.assertFalse(by[(0, 3)]["present"])
        self.assertEqual(by[(0, 4)]["lines"], {"dealt": 75, "healed": 90, "triggered": 3})
        self.assertEqual(by[(1, 0)]["lines"], {"dealt": 1, "triggered": 1})

    def test_shock_burn_shield_lines_and_wide_threes(self):
        # yellow Shock, orange Burn and brown "Applied N shield" lines; the wide 3 of "Triggered 3"
        name = "battles/20261112_132653_stats_top.png"
        if not (ROOT / "captures" / name).exists():
            self.skipTest(f"captures/{name} not here")
        r = reader.read_stats_window(pic(name))
        self.assertEqual(r["problems"], [])
        by = {(c["header"], c["slot"]): c["lines"] for c in r["cells"]}
        self.assertEqual(by[(0, 4)], {"dealt": 75, "inflicted": {"Shock": 10}, "triggered": 10})
        self.assertEqual(by[(1, 1)], {"shielded": 200, "inflicted": {"Burn": 20}, "triggered": 5})

    def test_unscrolled_window_reports_the_missing_opponent_row(self):
        r = reader.read_stats(pic("stats_day2.png"), None)
        self.assertEqual(r["my_team"][0], {"dealt": 150, "triggered": 3})
        self.assertIsNone(r["my_team"][3])
        self.assertEqual(r["opponent_team"][0], {"dealt": 1, "triggered": 1})
        self.assertTrue(any("scroll" in p for p in r["problems"]))

    def test_screen_is_recognised(self):
        self.assertEqual(reader.detect_screen(pic("stats_day2.png")), "stats")


class EndHp(unittest.TestCase):
    def test_day3_loss(self):
        hp = reader.read_result_hp(pic("result_loss_day3.png"))
        self.assertEqual(hp["me"], 0.0)
        self.assertAlmostEqual(hp["opponent"], 124 / 800, delta=0.02)


def _seen_slot(s):
    if not s:
        return None
    return {"name": s["name"], "level": s["level"],
            "stats": [{"stat": k, "value": v} for k, v in s["stats"].items()]}


class LogsWithStats(unittest.TestCase):
    def test_stats_become_units_and_the_simulator_is_compared(self):
        case = json.loads((ROOT / "sim" / "cases" / "day2_rich_lady_win.json").read_text(encoding="utf-8"))
        lines_a = [None] * 6
        for slot, u in case["expect"]["a_units"].items():
            inflicted = {"Poison": u["inflicted_poison"]} if "inflicted_poison" in u else {}
            lines_a[int(slot) - 1] = {k: v for k, v in u.items() if k != "inflicted_poison"}
            if inflicted:
                lines_a[int(slot) - 1]["inflicted"] = inflicted
        recs = [
            {"kind": "battle", "day": 2, "trainer": "Rich Lady", "trainer_hp": 500,
             "seen": {"my_team": [_seen_slot(s) for s in case["a"]["slots"]],
                      "opponent_team": [_seen_slot(s) for s in case["b"]["slots"]], "problems": []}},
            {"kind": "battle_stats", "day": 2, "my_team": lines_a, "opponent_team": [None] * 6,
             "end_hp_fraction": {"me": 0.4, "opponent": 0.0}, "problems": []},
            {"kind": "day_result", "day": 1, "badges": 1, "lives": 0},
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "run_x.jsonl"
            p.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
            cases = from_logs.battles_from_log(p)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["result"], "win")
        self.assertIn("stats", cases[0])
        err = from_logs.stats_error(cases[0])
        self.assertIsNotNone(err)
        self.assertLess(err["mean_abs_error"], 1.0)    # the day 2 case is reproduced exactly


if __name__ == "__main__":
    unittest.main()


class LoggedTeamNames(unittest.TestCase):
    def test_unnamed_battle_slot_takes_the_unique_team_match(self):
        badge = lambda stat, v: {"stat": stat, "value": v}
        team = [{"name": "Reapra", "level": 1, "stats": [badge("damage", 120)]},
                {"name": "Spinarai", "level": 2, "stats": [badge("damage", 6), badge("poison", 11)]},
                {"name": "Joltail", "level": 1, "stats": [badge("damage", 30)]},
                {"name": "Ironcore", "level": 1, "stats": [badge("damage", 30)]}]
        slots = [from_logs._slot({"name": None, "level": 1, "stats": [badge("damage", 120)]}),
                 from_logs._slot({"name": None, "level": 1, "stats": [badge("damage", 30)]})]
        from_logs._name_from_team(slots, team)
        self.assertEqual(slots[0]["name"], "Reapra")
        self.assertIsNone(slots[1]["name"])          # Joltail or Ironcore: not unique


class BattleSpriteRule(unittest.TestCase):
    def test_acceptance(self):
        self.assertTrue(reader._battle_match_ok(42, 49))      # Bumblebolt, seen right
        self.assertTrue(reader._battle_match_ok(63, 82))      # Spinarai with an effect on it
        self.assertFalse(reader._battle_match_ok(60, 73))     # Aristobat on a Shiny monster: wrong
        self.assertFalse(reader._battle_match_ok(70, 140))    # too far from anything


class ScrolledStats(unittest.TestCase):
    def test_scrolled_window_gives_all_six_opponents(self):
        # the first real scrolled picture: the yellow scroll handle covers the old frame point
        top, bottom = "battles/20261113_085236_stats_top.png", "battles/20261113_085236_stats_bottom.png"
        if not (ROOT / "captures" / bottom).exists():
            self.skipTest("captures not here")
        a, b = pic(top), pic(bottom)
        self.assertTrue(reader.is_stats_window(b))
        r = reader.read_stats(a, b)
        self.assertEqual(r["problems"], [])
        self.assertEqual(r["opponent_team"][3], {"inflicted": {"Poison": 6}, "triggered": 6})
        self.assertEqual(r["opponent_team"][4], {"healed": 140, "inflicted": {"Poison": 161}, "triggered": 14})


class StatsNames(unittest.TestCase):
    def test_both_teams_are_named_from_the_stats_cards(self):
        top, bottom = "battles/20261113_085236_stats_top.png", "battles/20261113_085236_stats_bottom.png"
        if not (ROOT / "captures" / bottom).exists():
            self.skipTest("captures not here")
        r = reader.read_stats(pic(top), pic(bottom))
        self.assertEqual(r["my_names"], ["Ironcore", "Bumblebolt", "Runerock", "Frizzly", "Venopuff", "Velocect"])
        self.assertEqual(r["opponent_names"], ["Spinarai", "Puffloon", "Shogapede", "Noxnimbus", "Puffloon", "Venopuff"])

    def test_unnamed_battle_slots_take_the_stats_names(self):
        case = {"a": {"slots": [from_logs._slot({"name": None, "level": 1, "stats": []}), None]},
                "b": {"slots": [from_logs._slot({"name": "Spinarai", "level": 1, "stats": []}),
                                from_logs._slot({"name": None, "level": 2, "stats": []})]},
                "problems": ["my slot 1 not named", "opponent slot 2 not named"]}
        from_logs._name_from_stats(case, ["Ironcore", None], ["Puffloon", "Puffloon"])
        self.assertEqual(case["a"]["slots"][0]["name"], "Ironcore")
        self.assertEqual(case["b"]["slots"][0]["name"], "Spinarai")     # a battle name is kept
        self.assertEqual(case["b"]["slots"][1]["name"], "Puffloon")
        self.assertEqual(case["problems"], [])


class BattleBadges(unittest.TestCase):
    """Badges whose digits fill a narrow tile (found 2026-11-13 in the late battles)."""

    def badges(self, name, slot):
        if not (ROOT / "captures" / name).exists():
            self.skipTest(f"captures/{name} not here")
        got = reader.read_stat_badges(pic(name), reader.owned_badge_band(reader.battle_slot(1, slot)))
        return [(b["value"], b["stat"]) for b in got]

    def test_a_shield_between_two_badges_is_not_read_as_damage(self):
        self.assertEqual(self.badges("battles/20261112_134119_start.png", 0),
                         [(52, "damage"), (1128, "shield"), (40, "burn")])

    def test_three_digits_filling_the_tile_are_all_read(self):
        self.assertEqual(self.badges("battles/20261112_134015_start.png", 5), [(550, "shield"), (22, "burn")])

    def test_leading_digits_of_a_four_digit_number_are_kept(self):
        self.assertEqual(self.badges("battles/20261112_144657_start.png", 2), [(2937, "damage"), (9, "poison")])


class WonRunLabel(unittest.TestCase):
    def test_the_last_battle_of_a_won_run_is_a_win(self):
        def log(badges, lives):
            recs = [{"kind": "shop", "state": {"badges": badges, "badges_goal": 10, "lives": lives, "day": 11}},
                    {"kind": "battle", "day": 11, "seen": {"my_team": [], "opponent_team": []}},
                    {"kind": "run_over"}]
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / "run_x.jsonl"
                path.write_text(chr(10).join(json.dumps(r) for r in recs), encoding="utf-8")
                return from_logs.battles_from_log(path)[0]["result"]
        self.assertEqual(log(9, 7), "win")
        self.assertEqual(log(4, 1), "loss")
        self.assertIsNone(log(9, 1))            # one badge short on the last life: either


class ScrolledStatsScreen(unittest.TestCase):
    def test_a_scrolled_stats_window_is_the_stats_screen(self):
        for name in ("battles/20261113_085927_stats_bottom.png", "unread_20261113_201825_127428.png"):
            if (ROOT / "captures" / name).exists():
                self.assertEqual(reader.detect_screen(pic(name)), "stats", name)
