"""Whole-run practice environment: shop rolls, gold, rerolls, merges, gifts, days, lives.

It wraps the pieces the engine already has (engine/model.py for the shop, engine/growth.py
for growth between battles, sim/ for fights) in one function, `play_run`, that any policy with
`play_shop(state, rng)` can use. Opponents come from an `OppSource`, which mixes three kinds of
teams, all of them snapshots like in the real game (you fight a stored team for your day):

  ghosts    the synthetic teams of engine/opponents.py (guessed skill levels);
  league    teams that earlier generations of the learner itself built on that day (self-play);
  recorded  real opponent teams the bot logged (data/opponents_recorded.jsonl), the only
            kind that is not a guess. They get the largest weight allowed once they exist.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from engine import data, growth, model, opponents
from engine.evaluate import team_spec
from engine.model import RunState
from sim.battle import simulate

MAX_DAYS = 20


@dataclass
class OppSource:
    ghosts: dict[int, list[dict]]
    league: dict[int, list[dict]] = field(default_factory=dict)
    recorded: dict[int, list[dict]] = field(default_factory=dict)
    p_ghost: float = 0.5
    p_league: float = 0.35
    p_recorded: float = 0.30        # used only on days that have recorded teams

    def sample(self, day: int, rng: random.Random) -> dict:
        d = min(day, max(self.ghosts))
        rec = self.recorded.get(d) or []
        lg = self.league.get(d) or []
        w_rec = self.p_recorded if rec else 0.0
        w_lg = self.p_league if lg else 0.0
        w_gh = self.p_ghost
        x = rng.random() * (w_rec + w_lg + w_gh)
        if x < w_rec:
            return rng.choice(rec)
        if x < w_rec + w_lg:
            return rng.choice(lg)
        return rng.choice(self.ghosts[d])


def _gift(rarity: str, rng: random.Random) -> str | None:
    opts = [n for n, t in data.trinkets().items() if t["rarity"] == rarity]
    return rng.choice(opts) if opts else None


def play_run(policy, seed: int, source: OppSource, snapshots: bool = False) -> dict:
    """One run from day 1 until 10 badges, or until the last life is gone (one rescue)."""
    rng = random.Random(seed)
    shop_rng = random.Random(seed * 7 + 1)
    s = RunState(day=1, money=0, rank=1)
    arc, snaps = [], {}
    locked = None
    for day in range(1, MAX_DAYS + 1):
        s.day = s.rank = day
        s.money += data.income(day)
        s.items_left = 1
        s.gifts = []
        s.shop = locked if locked else model.random_shop(day, shop_rng)
        s.locked = False
        s = policy.play_shop(s, shop_rng)
        for r in s.gifts:
            t = _gift(r, rng)
            if t:
                s.trinkets.append(t)
        s.gifts = []
        base_hp = data.hp_for_day(day)
        mine = team_spec(s.team, int(base_hp * (1.25 if s.rescue_used else 1)), s.trainer, s.trinkets)
        if snapshots and any(mine["slots"]):
            snaps[day] = team_spec(s.team, base_hp, s.trainer, s.trinkets)
        opp = dict(source.sample(day, rng))
        opp["hp"] = base_hp
        r = simulate(mine, opp, seed=rng.randrange(1 << 30)) if any(mine["slots"]) else None
        won = r is not None and r.winner == "a"
        if r is not None:
            s.team = growth.carry(s.team, r.units[0])
        if won:
            s.badges += 1
        else:
            s.lives -= data.lives_lost(day)
        arc.append("W" if won else "L")
        out = {"seed": seed, "badges": s.badges, "day": day, "arc": "".join(arc), "snaps": snaps}
        if s.badges >= data.BADGES_TO_WIN:
            return {**out, "won": True}
        if s.lives <= 0:
            if s.rescue_used:
                return {**out, "won": False}
            s.rescue_used, s.lives = True, 1
    return {"seed": seed, "badges": s.badges, "day": MAX_DAYS, "arc": "".join(arc), "snaps": snaps, "won": False}
