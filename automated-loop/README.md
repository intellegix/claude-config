# Intellegix Code Agent Toolkit

A self-driving automation loop that pairs **Claude Code CLI** with **Perplexity deep research** via an **MCP browser bridge** to execute multi-step software engineering tasks autonomously. No API keys required — just a [Claude Code subscription](https://claude.ai/code).

The two cornerstones of the toolkit:

1. **Perplexity Research Automation** — Playwright-driven browser automation that runs deep research queries through Perplexity's web UI, giving Claude access to real-time web knowledge between iterations. Free tier, no API key, $0/query.
2. **MCP Browser Bridge** — A Chrome extension + WebSocket bridge that provides reliable browser automation for Claude Code, working around the limitations of Claude's built-in browser capabilities.

> **Note:** The toolkit also includes council automation (multi-model queries via Perplexity), which requires a Perplexity Pro/Max subscription. Research mode works on the free tier.

## Prerequisites

- **Python 3.11+**
- **Claude Code CLI** — installed via `npm install -g @anthropic-ai/claude-code` (requires a Max $20/mo or Team $100/mo subscription; no API key needed)
- **Perplexity account** — free tier works for research queries; login session is cached via Playwright (no API key, $0/query)

## Quick Start

```bash
pip install -r requirements.txt
# Point at any project with a CLAUDE.md:
python loop_driver.py --project /path/to/your/project --max-iterations 10 --verbose
```

That's it. The loop reads your project's `CLAUDE.md` for instructions, spawns Claude Code in `-p` (prompt) mode, streams NDJSON progress, and optionally runs Perplexity research between iterations.

## How It Works

```
┌─────────────┐     NDJSON stream      ┌──────────────┐
│ loop_driver  │ ───────────────────── │  Claude Code  │
│  (Python)    │ ◄───────────────────  │   CLI (-p)    │
└──────┬───────┘   session resume      └──────────────┘
       │
       │  research trigger
       ▼
┌──────────────┐   Playwright browser   ┌──────────────┐
│research_bridge│ ───────────────────── │  Perplexity   │
│              │ ◄───────────────────  │  (web UI)     │
└──────────────┘                        └──────────────┘
       │
       ▼
┌──────────────┐    .workflow/state.json
│ state_tracker │ ─► metrics_summary.json
│              │ ─► trace.jsonl
└──────────────┘
```

**Six modules:**

| Module | Role |
|--------|------|
| `loop_driver.py` | Entry point — spawns `claude -p` with `--dangerously-skip-permissions`, streams NDJSON, manages iteration lifecycle |
| `ndjson_parser.py` | Parses Claude CLI `stream-json` output (`init`, `assistant`, `result`, `system` events) |
| `research_bridge.py` | Runs Perplexity queries via Playwright browser automation with circuit breaker + exponential backoff |
| `state_tracker.py` | Persists loop state, enforces budgets, computes per-model analytics |
| `config.py` | Pydantic validation of `.workflow/config.json` with model-aware scaling |
| `log_redactor.py` | Scrubs API keys and secrets from log output |

## Features

### Research & Browser Automation
- **Perplexity research automation** — deep research queries via Playwright browser session, giving Claude real-time web knowledge ($0/query, no API key)
- **MCP browser bridge** — Chrome extension + WebSocket bridge for reliable browser automation, bypassing Claude's built-in browser limitations
- **Smart completion detection** — stop-button monitoring + MutationObserver + text stability signals to detect when Perplexity finishes
- **Circuit breaker** — trips after 5 consecutive research failures, 120s cooldown with exponential backoff

### Loop Orchestration
- **Zero API keys** — Claude Code subscription handles auth; Perplexity uses browser session
- **Model-aware scaling** — Opus gets 2x timeout + 25-turn cap; Haiku gets 0.5x timeout
- **Automatic model fallback** — falls back (e.g., opus to sonnet) after consecutive timeouts, reverts on productive iteration
- **Session continuity** — `--resume` preserves full context across iterations
- **Session rotation** — auto-rotates after 200 turns or $20/session to prevent context exhaustion
- **Budget enforcement** — per-iteration and total budget caps with graceful exit
- **Stagnation detection** — two-strike system: resets session first, then exits (code 3)
- **Timeout cooldown** — exponential backoff (60s base, 300s cap) between timeout retries

### Observability
- **Trace logging** — JSONL trace with auto-rotation at 10MB
- **Extended preflight** — verifies CLI, CLAUDE.md, git, and .workflow writability before starting
- **Per-model analytics** — tracks iterations, avg cost/turns/duration, timeout and error rates per model
- **Log redaction** — scrubs API keys from all log output

## Usage

```bash
# Full run with defaults (50 iterations, sonnet model)
python loop_driver.py --project /path/to/project --verbose

# Specify model and budget
python loop_driver.py --project . --model opus --max-budget 25.0 --verbose

# Smoke test (single iteration, reduced limits)
python loop_driver.py --smoke-test --verbose

# Dry run (simulate without spawning Claude)
python loop_driver.py --project . --max-iterations 5 --dry-run --verbose

# Custom config file
python loop_driver.py --project . --config /path/to/config.json --verbose

# JSON-structured logging
python loop_driver.py --project . --json-log --verbose
```

### CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--project` | `.` | Target project directory |
| `--max-iterations` | `50` | Maximum loop iterations |
| `--model` | `sonnet` | Claude model (`sonnet`, `opus`, `haiku`) |
| `--prompt` | auto | Initial prompt for the first iteration |
| `--timeout` | `300` | Per-iteration timeout in seconds |
| `--max-budget` | `50.0` | Maximum total budget in USD |
| `--dry-run` | off | Simulate without spawning Claude |
| `--smoke-test` | off | Single-iteration production validation |
| `--verbose` | off | Enable verbose logging |
| `--json-log` | off | Structured JSON log output |
| `--no-stagnation-check` | off | Disable diminishing returns detection |
| `--skip-preflight` | off | Skip CLI preflight verification |
| `--config` | auto | Path to config.json |

### Running Multiple Projects

Each project gets its own `.workflow/` state directory. You can run concurrent loops targeting different projects:

```bash
# Terminal 1
python loop_driver.py --project ~/projects/backend --model opus --verbose

# Terminal 2
python loop_driver.py --project ~/projects/frontend --model sonnet --verbose
```

Never run two loops targeting the same project — they share `.workflow/state.json` and will corrupt state.

## Configuration

The loop uses sensible defaults and works out of the box. For customization, create `.workflow/config.json` in your target project:

```json
{
  "limits": {
    "max_iterations": 50,
    "timeout_seconds": 300,
    "max_total_budget_usd": 50.0,
    "max_per_iteration_budget_usd": 5.0,
    "max_turns_per_iteration": 50,
    "model_timeout_multipliers": { "opus": 2.0, "sonnet": 1.0, "haiku": 0.5 },
    "model_fallback": { "opus": "sonnet" },
    "trace_max_size_bytes": 10000000
  },
  "perplexity": {
    "research_timeout_seconds": 600,
    "headful": true,
    "perplexity_mode": "research"
  },
  "claude": {
    "model": "sonnet",
    "dangerously_skip_permissions": true
  },
  "stagnation": {
    "enabled": true,
    "window_size": 3,
    "max_consecutive_timeouts": 2,
    "session_max_turns": 200,
    "session_max_cost_usd": 20.0
  }
}
```

All fields are optional — unspecified values use defaults.

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| `0` | Project complete | Completion marker detected in Claude output |
| `1` | Max iterations reached | Increase `--max-iterations` or refine CLAUDE.md instructions |
| `2` | Budget exceeded | Increase `--max-budget` or reduce scope |
| `3` | Stagnation detected | Loop stopped making progress; check CLAUDE.md clarity |

## Project Structure

```
automated claude/
├── loop_driver.py        # Entry point + iteration orchestration
├── loop_driver.ps1       # PowerShell wrapper (legacy)
├── ndjson_parser.py      # Claude CLI stream parser
├── research_bridge.py    # Perplexity Playwright integration
├── state_tracker.py      # State persistence + budget enforcement
├── config.py             # Pydantic config models
├── log_redactor.py       # API key scrubbing
├── requirements.txt      # pydantic, pytest
├── CLAUDE.md             # Project instructions for the loop
├── tests/
│   ├── test_loop_driver.py
│   ├── test_ndjson_parser.py
│   ├── test_research_bridge.py
│   ├── test_state_tracker.py
│   ├── test_config.py
│   ├── test_log_redactor.py
│   ├── test_integration.py
│   ├── helpers.py
│   └── conftest.py
└── .workflow/             # Per-project runtime state (gitignored)
    ├── state.json
    ├── trace.jsonl
    └── metrics_summary.json
```

## Deploying to Other Projects

This directory **is** the toolkit. To automate any project:

1. Ensure the target project has a `CLAUDE.md` with clear instructions for Claude
2. Run: `python loop_driver.py --project /path/to/target --verbose`
3. Each target project gets its own `.workflow/` directory for state — nothing is shared

The loop reads the target's `CLAUDE.md`, spawns Claude Code pointing at that directory, and manages the iteration lifecycle. Your target project needs no dependencies on this toolkit.

## Testing

```bash
pytest tests/ -v  # 220 tests
```

## License

MIT
