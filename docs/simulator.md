# Battle simulator (step 3)

`sim/` plays a Batomon battle offline from two teams. Pure Python, no extra packages, about 2-3 ms per
battle, so the shop logic can call it thousands of times.

## Run it

```
.\.venv\Scripts\python.exe -m sim --check                              # compare with the recorded battles
.\.venv\Scripts\python.exe -m sim --rules                              # every rule, verified or guessed
.\.venv\Scripts\python.exe -m sim --case sim\cases\day2_rich_lady_win.json --log
.\.venv\Scripts\python.exe -m sim my_team.json their_team.json [--seed 3] [--json]
.\.venv\Scripts\python.exe -m unittest tests.test_sim
```

From code:

```python
from sim.battle import simulate, team_from_reader, win_rate
r = simulate(team_a, team_b, seed=0)     # r.winner is "a", "b" or "draw"; r.hp, r.time, r.units
mine = team_from_reader(reader.read_state(image))   # shop screen -> team
```

## Team format

```json
{
  "trainer": "Rich Lady",
  "hp": 500,
  "trinkets": ["Rally Flag"],
  "slots": [
    {"name": "Brawlmantis", "level": 1, "stats": {"damage": 60}},
    {"name": "Venopuff", "level": 1, "stats": {"damage": 15, "poison": 4}},
    null,
    null,
    {"name": "Mosslug", "level": 1},
    null
  ]
}
```

- `slots`: 6 entries. Slots 1-3 are the top row left to right, 4-6 the bottom row. Your team faces right.
  Behind = the left neighbour, In front = the right neighbour, Above = the top-row slot in the same column,
  Adjacent = left, right, above, below (not diagonal). Opposite = the enemy's slot with the same number.
- `stats` is optional. When given (the badges the reader sees), it replaces the Batopedia numbers for that
  level, so buffs bought in the shop are included. Without it, the level's Batopedia numbers are used, and
  badge-type trinket and trainer bonuses (Wood Sword, Chef, Chemist...) are added.
- Optional per slot: `multicast`, `cooldown`, `speed` (% cooldown speed), `protect`.
- `hp` is the trainer's HP; or give `"day": 3` to use the day table (300, 500, 800, 1400, 2400, 3800, 5700,
  8300, 11600, 17300, 24900, 34700, 47300).
- `coffee: true` means a Coffee was used before this battle.

## How a battle runs

1. Battle start: trinket effects, then Celestia, then every On Battle Start ability (player's side first).
2. Each monster casts when its cooldown has fully passed, then again every cooldown. Cooldown Speed divides
   the cooldown; Charge moves the timer forward.
3. A cast repeats its active Multicast times (Deal hits the enemy trainer, Heal and Shield go to your own
   trainer, Poison, Burn and Shock go on the enemy trainer). On Cast passives run once afterwards.
4. Poison ticks once a second on the battle clock for its stacks and stays. Burn ticks twice a second and
   loses 1 stack per tick. Shock adds its stacks to every damaging hit and stays. Shield absorbs damage
   first; Poison and Burn do 15% less while there is a shield.
5. At the same instant: casts (player's side, then the opponent's), then Burn and Poison ticks. A trainer
   at 0 HP loses at once. Both at 0 on the same tick is a draw; 300 s is a draw.

## What is verified and what is guessed

Two battles are recorded well enough to check (cases in `sim/cases/`, from the Rich Lady run on
2026-11-11). `python -m sim --check` prints every comparison.

| Battle | Result |
|---|---|
| Day 2 win (both teams visible at battle start, full Stats screen for Ed's side) | **Reproduced exactly**: winner, end time 19 s (the cast counts allow 18-20 s), every trigger count, every Dealt/Healed/Inflicted number on both sides. |
| Day 3 loss (Ed's team from the log, opponent's team and both HP bars from the end screen) | **Opponent side exact**: 676 damage taken by 14 s (= 800 - 124 on the end screen), Poison 16 and Shock 25 on their bar, Spinarai 5 -> 17 Poison, Noxnimbus 5, Venopuff 8, Mosslug 45. Ed's Poison 101, Mosslug 55, Electranade 1 cast all exact. **Gap:** by 14 s the sim has Ed taking 802 damage and healing 140, so he survives to 16 s and the battle is a draw; the game had him dead by 15 s. The missing ~140 is exactly his heals. |

**Verified by those battles:** first cast after a full cooldown; Poison = stacks once a second on the battle
clock with no decay; Shock = flat +stacks on every hit with no decay (percent Shock would leave the opponent
at 345, not 124); adjacency is orthogonal (the opponent's diagonal Venopuff got no Noxnimbus bonus);
Noxnimbus buffs neighbours, not itself; Mosslug hits first, then gains; Stats 'Dealt' excludes ticks;
Stats 'Healed' counts the full heal.

**From the game's own keyword text** (copied in the older Kayloe1/batomon notes): Burn twice a second and
-1 per tick; status damage 15% less against shields; Knockout and Protect; Charge; behind/front/above.

**Guessed** (each one is listed with its reason by `python -m sim --rules`):
- Cooldown Speed formula (divide by 1 + X%).
- Order at the same instant (player first; before the September patch the enemy went first).
- Heal capped at max HP.
- No time limit (300 s = draw); both dead on one tick = draw; a trainer loses the moment HP hits 0.
- On Cast passives run once per cast, not once per Multicast hit.
- "Trigger" casts at once without resetting the timer.
- When badges are given, badge-type trinket/trainer bonuses are already in them; cooldown and Multicast
  trinkets are always added; +HP trinkets are already in the HP the reader sees.
- Runerock/Sirenade remove from Poison, Burn and Shock on your own trainer; percentages round down.
- Celestia disables Ongoing monsters in its row on both sides.
- Dragon Egg: 10 s cooldown, 1 damage (the Day 2 battle only says 9.5-19 s).
- Random effects use a seeded generator.

**Not simulated:** shop-phase effects (they show up in the badges instead), Shiny variants, Fancy Sword,
Scrap Sword, Zenith Stone, Magic Lasso, Jinto monsters, the 6 locked Mythical trinkets.

## Open question from Day 3

Either Ed's heals did not count while he was heavily poisoned, or the opponent had about 140 damage the
end screen does not show (for example a self-knockout monster that left the board). The cheapest way to
settle it: after a battle where we heal while poisoned, open **Replay** and read both HP bars every few
seconds, or read the opponent's Stats tab (the bot does not read the Stats screen yet). Once known, change
the rule in `sim/battle.py` and move the case's `known_gaps` entry to a passing check.

## Why only two battles

The bot's logs record our own team but not the opponent's team, and the older repo's 105 logged fights
have Stats numbers but no team names on either side, so neither can be replayed. Logging the opponent's
team (from the battle screen at start) and the Stats screen after every battle would turn each Casual
battle into a new test case: add it as a JSON file in `sim/cases/`.
