"""MCP server with the SWE-bench tools (mandatory tools, tested independently).

The repository location is read from the TESTBED_PATH environment variable
(set by the moulinette before it starts this server). Relative paths given to
the tools are resolved against it.

run_tests() looks for the evaluation script in EVAL_SCRIPT_PATH (a file),
then EVAL_SCRIPT (the script text), then /eval.sh (where SWE-bench images keep it).

Expected failures (missing file, ambiguous edit, ...) are returned as text starting
with "Error:" so the agent gets an explanation it can act on.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import os
import re
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Iterator

from mcp.server.mcpserver import MCPServer
from pydantic import Field

DEFAULT_READ_LINES = 1000  # read_file without end_line stops here
MAX_MATCHES = 200          # search results returned at most
MAX_LISTED = 500           # list_files entries returned at most
MAX_LINE_CHARS = 300       # long lines in search results are cut
MAX_OUTPUT = 10000         # chars of command / test output returned
MAX_FILE_BYTES = 2_000_000  # bigger files are skipped by the search tools
COMMAND_TIMEOUT = 120      # seconds for run_command
TESTS_TIMEOUT = 300        # seconds for run_tests
SKIP_DIRS = {".git", "__pycache__", ".tox", ".eggs", ".mypy_cache", ".pytest_cache", "node_modules"}
DEFINITION = re.compile(r"^\s*(?:async\s+def|def|class)\s+(\w+)")


# -- helpers -----------------------------------------------------------------

def _root() -> Path:
    return Path(os.path.abspath(os.environ.get("TESTBED_PATH", "/testbed")))


def _resolve(path: str) -> Path:
    p = Path(path)
    return Path(os.path.normpath(p if p.is_absolute() else _root() / p))


def _lines(text: str) -> list[str]:
    """Split like grep / git count lines (only on \\n, so numbers always agree)."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line.rstrip("\r") for line in lines]


def _read_text(path: Path) -> str | None:
    """File contents, or None for binary / oversized files."""
    if path.stat().st_size > MAX_FILE_BYTES:
        return None
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        return None
    return data.decode("utf-8", errors="replace")


def _clip(text: str, limit: int = MAX_OUTPUT) -> str:
    """Keep the head and (mostly) the tail, where errors and summaries are."""
    if len(text) <= limit:
        return text
    head = limit // 4
    return f"{text[:head]}\n...[{len(text) - limit} chars truncated]...\n{text[-(limit - head):]}"


def _walk_files(file_pattern: str = "*") -> Iterator[Path]:
    """Every file under the repo, sorted, matching a comma-separated glob list.

    A pattern containing "/" is matched against the path relative to the repo,
    otherwise against the file name.
    """
    root = _root()
    patterns = [p.strip() for p in file_pattern.split(",") if p.strip()] or ["*"]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info"))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if any(fnmatch.fnmatch(rel if "/" in p else name, p) for p in patterns):
                yield path


def _format_matches(matches: list[str], total: int, what: str) -> str:
    if not matches:
        return f"No {what} found."
    text = "\n".join(matches)
    if total > len(matches):
        text += f"\n...[{total - len(matches)} more {what} not shown, narrow the search]"
    return text


def _match_line(path: Path, number: int, line: str) -> str:
    return f"{path}:{number} {line.strip()[:MAX_LINE_CHARS]}"


def _grep(regex: re.Pattern[str], file_pattern: str) -> tuple[list[str], int]:
    matches: list[str] = []
    total = 0
    for path in _walk_files(file_pattern):
        text = _read_text(path)
        if text is None or not regex.search(text):
            continue
        for number, line in enumerate(_lines(text), 1):
            if regex.search(line):
                total += 1
                if len(matches) < MAX_MATCHES:
                    matches.append(_match_line(path, number, line))
    return matches, total


