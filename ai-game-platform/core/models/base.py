"""Abstract base class for all model interfaces."""

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple


class ModelInterface(ABC):
    """Unified interface for all LLM models.

    All model implementations must implement:
    - chat(): send messages, return (thinking, content) tuple
    - model_name: property returning the model identifier
    """

    @abstractmethod
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> Tuple[str, str]:
        """Send a conversation to the model.

        Args:
            messages: List of {"role": "...", "content": "..."} dicts
            **kwargs: Provider-specific options (temperature, max_tokens, etc.)

        Returns:
            (thinking, content) tuple.
            - thinking: model's internal reasoning ("" if not supported)
            - content: the model's text response
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model identifier string."""
        pass

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return self.__class__.__name__

    def __repr__(self) -> str:
        return f"{self.provider_name}({self.model_name})"
