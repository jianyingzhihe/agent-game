"""Dou Dizhu card system — 54 cards, combination types, comparison."""

import random
import re
from collections import Counter
from typing import List, Optional, Tuple

# Rank order: 3(3) < 4(4) < ... < A(14) < 2(15) < Small Joker(16) < Big Joker(17)
RANK_ORDER = {str(r): r for r in range(3, 11)}  # 3-10
RANK_ORDER.update({"J": 11, "Q": 12, "K": 13, "A": 14, "2": 15})
RANK_ORDER["小王"] = 16
RANK_ORDER["大王"] = 17

RANK_DISPLAY = {v: k for k, v in RANK_ORDER.items()}
RANK_CODE = {
    3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10",
    11: "11", 12: "12", 13: "13", 14: "14", 15: "15",
    16: "-1", 17: "-2",
}
CODE_TO_RANK = {code: rank for rank, code in RANK_CODE.items()}
TOKEN_TO_RANK = {
    "J": 11,
    "Q": 12,
    "K": 13,
    "A": 14,
    "2": 15,
    "SJ": 16,
    "SMALLJOKER": 16,
    "XIAOWANG": 16,
    "小王": 16,
    "BJ": 17,
    "BIGJOKER": 17,
    "DAWANG": 17,
    "大王": 17,
}

SUITS = ["♠", "♥", "♦", "♣"]

# Combo type ranks (higher = stronger)
COMBO_RANKS = {
    "single": 1, "pair": 2, "triple": 3, "triple_one": 4, "triple_two": 5,
    "straight": 6, "consecutive_pairs": 7, "airplane": 8,
    "four_two": 9, "bomb": 10, "rocket": 11,
}


class Card:
    def __init__(self, rank: int, suit: str = ""):
        self.rank = rank
        self.suit = suit

    def __repr__(self):
        if self.rank >= 16:
            return RANK_DISPLAY[self.rank]
        return f"{RANK_DISPLAY[self.rank]}{self.suit}"

    def __eq__(self, other):
        return self.rank == other.rank and self.suit == other.suit

    def __hash__(self):
        return hash((self.rank, self.suit))

    @property
    def is_joker(self):
        return self.rank >= 16


def create_deck() -> List[Card]:
    """Create a shuffled 54-card deck."""
    cards = []
    for rank in range(3, 16):  # 3 to 2
        for suit in SUITS:
            cards.append(Card(rank, suit))
    cards.append(Card(16, ""))  # Small Joker
    cards.append(Card(17, ""))  # Big Joker
    random.shuffle(cards)
    return cards


def deal(cards: List[Card]) -> Tuple[List[Card], List[Card], List[Card], List[Card]]:
    """Deal 17 cards each + 3 landlord cards."""
    return cards[:17], cards[17:34], cards[34:51], cards[51:]


def sort_hand(hand: List[Card]) -> List[Card]:
    return sorted(hand, key=lambda c: c.rank, reverse=True)


def hand_str(hand: List[Card]) -> str:
    return " ".join(str(c) for c in sort_hand(hand))


def short_hand_str(hand: List[Card]) -> str:
    """Compact rank-count representation."""
    counts = Counter(c.rank for c in hand)
    parts = []
    for rank in sorted(counts.keys(), reverse=True):
        count = counts[rank]
        name = RANK_DISPLAY.get(rank, "?")
        if count == 1:
            parts.append(name)
        else:
            parts.append(f"{name}×{count}")
    return " ".join(parts)


def encoded_hand_str(hand: List[Card]) -> str:
    """Rank-coded hand representation, e.g. '#15 #15 #14 #-1 #-2'."""
    return " ".join(f"#{RANK_CODE.get(card.rank, '?')}" for card in sort_hand(hand))


def encoded_hand_inventory_str(hand: List[Card]) -> str:
    """Compact inventory by rank, e.g. '#15×2 #14 #13×2 #-1'."""
    counts = Counter(card.rank for card in hand)
    parts = []
    for rank in sorted(counts.keys(), reverse=True):
        code = f"#{RANK_CODE.get(rank, '?')}"
        count = counts[rank]
        parts.append(code if count == 1 else f"{code}×{count}")
    return " ".join(parts)


