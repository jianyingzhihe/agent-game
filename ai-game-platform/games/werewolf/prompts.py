"""狼人杀游戏的提示词模板。"""

from typing import Dict, List, Optional

from .roles import Role


RESPONSE_FORMAT = """
回复格式
你必须只使用大写的 `KEY: value` 行进行回答。
不要输出 JSON。
不要在这些键值行之外添加额外说明。

通用字段：
REASON: <你的私下推理，1-3 句短句>
SUSPECT: <你当前最怀疑的玩家名，或 none>
TRUST: <你当前最信任的玩家名，或 none>
PLAN: <这一轮的简短策略>
CLAIM: <你的身份声称，或 none>

不同阶段的动作字段：

狼人击杀 / 预言家查验 / 猎人开枪：
TARGET: <玩家名或 none>

女巫：
SAVE: yes 或 no
POISON: <玩家名或 none>

白天发言：
SPEECH: <你的公开发言>

白天投票：
VOTE: <玩家名>

规则：
- 玩家名必须严格使用玩家列表里的原样名字。
- 某字段不适用时填 none。
- REASON 是私下推理，SPEECH 是公开发言。
- 除非你的角色在策略上会真实公开隐藏信息，否则不要在公开发言中泄露隐私信息。
- 公开发言请优先使用中文。
"""


def _state_section(alive: List[str], dead: List[str]) -> str:
    parts = [f"存活玩家（{len(alive)}）：{', '.join(alive)}"]
    if dead:
        parts.append(f"死亡玩家（{len(dead)}）：{', '.join(dead)}")
    return "\n".join(parts)


def _belief_section(
    suspicion: Optional[Dict[str, float]] = None,
    role_guesses: Optional[Dict[str, str]] = None,
    trust: Optional[Dict[str, float]] = None,
) -> List[str]:
    lines: List[str] = []

    if suspicion:
        ranked = sorted(suspicion.items(), key=lambda item: item[1], reverse=True)[:3]
        if ranked:
            lines.append("## 你的怀疑列表")
            for name, score in ranked:
                lines.append(f"- {name}: {score:.2f}")

    if role_guesses:
        guessed = [(name, role_id) for name, role_id in role_guesses.items() if role_id != "unknown"]
        if guessed:
            lines.append("")
            lines.append("## 你的身份猜测")
            for name, role_id in guessed[:5]:
                lines.append(f"- {name}: {role_id}")

    if trust:
        ranked_trust = sorted(trust.items(), key=lambda item: item[1], reverse=True)[:2]
        if ranked_trust:
            lines.append("")
            lines.append("## 你的信任判断")
            for name, score in ranked_trust:
                lines.append(f"- {name}: {score:.2f}")

    return lines


def build_system_prompt(
    player_name: str,
    role: Role,
    all_players: list,
    fellow_wolves: Optional[List[str]] = None,
) -> str:
    player_names = [player.name for player in all_players]
    player_list_str = ", ".join(player_names)

    lines = [
        f"你是玩家 {player_name}，正在参加一局严肃的狼人杀。",
        "",
        f"本局玩家：{player_list_str}（共 {len(all_players)} 人）",
        "",
        "## 你的身份",
        role.description,
    ]

    if fellow_wolves:
        lines.extend([
            "",
            f"已知狼人队友：{', '.join(fellow_wolves)}",
        ])

    lines.extend([
        "",
        "## 信息边界",
        "- 只能依据你这个角色本来能知道的信息进行推理。",
        "- 公开发言必须像真实桌游玩家一样自然。",
        "- 隐藏身份信息应当保密，除非你主动选择跳身份、悍跳或故意误导。",
        "- 你可以撒谎、误导、隐瞒，但要符合当前身份和局势。",
        "- 不要提到自己是 AI、语言模型，或在遵循提示词。",
        "",
        "## 胜利目标",
        "- 好人阵营在所有狼人出局时获胜。",
        "- 狼人阵营在人数追平或超过好人阵营时获胜。",
        "- 追求像真实对局一样可信的桌面表现，而不是机械地说真话。",
        "",
        RESPONSE_FORMAT,
    ])

    return "\n".join(lines)


