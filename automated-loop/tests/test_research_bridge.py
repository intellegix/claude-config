"""Tests for research_bridge module."""

import json
import subprocess as sp
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import RetryConfig
from research_bridge import ResearchBridge, SessionContext

from helpers import (
    mock_git_log_result,
    mock_playwright_error,
    mock_playwright_result,
    make_research_dispatcher,
)


@pytest.fixture
def research_project_dir(tmp_path: Path) -> Path:
    """Create a project with specific state for research bridge tests."""
    workflow_dir = tmp_path / ".workflow"
    workflow_dir.mkdir()

    (tmp_path / "CLAUDE.md").write_text(
        "# Test Project\nA simple test project.", encoding="utf-8"
    )

    state = {
        "session_id": "test-session",
        "iteration": 3,
        "status": "running",
        "metrics": {"total_cost_usd": 0.15, "total_turns": 10},
    }
    (workflow_dir / "state.json").write_text(
        json.dumps(state), encoding="utf-8"
    )

    return tmp_path


@pytest.fixture
def bare_project_dir(tmp_path: Path) -> Path:
    """Create a bare project with no files."""
    workflow_dir = tmp_path / ".workflow"
    workflow_dir.mkdir()
    return tmp_path


class TestSessionContext:
    def test_gather_with_claude_md(self, research_project_dir: Path) -> None:
        ctx = SessionContext(research_project_dir)
        result = ctx.gather()

        assert "claude_md" in result
        assert "Test Project" in result["claude_md"]

    def test_gather_with_workflow_state(self, research_project_dir: Path) -> None:
        ctx = SessionContext(research_project_dir)
        result = ctx.gather()

        assert "workflow_state" in result
        state = json.loads(result["workflow_state"])
        assert state["iteration"] == 3
        assert state["status"] == "running"

    def test_gather_without_claude_md(self, bare_project_dir: Path) -> None:
        ctx = SessionContext(bare_project_dir)
        result = ctx.gather()

        assert "claude_md" not in result

    def test_gather_with_memory_md(self, research_project_dir: Path) -> None:
        memory = research_project_dir / "MEMORY.md"
        memory.write_text("# Key learnings\n- Thing 1", encoding="utf-8")

        ctx = SessionContext(research_project_dir)
        result = ctx.gather()

        assert "memory_md" in result
        assert "Key learnings" in result["memory_md"]

    def test_gather_with_research_result(self, research_project_dir: Path) -> None:
        research = research_project_dir / ".workflow" / "research_result.md"
        research.write_text("# Previous Result\nDo X next.", encoding="utf-8")

        ctx = SessionContext(research_project_dir)
        result = ctx.gather()

        assert "last_research" in result
        assert "Do X next" in result["last_research"]

    def test_git_log_not_in_non_repo(self, bare_project_dir: Path) -> None:
        ctx = SessionContext(bare_project_dir)
        result = ctx.gather()

        # Not a git repo, so no git_log
        assert "git_log" not in result


