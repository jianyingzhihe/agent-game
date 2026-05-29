"""Prompt templates for the Werewolf game — strict KEYWORD: value format.

Every model response must follow a rigid line-based format:
  REASON: <one line>
  TARGET: <name>      (for night actions & voting)
  SPEECH: <text>       (for day discussion)
  SAVE: yes|no         (witch only)
  POISON: <name>|none  (witch only)
  VOTE: <name>         (day voting)

The parser only looks for these exact prefixes at line start (case-insensitive).
No tags, no JSON, no ambiguity.
"""

from typing import List, Optional

from .roles import Role

# ============================================================
#  Response format instruction (appended to every system prompt)
# ============================================================

RESPONSE_FORMAT = """
RESPONSE FORMAT — You MUST respond with exactly these lines, nothing else:

For werewolf kill / seer check / hunter shot:
REASON: <your reasoning>
TARGET: <player name>

For witch:
REASON: <your reasoning>
SAVE: yes or no
POISON: <player name> or none

For day discussion:
REASON: <your private reasoning>
SPEECH: <your public statement>

For day voting:
REASON: <your reasoning>
VOTE: <player name>

Rules:
- Each line starts with the EXACT keyword in ALL CAPS followed by colon and space.
- One keyword per line. Do NOT combine lines.
- Do NOT add any other text, punctuation, or formatting outside these lines.
- TARGET/VOTE must be the exact player name from the player list.
- REASON should be 1-2 sentences.
"""

# ============================================================
#  System Prompt
# ============================================================


def build_system_prompt(
    player_name: str,
    role: Role,
    all_players: list,
    fellow_wolves: Optional[List[str]] = None,
) -> str:
    player_names = [p.name for p in all_players]
    player_list_str = ", ".join(player_names)

    lines = [
        f"You are {player_name}, playing Werewolf (狼人杀).",
        "",
        f"Players: {player_list_str} ({len(all_players)} total)",
        "",
        "## Your Role",
        role.description,
    ]

    if fellow_wolves:
        lines.append(f"Fellow werewolves: {', '.join(fellow_wolves)}")

    lines.extend([
        "",
        "## Game Flow",
        "Night: Werewolves vote to kill → Seer checks → Witch acts",
        "Day: Death announced → Players discuss → Vote to eliminate",
        "Werewolves win when they outnumber villagers. Villagers win when all wolves dead.",
        "",
        "## Strategy",
        "- You may lie, deceive, or accuse as suits your role.",
        "- Do NOT mention you are an AI. Act human.",
        "- Keep responses concise.",
        "",
        RESPONSE_FORMAT,
    ])

    return "\n".join(lines)


def _state_section(alive: List[str], dead: List[str]) -> str:
    """Format alive/dead player summary for prompts."""
    parts = [f"Alive ({len(alive)}): " + ", ".join(alive)]
    if dead:
        parts.append(f"Dead ({len(dead)}): " + ", ".join(dead))
    return "\n".join(parts)


# ============================================================
#  Night Phase Prompts
# ============================================================


def night_werewolf_prompt(
    alive_names: List[str],
    dead_names: List[str],
    fellow_wolves: List[str],
    game_log: List[str],
    previous_suggestions: Optional[List[str]] = None,
) -> str:
    alive_str = "\n".join(f"  {n}" for n in alive_names)

    lines = [
        "## Night — Werewolf Kill Vote",
        "",
        _state_section(alive_names, dead_names),
        "",
        f"Valid targets (non-wolves):",
        alive_str,
        "",
        f"Your partners: {', '.join(fellow_wolves)}",
    ]

    if previous_suggestions:
        lines.append("")
        lines.append("Partners' votes so far:")
        for s in previous_suggestions:
            lines.append(f"  {s}")

    if game_log:
        lines.append("")
        lines.append("Recent events:")
        for e in game_log[-8:]:
            lines.append(f"  {e}")

    lines.extend([
        "",
        "Vote for ONE player to kill tonight.",
        "Reply with:",
        "REASON: <why>",
        "TARGET: <player name>",
    ])

    return "\n".join(lines)


