"""Tests for the battle simulator (sim/). No game, captures or extra packages needed."""
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sim import data  # noqa: E402
from sim.battle import Battle, simulate, team_from_reader, win_rate  # noqa: E402
from sim.check import check_case, load_cases  # noqa: E402
from sim.__main__ import main  # noqa: E402


def team(slots, hp=1000, **kw):
    slots = list(slots) + [None] * (6 - len(slots))
    return {"hp": hp, "slots": slots, **kw}


def mon(name, level=1, **stats):
    out = {"name": name, "level": level}
    if stats:
        out["stats"] = stats
    return out


EMPTY = team([])


class Data(unittest.TestCase):
    def test_all_pantra_species_load(self):
        sp = data.load_species()
        self.assertEqual(len([n for n in sp if n not in data.EXTRA_UNITS]), 64)
        for s in sp.values():
            for lv in (1, 2, 3, 4):
                self.assertGreater(s.levels[lv].cooldown, 0, s.name)

    def test_level_numbers(self):
        self.assertEqual(data.species("Brawlmantis").levels[2].stats["damage"], 100)
        self.assertEqual(data.species("Velocect").levels[1].multicast, 2)
        self.assertEqual(data.species("Velocect").levels[4].multicast, 8)
        self.assertEqual(data.species("Cherubble").levels[2].cooldown, 2.0)
        self.assertEqual([data.species("Dracana").levels[n].param for n in (1, 2, 3, 4)], [1, 2, 3, 18])
        self.assertEqual([data.species("Lignite").levels[n].param for n in (1, 2)], [24, 48])
        self.assertEqual(data.species("Draconarch").levels[1].param, 6)
        self.assertEqual(data.species("Draconarch").levels[2].param, 3)
        self.assertEqual(data.species("Shelldra").levels[3].param, 3)
        self.assertEqual(data.species("Shelldra").levels[3].stats["damage"], 15)

    def test_evolved_forms(self):
        bambudo = data.species("Bambudo")
        self.assertEqual(bambudo.levels[3].stats["damage"], 75)
        self.assertEqual(bambudo.levels[3].param, 35)
        self.assertEqual(data.species("Dribblet").levels[3].param, 60)
        self.assertEqual(data.species("Scorchimp").levels[4].param, 20)


class Positions(unittest.TestCase):
    def setUp(self):
        names = ["Panbud", "Spinarai", "Velocect", "Mosslug", "Dribblet", "Pebbler"]
        self.b = Battle(team([mon(n) for n in names]), EMPTY)
        self.t = self.b.teams[0]

    def test_behind_front_above(self):
        self.assertIs(self.b.behind(self.t[1]), self.t[0])
        self.assertIs(self.b.in_front(self.t[1]), self.t[2])
        self.assertIsNone(self.b.behind(self.t[3]))
        self.assertIs(self.b.above(self.t[4]), self.t[1])
        self.assertIsNone(self.b.above(self.t[1]))

    def test_adjacent_is_orthogonal(self):
        self.assertEqual({u.slot for u in self.b.adjacent(self.t[0])}, {1, 3})
        self.assertEqual({u.slot for u in self.b.adjacent(self.t[4])}, {1, 3, 5})


