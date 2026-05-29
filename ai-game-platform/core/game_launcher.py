"""Shared game launch helpers.

Keep game-specific startup logic in each game's own folder while reusing
common model/config/bootstrap behavior from this module.
"""

import itertools
import os
import sys
from pathlib import Path

import yaml

from core.models.factory import create_model
from core.utils import Colors


# ── Model Registry ─────────────────────────────────────────────────────────
# Loaded once from config/models.yaml at first access.

_MODEL_REGISTRY: dict | None = None


def _load_model_registry() -> dict:
    """Load model registry from config/models.yaml, cached in memory."""
    global _MODEL_REGISTRY
    if _MODEL_REGISTRY is not None:
        return _MODEL_REGISTRY

    config_path = Path(__file__).parent.parent / "config" / "models.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            _MODEL_REGISTRY = yaml.safe_load(f) or {}
    else:
        _MODEL_REGISTRY = {"providers": {}, "presets": {}}
    return _MODEL_REGISTRY


def _get_provider_config(provider: str) -> dict | None:
    """Get provider config from registry, or None if not found."""
    registry = _load_model_registry()
    return registry.get("providers", {}).get(provider.lower())


def _get_model_default(provider_cfg: dict | None) -> str:
    """Return the default model name from a provider config."""
    if not provider_cfg:
        return ""
    models = provider_cfg.get("models", [])
    for m in models:
        if m.get("default"):
            return m["name"]
    return models[0]["name"] if models else ""


# ── Environment helpers ────────────────────────────────────────────────────


def env(key: str, default: str = "") -> str:
    val = os.getenv(key, default)
    return val.strip().strip('"').strip("'") if val else default


def env_bool(key: str, default: bool = True) -> bool:
    return env(key, str(default)).lower() in ("true", "1", "yes", "on")


# ── Model building ─────────────────────────────────────────────────────────


def build_model(provider: str, model_name: str = ""):
    """Create a model instance.

    Resolution order for model name:
      1. Explicit `model_name` argument
      2. {PROVIDER}_MODEL env var
      3. Default model from config/models.yaml
      4. Factory built-in default

    Resolution order for base URL:
      1. {PROVIDER}_BASE_URL env var
      2. base_url from config/models.yaml
      3. Factory built-in default
    """
    key = env(f"{provider}_KEY")
    if not key:
        return None

    provider_cfg = _get_provider_config(provider)

    # Resolve model name
    effective_model = model_name or env(f"{provider}_MODEL")
    if not effective_model:
        effective_model = _get_model_default(provider_cfg)

    # Resolve base URL
    base_url = env(f"{provider}_BASE_URL")
    if not base_url and provider_cfg:
        base_url = provider_cfg.get("base_url", "")

    temp = float(env("MODEL_TEMPERATURE", "0.8"))
    max_tok = int(env("MODEL_MAX_TOKENS", "1024"))
    timeout = float(env(f"{provider}_TIMEOUT_SECONDS",
                        env("MODEL_TIMEOUT_SECONDS", "120")))
    kwargs = {"temperature": temp, "max_tokens": max_tok, "timeout": timeout}
    if effective_model:
        kwargs["model"] = effective_model
    if base_url:
        kwargs["base_url"] = base_url
    return create_model(provider, api_key=key, **kwargs)


# ── Player config parsing ──────────────────────────────────────────────────


def parse_player_config(config_str: str) -> list:
    """Parse a player config string into (provider, count, model_name) tuples.

    Formats:
      provider:count              → default model
      provider:model_name:count   → specific model
      @preset_name               → load from config/models.yaml presets

    Examples:
      "deepseek:2,dashscope:qwen-max:1"
      "@sgs_8p_freeforall"
    """
    # Resolve preset
    resolved = config_str
    if config_str.startswith("@"):
        registry = _load_model_registry()
        preset_name = config_str[1:]
        presets = registry.get("presets", {})
        resolved = presets.get(preset_name, "")
        if not resolved:
            print(Colors.color(
                f"  [WARN] Preset '{preset_name}' not found in models.yaml", Colors.YELLOW))
            return []

    result = []
    for part in resolved.split(","):
        part = part.strip()
        if not part:
            continue
        pieces = part.split(":")
        provider = pieces[0].strip().upper()
        if len(pieces) == 2:
            count = int(pieces[1].strip())
            model_name = ""
        elif len(pieces) >= 3:
            model_name = pieces[1].strip()
            count = int(pieces[2].strip())
        else:
            count = 1
            model_name = ""
        result.append((provider, count, model_name))
    return result


def auto_detect_players() -> list:
    """Auto-detect players from all configured providers that have keys."""
    all_p = [
        "DEEPSEEK", "OPENAI", "GEMINI", "QWEN", "ZHIPU", "MOONSHOT", "GROQ",
        "SILICONFLOW", "DOUBAO", "DASHSCOPE", "XAI", "OPENROUTER",
    ]
    return [(p, 2, "") for p in all_p if env(f"{p}_KEY")]


def get_model_assignments(config_override: str = ""):
    """Get model assignments from config override or env var."""
    cfg = config_override or env("PLAYER_CONFIG", "")
    if cfg:
        return parse_player_config(cfg)
    return auto_detect_players()


