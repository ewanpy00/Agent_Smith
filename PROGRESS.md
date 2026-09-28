# PROGRESS — Agent Smith

Трекер стадий проекта. Легенда: ✅ готово · 🟡 частично · ⬜ не начато

Сейчас в репозитории: полный скелет модулей (сигнатуры + докстринги со ссылками
на разделы сабжекта), работающие Pydantic-модели и базовые тесты. Вся логика —
`raise NotImplementedError`.

---

## Общая стадия

**Стадия 1 из 5: каркас.** Дальше — сначала песочница, потом MBPP-агент end-to-end,
потом SWE-bench, потом бенчмарк и документы.

| # | Стадия | Статус |
|---|--------|--------|
| 1 | Каркас: модели, конфиг, лимиты, структура пакетов | ✅ |
| 2 | Песочница + MCP + CLI (`uv run sandbox`) | ⬜ |
| 3 | MBPP-агент end-to-end (проходит moulinette) | ⬜ |
| 4 | SWE-bench-агент end-to-end (Docker + tools) | ⬜ |
| 5 | Бенчмарк моделей, README, финальная полировка | ⬜ |

---

## Модули

### Основа

| Модуль | Что делает | Статус |
|--------|-----------|--------|
| `models.py` | `MBPPTaskInput`, `SWEBenchTaskInput`, `StepMetrics`, `SolutionOutput`, `SandboxConfig` | ✅ |
| `agent_smith/config.py` | загрузка `sandbox_template.json` в модель | ✅ |
| `agent_smith/agent/limits.py` | лимиты MBPP / SWE-bench из сабжекта | ✅ |
| `tests/test_models.py` | смоук-тесты моделей и лимитов | ✅ |

### Песочница (стадия 2, самая важная — отдельный exam-скрипт)

| Модуль | Что делает | Статус |
|--------|-----------|--------|
| `sandbox/restrictions.py` | безопасные builtins, import-hook по allowlist, проверка путей, блок сети, лимит памяти | ⬜ |
| `sandbox/executor.py` | `Sandbox.execute()` — отдельный процесс, persistent state, таймаут, `final_answer`, инъекция MCP-тулов | ⬜ |
| `sandbox/cli.py` | REPL `uv run sandbox [config.json] [--mcp-stdio / --mcp-server]` | ⬜ |
| `tests/test_sandbox_security.py` | 7 тестов зеркалят `exam_sandbox.sh` (сейчас все `skip`) | ⬜ |

Требования: только stdlib, никакого RestrictedPython. `KeyboardInterrupt` / `SystemExit`
не глотать. `final_answer` — не MCP-тул, живёт в самой песочнице всегда.

### MCP

| Модуль | Что делает | Статус |
|--------|-----------|--------|
| `mcp_client/client.py` | клиент: stdio + streamable HTTP, динамический discovery тулов/ресурсов/промптов | ⬜ |
| `mcp_client/manual.py` | генерация мануала по схемам тулов (для системного промпта) | ⬜ |
| `mcp_tools_mbpp.py` | MCP-сервер: `run_tests(code, test_list)` | ⬜ |
| `mcp_tools_swebench.py` | MCP-сервер: 9 обязательных тулов (fs / search / exec), путь из `TESTBED_PATH` | ⬜ |

Система тестируется с **неизвестным** MCP-сервером → ничего про тулы не хардкодить.

### Ядро агента

| Модуль | Что делает | Статус |
|--------|-----------|--------|
| `extraction/extractor.py` | парсинг ответа LLM: ```python-блок, XML, Hermes JSON, ReAct → Python-вызовы | ⬜ |
| `prompts/system.py` | системный промпт: роль, слоты Thought/Code/Observation, мануал, примеры | ⬜ |
| `agent/loop.py` | цикл Thought → Code → Observation, стоп-условия, явный фидбек об ошибках | ⬜ |
| `agent/metrics.py` | сбор `StepMetrics`, сборка `SolutionOutput` | ⬜ |

### LLM-слой

| Модуль | Что делает | Статус |
|--------|-----------|--------|
| `llm/base.py` | интерфейс `LLMClient` / `LLMResponse` | ✅ (только контракт) |
| `llm/key_pool.py` | несколько ключей на провайдера, ротация при 429/квоте | ⬜ |
| `llm/openai_compatible.py` | клиент `/chat/completions`, ретраи, stop-последовательности, учёт токенов | ⬜ |

Ключи — только из env (`OPENROUTER_API_KEY=key1,key2`), хардкод = провал ревью.

### CLI агентов

| Модуль | Что делает | Статус |
|--------|-----------|--------|
| `agent_mbpp/__main__.py` | аргументы разобраны, сборка пайплайна — нет | 🟡 |
| `agent_swebench/__main__.py` | то же + pull образа, контейнер, гарантированный cleanup по SIGTERM | 🟡 |
| `pyproject.toml` | нет `[project.scripts]` для `sandbox`, нет зависимостей (mcp, http-клиент, dotenv, docker) | 🟡 |

### Документы и отчёты

| Артефакт | Статус |
|----------|--------|
| `README.md` (архитектура, цикл агента, дизайн песочницы, тулы, результаты; первая строка — курсив про 42) | ⬜ пустой |
| `BENCHMARK_REPORT.md` (≥5 моделей × ≥2 провайдера × ≥3 SWE-bench задачи + ablation + выводы) | ⬜ |
| `solution.json` файлы, подтверждающие бенчмарк | ⬜ |

---

## Порядок работ

1. **Песочница без MCP** — restrictions → executor → снять `skip` с тестов безопасности.
2. **MCP** — клиент (stdio), `mcp_tools_mbpp.py`, инъекция тулов в песочницу, мануал, затем HTTP-транспорт и `uv run sandbox` REPL.
3. **LLM-слой** — key pool → openai-совместимый клиент со stop-последовательностями и подсчётом токенов.
4. **MBPP end-to-end** — extractor → промпт → loop → metrics → `agent_mbpp`. Цель: `moulinette_eval validate mbpp` зелёный на одной задаче, потом 4/5.
5. **SWE-bench** — 9 тулов + Docker-обвязка + cleanup, отладка на `sympy__sympy-14711`, `sympy__sympy-13480`, `pydata__xarray-4629`. Цель: 2/3.
6. **Бенчмарк и документы** — прогнать модели, собрать отчёт, дописать README.

Совет из сабжекта: сначала доказать, что всё работает на самой простой задаче
**без** лимитов токенов/итераций, и только потом закручивать ограничения.

---

## Критерии сдачи

- MBPP 4/5, SWE-bench 2/3 (ретраев на экзамене нет)
- Все лимиты соблюдены: MBPP 10 итераций / 6k in / 1.5k out / 120 c · SWE-bench 30 / 300k / 10k / 900 c
- `exam_sandbox.sh` — все 7 тестов
- Обязательные тулы проходят независимые тесты
- Никаких ключей в коде, только free tier
- На защите — быстрая правка агента вживую (2–5 мин) и перезапуск на MBPP
