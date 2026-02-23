# /automate-perplexity — Unified Perplexity Automation

Run a Perplexity query with **automatic mode selection** — picks the best Perplexity mode (research, council, or labs) based on your query, or lets you force a specific mode. Single entry point replacing `/research-perplexity`, `/export-to-council`, and `/labs-perplexity`.

**No API keys required** — uses Perplexity login session via Playwright browser automation. $0/query.

**CRITICAL: Do NOT ask the user questions before completing Step 0 and Step 1. Compile context silently, build the query, and execute. Only ask questions if $ARGUMENTS is empty AND you cannot determine a useful research focus from the compiled context.**

## Input

`$ARGUMENTS` = Query text, optionally prefixed with a mode flag:

- No flag → **auto-select** mode based on query keywords
- `--research <query>` → force `research_query`
- `--council <query>` → force `council_query`
- `--labs <query>` → force `labs_query`

## Workflow

### Step 0: Compile Session Context — MANDATORY, SILENT

**Before doing ANYTHING else**, compile the current session state. Do NOT ask the user any questions during this step — proceed silently and autonomously.

1. **Read project memory**: Read the project's `MEMORY.md` from the auto-memory directory to understand what's been worked on, recent patterns, and known issues
2. **Recent commits**: Run `git log --oneline -10` to see recent work
3. **Uncommitted work**: Run `git diff --stat` to see what's in progress
4. **Active tasks**: Check `TaskList` for any active/pending tasks
5. **Synthesize**: Form a 1-paragraph internal "current state" summary — do NOT output this to the user, just hold it in context for Step 1

Do NOT present findings. Do NOT ask questions. Proceed directly to Step 1.

### Step 1: Parse Mode + Build Query

#### 1a: Determine mode

Parse `$ARGUMENTS` for a mode flag (`--research`, `--council`, `--labs`). Strip the flag from the query text.

If no flag provided, auto-select based on query keywords:
- **council**: query contains "compare", "tradeoffs", "trade-offs", "pros and cons", "which is better", "versus", "vs", "evaluate options", "multi-model", "council"
- **labs**: query contains "experimental", "cutting edge", "cutting-edge", "novel", "prototype", "explore", "labs"
- **research** (default): everything else

Announce the selected mode briefly: `Using {mode} mode.`

#### 1b: Build enriched query

Compose the query from session context + the user's question:

```
You are a development strategy advisor analyzing a coding session. Given the project context (provided as system context), provide strategic analysis and concrete next steps.

FOCUS AREA: {query text or "general next steps — what should be the priority?"}

Please analyze and respond with:
1. CURRENT STATE: What has been accomplished based on the project context
2. PROGRESS VS PLAN: How does the work align with the project's implementation plan?
3. IMMEDIATE NEXT STEPS: 3-5 concrete actions in priority order, with specific file paths and code changes
4. BLOCKERS: Any issues that need resolution before proceeding
5. TECHNICAL DEBT: Items that should be addressed soon
6. STRATEGIC RECOMMENDATIONS: Longer-term suggestions for the project direction
7. RISKS: What could go wrong with the recommended path, and mitigations
```

### Step 2: Execute via MCP

Based on the selected mode, call the corresponding MCP tool:

- **research** → `mcp__browser-bridge__research_query(query, includeContext=true)`
- **council** → `mcp__browser-bridge__council_query(query, mode="browser", includeContext=true)`
- **labs** → `mcp__browser-bridge__labs_query(query, includeContext=true)`

All modes run via Playwright browser automation. Results cached to `~/.claude/council-cache/council_latest.json`.

### Step 3: Read + Present Results

The MCP response contains the Perplexity output. Present key findings to the user in a concise summary.

For council mode only: if deeper detail on a specific model's response is needed, call `council_read` with `level: "gpt-5.2"`, `level: "claude-sonnet-4.5"`, or `level: "gemini-3-pro"`.

### Step 4: Persist Results

- Create directory `~/.claude/council-logs/` if it doesn't exist
- Determine project name from current working directory
- Save output to `~/.claude/council-logs/{YYYY-MM-DD_HHmm}-{mode}-{projectName}.md`
  - mode = `research`, `council`, or `labs`

### Step 5: Enter plan mode — MANDATORY

**IMMEDIATELY after receiving results, you MUST enter plan mode using the `EnterPlanMode` tool.** Do not ask the user, do not present findings first, do not do anything else — go straight into plan mode.

**CRITICAL: Do NOT ask the user which priorities to tackle. Cover ALL priorities from the research. Never filter, skip, or ask for selection — build the complete plan automatically.**

In plan mode, create a **two-tier plan structure** (master plan + sub-plans):

#### Tier 1: Master Plan (the blueprint)

1. Read relevant project files identified in the research findings
2. Cross-reference ALL recommendations against the current codebase
3. List every priority as a numbered **Phase** in execution order:
   - Phase ordering: blockers first, then dependencies, then independent work, then polish
   - Each Phase gets: title, 1-line goal, estimated complexity (S/M/L), prerequisite phases
   - Group related priorities into the same phase when they touch the same files
4. The master plan should read like a table of contents with dependency arrows between phases

#### Tier 2: Sub-Plans (the details)

For each Phase in the master plan, write a detailed sub-plan:
   - Specific files to create/modify (with paths)
   - Code changes needed (describe the what, not line-by-line diffs)
   - Acceptance criteria — how to verify this phase is done
   - Risk mitigations from the research findings
   - Dependencies on other phases (what must be done first)

#### Required final sections (in every plan):

- **Second-to-last phase: Update project memory** — follow these 6 rules:
  1. MEMORY.md stays under 150 lines — move implementation details to `memory/*.md` topic files
  2. No duplication between MEMORY.md and CLAUDE.md — if it's a behavioral rule, it belongs in CLAUDE.md only
  3. New session-learned patterns (bugs, gotchas, workarounds) go in MEMORY.md; implementation details go to topic files
  4. Delete outdated entries rather than accumulating — check if existing content is superseded
  5. If adding a new topic file, add a 1-line entry to the Topic File Index in MEMORY.md
  6. Topic file naming: kebab-case.md
- **Final phase: Commit & Push** — commit all changes and push to remote

Write the full plan (master + all sub-plans), then call `ExitPlanMode` for user approval.

After the user approves:
- Use `TaskCreate` to create one task per Phase from the master plan
- Set dependencies with `addBlockedBy` matching the phase prerequisites
- Each task description should contain the full sub-plan for that phase
- Begin executing the first unblocked task

## Auto-Selection Reference

| Keywords in query | Mode selected |
|---|---|
| compare, tradeoffs, pros and cons, versus, vs, which is better, evaluate options, multi-model, council | **council** |
| experimental, cutting edge, novel, prototype, explore, labs | **labs** |
| everything else | **research** (default) |

## Error Handling

- **Session expired**: Report "run `python council_browser.py --save-session` to refresh"
- **Research/labs mode not available**: Falls back to regular Perplexity query
- **Council model timeout**: Individual model failures don't block others (parallel execution)
- **Synthesis failure (council)**: Still returns individual model responses via `council_read --read-full`
