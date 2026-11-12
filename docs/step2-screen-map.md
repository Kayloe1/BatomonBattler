# Step 2: screen map of a run (Casual, Pantra, 2026-11-11)

Observed by playing day 1 of a Casual run by hand. Game window was about 970 x 545 px of game area inside a 1456 x 819 screen; all positions below should be stored as fractions of the game area, not fixed pixels, because the window moves.

## Flow
1. Main menu: New Run, Batopedia, Settings, Quit. Rank badge bottom right.
2. New Run: pick region card (Pantra / Jinto), pick Ranked Mode or Casual Mode, then CONFIRM. **Ranked Mode is selected by default**, so the bot must always check the mode button before confirming.
3. Trainer pick: 3 random trainer cards, click one.
4. Shop screen (one per day), then BATTLE!
5. "Opponent Found!", VS screen with both player names, then the battle.
6. Result box ("You won! You earned a Badge!") with Replay, Stats, HIDE and CONFIRM. CONFIRM goes to the next day's shop.

## Shop screen
- Top bar: lives (heart, starts at 10), DAY n, badges n/10 (10 badges wins the run), Batopedia, settings, exit.
- Left: trainer card and ability, and the trainer HP bar (300 on day 1, 500 on day 2).
- BENCH: 4 slots. MY TEAM: 3 x 2 grid (6 slots). New buys fill the bottom row from the right.
- Shop bar: "Rank n" with the odds per rarity (rank 3: 75% Common, 25% Uncommon; rank 4: 67 / 30 / 3% Rare). Rank went up by 1 from day 1 to day 2.
- Money shown in a red tab above the shop. Day 1: $40 (Rich Lady adds $10, so base is $30). Day 2: $40 after ending day 1 with $5, so income looks like $35 on top of what is left over (to confirm).
- Shop row: 4 monster cards and 1 item card ("1/1 ITEM" = item uses left today). Each card shows name, price, and stat badges. Cards you cannot afford are greyed out.
- REROLL $3 (left), LOCK (above shop), BATTLE! (right).

## Controls
- Left click a shop card: buys it at once (no confirm). Left click an item: uses it at once.
- After the item was used, its slot was refilled with another monster card.
- Hover a monster: info panel on the right with name, sell value, rarity, type, cooldown and effects. Right click: inspect.
- Drag a monster to another slot to move it. While dragging, the shop bar turns into "DRAG HERE TO SELL ($n)".
- Merging copies (drag onto same species or automatic) not yet tested.

## Battle screen
- Each side has a trainer HP bar; monsters attack on their own cooldowns and damage the enemy trainer's HP. Status stacks (poison etc.) show as icons under each HP bar.
- Pause and Fast Forward buttons at the top centre. With fast forward a day 1 battle ended in under 10 seconds.
- First to 0 HP loses. Win = 1 badge. (Loss presumably costs lives; not yet seen.)

## Added 2026-11-11 (third session): seen while the bot played days 2 to 8

All positions are in the 2560 x 1440 picture the reader uses; the boxes are in `reader.py`.

### Screens after BATTLE!
1. **Matchmaking**: the shop stays, a dialog "Searching for opponent.." then "Opponent Found!" replaces the shop bar (about 2 s). The right button reads CANCEL, then a grey BATTLE!.
2. **VS screen** with both player names (about 4 s), then a fade.
3. **Battle**: both trainers' HP bars (current/max), trainer portraits in the bottom corners, pause and fast forward at the top centre. Fast forward is **red when on** and it stays on between battles. A day 2 battle took about 8 s with it on.
4. **Result box**: "You won! You earned a Badge!" with the badge case, or "You lost. You lose N Lives." with hearts. Buttons: Replay and Stats (top left), HIDE (bottom left), CONFIRM (bottom right, same place as BATTLE!).
5. **Stats** (from the result box): MY TEAM and OPPONENT TEAM, one box per slot with "Dealt n damage", "Healed n HP", "Inflicted n Poison", "Triggered n time(s)". Close with the X at the top right. It scrolls.
6. After CONFIRM: the next shop, or an **event**, or the **end of the run**.

### Events
Black screen with a picture, up to three choice boxes (grey title, black effect line) and a story box; SHOW TEAM at the bottom left. Clicking a choice goes to the shop.
- Day 3, dragon's hoard: Gain Dragon Egg / Gain Hero's Sword / Gain $20.
- Day 6, baby basilisk: Gain Ignit / Get a Rare trinket gift / Gain $40.
- After the day 7 loss left 0 lives, mysterious trainer: each choice gives a life plus a Super Rare trinket gift / a random level 2 Super Rare monster / Mysterious Charm. The bot took the charm and continued with 1 life.

### End of the run
"This journey ends here." with the trainer, badges, final team, day, lives and trinkets. Buttons: camera (bottom left), **New Run** and **Main Menu** (bottom right).

### Shop details
- A bought card leaves an empty light grey slot. After an item is used its slot refills (with a monster on day 2, with another item on day 3).
- Cards you cannot afford: grey name, red price, grey frame.
- Frame colour is rarity: grey Common, green Uncommon, blue Rare, purple Super Rare, orange Legendary.
- Stat badge colours: red damage, blue heal, pale blue shield, purple poison, orange burn, yellow shock, teal "x2"/"x3" multicast.
- **LOCK** puts a padlock on every card and the button becomes UNLOCK (it holds the shop for the next day; not yet confirmed across a day).
- **Sell**: Electranade bought for $25 sold for $13.
- **Reroll** stayed $3 through day 7.
- **Copies**: buying a second Dribblet put it in a free slot at level 1; dragging one onto the other only swapped them. Ed: three copies make a level 2.
- New buys go to a free team slot; with the team full nothing was bought, so the bench is untested.

