"""MCP client: stdio and streamable HTTP transports, tools exposed as Python callables."""
from __future__ import annotations

from typing import Any, Callable, Dict, List


class MCPClient:
    """Connects to an MCP server and discovers what it offers.

    The system is tested with an unknown MCP server, so nothing about tools
    may be hardcoded: discover tools, resources and prompts dynamically.
    """

    def __init__(self, stdio_command: str | None = None, server_url: str | None = None) -> None:
        raise NotImplementedError

    def connect(self) -> None:
        raise NotImplementedError

    def list_tools(self) -> List[Dict[str, Any]]:
        """Tool schemas: names, descriptions, parameter types."""
        raise NotImplementedError

    def as_python_functions(self) -> Dict[str, Callable[..., Any]]:
        """Wrap every discovered tool into a plain Python function for the sandbox namespace."""
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
