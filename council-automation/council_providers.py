"""Direct provider adapters for Tier 3 fallback.

When Perplexity Responses API and Sonar Pro are both down, these adapters
call OpenAI, Anthropic, and Google APIs directly to maintain multi-model
diversity. Loses web search/citations but preserves the council pattern.

Each adapter normalizes responses to the standard council result schema:
{model, label, response, tokens_in, tokens_out, cost, citations, error}
"""

import asyncio
import os
from typing import Optional

from council_config import (
    DIRECT_MODEL_MAP,
    DIRECT_PRICING,
    DIRECT_TIMEOUT,
    MAX_OUTPUT_TOKENS,
    MODEL_INSTRUCTIONS,
    PROVIDER_API_KEYS,
)


def _compute_cost(model_id: str, tokens_in: int, tokens_out: int) -> float:
    """Compute cost from token counts using published pricing."""
    pricing = DIRECT_PRICING.get(model_id, {})
    input_price = pricing.get("input", 0)
    output_price = pricing.get("output", 0)
    return round((tokens_in * input_price + tokens_out * output_price) / 1_000_000, 6)


def _make_error_result(model_cfg: dict, error: str) -> dict:
    """Create a standardized error result dict."""
    return {
        "model": model_cfg["id"],
        "label": f"{model_cfg['label']} (direct)",
        "response": None,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost": 0,
        "citations": [],
        "search_results": [],
        "web_search_used": False,
        "error": error,
    }


async def _query_openai(model_cfg: dict, full_input: str, timeout: int) -> dict:
    """Query OpenAI directly via AsyncOpenAI."""
    import sys

    api_key = os.environ.get(PROVIDER_API_KEYS["openai"])
    if not api_key:
        return _make_error_result(model_cfg, f"{PROVIDER_API_KEYS['openai']} not set")

    from openai import AsyncOpenAI

    native_model = DIRECT_MODEL_MAP.get(model_cfg["id"], model_cfg["id"])
    client = AsyncOpenAI(api_key=api_key)

    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=native_model,
                messages=[
                    {"role": "system", "content": MODEL_INSTRUCTIONS},
                    {"role": "user", "content": full_input},
                ],
                max_completion_tokens=MAX_OUTPUT_TOKENS,
            ),
            timeout=timeout,
        )

        text = response.choices[0].message.content or ""
        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0
        cost = _compute_cost(model_cfg["id"], tokens_in, tokens_out)

        print(f"  [{model_cfg['label']} direct] OK: {len(text)} chars", file=sys.stderr)
        return {
            "model": model_cfg["id"],
            "label": f"{model_cfg['label']} (direct)",
            "response": text,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost": cost,
            "citations": [],
            "search_results": [],
            "web_search_used": False,
            "error": None,
        }
    except asyncio.TimeoutError:
        return _make_error_result(model_cfg, f"Timeout after {timeout}s")
    except Exception as e:
        return _make_error_result(model_cfg, str(e))


async def _query_anthropic(model_cfg: dict, full_input: str, timeout: int) -> dict:
    """Query Anthropic directly via AsyncAnthropic."""
    import sys

    api_key = os.environ.get(PROVIDER_API_KEYS["anthropic"])
    if not api_key:
        return _make_error_result(model_cfg, f"{PROVIDER_API_KEYS['anthropic']} not set")

    from anthropic import AsyncAnthropic

    native_model = DIRECT_MODEL_MAP.get(model_cfg["id"], model_cfg["id"])
    client = AsyncAnthropic(api_key=api_key)

    try:
        response = await asyncio.wait_for(
            client.messages.create(
                model=native_model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=MODEL_INSTRUCTIONS,
                messages=[{"role": "user", "content": full_input}],
            ),
            timeout=timeout,
        )

        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        tokens_in = response.usage.input_tokens if response.usage else 0
        tokens_out = response.usage.output_tokens if response.usage else 0
        cost = _compute_cost(model_cfg["id"], tokens_in, tokens_out)

        print(f"  [{model_cfg['label']} direct] OK: {len(text)} chars", file=sys.stderr)
        return {
            "model": model_cfg["id"],
            "label": f"{model_cfg['label']} (direct)",
            "response": text,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost": cost,
            "citations": [],
            "search_results": [],
            "web_search_used": False,
            "error": None,
        }
    except asyncio.TimeoutError:
        return _make_error_result(model_cfg, f"Timeout after {timeout}s")
    except Exception as e:
        return _make_error_result(model_cfg, str(e))


async def _query_google(model_cfg: dict, full_input: str, timeout: int) -> dict:
    """Query Google Generative AI directly."""
    import sys

    api_key = os.environ.get(PROVIDER_API_KEYS["google"])
    if not api_key:
        return _make_error_result(model_cfg, f"{PROVIDER_API_KEYS['google']} not set — skipping")

    import google.generativeai as genai

    native_model = DIRECT_MODEL_MAP.get(model_cfg["id"], model_cfg["id"])
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        native_model,
        system_instruction=MODEL_INSTRUCTIONS,
    )

    try:
        response = await asyncio.wait_for(
            model.generate_content_async(
                full_input,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=MAX_OUTPUT_TOKENS,
                ),
            ),
            timeout=timeout,
        )

        text = response.text or ""
        tokens_in = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        tokens_out = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        cost = _compute_cost(model_cfg["id"], tokens_in, tokens_out)

        print(f"  [{model_cfg['label']} direct] OK: {len(text)} chars", file=sys.stderr)
        return {
            "model": model_cfg["id"],
            "label": f"{model_cfg['label']} (direct)",
            "response": text,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost": cost,
            "citations": [],
            "search_results": [],
            "web_search_used": False,
            "error": None,
        }
    except asyncio.TimeoutError:
        return _make_error_result(model_cfg, f"Timeout after {timeout}s")
    except Exception as e:
        return _make_error_result(model_cfg, str(e))


# Provider → adapter function mapping
_ADAPTERS = {
    "openai": _query_openai,
    "anthropic": _query_anthropic,
    "google": _query_google,
}


def get_adapter(provider: str):
    """Get the adapter function for a provider. Returns None if unknown."""
    return _ADAPTERS.get(provider)


async def query_direct_providers(
    models: list[dict], full_input: str, timeout: int = DIRECT_TIMEOUT,
) -> list[dict]:
    """Query all available direct providers in parallel.

    Skips providers whose API keys are not set (returns error dict, non-fatal).
    """
    import sys

    print("  Querying direct providers (Tier 3)...", file=sys.stderr)
    tasks = []
    for model in models:
        provider = model.get("provider")
        adapter = get_adapter(provider)
        if adapter:
            tasks.append(adapter(model, full_input, timeout))
        else:
            tasks.append(asyncio.coroutine(lambda m=model: _make_error_result(m, f"Unknown provider: {m.get('provider')}"))())

    if not tasks:
        return [{"error": "No direct provider adapters available", "model": "none",
                 "label": "none", "response": None, "tokens_in": 0, "tokens_out": 0,
                 "cost": 0, "citations": [], "search_results": [], "web_search_used": False}]

    raw = await asyncio.gather(*tasks, return_exceptions=True)
    results = []
    for r in raw:
        if isinstance(r, Exception):
            results.append({"model": "unknown", "label": "unknown (direct)",
                            "response": None, "error": str(r), "tokens_in": 0,
                            "tokens_out": 0, "cost": 0, "citations": [],
                            "search_results": [], "web_search_used": False})
        else:
            results.append(r)

    ok = sum(1 for r in results if r.get("response"))
    print(f"  Direct providers: {ok}/{len(results)} succeeded", file=sys.stderr)
    return results
