"""The run as the engine sees it, and the shop moves that change it.

A `RunState` holds one shop turn: day, lives, badges, money, shop rank, the five
shop cards, the 6 team slots (row-major: 0-2 top row left to right, 3-5 bottom
row) and the 4 bench slots. The moves (`buy`, `sell`, `use_item`, `reroll`) are
pure: they return a new state, so the planner can try sequences without touching
the game. `from_reader()` builds a state from `reader.read_state()`.

Rules modelled (see docs/decision-engine.md for where each comes from):
- buying puts the monster in the first free team slot, else the bench;
- the third Lv1 copy merges into a Lv2 at once, and two Lv2 make a Lv3. The
  merged monster keeps the largest permanent growth of its copies and takes the
  slot of the copy that was on the team (if any);
- every merge gives a trinket gift (its value is scored, the pick is made later);
- a Bug buy grows Guardiant (+8/+16/+24/+48 by level) on team and bench;
- selling refunds about half the price paid (rounded up), free monsters $0.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace

from . import data

TEAM, BENCH = "team", "bench"


@dataclass(frozen=True)
class Unit:
    name: str | None
    level: int = 1
    stats: tuple[tuple[str, int], ...] = ()       # current card numbers, incl. permanent buffs
    paid: int = 0                                  # what the copies cost (sell value basis)
    sell_value: int | None = None                  # as read in game, when known
    copies: int = 1                                # Lv1 copies inside (1, 3, 6, ...)

    @property
    def species(self) -> data.Species | None:
        return data.species(self.name)

    def stat(self, key: str) -> int:
        for k, v in self.stats:
            if k == key:
                return v
        return 1 if key == "multicast" else 0

    def stat_dict(self) -> dict[str, int]:
        d = {k: 0 for k in data.STATS}
        d["multicast"] = 1
        d.update(dict(self.stats))
        return d

    def with_stats(self, d: dict[str, int]) -> "Unit":
        return replace(self, stats=tuple(sorted((k, int(v)) for k, v in d.items() if v)))

    def growth(self) -> dict[str, int]:
        """Numbers above this level's Batopedia values: the permanent buffs."""
        sp = self.species
        if sp is None:
            return {}
        base = sp.stats(self.level)
        cur = self.stat_dict()
        return {k: cur[k] - base.get(k, 0) for k in data.STATS if k != "multicast" and cur[k] > base.get(k, 0)}

    def sell_price(self) -> int:
        if self.sell_value is not None:
            return self.sell_value
        return math.ceil(self.paid / 2)


def new_unit(name: str, paid: int, level: int = 1, stats: dict | None = None) -> Unit:
    sp = data.species(name)
    base = sp.stats(level) if sp else {}
    u = Unit(name=name, level=level, paid=paid, copies=data.COPIES_FOR_LEVEL.get(level, 1))
    return u.with_stats(stats if stats else base)


@dataclass(frozen=True)
class Card:
    name: str | None
    price: int
    kind: str                                   # "monster" or "item"
    stats: tuple[tuple[str, int], ...] = ()
    rarity: str | None = None


@dataclass
class RunState:
    day: int = 1
    lives: int = data.START_LIVES
    badges: int = 0
    money: int = 0
    rank: int = 1
    trainer: str | None = None
    trinkets: list[str] = field(default_factory=list)
    shop: list[Card | None] = field(default_factory=lambda: [None] * 5)
    team: list[Unit | None] = field(default_factory=lambda: [None] * data.TEAM_SLOTS)
    bench: list[Unit | None] = field(default_factory=lambda: [None] * data.BENCH_SLOTS)
    locked: bool = False
    rescue_used: bool = False
    free_rerolls: int = 0
    bug_discount_used: bool = False           # Bug Catcher: first Bug each day $10 less
    gifts: list[str] = field(default_factory=list)   # rarities of trinket gifts earned this turn
    bonus_damage_next_win: int = 0            # Gray Chip and similar, as $ on a win
    items_left: int = 1
    hp_today: int | None = None               # trainer HP read on the shop screen
    odds: tuple[int, ...] | None = None       # shop odds read on the rank bar
    reroll_price: int = data.REROLL_PRICE

    def copy(self) -> "RunState":
        return replace(self, trinkets=list(self.trinkets), shop=list(self.shop), team=list(self.team),
                       bench=list(self.bench), gifts=list(self.gifts))

    # -- views --
    def owned(self) -> list[tuple[str, int, Unit]]:
        return [(TEAM, i, u) for i, u in enumerate(self.team) if u] + \
               [(BENCH, i, u) for i, u in enumerate(self.bench) if u]

    def slot(self, where: str, i: int) -> Unit | None:
        return (self.team if where == TEAM else self.bench)[i]

    def set_slot(self, where: str, i: int, u: Unit | None) -> None:
        (self.team if where == TEAM else self.bench)[i] = u

    def free_slots(self) -> int:
        return sum(u is None for u in self.team + self.bench)

    def key(self) -> tuple:
        return (self.money, tuple(self.team), tuple(self.bench), tuple(self.shop), tuple(self.trinkets))


