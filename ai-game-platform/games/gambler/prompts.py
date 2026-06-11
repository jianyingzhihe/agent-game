"""Prompt templates for the Gambler game."""

SYSTEM_PROMPT = """You are a gambler in a high-stakes life simulation. Your goal is NOT just to make the most money — it's to live the happiest, healthiest life possible.

=== ECONOMY ===
- You start with $50.
- Daily wage (WORK): $10. This is safe and guaranteed.
- Daily food cost: $5 (deducted AFTER your decision each round).
- Net from working: $5/day after food.

=== GAMBLE ===
- 30% chance to WIN: assets multiplied by 3.0x.
- 70% chance to LOSE: assets multiplied by 0.3x (you keep 30%).
- All gamblers in the same round share the same luck (same random roll).
- Winning gives a small SAN boost (excitement). Losing hits SAN hard (despair).

=== STUDY (self-improvement) ===
- Pay tuition, then train for 3 rounds with ZERO income. Food ($5/day) still costs.
- After completion, your daily wage increases by $10 (linear, stackable).
- Tuition adjusts so total investment stays ~$90 each time (payback ~9 rounds).
- STUDY costs SAN when you start AND every round (mental strain). Completion restores SAN.
- WARNING: If you go hungry during study, all progress is CANCELLED.
- While studying, you are LOCKED — no decisions, no income, only food deducted.
- If you choose STUDY but can't afford it, you fall back to WORK.

=== MEDICAL DISASTER ===
- At a RANDOM round between round 10 and round (max-5), ALL players get sick simultaneously.
- This happens EXACTLY ONCE per game. After it strikes, you are safe.
- Medical bill: $100 per person. Paying it costs SAN. Taking a loan costs MUCH MORE SAN.
- Loan terms: 20% interest, repaid over 20 rounds (auto-deducted).
- Having a loan also costs SAN every round (debt stress). Paying it off grants a SAN bonus.

=== HUNGER ===
- If you can't afford the $5 food cost: you go HUNGRY that day, losing SAN and HP.
- 3 consecutive hungry days = STARVATION DEATH (eliminated).
- Consecutive hunger days hurt MORE — day 2+ penalties are higher than day 1.
- Hunger during study cancels your study progress.

=== LIFE QUALITY SYSTEM — This is the CORE ===

SAN (Sanity) = Mental state. Affects your decisions, stress, and happiness.
HP (Health) = Physical state. Affects your work ability, disease resistance, and survival.

SAN thresholds:
  SAN >= 80: Happy    — no penalties, earn bonus happiness points
  SAN 50-79: Stable   — normal
  SAN 30-49: Anxious  — gamble losses hurt more, study costs more SAN
  SAN 1-29:  Breaking — cannot start study, high risk of insanity
  SAN = 0:   INSANITY (eliminated)

HP thresholds:
  HP >= 80:  Healthy  — no penalties, immune to minor illness, earn bonus happiness
  HP 50-79:  Normal   — normal
  HP 30-49:  Weak     — work income reduced 20%, study may stall
  HP 1-29:   Critical — high minor illness risk, work income -50%, cannot start study
  HP = 0:    DEATH (eliminated)

How SAN decreases:
  - Going hungry: -15 SAN (day 1), -20 SAN (day 2+)
  - GAMBLE loss: -14 SAN (despair)
  - Working 3+ consecutive rounds without break: -3 SAN/round (fatigue)
  - Starting STUDY: -5 SAN, then -4 SAN each study round
  - Carrying loan debt: -2 SAN/round
  - Medical disaster (can pay): -10 SAN
  - Medical disaster (can't pay, take loan): -25 SAN
  - Minor illness: -15 SAN

How SAN increases:
  - BUY_GOODS: +20 SAN (only +10 if SAN already >= 80)
  - REST: +8 SAN (free, no income)
  - GAMBLE win: +4 SAN
  - Completing STUDY: +10 SAN
  - Paying off loan: +10 SAN

How HP decreases:
  - Going hungry: -10 HP (day 1), -15 HP (day 2+)
  - Working 3+ consecutive rounds without break: -2 HP/round (fatigue)
  - STUDY: -2 HP each study round

How HP increases:
  - BUY_MEDICINE: +30 HP (only +15 if HP already >= 80)
  - REST: +8 HP (free, no income)

=== MINOR ILLNESS ===
- If HP < 30: chance of illness each round. Lower HP = higher chance.
- Illness costs $20 and loses 15 SAN.
- BUY_MEDICINE grants immunity from minor illness for that round.

=== WORK FATIGUE ===
- Working 1-2 rounds in a row: no penalty.
- Working 3+ rounds in a row without a break: -3 SAN, -2 HP per round.
- Taking BUY_GOODS, BUY_MEDICINE, REST, STUDY, or GAMBLE resets your work streak.

=== TURN FLOW (each round, in order) ===
1. YOU choose: WORK, GAMBLE, STUDY, BUY_GOODS, BUY_MEDICINE, or REST
2. Food cost ($5) deducted — if can't pay, go hungry
3. Loan installment (if any) auto-deducted
4. Medical disaster (if it strikes this round) applied to ALL players
5. Self-care effects applied (BUY_GOODS/BUY_MEDICINE/REST restore SAN/HP)
6. Minor illness check (HP < 30 = chance of illness)
7. Study progress advances (if studying)
8. Happiness points accumulated

=== HAPPINESS SCORING (this determines the WINNER) ===

Every round you survive, you earn life points:
  +10 base (just for being alive)
  +SAN/25 (mental well-being)
  +HP/25 (physical well-being)
  +min(4, log(assets)) (economic security, logarithmic)
  -8 if hungry today
  -3 if carrying debt

Final score = life_points + wealth_score + SAN*0.8 + HP*1.0 - loan*0.5 - hunger_days*10 - illnesses*8

The winner is the player with the HIGHEST happiness score — NOT necessarily the richest.
A player with moderate wealth but excellent SAN/HP and no debt can beat a rich but miserable player."""

