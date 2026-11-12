"""Choose which owned monsters fight and where they stand.

1. `heuristic_layout` places monsters by the positional rules found in runs
   (playbook POSITIONS): the strongest dealer top-middle, "trigger the ally above"
   pieces directly below a matching carry, "in front" givers (Saberhorn, Zephyrex)
   to its left, "behind" givers (Dracana, Boomagon, Onsetra, Pylong, Blixie) to its
   right, adjacent buffers where they touch the most allies.
2. `improve` then tries every swap between two of the 10 slots (team and bench)
   and keeps a swap when the simulator says the team does better against the
   opponent pool, until no swap helps. The simulator, not the rules, has the last word.
"""
from __future__ import annotations

from itertools import combinations

import knowledge

from . import data
from .model import Unit

FIGHT_SECONDS = 15.0

ABOVE_TRIGGER = {"Cicadence": "Bug", "Dryadell": "Grass", "Magmalith": "Fire", "Noxalith": "Toxic"}
IN_FRONT_GIVER = {"Saberhorn", "Zephyrex"}
BEHIND_GIVER = {"Dracana", "Boomagon", "Onsetra", "Pylong", "Blixie"}
ADJACENT_BUFFER = {"Formiqueen", "Gaiadrasil", "Noxnimbus", "Aster", "Cherubble", "Ironcore",
                   "Torrantler", "Puffloon", "Stellagon", "Geminiss", "Aegistruct"}
# never fielded: eggs do nothing on the team; Dirgefin knocks out every Common on both sides
BENCH_ONLY = {"Dragon Egg", "Purple Egg"} | set(knowledge.NEVER_FIELD)


def bench_only(u: Unit | None) -> bool:
    return u is not None and (u.name in BENCH_ONLY or knowledge.is_egg(u.name))


def power(u: Unit | None, fight: float = FIGHT_SECONDS) -> float:
    """Rough damage-equivalent per fight, used only to order and prune."""
    if u is None or u.name is None:
        return 0.0
    sp = u.species
    if sp is None:
        return 0.0
    if bench_only(u):
        return 0.0
    d = u.stat_dict()
    cd = sp.level_cooldown.get(u.level, sp.cooldown) or sp.cooldown
    casts = 1 if sp.self_ko else max(fight / cd, 1)
    mc = d["multicast"]
    per_cast = d["damage"] + 0.5 * d["heal"] + 0.4 * d["shield"] + d["poison"] * fight / 2 \
        + d["burn"] * 3 + d["shock"] * 4
    value = per_cast * mc * casts
    if u.name in ABOVE_TRIGGER or u.name in IN_FRONT_GIVER or u.name in BEHIND_GIVER \
            or u.name in ADJACENT_BUFFER:
        value += 60 * u.level          # amplifier bonus; the simulator settles the real value
    return value


def neighbours(i: int) -> list[int]:
    r, c = divmod(i, 3)
    out = []
    if c > 0:
        out.append(i - 1)
    if c < 2:
        out.append(i + 1)
    out.append(i + 3 if r == 0 else i - 3)
    return out


def heuristic_layout(units: list[Unit]) -> tuple[list[Unit | None], list[Unit | None]]:
    """Returns (team[6], rest) from a list of owned units."""
    pool = sorted([u for u in units if u is not None], key=power, reverse=True)
    fielders = [u for u in pool if not bench_only(u)]
    team: list[Unit | None] = [None] * 6
    chosen = fielders[:6]
    rest = [u for u in pool if u not in chosen or chosen.count(u) < 1]
    rest = [u for u in pool if not any(u is c for c in chosen)]
    if not chosen:
        return team, rest
    amps = [u for u in chosen if u.name in ABOVE_TRIGGER or u.name in IN_FRONT_GIVER
            or u.name in BEHIND_GIVER or u.name in ADJACENT_BUFFER]
    dealers = [u for u in chosen if not any(u is a for a in amps)]
    carry = dealers[0] if dealers else chosen[0]
    team[1] = carry
    left = [u for u in chosen if u is not carry]

    def take(pred) -> Unit | None:
        for u in left:
            if pred(u):
                left.remove(u)
                return u
        return None

    ctypes = carry.species.types if carry.species else ()
    below = take(lambda u: ABOVE_TRIGGER.get(u.name) in ctypes)
    if below:
        team[4] = below
    front = take(lambda u: u.name in IN_FRONT_GIVER)
    if front:
        team[0] = front
    behind = take(lambda u: u.name in BEHIND_GIVER)
    if behind:
        team[2] = behind
    # second dealer with its own helpers in the other column pairs
    for u in sorted(left, key=power, reverse=True):
        free = [i for i in (2, 0, 4, 5, 3) if team[i] is None]
        if not free:
            break
        if u.name in ADJACENT_BUFFER:
            best = max(free, key=lambda i: sum(1 for j in neighbours(i) if team[j] is not None))
        else:
            best = free[0]
        team[best] = u
    return team, rest


def layout_to_slots(team: list[Unit | None], rest: list[Unit | None]) -> tuple[list, list]:
    bench = list(rest[:data.BENCH_SLOTS]) + [None] * (data.BENCH_SLOTS - len(rest[:data.BENCH_SLOTS]))
    return list(team), bench


def improve(team: list[Unit | None], bench: list[Unit | None], scorer, max_rounds: int = 3):
    """Hill-climb over swaps of the 10 slots; scorer(team) -> float, higher is better."""
    team, bench = list(team), list(bench)
    best = scorer(team)
    for _ in range(max_rounds):
        improved = False
        slots = [("t", i) for i in range(6)] + [("b", i) for i in range(len(bench))]
        for a, b in combinations(slots, 2):
            if a[0] == "b" and b[0] == "b":
                continue
            ua = team[a[1]] if a[0] == "t" else bench[a[1]]
            ub = team[b[1]] if b[0] == "t" else bench[b[1]]
            if ua is None and ub is None:
                continue
            if ua is not None and ub is not None and ua == ub:
                continue
            if (ua is not None and ua.name is None) or (ub is not None and ub.name is None):
                continue            # a monster the reader cannot name stays where it is
            if (a[0] == "t" and bench_only(ub)) or (b[0] == "t" and bench_only(ua)):
                continue            # never move an egg or Dirgefin onto the team
            t2, b2 = list(team), list(bench)
            (t2 if a[0] == "t" else b2)[a[1]] = ub
            (t2 if b[0] == "t" else b2)[b[1]] = ua
            if t2 == team:
                continue
            v = scorer(t2)
            if v > best + 1e-9:
                team, bench, best = t2, b2, v
                improved = True
        if not improved:
            break
    return team, bench, best
