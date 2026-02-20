# Portfolio Decision Framework

## Start New Project (ALL must be YES)
- [ ] <2 active feature branches right now?
- [ ] No open T1 bugs or blockers?
- [ ] Clear use case with defined user?
- [ ] Not a duplicate of existing project?
- [ ] Fits within a tier allocation (T1-60%, T2-30%, T3-10%)?

## Archive a Project (ANY ONE triggers archive)
- [ ] 90+ days with no commits
- [ ] Superseded by another project
- [ ] No longer aligned with business goals
- [ ] User count dropped to 0

## Phase Transitions

### Prototype -> Development
- [ ] Core feature works end-to-end
- [ ] At least 1 real user (even if just Austin)
- [ ] Clear next 3 features identified

### Development -> Hardening
- [ ] All planned features implemented
- [ ] Unit test coverage >60%
- [ ] No known critical bugs
- [ ] Feature freeze declared

### Hardening -> Maintenance
- [ ] Integration tests pass
- [ ] CI pipeline green
- [ ] Input validation on all external boundaries
- [ ] Deployed to production with 1+ week stable

### Maintenance -> Archive
- [ ] No active users for 90+ days
- [ ] Replacement exists OR need is gone

## Feature Freeze Triggers (ANY ONE activates freeze)
- Test coverage drops below 50%
- 3+ open bugs in the same project
- 2+ failed deployments in a week
- Production incident unresolved >24h
