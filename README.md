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

## Safety rules

- The New Run screen defaults to **Ranked Mode** — never start a Ranked run.
- Do not modify the game's install folder or read/decrypt its `.pck` file.
