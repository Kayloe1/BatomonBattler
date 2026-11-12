"""Every battle rule the simulator uses, with where it comes from.

status:
  verified  - reproduced numerically from a recorded battle (see sim/cases/)
  glossary  - the game's own keyword tooltip (copied in the older Kayloe1/batomon notes, section 5/6)
  observed  - seen in play but not checked numerically by this simulator
  guess     - not known; chosen to be plausible. Change it here when a battle disproves it.

Engine switches (values the code reads) are in SETTINGS. The RULES list is documentation and is
printed by `python -m sim --rules`.
"""

SETTINGS = {
    # Seconds between Poison ticks, and whether ticks run on one battle clock (t = 1, 2, 3...).
    "poison_interval": 1.0,
    "burn_interval": 0.5,
    # Status damage against a shield is multiplied by this.
    "status_vs_shield": 0.85,
    # How Shock adds damage to an attack: "flat" adds the stacks to every hit,
    # "percent" adds stacks% to every hit, "none" ignores Shock.
    "shock_mode": "flat",
    # Heal cannot raise HP above the maximum.
    "heal_cap": True,
    # At equal times the player's side acts first, then the opponent's.
    "player_first_on_ties": True,
    # Longest battle before it is called a draw.
    "time_limit": 300.0,
    # Stop chains of triggers that trigger each other.
    "max_trigger_depth": 8,
}

