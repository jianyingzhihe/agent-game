"""Three Kingdoms Kill game runner."""

from core.game_launcher import build_models_and_names, check_models, env
from core.utils import Colors

from .engine import SanguoshaEngine
from .player import SanguoshaPlayer

DEFAULT_PLAYER_CONFIG = "deepseek:1,dashscope:qwen-max:1,dashscope:kimi-k2.6:1,dashscope:glm-5.1:1"


def run(logger, max_rounds, verbose):
    print(Colors.bold("\n  Three Kingdoms Kill (三国杀)"))
    cfg = env("SGS_PLAYER_CONFIG", DEFAULT_PLAYER_CONFIG)
    game_mode = env("SGS_MODE", "free_for_all").lower()
    if game_mode not in ("free_for_all", "identity"):
        print(Colors.color(f"  Invalid SGS_MODE '{game_mode}', using free_for_all", Colors.YELLOW))
        game_mode = "free_for_all"

    entries = build_models_and_names(cfg)

    if len(entries) < 2:
        print(Colors.color("  Need at least 2 players", Colors.RED))
        return

    entries = check_models(entries)
    if len(entries) < 2:
        print(Colors.color("  Need at least 2 working players", Colors.RED))
        return

    players = [SanguoshaPlayer(n, m, p) for n, m, p in entries]
    for p in players:
        print(f"  {p.name:12s} [{p.model.model_name}]")
    mode_label = "身份模式" if game_mode == "identity" else "混战模式"
    print(Colors.dim(f"  游戏模式: {mode_label}"))

    engine = SanguoshaEngine(players, logger=logger, game_mode=game_mode)
    engine.run(max_rounds=max_rounds, verbose=verbose)
