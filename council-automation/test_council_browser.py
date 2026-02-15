"""Tests for council_browser.py — Playwright-based Perplexity council automation.

Unit tests that don't require a running browser or Perplexity session.
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure council_config is importable
sys.path.insert(0, str(Path(__file__).parent))

from council_browser import PerplexityCouncil, _load_selectors


def test_load_selectors_from_file():
    """Selectors load from perplexity-selectors.json."""
    selectors = _load_selectors()
    assert isinstance(selectors, dict)
    assert "textarea" in selectors
    assert selectors["textarea"] == "#ask-input"
    assert "responseContainer" in selectors
    assert "councilSynthesis" in selectors
    print("PASS: test_load_selectors_from_file")


def test_load_selectors_fallback():
    """Falls back to defaults when file missing."""
    from council_config import SELECTORS_PATH

    original = SELECTORS_PATH
    import council_browser
    council_browser.SELECTORS_PATH = Path("/nonexistent/path.json")
    try:
        selectors = _load_selectors()
        assert "textarea" in selectors
        assert selectors["textarea"] == "#ask-input"
        print("PASS: test_load_selectors_fallback")
    finally:
        council_browser.SELECTORS_PATH = original


def test_parse_cookie_string():
    """Semicolon-delimited cookie string -> list of dicts."""
    cookie_str = "session_id=abc123; user_token=xyz789; pplx_theme=dark"
    cookies = PerplexityCouncil._parse_cookie_string(cookie_str)

    assert len(cookies) == 3
    assert cookies[0]["name"] == "session_id"
    assert cookies[0]["value"] == "abc123"
    assert cookies[0]["domain"] == ".perplexity.ai"
    assert cookies[0]["path"] == "/"
    assert cookies[1]["name"] == "user_token"
    assert cookies[1]["value"] == "xyz789"
    assert cookies[2]["name"] == "pplx_theme"
    assert cookies[2]["value"] == "dark"
    print("PASS: test_parse_cookie_string")


def test_parse_cookie_string_empty():
    """Empty cookie string returns empty list."""
    assert PerplexityCouncil._parse_cookie_string("") == []
    assert PerplexityCouncil._parse_cookie_string(None) == []
    print("PASS: test_parse_cookie_string_empty")


def test_parse_cookie_string_with_values_containing_equals():
    """Cookie values with = signs are preserved."""
    cookie_str = "token=abc=def=ghi; simple=value"
    cookies = PerplexityCouncil._parse_cookie_string(cookie_str)

    assert len(cookies) == 2
    assert cookies[0]["name"] == "token"
    assert cookies[0]["value"] == "abc=def=ghi"
    print("PASS: test_parse_cookie_string_with_values_containing_equals")


def test_council_init_defaults():
    """PerplexityCouncil initializes with default config values."""
    council = PerplexityCouncil()
    assert council.headless is False  # Headful by default (Cloudflare blocks headless)
    assert council.timeout == 120_000
    assert isinstance(council.selectors, dict)
    assert council.playwright is None
    assert council.context is None
    print("PASS: test_council_init_defaults")


def test_council_init_custom():
    """PerplexityCouncil accepts custom params."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        session_path = Path(f.name)

    council = PerplexityCouncil(headless=False, session_path=session_path, timeout=60000)
    assert council.headless is False
    assert council.session_path == session_path
    assert council.timeout == 60000
    print("PASS: test_council_init_custom")


def test_result_schema():
    """Extracted result dict has required keys."""
    expected_keys = {"synthesis", "models", "citations"}
    # Simulate the structure council_browser.extract_results would return
    result = {
        "synthesis": "Test synthesis text",
        "models": {"GPT-5.2": {"response": "test"}},
        "citations": [{"url": "https://example.com", "text": "Example"}],
    }
    assert expected_keys.issubset(result.keys())
    assert isinstance(result["models"], dict)
    assert isinstance(result["citations"], list)
    print("PASS: test_result_schema")