# ── Model listing ──────────────────────────────────────────────────────────


def list_available_models() -> None:
    """Print all models from the registry with availability indicators."""
    registry = _load_model_registry()
    providers = registry.get("providers", {})
    presets = registry.get("presets", {})

    if not providers:
        print(Colors.color("  No model registry found at config/models.yaml", Colors.YELLOW))
        return

    print(Colors.bold("\n  ====== Available Models ======\n"))

    for prov_name, prov_cfg in sorted(providers.items()):
        desc = prov_cfg.get("description", prov_name)
        base_url = prov_cfg.get("base_url", "(custom)")
        api_key_env = prov_cfg.get("api_key_env", "")
        has_key = bool(env(api_key_env))
        status = Colors.color("[OK]", Colors.GREEN) if has_key else Colors.color("[  ]", Colors.DIM)
        print(f"  {status}  {Colors.bold(prov_name):20s} {Colors.dim(base_url)}")
        print(f"           {desc}")
        for m in prov_cfg.get("models", []):
            flags = []
            if m.get("default"):
                flags.append("default")
            if m.get("latest"):
                flags.append("latest")
            flag_str = f" ({', '.join(flags)})" if flags else ""
            note_str = f" -- {m['note']}" if m.get("note") else ""
            print(f"      {m['name']:32s} {m['label']}{flag_str}{note_str}")
        print()

    if presets:
        print(Colors.bold("  Presets:"))
        for name, value in presets.items():
            count = len(value.split(","))
            print(f"    {'@' + name:30s} -> {count} players")
        print()


# ── Player builder ─────────────────────────────────────────────────────────


PERSONAS = [
    "You are a logical and analytical thinker.",
    "You trust your gut instincts and act on intuition.",
    "You are aggressive and quick to take initiative.",
    "You are cautious and prefer to observe.",
    "You are diplomatic and try to build consensus.",
    "You are quiet but sharply observant.",
    "You are charismatic and persuasive.",
    "You are skeptical and question everything.",
    "You are unpredictable and prone to sudden changes.",
    "You play the long game, patient and strategic.",
]

NAME_POOL = [
    "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank",
    "Grace", "Henry", "Iris", "Jack", "Kate", "Leo",
]


def build_models_and_names(config_override: str = ""):
    """Parse config, build models, return [(name, model, persona), ...]."""
    assignments = get_model_assignments(config_override)
    if not assignments:
        print(Colors.color("\n  No API keys found! Check your .env file.", Colors.RED))
        sys.exit(1)

    name_iter = itertools.cycle(NAME_POOL)
    persona_iter = itertools.cycle(PERSONAS)
    result = []
    for provider, count, model_name in assignments:
        model = build_model(provider, model_name)
        if model is None:
            print(Colors.color(f"  [WARN] Skipping {provider}: no key", Colors.YELLOW))
            continue
        for _ in range(count):
            result.append((next(name_iter), model, next(persona_iter)))
    return result


def check_models(entries: list) -> list:
    """Probe each model with a quick OK check. Remove failed ones."""
    print(Colors.bold("\n  [CHECK] Checking model connectivity...\n"))
    ok, bad = [], []
    seen = {}
    for name, model, persona in entries:
        probe_key = (type(model).__name__, model.model_name)
        if probe_key in seen:
            passed, detail = seen[probe_key]
            if passed:
                ok.append((name, model, persona))
                print(
                    f"  {Colors.color('[OK]', Colors.GREEN)} {name:12s} "
                    f"{model.model_name} ({type(model).__name__})  {Colors.dim('[cached]')}"
                )
            else:
                bad.append((name, detail))
                print(
                    f"  {Colors.color('[FAIL]', Colors.RED)} {name:12s} "
                    f"{model.model_name} - {str(detail)[:80]}"
                )
            continue

        print(f"  {Colors.dim(f'-> probing {name} / {model.model_name} ...')}")
        try:
            _, resp = model.chat([{"role": "user", "content": "Say exactly: OK"}])
            if "ERROR:" in resp[:20] or not resp.strip():
                raise RuntimeError(resp[:80])
            ok.append((name, model, persona))
            seen[probe_key] = (True, "ok")
            print(f"  {Colors.color('[OK]', Colors.GREEN)} {name:12s} {model.model_name} ({type(model).__name__})")
        except Exception as e:
            bad.append((name, str(e)))
            seen[probe_key] = (False, str(e))
            print(f"  {Colors.color('[FAIL]', Colors.RED)} {name:12s} {model.model_name} - {str(e)[:80]}")

    if bad:
        print(f"\n  {Colors.color(f'[WARN] {len(bad)} model(s) failed, removed from game.', Colors.YELLOW)}")
    if len(ok) < 2:
        print(Colors.color("\n  Not enough working models to play.", Colors.RED))
        sys.exit(1)
    return ok


def print_players(players):
    print("  Players:")
    for p in players:
        label = f"{p.model.model_name}"
        print(f"    {Colors.bold(p.name):14s} {Colors.dim(label):30s} {p.persona[:50]}")
    print()
