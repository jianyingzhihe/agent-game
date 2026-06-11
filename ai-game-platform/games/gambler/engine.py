"""Gambler game engine — each round players choose WORK, GAMBLE, STUDY, BUY_GOODS, BUY_MEDICINE, or REST.

Shared-randomness arena mode: one roll per round, so all gamblers
in round N face the same luck.  Writes ui_state.json for live viewer.
All players are queried concurrently within each round (ThreadPoolExecutor).

Turn order (per round):
  1. Player decisions (LLM query + immediate money movement)
  2. Food deduction (hunger / SAN+HP loss)
  3. Loan repayment
  4. Medical disaster (if triggered)
  5. Self-care effects (BUY_GOODS/BUY_MEDICINE/REST SAN+HP restoration)
  6. Minor illness check (probabilistic)
  7. Study advancement
  8. Life points accumulation
"""

import json
import math
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

from core.logger import GameLogger
from core.utils import Colors, parse_keyword_response

from .player import GamblerPlayer
from .prompts import SYSTEM_PROMPT, decision_prompt

# Where the live viewer looks for state
_UI_STATE_FILE = Path(__file__).parent / "ui_state.json"


class GamblerEngine:
    """A gambling competition where AI agents manage money, sanity, and health."""

    def __init__(
        self,
        players: List[GamblerPlayer],
        config: Optional[dict] = None,
        logger: Optional[GameLogger] = None,
    ):
        for p in players:
            if not isinstance(p, GamblerPlayer):
                raise TypeError(f"All players must be GamblerPlayer, got {type(p).__name__}")

        if len(players) < 1:
            raise ValueError("Need at least 1 player")

        self.players = players
        self.config = config or {}
        self.logger = logger
        self.round = 0
        self.finished = False
        self.winner: Optional[str] = None

        # ---- Economy ----
        self.initial_assets = float(self.config.get("initial_assets", 50))
        self.daily_wage = float(self.config.get("daily_wage", 10))
        self.win_probability = float(self.config.get("win_probability", 0.3))
        self.win_multiplier = float(self.config.get("win_multiplier", 3.0))
        self.loss_multiplier = float(self.config.get("loss_multiplier", 0.3))
        self.max_rounds = int(self.config.get("max_rounds", 30))
        self.temperature = float(self.config.get("temperature", 0.7))
        self.food_cost = float(self.config.get("food_cost", 5))

        # ---- Medical Disaster ----
        self.illness_cost = float(self.config.get("illness_cost", 100))
        self.loan_interest_rate = float(self.config.get("loan_interest_rate", 0.2))
        self.loan_repay_rounds = int(self.config.get("loan_repay_rounds", 20))
        self._illness_triggered = False
        self._illness_round = random.randint(10, max(self.max_rounds - 5, 11))

        # ---- Study ----
        self.base_study_cost = float(self.config.get("base_study_cost", 45))
        self.study_duration = int(self.config.get("study_duration", 3))

        # ---- Sanity & Health ----
        self.initial_san = float(self.config.get("initial_san", 100))
        self.initial_hp = float(self.config.get("initial_hp", 100))
        self.san_hunger_penalty = float(self.config.get("san_hunger_penalty", 15))
        self.hp_hunger_penalty = float(self.config.get("hp_hunger_penalty", 10))
        self.san_hunger_streak_penalty = float(self.config.get("san_hunger_streak_penalty", 20))
        self.hp_hunger_streak_penalty = float(self.config.get("hp_hunger_streak_penalty", 15))

        # ---- Work Fatigue ----
        self.work_fatigue_threshold = int(self.config.get("work_fatigue_threshold", 3))
        self.work_fatigue_san_penalty = float(self.config.get("work_fatigue_san_penalty", 3))
        self.work_fatigue_hp_penalty = float(self.config.get("work_fatigue_hp_penalty", 2))

        # ---- Gamble Stress ----
        self.san_gamble_win_bonus = float(self.config.get("san_gamble_win_bonus", 4))
        self.san_gamble_loss_penalty = float(self.config.get("san_gamble_loss_penalty", 14))
        self.san_consecutive_gamble_penalty = float(self.config.get("san_consecutive_gamble_penalty", 3))

        # ---- Study Stress ----
        self.san_study_start_cost = float(self.config.get("san_study_start_cost", 5))
        self.san_study_round_penalty = float(self.config.get("san_study_round_penalty", 4))
        self.hp_study_round_penalty = float(self.config.get("hp_study_round_penalty", 2))
        self.san_study_complete_bonus = float(self.config.get("san_study_complete_bonus", 10))

        # ---- Debt Stress ----
        self.san_disaster_paid_loss = float(self.config.get("san_disaster_paid_loss", 10))
        self.san_disaster_loan_loss = float(self.config.get("san_disaster_loan_loss", 25))
        self.san_debt_round_penalty = float(self.config.get("san_debt_round_penalty", 2))
        self.san_loan_repaid_bonus = float(self.config.get("san_loan_repaid_bonus", 10))

        # ---- Minor Illness ----
        self.minor_illness_probabilistic = bool(self.config.get("minor_illness_probabilistic", True))
        self.minor_illness_hp_threshold = float(self.config.get("minor_illness_hp_threshold", 30))
        self.minor_illness_cost = float(self.config.get("minor_illness_cost", 20))
        self.minor_illness_san_loss = float(self.config.get("minor_illness_san_loss", 15))

        # ---- Self-Care ----
        self.goods_cost = float(self.config.get("goods_cost", 8))
        self.goods_san_restore = float(self.config.get("goods_san_restore", 20))
        self.goods_high_san_penalty = float(self.config.get("goods_high_san_penalty", 0.5))
        self.medicine_cost = float(self.config.get("medicine_cost", 15))
        self.medicine_hp_restore = float(self.config.get("medicine_hp_restore", 30))
        self.medicine_high_hp_penalty = float(self.config.get("medicine_high_hp_penalty", 0.5))

        # ---- REST ----
        self.rest_san_restore = float(self.config.get("rest_san_restore", 8))
        self.rest_hp_restore = float(self.config.get("rest_hp_restore", 8))

        # ---- Happiness Scoring ----
        self.happiness_wealth_log_base = float(self.config.get("happiness_wealth_log_base", 301))
        self.happiness_base_per_round = float(self.config.get("happiness_base_per_round", 10))

        # Shared-randomness arena mode
        seed = self.config.get("random_seed")
        if seed is not None:
            random.seed(int(seed))
        else:
            random.seed()
        self._shared_rolls = [random.random() for _ in range(self.max_rounds)]
        self._state_file = Path(self.config.get("state_file", str(_UI_STATE_FILE)))

        # Per-round snapshot history (for viewer)
        self._snapshots: List[dict] = []

    def _player_study_cost(self, player: GamblerPlayer) -> float:
        """Tuition adjusts so total cost stays ~$90 (payback ~9 rounds).
        Higher wage — more lost wages — lower tuition to compensate."""
        effective_wage = self.daily_wage + player.wage_bonus
        tuition = 75.0 - 3.0 * effective_wage  # target: total cost ~$90
        return max(5.0, tuition)  # minimum $5 tuition

    def _auto_choice(self, player: GamblerPlayer) -> dict | None:
        """Return a forced choice dict if the player has NO viable path, else None.

        Only auto-decides when ALL choices (WORK, GAMBLE win, GAMBLE lose)
        lead to unavoidable death. Otherwise the model decides.
        """
        effective_wage = self.daily_wage + player.wage_bonus
        food_next = self.food_cost
        loan_next = (player.loan_balance / max(player.loan_repay_remaining, 1)
                     if player.loan_balance > 0 else 0.0)
        survival_cost = food_next + loan_next

        # Truly doomed: hunger=2 and even max possible income can't save them
        if player.hunger_streak >= 2:
            after_work = player.assets + effective_wage
            after_gamble_win = player.assets * self.win_multiplier

            if after_work < survival_cost and after_gamble_win < survival_cost:
                return {
                    "choice": "WORK",
                    "reason": "AUTO: hunger 2 — no choice prevents starvation. All paths = death."
                }

        # SAN or HP will hit 0 regardless
        if player.hunger_streak >= 2:
            if player.san <= self.san_hunger_penalty and player.hp <= self.hp_hunger_penalty:
                after_work = player.assets + effective_wage
                if after_work < food_next:
                    return {
                        "choice": "WORK",
                        "reason": "AUTO: will go insane/die from hunger regardless of choice."
                    }

        return None

    # ---- Query helper ----

    def _query(self, player: GamblerPlayer, prompt: str) -> tuple[dict, float]:
        t0 = time.time()

        if self.logger:
            self.logger.log_prompt(player.name, f"round_{self.round}", 0, SYSTEM_PROMPT, prompt)

        _, response = player.chat(SYSTEM_PROMPT, prompt, temperature=self.temperature)
        parsed = parse_keyword_response(response)
        elapsed = time.time() - t0

        if self.logger:
            self.logger.log_response(
                player.name, f"round_{self.round}", 0, response, parsed, 0,
                elapsed * 1000
            )

        return parsed, elapsed

    # ---- Game flow ----

    def _leaderboard(self) -> str:
        ranked = sorted(self.players, key=lambda p: p.assets, reverse=True)
        lines = []
        for i, p in enumerate(ranked, 1):
            icon = {1: "1st", 2: "2nd", 3: "3rd"}.get(i, f"{i}th")
            tags = []
            if p.starved:
                tags.append("STARVED")
            elif p.insane:
                tags.append("INSANE")
            elif p.bankrupt:
                tags.append("BANKRUPT")
            elif p.studying_remaining > 0:
                tags.append(f"STUDYING {p.studying_remaining}r")
            if tags:
                tag = f"  [{', '.join(tags)}]"
            else:
                tag = ""
            san_str = f" SAN:{p.san:.0f}({p.san_status})"
            hp_str = f" HP:{p.hp:.0f}({p.hp_status})"
            lines.append(f"  {icon}. {p.name}: ${p.assets:,.2f}{san_str}{hp_str}{tag}")
        return "\n".join(lines)

    def _player_history(self, player: GamblerPlayer) -> str:
        if not player.history:
            return "(no history yet)"
        lines = []
        for h in player.history[-8:]:
            icon = {"WIN": "WIN", "LOSE": "LOSE", "EARNED": "SAFE",
                    "GOODS_BOUGHT": "GOODS", "MEDICINE_BOUGHT": "MEDICINE",
                    "RESTED": "RESTED"}.get(h["result"], h["result"])
            lines.append(
                f"  Round {h['round']}: {h['choice']} → {icon} → ${h['assets_after']:,.2f}"
            )
        return "\n".join(lines)

    def _player_status(self, player: GamblerPlayer) -> str:
        """Generate a compact status summary for the decision prompt."""
        parts = [
            f"SAN: {player.san:.0f}/100 ({player.san_status})",
            f"HP: {player.hp:.0f}/100 ({player.hp_status})",
        ]
        if player.consecutive_work >= self.work_fatigue_threshold:
            parts.append(f"Work fatigue: {player.consecutive_work} rounds (penalty active)")
        elif player.consecutive_work > 0:
            parts.append(f"Consecutive work: {player.consecutive_work} rounds")
        if player.consecutive_gamble > 0:
            parts.append(f"Consecutive gamble: {player.consecutive_gamble} rounds")
        if player.loan_balance > 0:
            parts.append(f"Loan: ${player.loan_balance:,.2f} ({player.loan_repay_remaining}r left)")
        if player.hunger_streak > 0:
            parts.append(f"Hunger streak: {player.hunger_streak}/3")
        return " | ".join(parts)

    def setup(self) -> None:
        for p in self.players:
            p.assets = self.initial_assets
            p.initial_assets = self.initial_assets
            p.san = self.initial_san
            p.hp = self.initial_hp
            p.history = []
            p.gamble_count = 0
            p.work_count = 0
            p.gamble_wins = 0
            p.gamble_losses = 0
            p.goods_count = 0
            p.medicine_count = 0
            p.rest_count = 0
            p.study_count = 0
            p.bankrupt = False
            p.starved = False
            p.insane = False
            p.sick = False
            p.loan_balance = 0.0
            p.loan_repay_remaining = 0
            p.hunger_streak = 0
            p.wage_bonus = 0.0
            p.studying_remaining = 0
            p.minor_illness_count = 0
            # Life quality fields
            p.life_points = 0.0
            p.consecutive_work = 0
            p.consecutive_gamble = 0
            p.total_hunger_days = 0
            p.happy_rounds = 0
            p.medicine_immune = False
        self.round = 0
        self.finished = False
        self.winner = None
        self._illness_triggered = False
        self._snapshots = []

        if self.logger:
            self.logger.log_game_start(self.players)
            self.logger.set_config({
                "initial_assets": self.initial_assets,
                "daily_wage": self.daily_wage,
                "win_probability": self.win_probability,
                "win_multiplier": self.win_multiplier,
                "loss_multiplier": self.loss_multiplier,
                "max_rounds": self.max_rounds,
                "random_seed": self.config.get("random_seed"),
            })

        self._write_ui_state()

    # ===================================================================
    #  Main turn loop
    # ===================================================================

    def step(self) -> dict:
        """Execute one round. New order:
        1. Player decisions (LLM + money movement)
        2. Food deduction
        3. Loan repayment
        4. Medical disaster
        5. Self-care effects (BUY_GOODS/BUY_MEDICINE/REST SAN/HP restore)
        6. Minor illness check (probabilistic)
        7. Study advancement
        8. Life points accumulation
        """
        self.round += 1
        active = [p for p in self.players if not p.bankrupt]

        if not active:
            self.finished = True
            self._write_ui_state()
            return {"round": self.round, "error": "all_bankrupt"}

        round_result = {"round": self.round, "actions": [], "events": []}

        # Clear medicine_immune flags from previous rounds
        for p in active:
            p.medicine_immune = False

        # ================================================================
        #  Step 1: Player decisions (LLM queries + immediate money movement)
        # ================================================================

        # Split active players: those studying vs. those making decisions
        studying_players = [p for p in active if p.studying_remaining > 0]
        deciding_players = [p for p in active if p.studying_remaining <= 0]

        # Fast path: auto-decide for doomed players
        auto_results: dict[str, tuple[dict, float]] = {}
        need_api = []
        for player in deciding_players:
            forced = self._auto_choice(player)
            if forced:
                auto_results[player.name] = (forced, 0.0)
            else:
                need_api.append(player)

        # Shared roll for this round
        shared_roll = self._shared_rolls[self.round - 1]

        # Build prompts for players who need an API call
        order = list(need_api)
        random.shuffle(order)
        tasks = []
        for player in order:
            # Upcoming deductions the player should plan for
            loan_next = (player.loan_balance / max(player.loan_repay_remaining, 1)
                         if player.loan_balance > 0 else 0.0)
            prompt = decision_prompt(
                player_name=player.name,
                assets=player.assets,
                daily_wage=self.daily_wage,
                win_probability=self.win_probability,
                win_multiplier=self.win_multiplier,
                loss_multiplier=self.loss_multiplier,
                round_num=self.round,
                max_rounds=self.max_rounds,
                leaderboard=self._leaderboard(),
                my_history=self._player_history(player),
                loan_balance=player.loan_balance,
                loan_repay_remaining=player.loan_repay_remaining,
                sick=player.sick,
                hunger_streak=player.hunger_streak,
                food_cost=self.food_cost,
                loan_next=loan_next,
                wage_bonus=player.wage_bonus,
                studying_remaining=player.studying_remaining,
                study_cost=self._player_study_cost(player),
                study_duration=self.study_duration,
                disaster_warning=not self._illness_triggered,
                san=player.san,
                hp=player.hp,
                san_status=player.san_status,
                hp_status=player.hp_status,
                consecutive_work=player.consecutive_work,
                consecutive_gamble=player.consecutive_gamble,
                work_fatigue_threshold=self.work_fatigue_threshold,
                san_hunger_penalty=self.san_hunger_penalty,
                hp_hunger_penalty=self.hp_hunger_penalty,
                minor_illness_threshold=self.minor_illness_hp_threshold,
                goods_cost=self.goods_cost,
                goods_san_restore=self.goods_san_restore,
                goods_high_san_penalty=self.goods_high_san_penalty,
                medicine_cost=self.medicine_cost,
                medicine_hp_restore=self.medicine_hp_restore,
                medicine_high_hp_penalty=self.medicine_high_hp_penalty,
                rest_san_restore=self.rest_san_restore,
                rest_hp_restore=self.rest_hp_restore,
                life_points=player.life_points,
            )
            tasks.append((player, prompt))

        # Query all players concurrently
        round_t0 = time.time()
        results: dict[str, tuple[dict, float]] = dict(auto_results)
        if tasks:
            with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
                future_to_player = {
                    executor.submit(self._query, player, prompt): player.name
                    for player, prompt in tasks
                }
                for future in as_completed(future_to_player):
                    name = future_to_player[future]
                    try:
                        results[name] = future.result()
                    except Exception as e:
                        results[name] = ({"choice": "WORK", "reason": f"ERROR: {e}"}, 0.0)
        round_elapsed = time.time() - round_t0

        # Deferred self-care: record intentions, apply effects in step 5
        deferred_self_care: dict[str, str] = {}  # player_name -> "goods" | "medicine" | "rest"

        # Auto-record actions for studying players
        for player in studying_players:
            # Apply study round SAN/HP penalties
            player.san = max(0.0, player.san - self.san_study_round_penalty)
            player.hp = max(0.0, player.hp - self.hp_study_round_penalty)
            if player.san <= 0:
                player.insane = True
                player.bankrupt = True
            if player.hp <= 0:
                player.bankrupt = True

            player.history.append({
                "round": self.round,
                "choice": "STUDY",
                "result": f"STUDYING ({player.studying_remaining}r left)",
                "assets_after": player.assets,
            })
            round_result["actions"].append({
                "player": player.name,
                "choice": "STUDY",
                "result": f"STUDYING ({player.studying_remaining}r left)",
                "reason": "Auto-advancing study.",
                "assets_before": player.assets,
                "assets_after": player.assets,
                "elapsed": 0.0,
            })

        # Resolve outcomes for deciding players
        all_deciding = list(deciding_players)
        for player in all_deciding:
            parsed, elapsed = results.get(player.name, ({"choice": "WORK", "reason": ""}, 0.0))
            choice = parsed.get("choice", "WORK").strip().upper()
            reason = parsed.get("reason", "")

            assets_before = player.assets

            if "REST" in choice and "BUY_GOODS" not in choice and "BUY_MEDICINE" not in choice \
               and "STUDY" not in choice and "GAMBLE" not in choice and "WORK" not in choice:
                # REST: defer SAN/HP restore to step 5, no money movement, no income
                deferred_self_care[player.name] = "rest"
                player.history.append({
                    "round": self.round, "choice": "REST",
                    "result": "RESTED", "assets_after": player.assets,
                })
                round_result["actions"].append({
                    "player": player.name, "choice": "REST",
                    "result": "RESTED (SAN/HP restore in step 5)",
                    "reason": reason, "assets_before": assets_before,
                    "assets_after": player.assets, "elapsed": elapsed,
                })

            elif "BUY_GOODS" in choice:
                gresult = player.buy_goods(self.goods_cost, self.goods_san_restore,
                                           self.goods_high_san_penalty)
                if gresult["event"] == "goods_fail":
                    # Fall back to WORK
                    effective_wage = self.daily_wage + player.wage_bonus
                    new_assets = player.assets + effective_wage
                    result = "EARNED"
                    player.record(self.round, "WORK", result, new_assets)
                    reason = f"Wanted BUY_GOODS but can't afford. Fell back to WORK. {reason}"
                    # Apply work fatigue
                    self._apply_work_fatigue(player)
                    choice = "WORK"
                else:
                    new_assets = player.assets
                    result = "GOODS_BOUGHT"
                    player.history.append({
                        "round": self.round, "choice": "BUY_GOODS",
                        "result": result, "assets_after": new_assets,
                    })
                    player.assets = new_assets
                    if player.assets <= 0:
                        player.bankrupt = True
                    round_result["events"].append({
                        "type": "goods_bought",
                        "player": player.name,
                        "cost": self.goods_cost,
                        "san_restored": gresult["san_restored"],
                        "san": player.san,
                    })

            elif "BUY_MEDICINE" in choice:
                mresult = player.buy_medicine(self.medicine_cost, self.medicine_hp_restore,
                                              self.medicine_high_hp_penalty)
                if mresult["event"] == "medicine_fail":
                    effective_wage = self.daily_wage + player.wage_bonus
                    new_assets = player.assets + effective_wage
                    result = "EARNED"
                    player.record(self.round, "WORK", result, new_assets)
                    reason = f"Wanted BUY_MEDICINE but can't afford. Fell back to WORK. {reason}"
                    self._apply_work_fatigue(player)
                    choice = "WORK"
                else:
                    new_assets = player.assets
                    result = "MEDICINE_BOUGHT"
                    player.history.append({
                        "round": self.round, "choice": "BUY_MEDICINE",
                        "result": result, "assets_after": new_assets,
                    })
                    player.assets = new_assets
                    if player.assets <= 0:
                        player.bankrupt = True
                    round_result["events"].append({
                        "type": "medicine_bought",
                        "player": player.name,
                        "cost": self.medicine_cost,
                        "hp_restored": mresult["hp_restored"],
                        "hp": player.hp,
                    })

            elif "STUDY" in choice:
                if player.studying_remaining > 0:
                    effective_wage = self.daily_wage + player.wage_bonus
                    new_assets = player.assets + effective_wage
                    result = "EARNED"
                    player.record(self.round, "WORK", result, new_assets)
                    reason = f"Already studying, so WORK instead. {reason}"
                    self._apply_work_fatigue(player)
                    choice = "WORK"
                else:
                    sresult = player.start_study(self._player_study_cost(player), self.study_duration)
                    if sresult["event"] == "study_fail":
                        effective_wage = self.daily_wage + player.wage_bonus
                        new_assets = player.assets + effective_wage
                        result = "EARNED"
                        player.record(self.round, "WORK", result, new_assets)
                        reason = f"Wanted STUDY but can't afford. Fell back to WORK. {reason}"
                        self._apply_work_fatigue(player)
                        choice = "WORK"
                    else:
                        new_assets = player.assets
                        result = "STUDY_START"
                        player.history.append({
                            "round": self.round, "choice": "STUDY",
                            "result": result, "assets_after": new_assets,
                        })
                        player.assets = new_assets
                        if player.assets <= 0:
                            player.bankrupt = True
                        # Study start SAN penalty
                        player.san = max(0.0, player.san - self.san_study_start_cost)
                        if player.san <= 0:
                            player.insane = True
                            player.bankrupt = True
                        round_result["events"].append({
                            "type": "study_start",
                            "player": player.name,
                            "cost": sresult["cost"],
                            "duration": self.study_duration,
                        })

            elif "GAMBLE" in choice:
                if shared_roll < self.win_probability:
                    new_assets = player.assets * self.win_multiplier
                    result = "WIN"
                    player.san = min(100.0, player.san + self.san_gamble_win_bonus)
                else:
                    new_assets = player.assets * self.loss_multiplier
                    result = "LOSE"
                    player.san = max(0.0, player.san - self.san_gamble_loss_penalty)
                    if player.san <= 0:
                        player.insane = True
                        player.bankrupt = True
                # Consecutive gamble penalty
                if player.consecutive_gamble >= 2:
                    player.san = max(0.0, player.san - self.san_consecutive_gamble_penalty)
                    if player.san <= 0:
                        player.insane = True
                        player.bankrupt = True
                player.record(self.round, "GAMBLE", result, new_assets)
                # Reset fatigue counters are done inside record()

            else:  # Default: WORK
                effective_wage = self.daily_wage + player.wage_bonus
                new_assets = player.assets + effective_wage
                result = "EARNED"
                player.record(self.round, "WORK", result, new_assets)
                choice = "WORK"
                # Apply work fatigue
                self._apply_work_fatigue(player)

            # Record action for display
            round_result["actions"].append({
                "player": player.name,
                "choice": choice,
                "result": result,
                "reason": reason,
                "assets_before": assets_before,
                "assets_after": player.assets,
                "elapsed": elapsed,
            })

        # ================================================================
        #  Step 2: Food deduction
        # ================================================================
        for player in list(active):
            if player.bankrupt:
                continue
            # Progressive hunger penalties: day 2+ hits harder
            if player.hunger_streak >= 1:
                san_pen = self.san_hunger_streak_penalty
                hp_pen = self.hp_hunger_streak_penalty
            else:
                san_pen = self.san_hunger_penalty
                hp_pen = self.hp_hunger_penalty

            food_result = player.pay_food(self.food_cost, san_pen, hp_pen)
            ev_type = food_result["event"]
            if ev_type == "hungry":
                round_result["events"].append({
                    "type": "hungry",
                    "player": player.name,
                    "streak": food_result["streak"],
                    "san_lost": food_result.get("san_lost", 0),
                    "hp_lost": food_result.get("hp_lost", 0),
                })
            elif ev_type in ("starved", "insane", "hp_death"):
                round_result["events"].append({
                    "type": ev_type,
                    "player": player.name,
                    "streak": food_result.get("streak", 0),
                })
                if self.logger:
                    self.logger.log_event(f"round_{self.round}_{ev_type}", {
                        "player": player.name,
                    })

        # ================================================================
        #  Step 3: Loan repayment
        # ================================================================
        for player in list(active):
            if player.bankrupt:
                continue
            if player.loan_balance > 0:
                paid = player.repay_loan()
                if paid > 0:
                    round_result["events"].append({
                        "type": "loan_repay",
                        "player": player.name,
                        "paid": paid,
                        "remaining_balance": player.loan_balance,
                        "remaining_rounds": player.loan_repay_remaining,
                    })
                # Debt stress: penalty for carrying debt
                if player.loan_balance > 0:
                    player.san = max(0.0, player.san - self.san_debt_round_penalty)
                    if player.san <= 0:
                        player.insane = True
                        player.bankrupt = True
                else:
                    # Loan just paid off
                    player.san = min(100.0, player.san + self.san_loan_repaid_bonus)

        # ================================================================
        #  Step 4: Medical disaster
        # ================================================================
        if not self._illness_triggered and self.round == self._illness_round:
            self._illness_triggered = True
            for player in list(active):
                if player.bankrupt:
                    continue
                illness_result = player.apply_illness(
                    self.illness_cost, self.loan_interest_rate, self.loan_repay_rounds
                )
                illness_result["type"] = "illness"
                illness_result["player"] = player.name
                illness_result["round"] = self.round
                illness_result["cost"] = self.illness_cost
                round_result["events"].append(illness_result)

                # Disaster stress
                if illness_result["event"] == "illness_loan":
                    player.san = max(0.0, player.san - self.san_disaster_loan_loss)
                else:
                    player.san = max(0.0, player.san - self.san_disaster_paid_loss)
                if player.san <= 0:
                    player.insane = True
                    player.bankrupt = True

                if self.logger:
                    self.logger.log_event(f"round_{self.round}_illness_{player.name}", illness_result)

        # ================================================================
        #  Step 5: Self-care effects (SAN/HP restoration)
        # ================================================================
        # (BUY_GOODS/BUY_MEDICINE already applied in step 1; REST deferred)
        for player_name, care_type in deferred_self_care.items():
            player = next((p for p in active if p.name == player_name), None)
            if player is None or player.bankrupt:
                continue
            if care_type == "rest":
                r = player.rest(self.rest_san_restore, self.rest_hp_restore)
                round_result["events"].append({
                    "type": "rested",
                    "player": player.name,
                    "san_restored": r["san_restored"],
                    "hp_restored": r["hp_restored"],
                    "san": player.san,
                    "hp": player.hp,
                })

        # ================================================================
        #  Step 6: Minor illness check (probabilistic)
        # ================================================================
        for player in list(active):
            if player.bankrupt:
                continue
            roll = random.random()
            mi = player.check_minor_illness(
                self.minor_illness_hp_threshold,
                self.minor_illness_cost,
                self.minor_illness_san_loss,
                roll=roll,
                probabilistic=self.minor_illness_probabilistic,
            )
            if mi:
                mi["player"] = player.name
                mi["type"] = "minor_illness"
                mi["round"] = self.round
                round_result["events"].append(mi)

        # ================================================================
        #  Step 7: Study advancement
        # ================================================================
        for player in list(active):
            if player.bankrupt:
                continue
            if player.studying_remaining > 0:
                study_result = player.advance_study()
                if study_result["event"] == "study_complete":
                    player.san = min(100.0, player.san + self.san_study_complete_bonus)
                    round_result["events"].append({
                        "type": "study_complete",
                        "player": player.name,
                        "new_bonus": player.wage_bonus,
                        "new_wage": 10.0 + player.wage_bonus,
                    })

        # ================================================================
        #  Step 8: Life points accumulation
        # ================================================================
        for player in list(active):
            if player.bankrupt:
                continue
            self._accumulate_life_points(player)

        # Store round elapsed
        round_result["round_elapsed"] = round_elapsed

        # Refresh active list
        active = [p for p in active if not p.bankrupt]
        if not active:
            self.finished = True

        self._write_ui_state()
        return round_result

    # ===================================================================
    #  Life quality helpers
    # ===================================================================

    def _apply_work_fatigue(self, player: GamblerPlayer):
        """Apply fatigue penalties if player has been working too many consecutive rounds."""
        if player.consecutive_work >= self.work_fatigue_threshold:
            player.san = max(0.0, player.san - self.work_fatigue_san_penalty)
            player.hp = max(0.0, player.hp - self.work_fatigue_hp_penalty)
            if player.san <= 0:
                player.insane = True
                player.bankrupt = True
            if player.hp <= 0:
                player.bankrupt = True

    def _accumulate_life_points(self, player: GamblerPlayer):
        """Accumulate happiness score for one round."""
        # Base survival points
        player.life_points += self.happiness_base_per_round
        # SAN contribution
        player.life_points += player.san / 25.0
        # HP contribution
        player.life_points += player.hp / 25.0
        # Economic security (logarithmic, capped)
        player.life_points += min(4.0, math.log(max(player.assets, 0.0) + 1.0))
        # Hunger penalty
        if player.hunger_streak > 0:
            player.life_points -= 8.0
        # Debt penalty
        if player.loan_balance > 0:
            player.life_points -= 3.0
        # Track happy rounds
        if player.san >= 90:
            player.happy_rounds += 1

    def _compute_final_score(self, player: GamblerPlayer) -> float:
        """Compute the final happiness score for ranking."""
        if player.bankrupt or player.starved or player.insane or player.hp <= 0:
            return 0.0
        wealth_score = min(100.0, 100.0 * math.log(max(player.assets, 0.0) + 1.0)
                           / math.log(self.happiness_wealth_log_base))
        return (
            player.life_points
            + wealth_score
            + 0.8 * player.san
            + 1.0 * player.hp
            - 0.5 * player.loan_balance
            - 10.0 * player.total_hunger_days
            - 8.0 * player.minor_illness_count
        )

    def check_win(self) -> Optional[str]:
        if self.round >= self.max_rounds:
            # Winner = highest happiness score
            ranked = sorted(self.players, key=lambda p: self._compute_final_score(p), reverse=True)
            return ranked[0].name if ranked else None
        return None

    # ===================================================================
    #  UI state
    # ===================================================================

    def _build_ui_state(self) -> dict:
        return {
            "game_config": {
                "initial_assets": self.initial_assets,
                "daily_wage": self.daily_wage,
                "win_probability": self.win_probability,
                "win_multiplier": self.win_multiplier,
                "loss_multiplier": self.loss_multiplier,
                "max_rounds": self.max_rounds,
                "food_cost": self.food_cost,
                "illness_cost": self.illness_cost,
                "base_study_cost": self.base_study_cost,
                "study_duration": self.study_duration,
                "goods_cost": self.goods_cost,
                "medicine_cost": self.medicine_cost,
            },
            "engine_state": {
                "random_seed": self.config.get("random_seed"),
                "shared_rolls": self._shared_rolls,
                "illness_round": self._illness_round,
                "illness_triggered": self._illness_triggered,
            },
            "players": [
                {
                    "name": p.name,
                    "model_name": getattr(p.model, 'model_name', ''),
                    "current_assets": p.assets,
                    "initial_assets": p.initial_assets,
                    "bankrupt": p.bankrupt,
                    "starved": p.starved,
                    "insane": p.insane,
                    "hunger_streak": p.hunger_streak,
                    "work_count": p.work_count,
                    "gamble_count": p.gamble_count,
                    "gamble_wins": p.gamble_wins,
                    "gamble_losses": p.gamble_losses,
                    "goods_count": p.goods_count,
                    "medicine_count": p.medicine_count,
                    "rest_count": p.rest_count,
                    "sick": p.sick,
                    "loan_balance": p.loan_balance,
                    "loan_repay_remaining": p.loan_repay_remaining,
                    "wage_bonus": p.wage_bonus,
                    "studying_remaining": p.studying_remaining,
                    "study_count": p.study_count,
                    "san": p.san,
                    "hp": p.hp,
                    "san_status": p.san_status,
                    "hp_status": p.hp_status,
                    "minor_illness_count": p.minor_illness_count,
                    "life_points": p.life_points,
                    "consecutive_work": p.consecutive_work,
                    "consecutive_gamble": p.consecutive_gamble,
                    "total_hunger_days": p.total_hunger_days,
                    "happy_rounds": p.happy_rounds,
                    "final_score": self._compute_final_score(p),
                }
                for p in self.players
            ],
            "player_names": [p.name for p in self.players],
            "current_round": self.round,
            "finished": self.finished,
            "winner": self.winner,
            "trajectories_with_start": {
                p.name: [{"round": 0, "assets": p.initial_assets, "choice": "START", "result": ""}]
                + [dict(h) for h in p.history]
                for p in self.players
            },
        }

    def _write_ui_state(self):
        try:
            data = json.dumps(self._build_ui_state(), indent=2, ensure_ascii=False)
            tmp = str(self._state_file) + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(data)
            os.replace(tmp, str(self._state_file))
        except Exception:
            pass

    # ===================================================================
    #  Resume from saved state
    # ===================================================================

    @classmethod
    def resume(cls, players: List[GamblerPlayer], state: dict,
               logger: Optional[GameLogger] = None) -> "GamblerEngine":
        """Reconstruct engine from a prior _build_ui_state() dict."""
        gc = state.get("game_config", {})
        es = state.get("engine_state", {})
        merged_config = dict(gc)

        engine = cls(players, config=merged_config, logger=logger)
        engine.round = state.get("current_round", 0)
        engine.finished = state.get("finished", False)
        engine.winner = state.get("winner")
        engine._shared_rolls = es.get("shared_rolls", engine._shared_rolls)
        engine._illness_round = es.get("illness_round", engine._illness_round)
        engine._illness_triggered = es.get("illness_triggered", False)

        # Restore per-player state
        sp = {p["name"]: p for p in state.get("players", [])}
        for p in players:
            sd = sp.get(p.name, {})
            p.assets = sd.get("current_assets", p.assets)
            p.initial_assets = sd.get("initial_assets", p.initial_assets)
            p.san = sd.get("san", p.san)
            p.hp = sd.get("hp", p.hp)
            p.bankrupt = sd.get("bankrupt", False)
            p.starved = sd.get("starved", False)
            p.insane = sd.get("insane", False)
            p.sick = sd.get("sick", False)
            p.hunger_streak = sd.get("hunger_streak", 0)
            p.work_count = sd.get("work_count", 0)
            p.gamble_count = sd.get("gamble_count", 0)
            p.gamble_wins = sd.get("gamble_wins", 0)
            p.gamble_losses = sd.get("gamble_losses", 0)
            p.goods_count = sd.get("goods_count", 0)
            p.medicine_count = sd.get("medicine_count", 0)
            p.rest_count = sd.get("rest_count", 0)
            p.study_count = sd.get("study_count", 0)
            p.loan_balance = sd.get("loan_balance", 0.0)
            p.loan_repay_remaining = sd.get("loan_repay_remaining", 0)
            p.wage_bonus = sd.get("wage_bonus", 0.0)
            p.studying_remaining = sd.get("studying_remaining", 0)
            p.minor_illness_count = sd.get("minor_illness_count", 0)
            p.life_points = sd.get("life_points", 0.0)
            p.consecutive_work = sd.get("consecutive_work", 0)
            p.consecutive_gamble = sd.get("consecutive_gamble", 0)
            p.total_hunger_days = sd.get("total_hunger_days", 0)
            p.happy_rounds = sd.get("happy_rounds", 0)
            p.medicine_immune = False

        # Rebuild history from trajectories
        traj = state.get("trajectories_with_start", {})
        for p in players:
            p.history = []
            for h in traj.get(p.name, []):
                if h.get("round", 0) == 0:
                    continue
                p.history.append({
                    "round": h["round"],
                    "choice": h.get("choice", "?"),
                    "result": h.get("result", "?"),
                    "assets_after": h.get("assets", 0),
                })

        return engine

    # ===================================================================
    #  Display
    # ===================================================================

    def _display_step(self, step_result: dict, verbose: bool = True):
        if not verbose:
            return

        actions = step_result.get("actions", [])
        events = step_result.get("events", [])
        events_by_type: dict[str, list] = {}
        for ev in events:
            events_by_type.setdefault(ev.get("type", "?"), []).append(ev)

        # Events
        for etype, evs in events_by_type.items():
            for ev in evs:
                if etype == "illness":
                    name = ev["player"]
                    cost = ev.get("cost", 0)
                    if ev.get("event") == "illness_loan":
                        loan = ev.get("loan", 0)
                        print(f"  {Colors.color('!!!', Colors.RED)} {name} got SICK! Can't afford ${cost:,.0f} — took LOAN of ${loan:,.2f}.")
                    else:
                        print(f"  {Colors.color('!!!', Colors.RED)} {name} paid ${cost:,.0f} medical bill from assets.")
                elif etype == "minor_illness":
                    name = ev["player"]
                    cost_val = ev["cost"]
                    san_lost = ev["san_lost"]
                    print(f"  {Colors.color(f'{name} fell ILL from low HP! Paid ${cost_val:,.0f}, SAN -{san_lost:.0f}', Colors.YELLOW)}")
                elif etype == "starved":
                    pname = ev["player"]
                    print(f"  {Colors.color(f'{pname} STARVED to death!', Colors.RED)}")
                elif etype == "insane":
                    pname = ev["player"]
                    print(f"  {Colors.color(f'{pname} went INSANE (SAN=0)!', Colors.RED)}")
                elif etype == "hp_death":
                    pname = ev["player"]
                    print(f"  {Colors.color(f'{pname} died from low HP!', Colors.RED)}")
                elif etype == "study_start":
                    name = ev["player"]
                    cost = ev.get("cost", self.base_study_cost)
                    print(f"  {Colors.color(f'{name} began STUDY (${cost:,.0f} tuition, {self.study_duration} rounds)', Colors.CYAN)}")
                elif etype == "study_complete":
                    name = ev["player"]
                    print(f"  {Colors.color(f'{name} COMPLETED study! Wage bonus now +${self.daily_wage + self.daily_wage:.0f}/day', Colors.CYAN)}")
                elif etype == "goods_bought":
                    name = ev["player"]
                    sr = ev.get("san_restored", 0)
                    san = ev.get("san", 0)
                    print(f"  {Colors.color(f'{name} bought goods: SAN +{sr:.0f} → {san:.0f}', Colors.MAGENTA)}")
                elif etype == "medicine_bought":
                    name = ev["player"]
                    hr = ev.get("hp_restored", 0)
                    hp = ev.get("hp", 0)
                    print(f"  {Colors.color(f'{name} bought medicine: HP +{hr:.0f} → {hp:.0f}', Colors.MAGENTA)}")
                elif etype == "rested":
                    name = ev["player"]
                    sr = ev.get("san_restored", 0)
                    hr = ev.get("hp_restored", 0)
                    print(f"  {Colors.color(f'{name} rested: SAN +{sr:.0f}, HP +{hr:.0f}', Colors.BLUE)}")
                elif etype == "hungry":
                    name = ev["player"]
                    streak = ev.get("streak", 0)
                    print(f"  {Colors.color(f'{name} went HUNGRY (streak {streak}/3)!', Colors.YELLOW)}")

        # Per-player actions
        for a in actions:
            name = a["player"]
            choice = a["choice"]
            result = a["result"]
            ab = a["assets_before"]
            aa = a["assets_after"]
            delta = aa - ab
            delta_str = f"${aa:,.2f}"
            if delta != 0:
                sign = "+" if delta > 0 else ""
                delta_str += f" ({sign}{delta:+,.2f})"

            if "STUDY" in choice:
                player = next((p for p in self.players if p.name == name), None)
                if player and player.studying_remaining > 0:
                    print(f"  {Colors.color(f'{name} → STUDY (studying, {player.studying_remaining}r left) | {delta_str}', Colors.CYAN)}")
                else:
                    print(f"  {Colors.color(f'{name} → STUDY started | {delta_str}', Colors.CYAN)}")
            elif choice == "BUY_GOODS":
                print(f"  {Colors.color(f'{name} → BUY_GOODS | {delta_str}', Colors.MAGENTA)}")
            elif choice == "BUY_MEDICINE":
                print(f"  {Colors.color(f'{name} → BUY_MEDICINE | {delta_str}', Colors.MAGENTA)}")
            elif choice == "REST":
                print(f"  {Colors.color(f'{name} → REST | {delta_str}', Colors.BLUE)}")
            elif choice == "WORK":
                print(f"  {Colors.color(f'{name} → WORK | {delta_str}', Colors.GREEN)}")
            elif "WIN" in result:
                print(f"  {Colors.color(f'{name} → GAMBLE | {Colors.color("WIN!", Colors.CYAN)} | {delta_str}', Colors.YELLOW)}")
            elif "LOSE" in result:
                print(f"  {Colors.color(f'{name} → GAMBLE | {Colors.color("LOSE", Colors.RED)} | {delta_str}', Colors.YELLOW)}")
            else:
                print(f"  {name} → {choice} | {delta_str}")

        print(Colors.dim(f"  Round {self.round} elapsed: {step_result.get('round_elapsed', 0):.1f}s"))

    def _print_header(self, text: str):
        print(Colors.bold(f"\n{'='*60}"))
        print(Colors.bold(f"  {text}"))
        print(Colors.bold(f"{'='*60}\n"))

    def _print_setup(self):
        print(Colors.dim(f"  {len(self.players)} players, starting ${self.initial_assets:,.0f}, {self.max_rounds} rounds"))
        print(Colors.dim(f"  Daily wage: ${self.daily_wage:,.0f}  |  Food: ${self.food_cost:,.0f}/day"))
        print(Colors.dim(f"  Initial SAN: {self.initial_san:.0f}  |  Initial HP: {self.initial_hp:.0f}"))
        print(Colors.dim(f"  Study: {self.study_duration}rd lock, tuition from ${self.base_study_cost:,.0f} (scales inversely with wage)"))
        print(Colors.dim(f"  BUY_GOODS: ${self.goods_cost:,.0f} → SAN +{self.goods_san_restore:.0f}"))
        print(Colors.dim(f"  BUY_MEDICINE: ${self.medicine_cost:,.0f} → HP +{self.medicine_hp_restore:.0f}"))
        print(Colors.dim(f"  REST: free → SAN +{self.rest_san_restore:.0f}, HP +{self.rest_hp_restore:.0f}"))
        print(Colors.dim(f"  Gamble EV factor: {self.win_probability * self.win_multiplier + (1 - self.win_probability) * self.loss_multiplier:.2f}x"))
        seed = self.config.get("random_seed")
        if seed is not None:
            print(Colors.dim(f"  Random seed: {seed} (deterministic)"))
        print(Colors.dim(f"  Medical disaster: round {self._illness_round} ($100/person, once)."))
        print(Colors.color(f"  {'Winner decided by Happiness Score (not just assets)!':>60s}", Colors.CYAN))

        print()
        for p in self.players:
            tags = []
            if p.wage_bonus > 0:
                tags.append(f"+${p.wage_bonus:.0f} wage")
            if tags:
                tag_str = f"  ({', '.join(tags)})"
            else:
                tag_str = ""
            print(f"  {p.name}: ${p.assets:,.0f}  SAN:{p.san:.0f}  HP:{p.hp:.0f}{tag_str}  [{getattr(p.model, 'model_name', '?')}]")

    def _print_result(self):
        print(Colors.bold(f"\n{'='*60}"))
        print(Colors.bold(f"  FINAL RESULTS — Happiness Ranking"))
        print(Colors.bold(f"{'='*60}\n"))

        ranked = sorted(self.players, key=lambda p: self._compute_final_score(p), reverse=True)
        for i, p in enumerate(ranked, 1):
            icon = {1: "1st", 2: "2nd", 3: "3rd"}.get(i, f"{i}th")
            score = self._compute_final_score(p)
            profit = p.assets - p.initial_assets

            profit_color = Colors.GREEN if profit >= 0 else Colors.RED
            profit_str = Colors.color(f"${profit:+,.2f}", profit_color)

            stats = (f"W:{p.work_count} G:{p.gamble_count}(W{p.gamble_wins}/L{p.gamble_losses}) "
                     f"Study:{p.study_count} Goods:{p.goods_count} Med:{p.medicine_count} Rest:{p.rest_count}")
            extras = []
            if p.wage_bonus > 0:
                extras.append(f"wage+${p.wage_bonus:.0f}")
            extras.append(f"SAN:{p.san:.0f}({p.san_status})")
            extras.append(f"HP:{p.hp:.0f}({p.hp_status})")

            tags = []
            if p.studying_remaining > 0:
                tags.append("STUDYING")
            if p.insane:
                tags.append("INSANE")
            if p.sick:
                tags.append("SICK")
            if p.loan_balance > 0:
                tags.append(f"LOAN ${p.loan_balance:,.0f}")
            if p.starved:
                tags.append("STARVED")

            tag = f"  [{', '.join(tags)}]" if tags else ""

            print(f"  {icon}. {p.name}: Happiness {score:,.1f}  |  ${p.assets:,.2f} ({profit_str})  |  {stats}")
            print(f"     {', '.join(extras)}{tag}")

        # Announce winner
        winner = ranked[0]
        print(Colors.color(f"\n  *** {winner.name} wins with Happiness Score {self._compute_final_score(winner):,.1f}! ***", Colors.YELLOW))

    # ===================================================================
    #  Run loop
    # ===================================================================

    def run(self, verbose: bool = True, resumed: bool = False) -> Optional[str]:
        if not resumed:
            self.setup()

        t0 = time.time()

        if verbose:
            self._print_header("Gambler — Happiness Arena")
            self._print_setup()

        while not self.finished and self.round < self.max_rounds:
            step_result = self.step()
            if verbose:
                print(Colors.bold(f"\n--- Round {self.round} ---"))
                self._display_step(step_result, verbose=True)

            winner_name = self.check_win()
            if winner_name:
                self.finished = True
                self.winner = winner_name
                if verbose:
                    self._print_result()
                if self.logger:
                    self.logger.write_summary(
                        self.players, winner_name, self.round, [],
                        extra={"scores": {p.name: self._compute_final_score(p) for p in self.players}}
                    )
                elapsed = time.time() - t0
                print(Colors.dim(f"\n  Game time: {elapsed:,.1f}s"))
                self._build_replay()
                return winner_name

        # Game ended without explicit winner — decide by happiness score
        active = [p for p in self.players if not p.bankrupt]
        if active:
            ranked = sorted(active, key=lambda p: self._compute_final_score(p), reverse=True)
            winner = ranked[0]
            self.winner = winner.name
        elif self.players:
            # All bankrupt — highest score among all
            ranked = sorted(self.players, key=lambda p: self._compute_final_score(p), reverse=True)
            self.winner = ranked[0].name
        else:
            self.winner = None

        self.finished = True
        if verbose:
            self._print_result()

        if self.logger and self.winner:
            self.logger.write_summary(
                self.players, self.winner, self.round, [],
                extra={"scores": {p.name: self._compute_final_score(p) for p in self.players}}
            )

        elapsed = time.time() - t0
        print(Colors.dim(f"\n  Game time: {elapsed:,.1f}s"))
        self._build_replay()
        return self.winner

    def _build_replay(self):
        try:
            from .replay import build_replay
            state = self._build_ui_state()
            ts = time.strftime("%Y%m%d_%H%M%S")
            path = Path(__file__).parent / f"replay_{ts}.html"
            build_replay(state, path)
            print(Colors.dim(f"  Replay saved: {path}"))
        except Exception:
            pass
