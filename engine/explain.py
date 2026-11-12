"""Turn a Plan into plain English, so Ed can follow what the bot is thinking.

The numbers: every option gets a "gain", which is how much better the run looks after that
action than if the turn ended right now. It mixes the chance to win today's battle, the next
two days' battles, money kept and progress toward level-ups. Bigger is better; an option at
or below +0.00 is not worth doing.
"""
from __future__ import annotations

SLOT_NAMES = ["top left", "top middle", "top right", "bottom left", "bottom middle", "bottom right"]


def _where(pos) -> str:
    if not pos:
        return "?"
    kind, i = pos
    return f"team {SLOT_NAMES[i]}" if kind == "team" and i < 6 else f"bench slot {i + 1}"


def _name(state: dict, pos) -> str:
    try:
        slot = state[pos[0]][pos[1]]
        return (slot or {}).get("name") or "a monster"
    except Exception:
        return "a monster"


def _strength(gain: float) -> str:
    if gain >= 0.5:
        return "a big improvement"
    if gain >= 0.15:
        return "a clear improvement"
    if gain > 0.02:
        return "a small improvement"
    return "about the same as doing nothing"


def explain(plan, state: dict) -> list[str]:
    """Lines to print for one decision on the shop screen."""
    lines = [f"--- Day {state.get('day')} | ${state.get('money')} | {state.get('lives')} lives | "
             f"{state.get('badges')} badges ---"]
    if plan.win_now is not None:
        lines.append(f"Chance to win today's battle with the team as it is: {plan.win_now:.0%}.")
    ranked = sorted(plan.considered, key=lambda x: -x[1])
    first = plan.actions[0] if plan.actions else None
    chosen = first.why if first is not None and first.kind not in ("lock", "move", "battle") else None
    if ranked:
        lines.append("Options I weighed (gain compared with ending the turn now):")
        for label, gain in ranked[:5]:
            mark = "   <-- my choice" if chosen and label == chosen else ""
            lines.append(f"   {gain:+.2f}  {label}{mark}")
        if len(ranked) > 5:
            lines.append(f"   ... and {len(ranked) - 5} weaker options")
    if chosen:
        gain = next((g for label, g in ranked if label == chosen), None)
        if gain is not None:
            second = next(((label, g) for label, g in ranked if label != chosen), None)
            text = f"Decision: {chosen}. It is {_strength(gain)} ({gain:+.2f})"
            if second and second[1] > 0:
                text += f", ahead of '{second[0]}' ({second[1]:+.2f})"
            lines.append(text + ".")
        else:
            lines.append(f"Decision: {chosen}. It is free and can only help, so I use it before the battle.")
        if chosen == "reroll":
            lines.append("Why reroll: on average a fresh shop is worth more to this team than anything on offer now.")
        elif chosen.startswith("sell") and " to buy " in chosen:
            lines.append("Why sell first: I cannot afford or fit the new monster otherwise, and the team is stronger with it.")
        elif chosen.startswith("sell"):
            lines.append("Why sell: its money is worth more than what it adds to the team.")
        elif chosen.startswith("feed"):
            lines.append("Why: buying a Bug makes Guardiant grow; the Bug itself is then sold back.")
        return lines
    # end of the turn
    best = ranked[0] if ranked else None
    if best and best[1] > 0:
        lines.append(f"Nothing beats ending the turn by enough (best was '{best[0]}' at {best[1]:+.2f}).")
    else:
        lines.append("Nothing left in the shop makes the team better, so the turn ends here.")
    for a in plan.actions:
        if a.kind == "lock":
            lines.append(f"Lock the shop: {a.why}. I cannot pay for it today, but can tomorrow.")
        elif a.kind == "move":
            lines.append(f"Move {_name(state, a.src)} from {_where(a.src)} to {_where(a.dst)}: "
                         f"this layout won the most simulated battles.")
        elif a.kind == "battle":
            lines.append(f"Battle: {a.why}.")
    return lines
