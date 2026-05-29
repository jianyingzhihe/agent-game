"""OpenAI-compatible model implementation.

Handles OpenAI, DeepSeek, Qwen, DashScope, Doubao, and any OpenAI-compatible API.
Auto-falls-back to streaming for models that require it.
"""

from typing import Dict, List, Optional, Tuple

import httpx
from openai import OpenAI

from .base import ModelInterface


class OpenAICompatibleModel(ModelInterface):
    """Model for OpenAI and OpenAI-compatible APIs.

    Returns (thinking, content) from chat(). For models with reasoning_content
    (MiniMax, DeepSeek-R1, etc.), thinking captures that. For standard models,
    thinking is "" and content is the response.
    """

    def __init__(
        self,
        model_name: str,
        api_key: str,
        base_url: Optional[str] = None,
        default_temperature: float = 0.8,
        default_max_tokens: int = 1024,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = 20.0,
        max_retries: int = 0,
    ):
        self._model_name = model_name
        self._default_temperature = temperature if temperature is not None else default_temperature
        self._default_max_tokens = max_tokens if max_tokens is not None else default_max_tokens

        client_kwargs = {"api_key": api_key, "max_retries": max_retries}
        if base_url:
            client_kwargs["base_url"] = base_url
        if timeout is not None and timeout > 0:
            # Use a stricter read timeout so slow/half-stalled streams fail
            # promptly instead of looking like the game engine is frozen.
            client_kwargs["timeout"] = httpx.Timeout(
                connect=min(timeout, 10.0),
                read=timeout,
                write=min(timeout, 20.0),
                pool=min(timeout, 10.0),
            )
        self.client = OpenAI(**client_kwargs)

    def _prefers_streaming(self) -> bool:
        """Reasoning-style models are much more responsive in streaming mode."""
        model = self._model_name.lower()
        stream_first_markers = (
            "reasoner",
            "deepseek-v4-pro",
        )
        return any(marker in model for marker in stream_first_markers)

    def _run_nonstream(self, params: Dict) -> Tuple[str, str]:
        response = self.client.chat.completions.create(**params)
        msg = response.choices[0].message
        thinking = getattr(msg, "reasoning_content", "") or ""
        content = msg.content or ""
        return (thinking, content)

    def _run_stream(self, params: Dict) -> Tuple[str, str]:
        stream_params = dict(params)
        stream_params["stream"] = True
        stream = self.client.chat.completions.create(**stream_params)
        thinking_chunks = []
        content_chunks = []
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    thinking_chunks.append(delta.reasoning_content)
                if delta.content:
                    content_chunks.append(delta.content)
        thinking = "".join(thinking_chunks)
        content = "".join(content_chunks)
        if content:
            return (thinking, content)
        if thinking:
            return ("", thinking)
        return ("", "[ERROR: empty streamed response]")

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Tuple[str, str]:
        """Send messages, return (thinking, content)."""
        # Only pass params that were explicitly set
        params = {"model": self._model_name, "messages": messages}
        if "temperature" in kwargs:
            params["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            params["max_tokens"] = kwargs["max_tokens"]

        first, second = (
            (self._run_stream, self._run_nonstream)
            if self._prefers_streaming()
            else (self._run_nonstream, self._run_stream)
        )

        first_err = None
        try:
            return first(params)
        except Exception as e:
            first_err = e

        try:
            return second(params)
        except Exception as e:
            first_name = "stream" if first is self._run_stream else "non-stream"
            second_name = "non-stream" if first is self._run_stream else "stream"
            return ("", f"[ERROR: {first_name}={first_err}; {second_name}={type(e).__name__}: {e}]")

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def provider_name(self) -> str:
        return "OpenAICompat"
