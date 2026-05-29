"""Constants, colors, font management, and skill/card mappings (Pygame version)."""

import pygame
from pathlib import Path

# pygame.init() must be called before pygame.font.Font works
pygame.init()

# ── Window ──
WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900
FPS = 60

# ── Hex-to-RGB helper ──
def _rgb(hex_color: str) -> tuple[int, int, int]:
    return int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)

# ── Colors ──
HEX = {
    "bg": "#111522",
    "panel_bg": "#1d2336",
    "panel_turn": "#25304a",
    "panel_dead": "#2b3140",
    "panel_border": "#56627f",
    "panel_highlight": "#7f8fb3",
    "text_primary": "#f3f5fb",
    "text_secondary": "#b2bad0",
    "hp_heart": "#d4455a",
    "hp_empty": "#555555",
    "skill_badge": "#2d3753",
    "card_sha": "#f06075",
    "card_shan": "#6ab8e0",
    "card_tao": "#4cd268",
    "card_spell": "#d4a84c",
    "card_wuxie": "#b070d8",
    "arrow_attack": "#f03c3c",
    "arrow_spell": "#f0b428",
    "arrow_aoe": "#f06428",
    "arrow_heal": "#3cdc64",
    "turn_glow": "#d4455a",
    "flash_damage": "#ff3333",
    "flash_heal": "#33ff33",
    "button_bg": "#d4455a",
    "button_hover": "#b8384a",
    "button_sec": "#444444",
    "slider_track": "#3c3c46",
    "slider_thumb": "#d4455a",
    "info_bg": "#171d2d",
    "divider": "#46516c",
    "action_label": "#ffcc44",
    "black": "#000000",
    "white": "#ffffff",
    "phase_bg": "#323250",
    # Identity colors
    "id_lord": "#f0d040",      # 主公 - gold
    "id_loyalist": "#4c8cf0",  # 忠臣 - blue
    "id_rebel": "#f04848",     # 反贼 - red
    "id_spy": "#8c4cf0",       # 内奸 - purple
    "id_hidden": "#6c6c78",   # ??? - grey
}

IDENTITY_COLORS = {
    "lord": "id_lord",
    "loyalist": "id_loyalist",
    "rebel": "id_rebel",
    "spy": "id_spy",
}

# Convert to RGB tuples
C = {k: _rgb(v) for k, v in HEX.items()}

# ── Skill mapping ──
SKILL_MAP = {
    "unlim": "咆哮", "swap": "武圣",
    "wound": "刚烈", "wound_draw": "刚烈",
    "steal": "反馈", "wound_steal": "反馈",
    "blood": "苦肉", "blood_draw": "苦肉",
    "empty": "空城", "empty_draw": "空城",
    "immune": "空城·守", "empty_immune": "空城·守",
}

SKILL_DESC = {
    "咆哮": "无限出杀",
    "武圣": "杀闪互通",
    "刚烈": "受伤摸2牌",
    "反馈": "受伤偷1牌",
    "苦肉": "扣1血摸2牌",
    "空城": "空手摸1牌",
    "空城·守": "空手免疫杀",
}

# ── Card category colors ──
CARD_COLORS = {
    "杀": "card_sha", "闪": "card_shan",
    "桃": "card_tao", "无懈可击": "card_wuxie", "无懈": "card_wuxie",
    "南蛮入侵": "card_spell", "万箭齐发": "card_spell",
    "无中生有": "card_spell", "过河拆桥": "card_spell",
    "顺手牵羊": "card_spell", "桃园结义": "card_spell",
}

# ── Action → arrow color ──
ACTION_ARROW_COLORS = {
    "sha": "arrow_attack",
    "spell_steal": "arrow_spell",
    "spell_dismantle": "arrow_spell",
    "spell_aoe": "arrow_aoe",
    "heal_aoe": "arrow_heal",
    "steal": "arrow_spell",
}

# ── Action type → display label ──
ACTION_LABELS = {
    "sha": "发动【杀】",
    "spell_steal": "发动【顺手牵羊】",
    "spell_dismantle": "发动【过河拆桥】",
    "spell_aoe_nanman": "发动【南蛮入侵】",
    "spell_aoe_wanjian": "发动【万箭齐发】",
    "spell_self_draw": "发动【无中生有】",
    "heal_self": "使用【桃】",
    "heal_aoe": "发动【桃园结义】",
    "skill_blood_draw": "发动【苦肉】",
    "respond_shan": "使用【闪】",
    "respond_sha": "使用【杀】响应",
    "end_turn": "结束回合",
    "pass_response": "不响应",
    "discard": "弃牌",
}

