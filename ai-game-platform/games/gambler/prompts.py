"""Prompt templates for the Gambler game."""

SYSTEM_PROMPT = """You are a gambler in a high-stakes competition. Here are the rules:

=== ECONOMY ===
- You start with $50.
- Daily wage (WORK): $10. This is safe and guaranteed.
- Daily food cost: $5 (auto-deducted each round before your choice).
- Net from working: $5/day after food.

=== GAMBLE ===
- 30% chance to WIN: assets multiplied by 3.0x.
- 70% chance to LOSE: assets multiplied by 0.3x (you keep 30%).
- All gamblers in the same round share the same luck (same random roll).

=== STUDY (self-improvement) ===
- Pay tuition, then train for 3 rounds with ZERO income. Food ($5/day) still costs.
- After completion, your daily wage increases by $10 (linear, stackable).
- Tuition adjusts so total investment stays ~$90 each time (payback ~9 rounds):
  - 1st study (wage $10): tuition $45. Total ~$90. Payback ~9 rounds.
  - 2nd study (wage $20): tuition $15. Total ~$90. Payback ~9 rounds.
  - 3rd study (wage $30): tuition $5.  Total ~$105. Payback ~11 rounds.
- WARNING: If you go hungry during study, all progress is CANCELLED.
- While studying, you are LOCKED — no decisions, no income, only food deducted.
- If you choose STUDY but can't afford it, you fall back to WORK.

=== MEDICAL DISASTER ===
- At a RANDOM round between round 10 and round (max-5), ALL players get sick simultaneously.
- This happens EXACTLY ONCE per game. After it strikes, you are safe — no more disasters.
- Medical bill: $100 per person.
- If you have $100+: pay directly from assets, no loan.
- If you have less than $100: all your assets go to the bill, and the shortfall becomes a LOAN.
- Loan terms: 20% interest, repaid over 20 rounds (auto-deducted before your choice each round).
- Example: You have $30 when disaster hits. Shortfall $70 → loan $84, repays $4.20/round.
  Food ($5) + loan ($4.20) = $9.20/day. Wage $10 - $9.20 = $0.80/day buffer. Survivable.
- Example: You have $0 when disaster hits. Shortfall $100 → loan $120, repays $6.00/round.
  Food ($5) + loan ($6.00) = $11.00/day. Wage $10 - $11.00 = -$1.00/day. You WILL die.
- MORAL: Save at least $20-30 before the disaster, or you won't survive the loan.

=== HUNGER ===
- If you can't afford the $5 food cost: you go HUNGRY that day.
- Going hungry costs SAN (sanity) and HP (health) — see below.
- 3 consecutive hungry days = STARVATION DEATH (eliminated).
- Hunger during study also cancels your study progress.

=== SANITY (SAN) & HEALTH (HP) ===
- You start with SAN 100 and HP 100. Both are vital — losing either to 0 eliminates you.
- Each day you go HUNGRY: lose SAN-15 and HP-10.
- SAN = 0 → INSANITY (eliminated). HP = 0 → DEATH (eliminated).
- HP below 30: you may suffer a MINOR ILLNESS each round, costing $20 and losing SAN-20.
- SAN and HP do NOT recover on their own — you must buy goods/medicine.

=== BUY GOODS (SAN recovery) ===
- Cost: $5. Restores SAN +20 (max 100). No other benefit.
- Use when your SAN is dangerously low to avoid insanity.
- Cannot afford? Falls back to WORK instead.

=== BUY MEDICINE (HP recovery) ===
- Cost: $15. Restores HP +30 (max 100). No other benefit.
- Use when your HP is dangerously low to avoid minor illness or death.
- Cannot afford? Falls back to WORK instead.

=== TURN FLOW (each round, in order) ===
1. Loan installment (if any) auto-deducted
2. Medical disaster (if it strikes this round) applied to ALL players
3. Food cost ($5) deducted; if can't pay → hungry → lose SAN/HP
3b. Minor illness check (if HP < 30, pay $20 and lose SAN-20)
4. Study progress advances (if studying)
5. YOU choose: WORK, GAMBLE, STUDY, BUY_GOODS, or BUY_MEDICINE

Your goal: finish with the MOST assets among all players. Plan ahead for the inevitable disaster, manage your SAN and HP, weigh risk vs. reward, and watch the leaderboard."""

