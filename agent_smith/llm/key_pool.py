"""Multiple API keys per provider with rotation (mandatory, subject V.6.1)."""
from __future__ import annotations

from typing import List


class KeyPool:
    """Round-robin pool of API keys that skips keys hitting rate limits/quotas."""

    def __init__(self, keys: List[str]) -> None:
        raise NotImplementedError

    @classmethod
    def from_env(cls, env_var: str) -> "KeyPool":
        """Read comma-separated keys from an environment variable (never hardcode keys)."""
        raise NotImplementedError

    def next_key(self) -> str:
        """Return the next usable key; raise when every key is exhausted."""
        raise NotImplementedError

    def mark_exhausted(self, key: str) -> None:
        """Take a key out of rotation (quota exhausted or rate limited)."""
        raise NotImplementedError
