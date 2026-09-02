"""Tests for constrained LLM-generated demo inputs."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from src.input_generator import build_prompt, generate_inputs, validate_inputs
from src.modal_runner import REPOSITORY_ROOT, TICKET_PATH, load_sources
from src.pr_pipeline import find_callers, function_source


LIVE_LLM_TESTS = os.environ.get("ALIBI_RUN_LIVE_LLM_TESTS") == "1"


class InputGeneratorTests(unittest.TestCase):
    def test_prompt_marks_repository_and_review_text_as_untrusted(self) -> None:
        prompt = build_prompt(
            ticket_text="VIP orders above $100 receive five more points.",
            function_name="calculate_discount",
            old_function="def calculate_discount(...): pass",
            new_function="def calculate_discount(...): return {}",
            callers=[{"path": "checkout.py", "excerpt": "calculate_discount(...)"}],
            greptile_comments=[{"body": "Check the $100 boundary"}],
        )

        self.assertIn("untrusted data", prompt)
        self.assertIn("Check the $100 boundary", prompt)
        self.assertIn("Return data only", prompt)

    def test_validate_inputs_accepts_safe_unique_data(self) -> None:
        inputs = validate_inputs(
            {
                "inputs": [
                    {"order_total": 100, "customer_type": "vip", "item_count": 1},
                    {"order_total": 101, "customer_type": "vip", "item_count": 1},
                    {"order_total": 80, "customer_type": "regular", "item_count": 2},
                ]
            }
        )

        self.assertEqual(inputs[1], (101.0, "vip", 1))

    def test_validate_inputs_rejects_duplicates(self) -> None:
        repeated = {"order_total": 100, "customer_type": "vip", "item_count": 1}
        with self.assertRaisesRegex(ValueError, "duplicates"):
            validate_inputs({"inputs": [repeated, dict(repeated), dict(repeated)]})


@unittest.skipUnless(
    LIVE_LLM_TESTS,
    "set ALIBI_RUN_LIVE_LLM_TESTS=1 to call the real input generator",
)
class LiveInputGeneratorTests(unittest.TestCase):
    def test_real_discount_change_produces_safe_inputs(self) -> None:
        old_source, new_source, _old_commit, _old_message = load_sources()
        ticket = (REPOSITORY_ROOT / Path(TICKET_PATH)).read_text(encoding="utf-8")

        inputs = generate_inputs(
            ticket_text=ticket,
            function_name="calculate_discount",
            old_function=function_source(old_source, "calculate_discount"),
            new_function=function_source(new_source, "calculate_discount"),
            callers=find_callers("HEAD", "calculate_discount"),
        )

        self.assertGreaterEqual(len(inputs), 3)
        self.assertLessEqual(len(inputs), 5)
        self.assertTrue(
            any(
                total > 100 and kind == "vip" and count < 10
                for total, kind, count in inputs
            )
        )


if __name__ == "__main__":
    unittest.main()
