"""Three Kingdoms Kill game engine — option-based AI selection."""

import random
import re
import time
from typing import List, Optional

from core.engine import GameEngine
from core.logger import GameLogger
from core.utils import Colors, parse_keyword_response, truncate

from .cards import (
    Card, CardType, card_at, create_deck,
    format_options_for_prompt, generate_card_choice_options,
    generate_play_options, generate_response_options,
    hand_list_str, hand_summary,
)
from .player import (
    SanguoshaPlayer, Identity, IDENTITY_NAMES, IDENTITY_DISTRIBUTION,
)
from .prompts import (
    PLAY_SYSTEM, IDENTITY_SYSTEM, discard_prompt, format_players_state,
    play_turn_prompt, response_option_prompt,
    steal_prompt, target_card_prompt,
)
from .skills import SKILL_INFO, SkillID, random_skill


class SanguoshaEngine(GameEngine):
    def __init__(self, players, config=None, logger=None, game_mode="free_for_all"):
        super().__init__(players, config)
        self.logger = logger
        self.deck: List[Card] = []
        self.discard: List[Card] = []
        self.turn_idx = 0
        self.history: List[str] = []

        mode_lower = game_mode.lower() if game_mode else "free_for_all"
        if mode_lower not in ("free_for_all", "identity"):
            raise ValueError(
                f"Invalid game_mode '{game_mode}'. "
                f"Must be 'free_for_all' or 'identity'."
            )
        self.game_mode = mode_lower

    def _draw(self, n=1) -> List[Card]:
        """Draw cards from deck. Recycles discard pile when deck runs out."""
        cards = []
        for _ in range(n):
            if not self.deck:
                random.shuffle(self.discard)
                self.deck = self.discard
                self.discard = []
                if self.deck:
                    self._log_action(
                        "reshuffle_deck",
                        source="discard",
                        target="deck",
                        cards=self.deck[:],
                        zone_from="discard",
                        zone_to="deck",
                        extra={"deck_count": len(self.deck)},
                    )
                else:
                    # Empty discard too — create fresh deck (shouldn't happen)
                    self.deck = create_deck()
                    self._log_action(
                        "reshuffle_deck",
                        source="new",
                        target="deck",
                        cards=self.deck[:],
                        zone_from="new",
                        zone_to="deck",
                        extra={"deck_count": len(self.deck), "note": "fresh deck created"},
                    )
            cards.append(self.deck.pop())
        return cards

    def _consume_card(self, player: "SanguoshaPlayer", card: Card) -> None:
        """Remove card from player's hand and add to discard pile for tracking."""
        if card and card in player.hand:
            player.hand.remove(card)
            self.discard.append(card)

    @staticmethod
    def _card_payload(card: Optional[Card]) -> Optional[dict]:
        if card is None:
            return None
        return {
            "id": getattr(card, "card_id", ""),
            "name": card.name,
        }

    def _deck_payload(self) -> dict:
        """Serialize deck and discard pile state for complete reconstruction."""
        return {
            "deck_count": len(self.deck),
            "deck": [self._card_payload(c) for c in self.deck],
            "discard_count": len(self.discard),
            "discard": [self._card_payload(c) for c in self.discard],
        }

    def _players_payload(self) -> List[dict]:
        payload = []
        for p in self.players:
            item = {
                "name": p.name,
                "hp": p.hp,
                "max_hp": p.max_hp,
                "alive": p.is_alive,
                "hand_count": p.card_count,
                "hand": [self._card_payload(card) for card in p.hand],
                "skill": p.skill.value if p.skill else "",
                "skill_name": SKILL_INFO[p.skill]["name"] if p.skill else "",
            }
            if self.game_mode == "identity" and p.identity:
                item["identity"] = p.identity.value
                item["identity_revealed"] = p.identity_revealed
            payload.append(item)
        return payload

    def _log_state(self, label: str, actor: str = "", extra: Optional[dict] = None) -> None:
        if not self.logger:
            return
        data = {
            "round": self.round,
            "label": label,
            "actor": actor,
            "players": self._players_payload(),
            "deck": self._deck_payload(),
        }
        if extra:
            data.update(extra)
        self.logger.log_event("sgs_state", data)

    def _log_action(
        self,
        action_type: str,
        source: str = "",
        target: str = "",
        cards: Optional[List[Card]] = None,
        visual: str = "global",
        zone_from: str = "",
        zone_to: str = "",
        extra: Optional[dict] = None,
    ) -> None:
        if not self.logger:
            return
        data = {
            "round": self.round,
            "action_type": action_type,
            "source": source,
            "target": target,
            "visual": visual,
            "zone_from": zone_from,
            "zone_to": zone_to,
            "cards": [self._card_payload(card) for card in (cards or []) if card is not None],
            "players": self._players_payload(),
        }
        if extra:
            data.update(extra)
        self.logger.log_event("sgs_action", data)

    # ---- Query (with thinking capture) ----

    def _query(self, player, phase, prompt, system="", temp=0.7):
        t0 = time.time()
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": prompt})
        if self.logger:
            self.logger.log_prompt(player.name, phase, 0, system, prompt)
        try:
            thinking, response = player.model.chat(msgs, temperature=temp)
        except Exception as e:
            thinking = ""
            response = f"[ERROR: {type(e).__name__}: {e}]"
        parsed = parse_keyword_response(response)
        elapsed_ms = (time.time() - t0) * 1000
        if self.logger:
            self.logger.log_response(player.name, phase, 0, response, parsed, 0, elapsed_ms, thinking=thinking)
        if thinking and len(thinking) > 50:
            try:
                self._print_dim(f"  [{player.name}] 思考 {len(thinking)} 字符: {truncate(thinking, 150)}")
            except UnicodeEncodeError:
                self._print_dim(f"  [{player.name}] 思考 {len(thinking)} 字符 (编码限制无法显示)")
        return thinking, response, parsed

    # ---- Setup ----

    def setup(self) -> None:
        random.shuffle(self.players)
        self.deck = create_deck()

        # Identity assignment
        if self.game_mode == "identity":
            self._assign_identities()

        for p in self.players:
            p.skill = random_skill()
            p.hand = self._draw(4)
            if self.game_mode == "identity" and p.identity == Identity.LORD:
                p.hp = 5
                p.max_hp = 5
            else:
                p.hp = 4
                p.max_hp = 4
            p.alive = True

        print(f"\n{Colors.bold('  [SGS] 三国杀')}")
        mode_label = "身份模式" if self.game_mode == "identity" else "混战模式"
        print(f"  {Colors.dim(f'模式: {mode_label}')}")
        for p in self.players:
            sk = SKILL_INFO[p.skill]
            if self.game_mode == "identity" and p.identity:
                id_str = IDENTITY_NAMES[p.identity]
                if p.identity == Identity.LORD:
                    id_str += " (公开)"
                else:
                    id_str = "???"
            else:
                id_str = ""
            extra = f" [{id_str}]" if id_str else ""
            print(f"  {p.name}{extra}: {sk['name']}({sk['desc'][:30]}...) 手牌={len(p.hand)}张")

        if self.logger:
            log_players = []
            for p in self.players:
                entry = {
                    "name": p.name, "model": p.model.model_name,
                    "skill": p.skill.value, "hp": p.hp,
                }
                if self.game_mode == "identity":
                    entry["identity"] = p.identity.value
                    entry["identity_revealed"] = p.identity_revealed
                log_players.append(entry)
            self.logger.log_event("game_start", {
                "players": log_players,
                "game_mode": self.game_mode,
                "initial_deck": self._deck_payload(),
            })
        self._log_state("setup_complete")

    def _assign_identities(self) -> None:
        """Assign identities based on player count."""
        n = len(self.players)
        if n not in IDENTITY_DISTRIBUTION:
            raise ValueError(
                f"身份模式需要 {sorted(IDENTITY_DISTRIBUTION.keys())} 名玩家，当前为 {n} 名。"
            )
        ids = list(IDENTITY_DISTRIBUTION[n])
        random.shuffle(ids)
        for player, identity in zip(self.players, ids):
            player.identity = identity
            player.identity_revealed = (identity == Identity.LORD)

    # ---- Win condition check ----

    def _check_identity_win(self) -> Optional[dict]:
        """Check identity-mode win conditions. Returns {winner: str, winners: [str]} or None."""
        alive = [p for p in self.players if p.is_alive]

        lord = next((p for p in self.players if p.identity == Identity.LORD), None)
        if lord is None:
            return None

        rebels_alive = [p for p in alive if p.identity == Identity.REBEL]
        spy_alive = [p for p in alive if p.identity == Identity.SPY]
        loyalists_alive = [p for p in alive if p.identity == Identity.LOYALIST]

        # Rebel victory: lord is dead
        if not lord.is_alive:
            if rebels_alive:
                return {"winner": "反贼", "winners": [p.name for p in rebels_alive]}
            if spy_alive:
                return {"winner": "内奸", "winners": [p.name for p in spy_alive]}
            return {"winner": "none", "winners": []}

        # Lord + Loyalist victory: all rebels and spy eliminated
        if not rebels_alive and not spy_alive:
            winners = [p.name for p in alive
                       if p.identity in (Identity.LORD, Identity.LOYALIST)]
            return {"winner": "主公/忠臣", "winners": winners}

        # Spy victory: spy is the only player alive
        if len(alive) == 1 and spy_alive:
            return {"winner": "内奸", "winners": [spy_alive[0].name]}

        return None

    # ---- Step (one turn) ----

    def step(self) -> dict:
        alive = [p for p in self.players if p.is_alive]

        # Check win conditions based on game mode
        if self.game_mode == "identity":
            result = self._check_identity_win()
            if result:
                self.finished = True
                self.winner = result["winner"]
                self._identity_winners = result["winners"]
                return result

        if len(alive) <= 1:
            self.finished = True
            self.winner = alive[0].name if alive else "none"
            return {"winner": self.winner}

        # Find next player
        while not self.players[self.turn_idx % len(self.players)].is_alive:
            self.turn_idx += 1
        player = self.players[self.turn_idx % len(self.players)]
        self.turn_idx += 1

        print(f"\n{Colors.bold(f'═ {player.name} 的回合 ═')}")

        # Reset turn state
        player.sha_used = False

        # ---- Draw Phase ----
        drawn = self._draw(2)
        player.hand.extend(drawn)
        draw_str = "、".join(str(c) for c in drawn)
        print(f"  摸牌：{draw_str}")
        self._log(f"{player.name} draws 2 cards")
        self._log_action(
            "draw",
            source="deck",
            target=player.name,
            cards=drawn,
            visual="targeted",
            zone_from="deck",
            zone_to="hand",
        )

        # ---- Play Phase ----
        self._play_phase(player)

        # ---- Discard Phase ----
        if player.is_alive and len(player.hand) > player.hp:
            excess = len(player.hand) - player.hp
            print(f"  {Colors.dim(f'手牌({len(player.hand)}) > 体力({player.hp})，需弃{excess}张')}")
            self._discard_phase(player, excess)

        # ---- End Phase ----
        if player.is_alive and player.skill == SkillID.EMPTY_DRAW and not player.hand:
            extra = self._draw(1)
            player.hand.extend(extra)
            print(f"  {Colors.dim('空城技能触发：摸1张牌')}")
            self._log(f"{player.name} uses 空城, draws 1")
            self._log_action(
                "skill_draw",
                source="deck",
                target=player.name,
                cards=extra,
                visual="targeted",
                zone_from="deck",
                zone_to="hand",
                extra={"skill": "empty_draw"},
            )

        return {"turn": player.name}

    # ---- Play Phase (option-based) ----

    def _play_phase(self, player):
        while player.is_alive:
            # Build alive player info for option generation
            alive_info = [
                {"name": p.name, "hp": p.hp, "card_count": p.card_count}
                for p in self.players if p.is_alive
            ]

            # Generate options
            options = generate_play_options(
                player.hand, player.skill, player.sha_used,
                player.hp, player.max_hp, alive_info, player.name,
            )
            options_text = format_options_for_prompt(options)

            # Build situation hint
            hint = self._build_situation_hint(player)

            # Build prompt
            state = format_players_state(self.players, self.game_mode)
            identity_label = ""
            if self.game_mode == "identity" and player.identity:
                identity_label = IDENTITY_NAMES[player.identity]
                if player.identity == Identity.LORD:
                    identity_label += " (公开)"
                else:
                    identity_label += " (隐藏)"
            prompt = play_turn_prompt(
                player.name, player.hp, player.max_hp,
                hand_summary(player.hand), hand_list_str(player.hand),
                SKILL_INFO[player.skill]["name"], SKILL_INFO[player.skill]["desc"],
                player.sha_used, state, options_text, hint,
                history=self.history[-4:],
                identity_label=identity_label,
            )

            # Query with retry (max 3 attempts, handles model errors + invalid output)
            MAX_RETRIES = 3
            choice_idx = None
            choice_error = ""
            system_prompt = IDENTITY_SYSTEM if self.game_mode == "identity" else PLAY_SYSTEM
            base_prompt = prompt  # keep original for error retries

            for attempt in range(MAX_RETRIES):
                print(f"\n  {Colors.dim(f'[{player.name}] 选择行动... (attempt {attempt+1}/{MAX_RETRIES})')}")
                _, raw_response, parsed = self._query(player, "play", prompt, system=system_prompt, temp=0.55)

                # ── Model error (connection timeout, etc.) → retry ──
                if raw_response.startswith("[ERROR:"):
                    choice_error = f"模型调用失败: {raw_response}"
                    print(f"  {player.name}: {Colors.color(f'MODEL ERROR: {raw_response[:80]}', Colors.RED)}")
                    if attempt < MAX_RETRIES - 1:
                        prompt = base_prompt + f"\n\n（前次调用失败，请重新选择。）"
                        continue
                    break

                reason = parsed.get("reason", "")
                if reason:
                    self._print_dim(f"  [{player.name}] REASON: {truncate(reason, 100)}")

                choice_str = parsed.get("choice", "").strip()
                self._print_dim(f"  [{player.name}] CHOICE: {choice_str if choice_str else '(empty)'}")

                if not choice_str:
                    choice_error = "未输出 CHOICE 行，请写 CHOICE: 数字"
                    print(f"  {player.name}: {Colors.color('MISSING CHOICE', Colors.RED)}")
                    if attempt < MAX_RETRIES - 1:
                        prompt = base_prompt + f"\n\n纠错：{choice_error}\n请重新选一个有效的选项编号。"
                    continue

                choice_idx, choice_error = self._validate_choice(
                    choice_str, options, allow_zero=True)
                if choice_error is None:
                    break  # valid choice

                print(f"  {player.name}: {Colors.color(f'INVALID: {choice_error}', Colors.RED)}")
                if attempt < MAX_RETRIES - 1:
                    prompt = base_prompt + f"\n\n纠错：{choice_error}\n请重新选一个有效的选项编号。"
                    continue

            # Execute
            if choice_error or choice_idx is None:
                print(f"  {player.name}: {Colors.color(f'{MAX_RETRIES} failures, forced END.', Colors.YELLOW)}")
                break

            if choice_idx == 0:
                # END turn
                print(f"  {player.name}: 结束回合")
                break

            # Execute chosen option
            opt = self._option_by_index(options, choice_idx)
            if opt is None:
                print(f"  {player.name}: 选项 {choice_idx} 未找到，结束回合")
                break
            self._execute_play_option(player, opt)

            # Check if player died during own turn
            if not player.is_alive:
                break

            # Check win conditions
            if self.game_mode == "identity":
                result = self._check_identity_win()
                if result:
                    self.finished = True
                    self.winner = result["winner"]
                    self._identity_winners = result["winners"]
                    break
            alive_check = [p for p in self.players if p.is_alive]
            if len(alive_check) <= 1:
                self.finished = True
                self.winner = alive_check[0].name if alive_check else "none"
                break

    def _execute_play_option(self, player, opt):
        """Execute a chosen play option dict."""
        action = opt["action_type"]

        if action == "sha":
            card = card_at(player.hand, opt["card_index"])
            if card is None:
                return
            target = self._find_player(opt["target_name"])
            if target:
                self._use_sha(player, card, target)

        elif action == "tao":
            card = card_at(player.hand, opt["card_index"])
            if card is None:
                return
            self._use_tao(player, card)

        elif action == "spell":
            card = card_at(player.hand, opt["card_index"])
            if card is None:
                return
            target = self._find_player(opt.get("target_name")) if opt.get("target_name") else None
            self._execute_card(player, card, target)

        elif action == "skill":
            self._handle_skill(player, {"action": "SKILL"})

    # ---- Choice validation ----

    def _validate_choice(self, choice_str: str, options: list,
                         allow_zero: bool = True) -> tuple:
        """Validate a CHOICE response. Returns (index, error_message).

        A valid choice returns (int_index, None).
        An invalid choice returns (None, error_description).
        """
        try:
            idx = int(choice_str)
        except ValueError:
            return (None, f"'{choice_str}' 不是有效数字，请输入选项编号如 0, 1, 2...")

        min_val = 0 if allow_zero else 1
        max_val = options[-1]["index"] if options else 0

        if idx < min_val or idx > max_val:
            return (None, f"选项 {idx} 超出范围 ({min_val}-{max_val})")

        return (idx, None)

    # ---- Card execution ----

    def _execute_card(self, player, card, target):
        """Execute a card play. Returns True if played, False if invalid."""
        ct = card.card_type

        if ct == CardType.SHA:
            return self._use_sha(player, card, target)
        elif ct == CardType.TAO:
            return self._use_tao(player, card)
        elif ct == CardType.WUZHONG:
            return self._use_spell(player, card, None, "无中生有")
        elif ct == CardType.NANMAN:
            return self._use_nanman(player, card)
        elif ct == CardType.WANJIAN:
            return self._use_wanjian(player, card)
        elif ct == CardType.TAOYUAN:
            return self._use_taoyuan(player, card)
        elif ct in (CardType.GUOHE, CardType.SHUNSHOU):
            return self._use_target_spell(player, card, ct, target)
        else:
            print(f"  {Colors.color(f'不能主动使用{ct.value}', Colors.RED)}")
            return False

    # ---- 杀 ----

    def _use_sha(self, player, card, target):
        if not target:
            print(f"  {Colors.color('出杀需要指定目标', Colors.RED)}")
            return False
        if target == player:
            print(f"  {Colors.color('不能对自己出杀', Colors.RED)}")
            return False

        has_unlim = (player.skill == SkillID.UNLIMITED_SHA)
        is_swap = (card.card_type == CardType.SHAN and player.skill == SkillID.SWAP)

        if card.card_type != CardType.SHA and not is_swap:
            print(f"  {Colors.color('只能使用【杀】', Colors.RED)}")
            return False

        if player.sha_used and not has_unlim and not is_swap:
            print(f"  {Colors.color('本回合已出过杀', Colors.RED)}")
            return False

        # Check target immunity (空城·守)
        if target.skill == SkillID.EMPTY_IMMUNE and not target.hand:
            print(f"  {Colors.color(f'{target.name}无手牌，不能成为目标', Colors.RED)}")
            return False

        self._consume_card(player, card)
        self._log_action(
            "use_sha",
            source=player.name,
            target=target.name,
            cards=[card],
            visual="targeted",
            zone_from="hand",
            zone_to="table",
        )
        player.sha_used = True
        print(f"  {player.name} 对 {target.name} 使用【杀】")

        # Ask target for 闪
        dodged = self._ask_response(target, CardType.SHAN, f"{player.name} 对你使用了【杀】，请出【闪】响应")
        if dodged:
            print(f"  {target.name} 出【闪】抵消")
            self._log(f"{player.name} uses 杀 on {target.name}, {target.name} dodges")
        else:
            self._deal_damage(target, 1, player)
            self._log(f"{player.name} uses 杀 on {target.name}, deals 1 damage")

        return True

    # ---- 桃 ----

    def _use_tao(self, player, card):
        if player.hp >= player.max_hp:
            print(f"  {Colors.color('体力已满，不能吃桃', Colors.RED)}")
            return False
        self._consume_card(player, card)
        player.hp = min(player.hp + 1, player.max_hp)
        print(f"  {player.name} 吃桃恢复1点体力 ({player.hp}/{player.max_hp})")
        self._log(f"{player.name} uses 桃, heals to {player.hp}")
        self._log_action(
            "use_tao",
            source=player.name,
            target=player.name,
            cards=[card],
            visual="self",
            zone_from="hand",
            zone_to="table",
        )
        return True

    # ---- Spells ----

    def _use_spell(self, player, card, target, spell_name):
        """Generic spell: draw cards etc."""
        self._consume_card(player, card)
        if card.card_type == CardType.WUZHONG:
            drawn = self._draw(2)
            player.hand.extend(drawn)
            print(f"  {player.name} 使用【无中生有】，摸2张牌")
            self._log(f"{player.name} uses 无中生有")
            self._log_action(
                "use_wuzhong",
                source=player.name,
                target=player.name,
                cards=[card, *drawn],
                visual="self",
                zone_from="hand",
                zone_to="table",
            )
        return True

    def _use_nanman(self, player, card):
        """南蛮入侵: all others must play 杀 or take 1 damage."""
        self._consume_card(player, card)
        print(f"  {player.name} 使用【南蛮入侵】！所有人必须出【杀】")
        self._log(f"{player.name} uses 南蛮入侵")
        self._log_action(
            "use_nanman",
            source=player.name,
            cards=[card],
            visual="global",
            zone_from="hand",
            zone_to="table",
        )

        for target in self.players:
            if target == player or not target.is_alive:
                continue
            responded = self._ask_response(target, CardType.SHA,
                                           f"{player.name} 使用了【南蛮入侵】，请出【杀】响应")
            if not responded:
                self._deal_damage(target, 1, player)
        return True

    def _use_wanjian(self, player, card):
        """万箭齐发: all others must play 闪 or take 1 damage."""
        self._consume_card(player, card)
        print(f"  {player.name} 使用【万箭齐发】！所有人必须出【闪】")
        self._log(f"{player.name} uses 万箭齐发")
        self._log_action(
            "use_wanjian",
            source=player.name,
            cards=[card],
            visual="global",
            zone_from="hand",
            zone_to="table",
        )

        for target in self.players:
            if target == player or not target.is_alive:
                continue
            responded = self._ask_response(target, CardType.SHAN,
                                           f"{player.name} 使用了【万箭齐发】，请出【闪】响应")
            if not responded:
                self._deal_damage(target, 1, player)
        return True

    def _use_taoyuan(self, player, card):
        """桃园结义: all players heal 1."""
        self._consume_card(player, card)
        print(f"  {player.name} 使用【桃园结义】！所有人恢复1点体力")
        self._log(f"{player.name} uses 桃园结义")
        for p in self.players:
            if p.is_alive:
                p.hp = min(p.hp + 1, p.max_hp)
        self._log_action(
            "use_taoyuan",
            source=player.name,
            cards=[card],
            visual="global",
            zone_from="hand",
            zone_to="table",
        )
        return True

    def _use_target_spell(self, player, card, ct, target):
        """Targeted spell: 过河拆桥 or 顺手牵羊.
        Now asks AI which card to target instead of random."""
        if not target:
            print(f"  {Colors.color('需要指定目标', Colors.RED)}")
            return False
        if target == player:
            print(f"  {Colors.color('不能对自己使用', Colors.RED)}")
            return False
        if not target.hand:
            print(f"  {Colors.color(f'{target.name}没有手牌', Colors.RED)}")
            return False

        self._consume_card(player, card)
        self._log_action(
            "use_target_spell",
            source=player.name,
            target=target.name,
            cards=[card],
            visual="targeted",
            zone_from="hand",
            zone_to="table",
            extra={"spell_type": ct.value},
        )

        spell_name = "过河拆桥" if ct == CardType.GUOHE else "顺手牵羊"

        # Ask AI which card to target from target's hand
        chosen = self._ask_card_selection(
            player, target, spell_name,
            f"你对{target.name}使用【{spell_name}】，请选择目标的一张手牌。",
        )

        if ct == CardType.GUOHE:
            self._consume_card(target, chosen)
            print(f"  {player.name} 对 {target.name} 使用【过河拆桥】，弃掉 {chosen.name}")
            self._log(f"{player.name} uses 过河拆桥 on {target.name}, discards {chosen.name}")
            self._log_action(
                "discard_from_target",
                source=target.name,
                target="discard",
                cards=[chosen],
                visual="discard",
                zone_from="hand",
                zone_to="discard",
                extra={"actor": player.name, "spell_type": ct.value},
            )
        else:
            target.remove_card(chosen)
            player.hand.append(chosen)
            print(f"  {player.name} 对 {target.name} 使用【顺手牵羊】，获得 {chosen.name}")
            self._log(f"{player.name} uses 顺手牵羊 on {target.name}, steals {chosen.name}")
            self._log_action(
                "steal_from_target",
                source=target.name,
                target=player.name,
                cards=[chosen],
                visual="targeted",
                zone_from="hand",
                zone_to="hand",
                extra={"actor": player.name, "spell_type": ct.value},
            )

        return True

    # ---- Response System (option-based) ----

    def _ask_response(self, player, required_type, prompt_text):
        """Ask a player to respond. Returns True if they played the required card.
        Uses option-based selection with retry."""
        # Check swap skill
        options = generate_response_options(player.hand, required_type, player.skill)
        options_text = format_options_for_prompt(options)

        state = format_players_state(self.players, self.game_mode)
        prompt = response_option_prompt(
            player.name, player.hp,
            hand_summary(player.hand), hand_list_str(player.hand),
            SKILL_INFO[player.skill]["name"],
            prompt_text, state, options_text,
        )

        print(f"\n  {Colors.dim(f'[{player.name}] 响应...')}")
        system_prompt = IDENTITY_SYSTEM if self.game_mode == "identity" else PLAY_SYSTEM
        base_prompt = prompt

        # Query with retry (max 3 attempts, handles model errors + invalid output)
        for attempt in range(3):
            _, raw_response, parsed = self._query(player, "respond", prompt, system=system_prompt, temp=0.4)

            # ── Model error → retry ──
            if raw_response.startswith("[ERROR:"):
                print(f"  {player.name}: {Colors.color(f'MODEL ERROR: {raw_response[:60]}', Colors.RED)}")
                if attempt < 2:
                    prompt = base_prompt + "\n\n（前次调用失败，请重新选择。）"
                    continue
                print(f"  {player.name}: 不响应 (model error)")
                return False

            reason = parsed.get("reason", "")
            if reason:
                self._print_dim(f"  [{player.name}] {truncate(reason, 60)}")

            choice_str = parsed.get("choice", "").strip()

            if not choice_str:
                if attempt < 2:
                    prompt = base_prompt + "\n\n纠错：请输出 CHOICE: 数字"
                    continue
                print(f"  {player.name}: 不响应")
                return False

            choice_idx, error = self._validate_choice(choice_str, options, allow_zero=True)

            if error is not None:
                if attempt < 2:
                    prompt = base_prompt + f"\n\n纠错：{error}\n请重新选择。"
                    continue
                print(f"  {player.name}: 不响应")
                return False

            if choice_idx == 0:
                # PASS
                print(f"  {player.name}: 不响应")
                return False

            # Execute response
            opt = self._option_by_index(options, choice_idx)
            if opt is None:
                return False
            card = card_at(player.hand, opt["card_index"])
            if card is None:
                return False

            self._consume_card(player, card)
            self._log_action(
                "response_card",
                source=player.name,
                cards=[card],
                visual="discard",
                zone_from="hand",
                zone_to="table",
                extra={"required_type": required_type.value},
            )
            print(f"  {player.name}: 使用 {card.name} 响应")
            return True

        print(f"  {player.name}: 不响应")
        return False

    # ---- Damage ----

    def _deal_damage(self, target, amount, source):
        target.hp -= amount
        self._log_action(
            "damage",
            source=source.name if source else "",
            target=target.name,
            visual="targeted" if source else "self",
            extra={"amount": amount},
        )
        print(f"  {Colors.color(f'{target.name} 受到{amount}点伤害 ({target.hp}/{target.max_hp})', Colors.RED)}")

        # Wound skill: 刚烈
        if target.skill == SkillID.WOUND_DRAW:
            drawn = self._draw(2)
            target.hand.extend(drawn)
            print(f"  {Colors.dim(f'{target.name} 刚烈触发：摸2张牌')}")
            self._log_action(
                "wound_draw",
                source="deck",
                target=target.name,
                cards=drawn,
                visual="targeted",
                zone_from="deck",
                zone_to="hand",
                extra={"skill": "wound_draw"},
            )

        # Wound skill: 反馈 — AI selects which card to steal
        if target.skill == SkillID.WOUND_STEAL and source and source.is_alive and source.hand:
            stolen = self._ask_card_selection(
                target, source, "反馈",
                f"你受到{source.name}的伤害，触发【反馈】技能。请选择获得{source.name}的哪张手牌。",
            )
            source.hand.remove(stolen)
            target.hand.append(stolen)
            print(f"  {Colors.dim(f'{target.name} 反馈触发：获得{source.name}的{stolen.name}')}")
            self._log_action(
                "wound_steal",
                source=source.name,
                target=target.name,
                cards=[stolen],
                visual="targeted",
                zone_from="hand",
                zone_to="hand",
                extra={"skill": "wound_steal"},
            )

        # Death check
        if target.hp <= 0:
            self._check_death(target, source)

    def _check_death(self, player, source):
        """Check if player can be saved with 桃. On death, reveal identity."""
        while player.hp <= 0:
            if player.has_card(CardType.TAO):
                t = player.find_card(CardType.TAO)
                self._consume_card(player, t)
                player.hp = 1
                print(f"  {Colors.color(f'{player.name} 使用【桃】自救，恢复至1体力', Colors.GREEN)}")
                self._log(f"{player.name} uses 桃 to survive")
                self._log_action(
                    "survive_with_tao",
                    source=player.name,
                    target=player.name,
                    cards=[t],
                    visual="self",
                    zone_from="hand",
                    zone_to="table",
                )
            else:
                player.alive = False
                # Reveal identity on death
                if self.game_mode == "identity" and player.identity and not player.identity_revealed:
                    player.identity_revealed = True
                    id_name = IDENTITY_NAMES[player.identity]
                    print(f"  {Colors.dim(f'[{player.name}] 身份揭示: {id_name}')}")
                print(f"  {Colors.color(f'{player.name} 阵亡！', Colors.RED)}")
                self._log(f"{player.name} dies")
                if source and source.is_alive:
                    source.hand.extend(player.hand)
                    self._log_action(
                        "loot_dead_player",
                        source=player.name,
                        target=source.name,
                        cards=list(player.hand),
                        visual="targeted",
                        zone_from="hand",
                        zone_to="hand",
                    )
                    player.hand.clear()
                self._log_action(
                    "death",
                    source=player.name,
                    visual="discard",
                )
                break

    # ---- Discard (AI-decided) ----

    def _discard_phase(self, player, excess):
        """Let AI choose which cards to discard, one at a time."""
        for _ in range(excess):
            if not player.hand:
                break

            options = generate_card_choice_options(player.hand, "弃")
            if not options:
                break

            options_text = format_options_for_prompt(options)
            prompt = discard_prompt(
                player.name, player.hp, player.max_hp,
                len(player.hand),
                hand_summary(player.hand), hand_list_str(player.hand),
                excess, options_text,
            )

            # Query AI
            print(f"  {Colors.dim(f'[{player.name}] 选择弃牌...')}")
            system_prompt = IDENTITY_SYSTEM if self.game_mode == "identity" else PLAY_SYSTEM
            base_prompt = prompt

            for attempt in range(3):
                _, raw_response, parsed = self._query(player, "discard", prompt, system=system_prompt, temp=0.5)

                # ── Model error → retry ──
                if raw_response.startswith("[ERROR:"):
                    print(f"  {player.name}: {Colors.color(f'MODEL ERROR: {raw_response[:60]}', Colors.RED)}")
                    if attempt < 2:
                        prompt = base_prompt + "\n\n（前次调用失败，请重新选择。）"
                        continue
                    # Fallback: discard random
                    chosen = random.choice(player.hand)
                    self._consume_card(player, chosen)
                    print(f"  {Colors.dim(f'弃牌(随机-兜底): {chosen.name}')}")
                    self._log_action("discard_random", source=player.name, cards=[chosen],
                                     visual="discard", zone_from="hand", zone_to="discard")
                    break

                choice_str = parsed.get("choice", "").strip()

                if not choice_str:
                    if attempt < 2:
                        prompt = base_prompt + "\n\n纠错：请输出 CHOICE: 数字（选择要弃的牌）"
                        continue
                    # Fallback: discard random
                    chosen = random.choice(player.hand)
                    self._consume_card(player, chosen)
                    print(f"  {Colors.dim(f'弃牌(随机): {chosen.name}')}")
                    self._log_action("discard_random", source=player.name, cards=[chosen],
                                     visual="discard", zone_from="hand", zone_to="discard")
                    break

                choice_idx, error = self._validate_choice(choice_str, options, allow_zero=False)

                if error is not None:
                    if attempt < 2:
                        prompt = base_prompt + f"\n\n纠错：{error}\n请重新选择。"
                        continue
                    chosen = random.choice(player.hand)
                    self._consume_card(player, chosen)
                    print(f"  {Colors.dim(f'弃牌(随机): {chosen.name}')}")
                    self._log_action("discard_random", source=player.name, cards=[chosen],
                                     visual="discard", zone_from="hand", zone_to="discard")
                    break

                # Valid choice
                opt = self._option_by_index(options, choice_idx)
                if opt:
                    card = card_at(player.hand, opt["card_index"])
                    if card:
                        self._consume_card(player, card)
                        print(f"  {Colors.dim(f'弃牌: {card.name}')}")
                        self._log_action(
                            "discard",
                            source=player.name,
                            cards=[card],
                            visual="discard",
                            zone_from="hand",
                            zone_to="discard",
                        )
                break
            else:
                # All retries exhausted
                if player.hand:
                    chosen = player.hand[-1]
                    self._consume_card(player, chosen)
                    print(f"  {Colors.dim(f'弃牌(兜底): {chosen.name}')}")
                    self._log_action(
                        "discard_fallback",
                        source=player.name,
                        cards=[chosen],
                        visual="discard",
                        zone_from="hand",
                        zone_to="discard",
                    )

    # ---- AI card selection helper ----

    def _ask_card_selection(self, chooser, target, action_label, prompt_hint):
        """Ask AI to choose a card from target's hand.
        Used for: 过河拆桥 discard, 顺手牵羊 steal, 反馈 steal.

        Returns the chosen Card (falls back to random on failure).
        """
        if not target.hand:
            return None

        if len(target.hand) == 1:
            return target.hand[0]

        options = generate_card_choice_options(target.hand, "拿" if "获得" in prompt_hint else "拆")
        options_text = format_options_for_prompt(options)

        if "反馈" in action_label:
            prompt = steal_prompt(
                chooser.name, target.name,
                hand_list_str(target.hand), options_text,
            )
        else:
            prompt = target_card_prompt(
                chooser.name, target.name, action_label,
                hand_list_str(target.hand), options_text,
            )

        print(f"  {Colors.dim(f'[{chooser.name}] 选择目标牌...')}")
        system_prompt = IDENTITY_SYSTEM if self.game_mode == "identity" else PLAY_SYSTEM
        base_prompt = prompt

        for attempt in range(3):
            _, raw_response, parsed = self._query(chooser, "select_card", prompt, system=system_prompt, temp=0.5)

            # ── Model error → retry ──
            if raw_response.startswith("[ERROR:"):
                print(f"  {chooser.name}: {Colors.color(f'MODEL ERROR: {raw_response[:60]}', Colors.RED)}")
                if attempt < 2:
                    prompt = base_prompt + "\n\n（前次调用失败，请重新选择。）"
                    continue
                return random.choice(target.hand)

            choice_str = parsed.get("choice", "").strip()

            if not choice_str:
                if attempt < 2:
                    prompt = base_prompt + "\n\n纠错：请输出 CHOICE: 数字（选择要目标的手牌）"
                    continue
                return random.choice(target.hand)

            choice_idx, error = self._validate_choice(choice_str, options, allow_zero=False)

            if error is not None:
                if attempt < 2:
                    prompt = base_prompt + f"\n\n纠错：{error}\n请重新选择。"
                    continue
                return random.choice(target.hand)

            opt = self._option_by_index(options, choice_idx)
            if opt:
                card = card_at(target.hand, opt["card_index"])
                if card:
                    return card
            return random.choice(target.hand)

        return random.choice(target.hand)

    # ---- Skill ----

    def _handle_skill(self, player, parsed):
        if player.skill == SkillID.BLOOD_DRAW and player.hp > 0:
            player.hp -= 1
            drawn = self._draw(2)
            player.hand.extend(drawn)
            print(f"  {player.name} 苦肉：扣1血，摸2牌")
            self._log(f"{player.name} uses 苦肉")
            self._log_action(
                "use_skill",
                source=player.name,
                target=player.name,
                cards=drawn,
                visual="self",
                zone_from="deck",
                zone_to="hand",
                extra={"skill": "blood_draw"},
            )
            if player.hp <= 0:
                self._check_death(player, None)

    # ---- Situation hint ----

    def _build_situation_hint(self, player) -> str:
        """Build strategic hints about the current game state.
        Provides concrete, actionable advice tied to the current board."""
        parts = []

        # ── Identity-specific priority ──
        if self.game_mode == "identity" and player.identity:
            pid = player.identity
            if pid == Identity.LORD:
                parts.append("你是主公——消灭反贼和内奸。谨慎选择目标，避免误伤忠臣")
            elif pid == Identity.LOYALIST:
                lord = next((p for p in self.players if p.identity == Identity.LORD), None)
                lord_name = lord.name if lord else "主公"
                lord_hp = lord.hp if lord else 5
                if lord_hp <= 2:
                    parts.append(f"[急] {lord_name}(主公)仅剩{lord_hp}HP，全力保护！")
                else:
                    parts.append(f"你是忠臣——保护{lord_name}，积极进攻反贼和内奸")
            elif pid == Identity.REBEL:
                lord = next((p for p in self.players if p.identity == Identity.LORD), None)
                lord_name = lord.name if lord else "主公"
                lord_hp = lord.hp if lord else 5
                if lord_hp <= 2:
                    parts.append(f"[急] {lord_name}(主公)仅剩{lord_hp}HP！全力击杀主公即可获胜！")
                else:
                    parts.append(f"你是反贼——目标是击杀{lord_name}(主公)。集火主公优先！")
            elif pid == Identity.SPY:
                # Count remaining rebels vs loyalists vs lord
                rebels_alive = sum(1 for p in self.players
                                   if p.is_alive and p.identity == Identity.REBEL)
                loyalists_alive = sum(1 for p in self.players
                                      if p.is_alive and p.identity == Identity.LOYALIST)
                if rebels_alive > 0:
                    parts.append(f"你是内奸——先装忠臣消灭反贼(还剩{rebels_alive}个)")
                elif loyalists_alive > 0:
                    parts.append(f"你是内奸——反贼已灭，找机会除掉忠臣(还剩{loyalists_alive}个)")
                else:
                    parts.append("你是内奸——最后时刻！与主公1v1决胜负")

        # ── Defense assessment ──
        has_shan = any(c.card_type == CardType.SHAN for c in player.hand)
        has_swap_defense = (player.skill == SkillID.SWAP and
                            any(c.card_type == CardType.SHA for c in player.hand))
        if not has_shan and not has_swap_defense:
            parts.append("[!] 你手中没有【闪】——建议不要出杀，优先留牌防守或使用锦囊")
        elif has_shan:
            shan_count = sum(1 for c in player.hand if c.card_type == CardType.SHAN)
            parts.append(f"持有{shan_count}张【闪】，防御充足可以放心进攻")

        # ── Kill targets ──
        threats = []
        for p in self.players:
            if p is not player and p.is_alive and player.is_enemy(p):
                if p.hp == 1:
                    threats.append(f"[斩] {p.name} HP=1，一张杀即可收割！")
                elif p.hp == 2:
                    threats.append(f"[压] {p.name} HP=2，优先压制")
        if threats:
            parts.extend(threats[:3])  # Show top 3, avoid information overload

        # ── Card advantage targets ──
        big_hand = [p for p in self.players
                    if p is not player and p.is_alive and player.is_enemy(p) and p.card_count >= 4]
        if big_hand:
            names = "、".join(p.name for p in big_hand[:2])
            parts.append(f"{names} 手牌较多——用【过河拆桥】/【顺手牵羊】削弱之")

        # ── Empty city ──
        if player.skill == SkillID.EMPTY_IMMUNE and not player.hand:
            parts.append("[防] 空城·守生效：你现在免疫【杀】！")

        # ── Low HP warning ──
        if player.hp == 1:
            has_tao = any(c.card_type == CardType.TAO for c in player.hand)
            if has_tao:
                parts.append("[急] HP=1！手中有【桃】，建议立刻吃桃或留着防濒死")
            else:
                parts.append("[危] HP=1且无桃！防御优先，切勿冒险")

        return "；".join(parts) if parts else ""


    # ---- Helpers ----

    def _option_by_index(self, options: list, idx: int) -> Optional[dict]:
        """Find an option dict by its 'index' field (not list position)."""
        for opt in options:
            if opt["index"] == idx:
                return opt
        return None

    def _find_player(self, name: str) -> Optional[SanguoshaPlayer]:
        """Find a player by name (case-insensitive)."""
        if not name:
            return None
        for p in self.players:
            if p.name.lower() == name.lower():
                return p
        # Partial match
        for p in self.players:
            if name.lower() in p.name.lower():
                return p
        return None

    def _log(self, msg):
        self.history.append(msg)

    def _print_dim(self, text):
        try:
            print(f"  {Colors.dim(text)}")
        except UnicodeEncodeError:
            safe = text.encode("gbk", errors="replace").decode("gbk")
            print(f"  {Colors.dim(safe)}")

    def check_win(self):
        return self.winner if self.finished else None

    def run(self, max_rounds=200, verbose=True):
        self.setup()
        for _ in range(max_rounds):
            self.round += 1
            result = self.step()
            self.log.append(result)
            if self.finished:
                if verbose:
                    self._print_result()
                if self.logger:
                    extra = {}
                    if self.game_mode == "identity":
                        extra["game_mode"] = "identity"
                        extra["winner_faction"] = self.winner
                        extra["winners"] = getattr(self, "_identity_winners", [])
                        for p in self.players:
                            extra[f"identity_{p.name}"] = p.identity.value if p.identity else "none"
                    self.logger.write_summary(self.players, self.winner, self.round, self.history, extra=extra)
                return self.winner
        return None

    def _print_setup(self):
        pass

    def _print_result(self):
        print(f"\n{Colors.bold('=' * 40)}")
        if self.game_mode == "identity" and hasattr(self, "_identity_winners"):
            winners = self._identity_winners
            winner_label = self.winner
            print(Colors.bold(f"  胜利方: {winner_label}"))
            if winners:
                print(Colors.bold(f"  胜利者: {', '.join(winners)}"))
            # Show all identities
            print(Colors.dim("  --- 身份揭晓 ---"))
            for p in self.players:
                id_str = IDENTITY_NAMES.get(p.identity, "无") if p.identity else "无"
                status = "存活" if p.is_alive else "阵亡"
                print(Colors.dim(f"  {p.name}: {id_str} [{status}]"))
        else:
            alive = [p for p in self.players if p.is_alive]
            if alive:
                print(Colors.bold(f"  Winner: {alive[0].name}"))
        print(Colors.bold('=' * 40))
