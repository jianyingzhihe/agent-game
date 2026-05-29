"""Quick verification of hand evaluation."""
from cards import Card, Deck, evaluate_hand, RANK_NAMES

def c(rank, suit=0):
    return Card(rank, suit)

def t(name, hole, community, expected_name):
    _, hand_name, kickers = evaluate_hand(hole, community)
    status = "✓" if hand_name == expected_name else f"✗ (got {hand_name})"
    cards_str = " ".join(str(x) for x in hole) + " | " + " ".join(str(x) for x in community)
    print(f"  {status:6s} {cards_str:50s} → {hand_name} kickers={kickers}")

print("Hand evaluation tests:\n")

# Royal Flush
t("Royal", [c(14,0), c(13,0)], [c(12,0), c(11,0), c(10,0), c(5,1), c(3,2)], "Royal Flush")

# Straight Flush
t("SF", [c(9,0), c(8,0)], [c(7,0), c(6,0), c(5,0), c(2,1), c(3,2)], "Straight Flush")

# Wheel Straight Flush (A-2-3-4-5 suited) - was buggy
t("Wheel SF", [c(14,0), c(2,0)], [c(3,0), c(4,0), c(5,0), c(9,1), c(10,2)], "Straight Flush")

# Four of a Kind
t("Quads", [c(10,0), c(10,1)], [c(10,2), c(10,3), c(14,0), c(5,1), c(3,2)], "Four of a Kind")

# Full House
t("Boat", [c(14,0), c(14,1)], [c(13,0), c(13,1), c(13,2), c(5,1), c(3,2)], "Full House")

# Flush
t("Flush", [c(14,0), c(5,0)], [c(10,0), c(7,0), c(3,0), c(13,1), c(2,2)], "Flush")

# Straight
t("Straight", [c(10,0), c(9,1)], [c(8,0), c(7,2), c(6,3), c(2,1), c(3,2)], "Straight")

# Wheel Straight (A-2-3-4-5) - was buggy
t("Wheel", [c(14,0), c(2,1)], [c(3,0), c(4,2), c(5,3), c(9,1), c(10,2)], "Straight")

# Three of a Kind
t("Trips", [c(8,0), c(8,1)], [c(8,2), c(14,0), c(5,1), c(3,2), c(2,3)], "Three of a Kind")

# Two Pair
t("TwoPair", [c(14,0), c(14,1)], [c(13,0), c(13,1), c(5,2), c(3,2), c(2,3)], "Two Pair")

# One Pair
t("Pair", [c(14,0), c(14,1)], [c(13,0), c(5,1), c(3,2), c(2,3), c(7,3)], "Pair")

# High Card
t("HighCard", [c(14,0), c(5,1)], [c(13,0), c(10,1), c(7,2), c(3,3), c(2,1)], "High Card")

# ---- Comparison tests ----
print("\nComparison tests:\n")

# Wheel (5-high) should lose to 6-high straight
r1, _, k1 = evaluate_hand([c(14,0), c(2,1)], [c(3,0), c(4,2), c(5,3), c(9,1), c(10,2)])
r2, _, k2 = evaluate_hand([c(6,0), c(5,1)], [c(4,0), c(3,2), c(2,3), c(9,1), c(10,2)])
print(f"  Wheel A-5 ({k1}) vs 6-high ({k2}): {'✓ 6-high wins' if k2 > k1 else '✗ WRONG'}")

# Higher flush wins
r1, _, k1 = evaluate_hand([c(14,0), c(5,0)], [c(10,0), c(7,0), c(3,0), c(13,1), c(2,2)])
r2, _, k2 = evaluate_hand([c(13,0), c(12,0)], [c(10,0), c(7,0), c(3,0), c(14,1), c(2,2)])
print(f"  A-high flush ({k1}) vs K-high flush ({k2}): {'✓ A-high wins' if k1 > k2 else '✗ WRONG'}")

# Full house: higher trips wins
r1, _, k1 = evaluate_hand([c(14,0), c(14,1)], [c(13,0), c(13,1), c(13,2), c(5,1), c(3,2)])
r2, _, k2 = evaluate_hand([c(14,0), c(14,1)], [c(14,2), c(5,0), c(5,1), c(13,2), c(3,3)])
print(f"  AAAKK vs KKKAA: {'✓ AAA wins' if k1 > k2 else '✗ WRONG'}")

print("\nDone.")
