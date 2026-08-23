"""Standalone Step 3 checked-in call-site evidence checkpoint.

Greptile deprecated its codebase Query API and directed this project to its PR
review product instead. PR review is a side-by-side demo comparison and never
feeds Alibi's pipeline. The pipeline's sole call-site source is therefore the
3–5 manually curated locations validated by this module.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CALL_SITE_DIRECTORY = Path("demo-repo/call-sites")


class CallSiteError(RuntimeError):
    """Raised when checked-in call-site evidence is invalid or stale."""


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
    """Load and validate the pipeline's sole call-site evidence source."""
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
        description=(
            "Validate checked-in call sites; Greptile's Query API is deprecated"
        )
    )
    parser.add_argument("--function", required=True)
    args = parser.parse_args()

    repo = Path(__file__).resolve().parents[1]
    try:
        result = load_hardcoded_call_sites(repo, args.function)
    except CallSiteError as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
