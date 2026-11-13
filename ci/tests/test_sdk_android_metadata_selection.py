"""Android metadata selection from an independently authenticated state root."""

from copy import deepcopy
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_android_metadata_selection as selection
from ci.products.inventory import (
    load_canonical_json_bytes, sha256_bytes, write_canonical_json,
)
from products.restore import verify_phase_shard
from ci.tests import test_sdk_android_metadata_original as fixtures


class AndroidMetadataSelectionTest(unittest.TestCase):
    def setUp(self):
        # Reuse the genuine metadata/validation fixture without importing its
        # TestCase into this module's discovery namespace.
        self.f = fixtures.AndroidMetadataOriginalTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        temporary = tempfile.TemporaryDirectory(prefix="android-metadata-selection-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.state = self.root / "authenticated-state"
        self.carrier = self.state / "sdk-metadata-evidence/0"
        self.capture = self.carrier / "capture"
        self.carrier.mkdir(parents=True)
        shutil.copytree(self.f.retained_capture, self.capture)
        self.receipt = self.carrier / "receipt.json"
        self.receipt.write_bytes(self.f.receipt_path.read_bytes())
        validation_transport = self.capture / "original/originals/validation/capture-transport.json"
        transport = load_canonical_json_bytes(validation_transport.read_bytes())
        transport["artifact"] = {"id": 77, "digest": "sha256:" + "7" * 64}
        write_canonical_json(validation_transport, transport)
        self.record = {
            "component": "sdk-android", "phase": "metadata", "target": "android",
            "receiptSha256": sha256_bytes(self.receipt.read_bytes()),
            "receipt": "receipt.json", "capture": "capture",
        }
        shard = verify_phase_shard(self.capture / "original/shard", selection._METADATA)
        self.destination = self.root / "policy"
        workflow = self.f.f
        self.arguments = dict(
            plan=self.f.recovery_plan, authenticated_state_root=self.state,
            destination=self.destination, expected_build_key=shard["buildKey"],
            metadata_receipt_sha256=shard["receiptSha256"],
            metadata_object_sha256=shard["objectSha256"],
            trusted_workflow_sha="8" * 40,
            trusted_android_workflow_sha="9" * 40,
            expected_original_run_id=workflow.validation_producer["runId"],
            expected_original_run_attempt=workflow.validation_producer["runAttempt"],
            package_stage=workflow.package_stage,
            package_receipt=workflow.package_receipt,
            binary_stage=workflow.binary_stage, binary_receipt=workflow.binary_receipt,
            compatibility_request=workflow.compatibility,
            binary_contract_evidence=deepcopy(workflow.contract_evidence),
            trusted_source_commit="e" * 40, trusted_source_tree="f" * 40,
            original_context=deepcopy(self.f.context), tooling_evidence=workflow.tooling,
            tooling_public_key=workflow.tooling_key, java_executable=workflow.java,
            apkanalyzer_executable=workflow.analyzer,
            required_trust_domain="development", repository_root=workflow.root,
            environ={}, token="caller observation token")
        self.loader = self.enterContext(patch.object(
            selection, "load_sdk_metadata_evidence", return_value=[self.record]))
        self.compatibility_marker = self.root / "s858-execution-closure/new-proof.bin"
        self.request_inventory = self.enterContext(patch.object(
            selection, "_request_inventory", side_effect=lambda request: (
                {} if not self.compatibility_marker.exists() else
                {self.compatibility_marker: "sha256:" + "6" * 64})))
        self.checkout = {"commit": "a" * 40, "tree": "b" * 40}
        self.enterContext(patch.object(
            selection.product_reuse, "_validate_plan", return_value={
                "validationCommit": self.checkout["commit"],
                "validationTree": self.checkout["tree"],
            }))
        self.enterContext(patch.object(
            selection.product_reuse, "_git_value", side_effect=lambda root, op, revision:
            self.checkout["tree" if revision.endswith("{tree}") else "commit"]))
        self.created = {"evidenceRoot": str(self.carrier), "records": [], "policy": {}}

        def create(*args, **kwargs):
            private_output = Path(args[4])
            private_output.mkdir()
            write_canonical_json(
                private_output / selection.POLICY_NAME, self.created)
            return deepcopy(self.created)

        self.producer = self.enterContext(patch.object(
            selection, "create_sdk_android_metadata_policy", side_effect=create))

    def call(self, **changes):
        return selection.create_selected_sdk_android_metadata_policy(
            **{**self.arguments, **changes})

    def test_exact_election_selects_locator_but_preserves_caller_authority(self):
        self.assertEqual(self.created, self.call())
        self.loader.assert_called_once_with(self.carrier)
        args, kwargs = self.producer.call_args
        self.assertEqual((self.f.recovery_plan, self.carrier,
                          self.capture / "original/inputs/sdk-sdk-android-validation-android/phase-receipt.json",
                          self.capture / "original/originals/validation"), args[:4])
        self.assertNotEqual(self.destination, args[4])
        self.assertEqual(
            self.created,
            load_canonical_json_bytes(
                (self.destination / selection.POLICY_NAME).read_bytes()))
        self.assertEqual(77, kwargs["validation_artifact_id"])
        self.assertEqual("sha256:" + "7" * 64, kwargs["validation_artifact_sha256"])
        for name in ("trusted_workflow_sha", "trusted_android_workflow_sha",
                     "expected_original_run_id", "expected_original_run_attempt",
                     "trusted_source_commit", "trusted_source_tree", "original_context"):
            self.assertEqual(self.arguments[name], kwargs[name])

    def test_wrong_election_or_duplicate_index_fails_before_policy(self):
        for name, value in (
                ("expected_build_key", "sha256:" + "1" * 64),
                ("metadata_receipt_sha256", "sha256:" + "2" * 64),
                ("metadata_object_sha256", "sha256:" + "3" * 64)):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "elect"):
                self.call(**{name: value})
        self.loader.return_value = [self.record, deepcopy(self.record)]
        with self.assertRaisesRegex(ValueError, "one exact elected"):
            self.call()
        self.producer.assert_not_called()

    def test_transport_producer_and_validation_upstream_are_bound(self):
        path = self.capture / "capture-transport.json"
        original = path.read_bytes()
        value = load_canonical_json_bytes(original)
        value["captureProducer"]["runAttempt"] += 1
        write_canonical_json(path, value)
        with self.assertRaisesRegex(ValueError, "metadata transport"):
            self.call()
        path.write_bytes(original)

        validation = self.capture / "original/inputs/sdk-sdk-android-validation-android/phase-receipt.json"
        original = validation.read_bytes()
        value = load_canonical_json_bytes(original)
        value["productVersion"] = "99.0.0"
        write_canonical_json(validation, value)
        with self.assertRaises(ValueError):
            self.call()
        validation.write_bytes(original)
        self.producer.assert_not_called()

    def test_state_lifetime_and_output_separation_fail_closed(self):
        publish = selection.publish_regular_tree

        def mutate(source, destination, **kwargs):
            publish(source, destination, **kwargs)
            (self.state / "late-mutation.bin").write_bytes(b"changed")

        with patch.object(selection, "publish_regular_tree", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "caller inputs changed"):
            self.call()
        self.assertTrue(self.destination.is_dir())
        (self.state / "late-mutation.bin").unlink()
        nested = self.state / "nested-output"
        with self.assertRaises(ValueError):
            self.call(destination=nested)
        self.assertFalse(nested.exists())
        nested = self.f.f.package_stage / "new-policy"
        with self.assertRaises(ValueError):
            self.call(destination=nested)
        self.assertFalse(nested.exists())
        self.producer.assert_called_once()

    def test_external_caller_input_is_held_through_publication(self):
        publish = selection.publish_regular_tree
        marker = self.f.f.package_stage / "late-input-mutation.bin"

        def mutate(source, destination, **kwargs):
            publish(source, destination, **kwargs)
            marker.write_bytes(b"changed")

        with patch.object(selection, "publish_regular_tree", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "caller inputs changed"):
            self.call()
        self.assertTrue(self.destination.is_dir())
        marker.unlink()

    def test_checkout_and_recomputed_s858_inventory_are_held_through_publication(self):
        publish = selection.publish_regular_tree

        def move_head(source, destination, **kwargs):
            publish(source, destination, **kwargs)
            self.checkout["commit"] = "c" * 40

        with patch.object(selection, "publish_regular_tree", side_effect=move_head), \
                self.assertRaisesRegex(ValueError, "caller inputs changed"):
            self.call()
        self.assertTrue(self.destination.is_dir())
        shutil.rmtree(self.destination)
        self.checkout["commit"] = "a" * 40

        def add_s858_closure_file(source, destination, **kwargs):
            publish(source, destination, **kwargs)
            self.compatibility_marker.parent.mkdir()
            self.compatibility_marker.write_bytes(b"new retained S858 proof")

        with patch.object(selection, "publish_regular_tree",
                          side_effect=add_s858_closure_file), \
                self.assertRaisesRegex(ValueError, "caller inputs changed"):
            self.call()
        self.assertTrue(self.destination.is_dir())
        self.assertGreaterEqual(self.request_inventory.call_count, 4)

    def test_byte_identical_foreign_replacement_is_not_removed_on_late_failure(self):
        inventory = selection._directory_inventory
        replaced = False

        def replace_after_publication(descriptor):
            nonlocal replaced
            value = inventory(descriptor)
            if self.destination.exists() and not replaced:
                replaced = True
                self.destination.rename(self.root / "owned-policy")
                shutil.copytree(self.root / "owned-policy", self.root / "replacement")
                (self.root / "replacement").rename(self.destination)
                self.replacement_inode = self.destination.stat().st_ino
            return value

        with patch.object(selection, "_directory_inventory",
                          side_effect=replace_after_publication), \
                self.assertRaisesRegex(ValueError, "changed after publication"):
            self.call()
        self.assertTrue(self.destination.is_dir())
        self.assertEqual(self.replacement_inode, self.destination.stat().st_ino)
        self.assertEqual(
            (self.root / "owned-policy/android-metadata-policy.json").read_bytes(),
            (self.destination / "android-metadata-policy.json").read_bytes())

    def test_empty_foreign_replacement_is_preserved_on_late_failure(self):
        inventory = selection._directory_inventory
        replaced = False

        def replace_with_empty_directory(descriptor):
            nonlocal replaced
            value = inventory(descriptor)
            if self.destination.exists() and not replaced:
                replaced = True
                self.destination.rename(self.root / "owned-policy")
                self.destination.mkdir()
                self.replacement_inode = self.destination.stat().st_ino
            return value

        with patch.object(selection, "_directory_inventory",
                          side_effect=replace_with_empty_directory), \
                self.assertRaisesRegex(ValueError, "inconsistent"):
            self.call()
        self.assertEqual(self.replacement_inode, self.destination.stat().st_ino)
        self.assertEqual([], list(self.destination.iterdir()))

    def test_signing_secret_rejected_before_state_or_policy_use(self):
        with patch.dict(os.environ, {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "secret"}), \
                self.assertRaisesRegex(ValueError, "signing-secret"):
            self.call()
        self.loader.assert_not_called()
        self.producer.assert_not_called()

    def cli_argv(self):
        contract = self.root / "binary-contract-evidence.json"
        context = self.root / "original-context.json"
        write_canonical_json(contract, self.arguments["binary_contract_evidence"])
        write_canonical_json(context, self.arguments["original_context"])
        paths = {
            "plan": self.arguments["plan"],
            "authenticated-state-root": self.state,
            "destination": self.destination,
            "package-stage": self.arguments["package_stage"],
            "package-receipt": self.arguments["package_receipt"],
            "binary-stage": self.arguments["binary_stage"],
            "binary-receipt": self.arguments["binary_receipt"],
            "compatibility-request": self.arguments["compatibility_request"],
            "binary-contract-evidence": contract,
            "original-context": context,
            "tooling-evidence": self.arguments["tooling_evidence"],
            "tooling-public-key": self.arguments["tooling_public_key"],
            "java-executable": self.arguments["java_executable"],
            "apkanalyzer-executable": self.arguments["apkanalyzer_executable"],
            "repository-root": self.arguments["repository_root"],
        }
        scalars = {
            "expected-build-key": self.arguments["expected_build_key"],
            "metadata-receipt-sha256": self.arguments["metadata_receipt_sha256"],
            "metadata-object-sha256": self.arguments["metadata_object_sha256"],
            "trusted-workflow-sha": self.arguments["trusted_workflow_sha"],
            "trusted-android-workflow-sha": self.arguments["trusted_android_workflow_sha"],
            "expected-original-run-id": self.arguments["expected_original_run_id"],
            "expected-original-run-attempt": self.arguments["expected_original_run_attempt"],
            "trusted-source-commit": self.arguments["trusted_source_commit"],
            "trusted-source-tree": self.arguments["trusted_source_tree"],
            "required-trust-domain": self.arguments["required_trust_domain"],
        }
        argv = [part for name, value in {**paths, **scalars}.items()
                for part in ("--" + name, str(value))]
        return argv, contract, context

    def test_cli_forwards_only_caller_elected_identity_and_explicit_authority(self):
        argv, contract, _ = self.cli_argv()
        with patch.object(selection, "create_selected_sdk_android_metadata_policy",
                          return_value=self.created) as create, \
                patch.dict(os.environ, {"GITHUB_TOKEN": "protected token"}, clear=True), \
                redirect_stdout(io.StringIO()) as output:
            self.assertEqual(0, selection.main(argv))
        self.assertEqual(
            {"policy_path": str(self.destination / selection.POLICY_NAME)},
            load_canonical_json_bytes(output.getvalue().encode()))
        self.assertEqual(self.arguments["expected_build_key"],
                         create.call_args.kwargs["expected_build_key"])
        self.assertEqual(self.arguments["metadata_receipt_sha256"],
                         create.call_args.kwargs["metadata_receipt_sha256"])
        self.assertEqual(self.arguments["metadata_object_sha256"],
                         create.call_args.kwargs["metadata_object_sha256"])
        self.assertEqual(self.arguments["binary_contract_evidence"],
                         create.call_args.kwargs["binary_contract_evidence"])
        self.assertEqual(self.arguments["original_context"],
                         create.call_args.kwargs["original_context"])
        self.assertEqual("protected token", create.call_args.kwargs["token"])
        for invalid in (
                [*argv, "--validation-artifact-id", "77"],
                [*argv, "--token", "forbidden"],
                [*argv, "--github-output", str(self.state / "retained")],
                [*argv, "--tooling-keyring", str(self.root / "keyring")],
                [*argv, "--tooling-keys-directory", str(self.root / "keys")],
                argv[:-2],
                [*argv, "--required-trust-domain", "unknown"]):
            with self.subTest(invalid=invalid[-2:]), redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit):
                selection.main(invalid)
        contract.write_text("not-json")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            selection.main(argv)
        self.assertEqual(1, create.call_count)

    def test_cli_rejects_carrier_supplied_controls(self):
        argv, contract, _ = self.cli_argv()
        retained_control = self.state / "untrusted-contract.json"
        retained_control.write_bytes(contract.read_bytes())
        changed = list(argv)
        changed[changed.index("--binary-contract-evidence") + 1] = str(retained_control)
        with patch.object(selection, "create_selected_sdk_android_metadata_policy") as create, \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            selection.main(changed)
        create.assert_not_called()

    def test_cli_rejects_late_control_replacement(self):
        argv, contract, _ = self.cli_argv()
        original = contract.read_bytes()

        def mutate_control(*args, **kwargs):
            contract.write_bytes(b"replaced caller Contract control")
            return self.created

        with patch.object(selection, "create_selected_sdk_android_metadata_policy",
                          side_effect=mutate_control), redirect_stdout(io.StringIO()) as output, \
                redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            selection.main(argv)
        self.assertEqual("", output.getvalue())
        contract.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
