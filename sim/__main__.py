"""Command line:

    python -m sim TEAM_A.json TEAM_B.json [--seed N] [--log] [--json]
    python -m sim --case sim/cases/day2_rich_lady_win.json [--log]
    python -m sim --check      # compare with every recorded battle in sim/cases/
    python -m sim --rules      # list every rule and whether it is verified or guessed
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .battle import simulate
from .rules import NOT_SIMULATED, RULES, SETTINGS


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _print_result(r, as_json: bool) -> None:
    if as_json:
        print(json.dumps(r.as_dict(), indent=2))
        return
    names = {"a": "A (you) wins", "b": "B wins", "draw": "draw", "none": "nobody has won yet"}
    print(f"{names[r.winner]} at {r.time:.2f} s.  HP A {r.hp[0]:.0f}/{r.max_hp[0]:.0f}, "
          f"B {r.hp[1]:.0f}/{r.max_hp[1]:.0f}")
    for side, label in ((0, "A"), (1, "B")):
        st = ", ".join(f"{k} {v}" for k, v in r.statuses[side].items()) or "none"
        print(f"  {label} statuses at the end: {st}")
        for u in r.units[side]:
            extra = " ".join(f"{k}={v}" for k, v in u.items()
                             if k not in ("slot", "name", "level", "stats") and v)
            print(f"    slot {u['slot']} {u['name']} L{u['level']}: {extra}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m sim", description="Batomon battle simulator")
    ap.add_argument("teams", nargs="*", help="TEAM_A.json TEAM_B.json")
    ap.add_argument("--case", help="a case file with 'a' and 'b' teams")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--log", action="store_true", help="print every cast")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    ap.add_argument("--check", action="store_true", help="compare with the recorded battles")
    ap.add_argument("--rules", action="store_true", help="list the rules and their status")
    args = ap.parse_args(argv)

    if args.rules:
        for text, status, why in RULES:
            print(f"[{status}] {text}" + (f"\n          {why}" if why else ""))
        print("\nNot simulated:")
        for t in NOT_SIMULATED:
            print(f"  - {t}")
        print("\nSettings:", json.dumps(SETTINGS))
        return 0
    if args.check:
        from .check import report
        _, failed, _ = report()
        return 1 if failed else 0
    if args.case:
        c = _load(args.case)
        a, b = c["a"], c["b"]
    elif len(args.teams) == 2:
        a, b = _load(args.teams[0]), _load(args.teams[1])
    else:
        ap.print_help()
        return 2
    r = simulate(a, b, seed=args.seed, verbose=args.log)
    if args.log:
        print("\n".join(r.log))
    _print_result(r, args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
