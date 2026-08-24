#!/usr/bin/env python3
"""Human-readable live demo for Alibi's complete hardcoded pipeline.

Run with the repository virtual environment so the pinned Modal SDK is used:

    ./.venv/bin/python demo.py --scenario clean
    ./.venv/bin/python demo.py --scenario regression
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

from src.claude_memory import ClaudeMemClient
from src.diff_engine import compare_results
from src.divergence_classifier import classify_divergence
from src.greptile_call_sites import load_hardcoded_call_sites
from src.modal_runner import (
    PRICING_PATH,
    REPOSITORY_ROOT,
    TEST_INPUTS,
    TICKET_PATH,
    load_sources,
    run_old_vs_new,
)
from src.verdict import aggregate_verdict


EXPECTED_PYTHON = REPOSITORY_ROOT / ".venv/bin/python"
FUNCTION_NAME = "calculate_discount"
REGRESSION_MARKER = '    if customer_type == "vip" and order_total > 100:\n'
REGRESSION_CHANGE = (
    '    if customer_type == "regular":\n'
    "        discount_rate += 0.05\n\n"
    + REGRESSION_MARKER
)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def source_for_scenario(new_source: str, scenario: str) -> str:
    """Return the checked-in source or a demo-only in-memory regression."""
    if scenario == "clean":
        return new_source
    if scenario != "regression":
        raise ValueError(f"unknown scenario: {scenario}")
    if REGRESSION_MARKER not in new_source:
        raise RuntimeError("could not locate the VIP branch for demo injection")
    return new_source.replace(REGRESSION_MARKER, REGRESSION_CHANGE, 1)


def _run_errors(modal_output: Mapping[str, Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
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


def _reason(classification: str, input_evidence: Mapping[str, Any]) -> str:
    if classification == "intended":
        return (
            "This is a direct effect of the ticket's additional five-point "
            "discount for qualifying VIP orders."
        )
    customer_type = input_evidence.get("customer_type", "this customer")
    return (
        f"The ticket only changes qualifying VIP orders; it explicitly says "
        f"other behavior must remain unchanged, but this input is {customer_type!r}."
    )


def run_demo(scenario: str) -> dict[str, Any]:
    """Run one live scenario and retain evidence needed by the presenter."""
    ticket_text = (REPOSITORY_ROOT / TICKET_PATH).read_text(encoding="utf-8")
    call_sites = load_hardcoded_call_sites(REPOSITORY_ROOT, FUNCTION_NAME)
    old_source, checked_in_new_source, old_commit, old_message = load_sources()
    new_source = source_for_scenario(checked_in_new_source, scenario)
    ticket_commit = _git(
        "log", "--diff-filter=A", "--format=%H", "-1", "--", str(TICKET_PATH)
    )

    modal_output = run_old_vs_new(old_source, new_source, TEST_INPUTS)
    errors = _run_errors(modal_output)
    comparisons: list[dict[str, Any]] = []
    classified: list[dict[str, Any]] = []
    recalled_context: list[dict[str, Any]] = []
    memory = ClaudeMemClient()

    if not errors:
        comparisons = compare_results(modal_output["results"])
        for comparison in comparisons:
            for divergence in comparison["divergences"]:
                recall = memory.recall(
                    function=FUNCTION_NAME,
                    divergence=divergence,
                )
                recalled_context.append(
                    {
                        "function": FUNCTION_NAME,
                        "field": divergence["field"],
                        **recall,
                    }
                )
                try:
                    classification = classify_divergence(
                        divergence,
                        ticket_text,
                        input_evidence=comparison["input"],
                        recalled_context=recall["matches"],
                    )
                    evidence = {
                        "input": comparison["input"],
                        **divergence,
                        "classification": classification,
                        "reasoning": _reason(classification, comparison["input"]),
                    }
                    classified.append(evidence)
                    memory.store(
                        function=FUNCTION_NAME,
                        divergence=divergence,
                        ticket_reference=str(TICKET_PATH),
                        classification=classification,
                    )
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
            "functions": [FUNCTION_NAME],
        },
        "call_sites": {
            "source": call_sites["source"],
            "count": len(call_sites["call_sites"]),
        },
        "old_source": {"commit": old_commit, "message": old_message},
    }
    return {
        "scenario": scenario,
        "ticket_text": ticket_text.strip(),
        "modal_results": modal_output.get("results", []),
        "comparisons": comparisons,
        "report": report,
    }


def _value(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _fields(values: Mapping[str, Any]) -> str:
    return ", ".join(f"{key}={_value(value)}" for key, value in values.items())


def _confirmed_divergences(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten deterministic evidence independently of LLM classification."""
    confirmed: list[dict[str, Any]] = []
    for comparison in result.get("comparisons", []):
        for divergence in comparison.get("divergences", []):
            confirmed.append({"input": comparison["input"], **divergence})
    return confirmed


