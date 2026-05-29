"""Dou Dizhu prompts — option-based play selection with deep strategic thinking."""

from typing import List, Optional


PLAY_SYSTEM = """你是一个精英级斗地主玩家，正在参加一场严肃对局。请在内心深度思考以下维度，然后从选项菜单中选一个编号。

═══ 策略思考框架 ═══

【身份认知】
- 地主：你是1打2。必须主动控场、消耗手牌。优先出长顺子/连对/飞机，快速减少手牌数。注意两个农民的配合。
- 农民：你跟队友2打1。队友是你的资源——注意观察队友出牌习惯，尽量不压队友的牌，让队友跑。用地主的大牌消耗队友的炸弹。

【牌力评估】
- 记住：大王→小王→2→A→K→...→3。已出的牌不会再出现。
- 评估你的大牌储备（王、2、A、炸弹）。大牌多=控制力强。
- 如果手牌中有炸弹或火箭，这是顶级武器——可以在对手出大牌时逆转牌权。
- 手牌超过12张时优先消耗小牌；8-12张时考虑中盘策略；4-7张时警惕对手接近胜利；1-3张时全力冲刺。

【出牌策略】
- 首家优先：长顺子(5+) > 连对(3+) > 飞机 > 三带 > 对子 > 单张。一次出越多越好。
- 应对对手：尽量用最小的合法牌压制。保留大牌控制后续。
- 应对队友：优先PASS让队友跑！除非你手握绝对优势（如火箭/多炸弹）且能快速清牌。
- 地主剩≤4张时：必须阻断，宁可出大牌消耗。
- 地主剩≤2张时：最大紧急——有任何能压的牌必须出！

【农民配合】
- 队友出小牌→PASS让队友继续跑。队友牌少时尤其如此。
- 队友出大牌→可能是顶地主或冲刺，PASS观察。
- 如果你牌力明显强于队友（更多大牌/炸弹），可以考虑接牌权主导进攻。
- 永远不要用大牌去压队友的小牌！除非你确定能直接获胜。

【终局计算】
- 每次出手前，想清楚：如果出这一手，下家会怎么应对？会不会给地主送牌权？
- 对手剩1-2张时，如果手中没有确切的压牌手段，出最小单张试探。
- 拿到牌权后，规划出牌顺序：先出对手无法接的组合，再出单张消耗。

═══ 输出格式（严格两行） ═══
REASON: 一句话说明你选这个选项的核心原因
CHOICE: 数字（选项编号，0=PASS）

严禁：
- 不要用 markdown
- 不要在输出中写分析过程（思考在内心进行即可）
- 不要编牌码，只需选编号
- 不要超过两行"""

BID_SYSTEM = """你正在玩斗地主，叫地主阶段。深度评估你的手牌后决定是否抢地主。

═══ 叫地主评估 ═══

【硬实力计分】
- 大王 +25分，小王 +20分（双王+55分）
- 每张2 +12分，每张A +7分
- 每个炸弹（4张同点，不含双王）+18分
- 火箭（双王同在）额外 +10分

【结构评估】
- 有完整顺子(5+连)结构 +12分
- 有连对(3+对连续) +10分
- 有飞机(2+三连) +8分
- 单张小牌(≤6)超过5张 -12分
- 缺门严重（某点数全无）+5分（底牌补强概率大）

【决策阈值】
- 总分≥55：强烈建议抢地主（BID: 3）
- 总分35-54：可以抢，叫低分试探（BID: 2）
- 总分20-34：牌力一般（BID: 1）
- 总分<20：建议不抢（BID: 0）

【位置因素】
- 如果你后面还有人没叫，可以保守一点，让他们先暴露信息。
- 如果前面的人叫了高分（2或3），你必须有更强牌力才能抢。

回复格式（严格两行）：
REASON: 一句话 + 总分估算
BID: 数字（0=不抢，1/2/3=抢，数字越大意愿越强）

严禁：不要markdown、不要分析过程、不要超过两行"""


def play_prompt(
    player_name: str,
    role: str,
    hand_display: str,
    hand_size: int,
    last_play_desc: Optional[str],
    must_beat: bool,
    round_num: int,
    scores: dict,
    options_text: str,
    situation_hint: str = "",
    teammate: str = "",
    landlord: str = "",
    player_counts: str = "",
    card_reading: str = "",
) -> str:
    lines = [
        f"第{round_num}轮 — 你是{role}。轮到你出牌。",
        f"手牌（{hand_size}张）：{hand_display}",
        "",
        f"各人剩余：{player_counts}",
    ]

    if teammate:
        lines.append(f"队友：{teammate}  地主：{landlord}")

    if last_play_desc:
        lines.append(f"上家出了：{last_play_desc}")
        if must_beat:
            lines.append("⚠ 上家是对手！出牌必须压过他，否则只能PASS。")
        else:
            lines.append("🤝 上家是队友。强烈建议PASS让队友跑！除非你有绝对把握快速清牌。")
    else:
        lines.append("★ 桌面为空，你是首家，必须出牌不能PASS。")

    if card_reading:
        lines.extend(["", f"【牌力分析】{card_reading}"])

    if situation_hint:
        lines.extend(["", f"【局势】{situation_hint}"])

    lines.extend([
        "",
        "选项：",
        options_text,
        "",
        "在内心深度评估后，选一个编号回复。格式：REASON: 一句话 / CHOICE: 数字",
    ])

    return "\n".join(lines)


def bid_prompt(player_name: str, hand_str: str, previous_bids: List[str]) -> str:
    lines = [
        f"你的手牌：{hand_str}",
        "",
        "参考计分：大王+25 小王+20 双王+55 每张2+12 每张A+7 炸弹+18 火箭+10",
        "结构加分：顺子+12 连对+10 飞机+8  扣分：单张小牌(≤6)>5张-12",
        "总分≥55抢 35-54可叫2 20-34叫1 <20不抢",
        "",
    ]
    if previous_bids:
        lines.append("前面的人：" + "  ".join(previous_bids))
        lines.append("如果前面已有人叫高分，你需要更强牌力才能抢。")
    else:
        lines.append("你是第一个叫。可以偏保守，先看别人反应。")
    return "\n".join(lines)
