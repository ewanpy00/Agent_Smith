"""CLI: uv run python -m agent_swebench --task-file T --output O --model-name M --provider-url U"""
from __future__ import annotations

import argparse
from pathlib import Path

from models import SWEBenchTaskInput


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="agent_swebench")
    parser.add_argument("--task-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--provider-url", required=True)
    parser.add_argument("--sandbox-config", type=Path, default=Path("sandbox_template.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    task = SWEBenchTaskInput.model_validate_json(args.task_file.read_text())
    # TODO: pull task.docker_image, start container, start MCP server (mcp_tools_swebench.py)
    #       with TESTBED_PATH set, run AgentLoop with SWEBENCH_LIMITS, write SolutionOutput,
    #       and ALWAYS clean the container up (also on SIGTERM: the timeout kills the process).
    raise NotImplementedError(f"agent_swebench not implemented (task {task.instance_id})")


if __name__ == "__main__":
    main()
