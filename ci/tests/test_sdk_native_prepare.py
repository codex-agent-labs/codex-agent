"""Preparation controls with mocked process/content gates, not product evidence."""

from contextlib import ExitStack
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import product_reuse  # noqa: E402
import sdk_native_prepare as worker  # noqa: E402
from products.inventory import load_canonical_json_bytes, regular_file_inventory, sha256_bytes  # noqa: E402
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS  # noqa: E402
from ci.tests import test_sdk_native_phase as package_fixture  # noqa: E402


class SdkNativePrepareTest(unittest.TestCase):
    # Reuse deterministic receipt/stage fixture methods, not inherited tests.
    setUp = package_fixture.SdkNativePhaseTest.setUp
    predecessor = package_fixture.SdkNativePhaseTest.predecessor

    def fixture(self, language="python"):
        package_fixture.SdkNativePhaseTest.fixture(self, language)
        build = self.root / "codex-agent-sdk/build"
        self.prepared = build / "native-wrapper-package-sources"
        self.staged = build / f"native-wrapper-c-abi-sdks/{self.producer['tree']}"
        self.gate_error = False
        self.after_gate = lambda: None
        self.index_changes = {}

    def process(self, command, **arguments):
        self.calls.append(command)
        self.assertEqual(self.root, arguments["cwd"])
        self.assertEqual({"SAFE": "explicit child environment"}, arguments["env"])
        self.assertFalse(arguments["check"])
        self.assertEqual(subprocess.STDOUT, arguments["stderr"])
        self.assertEqual(".", command[command.index("-p") + 1])
        self.assertIn("--offline", command)
        self.assertEqual(1, command.count(worker.TASK))
        self.assertNotIn("ciProductPhase", command)
        self.assertEqual(worker.TASK, ":codex-agent-sdk:prepareNativeWrapperPackageSources")
        self.assertEqual(dict(value[2:].split("=", 1) for value in command if value.startswith("-P")), {
            "codexAgent.candidateCommit": self.producer["commit"],
            "codexAgent.candidateTree": self.producer["tree"],
            "codexAgent.nativeWrapperRuntimeStageRoot": str(self.runtime),
            "codexAgent.sdkCompatibilityRequest": str(self.request),
        })
        arguments["stdout"].write(b"raw preparation\xff\x00\n")
        if self.launch_error:
            raise OSError("synthetic launch failure")
        if self.return_code == 0:
            for language in NATIVE_BINDINGS:
                directory = self.prepared / language
                directory.mkdir(parents=True)
                (directory / "source").write_bytes(b"synthetic prepared source\n")
            self.staged.mkdir(parents=True)
            (self.staged / "synthetic-sdk").write_bytes(b"synthetic staging\n")
        self.after_process()
        return subprocess.CompletedProcess(command, self.return_code)

    def gate(self, staged, request, runtime, sdk_root_public_key):
        self.assertEqual((self.staged, self.request, self.runtime), (staged, request, runtime))
        self.assertEqual(b"synthetic pinned root\n", sdk_root_public_key)
        if self.gate_error:
            raise ValueError("synthetic staged SDK semantic rejection")
        self.after_gate()
        return {"sdkVersion": "0.3.0", "producerCommit": self.producer["commit"],
                "producerTree": self.producer["tree"], **self.index_changes}

    def invoke(self, **changes):
        arguments = dict(producer=self.producer, sdk_version="0.3.0", repository_root=self.root,
            destination=self.destination, runtime_stages=self.runtime,
            compatibility_request=self.request, predecessor=self.predecessor, environ={})
        with ExitStack() as stack:
            stack.enter_context(patch("native_wrappers.host_classifier", return_value=self.host))
            stack.enter_context(patch.object(product_reuse, "_runtime_worker_environment", return_value=(
                {"SAFE": "explicit child environment"}, self.root / "gradlew")))
            self.checkout = stack.enter_context(patch.object(product_reuse, "_runtime_worker_checkout"))
            stack.enter_context(patch.object(worker, "_request_inventory", side_effect=lambda _: {
                self.request_input: sha256_bytes(self.request_input.read_bytes())}))
            stack.enter_context(patch.object(worker, "git_regular_blob_bytes",
                                            return_value=b"synthetic pinned root\n"))
            self.verifier = stack.enter_context(patch.object(worker, "verify_staged_native_sdk_inputs",
                                                            side_effect=self.gate))
            stack.enter_context(patch.object(worker.subprocess, "run", side_effect=self.process))
            stack.enter_context(patch("products.restore.finalize_phase_object",
                                      side_effect=AssertionError("preparation cannot finalize a phase")))
            return worker.execute(self.plan, **{**arguments, **changes})

    def test_one_fixed_task_prepares_all_languages_without_packaging_or_changing_originals(self):
        before = regular_file_inventory(self.root / "originals")
        imported = regular_file_inventory(self.runtime)
        result = self.invoke()
        self.assertEqual(result, {"preparedSources": self.prepared,
            "preparedSourcesInventory": regular_file_inventory(self.prepared),
            "stagedSdks": self.staged, "stagedSdkInventory": regular_file_inventory(self.staged),
            "diagnostics": self.destination})
        self.assertEqual(set(NATIVE_BINDINGS), {path.name for path in self.prepared.iterdir()})
        self.assertEqual(1, len(self.calls))
        self.verifier.assert_called_once()
        self.assertEqual(set(self.records), set(self.predecessor_calls))
        self.assertEqual(10, len(self.predecessor_calls))
        self.assertEqual(before, regular_file_inventory(self.root / "originals"))
        self.assertEqual(imported, regular_file_inventory(self.runtime))
        self.assertFalse((self.root / "codex-agent-sdk/build/product-stage").exists())
        self.assertFalse((self.destination / "shard").exists())
        self.assertEqual(b"raw preparation\xff\x00\n", (self.destination / "gradle.log").read_bytes())

    def test_wrong_phase_host_or_original_stage_never_runs_preparation(self):
        for kind in ("phase", "language", "host", "receipt", "imported"):
            with self.subTest(kind=kind):
                self.fixture()
                if kind == "phase":
                    self.plan["phase"] = "metadata"
                elif kind == "language":
                    self.plan["component"] = "javascript"
                elif kind == "host":
                    self.host = "linux-arm64"
                elif kind == "receipt":
                    record = next(iter(self.records.values()))
                    record["receipt"] = {**record["receipt"], "target": "wrong-target"}
                else:
                    (self.runtime / NATIVE_TARGETS[0] / "package/outputs/original").write_bytes(b"changed")
                with self.assertRaises(ValueError):
                    self.invoke()
                self.assertEqual([], self.calls)
                self.assertFalse(self.destination.exists())

    def test_failure_and_launch_error_preserve_raw_diagnostics_without_outputs(self):
        for launch in (False, True):
            with self.subTest(launch=launch):
                self.fixture()
                self.return_code, self.launch_error = 9, launch
                with self.assertRaisesRegex(OSError if launch else ValueError,
                                            "launch failure" if launch else "exit code 9"):
                    self.invoke()
                self.assertEqual(b"raw preparation\xff\x00\n", (self.destination / "gradle.log").read_bytes())
                trace = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
                self.assertEqual(None if launch else 9, trace["returnCode"])
                self.verifier.assert_not_called()
                self.assertFalse(self.prepared.exists())

    def test_semantic_gate_and_staging_identity_failures_do_not_return_success(self):
        for kind in ("gate", "version", "commit", "tree"):
            with self.subTest(kind=kind):
                self.fixture()
                if kind == "gate":
                    self.gate_error = True
                else:
                    key = {"version": "sdkVersion", "commit": "producerCommit", "tree": "producerTree"}[kind]
                    self.index_changes[key] = "0.2.0" if kind == "version" else "c" * 40
                with self.assertRaisesRegex(ValueError, "semantic rejection|elected version or producer"):
                    self.invoke()
                self.assertTrue((self.destination / "execution.json").is_file())
                self.assertFalse((self.destination / "shard").exists())

    def test_input_and_prepared_output_mutations_are_rechecked_around_content_gate(self):
        for kind in ("receipt", "request", "request-input", "bytecode", "prepared", "staged"):
            with self.subTest(kind=kind):
                self.fixture()
                record = next(iter(self.records.values()))
                def mutate():
                    path = {"receipt": record["receiptPath"], "request": self.request,
                        "request-input": self.request_input, "bytecode": self.destination / "python-bytecode",
                        "prepared": self.prepared / "python/source", "staged": self.staged / "synthetic-sdk"}[kind]
                    path.write_bytes(b"changed")
                self.after_gate = mutate
                with self.assertRaisesRegex(ValueError, "changed|bytecode"):
                    self.invoke()
                self.assertFalse((self.destination / "shard").exists())

    def test_owned_output_collisions_and_alias_preserve_originals_before_cleanup(self):
        for kind in ("sources", "sdks", "snapshot", "assets", "compatibility", "alias"):
            with self.subTest(kind=kind):
                self.fixture()
                build = self.root / "codex-agent-sdk/build"
                path = {"sources": self.prepared, "sdks": self.staged,
                    "snapshot": build / f"imported-native-wrapper-runtime-stages/{self.producer['tree']}",
                    "assets": build / f"native-wrapper-package-assets/{self.producer['tree']}",
                    "compatibility": build / f"sdk-compatibility/{self.producer['tree']}",
                    "alias": self.prepared}[kind]
                if kind == "alias":
                    path.parent.mkdir(parents=True)
                    path.symlink_to(self.runtime, target_is_directory=True)
                else:
                    path.mkdir(parents=True)
                    (path / "sentinel").write_bytes(b"original")
                before = regular_file_inventory(self.runtime)
                with self.assertRaisesRegex(ValueError, "fresh"):
                    self.invoke()
                self.assertEqual([], self.calls)
                self.assertEqual(before, regular_file_inventory(self.runtime))
                if kind != "alias":
                    self.assertEqual(b"original", (path / "sentinel").read_bytes())

    def test_missing_or_extra_language_output_rejects_before_content_gate(self):
        for extra in (False, True):
            with self.subTest(extra=extra):
                self.fixture()
                def mutate():
                    if extra:
                        (self.prepared / "unexpected").mkdir()
                    else:
                        (self.prepared / "python").rename(self.prepared / "not-python")
                self.after_process = mutate
                with self.assertRaisesRegex(ValueError, "exactly five"):
                    self.invoke()
                self.verifier.assert_not_called()


if __name__ == "__main__":
    unittest.main()
