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

Do NOT present findings. Do NOT ask questions. Proceed directly to Step 1.

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
```

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

In plan mode:
1. Read relevant project files identified in the council findings (use Glob, Grep, Read)
2. Cross-reference the council's recommended actions against the current codebase state
3. Identify which recommendations are actionable now vs. need prerequisites
4. Create a concrete implementation plan with:
   - Specific files to create/modify
   - Code changes needed
   - Dependency ordering (what must happen first)
   - Risk mitigations from the council findings
   - **Second-to-last step: Update MEMORY.md** — synthesize key findings, new patterns, lessons learned, and architectural decisions from the council into the project's `MEMORY.md` file. Add new sections or update existing ones. Keep it concise — index-style entries with links to topic files for details. If MEMORY.md exceeds 200 lines, move detailed content into separate topic files under the memory directory.
   - **ALWAYS end with a "Commit & Push" step** — the final step of every plan must commit all changes and push to remote
5. Write the plan, then call `ExitPlanMode` for user approval

The plan should directly translate the council's strategic recommendations into executable implementation steps. Don't just summarize the council — turn it into a buildable plan.

### Step 6: Create task list from plan

After the user approves the plan:
- Use `TaskCreate` to create tasks for each implementation step
- Set dependencies with `addBlockedBy` where steps depend on each other
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
