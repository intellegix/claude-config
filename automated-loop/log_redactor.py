"""Log redaction utility — scrubs API keys and secrets from log output."""

from __future__ import annotations

import logging
import re
from typing import Sequence


def redact_string(text: str, patterns: Sequence[str]) -> str:
    """Replace all matches of the given regex patterns with [REDACTED]."""
    for pattern in patterns:
        try:
            text = re.sub(pattern, "[REDACTED]", text)
        except re.error:
            pass
    return text


class RedactingFilter(logging.Filter):
    """Logging filter that redacts sensitive patterns from log records."""

    def __init__(self, patterns: Sequence[str], name: str = "") -> None:
        super().__init__(name)
        self._patterns = list(patterns)

    def filter(self, record: logging.LogRecord) -> bool:
        if self._patterns:
            record.msg = redact_string(str(record.msg), self._patterns)
            if record.args:
                record.args = tuple(
                    redact_string(str(a), self._patterns) if isinstance(a, str) else a
                    for a in record.args
                )
        return True
