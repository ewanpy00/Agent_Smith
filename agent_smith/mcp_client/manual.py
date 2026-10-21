"""Sandbox manual: what the LLM reads to learn which tools exist and how to call them."""
from __future__ import annotations

from typing import Any, Dict, List

_PRELUDE = """\
## Sandbox manual

Your code runs in a persistent Python sandbox: variables and functions defined in one
step are still there in the next one. Use print() to see values; only printed output
(and errors) come back to you as the Observation.

Restrictions: only allowlisted modules can be imported, there is no network access, and
each step has a time and memory limit (exceeding it restarts the sandbox and loses all
variables). Everything the sandbox needs from the outside world goes through the tools below.
"""

_FINAL_ANSWER = """\
### final_answer(answer)
Built into the sandbox (not an MCP tool). Call it exactly once, when the task is done, to
submit your result and stop. `answer` is a string. Nothing after this call is executed.
"""


def _type_of(schema: Dict[str, Any]) -> str:
    """Render a JSON-Schema fragment as a short Python-like type."""
    if "enum" in schema:
        return " | ".join(repr(v) for v in schema["enum"])
    for key in ("anyOf", "oneOf"):
        if key in schema:
            return " | ".join(_type_of(s) for s in schema[key])
    kind = schema.get("type")
    if isinstance(kind, list):
        return " | ".join(_type_of({**schema, "type": k}) for k in kind)
    if kind == "array":
        return f"list[{_type_of(schema['items'])}]" if "items" in schema else "list"
    return {
        "string": "str", "integer": "int", "number": "float", "boolean": "bool",
        "object": "dict", "null": "None",
    }.get(kind, "Any")


def _describe_tool(tool: Dict[str, Any]) -> str:
    schema = tool.get("input_schema") or {}
    props: Dict[str, Any] = schema.get("properties", {})
    required = set(schema.get("required", []))

    params = []
    for name, spec in props.items():
        text = f"{name}: {_type_of(spec)}"
        if name not in required:
            text += f" = {spec['default']!r}" if "default" in spec else " = None"
        params.append(text)
    lines = [f"### {tool['name']}({', '.join(params)})"]
    if tool.get("description"):
        lines.append(tool["description"].strip())
    if props:
        lines.append("Parameters:")
        for name, spec in props.items():
            note = spec.get("description", "")
            flag = "required" if name in required else "optional"
            lines.append(f"- `{name}` ({_type_of(spec)}, {flag})" + (f": {note}" if note else ""))
    lines.append("Call it like a normal Python function; it returns its result as a string.")
    return "\n".join(lines)


def build_sandbox_manual(tools: List[Dict[str, Any]]) -> str:
    """Generate the manual dynamically from the connected server's tool schemas.

    Must reflect a different MCP server automatically (subject V.2 item 5).
    Also documents final_answer, which is always present and not an MCP tool.
    """
    sections = [_PRELUDE, "## Tools"]
    if tools:
        sections += [_describe_tool(t) for t in tools]
    else:
        sections.append("No external tools are connected.")
    sections.append(_FINAL_ANSWER)
    return "\n\n".join(sections)
