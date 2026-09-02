"""Tests for structured generated-change inspection."""

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from inspect_change import changed_new_lines, inspect_change  # noqa: E402


class InspectChangeTests(unittest.TestCase):
    def test_changed_new_lines_handles_additions_and_deletions(self) -> None:
        diff = """@@ -2,2 +2,3 @@
 unchanged
-old
+new
+added
"""
        self.assertEqual(changed_new_lines(diff), {3, 4})

    def test_current_ticket_change_identifies_target_function(self) -> None:
        change = inspect_change(
            REPO_ROOT, "HEAD", Path("demo-repo/pricing.py")
        )
        changed_file = change["files"][0]

        self.assertEqual(changed_file["path"], "demo-repo/pricing.py")
        self.assertEqual(
            [function["name"] for function in changed_file["functions"]],
            ["calculate_discount"],
        )
        self.assertIn(
            'customer_type == "vip" and order_total > 100',
            changed_file["functions"][0]["new_body"],
        )
        self.assertIn("discount_rate += 0.05", changed_file["diff"])


if __name__ == "__main__":
    unittest.main()
