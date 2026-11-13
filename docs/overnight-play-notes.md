# Overnight manual play notes (2026-11-12 night)

Claude played Batomon Showdown by hand (screenshots + clicks), **Casual Mode only**, to learn things
for the bot. Each section is written as it happened; the summary of lessons is at the top once done.

## Lessons for the bot (summary)

_(filled in at the end)_

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
