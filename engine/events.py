"""Weigh the choices of an event and pick the best one for the current team.

Each choice shows an effect line ("Gain $40", "Get a Rare trinket gift", "Level up a monster
(max level 4)"...). The line is turned into an effect and scored on the same scale as shop
decisions (planner.team_score: today's and the next days' battles in the simulator):

- money: what the planner counts a dollar as;
- a trinket gift: the planner's value of a gift of that rarity;
- a level-up, a stat boost or a monster the data knows: simulated on the current team;
- things the data does not know (event-only trinkets and monsters): a small fixed guess.

On top comes a bonus or a veto from the qualitative lessons in knowledge.EVENT_EFFECT_NOTES.
Every score comes back with its reason, so play.py can explain the choice. Guessed values are
marked "guess": they are the first thing to correct from real run results.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import knowledge

from . import data, model
from .model import RunState
from .planner import GIFT_VALUE, Planner

UNKNOWN_GAIN = 0.05        # GUESS: an event-only trinket or monster the data does not describe
PREFER_BONUS = 0.12        # a choice the September lessons call the good one (qualitative, my weight)
VETO = -9.0
RANDOM_SAMPLES = 4


@dataclass
class Scored:
    index: int
    effect: str | None
    value: float
    why: str
    guess: bool = False


def _key(text: str) -> str:
    """Compare texts with capital I and lowercase l treated as the same glyph."""
    return text.replace("I", "l").lower()


def _has(effect: str, words: str) -> bool:
    return _key(words) in _key(effect)


def _team_gain(planner: Planner, s: RunState, t: RunState) -> float:
    k = planner.p.k_final
    team0, _ = planner.final_layout(s)
    team1, _ = planner.final_layout(t)
    return planner.team_score(t, team1, k) - planner.team_score(s, team0, k)


def _with_unit(s: RunState, unit) -> RunState | None:
    t = s.copy()
    for where, slots in ((model.TEAM, t.team), (model.BENCH, t.bench)):
        for i, u in enumerate(slots):
            if u is None:
                t.set_slot(where, i, unit)
                return t
    return None


def _level_up(u):
    sp = u.species
    if sp is None or u.level >= 4:
        return None
    d = u.stat_dict()
    lo, hi = sp.stats(u.level), sp.stats(u.level + 1)
    for k, v in hi.items():
        if k == "multicast":
            d[k] = max(d.get(k, 1), v)
        else:
            d[k] = d.get(k, 0) + v - lo.get(k, 0)      # permanent growth is kept
    return model.replace(u.with_stats(d), level=u.level + 1)


def _make_shiny(u):
    """The same monster as a Shiny copy (what Shiny changes is in sim.battle SHINY_*)."""
    return None if u.shiny or u.species is None else model.replace(u, shiny=True)


def _best_single_change_unit(planner: Planner, s: RunState, change):
    """(gain, unit) of the owned monster that gains most from change(unit); (0.0, None) if none does."""
    best, who = 0.0, None
    for w, k, u in s.owned():
        v = change(u)
        if v is None:
            continue
        t = s.copy()
        t.set_slot(w, k, v)
        g = _team_gain(planner, s, t)
        if g > best:
            best, who = g, u
    return best, who


def _best_single_change(planner: Planner, s: RunState, change) -> tuple[float, str | None]:
    g, u = _best_single_change_unit(planner, s, change)
    return g, (u.name if u else None)


def _shock(n: int):
    def change(u):
        d = u.stat_dict()
        d["shock"] += n
        return u.with_stats(d)
    return change


def best_target(planner: Planner, s: RunState, effect: str | None):
    """The owned monster an event effect should be put on, with the reason: (Unit or None, why).

    Level-ups and +Shock go where the simulator gains most. For effects it cannot model (shiny...)
    the strongest monster is taken: the September lessons say to put such boosts on the carry.
    """
    from .arrange import power
    effect = effect or ""
    unit = None
    if _has(effect, "Level up a monster"):
        _, unit = _best_single_change_unit(planner, s, _level_up)
        why = "levelling it improves the simulated battles most"
    elif _has(effect, "SHINY"):
        _, unit = _best_single_change_unit(planner, s, _make_shiny)
        why = "its Shiny effect improves the simulated battles most"
    else:
        m = re.search(r"\+(\d+) Shock", effect)
        if m:
            _, unit = _best_single_change_unit(planner, s, _shock(int(m.group(1))))
            why = f"+{m.group(1)} Shock helps it most in the simulator"
    if unit is None:
        owned = [u for _, _, u in s.owned()]
        unit = max(owned, key=power, default=None)
        why = "it is my strongest monster, and boosts belong on the carry"
    return unit, why


def unit_signature(level, stats: dict) -> tuple:
    """What identifies a monster on a screen where its name may not be readable."""
    return (level or 1, tuple(sorted((k, int(v)) for k, v in stats.items() if v and k != "multicast")))


def find_on_screen(unit, state: dict) -> tuple[str, int] | None:
    """Where the unit sits on the "Select a target" screen: same name if readable, same level and badges."""
    if unit is None:
        return None
    want = unit_signature(unit.level, unit.stat_dict())
    fallback = None
    for where in ("team", "bench"):
        for i, slot in enumerate(state.get(where) or []):
            if not slot:
                continue
            got = unit_signature(slot.get("level"), {b.get("stat"): b.get("value") or 0 for b in slot.get("stats", [])})
            if got == want:
                if slot.get("name") in (None, unit.name):
                    return (where, i)
                fallback = fallback or (where, i)
    return fallback


def score_effect(planner: Planner, s: RunState, effect: str) -> tuple[float, str, bool]:
    """(value, reason, is_guess) of one effect line."""
    m = re.search(r"Gain \$(\d+)", effect)
    if m:
        n = int(m.group(1))
        return planner.p.money * n, f"${n} at the planner's value of money", False
    m = re.search(r"Get a (.+) trinket gift", effect)
    if m:
        v = planner.p.gift_scale * GIFT_VALUE.get(m.group(1), 0.03)
        return v, f"a {m.group(1)} trinket gift (the planner's value of that gift)", False
    if _has(effect, "Level up a monster"):
        g, who = _best_single_change(planner, s, _level_up)
        if who:
            return g, f"levelling {who} improves the simulated battles most", False
        return 0.0, "no monster to level", False
    if _has(effect, "Turn a monster SHINY"):
        g, who = _best_single_change(planner, s, _make_shiny)
        if who:
            return g, f"a Shiny {who} improves the simulated battles most", False
        return 0.0, "no monster gains from Shiny in the simulator", False
    if _has(effect, "Mysterious Charm"):
        # "[Unique] +25% HP" (seen on the last-life rescue, 2026-11-12)
        if "Mysterious Charm" in s.trinkets:
            return 0.0, "the Mysterious Charm is unique and I already have it", False
        t = s.copy()
        t.trinkets = s.trinkets + ["Mysterious Charm"]
        if s.hp_today:
            t.hp_today = int(s.hp_today * 1.25)
        team, _ = planner.final_layout(s)
        k = planner.p.k_final
        return (planner.team_score(t, team, k) - planner.team_score(s, team, k),
                "Mysterious Charm (+25% HP) in the simulator", False)
    m = re.search(r"\+(\d+) Shock", effect)
    if m:
        n = int(m.group(1))

        def shock(u):
            d = u.stat_dict()
            d["shock"] += n
            return u.with_stats(d)
        g, who = _best_single_change(planner, s, shock)
        return g, (f"+{n} Shock on {who} in the simulator" if who else "no monster gains from Shock"), False
    if _has(effect, "random level"):
        m = re.search(r"(\d) (.+) monster", effect)
        level = int(m.group(1)) if m else 2
        rarity = m.group(2).strip() if m else "Rare"
        pool = sorted(data.by_rarity(rarity), key=lambda sp: sp.name)
        if pool:
            step = max(1, len(pool) // RANDOM_SAMPLES)
            gains = []
            for sp in pool[::step][:RANDOM_SAMPLES]:
                t = _with_unit(s, model.new_unit(sp.name, sp.cost, level))
                gains.append(_team_gain(planner, s, t) if t else 0.0)
            return sum(gains) / len(gains), f"average of {len(gains)} sample level {level} {rarity} monsters added to the team", False
    m = re.match(r"Gain (.+)$", effect)
    if m:
        name = m.group(1).strip()
        known = next((n for n in data.roster() if _key(n) == _key(name)), None)
        if known or _key(name) == _key("Dragon Egg"):
            if known:
                sp = data.species(known)
                t = _with_unit(s, model.new_unit(known, sp.cost, 1))
                return (_team_gain(planner, s, t) if t else 0.0), f"{known} added to the team in the simulator", False
            return 0.0, "the egg does nothing in battle until it hatches", False
        trinket = next((n for n in data.trinkets() if _key(n) == _key(name)), None)
        if trinket:
            from .choices import _HP, with_trinket_stats
            t = s.copy()
            t.trinkets = s.trinkets + [trinket]
            hp = _HP.search(data.trinkets()[trinket].get("effect", ""))
            if hp and t.hp_today:                 # Dryad's Charm, Mysterious Charm, Barbell...
                n = int(hp.group(1))
                t.hp_today = int(t.hp_today * (1 + n / 100)) if hp.group(2) else t.hp_today + n
            team, _ = planner.final_layout(s)
            k = planner.p.k_final
            return (planner.team_score(t, with_trinket_stats(team, trinket, s.trinkets), k)
                    - planner.team_score(s, team, k)), f"trinket {trinket} in the simulator", False
        return UNKNOWN_GAIN, f"'{name}' is not in my data yet, so a small fixed guess", True
    return UNKNOWN_GAIN, "an effect I cannot model yet, so a small fixed guess", True


def score_choices(planner: Planner, s: RunState, effects: list[str | None]) -> list[Scored]:
    out = []
    for i, effect in enumerate(effects):
        if not effect:
            out.append(Scored(i, None, -1.0, "could not read this choice", True))
            continue
        try:
            v, why, guess = score_effect(planner, s, effect)
        except Exception as e:            # a modelling bug must not stop a run
            v, why, guess = UNKNOWN_GAIN, f"could not be simulated ({type(e).__name__}), so a small fixed guess", True
        for words, sign, note in knowledge.EVENT_EFFECT_NOTES:
            if _has(effect, words):
                if sign < 0:
                    v, why, guess = VETO, note, False
                else:
                    v += PREFER_BONUS
                    why += f"; plus a bonus because {note}"
                break
        out.append(Scored(i, effect, v, why, guess))
    return out


def pick(planner: Planner, s: RunState, effects: list[str | None]) -> tuple[int, list[str]]:
    """Index of the best choice and the lines that explain it."""
    scored = score_choices(planner, s, effects)
    readable = [c for c in scored if c.effect]
    if not readable:
        k = len(effects) - 1
        return k, [f"Event: I could not read any choice, so I take the last one (choice {k + 1}), the old fixed rule."]
    best = max(readable, key=lambda c: c.value)
    lines = ["Event choices (same scale as shop decisions, bigger is better):"]
    for c in scored:
        mark = "   <-- my choice" if c is best else ""
        val = "never" if c.value <= VETO / 2 else f"{c.value:+.2f}"
        text = c.effect or "(unreadable)"
        lines.append(f"   {val}  {text}: {c.why}{' [guess]' if c.guess and c.effect else ''}{mark}")
    lines.append(f"Decision: {best.effect}.")
    return best.index, lines
