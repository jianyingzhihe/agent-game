"""Gambler player with asset tracking and decision history."""

from typing import List

from core.player import Player
from core.models.base import ModelInterface


class GamblerPlayer(Player):
    """A gambler who chooses between working and gambling each round."""

    def __init__(self, name: str, model: ModelInterface, assets: float = 100, persona: str = ""):
        super().__init__(name, model, persona)
        self.assets = assets
        self.initial_assets = assets
        self.history: List[dict] = []  # [{round, choice, result, assets_after}]
        self.gamble_count = 0
        self.work_count = 0
        self.gamble_wins = 0
        self.gamble_losses = 0
        self.bankrupt = False
        self.starved = False
        # Illness / loan state
        self.sick = False
        self.loan_balance = 0.0
        self.loan_repay_remaining = 0
        # Hunger state
        self.hunger_streak = 0  # consecutive rounds without food

    def record(self, round_num: int, choice: str, result: str, assets_after: float):
        self.history.append({
            "round": round_num,
            "choice": choice,
            "result": result,
            "assets_after": assets_after,
        })
        if choice == "WORK":
            self.work_count += 1
        else:
            self.gamble_count += 1
            if result == "WIN":
                self.gamble_wins += 1
            else:
                self.gamble_losses += 1
        self.assets = assets_after
        if self.assets <= 0:
            self.bankrupt = True

    def apply_illness(self, cost: float, interest_rate: float, repay_rounds: int):
        """Player gets sick. Pay if possible, otherwise take a loan."""
        self.sick = True
        if self.assets >= cost:
            self.assets -= cost
            return {"event": "illness_paid", "paid": cost, "loan": 0}
        else:
            shortfall = cost - self.assets
            loan_amount = shortfall * (1 + interest_rate)
            self.loan_balance = loan_amount
            self.loan_repay_remaining = repay_rounds
            self.assets = 0  # all assets go to medical bill
            return {"event": "illness_loan", "paid": self.assets + shortfall - loan_amount + loan_amount,
                    "shortfall": shortfall, "loan": loan_amount, "interest_rate": interest_rate}

    def repay_loan(self) -> float:
        """Deduct one installment of loan repayment. Returns amount paid."""
        if self.loan_balance <= 0 or self.loan_repay_remaining <= 0:
            return 0.0
        installment = self.loan_balance / self.loan_repay_remaining
        actual = min(installment, self.assets)
        self.assets -= actual
        self.loan_balance -= actual
        self.loan_repay_remaining -= 1
        if self.loan_balance <= 0.001:
            self.loan_balance = 0.0
            self.loan_repay_remaining = 0
        if self.assets <= 0:
            self.bankrupt = True
        return actual

    def pay_food(self, cost: float) -> dict:
        """Pay daily food cost. Returns event dict if went hungry or starved."""
        if self.assets >= cost:
            self.assets -= cost
            self.hunger_streak = 0  # ate today, reset
            return {"event": "fed", "paid": cost}
        else:
            self.hunger_streak += 1
            if self.hunger_streak >= 3:
                self.starved = True
                self.bankrupt = True
                return {"event": "starved", "streak": self.hunger_streak}
            return {"event": "hungry", "streak": self.hunger_streak, "shortfall": cost - self.assets}

    @property
    def profit(self) -> float:
        return self.assets - self.initial_assets