def night_seer_prompt(
    alive_names: List[str],
    dead_names: List[str],
    previous_checks: List[str],
    game_log: List[str],
) -> str:
    alive_str = "\n".join(f"  {n}" for n in alive_names)

    lines = [
        "## Night — Seer Investigation",
        "",
        _state_section(alive_names, dead_names),
        "",
        f"Players you can check:",
        alive_str,
    ]

    if previous_checks:
        lines.append("")
        lines.append("Previous checks:")
        for c in previous_checks:
            lines.append(f"  {c}")

    if game_log:
        lines.append("")
        lines.append("Recent events:")
        for e in game_log[-6:]:
            lines.append(f"  {e}")

    lines.extend([
        "",
        "Choose ONE player to investigate.",
        "Reply with:",
        "REASON: <why>",
        "TARGET: <player name>",
    ])

    return "\n".join(lines)


def night_witch_prompt(
    alive_names: List[str],
    dead_names: List[str],
    werewolf_target: str,
    has_antidote: bool,
    has_poison: bool,
    game_log: List[str],
) -> str:
    alive_str = "\n".join(f"  {n}" for n in alive_names)

    lines = [
        "## Night — Witch Decision",
        "",
        _state_section(alive_names, dead_names),
        "",
        f"Werewolves targeted: **{werewolf_target}**",
        "",
        f"Antidote (save): {'YES' if has_antidote else 'USED'}",
        f"Poison (kill):   {'YES' if has_poison else 'USED'}",
    ]

    if game_log:
        lines.append("")
        lines.append("Recent events:")
        for e in game_log[-6:]:
            lines.append(f"  {e}")

    lines.extend([
        "",
        "Decide your actions.",
        "Reply with:",
        "REASON: <your reasoning>",
        "SAVE: yes or no",
        "POISON: <player name> or none",
    ])

    return "\n".join(lines)


# ============================================================
#  Day Phase Prompts
# ============================================================


def day_discussion_prompt(
    player_name: str,
    alive_names: List[str],
    dead_names: List[str],
    night_summary: str,
    discussion_history: List[str],
    game_log: List[str],
) -> str:

    lines = [
        "## Day — Discussion",
        "",
        _state_section(alive_names, dead_names),
        f"Last night: {night_summary}",
    ]

    if discussion_history:
        lines.append("")
        lines.append("What others said:")
        for i, speech in enumerate(discussion_history[-10:], 1):
            lines.append(f"  {speech}")

    if game_log:
        lines.append("")
        lines.append("Previous rounds:")
        for e in game_log[-6:]:
            lines.append(f"  {e}")

    lines.extend([
        "",
        f"Your turn to speak, {player_name}.",
        "Reply with:",
        "REASON: <your private strategy/thoughts>",
        "SPEECH: <your public statement to everyone>",
    ])

    return "\n".join(lines)


def day_vote_prompt(
    player_name: str,
    alive_names: List[str],
    dead_names: List[str],
    discussion_summary: str,
    game_log: List[str],
) -> str:
    alive_str = "\n".join(f"  {n}" for n in alive_names)

    lines = [
        "## Day — Elimination Vote",
        "",
        _state_section(alive_names, dead_names),
        "",
        f"Vote to eliminate one player:",
        alive_str,
        f"Discussion: {discussion_summary}",
    ]

    if game_log:
        lines.append("")
        lines.append("Recent events:")
        for e in game_log[-4:]:
            lines.append(f"  {e}")

    lines.extend([
        "",
        f"Cast your vote, {player_name}.",
        "Reply with:",
        "REASON: <why>",
        "VOTE: <player name>",
    ])

    return "\n".join(lines)


def hunter_shot_prompt(
    alive_names: List[str],
    dead_names: List[str],
    game_log: List[str],
) -> str:
    alive_str = "\n".join(f"  {n}" for n in alive_names)

    lines = [
        "## You Died — Hunter's Shot",
        "",
        _state_section(alive_names, dead_names),
        "",
        "As the Hunter, shoot one player to take with you.",
        "",
        f"Alive targets:",
        alive_str,
    ]

    if game_log:
        lines.append("")
        lines.append("Recent events:")
        for e in game_log[-6:]:
            lines.append(f"  {e}")

    lines.extend([
        "",
        "Reply with:",
        "REASON: <why>",
        "TARGET: <player name>   (or TARGET: none to spare everyone)",
    ])

    return "\n".join(lines)
