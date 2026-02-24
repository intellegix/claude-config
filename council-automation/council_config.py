"""Configuration for hybrid council automation."""

import os
import sys
from pathlib import Path

# --- System-level capability toggle ---
# When True AND a model has web_search_capable=True, the web_search tool
# is included in Responses API calls. Currently False because Perplexity's
# web_search tool causes empty output_text for Claude/Gemini and intermittent
# failures for GPT-5.2. Flip to True when Perplexity fixes the tool-loop
# abstraction, then re-test per model.
WEB_SEARCH_ENABLED = False

# --- Perplexity Responses API models ---
# web_search_capable: whether the model *can* handle web_search (if API supports it)
# Actual tool inclusion = web_search_capable AND WEB_SEARCH_ENABLED
ANALYSIS_MODELS = [
    {"id": "openai/gpt-5.2", "label": "GPT-5.2", "web_search_capable": True, "provider": "openai"},
    {"id": "anthropic/claude-sonnet-4-5", "label": "Claude Sonnet 4.5", "web_search_capable": False, "provider": "anthropic"},
    {"id": "google/gemini-3-pro-preview", "label": "Gemini 3 Pro", "web_search_capable": False, "provider": "google"},
]

# --- Fallback: chat/completions with Sonar (when Responses API is down) ---
# Only Sonar models are available via chat/completions.
# Loses multi-model diversity but gains reliability.
FALLBACK_MODEL = "sonar-pro"
FALLBACK_ENABLED = False  # Disabled — browser mode is primary, no API fallback

# --- Synthesis model (Anthropic API direct) ---
SYNTHESIS_MODEL = "claude-opus-4-6"
THINKING_BUDGET = 10_000  # extended thinking tokens

# --- Directories ---
CACHE_DIR = Path.home() / ".claude" / "council-cache"
HISTORY_DIR = CACHE_DIR / "history"
AUTOMATION_DIR = Path.home() / ".claude" / "council-automation"
COUNCIL_LOGS_DIR = Path.home() / ".claude" / "council-logs"
SYNTHESIS_PROMPT_PATH = AUTOMATION_DIR / "synthesis_prompt.md"

# --- Timeouts (seconds) ---
PERPLEXITY_TIMEOUT = 60
PERPLEXITY_CONNECT_TIMEOUT = 10  # Fast fail for connection-level issues
SYNTHESIS_TIMEOUT = 120
TOTAL_TIMEOUT = 180

# --- Retry config ---
PERPLEXITY_RETRIES = 1
SYNTHESIS_RETRIES = 2

# --- Model instructions ---
MODEL_INSTRUCTIONS = (
    "Provide concrete, actionable technical analysis. "
    "If you have web search access, cite authoritative sources. "
    "Focus on practical recommendations with specific file paths and code changes."
)

# --- Max output tokens for Perplexity models ---
MAX_OUTPUT_TOKENS = 4096

# --- Direct provider fallback (Tier 3) ---
# When both Perplexity Responses API and Sonar are down, call providers directly.
# Loses web search/citations but preserves multi-model diversity.
DIRECT_PROVIDERS_ENABLED = False  # Disabled — browser mode is primary

# Perplexity model ID → native provider model ID
DIRECT_MODEL_MAP = {
    "openai/gpt-5.2": "gpt-5.2",
    "anthropic/claude-sonnet-4-5": "claude-sonnet-4-5-20250929",
    "google/gemini-3-pro-preview": "gemini-3-pro-preview",
}

# Per-provider env var names for API keys
PROVIDER_API_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
}

# Pricing per 1M tokens (input/output) for cost tracking
DIRECT_PRICING = {
    "openai/gpt-5.2": {"input": 1.75, "output": 14.0},
    "anthropic/claude-sonnet-4-5": {"input": 3.0, "output": 15.0},
    "google/gemini-3-pro-preview": {"input": 2.0, "output": 12.0},
}

DIRECT_TIMEOUT = 60  # seconds per direct provider call

# --- Browser automation (Playwright) ---
# rebrowser-playwright patches the CDP Runtime.enable leak that Cloudflare detects.
# v1.52.0 tested 2026-02-24: ProtocolError persists, Cloudflare still blocks headless.
# Set USE_REBROWSER = True to re-test after rebrowser-patches updates.
USE_REBROWSER = False

# Headful by default — rebrowser-patches v1.52.0 does not yet bypass Cloudflare on Perplexity.
# Set BROWSER_HEADLESS_FALLBACK = True to auto-retry headful if headless gets blocked.
BROWSER_HEADLESS = False
BROWSER_HEADLESS_FALLBACK = True  # Safety net: headless → detect Cloudflare → retry headful
BROWSER_TIMEOUT = 180_000  # ms, total timeout for council query
BROWSER_RESEARCH_TIMEOUT = 480_000  # ms, deep research can take up to 7 min
BROWSER_LABS_TIMEOUT = 840_000  # ms, labs mode — 14 min (1 min buffer under 15 min MCP timeout)
BROWSER_STABLE_MS = 8_000  # ms, content unchanged = stable
BROWSER_POLL_INTERVAL = 2_000  # ms, check interval

