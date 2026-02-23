# Security Policy

## Reporting a Vulnerability

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, email security concerns to: **austin@intellegix.com**

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline
- **Acknowledgment**: Within 72 hours
- **Assessment**: Within 1 week
- **Fix/disclosure**: Coordinated with reporter

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest on `master` | Yes |
| Older commits | No |

## Security Practices

This repository has the following security controls enabled:

- **Branch protection** on `master` — all changes go through pull requests
- **CI/CD** — automated tests run on every PR
- **CodeQL** — static analysis for code vulnerabilities
- **Dependency review** — blocks PRs that introduce high-severity vulnerabilities
- **Dependabot** — automated security updates for dependencies
- **OpenSSF Scorecard** — continuous security posture monitoring
- **Secret scanning + push protection** — prevents accidental credential commits
- **SHA-pinned Actions** — all GitHub Actions pinned to full commit SHA to prevent supply chain attacks
- **PR security checklist** — manual review checklist for every pull request
