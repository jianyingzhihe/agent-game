"""Codenames board — word grid and color assignments."""

import random
from typing import Dict, List, Tuple

# 200 common nouns for the word pool
WORD_POOL = [
    "apple", "bank", "bat", "bear", "bell", "belt", "bench", "berry", "bird", "block",
    "board", "bolt", "bomb", "bond", "book", "boot", "bowl", "box", "bread", "bridge",
    "brush", "bug", "button", "cake", "camel", "camp", "candle", "carpet", "carrot", "castle",
    "cat", "cell", "chain", "chair", "chest", "chicken", "chip", "circle", "clock", "cloud",
    "club", "coat", "code", "coin", "comet", "crane", "crown", "cycle", "dance", "desert",
    "diamond", "dice", "dinosaur", "dragon", "dress", "drill", "drum", "duck", "eagle", "engine",
    "eye", "fence", "field", "fire", "fish", "flag", "flute", "forest", "fork", "ghost",
    "giant", "glass", "glove", "gold", "grass", "hammer", "hawk", "helmet", "horn", "horse",
    "hospital", "hotel", "ice", "island", "jacket", "jewel", "key", "king", "knife", "knight",
    "lamp", "leaf", "lemon", "light", "lion", "lizard", "lock", "mammoth", "maple", "marble",
    "mask", "microscope", "mill", "mine", "mirror", "moon", "mountain", "mouse", "needle", "nest",
    "net", "ninja", "note", "nut", "octopus", "oil", "opera", "orange", "organ", "palm",
    "pan", "paper", "park", "penguin", "pepper", "piano", "pie", "pilot", "pin", "pipe",
    "pirate", "pitch", "plane", "plate", "point", "pole", "pool", "pound", "press", "princess",
    "pumpkin", "pupil", "pyramid", "queen", "rabbit", "racket", "rainbow", "ring", "robot", "rocket",
    "rope", "rose", "ruler", "satellite", "school", "screen", "shadow", "shark", "shell", "ship",
    "shoe", "skull", "snake", "snow", "soldier", "spider", "spring", "spy", "square", "star",
    "stick", "storm", "straw", "stream", "switch", "table", "temple", "theater", "thief", "tower",
    "track", "train", "triangle", "trunk", "tube", "turtle", "vampire", "virus", "watch", "water",
    "wave", "web", "whale", "whip", "wind", "wing", "witch", "worm", "yard", "zebra",
]


class CodenamesBoard:
    """A 5x5 Codenames board with hidden color assignments."""

    COLORS = ["red", "blue", "neutral", "assassin"]

    def __init__(self, seed: int = None):
        if seed is not None:
            random.seed(seed)
        self.words: List[str] = random.sample(WORD_POOL, 25)
        random.shuffle(self.words)

        # Assign colors: 8 red, 8 blue, 8 neutral, 1 assassin (first team gets 9)
        first_team_extra = random.choice([0, 1])  # 0=red starts, 1=blue starts
        if first_team_extra == 0:
            colors = ["red"] * 9 + ["blue"] * 8 + ["neutral"] * 7 + ["assassin"]
        else:
            colors = ["red"] * 8 + ["blue"] * 9 + ["neutral"] * 7 + ["assassin"]
        random.shuffle(colors)

        self.grid: Dict[str, str] = {}  # word → color
        for word, color in zip(self.words, colors):
            self.grid[word] = color

        self.revealed: Dict[str, bool] = {w: False for w in self.words}

        self.red_remaining = sum(1 for c in colors if c == "red")
        self.blue_remaining = sum(1 for c in colors if c == "blue")

        # First team is the one with 9 words
        self.current_team = "red" if colors.count("red") == 9 else "blue"
        self.starting_team = self.current_team

    def get_color(self, word: str) -> str:
        return self.grid.get(word.lower(), "neutral")

    def reveal(self, word: str) -> str:
        """Reveal a word. Returns its color."""
        w = word.lower().strip()
        if w not in self.grid:
            return "invalid"
        self.revealed[w] = True
        color = self.grid[w]
        if color == "red":
            self.red_remaining -= 1
        elif color == "blue":
            self.blue_remaining -= 1
        return color

    def is_game_over(self) -> Tuple[bool, str]:
        """Check win/loss. Returns (is_over, winner_or_empty)."""
        if self.red_remaining == 0:
            return True, "red"
        if self.blue_remaining == 0:
            return True, "blue"
        return False, ""

    def display_for_spymaster(self) -> str:
        """Show the full board with colors (for spymaster only)."""
        lines = []
        for i in range(0, 25, 5):
            row_words = self.words[i:i+5]
            row = []
            for w in row_words:
                c = self.grid[w]
                r = "✓" if self.revealed[w] else " "
                row.append(f"[{r}]{w}({c})")
            lines.append("  " + " | ".join(row))
        return "\n".join(lines)

    def display_for_guesser(self) -> str:
        """Show the board without colors (for guessers)."""
        lines = []
        for i in range(0, 25, 5):
            row_words = self.words[i:i+5]
            row = []
            for j, w in enumerate(row_words):
                idx = i + j + 1
                if self.revealed[w]:
                    c = self.grid[w]
                    icon = {"red": "R", "blue": "B", "neutral": "N", "assassin": "X"}[c]
                    row.append(f"[{icon}]{w}")
                else:
                    row.append(f"[{idx:02d}]{w}")
            lines.append("  " + " | ".join(row))
        return "\n".join(lines)

    def unrevealed_words(self) -> List[str]:
        return [w for w in self.words if not self.revealed[w]]
