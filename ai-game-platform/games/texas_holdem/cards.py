"""Card deck, dealing, and hand evaluation for Texas Hold'em."""

import random
from collections import Counter
from enum import IntEnum
from itertools import combinations
from typing import List, Optional, Tuple


class Suit(IntEnum):
    CLUBS = 0
    DIAMONDS = 1
    HEARTS = 2
    SPADES = 3


class Rank(IntEnum):
    TWO = 2; THREE = 3; FOUR = 4; FIVE = 5; SIX = 6
    SEVEN = 7; EIGHT = 8; NINE = 9; TEN = 10
    JACK = 11; QUEEN = 12; KING = 13; ACE = 14


RANK_NAMES = {
    2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8",
    9: "9", 10: "10", 11: "J", 12: "Q", 13: "K", 14: "A",
}
SUIT_SYMBOLS = {0: "♣", 1: "♦", 2: "♥", 3: "♠"}


class Card:
    def __init__(self, rank: int, suit: int):
        self.rank = rank
        self.suit = suit

    def __repr__(self):
        return f"{RANK_NAMES[self.rank]}{SUIT_SYMBOLS[self.suit]}"

    def __eq__(self, other):
        return self.rank == other.rank and self.suit == other.suit

    def __hash__(self):
        return hash((self.rank, self.suit))


class Deck:
    def __init__(self):
        self.cards = [Card(r, s) for r in range(2, 15) for s in range(4)]
        self.shuffle()

    def shuffle(self):
        random.shuffle(self.cards)

    def deal(self, n: int = 1) -> List[Card]:
        return [self.cards.pop() for _ in range(n)]


# ---- Hand Evaluation ----

HAND_RANKS = {
    "high_card": 0, "pair": 1, "two_pair": 2, "three_kind": 3,
    "straight": 4, "flush": 5, "full_house": 6, "four_kind": 7,
    "straight_flush": 8, "royal_flush": 9,
}


def evaluate_hand(hole: List[Card], community: List[Card]) -> Tuple[int, str, List[int]]:
    """Evaluate the best 5-card hand from hole + community cards.

    Returns: (hand_rank_value, hand_name, kickers_for_comparison)
    """
    all_cards = hole + community
    best_rank = -1
    best_name = ""
    best_kickers = []

    for combo in combinations(all_cards, 5):
        rank, name, kickers = _eval_five(combo)
        if rank > best_rank or (rank == best_rank and kickers > best_kickers):
            best_rank, best_name, best_kickers = rank, name, kickers

    return best_rank, best_name, best_kickers


def _eval_five(cards: Tuple[Card, ...]) -> Tuple[int, str, List[int]]:
    ranks = sorted([c.rank for c in cards], reverse=True)
    suits = [c.suit for c in cards]
    is_flush = len(set(suits)) == 1
    is_straight = _is_straight(ranks)
    is_wheel = (ranks == [14, 5, 4, 3, 2])  # A-2-3-4-5

    if is_straight and is_flush:
        if is_wheel:
            return HAND_RANKS["straight_flush"], "Straight Flush", [5]
        if ranks[0] == 14 and ranks[1] == 13:
            return HAND_RANKS["royal_flush"], "Royal Flush", [14]
        return HAND_RANKS["straight_flush"], "Straight Flush", [ranks[0]]

    rank_counts = Counter(ranks)
    count_vals = sorted(rank_counts.values(), reverse=True)
    # Sort by count desc then rank desc
    sorted_by_count = sorted(rank_counts.items(), key=lambda x: (x[1], x[0]), reverse=True)

    if count_vals == [4, 1]:
        quad = sorted_by_count[0][0]
        kicker = sorted_by_count[1][0]
        return HAND_RANKS["four_kind"], "Four of a Kind", [quad, kicker]

    if count_vals == [3, 2]:
        trips = sorted_by_count[0][0]
        pair = sorted_by_count[1][0]
        return HAND_RANKS["full_house"], "Full House", [trips, pair]

    if is_flush:
        return HAND_RANKS["flush"], "Flush", ranks

    if is_straight:
        return HAND_RANKS["straight"], "Straight", [5 if is_wheel else ranks[0]]

    if count_vals == [3, 1, 1]:
        trips = sorted_by_count[0][0]
        kickers = [sorted_by_count[1][0], sorted_by_count[2][0]]
        return HAND_RANKS["three_kind"], "Three of a Kind", [trips] + kickers

    if count_vals == [2, 2, 1]:
        high_pair = max(sorted_by_count[0][0], sorted_by_count[1][0])
        low_pair = min(sorted_by_count[0][0], sorted_by_count[1][0])
        kicker = sorted_by_count[2][0]
        return HAND_RANKS["two_pair"], "Two Pair", [high_pair, low_pair, kicker]

    if count_vals == [2, 1, 1, 1]:
        pair = sorted_by_count[0][0]
        kickers = [sorted_by_count[1][0], sorted_by_count[2][0], sorted_by_count[3][0]]
        return HAND_RANKS["pair"], "Pair", [pair] + kickers

    return HAND_RANKS["high_card"], "High Card", ranks


def _is_straight(ranks: List[int]) -> bool:
    """Check if sorted ranks form a straight (including A-2-3-4-5)."""
    if ranks == [14, 5, 4, 3, 2]:
        return True
    return all(ranks[i] - ranks[i+1] == 1 for i in range(4))


def hand_description(rank: int, name: str) -> str:
    return name
