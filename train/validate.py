"""Check a learned policy where the learner cannot have cheated.

    python -m train.validate                       # train/best_policy.json
    python -m train.validate --runs 300 --policy simple

1. Held-out opponents: whole runs against a ghost pool with a seed the learner never saw.
2. Changed rules: the same runs with the unverified battle rules changed (Burn speed, status
   damage against shields, Shock mode), to see whether the gain depends on a guess.
3. Anchor to real life: the old simple rules should score near their real record (3 battles
   won of 14; 1.2 badges in the real November runs). If the simulator made them look strong,
   the numbers are not to be trusted.
4. Any real recorded opponent teams (data/opponents_recorded.jsonl) are reported and used.
5. Plays are printed so a person can see whether the teams look like sensible teams.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import statistics
import sys
from concurrent.futures import ProcessPoolExecutor

from engine import data, model, opponents
from engine.evaluate import Evaluator
from engine.runsim import simple_policy_turn
from sim import rules

from .env import OppSource, play_run
from .policy import FastPolicy, load_theta

HOLDOUT_SEED = 9001

VARIANTS = {
    "as built": {},
    "burn slower (1 tick/s)": {"burn_interval": 1.0},
    "no shield penalty on status": {"status_vs_shield": 1.0},
    "bigger shield penalty": {"status_vs_shield": 0.6},
    "shock percent": {"shock_mode": "percent"},
}


class SimplePolicy:
    def play_shop(self, s, rng):
        s = simple_policy_turn(s, rng)
        from engine.arrange import heuristic_layout
        team, rest = heuristic_layout([u for _, _, u in s.owned()])
        s.team, s.bench = list(team), (rest + [None] * 4)[:4]
        return s


def make_policy(name: str):
    if name == "simple":
        return SimplePolicy()
    th = load_theta() if name == "learned" else load_theta(Path(name))
    ev = Evaluator(opponents.pools(n=24, seed=2)) if th.w_sim else None
    return FastPolicy(th, evaluator=ev)


def _job(args):
    name, seeds, overrides, pool_seed = args
    saved = {k: rules.SETTINGS[k] for k in overrides}
    rules.SETTINGS.update(overrides)
    try:
        src = OppSource(ghosts=opponents.pools(n=48, seed=pool_seed), p_ghost=1, p_league=0, p_recorded=0)
        pol = make_policy(name)
        return [play_run(pol, s, src) for s in seeds]
    finally:
        rules.SETTINGS.update(saved)


def evaluate(name: str, runs: int, overrides: dict | None = None, pool_seed: int = HOLDOUT_SEED,
             first_seed: int = 500_000, workers: int = 4) -> dict:
    seeds = list(range(first_seed, first_seed + runs))
    chunks = [seeds[i::workers] for i in range(workers)]
    with ProcessPoolExecutor(workers) as ex:
        res = [r for part in ex.map(_job, [(name, c, overrides or {}, pool_seed) for c in chunks]) for r in part]
    n = len(res)
    battles = sum(len(r["arc"]) for r in res)
    return {"policy": name, "runs": n, "runs_won": round(sum(r["won"] for r in res) / n, 3),
            "mean_badges": round(statistics.fmean(r["badges"] for r in res), 2),
            "battles_won": round(sum(r["arc"].count("W") for r in res) / battles, 3),
            "mean_last_day": round(statistics.fmean(r["day"] for r in res), 1)}


def describe_run(name: str, seed: int) -> None:
    pol = make_policy(name)
    src = OppSource(ghosts=opponents.pools(n=48, seed=HOLDOUT_SEED), p_ghost=1, p_league=0, p_recorded=0)
    r = play_run(pol, seed, src, snapshots=True)
    print(f"  seed {seed}: {r['arc']}  ({r['badges']} badges)")
    for d in (3, 5, 7, 9):
        spec = r["snaps"].get(d)
        if spec:
            names = [f"{sl['name']}{sl['level']}" if sl else "-" for sl in spec["slots"]]
            print(f"    day {d}: {' '.join(names)}  trinkets {len(spec['trinkets'])}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default="learned", help="learned, simple, or a path to a policy json")
    ap.add_argument("--runs", type=int, default=200)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-variants", action="store_true")
    args = ap.parse_args()
    rec = opponents.load_recorded()
    print(f"real recorded opponent teams available: {sum(len(v) for v in rec.values())}")
    print("\n== held-out opponents (ghost pool seed never used in training) ==")
    for name in ("simple", args.policy):
        print(evaluate(name, args.runs, workers=args.workers))
    if not args.no_variants:
        print("\n== unverified battle rules changed ==")
        for label, ov in VARIANTS.items():
            if not ov:
                continue
            a = evaluate("simple", args.runs // 2, ov, workers=args.workers)
            b = evaluate(args.policy, args.runs // 2, ov, workers=args.workers)
            print(f"{label:30s} simple {a['mean_badges']:.2f} badges, {a['battles_won']:.0%} battles | "
                  f"{args.policy} {b['mean_badges']:.2f} badges, {b['battles_won']:.0%} battles, "
                  f"{b['runs_won']:.0%} runs won")
    print("\n== sample runs ==")
    for sd in (11, 12, 13):
        describe_run(args.policy, sd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
