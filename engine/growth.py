"""Permanent growth from battles, carried to the next day (offline only).

In the game the reader sees every badge, so live play needs none of this. Offline
(ghost opponents and engine/runsim.py), teams would otherwise never grow from
fighting, which made late opponents too weak: real players' Bambudo, Prismagon,
Thorntail, Magmalith/Noxalith and Aster teams grow every battle.

Growth is read from the simulator: a stat that rose during the battle is kept when
the team has a source that grows it permanently, and dropped when the only source is
"for this battle" (Mosslug, Pebbler, Galvanine, Stalagrove, Noxnimbus, Blixie...).
"""
from __future__ import annotations

from sim.battle import simulate

from .model import Unit

# stat -> monsters whose permanent effects can raise it (on themselves or allies)
PERMANENT_SOURCES = {
    "damage": {"Panbud", "Bambudo", "Prismagon", "Thorntail", "Dribblet", "Emperooze"},
    "heal": {"Aster", "Dribblet", "Emperooze"},
    "burn": {"Magmalith"},
    "poison": {"Noxalith"},
}
# monsters whose own gains are only for the battle
TEMPORARY_SELF = {"Mosslug", "Pebbler", "Galvanine", "Stalagrove", "Shelldra"}
# temporary gifts to allies, by stat
TEMPORARY_GIVERS = {"poison": {"Noxnimbus"}, "burn": {"Blixie"}, "shield": {"Geminiss", "Aegistruct"}}

FIGHT_SECONDS = 25.0


def _grows(team: list[Unit | None], stat: str) -> bool:
    names = {u.name for u in team if u}
    src = PERMANENT_SOURCES.get(stat, set())
    if not names & src:
        return False
    if stat == "damage" and names & {"Panbud", "Dribblet"}:
        # only the evolved (level 3+) forms grow
        return any(u and u.name in src and (u.name not in ("Panbud", "Dribblet") or u.level >= 3) for u in team)
    return True


def carry(team: list[Unit | None], end_units: list[dict]) -> list[Unit | None]:
    """Team after a battle: permanent stat gains from end_units (sim summaries) kept."""
    by_slot = {d["slot"] - 1: d for d in end_units}
    out = list(team)
    names = {u.name for u in team if u}
    for i, u in enumerate(team):
        if u is None or i not in by_slot or u.name in TEMPORARY_SELF:
            continue
        end = by_slot[i].get("stats", {})
        d = u.stat_dict()
        changed = False
        for stat in ("damage", "heal", "burn", "poison"):
            gain = end.get(stat, 0) - d.get(stat, 0)
            if gain <= 0 or not _grows(team, stat):
                continue
            if names & TEMPORARY_GIVERS.get(stat, set()):
                continue                     # cannot tell permanent from temporary: keep nothing
            d[stat] += gain
            changed = True
        if changed:
            out[i] = u.with_stats(d)
    return out


def after_mirror_battle(team: list[Unit | None], spec: dict) -> list[Unit | None]:
    """Growth from a typical-length battle (used for ghosts, which have no real fight)."""
    if not any(_grows(team, s) for s in PERMANENT_SOURCES):
        return team
    r = simulate(spec, spec, immortal=True, until=FIGHT_SECONDS)
    return carry(team, r.units[0])
