"""Offline tests for the decision engine (no game needed).

    python -m unittest tests.test_engine
"""
import random
import unittest

from engine import data, model, opponents
from engine.choices import pick_trainer, pick_trinket
from engine.evaluate import Evaluator
from engine.model import BENCH, TEAM, Card, RunState, new_unit
from engine.planner import Params, Planner, drag_works, moves_to

FAST = Params(k_final=4, k_quick=3, reroll_samples=1, greedy_steps=1, final_rounds=1)


def card(name, price=None):
    sp = data.species(name)
    return Card(name, sp.cost if price is None else price, "monster", tuple(sorted(sp.stats(1).items())), sp.rarity)


def small_planner():
    return Planner(Evaluator(opponents.pools(n=6, seed=1)), FAST)


class Data(unittest.TestCase):
    def test_roster(self):
        r = data.roster()
        self.assertEqual(len(r), 64)
        self.assertEqual(r["Guardiant"].bug_growth[1], 8)
        self.assertTrue(r["Stingarde"].self_ko)
        self.assertTrue(r["Panbud"].evolves)
        self.assertEqual(r["Velocect"].stats(2)["multicast"], 3)

    def test_run_rules(self):
        self.assertEqual([data.lives_lost(d) for d in (1, 2, 3, 4, 5, 9)], [1, 1, 2, 2, 3, 3])
        self.assertEqual(data.income(1), 30)
        self.assertEqual(data.income(2), 35)
        self.assertEqual(data.hp_for_day(3), 800)


class Model(unittest.TestCase):
    def test_third_copy_merges_and_gives_gift(self):
        s = RunState(money=100, shop=[card("Panbud")] * 3 + [None, None])
        for i in range(3):
            s = model.buy(s, i)
        owned = [u for _, _, u in s.owned()]
        self.assertEqual(len(owned), 1)
        self.assertEqual(owned[0].level, 2)
        self.assertEqual(owned[0].stat("damage"), 50)
        self.assertEqual(s.gifts, ["Common"])
        self.assertEqual(s.money, 70)

    def test_two_level2_make_level3(self):
        s = RunState(money=200, shop=[card("Panbud")] * 5)
        s.team[0] = new_unit("Panbud", 30, level=2)
        for i in range(3):
            s = model.buy(s, i)
        owned = [u for _, _, u in s.owned()]
        self.assertEqual([u.level for u in owned], [3])

    def test_bug_buy_grows_guardiant(self):
        s = RunState(money=100, shop=[card("Velocect"), card("Panbud"), None, None, None])
        s.team[1] = new_unit("Guardiant", 15)
        s = model.buy(s, 0)
        self.assertEqual(s.team[1].stat("damage"), 23)
        s = model.buy(s, 1)                    # Panbud is not a Bug
        self.assertEqual(s.team[1].stat("damage"), 23)

    def test_full_board_only_takes_a_merging_copy(self):
        s = RunState(money=100, shop=[card("Panbud"), card("Velocect"), None, None, None])
        s.team = [new_unit("Mosslug", 10) for _ in range(6)]
        s.bench = [new_unit("Panbud", 10), new_unit("Panbud", 10), new_unit("Pebbler", 15), new_unit("Pebbler", 15)]
        self.assertTrue(model.can_buy(s, 0))
        self.assertFalse(model.can_buy(s, 1))
        t = model.buy(s, 0)
        self.assertEqual(len(t.bench), 4)
        self.assertEqual(sum(1 for u in t.bench if u and u.name == "Panbud" and u.level == 2), 1)

    def test_sell_refunds_half(self):
        s = RunState(money=0)
        s.team[0] = new_unit("Formiqueen", 25)
        self.assertEqual(model.sell(s, TEAM, 0).money, 13)

    def test_from_reader(self):
        state = {"screen": "shop", "day": 3, "lives": 8, "badges": 2, "money": 41, "shop_rank": 3,
                 "trainer": "Rich Lady", "trainer_hp": 800, "locked": False, "reroll_price": 3,
                 "shop_odds": {"Common": 75, "Uncommon": 25, "Rare": 0, "Super Rare": 0, "Legendary": 0},
                 "shop": [{"name": "Panbud", "price": 10, "kind": "monster", "stats": [{"stat": "damage", "value": 25}]},
                          None, None, None, {"name": "Cake", "price": 0, "kind": "item", "stats": []}],
                 "team": [None, None, None, None, None,
                          {"name": "Velocect", "level": 2, "stats": [{"stat": "damage", "value": 20},
                                                                     {"stat": "multicast", "value": 3}]}],
                 "bench": [None] * 4}
        s = model.from_reader(state)
        self.assertEqual(s.team[5].stat("multicast"), 3)
        self.assertEqual(s.shop[4].kind, "item")
        self.assertEqual(s.odds, (75, 25, 0, 0, 0))
        self.assertEqual(s.hp_today, 800)


