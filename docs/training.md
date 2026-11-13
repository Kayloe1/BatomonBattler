# Practice shop and learning (`train/`)

The decision engine picks every action by playing hundreds of simulated battles, which takes
5 to 20 seconds per decision and minutes per whole run. That is too slow to learn from. `train/`
adds a fast whole-run practice environment and a learner.

```
python -m train.learn --sim --gens 18 --pop 24 --runs 16     # ~40 min on 4 cores; writes train/best_policy.json
python -m train.learn --gens 40 --pop 48 --runs 40           # no simulator feature, 6 min (weak, see below)
python -m train.validate --runs 120                           # held-out opponents, changed rules, sample teams
python play.py --new-run --learned                            # play a Casual run with the learned policy
python -m unittest tests.test_train
```

## Pieces
- `train/env.py` `play_run(policy, seed, opponents)`: a whole run (shop rolls by rank odds, income, rerolls,
  merges, trinket gifts, trainer HP, lives, the one rescue, 10 badges), built on `engine/model.py`,
  `engine/growth.py` and the battle simulator (about 1 ms per battle). Opponents are snapshots, as in the real game,
  from three sources: ghost teams (`engine/opponents.py`), a self-play league (teams earlier generations of the
  learner built on that day) and **real recorded teams** (`data/opponents_recorded.jsonl`), which get
  30% of fights on any day that has some. None are recorded yet, so training is not anchored to real players yet.
- `train/policy.py` `FastPolicy(Theta)`: buys the card with the highest value if it clears a day-dependent threshold,
  sells the weakest monster to make room only for a clearly better one, rerolls within a cap and a money reserve,
  lays out the team with the positional rules. 19 numbers; `w_sim` weights the simulator's estimate of how much a
  card raises the chance to win today and tomorrow.
- `train/learn.py`: cross-entropy method over those numbers, scored by mean badges over whole runs with identical
  shops for every candidate.
- `train/validate.py`: scores on a ghost pool the learner never saw, repeats under changed unverified battle
  rules, and prints sample teams.

## Results (2026-11-12, offline, 120 runs on held-out ghost opponents)
| Policy | Mean badges | Battles won | Runs won |
|---|---|---|---|
| Old simple rules | 1.3 | 18% | 0% |
| Learned, no simulator feature (6 min of training) | 1.5 | 19% | 0% |
| Learned with simulator feature (`train/best_policy.json`) | 3.9 | 40% | 3% |
| **Engine (12 runs, same opponents, `engine.runsim`)** | **6.6** | **55%** | **25%** |

Under changed Burn speed, shield penalty and Shock mode the learned policy keeps 3.5 to 4.1 badges.

## What this shows and does not show
- **The learned policy is not better than the engine.** It is about 2.7 badges behind (12 engine runs is a small sample,
  but the gap is large). It is 100 times faster, so it is useful for learning and as a fast fallback, not as the player.
  `play.py` still uses the engine by default; `--learned` is opt-in.
- Pure learning of card values (no simulator in the loop) did not help: the first run's good-looking training
  scores were the best of 48 candidates on 40 runs, which does not hold on a fresh pool. Always judge on `train.validate`.
- The gain comes from giving the policy the simulator's view of a card. Practice then tunes how much to trust it,
  how long to keep rerolling, and when to sell.
- Everything is only as good as the simulator and the opponents. Ghost and league opponents are guesses. The learner
  will exploit any flaw in them; the real check is Casual runs. After real opponent teams are logged, rerun
  `train.learn` (they join automatically) and compare again.
