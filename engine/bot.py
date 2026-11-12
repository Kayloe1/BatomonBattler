"""What play.py talks to: one object that holds the opponent pool, the simulator
cache and what the screen does not show (trinkets owned, rescue used), and turns
reader states into decisions."""
from __future__ import annotations

import json
from pathlib import Path

from . import choices, data, events, model, opponents
from .evaluate import Evaluator
from .planner import Params, Plan, Planner

MEMORY_FILE = Path(__file__).resolve().parent.parent / "logs" / "engine_memory.json"


class Brain:
    def __init__(self, params: Params | None = None, pool_size: int = 24):
        self.pools = opponents.pools(n=pool_size, seed=1)
        self.planner = Planner(Evaluator(self.pools), params or Params())
        self.memory = self._load()

    # -- memory that survives a restart of play.py --
    def _load(self) -> dict:
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"trinkets": [], "rescue_used": False, "last_lives": None, "last_day": None}

    def save(self) -> None:
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(json.dumps(self.memory, indent=1), encoding="utf-8")

    def new_run(self) -> None:
        self.memory = {"trinkets": [], "rescue_used": False, "last_lives": None, "last_day": None}
        self.save()

    def observe_shop(self, state: dict) -> None:
        """Keep track of the rescue: lives reaching 0 once gives one more life."""
        last = self.memory.get("last_lives")
        day = state.get("day")
        if last is not None and self.memory.get("last_day") is not None and day == self.memory["last_day"] + 1:
            lost = data.lives_lost(self.memory["last_day"])
            if last - lost <= 0 and (state.get("lives") or 0) > 0:
                self.memory["rescue_used"] = True
        if day is not None and state.get("lives") is not None:
            self.memory["last_day"], self.memory["last_lives"] = day, state["lives"]
        self.save()

    def note_action(self, kind: str, state: dict, index: int | None = None) -> None:
        """Remember what was done today (the screen does not show it): monsters bought are not sold
        again today, and rerolls are counted so a spending spree has an end."""
        day = state.get("day")
        if self.memory.get("turn_day") != day:
            self.memory.update(turn_day=day, bought=[], rerolls=0)
        if kind == "buy" and index is not None:
            card = (state.get("shop") or [None] * 5)[index]
            if card and card.get("kind") == "monster" and card.get("name"):
                self.memory["bought"].append(card["name"])
        elif kind == "reroll":
            self.memory["rerolls"] = self.memory.get("rerolls", 0) + 1
        self.save()

    # -- decisions --
    def run_state(self, state: dict) -> model.RunState:
        return model.from_reader(state, self.memory)

    def shop_plan(self, state: dict) -> Plan:
        return self.planner.decide(self.run_state(state))

    def trinket(self, shop_state: dict | None, offered: list[str | None]) -> tuple[int, str]:
        s = self.run_state(shop_state) if shop_state else model.RunState()
        k, why = choices.pick_trinket(self.planner, s, offered)
        if offered[k]:
            self.memory["trinkets"].append(offered[k])
            self.save()
        return k, why

    def event(self, shop_state: dict | None, effects: list[str | None]) -> tuple[int, list[str]]:
        """Best event choice for the team last seen in the shop, with the explanation lines."""
        s = self.run_state(shop_state) if shop_state else model.RunState()
        return events.pick(self.planner, s, effects)

    def trainer(self, offered: list[str | None]) -> tuple[int, str]:
        return choices.pick_trainer(offered)
