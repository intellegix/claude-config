# Portfolio Status Review

Review the health of all projects in the portfolio.

## Process

### 1. Load Portfolio Registry
Read `~/.claude/portfolio/PORTFOLIO.md` and display the project table.

### 2. Check Velocity Constraints
```bash
# Count active feature branches across all known project directories
# Flag if >2 active branches
```
- List all active feature branches across T1/T2 projects
- Flag velocity violations (>2 active branches)

### 3. Check T1 Project Health
For each T1 project directory that exists locally:
```bash
# Check for uncommitted changes (risk flag)
git -C [project_dir] status --porcelain

# Check last commit date (stale flag if >30 days)
git -C [project_dir] log -1 --format="%ci" 2>/dev/null
```

### 4. Check T2 Project Health
For each T2 project:
- Last commit date
- Active branches

### 5. Flag Issues
Report any of:
- Active branches > 2 (VELOCITY VIOLATION)
- T1 projects with uncommitted changes (RISK)
- Projects with no commits in 30+ days (STALE)
- Phase mismatches (e.g., Maintenance project with feature branches)

## Output Format

```markdown
## Portfolio Status — [Date]

### Velocity: [OK / VIOLATION]
Active branches: [count]/2 max
[List branches if any]

### T1 Production (60%)
| Project | Status | Last Commit | Open Branches | Issues |
|---------|--------|-------------|---------------|--------|

### T2 Strategic (30%)
| Project | Status | Last Commit | Open Branches | Issues |
|---------|--------|-------------|---------------|--------|

### T3 Experimental (10%)
[Brief status — no deep checks needed]

### Flags
- [Any violations, risks, or stale projects]

### Recommended Actions
- [Actionable next steps based on findings]
```
