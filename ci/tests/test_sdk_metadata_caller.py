"""Selected-state SDK caller routing; replay/projection/execution seams are mocked."""

from contextlib import ExitStack
from pathlib import Path
import os
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.tests.test_runtime_phase_execution import adapter
from products.inventory import canonical_json_bytes, sha256_bytes
from products.registry import NATIVE_TARGETS, PhaseInstanceId


class SdkMetadataCallerTest(unittest.TestCase):
    def test_clean_script_and_package_imports_and_metadata_cli_help(self):
        repository = Path(__file__).resolve().parents[2]
        environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
        for command in (
            [sys.executable, "-B", "-c", "import ci.products.tooling; import ci.products.sdk_native_metadata_admission"],
            [sys.executable, "-B", "-c", "import sys; sys.path.insert(0, 'ci'); import sdk_metadata_phase"],
            [sys.executable, "-B", "ci/product_reuse.py", "execute-sdk-metadata", "--help"],
        ):
            with self.subTest(command=command):
                result = subprocess.run(command, cwd=repository, env=environment, capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stderr)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sdk-metadata-caller-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        for name in ("discovery", "state", "runtime", "sdks"):
            (self.root / name).mkdir()
        (self.root / "request.json").write_bytes(b"{}\n")
        self.instance = PhaseInstanceId("sdk", "python", "metadata", "desktop")
        self.ready = {"product": "sdk", "component": "python", "phase": "metadata", "target": "desktop",
                      "buildKey": "sha256:" + "a" * 64}
        self.producer = {"commit": "a" * 40, "tree": "b" * 40}
        self.state = SimpleNamespace(plan={"event": "merge_group"}, prior_ready_plans={self.instance: self.ready}, producer=self.producer,
            expected_fixed={"versions": {"sdk": "0.2.0"}}, rebased_request={"sdkValidationEvidence": []})
        self.tooling = {"evidence": str(self.root / "tooling"), "publicKey": str(self.root / "key.pub"),
            "javaExecutable": str(self.root / "java"), "requiredTrustDomain": "release",
            "keyring": str(self.root / "keys.json"), "keysDirectory": str(self.root / "keys")}
        self.originals = {}
        self.proofs = {target: object() for target in NATIVE_TARGETS}

    def materialize(self, state, instance, destination, key, root):
        self.assertIs(state, self.state)
        self.assertEqual(self.instance, instance)
        self.assertEqual(self.ready["buildKey"], key)
        for phase, target in [("package", "desktop"), *[("validation", target) for target in NATIVE_TARGETS]]:
            directory = destination / f"sdk-python-{phase}-{target}"
            (directory / "stage").mkdir(parents=True)
            receipt = {"product": "sdk", "component": "python", "phase": phase, "target": target}
            path = directory / "phase-receipt.json"
            path.write_bytes(canonical_json_bytes(receipt))
            self.originals[path] = receipt
        return self.ready

    def invoke(self, **changes):
        return adapter.execute_sdk_metadata(self.root / "plan.json", self.root / "discovery", self.root / "state",
            self.root / "result", **{"component": "python", "expected_build_key": self.ready["buildKey"],
            "compatibility_request": self.root / "request.json", "runtime_stages": self.root / "runtime",
            "staged_sdks": self.root / "sdks", "sdk_validation_tooling": self.tooling,
            "repository_root": self.root, "environ": {}, **changes})

    def seams(self, *, provider=True):
        stack = ExitStack()
        self.addCleanup(stack.close)
        replay = stack.enter_context(patch.object(adapter, "_verified_product_state", return_value=self.state))
        stack.enter_context(patch.object(adapter, "_runtime_worker_checkout"))
        materialize = stack.enter_context(patch.object(adapter, "_materialize_product_predecessors", side_effect=self.materialize))
        stack.enter_context(patch.object(adapter, "_retained_sdk_handoffs", return_value=[]))
        stack.enter_context(patch.object(adapter, "_canonical_control", side_effect=lambda path, _label: self.originals[path]))
        stack.enter_context(patch.object(adapter, "validate_phase_receipt", side_effect=lambda receipt: receipt))
        def projection(entry):
            receipt = {key: entry[key] for key in ("product", "component", "phase", "target")}
            self.assertEqual(sha256_bytes(canonical_json_bytes(receipt)), entry["receiptSha256"])
            return self.proofs[entry["target"]]
        stack.enter_context(patch("products.sdk_validation.sdk_validation_provider",
                                 return_value=projection if provider else None))
        execute = stack.enter_context(patch("sdk_metadata_phase.execute", return_value={"result": "fixture"}))
        return replay, materialize, execute

    def test_exact_election_restores_originals_and_passes_existing_host_proofs(self):
        replay, materialize, execute = self.seams()
        self.assertEqual({"result": "fixture"}, self.invoke())
        replay.assert_called_once()
        materialize.assert_called_once()
        args, values = execute.call_args
        self.assertEqual((self.ready,), args)
        self.assertEqual(self.producer, values["producer"])
        self.assertEqual("release", values["trust_domain"])
        self.assertEqual(tuple(self.proofs[target] for target in sorted(NATIVE_TARGETS)), values["sdk_validation_projections"])
        original = values["predecessor"]("sdk", "python", "package", "desktop")
        self.assertEqual("package", original["receipt"]["phase"])
        with self.assertRaisesRegex(ValueError, "unrelated direct predecessor"):
            values["predecessor"]("sdk", "rust", "package", "desktop")

    def test_non_elected_or_wrong_key_never_materializes_or_executes(self):
        _, materialize, execute = self.seams()
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.invoke(expected_build_key="sha256:" + "f" * 64)
        self.state.prior_ready_plans = {}
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.invoke()
        materialize.assert_not_called()
        execute.assert_not_called()

    def test_cli_forwards_only_explicit_metadata_inputs_to_elected_caller(self):
        with patch.object(adapter, "_canonical_control", return_value=self.tooling), \
                patch.object(adapter, "execute_sdk_metadata") as execute:
            self.assertEqual(0, adapter.main([
                "execute-sdk-metadata", "--plan", "plan", "--discovery-root", "discovery",
                "--state-root", "state", "--destination", "output", "--component", "python",
                "--expected-build-key", self.ready["buildKey"], "--compatibility-request", "request",
                "--runtime-stages", "runtime", "--staged-sdks", "sdks", "--sdk-validation-tooling", "tooling",
            ]))
            execute.assert_called_once_with(Path("plan"), Path("discovery"), Path("state"), Path("output"),
                component="python", expected_build_key=self.ready["buildKey"], compatibility_request=Path("request"),
                runtime_stages=Path("runtime"), staged_sdks=Path("sdks"), sdk_validation_tooling=self.tooling,
                sdk_original_workflow_sha=None)

    def test_pr_metadata_keeps_development_receipt_trust(self):
        self.state.plan["event"] = "pull_request"
        _, _, execute = self.seams()
        self.invoke()
        self.assertEqual("development", execute.call_args.kwargs["trust_domain"])

    def test_missing_full_host_provider_never_executes(self):
        _, _, execute = self.seams(provider=False)
        with self.assertRaisesRegex(ValueError, "authenticated original host"):
            self.invoke()
        execute.assert_not_called()

    def test_failed_state_replay_and_existing_destination_never_execute(self):
        replay, _, execute = self.seams()
        replay.side_effect = ValueError("invalid original state")
        with self.assertRaisesRegex(ValueError, "invalid original state"):
            self.invoke()
        (self.root / "result").mkdir()
        with self.assertRaisesRegex(ValueError, "destination must not exist"):
            self.invoke()
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
