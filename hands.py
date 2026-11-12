"""Mouse actions on the shop screen, each one checked against a fresh capture.

    hands = Hands(dry_run=True)       # dry_run: work out and log the clicks, send nothing
    result = hands.buy(2)             # Result(ok, message, before, after)

Rules built in:
- Input is only ever sent on the shop screen. This module cannot start a run,
  so it cannot start a Ranked run.
- Before an action the state must read cleanly (no "problems"); after it the
  screen is captured again and compared with what the action should have done.
  If anything is off, ok is False and the caller must stop.
- pyautogui's fail-safe stays on: push the mouse into a screen corner to abort.
- Every state, action and result is appended to logs/actions_<date>.jsonl.

Not covered yet (no captures of those screens exist): fast forward, confirming
the battle result, the trinket choice. battle() presses BATTLE! and then stops.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import reader
import window

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
CAPTURE_DIR = ROOT / "captures"

PARK = (2300, 640, 2340, 680)     # empty background: the pointer rests here, hovering nothing
SETTLE_S = 0.6                    # wait after an action before capturing again


@dataclass
class Result:
    ok: bool
    message: str
    before: dict | None = None
    after: dict | None = None
    clicks: list = field(default_factory=list)
    battle: dict | None = None        # battle(): both teams as read at the start


# ------------------------------------------------- checks (pure functions) ----

def _slots(state: dict, where: str) -> list:
    return state[where]


def _owned_count(state: dict) -> int:
    return sum(s is not None for s in state["team"] + state["bench"])


def check_buy(before: dict, after: dict, i: int) -> str | None:
    """None if 'after' looks like 'before' plus buying shop slot i, else what is wrong."""
    card = before["shop"][i]
    if after.get("screen") != "shop":
        return f"screen became '{after.get('screen')}'"
    if after["money"] is None:
        return "money cannot be read after the click"
    if card["kind"] == "item":
        # items can pay out (Lucky Coin gave +$3), so only the card itself must be gone
        if after["money"] < before["money"] - card["price"]:
            return f"money went {before['money']} -> {after['money']}, more than the price"
        if after["shop"][i] == card:
            return "the item card is still there"
        return None
    if after["money"] != before["money"] - card["price"]:
        return f"money went {before['money']} -> {after['money']}, expected -{card['price']}"
    if card["kind"] == "monster":
        # one more monster owned, or the same number if it merged into a copy
        gained = _owned_count(after) - _owned_count(before)
        if gained not in (0, 1):
            return f"owned monsters changed by {gained}"
        if gained == 0 and after["team"] == before["team"] and after["bench"] == before["bench"]:
            return "nothing changed on team or bench"
    return None


def check_move(before: dict, after: dict, src: tuple[str, int], dst: tuple[str, int]) -> str | None:
    if after.get("screen") != "shop":
        return f"screen became '{after.get('screen')}'"
    if after["money"] != before["money"]:
        return "money changed during a move"
    moved = _slots(before, src[0])[src[1]]
    target = _slots(before, dst[0])[dst[1]]
    now_src = _slots(after, src[0])[src[1]]
    now_dst = _slots(after, dst[0])[dst[1]]
    if now_dst is None:
        return "target slot is still empty"
    if target is None and now_src is not None:
        return "source slot is still occupied"
    if target is not None and now_src is None and now_dst["level"] == target["level"]:
        return "source emptied but target did not level up"
    if moved["stats"] != now_dst["stats"] and target is None:
        return "monster in the target slot has different stats"
    return None


def check_sell(before: dict, after: dict, src: tuple[str, int]) -> str | None:
    if after.get("screen") != "shop":
        return f"screen became '{after.get('screen')}'"
    if _slots(after, src[0])[src[1]] is not None:
        return "slot is still occupied"
    if after["money"] <= before["money"]:
        return f"money did not go up ({before['money']} -> {after['money']})"
    return None


def check_reroll(before: dict, after: dict) -> str | None:
    if after.get("screen") != "shop":
        return f"screen became '{after.get('screen')}'"
    if after["money"] != before["money"] - before["reroll_price"]:
        return f"money went {before['money']} -> {after['money']}, expected -{before['reroll_price']}"
    return None


# ------------------------------------------------------------------ hands ----

class Hands:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.hwnd = window.find_window()
        if self.hwnd is None:
            raise RuntimeError("Batomon Showdown window not found")
        LOG_DIR.mkdir(exist_ok=True)
        self.log_path = LOG_DIR / f"actions_{datetime.now():%Y%m%d}.jsonl"

    # -- seeing --
    def look(self, save_if_unreadable: bool = True) -> dict:
        if window.is_minimized(self.hwnd):
            return {"screen": "minimized", "problems": ["game window is minimized"]}
        # A shine sweeps across shop cards of monsters you already own and can cut
        # through their text, so a shop that does not read cleanly is read again.
        for attempt in range(4):
            img = window.capture_client(self.hwnd)
            self.last_image = img
            state = reader.read_state(img)
            if state["screen"] != "shop" or not state["problems"]:
                break
            time.sleep(0.45)
        if save_if_unreadable and state["problems"]:
            CAPTURE_DIR.mkdir(exist_ok=True)
            path = CAPTURE_DIR / f"unread_{datetime.now():%Y%m%d_%H%M%S_%f}.png"
            img.save(path)
            state["saved_capture"] = path.name
        return state

    def _log(self, action: str, result: Result) -> Result:
        rec = {"time": datetime.now().isoformat(timespec="seconds"), "action": action,
               "dry_run": self.dry_run, "ok": result.ok, "message": result.message,
               "clicks": result.clicks, "before": result.before, "after": result.after}
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        return result

    # -- pointing --
    def screen_point(self, box: reader.Box) -> tuple[int, int]:
        fx, fy = reader.box_to_frac(box)
        return window.frac_to_screen(window.client_rect(self.hwnd), fx, fy)

    def _focus(self) -> None:
        """Bring the game window to the front, or raise if that fails."""
        import win32api
        import win32gui
        import win32process
        if win32gui.GetForegroundWindow() == self.hwnd:
            return
        # Windows only lets the thread that owns the foreground window hand focus
        # over, so attach to it for the duration of the call.
        fg = win32gui.GetForegroundWindow()
        me = win32api.GetCurrentThreadId()
        other = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
        attached = False
        try:
            if other and other != me:
                try:
                    win32process.AttachThreadInput(me, other, True)
                    attached = True
                except Exception:
                    pass
            try:
                win32gui.BringWindowToTop(self.hwnd)
                win32gui.SetForegroundWindow(self.hwnd)
            except Exception:
                pass
        finally:
            if attached:
                win32process.AttachThreadInput(me, other, False)
        time.sleep(0.3)
        if win32gui.GetForegroundWindow() != self.hwnd:
            raise RuntimeError("could not bring the game window to the front; click on the game once and retry")

    def _click(self, box: reader.Box) -> list:
        x, y = self.screen_point(box)
        if not self.dry_run:
            import pyautogui
            self._focus()
            pyautogui.moveTo(x, y, duration=0.15)
            pyautogui.mouseDown()
            time.sleep(0.06)
            pyautogui.mouseUp()
            pyautogui.moveTo(*self.screen_point(PARK), duration=0.15)
        return [["click", x, y]]

    def _drag(self, src: reader.Box, dst: reader.Box) -> list:
        x0, y0 = self.screen_point(src)
        x1, y1 = self.screen_point(dst)
        if not self.dry_run:
            import pyautogui
            self._focus()
            pyautogui.moveTo(x0, y0, duration=0.15)
            pyautogui.mouseDown()
            time.sleep(0.12)
            pyautogui.moveTo(x1, y1, duration=0.35)
            time.sleep(0.12)
            pyautogui.mouseUp()
            pyautogui.moveTo(*self.screen_point(PARK), duration=0.15)
        return [["drag", x0, y0, x1, y1]]

    def _scroll(self, box: reader.Box, clicks: int) -> list:
        """Turn the mouse wheel over a box (negative = scroll down)."""
        x, y = self.screen_point(box)
        if not self.dry_run:
            import pyautogui
            self._focus()
            pyautogui.moveTo(x, y, duration=0.15)
            pyautogui.scroll(clicks)
            time.sleep(0.3)
        return [["scroll", x, y, clicks]]

    # -- the common shape of every action --
    def _act(self, name: str, precheck, do, check) -> Result:
        before = self.look()
        if before.get("screen") != "shop":
            return self._log(name, Result(False, f"not on the shop screen ({before.get('screen')})", before))
        if before["problems"]:
            return self._log(name, Result(False, "state not read cleanly: " + "; ".join(before["problems"]), before))
        why = precheck(before)
        if why:
            return self._log(name, Result(False, why, before))
        clicks = do()
        if self.dry_run:
            return self._log(name, Result(True, "dry run: nothing sent", before, None, clicks))
        time.sleep(SETTLE_S)
        after = self.look(save_if_unreadable=False)
        if after.get("screen") != "shop":
            # a third copy makes a monster level up, and a gift box slides in over the shop
            after = self.wait_for({"shop", "gift_box"}, 8)
        elif after.get("problems"):
            after = self.look()           # read again, saving the capture this time
        if after.get("screen") == "gift_box":
            return self._log(name, Result(True, "ok: a monster leveled up, gift box showing", before, after, clicks))
        if after.get("problems"):
            # an unreadable state cannot be checked; report that, not a guess
            why = "state after the action not read cleanly: " + "; ".join(after["problems"])
        else:
            why = check(before, after)
        return self._log(name, Result(why is None, why or "ok", before, after, clicks))

    @staticmethod
    def _slot_box(where: tuple[str, int]) -> reader.Box:
        kind, i = where
        return reader.team_slot(i) if kind == "team" else reader.bench_slot(i)

    # -- actions --
    def buy(self, i: int) -> Result:
        """Click shop card i: buys a monster, or uses an item."""
        def pre(s):
            card = s["shop"][i]
            if card is None:
                return f"shop slot {i} is empty"
            if card["price"] > s["money"]:
                return f"{card['name']} costs ${card['price']}, only ${s['money']}"
            if card["kind"] == "monster" and reader_free_slots(s) == 0 and not _has_copy(s, card["name"]):
                return "no free team or bench slot"
            return None
        result = self._act(f"buy {i}", pre, lambda: self._click(reader.shop_card(i)),
                           lambda b, a: check_buy(b, a, i))
        if result.ok and result.after and result.after.get("screen") == "shop":
            self._learn_new_sprite(result.before, result.after, i)
        return result

    def _learn_new_sprite(self, before: dict, after: dict, i: int) -> None:
        """Team slots show no name. Right after a buy we know which monster the
        newly filled slot holds, so save its sprite under that name."""
        import numpy as np
        card = before["shop"][i]
        if card["kind"] != "monster":
            return
        new = [(kind, k) for kind in ("team", "bench") for k in range(len(before[kind]))
               if before[kind][k] is None and after[kind][k] is not None]
        if len(new) != 1:
            return
        kind, k = new[0]
        slot = after[kind][k]
        if slot["name"] is None:
            pic = np.asarray(window.canonical_picture(self.last_image))
            reader.learn_sprite(card["name"], reader.crop(pic, self._slot_box(new[0])))
            slot["name"] = card["name"]
        elif slot["name"] != card["name"]:
            raise RuntimeError(f"bought {card['name']} but the sprite in {kind} {k} matches {slot['name']}")

    use_item = buy

    def move(self, src: tuple[str, int], dst: tuple[str, int]) -> Result:
        """Drag a monster, e.g. move(("team", 4), ("bench", 0))."""
        def pre(s):
            if _slots(s, src[0])[src[1]] is None:
                return f"{src[0]} slot {src[1]} is empty"
            return None
        return self._act(f"move {src} -> {dst}", pre,
                         lambda: self._drag(self._slot_box(src), self._slot_box(dst)),
                         lambda b, a: check_move(b, a, src, dst))

    def sell(self, src: tuple[str, int]) -> Result:
        """Drag a monster onto the shop bar."""
        def pre(s):
            if _slots(s, src[0])[src[1]] is None:
                return f"{src[0]} slot {src[1]} is empty"
            return None
        return self._act(f"sell {src}", pre,
                         lambda: self._drag(self._slot_box(src), reader.SELL_BAR),
                         lambda b, a: check_sell(b, a, src))

    def reroll(self) -> Result:
        def pre(s):
            if s["reroll_price"] > s["money"]:
                return f"reroll costs ${s['reroll_price']}, only ${s['money']}"
            return None
        return self._act("reroll", pre, lambda: self._click(reader.REROLL_BUTTON), check_reroll)

    def lock(self) -> Result:
        """Press LOCK / UNLOCK. Locking puts a padlock on every shop card (it keeps
        the shop for the next day) and the button then reads UNLOCK."""
        def check(b, a):
            if a.get("screen") != "shop":
                return f"screen became '{a.get('screen')}'"
            if a["locked"] == b["locked"]:
                return "lock state did not change"
            return None
        return self._act("lock", lambda s: None, lambda: self._click(reader.LOCK_BUTTON), check)

    # -- screens after the shop --
    def wait_for(self, wanted: set[str], timeout: float = 120, unknown_limit: float = 25) -> dict:
        """Watch the game until one of the wanted screens shows (twice in a row).

        During a battle, turns fast forward on if it is off. Gives up at the
        timeout, or when an unrecognised screen stays for unknown_limit seconds
        (fades and the VS animation are shorter); the capture is then saved.
        """
        import numpy as np
        start = time.time()
        unknown_since = None
        hits = 0
        ff_clicked = False
        state: dict = {}
        while time.time() - start < timeout:
            state = self.look(save_if_unreadable=False)
            screen = state["screen"]
            if screen == "battle":
                # keep an early frame of the battle: both teams with their starting badges
                self._battle_frames = getattr(self, "_battle_frames", 0) + 1
                if self._battle_frames == 2:
                    self.battle_start_image = self.last_image
            if screen in wanted:
                hits += 1
                if hits >= 2:
                    return self.look()
            else:
                hits = 0
            if screen == "unknown":
                unknown_since = unknown_since or time.time()
                if time.time() - unknown_since > unknown_limit:
                    break
            else:
                unknown_since = None
            if screen == "battle" and not ff_clicked and not self.dry_run:
                pic = np.asarray(window.canonical_picture(self.last_image))
                if not reader.fast_forward_on(pic):
                    self._click(reader.FAST_FORWARD)
                    ff_clicked = True
            time.sleep(0.4)
        path = CAPTURE_DIR / f"stuck_{datetime.now():%Y%m%d_%H%M%S}.png"
        self.last_image.save(path)
        state["saved_capture"] = path.name
        state.setdefault("problems", []).append(
            f"waited for {sorted(wanted)}, stuck on '{state.get('screen')}'")
        return state

    def _press_and_wait(self, name: str, on: str, box: reader.Box, wanted: set[str], timeout: float) -> Result:
        before = self.look()
        if before.get("screen") != on:
            return self._log(name, Result(False, f"not on the {on} screen ({before.get('screen')})", before))
        if before["problems"]:
            return self._log(name, Result(False, "state not read cleanly: " + "; ".join(before["problems"]), before))
        clicks = self._click(box)
        if self.dry_run:
            return self._log(name, Result(True, "dry run: nothing sent", before, None, clicks))
        after = self.wait_for(wanted, timeout)
        ok = after.get("screen") in wanted
        return self._log(name, Result(ok, f"now on '{after.get('screen')}'", before, after, clicks))

    def battle(self) -> Result:
        """Press BATTLE! and watch until the result box shows.

        An early frame of the battle is kept and read after the battle (reading both teams
        takes a few seconds): result.battle holds both teams, as reader.read_battle()
        returns them, and where the start and result captures were saved.
        """
        self._battle_frames = 0
        self.battle_start_image = None
        r = self._press_and_wait("battle", "shop", reader.BATTLE_BUTTON, {"result"}, 300)
        if not self.dry_run:
            r.battle = self._record_battle(r.ok)
        return r

    def _record_battle(self, reached_result: bool) -> dict:
        folder = CAPTURE_DIR / "battles"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
        out: dict = {"start_capture": None, "result_capture": None}
        if reached_result and self.last_image is not None:
            path = folder / f"{stamp}_result.png"
            self.last_image.save(path)
            out["result_capture"] = str(path.relative_to(ROOT))
        img = self.battle_start_image
        if img is None:
            out["problems"] = ["no battle frame was seen"]
            return out
        path = folder / f"{stamp}_start.png"
        img.save(path)
        out["start_capture"] = str(path.relative_to(ROOT))
        import numpy as np
        try:
            out.update(reader.read_battle(np.asarray(window.canonical_picture(img))))
        except Exception as e:     # a reading bug must not stop the run; the capture is kept
            out["problems"] = [f"battle screen not read: {type(e).__name__}: {e}"]
        return out

    def read_battle_stats(self) -> dict:
        """On the result box: open Stats, read both teams' numbers, close it again.

        Best effort: reading problems come back in "problems" and the run goes on. Only a
        window that will not close is reported in "stuck" (the caller must stop then).
        Both captures are kept in captures/battles/.
        """
        import numpy as np
        out: dict = {"problems": [], "stuck": False}
        if self.dry_run:
            return out
        before = self.look()
        if before.get("screen") != "result":
            out["problems"].append(f"stats: not on the result screen ({before.get('screen')})")
            return out
        folder = CAPTURE_DIR / "battles"
        folder.mkdir(parents=True, exist_ok=True)
        stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
        pic = np.asarray(window.canonical_picture(self.last_image))
        try:
            out["end_hp_fraction"] = reader.read_result_hp(pic)
        except Exception as e:
            out["problems"].append(f"end HP not read: {type(e).__name__}: {e}")
        self._click(reader.RESULT_STATS)
        state = self.wait_for({"stats"}, 10)
        if state.get("screen") != "stats":
            out["problems"].append(f"stats: window did not open ({state.get('screen')})")
            return out
        top = self.last_image
        top.save(folder / f"{stamp}_stats_top.png")
        scrolled = None
        try:
            self._scroll(reader.STATS_SCROLL_POINT, -15)
            time.sleep(0.5)
            self.look(save_if_unreadable=False)
            if reader.detect_screen(np.asarray(window.canonical_picture(self.last_image))) == "stats":
                scrolled = self.last_image
                scrolled.save(folder / f"{stamp}_stats_bottom.png")
        except Exception as e:
            out["problems"].append(f"stats: scrolling failed: {type(e).__name__}: {e}")
        try:
            canon = lambda im: np.asarray(window.canonical_picture(im))
            out.update(reader.read_stats(canon(top), canon(scrolled) if scrolled is not None else None))
        except Exception as e:
            out["problems"].append(f"stats not read: {type(e).__name__}: {e}")
        out["captures"] = [f"captures/battles/{stamp}_stats_top.png"] + (
            [f"captures/battles/{stamp}_stats_bottom.png"] if scrolled is not None else [])
        self._click(reader.STATS_CLOSE)
        after = self.wait_for({"result"}, 10)
        if after.get("screen") != "result":
            out["stuck"] = True
            out["problems"].append(f"stats: window did not close ({after.get('screen')})")
        return out

    def confirm_result(self) -> Result:
        """Press CONFIRM on the result box; the next shop, an event or the end of the run follows."""
        return self._press_and_wait("confirm result", "result", reader.RESULT_CONFIRM,
                                    {"shop", "event", "run_over", "gift_box", "trinket_pick"}, 40)

    def start_casual_run(self) -> Result:
        """Start a new CASUAL Pantra run from the end-of-run screen or the New Run dialog.

        Rule 1 of the project: never start a Ranked run. CONFIRM is pressed only
        when two fresh captures in a row both show Casual Mode selected (blue),
        Ranked Mode not selected (grey) and Pantra selected. This method never
        clicks the Ranked Mode button, and there is no ranked counterpart.
        """
        name = "start casual run"
        before = self.look()
        if before["screen"] == "run_over":
            self._click(reader.RUN_OVER_NEW_RUN)
            if self.dry_run:
                return self._log(name, Result(True, "dry run: nothing sent", before))
            state = self.wait_for({"new_run"}, 15)
        else:
            state = before
        if state["screen"] != "new_run":
            return self._log(name, Result(False, f"New Run dialog not showing ({state['screen']})", before, state))
        if self.dry_run:
            return self._log(name, Result(True, "dry run: nothing sent", before))

        if state.get("region") != "Pantra":
            self._click(reader.NEW_RUN_PANTRA)
            time.sleep(SETTLE_S)
            state = self.look()
        if state.get("screen") == "new_run" and state.get("mode") != "casual":
            self._click(reader.NEW_RUN_CASUAL)
            time.sleep(SETTLE_S)
            state = self.look()

        # the gate: two independent reads, both must be clean Casual + Pantra
        for _ in range(2):
            time.sleep(0.3)
            state = self.look()
            if not (state.get("screen") == "new_run" and state.get("mode") == "casual"
                    and state.get("region") == "Pantra" and not state["problems"]):
                return self._log(name, Result(
                    False, f"NOT confirmed: mode={state.get('mode')}, region={state.get('region')}, "
                           f"screen={state.get('screen')}", before, state))
        clicks = self._click(reader.NEW_RUN_CONFIRM)
        after = self.wait_for({"trainer_pick", "shop"}, 30)
        ok = after.get("screen") in ("trainer_pick", "shop")
        return self._log(name, Result(ok, f"Casual run confirmed; now on '{after.get('screen')}'", before, after, clicks))

    def pick_trainer(self, k: int) -> Result:
        """Click trainer card k (0 = left) on the trainer pick screen; the day 1 shop follows."""
        return self._press_and_wait(f"pick trainer {k}", "trainer_pick", reader.trainer_card(k), {"shop"}, 40)

    def open_gift(self) -> Result:
        """Click the gift box that appears when a monster levels up; the trinket choice follows."""
        return self._press_and_wait("open gift", "gift_box", reader.GIFT_BOX, {"trinket_pick"}, 20)

    def pick_trinket(self, k: int) -> Result:
        """Click trinket card k (0 = left). The shop comes back, or another gift."""
        return self._press_and_wait(f"pick trinket {k}", "trinket_pick", reader.trinket_card(k),
                                    {"shop", "gift_box"}, 20)

    def choose_event(self, k: int) -> Result:
        """Click choice k (0 = top) on an event screen."""
        import numpy as np
        before = self.look()
        if before.get("screen") != "event":
            return self._log("event", Result(False, f"not on an event screen ({before.get('screen')})", before))
        boxes = reader.event_choices(np.asarray(window.canonical_picture(self.last_image)))
        if not 0 <= k < len(boxes):
            return self._log("event", Result(False, f"no choice {k} (there are {len(boxes)})", before))
        return self._press_and_wait(f"event choice {k}", "event", boxes[k],
                                    {"shop", "event", "gift_box", "trinket_pick"}, 40)


def reader_free_slots(state: dict) -> int:
    return sum(s is None for s in state["team"] + state["bench"])


def _has_copy(state: dict, name: str) -> bool:
    return any(s and s["name"] == name for s in state["team"] + state["bench"])
