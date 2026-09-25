"""System prompt construction (subject V.1, item 6)."""
from __future__ import annotations


def build_system_prompt(benchmark: str, sandbox_manual: str) -> str:
    """Compose the prompt: role, Thought/Code/Observation slots, the sandbox manual
    (tool docs), examples of effective reasoning loops, and how to finish with
    final_answer(...). The full text is stored in SolutionOutput.system_prompt.
    """
    raise NotImplementedError
