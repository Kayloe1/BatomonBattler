"""Choices outside the shop: trainer at the start of a run, trinket from a gift.

Trainer: Ed's own record per trainer from the Batopedia (data/trainers.csv: runs
won / runs played, read 2026-11-11), smoothed so one lucky run does not dominate,
minus trainers whose ability works against the engine's plan (qualitative lessons
from the September notes, no numbers): Mad Scientist replaces the whole team with
random monsters mid-run, Gentleman removes the cheap monsters merges are built from.

Trinket: each offered trinket is added to the team's trinkets and the team is
scored against today's and tomorrow's opponents in the simulator; the trinket that
helps most wins. Trinkets whose effect is outside battles (income, sell value) get
a money value instead, since the simulator cannot see them.
"""
from __future__ import annotations

import csv
import re

import knowledge

from . import data
from .model import RunState
from .planner import Planner

AVOID_TRAINERS = knowledge.AVOID_TRAINERS
PREFERENCE_BONUS = 0.05     # small tie-breaker for trainers that did well in September


def trainer_scores() -> dict[str, float]:
    out = {}
    with open(data.DATA / "trainers.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            won = int(r.get("ed_championships") or 0)
            played = int(r.get("ed_games_played") or 0)
            score = (won + 1) / (played + 3)          # smoothed win share
            if r["name"] in AVOID_TRAINERS:
                score -= 1.0
            if r["name"] in knowledge.TRAINER_PREFERENCE:
                score += PREFERENCE_BONUS
            out[r["name"]] = score
    return out


def pick_trainer(offered: list[str | None]) -> tuple[int, str]:
    scores = trainer_scores()
    best = max(range(len(offered)), key=lambda k: scores.get(offered[k] or "", 0.2))
    name = offered[best] or f"card {best}"
    return best, f"{name}: Ed's record and fit with the plan (scores {[round(scores.get(o or '', 0.2), 2) for o in offered]})"


_INCOME = re.compile(r"Increase Income by \$(\d+)")
_SIM_SOURCE = (data.DATA.parent / "sim" / "battle.py")


def sim_knows(name: str) -> bool:
    """Trinkets the simulator applies in battle (it names them in its source)."""
    try:
        return f'"{name}"' in _SIM_SOURCE.read_text(encoding="utf-8")
    except OSError:
        return False


# Trinkets that act in the shop (next buy, sell value, rerolls...) are invisible to the
# simulator. They get a small prior from their wording so they are not all scored zero.
_PRIOR_WORDS = [("permanently", 0.02), ("Multicast", 0.02), ("Cooldown Speed", 0.012), ("Damage", 0.01),
                ("free", 0.01), ("Trinket gift", 0.01), ("reroll", 0.006), ("Sell Value", 0.004)]
RARITY_PRIOR = {"Common": 0.0, "Uncommon": 0.004, "Rare": 0.008, "Super Rare": 0.012, "Legendary": 0.016}


def text_prior(name: str) -> float:
    t = data.trinkets().get(name, {})
    effect = t.get("effect", "")
    return RARITY_PRIOR.get(t.get("rarity"), 0.0) + sum(v for w, v in _PRIOR_WORDS if w in effect)


def pick_trinket(planner: Planner, s: RunState, offered: list[str | None]) -> tuple[int, str]:
    team, _ = planner.final_layout(s)
    k = planner.p.k_final
    base = planner.team_score(s, team, k)
    days_left = max(1, data.BADGES_TO_WIN - s.badges)
    results = []
    for j, name in enumerate(offered):
        if not name:
            results.append((-1.0, j, "unreadable"))
            continue
        effect = data.trinkets().get(name, {}).get("effect", "")
        t = s.copy()
        t.trinkets = s.trinkets + [name]
        gain = planner.team_score(t, team, k) - base
        if not sim_knows(name):
            gain += text_prior(name)
        m = _INCOME.search(effect)
        if m:
            gain += planner.p.money * int(m.group(1)) * days_left
        results.append((gain, j, f"{name} {gain:+.3f}"))
    results.sort(reverse=True)
    return results[0][1], "; ".join(r[2] for r in results)