# ------------------------------------------------------------------ moves ----

def card_price(s: RunState, card: Card) -> int:
    price = card.price
    if card.kind == "monster" and s.trainer == "Bug Catcher" and not s.bug_discount_used:
        sp = data.species(card.name)
        if sp and sp.is_bug:
            # the reader already shows the discounted price on the card; do not
            # discount twice. The flag only records that today's discount is spent.
            pass
    return price


def can_buy(s: RunState, i: int) -> bool:
    card = s.shop[i]
    if card is None or card.name is None or card_price(s, card) > s.money:
        return False
    if card.kind == "item":
        return s.items_left > 0
    if s.free_slots() > 0:
        return True
    # a full team and bench can still take a copy that merges at once
    lv1 = sum(1 for _, _, u in s.owned() if u.name == card.name and u.level == 1)
    return lv1 == 2


def buy(s: RunState, i: int) -> RunState:
    card = s.shop[i]
    assert card is not None and can_buy(s, i), (i, card)
    if card.kind == "item":
        return use_item(s, i)
    t = s.copy()
    price = card_price(t, card)
    t.money -= price
    t.shop[i] = None
    sp = data.species(card.name)
    if sp and sp.is_bug:
        _grow_on_bug_buy(t)
        if t.trainer == "Bug Catcher":
            t.bug_discount_used = True
    stats = dict(card.stats) if card.stats else None
    unit = new_unit(card.name, price, 1, stats)
    place = _first_free(t)
    if place is None:
        t.bench.append(unit)                    # temporary 5th slot: it merges at once
    else:
        t.set_slot(*place, unit)
    _merge(t, card.name)
    return t


def _first_free(s: RunState) -> tuple[str, int] | None:
    # new buys fill the bottom row from the right first (seen in runs), then the top row
    for i in (5, 4, 3, 2, 1, 0):
        if s.team[i] is None:
            return TEAM, i
    for i in range(data.BENCH_SLOTS):
        if s.bench[i] is None:
            return BENCH, i
    return None


def _grow_on_bug_buy(s: RunState) -> None:
    for where, i, u in s.owned():
        sp = u.species
        if sp and sp.bug_growth:
            d = u.stat_dict()
            d["damage"] += sp.bug_growth.get(u.level, sp.bug_growth[1])
            s.set_slot(where, i, u.with_stats(d))


def _merge(s: RunState, name: str) -> None:
    """Apply automatic merges for one species: 3 x Lv1 -> Lv2, 2 x Lv2 -> Lv3."""
    for level, need in ((1, 3), (2, 2)):
        group = [(w, i, u) for w, i, u in s.owned() if u.name == name and u.level == level]
        while len(group) >= need:
            parts = group[:need]
            group = group[need:]
            sp = data.species(name)
            new_level = level + 1
            if sp:
                base = sp.stats(new_level)
                grown = {k: max((p[2].growth().get(k, 0) for p in parts), default=0) for k in data.STATS}
                stats = {k: base.get(k, 0) + grown.get(k, 0) for k in data.STATS}
                stats["multicast"] = base.get("multicast", 1)
            else:
                stats = parts[0][2].stat_dict()
            merged = Unit(name=name, level=new_level, paid=sum(p[2].paid for p in parts),
                          copies=sum(p[2].copies for p in parts)).with_stats(stats)
            # lands in a team slot of one of the copies if any, else the first copy's slot
            target = next(((w, i) for w, i, _ in parts if w == TEAM), (parts[0][0], parts[0][1]))
            for w, i, _ in parts:
                if (w, i) != target:
                    s.set_slot(w, i, None)
            s.set_slot(*target, merged)
            s.gifts.append(sp.rarity if sp else "Common")
    # a copy bought onto a full team and bench sat in a temporary 5th bench slot
    while len(s.bench) > data.BENCH_SLOTS and None in s.bench[data.BENCH_SLOTS:]:
        s.bench.pop(data.BENCH_SLOTS + s.bench[data.BENCH_SLOTS:].index(None))


