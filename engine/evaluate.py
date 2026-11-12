"""Score a team by playing it against a spread of plausible opponents in the simulator.

Opponents are random snapshots of other players, so a team is judged by its
expected result against a pool of opponent teams for that day (engine/opponents.py),
not against one guess. Every candidate in one decision is scored against the same
opponents and seeds ("common random numbers"), so differences between candidates
are not noise from different draws.

score = share of battles won (draw = half) + MARGIN_WEIGHT x mean HP margin.
The small margin term ranks teams that all win (or all lose) by how close it was.
"""
from __future__ import annotations

from dataclasses import dataclass

from sim.battle import simulate

from . import data
from .model import Unit

MARGIN_WEIGHT = 0.15
# Battles still running after this many seconds are stopped and judged by HP left
# (the simulator calls 300 s a draw). Real battles so far ended in under 30 s;
# stalls only happen between sustain-heavy teams and cost most of the search time.
SCORE_UNTIL = 120.0


def slot_spec(u: Unit | None) -> dict | None:
    if u is None or u.name is None or data.species(u.name) is None:
        return None
    d = u.stat_dict()
    spec = {"name": u.name, "level": u.level,
            "stats": {k: d[k] for k in ("damage", "heal", "shield", "poison", "burn", "shock")}}
    if d.get("multicast", 1) != 1:
        spec["multicast"] = d["multicast"]
    return spec


def team_spec(team: list[Unit | None], hp: int, trainer: str | None = None,
              trinkets: list[str] | None = None) -> dict:
    return {"trainer": trainer or "", "hp": hp, "trinkets": list(trinkets or []),
            "slots": [slot_spec(u) for u in team]}


def team_key(team: list[Unit | None]) -> tuple:
    return tuple((u.name, u.level, u.stats) if u else None for u in team)


@dataclass
class Score:
    win: float
    margin: float
    n: int
    margin_weight: float = MARGIN_WEIGHT

    @property
    def value(self) -> float:
        return self.win + self.margin_weight * self.margin


class Evaluator:
    """Plays teams against opponent pools; caches every result."""

    def __init__(self, pools: dict[int, list[dict]], seeds: int = 1, margin_weight: float = MARGIN_WEIGHT):
        self.margin_weight = margin_weight
        self.pools = pools
        self.seeds = seeds
        self.cache: dict[tuple, tuple[float, float]] = {}
        self.battles = 0

    def pool(self, day: int) -> list[dict]:
        if day in self.pools:
            return self.pools[day]
        known = sorted(self.pools)
        return self.pools[min(known, key=lambda d: abs(d - day))]

    def score(self, team: list[Unit | None], day: int, k: int, *, hp: int | None = None,
              trainer: str | None = None, trinkets: list[str] | None = None) -> Score:
        hp = hp or data.hp_for_day(day)
        pool = self.pool(day)[:k]
        spec = None
        key0 = (team_key(team), day, hp, trainer, tuple(trinkets or ()))
        wins = margin = 0.0
        n = 0
        for j, opp in enumerate(pool):
            for s in range(self.seeds):
                key = key0 + (j, s)
                hit = self.cache.get(key)
                if hit is None:
                    if spec is None:
                        spec = team_spec(team, hp, trainer, trinkets)
                    if not any(spec["slots"]):
                        hit = (0.0, -1.0)
                    else:
                        o = dict(opp)
                        o["hp"] = data.hp_for_day(day)
                        r = simulate(spec, o, seed=s, until=SCORE_UNTIL)
                        self.battles += 1
                        m = r.hp[0] / r.max_hp[0] - r.hp[1] / r.max_hp[1]
                        if r.winner == "none":       # stopped at SCORE_UNTIL: lean by HP left
                            w = 0.5 + max(-0.4, min(0.4, m))
                        else:
                            w = 1.0 if r.winner == "a" else 0.5 if r.winner == "draw" else 0.0
                        hit = (w, m)
                    self.cache[key] = hit
                wins += hit[0]
                margin += hit[1]
                n += 1
        if n == 0:
            return Score(0.0, 0.0, 0)
        return Score(wins / n, margin / n, n, self.margin_weight)