def _run(argv: list[str], cwd: Path, timeout: int, merge_stderr: bool = False) -> tuple[int | None, str, str]:
    """Run a process in its own group; on timeout kill the whole group. None = timed out."""
    proc = subprocess.Popen(
        argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        text=True, errors="replace", start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err or ""
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
        return None, out, err or ""


# -- file system tools -------------------------------------------------------

def read_file(
    filepath: Annotated[str, Field(description="File path, absolute or relative to the repository root")],
    start_line: Annotated[int, Field(description="First line to show (1-based)")] = 1,
    end_line: Annotated[int | None, Field(description="Last line to show, inclusive (default: end of file)")] = None,
) -> str:
    """Read a file with line numbers, one "<line_number>: <line_content>" per line.

    Without end_line at most 1000 lines are shown; pass start_line/end_line to read more.
    """
    path = _resolve(filepath)
    if path.is_dir():
        return f"Error: {path} is a directory, use list_files to see its content."
    if not path.is_file():
        return f"Error: file not found: {path}"
    text = _read_text(path)
    if text is None:
        return f"Error: {path} is a binary or very large file."
    lines = _lines(text)
    if not lines:
        return f"(file {path} is empty)"
    start = max(start_line, 1)
    if start > len(lines):
        return f"Error: start_line {start_line} is past the end of the file ({len(lines)} lines)."
    limited = end_line is None and len(lines) - start + 1 > DEFAULT_READ_LINES
    end = start + DEFAULT_READ_LINES - 1 if limited else min(end_line or len(lines), len(lines))
    if end < start:
        return f"Error: end_line {end_line} is before start_line {start_line}."
    body = "\n".join(f"{n}: {lines[n - 1]}" for n in range(start, end + 1))
    if limited:
        body += f"\n...[file has {len(lines)} lines, use start_line/end_line to read the rest]"
    return body


def edit_file(
    filepath: Annotated[str, Field(description="File path, absolute or relative to the repository root")],
    old_str: Annotated[str, Field(description="Exact text to replace (whitespace included); must occur exactly once. Empty creates a new file")],
    new_str: Annotated[str, Field(description="Replacement text")],
) -> str:
    """Replace an exact string in a file with a new string.

    old_str must match the file exactly once, including indentation; add surrounding
    lines to make it unique. Reports the edited lines and any Python syntax error it caused.
    """
    path = _resolve(filepath)
    if old_str == "":
        if path.exists():
            return f"Error: old_str is empty but {path} already exists; pass the text to replace."
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_str, encoding="utf-8")
        return f"Created {path} ({len(_lines(new_str))} lines)." + _syntax_warning(path, new_str)
    if not path.is_file():
        return f"Error: file not found: {path}"
    if old_str == new_str:
        return "Error: old_str and new_str are identical, nothing to change."
    with open(path, encoding="utf-8", errors="surrogateescape", newline="") as f:
        text = f.read()

    count = text.count(old_str)
    if count == 0:
        hint = "Re-read the file with read_file and copy the text exactly, including indentation."
        stripped = old_str.strip()
        if stripped and stripped in text:
            line = text[:text.index(stripped)].count("\n") + 1
            hint = f"A match ignoring leading/trailing whitespace exists at line {line}; fix the indentation."
        return f"Error: old_str not found in {path}. {hint}"
    if count > 1:
        lines = [text[:m.start()].count("\n") + 1 for m in re.finditer(re.escape(old_str), text)]
        return (f"Error: old_str occurs {count} times in {path} (lines {', '.join(map(str, lines[:10]))}); "
                "include more surrounding lines so it is unique.")

    offset = text.index(old_str)
    new_text = text[:offset] + new_str + text[offset + len(old_str):]
    with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
        f.write(new_text)

    first = text[:offset].count("\n") + 1
    last = first + new_str.count("\n")
    lines = _lines(new_text)
    shown = range(max(first - 3, 1), min(last + 3, len(lines)) + 1)
    snippet = "\n".join(f"{n}: {lines[n - 1]}" for n in shown)
    return f"Edited {path} (lines {first}-{last} now):\n{snippet}" + _syntax_warning(path, new_text)


