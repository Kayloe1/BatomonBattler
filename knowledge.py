"""Qualitative game knowledge for the bot's decisions, from Ed's September runs (Kayloe1/batomon).

Only rules that should survive balance patches are kept here: what card wording means,
what to avoid, what to treat as a decision, and the order of priorities that won runs.
Hard numbers (damage, prices, HP, odds, thresholds) are deliberately left out because
the game has been patched since September; read those from the screen or the data files.

Pure functions, no game input or screen reading. Slot numbering matches reader.py:
team slots 0-2 are the top row left to right, 3-5 the bottom row; the team faces right.
The full write-up with the evidence is docs/game-knowledge.md.
"""
from __future__ import annotations

TEAM_COLS, TEAM_ROWS = 3, 2


# ---------------------------------------------------------------- positions
def _rc(slot: int) -> tuple[int, int]:
    if not 0 <= slot < TEAM_COLS * TEAM_ROWS:
        raise ValueError(f"team slot {slot} out of range")
    return slot // TEAM_COLS, slot % TEAM_COLS


def _slot(row: int, col: int) -> int | None:
    if 0 <= row < TEAM_ROWS and 0 <= col < TEAM_COLS:
        return row * TEAM_COLS + col
    return None


def position_targets(slot: int, word: str) -> list[int]:
    """Team slots that a card's positional word points at, seen from `slot`.

    "behind" is the ally directly to the LEFT (same row), "in front" the ally directly to the
    RIGHT, "above"/"below" the other row in the same column, "adjacent" is left, right, above
    and below only (diagonals never count). "opposite" means the mirrored ENEMY slot, so it is
    returned as that slot number on the enemy's side. An early guess that "behind" meant "above"
    cost two battles in September.
    """
    row, col = _rc(slot)
    word = word.lower().strip().replace("-", " ")
    if word == "behind":
        cands = [_slot(row, col - 1)]
    elif word == "in front":
        cands = [_slot(row, col + 1)]
    elif word == "above":
        cands = [_slot(row - 1, col)]
    elif word == "below":
        cands = [_slot(row + 1, col)]
    elif word == "adjacent":
        cands = [_slot(row, col - 1), _slot(row, col + 1), _slot(row - 1, col), _slot(row + 1, col)]
    elif word == "opposite":
        cands = [slot]
    else:
        raise ValueError(f"unknown position word {word!r}")
    return [s for s in cands if s is not None]


def helper_slot_for(carry_slot: int, word: str) -> int | None:
    """Where a helper must stand so that its `word` points at the carry.

    A "behind" helper (Boomagon, Dracana, Onsetra, Blixie) goes to the carry's RIGHT, an
    "in front" helper (Saberhorn, Zephyrex) to its LEFT, an "above" helper (Cicadence, Dryadell,
    Magmalith, Noxalith) directly BELOW it, so the carry must be in the top row.
    """
    row, col = _rc(carry_slot)
    return {"behind": _slot(row, col + 1), "in front": _slot(row, col - 1),
            "above": _slot(row + 1, col), "below": _slot(row - 1, col)}.get(word.lower().strip())


def neighbour_count(slot: int) -> int:
    """Orthogonal neighbours of a slot. The top-middle slot has three (left, right, below),
    which is why every winning September layout put the carry there."""
    return len(position_targets(slot, "adjacent"))


BEST_CARRY_SLOT = 1  # top middle
# Adjacent buffers (Formiqueen, Gaiadrasil, Aster) go where they touch the MOST qualifying allies,
# not just the carry. Link Cable makes every team slot adjacent.


# ---------------------------------------------------------------- what to avoid
NEVER_FIELD = {
    "Dirgefin": "knocks out ALL Common monsters on both sides, including a Common carry",
}

SELF_KNOCKOUT = {"Stingarde", "Pyronade", "Electranade"}
"""One big hit, then they knock themselves out. Good cheap damage in the first days, dead slots
once fights get long. A SHINY copy can lose the drawback (Shiny Stingarde did): inspect it."""