class Mechanics(unittest.TestCase):
    def test_first_cast_after_full_cooldown(self):
        r = simulate(team([mon("Panbud")]), EMPTY, until=4.99)
        self.assertEqual(r.units[0][0]["triggered"], 0)
        r = simulate(team([mon("Panbud")]), EMPTY, until=5.0)
        self.assertEqual(r.units[0][0]["triggered"], 1)
        self.assertEqual(r.hp[1], 1000 - 25)

    def test_poison_ticks_every_second_and_stays(self):
        r = simulate(team([mon("Venopuff")]), EMPTY, until=6.0)
        # Poison 4 at 3.5 s; ticks at 4, 5, 6.
        self.assertEqual(r.statuses[1]["poison"], 4)
        self.assertEqual(r.hp[1], 1000 - 12)

    def test_burn_ticks_twice_a_second_and_decays(self):
        # Checks the code against an UNVERIFIED rule from the September notes (see sim/rules.py).
        r = simulate(team([mon("Pyronade")]), EMPTY, until=6.0)
        # Burn 20 at 4.5 s; ticks at 4.5 (right after the cast), 5.0, 5.5, 6.0 deal 20, 19, 18, 17.
        self.assertEqual(r.hp[1], 1000 - 74)
        self.assertEqual(r.statuses[1]["burn"], 16)

    def test_shock_adds_flat_damage_to_hits(self):
        r = simulate(team([mon("Electranade"), mon("Panbud")]), EMPTY, until=5.0)
        self.assertEqual(r.hp[1], 1000 - (25 + 25))
        self.assertEqual(r.statuses[1]["shock"], 25)

    def test_shield_blocks_damage_and_status_is_reduced(self):
        # The 15% status reduction is an UNVERIFIED number from the September notes.
        # Both cast at 5 s, player first: Shield 20, then the 25 hit takes it and 5 HP.
        r = simulate(team([mon("Pebbler")]), team([mon("Panbud")]), until=5.0)
        self.assertEqual(r.hp[0], 995)
        # Poison 4 from 3.5 s. Tick at 4 s hits HP (4); Shield 20 at 5 s; ticks at 5 and 6 s
        # do 4 x 0.85 = 3.4 each into the shield.
        r = simulate(team([mon("Pebbler")]), team([mon("Venopuff")]), until=6.0)
        self.assertEqual(r.hp[0], 996)
        self.assertEqual(r.statuses[0]["shield"], round(20 - 6.8))

    def test_heal_is_capped(self):
        r = simulate(team([mon("Dribblet")]), EMPTY, until=10)
        self.assertEqual(r.hp[0], 1000)

    def test_self_knockout(self):
        r = simulate(team([mon("Stingarde")]), EMPTY, until=20)
        self.assertEqual(r.units[0][0]["triggered"], 1)
        self.assertTrue(r.units[0][0]["knocked_out"])

    def test_cherubble_protect_blocks_self_knockout(self):
        # Cherubble (4 s) protects its neighbour before Stingarde (6 s) casts.
        r = simulate(team([mon("Cherubble"), mon("Stingarde")]), EMPTY, until=13)
        self.assertEqual(r.units[0][1]["triggered"], 2)

    def test_cicadence_triggers_bug_above(self):
        r = simulate(team([mon("Panbud"), mon("Velocect"), None, None, mon("Cicadence")]), EMPTY,
                     until=6.0)
        velocect = r.units[0][1]
        # Velocect casts at 3.5 (x2) and again when Cicadence casts at 6.0 (x2): two casts, four hits.
        # "triggered" counts casts, as the game's Stats screen does (seen 2026-11-12).
        self.assertEqual(velocect["triggered"], 2)
        self.assertEqual(velocect["dealt"], 60)

    def test_dracana_charges_ally_behind(self):
        r = simulate(team([mon("Stingarde"), mon("Dracana")]), EMPTY, until=5.0)
        # Dracana casts at 3 s and charges Stingarde 1 s: Stingarde casts at 5 s, not 6 s.
        self.assertEqual(r.units[0][0]["triggered"], 1)

    def test_formiqueen_speeds_adjacent_common(self):
        r = simulate(team([mon("Panbud"), mon("Formiqueen")]), EMPTY, until=4.0)
        self.assertEqual(r.units[0][0]["triggered"], 1)    # 5 s / 1.25 = 4 s

    def test_multicast_hits_twice_but_triggers_once(self):
        # Stats screen 2026-11-12: Velocect (15 x2) "Triggered 4 time(s)", "Dealt 144" with Shock on us.
        r = simulate(team([mon("Velocect")]), EMPTY, until=3.5)
        self.assertEqual(r.units[0][0]["triggered"], 1)
        self.assertEqual(r.hp[1], 1000 - 30)

    def test_badges_replace_base_numbers(self):
        r = simulate(team([mon("Brawlmantis", damage=60)]), EMPTY, until=5.5)
        self.assertEqual(r.hp[1], 1000 - 60)

    def test_winner_and_draw(self):
        r = simulate(team([mon("Stingarde")], hp=100), team([], hp=100))
        self.assertEqual(r.winner, "a")
        # Same instant: every cast of both sides resolves before deaths are checked (the opponent's
        # Craghorn still cast at the 18 s instant our casts won at, 2026-11-12), so both die: draw.
        r = simulate(team([mon("Stingarde")], hp=100), team([mon("Stingarde")], hp=100))
        self.assertEqual(r.winner, "draw")
        # Both die to the same Poison tick: draw.
        r = simulate(team([mon("Venopuff")], hp=4), team([mon("Venopuff")], hp=4))
        self.assertEqual(r.winner, "draw")
        r = simulate(team([mon("Dribblet")]), team([mon("Dribblet")]))
        self.assertEqual(r.winner, "draw")    # nobody can win: time limit

    def test_day_hp_table(self):
        r = simulate({"day": 3, "slots": []}, EMPTY, until=1)
        self.assertEqual(r.max_hp[0], 800)


