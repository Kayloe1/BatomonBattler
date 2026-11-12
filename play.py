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
    from engine.explain import explain
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


def learn_sprites(h, state: dict) -> None:
    """Save the shop cards' sprites so opponents' monsters can be named on the battle screen."""
    if getattr(h, "last_image", None) is None:
        return
    try:
        import numpy as np
        import reader
        import window
        reader.learn_card_sprites(np.asarray(window.canonical_picture(h.last_image)), state)
    except Exception as e:      # never stop a run over this
        print("card sprites not saved:", e)


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


LAST_LOG = None          # path of the log of the latest main() call (batch.py reads it)


def alert(why: str, log_path) -> None:
    """Stop-and-tell: a loud message, a beep and a note file, so a stop is never missed."""
    text = (f"\n{'=' * 70}\nTHE BOT STOPPED AND NEEDS YOU\n{why}\n"
            f"Nothing was clicked after this. Look at the game window, then tell Claude what it shows\n"
            f"(the capture named above is in captures\\). Log: {log_path}\n{'=' * 70}\n")
    print(text)
    try:
        hands_mod.LOG_DIR.mkdir(exist_ok=True)
        (hands_mod.LOG_DIR / "last_stop.txt").write_text(f"{datetime.now():%Y-%m-%d %H:%M:%S}\n{why}\n", encoding="utf-8")
    except OSError:
        pass
    try:
        import winsound
        for _ in range(3):
            winsound.Beep(1000, 300)
    except Exception:                      # not Windows, or no sound: the message is enough
        pass


def main(argv=None) -> int:
    global LAST_LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=99, help="stop after this many battles")
    ap.add_argument("--simple", action="store_true", help="use the old simple shop rules")
    ap.add_argument("--new-run", action="store_true",
                    help="if no run is open, start a CASUAL Pantra run (never Ranked) and pick a trainer")
    args = ap.parse_args(argv)

    h = hands_mod.Hands(dry_run=False)
    brain = None
    if not args.simple:
        if Brain is None:
            print("decision engine unavailable:", _ENGINE_ERROR)
            return 1
        brain = Brain()
    log_path = hands_mod.LOG_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    LAST_LOG = log_path

    def log(kind: str, **data) -> None:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, **data}) + "\n")

    think_path = log_path.with_name(log_path.name.replace("run_", "thinking_").replace(".jsonl", ".txt"))

    def think(lines: list[str]) -> None:
        """Say what the bot is thinking: on screen and in logs\\thinking_<time>.txt."""
        print("\n".join(lines))
        try:
            with open(think_path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n\n")
        except OSError:
            pass

    if brain is not None:
        think(["HOW TO READ THIS: each option gets a 'gain' = how much better the run looks after it",
               "(and the buys it leads to) than ending the turn now. It mixes the chance to win today,",
               "the next two days, money kept and progress to level-ups. Bigger is better."])

    def stop(why: str, state: dict | None = None) -> int:
        print("STOPPED:", why)
        log("stop", why=why, state=state)
        alert(why, log_path)
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
            learn_sprites(h, state)
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
                think(explain(plan, state))
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
            log("battle", team=state["team"], ok=r.ok, message=r.message, day=state["day"],
                trainer=state["trainer"], trainer_hp=state["trainer_hp"], seen=r.battle)
            if r.ok and r.battle is not None:
                # the numbers of the battle that was just fought; never stops the run, except a
                # Stats window that will not close
                st = h.read_battle_stats()
                r.battle["stats"] = {k: v for k, v in st.items() if k != "stuck"}
                log("battle_stats", day=state["day"], **r.battle["stats"])
                for p_ in st["problems"]:
                    print("  stats:", p_)
                if st["stuck"]:
                    return stop("the Stats window did not close", None)
            if not r.ok:
                return stop(f"battle did not reach the result box: {r.message} "
                            f"(capture: {(r.after or {}).get('saved_capture')})", r.after)
        elif screen == "cash_in":
            h.last_image.save(hands_mod.CAPTURE_DIR / f"cash_in_{datetime.now():%Y%m%d_%H%M%S}.png")
            r = h.cash_in()
            print(f"cash in -> {r.message}")
            log("cash_in", ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"after Cash In: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
        elif screen in ("run_over", "new_run", "main_menu"):
            if screen in ("run_over", "main_menu") and played:
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
            think([f"Trinket choice between {', '.join(str(o) for o in offered)}: "
                   f"I took {offered[k] if k < len(offered) else k} because {why}. ({r.message})"])
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
            think([f"Trainer choice between {', '.join(str(o) for o in offered)}: "
                   f"{offered[k] or 'card ' + str(k)}. Reason: {why}."])
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
            effects = state.get("effects") or [None] * state["choices"]
            if brain:
                k, lines = brain.event(last_shop_state, effects)
            else:
                k, lines = state["choices"] - 1, ["Event: simple rules take the last choice."]
            r = h.choose_event(k)
            think(lines + [f"({r.message})"])
            log("event", choice=k, choices=state["choices"], effects=effects, raw=state.get("raw"), why=lines,
                ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"after the event: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
        else:
            return stop(f"screen '{screen}' is not handled (capture: {state.get('saved_capture')})", state)


if __name__ == "__main__":
    sys.exit(main())
