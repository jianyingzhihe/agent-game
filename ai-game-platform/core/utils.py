"""Common utilities shared across all games."""

import json
import random
import re
from typing import Any, Dict, List, Optional


def parse_tagged_block(response: str, tag: str) -> Optional[str]:
    """Extract content between [TAG]...[/TAG] delimiters.

    Args:
        response: The full model response text
        tag: Tag name (case-insensitive), e.g. 'THINKING', 'ACTION', 'SPEECH'

    Returns:
        Content between the tags, or None if not found
    """
    pattern = rf'\[{tag}\]\s*(.*?)\s*\[/{tag}\]'
    match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else None


def try_parse_json(response: str) -> Optional[Dict]:
    """Attempt to extract and parse a JSON object from model response."""
    json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Try with nested braces
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return None


def format_player_list(players: List[Any], show_status: bool = True) -> str:
    """Format a list of players for display in prompts.

    Args:
        players: List of Player objects
        show_status: Include alive/dead status

    Returns:
        Formatted string like "1. Alice  2. Bob [DEAD]  3. Charlie"
    """
    lines = []
    for i, p in enumerate(players, 1):
        if show_status:
            status = " [DEAD]" if hasattr(p, 'alive') and not p.alive else ""
        else:
            status = ""
        lines.append(f"  {i}. {p.name}{status}")
    return "\n".join(lines)


def parse_keyword_response(response: str) -> Dict[str, str]:
    """Parse a model response in strict KEYWORD: value format.

    Each line is checked for known keywords (case-insensitive).
    The value after the colon is extracted.

    Known keywords:
        REASON, TARGET, VOTE, SPEECH, SAVE, POISON,
        QUEST, TEAM, CLUE, COUNT, GUESS, ACTION

    Example:
        >>> parse_keyword_response("REASON: Charlie is suspicious\\nVOTE: Charlie")
        {"reason": "Charlie is suspicious", "vote": "Charlie"}

    If a keyword appears multiple times, the last occurrence wins.
    Also falls back to tag-based parsing ([THINKING], [ACTION], [SPEECH]).
    """
    result: Dict[str, str] = {
        "reason": "",
        "target": "",
        "vote": "",
        "speech": "",
        "save": "",
        "poison": "",
        "quest": "",
        "team": "",
        "clue": "",
        "count": "",
        "guess": "",
        "action": "",
        "bid": "",
        "play": "",
        "choice": "",
    }

    for line in response.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        upper = line.upper()
        for key in result:
            if upper.startswith(f"{key.upper()}:"):
                result[key] = line[len(key) + 1:].strip()
                break

    # Fallback: try [TAG] format if keywords are empty
    if not result["reason"]:
        result["reason"] = parse_tagged_block(response, "THINKING") or ""
    if not result["target"] and not result["vote"]:
        action = parse_tagged_block(response, "ACTION") or ""
        for keyword in ("KILL:", "CHECK:", "SHOOT:", "VOTE:", "TARGET:"):
            if keyword in action.upper():
                result["target"] = action.upper().split(keyword)[-1].strip().rstrip(".,;!?")
                break
        if not result["target"]:
            result["target"] = action.strip()
    if not result["speech"]:
        result["speech"] = parse_tagged_block(response, "SPEECH") or ""

    return result


def format_alive_players(players: List[Any]) -> str:
    """Format only alive players."""
    alive = [p for p in players if p.alive]
    return format_player_list(alive, show_status=False)


def count_votes(votes: List[Optional[str]]) -> Dict[str, int]:
    """Count votes, returning {target: count}. None votes are abstentions."""
    counts: Dict[str, int] = {}
    for v in votes:
        if v is None:
            continue
        counts[v] = counts.get(v, 0) + 1
    return counts


def majority_vote(votes: List[Optional[str]]) -> Optional[str]:
    """Get the target with the most votes. Ties are broken randomly."""
    counts = count_votes(votes)
    if not counts:
        return None
    max_count = max(counts.values())
    top = [name for name, c in counts.items() if c == max_count]
    return random.choice(top)


def truncate(text: str, max_len: int = 500) -> str:
    """Truncate text for display."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


# ---- ANSI color helpers for terminal output ----

class Colors:
    """ANSI escape codes for terminal colors."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    @staticmethod
    def color(text: str, color: str) -> str:
        return f"{color}{text}{Colors.RESET}"

    @staticmethod
    def bold(text: str) -> str:
        return f"{Colors.BOLD}{text}{Colors.RESET}"

    @staticmethod
    def dim(text: str) -> str:
        return f"{Colors.DIM}{text}{Colors.RESET}"
