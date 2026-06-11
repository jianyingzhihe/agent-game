"""Gambler game engine — each round players choose WORK or GAMBLE.

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
    """A gambling competition where AI agents decide between safe income and risky bets."""

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

        # Game parameters
        self.initial_assets = float(self.config.get("initial_assets", 100))
        self.daily_wage = float(self.config.get("daily_wage", 10))
        self.win_probability = float(self.config.get("win_probability", 0.4))
        self.win_multiplier = float(self.config.get("win_multiplier", 3.0))
        self.loss_multiplier = float(self.config.get("loss_multiplier", 0.3))
        self.max_rounds = int(self.config.get("max_rounds", 30))
        self.temperature = float(self.config.get("temperature", 0.7))

        # Shared-randomness arena mode
        seed = self.config.get("random_seed")
        if seed is not None:
            random.seed(int(seed))
        else:
            random.seed()
        self._shared_rolls = [random.random() for _ in range(self.max_rounds)]
        self._state_file = Path(self.config.get("state_file", str(_UI_STATE_FILE)))

        # Daily living cost
        self.food_cost = float(self.config.get("food_cost", 5))

        # Illness event (shared randomness, one-time per game)
        self.illness_probability = float(self.config.get("illness_probability", 0.25))
        self.illness_cost = float(self.config.get("illness_cost", 30))
        self.loan_interest_rate = float(self.config.get("loan_interest_rate", 0.5))
        self.loan_repay_rounds = int(self.config.get("loan_repay_rounds", 5))
        self._illness_triggered = False
        self._illness_round = -1
        self._illness_target_index = -1
        # Pre-generate: will illness happen?
        if random.random() < self.illness_probability:
            self._illness_round = random.randint(3, max(self.max_rounds - 3, 4))
            self._illness_target_index = random.randint(0, len(self.players) - 1)

        # Per-round snapshot history (for viewer)
        self._snapshots: List[dict] = []

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
            if p.starved:
                tag = " [STARVED]"
            elif p.bankrupt:
                tag = " [BANKRUPT]"
            else:
                tag = ""
            lines.append(f"  {icon}. {p.name}: ${p.assets:,.2f}{tag}")
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
            p.history = []
            p.gamble_count = 0
            p.work_count = 0
            p.gamble_wins = 0
            p.gamble_losses = 0
            p.bankrupt = False
            p.starved = False
            p.sick = False
            p.loan_balance = 0.0
            p.loan_repay_remaining = 0
            p.hunger_streak = 0

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
        spending: dict[str, dict] = {p.name: {"food": 0.0, "loan": 0.0, "medical": 0.0} for p in active}

        # ---- 1. Process loan repayments ----
        for player in active:
            if player.loan_balance > 0:
                assets_before_loan = player.assets
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

        # ---- 2. Illness event check (shared randomness, one-time) ----
        if not self._illness_triggered and self.round == self._illness_round:
            self._illness_triggered = True
            target = self.players[self._illness_target_index]
            if not target.bankrupt:
                illness_result = target.apply_illness(
                    self.illness_cost, self.loan_interest_rate, self.loan_repay_rounds
                )
                illness_result["type"] = "illness"
                illness_result["player"] = target.name
                illness_result["round"] = self.round
                illness_result["cost"] = self.illness_cost
                round_result["events"].append(illness_result)
                if target.name in spending:
                    spending[target.name]["medical"] = self.illness_cost
                if self.logger:
                    self.logger.log_event(f"round_{self.round}_illness", illness_result)

        # ---- 3. Daily food cost ----
        for player in active:
            assets_before_food = player.assets
            food_result = player.pay_food(self.food_cost)
            if food_result["event"] == "fed":
                spending[player.name]["food"] = self.food_cost
            elif food_result["event"] == "hungry":
                round_result["events"].append({
                    "type": "hungry",
                    "player": player.name,
                    "streak": food_result["streak"],
                })
            elif food_result["event"] == "starved":
                round_result["events"].append({
                    "type": "starved",
                    "player": player.name,
                    "streak": food_result["streak"],
                })
                if self.logger:
                    self.logger.log_event(f"round_{self.round}_starved", {
                        "player": player.name, "streak": food_result["streak"]
                    })

        # Store spending in round_result for display
        round_result["spending"] = {k: dict(v) for k, v in spending.items()}

        # Refresh active list (starvation may have eliminated players)
        active = [p for p in active if not p.bankrupt]

        if not active:
            self.finished = True
            self._write_ui_state()
            return round_result

        # Shared roll for this round — all gamblers face the same luck
        shared_roll = self._shared_rolls[self.round - 1]

        # Build all prompts first (snapshot current state for all players)
        order = list(active)
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
            )
            tasks.append((player, prompt))

        # Query all players concurrently — wait for the slowest, not the sum
        round_t0 = time.time()
        results: dict[str, tuple[dict, float]] = {}
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            future_to_player = {
                executor.submit(self._query, player, prompt): player.name
                for player, prompt in tasks
            }
            for future in as_completed(future_to_player):
                name = future_to_player[future]
                try:
                    results[name] = future.result()  # (parsed, elapsed)
                except Exception as e:
                    results[name] = ({"choice": "WORK", "reason": f"ERROR: {e}"}, 0.0)
        round_elapsed = time.time() - round_t0

        # Resolve outcomes (same shared roll for all gamblers this round)
        for player in order:
            parsed, elapsed = results.get(player.name, ({"choice": "WORK", "reason": ""}, 0.0))
            choice = parsed.get("choice", "WORK").strip().upper()
            reason = parsed.get("reason", "")

            assets_before = player.assets
            if "GAMBLE" in choice:
                if shared_roll < self.win_probability:
                    new_assets = player.assets * self.win_multiplier
                    result = "WIN"
                else:
                    new_assets = player.assets * self.loss_multiplier
                    result = "LOSE"
                player.record(self.round, "GAMBLE", result, new_assets)
            else:
                new_assets = player.assets + self.daily_wage
                result = "EARNED"
                player.record(self.round, "WORK", result, new_assets)

            action = {
                "player": player.name,
                "choice": "GAMBLE" if "GAMBLE" in choice else "WORK",
                "result": result,
                "reason": reason,
                "assets_before": assets_before,
                "assets_after": new_assets,
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

    # ---- UI state file (consumed by viewer.html) ----

    def _build_ui_state(self) -> dict:
        """Build a JSON-serializable snapshot of the entire game so far."""
        return {
            "game_config": {
                "initial_assets": self.initial_assets,
                "daily_wage": self.daily_wage,
                "win_probability": self.win_probability,
                "win_multiplier": self.win_multiplier,
                "loss_multiplier": self.loss_multiplier,
                "max_rounds": self.max_rounds,
            },
            "players": [
                {
                    "name": p.name,
                    "model_name": p.model.model_name,
                    "current_assets": p.assets,
                    "initial_assets": p.initial_assets,
                    "bankrupt": p.bankrupt,
                    "starved": p.starved,
                    "hunger_streak": p.hunger_streak,
                    "work_count": p.work_count,
                    "gamble_count": p.gamble_count,
                    "gamble_wins": p.gamble_wins,
                    "gamble_losses": p.gamble_losses,
                    "sick": p.sick,
                    "loan_balance": p.loan_balance,
                    "loan_repay_remaining": p.loan_repay_remaining,
                }
                for p in self.players
            ],
            "player_names": [p.name for p in self.players],
            "current_round": self.round,
            "finished": self.finished,
            "winner": self.winner,
            "trajectories_with_start": {
                p.name: (
                    [{"round": 0, "assets": p.initial_assets}]
                    + [{"round": h["round"], "assets": h["assets_after"]} for h in p.history]
                )
                for p in self.players
            },
        }

    def _write_ui_state(self) -> None:
        """Persist the current game state to a JSON file for the live viewer."""
        state = self._build_ui_state()
        try:
            tmp = str(self._state_file) + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            os.replace(tmp, str(self._state_file))  # atomic on Windows
        except OSError:
            pass

    # ---- Replay ----

    def _build_replay(self) -> None:
        """Generate a self-contained replay HTML file."""
        try:
            from .replay import build_replay
            state = self._build_ui_state()
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            replay_path = self._state_file.parent / f"replay_{timestamp}.html"
            build_replay(state, replay_path)
            print(f"\n  {Colors.color(f'Replay saved: {replay_path}', Colors.CYAN)}")
        except Exception as e:
            pass  # silently skip if replay generation fails

    # ---- Run ----

    def run(self, verbose: bool = True) -> Optional[str]:
        game_t0 = time.time()
        self.setup()

        if verbose:
            self._print_header("GAMBLER GAME START")
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

        # ---- Spending summary per player ----
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
            if not parts:
                # Check if hungry
                for ev in step_result.get("events", []):
                    if ev.get("player") == name and ev.get("type") == "hungry":
                        parts.append(Colors.color("went HUNGRY", Colors.YELLOW))
                        break
            if parts:
                print(Colors.dim(f"  {name}: {' | '.join(parts)}"))

        # Display dramatic events (illness, starved)
        for event in step_result.get("events", []):
            if event["type"] == "illness":
                name = event["player"]
                cost = event["cost"]
                if event["event"] == "illness_paid":
                    print(f"  {Colors.color('!!!', Colors.RED)} {name} got SICK! Paid ${cost:,.0f} medical bill.")
                else:
                    loan = event["loan"]
                    print(f"  {Colors.color('!!!', Colors.RED)} {name} got SICK! Can't afford ${cost:,.0f} — took LOAN of ${loan:,.2f} ({self.loan_interest_rate:.0%} interest, {self.loan_repay_rounds} rounds to repay).")
            elif event["type"] == "starved":
                name = event["player"]
                print(f"  {Colors.color(f'{name} STARVED to death after 3 days without food!', Colors.RED)}")

        for action in step_result.get("actions", []):
            name = action["player"]
            choice = action["choice"]
            result = action["result"]
            after = action["assets_after"]
            elapsed = action.get("elapsed", 0.0)
            timing = Colors.dim(f"  [{elapsed:.1f}s]")

            if choice == "WORK":
                print(f"  {name}: {Colors.color('WORK', Colors.GREEN)}  → +${self.daily_wage:,.0f}  → ${after:,.2f}{timing}")
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
              f"Gamble: {self.win_probability:.0%} chance of {self.win_multiplier}x, "
              f"else {self.loss_multiplier}x  |  "
              f"EV factor: {gamble_ev_factor:.2f}x")
        seed_info = f"  seed: {self.config.get('random_seed')}" if self.config.get("random_seed") else ""
        if seed_info:
            print(Colors.dim(seed_info))
        # Illness info
        if self._illness_round > 0:
            target_name = self.players[self._illness_target_index].name
            print(Colors.color(
                f"  Illness event: Round {self._illness_round} → {target_name} "
                f"(cost ${self.illness_cost:,.0f}, loan interest {self.loan_interest_rate:.0%}, "
                f"repay {self.loan_repay_rounds} rds)",
                Colors.YELLOW
            ))
        else:
            print(Colors.dim(f"  No illness event this game"))
        print()
        for p in self.players:
            print(f"  {p.name:12s} ${p.assets:,.0f}  [{p.model.model_name}]")

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
            stats += ")"
            loan_info = ""
            if p.sick:
                loan_info += " SICK"
            if p.loan_balance > 0:
                loan_info += f" LOAN(${p.loan_balance:,.1f})"
            if p.starved:
                loan_info += " STARVED"
            print(f"  {Colors.bold(icon)}. {p.name:12s} ${p.assets:,.2f}  "
                  f"({Colors.color(f'{sign}{delta:,.2f}', color)})  {Colors.dim(stats)}"
                  f"{Colors.color(loan_info, Colors.RED) if loan_info else ''}")
        winner_name = self.winner or ranked[0].name
        print(f"\n  {Colors.color(f'{winner_name} is the richest gambler!', Colors.YELLOW)}")
