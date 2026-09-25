"""CLI: uv run python -m agent_mbpp --task-file T --output O --model-name M --provider-url U"""
from __future__ import annotations

import argparse
from pathlib import Path

from models import MBPPTaskInput


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent_mbpp")
    parser.add_argument("--task-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--provider-url", required=True)
    parser.add_argument("--sandbox-config", type=Path, default=Path("sandbox_template.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task = MBPPTaskInput.model_validate_json(args.task_file.read_text())
    # TODO: build LLM client (keys from env), start MCP server (mcp_tools_mbpp.py),
    #       create Sandbox with MCP tools, run AgentLoop with MBPP_LIMITS,
    #       write SolutionOutput JSON to args.output. Handle every error gracefully.
    raise NotImplementedError(f"agent_mbpp not implemented (task {task.task_id})")


if __name__ == "__main__":
    main()
