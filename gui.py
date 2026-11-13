"""The bot's control window: Start, Pause / Resume and Stop without a terminal.

    python gui.py                  (or double-click control_window.bat)

It runs play.main() in a second thread with the options ticked in the window, and shows what that
session reports: what the bot is thinking, the state it last read, the last action and its result,
and, in a red box, why it stopped when it cannot read something.

Pause and Stop take effect between two actions: never in the middle of a click or a drag, and never
while the bot waits for a battle to end. After a pause the screen is read again before anything else.

The window starts nothing in the game itself. With the first box ticked, play.py may call
hands.start_casual_run() (Casual Mode is read twice before Confirm is pressed), exactly as
`python play.py --new-run` does. There is no control for Ranked Mode and nothing here clicks.

The window is not kept on top and does not take the keyboard while the bot plays: the bot brings the
game to the front before every click. Keep it beside the game picture, not over it. Pushing the mouse
into a screen corner still aborts (pyautogui's fail-safe); the window then says so.
"""
from __future__ import annotations

import os
import queue
import re
import sys
import threading
import traceback
from datetime import datetime

import play                      # play imports hands and window; window makes the process DPI aware,
import hands as hands_mod        # which has to happen before the first Tk window exists
import window

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

SCREENS = {
    "shop": "shop", "battle": "battle", "matchmaking": "looking for an opponent", "blank": "between two screens",
    "result": "battle result", "stats": "Stats window", "event": "event", "gift_box": "gift box",
    "trinket_pick": "trinket choice", "trainer_pick": "trainer choice", "select_target": "choosing a target",
    "overflow": "team and bench full", "cash_in": "Cash In", "run_over": "end of the run",
    "new_run": "New Run dialog", "main_menu": "main menu", "main_menu_continue": "main menu (a run is open)",
    "continue_confirm": "Continue panel", "title": "title screen", "minimized": "game window minimized",
    "unknown": "not recognised",
}
DOING = {"thinking": "thinking about the shop", "battle": "battle running, waiting for the result"}
TEAM_PLACES = ["top left", "top middle", "top right", "bottom left", "bottom middle", "bottom right"]
STOPPED_HERE = "stopped from the control window"       # play.py's reason when Stop was pressed
MAX_LINES = 3000                                        # lines kept in the thinking pane


# ------------------------------------------------------------ the session ----

