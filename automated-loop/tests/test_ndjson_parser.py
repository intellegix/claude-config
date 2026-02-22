"""Tests for ndjson_parser module."""

import json

import pytest

from ndjson_parser import (
    ClaudeEvent,
    ClaudeResult,
    extract_result,
    parse_ndjson_line,
    parse_ndjson_string,
    process_events,
)


# --- Sample NDJSON data (from Claude Code --output-format stream-json) ---

INIT_EVENT = json.dumps({
    "type": "init",
    "session_id": "abc-123-def",
    "model": "claude-sonnet-4-5-20250929",
    "tools": ["Read", "Write", "Edit", "Bash"],
})

ASSISTANT_EVENT = json.dumps({
    "type": "assistant",
    "message": {
        "role": "assistant",
        "content": [
            {"type": "text", "text": "I'll implement the feature now."},
            {
                "type": "tool_use",
                "id": "tu_1",
                "name": "Write",
                "input": {"file_path": "/tmp/test.py", "content": "print('hello')"},
            },
        ],
    },
    "session_id": "abc-123-def",
})

THINKING_EVENT = json.dumps({
    "type": "assistant",
    "message": {
        "role": "assistant",
        "content": [
            {"type": "thinking", "thinking": "Let me analyze the codebase..."},
            {"type": "text", "text": "Here's my plan."},
        ],
    },
    "session_id": "abc-123-def",
})

RESULT_EVENT = json.dumps({
    "type": "result",
    "session_id": "abc-123-def",
    "total_cost_usd": 0.042,
    "total_duration_ms": 15000,
    "total_duration_api_ms": 12000,
    "num_turns": 3,
    "result": "Implementation complete. All files created.",
    "is_error": False,
})

ERROR_RESULT_EVENT = json.dumps({
    "type": "result",
    "session_id": "err-456",
    "total_cost_usd": 0.01,
    "total_duration_ms": 5000,
    "total_duration_api_ms": 3000,
    "num_turns": 1,
    "result": "Error: file not found",
    "is_error": True,
})

CONTENT_BLOCK_START_EVENT = json.dumps({
    "type": "content_block_start",
    "content_block": {
        "type": "tool_use",
        "id": "tu_2",
        "name": "Edit",
        "input": {"file_path": "/tmp/config.py", "old_string": "x", "new_string": "y"},
    },
})


class TestParseNdjsonLine:
    def test_parse_init_event(self) -> None:
        event = parse_ndjson_line(INIT_EVENT)
        assert event is not None
        assert event.type == "init"
        assert event.session_id == "abc-123-def"

    def test_parse_result_event(self) -> None:
        event = parse_ndjson_line(RESULT_EVENT)
        assert event is not None
        assert event.type == "result"
        assert event.raw["total_cost_usd"] == 0.042

    def test_parse_empty_line(self) -> None:
        assert parse_ndjson_line("") is None
        assert parse_ndjson_line("   ") is None

    def test_parse_malformed_json(self) -> None:
        assert parse_ndjson_line("not json {{{") is None

    def test_parse_whitespace_padded(self) -> None:
        event = parse_ndjson_line(f"  {INIT_EVENT}  ")
        assert event is not None
        assert event.type == "init"


class TestParseNdjsonString:
    def test_parse_full_stream(self) -> None:
        raw = f"{INIT_EVENT}\n{ASSISTANT_EVENT}\n{RESULT_EVENT}"
        events = parse_ndjson_string(raw)

        assert len(events) == 3
        assert events[0].type == "init"
        assert events[1].type == "assistant"
        assert events[2].type == "result"

    def test_parse_with_blank_lines(self) -> None:
        raw = f"{INIT_EVENT}\n\n\n{RESULT_EVENT}\n"
        events = parse_ndjson_string(raw)
        assert len(events) == 2

    def test_parse_with_malformed_lines(self) -> None:
        raw = f"{INIT_EVENT}\nnot json\n{RESULT_EVENT}"
        events = parse_ndjson_string(raw)
        assert len(events) == 2  # malformed line skipped


