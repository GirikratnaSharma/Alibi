"""Tests for GitHub PR and Greptile review ingestion."""

from __future__ import annotations

import json
import subprocess
import unittest

from src.github_pr import load_greptile_review, load_pull_request


def completed(data: object) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(data), stderr="")


class GitHubPullRequestTests(unittest.TestCase):
    def test_load_pull_request_normalizes_immutable_revisions(self) -> None:
        def runner(arguments, **_kwargs):
            self.assertEqual(arguments[:3], ["gh", "pr", "view"])
            return completed(
                {
                    "number": 7,
                    "title": "Change discount",
                    "body": "Ticket details",
                    "url": "https://github.com/acme/alibi/pull/7",
                    "state": "OPEN",
                    "baseRefName": "main",
                    "headRefName": "feature",
                    "baseRefOid": "a" * 40,
                    "headRefOid": "b" * 40,
                    "files": [
                        {
                            "path": "demo-repo/pricing.py",
                            "additions": 2,
                            "deletions": 1,
                        }
                    ],
                }
            )

        result = load_pull_request("acme/alibi", 7, runner=runner)

        self.assertEqual(result["base_sha"], "a" * 40)
        self.assertEqual(result["head_sha"], "b" * 40)
        self.assertEqual(result["files"][0]["path"], "demo-repo/pricing.py")

    def test_greptile_review_filters_other_authors(self) -> None:
        responses = iter(
            [
                [
                    {
                        "user": {"login": "greptile-apps[bot]"},
                        "body": "Review summary",
                        "html_url": "https://example.test/review",
                    },
                    {"user": {"login": "human"}, "body": "Ignore me"},
                ],
                [
                    {
                        "user": {"login": "greptile-apps[bot]"},
                        "body": "Potential boundary issue",
                        "path": "demo-repo/pricing.py",
                        "line": 20,
                    }
                ],
                [],
            ]
        )

        result = load_greptile_review(
            "acme/alibi",
            7,
            runner=lambda *_args, **_kwargs: completed(next(responses)),
        )

        self.assertEqual(result["status"], "available")
        self.assertEqual(len(result["comments"]), 2)
        self.assertEqual(result["comments"][1]["path"], "demo-repo/pricing.py")


if __name__ == "__main__":
    unittest.main()
