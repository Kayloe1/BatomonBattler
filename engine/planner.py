"""The shop-turn decision: what to buy, sell, use, reroll or lock, and where everyone stands.

The planner is called again after every action (the game refills cards, merges,
rolls random items), so it only has to pick the best NEXT action:

1. Value the board as it is (after the best arrangement) with `value()`.
2. Try every candidate: use an item, buy a card (and try it in each slot), sell a
   monster, sell-then-buy when money or space is short, buy-then-sell a Bug to
   grow Guardiant (the fodder loop), and reroll (expected value over sampled shops).
3. Take the candidate with the highest value if it beats ending the turn.
4. When nothing beats ending the turn: maybe LOCK (a card worth saving for), then
   the final arrangement (a full swap search) and BATTLE!

value(state) = W_TODAY x score vs today's opponent pool
             + W_NEXT  x score vs tomorrow's pool (does the board keep up?)
             + money and sell value of bench monsters x MONEY
             + trinket gifts earned + progress toward merges.
The weights live in `Params` and were tuned by playing whole runs offline
(engine/runsim.py); see docs/decision-engine.md.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace

import knowledge

from . import data, model
from .arrange import heuristic_layout, improve, power
from .evaluate import Evaluator, team_key
from .model import BENCH, TEAM, RunState, Unit

GIFT_VALUE = {"Common": 0.025, "Uncommon": 0.035, "Rare": 0.05, "Super Rare": 0.07, "Legendary": 0.09}
# Free items that can only help: used at the end of the turn when nothing else was worth doing, so the
# simulator's small estimate of their value can never leave a free Cake sitting in the shop.
FREE_BUFFS = {"Cake", "Feast", "Pom Berry", "Gray Chip"}
TICKETS = {"Gray Ticket", "Green Ticket", "Blue Ticket", "Purple Ticket", "Golden Ticket"}


@dataclass
class Params:
    k_final: int = 16          # opponents when reporting a board's score
    k_quick: int = 10          # opponents inside the search (same ones for every candidate)
    w_today: float = 1.0
    w_next: float = 0.6
    w_next2: float = 0.3       # the day after tomorrow: keeps the board growing when today looks safe
    money: float = 0.003       # value of $1 carried to tomorrow ...
    money_cap: int = 40        # ... up to this much; more saved money buys nothing extra
    bench_money: float = 0.8   # share of the monsters' sell value counted as money
    copy_progress: float = 0.04
    power_weight: float = 0.05   # tie-breaker: a stronger fielded team is better even when the simulator's
                                 # score is flat (late days, where every purchase looks equally hopeless)
    swap_gain: float = 0.004     # a layout change must beat the current layout by this much (no shuffling)
    reserve: int = 20            # money worth keeping; anything above it is spent (rerolls hunt for merges)
    max_rerolls: int = 25        # surplus rerolls per day
    gift_scale: float = 1.0
    reroll_samples: int = 3
    lock_gain: float = 0.06
    min_gain: float = 0.0     # an action must beat ending the turn by this much
    greedy_steps: int = 3      # buys looked ahead after each candidate
    screen: int = 2            # cards tried per greedy step (best by a quick estimate)
    final_rounds: int = 3
    margin_weight: float = 0.3   # how much "closer battles" count next to battles won


@dataclass
class Action:
    kind: str                  # item, buy, sell, reroll, lock, move, battle
    index: int | None = None   # shop card for item/buy
    src: tuple[str, int] | None = None
    dst: tuple[str, int] | None = None
    why: str = ""
    value: float = 0.0

    def __str__(self) -> str:
        if self.kind in ("buy", "item"):
            return f"{self.kind} card {self.index}"
        if self.kind == "sell":
            return f"sell {self.src}"
        if self.kind == "move":
            return f"move {self.src} -> {self.dst}"
        return self.kind


@dataclass
class Plan:
    actions: list[Action]
    value: float
    notes: list[str] = field(default_factory=list)
    # for explaining the choice (engine/explain.py): every option weighed as (label, gain over
    # ending the turn now), best first, and the chance to win today's battle with the team as it is
    considered: list[tuple[str, float]] = field(default_factory=list)
    win_now: float | None = None


def stake_weight(s: RunState) -> float:
    """Today's battle matters more when a loss could end the run."""
    w = 1.0
    lose = data.lives_lost(s.day)
    if s.lives <= lose:
        w *= 1.6 if s.rescue_used else 1.25
    if s.badges >= data.BADGES_TO_WIN - 1:
        w *= 1.3
    return w


