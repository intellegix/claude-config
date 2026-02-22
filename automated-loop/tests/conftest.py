"""Shared pytest fixtures for the automated Claude loop test suite.

Non-fixture helpers (mock builders, NDJSON stream builders) are in helpers.py.
"""

import json
import sys
from pathlib import Path

import pytest

# Add the tests directory to sys.path so test files can import helpers.py
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a fully populated project directory.

    Includes: .workflow/, CLAUDE.md, MEMORY.md, .workflow/config.json.
    Tests needing a bare directory should use tmp_path directly.
    """
    workflow_dir = tmp_path / ".workflow"
    workflow_dir.mkdir()

    (tmp_path / "CLAUDE.md").write_text(
        "# Test Project\nAutomated loop test.", encoding="utf-8"
    )
    (tmp_path / "MEMORY.md").write_text(
        "# Key Learnings\n- Integration tests work.", encoding="utf-8"
    )

    config = {
        "limits": {"max_iterations": 10, "max_total_budget_usd": 5.0},
        "patterns": {"completion_markers": ["PROJECT_COMPLETE", "ALL_TASKS_DONE"]},
    }
    (workflow_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")

    return tmp_path
