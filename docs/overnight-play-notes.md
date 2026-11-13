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
