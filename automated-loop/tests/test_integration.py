"""Integration tests exercising the full pipeline."""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from config import RetryConfig, WorkflowConfig, load_config
from log_redactor import RedactingFilter, redact_string
from loop_driver import EXIT_BUDGET_EXCEEDED, EXIT_COMPLETE, EXIT_MAX_ITERATIONS, LoopDriver
from ndjson_parser import parse_ndjson_string, process_events
from research_bridge import ResearchBridge
from state_tracker import CURRENT_STATE_VERSION, StateTracker

from helpers import (
    build_ndjson_stream,
    make_popen_dispatcher,
    make_subprocess_dispatcher,
    mock_git_log_result,
    mock_playwright_result,
    make_research_dispatcher,
    MockPopen,
)


class TestConfigToStateToCompletion:
    """Full lifecycle: load config -> track state -> complete."""

    def test_full_lifecycle(self, project_dir: Path) -> None:
        result = load_config(project_dir / ".workflow" / "config.json")
        assert result.success
        config = result.data

        tracker = StateTracker(project_dir)
        tracker.start_session()

        for i in range(3):
            tracker.increment_iteration()
            tracker.add_cycle(
                prompt=f"step {i}", session_id=f"sess-{i}",
                cost_usd=0.05, num_turns=2,
            )

        tracker.complete()
        tracker.save()

        # Reload and verify
        tracker2 = StateTracker(project_dir)
        tracker2.load()
        assert tracker2.state.status == "completed"
        assert tracker2.state.iteration == 3
        assert tracker2.get_metrics().total_cost_usd == pytest.approx(0.15)


class TestNdjsonFeedsStateTracker:
    """Parser output feeds into state tracker."""

    def test_parser_to_state(self, project_dir: Path) -> None:
        ndjson = build_ndjson_stream("sess-abc", cost=0.042, turns=3, result_text="Done.")
        events = parse_ndjson_string(ndjson)
        parsed = process_events(events)

        tracker = StateTracker(project_dir)
        tracker.start_session()
        tracker.increment_iteration()
        tracker.add_cycle(
            prompt="implement feature",
            session_id=parsed.session_id,
            cost_usd=parsed.result.cost_usd,
            duration_ms=int(parsed.result.duration_ms),
            num_turns=parsed.result.num_turns,
            is_error=parsed.result.is_error,
        )
        tracker.save()

        tracker2 = StateTracker(project_dir)
        tracker2.load()
        assert tracker2.state.last_session_id == "sess-abc"
        assert tracker2.get_metrics().total_cost_usd == pytest.approx(0.042)


class TestResearchBridgeWithPopulatedState:
    """Context gathering from real state."""

    def test_context_includes_state(self, project_dir: Path) -> None:
        # Populate state
        tracker = StateTracker(project_dir)
        tracker.start_session()
        tracker.increment_iteration()
        tracker.add_cycle(prompt="build API", session_id="s1", cost_usd=0.1)
        tracker.save()

        bridge = ResearchBridge(project_dir)
        query = bridge.build_query()

        assert "Test Project" in query
        assert "Workflow State" in query


class TestBudgetEnforcementHaltsPipeline:
    """Cost check stops the loop."""

    def test_budget_exceeded_halts(self, project_dir: Path) -> None:
        config_result = load_config(project_dir / ".workflow" / "config.json")
        config = config_result.data

        tracker = StateTracker(project_dir)
        tracker.start_session()

        # Simulate iterations that exceed total budget (5.0)
        for i in range(3):
            tracker.increment_iteration()
            tracker.add_cycle(prompt=f"step {i}", cost_usd=2.0)

        budget_check = tracker.check_budget(
            per_iteration_limit=config.limits.max_per_iteration_budget_usd,
            total_limit=config.limits.max_total_budget_usd,
        )
        assert not budget_check.success
        assert budget_check.error_code == "BUDGET_EXCEEDED_TOTAL"


class TestCompletionMarkerDetection:
    """NDJSON result text -> completion marker check."""

    def test_completion_detected(self, project_dir: Path) -> None:
        ndjson = build_ndjson_stream(
            "sess-done", cost=0.01, turns=1,
            result_text="All tasks finished. PROJECT_COMPLETE."
        )
        events = parse_ndjson_string(ndjson)
        parsed = process_events(events)

        config_result = load_config(project_dir / ".workflow" / "config.json")
        markers = config_result.data.patterns.completion_markers

        found = any(
            marker in (parsed.result.result_text + " " + parsed.assistant_text)
            for marker in markers
        )
        assert found


