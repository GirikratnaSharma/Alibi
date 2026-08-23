"""Local contract tests for the real Step 4 Modal runner."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from src import modal_runner


class ModalRunnerTests(unittest.TestCase):
    def test_checkpoint_uses_three_to_five_hardcoded_inputs(self) -> None:
        self.assertGreaterEqual(len(modal_runner.TEST_INPUTS), 3)
        self.assertLessEqual(len(modal_runner.TEST_INPUTS), 5)
        self.assertEqual(
            modal_runner.TEST_INPUTS,
            [
                (80.00, "regular", 2),
                (120.00, "member", 3),
                (200.00, "vip", 5),
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

    def test_sandbox_blocks_network_and_limits_resources(self) -> None:
        sandbox = Mock()
        sandbox.exec.return_value.stdout.read.return_value = (
            '[{"status":"ok","value":{"final_total":80.0}}]'
        )
        sandbox.exec.return_value.stderr.read.return_value = ""
        sandbox.exec.return_value.wait.return_value = 0

        with patch(
            "src.modal_runner.modal.Sandbox.create", return_value=sandbox
        ) as create:
            result = modal_runner.run_source_in_sandbox(
                "def calculate_discount(*args): return {'final_total': 80.0}",
                [(80.0, "regular", 2)],
                app=Mock(),
                image=Mock(),
            )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(create.call_args.kwargs["block_network"])
        self.assertEqual(create.call_args.kwargs["cpu"], 1.0)
        self.assertEqual(create.call_args.kwargs["memory"], 256)


if __name__ == "__main__":
    unittest.main()
