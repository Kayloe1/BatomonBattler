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
- Day 7 (HP 5700): rerolled into an **Aegistruct** (sim 62% -> 79% in place of Shiny Stingarde) and bought
  **Thorntail** (+8 Damage permanently whenever an ally inflicts Poison). Sold Cicadence and Shogapede for room.
  **Lost Day 7 by 389 HP** (-3 lives, 3 left) to a mirror poison team (2 Noxnimbus, Puffloon, Shiny Venopuff
  Lv2, Shiny Spinarai Lv2, Thorntail 543): 787 Poison stacked on us. Our Thorntail grew 50 -> 170 in that
  one battle. The **Locked Box** paid out on that loss: **Haste Orb** (Super Rare, +10% cooldown speed).
- Day 8 (HP 8300, $80): **a Coupon only discounts the shop it is used in; rerolling after it wastes it.**
  Kept the team (sim 73%), won (4 badges). Event: monster professor -> "Level up a monster (max level 4)" /
  "Gain Research Notes" / "Gain $60". Levelled Fumungus 2 -> 3: **an event level-up keeps permanent growth**
  (Poison 39 kept) and the card's cooldown already includes Haste Orb (3.0 -> 2.7 s).
- Day 9 (HP 11600, $141): bought 2nd copies (Noxalith, Runerock, Thorntail); a "LV 2" Thorntail merged:
  **the merge kept the team copy's growth (298)** and its team slot. **The gift's rarity follows the merged
  monster's rarity**: Magmite (Common) offered Common trinkets, Thorntail (Rare) offered Rare ones
  (Warhorn, Ancient Plume, Mega Duplicator). Took **Warhorn** (On Battle Start: your monsters +10 Damage
  permanently; only team monsters get it). Won (5 badges, 7773/11600 left).