def rank_code_hint(rank: int) -> str:
    """Human-friendly code hint, e.g. '#13/#K'."""
    alias_map = {
        11: "#11/#J",
        12: "#12/#Q",
        13: "#13/#K",
        14: "#14/#A",
        15: "#15/#2",
        16: "#-1/#小王",
        17: "#-2/#大王",
    }
    return alias_map.get(rank, f"#{rank}")


def _token_to_rank(token: str) -> Optional[int]:
    token = token.strip()
    if not token:
        return None

    if token in CODE_TO_RANK:
        return CODE_TO_RANK[token]

    upper = token.upper()
    if upper in TOKEN_TO_RANK:
        return TOKEN_TO_RANK[upper]

    if token in TOKEN_TO_RANK:
        return TOKEN_TO_RANK[token]

    if token in RANK_ORDER:
        return RANK_ORDER[token]

    return None


def parse_rank_selection(hand: List[Card], selection: str) -> Optional[List[Card]]:
    """Parse '#3 #3 #15 #-1', '#K #K', '#A', '#小王', or 'PASS'.

    Returns list of selected cards, empty list for PASS, None for invalid.
    """
    selection = selection.strip()
    if selection.upper() == "PASS":
        return []

    normalized_tokens = []
    for raw_token in selection.replace(",", " ").split():
        token = raw_token.strip()
        if not token:
            continue
        if token.upper() == "PASS":
            return []
        if token.startswith("#"):
            token = token[1:].strip()
        normalized_tokens.append(token)

    if not normalized_tokens:
        return None

    available = sort_hand(hand)
    selected = []
    for token in normalized_tokens:
        rank = _token_to_rank(token)
        if rank is None:
            return None
        found = next((card for card in available if card.rank == rank), None)
        if found is None:
            return None
        selected.append(found)
        available.remove(found)
    return selected if selected else None


def validate_rank_selection(hand: List[Card], selection: str) -> tuple[Optional[List[Card]], str]:
    """Validate selection and return (cards, error_message)."""
    selection = selection.strip()
    if selection.upper() == "PASS":
        return [], ""

    normalized_tokens = []
    raw_tokens = []
    for raw_token in selection.replace(",", " ").split():
        token = raw_token.strip()
        if not token:
            continue
        if token.upper() == "PASS":
            return [], ""
        if token.startswith("#"):
            token = token[1:].strip()
        raw_tokens.append(raw_token.strip())
        normalized_tokens.append(token)

    if not normalized_tokens:
        return None, "你没有写出任何有效编码。"

    available = sort_hand(hand)
    available_counts = Counter(card.rank for card in available)
    selected = []
    for raw_token, token in zip(raw_tokens, normalized_tokens):
        rank = _token_to_rank(token)
        if rank is None:
            return None, (
                f"无法识别编码 '{raw_token}'。请使用当前手牌里真实存在的编码，"
                "例如 #13/#K、#14/#A、#15/#2、#-1/#小王。"
            )
        if available_counts[rank] <= 0:
            return None, (
                f"你写了 {raw_token}，但当前手牌里没有这么多 {rank_code_hint(rank)}。"
                f" 当前手牌库存：{encoded_hand_inventory_str(hand)}。"
            )
        found = next((card for card in available if card.rank == rank), None)
        if found is None:
            return None, (
                f"你写了 {raw_token}，但当前手牌里没有这么多 {rank_code_hint(rank)}。"
                f" 当前手牌库存：{encoded_hand_inventory_str(hand)}。"
            )
        selected.append(found)
        available.remove(found)
        available_counts[rank] -= 1
    return selected if selected else None, ""


# ---- Combo Detection ----

