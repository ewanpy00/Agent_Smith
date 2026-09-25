"""Interactive sandbox CLI (`uv run sandbox`, subject V.2 item 1).

Usage:
    uv run sandbox
    uv run sandbox sandbox_template.json
    uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" sandbox_template.json
    uv run sandbox --mcp-server <URL>
"""
from __future__ import annotations


def main() -> None:
    """REPL: read code in a loop, run it in the sandbox, print result or error.

    Exits cleanly on `exit` or EOF (Ctrl+D).
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()
