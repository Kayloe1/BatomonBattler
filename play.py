"""Play the run that is open in the game, and log everything.

    python play.py            # play until the run ends or something is unclear
    python play.py --days 1   # stop after one battle
    python play.py --simple   # the old simple rules instead of the decision engine
    python gui.py             # the same, from a small window with Start, Pause and Stop

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
import learn_monsters

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


def _roster(state: dict | None) -> list[str]:
    """Every owned monster as "name Lv n [badges]", for comparing two shop states."""
    out = []
    for s in ((state or {}).get("team") or []) + ((state or {}).get("bench") or []):
        if s:
            badges = ",".join(f"{b.get('stat')} {b.get('value')}" for b in s.get("stats", []))
            out.append(f"{s.get('name') or 'unnamed'} Lv{s.get('level')} [{badges}]")
    return out


def event_outcome(before: dict | None, after: dict) -> dict:
    """What changed between the shop before an event and the shop after it.

    The next day's income is inside the money change, so compare it with days without an event.
    """
    a, b = _roster(before), _roster(after)
    gained, lost = list(b), []
    for m in a:
        if m in gained:
            gained.remove(m)
        else:
            lost.append(m)
    return {"day": after.get("day"), "money_before": (before or {}).get("money"), "money_after": after.get("money"),
            "lives_before": (before or {}).get("lives"), "lives_after": after.get("lives"),
            "monsters_new_or_changed": gained, "monsters_gone_or_changed": lost}


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


def remember_opponent(log_path) -> None:
    """Add the opponent of the battle just logged to data/opponents_recorded.jsonl, so the engine
    scores later decisions against real teams too (it joins the pool the next time play.py starts)."""
    try:
        from engine import opponents
        from sim import from_logs
        cases = from_logs.battles_from_log(log_path)
        spec = opponents.from_case(cases[-1]) if cases else None
        if spec is not None and opponents.add_recorded(spec["day"], spec):
            print(f"  opponent of day {spec['day']} recorded ({spec['unnamed']} unnamed)")
    except Exception as e:      # never stop a run over this
        print("opponent not recorded:", type(e).__name__, e)


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


# Every screen the loop in main() acts on. A fade, matchmaking or a battle can end on any of them
# (a fade after an event leads to a gift box, after the last battle to the run-over screen), so
# the wait at the top of the loop accepts them all.
AFTER_WAIT = {"shop", "result", "event", "gift_box", "trinket_pick", "trainer_pick", "select_target",
              "overflow", "cash_in", "run_over", "new_run", "main_menu", "main_menu_continue",
              "continue_confirm", "title", "stats"}

LAST_LOG = None          # path of the log of the latest main() call (batch.py reads it)


class Control:
    """Who follows a session from outside, and may hold or end it between two actions.

    This one is the terminal: it shows nothing extra and never holds the loop. The control window
    (gui.py) passes its own, which fills its panes from the events and has the buttons.
    Events: "start" (log, thinking: file names), "state" (state: each fresh read of the screen),
    "doing" (what: "thinking" or "battle"), "plan" (win_now), "think" (lines), "log" (record, data:
    every record written to the run log) and "needs_you" (why, capture, log: the bot has stopped).
    """
    stop_asked = False          # True once the session should end after the current action

    def event(self, kind: str, **data) -> None:
        pass

    def pause_point(self) -> bool:
        """Called between two actions, never inside one. Waits here while paused. True when the
        loop must start over: a pause has passed (the screen is read again) or a stop was asked."""
        return False


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


def main(argv=None, control: Control | None = None, hands=None, brain=None) -> int:
    """Play one session. From the terminal only argv is used. gui.py passes a Control (events,
    pause, stop); the tests also pass their own hands and brain so that no game is needed."""
    global LAST_LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=99, help="stop after this many battles")
    ap.add_argument("--simple", action="store_true", help="use the old simple shop rules")
    ap.add_argument("--learned", action="store_true",
                    help="shop with the policy learned by practice runs (train/) instead of the planner")
    ap.add_argument("--new-run", action="store_true",
                    help="if no run is open, start a CASUAL Pantra run (never Ranked) and pick a trainer")
    args = ap.parse_args(argv)

    control = control or Control()
    h = hands or hands_mod.Hands(dry_run=False)
    if brain is None and not args.simple:
        if Brain is None:
            print("decision engine unavailable:", _ENGINE_ERROR)
            control.event("needs_you", why=f"decision engine unavailable: {_ENGINE_ERROR}", capture=None, log=None)
            return 1
        brain = Brain(learned=args.learned)
    log_path = hands_mod.LOG_DIR / f"run_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    LAST_LOG = log_path

    def log(kind: str, **data) -> None:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), "kind": kind, **data}) + "\n")
        control.event("log", record=kind, data=data)

    think_path = log_path.with_name(log_path.name.replace("run_", "thinking_").replace(".jsonl", ".txt"))
    control.event("start", log=log_path.name, thinking=think_path.name)

    def think(lines: list[str]) -> None:
        """Say what the bot is thinking: on screen and in logs\\thinking_<time>.txt."""
        print("\n".join(lines))
        control.event("think", lines=lines)
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
        control.event("needs_you", why=why, capture=(state or {}).get("saved_capture"), log=log_path.name)
        alert(why, log_path)
        return 1

    battles = 0
    pending_event: dict | None = None
    last_shop_state: dict | None = None
    played = False          # True once this session has acted inside a run
    last_shop: dict | None = None
    tried_unknown: set = set()  # unnamed monsters already hovered (learn_monsters)
    seen_notes: list[str] = []
    while True:
        control.pause_point()               # a pause is held here; the screen is read again after it
        if control.stop_asked:
            print("stopped from the control window")
            log("stop", why="stopped from the control window")
            return 0
        state = h.look()
        screen = state["screen"]
        control.event("state", state=state)
        if screen in ("blank", "matchmaking", "battle"):
            state = h.wait_for(AFTER_WAIT, 300)
            screen = state["screen"]
            control.event("state", state=state)
        if state["problems"]:
            return stop("; ".join(state["problems"]) + f" (capture: {state.get('saved_capture')})", state)
        if state.get("notes") and state["notes"] != seen_notes:
            seen_notes = state["notes"]
            think(["Reading note (carried on; tell Claude so the glyph can be taught):"]
                  + [f"  {n}" for n in seen_notes])

        if screen == "shop":
            played = True
            if last_shop is not None and state["day"] != last_shop["day"]:
                outcome = {"badges": state["badges"] - last_shop["badges"],
                           "lives": state["lives"] - last_shop["lives"]}
                log("day_result", day=last_shop["day"], **outcome)
                print(f"day {last_shop['day']}: badges {outcome['badges']:+d}, lives {outcome['lives']:+d}")
                last_shop = None
            log("shop", state=state)
            if pending_event is not None:
                # what the event actually did: the first shop after it, next to the last shop before it
                log("event_outcome", **pending_event, **event_outcome(pending_event.pop("_before"), state))
                pending_event = None
            learn_sprites(h, state)
            if not h.dry_run:
                try:
                    lines = learn_monsters.learn_unknown(h, state, tried_unknown)
                except Exception as e:          # never stop a run over this
                    lines = [f"could not inspect an unknown monster: {type(e).__name__}: {e}"]
                if lines:
                    think(lines)
                    log("learn_monster", lines=lines)
                    continue                    # look again: the monster may have a name now
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
                control.event("doing", what="thinking")
                plan = brain.shop_plan(state)
                if control.pause_point():
                    continue                    # paused or stopped while thinking: nothing is clicked
                a = plan.actions[0]
                control.event("plan", win_now=plan.win_now)
                think(explain(plan, state))
                log("plan", actions=[str(x) for x in plan.actions], why=[x.why for x in plan.actions],
                    notes=plan.notes, value=plan.value)
                if a.kind != "battle" and not (a.kind in ("lock", "move")):
                    r = act(h, a)
                    print(f"day {state['day']}: {a.why} -> {r.message}")
                    log(a.kind, action=str(a), why=a.why, ok=r.ok, message=r.message)
                    if not r.ok and a.kind == "item" and r.message == hands_mod.ITEM_STILL_THERE:
                        # the click did nothing we can see: today's item uses are spent (the item
                        # counter is not read). Not a reason to stop; plan again without items.
                        brain.note_action("items_done", state)
                        think([f"The game did not take {state['shop'][a.index]['name']}: "
                               f"I use no more items today."])
                        continue
                    if not r.ok:
                        return stop(f"{a} failed: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
                    brain.note_action(a.kind, state, a.index)
                    continue
                # end of the turn: lock, moves, then battle
                held = False
                for b in plan.actions[:-1]:
                    held = control.pause_point()
                    if held:
                        break
                    r = act(h, b)
                    print(f"day {state['day']}: {b} ({b.why}) -> {r.message}")
                    log(b.kind, action=str(b), why=b.why, ok=r.ok, message=r.message)
                    if not r.ok:
                        # a failed move leaves a worse layout, not a broken run: stop moving
                        print("  layout step failed; battling with the layout as it is")
                        break
                if held:
                    continue                    # paused or stopped between two moves: read and plan again
                print(f"day {state['day']}: {plan.notes[-1] if plan.notes else ''}")
            if battles >= args.days:
                print("day limit reached; stopping before BATTLE!")
                log("stop", why="day limit")
                return 0
            if control.pause_point():
                continue                        # paused or stopped just before BATTLE!
            last_shop = state
            control.event("doing", what="battle")
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
                remember_opponent(log_path)
                if st["stuck"]:
                    return stop("the Stats window did not close", None)
            if not r.ok:
                return stop(f"battle did not reach the result box: {r.message} "
                            f"(capture: {(r.after or {}).get('saved_capture')})", r.after)
        elif screen == "main_menu_continue":
            r = h.continue_run()
            print(f"main menu: a run is open, pressed Continue -> {r.message}")
            log("continue_run", ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"after Continue: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
        elif screen == "select_target":
            h.last_image.save(hands_mod.CAPTURE_DIR / f"select_target_{datetime.now():%Y%m%d_%H%M%S}.png")
            effect = (pending_event or {}).get("picked")
            if brain:
                pos, why = brain.event_target(last_shop_state, effect, state)
            else:
                pos = next(((w, i) for w in ("team", "bench") for i, s_ in enumerate(state[w]) if s_), None)
                why = "simple rules take the first monster"
            if pos is None:
                return stop("Select a target: there is no monster to click", state)
            r = h.select_target(pos)
            think([f"Target for '{effect or 'the event effect'}': {pos[0]} slot {pos[1] + 1}. {why}. ({r.message})"])
            log("select_target", effect=effect, target=list(pos), why=why, ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"Select a target: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
        elif screen == "continue_confirm":
            # only a run shown as CASUAL MODE is continued (read twice); otherwise stop and tell
            r = h.confirm_continue()
            print(f"continue panel -> {r.message}")
            log("confirm_continue", ok=r.ok, message=r.message)
            if not r.ok:
                h.last_image.save(hands_mod.CAPTURE_DIR / f"continue_panel_{datetime.now():%Y%m%d_%H%M%S}.png")
                return stop(f"continue panel: {r.message}. I did not press Confirm.", r.after)
            played = True
        elif screen == "title":
            r = h.leave_title()
            log("title", ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"after the title screen: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
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
        elif screen == "stats":
            # a Stats window left open by an earlier session that stopped: close it, the result box follows
            r = h.close_stats()
            log("close_stats", ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"the Stats window did not close: {r.message}", r.after)
        elif screen == "overflow":
            # an event gave a monster with team and bench full: sell the weakest named bench monster,
            # or the newcomer when nothing on the bench may be sold (unnamed monsters are never sold)
            h.last_image.save(hands_mod.CAPTURE_DIR / f"overflow_{datetime.now():%Y%m%d_%H%M%S}.png")
            from engine.arrange import power
            from engine.model import unit_from_reader
            named = [(power(unit_from_reader(s_)), i) for i, s_ in enumerate(state["bench"]) if s_ and s_.get("name")]
            newcomer = state.get("overflow")
            new_power = power(unit_from_reader(newcomer)) if newcomer and newcomer.get("name") else None
            if named and (new_power is None or min(named)[0] <= new_power):
                which, why = min(named)[1], "the weakest monster on the bench"
            else:
                which, why = "overflow", "nothing on the bench is weaker than the new monster"
            r = h.resolve_overflow(which)
            think([f"Team and bench are full: I sell {'bench slot ' + str(which + 1) if which != 'overflow' else 'the new monster'} ({why}). ({r.message})"])
            log("overflow", sold=which, why=why, ok=r.ok, message=r.message)
            if not r.ok:
                return stop(f"overflow: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
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
            pending_event = {"effects": effects, "picked": effects[k] if k < len(effects) else None,
                             "_before": last_shop_state}
            if not r.ok:
                return stop(f"after the event: {r.message} (capture: {(r.after or {}).get('saved_capture')})", r.after)
        else:
            return stop(f"screen '{screen}' is not handled (capture: {state.get('saved_capture')})", state)


if __name__ == "__main__":
    sys.exit(main())
