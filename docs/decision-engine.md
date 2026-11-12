# Decision engine (step 4)

`engine/` replaces the simple shop rules in `play.py`. It decides every shop action, the
team layout, which trinket to take from a gift and which trainer to pick. It runs on the
battle simulator from step 3 (`sim/`), so it needs that code next to it.

```
.\.venv\Scripts\python.exe play.py --new-run            # plays with the engine (Casual only, as before)
.\.venv\Scripts\python.exe play.py --simple             # the old rules, for comparison
.\.venv\Scripts\python.exe -m engine.runsim --policy engine --runs 20     # offline whole runs
.\.venv\Scripts\python.exe -m engine.runsim --policy simple --runs 300
.\.venv\Scripts\python.exe -m engine.runsim --verbose --first-seed 7      # one run, day by day
.\.venv\Scripts\python.exe -m unittest tests.test_engine
```

Nothing about the Ranked safeguard changed: the engine only acts on the shop, gift and
trainer screens, and `play.py` still starts runs only through `hands.start_casual_run()`.

## How a shop decision is made

Opponents are random snapshots of other players' teams for the same day, so there is no
single enemy to plan against. The engine plays every candidate team against a **pool of
plausible opponents** in the simulator and uses the share of battles won (plus a small
term for how close the battles were). All candidates in one decision meet the same
opponents with the same seeds, so a difference between two candidates is a real
difference, not luck of the draw.

After every action the game state is read again and the engine picks the next action:

1. **Value the board as it is**, after the best layout (a swap search over the 6 team
   and 4 bench slots, scored by the simulator).
2. **Try every candidate**: use an item; buy each card (and try the new monster in each
   team slot); sell a monster; sell one to afford or make room for a card; buy a Bug and
   sell it again to grow Guardiant (the fodder loop); reroll.
3. Each candidate is followed by a short **greedy look-ahead** (keep buying the best
   card while it helps), so a buy is judged by what the money could otherwise do.
   A reroll is judged the same way over several random shops drawn by the shop odds
   on screen.
4. The best candidate is played if it beats ending the turn. Otherwise: **LOCK** if a
   card the team cannot afford today would add a lot tomorrow, move the team into the
   best layout, and **BATTLE!**.

The value of a finished shop is:

```
  today's score  (x a stake weight: higher when a loss could end the run or the 10th badge is next)
+ tomorrow's score with the same team (does the board keep up as opponents grow?)
+ money and resale value, up to a cap (money carries over, but hoarding buys nothing)
+ trinket gifts earned by merges + progress toward merges (2 copies of a monster)
```

The weights are in `engine/planner.py` (`Params`).

## What the engine models (engine/model.py)

- Buying puts a monster in the first free team slot, then the bench.
- The third Lv1 copy merges into Lv2 at once (seen 2026-11-11); two Lv2 make a Lv3
  (assumed; not yet seen in a November run). The merged monster keeps the largest
  permanent growth of its copies. Every merge gives a trinket gift.
- A Bug buy grows Guardiant by its level's amount (Batopedia text).
- Selling refunds half the price, rounded up (Electranade $25 sold for $13 on 2026-11-11).
- Items with a known effect: Cake, Feast, Pom Berry, Coupon, Fake Coin, Lucky Coin,
  Red Coin (only with lives to spare, early), Gray Chip, the type buffs (Black Sludge,
  Hot Pepper, Battery Pack, Shiny Pebble, Mystic Pearl), Tote Bag, Nana Berry. Other free
  items are used; Tickets are used last because they replace the shop. Paid items whose
  effect is not modelled are skipped.
- Moves: drags onto an empty slot always work; a drag between two occupied team slots
  in the same row fails silently in the game, so the engine routes those through an
  empty slot or the bench.
- A monster the reader cannot name (sprite not learned yet) is never sold or moved, and
  counts as an empty slot in the simulator.

## Opponent pool (engine/opponents.py)

Built from "ghost" runs: each ghost gets the real income and real shop draws and buys
with one of four skill levels (casual, steady, strong, expert), merges, rerolls, sells
weak monsters and gets trinkets from its merges. One ghost run gives one team for every
day. The engine plans against one pool (seed 1); the offline test fights a different
pool (seed 9001), so it is not graded on the opponents it practised against.

