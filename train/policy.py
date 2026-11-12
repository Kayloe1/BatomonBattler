"""A fast, learnable shop policy.

The engine (engine/planner.py) decides by playing hundreds of simulated battles per
action, which is too slow to learn from (minutes per run). This policy decides with a
handful of numbers (`Theta`) and costs about a millisecond per action, so the learner
(train/learn.py) can play tens of thousands of simulated runs and tune the numbers.

Per shop turn it:
  1. uses free items;
  2. buys the card with the highest value if the value clears a threshold that grows
     with the day; when team and bench are full it sells the least valuable monster
     if the card is worth clearly more;
  3. rerolls while there is spare money and no card is good enough (with a cap);
  4. then lays the team out (engine.arrange: positional rules, optionally refined
     by a few simulated battles) and fights.

It has no knowledge of the numbers of the September repo: every number here starts as a
neutral guess and is set by the learner.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, fields, asdict
from pathlib import Path

from engine import data, model
from engine.arrange import ADJACENT_BUFFER, ABOVE_TRIGGER, BEHIND_GIVER, IN_FRONT_GIVER, \
    bench_only, heuristic_layout, power
from engine.model import BENCH, TEAM, RunState, Unit
from engine.planner import Action, Plan, TICKETS, moves_to

BEST_FILE = Path(__file__).resolve().parent / "best_policy.json"
AMPS = set(ABOVE_TRIGGER) | IN_FRONT_GIVER | BEHIND_GIVER | ADJACENT_BUFFER


@dataclass
class Theta:
    """Every learnable number. SPEC gives (low, high) for the learner."""
    w_power: float = 1.0          # value per log(1 + power)
    w_rarity: float = 0.0         # per rarity step (Common=0 ... Legendary=4)
    w_pair: float = 1.0           # already own 1 Lv1 copy: progress to a merge
    w_triple: float = 2.0         # already own 2 Lv1 copies: next buy merges
    w_lv2pair: float = 1.5        # own a Lv2 of this species: next merge makes Lv3
    w_bug: float = 0.5            # Bug while owning a Bug-growth monster
    w_amp: float = 0.3            # amplifier pieces
    w_selfko: float = -0.5        # self-knockout monsters
    w_cost: float = -0.1          # per $10 of price
    w_upgrade: float = 1.0        # card power over the weakest fielded monster
    buy_base: float = 3.0         # value a card must reach to be bought ...
    buy_day: float = -0.1         # ... changes by this per day
    swap_margin: float = 1.0      # card must beat the monster it replaces by this
    reroll_reserve: float = 10.0  # money kept after a reroll
    reroll_reserve_day: float = 1.0   # ... plus this per day
    max_rerolls: float = 4.0
    max_rerolls_day: float = 1.0  # ... plus this per day
    w_sim: float = 0.0            # value per +1.0 of expected win share from the simulator (0 = off)
    keep_money: float = 0.0       # money left unspent when buying (saves for tomorrow)


SPEC = {
    "w_power": (0.0, 3.0), "w_rarity": (-1.0, 2.0), "w_pair": (0.0, 4.0), "w_triple": (0.0, 6.0),
    "w_lv2pair": (0.0, 5.0), "w_bug": (-1.0, 2.0), "w_amp": (-1.0, 2.0), "w_selfko": (-3.0, 1.0),
    "w_cost": (-1.0, 0.5), "w_upgrade": (0.0, 3.0), "buy_base": (0.0, 10.0), "buy_day": (-0.6, 0.6),
    "swap_margin": (0.0, 4.0), "reroll_reserve": (0.0, 60.0),
    "reroll_reserve_day": (-3.0, 8.0), "max_rerolls": (0.0, 12.0), "max_rerolls_day": (-1.0, 4.0),
    "keep_money": (0.0, 40.0), "w_sim": (0.0, 30.0),
}
NAMES = [f.name for f in fields(Theta)]


def theta_from_vec(v) -> Theta:
    return Theta(**{n: float(x) for n, x in zip(NAMES, v)})


def vec_from_theta(t: Theta) -> list[float]:
    return [getattr(t, n) for n in NAMES]


def save_theta(t: Theta, path: Path = BEST_FILE, meta: dict | None = None) -> None:
    path.write_text(json.dumps({"theta": asdict(t), "meta": meta or {}}, indent=1), encoding="utf-8")


def load_theta(path: Path = BEST_FILE) -> Theta:
    d = json.loads(path.read_text(encoding="utf-8"))["theta"]
    return Theta(**{k: v for k, v in d.items() if k in NAMES})


def _bug_grower(s: RunState) -> bool:
    return any(u.species and u.species.bug_growth for _, _, u in s.owned())


class FastPolicy:
    def __init__(self, theta: Theta | None = None, layout_scorer=None, evaluator=None, k: int = 5):
        self.t = theta or Theta()
        # layout_scorer(day, trinkets) -> f(team) -> float; None = positional rules only
        self.layout_scorer = layout_scorer
        self.ev, self.k = evaluator, k       # engine.evaluate.Evaluator: marginal-gain feature
        self._cache: dict = {}
        self._turn = None
        self._rerolls = 0

    # ---------------------------------------------------------------- values --
    def _features(self, s: RunState, name: str, u: Unit, price: int, copies_owned: tuple[int, int],
                  weakest: float) -> float:
        t = self.t
        sp = data.species(name)
        pw = power(u)
        lv1, lv2 = copies_owned
        v = t.w_power * math.log1p(pw / 10.0)
        v += t.w_rarity * data.RARITIES.index(sp.rarity)
        v += t.w_cost * price / 10.0
        v += t.w_pair * (lv1 == 1) + t.w_triple * (lv1 >= 2) + t.w_lv2pair * (lv2 >= 1)
        if sp.is_bug and _bug_grower(s):
            v += t.w_bug
        if name in AMPS:
            v += t.w_amp
        if sp.self_ko:
            v += t.w_selfko
        v += t.w_upgrade * max(0.0, math.log1p(pw / 10.0) - math.log1p(weakest / 10.0))
        return v

    def _weakest_fielded(self, s: RunState) -> float:
        field = [power(u) for u in s.team if u is not None and not bench_only(u)]
        if len([u for u in s.team if u is not None]) < data.TEAM_SLOTS:
            return 0.0
        return min(field) if field else 0.0

    def card_value(self, s: RunState, c: model.Card, weakest: float) -> float:
        if bench_only(model.Unit(c.name)) or data.species(c.name) is None:
            return -99.0
        u = model.new_unit(c.name, c.price, 1, dict(c.stats) or None)
        owned = [o for _, _, o in s.owned() if o.name == c.name]
        lv1 = sum(o.level == 1 for o in owned)
        lv2 = sum(o.level == 2 for o in owned)
        v = self._features(s, c.name, u, c.price, (lv1, lv2), weakest)
        if self.ev is not None and self.t.w_sim:
            v += self.t.w_sim * self._gain(s, c)
        return v

    def _board(self, s: RunState) -> float:
        owned = [u for _, _, u in s.owned()]
        if not owned or any(u.name is None for u in owned):
            return 0.0
        team, _ = heuristic_layout(owned)
        a = self.ev.score(team, s.day, self.k, trainer=s.trainer, trinkets=s.trinkets).value
        b = self.ev.score(team, s.day + 1, self.k, trainer=s.trainer, trinkets=s.trinkets).value
        return 0.6 * a + 0.4 * b

    def _gain(self, s: RunState, c: model.Card) -> float:
        """Expected win-share gain from buying this card (simulator, shared opponents)."""
        key = (s.day, tuple(sorted(map(repr, s.owned()))))
        base = self._cache.get(key)
        if base is None:
            base = self._cache[key] = self._board(s)
        i = next((j for j, x in enumerate(s.shop) if x is c), None)
        if i is None or not model.can_buy(s, i):
            return 0.0
        return self._board(model.buy(s, i)) - base

    def unit_value(self, s: RunState, u: Unit) -> float:
        owned = [o for _, _, o in s.owned() if o.name == u.name and o is not u]
        lv1 = sum(o.level == 1 for o in owned)
        lv2 = sum(o.level == 2 for o in owned)
        # a unit is worth what a card like it would be worth, with its levels counted as copies
        base = self._features(s, u.name, u, 0, (lv1, lv2), 0.0)
        return base + 0.6 * (u.level - 1)

    # --------------------------------------------------------------- decide --
    def _bounds(self, day: int) -> tuple[float, float, int]:
        t = self.t
        thresh = t.buy_base + t.buy_day * day
        reserve = t.reroll_reserve + t.reroll_reserve_day * day
        cap = int(max(0, round(t.max_rerolls + t.max_rerolls_day * day)))
        return thresh, reserve, cap

    def next_action(self, s: RunState) -> Action | None:
        """One shop action, or None to end the turn."""
        key = (s.day, s.badges, s.lives)
        if self._turn != key:
            self._turn, self._rerolls = key, 0
        t = self.t
        thresh, reserve, cap = self._bounds(s.day)
        # free items first
        for i, c in enumerate(s.shop):
            if c and c.kind == "item" and c.name not in TICKETS and c.price == 0 \
                    and s.items_left > 0 and model.item_is_worth_using(s, c):
                return Action("item", i, why=f"use {c.name}")
        weakest = self._weakest_fielded(s)
        best = None
        for i, c in enumerate(s.shop):
            if c is None or c.kind != "monster" or c.name is None or c.price > s.money - t.keep_money:
                continue
            v = self.card_value(s, c, weakest)
            if v < thresh:
                continue
            if model.can_buy(s, i):
                if best is None or v > best[0]:
                    best = (v, i, None)
                continue
            # full: sell the least valuable monster if the card is clearly better
            owned = [(self.unit_value(s, u), w, k, u) for w, k, u in s.owned() if u.name is not None]
            if not owned:
                continue
            uv, w, k, u = min(owned, key=lambda x: x[0])
            if v > uv + t.swap_margin and u.sell_price() + s.money >= c.price + t.keep_money:
                if best is None or v > best[0]:
                    best = (v, i, (w, k))
        if best is not None:
            v, i, sell = best
            if sell is not None:
                return Action("sell", src=sell, why="sell to make room")
            return Action("buy", i, why=f"buy {s.shop[i].name} (value {v:.1f})")
        if self._rerolls < cap and s.money - s.reroll_price >= reserve:
            return Action("reroll", why="reroll")
        return None

    def decide(self, s: RunState) -> Plan:
        """Same interface as engine.planner.Planner.decide: the next action(s)."""
        a = self.next_action(s)
        if a is not None:
            if a.kind == "reroll":
                self._rerolls += 1
            return Plan([a], 0.0)
        team, bench = self.final_layout(s)
        actions = moves_to(s.team, s.bench, team, bench)
        actions.append(Action("battle", why="policy: done shopping"))
        return Plan(actions, 0.0)

    def final_layout(self, s: RunState):
        owned = [u for _, _, u in s.owned()]
        if any(u.name is None for u in owned):       # unreadable monster: leave it where it is
            return list(s.team), list(s.bench)
        team, rest = heuristic_layout(owned)
        if self.layout_scorer is not None:
            from engine.arrange import improve
            f = self.layout_scorer(s.day, s.trinkets)
            bench0 = (rest + [None] * data.BENCH_SLOTS)[:data.BENCH_SLOTS]
            team, bench, _ = improve(team, bench0, f, max_rounds=2)
            return team, bench
        return team, (rest + [None] * data.BENCH_SLOTS)[:data.BENCH_SLOTS]

    # ------------------------------------------------------ offline shop turn --
    def play_shop(self, s: RunState, rng: random.Random) -> RunState:
        for _ in range(60):
            a = self.next_action(s)
            if a is None:
                break
            if a.kind == "buy":
                s = model.buy(s, a.index)
            elif a.kind == "item":
                s = model.use_item(s, a.index)
            elif a.kind == "sell":
                s = model.sell(s, *a.src)
            elif a.kind == "reroll":
                self._rerolls += 1
                s = model.reroll(s, rng)
        team, bench = self.final_layout(s)
        s.team, s.bench = list(team), list(bench)
        return s
