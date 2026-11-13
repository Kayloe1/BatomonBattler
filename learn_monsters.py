"""Learn monsters the bot cannot name, from the info panel the game shows when one is hovered.

An event can give a monster of another region ("Gain a foreign Rare monster"), and some events give
event-only monsters. Neither is in data/batomon_pantra.csv, so the reader cannot name it and the engine
played it as the "Unknown Rare" stand-in. play.py calls learn_unknown() on the shop screen: it hovers
each unnamed team/bench monster once, reads the panel (reader.read_info_panel) and

* if the name is new: appends it to data/foreign_monsters.csv (rarity, type, cooldown, active numbers,
  a typical price for the rarity; the passive is left empty and the saved panel picture is named in
  the source column, so a person can read it), and saves its sprite;
* if the name is known (the sprite just was not recognised, e.g. a Shiny or a new pose): saves the sprite.

The engine, simulator and reader caches are cleared so the next look names it.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FOREIGN = ROOT / "data" / "foreign_monsters.csv"
TYPICAL_COST = {"Common": 10, "Uncommon": 25, "Rare": 30, "Super Rare": 40, "Legendary": 50}
STAT_WORDS = [("damage", "Deal {} damage"), ("heal", "Heal {}"), ("shield", "Shield {}"),
              ("poison", "Poison {}"), ("burn", "Burn {}"), ("shock", "Shock {}")]


def _is_dragon_egg(slot: dict) -> bool:
    stats = {b.get("stat"): b.get("value") for b in slot.get("stats") or []}
    return (slot.get("level") or 1) == 1 and {k: v for k, v in stats.items() if v and k != "multicast"} == {"damage": 1}


def unnamed_slots(state: dict) -> list[tuple[str, int]]:
    out = []
    for where in ("team", "bench"):
        for i, s in enumerate(state.get(where) or []):
            if s and s.get("name") is None and s.get("stats") and not _is_dragon_egg(s):
                out.append((where, i))
    return out


def active_text(stats: dict) -> str:
    return "; ".join(fmt.format(stats[k]) for k, fmt in STAT_WORDS if stats.get(k))


def add_monster(panel: dict, path: Path = FOREIGN) -> bool:
    """Append a newly seen monster to the foreign list. False if it is there already or incomplete."""
    name, rarity, cd = panel.get("name"), panel.get("rarity"), panel.get("cooldown")
    if not name or not rarity or cd is None or not panel.get("stats"):
        return False
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys()) if rows else ["name", "cost", "rarity", "types", "cooldown_s",
                                                     "active", "passive", "source"]
    if any(r["name"] == name for r in rows):
        return False
    row = {"name": name, "cost": TYPICAL_COST.get(rarity, 30), "rarity": rarity,
           "types": panel.get("type") or "Unknown", "cooldown_s": cd, "active": active_text(panel["stats"]),
           "passive": "",
           "source": (f"Learned by the bot from the hover panel; passive NOT read yet (read it from "
                      f"{panel.get('capture')}). Cost is a typical {rarity}'s.")}
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=fields).writerow(row)
    return True


def forget_caches() -> None:
    """Make the engine, the simulator and the reader see a newly added monster."""
    import reader
    from engine import data as edata
    from sim import data as sdata
    edata.roster.cache_clear()
    sdata.load_species.cache_clear()
    with open(FOREIGN, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["name"] not in reader.MONSTER_NAMES:
                reader.MONSTER_NAMES.append(r["name"])


def learn_unknown(h, state: dict, tried: set) -> list[str]:
    """Hover each unnamed monster once (per slot and badges) and learn what its panel says.
    Returns lines for the run's commentary; empty when there was nothing to do."""
    import reader
    lines = []
    for where, i in unnamed_slots(state):
        slot = state[where][i]
        key = (where, i, repr(slot.get("stats")), slot.get("level"))
        if key in tried:
            continue
        tried.add(key)
        panel = h.inspect(where, i)
        if not panel or not panel.get("name"):
            lines.append(f"{where} slot {i + 1}: hovered an unknown monster, but could not read its panel "
                         f"({(panel or {}).get('raw')})")
            continue
        name = panel["name"]
        new = name not in reader.MONSTER_NAMES and add_monster(panel)
        reader.learn_sprite(name, panel["slot_rgb"])
        if new:
            forget_caches()
            lines.append(f"Learned a new monster from its panel: {name} ({panel['rarity']}, {panel.get('type')}, "
                         f"{panel['cooldown']} s, {active_text(panel['stats'])}); its passive is not read yet "
                         f"(picture: {panel.get('capture')})")
        else:
            lines.append(f"{where} slot {i + 1} is {name} (its picture was not recognised; saved it)")
    return lines
