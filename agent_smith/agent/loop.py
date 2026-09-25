"""The agent loop: Thought -> Code -> Observation (own implementation, no agent frameworks)."""
from __future__ import annotations

from agent_smith.agent.limits import Limits
from agent_smith.llm.base import LLMClient
from agent_smith.sandbox.executor import Sandbox
from models import SolutionOutput


class AgentLoop:
    """Orchestrator.

    One iteration: call the LLM (with stop sequences) -> extract code -> run it in
    the sandbox -> feed the observation back. Stops on final_answer(), on
    max_iterations, or when a token limit would be exceeded.

    Every abnormal situation must produce explicit feedback to the LLM: no code
    block, malformed block interpreted anyway, timeout with partial output,
    truncated tool output, syntax/lint error after an edit.
    Errors must be handled gracefully: a crash during evaluation is a failure.
    """

    def __init__(
        self,
        llm: LLMClient,
        sandbox: Sandbox,
        system_prompt: str,
        limits: Limits,
        benchmark: str,
        task_id: str,
    ) -> None:
        raise NotImplementedError

    def run(self, task_prompt: str) -> SolutionOutput:
        raise NotImplementedError
