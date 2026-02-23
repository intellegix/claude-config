# intellegix-code-agent-toolkit

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Node.js 18+](https://img.shields.io/badge/Node.js-18+-green.svg)](https://nodejs.org)
[![Tests: 194](https://img.shields.io/badge/Tests-194-brightgreen.svg)](automated-loop/tests/)

A modular configuration system for Claude Code CLI. Includes an automated loop driver, custom slash commands, multi-model council automation, MCP browser bridge, and portfolio governance.

## Features

- **Automated Loop Driver** - Run Claude Code in autonomous loops with session continuity, budget enforcement, stagnation detection, and model-aware scaling
- **Custom Slash Commands** - 15+ reusable commands for research, planning, code review, and deployment workflows
- **Council Automation** - Multi-model queries via Perplexity (GPT, Claude, Gemini) with Opus synthesis
- **MCP Browser Bridge** - Chrome extension bridge for browser automation through Claude Code
- **Portfolio Governance** - Project tier system with phase restrictions and complexity budgets
- **Perplexity Integration** - Playwright-based research queries using your Perplexity Pro subscription ($0/query)

## Repository Structure

```
~/.claude/
├── CLAUDE.md.example          # Global Claude Code instructions (template)
├── LICENSE                    # MIT License
├── NOTICE                     # Trademark disclaimers
├── README.md                  # This file
├── perplexity-selectors.json  # Perplexity UI selectors for automation
│
├── automated-loop/            # Automated Claude Code loop driver
│   ├── loop_driver.py         # Main entry point
│   ├── config.py              # Pydantic config with model-aware scaling
│   ├── ndjson_parser.py       # Claude CLI NDJSON stream parser
│   ├── research_bridge.py     # Perplexity research via Playwright
│   ├── state_tracker.py       # Workflow state persistence + budget
│   ├── log_redactor.py        # API key scrubbing from logs
│   ├── loop_driver.ps1        # PowerShell wrapper
│   └── tests/                 # 194 pytest tests
│
├── commands/                  # Custom slash commands
│   ├── research-perplexity.md # Deep research via Perplexity
│   ├── smart-plan.md          # Multi-phase project planning
│   ├── council-refine.md      # Multi-model plan refinement
│   ├── export-to-council.md   # Export session for council review
│   ├── fix-issue.md           # GitHub issue resolution
│   ├── implement.md           # Feature implementation
│   ├── review.md              # Code review
│   ├── handoff.md             # Agent handoff
│   └── ...                    # 15+ commands total
│
├── council-automation/        # Multi-model council system
│   ├── council_browser.py     # Playwright-based Perplexity automation
│   ├── council_config.py      # Council configuration
│   ├── council_query.py       # Query orchestration
│   ├── session_context.py     # Session/cookie management
│   ├── refresh_session.py     # Session cookie refresh script
│   └── synthesis_prompt.md    # Opus synthesis prompt template
│
├── mcp-servers/
│   └── browser-bridge/        # MCP Browser Bridge server
│       ├── server.js           # MCP protocol handler
│       ├── extension/          # Chrome extension (load unpacked)
│       │   ├── manifest.json   # MV3 manifest
│       │   ├── background.js   # Service worker + WebSocket client
│       │   ├── content.js      # DOM interaction helpers
│       │   └── popup.html      # Connection status popup
│       ├── lib/                # Server modules
│       │   ├── websocket-bridge.js
│       │   ├── context-manager.js
│       │   ├── rate-limiter.js
│       │   └── ...
│       └── test-*.js           # Integration tests
│
└── portfolio/                 # Portfolio governance
    ├── PORTFOLIO.md.example   # Project registry + tier system (template)
    ├── DECISIONS.md           # Architecture decision records
    └── PROJECT_TEMPLATE.md    # New project template
```

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Claude Code CLI                         │
│                  (claude -p --stream-json)                 │
├──────────────┬────────────────────────┬───────────────────┤
│              │                        │                   │
│   ┌──────────▼──────────┐   ┌────────▼────────┐         │
│   │   Loop Driver        │   │  Slash Commands  │         │
│   │   (loop_driver.py)   │   │  (commands/*.md)  │        │
│   │                      │   └────────┬────────┘         │
│   │  ┌──────────────┐   │            │                   │
│   │  │ NDJSON Parser │   │   ┌────────▼────────┐         │
│   │  └──────┬───────┘   │   │ Council Automation│        │
│   │         │            │   │ (Playwright →     │        │
│   │  ┌──────▼───────┐   │   │  Perplexity)      │        │
│   │  │ State Tracker │   │   └─────────────────┘         │
│   │  │ + Budget      │   │                               │
│   │  └──────┬───────┘   │   ┌─────────────────┐         │
│   │         │            │   │ MCP Browser Bridge│        │
│   │  ┌──────▼───────┐   │   │ (WebSocket ↔      │        │
│   │  │Research Bridge│   │   │  Chrome Extension)│        │
│   │  └──────────────┘   │   └─────────────────┘         │
│   └──────────────────────┘                               │
└──────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- Python 3.11+ (for automated loop and council automation)
- Node.js 18+ (for MCP browser bridge)
- Perplexity Pro subscription (for research features, optional)

### Installation

```bash
# Clone to ~/.claude (or your Claude Code config directory)
git clone https://github.com/intellegix/intellegix-code-agent-toolkit.git ~/.claude

# Install automated loop dependencies
cd ~/.claude/automated-loop
pip install -r requirements.txt

# Install council automation dependencies
cd ~/.claude/council-automation
pip install -r requirements.txt

# Install MCP browser bridge dependencies
cd ~/.claude/mcp-servers/browser-bridge
npm install
```

### First Loop Run

```bash
cd ~/.claude/automated-loop

# Smoke test (1 iteration, safe defaults)
python loop_driver.py --smoke-test --verbose

# Run against a project
python loop_driver.py --project /path/to/your/project --max-iterations 10 --verbose

# With model selection
python loop_driver.py --project /path/to/project --model opus --timeout 600 --verbose
```

## Perplexity Setup

Council, research, and labs features use Perplexity browser automation. Setup is required before first use.

### Requirements

| Feature | Subscription |
|---------|-------------|
| `/council` (multi-model) | Perplexity **Max** |
| `/research` (deep research) | Perplexity Pro or Max |
| `/labs` (experimental) | Perplexity Pro or Max |

### Step 1: Create Perplexity Custom Shortcuts

The toolkit types `/council`, `/research`, and `/labs` into Perplexity's input to activate modes. These must exist as Perplexity shortcuts:

1. Go to [perplexity.ai/settings](https://perplexity.ai/settings) > Shortcuts
2. Create three custom shortcuts:
   - **`/council`** — Activates Model Council (queries 3 models simultaneously)
   - **`/research`** — Activates Deep Research mode
   - **`/labs`** — Activates Labs (experimental) mode

### Step 2: Cache Session Cookies

The toolkit uses your browser login session — no Perplexity API key needed ($0/query).

1. Install the **MCP Browser Bridge** Chrome extension included in this repo:
   - Open `chrome://extensions` → enable **Developer mode** → **Load unpacked** → select `~/.claude/mcp-servers/browser-bridge/extension/`
   - See [MCP Browser Bridge](#mcp-browser-bridge) below for full setup (server + Claude Code config)
   - *Note: Anthropic's official "Claude in Chrome" extension is still in beta and has [known Bun runtime issues on Windows](https://github.com/anthropics/claude-code/issues/24034) that prevent the native host from connecting. The team is actively working on fixes. This toolkit uses its own extension to avoid those issues.*
2. Log into [perplexity.ai](https://perplexity.ai) in Chrome
3. From Claude Code, run: `/cache-perplexity-session`
4. Session saves to `~/.claude/config/perplexity-session.json` (24h TTL)

**Refresh expired sessions:**
```bash
cd ~/.claude/council-automation
python refresh_session.py            # headful refresh (~6s)
python refresh_session.py --validate # refresh + test query
```

## Components

### Automated Loop Driver

Runs Claude Code CLI in autonomous loops with NDJSON streaming, session continuity, and safety guardrails.

```bash
# Basic usage
python loop_driver.py --project . --max-iterations 50

# With budget limit
python loop_driver.py --project . --max-iterations 50 --max-cost 25.00

# Dry run (no Claude invocation)
python loop_driver.py --project . --dry-run --verbose

# Run tests
pytest tests/ -v
```

**Exit codes**: 0 = complete, 1 = max iterations, 2 = budget exceeded, 3 = stagnation

**Key features**:
- Model-aware scaling (Opus: 2x timeout, 25-turn cap)
- Model fallback (Opus -> Sonnet after consecutive timeouts)
- Exponential backoff with timeout cooldown
- Session continuity via `--resume`
- Stagnation detection with two-strike system
- Budget enforcement per-iteration and cumulative

### Supervising the Automation Loop

The loop driver is autonomous, but the **human operator remains in control**. Claude Code is your control plane — you launch the loop, monitor its progress, and steer the project between runs.

#### Launching & Managing

Run `loop_driver.py` from a Claude Code session or a separate terminal. The loop spawns Claude Code CLI as a worker:

```
claude -p "<prompt>" --output-format stream-json --dangerously-skip-permissions --resume <sessionId>
```

Each iteration streams NDJSON events (`init`, `assistant`, `result`, `system`). The driver extracts cost, turns, and completion markers automatically.

#### Auditing Progress

The loop writes state to `<project>/.workflow/`:

| File | Purpose |
|------|---------|
| `state.json` | Full cycle history — iteration count, cost per cycle, turns, session IDs |
| `trace.jsonl` | Append-only event log (loop_start, claude_invoke, claude_complete, research_start, timeout_detected, model_fallback, stagnation_exit, etc.) |
| `metrics_summary.json` | Written on every exit — total cost, iterations, turns, error count |
| `research_result.md` | Latest Perplexity research response |

Review these between runs (or during, via `tail -f trace.jsonl`) to decide whether the loop is making progress.

#### Deciding When to Stop

The loop exits automatically on:
- `PROJECT_COMPLETE` marker in output → exit 0
- Max iterations reached → exit 1
- Budget exceeded → exit 2
- Stagnation detected → exit 3

Between runs, read the loop's output and `state.json` to audit what was accomplished. If more phases remain, restart the loop. If the work needs course correction, revise `CLAUDE.md` first.

#### Revising the Blueprint (CLAUDE.md)

The loop's default prompt instructs Claude to "Read CLAUDE.md first" — it's the project's source of truth for what to build. The operator edits `CLAUDE.md` between loop runs to add/remove/reorder phases, update status markers, or change priorities.

The loop never modifies `CLAUDE.md` itself — the human retains full editorial control. This is how you steer multi-session projects: update `CLAUDE.md`, restart the loop.

#### Known Limitations

**Concurrent Perplexity Research Queries**

When running multiple loop instances that each trigger Perplexity research, only one query typically succeeds. Each research query launches a headful Chromium instance using the same Perplexity session cookies (`~/.claude/config/playwright-session.json`). Perplexity's web UI is designed for single-user interaction — concurrent browsers presenting the same session get errors or incomplete results. The toolkit includes a `SessionSemaphore` (max 3 concurrent browser slots), but Perplexity's own session handling means concurrent queries from the same account rarely all succeed.

**Workaround**: Run research-heavy loops sequentially, or stagger start times so research phases don't overlap.

**Research Query Retries**

Failed research queries automatically retry up to **3 times** with exponential backoff:
- Delay schedule: ~1s → ~2s → ~4s (base 1.0s × 2^attempt, with random jitter ±50%, capped at 30s)
- Retryable errors: timeouts, Playwright errors, parse failures
- A **circuit breaker** trips after 5 consecutive failures, pausing research for 120s before allowing retries

Transient Perplexity/Cloudflare issues are handled automatically — the loop continues even if research fails.

### Custom Slash Commands

Place in `~/.claude/commands/` and invoke from Claude Code with `/<command-name>`.

| Command | Description |
|---------|-------------|
| `/research-perplexity` | Deep research via Perplexity browser automation |
| `/smart-plan` | Multi-phase project planning |
| `/council-refine` | Multi-model plan refinement with Opus synthesis |
| `/export-to-council` | Export session context for council review |
| `/fix-issue` | GitHub issue investigation and resolution |
| `/implement` | Feature implementation workflow |
| `/review` | Code review workflow |
| `/handoff` | Agent-to-agent handoff documentation |
| `/portfolio-status` | Portfolio-wide project status review |
| `/cache-perplexity-session` | Refresh Perplexity browser session cookies |

#### Authoring Custom Commands

Create a markdown file in `~/.claude/commands/` — Claude Code auto-discovers all `.md` files in this directory. No YAML frontmatter needed; the file is pure markdown.

Use `$ARGUMENTS` as a placeholder for whatever the user types after the command name:

```markdown
# Explain Code

Explain the following code in detail: $ARGUMENTS

## Instructions
- Identify the language and framework
- Describe the overall purpose
- Walk through the logic step by step
- Note any potential issues or improvements
```

Save this as `~/.claude/commands/explain.md`, then invoke it from Claude Code:

```
/explain src/utils/parser.py
```

The `$ARGUMENTS` variable is replaced with `src/utils/parser.py` at invocation time.

### Council Automation

Queries multiple AI models through Perplexity and synthesizes results with Opus.

```bash
# Setup: cache your Perplexity login session
# (run /cache-perplexity-session from Claude Code)

# Direct CLI usage
cd ~/.claude/council-automation
python council_browser.py --headful --perplexity-mode research "your query here"
```

### MCP Browser Bridge

WebSocket bridge between Claude Code CLI and Chrome. Both the server and extension are required.

#### Chrome Extension

1. Open `chrome://extensions` in Chrome
2. Enable **Developer mode** (top-right toggle)
3. Click **Load unpacked** → select `~/.claude/mcp-servers/browser-bridge/extension/`
4. Pin the extension — popup shows connection status (green = connected)

#### MCP Server

```bash
cd ~/.claude/mcp-servers/browser-bridge
npm install  # first time only
npm start
```

The extension auto-connects to `ws://127.0.0.1:8765`.

#### Claude Code Configuration

MCP servers are configured in `~/.claude/mcp.json` (global) or `.mcp.json` (project-level), **not** in `settings.json`.

```json
{
  "mcpServers": {
    "browser-bridge": {
      "command": "node",
      "args": ["C:\\Users\\YourName\\.claude\\mcp-servers\\browser-bridge\\server.js"]
    }
  }
}
```

A more complete example with multiple servers:

```json
{
  "mcpServers": {
    "browser-bridge": {
      "command": "node",
      "args": ["C:\\Users\\YourName\\.claude\\mcp-servers\\browser-bridge\\server.js"]
    },
    "playwright": {
      "command": "npx",
      "args": ["-y", "@executeautomation/playwright-mcp-server"]
    }
  }
}
```

Each server entry supports `command` (executable), `args` (argument array), and optionally `env` (environment variable overrides).

> **Windows note**: Use absolute paths with double-backslash escaping in JSON. The `~` shorthand does not expand inside JSON values.

**CLI shortcut**: You can also add servers via the command line:
```bash
claude mcp add browser-bridge -- node ~/.claude/mcp-servers/browser-bridge/server.js
```

**Verify connection**: Run `/mcp` inside Claude Code to list connected MCP servers and their status.

### Portfolio Governance

A tier-based project management system that constrains complexity per project.

| Tier | Effort | Tests | CI | Monitoring |
|------|--------|-------|----|------------|
| T1 Production | 60% | Existing only | Existing only | Existing only |
| T2 Strategic | 30% | Unit tests | Optional | None |
| T3 Experimental | 10% | None | None | None |
| T4 Archive | 0% | None | None | None |

Copy `portfolio/PORTFOLIO.md.example` to `portfolio/PORTFOLIO.md` and register your projects.

## Configuration

### CLAUDE.md

Copy `CLAUDE.md.example` to `CLAUDE.md` and customize. Claude Code loads `CLAUDE.md` files at multiple levels, merging them in order:

1. **Managed** — enterprise-managed config (if applicable)
2. **Project** — `CLAUDE.md` files found by walking from `cwd` up to the repo root (all are loaded, closest wins on conflicts)
3. **User global** — `~/.claude/CLAUDE.md`
4. **Local** — `CLAUDE.local.md` (same directory as a project `CLAUDE.md`, for personal overrides)

**Project vs. local**: Commit `CLAUDE.md` to git so the whole team shares it. Use `CLAUDE.local.md` (add to `.gitignore`) for personal preferences that shouldn't be shared.

**Key sections and what they control**:

| Section | Effect |
|---------|--------|
| **Identity** | Sets persona (name, role, org) for response style |
| **Code Standards** | Enforced during code generation — naming, patterns, type hints |
| **Agent Behavior** | Controls planning discipline, verification steps, autonomous patterns |
| **Add-ons** | Domain-specific context modules activated per-project |
| **Portfolio Governance** | Project tier constraints — complexity budgets, testing requirements |
| **Commands** | Documents available slash commands for discoverability |

The template at `CLAUDE.md.example` has all sections with placeholder values — fill in your details.

### settings.json

Located at `~/.claude/settings.json`. Controls global permissions and plugin management. **MCP servers are not configured here** — use [`mcp.json`](#claude-code-configuration) instead.

**Permissions** — `allow` and `deny` lists control which tools Claude Code can use without prompting:

```json
{
  "permissions": {
    "allow": [
      "Bash(git status)",
      "Bash(pytest:*)",
      "Read(**/*.py)",
      "Write(**/*.py)",
      "Edit(**/*.py)"
    ],
    "deny": [
      "Bash(rm -rf /)",
      "Bash(sudo:*)",
      "Read(.env)",
      "Read(**/*.pem)"
    ]
  }
}
```

Permission patterns use the format `Tool(pattern)`:
- `Bash(command:*)` — allow a CLI command with any arguments
- `Read(**/*.ext)` — allow reading files matching a glob
- `Write(**/*.py)` — allow writing Python files
- Deny rules take precedence over allow rules

**Plugins** — enable or disable plugins from the official registry:

```json
{
  "enabledPlugins": {
    "code-review@claude-plugins-official": true,
    "commit-commands@claude-plugins-official": true,
    "superpowers@claude-plugins-official": true
  }
}
```

### Automated Loop Config

The loop driver reads `.workflow/config.json` from your project directory:

```json
{
  "limits": {
    "max_iterations": 50,
    "timeout_seconds": 300,
    "max_cost_per_iteration": 5.0,
    "max_total_cost": 50.0,
    "model_timeout_multipliers": { "opus": 2.0, "sonnet": 1.0, "haiku": 0.5 },
    "model_fallback": { "opus": "sonnet" }
  },
  "stagnation": {
    "window_size": 3,
    "low_turn_threshold": 2,
    "max_consecutive_timeouts": 2
  }
}
```

## Security

- **Never commit** API keys, tokens, or credentials
- All secrets load from environment variables (see `.env.example` files)
- `--dangerously-skip-permissions` is used by the loop driver for autonomous operation. Understand the implications before using it.
- Session files (`playwright-session.json`) contain auth cookies and are excluded from git
- The `log_redactor.py` module scrubs API keys from all log output

## Trademark Notice

"Claude" is a trademark of Anthropic, PBC. This project is not affiliated with, endorsed by, or sponsored by Anthropic. See [NOTICE](NOTICE) for full details.

## License

[MIT](LICENSE)

## Contributing

Issues and pull requests are welcome. Please:

1. Follow existing code patterns (see `CLAUDE.md.example` for standards)
2. Include tests for new functionality
3. Never commit secrets or credentials
4. Keep CLAUDE.md files under 150 lines