class RecordedBattles(unittest.TestCase):
    def setUp(self):
        self.cases = dict(load_cases())

    def _rows(self, name):
        case = self.cases[name]
        known = case["expect"].get("known_gaps", {})
        rows = check_case(case)
        verified = [r for r in rows if not any(r[0] == k or r[0].endswith(k) for k in known)]
        return rows, verified

    def test_day2_reproduced_exactly(self):
        rows, _ = self._rows("day2_rich_lady_win")
        bad = [r for r in rows if not r[3]]
        self.assertEqual(bad, [])

    def test_day3_verified_parts(self):
        _, verified = self._rows("day3_rich_lady_loss")
        bad = [r for r in verified if not r[3]]
        self.assertEqual(bad, [])
        self.assertGreaterEqual(len(verified), 10)

    @unittest.expectedFailure
    def test_day3_outcome_known_gap(self):
        """Known gap: the simulator does not yet kill Ed by 15 s (see the case's known_gaps)."""
        r = simulate(self.cases["day3_rich_lady_loss"]["a"], self.cases["day3_rich_lady_loss"]["b"])
        self.assertEqual(r.winner, "b")

    def test_check_command_passes(self):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--check"]), 0)


class Robustness(unittest.TestCase):
    def test_every_species_and_level_runs(self):
        names = [n for n in data.load_species()]
        rng = random.Random(1)
        for i in range(150):
            def rand_team():
                return team([mon(rng.choice(names), rng.randint(1, 4)) if rng.random() < 0.85 else None
                             for _ in range(6)], hp=rng.choice([300, 2400, 47300]),
                            trinkets=rng.sample(["Rally Flag", "Warhorn", "Link Cable", "Metronome",
                                                 "Repeater Charm", "Topaz Amulet", "Momentum Flag",
                                                 "Tempo Charm", "Haste Orb", "Razor Beak"], 3))
            r = simulate(rand_team(), rand_team(), seed=i)
            self.assertIn(r.winner, ("a", "b", "draw"))

    def test_self_accelerating_team_finishes(self):
        # Galvanine Lv4 gains +50% Cooldown Speed per cast; without the min_cooldown floor this
        # battle never ended.
        a = team([None, mon("Pebbler", 4), mon("Guardiant"), mon("Geminiss", 4), mon("Aegistruct"),
                  mon("Craghorn", 2)], hp=800, trinkets=["Razor Beak", "Warhorn", "Repeater Charm"])
        b = team([mon("Noxalith", 2), mon("Galvanine", 4), mon("Noxnimbus", 3), mon("Dirgefin", 4),
                  None, mon("Dryadell", 4)], hp=8300, trinkets=["Razor Beak", "Metronome", "Repeater Charm"])
        r = simulate(a, b)
        self.assertIn(r.winner, ("a", "b", "draw"))

    def test_speed_cache_follows_buffs(self):
        # Boomagon speeds up the ally behind it on each cast; the cached speed must follow.
        r = simulate(team([mon("Panbud"), mon("Boomagon", 4)]), EMPTY, until=60)
        r0 = simulate(team([mon("Panbud")]), EMPTY, until=60)
        self.assertGreater(r.units[0][0]["triggered"], r0.units[0][0]["triggered"])

    def test_same_seed_same_result(self):
        a = team([mon("Reapra", 4), mon("Panbud")], trinkets=["Tempo Charm"])
        b = team([mon("Velocect"), mon("Panbud"), mon("Spinarai")], trinkets=["Tempo Charm"])
        self.assertEqual(simulate(a, b, seed=3).as_dict(), simulate(a, b, seed=3).as_dict())

    def test_win_rate(self):
        strong = team([mon("Stingarde", 2)], hp=300)
        weak = team([mon("Dribblet")], hp=300)
        self.assertEqual(win_rate(strong, [weak, weak]), 1.0)

    def test_team_from_reader(self):
        state = {"trainer": "Rich Lady", "trainer_hp": 500, "team": [
            {"name": "Brawlmantis", "level": 1, "stats": [{"value": 60, "stat": "damage"}]},
            None,
            {"name": "Velocect", "level": 2, "stats": [{"value": 20, "stat": "damage"},
                                                      {"value": 3, "stat": "multicast"}]},
            {"name": None, "level": 1, "stats": []}, None, None]}
        t = team_from_reader(state)
        self.assertEqual(t["hp"], 500)
        self.assertEqual(t["slots"][0]["stats"], {"damage": 60})
        self.assertEqual(t["slots"][2]["multicast"], 3)
        self.assertIsNone(t["slots"][3])
        simulate(t, EMPTY, until=5)