def format_demo(result: Mapping[str, Any]) -> str:
    """Render a stage-friendly narrative rather than a JSON payload."""
    report = result["report"]
    change = report["pipeline"]["generated_change"]
    scenario = result["scenario"]
    lines = [
        "=" * 72,
        f"ALIBI LIVE DEMO — {scenario.upper()} SCENARIO",
        "=" * 72,
        "",
        "TICKET",
        "------",
        result["ticket_text"],
        "",
        "CHANGE UNDER TEST",
        "-----------------",
        f"Commit:   {change['commit']}",
        f"File:     {change['file']}",
        f"Function: {', '.join(change['functions'])}",
    ]
    if scenario == "regression":
        lines.append(
            "Scenario: demo-only in-memory regression adds 5% to regular orders; "
            "no source file is changed."
        )

    lines.extend(["", "OLD VS NEW OUTPUTS", "------------------"])
    for index, item in enumerate(result["modal_results"], start=1):
        lines.extend(
            [
                f"Input {index}: {_fields(item['input'])}",
                f"  OLD: {_fields(item['old_output'])}",
                f"  NEW: {_fields(item['new_output'])}",
                f"  Result: {'EQUAL' if item['old_output'] == item['new_output'] else 'CHANGED'}",
            ]
        )

    confirmed_divergences = _confirmed_divergences(result)
    classified_divergences = report["divergences"]
    lines.extend(["", "CONFIRMED DIVERGENCES", "---------------------"])
    if not confirmed_divergences:
        lines.append("None.")
    for index, item in enumerate(confirmed_divergences, start=1):
        lines.extend(
            [
                f"{index}. Input: {_fields(item['input'])}",
                f"   {item['field']}: {_value(item['old_value'])} -> "
                f"{_value(item['new_value'])}",
            ]
        )

    recalls = report.get("recalled_context", [])
    lines.extend(["", "CLASSIFICATIONS", "---------------"])
    if not classified_divergences:
        if confirmed_divergences:
            lines.append("No classifications completed; see run errors below.")
        else:
            lines.append("No divergence needed classification.")
    for index, item in enumerate(classified_divergences, start=1):
        recall = recalls[index - 1] if index <= len(recalls) else {}
        memory_note = (
            f"{len(recall.get('matches', []))} prior verdict(s) recalled"
            if recall.get("status") == "recalled"
            else recall.get("status", "cold_start")
        )
        lines.extend(
            [
                f"{index}. [{item['classification'].upper()}] {item['field']}",
                f"   Reasoning: {item['reasoning']}",
                f"   Memory: {memory_note} (advisory only)",
            ]
        )

    lines.extend(["", "FINAL VERDICT", "-------------"])
    if report["verdict"] == "flag":
        lines.extend(
            [
                "!!! FLAG — HUMAN REVIEW REQUIRED !!!",
                report["summary"],
                "",
                "FLAGGED EVIDENCE",
            ]
        )
        for item in report["flagged_evidence"]:
            lines.extend(
                [
                    f"- Input: {_fields(item['input'])}",
                    f"  {item['field']}: {_value(item['old_value'])} -> "
                    f"{_value(item['new_value'])}",
                    f"  Why: {item['reasoning']}",
                ]
            )
    else:
        lines.extend(["AUTO-APPROVE", report["summary"]])

    if report["run_errors"]:
        lines.extend(["", "RUN ERRORS"])
        for error in report["run_errors"]:
            detail = error["error"]
            lines.append(
                f"- {error['stage']}: {detail.get('type', 'Error')}: "
                f"{detail.get('message', 'unknown error')}"
            )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("clean", "regression"),
        default="clean",
        help="clean auto-approve path or injected regression flag path",
    )
    return parser.parse_args()


def main() -> int:
    expected = EXPECTED_PYTHON.resolve()
    if Path(sys.executable).resolve() != expected:
        print(
            f"Run this demo with: ./.venv/bin/python demo.py --scenario clean",
            file=sys.stderr,
        )
        return 2
    args = parse_args()
    try:
        result = run_demo(args.scenario)
    except Exception as exc:
        print(f"ALIBI DEMO FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(format_demo(result))
    return 2 if result["report"]["run_errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
