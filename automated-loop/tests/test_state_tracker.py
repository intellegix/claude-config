"""Tests for state_tracker module."""

import json
from pathlib import Path

import pytest

from state_tracker import CURRENT_STATE_VERSION, ModelAnalytics, StateTracker, WorkflowState


# Uses project_dir fixture from conftest.py


class TestStateTracker:
    def test_fresh_state_has_defaults(self, project_dir: Path) -> None:
        """New tracker starts with sensible defaults."""
        tracker = StateTracker(project_dir)
        assert tracker.state.iteration == 0
        assert tracker.state.status == "idle"
        assert tracker.state.cycles == []
        assert tracker.state.session_id  # UUID generated

    def test_save_creates_file(self, project_dir: Path) -> None:
        """save() persists state to .workflow/state.json."""
        tracker = StateTracker(project_dir)
        result = tracker.save()

        assert result.success
        state_file = project_dir / ".workflow" / "state.json"
        assert state_file.exists()

        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["iteration"] == 0
        assert data["status"] == "idle"

    def test_load_existing_state(self, project_dir: Path) -> None:
        """load() restores state from disk."""
        # Save initial state
        tracker = StateTracker(project_dir)
        tracker.state.iteration = 5
        tracker.state.status = "running"
        tracker.save()

        # Load in new tracker
        tracker2 = StateTracker(project_dir)
        result = tracker2.load()

        assert result.success
        assert tracker2.state.iteration == 5
        assert tracker2.state.status == "running"

    def test_load_missing_file_returns_defaults(self, project_dir: Path) -> None:
        """load() returns defaults when state.json doesn't exist."""
        tracker = StateTracker(project_dir)
        result = tracker.load()

        assert result.success
        assert tracker.state.iteration == 0

    def test_load_corrupt_file_returns_error(self, project_dir: Path) -> None:
        """load() returns error for corrupt JSON."""
        state_file = project_dir / ".workflow" / "state.json"
        state_file.write_text("not json {{{", encoding="utf-8")

        tracker = StateTracker(project_dir)
        result = tracker.load()

        assert not result.success
        assert result.error_code == "JSON_ERROR"

    def test_increment_iteration(self, project_dir: Path) -> None:
        """increment_iteration() advances the counter."""
        tracker = StateTracker(project_dir)
        assert tracker.increment_iteration() == 1
        assert tracker.increment_iteration() == 2
        assert tracker.state.iteration == 2

    def test_add_cycle(self, project_dir: Path) -> None:
        """add_cycle() records a cycle and updates metrics."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(
            prompt="implement feature X",
            session_id="abc-123",
            cost_usd=0.05,
            duration_ms=30000,
            num_turns=5,
        )

        assert len(tracker.state.cycles) == 1
        cycle = tracker.state.cycles[0]
        assert cycle.iteration == 1
        assert cycle.session_id == "abc-123"
        assert cycle.cost_usd == 0.05
        assert cycle.completed_at is not None

        metrics = tracker.get_metrics()
        assert metrics.total_cost_usd == 0.05
        assert metrics.total_turns == 5

    def test_add_error_cycle(self, project_dir: Path) -> None:
        """Error cycles increment error count in metrics."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(
            prompt="broken",
            is_error=True,
            error_message="timeout",
        )

        assert tracker.state.cycles[0].is_error is True
        assert tracker.get_metrics().error_count == 1

    def test_multiple_cycles_accumulate_metrics(self, project_dir: Path) -> None:
        """Metrics accumulate across multiple cycles."""
        tracker = StateTracker(project_dir)

        for i in range(3):
            tracker.increment_iteration()
            tracker.add_cycle(
                prompt=f"step {i}",
                cost_usd=0.10,
                duration_ms=10000,
                num_turns=3,
            )

        metrics = tracker.get_metrics()
        assert metrics.total_cost_usd == pytest.approx(0.30)
        assert metrics.total_duration_ms == 30000
        assert metrics.total_turns == 9

    def test_start_session(self, project_dir: Path) -> None:
        """start_session() sets status and start_time."""
        tracker = StateTracker(project_dir)
        tracker.start_session()

        assert tracker.state.status == "running"
        assert tracker.state.start_time is not None

    def test_complete(self, project_dir: Path) -> None:
        """complete() sets status and end_time."""
        tracker = StateTracker(project_dir)
        tracker.start_session()
        tracker.complete()

        assert tracker.state.status == "completed"
        assert tracker.state.end_time is not None

    def test_fail(self, project_dir: Path) -> None:
        """fail() sets status and end_time."""
        tracker = StateTracker(project_dir)
        tracker.start_session()
        tracker.fail("timeout exceeded")

        assert tracker.state.status == "failed"
        assert tracker.state.end_time is not None

    def test_last_session_id_tracked(self, project_dir: Path) -> None:
        """add_cycle with session_id updates last_session_id for --resume."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="step 1", session_id="sess-001")
        assert tracker.state.last_session_id == "sess-001"

        tracker.increment_iteration()
        tracker.add_cycle(prompt="step 2", session_id="sess-002")
        assert tracker.state.last_session_id == "sess-002"

    def test_roundtrip_save_load(self, project_dir: Path) -> None:
        """Full roundtrip: create state, save, load, verify."""
        tracker = StateTracker(project_dir)
        tracker.start_session()
        tracker.increment_iteration()
        tracker.add_cycle(prompt="test", session_id="s1", cost_usd=0.01, num_turns=2)
        tracker.save()

        tracker2 = StateTracker(project_dir)
        tracker2.load()

        assert tracker2.state.iteration == 1
        assert tracker2.state.status == "running"
        assert len(tracker2.state.cycles) == 1
        assert tracker2.state.last_session_id == "s1"
        assert tracker2.get_metrics().total_cost_usd == pytest.approx(0.01)


class TestBudgetEnforcement:
    def test_within_budget_passes(self, project_dir: Path) -> None:
        """check_budget passes when costs are within limits."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="test", cost_usd=1.0)

        result = tracker.check_budget(per_iteration_limit=5.0, total_limit=50.0)
        assert result.success

    def test_per_iteration_exceeded(self, project_dir: Path) -> None:
        """check_budget fails when last cycle exceeds per-iteration limit."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="expensive", cost_usd=10.0)

        result = tracker.check_budget(per_iteration_limit=5.0, total_limit=50.0)
        assert not result.success
        assert result.error_code == "BUDGET_EXCEEDED_ITERATION"

    def test_total_exceeded(self, project_dir: Path) -> None:
        """check_budget fails when total cost exceeds total limit."""
        tracker = StateTracker(project_dir)
        for i in range(6):
            tracker.increment_iteration()
            tracker.add_cycle(prompt=f"step {i}", cost_usd=10.0)

        result = tracker.check_budget(per_iteration_limit=15.0, total_limit=50.0)
        assert not result.success
        assert result.error_code == "BUDGET_EXCEEDED_TOTAL"

    def test_zero_cost_passes(self, project_dir: Path) -> None:
        """check_budget passes when cost is zero (e.g., dry run)."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="dry run", cost_usd=0.0)

        result = tracker.check_budget(per_iteration_limit=5.0, total_limit=50.0)
        assert result.success