NEEDS_SUPPORT = {
    "Talonite": "only scales with Rock and Flying allies",
    "Clawnetic": "its level-ups only raise Shock charge; useless without a Shock source",
}

AVOID_TRAINERS = {
    "Mad Scientist": "turns the active team into random level 1 Legendaries mid-run, wiping your investment",
    "Gentleman": "stops Common and Uncommon monsters appearing after the first days (kills Common copy sets)",
}

TRAINER_PREFERENCE = ["Monster Ranger", "Swim Coach", "Bug Catcher", "Youngster", "Egg Breeder"]
"""Trainers that won or helped in September, best first (judgment from few runs). Monster Ranger
and Swim Coach each won twice, Bug Catcher once (its free Bug each day also covers Cicadence,
Formiqueen and Guardiant). Youngster's free rerolls feed a Bug fodder loop. Burglar is strong late but
gives no early power; Rich Lady's higher shop rank thins out Commons; Twins only triggers on real
level 3 merges, not event level-ups; Masked Man is idle at first and its picks are random."""


# ---------------------------------------------------------------- items
ITEM_AUTO_OK = {"Cake", "Coupon", "Fake Coin", "Feast", "Gray Chip", "Nana Berry", "Pom Berry", "Focus Pill"}
"""Free or near-free items with no downside. Use Coupon before buying monsters. Buying any item
still uses up the day's item use and its shop slot refills, often with a paid card."""

ITEM_DECISIONS = {
    # Basic Bait is missing from the November Batopedia capture (data/items.csv); check it still exists.
    "Basic Bait": "lowers the shop rank for the REST of the run: take it early while you still need "
                  "Commons; skip it once you are hunting Rare amplifiers; fine again late once every "
                  "amplifier you want is on the board",
    "Red Coin": "money for a life: only when that life cannot change where the next loss leaves you",
    "Green Stone": "turns a random Common into an Uncommon: could hit a Common carry",
    "Voucher": "a random shop monster for free; only when every remaining card is useful (it does sell for money)",
    "Upgrade Disc": "levels the VERY NEXT monster bought, even a free or fodder one, and the copy will not "
                    "merge: buy the monster you want levelled next, and pause any fodder loop meanwhile",
    "Tote Bag": "extra item uses for today only",
    "Magic Lasso": "the promised copy of the enemy's top-middle monster never appeared when tried",
}
TICKETS = {"Gray Ticket": "Common", "Green Ticket": "Uncommon", "Blue Ticket": "Rare",
           "Purple Ticket": "Super Rare", "Golden Ticket": "Legendary", "Crimson Ticket": "Mythical"}
"""A ticket REPLACES the whole shop with one rarity. Buy what you want from the current shop
first. A Gray Ticket is a good Bug-fodder shop; a Blue Ticket is the best way to find Rare
amplifiers (Cicadence, Formiqueen) when rerolls fail."""

TRINKET_WARNINGS = {
    "Fool's Gold": "removes items from the shop, which cancels item scalers (Craghorn, Power Pouch, Berroon)",
    "Piggy Bank": "rewards holding money, which fights spending down",
    "Blue Incense": "several all-Rare shops: good for amplifiers, but no cheap Bugs for the fodder loop",
    "Purple Incense": "several all-Super-Rare shops: no cheap fodder meanwhile",
    "Gold Incense": "several all-Legendary shops: no cheap fodder meanwhile",
}


def item_policy(name: str) -> str:
    """'auto' (just use it) or 'decide' (the planner chooses). Tickets, the items in
    ITEM_DECISIONS and any item not listed here are never used automatically."""
    return "auto" if name in ITEM_AUTO_OK else "decide"


def is_egg(name: str | None) -> bool:
    """An egg does nothing in a team slot and hatches just as well on the bench:
    always move it to the bench the moment it arrives (a September run lost a day with one fielded)."""
    return bool(name) and "egg" in name.lower()


