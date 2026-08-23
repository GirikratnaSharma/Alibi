"""Step 7 verdict aggregation and the hardcoded 1–7 demo pipeline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, Sequence

from src.claude_memory import ClaudeMemClient
from src.diff_engine import compare_results
from src.divergence_classifier import Classification, classify_divergence
from src.greptile_call_sites import load_hardcoded_call_sites
from src.inspect_change import inspect_change
from src.modal_runner import (
    PRICING_PATH,
    REPOSITORY_ROOT,
    TEST_INPUTS,
    TICKET_PATH,
    load_sources,
    run_old_vs_new,
)


Verdict = Literal["auto-approve", "flag"]
Classifier = Callable[..., Classification]
MemoryClient = ClaudeMemClient


def aggregate_verdict(
    classified_divergences: Sequence[Mapping[str, Any]],
    *,
    inputs_tested: int,
    run_errors: Sequence[Mapping[str, Any]] = (),
    run_status: Mapping[str, Any] | None = None,
    recalled_context: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Aggregate classifications and errors without making judgments itself."""
    divergences = [dict(item) for item in classified_divergences]
    errors = [dict(item) for item in run_errors]

    for item in divergences:
        if item.get("classification") not in ("intended", "unintended"):
            raise ValueError("every divergence needs an intended/unintended classification")
        for required in ("input", "field", "old_value", "new_value"):
            if required not in item:
                raise ValueError(f"classified divergence is missing: {required}")

    flagged_evidence = [
        item for item in divergences if item["classification"] == "unintended"
    ]
    verdict: Verdict = "flag" if flagged_evidence or errors else "auto-approve"
    intended_count = sum(
        item["classification"] == "intended" for item in divergences
    )

    if errors:
        summary = f"Flagged because {len(errors)} pipeline run(s) failed."
    elif flagged_evidence:
        summary = (
            f"Flagged because {len(flagged_evidence)} confirmed divergence(s) "
            "were classified as unintended."
        )
    else:
        summary = (
            f"Auto-approved because all {len(divergences)} confirmed "
            "divergence(s) were classified as intended."
        )

    return {
        "verdict": verdict,
        "summary": summary,
        "counts": {
            "inputs_tested": inputs_tested,
            "divergences": len(divergences),
            "intended": intended_count,
            "unintended": len(flagged_evidence),
            "run_errors": len(errors),
        },
        "run_status": dict(run_status or {}),
        "recalled_context": [dict(item) for item in recalled_context],
        "divergences": divergences,
        "flagged_evidence": flagged_evidence,
        "run_errors": errors,
    }


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


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
            error = result.get(f"{version}_error")
            if error is not None:
                errors.append(
                    {
                        "stage": "modal",
                        "version": version,
                        "input": result.get("input"),
                        "error": error,
                    }
                )
    return errors


def run_pipeline(
    *,
    classifier: Classifier = classify_divergence,
    memory: MemoryClient | None = None,
) -> dict[str, Any]:
    """Run the checked-in ticket through the complete hardcoded 1–7 path."""
    memory = memory or ClaudeMemClient()
    ticket_text = (REPOSITORY_ROOT / TICKET_PATH).read_text(encoding="utf-8")
    call_sites = load_hardcoded_call_sites(
        REPOSITORY_ROOT, "calculate_discount"
    )

    old_source, new_source, old_commit, old_message = load_sources()
    ticket_commit = _git(
        "log",
        "--diff-filter=A",
        "--format=%H",
        "-1",
        "--",
        str(TICKET_PATH),
    )
    if not ticket_commit:
        raise RuntimeError(f"Could not find the add commit for {TICKET_PATH}")
    change = inspect_change(
        REPOSITORY_ROOT,
        old_commit,
        PRICING_PATH,
        target=ticket_commit,
    )

    modal_output = run_old_vs_new(old_source, new_source, TEST_INPUTS)
    errors = _run_errors(modal_output)
    classified: list[dict[str, Any]] = []
    recalled_context: list[dict[str, Any]] = []

    if not errors:
        comparisons = compare_results(modal_output["results"])
        for comparison in comparisons:
            for divergence in comparison["divergences"]:
                evidence = {
                    "input": comparison["input"],
                    "field": divergence["field"],
                    "old_value": divergence["old_value"],
                    "new_value": divergence["new_value"],
                    "old_present": divergence["old_present"],
                    "new_present": divergence["new_present"],
                }
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
                            ticket_reference=str(TICKET_PATH),
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
        inputs_tested=len(TEST_INPUTS),
        run_errors=errors,
        run_status=modal_output.get("runs", {}),
        recalled_context=recalled_context,
    )
    report["pipeline"] = {
        "ticket": str(TICKET_PATH),
        "generated_change": {
            "commit": ticket_commit,
            "file": str(PRICING_PATH),
            "functions": [
                function["name"]
                for function in change["files"][0]["functions"]
            ],
        },
        "call_sites": {
            "source": call_sites["source"],
            "count": len(call_sites["call_sites"]),
        },
        "old_source": {
            "commit": old_commit,
            "message": old_message,
        },
    }
    return report


