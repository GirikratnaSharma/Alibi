"""Optional Claude-Mem recall/store adapter for divergence verdicts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Mapping


PROJECT_NAME = "Alibi"
MEMORY_KIND = "alibi_divergence_verdict"


def _value_shape(value: Any, present: bool) -> dict[str, Any]:
    return {"present": present, "type": type(value).__name__}


def default_worker_url() -> str:
    """Resolve Claude-Mem's local worker without requiring its installation."""
    configured_url = os.environ.get("CLAUDE_MEM_URL")
    if configured_url:
        return configured_url.rstrip("/")

    configured_port = os.environ.get("CLAUDE_MEM_WORKER_PORT")
    if not configured_port:
        settings_path = Path.home() / ".claude-mem" / "settings.json"
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            configured_port = settings.get("CLAUDE_MEM_WORKER_PORT")
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            configured_port = None

    if not configured_port:
        getuid = getattr(os, "getuid", None)
        configured_port = 37700 + (getuid() % 100) if getuid else 37777
    return f"http://127.0.0.1:{configured_port}"


class ClaudeMemClient:
    """Best-effort client that never makes memory a pipeline dependency."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        project: str = PROJECT_NAME,
        timeout: float = 1.0,
        opener: Callable[..., object] = urllib.request.urlopen,
    ) -> None:
        self.base_url = (base_url or default_worker_url()).rstrip("/")
        self.project = project
        self.timeout = timeout
        self.opener = opener

    def _request_json(self, request: urllib.request.Request) -> object:
        with self.opener(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _record_from_observation(observation: object) -> dict[str, Any] | None:
        if not isinstance(observation, dict):
            return None

        candidates = [observation.get("metadata"), observation.get("narrative")]
        for candidate in candidates:
            if isinstance(candidate, str):
                try:
                    candidate = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
            if isinstance(candidate, dict) and candidate.get("kind") == MEMORY_KIND:
                return dict(candidate)
        return None

    def recall(
        self,
        *,
        function: str,
        divergence: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Recall prior judgments matching function, field, and value shape."""
        old_shape = _value_shape(
            divergence.get("old_value"), divergence.get("old_present", True)
        )
        new_shape = _value_shape(
            divergence.get("new_value"), divergence.get("new_present", True)
        )
        field = str(divergence["field"])
        query = " ".join(
            [
                MEMORY_KIND,
                function,
                field,
                str(old_shape["type"]),
                str(new_shape["type"]),
            ]
        )
        url = f"{self.base_url}/api/search?{urllib.parse.urlencode({
            'query': query,
            'project': self.project,
            'type': 'observations',
            'limit': 5,
            'format': 'json',
        })}"
        request = urllib.request.Request(url, method="GET")

        try:
            data = self._request_json(request)
            observations = data.get("observations", []) if isinstance(data, dict) else []
            matches = []
            for observation in observations if isinstance(observations, list) else []:
                record = self._record_from_observation(observation)
                if not record:
                    continue
                if (
                    record.get("function") == function
                    and record.get("field") == field
                    and record.get("old_shape") == old_shape
                    and record.get("new_shape") == new_shape
                    and record.get("classification") in ("intended", "unintended")
                ):
                    matches.append(record)
            return {
                "status": "recalled" if matches else "cold_start",
                "matches": matches,
            }
        except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            return {
                "status": "unavailable",
                "matches": [],
                "reason": f"{type(exc).__name__}: {exc}",
            }

    def store(
        self,
        *,
        function: str,
        divergence: Mapping[str, Any],
        ticket_reference: str,
        classification: str,
    ) -> dict[str, Any]:
        """Store one classification, failing open when Claude-Mem is absent."""
        record = {
            "kind": MEMORY_KIND,
            "function": function,
            "field": divergence["field"],
            "old_value": divergence.get("old_value"),
            "new_value": divergence.get("new_value"),
            "old_shape": _value_shape(
                divergence.get("old_value"), divergence.get("old_present", True)
            ),
            "new_shape": _value_shape(
                divergence.get("new_value"), divergence.get("new_present", True)
            ),
            "ticket_reference": ticket_reference,
            "classification": classification,
        }
        payload = {
            "text": json.dumps(record, sort_keys=True),
            "title": f"Alibi verdict: {function}.{divergence['field']}",
            "project": self.project,
            "metadata": record,
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/memory/save",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            data = self._request_json(request)
            return {"status": "stored", "response": data}
        except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
            return {
                "status": "unavailable",
                "reason": f"{type(exc).__name__}: {exc}",
            }
