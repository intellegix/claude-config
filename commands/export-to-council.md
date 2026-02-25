# /export-to-council — Export Session to Multi-Model Council Analysis

Query 3 frontier AI models (GPT-5.2, Claude Sonnet 4.5, Gemini 3 Pro) via Perplexity API or browser automation, then synthesize findings. Automatically enters plan mode to study implementation.

**No API keys required for browser mode** — uses Perplexity login session. API mode requires `PERPLEXITY_API_KEY` + `ANTHROPIC_API_KEY`.

**CRITICAL: Do NOT ask the user questions before completing Step 0 and Step 1. Compile context silently, build the query, and execute. Only ask questions if $ARGUMENTS is empty AND you cannot determine a useful research focus from the compiled context.**

## Input

`$ARGUMENTS` = Optional focus area or question (e.g., "focus on the database layer", "what should we prioritize next"). If empty, defaults to "general next steps".

## Workflow

### Step 0: Compile Session Context — MANDATORY, SILENT

**Before doing ANYTHING else**, compile the current session state. Do NOT ask the user any questions during this step — proceed silently and autonomously.

1. **Read project memory**: Read the project's `MEMORY.md` from the auto-memory directory to understand what's been worked on, recent patterns, and known issues
2. **Recent commits**: Run `git log --oneline -10` to see recent work
3. **Uncommitted work**: Run `git diff --stat` to see what's in progress
4. **Active tasks**: Check `TaskList` for any active/pending tasks
5. **Synthesize**: Form a 1-paragraph internal "current state" summary — do NOT output this to the user, just hold it in context for Step 1

Do NOT present findings. Do NOT ask questions. Proceed directly to Step 0.5.

### Step 0.5: Explore Codebase — MANDATORY, SILENT

After compiling session context (Step 0), explore the actual codebase:

1. **Find key files**: Use `Glob` for main source files (*.py, *.ts, *.js) in project root and src/
2. **Read recently modified**: Run `git diff --name-only HEAD~5 HEAD`, read up to 10 files (first 100 lines each)
3. **Read structural files**: README.md, pyproject.toml, package.json if they exist
4. **Synthesize**: Form internal "codebase summary" — key files, purposes, connections

Do NOT present findings. Do NOT ask questions. Include this context when building the query in Step 1.

### Step 1: Build the query prompt

Using the compiled context from Step 0, build the council query. Do not ask the user for clarification — use the session context to determine the best research angle.

Compose the council query from session context + focus area. The prompt should be:

```
You are a development strategy advisor analyzing a coding session. Given the project context (provided as system context), provide strategic analysis and concrete next steps.

FOCUS AREA: {$ARGUMENTS or "general next steps — what should be the priority?"}

Please analyze and respond with:
1. CURRENT STATE: What has been accomplished based on the project context
2. PROGRESS VS PLAN: How does the work align with the project's implementation plan?
3. IMMEDIATE NEXT STEPS: 3-5 concrete actions in priority order, with specific file paths and code changes
4. BLOCKERS: Any issues that need resolution before proceeding
5. TECHNICAL DEBT: Items that should be addressed soon
6. STRATEGIC RECOMMENDATIONS: Longer-term suggestions for the project direction
7. RISKS: What could go wrong with the recommended path, and mitigations
8. CODEBASE FIT: How do recommendations integrate with existing code structure?
```

### Step 1.5: Close Browser Bridge Sessions — MANDATORY

**Before launching any Playwright-based query**, close active browser-bridge sessions to prevent DevTools Protocol collisions:

1. Call `mcp__browser-bridge__browser_close_session` to release all browser-bridge tab connections
2. Wait 2 seconds (`sleep 2` via Bash) for Chrome DevTools to fully detach
3. Then proceed to Step 2

**Why:** The `council_query` tool launches Playwright (separate Chromium instance). If `browser-bridge` has active Chrome DevTools connections, the two systems can collide — causing tab detachment errors, empty results, and `"Debugger is not attached"` failures. Closing browser-bridge first prevents this.

**After Step 3 (Read synthesis):** Browser-bridge connections can be re-established by calling any `browser-bridge` tool — no explicit reconnect needed.

### Step 2: Run council query (auto mode)

Call `council_query` MCP tool with:
- `query`: The prompt from Step 1
- `mode`: `"browser"` (Playwright browser automation — no API keys needed, uses Perplexity login)
- `includeContext`: `true` (auto-extracts git log, CLAUDE.md, MEMORY.md)

This runs externally as a Python subprocess — zero context tokens consumed during execution. Results are cached to `~/.claude/council-cache/council_latest.json`.