RESPONSE_FORMAT = """
RESPONSE FORMAT — Reply with exactly these lines:
REASON: <your reasoning — consider SAN/HP, fatigue, debt, happiness score, not just money>
CHOICE: WORK or GAMBLE or STUDY or BUY_GOODS or BUY_MEDICINE or REST
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
    loan_next: float = 0.0,
    wage_bonus: float = 0.0,
    studying_remaining: int = 0,
    study_cost: float = 45,
    study_duration: int = 3,
    disaster_warning: bool = False,
    san: float = 100.0,
    hp: float = 100.0,
    san_status: str = "stable",
    hp_status: str = "normal",
    consecutive_work: int = 0,
    consecutive_gamble: int = 0,
    work_fatigue_threshold: int = 3,
    san_hunger_penalty: float = 15.0,
    hp_hunger_penalty: float = 10.0,
    minor_illness_threshold: float = 30.0,
    goods_cost: float = 8.0,
    goods_san_restore: float = 20.0,
    goods_high_san_penalty: float = 0.5,
    medicine_cost: float = 15.0,
    medicine_hp_restore: float = 30.0,
    medicine_high_hp_penalty: float = 0.5,
    rest_san_restore: float = 8.0,
    rest_hp_restore: float = 8.0,
    life_points: float = 0.0,
) -> str:
    """Build the decision prompt for a player's turn."""

    effective_wage = daily_wage + wage_bonus
    gamble_ev = assets * (win_probability * win_multiplier + (1 - win_probability) * loss_multiplier)
    work_ev = assets + effective_wage
    can_afford_study = assets >= study_cost
    food_reserve = study_duration * food_cost
    can_afford_goods = assets >= goods_cost
    can_afford_medicine = assets >= medicine_cost

    # Upcoming known deductions
    upcoming_total = food_cost + loan_next

    lines = [
        f"## Round {round_num} / {max_rounds}",
        f"Player: {player_name}",
        "",
        "### Turn Flow (your decision is STEP 1)",
        "",
        "  1. YOU choose NOW: WORK, GAMBLE, STUDY, BUY_GOODS, BUY_MEDICINE, or REST",
        "  2. Food cost (${:.0f}) deducted — if can't pay → HUNGRY".format(food_cost),
    ]
    if loan_next > 0:
        lines.append(f"  3. Loan repayment (${loan_next:,.2f}) auto-deducted")
    else:
        lines.append("  3. Loan repayment (none)")
    if disaster_warning:
        lines.append("  4. Medical disaster MAY strike (unknown round, $100)")
    else:
        lines.append("  4. Medical disaster (already happened)")
    lines.extend([
        "  5. Self-care effects (BUY_GOODS/BUY_MEDICINE/REST restore SAN/HP)",
        "  6. Minor illness check (if HP < threshold)",
        "  7. Study progress advances (if studying)",
        "  8. Happiness points accumulated",
        "",
        f"  → You have ${assets:,.2f} NOW. After your choice, ${upcoming_total:,.2f} will be deducted (food + loan).",
        "",
        "### Your Status",
        f"Assets: ${assets:,.2f}",
        f"{san_status.upper()}  SAN: {san:.0f}/100  |  {hp_status.upper()}  HP: {hp:.0f}/100",
    ])

    # ---- SAN warnings ----
    if san <= 30:
        lines.append(f"!!! SANITY CRITICAL ({san:.0f}) !!! At 0 you go INSANE (eliminated). You CANNOT start study.")
        lines.append(f"    BUY_GOODS costs ${goods_cost:.0f} → +{goods_san_restore:.0f} SAN. REST is free → +{rest_san_restore:.0f} SAN.")
    elif san <= 50:
        lines.append(f"Warning: SAN is low ({san:.0f}) — anxious. Gamble losses hurt more, study costs more.")

    # ---- HP warnings ----
    if hp <= minor_illness_threshold:
        chance_pct = (minor_illness_threshold - hp) / minor_illness_threshold * 100
        lines.append(f"!!! HP CRITICAL ({hp:.0f}) !!! ~{chance_pct:.0f}% chance of minor illness ($20, SAN-15) this round.")
        lines.append(f"    BUY_MEDICINE costs ${medicine_cost:.0f} → +{medicine_hp_restore:.0f} HP + blocks illness.")
        lines.append(f"    You CANNOT start study while HP is critical.")
    elif hp <= 50:
        lines.append(f"Warning: HP is low ({hp:.0f}) — weak. Work income may be reduced.")

    # ---- Work fatigue ----
    if consecutive_work >= work_fatigue_threshold:
        lines.append(f"!!! WORK FATIGUE: {consecutive_work} consecutive work rounds! You are losing SAN/HP each round.")
        lines.append(f"    Take a break: BUY_GOODS, BUY_MEDICINE, REST, STUDY, or GAMBLE to reset.")
    elif consecutive_work > 0:
        lines.append(f"Consecutive work: {consecutive_work} rounds (fatigue starts at {work_fatigue_threshold}).")

    # ---- Gambling streak ----
    if consecutive_gamble >= 2:
        lines.append(f"Consecutive gambling: {consecutive_gamble} rounds — extra SAN penalty per round.")

    # ---- Hunger warning ----
    if hunger_streak >= 2:
        lines.append(f"!!! HUNGER STREAK: {hunger_streak}/3 !!! One more hungry day = STARVATION DEATH. Must afford ${food_cost:.0f} for food!")
    elif hunger_streak >= 1:
        lines.append(f"Warning: Hungry yesterday ({hunger_streak}/3). Need ${food_cost:.0f} for food this round.")

    # ---- Study status ----
    if studying_remaining > 0:
        lines.append(f"Currently STUDYING: {studying_remaining} round(s) remaining. No income, still pay ${food_cost:.0f}/day food.")
        lines.append(f"  → If you go hungry during study, ALL progress is LOST.")
    if wage_bonus > 0:
        lines.append(f"Wage upgraded: +${wage_bonus:,.0f}/day bonus. Your WORK earns ${effective_wage:,.0f}/day.")

    # ---- Loan status ----
    if loan_balance > 0:
        installment = loan_balance / max(loan_repay_remaining, 1)
        lines.extend([
            f"!!! MEDICAL LOAN: ${loan_balance:,.2f} ({loan_repay_remaining} payments of ${installment:,.2f} left)",
            f"    Debt stress: -{2:.0f} SAN/round while carrying loan.",
        ])
    if sick and loan_balance <= 0:
        lines.append("Recovered from illness — bill paid.")

    # ---- Disaster warning ----
    if disaster_warning:
        lines.append("")
        lines.append("!!! MEDICAL DISASTER is coming (round 10-25). Save $20-30 or prepare for loan stress. !!!")

    lines.extend([
        "",
        "### Game Parameters",
        f"Food cost: ${food_cost:.0f}/day (deducted AFTER your choice. 3 missed = DEATH)",
        f"WORK: earn ${effective_wage:.0f} (guaranteed)" + (f" (base ${daily_wage:.0f} + ${wage_bonus:.0f} bonus)" if wage_bonus > 0 else ""),
        f"      Warning: {work_fatigue_threshold}+ consecutive work rounds = SAN/HP fatigue",
        f"GAMBLE: {win_probability:.0%} win → ${assets * win_multiplier:,.2f} (SAN +4) | {(1 - win_probability):.0%} lose → ${assets * loss_multiplier:,.2f} (SAN -14)",
        f"        Consecutive gambling = extra SAN penalty",
        "",
    ])

    # ---- STUDY section ----
    if studying_remaining > 0:
        lines.append(f"STUDY: Already studying ({studying_remaining} rounds left). Cannot take another course.")
    elif san <= 30:
        lines.append(f"STUDY: BLOCKED — SAN too low ({san:.0f}). Must restore SAN first.")
    elif hp <= minor_illness_threshold:
        lines.append(f"STUDY: BLOCKED — HP too low ({hp:.0f}). Must restore HP first.")
    elif can_afford_study:
        total_study_cost = study_cost + study_duration * food_cost + study_duration * effective_wage
        lines.extend([
            f"STUDY: You CAN afford this (have ${assets:,.0f}, need ${study_cost + food_reserve:,.0f} for tuition + food).",
            f"  → Pay ${study_cost:,.0f} now. Keep ${food_reserve:,.0f} for food during study.",
            f"  → {study_duration} rounds ZERO income. Lost wages: ${effective_wage * study_duration:,.0f}.",
            f"  → Total cost: ~${total_study_cost:,.0f}. After: wage ${effective_wage:,.0f} → ${effective_wage + daily_wage:,.0f}/day.",
            f"  → SAN: -5 start, -4/round during. Completion: SAN +10.",
            f"  → Payback: ~{total_study_cost / daily_wage:.0f} rounds.",
        ])
    else:
        shortfall = study_cost + food_reserve - assets
        lines.extend([
            f"STUDY: Cannot afford (need ${study_cost + food_reserve:,.0f}, have ${assets:,.0f}, short ${shortfall:,.0f}).",
            f"  → Falls back to WORK if chosen.",
        ])

    # ---- BUY_GOODS ----
    if can_afford_goods:
        actual_restore = goods_san_restore
        if san >= 80:
            actual_restore = goods_san_restore * goods_high_san_penalty
        new_san = min(100.0, san + actual_restore)
        lines.append(f"BUY_GOODS: ${goods_cost:.0f} → SAN +{actual_restore:.0f} ({san:.0f} → {new_san:.0f}) | Resets work fatigue")
    else:
        lines.append(f"BUY_GOODS: Cannot afford (need ${goods_cost:.0f}). Falls back to WORK.")

    # ---- BUY_MEDICINE ----
    if can_afford_medicine:
        actual_restore = medicine_hp_restore
        if hp >= 80:
            actual_restore = medicine_hp_restore * medicine_high_hp_penalty
        new_hp = min(100.0, hp + actual_restore)
        immune_note = " + IMMUNE to minor illness this round" if hp < minor_illness_threshold else ""
        lines.append(f"BUY_MEDICINE: ${medicine_cost:.0f} → HP +{actual_restore:.0f} ({hp:.0f} → {new_hp:.0f}) | Resets work fatigue{immune_note}")
    else:
        lines.append(f"BUY_MEDICINE: Cannot afford (need ${medicine_cost:.0f}). Falls back to WORK.")

    # ---- REST ----
    lines.append(f"REST: FREE → SAN +{rest_san_restore:.0f}, HP +{rest_hp_restore:.0f} | No income | Resets all fatigue")

    lines.extend([
        "",
        "### Expected Value Comparison",
        f"WORK:        +${effective_wage:.0f} guaranteed  |  Fatigue risk after {work_fatigue_threshold} consecutive rounds",
        f"GAMBLE:      EV ${gamble_ev:,.2f}  (swing ${assets * win_multiplier:,.0f} or ${assets * loss_multiplier:,.0f})  |  SAN: +4 win / -14 lose",
    ])
    if can_afford_study and san > 30 and hp > minor_illness_threshold:
        lines.append(f"STUDY:       ${study_cost:,.0f} now, {study_duration}rd lock → wage +${daily_wage:,.0f}/day forever  |  SAN: -5 start, -4/rd, +10 finish")
    else:
        lines.append(f"STUDY:       N/A (cannot afford or SAN/HP too low)")

    lines.extend([
        f"BUY_GOODS:   ${goods_cost:.0f} → SAN +{goods_san_restore:.0f}" + (" (affordable)" if can_afford_goods else " (CANNOT AFFORD)"),
        f"BUY_MEDICINE: ${medicine_cost:.0f} → HP +{medicine_hp_restore:.0f}" + (" (affordable)" if can_afford_medicine else " (CANNOT AFFORD)"),
        f"REST:        FREE → SAN +{rest_san_restore:.0f}, HP +{rest_hp_restore:.0f}",
        "",
        f"Your life points so far: {life_points:,.1f}  (winner = highest final happiness, NOT just most money)",
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
        "REMEMBER: The winner is decided by HAPPINESS SCORE, not just assets.",
        "A healthy, happy player with moderate wealth can beat a rich but miserable one.",
        "",
        f"Your choice. WORK, GAMBLE, STUDY, BUY_GOODS, BUY_MEDICINE, or REST?",
        RESPONSE_FORMAT,
    ])

    return "\n".join(lines)
