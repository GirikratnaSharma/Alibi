"""Tests for the standalone Greptile call-site discovery integration."""

import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from greptile_call_sites import (  # noqa: E402
    build_payload,
    find_call_sites,
    parse_response,
)


class FakeResponse:
    def __init__(self, data: object) -> None:
        self.body = json.dumps(data).encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class GreptileCallSiteTests(unittest.TestCase):
    def test_payload_requests_only_executable_call_sites(self) -> None:
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

    def test_response_is_normalized_to_call_site_evidence(self) -> None:
        message, sites = parse_response(
            {
                "message": "The function is called by the pricing tests.",
                "sources": [
                    {
                        "filepath": "tests/test_pricing.py",
                        "linestart": 45,
                        "lineend": 45,
                        "summary": "Calls calculate_discount with case inputs.",
                    }
                ],
            }
        )

        self.assertIn("pricing tests", message)
        self.assertEqual(sites[0].path, "tests/test_pricing.py")
        self.assertEqual(sites[0].line_start, 45)

    def test_query_sends_secrets_in_headers_not_output(self) -> None:
        captured = {}

        def opener(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse(
                {
                    "message": "Found one caller.",
                    "sources": [
                        {
                            "filepath": "tests/test_pricing.py",
                            "linestart": 45,
                            "lineend": 47,
                            "summary": "Test invocation.",
                        }
                    ],
                }
            )

        result = find_call_sites(
            api_key="greptile-secret",
            github_token="github-secret",
            repository="GirikratnaSharma/Alibi",
            branch="main",
            function="calculate_discount",
            scope="demo-repo/",
            opener=opener,
        )

        request = captured["request"]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer greptile-secret")
        self.assertEqual(request.get_header("X-github-token"), "github-secret")
        self.assertNotIn("greptile-secret", json.dumps(result))
        self.assertEqual(result["call_sites"][0]["path"], "tests/test_pricing.py")


if __name__ == "__main__":
    unittest.main()