class Planner:
    def __init__(self, evaluator: Evaluator, params: Params | None = None, seed: int = 0):
        self.ev = evaluator
        self.p = params or Params()
        self.ev.margin_weight = self.p.margin_weight
        self.rng = random.Random(seed)
        self._arranged: dict[tuple, tuple[list, list]] = {}

    # ------------------------------------------------------------ scoring ----
    def _hp(self, s: RunState, day: int) -> int:
        if s.hp_today:                        # what the screen shows beats the table
            return int(s.hp_today * data.hp_for_day(day) / data.hp_for_day(s.day))
        hp = data.hp_for_day(day)
        # after the last-life rescue the trainer's HP was 25% higher (two runs)
        return int(hp * 1.25) if s.rescue_used else hp

    def team_score(self, s: RunState, team: list[Unit | None], k: int) -> float:
        today = self.ev.score(team, s.day, k, hp=self._hp(s, s.day), trainer=s.trainer, trinkets=s.trinkets)
        if self.p.w_next == 0:
            return self.p.w_today * stake_weight(s) * today.value
        nxt = self.ev.score(team, s.day + 1, k, hp=self._hp(s, s.day + 1), trainer=s.trainer,
                            trinkets=s.trinkets)
        v = self.p.w_today * stake_weight(s) * today.value + self.p.w_next * nxt.value
        if self.p.w_next2:
            nxt2 = self.ev.score(team, s.day + 2, k, hp=self._hp(s, s.day + 2), trainer=s.trainer,
                                 trinkets=s.trinkets)
            v += self.p.w_next2 * nxt2.value
        return v

    def win_today(self, s: RunState, team: list[Unit | None], k: int | None = None) -> float:
        return self.ev.score(team, s.day, k or self.p.k_final, hp=self._hp(s, s.day), trainer=s.trainer,
                             trinkets=s.trinkets).win

    def extras(self, s: RunState, bench: list[Unit | None]) -> float:
        # money and what the monsters would sell for, counted up to a cap: beyond it,
        # saved money buys nothing that today's spending could not
        resale = sum(u.sell_price() for _, _, u in s.owned())
        v = self.p.money * min(s.money + self.p.bench_money * resale, self.p.money_cap)
        v += self.p.gift_scale * sum(GIFT_VALUE.get(r, 0.03) for r in s.gifts)
        counts: dict[str, int] = {}
        for _, _, u in s.owned():
            if u.level == 1 and u.name:
                counts[u.name] = counts.get(u.name, 0) + 1
        for name, c in counts.items():
            if c >= 2:
                sp = data.species(name)
                v += self.p.copy_progress * (1 + data.RARITIES.index(sp.rarity) if sp else 1)
        return v

    def quick(self, s: RunState, team, bench) -> float:
        v = self.team_score(s, team, self.p.k_quick) + self.extras(s, bench)
        if self.p.power_weight:
            v += self.p.power_weight * math.log1p(sum(power(u) for u in team if u is not None))
        return v

    # -------------------------------------------------------- arrangement ----
    def arrange_full(self, s: RunState, hint=None) -> tuple[list, list]:
        """Full swap search (used for the board as it is and before BATTLE!)."""
        owned = [u for _, _, u in s.owned()]
        key = (tuple(sorted((team_key([u])[0] for u in owned), key=repr)), s.day, s.rescue_used,
               tuple(s.trinkets))
        if key in self._arranged:
            return self._arranged[key]
        cands = [(list(s.team), list(s.bench))]
        if hint is not None:
            cands.append((list(hint[0]), list(hint[1])))
        if all(u.name for u in owned):
            ht, hr = heuristic_layout(owned)
            cands.append((list(ht), (hr + [None] * 4)[:4]))
        cands = [c for c in cands if _same_units(c, owned)] or cands[:1]
        f = lambda t: self.team_score(s, t, self.p.k_quick)
        best, best_v = cands[0], f(cands[0][0])          # the layout as it is wins unless clearly beaten
        for c in cands[1:]:
            v = f(c[0])
            if v > best_v + self.p.swap_gain:
                best, best_v = c, v
        team, bench, _ = improve(best[0], best[1], f, max_rounds=self.p.final_rounds, min_gain=self.p.swap_gain)
        self._arranged[key] = (team, bench)
        return team, bench

    def place(self, s: RunState, team: list, bench: list) -> tuple[list, list]:
        """Cheap placement after one buy or sale: keep the arrangement, but try the
        changed monster in each team slot and refill an emptied team slot from the bench."""
        owned = [u for _, _, u in s.owned()]
        left = list(owned)

        def keep(u):
            if u is not None and u in left:
                left.remove(u)
                return u
            return None
        team = [keep(u) for u in team]
        bench = [keep(u) for u in bench]
        fresh = []
        for u in left:                      # new or merged monsters start on the bench
            free = [i for i, x in enumerate(bench) if x is None]
            if free:
                bench[free[0]] = u
                fresh.append(free[0])
            else:
                bench.append(u)
                fresh.append(len(bench) - 1)
        f = lambda t: self.ev.score(t, s.day, self.p.k_quick, hp=self._hp(s, s.day), trainer=s.trainer,
                                    trinkets=s.trinkets).value
        best_t, best_b, best_v = team, bench, f(team)
        others = sorted((i for i, u in enumerate(bench) if u is not None and i not in fresh),
                        key=lambda i: -power(bench[i]))
        movers = (fresh + others)[:2]
        if not movers:
            return best_t, (best_b + [None] * data.BENCH_SLOTS)[:data.BENCH_SLOTS]
        # try the new monster (then the strongest bench monster) in every team slot
        for i in movers:
            if bench[i].name is None:
                continue
            for j in range(6):
                if team[j] is not None and team[j].name is None:
                    continue
                t2, b2 = list(team), list(bench)
                t2[j], b2[i] = bench[i], team[j]
                v = f(t2)
                if v > best_v + (1e-9 if i in fresh else self.p.swap_gain):
                    best_t, best_b, best_v = t2, b2, v
        rest = [u for u in best_b if u is not None]
        if len(rest) > data.BENCH_SLOTS:          # cannot happen in the game; keep the strongest
            rest = sorted(rest, key=power, reverse=True)[:data.BENCH_SLOTS]
        return best_t, (rest + [None] * data.BENCH_SLOTS)[:data.BENCH_SLOTS]

    def evaluate_after(self, s: RunState, t: RunState, team, bench) -> tuple[float, list, list]:
        team2, bench2 = self.place(t, team, bench)
        return self.quick(t, team2, bench2), team2, bench2

    # ------------------------------------------------------ greedy finish ----
    def _card_order(self, s: RunState) -> list[int]:
        cands = []
        for i, c in enumerate(s.shop):
            if c and c.kind == "monster" and model.can_buy(s, i):
                u = model.new_unit(c.name, c.price, 1, dict(c.stats) or None)
                same = sum(1 for _, _, o in s.owned() if o.name == c.name)
                cands.append((power(u) + 200 * same, i))
        return [i for _, i in sorted(cands, reverse=True)][: self.p.screen]

    def finish(self, s: RunState, team, bench, v: float) -> float:
        """Value after greedily buying more from the visible shop (what the money is for)."""
        for _ in range(self.p.greedy_steps):
            best = None
            for i in self._card_order(s):
                t = model.buy(s, i)
                v2, team2, bench2 = self.evaluate_after(s, t, team, bench)
                if v2 > v + 1e-9 and (best is None or v2 > best[0]):
                    best = (v2, t, team2, bench2)
            if best is None:
                break
            v, s, team, bench = best
        return v

    # --------------------------------------------------------- candidates ----
    @staticmethod
    def _sellable(s: RunState, u: Unit) -> bool:
        """Units a sale may be considered for: never one bought this turn (that is a wasted purchase
        and half its price), never an egg (it hatches on the bench), never one the reader cannot name."""
        return u.name is not None and u.name not in s.bought and not knowledge.is_egg(u.name)

    def _item_states(self, s: RunState, i: int, c) -> list[RunState]:
        """The states an item can lead to (a sample when it is random)."""
        if c.name == "Apex Bait":
            # ranking the shop up only pays through the rerolls that follow: score it with one
            if s.money < c.price + s.reroll_price:
                return []
            up = model.item_outcomes(s, i)[0]
            return [model.reroll(up, self.rng) for _ in range(max(2, self.p.reroll_samples))]
        outs = model.item_outcomes(s, i)
        if len(outs) > model.MAX_OUTCOMES:
            outs = self.rng.sample(outs, model.MAX_OUTCOMES)
        return outs

    def _candidates(self, s: RunState) -> list[tuple[str, list[Action], list[RunState]]]:
        """(label, actions, resulting states); several states when the result is random (their value is
        averaged)."""
        out: list[tuple[str, list[Action], list[RunState]]] = []
        for i, c in enumerate(s.shop):
            if c is None or c.name is None:
                continue
            if c.kind == "item":
                if c.price <= s.money and s.items_left > 0 and model.item_is_worth_using(s, c) \
                        and c.name not in TICKETS:
                    states = self._item_states(s, i, c)
                    if states:
                        out.append((f"use {c.name}", [Action("item", i)], states))
                continue
            if model.can_buy(s, i):
                t = model.buy(s, i)
                out.append((f"buy {c.name} ${c.price}", [Action("buy", i)], [t]))
                sp = data.species(c.name)
                # fodder loop: a Bug bought for its growth on Guardiant, then sold
                if sp and sp.is_bug and any(u.species and u.species.bug_growth for _, _, u in s.owned()):
                    new = _new_slot(s, t, c.name)
                    if new is not None and t.slot(*new).level == 1:
                        out.append((f"feed {c.name} to Guardiant (buy, then sell)", [Action("buy", i)],
                                    [model.sell(t, *new)]))
            # sell first when money or space is short
            if c.price > s.money or not model.can_buy(s, i):
                for w, k, u in sorted((x for x in s.owned() if self._sellable(s, x[2])),
                                      key=lambda x: power(x[2]))[:3]:
                    if u.name == c.name:
                        continue
                    t = model.sell(s, w, k)
                    if model.can_buy(t, i):
                        out.append((f"sell {u.name} to buy {c.name}", [Action("sell", src=(w, k))],
                                    [model.buy(t, i)]))
        team_weak = sorted(((w, k, u) for w, k, u in s.owned() if w == TEAM and self._sellable(s, u)),
                           key=lambda x: power(x[2]))[:2]
        for w, k, u in [x for x in s.owned() if x[0] == BENCH and self._sellable(s, x[2])] + team_weak:
            out.append((f"sell {u.name}", [Action("sell", src=(w, k))], [model.sell(s, w, k)]))
        return out

    # ------------------------------------------------------------ clean-up ----
    def dead_weight(self, s: RunState, team) -> list[tuple[str, int, Unit]]:
        """Bench monsters that will never play: they are not on the team, will not join it, and are not
        two copies away from a merge that would make them good enough to. Selling them frees a bench slot
        and turns them into money that buys something useful.

        Kept: eggs (they hatch), a monster a shop card could merge (a third copy is on sale right now),
        a pair of copies whose merged form would out-rank the weakest fielded monster, anything the
        reader cannot name, and anything bought this turn."""
        fielded = [u for u in team if u is not None]
        if len(fielded) < 4 and s.day < 6:
            return []                            # early on the bench is a waiting room, not a cost
        weakest = min((power(u) for u in fielded), default=0.0)
        on_sale = {c.name for c in s.shop if c and c.kind == "monster" and c.name}
        owned = [u for _, _, u in s.owned()]
        out = []
        for k, u in enumerate(s.bench):
            if u is None or not self._sellable(s, u) or u.sell_price() <= 0 and u.growth():
                continue
            if u.name in on_sale:
                continue
            copies = sum(1 for o in owned if o.name == u.name and o.level == u.level)
            need = 3 if u.level == 1 else 2
            if u.level < 3 and copies >= need - 1:
                nxt = model.new_unit(u.name, 0, u.level + 1)
                if power(nxt) > 1.1 * weakest:
                    continue                     # a merge here would improve the team: worth holding
            if power(u) > weakest and not any(o is u for o in team):
                # stronger than the weakest fielded monster: the arrangement will use it, not a dead weight
                continue
            out.append((BENCH, k, u))
        return out

    def _reroll_value(self, s: RunState, team, bench) -> float | None:
        free = s.free_rerolls > 0
        if self.p.reroll_samples <= 0 or s.rerolls >= self.p.max_rerolls:
            return None
        if not free and s.money < s.reroll_price + 5:
            return None
        total = 0.0
        for _ in range(self.p.reroll_samples):
            t = model.reroll(s, self.rng)
            v0 = self.quick(t, team, bench)
            total += self.finish(t, team, bench, v0)
        return total / self.p.reroll_samples

    # ------------------------------------------------------------- decide ----
    def decide(self, s: RunState) -> Plan:
        """The next action(s) for this shop state."""
        notes: list[str] = []
        team, bench = self.arrange_full(s)
        # 0. monsters that will never play: sell them first, so the bench has room and the money is spent
        for w, k, u in self.dead_weight(s, team):
            win = self.win_today(s, team) if any(team) else 0.0
            return Plan([Action("sell", src=(w, k), why=f"sell {u.name}: it will never play (not on the team, "
                                                       f"no merge in reach)", value=0.0)],
                        0.0, notes, considered=[], win_now=win)
        base = self.quick(s, team, bench)
        base_finish = self.finish(s, team, bench, base)
        best_label, best_actions, best_v = "end turn", [], base
        considered = []
        win_now = self.win_today(s, team) if any(team) else 0.0
        for label, actions, states in self._candidates(s):
            total = 0.0
            for t in states:
                v, team2, bench2 = self.evaluate_after(s, t, team, bench)
                total += self.finish(t, team2, bench2, v)
            v = total / len(states)
            considered.append((label, v - base))
            if v > best_v + self.p.min_gain:
                best_label, best_actions, best_v = label, actions, v
        rv = self._reroll_value(s, team, bench)
        if rv is not None:
            notes.append(f"reroll {rv - base:+.3f} vs best {best_v - base:+.3f}")
            considered.append(("reroll", rv - base))
            if rv > max(best_v, base_finish) + self.p.min_gain:
                best_label, best_actions, best_v = "reroll", [Action("reroll")], rv
        if best_actions:
            for a in best_actions:
                a.why, a.value = best_label, best_v
            return Plan(best_actions, best_v, notes + [f"{best_label}: {best_v - base:+.3f}"],
                        considered=considered, win_now=win_now)
        # nothing beats ending the turn: tickets, free buffs, spend the surplus, lock, arrange and battle
        for i, c in enumerate(s.shop):
            if c and c.kind == "item" and c.name in TICKETS and c.price <= s.money and s.items_left > 0:
                return Plan([Action("item", i, why=f"use {c.name} (shop of one rarity)")], base, notes,
                            considered=considered, win_now=win_now)
        if s.items_left > 0 and s.owned():
            for i, c in enumerate(s.shop):
                if c and c.kind == "item" and c.name in FREE_BUFFS and c.price == 0:
                    return Plan([Action("item", i, why=f"use free {c.name}")], base, notes,
                                considered=considered, win_now=win_now)
        spare = self.surplus(s)
        if spare >= s.reroll_price and s.rerolls < self.p.max_rerolls:
            return Plan([Action("reroll", why=f"spend the surplus: ${s.money} in hand, ${spare} more than is "
                                              f"worth keeping, and a reroll is the only way left to turn it "
                                              f"into a stronger team", value=base)],
                        base, notes + ["surplus reroll"], considered=considered, win_now=win_now)
        actions: list[Action] = []
        lock = self._lock_choice(s, team, bench, base)
        if lock:
            actions.append(Action("lock", why=lock))
        actions += moves_to(s.team, s.bench, team, bench)
        win = self.win_today(s, team)
        notes.append(f"expected win chance today {win:.0%}")
        actions.append(Action("battle", why=f"expected win chance {win:.0%}"))
        return Plan(actions, base, notes, considered=considered, win_now=win)

    def surplus(self, s: RunState) -> int:
        """Money above what is worth carrying into tomorrow. Unspent money wins no battles: with $300 in
        hand and nothing worth buying, rerolling (the shop, and its item slot) is the way to find
        merges, higher-tier monsters and items. Nothing is kept when a loss today could end the run."""
        reserve = 0 if s.lives <= data.lives_lost(s.day) else self.p.reserve
        return max(0, s.money - reserve)

    def _lock_choice(self, s: RunState, team, bench, base: float) -> str | None:
        if s.locked:
            return None
        tomorrow = s.money + data.income(s.day + 1)
        for i, c in enumerate(s.shop):
            if c is None or c.kind != "monster" or c.price <= s.money or c.price > tomorrow:
                continue
            t = replace(s.copy(), money=c.price)
            if not model.can_buy(t, i):
                continue
            v_with, _, _ = self.evaluate_after(t, model.buy(t, i), team, bench)
            gain = v_with - self.quick(replace(s.copy(), money=0), team, bench)
            if gain > self.p.lock_gain:
                return f"lock for {c.name} (${c.price}, worth {gain:+.3f})"
        return None

    def final_layout(self, s: RunState):
        return self.arrange_full(s)