# ---------------------------------------------------------------- events
EVENT_PICKS = [
    # (words in the event text, the option to prefer, why)
    ("bug collector", "level 2 Guardiant", "counts toward Guardiant's next merge"),
    ("rainbow berry", "make a monster shiny", "put it on the carry"),
    ("professor", "level up a monster", "level the carry; beats the cash option"),
    ("fairy", "Gold Bar", "income; avoid the shop-rank-up option if the plan needs Commons"),
    ("inventor", "Gold-o-matic", "income; NEVER Recombobulator, it wipes permanent growth"),
    ("dragon tamer", "Shiny Saberhorn", "best single-carry amplifier"),
    ("dragon's hoard", "Dragon Egg", "hatches a random Legendary Dragon later; keep the egg on the bench"),
    ("merchant", "the exotic monster", "random foreign Rare (Kickrane, Dollhime, Shikitsune seen): inspect it"),
    ("basilisk", "trinket gift", ""),
    ("meteor", "level up a level 1 monster", "only if it is a carry piece, else the cash"),
    ("mysterious trainer", "a life and a trinket", "rescue at 0 lives; the random monster never fit the team"),
]
NEVER_PICK = {"Recombobulator": "randomly transforms your monsters and destroys permanent growth"}


# ---------------------------------------------------------------- priorities
PLANNER_RULES = [
    "The first days decide the run: losses cost more lives as days go on, and every September run that lost "
    "several early fights ran out of lives before its engine paid off. Early on, buy damage that fights TODAY.",
    "After a clear early loss, spend the next shop on damage that fights today and on merges that complete "
    "today, not on growth for later.",
    "Fill every team slot as soon as money allows.",
    "Amplifiers beat levels: a carry with a trigger/speed/multicast helper around it cast far more often than "
    "a higher-level carry alone. Once the carry exists, a helper outranks another carry copy.",
    "Strongest helpers found: 'trigger the ally above' pieces directly below a same-typed carry (Cicadence for "
    "Bugs, Dryadell for Grass), Multicast granters in front of it (Saberhorn per battle, Zephyrex permanent), "
    "cooldown speed (Formiqueen for adjacent Commons, Boomagon/Dracana for the ally behind).",
    "Put the carry top middle (three neighbours) and surround it; re-check the layout after every merge, "
    "because merged monsters can land in a different slot and leave a slot empty.",
    "A shop card with a level tag completes a merge: buy it (every merge also gives a trinket gift of the "
    "monster's rarity). Level-ups from events, discs or candy give no gift.",
    "A level-up raises the numbers in the ability, not the monster's current damage: check what the level "
    "actually improves before paying for copies.",
    "Finish Common copy sets early; as shop rank rises Commons get rare, so stop rerolling for a Common copy "
    "and spend on the Rare/Super Rare cards the shop now offers.",
    "Spend down before every battle: money carries over but earns nothing. Lock the shop instead when a wanted "
    "card is too expensive today. Reroll only if the money left still buys the card you want.",
    "Sell bench monsters that are not merge copies or planned replacements; the money buys power now.",
    "Never sell a monster with large permanent growth: growth cannot be bought back.",
    "Every slot must pull weight: replace slots that deal almost nothing and buff nobody.",
    "Enemies can't be scouted. Two loss modes: heal/shield teams (common in the late game) and burst teams. "
    "Pantra has no anti-heal; both are beaten by more damage per second, not by defence. At most one hedge slot.",
    "Back-loaded helpers (Saberhorn first casts late and slows itself each cast) are weak in short fights.",
    "Engines that won besides a Bug-fodder carry: a multi-hit carry (Velocect) with Cicadence below and Zephyrex "
    "in front; Stellagon next to monsters with no abilities; Craghorn fed by free items; Dollhime growing per "
    "trinket. A Burn engine (Lignite with Magmalith) beat heal teams but lost to burst.",
]
