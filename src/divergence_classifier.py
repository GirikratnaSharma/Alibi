"""Narrow LLM classification of confirmed Step 5 divergences.

This is the only Step 6 module that calls a model. It receives comparison
evidence from the deterministic diff engine and never re-runs that comparison.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence


Classification = Literal["intended", "unintended"]

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "classification": {
            "type": "string",
            "enum": ["intended", "unintended"],
        }
    },
    "required": ["classification"],
    "additionalProperties": False,
}


def build_prompt(
    divergence: Mapping[str, Any],
    ticket_text: str,
    *,
    input_evidence: Mapping[str, Any] | None = None,
    recalled_context: Sequence[Mapping[str, Any]] = (),
) -> str:
    """Build a prompt that judges intent without repeating comparison work."""
    required = {"field", "old_value", "new_value"}
    if not required.issubset(divergence):
        missing = ", ".join(sorted(required - divergence.keys()))
        raise ValueError(f"confirmed divergence is missing: {missing}")
    if not ticket_text.strip():
        raise ValueError("ticket text must not be empty")

    evidence = {
        "input": dict(input_evidence) if input_evidence is not None else None,
        "confirmed_divergence": {
            "field": divergence["field"],
            "old_value": divergence["old_value"],
            "new_value": divergence["new_value"],
            "old_present": divergence.get("old_present", True),
            "new_present": divergence.get("new_present", True),
        },
    }
    prior_judgments = [dict(item) for item in recalled_context]
    return f"""You are a narrow intent classifier for a confirmed code-behavior divergence.

The deterministic diff engine has already established the exact OLD and NEW
values below. Do not re-run, recalculate, dispute, or re-check that comparison.
Do not inspect code, files, tests, or any outside context.

Judge only whether this confirmed field change is requested by, or is a direct
necessary consequence of, the original ticket.

Prior judgments, when supplied, are advisory context only. Make your own
judgment from the current ticket and confirmed divergence. Never copy or defer
to a prior classification when it conflicts with the current ticket.

- Return `intended` when it matches the requested behavior.
- Return `unintended` when it is outside the request or contradicts behavior
  the ticket says must remain unchanged.

Original ticket:
<ticket>
{ticket_text.strip()}
</ticket>

Confirmed evidence:
{json.dumps(evidence, indent=2, sort_keys=True)}

Prior judgments for a similar function/field/value shape:
{json.dumps(prior_judgments, indent=2, sort_keys=True)}

Return only the JSON object required by the supplied output schema.
"""


def classify_divergence(
    divergence: Mapping[str, Any],
    ticket_text: str,
    *,
    input_evidence: Mapping[str, Any] | None = None,
    recalled_context: Sequence[Mapping[str, Any]] = (),
    codex_executable: str | None = None,
) -> Classification:
    """Classify one confirmed divergence with an ephemeral Codex invocation."""
    executable = codex_executable or shutil.which("codex")
    if not executable:
        raise RuntimeError("Codex CLI is required for divergence classification")

    prompt = build_prompt(
        divergence,
        ticket_text,
        input_evidence=input_evidence,
        recalled_context=recalled_context,
    )
    with tempfile.TemporaryDirectory(prefix="alibi-classifier-") as directory:
        workdir = Path(directory)
        schema_path = workdir / "output-schema.json"
        result_path = workdir / "result.json"
        schema_path.write_text(json.dumps(OUTPUT_SCHEMA), encoding="utf-8")

        completed = subprocess.run(
            [
                executable,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(result_path),
                "-",
            ],
            cwd=workdir,
            input=prompt,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"Codex classifier failed: {detail}")

        try:
            response = json.loads(result_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise RuntimeError("Codex classifier returned invalid JSON") from exc

    classification = response.get("classification")
    if classification not in ("intended", "unintended"):
        raise RuntimeError("Codex classifier returned an invalid classification")
    return classification
