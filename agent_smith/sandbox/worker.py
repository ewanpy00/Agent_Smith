"""Sandbox worker: the separate process in which LLM-generated code actually runs.

Protocol with the parent (executor.py): JSON messages over a pipe. JSON and not
pickle on purpose: the parent must never unpickle bytes produced by sandboxed code.

parent -> worker   {"type": "exec", "code": str, "echo": bool}
                   {"type": "tool_result", "ok": bool, "value"|"error": ...}
                   {"type": "close"}
worker -> parent   {"type": "ready"}
                   {"type": "out", "data": str}              (streamed stdout/stderr)
                   {"type": "tool", "name", "args", "kwargs"}  (MCP call, run by the parent)
                   {"type": "done", "error", "final_answer", "propagate"}
"""
from __future__ import annotations

import ast
import json
import os
import sys
import traceback
from multiprocessing.connection import Connection
from typing import Any, Dict, List, Optional

from agent_smith.sandbox import restrictions

FILENAME = "<sandbox>"


class FinalAnswer(BaseException):
    """Raised by final_answer() to stop the running code.

    BaseException so that `except Exception:` in generated code cannot swallow it.
    """


class _Channel:
    def __init__(self, conn: Connection) -> None:
        self._conn = conn

    def send(self, message: Dict[str, Any]) -> None:
        self._conn.send_bytes(json.dumps(message, default=str).encode())

    def recv(self) -> Dict[str, Any]:
        return json.loads(self._conn.recv_bytes())


class _Stream:
    """Replacement for sys.stdout/sys.stderr: forwards writes to the parent immediately,
    so output is not lost if the process has to be killed on timeout."""

    def __init__(self, channel: _Channel) -> None:
        self._channel = channel

    def write(self, text: str) -> int:
        if text:
            self._channel.send({"type": "out", "data": text})
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def _format_error(exc: BaseException, code: str) -> str:
    """Traceback limited to the generated code (worker internals are not the LLM's business)."""
    source = code.splitlines()
    lines: List[str] = []
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename == FILENAME]
    if frames:
        lines.append("Traceback (most recent call last):")
        for frame in frames:
            lines.append(f'  File "{FILENAME}", line {frame.lineno}, in {frame.name}')
            if frame.lineno and 0 < frame.lineno <= len(source):
                lines.append(f"    {source[frame.lineno - 1].strip()}")
    lines.append("".join(traceback.format_exception_only(type(exc), exc)).rstrip())
    return "\n".join(lines)


def _make_tool(channel: _Channel, name: str):
    def call(*args: Any, **kwargs: Any) -> Any:
        channel.send({"type": "tool", "name": name, "args": list(args), "kwargs": kwargs})
        reply = channel.recv()
        if reply.get("ok"):
            return reply.get("value")
        raise RuntimeError(f"Tool '{name}' failed: {reply.get('error')}")

    call.__name__ = name
    return call


def _run(code: str, echo: bool, namespace: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute one code snippet in the persistent namespace and describe the outcome."""
    done: Dict[str, Any] = {"type": "done", "error": None, "final_answer": None, "propagate": None}
    try:
        tree = ast.parse(code, FILENAME, "exec")
        restrictions.validate_ast(tree)
        last = None
        if echo and tree.body and isinstance(tree.body[-1], ast.Expr):
            last = ast.Expression(tree.body.pop().value)
        body = compile(tree, FILENAME, "exec")
        last_code = compile(last, FILENAME, "eval") if last is not None else None
    except SyntaxError as exc:
        done["error"] = _format_error(exc, code)
        return done
    except PermissionError as exc:
        done["error"] = f"PermissionError: {exc}"
        return done

    try:
        exec(body, namespace)
        if last_code is not None:
            value = eval(last_code, namespace)
            if value is not None:
                print(repr(value))
    except FinalAnswer:
        pass
    except (KeyboardInterrupt, SystemExit) as exc:
        done["propagate"] = {"type": type(exc).__name__, "code": getattr(exc, "code", None)}
    except BaseException as exc:
        done["error"] = _format_error(exc, code)
    done["final_answer"] = state["final_answer"]
    state["final_answer"] = None
    return done


def worker_main(conn: Connection, config: Dict[str, Any], tool_names: List[str]) -> None:
    """Entry point of the worker process."""
    channel = _Channel(conn)

    os.environ.clear()
    restrictions.apply_memory_limit(config["max_memory_mb"])
    for directory in config["allowed_directories"]:
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError:
            pass
    restrictions.block_network()

    sys.stdout = sys.stderr = _Stream(channel)

    state: Dict[str, Any] = {"final_answer": None}

    def final_answer(answer: Any) -> None:
        """Finish the task with `answer` (a string). Built into the sandbox, not an MCP tool."""
        state["final_answer"] = answer if isinstance(answer, str) else str(answer)
        raise FinalAnswer()

    namespace = restrictions.make_safe_builtins(config["allowed_directories"])
    namespace["__builtins__"]["__import__"] = restrictions.make_import_hook(config["authorized_imports"])
    namespace["__name__"] = "__sandbox__"
    namespace["final_answer"] = final_answer
    for name in tool_names:
        namespace[name] = _make_tool(channel, name)

    channel.send({"type": "ready"})
    while True:
        try:
            message = channel.recv()
        except (EOFError, OSError):
            return
        if message["type"] == "close":
            return
        if message["type"] == "exec":
            channel.send(_run(message["code"], bool(message.get("echo")), namespace, state))
