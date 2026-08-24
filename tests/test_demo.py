"""Unit tests for the stage-friendly demo runner."""

from __future__ import annotations

import unittest

from demo import format_demo, source_for_scenario


class DemoTests(unittest.TestCase):
    def test_regression_is_injected_only_into_returned_source(self) -> None:
        source = (
            "discount_rate = 0.0\n"
            '    if customer_type == "vip" and order_total > 100:\n'
            "        discount_rate += 0.05\n"
        )

        changed = source_for_scenario(source, "regression")

        self.assertNotIn('customer_type == "regular"', source)
        self.assertIn('customer_type == "regular"', changed)
        self.assertIn('customer_type == "vip"', changed)
        self.assertEqual(source_for_scenario(source, "clean"), source)

    def test_flag_report_prominently_renders_exact_evidence(self) -> None:
        evidence = {
            "input": {
                "order_total": 80.0,
                "customer_type": "regular",
                "item_count": 2,
            },
            "field": "discount_rate",
            "old_value": 0.0,
            "new_value": 0.05,
            "classification": "unintended",
            "reasoning": "Regular-order behavior must remain unchanged.",
        }
        result = {
            "scenario": "regression",
            "ticket_text": "Give qualifying VIP orders another five percent.",
            "modal_results": [
                {
                    "input": evidence["input"],
                    "old_output": {"discount_rate": 0.0},
                    "new_output": {"discount_rate": 0.05},
                }
            ],
            "report": {
                "verdict": "flag",
                "summary": "Flagged because 1 divergence was unintended.",
                "pipeline": {
                    "generated_change": {
                        "commit": "31dd30e",
                        "file": "demo-repo/pricing.py",
                        "functions": ["calculate_discount"],
                    }
                },
                "divergences": [evidence],
                "flagged_evidence": [evidence],
                "recalled_context": [
                    {"status": "recalled", "matches": [{"classification": "unintended"}]}
                ],
                "run_errors": [],
            },
        }

        rendered = format_demo(result)

        self.assertIn("OLD VS NEW OUTPUTS", rendered)
        self.assertIn("CONFIRMED DIVERGENCES", rendered)
        self.assertIn("[UNINTENDED] discount_rate", rendered)
        self.assertIn("!!! FLAG — HUMAN REVIEW REQUIRED !!!", rendered)
        self.assertIn("discount_rate: 0.0 -> 0.05", rendered)
        self.assertNotIn('{"verdict":', rendered)


if __name__ == "__main__":
    unittest.main()