# Mode-aware stability thresholds (research/labs pause 60-120s+ between sections)
# These must be LONGER than the longest Perplexity "thinking" pause to avoid
# declaring completion during an inter-section pause.
BROWSER_STABLE_MS_RESEARCH = 120_000  # ms, 2 min — fallback only (smart detection is primary)
BROWSER_STABLE_MS_LABS = 150_000      # ms, 2.5 min — fallback only (smart detection is primary)
BROWSER_POLL_INTERVAL_RESEARCH = 3_000  # ms, slightly slower polling for long responses

# DOM signal guards — prevent premature completion detection
# Perplexity shows sources/action buttons mid-generation; don't trust DOM signals early
BROWSER_DOM_MIN_ELAPSED_RESEARCH = 120_000  # ms, fallback only (smart detection is primary)
BROWSER_DOM_MIN_ELAPSED_LABS = 180_000      # ms, fallback only (smart detection is primary)
BROWSER_DOM_MIN_TEXT_LENGTH = 3000          # chars, research reports are 5000+ when complete
BROWSER_DOM_CONFIRM_WAIT = 30_000           # ms, polling window with 5s growth checks (must exceed longest inter-section pause)
BROWSER_TYPE_DELAY = 30  # ms between keystrokes

# --- Smart completion detection (stop button + multi-signal) ---
BROWSER_STOP_BUTTON_POLL_MS = 1_000       # ms, polling interval for stop button check
BROWSER_STOP_BUTTON_DEBOUNCE_MS = 3_000   # ms, re-check after disappearance
BROWSER_MIN_GENERATION_TIME_MS = 30_000   # ms, minimum before accepting stop button signal
BROWSER_CONFIRMATION_WINDOW_MS = 10_000   # ms, wait for confirming signal after primary
BROWSER_MUTATION_STABILITY_MS = 5_000     # ms, zero mutations = stable
BROWSER_USER_DATA_DIR = Path.home() / ".claude" / "config" / "playwright-chrome-profile"
BROWSER_SESSION_PATH = Path.home() / ".claude" / "config" / "playwright-session.json"
SELECTORS_PATH = Path.home() / ".claude" / "perplexity-selectors.json"

# --- Concurrent browser sessions ---
MAX_CONCURRENT_SESSIONS = 3       # Max simultaneous Playwright browsers
SEMAPHORE_TTL = 300               # seconds, auto-expire stale session slots
SEMAPHORE_WAIT_TIMEOUT = 30       # seconds, wait for slot before BROWSER_BUSY
BROWSER_SESSIONS_DIR = Path.home() / ".claude" / "config" / "browser-sessions"
BROWSER_LOCALSTORAGE_PATH = Path.home() / ".claude" / "config" / "playwright-localstorage.json"

# --- Vision monitoring (Claude Haiku for page state detection) ---
VISION_MODEL = "claude-haiku-4-5-20251001"
VISION_MAX_TOKENS = 300
VISION_POLL_INTERVAL_MODELS = 8  # seconds between screenshots during model generation
VISION_POLL_INTERVAL_SYNTHESIS = 4  # seconds during synthesis phase (faster)
VISION_JPEG_QUALITY = 60  # lower quality = fewer tokens = cheaper
VISION_ENABLED = True  # Set False to force CSS selector fallback


def validate_config(mode: str) -> tuple[list[str], list[str]]:
    """Validate configuration for the given mode.

    Returns (errors, warnings) — errors are fatal for the mode, warnings are informational.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Common: ensure output directories are writable
    for d in [CACHE_DIR, HISTORY_DIR, COUNCIL_LOGS_DIR]:
        if not d.exists():
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                errors.append(f"Cannot create directory {d}: {e}")

    if mode in ("browser", "auto"):
        try:
            if USE_REBROWSER:
                from rebrowser_playwright.async_api import async_playwright  # noqa: F401
            else:
                from playwright.async_api import async_playwright  # noqa: F401
        except ImportError:
            pkg = "rebrowser-playwright" if USE_REBROWSER else "playwright"
            errors.append(f"{pkg} not installed: pip install {pkg} && python -m playwright install chromium")
        if not BROWSER_SESSION_PATH.exists():
            warnings.append(f"No session file: {BROWSER_SESSION_PATH}. Run: python council_browser.py --save-session")

    if mode in ("api", "auto", "direct"):
        if not os.environ.get("PERPLEXITY_API_KEY"):
            if mode == "auto":
                warnings.append("PERPLEXITY_API_KEY not set — auto mode will skip API tier")
            elif mode != "direct":
                errors.append("PERPLEXITY_API_KEY not set (required for api mode)")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        warnings.append("ANTHROPIC_API_KEY not set — Opus synthesis and vision monitoring disabled")

    return errors, warnings


def print_validation(mode: str) -> bool:
    """Run validation and print results. Returns True if no fatal errors."""
    errors, warnings = validate_config(mode)
    for w in warnings:
        print(f"  WARNING: {w}", file=sys.stderr)
    for e in errors:
        print(f"  ERROR: {e}", file=sys.stderr)
    if errors:
        print(f"  Startup validation failed for --mode {mode}", file=sys.stderr)
        return False
    return True
