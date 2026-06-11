"""Gambler game engine — each round players choose WORK, GAMBLE, STUDY, BUY_GOODS, or BUY_MEDICINE.

Shared-randomness arena mode: one roll per round, so all gamblers
in round N face the same luck.  Writes ui_state.json for live viewer.
All players are queried concurrently within each round (ThreadPoolExecutor).
"""

import json
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
        self.minor_illness_hp_threshold = float(self.config.get("minor_illness_hp_threshold", 30))
        self.minor_illness_cost = float(self.config.get("minor_illness_cost", 20))
        self.minor_illness_san_loss = float(self.config.get("minor_illness_san_loss", 20))
        self.goods_cost = float(self.config.get("goods_cost", 5))
        self.goods_san_restore = float(self.config.get("goods_san_restore", 20))
        self.medicine_cost = float(self.config.get("medicine_cost", 15))
        self.medicine_hp_restore = float(self.config.get("medicine_hp_restore", 30))

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
        Higher wage → more lost wages → lower tuition to compensate."""
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
                # Can't afford food AND will die from SAN/HP loss regardless of income
                # since food was already deducted this round
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
            san_str = f" SAN:{p.san:.0f}" if p.san < 80 else ""
            hp_str = f" HP:{p.hp:.0f}" if p.hp < 80 else ""
            lines.append(f"  {icon}. {p.name}: ${p.assets:,.2f}{san_str}{hp_str}{tag}")
        return "\n".join(lines)

    def _player_history(self, player: GamblerPlayer) -> str:
        if not player.history:
            return "(no history yet)"
        lines = []
        for h in player.history[-8:]:
            icon = {"WIN": "WIN", "LOSE": "LOSE", "EARNED": "SAFE"}.get(h["result"], h["result"])
            lines.append(
                f"  Round {h['round']}: {h['choice']} → {icon} → ${h['assets_after']:,.2f}"
            )
        return "\n".join(lines)

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
            p.bankrupt = False
            p.starved = False
            p.insane = False
            p.sick = False
            p.loan_balance = 0.0
            p.loan_repay_remaining = 0
            p.hunger_streak = 0
            p.wage_bonus = 0.0
            p.studying_remaining = 0
            p.study_count = 0
            p.minor_illness_count = 0

        self._illness_triggered = False
        self._snapshots = []

        if self.logger:
            self.logger.log_event("game_start", {
                "players": [{"name": p.name, "initial_assets": self.initial_assets} for p in self.players],
                "daily_wage": self.daily_wage,
                "win_probability": self.win_probability,
                "win_multiplier": self.win_multiplier,
                "loss_multiplier": self.loss_multiplier,
                "max_rounds": self.max_rounds,
                "random_seed": self.config.get("random_seed"),
            })

        self._write_ui_state()

    def step(self) -> dict:
        self.round += 1
        active = [p for p in self.players if not p.bankrupt]

        if not active:
            self.finished = True
            self._write_ui_state()
            return {"round": self.round, "error": "all_bankrupt"}

        round_result = {"round": self.round, "actions": [], "events": []}

        # Track per-player spending this round
        spending: dict[str, dict] = {p.name: {"food": 0.0, "loan": 0.0, "medical": 0.0,
                                               "minor_illness": 0.0, "goods": 0.0, "medicine": 0.0}
                                     for p in active}

        # ---- 1. Process loan repayments ----
        for player in active:
            if player.loan_balance > 0:
                paid = player.repay_loan()
                if paid > 0:
                    spending[player.name]["loan"] = paid
                    round_result["events"].append({
                        "type": "loan_repay",
                        "player": player.name,
                        "paid": paid,
                        "remaining_balance": player.loan_balance,
                        "remaining_rounds": player.loan_repay_remaining,
                    })

        # ---- 2. Medical disaster — ALL players get sick ----
        if not self._illness_triggered and self.round == self._illness_round:
            self._illness_triggered = True
            for player in active:
                illness_result = player.apply_illness(
                    self.illness_cost, self.loan_interest_rate, self.loan_repay_rounds
                )
                illness_result["type"] = "illness"
                illness_result["player"] = player.name
                illness_result["round"] = self.round
                illness_result["cost"] = self.illness_cost
                round_result["events"].append(illness_result)
                spending[player.name]["medical"] = self.illness_cost
                if self.logger:
                    self.logger.log_event(f"round_{self.round}_illness_{player.name}", illness_result)

        # ---- 3. Daily food cost (with SAN/HP penalty for hunger) ----
        for player in active:
            food_result = player.pay_food(self.food_cost, self.san_hunger_penalty, self.hp_hunger_penalty)
            ev_type = food_result["event"]
            if ev_type == "fed":
                spending[player.name]["food"] = self.food_cost
            elif ev_type == "hungry":
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

        # ---- 3b. Minor illness check (HP below threshold) ----
        for player in list(active):
            if not player.bankrupt:
                mi = player.check_minor_illness(
                    self.minor_illness_hp_threshold,
                    self.minor_illness_cost,
                    self.minor_illness_san_loss,
                )
                if mi:
                    mi["player"] = player.name
                    mi["type"] = "minor_illness"
                    mi["round"] = self.round
                    round_result["events"].append(mi)
                    spending[player.name]["minor_illness"] = mi["cost"]

        # ---- 4. Advance study for players already studying ----
        for player in active:
            if player.studying_remaining > 0:
                study_result = player.advance_study()
                if study_result["event"] == "study_complete":
                    round_result["events"].append({
                        "type": "study_complete",
                        "player": player.name,
                        "new_bonus": player.wage_bonus,
                        "new_wage": 10.0 + player.wage_bonus,
                    })

        # Store spending in round_result for display
        round_result["spending"] = {k: dict(v) for k, v in spending.items()}

        # Refresh active list
        active = [p for p in active if not p.bankrupt]

        if not active:
            self.finished = True
            self._write_ui_state()
            return round_result

        # Split active players: those studying vs. those making decisions
        studying_players = [p for p in active if p.studying_remaining > 0]
        deciding_players = [p for p in active if p.studying_remaining <= 0]

        # Fast path: auto-decide for players whose choice is forced
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

        # Build prompts for players who actually need an API call
        order = list(need_api)
        random.shuffle(order)
        tasks = []
        for player in order:
            sp = spending.get(player.name, {})
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
                spent_food=sp.get("food", 0),
                spent_loan=sp.get("loan", 0),
                spent_medical=sp.get("medical", 0),
                wage_bonus=player.wage_bonus,
                studying_remaining=player.studying_remaining,
                study_cost=self._player_study_cost(player),
                study_duration=self.study_duration,
                disaster_warning=not self._illness_triggered,
                san=player.san,
                hp=player.hp,
                san_hunger_penalty=self.san_hunger_penalty,
                hp_hunger_penalty=self.hp_hunger_penalty,
                minor_illness_threshold=self.minor_illness_hp_threshold,
                goods_cost=self.goods_cost,
                goods_san_restore=self.goods_san_restore,
                medicine_cost=self.medicine_cost,
                medicine_hp_restore=self.medicine_hp_restore,
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

        # Auto-record actions for studying players
        for player in studying_players:
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

            if "BUY_GOODS" in choice:
                gresult = player.buy_goods(self.goods_cost, self.goods_san_restore)
                if gresult["event"] == "goods_fail":
                    # Fall back to WORK
                    effective_wage = self.daily_wage + player.wage_bonus
                    new_assets = player.assets + effective_wage
                    result = "EARNED"
                    player.record(self.round, "WORK", result, new_assets)
                    reason = f"Wanted BUY_GOODS but can't afford. Fell back to WORK. {reason}"
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
                    spending[player.name]["goods"] = self.goods_cost
                    round_result["events"].append({
                        "type": "goods_bought",
                        "player": player.name,
                        "cost": self.goods_cost,
                        "san_restored": self.goods_san_restore,
                        "san": player.san,
                    })

            elif "BUY_MEDICINE" in choice:
                mresult = player.buy_medicine(self.medicine_cost, self.medicine_hp_restore)
                if mresult["event"] == "medicine_fail":
                    effective_wage = self.daily_wage + player.wage_bonus
                    new_assets = player.assets + effective_wage
                    result = "EARNED"
                    player.record(self.round, "WORK", result, new_assets)
                    reason = f"Wanted BUY_MEDICINE but can't afford. Fell back to WORK. {reason}"
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
                    spending[player.name]["medicine"] = self.medicine_cost
                    round_result["events"].append({
                        "type": "medicine_bought",
                        "player": player.name,
                        "cost": self.medicine_cost,
                        "hp_restored": self.medicine_hp_restore,
                        "hp": player.hp,
                    })

            elif "STUDY" in choice:
                if player.studying_remaining > 0:
                    effective_wage = self.daily_wage + player.wage_bonus
                    new_assets = player.assets + effective_wage
                    result = "EARNED"
                    player.record(self.round, "WORK", result, new_assets)
                    reason = f"Already studying, so WORK instead. {reason}"
                else:
                    scost = self._player_study_cost(player)
                    study_result = player.start_study(scost, self.study_duration)
                    if study_result["event"] == "study_fail":
                        effective_wage = self.daily_wage + player.wage_bonus
                        new_assets = player.assets + effective_wage
                        result = "EARNED"
                        player.record(self.round, "WORK", result, new_assets)
                        reason = f"Wanted STUDY but can't afford ${scost:,.0f}. Fell back to WORK. {reason}"
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
                        round_result["events"].append({
                            "type": "study_start",
                            "player": player.name,
                            "cost": scost,
                            "duration": self.study_duration,
                        })

            elif "GAMBLE" in choice:
                if shared_roll < self.win_probability:
                    new_assets = player.assets * self.win_multiplier
                    result = "WIN"
                else:
                    new_assets = player.assets * self.loss_multiplier
                    result = "LOSE"
                player.record(self.round, "GAMBLE", result, new_assets)

            else:
                effective_wage = self.daily_wage + player.wage_bonus
                new_assets = player.assets + effective_wage
                result = "EARNED"
                player.record(self.round, "WORK", result, new_assets)

            # Determine display choice
            display_choice = choice
            if "STUDY" in choice and result == "EARNED":
                display_choice = "WORK"
            elif "BUY_GOODS" in choice and result == "EARNED":
                display_choice = "WORK"
            elif "BUY_MEDICINE" in choice and result == "EARNED":
                display_choice = "WORK"

            valid = ("WORK", "GAMBLE", "STUDY", "BUY_GOODS", "BUY_MEDICINE")
            action = {
                "player": player.name,
                "choice": display_choice if display_choice in valid else "WORK",
                "result": result,
                "reason": reason,
                "assets_before": assets_before,
                "assets_after": player.assets,
                "elapsed": elapsed,
            }
            round_result["actions"].append(action)

            if self.logger:
                self.logger.log_event(f"round_{self.round}_{player.name}", action)

        round_result["round_elapsed"] = round_elapsed

        self._write_ui_state()
        return round_result

    def check_win(self) -> Optional[str]:
        if self.round >= self.max_rounds:
            active = [p for p in self.players if not p.bankrupt]
            if not active:
                return None
            return max(active, key=lambda p: p.assets).name
        return None

    # ---- UI state file ----

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
                "study_cost": self.base_study_cost,
                "study_duration": self.study_duration,
                "temperature": self.temperature,
                "illness_cost": self.illness_cost,
                "loan_interest_rate": self.loan_interest_rate,
                "loan_repay_rounds": self.loan_repay_rounds,
                "initial_san": self.initial_san,
                "initial_hp": self.initial_hp,
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
                    "model_name": p.model.model_name,
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
                    "sick": p.sick,
                    "loan_balance": p.loan_balance,
                    "loan_repay_remaining": p.loan_repay_remaining,
                    "wage_bonus": p.wage_bonus,
                    "studying_remaining": p.studying_remaining,
                    "study_count": p.study_count,
                    "san": p.san,
                    "hp": p.hp,
                    "minor_illness_count": p.minor_illness_count,
                }
                for p in self.players
            ],
            "player_names": [p.name for p in self.players],
            "current_round": self.round,
            "finished": self.finished,
            "winner": self.winner,
            "trajectories_with_start": {
                p.name: (
                    [{"round": 0, "assets": p.initial_assets, "choice": "START", "result": ""}]
                    + [{"round": h["round"], "assets": h["assets_after"],
                        "choice": h.get("choice", ""), "result": h.get("result", "")}
                       for h in p.history]
                )
                for p in self.players
            },
        }

    def _write_ui_state(self) -> None:
        state = self._build_ui_state()
        try:
            tmp = str(self._state_file) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, str(self._state_file))
        except OSError:
            pass

    @classmethod
    def resume(cls, players: List[GamblerPlayer], state: dict, logger=None) -> "GamblerEngine":
        cfg = state["game_config"]
        eng_state = state.get("engine_state", {})

        config = {
            "initial_assets": cfg["initial_assets"],
            "daily_wage": cfg["daily_wage"],
            "win_probability": cfg["win_probability"],
            "win_multiplier": cfg["win_multiplier"],
            "loss_multiplier": cfg["loss_multiplier"],
            "max_rounds": cfg["max_rounds"],
            "food_cost": cfg.get("food_cost", 5),
            "study_cost": cfg.get("study_cost", 45),
            "study_duration": cfg.get("study_duration", 3),
            "temperature": cfg.get("temperature", 0.7),
            "illness_cost": cfg.get("illness_cost", 100),
            "loan_interest_rate": cfg.get("loan_interest_rate", 0.2),
            "loan_repay_rounds": cfg.get("loan_repay_rounds", 20),
            "initial_san": cfg.get("initial_san", 100),
            "initial_hp": cfg.get("initial_hp", 100),
            "san_hunger_penalty": cfg.get("san_hunger_penalty", 15),
            "hp_hunger_penalty": cfg.get("hp_hunger_penalty", 10),
            "minor_illness_hp_threshold": cfg.get("minor_illness_hp_threshold", 30),
            "minor_illness_cost": cfg.get("minor_illness_cost", 20),
            "minor_illness_san_loss": cfg.get("minor_illness_san_loss", 20),
            "goods_cost": cfg.get("goods_cost", 5),
            "goods_san_restore": cfg.get("goods_san_restore", 20),
            "medicine_cost": cfg.get("medicine_cost", 15),
            "medicine_hp_restore": cfg.get("medicine_hp_restore", 30),
            "state_file": str(_UI_STATE_FILE),
        }
        if eng_state.get("random_seed") is not None:
            config["random_seed"] = eng_state["random_seed"]

        engine = cls(players, config=config, logger=logger)

        engine.round = state["current_round"]
        engine.finished = state.get("finished", False)
        engine.winner = state.get("winner")
        if eng_state.get("shared_rolls"):
            engine._shared_rolls = eng_state["shared_rolls"]
        if eng_state.get("illness_round"):
            engine._illness_round = eng_state["illness_round"]
        engine._illness_triggered = eng_state.get("illness_triggered", False)

        saved_players = {p["name"]: p for p in state["players"]}
        for p in players:
            sp = saved_players.get(p.name, {})
            p.assets = sp.get("current_assets", p.assets)
            p.initial_assets = sp.get("initial_assets", p.initial_assets)
            p.san = sp.get("san", 100.0)
            p.hp = sp.get("hp", 100.0)
            p.bankrupt = sp.get("bankrupt", False)
            p.starved = sp.get("starved", False)
            p.insane = sp.get("insane", False)
            p.hunger_streak = sp.get("hunger_streak", 0)
            p.work_count = sp.get("work_count", 0)
            p.gamble_count = sp.get("gamble_count", 0)
            p.gamble_wins = sp.get("gamble_wins", 0)
            p.gamble_losses = sp.get("gamble_losses", 0)
            p.goods_count = sp.get("goods_count", 0)
            p.medicine_count = sp.get("medicine_count", 0)
            p.sick = sp.get("sick", False)
            p.loan_balance = sp.get("loan_balance", 0.0)
            p.loan_repay_remaining = sp.get("loan_repay_remaining", 0)
            p.wage_bonus = sp.get("wage_bonus", 0.0)
            p.studying_remaining = sp.get("studying_remaining", 0)
            p.study_count = sp.get("study_count", 0)
            p.minor_illness_count = sp.get("minor_illness_count", 0)

            traj = state.get("trajectories_with_start", {}).get(p.name, [])
            p.history = [
                {"round": pt["round"], "choice": pt.get("choice", ""),
                 "result": pt.get("result", ""), "assets_after": pt["assets"]}
                for pt in traj if pt.get("round", 0) > 0
            ]

        return engine

    # ---- Replay ----

    def _build_replay(self) -> None:
        try:
            from .replay import build_replay
            state = self._build_ui_state()
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            replay_path = self._state_file.parent / f"replay_{timestamp}.html"
            build_replay(state, replay_path)
            print(f"\n  {Colors.color(f'Replay saved: {replay_path}', Colors.CYAN)}")
        except Exception:
            pass

    # ---- Run ----

    def run(self, verbose: bool = True, resumed: bool = False) -> Optional[str]:
        game_t0 = time.time()
        if not resumed:
            self.setup()
        else:
            self._write_ui_state()

        if verbose:
            self._print_header("GAMBLER GAME START" if not resumed else "GAMBLER GAME RESUMED")
            self._print_setup()

        while not self.finished and self.round < self.max_rounds:
            if verbose:
                print(f"\n{'─' * 55}")
                print(Colors.bold(f" Round {self.round + 1} / {self.max_rounds} "))
                print(f"{'─' * 55}")

            step_result = self.step()
            self._display_step(step_result, verbose)

            winner = self.check_win()
            if winner:
                self.finished = True
                self.winner = winner
                self._write_ui_state()
                if verbose:
                    self._print_result()
                if self.logger:
                    self.logger.write_summary(
                        self.players, winner, self.round,
                        [f"{p.name}: ${p.assets:,.2f}" for p in self.players]
                    )
                game_elapsed = time.time() - game_t0
                print(Colors.dim(f"  Total game time: {game_elapsed:.1f}s ({game_elapsed/60:.1f} min)"))
                self._build_replay()
                return winner

        if not self.winner:
            self.finished = True
            active = [p for p in self.players if not p.bankrupt]
            if active:
                self.winner = max(active, key=lambda p: p.assets).name
            self._write_ui_state()
            if verbose:
                self._print_result()

        game_elapsed = time.time() - game_t0
        print(Colors.dim(f"  Total game time: {game_elapsed:.1f}s ({game_elapsed/60:.1f} min)"))
        self._build_replay()
        return self.winner

    def _display_step(self, step_result: dict, verbose: bool) -> None:
        if not verbose:
            return

        spending = step_result.get("spending", {})
        for action in step_result.get("actions", []):
            name = action["player"]
            sp = spending.get(name, {})
            parts = []
            if sp.get("food", 0) > 0:
                parts.append(f"food -${sp['food']:,.0f}")
            if sp.get("loan", 0) > 0:
                parts.append(f"loan -${sp['loan']:,.0f}")
            if sp.get("medical", 0) > 0:
                parts.append(f"medical -${sp['medical']:,.0f}")
            if sp.get("minor_illness", 0) > 0:
                parts.append(f"minor ill -${sp['minor_illness']:,.0f}")
            if sp.get("goods", 0) > 0:
                parts.append(f"goods -${sp['goods']:,.0f}")
            if sp.get("medicine", 0) > 0:
                parts.append(f"med -${sp['medicine']:,.0f}")
            if not parts:
                for ev in step_result.get("events", []):
                    if ev.get("player") == name and ev.get("type") == "hungry":
                        san_lost = ev.get("san_lost", 0)
                        hp_lost = ev.get("hp_lost", 0)
                        parts.append(Colors.color(f"went HUNGRY (SAN-{san_lost:.0f} HP-{hp_lost:.0f})", Colors.YELLOW))
                        break
            if parts:
                print(Colors.dim(f"  {name}: {' | '.join(parts)}"))

        # Display events
        for event in step_result.get("events", []):
            etype = event["type"]
            if etype == "illness":
                name = event["player"]
                cost = event["cost"]
                if event.get("event") == "illness_paid":
                    print(f"  {Colors.color('!!!', Colors.RED)} {name} got SICK! Paid ${cost:,.0f} medical bill.")
                else:
                    loan = event.get("loan", 0)
                    print(f"  {Colors.color('!!!', Colors.RED)} {name} got SICK! Can't afford ${cost:,.0f} — took LOAN of ${loan:,.2f}.")
            elif etype == "minor_illness":
                name = event["player"]
                cost_val = event["cost"]
                san_lost = event["san_lost"]
                print(f"  {Colors.color(f'{name} fell ILL from low HP! Paid ${cost_val:,.0f}, SAN -{san_lost:.0f}', Colors.YELLOW)}")
            elif etype == "starved":
                pname = event["player"]
                print(f"  {Colors.color(f'{pname} STARVED to death!', Colors.RED)}")
            elif etype == "insane":
                pname = event["player"]
                print(f"  {Colors.color(f'{pname} went INSANE (SAN=0)!', Colors.RED)}")
            elif etype == "hp_death":
                pname = event["player"]
                print(f"  {Colors.color(f'{pname} died from low HP!', Colors.RED)}")
            elif etype == "study_start":
                name = event["player"]
                cost = event.get("cost", self.base_study_cost)
                print(f"  {Colors.color(f'{name} started STUDY (${cost:,.0f}, {self.study_duration} rounds)', Colors.CYAN)}")
            elif etype == "study_complete":
                name = event["player"]
                new_wage = event.get("new_wage", 20)
                print(f"  {Colors.color(f'{name} completed STUDY! Wage now ${new_wage:,.0f}/day', Colors.CYAN)}")
            elif etype == "goods_bought":
                name = event["player"]
                san = event.get("san", 0)
                print(f"  {Colors.color(f'{name} bought goods → SAN {san:.0f}', Colors.MAGENTA)}")
            elif etype == "medicine_bought":
                name = event["player"]
                hp = event.get("hp", 0)
                print(f"  {Colors.color(f'{name} bought medicine → HP {hp:.0f}', Colors.MAGENTA)}")

        for action in step_result.get("actions", []):
            name = action["player"]
            choice = action["choice"]
            result = action["result"]
            after = action["assets_after"]
            reason = action.get("reason", "")
            elapsed = action.get("elapsed", 0.0)

            if reason.startswith("AUTO:"):
                timing = Colors.dim("  [auto]")
            else:
                timing = Colors.dim(f"  [{elapsed:.1f}s]")

            if choice == "STUDY":
                if "STUDYING" in str(result):
                    p = next((pl for pl in self.players if pl.name == name), None)
                    remaining = p.studying_remaining if p else '?'
                    print(f"  {name}: {Colors.color('STUDY', Colors.CYAN)} — studying ({remaining}r left), no income {timing}")
                else:
                    p = next((pl for pl in self.players if pl.name == name), None)
                    scost = self._player_study_cost(p) if p else self.base_study_cost
                    print(f"  {name}: {Colors.color('STUDY', Colors.CYAN)} — paid ${scost:,.0f}, studying for {self.study_duration} rounds {timing}")
            elif choice == "BUY_GOODS":
                print(f"  {name}: {Colors.color('BUY GOODS', Colors.MAGENTA)} → SAN restored +${self.goods_san_restore:.0f} → ${after:,.2f}{timing}")
            elif choice == "BUY_MEDICINE":
                print(f"  {name}: {Colors.color('BUY MED', Colors.MAGENTA)} → HP restored +${self.medicine_hp_restore:.0f} → ${after:,.2f}{timing}")
            elif choice == "WORK":
                p = next((pl for pl in self.players if pl.name == name), None)
                eff_wage = self.daily_wage + (p.wage_bonus if p else 0.0)
                print(f"  {name}: {Colors.color('WORK', Colors.GREEN)}  → +${eff_wage:,.0f}  → ${after:,.2f}{timing}")
            elif result == "WIN":
                mult = self.win_multiplier
                print(f"  {name}: {Colors.color('GAMBLE', Colors.YELLOW)} → {Colors.color('WIN!', Colors.CYAN)} ({mult}x) → ${after:,.2f}{timing}")
            else:
                mult = self.loss_multiplier
                print(f"  {name}: {Colors.color('GAMBLE', Colors.YELLOW)} → {Colors.color('LOSE', Colors.RED)} ({mult}x) → ${after:,.2f}{timing}")

        round_elapsed = step_result.get("round_elapsed", 0.0)
        print(Colors.dim(f"  Round completed in {round_elapsed:.1f}s (concurrent)"))

    # ---- Display ----

    def _print_header(self, text: str) -> None:
        print(f"\n{Colors.bold('=' * 55)}")
        print(Colors.bold(f"  {text}"))
        print(Colors.bold('=' * 55))

    def _print_setup(self) -> None:
        gamble_ev_factor = self.win_probability * self.win_multiplier + (1 - self.win_probability) * self.loss_multiplier
        print(f"\n  {Colors.bold(f'{len(self.players)} players')}  |  "
              f"${self.initial_assets:,.0f} starting assets  |  "
              f"{self.max_rounds} rounds")
        print(f"  Daily wage: ${self.daily_wage:,.0f}  |  "
              f"Food cost: ${self.food_cost:,.0f}/day  |  "
              f"SAN:{self.initial_san:.0f} HP:{self.initial_hp:.0f}")
        print(f"  Study: ${self.base_study_cost:,.0f}→$5 tuition ({self.study_duration}rd) → wage +${self.daily_wage:,.0f}/day (~9rd payback)")
        print(f"  Goods: ${self.goods_cost:,.0f} → +{self.goods_san_restore:.0f} SAN  |  "
              f"Medicine: ${self.medicine_cost:,.0f} → +{self.medicine_hp_restore:.0f} HP")
        print(f"  Gamble: {self.win_probability:.0%} chance of {self.win_multiplier}x, "
              f"else {self.loss_multiplier}x  |  "
              f"EV factor: {gamble_ev_factor:.2f}x")
        seed_info = f"  seed: {self.config.get('random_seed')}" if self.config.get("random_seed") else ""
        if seed_info:
            print(Colors.dim(seed_info))
        print(Colors.color(
            f"  DISASTER: Round {self._illness_round} → ALL PLAYERS get sick! "
            f"(medical ${self.illness_cost:,.0f} each, loan {self.loan_interest_rate:.0%}/{self.loan_repay_rounds}rd)",
            Colors.RED
        ))
        print()
        for p in self.players:
            print(f"  {p.name:12s} ${p.assets:,.0f}  SAN:{p.san:.0f} HP:{p.hp:.0f}  [{p.model.model_name}]")

    def _print_result(self) -> None:
        print(f"\n{Colors.bold('=' * 55)}")
        print(Colors.bold(f"  GAME OVER — FINAL RESULTS"))
        print(Colors.bold('=' * 55))
        print()
        ranked = sorted(self.players, key=lambda p: p.assets, reverse=True)
        for i, p in enumerate(ranked, 1):
            delta = p.profit
            sign = "+" if delta >= 0 else ""
            color = Colors.GREEN if delta >= 0 else Colors.RED
            icon = {1: "1st", 2: "2nd", 3: "3rd"}.get(i, f"{i}th")
            stats = f"({p.work_count}W {p.gamble_count}G"
            if p.gamble_count > 0:
                stats += f" {p.gamble_wins}W/{p.gamble_losses}L"
            if p.study_count > 0:
                stats += f" {p.study_count}S"
            if p.goods_count > 0:
                stats += f" {p.goods_count}Gd"
            if p.medicine_count > 0:
                stats += f" {p.medicine_count}Md"
            stats += ")"
            extras = ""
            if p.wage_bonus > 0.0:
                extras += f" WAGE+${p.wage_bonus:,.0f}"
            extras += f" SAN:{p.san:.0f} HP:{p.hp:.0f}"
            tags = ""
            if p.studying_remaining > 0:
                tags += f" STUDYING({p.studying_remaining}r)"
            if p.insane:
                tags += " INSANE"
            if p.sick:
                tags += " SICK"
            if p.loan_balance > 0:
                tags += f" LOAN(${p.loan_balance:,.1f})"
            if p.starved:
                tags += " STARVED"
            print(f"  {Colors.bold(icon)}. {p.name:12s} ${p.assets:,.2f}  "
                  f"({Colors.color(f'{sign}{delta:,.2f}', color)})  {Colors.dim(stats)}{Colors.color(extras, Colors.CYAN) if extras else ''}"
                  f"{Colors.color(tags, Colors.RED) if tags else ''}")
        winner_name = self.winner or ranked[0].name
        print(f"\n  {Colors.color(f'{winner_name} is the richest gambler!', Colors.YELLOW)}")
