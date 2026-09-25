"""Turn an LLM response into Python code for the sandbox (subject V.1, item 2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class ExtractionResult:
    """Code found in a response plus feedback for the LLM.

    `code` is empty when nothing valid was found. `warnings` are messages the
    agent loop shows to the LLM: no code block found, block was malformed but
    interpreted anyway (and how). Silent failures are not allowed.
    """
    code: str = ""
    source_format: str = ""  # "python_block" | "xml" | "hermes_json" | "react"
    warnings: List[str] = field(default_factory=list)


def extract_code(response_text: str) -> ExtractionResult:
    """Extract code from the response.

    Formats to support:
      (a) ```python ... ``` <end_code>      (primary)
      (b) XML <invoke name="..."><parameter>...
      (c) <tool_call>{"name": ..., "arguments": {...}}</tool_call>
      (d) ReAct "Action: tool / Action Input: {...}"
    Non-Python formats are converted to equivalent Python calls,
    e.g. result = read_file(filepath="/testbed/file.py").
    """
    raise NotImplementedError
