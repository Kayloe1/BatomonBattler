"""Summarise the bot's run logs: results per run, what the shop offered, income, unseen Batomon.

    python report.py                  # every logs\\run_*.jsonl
    python report.py logs\\run_x.jsonl runs\\...   # chosen files
    python report.py --json out.json  # also save the numbers

Reads only the logs written by play.py ("shop", "battle", "battle_stats", "day_result",
"trainer", "run_over" records). Nothing is sent to the game.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RARITIES = ["Common", "Uncommon", "Rare", "Super Rare", "Legendary"]


def load(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass                      # a half-written last line after a crash
    return out


def summarize_run(records: list[dict]) -> dict | None:
    """One run's story from its log. None when the log holds no battle (nothing to tell)."""
    shops = [r["state"] for r in records if r.get("kind") == "shop" and r.get("state")]
    battles = [r for r in records if r.get("kind") == "battle"]
    if not battles:
        return None
    trainer = None
    for r in records:
        if r.get("kind") == "trainer" and r.get("ok"):
            offered, k = r.get("offered") or [], r.get("picked")
            if isinstance(k, int) and k < len(offered):
                trainer = offered[k]
    trainer = trainer or (shops[0].get("trainer") if shops else None)
    days = []
    for r in records:
        if r.get("kind") == "day_result":
            days.append({"day": r["day"], "badges": r["badges"], "lives": r["lives"]})
    ended = any(r.get("kind") == "run_over" for r in records)
    stopped = [r.get("why") for r in records if r.get("kind") == "stop"]
    last = shops[-1] if shops else {}
    badges, lives = last.get("badges"), last.get("lives")
    final = None
    if ended and battles:
        # the last battle has no shop after it: its result comes from the end HP, else a loss
        stats = [r for r in records if r.get("kind") == "battle_stats"]
        hp = (stats[-1].get("end_hp_fraction") or {}) if stats else {}
        won = bool(hp) and hp.get("me", 0) > 0 and hp.get("opponent", 1) == 0
        final = "win" if won else "loss"
        if won and badges is not None:
            badges += 1
    return {
        "trainer": trainer, "battles": len(battles), "badges": badges, "lives_left": lives,
        "last_day": last.get("day"), "ended": ended, "final_battle": final,
        "stopped": stopped[-1] if stopped else None, "days": days,
        "lost_lives_on": [(d["day"], -d["lives"]) for d in days if d["lives"] < 0],
    }


def names_seen(records: list[dict]) -> dict[str, Counter]:
    """Where each Batomon name was seen: shop offers, my team/bench, or an opponent's team."""
    seen = {"shop": Counter(), "mine": Counter(), "opponent": Counter()}
    for r in records:
        st = r.get("state")
        if r.get("kind") == "shop" and st:
            for c in st.get("shop", []):
                if c and c.get("kind") == "monster" and c.get("name"):
                    seen["shop"][c["name"]] += 1
            for s in st.get("team", []) + st.get("bench", []):
                if s and s.get("name"):
                    seen["mine"][s["name"]] += 1
        if r.get("kind") == "battle":
            sn = r.get("seen") or {}
            for s in sn.get("opponent_team", []) or []:
                if s and s.get("name"):
                    seen["opponent"][s["name"]] += 1
    return seen


def unnamed_opponents(records: list[dict]) -> int:
    n = 0
    for r in records:
        if r.get("kind") == "battle":
            n += sum(1 for s in (r.get("seen") or {}).get("opponent_team", []) or [] if s and not s.get("name"))
    return n


def shop_offers(records: list[dict]) -> dict[int, dict]:
    """Per shop rank: printed odds and the rarities of the monster cards actually offered.

    A shop is counted once per distinct set of cards (the log has one record per action).
    """
    out: dict[int, dict] = {}
    done = set()
    for r in records:
        st = r.get("state")
        if r.get("kind") != "shop" or not st or st.get("shop_rank") is None:
            continue
        cards = [c for c in st.get("shop", []) if c and c.get("kind") == "monster"]
        key = (st.get("day"), tuple(c["name"] for c in cards))
        if key in done:
            continue
        done.add(key)
        e = out.setdefault(st["shop_rank"], {"odds": st.get("shop_odds"), "cards": Counter()})
        for c in cards:
            e["cards"][c.get("rarity")] += 1
    return out


def income(records: list[dict]) -> list[dict]:
    """Money before BATTLE! on day D and at the first shop of day D+1; the difference is the income."""
    rows, last = [], None
    first_of_day: dict[int, dict] = {}
    pending: dict | None = None
    for r in records:
        st = r.get("state")
        if r.get("kind") == "shop" and st and st.get("money") is not None and st.get("day") is not None:
            if pending and st["day"] == pending["day"] + 1 and st["day"] not in first_of_day:
                rows.append({"day": pending["day"], "left_over": pending["money"], "next_day_start": st["money"],
                             "income": st["money"] - pending["money"], "rank": st.get("shop_rank")})
            first_of_day.setdefault(st["day"], st)
            pending = st
    return rows


