"""MCP server with the MBPP tools (run as a separate process, stdio or HTTP)."""
from __future__ import annotations


def run_tests(code: str, test_list: list[str]) -> str:
    """Run `code` against the given test assertions.

    Returns a JSON string: {"success": bool, "output": str}, where success
    means all assertions passed. Tools must work independently of the agent loop.
    """
    raise NotImplementedError


def main() -> None:
    # TODO: register run_tests (and any useful extra tools) on an MCP server and
    #       serve it over stdio (and streamable HTTP).
    raise NotImplementedError


if __name__ == "__main__":
    main()
