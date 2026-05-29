"""Prompt templates for Three Kingdoms Kill — option-based selection."""

from typing import List, Optional


PLAY_SYSTEM = """你是三国杀精英玩家。每回合从提供的选项中做出最优选择。

═══ 决策框架：先分析，再行动 ═══

【第1步 · 评估局势】
- 谁是最大威胁？→ 查看场上HP最低的敌人，优先收割
- 谁手牌最多？→ 用【过河拆桥】或【顺手牵羊】削弱
- 你的防御如何？→ 手牌中有【闪】吗？没有的话出杀会暴露破绽
- 你能斩杀谁？→ 如果你有【杀】且某敌人1HP且无闪的可能，出手

【第2步 · 优先级排序】
① 保命 > 杀敌 > 攒牌  （永远的铁律）
② HP ≤ 1 时，有【桃】立刻吃或留着防濒死
③ 手牌 ≤ 2 时，优先用【无中生有】或【苦肉】补牌
④ 有【闪】在手才放心出杀，否则优先留牌防守
⑤ 回合结束时手牌超过体力必须弃牌，提前规划

【第3步 · 选最优行动】
- 【无中生有】→ 手牌少时第一个用，增加后续选择空间
- 【过河拆桥】/【顺手牵羊】→ 优先瞄准手牌最多的敌人
- 【南蛮入侵】/【万箭齐发】→ 自己持有对应防御牌（杀/闪）时才用
- 【桃园结义】→ 只有当你残血且敌人满血，或队友更需要时才用
- 【杀】→ 优先杀1HP残血敌人，其次杀对你威胁大的

═══ 技能决策 ═══
- 咆哮：无限出杀。手中有多张杀时——全打出去，持续施压不要停
- 武圣：杀闪互换。可以将闪当杀出增加进攻，或将杀当闪留作防御
- 苦肉：HP ≥ 3 时积极用（扣1血摸2牌净赚）；HP ≤ 2 时谨慎（再扣可能濒死）
- 刚烈/反馈：受伤后自动触发，不需要你操作
- 空城·守：无手牌时免疫【杀】。可故意弃光手牌进入无敌状态

═══ 输出格式 ═══
REASON: 简要分析局势 + 说明为什么选这个选项（2-4句话）
CHOICE: 数字

禁止：不要编造不存在的牌名、不要markdown、不要列举所有选项"""

IDENTITY_SYSTEM = """你是三国杀精英身份局玩家。每回合从提供的选项中做出最优选择。

═══ 身份局核心规则 ═══
- 主公（公开）：消灭所有反贼和内奸
- 忠臣（隐藏）：保护主公，消灭反贼和内奸
- 反贼（隐藏）：杀死主公即为胜利
- 内奸（隐藏）：先灭反贼、再除忠臣、最后与主公单挑

【身份推理指南】
- 攻击主公的人 → 很可能是反贼
- 保护主公、攻击反贼的人 → 很可能是忠臣
- 作为内奸 → 前期必须伪装成忠臣，不要攻击主公
- 观察其他玩家的行动来推断他们的身份

═══ 决策框架 ═══

【第1步 · 评估局势】
- 主公的HP是多少？主公危险吗？
- 谁在攻击主公？谁在保护主公？
- 场上哪些人大概率是反贼？哪些像是忠臣？

【第2步 · 优先级排序】
① 保命 > 完成身份目标 > 杀敌 > 攒牌
② 作为主公：生存第一，不要盲狙可能的忠臣
③ 作为忠臣：主公的危险就是你的危险，优先保护主公
④ 作为反贼：速度集火主公，迟则生变
⑤ 作为内奸：先帮助杀反贼（假装忠臣），保持低调

【第3步 · 选最优行动】
- 反贼：有杀就对着主公打！除非自己命悬一线
- 忠臣：攻击正在威胁主公的敌人；如果主公HP低，考虑留桃救主
- 主公：谨慎选择目标——分辨谁是忠臣谁是反贼
- 内奸：平衡局面，不要让任何一方太强

═══ 技能决策 ═══
- 咆哮：无限出杀。手中有多张杀时——全打出去，持续施压不要停
- 武圣：杀闪互换。可以将闪当杀出增加进攻，或将杀当闪留作防御
- 苦肉：HP ≥ 3 时积极用（扣1血摸2牌净赚）；HP ≤ 2 时谨慎（再扣可能濒死）
- 刚烈/反馈：受伤后自动触发，不需要你操作
- 空城·守：无手牌时免疫【杀】。可故意弃光手牌进入无敌状态

═══ 输出格式 ═══
REASON: 基于你的身份分析局势 + 说明选择理由（2-4句话）
CHOICE: 数字

禁止：不要编造不存在的牌名、不要markdown、不要列举所有选项"""


