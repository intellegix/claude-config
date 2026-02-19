# /labs-perplexity — Labs Query via Perplexity

Run a query using Perplexity's `/labs` mode via Playwright browser automation. Similar to `/research-perplexity` but uses Perplexity's experimental labs mode with a longer 15-minute timeout for complex queries.

**No API keys required** — uses Perplexity login session only.

**CRITICAL: Do NOT ask the user questions before completing Step 0 and Step 1. Compile context silently, build the query, and execute. Only ask questions if $ARGUMENTS is empty AND you cannot determine a useful research focus from the compiled context.**

## Input

`$ARGUMENTS` = The research question or topic to investigate. If empty, defaults to a general project analysis.

## Workflow

### Step 0: Compile Session Context — MANDATORY, SILENT

**Before doing ANYTHING else**, compile the current session state. Do NOT ask the user any questions during this step — proceed silently and autonomously.

1. **Read project memory**: Read the project's `MEMORY.md` from the auto-memory directory to understand what's been worked on, recent patterns, and known issues
2. **Recent commits**: Run `git log --oneline -10` to see recent work
3. **Uncommitted work**: Run `git diff --stat` to see what's in progress
4. **Active tasks**: Check `TaskList` for any active/pending tasks
5. **Synthesize**: Form a 1-paragraph internal "current state" summary — do NOT output this to the user, just hold it in context for Step 1

Do NOT present findings. Do NOT ask questions. Proceed directly to Step 1.

### Step 1: Build the research query

Using the compiled context from Step 0, build the research query. Do not ask the user for clarification — use the session context to determine the best research angle.

Compose the query from session context + the user's research question:

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
```

### Step 2: Run labs query

Call `labs_query` MCP tool with:
- `query`: The prompt from Step 1
- `includeContext`: `true` (auto-extracts git log, CLAUDE.md, MEMORY.md)

This runs Playwright browser automation with Perplexity's `/labs` mode — an experimental labs thread with extended timeout (15 min). Results are cached to `~/.claude/council-cache/council_latest.json`.

### Step 3: Read results

The `labs_query` response contains the Perplexity synthesis. Present the key findings to the user in a concise summary.

### Step 4: Persist results

- Save output to `~/.claude/council-logs/{YYYY-MM-DD_HHmm}-labs-{projectName}.md`

### Step 5: Enter plan mode — MANDATORY

**IMMEDIATELY after receiving the research results, you MUST enter plan mode using the `EnterPlanMode` tool.** Do not ask the user, do not present the research first, do not do anything else — go straight into plan mode.

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

## Key Differences from /research-perplexity
- Uses Perplexity `/labs` mode instead of `/research` (deep research)
- 15-minute timeout (vs 7 min for research) — labs queries can run longer
- Always runs via browser (Playwright) — no API mode
- Good for experimental or complex analysis tasks
- Same cost: $0 (uses Perplexity login session)

## Error Handling
- **Session expired**: Report "run python council_browser.py --save-session to refresh"
- **Labs mode not available**: Falls back to regular Perplexity query (proceeds optimistically)