def detect_combo(cards: List[Card]) -> Optional[dict]:
    """Detect the combination type of a set of cards.
    Returns {type, rank, length, extra_cards} or None if invalid.
    """
    if not cards:
        return None

    ranks = sorted([c.rank for c in cards], reverse=True)
    n = len(ranks)
    counter = Counter(ranks)
    counts = sorted(counter.values(), reverse=True)
    unique = sorted(counter.keys(), reverse=True)

    # Rocket: both jokers
    if set(ranks) == {16, 17}:
        return {"type": "rocket", "rank": 17, "length": 1}

    # Bomb: 4 of a kind, exactly 4 cards
    if n == 4 and counts == [4]:
        return {"type": "bomb", "rank": unique[0], "length": 1}

    # Single
    if n == 1:
        return {"type": "single", "rank": ranks[0], "length": 1}

    # Pair
    if n == 2 and counts == [2]:
        return {"type": "pair", "rank": unique[0], "length": 1}

    # Triple
    if n == 3 and counts == [3]:
        return {"type": "triple", "rank": unique[0], "length": 1}

    # Triple + 1
    if n == 4 and counts == [3, 1]:
        return {"type": "triple_one", "rank": unique[0], "length": 1}

    # Triple + 2
    if n == 5 and counts == [3, 2]:
        return {"type": "triple_two", "rank": unique[0], "length": 1}

    # Four + 2 singles
    if n == 6 and counts == [4, 1, 1]:
        return {"type": "four_two", "rank": unique[0], "length": 2}

    # Straight: 5+ consecutive, no 2 or jokers
    if n >= 5 and all(c == 1 for c in counts) and all(r <= 14 for r in ranks):
        if all(ranks[i] - ranks[i+1] == 1 for i in range(n-1)):
            return {"type": "straight", "rank": ranks[0], "length": n}

    # Consecutive pairs: 3+ pairs, consecutive, no 2 or jokers
    if n >= 6 and n % 2 == 0 and all(c == 2 for c in counts) and all(r <= 14 for r in unique):
        if len(unique) >= 3 and all(unique[i] - unique[i+1] == 1 for i in range(len(unique)-1)):
            return {"type": "consecutive_pairs", "rank": unique[0], "length": len(unique)}

    # Airplane: 2+ consecutive triples, optionally with wings
    triple_ranks = [r for r, c in counter.items() if c == 3 and r <= 14]
    triple_ranks.sort(reverse=True)
    if len(triple_ranks) >= 2:
        # Find longest consecutive sequence
        best = []
        cur = [triple_ranks[0]]
        for r in triple_ranks[1:]:
            if cur[-1] - r == 1:
                cur.append(r)
            else:
                if len(cur) > len(best):
                    best = cur
                cur = [r]
        if len(cur) > len(best):
            best = cur
        if len(best) >= 2:
            triple_count = len(best)
            total_triple_cards = triple_count * 3
            extra = n - total_triple_cards
            if extra == 0:
                return {"type": "airplane", "rank": best[0], "length": triple_count}
            if extra == triple_count:  # 1 wing each
                return {"type": "airplane", "rank": best[0], "length": triple_count, "wings": 1}
            if extra == triple_count * 2:  # 2 wings each
                return {"type": "airplane", "rank": best[0], "length": triple_count, "wings": 2}

    return None


def can_beat(new_combo: dict, last_combo: Optional[dict]) -> bool:
    """Check if new_combo beats last_combo. If last_combo is None, any valid combo passes."""
    if last_combo is None:
        return True

    nt, nr, nl = new_combo["type"], new_combo["rank"], new_combo.get("length", 1)
    lt, lr, ll = last_combo["type"], last_combo["rank"], last_combo.get("length", 1)

    # Rocket beats everything
    if nt == "rocket":
        return True
    if lt == "rocket":
        return False

    # Bomb beats non-bomb
    if nt == "bomb" and lt != "bomb":
        return True
    if lt == "bomb" and nt != "bomb":
        return False

    # Same type: higher rank, same length
    if nt == lt and nl == ll:
        return nr > lr

    return False


def combo_name(combo: dict) -> str:
    """Human-readable combo description."""
    t = combo["type"]
    r = combo["rank"]
    l = combo.get("length", 1)
    name_map = {
        "single": "单张", "pair": "对子", "triple": "三张",
        "triple_one": "三带一", "triple_two": "三带二",
        "straight": f"{l}顺子", "consecutive_pairs": f"{l}连对",
        "airplane": f"{l}飞机", "four_two": "四带二",
        "bomb": "炸弹", "rocket": "火箭",
    }
    return name_map.get(t, t)


