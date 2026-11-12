# Prompt for the next AI: continue the Batomon Showdown bot

Paste everything below into the AI you want to continue with, and give it access to this folder (`batomon-bot` on the Desktop).

---

You are continuing a project for Ed. The goal is a Python program on his Windows PC that plays the Steam game **Batomon Showdown** automatically and well enough to climb the ranked ladder. Everything so far is in this folder. Read `STATUS.md`, `README.md`, and the files in `docs\` and `data\` before you write any code.

## The game
- Monster auto-battler by solo developer berrymint (Godot 4.7, Steam app 4557380). Installed at `C:\Program Files (x86)\Steam\steamapps\common\Batomon Showdown`.
- A run is a series of days. Each day has a shop phase (buy, sell, move, use one item, reroll) and then one battle against a stored snapshot of another player's team. You cannot know the opponent in advance. 10 lives, and 10 badges wins the run.
- Battles are real time and automatic. Each monster acts on its own cooldown and damages the enemy trainer's HP bar (300 HP on day 1, 500 on day 2). Position on the 3 x 2 team grid matters for many abilities.
- Scope: **Pantra region only** (64 Batomon). Ignore Jinto and the third region.

## What exists
- `docs\step1-findings.md`: research on the game, rules found in public guides, and why we read the screen.
- `docs\step2-screen-map.md`: every screen in a run, the layout of the shop screen, and the controls (left click buys or uses, drag moves, drag onto the shop bar sells).
- `data\batomon_pantra.csv` and `data\batomon_pantra_levels.csv`: all 64 Pantra Batomon at levels 1 to 4 (cost, rarity, types, cooldown, abilities).
- `data\trinkets.csv` (76 trinkets; 6 Mythical ones are locked and unknown), `data\items.csv` (39 items), `data\trainers.csv` (24 trainers).
- Code: `window.py` (find the game window, capture it, convert fractions to pixels) and `capture.py`, both tested on the live game. `data\names.json` lists the known Batomon and item names. `captures\` has a clean capture of the Day 2 shop screen to use as the first test case. Python 3.12 with a virtual environment in `.venv` (mss, pillow, numpy, opencv-python, pyautogui, pywin32).

The data was read by eye from the in-game Batopedia in a small pixel font where "7" looks like "?". Treat the numbers as probably right, and fix the CSVs when the game shows something different.

## Rules Ed has agreed to. Keep them.
1. **Never start a Ranked run** without Ed saying so. The New Run screen has Ranked Mode selected by default, so the program must read the mode button and confirm that Casual Mode is selected before it clicks CONFIRM. Develop and test in Casual only.
2. Do not decrypt, unpack or modify the game's files (`batomon_showdown.pck` is encrypted). Do not read or write the game's memory. The program only looks at the window and sends mouse input, like a player.
3. Nothing was found about whether the developer allows bots. Ed was advised to ask on the game's Discord before running this on the ranked ladder, and has not decided. Raise it again before any ranked use. An advisor mode that recommends moves while Ed clicks is the fallback.
4. Work only inside this folder.

## The plan, and where it stands
1. Map the game. **Done.**
2. Eyes and hands. Data collection and screen map are **done**. Window capture is **done**. Screen reading and clicking are **not started**.
3. Offline battle simulator. **Not started.**
4. Use the simulator to choose shop moves, then tune on real results. **Not started.**

## What to do next, in order
1. First make `window.py` measure fractions against the 16:9 game picture only (the window has black bars above and below it). Then write `read_state(image)`: detect which screen is showing and, on the shop screen, read lives, day, badges, trainer HP, money, shop rank and odds, reroll price, the 5 shop slots, the 6 team slots and the 4 bench slots. Prefer matching glyph templates cut from real captures over a general OCR engine. Save a capture for every screen you meet and turn it into a test.
2. Add the hands: buy (click a shop card), use an item (click), move (drag between slots), sell (drag onto the shop bar), reroll, lock, battle, fast forward, confirm the result. After every action, capture again and check that the state changed as expected. Stop and report if the screen is unknown.
3. Map the screens not yet seen: a lost battle, the trinket gift choice, merging copies to level up, what LOCK does, the end of a run, and the Stats screen after a battle.
4. Milestone for step 2: the program finishes one whole Casual run with simple rules (buy the most expensive thing it can afford, fill the team, press BATTLE!), and logs every shop state, action and battle result to a file.
5. Build the simulator from the CSV data. Check it against real battles using the logs and the in-game Stats screen, and correct the data where they disagree.
6. Use the simulator to score shop choices against a pool of logged opponent teams, then compare the bot's Casual results with Ed's own record before anyone considers ranked.

Ed's own record when this started: about 53 games, rank Bronze 1, best results with the trainers Monster Ranger and Swim Coach.
