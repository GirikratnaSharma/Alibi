"""Unit tests for deterministic Step 7 verdict aggregation."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.verdict import aggregate_verdict, format_report, run_pipeline


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
        self.assertEqual(report["recalled_context"], [])
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

    @patch("src.verdict.compare_results")
    @patch("src.verdict.run_old_vs_new")
    @patch("src.verdict.inspect_change")
    @patch("src.verdict._git")
    @patch("src.verdict.load_sources")
    @patch("src.verdict.load_hardcoded_call_sites")
    def test_pipeline_recalls_then_stores_without_overriding_classifier(
        self,
        load_call_sites,
        load_source_versions,
        git,
        inspect,
        run_modal,
        compare,
    ) -> None:
        divergence = {
            "field": "discount_rate",
            "old_value": 0.15,
            "new_value": 0.2,
            "old_present": True,
            "new_present": True,
        }
        prior = {
            "function": "calculate_discount",
            "field": "discount_rate",
            "classification": "unintended",
        }

        class FakeMemory:
            def __init__(self) -> None:
                self.stored = []

            def recall(self, **_kwargs):
                return {"status": "recalled", "matches": [prior]}

            def store(self, **kwargs):
                self.stored.append(kwargs)
                return {"status": "stored"}

        classifier_calls = []

        def classifier(_divergence, _ticket, **kwargs):
            classifier_calls.append(kwargs)
            return "intended"

        load_call_sites.return_value = {
            "source": "hardcoded_fallback",
            "call_sites": [{}, {}, {}, {}, {}],
        }
        load_source_versions.return_value = (
            "old source",
            "new source",
            "old-commit",
            "old message",
        )
        git.return_value = "ticket-commit"
        inspect.return_value = {
            "files": [{"functions": [{"name": "calculate_discount"}]}]
        }
        run_modal.return_value = {
            "runs": {"old": {"status": "ok"}, "new": {"status": "ok"}},
            "results": [{}],
        }
        compare.return_value = [
            {"input": VIP_INPUT, "divergences": [divergence]}
        ]
        memory = FakeMemory()

        report = run_pipeline(classifier=classifier, memory=memory)

        self.assertEqual(report["verdict"], "auto-approve")
        self.assertEqual(classifier_calls[0]["recalled_context"], [prior])
        self.assertEqual(memory.stored[0]["classification"], "intended")
        self.assertEqual(report["recalled_context"][0]["status"], "recalled")
        self.assertEqual(report["recalled_context"][0]["matches"], [prior])


if __name__ == "__main__":
    unittest.main()
