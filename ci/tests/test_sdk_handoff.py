"""SDK caller composition; mocked upload capture does not establish CI authority."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_handoff as caller
from products.inventory import canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from products.signatures import generate_development_key


def captured_fixture(plan, destination, original):
    snapshot_regular_tree(original, destination / "original", allow_empty=True)
    (destination / "plan").mkdir()
    (destination / "plan/impact-plan.json").write_bytes(plan.read_bytes())
    (destination / "transport.zip").write_bytes(b"synthetic captured upload\x00\xff")
    (destination / "capture-transport.json").write_bytes(b'{"synthetic":true}\n')


class SdkHandoffTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-handoff-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.repository = self.work / "repository"
        versions = self.repository / "gradle/release/versions"
        versions.mkdir(parents=True)
        (versions / "sdk.txt").write_bytes(b"0.2.0\n")
        (versions.parent / "sdk-default-runtime.txt").write_bytes(b"0.2.0\n")
        (versions.parent / "sdk-runtime-compatibility.json").write_bytes(canonical_json_bytes({
            "compatibleReleaseRange": ">=0.2.0 <0.4.0",
            "compatibleRuntimeCompatibilityRange": ">=0.2.0 <0.3.0"}))
        for args in (("init", "-q"), ("add", "gradle"),
                     ("-c", "user.name=Synthetic", "-c", "user.email=test@example.invalid",
                      "commit", "-qm", "synthetic policy")):
            subprocess.run(["git", *args], cwd=self.repository, check=True, capture_output=True)
        self.revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repository,
                                      check=True, capture_output=True, text=True).stdout.strip()
        _, public, metadata = generate_development_key(self.work / "key")
        self.keys = self.work / "policy/keys"
        self.keys.mkdir(parents=True)
        (self.keys / f"{metadata['keyId']}.pub").write_bytes(public.read_bytes())
        self.keyring = self.keys.parent / "product-signing-keys.json"
        self.keyring.write_bytes(canonical_json_bytes({"schemaVersion": 1, "trustDomain": "release",
            **{name: metadata[name] for name in ("algorithm", "namespace")},
            "activeKey": {name: metadata[name] for name in ("keyId", "fingerprint")}, "retiredKeys": []}))
        self.plan = self.work / "impact-plan.json"
        self.plan.write_bytes(b'{"synthetic-plan":true}\n')
        self.original = self.work / "original"
        self.original.mkdir()
        (self.original / "empty.log").write_bytes(b"")
        (self.original / "raw.bin").write_bytes(b"original\x00\xff")
        self.output = self.work / "output"
        self.options = dict(artifact_id=42, artifact_sha256="sha256:" + "a" * 64,
            trusted_workflow_sha="b" * 40, expected_build_key="sha256:" + "c" * 64,
            expected_metadata_receipt_sha256="sha256:" + "d" * 64,
            sdk_version="0.2.0", compatible_release_range=">=0.2.0 <0.4.0",
            compatible_runtime_compatibility_range=">=0.2.0 <0.3.0", keyring=self.keyring,
            keys_directory=self.keys, selection_repository_root=self.repository, selection_revision=self.revision,
            repository_root=self.repository, environ={"RUN": "fixture"}, token="synthetic-token")
        self.calls = []

    def capture(self, plan, destination, **arguments):
        self.calls.append("capture")
        self.assertEqual(self.plan, plan)
        self.assertEqual({name: self.options[name] for name in (
            "artifact_id", "artifact_sha256", "trusted_workflow_sha", "expected_build_key",
            "expected_metadata_receipt_sha256", "repository_root", "environ", "token")}, arguments)
        captured_fixture(plan, destination, self.original)

    def bridge(self, original, destination, **arguments):
        self.calls.append("bridge")
        self.assertEqual(["capture", "bridge"], self.calls)
        self.assertEqual(regular_file_inventory(self.original, allow_empty=True),
                         regular_file_inventory(original, allow_empty=True))
        for name in ("expected_build_key", "expected_metadata_receipt_sha256", "sdk_version",
                     "compatible_release_range", "compatible_runtime_compatibility_range",
                     "selection_repository_root", "selection_revision"):
            self.assertEqual(self.options[name], arguments[name])
        self.assertNotEqual(self.keyring, arguments["keyring"])
        self.assertEqual(self.keyring.read_bytes(), arguments["keyring"].read_bytes())
        snapshot_regular_tree(original, destination / "runtime-release", allow_empty=True)
        (destination / "sdk-inputs").mkdir()
        (destination / "sdk-inputs/request.json").write_bytes(b'{"synthetic-sdk":true}\n')
        self.assertFalse(self.output.exists())
        return {"inventory": "explicitly mocked bridge result"}

    def invoke(self, *, capture=None, bridge=None):
        with patch.object(caller.product_reuse, "capture_runtime_aggregate_release_upload",
                          side_effect=capture or self.capture), \
                patch.object(caller, "stage_protected_runtime_sdk_inputs", side_effect=bridge or self.bridge):
            return caller.capture_sdk_handoff(self.plan, self.output, **self.options)

    def test_exact_capture_then_bridge_publishes_one_original_history_and_nonempty_sdk_tree(self):
        before = regular_file_inventory(self.original, allow_empty=True)
        result = self.invoke()
        self.assertEqual(["capture", "bridge"], self.calls)
        self.assertEqual({"runtime-capture", "sdk-inputs"}, {path.name for path in self.output.iterdir()})
        self.assertEqual(before, regular_file_inventory(self.output / "runtime-capture/original", allow_empty=True))
        self.assertEqual(before, regular_file_inventory(self.original, allow_empty=True))
        self.assertEqual(self.plan.read_bytes(), (self.output / "runtime-capture/plan/impact-plan.json").read_bytes())
        self.assertEqual(b"synthetic captured upload\x00\xff", (self.output / "runtime-capture/transport.zip").read_bytes())
        self.assertEqual({"inventory": "explicitly mocked bridge result"}, result)

    def test_capture_or_full_bridge_failure_never_publishes(self):
        for failure in ("capture", "bridge"):
            self.calls.clear()
            with self.subTest(failure=failure), self.assertRaisesRegex(ValueError, "rejected"):
                self.invoke(**{failure: ValueError("rejected")})
            self.assertFalse(self.output.exists())

    def test_caller_cannot_widen_original_git_range_before_capture(self):
        for field in ("compatible_release_range", "compatible_runtime_compatibility_range"):
            original = self.options[field]
            self.options[field] = ">=0.2.0 <0.9.0"
            try:
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.invoke()
                self.assertEqual([], self.calls)
                self.assertFalse(self.output.exists())
            finally:
                self.options[field] = original

    def test_late_original_plan_capture_or_public_policy_mutation_rejects(self):
        for target in ("plan", "capture", "policy"):
            self.calls.clear()
            plan_bytes, policy_bytes = self.plan.read_bytes(), self.keyring.read_bytes()

            def mutate(original, destination, **arguments):
                result = self.bridge(original, destination, **arguments)
                path = {"plan": self.plan, "capture": original / "raw.bin", "policy": self.keyring}[target]
                path.write_bytes(path.read_bytes() + b"mutation\n")
                return result

            try:
                with self.subTest(target=target), self.assertRaisesRegex(ValueError, "changed before publication"):
                    self.invoke(bridge=mutate)
                self.assertFalse(self.output.exists())
            finally:
                self.plan.write_bytes(plan_bytes)
                self.keyring.write_bytes(policy_bytes)

    def test_output_overlap_and_existing_or_symbolic_destination_reject_before_capture(self):
        original_output = self.output
        self.output.mkdir()
        sentinel = self.output / "sentinel"
        sentinel.write_bytes(b"keep\n")
        alias = self.work / "alias"
        alias.symlink_to(self.repository, target_is_directory=True)
        before = regular_file_inventory(self.repository, allow_empty=True)
        for output in (original_output, self.repository / "build/handoff", alias / "handoff"):
            self.output = output
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.invoke()
            self.assertEqual([], self.calls)
        self.assertEqual(b"keep\n", sentinel.read_bytes())
        self.assertEqual(before, regular_file_inventory(self.repository, allow_empty=True))

    def test_cli_requires_and_forwards_every_explicit_caller_policy_field(self):
        options = {name: value for name, value in self.options.items() if name not in {"environ", "token"}}
        argv = ["--plan", str(self.plan), "--destination", str(self.output)]
        for name, value in options.items():
            argv.extend(("--" + name.replace("_", "-"), str(value)))
        with patch.dict(os.environ, {"GITHUB_TOKEN": "caller-token"}, clear=True), \
                patch.object(caller, "capture_sdk_handoff") as capture:
            self.assertEqual(0, caller.main(argv))
            capture.assert_called_once_with(self.plan, self.output, **options,
                                           environ=os.environ, token="caller-token")
        for flag in ("--expected-metadata-receipt-sha256", "--compatible-release-range", "--selection-revision"):
            position = argv.index(flag)
            with self.subTest(flag=flag), patch.object(caller, "capture_sdk_handoff") as capture, \
                    self.assertRaises(SystemExit):
                caller.main(argv[:position] + argv[position + 2:])
            capture.assert_not_called()


class SignedSdkHandoffCompositionTest(unittest.TestCase):
    def test_real_signed_adapter_and_s858_follow_the_single_mocked_upload_capture(self):
        from ci.tests import test_sdk_protected_runtime as fixture
        source = fixture.SdkProtectedRuntimeTest
        source.setUpClass()
        self.addCleanup(source.doClassCleanups)
        with tempfile.TemporaryDirectory(prefix="signed-sdk-handoff-") as temporary:
            work = Path(temporary).resolve()
            plan = work / "impact-plan.json"
            plan.write_bytes(b'{"synthetic-current-plan":true}\n')
            output = work / "output"
            before = regular_file_inventory(source.retained, allow_empty=True)

            def capture(plan_path, destination, **arguments):
                self.assertEqual(source.key, arguments["expected_build_key"])
                self.assertEqual(source.digest, arguments["expected_metadata_receipt_sha256"])
                captured_fixture(plan_path, destination, source.retained)

            with patch.object(caller.product_reuse, "capture_runtime_aggregate_release_upload", side_effect=capture), \
                    patch("reuse.api_request", side_effect=AssertionError("unexpected network")), \
                    patch("products.runtime_aggregate.sign_manifest", side_effect=AssertionError("unexpected signing")):
                caller.capture_sdk_handoff(plan, output, artifact_id=42, artifact_sha256="sha256:" + "a" * 64,
                    trusted_workflow_sha="b" * 40, expected_build_key=source.key,
                    expected_metadata_receipt_sha256=source.digest, sdk_version="0.2.9",
                    compatible_release_range=">=0.2.0 <0.3.0", compatible_runtime_compatibility_range=">=0.2.0 <0.3.0",
                    keyring=source.keyring, keys_directory=source.keys, selection_repository_root=source.selection,
                    selection_revision=source.revision, repository_root=source.source.source.repository,
                    environ={}, token="synthetic-token")
            self.assertEqual(before, regular_file_inventory(source.retained, allow_empty=True))
            self.assertEqual(before, regular_file_inventory(output / "runtime-capture/original", allow_empty=True))
            self.assertTrue((output / "sdk-inputs/sdk-compatibility-request.json").is_file())


if __name__ == "__main__":
    unittest.main()