def play_turn_prompt(
    player_name: str,
    hp: int,
    max_hp: int,
    hand_sum: str,
    hand_str: str,
    skill_name: str,
    skill_desc: str,
    sha_used: bool,
    players_state: str,
    options_text: str,
    situation_hint: str = "",
    history: Optional[List[str]] = None,
    identity_label: str = "",
) -> str:
    """Build a strategic turn prompt. Includes decision cues and priority
    reminders to steer the model toward optimal play."""
    hearts = "♥" * hp + "♡" * (max_hp - hp)

    # Build header
    lines = [
        f"╔══ 你的回合 — {player_name} ══╗",
        f"║ 体力：{hearts}  ({hp}/{max_hp})",
        f"║ 技能：【{skill_name}】— {skill_desc}",
        f"║ 手牌：{hand_sum}",
    ]
    # Show individual hand cards indented
    for card_line in hand_str.split("\n"):
        if card_line.strip():
            lines.append(f"║   {card_line.strip()}")

    if identity_label:
        lines.append(f"║ 身份：{identity_label}")

    lines.append("╚" + "═" * 38 + "╝")

    lines.append("")
    lines.append(f"【场上局势】{players_state}")

    if sha_used:
        lines.append("")
        lines.append("⚠ 本回合已使用过【杀】，不能再出杀（除非有咆哮技能）。")

    # Situation hint — this is the AI-generated strategic cue
    if situation_hint:
        lines.append("")
        lines.append(f"【战略提示】{situation_hint}")

    # Recent events
    if history:
        lines.append("")
        lines.append("【最近事件】")
        for evt in history[-4:]:
            lines.append(f"  · {evt}")

    # Decision reminders based on game state
    lines.append("")
    lines.append("【决策提醒】")
    if hp <= 1:
        lines.append("  ⚠ 你处于濒死边缘！优先吃桃或防守，不要冒险出杀。")
    elif hp <= 2:
        lines.append("  ⚡ HP偏低，优先考虑防守或吃桃恢复。")
    no_shan = "闪×" not in hand_sum
    if no_shan:
        lines.append("  🛡 你手中无【闪】！出杀前想清楚——敌人可能反击。")
    has_wuzhong = "无中生有" in hand_sum
    if has_wuzhong and len(hand_str.split("\n")) <= 3:
        lines.append("  💡 手牌偏少，先打【无中生有】补牌再行动。")
    has_blood_skill = ("苦肉" in skill_name) and hp >= 3
    if has_blood_skill:
        lines.append("  💡 HP充足，可优先用【苦肉】摸牌增加选择。")

    # Options
    lines.append("")
    lines.append("【可选行动】")
    lines.append(options_text)
    lines.append("")
    lines.append("→ 输出格式：REASON: 分析+理由（2-4句）\\nCHOICE: 数字")

    return "\n".join(lines)


def response_option_prompt(
    player_name: str,
    hp: int,
    hand_sum: str,
    hand_str: str,
    skill_name: str,
    prompt_text: str,
    players_state: str,
    options_text: str,
) -> str:
    """Build a response prompt (e.g. respond to 杀 with 闪).
    Now includes strategic context about whether response is worth it."""
    lines = [
        f"══ 响应阶段 — {player_name} ══",
        f"体力：{hp}  |  技能：【{skill_name}】  |  手牌：{hand_sum}",
    ]
    for card_line in hand_str.split("\n"):
        if card_line.strip():
            lines.append(f"  {card_line.strip()}")

    lines.append("")
    lines.append(f"【场上】{players_state}")
    lines.append("")
    lines.append(f"【事件】{prompt_text}")
    lines.append("")

    # Strategic context for response decisions
    lines.append("【响应策略】")
    lines.append("  如果出牌响应：消耗一张牌但避免受伤")
    lines.append("  如果PASS不响应：省下牌但受到伤害")
    if hp <= 1:
        lines.append("  ⚠ 你HP=1！如果手中有响应牌，强烈建议响应——受伤即死。")
    elif hp <= 2:
        lines.append("  ⚡ HP偏低，建议优先响应避免进一步受伤。")
    else:
        lines.append("  HP尚可，可权衡：省下这张牌留着后续进攻 vs 避免本次伤害。")

    lines.append("")
    lines.append("【选项】")
    lines.append(options_text)
    lines.append("")
    lines.append("→ 格式：REASON: 简要理由\\nCHOICE: 数字  (0=PASS)")

    return "\n".join(lines)


