r"""Tests for the control window (gui.py) and the hooks in play.py it uses.

The game is not needed: FakeHands is a pretend game (shop -> battle -> result -> shop ...) with no
window and no mouse, and FakeBrain a pretend decision engine. Logs and captures go to a temporary
folder. The window tests build the real window but never show it.
"""
import io
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import gui  # noqa: E402
import hands  # noqa: E402
import play  # noqa: E402
from engine.planner import Action, Plan  # noqa: E402


class FakeImage:
    def save(self, path):
        pass


class FakeHands:
    """A pretend game. `journal` lists every look and action in order, `calls` the actions only.
    hooks[name] runs inside the action of that name (while the bot is "in the middle of it")."""
    dry_run = True              # play.py then leaves out hovering unknown monsters

    def __init__(self, days: int = 2, full_team: bool = False):
        self.days = days
        self.day, self.screen, self.money, self.badges = 1, "shop", 10, 0
        self.card = {"name": "Pebbler", "price": 3, "kind": "monster", "stats": []}
        self.team = [{"name": "Joltail", "level": 1, "stats": []}] * (6 if full_team else 2) + [None] * (0 if full_team else 4)
        self.moves = 0
        self.unreadable = False
        self.journal, self.calls, self.hooks = [], [], {}
        self.last_image = FakeImage()

    def _did(self, name: str) -> None:
        self.journal.append(name)
        self.calls.append(name)
        hook = self.hooks.pop(name, None)
        if hook:
            hook()

    def look(self, save_if_unreadable: bool = True) -> dict:
        self.journal.append("look")
        if self.unreadable:
            return {"screen": "shop", "problems": ["money: cannot read '?7'"], "saved_capture": "unread_test.png"}
        if self.screen != "shop":
            return {"screen": self.screen, "problems": []}
        return {"screen": "shop", "day": self.day, "lives": 5, "badges": self.badges, "badges_goal": 10,
                "trainer": "Swim Coach", "trainer_hp": 500, "money": self.money, "reroll_price": 1,
                "locked": False, "shop": [self.card, None, None, None, None], "team": list(self.team),
                "bench": [None] * 4, "problems": []}

    def wait_for(self, wanted, timeout=120):
        return self.look()

    def buy(self, i: int):
        self._did("buy")
        self.money -= self.card["price"]
        self.card = None
        return hands.Result(True, "ok")

    def move(self, src, dst):
        self._did("move")
        self.moves += 1
        return hands.Result(True, "ok")

    def battle(self):
        self._did("battle")
        self.screen = "result"
        return hands.Result(True, "now on 'result'")

    def confirm_result(self):
        self._did("confirm")
        self.badges += 1
        self.day += 1
        self.screen = "shop" if self.day <= self.days else "run_over"
        self.card = {"name": "Pebbler", "price": 3, "kind": "monster", "stats": []}
        return hands.Result(True, f"now on '{self.screen}'")


class FakeBrain:
    """Buys the first shop card while there is one, then battles. Always expects to win 62%.
    With moves_on_day set, that day's turn ends with two moves before the battle."""

    def __init__(self, game: FakeHands, moves_on_day: int | None = None):
        self.game, self.moves_on_day = game, moves_on_day

    def observe_shop(self, state):
        pass

    def note_action(self, *a):
        pass

    def shop_plan(self, state) -> Plan:
        card = state["shop"][0]
        if card:
            label = f"buy {card['name']} ${card['price']}"
            return Plan([Action("buy", 0, why=label)], 0.5, [], considered=[(label, 0.3)], win_now=0.62)
        actions = []
        if state["day"] == self.moves_on_day and self.game.moves < 2:
            actions = [Action("move", src=("bench", 0), dst=("team", 0)), Action("move", src=("bench", 1), dst=("team", 1))]
        actions.append(Action("battle", why="expected win chance 62%"))
        return Plan(actions, 0.5, ["battle"], considered=[], win_now=0.62)


