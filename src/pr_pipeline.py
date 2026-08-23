"""Verify the demo pure-function change from a GitHub pull request."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

from src.claude_memory import ClaudeMemClient
from src.diff_engine import compare_results
from src.divergence_classifier import classify_divergence
from src.github_pr import ensure_commit, load_greptile_review, load_pull_request
from src.input_generator import generate_inputs
from src.inspect_change import inspect_change
from src.modal_runner import PRICING_PATH, REPOSITORY_ROOT, run_old_vs_new
from src.verdict import aggregate_verdict, format_report


InputGenerator = Callable[..., list[tuple[float, str, int]]]
Classifier = Callable[..., str]


def _git(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def source_at(revision: str, path: Path) -> str:
    """Read one file from an immutable Git revision."""
    return _git("show", f"{revision}:{path.as_posix()}")


def function_source(source: str, function_name: str) -> str:
    """Extract one top-level or nested function from Python source."""
    tree = ast.parse(source)
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one function named {function_name}; found {len(matches)}"
        )
    extracted = ast.get_source_segment(source, matches[0])
    if not extracted:
        raise RuntimeError(f"Could not extract function {function_name}")
    return extracted


def find_callers(revision: str, function_name: str) -> list[dict[str, Any]]:
    """Find executable Python call expressions at a Git revision."""
    paths = _git("ls-tree", "-r", "--name-only", revision).splitlines()
    callers = []
    for relative_path in paths:
        if not relative_path.endswith(".py"):
            continue
        try:
            source = source_at(revision, Path(relative_path))
            tree = ast.parse(source)
        except (subprocess.CalledProcessError, SyntaxError):
            continue
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            name = called.id if isinstance(called, ast.Name) else (
                called.attr if isinstance(called, ast.Attribute) else None
            )
            if name != function_name:
                continue
            start = node.lineno
            end = node.end_lineno or start
            callers.append(
                {
                    "path": relative_path,
                    "line_start": start,
                    "line_end": end,
                    "excerpt": "\n".join(lines[start - 1 : end])[:2_000],
                }
            )
    return callers[:20]


def _run_errors(modal_output: Mapping[str, Any]) -> list[dict[str, Any]]:
    errors = []
    for version, status in modal_output.get("runs", {}).items():
        if status.get("status") != "ok":
            errors.append(
                {
                    "stage": "modal",
                    "version": version,
                    "error": status.get("error", {"message": "unknown run error"}),
                }
            )
    for result in modal_output.get("results", []):
        for version in ("old", "new"):
            if result.get(f"{version}_error") is not None:
                errors.append(
                    {
                        "stage": "modal",
                        "version": version,
                        "input": result.get("input"),
                        "error": result[f"{version}_error"],
                    }
                )
    return errors


def run_pr_pipeline(
    repository: str,
    pr_number: int,
    *,
    input_generator: InputGenerator = generate_inputs,
    classifier: Classifier = classify_divergence,
    memory: ClaudeMemClient | None = None,
) -> dict[str, Any]:
    """Run the PR base/head through the complete Alibi demo path."""
    pr = load_pull_request(repository, pr_number)
    ensure_commit(REPOSITORY_ROOT, pr["base_sha"], fetch_ref=pr["base_ref"])
    ensure_commit(
        REPOSITORY_ROOT,
        pr["head_sha"],
        fetch_ref=f"pull/{pr_number}/head",
    )

    changed_paths = {item["path"] for item in pr["files"]}
    if PRICING_PATH.as_posix() not in changed_paths:
        raise RuntimeError(
            f"PR #{pr_number} does not change the demo pure function file {PRICING_PATH}"
        )
    change = inspect_change(
        REPOSITORY_ROOT,
        pr["base_sha"],
        PRICING_PATH,
        target=pr["head_sha"],
    )
    names = [item["name"] for item in change["files"][0]["functions"]]
    if names != ["calculate_discount"]:
        raise RuntimeError(
            "The PR-driven demo requires calculate_discount to be the only changed "
            f"function in {PRICING_PATH}; found {names}"
        )

    old_source = source_at(pr["base_sha"], PRICING_PATH)
    new_source = source_at(pr["head_sha"], PRICING_PATH)
    callers = find_callers(pr["head_sha"], "calculate_discount")
    if not callers:
        raise RuntimeError("No executable calculate_discount callers were found")
    greptile = load_greptile_review(repository, pr_number)
    ticket_text = f"{pr['title']}\n\n{pr['body']}".strip()
    inputs = input_generator(
        ticket_text=ticket_text,
        function_name="calculate_discount",
        old_function=function_source(old_source, "calculate_discount"),
        new_function=function_source(new_source, "calculate_discount"),
        callers=callers,
        greptile_comments=greptile["comments"],
    )

    modal_output = run_old_vs_new(old_source, new_source, inputs)
    errors = _run_errors(modal_output)
    classified: list[dict[str, Any]] = []
    recalled_context: list[dict[str, Any]] = []
    memory = memory or ClaudeMemClient()

    if not errors:
        comparisons = compare_results(modal_output["results"])
        divergence_count = sum(len(item["divergences"]) for item in comparisons)
        if divergence_count == 0:
            errors.append(
                {
                    "stage": "diff",
                    "error": {
                        "type": "NoBehaviorChange",
                        "message": "No output changed on the generated inputs",
                    },
                }
            )
        for comparison in comparisons:
            for divergence in comparison["divergences"]:
                try:
                    recall = memory.recall(
                        function="calculate_discount",
                        divergence=divergence,
                    )
                except Exception as exc:
                    recall = {
                        "status": "unavailable",
                        "matches": [],
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                recalled_context.append(
                    {
                        "function": "calculate_discount",
                        "field": divergence["field"],
                        **recall,
                    }
                )
                evidence = {
                    "input": comparison["input"],
                    **divergence,
                }
                try:
                    evidence["classification"] = classifier(
                        divergence,
                        ticket_text,
                        input_evidence=comparison["input"],
                        recalled_context=recall["matches"],
                    )
                    classified.append(evidence)
                    try:
                        memory.store(
                            function="calculate_discount",
                            divergence=divergence,
                            ticket_reference=pr["url"],
                            classification=evidence["classification"],
                        )
                    except Exception:
                        pass
                except Exception as exc:
                    errors.append(
                        {
                            "stage": "classification",
                            "input": comparison["input"],
                            "field": divergence["field"],
                            "old_value": divergence["old_value"],
                            "new_value": divergence["new_value"],
                            "error": {
                                "type": type(exc).__name__,
                                "message": str(exc),
                            },
                        }
                    )

    report = aggregate_verdict(
        classified,
        inputs_tested=len(inputs),
        run_errors=errors,
        run_status=modal_output.get("runs", {}),
        recalled_context=recalled_context,
    )
    report["pipeline"] = {
        "ticket": pr["url"],
        "generated_change": {
            "commit": pr["head_sha"],
            "file": PRICING_PATH.as_posix(),
            "functions": names,
        },
        "call_sites": {"source": "git_ast", "count": len(callers)},
        "old_source": {"commit": pr["base_sha"], "message": pr["base_ref"]},
        "pull_request": pr,
        "greptile_review": greptile,
        "generated_inputs": [
            {
                "order_total": item[0],
                "customer_type": item[1],
                "item_count": item[2],
            }
            for item in inputs
        ],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a GitHub PR with Alibi")
    parser.add_argument("--repository", default="GirikratnaSharma/Alibi")
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = run_pr_pipeline(args.repository, args.pr)
    except Exception as exc:
        report = aggregate_verdict(
            [],
            inputs_tested=0,
            run_errors=[
                {
                    "stage": "pipeline",
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                }
            ],
        )
    print(json.dumps(report, indent=2) if args.json else format_report(report))
    return 0 if report["verdict"] == "auto-approve" else 1


if __name__ == "__main__":
    sys.exit(main())
