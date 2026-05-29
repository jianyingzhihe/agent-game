"""Prompt templates for Codenames — strict KEYWORD: value format."""

from typing import List

RESPONSE_FORMAT_SPYMASTER = """
RESPONSE FORMAT — Reply with exactly these lines:
REASON: <your reasoning — which words are you targeting, why this clue>
CLUE: <one word>
COUNT: <number>

Rules: CLUE must be a single English word. COUNT is how many words it connects to.
Do NOT say any of the words on the board as your clue.
"""

RESPONSE_FORMAT_GUESSER = """
RESPONSE FORMAT — Reply with exactly these lines:
REASON: <your reasoning — which words match the clue>
GUESS: <word1>, <word2>, ...

Rules: GUESS is a comma-separated list of words you want to pick.
You may guess up to COUNT+1 words. Say GUESS: PASS to end your turn.
"""


def spymaster_prompt(
    player_name: str,
    team: str,
    board_display: str,
    opponent_remaining: int,
    my_remaining: int,
    previous_clues: List[str],
) -> str:
    lines = [
        f"## You are the {team.upper()} Spymaster",
        "",
        "Give a one-word clue that connects multiple of your team's words.",
        "Avoid clues that could lead to the opponent's words, neutral words, or the assassin.",
        "",
        f"Your remaining words: {my_remaining}",
        f"Opponent remaining: {opponent_remaining}",
        "",
        "Board (your view — shows colors):",
        board_display,
    ]

    if previous_clues:
        lines.append("")
        lines.append("Previous clues given:")
        for c in previous_clues[-6:]:
            lines.append(f"  {c}")

    lines.extend([
        "",
        RESPONSE_FORMAT_SPYMASTER,
    ])

    return "\n".join(lines)


def guesser_prompt(
    player_name: str,
    team: str,
    board_display: str,
    clue_word: str,
    clue_count: int,
    previous_clues: List[str],
) -> str:
    lines = [
        f"## You are the {team.upper()} Guesser",
        "",
        f"Your spymaster's clue: **{clue_word}** (connecting {clue_count} word(s))",
        "",
        "Pick words on the board that match this clue.",
        f"You may guess up to {clue_count + 1} words.",
        "Guess PASS to end your turn without guessing more.",
        "",
        "Board (your view — unrevealed words only):",
        board_display,
    ]

    if previous_clues:
        lines.append("")
        lines.append("Previous clues:")
        for c in previous_clues[-4:]:
            lines.append(f"  {c}")

    lines.extend([
        "",
        RESPONSE_FORMAT_GUESSER,
    ])

    return "\n".join(lines)
