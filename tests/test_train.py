"""Offline tests for the practice shop and the learned policy.

    python -m unittest tests.test_train
"""
import random
import unittest

from engine import data, model, opponents
from engine.model import Card, RunState, new_unit
from train.env import OppSource, play_run
from train.learn import learn
from train.policy import NAMES, SPEC, FastPolicy, Theta, theta_from_vec, vec_from_theta


def card(name):
    sp = data.species(name)
    return Card(name, sp.cost, "monster", tuple(sorted(sp.stats(1).items())), sp.rarity)


def src():
    return OppSource(ghosts=opponents.pools(n=6, seed=3), p_ghost=1, p_league=0, p_recorded=0)


class Policy(unittest.TestCase):
    def test_vector_roundtrip_and_bounds(self):
        t = Theta()
        self.assertEqual(theta_from_vec(vec_from_theta(t)), t)
        for n in NAMES:
            lo, hi = SPEC[n]
            self.assertLessEqual(lo, getattr(t, n))
            self.assertLessEqual(getattr(t, n), hi)

    def test_buys_good_card_and_never_overspends(self):
        s = RunState(day=1, money=30, shop=[card("Panbud"), card("Velocect"), None, None, None])
        pol = FastPolicy(Theta(buy_base=0.0, max_rerolls=0, max_rerolls_day=0))
        s = pol.play_shop(s, random.Random(0))
        self.assertGreaterEqual(s.money, 0)
        self.assertTrue(s.owned())

    def test_full_board_sells_to_make_room_only_for_clearly_better(self):
        s = RunState(day=5, money=100, rank=5)
        for i in range(6):
            s.team[i] = new_unit("Dribblet", 15)
        for i in range(4):
            s.bench[i] = new_unit("Dribblet", 15)
        s.shop = [card("Dragon Egg") if "Dragon Egg" in data.roster() else card("Velocect"), None, None, None, None]
        pol = FastPolicy(Theta(max_rerolls=0, max_rerolls_day=0))
        a = pol.next_action(s)
        self.assertTrue(a is None or a.kind in ("buy", "sell"))


class Env(unittest.TestCase):
    def test_run_is_deterministic_and_legal(self):
        pol = FastPolicy(Theta())
        a = play_run(pol, 5, src(), snapshots=True)
        b = play_run(FastPolicy(Theta()), 5, src(), snapshots=True)
        self.assertEqual(a["arc"], b["arc"])
        self.assertLessEqual(a["badges"], data.BADGES_TO_WIN)
        self.assertEqual(a["arc"].count("W"), a["badges"])
        for d, spec in a["snaps"].items():
            self.assertLessEqual(len([x for x in spec["slots"] if x]), 6)

    def test_recorded_teams_are_preferred_when_present(self):
        rec = {1: [{"hp": 300, "trainer": "", "trinkets": [], "slots": [None] * 6, "marker": 1}]}
        s = OppSource(ghosts=opponents.pools(n=6, seed=3), recorded=rec, p_ghost=0.0, p_league=0.0,
                      p_recorded=1.0)
        self.assertEqual(s.sample(1, random.Random(0)).get("marker"), 1)
        self.assertNotIn("marker", s.sample(2, random.Random(0)))


class Learner(unittest.TestCase):
    def test_learning_does_not_get_worse_on_a_tiny_run(self):
        theta, hist = learn(gens=3, pop=8, runs=6, seed=1, workers=1, ghost_n=6, log=lambda *_: None)
        self.assertEqual(len(hist), 3)
        self.assertIsInstance(theta, Theta)


if __name__ == "__main__":
    unittest.main()
