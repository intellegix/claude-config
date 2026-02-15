# /council-refine — Multi-Model Plan Refinement with Opus 4.6 Synthesis

Submit a plan to 3 frontier AI models (GPT-5.2, Claude Sonnet 4.5, Gemini 3 Pro) via Perplexity API for iterative refinement, with Opus 4.6 extended thinking synthesis. Loop until convergence (score >= 8, no critical issues, score gain < 1) or max 3 iterations.

**Prerequisites**: `PERPLEXITY_API_KEY` and `ANTHROPIC_API_KEY` environment variables set. Python packages installed (`pip install perplexityai anthropic`).

## Input

`$ARGUMENTS` = The plan text to refine. Can be multi-line.

## Workflow

### Step 0: Initialize
- Store the plan text from `$ARGUMENTS`
- Set `iteration = 1`, `maxIterations = 3`, `previousScore = 0`

### Step 1: Build refinement query

Compose the council query for this iteration:

```
You are a panel of expert reviewers evaluating a technical implementation plan. Analyze the following plan thoroughly and provide:

1. OVERALL SCORE (1-10): How production-ready is this plan?
2. STRENGTHS: What's well-designed?
3. WEAKNESSES: What needs improvement?
4. CRITICAL ISSUES: Blockers that must be fixed before implementation
5. SPECIFIC IMPROVEMENTS: Concrete, actionable changes with code/architecture suggestions
6. REVISED SECTIONS: Rewritten sections incorporating your feedback

PLAN TO REVIEW (Iteration {iteration}/{maxIterations}):
---
{planText}
---

{If iteration > 1: "PREVIOUS FEEDBACK ADDRESSED: {summary of changes made}"}

IMPORTANT: Include a numeric score (1-10) prominently in your response.
```

### Step 2: Run council query

Call `council_query` MCP tool with:
- `query`: The prompt from Step 1
- `mode`: `"browser"` (Playwright browser automation — no API keys needed, uses Perplexity login)
- `includeContext`: `true`

This runs the full pipeline: 3 parallel Perplexity queries + Opus 4.6 synthesis with extended thinking (~20s total).

### Step 3: Read and evaluate

The `council_query` response contains the Opus synthesis. Extract:
- **Score**: From `recommended_actions` or `narrative` — look for the numeric score
- **Critical issues**: From `risks` and `disagreements`
- **Improvements**: From `recommended_actions` and `unique_insights`

If the score isn't clearly extractable from the synthesis, read the full results via `council_read` with `level: "full"` and parse individual model responses for scores.

### Step 4: Convergence check

- **Stop if**: score >= 8 AND no critical issues
- **Stop if**: score gain < 1 from previous iteration (diminishing returns)
- **Stop if**: iteration >= maxIterations
- **Continue if**: score < 8 OR critical issues remain

If continuing:
- Synthesize an improved plan incorporating the council's feedback
- Increment iteration
- Go back to Step 1

### Step 5: Persist results

- Save the final council response to `~/.claude/council-logs/{YYYY-MM-DD_HHmm}-council-refine.md` with iteration summaries
- If a previous council log exists for a similar topic, include "PREVIOUS COUNCIL FEEDBACK" context in the next iteration

## Output Format

Present the final results as:

### Council Refinement Summary

| Iteration | Score | Key Changes | Cost |
|-----------|-------|-------------|------|
| 1 | X/10 | ... | $0.XX |
| 2 | Y/10 | ... | $0.XX |

**Total Cost**: $X.XX | **Total Time**: Xs

### Final Refined Plan
{The synthesized plan after all iterations}

### Key Improvements Made
{Bulleted list of major changes from original}

### Remaining Considerations
{Any unresolved items or trade-offs the council flagged}

## Cost
- ~$0.06-0.20 per iteration × up to 3 iterations = ~$0.18-0.60 total
- ~3-5K context tokens per iteration
- ~20s per iteration

## Error Handling
- **Missing API keys**: Report which key is missing
- **Model timeout**: Individual model failures don't block others
- **Synthesis failure**: Still returns individual model responses
- **Score parse failure**: Use Claude's analysis to estimate score from narrative
