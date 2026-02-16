# /research-perplexity — Deep Research via Perplexity

Run a deep research query using Perplexity's `/research` mode via Playwright browser automation. This is an alternative to `/export-to-council` that uses Perplexity's dedicated research mode instead of multi-model council.

**No API keys required** — uses Perplexity login session only. Good fallback when council mode defaults to single-model.

## Input

`$ARGUMENTS` = The research question or topic to investigate. If empty, defaults to a general project analysis.

## Workflow

### Step 1: Build the research query

Compose the query from session context + the user's research question:

```
You are a technical research analyst. Given the project context (provided as system context), perform deep research on the following topic.

RESEARCH TOPIC: {$ARGUMENTS or "Analyze the current project architecture and identify the most impactful improvements based on recent industry best practices."}

Please provide:
1. KEY FINDINGS: Main discoveries from your research with citations
2. CURRENT BEST PRACTICES: What the industry recommends in 2025-2026
3. APPLICABILITY: How these findings apply to the specific project context
4. ACTIONABLE RECOMMENDATIONS: 3-5 concrete steps in priority order
5. TRADE-OFFS: What are the downsides or risks of each recommendation
6. SOURCES: Key references and their credibility
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
3. Create a concrete implementation plan
4. Write the plan, then call `ExitPlanMode` for user approval

## Key Differences from /export-to-council
- Uses Perplexity `/research` mode instead of `/council` (multi-model)
- Always runs via browser (Playwright) — no API mode
- Better for deep, focused research on a single topic
- Good fallback when council mode uses single-model anyway
- Same cost: $0 (uses Perplexity login session)

## Error Handling
- **Session expired**: Report "run python council_browser.py --save-session to refresh"
- **Research mode not available**: Falls back to regular Perplexity query
