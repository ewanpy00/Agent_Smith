"""MCP server with the SWE-bench tools (mandatory tools, tested independently).

The repository location is read from the TESTBED_PATH environment variable
(set by the moulinette before it starts this server).
"""
from __future__ import annotations


# File system tools
def read_file(filepath: str, start_line: int, end_line: int) -> str:
    """Return the lines with numbers, `cat -n` style: "<line_number>: <line_content>"."""
    raise NotImplementedError


def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """Replace an exact string in a file."""
    raise NotImplementedError


def list_files(directory: str, pattern: str) -> str:
    """List files in a directory matching a pattern."""
    raise NotImplementedError


# Code search tools (output: "/absolute/path/file.py:<line_number> <line_content>")
def search_code(pattern: str, file_pattern: str) -> str:
    """grep-like search in the codebase."""
    raise NotImplementedError


def search_function_or_class_definition_in_code(name: str) -> str:
    """Find the definition of a function or class."""
    raise NotImplementedError


def find_references(name: str, filepath: str, line: int) -> str:
    """Find all usages of a symbol."""
    raise NotImplementedError


# Execution tools
def run_tests() -> str:
    """Execute the evaluation script."""
    raise NotImplementedError


def get_patch() -> str:
    """Unified diff of all changes (git -c core.fileMode=false diff)."""
    raise NotImplementedError


def run_command(command: str, workdir: str) -> str:
    """Run a shell command; return stdout, stderr and the exit code."""
    raise NotImplementedError


def main() -> None:
    # TODO: register the tools above on an MCP server and serve it over stdio (and HTTP).
    raise NotImplementedError


if __name__ == "__main__":
    main()