def cards_from_string(hand: List[Card], card_str: str) -> Optional[List[Card]]:
    """Parse a card selection string like '3♠ 3♥ 3♦ 5♠' or 'PASS' from a hand."""
    card_str = card_str.strip()
    if card_str.upper() == "PASS" or card_str == "":
        return []

    # Map display names to cards in hand
    available = list(hand)
    selected = []
    for token in card_str.replace(",", " ").split():
        token = token.strip()
        if not token:
            continue
        if token == "PASS":
            return []
        # Find matching card in hand
        found = None
        for c in available:
            if str(c) == token:
                found = c
                break
        if found:
            selected.append(found)
            available.remove(found)
        else:
            # Try matching by rank only
            for c in available:
                if RANK_DISPLAY.get(c.rank) == token:
                    found = c
                    break
            if found:
                selected.append(found)
                available.remove(found)
    return selected if selected else None


# ═══════════════════════════════════════════════════════════════════
#  Play Option Enumeration — generate a menu of valid plays for the AI
# ═══════════════════════════════════════════════════════════════════

# Combo-type sort priority (lower = shown first in options list)
_COMBO_PRIORITY = {
    "rocket": 0, "bomb": 1, "airplane": 2, "four_two": 3,
    "consecutive_pairs": 4, "straight": 5, "triple_two": 6,
    "triple_one": 7, "triple": 8, "pair": 9, "single": 10,
}


def generate_play_options(
    hand: List[Card],
    last_play: Optional[dict] = None,
) -> List[dict]:
    """Generate a ranked list of valid play options from *hand*.

    When *last_play* is None the player is leading; otherwise only plays
    that can beat *last_play* are returned (plus PASS which is always
    available as the implicit option 0).

    Returns at most 15 options, sorted best-first (complex combos, bombs,
    then simpler plays).
    """
    if not hand:
        return []

    sorted_hand = sort_hand(hand)
    rank_counts = Counter(c.rank for c in sorted_hand)
    ranks_present = sorted(rank_counts.keys(), reverse=True)

    raw: List[dict] = []

    # ---- Bombs & Rocket (always valid overrides) ----
    _add_bombs_and_rocket(raw, sorted_hand, rank_counts)

    if last_play is None:
        _add_leading_options(raw, sorted_hand, rank_counts, ranks_present)
    else:
        _add_beating_options(raw, sorted_hand, rank_counts, ranks_present,
                             last_play)

    # ---- Deduplicate ----
    seen: set = set()
    unique: List[dict] = []
    for opt in raw:
        key = (opt["combo_type"], opt["rank"], opt.get("length", 1),
               opt.get("wings", 0))
        if key not in seen:
            seen.add(key)
            unique.append(opt)

    # ---- Sort: complex combos first, then by rank desc ----
    unique.sort(key=lambda o: (
        _COMBO_PRIORITY.get(o["combo_type"], 99),
        -o["rank"],
    ))

    # Assign index and label
    for i, opt in enumerate(unique[:15]):
        opt["index"] = i + 1
        opt["remaining"] = len(hand) - len(opt["cards"])
        opt["label"] = _strategic_label(opt)

    return unique[:15]


def format_options_for_prompt(
    options: List[dict],
    hand_size: int,
) -> str:
    """Format a list of play options for display in the model prompt."""
    lines = ["选项 0: PASS — 不出"]
    for opt in options:
        label = opt.get("label", "")
        label_str = f"[{label}] " if label else ""
        lines.append(
            f"选项 {opt['index']}: {label_str}"
            f"{opt['description']} → 剩{opt['remaining']}张"
        )
    return "\n".join(lines)


# ---- Internal helpers ----

def _make_option(cards: List[Card], combo: dict, desc: str) -> dict:
    return {
        "cards": cards,
        "combo_type": combo["type"],
        "rank": combo["rank"],
        "length": combo.get("length", 1),
        "wings": combo.get("wings", 0),
        "description": desc,
        "combo": combo,
    }