class Session(play.Control):
    """One play.main() call in its own thread.

    The bot's side: event() puts what it reports in `events`, and pause_point() is where it waits.
    The window's side: start(), pause(), resume(), stop(). Nothing in here touches Tk.
    """

    def __init__(self, argv: list[str], hands=None, brain=None, runner=None) -> None:
        self.argv = list(argv)
        self.events: queue.Queue = queue.Queue()
        self._hands, self._brain = hands, brain         # only the tests pass these
        self._runner = runner or play.main
        self._cond = threading.Condition()
        self._pause = False
        self._stop = False
        self.thread: threading.Thread | None = None

    # -- the bot's side (called from the worker thread) --
    def event(self, kind: str, **data) -> None:
        self.events.put((kind, data))

    @property
    def stop_asked(self) -> bool:
        return self._stop

    def pause_point(self) -> bool:
        with self._cond:
            if self._stop:
                return True
            if not self._pause:
                return False
            self.event("paused")
            while self._pause and not self._stop:
                self._cond.wait()
            if not self._stop:
                self.event("resumed")
            return True

    def _work(self) -> None:
        code = None
        try:
            code = self._runner(self.argv, control=self, hands=self._hands, brain=self._brain)
        except BaseException as e:                      # shown in the window; the thread ends cleanly
            if type(e).__name__ == "FailSafeException":
                text = ("Emergency stop: the mouse was pushed into a corner of the screen. "
                        "Nothing more was clicked.")
            else:
                traceback.print_exc()
                text = str(e) if isinstance(e, RuntimeError) and str(e) else f"{type(e).__name__}: {e}"
            self.event("error", text=text)
        finally:
            self.event("finished", code=code)

    # -- the window's side --
    def start(self) -> None:
        self.thread = threading.Thread(target=self._work, name="batomon-bot", daemon=True)
        self.thread.start()

    def pause(self) -> None:
        with self._cond:
            self._pause = True

    def resume(self) -> None:
        with self._cond:
            self._pause = False
            self._cond.notify_all()

    def stop(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify_all()

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


# ------------------------------------------------- what the events mean ----

def _place(text: str) -> str:
    """"('team', 0)" in an action's name -> "team top left"."""
    def one(m):
        i = int(m.group(2))
        return f"team {TEAM_PLACES[i]}" if m.group(1) == "team" and i < 6 else f"bench slot {i + 1}"
    return re.sub(r"\('(team|bench)', (\d+)\)", one, text)


def _offered(rec: dict, key: str):
    items, k = rec.get("offered") or rec.get("effects") or [], rec.get(key)
    return items[k] if isinstance(k, int) and 0 <= k < len(items) and items[k] else None


def action_text(kind: str, rec: dict) -> str | None:
    """A few words for one record of the run log, or None when the record is not an action."""
    if "ok" not in rec:
        return None
    if kind == "buy" and rec.get("card"):
        return f"buy {rec['card'].get('name')} (${rec['card'].get('price')})"
    if kind in ("buy", "item", "sell", "reroll", "lock", "move"):
        return _place(rec.get("why") or rec.get("action") or kind)
    if kind == "battle":
        return f"BATTLE! (day {rec.get('day')})"
    if kind == "trainer":
        return f"pick the trainer {_offered(rec, 'picked') or 'card ' + str(rec.get('picked'))}"
    if kind == "trinket":
        return f"take the trinket {_offered(rec, 'picked') or 'card ' + str(rec.get('picked'))}"
    if kind == "event":
        return f"event: {_offered(rec, 'choice') or 'choice ' + str((rec.get('choice') or 0) + 1)}"
    if kind == "select_target":
        return _place(f"target for the event: {tuple(rec['target'])}") if rec.get("target") else "pick a target"
    if kind == "overflow":
        sold = rec.get("sold")
        return "sell " + (f"bench slot {sold + 1}" if isinstance(sold, int) else "the new monster") + " (no room)"
    return {"confirm": "CONFIRM on the result box", "gift": "open the gift box", "cash_in": "Cash In",
            "new_run": "start a Casual run", "continue_run": "Continue on the main menu",
            "confirm_continue": "Confirm on the Continue panel (Casual run)",
            "title": "click on the title screen"}.get(kind, kind)


def activity_line(kind: str, rec: dict) -> tuple[str, bool] | None:
    """(line for the thinking pane, went well) for a record worth showing between the thoughts."""
    what = action_text(kind, rec)
    if what is not None:
        return f"> {what}  ->  {rec.get('message')}", bool(rec.get("ok"))
    if kind == "day_result":
        return f"> Day {rec.get('day')} is over: badges {rec.get('badges', 0):+d}, lives {rec.get('lives', 0):+d}", True
    return None


class Status:
    """What the status pane shows, kept up to date from a session's events."""

    def __init__(self) -> None:
        self.day = self.lives = self.badges = self.badges_goal = self.money = self.trainer = None
        self.screen: str | None = None       # as the reader names it
        self.doing: str | None = None        # "thinking" / "battle", until the screen is read again
        self.win_now: float | None = None    # Plan.win_now of the latest plan for this day
        self.last_action: str | None = None
        self.last_result: str | None = None
        self.last_ok: bool | None = None
        self.ended: str | None = None        # how the session ended when it did not need help

    def apply(self, kind: str, data: dict) -> None:
        if kind == "state":
            s = data["state"]
            self.screen, self.doing = s.get("screen"), None
            if self.screen == "shop":
                if s.get("day") != self.day:
                    self.win_now = None                  # yesterday's chance says nothing about today
                for name in ("day", "lives", "badges", "badges_goal", "money", "trainer"):
                    if s.get(name) is not None:
                        setattr(self, name, s[name])
        elif kind == "doing":
            self.doing = data.get("what")
        elif kind == "plan":
            self.win_now = data.get("win_now")
        elif kind == "log":
            name, rec = data["record"], data["data"]
            what = action_text(name, rec)
            if what is not None:
                self.last_action, self.last_result, self.last_ok = what, rec.get("message"), bool(rec.get("ok"))
                self.doing = None                        # that action is over
                now_on = re.search(r"now on '(\w+)'", str(rec.get("message")))
                if now_on:
                    self.screen = now_on.group(1)        # the hands say where it ended
            if name == "run_over":
                self.ended = "The run is over."
            elif name == "stop" and rec.get("why") == "day limit":
                self.ended = "The number of battles you set is played. Stopped before pressing BATTLE!."
            elif name == "stop" and rec.get("why") == STOPPED_HERE:
                self.ended = "Stopped, as you asked."

    # -- texts --
    def run_line(self) -> str:
        def show(v, pre=""):
            return "-" if v is None else f"{pre}{v}"
        badges = show(self.badges) + (f" / {self.badges_goal}" if self.badges_goal and self.badges is not None else "")
        return f"Day {show(self.day)}     Lives {show(self.lives)}     Badges {badges}     Money {show(self.money, '$')}"

    def screen_line(self) -> str:
        if self.doing == "battle":
            return DOING["battle"]
        text = "-" if self.screen is None else SCREENS.get(self.screen, self.screen)
        return f"{text} ({DOING.get(self.doing, self.doing)})" if self.doing else text

    def win_line(self) -> str:
        return "-" if self.win_now is None else f"{self.win_now:.0%}  (day {self.day}, with the team as it is)"

    def action_line(self) -> str:
        if self.last_action is None:
            return "-"
        return f"{self.last_action}  ->  {self.last_result}" + ("" if self.last_ok else "   (FAILED)")


# -------------------------------------------------- where the window goes ----

def beside(game, works, size, gap: int = 12) -> tuple[int, int]:
    """Top left corner for a window of `size` (w, h) that keeps off the game window.

    game: the game window as (left, top, right, bottom), or None when it is not open.
    works: the usable area of every monitor, same shape. Another monitor than the game's is taken
    first; else right of the game, left of it, below it, above it, whichever fits first. When
    nothing fits (or there is no game) the top right corner of the screen is used.
    """
    w, h = size
    if game is None:
        return works[0][2] - w - gap, works[0][1] + gap
    gl, gt, gr, gb = game
    cx, cy = (gl + gr) // 2, (gt + gb) // 2
    home = next((a for a in works if a[0] <= cx < a[2] and a[1] <= cy < a[3]), works[0])
    for a in works:
        if a is not home:
            return a[0] + gap, a[1] + gap
    left, top, right, bottom = home
    y = max(top, min(max(gt, top), bottom - h))          # level with the game, pushed up if too tall
    x = max(left, min(max(gl, left), right - w))
    for px, py in ((gr + gap, y), (gl - gap - w, y), (x, gb + gap), (x, gt - gap - h)):
        if left <= px and px + w <= right and top <= py and py + h <= bottom:
            return px, py
    return right - w - gap, top + gap


def place_beside_game(root: tk.Tk) -> None:
    """Put the window where beside() says. Never fatal: without it the window opens where Windows likes."""
    try:
        import win32api
        import win32gui
        root.update_idletasks()
        size = root.winfo_reqwidth() + 32, root.winfo_reqheight() + 80      # the frame and the title bar
        works = [win32api.GetMonitorInfo(m[0])["Work"] for m in win32api.EnumDisplayMonitors()]
        hwnd = window.find_window()
        game = win32gui.GetWindowRect(hwnd) if hwnd and not window.is_minimized(hwnd) else None
        root.geometry("+%d+%d" % beside(game, works, size))
    except Exception as e:
        print("control window not placed:", type(e).__name__, e)


# -------------------------------------------------------------- the window ----

RED, CALM, AMBER, GREY = "#b3261e", "#1f5f8b", "#8a5a00", "#5f6368"
MODES = {
    "idle": "Not running.",
    "starting": "Getting ready (finding the game, loading the decision engine) ...",
    "playing": "Playing.",
    "pausing": "Pausing after the current action (a battle is waited out first) ...",
    "paused": "PAUSED. Nothing is clicked until you press Resume.",
    "stopping": "Stopping after the current action (a battle is waited out first) ...",
}


class App:
    POLL_MS = 100

    def __init__(self, root: tk.Tk, new_session=None) -> None:
        self.root = root
        self.new_session = new_session or Session       # the tests pass one with a fake game
        self.session: Session | None = None
        self.status = Status()
        self.mode = "idle"
        self.closing = False
        self.banner_kind: str | None = None             # None, "needs", "error" or "info"
        self.capture: str | None = None                 # file name in captures\ of the last stop
        self._copy_text = ""
        self._ticks = 0
        self._build()
        self._set_mode("idle")
        self._refresh()
        self._check_windows()
        self._after = root.after(self.POLL_MS, self._tick)

    # -- building --
    def _build(self) -> None:
        root = self.root
        root.title("Batomon bot")
        root.protocol("WM_DELETE_WINDOW", self.close)
        base = tkfont.nametofont("TkDefaultFont")
        self.f_bold = base.copy()
        self.f_bold.configure(weight="bold")
        self.f_big = base.copy()
        self.f_big.configure(size=base.cget("size") + 2, weight="bold")
        self.f_mono = tkfont.Font(family="Consolas", size=9)
        self.wrap = self.f_mono.measure("0") * 76          # width of the text column, in pixels
        root.columnconfigure(0, weight=1)
        root.rowconfigure(4, weight=1)
        P = {"padx": "6p", "pady": "3p"}

        # the box that says why the bot stopped (hidden until then)
        self.banner = tk.Frame(root, bg=RED)
        self.banner.columnconfigure(0, weight=1)
        self.banner_title = tk.Label(self.banner, bg=RED, fg="white", font=self.f_big, anchor="w", justify="left")
        self.banner_text = tk.Label(self.banner, bg=RED, fg="white", anchor="w", justify="left", wraplength=self.wrap)
        self.banner_capture = tk.Label(self.banner, bg=RED, fg="white", font=self.f_bold, anchor="w",
                                       justify="left", wraplength=self.wrap)
        self.banner_buttons = tk.Frame(self.banner, bg=RED)
        self.open_button = ttk.Button(self.banner_buttons, text="Open the capture", command=self.open_capture)
        self.copy_button = ttk.Button(self.banner_buttons, text="Copy this for Claude", command=self.copy_stop)
        self.open_button.pack(side="left", padx=(0, "6p"))
        self.copy_button.pack(side="left")
        self.banner_title.grid(row=0, column=0, sticky="ew", padx="8p", pady=("6p", 0))
        self.banner_text.grid(row=1, column=0, sticky="ew", padx="8p")
        self.banner_capture.grid(row=2, column=0, sticky="ew", padx="8p")
        self.banner_buttons.grid(row=3, column=0, sticky="w", padx="8p", pady="6p")

        # options: the same ones play.py takes
        opts = ttk.LabelFrame(root, text="Options", padding="6p")
        opts.grid(row=1, column=0, sticky="ew", **P)
        self.new_run = tk.BooleanVar(value=False)
        self.limit_days = tk.BooleanVar(value=False)
        self.days = tk.StringVar(value="1")
        self.decide = tk.StringVar(value="planner")
        self.option_widgets = []
        w = ttk.Checkbutton(opts, variable=self.new_run,
                            text="If no run is open, start a new Casual run (never Ranked)")
        w.grid(row=0, column=0, columnspan=4, sticky="w")
        self.option_widgets.append(w)
        w = ttk.Checkbutton(opts, variable=self.limit_days, text="Stop after")
        w.grid(row=1, column=0, sticky="w")
        self.option_widgets.append(w)
        w = ttk.Spinbox(opts, from_=0, to=99, width=3, textvariable=self.days)
        w.grid(row=1, column=1, sticky="w", padx="4p")
        self.option_widgets.append(w)
        ttk.Label(opts, text="battles (otherwise it plays until the run ends)").grid(row=1, column=2, sticky="w")
        how = ttk.Frame(opts)
        how.grid(row=2, column=0, columnspan=4, sticky="w", pady=("3p", 0))
        ttk.Label(how, text="Decide with:").pack(side="left")
        for value, text in (("planner", "the planner (normal)"), ("learned", "the learned policy"),
                            ("simple", "the old simple rules")):
            w = ttk.Radiobutton(how, variable=self.decide, value=value, text=text)
            w.pack(side="left", padx=("6p", 0))
            self.option_widgets.append(w)

        # the buttons
        bar = ttk.Frame(root)
        bar.grid(row=2, column=0, sticky="ew", **P)
        self.start_button = ttk.Button(bar, text="Start", command=self.start)
        self.pause_button = ttk.Button(bar, text="Pause", command=self.pause_resume)
        self.stop_button = ttk.Button(bar, text="Stop", command=self.stop)
        for b in (self.start_button, self.pause_button, self.stop_button):
            b.pack(side="left", padx=(0, "6p"))
        self.mode_text = tk.StringVar()
        self.mode_label = ttk.Label(root, textvariable=self.mode_text, font=self.f_bold, wraplength=self.wrap)
        self.mode_label.grid(row=3, column=0, sticky="ew", padx="6p")

        body = ttk.Frame(root)
        body.grid(row=4, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(2, weight=1)
        self.warning = tk.StringVar()
        self.warning_label = tk.Label(body, textvariable=self.warning, fg=AMBER, font=self.f_bold, anchor="w",
                                      justify="left", wraplength=self.wrap)

        # status
        st = ttk.LabelFrame(body, text="Status", padding="6p")
        st.grid(row=1, column=0, sticky="ew", **P)
        st.columnconfigure(1, weight=1)
        self.v = {name: tk.StringVar(value="-") for name in ("run", "trainer", "screen", "win", "action", "game")}
        ttk.Label(st, textvariable=self.v["run"], font=self.f_big).grid(row=0, column=0, columnspan=2, sticky="w")
        rows = (("trainer", "Trainer"), ("screen", "Screen"), ("win", "Win chance today"),
                ("action", "Last action"), ("game", "Game window"))
        self.value_labels = {}
        for r, (name, caption) in enumerate(rows, start=1):
            ttk.Label(st, text=caption + ":", foreground=GREY).grid(row=r, column=0, sticky="nw", padx=(0, "8p"))
            lab = ttk.Label(st, textvariable=self.v[name], wraplength=self.wrap - self.f_mono.measure("0") * 18,
                            justify="left")
            lab.grid(row=r, column=1, sticky="w")
            self.value_labels[name] = lab

        # thinking
        th = ttk.LabelFrame(body, text="Thinking (newest at the bottom)", padding="3p")
        th.grid(row=2, column=0, sticky="nsew", **P)
        th.columnconfigure(0, weight=1)
        th.rowconfigure(0, weight=1)
        self.text = tk.Text(th, width=76, height=22, wrap="word", font=self.f_mono, state="disabled",
                            borderwidth=0, padx=4, pady=4)
        scroll = ttk.Scrollbar(th, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.tag_configure("head", foreground=GREY)
        self.text.tag_configure("done", foreground=CALM)
        self.text.tag_configure("bad", foreground=RED)

        self.files = tk.StringVar(value="Emergency stop: push the mouse into a corner of the screen.")
        ttk.Label(root, textvariable=self.files, foreground=GREY, wraplength=self.wrap, justify="left").grid(
            row=5, column=0, sticky="ew", padx="6p", pady=(0, "4p"))

    # -- the options, as the arguments play.py takes --
    def argv(self) -> list[str] | None:
        out = []
        if self.new_run.get():
            out.append("--new-run")
        if self.limit_days.get():
            text = self.days.get().strip()
            if not text.isdigit() or not 0 <= int(text) <= 99:
                return None
            out += ["--days", str(int(text))]
        if self.decide.get() == "simple":
            out.append("--simple")
        elif self.decide.get() == "learned":
            out.append("--learned")
        return out

    # -- the buttons --
    def start(self) -> None:
        if self.session is not None and self.session.running:
            return
        argv = self.argv()
        if argv is None:
            self.mode_text.set("Not started: the number of battles must be between 0 and 99.")
            return
        self.drain()
        self._hide_banner()
        self.status = Status()
        self._say([f"=== {datetime.now():%H:%M:%S}  Start"
                   f"{' with ' + ' '.join(argv) if argv else ''} ==="], "head")
        self.session = self.new_session(argv)
        self.session.start()
        self._set_mode("starting")
        self._refresh()

    def pause_resume(self) -> None:
        if self.session is None or not self.session.running:
            return
        if self.mode in ("starting", "playing"):
            self.session.pause()
            self._set_mode("pausing")
        elif self.mode in ("pausing", "paused"):
            self.session.resume()
            self._set_mode("playing")

    def stop(self) -> None:
        if self.session is None or not self.session.running:
            return
        self.session.stop()
        self._set_mode("stopping")

    def close(self) -> None:
        """The window's X: the bot first finishes what it is doing, so no click or drag is cut in half."""
        if self.session is not None and self.session.running:
            if self.closing and not messagebox.askyesno(
                    "Batomon bot", "The bot is still finishing an action (a battle can take a few minutes).\n\n"
                                   "Close now anyway?", parent=self.root):
                return
            if not self.closing:
                self.closing = True
                self.session.stop()
                self._set_mode("stopping")
                self.mode_text.set("Closing after the current action ... (press X again to close at once)")
                return
        self.destroy()

    def destroy(self) -> None:
        try:
            self.root.after_cancel(self._after)
            self.root.destroy()
        except tk.TclError:
            pass

    def open_capture(self) -> None:
        path = hands_mod.CAPTURE_DIR / self.capture if self.capture else hands_mod.CAPTURE_DIR
        try:
            os.startfile(path if path.exists() else hands_mod.CAPTURE_DIR)
        except OSError as e:
            self.mode_text.set(f"Could not open {path}: {e}")

    def copy_stop(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self._copy_text)

    # -- what the session reports --
    def _tick(self) -> None:
        self.drain()
        self._ticks += 1
        if self._ticks % 20 == 0:
            self._check_windows()
        self._after = self.root.after(self.POLL_MS, self._tick)

    def drain(self) -> None:
        """Take everything the session has reported so far and show it."""
        if self.session is None:
            return
        changed = False
        for _ in range(500):
            try:
                kind, data = self.session.events.get_nowait()
            except queue.Empty:
                break
            self._handle(kind, data)
            changed = True
            if kind == "finished" and self.closing:
                self.destroy()
                return
        if changed:
            self._refresh()

    def _handle(self, kind: str, data: dict) -> None:
        self.status.apply(kind, data)
        if kind == "start":
            self.files.set(f"Log: logs\\{data['log']}  and  logs\\{data['thinking']}\n"
                           f"Emergency stop: push the mouse into a corner of the screen.")
            if self.mode == "starting":
                self._set_mode("playing")
        elif kind == "think":
            self._say(list(data["lines"]) + [""])
        elif kind == "log":
            line = activity_line(data["record"], data["data"])
            if line:
                self._say([line[0], ""], "done" if line[1] else "bad")
        elif kind == "paused":
            if self.mode == "pausing":
                self._set_mode("paused")
        elif kind == "resumed":
            if self.mode in ("pausing", "paused"):
                self._set_mode("playing")
        elif kind == "needs_you":
            why = data.get("why") or "no reason was given"
            capture = data.get("capture")
            if not capture:
                m = re.search(r"capture: ([\w.\-]+\.png)", why)
                capture = m.group(1) if m else None
            if "--new-run" in why:
                why = ("No run is open in the game. Tick the first box under Options to let the bot start a "
                       "Casual run, then press Start.")
            self._show_banner("needs", "THE BOT STOPPED AND NEEDS YOU", why, capture, data.get("log"))
        elif kind == "error":
            text = data.get("text") or "unknown error"
            if "window not found" in text:
                text += ". Open the game first, then press Start."
            self._show_banner("error", "THE BOT STOPPED", text, None, None)
        elif kind == "finished":
            self._set_mode("idle")
            if self.banner_kind is None:
                if data.get("code") == 0 or self.status.ended:
                    self._show_banner("info", self.status.ended or "The session has ended.", "", None, None)
                else:
                    self._show_banner("error", "THE BOT STOPPED", "It gave no reason. Look at the last lines "
                                      "under Thinking and at the log named below.", None, None)

    def _say(self, lines: list[str], tag: str | None = None) -> None:
        """Add lines to the thinking pane; it follows the newest unless you have scrolled up."""
        at_end = self.text.yview()[1] >= 0.999
        self.text.configure(state="normal")
        self.text.insert("end", "\n".join(lines) + "\n", (tag,) if tag else ())
        extra = int(self.text.index("end-1c").split(".")[0]) - MAX_LINES
        if extra > 0:
            self.text.delete("1.0", f"{extra + 1}.0")
        self.text.configure(state="disabled")
        if at_end:
            self.text.see("end")

    def thinking(self) -> str:
        return self.text.get("1.0", "end-1c")

    # -- showing --
    def _set_mode(self, mode: str) -> None:
        self.mode = mode
        self.mode_text.set(MODES[mode])
        running = mode != "idle"
        self.start_button.configure(state="disabled" if running else "normal")
        self.pause_button.configure(state="normal" if mode in ("starting", "playing", "pausing", "paused") else "disabled",
                                    text="Resume" if mode in ("pausing", "paused") else "Pause")
        self.stop_button.configure(state="normal" if mode in ("starting", "playing", "pausing", "paused") else "disabled")
        for w in self.option_widgets:
            w.configure(state="disabled" if running else "normal")

    def _refresh(self) -> None:
        s = self.status
        self.v["run"].set(s.run_line())
        self.v["trainer"].set(s.trainer or "-")
        self.v["screen"].set(s.screen_line())
        self.v["win"].set(s.win_line())
        self.v["action"].set(s.action_line())
        self.value_labels["action"].configure(foreground=RED if s.last_ok is False else "")

    def _show_banner(self, kind: str, title: str, text: str, capture: str | None, log: str | None) -> None:
        colour = CALM if kind == "info" else RED
        for w in (self.banner, self.banner_title, self.banner_text, self.banner_capture, self.banner_buttons):
            w.configure(bg=colour)
        self.banner_kind, self.capture = kind, capture
        self.banner_title.configure(text=title)
        if kind == "needs":
            text += "\nNothing was clicked after this. Look at the game, then tell Claude what it shows."
            where = f"Capture: captures\\{capture}" if capture else "No capture was saved for this stop."
        else:
            where = ""
        self.banner_text.configure(text=text)
        self.banner_capture.configure(text=where)
        self._copy_text = "\n".join(x for x in (title, text, where, f"Log: logs\\{log}" if log else "") if x)
        for w, show in ((self.banner_text, bool(text)), (self.banner_capture, bool(where)),
                        (self.banner_buttons, kind != "info")):
            w.grid() if show else w.grid_remove()
        self.open_button.configure(text="Open the capture" if capture else "Open the captures folder")
        self.banner.grid(row=0, column=0, sticky="ew")
        if kind != "info":
            self._call_attention()

    def _hide_banner(self) -> None:
        self.banner_kind = self.capture = None
        self.banner.grid_remove()

    def _call_attention(self) -> None:
        """Bring the window into view and flash its taskbar button, without taking the keyboard.
        Only used once the bot has stopped clicking."""
        try:
            if self.root.state() != "normal":
                return
            import ctypes
            self.root.attributes("-topmost", True)
            self.root.after(400, self._not_topmost)
            user32 = ctypes.windll.user32
            user32.GetParent.restype = ctypes.c_void_p
            user32.FlashWindow(ctypes.c_void_p(user32.GetParent(self.root.winfo_id())), True)
        except Exception:
            pass

    def _not_topmost(self) -> None:
        try:
            self.root.attributes("-topmost", False)
        except tk.TclError:
            pass

    def _check_windows(self) -> None:
        """Is the game there, at the size the reader needs, and is this window off its picture?"""
        over = False
        try:
            hwnd = window.find_window()
            if hwnd is None:
                game = "not found (open Batomon Showdown first)"
            elif window.is_minimized(hwnd):
                game = "minimized (the bot cannot read a minimized window)"
            else:
                pic = window.picture_rect(window.client_rect(hwnd))
                right_size = (pic.width, pic.height) == (window.CANON_W, window.CANON_H)
                game = f"open, picture {pic.width} x {pic.height}" + (
                    "" if right_size else f" (the reader needs {window.CANON_W} x {window.CANON_H})")
                x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
                over = (self.root.state() == "normal" and x < pic.right and pic.left < x + self.root.winfo_width()
                        and y < pic.bottom and pic.top < y + self.root.winfo_height())
        except Exception as e:
            game = f"could not be checked ({type(e).__name__})"
        self.v["game"].set(game)
        if over:
            self.warning.set("This window is over the game picture. Move it beside the game: the bot brings "
                             "the game to the front when it clicks, and this window would end up behind it.")
            self.warning_label.grid(row=0, column=0, sticky="ew", padx="6p")
        else:
            self.warning.set("")
            self.warning_label.grid_remove()


def main() -> int:
    if sys.stdout is None or sys.stderr is None:
        # started without a console (pythonw): keep what play.py prints, and any error, in a file
        hands_mod.LOG_DIR.mkdir(exist_ok=True)
        sys.stdout = sys.stderr = open(hands_mod.LOG_DIR / "control_window_console.txt", "a",
                                       encoding="utf-8", buffering=1)
        print(f"\n=== control window opened {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    root = tk.Tk()
    App(root)
    place_beside_game(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
