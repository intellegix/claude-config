# Portfolio Registry v1.0
# Austin Kidwell | Intellegix + ASR Inc

## Velocity Constraints
- MAX 2 active feature branches across all projects
- Prototype phase = working code only, NO infrastructure
- If feature estimate >4h, break it down or question scope
- Default to SIMPLEST solution for the user count

## Project Registry

| Project | Tier | Phase | Users | Next Priority | DO NOT |
|---------|------|-------|-------|--------------|--------|
| Certified Payroll 2.0 | T1 | Maintenance | 2 | Bug fixes only | Add features, add infra, refactor |
| ASR Records App | T1 | Development | 5 | Core CRUD | Over-engineer, add monitoring |
| P.O. System | T1 | Development | 3 | Clark Rep sync | Add analytics, add dashboards |
| AI Audio Transcriber | T2 | Development | 1 | Core transcription | Add auth, add rate limiting |
| Automated Claude | T2 | Development | 1 | CLI workflow | Add UI, add database |
| Claude Watcher | T2 | Prototype | 1 | Working MVP | Add tests, add CI, add types |
| AI TV 2.0 | T2 | Development | 2 | Content pipeline | Add billing, add user mgmt |
| AI Tuxemon | T3 | Prototype | 1 | Playable demo | Add anything beyond gameplay |
| Languages App | T3 | Prototype | 1 | Working vocab UI | Add backend, add auth |
| Remote Mobile UI | T3 | Maintenance | 1 | Keep running | Kill the server process |
| Perplexity Voice | T3 | Prototype | 1 | Voice input works | Add UI polish, add settings |
| Podcast Builder | T3 | Prototype | 1 | Audio generation | Add hosting, add analytics |
| PokeFireRed | T4 | Archive | 0 | None | Touch it |
| Intellegix Chrome Ext | T4 | Archive | 0 | None | Touch it |
| AI City Experiment | T4 | Archive | 0 | None | Touch it |

## Tier Definitions

| Tier | Effort | What It Means |
|------|--------|---------------|
| T1 Production | 60% | Revenue-generating or business-critical. Bug fixes prioritized. |
| T2 Strategic | 30% | Future value. Active development with clear goals. |
| T3 Experimental | 10% | Learning/exploration. Minimal investment. |
| T4 Archive | 0% | Dead. Do not allocate any time. |

## Phase Definitions

| Phase | Allowed | Forbidden |
|-------|---------|-----------|
| Prototype | Working code, hardcoded values, console.log | Tests, CI, types, monitoring, auth, infra |
| Development | Unit tests, basic types, simple error handling | Sentry, rate limiting, audit logging, circuit breakers |
| Hardening | Integration tests, CI, input validation, logging | New features (feature freeze) |
| Maintenance | Bug fixes, security patches, dependency updates | New features, refactors, infra changes |
| Archive | Nothing | Everything |

## Anti-Patterns (NEVER DO)

1. Add Sentry/error tracking to apps with <10 users
2. Add rate limiting to apps with <10 users
3. Add audit logging to apps with <10 users
4. Add circuit breakers to apps with <10 users
5. Write >150 lines in a project CLAUDE.md (use ARCHITECTURE.md for detail)
6. Add CI/CD to prototype-phase projects
7. Add authentication to single-user tools
8. Create monitoring dashboards for apps with <5 users
9. Add database migrations to SQLite-only projects
10. Spend >30 min on infrastructure for T3/T4 projects
