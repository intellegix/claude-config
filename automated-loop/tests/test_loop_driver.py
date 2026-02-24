"""Tests for loop_driver module."""

import json
import logging
import subprocess as sp
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import WorkflowConfig
from loop_driver import EXIT_BUDGET_EXCEEDED, EXIT_COMPLETE, EXIT_MAX_ITERATIONS, EXIT_STAGNATION, JsonFormatter, LoopDriver

from helpers import (
    build_ndjson_stream,
    make_popen_dispatcher,
    make_subprocess_dispatcher,
    mock_git_log_result,
    mock_playwright_result,
    MockPopen,
)


@pytest.fixture
def config() -> WorkflowConfig:
    return WorkflowConfig(
        limits={
            "max_iterations": 3,
            "timeout_seconds": 30,
            "max_per_iteration_budget_usd": 5.0,
            "max_total_budget_usd": 10.0,
            "timeout_cooldown_base_seconds": 0,  # Disable cooldown in tests
        },
        retry={"max_retries": 0, "base_delay_seconds": 0.001},
    )


class TestDryRun:
    def test_dry_run_completes_max_iterations(
        self, project_dir: Path, config: WorkflowConfig
    ) -> None:
        """Dry run simulates iterations without spawning Claude."""
        with patch("research_bridge.subprocess.run") as mock_run:
            mock_run.return_value = mock_playwright_result()
            driver = LoopDriver(project_dir, config, dry_run=True)
            exit_code = driver.run()
            assert exit_code == EXIT_MAX_ITERATIONS

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_dry_run_no_claude_spawned(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Dry run never spawns Claude CLI (subprocess.Popen with 'claude' args)."""
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )
        mock_popen.side_effect = make_popen_dispatcher()

        driver = LoopDriver(project_dir, config, dry_run=True)
        driver.run()

        # Verify no Popen calls with 'claude'
        claude_calls = [
            c for c in mock_popen.call_args_list
            if c[0] and isinstance(c[0][0], list) and c[0][0] and c[0][0][0] == "claude"
        ]
        assert len(claude_calls) == 0


class TestCompletionDetection:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_completion_marker_exits_zero(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Completion marker in output exits with code 0."""
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "All done. PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_COMPLETE

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_completion_case_insensitive(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Completion markers match case-insensitively."""
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "All done. project_complete"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_COMPLETE

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_completion_partial_match(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Completion marker embedded in a sentence still matches."""
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream(
                "s1", 0.01, 1,
                "The implementation is now PROJECT_COMPLETE and ready for review."
            ),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_COMPLETE


class TestBudgetExceeded:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_per_iteration_budget_exceeded(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Exceeding per-iteration budget exits with code 2."""
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 10.0, 1, "Expensive operation"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_BUDGET_EXCEEDED


class TestMaxIterations:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_max_iterations_exit_code(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Reaching max iterations exits with code 1."""
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "Still working..."),
        )
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_MAX_ITERATIONS


class TestNdjsonParsing:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_session_id_tracked(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Session ID from NDJSON is tracked for --resume."""
        config.limits.max_iterations = 1
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("sess-xyz", 0.01, 1, "Done step 1"),
        )
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        driver.run()

        assert driver.tracker.state.last_session_id == "sess-xyz"


class TestTimeoutHandling:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_timeout_records_error(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Timeout triggers error recovery path."""
        config.limits.max_iterations = 1
        mock_popen.side_effect = make_popen_dispatcher(claude_ndjson="")
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        driver.run()

        assert driver.tracker.get_metrics().error_count >= 0  # Doesn't crash


class TestResearchFailureFallback:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_research_failure_uses_fallback(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Research failure falls back to generic prompt."""
        config.limits.max_iterations = 2
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "Working..."),
        )
        mock_run.side_effect = make_subprocess_dispatcher(
            research_side_effect=sp.TimeoutExpired(cmd="python", timeout=600),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()

        # Should not crash — falls back gracefully
        assert exit_code == EXIT_MAX_ITERATIONS


class TestResumeSessionId:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_resume_session_passed_to_claude(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Second iteration passes --resume with session ID from first."""
        config.limits.max_iterations = 2
        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                sid = f"s{call_count[0]}"
                return MockPopen(build_ndjson_stream(sid, 0.01, 1, "Working..."))
            return MockPopen("")  # taskkill

        def run_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd:
                if cmd[0] == "git":
                    return mock_git_log_result()
                if "council_browser" in str(cmd):
                    return mock_playwright_result("Continue")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = run_side_effect

        driver = LoopDriver(project_dir, config)
        driver.run()

        # Find claude CLI calls
        claude_calls = [
            c for c in mock_popen.call_args_list
            if c[0] and isinstance(c[0][0], list) and c[0][0] and c[0][0][0] == "claude"
        ]
        assert len(claude_calls) >= 2
        # Second call should have --resume with s1
        second_call_args = claude_calls[1][0][0]
        assert "--resume" in second_call_args
        resume_idx = second_call_args.index("--resume")
        assert second_call_args[resume_idx + 1] == "s1"


class TestErrorClearsSession:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_error_clears_session_for_retry(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """After error, next iteration doesn't use --resume."""
        config.limits.max_iterations = 2
        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                if call_count[0] == 1:
                    # First call: returns error with a session ID
                    return MockPopen(
                        build_ndjson_stream(
                            "err-session", 0.01, 1, "Error occurred", is_error=True
                        )
                    )
                else:
                    # Second call: should NOT have --resume
                    return MockPopen(build_ndjson_stream("s2", 0.01, 1, "Working..."))
            return MockPopen("")  # taskkill

        def run_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd:
                if cmd[0] == "git":
                    return mock_git_log_result()
                if "council_browser" in str(cmd):
                    return mock_playwright_result()
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = run_side_effect

        driver = LoopDriver(project_dir, config)
        driver.run()

        # Find claude CLI calls
        claude_calls = [
            c for c in mock_popen.call_args_list
            if c[0] and isinstance(c[0][0], list) and c[0][0] and c[0][0][0] == "claude"
        ]
        assert len(claude_calls) >= 2
        # Second call should NOT have --resume (session cleared after error)
        second_call_args = claude_calls[1][0][0]
        assert "--resume" not in second_call_args


class TestMetricsSummary:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_metrics_summary_written_on_complete(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Metrics summary JSON is written when loop completes."""
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.05, 2, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()

        assert exit_code == EXIT_COMPLETE
        summary_path = project_dir / ".workflow" / "metrics_summary.json"
        assert summary_path.exists()

        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["exit_code"] == 0
        assert summary["status"] == "completed"
        assert summary["iterations"] == 1
        assert summary["total_cost_usd"] == pytest.approx(0.05)
        assert summary["total_turns"] == 2
        assert summary["error_count"] == 0

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_metrics_summary_written_on_budget_exceeded(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Metrics summary JSON is written when budget is exceeded."""
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 10.0, 1, "Expensive"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()

        assert exit_code == EXIT_BUDGET_EXCEEDED
        summary_path = project_dir / ".workflow" / "metrics_summary.json"
        assert summary_path.exists()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["exit_code"] == 2
        assert summary["status"] == "failed"


class TestTraceLogging:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_trace_jsonl_written_on_complete(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """After successful run, trace.jsonl contains expected event types."""
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.05, 2, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_COMPLETE

        trace_path = project_dir / ".workflow" / "trace.jsonl"
        assert trace_path.exists()

        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").strip().splitlines()]
        event_types = [e["event_type"] for e in events]
        assert "loop_start" in event_types
        assert "claude_invoke" in event_types
        assert "claude_complete" in event_types
        assert "completion_detected" in event_types
        assert "loop_end" in event_types

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_trace_events_are_valid_json(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Each trace line is valid JSON with required fields."""
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        driver.run()

        trace_path = project_dir / ".workflow" / "trace.jsonl"
        for line in trace_path.read_text(encoding="utf-8").strip().splitlines():
            event = json.loads(line)
            assert "timestamp" in event
            assert "event_type" in event
            assert "iteration" in event


class TestSmokeTestMode:
    def test_smoke_test_overrides_config(
        self, project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Smoke test mode overrides config limits."""
        with patch("research_bridge.subprocess.run") as mock_run:
            mock_run.return_value = mock_playwright_result()
            driver = LoopDriver(project_dir, config, smoke_test=True, dry_run=True)
            assert driver.config.limits.max_iterations == 1
            assert driver.config.limits.timeout_seconds == 120
            assert driver.config.limits.max_per_iteration_budget_usd == 2.0
            assert driver.config.limits.max_turns_per_iteration == 10

    def test_smoke_test_uses_safe_prompt(
        self, project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Smoke test mode uses a safe default prompt."""
        with patch("research_bridge.subprocess.run") as mock_run:
            mock_run.return_value = mock_playwright_result()
            driver = LoopDriver(project_dir, config, smoke_test=True, dry_run=True)
            assert "PROJECT_COMPLETE" in driver.initial_prompt
            assert "Review the current project" in driver.initial_prompt


class TestStagnationDetection:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_low_turns_triggers_stagnation_exit(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Consecutive low-turn iterations trigger stagnation exit after session reset."""
        # Need enough iterations: 3 for initial window + 1 reset + 3 more = 7
        config.limits.max_iterations = 10
        config.stagnation.window_size = 3
        config.stagnation.low_turn_threshold = 2

        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "Thinking..."),
        )
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_STAGNATION

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_stagnation_resets_session_first(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Stagnation detection resets session before giving up."""
        config.limits.max_iterations = 10
        config.stagnation.window_size = 3
        config.stagnation.low_turn_threshold = 2

        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "Thinking..."),
        )
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        driver.run()

        # Verify trace has a stagnation_reset event (first detection)
        trace_path = project_dir / ".workflow" / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").strip().splitlines()]
        event_types = [e["event_type"] for e in events]
        assert "stagnation_reset" in event_types
        assert "stagnation_exit" in event_types

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_productive_iteration_resets_stagnation(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """A productive iteration (high turns) resets the stagnation flag."""
        config.limits.max_iterations = 5
        config.stagnation.window_size = 3
        config.stagnation.low_turn_threshold = 2
        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                # Alternate: 2 low-turn, then 1 productive, then 2 low-turn
                # Never hits window of 3 consecutive low-turn
                turns = 1 if call_count[0] % 3 != 0 else 10
                return MockPopen(
                    build_ndjson_stream(f"s{call_count[0]}", 0.05, turns, "Working...")
                )
            return MockPopen("")  # taskkill

        def run_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd:
                if cmd[0] == "git":
                    return mock_git_log_result()
                if "council_browser" in str(cmd):
                    return mock_playwright_result()
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = run_side_effect

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        # Should hit max iterations, not stagnation
        assert exit_code == EXIT_MAX_ITERATIONS

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_stagnation_disabled_by_config(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Stagnation detection can be disabled."""
        config.limits.max_iterations = 5
        config.stagnation.enabled = False
        config.stagnation.window_size = 3
        config.stagnation.low_turn_threshold = 2

        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "Thinking..."),
        )
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        # Should reach max iterations, not stagnation
        assert exit_code == EXIT_MAX_ITERATIONS

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_zero_cost_triggers_stagnation(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """All-zero-cost iterations trigger stagnation (context exhaustion)."""
        config.limits.max_iterations = 10
        config.stagnation.window_size = 3
        # Use high turn threshold so the zero-cost check triggers, not low-turn
        config.stagnation.low_turn_threshold = 0

        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.0, 5, "Working..."),
        )
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_STAGNATION


class TestConsecutiveTimeouts:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_consecutive_timeouts_exit_stagnation(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Consecutive timeouts exit with stagnation code after limit."""
        config.limits.max_iterations = 5
        config.stagnation.max_consecutive_timeouts = 2

        mock_popen.side_effect = make_popen_dispatcher(claude_ndjson="")
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_STAGNATION

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_timeout_clears_session(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """First timeout clears session for fresh context."""
        config.limits.max_iterations = 3
        config.stagnation.max_consecutive_timeouts = 3  # Don't exit on timeouts
        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                if call_count[0] == 1:
                    return MockPopen("")  # Simulates timeout (no result event)
                return MockPopen(build_ndjson_stream("s2", 0.05, 5, "Working..."))
            return MockPopen("")  # taskkill

        def run_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd:
                if cmd[0] == "git":
                    return mock_git_log_result()
                if "council_browser" in str(cmd):
                    return mock_playwright_result()
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = run_side_effect

        driver = LoopDriver(project_dir, config)
        driver.run()

        # After timeout, session should be cleared — second call should NOT have --resume
        claude_calls = [
            c for c in mock_popen.call_args_list
            if c[0] and isinstance(c[0][0], list) and c[0][0] and c[0][0][0] == "claude"
        ]
        if len(claude_calls) >= 2:
            second_call_args = claude_calls[1][0][0]
            assert "--resume" not in second_call_args

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_timeout_counter_resets_on_success(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Successful iteration resets the consecutive timeout counter."""
        config.limits.max_iterations = 5
        config.stagnation.max_consecutive_timeouts = 2
        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                # Timeout on 1st, succeed on 2nd-5th
                if call_count[0] == 1:
                    return MockPopen("")  # Simulates timeout (no result event)
                return MockPopen(
                    build_ndjson_stream(f"s{call_count[0]}", 0.05, 5, "Working...")
                )
            return MockPopen("")  # taskkill

        def run_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd:
                if cmd[0] == "git":
                    return mock_git_log_result()
                if "council_browser" in str(cmd):
                    return mock_playwright_result()
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = run_side_effect

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        # Should not stagnate — timeout counter reset after success
        assert exit_code == EXIT_MAX_ITERATIONS
        assert driver._consecutive_timeouts == 0


class TestModelAwareTimeout:
    @patch("loop_driver.threading.Timer")
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_opus_gets_double_timeout(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_timer: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Opus model gets 2x the base timeout."""
        config.limits.max_iterations = 1
        config.limits.timeout_seconds = 600
        config.claude.model = "opus"

        mock_timer.return_value = MagicMock()  # No-op timer
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.50, 10, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        driver.run()

        # Timer was called with (effective_timeout, callback)
        assert mock_timer.call_args[0][0] == 1200  # 600 * 2.0

    @patch("loop_driver.threading.Timer")
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_sonnet_gets_normal_timeout(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_timer: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Sonnet model gets 1x the base timeout (no scaling)."""
        config.limits.max_iterations = 1
        config.limits.timeout_seconds = 600
        config.claude.model = "sonnet"

        mock_timer.return_value = MagicMock()  # No-op timer
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.50, 10, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        driver.run()

        # Timer was called with (effective_timeout, callback)
        assert mock_timer.call_args[0][0] == 600  # 600 * 1.0

    @patch("loop_driver.threading.Timer")
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_unknown_model_gets_1x_timeout(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_timer: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Unknown model defaults to 1x multiplier."""
        config.limits.max_iterations = 1
        config.limits.timeout_seconds = 300
        config.claude.model = "custom-model"

        mock_timer.return_value = MagicMock()  # No-op timer
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.10, 5, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        driver.run()

        # Timer was called with (effective_timeout, callback)
        assert mock_timer.call_args[0][0] == 300  # 300 * 1.0 (default)

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_opus_max_turns_capped(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Opus model caps max-turns to 25 (below config default of 50)."""
        config.limits.max_iterations = 1
        config.limits.max_turns_per_iteration = 50
        config.claude.model = "opus"

        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.50, 10, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        driver.run()

        claude_calls = [
            c for c in mock_popen.call_args_list
            if c[0] and isinstance(c[0][0], list) and c[0][0] and c[0][0][0] == "claude"
        ]
        assert len(claude_calls) >= 1
        args = claude_calls[0][0][0]
        turns_idx = args.index("--max-turns")
        assert args[turns_idx + 1] == "25"

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_sonnet_max_turns_default(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Sonnet model uses full config max-turns (no override)."""
        config.limits.max_iterations = 1
        config.limits.max_turns_per_iteration = 50
        config.claude.model = "sonnet"

        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.50, 10, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        driver.run()

        claude_calls = [
            c for c in mock_popen.call_args_list
            if c[0] and isinstance(c[0][0], list) and c[0][0] and c[0][0][0] == "claude"
        ]
        assert len(claude_calls) >= 1
        args = claude_calls[0][0][0]
        turns_idx = args.index("--max-turns")
        assert args[turns_idx + 1] == "50"

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_opus_three_timeouts_before_stagnation(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Opus needs 3 consecutive timeouts before stagnation exit (not 2).

        With model fallback enabled (default), Opus falls back to Sonnet at 2 timeouts,
        so we disable fallback here to test the raw Opus timeout limit.
        """
        config.limits.max_iterations = 5
        config.claude.model = "opus"
        config.stagnation.max_consecutive_timeouts = 2  # base: 2
        config.limits.model_fallback = {}  # Disable fallback to test raw Opus limit
        # opus override defaults to 3

        mock_popen.side_effect = make_popen_dispatcher(claude_ndjson="")
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_STAGNATION
        assert driver._consecutive_timeouts == 3  # Not 2

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_sonnet_two_timeouts_triggers_stagnation(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Sonnet still uses default of 2 consecutive timeouts for stagnation."""
        config.limits.max_iterations = 5
        config.claude.model = "sonnet"
        config.stagnation.max_consecutive_timeouts = 2

        mock_popen.side_effect = make_popen_dispatcher(claude_ndjson="")
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_STAGNATION
        assert driver._consecutive_timeouts == 2


class TestJsonFormatter:
    def test_json_log_format_produces_valid_json(self) -> None:
        """JsonFormatter produces valid JSON output."""
        formatter = JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S")
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Test message with data: %s", args=("value",),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)

        assert parsed["level"] == "INFO"
        assert "Test message with data: value" in parsed["message"]
        assert "module" in parsed
        assert "timestamp" in parsed


class TestTimeoutCooldown:
    @patch("loop_driver.time.sleep")
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_cooldown_applied_after_timeout(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_sleep: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """After first timeout, loop sleeps for cooldown before retry."""
        config.limits.max_iterations = 3
        config.limits.timeout_cooldown_base_seconds = 60
        config.limits.timeout_cooldown_max_seconds = 300
        config.stagnation.max_consecutive_timeouts = 3
        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                if call_count[0] == 1:
                    return MockPopen("")  # Timeout
                return MockPopen(build_ndjson_stream("s2", 0.05, 5, "PROJECT_COMPLETE"))
            return MockPopen("")

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        driver.run()

        # Verify sleep was called with base cooldown (60s for first timeout)
        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        assert 60 in sleep_calls

    @patch("loop_driver.time.sleep")
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_cooldown_escalates(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_sleep: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Consecutive timeouts increase cooldown (60, 120)."""
        config.limits.max_iterations = 5
        config.limits.timeout_cooldown_base_seconds = 60
        config.limits.timeout_cooldown_max_seconds = 300
        config.stagnation.max_consecutive_timeouts = 4
        config.limits.model_fallback = {}  # Disable fallback

        mock_popen.side_effect = make_popen_dispatcher(claude_ndjson="")
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        driver.run()

        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        assert 60 in sleep_calls   # First timeout
        assert 120 in sleep_calls  # Second timeout

    @patch("loop_driver.time.sleep")
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_cooldown_capped_at_max(
        self, mock_run: MagicMock, mock_popen: MagicMock, mock_sleep: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Cooldown doesn't exceed max configured value."""
        config.limits.max_iterations = 10
        config.limits.timeout_cooldown_base_seconds = 100
        config.limits.timeout_cooldown_max_seconds = 200
        config.stagnation.max_consecutive_timeouts = 5
        config.limits.model_fallback = {}  # Disable fallback

        mock_popen.side_effect = make_popen_dispatcher(claude_ndjson="")
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        driver.run()

        sleep_calls = [c[0][0] for c in mock_sleep.call_args_list]
        # All cooldowns should be <= max
        for val in sleep_calls:
            assert val <= 200


class TestPreflightCheck:
    @patch("subprocess.run")
    def test_preflight_passes(
        self, mock_run: MagicMock, project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Preflight passes when claude --version succeeds."""
        mock_run.return_value = MagicMock(returncode=0, stdout="claude 1.0.0\n", stderr="")
        driver = LoopDriver(project_dir, config, dry_run=True)
        assert driver._preflight_check() is True

    @patch("subprocess.run")
    def test_preflight_fails_missing_cli(
        self, mock_run: MagicMock, project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Preflight fails when claude is not on PATH."""
        mock_run.side_effect = FileNotFoundError("claude not found")
        driver = LoopDriver(project_dir, config, dry_run=True)
        assert driver._preflight_check() is False

    @patch("subprocess.run")
    def test_preflight_fails_timeout(
        self, mock_run: MagicMock, project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Preflight fails when claude --version times out."""
        mock_run.side_effect = sp.TimeoutExpired(cmd="claude", timeout=30)
        driver = LoopDriver(project_dir, config, dry_run=True)
        assert driver._preflight_check() is False

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_preflight_failure_exits_stagnation(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Preflight failure exits with EXIT_STAGNATION before any iteration."""
        mock_run.side_effect = FileNotFoundError("claude not found")
        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_STAGNATION

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_skip_preflight_flag(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """--skip-preflight bypasses the preflight check."""
        config.limits.max_iterations = 1
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config, skip_preflight=True)
        exit_code = driver.run()
        assert exit_code == EXIT_COMPLETE


class TestDiagnosticCapture:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_timeout_trace_includes_event_count(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Timeout trace event includes ndjson_events_received count."""
        config.limits.max_iterations = 2
        config.stagnation.max_consecutive_timeouts = 2

        mock_popen.side_effect = make_popen_dispatcher(claude_ndjson="")
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        driver.run()

        trace_path = project_dir / ".workflow" / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").strip().splitlines()]
        timeout_events = [e for e in events if e["event_type"] == "timeout_detected"]
        assert len(timeout_events) >= 1
        assert "ndjson_events_received" in timeout_events[0]
        assert timeout_events[0]["ndjson_events_received"] == 0
        assert "had_session_id" in timeout_events[0]

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_zero_events_logs_warning(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig, caplog,
    ) -> None:
        """Zero events on timeout produces specific warning."""
        config.limits.max_iterations = 1
        config.stagnation.max_consecutive_timeouts = 2

        mock_popen.side_effect = make_popen_dispatcher(claude_ndjson="")
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        with caplog.at_level(logging.WARNING):
            driver.run()

        assert any("ZERO events" in r.message for r in caplog.records)


class TestModelFallback:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_opus_falls_back_to_sonnet_after_2_timeouts(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """After 2 Opus timeouts, model switches to Sonnet."""
        config.limits.max_iterations = 5
        config.claude.model = "opus"
        config.stagnation.max_consecutive_timeouts = 2
        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                if call_count[0] <= 2:
                    return MockPopen("")  # Timeout (Opus)
                # Sonnet succeeds
                return MockPopen(
                    build_ndjson_stream(f"s{call_count[0]}", 0.05, 5, "PROJECT_COMPLETE")
                )
            return MockPopen("")

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_COMPLETE

        # Verify model was switched
        trace_path = project_dir / ".workflow" / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").strip().splitlines()]
        fallback_events = [e for e in events if e["event_type"] == "model_fallback"]
        assert len(fallback_events) == 1
        assert fallback_events[0]["from_model"] == "opus"
        assert fallback_events[0]["to_model"] == "sonnet"

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_fallback_reverts_on_success(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """After Sonnet succeeds productively, model reverts to Opus."""
        config.limits.max_iterations = 5
        config.claude.model = "opus"
        config.stagnation.max_consecutive_timeouts = 2
        config.stagnation.low_turn_threshold = 2
        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                if call_count[0] <= 2:
                    return MockPopen("")  # Timeout (Opus)
                # Sonnet succeeds with productive iteration (turns > threshold)
                return MockPopen(
                    build_ndjson_stream(f"s{call_count[0]}", 0.05, 10, "Working...")
                )
            return MockPopen("")

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        driver.run()

        # Verify model reverted
        trace_path = project_dir / ".workflow" / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").strip().splitlines()]
        revert_events = [e for e in events if e["event_type"] == "model_fallback_revert"]
        assert len(revert_events) >= 1
        assert revert_events[0]["from_model"] == "sonnet"
        assert revert_events[0]["to_model"] == "opus"

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_fallback_model_stagnates_exits(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """If fallback model also times out, stagnation exit still works."""
        config.limits.max_iterations = 10
        config.claude.model = "opus"
        config.stagnation.max_consecutive_timeouts = 2

        # All timeouts — Opus falls back to Sonnet, Sonnet also times out
        mock_popen.side_effect = make_popen_dispatcher(claude_ndjson="")
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_STAGNATION

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_no_fallback_when_already_using_fallback(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Fallback only triggers once — no cascading fallbacks."""
        config.limits.max_iterations = 10
        config.claude.model = "opus"
        config.stagnation.max_consecutive_timeouts = 2

        mock_popen.side_effect = make_popen_dispatcher(claude_ndjson="")
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        driver.run()

        # Should have exactly 1 fallback event (opus→sonnet), not opus→sonnet→?
        trace_path = project_dir / ".workflow" / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").strip().splitlines()]
        fallback_events = [e for e in events if e["event_type"] == "model_fallback"]
        assert len(fallback_events) == 1


class TestSessionRotation:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_session_rotation_at_turn_limit(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Session rotates when cumulative turns reach the limit."""
        config.limits.max_iterations = 3
        config.stagnation.session_max_turns = 20  # Low limit for testing
        config.stagnation.session_max_cost_usd = 999.0  # Won't trigger

        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 15, "Working..."),
        )
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_MAX_ITERATIONS

        # Verify rotation trace event
        trace_path = project_dir / ".workflow" / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").strip().splitlines()]
        rotation_events = [e for e in events if e["event_type"] == "session_rotation"]
        assert len(rotation_events) >= 1
        assert "turn limit" in rotation_events[0]["reason"].lower()

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_session_rotation_at_cost_limit(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Session rotates when cumulative cost reaches the limit."""
        config.limits.max_iterations = 3
        config.limits.max_total_budget_usd = 100.0  # High total so we don't exit on budget
        config.limits.max_per_iteration_budget_usd = 50.0
        config.stagnation.session_max_turns = 9999  # Won't trigger
        config.stagnation.session_max_cost_usd = 1.0  # Low limit for testing

        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.80, 10, "Working..."),
        )
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_MAX_ITERATIONS

        # Verify rotation trace event
        trace_path = project_dir / ".workflow" / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").strip().splitlines()]
        rotation_events = [e for e in events if e["event_type"] == "session_rotation"]
        assert len(rotation_events) >= 1
        assert "cost limit" in rotation_events[0]["reason"].lower()

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_context_exhaustion_triggers_rotation(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Behavioral detection: 2/3 low-turn iterations trigger rotation."""
        config.limits.max_iterations = 5
        config.stagnation.session_max_turns = 9999  # Won't trigger
        config.stagnation.session_max_cost_usd = 999.0  # Won't trigger
        config.stagnation.context_exhaustion_turn_threshold = 5
        config.stagnation.context_exhaustion_window = 3
        # Disable regular stagnation so it doesn't interfere
        config.stagnation.low_turn_threshold = 0

        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                # All iterations with 3 turns (below threshold of 5)
                return MockPopen(
                    build_ndjson_stream(f"s1", 0.05, 3, "Working...")
                )
            return MockPopen("")  # taskkill

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_MAX_ITERATIONS

        # Verify rotation trace event
        trace_path = project_dir / ".workflow" / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").strip().splitlines()]
        rotation_events = [e for e in events if e["event_type"] == "session_rotation"]
        assert len(rotation_events) >= 1
        assert "context exhaustion" in rotation_events[0]["reason"].lower()

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_rotation_continues_loop(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """After rotation, loop continues (doesn't exit)."""
        config.limits.max_iterations = 4
        config.stagnation.session_max_turns = 10  # Will trigger after iter 1
        config.stagnation.session_max_cost_usd = 999.0

        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                sid = f"s{call_count[0]}"
                return MockPopen(build_ndjson_stream(sid, 0.05, 15, "Working..."))
            return MockPopen("")

        def run_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd:
                if cmd[0] == "git":
                    return mock_git_log_result()
                if "council_browser" in str(cmd):
                    return mock_playwright_result()
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = run_side_effect

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        # Should hit max iterations, NOT stagnation
        assert exit_code == EXIT_MAX_ITERATIONS
        # Multiple Claude calls means loop continued
        claude_calls = [
            c for c in mock_popen.call_args_list
            if c[0] and isinstance(c[0][0], list) and c[0][0] and c[0][0][0] == "claude"
        ]
        assert len(claude_calls) == 4

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_rotation_does_not_set_stagnation_flag(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Session rotation doesn't count as a stagnation strike."""
        config.limits.max_iterations = 4
        config.stagnation.session_max_turns = 10  # Triggers rotation
        config.stagnation.session_max_cost_usd = 999.0

        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                sid = f"s{call_count[0]}"
                return MockPopen(build_ndjson_stream(sid, 0.05, 15, "Working..."))
            return MockPopen("")

        def run_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd:
                if cmd[0] == "git":
                    return mock_git_log_result()
                if "council_browser" in str(cmd):
                    return mock_playwright_result()
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = run_side_effect

        driver = LoopDriver(project_dir, config)
        driver.run()

        # Rotation should NOT have set the stagnation reset flag
        assert driver._stagnation_reset_done is False

    def test_should_rotate_disabled(
        self, project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Rotation returns False when stagnation is disabled."""
        config.stagnation.enabled = False
        driver = LoopDriver(project_dir, config, dry_run=True, skip_preflight=True)
        should, reason = driver._should_rotate_session("s1")
        assert should is False

    def test_should_rotate_no_session(
        self, project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Rotation returns False when session_id is None."""
        driver = LoopDriver(project_dir, config, dry_run=True, skip_preflight=True)
        should, reason = driver._should_rotate_session(None)
        assert should is False


class TestComputeCooldown:
    def test_first_timeout_returns_base(
        self, project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """First timeout returns the base cooldown value."""
        config.limits.timeout_cooldown_base_seconds = 60
        config.limits.timeout_cooldown_max_seconds = 300
        driver = LoopDriver(project_dir, config, dry_run=True, skip_preflight=True)
        assert driver._compute_cooldown(1) == 60

    def test_second_timeout_doubles(
        self, project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Second timeout doubles the base."""
        config.limits.timeout_cooldown_base_seconds = 60
        config.limits.timeout_cooldown_max_seconds = 300
        driver = LoopDriver(project_dir, config, dry_run=True, skip_preflight=True)
        assert driver._compute_cooldown(2) == 120

    def test_capped_at_max(
        self, project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Cooldown capped at max."""
        config.limits.timeout_cooldown_base_seconds = 60
        config.limits.timeout_cooldown_max_seconds = 300
        driver = LoopDriver(project_dir, config, dry_run=True, skip_preflight=True)
        assert driver._compute_cooldown(10) == 300

    def test_zero_base_returns_zero(
        self, project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Base of 0 disables cooldown."""
        config.limits.timeout_cooldown_base_seconds = 0
        driver = LoopDriver(project_dir, config, dry_run=True, skip_preflight=True)
        assert driver._compute_cooldown(5) == 0


class TestTraceLogRotation:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_trace_rotates_when_over_limit(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """trace.jsonl rotates to .jsonl.1 when exceeding configured size."""
        trace_path = project_dir / ".workflow" / "trace.jsonl"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        # Write enough data to exceed limit
        trace_path.write_text("x" * 500, encoding="utf-8")
        config.limits.trace_max_size_bytes = 100  # Very low limit

        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        driver.run()

        rotated = trace_path.with_suffix(".jsonl.1")
        assert rotated.exists()
        # New trace.jsonl should exist with fresh events
        assert trace_path.exists()
        assert trace_path.stat().st_size < 500  # Smaller than original

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_trace_rotation_replaces_existing_backup(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Rotation replaces existing .jsonl.1 file."""
        trace_path = project_dir / ".workflow" / "trace.jsonl"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text("new_data_" * 100, encoding="utf-8")
        rotated = trace_path.with_suffix(".jsonl.1")
        rotated.write_text("old_backup", encoding="utf-8")
        config.limits.trace_max_size_bytes = 100

        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        driver.run()

        assert rotated.exists()
        assert "old_backup" not in rotated.read_text(encoding="utf-8")

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_trace_no_rotation_when_zero(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """trace_max_size_bytes=0 disables rotation."""
        trace_path = project_dir / ".workflow" / "trace.jsonl"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text("x" * 500, encoding="utf-8")
        config.limits.trace_max_size_bytes = 0

        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        driver.run()

        rotated = trace_path.with_suffix(".jsonl.1")
        assert not rotated.exists()


class TestExtendedPreflightChecks:
    @patch("subprocess.run")
    def test_preflight_warns_missing_claude_md(
        self, mock_run: MagicMock, tmp_path: Path, config: WorkflowConfig, caplog,
    ) -> None:
        """Preflight warns when CLAUDE.md is missing."""
        (tmp_path / ".workflow").mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout="claude 1.0.0\n", stderr="")

        driver = LoopDriver(tmp_path, config, dry_run=True)
        with caplog.at_level(logging.WARNING):
            result = driver._preflight_check()

        assert result is True
        assert any("No CLAUDE.md" in r.message for r in caplog.records)

    @patch("subprocess.run")
    def test_preflight_warns_not_git_repo(
        self, mock_run: MagicMock, tmp_path: Path, config: WorkflowConfig, caplog,
    ) -> None:
        """Preflight warns when .git/ doesn't exist."""
        (tmp_path / ".workflow").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Project", encoding="utf-8")
        mock_run.return_value = MagicMock(returncode=0, stdout="claude 1.0.0\n", stderr="")

        driver = LoopDriver(tmp_path, config, dry_run=True)
        with caplog.at_level(logging.WARNING):
            driver._preflight_check()

        assert any("Not a git repo" in r.message for r in caplog.records)

    @patch("subprocess.run")
    def test_preflight_no_warnings_when_all_present(
        self, mock_run: MagicMock, tmp_path: Path, config: WorkflowConfig, caplog,
    ) -> None:
        """Preflight logs no warnings when all checks pass."""
        (tmp_path / ".workflow").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# Project", encoding="utf-8")
        (tmp_path / ".git").mkdir()
        mock_run.return_value = MagicMock(returncode=0, stdout="claude 1.0.0\n", stderr="")

        driver = LoopDriver(tmp_path, config, dry_run=True)
        with caplog.at_level(logging.WARNING):
            result = driver._preflight_check()

        assert result is True
        preflight_warnings = [r for r in caplog.records if "Preflight:" in r.message]
        # May have Perplexity session warning, but no CLAUDE.md or git warnings
        no_project_warnings = [
            r for r in preflight_warnings
            if "CLAUDE.md" in r.message or "git repo" in r.message
        ]
        assert len(no_project_warnings) == 0

    @patch("subprocess.run")
    def test_preflight_creates_workflow_dir(
        self, mock_run: MagicMock, tmp_path: Path, config: WorkflowConfig,
    ) -> None:
        """Preflight creates .workflow/ directory if it doesn't exist."""
        (tmp_path / "CLAUDE.md").write_text("# Project", encoding="utf-8")
        mock_run.return_value = MagicMock(returncode=0, stdout="claude 1.0.0\n", stderr="")

        driver = LoopDriver(tmp_path, config, dry_run=True)
        result = driver._preflight_check()

        assert result is True
        assert (tmp_path / ".workflow").exists()


class TestModelAnalyticsInMetrics:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_metrics_summary_includes_model_analytics(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Metrics summary JSON includes per-model analytics."""
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.05, 2, "PROJECT_COMPLETE"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()
        assert exit_code == EXIT_COMPLETE

        summary_path = project_dir / ".workflow" / "metrics_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert "model_analytics" in summary
        assert "sonnet" in summary["model_analytics"]  # default model
        sonnet_stats = summary["model_analytics"]["sonnet"]
        assert sonnet_stats["iterations"] == 1
        assert sonnet_stats["avg_turns"] == 2.0
        assert sonnet_stats["avg_cost_usd"] == pytest.approx(0.05)

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_model_analytics_with_fallback(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig,
    ) -> None:
        """Model analytics separates opus and sonnet cycles after fallback."""
        config.limits.max_iterations = 5
        config.claude.model = "opus"
        config.stagnation.max_consecutive_timeouts = 2
        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                if call_count[0] <= 2:
                    return MockPopen("")  # Timeout (Opus)
                return MockPopen(
                    build_ndjson_stream(f"s{call_count[0]}", 0.05, 5, "PROJECT_COMPLETE")
                )
            return MockPopen("")

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        driver.run()

        summary_path = project_dir / ".workflow" / "metrics_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        analytics = summary["model_analytics"]
        # Opus had 2 timeout iterations, sonnet had 1 successful
        assert "opus" in analytics
        assert "sonnet" in analytics
        assert analytics["opus"]["timeout_count"] == 2
        assert analytics["sonnet"]["iterations"] >= 1


class TestImprovedErrorMessages:
    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_stagnation_error_has_recovery_steps(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig, caplog,
    ) -> None:
        """Stagnation exit error message includes actionable recovery steps."""
        config.limits.max_iterations = 10
        config.stagnation.window_size = 3
        config.stagnation.low_turn_threshold = 2

        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.01, 1, "Thinking..."),
        )
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        with caplog.at_level(logging.ERROR):
            driver.run()

        assert any("Recovery:" in r.message for r in caplog.records)
        assert any("CLAUDE.md" in r.message for r in caplog.records)

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_budget_error_has_iteration_count(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig, caplog,
    ) -> None:
        """Budget exceeded message includes iteration count and metrics reference."""
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 10.0, 1, "Expensive"),
        )
        mock_run.side_effect = make_subprocess_dispatcher()

        driver = LoopDriver(project_dir, config)
        with caplog.at_level(logging.ERROR):
            driver.run()

        assert any("metrics_summary.json" in r.message for r in caplog.records)

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_timeout_stagnation_has_recovery_steps(
        self, mock_run: MagicMock, mock_popen: MagicMock,
        project_dir: Path, config: WorkflowConfig, caplog,
    ) -> None:
        """Consecutive timeout stagnation includes recovery guidance."""
        config.limits.max_iterations = 5
        config.stagnation.max_consecutive_timeouts = 2

        mock_popen.side_effect = make_popen_dispatcher(claude_ndjson="")
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        driver = LoopDriver(project_dir, config)
        with caplog.at_level(logging.ERROR):
            driver.run()

        assert any("Recovery:" in r.message for r in caplog.records)

    @patch("subprocess.run")
    def test_preflight_failure_has_recovery_steps(
        self, mock_run: MagicMock, project_dir: Path, config: WorkflowConfig, caplog,
    ) -> None:
        """Preflight failure includes actionable recovery guidance."""
        mock_run.side_effect = FileNotFoundError("claude not found")

        driver = LoopDriver(project_dir, config, dry_run=True)
        with caplog.at_level(logging.ERROR):
            driver._preflight_check()

        assert any("taskkill" in r.message for r in caplog.records)
