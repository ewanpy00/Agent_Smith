# PROGRESS — Agent Smith

Stage tracker for the project. Legend: ✅ done · 🟡 partial · ⬜ not started

Current state: a complete skeleton (signatures + docstrings referencing the subject
sections), working Pydantic models, and a few smoke tests. All logic is still
`raise NotImplementedError`.

---

## Overall stage

**Stage 1 of 5: skeleton.** Next up: the sandbox first, then MBPP end-to-end, then
SWE-bench, then the benchmark and the write-ups.

| # | Stage | Status |
|---|-------|--------|
| 1 | Skeleton: models, config, limits, package layout | ✅ |
| 2 | Sandbox + MCP + CLI (`uv run sandbox`) | 🟡 sandbox, MCP client/server, manual done |
| 3 | MBPP agent end-to-end (passes the moulinette) | ⬜ |
| 4 | SWE-bench agent end-to-end (Docker + tools) | ⬜ |
| 5 | Model benchmark, README, final polish | ⬜ |

---

## Modules

### Foundation

| Module | What it does | Status |
|--------|--------------|--------|
| `models.py` | `MBPPTaskInput`, `SWEBenchTaskInput`, `StepMetrics`, `SolutionOutput`, `SandboxConfig` | ✅ |
| `agent_smith/config.py` | loads `sandbox_template.json` into the model | ✅ |
| `agent_smith/agent/limits.py` | MBPP / SWE-bench limits from the subject | ✅ |
| `tests/test_models.py` | smoke tests for models and limits | ✅ |

### Sandbox (stage 2 — most important, it has its own exam script)

| Module | What it does | Status |
|--------|--------------|--------|
| `sandbox/restrictions.py` | safe builtins, allowlist import hook, AST check, path checks, network block, memory limit | ✅ |
| `sandbox/worker.py` | the isolated process: persistent namespace, streamed output, tool proxies, `final_answer` | ✅ |
| `sandbox/executor.py` | `Sandbox.execute()` — separate process, persistent state, timeout, RSS watchdog, tool bridge | ✅ |
| `sandbox/cli.py` | REPL `uv run sandbox [config.json]` works; `--mcp-stdio / --mcp-server` wired to the MCP client | ✅ |
| `tests/test_sandbox_security.py` | 7 tests mirroring `exam_sandbox.sh` + state / final_answer / SystemExit (MCP test uses a fake tool until the client exists) | ✅ |

Constraints: stdlib only, no RestrictedPython. `KeyboardInterrupt` / `SystemExit` must not
be swallowed. `final_answer` is not an MCP tool — it always lives in the sandbox itself.

### MCP

| Module | What it does | Status |
|--------|--------------|--------|
| `mcp_client/client.py` | client: stdio + streamable HTTP, dynamic discovery of tools/resources/prompts | ✅ |
| `mcp_client/manual.py` | manual generated from tool schemas (fed into the system prompt) | ✅ |
| `mcp_tools_mbpp.py` | MCP server: `run_tests(code, test_list)` (stdio and `--http`) | ✅ |
| `tests/test_mcp_client.py` | client against the real server over stdio + HTTP, and from inside the sandbox | ✅ |
| `mcp_tools_swebench.py` | MCP server: the 9 mandatory tools (fs / search / exec), repo path from `TESTBED_PATH` | ⬜ |

The system is tested against an **unknown** MCP server — nothing about tools may be hardcoded.

### Agent core

| Module | What it does | Status |
|--------|--------------|--------|
| `extraction/extractor.py` | parse the LLM response: ```python block, XML, Hermes JSON, ReAct → Python calls | ⬜ |
| `prompts/system.py` | system prompt: role, Thought/Code/Observation slots, manual, examples | ⬜ |
| `agent/loop.py` | Thought → Code → Observation loop, stop conditions, explicit feedback on every failure | ⬜ |
| `agent/metrics.py` | collect `StepMetrics`, build `SolutionOutput` | ⬜ |

### LLM layer

| Module | What it does | Status |
|--------|--------------|--------|
| `llm/base.py` | `LLMClient` / `LLMResponse` interface | ✅ (contract only) |
| `llm/key_pool.py` | several keys per provider, rotation on 429 / quota exhaustion | ⬜ |
| `llm/openai_compatible.py` | `/chat/completions` client, retries, stop sequences, token accounting | ⬜ |

Keys come from the environment only (`OPENROUTER_API_KEY=key1,key2`); a hardcoded key fails the review.

### Agent CLIs

| Module | What it does | Status |
|--------|--------------|--------|
| `agent_mbpp/__main__.py` | args are parsed, pipeline wiring is missing | 🟡 |
| `agent_swebench/__main__.py` | same, plus image pull, container, guaranteed cleanup on SIGTERM | 🟡 |
| `pyproject.toml` | `sandbox` script and build backend added; still no dependencies (mcp, http client, dotenv, docker) | 🟡 |

### Documents and reports

| Artifact | Status |
|----------|--------|
| `README.md` (architecture, agent loop, sandbox design, tools, results; first line italic, 42 curriculum) | ⬜ empty |
| `BENCHMARK_REPORT.md` (≥5 models × ≥2 providers × ≥3 SWE-bench tasks + ablation + conclusions) | ⬜ |
| `solution.json` files backing the benchmark | ⬜ |

---

## Order of work

1. **Sandbox without MCP** — restrictions → executor → un-skip the security tests.
2. **MCP** — client (stdio), `mcp_tools_mbpp.py`, tool injection into the sandbox, the manual, then the HTTP transport and the `uv run sandbox` REPL.
3. **LLM layer** — key pool → OpenAI-compatible client with stop sequences and token counting.
4. **MBPP end-to-end** — extractor → prompt → loop → metrics → `agent_mbpp`. Target: `moulinette_eval validate mbpp` green on one task, then 4/5.
5. **SWE-bench** — the 9 tools + Docker plumbing + cleanup, debugged on `sympy__sympy-14711`, `sympy__sympy-13480`, `pydata__xarray-4629`. Target: 2/3.
6. **Benchmark and documents** — run the models, write the report, fill in the README.

Advice from the subject: first prove the whole thing works on the easiest task **without**
token/iteration limits, and only then tighten the constraints.

---

## Pass criteria

- MBPP 4/5, SWE-bench 2/3 (no retries during the exam)
- All limits respected: MBPP 10 iterations / 6k in / 1.5k out / 120 s · SWE-bench 30 / 300k / 10k / 900 s
- `exam_sandbox.sh` — all 7 tests
- Mandatory tools pass their independent tests
- No keys in the source, free tier only
- At the defense: a small live change to the agent (2–5 min) and a re-run on an MBPP task
