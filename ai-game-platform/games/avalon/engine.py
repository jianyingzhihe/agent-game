"""Avalon game engine — team proposals, voting, quests, assassin guess."""

import random
import time
from typing import Dict, List, Optional, Tuple

from core.engine import GameEngine
from core.logger import GameLogger
from core.utils import Colors, count_votes, majority_vote, parse_keyword_response, truncate

from .player import AvalonPlayer
from .prompts import (
    assassin_guess_prompt,
    propose_team_prompt,
    quest_vote_prompt,
    vote_team_prompt,
)
from .roles import Faction, Role, get_quest_sizes, get_role_set


class AvalonEngine(GameEngine):
    """Avalon game engine. No elimination — everyone plays all rounds."""

    def __init__(
        self,
        players: List[AvalonPlayer],
        config: dict | None = None,
        logger: GameLogger | None = None,
    ):
        for p in players:
            if not isinstance(p, AvalonPlayer):
                raise TypeError(f"All players must be AvalonPlayer, got {type(p).__name__}")
        super().__init__(players, config)
        self.game_log: List[str] = []
        self.logger = logger
        self._log_round_num = 0
        self.quest_sizes: List[int] = []
        self.quest_results: List[dict] = []   # [{num, team, votes, success/fail}]
        self.good_wins = 0
        self.evil_wins = 0
        self.reject_count = 0
        self.leader_index = 0

    # ---- Query helper ----

    def _query(self, player, phase: str, system: str, prompt: str, temp=0.7):
        t0 = time.time()
        if self.logger:
            self.logger.log_prompt(player.name, phase, self._log_round_num, system, prompt)
        model_thinking, response = player.chat(system, prompt, temperature=temp)
        parsed = parse_keyword_response(response)
        if self.logger:
            self.logger.log_response(player.name, phase, self._log_round_num, response, parsed,
                                     prompt_index=0, latency_ms=(time.time()-t0)*1000)
        return response, parsed

    # ---- Setup ----

    def setup(self) -> None:
        num = len(self.players)
        roles = get_role_set(num)
        self.quest_sizes = get_quest_sizes(num)

        random.shuffle(roles)
        random.shuffle(self.players)

        for player, role in zip(self.players, roles):
            player.assign_role(role)

        # Knowledge distribution
        evil_players = [p for p in self.players if p.is_evil]
        evil_names = [p.name for p in evil_players]
        good_players = [p for p in self.players if p.is_good]

        merlin = next((p for p in self.players if p.role and p.role.role_id == "merlin"), None)
        percival = next((p for p in self.players if p.role and p.role.role_id == "percival"), None)
        morgana = next((p for p in self.players if p.role and p.role.role_id == "morgana"), None)
        assassin = next((p for p in self.players if p.role and p.role.role_id == "assassin"), None)

        # Evil know each other
        for evil in evil_players:
            evil.known_evil = [n for n in evil_names if n != evil.name]
            evil.memory.append(f"Fellow evil: {', '.join(evil.known_evil)}")

        # Merlin knows evil (except Mordred — skip for simplicity)
        if merlin:
            merlin.known_evil = evil_names
            merlin.memory.append(f"Evil players: {', '.join(evil_names)}")

        # Percival sees Merlin + Morgana
        if percival and merlin:
            candidates = [merlin.name]
            if morgana:
                candidates.append(morgana.name)
            random.shuffle(candidates)
            percival.merlin_candidates = candidates
            percival.memory.append(f"Merlin is one of: {', '.join(candidates)}")

        self._log("Avalon begins. Roles assigned in secret.")
        if self.logger:
            self.logger.log_game_start(self.players)

    # ---- Main Step (one quest round) ----

    def step(self) -> dict:
        self._log_round_num = self.round
        quest_num = self.round
        team_size = self.quest_sizes[quest_num - 1]

        print(f"\n  {Colors.bold(f'Quest {quest_num} — Team size: {team_size}')}")
        if self.logger:
            self.logger.log_round_start(self.round)

        # ---- Phase 1: Leader proposes team ----
        leader = self.players[self.leader_index % len(self.players)]
        print(f"  Leader: {Colors.color(leader.name, Colors.CYAN)}")

        system = leader.get_system_prompt(self.players)
        prompt = propose_team_prompt(
            leader.name, [p.name for p in self.players], team_size,
            quest_num, self.round,
            [f"Q{q['num']}: {'PASS' if q['passed'] else 'FAIL'} (team: {', '.join(q['team'])})"
             for q in self.quest_results],
        )
        self._print_action(leader, "proposing team...")
        _, parsed = self._query(leader, "propose_team", system, prompt, temp=0.8)
        reason = parsed.get("reason", "")

        # Parse team
        team_str = parsed.get("team", "")
        proposed = [n.strip() for n in team_str.split(",") if n.strip()]
        proposed = [n for n in proposed if self._find_player(n)]
        if len(proposed) != team_size:
            # Fallback: random
            pool = [p.name for p in self.players]
            random.shuffle(pool)
            proposed = pool[:team_size]

        if reason:
            self._print_dim(f"  [{leader.name}] {truncate(reason, 120)}")
        print(f"  Proposed: {Colors.bold(', '.join(proposed))}")

        # ---- Phase 2: Everyone votes on the team ----
        reject_streak = 0
        team_approved = False

        for attempt in range(4):  # Max 4 proposals
            if attempt > 0:
                # New leader proposes
                self.leader_index = (self.leader_index + 1) % len(self.players)
                leader = self.players[self.leader_index]
                print(f"\n  {Colors.dim(f'Re-proposal {attempt+1} — Leader: {leader.name}')}")
                system = leader.get_system_prompt(self.players)
                prompt = propose_team_prompt(
                    leader.name, [p.name for p in self.players], team_size,
                    quest_num, self.round,
                    [f"Q{q['num']}: {'PASS' if q['passed'] else 'FAIL'}"
                     for q in self.quest_results],
                )
                _, parsed = self._query(leader, "propose_team", system, prompt, temp=0.8)
                team_str = parsed.get("team", "")
                proposed = [n.strip() for n in team_str.split(",") if n.strip()]
                proposed = [n for n in proposed if self._find_player(n)]
                if len(proposed) != team_size:
                    pool = [p.name for p in self.players]
                    random.shuffle(pool)
                    proposed = pool[:team_size]
                print(f"  Proposed: {Colors.bold(', '.join(proposed))}")

            # On 4th consecutive rejection, force the team through
            if reject_streak >= 3:
                print(f"  {Colors.color('3 consecutive rejections — forcing this team through!', Colors.YELLOW)}")
                team_approved = True
                break

            # Collect votes
            votes_for = 0
            votes_against = 0
            vote_log = []

            for player in self.players:
                sys_p = player.get_system_prompt(self.players)
                vp = vote_team_prompt(
                    player.name, proposed, leader.name, quest_num,
                    vote_log,
                    [f"Q{q['num']}: {'PASS' if q['passed'] else 'FAIL'}"
                     for q in self.quest_results],
                )
                self._print_action(player, "voting on team...")
                _, vparsed = self._query(player, "vote_team", sys_p, vp, temp=0.6)
                vote = vparsed.get("vote", "").upper()
                vreason = vparsed.get("reason", "")

                if vote == "APPROVE" or "APPROVE" in vote:
                    votes_for += 1
                    vote_log.append(f"{player.name}: APPROVE")
                else:
                    votes_against += 1
                    vote_log.append(f"{player.name}: REJECT")

                if vreason:
                    self._print_dim(f"  [{player.name}] {truncate(vreason, 80)}")

            total = votes_for + votes_against
            print(f"\n  Vote: {Colors.color(str(votes_for), Colors.GREEN)} APPROVE / {Colors.color(str(votes_against), Colors.RED)} REJECT (need > {total//2})")

            if votes_for > total // 2:
                team_approved = True
                break
            else:
                reject_streak += 1

        if not team_approved:
            return {"quest": quest_num, "result": "no_team"}

        # ---- Phase 3: Quest — team members vote SUCCESS/FAIL secretly ----
        # Count evil players on the team for coordination hints
        evil_on_team_names = [n for n in proposed if self._find_player(n) and self._find_player(n).is_evil]
        evil_on_team_count = len(evil_on_team_names)

        quest_votes = []
        for name in proposed:
            player = self._find_player(name)
            if not player:
                continue
            sys_p = player.get_system_prompt(self.players)
            qp = quest_vote_prompt(
                player.name, proposed, quest_num,
                [f"Q{q['num']}: {'PASS' if q['passed'] else 'FAIL'}"
                 for q in self.quest_results],
                fellow_evil_on_team=evil_on_team_count if player.is_evil else 0,
                is_evil=player.is_evil,
            )
            self._print_action(player, "voting on quest (secret)...")
            _, qparsed = self._query(player, "quest_vote", sys_p, qp, temp=0.5)
            qvote = qparsed.get("quest", "").upper()
            qreason = qparsed.get("reason", "")

            is_fail = "FAIL" in qvote
            quest_votes.append({"player": name, "fail": is_fail})
            if qreason:
                self._print_dim(f"  [{player.name}] {truncate(qreason, 100)}")

        fail_count = sum(1 for v in quest_votes if v["fail"])
        quest_passed = fail_count == 0

        self.quest_results.append({
            "num": quest_num, "team": proposed, "passed": quest_passed,
            "fails": fail_count,
        })

        if quest_passed:
            self.good_wins += 1
            self._log(f"Quest {quest_num}: PASS ({fail_count} fails)")
            print(f"\n  {Colors.color(f'Quest {quest_num}: PASS ✓', Colors.GREEN)}")
        else:
            self.evil_wins += 1
            self._log(f"Quest {quest_num}: FAIL ({fail_count} fails)")
            print(f"\n  {Colors.color(f'Quest {quest_num}: FAIL ✗ ({fail_count} fails)', Colors.RED)}")

        self.leader_index = (self.leader_index + 1) % len(self.players)
        return {"quest": quest_num, "passed": quest_passed, "team": proposed}

    # ---- Win Condition ----

    def check_win(self) -> Optional[str]:
        if self.good_wins >= 3:
            # Assassin guess
            assassin = next((p for p in self.players if p.role and p.role.role_id == "assassin"), None)
            if assassin:
                return self._assassin_phase(assassin)
            return "good"
        if self.evil_wins >= 3:
            return "evil"
        return None

    def _assassin_phase(self, assassin: AvalonPlayer) -> str:
        print(f"\n  {Colors.bold('⚔ Good won 3 quests! Assassin gets one shot at Merlin...')}")

        sys_p = assassin.get_system_prompt(self.players)
        prompt = assassin_guess_prompt(
            assassin.name,
            [p.name for p in self.players],
            [f"Q{q['num']}: {'PASS' if q['passed'] else 'FAIL'} (fails: {q.get('fails', '?')})"
             for q in self.quest_results],
        )
        self._print_action(assassin, "choosing target...")
        _, parsed = self._query(assassin, "assassin_guess", sys_p, prompt, temp=0.6)
        target = parsed.get("target", "")
        reason = parsed.get("reason", "")

        merlin = next((p for p in self.players if p.role and p.role.role_id == "merlin"), None)

        if reason:
            self._print_dim(f"  [{assassin.name}] {truncate(reason, 150)}")

        if merlin and target.lower() == merlin.name.lower():
            print(f"\n  {Colors.color(f'💀 Assassin kills Merlin ({merlin.name})! Evil steals the victory!', Colors.RED)}")
            self._log(f"Assassin killed Merlin! Evil wins!")
            return "evil"
        else:
            print(f"\n  {Colors.color(f'❌ Assassin guessed {target}. Merlin was {merlin.name if merlin else "?"}. Good wins!', Colors.GREEN)}")
            self._log(f"Assassin missed. Good wins!")
            return "good"

    # ---- Helpers ----

    def _find_player(self, name: str) -> Optional[AvalonPlayer]:
        nl = name.lower().strip()
        for p in self.players:
            if p.name.lower() == nl:
                return p
        for p in self.players:
            if nl in p.name.lower():
                return p
        return None

    def _log(self, msg: str) -> None:
        self.game_log.append(msg)

    def _print_action(self, player, action):
        print(f"\n  {Colors.dim(f'[{player.name}] {action}')}")

    def _print_dim(self, text):
        print(f"  {Colors.dim(text)}")

    # ---- Run override ----

    def run(self, max_rounds=100, verbose=True):
        winner = super().run(max_rounds=max_rounds, verbose=verbose)
        if self.logger:
            path = self.logger.write_summary(self.players, winner, self.round, self.game_log)
            if verbose:
                print(f"\n{Colors.dim(f'📁 Logs: {self.logger.log_dir}')}")
        return winner

    # ---- Display ----

    def _print_setup(self):
        print(f"\n  {Colors.bold('Players & roles (secret):')}")
        for p in self.players:
            c = Colors.RED if p.is_evil else Colors.GREEN
            role_name = (p.role.name if p.role else '???').ljust(25)
            print(f"  {p.name:12s} → {Colors.color(role_name, c)} [{p.model.model_name}]")
        print()

    def _print_result(self):
        self._print_header("GAME OVER")
        w = self.winner or "?"
        c = Colors.GREEN if w == "good" else Colors.RED
        print(f"\n  {Colors.color(f'🏆 {w.upper()} team wins!', c)}")
        for p in self.players:
            rc = Colors.RED if p.is_evil else Colors.GREEN
            print(f"  {p.name:12s} — {Colors.color(p.role.name if p.role else '???', rc)}")

    def _print_header(self, text):
        print(f"\n{Colors.bold('='*50)}")
        print(Colors.bold(f"  {text}"))
        print(Colors.bold('='*50))
