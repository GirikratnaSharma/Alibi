"""Tests for the Step 4 Modal runner without live Modal access."""

from __future__ import annotations

import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src import modal_runner


class _LocalSandboxFile:
    def __init__(self, local_path: Path) -> None:
        self._file = local_path.open("w", encoding="utf-8")

    def write(self, contents: str) -> None:
        self._file.write(contents)

    def close(self) -> None:
        self._file.close()


class _LocalProcess:
    def __init__(self, completed: subprocess.CompletedProcess[str]) -> None:
        self.stdout = io.StringIO(completed.stdout)
        self.stderr = io.StringIO(completed.stderr)
        self._return_code = completed.returncode

    def wait(self) -> int:
        return self._return_code


class _LocalSandbox:
    instances: list["_LocalSandbox"] = []

    def __init__(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary_directory.name)
        self.terminated = False
        self.__class__.instances.append(self)

    def open(self, path: str, mode: str) -> _LocalSandboxFile:
        assert mode == "w"
        return _LocalSandboxFile(self.root / Path(path).name)

    def exec(self, *args: str, **kwargs: object) -> _LocalProcess:
        del kwargs
        command = [
            args[0],
            str(self.root / Path(args[1]).name),
            *args[2:],
        ]
        driver = (self.root / "driver.py").read_text(encoding="utf-8")
        driver = driver.replace("/tmp/pricing.py", str(self.root / "pricing.py"))
        (self.root / "driver.py").write_text(driver, encoding="utf-8")
        completed = subprocess.run(command, capture_output=True, text=True)
        return _LocalProcess(completed)

    def terminate(self) -> None:
        self.terminated = True


class _MockSandboxApi:
    @staticmethod
    def create(**kwargs: object) -> _LocalSandbox:
        del kwargs
        return _LocalSandbox()


class ModalRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        _LocalSandbox.instances.clear()

    def tearDown(self) -> None:
        for sandbox in _LocalSandbox.instances:
            sandbox._temporary_directory.cleanup()

    @mock.patch.object(modal_runner.modal.Image, "debian_slim")
    @mock.patch.object(modal_runner.modal.App, "lookup")
    def test_driver_json_parsing_with_two_separate_mocked_sandboxes(
        self, lookup: mock.Mock, debian_slim: mock.Mock
    ) -> None:
        lookup.return_value = object()
        debian_slim.return_value = object()
        old_source, new_source, _, _ = modal_runner.load_sources()

        output = modal_runner.run_old_vs_new(
            old_source,
            new_source,
            modal_runner.TEST_INPUTS,
            sandbox_api=_MockSandboxApi,
        )

        self.assertEqual(output["runs"], {
            "old": {"status": "ok"},
            "new": {"status": "ok"},
        })
        self.assertEqual(len(_LocalSandbox.instances), 2)
        self.assertIsNot(_LocalSandbox.instances[0], _LocalSandbox.instances[1])
        self.assertTrue(all(sandbox.terminated for sandbox in _LocalSandbox.instances))
        self.assertEqual(
            output["results"][2],
            {
                "input": {
                    "order_total": 200.0,
                    "customer_type": "vip",
                    "item_count": 5,
                },
                "old_output": {
                    "discount_rate": 0.15,
                    "discount_amount": 30.0,
                    "final_total": 170.0,
                },
                "new_output": {
                    "discount_rate": 0.2,
                    "discount_amount": 40.0,
                    "final_total": 160.0,
                },
            },
        )

    def test_sandbox_failure_is_structured(self) -> None:
        class FailingSandboxApi:
            @staticmethod
            def create(**kwargs: object) -> None:
                del kwargs
                raise TimeoutError("sandbox timed out")

        run = modal_runner.run_source_in_sandbox(
            "function source",
            modal_runner.TEST_INPUTS,
            app=object(),
            image=object(),
            sandbox_api=FailingSandboxApi,
        )

        self.assertEqual(run["status"], "error")
        self.assertEqual(run["error"]["type"], "TimeoutError")
        self.assertIn("timed out", run["error"]["message"])


if __name__ == "__main__":
    unittest.main()
