# Overnight manual play notes (2026-11-12 night)

Claude played Batomon Showdown by hand (screenshots + clicks), **Casual Mode only**, to learn things
for the bot. Each section is written as it happened; the summary of lessons is at the top once done.

## Lessons for the bot (summary)

Two hand-played Casual runs: Run 1 (Egg Breeder) ended on Day 13 with 7 badges; Run 2 (Witch) **won**
(10 badges on Day 14). A third run was then played by the bot itself (`play.py --new-run`) with the changes
below; see the end of the log.

**Mechanics confirmed tonight** (details and evidence in the log below):
- Shiny: each species changes differently. Self-knockout monsters lose the knockout (Stingarde); monsters with
  no passive gain "+1 stat per level permanently at battle start" (Magmite, Venopuff); others get ~+20% on a
  key number (Stalagrove 15->18%, Cobrex Poison 300->360, Geminiss 50->60%, Blixie 1->1.2x, Torrantler
  cooldown 7->5.5 s). Shiny survives merges. Shiny cards are priced like plain ones.
- Merges keep the largest growth and the team copy's slot. **Gift rarity = merged monster's rarity**
  (Common -> Common trinkets, Rare -> Rare, Legendary -> Legendary); Treasure Map raises it one tier.
- Event level-ups keep permanent growth. Candies and Growth/Shiny Potions can hit **bench** monsters.
- Using an item refills its shop slot with a new card. A Coupon only discounts the current shop.
- Events come after Days 2, 5 and 8 (none after 11). The last-life rescue offers a Super Rare gift / a random
  Lv2 Super Rare / **Mysterious Charm (+25% HP)**. **The +25% HP the engine assumed after every rescue comes
  from that Charm**, not the rescue (the old simple rules always took it).
- Trainer HP Day 14 = 63000. Two Giant Clubs stack additively (x2.4). Link Cable makes Gaiadrasil add up
  the whole team, and Gaiadrasil counts allies' Ongoing damage (Fumungus's Poison damage).
- Simulator timing: "Triggered" counts casts (not Multicast hits); "Dealt" includes the Shock bonus; Shock
  gained at an instant counts from the next instant; all casts at an instant resolve before deaths.
- The simulator's win chances were reasonably calibrated over 20 battles (~62% predicted, 60% won).

**Strategy lessons:**
- Day 1-2: Poison (Venopuff) beats flat damage; a single Venopuff beat two Guardiants.
- Mid game: **permanent growers win runs** (Fumungus+Noxalith, Thorntail, Warhorn, Boxing Glove).
  Late game: Burn burst (Lignite+Magmalith, Blazewing Lv3) kills in ~15 s; slow carries lose to it.
- **Multiplying trinkets on one grown carry** (Giant Club x2, Winged Crown, Zenith Stone) turned Run 2 around.
- Random Legendaries without synergy (Legendary Potion) were weak; Legendary merges were strong (Legendary gifts).
- Rigged Dice + Mirror Potion make "LV 2" copies show up often late.

**Changed in the code tonight** (all with tests; `python -m unittest discover tests`, `python -m sim --check`):
- Reader: Shiny team/bench monsters (colour histogram vs `Name@shiny` templates) and the SHINY tag on shop
  cards; bought Shiny cards are learned as `Name@shiny`; new sprites for 7 Legendaries/Shinies.
- Model/engine: `shiny` flag on units and cards, kept through merges; events value "Turn a monster SHINY",
  Mysterious Charm and any "+N HP"/"+N% HP" trinket; trinket picks apply stat trinkets to badge stats
  (Giant Club was scored 0 before); HP bonus only with the Charm; Day 14 HP; candies reach level 4 and hit
  the bench; Witch potions, Ultra Candy, Legendary/Mirror/Glimmer Potions in the data.
- Simulator: the timing fixes above, Shiny effects, additive clubs, Gaiadrasil counting Ongoing damage;
  5 new recorded cases in `sim/cases/`.
- Data: `data/special_monsters.csv` (Batopedia "???" tab), new trinkets and items.
- **The game window was resized** with `SetWindowPos` so its client area is exactly 2560 x 1440 (it was
  2560 x 1600 with black bars); the reader handles both.

## To build (found tonight, not built yet)
1. Item-slot refill is not modelled (`model.use_item` leaves the slot empty). Live play is unaffected (the
   bot reads the refilled shop after each action); only the value of using a paid item is a bit low.
2. Event-only monsters are unknown to the simulator: Ignit (Burn 1, evolves on a victory into something
   unseen), Talonite, Wishwash, Cosmivore, Faebloom, Omnichrome (`data/special_monsters.csv`), Dryadell.
   Rhizuka (a foreign Rare from an event) is now in `data/foreign_monsters.csv` without its passive.
3. The engine's "feed and sell" Bug move scored above keeping a strong Bug (Stingarde) on Day 2. Looked at
   again on 2026-11-13: the simulator pool had it as a near tie (15% vs 12%), so it is left as it is.