def night_werewolf_prompt(
    alive_names: List[str],
    dead_names: List[str],
    fellow_wolves: List[str],
    game_log: List[str],
    previous_suggestions: Optional[List[str]] = None,
    coordination_notes: Optional[List[str]] = None,
    suspicion: Optional[Dict[str, float]] = None,
    role_guesses: Optional[Dict[str, str]] = None,
    trust: Optional[Dict[str, float]] = None,
) -> str:
    alive_str = "\n".join(f"  {name}" for name in alive_names)

    lines = [
        "## 夜晚阶段：狼人刀人",
        "",
        _state_section(alive_names, dead_names),
        "",
        "可击杀目标：",
        alive_str,
        "",
        f"狼队成员：{', '.join(fellow_wolves) if fellow_wolves else '未显示'}",
    ]

    if previous_suggestions:
        lines.extend([
            "",
            "队友当前建议：",
            *[f"  {item}" for item in previous_suggestions],
        ])

    if coordination_notes:
        lines.extend([
            "",
            "最近的狼队协作记录：",
            *[f"  {note}" for note in coordination_notes[-4:]],
        ])

    belief_lines = _belief_section(suspicion=suspicion, role_guesses=role_guesses, trust=trust)
    if belief_lines:
        lines.extend(["", *belief_lines])

    if game_log:
        lines.extend([
            "",
            "最近公开事件：",
            *[f"  {event}" for event in game_log[-8:]],
        ])

    lines.extend([
        "",
        "请选择一个最有利于狼队长期局势的刀口。",
        "你可以优先考虑高价值神职、强势带队位，或更具迷惑性的刀法。",
        "请结合队友思路协同决策，而不是孤立做选择。",
        "",
        "必填字段：",
        "REASON: <私下推理>",
        "SUSPECT: <玩家名或 none>",
        "TRUST: <玩家名或 none>",
        "PLAN: <简短策略>",
        "CLAIM: none",
        "TARGET: <玩家名>",
    ])

    return "\n".join(lines)


def night_seer_prompt(
    alive_names: List[str],
    dead_names: List[str],
    previous_checks: List[str],
    game_log: List[str],
    public_plan_history: Optional[List[str]] = None,
    suspicion: Optional[Dict[str, float]] = None,
    role_guesses: Optional[Dict[str, str]] = None,
    trust: Optional[Dict[str, float]] = None,
) -> str:
    alive_str = "\n".join(f"  {name}" for name in alive_names)

    lines = [
        "## 夜晚阶段：预言家查验",
        "",
        _state_section(alive_names, dead_names),
        "",
        "可查验目标：",
        alive_str,
    ]

    if previous_checks:
        lines.extend([
            "",
            "你已经确认过的查验结果：",
            *[f"  {check}" for check in previous_checks],
        ])

    if public_plan_history:
        lines.extend([
            "",
            "你之前的公开思路/发言计划：",
            *[f"  {item}" for item in public_plan_history[-4:]],
        ])

    belief_lines = _belief_section(suspicion=suspicion, role_guesses=role_guesses, trust=trust)
    if belief_lines:
        lines.extend(["", *belief_lines])

    if game_log:
        lines.extend([
            "",
            "最近公开事件：",
            *[f"  {event}" for event in game_log[-6:]],
        ])

    lines.extend([
        "",
        "请选择一个能为明天带来最高信息价值的查验目标。",
        "优先考虑那些能帮助你明天组织可信发言线的人。",
        "",
        "必填字段：",
        "REASON: <私下推理>",
        "SUSPECT: <玩家名或 none>",
        "TRUST: <玩家名或 none>",
        "PLAN: <简短策略>",
        "CLAIM: none",
        "TARGET: <玩家名>",
    ])

    return "\n".join(lines)


def night_witch_prompt(
    alive_names: List[str],
    dead_names: List[str],
    werewolf_target: str,
    has_antidote: bool,
    has_poison: bool,
    game_log: List[str],
    witch_decision_history: Optional[List[str]] = None,
    suspicion: Optional[Dict[str, float]] = None,
    role_guesses: Optional[Dict[str, str]] = None,
    trust: Optional[Dict[str, float]] = None,
) -> str:
    lines = [
        "## 夜晚阶段：女巫决策",
        "",
        _state_section(alive_names, dead_names),
        "",
        f"今晚被狼人刀中的玩家：{werewolf_target}",
        f"解药是否可用：{'yes' if has_antidote else 'no'}",
        f"毒药是否可用：{'yes' if has_poison else 'no'}",
    ]

    belief_lines = _belief_section(suspicion=suspicion, role_guesses=role_guesses, trust=trust)
    if belief_lines:
        lines.extend(["", *belief_lines])

    if witch_decision_history:
        lines.extend([
            "",
            "你之前的女巫决策记录：",
            *[f"  {item}" for item in witch_decision_history[-4:]],
        ])

    if game_log:
        lines.extend([
            "",
            "最近公开事件：",
            *[f"  {event}" for event in game_log[-6:]],
        ])

    lines.extend([
        "",
        "请平衡短期生存与长期收益。",
        "思考这个刀口是否像高价值好人位、诱导刀，还是可放弃的普通位置。",
        "",
        "必填字段：",
        "REASON: <私下推理>",
        "SUSPECT: <玩家名或 none>",
        "TRUST: <玩家名或 none>",
        "PLAN: <简短策略>",
        "CLAIM: none",
        "SAVE: yes 或 no",
        "POISON: <玩家名或 none>",
    ])

    return "\n".join(lines)


