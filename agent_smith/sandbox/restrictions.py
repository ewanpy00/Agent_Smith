"""Security primitives of the sandbox, standard library only (no RestrictedPython).

These are *language-level* layers (defence in depth). The real boundary is the
separate process in executor.py: it can be killed, memory-limited and has no
secrets. Never rely on the layers below alone.
"""
from __future__ import annotations

import ast
import builtins
import os
import types
from pathlib import Path
from typing import Any, Callable, Dict, List

# Attributes that give access to interpreter internals (class hierarchy walking,
# function globals, frames). `().__class__.__bases__[0].__subclasses__()` is the
# classic way out of a builtins-only jail, so we reject these names statically.
BLOCKED_ATTRS = frozenset({
    "__class__", "__bases__", "__base__", "__mro__", "__subclasses__",
    "__globals__", "__builtins__", "__dict__", "__code__", "__closure__",
    "__func__", "__self__", "__wrapped__", "__getattribute__", "__reduce__",
    "__reduce_ex__", "__subclasshook__", "__init_subclass__", "__loader__",
    "__spec__", "__traceback__", "__import__",
    "gi_frame", "gi_code", "cr_frame", "cr_code", "ag_frame", "ag_code",
    "tb_frame", "f_globals", "f_locals", "f_builtins", "f_back", "f_code",
})
BLOCKED_NAMES = frozenset({"__builtins__", "__import__", "__loader__", "__spec__"})

# Allowed modules expose helpers that re-open the holes closed above
# (operator.attrgetter("__class__"), string.Formatter().get_field(...)).
HIDDEN_MODULE_ATTRS: Dict[str, frozenset] = {
    "operator": frozenset({"attrgetter", "methodcaller"}),
    "string": frozenset({"Formatter"}),
}

REMOVED_BUILTINS = (
    "eval", "exec", "compile",              # dynamic code execution
    "__import__",                           # replaced by make_import_hook
    "breakpoint", "input",                  # debugger / blocking stdin
    "exit", "quit", "help", "license", "credits", "copyright",  # site helpers
    "globals", "locals", "vars", "dir",     # namespace introspection
    "__loader__", "__spec__",
)


