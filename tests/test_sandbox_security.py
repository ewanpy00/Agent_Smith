"""Mirrors the checks of exam_sandbox.sh (subject VI, Table VI.1). All must pass."""
import subprocess
import sys

import pytest

from models import SandboxConfig
from agent_smith.sandbox.executor import Sandbox


@pytest.fixture
def make_sandbox(tmp_path):
    created = []

    def factory(tools=None, **overrides):
        config = SandboxConfig(allowed_directories=[str(tmp_path / "work")], **overrides)
        sandbox = Sandbox(config, tools=tools)
        created.append(sandbox)
        return sandbox

    yield factory
    for sandbox in created:
        sandbox.close()


def test_import_block(make_sandbox):
    """`import os` / `import subprocess` are rejected."""
    sb = make_sandbox()
    for module in ("os", "subprocess", "sys", "socket", "pathlib"):
        result = sb.execute(f"import {module}")
        assert result.error and "not allowed" in result.error, module
    assert sb.execute("import math\nprint(math.sqrt(16))").output.strip() == "4.0"
    assert sb.execute("from collections import abc\nprint(abc.Mapping.__name__)").output.strip() == "Mapping"
    # an allowed module must not leak a forbidden one through its attributes
    assert sb.execute("import json\njson.codecs").error
    assert sb.execute("import typing\ntyping.sys").error


def test_builtin_block(make_sandbox):
    """open, eval, exec, __import__ are unavailable."""
    sb = make_sandbox()
    for snippet in ("eval('1')", "exec('x = 1')", "__import__('os')", "compile('1', 'f', 'eval')"):
        assert sb.execute(snippet).error, snippet
    assert sb.execute("open('/etc/passwd')").error  # path check, see test_path_restrict
    # classic escapes
    assert sb.execute("().__class__.__bases__[0].__subclasses__()").error
    assert sb.execute("getattr((), '__cl' + 'ass__')").error
    assert sb.execute("(lambda: 0).__globals__").error
    assert sb.execute("import operator\noperator.attrgetter('real')").error
    # ordinary code keeps working
    result = sb.execute("class A:\n    def __init__(self): self.x = 1\nprint(isinstance(A(), A))")
    assert result.output.strip() == "True" and not result.error


def test_network_block(make_sandbox):
    """Creating a socket / connecting fails."""
    sb = make_sandbox()
    assert sb.execute("import socket").error
    # the second layer, independent of the import allowlist:
    script = (
        "from agent_smith.sandbox import restrictions as r\n"
        "r.block_network()\n"
        "import socket\n"
        "try:\n"
        "    socket.socket()\n"
        "except PermissionError:\n"
        "    print('blocked')\n"
    )
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert out.stdout.strip() == "blocked", out.stderr


def test_path_restrict(make_sandbox, tmp_path):
    """Reading outside allowed_directories (also via '..' and symlinks) is denied."""
    work = tmp_path / "work"
    work.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    (work / "link").symlink_to(secret)
    sb = make_sandbox()

    assert not sb.execute(f"open({str(work / 'ok.txt')!r}, 'w').write('hi')").error
    assert sb.execute(f"print(open({str(work / 'ok.txt')!r}).read())").output.strip() == "hi"
    assert "denied" in sb.execute(f"open({str(secret)!r}).read()").error
    assert "denied" in sb.execute(f"open({str(work / '..' / 'secret.txt')!r}).read()").error
    assert "denied" in sb.execute(f"open({str(work / 'link')!r}).read()").error
    assert sb.execute("open(0)").error


def test_timeout(make_sandbox):
    """`while True: pass` is killed after max_execution_time_seconds."""
    sb = make_sandbox(max_execution_time_seconds=1)
    result = sb.execute("print('started')\nwhile True: pass")
    assert result.timed_out
    assert "started" in result.output  # partial output survives the kill
    # the sandbox is usable again afterwards, with fresh state
    assert sb.execute("print(1 + 1)").output.strip() == "2"


def test_memory_limit(make_sandbox):
    """Allocating far more than max_memory_mb is terminated."""
    sb = make_sandbox(max_memory_mb=256, max_execution_time_seconds=20)
    result = sb.execute("hog = []\nwhile True:\n    hog.append('a' * 10**6)")
    assert result.error and "emory" in result.error  # MemoryError (Linux) or watchdog (macOS)
    assert sb.execute("print('alive')").output.strip() == "alive"


def test_mcp_protocol(make_sandbox):
    """Tools of a connected MCP server are callable from sandboxed code.

    A plain function stands in for the MCP wrapper here; the real MCP client is
    covered once agent_smith/mcp_client exists.
    """
    calls = []

    def add(a, b):
        calls.append((a, b))
        return a + b

    def boom():
        raise ValueError("nope")

    sb = make_sandbox(tools={"add": add, "boom": boom})
    assert sb.execute("print(add(2, b=3))").output.strip() == "5"
    assert calls == [(2, 3)]
    assert "Tool 'boom' failed" in sb.execute("boom()").error


def test_state_final_answer_and_errors(make_sandbox):
    sb = make_sandbox()
    sb.execute("x = 41")
    assert sb.execute("print(x + 1)").output.strip() == "42"
    assert "ZeroDivisionError" in sb.execute("1 / 0").error
    assert "SyntaxError" in sb.execute("def (:").error
    result = sb.execute("try:\n    final_answer('done')\nexcept Exception:\n    print('swallowed')")
    assert result.final_answer == "done" and "swallowed" not in result.output
    assert sb.execute("print('x' * 20000)").truncated


def test_system_exit_propagates(make_sandbox):
    sb = make_sandbox()
    with pytest.raises(SystemExit):
        sb.execute("raise SystemExit(3)")
    with pytest.raises(KeyboardInterrupt):
        sb.execute("raise KeyboardInterrupt()")
