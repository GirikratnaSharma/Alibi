"""Emit a structured description of a generated Python change."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path


HUNK_HEADER = re.compile(
    r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@"
)


def changed_new_lines(diff: str) -> set[int]:
    """Return new-file line numbers affected by a unified diff."""
    changed: set[int] = set()
    new_line: int | None = None

    for line in diff.splitlines():
        match = HUNK_HEADER.match(line)
        if match:
            new_line = int(match.group("start"))
            if int(match.group("count") or "1") == 0:
                changed.add(new_line)
            continue

        if new_line is None or line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            changed.add(new_line)
            new_line += 1
        elif line.startswith("-"):
            changed.add(new_line)
        else:
            new_line += 1

    return changed


def changed_lines_by_side(diff: str) -> tuple[set[int], set[int]]:
    """Return OLD and NEW line numbers changed by a unified diff."""
    old_changed: set[int] = set()
    new_changed: set[int] = set()
    old_line: int | None = None
    new_line: int | None = None

    for line in diff.splitlines():
        match = re.match(
            r"^@@ -(?P<old>\d+)(?:,\d+)? \+(?P<new>\d+)(?:,\d+)? @@",
            line,
        )
        if match:
            old_line = int(match.group("old"))
            new_line = int(match.group("new"))
            continue
        if old_line is None or new_line is None or line.startswith(("+++", "---")):
            continue
        if line.startswith("+"):
            new_changed.add(new_line)
            new_line += 1
        elif line.startswith("-"):
            old_changed.add(old_line)
            old_line += 1
        else:
            old_line += 1
            new_line += 1
    return old_changed, new_changed


def inspect_change(
    repo: Path,
    base: str,
    relative_path: Path,
    target: str | None = None,
) -> dict[str, object]:
    """Inspect a changed Python file relative to a Git revision."""
    diff_command = [
        "git",
        "diff",
        "--no-ext-diff",
        "--unified=0",
        base,
    ]
    if target is not None:
        diff_command.append(target)
    diff_command.extend(["--", relative_path.as_posix()])
    result = subprocess.run(
        diff_command,
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    diff = result.stdout
    if target is None:
        source = (repo / relative_path).read_text()
    else:
        source = subprocess.run(
            ["git", "show", f"{target}:{relative_path.as_posix()}"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    tree = ast.parse(source)
    changed_lines = changed_new_lines(diff)
    functions = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end_line = node.end_lineno or node.lineno
        if changed_lines.intersection(range(node.lineno, end_line + 1)):
            functions.append(
                {
                    "name": node.name,
                    "new_body": ast.get_source_segment(source, node),
                }
            )

    return {
        "base": base,
        "target": target or "working-tree",
        "files": [
            {
                "path": relative_path.as_posix(),
                "functions": functions,
                "diff": diff,
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--target")
    parser.add_argument("--path", required=True, type=Path)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    print(
        json.dumps(
            inspect_change(repo, args.base, args.path, target=args.target),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