The tool returns the formatted synthesis directly (~3-5K tokens).

**Mode cascade:**
- `api` (~20s, $0.06-0.20): Perplexity Agent API → Sonar fallback → Direct providers → Opus synthesis
- `browser` (~90-130s, $0): Playwright opens Perplexity UI → activates council → extracts synthesis
- `auto` (default): Tries api first, falls back to browser if API fails

### Step 3: Read synthesis

The `council_query` response contains the synthesis with:
- Executive summary
- Model agreements and disagreements
- Unique insights per model
- Prioritized recommended actions
- Risk assessment
- Detailed narrative analysis

If you need deeper detail on a specific model's response, call `council_read` with `level: "gpt-5.2"` or `level: "claude-sonnet-4.5"` or `level: "gemini-3-pro"`.

For the complete dataset: `council_read` with `level: "full"`.

### Step 4: Persist results

- Create directory `~/.claude/council-logs/` if it doesn't exist
- Determine project name from current working directory
- Save council output to `~/.claude/council-logs/{YYYY-MM-DD_HHmm}-export-{projectName}.md`
- If previous council logs exist for the same project, reference them for trend analysis

### Step 5: Enter plan mode — MANDATORY

**IMMEDIATELY after receiving the council synthesis, you MUST enter plan mode using the `EnterPlanMode` tool.** Do not ask the user, do not present the synthesis first, do not do anything else — go straight into plan mode.

**CRITICAL: Do NOT ask the user which priorities to tackle. Cover ALL priorities from the research. Never filter, skip, or ask for selection — build the complete plan automatically.**

In plan mode, create a **two-tier plan structure** (master plan + sub-plans):

#### Tier 1: Master Plan (the blueprint)

1. Read relevant project files identified in the council findings (use Glob, Grep, Read)
2. Cross-reference ALL recommended actions against the current codebase
3. List every priority from the research as a numbered **Phase** in execution order:
   - Phase ordering: blockers first, then dependencies, then independent work, then polish
   - Each Phase gets: title, 1-line goal, estimated complexity (S/M/L), prerequisite phases
   - Group related priorities into the same phase when they touch the same files
4. The master plan should read like a table of contents with dependency arrows between phases

#### Tier 2: Sub-Plans (the details)

For each Phase in the master plan, write a detailed sub-plan:
   - Specific files to create/modify (with paths)
   - Code changes needed (describe the what, not line-by-line diffs)
   - Acceptance criteria — how to verify this phase is done
   - Risk mitigations from the council findings
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

#### Plan Verification — MANDATORY

After writing the complete plan but BEFORE calling `ExitPlanMode`:

1. **Build verification query**: Include the complete plan + research summary + key codebase files from Step 0.5
2. **Run verification**: Call `council_query` with a critique-focused prompt asking Perplexity to evaluate: logical errors, missing edge cases, file path accuracy, dependency ordering, scope creep, feasibility
3. **Revise plan**: If critique identifies issues, revise the plan. If APPROVED, proceed as-is.
4. **Maximum 1 verification pass** — never re-verify after revision. Call ExitPlanMode.

Write the full plan (master + all sub-plans), then call `ExitPlanMode` for user approval.

### Step 6: Create task list from plan

After the user approves the plan:
- Use `TaskCreate` to create one task per Phase from the master plan
- Set dependencies with `addBlockedBy` matching the phase prerequisites
- Each task description should contain the full sub-plan for that phase
- Begin executing the first unblocked task

## Key Differences from /council-refine
- **Single pass** — no iteration loop, research/strategy-oriented
- **Auto mode** — tries API first, falls back to browser (no manual config needed)
- **Auto-plan** — enters plan mode automatically after receiving findings
- **Auto-extracts project context** from git + CLAUDE.md + MEMORY.md
- `$ARGUMENTS` is a focus filter, not the content to review
- Output is a prioritized roadmap turned into an executable plan

## Error Handling
- **API keys missing + browser fails**: Report which tier failed and suggest `python council_browser.py --save-session`
- **Session expired (browser)**: Report "run python council_browser.py --save-session to refresh"
- **Model timeout**: Individual model failures don't block others (parallel execution)
- **Synthesis failure**: Still returns individual model responses via `council_read --read-full`
- **Browser collision / empty results**: If `council_query` returns empty synthesis, the most likely cause is browser-bridge DevTools collision. Close browser-bridge sessions (`browser_close_session`), wait 2 seconds, and retry once. If still empty, report "Perplexity session may be expired — run `/cache-perplexity-session` to refresh."