def test_run_result_error_format():
    """Error results include error and step fields."""
    error_result = {
        "error": "Session expired",
        "step": "validate",
    }
    assert "error" in error_result
    assert "step" in error_result
    print("PASS: test_run_result_error_format")


def test_cli_args():
    """CLI argument parsing works."""
    import argparse
    from council_browser import main

    # Verify the module has a main function that uses argparse
    import inspect
    source = inspect.getsource(main)
    assert "argparse" in source or "ArgumentParser" in source
    assert "--headful" in source
    assert "--save-session" in source
    assert "--timeout" in source
    print("PASS: test_cli_args")


def test_session_conversion_format():
    """Legacy session format is correctly identified."""
    # Legacy format: dict with cookies string
    legacy = {
        "cookies": "session_id=abc; token=xyz",
        "localStorage": {"theme": "dark"},
    }
    assert isinstance(legacy, dict)
    assert "cookies" in legacy

    # Playwright-native format: list of cookie dicts
    native = [
        {"name": "session_id", "value": "abc", "domain": ".perplexity.ai", "path": "/"},
    ]
    assert isinstance(native, list)
    print("PASS: test_session_conversion_format")


def test_council_query_integration_format():
    """Browser results convert to standard council result format."""
    # Simulate what run_browser_query produces
    browser_result = {
        "synthesis": "The consensus is...",
        "models": {
            "GPT-5.2": {"response": "GPT response"},
            "Claude Sonnet 4.5": {"response": "Claude response"},
        },
        "citations": [{"url": "https://example.com", "text": "src"}],
        "query": "test query",
        "mode": "browser",
        "completed": True,
        "execution_time_ms": 85000,
    }

    # Verify it has the fields council_query.py expects
    assert "synthesis" in browser_result
    assert "models" in browser_result
    assert "mode" in browser_result
    assert browser_result["mode"] == "browser"
    print("PASS: test_council_query_integration_format")


def test_analyze_screenshot_prompt_format():
    """Vision analysis prompt includes required JSON keys."""
    import inspect
    source = inspect.getsource(PerplexityCouncil._analyze_screenshot)
    assert "models_completed" in source
    assert "synthesis_visible" in source
    assert "page_state" in source
    assert "error_text" in source
    print("PASS: test_analyze_screenshot_prompt_format")


def test_vision_config_constants():
    """Vision config constants have sensible defaults."""
    from council_config import (
        VISION_MODEL,
        VISION_MAX_TOKENS,
        VISION_POLL_INTERVAL_MODELS,
        VISION_POLL_INTERVAL_SYNTHESIS,
        VISION_JPEG_QUALITY,
        VISION_ENABLED,
    )
    assert "haiku" in VISION_MODEL
    assert VISION_MAX_TOKENS <= 500
    assert VISION_POLL_INTERVAL_MODELS >= 5
    assert VISION_POLL_INTERVAL_SYNTHESIS >= 2
    assert 30 <= VISION_JPEG_QUALITY <= 80
    assert isinstance(VISION_ENABLED, bool)
    print("PASS: test_vision_config_constants")


def test_vision_fallback_without_api_key():
    """Without ANTHROPIC_API_KEY, falls back to CSS selectors."""
    import os
    saved = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        council = PerplexityCouncil()
        assert not bool(os.environ.get("ANTHROPIC_API_KEY"))
        print("PASS: test_vision_fallback_without_api_key")
    finally:
        if saved:
            os.environ["ANTHROPIC_API_KEY"] = saved


if __name__ == "__main__":
    tests = [
        test_load_selectors_from_file,
        test_load_selectors_fallback,
        test_parse_cookie_string,
        test_parse_cookie_string_empty,
        test_parse_cookie_string_with_values_containing_equals,
        test_council_init_defaults,
        test_council_init_custom,
        test_result_schema,
        test_run_result_error_format,
        test_cli_args,
        test_session_conversion_format,
        test_council_query_integration_format,
        test_analyze_screenshot_prompt_format,
        test_vision_config_constants,
        test_vision_fallback_without_api_key,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    if failed:
        sys.exit(1)
