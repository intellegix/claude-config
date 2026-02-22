# claude-code-toolkit

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Node.js 18+](https://img.shields.io/badge/Node.js-18+-green.svg)](https://nodejs.org)
[![Tests: 175+](https://img.shields.io/badge/Tests-175+-brightgreen.svg)](automated-loop/tests/)

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
│   └── tests/                 # 175+ pytest tests
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
│   └── synthesis_prompt.md    # Opus synthesis prompt template
│
├── mcp-servers/
│   └── browser-bridge/        # MCP Browser Bridge server
│       ├── server.js           # MCP protocol handler
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
git clone https://github.com/yourusername/claude-code-toolkit.git ~/.claude

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

WebSocket-based bridge between Claude Code CLI and Chrome browser extension.

```bash
# Start the MCP server
cd ~/.claude/mcp-servers/browser-bridge
npm start

# Configure in Claude Code settings as an MCP server
# See server.js for tool definitions
```

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

Copy `CLAUDE.md.example` to `CLAUDE.md` and customize with your identity, projects, and preferences. The global `CLAUDE.md` file configures Claude Code's behavior across all projects. Key sections:

- **Identity** - Your name, role, and organization
- **Code Standards** - Language-specific conventions
- **Agent Behavior** - Planning discipline and verification rules
- **Add-ons** - Domain-specific context modules
- **Portfolio Governance** - Project tier constraints

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
