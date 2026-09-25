"""Security primitives of the sandbox, standard library only (no RestrictedPython)."""
from __future__ import annotations

from typing import Any, Callable, Dict, List


def make_safe_builtins() -> Dict[str, Any]:
    """Builtins with dangerous ones removed or overridden (open, eval, exec, __import__, ...)."""
    raise NotImplementedError


def make_import_hook(authorized_imports: List[str]) -> Callable[..., Any]:
    """Replacement for __import__ allowing only allowlisted modules.

    An entry like "collections.*" also permits submodules (collections.abc).
    """
    raise NotImplementedError


def check_path_allowed(path: str, allowed_directories: List[str]) -> None:
    """Raise PermissionError unless `path` resolves inside an allowed directory.

    Resolve symlinks and '..' first, otherwise the allowlist can be bypassed.
    """
    raise NotImplementedError


def block_network() -> None:
    """Prevent any inbound/outbound network connection in the sandbox process."""
    raise NotImplementedError


def apply_memory_limit(max_memory_mb: int) -> None:
    """Limit process memory (e.g. resource.setrlimit) so runaway code is terminated."""
    raise NotImplementedError