**Calibration is the weakest point.** The pool was made harder until the old simple
rules came out near their real November record, but the simple rules still win about a
third of their simulated battles against it, against 3 of 14 in the real game. Ghosts
also miss what real players get from trainers, events, items, and monsters that grow in
battle (Prismagon, Bambudo). Ghosts get extra money per day to stand in for that.
Real opponents will replace guesses as soon as the bot logs them: any team added with
`opponents.add_recorded(day, team)` (or a line in `data/opponents_recorded.jsonl`) joins
the pool for its day. Logging the opponent's team from the battle screen is the most
valuable next step for the engine.

## Choices outside the shop (engine/choices.py)

- **Trinket gift**: each offered trinket is added to the team and scored in the simulator
  against today's and tomorrow's opponents; income trinkets are valued as money for the
  days left. The best one is taken.
- **Trainer**: Ed's own record per trainer from the Batopedia (runs won / played,
  smoothed), avoiding Mad Scientist (replaces the team mid-run) and Gentleman (no cheap
  monsters to merge).
- **Events**: still the last choice, because the reader does not read event texts yet.

## Numbers and where they come from

Ed asked (2026-11-12) not to rely on hard numbers from the September notes, because the
game has changed since. Live play uses what the screen shows: trainer HP, shop odds,
reroll price, money and every badge. The fallback tables in `engine/data.py` are used only
for planning ahead (tomorrow's HP) and for offline runs:

| Number | Source |
|---|---|
| Trainer HP days 1-8 | November runs (step2 screen map) |
| Trainer HP day 9+ | the simulator's table; not seen in November, check when a run gets there |
| Lives per loss (1, 1, 2, 2, then 3) | November runs, days 2-8 |
| Income ($30, then $25 + $5 x day) | November: $40 on day 1 with Rich Lady's $10, $35 on day 2 |
| Shop odds ranks 1-10 | November runs; ranks 11-13 extrapolated, live play reads them |
| HP +25% after the rescue | November runs (twice) |
| Lv3 = two Lv2 | assumption, to check in a run |

Qualitative lessons from the September notes are used: positions (behind = left, in
front = right, above, adjacent is orthogonal), amplifier pieces, eggs stay on the bench,
Dirgefin and self-knockout monsters judged by the simulator rather than banned, and the
same-row drag rule.

## Offline results

### First version (2026-11-12, PR #3)
Against the first opponent pool the engine won 23 of 24 offline runs. The first live
Casual run (Chef) then won Days 1-6 and lost Days 7-11 (6 badges). Its logs
(`runs/2026-11-12-chef/`) showed why: from Day 7 it fielded a slow Burn/shield team that
beat the ghost opponents in long battles but lost to real players. The pool was too weak late.

### Calibrated to the live run (2026-11-12)
- Ghost teams now keep the permanent growth they would get from battles (`engine/growth.py`),
  get more extra money per day, and their numbers are scaled up from day 5 (`POWER_RAMP`).
  The settings were chosen so that the real Chef teams score close to their real results
  (high on Days 1-6, low on Days 7-11) and the old simple rules win 16-17% of simulated
  battles (21% in the real runs).
- The planner also scores the board against the day after tomorrow, so a board that looks
  safe today still keeps growing; trinkets the simulator cannot see get a small value from
  their wording.
- Settings were swept over 13 variants (24 runs each) and the best combination checked on
  40 fresh runs:

| Policy | Runs | Runs won | Mean badges | Battles won |
|---|---|---|---|---|
| Old simple rules | 300 | 0% | 1.2 | 16% |
| Engine, previous settings | 40 | 2.5% | 4.9 | 47% |
| Engine, current settings (k_quick 10, min_gain 0, margin weight 0.3) | 40 | 22.5% | 5.6 | 52% |

Rerolling matters most: without it the engine fell to 3.1 badges. Expect the real numbers
to move as real opponent teams get logged (PR #6) and replace the ghosts.

## Speed

About 5-20 s per shop decision on one core (more late in a run, when there is more money
and more candidates). A whole offline run takes 2-4 minutes.
