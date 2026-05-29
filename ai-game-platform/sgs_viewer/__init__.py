"""三国杀 Round-Table Replay Viewer (Pygame version).

Usage:
    python -m sgs_viewer [path/to/game.jsonl]
    python -m sgs_viewer                     # auto-load latest
"""

import sys
import math
import time
import pygame
from pathlib import Path

from .assets import C, WINDOW_WIDTH, WINDOW_HEIGHT, FPS, INFO_WIDTH, CONTROL_HEIGHT
from .log_parser import load_steps
from .game_state import GameStateEngine
from .renderer import GameRenderer
from .animations import AnimationEngine
from .ui_controls import ControlBar


class GameViewer:
    """Main application: owns the window, state engine, renderer, and game loop."""

    def __init__(self, jsonl_path: str):
        self.jsonl_path = jsonl_path

        # State
        self.engine = GameStateEngine()
        self.animations = AnimationEngine()
        self.renderer = GameRenderer()
        self.controls = ControlBar()

        self.current_idx = 0
        self.snapshot = None
        self.info_visible = True

        # Auto-play
        self._auto_timer = 0

        # Pygame display
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
        # Verify font rendering
        from .assets import FONTS, FONT_PATH
        test_surf = FONTS.name.render("三国杀测试", True, (255, 255, 255))
        font_status = f"Font: {Path(FONT_PATH).name if FONT_PATH else 'SysFont'}, test={test_surf.get_width()}px"
        print(f"[sgs_viewer] {font_status}")
        if test_surf.get_width() < 20:
            print(f"[sgs_viewer] WARNING: Font rendering may show boxes!")
        pygame.display.set_caption("三国杀 Round-Table Viewer")
        self.clock = pygame.time.Clock()

        # Control bar layout
        self.controls.layout_for_surface(WINDOW_HEIGHT)

        # Load
        self._load_game()
        self._goto_step(0)

    # ═══════════════════════════════════════════════════
    # Loading
    # ═══════════════════════════════════════════════════

    def _load_game(self):
        print(f"Loading: {self.jsonl_path}")
        steps = load_steps(self.jsonl_path)
        self.engine.load(steps)
        print(f"  Loaded {len(steps)} steps")
        p = Path(self.jsonl_path)
        session_name = p.parent.name if p.parent.name != "sanguosha" else p.name
        player_count = 0
        if steps:
            first = steps[0]
            if first.get("type") == "game_start":
                player_count = len(first.get("players", []))
        pygame.display.set_caption(f"三国杀 Round-Table — {player_count}人局 — {session_name}")

    # ═══════════════════════════════════════════════════
    # Navigation
    # ═══════════════════════════════════════════════════

    def _goto_step(self, idx: int):
        idx = max(0, min(idx, self.engine.total_steps() - 1))
        self.current_idx = idx
        self.snapshot = self.engine.get_snapshot(idx)

        if self.snapshot.active_action and self.snapshot.active_action.has_arrow():
            self._spawn_action_arrows()

        self.controls.set_step(self.current_idx, self.engine.total_steps(),
                               self.snapshot.current_phase)

    def _spawn_action_arrows(self):
        action = self.snapshot.active_action
        if not action:
            return

        w, h = self.screen.get_size()
        cx = w // 2 + (-INFO_WIDTH // 2 if self.info_visible else 0)
        avail_top = self.renderer.banner_height
        avail_bottom = h - CONTROL_HEIGHT
        cy = (avail_top + avail_bottom) // 2
        pw, ph = self.renderer._get_panel_dimensions(w, h, self.info_visible)
        self.renderer.panel_w, self.renderer.panel_h = pw, ph
        positions = self.renderer.compute_positions(
            self.snapshot.player_order, cx, cy, pw, ph, avail_top, avail_bottom)

        source = action.source_player
        now_ms = pygame.time.get_ticks()
        arrow_color = C.get(action.arrow_color, C["arrow_attack"])

        if action.action_type in ("spell_aoe_nanman", "spell_aoe_wanjian", "heal_aoe"):
            targets = [
                n for n in self.snapshot.player_order
                if n != source and self.snapshot.players.get(n) and self.snapshot.players[n].alive
            ]
            self.animations.spawn_aoe(source, targets, positions, arrow_color, now_ms)
        elif action.target_player and action.target_player in positions:
            sx, sy = positions.get(source, (0, 0))
            ex, ey = positions[action.target_player]
            self.animations.spawn_arrow(
                source, action.target_player,
                sx, sy, ex, ey, arrow_color, now_ms,
            )

    # ═══════════════════════════════════════════════════
    # Main Loop
    # ═══════════════════════════════════════════════════

    def run(self):
        running = True
        mouse_down = False

        while running:
            dt = self.clock.tick(FPS)
            now_ms = pygame.time.get_ticks()
            mouse_pos = pygame.mouse.get_pos()

            # ── Events ──
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.VIDEORESIZE:
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    self.controls.layout_for_surface(event.h)

                elif event.type == pygame.KEYDOWN:
                    action = self._handle_key(event.key)
                    if action:
                        self._dispatch(action)

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        mouse_down = True
                        action = self.controls.handle_click(event.pos)
                        if action:
                            self._dispatch(action)

                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        mouse_down = False

            # ── Update ──
            self.controls.update(mouse_pos, mouse_down)
            self.animations.update(dt, now_ms)

            # Auto-play
            if self.controls.auto_playing:
                self._auto_timer += dt
                interval = self.controls.get_speed_ms()
                if self._auto_timer >= interval:
                    self._auto_timer = 0
                    if self.current_idx < self.engine.total_steps() - 1:
                        self._goto_step(self.current_idx + 1)
                    else:
                        self.controls.set_auto_state(False)

            # ── Draw ──
            self.renderer.draw_all(
                self.screen, self.snapshot, self.animations,
                self.info_visible, now_ms, mouse_pos,
            )
            self.controls.draw(self.screen)

            pygame.display.flip()

        pygame.quit()

    # ═══════════════════════════════════════════════════
    # Input handling
    # ═══════════════════════════════════════════════════

    def _handle_key(self, key: int) -> str | None:
        if key == pygame.K_LEFT:
            return "prev"
        if key == pygame.K_RIGHT:
            return "next"
        if key == pygame.K_SPACE:
            return "autoplay_toggle"
        if key == pygame.K_HOME:
            return "beginning"
        if key == pygame.K_END:
            return "end"
        if key == pygame.K_ESCAPE:
            return "quit"
        if key == pygame.K_i:
            return "toggle_info"
        if key == pygame.K_1:
            if self.controls.slider:
                self.controls.slider.value = 1
            return "speed_change"
        if key == pygame.K_2:
            if self.controls.slider:
                self.controls.slider.value = 2
            return "speed_change"
        if key == pygame.K_3:
            if self.controls.slider:
                self.controls.slider.value = 3
            return "speed_change"
        return None

    def _dispatch(self, action: str):
        if action == "prev":
            self._goto_step(self.current_idx - 1)
        elif action == "next":
            self._goto_step(self.current_idx + 1)
        elif action == "beginning":
            self.animations.clear_all()
            self._goto_step(0)
        elif action == "end":
            self.animations.clear_all()
            self._goto_step(self.engine.total_steps() - 1)
        elif action == "autoplay_toggle":
            playing = not self.controls.auto_playing
            self.controls.set_auto_state(playing)
            self._auto_timer = 0
        elif action == "toggle_info":
            self.info_visible = not self.info_visible
        elif action == "quit":
            pygame.event.post(pygame.event.Event(pygame.QUIT))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="三国杀 Round-Table Replay Viewer")
    parser.add_argument("jsonl_path", nargs="?", help="Path to game.jsonl")
    args = parser.parse_args()

    jsonl_path = args.jsonl_path
    if not jsonl_path:
        logs_base = Path(__file__).parent.parent / "logs"
        candidates = []
        for game_dir_name in ("sanguosha", "sgs"):
            game_dir = logs_base / game_dir_name
            if game_dir.is_dir():
                for session_dir in sorted(game_dir.iterdir(), reverse=True):
                    jl = session_dir / "game.jsonl"
                    if jl.is_file():
                        candidates.append((session_dir, jl))
                        break
        if candidates:
            candidates.sort(key=lambda x: x[0].name, reverse=True)
            jsonl_path = str(candidates[0][1])
            print(f"Auto-detected log: {jsonl_path}")

    if not jsonl_path:
        print("Error: No game log found.")
        print("Usage: python -m sgs_viewer [path/to/game.jsonl]")
        sys.exit(1)

    viewer = GameViewer(jsonl_path)
    viewer.run()


if __name__ == "__main__":
    main()
