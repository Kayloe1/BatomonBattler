# Status (2026-11-11, end of fourth session)

The program now **starts a Casual run, plays it to the end, and stops**. Two runs were played today:
1. The run Ed had open (Rich Lady), from Day 2 to its end on Day 8 with 3 badges.
2. A new **Casual** run the bot started itself (Monster Ranger), from Day 1 to its end on Day 7 with 1 badge.

Neither was unattended from start to finish: the bot stopped whenever it met a digit, letter or screen it
had not seen, that was taught from the saved capture, and it was restarted. In the second run it played
Days 3 to 6 without help. The game is on the end-of-run screen. Nothing was ever started in Ranked Mode.

The simple rules play badly (they stop buying once the team is full), which is expected until the simulator
replaces them.

## What works (tested live and by 33 tests)
| File | Status |
|---|---|
| `window.py` | Finds and captures the window. Fractions are measured against the 16:9 game picture, not the black bars. |
| `glyphs.py` | Reads the pixel fonts by matching glyph templates in `templates\glyphs.json`. An unknown glyph is `?`, never a guess. |
| `reader.py` | `read_state(image)`. Screens recognised: `new_run`, `trainer_pick`, `shop`, `matchmaking`, `battle`, `result`, `stats`, `event`, `gift_box`, `trinket_pick`, `run_over`, `blank` (fade), else `unknown`. On the shop it reads lives, day, badges, trainer, trainer HP, money, shop rank and odds, reroll price, lock state, 5 shop slots (name, price, monster or item, stat badges, rarity from the frame colour, greyed out, sold), 6 team and 4 bench slots (level 1 to 3, stat badges, name by sprite). It also reads the selected mode and region on the New Run dialog, the three trainer names, and the offered trinket names. Anything unreadable is `None` plus a line in `problems`. |
| `teach.py` | Rebuilds `templates\glyphs.json` from the labelled captures in its `LESSONS` list and adds their sprites. |
| `hands.py` | Live or dry-run. Verified live: buy, use item, move (drag), sell, reroll, lock/unlock, battle (waits for the result, turns fast forward on if off), confirm result, event choice, open gift, pick trinket, pick trainer, and `start_casual_run()`. Each action reads the state first and checks it afterwards. |
| `play.py` | Simple-rules loop: use free items, buy the dearest affordable monster while the team has an empty slot, BATTLE!, CONFIRM, last event option, first trinket, preferred trainer (Monster Ranger, Swim Coach, else the left card). With `--new-run` it starts a Casual run when none is open. Stops on anything unclear and at the end of the run. |
| `tests\` | `.venv\Scripts\python.exe -m unittest discover tests` |

Logs: `logs\actions_<date>.jsonl` (every action with the state before and after) and `logs\run_<time>.jsonl`.

## The Ranked safeguard (rule 1)
- The New Run dialog has two buttons, Ranked Mode and Casual Mode; the selected one is blue, the other grey.
  This was checked by clicking each once without confirming. Today the dialog opened with Casual already
  selected (it seems to remember the last mode), but the code does not rely on that.
- `hands.start_casual_run()` presses CONFIRM only after two fresh captures both read "Casual blue, Ranked grey,
  Pantra selected". If the reading is unclear it stops. It never clicks the Ranked button, and no other code
  path presses CONFIRM on that dialog. Tests cover the reading and that the Ranked button box is never used.
- `play.py` only starts a run when given `--new-run`.

## How to add what the reader does not know yet
When `play.py` stops with "cannot read", the capture is saved as `captures\unread_*.png`. Look at it, add
an entry with the true text to `LESSONS` in `teach.py`, run `teach.py`, then
`reader.py <capture> --expect` to make it a test (check the printed values by eye first).

## Limits
- **Fonts are still incomplete.** Each run today met a few unseen glyphs (a digit in one of the fonts, or a new
  label colour). Names with unknown letters resolve when exactly one known name fits, which has worked for
  every monster, item, trainer and trinket met. Expect occasional stops until every glyph has been seen once.
- **Window size:** templates only fit a 2560 x 1440 game picture. At another size the reader reports a problem.
- **Not handled:** the main menu, a won run (10 badges), level 4.
- **Not read:** the Stats screen contents, event option texts (the bot takes the last option blindly), the
  result text (win or loss is worked out from badges and lives on the next shop), owned trinkets, the item
  counter, the hover panel, the small flag and arrow marks trinkets put on team slots.
- **Team names come from sprites** saved when the bot buys a monster. A monster that arrives another way
  (an event, a Green Stone transformation) has `name: None` until its sprite is taught. Venopuff, Mosslug and
  Panbud were named by Claude from their stats; Ed should confirm the cream and purple fox is Venopuff.
- A shine animation crosses shop cards of monsters you own; the hands re-read the shop up to four times to
  get past it.
- `CONTINUE_PROMPT.md` describes the state before these sessions; this file is the current one.

## What the runs taught us about the game
See `docs\step2-screen-map.md`: trainer HP per day, lives lost per loss, shop rank and odds per day, sell
value, what LOCK does, three copies make a level 2 and give a trinket gift, level label colours, the events,
and Stats screen numbers that match the CSV data.

## Next steps
1. Run `play.py --new-run` a few more times in Casual until a whole run passes with no stop (this fills in
   the remaining glyphs). Add the main menu so it can also start from there.
2. Read the Stats screen after each battle into the log, and log the opponent's team. The simulator needs both.
3. Read event options and trinket effects so those choices can be made on purpose.
4. Build the simulator from the CSV data and check it against the logged battles (step 3 of the plan).
5. Replace the simple shop rules with simulator-scored choices, including selling and the bench.

## Safety rules (unchanged)
- Never start a Ranked run without Ed saying so.
- Do not decrypt, unpack or modify the game's files, and do not read or write its memory.
- Bots: Ed said on 2026-11-11 that the developer allows bots. (This is Ed's statement; no source is recorded here.) Rule 1 still applies: Ranked only when Ed says to start it.
- Work only inside this folder.
