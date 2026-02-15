# Fix GitHub Issue

Analyze and fix the GitHub issue: $ARGUMENTS

## Process

### Phase 1: Understand the Issue

1. **Fetch Issue Details**
   ```bash
   gh issue view $ARGUMENTS --json title,body,labels,assignees,comments
   ```

2. **Analyze the Problem**
   - Read the issue description carefully
   - Check comments for additional context
   - Identify reproduction steps if provided
   - Note any related issues or PRs mentioned

3. **Search the Codebase**
   - Find affected files by searching for relevant terms
   - Identify the root cause location
   - Check git blame for recent changes to the area

### Phase 2: Reproduce & Verify

4. **Create Reproduction**
   - Write a failing test that demonstrates the bug
   - Or create a minimal reproduction scenario
   - Document how to trigger the issue

   ```bash
   # Run existing tests to establish baseline
   npm test -- --testPathPattern="[affected-area]"
   # or
   pytest tests/[affected_area] -v
   ```

### Phase 3: Implement the Fix

5. **Make Minimum Necessary Changes**
   - Fix the root cause, not just the symptom
   - Avoid scope creep - don't refactor unrelated code
   - Follow existing code patterns

6. **Update/Add Tests**
   - Ensure the failing test now passes
   - Add edge case tests if needed
   - Verify no regressions

### Phase 4: Verify the Fix

7. **Run Verification**
   ```bash
   # Type checking
   npm run type-check || mypy src/

   # Full test suite
   npm test || pytest

   # Linting
   npm run lint || ruff check .
   ```

8. **Manual Verification**
   - Test the fix manually if applicable
   - Verify in relevant environments

### Phase 5: Create Commit

9. **Stage and Commit**
   ```bash
   git add -A
   git commit -m "fix([scope]): [brief description]

   [Longer explanation if needed]

   - [Bullet point of what changed]
   - [Another bullet point]

   Fixes #$ARGUMENTS"
   ```

## Output Format

```markdown
## Issue Analysis: #[NUMBER]

### Problem Summary
[1-2 sentence description of the bug]

### Root Cause
[Technical explanation of why this was happening]

### Solution
[What was done to fix it]

### Files Modified
| File | Change |
|------|--------|
| `path/to/file` | [Description of change] |

### Testing
- [x] Added failing test
- [x] Test now passes
- [x] No regressions

### Verification Commands Run
```bash
npm test -- --testPathPattern="affected"
npm run type-check
```

### Commit
```
fix(scope): description

Fixes #NUMBER
```

### Follow-up
- [Any related issues to address]
- [Technical debt noted]
```

## Quality Checklist

- [ ] Issue root cause identified (not just symptoms)
- [ ] Failing test written before fix
- [ ] Fix is minimal and focused
- [ ] All tests pass
- [ ] Type checking passes
- [ ] Commit message references issue number
- [ ] No unrelated changes included
