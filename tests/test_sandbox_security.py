"""Mirrors the checks of exam_sandbox.sh (subject VI, Table VI.1). All must pass."""
import pytest

pytestmark = pytest.mark.skip(reason="sandbox not implemented yet")


def test_import_block():
    """`import os` / `import subprocess` are rejected."""


def test_builtin_block():
    """open, eval, exec, __import__ are unavailable."""


def test_network_block():
    """Creating a socket / connecting fails."""


def test_path_restrict():
    """Reading outside allowed_directories (also via '..' and symlinks) is denied."""


def test_timeout():
    """`while True: pass` is killed after max_execution_time_seconds."""


def test_memory_limit():
    """Allocating far more than max_memory_mb is terminated."""


def test_mcp_protocol():
    """Tools of a connected MCP server are callable from sandboxed code."""
