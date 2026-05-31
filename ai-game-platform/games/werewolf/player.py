"""狼人杀玩家类。"""

from typing import Dict, List, Optional

from core.player import Player
from core.models.base import ModelInterface

from .roles import Role


class WerewolfPlayer(Player):
    """狼人杀玩家对象，带角色认知和结构化状态。"""

    def __init__(
        self,
        name: str,
        model: ModelInterface,
        persona: str = "",
    ):
        super().__init__(name, model, persona)
        self.role: Optional[Role] = None
        self.fellow_wolves: list[str] = []
        self.death_message: str = ""
        self.public_state: Dict[str, object] = {
            "round": 0,
            "alive_players": [],
            "dead_players": [],
            "recent_events": [],
            "discussion_history": [],
            "vote_history": [],
        }
        self.private_state: Dict[str, object] = {
            "role_id": None,
            "fellow_wolves": [],
            "seer_checks": [],
            "seer_public_plan": [],
            "witch": {
                "antidote_available": True,
                "poison_available": True,
                "antidote_target_history": [],
                "poison_target_history": [],
                "night_decision_history": [],
            },
            "werewolf": {
                "kill_plan_history": [],
                "coordination_notes": [],
            },
            "hunter": {
                "shot_available": True,
                "shot_history": [],
            },
        }
        self.belief_state: Dict[str, Dict[str, object]] = {
            "suspicion": {},
            "role_guesses": {},
            "trust": {},
        }

    def assign_role(self, role: Role) -> None:
        """为玩家分配角色。"""
        self.role = role
        self.private_state["role_id"] = role.role_id

    def initialize_state(self, all_player_names: List[str]) -> None:
        """初始化当前对局的结构化推理状态。"""
        others = [name for name in all_player_names if name != self.name]
        self.belief_state["suspicion"] = {name: 0.0 for name in others}
        self.belief_state["role_guesses"] = {name: "unknown" for name in others}
        self.belief_state["trust"] = {name: 0.0 for name in others}

    def update_public_state(
        self,
        round_num: int,
        alive_players: List[str],
        dead_players: List[str],
        recent_events: List[str],
        discussion_history: Optional[List[str]] = None,
        vote_history: Optional[List[str]] = None,
    ) -> None:
        """保存该玩家当前允许看到的公开信息。"""
        self.public_state = {
            "round": round_num,
            "alive_players": list(alive_players),
            "dead_players": list(dead_players),
            "recent_events": list(recent_events),
            "discussion_history": list(discussion_history or []),
            "vote_history": list(vote_history or []),
        }

    def set_fellow_wolves(self, names: List[str]) -> None:
        """保存狼人队友信息。"""
        self.fellow_wolves = list(names)
        self.private_state["fellow_wolves"] = list(names)

    def record_seer_check(self, round_num: int, target: str, identity: str) -> None:
        """把预言家查验结果写入结构化私有状态。"""
        entry = {
            "round": round_num,
            "target": target,
            "identity": identity,
        }
        checks = self.private_state["seer_checks"]
        if isinstance(checks, list):
            checks.append(entry)

    def record_seer_plan(self, round_num: int, plan: str) -> None:
        plans = self.private_state.get("seer_public_plan", [])
        if isinstance(plans, list):
            plans.append({
                "round": round_num,
                "plan": plan,
            })

    def get_seer_check_history(self) -> List[str]:
        """返回适合提示词拼接的查验历史。"""
        checks = self.private_state.get("seer_checks", [])
        if not isinstance(checks, list):
            return []
        return [
            f"第 {entry['round']} 夜：你查验了 {entry['target']}，结果是 {entry['identity']}"
            for entry in checks
        ]

    @property
    def has_antidote(self) -> bool:
        witch_state = self.private_state.get("witch", {})
        return bool(witch_state.get("antidote_available", False))

    @property
    def has_poison(self) -> bool:
        witch_state = self.private_state.get("witch", {})
        return bool(witch_state.get("poison_available", False))

    def use_antidote(self, round_num: int, target: str) -> None:
        witch_state = self.private_state["witch"]
        witch_state["antidote_available"] = False
        witch_state["antidote_target_history"].append({
            "round": round_num,
            "target": target,
        })

    def use_poison(self, round_num: int, target: str) -> None:
        witch_state = self.private_state["witch"]
        witch_state["poison_available"] = False
        witch_state["poison_target_history"].append({
            "round": round_num,
            "target": target,
        })

    def record_witch_decision(
        self,
        round_num: int,
        werewolf_target: str,
        save: bool,
        poison_target: Optional[str],
        plan: str,
    ) -> None:
        witch_state = self.private_state["witch"]
        witch_state["night_decision_history"].append({
            "round": round_num,
            "werewolf_target": werewolf_target,
            "save": save,
            "poison_target": poison_target,
            "plan": plan,
        })

    def record_werewolf_plan(
        self,
        round_num: int,
        suggested_target: str,
        plan: str,
        coordination_note: str,
    ) -> None:
        werewolf_state = self.private_state["werewolf"]
        werewolf_state["kill_plan_history"].append({
            "round": round_num,
            "suggested_target": suggested_target,
            "plan": plan,
        })
        if coordination_note:
            werewolf_state["coordination_notes"].append({
                "round": round_num,
                "note": coordination_note,
            })

    @property
    def can_shoot(self) -> bool:
        hunter_state = self.private_state.get("hunter", {})
        return bool(hunter_state.get("shot_available", False))

    def mark_hunter_shot(self, round_num: int, target: Optional[str]) -> None:
        hunter_state = self.private_state["hunter"]
        hunter_state["shot_available"] = False
        hunter_state["shot_history"].append({
            "round": round_num,
            "target": target,
        })

    def update_suspicion(self, player_name: str, score: float) -> None:
        if player_name in self.belief_state["suspicion"]:
            self.belief_state["suspicion"][player_name] = score

    def set_role_guess(self, player_name: str, role_id: str) -> None:
        if player_name in self.belief_state["role_guesses"]:
            self.belief_state["role_guesses"][player_name] = role_id

    @property
    def faction(self) -> str:
        """返回玩家阵营。"""
        return self.role.faction.value if self.role else "unknown"

    @property
    def is_werewolf(self) -> bool:
        return self.role is not None and self.role.role_id == "werewolf"

    @property
    def is_villager_team(self) -> bool:
        return self.role is not None and self.role.faction.value == "villager"

    def get_system_prompt(self, all_players: list) -> str:
        """构造该玩家的系统提示词。"""
        from .prompts import build_system_prompt

        wolves = self.fellow_wolves if self.is_werewolf else None
        return build_system_prompt(
            player_name=self.name,
            role=self.role,
            all_players=all_players,
            fellow_wolves=wolves,
        )

    def __repr__(self) -> str:
        role_name = self.role.name if self.role else "未分配"
        status = "存活" if self.alive else "死亡"
        return f"WerewolfPlayer({self.name}, {role_name}, {self.model.model_name}, {status})"
