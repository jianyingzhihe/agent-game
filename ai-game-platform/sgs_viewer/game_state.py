"""Incremental game state reconstruction engine.

Builds up GameSnapshot objects by replaying events step-by-step,
with caching to avoid re-parsing from scratch on every step change.
"""

import re
from dataclasses import dataclass, field
from .assets import SKILL_MAP, ACTION_ARROW_COLORS
from .log_parser import (
    PlayerSnapshot, HandCardGroup, ParsedOption, PromptData,
    parse_prompt_user_prompt, build_response_data,
)


@dataclass
class PlayerState:
    """Accumulated state for one player across steps."""
    name: str
    model_name: str = ""
    skill_id: str = ""
    skill_name: str = ""
    max_hp: int = 4
    hp: int = 4
    hand_count: int = 4
    alive: bool = True
    hand_summary: list = field(default_factory=list)
    last_action: str = ""
    last_reason: str = ""
    turns_played: int = 0
    identity: str = ""            # "lord", "loyalist", "rebel", "spy" or ""
    identity_label: str = ""      # display label: "主公", "忠臣", etc.
    identity_revealed: bool = False

    @property
    def display_name(self) -> str:
        """Model name for display, fall back to player name."""
        return self.model_name or self.name


@dataclass
class ActionInfo:
    """What happened at the current step."""
    action_type: str
    source_player: str
    target_player: str | None
    card_name: str | None
    display_text: str
    arrow_color: str  # key into C (assets.C)

    def has_arrow(self) -> bool:
        return self.target_player is not None and self.action_type in (
            "sha", "spell_steal", "spell_dismantle",
            "spell_aoe_nanman", "spell_aoe_wanjian", "heal_aoe",
        )


@dataclass
class GameSnapshot:
    """Complete game state at a specific step index."""
    step_index: int
    players: dict[str, PlayerState]
    player_order: list[str]
    turn_player: str
    current_phase: str
    current_round: int
    active_action: ActionInfo | None = None
    raw_step: dict | None = None