def discard_prompt(
    player_name: str,
    hp: int,
    max_hp: int,
    hand_count: int,
    hand_sum: str,
    hand_str: str,
    excess: int,
    options_text: str,
) -> str:
    """Build discard phase prompt. Now includes card priority guidance."""
    lines = [
        f"══ 弃牌阶段 — {player_name} ══",
        f"体力：{hp}/{max_hp}  |  手牌：{hand_count}张",
        f"手牌分布：{hand_sum}",
    ]
    for card_line in hand_str.split("\n"):
        if card_line.strip():
            lines.append(f"  {card_line.strip()}")

    lines.append("")
    lines.append(f"手牌({hand_count}) > 体力({hp})，需要弃掉 {excess} 张。")
    lines.append("")

    # Priority guide for keeping cards
    lines.append("【弃牌优先级 · 优先保留靠前的】")
    lines.append("  1. 【桃】— 保命第一，濒死时能自救")
    lines.append("  2. 【闪】— 唯一防御手段，至少留1张")
    lines.append("  3. 【杀】— 下回合还要输出，但防御更重要")
    lines.append("  4. 【锦囊】— 无中生有 > 过河拆桥/顺手牵羊 > AOE > 桃园结义")
    if hp <= 1:
        lines.append("  ⚠ 你HP=1，无论如何留一张【桃】！")
    lines.append("")
    lines.append("选项：")
    lines.append(options_text)
    lines.append("")
    lines.append("→ 格式：REASON: 弃牌理由\\nCHOICE: 数字")

    return "\n".join(lines)


def steal_prompt(
    player_name: str,
    source_name: str,
    hand_str: str,
    options_text: str,
) -> str:
    """Build prompt for feedback skill: choose which card to steal."""
    lines = [
        f"══ 反馈技能 — {player_name} ══",
        f"你受到 {source_name} 的伤害，触发【反馈】——你可以获得对方1张手牌。",
        f"",
        f"{source_name} 的手牌：",
    ]
    for card_line in hand_str.split("\n"):
        if card_line.strip():
            lines.append(f"  {card_line.strip()}")
    lines.append("")
    lines.append("【选择策略】优先拿【桃】或【闪】（削弱对方防御/续航），其次拿关键锦囊。")
    lines.append("")
    lines.append("选项：")
    lines.append(options_text)
    lines.append("")
    lines.append("→ 格式：REASON: 选择理由\\nCHOICE: 数字")

    return "\n".join(lines)


def target_card_prompt(
    player_name: str,
    target_name: str,
    spell_name: str,
    target_hand_str: str,
    options_text: str,
) -> str:
    """Build prompt for choosing target's card (过河拆桥/顺手牵羊)."""
    lines = [
        f"══ 选择目标牌 — {player_name} ══",
        f"你对 {target_name} 使用【{spell_name}】。",
        f"",
        f"{target_name} 的手牌：",
    ]
    for card_line in target_hand_str.split("\n"):
        if card_line.strip():
            lines.append(f"  {card_line.strip()}")
    lines.append("")
    lines.append("【选择策略】优先拆/拿【桃】和【闪】（破坏其防御），其次拆锦囊。")
    lines.append("")
    lines.append("选项：")
    lines.append(options_text)
    lines.append("")
    lines.append("→ 格式：REASON: 选择理由\\nCHOICE: 数字")

    return "\n".join(lines)


def format_players_state(players, game_mode="free_for_all") -> str:
    """Format all players' public state.
    In identity mode: lord's identity is public, others are hidden (???).
    Dead players' identities are revealed."""
    from .skills import SKILL_INFO
    from .player import Identity, IDENTITY_NAMES

    parts = []
    for p in players:
        alive_str = "[活]" if p.is_alive else "[亡]"
        skill_name = SKILL_INFO[p.skill]['name'] if p.skill else "无"

        # Identity display
        id_display = ""
        if game_mode == "identity" and hasattr(p, 'identity') and p.identity:
            if p.identity_revealed or not p.is_alive:
                id_display = f" [{IDENTITY_NAMES[p.identity]}]"
            else:
                id_display = " [???]"

        parts.append(
            f"{alive_str} {p.name}{id_display}: {p.hp}HP {p.card_count}手牌 [{skill_name}]"
        )
    return "  |  ".join(parts)