class Moves(unittest.TestCase):
    def apply(self, team, bench, actions):
        cur = {(TEAM, i): u for i, u in enumerate(team)}
        cur.update({(BENCH, i): u for i, u in enumerate(bench)})
        for a in actions:
            self.assertTrue(drag_works(a.src, a.dst, cur[a.dst] is not None), f"illegal drag {a}")
            cur[a.src], cur[a.dst] = cur[a.dst], cur[a.src]
        return [cur[(TEAM, i)] for i in range(6)]

    def test_same_row_swap_goes_through_an_empty_slot(self):
        a, b = new_unit("Panbud", 10), new_unit("Velocect", 15)
        team0 = [a, b, None, None, None, None]
        team1 = [b, a, None, None, None, None]
        acts = moves_to(team0, [None] * 4, team1, [None] * 4)
        self.assertEqual(self.apply(team0, [None] * 4, acts), team1)

    def test_full_board_rearrangement(self):
        u = [new_unit(n, 10) for n in ("Panbud", "Velocect", "Mosslug", "Pebbler", "Magmite", "Spinarai")]
        bench = [new_unit(n, 10) for n in ("Venopuff", "Joltail", "Dribblet", "Stingarde")]
        target = [u[1], u[0], bench[0], u[4], u[3], u[5]]
        acts = moves_to(u, bench, target, [u[2]] + bench[1:])
        self.assertEqual(self.apply(u, bench, acts), target)


class Planning(unittest.TestCase):
    def test_day1_spends_on_monsters(self):
        p = small_planner()
        s = RunState(day=1, money=30, shop=[card("Panbud"), card("Velocect"), card("Stingarde"), card("Pebbler"), None])
        rng = random.Random(0)
        for _ in range(10):
            plan = p.decide(s)
            a = plan.actions[0]
            if a.kind == "buy":
                s = model.buy(s, a.index)
            elif a.kind == "reroll":
                s = model.reroll(s, rng)
            elif a.kind == "sell":
                s = model.sell(s, *a.src)
            else:
                break
        self.assertGreaterEqual(len(s.owned()), 2)
        self.assertLessEqual(s.money, 10)

    def test_end_of_turn_has_battle_last(self):
        p = small_planner()
        s = RunState(day=2, money=0, shop=[None] * 5)
        s.team[5] = new_unit("Velocect", 15)
        s.bench[0] = new_unit("Panbud", 10)
        plan = p.decide(s)
        self.assertEqual(plan.actions[-1].kind, "battle")

    def test_unknown_monster_is_never_sold(self):
        p = small_planner()
        s = RunState(day=2, money=0, shop=[card("Formiqueen"), None, None, None, None])
        s.team = [model.Unit(None, 1)] + [new_unit("Panbud", 10)] * 5
        s.bench = [model.Unit(None, 1)] * 4
        plan = p.decide(s)
        for a in plan.actions:
            if a.kind == "sell":
                self.assertIsNotNone(s.slot(*a.src).name)


class Choices(unittest.TestCase):
    def test_trainer_avoids_mad_scientist(self):
        k, _ = pick_trainer(["Mad Scientist", "Painter", "Gentleman"])
        self.assertEqual(k, 1)

    def test_trinket_pick_returns_an_index(self):
        p = small_planner()
        s = RunState(day=3)
        s.team[1] = new_unit("Velocect", 15)
        k, why = pick_trinket(p, s, ["Wood Sword", "Gold Nugget", None])
        self.assertIn(k, (0, 1))


class FreeItems(unittest.TestCase):
    def test_free_cake_is_always_used_before_battle(self):
        s = RunState(money=0, shop=[None, None, None, None, Card("Cake", 0, "item", (), "Common")])
        s.team[0] = new_unit("Dribblet", 20)          # no damage badge: the simulator sees no gain
        plan = small_planner().decide(s)
        self.assertEqual([a.kind for a in plan.actions], ["item"])
        self.assertEqual(plan.actions[0].index, 4)


class Explain(unittest.TestCase):
    STATE = {"day": 1, "money": 40, "lives": 10, "badges": 0,
             "team": [{"name": "Brawlmantis"}] + [None] * 5, "bench": [None] * 4}

    def test_choice_is_listed_with_the_options(self):
        from engine.explain import explain
        s = RunState(money=40, shop=[card("Panbud"), card("Velocect"), None, None, None])
        s.team[0] = new_unit("Brawlmantis", 30)
        plan = small_planner().decide(s)
        text = "\n".join(explain(plan, self.STATE))
        self.assertTrue(plan.considered)
        self.assertIn("<-- my choice", text)
        self.assertIn("Decision: " + plan.actions[0].why, text)

    def test_end_of_turn_says_why_it_battles(self):
        from engine.explain import explain
        s = RunState(money=0, shop=[None] * 5)
        s.team[0] = new_unit("Brawlmantis", 30)
        text = "\n".join(explain(small_planner().decide(s), self.STATE))
        self.assertIn("Battle:", text)
        self.assertNotIn("my choice", text)