def _strategic_label(opt: dict) -> str:
    t = opt["combo_type"]
    if t == "rocket":
        return "火箭"
    if t == "bomb":
        return "炸弹"
    cards_out = len(opt["cards"])
    if cards_out >= 6:
        return "高效组合"
    if cards_out >= 4:
        return "多牌"
    if t == "single" and opt["rank"] <= 7:
        return "过渡"
    if t == "single" and opt["rank"] >= 15:
        return "顶牌"
    return ""


def _add_bombs_and_rocket(
    raw: List[dict], hand: List[Card], rc: Counter,
) -> None:
    """Add bomb and rocket options."""
    # Rocket
    if rc.get(16, 0) >= 1 and rc.get(17, 0) >= 1:
        cards = [c for c in hand if c.rank == 16][:1] + \
                [c for c in hand if c.rank == 17][:1]
        combo = detect_combo(cards)
        if combo:
            raw.append(_make_option(cards, combo, "火箭 小王+大王"))

    # Bombs (4 of a kind)
    for rank in sorted(rc.keys(), reverse=True):
        if rc[rank] >= 4 and rank <= 15:
            cards = [c for c in hand if c.rank == rank][:4]
            combo = detect_combo(cards)
            if combo:
                name = RANK_DISPLAY.get(rank, str(rank))
                raw.append(_make_option(cards, combo, f"炸弹 {name}{name}{name}{name}"))


def _add_leading_options(
    raw: List[dict], hand: List[Card], rc: Counter,
    ranks: List[int],
) -> None:
    """Generate all play options when leading (last_play is None)."""
    used_in_combos: List[Card] = []

    # 1. Four-two (四带二)
    for rank in ranks:
        if rc[rank] >= 4 and rank <= 15:
            quads = [c for c in hand if c.rank == rank][:4]
            singles = _pick_kickers(hand, quads, 2, as_pair=False)
            if singles:
                cards = quads + singles
                combo = detect_combo(cards)
                if combo:
                    name = RANK_DISPLAY.get(rank, str(rank))
                    raw.append(_make_option(cards, combo,
                        f"四带二 {name}{name}{name}{name}+{_kicker_desc(singles)}"))

    # 2. Airplanes (飞机)
    _add_airplanes(raw, hand, rc, ranks, used_in_combos)

    # 3. Consecutive pairs (连对)
    _add_consecutive_pairs(raw, hand, rc, ranks)

    # 4. Straights (顺子)
    _add_straights(raw, hand, rc, ranks)

    # 5. Triples with kickers
    triples_added = 0
    for rank in ranks:
        if rc[rank] >= 3 and rank <= 15 and triples_added < 3:
            trips = [c for c in hand if c.rank == rank][:3]
            name = RANK_DISPLAY.get(rank, str(rank))

            # Triple only
            combo = detect_combo(trips)
            if combo:
                raw.append(_make_option(trips[:], combo, f"三张 {name}{name}{name}"))

            # Triple + 1
            kicker = _pick_kickers(hand, trips, 1, as_pair=False)
            if kicker:
                cards = trips + kicker
                combo = detect_combo(cards)
                if combo:
                    raw.append(_make_option(cards, combo,
                        f"三带一 {name}{name}{name}+{_kicker_desc(kicker)}"))

            # Triple + 2 (pair kicker)
            kickers = _pick_kickers(hand, trips, 1, as_pair=True)
            if kickers:
                cards = trips + kickers
                combo = detect_combo(cards)
                if combo:
                    raw.append(_make_option(cards, combo,
                        f"三带二 {name}{name}{name}+{_kicker_desc(kickers)}"))
            triples_added += 1

    # 6. Pairs — show largest few
    pairs_added = 0
    for rank in ranks:
        if rc[rank] >= 2 and pairs_added < 4:
            cards = [c for c in hand if c.rank == rank][:2]
            combo = detect_combo(cards)
            if combo:
                name = RANK_DISPLAY.get(rank, str(rank))
                label = "最小对子" if pairs_added == 0 else ""
                raw.append(_make_option(cards, combo,
                    f"对子 {name}{name}{' (' + label + ')' if label else ''}"))
            pairs_added += 1

    # 7. Singles — show smallest (for probing) and largest
    singles_added = 0
    for rank in sorted(ranks):  # ascending = smallest first
        if singles_added < 3:
            cards = [c for c in hand if c.rank == rank][:1]
            combo = detect_combo(cards)
            if combo:
                name = RANK_DISPLAY.get(rank, str(rank))
                label = "最小单张" if singles_added == 0 else ""
                raw.append(_make_option(cards, combo,
                    f"单张 {name}{' (' + label + ')' if label else ''}"))
            singles_added += 1


