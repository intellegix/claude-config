"""Compact session context exporter for council queries.

Produces ~500-2000 tokens of project context instead of dumping
the full JSONL transcript (which can be 40K+ tokens).

Usage:
    python session_context.py /path/to/project > session_context.md
"""

import io
import json
import subprocess
import sys
from pathlib import Path

# Force UTF-8 stdout on Windows (cp1252 can't encode Unicode arrows etc.)
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def get_git_log(project_dir: Path, count: int = 10) -> str:
    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-{count}"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def get_git_diff_summary(project_dir: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def get_recently_modified(project_dir: Path, count: int = 15) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~5", "HEAD"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split("\n")[:count]
    except Exception:
        pass
    return []


def read_truncated(path: Path, max_lines: int = 50) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[:max_lines])
    except Exception:
        return ""


def extract_claude_md_overview(project_dir: Path) -> str:
    claude_md = project_dir / "CLAUDE.md"
    if not claude_md.exists():
        return ""
    text = read_truncated(claude_md, max_lines=80)
    # Extract up to the first major section break after overview
    lines = text.splitlines()
    overview_lines: list[str] = []
    found_overview = False
    sections_found = 0
    for line in lines:
        if line.startswith("## "):
            sections_found += 1
            if sections_found > 3:
                break
            found_overview = True
        if found_overview or not line.startswith("##"):
            overview_lines.append(line)
    return "\n".join(overview_lines) if overview_lines else text


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python session_context.py /path/to/project", file=sys.stderr)
        sys.exit(1)

    project_dir = Path(sys.argv[1]).resolve()
    project_name = project_dir.name

    git_log = get_git_log(project_dir)
    git_diff = get_git_diff_summary(project_dir)
    recent_files = get_recently_modified(project_dir)
    claude_overview = extract_claude_md_overview(project_dir)

    # Claude Code encodes project paths by replacing all non-alphanumeric chars with dashes
    import re
    hash_name = re.sub(r"[^a-zA-Z0-9]", "-", project_dir.as_posix()).lstrip("-")
    memory_dir = Path.home() / ".claude" / "projects" / hash_name / "memory"
    memory_text = read_truncated(memory_dir / "MEMORY.md", max_lines=50)

    output = f"""# Session Context: {project_name}

## Recent Git History
```
{git_log or "(no git history)"}
```

## Uncommitted Changes
```
{git_diff or "(clean working tree)"}
```

## Recently Modified Files
{chr(10).join(f"- {f}" for f in recent_files) if recent_files else "(none)"}

## Project Overview (CLAUDE.md)
{claude_overview or "(no CLAUDE.md found)"}

## Project Memory (MEMORY.md excerpt)
{memory_text or "(no MEMORY.md found)"}
"""
    print(output)


if __name__ == "__main__":
    main()
