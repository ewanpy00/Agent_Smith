"""Sandbox executor: runs code with persistent state and enforces the SandboxConfig."""
from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from models import SandboxConfig
from agent_smith.sandbox.worker import worker_main

MAX_OUTPUT_CHARS = 10_000   # captured output beyond this is dropped and flagged
STARTUP_TIMEOUT = 15.0      # seconds to wait for a freshly spawned worker
MEMORY_POLL_INTERVAL = 0.1  # seconds between RSS checks of the worker


@dataclass
class ExecutionResult:
    """Outcome of one execute() call, always explicit so the LLM never guesses."""
    output: str = ""                       # captured stdout/stderr or error message
    error: Optional[str] = None            # raised exception, if any
    timed_out: bool = False                # execution hit the timeout, output is partial
    truncated: bool = False                # output was cut because of size limits
    final_answer: Optional[str] = None     # set when the code called final_answer(...)


def _rss_mb(pid: int) -> Optional[float]:
    """Resident memory of a process in MB (Linux: /proc, macOS: ps). None if unknown."""
    try:
        with open(f"/proc/{pid}/statm") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)
    except (OSError, ValueError, IndexError):
        pass
    try:
        out = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True, timeout=2
        ).stdout.strip()
        return int(out) / 1024 if out else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class Sandbox:
    """Execution boundary between LLM-generated code and the real world.

    - Variables persist between execute() calls (REPL semantics).
    - `tools` (MCP wrappers) and final_answer are injected into the namespace.
    - final_answer is built into the sandbox and is NOT an MCP tool.
    - KeyboardInterrupt and SystemExit must not be swallowed.
    - Design decision to defend at review: run code in a separate process so it
      can be force-killed on timeout and its memory limited.

    The code runs in a spawned worker process (worker.py). Tools are *not* run there:
    the worker only holds proxies that ask this process to call the real function, so
    tool actions happen outside the sandbox and do not count against its timeout.
    """

    def __init__(
        self,
        config: SandboxConfig,
        tools: Optional[Dict[str, Callable[..., Any]]] = None,
    ) -> None:
        self._config = config
        self._tools = dict(tools or {})
        self._ctx = multiprocessing.get_context("spawn")
        self._proc: Optional[multiprocessing.process.BaseProcess] = None
        self._conn: Any = None
        self._start()

    # -- lifecycle ---------------------------------------------------------

    def _start(self) -> None:
        parent_conn, child_conn = self._ctx.Pipe(duplex=True)
        proc = self._ctx.Process(
            target=worker_main,
            args=(child_conn, self._config.model_dump(), list(self._tools)),
            daemon=True,
        )
        proc.start()
        child_conn.close()
        self._proc, self._conn = proc, parent_conn
        if not parent_conn.poll(STARTUP_TIMEOUT) or self._recv().get("type") != "ready":
            self._kill()
            raise RuntimeError("Sandbox worker failed to start")

    def _kill(self) -> None:
        if self._proc is not None:
            if self._proc.is_alive():
                self._proc.kill()
            self._proc.join(timeout=2)
        if self._conn is not None:
            self._conn.close()
        self._proc = self._conn = None

    def close(self) -> None:
        """Release the sandbox process and its resources."""
        if self._proc is not None and self._proc.is_alive():
            try:
                self._send({"type": "close"})
                self._proc.join(timeout=1)
            except (OSError, ValueError):
                pass
        self._kill()

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- messaging ---------------------------------------------------------

    def _send(self, message: Dict[str, Any]) -> None:
        self._conn.send_bytes(json.dumps(message, default=str).encode())

    def _recv(self) -> Dict[str, Any]:
        return json.loads(self._conn.recv_bytes())

    def _call_tool(self, request: Dict[str, Any]) -> Dict[str, Any]:
        fn = self._tools.get(request["name"])
        if fn is None:
            return {"type": "tool_result", "ok": False, "error": f"unknown tool {request['name']!r}"}
        try:
            value = fn(*request.get("args", []), **request.get("kwargs", {}))
            return {"type": "tool_result", "ok": True, "value": value}
        except Exception as exc:  # tool failures become a RuntimeError inside the sandbox
            return {"type": "tool_result", "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # -- execution ---------------------------------------------------------

    def execute(self, code: str, *, echo_last_expr: bool = False) -> ExecutionResult:
        """Run `code` in the persistent namespace.

        echo_last_expr: print the value of a trailing expression (REPL behaviour).
        """
        if self._proc is None or not self._proc.is_alive():
            self._kill()
            self._start()

        limit = self._config.max_execution_time_seconds
        deadline = time.monotonic() + limit
        next_mem_check = time.monotonic() + MEMORY_POLL_INTERVAL
        chunks: List[str] = []
        size = 0
        truncated = False

        def partial() -> str:
            text = "".join(chunks)
            return text + "\n[output truncated]" if truncated else text

        try:
            self._send({"type": "exec", "code": code, "echo": echo_last_expr})
            while True:
                now = time.monotonic()
                if now >= deadline:
                    self._kill()
                    return ExecutionResult(
                        output=partial(), timed_out=True, truncated=truncated,
                        error=f"Execution timed out after {limit}s. The output above is partial. "
                              "The sandbox was restarted: all variables were lost.",
                    )
                if now >= next_mem_check:
                    next_mem_check = now + MEMORY_POLL_INTERVAL
                    rss = _rss_mb(self._proc.pid)
                    if rss is not None and rss > self._config.max_memory_mb:
                        self._kill()
                        return ExecutionResult(
                            output=partial(), truncated=truncated,
                            error=f"Memory limit exceeded ({self._config.max_memory_mb} MB). "
                                  "The sandbox was restarted: all variables were lost.",
                        )
                if not self._conn.poll(min(deadline - now, MEMORY_POLL_INTERVAL)):
                    continue

                try:
                    message = self._recv()
                except (EOFError, OSError):
                    exitcode = self._proc.exitcode if self._proc else None
                    self._kill()
                    return ExecutionResult(
                        output=partial(), truncated=truncated,
                        error=f"The sandbox process died unexpectedly (exit code {exitcode}), "
                              "probably out of memory. It was restarted: all variables were lost.",
                    )

                kind = message.get("type")
                if kind == "out":
                    room = MAX_OUTPUT_CHARS - size
                    data = message["data"]
                    if room > 0:
                        chunks.append(data[:room])
                        size += min(len(data), room)
                    if len(data) > room:
                        truncated = True
                elif kind == "tool":
                    started = time.monotonic()
                    self._send(self._call_tool(message))
                    deadline += time.monotonic() - started  # tool time is not sandbox time
                elif kind == "done":
                    return self._finish(message, partial(), truncated)
        except BaseException:
            # Ctrl+C / SystemExit in the parent: don't leave a runaway worker behind.
            self._kill()
            raise

    def _finish(self, message: Dict[str, Any], output: str, truncated: bool) -> ExecutionResult:
        propagate = message.get("propagate")
        if propagate:
            if propagate["type"] == "KeyboardInterrupt":
                raise KeyboardInterrupt()
            raise SystemExit(propagate.get("code"))
        return ExecutionResult(
            output=output,
            error=message.get("error"),
            truncated=truncated,
            final_answer=message.get("final_answer"),
        )
