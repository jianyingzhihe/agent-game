"""Card types and deck for Three Kingdoms Kill."""

import itertools
import random
from enum import Enum
from typing import Dict, List, Optional

from .skills import SkillID


class CardType(Enum):
    SHA = "杀"           # Attack: deal 1 damage, once per turn normally
    SHAN = "闪"          # Dodge: block 杀
    TAO = "桃"           # Peach: heal 1 HP (or save from death)
    WUZHONG = "无中生有"  # Draw 2 cards
    NANMAN = "南蛮入侵"    # All others must play 杀 or take 1 damage
    WANJIAN = "万箭齐发"  # All others must play 闪 or take 1 damage
    WUXIE = "无懈可击"    # Negate any spell card
    TAOYUAN = "桃园结义"  # All players heal 1 HP
    GUOHE = "过河拆桥"    # Discard 1 card from target's hand
    SHUNSHOU = "顺手牵羊" # Take 1 card from target's hand


class Card:
    def __init__(self, card_type: CardType, suit: str = "", rank: str = "", card_id: str | None = None):
        self.card_type = card_type
        self.suit = suit
        self.rank = rank
        self.card_id = card_id or f"sgs-{next(_CARD_ID_COUNTER)}"

    @property
    def name(self) -> str:
        return self.card_type.value

    @property
    def is_basic(self) -> bool:
        return self.card_type in (CardType.SHA, CardType.SHAN, CardType.TAO)

    @property
    def is_spell(self) -> bool:
        return not self.is_basic

    def __repr__(self) -> str:
        return self.name


_CARD_ID_COUNTER = itertools.count(1)


def create_deck() -> List[Card]:
    """Create a standard deck. Returns shuffled list."""
    cards = []
    # 30 杀
    cards.extend([Card(CardType.SHA)] * 30)
    # 15 闪
    cards.extend([Card(CardType.SHAN)] * 15)
    # 8 桃
    cards.extend([Card(CardType.TAO)] * 8)
    # 4 无中生有
    cards.extend([Card(CardType.WUZHONG)] * 4)
    # 3 南蛮入侵
    cards.extend([Card(CardType.NANMAN)] * 3)
    # 1 万箭齐发
    cards.extend([Card(CardType.WANJIAN)] * 1)
    # 3 无懈可击
    cards.extend([Card(CardType.WUXIE)] * 3)
    # 1 桃园结义
    cards.extend([Card(CardType.TAOYUAN)] * 1)
    # 6 过河拆桥
    cards.extend([Card(CardType.GUOHE)] * 6)
    # 5 顺手牵羊
    cards.extend([Card(CardType.SHUNSHOU)] * 5)
    random.shuffle(cards)
    return cards


def hand_list_str(hand: List[Card]) -> str:
    """Format hand with indices for LLM selection."""
    if not hand:
        return "(empty)"
    lines = []
    for i, card in enumerate(hand):
        lines.append(f"#{i+1}:{card.name}")
    return "\n".join(lines)


def hand_summary(hand: List[Card]) -> str:
    """Brief hand summary like '杀×3 闪×2 桃×1'."""
    from collections import Counter
    counts = Counter(c.name for c in hand)
    parts = []
    for name in ["杀", "闪", "桃", "无中生有", "南蛮入侵", "万箭齐发", "无懈可击", "桃园结义", "过河拆桥", "顺手牵羊"]:
        if counts.get(name, 0) > 0:
            parts.append(f"{name}×{counts[name]}")
    return "  ".join(parts) if parts else "无"


# ---- Option generation for AI selection ----

