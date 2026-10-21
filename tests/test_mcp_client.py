"""MCP client against the real MBPP server, over stdio and streamable HTTP."""
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agent_smith.mcp_client.client import MCPClient

SERVER = str(Path(__file__).resolve().parent.parent / "mcp_tools_mbpp.py")
GOOD = "def add(a, b):\n    return a + b"
TESTS = ["assert add(1, 2) == 3", "assert add(0, 0) == 0"]


def _check_tool_behaviour(client: MCPClient) -> None:
    tools = client.list_tools()
    assert [t["name"] for t in tools] == ["run_tests"]
    assert set(tools[0]["input_schema"]["properties"]) == {"code", "test_list"}

    run_tests = client.as_python_functions()["run_tests"]
    ok = json.loads(run_tests(GOOD, TESTS))                      # positional
    assert ok["success"] and "2 passed" in ok["output"]
    bad = json.loads(run_tests(code="def add(a, b): return a - b", test_list=TESTS))  # keywords
    assert not bad["success"] and "FAILED: assert add(1, 2) == 3" in bad["output"]
    assert not json.loads(run_tests("def (:", TESTS))["success"]
    with pytest.raises(TypeError):
        run_tests(1, 2, 3)


def test_stdio():
    with MCPClient(stdio_command=f"{sys.executable} {SERVER}") as client:
        _check_tool_behaviour(client)


def test_http():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = subprocess.Popen([sys.executable, SERVER, "--http", "--port", str(port)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.2)
        with MCPClient(server_url=f"http://127.0.0.1:{port}/mcp") as client:
            _check_tool_behaviour(client)
    finally:
        server.terminate()
        server.wait(timeout=5)


def test_tools_inside_sandbox():
    from models import SandboxConfig
    from agent_smith.sandbox.executor import Sandbox

    with MCPClient(stdio_command=f"{sys.executable} {SERVER}") as client:
        with Sandbox(SandboxConfig(), tools=client.as_python_functions()) as sb:
            r = sb.execute(f"print(run_tests({GOOD!r}, {TESTS!r}))")
            assert json.loads(r.output)["success"], r


def test_bad_arguments_to_constructor():
    with pytest.raises(ValueError):
        MCPClient()


def test_manual_reflects_server_tools():
    from agent_smith.mcp_client.manual import build_sandbox_manual

    with MCPClient(stdio_command=f"{sys.executable} {SERVER}") as client:
        manual = build_sandbox_manual(client.list_tools())
    assert "### run_tests(code: str, test_list: list[str])" in manual
    assert "final_answer(answer)" in manual

    other = [{"name": "grep", "description": "Search files.",
              "input_schema": {"type": "object", "required": ["pattern"],
                               "properties": {"pattern": {"type": "string", "description": "regex"},
                                              "limit": {"type": "integer", "default": 10}}}}]
    text = build_sandbox_manual(other)
    assert "### grep(pattern: str, limit: int = 10)" in text and "run_tests" not in text
    assert "No external tools" in build_sandbox_manual([])
