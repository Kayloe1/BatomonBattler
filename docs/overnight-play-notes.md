# Overnight manual play notes (2026-11-12 night)

Claude played Batomon Showdown by hand (screenshots + clicks), **Casual Mode only**, to learn things
for the bot. Each section is written as it happened; the summary of lessons is at the top once done.

## Lessons for the bot (summary)

_(filled in at the end)_

## To build (found tonight, not built yet)
1. **Shiny detection.** The reader names a Shiny monster like the normal one (same badges, blue/sparkly
   sprite). The model needs a `shiny` flag passed to the sim's new `"shiny"` key, and `engine/events.py`
   should value "Turn a monster SHINY" (Shiny Stingarde: ~4% -> ~80% Day 3 win chance in the sim pool).
2. **Purple Egg sprite.** Egg Breeder's egg is unnamed by the reader. Sprites cut from the bench matched the
   opponent's Dragon Egg in `tests/test_reader.py`, so they were deleted; the egg needs its own handling
   (it should stay on the bench and never be sold).
3. Using an item refills its shop slot with a new card; check `engine/model.py` models this.
4. The engine's "feed and sell" Bug move scored above keeping a strong Bug (Stingarde) on Day 2.

## Log

### Run 1 (Casual, Egg Breeder; trainer choice was Gentleman / Redhead / Egg Breeder)
- Patch notes v1.5.x read from the main menu; the Pantra changes (Prismagon, Craghorn, Lignite, Emperooze,
  Aster, Scorchimp/Sunsage, Noxnimbus, Dracana, Gildshell) are already in `data/batomon_pantra.csv`.
  Also from v1.5: Purple/Golden/Crimson Gifts never offer drawback trinkets (Fool's Gold, Incenses);
  Green Stone no longer shows up while you own a level 4+ Common; Burglar now offers 3 trinkets, pick one and
  steal one of the other two at random.
- Egg Breeder: the Purple Egg starts in team slot 5 (bottom right). Moved it to the bench.
- Day 1 shop: Stingarde, Spinarai, Guardiant, Guardiant, Green Stone (free). Bought both Guardiants
  ($30): the first went to slot 5 and grew to 23 when the second (slot 4) was bought.
- **Day 1 lost** to a lone Lv1 Venopuff (Poison 4, 3.5 s). We dealt 228 of 300 (90 + 138, 6 casts each);
  their poison reached 24 stacks and killed us at about 24 s. Saved as `sim/cases/day1_egg_breeder_loss.json`;
  the simulator reproduces it exactly. Lesson: **Poison scales with time (sum of stacks), so a single
  Venopuff out-damages two Guardiants on Day 1.** A Day 1 team needs to deal 300 in ~20 s, i.e. ~15 dps.
- **Day 2 lost** narrowly (they ended at 29/500) to Guardiant 38, Stingarde, 2 Velocect, Bumblebolt.
  Bought: Voucher (gave Panbud), Stingarde, Magmite. **Using an item refills its shop slot with a new
  card** (the Voucher slot became a Joltail). Sim case `day2_egg_breeder_loss.json`. It showed two sim
  bookkeeping errors, now fixed: the Stats screen's "Triggered" counts **casts, not Multicast hits**
  (Velocect x2: 4 casts), and "Dealt" **includes the Shock bonus**.
- The engine (asked through a helper, see below) wanted "feed Stingarde to Guardiant (buy then sell)";
  the sim pool said keeping Stingarde was slightly better (15% vs 12%). Small difference.
- Event after Day 2: berry bush. Options "Turn a monster SHINY" / "Gain Rainbow Berry" / "Gain $20".
  Took SHINY on Stingarde: **Shiny Stingarde has no "Knockout self"** (its card shows only "Deal 150
  damage"); it keeps casting every 6 s. It looks blue with sparkles; the reader still names it
  "Stingarde" and the engine treats it as self-knockout. Capture: `captures/manual_shop_day3_shiny_stingarde_slot2.png`.
  In the sim pool, modelling it right takes Day 3 win chance from ~4% to ~80%.
- Red Coin card text: "+$20 and lose 1 life" (Uncommon, $0). Not used.
- **Day 3 won** (us 409/800) against Redhead: Pyronade, 2 Bumblebolt, Craghorn 34/34, Dragon Egg, Panbud.
  Shiny Stingarde: 3 casts, 450 damage. Case `day3_egg_breeder_win_shiny.json` taught the sim two
  timing rules: (1) **Shock gained at an instant only boosts hits from the next instant** (two Bumblebolts
  casting together both dealt 63; Panbud casting with them got 2+6+10 Shock); (2) **every cast of both
  sides at an instant resolves before deaths are checked** (their Craghorn still cast at 18 s, the instant
  our team won), so a mutual kill is a draw, and a heal cannot revive a trainer at 0 HP.
- The confirm button shows "HOTKEY: SPACE" on the result box.
- **Day 4 lost** (-2 lives) to Masked Man (3 trinkets): Panbud 55, Brawlmantis-like 69, Fumungus, Mosslug Lv2,
  Velocect 45, Spinarai (Poison grew 1 -> 16 in battle). They ended at 480/1400 after 20 s. Bought Runerock +
  Shogapede after selling Mosslug and the plain Stingarde (sim: 73%). Gray Chip used (slot refilled with
  Scorchimp). **Dragging a bench monster onto an occupied team slot swaps them.** Trainer HP: Day 4 1400,
  Day 5 2400, Day 6 3800.
- **Day 5: the Purple Egg hatched at the start of Day 5** (Day 1 + 4) into a **Lv2 Fumungus** (Super Rare,
  card says $60; Poison 6 every 3 s, +200% of the enemy's Poison as Damage), in the egg's own bench slot.
- Buying a "LV 2"-tagged Magmite merged the team copy and bench copy; the Lv2 stayed in the **team** copy's
  slot and the bench copy's slot emptied. Gift box -> trinkets offered: Mini Duplicator, Locked Box, Gold
  Trophy (On Victory +$8). Took Locked Box ("next loss: a random non-unique trinket of the highest rarity
  your shop rank allows").
- **Fake Coin** (free item) turns REROLL into "FREE (1)"; its slot refilled with a Magmite.
- **Shop cards can be Shiny** (a "SHINY" tag on the card). Shiny effects differ per species:
  Stingarde loses "Knockout self"; **Magmite gains "On Battle Start: +10 Shield and +1 Burn permanently"**;
  **Stalagrove's 15% becomes 18%**. Priced like the normal card ($15 Magmite, $35 Stalagrove).
- **Day 5 won** (us 1249/2400, 30 s) against Hiker-like trainer with 5 trinkets. Fumungus Lv2 dealt 900,
  Shiny Stingarde 750 (5 casts), Guardiant 55 dealt 385.
- Event after Day 5: crying baby basilisk -> "Gain Ignit" / "Get a Rare trinket gift" / "Gain $40". The
  engine picked the trinket (Ignit is not in its data: +0.05 guess). Took Ignit to read it: **Ignit, Rare
  Fire, 8 s, Burn 1, "On Victory: Evolve"**, sells for $20.
- **The Batopedia has a "???" tab with 9 special monsters**; 6 are now in `data/special_monsters.csv`
  (Ignit, Talonite, Wishwash, Cosmivore, Faebloom, Omnichrome), 3 are still locked. **Escape closes the
  Batopedia** (clicking its X did not).
- Day 6 ($65): the engine (blind to Shiny, and to Fumungus whose sprite it does not know) wanted to sell the
  Shiny Stingarde. Sold both bench Guardiants ($8 each: a grown Guardiant still sells for $8), bought
  **Noxalith** (On Cast: Toxic ally above +3 Poison permanently) under Fumungus and a Shiny Stalagrove,
  used Shiny Pebble (+20 Shield to every Rock monster, **bench included**). Sim: 56%.
- **Day 6 won** easily (us 3454/3800). Fumungus went from Poison 6 to 21 in one battle (Noxalith x5) and
  dealt 1608; Shiny Stalagrove dealt 1368 (its damage reached 374 = 18% of 2080 shield received).
  **Fumungus + Noxalith below it is a strong engine** (permanent growth every Noxalith cast).