def validate_ast(tree: ast.AST) -> None:
    """Reject code that touches interpreter internals. Raises PermissionError."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in BLOCKED_ATTRS:
            raise PermissionError(
                f"Access to attribute '{node.attr}' is not allowed (line {node.lineno})"
            )
        if isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise PermissionError(f"Use of '{node.id}' is not allowed (line {node.lineno})")


def _check_attr_name(name: Any) -> None:
    # getattr(x, "__cl" + "ass__") defeats the static check, so guard at runtime too.
    if isinstance(name, str) and name in BLOCKED_ATTRS:
        raise PermissionError(f"Access to attribute '{name}' is not allowed")


def make_safe_builtins(allowed_directories: List[str]) -> Dict[str, Any]:
    """Builtins with dangerous ones removed or overridden (open, eval, exec, __import__, ...).

    Returns a globals dict `{"__builtins__": {...}}` ready to be used with exec().
    Harmless-but-useful builtins (type, isinstance, super, object, bytearray, ...) are
    kept: removing them breaks ordinary code (classes, isinstance checks) and gives
    no protection, since the attribute checks above are what stops hierarchy walking.
    """
    safe = vars(builtins).copy()
    for name in REMOVED_BUILTINS:
        safe.pop(name, None)

    real_open = builtins.open
    real_getattr, real_setattr = builtins.getattr, builtins.setattr
    real_delattr, real_hasattr = builtins.delattr, builtins.hasattr

    def safe_open(file, mode="r", buffering=-1, encoding=None, errors=None,
                  newline=None, closefd=True, opener=None):
        if opener is not None:
            raise PermissionError("Custom openers are not allowed")
        if isinstance(file, int):
            raise PermissionError("Opening file descriptors is not allowed")
        check_path_allowed(os.fsdecode(file), allowed_directories)
        return real_open(file, mode, buffering, encoding, errors, newline, closefd)

    def safe_getattr(obj, name, *default):
        _check_attr_name(name)
        return real_getattr(obj, name, *default)

    def safe_setattr(obj, name, value):
        _check_attr_name(name)
        real_setattr(obj, name, value)

    def safe_delattr(obj, name):
        _check_attr_name(name)
        real_delattr(obj, name)

    def safe_hasattr(obj, name):
        _check_attr_name(name)
        return real_hasattr(obj, name)

    safe.update(
        open=safe_open, getattr=safe_getattr, setattr=safe_setattr,
        delattr=safe_delattr, hasattr=safe_hasattr,
    )
    return {"__builtins__": safe}


def make_import_hook(authorized_imports: List[str]) -> Callable[..., Any]:
    """Replacement for __import__ allowing only allowlisted modules.

    An entry like "collections.*" also permits submodules (collections.abc).

    The hook returns a *public view* of the module (no `_private` names, no
    attributes that are themselves non-allowed modules). Otherwise `typing.sys` or
    `json.codecs` would hand the code `sys` / `codecs.open` through an allowed module.
    """
    exact = {e for e in authorized_imports if not e.endswith(".*")}
    wildcards = {e[:-2] for e in authorized_imports if e.endswith(".*")}

    def allowed(name: str) -> bool:
        return name in exact or any(name == w or name.startswith(w + ".") for w in wildcards)

    real_import = builtins.__import__
    views: Dict[str, types.ModuleType] = {}

    def view_of(module: types.ModuleType) -> types.ModuleType:
        name = module.__name__
        if name in views:
            return views[name]
        view = types.ModuleType(name, getattr(module, "__doc__", None))
        views[name] = view  # registered before filling: submodules may refer back
        hidden = HIDDEN_MODULE_ATTRS.get(name, frozenset())
        for key, value in vars(module).items():
            if key.startswith("_") or key in hidden:
                continue
            if isinstance(value, types.ModuleType):
                if not allowed(value.__name__):
                    continue
                value = view_of(value)
            view.__dict__[key] = value
        return view

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level != 0:
            raise ImportError("Relative imports are not allowed")
        if not allowed(name):
            raise ImportError(f"Import of '{name}' is not allowed")
        return view_of(real_import(name, globals, locals, fromlist, 0))

    return safe_import


def check_path_allowed(path: str, allowed_directories: List[str]) -> None:
    """Raise PermissionError unless `path` resolves inside an allowed directory.

    Resolve symlinks and '..' first, otherwise the allowlist can be bypassed.
    """
    try:
        resolved = Path(path).resolve()
    except (OSError, RuntimeError):
        raise PermissionError(f"Cannot resolve path: {path}")

    for allowed in allowed_directories:
        try:
            resolved.relative_to(Path(allowed).resolve())
            return
        except ValueError:
            continue

    raise PermissionError(
        f"Access to '{resolved}' is denied. Allowed directories: {allowed_directories}"
    )


def block_network() -> None:
    """Prevent any inbound/outbound network connection in the sandbox process.

    Call this inside the worker process, before running untrusted code. Sockets that
    already exist (our own pipe to the parent) keep working; creating new ones fails.
    """
    import _socket
    import socket

    def deny(*_args: Any, **_kwargs: Any) -> Any:
        raise PermissionError("Network access is disabled in the sandbox")

    class BlockedSocket:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            deny()

    for module in (socket, _socket):
        module.socket = BlockedSocket
        for fn in ("create_connection", "create_server", "socketpair", "fromfd",
                   "getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr"):
            if hasattr(module, fn):
                setattr(module, fn, deny)
    socket.SocketType = BlockedSocket


def apply_memory_limit(max_memory_mb: int) -> None:
    """Limit process memory so runaway code is terminated.

    RLIMIT_AS is enforced on Linux (allocation raises MemoryError) but is ignored on
    macOS, so the parent process additionally watches the worker's RSS (executor.py).
    """
    try:
        import resource
    except ImportError:  # non-POSIX
        return
    limit = max_memory_mb * 1024 * 1024
    for res in (resource.RLIMIT_AS, getattr(resource, "RLIMIT_DATA", None)):
        if res is None:
            continue
        try:
            resource.setrlimit(res, (limit, limit))
        except (ValueError, OSError):
            pass
    try:  # a killed worker must not leave a multi-hundred-MB core dump behind
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ValueError, OSError):
        pass