def _add_beating_options(
    raw: List[dict], hand: List[Card], rc: Counter,
    ranks: List[int], last_play: dict,
) -> None:
    """Generate only plays that can beat *last_play*."""
    lt = last_play["type"]
    lr = last_play["rank"]
    ll = last_play.get("length", 1)
    lw = last_play.get("wings", 0)

    # Bombs and rocket were already added in _add_bombs_and_rocket
    # (they always beat everything, so they're always valid)

    # Same-type, higher-rank matches
    if lt == "single":
        for rank in ranks:
            if rank > lr:
                cards = [c for c in hand if c.rank == rank][:1]
                combo = detect_combo(cards)
                if combo:
                    name = RANK_DISPLAY.get(rank, str(rank))
                    raw.append(_make_option(cards, combo, f"单张 {name}"))

    elif lt == "pair":
        for rank in ranks:
            if rank > lr and rc[rank] >= 2:
                cards = [c for c in hand if c.rank == rank][:2]
                combo = detect_combo(cards)
                if combo:
                    name = RANK_DISPLAY.get(rank, str(rank))
                    raw.append(_make_option(cards, combo, f"对子 {name}{name}"))

    elif lt in ("triple", "triple_one", "triple_two"):
        for rank in ranks:
            if rank > lr and rc[rank] >= 3:
                trips = [c for c in hand if c.rank == rank][:3]
                name = RANK_DISPLAY.get(rank, str(rank))
                if lt == "triple":
                    combo = detect_combo(trips)
                    if combo:
                        raw.append(_make_option(trips[:], combo,
                            f"三张 {name}{name}{name}"))
                elif lt == "triple_one":
                    kicker = _pick_kickers(hand, trips, 1, as_pair=False)
                    if kicker:
                        cards = trips + kicker
                        combo = detect_combo(cards)
                        if combo:
                            raw.append(_make_option(cards, combo,
                                f"三带一 {name}{name}{name}+{_kicker_desc(kicker)}"))
                elif lt == "triple_two":
                    kickers = _pick_kickers(hand, trips, 1, as_pair=True)
                    if kickers:
                        cards = trips + kickers
                        combo = detect_combo(cards)
                        if combo:
                            raw.append(_make_option(cards, combo,
                                f"三带二 {name}{name}{name}+{_kicker_desc(kickers)}"))

    elif lt == "straight":
        _add_beating_straights(raw, hand, rc, ranks, lr, ll)

    elif lt == "consecutive_pairs":
        _add_beating_consecutive_pairs(raw, hand, rc, ranks, lr, ll)

    elif lt == "airplane":
        _add_beating_airplanes(raw, hand, rc, ranks, lr, ll, lw)

    elif lt == "four_two":
        for rank in ranks:
            if rank > lr and rc[rank] >= 4:
                quads = [c for c in hand if c.rank == rank][:4]
                kickers = _pick_kickers(hand, quads, 2, as_pair=False)
                if kickers:
                    cards = quads + kickers
                    combo = detect_combo(cards)
                    if combo:
                        name = RANK_DISPLAY.get(rank, str(rank))
                        raw.append(_make_option(cards, combo,
                            f"四带二 {name}{name}{name}{name}+{_kicker_desc(kickers)}"))


