"""Model factory - create model instances by provider name.

Supports a growing list of providers. To add a new one:
1. If it's OpenAI-compatible, just add an entry to PROVIDER_CONFIGS
2. If it needs a custom client, create a new class and add it here
"""

from typing import Dict, List

from .base import ModelInterface
from .gemini_model import GeminiModel
from .openai_compat import OpenAICompatibleModel

# Provider configurations for OpenAI-compatible APIs
# Each entry: {base_url, default_model}
PROVIDER_CONFIGS: Dict[str, Dict[str, str]] = {
    "openai": {
        "base_url": "",
        "default_model": "gpt-4o",
        "description": "OpenAI GPT models",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "description": "DeepSeek models",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-max",
        "description": "Alibaba Qwen (DashScope)",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "default_model": "glm-4-flash",
        "description": "Zhipu GLM models",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "moonshot-v1-8k",
        "description": "Moonshot Kimi models",
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "default_model": "deepseek-ai/DeepSeek-V3",
        "description": "SiliconFlow (multi-model)",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.1-70b-versatile",
        "description": "Groq fast inference",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "description": "Together AI",
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "default_model": "grok-2",
        "description": "xAI Grok models",
    },
    "doubao": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-seed-2-0-pro-260215",
        "description": "ByteDance Doubao (Volcano Engine Ark)",
    },
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-max",
        "description": "Aliyun DashScope — Qwen / Kimi / GLM / MiniMax 统一网关",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "openai/gpt-4o",
        "description": "OpenRouter (multi-model gateway)",
    },
}


def create_model(
    provider: str,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
    **kwargs,
) -> ModelInterface:
    """Create a model instance by provider name.

    Args:
        provider: Provider identifier ('openai', 'deepseek', 'gemini', 'qwen', etc.)
        api_key: API key for authentication
        model: Model name override (uses provider default if not specified)
        base_url: API base URL override
        **kwargs: Passed to the model constructor (temperature, max_tokens, etc.)

    Returns:
        A ModelInterface instance ready to use

    Raises:
        ValueError: If the provider is unknown

    Example:
        >>> deepseek = create_model("deepseek", api_key="sk-xxx")
        >>> gpt = create_model("openai", api_key="sk-xxx", model="gpt-4o")
        >>> gemini = create_model("gemini", api_key="xxx")
    """
    provider = provider.lower().strip()

    # -- Gemini (custom implementation) --
    if provider == "gemini":
        model_name = model or "gemini-2.0-flash"
        return GeminiModel(model_name=model_name, api_key=api_key, **kwargs)

    # -- OpenAI-compatible providers --
    if provider in PROVIDER_CONFIGS:
        config = PROVIDER_CONFIGS[provider]
        effective_base_url = base_url or config["base_url"] or None
        model_name = model or config["default_model"]
        return OpenAICompatibleModel(
            model_name=model_name,
            api_key=api_key,
            base_url=effective_base_url,
            **kwargs,
        )

    # -- Custom base_url (user-specified endpoint) --
    if base_url:
        return OpenAICompatibleModel(
            model_name=model or "custom-model",
            api_key=api_key,
            base_url=base_url,
            **kwargs,
        )

    raise ValueError(
        f"Unknown provider '{provider}'. "
        f"Available providers: {list(PROVIDER_CONFIGS.keys()) + ['gemini']}. "
        f"For custom providers, pass base_url."
    )


def list_providers() -> List[Dict[str, str]]:
    """List all available providers with their default models and descriptions."""
    result = []
    for name, config in PROVIDER_CONFIGS.items():
        result.append({
            "provider": name,
            "default_model": config["default_model"],
            "description": config["description"],
        })
    result.append({
        "provider": "gemini",
        "default_model": "gemini-2.0-flash",
        "description": "Google Gemini models",
    })
    return result