class TestStateVersion:
    def test_old_state_without_version_loads_as_v1(self, project_dir: Path) -> None:
        """State files without a version field get migrated to version=1."""
        state_file = project_dir / ".workflow" / "state.json"
        old_state = {
            "session_id": "old-session",
            "iteration": 3,
            "status": "running",
            "cycles": [],
            "metrics": {"total_cost_usd": 0.0, "total_duration_ms": 0, "total_turns": 0, "error_count": 0, "files_modified": []},
        }
        state_file.write_text(json.dumps(old_state), encoding="utf-8")

        tracker = StateTracker(project_dir)
        result = tracker.load()

        assert result.success
        assert tracker.state.version == 1
        assert tracker.state.iteration == 3

    def test_version_persists_on_save(self, project_dir: Path) -> None:
        """Version field is written to disk on save."""
        tracker = StateTracker(project_dir)
        tracker.save()

        state_file = project_dir / ".workflow" / "state.json"
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["version"] == CURRENT_STATE_VERSION


class TestSessionValidation:
    def test_validate_session_id_valid(self, project_dir: Path) -> None:
        """Normal UUID string returns itself."""
        tracker = StateTracker(project_dir)
        result = tracker.validate_session_id("abc-123-def-456")
        assert result == "abc-123-def-456"

    def test_validate_session_id_none(self, project_dir: Path) -> None:
        """None returns None."""
        tracker = StateTracker(project_dir)
        assert tracker.validate_session_id(None) is None

    def test_validate_session_id_empty(self, project_dir: Path) -> None:
        """Empty string returns None."""
        tracker = StateTracker(project_dir)
        assert tracker.validate_session_id("") is None

    def test_validate_session_id_whitespace(self, project_dir: Path) -> None:
        """Whitespace-only string returns None."""
        tracker = StateTracker(project_dir)
        assert tracker.validate_session_id("   ") is None

    def test_validate_session_id_too_long(self, project_dir: Path) -> None:
        """201-char string returns None."""
        tracker = StateTracker(project_dir)
        assert tracker.validate_session_id("x" * 201) is None

    def test_clear_session(self, project_dir: Path) -> None:
        """clear_session() resets last_session_id to None."""
        tracker = StateTracker(project_dir)
        tracker.state.last_session_id = "some-session-id"
        tracker.clear_session()
        assert tracker.state.last_session_id is None


