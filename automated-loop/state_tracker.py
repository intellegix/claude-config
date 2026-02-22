"""Persistent workflow state tracking for the automated Claude loop."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from config import Result

logger = logging.getLogger(__name__)


class CycleRecord(BaseModel):
    """Record of a single loop iteration."""

    iteration: int
    prompt_preview: str = Field(default="", max_length=200)
    session_id: Optional[str] = None
    cost_usd: float = 0.0
    duration_ms: int = 0
    num_turns: int = 0
    research_query: Optional[str] = None
    completed_at: Optional[str] = None
    is_error: bool = False
    error_message: Optional[str] = None


class WorkflowMetrics(BaseModel):
    """Aggregated metrics across all cycles."""

    total_cost_usd: float = 0.0
    total_duration_ms: int = 0
    total_turns: int = 0
    error_count: int = 0
    files_modified: list[str] = Field(default_factory=list)


CURRENT_STATE_VERSION = 1


class WorkflowState(BaseModel):
    """Root state model persisted to .workflow/state.json."""

    version: int = Field(default=CURRENT_STATE_VERSION)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    iteration: int = 0
    status: str = Field(default="idle")  # idle, running, paused, completed, failed
    cycles: list[CycleRecord] = Field(default_factory=list)
    metrics: WorkflowMetrics = Field(default_factory=WorkflowMetrics)
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    last_session_id: Optional[str] = None  # Claude CLI session ID for --resume


class StateTracker:
    """Manages persistent workflow state in .workflow/state.json."""

    def __init__(self, project_path: str | Path) -> None:
        self.project_path = Path(project_path)
        self.state_path = self.project_path / ".workflow" / "state.json"
        self.state = WorkflowState()

    @staticmethod
    def _migrate_state(raw: dict) -> dict:
        """Migrate older state formats to current version."""
        if "version" not in raw:
            raw["version"] = 1
            logger.info("Migrated state file: added version=1")
        return raw

    def load(self) -> Result[WorkflowState]:
        """Load state from disk. Returns defaults if file doesn't exist."""
        if not self.state_path.exists():
            logger.info("No existing state at %s, starting fresh", self.state_path)
            return Result.ok(self.state)

        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            raw = self._migrate_state(raw)
            self.state = WorkflowState.model_validate(raw)
            return Result.ok(self.state)
        except json.JSONDecodeError as e:
            return Result.fail(f"Corrupt state file: {e}", "JSON_ERROR")
        except Exception as e:
            return Result.fail(f"State load failed: {e}", "LOAD_ERROR")

    def save(self) -> Result[None]:
        """Persist current state to disk."""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(
                self.state.model_dump_json(indent=2), encoding="utf-8"
            )
            return Result.ok(None)
        except Exception as e:
            return Result.fail(f"State save failed: {e}", "SAVE_ERROR")

    def start_session(self) -> None:
        """Mark session as running with a fresh start time."""
        self.state.status = "running"
        self.state.start_time = datetime.now(timezone.utc).isoformat()

    def increment_iteration(self) -> int:
        """Advance iteration counter and return the new value."""
        self.state.iteration += 1
        return self.state.iteration

    def add_cycle(
        self,
        prompt: str,
        session_id: Optional[str] = None,
        cost_usd: float = 0.0,
        duration_ms: int = 0,
        num_turns: int = 0,
        is_error: bool = False,
        error_message: Optional[str] = None,
    ) -> None:
        """Record a completed loop cycle."""
        cycle = CycleRecord(
            iteration=self.state.iteration,
            prompt_preview=prompt[:200],
            session_id=session_id,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            num_turns=num_turns,
            completed_at=datetime.now(timezone.utc).isoformat(),
            is_error=is_error,
            error_message=error_message,
        )
        self.state.cycles.append(cycle)

        # Update aggregated metrics
        self.state.metrics.total_cost_usd += cost_usd
        self.state.metrics.total_duration_ms += duration_ms
        self.state.metrics.total_turns += num_turns
        if is_error:
            self.state.metrics.error_count += 1

        # Track last Claude session ID for --resume
        if session_id:
            self.state.last_session_id = session_id

    def complete(self) -> None:
        """Mark the workflow as completed."""
        self.state.status = "completed"
        self.state.end_time = datetime.now(timezone.utc).isoformat()

    def fail(self, reason: str) -> None:
        """Mark the workflow as failed."""
        self.state.status = "failed"
        self.state.end_time = datetime.now(timezone.utc).isoformat()
        logger.error("Workflow failed: %s", reason)

    def check_budget(
        self, per_iteration_limit: float, total_limit: float
    ) -> Result[None]:
        """Check if the last cycle or total cost exceeds budget limits."""
        if self.state.cycles:
            last_cost = self.state.cycles[-1].cost_usd
            if last_cost > per_iteration_limit:
                return Result.fail(
                    f"Per-iteration budget exceeded: ${last_cost:.4f} > ${per_iteration_limit:.4f}",
                    "BUDGET_EXCEEDED_ITERATION",
                )

        total_cost = self.state.metrics.total_cost_usd
        if total_cost > total_limit:
            return Result.fail(
                f"Total budget exceeded: ${total_cost:.4f} > ${total_limit:.4f}",
                "BUDGET_EXCEEDED_TOTAL",
            )

        return Result.ok(None)

    def validate_session_id(self, session_id: Optional[str]) -> Optional[str]:
        """Validate session ID format. Returns None if invalid."""
        if not session_id or not isinstance(session_id, str):
            return None
        session_id = session_id.strip()
        if not session_id or len(session_id) > 200:
            return None
        return session_id

    def clear_session(self) -> None:
        """Clear the last session ID (e.g., after resume failure)."""
        self.state.last_session_id = None

    def get_metrics(self) -> WorkflowMetrics:
        """Return current aggregated metrics."""
        return self.state.metrics