def _syntax_warning(path: Path, text: str) -> str:
    if path.suffix != ".py":
        return ""
    try:
        ast.parse(text)
    except SyntaxError as exc:
        return f"\nWarning: {path} no longer parses: SyntaxError at line {exc.lineno}: {exc.msg}. Fix it."
    return ""


def list_files(
    directory: Annotated[str, Field(description="Directory, absolute or relative to the repository root")] = ".",
    pattern: Annotated[str, Field(description='Glob pattern, e.g. "*.py"; use "**/*.py" to search subdirectories')] = "*",
) -> str:
    """List files in a directory matching a glob pattern (absolute paths, directories end with "/")."""
    base = _resolve(directory)
    if not base.is_dir():
        return f"Error: not a directory: {base}"
    try:
        found = sorted(p for p in base.glob(pattern) if not SKIP_DIRS & set(p.relative_to(base).parts))
    except (ValueError, NotImplementedError) as exc:
        return f"Error: bad pattern {pattern!r}: {exc}"
    if not found:
        return f"No files matching {pattern!r} in {base}"
    shown = [f"{p}/" if p.is_dir() else str(p) for p in found[:MAX_LISTED]]
    if len(found) > MAX_LISTED:
        shown.append(f"...[{len(found) - MAX_LISTED} more entries not shown, narrow the pattern]")
    return "\n".join(shown)


# -- code search tools -------------------------------------------------------

def search_code(
    pattern: Annotated[str, Field(description="Regular expression (Python syntax) to look for")],
    file_pattern: Annotated[str, Field(description='Glob for the files to search, e.g. "*.py" or "sympy/core/*.py"; comma-separated for several')] = "*",
) -> str:
    """Grep-like search in the repository. One "/absolute/path/file.py:<line_number> <line_content>" per match."""
    note = ""
    try:
        regex = re.compile(pattern)
    except re.error:
        regex = re.compile(re.escape(pattern))
        note = "(not a valid regular expression, searched as plain text)\n"
    matches, total = _grep(regex, file_pattern)
    return note + _format_matches(matches, total, "matches")


def search_function_or_class_definition_in_code(
    name: Annotated[str, Field(description='Function or class name, optionally qualified: "Foo", "bar" or "Foo.bar"')],
) -> str:
    """Find where a function or class is defined. Output format is the same as search_code."""
    target = name.strip()
    short = target.rsplit(".", 1)[-1]
    if not short.isidentifier():
        return f"Error: {name!r} is not a valid Python name."
    candidate = re.compile(rf"^\s*(?:async\s+def|def|class)\s+{short}\b", re.MULTILINE)
    matches: list[str] = []
    for path in _walk_files("*.py"):
        text = _read_text(path)
        if text is None or not candidate.search(text):
            continue
        lines = _lines(text)
        for number in _definition_lines(text, target, short):
            matches.append(_match_line(path, number, lines[number - 1]))
    return _format_matches(matches[:MAX_MATCHES], len(matches), "definitions")


def _definition_lines(text: str, target: str, short: str) -> list[int]:
    """Line numbers of definitions whose qualified name is `target` or ends with it."""
    try:
        tree = ast.parse(text)
    except SyntaxError:  # e.g. Python 2 files: fall back to the regex
        return [n for n, line in enumerate(_lines(text), 1)
                if (m := DEFINITION.match(line)) and m.group(1) == short]
    found = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualname = f"{prefix}{child.name}"
                if qualname == target or qualname.endswith("." + target):
                    found.append(child.lineno)
                visit(child, qualname + ".")
            else:
                visit(child, prefix)

    visit(tree, "")
    return sorted(found)


