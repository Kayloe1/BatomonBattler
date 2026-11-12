"""Load the Batopedia data in data/ into per-level battle numbers.

Only what matters inside a battle is parsed: cooldown, the active stats (Deal, Heal, Shield,
Poison, Burn, Shock, Multicast) and the number that drives each battle passive. Shop-phase
passives (Guardiant, Brawlmantis, Gildshell...) are kept as text but have no battle effect.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

STATS = ("damage", "heal", "shield", "poison", "burn", "shock")

# Trainer HP per day, read from the HP bar (docs/step2-screen-map.md; days 9 to 13 from the
# older Kayloe1/batomon notes, build 25448953).
DAY_HP = {1: 300, 2: 500, 3: 800, 4: 1400, 5: 2400, 6: 3800, 7: 5700, 8: 8300,
          9: 11600, 10: 17300, 11: 24900, 12: 34700, 13: 47300}

# Units that are not in the Batopedia CSVs. GUESS: the Dragon Egg (event reward) was seen dealing
# 1 damage and triggering once in a ~19 s battle, so its cooldown is somewhere in 9.5-19 s.
EXTRA_UNITS = {
    "Dragon Egg": {"cost": 0, "rarity": "Common", "types": ["Dragon"], "cooldown": 10.0,
                   "active": "Deal 1 damage", "passive": ""},
}

# How to find each battle passive's number in its text. The first pattern that matches wins.
# A level whose text has no passive part keeps the previous level's number.
PASSIVE_PATTERNS: dict[str, list[str]] = {
    "Mosslug": [r"\+(\d+) Damage"],
    "Pebbler": [r"\+(\d+) Shield"],
    "Boomagon": [r"\+(\d+)%"],
    "Noxnimbus": [r"\+(\d+) Poison"],
    "Runerock": [r"[Rr]emove (\d+)"],
    "Aster": [r"\+(\d+) Heal"],
    "Cherubble": [r"Protect (\d+)"],
    "Dracana": [r"by (\d+) second", r"[Cc]harge \D*?(\d+)s"],
    "Formiqueen": [r"\+(\d+)%"],
    "Ironcore": [r"by (\d+) second", r"[Cc]harge \D*?(\d+)s"],
    "Lignite": [r"(\d+) times", r"(\d+)x"],
    "Magmalith": [r"\+(\d+) Burn"],
    "Noxalith": [r"\+(\d+) Poison"],
    "Stalagrove": [r"(\d+)%"],
    "Thorntail": [r"\+(\d+)"],
    "Aegistruct": [r"(\d+)x"],
    "Clawnetic": [r"by ([\d.]+) second"],
    "Fumungus": [r"(\d+)%"],
    "Prismagon": [r"\+(\d+)"],
    "Pylong": [r"\+(\d+)%"],
    "Shelldra": [r"\+(\d+) Multicast"],
    "Sirenade": [r"(\d+)%"],
    "Zephyrex": [r"\+(\d+) Multicast"],
    "Blixie": [r"(\d+)x"],
    "Cobrex": [r"by (\d+) second"],
    "Draconarch": [r"by (\d+)", r"\+(\d+) per cast"],
    "Gaiadrasil": [r"(\d+)%"],
    "Galvanine": [r"\+(\d+) Shock"],
    "Geminiss": [r"\+(\d+)%"],
    "Onsetra": [r"(\d+) (?:additional|extra)"],
    "Saberhorn": [r"\+(\d+) Multicast"],
    "Stellagon": [r"\+(\d+)"],
    "Dribblet": [r"\+(\d+) Damage"],
    "Panbud": [r"\+(\d+) Damage"],
    "Scorchimp": [r"\+(\d+)%"],
}
# Used when no number is written ("equal to the Shield of adjacent allies" means 1x).
PASSIVE_DEFAULTS = {"Aegistruct": 1.0, "Blixie": 1.0, "Clawnetic": 1.0, "Cobrex": 1.0}
# Passives that only exist once the monster has evolved (level 3 and up).
EVOLVES = {"Dribblet": "Dribblet", "Panbud": "Bambudo", "Scorchimp": "Sunsage"}
EVOLVED_NAMES = {"Bambudo": "Panbud", "Sunsage": "Scorchimp"}


@dataclass
class Level:
    cooldown: float
    stats: dict[str, float]
    multicast: int
    passive_text: str
    param: float | None


@dataclass
class Species:
    name: str
    cost: int
    rarity: str
    types: list[str]
    passive: str
    levels: dict[int, Level] = field(default_factory=dict)

    @property
    def is_ongoing(self) -> bool:
        return self.passive.startswith("Ongoing")

    def has_ability(self) -> bool:
        return bool(self.passive.strip())


def parse_active(text: str) -> tuple[dict[str, float], int, float | None]:
    stats = {s: 0.0 for s in STATS}
    for key, pat in (("damage", r"Deal (\d+)"), ("heal", r"Heal (\d+)"),
                     ("shield", r"Shield (\d+)"), ("poison", r"Poison (\d+)"),
                     ("burn", r"Burn (\d+)"), ("shock", r"Shock (\d+)")):
        m = re.search(pat, text)
        if m:
            stats[key] = float(m.group(1))
    m = re.search(r"Multicast (\d+)", text)
    multicast = int(m.group(1)) if m else 1
    m = re.search(r"CD ([\d.]+)s", text)
    cooldown = float(m.group(1)) if m else None
    return stats, multicast, cooldown


def find_param(name: str, text: str) -> float | None:
    for pat in PASSIVE_PATTERNS.get(name, []):
        m = re.search(pat, text)
        if m:
            return float(m.group(1))
    return None


def _strip_prefix(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^EVOLVED\s*\w*\s*:?\s*", "", text)
    text = re.sub(r"^[A-Z][a-z]+:\s*", "", text)   # "Bambudo: Deal 150"
    return text


@lru_cache(maxsize=1)
def load_species() -> dict[str, Species]:
    out: dict[str, Species] = {}
    with open(DATA / "batomon_pantra.csv", newline="", encoding="utf-8") as f:
        base_rows = list(csv.DictReader(f))
    with open(DATA / "batomon_pantra_levels.csv", newline="", encoding="utf-8") as f:
        level_rows = {r["name"]: r for r in csv.DictReader(f)}
    rows = [dict(r) for r in base_rows]
    for name, e in EXTRA_UNITS.items():
        rows.append({"name": name, "cost": e["cost"], "rarity": e["rarity"],
                     "types": "/".join(e["types"]), "cooldown_s": e["cooldown"],
                     "active": e["active"], "passive": e["passive"]})
    for r in rows:
        name = r["name"]
        sp = Species(name, int(r["cost"]), r["rarity"], r["types"].split("/"), r["passive"] or "")
        stats, mc, _ = parse_active(r["active"] or "")
        cd = float(r["cooldown_s"])
        param = find_param(name, sp.passive)
        if param is None:
            param = PASSIVE_DEFAULTS.get(name)
        sp.levels[1] = Level(cd, stats, mc, sp.passive, param)
        prev = sp.levels[1]
        lv = level_rows.get(name)
        for n in (2, 3, 4):
            if not lv:
                sp.levels[n] = prev
                continue
            text = lv[f"lv{n}"]
            active_part, _, passive_part = text.partition("|")
            active_part = _strip_prefix(active_part)
            if active_part.strip().lower() == "same":
                stats, mc, cd_new = dict(prev.stats), prev.multicast, None
            else:
                stats, mc, cd_new = parse_active(active_part)
            p_text = passive_part.strip()
            # "Brawlmantis, Deal 100 | On Victory..." or "same passive +20%"
            p_param = find_param(name, p_text) if p_text else None
            if p_param is None and name in EVOLVES and n >= 3:
                p_param = find_param(name, active_part + " " + p_text)
            if p_param is None:
                p_param = prev.param if prev.param is not None else PASSIVE_DEFAULTS.get(name)
            level = Level(cd_new if cd_new else prev.cooldown, stats, mc,
                          p_text or prev.passive_text, p_param)
            sp.levels[n] = level
            prev = level
        out[name] = sp
    return out


def species(name: str) -> Species:
    all_ = load_species()
    if name in all_:
        return all_[name]
    if name in EVOLVED_NAMES:
        return all_[EVOLVED_NAMES[name]]
    raise KeyError(f"unknown Batomon: {name!r}")


def canonical_name(name: str) -> str:
    return EVOLVED_NAMES.get(name, name)
