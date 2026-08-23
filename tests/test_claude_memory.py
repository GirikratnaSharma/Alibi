"""Tests for the optional Claude-Mem classifier-boundary adapter."""

from __future__ import annotations

import json
import unittest
import urllib.error

from src.claude_memory import ClaudeMemClient, MEMORY_KIND


DIVERGENCE = {
    "field": "discount_rate",
    "old_value": 0.15,
    "new_value": 0.2,
    "old_present": True,
    "new_present": True,
}


class FakeResponse:
    def __init__(self, data: object) -> None:
        self.data = data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.data).encode("utf-8")


class ClaudeMemClientTests(unittest.TestCase):
    def test_recall_filters_to_same_function_field_and_value_shape(self) -> None:
        matching = {
            "kind": MEMORY_KIND,
            "function": "calculate_discount",
            "field": "discount_rate",
            "old_value": 0.1,
            "new_value": 0.15,
            "old_shape": {"present": True, "type": "float"},
            "new_shape": {"present": True, "type": "float"},
            "ticket_reference": "demo-repo/tickets/previous.md",
            "classification": "intended",
        }
        wrong_field = {**matching, "field": "final_total"}

        client = ClaudeMemClient(
            base_url="http://memory.test",
            opener=lambda *_args, **_kwargs: FakeResponse(
                {
                    "observations": [
                        {"metadata": json.dumps(matching)},
                        {"metadata": json.dumps(wrong_field)},
                    ]
                }
            ),
        )

        result = client.recall(
            function="calculate_discount", divergence=DIVERGENCE
        )

        self.assertEqual(result, {"status": "recalled", "matches": [matching]})

    def test_store_sends_complete_verdict_record(self) -> None:
        captured = {}

        def opener(request: object, **_kwargs: object) -> FakeResponse:
            captured["request"] = request
            return FakeResponse({"success": True, "id": 42})

        client = ClaudeMemClient(
            base_url="http://memory.test",
            opener=opener,
        )
        result = client.store(
            function="calculate_discount",
            divergence=DIVERGENCE,
            ticket_reference="demo-repo/tickets/001.md",
            classification="intended",
        )

        request = captured["request"]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(result["status"], "stored")
        self.assertEqual(request.full_url, "http://memory.test/api/memory/save")
        self.assertEqual(payload["metadata"]["function"], "calculate_discount")
        self.assertEqual(payload["metadata"]["field"], "discount_rate")
        self.assertEqual(payload["metadata"]["old_value"], 0.15)
        self.assertEqual(payload["metadata"]["new_value"], 0.2)
        self.assertEqual(payload["metadata"]["classification"], "intended")

    def test_unavailable_worker_degrades_to_cold_pipeline_state(self) -> None:
        def unavailable(*_args: object, **_kwargs: object) -> object:
            raise urllib.error.URLError("worker offline")

        client = ClaudeMemClient(
            base_url="http://memory.test",
            opener=unavailable,
        )

        recall = client.recall(
            function="calculate_discount", divergence=DIVERGENCE
        )
        stored = client.store(
            function="calculate_discount",
            divergence=DIVERGENCE,
            ticket_reference="demo-repo/tickets/001.md",
            classification="intended",
        )

        self.assertEqual(recall["status"], "unavailable")
        self.assertEqual(recall["matches"], [])
        self.assertEqual(stored["status"], "unavailable")