def _add_straights(
    raw: List[dict], hand: List[Card], rc: Counter,
    ranks: List[int],
) -> None:
    """Add straight options (5+ consecutive, rank <= 14)."""
    straight_ranks = [r for r in ranks if rc[r] >= 1 and r <= 14]
    straight_ranks.sort(reverse=True)
    if len(straight_ranks) < 5:
        return

    runs = _find_runs(straight_ranks, 5)
    for start, length in runs[:3]:  # top 3 longest
        cards = _collect_run_cards(hand, start, length, 1)
        combo = detect_combo(cards)
        if combo:
            s_name = RANK_DISPLAY.get(start, str(start))
            e_name = RANK_DISPLAY.get(start - length + 1, str(start - length + 1))
            raw.append(_make_option(cards, combo,
                f"{length}顺子 {s_name}-{e_name}"))


def _add_consecutive_pairs(
    raw: List[dict], hand: List[Card], rc: Counter,
    ranks: List[int],
) -> None:
    """Add consecutive pair options (3+ consecutive pairs, rank <= 14)."""
    cp_ranks = [r for r in ranks if rc[r] >= 2 and r <= 14]
    cp_ranks.sort(reverse=True)
    if len(cp_ranks) < 3:
        return

    runs = _find_runs(cp_ranks, 3)
    for start, length in runs[:2]:
        cards = _collect_run_cards(hand, start, length, 2)
        combo = detect_combo(cards)
        if combo:
            s_name = RANK_DISPLAY.get(start, str(start))
            raw.append(_make_option(cards, combo,
                f"{length}连对 {s_name}对起"))


def _add_airplanes(
    raw: List[dict], hand: List[Card], rc: Counter,
    ranks: List[int], _used: List[Card],
) -> None:
    """Add airplane options (2+ consecutive triples, rank <= 14)."""
    ap_ranks = [r for r in ranks if rc[r] >= 3 and r <= 14]
    ap_ranks.sort(reverse=True)
    if len(ap_ranks) < 2:
        return

    runs = _find_runs(ap_ranks, 2)
    for start, length in runs[:2]:
        triples = _collect_run_cards(hand, start, length, 3)
        desc_prefix = f"{length}飞机 {RANK_DISPLAY.get(start, str(start))}起"

        # Airplane only (no wings)
        combo = detect_combo(triples)
        if combo:
            raw.append(_make_option(triples[:], combo, desc_prefix))

        # Airplane + 1 wing each
        singles = _pick_kickers(hand, triples, length, as_pair=False)
        if singles:
            cards = triples + singles
            combo = detect_combo(cards)
            if combo:
                raw.append(_make_option(cards, combo, f"{desc_prefix}+{length}单"))

        # Airplane + 2 wings each
        pairs = _pick_kickers(hand, triples, length, as_pair=True)
        if pairs:
            cards = triples + pairs
            combo = detect_combo(cards)
            if combo:
                raw.append(_make_option(cards, combo, f"{desc_prefix}+{length}对"))


def _add_beating_straights(
    raw: List[dict], hand: List[Card], rc: Counter,
    ranks: List[int], lr: int, ll: int,
) -> None:
    """Add straights that beat the given straight."""
    straight_ranks = [r for r in ranks if rc[r] >= 1 and r <= 14]
    straight_ranks.sort(reverse=True)

    runs = _find_runs(straight_ranks, ll)
    for start, length in runs:
        if start > lr:
            cards = _collect_run_cards(hand, start, ll, 1)
            combo = detect_combo(cards)
            if combo:
                raw.append(_make_option(cards, combo,
                    f"{ll}顺子 {RANK_DISPLAY.get(start, str(start))}起"))


def _add_beating_consecutive_pairs(
    raw: List[dict], hand: List[Card], rc: Counter,
    ranks: List[int], lr: int, ll: int,
) -> None:
    """Add consecutive pairs that beat the given one."""
    cp_ranks = [r for r in ranks if rc[r] >= 2 and r <= 14]
    cp_ranks.sort(reverse=True)

    runs = _find_runs(cp_ranks, ll)
    for start, length in runs:
        if start > lr:
            cards = _collect_run_cards(hand, start, ll, 2)
            combo = detect_combo(cards)
            if combo:
                raw.append(_make_option(cards, combo,
                    f"{ll}连对 {RANK_DISPLAY.get(start, str(start))}起"))