### Numbers observed (Rich Lady run)
| Day | Trainer HP | Shop rank | Odds C/U/R/SR/L | Result | Lives after |
|---|---|---|---|---|---|
| 2 | 500 | 4 | 67/30/3/0/0 | win | 10 |
| 3 | 800 | 5 | 55/30/15/0/0 | loss, -2 | 8 |
| 4 | 1400 | 6 | 45/32/20/3/0 | win | 8 |
| 5 | 2400 | 7 | 30/40/25/5/0 | loss, -3 | 5 |
| 6 | 3800 | 8 | 25/30/35/10/0 | loss, -3 | 2 |
| 7 | 5700 | 9 | 20/25/38/15/2 | loss, -3 (then +1 from the event) | 1 |
| 8 | 10375 | 10 | 15/20/40/20/5 | loss | 0 |

The day 8 HP may include the Mysterious Charm; treat it as unexplained. Money grew fast because the simple rules stop buying once the team is full ($40, 75, 98, 148, 243, 303, 344 at the start of days 2 to 8).

### Checks against the data files
- Day 2 Stats screen: Brawlmantis 3 casts, 150 damage; Venopuff 5 casts, 25 damage, 20 poison; Dribblet 6 casts, 120 healed; Mosslug 3 casts, 75 damage, 90 healed; Panbud 3 casts, 75 damage. All fit the CSV values (with +5 damage from a Cake on Venopuff and Mosslug, and Mosslug's +20 damage per cast).
- Brawlmantis "On Victory: this and Common allies +10 Damage" was seen after both wins. Dribblet (heal only) gained a damage badge from it.
- Prices seen and matching `names.json`: every card met, including Gaiadrasil $60, Shelldra $40, Stalagrove $35.

## Added 2026-11-11 (fourth session): starting a run, leveling up, trinkets

### New Run dialog (opens over the end-of-run screen after clicking New Run)
- Two region cards, Pantra and Jinto. The selected card has a pink header, the other is grey.
- Two mode buttons, **Ranked Mode** and **Casual Mode**. The selected one is blue, the other grey (checked by clicking each once). It opened with Casual selected after a Casual run, so it seems to remember the last mode; the earlier note said Ranked was the default.
- CANCEL bottom left, CONFIRM bottom right.

### Trainer pick
Three trainer cards (yellow header with the name, portrait, ability text) over a "Select a trainer to begin your journey." box. Clicking a card starts day 1. Seen: Witch, Painter, Monster Ranger.

### Day 1
Monster Ranger starts with one Uncommon monster (Electranade), $30, 300 HP, shop rank 1 (100% Common), reroll $3. With $0 the REROLL button turns grey.

### Leveling up and the trinket gift
- **Three copies make a level 2** (as Ed said). The third copy merges at once when bought: "Electranade leveled up! Electranade gives you a gift." with a gift box marked OPEN over the dimmed shop.
- Clicking the box shows "Select a trinket." with **three** trinket cards (name, rarity, effect) and a HIDE button. Clicking a card takes it and returns to the shop. The backpack icon then shows the trinket count.
- Offers seen: Fire Bell / Poison Bell / Power Crown (all Uncommon), then Rally Flag / Earth Crest / Poison Orb. The first three match `data/trinkets.csv` word for word.
- An event can also lead straight to a gift box.
- Level label colours: bronze at level 1, silver at level 2, gold at level 3.
- Electranade Shock by level: 25, 50, 75.
- Fire Bell raised Magmite's Burn in the shop from 4 to 9, as its text says (+5).
- Green Stone turned a Common team monster into an Uncommon one; in this run that produced an Electranade.

### Numbers observed (Monster Ranger run)
| Day | Trainer HP | Shop rank and odds C/U/R/SR/L | Result | Lives after |
|---|---|---|---|---|
| 1 | 300 | 1: 100/0/0/0/0 | win | 10 |
| 2 | 500 | 2: 90/10/0/0/0 | loss, -1 | 9 |
| 3 | 800 | 3: 75/25/0/0/0 | loss, -2 | 7 |
| 4 | 1400 | 4 | loss, -2 | 5 |
| 5 | 2400 | 5 | loss, -3 (after a Red Coin took 1 life in the shop: 5 to 4 lives, $115 to $135) | 1 |
| 6 | 3800 | 6 | loss, then the last-life event gave 1 life back | 1 |
| 7 | 7125 | 7: 30/40/25/5/0 | loss | 0 |

(Values for days 4 to 7 are from `logs\run_*.jsonl`.)

- Lives lost per loss grow with the day: 1 on day 2, 2 on days 3 and 4, 3 from day 5.
- Shop rank goes up by 1 a day (Rich Lady's +2 explains her higher ranks in the first run).
- Trainer HP by day, same in both runs: 300, 500, 800, 1400, 2400, 3800, 5700, and 8300 on day 8 (seen on the opponent's bar).
- **After the last-life event, your own trainer HP is 25% higher**: 7125 = 5700 x 1.25 on day 7 here, and 10375 = 8300 x 1.25 on day 8 in the first run. Whether that comes from being on the last life or from the event's reward is not known.
- Red Coin appears to trade 1 life for $20 (seen once).

## Still to map
The main menu, a won run, level 4, whether LOCK carries a shop over to the next day, the bench when the team is full, what the flag and arrow marks on team slots mean.