class Quiet(unittest.TestCase):
    """Logs and captures in a temporary folder, no beeps, nothing printed, no sprites saved."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.logs = Path(self.tmp.name) / "logs"
        self.logs.mkdir()
        (Path(self.tmp.name) / "captures").mkdir()
        self.printed = io.StringIO()
        for p in (mock.patch.object(hands, "LOG_DIR", self.logs),
                  mock.patch.object(hands, "CAPTURE_DIR", Path(self.tmp.name) / "captures"),
                  mock.patch.object(play, "learn_sprites", lambda h, state: None),
                  mock.patch("winsound.Beep"),
                  mock.patch("sys.stdout", self.printed)):
            p.start()
            self.addCleanup(p.stop)
        self.sessions = []
        self.addCleanup(self.end_sessions)

    def end_sessions(self):
        for s in self.sessions:
            s.stop()
            if s.thread is not None:
                s.thread.join(10)

    def session(self, game, argv=(), brain="fake", **kw) -> gui.Session:
        if brain == "fake":
            brain = FakeBrain(game, **kw)
        s = gui.Session(list(argv), hands=game, brain=brain)
        self.sessions.append(s)
        return s

    def log_records(self) -> list[dict]:
        return [json.loads(line) for f in sorted(self.logs.glob("run_*.jsonl"))
                for line in f.read_text(encoding="utf-8").splitlines()]


def held_inside(game: FakeHands, action: str):
    """Make the next `action` of the pretend game wait in the middle. Returns (entered, release)."""
    entered, release = threading.Event(), threading.Event()

    def hook():
        entered.set()
        release.wait(10)
    game.hooks[action] = hook
    return entered, release


class SessionTests(Quiet):
    def events_until(self, s: gui.Session, kind: str, timeout: float = 10) -> list:
        """Everything reported up to and including the first event of this kind."""
        out, end = [], time.time() + timeout
        while time.time() < end:
            try:
                e = s.events.get(timeout=0.05)
            except Exception:
                continue
            out.append(e)
            if e[0] == kind:
                return out
        self.fail(f"no '{kind}' event; got {[k for k, _ in out]}")

    def test_a_session_reports_thinking_state_plan_and_actions(self):
        game = FakeHands(days=2)
        s = self.session(game)
        s.start()
        events = self.events_until(s, "finished")
        self.assertEqual(events[-1][1]["code"], 0)
        kinds = [k for k, _ in events]
        self.assertEqual(kinds[0], "start")
        thoughts = "\n".join(line for k, d in events if k == "think" for line in d["lines"])
        self.assertIn("Chance to win today's battle with the team as it is: 62%.", thoughts)
        self.assertIn("Decision: buy Pebbler $3", thoughts)
        self.assertEqual({d["win_now"] for k, d in events if k == "plan"}, {0.62})
        days = [d["state"]["day"] for k, d in events if k == "state" and d["state"]["screen"] == "shop"]
        self.assertEqual(sorted(set(days)), [1, 2])
        logged = [d["record"] for k, d in events if k == "log"]
        for kind in ("shop", "buy", "battle", "confirm", "day_result", "run_over"):
            self.assertIn(kind, logged)
        self.assertEqual(game.calls, ["buy", "battle", "confirm", "buy", "battle", "confirm"])
        # the window gets the same records the log file gets
        self.assertEqual([r["kind"] for r in self.log_records()], logged)

    def test_pause_before_the_first_action_holds_until_resume(self):
        game = FakeHands()
        s = self.session(game)
        s.pause()
        s.start()
        self.events_until(s, "paused")
        time.sleep(0.2)
        self.assertEqual(game.journal, [])                      # not even a look while paused
        s.resume()
        events = self.events_until(s, "finished")
        self.assertIn("resumed", [k for k, _ in events])
        self.assertEqual(game.calls[:2], ["buy", "battle"])

    def test_pause_asked_during_a_battle_waits_for_it_then_reads_the_screen_again(self):
        game = FakeHands()
        s = self.session(game)
        entered, release = held_inside(game, "battle")
        s.start()
        self.assertTrue(entered.wait(10))
        s.pause()                                               # the battle is still running
        time.sleep(0.1)
        self.assertEqual(game.calls, ["buy", "battle"])
        self.assertFalse(any(k == "paused" for k, _ in list(s.events.queue)))    # not held inside the battle
        release.set()
        self.events_until(s, "paused")
        time.sleep(0.2)
        self.assertEqual(game.journal[-1], "battle")            # nothing after the battle, not even a look
        s.resume()
        self.events_until(s, "finished")
        after = game.journal[game.journal.index("battle") + 1:]
        self.assertEqual(after[:2], ["look", "confirm"])        # a fresh read first, then on with the run

    def test_pause_between_two_moves_plans_again_after_resume(self):
        game = FakeHands(days=1)
        s = self.session(game, moves_on_day=1)
        entered, release = held_inside(game, "move")
        s.start()
        self.assertTrue(entered.wait(10))
        s.pause()
        release.set()
        self.events_until(s, "paused")
        time.sleep(0.2)
        self.assertEqual(game.calls, ["buy", "move"])           # held after the first move, before the second
        s.resume()
        self.events_until(s, "finished")
        self.assertEqual(game.journal[game.journal.index("move") + 1], "look")
        # planned again from that read: the new plan starts its two moves over (one was already done)
        self.assertEqual(game.calls, ["buy", "move", "move", "move", "battle", "confirm"])

    def test_pause_while_thinking_clicks_nothing(self):
        game = FakeHands()
        brain = FakeBrain(game)
        entered, release = threading.Event(), threading.Event()
        plan = brain.shop_plan

        def slow_plan(state):
            if not entered.is_set():
                entered.set()
                release.wait(10)
            return plan(state)
        brain.shop_plan = slow_plan
        s = self.session(game, brain=brain)
        s.start()
        self.assertTrue(entered.wait(10))
        s.pause()
        release.set()
        self.events_until(s, "paused")
        time.sleep(0.2)
        self.assertEqual(game.calls, [])                        # the plan made before the pause is dropped
        s.resume()
        self.events_until(s, "finished")
        self.assertEqual(game.calls[0], "buy")

    def test_stop_ends_the_session_after_the_current_action(self):
        game = FakeHands()
        s = self.session(game)
        entered, release = held_inside(game, "battle")
        s.start()
        self.assertTrue(entered.wait(10))
        s.stop()
        release.set()
        events = self.events_until(s, "finished")
        self.assertEqual(events[-1][1]["code"], 0)
        s.thread.join(5)
        self.assertFalse(s.running)
        self.assertEqual(game.calls, ["buy", "battle"])         # the battle was finished, nothing after it
        self.assertEqual(self.log_records()[-1]["why"], gui.STOPPED_HERE)

    def test_stop_while_paused(self):
        game = FakeHands()
        s = self.session(game)
        s.pause()
        s.start()
        self.events_until(s, "paused")
        s.stop()
        events = self.events_until(s, "finished")
        self.assertEqual(events[-1][1]["code"], 0)
        self.assertEqual(game.journal, [])

    def test_an_unreadable_screen_reports_the_reason_and_the_capture(self):
        game = FakeHands()
        game.unreadable = True
        s = self.session(game)
        s.start()
        events = self.events_until(s, "finished")
        self.assertEqual(events[-1][1]["code"], 1)
        (stop,) = [d for k, d in events if k == "needs_you"]
        self.assertIn("money: cannot read '?7'", stop["why"])
        self.assertEqual(stop["capture"], "unread_test.png")
        self.assertEqual(game.calls, [])
        self.assertIn("money: cannot read", (self.logs / "last_stop.txt").read_text(encoding="utf-8"))

    def test_an_error_in_the_bot_is_reported_not_lost(self):
        class FailSafeException(Exception):
            pass
        for error, expected in ((RuntimeError("could not bring the game window to the front"), "could not bring"),
                                (FailSafeException("corner"), "Emergency stop"),
                                (KeyError("day"), "KeyError")):
            game = FakeHands()
            game.hooks["buy"] = lambda error=error: (_ for _ in ()).throw(error)
            s = self.session(game)
            with mock.patch("sys.stderr", io.StringIO()):
                s.start()
                events = self.events_until(s, "finished")
            self.assertIsNone(events[-1][1]["code"])
            (text,) = [d["text"] for k, d in events if k == "error"]
            self.assertIn(expected, text)

    def test_the_game_window_missing_is_reported(self):
        s = gui.Session([], runner=lambda argv, **kw: (_ for _ in ()).throw(RuntimeError("Batomon Showdown window not found")))
        self.sessions.append(s)
        with mock.patch("sys.stderr", io.StringIO()):
            s.start()
            events = self.events_until(s, "finished")
        self.assertEqual([d["text"] for k, d in events if k == "error"], ["Batomon Showdown window not found"])


class TerminalStillWorks(Quiet):
    """python play.py and batch.py: no Control is passed, and play.LAST_LOG names the log."""

    def test_main_without_a_control_plays_and_sets_last_log(self):
        game = FakeHands(days=2, full_team=True)
        self.assertEqual(play.main(["--simple", "--days", "1"], hands=game), 0)
        self.assertEqual(game.calls, ["battle", "confirm"])     # team full: no buy; stopped before the second BATTLE!
        self.assertTrue(play.LAST_LOG.exists())
        self.assertEqual(self.log_records()[-1], {**self.log_records()[-1], "kind": "stop", "why": "day limit"})

    def test_the_default_control_never_holds_or_stops(self):
        c = play.Control()
        self.assertFalse(c.pause_point())
        self.assertFalse(c.stop_asked)
        self.assertIsNone(c.event("state", state={}))


class StatusTests(unittest.TestCase):
    def test_status_follows_the_events(self):
        st = gui.Status()
        self.assertEqual(st.run_line(), "Day -     Lives -     Badges -     Money -")
        shop = {"screen": "shop", "day": 4, "lives": 3, "badges": 2, "badges_goal": 10, "money": 17, "trainer": "Witch"}
        st.apply("state", {"state": shop})
        st.apply("doing", {"what": "thinking"})
        self.assertEqual(st.run_line(), "Day 4     Lives 3     Badges 2 / 10     Money $17")
        self.assertEqual(st.screen_line(), "shop (thinking about the shop)")
        st.apply("plan", {"win_now": 0.455})
        self.assertTrue(st.win_line().startswith("46%"), st.win_line())      # rounded as play.py prints it
        st.apply("log", {"record": "sell", "data": {"action": "sell ('team', 3)", "why": "sell Joltail to buy Humbolt",
                                                  "ok": True, "message": "ok"}})
        self.assertEqual(st.action_line(), "sell Joltail to buy Humbolt  ->  ok")
        st.apply("log", {"record": "move", "data": {"action": "move ('bench', 3) -> ('team', 0)", "why": "",
                                                  "ok": False, "message": "target slot is still empty"}})
        self.assertEqual(st.action_line(), "move bench slot 4 -> team top left  ->  target slot is still empty   (FAILED)")
        st.apply("doing", {"what": "battle"})
        self.assertEqual(st.screen_line(), "battle running, waiting for the result")
        st.apply("log", {"record": "battle", "data": {"day": 4, "ok": True, "message": "now on 'result'"}})
        self.assertEqual(st.screen_line(), "battle result")                   # known before the next read
        st.apply("state", {"state": {"screen": "event", "problems": []}})
        self.assertEqual(st.screen_line(), "event")
        self.assertEqual(st.day, 4)                                           # kept while another screen shows
        st.apply("state", {"state": {**shop, "day": 5}})
        self.assertEqual(st.win_line(), "-")                                  # yesterday's chance is not shown for today

    def test_every_action_record_gets_plain_words(self):
        said = {kind: gui.action_text(kind, rec) for kind, rec in {
            "buy": {"card": {"name": "Pebbler", "price": 3}, "ok": True},
            "trainer": {"offered": ["Witch", "Swim Coach", None], "picked": 1, "ok": True},
            "trinket": {"offered": ["Bug Net", "Poison Bell"], "picked": 0, "ok": True},
            "event": {"choice": 2, "effects": ["a", "b", "Gain Mysterious Charm"], "ok": True},
            "overflow": {"sold": 1, "ok": True},
            "select_target": {"target": ["team", 4], "ok": True},
            "battle": {"day": 6, "ok": True},
            "confirm": {"ok": True},
        }.items()}
        self.assertEqual(said, {"buy": "buy Pebbler ($3)", "trainer": "pick the trainer Swim Coach",
                                "trinket": "take the trinket Bug Net", "event": "event: Gain Mysterious Charm",
                                "overflow": "sell bench slot 2 (no room)",
                                "select_target": "target for the event: team bottom middle",
                                "battle": "BATTLE! (day 6)", "confirm": "CONFIRM on the result box"})
        self.assertIsNone(gui.action_text("shop", {"state": {}}))             # not an action

    def test_the_window_is_placed_off_the_game(self):
        screen = (0, 0, 3840, 2088)
        game = (40, 20, 2622, 1516)
        self.assertEqual(gui.beside(game, [screen], (700, 1000)), (2634, 20))              # right of the game
        self.assertEqual(gui.beside((1200, 20, 3840, 1516), [screen], (700, 1000)), (488, 20))    # no room: left
        self.assertEqual(gui.beside((0, 0, 3840, 1500), [screen], (700, 500)), (0, 1512))  # below
        second = (3840, 0, 5760, 1040)
        self.assertEqual(gui.beside(game, [screen, second], (700, 1000)), (3852, 12))      # another monitor first
        self.assertEqual(gui.beside(None, [screen], (700, 1000)), (3128, 12))              # no game: top right
        x, y = gui.beside((0, 0, 3840, 2088), [screen], (700, 1000))                       # nothing fits
        self.assertTrue(0 <= x and x + 700 <= 3840 and 0 <= y)


class SafetyTests(unittest.TestCase):
    def test_the_window_has_no_way_to_click_or_to_pick_ranked(self):
        """Rule 1: only hands.start_casual_run() starts a run. gui.py must not click, must not use the
        New Run dialog's boxes, and must not call any of the hands' actions itself."""
        import re
        src = Path(gui.__file__).read_text(encoding="utf-8")
        code = "\n".join(line.split("#")[0] for line in src.split('"""', 2)[2].splitlines())
        for banned in ("pyautogui", "NEW_RUN", "RANKED", "_click", "_drag", "start_casual_run", "win32api.mouse",
                       "SendInput", "mouse_event", "keybd_event", "PostMessage", "SendMessage"):
            self.assertNotIn(banned, code, banned)
        self.assertEqual(re.findall(r"ranked", code, re.I), ["Ranked"])       # only the words "(never Ranked)"
        self.assertIn("(never Ranked)", code)