def _add_beating_airplanes(
    raw: List[dict], hand: List[Card], rc: Counter,
    ranks: List[int], lr: int, ll: int, lw: int,
) -> None:
    """Add airplanes that beat the given one."""
    ap_ranks = [r for r in ranks if rc[r] >= 3 and r <= 14]
    ap_ranks.sort(reverse=True)

    runs = _find_runs(ap_ranks, ll)
    for start, length in runs:
        if start > lr:
            triples = _collect_run_cards(hand, start, ll, 3)
            prefix = f"{ll}飞机 {RANK_DISPLAY.get(start, str(start))}起"

            if lw == 0:
                combo = detect_combo(triples)
                if combo:
                    raw.append(_make_option(triples[:], combo, prefix))
            elif lw == 1:
                singles = _pick_kickers(hand, triples, ll, as_pair=False)
                if singles:
                    cards = triples + singles
                    combo = detect_combo(cards)
                    if combo:
                        raw.append(_make_option(cards, combo, f"{prefix}+{ll}单"))
            elif lw == 2:
                pairs = _pick_kickers(hand, triples, ll, as_pair=True)
                if pairs:
                    cards = triples + pairs
                    combo = detect_combo(cards)
                    if combo:
                        raw.append(_make_option(cards, combo, f"{prefix}+{ll}对"))


# ---- Low-level helpers ----

def _find_runs(sorted_ranks: List[int], min_len: int) -> List[tuple]:
    """Find consecutive runs of length >= min_len in descending-sorted ranks.
    Returns list of (start_rank, length), longest first.
    """
    if not sorted_ranks:
        return []
    runs = []
    cur_start = sorted_ranks[0]
    cur_len = 1
    for i in range(1, len(sorted_ranks)):
        if sorted_ranks[i] == sorted_ranks[i - 1] - 1:
            cur_len += 1
        else:
            if cur_len >= min_len:
                runs.append((cur_start, cur_len))
            cur_start = sorted_ranks[i]
            cur_len = 1
    if cur_len >= min_len:
        runs.append((cur_start, cur_len))
    runs.sort(key=lambda x: (-x[1], -x[0]))  # longest first, then highest
    return runs


def _collect_run_cards(
    hand: List[Card], start_rank: int, length: int,
    count_per: int,
) -> List[Card]:
    """Collect *count_per* cards for each rank in the run [start, start-length+1]."""
    result = []
    for rank in range(start_rank, start_rank - length, -1):
        cards_of_rank = [c for c in hand if c.rank == rank]
        result.extend(cards_of_rank[:count_per])
    return result


def _pick_kickers(
    hand: List[Card], used: List[Card], count: int,
    as_pair: bool = False,
) -> List[Card]:
    """Pick *count* smallest-rank unused cards as kickers.
    If *as_pair*, each kicker must be a pair (2 cards of same rank).
    Returns empty list if not enough cards available.
    """
    available = [c for c in sort_hand(hand)
                 if c not in used and not c.is_joker]
    if as_pair:
        # Need *count* distinct ranks with >= 2 each
        ac = Counter(c.rank for c in available)
        rank_order = sorted(ac.keys())  # ascending = smallest first
        picked = []
        for rank in rank_order:
            if ac[rank] >= 2:
                cards = [c for c in available if c.rank == rank][:2]
                picked.extend(cards)
                if len(picked) >= count * 2:
                    return picked[:count * 2]
        return []
    else:
        # Need *count* distinct singles
        seen_ranks = set()
        picked = []
        for c in sort_hand(available):  # ascending = smallest first
            if c.rank not in seen_ranks:
                seen_ranks.add(c.rank)
                picked.append(c)
                if len(picked) >= count:
                    return picked
        return []


def _kicker_desc(cards: List[Card]) -> str:
    """Compact description of kicker cards."""
    if not cards:
        return ""
    return " ".join(RANK_DISPLAY.get(c.rank, "?") for c in cards[:3])
