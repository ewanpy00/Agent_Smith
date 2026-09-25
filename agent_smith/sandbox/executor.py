"""Sandbox executor: runs code with persistent state and enforces the SandboxConfig."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from models import SandboxConfig


@dataclass
class ExecutionResult:
    """Outcome of one execute() call, always explicit so the LLM never guesses."""
    output: str = ""                       # captured stdout/stderr or error message
    error: Optional[str] = None            # raised exception, if any
    timed_out: bool = False                # execution hit the timeout, output is partial
    truncated: bool = False                # output was cut because of size limits
    final_answer: Optional[str] = None     # set when the code called final_answer(...)


class Sandbox:
    """Execution boundary between LLM-generated code and the real world.

    - Variables persist between execute() calls (REPL semantics).
    - `tools` (MCP wrappers) and final_answer are injected into the namespace.
    - final_answer is built into the sandbox and is NOT an MCP tool.
    - KeyboardInterrupt and SystemExit must not be swallowed.
    - Design decision to defend at review: run code in a separate process so it
      can be force-killed on timeout and its memory limited.
    """

    def __init__(
        self,
        config: SandboxConfig,
        tools: Optional[Dict[str, Callable[..., Any]]] = None,
    ) -> None:
        raise NotImplementedError

    def execute(self, code: str) -> ExecutionResult:
        raise NotImplementedError

    def close(self) -> None:
        """Release the sandbox process and its resources."""
        raise NotImplementedError
