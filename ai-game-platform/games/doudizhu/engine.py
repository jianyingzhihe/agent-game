"""Dou Dizhu game engine — bidding, playing, scoring."""

import random
import time
from typing import List, Optional

from core.engine import GameEngine
from core.logger import GameLogger
from core.utils import Colors, parse_keyword_response, truncate

from .cards import (
    Card, RANK_DISPLAY, can_beat, combo_name, create_deck, deal,
    detect_combo, hand_str, sort_hand,
    encoded_hand_inventory_str, encoded_hand_str, short_hand_str,
    parse_rank_selection, rank_code_hint, validate_rank_selection,
    generate_play_options, format_options_for_prompt,
)
from .player import DoudizhuPlayer
from .prompts import bid_prompt, play_prompt, BID_SYSTEM, PLAY_SYSTEM


class DoudizhuEngine(GameEngine):
    """Dou Dizhu engine for 3 players."""

    def __init__(self, players, config=None, logger=None):
        if len(players) != 3:
            raise ValueError("Dou Dizhu requires exactly 3 players")
        super().__init__(players, config)
        self.logger = logger
        self.game_log: List[str] = []
        self.landlord_idx = -1
        self.play_history: List[str] = []
        self.round_num = 0
        self.bomb_count = 0
        self.played_high_cards: set = set()  # track played jokers, 2s, As

    # ---- Query helper ----

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
        # Display thinking if model did deep reasoning
        if thinking and len(thinking) > 50:
            self._print_dim(f"  [{player.name}] 思考 {len(thinking)} 字符: {truncate(thinking, 150)}")
        return thinking, response, parsed

    # ---- Setup ----

    def setup(self) -> None:
        print(f"\n{Colors.bold('  Dou Dizhu - 斗地主')}")
        print(f"  {', '.join(p.name for p in self.players)}\n")

        deck = create_deck()
        h1, h2, h3, landlord_cards = deal(deck)
        for i, h in enumerate([h1, h2, h3]):
            self.players[i].hand = sort_hand(h)

        for p in self.players:
            print(f"  {p.name}: {short_hand_str(p.hand)}")
        print(f"\n  Landlord cards (底牌): {short_hand_str(landlord_cards)}")

        self.landlord_idx = self._bidding(landlord_cards)

        landlord = self.players[self.landlord_idx]
        landlord.role = "Landlord (地主)"
        landlord.hand = sort_hand(landlord.hand + landlord_cards)
        for i, p in enumerate(self.players):
            if i != self.landlord_idx:
                p.role = "Farmer (农民)"

        print(f"\n  {Colors.bold(f'{landlord.name} is the Landlord!')}")
        print(f"  {landlord.name}: {short_hand_str(landlord.hand)}")
        for p in self.players:
            if p.role.startswith("Farmer"):
                print(f"  {p.name}: {short_hand_str(p.hand)}")

        if self.logger:
            self.logger.log_event("game_start", {
                "players": [{"name": p.name, "role": p.role, "hand": short_hand_str(p.hand)} for p in self.players],
                "landlord_cards": short_hand_str(landlord_cards),
                "landlord": landlord.name,
            })

    # ---- Bidding ----

    def _bidding(self, landlord_cards):
        print(f"\n  {Colors.bold('Bidding (叫地主):')}")
        bids = []
        start = random.randint(0, 2)
        for offset in range(3):
            idx = (start + offset) % 3
            player = self.players[idx]
            prompt = bid_prompt(player.name, short_hand_str(player.hand),
                                [f"{self.players[i].name}: {b}" for i, b in bids])
            print(f"\n  {Colors.dim(f'[{player.name}] bidding...')}")
            _, _, parsed = self._query(player, "bid", prompt, system=BID_SYSTEM, temp=0.6)
            bid_val = parsed.get("bid", "0").strip()
            reason = parsed.get("reason", "")
            try:
                bid_amount = int(bid_val)
            except ValueError:
                bid_amount = 0
            bids.append((idx, bid_amount))
            if reason:
                self._print_dim(f"  [{player.name}] {truncate(reason, 80)}")
            print(f"  {player.name}: {Colors.bold(str(bid_amount))}")
            if bid_amount >= 3:
                print(f"  {Colors.color(f'{player.name} bids to be Landlord!', Colors.YELLOW)}")
                return idx
        fallback = random.randint(0, 2)
        print(f"  {Colors.dim('Nobody bid, random landlord.')}")
        return fallback

    # ---- Step (one trick) ----

    def step(self) -> dict:
        self.round_num += 1
        print(f"\n  {Colors.bold(f'[Round {self.round_num}]')}")

        last_play = None
        last_player_idx = -1
        last_cards: List[Card] = []
        pass_count = 0
        trick_log: List[str] = []

        while True:
            for offset in range(3):
                idx = (self.landlord_idx + offset) % 3
                player = self.players[idx]
                if not player.hand:
                    continue

                must_beat = (last_player_idx != -1 and last_play is not None
                             and not self._is_partner(idx, last_player_idx))

                # Trick reset: 2 consecutive passes → last player takes the trick
                if pass_count >= 2 and idx == last_player_idx:
                    last_play = None
                    last_player_idx = -1
                    pass_count = 0
                    trick_log = []

                # ---- Generate options ----
                options = generate_play_options(player.hand, last_play)
                options_text = format_options_for_prompt(options, len(player.hand))

                # ---- Build context strings ----
                teammate = ""
                landlord_name = ""
                for p in self.players:
                    if p.role.startswith("Landlord"):
                        landlord_name = p.name
                    if (player.role.startswith("Farmer") and
                            p.role.startswith("Farmer") and p.name != player.name):
                        teammate = p.name

                counts = []
                for p in self.players:
                    role_tag = "地主" if p.role.startswith("Landlord") else "农民"
                    counts.append(f"{p.name}({role_tag}):{len(p.hand)}张")
                player_counts = "  ".join(counts)

                last_play_desc = None
                if last_play and last_cards:
                    lp_name = self.players[last_player_idx].name
                    last_play_desc = f"{lp_name}: {short_hand_str(last_cards)} ({combo_name(last_play)})"

                situation_hint = self._build_situation_hint(player, last_play, must_beat)
                card_reading = self._build_card_reading(player)

                # ---- Model query with retry (max 2 attempts) ----
                choice_idx = None
                choice_error = ""

                for attempt in range(2):
                    prompt = play_prompt(
                        player.name, player.role,
                        short_hand_str(player.hand),
                        len(player.hand),
                        last_play_desc,
                        must_beat,
                        self.round_num,
                        {p.name: p.score for p in self.players},
                        options_text,
                        situation_hint=situation_hint,
                        teammate=teammate,
                        landlord=landlord_name,
                        player_counts=player_counts,
                        card_reading=card_reading,
                    )

                    if choice_error:
                        prompt += (
                            f"\n\n纠错：上次选择无效 — {choice_error}\n"
                            "请重新选一个有效的选项编号。"
                        )

                    label = f"{len(player.hand)} cards left" + (" (retry)" if attempt > 0 else "")
                    print(f"\n  {Colors.dim(f'[{player.name}] {player.role} - {label}...')}")
                    _, raw_response, parsed = self._query(player, "play", prompt, system=PLAY_SYSTEM, temp=0.7)

                    choice_str = parsed.get("choice", "").strip()
                    reason = parsed.get("reason", "")

                    if reason:
                        self._print_dim(f"  [{player.name}] REASON: {truncate(reason, 80)}")
                    self._print_dim(f"  [{player.name}] CHOICE: {choice_str if choice_str else '(empty)'}")

                    if not choice_str:
                        choice_error = "未输出 CHOICE 行，请写 CHOICE: 数字"
                        print(f"  {player.name}: {Colors.color('MISSING CHOICE', Colors.RED)}")
                        continue

                    choice_idx, choice_error = self._validate_choice(
                        choice_str, options, last_play is None)
                    if choice_error is None:
                        break  # valid choice

                    print(f"  {player.name}: {Colors.color(f'INVALID: {choice_error}', Colors.RED)}")

                # ---- Execute ----
                if choice_error:
                    # All retries failed — force fallback
                    if last_play is not None:
                        print(f"  {player.name}: {Colors.color('2 errors, forced PASS.', Colors.YELLOW)}")
                        trick_log.append(f"{player.name}: PASS (forced)")
                        pass_count += 1
                        player.record_pass()
                    else:
                        # Must lead: pick first (best) option
                        print(f"  {player.name}: {Colors.color('2 errors, forced best option.', Colors.YELLOW)}")
                        opt = options[0]
                        player, last_play, last_player_idx, last_cards, pass_count = \
                            self._apply_play(player, idx, opt, trick_log)
                        if not player.hand:
                            self._resolve_game(player)
                            return {"round": self.round_num, "winner": player.name}
                    continue

                if choice_idx == 0:
                    # PASS
                    print(f"  {player.name}: {Colors.color('PASS', Colors.YELLOW)}")
                    trick_log.append(f"{player.name}: PASS")
                    pass_count += 1
                    player.record_pass()
                    continue

                # Execute chosen play
                opt = options[choice_idx - 1]
                player, last_play, last_player_idx, last_cards, pass_count = \
                    self._apply_play(player, idx, opt, trick_log)

                if not player.hand:
                    self._resolve_game(player)
                    return {"round": self.round_num, "winner": player.name}

    def _apply_play(self, player, player_idx, opt, trick_log):
        """Apply a play option: remove cards, update state, print.
        Returns updated (player, last_play, last_player_idx, last_cards, pass_count)."""
        selected = opt["cards"]
        combo = opt["combo"]

        player.remove_cards(selected)
        player.record_play()

        if combo["type"] in ("bomb", "rocket"):
            self.bomb_count += 1

        # Track high cards for card reading
        for c in selected:
            if c.rank in (16, 17, 15):  # jokers and 2s
                self.played_high_cards.add(c.rank)
            elif c.rank == 14:  # A
                self.played_high_cards.add(c.rank)

        play_desc = f"{player.name}: {short_hand_str(selected)} ({combo_name(combo)})"
        trick_log.append(play_desc)
        self.play_history.append(play_desc)
        print(f"  {play_desc}  [{len(player.hand)} left]")

        return player, combo, player_idx, selected, 0

    # ---- Choice validation ----

    def _validate_choice(self, choice_str: str, options: list,
                         is_lead: bool) -> tuple:
        """Validate a CHOICE response. Returns (index, error_message).

        A valid choice returns (int_index, None).
        An invalid choice returns (None, error_description).
        """
        try:
            idx = int(choice_str)
        except ValueError:
            return (None, f"'{choice_str}' 不是有效数字，请输入选项编号如 0, 1, 2...")

        if idx < 0 or idx > len(options):
            return (None, f"选项 {idx} 超出范围 (0-{len(options)})")

        if idx == 0 and is_lead:
            return (None, "桌面为空时不能 PASS，必须选一个出牌选项")

        return (idx, None)

    # ---- Situation hint ----

    def _build_situation_hint(self, player, last_play, must_beat: bool) -> str:
        """Build a strategic situation hint."""
        parts = []

        # Opponent danger assessment
        opponents = [p for p in self.players
                     if p is not player
                     and not self._is_partner(self.players.index(player),
                                              self.players.index(p))]
        if opponents:
            min_opp = min(opponents, key=lambda p: len(p.hand))
            if len(min_opp.hand) <= 2:
                parts.append(f"🔴 对手{min_opp.name}只剩{len(min_opp.hand)}张！必须不惜代价阻断——有大牌出大牌，有炸弹出炸弹！")
            elif len(min_opp.hand) <= 4:
                parts.append(f"🟡 对手{min_opp.name}只剩{len(min_opp.hand)}张，危险临近。优先出能压制他的牌。")
            elif len(min_opp.hand) <= 8:
                parts.append(f"对手{min_opp.name}还有{len(min_opp.hand)}张，相对安全。")

        # Teammate assessment
        teammates = [p for p in self.players
                     if p is not player
                     and self._is_partner(self.players.index(player),
                                          self.players.index(p))]
        if teammates:
            min_tm = min(teammates, key=lambda p: len(p.hand))
            if len(min_tm.hand) <= 3:
                parts.append(f"🤝 队友{min_tm.name}只剩{len(min_tm.hand)}张！立即PASS让队友跑，千万不要压队友！")
            elif len(min_tm.hand) <= 6:
                parts.append(f"队友{min_tm.name}还剩{len(min_tm.hand)}张，接近胜利，建议PASS配合。")
            elif len(min_tm.hand) > 10:
                parts.append("队友牌还多，如果你牌力强可以主动接牌权。")

        # Leading strategy
        if last_play is None:
            parts.append("★ 你是首家。优先选高效组合（顺子>连对>飞机>三带），一次性多出牌。")

        # Must-beat pressure
        if must_beat and last_play:
            parts.append("上家是敌人，不压就给他牌权。用最小能压的牌应对，保留大牌。")

        return "。".join(parts) if parts else ""

    def _build_card_reading(self, player) -> str:
        """Analyze which high cards are likely still in play."""
        if not self.played_high_cards:
            return ""

        parts = []
        # Jokers
        if 16 in self.played_high_cards and 17 in self.played_high_cards:
            parts.append("双王已出")
        elif 16 in self.played_high_cards:
            parts.append("小王已出，大王在外")
        elif 17 in self.played_high_cards:
            parts.append("大王已出，小王在外")
        else:
            parts.append("双王均在外")

        # 2s played count
        # (simplified: we just track if 2s have been seen)
        if 15 in self.played_high_cards:
            parts.append("已有2被打出")
        else:
            parts.append("所有2均在外")

        # Aces
        if 14 in self.played_high_cards:
            parts.append("已有A被打出")

        # Player's own high card count
        player_high = sum(1 for c in player.hand if c.rank >= 14)
        if player_high > 0:
            parts.append(f"你手中有{player_high}张大牌(≥A)")

        return "；".join(parts) if parts else ""

    # ---- Result ----

    def _resolve_game(self, winner):
        base = 1
        multiplier = 2 ** self.bomb_count if self.bomb_count > 0 else 1
        total_mult = base * multiplier

        print(f"\n  {Colors.color(f'[WIN] {winner.name} ({winner.role}) wins!', Colors.YELLOW)}")
        if self.bomb_count > 0:
            print(f"  {Colors.color(f'Bombs: {self.bomb_count} — score x{multiplier}', Colors.YELLOW)}")

        self.finished = True
        if winner.role.startswith("Landlord"):
            self.winner = "landlord"
            winner.score += 2 * total_mult
            for p in self.players:
                if p != winner:
                    p.score -= 1 * total_mult
        else:
            self.winner = "farmers"
            for p in self.players:
                if p.role.startswith("Farmer"):
                    p.score += 1 * total_mult
                else:
                    p.score -= 2 * total_mult

    def _is_partner(self, idx, other_idx):
        p1, p2 = self.players[idx], self.players[other_idx]
        return p1.role.startswith("Farmer") and p2.role.startswith("Farmer")

    def check_win(self):
        return self.winner if self.finished else None

    def run(self, max_rounds=100, verbose=True):
        self.setup()
        for _ in range(max_rounds):
            self.round = self.round_num
            self.step()
            if self.finished:
                if verbose:
                    self._print_result()
                if self.logger:
                    self.logger.write_summary(self.players, self.winner, self.round_num, self.game_log)
                return self.winner
        return None

    def _print_dim(self, text):
        print(f"  {Colors.dim(text)}")

    def _print_setup(self):
        pass

    def _print_result(self):
        print(f"\n{Colors.bold('=' * 40)}")
        print(f"  Final scores:")
        for p in sorted(self.players, key=lambda x: x.score, reverse=True):
            print(f"  {p.name:12s} {p.score:+d}")
        print(Colors.bold('=' * 40))
