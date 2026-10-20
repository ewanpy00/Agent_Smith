"""MCP server with the MBPP tools (run as a separate process, stdio or HTTP)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp.server.mcpserver import MCPServer

TEST_TIMEOUT = 10  # seconds for the whole candidate + assertions run
MAX_OUTPUT = 4000  # chars of stderr/stdout returned to the agent


def _tail(text: str) -> str:
    return text if len(text) <= MAX_OUTPUT else "...[truncated]\n" + text[-MAX_OUTPUT:]


def run_tests(code: str, test_list: list[str]) -> str:
    """Run `code` against the given test assertions.

    Returns a JSON string: {"success": bool, "output": str}, where success
    means all assertions passed. Tools must work independently of the agent loop.
    """
    # Each assertion runs separately so the report names every failing one, not only the first.
    runner = (
        "import json, sys, traceback\n"
        "payload = json.load(open(sys.argv[1]))\n"
        "ns = {'__name__': '__candidate__'}\n"
        "try:\n"
        "    exec(compile(payload['code'], 'solution', 'exec'), ns)\n"
        "except BaseException:\n"
        "    traceback.print_exc(); sys.exit(2)\n"
        "failed = 0\n"
        "for t in payload['tests']:\n"
        "    try:\n"
        "        exec(compile(t, 'test', 'exec'), ns)\n"
        "    except BaseException as e:\n"
        "        failed += 1\n"
        "        print(f'FAILED: {t}\\n  {type(e).__name__}: {e}')\n"
        "print(f\"{len(payload['tests']) - failed} passed, {failed} failed\")\n"
        "sys.exit(1 if failed else 0)\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        payload = Path(tmp) / "payload.json"
        payload.write_text(json.dumps({"code": code, "tests": list(test_list)}))
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", runner, str(payload)],
                capture_output=True, text=True, timeout=TEST_TIMEOUT, cwd=tmp,
            )
        except subprocess.TimeoutExpired:
            return json.dumps({"success": False, "output": f"Timed out after {TEST_TIMEOUT}s (infinite loop?)"})
    output = _tail((proc.stdout + proc.stderr).strip())
    return json.dumps({"success": proc.returncode == 0, "output": output})


def build_server() -> MCPServer:
    server = MCPServer("mbpp-tools")
    server.add_tool(run_tests, name="run_tests", description=(run_tests.__doc__ or "").strip())
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="MBPP MCP server")
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = build_server()
    if args.http:
        server.run(transport="streamable-http", port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
