# Global CLAUDE.md v3.0 — Compact
# Austin Kidwell | Intellegix, ASR Inc | Patterns: ~/.claude/patterns/

## Identity
- Austin Kidwell | CEO, Full-stack Dev, Systems Architect
- Intellegix (Construction BI SaaS), ASR Inc (Systems Integration)
- San Diego, CA | Pacific (PT)

## Tech Stack
- Python (70%), TypeScript (25%), Kotlin (5%)
- Backend: FastAPI, Flask, Node.js | Frontend: React, Next.js, TailwindCSS
- AI/ML: Claude API, Perplexity, Ollama | DB: PostgreSQL, SQLite, Redis

## Commands
`/research`, `/smart-plan`, `/fix-issue`, `/implement`, `/review`, `/handoff`, `/mcp-setup`, `/browser-test`, `/mcp-deploy`, `/council-refine`, `/export-to-council`, `/council-extract`, `/cache-perplexity-session`, `/portfolio-status` (Defined in `~/.claude/commands/*.md`)

## Models
opus (complex arch) | sonnet (code) | haiku (quick) | sonnet+web (research)

## Response Style
- Be direct and technical - skip preambles
- Show code first, explain after
- State assumptions explicitly when uncertain
- Don't ask for confirmation - just do it, then summarize

## Code Standards

### Python (Primary)
- Type hints on ALL functions: `def process(data: dict) -> Result[T]:`
- Async/await for I/O: `async def fetch(url: str) -> dict:`
- Pydantic for validation, logging over print, Result pattern for errors
- See `patterns/PYTHON_PATTERNS.md`

### TypeScript
- ES modules only, explicit return types on exports
- React Query for server state, Zustand for client, Zod for validation
- See `patterns/TYPESCRIPT_PATTERNS.md`

### Naming
Py: snake_case vars/funcs, PascalCase classes, SCREAMING_SNAKE consts, snake_case.py files
TS: camelCase vars/funcs, PascalCase classes, SCREAMING_SNAKE consts, kebab-case.ts files

## Pattern References
Error handling: `patterns/PYTHON_PATTERNS.md#result-pattern`; Validation: `patterns/PYTHON_PATTERNS.md#pydantic-validation`; API: `patterns/API_PATTERNS.md`; Testing: `patterns/TESTING_PATTERNS.md`; Security: `patterns/SECURITY_CHECKLIST.md`; MCP: `patterns/MCP_PATTERNS.md`; Browser: `patterns/BROWSER_AUTOMATION_PATTERNS.md`

## Security
- Load credentials from environment: `API_KEY = os.environ["API_KEY"]` — never hardcode; use pydantic-settings or python-dotenv
- Validate ALL external input with Pydantic/Zod; parameterized queries only — never concatenate user input into SQL
- Never log passwords, tokens, PII, or API keys; audit log all mutations with user_id + timestamp
- Full checklist: `patterns/SECURITY_CHECKLIST.md`

## Git Workflow
- Branches: `feature/IGX-123-desc` | `bugfix/ASR-456-fix` | `hotfix/critical-patch`
- Commits: `feat(scope): add feature` | `fix(scope): resolve bug` | `refactor(scope): improve code`
- Pre-commit: type check (`mypy src/` or `npm run type-check`); run affected tests; no hardcoded secrets; new env vars in `.env.example`

## Agent Behavior
- Before changes: read files first, understand context; Bugs: failing test first; Features: types/interfaces first; Refactors: tests pass before AND after
- Code gen: complete working code (no TODOs), all imports, follow codebase patterns, docstrings on public funcs
- Verify after changes: type-check; run affected tests; check circular deps if new imports

### Planning Discipline (MANDATORY)
For non-trivial tasks (3+ files, new features, refactors, bug investigations): ALWAYS enter plan mode first. After implementation, run `/export-to-council` for feedback. For plans >1hr, run `/council-refine` first.

### Post-Plan Completion (MANDATORY)
After completing any plan (all steps done, committed): **always suggest** running `/research-perplexity` to get strategic analysis on next steps. Present it as: "Plan complete. Suggest running `/research-perplexity` for strategic next steps — want me to proceed?" This applies to every plan, not just major ones.

### Post-Implementation Council Review
After major implementation: run `/export-to-council` → synthesize into MEMORY.md → create follow-up tasks.

### Perplexity Session Caching
Run `/cache-perplexity-session` after Perplexity login. Cached to `~/.claude/config/perplexity-session.json` (24h TTL). Auto-used by council commands; falls back to UI clicks if expired.