class Events(unittest.TestCase):
    def state(self):
        s = RunState(money=10, day=3)
        s.team[0] = new_unit("Brawlmantis", 30)
        s.team[1] = new_unit("Velocect", 15)
        return s

    def test_more_money_beats_less_and_unknowns_are_marked(self):
        from engine import events
        sc = events.score_choices(small_planner(), self.state(), ["Gain $20", "Gain $60", "Gain Hero's Sword"])
        self.assertGreater(sc[1].value, sc[0].value)
        self.assertTrue(sc[2].guess)

    def test_recombobulator_is_never_taken(self):
        from engine import events
        k, lines = events.pick(small_planner(), self.state(), [
            "RandomIy transform your monsters 1 rarity higher (max MythicaI rarity)", "Gain $20"])
        self.assertEqual(k, 1)
        self.assertIn("never", "\n".join(lines))

    def test_level_up_is_simulated(self):
        from engine import events
        v, why, guess = events.score_effect(small_planner(), self.state(), "LeveI up a monster (max IeveI 4)")
        self.assertGreater(v, 0)
        self.assertFalse(guess)

    def test_unreadable_choices_fall_back(self):
        from engine import events
        self.assertEqual(events.pick(small_planner(), self.state(), [None, None, None])[0], 2)
        self.assertEqual(events.pick(small_planner(), self.state(), [None, "Gain $40", None])[0], 1)


if __name__ == "__main__":
    unittest.main()


def item(name):
    it = data.items()[name]
    return Card(name, it["cost"], "item", (), it["rarity"])


class ItemsAreModelled(unittest.TestCase):
    """The last live run barely used items: every paid item the planner did not know was skipped."""

    def test_candy_levels_up_a_level_1_monster(self):
        s = RunState(day=8, money=100, shop=[None, None, None, None, item("Basic Candy")])
        s.team[0] = new_unit("Velocect", 15)
        outs = model.item_outcomes(s, 4)
        self.assertEqual(len(outs), 1)
        self.assertEqual(outs[0].team[0].level, 2)
        self.assertEqual(outs[0].money, 70)
        self.assertEqual(outs[0].team[0].stat("multicast"), 3)

    def test_voucher_gives_a_shop_monster_for_free(self):
        s = RunState(day=5, money=10, shop=[card("Velocect"), card("Panbud"), None, None, item("Voucher")])
        outs = model.item_outcomes(s, 4)
        self.assertEqual(len(outs), 2)
        for o in outs:
            self.assertEqual(o.money, 5)               # only the voucher's $5
            self.assertEqual(len(o.owned()), 1)

    def test_apex_bait_ranks_the_shop_up(self):
        s = RunState(day=9, rank=9, money=50, shop=[None, None, None, None, item("Apex Bait")])
        self.assertEqual(model.item_outcomes(s, 4)[0].rank, 10)

    def test_lootbox_and_flyer_add_a_monster(self):
        s = RunState(day=9, money=200, shop=[None, None, None, None, item("Lootbox")])
        for o in model.item_outcomes(s, 4):
            self.assertEqual(len(o.owned()), 1)
            self.assertEqual(o.owned()[0][2].species.rarity, "Legendary")
        s.shop[4] = item("Recruiting Flyer")
        for o in model.item_outcomes(s, 4):
            self.assertEqual(o.owned()[0][2].level, 3)

    def test_shops_roll_an_item_card(self):
        shop = model.random_shop(8, random.Random(4))
        self.assertEqual(shop[4].kind, "item")

    def test_paid_item_is_weighed_and_found_useful(self):
        p = small_planner()
        s = RunState(day=8, rank=8, money=120, shop=[None, None, None, None, item("Basic Candy")])
        s.team = [new_unit("Velocect", 15), new_unit("Stalagrove", 35), new_unit("Spinarai", 10),
                  new_unit("Magmite", 15), new_unit("Pebbler", 15), new_unit("Joltail", 15)]
        plan = p.decide(s)
        gains = dict(plan.considered)
        self.assertIn("use Basic Candy", gains)            # before: paid items the planner did not know were skipped
        self.assertGreater(gains["use Basic Candy"], 0)


