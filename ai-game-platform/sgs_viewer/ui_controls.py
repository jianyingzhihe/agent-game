"""Pygame UI controls: buttons, speed slider, step counter, auto-play toggle."""

import pygame
from .assets import C, FONTS, WINDOW_WIDTH, CONTROL_HEIGHT, blend_rgb


class Button:
    """A clickable button rendered with pygame.draw."""

    def __init__(self, x: int, y: int, w: int, h: int, text: str, action: str):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.action = action
        self.hovered = False
        self.toggled = False

    def update(self, mouse_pos: tuple[int, int]):
        self.hovered = self.rect.collidepoint(mouse_pos)

    def draw(self, surface: pygame.Surface):
        if self.hovered:
            bg = blend_rgb(C["button_bg"], C["white"], 0.15)
        elif self.toggled:
            bg = C["button_bg"]
        else:
            bg = C["button_sec"]
        pygame.draw.rect(surface, bg, self.rect, border_radius=6)
        txt = FONTS.button.render(self.text, True, C["text_primary"])
        surface.blit(txt, (self.rect.centerx - txt.get_width() // 2,
                           self.rect.centery - txt.get_height() // 2))

    def handle_click(self, pos: tuple[int, int]) -> str | None:
        if self.rect.collidepoint(pos):
            return self.action
        return None


class SpeedSlider:
    """A horizontal slider for auto-play speed (1=slow, 2=normal, 3=fast)."""

    def __init__(self, x: int, y: int, w: int, h: int):
        self.rect = pygame.Rect(x, y, w, h)
        self.value = 2  # 1, 2, 3
        self.dragging = False
        self._labels = {1: "慢", 2: "正常", 3: "快"}

    def update(self, mouse_pos: tuple[int, int], mouse_down: bool):
        if mouse_down and self.rect.collidepoint(mouse_pos):
            self.dragging = True
        if not mouse_down:
            self.dragging = False
        if self.dragging:
            rel_x = mouse_pos[0] - self.rect.x
            frac = max(0, min(1, rel_x / self.rect.width))
            self.value = 1 + round(frac * 2)

    def draw(self, surface: pygame.Surface):
        # Track background
        track_rect = pygame.Rect(self.rect.x, self.rect.centery - 3, self.rect.width, 6)
        pygame.draw.rect(surface, C["slider_track"], track_rect, border_radius=3)

        # Handle position
        frac = (self.value - 1) / 2
        handle_x = self.rect.x + int(frac * self.rect.width)
        handle_rect = pygame.Rect(handle_x - 8, self.rect.centery - 10, 16, 20)
        pygame.draw.rect(surface, C["slider_thumb"], handle_rect, border_radius=4)

        # Label
        label = self._labels.get(self.value, "正常")
        lbl_surf = FONTS.card.render(label, True, C["text_secondary"])
        surface.blit(lbl_surf, (self.rect.x + self.rect.width + 8,
                                self.rect.centery - lbl_surf.get_height() // 2))

    def handle_click(self, pos: tuple[int, int]):
        if self.rect.collidepoint(pos):
            rel_x = pos[0] - self.rect.x
            frac = max(0, min(1, rel_x / self.rect.width))
            self.value = 1 + round(frac * 2)

    def get_speed_ms(self) -> int:
        return {1: 2200, 2: 1000, 3: 350}.get(self.value, 1000)


class ControlBar:
    """Bottom control bar: buttons, slider, step info, phase badge."""

    def __init__(self):
        self.buttons: list[Button] = []
        self.slider: SpeedSlider | None = None
        self.auto_playing = False
        self.step_text = "Step 0/0"
        self.phase_text = ""
        self.step_rect = pygame.Rect(0, 0, 100, 32)
        self.phase_rect = pygame.Rect(0, 0, 60, 32)

    def layout_for_surface(self, surface_height: int):
        """Position controls at the bottom of the given surface."""
        bar_y = surface_height - CONTROL_HEIGHT

        # Calculate total width of all controls
        btn_w, btn_h = 48, 36
        step_w = 110
        auto_w = 90
        slider_w = 100
        gap = 8

        total_w = (4 * btn_w + step_w + auto_w + slider_w +
                   4 * 30 + gap * 10)  # labels + gaps
        start_x = (WINDOW_WIDTH - total_w) // 2
        if start_x < 10:
            start_x = 10

        x = start_x
        by = bar_y + (CONTROL_HEIGHT - btn_h) // 2

        self.buttons.clear()

        def add_btn(text, action, w=btn_w):
            nonlocal x
            self.buttons.append(Button(x, by, w, btn_h, text, action))
            x += w + gap

        add_btn("<<", "beginning")
        add_btn("<", "prev")
        x += 4

        # Step label (drawn as text, not button)
        self.step_rect = pygame.Rect(x, by, step_w, btn_h)
        x += step_w + gap + 4

        add_btn(">", "next")
        add_btn(">>", "end")
        x += 12

        # Auto-play button
        self.auto_btn = Button(x, by, auto_w, btn_h, "自动", "autoplay_toggle")
        self.buttons.append(self.auto_btn)
        x += auto_w + gap + 8

        # Speed label
        self.speed_label_rect = pygame.Rect(x, by, 36, btn_h)
        x += 36 + gap

        # Speed slider
        self.slider = SpeedSlider(x, by, slider_w, btn_h)
        x += slider_w + 40

        # Phase badge area
        self.phase_rect = pygame.Rect(x, by, 60, btn_h)
        self._bar_y = bar_y
        self._start_x = start_x

    def update(self, mouse_pos: tuple[int, int], mouse_down: bool):
        for btn in self.buttons:
            btn.update(mouse_pos)
        if self.slider:
            self.slider.update(mouse_pos, mouse_down)

    def draw(self, surface: pygame.Surface):
        h = surface.get_height()
        bar_y = h - CONTROL_HEIGHT

        # Background
        bar_rect = pygame.Rect(0, bar_y, surface.get_width(), CONTROL_HEIGHT)
        pygame.draw.rect(surface, C["panel_bg"], bar_rect)
        pygame.draw.line(surface, C["divider"], (0, bar_y), (surface.get_width(), bar_y), 1)

        # Buttons
        for btn in self.buttons:
            btn.draw(surface)

        # Step text
        step_surf = FONTS.step.render(self.step_text, True, C["text_primary"])
        sr = self.step_rect
        sr.y = bar_y + (CONTROL_HEIGHT - sr.height) // 2
        surface.blit(step_surf, (sr.centerx - step_surf.get_width() // 2,
                                 sr.centery - step_surf.get_height() // 2))

        # Slider
        if self.slider:
            self.slider.draw(surface)

        # Phase badge
        if self.phase_text:
            phase_colors = {"出牌": C["card_tao"], "响应": C["card_shan"],
                           "弃牌": C["flash_damage"], "选牌": C["card_wuxie"]}
            pcolor = phase_colors.get(self.phase_text, C["skill_badge"])
            phase_surf = FONTS.phase.render(self.phase_text, True, C["white"])
            pr = self.phase_rect
            pr.y = bar_y + (CONTROL_HEIGHT - pr.height) // 2
            pw = phase_surf.get_width() + 20
            badge_rect = pygame.Rect(pr.centerx - pw // 2, pr.y, pw, pr.height)
            pygame.draw.rect(surface, pcolor, badge_rect, border_radius=6)
            surface.blit(phase_surf, (badge_rect.centerx - phase_surf.get_width() // 2,
                                      badge_rect.centery - phase_surf.get_height() // 2))

    def handle_click(self, pos: tuple[int, int]) -> str | None:
        for btn in self.buttons:
            action = btn.handle_click(pos)
            if action:
                return action
        if self.slider:
            self.slider.handle_click(pos)
        return None

    def set_step(self, current: int, total: int, phase: str):
        self.step_text = f"Step {current}/{total}"
        phase_labels = {"play": "出牌", "respond": "响应", "discard": "弃牌", "select_card": "选牌"}
        self.phase_text = phase_labels.get(phase, "")

    def set_auto_state(self, playing: bool):
        self.auto_playing = playing
        if playing:
            self.auto_btn.text = "停止"
            self.auto_btn.toggled = True
        else:
            self.auto_btn.text = "自动"
            self.auto_btn.toggled = False

    def get_speed_ms(self) -> int:
        if self.slider:
            return self.slider.get_speed_ms()
        return 1000
