"""Provider-agnostic LLM interface (subject IV.2, V.6: switch providers without refactoring)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional


class LLMError(Exception):
    """Raised when the LLM call fails for good (all retries and keys exhausted)."""


@dataclass
class LLMResponse:
    """One completed LLM call; the fields feed StepMetrics."""
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    retries: int
    model_name: str
    api_url: str


class LLMClient(ABC):
    """What the agent loop needs from any provider."""

    @abstractmethod
    def complete(
        self,
        messages: List[Dict[str, str]],
        stop: Optional[List[str]] = None,
    ) -> LLMResponse:
        """Send chat messages and return the response.

        `stop` carries sequences such as "<end_code>" so the model does not
        hallucinate tool output after a code block (subject V.6).
        Must retry on rate limits/timeouts and rotate keys; the number of
        retries goes into LLMResponse.retries.
        """
