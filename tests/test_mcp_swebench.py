"""SWE-bench tools against a throwaway git repo (TESTBED_PATH), directly and over MCP stdio."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

import mcp_tools_swebench as tools
from agent_smith.mcp_client.client import MCPClient

SERVER = str(Path(__file__).resolve().parent.parent / "mcp_tools_swebench.py")

CORE = '''\
class Foo:
    def bar(self):
        return helper(1)


def helper(x):
    return x + 1
'''
UTIL = '''\
from pkg.core import helper

print(helper(2))  # helper is used here
'''


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = Path(os.path.realpath(tmp_path)) / "testbed"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "__init__.py").write_text("")
    (root / "pkg" / "core.py").write_text(CORE)
    (root / "pkg" / "util.py").write_text(UTIL)
    (root / "README.txt").write_text("helper docs\n")
    _git(root, "init", "-q")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    monkeypatch.setenv("TESTBED_PATH", str(root))
    for var in ("EVAL_SCRIPT_PATH", "EVAL_SCRIPT"):
        monkeypatch.delenv(var, raising=False)
    return root


# -- file system ---------------------------------------------------------------

def test_read_file_format_and_ranges(repo):
    assert tools.read_file("pkg/core.py", 1, 2) == "1: class Foo:\n2:     def bar(self):"
    assert tools.read_file(str(repo / "pkg/core.py"), 6, 99) == "6: def helper(x):\n7:     return x + 1"
    assert tools.read_file("pkg/core.py").startswith("1: class Foo:")
    assert tools.read_file("pkg/core.py", 50, 60).startswith("Error:")
    assert tools.read_file("missing.py").startswith("Error: file not found")
    assert tools.read_file("pkg").startswith("Error:")


def test_read_file_caps_unbounded_reads(repo, monkeypatch):
    monkeypatch.setattr(tools, "DEFAULT_READ_LINES", 3)
    out = tools.read_file("pkg/core.py")
    assert out.splitlines()[:3] == ["1: class Foo:", "2:     def bar(self):", "3:         return helper(1)"]
    assert "file has 7 lines" in out
    assert "7: " in tools.read_file("pkg/core.py", 1, 7)  # an explicit range is not capped


def test_edit_file(repo):
    out = tools.edit_file("pkg/core.py", "return x + 1", "return x + 2")
    assert out.startswith("Edited") and "7:     return x + 2" in out
    assert "return x + 2" in (repo / "pkg/core.py").read_text()

    assert "not found" in tools.edit_file("pkg/core.py", "nope", "x")
    assert "fix the indentation" in tools.edit_file("pkg/core.py", "      def bar(self):", "x")
    assert "occurs 2 times" in tools.edit_file("pkg/core.py", "return", "yield")
    assert "identical" in tools.edit_file("pkg/core.py", "Foo", "Foo")
    assert "no longer parses" in tools.edit_file("pkg/core.py", "def helper(x):", "def helper(x:")


def test_edit_file_creates_new_file(repo):
    assert tools.edit_file("pkg/new.py", "", "X = 1\n").startswith("Created")
    assert (repo / "pkg/new.py").read_text() == "X = 1\n"
    assert "already exists" in tools.edit_file("pkg/new.py", "", "X = 2\n")


def test_list_files(repo):
    assert tools.list_files("pkg", "*.py").splitlines() == [
        f"{repo}/pkg/__init__.py", f"{repo}/pkg/core.py", f"{repo}/pkg/util.py"]
    everything = tools.list_files(".", "**/*")
    assert f"{repo}/pkg/" in everything.splitlines() and ".git" not in everything
    assert tools.list_files(".", "*.rs").startswith("No files")
    assert tools.list_files("nope").startswith("Error:")


# -- search --------------------------------------------------------------------

def test_search_code_format(repo):
    out = tools.search_code(r"helper\(", "*.py")
    assert out.splitlines() == [
        f"{repo}/pkg/core.py:3 return helper(1)",
        f"{repo}/pkg/core.py:6 def helper(x):",
        f"{repo}/pkg/util.py:3 print(helper(2))  # helper is used here",
    ]
    assert tools.search_code("helper", "*.txt") == f"{repo}/README.txt:1 helper docs"
    assert tools.search_code("helper", "pkg/u*.py").count("\n") == 1
    assert "plain text" in tools.search_code("helper(", "*.py")
    assert tools.search_code("zzz_nothing").startswith("No matches")


def test_search_definition(repo):
    assert tools.search_function_or_class_definition_in_code("helper") == f"{repo}/pkg/core.py:6 def helper(x):"
    assert tools.search_function_or_class_definition_in_code("Foo") == f"{repo}/pkg/core.py:1 class Foo:"
    assert tools.search_function_or_class_definition_in_code("Foo.bar") == f"{repo}/pkg/core.py:2 def bar(self):"
    assert tools.search_function_or_class_definition_in_code("Nope").startswith("No definitions")


def test_find_references(repo):
    out = tools.find_references("helper", str(repo / "pkg/core.py"), 6).splitlines()
    assert f"{repo}/pkg/util.py:1 from pkg.core import helper" in out
    assert f"{repo}/pkg/core.py:3 return helper(1)" in out
    assert len(out) == 4
    assert "does not appear" in tools.find_references("helper", "pkg/core.py", 1)


# -- execution -----------------------------------------------------------------

def test_run_command(repo, monkeypatch):
    out = tools.run_command("echo hi; echo oops >&2; exit 3", "pkg")
    assert out == "exit_code: 3\n--- stdout ---\nhi\n\n--- stderr ---\noops\n"
    assert str(repo / "pkg") in tools.run_command("pwd", "pkg")
    assert tools.run_command("ls", "missing").startswith("Error:")

    monkeypatch.setattr(tools, "COMMAND_TIMEOUT", 1)
    assert "timed out" in tools.run_command("echo start; sleep 10")


def test_run_tests(repo, tmp_path, monkeypatch):
    assert tools.run_tests().startswith("Error: no evaluation script")
    script = tmp_path / "eval.sh"
    script.write_text("cd pkg && ls core.py && echo FAILED >&2 && exit 1\n")
    monkeypatch.setenv("EVAL_SCRIPT_PATH", str(script))
    assert tools.run_tests() == "exit_code: 1\ncore.py\nFAILED\n"
    monkeypatch.delenv("EVAL_SCRIPT_PATH")
    monkeypatch.setenv("EVAL_SCRIPT", "echo PASSED")
    assert tools.run_tests() == "exit_code: 0\nPASSED\n"


def test_get_patch(repo):
    assert tools.get_patch() == ""
    os.chmod(repo / "pkg/core.py", 0o755)  # mode changes are ignored
    assert tools.get_patch() == ""
    tools.edit_file("pkg/core.py", "return x + 1", "return x + 2")
    patch = tools.get_patch()
    assert patch.startswith("diff --git a/pkg/core.py b/pkg/core.py")
    assert "-    return x + 1\n+    return x + 2" in patch


# -- over MCP ------------------------------------------------------------------

def test_server_over_stdio(repo):
    with MCPClient(stdio_command=f"env TESTBED_PATH={repo} {sys.executable} {SERVER}") as client:
        schemas = {t["name"]: list(t["input_schema"]["properties"]) for t in client.list_tools()}
        assert schemas == {
            "read_file": ["filepath", "start_line", "end_line"],
            "edit_file": ["filepath", "old_str", "new_str"],
            "list_files": ["directory", "pattern"],
            "search_code": ["pattern", "file_pattern"],
            "search_function_or_class_definition_in_code": ["name"],
            "find_references": ["name", "filepath", "line"],
            "run_tests": [],
            "get_patch": [],
            "run_command": ["command", "workdir"],
        }
        fns = client.as_python_functions()
        assert fns["read_file"]("pkg/core.py", 6, 6) == "6: def helper(x):"
        fns["edit_file"](filepath="pkg/core.py", old_str="x + 1", new_str="x + 2")
        assert "+    return x + 2" in fns["get_patch"]()
