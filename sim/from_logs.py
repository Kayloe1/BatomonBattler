"""Turn the bot's run logs into simulator test cases and check how often the simulator agrees.

    python -m sim.from_logs                     # every logs/run_*.jsonl
    python -m sim.from_logs logs/run_x.jsonl -v # one log, one line per battle
    python -m sim.from_logs --save              # also write each battle to sim/cases/logged/

play.py writes a "battle" record after each battle with both teams as read from the battle screen
("seen"), and a "day_result" record on the next shop screen (badges +1 = won, lives -1 = lost).
Trinkets come from the "trinket" picks earlier in the same run. The opponent's trinkets and trainer
are not visible, so the opponent gets none and the day's HP from sim.data.DAY_HP.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import data
from .battle import simulate

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
SAVE_DIR = Path(__file__).resolve().parent / "cases" / "logged"


def _slot(s: dict | None) -> dict | None:
    if not s:
        return None
    stats, mc = {}, None
    for b in s.get("stats", []):
        if b.get("stat") == "multicast":
            mc = b.get("value")
        elif b.get("stat") in data.STATS and b.get("value") is not None:
            stats[b["stat"]] = b["value"]
    name = s.get("name")
    # GUESS: an unnamed level-1 monster whose only badge is 1 damage is the Dragon Egg (an event
    # reward, never in the shop, so there is no card sprite to name it).
    if name is None and (s.get("level") or 1) == 1 and stats == {"damage": 1}:
        name = "Dragon Egg"
    out = {"name": name, "level": s.get("level") or 1, "stats": stats}
    if mc:
        out["multicast"] = mc
    return out


def _name_from_team(slots: list, team: list | None) -> None:
    """Name my unnamed battle slots from the shop team logged with the battle: the one team monster
    with the same level, stats and Multicast (the battle grid is laid out differently from the shop
    grid, so slots are matched by numbers, not position). Left unnamed when it is not unique."""
    known = [x for x in (_slot(t) for t in (team or [])) if x and x["name"]]
    for s in slots:
        if s and not s["name"]:
            same = {k["name"] for k in known if k["level"] == s["level"] and k["stats"] == s["stats"]
                    and k.get("multicast") == s.get("multicast")}
            if len(same) == 1:
                s["name"] = same.pop()


NAMES_CACHE = LOG_DIR / "stats_names_cache.json"
_names_cache: dict | None = None


def _stats_names(rec: dict) -> tuple[list, list]:
    """(my names, opponent names) from the Stats window pictures: logged by play.py since
    2026-11-13, otherwise read from the saved captures (cached in logs/stats_names_cache.json)."""
    if "opponent_names" in rec:
        return rec.get("my_names") or [None] * 6, rec.get("opponent_names") or [None] * 6
    caps = [c for c in (rec.get("captures") or []) if (ROOT / c).exists()]
    if not caps:
        return [None] * 6, [None] * 6
    global _names_cache
    if _names_cache is None:
        _names_cache = json.loads(NAMES_CACHE.read_text(encoding="utf-8")) if NAMES_CACHE.exists() else {}
    key = "|".join(caps)
    if key not in _names_cache:
        import numpy as np
        from PIL import Image
        sys.path.insert(0, str(ROOT))
        import reader
        import window
        canon = lambda c: np.asarray(window.canonical_picture(Image.open(ROOT / c)))
        st = reader.read_stats(canon(caps[0]), canon(caps[1]) if len(caps) > 1 else None)
        _names_cache[key] = [st["my_names"], st["opponent_names"]]
        NAMES_CACHE.write_text(json.dumps(_names_cache), encoding="utf-8")
    mine, theirs = _names_cache[key]
    return mine, theirs


def _name_from_stats(case: dict, names_a: list, names_b: list) -> None:
    """Fill unnamed battle slots from the Stats window, whose slots are numbered the same way
    (checked 2026-11-13: 304 slots named by both, all the same) and whose pictures are surer."""
    for side, names, label in (("a", names_a, "my"), ("b", names_b, "opponent")):
        for i, s in enumerate(case[side]["slots"]):
            if s and not s["name"] and i < len(names) and names[i]:
                s["name"] = names[i]
                msg = f"{label} slot {i + 1} not named"
                if msg in case["problems"]:
                    case["problems"].remove(msg)


def _fresh_badges(seen: dict) -> dict:
    """The logged battle with its stat badges read again from the saved start capture, when it is
    still there: the log keeps what the reader made of them on the day, and badge reading has
    been corrected since (2026-11-13: leading digits of four-digit numbers were dropped)."""
    cap = seen.get("start_capture")
    if not cap or not (ROOT / cap).exists():
        return seen
    try:
        import numpy as np
        from PIL import Image
        sys.path.insert(0, str(ROOT))
        import reader
        import window
        pic = np.asarray(window.canonical_picture(Image.open(ROOT / cap)))
        out = dict(seen)
        for side, key in ((0, "my_team"), (1, "opponent_team")):
            out[key] = [None if s is None else
                        {**s, "stats": reader.read_stat_badges(pic, reader.owned_badge_band(reader.battle_slot(side, i)))}
                        for i, s in enumerate(seen.get(key) or [])]
        return out
    except Exception:                    # no reader here (the simulator alone needs only Python)
        return seen


def _lives_lost(day) -> int:
    """Lives a loss costs on this day (the engine's table; 99 = unknown, so a loss stays possible)."""
    try:
        from engine import data as engine_data
        return engine_data.lives_lost(day)
    except Exception:
        return 99


def battles_from_log(path: Path) -> list[dict]:
    """One case per logged battle: {"a", "b", "day", "result", "problems", "source"}."""
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    trinkets: list[str] = []
    cases: list[dict] = []
    open_case: dict | None = None
    shop: dict = {}                      # the last shop state before the battle
    for rec in records:
        kind = rec.get("kind")
        if kind == "shop":
            shop = rec.get("state") or {}
        if kind == "new_run" or kind == "trainer":
            trinkets = []
        elif kind == "trinket" and rec.get("ok"):
            offered, k = rec.get("offered") or [], rec.get("picked")
            if isinstance(k, int) and k < len(offered) and offered[k]:
                trinkets.append(offered[k])
        elif kind == "battle":
            seen = _fresh_badges(rec.get("seen") or {})
            problems = list(seen.get("problems", []))
            mine = [_slot(s) for s in seen.get("my_team", [])] or [None] * 6
            theirs = [_slot(s) for s in seen.get("opponent_team", [])] or [None] * 6
            _name_from_team(mine, rec.get("team"))
            if not seen:
                problems.append("battle screen not read")
            for side, team in (("my", mine), ("opponent", theirs)):
                for i, s in enumerate(team):
                    if s and not s["name"]:
                        problems.append(f"{side} slot {i + 1} not named")
            day = rec.get("day")
            hp_them = data.DAY_HP.get(day)
            if hp_them is None:
                problems.append(f"no HP known for day {day}")
            open_case = {
                "source": f"{path.name} {rec.get('time')}",
                "day": day,
                "a": {"trainer": rec.get("trainer"), "hp": rec.get("trainer_hp") or data.DAY_HP.get(day),
                      "trinkets": list(trinkets), "slots": mine},
                "b": {"hp": hp_them, "trinkets": [], "slots": theirs},
                "result": None,
                "problems": problems,
                "captures": [seen.get("start_capture"), seen.get("result_capture")],
            }
            cases.append(open_case)
        elif kind == "battle_stats" and open_case is not None:
            _name_from_stats(open_case, *_stats_names(rec))
            open_case["stats"] = {"my_team": rec.get("my_team"), "opponent_team": rec.get("opponent_team"),
                                  "end_hp_fraction": rec.get("end_hp_fraction"),
                                  "problems": rec.get("problems", [])}
        elif kind == "day_result" and open_case is not None:
            if rec.get("badges", 0) > 0:
                open_case["result"] = "win"
            elif rec.get("lives", 0) < 0:
                open_case["result"] = "loss"
            else:
                open_case["result"] = "draw"     # GUESS: neither a badge nor a life changed hands
            open_case = None
        elif kind == "run_over" and open_case is not None and open_case["result"] is None:
            # A run ends on the last lost life or on the last badge won; the shop before the
            # battle says which was possible. When both were (one badge short on the last life),
            # the result stays unknown.
            badges, goal, lives = shop.get("badges"), shop.get("badges_goal"), shop.get("lives")
            could_win = None not in (badges, goal) and badges >= goal - 1
            could_lose = lives is None or lives <= _lives_lost(open_case["day"])
            if could_win != could_lose:
                open_case["result"] = "win" if could_win else "loss"
            open_case = None
    return cases


def units_from_stats(lines: list | None) -> dict:
    """Stats-window lines per slot (0-based list) -> the "a_units" format of sim/cases (1-based slots)."""
    out = {}
    for i, ln in enumerate(lines or []):
        if ln is None:
            continue
        u = {k: v for k, v in ln.items() if k != "inflicted" and v is not None}
        for status, n in (ln.get("inflicted") or {}).items():
            if n is not None:
                u[f"inflicted_{status.lower()}"] = n
        out[str(i + 1)] = u
    return out


def stats_error(case: dict, seeds: int = 5) -> dict | None:
    """How far the simulated per-monster numbers are from the Stats window (mean over seeds).

    Returns {"rows": n, "mean_abs_error": x, "worst": [(label, real, sim)]} or None without stats.
    """
    st = case.get("stats")
    if not st or case["problems"] or st.get("problems"):
        return None
    want = {"a": units_from_stats(st["my_team"]), "b": units_from_stats(st["opponent_team"])}
    sums: dict[tuple, float] = {}
    for seed in range(seeds):
        r = simulate(case["a"], case["b"], seed=seed)
        for side, idx in (("a", 0), ("b", 1)):
            for slot, fields in want[side].items():
                unit = next((u for u in r.units[idx] if str(u["slot"]) == slot), {})
                for k, v in fields.items():
                    sums[(side, slot, k, v)] = sums.get((side, slot, k, v), 0) + unit.get(k, 0)
    rows = [(f"{side} slot {slot} {k}", v, round(tot / seeds, 1)) for (side, slot, k, v), tot in sums.items()]
    if not rows:
        return None
    errs = sorted(rows, key=lambda r: -abs(r[1] - r[2]))
    return {"rows": len(rows), "mean_abs_error": round(sum(abs(r[1] - r[2]) for r in rows) / len(rows), 1),
            "worst": errs[:3]}


def check(cases: list[dict], seeds: int = 5) -> dict:
    """Simulate each usable case; a case agrees when the most common winner over the seeds matches."""
    word = {"a": "win", "b": "loss", "draw": "draw"}
    out = {"usable": 0, "agree": 0, "skipped": 0, "rows": []}
    for c in cases:
        if c["problems"] or c["result"] is None:
            out["skipped"] += 1
            out["rows"].append((c, None, "skipped: " + ("; ".join(c["problems"]) or "no result logged")))
            continue
        try:
            wins: dict[str, int] = {}
            for seed in range(seeds):
                r = simulate(c["a"], c["b"], seed=seed)
                wins[r.winner] = wins.get(r.winner, 0) + 1
        except Exception as e:  # an unknown name or a bad slot: report, do not stop
            out["skipped"] += 1
            out["rows"].append((c, None, f"skipped: {type(e).__name__}: {e}"))
            continue
        sim = word[max(wins, key=wins.get)]
        out["usable"] += 1
        out["agree"] += sim == c["result"]
        out["rows"].append((c, sim, "agree" if sim == c["result"] else "DISAGREE"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("logs", nargs="*", type=Path)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--save", action="store_true", help=f"write each usable battle to {SAVE_DIR}")
    args = ap.parse_args(argv)
    paths = args.logs or sorted(LOG_DIR.glob("run_*.jsonl"))
    if not paths:
        print(f"no logs in {LOG_DIR}")
        return 1
    cases = [c for p in paths for c in battles_from_log(p)]
    res = check(cases)
    for c, sim, verdict in res["rows"]:
        if args.verbose or verdict == "DISAGREE":
            print(f"{c['source']} day {c['day']}: game {c['result']}, sim {sim}: {verdict}")
    if args.save:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        for c, sim, _ in res["rows"]:
            if sim is not None:
                name = c["source"].replace(" ", "_").replace(":", "").replace(".jsonl", "")
                expect: dict = {"result": c["result"]}
                st = c.get("stats")
                if st:
                    expect["a_units"] = units_from_stats(st["my_team"])
                    expect["b_units"] = units_from_stats(st["opponent_team"])
                    expect["end_hp_fraction"] = st.get("end_hp_fraction")
                (SAVE_DIR / f"{name}.json").write_text(json.dumps(
                    {"source": c["source"], "a": c["a"], "b": c["b"], "expect": expect},
                    indent=1), encoding="utf-8")
    errs = [(c, stats_error(c)) for c, sim, _ in res["rows"] if sim is not None]
    errs = [(c, e) for c, e in errs if e]
    for c, e in errs:
        if args.verbose:
            worst = "; ".join(f"{lab}: game {real}, sim {got}" for lab, real, got in e["worst"])
            print(f"  day {c['day']} stats: mean error {e['mean_abs_error']} over {e['rows']} numbers; worst: {worst}")
    if errs:
        print(f"Stats window numbers compared on {len(errs)} battles: mean error "
              f"{sum(e['mean_abs_error'] for _, e in errs) / len(errs):.1f} per number")
    n = res["usable"]
    pct = f"{100 * res['agree'] / n:.0f}%" if n else "-"
    print(f"{len(cases)} battles logged, {n} usable, simulator agrees on {res['agree']} ({pct}), "
          f"{res['skipped']} skipped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
