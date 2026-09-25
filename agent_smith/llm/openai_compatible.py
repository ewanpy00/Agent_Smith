"""Client for OpenAI-compatible chat-completions APIs (OpenRouter, Groq, Together, ...)."""
from __future__ import annotations

from typing import Dict, List, Optional

from agent_smith.llm.base import LLMClient, LLMResponse
from agent_smith.llm.key_pool import KeyPool


class OpenAICompatibleClient(LLMClient):
    """One class for every provider that speaks the /chat/completions protocol.

    A provider is just (base_url, KeyPool, model_name), so adding one needs no new code.
    """

    def __init__(self, base_url: str, model_name: str, keys: KeyPool, max_retries: int = 5) -> None:
        raise NotImplementedError

    def complete(
        self,
        messages: List[Dict[str, str]],
        stop: Optional[List[str]] = None,
    ) -> LLMResponse:
        raise NotImplementedError