- No event after Day 9: **events came after Days 2, 5 and 8** (every 3 days).
- Day 10 (HP 17300, $129): added Noxnimbus next to Fumungus and Thorntail. **Rare Candy ($40, "level up a
  random level 1 monster") can pick a bench monster**: it levelled the benched Shiny Stingarde to Lv2 (300).
  Hovering shop cards shows "RIGHT CLICK TO INSPECT". Won Day 10 easily (15867/17300 left, 6 badges);
  Thorntail reached 1038 damage, Fumungus 2561.
- Item note: **Ultra Candy (Mythical, $60) levels a random level 3 monster**; with only one Lv3 it is a
  guaranteed Lv4 (Fumungus Lv4: CD 1.5 s, Poison 12, 1200%).
- Day 11 (HP 24900, $138): **Warhorn stacks every battle** (team monsters showed +20 Damage by Day 11).
  Added Aristobat (Toxic, Poison 4 x2) and a Legendary **Gaiadrasil** (Damage = 100% of adjacent allies'
  Damage; next to Thorntail its card showed 1038 in the shop). **Lost** to a Burn engine: **Lignite Lv2
  (Damage = 48x its Burn) with Burn 144 hit for 6982** (8562 total) fed by Magmalith Lv3, plus Sunsage Lv3
  (21 casts), Cinderfly, Dracana and a Shiny Dribblet Lv3 healer (2568 healed). 763 Burn on us.
- **Last-life rescue** ("A mysterious trainer approaches..."): three "Accept a life and ..." options:
  Super Rare trinket gift / random level 2 Super Rare monster / **Mysterious Charm = "[Unique] +25% HP"**.
  The engine picked the monster (+0.81) and valued the Charm at a +0.05 guess. Took the Charm: HP went
  34700 -> 43375 (x1.25). **So the +25% HP the engine applies after every rescue (`planner._hp`) comes from
  this Charm, not from the rescue itself** (the old simple rules always took the last option, the Charm).
  The opponent's HP stays on the table (34700).
- Day 12 (1 life): **Saberhorn** (Legendary, gives the ally in front +1 Multicast) behind Thorntail (sim 59% ->
  67%). **Golden Gift ($50) gives one Legendary trinket with no choice**: Metronome (casts give +10 Damage
  for the battle). Won Day 12 (7 badges).
- Day 13 (HP 59125): **Blue Ticket** turned the shop Rare and offered a "LV 2" Noxalith (merged; gift: Link
  Cable / Arcade Coins (10 free rerolls) / Fool's Gold). **Link Cable makes Gaiadrasil add up the whole
  team**: its card showed 2472 = every ally's Damage + its own; two Gaiadrasils each showed ~2440 (each
  leaves out the other). The sim did not change its win chance for any of this (it probably does not model
  Link Cable on Gaiadrasil).
- **Day 13 lost, run over (7 badges)**: Blazewing Lv3 (Burn 195, Multicast 7) put 5113 Burn on us; dead in
  ~14 s. Each Gaiadrasil (9 s cooldown, 8.2 s with Haste Orb) cast once.

### What Run 1 says about strategy
- Late game (Day 11+) is decided by **Burn burst**: Lignite/Magmalith or Blazewing teams kill in ~15 s. Slow
  carries (9 s Gaiadrasil, poison that needs time) lose to them. Poison scaling won Days 5-10 and 12.
- **Permanent growers carried the run**: Fumungus (Poison 6 -> 90 via Noxalith), Thorntail (50 -> 2442),
  Warhorn. The bot should value permanent growth that compounds across days much more than the one-battle sim does.
- Several of the engine's choices were wrong because it could not see things: Shiny Stingarde (sell it),
  Fumungus (unnamed), Ignit, Mysterious Charm, Link Cable + Gaiadrasil.

### Run 2 (Casual, Witch; choice was Witch / Mad Scientist / Rich Lady)
- **Witch**: the first shop each day has a Potion. Seen: **Summon Potion** ($10, Common: a random level 2
  Common monster with no sell value; gave Dribblet Lv2, then Pebbler Lv2), **Gold Potion** ($0: +$10),
  **Growth Potion** ($1: every monster, **bench included**, gets a small random Damage, Poison or Burn),
  **Shiny Potion** ($0, Rare: a random monster becomes Shiny; it picked the benched Ignit).
- Day 1: Summon Potion + Venopuff (sim 96%) won. Day 2: Gold Potion, 2 Magmites, Dribblet; Gold Potion's
  slot refilled with a Stingarde; won. Berry event again -> Shiny on Venopuff: **Shiny Venopuff = "On Battle
  Start: +1 Poison permanently"**. Day 3: "LV 2" Magmite merge -> Common gift (Training Weights +100 HP /
  Boxing Glove "On Victory: team +5 Damage permanently" / Treasure Map "next gift one tier higher"); took
  Boxing Glove. Won Day 3.
- Day 4: "LV 2" Venopuff merge with the Shiny team copy: **the Lv2 is still Shiny and its bonus scales
  ("+2 Poison permanently")**, and it kept its growth (Poison 9). Gift: Quick Flag / Gold Trophy / Treasure
  Map; took Treasure Map. Lost Day 4 (they had 353/1400).
- Day 5: Thorntail instead of the plain Stingarde (sim 46% -> 56%); then a **Shiny Stingarde card for $10**
  appeared in the Gold Potion's refilled slot. Lost Day 5 (-3, 5 lives).
- Event after Day 5: Ignit again; adopted. **Shiny Ignit = Poison 2 + Burn 1** (Shiny added Poison).
- Day 6: Runerock (21% -> 35%) and a 2nd Runerock; won. Day 7: Formiqueen next to Commons; won at a 36% sim
  estimate. Day 8: "LV 2" Runerock merge with Treasure Map: **the Uncommon Runerock gave a Rare gift** (Rigged
  Dice / Power Bell / Mega Duplicator); took Rigged Dice ("[Unique] the first shop each day stocks only the
  rarest monsters and items your shop rank allows"). Ignit on the team would have cost ~23% (sim 30% vs 53%),
  so it was benched and the evolution is still unseen. Lost Day 8 to a Burn team (2 lives left).
- **Sim calibration over both runs** (the sim's win chance for the team I fielded vs the result): about 62%
  predicted on average and 60% actual over 20 battles. Misses both ways (lost at 73-76%, won at 35-36%).
