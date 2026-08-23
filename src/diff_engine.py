"""Deterministic OLD-vs-NEW output comparison.

This module performs plain equality checks only. It must never call an LLM,
network service, or classifier.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def diff_outputs(
    old_output: Mapping[str, Any], new_output: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Report every top-level field whose presence or value changed."""
    if old_output == new_output:
        return []

    divergences = []
    for field in sorted(old_output.keys() | new_output.keys()):
        old_present = field in old_output
        new_present = field in new_output
        old_value = old_output.get(field)
        new_value = new_output.get(field)

        if old_present == new_present and old_value == new_value:
            continue
        divergences.append(
            {
                "field": field,
                "old_value": old_value,
                "new_value": new_value,
                "old_present": old_present,
                "new_present": new_present,
            }
        )
    return divergences


def compare_results(
    results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Compare each successful Step 4 result and retain its input evidence."""
    comparisons = []
    for result in results:
        if "old_error" in result or "new_error" in result:
            raise ValueError("diff engine only compares successful outputs")

        old_output = result.get("old_output")
        new_output = result.get("new_output")
        if not isinstance(old_output, Mapping) or not isinstance(new_output, Mapping):
            raise ValueError("old_output and new_output must be objects")

        divergences = diff_outputs(old_output, new_output)
        comparisons.append(
            {
                "input": result.get("input"),
                "equal": not divergences,
                "divergences": divergences,
            }
        )
    return comparisons
