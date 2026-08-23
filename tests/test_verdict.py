"""Unit tests for deterministic Step 7 verdict aggregation."""

from __future__ import annotations

import unittest

from src.verdict import aggregate_verdict, format_report


VIP_INPUT = {
    "order_total": 200.0,
    "customer_type": "vip",
    "item_count": 5,
}
REGULAR_INPUT = {
    "order_total": 80.0,
    "customer_type": "regular",
    "item_count": 2,
}


class VerdictTests(unittest.TestCase):
    def test_all_intended_divergences_auto_approve(self) -> None:
        report = aggregate_verdict(
            [
                {
                    "input": VIP_INPUT,
                    "field": "discount_rate",
                    "old_value": 0.15,
                    "new_value": 0.2,
                    "classification": "intended",
                },
                {
                    "input": VIP_INPUT,
                    "field": "discount_amount",
                    "old_value": 30.0,
                    "new_value": 40.0,
                    "classification": "intended",
                },
            ],
            inputs_tested=5,
            run_status={"old": {"status": "ok"}, "new": {"status": "ok"}},
        )

        self.assertEqual(report["verdict"], "auto-approve")
        self.assertEqual(report["flagged_evidence"], [])
        self.assertEqual(report["counts"]["intended"], 2)
        self.assertIn("ALIBI VERDICT: AUTO-APPROVE", format_report(report))

    def test_regular_order_unintended_divergence_flags_exact_evidence(self) -> None:
        report = aggregate_verdict(
            [
                {
                    "input": VIP_INPUT,
                    "field": "discount_rate",
                    "old_value": 0.15,
                    "new_value": 0.2,
                    "classification": "intended",
                },
                {
                    "input": REGULAR_INPUT,
                    "field": "discount_rate",
                    "old_value": 0.0,
                    "new_value": 0.05,
                    "classification": "unintended",
                },
            ],
            inputs_tested=5,
            run_status={"old": {"status": "ok"}, "new": {"status": "ok"}},
        )

        self.assertEqual(report["verdict"], "flag")
        self.assertEqual(
            report["flagged_evidence"],
            [
                {
                    "input": REGULAR_INPUT,
                    "field": "discount_rate",
                    "old_value": 0.0,
                    "new_value": 0.05,
                    "classification": "unintended",
                }
            ],
        )
        rendered = format_report(report)
        self.assertIn("ALIBI VERDICT: FLAG", rendered)
        self.assertIn('order_total=80.0, customer_type="regular", item_count=2', rendered)
        self.assertIn("discount_rate: 0.0 → 0.05", rendered)

    def test_run_error_flags_without_divergence(self) -> None:
        report = aggregate_verdict(
            [],
            inputs_tested=5,
            run_errors=[
                {
                    "stage": "modal",
                    "version": "new",
                    "error": {"type": "TimeoutError", "message": "timed out"},
                }
            ],
        )

        self.assertEqual(report["verdict"], "flag")
        self.assertEqual(report["counts"]["run_errors"], 1)


if __name__ == "__main__":
    unittest.main()
