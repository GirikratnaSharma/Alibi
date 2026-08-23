"""Tests for the narrow Step 6 divergence classifier."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from src.divergence_classifier import build_prompt, classify_divergence


REPOSITORY_ROOT = Path(__file__).parents[1]
TICKET_PATH = (
    REPOSITORY_ROOT / "demo-repo/tickets/001-vip-order-discount.md"
)
LIVE_LLM_TESTS = os.environ.get("ALIBI_RUN_LIVE_LLM_TESTS") == "1"

VIP_INPUT = {
    "order_total": 200.0,
    "customer_type": "vip",
    "item_count": 5,
}
REAL_INTENDED_DIVERGENCES = [
    {
        "field": "discount_rate",
        "old_value": 0.15,
        "new_value": 0.2,
        "old_present": True,
        "new_present": True,
    },
    {
        "field": "discount_amount",
        "old_value": 30.0,
        "new_value": 40.0,
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
]


class ClassifierPromptTests(unittest.TestCase):
    def test_prompt_is_limited_to_ticket_and_confirmed_evidence(self) -> None:
        ticket = TICKET_PATH.read_text(encoding="utf-8")
        prompt = build_prompt(
            REAL_INTENDED_DIVERGENCES[0],
            ticket,
            input_evidence=VIP_INPUT,
        )

        self.assertIn("Do not re-run, recalculate, dispute, or re-check", prompt)
        self.assertIn("Do not inspect code, files, tests", prompt)
        self.assertIn('"field": "discount_rate"', prompt)
        self.assertIn("additional 5 percentage-point discount", prompt)


@unittest.skipUnless(
    LIVE_LLM_TESTS,
    "set ALIBI_RUN_LIVE_LLM_TESTS=1 to call the real classifier",
)
class LiveClassifierTests(unittest.TestCase):
    def test_real_step_4_and_5_divergences_are_intended(self) -> None:
        ticket = TICKET_PATH.read_text(encoding="utf-8")

        for divergence in REAL_INTENDED_DIVERGENCES:
            with self.subTest(field=divergence["field"]):
                self.assertEqual(
                    classify_divergence(
                        divergence,
                        ticket,
                        input_evidence=VIP_INPUT,
                    ),
                    "intended",
                )

    def test_non_vip_discount_is_unintended(self) -> None:
        ticket = TICKET_PATH.read_text(encoding="utf-8")
        divergence = {
            "field": "discount_rate",
            "old_value": 0.0,
            "new_value": 0.05,
            "old_present": True,
            "new_present": True,
        }

        self.assertEqual(
            classify_divergence(
                divergence,
                ticket,
                input_evidence={
                    "order_total": 80.0,
                    "customer_type": "regular",
                    "item_count": 2,
                },
            ),
            "unintended",
        )


if __name__ == "__main__":
    unittest.main()
