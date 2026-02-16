"""Standalone Playwright script for Perplexity council mode automation.

Runs the full council workflow autonomously:
  navigate -> activate council -> submit query -> wait -> extract -> return JSON

Usage:
    python council_browser.py "What architecture for X?"
    python council_browser.py --headful "Debug query"
    python council_browser.py --save-session   # headful login, save state
"""

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

from council_config import (
    BROWSER_HEADLESS,
    BROWSER_POLL_INTERVAL,
    BROWSER_SESSION_PATH,
    BROWSER_STABLE_MS,
    BROWSER_TIMEOUT,
    BROWSER_TYPE_DELAY,
    BROWSER_USER_DATA_DIR,
    SELECTORS_PATH,
    VISION_ENABLED,
    VISION_JPEG_QUALITY,
    VISION_MAX_TOKENS,
    VISION_MODEL,
    VISION_POLL_INTERVAL_MODELS,
    VISION_POLL_INTERVAL_SYNTHESIS,
)


def _log(msg: str) -> None:
    """Log to stderr (stdout reserved for JSON result)."""
    print(f"  [browser] {msg}", file=sys.stderr)


def _load_selectors() -> dict:
    """Load CSS selectors from perplexity-selectors.json."""
    if SELECTORS_PATH.exists():
        return json.loads(SELECTORS_PATH.read_text(encoding="utf-8"))
    _log(f"WARNING: selectors file not found at {SELECTORS_PATH}, using defaults")
    return {
        "textarea": "#ask-input",
        "responseContainer": ".prose",
        "councilSynthesis": ".prose:first-of-type",
        "councilModelRow": "[class*='interactable'][class*='appearance-none']",
        "councilCompletedIndicator": "[class*='Completed'], svg[class*='check']",
        "councilPanelClose": "button[aria-label='Close']",
    }