def find_references(
    name: Annotated[str, Field(description="Symbol (function or class) name")],
    filepath: Annotated[str, Field(description="File where the symbol appears (used to check the name)")] = "",
    line: Annotated[int, Field(description="Line in that file where the symbol appears")] = 0,
) -> str:
    """Find all usages of a symbol across the repository's Python files (whole-word matches).

    Output format is the same as search_code.
    """
    short = name.strip().rsplit(".", 1)[-1]
    if not short.isidentifier():
        return f"Error: {name!r} is not a valid Python name."
    regex = re.compile(rf"\b{short}\b")
    note = ""
    if filepath and line > 0:
        path = _resolve(filepath)
        text = _read_text(path) if path.is_file() else None
        lines = _lines(text) if text is not None else []
        if not 1 <= line <= len(lines) or not regex.search(lines[line - 1]):
            note = f"(note: {short!r} does not appear at {path}:{line}; showing all usages of the name)\n"
    matches, total = _grep(regex, "*.py")
    return note + _format_matches(matches, total, "references")


# -- execution tools ---------------------------------------------------------

def _eval_script() -> Path | str | None:
    if os.environ.get("EVAL_SCRIPT_PATH"):
        return Path(os.environ["EVAL_SCRIPT_PATH"])
    if os.environ.get("EVAL_SCRIPT"):
        return os.environ["EVAL_SCRIPT"]
    default = Path("/eval.sh")
    return default if default.is_file() else None


def run_tests() -> str:
    """Run the task's evaluation script (the tests that must pass) and return its exit code and output."""
    script = _eval_script()
    if script is None:
        return "Error: no evaluation script configured (EVAL_SCRIPT_PATH, EVAL_SCRIPT or /eval.sh)."
    with tempfile.TemporaryDirectory() as tmp:
        if isinstance(script, str):
            path = Path(tmp) / "eval.sh"
            path.write_text(script)
        else:
            path = script
        if not path.is_file():
            return f"Error: evaluation script not found: {path}"
        code, out, _ = _run(["bash", str(path)], _root(), TESTS_TIMEOUT, merge_stderr=True)
    status = f"timed out after {TESTS_TIMEOUT}s (killed)" if code is None else str(code)
    return f"exit_code: {status}\n{_clip(out)}"


def get_patch() -> str:
    """Return the unified diff of all changes made to the repository (git -c core.fileMode=false diff)."""
    code, out, err = _run(["git", "-c", "core.fileMode=false", "diff"], _root(), COMMAND_TIMEOUT)
    if code != 0:
        return f"Error: git diff failed: {err.strip() or out.strip()}"
    return out


def run_command(
    command: Annotated[str, Field(description="Shell command (run with bash -c)")],
    workdir: Annotated[str, Field(description="Working directory, absolute or relative to the repository root")] = ".",
) -> str:
    """Execute a shell command in a working directory and return its exit code, stdout and stderr.

    Commands are killed after 120 seconds; long outputs are cut in the middle.
    """
    cwd = _resolve(workdir)
    if not cwd.is_dir():
        return f"Error: not a directory: {cwd}"
    code, out, err = _run(["bash", "-c", command], cwd, COMMAND_TIMEOUT)
    status = f"timed out after {COMMAND_TIMEOUT}s (killed)" if code is None else str(code)
    return f"exit_code: {status}\n--- stdout ---\n{_clip(out)}\n--- stderr ---\n{_clip(err)}"


TOOLS = [
    read_file, edit_file, list_files,
    search_code, search_function_or_class_definition_in_code, find_references,
    run_tests, get_patch, run_command,
]


def build_server() -> MCPServer:
    server = MCPServer("swebench-tools")
    for tool in TOOLS:
        server.add_tool(tool, name=tool.__name__, description=(tool.__doc__ or "").strip())
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="SWE-bench MCP server")
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    server = build_server()
    if args.http:
        server.run(transport="streamable-http", port=args.port)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
