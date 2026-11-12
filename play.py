"""Play the run that is open in the game with simple rules, and log everything.

    python play.py            # play until the run ends or something is unclear
    python play.py --days 1   # stop after one battle

Rules (deliberately simple; the simulator will replace them):
- shop: use every free item, then keep buying the most expensive monster that
  is affordable while the team has an empty slot, then press BATTLE!
- result box: CONFIRM
- event: take the last choice; trinket gift: take the first card

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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=99, help="stop after this many battles")
    ap.add_argument("--new-run", action="store_true",
                    help="if no run is open, start a CASUAL Pantra run (never Ranked) and pick a trainer")
    args = ap.parse_args()

    h = hands_mod.Hands(dry_run=False)
    log_path = hands_mod.LOG_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}.jsonl"

    def log(kind: str, **data) -> None:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, **data}) + "\n")

    def stop(why: str, state: dict | None = None) -> int:
        print("STOPPED:", why)
        log("stop", why=why, state=state)
        return 1

    battles = 0
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
            i = choose_purchase(state)
            if i is not None:
                card = state["shop"][i]
                r = h.buy(i)
                print(f"day {state['day']}: buy {card['name']} (${card['price']}) -> {r.message}")
                log("buy", card=card, ok=r.ok, message=r.message)
                if not r.ok:
                    return stop(f"buy failed: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
                continue
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
            r = h.pick_trinket(0)
            print(f"trinkets {offered}: took the first -> {r.message}")
            log("trinket", offered=offered, picked=0, ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"after picking a trinket: {r.message}", r.after)
        elif screen == "trainer_pick":
            h.last_image.save(hands_mod.CAPTURE_DIR / f"trainer_pick_{datetime.now():%Y%m%d_%H%M%S}.png")
            offered = state["trainers"]
            k = next((offered.index(t) for t in PREFERRED_TRAINERS if t in offered), 0)
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
