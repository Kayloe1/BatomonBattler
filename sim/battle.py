"""Offline Batomon battle simulator.

A team is a dict (or the JSON form of one):

    {
      "trainer": "Rich Lady",            # optional
      "hp": 500,                          # trainer HP (or "day": 2 to use the day table)
      "trinkets": ["Rally Flag"],         # optional
      "coffee": false,                    # optional: Coffee item used before this battle
      "slots": [                          # 6 entries: top row left->right, then bottom row
        {"name": "Brawlmantis", "level": 1, "stats": {"damage": 60}},
        null, ...
      ]
    }

A slot's "stats" (the badges on the shop screen) replace the Batopedia numbers when given.
Optional per-slot keys: "cooldown", "multicast", "speed" (% cooldown speed), "protect".

`simulate(team_a, team_b)` plays the battle and returns a BattleResult. Rules and guesses are
listed in sim/rules.py.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from . import data
from .rules import SETTINGS

EPS = 1e-9

# Static trinket bonuses that change a card's badges (applied only when a slot has no "stats").
STATIC_STAT_TRINKETS = {"Wood Sword", "Small Club", "Giant Club", "Terrarium", "Fire Orb",
                        "Poison Orb", "Power Crown"}
STATIC_STAT_TRAINERS = {"Chef", "Chemist", "Musician"}


@dataclass
class Unit:
    side: int
    slot: int
    name: str
    level: int
    types: list[str]
    rarity: str
    cooldown: float
    stats: dict[str, float]
    multicast: int
    passive: str
    param: float | None
    ongoing: bool
    has_ability: bool
    speed: float = 0.0            # % cooldown speed for this battle
    progress: float = 0.0         # seconds of cooldown done
    alive: bool = True
    disabled: bool = False        # abilities disabled (Celestia)
    protect: int = 0
    extra_multicast: int = 0
    shelldra_next: float = 4.0
    casts: int = 0
    triggers: int = 0
    dealt: float = 0.0
    healed: float = 0.0
    shielded: float = 0.0
    inflicted: dict[str, float] = field(default_factory=lambda: {"poison": 0, "burn": 0, "shock": 0})

    @property
    def row(self) -> int:
        return self.slot // 3

    @property
    def col(self) -> int:
        return self.slot % 3

    @property
    def base_name(self) -> str:
        return data.canonical_name(self.name)

    def is_(self, name: str) -> bool:
        return self.base_name == name

    def active_passive(self) -> bool:
        return self.alive and not self.disabled

    def evolved(self) -> bool:
        return self.base_name in data.EVOLVES and self.level >= 3

    def summary(self) -> dict:
        out = {"slot": self.slot + 1, "name": self.name, "level": self.level,
               "triggered": self.triggers, "dealt": round(self.dealt), "healed": round(self.healed)}
        if self.shielded:
            out["shielded"] = round(self.shielded)
        for k, v in self.inflicted.items():
            if v:
                out[f"inflicted_{k}"] = round(v)
        if not self.alive:
            out["knocked_out"] = True
        out["stats"] = {k: round(v) for k, v in self.stats.items() if v}
        return out


@dataclass
class Trainer:
    side: int
    name: str
    max_hp: float
    hp: float
    trinkets: list[str]
    shield: float = 0.0
    poison: float = 0.0
    burn: float = 0.0
    shock: float = 0.0
    heal_mult: float = 1.0
    shield_mult: float = 1.0
    link_cable: bool = False
    metronome: int = 0


@dataclass
class BattleResult:
    winner: str            # "a", "b", "draw", or "none" (stopped early with `until`)
    time: float
    hp: tuple[float, float]
    max_hp: tuple[float, float]
    statuses: tuple[dict, dict]
    units: tuple[list[dict], list[dict]]
    log: list[str]

    def as_dict(self) -> dict:
        return {"winner": self.winner, "time": round(self.time, 2),
                "hp": [round(h) for h in self.hp], "max_hp": list(self.max_hp),
                "statuses": list(self.statuses), "units": list(self.units)}


def build_unit(side: int, slot: int, spec: dict, trainer: str | None, trinkets: list[str]) -> Unit:
    name = spec["name"]
    level = int(spec.get("level", 1))
    sp = data.species(name)
    lv = sp.levels[min(max(level, 1), 4)]
    stats = dict(lv.stats)
    given = spec.get("stats")
    if given:
        stats = {s: float(given.get(s, 0)) for s in data.STATS}
    types = list(sp.types)
    multicast = int(spec.get("multicast", lv.multicast))
    unit = Unit(side, slot, name, level, types, sp.rarity, float(spec.get("cooldown", lv.cooldown)),
                stats, multicast, lv.passive_text if level > 1 else sp.passive, lv.param,
                sp.is_ongoing, sp.has_ability() and not (sp.name in data.EVOLVES and level < 3),
                speed=float(spec.get("speed", 0)), protect=int(spec.get("protect", 0)))
    # Trainer / trinket bonuses that the badges would already show.
    if not given:
        if trainer == "Chef":
            if len(types) == 1 and "Fire" not in types:
                unit.types.append("Fire")
            if "Fire" in unit.types:
                unit.stats["burn"] += 2
        if trainer == "Chemist" and "Toxic" in unit.types:
            unit.stats["poison"] += 3
        for t in trinkets:
            if t == "Wood Sword":
                unit.stats["damage"] += 5
            elif t == "Fire Orb" and "Fire" in unit.types:
                unit.stats["burn"] += 3
            elif t == "Poison Orb" and "Toxic" in unit.types:
                unit.stats["poison"] += 3
            elif t == "Power Crown" and slot == 1:
                unit.stats["damage"] += 20
            elif t == "Terrarium" and "Bug" in unit.types:
                unit.stats["damage"] *= 1.2
            elif t == "Small Club" and unit.cooldown >= 5:
                unit.stats["damage"] *= 1.2
            elif t == "Giant Club" and unit.cooldown >= 5:
                for s in data.STATS:
                    unit.stats[s] *= 1.7
    elif trainer == "Chef" and len(types) == 1 and "Fire" not in types:
        unit.types.append("Fire")
    # Cooldown and Multicast bonuses (not visible on badges).
    if "multicast" not in spec:
        for t in trinkets:
            if t == "Razor Beak" and "Flying" in unit.types:
                unit.multicast += 1
            elif t == "Winged Crown" and slot == 1:
                unit.multicast += 1
    if "speed" not in spec:
        for t in trinkets:
            if t == "Quick Flag" and unit.col == 0:
                unit.speed += 4
            elif t == "Speed Crest" and unit.col == 2:
                unit.speed += 15
            elif t == "Haste Orb":
                unit.speed += 10
            elif t == "Haste Crown" and slot == 1:
                unit.speed += 20
    return unit


class Battle:
    def __init__(self, team_a: dict, team_b: dict, seed: int = 0, verbose: bool = False,
                 until: float | None = None, immortal: bool = False):
        self.until = until
        self.immortal = immortal
        self.rng = random.Random(seed)
        self.verbose = verbose
        self.log: list[str] = []
        self.t = 0.0
        self.trainers = [self._trainer(0, team_a), self._trainer(1, team_b)]
        self.teams: list[list[Unit | None]] = [self._units(0, team_a), self._units(1, team_b)]
        self.coffee = [bool(team_a.get("coffee")), bool(team_b.get("coffee"))]
        self.next_poison = SETTINGS["poison_interval"]
        self.next_burn = SETTINGS["burn_interval"]
        self.depth = 0

    # ---------- setup ----------
    def _trainer(self, side: int, team: dict) -> Trainer:
        hp = team.get("hp")
        if hp is None:
            hp = data.DAY_HP[int(team["day"])]
        trinkets = list(team.get("trinkets", []))
        tr = Trainer(side, team.get("trainer") or "", float(hp), float(team.get("hp_now", hp)), trinkets)
        if "Sapphire Amulet" in trinkets:
            tr.heal_mult = 1.25
        if "Topaz Amulet" in trinkets:
            tr.shield_mult = 1.25
        tr.link_cable = "Link Cable" in trinkets
        tr.metronome = trinkets.count("Metronome")
        return tr

    def _units(self, side: int, team: dict) -> list[Unit | None]:
        slots = list(team.get("slots", []))[:6]
        slots += [None] * (6 - len(slots))
        trainer = team.get("trainer")
        trinkets = list(team.get("trinkets", []))
        out = []
        for i, s in enumerate(slots):
            out.append(build_unit(side, i, s, trainer, trinkets) if s else None)
        if trainer == "Musician" and not any(s and s.get("stats") for s in slots if s):
            electric = [u for u in out if u and "Electric" in u.types]
            if len(electric) == 1:
                electric[0].stats["shock"] *= 2.5
        return out

    def say(self, msg: str) -> None:
        if self.verbose:
            self.log.append(f"{self.t:6.2f}  {msg}")

    # ---------- geometry ----------
    def unit_at(self, side: int, row: int, col: int) -> Unit | None:
        if not (0 <= row < 2 and 0 <= col < 3):
            return None
        return self.teams[side][row * 3 + col]

    def behind(self, u: Unit) -> Unit | None:
        return self.unit_at(u.side, u.row, u.col - 1)

    def in_front(self, u: Unit) -> Unit | None:
        return self.unit_at(u.side, u.row, u.col + 1)

    def above(self, u: Unit) -> Unit | None:
        return self.unit_at(u.side, u.row - 1, u.col) if u.row == 1 else None

    def adjacent(self, u: Unit) -> list[Unit]:
        if self.trainers[u.side].link_cable:
            return [v for v in self.teams[u.side] if v and v is not u]
        cells = [(u.row, u.col - 1), (u.row, u.col + 1), (u.row - 1, u.col), (u.row + 1, u.col)]
        return [v for v in (self.unit_at(u.side, r, c) for r, c in cells) if v]

    def allies(self, u: Unit) -> list[Unit]:
        return [v for v in self.teams[u.side] if v and v is not u]

    def living(self, side: int) -> list[Unit]:
        return [u for u in self.teams[side] if u and u.alive]

    # ---------- ongoing effects ----------
    def ongoing_mult(self, u: Unit) -> int:
        """How many times u's Ongoing ability applies (Onsetra in front of it adds more)."""
        n = 1
        front = self.in_front(u)
        if front and front.is_("Onsetra") and front.active_passive() and front.param:
            n += int(front.param)
        return n

    def ongoing_active(self, u: Unit) -> bool:
        return u.ongoing and u.active_passive()

    def speed_of(self, u: Unit) -> float:
        bonus = u.speed
        for v in self.adjacent(u):
            if v.is_("Formiqueen") and self.ongoing_active(v) and u.rarity == "Common" and v.param:
                bonus += v.param * self.ongoing_mult(v)
        return 1.0 + bonus / 100.0

    def damage_of(self, u: Unit) -> float:
        dmg = u.stats["damage"]
        if not self.ongoing_active(u) or u.param is None:
            return dmg
        k = self.ongoing_mult(u)
        if u.is_("Lignite"):
            dmg += u.param * k * u.stats["burn"]
        elif u.is_("Fumungus"):
            dmg += u.param / 100.0 * k * self.trainers[1 - u.side].poison
        elif u.is_("Gaiadrasil"):
            dmg += u.param / 100.0 * k * sum(v.stats["damage"] for v in self.adjacent(u)
                                            if not v.is_("Gaiadrasil") and v.alive)
        return dmg

    def shock_of(self, u: Unit) -> float:
        shock = u.stats["shock"]
        b = self.in_front(u)   # Pylong boosts the ally behind it, i.e. Pylong is in front of u
        if b and b.is_("Pylong") and self.ongoing_active(b) and b.param:
            shock *= 1 + b.param / 100.0 * self.ongoing_mult(b)
        return shock

    def multicast_of(self, u: Unit) -> int:
        mc = u.multicast + u.extra_multicast
        if not u.has_ability:
            for v in self.adjacent(u):
                if v.is_("Stellagon") and self.ongoing_active(v) and v.param:
                    mc += int(v.param) * self.ongoing_mult(v)
        if u.is_("Zephyrex"):
            mc = 1
        return max(mc, 1)

    # ---------- damage and statuses ----------
    def hit(self, target: Trainer, amount: float, source: Unit | None) -> float:
        if amount <= 0:
            return 0.0
        if target.shock > 0:
            mode = SETTINGS["shock_mode"]
            if mode == "flat":
                amount += target.shock
            elif mode == "percent":
                amount *= 1 + target.shock / 100.0
        self._take(target, amount)
        return amount

    def status_damage(self, target: Trainer, amount: float) -> None:
        if amount <= 0:
            return
        if target.shield > 0:
            amount *= SETTINGS["status_vs_shield"]
        self._take(target, amount)

    def _take(self, target: Trainer, amount: float) -> None:
        absorbed = min(target.shield, amount)
        target.shield -= absorbed
        target.hp -= amount - absorbed

    def heal(self, tr: Trainer, amount: float) -> None:
        amount *= tr.heal_mult
        tr.hp += amount
        if SETTINGS["heal_cap"]:
            tr.hp = min(tr.hp, tr.max_hp)

    def gain_shield(self, tr: Trainer, amount: float) -> None:
        amount *= tr.shield_mult
        tr.shield += amount
        for v in self.teams[tr.side]:
            if v and v.is_("Stalagrove") and v.active_passive() and v.param:
                v.stats["damage"] += v.param / 100.0 * amount

    def knockout(self, u: Unit) -> None:
        if not u.alive:
            return
        if u.protect > 0:
            u.protect -= 1
            self.say(f"{u.name} (side {u.side}) Protect blocks a Knockout")
            return
        u.alive = False
        self.say(f"{u.name} (side {u.side}) is knocked out")

    def charge(self, u: Unit, seconds: float) -> None:
        if u.alive:
            u.progress += seconds

    # ---------- casting ----------
    def cast(self, u: Unit, reason: str = "cooldown") -> None:
        if not u.alive:
            return
        if self.depth >= SETTINGS["max_trigger_depth"]:
            return
        self.depth += 1
        try:
            self._cast(u, reason)
        finally:
            self.depth -= 1

    def _cast(self, u: Unit, reason: str) -> None:
        me, foe = self.trainers[u.side], self.trainers[1 - u.side]
        mc = self.multicast_of(u)
        u.casts += 1
        for _ in range(mc):
            u.triggers += 1
            dmg = self.damage_of(u)
            if dmg > 0:
                self.hit(foe, dmg, u)
                u.dealt += dmg
            if u.stats["heal"] > 0:
                self.heal(me, u.stats["heal"])
                u.healed += u.stats["heal"]
            if u.stats["shield"] > 0:
                self.gain_shield(me, u.stats["shield"])
                u.shielded += u.stats["shield"]
            if u.stats["poison"] > 0:
                foe.poison += u.stats["poison"]
                u.inflicted["poison"] += u.stats["poison"]
                self.on_ally_inflicts(u, "poison")
            if u.stats["burn"] > 0:
                foe.burn += u.stats["burn"]
                u.inflicted["burn"] += u.stats["burn"]
            shock = self.shock_of(u)
            if shock > 0:
                foe.shock += shock
                u.inflicted["shock"] += shock
                self.on_ally_inflicts(u, "shock")
        if self.verbose:
            self.say(f"{u.name} (side {u.side}, slot {u.slot + 1}) casts x{mc} [{reason}] "
                     f"-> HP {self.trainers[0].hp:.0f} / {self.trainers[1].hp:.0f}")
        if me.metronome:
            u.stats["damage"] += 10 * me.metronome
        if u.active_passive():
            self.on_cast(u)
        # Puffloon: trigger when adjacent Toxic allies trigger.
        if "Toxic" in u.types and not u.is_("Puffloon"):
            for v in self.adjacent(u):
                if v.is_("Puffloon") and v.active_passive():
                    self.cast(v, f"{u.name} triggered")

    def on_ally_inflicts(self, u: Unit, kind: str) -> None:
        for v in self.allies(u):
            if not v.active_passive():
                continue
            if kind == "poison" and v.is_("Thorntail") and v.param:
                v.stats["damage"] += v.param
            if kind == "poison" and v.is_("Cobrex") and v.param:
                self.charge(v, v.param)
            if kind == "shock" and v.is_("Clawnetic") and v.param:
                self.charge(v, v.param)

    def on_cast(self, u: Unit) -> None:
        p = u.param or 0
        name = u.base_name
        me = self.trainers[u.side]
        if name == "Mosslug":
            u.stats["damage"] += p
        elif name == "Pebbler":
            u.stats["shield"] += p
        elif name in ("Stingarde", "Electranade", "Pyronade"):
            self.knockout(u)
        elif name == "Boomagon":
            b = self.behind(u)
            if b:
                b.speed += p
        elif name == "Noxnimbus":
            for v in self.adjacent(u):
                if "Toxic" in v.types:
                    v.stats["poison"] += p
        elif name == "Runerock":
            for s in ("poison", "burn", "shock"):
                setattr(me, s, max(0.0, getattr(me, s) - p))
        elif name == "Cherubble":
            for v in self.adjacent(u):
                v.protect += int(p)
        elif name == "Cicadence":
            a = self.above(u)
            if a and "Bug" in a.types:
                self.cast(a, "Cicadence")
        elif name == "Dirgefin":
            for side in (0, 1):
                for v in self.teams[side]:
                    if v and v is not u and v.rarity == "Common":
                        self.knockout(v)
        elif name == "Dracana":
            b = self.behind(u)
            if b and not b.is_("Dracana"):
                self.charge(b, p)
        elif name == "Ironcore":
            for v in self.adjacent(u):
                if "Electric" in v.types and not v.is_("Ironcore"):
                    self.charge(v, p)
        elif name == "Magmalith":
            a = self.above(u)
            if a and "Fire" in a.types:
                a.stats["burn"] += p
        elif name == "Noxalith":
            a = self.above(u)
            if a and "Toxic" in a.types:
                a.stats["poison"] += p
        elif name == "Dryadell":
            a = self.above(u)
            if a and "Grass" in a.types:
                self.cast(a, "Dryadell")
        elif name == "Prismagon":
            kinds = {t for v in self.living(u.side) for t in v.types}
            u.stats["damage"] += p * len(kinds)
        elif name == "Reapra":
            enemies = [v for v in self.teams[1 - u.side] if v and v.alive]
            if u.level >= 4 and enemies:
                self.knockout(self.rng.choice(enemies))
            else:
                v = self.teams[1 - u.side][u.slot]
                if v:
                    self.knockout(v)
        elif name == "Sirenade":
            for s in ("poison", "burn", "shock"):
                cur = getattr(me, s)
                setattr(me, s, cur - math.floor(cur * p / 100.0))
        elif name == "Zephyrex":
            f = self.in_front(u)
            if f and "Flying" in f.types and not f.is_("Zephyrex"):
                f.extra_multicast += int(p)
        elif name == "Blixie":
            b = self.behind(u)
            if b and "Fire" in b.types:
                b.stats["burn"] += p * u.stats["burn"]
        elif name == "Draconarch":
            for v in self.adjacent(u):
                if v.active_passive():
                    self.battle_start(v)
            u.cooldown += p
        elif name == "Galvanine":
            u.speed += 50
            u.stats["shock"] += p
        elif name == "Geminiss":
            for v in self.adjacent(u):
                v.stats["shield"] *= 1 + p / 100.0
        elif name == "Saberhorn":
            f = self.in_front(u)
            if f:
                f.extra_multicast += int(p)
            u.cooldown += 8
        elif name == "Torrantler":
            for v in self.adjacent(u):
                if "Water" in v.types and not v.is_("Torrantler"):
                    self.cast(v, "Torrantler")
        elif name == "Panbud" and u.evolved():
            u.stats["damage"] += p

    # ---------- battle start ----------
    def battle_start(self, u: Unit) -> None:
        if not u.active_passive():
            return
        p = u.param or 0
        name = u.base_name
        if name in ("Frizzly", "Coalem"):
            self.cast(u, "battle start")
        elif name == "Aster":
            for v in self.adjacent(u):
                if "Water" in v.types:
                    v.stats["heal"] += p
        elif name == "Aegistruct":
            gain = sum(v.stats["shield"] for v in self.adjacent(u) if not v.is_("Aegistruct"))
            u.stats["shield"] += p * gain
        elif name == "Dribblet" and u.evolved():
            u.stats["damage"] += p
            u.stats["heal"] += p
        elif name == "Scorchimp" and u.evolved():
            fire = sum(1 for v in self.allies(u) if "Fire" in v.types)
            u.speed += p * fire

    def trinket_start(self, side: int) -> None:
        tr = self.trainers[side]
        units = self.living(side)
        for t in tr.trinkets:
            if t == "Rally Flag":
                for u in units:
                    if u.col == 0:
                        u.stats["damage"] += 12
            elif t == "Momentum Flag":
                for u in units:
                    if u.col == 0:
                        u.speed += 8
            elif t == "Earth Crest":
                for u in units:
                    if u.col == 2:
                        u.stats["shield"] *= 1.10
            elif t == "Sea Crest":
                for u in units:
                    if u.col == 2:
                        u.stats["heal"] *= 1.10
            elif t == "Warhorn":
                for u in units:
                    u.stats["damage"] += 10
            elif t == "Tempo Charm" and units:
                self.rng.choice(units).speed += 4
            elif t == "Metal Bat" and units:
                max(units, key=lambda u: u.cooldown).stats["damage"] *= 1.5
            elif t == "Ancient Plume" and len(units) == 1:
                units[0].multicast += 1
            elif t == "Alpha Crown":
                top = self.teams[side][1]
                if top:
                    for u in units:
                        u.stats["damage"] = top.stats["damage"]

    def start(self) -> None:
        for side in (0, 1):
            self.trinket_start(side)
        # Celestia first: it disables Ongoing monsters before anything reads them.
        for side in (0, 1):
            for u in self.teams[side]:
                if u and u.is_("Celestia") and u.active_passive():
                    for s2 in (0, 1):
                        for v in self.teams[s2]:
                            if v and v.row == u.row and v.ongoing:
                                v.disabled = True
        for side in self.order():
            repeats = 1 + ("Repeater Charm" in self.trainers[side].trinkets) + self.coffee[side]
            for _ in range(repeats):
                for u in self.teams[side]:
                    if u:
                        self.battle_start(u)

    def order(self) -> tuple[int, int]:
        return (0, 1) if SETTINGS["player_first_on_ties"] else (1, 0)

    # ---------- main loop ----------
    def dead(self) -> tuple[bool, bool]:
        return self.trainers[0].hp <= EPS, self.trainers[1].hp <= EPS

    def run(self) -> BattleResult:
        self.start()
        limit = SETTINGS["time_limit"] if self.until is None else self.until
        result = None
        if not self.immortal and any(self.dead()):
            result = self._result()
        while result is None:
            # Next event time.
            times = [self.next_poison, self.next_burn]
            for side in (0, 1):
                for u in self.living(side):
                    times.append(self.t + max(0.0, u.cooldown - u.progress) / self.speed_of(u))
                    if u.is_("Shelldra") and u.active_passive():
                        times.append(u.shelldra_next)
            t_next = min(times)
            if t_next > limit + EPS:
                self.t = limit
                return self._result(force_draw=self.until is None)
            dt = t_next - self.t
            for side in (0, 1):
                for u in self.living(side):
                    u.progress += dt * self.speed_of(u)
            self.t = t_next
            # Casts: keep going while someone is ready (charges can make more units ready).
            for _ in range(50):
                ready = False
                for side in self.order():
                    for u in self.teams[side]:
                        if u and u.alive and u.progress >= u.cooldown - 1e-7:
                            u.progress -= u.cooldown
                            if u.progress < 1e-7:
                                u.progress = 0.0
                            u.progress = min(u.progress, u.cooldown)
                            self.cast(u)
                            ready = True
                            if not self.immortal and any(self.dead()):
                                return self._result()
                if not ready:
                    break
            for side in (0, 1):
                for u in self.living(side):
                    if u.is_("Shelldra") and u.active_passive() and u.shelldra_next <= self.t + EPS:
                        u.extra_multicast += int(u.param or 0)
                        u.shelldra_next += 4.0
            if abs(self.t - self.next_burn) < 1e-7:
                for tr in (self.trainers[i] for i in self.order()):
                    if tr.burn > 0:
                        self.status_damage(tr, tr.burn)
                        tr.burn = max(0.0, tr.burn - 1)
                self.next_burn += SETTINGS["burn_interval"]
            if abs(self.t - self.next_poison) < 1e-7:
                for tr in (self.trainers[i] for i in self.order()):
                    self.status_damage(tr, tr.poison)
                self.next_poison += SETTINGS["poison_interval"]
            if not self.immortal and any(self.dead()):
                result = self._result()
        return result

    def _result(self, force_draw: bool = False) -> BattleResult:
        da, db = self.dead()
        if self.immortal or (self.until is not None and not (da or db)):
            winner = "none"
        elif force_draw or (da and db):
            winner = "draw"
        elif db:
            winner = "a"
        else:
            winner = "b"
        a, b = self.trainers
        stat = lambda tr: {k: round(getattr(tr, k)) for k in ("poison", "burn", "shock", "shield")
                           if getattr(tr, k)}
        return BattleResult(
            winner, self.t, (a.hp if self.immortal else max(a.hp, 0.0),
                             b.hp if self.immortal else max(b.hp, 0.0)), (a.max_hp, b.max_hp),
            (stat(a), stat(b)),
            tuple([u.summary() for u in self.teams[s] if u] for s in (0, 1)),
            self.log)


