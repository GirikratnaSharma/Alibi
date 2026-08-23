"""Tests for the standalone Step 3 hardcoded call-site checkpoint."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from greptile_call_sites import (  # noqa: E402
    build_payload,
    load_hardcoded_call_sites,
)


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
        environment = os.environ.copy()
        environment.pop("GREPTILE_API_KEY", None)
        environment.pop("GITHUB_TOKEN", None)
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
            env=environment,
        )
        data = json.loads(result.stdout)

        self.assertEqual(data["function"], "calculate_discount")
        self.assertEqual(data["source"], "hardcoded_fallback")
        self.assertEqual(len(data["call_sites"]), 5)
        self.assertIn("GREPTILE_API_KEY is not configured", data["fallback_reason"])

    def test_live_payload_requests_only_executable_call_sites(self) -> None:
        payload = build_payload(
            "GirikratnaSharma/Alibi",
            "main",
            "calculate_discount",
            "demo-repo/",
        )

        self.assertEqual(
            payload["repositories"],
            [
                {
                    "remote": "github",
                    "repository": "GirikratnaSharma/Alibi",
                    "branch": "main",
                }
            ],
        )
        prompt = payload["messages"][0]["content"]
        self.assertIn("Exclude its definition, comments, docstrings", prompt)
        self.assertIn("calculate_discount", prompt)


if __name__ == "__main__":
    unittest.main()
