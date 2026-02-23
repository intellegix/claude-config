"""Research bridge for automated Claude loop — queries Perplexity via Playwright browser automation.

Gathers project context (CLAUDE.md, MEMORY.md, git log, workflow state)
and builds a structured research query for Perplexity to determine next steps.
Uses council_browser.py subprocess for Playwright-based Perplexity research.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from config import Result, RetryConfig, SecurityConfig

logger = logging.getLogger(__name__)

COUNCIL_BROWSER_SCRIPT = Path.home() / ".claude" / "council-automation" / "council_browser.py"


class ResearchResult(BaseModel):
    """Result from a Perplexity research query."""

    query: str
    response: str
    model: str = "perplexity-research"
    cost_estimate: float = 0.0
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class SessionContext:
    """Gathers project context for research queries."""

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path)

    def gather(self) -> dict[str, str]:
        """Collect all available context from the project."""
        ctx: dict[str, str] = {}

        # CLAUDE.md
        claude_md = self.project_path / "CLAUDE.md"
        if claude_md.exists():
            ctx["claude_md"] = claude_md.read_text(encoding="utf-8")[:3000]

        # MEMORY.md (check project and auto-memory dir)
        memory_md = self.project_path / "MEMORY.md"
        if memory_md.exists():
            ctx["memory_md"] = memory_md.read_text(encoding="utf-8")[:2000]

        # Workflow state
        state_file = self.project_path / ".workflow" / "state.json"
        if state_file.exists():
            try:
                state = json.loads(state_file.read_text(encoding="utf-8"))
                ctx["workflow_state"] = json.dumps(
                    {
                        "iteration": state.get("iteration", 0),
                        "status": state.get("status", "unknown"),
                        "metrics": state.get("metrics", {}),
                        "last_session_id": state.get("last_session_id"),
                    },
                    indent=2,
                )
            except (json.JSONDecodeError, KeyError):
                pass

        # Git log (last 10 commits)
        git_log = self._get_git_log()
        if git_log:
            ctx["git_log"] = git_log

        # Recent research result
        research_file = self.project_path / ".workflow" / "research_result.md"
        if research_file.exists():
            ctx["last_research"] = research_file.read_text(encoding="utf-8")[:2000]

        return ctx

    def _get_git_log(self) -> Optional[str]:
        """Get recent git log, returns None if not a git repo."""
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                cwd=str(self.project_path),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return None


# Error codes that are transient and worth retrying
RETRYABLE_ERRORS = {"TIMEOUT", "PLAYWRIGHT_ERROR", "PARSE_ERROR"}


class ResearchBridge:
    """Queries Perplexity via Playwright browser automation with project context."""

    def __init__(
        self,
        project_path: str | Path,
        retry_config: Optional[RetryConfig] = None,
        research_timeout: int = 600,
        headful: bool = True,
        perplexity_mode: str = "research",
    ) -> None:
        self.project_path = Path(project_path)
        self.context = SessionContext(project_path)
        self.retry_config = retry_config or RetryConfig()
        self.research_timeout = research_timeout
        self.headful = headful
        self.perplexity_mode = perplexity_mode

        # Circuit breaker state
        self._consecutive_failures: int = 0
        self._last_failure_time: float = 0.0

    def build_query(self, extra_context: Optional[str] = None) -> str:
        """Build a structured research query from project context."""
        ctx = self.context.gather()

        parts = [
            "You are a software development strategist analyzing a project's current state.",
            "Based on the context below, provide specific, actionable next steps.",
            "Focus on: what to implement next, potential blockers, and strategic priorities.",
            "",
        ]

        if ctx.get("claude_md"):
            parts.append("## Project Definition (CLAUDE.md)")
            parts.append(ctx["claude_md"])
            parts.append("")

        if ctx.get("workflow_state"):
            parts.append("## Current Workflow State")
            parts.append(ctx["workflow_state"])
            parts.append("")

        if ctx.get("git_log"):
            parts.append("## Recent Commits")
            parts.append(ctx["git_log"])
            parts.append("")

        if ctx.get("last_research"):
            parts.append("## Previous Research Result")
            parts.append(ctx["last_research"])
            parts.append("")

        if extra_context:
            parts.append("## Additional Context")
            parts.append(extra_context)
            parts.append("")

        parts.append("## Question")
        parts.append(
            "What are the top 3-5 most important next steps for this project? "
            "Be specific about files to modify, features to implement, and potential issues. "
            "If the project appears complete, respond with PROJECT_COMPLETE."
        )

        return "\n".join(parts)

    def _is_circuit_open(self) -> bool:
        """Check if circuit breaker is tripped (too many consecutive failures)."""
        if self._consecutive_failures < self.retry_config.circuit_breaker_threshold:
            return False
        elapsed = time.monotonic() - self._last_failure_time
        if elapsed >= self.retry_config.circuit_breaker_reset_seconds:
            # Reset circuit breaker after cooldown
            logger.info("Circuit breaker reset after %.1fs cooldown", elapsed)
            self._consecutive_failures = 0
            return False
        return True

    def _record_failure(self) -> None:
        """Record a failure for circuit breaker tracking."""
        self._consecutive_failures += 1
        self._last_failure_time = time.monotonic()

    def _record_success(self) -> None:
        """Reset circuit breaker on success."""
        self._consecutive_failures = 0

    def _is_retryable(self, result: Result[ResearchResult]) -> bool:
        """Check if a failed result is worth retrying."""
        if result.success:
            return False
        if result.error_code not in RETRYABLE_ERRORS:
            return False
        return True

    def _calculate_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter."""
        delay = self.retry_config.base_delay_seconds * (2 ** attempt)
        delay = min(delay, self.retry_config.max_delay_seconds)
        # Add jitter: 0.5x to 1.5x
        jitter = 0.5 + random.random()
        return delay * jitter

    def query(self, extra_context: Optional[str] = None) -> Result[ResearchResult]:
        """Execute a research query with retry and circuit breaker."""
        if self._is_circuit_open():
            return Result.fail(
                f"Circuit breaker open: {self._consecutive_failures} consecutive failures. "
                f"Resets after {self.retry_config.circuit_breaker_reset_seconds}s.",
                "CIRCUIT_OPEN",
            )

        last_result: Result[ResearchResult] = Result.fail("No attempts made", "UNKNOWN")

        for attempt in range(self.retry_config.max_retries + 1):
            last_result = self._single_query(extra_context)

            if last_result.success:
                self._record_success()
                return last_result

            self._record_failure()

            if not self._is_retryable(last_result):
                logger.warning(
                    "Non-retryable error: [%s] %s",
                    last_result.error_code, last_result.error,
                )
                return last_result

            if attempt < self.retry_config.max_retries:
                delay = self._calculate_delay(attempt)
                logger.info(
                    "Retry %d/%d after %.1fs (error: %s)",
                    attempt + 1, self.retry_config.max_retries,
                    delay, last_result.error_code,
                )
                time.sleep(delay)

        return last_result

    def _single_query(self, extra_context: Optional[str] = None) -> Result[ResearchResult]:
        """Execute a single research query via Playwright browser automation (no retry)."""
        query_text = self.build_query(extra_context)

        try:
            cmd = [
                sys.executable, str(COUNCIL_BROWSER_SCRIPT),
                "--perplexity-mode", self.perplexity_mode,
                query_text,
            ]
            if self.headful:
                cmd.insert(2, "--headful")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.research_timeout,
            )

            if result.returncode != 0:
                stderr = result.stderr.strip() if result.stderr else "Unknown error"
                return Result.fail(
                    f"Playwright subprocess failed (exit {result.returncode}): {stderr}",
                    "PLAYWRIGHT_ERROR",
                )

            data = json.loads(result.stdout)

            if data.get("error"):
                return Result.fail(data["error"], "PLAYWRIGHT_ERROR")

            content = data.get("synthesis", "")
            if not content:
                return Result.fail("Empty response from Perplexity research", "PARSE_ERROR")

            research_result = ResearchResult(
                query=query_text[:500],
                response=content,
                model=f"perplexity-{self.perplexity_mode}",
            )

            # Save to .workflow/research_result.md
            self._save_result(research_result)

            return Result.ok(research_result)

        except subprocess.TimeoutExpired:
            return Result.fail(
                f"Playwright research timed out ({self.research_timeout}s)", "TIMEOUT"
            )
        except json.JSONDecodeError as e:
            return Result.fail(f"Invalid JSON from Playwright subprocess: {e}", "PARSE_ERROR")
        except FileNotFoundError:
            return Result.fail(
                f"council_browser.py not found at {COUNCIL_BROWSER_SCRIPT}", "SCRIPT_NOT_FOUND"
            )
        except Exception as e:
            return Result.fail(f"Research query failed: {e}", "QUERY_ERROR")

    def _save_result(self, result: ResearchResult) -> None:
        """Save research result to .workflow/research_result.md."""
        output_path = self.project_path / ".workflow" / "research_result.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        content = (
            f"# Research Result\n\n"
            f"**Timestamp:** {result.timestamp}\n"
            f"**Model:** {result.model}\n\n"
            f"---\n\n"
            f"{result.response}\n"
        )
        output_path.write_text(content, encoding="utf-8")
        logger.info("Research result saved to %s", output_path)


