# Agent Handoff Protocol

## Purpose

Handoff documents capture session context when an agent's work needs to continue in a new session. They preserve decisions, progress, blockers, and next steps to minimize context loss.

## When to Create a Handoff

- Context window is filling (>70% capacity)
- Switching between major task phases
- End of a work session with incomplete tasks
- Delegating complex work to another agent

## Naming Convention

```
YYYY-MM-DD-HH-MM-task-slug.md
```

Examples:
- `2026-02-12-14-30-procore-api-integration.md`
- `2026-02-12-09-15-dashboard-redesign.md`

## Quick-Reference Template

```markdown
# Agent Handoff: [Task Name]

**Generated**: [Timestamp]
**Agent**: [Agent Name]
**Status**: [% complete] | [Phase]

## Work Completed
- [x] [Completed item]
- [ ] [In-progress item] - [current state]

## Files Modified
| File | Change | Description |
|------|--------|-------------|
| `path/file` | Created/Modified | What changed |

## Key Decisions
1. **[Decision]**: [Choice made] because [rationale]

## Blockers
- [Blocker description] - needs [resolution]

## Next Steps
1. [Immediate priority]
2. [Follow-up task]

## Context for Next Agent
[What they need to know to continue effectively]
```

## Full Template

The complete handoff template with all sections is defined in:
`~/.claude/commands/handoff.md`

Use the `/handoff` command to generate a full handoff document automatically.

## Directory Contents

Handoff files are stored in this directory and can be referenced by any agent picking up work. Files older than 30 days can be archived or deleted at Austin's discretion.
