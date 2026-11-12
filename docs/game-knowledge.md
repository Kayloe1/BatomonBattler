# Game knowledge from the September runs

These are the lessons from Ed's September toolkit (private repo Kayloe1/batomon, Runs 1 to 18, Pantra, mostly Casual, six runs won) that should still hold after the patches since. Hard numbers (damage, prices, HP, odds, thresholds) are left out on purpose: read those from the screen or from `data/`. The bot-usable form is `knowledge.py`; this page explains it.

The longer write-up with the September numbers is the Claude Doc "Batomon quirks and tips from the September repo" (Library copy: `batomon/september-repo-tips.md`). Treat its numbers as history, not as current values.

## Card wording and positions

Team slots 0 to 2 are the top row and 3 to 5 the bottom row, left to right. The team faces right.

| Card says | Means |
|---|---|
| behind | the ally directly to its left, same row |
| in front | the ally directly to its right, same row |
| above | the slot directly above, same column |
| adjacent | left, right, above and below; never diagonal |
| opposite | the mirrored enemy slot |

- The top-middle slot has three neighbours, so the carry goes there and its helpers surround it: an "in front" helper on its left, a "behind" helper on its right, an "above" helper below it.
- Buffers that hit adjacent allies go where they touch the most qualifying allies, not only the carry.
- Merged monsters can land in a different slot and leave a slot empty, so re-check the layout after every merge.
- In the game, hovering your own monster outlines what its positional effect targets, and same-row drags between two occupied team slots silently fail (route through an empty slot).

## What to avoid

- **Dirgefin** knocks out all Common monsters on both sides.
- Self-knockout monsters (Stingarde, Pyronade, Electranade) are good early and dead slots later, unless a Shiny copy has lost the drawback.
- **Recombobulator** (event) and anything that transforms monsters wipes permanent growth.
- Trainers: Mad Scientist (replaces your team mid-run) and Gentleman (no Commons or Uncommons after the first days).
- An egg on the team does nothing: bench it as soon as it arrives.
- Fool's Gold cancels item scalers. Piggy Bank fights spending down. Incense shops have no cheap fodder.

## Items that need a decision

- **Tickets replace the whole shop** with one rarity, so buy what you want first. Blue (Rare) is the best way to find amplifiers.
- **Basic Bait** lowers the shop rank for the rest of the run: useful early, harmful while you hunt Rare amplifiers, fine again late. It is missing from the November item capture, so check that it still exists.
- **Upgrade Disc** levels the very next monster bought, even a free one, and that copy will not merge.
- Red Coin trades a life for money; Green Stone may transform a Common carry; Voucher gives a random shop monster.
- Plain free items (Cake, Coupon, Fake Coin, Feast, Gray Chip, berries, Focus Pill) are safe to use. Coupon goes before buying monsters.

## Priorities that won runs

1. The first days decide the run. Losses cost more lives later, and every run that lost several early fights ran out of lives before its engine paid off. Early on, buy damage that fights today and fill every slot.
2. After a clear early loss, spend the next shop on damage and merges that work today.
3. Amplifiers beat levels. Once the carry exists, a helper that triggers it, speeds it up or gives it Multicast outranks another copy of it.
4. Buy shop cards with a level tag: they complete a merge, and every merge gives a trinket gift. Event, disc and candy level-ups give none.
5. A level-up raises the ability's numbers, not current damage, so check what a level actually improves.
6. Finish Common copy sets early. As shop rank rises Commons get rare; switch to the higher-rarity cards then.
7. Spend down before every battle (money earns nothing), or lock the shop for a card you can't afford yet. Reroll only if the money left still buys the target.
8. Sell idle bench monsters. Never sell a monster with large permanent growth.
9. Replace slots that deal almost nothing and buff nobody.
10. Enemies can't be scouted. Late losses come from heal/shield teams and from burst teams. Pantra has no anti-heal, so both are beaten with more damage per second; keep at most one defensive hedge slot.

## Engines that worked

- A Bug carry that grows each time you buy a Bug (Guardiant), fed by buying and selling cheap Bugs, with Cicadence below, Saberhorn in front and Formiqueen beside it.
- A multi-hit carry (Velocect) with Cicadence below and Zephyrex in front; flat damage bonuses multiply by its hit count.
- Stellagon next to monsters that have no abilities.
- Craghorn fed by free items; Dollhime growing with each trinket.
- A Burn engine (Lignite with Magmalith below) beat heal teams but lost to burst.

## Trainers

Monster Ranger and Swim Coach each won twice and Bug Catcher once. Youngster's free rerolls feed a fodder loop. Burglar is strong late but weak early; Rich Lady's higher rank thins Commons; Twins only triggers on real level 3 merges; Masked Man is idle at first and random.