class WindowTests(Quiet):
    """The real window, never shown, driven by its own buttons."""

    def setUp(self):
        super().setUp()
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"no display for Tk: {e}")
        self.root.withdraw()
        self.addCleanup(self.destroy)
        self.game = FakeHands(days=2)
        self.brain_options = {}

        def new_session(argv):
            return self.session(self.game, argv, **self.brain_options)
        self.app = gui.App(self.root, new_session=new_session)

    def destroy(self):
        self.end_sessions()
        if getattr(self, "app", None) is not None:
            self.app.destroy()
        else:
            self.root.destroy()

    def pump(self, until, timeout: float = 10, what: str = ""):
        end = time.time() + timeout
        while time.time() < end:
            self.root.update()
            self.app.drain()
            if until():
                return
            time.sleep(0.01)
        self.fail(f"timed out waiting for {what or until}")

    def state(self, button) -> str:
        return str(button.cget("state"))

    def test_start_fills_the_thinking_and_status_panes(self):
        app = self.app
        self.assertEqual((self.state(app.start_button), self.state(app.pause_button), self.state(app.stop_button)),
                         ("normal", "disabled", "disabled"))
        seen = []
        entered, release = held_inside(self.game, "battle")
        app.start_button.invoke()
        self.assertEqual(self.state(app.start_button), "disabled")
        self.pump(entered.is_set, what="the first battle")
        self.pump(lambda: app.status.doing == "battle")
        seen.append({k: v.get() for k, v in app.v.items()})          # the panes while the bot is playing
        thinking_live = app.thinking()
        self.assertEqual(app.mode_text.get(), gui.MODES["playing"])
        release.set()
        self.pump(lambda: app.mode == "idle", what="the end of the run")
        live = seen[0]
        self.assertEqual(live["run"], "Day 1     Lives 5     Badges 0 / 10     Money $7")
        self.assertEqual(live["trainer"], "Swim Coach")
        self.assertEqual(live["screen"], "battle running, waiting for the result")
        self.assertTrue(live["win"].startswith("62%"), live["win"])
        self.assertEqual(live["action"], "buy Pebbler $3  ->  ok")
        self.assertIn("Chance to win today's battle with the team as it is: 62%.", thinking_live)
        self.assertIn("> buy Pebbler $3  ->  ok", thinking_live)
        # after the run: the last lines are the newest, and the end is announced calmly
        self.assertIn("> Day 1 is over: badges +1, lives +0", app.thinking())
        self.assertTrue(app.thinking().rstrip().endswith("> CONFIRM on the result box  ->  now on 'run_over'"))
        self.assertEqual(app.v["screen"].get(), "end of the run")
        self.assertEqual((app.banner_kind, app.banner_title.cget("text")), ("info", "The run is over."))
        self.assertEqual(self.state(app.start_button), "normal")
        self.assertIn("Log: logs\\run_", app.files.get())

    def test_pause_resume_and_stop_buttons(self):
        app, game = self.app, self.game
        entered, release = held_inside(game, "battle")
        app.start_button.invoke()
        self.pump(entered.is_set, what="the first battle")
        app.pause_button.invoke()                                # pressed while the battle runs
        self.assertEqual(app.mode, "pausing")
        self.assertEqual(str(app.pause_button.cget("text")), "Resume")
        release.set()
        self.pump(lambda: app.mode == "paused", what="the pause")
        self.assertEqual(app.mode_text.get(), gui.MODES["paused"])
        for _ in range(20):                                      # stays held: nothing after the battle
            self.root.update()
            app.drain()
            time.sleep(0.01)
        self.assertEqual(game.journal[-1], "battle")
        entered2, release2 = held_inside(game, "battle")
        app.pause_button.invoke()                                # Resume
        self.assertEqual(str(app.pause_button.cget("text")), "Pause")
        self.pump(entered2.is_set, what="the second battle")
        self.assertEqual(game.journal[game.journal.index("battle") + 1:][:2], ["look", "confirm"])
        self.assertEqual(app.v["run"].get(), "Day 2     Lives 5     Badges 1 / 10     Money $4")
        app.stop_button.invoke()                                 # Stop, in the middle of the second battle
        self.assertEqual(app.mode, "stopping")
        self.assertEqual(self.state(app.stop_button), "disabled")
        release2.set()
        self.pump(lambda: app.mode == "idle", what="the stop")
        self.assertEqual(game.calls[-1], "battle")               # that battle was finished, nothing after it
        self.assertEqual(app.banner_title.cget("text"), "Stopped, as you asked.")
        sessions = list(self.sessions)
        sessions[-1].thread.join(5)
        self.assertFalse(sessions[-1].running)
        # and it can be started again
        app.start_button.invoke()
        self.pump(lambda: app.mode == "idle" and len(self.sessions) == 2 and not self.sessions[-1].running,
                  what="the second session")
        self.assertIsNone(app.capture)

    def test_a_stop_shows_the_reason_and_the_capture_name(self):
        app = self.app
        self.game.unreadable = True
        app.start_button.invoke()
        self.pump(lambda: app.mode == "idle", what="the stop")
        self.assertEqual(app.banner_kind, "needs")
        self.assertEqual(app.banner.winfo_manager(), "grid")     # the red box is in the window
        self.assertEqual(app.banner_title.cget("text"), "THE BOT STOPPED AND NEEDS YOU")
        self.assertIn("money: cannot read '?7'", app.banner_text.cget("text"))
        self.assertEqual(app.banner_capture.cget("text"), "Capture: captures\\unread_test.png")
        app.copy_button.invoke()
        copied = self.root.clipboard_get()
        self.assertIn("unread_test.png", copied)
        self.assertIn("Log: logs\\run_", copied)
        # starting again takes the box away
        self.game.unreadable = False
        app.start_button.invoke()
        self.assertIsNone(app.banner_kind)
        self.assertEqual(app.banner.winfo_manager(), "")
        self.pump(lambda: app.mode == "idle", what="the run")

    def test_the_game_not_being_open_is_said_plainly(self):
        app = self.app
        app.new_session = lambda argv: self.sessions.append(gui.Session(argv, runner=lambda argv, **kw: (
            _ for _ in ()).throw(RuntimeError("Batomon Showdown window not found")))) or self.sessions[-1]
        with mock.patch("sys.stderr", io.StringIO()):
            app.start_button.invoke()
            self.pump(lambda: app.mode == "idle", what="the stop")
        self.assertEqual(app.banner_kind, "error")
        self.assertEqual(app.banner_text.cget("text"),
                         "Batomon Showdown window not found. Open the game first, then press Start.")

    def test_no_run_open_is_explained_with_the_box_to_tick(self):
        app = self.app
        self.game.screen = "main_menu"
        app.start_button.invoke()
        self.pump(lambda: app.mode == "idle", what="the stop")
        self.assertEqual(app.banner_kind, "needs")
        self.assertIn("Tick the first box under Options", app.banner_text.cget("text"))
        self.assertEqual(self.game.calls, [])                    # nothing was pressed on the main menu

    def test_the_options_become_the_arguments_play_py_takes(self):
        app = self.app
        self.assertEqual(app.argv(), [])
        app.new_run.set(True)
        app.limit_days.set(True)
        app.days.set("3")
        app.decide.set("learned")
        self.assertEqual(app.argv(), ["--new-run", "--days", "3", "--learned"])
        app.decide.set("simple")
        app.new_run.set(False)
        self.assertEqual(app.argv(), ["--days", "3", "--simple"])
        app.days.set("lots")
        self.assertIsNone(app.argv())
        app.start_button.invoke()                                # a bad number starts nothing
        self.assertEqual(app.mode, "idle")
        self.assertEqual(self.sessions, [])
        self.assertIn("between 0 and 99", app.mode_text.get())

    def test_closing_the_window_lets_the_bot_finish_its_action_first(self):
        import tkinter as tk
        app = self.app
        entered, release = held_inside(self.game, "battle")
        app.start_button.invoke()
        self.pump(entered.is_set, what="the first battle")
        app.close()                                              # the X, in the middle of a battle
        self.assertTrue(self.sessions[-1].stop_asked)
        self.assertEqual(self.root.winfo_exists(), 1)            # still open: the action is not cut off
        release.set()
        self.sessions[-1].thread.join(5)
        app.drain()
        with self.assertRaises(tk.TclError):                     # now the window is gone
            self.root.winfo_exists()
        self.assertEqual(self.game.calls, ["buy", "battle"])

    def test_the_day_limit_reaches_play_py(self):
        app = self.app
        app.limit_days.set(True)
        app.days.set("1")
        app.start_button.invoke()
        self.pump(lambda: app.mode == "idle", what="the day limit")
        self.assertEqual(self.game.calls, ["buy", "battle", "confirm", "buy"])
        self.assertIn("Stopped before pressing BATTLE!", app.banner_title.cget("text"))


if __name__ == "__main__":
    unittest.main()
