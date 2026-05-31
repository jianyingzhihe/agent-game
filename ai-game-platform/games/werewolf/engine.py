"""Werewolf game engine - orchestrates the full game flow.

Game flow:
  Night: werewolves kill -> seer checks -> witch acts -> resolve deaths
  Day:   announce -> discuss -> vote -> eliminate -> hunter shot -> check win
  Repeat until one faction wins.
"""

import random
import time
from typing import Dict, List, Optional, Tuple

from core.engine import GameEngine
from core.logger import GameLogger
from core.utils import Colors, count_votes, majority_vote, parse_keyword_response, truncate

from .player import WerewolfPlayer
from .prompts import (
    day_discussion_prompt,
    day_final_statement_prompt,
    day_vote_prompt,
    hunter_shot_prompt,
    last_words_prompt,
    night_seer_prompt,
    night_werewolf_prompt,
    night_witch_prompt,
    runoff_discussion_prompt,
)
from .roles import VILLAGER, get_role_set


class WerewolfEngine(GameEngine):
    """Full Werewolf game engine."""

    def __init__(
        self,
        players: List[WerewolfPlayer],
        config: dict | None = None,
        logger: GameLogger | None = None,
    ):
        for player in players:
            if not isinstance(player, WerewolfPlayer):
                raise TypeError(
                    "All players must be WerewolfPlayer instances. "
                    f"Got {type(player).__name__} for '{player.name}'"
                )

        super().__init__(players, config)
        self.game_log: List[str] = []
        self.logger = logger
        self._log_round_num = 0
        self.public_vote_history: List[str] = []
        self.day_speech_history: List[str] = []

    # ---- Query helper ----

    def _query_player(
        self,
        player: WerewolfPlayer,
        phase: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.8,
    ) -> Tuple[str, dict]:
        """Query a player's model and log prompt/response."""
        t0 = time.time()

        prompt_idx = None
        if self.logger:
            prompt_idx = self.logger.log_prompt(
                player_name=player.name,
                phase=phase,
                round_num=self._log_round_num,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

        model_thinking, response = player.chat(
            system_prompt,
            user_prompt,
            temperature=temperature,
        )
        latency_ms = (time.time() - t0) * 1000
        parsed = parse_keyword_response(response)

        if self.logger:
            self.logger.log_response(
                player_name=player.name,
                phase=phase,
                round_num=self._log_round_num,
                raw_response=response,
                parsed=parsed,
                prompt_index=prompt_idx or 0,
                latency_ms=round(latency_ms, 1),
                thinking=model_thinking,
            )

        return response, parsed

    # ================================================================
    # Setup
    # ================================================================

    def setup(self) -> None:
        """Assign roles and initialize structured state."""
        num_players = len(self.players)
        roles = get_role_set(num_players)

        if len(roles) < num_players:
            roles = list(roles)
            roles.extend([VILLAGER] * (num_players - len(roles)))

        random.shuffle(roles)
        random.shuffle(self.players)

        for player, role in zip(self.players, roles):
            player.assign_role(role)

        all_player_names = [player.name for player in self.players]
        for player in self.players:
            player.initialize_state(all_player_names)

        wolves = [player for player in self.players if player.is_werewolf]
        wolf_names = [wolf.name for wolf in wolves]
        for wolf in wolves:
            partners = [name for name in wolf_names if name != wolf.name]
            wolf.set_fellow_wolves(partners)
            if partners:
                wolf.memory.append(f"你的狼人队友：{', '.join(partners)}")

        self._refresh_public_state()
        self._log("游戏开始，身份已秘密分配。")

        if self.logger:
            self.logger.log_game_start(self.players)

    # ================================================================
    # Main step
    # ================================================================

    def step(self) -> dict:
        """Execute one full round."""
        self._log_round_num = self.round
        round_data = {"round": self.round, "night": {}, "day": {}}

        if self.logger:
            self.logger.log_round_start(self.round)

        night_deaths: List[str] = []
        self._refresh_public_state()

        if self._wolves_alive():
            target = self._night_werewolf_kill()
            round_data["night"]["werewolf_target"] = target

        if self._seer_alive():
            round_data["night"]["seer_check"] = self._night_seer_check()

        if self._witch_alive():
            werewolf_target = round_data["night"].get("werewolf_target", "")
            save, poison = self._night_witch_act(werewolf_target)
            round_data["night"]["witch_save"] = save
            round_data["night"]["witch_poison"] = poison

            if save and werewolf_target:
                self._log(f"女巫使用了解药，救下了 {werewolf_target}")
            elif werewolf_target:
                night_deaths.append(werewolf_target)

            if poison:
                night_deaths.append(poison)
                self._log(f"女巫使用毒药毒杀了 {poison}")
        else:
            werewolf_target = round_data["night"].get("werewolf_target", "")
            if werewolf_target:
                night_deaths.append(werewolf_target)

        night_deaths = list(dict.fromkeys(night_deaths))

        for name in night_deaths:
            player = self._find_player(name)
            if player:
                player.kill()
                self._log(f"{name} 在夜晚死亡")

        round_data["night"]["deaths"] = night_deaths

        werewolf_target = round_data["night"].get("werewolf_target", "")
        if werewolf_target and werewolf_target not in night_deaths:
            self._log(
                f"第 {self.round} 夜：狼人袭击了 {werewolf_target}，但其被女巫救下"
            )

        if self.finished:
            return round_data

        for name in list(night_deaths):
            hunter = self._find_player(name)
            if hunter and hunter.role and hunter.role.role_id == "hunter":
                shot = self._hunter_shot(hunter)
                if shot:
                    target = self._find_player(shot)
                    if target:
                        target.kill()
                        self._log(f"猎人 {hunter.name} 临死带走了 {shot}！")
                        if shot not in night_deaths:
                            night_deaths.append(shot)

        self._refresh_public_state()
        self._print_night_results(night_deaths)
        round_data["day"]["night_deaths"] = list(night_deaths)

        winner = self.check_win()
        if winner:
            if self.logger:
                self.logger.log_round_end(self.round, round_data)
            return round_data

        self._refresh_public_state()
        discussion = self._day_discussion()
        round_data["day"]["discussion"] = discussion

        self._refresh_public_state(discussion_history=discussion)
        final_statements = self._day_final_statements(discussion)
        round_data["day"]["final_statements"] = final_statements

        self._refresh_public_state(discussion_history=discussion + final_statements)
        vote_result = self._day_vote(discussion, final_statements)
        round_data["day"]["vote"] = vote_result

        eliminated = vote_result.get("eliminated")
        if eliminated:
            player = self._find_player(eliminated)
            if player:
                last_words = self._last_words(
                    player,
                    elimination_reason=f"第 {self.round} 轮白天投票放逐",
                )
                round_data["day"]["last_words"] = {
                    "player": player.name,
                    "speech": last_words,
                }
                player.kill()
                self._log(f"{eliminated} 被投票放逐出局")
                self._refresh_public_state()

                if player.role and player.role.role_id == "hunter":
                    shot = self._hunter_shot(player)
                    if shot:
                        target = self._find_player(shot)
                        if target:
                            target.kill()
                            self._log(f"猎人 {player.name} 临出局前开枪带走了 {shot}！")
                            round_data["day"]["hunter_shot"] = shot

        self._refresh_public_state()

        if self.logger:
            self.logger.log_round_end(self.round, round_data)
        return round_data

    # ================================================================
    # Night helpers
    # ================================================================

    def _night_werewolf_kill(self) -> Optional[str]:
        """Have werewolves choose a kill target sequentially."""
        wolves = [player for player in self.alive_players if player.is_werewolf]
        if not wolves:
            return None

        alive_names = [player.name for player in self.alive_players]
        suggestions: List[str] = []
        target_votes: List[str] = []

        for wolf in wolves:
            valid_targets = [name for name in alive_names if name not in {w.name for w in wolves}]
            if not valid_targets:
                continue

            self._refresh_public_state()
            prompt = night_werewolf_prompt(
                alive_names=valid_targets,
                dead_names=[player.name for player in self.dead_players],
                fellow_wolves=wolf.fellow_wolves,
                game_log=self.game_log[-12:],
                previous_suggestions=suggestions if suggestions else None,
                coordination_notes=[
                    note["note"]
                    for note in wolf.private_state["werewolf"]["coordination_notes"]
                    if isinstance(note, dict) and "note" in note
                ],
                suspicion=wolf.belief_state["suspicion"],
                role_guesses=wolf.belief_state["role_guesses"],
                trust=wolf.belief_state["trust"],
            )
            system = wolf.get_system_prompt(self.players)

            self._print_player_action(wolf, "选择击杀目标中...")
            _, parsed = self._query_player(
                wolf,
                "night_werewolf",
                system,
                prompt,
                temperature=0.9,
            )
            target_name = parsed["target"]
            reason = parsed["reason"]
            plan = parsed.get("plan", "")
            self._apply_inference_fields(wolf, parsed)

            target = target_name if target_name in valid_targets else None
            if target:
                suggestions.append(f"{wolf.name} 建议击杀 {target}")
                target_votes.append(target)
                wolf.record_werewolf_plan(
                    self.round,
                    suggested_target=target,
                    plan=plan,
                    coordination_note=f"{wolf.name}: 目标={target}; 策略={plan or 'none'}",
                )
                wolf.memory.append(f"第 {self.round} 夜：你建议击杀 {target}")
            elif valid_targets:
                target = random.choice(valid_targets)
                suggestions.append(f"{wolf.name} 建议击杀 {target}（随机）")
                target_votes.append(target)
                wolf.record_werewolf_plan(
                    self.round,
                    suggested_target=target,
                    plan=plan,
                    coordination_note=f"{wolf.name}: 回退随机目标={target}",
                )

            if reason:
                self._print_dim(f"[{wolf.name}] {truncate(reason, 150)}")

        target = majority_vote(target_votes)
        if not target:
            valid = [player.name for player in self.alive_players if not player.is_werewolf]
            target = random.choice(valid) if valid else None

        return target

    def _night_seer_check(self) -> Optional[str]:
        """Have the Seer check a player's identity."""
        seer = self._find_role("seer")
        if not seer:
            return None

        alive_names = [player.name for player in self.alive_players]
        prev_checks = seer.get_seer_check_history()

        self._refresh_public_state()
        prompt = night_seer_prompt(
            alive_names=alive_names,
            dead_names=[player.name for player in self.dead_players],
            previous_checks=prev_checks,
            game_log=self.game_log[-8:],
            public_plan_history=[
                item["plan"]
                for item in seer.private_state["seer_public_plan"]
                if isinstance(item, dict) and "plan" in item
            ],
            suspicion=seer.belief_state["suspicion"],
            role_guesses=seer.belief_state["role_guesses"],
            trust=seer.belief_state["trust"],
        )
        system = seer.get_system_prompt(self.players)

        self._print_player_action(seer, "checking a player...")
        _, parsed = self._query_player(
            seer,
            "night_seer",
            system,
            prompt,
            temperature=0.7,
        )
        target = parsed["target"]
        reason = parsed["reason"]
        plan = parsed.get("plan", "")
        self._apply_inference_fields(seer, parsed)
        if not target or target not in alive_names:
            target = random.choice([name for name in alive_names if name != seer.name])
        if target == seer.name and len(alive_names) > 1:
            target = random.choice([name for name in alive_names if name != seer.name])

        if plan:
            seer.record_seer_plan(self.round, plan)

        checked_player = self._find_player(target)
        if checked_player and checked_player.role:
            identity = "狼人" if checked_player.is_werewolf else "好人"
            seer.record_seer_check(self.round, target, identity)
            result_msg = f"第 {self.round} 夜：你查验了 {target}，结果是 {identity}"
            seer.memory.append(result_msg)
            seer.remember(result_msg)
            if target in seer.belief_state["role_guesses"]:
                seer.set_role_guess(target, "werewolf" if checked_player.is_werewolf else "villager")
            if target in seer.belief_state["suspicion"]:
                seer.update_suspicion(target, 1.0 if checked_player.is_werewolf else 0.0)
            if target in seer.belief_state["trust"] and not checked_player.is_werewolf:
                seer.belief_state["trust"][target] = 1.0

        if reason:
            self._print_dim(f"[{seer.name}] {truncate(reason, 150)}")
        self._print_dim(f"预言家查验了：{target}")

        return target

    def _night_witch_act(self, werewolf_target: str) -> Tuple[bool, Optional[str]]:
        """Have the Witch decide save/poison."""
        witch = self._find_role("witch")
        if not witch:
            return False, None

        has_antidote = witch.has_antidote
        has_poison = witch.has_poison
        alive_names = [player.name for player in self.alive_players]

        self._refresh_public_state()
        prompt = night_witch_prompt(
            alive_names=alive_names,
            dead_names=[player.name for player in self.dead_players],
            werewolf_target=werewolf_target or "无人",
            has_antidote=has_antidote,
            has_poison=has_poison,
            game_log=self.game_log[-8:],
            witch_decision_history=[
                (
                    f"第 {item['round']} 夜：救人={item['save']}, "
                    f"毒人={item['poison_target'] or 'none'}, 策略={item['plan']}"
                )
                for item in witch.private_state["witch"]["night_decision_history"]
                if isinstance(item, dict)
            ],
            suspicion=witch.belief_state["suspicion"],
            role_guesses=witch.belief_state["role_guesses"],
            trust=witch.belief_state["trust"],
        )
        system = witch.get_system_prompt(self.players)

        self._print_player_action(witch, "deciding on potions...")
        _, parsed = self._query_player(
            witch,
            "night_witch",
            system,
            prompt,
            temperature=0.6,
        )
        reason = parsed["reason"]
        plan = parsed.get("plan", "")
        self._apply_inference_fields(witch, parsed)

        use_save = parsed["save"].lower() == "yes" and has_antidote
        poison_target = parsed["poison"].strip()
        if poison_target.lower() in ("none", "no one", ""):
            poison_target = None
        if poison_target and (poison_target not in alive_names or not has_poison):
            poison_target = None
        if poison_target == werewolf_target:
            poison_target = None
        if poison_target == witch.name:
            poison_target = None

        if use_save and not werewolf_target:
            use_save = False

        if use_save:
            witch.use_antidote(self.round, werewolf_target)
            witch.memory.append(f"第 {self.round} 夜：你使用解药救下了 {werewolf_target}")
        if poison_target:
            witch.use_poison(self.round, poison_target)
            witch.memory.append(f"第 {self.round} 夜：你使用毒药带走了 {poison_target}")

        witch.record_witch_decision(
            round_num=self.round,
            werewolf_target=werewolf_target,
            save=use_save,
            poison_target=poison_target,
            plan=plan,
        )

        if reason:
            self._print_dim(f"[{witch.name}] {truncate(reason, 150)}")
        self._print_dim(
            f"女巫决策：救人={'yes' if use_save else 'no'}，毒人={poison_target or 'none'}"
        )

        return use_save, poison_target

    # ================================================================
    # Day helpers
    # ================================================================

    def _day_discussion(self) -> List[str]:
        """Run the day discussion with a fixed speaking order."""
        alive = self._day_speaking_order()
        night_deaths = [
            event for event in self.game_log[-3:]
            if "died" in event.lower() or "killed" in event.lower()
        ]
        night_summary = "；".join(night_deaths) if night_deaths else "昨夜无人死亡"

        discussion_log: List[str] = []
        for player in alive:
            self._refresh_public_state(discussion_history=discussion_log)
            prompt = day_discussion_prompt(
                player_name=player.name,
                alive_names=[p.name for p in alive],
                dead_names=[p.name for p in self.dead_players],
                night_summary=night_summary,
                discussion_history=discussion_log,
                game_log=self.game_log[-8:],
                suspicion=player.belief_state["suspicion"],
                role_guesses=player.belief_state["role_guesses"],
                trust=player.belief_state["trust"],
            )
            system = player.get_system_prompt(self.players)

            self._print_player_action(player, "发言中...")
            response, parsed = self._query_player(
                player,
                "day_discussion",
                system,
                prompt,
                temperature=0.85,
            )
            speech = parsed["speech"] or response
            reason = parsed["reason"]
            self._apply_inference_fields(player, parsed)

            entry = f"{player.name}: {speech}"
            discussion_log.append(entry)
            self.day_speech_history.append(entry)
            player.memory.append(f"第 {self.round} 轮白天发言：{speech}")

            if reason:
                self._print_dim(f"[{player.name}] {truncate(reason, 120)}")
            print(f"  {Colors.color(player.name, Colors.CYAN)}: {speech}")

        return discussion_log

    def _day_final_statements(self, discussion_log: List[str]) -> List[str]:
        """Give each alive player a short final statement before voting."""
        alive = self._day_speaking_order()
        alive_names = [player.name for player in alive]
        dead_names = [player.name for player in self.dead_players]
        top_targets = self._top_suspects_from_discussion(discussion_log)
        discussion_summary = "；".join(discussion_log[-4:]) if discussion_log else "暂无讨论。"

        final_statements: List[str] = []
        for player in alive:
            self._refresh_public_state(discussion_history=discussion_log + final_statements)
            prompt = day_final_statement_prompt(
                player_name=player.name,
                alive_names=alive_names,
                dead_names=dead_names,
                discussion_summary=discussion_summary,
                top_targets=top_targets,
                game_log=self.game_log[-6:],
                suspicion=player.belief_state["suspicion"],
                role_guesses=player.belief_state["role_guesses"],
                trust=player.belief_state["trust"],
            )
            system = player.get_system_prompt(self.players)

            self._print_player_action(player, "进行总结陈词中...")
            response, parsed = self._query_player(
                player,
                "day_final_statement",
                system,
                prompt,
                temperature=0.75,
            )
            speech = parsed["speech"] or response
            reason = parsed["reason"]
            self._apply_inference_fields(player, parsed)

            entry = f"{player.name}（总结陈词）：{speech}"
            final_statements.append(entry)
            self.day_speech_history.append(entry)

            if reason:
                self._print_dim(f"[{player.name}] {truncate(reason, 120)}")
            print(f"  {Colors.color(player.name, Colors.CYAN)} [总结]: {speech}")

        return final_statements

    def _day_vote(self, discussion_log: List[str], final_statements: List[str]) -> dict:
        """Run the daytime vote, including runoff handling for ties."""
        alive = self._day_speaking_order()
        alive_names = [player.name for player in alive]
        discussion_summary = self._discussion_summary(discussion_log, final_statements)

        votes: List[Optional[str]] = []
        vote_record: Dict[str, str] = {}

        for player in alive:
            self._refresh_public_state(vote_history=self.public_vote_history)
            prompt = day_vote_prompt(
                player_name=player.name,
                alive_names=alive_names,
                dead_names=[p.name for p in self.dead_players],
                discussion_summary=discussion_summary,
                game_log=self.game_log[-6:],
                suspicion=player.belief_state["suspicion"],
                role_guesses=player.belief_state["role_guesses"],
                trust=player.belief_state["trust"],
                vote_history=self.public_vote_history,
            )
            system = player.get_system_prompt(self.players)

            self._print_player_action(player, "投票中...")
            _, parsed = self._query_player(
                player,
                "day_vote",
                system,
                prompt,
                temperature=0.5,
            )
            vote_target = parsed["vote"]
            speech = parsed["speech"]
            self._apply_inference_fields(player, parsed)

            if vote_target and vote_target in alive_names:
                votes.append(vote_target)
                vote_record[player.name] = vote_target
            else:
                votes.append(None)
                vote_record[player.name] = "弃票"

            if speech:
                print(f"  {Colors.color(player.name, Colors.CYAN)}: {speech}")

        print(f"\n  {Colors.bold('投票结果：')}")
        for voter, target in vote_record.items():
            print(f"    {voter} -> {target}")

        self.public_vote_history.append(
            f"第 {self.round} 轮投票：" + ", ".join(
                f"{voter}->{target}" for voter, target in vote_record.items()
            )
        )

        vote_counts = count_votes(votes)
        tied_targets = self._top_vote_targets(vote_counts)
        eliminated = tied_targets[0] if len(tied_targets) == 1 else None

        if eliminated:
            count = vote_counts.get(eliminated, 0)
            total = len([vote for vote in votes if vote is not None])
            print(
                f"\n  {Colors.color(f'{eliminated} 被放逐出局！（{count}/{total} 票）', Colors.RED)}"
            )
        else:
            if tied_targets:
                print(f"\n  {Colors.color('出现平票，进入加赛发言。', Colors.YELLOW)}")
                runoff = self._runoff_vote(
                    tied_targets=tied_targets,
                    discussion_log=discussion_log + final_statements,
                )
                runoff["initial_votes"] = vote_record
                runoff["initial_vote_counts"] = vote_counts
                return runoff
            print(f"\n  {Colors.color('本轮无人出局（全员弃票）。', Colors.YELLOW)}")

        return {
            "votes": vote_record,
            "vote_counts": vote_counts,
            "eliminated": eliminated,
        }

    def _runoff_vote(self, tied_targets: List[str], discussion_log: List[str]) -> dict:
        """Run a short runoff discussion and a second vote among tied players."""
        alive = self._day_speaking_order()
        alive_names = [player.name for player in alive]
        dead_names = [player.name for player in self.dead_players]

        runoff_statements: List[str] = []
        for player in alive:
            self._refresh_public_state(discussion_history=discussion_log + runoff_statements)
            prompt = runoff_discussion_prompt(
                player_name=player.name,
                alive_names=alive_names,
                dead_names=dead_names,
                tied_targets=tied_targets,
                discussion_history=discussion_log,
                game_log=self.game_log[-6:],
                suspicion=player.belief_state["suspicion"],
                role_guesses=player.belief_state["role_guesses"],
                trust=player.belief_state["trust"],
            )
            system = player.get_system_prompt(self.players)

            self._print_player_action(player, "进行加赛发言中...")
            response, parsed = self._query_player(
                player,
                "day_runoff_discussion",
                system,
                prompt,
                temperature=0.75,
            )
            speech = parsed["speech"] or response
            reason = parsed["reason"]
            self._apply_inference_fields(player, parsed)

            entry = f"{player.name}（加赛发言）：{speech}"
            runoff_statements.append(entry)
            self.day_speech_history.append(entry)

            if reason:
                self._print_dim(f"[{player.name}] {truncate(reason, 100)}")
            print(f"  {Colors.color(player.name, Colors.CYAN)} [加赛]: {speech}")

        votes: List[Optional[str]] = []
        vote_record: Dict[str, str] = {}
        runoff_summary = self._discussion_summary(discussion_log, runoff_statements)

        for player in alive:
            self._refresh_public_state(vote_history=self.public_vote_history)
            prompt = day_vote_prompt(
                player_name=player.name,
                alive_names=tied_targets,
                dead_names=dead_names,
                discussion_summary=f"加赛投票对象：{', '.join(tied_targets)}。{runoff_summary}",
                game_log=self.game_log[-6:],
                suspicion=player.belief_state["suspicion"],
                role_guesses=player.belief_state["role_guesses"],
                trust=player.belief_state["trust"],
                vote_history=self.public_vote_history,
            )
            system = player.get_system_prompt(self.players)

            self._print_player_action(player, "加赛投票中...")
            _, parsed = self._query_player(
                player,
                "day_runoff_vote",
                system,
                prompt,
                temperature=0.5,
            )
            vote_target = parsed["vote"]
            self._apply_inference_fields(player, parsed)

            if vote_target in tied_targets:
                votes.append(vote_target)
                vote_record[player.name] = vote_target
            else:
                votes.append(None)
                vote_record[player.name] = "弃票"

        vote_counts = count_votes(votes)
        runoff_tied = self._top_vote_targets(vote_counts)
        eliminated = runoff_tied[0] if len(runoff_tied) == 1 else None

        self.public_vote_history.append(
            f"第 {self.round} 轮加赛投票：" + ", ".join(
                f"{voter}->{target}" for voter, target in vote_record.items()
            )
        )

        if eliminated:
            count = vote_counts.get(eliminated, 0)
            total = len([vote for vote in votes if vote is not None])
            print(
                f"\n  {Colors.color(f'{eliminated} 在加赛中出局！（{count}/{total} 票）', Colors.RED)}"
            )
        else:
            print(f"\n  {Colors.color('加赛后仍然平票，今天无人出局。', Colors.YELLOW)}")

        return {
            "runoff": True,
            "tied_targets": tied_targets,
            "runoff_statements": runoff_statements,
            "votes": vote_record,
            "vote_counts": vote_counts,
            "eliminated": eliminated,
        }

    def _last_words(self, player: WerewolfPlayer, elimination_reason: str) -> str:
        """Allow an eliminated player to leave short last words."""
        alive_names = [alive_player.name for alive_player in self.alive_players if alive_player.name != player.name]
        dead_names = [dead_player.name for dead_player in self.dead_players] + [player.name]

        self._refresh_public_state()
        prompt = last_words_prompt(
            player_name=player.name,
            alive_names=alive_names,
            dead_names=dead_names,
            elimination_reason=elimination_reason,
            game_log=self.game_log[-6:],
            suspicion=player.belief_state["suspicion"],
            role_guesses=player.belief_state["role_guesses"],
            trust=player.belief_state["trust"],
        )
        system = player.get_system_prompt(self.players)

        self._print_player_action(player, "leaving last words...")
        response, parsed = self._query_player(
            player,
            "day_last_words",
            system,
            prompt,
            temperature=0.8,
        )
        speech = parsed["speech"] or response
        reason = parsed["reason"]
        self._apply_inference_fields(player, parsed)
        player.death_message = speech
        self._log(f"{player.name} 的遗言：{speech}")

        if reason:
            self._print_dim(f"[{player.name}] {truncate(reason, 100)}")
        print(f"  {Colors.color(player.name, Colors.YELLOW)} [遗言]: {speech}")
        return speech

    def _hunter_shot(self, hunter: WerewolfPlayer) -> Optional[str]:
        """Trigger the Hunter's death ability."""
        if not hunter.can_shoot:
            return None

        alive_names = [player.name for player in self.alive_players if player.name != hunter.name]
        if not alive_names:
            return None

        self._refresh_public_state()
        prompt = hunter_shot_prompt(
            alive_names=alive_names,
            dead_names=[player.name for player in self.dead_players],
            game_log=self.game_log[-8:],
            shot_history=[
                (
                    f"第 {item['round']} 轮：目标={item['target'] or 'none'}"
                )
                for item in hunter.private_state["hunter"]["shot_history"]
                if isinstance(item, dict)
            ],
            suspicion=hunter.belief_state["suspicion"],
            role_guesses=hunter.belief_state["role_guesses"],
            trust=hunter.belief_state["trust"],
        )
        system = hunter.get_system_prompt(self.players)

        self._print_player_action(hunter, "发动猎人技能，选择目标中...")
        _, parsed = self._query_player(
            hunter,
            "hunter_shot",
            system,
            prompt,
            temperature=0.8,
        )
        target = parsed["target"]
        speech = parsed["speech"]
        self._apply_inference_fields(hunter, parsed)

        if target in ("none", "no one", "无人", ""):
            target = None
        if target and target not in alive_names:
            print(f"  {Colors.dim(f'无效目标 {target}（目标不存活），跳过开枪。')}")
            target = None
        if target == hunter.name:
            target = None

        if speech:
            print(f"  {Colors.color(hunter.name, Colors.YELLOW)}: {speech}")

        hunter.mark_hunter_shot(self.round, target)

        if target:
            print(f"  {Colors.color(f'猎人开枪带走 {target}！', Colors.RED)}")
        else:
            print(f"  {Colors.dim('猎人选择不开枪。')}")

        return target

    # ================================================================
    # Win condition
    # ================================================================

    def check_win(self) -> Optional[str]:
        """Check if either faction has won."""
        alive_wolves = sum(1 for player in self.alive_players if player.is_werewolf)
        alive_villagers = sum(1 for player in self.alive_players if player.is_villager_team)

        if alive_wolves == 0:
            return "villager"
        if alive_wolves >= alive_villagers:
            return "werewolf"
        return None

    # ================================================================
    # Run
    # ================================================================

    def run(self, max_rounds: int = 100, verbose: bool = True) -> Optional[str]:
        """Run the game and write summary logs when finished."""
        winner = super().run(max_rounds=max_rounds, verbose=verbose)

        if self.logger:
            path = self.logger.write_summary(
                players=self.players,
                winner=winner,
                total_rounds=self.round,
                game_log=self.game_log,
                extra={
                    "vote_history": self.public_vote_history,
                    "day_speech_history": self.day_speech_history,
                },
            )
            if verbose:
                print(f"\n{Colors.dim(f'完整日志已保存到：{self.logger.log_dir}')}")
                print(f"{Colors.dim(f'  摘要文件：{path}')}")

        return winner

    # ================================================================
    # Helpers
    # ================================================================

    def _find_player(self, name: str) -> Optional[WerewolfPlayer]:
        """Find a player by name."""
        name_lower = name.lower().strip()
        for player in self.players:
            if player.name.lower() == name_lower:
                return player
        for player in self.players:
            if name_lower in player.name.lower():
                return player
        return None

    def _find_role(self, role_id: str) -> Optional[WerewolfPlayer]:
        """Find the first alive player with the given role."""
        for player in self.alive_players:
            if player.role and player.role.role_id == role_id:
                return player
        return None

    def _wolves_alive(self) -> bool:
        return any(player.is_werewolf for player in self.alive_players)

    def _seer_alive(self) -> bool:
        return self._find_role("seer") is not None

    def _witch_alive(self) -> bool:
        return self._find_role("witch") is not None

    def _log(self, message: str) -> None:
        """Add a public game log entry."""
        self.game_log.append(message)

    def _day_speaking_order(self) -> List[WerewolfPlayer]:
        """Return a deterministic speaking order for the current day."""
        return sorted(self.alive_players, key=lambda player: player.name.lower())

    def _discussion_summary(self, discussion_log: List[str], extra_log: Optional[List[str]] = None) -> str:
        combined = discussion_log + list(extra_log or [])
        if not combined:
            return "暂无讨论。"
        return " | ".join(combined[-6:])

    def _top_suspects_from_discussion(self, discussion_log: List[str]) -> List[str]:
        counts: Dict[str, int] = {}
        alive_names = {player.name for player in self.alive_players}
        for entry in discussion_log[-10:]:
            lowered = entry.lower()
            for name in alive_names:
                if name.lower() in lowered:
                    counts[name] = counts.get(name, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        return [name for name, _ in ranked[:3]]

    def _top_vote_targets(self, vote_counts: Dict[str, int]) -> List[str]:
        if not vote_counts:
            return []
        max_votes = max(vote_counts.values())
        return sorted([name for name, count in vote_counts.items() if count == max_votes])

    def _refresh_public_state(
        self,
        discussion_history: Optional[List[str]] = None,
        vote_history: Optional[List[str]] = None,
    ) -> None:
        """Broadcast public information to every player."""
        alive_names = [player.name for player in self.alive_players]
        dead_names = [player.name for player in self.dead_players]
        recent_events = self.game_log[-8:]

        for player in self.players:
            player.update_public_state(
                round_num=self.round,
                alive_players=alive_names,
                dead_players=dead_names,
                recent_events=recent_events,
                discussion_history=discussion_history,
                vote_history=vote_history or self.public_vote_history,
            )

    def _apply_inference_fields(self, player: WerewolfPlayer, parsed: dict) -> None:
        """Write structured prompt outputs back into belief/private state."""
        suspect_name = (parsed.get("suspect") or "").strip()
        trust_name = (parsed.get("trust") or "").strip()
        claim = (parsed.get("claim") or "").strip().lower()
        plan = (parsed.get("plan") or "").strip()

        if suspect_name and suspect_name.lower() != "none":
            if suspect_name in player.belief_state["suspicion"]:
                player.update_suspicion(suspect_name, 1.0)

        if trust_name and trust_name.lower() != "none":
            if trust_name in player.belief_state["trust"]:
                player.belief_state["trust"][trust_name] = 1.0
            if trust_name in player.belief_state["suspicion"]:
                player.update_suspicion(trust_name, 0.0)

        if claim and claim != "none":
            player.private_state["last_claim"] = claim
            if suspect_name and suspect_name in player.belief_state["role_guesses"]:
                player.set_role_guess(suspect_name, "werewolf")

        if plan:
            player.private_state["last_plan"] = plan

    # ================================================================
    # Display
    # ================================================================

    def _print_setup(self) -> None:
        """Print the initial game setup."""
        print(f"\n  {Colors.bold('玩家与身份（调试可见）：')}")
        print(f"  {'-' * 45}")
        for player in self.players:
            model_info = player.model.model_name
            role_color = Colors.RED if player.is_werewolf else Colors.GREEN
            role_name = (player.role.name if player.role else "???").ljust(20)
            print(
                f"  {player.name:12s} -> {Colors.color(role_name, role_color)}"
                f"  [{model_info}]"
            )
        print()

    def _print_night_results(self, deaths: List[str]) -> None:
        """Announce night deaths."""
        print(f"\n  {Colors.bold('天亮了……')}")
        if deaths:
            for name in deaths:
                print(f"  {Colors.color(f'{name} 死亡。', Colors.RED)}")
        else:
            print(f"  {Colors.color('昨夜是平安夜，无人死亡。', Colors.GREEN)}")

    def _print_player_action(self, player: WerewolfPlayer, action: str) -> None:
        """Print a dim status line for a player's action."""
        role_icon = "狼人" if player.is_werewolf else "玩家"
        model_short = player.model.model_name[:20]
        print(f"\n  {Colors.dim(f'[{role_icon} {player.name} ({model_short})] {action}')}")

    def _print_dim(self, text: str) -> None:
        print(f"  {Colors.dim(text)}")

    def _print_result(self) -> None:
        """Print the final result."""
        self._print_header("游戏结束")
        if self.winner == "villager":
            print(
                f"\n  {Colors.color('好人阵营获胜！所有狼人均已出局。', Colors.GREEN)}"
            )
        elif self.winner == "werewolf":
            print(
                f"\n  {Colors.color('狼人阵营获胜！他们已经控制了全场。', Colors.RED)}"
            )

        print(f"\n  {Colors.bold('最终身份：')}")
        for player in self.players:
            status = "死亡" if not player.alive else "存活"
            role_color = Colors.RED if player.is_werewolf else Colors.GREEN
            print(
                f"  {status:5s} {player.name:12s} - "
                f"{Colors.color(player.role.name if player.role else '???', role_color)}"
                f"  [{player.model.model_name}]"
            )

        print(f"\n  {Colors.bold('对局日志：')}")
        for entry in self.game_log:
            print(f"  {Colors.dim('-')} {entry}")

    def _print_header(self, text: str) -> None:
        print(f"\n{Colors.bold('=' * 55)}")
        print(Colors.bold(f"  {text}"))
        print(Colors.bold('=' * 55))
