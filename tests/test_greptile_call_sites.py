"""Tests for the standalone Step 3 hardcoded call-site checkpoint."""

import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from greptile_call_sites import load_hardcoded_call_sites  # noqa: E402


class GreptileCallSiteTests(unittest.TestCase):
    def test_fallback_contains_five_validated_real_locations(self) -> None:
        result = load_hardcoded_call_sites(REPO_ROOT, "calculate_discount")

        self.assertEqual(result["source"], "hardcoded_fallback")
        self.assertEqual(len(result["call_sites"]), 5)
        self.assertTrue(
            all(
                site["path"] == "tests/test_pricing.py"
                for site in result["call_sites"]
            )
        )

    def test_standalone_command_emits_structured_json(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "src/greptile_call_sites.py",
                "--function",
                "calculate_discount",
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)

        self.assertEqual(data["function"], "calculate_discount")
        self.assertEqual(data["source"], "hardcoded_fallback")
        self.assertEqual(len(data["call_sites"]), 5)
        self.assertNotIn("fallback_reason", data)


if __name__ == "__main__":
    unittest.main()