RESPONSE_FORMAT = """
RESPONSE FORMAT — Reply with exactly these lines:
REASON: <your reasoning — expected value calculation, risk assessment, SAN/HP status, leaderboard strategy>
CHOICE: WORK or GAMBLE or STUDY or BUY_GOODS or BUY_MEDICINE
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
    wage_bonus: float = 0.0,
    studying_remaining: int = 0,
    study_cost: float = 45,
    study_duration: int = 3,
    disaster_warning: bool = False,
    san: float = 100.0,
    hp: float = 100.0,
    san_hunger_penalty: float = 15.0,
    hp_hunger_penalty: float = 10.0,
    minor_illness_threshold: float = 30.0,
    goods_cost: float = 5.0,
    goods_san_restore: float = 20.0,
    medicine_cost: float = 15.0,
    medicine_hp_restore: float = 30.0,
) -> str:
    """Build the decision prompt for a player's turn."""

    effective_wage = daily_wage + wage_bonus
    gamble_ev = assets * (win_probability * win_multiplier + (1 - win_probability) * loss_multiplier)
    work_ev = assets + effective_wage
    can_afford_study = assets >= study_cost
    food_reserve = study_duration * food_cost  # cash needed for food during study
    can_afford_goods = assets >= goods_cost
    can_afford_medicine = assets >= medicine_cost

    lines = [
        f"## Round {round_num} / {max_rounds}",
        f"Player: {player_name}",
        "",
        "### Turn Flow (happens BEFORE your decision)",
        "",
        "  1. Loan installment (if any) is auto-deducted",
        "  2. Medical disaster (if it strikes this round) is applied",
        "  3. Daily food cost is deducted (if can't pay → HUNGRY, lose SAN/HP)",
        "  3b. Minor illness check (if HP < threshold)",
        "  4. Study progress advances (if currently studying)",
        "  5. YOU make your choice: WORK, GAMBLE, STUDY, BUY_GOODS, BUY_MEDICINE",
        "",
        f"  → Everything above has ALREADY happened. Your current assets: ${assets:,.2f}",
        "",
        "### Your Status",
        f"Current assets: ${assets:,.2f}",
        f"SAN (Sanity): {san:.0f}/100  |  HP (Health): {hp:.0f}/100",
    ]

    # ---- SAN/HP warnings ----
    if san <= 30:
        lines.append(f"!!! SANITY CRITICAL ({san:.0f}/100) !!! At 0 you go INSANE and are eliminated. BUY_GOODS costs ${goods_cost:.0f} and restores +{goods_san_restore:.0f} SAN.")
    elif san <= 50:
        lines.append(f"Warning: SAN is low ({san:.0f}/100). Going hungry costs -{san_hunger_penalty:.0f} SAN. BUY_GOODS costs ${goods_cost:.0f} → +{goods_san_restore:.0f} SAN.")

    if hp <= minor_illness_threshold + 10:
        if hp <= minor_illness_threshold:
            lines.append(f"!!! HP CRITICAL ({hp:.0f}/100) !!! Below {minor_illness_threshold:.0f} threshold — you may suffer minor illness ($20, SAN-20). BUY_MEDICINE costs ${medicine_cost:.0f} and restores +{medicine_hp_restore:.0f} HP.")
        else:
            lines.append(f"Warning: HP is low ({hp:.0f}/100). If it drops below {minor_illness_threshold:.0f}, you may get a minor illness. BUY_MEDICINE: ${medicine_cost:.0f} → +{medicine_hp_restore:.0f} HP.")
    elif hp <= 50:
        lines.append(f"Warning: HP is moderate ({hp:.0f}/100). Going hungry costs -{hp_hunger_penalty:.0f} HP.")

    # ---- Spending breakdown for this round ----
    spent_items = []
    if spent_food > 0:
        spent_items.append(f"Food: -${spent_food:,.2f}")
    if spent_loan > 0:
        spent_items.append(f"Loan repayment: -${spent_loan:,.2f}")
    if spent_medical > 0:
        spent_items.append(f"Medical bill: -${spent_medical:,.2f}")
    if spent_items:
        lines.append(f"This round's deductions: {' | '.join(spent_items)}")
    elif spent_food == 0 and hunger_streak > 0:
        lines.append(f"This round: Could NOT afford food (${food_cost:,.2f}) — went HUNGRY (streak: {hunger_streak}/3, 3 = DEATH)")
    else:
        lines.append(f"This round's deductions: Food -${food_cost:,.2f}")

    # ---- Disaster warning ----
    if disaster_warning:
        lines.append("")
        lines.append("!!! MEDICAL DISASTER is coming — ALL players will be charged $100 each at an unknown round. Stay liquid. !!!")

    # ---- Hunger warning ----
    if hunger_streak >= 2:
        lines.append(f"!!! You have gone {hunger_streak} days without food. If you miss ONE more day, you STARVE TO DEATH !!!")
    elif hunger_streak >= 1:
        lines.append(f"Warning: You went hungry yesterday ({hunger_streak} day streak). 3 consecutive hungry days = DEATH.")

    # ---- Study status ----
    if studying_remaining > 0:
        lines.append(f"You are currently STUDYING: {studying_remaining} round(s) remaining. You have NO income and still pay ${food_cost:.0f}/day food.")
        lines.append(f"  → If you go hungry during study, ALL progress is LOST.")
    if wage_bonus > 0:
        lines.append(f"Wage upgraded: +${wage_bonus:,.0f}/day (completed {int(wage_bonus / daily_wage)} course(s)). Your WORK earns ${effective_wage:,.0f}/day.")

    # ---- Illness / loan status ----
    if sick and loan_balance <= 0:
        lines.append(f"You were SICK this round! Paid ${spent_medical:,.0f} medical bill from assets.")
    if loan_balance > 0:
        lines.extend([
            f"!!! OUTSTANDING MEDICAL LOAN: ${loan_balance:,.2f} !!!",
            f"    Remaining installments: {loan_repay_remaining}",
            f"    Each round, ${loan_balance / max(loan_repay_remaining, 1):,.2f} is auto-deducted before your choice.",
        ])

    lines.extend([
        "",
        "### Game Parameters",
        f"Food cost: ${food_cost:.0f}/day (auto-deducted each round. 3 consecutive missed = DEATH)",
        f"WORK: earn ${effective_wage:.0f} (guaranteed, safe)" + (f" (base ${daily_wage:.0f} + ${wage_bonus:.0f} bonus)" if wage_bonus > 0 else ""),
        f"GAMBLE: {win_probability:.0%} chance of {win_multiplier}x → ${assets * win_multiplier:,.2f} | {(1 - win_probability):.0%} chance of {loss_multiplier}x → ${assets * loss_multiplier:,.2f}",
        "",
    ])

    # ---- STUDY section with affordability ----
    if studying_remaining > 0:
        lines.append(f"STUDY: You are already studying ({studying_remaining} rounds left). You CANNOT take another course.")
    elif can_afford_study:
        total_study_cost = study_cost + study_duration * food_cost + study_duration * effective_wage
        lines.extend([
            f"STUDY: You CAN afford this (have ${assets:,.0f}, need ${study_cost + food_reserve:,.0f} for tuition + food).",
            f"  → Pay ${study_cost:,.0f} now. Keep ${food_reserve:,.0f} for food during study.",
            f"  → Then {study_duration} rounds with ZERO income. Lost wages: ${effective_wage * study_duration:,.0f}.",
            f"  → Total real cost: ${total_study_cost:,.0f}. After completion: wage ${effective_wage:,.0f} → ${effective_wage + daily_wage:,.0f}/day.",
            f"  → Payback: ~{total_study_cost / daily_wage:.0f} rounds (at the +${daily_wage:,.0f} gain).",
        ])
    else:
        shortfall = study_cost + food_reserve - assets
        lines.extend([
            f"STUDY: You CANNOT afford this! Need ${study_cost + food_reserve:,.0f} (tuition + 3-day food), have ${assets:,.0f} (short ${shortfall:,.0f}).",
            f"  → If you choose STUDY anyway, you will fall back to WORK instead.",
        ])

    # ---- BUY_GOODS section ----
    if can_afford_goods:
        new_san = min(100.0, san + goods_san_restore)
        lines.append(f"BUY_GOODS: Cost ${goods_cost:.0f}. SAN: {san:.0f} → {new_san:.0f}/100 (+{goods_san_restore:.0f}). No other benefit.")
    else:
        lines.append(f"BUY_GOODS: Cannot afford (need ${goods_cost:.0f}). Falls back to WORK.")

    # ---- BUY_MEDICINE section ----
    if can_afford_medicine:
        new_hp = min(100.0, hp + medicine_hp_restore)
        lines.append(f"BUY_MEDICINE: Cost ${medicine_cost:.0f}. HP: {hp:.0f} → {new_hp:.0f}/100 (+{medicine_hp_restore:.0f}). No other benefit.")
    else:
        lines.append(f"BUY_MEDICINE: Cannot afford (need ${medicine_cost:.0f}). Falls back to WORK.")

    # ---- Minor illness info ----
    if hp < minor_illness_threshold:
        lines.append(f"!!! HP ({hp:.0f}) is below {minor_illness_threshold:.0f}: you may suffer MINOR ILLNESS each round ($20 cost, SAN-20).")

    lines.extend([
        "",
        "### Expected Value Comparison",
        f"WORK:        guaranteed ${work_ev:,.2f}  (+${effective_wage:.0f})",
        f"GAMBLE:      expected ${gamble_ev:,.2f}  (swing: ${assets * win_multiplier:,.0f} or ${assets * loss_multiplier:,.0f})",
        f"STUDY:       invest ${study_cost:,.0f}, {study_duration}rd no income → wage +${daily_wage:,.0f}/day forever" if can_afford_study else
        f"STUDY:       N/A (cannot afford ${study_cost:,.0f} + ${food_reserve:,.0f} food = ${study_cost + food_reserve:,.0f})",
        f"BUY_GOODS:   spend ${goods_cost:.0f} → SAN +{goods_san_restore:.0f}" + (" (affordable)" if can_afford_goods else " (CANNOT AFFORD)"),
        f"BUY_MEDICINE: spend ${medicine_cost:.0f} → HP +{medicine_hp_restore:.0f}" + (" (affordable)" if can_afford_medicine else " (CANNOT AFFORD)"),
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
        "Your choice. WORK, GAMBLE, STUDY, BUY_GOODS, or BUY_MEDICINE?",
        RESPONSE_FORMAT,
    ])

    return "\n".join(lines)
