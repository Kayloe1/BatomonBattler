"""Play the run that is open in the game, and log everything.

    python play.py            # play until the run ends or something is unclear
    python play.py --days 1   # stop after one battle
    python play.py --simple   # the old simple rules instead of the decision engine

Decisions (engine/, see docs/decision-engine.md):
- shop: the engine picks one action at a time (use an item, buy, sell, reroll),
  scoring each by simulated battles against a spread of likely opponents, then
  LOCK if a card is worth saving for, moves the team into the best layout and
  presses BATTLE!. The state is read again after every action.
- trinket gift: the trinket that helps the team most in the simulator
- trainer: Ed's record per trainer, minus trainers that fight the plan
- result box: CONFIRM; event: the last choice (event texts are not read yet)

It continues the run that is open. With --new-run it may also start one, but
only a Casual run: hands.start_casual_run() presses CONFIRM only after reading
"Casual Mode selected" twice, and nothing here can select Ranked Mode. It stops, with a saved capture, on any screen or
state it does not understand. Push the mouse into a screen corner to abort.
Log: logs/run_<time>.jsonl (plus every action in logs/actions_<date>.jsonl).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

import hands as hands_mod

try:
    from engine.bot import Brain
except ImportError as e:                 # engine needs the simulator (sim/)
    Brain = None
    _ENGINE_ERROR = e


# Ed's best results so far were with these trainers; otherwise the left card is taken.
PREFERRED_TRAINERS = ["Monster Ranger", "Swim Coach"]


def choose_purchase(state: dict) -> int | None:
    """Index of the shop card to click next, or None when done shopping."""
    cards = [(i, c) for i, c in enumerate(state["shop"]) if c is not None and c["price"] is not None]
    for i, c in cards:
        if c["kind"] == "item" and c["price"] == 0:
            return i
    if all(slot is not None for slot in state["team"]):
        return None
    monsters = [(c["price"], -i) for i, c in cards if c["kind"] == "monster" and c["price"] <= state["money"]]
    if not monsters:
        return None
    _, neg_i = max(monsters)
    return -neg_i


def act(h, a):
    """Carry out one engine action with the hands."""
    if a.kind == "buy":
        return h.buy(a.index)
    if a.kind == "item":
        return h.use_item(a.index)
    if a.kind == "sell":
        return h.sell(a.src)
    if a.kind == "reroll":
        return h.reroll()
    if a.kind == "lock":
        return h.lock()
    if a.kind == "move":
        return h.move(a.src, a.dst)
    raise ValueError(f"unknown action {a}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=99, help="stop after this many battles")
    ap.add_argument("--simple", action="store_true", help="use the old simple shop rules")
    ap.add_argument("--new-run", action="store_true",
                    help="if no run is open, start a CASUAL Pantra run (never Ranked) and pick a trainer")
    args = ap.parse_args()

    h = hands_mod.Hands(dry_run=False)
    brain = None
    if not args.simple:
        if Brain is None:
            print("decision engine unavailable:", _ENGINE_ERROR)
            return 1
        brain = Brain()
    log_path = hands_mod.LOG_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}.jsonl"

    def log(kind: str, **data) -> None:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, **data}) + "\n")

    def stop(why: str, state: dict | None = None) -> int:
        print("STOPPED:", why)
        log("stop", why=why, state=state)
        return 1

    battles = 0
    last_shop_state: dict | None = None
    played = False          # True once this session has acted inside a run
    last_shop: dict | None = None
    while True:
        state = h.look()
        screen = state["screen"]
        if screen in ("blank", "matchmaking", "battle"):
            state = h.wait_for({"shop", "result", "event"}, 300)
            screen = state["screen"]
        if state["problems"]:
            return stop("; ".join(state["problems"]) + f" (capture: {state.get('saved_capture')})", state)

        if screen == "shop":
            played = True
            if last_shop is not None and state["day"] != last_shop["day"]:
                outcome = {"badges": state["badges"] - last_shop["badges"],
                           "lives": state["lives"] - last_shop["lives"]}
                log("day_result", day=last_shop["day"], **outcome)
                print(f"day {last_shop['day']}: badges {outcome['badges']:+d}, lives {outcome['lives']:+d}")
                last_shop = None
            log("shop", state=state)
            if brain is None:
                i = choose_purchase(state)
                if i is not None:
                    card = state["shop"][i]
                    r = h.buy(i)
                    print(f"day {state['day']}: buy {card['name']} (${card['price']}) -> {r.message}")
                    log("buy", card=card, ok=r.ok, message=r.message)
                    if not r.ok:
                        return stop(f"buy failed: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
                    continue
            else:
                brain.observe_shop(state)
                last_shop_state = state
                plan = brain.shop_plan(state)
                a = plan.actions[0]
                log("plan", actions=[str(x) for x in plan.actions], why=[x.why for x in plan.actions],
                    notes=plan.notes, value=plan.value)
                if a.kind != "battle" and not (a.kind in ("lock", "move")):
                    r = act(h, a)
                    print(f"day {state['day']}: {a.why} -> {r.message}")
                    log(a.kind, action=str(a), why=a.why, ok=r.ok, message=r.message)
                    if not r.ok:
                        return stop(f"{a} failed: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
                    continue
                # end of the turn: lock, moves, then battle
                for b in plan.actions[:-1]:
                    r = act(h, b)
                    print(f"day {state['day']}: {b} ({b.why}) -> {r.message}")
                    log(b.kind, action=str(b), why=b.why, ok=r.ok, message=r.message)
                    if not r.ok:
                        # a failed move leaves a worse layout, not a broken run: stop moving
                        print("  layout step failed; battling with the layout as it is")
                        break
                print(f"day {state['day']}: {plan.notes[-1] if plan.notes else ''}")
            if battles >= args.days:
                print("day limit reached; stopping before BATTLE!")
                log("stop", why="day limit")
                return 0
            last_shop = state
            r = h.battle()
            battles += 1
            print(f"day {state['day']}: battle -> {r.message}")
            log("battle", team=state["team"], ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"battle did not reach the result box: {r.message} "
                            f"(capture: {(r.after or {}).get('saved_capture')})", r.after)
        elif screen in ("run_over", "new_run"):
            if screen == "run_over" and played:
                h.last_image.save(hands_mod.CAPTURE_DIR / f"run_over_{datetime.now():%Y%m%d_%H%M%S}.png")
                print("run over")
                log("run_over")
                return 0
            if not args.new_run:
                return stop("no run is open; use --new-run to start a Casual run")
            # hands.start_casual_run() only confirms after reading Casual Mode twice
            r = h.start_casual_run()
            print("new run ->", r.message)
            log("new_run", ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"could not start a Casual run: {r.message}", r.after)
        elif screen == "gift_box":
            r = h.open_gift()
            log("gift", ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"after opening the gift: {r.message}", r.after)
        elif screen == "trinket_pick":
            h.last_image.save(hands_mod.CAPTURE_DIR / f"trinket_pick_{datetime.now():%Y%m%d_%H%M%S}.png")
            offered = state["trinkets"]
            k, why = brain.trinket(last_shop_state, offered) if brain else (0, "first card")
            r = h.pick_trinket(k)
            print(f"trinkets {offered}: took {offered[k] if k < len(offered) else k} ({why}) -> {r.message}")
            log("trinket", offered=offered, picked=k, why=why, ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"after picking a trinket: {r.message}", r.after)
        elif screen == "trainer_pick":
            h.last_image.save(hands_mod.CAPTURE_DIR / f"trainer_pick_{datetime.now():%Y%m%d_%H%M%S}.png")
            offered = state["trainers"]
            if brain:
                k, why = brain.trainer(offered)
                brain.new_run()
            else:
                k = next((offered.index(t) for t in PREFERRED_TRAINERS if t in offered), 0)
                why = "preferred list"
            print(f"trainer choice: {why}")
            r = h.pick_trainer(k)
            print(f"trainers {offered}: picked {offered[k] or 'card ' + str(k)} -> {r.message}")
            log("trainer", offered=offered, picked=k, ok=r.ok, message=r.message)
            played = True
            if not r.ok:
                return stop(f"after picking a trainer: {r.message} "
                            f"(capture: {(r.after or {}).get('saved_capture')})", r.after)
        elif screen == "result":
            h.last_image.save(hands_mod.CAPTURE_DIR / f"result_{datetime.now():%Y%m%d_%H%M%S}.png")
            r = h.confirm_result()
            log("confirm", ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"after CONFIRM: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
        elif screen == "event":
            h.last_image.save(hands_mod.CAPTURE_DIR / f"event_{datetime.now():%Y%m%d_%H%M%S}.png")
            k = state["choices"] - 1
            r = h.choose_event(k)
            print(f"event: took choice {k} of {state['choices']} -> {r.message}")
            log("event", choice=k, choices=state["choices"], ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"after the event: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
        else:
            return stop(f"screen '{screen}' is not handled (capture: {state.get('saved_capture')})", state)


if __name__ == "__main__":
    sys.exit(main())
