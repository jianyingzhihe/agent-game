"""JSONL log parsing: extract structured data from raw log entries."""

import re
import json
from pathlib import Path
from dataclasses import dataclass, field
from .assets import SKILL_MAP

# ── Regex patterns ──
FIELD_RE = re.compile(r"\[(.+?)\]\s*(\w+)(?:\s*\[(.+?)\])?\s*:\s*(\d+)HP\s*(\d+)手牌\s*\[(.+?)\]")
HAND_SUMMARY_RE = re.compile(r"(\S+?)×(\d+)")
HAND_SINGLE_RE = re.compile(r"(?<![×\d])(\S+?)(?=\s|$)")
OPTION_LINE_RE = re.compile(r"^(?:选项\s*)?(\d+)[：:]\s*(.+)$")
TURN_PLAYER_RE = re.compile(r"(?:你的回合|响应)\s*[—\-]\s*(\w+)")
RECENT_EVENT_RE = re.compile(r"\[事件\]\s*(.+)")


@dataclass
class PlayerSnapshot:
    """Parsed state of one player from a 场上 line."""
    name: str
    alive: bool
    hp: int
    hand_count: int
    skill_name: str
    identity_label: str = ""  # "主公", "忠臣", "反贼", "内奸", "???" or ""


@dataclass
class HandCardGroup:
    """Aggregated card type in hand (e.g. 杀×3)."""
    card_name: str
    count: int


@dataclass
class ParsedOption:
    """One option from the option menu in a user_prompt."""
    option_number: int
    action_type: str
    target: str | None
    card_name: str | None
    raw_text: str


@dataclass
class PromptData:
    """All structured data extracted from a user_prompt."""
    turn_player: str
    field_players: list[PlayerSnapshot]
    hand_cards: list[HandCardGroup]
    options: list[ParsedOption]


def load_steps(jsonl_path: str) -> list[dict]:
    """Read a JSONL file into a list of raw step dicts."""
    steps = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                steps.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return steps


def parse_field_line(text: str) -> list[PlayerSnapshot]:
    """Parse a 场上： line into player snapshots.

    Example (free_for_all): '[活] Alice: 4HP 6手牌 [咆哮] | [亡] Bob: 0HP 0手牌 [刚烈]'
    Example (identity):   '[活] Alice [主公]: 5HP 4手牌 [咆哮] | [活] Bob [???]: 4HP 4手牌 [刚烈]'
    """
    results = []
    for m in FIELD_RE.finditer(text):
        alive = m.group(1) == "活"
        name = m.group(2)
        identity_label = m.group(3) or ""
        hp = int(m.group(4))
        hand_count = int(m.group(5))
        skill_raw = m.group(6)
        skill_name = SKILL_MAP.get(skill_raw, skill_raw)
        results.append(PlayerSnapshot(
            name=name, alive=alive, hp=hp,
            hand_count=hand_count, skill_name=skill_name,
            identity_label=identity_label,
        ))
    return results


def parse_hand_line(text: str) -> list[HandCardGroup]:
    """Parse a 手牌： line into card groups.

    Example: '杀×3  闪×1  无中生有×1  无懈可击×1'
    """
    results = []
    seen = set()
    # Match "卡名×数量"
    for m in HAND_SUMMARY_RE.finditer(text):
        name = m.group(1)
        count = int(m.group(2))
        if name not in seen:
            seen.add(name)
            results.append(HandCardGroup(card_name=name, count=count))
    return results


def _infer_action_type(option_text: str) -> str:
    """Infer the action type from an option's description text."""
    text = option_text
    if "结束回合" in text or "结束" in text[:4]:
        return "end_turn"
    if "PASS" in text and "不响应" in text:
        return "pass_response"
    if "不响应" in text:
        return "pass_response"
    if "攻击·杀" in text or "[攻击" in text:
        return "sha"
    if "锦囊·AOE" in text and "南蛮" in text:
        return "spell_aoe_nanman"
    if "锦囊·AOE" in text and "万箭" in text:
        return "spell_aoe_wanjian"
    if "顺手牵羊" in text:
        return "spell_steal"
    if "过河拆桥" in text:
        return "spell_dismantle"
    if "无中生有" in text:
        return "spell_self_draw"
    if "桃园结义" in text:
        return "heal_aoe"
    if "治疗" in text and "桃" in text:
        return "heal_self"
    if "技能" in text or "苦肉" in text:
        return "skill_blood_draw"
    if "响应" in text and "闪" in text:
        return "respond_shan"
    if "响应" in text and "杀" in text:
        return "respond_sha"
    if "弃" in text:
        return "discard"
    return "unknown"


