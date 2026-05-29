"""Werewolf game engine - orchestrates the full game flow.

Game flow:
  Night: Werewolves kill → Seer checks → Witch acts → Resolve deaths
  Day:   Announce → Discuss → Vote → Eliminate → Hunter? → Check win
  Repeat until one faction wins.
"""

import random
import time
from typing import Dict, List, Optional, Tuple

from core.engine import GameEngine
from core.logger import GameLogger
from core.player import Player
from core.utils import (
    Colors,
    count_votes,
    format_alive_players,
    majority_vote,
    parse_keyword_response,
    truncate,
)

from .player import WerewolfPlayer
from .prompts import (
    day_discussion_prompt,
    day_vote_prompt,
    hunter_shot_prompt,
    night_seer_prompt,
    night_werewolf_prompt,
    night_witch_prompt,
)
from .roles import Faction, Role, get_role_set


class WerewolfEngine(GameEngine):
    """Full Werewolf game engine.

    Handles:
    - Role assignment and shuffling
    - Night phase orchestration (werewolf kill, seer check, witch actions)
    - Day phase orchestration (announcement, discussion, voting, hunter shot)
    - Win condition checking
    - Pretty terminal output with colors
    """

    def __init__(
        self,
        players: List[WerewolfPlayer],
        config: dict | None = None,
        logger: GameLogger | None = None,
    ):
        # Ensure all players are WerewolfPlayer instances
        for p in players:
            if not isinstance(p, WerewolfPlayer):
                raise TypeError(
                    f"All players must be WerewolfPlayer instances. "
                    f"Got {type(p).__name__} for '{p.name}'"
                )
        super().__init__(players, config)
        self.game_log: List[str] = []  # Public game event log
        self.logger = logger  # File logger (None = no disk logging)
        self._log_round_num = 0  # Track round for logger context

    # ---- Query helper (logs everything) ----

    def _query_player(
        self,
        player: WerewolfPlayer,
        phase: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.8,
    ) -> Tuple[str, dict]:
        """Query a player's model, logging prompt & response to disk.

        Returns (raw_response, parsed_dict).
        parsed_dict has keys: reason, target, vote, speech, save, poison.
        """
        t0 = time.time()

        # Log prompt
        prompt_idx = None
        if self.logger:
            prompt_idx = self.logger.log_prompt(
                player_name=player.name,
                phase=phase,
                round_num=self._log_round_num,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

        # Call model — returns (thinking, content)
        model_thinking, response = player.chat(system_prompt, user_prompt, temperature=temperature)

        latency = (time.time() - t0) * 1000

        # Parse response (keyword format with tag fallback)
        parsed = parse_keyword_response(response)

        # Log response
        if self.logger:
            self.logger.log_response(
                player_name=player.name,
                phase=phase,
                round_num=self._log_round_num,
                raw_response=response,
                parsed=parsed,
                prompt_index=prompt_idx or 0,
                latency_ms=round(latency, 1),
            )

        return response, parsed

    # ================================================================
    #  Setup
    # ================================================================

    def setup(self) -> None:
        """Assign roles to players randomly."""
        num_players = len(self.players)
        roles = get_role_set(num_players)

        # Ensure we have exactly the right number of roles
        if len(roles) < num_players:
            roles = list(roles)
            roles.extend([Role("villager", "Villager (村民)", Faction.VILLAGER, "...")]
                         * (num_players - len(roles)))

        random.shuffle(roles)
        random.shuffle(self.players)  # Randomize player order

        for player, role in zip(self.players, roles):
            player.assign_role(role)

        # Tell werewolves who their partners are
        wolves = [p for p in self.players if p.is_werewolf]
        wolf_names = [w.name for w in wolves]
        for wolf in wolves:
            wolf.fellow_wolves = [n for n in wolf_names if n != wolf.name]
            wolf.memory.append(f"Your fellow werewolves: {', '.join(wolf.fellow_wolves)}")

        self._log("The game begins. Roles have been assigned in secret.")

        # Log to file
        if self.logger:
            self.logger.log_game_start(self.players)

    # ================================================================
    #  Main Step
    # ================================================================

    def step(self) -> dict:
        """Execute one full round (night + day).

        Returns a dict summarizing the round's events.
        """
        self._log_round_num = self.round
        round_data = {"round": self.round, "night": {}, "day": {}}
        if self.logger:
            self.logger.log_round_start(self.round)

        # ---- Night Phase ----
        night_deaths: List[str] = []

        # 1. Werewolves choose a target
        if self._wolves_alive():
            target = self._night_werewolf_kill()
            round_data["night"]["werewolf_target"] = target
            # NOTE: do NOT log werewolf target yet — seer/witch prompts read game_log
            # and only the witch should know the target during night phase.

        # 2. Seer checks a player
        if self._seer_alive():
            check_result = self._night_seer_check()
            round_data["night"]["seer_check"] = check_result

        # 3. Witch acts
        if self._witch_alive():
            save, poison = self._night_witch_act(
                round_data["night"].get("werewolf_target", "")
            )
            round_data["night"]["witch_save"] = save
            round_data["night"]["witch_poison"] = poison

            # Resolve witch actions vs werewolf kill
            werewolf_target = round_data["night"].get("werewolf_target", "")
            if save and werewolf_target:
                self._log(f"The Witch used antidote to save {werewolf_target}")
                # Target is saved, not killed
            elif werewolf_target:
                night_deaths.append(werewolf_target)

            if poison:
                night_deaths.append(poison)
                self._log(f"The Witch used poison on {poison}")
        else:
            # No witch, werewolf kill goes through
            werewolf_target = round_data["night"].get("werewolf_target", "")
            if werewolf_target:
                night_deaths.append(werewolf_target)

        # Remove duplicates (if witch poisoned the same target)
        night_deaths = list(set(night_deaths))

        # Apply deaths
        for name in night_deaths:
            player = self._find_player(name)
            if player:
                player.kill()
                self._log(f"{name} died during the night")

        round_data["night"]["deaths"] = night_deaths

        # Now that night is over, log the werewolf target (witch already knew it)
        werewolf_target = round_data["night"].get("werewolf_target", "")
        if werewolf_target and werewolf_target not in night_deaths:
            self._log(f"Night {self.round}: Werewolves targeted {werewolf_target} (saved by witch)")

        # ---- Day Phase ----
        if self.finished:
            return round_data

        # Check for Hunter ability on night deaths
        for name in night_deaths:
            hunter = self._find_player(name)
            if hunter and hunter.role and hunter.role.role_id == "hunter":
                shot = self._hunter_shot(hunter)
                if shot:
                    target = self._find_player(shot)
                    if target:
                        target.kill()
                        self._log(f"Hunter {hunter.name} took {shot} down with them!")
                        night_deaths.append(shot)  # Display in announcement

        # Announce
        self._print_night_results(night_deaths)
        round_data["day"]["night_deaths"] = night_deaths

        # Check win after night deaths
        winner = self.check_win()
        if winner:
            return round_data

        # Discussion round
        discussion = self._day_discussion()
        round_data["day"]["discussion"] = discussion

        # Voting round
        vote_result = self._day_vote()
        round_data["day"]["vote"] = vote_result

        eliminated = vote_result.get("eliminated")
        if eliminated:
            player = self._find_player(eliminated)
            if player:
                player.kill()
                self._log(f"{eliminated} was voted out")

                # Hunter ability on elimination
                if player.role and player.role.role_id == "hunter":
                    shot = self._hunter_shot(player)
                    if shot:
                        target = self._find_player(shot)
                        if target:
                            target.kill()
                            self._log(
                                f"Hunter {player.name} shot {shot} before dying!"
                            )
                            round_data["day"]["hunter_shot"] = shot

        if self.logger:
            self.logger.log_round_end(self.round, round_data)
        return round_data

    # ================================================================
    #  Night Phase Helpers
    # ================================================================

    def _night_werewolf_kill(self) -> Optional[str]:
        """Have werewolves choose a kill target. They coordinate sequentially."""
        wolves = [p for p in self.alive_players if p.is_werewolf]
        if not wolves:
            return None

        alive_names = [p.name for p in self.alive_players]
        suggestions: List[str] = []       # Human-readable for display
        target_votes: List[str] = []      # Actual target names for voting

        for wolf in wolves:
            # Exclude werewolves from valid targets
            valid_targets = [
                n for n in alive_names
                if n not in [w.name for w in wolves]
            ]

            if not valid_targets:
                continue

            prompt = night_werewolf_prompt(
                alive_names=valid_targets,
                dead_names=[p.name for p in self.dead_players],
                fellow_wolves=wolf.fellow_wolves,
                game_log=self.game_log[-12:],
                previous_suggestions=suggestions if suggestions else None,
            )
            system = wolf.get_system_prompt(self.players)

            self._print_player_action(wolf, "choosing kill target...")
            response, parsed = self._query_player(
                wolf, "night_werewolf", system, prompt, temperature=0.9,
            )
            target_name = parsed["target"]
            reason = parsed["reason"]

            # Use parsed target directly
            target = target_name if target_name in valid_targets else None
            if target:
                suggestions.append(f"{wolf.name} wants to kill {target}")
                target_votes.append(target)
                wolf.memory.append(
                    f"Night {self.round}: You suggested killing {target}"
                )
            else:
                # Fallback: pick randomly from valid non-wolf targets
                if valid_targets:
                    target = random.choice(valid_targets)
                    suggestions.append(f"{wolf.name} wants to kill {target} (random)")
                    target_votes.append(target)

            if reason:
                self._print_dim(f"  [{wolf.name}] {truncate(reason, 150)}")

        # Majority vote among werewolves (use actual target names, not description strings)
        target = majority_vote(target_votes)

        # Fallback
        if not target:
            valid = [p.name for p in self.alive_players if not p.is_werewolf]
            target = random.choice(valid) if valid else None

        return target

    def _night_seer_check(self) -> Optional[str]:
        """Have the Seer check a player's identity."""
        seer = self._find_role("seer")
        if not seer:
            return None

        alive_names = [p.name for p in self.alive_players]
        # Get previous checks from memory
        prev_checks = [
            m for m in seer.memory if m.startswith("Night") and "checked" in m
        ]

        prompt = night_seer_prompt(
            alive_names=alive_names,
            dead_names=[p.name for p in self.dead_players],
            previous_checks=prev_checks,
            game_log=self.game_log[-8:],
        )
        system = seer.get_system_prompt(self.players)

        self._print_player_action(seer, "checking a player...")
        response, parsed = self._query_player(
            seer, "night_seer", system, prompt, temperature=0.7,
        )
        target = parsed["target"]
        reason = parsed["reason"]
        if not target or target not in alive_names:
            target = random.choice([n for n in alive_names if n != seer.name])

        # Reveal identity to seer
        checked_player = self._find_player(target)
        if checked_player and checked_player.role:
            identity = "WEREWOLF" if checked_player.is_werewolf else "VILLAGER"
            result_msg = f"Night {self.round}: You checked {target} — they are a {identity}"
            seer.memory.append(result_msg)
            seer.remember(result_msg)

        if reason:
            self._print_dim(f"  [{seer.name}] {truncate(reason, 150)}")
        self._print_dim(f"  Seer checked: {target}")

        return target

    def _night_witch_act(self, werewolf_target: str) -> Tuple[bool, Optional[str]]:
        """Have the Witch decide save/poison. Returns (used_save, poison_target)."""
        witch = self._find_role("witch")
        if not witch:
            return False, None

        has_antidote = not any("used antidote" in m.lower() for m in witch.memory)
        has_poison = not any("used poison" in m.lower() for m in witch.memory)

        alive_names = [p.name for p in self.alive_players]

        prompt = night_witch_prompt(
            alive_names=alive_names,
            dead_names=[p.name for p in self.dead_players],
            werewolf_target=werewolf_target or "no one",
            has_antidote=has_antidote,
            has_poison=has_poison,
            game_log=self.game_log[-8:],
        )
        system = witch.get_system_prompt(self.players)

        self._print_player_action(witch, "deciding on potions...")
        response, parsed = self._query_player(
            witch, "night_witch", system, prompt, temperature=0.6,
        )
        reason = parsed["reason"]

        # Parse save/poison from keyword format
        use_save = parsed["save"].lower() == "yes" and has_antidote
        poison_target = parsed["poison"].strip()
        if poison_target.lower() in ("none", "no one", ""):
            poison_target = None
        if poison_target and (poison_target not in alive_names or not has_poison):
            poison_target = None

        if use_save:
            witch.memory.append(f"Night {self.round}: Used antidote to save {werewolf_target}")
        if poison_target:
            witch.memory.append(f"Night {self.round}: Used poison on {poison_target}")

        if reason:
            self._print_dim(f"  [{witch.name}] {truncate(reason, 150)}")
        self._print_dim(
            f"  Witch: save={'yes' if use_save else 'no'}, "
            f"poison={poison_target or 'none'}"
        )

        return use_save, poison_target

    # ================================================================
    #  Day Phase Helpers
    # ================================================================

    def _day_discussion(self) -> List[str]:
        """Run the day discussion. Each alive player speaks once."""
        alive = self.alive_players
        night_deaths = [
            e for e in self.game_log[-3:]
            if "died" in e.lower() or "killed" in e.lower()
        ]
        night_summary = "; ".join(night_deaths) if night_deaths else "No one died"

        discussion_log: List[str] = []

        for player in alive:
            prompt = day_discussion_prompt(
                player_name=player.name,
                alive_names=[p.name for p in alive],
                dead_names=[p.name for p in self.dead_players],
                night_summary=night_summary,
                discussion_history=discussion_log,
                game_log=self.game_log[-8:],
            )
            system = player.get_system_prompt(self.players)

            self._print_player_action(player, "speaking...")
            response, parsed = self._query_player(
                player, "day_discussion", system, prompt, temperature=0.85,
            )
            speech = parsed["speech"] or response
            reason = parsed["reason"]

            entry = f"{player.name}: {speech}"
            discussion_log.append(entry)

            if reason:
                self._print_dim(f"  [{player.name}] {truncate(reason, 120)}")
            print(f"  {Colors.color(player.name, Colors.CYAN)}: {speech}")

            player.memory.append(f"Round {self.round} discussion: You said: {speech}")

        return discussion_log

    def _day_vote(self) -> dict:
        """Run the voting round. Each alive player votes for someone to eliminate."""
        alive = self.alive_players
        alive_names = [p.name for p in alive]

        # Summarize discussion for the voting prompt
        discussion_summary = (
            f"{len(alive)} players discussed. Time to vote."
        )

        votes: List[Optional[str]] = []
        vote_record: Dict[str, str] = {}

        for player in alive:
            prompt = day_vote_prompt(
                player_name=player.name,
                alive_names=alive_names,
                dead_names=[p.name for p in self.dead_players],
                discussion_summary=discussion_summary,
                game_log=self.game_log[-6:],
            )
            system = player.get_system_prompt(self.players)

            self._print_player_action(player, "voting...")
            response, parsed = self._query_player(
                player, "day_vote", system, prompt, temperature=0.5,
            )
            vote_target = parsed["vote"]
            speech = parsed["speech"]
            if vote_target and vote_target in alive_names:
                votes.append(vote_target)
                vote_record[player.name] = vote_target
            else:
                votes.append(None)
                vote_record[player.name] = "abstain"

            if speech:
                print(f"  {Colors.color(player.name, Colors.CYAN)}: {speech}")

        # Tally
        print(f"\n  {Colors.bold('Vote results:')}")
        for voter, target in vote_record.items():
            print(f"    {voter} → {target}")

        vote_counts = count_votes(votes)
        eliminated = majority_vote(votes)

        if eliminated:
            count = vote_counts.get(eliminated, 0)
            total = len([v for v in votes if v is not None])
            print(
                f"\n  {Colors.color(f'{eliminated} was eliminated! ({count}/{total} votes)', Colors.RED)}"
            )
        else:
            print(f"\n  {Colors.color('No one was eliminated (tie or abstentions).', Colors.YELLOW)}")

        return {
            "votes": vote_record,
            "vote_counts": vote_counts,
            "eliminated": eliminated,
        }

    def _hunter_shot(self, hunter: WerewolfPlayer) -> Optional[str]:
        """Trigger the Hunter's death ability."""
        alive_names = [p.name for p in self.alive_players if p.name != hunter.name]
        if not alive_names:
            return None

        prompt = hunter_shot_prompt(
            alive_names=alive_names,
            dead_names=[p.name for p in self.dead_players],
            game_log=self.game_log[-8:],
        )
        system = hunter.get_system_prompt(self.players)

        self._print_player_action(hunter, "choosing a target (Hunter ability)...")
        response, parsed = self._query_player(
            hunter, "hunter_shot", system, prompt, temperature=0.8,
        )
        target = parsed["target"]
        speech = parsed["speech"]
        if target in ("none", "no one", ""):
            target = None
        # Validate: only shoot alive players
        if target and target not in alive_names:
            print(f"  {Colors.dim(f'Invalid target {target} (not alive), skipping shot.')}")
            target = None

        if speech:
            print(f"  {Colors.color(hunter.name, Colors.YELLOW)}: {speech}")

        if target:
            print(
                f"  {Colors.color(f'💥 Hunter shoots {target}!', Colors.RED)}"
            )
        else:
            print(f"  {Colors.dim('Hunter chose not to shoot anyone.')}")

        return target

    # ================================================================
    #  Win Condition
    # ================================================================

    def check_win(self) -> Optional[str]:
        """Check if either faction has won.

        Returns:
            'werewolf' if werewolves win
            'villager' if villagers win
            None if game continues
        """
        alive_wolves = sum(1 for p in self.alive_players if p.is_werewolf)
        alive_villagers = sum(1 for p in self.alive_players if p.is_villager_team)

        if alive_wolves == 0:
            return "villager"
        if alive_wolves >= alive_villagers:
            return "werewolf"
        return None

    # ================================================================
    #  Run (with summary logging)
    # ================================================================

    def run(self, max_rounds: int = 100, verbose: bool = True) -> Optional[str]:
        """Run the game, writing a summary to disk when finished."""
        winner = super().run(max_rounds=max_rounds, verbose=verbose)

        if self.logger:
            path = self.logger.write_summary(
                players=self.players,
                winner=winner,
                total_rounds=self.round,
                game_log=self.game_log,
            )
            if verbose:
                print(f"\n{Colors.dim(f'📁 Full logs saved to: {self.logger.log_dir}')}")
                print(f"{Colors.dim(f'   Summary: {path}')}")

        return winner

    # ================================================================
    #  Helpers
    # ================================================================

    def _find_player(self, name: str) -> Optional[WerewolfPlayer]:
        """Find a player by name (case-insensitive partial match)."""
        name_lower = name.lower().strip()
        for p in self.players:
            if p.name.lower() == name_lower:
                return p
        # Partial match
        for p in self.players:
            if name_lower in p.name.lower():
                return p
        return None

    def _find_role(self, role_id: str) -> Optional[WerewolfPlayer]:
        """Find the first alive player with the given role."""
        for p in self.alive_players:
            if p.role and p.role.role_id == role_id:
                return p
        return None

    def _wolves_alive(self) -> bool:
        return any(p.is_werewolf for p in self.alive_players)

    def _seer_alive(self) -> bool:
        return self._find_role("seer") is not None

    def _witch_alive(self) -> bool:
        return self._find_role("witch") is not None

    @staticmethod
    def _parse_target(action_text: str, keyword: str) -> Optional[str]:
        """Extract a player name from an action string like 'KILL: Alice'."""
        if not action_text:
            return None
        text = action_text.strip()
        # Try "KEYWORD: Name" format
        prefix = f"{keyword.upper()}:"
        if prefix in text.upper():
            idx = text.upper().find(prefix) + len(prefix)
            target = text[idx:].strip().rstrip(".,;!?")
            # Remove any trailing text after the name
            for delim in [",", "(", "（"]:
                if delim in target:
                    target = target.split(delim)[0].strip()
            return target if target else None
        # Try just the first word as fallback
        first_word = text.split()[0].rstrip(".,;!?")
        if first_word.upper() != keyword.upper():
            return first_word
        return None

    @staticmethod
    def _last_word(text: str) -> Optional[str]:
        """Get the last word of a string as a fallback target."""
        words = text.strip().split()
        return words[-1].rstrip(".,;!?") if words else None

    def _log(self, message: str) -> None:
        """Add a public game log entry."""
        self.game_log.append(message)

    # ================================================================
    #  Display
    # ================================================================

    def _print_setup(self) -> None:
        """Print the initial game setup."""
        print(f"\n  {Colors.bold('Players and their roles (secret):')}")
        print(f"  {'─' * 45}")
        for p in self.players:
            model_info = f"{p.model.model_name}"
            role_color = Colors.RED if p.is_werewolf else Colors.GREEN
            role_name = (p.role.name if p.role else '???').ljust(25)
            print(
                f"  {p.name:12s} → {Colors.color(role_name, role_color)}"
                f"  [{model_info}]"
            )
        print()

    def _print_night_results(self, deaths: List[str]) -> None:
        """Announce the night's deaths."""
        print(f"\n  {Colors.bold('☀ Day breaks...')}")
        if deaths:
            for name in deaths:
                print(
                    f"  {Colors.color(f'💀 {name} was found dead!', Colors.RED)}"
                )
        else:
            print(f"  {Colors.color('Last night was peaceful. No one died.', Colors.GREEN)}")

    def _print_player_action(self, player: WerewolfPlayer, action: str) -> None:
        """Print a dim status line for a player's action."""
        role_icon = "🐺" if player.is_werewolf else "👤"
        model_short = player.model.model_name[:20]
        print(
            f"\n  {Colors.dim(f'[{role_icon} {player.name} ({model_short})] {action}')}"
        )

    def _print_dim(self, text: str) -> None:
        """Print dimmed text."""
        print(f"  {Colors.dim(text)}")

    def _print_result(self) -> None:
        """Print the final result."""
        self._print_header("GAME OVER")
        if self.winner == "villager":
            print(
                f"\n  {Colors.color('🏆 The VILLAGER team wins! All werewolves eliminated.', Colors.GREEN)}"
            )
        elif self.winner == "werewolf":
            print(
                f"\n  {Colors.color('🐺 The WEREWOLVES win! They have taken over the village.', Colors.RED)}"
            )

        print(f"\n  {Colors.bold('Final roles revealed:')}")
        for p in self.players:
            status = "💀" if not p.alive else "✓"
            role_color = Colors.RED if p.is_werewolf else Colors.GREEN
            print(
                f"  {status} {p.name:12s} — {Colors.color(p.role.name if p.role else '???', role_color)}"
                f"  [{p.model.model_name}]"
            )

        print(f"\n  {Colors.bold('Game log:')}")
        for entry in self.game_log:
            print(f"  {Colors.dim('•')} {entry}")

    def _print_header(self, text: str) -> None:
        print(f"\n{Colors.bold('=' * 55)}")
        print(Colors.bold(f"  {text}"))
        print(Colors.bold('=' * 55))