class TestErrorCycleToResearchRecovery:
    """Error state appears in research context."""

    def test_error_state_in_context(self, project_dir: Path) -> None:
        tracker = StateTracker(project_dir)
        tracker.start_session()
        tracker.increment_iteration()
        tracker.add_cycle(
            prompt="broken step", is_error=True,
            error_message="timeout exceeded",
        )
        tracker.save()

        bridge = ResearchBridge(project_dir)
        query = bridge.build_query(extra_context="Previous iteration failed with timeout.")

        assert "timeout" in query.lower()


class TestCircuitBreakerInPipeline:
    """Repeated failures trip circuit breaker."""

    @patch("research_bridge.subprocess.run")
    def test_circuit_breaker_trips(
        self, mock_run: MagicMock, project_dir: Path
    ) -> None:
        import subprocess as sp

        mock_run.side_effect = sp.TimeoutExpired(cmd="python", timeout=600)

        config = RetryConfig(
            max_retries=2, base_delay_seconds=0.001, max_delay_seconds=0.01,
            circuit_breaker_threshold=3, circuit_breaker_reset_seconds=60.0,
        )
        bridge = ResearchBridge(
            project_dir, retry_config=config
        )
        bridge.query()  # 3 failures (1 + 2 retries)

        # Next call should be blocked
        result = bridge.query()
        assert result.error_code == "CIRCUIT_OPEN"


class TestLogRedactionInPipeline:
    """API keys scrubbed from logs."""

    def test_keys_redacted(self) -> None:
        from config import SecurityConfig

        sec = SecurityConfig()
        log_line = "Connecting with key sk-ant-api03-z7ekh and pplx-jhZTkQ"
        redacted = redact_string(log_line, sec.log_redact_patterns)

        assert "sk-ant-" not in redacted
        assert "pplx-" not in redacted
        assert redacted.count("[REDACTED]") == 2


class TestStateVersionMigration:
    """Old state files get version field added."""

    def test_old_file_upgraded(self, project_dir: Path) -> None:
        state_file = project_dir / ".workflow" / "state.json"
        old_state = {
            "session_id": "legacy",
            "iteration": 5,
            "status": "paused",
            "cycles": [],
            "metrics": {
                "total_cost_usd": 0.5,
                "total_duration_ms": 60000,
                "total_turns": 15,
                "error_count": 1,
                "files_modified": [],
            },
        }
        state_file.write_text(json.dumps(old_state), encoding="utf-8")

        tracker = StateTracker(project_dir)
        result = tracker.load()

        assert result.success
        assert tracker.state.version == CURRENT_STATE_VERSION
        assert tracker.state.iteration == 5


class TestFullCycleRoundtrip:
    """3-iteration mock loop end-to-end."""

    @patch("research_bridge.subprocess.run")
    def test_three_iteration_loop(
        self, mock_research_run: MagicMock, project_dir: Path
    ) -> None:
        mock_research_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "synthesis": "Next: implement feature X",
                "models": ["perplexity-research"],
                "citations": [],
                "execution_time_ms": 30000,
            }),
            stderr="",
        )

        config_result = load_config(project_dir / ".workflow" / "config.json")
        config = config_result.data

        tracker = StateTracker(project_dir)
        tracker.start_session()

        bridge = ResearchBridge(
            project_dir,
            retry_config=RetryConfig(max_retries=0),
        )

        ndjson_streams = [
            build_ndjson_stream("s1", 0.03, 2, "Implemented module A."),
            build_ndjson_stream("s2", 0.05, 4, "Added tests for module A."),
            build_ndjson_stream("s3", 0.02, 1, "All done. PROJECT_COMPLETE"),
        ]

        completed = False
        for i, ndjson in enumerate(ndjson_streams):
            tracker.increment_iteration()

            events = parse_ndjson_string(ndjson)
            parsed = process_events(events)

            tracker.add_cycle(
                prompt=f"iteration {i+1}",
                session_id=parsed.session_id,
                cost_usd=parsed.result.cost_usd,
                num_turns=parsed.result.num_turns,
            )

            budget_check = tracker.check_budget(
                per_iteration_limit=config.limits.max_per_iteration_budget_usd,
                total_limit=config.limits.max_total_budget_usd,
            )
            assert budget_check.success

            output = parsed.result.result_text + " " + parsed.assistant_text
            if any(m in output for m in config.patterns.completion_markers):
                tracker.complete()
                completed = True
                break

            # Query research for next steps
            research_result = bridge.query()
            assert research_result.success

        tracker.save()

        assert completed
        assert tracker.state.status == "completed"
        assert tracker.state.iteration == 3
        assert tracker.get_metrics().total_cost_usd == pytest.approx(0.10)
        assert tracker.state.last_session_id == "s3"