def events_seen(records: list[dict]) -> dict:
    """Every event met: its choices, how often each was picked, what followed, and what is still unknown."""
    try:
        import reader
        known = set(reader.KNOWN_EVENT_EFFECTS)
    except Exception:
        known = set()
    events: dict[tuple, dict] = {}
    unread, new_lines, guessed = Counter(), Counter(), Counter()
    for r in records:
        if r.get("kind") == "event":
            effects = r.get("effects") or []
            key = tuple(e or "(unreadable)" for e in effects)
            e = events.setdefault(key, {"choices": list(key), "seen": 0, "picked": Counter(), "outcomes": []})
            e["seen"] += 1
            k = r.get("choice")
            if isinstance(k, int) and k < len(key):
                e["picked"][key[k]] += 1
            for eff, raw in zip(effects, r.get("raw") or [None] * len(effects)):
                if eff is None:
                    unread[raw or "?"] += 1
                elif known and eff not in known:
                    new_lines[eff] += 1
            for line in r.get("why") or []:
                if "[guess]" in line:
                    guessed[line.strip().split("  ", 1)[-1].split(":")[0]] += 1
        elif r.get("kind") == "event_outcome":
            key = tuple(e or "(unreadable)" for e in (r.get("effects") or []))
            if key in events:
                events[key]["outcomes"].append({k: r.get(k) for k in (
                    "picked", "day", "money_before", "money_after", "lives_before", "lives_after",
                    "monsters_new_or_changed", "monsters_gone_or_changed")})
    return {"events": [{**e, "picked": dict(e["picked"])} for e in events.values()],
            "unreadable_lines": dict(unread), "new_effect_lines": dict(new_lines),
            "scored_by_guess": dict(guessed)}


def report(paths: list[Path]) -> dict:
    runs, allrecs = [], []
    for p in paths:
        recs = load(p)
        s = summarize_run(recs)
        if s:
            s["log"] = p.name
            runs.append(s)
            allrecs += recs
    from collections import Counter as C
    seen = names_seen(allrecs)
    try:
        sys.path.insert(0, str(ROOT))
        from engine.data import roster
        everyone = sorted(roster())
    except Exception:
        everyone = []
    anywhere = set().union(*(set(c) for c in seen.values()))
    return {"runs": runs, "never_seen": [n for n in everyone if n not in anywhere],
            "seen_counts": {k: dict(v) for k, v in seen.items()},
            "unnamed_opponent_monsters": unnamed_opponents(allrecs),
            "shop_offers": {k: {"odds": v["odds"], "cards": dict(v["cards"])} for k, v in shop_offers(allrecs).items()},
            "income": income(allrecs), "events": events_seen(allrecs)}


def show(rep: dict) -> None:
    runs = rep["runs"]
    print(f"{len(runs)} run(s)\n")
    for r in runs:
        status = ("finished" if r["ended"] else f"stopped: {r['stopped']}" if r["stopped"] else "unfinished")
        lost = ", ".join(f"day {d}: -{n}" for d, n in r["lost_lives_on"]) or "none"
        print(f"- {r['log']}: {r['trainer']}, {r['badges']} badge(s), {r['battles']} battles, "
              f"last day {r['last_day']}, {status}; lives lost: {lost}")
    badges = [r["badges"] for r in runs if r["badges"] is not None and r["ended"]]
    if badges:
        print(f"\nFinished runs: mean {sum(badges) / len(badges):.1f} badges "
              f"({sum(b >= 10 for b in badges)} of {len(badges)} won)")
    print(f"\nBatomon never seen yet ({len(rep['never_seen'])}): {', '.join(rep['never_seen']) or '-'}")
    if rep["unnamed_opponent_monsters"]:
        print(f"Opponent monsters on the battle screen that could not be named: {rep['unnamed_opponent_monsters']}")
    print("\nShop: printed odds vs rarities offered (monster cards only, each shop counted once)")
    for rank, e in sorted(rep["shop_offers"].items()):
        total = sum(e["cards"].values()) or 1
        obs = " / ".join(f"{100 * e['cards'].get(r, 0) / total:.0f}" for r in RARITIES)
        odds = " / ".join(str((e["odds"] or {}).get(r, "?")) for r in RARITIES)
        print(f"  rank {rank}: printed {odds} | offered {obs} (n={total})")
    ev = rep.get("events") or {}
    if ev.get("events"):
        print(f"\nEvents met ({len(ev['events'])} different):")
        for e in ev["events"]:
            print(f"  seen {e['seen']}x: " + " | ".join(e["choices"]))
            for name, n in e["picked"].items():
                print(f"      picked {n}x: {name}")
            for o in e["outcomes"][-2:]:
                print(f"      after '{o['picked']}': money {o['money_before']} -> {o['money_after']}, "
                      f"lives {o['lives_before']} -> {o['lives_after']}, new/changed: "
                      f"{', '.join(o['monsters_new_or_changed']) or 'nothing'}")
        if ev["scored_by_guess"]:
            print("  Effects still scored by a guess (need a real description): " + "; ".join(ev["scored_by_guess"]))
        if ev["new_effect_lines"]:
            print("  New effect lines not in the known list yet: " + "; ".join(ev["new_effect_lines"]))
        if ev["unreadable_lines"]:
            print("  Lines the reader could not read (raw): " + "; ".join(ev["unreadable_lines"]))
    if rep["income"]:
        print("\nMoney: left over after shopping day D -> start of day D+1")
        by_day = defaultdict(list)
        for i in rep["income"]:
            by_day[i["day"]].append(i["income"])
        for d, v in sorted(by_day.items()):
            print(f"  day {d} -> {d + 1}: income {min(v)} to {max(v)} (n={len(v)})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("logs", nargs="*", type=Path)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)
    paths = args.logs or sorted((ROOT / "logs").glob("run_*.jsonl"))
    if not paths:
        print("no logs found")
        return 1
    rep = report(paths)
    show(rep)
    if args.json:
        args.json.write_text(json.dumps(rep, indent=1, default=list), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
