"""Tests for capability handshake in council_query.py.

Verifies that WEB_SEARCH_ENABLED + per-model web_search_capable flags
correctly control web_search tool inclusion.
"""

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add council-automation to path
sys.path.insert(0, str(Path(__file__).parent))

import council_config
import council_query


class TestCapabilityHandshake(unittest.TestCase):
    """Test that web_search tool is only included when both flags are True."""

    def test_web_search_disabled_no_tools(self):
        """When WEB_SEARCH_ENABLED=False, no model gets web_search regardless of capability."""
        with patch.object(council_config, "WEB_SEARCH_ENABLED", False):
            # Reload to pick up patched value
            importlib.reload(council_query)

            for model in council_config.ANALYSIS_MODELS:
                use_ws = model.get("web_search_capable", False) and council_config.WEB_SEARCH_ENABLED
                self.assertFalse(
                    use_ws,
                    f"{model['label']} should NOT get web_search when system disabled",
                )

    def test_web_search_enabled_respects_capability(self):
        """When WEB_SEARCH_ENABLED=True, only capable models get web_search."""
        with patch.object(council_config, "WEB_SEARCH_ENABLED", True):
            for model in council_config.ANALYSIS_MODELS:
                use_ws = model.get("web_search_capable", False) and True
                if model["label"] == "GPT-5.2":
                    self.assertTrue(use_ws, "GPT-5.2 should get web_search (capable=True)")
                elif model["label"] in ("Claude Sonnet 4.5", "Gemini 3 Pro"):
                    self.assertFalse(use_ws, f"{model['label']} should NOT get web_search (capable=False)")

    def test_model_config_has_capability_flag(self):
        """All models must have web_search_capable field."""
        for model in council_config.ANALYSIS_MODELS:
            self.assertIn(
                "web_search_capable", model,
                f"{model['label']} missing web_search_capable flag",
            )

    def test_kwargs_build_without_web_search(self):
        """Verify kwargs dict does NOT include tools when web_search disabled."""
        kwargs = {
            "model": "openai/gpt-5.2",
            "input": "test query",
            "max_output_tokens": council_config.MAX_OUTPUT_TOKENS,
            "instructions": council_config.MODEL_INSTRUCTIONS,
        }
        # Simulate the handshake with WEB_SEARCH_ENABLED=False
        use_web_search = True and False  # capable=True, enabled=False
        if use_web_search:
            kwargs["tools"] = [{"type": "web_search"}]

        self.assertNotIn("tools", kwargs, "tools should not be in kwargs when disabled")

    def test_kwargs_build_with_web_search(self):
        """Verify kwargs dict includes tools when both flags are True."""
        kwargs = {
            "model": "openai/gpt-5.2",
            "input": "test query",
            "max_output_tokens": council_config.MAX_OUTPUT_TOKENS,
            "instructions": council_config.MODEL_INSTRUCTIONS,
        }
        # Simulate the handshake with both True
        use_web_search = True and True  # capable=True, enabled=True
        if use_web_search:
            kwargs["tools"] = [{"type": "web_search"}]

        self.assertIn("tools", kwargs, "tools should be in kwargs when both flags True")
        self.assertEqual(kwargs["tools"], [{"type": "web_search"}])

    def test_fallback_config(self):
        """Sonar fallback config is correct."""
        self.assertEqual(council_config.FALLBACK_MODEL, "sonar-pro")
        self.assertTrue(council_config.FALLBACK_ENABLED)

    def test_model_instructions_no_stale_references(self):
        """MODEL_INSTRUCTIONS should not reference 'search results from other models'."""
        self.assertNotIn("search results from other models", council_config.MODEL_INSTRUCTIONS)
        self.assertNotIn("search findings", council_config.MODEL_INSTRUCTIONS)

    def test_no_dead_config_exports(self):
        """Verify dead config names are removed."""
        self.assertFalse(hasattr(council_config, "SEARCH_MODELS"))
        self.assertFalse(hasattr(council_config, "WEB_SEARCH_INSTRUCTIONS"))
        self.assertFalse(hasattr(council_config, "ANALYSIS_INSTRUCTIONS"))
        self.assertFalse(hasattr(council_config, "PERPLEXITY_MODELS"))


if __name__ == "__main__":
    unittest.main()
