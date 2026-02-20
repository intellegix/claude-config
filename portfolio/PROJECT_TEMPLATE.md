# CLAUDE.md Template — Keep Under 80 Lines

```markdown
# CLAUDE.md — [Project Name]

## Portfolio Context
- **Tier**: T[1-4] | **Phase**: [Prototype/Development/Hardening/Maintenance]
- **Users**: [count] | **Deploy**: [platform]
- **Stack**: [language, framework, db]

## DO NOT (Phase-Specific)
- [Prohibition 1 — from PORTFOLIO.md phase table]
- [Prohibition 2]
- [Prohibition 3]

## Commands
```bash
# Dev
[single command to run locally]

# Test
[single command to run tests]

# Deploy
[single command or "auto on push to main"]
```

## Architecture
[3-5 sentences describing the system. NOT a file tree.
Mention: entry point, key modules, data flow, external integrations.]

## Key Patterns (Project-Specific Only)
[2-3 patterns unique to THIS project. Do NOT repeat global patterns
from ~/.claude/patterns/. Link to pattern files if needed.]

## Current Priority
[1-2 sentences: what should Claude work on RIGHT NOW in this project.]

## Environment
Required env vars (no values):
- `VAR_NAME` — purpose
- `VAR_NAME` — purpose
```

## Rules
1. Total CLAUDE.md MUST be under 100 lines (target 60-80)
2. Move file trees, route tables, and detailed docs to ARCHITECTURE.md
3. DO NOT section appears early — Claude reads top-down
4. No global patterns — those live in ~/.claude/patterns/
5. No API key values — only env var names
6. Architecture is prose, not a file tree
