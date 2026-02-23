# Contributing

Thanks for your interest in contributing to claude-code-toolkit!

## Process

1. **Open an issue first** — describe what you want to change and why
2. **Fork the repository** and create a feature branch
3. **Make your changes** following the guidelines below
4. **Open a pull request** against `master`

## Requirements

- All existing tests must pass: `pytest automated-loop/tests/ -v`
- New features need tests
- No new dependencies without prior discussion (open an issue first)
- Keep changes small and focused — one PR per concern

## What the Maintainer Looks For

- **Clear description** — what changed and why
- **Small, focused changes** — easier to review and less risk
- **No CI/workflow changes** without prior discussion
- **No new external dependencies** without justification
- **Tests pass** and new functionality is covered

## Code Style

- Python: type hints on all functions, async/await for I/O, Pydantic for validation
- Follow existing patterns in the codebase
- No dynamic code execution or shell commands with unsanitized input

## Questions?

Open an issue — happy to help.
