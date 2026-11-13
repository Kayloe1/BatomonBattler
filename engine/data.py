"""Static game knowledge the decision engine needs (Pantra only).

Monster numbers come from data/batomon_pantra.csv and data/batomon_pantra_levels.csv
(read from the Batopedia). Run rules (HP, income, lives, shop odds) come from
docs/step2-screen-map.md and the older playbook (Kayloe1/batomon,
batomon-showdown-notes.md, MECHANICS 1), checked in runs 1 to 18.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

STATS = ("damage", "heal", "shield", "poison", "burn", "shock", "multicast")
RARITIES = ("Common", "Uncommon", "Rare", "Super Rare", "Legendary")

# Trainer HP by day (own bar; the enemy's matches it). Days 9+ from Run 14/18 on
# build 25448953; day 14 (63000) seen on the opponent bar 2026-11-12; past day 14 the growth
# (~35-40% a day) is extrapolated.
HP_BY_DAY = [300, 500, 800, 1400, 2400, 3800, 5700, 8300, 11600, 17300, 24900, 34700, 47300, 63000]


def hp_for_day(day: int) -> int:
    if day <= len(HP_BY_DAY):
        return HP_BY_DAY[max(day, 1) - 1]
    return int(HP_BY_DAY[-1] * 1.4 ** (day - len(HP_BY_DAY)))


def lives_lost(day: int) -> int:
    """Lives a loss costs: 1 on days 1-2, 2 on days 3-4, 3 from day 5 (verified to day 11)."""
    return 1 if day <= 2 else 2 if day <= 4 else 3


def income(day: int) -> int:
    """Money added at the start of a day: $30 on day 1, then $25 + $5 x day."""
    return 30 if day <= 1 else 25 + 5 * day


REROLL_PRICE = 3
SHOP_MONSTERS = 4
TEAM_SLOTS = 6
BENCH_SLOTS = 4
BADGES_TO_WIN = 10
START_LIVES = 10

# Shop rarity odds (C, U, R, SR, L) by shop rank; rank = day, +2 for Rich Lady.
RANK_ODDS = {
    1: (100, 0, 0, 0, 0), 2: (90, 10, 0, 0, 0), 3: (75, 25, 0, 0, 0), 4: (67, 30, 3, 0, 0),
    5: (55, 30, 15, 0, 0), 6: (45, 32, 20, 3, 0), 7: (30, 40, 25, 5, 0), 8: (25, 30, 35, 10, 0),
    9: (20, 25, 38, 15, 2), 10: (15, 20, 40, 20, 5), 11: (10, 20, 35, 25, 10),
    12: (5, 15, 30, 35, 15), 13: (1, 10, 30, 39, 20),
}


def rank_odds(rank: int) -> tuple[int, ...]:
    return RANK_ODDS[min(max(rank, 1), 13)]


# Copies needed for a level: 3 Lv1 make a Lv2, two Lv2 (6 copies) make a Lv3.
# Lv4 comes only from events and candies.
COPIES_FOR_LEVEL = {1: 1, 2: 3, 3: 6, 4: 12}


@dataclass
class Species:
    name: str
    cost: int
    rarity: str
    types: tuple[str, ...]
    cooldown: float
    level_stats: dict[int, dict[str, int]]     # 1..4 -> stat -> value (multicast 1 when absent)
    level_cooldown: dict[int, float]
    passive: str = ""
    level_text: dict[int, str] = field(default_factory=dict)
    bug_growth: dict[int, int] = field(default_factory=dict)   # +Damage per Bug bought, by level
    self_ko: bool = False
    evolves: bool = False
    no_ability: bool = False                                   # Stellagon / Focus Pill condition
    foreign: bool = False                                      # data/foreign_monsters.csv (another region)
    event_only: bool = False                                   # given only by an event (Ignit, Talonite...)

    @property
    def is_bug(self) -> bool:
        return "Bug" in self.types

    def stats(self, level: int) -> dict[str, int]:
        return dict(self.level_stats.get(level) or self.level_stats[1])


_NUM = {
    "damage": re.compile(r"Deal (\d+)"),
    "heal": re.compile(r"Heal (\d+)"),
    "shield": re.compile(r"Shield (\d+)"),
    "poison": re.compile(r"Poison (\d+)"),
    "burn": re.compile(r"Burn (\d+)"),
    "shock": re.compile(r"Shock (\d+)"),
    "multicast": re.compile(r"Multicast (\d+)"),
}


def _parse_active(text: str) -> dict[str, int]:
    head = text.split("|")[0]
    out = {k: 0 for k in STATS}
    for k, rx in _NUM.items():
        m = rx.search(head)
        if m:
            out[k] = int(m.group(1))
    out["multicast"] = max(out["multicast"], 1)
    return out


@lru_cache(maxsize=1)
def roster() -> dict[str, Species]:
    levels = {}
    with open(DATA / "batomon_pantra_levels.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            levels[row["name"]] = row
    out: dict[str, Species] = {}
    rows = []
    with open(DATA / "batomon_pantra.csv", encoding="utf-8") as f:
        rows += [(r, False) for r in csv.DictReader(f)]
    foreign = DATA / "foreign_monsters.csv"
    if foreign.exists():
        with open(foreign, encoding="utf-8") as f:
            rows += [(r, True) for r in csv.DictReader(f)]
    with open(DATA / "stand_in_monsters.csv", encoding="utf-8") as f:     # never in the shop, like foreign
        rows += [(r, True) for r in csv.DictReader(f)]
    for row, is_foreign in rows:
        name = row["name"]
        cd = float(row["cooldown_s"])
        stats = {1: _parse_active(row["active"])}
        cds = {1: cd}
        text = {1: (row["active"] + " | " + row["passive"]).strip(" |")}
        lv = levels.get(name, {})
        for n in (2, 3, 4):
            t = lv.get(f"lv{n}", "") or ""
            text[n] = t
            body = re.sub(r"^(EVOLVED:?\s*\w*:?|\w+:)\s*", "", t) if t.startswith(("EVOLVED", "Bambudo", "Sunsage")) else t
            body = re.sub(r"^CD [\d.]+s\s*", "", body)
            s = _parse_active(body) if body and not body.startswith("same") else dict(stats[n - 1])
            # a level row that only changes a number in the passive keeps the active
            if not any(s[k] for k in STATS if k != "multicast") and any(stats[n - 1][k] for k in STATS if k != "multicast"):
                keep = dict(stats[n - 1])
                keep["multicast"] = max(keep["multicast"], s["multicast"])
                s = keep
            stats[n] = s
            m = re.search(r"CD ([\d.]+)s", t)
            cds[n] = float(m.group(1)) if m else cds[n - 1]
        passive = row["passive"] or ""
        growth = {}
        if "After you buy a Bug" in passive and "Damage" in passive:
            g1 = int(re.search(r"\+(\d+) Damage", passive).group(1))
            growth = {1: g1}
            for n in (2, 3, 4):
                m = re.search(r"\+(\d+) Damage per Bug", text[n])
                growth[n] = int(m.group(1)) if m else growth[n - 1]
        out[name] = Species(
            name=name, cost=int(row["cost"]), rarity=row["rarity"],
            types=tuple(row["types"].split("/")), cooldown=cd,
            level_stats=stats, level_cooldown=cds, passive=passive, level_text=text,
            bug_growth=growth,
            self_ko="Knockout self" in passive,
            evolves="Evolves at level 3" in passive,
            no_ability=not passive,
            foreign=is_foreign,
            event_only="Event-only" in (row.get("source") or ""),
        )
    return out


# A monster the reader cannot name plays as this (data/stand_in_monsters.csv): its own badges, a typical
# Rare's speed, no passive. Before, such a monster could neither join the team nor be sold.
STAND_IN = "Unknown Rare"


def species(name: str | None) -> Species | None:
    return roster().get(name) if name else None


def by_rarity(rarity: str) -> list[Species]:
    """Pantra monsters of a rarity (foreign monsters only reach the shop through an event)."""
    return [s for s in roster().values() if s.rarity == rarity and not s.foreign]


@lru_cache(maxsize=1)
def items() -> dict[str, dict]:
    with open(DATA / "items.csv", encoding="utf-8") as f:
        return {r["name"]: {"cost": int(r["cost"]), "rarity": r["rarity"], "effect": r["effect"]}
                for r in csv.DictReader(f)}


@lru_cache(maxsize=1)
def trinkets() -> dict[str, dict]:
    with open(DATA / "trinkets.csv", encoding="utf-8") as f:
        return {r["name"]: {"rarity": r["rarity"], "effect": r["effect"]} for r in csv.DictReader(f)}
