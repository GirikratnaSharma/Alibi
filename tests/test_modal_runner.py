"""Local contract tests for the real Step 4 Modal runner."""

from __future__ import annotations

import unittest

from src import modal_runner


class ModalRunnerTests(unittest.TestCase):
    def test_checkpoint_uses_six_hardcoded_inputs(self) -> None:
        self.assertEqual(len(modal_runner.TEST_INPUTS), 6)
        self.assertEqual(
            modal_runner.TEST_INPUTS,
            [
                (80.00, "regular", 2),
                (120.00, "member", 3),
                (200.00, "vip", 5),
                (150.00, "member", 12),
                (100.00, "vip", 1),
                (101.00, "vip", 10),
            ],
        )

    def test_loads_distinct_old_and_new_sources(self) -> None:
        old_source, new_source, old_commit, old_message = modal_runner.load_sources()

        self.assertNotEqual(old_source, new_source)
        self.assertNotIn(
            'customer_type == "vip" and order_total > 100', old_source
        )
        self.assertIn(
            'customer_type == "vip" and order_total > 100', new_source
        )
        self.assertEqual(len(old_commit), 40)
        self.assertEqual(old_message, "Complete deterministic demo function checkpoint")

    def test_error_details_are_structured(self) -> None:
        error = modal_runner._error_details(TimeoutError("sandbox timed out"))

        self.assertEqual(
            error,
            {"type": "TimeoutError", "message": "sandbox timed out"},
        )


if __name__ == "__main__":
    unittest.main()
