"""Hard limits per benchmark (subject VI.1). Token limits are cumulative across iterations."""
from __future__ import annotations

from pydantic import BaseModel


class Limits(BaseModel):
    max_iterations: int
    max_input_tokens: int
    max_output_tokens: int
    timeout_seconds: int


MBPP_LIMITS = Limits(max_iterations=10, max_input_tokens=6_000, max_output_tokens=1_500, timeout_seconds=120)
SWEBENCH_LIMITS = Limits(max_iterations=30, max_input_tokens=300_000, max_output_tokens=10_000, timeout_seconds=900)