def sell(s: RunState, where: str, i: int) -> RunState:
    t = s.copy()
    u = t.slot(where, i)
    assert u is not None
    t.money += u.sell_price()
    t.set_slot(where, i, None)
    return t


def move(s: RunState, src: tuple[str, int], dst: tuple[str, int]) -> RunState:
    t = s.copy()
    a, b = t.slot(*src), t.slot(*dst)
    t.set_slot(*dst, a)
    t.set_slot(*src, b)
    return t


# Items whose effect is modelled. Anything else that costs $0 is used anyway
# unless it is in AVOID_ITEMS; paid unmodelled items are skipped.
AVOID_ITEMS = {"Basic Bait", "Recombobulator", "Magic Lasso"}


def use_item(s: RunState, i: int, rng: random.Random | None = None) -> RunState:
    card = s.shop[i]
    t = s.copy()
    t.money -= card.price
    t.shop[i] = None
    t.items_left -= 1
    name = card.name
    owned = t.owned()
    if name in ("Cake", "Feast", "Pom Berry"):
        targets = owned if name == "Feast" else (
            [(w, k, u) for w, k, u in owned if (w, k) == (TEAM, 5)] if name == "Pom Berry" else owned)
        bonus = 8 if name == "Pom Berry" else 5
        if name == "Cake":
            # 2 random monsters: in expectation every owned monster gets 2/n of +5
            share = min(1.0, 2 / max(len(owned), 1))
            for w, k, u in owned:
                d = u.stat_dict()
                if d["damage"] or u.species and u.species.level_stats[1]["damage"]:
                    d["damage"] += round(bonus * share)
                t.set_slot(w, k, u.with_stats(d))
        else:
            for w, k, u in targets:
                d = u.stat_dict()
                d["damage"] += bonus
                t.set_slot(w, k, u.with_stats(d))
        if name == "Pom Berry":
            t.items_left += 1
    elif name == "Coupon":
        t.shop = [replace(c, price=max(0, c.price - 3)) if c and c.kind == "monster" else c for c in t.shop]
    elif name == "Fake Coin":
        t.free_rerolls += 1
    elif name == "Lucky Coin":
        t.money += 3
        t.items_left += 1
    elif name == "Red Coin":
        t.money += 20
        t.lives -= 1
    elif name == "Gray Chip":
        t.bonus_damage_next_win += 15
    elif name in ("Black Sludge", "Hot Pepper", "Battery Pack", "Shiny Pebble", "Mystic Pearl"):
        kind = {"Black Sludge": ("Toxic", "poison", 1), "Hot Pepper": ("Fire", "burn", 1),
                "Battery Pack": ("Electric", "shock", 1), "Shiny Pebble": ("Rock", "shield", 20),
                "Mystic Pearl": ("Water", "heal", 15)}[name]
        for w, k, u in owned:
            if u.species and kind[0] in u.species.types:
                d = u.stat_dict()
                d[kind[1]] += kind[2]
                t.set_slot(w, k, u.with_stats(d))
    elif name == "Tote Bag":
        t.items_left += 2
    elif name == "Nana Berry":
        t.items_left += 1
    return t


def item_is_worth_using(s: RunState, card: Card) -> bool:
    """Items the planner may use. Unmodelled paid items are skipped."""
    if card.name in AVOID_ITEMS:
        return False
    if card.name == "Red Coin":
        # money for a life: only when that life cannot change where the next loss leaves you
        return s.lives >= 8 and s.day <= 4
    if card.name == "Green Stone":
        # turns a random Common into an Uncommon: not when that could hit a grown or levelled Common
        return not any(u.species and u.species.rarity == "Common" and (u.level > 1 or u.growth())
                       for _, _, u in s.owned())
    modelled = {"Cake", "Feast", "Pom Berry", "Coupon", "Fake Coin", "Lucky Coin", "Gray Chip",
                "Black Sludge", "Hot Pepper", "Battery Pack", "Shiny Pebble", "Mystic Pearl",
                "Tote Bag", "Nana Berry", "Focus Pill", "Green Stone", "Gray Ticket", "Green Ticket",
                "Blue Ticket", "Purple Ticket", "Golden Ticket", "Coffee"}
    return card.price == 0 or card.name in modelled


