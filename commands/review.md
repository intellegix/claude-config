# Code Review

Review the code changes and provide detailed feedback.

**Target**: $ARGUMENTS

If no target specified, review staged changes: `git diff --cached`

## Review Process

### Step 1: Gather Context

1. **Get the diff**
   ```bash
   # If PR number provided
   gh pr diff $ARGUMENTS

   # If file path provided
   git diff HEAD -- $ARGUMENTS

   # If no argument, staged changes
   git diff --cached
   ```

2. **Understand the context**
   - What is this change trying to accomplish?
   - Check related issues/PRs if mentioned
   - Review commit messages

### Step 2: Code Quality Review

3. **Check against project standards**
   - Follows naming conventions (see CLAUDE.md Section 1)
   - Proper error handling with Result pattern
   - No hardcoded values that should be config
   - No commented-out code or debug statements

4. **TypeScript/Python specific**
   - Explicit return types on exported functions
   - No `any` types (use `unknown` if truly needed)
   - Proper null/undefined handling
   - Type hints on all functions (Python)

### Step 3: Security Review

5. **Security checklist**
   - No secrets or credentials in code
   - Input validation for external data
   - Proper authentication/authorization checks
   - No SQL injection vulnerabilities
   - No XSS vulnerabilities (if frontend)

### Step 4: Testing Review

6. **Test coverage**
   - New code has corresponding tests
   - Edge cases covered
   - Tests are readable and test behavior (not implementation)
   - Mocks used appropriately

### Step 5: Performance Review

7. **Performance checklist**
   - No obvious N+1 query issues
   - Appropriate use of async/await
   - No unnecessary re-renders (React)
   - Large lists virtualized
   - No memory leaks (cleanup in useEffect)

### Step 6: Portfolio Compliance Review

8. **Over-engineering check**
   - Read `~/.claude/portfolio/PORTFOLIO.md`
   - Is complexity appropriate for this project's tier and user count?
   - Are there enterprise patterns that don't belong at this scale?
   - Does the change respect phase restrictions?
   - Flag over-engineering as a "Must Fix" issue.

## Output Format

```markdown
## Code Review: [Target]

### Summary
[1-2 sentence overview of the changes]

### Scope
- Files changed: X
- Lines added: +X
- Lines removed: -X

---

## ✅ Strengths

### What's Done Well
- [Specific positive feedback with file:line reference]
- [Another positive point]

---

## ⚠️ Suggestions (Non-blocking)

### 1. [Category]: [Brief title]
**Location**: `file.ts:42`
**Current**:
```typescript
// Current code
```
**Suggested**:
```typescript
// Improved code
```
**Rationale**: [Why this is better]

### 2. [Category]: [Brief title]
...

---

## 🚨 Issues (Must Fix Before Merge)

### 1. [Severity]: [Brief title]
**Location**: `file.ts:123`
**Problem**: [What's wrong]
**Impact**: [Why it matters - security/performance/correctness]
**Fix**:
```typescript
// How to fix
```

---

## 📝 Questions for Author

1. [Question about design decision or intent]
2. [Clarification needed]

---

## Testing Notes

- [ ] Ran tests locally: [Yes/No]
- [ ] New tests added: [Yes/No/N/A]
- [ ] Manual testing done: [Yes/No/N/A]

---

## Verdict

**Status**: [Approved / Needs Changes / Blocked]

[Final summary and any conditions for approval]
```

## Review Checklist

### Code Quality
- [ ] Follows project coding standards
- [ ] No commented-out code or debug statements
- [ ] Meaningful names for variables and functions
- [ ] Appropriate error handling
- [ ] No hardcoded values

### TypeScript/JavaScript
- [ ] Explicit return types on exports
- [ ] No `any` types
- [ ] Proper null handling (`?.`, `??`)
- [ ] Interfaces for data structures

### Python
- [ ] Type hints on all functions
- [ ] Docstrings for public functions
- [ ] Proper exception handling
- [ ] No mutable default arguments

### Security
- [ ] No secrets in code
- [ ] Input validation present
- [ ] Auth checks appropriate
- [ ] No injection vulnerabilities

### Testing
- [ ] Tests exist for new code
- [ ] Edge cases covered
- [ ] Tests are maintainable

### Performance
- [ ] No N+1 queries
- [ ] Async used appropriately
- [ ] No obvious memory leaks
