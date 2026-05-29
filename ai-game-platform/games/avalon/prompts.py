"""Prompt templates for Avalon — strict KEYWORD: value format."""

from typing import List, Optional

from .roles import Role

RESPONSE_FORMAT = """
RESPONSE FORMAT — Reply with exactly these lines:

For team proposal:
REASON: <why you chose these players>
TEAM: <player1>, <player2>, ...

For team vote (approve/reject):
REASON: <why>
VOTE: APPROVE or REJECT

For quest (success/fail):
REASON: <why>
QUEST: SUCCESS or FAIL

For assassin guess:
REASON: <why>
TARGET: <player name>

Rules: One keyword per line. Exact ALL CAPS keywords. No extra text.
"""


def build_system_prompt(
    player_name: str,
    role: Role,
    all_players: list,
    known_evil: Optional[List[str]] = None,
    merlin_candidates: Optional[List[str]] = None,
) -> str:
    player_names = [p.name for p in all_players]

    lines = [
        f"You are {player_name}, playing The Resistance: Avalon (阿瓦隆).",
        "",
        f"Players: {', '.join(player_names)} ({len(all_players)} total)",
        "",
        "## Your Role",
        role.description,
    ]

    if known_evil and role.faction.value == "good" and role.role_id == "merlin":
        lines.append(f"Evil players: {', '.join(known_evil)}")

    if known_evil and role.faction.value == "evil":
        lines.append(f"Fellow evil players: {', '.join(known_evil)}")

    if merlin_candidates:
        lines.append(f"These players could be Merlin (one is real, one is Morgana): {', '.join(merlin_candidates)}")

    lines.extend([
        "",
        "## Game Rules",
        f"- {len(all_players)} players: Good vs Evil",
        "- 5 quests. First to 3 wins.",
        "- Each round: Leader proposes a team → everyone votes → team members vote SUCCESS/FAIL",
        "- Good MUST vote SUCCESS. Evil may vote SUCCESS or FAIL.",
        "- If Good wins 3 quests, the Assassin gets one kill attempt on Merlin — if correct, Evil steals the win!",
        "- No one is eliminated. Everyone plays all rounds.",
        "",
        "## Strategy",
        "- Good: deduce who's evil from voting patterns and quest failures.",
        "- Evil: sabotage selectively. Too many fails = exposed.",
        "- Merlin: guide subtly. If the Assassin identifies you, Good's victory is stolen.",
        "",
        RESPONSE_FORMAT,
    ])

    return "\n".join(lines)


def propose_team_prompt(
    player_name: str,
    alive_names: List[str],
    team_size: int,
    quest_num: int,
    round_num: int,
    previous_quests: List[str],
) -> str:
    alive_str = ", ".join(alive_names)

    lines = [
        f"## Quest {quest_num} — You are the Leader",
        "",
        f"Choose {team_size} players for the quest team.",
        f"All players: {alive_str}",
    ]

    if previous_quests:
        lines.append("")
        lines.append("Previous quest results:")
        for q in previous_quests:
            lines.append(f"  {q}")

    lines.extend([
        "",
        "Reply with:",
        "REASON: <why>",
        f"TEAM: <name1>, <name2>, ...   (exactly {team_size} names, comma separated)",
    ])

    return "\n".join(lines)


def vote_team_prompt(
    player_name: str,
    proposed_team: List[str],
    leader_name: str,
    quest_num: int,
    previous_votes_this_round: List[str],
    previous_quests: List[str],
) -> str:
    team_str = ", ".join(proposed_team)

    lines = [
        f"## Quest {quest_num} — Team Vote",
        "",
        f"Leader {leader_name} proposes: {team_str}",
        "",
        "Vote APPROVE to send this team on the quest.",
        "Vote REJECT to force a new proposal.",
    ]

    if previous_votes_this_round:
        lines.append("")
        lines.append("Votes so far:")
        for v in previous_votes_this_round:
            lines.append(f"  {v}")

    if previous_quests:
        lines.append("")
        lines.append("Previous quest results:")
        for q in previous_quests:
            lines.append(f"  {q}")

    lines.extend([
        "",
        "Reply with:",
        "REASON: <why>",
        "VOTE: APPROVE or REJECT",
    ])

    return "\n".join(lines)


def quest_vote_prompt(
    player_name: str,
    team: List[str],
    quest_num: int,
    previous_quests: List[str],
    fellow_evil_on_team: int = 0,
    is_evil: bool = False,
) -> str:
    team_str = ", ".join(team)

    lines = [
        f"## Quest {quest_num} — Quest Vote (SECRET)",
        "",
        f"You are on the quest team: {team_str}",
        "",
        "Vote SUCCESS to help the quest pass.",
        "Vote FAIL to sabotage the quest.",
        "",
    ]

    if is_evil:
        if fellow_evil_on_team > 1:
            lines.append(f"⚠ You have {fellow_evil_on_team - 1} fellow evil player(s) ALSO on this team!")
            lines.append("COORDINATE: only ONE of you needs to vote FAIL to sabotage the quest.")
            lines.append("Too many FAIL votes will expose all of you. Be strategic about who fails.")
        elif fellow_evil_on_team == 1:
            lines.append("You are the ONLY evil player on this team.")
            lines.append("If you vote FAIL, only you could be responsible — weigh exposure vs sabotage.")
        lines.append("")
    else:
        lines.append("You are a GOOD player. You MUST vote SUCCESS.")
        lines.append("")

    if previous_quests:
        lines.append("Previous quest results:")
        for q in previous_quests:
            lines.append(f"  {q}")
        lines.append("")

    lines.extend([
        "Reply with:",
        "REASON: <why>",
        "QUEST: SUCCESS or FAIL",
    ])

    return "\n".join(lines)


def assassin_guess_prompt(
    player_name: str,
    alive_names: List[str],
    quest_history: List[str],
) -> str:
    alive_str = ", ".join(alive_names)

    lines = [
        "## Assassin's Final Guess",
        "",
        "The Good team won 3 quests! But you have one chance...",
        "",
        "Identify MERLIN among these players:",
        alive_str,
        "",
        "If you guess correctly, Evil steals the victory!",
    ]

    if quest_history:
        lines.append("")
        lines.append("Quest history:")
        for q in quest_history:
            lines.append(f"  {q}")

    lines.extend([
        "",
        "Reply with:",
        "REASON: <who you think is Merlin and why>",
        "TARGET: <player name>",
    ])

    return "\n".join(lines)