def reroll(s: RunState, rng: random.Random) -> RunState:
    t = s.copy()
    if t.free_rerolls:
        t.free_rerolls -= 1
    else:
        t.money -= t.reroll_price
    t.shop = random_shop(t.rank, rng, t.trainer, t.odds)
    return t


def random_shop(rank: int, rng: random.Random, trainer: str | None = None,
                odds: tuple[int, ...] | None = None) -> list[Card | None]:
    odds = odds or data.rank_odds(rank)
    if trainer == "Gentleman" and odds is None:
        odds = (0, 0) + tuple(odds[2:]) if sum(odds[2:]) else (0, 0, 100, 0, 0)
    cards: list[Card | None] = []
    for _ in range(data.SHOP_MONSTERS):
        rarity = rng.choices(data.RARITIES, weights=odds)[0]
        sp = rng.choice(data.by_rarity(rarity))
        cards.append(Card(sp.name, sp.cost, "monster", tuple(sorted(sp.stats(1).items())), rarity))
    cards.append(None)          # the item slot is not modelled in rollouts
    return cards


# ------------------------------------------------------- reader -> state ----

def _stats_from_badges(badges: list[dict] | None) -> dict[str, int]:
    out: dict[str, int] = {}
    for b in badges or []:
        if b.get("value") is None or not b.get("stat"):
            continue
        out[b["stat"]] = out.get(b["stat"], 0) + int(b["value"])
    return out


def unit_from_reader(slot: dict | None, price_hint: int | None = None) -> Unit | None:
    if slot is None:
        return None
    name = slot.get("name")
    level = slot.get("level") or 1
    sp = data.species(name)
    stats = _stats_from_badges(slot.get("stats"))
    if sp and "multicast" not in stats:
        stats["multicast"] = sp.stats(level).get("multicast", 1)
    paid = price_hint if price_hint is not None else (sp.cost * data.COPIES_FOR_LEVEL.get(level, 1) if sp else 0)
    return Unit(name=name, level=level, paid=paid, sell_value=slot.get("sell_value"),
                copies=data.COPIES_FOR_LEVEL.get(level, 1)).with_stats(stats)


def card_from_reader(card: dict | None) -> Card | None:
    if card is None or card.get("name") is None or card.get("price") is None:
        return None
    return Card(card["name"], card["price"], card.get("kind") or "monster",
                tuple(sorted(_stats_from_badges(card.get("stats")).items())), card.get("rarity"))


def from_reader(state: dict, memory: dict | None = None) -> RunState:
    """Build a RunState from reader.read_state() on the shop screen.

    `memory` carries what the screen does not show (trinkets owned, what each
    monster cost, whether the rescue was used); play.py keeps it between calls.
    """
    memory = memory or {}
    paid = memory.get("paid", {})
    team = [unit_from_reader(s, paid.get(f"team{i}")) for i, s in enumerate(state.get("team") or [None] * 6)]
    bench = [unit_from_reader(s, paid.get(f"bench{i}")) for i, s in enumerate(state.get("bench") or [None] * 4)]
    return RunState(
        day=state.get("day") or 1, lives=state.get("lives") or 1, badges=state.get("badges") or 0,
        money=state.get("money") or 0, rank=state.get("shop_rank") or state.get("day") or 1,
        trainer=state.get("trainer"), trinkets=list(memory.get("trinkets", [])),
        shop=[card_from_reader(c) for c in state.get("shop") or [None] * 5],
        team=team, bench=bench, locked=bool(state.get("locked")),
        rescue_used=bool(memory.get("rescue_used")), items_left=1,
        hp_today=state.get("trainer_hp"),
        odds=tuple(state["shop_odds"].get(r, 0) for r in data.RARITIES) if state.get("shop_odds") else None,
        reroll_price=state.get("reroll_price") or data.REROLL_PRICE,
    )
