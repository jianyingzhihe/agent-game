"""Prompt templates for Texas Hold'em — strict KEYWORD: value format."""

from typing import List

RESPONSE_FORMAT = """
RESPONSE FORMAT — Reply with exactly these lines:
REASON: <your reasoning — hand strength, pot odds, opponent reads>
ACTION: FOLD or CHECK or CALL or RAISE <amount>

Rules:
- FOLD: give up your hand
- CHECK: pass (only if no bet to match)
- CALL: match the current bet
- RAISE <amount>: increase the bet (must be >= current bet + min raise)
"""


def betting_prompt(
    player_name: str,
    hole_cards: List[str],
    community_cards: List[str],
    pot: int,
    current_bet: int,
    player_chips: int,
    to_call: int,
    min_raise: int,
    round_name: str,
    position: str,
    num_active: int,
    actions_this_round: List[str],
) -> str:
    comm_str = " ".join(community_cards) if community_cards else "(none yet)"

    lines = [
        f"## Texas Hold'em — {round_name}",
        f"Position: {position}",
        "",
        f"Your hand: {' '.join(hole_cards)}",
        f"Community: {comm_str}",
        "",
        f"Pot: {pot} chips",
        f"Current bet: {current_bet} chips",
        f"Your chips: {player_chips} chips",
        f"To call: {to_call} chips",
        f"Minimum raise: {min_raise} chips",
        f"Active players: {num_active}",
    ]

    if actions_this_round:
        lines.append("")
        lines.append("Actions this round:")
        for a in actions_this_round:
            lines.append(f"  {a}")

    lines.extend([
        "",
        "Your turn. Decide your action.",
        RESPONSE_FORMAT,
    ])

    return "\n".join(lines)
