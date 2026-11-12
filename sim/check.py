"""Check the simulator against the recorded battles in sim/cases/*.json.

Each case gives both teams and an "expect" block. Values that the simulator does not yet
reproduce are listed under "known_gaps" with the reason; they are reported as GAP, not FAIL.
"""
from __future__ import annotations

import json
from pathlib import Path

from .battle import simulate

CASES = Path(__file__).resolve().parent / "cases"


def load_cases() -> list[tuple[str, dict]]:
    return [(p.stem, json.loads(p.read_text(encoding="utf-8"))) for p in sorted(CASES.glob("*.json"))]


def _unit_by_slot(units: list[dict], slot: str) -> dict:
    for u in units:
        if str(u["slot"]) == str(slot):
            return u
    return {}


def _compare_units(prefix: str, want: dict, units: list[dict], out: list) -> None:
    for slot, fields in want.items():
        got_u = _unit_by_slot(units, slot)
        for k, v in fields.items():
            if k == "stats":
                for sk, sv in v.items():
                    got = got_u.get("stats", {}).get(sk, 0)
                    out.append((f"{prefix} slot {slot} {sk} badge", sv, got, round(got) == sv))
            else:
                got = got_u.get(k, 0)
                out.append((f"{prefix} slot {slot} {k}", v, got, round(got) == v))


def check_case(case: dict) -> list[tuple[str, object, object, bool]]:
    """Return (name, expected, got, ok) rows."""
    exp = case["expect"]
    rows: list[tuple[str, object, object, bool]] = []
    r = simulate(case["a"], case["b"])
    if "winner" in exp:
        rows.append(("winner", exp["winner"], r.winner, r.winner == exp["winner"]))
    if "time_between" in exp:
        lo, hi = exp["time_between"]
        rows.append(("time_between", f"{lo}-{hi} s", round(r.time, 2), lo - 1e-9 <= r.time < hi))
    _compare_units("a", exp.get("a_units", {}), r.units[0], rows)
    _compare_units("b", exp.get("b_units", {}), r.units[1], rows)
    snap = exp.get("snapshot")
    if snap:
        s = simulate(case["a"], case["b"], until=snap["at"], immortal=True)
        at = f"snapshot.{snap['at']}s"
        if "b_damage_taken" in snap:
            got = s.max_hp[1] - s.hp[1]
            rows.append((f"{at} b_damage_taken", snap["b_damage_taken"], round(got),
                         round(got) == snap["b_damage_taken"]))
        if "a_damage_taken_at_least" in snap:
            got = s.max_hp[0] - s.hp[0]
            rows.append((f"snapshot.a_damage_taken_at_least", snap["a_damage_taken_at_least"],
                         round(got), got >= snap["a_damage_taken_at_least"]))
        for side, key in ((0, "a_status"), (1, "b_status")):
            for k, v in snap.get(key, {}).items():
                got = s.statuses[side].get(k, 0)
                rows.append((f"{at} {key} {k}", v, got, got == v))
        _compare_units(f"{at} a", snap.get("a_units", {}), s.units[0], rows)
        _compare_units(f"{at} b", snap.get("b_units", {}), s.units[1], rows)
    return rows


def report() -> tuple[int, int, int]:
    """Print every check. Returns (passed, failed, known gaps that still fail)."""
    passed = failed = gaps = 0
    for name, case in load_cases():
        print(f"== {name}: {case.get('title', '')}")
        known = case["expect"].get("known_gaps", {})
        for label, want, got, ok in check_case(case):
            gap = any(label == k or label.startswith(k + " ") or label.endswith(k) for k in known)
            if ok:
                passed += 1
                tag = "ok  " if not gap else "ok (was a known gap; remove it from known_gaps)"
            elif gap:
                gaps += 1
                tag = "GAP "
            else:
                failed += 1
                tag = "FAIL"
            print(f"  {tag} {label}: expected {want}, got {got}")
        for k, why in known.items():
            print(f"  note on {k}: {why}")
    print(f"\n{passed} passed, {failed} failed, {gaps} known gaps")
    return passed, failed, gaps