4. Opponent Shiny monsters in battle are not read as Shiny (battle matching uses plain sprites only).
5. ~~The Stats window does not find yellow "Inflicted N Shock" lines.~~ Done 2026-11-13: each status has
   its own line colour (purple Poison, yellow Shock, orange Burn) and "Applied N shield" is brown; all are
   read now.
6. **OVERFLOW screen** (now handled: `reader.read_overflow`, `hands.resolve_overflow`, play.py sells the
   weakest named bench monster). An event monster that arrives with team and bench full sits in an
   "OVERFLOW" slot right of the team ("YOUR TEAM IS FULL. DRAG HERE TO SELL A MONSTER."); the team grid
   shifts left, the bench does not. Selling any bench monster (drag onto the message box) moves the overflow
   monster into the freed slot and the shop returns. Capture: `captures/stuck_20261112_211945.png`; probe
   colours: OVERFLOW header (255,189,8) at (1700,655), grey buttons (90,90,99) at (100,1215) and (2300,1215).
   Bot Run 3 (Chemist) stopped here on Day 9 with 4 badges and 1 life; the sale was done by hand.

## Done on 2026-11-13 (after the night)
- **Card sprites**: the shop-card cut-out was seeded from the top row, so a monster that pokes above the
  card's picture rows lost its inside and only its outline was saved (or a greyed-out card was saved in
  grey). Fixed, and outline-only or grey cut-outs are no longer saved. The 30 committed outline sprites
  were kept: they still name their monster correctly in battle (Boomagon, Magmalith, Dracana, Shogapede).
- **Stats window**: two wider shapes of the digit 3 taught (142 of 1228 lines in the saved captures read
  '?'; now none). Shock, Burn and shield lines are read.
- **Stats scroll never worked**: pyautogui on Windows sends `scroll(n)` as n raw wheel units, and a notch
  is 120, so `scroll(-15)` was 1/8 of a notch. Every saved `stats_bottom` is the same as `stats_top`, so the
  opponent's back row was never read. Now whole notches are sent. **Not yet checked in the game.**
