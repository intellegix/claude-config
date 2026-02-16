"""Analyze council run logs for operational metrics.

Reads runs.jsonl and computes aggregate stats: degradation ratio,
avg cost, per-mode breakdown, error rate, fallback frequency.

Usage:
    python council_metrics.py          # Markdown table
    python council_metrics.py --json   # JSON output (for MCP tool)
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


LOG_PATH = Path("~/.claude/council-logs/runs.jsonl").expanduser()


def load_runs(log_path: Path | None = None) -> list[dict]:
    """Read runs.jsonl, skip malformed lines."""
    path = log_path or LOG_PATH
    if not path.exists():
        return []
    runs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            runs.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return runs


def compute_metrics(runs: list[dict]) -> dict:
    """Compute aggregate metrics from run log entries."""
    if not runs:
        return {"total_runs": 0, "message": "No runs recorded yet."}

    total = len(runs)
    degraded_count = sum(1 for r in runs if r.get("degraded"))
    error_count = sum(1 for r in runs if r.get("error"))
    costs = [r.get("cost", 0) for r in runs if r.get("cost") is not None]
    times = [r.get("execution_time_ms", 0) for r in runs if r.get("execution_time_ms")]

    # Per-mode breakdown
    by_mode: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "degraded": 0, "errors": 0, "total_cost": 0.0, "total_time_ms": 0,
    })
    for r in runs:
        mode = r.get("mode", "unknown")
        by_mode[mode]["count"] += 1
        if r.get("degraded"):
            by_mode[mode]["degraded"] += 1
        if r.get("error"):
            by_mode[mode]["errors"] += 1
        by_mode[mode]["total_cost"] += r.get("cost", 0) or 0
        by_mode[mode]["total_time_ms"] += r.get("execution_time_ms", 0) or 0

    # Compute averages per mode
    for mode, stats in by_mode.items():
        n = stats["count"]
        stats["avg_cost"] = round(stats["total_cost"] / n, 4) if n else 0
        stats["avg_time_ms"] = round(stats["total_time_ms"] / n) if n else 0
        stats["degradation_ratio"] = round(stats["degraded"] / n, 3) if n else 0

    # Fallback frequency
    fallback_freq: dict[str, int] = defaultdict(int)
    for r in runs:
        fc = r.get("fallback_count", 0)
        if fc > 0:
            fallback_freq["runs_with_fallback"] += 1

    return {
        "total_runs": total,
        "degradation_ratio": round(degraded_count / total, 3),
        "error_rate": round(error_count / total, 3),
        "avg_cost": round(sum(costs) / len(costs), 4) if costs else 0,
        "avg_time_ms": round(sum(times) / len(times)) if times else 0,
        "total_cost": round(sum(costs), 4),
        "by_mode": dict(by_mode),
        "fallback_frequency": dict(fallback_freq),
        "runs_with_degradation": degraded_count,
        "runs_with_errors": error_count,
    }


def format_report(metrics: dict) -> str:
    """Format metrics as a readable markdown report."""
    if metrics.get("total_runs", 0) == 0:
        return "No council runs recorded yet."

    lines = [
        "# Council Pipeline Metrics",
        "",
        f"**Total runs:** {metrics['total_runs']}",
        f"**Degradation ratio:** {metrics['degradation_ratio']:.1%} ({metrics['runs_with_degradation']}/{metrics['total_runs']})",
        f"**Error rate:** {metrics['error_rate']:.1%} ({metrics['runs_with_errors']}/{metrics['total_runs']})",
        f"**Avg cost:** ${metrics['avg_cost']:.4f}",
        f"**Avg time:** {metrics['avg_time_ms'] / 1000:.1f}s",
        f"**Total cost:** ${metrics['total_cost']:.4f}",
        "",
        "## By Mode",
        "",
        "| Mode | Runs | Degraded | Errors | Avg Cost | Avg Time | Degr. Ratio |",
        "|------|------|----------|--------|----------|----------|-------------|",
    ]

    for mode, stats in metrics.get("by_mode", {}).items():
        lines.append(
            f"| {mode} | {stats['count']} | {stats['degraded']} | {stats['errors']} "
            f"| ${stats['avg_cost']:.4f} | {stats['avg_time_ms'] / 1000:.1f}s "
            f"| {stats['degradation_ratio']:.1%} |"
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Council run log analytics")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--log-path", type=str, help="Path to runs.jsonl (default: ~/.claude/council-logs/runs.jsonl)")
    args = parser.parse_args()

    log_path = Path(args.log_path) if args.log_path else None
    runs = load_runs(log_path)
    metrics = compute_metrics(runs)

    if args.json:
        print(json.dumps(metrics, indent=2))
    else:
        print(format_report(metrics))


if __name__ == "__main__":
    main()
