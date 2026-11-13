# batomon-bot

A Python helper that will play **Batomon Showdown** by reading the game window and clicking.
It reads the screen and plays a run that is already open with simple rules; see `STATUS.md`.

## Layout

| Path | What it is |
|---|---|
| `.venv/` | Python 3.12 virtual environment (mss, pillow, numpy, opencv-python, pyautogui, pywin32) |
| `window.py` | Finds the game window, captures it, finds the 16:9 game picture inside it, and converts picture fractions to screen pixels |
| `capture.py` | Saves a timestamped PNG of the client area to `captures/` |
| `glyphs.py` | Reads the game's pixel fonts with glyph templates |
| `reader.py` | `read_state(image)`: which screen is showing, and everything on the shop screen |
| `teach.py` | Rebuilds `templates/` (glyphs and monster sprites) from labelled captures |
| `hands.py` | Mouse actions (buy, move, sell, reroll, lock, battle, confirm, event choice), each one checked afterwards |
| `play.py` | Plays the open run with simple rules and logs everything; stops on anything unclear |
| `gui.py` | The control window: Start, Pause / Resume, Stop, what the bot is thinking, and why it stopped |
| `sim/` | Offline battle simulator (`python -m sim --help`, `docs/simulator.md`) |
| `tests/` | Tests that run on the saved captures, plus `test_sim.py` for the simulator |
| `captures/` | Saved screenshots; a `.expected.json` beside one makes it a test |
| `templates/` | Glyph and sprite templates (built by `teach.py`) |
| `logs/` | One JSON line per action |
| `data/` | Batomon, item, trinket and trainer data read from the in-game Batopedia |
| `docs/` | Research findings and the screen map |
| `STATUS.md` | What works, what does not, and what is next |

All positions are **fractions (0.0-1.0) of the 16:9 game picture** (the client area without its
black bars). `window.frac_to_screen(rect, fx, fy)` gives a screen pixel and
`window.screen_to_frac(rect, x, y)` goes back. The reader works on the picture scaled to
2560 x 1440 and `reader.box_to_frac(box)` converts one of its boxes to fractions.

## Run

With the game open and not minimized:

```
cd C:\Users\eddyp\Desktop\batomon-bot
.\.venv\Scripts\python.exe capture.py
.\.venv\Scripts\python.exe reader.py
.\.venv\Scripts\python.exe -m unittest discover tests
```

`capture.py` saves a screenshot, `reader.py` prints the state of the live window, and the last
line runs the tests. Capture uses Win32 `PrintWindow`, so it works even when other windows cover
the game (not while it is minimized).

## The control window

Double-click `control_window.bat`, or run `.\.venv\Scripts\python.exe gui.py`. It plays exactly what
`play.py` plays, without a terminal.

- **Options** are the ones `play.py` takes: start a Casual run when none is open (`--new-run`), stop
  after N battles (`--days N`), and what decides: the planner, the learned policy (`--learned`) or the
  old simple rules (`--simple`).
- **Start** begins. **Pause** holds the bot between two actions and **Resume** carries on from a fresh
  read of the screen, so you can do something in the game by hand in between. **Stop** ends the session.
  Pause and Stop wait for the current action to finish: a click or drag is never cut in half, and a
  battle that is running is waited out first (the window says so while it waits).
- **Status** shows day, lives, badges, money, trainer, the screen, the last action with its result, and
  the chance to win today's battle. **Thinking** shows the same lines as `logs	hinking_<time>.txt`,
  with each action's result in blue between them.
- When the bot stops because it cannot read something, a **red box** gives the reason and the name of
  the saved capture, with buttons to open the picture and to copy the message for Claude. It still beeps.
- Keep the window **beside the game picture**, not over it (it opens beside the game when there is
  room, and warns when it covers the picture). It is never kept on top: the bot brings the game to the
  front for every click. Pushing the mouse into a screen corner still aborts.
- The window clicks nothing itself and has no control for Ranked Mode. Started from the `.bat` there is
  no console; what would be printed goes to `logs\control_window_console.txt`.

`python play.py ...` and `python batch.py` work as before.

## Safety rules

- The New Run screen defaults to **Ranked Mode** — never start a Ranked run.
- Do not modify the game's install folder or read/decrypt its `.pck` file.
