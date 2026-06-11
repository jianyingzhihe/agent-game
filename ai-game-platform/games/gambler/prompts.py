"""Prompt templates for the Gambler game."""

SYSTEM_PROMPT = """You are a gambler in a high-stakes competition. Each round you face a critical choice:

WORK — Earn a fixed daily wage. Safe and guaranteed.
GAMBLE — Risk your wealth. Win and multiply assets; lose and lose big.

Your goal is to finish with the MOST assets among all players. Think carefully about expected value, risk, and your position on the leaderboard."""

RESPONSE_FORMAT = """
RESPONSE FORMAT — Reply with exactly these lines:
REASON: <your reasoning — expected value calculation, risk assessment, leaderboard strategy>
CHOICE: WORK or GAMBLE
"""


def decision_prompt(
    player_name: str,
    assets: float,
    daily_wage: float,
    win_probability: float,
    win_multiplier: float,
    loss_multiplier: float,
    round_num: int,
    max_rounds: int,
    leaderboard: str,
    my_history: str,
    loan_balance: float = 0.0,
    loan_repay_remaining: int = 0,
    sick: bool = False,
    hunger_streak: int = 0,
    food_cost: float = 5,
    spent_food: float = 0,
    spent_loan: float = 0,
    spent_medical: float = 0,
) -> str:
    """Build the decision prompt for a player's turn."""

    gamble_ev = assets * (win_probability * win_multiplier + (1 - win_probability) * loss_multiplier)
    work_ev = assets + daily_wage

    lines = [
        f"## Round {round_num} / {max_rounds}",
        f"Player: {player_name}",
        "",
        "### Your Status",
        f"Current assets: ${assets:,.2f}",
    ]

    # ---- Spending breakdown for this round ----
    spent_items = []
    if spent_food > 0:
        spent_items.append(f"Food: -${spent_food:,.2f}")
    if spent_loan > 0:
        spent_items.append(f"Loan repayment: -${spent_loan:,.2f}")
    if spent_medical > 0:
        spent_items.append(f"Medical bill: -${spent_medical:,.2f}")
    if spent_items:
        lines.append(f"This round's spending: {' | '.join(spent_items)}")
    elif spent_food == 0 and hunger_streak > 0:
        lines.append(f"This round: Could NOT afford food (${food_cost:,.2f}) — went HUNGRY")
    else:
        lines.append(f"This round's spending: Food -${food_cost:,.2f}")

    # Hunger warning
    if hunger_streak >= 2:
        lines.append(f"!!! You have gone {hunger_streak} days without food. If you miss ONE more day, you STARVE TO DEATH !!!")
    elif hunger_streak >= 1:
        lines.append(f"Warning: You went hungry yesterday ({hunger_streak} day streak). 3 consecutive hungry days = DEATH.")

    # Illness / loan status
    if sick and loan_balance <= 0:
        lines.append("You were SICK this round and paid the medical bill from your assets.")
    if loan_balance > 0:
        lines.extend([
            f"!!! You have an OUTSTANDING LOAN of ${loan_balance:,.2f} !!!",
            f"    Remaining installments: {loan_repay_remaining}",
            f"    One installment (${loan_balance / max(loan_repay_remaining, 1):,.2f}) is auto-deducted each round before your decision.",
        ])

    lines.extend([
        "",
        "### Game Parameters",
        f"Daily food cost: ${food_cost:,.2f} (auto-deducted each round; 3 consecutive missed days = DEATH)",
        f"Daily wage (WORK): ${daily_wage:,.2f}",
        f"Win probability (GAMBLE): {win_probability:.0%}",
        f"Win multiplier (GAMBLE): {win_multiplier}x  → assets become ${assets * win_multiplier:,.2f}",
        f"Loss multiplier (GAMBLE): {loss_multiplier}x  → assets become ${assets * loss_multiplier:,.2f}",
        "",
        "### Expected Value Comparison",
        f"EV of WORK:    ${work_ev:,.2f}  (guaranteed)",
        f"EV of GAMBLE:  ${gamble_ev:,.2f}  (risky)",
        "",
        "### Leaderboard",
        leaderboard,
    ])

    if my_history:
        lines.extend([
            "",
            "### Your History",
            my_history,
        ])

    lines.extend([
        "",
        "Your choice. WORK or GAMBLE?",
        RESPONSE_FORMAT,
    ])

    return "\n".join(lines)
