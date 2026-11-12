# Collecting real Casual run data

What the bot records now, for the simulator and the practice shop:

| What | Where |
|---|---|
| Every shop screen: offered cards, prices, rank and odds, reroll price, money, team, bench | `logs\run_*.jsonl`, `kind: "shop"` (one record after every action, so every reroll is there) |
| Both teams at battle start (names from sprites, levels, badges) | `kind: "battle"`, field `seen`; captures in `captures\battles\` |
| **Stats window**: per monster dealt / healed / inflicted / triggered, for both teams | `kind: "battle_stats"` (`my_team`, `opponent_team`, 6 slots each) |
| **End HP**: fraction of each trainer's HP left when the battle ended | `kind: "battle_stats"`, `end_hp_fraction` (`me`, `opponent`; times the trainer HP) |
| Win or loss, lives lost | `kind: "day_result"` |
| Why a run stopped | `kind: "stop"` and `logs\last_stop.txt` |

The Stats window is opened from the result box, scrolled to reach the opponent's second row, read
and closed again, before CONFIRM. Reading problems (for example a digit the reader has not seen)
never stop a run; they are listed in `problems` and the captures are kept in `captures\battles\`.
Digits 4 and 8 of the Stats font have not been seen yet, so a number containing one will be
`null` until `teach.py` has a capture of it (see "How to add what the reader does not know").

## Commands

    python batch.py --runs 5            # five Casual runs back to back, summary at the end
    python report.py                    # all logs: runs, lives lost per day, Batomon never seen,
                                        # printed shop odds vs what was offered, money per day
    python -m sim.from_logs -v          # simulator vs the real battles, now also vs the Stats numbers
    python -m sim.from_logs --save      # turn each battle into a test case in sim\cases\logged\

`batch.py` only ever starts Casual runs (`hands.start_casual_run()`). If it meets a screen it does
not know, it stops, prints a boxed message, beeps three times and writes `logs\last_stop.txt`.
