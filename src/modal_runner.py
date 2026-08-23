"""Run the old and new demo pricing functions in separate Modal sandboxes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

import modal


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRICING_PATH = Path("demo-repo/pricing.py")
TICKET_PATH = Path("demo-repo/tickets/001-vip-order-discount.md")
APP_NAME = "alibi-pricing-step-4"
SANDBOX_TIMEOUT_SECONDS = 60

# These are the four docstring examples and the two VIP boundary/cap cases
# already established in tests/test_pricing.py. No inputs are generated here.
TEST_INPUTS: list[tuple[float, str, int]] = [
    (80.00, "regular", 2),
    (120.00, "member", 3),
    (200.00, "vip", 5),
    (150.00, "member", 12),
    (100.00, "vip", 1),
    (101.00, "vip", 10),
]

DRIVER_SOURCE = """\
import importlib.util
import json
import sys

spec = importlib.util.spec_from_file_location("sandbox_pricing", "/tmp/pricing.py")
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load /tmp/pricing.py")

pricing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pricing)
inputs = json.loads(sys.argv[1])
outputs = []

for arguments in inputs:
    try:
        outputs.append({
            "status": "ok",
            "value": pricing.calculate_discount(*arguments),
        })
    except Exception as exc:
        outputs.append({
            "status": "error",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        })

print(json.dumps(outputs, separators=(",", ":")))
"""


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def find_old_source_commit() -> tuple[str, str]:
    """Find the commit immediately before Ticket 001 was first added."""
    ticket_commit = _git(
        "log",
        "--diff-filter=A",
        "--format=%H",
        "-1",
        "--",
        str(TICKET_PATH),
    )
    if not ticket_commit:
        raise RuntimeError(f"Could not find the add commit for {TICKET_PATH}")

    old_commit = _git("rev-parse", f"{ticket_commit}^")
    old_message = _git("show", "-s", "--format=%s", old_commit)
    return old_commit, old_message


def load_sources() -> tuple[str, str, str, str]:
    """Load pricing.py from the pre-ticket commit and the working tree."""
    old_commit, old_message = find_old_source_commit()
    old_source = _git("show", f"{old_commit}:{PRICING_PATH}")
    new_source = (REPOSITORY_ROOT / PRICING_PATH).read_text(encoding="utf-8")
    return old_source, new_source, old_commit, old_message


def _write_sandbox_file(sandbox: Any, path: str, contents: str) -> None:
    sandbox_file = sandbox.open(path, "w")
    try:
        sandbox_file.write(contents)
    finally:
        sandbox_file.close()


def _error_details(exc: BaseException, stderr: str = "") -> dict[str, str]:
    details = {
        "type": type(exc).__name__,
        "message": str(exc),
    }
    if stderr:
        details["stderr"] = stderr
    return details


def run_source_in_sandbox(
    function_source: str,
    inputs: Sequence[tuple[float, str, int]],
    *,
    app: Any,
    image: Any,
    sandbox_api: Any = modal.Sandbox,
) -> dict[str, Any]:
    """Run one source version in a fresh sandbox and capture JSON output."""
    sandbox = None
    stderr = ""
    try:
        sandbox = sandbox_api.create(
            app=app,
            image=image,
            timeout=SANDBOX_TIMEOUT_SECONDS,
        )
        _write_sandbox_file(sandbox, "/tmp/pricing.py", function_source)
        _write_sandbox_file(sandbox, "/tmp/driver.py", DRIVER_SOURCE)

        process = sandbox.exec(
            "python",
            "/tmp/driver.py",
            json.dumps(inputs),
            timeout=SANDBOX_TIMEOUT_SECONDS,
        )
        stdout = process.stdout.read()
        stderr = process.stderr.read()
        return_code = process.wait()

        if return_code != 0:
            return {
                "status": "error",
                "error": {
                    "type": "SandboxProcessError",
                    "message": f"Sandbox driver exited with code {return_code}",
                    "stderr": stderr,
                },
            }

        parsed = json.loads(stdout)
        if not isinstance(parsed, list) or len(parsed) != len(inputs):
            raise ValueError(
                "Sandbox driver returned an unexpected number of outputs"
            )
        return {"status": "ok", "outputs": parsed}
    except Exception as exc:
        return {"status": "error", "error": _error_details(exc, stderr)}
    finally:
        if sandbox is not None:
            try:
                sandbox.terminate()
            except Exception:
                pass


def _output_at(run: dict[str, Any], index: int) -> Any:
    if run["status"] != "ok":
        return None
    item = run["outputs"][index]
    if item.get("status") == "ok":
        return item["value"]
    return None


def run_old_vs_new(
    old_source: str,
    new_source: str,
    inputs: Sequence[tuple[float, str, int]],
    *,
    app: Any | None = None,
    image: Any | None = None,
    sandbox_api: Any = modal.Sandbox,
) -> dict[str, Any]:
    """Run OLD once and NEW once, using two separate Modal sandboxes."""
    modal_app = app or modal.App.lookup(APP_NAME, create_if_missing=True)
    modal_image = image or modal.Image.debian_slim()

    old_run = run_source_in_sandbox(
        old_source, inputs, app=modal_app, image=modal_image, sandbox_api=sandbox_api
    )
    new_run = run_source_in_sandbox(
        new_source, inputs, app=modal_app, image=modal_image, sandbox_api=sandbox_api
    )

    results = []
    for index, arguments in enumerate(inputs):
        result = {
            "input": {
                "order_total": arguments[0],
                "customer_type": arguments[1],
                "item_count": arguments[2],
            },
            "old_output": _output_at(old_run, index),
            "new_output": _output_at(new_run, index),
        }
        if old_run["status"] == "ok" and old_run["outputs"][index]["status"] == "error":
            result["old_error"] = old_run["outputs"][index]["error"]
        if new_run["status"] == "ok" and new_run["outputs"][index]["status"] == "error":
            result["new_error"] = new_run["outputs"][index]["error"]
        results.append(result)

    return {
        "runs": {
            "old": {key: value for key, value in old_run.items() if key != "outputs"},
            "new": {key: value for key, value in new_run.items() if key != "outputs"},
        },
        "results": results,
    }


def _missing_modal_environment() -> list[str]:
    return [
        name
        for name in ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET")
        if not os.environ.get(name)
    ]


def main() -> int:
    missing = _missing_modal_environment()
    if missing:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": {
                        "type": "ModalConfigurationError",
                        "message": "Missing required environment variables: "
                        + ", ".join(missing),
                    },
                },
                indent=2,
            )
        )
        return 2

    try:
        old_source, new_source, old_commit, old_message = load_sources()
        output = run_old_vs_new(old_source, new_source, TEST_INPUTS)
        output["old_source"] = {
            "commit": old_commit,
            "message": old_message,
        }
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0 if all(run["status"] == "ok" for run in output["runs"].values()) else 1
    except Exception as exc:
        print(
            json.dumps(
                {"status": "error", "error": _error_details(exc)},
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