class TestSessionTracking:
    def test_get_session_turns_no_cycles(self, project_dir: Path) -> None:
        """Returns 0 when no cycles exist."""
        tracker = StateTracker(project_dir)
        assert tracker.get_session_turns("any-session") == 0

    def test_get_session_turns_no_session_id(self, project_dir: Path) -> None:
        """Returns 0 when no session_id provided and no last_session_id."""
        tracker = StateTracker(project_dir)
        assert tracker.get_session_turns() == 0

    def test_get_session_turns_single_session(self, project_dir: Path) -> None:
        """Correctly sums turns for a single session."""
        tracker = StateTracker(project_dir)
        for i in range(3):
            tracker.increment_iteration()
            tracker.add_cycle(prompt=f"step {i}", session_id="sess-1", num_turns=10)
        assert tracker.get_session_turns("sess-1") == 30

    def test_get_session_turns_filters_by_session(self, project_dir: Path) -> None:
        """Only counts turns for the matching session_id."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="step 1", session_id="sess-1", num_turns=10)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="step 2", session_id="sess-2", num_turns=20)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="step 3", session_id="sess-1", num_turns=15)

        assert tracker.get_session_turns("sess-1") == 25
        assert tracker.get_session_turns("sess-2") == 20

    def test_get_session_turns_uses_last_session_id(self, project_dir: Path) -> None:
        """Defaults to last_session_id when no explicit session_id given."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="step 1", session_id="sess-1", num_turns=10)
        assert tracker.get_session_turns() == 10  # last_session_id = "sess-1"

    def test_get_session_cost_no_cycles(self, project_dir: Path) -> None:
        """Returns 0.0 when no cycles exist."""
        tracker = StateTracker(project_dir)
        assert tracker.get_session_cost("any-session") == 0.0

    def test_get_session_cost_single_session(self, project_dir: Path) -> None:
        """Correctly sums cost for a single session."""
        tracker = StateTracker(project_dir)
        for i in range(3):
            tracker.increment_iteration()
            tracker.add_cycle(prompt=f"step {i}", session_id="sess-1", cost_usd=1.50)
        assert tracker.get_session_cost("sess-1") == pytest.approx(4.50)

    def test_get_session_cost_filters_by_session(self, project_dir: Path) -> None:
        """Only counts cost for the matching session_id."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="step 1", session_id="sess-1", cost_usd=2.0)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="step 2", session_id="sess-2", cost_usd=5.0)

        assert tracker.get_session_cost("sess-1") == pytest.approx(2.0)
        assert tracker.get_session_cost("sess-2") == pytest.approx(5.0)


class TestModelAnalytics:
    def test_single_model_analytics(self, project_dir: Path) -> None:
        """Analytics for a single model computes correct averages."""
        tracker = StateTracker(project_dir)
        for i in range(3):
            tracker.increment_iteration()
            tracker.add_cycle(
                prompt=f"step {i}", model="sonnet",
                cost_usd=0.10, duration_ms=10000, num_turns=5,
            )

        analytics = tracker.compute_model_analytics()
        assert "sonnet" in analytics
        s = analytics["sonnet"]
        assert s.iterations == 3
        assert s.avg_turns == 5.0
        assert s.avg_cost_usd == pytest.approx(0.10)
        assert s.avg_duration_ms == 10000.0
        assert s.timeout_count == 0
        assert s.error_count == 0

    def test_mixed_model_analytics(self, project_dir: Path) -> None:
        """Analytics splits correctly between opus and sonnet."""
        tracker = StateTracker(project_dir)
        # 2 opus cycles
        for i in range(2):
            tracker.increment_iteration()
            tracker.add_cycle(
                prompt=f"opus {i}", model="opus",
                cost_usd=0.50, num_turns=10,
            )
        # 1 sonnet cycle
        tracker.increment_iteration()
        tracker.add_cycle(
            prompt="sonnet 0", model="sonnet",
            cost_usd=0.10, num_turns=5,
        )

        analytics = tracker.compute_model_analytics()
        assert analytics["opus"].iterations == 2
        assert analytics["opus"].avg_turns == 10.0
        assert analytics["sonnet"].iterations == 1
        assert analytics["sonnet"].avg_turns == 5.0

    def test_timeout_cycles_counted(self, project_dir: Path) -> None:
        """Zero-turn, zero-cost cycles counted as timeouts."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="timeout", model="opus", cost_usd=0.0, num_turns=0)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="success", model="opus", cost_usd=0.5, num_turns=10)

        analytics = tracker.compute_model_analytics()
        assert analytics["opus"].timeout_count == 1
        assert analytics["opus"].timeout_rate == pytest.approx(0.5)

    def test_error_cycles_counted(self, project_dir: Path) -> None:
        """Error cycles counted in error_count and error_rate."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="error", model="sonnet", is_error=True)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="ok", model="sonnet", num_turns=5)

        analytics = tracker.compute_model_analytics()
        assert analytics["sonnet"].error_count == 1
        assert analytics["sonnet"].error_rate == pytest.approx(0.5)

    def test_backwards_compatibility_no_model_field(self, project_dir: Path) -> None:
        """Old cycles without model field grouped under 'unknown'."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="old cycle", cost_usd=0.05, num_turns=3)

        analytics = tracker.compute_model_analytics()
        assert "unknown" in analytics
        assert analytics["unknown"].iterations == 1

    def test_empty_cycles_returns_empty(self, project_dir: Path) -> None:
        """No cycles returns empty analytics dict."""
        tracker = StateTracker(project_dir)
        analytics = tracker.compute_model_analytics()
        assert analytics == {}

    def test_model_field_persists_in_state(self, project_dir: Path) -> None:
        """Model field round-trips through save/load."""
        tracker = StateTracker(project_dir)
        tracker.increment_iteration()
        tracker.add_cycle(prompt="test", model="opus", cost_usd=0.50)
        tracker.save()

        tracker2 = StateTracker(project_dir)
        tracker2.load()
        assert tracker2.state.cycles[0].model == "opus"

    def test_old_state_without_model_loads(self, project_dir: Path) -> None:
        """State.json from before model field was added still loads."""
        state_file = project_dir / ".workflow" / "state.json"
        old_state = {
            "version": 1,
            "session_id": "old-session",
            "iteration": 1,
            "status": "running",
            "cycles": [{
                "iteration": 1,
                "prompt_preview": "old",
                "cost_usd": 0.05,
                "num_turns": 3,
                "is_error": False,
            }],
            "metrics": {"total_cost_usd": 0.05, "total_duration_ms": 0, "total_turns": 3, "error_count": 0, "files_modified": []},
        }
        state_file.write_text(json.dumps(old_state), encoding="utf-8")

        tracker = StateTracker(project_dir)
        result = tracker.load()
        assert result.success
        assert tracker.state.cycles[0].model is None
