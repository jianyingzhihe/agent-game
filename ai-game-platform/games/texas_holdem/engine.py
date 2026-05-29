"""Texas Hold'em game engine — full poker gameplay."""

import random
import re
import time
from typing import Dict, List, Optional, Tuple

from core.engine import GameEngine
from core.logger import GameLogger
from core.utils import Colors, parse_keyword_response, truncate

from .cards import Card, Deck, evaluate_hand, hand_description, RANK_NAMES, SUIT_SYMBOLS
from .player import PokerPlayer
from .prompts import betting_prompt


class PokerEngine(GameEngine):
    """Texas Hold'em engine with blinds, flop/turn/river, and betting."""

    SMALL_BLIND = 10
    BIG_BLIND = 20

    def __init__(
        self,
        players: List[PokerPlayer],
        config: dict | None = None,
        logger: GameLogger | None = None,
    ):
        for p in players:
            if not isinstance(p, PokerPlayer):
                raise TypeError(f"All players must be PokerPlayer, got {type(p).__name__}")
        super().__init__(players, config)
        self.logger = logger
        self.game_log: List[str] = []
        self.dealer_idx = 0
        self.deck = Deck()
        self.community: List[Card] = []
        self.pot = 0
        self.hand_num = 0

    # ---- Query helper ----

    def _query(self, player, phase: str, prompt: str, temp=0.6):
        t0 = time.time()
        if self.logger:
            self.logger.log_prompt(player.name, phase, 0, "", prompt)
        model_thinking, response = player.model.chat([
            {"role": "user", "content": prompt},
        ], temperature=temp)
        parsed = parse_keyword_response(response)
        if self.logger:
            self.logger.log_response(player.name, phase, 0, response, parsed, 0, (time.time()-t0)*1000)
        return response, parsed

    # ---- Setup ----

    def setup(self) -> None:
        print(f"\n  {Colors.bold(f'{len(self.players)} players, starting chips: 1000')}")
        print(f"  Blinds: {self.SMALL_BLIND}/{self.BIG_BLIND}")
        self.dealer_idx = random.randint(0, len(self.players) - 1)

        if self.logger:
            self.logger.log_event("game_start", {
                "players": [{"name": p.name, "chips": p.chips} for p in self.players],
            })

    # ---- Step (one hand) ----

    def step(self) -> dict:
        self.hand_num += 1
        self.dealer_idx = (self.dealer_idx + 1) % len(self.players)

        # Reset
        self.deck = Deck()
        self.community = []
        self.pot = 0
        for p in self.players:
            p.reset_for_hand()

        active = [p for p in self.players if p.chips > 0]
        if len(active) < 2:
            self.finished = True
            return {"hand": self.hand_num, "error": "not_enough_players"}

        print(f"\n{Colors.bold('='*50)}")
        print(f"{Colors.bold(f'  HAND #{self.hand_num}')}")
        print(f"{Colors.bold('='*50)}")

        # Post blinds
        sb_idx = (self.dealer_idx + 1) % len(self.players)
        bb_idx = (self.dealer_idx + 2) % len(self.players)

        sb_player = self.players[sb_idx]
        bb_player = self.players[bb_idx]
        sb_amount = sb_player.bet(min(self.SMALL_BLIND, sb_player.chips))
        bb_amount = bb_player.bet(min(self.BIG_BLIND, bb_player.chips))
        self.pot += sb_amount + bb_amount
        print(f"\n  SB: {sb_player.name} posts {sb_amount}")
        print(f"  BB: {bb_player.name} posts {bb_amount}")

        # Deal hole cards
        for p in self.players:
            if p.chips > 0:
                p.hole_cards = self.deck.deal(2)

        # Show hole cards (for logging)
        for p in self.players:
            if p.hole_cards:
                print(f"  {p.name}: {self._card_str(p.hole_cards)} ({p.chips} chips)")

        # ---- Pre-flop betting ----
        if not self._betting_round("Pre-flop", active, bb_amount):
            winner = self._last_active()
            self._award_pot(winner)
            return {"hand": self.hand_num, "winner": winner.name if winner else "?"}

        # ---- Flop ----
        self.community = self.deck.deal(3)
        print(f"\n  {Colors.bold('FLOP:')} {self._card_str(self.community)}")
        if not self._betting_round("Flop", active, 0):
            winner = self._last_active()
            self._award_pot(winner)
            return {"hand": self.hand_num, "winner": winner.name if winner else "?"}

        # ---- Turn ----
        self.community.append(self.deck.deal(1)[0])
        print(f"\n  {Colors.bold('TURN:')} {self._card_str(self.community)}")
        if not self._betting_round("Turn", active, 0):
            winner = self._last_active()
            self._award_pot(winner)
            return {"hand": self.hand_num, "winner": winner.name if winner else "?"}

        # ---- River ----
        self.community.append(self.deck.deal(1)[0])
        print(f"\n  {Colors.bold('RIVER:')} {self._card_str(self.community)}")
        if not self._betting_round("River", active, 0):
            winner = self._last_active()
            self._award_pot(winner)
            return {"hand": self.hand_num, "winner": winner.name if winner else "?"}

        # ---- Showdown ----
        winner = self._showdown(active)
        self._award_pot(winner)
        return {"hand": self.hand_num, "winner": winner.name}

    # ---- Betting Round ----

    def _betting_round(self, round_name: str, players: List[PokerPlayer], initial_bet: int) -> bool:
        """Run one betting round. Returns True if multiple players remain, False if all folded."""
        current_bet = initial_bet
        actions_log: List[str] = []
        active = [p for p in players if not p.folded and p.chips > 0]

        # Betting order starts after dealer
        start_idx = (self.dealer_idx + 1) % len(self.players)
        if round_name == "Pre-flop":
            start_idx = (self.dealer_idx + 3) % len(self.players)  # After BB

        # Track who has acted
        last_raiser_idx = -1
        acted_count = 0

        while True:
            all_acted = True
            for offset in range(len(self.players)):
                idx = (start_idx + offset) % len(self.players)
                player = self.players[idx]

                if player.folded or player.chips == 0:
                    continue

                # In first round, blinds have already acted partially
                if round_name == "Pre-flop" and acted_count == 0 and idx == (self.dealer_idx + 2) % len(self.players):
                    # BB has option if no raise
                    if current_bet == self.BIG_BLIND:
                        player.current_bet = self.BIG_BLIND
                        continue

                # Check if this player still needs to act
                to_call = current_bet - player.current_bet
                if to_call == 0 and last_raiser_idx != -1 and idx == last_raiser_idx:
                    continue  # Already acted and action closed
                if to_call == 0 and acted_count >= len(active):
                    # Everyone has acted and no raise pending
                    break

                if to_call > 0 or (to_call == 0 and idx != last_raiser_idx):
                    all_acted = False

                # Query the AI
                min_raise = max(self.BIG_BLIND, current_bet * 2 - current_bet) if current_bet > 0 else self.BIG_BLIND
                position_desc = self._position_desc(idx, len(self.players), self.dealer_idx)

                prompt = betting_prompt(
                    player.name,
                    self._card_str(player.hole_cards).split(),
                    self._card_str(self.community).split() if self.community else [],
                    self.pot,
                    current_bet,
                    player.chips,
                    to_call,
                    min_raise,
                    round_name,
                    position_desc,
                    len(active),
                    actions_log[-6:],
                )

                print(f"\n  {Colors.dim(f'[{player.name}] deciding... (to call: {to_call}, pot: {self.pot})')}")
                _, parsed = self._query(player, round_name.lower().replace("-","_"), prompt, temp=0.6)
                action = parsed.get("action", "FOLD").strip().upper()
                reason = parsed.get("reason", "")

                if reason:
                    self._print_dim(f"  [{player.name}] {truncate(reason, 100)}")

                # Parse action
                if action.startswith("FOLD") or "FOLD" in action:
                    player.folded = True
                    print(f"  {player.name}: {Colors.color('FOLD', Colors.RED)}")
                    actions_log.append(f"{player.name}: FOLD")
                    self._log(f"{player.name} folds ({round_name})")

                elif action.startswith("CHECK") or "CHECK" in action:
                    print(f"  {player.name}: {Colors.color('CHECK', Colors.GREEN)}")
                    actions_log.append(f"{player.name}: CHECK")

                elif action.startswith("CALL") or "CALL" in action:
                    actual = player.bet(to_call)
                    self.pot += actual
                    print(f"  {player.name}: {Colors.color(f'CALL {actual}', Colors.YELLOW)}")
                    actions_log.append(f"{player.name}: CALL {actual}")

                elif action.startswith("RAISE") or "RAISE" in action:
                    # Parse raise amount
                    nums = re.findall(r'\d+', action)
                    raise_amount = int(nums[0]) if nums else min_raise
                    raise_amount = max(min_raise, raise_amount)
                    total_needed = raise_amount + to_call
                    actual = player.bet(total_needed)
                    self.pot += actual
                    current_bet = player.current_bet
                    last_raiser_idx = idx
                    # Reset acted count so others must respond
                    print(f"  {player.name}: {Colors.color(f'RAISE to {current_bet} ({actual})', Colors.CYAN)}")
                    actions_log.append(f"{player.name}: RAISE to {current_bet}")
                    self._log(f"{player.name} raises to {current_bet} ({round_name})")

                else:
                    # Default: call or check
                    if to_call > 0:
                        actual = player.bet(to_call)
                        self.pot += actual
                        print(f"  {player.name}: {Colors.color(f'CALL {actual}', Colors.YELLOW)}")
                        actions_log.append(f"{player.name}: CALL {actual}")
                    else:
                        print(f"  {player.name}: {Colors.color('CHECK', Colors.GREEN)}")
                        actions_log.append(f"{player.name}: CHECK")

                acted_count += 1

                # Check if only one active remains
                active = [p for p in self.players if not p.folded and p.chips > 0]
                if len(active) == 1:
                    return False

            if all_acted:
                break

        return True

    # ---- Showdown ----

    def _showdown(self, players: List[PokerPlayer]) -> Optional[PokerPlayer]:
        """Evaluate hands and determine winner."""
        active = [p for p in players if not p.folded]
        if not active:
            return None
        if len(active) == 1:
            return active[0]

        print(f"\n  {Colors.bold('SHOWDOWN:')}")
        best_player = None
        best_rank = -1
        best_kickers = []
        best_name = ""

        for p in active:
            rank, name, kickers = evaluate_hand(p.hole_cards, self.community)
            print(f"  {p.name}: {self._card_str(p.hole_cards)} → {Colors.bold(name)}")
            if rank > best_rank or (rank == best_rank and kickers > best_kickers):
                best_rank, best_name, best_kickers, best_player = rank, name, kickers, p

        if best_player:
            print(f"\n  {Colors.color(f'🏆 {best_player.name} wins with {best_name}!', Colors.YELLOW)}")
            self._log(f"{best_player.name} wins hand #{self.hand_num} with {best_name}")

        return best_player

    def _award_pot(self, winner: Optional[PokerPlayer]) -> None:
        if winner:
            winner.chips += self.pot
            print(f"  {winner.name} collects {self.pot} chips (now: {winner.chips})")
            self._log(f"{winner.name} wins pot of {self.pot}")

    def _last_active(self) -> Optional[PokerPlayer]:
        active = [p for p in self.players if not p.folded and p.chips > 0]
        return active[0] if active else None

    # ---- Helpers ----

    def _card_str(self, cards: List[Card]) -> str:
        return " ".join(str(c) for c in cards)

    def _position_desc(self, idx: int, total: int, dealer: int) -> str:
        if idx == dealer: return "BTN (dealer)"
        if idx == (dealer + 1) % total: return "SB (small blind)"
        if idx == (dealer + 2) % total: return "BB (big blind)"
        if idx == (dealer - 1) % total: return "CO (cutoff)"
        return f"MP (middle)"

    def _log(self, msg: str) -> None:
        self.game_log.append(msg)

    def _print_dim(self, text):
        print(f"  {Colors.dim(text)}")

    # ---- Win ----

    def check_win(self) -> Optional[str]:
        active = [p for p in self.players if p.chips > 0]
        if len(active) <= 1:
            return active[0].name if active else "none"
        return None

    def run(self, max_rounds=50, verbose=True):
        self.setup()
        for _ in range(max_rounds):
            self.round += 1
            result = self.step()
            self.log.append(result)
            winner = self.check_win()
            if winner:
                self.finished = True
                self.winner = winner
                if verbose:
                    self._print_result()
                if self.logger:
                    self.logger.write_summary(self.players, winner, self.round, self.game_log)
                return winner
        return None

    # ---- Display ----

    def _print_setup(self):
        pass

    def _print_result(self):
        print(f"\n{Colors.bold('='*50)}")
        print(Colors.bold(f"  GAME OVER — {self.winner} wins!"))
        print(Colors.bold('='*50))
        for p in sorted(self.players, key=lambda x: x.chips, reverse=True):
            print(f"  {p.name:12s} {p.chips} chips")
