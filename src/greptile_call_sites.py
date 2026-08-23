"""Find real call sites for a function with Greptile's Query API.

This is intentionally a standalone Step 3 integration. It does not generate
test inputs or feed later pipeline stages yet.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Callable


DEFAULT_API_URL = "https://api.greptile.com/v2/query"


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
        "messages": [
            {
                "role": "user",
                "content": build_prompt(function, scope),
            }
        ],
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

    call_sites: list[CallSite] = []
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
    payload = build_payload(repository, branch, function, scope)
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
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
    return {
        "repository": repository,
        "branch": branch,
        "function": function,
        "scope": scope,
        "message": message,
        "call_sites": [asdict(site) for site in call_sites],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find real function call sites with Greptile"
    )
    parser.add_argument("--repository", default="GirikratnaSharma/Alibi")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--function", required=True)
    parser.add_argument("--scope", default="demo-repo/")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    args = parser.parse_args()

    api_key = os.environ.get("GREPTILE_API_KEY")
    if not api_key:
        parser.error(
            "GREPTILE_API_KEY is required; create one at "
            "https://app.greptile.com/settings/api"
        )
    github_token = os.environ.get("GITHUB_TOKEN") or github_token_from_cli()
    if not github_token:
        parser.error(
            "GITHUB_TOKEN is required, or authenticate the GitHub CLI with "
            "`gh auth login`"
        )

    try:
        result = find_call_sites(
            api_key=api_key,
            github_token=github_token,
            repository=args.repository,
            branch=args.branch,
            function=args.function,
            scope=args.scope,
            api_url=args.api_url,
        )
    except GreptileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