def day_discussion_prompt(
    player_name: str,
    alive_names: List[str],
    dead_names: List[str],
    night_summary: str,
    discussion_history: List[str],
    game_log: List[str],
    suspicion: Optional[Dict[str, float]] = None,
    role_guesses: Optional[Dict[str, str]] = None,
    trust: Optional[Dict[str, float]] = None,
) -> str:
    lines = [
        "## 白天阶段：讨论发言",
        "",
        _state_section(alive_names, dead_names),
        f"昨夜结果摘要：{night_summary}",
    ]

    if discussion_history:
        lines.extend([
            "",
            "目前桌上已经出现的发言：",
            *[f"  {speech}" for speech in discussion_history[-10:]],
        ])

    belief_lines = _belief_section(suspicion=suspicion, role_guesses=role_guesses, trust=trust)
    if belief_lines:
        lines.extend(["", *belief_lines])

    if game_log:
        lines.extend([
            "",
            "最近公开回合信息：",
            *[f"  {event}" for event in game_log[-6:]],
        ])

    lines.extend([
        "",
        f"现在轮到 {player_name} 发言。",
        "你的公开发言必须像真实桌游玩家一样可信，除非出于策略考虑，否则不要表现出不合理的私下确定性。",
        "请尽量使用中文进行公开发言。",
        "",
        "必填字段：",
        "REASON: <私下推理>",
        "SUSPECT: <玩家名或 none>",
        "TRUST: <玩家名或 none>",
        "PLAN: <简短策略>",
        "CLAIM: <身份声称或 none>",
        "SPEECH: <公开发言>",
    ])

    return "\n".join(lines)


def day_vote_prompt(
    player_name: str,
    alive_names: List[str],
    dead_names: List[str],
    discussion_summary: str,
    game_log: List[str],
    suspicion: Optional[Dict[str, float]] = None,
    role_guesses: Optional[Dict[str, str]] = None,
    trust: Optional[Dict[str, float]] = None,
    vote_history: Optional[List[str]] = None,
) -> str:
    alive_str = "\n".join(f"  {name}" for name in alive_names)

    lines = [
        "## 白天阶段：投票放逐",
        "",
        _state_section(alive_names, dead_names),
        "",
        "可投票目标：",
        alive_str,
        f"讨论摘要：{discussion_summary}",
    ]

    if vote_history:
        lines.extend([
            "",
            "之前的投票记录：",
            *[f"  {vote}" for vote in vote_history[-5:]],
        ])

    belief_lines = _belief_section(suspicion=suspicion, role_guesses=role_guesses, trust=trust)
    if belief_lines:
        lines.extend(["", *belief_lines])

    if game_log:
        lines.extend([
            "",
            "最近公开事件：",
            *[f"  {event}" for event in game_log[-4:]],
        ])

    lines.extend([
        "",
        f"{player_name}，请投出你这一票。",
        "你的投票应当与桌面叙事保持可信一致。",
        "",
        "必填字段：",
        "REASON: <私下推理>",
        "SUSPECT: <玩家名或 none>",
        "TRUST: <玩家名或 none>",
        "PLAN: <简短策略>",
        "CLAIM: <身份声称或 none>",
        "VOTE: <玩家名>",
    ])

    return "\n".join(lines)


def day_final_statement_prompt(
    player_name: str,
    alive_names: List[str],
    dead_names: List[str],
    discussion_summary: str,
    top_targets: List[str],
    game_log: List[str],
    suspicion: Optional[Dict[str, float]] = None,
    role_guesses: Optional[Dict[str, str]] = None,
    trust: Optional[Dict[str, float]] = None,
) -> str:
    lines = [
        "## 白天阶段：投票前总结陈词",
        "",
        _state_section(alive_names, dead_names),
        f"讨论摘要：{discussion_summary}",
        f"当前主要嫌疑人：{', '.join(top_targets) if top_targets else 'none'}",
    ]

    belief_lines = _belief_section(suspicion=suspicion, role_guesses=role_guesses, trust=trust)
    if belief_lines:
        lines.extend(["", *belief_lines])

    if game_log:
        lines.extend([
            "",
            "最近公开事件：",
            *[f"  {event}" for event in game_log[-5:]],
        ])

    lines.extend([
        "",
        f"{player_name}，请在投票前做一段简短总结陈词。",
        "请尽量使用中文。",
        "",
        "必填字段：",
        "REASON: <私下推理>",
        "SUSPECT: <玩家名或 none>",
        "TRUST: <玩家名或 none>",
        "PLAN: <简短策略>",
        "CLAIM: <身份声称或 none>",
        "SPEECH: <公开总结陈词>",
    ])

    return "\n".join(lines)


