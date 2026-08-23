"""Unit tests for the deterministic Step 5 diff engine."""

from __future__ import annotations

import unittest

from src.diff_engine import compare_results, diff_outputs


class DiffOutputsTests(unittest.TestCase):
    def test_known_equal_outputs_have_no_divergences(self) -> None:
        output = {
            "discount_rate": 0.1,
            "discount_amount": 12.0,
            "final_total": 108.0,
        }

        self.assertEqual(diff_outputs(output, dict(output)), [])

    def test_known_different_outputs_report_exact_fields_and_values(self) -> None:
        old_output = {
            "discount_rate": 0.15,
            "discount_amount": 30.0,
            "final_total": 170.0,
        }
        new_output = {
            "discount_rate": 0.2,
            "discount_amount": 40.0,
            "final_total": 160.0,
        }

        self.assertEqual(
            diff_outputs(old_output, new_output),
            [
                {
                    "field": "discount_amount",
                    "old_value": 30.0,
                    "new_value": 40.0,
                    "old_present": True,
                    "new_present": True,
                },
                {
                    "field": "discount_rate",
                    "old_value": 0.15,
                    "new_value": 0.2,
                    "old_present": True,
                    "new_present": True,
                },
                {
                    "field": "final_total",
                    "old_value": 170.0,
                    "new_value": 160.0,
                    "old_present": True,
                    "new_present": True,
                },
            ],
        )

    def test_added_and_removed_fields_are_explicit(self) -> None:
        self.assertEqual(
            diff_outputs({"removed": 1}, {"added": 2}),
            [
                {
                    "field": "added",
                    "old_value": None,
                    "new_value": 2,
                    "old_present": False,
                    "new_present": True,
                },
                {
                    "field": "removed",
                    "old_value": 1,
                    "new_value": None,
                    "old_present": True,
                    "new_present": False,
                },
            ],
        )

    def test_comparisons_retain_input_evidence(self) -> None:
        comparisons = compare_results(
            [
                {
                    "input": {
                        "order_total": 200.0,
                        "customer_type": "vip",
                        "item_count": 5,
                    },
                    "old_output": {"discount_amount": 30.0},
                    "new_output": {"discount_amount": 40.0},
                }
            ]
        )

        self.assertEqual(comparisons[0]["input"]["order_total"], 200.0)
        self.assertFalse(comparisons[0]["equal"])
        self.assertEqual(
            comparisons[0]["divergences"][0]["field"], "discount_amount"
        )


if __name__ == "__main__":
    unittest.main()
