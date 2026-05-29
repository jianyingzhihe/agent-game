"""Pygame renderer: round table layout, player panels, arrows, info panel, notifications."""

import math
import pygame
from .assets import (
    C, FONTS, CARD_COLORS, SKILL_DESC, SKILL_ACTIONS,
    INFO_WIDTH, CONTROL_HEIGHT,
    blend_rgb, get_model_icon, IDENTITY_COLORS,
)
from .game_state import GameSnapshot, PlayerState
from .animations import AnimationEngine, ArrowAnimation


class SkillNotification:
    """A static notification that appears below a player panel."""

    def __init__(self, text: str, x: float, y: float, color):
        self.text = text
        self.x = x
        self.y = y
        self.color = color


class GameRenderer:
    """Draws the complete game view onto a pygame.Surface."""

    def __init__(self):
        self._prev_hp: dict[str, int] = {}
        self._global_notifs: list[SkillNotification] = []
        self._prev_turn_player = ""
        self._prev_phase = ""
        self._prev_round = -1
        self._prev_step_idx = -1
        self._seen_turns: set[tuple[str, int]] = set()
        self.panel_content_w = 232
        self.panel_content_h = 182
        # Current panel dimensions (recomputed each draw)
        self.panel_w = 232
        self.panel_h = 182  # tighter default for non-fullscreen windows

    # ═══════════════════════════════════════════════════
    # Main draw entry
    # ═══════════════════════════════════════════════════

    def draw_all(
        self,
        surface: pygame.Surface,
        snapshot: GameSnapshot,
        animations: AnimationEngine,
        info_visible: bool,
        now_ms: int,
        mouse_pos: tuple[int, int],
    ) -> None:
        w, h = surface.get_size()
        surface.fill(C["bg"])

        center_x = w // 2 + (-INFO_WIDTH // 2 if info_visible else 0)
        # Center the circle between banner bottom and control bar top
        avail_top = self.banner_height
        avail_bottom = h - CONTROL_HEIGHT
        center_y = (avail_top + avail_bottom) // 2

        # Compute proportional panel dimensions
        pw, ph = self._get_panel_dimensions(w, h, info_visible)
        self.panel_w, self.panel_h = pw, ph

        positions = self._compute_positions(snapshot.player_order, center_x, center_y,
                                            avail_top, avail_bottom, pw, ph)
        # _compute_positions may shrink panels to fit adjacency; re-read
        pw, ph = self.panel_w, self.panel_h

        # Detect state changes and trigger notifications
        self._detect_changes(snapshot, positions, now_ms)

        # Draw arrows (behind panels)
        for arrow in animations.arrows:
            self._draw_bezier_arrow(surface, arrow, now_ms)

        # Draw player panels
        for name in snapshot.player_order:
            ps = snapshot.players.get(name)
            if ps is None:
                continue
            pos = positions.get(name)
            if pos is None:
                continue
            is_turn = (name == snapshot.turn_player)
            flash = animations.panel_flashes.get(name, 0.0)
            heal_flash = animations.panel_flashes.get(f"heal_{name}", 0.0)
            self._draw_player_panel(surface, ps, pos[0], pos[1], pw, ph, is_turn, flash, heal_flash, now_ms)

        # Action label (below each player's panel — single line, no overlap)
        if snapshot.active_action:
            source = snapshot.active_action.source_player
            if source in positions:
                x, y = positions[source]
                self._draw_action_label(surface, x, y + self.panel_h // 2 + 14,
                                        snapshot.active_action.display_text)

        # Global notifications bar (above control bar)
        self._draw_global_notifs(surface)

        # ── Turn/Phase banner (top center) ──
        if snapshot.turn_player:
            self._draw_turn_banner(surface, snapshot, info_visible, now_ms)

        # Info panel
        if info_visible:
            self._draw_info_panel(surface, w - INFO_WIDTH, 0, INFO_WIDTH,
                                  h - CONTROL_HEIGHT, snapshot)

    # ═══════════════════════════════════════════════════
    # State change detection
    # ═══════════════════════════════════════════════════

    def _detect_changes(self, snapshot: GameSnapshot, positions: dict, now_ms: int):
        """Detect state changes and queue global notifications."""
        # Clear when step index changes
        if snapshot.step_index != self._prev_step_idx:
            self._global_notifs.clear()
            self._prev_step_idx = snapshot.step_index

        tp = snapshot.turn_player
        phase = snapshot.current_phase
        rnd = snapshot.current_round

        # ── Turn start: only fire once per (player, round) ──
        if phase == "play" and tp:
            turn_key = (tp, rnd)
            if turn_key not in self._seen_turns:
                self._seen_turns.add(turn_key)
                tp_ps = snapshot.players.get(tp)
                tp_disp = tp_ps.display_name if tp_ps else tp
                self._global_notifs.append(
                    SkillNotification(f"● {tp_disp} 摸2张牌", 0, 0, C["card_tao"])
                )

        # ── Phase transition (same player, non-play) → global ──
        phase_labels_full = {"respond": "响应", "discard": "弃牌", "select_card": "选牌"}
        phase_colors = {"respond": C["card_shan"], "discard": C["flash_damage"],
                        "select_card": C["card_wuxie"]}
        if phase != self._prev_phase and tp and tp == self._prev_turn_player:
            label = phase_labels_full.get(phase)
            if label:
                tp_ps = snapshot.players.get(tp)
                tp_disp = tp_ps.display_name if tp_ps else tp
                self._global_notifs.append(
                    SkillNotification(f"● {tp_disp} {label}", 0, 0,
                                      phase_colors.get(phase, C["text_secondary"]))
                )

        self._prev_turn_player = tp
        self._prev_phase = phase
        self._prev_round = rnd

        # ── Skill activation → global notification ──
        action = snapshot.active_action
        if action and action.action_type in SKILL_ACTIONS:
            src_ps = snapshot.players.get(action.source_player)
            src_disp = src_ps.display_name if src_ps else action.source_player
            self._global_notifs.append(
                SkillNotification(f"[技能] {src_disp} 发动【苦肉】", 0, 0, C["flash_damage"])
            )

    def _draw_global_notifs(self, surface: pygame.Surface):
        """Draw a horizontal strip of global notifications above the control bar."""
        if not self._global_notifs:
            return
        w = surface.get_width()
        h = surface.get_height()
        bar_y = h - CONTROL_HEIGHT - 30
        # Semi-transparent background strip
        strip_rect = pygame.Rect(0, bar_y, w, 30)
        pygame.draw.rect(surface, C["panel_bg"], strip_rect)
        pygame.draw.line(surface, C["divider"], (0, bar_y), (w, bar_y), 1)
        # Draw notifications left-to-right
        x = 16
        for n in self._global_notifs:
            txt = FONTS.notify.render(n.text[:40], True, n.color)
            surface.blit(txt, (x, bar_y + 5))
            x += txt.get_width() + 16

    # ═══════════════════════════════════════════════════
    # Dynamic panel sizing
    # ═══════════════════════════════════════════════════

    def _get_panel_dimensions(self, w: int, h: int, info_visible: bool) -> tuple[int, int]:
        """Compute panel dimensions proportional to window size.

        Base reference: 1440x900 -> about 260x215.
        Width-only scaling makes fullscreen/wide layouts overgrow vertically, so
        the playable height also caps the panel size.
        """
        info_w = INFO_WIDTH if info_visible else 0
        avail_w = w - info_w
        play_h = max(1, h - CONTROL_HEIGHT - self.banner_height)
        pw = max(148, min(320, int(avail_w * 0.19), int(play_h * 0.30)))
        ph = max(118, min(280, int(pw * 182 / 232)))
        return pw, ph

    # ═══════════════════════════════════════════════════
    # Layout
    # ═══════════════════════════════════════════════════

    def compute_positions(self, player_order, cx, cy, pw, ph,
                          avail_top=0, avail_bottom=900):
        return self._compute_positions(player_order, cx, cy,
                                       avail_top, avail_bottom, pw, ph)

    def _compute_positions(self, player_order, cx, cy,
                           avail_top=0, avail_bottom=900,
                           panel_w=260, panel_h=215):
        n = len(player_order)
        if n == 0:
            return {}

        margin = 14
        min_panel_gap = 10
        label_space = 28
        min_panel_w = 118
        min_panel_h = 98

        positions = {}
        for _ in range(16):
            positions = self._compute_perimeter_positions(
                player_order, cx, cy, avail_top, avail_bottom,
                panel_w, panel_h, margin, label_space,
            )
            rects = [self._panel_rect(pos, panel_w, panel_h) for pos in positions.values()]
            if not self._rects_overlap(rects, min_panel_gap):
                break

            next_w = max(min_panel_w, int(panel_w * 0.90))
            next_h = max(min_panel_h, int(panel_h * 0.90))
            if next_w == panel_w and next_h == panel_h:
                break
            panel_w, panel_h = next_w, next_h

        self.panel_w, self.panel_h = panel_w, panel_h
        return positions

    def _compute_perimeter_positions(
        self,
        player_order,
        cx: int,
        cy: int,
        avail_top: int,
        avail_bottom: int,
        panel_w: int,
        panel_h: int,
        margin: int,
        label_space: int,
    ) -> dict:
        n = len(player_order)
        if n == 1:
            return {player_order[0]: (cx, cy)}

        half_w = panel_w / 2
        half_h = panel_h / 2
        left = margin + half_w
        right = max(left, 2 * cx - margin - half_w)
        top = avail_top + margin + half_h
        bottom = max(top, avail_bottom - margin - label_space - half_h)

        layout_w = max(1.0, right - left)
        layout_h = max(1.0, bottom - top)
        perimeter = 2 * (layout_w + layout_h)
        step = perimeter / n

        def point_at(distance: float) -> tuple[int, int]:
            d = distance % perimeter
            top_right = layout_w / 2
            right_bottom = top_right + layout_h
            bottom_left = right_bottom + layout_w
            left_top = bottom_left + layout_h

            if d <= top_right:
                return int((left + right) / 2 + d), int(top)
            if d <= right_bottom:
                return int(right), int(top + (d - top_right))
            if d <= bottom_left:
                return int(right - (d - right_bottom)), int(bottom)
            if d <= left_top:
                return int(left), int(bottom - (d - bottom_left))
            return int(left + (d - left_top)), int(top)

        positions = {}
        for i, name in enumerate(player_order):
            positions[name] = point_at(i * step)
        return positions

    def _panel_rect(self, pos: tuple[int, int], panel_w: int, panel_h: int) -> pygame.Rect:
        x, y = pos
        return pygame.Rect(x - panel_w // 2, y - panel_h // 2, panel_w, panel_h)

    def _rects_overlap(self, rects: list[pygame.Rect], gap: int) -> bool:
        for i, rect in enumerate(rects):
            padded = rect.inflate(gap, gap)
            for other in rects[i + 1:]:
                if padded.colliderect(other):
                    return True
        return False
    def _rounded_rect(self, surface, rect, radius, color, width=0):
        r = min(radius, rect.width // 2, rect.height // 2)
        if width > 0:
            pygame.draw.rect(surface, color, rect, width, border_radius=r)
            return
        pygame.draw.circle(surface, color, (rect.x + r, rect.y + r), r)
        pygame.draw.circle(surface, color, (rect.x + rect.w - r, rect.y + r), r)
        pygame.draw.circle(surface, color, (rect.x + r, rect.y + rect.h - r), r)
        pygame.draw.circle(surface, color, (rect.x + rect.w - r, rect.y + rect.h - r), r)
        pygame.draw.rect(surface, color, (rect.x + r, rect.y, rect.w - 2 * r, rect.h))
        pygame.draw.rect(surface, color, (rect.x, rect.y + r, rect.w, rect.h - 2 * r))

    def _truncate_text(self, font, text: str, max_width: int) -> str:
        """Keep single-line labels inside their allotted width."""
        if not text or max_width <= 0:
            return ""
        if font.size(text)[0] <= max_width:
            return text
        suffix = "..."
        if font.size(suffix)[0] >= max_width:
            return ""
        trimmed = text
        while trimmed and font.size(trimmed + suffix)[0] > max_width:
            trimmed = trimmed[:-1]
        return (trimmed + suffix) if trimmed else ""

    # ═══════════════════════════════════════════════════
    # Player Panel
    # ═══════════════════════════════════════════════════

    def _draw_player_panel(self, surface, ps, cx, cy, pw, ph, is_turn, flash, heal_flash, now_ms):
        actual_x0 = cx - pw // 2
        actual_y0 = cy - ph // 2
        actual_rect = pygame.Rect(actual_x0, actual_y0, pw, ph)
        compact = self.panel_content_h < 190 or self.panel_content_w < 238
        name_font = FONTS.name_small if compact else FONTS.name
        skill_font = FONTS.skill_small if compact else FONTS.skill
        card_font = FONTS.card_small if compact else FONTS.card

        # Background
        if not ps.alive:
            bg = C["panel_dead"]
        elif is_turn:
            bg = C["panel_turn"]
        else:
            bg = C["panel_bg"]

        if flash > 0:
            bg = blend_rgb(bg, C["flash_damage"], flash * 0.45)
        if heal_flash > 0:
            bg = blend_rgb(bg, C["flash_heal"], heal_flash * 0.35)

        shadow_rect = actual_rect.inflate(10, 14)
        shadow_surf = pygame.Surface(shadow_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(shadow_surf, (4, 7, 14, 92), shadow_surf.get_rect(), border_radius=20)
        surface.blit(shadow_surf, (shadow_rect.x, shadow_rect.y + 4))

        # Turn glow
        if is_turn and ps.alive:
            glow_alpha = 0.4 + 0.4 * math.sin(now_ms / 600.0)
            glow_color = blend_rgb(C["bg"], C["turn_glow"], glow_alpha)
            self._rounded_rect(surface, actual_rect.inflate(4, 4), 14, glow_color, width=2)

        # Render panel internals in a fixed logical space, then scale the whole
        # panel to the final rect so content always stays proportional.
        main_surface = surface
        pw = self.panel_content_w
        ph = self.panel_content_h
        x0 = 0
        y0 = 0
        cx = pw // 2
        cy = ph // 2
        panel_rect = pygame.Rect(0, 0, pw, ph)
        panel_surface = pygame.Surface((pw, ph), pygame.SRCALPHA)
        surface = panel_surface
        self._rounded_rect(surface, panel_rect, 12, bg)
        pygame.draw.rect(surface, C["panel_border"], panel_rect, 1, border_radius=12)
        pygame.draw.line(
            surface,
            C["panel_highlight"],
            (panel_rect.x + 12, panel_rect.y + 11),
            (panel_rect.right - 12, panel_rect.y + 11),
            1,
        )

        # ── Avatar (model icon on white circle bg, fallback to letter circle) ──
        avatar_r = 18 if compact else 24
        avatar_x = cx
        avatar_y = y0 + avatar_r + (8 if compact else 10)
        icon = get_model_icon(ps.model_name) if ps.alive else None
        if icon:
            size = avatar_r * 2
            icon_scaled = icon if icon.get_size() == (size, size) else pygame.transform.smoothscale(icon, (size, size))
            # Composite: white circle background + icon on top, then clip to circle
            avatar_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            # Step 1: white circle background (for transparent PNGs)
            pygame.draw.circle(avatar_surf, (255, 255, 255, 255), (avatar_r, avatar_r), avatar_r)
            # Step 2: icon composited on top (alpha-blended over white)
            avatar_surf.blit(icon_scaled, (0, 0))
            # Step 3: circular clip mask to clean up rough edges
            mask = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(mask, (255, 255, 255, 255), (avatar_r, avatar_r), avatar_r)
            avatar_surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            # Draw final composite
            icon_rect = avatar_surf.get_rect(center=(avatar_x, avatar_y))
            surface.blit(avatar_surf, icon_rect.topleft)
            # Circle border
            pygame.draw.circle(surface, C["text_secondary"], (avatar_x, avatar_y), avatar_r, 2)
        elif ps.alive:
            pygame.draw.circle(surface, C["skill_badge"], (avatar_x, avatar_y), avatar_r)
            pygame.draw.circle(surface, C["text_secondary"], (avatar_x, avatar_y), avatar_r, 2)
            initial = ps.display_name[0] if ps.display_name else "?"
            init_surf = FONTS.avatar.render(initial, True, C["text_primary"])
            surface.blit(init_surf, (avatar_x - init_surf.get_width() // 2,
                                     avatar_y - init_surf.get_height() // 2))
        else:
            pygame.draw.circle(surface, C["panel_dead"], (avatar_x, avatar_y), avatar_r)
            pygame.draw.circle(surface, C["hp_empty"], (avatar_x, avatar_y), avatar_r, 2)
            init_surf = FONTS.avatar.render("亡", True, C["hp_empty"])
            surface.blit(init_surf, (avatar_x - init_surf.get_width() // 2,
                                     avatar_y - init_surf.get_height() // 2))

        # ── Name (below avatar) ──
        hand_label_y = ph - (48 if compact else 54)
        cards_y = ph - (22 if compact else 24)

        name_color = C["text_secondary"] if not ps.alive else C["text_primary"]
        skill_gap = 8
        content_max_w = pw - 28
        skill_name_surf = None
        skill_pill_w = 0
        if ps.skill_name and ps.alive:
            skill_text = self._truncate_text(
                skill_font,
                ps.skill_name,
                max(42, int(content_max_w * 0.34)),
            )
            if skill_text:
                skill_name_surf = skill_font.render(skill_text, True, C["card_wuxie"])
                skill_pill_w = skill_name_surf.get_width() + 12
        name_max_w = content_max_w if not skill_name_surf else max(52, content_max_w - skill_gap - skill_pill_w)
        name_text = self._truncate_text(name_font, ps.display_name, name_max_w)
        name_surf = name_font.render(name_text, True, name_color)
        row_w = name_surf.get_width()
        if skill_name_surf:
            row_w += skill_gap + skill_pill_w
        row_y = avatar_y + avatar_r + 4
        row_x = cx - row_w // 2
        surface.blit(name_surf, (row_x, row_y))
        row_bottom = row_y + name_surf.get_height()
        if skill_name_surf:
            skill_rect = pygame.Rect(
                row_x + name_surf.get_width() + skill_gap,
                row_y + max(0, (name_surf.get_height() - (skill_name_surf.get_height() + 4)) // 2),
                skill_pill_w,
                skill_name_surf.get_height() + 4,
            )
            self._rounded_rect(surface, skill_rect, 6, C["skill_badge"])
            surface.blit(
                skill_name_surf,
                (
                    skill_rect.x + (skill_rect.width - skill_name_surf.get_width()) // 2,
                    skill_rect.y + (skill_rect.height - skill_name_surf.get_height()) // 2,
                ),
            )
            row_bottom = max(row_bottom, skill_rect.bottom)

        # ── Identity badge ──
        badge_bottom = row_bottom
        if ps.identity_label and ps.alive:
            id_color_key = IDENTITY_COLORS.get(ps.identity, "id_hidden")
            id_color = C.get(id_color_key, C["id_hidden"])
            id_surf = skill_font.render(ps.identity_label, True, id_color)
            id_pad = 5
            id_pill_w = id_surf.get_width() + id_pad * 2
            id_pill_h = id_surf.get_height() + 3
            id_y = badge_bottom + 4
            id_pill = pygame.Rect(cx - id_pill_w // 2, id_y, id_pill_w, id_pill_h)
            self._rounded_rect(surface, id_pill, 5, C["skill_badge"])
            surface.blit(id_surf, (cx - id_surf.get_width() // 2, id_y + 1))
            badge_bottom = id_pill.bottom

        # ── HP bar ──
        hp_row_y = badge_bottom + (8 if compact else 10)
        hp_text = f"{ps.hp} / {ps.max_hp}"
        hp_surf = skill_font.render(hp_text, True, C["text_primary"])
        hp_gap = 8
        bar_w = min(118 if compact else 138, max(72, pw - hp_surf.get_width() - 48))
        bar_h = 9 if compact else 10
        total_hp_w = hp_surf.get_width() + hp_gap + bar_w
        hp_x = cx - total_hp_w // 2
        bar_x = hp_x + hp_surf.get_width() + hp_gap
        bar_y = hp_row_y + max(0, (hp_surf.get_height() - bar_h) // 2)
        surface.blit(hp_surf, (hp_x, hp_row_y))
        pygame.draw.rect(surface, C["hp_empty"], (bar_x, bar_y, bar_w, bar_h), border_radius=7)
        # Bar filled
        if ps.max_hp > 0:
            fill_w = int(bar_w * ps.hp / ps.max_hp)
            if fill_w > 0:
                hp_color = C["hp_heart"]
                if ps.hp == 1:
                    hp_color = blend_rgb(C["hp_heart"], C["flash_damage"], 0.3)
                elif ps.hp >= ps.max_hp:
                    hp_color = blend_rgb(C["hp_heart"], C["flash_heal"], 0.2)
                pygame.draw.rect(surface, hp_color, (bar_x, bar_y, fill_w, bar_h), border_radius=7)
        # Bar border
        pygame.draw.rect(surface, blend_rgb(C["hp_heart"], C["hp_empty"], 0.5),
                         (bar_x, bar_y, bar_w, bar_h), 1, border_radius=7)

        # ── Skill badge + description ──
        skill_y = bar_y + bar_h + (11 if compact else 13)
        hand_label_y = ph - (48 if compact else 54)
        cards_y = ph - (22 if compact else 24)
        if False:
            s_text = f"【{ps.skill_name}】"
            s_surf = skill_font.render(s_text, True, C["card_wuxie"])
            tw = s_surf.get_width() + 14
            badge = pygame.Rect(cx - tw // 2, skill_y - 8, tw, 18 if compact else 20)
            self._rounded_rect(surface, badge, 7, C["skill_badge"])
            surface.blit(s_surf, (cx - s_surf.get_width() // 2, skill_y - (7 if compact else 8)))

            desc = SKILL_DESC.get(ps.skill_name, "")
            if desc and not compact:
                d_surf = card_font.render(desc, True, C["text_secondary"])
                desc_y = skill_y + 16
                if desc_y + d_surf.get_height() <= hand_label_y - 8:
                    surface.blit(d_surf, (cx - d_surf.get_width() // 2, desc_y))

        # ── Hand info (always visible) ──
        hand_text = f"手牌 {ps.hand_count}张"
        hand_surf = card_font.render(hand_text, True,
                                      C["text_secondary"] if ps.alive else C["hp_empty"])
        surface.blit(hand_surf, (cx - hand_surf.get_width() // 2, hand_label_y))

        # ── Card summary (always show, even if empty) ──
        if ps.alive:
            cards = ps.hand_summary if ps.hand_summary else []
            self._draw_card_summary(surface, cx, cards_y, cards, compact=compact)

        # ── Dead overlay ──
        if not ps.alive:
            dead_surf = FONTS.large.render("阵亡", True, (120, 60, 60))
            dead_surf = pygame.transform.rotate(dead_surf, 20)
            surface.blit(dead_surf, (cx - dead_surf.get_width() // 2,
                                     cy - dead_surf.get_height() // 2))

    # ── Card summary ──
        scaled_panel = pygame.transform.smoothscale(panel_surface, (actual_rect.w, actual_rect.h))
        main_surface.blit(scaled_panel, actual_rect.topleft)

    def _draw_card_summary(self, surface, cx, y, cards, compact=False):
        font = FONTS.card_small if compact else FONTS.card
        if not cards:
            # Show placeholder when hand is empty
            empty_surf = FONTS.card.render("—", True, C["text_secondary"])
            surface.blit(empty_surf, (cx - empty_surf.get_width() // 2, y - empty_surf.get_height() // 2))
            return
        capsule_w, capsule_h, gap = (38, 16, 4) if compact else (46, 18, 6)
        n = len(cards)
        total_w = n * capsule_w + (n - 1) * gap
        start_x = cx - total_w // 2
        for i, c in enumerate(cards):
            name = c.get("name", "?")
            count = c.get("count", 0)
            color_key = CARD_COLORS.get(name, "card_spell")
            color = C.get(color_key, C["card_spell"])
            bx = start_x + i * (capsule_w + gap)
            cap = pygame.Rect(bx, y - capsule_h // 2, capsule_w, capsule_h)
            self._rounded_rect(surface, cap, 7, color)
            label = f"{name[:2]}x{count}" if len(name) > 2 else f"{name}x{count}"
            lbl_surf = font.render(label, True, C["white"])
            surface.blit(lbl_surf, (bx + capsule_w // 2 - lbl_surf.get_width() // 2,
                                    y - lbl_surf.get_height() // 2))

    # ═══════════════════════════════════════════════════
    # Arrows
    # ═══════════════════════════════════════════════════

    def _draw_bezier_arrow(self, surface, anim, now_ms):
        alpha = anim.alpha_frac(now_ms)
        if alpha <= 0.01:
            return
        color = blend_rgb(C["bg"], anim.color, alpha)
        progress = anim.progress(now_ms)
        segments = 50
        pts = []
        for i in range(int(segments * progress) + 2):
            t = i / segments
            if t > progress:
                t = progress
            pts.append(anim.point_at(t))
            if t >= progress:
                break
        if len(pts) >= 2:
            pygame.draw.lines(surface, color, False, pts, 2)
        if progress > 0.12:
            tip_x, tip_y = anim.point_at(min(progress, 1.0))
            dx, dy = anim.tangent_at(min(progress, 0.95))
            angle = math.atan2(dy, dx)
            size = 10 * alpha
            pts_head = [
                (tip_x, tip_y),
                (tip_x + size * math.cos(angle + math.pi * 0.75),
                 tip_y + size * math.sin(angle + math.pi * 0.75)),
                (tip_x + size * math.cos(angle - math.pi * 0.75),
                 tip_y + size * math.sin(angle - math.pi * 0.75)),
            ]
            pygame.draw.polygon(surface, color, pts_head)

    # ═══════════════════════════════════════════════════
    # Labels
    # ═══════════════════════════════════════════════════

    def _draw_action_label(self, surface, x, y, text):
        surf = FONTS.action.render(text[:28], True, C["action_label"])
        surface.blit(surf, (x - surf.get_width() // 2, y))

    # ═══════════════════════════════════════════════════
    # Turn / Phase Banner
    # ═══════════════════════════════════════════════════

    def _draw_turn_banner(self, surface: pygame.Surface, snapshot: GameSnapshot,
                          info_visible: bool, now_ms: int):
        w = surface.get_width()
        center_x = w // 2 + (-INFO_WIDTH // 2 if info_visible else 0)

        phase_labels = {"play": "出牌", "respond": "响应",
                        "discard": "弃牌", "select_card": "选牌"}
        phase_colors = {"play": C["card_tao"], "respond": C["card_shan"],
                        "discard": C["flash_damage"], "select_card": C["card_wuxie"]}

        phase = snapshot.current_phase
        turn_player_key = snapshot.turn_player
        ps = snapshot.players.get(turn_player_key)
        turn_name = ps.display_name if ps else turn_player_key
        round_num = snapshot.current_round

        # Single-line compact banner:  [Name] 的回合 · [Phase] · 第N回合
        turn_text = f"{turn_name} 的回合"
        turn_surf = FONTS.large.render(turn_text, True, C["text_primary"])

        phase_text = phase_labels.get(phase, phase)
        phase_color = phase_colors.get(phase, C["text_secondary"])
        phase_surf = FONTS.phase.render(phase_text, True, C["white"])

        rnd_text = f"第 {round_num + 1} 回合" if round_num is not None and round_num >= 0 else ""
        rnd_surf = FONTS.skill.render(rnd_text, True, C["text_secondary"]) if rnd_text else None

        # Layout: gap between elements
        gap = 10
        pw = phase_surf.get_width() + 16
        ph = phase_surf.get_height() + 6
        total_w = turn_surf.get_width() + gap + pw + gap
        if rnd_surf:
            total_w += rnd_surf.get_width()

        banner_y = 6
        # Baseline Y for vertical centering (use largest element)
        base_y = banner_y + max(turn_surf.get_height(), ph) // 2

        x = center_x - total_w // 2

        # Draw turn name
        surface.blit(turn_surf, (x, banner_y))
        x += turn_surf.get_width() + gap

        # Draw phase badge pill
        badge_rect = pygame.Rect(x, banner_y + (turn_surf.get_height() - ph) // 2, pw, ph)
        self._rounded_rect(surface, badge_rect, 6, phase_color)
        surface.blit(phase_surf, (badge_rect.x + 8, badge_rect.y + 3))
        x += pw + gap

        # Draw round number
        if rnd_surf:
            surface.blit(rnd_surf, (x, banner_y + (turn_surf.get_height() - rnd_surf.get_height()) // 2))

    @property
    def banner_height(self) -> int:
        """Height of the turn banner (for layout calculations)."""
        return 42  # compact single-line banner: 6px margin + ~36px text

    def _draw_badge(self, surface, x, y, text):
        txt_surf = FONTS.phase.render(text, True, C["text_secondary"])
        rect = pygame.Rect(x, y, txt_surf.get_width() + 16, txt_surf.get_height() + 6)
        self._rounded_rect(surface, rect, 6, C["phase_bg"])
        surface.blit(txt_surf, (x + 8, y + 3))

    # ═══════════════════════════════════════════════════
    # Info Panel
    # ═══════════════════════════════════════════════════

    def _draw_info_panel(self, surface, x, y, w, h, snapshot):
        panel = pygame.Rect(x, y, w, h)
        pygame.draw.rect(surface, C["info_bg"], panel)
        pygame.draw.line(surface, C["divider"], (x, y), (x, y + h), 1)

        pad = 14
        cy = y + pad

        # Title
        alive_count = sum(1 for p in snapshot.players.values() if p.alive)
        total = len(snapshot.players)
        title = f"回合 {snapshot.current_round} · 存活 {alive_count}/{total}"
        t_surf = FONTS.info_title.render(title, True, C["text_primary"])
        surface.blit(t_surf, (x + pad, cy))
        cy += 26

        # Phase
        phase_map = {"play": "出牌阶段", "respond": "响应阶段", "discard": "弃牌阶段", "select_card": "选牌阶段"}
        phase_text = phase_map.get(snapshot.current_phase, snapshot.current_phase)
        p_surf = FONTS.info_text.render(f"阶段: {phase_text}", True, C["text_secondary"])
        surface.blit(p_surf, (x + pad, cy))
        cy += 20

        # Turn player
        tp_ps = snapshot.players.get(snapshot.turn_player)
        tp_display = tp_ps.display_name if tp_ps else snapshot.turn_player
        t_surf = FONTS.info_text.render(f"行动: {tp_display}", True, C["text_primary"])
        surface.blit(t_surf, (x + pad, cy))
        cy += 26

        # Player stats
        for name in snapshot.player_order:
            ps = snapshot.players.get(name)
            if ps is None:
                continue
            alive_str = "[活]" if ps.alive else "[亡]"
            line = f"{alive_str} {ps.display_name}: {ps.hp}/{ps.max_hp}HP {ps.hand_count}张"
            if ps.skill_name:
                line += f" [{ps.skill_name}]"
            if ps.identity_label:
                id_color_key = IDENTITY_COLORS.get(ps.identity, "id_hidden")
                line += f" [{ps.identity_label}]"
            else:
                id_color_key = "text_primary"
            ln_surf = FONTS.info_text.render(line, True,
                                              C.get(id_color_key, C["text_primary"]) if ps.alive else C["hp_empty"])
            surface.blit(ln_surf, (x + pad, cy))
            cy += 18

        cy += 6
        pygame.draw.line(surface, C["divider"], (x + pad, cy), (x + w - pad, cy), 1)
        cy += 12

        # Current action
        if snapshot.active_action:
            a_title = FONTS.info_title.render("当前动作", True, C["text_primary"])
            surface.blit(a_title, (x + pad, cy))
            cy += 22
            act_text = snapshot.active_action.display_text
            for line in self._wrap_text(act_text, w - pad * 2, FONTS.info_text):
                ln_surf = FONTS.info_text.render(line, True, C["action_label"])
                surface.blit(ln_surf, (x + pad, cy))
                cy += 20
            cy += 4

        # LLM reasoning
        source = snapshot.active_action.source_player if snapshot.active_action else snapshot.turn_player
        if source and source in snapshot.players:
            reason = snapshot.players[source].last_reason
            if reason:
                r_title = FONTS.info_title.render("AI 推理", True, C["text_primary"])
                surface.blit(r_title, (x + pad, cy))
                cy += 22
                for line in self._wrap_text(reason, w - pad * 2, FONTS.reason):
                    if cy > y + h - 40:
                        break
                    ln_surf = FONTS.reason.render(line, True, C["text_secondary"])
                    surface.blit(ln_surf, (x + pad, cy))
                    cy += 18

    # ═══════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════

    def _wrap_text(self, text, max_width, font):
        words = list(text)
        lines = []
        current = ""
        for ch in words:
            test = current + ch
            if font.render(test, True, (0, 0, 0)).get_width() > max_width:
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)
        return lines