### Browser Automation (MANDATORY)
**Always use `mcp__browser-bridge__*` tools for ALL browser interactions.** Never fall back to other browser tools.
Tools: `browser_navigate`, `browser_execute`, `browser_screenshot`, `browser_get_context`, `browser_get_tabs`, `browser_switch_tab`, `browser_wait_for_element`, `browser_fill_form`, `browser_extract_data`, `browser_scroll`, `browser_select`, `browser_close_session`
Rules: Start with `browser_get_tabs`; sessions get own tab group; ALWAYS call `browser_close_session` when done; screenshots: no params=viewport, `selector`=element, `fullPage`=page, `savePath`=disk; if not connected, tell user to check extension.

## Portfolio Governance (MANDATORY)

### Before ANY Work
Read `~/.claude/portfolio/PORTFOLIO.md` for project tier, phase, and constraints.
Respect the project's "DO NOT" list. Phase restrictions are hard limits, not suggestions.

### Complexity Budget by Tier
| Tier | Tests | CI | Monitoring | Docs |
|------|-------|----|------------|------|
| T1 Maintenance | Existing only | Existing only | Existing only | CLAUDE.md + README |
| T2 Development | Unit tests | Optional | None | CLAUDE.md + README |
| T3 Experimental | None | None | None | CLAUDE.md only |
| T4 Archive | None | None | None | None |

### Velocity Rules
- MAX 2 active feature branches across all projects
- Prototype phase = working code only, no infrastructure
- If a feature takes >4h estimate, break it down or question scope
- Default to the SIMPLEST solution that works for the user count

## Add-ons

**CONSTRUCTION_BI** (Intellegix/ASR): Procore (3600 req/hr)/QB/Foundation/Raken | WIP, Job Costing, Change Orders, Retention 5-10%, Certified Payroll | margin=(rev-cost)/rev, WIP=earned_rev-billed | SD fire mitigation, SB721, Trex

**MULTI_AGENT** (Claude Orchestration, Code Max CLI, AI TV 2.0): Orchestrator(Opus)→Research/Backend/Frontend/Test(Sonnet) | Agent types: Orchestrator, Research, Architect, Frontend, Backend, Database, DevOps, Testing | Handoff: `.claude/handoffs/[timestamp]-[task].md`

**FINANCIAL_AUTOMATION** (Stocks CLI, Certified Payroll, Stock Manager): yfinance/Alpha Vantage/Finnhub/Foundation/Raken | pandas, openpyxl, PyPDF2, yagmail | Commodities: Lumber, Steel, Copper, Oil, USD Index

**WEB_SCRAPING** (Pricing scraper, App monitoring): undetected-chromedriver, mobile emulation, BOPIS | Price validation: range check, keyword match, 95% confidence | Claude 3.5 Sonnet for screenshot price extraction

**HARDWARE_IOT** (Voice Controller, Remote Mobile UI): GPIO (onoff), Vosk offline speech, Roku ECP | pyautogui (Win), xdotool (Linux) | **Remote Mobile UI server is a long-running intentional process — DO NOT kill it as stale**

**ANDROID_MOBILE** (IntelleGolf, Intellegix Attack, Perplexity Voice): Kotlin, Coroutines, Compose UI, Hilt DI | Min SDK 26, target latest

**MCP_BROWSER_AUTOMATION** (Browser Extension, Enterprise Test, MCP Protocol): MCP Server↔WS Bridge↔Chrome Ext↔DOM | <2.2s exec, 40% productivity boost, 80% test reduction | See `patterns/MCP_PATTERNS.md`, `patterns/BROWSER_AUTOMATION_PATTERNS.md`, `patterns/SECURITY_MCP.md` | Full plan: `~/.claude/plans/mcp-master-plan.md`

## Hooks
Auto-format on save: Python (`black`+`isort`), TS/JS (`eslint --fix`), JSON/YAML/MD (`prettier --write`). Configure in `~/.claude/settings.json`.
Activate add-ons in projects: reference `~/.claude/CLAUDE.md` add-on section, or copy to project CLAUDE.md.

## Troubleshooting
Python: `mypy src/` | `pip install -r requirements.txt --force-reinstall`
TS: `rm -rf node_modules/.cache && npm run build`
DB: `psql $DATABASE_URL -c "SELECT 1"` | Integrations: check OAuth expiry, rate limits, webhook delivery

## API Keys (Global)
Source: `C:\Users\AustinKidwell\ASR Dropbox\Austin Kidwell\02.02_ApiKeys\`
Load from environment variables. See source directory for values.
Keys: AWS (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`), Claude (`ANTHROPIC_API_KEY`), HeyGen (`HEYGEN_API_KEY`), OpenAI (`OPENAI_API_KEY`), Perplexity (`PERPLEXITY_API_KEY`), Render (`RENDER_API_KEY`), GitHub (use `gh auth login`)