RULES = [
    # --- time ---
    ("Each monster first acts when its full cooldown has passed (no head start), then every cooldown.",
     "verified", "Day 2 and Day 3 battles: every cast count on both Stats screens matches."),
    ("Cooldown Speed +X% divides the cooldown by (1 + X/100); bonuses add up.",
     "glossary", "'Increases how frequently you trigger by lowering cooldown.' The exact formula is a guess."),
    ("Charge N s moves the cooldown timer forward by N s; a full timer casts at once.",
     "glossary", "'Progresses cooldown timer.'"),
    ("Several events at the same instant: casts first (player's side, slots 1-6, then the opponent's), then Burn and Poison ticks.",
     "guess", "Before the 2026-09-21 patch the enemy moved first on ties (old notes)."),
    ("There is no time limit; at 300 s the battle is called a draw.",
     "guess", "Old notes: fights up to ~26 s seen, no draw seen."),
    ("A trainer loses the moment its HP reaches 0, even mid-instant (a later cast at the same time does not happen). If both reach 0 on the same Poison/Burn tick it is a draw.",
     "guess", "Never seen."),
    # --- damage ---
    ("Monsters hit the enemy trainer, never enemy monsters. Shield absorbs damage before HP.",
     "observed", "Battle screen: only trainer HP bars; 'Shield: Blocks damage.'"),
    ("Poison deals its stacks as damage once per second, on the battle clock (t = 1, 2, 3 ...), and never decays.",
     "verified", "Day 2: 325 direct + 164 Poison ticks ends the battle at t = 19 s, inside the 18-20 s window the cast counts allow. Day 3: 101 Poison on Ed's bar and 16 on the opponent's match exactly."),
    ("Burn deals its stacks twice a second and loses 1 stack after each tick.",
     "glossary", "'Takes damage twice a second. Burn decreases by 1 after causing damage.' Tick timing on the battle clock is a guess."),
    ("Shock adds its stacks as extra damage to every damaging hit the shocked trainer takes, and never decays.",
     "guess", "Glossary: 'Takes additional damage when attacked.' The 25 Shock from Electranade was still on the bar at the end of Day 3, so it does not decay or get used up. Flat vs percent is not known; flat fits Day 3 better."),
    ("Poison and Burn ticks do 15% less damage while the trainer has a shield, and hit the shield first.",
     "glossary", "'Damage from status effects deal 15% less damage against shields.'"),
    ("Heal cannot raise HP above the maximum.",
     "guess", "The Stats screen counts the full heal even at full HP (Day 2 Dribblet: 6 x 20 = 120), so it cannot show this."),
    ("Multicast N repeats the whole active N times; each repeat counts as one trigger.",
     "glossary", "Old notes, section 5."),
    ("'On Cast' passives run once per cast, after all Multicast repeats.",
     "guess", ""),
    ("'Deal' numbers in the Stats screen are the hit damage only; Poison, Burn and Shock ticks are not in 'Dealt'.",
     "verified", "Day 2: Venopuff 'Dealt 25' = 5 casts x 5, while its Poison did ~164."),
    ("'Trigger this/ally' makes the monster cast at once without resetting its own timer.",
     "guess", ""),
    # --- positions ---
    ("Team slots 1-3 are the top row and 4-6 the bottom row, left to right; your team faces right.",
     "observed", "Stats screen order and the battle screen."),
    ("Behind = left neighbour in the row; In front = right neighbour; Above = same column, top row.",
     "glossary", "Old notes section 6, confirmed with the hover outline."),
    ("Adjacent = left, right, above or below; not diagonal.",
     "verified", "Day 3: the opponent's Venopuff (bottom row, diagonal to Noxnimbus) kept 8 Poison while the Spinarai beside Noxnimbus went 5 -> 17. Old notes: Gaiadrasil matched its four orthogonal neighbours."),
    ("Opposite = the enemy monster in the same slot number.",
     "glossary", "Old notes section 6."),
    # --- stats on the cards ---
    ("When a slot gives 'stats' (the badges the reader sees on the shop screen), those replace the Batopedia numbers. Trinket and trainer bonuses that change badges are then assumed to be in them already.",
     "guess", "Fire Bell's +5 Burn did show on the card (step 2 notes); whether Wood Sword, Small Club, Chef etc. also show is not checked."),
    ("Cooldown and Multicast bonuses from trinkets are always applied (badges do not show cooldown).",
     "guess", ""),
    ("Trainer HP comes from the input (the reader reads it on the shop screen); +HP trinkets are not added again.",
     "guess", ""),
    # --- statuses ---
    ("Knockout stops a monster from acting and disables its abilities. Protect cancels one Knockout.",
     "glossary", "'A knocked out monster cannot trigger, and its abilities are disabled.' 'Prevents Knockout. Protect decreases by 1 when it prevents a Knockout.'"),
    ("Self-knockout monsters (Stingarde, Electranade, Pyronade) act once and are then knocked out.",
     "observed", "Old notes; Day 3 Electranade."),
    ("Debuffs that Runerock/Sirenade remove are the Poison, Burn and Shock on your own trainer; a percentage rounds down.",
     "guess", ""),
    ("Noxnimbus' bonus Poison goes to adjacent Toxic allies only (not itself).",
     "verified", "Day 3: Noxnimbus stayed at 5 Poison, the Spinarai beside it went 5 -> 17 after 4 casts."),
    ("Mosslug deals its damage first, then gains its On Cast damage.",
     "verified", "Day 2: 5 + 25 + 45 = 75 dealt in 3 casts; Day 3: 15 -> 55 after 2 casts."),
    ("Celestia's disable hits Ongoing monsters in its row on both sides.",
     "guess", "Card: 'Disable abilities of all Ongoing monsters in this row'."),
    ("The Dragon Egg has a 10 s cooldown and deals 1 damage.",
     "guess", "Day 2: 1 damage, 1 trigger in a ~19 s battle, so its cooldown is 9.5-19 s."),
    ("Random effects (Tempo Charm, Reapra Lv4) use a seeded random generator.",
     "guess", ""),
]

NOT_SIMULATED = [
    "Shop-phase effects (Guardiant, Cinderfly and Shogapede growth, Brawlmantis On Victory, Gildshell, Berroon, Plunderbird $, Craghorn items) - they change the badges the reader sees, not the battle.",
    "Shiny variants (each Shiny changes something different).",
    "Trinkets: Fancy Sword, Scrap Sword and Zenith Stone are not modelled; Magic Lasso is not modelled.",
    "Monsters from other regions (Jinto) and the 6 locked Mythical trinkets.",
]