def runoff_discussion_prompt(
    player_name: str,
    alive_names: List[str],
    dead_names: List[str],
    tied_targets: List[str],
    discussion_history: List[str],
    game_log: List[str],
    suspicion: Optional[Dict[str, float]] = None,
    role_guesses: Optional[Dict[str, str]] = None,
    trust: Optional[Dict[str, float]] = None,
) -> str:
    lines = [
        "## 白天阶段：平票加赛发言",
        "",
        _state_section(alive_names, dead_names),
        f"当前平票玩家：{', '.join(tied_targets)}",
    ]

    if discussion_history:
        lines.extend([
            "",
            "上一轮主要讨论内容：",
            *[f"  {speech}" for speech in discussion_history[-8:]],
        ])

    belief_lines = _belief_section(suspicion=suspicion, role_guesses=role_guesses, trust=trust)
    if belief_lines:
        lines.extend(["", *belief_lines])

    if game_log:
        lines.extend([
            "",
            "最近公开事件：",
            *[f"  {event}" for event in game_log[-5:]],
        ])

    lines.extend([
        "",
        f"{player_name}，请围绕平票玩家做一段简短加赛发言。",
        "请尽量使用中文。",
        "",
        "必填字段：",
        "REASON: <私下推理>",
        "SUSPECT: <玩家名或 none>",
        "TRUST: <玩家名或 none>",
        "PLAN: <简短策略>",
        "CLAIM: <身份声称或 none>",
        "SPEECH: <公开加赛发言>",
    ])

    return "\n".join(lines)


def last_words_prompt(
    player_name: str,
    alive_names: List[str],
    dead_names: List[str],
    elimination_reason: str,
    game_log: List[str],
    suspicion: Optional[Dict[str, float]] = None,
    role_guesses: Optional[Dict[str, str]] = None,
    trust: Optional[Dict[str, float]] = None,
) -> str:
    lines = [
        "## 出局阶段：遗言",
        "",
        _state_section(alive_names, dead_names),
        f"你的出局原因：{elimination_reason}",
    ]

    belief_lines = _belief_section(suspicion=suspicion, role_guesses=role_guesses, trust=trust)
    if belief_lines:
        lines.extend(["", *belief_lines])

    if game_log:
        lines.extend([
            "",
            "最近公开事件：",
            *[f"  {event}" for event in game_log[-5:]],
        ])

    lines.extend([
        "",
        f"{player_name}，请留下你的遗言。",
        "请尽量使用中文。",
        "",
        "必填字段：",
        "REASON: <私下推理>",
        "SUSPECT: <玩家名或 none>",
        "TRUST: <玩家名或 none>",
        "PLAN: <留给场上的提醒或策略>",
        "CLAIM: <身份声称或 none>",
        "SPEECH: <公开遗言>",
    ])

    return "\n".join(lines)


def hunter_shot_prompt(
    alive_names: List[str],
    dead_names: List[str],
    game_log: List[str],
    shot_history: Optional[List[str]] = None,
    suspicion: Optional[Dict[str, float]] = None,
    role_guesses: Optional[Dict[str, str]] = None,
    trust: Optional[Dict[str, float]] = None,
) -> str:
    alive_str = "\n".join(f"  {name}" for name in alive_names)

    lines = [
        "## 死亡触发：猎人开枪",
        "",
        _state_section(alive_names, dead_names),
        "",
        "你可以选择开枪带走一名存活玩家，也可以选择不开枪。",
        "可选目标：",
        alive_str,
    ]

    belief_lines = _belief_section(suspicion=suspicion, role_guesses=role_guesses, trust=trust)
    if belief_lines:
        lines.extend(["", *belief_lines])

    if shot_history:
        lines.extend([
            "",
            "你过往的开枪记录：",
            *[f"  {item}" for item in shot_history[-3:]],
        ])

    if game_log:
        lines.extend([
            "",
            "最近公开事件：",
            *[f"  {event}" for event in game_log[-6:]],
        ])

    lines.extend([
        "",
        "只有在对你阵营的预期收益明显为正时才开枪。",
        "必填字段：",
        "REASON: <私下推理>",
        "SUSPECT: <玩家名或 none>",
        "TRUST: <玩家名或 none>",
        "PLAN: <简短策略>",
        "CLAIM: none",
        "TARGET: <玩家名或 none>",
    ])

    return "\n".join(lines)
