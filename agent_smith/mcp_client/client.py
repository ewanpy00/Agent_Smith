"""MCP client: stdio and streamable HTTP transports, tools exposed as Python callables."""
from __future__ import annotations

import asyncio
import shlex
import threading
from concurrent.futures import Future
from contextlib import AsyncExitStack
from typing import Any, Callable, Coroutine, Dict, List, TypeVar

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

T = TypeVar("T")
CALL_TIMEOUT = 120.0  # seconds to wait for one MCP request


class MCPClient:
    """Connects to an MCP server and discovers what it offers.

    The system is tested with an unknown MCP server, so nothing about tools
    may be hardcoded: discover tools, resources and prompts dynamically.

    The MCP SDK is async, the sandbox is sync. The client owns a background thread
    with its own event loop; every public method submits a coroutine to that loop
    and blocks until it finishes. The session lives in that one loop for its whole
    life, which the SDK's transports (anyio task groups) require.
    """

    def __init__(self, stdio_command: str | None = None, server_url: str | None = None) -> None:
        if bool(stdio_command) == bool(server_url):
            raise ValueError("Pass exactly one of stdio_command or server_url")
        self._stdio_command = stdio_command
        self._server_url = server_url
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="mcp-client")
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: List[Dict[str, Any]] = []
        self._resources: List[Dict[str, Any]] = []
        self._prompts: List[Dict[str, Any]] = []

    # -- sync <-> async bridge --------------------------------------------

    def _run(self, coro: Coroutine[Any, Any, T], timeout: float | None = CALL_TIMEOUT) -> T:
        future: Future[T] = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout)
        except TimeoutError:
            future.cancel()
            raise TimeoutError(f"MCP request timed out after {timeout}s") from None

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> None:
        """Open the transport, run the MCP handshake and cache tools/resources/prompts."""
        if self._session is not None:
            return
        if not self._thread.is_alive():
            self._thread.start()
        try:
            self._run(self._connect(), timeout=60.0)
        except BaseException:
            self.close()
            raise

    async def _connect(self) -> None:
        stack = AsyncExitStack()
        self._stack = stack
        if self._stdio_command:
            argv = shlex.split(self._stdio_command)
            params = StdioServerParameters(command=argv[0], args=argv[1:])
            read, write = await stack.enter_async_context(stdio_client(params))
        else:
            read, write = await stack.enter_async_context(streamable_http_client(self._server_url))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        caps = session.server_capabilities

        self._tools = [self._tool_schema(t) for t in (await session.list_tools()).tools]
        # resources / prompts are optional in the protocol: ask only if the server has them
        if caps is not None and caps.resources is not None:
            self._resources = [
                {"uri": str(r.uri), "name": r.name, "description": r.description or ""}
                for r in (await session.list_resources()).resources
            ]
        if caps is not None and caps.prompts is not None:
            self._prompts = [
                {"name": p.name, "description": p.description or "",
                 "arguments": [a.name for a in (p.arguments or [])]}
                for p in (await session.list_prompts()).prompts
            ]
        self._session = session

    @staticmethod
    def _tool_schema(tool: Any) -> Dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.input_schema or {"type": "object", "properties": {}},
        }

    def close(self) -> None:
        """Close the session and stop the server subprocess / HTTP stream."""
        if self._stack is not None and self._thread.is_alive():
            try:
                self._run(self._stack.aclose(), timeout=10.0)
            except BaseException:
                pass  # shutting down: nothing useful to do with a failed teardown
        self._stack = self._session = None
        if self._thread.is_alive():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)

    def __enter__(self) -> "MCPClient":
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- discovery ---------------------------------------------------------

    def list_tools(self) -> List[Dict[str, Any]]:
        """Tool schemas: names, descriptions, parameter types (JSON Schema in `input_schema`)."""
        return list(self._tools)

    def list_resources(self) -> List[Dict[str, Any]]:
        return list(self._resources)

    def list_prompts(self) -> List[Dict[str, Any]]:
        return list(self._prompts)

    # -- calls -------------------------------------------------------------

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool and return its text. A tool-level error raises RuntimeError."""
        if self._session is None:
            raise RuntimeError("MCP client is not connected")
        result = self._run(self._session.call_tool(name, arguments))
        parts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
        text = "\n".join(parts)
        if result.is_error:
            raise RuntimeError(text or f"tool {name!r} reported an error")
        return text

    def read_resource(self, uri: str) -> str:
        if self._session is None:
            raise RuntimeError("MCP client is not connected")
        result = self._run(self._session.read_resource(uri))  # type: ignore[arg-type]
        return "\n".join(getattr(c, "text", "") for c in result.contents)

    def as_python_functions(self) -> Dict[str, Callable[..., Any]]:
        """Wrap every discovered tool into a plain Python function for the sandbox namespace.

        Positional arguments are mapped to the schema's parameter order, so both
        `run_tests(code, tests)` and `run_tests(code=..., test_list=...)` work.
        """
        return {t["name"]: self._make_function(t) for t in self._tools}

    def _make_function(self, tool: Dict[str, Any]) -> Callable[..., Any]:
        name = tool["name"]
        params = list(tool["input_schema"].get("properties", {}))

        def call(*args: Any, **kwargs: Any) -> str:
            if len(args) > len(params):
                raise TypeError(f"{name}() takes at most {len(params)} arguments ({', '.join(params)})")
            arguments = dict(zip(params, args))
            clash = arguments.keys() & kwargs.keys()
            if clash:
                raise TypeError(f"{name}() got multiple values for {', '.join(sorted(clash))}")
            arguments.update(kwargs)
            return self.call_tool(name, arguments)

        call.__name__ = name
        call.__doc__ = tool["description"]
        return call
