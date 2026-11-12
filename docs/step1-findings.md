# Step 1 findings: Batomon Showdown (as of 2026-11-11)

## The game
- Developer and publisher: berrymint. Engine: Godot 4. Steam app 4557380, released 2026-09-15. Also on Android; an old HTML5 demo existed on itch.io (reported retired).
- Async PvP auto-battler. Modes: Ranked, Extended, Casual. Season 1 started at launch; patch 1.1.0 has shipped since.
- No official wiki or public data source was found. Community: Discord https://discord.gg/kyArnasVTU, Steam hub https://steamcommunity.com/app/4557380

## Rules gathered so far (from community guides, incomplete)
- Teams appear to be 6 Batomon (inferred from published comps).
- Runs are counted in Days and Wins; a full run tops out at 10 wins. Events occur around Days 3, 6 and 9.
- Shop uses dollars. Cheap Batomon cost about $10. There are rerolls, a "shop rank", and rarity tiers: Common, Uncommon, Rare, Super Rare, Legendary, Mythic.
- Copies merge to Level 2 and Level 3. An Evolve Stone item exists.
- You pick a trainer (e.g. Burglar, Painter, Twins, Scavenger, Chemist, Bug Catcher, Swim Coach, Musician, Treasure Hunter, Youngster). Trinkets are offered two at a time.
- Types seen: Fire, Poison/Toxic, Shock, and more.
- NOT found anywhere public: Batomon stats, ability text, exact shop costs, lives/loss limit, ladder point system.

## Reported strong comps (GamesFuze, Sep 2026, pre-patch)
- Cairnage + Opalion: Bonshell, Cairnage, Opalion, Saberhorn, Dracana, Rhizuka (59% 10-win rate, 80 runs)
- Fumungus + Cobrex: Cobrex, Fumungus, Puffloon, Aristobat, Spinarai, Thorntail (55%, 51 runs)
- Miasmaw + Drumire: Cinnabark, Drumire, Miasmaw, Vipair, Brimtoad, Onsetra (54%, 87 runs)
- Swoonet + Snapscald: Snapscald, Steamscuttle, Swoonet, Lumijel, Frillet, Kappow (49%, 235 runs)

## How the game is built on Ed's PC
- Folder: C:\Program Files (x86)\Steam\steamapps\common\Batomon Showdown
- Files: batomon_showdown.exe (84 MB), batomon_showdown.pck (155 MB, Godot pack format v4, engine 4.7), GodotSteam DLL, steam_api64.dll.
- The .pck is encrypted (file index and contents; about 4,800 files). Game data and scripts cannot be read without breaking the developer's encryption. We did not attempt that.

## Automation stance
- No published rule for or against bots was found (store page, guides, search). The game has only the generic Steam agreement. The encrypted pack suggests the developer wants to protect the game's internals and ladder. The Discord is the place to ask.

- Update 2026-11-11: Ed says the developer allows bots. Nothing public was found earlier, so this rests on Ed's word; note the source here if there is one (for example a Discord message).

## What this means for the bot
- Reading state from game files is off the table; the bot has to read the screen (screenshots + image/text recognition) and click.
- Rules and Batomon data must be collected from the game's own screens (in-game collection/tooltips) rather than from files.
- The simulator (step 3) will need battle rules inferred from observed battles, so it will be approximate at first.

## Sources
- https://store.steampowered.com/app/4557380
- https://berrymint.itch.io/batomon-showdown
- https://rogueliker.com/pokemon-inspired-autobattler-batoman-showdown-launches-season-1/
- https://gamesfuze.com/guides/batomon-showdown-season-1-best-new-trainers-team-comps/
- https://gameplay.tips/guides/batomon-showdown-ranked-gameplay-guide.html
