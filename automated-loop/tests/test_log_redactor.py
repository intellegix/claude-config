"""Tests for log_redactor module."""

import logging

import pytest

from log_redactor import RedactingFilter, redact_string

# Default patterns from SecurityConfig
DEFAULT_PATTERNS = [
    r"sk-ant-[\w-]+",
    r"pplx-[\w]+",
    r"sk-proj-[\w-]+",
]


class TestRedactString:
    def test_redacts_anthropic_api_key(self) -> None:
        text = "Using key sk-ant-api03-z7ekhhHIJLhCuISogrQ for auth"
        result = redact_string(text, DEFAULT_PATTERNS)
        assert "sk-ant-" not in result
        assert "[REDACTED]" in result
        assert "for auth" in result

    def test_redacts_perplexity_api_key(self) -> None:
        text = "PERPLEXITY_API_KEY=pplx-jhZTkQlx1COxaG3K"
        result = redact_string(text, DEFAULT_PATTERNS)
        assert "pplx-" not in result
        assert "[REDACTED]" in result

    def test_redacts_openai_api_key(self) -> None:
        text = "key=sk-proj-z-g4XonIp8rDpv5VsPrV"
        result = redact_string(text, DEFAULT_PATTERNS)
        assert "sk-proj-" not in result
        assert "[REDACTED]" in result

    def test_multiple_patterns_in_one_string(self) -> None:
        text = "Keys: sk-ant-abc123 and pplx-xyz789"
        result = redact_string(text, DEFAULT_PATTERNS)
        assert "sk-ant-" not in result
        assert "pplx-" not in result
        assert result.count("[REDACTED]") == 2

    def test_empty_patterns_no_op(self) -> None:
        text = "sk-ant-api03-secret"
        result = redact_string(text, [])
        assert result == text

    def test_non_matching_passthrough(self) -> None:
        text = "No secrets here, just normal text"
        result = redact_string(text, DEFAULT_PATTERNS)
        assert result == text


class TestRedactingFilter:
    def test_filter_redacts_log_message(self) -> None:
        filt = RedactingFilter(DEFAULT_PATTERNS)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Auth with sk-ant-api03-secretkey123",
            args=None, exc_info=None,
        )
        filt.filter(record)
        assert "sk-ant-" not in record.msg
        assert "[REDACTED]" in record.msg

    def test_filter_redacts_args(self) -> None:
        filt = RedactingFilter(DEFAULT_PATTERNS)
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Key: %s", args=("pplx-secretkey123",),
            exc_info=None,
        )
        filt.filter(record)
        assert "pplx-" not in record.args[0]

    def test_filter_works_with_logging_module(self) -> None:
        """End-to-end: filter installed on a handler redacts output."""
        filt = RedactingFilter(DEFAULT_PATTERNS)
        handler = logging.StreamHandler()
        handler.addFilter(filt)

        test_logger = logging.getLogger("test_redaction")
        test_logger.addHandler(handler)
        test_logger.setLevel(logging.DEBUG)

        # This should not raise
        test_logger.info("Testing key sk-ant-api03-abc123 in logs")

        # Clean up
        test_logger.removeHandler(handler)