def simulate(team_a: dict, team_b: dict, seed: int = 0, verbose: bool = False,
             until: float | None = None, immortal: bool = False) -> BattleResult:
    """Play one battle. team_a is 'you' (side 0).

    until: stop at this time and report the state (winner "none" if nobody has died).
    immortal: nobody dies (HP can go negative); use with until to compare damage over time.
    """
    return Battle(team_a, team_b, seed=seed, verbose=verbose, until=until, immortal=immortal).run()


def win_rate(team_a: dict, opponents: list[dict], seeds: int = 1) -> float:
    """Share of battles team_a wins against a list of opponent teams (draws count half)."""
    score = 0.0
    n = 0
    for opp in opponents:
        for s in range(seeds):
            r = simulate(team_a, opp, seed=s)
            score += 1.0 if r.winner == "a" else 0.5 if r.winner == "draw" else 0.0
            n += 1
    return score / n if n else 0.0


def team_from_reader(state: dict) -> dict:
    """Turn reader.read_state() output for the shop screen into a simulator team."""
    slots = []
    for s in state.get("team", []):
        if not s or not s.get("name"):
            slots.append(None)
            continue
        stats = {}
        mc = None
        for b in s.get("stats", []):
            if b.get("stat") == "multicast":
                mc = b["value"]
            elif b.get("stat") in data.STATS and b.get("value") is not None:
                stats[b["stat"]] = b["value"]
        slot = {"name": s["name"], "level": s.get("level") or 1, "stats": stats}
        if mc:
            slot["multicast"] = mc
        slots.append(slot)
    return {"trainer": state.get("trainer"), "hp": state.get("trainer_hp"), "slots": slots}
