"""Sandbox manual: what the LLM reads to learn which tools exist and how to call them."""
from __future__ import annotations

from typing import Any, Dict, List


def build_sandbox_manual(tools: List[Dict[str, Any]]) -> str:
    """Generate the manual dynamically from the connected server's tool schemas.

    Must reflect a different MCP server automatically (subject V.2 item 5).
    Also documents final_answer, which is always present and not an MCP tool.
    """
    raise NotImplementedError