def _format_input(input_evidence: Mapping[str, Any]) -> str:
    return ", ".join(
        f"{key}={json.dumps(value)}" for key, value in input_evidence.items()
    )


def format_report(report: Mapping[str, Any]) -> str:
    """Render a concise reviewer-facing verdict report."""
    title = report["verdict"].upper()
    counts = report["counts"]
    lines = [
        f"ALIBI VERDICT: {title}",
        report["summary"],
        "",
        "CHECKPOINTS",
    ]

    pipeline = report.get("pipeline")
    if pipeline:
        lines.extend(
            [
                f"  Ticket: {pipeline['ticket']}",
                "  Generated change: "
                f"{pipeline['generated_change']['commit']} "
                f"({', '.join(pipeline['generated_change']['functions'])})",
                "  Call sites: "
                f"{pipeline['call_sites']['count']} validated "
                f"({pipeline['call_sites']['source']})",
            ]
        )
    lines.extend(
        [
            f"  Inputs tested: {counts['inputs_tested']}",
            f"  Modal OLD: {report['run_status'].get('old', {}).get('status', 'unknown')}",
            f"  Modal NEW: {report['run_status'].get('new', {}).get('status', 'unknown')}",
            f"  Divergences: {counts['divergences']} "
            f"({counts['intended']} intended, {counts['unintended']} unintended)",
            "  Memory: "
            + (
                ", ".join(
                    f"{item['field']}={item['status']}"
                    for item in report.get("recalled_context", [])
                )
                or "cold_start"
            ),
        ]
    )

    if report["divergences"]:
        lines.extend(["", "CLASSIFIED DIVERGENCES"])
        for item in report["divergences"]:
            lines.extend(
                [
                    f"  [{item['classification'].upper()}] {_format_input(item['input'])}",
                    f"    {item['field']}: {json.dumps(item['old_value'])} → "
                    f"{json.dumps(item['new_value'])}",
                ]
            )

    if report["run_errors"]:
        lines.extend(["", "RUN ERRORS"])
        for error in report["run_errors"]:
            location = error["stage"]
            if "version" in error:
                location += f"/{error['version']}"
            lines.append(
                f"  [{location}] {error['error'].get('type', 'Error')}: "
                f"{error['error'].get('message', 'unknown error')}"
            )
            if "input" in error:
                lines.append(f"    Input: {_format_input(error['input'])}")
            if "field" in error:
                lines.append(
                    f"    {error['field']}: {json.dumps(error['old_value'])} → "
                    f"{json.dumps(error['new_value'])}"
                )

    return "\n".join(lines)


def main() -> int:
    try:
        report = run_pipeline()
    except Exception as exc:
        report = aggregate_verdict(
            [],
            inputs_tested=0,
            run_errors=[
                {
                    "stage": "pipeline",
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            ],
        )
    print(format_report(report))
    return 0 if report["verdict"] == "auto-approve" else 1


if __name__ == "__main__":
    sys.exit(main())
