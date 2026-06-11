"""Gambler player with asset tracking, sanity/health, and decision history."""

from typing import List

from core.player import Player
from core.models.base import ModelInterface


class GamblerPlayer(Player):
    """A gambler who chooses between working, gambling, studying, and self-care each round."""

    def __init__(self, name: str, model: ModelInterface, assets: float = 100, persona: str = ""):
        super().__init__(name, model, persona)
        self.assets = assets
        self.initial_assets = assets
        self.history: List[dict] = []  # [{round, choice, result, assets_after}]
        self.gamble_count = 0
        self.work_count = 0
        self.gamble_wins = 0
        self.gamble_losses = 0
        self.study_count = 0      # times study completed
        self.goods_count = 0      # times bought goods
        self.medicine_count = 0   # times bought medicine
        self.bankrupt = False
        self.starved = False
        self.insane = False       # SAN reached 0
        # Illness / loan state
        self.sick = False
        self.loan_balance = 0.0
        self.loan_repay_remaining = 0
        # Hunger state
        self.hunger_streak = 0  # consecutive rounds without food
        # Sanity & Health
        self.san = 100.0
        self.hp = 100.0
        self.minor_illness_count = 0  # times fallen ill from low HP
        # Study state
        self.wage_bonus = 0.0  # starts at $0, +$10 per completed study
        self.studying_remaining = 0  # rounds left in current study (0 = not studying)

    def record(self, round_num: int, choice: str, result: str, assets_after: float):
        self.history.append({
            "round": round_num,
            "choice": choice,
            "result": result,
            "assets_after": assets_after,
        })
        if choice == "WORK":
            self.work_count += 1
        elif choice == "GAMBLE":
            self.gamble_count += 1
            if result == "WIN":
                self.gamble_wins += 1
            elif result == "LOSE":
                self.gamble_losses += 1
        elif choice == "BUY_GOODS":
            self.goods_count += 1
        elif choice == "BUY_MEDICINE":
            self.medicine_count += 1
        # STUDY doesn't count as work or gamble
        self.assets = assets_after
        if self.assets <= 0:
            self.bankrupt = True

    # ---- Study ----

    def start_study(self, cost: float, duration: int) -> dict:
        """Begin a study course. Pay cost, set remaining duration."""
        if self.assets < cost:
            return {"event": "study_fail", "reason": "cant_afford"}
        self.assets -= cost
        self.studying_remaining = duration
        return {"event": "study_start", "cost": cost, "duration": duration}

    def advance_study(self) -> dict:
        """Called each round during study. Returns event if completed or ongoing."""
        if self.studying_remaining <= 0:
            return {"event": "study_none"}
        self.studying_remaining -= 1
        if self.studying_remaining <= 0:
            self.wage_bonus += 10.0
            self.study_count += 1
            return {"event": "study_complete", "new_bonus": self.wage_bonus, "new_wage": 10.0 + self.wage_bonus}
        return {"event": "study_ongoing", "remaining": self.studying_remaining}

    def cancel_study(self) -> dict:
        """Study interrupted (e.g. can't afford food). Lose progress."""
        if self.studying_remaining > 0:
            remaining = self.studying_remaining
            self.studying_remaining = 0
            return {"event": "study_cancelled", "wasted_rounds": remaining}
        return {"event": "study_none"}

    @property
    def effective_wage(self) -> float:
        return 10.0 + self.wage_bonus  # base wage + bonus from study

    # ---- Medical Disaster ----

    def apply_illness(self, cost: float, interest_rate: float, repay_rounds: int):
        """Player gets sick (medical disaster). Pay if possible, otherwise take a loan."""
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
            return {"event": "illness_loan", "paid": self.assets,
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

    # ---- Food, SAN & HP ----

    def pay_food(self, cost: float, san_hunger: float, hp_hunger: float) -> dict:
        """Pay daily food cost. If can't pay: go hungry, lose SAN & HP.
        Returns event dict."""
        if self.assets >= cost:
            self.assets -= cost
            self.hunger_streak = 0  # ate today, reset
            return {"event": "fed", "paid": cost}
        else:
            # Can't afford food — go hungry
            self.hunger_streak += 1
            self.san = max(0.0, self.san - san_hunger)
            self.hp = max(0.0, self.hp - hp_hunger)
            result: dict = {"event": "hungry", "streak": self.hunger_streak,
                            "shortfall": cost - self.assets,
                            "san_lost": san_hunger, "hp_lost": hp_hunger,
                            "san": self.san, "hp": self.hp}

            if self.hunger_streak >= 3:
                self.starved = True
                self.bankrupt = True
                result = {"event": "starved", "streak": self.hunger_streak}
            if self.san <= 0:
                self.insane = True
                self.bankrupt = True
                result["insane"] = True
                result.setdefault("event", "insane")
            if self.hp <= 0:
                self.bankrupt = True
                result["hp_death"] = True
                result.setdefault("event", "hp_death")

            # Hunger cancels study
            if self.studying_remaining > 0:
                self.studying_remaining = 0
                result["study_cancelled"] = True
            return result

    # ---- Minor Illness (triggered by low HP) ----

    def check_minor_illness(self, threshold: float, cost: float, san_loss: float) -> dict | None:
        """If HP < threshold, trigger a minor illness: pay cost, lose SAN.
        Returns event dict or None."""
        if self.hp >= threshold:
            return None
        self.minor_illness_count += 1
        self.san = max(0.0, self.san - san_loss)
        actual_cost = min(cost, self.assets)
        self.assets -= actual_cost
        if self.assets <= 0:
            self.bankrupt = True
        if self.san <= 0:
            self.insane = True
            self.bankrupt = True
        return {"event": "minor_illness", "hp": self.hp, "hp_threshold": threshold,
                "cost": actual_cost, "san_lost": san_loss, "san": self.san}

    # ---- Goods & Medicine ----

    def buy_goods(self, cost: float, san_restore: float) -> dict:
        """Buy goods to restore sanity. Returns event dict."""
        if self.assets < cost:
            return {"event": "goods_fail", "reason": "cant_afford"}
        self.assets -= cost
        self.san = min(100.0, self.san + san_restore)
        return {"event": "goods_bought", "cost": cost, "san_restored": san_restore, "san": self.san}

    def buy_medicine(self, cost: float, hp_restore: float) -> dict:
        """Buy medicine to restore health. Returns event dict."""
        if self.assets < cost:
            return {"event": "medicine_fail", "reason": "cant_afford"}
        self.assets -= cost
        self.hp = min(100.0, self.hp + hp_restore)
        return {"event": "medicine_bought", "cost": cost, "hp_restored": hp_restore, "hp": self.hp}

    # ----

    @property
    def profit(self) -> float:
        return self.assets - self.initial_assets