def main() -> None:
    """CLI entry point for standalone research bridge usage."""
    parser = argparse.ArgumentParser(description="Query Perplexity for project next steps")
    parser.add_argument("--project", default=".", help="Project directory path")
    parser.add_argument(
        "--mode", default="playwright", choices=["playwright"],
        help="Query mode (playwright only)",
    )
    parser.add_argument("--context", default=None, help="Extra context to include")
    parser.add_argument("--headful", action="store_true", help="Run browser in visible mode")
    parser.add_argument(
        "--perplexity-mode", default="research",
        choices=["research", "council", "labs"],
        help="Perplexity query mode",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Install log redaction filter
    from log_redactor import RedactingFilter

    sec = SecurityConfig()
    for handler in logging.root.handlers:
        handler.addFilter(RedactingFilter(sec.log_redact_patterns))

    bridge = ResearchBridge(
        args.project,
        headful=args.headful,
        perplexity_mode=args.perplexity_mode,
    )
    result = bridge.query(extra_context=args.context)

    if result.success and result.data:
        print(f"\n{'='*60}")
        print("Research Result:")
        print(f"{'='*60}")
        print(result.data.response)
        print(f"\n{'='*60}")
        print(f"Saved to: {Path(args.project) / '.workflow' / 'research_result.md'}")
    else:
        print(f"ERROR [{result.error_code}]: {result.error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