class TestResearchBridge:
    def test_build_query_includes_context(self, research_project_dir: Path) -> None:
        bridge = ResearchBridge(research_project_dir)
        query = bridge.build_query()

        assert "Test Project" in query
        assert "Workflow State" in query
        assert "next steps" in query.lower()

    def test_build_query_with_extra_context(self, research_project_dir: Path) -> None:
        bridge = ResearchBridge(research_project_dir)
        query = bridge.build_query(extra_context="Focus on performance optimization")

        assert "performance optimization" in query.lower()

    @patch("research_bridge.subprocess.run")
    def test_successful_query(self, mock_run: MagicMock, research_project_dir: Path) -> None:
        mock_run.side_effect = make_research_dispatcher(
            playwright_result=mock_playwright_result("Next steps: 1. Implement caching 2. Add tests")
        )

        bridge = ResearchBridge(research_project_dir)
        result = bridge.query()

        assert result.success
        assert result.data is not None
        assert "Implement caching" in result.data.response

        # Verify result was saved
        research_file = research_project_dir / ".workflow" / "research_result.md"
        assert research_file.exists()
        content = research_file.read_text(encoding="utf-8")
        assert "Implement caching" in content

    @patch("research_bridge.subprocess.run")
    def test_playwright_timeout(self, mock_run: MagicMock, research_project_dir: Path) -> None:
        mock_run.side_effect = make_research_dispatcher(
            playwright_side_effect=sp.TimeoutExpired(cmd="python", timeout=600)
        )

        bridge = ResearchBridge(research_project_dir)
        result = bridge.query()

        assert not result.success
        assert result.error_code == "TIMEOUT"

    @patch("research_bridge.subprocess.run")
    def test_playwright_error_response(self, mock_run: MagicMock, research_project_dir: Path) -> None:
        mock_run.side_effect = make_research_dispatcher(
            playwright_result=mock_playwright_error("Browser session expired")
        )

        bridge = ResearchBridge(research_project_dir)
        result = bridge.query()

        assert not result.success
        assert result.error_code == "PLAYWRIGHT_ERROR"
        assert "Browser session expired" in result.error

    @patch("research_bridge.subprocess.run")
    def test_subprocess_crash(self, mock_run: MagicMock, research_project_dir: Path) -> None:
        mock_run.side_effect = make_research_dispatcher(
            playwright_result=MagicMock(returncode=1, stdout="", stderr="Traceback...")
        )

        bridge = ResearchBridge(research_project_dir)
        result = bridge.query()

        assert not result.success
        assert result.error_code == "PLAYWRIGHT_ERROR"

    @patch("research_bridge.subprocess.run")
    def test_invalid_json_response(self, mock_run: MagicMock, research_project_dir: Path) -> None:
        mock_run.side_effect = make_research_dispatcher(
            playwright_result=MagicMock(returncode=0, stdout="not json {{{", stderr="")
        )

        bridge = ResearchBridge(research_project_dir)
        result = bridge.query()

        assert not result.success
        assert result.error_code == "PARSE_ERROR"

    @patch("research_bridge.subprocess.run")
    def test_empty_synthesis_response(self, mock_run: MagicMock, research_project_dir: Path) -> None:
        mock_run.side_effect = make_research_dispatcher(
            playwright_result=MagicMock(
                returncode=0,
                stdout=json.dumps({"synthesis": "", "execution_time_ms": 1000}),
                stderr="",
            )
        )

        bridge = ResearchBridge(research_project_dir)
        result = bridge.query()

        assert not result.success
        assert result.error_code == "PARSE_ERROR"


