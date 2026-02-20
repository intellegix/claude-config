# Implement Feature

Implement the feature described: $ARGUMENTS

## Implementation Process

### Phase 0: Portfolio Gate
0. **Check project constraints**
   - Read `~/.claude/portfolio/PORTFOLIO.md`
   - If Maintenance phase: ONLY bug fixes. Reject feature requests.
   - If Prototype phase: Skip tests, skip types, skip CI.
   - Match complexity to tier. T3/T4 = simplest possible implementation.

### Phase 1: Planning (Types First)

1. **Clarify Requirements**
   - What is the expected behavior?
   - What are the acceptance criteria?
   - Are there edge cases to consider?
   - Who are the users of this feature?

2. **Identify Scope**
   - Which files need to be created/modified?
   - What new types/interfaces are needed?
   - What's the data flow?
   - Are there database changes needed?

3. **Create Type Definitions**
   ```typescript
   // TypeScript: src/types/[feature].ts
   export interface FeatureName {
     id: string;
     // ... properties
   }
   ```

   ```python
   # Python: src/models/[feature].py
   from pydantic import BaseModel

   class FeatureName(BaseModel):
       id: str
       # ... fields
   ```

### Phase 2: Implementation (Backend First)

4. **Database Layer** (if applicable)
   - Create migrations
   - Add models/schemas
   - Update seed data if needed

5. **Service Layer**
   - Implement business logic
   - Use Result pattern for error handling
   - Add logging at key points

6. **API Layer** (if applicable)
   - Create endpoints following API patterns
   - Add input validation (Zod/Pydantic)
   - Implement proper error responses

### Phase 3: Implementation (Frontend)

7. **Components** (if applicable)
   - Create React components
   - Add custom hooks for data fetching
   - Implement state management

8. **Integration**
   - Connect frontend to backend
   - Add loading/error states
   - Implement optimistic updates if needed

### Phase 4: Testing

9. **Write Tests**
   ```bash
   # Unit tests for services
   # Integration tests for API
   # Component tests for UI
   ```

10. **Run Verification**
    ```bash
    # Type check
    npm run type-check || mypy src/

    # Run tests
    npm test -- --coverage || pytest --cov

    # Lint
    npm run lint || ruff check .
    ```

### Phase 5: Documentation & Commit

11. **Update Documentation**
    - Add JSDoc/docstrings for public APIs
    - Update README if needed
    - Add comments for complex logic only

12. **Create Commit**
    ```bash
    git add -A
    git commit -m "feat([scope]): [feature description]

    - Added [component/service]
    - Implemented [functionality]
    - Added tests for [areas]

    Closes #[issue-number]"
    ```

## Output Format

Provide implementation plan before coding, then implement step by step:

```markdown
## Feature Implementation: [Name]

### Implementation Plan
1. [Step 1] - [Files affected]
2. [Step 2] - [Files affected]
3. [Step 3] - [Files affected]

### Types Created
- `FeatureType` in `src/types/feature.ts`

### Files Created/Modified
| File | Type | Description |
|------|------|-------------|
| `src/types/feature.ts` | Created | Type definitions |
| `src/services/feature.ts` | Created | Business logic |
| `src/api/feature.ts` | Created | API endpoints |
| `tests/feature.test.ts` | Created | Test suite |

### Testing Summary
- Unit tests: X passing
- Integration tests: X passing
- Coverage: X%

### Usage Example
```[language]
// How to use the new feature
```

### Verification
- [x] Types defined
- [x] Backend implemented
- [x] Frontend implemented (if applicable)
- [x] Tests written
- [x] Type check passes
- [x] All tests pass
- [x] Documentation updated
```

## Implementation Principles

1. **Types First** - Define interfaces before implementation
2. **Small Steps** - Implement incrementally, verify often
3. **Test Alongside** - Write tests as you implement
4. **Follow Patterns** - Match existing codebase patterns
5. **No Placeholders** - Complete, working code only
6. **Minimal Scope** - Only implement what's requested
