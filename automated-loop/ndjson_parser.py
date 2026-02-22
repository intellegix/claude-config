"""NDJSON parser for Claude Code --output-format stream-json events.

Ported from Claude Watcher v2.7.0 ndjson-parser.ts.
Parses line-by-line NDJSON from Claude CLI stdout and extracts structured events.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Iterator, Optional, TextIO

logger = logging.getLogger(__name__)

# Tools that modify files, mapped to the input key holding the file path
FILE_MOD_TOOLS: dict[str, str] = {
    "Edit": "file_path",
    "Write": "file_path",
    "MultiEdit": "file_path",
}


@dataclass
class ClaudeEvent:
    """A single parsed NDJSON event from Claude CLI."""

    type: str  # init, assistant, user, result, system, content_block_start, content_block_delta
    raw: dict = field(default_factory=dict)

    @property
    def session_id(self) -> Optional[str]:
        return self.raw.get("session_id")


@dataclass
class ClaudeResult:
    """Extracted result from a Claude CLI run."""

    session_id: str
    cost_usd: float
    duration_ms: float
    num_turns: int
    result_text: str
    is_error: bool


@dataclass
class ParsedStream:
    """Accumulated data from a fully parsed NDJSON stream."""

    events: list[ClaudeEvent] = field(default_factory=list)
    session_id: Optional[str] = None
    result: Optional[ClaudeResult] = None
    assistant_text: str = ""
    thinking_text: str = ""
    files_modified: list[str] = field(default_factory=list)
    tools_used: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)


def parse_ndjson_line(line: str) -> Optional[ClaudeEvent]:
    """Parse a single NDJSON line into a ClaudeEvent."""
    stripped = line.strip()
    if not stripped:
        return None

    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        logger.warning("Malformed NDJSON line: %s (error: %s)", stripped[:200], e)
        return None

    event_type = data.get("type", "unknown")
    return ClaudeEvent(type=event_type, raw=data)


def parse_ndjson_stream(stream: TextIO) -> Iterator[ClaudeEvent]:
    """Generator that yields ClaudeEvents from a line-buffered text stream."""
    for line in stream:
        event = parse_ndjson_line(line)
        if event:
            yield event


def parse_ndjson_string(raw: str) -> list[ClaudeEvent]:
    """Parse a complete NDJSON string into a list of events."""
    events = []
    for line in raw.splitlines():
        event = parse_ndjson_line(line)
        if event:
            events.append(event)
    return events


def process_events(events: list[ClaudeEvent]) -> ParsedStream:
    """Process a list of events into a ParsedStream with extracted metadata."""
    parsed = ParsedStream()
    parsed.events = events

    for event in events:
        _process_event(event, parsed)

    # Deduplicate files modified
    parsed.files_modified = list(dict.fromkeys(parsed.files_modified))
    return parsed


def _process_event(event: ClaudeEvent, parsed: ParsedStream) -> None:
    """Process a single event, updating the ParsedStream accumulator."""
    if event.type == "init":
        parsed.session_id = event.raw.get("session_id")

    elif event.type == "system":
        # Newer Claude CLI versions emit session_id in system events
        sid = event.raw.get("session_id")
        if sid and not parsed.session_id:
            parsed.session_id = sid

    elif event.type == "result":
        parsed.session_id = event.raw.get("session_id", parsed.session_id)
        parsed.result = ClaudeResult(
            session_id=event.raw.get("session_id", ""),
            cost_usd=event.raw.get("total_cost_usd", 0.0),
            duration_ms=event.raw.get("total_duration_ms", 0.0),
            num_turns=event.raw.get("num_turns", 0),
            result_text=event.raw.get("result", ""),
            is_error=event.raw.get("is_error", False),
        )

    elif event.type == "assistant":
        message = event.raw.get("message", {})
        content_blocks = message.get("content", [])
        for block in content_blocks:
            _process_content_block(block, parsed)

    elif event.type == "content_block_start":
        block = event.raw.get("content_block", {})
        _process_content_block(block, parsed)


def _process_content_block(block: dict, parsed: ParsedStream) -> None:
    """Process a content block for text, thinking, and tool use tracking."""
    block_type = block.get("type", "")

    if block_type == "text" and block.get("text"):
        parsed.assistant_text += block["text"]

    elif block_type == "thinking" and block.get("thinking"):
        parsed.thinking_text += block["thinking"]

    elif block_type == "tool_use" and block.get("name"):
        tool_name = block["name"]
        parsed.tools_used.add(tool_name)

        # Track file modifications
        path_key = FILE_MOD_TOOLS.get(tool_name)
        if path_key:
            tool_input = block.get("input", {})
            file_path = tool_input.get(path_key)
            if isinstance(file_path, str):
                parsed.files_modified.append(file_path)


def extract_result(events: list[ClaudeEvent]) -> Optional[ClaudeResult]:
    """Extract the result event from a list of parsed events (searches from end)."""
    for event in reversed(events):
        if event.type == "result":
            return ClaudeResult(
                session_id=event.raw.get("session_id", ""),
                cost_usd=event.raw.get("total_cost_usd", 0.0),
                duration_ms=event.raw.get("total_duration_ms", 0.0),
                num_turns=event.raw.get("num_turns", 0),
                result_text=event.raw.get("result", ""),
                is_error=event.raw.get("is_error", False),
            )
    return None
