"""Read-only GitHub pull-request and Greptile review ingestion."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


Runner = Callable[..., subprocess.CompletedProcess[str]]


class PullRequestError(RuntimeError):
    """Raised when a pull request cannot be loaded or validated."""


def _run_json(
    arguments: Sequence[str],
    *,
    runner: Runner = subprocess.run,
    cwd: Path | None = None,
) -> object:
    completed = runner(
        list(arguments),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise PullRequestError("GitHub CLI returned invalid JSON") from exc


def load_pull_request(
    repository: str,
    number: int,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Load the immutable base/head SHAs and ticket text for one PR."""
    if number < 1:
        raise ValueError("pull request number must be positive")
    if repository.count("/") != 1:
        raise ValueError("repository must use owner/name form")
    try:
        data = _run_json(
            [
                "gh",
                "pr",
                "view",
                str(number),
                "--repo",
                repository,
                "--json",
                (
                    "number,title,body,url,state,baseRefName,headRefName,"
                    "baseRefOid,headRefOid,files"
                ),
            ],
            runner=runner,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise PullRequestError(f"Could not load pull request #{number}") from exc

    if not isinstance(data, dict):
        raise PullRequestError("GitHub CLI returned a non-object pull request")
    required_strings = ("title", "url", "baseRefOid", "headRefOid")
    if any(not isinstance(data.get(field), str) or not data[field] for field in required_strings):
        raise PullRequestError("Pull request is missing required base/head metadata")

    files = data.get("files", [])
    if not isinstance(files, list):
        raise PullRequestError("Pull request files must be a list")
    normalized_files = []
    for item in files:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            normalized_files.append(
                {
                    "path": item["path"],
                    "additions": item.get("additions", 0),
                    "deletions": item.get("deletions", 0),
                }
            )

    return {
        "repository": repository,
        "number": data.get("number", number),
        "title": data["title"],
        "body": data.get("body") if isinstance(data.get("body"), str) else "",
        "url": data["url"],
        "state": data.get("state", "UNKNOWN"),
        "base_ref": data.get("baseRefName", ""),
        "head_ref": data.get("headRefName", ""),
        "base_sha": data["baseRefOid"],
        "head_sha": data["headRefOid"],
        "files": normalized_files,
    }


def _is_greptile_author(author: object) -> bool:
    if not isinstance(author, Mapping):
        return False
    identity = " ".join(
        str(author.get(field, "")) for field in ("login", "name", "slug")
    ).lower()
    return "greptile" in identity


def _normalize_review_items(items: object, kind: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    reviews = []
    for item in items:
        if not isinstance(item, dict) or not _is_greptile_author(item.get("user")):
            continue
        body = item.get("body")
        if not isinstance(body, str) or not body.strip():
            continue
        reviews.append(
            {
                "kind": kind,
                "body": body.strip()[:8_000],
                "path": item.get("path") if isinstance(item.get("path"), str) else None,
                "line": item.get("line") if isinstance(item.get("line"), int) else None,
                "url": item.get("html_url") if isinstance(item.get("html_url"), str) else None,
            }
        )
    return reviews


def load_greptile_review(
    repository: str,
    number: int,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Collect Greptile-authored PR reviews and comments from GitHub."""
    endpoints = (
        (f"repos/{repository}/pulls/{number}/reviews", "review"),
        (f"repos/{repository}/pulls/{number}/comments", "inline_comment"),
        (f"repos/{repository}/issues/{number}/comments", "issue_comment"),
    )
    comments: list[dict[str, Any]] = []
    try:
        for endpoint, kind in endpoints:
            items = _run_json(
                [
                    "gh",
                    "api",
                    "--method",
                    "GET",
                    endpoint,
                    "-f",
                    "per_page=100",
                ],
                runner=runner,
            )
            comments.extend(_normalize_review_items(items, kind))
    except (FileNotFoundError, subprocess.CalledProcessError, PullRequestError) as exc:
        return {
            "status": "unavailable",
            "comments": [],
            "reason": f"{type(exc).__name__}: {exc}",
        }
    return {
        "status": "available" if comments else "not_found",
        "comments": comments,
    }


def ensure_commit(repo: Path, revision: str, *, fetch_ref: str | None = None) -> None:
    """Ensure a PR revision is local, fetching one narrow ref when necessary."""
    completed = subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return
    if fetch_ref:
        fetched = subprocess.run(
            ["git", "fetch", "--no-tags", "origin", fetch_ref],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if fetched.returncode == 0:
            completed = subprocess.run(
                ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
                cwd=repo,
                capture_output=True,
                text=True,
            )
            if completed.returncode == 0:
                return
    raise PullRequestError(
        f"PR commit {revision} is not available in the local clone"
    )
