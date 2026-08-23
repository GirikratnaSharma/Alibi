"""Tests for deterministic PR source and caller inspection."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.pr_pipeline import find_callers, function_source, run_pr_pipeline


class PullRequestPipelineTests(unittest.TestCase):
    def test_function_source_extracts_only_requested_function(self) -> None:
        source = """\
def helper():
    return 1

def calculate_discount(total, customer, count):
    return {"final_total": total}
"""
        extracted = function_source(source, "calculate_discount")

        self.assertIn("def calculate_discount", extracted)
        self.assertNotIn("def helper", extracted)

    def test_find_callers_finds_real_application_callers(self) -> None:
        callers = find_callers("HEAD", "calculate_discount")
        paths = {item["path"] for item in callers}

        self.assertIn("demo-repo/checkout.py", paths)
        self.assertIn("demo-repo/order_service.py", paths)
        self.assertTrue(all("calculate_discount(" in item["excerpt"] for item in callers))

    @patch("src.pr_pipeline.load_pull_request")
    @patch("src.pr_pipeline.ensure_commit")
    @patch("src.pr_pipeline.inspect_change")
    @patch("src.pr_pipeline.source_at")
    @patch("src.pr_pipeline.find_callers")
    @patch("src.pr_pipeline.load_greptile_review")
    @patch("src.pr_pipeline.run_old_vs_new")
    def test_pr_pipeline_connects_pr_inputs_modal_diff_and_classifier(
        self,
        run_modal,
        load_review,
        find_real_callers,
        load_source,
        inspect,
        ensure,
        load_pr,
    ) -> None:
        load_pr.return_value = {
            "repository": "acme/alibi",
            "number": 7,
            "title": "Increase the VIP discount",
            "body": "VIP orders above $100 receive five more points.",
            "url": "https://github.com/acme/alibi/pull/7",
            "state": "OPEN",
            "base_ref": "main",
            "head_ref": "feature",
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "files": [{"path": "demo-repo/pricing.py"}],
        }
        inspect.return_value = {
            "files": [{"functions": [{"name": "calculate_discount"}]}]
        }
        old_source = """\
def calculate_discount(order_total, customer_type, item_count):
    return {"discount_rate": 0.15}
"""
        new_source = old_source.replace("0.15", "0.2")
        load_source.side_effect = [old_source, new_source]
        find_real_callers.return_value = [
            {
                "path": "demo-repo/checkout.py",
                "line_start": 10,
                "line_end": 10,
                "excerpt": "calculate_discount(subtotal, customer_type, item_count)",
            }
        ]
        load_review.return_value = {
            "status": "available",
            "comments": [{"kind": "review", "body": "Check the boundary"}],
        }
        generated_inputs = [
            (100.0, "vip", 1),
            (101.0, "vip", 1),
            (80.0, "regular", 2),
        ]
        run_modal.return_value = {
            "runs": {"old": {"status": "ok"}, "new": {"status": "ok"}},
            "results": [
                {
                    "input": {
                        "order_total": 101.0,
                        "customer_type": "vip",
                        "item_count": 1,
                    },
                    "old_output": {"discount_rate": 0.15},
                    "new_output": {"discount_rate": 0.2},
                }
            ],
        }

        class Memory:
            def recall(self, **_kwargs):
                return {"status": "cold_start", "matches": []}

            def store(self, **_kwargs):
                return {"status": "stored"}

        generator_calls = []

        def input_generator(**kwargs):
            generator_calls.append(kwargs)
            return generated_inputs

        report = run_pr_pipeline(
            "acme/alibi",
            7,
            input_generator=input_generator,
            classifier=lambda *_args, **_kwargs: "intended",
            memory=Memory(),
        )

        self.assertEqual(report["verdict"], "auto-approve")
        self.assertEqual(report["counts"]["divergences"], 1)
        self.assertEqual(report["pipeline"]["greptile_review"]["status"], "available")
        self.assertEqual(
            generator_calls[0]["greptile_comments"][0]["body"],
            "Check the boundary",
        )
        self.assertEqual(ensure.call_count, 2)


if __name__ == "__main__":
    unittest.main()
