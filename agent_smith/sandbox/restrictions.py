"""Security primitives of the sandbox, standard library only (no RestrictedPython)."""
from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any, Callable, Dict, List


def make_safe_builtins(allowed_directories: List[str]) -> Dict[str, Any]:
    """Builtins with dangerous ones removed or overridden (open, eval, exec, __import__, ...)."""

    safe = vars(builtins).copy()

    for name in [
        "eval", "exec", "compile",          # code execution
        "__import__",                        # replaced by make_import_hook
        "breakpoint", "input",              # debugger / blocking REPL
        "exit", "quit",                     # kill the sandbox worker process
        "globals", "locals", "vars", "dir", # namespace introspection → __builtins__ escape
        "memoryview", "bytearray", "object",# raw memory / base class access
        "getattr", "setattr", "delattr", "hasattr",  # attribute access → subclass traversal
        "type", "isinstance", "issubclass", "super", # class hierarchy → __subclasses__() escape
        "open",                             # file access without path check
    ]:
        safe.pop(name, None)
    original_open = builtins.open
    def safe_open(file, mode="r", *args, **kwargs):
        check_path_allowed(str(file), allowed_directories or [])
        return original_open(file, mode, *args, **kwargs)

    safe["open"] = safe_open
    return {"__builtins__": safe}


def make_import_hook(authorized_imports: List[str]) -> Callable[..., Any]:
    """Replacement for __import__ allowing only allowlisted modules.

    An entry like "collections.*" also permits submodules (collections.abc).
    """

    exact = set()
    wildcards = set()
    for enntry in authorized_imports:
        if enntry.endswith(".*"):
            wildcards.add(enntry[:-2])
        else:
            exact.add(enntry)

    original_import = builtins.__import__

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level != 0:
            raise ImportError(f"Relative imports are not allowed")

        top = name.split(".")[0]

        allowed = (
            name in exact
            or top in wildcards
            or any(name == w or name.startswith(w + ".") for w in wildcards)
        )
        if not allowed:
            raise ImportError(f"Import of '{name}' is not allowed")

        return original_import
    return safe_import


def check_path_allowed(path: str, allowed_directories: List[str]) -> None:
    """Raise PermissionError unless `path` resolves inside an allowed directory.

    Resolve symlinks and '..' first, otherwise the allowlist can be bypassed.
    """

    try:
        resolved = Path(path).resolve()
    except OSError:
        raise PermissionError(f"Cannot resolve path: {path}")

    for allowed in allowed_directories:
        allowed_resolved = Path(allowed).resolve()
        try:
            resolved.relative_to(allowed_resolved)
            return
        except ValueError:
            continue

    raise PermissionError(
        f"Access to {resolved!r} is denied. "
        f"Allowed directories: {allowed_directories}"
    )


def block_network() -> None:
    """Prevent any inbound/outbound network connection in the sandbox process."""
    raise NotImplementedError


def apply_memory_limit(max_memory_mb: int) -> None:
    """Limit process memory (e.g. resource.setrlimit) so runaway code is terminated."""
    raise NotImplementedError
