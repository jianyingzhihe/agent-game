"""Arrow and panel animation system using tkinter after() scheduling."""

from dataclasses import dataclass, field
import math

ARROW_DURATION_MS = 620


@dataclass
class ArrowAnimation:
    """A single bezier-curve arrow from source to target position."""
    source_name: str
    target_name: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    color: tuple  # RGB color
    start_time_ms: int = 0
    duration_ms: int = ARROW_DURATION_MS
    tag: str = ""  # canvas tag for grouped deletion

    def progress(self, now_ms: int) -> float:
        """0.0 to 1.0, clamped."""
        if self.duration_ms <= 0:
            return 1.0
        p = (now_ms - self.start_time_ms) / self.duration_ms
        return max(0.0, min(1.0, p))

    def alpha_frac(self, now_ms: int) -> float:
        """Alpha fraction (0 to 1) with fade-out at the end."""
        p = self.progress(now_ms)
        if p < 0.1:
            return p / 0.1  # fade in
        if p > 0.75:
            return (1.0 - p) / 0.25  # fade out
        return 1.0

    def control_point(self) -> tuple[float, float]:
        """Compute a bezier control point offset from the midpoint."""
        mx = (self.start_x + self.end_x) / 2
        my = (self.start_y + self.end_y) / 2
        dx = self.end_x - self.start_x
        dy = self.end_y - self.start_y
        dist = math.hypot(dx, dy)
        if dist < 1:
            return mx, my
        # Perpendicular offset
        nx = -dy / dist
        ny = dx / dist
        offset = dist * 0.35
        return mx + nx * offset, my + ny * offset

    def point_at(self, t: float) -> tuple[float, float]:
        """Quadratic bezier point at t."""
        cx, cy = self.control_point()
        x = (1 - t) ** 2 * self.start_x + 2 * (1 - t) * t * cx + t ** 2 * self.end_x
        y = (1 - t) ** 2 * self.start_y + 2 * (1 - t) * t * cy + t ** 2 * self.end_y
        return x, y

    def tangent_at(self, t: float) -> tuple[float, float]:
        """Derivative of bezier at t, for arrow head angle."""
        cx, cy = self.control_point()
        dx = 2 * (1 - t) * (cx - self.start_x) + 2 * t * (self.end_x - cx)
        dy = 2 * (1 - t) * (cy - self.start_y) + 2 * t * (self.end_y - cy)
        return dx, dy


class AnimationEngine:
    """Manages active animations: arrows and panel flashes."""

    def __init__(self):
        self.arrows: list[ArrowAnimation] = []
        self._arrow_id_counter = 0
        # Panel flashes: player_name -> intensity (0..1, decaying)
        self.panel_flashes: dict[str, float] = {}
        self.turn_glow: float = 0.0  # pulse for turn player highlight

    def spawn_arrow(
        self,
        source_name: str,
        target_name: str,
        sx: float, sy: float,
        ex: float, ey: float,
        color: str,
        now_ms: int,
    ) -> ArrowAnimation:
        """Create a single arrow and add to active list."""
        self._arrow_id_counter += 1
        anim = ArrowAnimation(
            source_name=source_name,
            target_name=target_name,
            start_x=sx, start_y=sy,
            end_x=ex, end_y=ey,
            color=color,
            start_time_ms=now_ms,
            tag=f"arrow_{self._arrow_id_counter}",
        )
        self.arrows.append(anim)
        return anim

    def spawn_aoe(
        self,
        source: str,
        targets: list[str],
        positions: dict[str, tuple[float, float]],
        color: str,
        now_ms: int,
    ) -> list[ArrowAnimation]:
        """Spawn arrows from source to multiple targets simultaneously."""
        result = []
        sx, sy = positions.get(source, (0, 0))
        for tgt in targets:
            if tgt in positions:
                ex, ey = positions[tgt]
                anim = self.spawn_arrow(source, tgt, sx, sy, ex, ey, color, now_ms)
                result.append(anim)
        return result

    def flash_panel(self, player_name: str) -> None:
        """Trigger a brief red flash on a player panel (damage)."""
        self.panel_flashes[player_name] = 1.0

    def flash_heal(self, player_name: str) -> None:
        """Trigger a brief green flash on a player panel (heal)."""
        self.panel_flashes[f"heal_{player_name}"] = 1.0

    def update(self, dt_ms: int, now_ms: int = 0) -> None:
        """Update all animations: cull expired, decay flashes."""
        # Cull expired arrows
        self.arrows = [a for a in self.arrows if a.progress(now_ms) < 1.0]

        # Decay flashes
        decay = dt_ms / 400.0  # fade over ~400ms
        for key in list(self.panel_flashes):
            self.panel_flashes[key] -= decay
            if self.panel_flashes[key] <= 0:
                del self.panel_flashes[key]

        # Pulse turn glow
        self.turn_glow += dt_ms / 1500.0  # ~1.5 second cycle

    def clear_all(self) -> None:
        """Remove all active animations."""
        self.arrows.clear()
        self.panel_flashes.clear()

    @property
    def is_idle(self) -> bool:
        return len(self.arrows) == 0 and len(self.panel_flashes) == 0