if __name__ == "__main__":
    unittest.main()


class FromLogs(unittest.TestCase):
    """A logged battle (as play.py writes it) becomes a simulator case."""

    def _log(self, tmp, records):
        import json
        p = Path(tmp) / "run_test.jsonl"
        p.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
        return p

    def test_day2_read_from_the_battle_screen_matches_the_hand_made_case(self):
        import json
        import tempfile
        from sim import from_logs
        seen = json.loads((Path(__file__).parent / "fixtures" / "battle_day2_seen.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path = self._log(tmp, [
                {"kind": "trainer", "ok": True},
                {"kind": "trinket", "ok": True, "offered": ["Rally Flag", "Wood Sword"], "picked": 1},
                {"kind": "battle", "time": "t", "day": 2, "trainer": "Rich Lady", "trainer_hp": 500, "seen": seen},
                {"kind": "day_result", "day": 2, "badges": 1, "lives": 0},
            ])
            cases = from_logs.battles_from_log(path)
        self.assertEqual(len(cases), 1)
        c = cases[0]
        self.assertEqual((c["result"], c["problems"], c["a"]["trinkets"]), ("win", [], ["Wood Sword"]))
        hand = json.loads((ROOT / "sim" / "cases" / "day2_rich_lady_win.json").read_text())
        self.assertEqual(c["a"]["slots"], hand["a"]["slots"])
        self.assertEqual(c["b"]["slots"], hand["b"]["slots"])
        c["a"]["trinkets"] = []
        res = from_logs.check([c], seeds=1)
        self.assertEqual((res["usable"], res["agree"]), (1, 1))

    def test_unnamed_opponent_is_skipped_not_guessed(self):
        import tempfile
        from sim import from_logs
        seen = {"my_team": [{"name": "Mosslug", "level": 1, "stats": []}] + [None] * 5,
                "opponent_team": [{"name": None, "level": 2, "stats": [{"stat": "damage", "value": 40}]}] + [None] * 5,
                "problems": []}
        with tempfile.TemporaryDirectory() as tmp:
            path = self._log(tmp, [{"kind": "battle", "day": 1, "seen": seen},
                                   {"kind": "day_result", "badges": 0, "lives": -1}])
            cases = from_logs.battles_from_log(path)
        self.assertEqual(cases[0]["result"], "loss")
        self.assertIn("opponent slot 1 not named", cases[0]["problems"])
        self.assertEqual(from_logs.check(cases)["skipped"], 1)