- **Battle names**: the sprite-match rule was too strict (needed 2x the runner-up's distance). Set by eye
  on 48 cases: at 50 or less a 1.15x lead, up to 66 a 1.3x lead. Plain sprites match Shiny monsters at
  40-65. Named slots in the 32 saved battles: 253 before, 294 after, no name changed.
- `sim.from_logs` names my unnamed battle slots from the logged shop team (unique level + stats match).
- Still the main reason logged battles cannot be checked against the simulator: unnamed opponents
  (52 of 56 logged battles skipped; 24 of them are from before the battle screen was read at all).

### Casual run on 2026-11-13 morning (Bug Catcher: 8 badges, out on day 13)
Stops fixed on the way, each with a test:
- Card font had no 7 (a Coupon took Mosslug to $7).
- A monster bought for $0 (Bug Catcher's first Bug of the day) sells for $0: the sell check now accepts
  unchanged money when one monster really left.
- **Stats scroll now works.** Whole wheel notches reach the game; the scrolled picture was then thrown away
  because the screen check looked at the first yellow header (scrolls away) and the scrollbar track (the
  yellow handle arrives). `reader.is_stats_window` uses the title bar and close button. Days 6-13: all
  12 slots read with no problems.
- Gift box and trinket pick after an event are drawn over plain black, not the dimmed shop: both are now
  recognised by their own pictures.
- **Opponents are named from the Stats window.** Its pictures are the shop card pictures, pixel for pixel
  (known monsters score 0, runner-up 70+). `read_stats` returns `my_names` / `opponent_names`;
  `sim.from_logs` fills unnamed battle slots from them (older logs: read from the saved Stats pictures,
  cached in logs/stats_names_cache.json). Slot numbers agree with the battle screen: 304 of 304.
  Logged battles the simulator can check went from 4 to 12 (agrees on 11). Older logs still miss the
  opponent's back row (no scrolled picture); new runs will not.

### Afternoon of 2026-11-13 (Swim Coach run, branch claude/casual-runs)
- **Shop lock**: the old rule locked whenever one card was a little too dear (judged against having $0),
  and the next morning the bot bought the locked card after only 5 of 18 locks. `_lock_choice` now runs
  tomorrow's first decision (tomorrow's money, these cards) and locks only if its best buy is a card that
  is too dear today and beats a fresh shop. Replayed on the 18 logged locks: 7 kept.
- **Unknown monsters** (e.g. an event's foreign Jinto monster): they play as the `Unknown Rare` stand-in
  (data/stand_in_monsters.csv: own badges, Rare-typical 5.0 s, no passive) so they can be fielded or sold.
  Before, an unnamed monster could do neither and blocked a bench slot for the run.
- **Learning them**: on the shop screen the bot hovers each unnamed monster once and reads the info panel
  (`reader.read_info_panel`: name and rarity in the caps font, type, cooldown, active numbers by line
  colour). A new name goes into data/foreign_monsters.csv with the panel picture for its passive
  (`learn_monsters.py`); the sprite is saved either way. Passives are read by a person from the picture.
- Pyrokami (Jinto Rare, Fire, 3.6 s, Deal 5 + Burn 5, On Cast +10 Burn) added by hand from its panel,
  with its passive in the simulator.
- The event "Gain a foreign Rare monster" is scored from the learned Jinto Rares (event-only monsters
  are marked `event_only` and left out), not a fixed guess.
- Dead weight never sells a bench monster that the arrangement puts on the team (it used to).
- Title screen: recognised without its blinking label, and clicked again while the intro ignores clicks.
- Overflow is accepted after a trinket pick, result, cash-in or continue (Swim Coach's daily Water monster).

Done later in the night: Purple Egg named on team/bench (kept out of battle matching), Mirror / Glimmer /
Legendary Potions modelled, and `Params.grow_next` (tomorrow is scored with one battle's permanent growth).

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
- Event after Day 8: Dryad statue -> "Give a monster Grass typing, Gain Dryadell" / "Gain Mysterious Gem" /
  "Gain Dryad's Charm". **Dryad's Charm = Legendary, "[Unique] +30% HP"** (Day 9 HP 11600 -> 15080).
- Day 9 with **Rigged Dice**: the first shop was all Legendaries plus a **Legendary Potion ($5): "Fill your team
  and bench with random Legendary monsters. They have no sell value."** Sold 7 monsters (keeping Thorntail and
  Shiny Venopuff) and used it: 8 random Legendaries (2 Galvanine, 2 Draconarch, Stellagon, 2 Torrantler,
  Gaiadrasil). Monsters from it sell for $0. Lost Day 9 badly (they kept 9584/11600): **random Legendaries
  without synergy were not a strong team.**
- Rescue: took the Super Rare trinket gift this time: Haste Orb / Blitz Bell (shop monsters +25% Cooldown
  Speed) / Haste Crown (top middle +20% Cooldown Speed).
- Day 10 (1 life): "LV 2" Draconarch merged the two potion copies: **potion monsters merge normally**, and the
  Legendary merge gave **Legendary** trinkets: Candy Jar (Commons/Uncommons permanently level up to 3 at
  battle start) / Barbell (+5000 HP) / **Zenith Stone (stat gains +80%)**; took Zenith Stone (Thorntail's
  growth jumped). **Glimmer Potion ($6, Legendary): every monster in the shop this turn is Shiny.** Shiny
  cards seen: Cobrex Poison 300 -> 360, Geminiss +50% -> +60% Shield, Blixie gives 1.2x its Burn, Torrantler
  cooldown 7 -> 5.5 s. **Shiny is roughly +20% on the key number** for monsters that have one. Shiny Cobrex
  replaced a Galvanine (sim 57% -> 75%); won Day 10.
- Day 11: **Mirror Potion ($5, Legendary): "Roll a shop that contains only monsters on your team and bench"**
  -> it offered a "LV 2" Galvanine (merge) and 2 Saberhorns. Legendary gift: Metronome / Mighty Bell (shop
  monsters +300 Damage) / **Giant Club (monsters with a cooldown of 5 s or more have +70% stats)**. Giant Club
  shows on cards at once, bench and shop included (Thorntail 888 -> 1510). Won Day 11.
- Day 12: Saberhorn Lv2 merge -> Candy Jar / **Winged Crown ("[Unique] top middle monster +1 Multicast")** /
  Metronome; Thorntail sits top middle, so it now hits twice. Won.
- **No event after Day 11 in either run** (events after Days 2, 5 and 8; the rescue is its own screen).
- Day 13: Cobrex Lv2 merge (Shiny kept) -> a **second Giant Club: they stack** (Thorntail 2349 -> 3316).
  Mirror Potion again (no Gaiadrasil). Won (9 badges).
- Day 14: **trainer HP is 63000 on Day 14** (the opponent's bar; ours was 81900 with Dryad's Charm). The
  engine extrapolates 66220. Rank shows "Max". Won with 1216/81900 left -> **Run 2 won, 10 badges**:
  "You are a Batomon champion!" with the same buttons as the run-over screen (the reader calls it
  `run_over`; capture `captures/manual_run_won_champion.png`).

### What Run 2 says about strategy
- The comeback came from **trinkets that multiply** (Giant Club x2, Winged Crown, Zenith Stone) on one grown
  carry (Thorntail 50 -> ~4000 with poison allies), and from Legendary merges, whose gifts are Legendary.
- Rigged Dice + Mirror Potion is a merge engine late: Rigged Dice makes the first shop Legendary-only and
  Mirror Potion rolls owned species, so "LV 2" copies show up often.

### Run 3 (Casual, Chemist; played by the bot, `play.py --new-run`)
- The bot started the Casual run itself (Casual read twice before Confirm) and picked Chemist.
- It stopped three times on things it had not seen, each fixed and taught: the foreign Rhizuka's level label
  (a horn pixel read as a glyph), an unreadable "MASKED MAN" trainer card and "LOCKED BOX" trinket name,
  and the OVERFLOW screen (an event's Shiny Saberhorn with team and bench full; sold a Frizzly by hand).
- **Run over on Day 9 with 4 badges** (lost Days 4, 7, 8 and 9). The OVERFLOW handling did not come up again,
  so it is tested on the saved capture only.
