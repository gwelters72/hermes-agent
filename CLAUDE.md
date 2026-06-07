# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

Hermes Agent is a self-improving AI agent built by Nous Research. It provides a full TUI, a messaging gateway (Telegram, Discord, Slack, WhatsApp, Signal), a cron scheduler, pluggable LLM providers, a skills system, and multiple terminal execution backends (Docker, SSH, Modal, Daytona, Vercel Sandbox).

## Development Setup

```bash
./setup-hermes.sh          # installs uv, creates venv, installs .[all], symlinks ~/.local/bin/hermes
./hermes                   # run from repo root — auto-detects venv
```

Manual equivalent:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv .venv --python 3.11
source .venv/bin/activate
uv pip install -e ".[all,dev]"
```

## Running Tests

```bash
scripts/run_tests.sh                         # full suite (per-file isolation, TZ=UTC)
scripts/run_tests.sh tests/foo.py            # single file
scripts/run_tests.sh tests/foo.py -- --tb=long  # with pytest args
scripts/run_tests.sh -j 4                    # cap parallelism
```

**Do not call `pytest` directly** — `scripts/run_tests.sh` enforces per-file subprocess isolation, deterministic env (`TZ=UTC LANG=C.UTF-8 PYTHONHASHSEED=0`), and hermetic credential blanking. Tests marked `integration` are excluded by default (`-m 'not integration'`).

## Linting / Type Checking

```bash
venv/bin/ruff check .       # lint (only PLW1514 is enforced — explicit file encoding)
venv/bin/ty check           # type checker (configured under [tool.ty] in pyproject.toml)
```

## Architecture

### Entry Points

| Entry point | Module |
|---|---|
| `hermes` (interactive CLI / TUI) | `hermes_cli/main.py` → `cli.py` |
| `hermes-agent` (headless agent) | `run_agent.py` — `AIAgent` class |
| `hermes-acp` (editor ACP adapter) | `acp_adapter/entry.py` |
| Gateway (messaging platforms) | `gateway/run.py` — `GatewayRunner` |
| TUI WebSocket bridge | `tui_gateway/server.py` |

### Core Agent Loop

`run_agent.AIAgent` owns the conversation state. The actual per-turn loop lives in `agent/conversation_loop.py` (`run_conversation`). One turn: model call → tool dispatch → retries/failover → compression check → post-turn hooks (memory nudge, skill review, background curator).

- **Tool dispatch**: `agent/tool_executor.py` + `agent/tool_dispatch_helpers.py`
- **System prompt assembly**: `agent/prompt_builder.py` (identity, skills index, context files)
- **Context compression**: `agent/context_compressor.py`; pluggable via `agent/context_engine.py` abstract base
- **Prompt caching**: `agent/prompt_caching.py`

### Provider Abstraction

All LLM providers are described declaratively as `ProviderProfile` subclasses in `providers/`. The agent constructs an OpenAI-compatible client; provider quirks (auth type, schema transforms, streaming differences) are encapsulated in per-provider adapter modules under `agent/*_adapter.py` (e.g. `anthropic_adapter.py`, `gemini_native_adapter.py`, `bedrock_adapter.py`, `codex_responses_adapter.py`).

### Tool System

Tools self-register by calling `registry.register()` at module level (`tools/registry.py`). `model_tools.py` imports all tool modules and queries the registry. Toolsets (named groups of tools) are declared in `toolsets.py` and distributed in `toolset_distributions.py`. Provider-specific or optional tools are lazy-installed at first use via `tools/lazy_deps.py` — they are **not** in `pyproject.toml`'s `dependencies`.

### Skills System

Skills are directories containing a `SKILL.md` (frontmatter + instructions). Built-in skills live in `skills/` and `optional-skills/`. User skills go in `~/.hermes/skills/`. The curator (`agent/curator.py`) runs as a background auxiliary-model task to maintain agent-created skills (pin/archive/consolidate). Skills are injected into the system prompt at runtime by `agent/prompt_builder.py`.

### Gateway

`gateway/run.py` hosts `GatewayRunner`, which loads platform adapters from `gateway/platform_registry.py`. Each platform (Telegram, Discord, Slack, etc.) is a separate adapter module. Sessions are per-platform-user, managed in `gateway/session.py`. The TUI bridge (`tui_gateway/`) exposes gateway events over WebSocket to the web dashboard.

### Memory & State

- Runtime config / credentials: `~/.hermes/` (controlled by `hermes_constants.get_hermes_home()`)
- Persistent state (SQLite WAL): `hermes_state.py`
- Memory tool / MEMORY.md: `tools/memory_tool.py` + `agent/memory_manager.py`
- Honcho dialectic user modeling: optional integration via `tools/lazy_deps.py`

### Dependency Policy

All `dependencies` in `pyproject.toml` are **exact-pinned** (`==X.Y.Z`) — no ranges. This was tightened after the Mini Shai-Hulud supply-chain incident (mistralai 2.4.6, 2026-05-12). When bumping a dep: update the pin **and** run `uv lock` to regenerate `uv.lock`. Provider/optional backends belong in optional extras and `tools/lazy_deps.py`, not in `dependencies`.

### Plugins

Plugin directories under `plugins/` can register tools, context engines, dashboard UIs, and platform adapters. A plugin is discovered when it provides a `register()` callable at its top level.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **hermes-agent** (135631 symbols, 236157 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/hermes-agent/context` | Codebase overview, check index freshness |
| `gitnexus://repo/hermes-agent/clusters` | All functional areas |
| `gitnexus://repo/hermes-agent/processes` | All execution flows |
| `gitnexus://repo/hermes-agent/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