def _same_units(tb, owned) -> bool:
    placed = [u for u in tb[0] + tb[1] if u is not None]
    return sorted(map(repr, placed)) == sorted(map(repr, owned))


def _count(lst, u) -> int:
    return sum(1 for x in lst if x == u)


def _contains(lst, u) -> bool:
    return u is not None and any(x == u for x in lst)


def _new_slot(before: RunState, after: RunState, name: str) -> tuple[str, int] | None:
    for w in (TEAM, BENCH):
        for i in range(len(before.team if w == TEAM else before.bench)):
            if before.slot(w, i) is None and after.slot(w, i) is not None and after.slot(w, i).name == name:
                return w, i
    return None


# --------------------------------------------------------------- moves ----

def _row(pos: tuple[str, int]) -> int | None:
    return pos[1] // 3 if pos[0] == TEAM else None


def drag_works(src: tuple[str, int], dst: tuple[str, int], occupied_dst: bool) -> bool:
    """Same-row team-to-team drags onto an occupied slot fail silently (runs 3-9)."""
    if not occupied_dst:
        return True
    return not (src[0] == TEAM and dst[0] == TEAM and _row(src) == _row(dst))


def moves_to(team0: list, bench0: list, team1: list, bench1: list, limit: int = 24) -> list[Action]:
    """Drags that turn (team0, bench0) into (team1, bench1). Units are matched by
    value (name, level, stats). Uses empty slots as a buffer for swaps that
    the game does not allow directly."""
    cur = {(TEAM, i): u for i, u in enumerate(team0)}
    cur.update({(BENCH, i): u for i, u in enumerate(bench0)})
    want = {(TEAM, i): u for i, u in enumerate(team1)}
    want.update({(BENCH, i): u for i, u in enumerate(bench1)})
    # only team placement matters; bench order is free
    actions: list[Action] = []

    def done(p):
        return p[0] == BENCH or cur[p] == want[p]

    for _ in range(limit):
        todo = [p for p in want if p[0] == TEAM and not done(p)]
        if not todo:
            break
        p = todo[0]
        target = want[p]
        if target is None:
            # this team slot must end empty: move its unit to a free bench slot (or swap later)
            free = [q for q in cur if q[0] == BENCH and cur[q] is None]
            if not free:
                break
            q = free[0]
            actions.append(Action("move", src=p, dst=q))
            cur[q], cur[p] = cur[p], None
            continue
        # where is a matching unit that is not already correctly placed?
        sources = [q for q, u in cur.items() if u == target and q != p and not (q[0] == TEAM and done(q))]
        if not sources:
            break
        q = sources[0]
        if drag_works(q, p, cur[p] is not None):
            actions.append(Action("move", src=q, dst=p))
            cur[p], cur[q] = cur[q], cur[p]
            continue
        # same-row swap: park the occupant of p in an empty slot first
        free = [r for r in cur if cur[r] is None and r != q]
        if free:
            r = sorted(free, key=lambda r: r[0] != BENCH)[0]
            actions.append(Action("move", src=p, dst=r))
            cur[r], cur[p] = cur[p], None
            actions.append(Action("move", src=q, dst=p))
            cur[p], cur[q] = cur[q], None
            continue
        # nothing empty: go through a bench slot (team<->bench swaps work)
        b = next(r for r in cur if r[0] == BENCH)
        actions.append(Action("move", src=q, dst=b))
        cur[b], cur[q] = cur[q], cur[b]
        actions.append(Action("move", src=b, dst=p))
        cur[p], cur[b] = cur[b], cur[p]
    return actions
