# Agent Handoff

Create a comprehensive handoff document for the current work session.

**Task Context**: $ARGUMENTS

## Handoff Process

### Step 1: Gather Session Information
1. Identify all files modified in this session
2. Summarize work completed
3. Note any blockers or issues encountered
4. List decisions made and their rationale

### Step 2: Document Current State
5. Run relevant status commands:
   ```bash
   git status
   git diff --stat
   git log --oneline -5
   ```

6. Check test status:
   ```bash
   npm test -- --passWithNoTests 2>/dev/null || pytest --co -q 2>/dev/null || echo "No test runner detected"
   ```

### Step 3: Create Handoff Document

Generate file at: `.claude/handoffs/[YYYY-MM-DD]-[HH-MM]-[task-slug].md`

## Handoff Document Template

```markdown
# Agent Handoff: [Task Name]

**Generated**: [Current Timestamp]
**Session Duration**: [Approximate time spent]
**Agent**: Claude Code

---

## Current Status

| Metric | Value |
|--------|-------|
| Overall Progress | X% complete |
| Phase | Planning / Implementation / Testing / Review |
| Blocked | Yes/No |
| Tests Passing | Yes/No/Partial |

## Work Completed This Session

### Tasks Finished
- [x] [Completed task 1]
- [x] [Completed task 2]

### Partial Progress
- [ ] [In-progress task] - [Current state, what's left]

## Files Modified

| File | Change Type | Description |
|------|-------------|-------------|
| `src/path/file.ts` | Created | New component for X |
| `src/path/other.ts` | Modified | Added Y method |
| `tests/path/test.ts` | Created | Tests for X |

## Key Decisions Made

### Decision 1: [Title]
- **Context**: [Why this decision was needed]
- **Choice**: [What was decided]
- **Rationale**: [Why this approach]
- **Alternatives Rejected**: [What else was considered]

## What Worked Well
- [Successful approach 1]
- [Successful approach 2]

## What Didn't Work
- **Attempted**: [Approach that failed]
- **Problem**: [Why it didn't work]
- **Resolution**: [What was done instead]

## Blockers & Dependencies

### Active Blockers
- **Blocker**: [Description]
  - **Impact**: [What it's blocking]
  - **Needed**: [What's needed to unblock]
  - **Owner**: [Who can resolve this]

### External Dependencies
- [Dependency on external team/service]

## Context for Next Agent

### Current State of Codebase
[Brief description of relevant code state - what's implemented, what's scaffolded, what's missing]

### Important Files to Review First
1. `path/to/file1.ts` - [Why it's important]
2. `path/to/file2.ts` - [Why it's important]

### Environment Setup
```bash
# Commands to run before starting
npm install  # or pip install -r requirements.txt
npm run dev  # or python -m uvicorn main:app
```

### Test Commands
```bash
# How to verify current state
npm test -- path/to/tests
# or
pytest tests/specific_test.py -v
```

## Recommended Next Steps

### Immediate (Do First)
1. [Most important next action]
2. [Second priority]

### Follow-up
3. [Lower priority task]
4. [Can be done later]

## Notes & Warnings

⚠️ **Warning**: [Important gotcha or thing to be careful about]

📝 **Note**: [Helpful context that isn't obvious from the code]

🐛 **Known Issue**: [Bug or limitation that exists but isn't fixed yet]

---

## Raw Session Data

### Git Status at Handoff
```
[Output of git status]
```

### Recent Commits
```
[Output of git log --oneline -5]
```
```

## After Creating Handoff

1. Save the document to `.claude/handoffs/`
2. Stage any uncommitted work: `git add -A`
3. Create WIP commit if needed: `git commit -m "WIP: [task description]"`
4. Summarize the handoff file location for the user