def generate_play_options(
    hand: List[Card],
    skill: Optional[SkillID],
    sha_used: bool,
    hp: int,
    max_hp: int,
    alive_players: List[Dict],
    player_name: str,
) -> List[Dict]:
    """Generate numbered options for a player's turn.

    Args:
        hand: Player's current hand cards
        skill: Player's skill (SkillID enum)
        sha_used: Whether 杀 has been used this turn
        hp: Current HP
        max_hp: Maximum HP
        alive_players: List of dicts [{name, hp, card_count}]
        player_name: Current player's name (to exclude from targets)

    Returns:
        List of option dicts: {index, action_type, card_index, card_name, target_name, description}
        Option 0 is always END.
    """
    options = [{"index": 0, "action_type": "end", "description": "结束回合"}]
    idx = 0

    can_unlimited_sha = (skill == SkillID.UNLIMITED_SHA)
    can_swap = (skill == SkillID.SWAP)
    can_sha = can_unlimited_sha or not sha_used

    # ---- 杀 options ----
    if can_sha:
        for i, card in enumerate(hand):
            is_sha = (card.card_type == CardType.SHA)
            is_swap_sha = (card.card_type == CardType.SHAN and can_swap)
            if not is_sha and not is_swap_sha:
                continue

            card_label = "杀" if is_sha else "闪→杀(武圣)"
            for target in alive_players:
                if target["name"] == player_name:
                    continue
                # Check 空城·守 immunity (we approximate: if target has skill immune and 0 cards)
                # We can't check skills here directly, so we pass all and engine filters
                idx += 1
                options.append({
                    "index": idx,
                    "action_type": "sha",
                    "card_index": i,
                    "card_name": card_label,
                    "target_name": target["name"],
                    "description": f"[攻击·杀] 用【{card_label}】#{i+1} → {target['name']} ({target['hp']}HP {target['card_count']}手牌)",
                })

    # ---- 桃 options ----
    if hp < max_hp:
        for i, card in enumerate(hand):
            if card.card_type == CardType.TAO:
                idx += 1
                options.append({
                    "index": idx,
                    "action_type": "tao",
                    "card_index": i,
                    "card_name": "桃",
                    "target_name": None,
                    "description": f"[治疗] 用【桃】#{i+1} 恢复1体力 ({hp}→{hp+1})",
                })

    # ---- Spell options ----
    spell_handled = {CardType.WUXIE}  # 无懈可击 not usable proactively on own turn
    for i, card in enumerate(hand):
        ct = card.card_type
        if ct in spell_handled:
            continue

        if ct == CardType.WUZHONG:
            idx += 1
            options.append({
                "index": idx, "action_type": "spell", "card_index": i,
                "card_name": "无中生有", "target_name": None,
                "description": f"[锦囊] 用【无中生有】#{i+1} — 摸2张牌",
            })
        elif ct == CardType.NANMAN:
            idx += 1
            options.append({
                "index": idx, "action_type": "spell", "card_index": i,
                "card_name": "南蛮入侵", "target_name": None,
                "description": f"[锦囊·AOE] 用【南蛮入侵】#{i+1} — 全体必须出【杀】",
            })
        elif ct == CardType.WANJIAN:
            idx += 1
            options.append({
                "index": idx, "action_type": "spell", "card_index": i,
                "card_name": "万箭齐发", "target_name": None,
                "description": f"[锦囊·AOE] 用【万箭齐发】#{i+1} — 全体必须出【闪】",
            })
        elif ct == CardType.TAOYUAN:
            idx += 1
            options.append({
                "index": idx, "action_type": "spell", "card_index": i,
                "card_name": "桃园结义", "target_name": None,
                "description": f"[锦囊] 用【桃园结义】#{i+1} — 全体恢复1体力",
            })
        elif ct == CardType.GUOHE:
            for target in alive_players:
                if target["name"] == player_name or target["card_count"] == 0:
                    continue
                idx += 1
                options.append({
                    "index": idx, "action_type": "spell", "card_index": i,
                    "card_name": "过河拆桥", "target_name": target["name"],
                    "description": f"[锦囊] 用【过河拆桥】#{i+1} → {target['name']} (拆1张牌)",
                })
        elif ct == CardType.SHUNSHOU:
            for target in alive_players:
                if target["name"] == player_name or target["card_count"] == 0:
                    continue
                idx += 1
                options.append({
                    "index": idx, "action_type": "spell", "card_index": i,
                    "card_name": "顺手牵羊", "target_name": target["name"],
                    "description": f"[锦囊] 用【顺手牵羊】#{i+1} → {target['name']} (拿1张牌)",
                })

    # ---- Skill options ----
    if skill == SkillID.BLOOD_DRAW and hp > 0:
        idx += 1
        options.append({
            "index": idx, "action_type": "skill",
            "card_index": None, "card_name": "苦肉", "target_name": None,
            "description": "[技能] 苦肉 — 扣1血摸2牌",
        })

    return options


def generate_response_options(
    hand: List[Card],
    required_type: CardType,
    skill: Optional[SkillID],
) -> List[Dict]:
    """Generate numbered options for responding to a card (e.g. 闪 to 杀).

    Args:
        hand: Player's current hand cards
        required_type: The card type needed (SHA or SHAN)
        skill: Player's skill (for 武圣 swap check)

    Returns:
        List of option dicts. Option 0 is always PASS.
    """
    options = [{"index": 0, "action_type": "pass", "description": "PASS — 不响应"}]
    idx = 0
    can_swap = (skill == SkillID.SWAP)

    for i, card in enumerate(hand):
        valid = (card.card_type == required_type)
        if not valid and can_swap:
            # 武圣: 杀↔闪
            if required_type == CardType.SHA and card.card_type == CardType.SHAN:
                valid = True
            elif required_type == CardType.SHAN and card.card_type == CardType.SHA:
                valid = True

        if valid:
            idx += 1
            label = card.name
            if can_swap and card.card_type != required_type:
                label = f"{card.name}→{required_type.value}(武圣)"
            options.append({
                "index": idx,
                "action_type": "respond",
                "card_index": i,
                "card_name": label,
                "target_name": None,
                "description": f"[响应] 用【{label}】#{i+1}",
            })

    return options


def generate_card_choice_options(
    hand: List[Card],
    action_label: str,
) -> List[Dict]:
    """Generate numbered options for choosing a card from a hand.
    Used for discard phase, 过河拆桥 target selection, 反馈 steal selection.

    Args:
        hand: The hand to choose from
        action_label: Action description prefix (e.g. "弃", "拆", "拿")

    Returns:
        List of option dicts, 1-based index.
    """
    options = []
    for i, card in enumerate(hand):
        options.append({
            "index": i + 1,
            "card_index": i,
            "card_name": card.name,
            "description": f"{action_label}【{card.name}】#{i+1}",
        })
    return options


def format_options_for_prompt(options: List[Dict]) -> str:
    """Format option dicts into a numbered text list for the prompt."""
    lines = []
    for opt in options:
        lines.append(f"选项 {opt['index']}: {opt['description']}")
    return "\n".join(lines)


def card_at(hand: List[Card], index: int) -> Optional[Card]:
    """Safely get card at index from hand."""
    if 0 <= index < len(hand):
        return hand[index]
    return None
