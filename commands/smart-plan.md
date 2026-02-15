# Smart Plan - Multi-Phase Project Planning

Create a comprehensive implementation plan for: $ARGUMENTS

## Planning Process

### Phase 1: Requirements Analysis
1. **Clarify scope**
   - What is the expected outcome?
   - What are the acceptance criteria?
   - Are there constraints (time, technology, budget)?

2. **Identify stakeholders**
   - Who will use this feature?
   - Who needs to approve/review?
   - Are there external dependencies?

### Phase 2: Research & Context
3. **Explore the codebase**
   - Find related existing implementations
   - Identify patterns to follow
   - Note any technical debt or constraints

4. **Research best practices** (if needed)
   - Industry standards for this type of feature
   - Security considerations
   - Performance implications

### Phase 3: Architecture Design
5. **Design the solution**
   - High-level architecture
   - Data flow diagrams
   - API contracts (if applicable)
   - Database schema changes (if applicable)

6. **Create ADR (Architecture Decision Record)**
   ```markdown
   # ADR-[NUMBER]: [Title]

   ## Status
   Proposed

   ## Context
   [Why is this decision needed?]

   ## Decision
   [What is the decision?]

   ## Consequences
   [What are the positive and negative impacts?]

   ## Alternatives Considered
   [What other options were evaluated?]
   ```

### Phase 4: Task Breakdown
7. **Create implementation tasks**
   - Order by dependency (what must come first)
   - Estimate complexity (S/M/L)
   - Identify parallelizable work

## Output Format

```markdown
# Implementation Plan: [Feature Name]

## Overview
[1-2 paragraph summary of what will be built]

## Requirements
### Functional Requirements
- [ ] FR-1: [Requirement]
- [ ] FR-2: [Requirement]

### Non-Functional Requirements
- [ ] NFR-1: [Performance/Security/Accessibility requirement]

## Architecture

### High-Level Design
[Describe the architecture]

### Data Model Changes
```sql
-- Schema changes if applicable
```

### API Changes
```
POST /api/v1/resource
Request: { ... }
Response: { ... }
```

## Implementation Tasks

### Phase 1: Foundation (Prerequisites)
| Task | Complexity | Dependencies | Files |
|------|-----------|--------------|-------|
| Task 1 | S | None | path/to/file.ts |

### Phase 2: Core Implementation
| Task | Complexity | Dependencies | Files |
|------|-----------|--------------|-------|
| Task 2 | M | Task 1 | path/to/file.ts |

### Phase 3: Testing & Polish
| Task | Complexity | Dependencies | Files |
|------|-----------|--------------|-------|
| Add tests | M | Phase 2 | tests/ |

## Risk Assessment
| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Risk 1 | Medium | High | How to mitigate |

## Testing Strategy
- Unit tests: [What to test]
- Integration tests: [What to test]
- Manual testing: [Scenarios to verify]

## Rollout Plan
1. [Step 1]
2. [Step 2]

## Success Metrics
- [How will we know this is successful?]
```

## Planning Quality Standards
- All tasks should be completable in under 4 hours
- Dependencies must be explicitly listed
- Include rollback plan for risky changes
- Consider both happy path and error cases
