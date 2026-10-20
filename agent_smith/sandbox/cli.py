"""Interactive sandbox CLI (`uv run sandbox`, subject V.2 item 1).

Usage:
    uv run sandbox
    uv run sandbox sandbox_template.json
    uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" sandbox_template.json
    uv run sandbox --mcp-server <URL>
"""
from __future__ import annotations

import argparse
import codeop
import sys

from agent_smith.config import load_sandbox_config
from agent_smith.mcp_client.client import MCPClient
from agent_smith.sandbox.executor import ExecutionResult, Sandbox


def _read_entry() -> str | None:
    """Read one complete entry; keeps prompting with '...' while a block is unfinished.

    Returns None on EOF (Ctrl+D).
    """
    lines: list[str] = []
    while True:
        try:
            line = input("... " if lines else ">>> ")
        except EOFError:
            return None
        lines.append(line)
        source = "\n".join(lines)
        try:
            if codeop.compile_command(source) is not None:
                return source
        except (SyntaxError, ValueError, OverflowError):
            return source  # let the sandbox report the syntax error
        if len(lines) > 1 and not line.strip():
            return source  # blank line ends a block


def _print_result(result: ExecutionResult) -> None:
    if result.output:
        print(result.output, end="" if result.output.endswith("\n") else "\n")
    if result.error:
        print(result.error, file=sys.stderr)
    if result.final_answer is not None:
        print(f"[final_answer] {result.final_answer}")


def main() -> None:
    """REPL: read code in a loop, run it in the sandbox, print result or error.

    Exits cleanly on `exit` or EOF (Ctrl+D).
    """
    parser = argparse.ArgumentParser(prog="sandbox", description="Interactive sandbox REPL")
    parser.add_argument("config", nargs="?", help="path to a SandboxConfig JSON file")
    parser.add_argument("--mcp-stdio", metavar="COMMAND", help="MCP server started as a subprocess")
    parser.add_argument("--mcp-server", metavar="URL", help="MCP server reachable over streamable HTTP")
    args = parser.parse_args()

    if args.mcp_stdio and args.mcp_server:
        parser.error("use either --mcp-stdio or --mcp-server, not both")

    client = None
    tools = {}
    if args.mcp_stdio or args.mcp_server:
        client = MCPClient(stdio_command=args.mcp_stdio, server_url=args.mcp_server)
        try:
            client.connect()
        except Exception as exc:
            parser.exit(1, f"sandbox: cannot connect to the MCP server: {exc}\n")
        tools = client.as_python_functions()
        print(f"[mcp] tools available: {', '.join(tools) or 'none'}")

    sandbox = Sandbox(load_sandbox_config(args.config), tools=tools)
    try:
        while True:
            entry = _read_entry()
            if entry is None or entry.strip() in ("exit", "exit()", "quit"):
                print()
                break
            if not entry.strip():
                continue
            try:
                _print_result(sandbox.execute(entry, echo_last_expr=True))
            except (SystemExit, KeyboardInterrupt) as exc:
                print(f"[sandbox code raised {type(exc).__name__}]", file=sys.stderr)
    except KeyboardInterrupt:
        print()
    finally:
        sandbox.close()
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
