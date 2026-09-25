"""Collects per-step data and builds the SolutionOutput written to solution.json."""
from __future__ import annotations

from typing import Optional

from models import SolutionOutput, StepMetrics


class MetricsRecorder:
    """Records every step (LLM output, sandbox input/output, tokens, retries).

    solution.json is inspected to verify the data comes from real execution,
    so nothing here may be fabricated.
    """

    def __init__(self, task_id: str, benchmark: str, system_prompt: str) -> None:
        raise NotImplementedError

    def add_step(self, step: StepMetrics) -> None:
        raise NotImplementedError

    def build(self, success: bool, solution: str, error: Optional[str] = None) -> SolutionOutput:
        """Compute totals (iterations, requests, tokens, wall-clock time) and build the output."""
        raise NotImplementedError