class GameStateEngine:
    """Incrementally rebuilds game state by replaying events."""

    def __init__(self):
        self.steps: list[dict] = []
        self._cache: dict[int, GameSnapshot] = {}
        self._last_prompt_data: PromptData | None = None
        self._last_prompt_step: dict | None = None

    def load(self, steps: list[dict]) -> None:
        """Load raw steps and reset all state."""
        self.steps = steps
        self._cache.clear()
        self._last_prompt_data = None
        self._last_prompt_step = None

    def get_snapshot(self, idx: int) -> GameSnapshot:
        """Get the game state at a specific step index, with caching."""
        if idx < 0:
            idx = 0
        if idx >= len(self.steps):
            idx = len(self.steps) - 1

        if idx in self._cache:
            return self._cache[idx]

        # Find nearest cached predecessor
        base_idx = -1
        for c in sorted(self._cache.keys()):
            if c < idx:
                base_idx = c
            else:
                break

        if base_idx >= 0:
            snap = self._clone_snapshot(self._cache[base_idx])
            start = base_idx + 1
        else:
            snap = self._empty_snapshot()
            start = 0

        for i in range(start, idx + 1):
            self._apply_step(snap, self.steps[i], i)
            # Cache periodically (every 5 steps to avoid memory bloat)
            if i % 5 == 0:
                self._cache[i] = self._clone_snapshot(snap)

        self._cache[idx] = self._clone_snapshot(snap)
        return snap

    @staticmethod
    def _identity_label(identity: str, revealed: bool) -> str:
        """Convert identity ID to display label."""
        if not identity:
            return ""
        if not revealed:
            return "???"
        mapping = {
            "lord": "主公", "loyalist": "忠臣",
            "rebel": "反贼", "spy": "内奸",
        }
        return mapping.get(identity, identity)

    def total_steps(self) -> int:
        return len(self.steps)

    def _empty_snapshot(self) -> GameSnapshot:
        return GameSnapshot(
            step_index=-1,
            players={},
            player_order=[],
            turn_player="",
            current_phase="",
            current_round=0,
        )

    def _clone_snapshot(self, snap: GameSnapshot) -> GameSnapshot:
        players = {}
        for name, ps in snap.players.items():
            players[name] = PlayerState(
                name=ps.name,
                model_name=ps.model_name,
                skill_id=ps.skill_id,
                skill_name=ps.skill_name,
                max_hp=ps.max_hp,
                hp=ps.hp,
                hand_count=ps.hand_count,
                alive=ps.alive,
                hand_summary=[dict(hc) for hc in ps.hand_summary],
                last_action=ps.last_action,
                last_reason=ps.last_reason,
                turns_played=ps.turns_played,
                identity=ps.identity,
                identity_label=ps.identity_label,
                identity_revealed=ps.identity_revealed,
            )
        return GameSnapshot(
            step_index=snap.step_index,
            players=players,
            player_order=list(snap.player_order),
            turn_player=snap.turn_player,
            current_phase=snap.current_phase,
            current_round=snap.current_round,
            active_action=snap.active_action,
            raw_step=snap.raw_step,
        )

    def _apply_step(self, snap: GameSnapshot, step: dict, step_idx: int) -> None:
        snap.step_index = step_idx
        snap.raw_step = step
        snap.active_action = None
        step_type = step.get("type", "")

        if step_type == "game_start":
            self._apply_game_start(snap, step)
        elif step_type == "prompt":
            self._apply_prompt(snap, step)
        elif step_type == "response":
            self._apply_response(snap, step)

    def _apply_game_start(self, snap: GameSnapshot, step: dict) -> None:
        players = step.get("players", [])
        order = []
        for p in players:
            name = p.get("name", "")
            skill_id = p.get("skill", "")
            skill_name = SKILL_MAP.get(skill_id, skill_id)
            identity = p.get("identity", "")
            identity_revealed = p.get("identity_revealed", False)
            identity_label = self._identity_label(identity, identity_revealed)
            order.append(name)
            snap.players[name] = PlayerState(
                name=name,
                model_name=p.get("model", ""),
                skill_id=skill_id,
                skill_name=skill_name,
                max_hp=p.get("hp", 4),
                hp=p.get("hp", 4),
                hand_count=4,
                alive=True,
                identity=identity,
                identity_label=identity_label,
                identity_revealed=identity_revealed,
            )
        snap.player_order = order

    def _apply_prompt(self, snap: GameSnapshot, step: dict) -> None:
        player = step.get("player", "")
        phase = step.get("phase", "play")
        rnd = step.get("round", 0)

        snap.turn_player = player
        snap.current_phase = phase
        snap.current_round = rnd

        data = parse_prompt_user_prompt(step)
        self._last_prompt_data = data
        self._last_prompt_step = step

        if data is None:
            return

        # Update player states from 场上 line
        for fp in data.field_players:
            if fp.name in snap.players:
                ps = snap.players[fp.name]
                ps.hp = fp.hp
                ps.hand_count = fp.hand_count
                ps.alive = fp.alive
                if fp.identity_label:
                    ps.identity_label = fp.identity_label
                    if fp.identity_label not in ("", "???"):
                        ps.identity_revealed = True

        # Update turn player's hand summary — only when parser found
        # hand cards.  select_card / discard / respond prompts may not
        # include a 手牌 line, so data.hand_cards can be empty; in that
        # case keep the previous hand_summary so card capsules persist.
        if player in snap.players and data.hand_cards:
            snap.players[player].hand_summary = [
                {"name": hc.card_name, "count": hc.count}
                for hc in data.hand_cards
            ]

    def _apply_response(self, snap: GameSnapshot, step: dict) -> None:
        resp = build_response_data(step)
        player = resp.get("player", "")
        phase = resp.get("phase", "")
        choice_str = resp.get("choice", "")
        reason = resp.get("reason", "")

        if player in snap.players:
            snap.players[player].last_reason = reason

        # Default: no special action detected
        action = None
        matched = None

        # Try to match choice with options from the preceding prompt
        if choice_str and self._last_prompt_data:
            try:
                choice_num = int(choice_str)
            except (ValueError, TypeError):
                choice_num = -1

            for opt in self._last_prompt_data.options:
                if opt.option_number == choice_num:
                    matched = opt
                    break

            if matched:
                action = self._build_select_card_action(matched, player, snap)
                if action is None:
                    action = self._build_action_info(
                        matched, player, reason, snap
                    )

        if action is None:
            # Build a generic action
            phase_labels = {
                "play": "行动",
                "respond": "响应",
                "discard": "弃牌",
                "select_card": "选牌",
            }
            label = phase_labels.get(phase, phase)
            dp = self._disp(snap, player)
            action = ActionInfo(
                action_type=phase,
                source_player=player,
                target_player=None,
                card_name=None,
                display_text=f"{dp} {label}",
                arrow_color="",
            )

        snap.active_action = action

        # Update player state
        if player in snap.players:
            ps = snap.players[player]
            ps.last_action = action.display_text
            if phase == "play":
                ps.turns_played += 1

            # When a player plays/responds with a card, deduct it from hand
            # immediately. The hand count from the prompt is pre-action;
            # the next prompt will correct it, but without this the viewer
            # shows the action AND the old hand count in the same frame.
            if action:
                consumed = self._consumed_card_name(action.action_type, action.card_name)
                if consumed and ps.hand_count > 0:
                    ps.hand_count = max(0, ps.hand_count - 1)
                    for hc in ps.hand_summary:
                        if hc.get("name") == consumed and hc.get("count", 0) > 0:
                            hc["count"] -= 1
                            if hc["count"] <= 0:
                                ps.hand_summary.remove(hc)
                            break

        if matched:
            self._apply_select_card_resolution(snap, player, phase, matched)

    def _disp(self, snap: GameSnapshot, key: str) -> str:
        """Look up display name for a player key."""
        if not key:
            return key
        ps = snap.players.get(key)
        return ps.display_name if ps else key

    # Actions that consume a card — default card name if not in matched option
    _ACTION_CARD = {
        "sha": "杀", "respond_sha": "杀", "respond_shan": "闪",
        "spell_steal": "顺手牵羊", "spell_dismantle": "过河拆桥",
        "spell_aoe_nanman": "南蛮入侵", "spell_aoe_wanjian": "万箭齐发",
        "spell_self_draw": "无中生有", "heal_self": "桃", "heal_aoe": "桃园结义",
    }

    def _consumed_card_name(self, action_type: str, matched_card: str | None) -> str | None:
        """Return the card name consumed by this action, or None."""
        # Use matched card name if available (handles 武圣 using 闪 as 杀, etc.)
        if matched_card:
            return matched_card
        return self._ACTION_CARD.get(action_type)

    def _extract_select_card_context(self) -> tuple[str, str] | None:
        if not self._last_prompt_step:
            return None
        text = self._last_prompt_step.get("user_prompt", "")
        match = re.search(r"你对(\w+)使用【(.+?)】", text)
        if not match:
            return None
        return match.group(1), match.group(2)

    @staticmethod
    def _adjust_hand_summary(ps: PlayerState, card_name: str, delta: int) -> None:
        if not card_name:
            return
        for hc in ps.hand_summary:
            if hc.get("name") == card_name:
                hc["count"] = max(0, hc.get("count", 0) + delta)
                if hc["count"] == 0:
                    ps.hand_summary.remove(hc)
                return
        if delta > 0:
            ps.hand_summary.append({"name": card_name, "count": delta})

    def _build_select_card_action(
        self, opt: ParsedOption, player: str, snap: GameSnapshot
    ) -> ActionInfo | None:
        if not self._last_prompt_step or self._last_prompt_step.get("phase") != "select_card":
            return None
        context = self._extract_select_card_context()
        if not context:
            return None

        target, tool_name = context
        source_name = self._disp(snap, player)
        target_name = self._disp(snap, target)
        card_name = opt.card_name or "?"

        if tool_name == "过河拆桥":
            text = f"{source_name} 拆掉 {target_name} 的【{card_name}】"
            action_type = "spell_dismantle_resolve"
        elif tool_name == "顺手牵羊":
            text = f"{source_name} 牵走 {target_name} 的【{card_name}】"
            action_type = "spell_steal_resolve"
        else:
            return None

        return ActionInfo(
            action_type=action_type,
            source_player=player,
            target_player=target,
            card_name=card_name,
            display_text=text,
            arrow_color="arrow_spell",
        )

    def _apply_select_card_resolution(
        self, snap: GameSnapshot, player: str, phase: str, opt: ParsedOption
    ) -> None:
        if phase != "select_card":
            return

        context = self._extract_select_card_context()
        if not context:
            return

        target, tool_name = context
        target_ps = snap.players.get(target)
        if target_ps and target_ps.hand_count > 0:
            target_ps.hand_count = max(0, target_ps.hand_count - 1)
            if opt.card_name:
                self._adjust_hand_summary(target_ps, opt.card_name, -1)

        if tool_name == "顺手牵羊" and player in snap.players:
            source_ps = snap.players[player]
            source_ps.hand_count += 1
            if opt.card_name:
                self._adjust_hand_summary(source_ps, opt.card_name, 1)

    def _build_action_info(
        self, opt: ParsedOption, player: str, reason: str, snap: GameSnapshot
    ) -> ActionInfo:
        at = opt.action_type
        target = opt.target
        card = opt.card_name
        arrow_key = ACTION_ARROW_COLORS.get(at, "")

        dp = self._disp(snap, player)  # display name for source
        dt = self._disp(snap, target) if target else ""  # display name for target

        # Build display text
        if at == "end_turn":
            text = f"{dp} 结束回合"
        elif at == "pass_response":
            text = f"{dp} 不响应"
        elif at == "sha":
            tgt = dt or "?"
            text = f"{dp} 用【杀】→ {tgt}"
        elif at == "spell_steal":
            tgt = dt or "?"
            text = f"{dp} 用【顺手牵羊】→ {tgt}"
        elif at == "spell_dismantle":
            tgt = dt or "?"
            text = f"{dp} 用【过河拆桥】→ {tgt}"
        elif at == "spell_aoe_nanman":
            text = f"{dp} 用【南蛮入侵】全体"
            # Target all other alive players for arrow
            if not target:
                others = [n for n in snap.player_order
                          if n != player and snap.players.get(n) and snap.players[n].alive]
                target = others[0] if others else None
        elif at == "spell_aoe_wanjian":
            text = f"{dp} 用【万箭齐发】全体"
            if not target:
                others = [n for n in snap.player_order
                          if n != player and snap.players.get(n) and snap.players[n].alive]
                target = others[0] if others else None
        elif at == "spell_self_draw":
            text = f"{dp} 用【无中生有】"
        elif at == "heal_self":
            text = f"{dp} 用【桃】治疗"
        elif at == "heal_aoe":
            text = f"{dp} 用【桃园结义】全体治疗"
            if not target:
                others = [n for n in snap.player_order
                          if n != player and snap.players.get(n) and snap.players[n].alive]
                target = others[0] if others else None
        elif at == "skill_blood_draw":
            text = f"{dp} 用【苦肉】扣血摸牌"
        elif at == "respond_shan":
            text = f"{dp} 用【闪】响应"
        elif at == "respond_sha":
            text = f"{dp} 用【杀】响应"
        elif at == "discard":
            text = f"{dp} 弃牌"
        else:
            text = f"{dp}: {opt.raw_text[:40]}"

        return ActionInfo(
            action_type=at,
            source_player=player,
            target_player=target,
            card_name=card,
            display_text=text,
            arrow_color=arrow_key,
        )