# ── Action type → skill flag (for notification) ──
SKILL_ACTIONS = {"skill_blood_draw"}  # actions that trigger skill notifications
# Passive skills are detected by their presence in player state, not by actions.

# ── Font management ──
def _find_cjk_font() -> str | None:
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyh.ttf",
        "C:/Windows/Fonts/SIMHEI.TTF",
        "C:/Windows/Fonts/SIMSUN.TTC",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    # Try sysfont as last resort
    return None


def _find_cjk_bold_font() -> str | None:
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/msyhbd.ttf",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/SIMHEI.TTF",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return _find_cjk_font()

_FONT_PATH = _find_cjk_font()
_FONT_BOLD_PATH = _find_cjk_bold_font()
FONT_PATH = _FONT_PATH  # exported for diagnostics
if _FONT_PATH:
    print(f"[sgs_viewer] Font: {Path(_FONT_PATH).name}")
else:
    print("[sgs_viewer] Font: SysFont fallback")

class Fonts:
    def __init__(self):
        self._font_path = _FONT_PATH
        self._bold_font_path = _FONT_BOLD_PATH
        # Pre-create all sizes
        self.name = self._load(30, bold=True)
        self.name_small = self._load(22, bold=True)
        self.hp = self._load(24, bold=True)
        self.skill = self._load(16, bold=True)
        self.skill_small = self._load(14, bold=True)
        self.card = self._load(15)
        self.card_small = self._load(13)
        self.action = self._load(17, bold=True)
        self.reason = self._load(14)
        self.info_title = self._load(17, bold=True)
        self.info_text = self._load(15)
        self.phase = self._load(16, bold=True)
        self.step = self._load(16)
        self.button = self._load(16, bold=True)
        self.dead = self._load(16)
        self.large = self._load(36, bold=True)
        self.notify = self._load(20, bold=True)  # skill notification
        self.avatar = self._load(30, bold=True)  # avatar initial char

    def _load(self, size, bold: bool = False):
        font_path = self._bold_font_path if bold and self._bold_font_path else self._font_path
        if font_path:
            try:
                return pygame.font.Font(font_path, size)
            except Exception:
                pass
        try:
            return pygame.font.SysFont("microsoftyaheiui", size, bold=bold)
        except Exception:
            try:
                return pygame.font.SysFont("microsoftyahei", size, bold=bold)
            except Exception:
                try:
                    return pygame.font.SysFont("simsun", size, bold=bold)
                except Exception:
                    return pygame.font.SysFont("arial", size, bold=bold)

    def render(self, font, text, color) -> pygame.Surface:
        """Render text, falling back to a box-char replacement if the font can't handle it."""
        try:
            return font.render(text, True, color)
        except Exception:
            # Font might not have the glyph; render as '?' for safety
            safe = ''.join(c if ord(c) < 128 else '?' for c in text)
            return font.render(safe, True, color)

FONTS = Fonts()


# ── Layout constants ──
PANEL_WIDTH = 260
PANEL_HEIGHT = 215
INFO_WIDTH = 330
CONTROL_HEIGHT = 60

# ── Model icon mapping (prefix → filename in data/icon/) ──
_ICON_DIR = Path(__file__).parent.parent / "data" / "icon"
_MODEL_ICON_MAP = {
    "deepseek": "deepseek.png",
    "qwen": "qwen.png",
    "kimi": "kimi.png",
    "glm": "glm.png",
    "minimax": "minimax.png",
    "doubao": "doubao.jpg",
    "claude": "claude.png",
    "openai": "openai.png",
    "gpt": "openai.png",
}
_MODEL_ICON_CACHE: dict[str, pygame.Surface | None] = {}

def get_model_icon(model_name: str) -> pygame.Surface | None:
    """Load and cache a model's icon. Returns None if no icon found."""
    model_lower = model_name.lower()
    if model_lower in _MODEL_ICON_CACHE:
        return _MODEL_ICON_CACHE[model_lower]

    icon = None
    for prefix, filename in _MODEL_ICON_MAP.items():
        if model_lower.startswith(prefix) or prefix in model_lower:
            path = _ICON_DIR / filename
            if path.exists():
                try:
                    img = pygame.image.load(str(path)).convert_alpha()
                    # Scale to avatar size (60x60, r=30)
                    icon = pygame.transform.smoothscale(img, (60, 60))
                except Exception:
                    icon = None
            break
    _MODEL_ICON_CACHE[model_lower] = icon
    return icon


# ── Helper: blend two RGB colors ──
def blend_rgb(c1: tuple, c2: tuple, f: float) -> tuple:
    return tuple(int(a + (b - a) * f) for a, b in zip(c1, c2))

def hex_to_rgb(hex_color: str) -> tuple:
    return _rgb(hex_color)
