"""Standalone Step 3 call-site discovery checkpoint.

The live path queries Greptile. If credentials, indexing, or the request fail,
the standalone command falls back to 3–5 manually curated real call sites and
validates that each one still exists in the checked-out repository. It does
not generate test inputs or feed a later pipeline stage.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from typing import Callable


CALL_SITE_DIRECTORY = Path("demo-repo/call-sites")
DEFAULT_API_URL = "https://api.greptile.com/v2/query"


class CallSiteError(RuntimeError):
    """Raised when checked-in call-site evidence is invalid or stale."""


class GreptileError(RuntimeError):
    """Raised when Greptile cannot complete a call-site query."""


@dataclass(frozen=True)
class CallSite:
    """A source location Greptile returned for a function usage."""

    path: str
    line_start: int | None
    line_end: int | None
    summary: str


def build_prompt(function: str, scope: str | None = None) -> str:
    """Build a narrow prompt that asks only for actual invocations."""
    scope_instruction = (
        f" Focus on usages related to `{scope}`." if scope else ""
    )
    return (
        f"Find every real call site that invokes the function `{function}` in "
        "this repository. Exclude its definition, comments, docstrings, and "
        "mentions that do not execute the function. Return the file path and "
        "exact line range for each invocation, with a brief description of the "
        f"arguments passed.{scope_instruction}"
    )


def build_payload(
    repository: str,
    branch: str,
    function: str,
    scope: str | None = None,
) -> dict[str, object]:
    """Build a non-streaming Greptile Query API request."""
    return {
        "messages": [{"role": "user", "content": build_prompt(function, scope)}],
        "repositories": [
            {
                "remote": "github",
                "repository": repository,
                "branch": branch,
            }
        ],
        "stream": False,
        "genius": False,
    }


def github_token_from_cli() -> str | None:
    """Read the active GitHub CLI token without persisting or printing it."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def parse_response(data: object) -> tuple[str, list[CallSite]]:
    """Normalize Greptile's answer and supporting sources."""
    if not isinstance(data, dict):
        raise GreptileError("Greptile returned a non-object response")

    message = data.get("message", "")
    sources = data.get("sources", [])
    if not isinstance(message, str) or not isinstance(sources, list):
        raise GreptileError("Greptile response has an unexpected shape")

    call_sites = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        path = source.get("filepath")
        if not isinstance(path, str):
            continue
        line_start = source.get("linestart")
        line_end = source.get("lineend")
        summary = source.get("summary", "")
        call_sites.append(
            CallSite(
                path=path,
                line_start=line_start if isinstance(line_start, int) else None,
                line_end=line_end if isinstance(line_end, int) else None,
                summary=summary if isinstance(summary, str) else "",
            )
        )
    return message, call_sites


def find_call_sites(
    *,
    api_key: str,
    github_token: str,
    repository: str,
    branch: str,
    function: str,
    scope: str | None = None,
    api_url: str = DEFAULT_API_URL,
    opener: Callable[..., object] = urllib.request.urlopen,
) -> dict[str, object]:
    """Query Greptile and return JSON-serializable call-site evidence."""
    request = urllib.request.Request(
        api_url,
        data=json.dumps(
            build_payload(repository, branch, function, scope)
        ).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "X-GitHub-Token": github_token,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with opener(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GreptileError(
            f"Greptile request failed with HTTP {exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise GreptileError(f"Could not reach Greptile: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise GreptileError("Greptile returned invalid JSON") from exc

    message, call_sites = parse_response(data)
    if not call_sites:
        raise GreptileError("Greptile returned no call-site sources")
    return {
        "repository": repository,
        "branch": branch,
        "function": function,
        "scope": scope,
        "source": "greptile_live",
        "message": message,
        "call_sites": [asdict(site) for site in call_sites],
    }


def query_greptile_call_sites(
    *,
    repository: str,
    branch: str,
    function: str,
    scope: str | None = "demo-repo/",
    api_url: str = DEFAULT_API_URL,
) -> dict[str, object]:
    """Query Greptile using env credentials or the authenticated GitHub CLI."""
    api_key = os.environ.get("GREPTILE_API_KEY")
    if not api_key:
        raise GreptileError("GREPTILE_API_KEY is not configured")
    github_token = os.environ.get("GITHUB_TOKEN") or github_token_from_cli()
    if not github_token:
        raise GreptileError(
            "GITHUB_TOKEN is not configured and GitHub CLI is not authenticated"
        )
    return find_call_sites(
        api_key=api_key,
        github_token=github_token,
        repository=repository,
        branch=branch,
        function=function,
        scope=scope,
        api_url=api_url,
    )


def _require_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise CallSiteError(f"{field} must be a positive integer")
    return value


def validate_call_site(repo: Path, function: str, site: object) -> None:
    """Confirm one hardcoded location still contains a real invocation."""
    if not isinstance(site, dict):
        raise CallSiteError("each call site must be an object")

    relative_path = site.get("path")
    if not isinstance(relative_path, str) or not relative_path:
        raise CallSiteError("call site path must be a non-empty string")

    repo = repo.resolve()
    source_path = (repo / relative_path).resolve()
    try:
        source_path.relative_to(repo)
    except ValueError as exc:
        raise CallSiteError(f"call site escapes repository: {relative_path}") from exc
    if not source_path.is_file():
        raise CallSiteError(f"call site file does not exist: {relative_path}")

    line_start = _require_int(site.get("line_start"), "line_start")
    line_end = _require_int(site.get("line_end"), "line_end")
    if line_end < line_start:
        raise CallSiteError("line_end must not precede line_start")

    lines = source_path.read_text().splitlines()
    if line_end > len(lines):
        raise CallSiteError(
            f"call site is past end of {relative_path}: {line_start}-{line_end}"
        )
    excerpt = "\n".join(lines[line_start - 1 : line_end])
    if f"{function}(" not in excerpt:
        raise CallSiteError(
            f"stale call site at {relative_path}:{line_start}-{line_end}"
        )


def load_hardcoded_call_sites(repo: Path, function: str) -> dict[str, object]:
    """Load and validate the manual fallback evidence for a function."""
    evidence_path = repo / CALL_SITE_DIRECTORY / f"{function}.json"
    try:
        data = json.loads(evidence_path.read_text())
    except FileNotFoundError as exc:
        raise CallSiteError(
            f"no hardcoded call sites for function: {function}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise CallSiteError(f"invalid JSON in {evidence_path}") from exc

    if not isinstance(data, dict) or data.get("function") != function:
        raise CallSiteError("call-site evidence has the wrong function")
    if data.get("source") != "hardcoded_fallback":
        raise CallSiteError("call-site evidence must identify the fallback source")

    call_sites = data.get("call_sites")
    if not isinstance(call_sites, list) or not 3 <= len(call_sites) <= 5:
        raise CallSiteError("hardcoded fallback must contain 3–5 call sites")
    for site in call_sites:
        validate_call_site(repo, function, site)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find call sites with Greptile, with a validated fallback"
    )
    parser.add_argument("--repository", default="GirikratnaSharma/Alibi")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--function", required=True)
    parser.add_argument("--scope", default="demo-repo/")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    try:
        result = query_greptile_call_sites(
            repository=args.repository,
            branch=args.branch,
            function=args.function,
            scope=args.scope,
            api_url=args.api_url,
        )
    except GreptileError as live_error:
        try:
            result = load_hardcoded_call_sites(repo, args.function)
        except CallSiteError as fallback_error:
            parser.error(f"{live_error}; fallback failed: {fallback_error}")
        result["fallback_reason"] = str(live_error)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