class WastefulPlay(unittest.TestCase):
    """What Ed saw in the last Casual run: shuffling, hoarding, dead weight, buy-then-sell."""

    def test_surplus_money_is_spent_on_rerolls(self):
        p = small_planner()
        s = RunState(day=9, rank=9, money=271, shop=[None] * 5)
        s.team = [new_unit("Spinarai", 10)] * 6
        s.lives = 5
        plan = p.decide(s)
        self.assertEqual(plan.actions[0].kind, "reroll")

    def test_surplus_spending_has_an_end(self):
        p = small_planner()
        s = RunState(day=9, rank=9, money=271, shop=[None] * 5, rerolls=p.p.max_rerolls)
        s.team = [new_unit("Spinarai", 10)] * 6
        self.assertEqual(p.decide(s).actions[-1].kind, "battle")

    def test_last_life_keeps_nothing(self):
        p = small_planner()
        self.assertEqual(p.surplus(RunState(day=9, lives=1, money=40)), 40)
        self.assertEqual(p.surplus(RunState(day=9, lives=8, money=40)), 40 - p.p.reserve)

    def test_dead_weight_bench_monsters_are_sold(self):
        p = small_planner()
        s = RunState(day=9, rank=9, money=0, shop=[None] * 5)
        s.team = [new_unit("Thorntail", 35, stats=None), new_unit("Formiqueen", 25), new_unit("Gaiadrasil", 60),
                  new_unit("Noxalith", 30), new_unit("Aster", 40), new_unit("Pylong", 40)]
        s.bench = [new_unit("Bumblebolt", 10), new_unit("Dribblet", 10), None, None]
        team, _ = p.arrange_full(s)
        sold = [u.name for _, _, u in p.dead_weight(s, team)]
        self.assertIn("Bumblebolt", sold)

    def test_a_pair_that_can_merge_is_kept_and_so_is_a_copy_on_sale(self):
        p = small_planner()
        s = RunState(day=9, rank=9, money=0, shop=[card("Bumblebolt"), None, None, None, None])
        s.team = [new_unit("Thorntail", 35), new_unit("Formiqueen", 25), new_unit("Gaiadrasil", 60),
                  new_unit("Noxalith", 30), new_unit("Aster", 40), new_unit("Pylong", 40)]
        s.bench = [new_unit("Bumblebolt", 10), None, None, None]
        team, _ = p.arrange_full(s)
        self.assertEqual(p.dead_weight(s, team), [])         # a third copy is on sale

    def test_eggs_and_new_buys_are_never_dead_weight(self):
        p = small_planner()
        s = RunState(day=9, rank=9, money=0, shop=[None] * 5, bought=["Dribblet"])
        s.team = [new_unit("Thorntail", 35), new_unit("Formiqueen", 25), new_unit("Gaiadrasil", 60),
                  new_unit("Noxalith", 30), new_unit("Aster", 40), new_unit("Pylong", 40)]
        s.bench = [new_unit("Dribblet", 10), new_unit("Dragon Egg", 0) if data.species("Dragon Egg")
                   else model.Unit("Dragon Egg", 1), None, None]
        team, _ = p.arrange_full(s)
        self.assertEqual(p.dead_weight(s, team), [])

    def test_a_monster_bought_today_is_not_sold_today(self):
        p = small_planner()
        s = RunState(day=5, money=30, shop=[card("Velocect"), None, None, None, None], bought=["Panbud"])
        s.team = [new_unit("Panbud", 10)] * 1 + [None] * 5
        for label, actions, _ in p._candidates(s):
            for a in actions:
                if a.kind == "sell":
                    self.assertNotEqual(s.slot(*a.src).name, "Panbud")

    def test_a_settled_layout_is_not_shuffled(self):
        p = small_planner()
        s = RunState(day=6, rank=6, money=0, shop=[None] * 5)
        s.team = [new_unit("Velocect", 15), new_unit("Spinarai", 10), new_unit("Spinarai", 10),
                  new_unit("Magmite", 15), new_unit("Pebbler", 15), new_unit("Mosslug", 10)]
        t1, b1 = p.arrange_full(s)
        s.team, s.bench = list(t1), list(b1)
        p2 = small_planner()
        t2, b2 = p2.arrange_full(s)
        self.assertEqual(moves_to(s.team, s.bench, t2, b2), [])

    def test_brain_remembers_buys_and_rerolls_for_the_day(self):
        from engine.bot import Brain
        b = Brain(Params(), pool_size=4)
        b.memory = {"trinkets": []}
        st = {"day": 3, "shop": [{"name": "Velocect", "kind": "monster", "price": 15}] + [None] * 4}
        b.note_action("buy", st, 0)
        b.note_action("reroll", st)
        self.assertEqual((b.memory["bought"], b.memory["rerolls"]), (["Velocect"], 1))
        s = model.from_reader({**st, "team": [None] * 6, "bench": [None] * 4, "money": 5, "shop_rank": 3},
                              b.memory)
        self.assertEqual((s.bought, s.rerolls), (["Velocect"], 1))
        s2 = model.from_reader({**st, "day": 4, "team": [None] * 6, "bench": [None] * 4, "money": 5}, b.memory)
        self.assertEqual((s2.bought, s2.rerolls), ([], 0))
