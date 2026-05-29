"""Google Gemini model implementation."""

from typing import Dict, List, Tuple

from .base import ModelInterface


class GeminiModel(ModelInterface):
    """Model interface for Google Gemini models.

    Usage:
        model = GeminiModel(model_name="gemini-2.0-flash", api_key="...")
        response = model.chat([
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello!"}
        ])
    """

    def __init__(
        self,
        model_name: str = "gemini-2.0-flash",
        api_key: str = "",
        default_temperature: float = 0.8,
        default_max_tokens: int = 1024,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        import google.generativeai as genai  # lazy import

        self._model_name = model_name
        self._default_temperature = temperature if temperature is not None else default_temperature
        self._default_max_tokens = max_tokens if max_tokens is not None else default_max_tokens
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Tuple[str, str]:
        """Send messages and get Gemini's response. Returns (thinking, content)."""
        temperature = kwargs.get("temperature", self._default_temperature)
        max_tokens = kwargs.get("max_tokens", self._default_max_tokens)

        try:
            system_parts = []
            history = []
            for msg in messages[:-1]:
                role = msg["role"]
                content = msg["content"]
                if role == "system":
                    system_parts.append(content)
                elif role == "user":
                    history.append({"role": "user", "parts": [content]})
                elif role == "assistant":
                    history.append({"role": "model", "parts": [content]})

            last_msg = messages[-1]
            user_content = last_msg["content"]
            if system_parts:
                user_content = "\n\n".join(system_parts) + "\n\n---\n\n" + user_content

            if history:
                chat = self.model.start_chat(history=history)
                response = chat.send_message(
                    user_content,
                    generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
                )
            else:
                response = self.model.generate_content(
                    user_content,
                    generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
                )

            text = response.text if response.text else ""
            return ("", text)

        except Exception as e:
            return ("", f"[ERROR: {type(e).__name__}: {str(e)}]")

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def provider_name(self) -> str:
        return "Gemini"