class TestProcessEvents:
    def test_extracts_session_id(self) -> None:
        events = parse_ndjson_string(f"{INIT_EVENT}\n{RESULT_EVENT}")
        parsed = process_events(events)
        assert parsed.session_id == "abc-123-def"

    def test_extracts_result(self) -> None:
        events = parse_ndjson_string(f"{INIT_EVENT}\n{RESULT_EVENT}")
        parsed = process_events(events)

        assert parsed.result is not None
        assert parsed.result.session_id == "abc-123-def"
        assert parsed.result.cost_usd == 0.042
        assert parsed.result.num_turns == 3
        assert parsed.result.is_error is False

    def test_extracts_assistant_text(self) -> None:
        events = parse_ndjson_string(f"{INIT_EVENT}\n{ASSISTANT_EVENT}\n{RESULT_EVENT}")
        parsed = process_events(events)
        assert "I'll implement the feature now." in parsed.assistant_text

    def test_extracts_thinking_text(self) -> None:
        events = parse_ndjson_string(f"{INIT_EVENT}\n{THINKING_EVENT}\n{RESULT_EVENT}")
        parsed = process_events(events)
        assert "Let me analyze the codebase" in parsed.thinking_text

    def test_tracks_tools_used(self) -> None:
        events = parse_ndjson_string(f"{INIT_EVENT}\n{ASSISTANT_EVENT}\n{RESULT_EVENT}")
        parsed = process_events(events)
        assert "Write" in parsed.tools_used

    def test_tracks_files_modified(self) -> None:
        events = parse_ndjson_string(f"{INIT_EVENT}\n{ASSISTANT_EVENT}\n{RESULT_EVENT}")
        parsed = process_events(events)
        assert "/tmp/test.py" in parsed.files_modified

    def test_tracks_files_from_content_block_start(self) -> None:
        events = parse_ndjson_string(
            f"{INIT_EVENT}\n{CONTENT_BLOCK_START_EVENT}\n{RESULT_EVENT}"
        )
        parsed = process_events(events)
        assert "Edit" in parsed.tools_used
        assert "/tmp/config.py" in parsed.files_modified

    def test_deduplicates_files_modified(self) -> None:
        # Two events modifying same file
        raw = f"{INIT_EVENT}\n{ASSISTANT_EVENT}\n{ASSISTANT_EVENT}\n{RESULT_EVENT}"
        events = parse_ndjson_string(raw)
        parsed = process_events(events)
        assert parsed.files_modified.count("/tmp/test.py") == 1

    def test_error_result(self) -> None:
        events = parse_ndjson_string(f"{INIT_EVENT}\n{ERROR_RESULT_EVENT}")
        parsed = process_events(events)
        assert parsed.result is not None
        assert parsed.result.is_error is True
        assert parsed.result.session_id == "err-456"


class TestExtractResult:
    def test_extract_from_events(self) -> None:
        events = parse_ndjson_string(f"{INIT_EVENT}\n{ASSISTANT_EVENT}\n{RESULT_EVENT}")
        result = extract_result(events)
        assert result is not None
        assert result.session_id == "abc-123-def"
        assert result.cost_usd == 0.042

    def test_extract_from_events_no_result(self) -> None:
        events = parse_ndjson_string(f"{INIT_EVENT}\n{ASSISTANT_EVENT}")
        result = extract_result(events)
        assert result is None

    def test_extract_takes_last_result(self) -> None:
        # Multiple result events — take the last one
        raw = f"{INIT_EVENT}\n{RESULT_EVENT}\n{ERROR_RESULT_EVENT}"
        events = parse_ndjson_string(raw)
        result = extract_result(events)
        assert result is not None
        assert result.session_id == "err-456"  # last result event
