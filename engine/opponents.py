"""A spread of plausible opponents for each day.

Battles are against stored snapshots of other players' teams on the same day, and
who you meet is random. We cannot see them in advance, so the engine scores a team
against a pool of synthetic opponents built by playing "ghost" runs: each ghost
gets the real income, draws real shops by the rank odds, and buys with one of
three skill levels:

- casual: buys whatever it can afford, no rerolls, no selling, rough placement;
- steady: prefers copies and merges, rerolls once or twice, replaces weak units;
- strong: merge-hunts with more rerolls, feeds Bug growth, upgrades the weakest slot.

Merges give the ghost a trinket of the merged monster's rarity (random), so late
opponents carry trinkets like real ones. One ghost run gives one team per day.

The calibration knobs are POOL_MIX, EXTRA_INCOME and POWER_RAMP. They were set on
2026-11-12 so that the teams of the first live engine run (runs/2026-11-12-chef) score
close to their real results (won Days 1-6, lost Days 7-11) and the old simple rules win
about as often as they did for real (3 of 14 battles). When the bot starts logging real
opponent teams, add them with `add_recorded()` and they join the pool.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from . import data, growth, model
from .arrange import heuristic_layout, power
from .evaluate import slot_spec
from .model import RunState

POOL_MIX = {"casual": 0.15, "steady": 0.35, "strong": 0.30, "expert": 0.20}
# Extra money per day for ghosts, standing in for what they get from items, events,
# trainer abilities and economy trinkets (none of which the ghosts model).
POWER_RAMP = 0.3
EXTRA_INCOME = {"casual": 0, "steady": 20, "strong": 35, "expert": 50}
RECORDED = Path(__file__).resolve().parent.parent / "data" / "opponents_recorded.jsonl"


def _ghost_buy_score(s: RunState, card: model.Card, skill: str) -> float:
    owned = [u for _, _, u in s.owned()]
    same = sum(1 for u in owned if u.name == card.name and u.level == 1)
    sp = data.species(card.name)
    if sp is None:
        return -1
    base = power(model.new_unit(card.name, card.price))
    if skill == "casual":
        return base + card.price
    bonus = 0.0
    if same >= 1:
        bonus += (160 if skill == "expert" else 80) * same      # working toward a merge
        if skill == "expert" and same >= 2:
            bonus += 400
    if sp.is_bug and any(u.species and u.species.bug_growth for u in owned):
        bonus += 40
    if sp.self_ko and s.day >= 4:
        bonus -= 120
    if card.name == "Dirgefin":
        bonus -= 500
    return base + bonus


def _ghost_shop(s: RunState, rng: random.Random, skill: str) -> RunState:
    rerolls = {"casual": rng.randint(0, 1), "steady": rng.randint(1, 3), "strong": rng.randint(3, 7),
               "expert": 12}[skill]
    for _ in range(30):
        cards = [(i, c) for i, c in enumerate(s.shop)
                 if c and c.kind == "monster" and c.price <= s.money]
        if cards:
            i, c = max(cards, key=lambda ic: _ghost_buy_score(s, ic[1], skill))
            worth = _ghost_buy_score(s, c, skill)
            if model.can_buy(s, i):
                s = model.buy(s, i)
                continue
            # full: sell the weakest unit that is worth less than the card
            owned = [(w, k, u) for w, k, u in s.owned()
                     if not (u.species and u.species.bug_growth and u.level > 1)
                     and not any(c2 and c2.name == u.name for c2 in s.shop)]
            if owned and skill != "casual":
                w, k, u = min(owned, key=lambda x: power(x[2]) * x[2].level)
                if worth > 1.3 * power(u) * u.level:
                    s = model.sell(s, w, k)
                    continue
        if rerolls > 0 and s.money >= data.REROLL_PRICE + (5 if skill == "expert" else 10):
            s = model.reroll(s, rng)
            rerolls -= 1
            continue
        break
    return s


def _ghost_trinket(rarity: str, rng: random.Random) -> str | None:
    opts = [n for n, t in data.trinkets().items() if t["rarity"] == rarity]
    return rng.choice(opts) if opts else None


def _ramped(spec: dict, day: int) -> dict:
    """Scale a ghost's numbers up from day 5 on (POWER_RAMP per day). Ghosts miss what
    real players get from trainers, events, item scalers and well-built amplifier
    combos; without this the engine thought a weak late board was safe."""
    f = 1.0 + POWER_RAMP * max(0, day - 4)
    if f == 1.0:
        return spec
    out = dict(spec)
    out["slots"] = [None if sl is None else {**sl, "stats": {k: round(v * f) for k, v in sl["stats"].items()}}
                    for sl in spec["slots"]]
    return out


def ghost_run(seed: int, days: int, skill: str) -> list[dict]:
    """Play one ghost run; return its team spec for every day 1..days."""
    rng = random.Random(seed)
    s = RunState(day=1, money=0, rank=1)
    out = []
    for day in range(1, days + 1):
        s.day = day
        s.rank = day
        s.money += data.income(day) + (EXTRA_INCOME.get(skill, 0) * (day - 1))
        s.items_left = 1
        s.shop = model.random_shop(s.rank, rng)
        s = _ghost_shop(s, rng, skill)
        for r in s.gifts:
            t = _ghost_trinket(r, rng)
            if t:
                s.trinkets.append(t)
        s.gifts = []
        units = [u for _, _, u in s.owned()]
        if skill == "casual":
            rng.shuffle(units)
            team = units[:6] + [None] * (6 - len(units[:6]))
            rest = units[6:]
        else:
            team, rest = heuristic_layout(units)
        s.team = list(team)
        s.bench = (rest + [None] * 4)[:4]
        # Brawlmantis-style "On Victory" growth: assume the ghost won about half its days
        if rng.random() < 0.5:
            for w, i, u in s.owned():
                if u.name == "Brawlmantis":
                    d = u.stat_dict()
                    d["damage"] += 10 * u.level
                    s.set_slot(w, i, u.with_stats(d))
        spec = {"trainer": "", "day": day, "hp": data.hp_for_day(day), "skill": skill,
                "trinkets": list(s.trinkets), "slots": [slot_spec(u) for u in s.team]}
        out.append(_ramped(spec, day))
        # the ghost's monsters keep what they grow permanently in its battle
        s.team = growth.after_mirror_battle(s.team, spec)
    return out


def build_pools(n: int = 48, days: int = 15, seed: int = 1, mix: dict | None = None) -> dict[int, list[dict]]:
    """n opponents for every day. The order is shuffled once, so the first k of a
    pool are a fair sample of the mix (the evaluator often uses only the first k)."""
    mix = mix or POOL_MIX
    rng = random.Random(seed)
    skills = []
    for skill, share in mix.items():
        skills += [skill] * round(share * n)
    while len(skills) < n:
        skills.append("steady")
    skills = skills[:n]
    rng.shuffle(skills)
    pools: dict[int, list[dict]] = {d: [] for d in range(1, days + 1)}
    for j, skill in enumerate(skills):
        for spec in ghost_run(seed * 100_003 + j, days, skill):
            pools[spec["day"]].append(spec)
    for d, recs in load_recorded().items():
        if d in pools:
            pools[d] = recs + pools[d]
    return pools


def load_recorded() -> dict[int, list[dict]]:
    """Real opponent teams logged by the bot (one JSON object per line, with 'day')."""
    out: dict[int, list[dict]] = {}
    if RECORDED.exists():
        for line in RECORDED.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out.setdefault(int(rec["day"]), []).append(rec)
    return out


def add_recorded(day: int, team: dict) -> None:
    RECORDED.parent.mkdir(parents=True, exist_ok=True)
    with open(RECORDED, "a", encoding="utf-8") as f:
        f.write(json.dumps({**team, "day": day}) + "\n")


_CACHE: dict[tuple, dict] = {}


def pools(n: int = 48, seed: int = 1) -> dict[int, list[dict]]:
    key = (n, seed)
    if key not in _CACHE:
        _CACHE[key] = build_pools(n=n, seed=seed)
    return _CACHE[key]
