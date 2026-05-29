"""Codenames game engine — spymaster clues, guesser picks."""

import time
from typing import List, Optional

from core.engine import GameEngine
from core.logger import GameLogger
from core.utils import Colors, parse_keyword_response, truncate

from .board import CodenamesBoard
from .player import CodenamesPlayer
from .prompts import guesser_prompt, spymaster_prompt


class CodenamesEngine(GameEngine):
    """Codenames engine. No real "rounds" — teams alternate turns."""

    def __init__(
        self,
        players: List[CodenamesPlayer],
        config: dict | None = None,
        logger: GameLogger | None = None,
    ):
        for p in players:
            if not isinstance(p, CodenamesPlayer):
                raise TypeError(f"All players must be CodenamesPlayer, got {type(p).__name__}")
        super().__init__(players, config)
        self.board = CodenamesBoard()
        self.logger = logger
        self.game_log: List[str] = []
        self.previous_clues: List[str] = []
        self.turn_count = 0

    # ---- Query helper ----

    def _query(self, player, phase: str, prompt: str, temp=0.7):
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
        print(f"\n  {Colors.bold('Starting team:')} {Colors.color(self.board.starting_team.upper(), Colors.RED if self.board.starting_team == 'red' else Colors.BLUE)}")
        print(f"\n  {Colors.bold('Board (25 words, 5x5):')}")
        print(self.board.display_for_guesser())

        if self.logger:
            self.logger.log_event("game_start", {
                "players": [{"name": p.name, "team": p.team, "role": p.role} for p in self.players],
                "starting_team": self.board.starting_team,
            })

    def get_spymaster(self, team: str) -> Optional[CodenamesPlayer]:
        for p in self.players:
            if p.team == team and p.is_spymaster:
                return p
        return None

    def get_guesser(self, team: str) -> Optional[CodenamesPlayer]:
        for p in self.players:
            if p.team == team and p.is_guesser:
                return p
        return None

    # ---- Step (one team's turn) ----

    def step(self) -> dict:
        self.turn_count += 1
        team = self.board.current_team
        opponent = "blue" if team == "red" else "red"
        team_color = Colors.RED if team == "red" else Colors.BLUE

        spymaster = self.get_spymaster(team)
        guesser = self.get_guesser(team)

        if not spymaster or not guesser:
            print(f"  {Colors.color(f'Missing player for {team} team!', Colors.RED)}")
            return {"turn": self.turn_count, "error": "missing_player"}

        my_remaining = self.board.red_remaining if team == "red" else self.board.blue_remaining
        opp_remaining = self.board.blue_remaining if team == "red" else self.board.red_remaining

        print(f"\n  {Colors.bold(f'— Turn {self.turn_count}: {team.upper()} team —')}")
        print(f"  Remaining: {Colors.color(str(my_remaining), team_color)} {team} / {opp_remaining} {opponent}")

        # ---- Spymaster gives clue ----
        sm_prompt = spymaster_prompt(
            spymaster.name, team,
            self.board.display_for_spymaster(),
            opp_remaining, my_remaining,
            self.previous_clues,
        )
        print(f"\n  {Colors.dim(f'[{spymaster.name}] thinking of a clue...')}")
        _, sm_parsed = self._query(spymaster, "spymaster", sm_prompt, temp=0.9)
        clue_word = sm_parsed.get("clue", "").strip().lower()
        clue_count_str = sm_parsed.get("count", "1").strip()
        try:
            clue_count = int(clue_count_str)
        except ValueError:
            clue_count = 1

        clue_reason = sm_parsed.get("reason", "")
        if clue_reason:
            self._print_dim(f"  [{spymaster.name}] {truncate(clue_reason, 120)}")

        if not clue_word:
            clue_word = "thing"
            clue_count = 1

        self.previous_clues.append(f"{team}: {clue_word} ({clue_count})")
        self._log(f"Turn {self.turn_count}: {team} spymaster gives clue '{clue_word}' ({clue_count})")
        print(f"  {Colors.bold(f'Clue: {clue_word.upper()} ({clue_count})')}")

        # Check for illegal clue (word on board)
        if clue_word in [w.lower() for w in self.board.words if not self.board.revealed[w]]:
            print(f"  {Colors.color('⚠ Illegal clue (word on board)! Turn forfeited.', Colors.YELLOW)}")
            self.board.current_team = opponent
            return {"turn": self.turn_count, "team": team, "clue": clue_word, "illegal": True}

        # ---- Guesser picks ----
        guesses_remaining = clue_count + 1
        guessed_this_turn = []

        for guess_num in range(guesses_remaining):
            board_view = self.board.display_for_guesser()
            g_prompt = guesser_prompt(
                guesser.name, team, board_view, clue_word, clue_count,
                self.previous_clues,
            )
            print(f"\n  {Colors.dim(f'[{guesser.name}] choosing words... (guess {guess_num+1}/{guesses_remaining})')}")
            _, g_parsed = self._query(guesser, "guesser", g_prompt, temp=0.7)
            g_reason = g_parsed.get("reason", "")
            guess_str = g_parsed.get("guess", "PASS").strip()

            if g_reason:
                self._print_dim(f"  [{guesser.name}] {truncate(g_reason, 120)}")

            if guess_str.upper() == "PASS":
                print(f"  {Colors.dim(f'{guesser.name} passes.')}")
                break

            guesses = [g.strip().lower() for g in guess_str.split(",") if g.strip()]
            for guess_word in guesses:
                if guess_word.upper() == "PASS":
                    break

                color = self.board.reveal(guess_word)
                guessed_this_turn.append((guess_word, color))

                if color == team:
                    print(f"  {Colors.color(f'✓ {guess_word} → {team.upper()} AGENT!', team_color)}")
                    self._log(f"Turn {self.turn_count}: {guesser.name} correctly guessed {guess_word} ({team})")
                elif color == opponent:
                    print(f"  {Colors.color(f'✗ {guess_word} → {opponent.upper()} AGENT!', Colors.RED if opponent == 'red' else Colors.BLUE)}")
                    self._log(f"Turn {self.turn_count}: {guesser.name} guessed {guess_word} ({opponent} team)")
                    self.board.current_team = opponent
                    break
                elif color == "neutral":
                    print(f"  {Colors.color(f'○ {guess_word} → NEUTRAL', Colors.YELLOW)}")
                    self._log(f"Turn {self.turn_count}: {guesser.name} guessed {guess_word} (neutral)")
                    self.board.current_team = opponent
                    break
                elif color == "assassin":
                    print(f"  {Colors.color(f'💀 {guess_word} → ASSASSIN! Game over!', Colors.RED)}")
                    self._log(f"Turn {self.turn_count}: {guesser.name} hit the ASSASSIN ({guess_word})")
                    self.finished = True
                    self.winner = opponent
                    return {"turn": self.turn_count, "team": team, "assassin_hit": True}

                # Check win after each correct guess
                over, winner = self.board.is_game_over()
                if over:
                    self.finished = True
                    self.winner = winner
                    return {"turn": self.turn_count, "team": team, "winner": winner}

            # If we hit opponent/neutral/assassin, inner loop already broke and switched teams
            if self.board.current_team == opponent or self.finished:
                break
        else:
            # All guesses used up without hitting wrong color — still this team's turn continues
            # But in standard Codenames, turn ends after guesses are done if no wrong hit
            pass

        # Switch turn if no game-ending event happened
        if not self.finished:
            self.board.current_team = opponent

        return {
            "turn": self.turn_count, "team": team, "clue": clue_word, "count": clue_count,
            "guesses": guessed_this_turn,
        }

    # ---- Win Condition ----

    def check_win(self) -> Optional[str]:
        over, winner = self.board.is_game_over()
        if over:
            return winner
        return None

    # ---- Helpers ----

    def _log(self, msg: str) -> None:
        self.game_log.append(msg)

    def _print_dim(self, text):
        print(f"  {Colors.dim(text)}")

    # ---- Run ----

    def run(self, max_rounds=50, verbose=True):
        winner = super().run(max_rounds=max_rounds, verbose=verbose)
        if self.logger:
            self.logger.write_summary(self.players, winner, self.turn_count, self.game_log)
        return winner

    # ---- Display ----

    def _print_setup(self):
        pass  # Already printed in setup()

    def _print_result(self):
        w = self.winner or "?"
        c = Colors.RED if w == "red" else Colors.BLUE
        print(f"\n  {Colors.color(f'🏆 {w.upper()} team wins!', c)}")
        print(f"\n  {Colors.bold('Full board revealed:')}")
        print(self.board.display_for_spymaster())