class TestRetryAndCircuitBreaker:
    """Tests for retry, backoff, and circuit breaker logic."""

    @pytest.fixture
    def fast_retry_config(self) -> RetryConfig:
        """Retry config with near-zero delays for fast tests."""
        return RetryConfig(
            max_retries=3,
            base_delay_seconds=0.001,
            max_delay_seconds=0.01,
            circuit_breaker_threshold=3,
            circuit_breaker_reset_seconds=0.1,
        )

    @patch("research_bridge.subprocess.run")
    def test_retry_exhaustion_returns_last_error(
        self, mock_run: MagicMock, research_project_dir: Path, fast_retry_config: RetryConfig
    ) -> None:
        """After max_retries, returns the last error result."""
        mock_run.side_effect = make_research_dispatcher(
            playwright_side_effect=sp.TimeoutExpired(cmd="python", timeout=600)
        )

        bridge = ResearchBridge(
            research_project_dir, retry_config=fast_retry_config
        )
        result = bridge.query()

        assert not result.success
        assert result.error_code == "TIMEOUT"

    @patch("research_bridge.time.sleep")
    @patch("research_bridge.subprocess.run")
    def test_backoff_delay_increases(
        self, mock_run: MagicMock, mock_sleep: MagicMock, research_project_dir: Path
    ) -> None:
        """Backoff delays increase with each attempt."""
        mock_run.side_effect = make_research_dispatcher(
            playwright_side_effect=sp.TimeoutExpired(cmd="python", timeout=600)
        )

        config = RetryConfig(
            max_retries=3, base_delay_seconds=1.0, max_delay_seconds=30.0,
            circuit_breaker_threshold=10,
        )
        bridge = ResearchBridge(
            research_project_dir, retry_config=config
        )
        bridge.query()

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert len(delays) == 3
        assert delays[0] >= 0.5
        assert delays[1] >= 1.0
        assert delays[2] >= 2.0

    @patch("research_bridge.subprocess.run")
    def test_circuit_breaker_trips_after_threshold(
        self, mock_run: MagicMock, research_project_dir: Path, fast_retry_config: RetryConfig
    ) -> None:
        """Circuit breaker opens after threshold consecutive failures."""
        mock_run.side_effect = make_research_dispatcher(
            playwright_side_effect=sp.TimeoutExpired(cmd="python", timeout=600)
        )

        bridge = ResearchBridge(
            research_project_dir, retry_config=fast_retry_config
        )
        bridge.query()

        result = bridge.query()
        assert not result.success
        assert result.error_code == "CIRCUIT_OPEN"

    @patch("research_bridge.subprocess.run")
    def test_circuit_breaker_resets_after_cooldown(
        self, mock_run: MagicMock, research_project_dir: Path, fast_retry_config: RetryConfig
    ) -> None:
        """Circuit breaker resets after cooldown period."""
        mock_run.side_effect = make_research_dispatcher(
            playwright_side_effect=sp.TimeoutExpired(cmd="python", timeout=600)
        )

        bridge = ResearchBridge(
            research_project_dir, retry_config=fast_retry_config
        )
        bridge.query()  # Trip the breaker

        time.sleep(0.15)

        result = bridge.query()
        assert result.error_code != "CIRCUIT_OPEN"

    @patch("research_bridge.subprocess.run")
    def test_playwright_error_retries(
        self, mock_run: MagicMock, research_project_dir: Path, fast_retry_config: RetryConfig
    ) -> None:
        """Playwright errors (retryable) trigger retries."""
        mock_run.side_effect = make_research_dispatcher(
            playwright_result=mock_playwright_error("Browser timeout")
        )

        bridge = ResearchBridge(
            research_project_dir, retry_config=fast_retry_config
        )
        result = bridge.query()

        assert not result.success
        assert result.error_code == "PLAYWRIGHT_ERROR"

    @patch("research_bridge.subprocess.run")
    def test_non_retryable_fails_immediately(
        self, mock_run: MagicMock, research_project_dir: Path, fast_retry_config: RetryConfig
    ) -> None:
        """Non-retryable errors (PARSE_ERROR) fail immediately without retry."""
        mock_run.side_effect = make_research_dispatcher(
            playwright_result=MagicMock(returncode=0, stdout="not json {{{", stderr="")
        )

        bridge = ResearchBridge(
            research_project_dir, retry_config=fast_retry_config
        )
        result = bridge.query()

        assert not result.success
        assert result.error_code == "PARSE_ERROR"
        council_calls = [
            c for c in mock_run.call_args_list
            if c[0] and isinstance(c[0][0], list) and c[0][0][0] != "git"
        ]
        assert len(council_calls) == 1

    @patch("research_bridge.time.sleep")
    @patch("research_bridge.subprocess.run")
    def test_jitter_present_in_delays(
        self, mock_run: MagicMock, mock_sleep: MagicMock, research_project_dir: Path
    ) -> None:
        """Delays include jitter (not exact powers of 2)."""
        mock_run.side_effect = make_research_dispatcher(
            playwright_side_effect=sp.TimeoutExpired(cmd="python", timeout=600)
        )

        config = RetryConfig(
            max_retries=2, base_delay_seconds=1.0, max_delay_seconds=30.0,
            circuit_breaker_threshold=10,
        )
        bridge = ResearchBridge(
            research_project_dir, retry_config=config
        )
        bridge.query()

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert len(delays) == 2
        assert delays[0] != 1.0
        assert delays[1] != 2.0

    @patch("research_bridge.subprocess.run")
    def test_success_resets_circuit_breaker(
        self, mock_run: MagicMock, research_project_dir: Path, fast_retry_config: RetryConfig
    ) -> None:
        """A successful query resets the circuit breaker failure count."""
        call_count = [0]

        def smart_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "git":
                return mock_git_log_result()
            call_count[0] += 1
            if call_count[0] <= 2:
                raise sp.TimeoutExpired(cmd="python", timeout=600)
            return mock_playwright_result("Next steps...")

        mock_run.side_effect = smart_side_effect

        bridge = ResearchBridge(
            research_project_dir, retry_config=RetryConfig(
                max_retries=0, base_delay_seconds=0.001, max_delay_seconds=0.01,
                circuit_breaker_threshold=5, circuit_breaker_reset_seconds=0.1,
            )
        )
        bridge.query()  # Failure 1
        bridge.query()  # Failure 2
        assert bridge._consecutive_failures == 2

        result = bridge.query()
        assert result.success
        assert bridge._consecutive_failures == 0