class TestLoopDriverEndToEnd:
    """Full LoopDriver-level integration tests exercising the real run() method."""

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_full_loop_with_resume_and_completion(
        self, mock_run: MagicMock, mock_popen: MagicMock, project_dir: Path
    ) -> None:
        """Full pipeline: init -> resume -> completion detection."""
        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                if call_count[0] == 1:
                    return MockPopen(
                        build_ndjson_stream("s1", 0.02, 2, "Working on feature...")
                    )
                else:
                    return MockPopen(
                        build_ndjson_stream("s2", 0.03, 3, "All done. PROJECT_COMPLETE")
                    )
            return MockPopen("", 0)

        def run_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd:
                if cmd[0] == "git":
                    return mock_git_log_result()
                if "council_browser" in str(cmd):
                    return mock_playwright_result("Continue with next step")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_popen.side_effect = popen_side_effect
        mock_run.side_effect = run_side_effect

        config = WorkflowConfig(
            limits={"max_iterations": 5, "max_total_budget_usd": 10.0},
            patterns={"completion_markers": ["PROJECT_COMPLETE"]},
            retry={"max_retries": 0, "base_delay_seconds": 0.001},
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()

        assert exit_code == EXIT_COMPLETE
        assert driver.tracker.state.status == "completed"
        assert driver.tracker.state.iteration == 2
        assert driver.tracker.state.last_session_id == "s2"

        # Verify second Claude call includes --resume s1
        claude_calls = [
            c for c in mock_popen.call_args_list
            if c[0] and isinstance(c[0][0], list) and c[0][0] and c[0][0][0] == "claude"
        ]
        assert len(claude_calls) == 2
        second_args = claude_calls[1][0][0]
        assert "--resume" in second_args
        assert second_args[second_args.index("--resume") + 1] == "s1"

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_error_recovery_then_completion(
        self, mock_run: MagicMock, mock_popen: MagicMock, project_dir: Path
    ) -> None:
        """Error in iteration 1, completion in iteration 2."""
        call_count = [0]

        def popen_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if isinstance(cmd, list) and cmd and cmd[0] == "claude":
                call_count[0] += 1
                if call_count[0] == 1:
                    return MockPopen(
                        build_ndjson_stream(
                            "err-1", 0.01, 1, "Error: something broke", is_error=True
                        )
                    )
                else:
                    return MockPopen(
                        build_ndjson_stream("s2", 0.02, 2, "PROJECT_COMPLETE")
                    )
            return MockPopen("", 0)

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

        config = WorkflowConfig(
            limits={"max_iterations": 5, "max_total_budget_usd": 10.0},
            patterns={"completion_markers": ["PROJECT_COMPLETE"]},
            retry={"max_retries": 0, "base_delay_seconds": 0.001},
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()

        assert exit_code == EXIT_COMPLETE
        assert driver.tracker.get_metrics().error_count == 1

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_budget_halt_mid_loop(
        self, mock_run: MagicMock, mock_popen: MagicMock, project_dir: Path
    ) -> None:
        """Budget exceeded in first iteration halts the loop."""
        mock_popen.side_effect = make_popen_dispatcher(
            claude_ndjson=build_ndjson_stream("s1", 0.12, 1, "Expensive work..."),
        )
        mock_run.side_effect = make_subprocess_dispatcher(
            research_result=mock_playwright_result(),
        )

        config = WorkflowConfig(
            limits={
                "max_iterations": 5,
                "max_per_iteration_budget_usd": 0.10,
                "max_total_budget_usd": 0.10,
            },
            retry={"max_retries": 0, "base_delay_seconds": 0.001},
        )

        driver = LoopDriver(project_dir, config)
        exit_code = driver.run()

        assert exit_code == EXIT_BUDGET_EXCEEDED
        assert driver.tracker.state.status == "failed"