class PerplexityCouncil:
    """Autonomous Playwright-based Perplexity automation.

    Supports two Perplexity modes:
      - "council": /council slash command (multi-model, 3 AI responses + synthesis)
      - "research": /research slash command (deep research, single synthesized response)
    """

    def __init__(
        self,
        headless: bool = BROWSER_HEADLESS,
        session_path: Path | None = None,
        timeout: int = BROWSER_TIMEOUT,
        save_artifacts: bool = False,
        perplexity_mode: str = "council",
    ):
        self.headless = headless
        self.session_path = session_path or BROWSER_SESSION_PATH
        self.timeout = timeout
        self.save_artifacts = save_artifacts
        self.perplexity_mode = perplexity_mode
        self.selectors = _load_selectors()
        self.playwright = None
        self.context = None
        self.page = None
        self._artifact_count = 0
        self._artifact_dir: Path | None = None

    def _init_artifact_dir(self, query: str) -> None:
        """Create run artifact directory based on timestamp + query slug."""
        slug = re.sub(r"[^a-z0-9]+", "-", query[:40].lower()).strip("-") or "query"
        run_id = f"{time.strftime('%Y%m%d_%H%M')}_{slug[:30]}"
        self._artifact_dir = Path("~/.claude/council-logs/runs").expanduser() / run_id
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        self._artifact_count = 0

    async def _save_artifact(self, page, label: str) -> None:
        """Capture screenshot + HTML as forensic artifacts. Non-fatal, capped at 10."""
        if not self.save_artifacts or not self._artifact_dir:
            return
        if self._artifact_count >= 10:
            return
        try:
            self._artifact_count += 1
            # Screenshot
            jpg_path = self._artifact_dir / f"{label}.jpg"
            screenshot = await page.screenshot(type="jpeg", quality=80)
            jpg_path.write_bytes(screenshot)
            # Page HTML
            html_path = self._artifact_dir / f"{label}.html"
            html = await page.content()
            html_path.write_text(html, encoding="utf-8")
            _log(f"Artifact saved: {self._artifact_dir.name}/{label} (screenshot + html)")
        except Exception as e:
            _log(f"WARNING: Failed to save artifact '{label}': {e}")

    async def start(self) -> None:
        """Launch Chrome with persistent context (uses system Chrome to pass Cloudflare)."""
        from playwright.async_api import async_playwright

        self.playwright = await async_playwright().start()

        # Ensure user data dir exists
        BROWSER_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_USER_DATA_DIR),
            channel="chrome",  # Use system Chrome binary (passes Cloudflare)
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            viewport={"width": 1280, "height": 900},
        )

        # Inject session cookies if available
        if self.session_path.exists():
            await self._load_session()

    async def _load_session(self) -> None:
        """Load session from playwright-session.json + playwright-localstorage.json."""
        try:
            data = json.loads(self.session_path.read_text(encoding="utf-8"))

            # Playwright-native format: list of cookie dicts
            if isinstance(data, list):
                await self.context.add_cookies(data)
                _log(f"Loaded {len(data)} cookies from {self.session_path.name}")

            # Legacy format from /cache-perplexity-session: {cookies: "str", localStorage: {}}
            elif isinstance(data, dict):
                cookies = self._parse_cookie_string(data.get("cookies", ""))
                if cookies:
                    await self.context.add_cookies(cookies)
                    _log(f"Converted and loaded {len(cookies)} cookies from legacy format")

        except Exception as e:
            _log(f"WARNING: Failed to load cookies: {e}")

        # Inject localStorage from companion file (critical for pplx-next-auth-session)
        ls_path = self.session_path.parent / "playwright-localstorage.json"
        if ls_path.exists():
            await self._inject_local_storage(ls_path)

    async def _inject_local_storage(self, ls_path: Path) -> None:
        """Inject localStorage items into Perplexity origin."""
        try:
            local_storage = json.loads(ls_path.read_text(encoding="utf-8"))
            if not local_storage:
                return
            page = await self.context.new_page()
            await page.goto("https://www.perplexity.ai/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            for key, value in local_storage.items():
                await page.evaluate(
                    f"localStorage.setItem({json.dumps(key)}, {json.dumps(value)})"
                )
            await page.close()
            _log(f"Injected {len(local_storage)} localStorage items")
        except Exception as e:
            _log(f"WARNING: Failed to inject localStorage: {e}")

    @staticmethod
    def _parse_cookie_string(cookie_str: str) -> list[dict]:
        """Parse semicolon-delimited cookie string into Playwright cookie dicts."""
        if not cookie_str:
            return []
        cookies = []
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": ".perplexity.ai",
                "path": "/",
            })
        return cookies

    async def validate_session(self) -> bool:
        """Check if we're logged in to Perplexity."""
        page = await self.context.new_page()
        try:
            await page.goto("https://www.perplexity.ai/", wait_until="domcontentloaded", timeout=30000)
            # Wait a moment for JS to hydrate
            await page.wait_for_timeout(2000)

            textarea = self.selectors.get("textarea", "#ask-input")
            try:
                await page.wait_for_selector(textarea, timeout=10000)
                _log("Session valid: found input element")
                return True
            except Exception:
                _log("Session invalid: input element not found (not logged in?)")
                await self._save_artifact(page, "validate_failure")
                return False
        finally:
            await page.close()

    async def activate_mode(self, page) -> bool:
        """Activate the configured Perplexity mode via slash command.

        Supports: /council (multi-model) and /research (deep research).
        """
        slash_cmd = f"/{self.perplexity_mode}"
        _log(f"Activating {self.perplexity_mode} mode via {slash_cmd}...")
        textarea = self.selectors.get("textarea", "#ask-input")

        # Focus the input
        try:
            await page.click(textarea)
            await page.wait_for_timeout(500)
        except Exception as e:
            _log(f"Failed to focus input: {e}")
            return False

        # Type the slash command
        await page.keyboard.type(slash_cmd, delay=BROWSER_TYPE_DELAY)
        await page.wait_for_timeout(1500)  # Wait for command palette

        # Press Enter to activate
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1500)  # Wait for activation

        # Verify activation based on mode
        if self.perplexity_mode == "council":
            return await self._verify_council_activation(page)
        elif self.perplexity_mode == "research":
            return await self._verify_research_activation(page)
        else:
            _log(f"Unknown mode '{self.perplexity_mode}', proceeding optimistically")
            return True

    async def _verify_council_activation(self, page) -> bool:
        """Verify council mode activated (look for '3 models' indicator)."""
        try:
            three_models = self.selectors.get("threeModelsDropdown", "button[aria-label='3 models']")
            await page.wait_for_selector(three_models, timeout=5000)
            _log("Council mode activated (found '3 models' indicator)")
            return True
        except Exception:
            try:
                council_text = await page.evaluate(
                    "!!document.querySelector('button')?.textContent?.includes('Model council')"
                )
                if council_text:
                    _log("Council mode activated (found 'Model council' text)")
                    return True
            except Exception:
                pass
            _log("WARNING: Could not verify council activation, proceeding anyway")
            return True  # Proceed optimistically

    async def _verify_research_activation(self, page) -> bool:
        """Verify research mode activated (look for research indicators)."""
        try:
            # Research mode shows a "Research" or "Deep Research" indicator
            found = await page.evaluate("""() => {
                const buttons = document.querySelectorAll('button, [role="button"], div[data-state]');
                for (const b of buttons) {
                    const text = (b.textContent || '').trim().toLowerCase();
                    if (text.includes('research') || text.includes('deep research')) return true;
                }
                return false;
            }""")
            if found:
                _log("Research mode activated (found research indicator)")
                return True
        except Exception:
            pass
        _log("WARNING: Could not verify research activation, proceeding anyway")
        return True  # Proceed optimistically

    async def activate_council(self, page) -> bool:
        """Activate council mode. Delegates to activate_mode()."""
        return await self.activate_mode(page)

    async def submit_query(self, page, query: str) -> None:
        """Type and submit the query."""
        textarea = self.selectors.get("textarea", "#ask-input")

        # Try native setter first (preserves newlines), fall back to page.fill()
        try:
            filled = await page.evaluate(
                """([sel, text]) => {
                    const el = document.querySelector(sel);
                    if (!el) return false;
                    // Try textarea/input native setter (React-compatible)
                    const proto = el.tagName === 'TEXTAREA'
                        ? HTMLTextAreaElement.prototype
                        : HTMLInputElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                    if (setter) {
                        setter.call(el, text);
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        return true;
                    }
                    return false;
                }""",
                [textarea, query],
            )
            if not filled:
                raise ValueError("Native setter failed")
        except Exception:
            _log("Native setter unavailable, using page.fill()")
            await page.fill(textarea, query)
        await page.wait_for_timeout(500)

        # Submit via Enter
        await page.keyboard.press("Enter")
        _log(f"Query submitted ({len(query)} chars)")

        # Wait for response to start appearing
        response_sel = self.selectors.get("responseContainer", ".prose")
        try:
            await page.wait_for_selector(response_sel, timeout=30000)
            _log("Response generation started")
        except Exception:
            _log("WARNING: Response container not detected within 30s")

    async def _analyze_screenshot(self, screenshot_bytes: bytes) -> dict:
        """Send screenshot to Claude Haiku for page state analysis.

        Returns dict with:
            models_completed: int (0-3)
            synthesis_visible: bool
            loading_active: bool
            page_state: "loading" | "generating" | "synthesizing" | "complete" | "error"
            error_text: str (empty if no error)
        """
        import anthropic

        b64 = base64.b64encode(screenshot_bytes).decode()

        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

        response = client.messages.create(
            model=VISION_MODEL,
            max_tokens=VISION_MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Analyze this Perplexity AI council query page screenshot. "
                            "Return ONLY valid JSON (no markdown, no explanation):\n"
                            '{"models_completed":<0-3>,"synthesis_visible":<bool>,'
                            '"loading_active":<bool>,"page_state":"<state>",'
                            '"error_text":"<text or empty>"}\n\n'
                            "IMPORTANT: Perplexity council has TWO phases:\n"
                            "Phase 1: Individual model responses (shown as expandable rows with checkmarks)\n"
                            "Phase 2: A SEPARATE synthesis/summary section BELOW the model rows. "
                            "This is the main response text that streams AFTER all models finish.\n\n"
                            "page_state values:\n"
                            '- "loading": page is loading, no model responses yet\n'
                            '- "generating": models are actively generating (streaming text, spinners, pulsing)\n'
                            '- "synthesizing": all 3 models have checkmarks BUT the synthesis text below '
                            "is still streaming (text is appearing, cursor/caret visible, content growing)\n"
                            '- "complete": synthesis text is FULLY rendered AND sources/citations section '
                            "is visible at the very bottom of the page. No streaming, no pulsing, no loading.\n"
                            '- "error": error message, red/orange banner, or "try again" button visible\n\n'
                            "CRITICAL: Do NOT report 'complete' just because 3 model checkmarks are visible. "
                            "The synthesis section below must ALSO be fully done with sources visible at bottom."
                        ),
                    },
                ],
            }],
            timeout=15,
        )

        text = response.content[0].text.strip()
        # Strip markdown code fences if Haiku wraps in ```json
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        return json.loads(text)

    async def wait_for_completion(self, page, timeout: int | None = None) -> bool:
        """Wait for all model responses and synthesis to complete.

        Primary: Vision-based detection via Haiku screenshot analysis.
        Fallback: CSS selector + stability polling (when ANTHROPIC_API_KEY not set).
        """
        timeout = timeout or self.timeout
        start = time.time()

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        use_vision = bool(api_key) and VISION_ENABLED

        if use_vision:
            return await self._wait_vision(page, timeout, start)
        else:
            _log("Vision monitoring unavailable (no ANTHROPIC_API_KEY), using CSS fallback")
            return await self._wait_css_fallback(page, timeout, start)

    async def _wait_vision(self, page, timeout: int, start: float) -> bool:
        """Vision-based completion detection using Haiku screenshots.

        Enforces state machine: generating -> synthesizing -> complete.
        Requires seeing 'synthesizing' before trusting 'complete', and
        requires 2 consecutive 'complete' polls for confidence.
        """
        poll_interval = VISION_POLL_INTERVAL_MODELS
        all_models_done = False
        seen_synthesizing = False
        consecutive_complete = 0

        _log("Vision monitoring: polling with Haiku screenshot analysis...")

        while (time.time() - start) * 1000 < timeout:
            try:
                screenshot = await page.screenshot(type="jpeg", quality=VISION_JPEG_QUALITY)
                state = await self._analyze_screenshot(screenshot)

                models_done = state.get("models_completed", 0)
                page_state = state.get("page_state", "unknown")
                _log(f"  Vision: {models_done}/3 models, state={page_state}")

                if page_state == "error":
                    error = state.get("error_text", "unknown error")
                    _log(f"Vision: error detected: {error}")
                    return False

                if page_state == "synthesizing":
                    seen_synthesizing = True
                    consecutive_complete = 0
                    if not all_models_done:
                        all_models_done = True
                        poll_interval = VISION_POLL_INTERVAL_SYNTHESIS
                        _log("  Synthesis phase detected, switching to faster polling")

                if page_state == "complete":
                    if not seen_synthesizing:
                        # Haiku likely confused "3 checkmarks" with "complete"
                        # Force at least one synthesizing cycle
                        _log("  Vision reported 'complete' but no synthesizing seen yet — treating as synthesizing")
                        seen_synthesizing = True
                        if not all_models_done:
                            all_models_done = True
                            poll_interval = VISION_POLL_INTERVAL_SYNTHESIS
                    else:
                        consecutive_complete += 1
                        if consecutive_complete >= 2:
                            _log(f"Vision: page complete (confirmed 2x) ({time.time() - start:.1f}s)")
                            return True
                        _log(f"  Vision: complete (need 1 more confirmation)")
                else:
                    consecutive_complete = 0

                # Switch to faster polling once all models done
                if models_done >= 3 and not all_models_done:
                    all_models_done = True
                    poll_interval = VISION_POLL_INTERVAL_SYNTHESIS
                    _log("  All models done, switching to faster polling")

            except json.JSONDecodeError as e:
                _log(f"  Vision: failed to parse Haiku response: {e}")
            except Exception as e:
                _log(f"  Vision: analysis error: {e}")

            await asyncio.sleep(poll_interval)

        _log(f"Vision: timed out after {time.time() - start:.1f}s")
        return False

    async def _wait_css_fallback(self, page, timeout: int, start: float) -> bool:
        """CSS selector + stability fallback (original implementation)."""
        # Phase A: Wait for model completion indicators
        completion_sel = self.selectors.get(
            "councilCompletedIndicator", "[class*='Completed'], svg[class*='check']"
        )
        _log("Phase A: Waiting for model completions...")

        phase_a_timeout = min(90000, timeout)
        try:
            await page.wait_for_function(
                f"""() => {{
                    const indicators = document.querySelectorAll("{completion_sel}");
                    return indicators.length >= 3;
                }}""",
                timeout=phase_a_timeout,
            )
            _log(f"Phase A complete: all models finished ({time.time() - start:.1f}s)")
        except Exception:
            try:
                count = await page.evaluate(
                    f'document.querySelectorAll("{completion_sel}").length'
                )
                _log(f"Phase A timeout: {count}/3 models completed, proceeding to Phase B")
            except Exception:
                _log("Phase A timeout: couldn't check completion count, proceeding")

        # Phase B: Wait for synthesis stability
        synthesis_sel = self.selectors.get("councilSynthesis", ".prose:first-of-type")
        _log("Phase B: Waiting for synthesis stability...")

        remaining = timeout - int((time.time() - start) * 1000)
        if remaining < 5000:
            _log("WARNING: Very little time remaining for stability check")
            remaining = 10000

        last_content = ""
        stable_since = time.time()
        poll_interval = BROWSER_POLL_INTERVAL / 1000
        stable_threshold = BROWSER_STABLE_MS / 1000

        while (time.time() - start) * 1000 < timeout:
            try:
                current = await page.evaluate(
                    f'document.querySelector("{synthesis_sel}")?.textContent || ""'
                )
                if current and current == last_content:
                    if time.time() - stable_since >= stable_threshold:
                        _log(f"Phase B complete: synthesis stable for {stable_threshold}s ({time.time() - start:.1f}s total)")
                        return True
                else:
                    last_content = current
                    stable_since = time.time()
            except Exception:
                pass

            await asyncio.sleep(poll_interval)

        _log(f"Completion wait timed out after {time.time() - start:.1f}s")
        return False

    async def _find_model_cards(self, page) -> list:
        """Find the 3 model card elements using JS evaluation (more reliable than CSS selectors).

        Strategy 1: querySelectorAll for model card containers (overflow-hidden rounded-xl)
        Strategy 2: Text-walk heuristic — find model name text, walk up to card boundary.
        Both run in page JS context to avoid Playwright CSS selector quirks.
        """
        # Strategy 1: direct querySelectorAll in page JS
        card_count = await page.evaluate("""() => {
            return document.querySelectorAll(
                'div[class*="overflow-hidden"][class*="rounded-xl"][class*="border-subtler"]'
            ).length;
        }""")
        _log(f"Model card JS querySelectorAll count: {card_count}")

        if card_count >= 2:
            # Use Playwright locator which supports auto-waiting
            cards = await page.query_selector_all(
                'div[class*="overflow-hidden"][class*="rounded-xl"][class*="border-subtler"]'
            )
            if len(cards) >= 2:
                _log(f"Found {len(cards)} model cards via primary selector")
                return cards

        # If CSS selector didn't work but JS found them, use evaluate_handle
        if card_count >= 2:
            handles = []
            for i in range(card_count):
                h = await page.evaluate_handle(
                    f"""() => document.querySelectorAll(
                        'div[class*="overflow-hidden"][class*="rounded-xl"][class*="border-subtler"]'
                    )[{i}]"""
                )
                handles.append(h.as_element())
            handles = [h for h in handles if h is not None]
            if len(handles) >= 2:
                _log(f"Found {len(handles)} model cards via evaluate_handle")
                return handles

        # Strategy 2: heuristic — walk text nodes for model names, find card boundaries
        model_names = ["GPT", "Claude", "Gemini"]
        card_indices = await page.evaluate("""(modelNames) => {
            const cards = [];
            const allDivs = document.querySelectorAll('div');
            // Build index of divs with class containing 'rounded-xl'
            const roundedDivs = [];
            allDivs.forEach((div, idx) => {
                const cls = div.className?.toString() || '';
                if (cls.includes('rounded-xl') && cls.includes('border')) {
                    const text = div.textContent || '';
                    if (text.length > 20 && text.length < 50000) {
                        roundedDivs.push({ idx, text: text.substring(0, 300), cls: cls.substring(0, 200) });
                    }
                }
            });
            // Filter to those containing model name text
            for (const name of modelNames) {
                const match = roundedDivs.find(d =>
                    d.text.includes(name) && !cards.some(c => c.idx === d.idx)
                );
                if (match) cards.push(match);
            }
            return cards;
        }""", model_names)

        if card_indices and len(card_indices) >= 2:
            _log(f"Found {len(card_indices)} model cards via heuristic (names: {[c.get('text', '')[:30] for c in card_indices]})")
            # Get element handles by re-querying
            handles = []
            for card_info in card_indices:
                cls_prefix = card_info.get("cls", "")[:40]
                if cls_prefix:
                    h = await page.evaluate_handle(
                        """(clsPrefix) => {
                            const divs = document.querySelectorAll('div');
                            for (const d of divs) {
                                if ((d.className?.toString() || '').startsWith(clsPrefix)) {
                                    return d;
                                }
                            }
                            return null;
                        }""",
                        cls_prefix,
                    )
                    el = h.as_element()
                    if el:
                        handles.append(el)
            if handles:
                return handles

        # 0 model cards is normal — Perplexity may use single-model mode for simpler queries
        _log(f"No model cards found (council may have used single-model mode)")
        return []

    async def _extract_model_name(self, card) -> str:
        """Extract the clean model name from a model card element."""
        name = await card.evaluate("""el => {
            // Look for the model name text element (font-medium, text-xs)
            const nameEl = el.querySelector(
                'div[class*="font-medium"][class*="text-xs"][class*="text-foreground"]'
            );
            if (nameEl) return nameEl.textContent.trim();
            // Fallback: first short text child
            const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                const t = walker.currentNode.textContent.trim();
                if (t.length > 2 && t.length < 60) return t;
            }
            return '';
        }""")
        # Clean up: strip "Thinking", "X steps", etc. suffixes
        if name:
            for suffix in [" Thinking", " Writing", " Searching"]:
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
        return (name or "Unknown Model")[:50]

    async def _extract_panel_response(self, page) -> str:
        """Extract the response text from the currently active model panel."""
        # The panel slides in with data-state="active" and contains .prose content
        panel_prose_sel = self.selectors.get(
            "councilModelPanelProse", "div[data-state='active'] .prose"
        )
        try:
            text = await page.evaluate(
                f'document.querySelector("{panel_prose_sel}")?.innerText || ""'
            )
            if text:
                return text
        except Exception:
            pass

        # Fallback: data-state="active" with h-full class, extract all text
        panel_sel = self.selectors.get(
            "councilModelPanel", "div[data-state='active'].h-full"
        )
        try:
            text = await page.evaluate(
                f'document.querySelector("{panel_sel}")?.innerText || ""'
            )
            return text or ""
        except Exception:
            return ""

    async def extract_results(self, page) -> dict:
        """Extract synthesis and per-model responses from the page.

        DOM structure (validated 2026-02-16):
          - Synthesis: first div.prose.inline element
          - Model cards: 3x div.overflow-hidden.rounded-xl.border-subtler
            - Each has a cursor-pointer clickable header
            - Model name in div.font-medium.text-xs.text-foreground
            - Clicking opens a data-state='active' slide-out panel on right
        """
        results = {
            "synthesis": "",
            "models": {},
            "citations": [],
        }

        # Extract synthesis text
        synthesis_sel = self.selectors.get("councilSynthesis", "div.prose.inline")
        synthesis_fallback = self.selectors.get("councilSynthesisFallback", ".prose:first-of-type")
        try:
            text = await page.evaluate(
                f'document.querySelector("{synthesis_sel}")?.innerText || ""'
            )
            if not text:
                text = await page.evaluate(
                    f'document.querySelector("{synthesis_fallback}")?.innerText || ""'
                )
            results["synthesis"] = text
            _log(f"Extracted synthesis: {len(results['synthesis'])} chars")
        except Exception as e:
            _log(f"WARNING: Failed to extract synthesis: {e}")

        # Find model cards
        cards = await self._find_model_cards(page)
        _log(f"Found {len(cards)} model cards")

        # Extract per-model responses by clicking each card
        for i, card in enumerate(cards):
            try:
                model_name = await self._extract_model_name(card)

                # Click the card header to expand the model panel
                clickable = await card.query_selector(
                    self.selectors.get(
                        "councilModelClickableRow",
                        "div[class*='cursor-pointer'][class*='p-3']",
                    )
                )
                target = clickable or card
                await target.click()
                await page.wait_for_timeout(1500)

                # Extract the response from the active panel
                response_text = await self._extract_panel_response(page)

                if response_text:
                    results["models"][model_name] = {"response": response_text}
                    _log(f"  Model '{model_name}': {len(response_text)} chars")
                else:
                    _log(f"  Model '{model_name}': no response text in panel")
                    await self._save_artifact(page, f"model_{i}_empty_panel")

                # Close the panel (Escape or close button)
                close_sel = self.selectors.get("councilPanelClose", "button[aria-label='Close']")
                try:
                    close_btn = await page.query_selector(close_sel)
                    if close_btn:
                        await close_btn.click()
                        await page.wait_for_timeout(500)
                    else:
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(500)
                except Exception:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)

            except Exception as e:
                _log(f"  WARNING: Failed to extract model {i}: {e}")
                await self._save_artifact(page, f"model_{i}_error")

        # Extract citations
        try:
            citations = await page.evaluate("""() => {
                const links = document.querySelectorAll('.prose a[href]');
                return Array.from(links).map(a => ({
                    url: a.href,
                    text: a.textContent?.trim() || ''
                })).filter(c => c.url && !c.url.startsWith('javascript:'));
            }""")
            results["citations"] = citations[:50]  # Cap at 50
            _log(f"Extracted {len(results['citations'])} citations")
        except Exception as e:
            _log(f"WARNING: Failed to extract citations: {e}")

        return results

    async def run(self, query: str) -> dict:
        """Full pipeline: start -> validate -> council -> query -> wait -> extract."""
        start_time = time.time()
        self._init_artifact_dir(query)

        try:
            _log("Starting Playwright browser...")
            await self.start()

            _log("Validating session...")
            if not await self.validate_session():
                return {
                    "error": "Session expired or not logged in. Run: python council_browser.py --save-session",
                    "step": "validate",
                }

            # Open a new page for the query
            page = await self.context.new_page()

            try:
                _log("Navigating to Perplexity...")
                await page.goto(
                    "https://www.perplexity.ai/",
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await page.wait_for_timeout(2000)

                _log(f"Activating {self.perplexity_mode} mode...")
                if not await self.activate_mode(page):
                    await self._save_artifact(page, "activate_failure")
                    return {"error": f"Failed to activate {self.perplexity_mode} mode", "step": "activate"}

                _log(f"Submitting query: {query[:80]}...")
                await self.submit_query(page, query)

                _log("Waiting for completion...")
                completed = await self.wait_for_completion(page, self.timeout)
                if not completed:
                    _log("WARNING: Timed out waiting for completion, extracting partial results")
                    await self._save_artifact(page, "timeout")

                _log("Extracting results...")
                results = await self.extract_results(page)

                elapsed = int((time.time() - start_time) * 1000)
                results["query"] = query
                results["mode"] = "browser"
                results["completed"] = completed
                results["execution_time_ms"] = elapsed
                _log(f"Done in {elapsed/1000:.1f}s")

                return results

            finally:
                await page.close()

        except Exception as e:
            # Try to capture artifact on unhandled exception
            if self.context:
                try:
                    pages = self.context.pages
                    if pages:
                        await self._save_artifact(pages[-1], "unhandled_exception")
                except Exception:
                    pass
            return {
                "error": str(e),
                "step": "unknown",
                "execution_time_ms": int((time.time() - start_time) * 1000),
            }

    async def save_session(self) -> None:
        """Save current browser session for future headless use."""
        if not self.context:
            _log("ERROR: No browser context to save from")
            return

        cookies = await self.context.cookies()

        # Save in Playwright-native format
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_path.write_text(
            json.dumps(cookies, indent=2, default=str),
            encoding="utf-8",
        )
        _log(f"Saved {len(cookies)} cookies to {self.session_path}")

    async def stop(self) -> None:
        """Close browser and Playwright."""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Perplexity council browser automation")
    parser.add_argument("query", nargs="?", help="The question to ask the council")
    parser.add_argument("--headful", action="store_true", help="Run with visible browser")
    parser.add_argument("--save-session", action="store_true", help="Login and save session")
    parser.add_argument("--timeout", type=int, default=BROWSER_TIMEOUT, help="Timeout in ms")
    parser.add_argument("--session-path", type=str, help="Path to session file")
    parser.add_argument("--save-artifacts", action="store_true", default=False,
        help="Save screenshots/HTML on failure (default: True when --opus-synthesis)")

    args = parser.parse_args()

    session_path = Path(args.session_path) if args.session_path else None
    council = PerplexityCouncil(
        headless=not args.headful,
        session_path=session_path,
        timeout=args.timeout,
        save_artifacts=args.save_artifacts,
    )

    if args.save_session:
        await council.start()
        _log("Browser opened. Log in to Perplexity in the browser window.")
        _log("Press Enter here when done...")
        # Use asyncio-compatible input
        await asyncio.get_event_loop().run_in_executor(None, input)
        await council.save_session()
        await council.stop()
        _log("Session saved. You can now run queries in headless mode.")
        return

    if not args.query:
        parser.error("Query is required unless using --save-session")

    try:
        result = await council.run(args.query)
        print(json.dumps(result, indent=2, default=str))
    finally:
        await council.stop()


if __name__ == "__main__":
    asyncio.run(main())