def _extract_target(option_text: str, action_type: str) -> str | None:
    """Extract target name from option text."""
    # Pattern: → TargetName
    m = re.search(r"→\s*(\w+)", option_text)
    if m:
        return m.group(1)
    # Pattern: 指定目标为XXX or 对XXX
    if action_type in ("spell_steal", "spell_dismantle"):
        m = re.search(r"【.+】.*?(\w+)$", option_text)
        if m:
            return m.group(1)
    return None


def _extract_card_name(option_text: str) -> str | None:
    """Extract card name from option text."""
    m = re.search(r"【(.+?)】", option_text)
    if m:
        return m.group(1)
    return None


def parse_options_from_text(options_text: str) -> list[ParsedOption]:
    """Parse the options block from a user_prompt.

    Handles formats like:
      '选项 0: 结束回合'
      '0: 结束回合'
      '选项 7: [锦囊] 用【顺手牵羊】#1 → Charlie (4HP 4手牌)'
    """
    results = []
    for line in options_text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        m = OPTION_LINE_RE.match(line)
        if not m:
            continue
        num = int(m.group(1))
        raw = m.group(2).strip()
        action = _infer_action_type(raw)
        target = _extract_target(raw, action)
        card = _extract_card_name(raw)
        results.append(ParsedOption(
            option_number=num,
            action_type=action,
            target=target,
            card_name=card,
            raw_text=raw,
        ))
    return results


def parse_prompt_user_prompt(step: dict) -> PromptData | None:
    """Parse a prompt event's user_prompt field into structured data."""
    if step.get("type") != "prompt":
        return None
    text = step.get("user_prompt", "")

    # Extract turn player
    turn_player = step.get("player", "")
    m = TURN_PLAYER_RE.search(text)
    if m:
        turn_player = m.group(1)

    # Extract 场上 line
    field_players = []
    field_match = re.search(r"场上[：:](.+)", text)
    if field_match:
        field_players = parse_field_line(field_match.group(1))

    # Extract 手牌 line
    hand_cards = []
    hand_match = re.search(r"手牌[：:](.+)", text)
    if hand_match:
        hand_cards = parse_hand_line(hand_match.group(1))

    # Extract options block
    options = []
    opt_match = re.search(r"(?:选项[：:]|可选操作[：:])\s*\n(.+?)(?:\n\s*\n|\Z)", text, re.DOTALL)
    if opt_match:
        options = parse_options_from_text(opt_match.group(1))
    else:
        # Try to find options at the end of the text
        lines = text.strip().split("\n")
        opt_start = -1
        for i in range(len(lines) - 1, -1, -1):
            if re.match(r"^(?:选项\s*)?\d+[：:]", lines[i].strip()):
                opt_start = i
                # Go back to find the header
                for j in range(i - 1, max(i - 3, -1), -1):
                    if "选项" in lines[j] or "操作" in lines[j]:
                        opt_start = j
                        break
                break
        if opt_start >= 0:
            opt_text = "\n".join(lines[opt_start:])
            options = parse_options_from_text(opt_text)

    return PromptData(
        turn_player=turn_player,
        field_players=field_players,
        hand_cards=hand_cards,
        options=options,
    )


def build_response_data(step: dict) -> dict:
    """Extract response-relevant fields from a response event."""
    if step.get("type") != "response":
        return {}
    parsed = step.get("parsed", {})
    return {
        "player": step.get("player", ""),
        "phase": step.get("phase", ""),
        "choice": parsed.get("choice", ""),
        "reason": parsed.get("reason", ""),
        "latency_ms": step.get("latency_ms", 0),
        "thinking": step.get("thinking", ""),
    }
