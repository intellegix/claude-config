# /research-perplexity — Deep Research via Perplexity

Run a deep research query using Perplexity's `/research` mode via Playwright browser automation. This is an alternative to `/export-to-council` that uses Perplexity's dedicated research mode instead of multi-model council.

**No API keys required** — uses Perplexity login session only. Good fallback when council mode defaults to single-model.

## Input

`$ARGUMENTS` = The research question or topic to investigate. If empty, defaults to a general project analysis.

## Workflow

### Step 1: Build the research query

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

### Step 2: Run research query

Call `research_query` MCP tool with:
- `query`: The prompt from Step 1
- `includeContext`: `true` (auto-extracts git log, CLAUDE.md, MEMORY.md)

This runs Playwright browser automation with Perplexity's `/research` mode — a single deep research thread (not multi-model council). Results are cached to `~/.claude/council-cache/council_latest.json`.

### Step 3: Read results

The `research_query` response contains the Perplexity synthesis. Present the key findings to the user in a concise summary.

### Step 4: Persist results

- Save output to `~/.claude/council-logs/{YYYY-MM-DD_HHmm}-research-{projectName}.md`

### Step 5: Enter plan mode — MANDATORY

**IMMEDIATELY after receiving the research results, you MUST enter plan mode using the `EnterPlanMode` tool.**

In plan mode:
1. Read relevant project files identified in the research findings
2. Cross-reference recommendations against the current codebase
3. Identify which recommendations are actionable now vs. need prerequisites
4. Create a concrete implementation plan with:
   - Specific files to create/modify
   - Code changes needed
   - Dependency ordering (what must happen first)
   - Risk mitigations from the research findings
   - **ALWAYS end with a "Commit & Push" step** — the final step of every plan must commit all changes and push to remote
5. Write the plan, then call `ExitPlanMode` for user approval

## Key Differences from /export-to-council
- Uses Perplexity `/research` mode instead of `/council` (multi-model)
- Always runs via browser (Playwright) — no API mode
- Better for deep, focused research on a single topic
- Good fallback when council mode uses single-model anyway
- Same cost: $0 (uses Perplexity login session)

## Error Handling
- **Session expired**: Report "run python council_browser.py --save-session to refresh"
- **Research mode not available**: Falls back to regular Perplexity query
