"""Show token usage and cost from cached council results."""
import json
from pathlib import Path

cache = Path.home() / ".claude" / "council-cache" / "council_latest.json"
data = json.loads(cache.read_text(encoding="utf-8"))

print("=== TOKEN USAGE & COST ===")
print(f"Timestamp: {data['timestamp']}")
print(f"Execution time: {data['execution_time_ms']}ms ({data['execution_time_ms']/1000:.1f}s)")
print()

print("--- Per-Model (Perplexity API) ---")
total_in = 0
total_out = 0
for label, m in data["models"].items():
    print(f"  {label}:")
    print(f"    Input tokens:  {m['tokens_in']}")
    print(f"    Output tokens: {m['tokens_out']}")
    print(f"    Cost:          ${m['cost']:.6f}")
    total_in += m["tokens_in"]
    total_out += m["tokens_out"]
    if m.get("error"):
        print(f"    ERROR: {m['error'][:80]}")
    citations = m.get("citations", [])
    print(f"    Citations:     {len(citations)}")
    resp = m.get("response") or ""
    print(f"    Response len:  {len(resp)} chars")

print(f"\n  Perplexity totals: {total_in} in / {total_out} out")

print()
s = data["synthesis"]
print("--- Synthesis (Opus 4.6) ---")
print(f"  Model:           {s.get('model')}")
print(f"  Thinking tokens: {s.get('thinking_tokens', 0)}")
resp_text = s.get("response", "") or ""
print(f"  Response length: {len(resp_text)} chars")
print(f"  Cost:            ${s.get('cost', 0):.6f}")
print(f"  Confidence:      {s.get('confidence', 'N/A')}")
print(f"  Agreements:      {len(s.get('agreements', []))}")
print(f"  Disagreements:   {len(s.get('disagreements', []))}")
print(f"  Insights:        {len(s.get('unique_insights', []))}")
print(f"  Actions:         {len(s.get('recommended_actions', []))}")
print(f"  Risks:           {len(s.get('risks', []))}")

print(f"\n=== TOTAL COST: ${data['total_cost']:.4f} ===")

# Context tokens estimate (what Claude would read)
synth_only = json.dumps(s.get("parsed", s), indent=2)
print(f"\n=== CONTEXT TOKEN ESTIMATE ===")
print(f"  Synthesis-only output: ~{len(synth_only.split())  } words / ~{len(synth_only) // 4} tokens")
print(f"  Full cache file:      ~{len(json.dumps(data).split())} words / ~{len(json.dumps(data)) // 4} tokens")
