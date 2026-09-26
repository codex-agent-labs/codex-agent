"""Android validation caller policy binds elected originals, not retained self-claims."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_android_validation_policy as policy


_KEY = "sha256:" + "a" * 64


class AndroidValidationPolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve(strict=True)
        self.root = base / "checkout"
        self.root.mkdir()
        self.discovery = self.root / "build/discovery"
        self.state = self.root / "build/state"
        self.discovery.mkdir(parents=True)
        self.state.mkdir(parents=True)
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"plan\n")
        self.destination = self.root / "build/android-validation-policy"

    def args(self, **changes):
        values = dict(plan=self.plan, discovery=self.discovery, state=self.state,
            destination=self.destination, expected_build_key=_KEY,
            sdk_inputs_artifact_id=19, sdk_inputs_artifact_sha256=_KEY,
            trusted_workflow_sha="b" * 40, keyring=self.root / "keyring.json",
            keys_directory=self.root / "keys", repository_root=self.root,
            environ={}, token="offline-test-token", sdk_validation_tooling={"signed": True})
        values.update(changes)
        return values

    def test_missing_original_tooling_or_upload_fails_before_state_replay(self):
        with patch.object(policy.product_reuse, "_verified_product_state") as verified:
            for changes in ({"sdk_validation_tooling": None}, {"sdk_inputs_artifact_id": 0},
                            {"sdk_inputs_artifact_sha256": "invalid"}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    policy.prepare(**self.args(**changes))
            verified.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_destination_must_be_fresh_normalized_and_separate(self):
        outside = self.root.parent / "runner-temp"
        outside.mkdir()
        (outside / "source").mkdir()
        (outside / "linked").symlink_to(outside / "source", target_is_directory=True)
        cases = (self.root, self.root.parent, self.discovery,
                 self.discovery / "child", self.root / "build",
                 outside / "linked" / "policy", outside / "source",
                 outside / "source" / ".." / "policy")
        with patch.object(policy.product_reuse, "_verified_product_state") as verified:
            for destination in cases:
                with self.subTest(destination=destination), self.assertRaisesRegex(
                        ValueError, "fresh, separate destination"):
                    policy.prepare(**self.args(destination=destination))
            with self.assertRaisesRegex(ValueError, "fresh, separate destination"):
                policy.prepare(**self.args(destination=outside / "source/policy",
                    sdk_validation_tooling={"evidence": str(outside / "source")}))
            verified.assert_not_called()

    def test_reused_package_binary_or_contract_fails_before_sdk_upload(self):
        for missing in (policy._PACKAGE, policy._BINARY, policy._CONTRACT):
            with self.subTest(missing=missing):
                phases = {phase: {"state": "retained"} for phase in
                          (policy._PACKAGE, policy._BINARY, policy._CONTRACT)}
                phases[missing] = {"state": "reused"}
                verified = SimpleNamespace(
                    prior_ready_plans={policy._VALIDATION: {"buildKey": _KEY}},
                    prior_by_instance=phases,
                    sources={phase: self.root / "unused" for phase in phases})
                with (patch.object(policy.product_reuse, "_verified_product_state", return_value=verified),
                      patch.object(policy.sdk_workflow, "verified_inputs") as sdk_upload,
                      self.assertRaisesRegex(ValueError, "same-campaign retained")):
                    policy.prepare(**self.args())
                    sdk_upload.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_selected_package_binary_contract_and_s858_are_referenced(self):
        phases = {phase: {"state": "retained"} for phase in
                  (policy._PACKAGE, policy._BINARY, policy._CONTRACT)}
        ready = {"buildKey": _KEY}
        contract_root = self.root / "contract-original"
        closure = contract_root / "execution-closure/receipts"
        closure.mkdir(parents=True)
        for name in ("attestation.json", "attestation.sig", "public-key.pub"):
            (contract_root / name).write_bytes(b"fixture")
        verified = SimpleNamespace(
            prior_ready_plans={policy._VALIDATION: ready}, prior_by_instance=phases,
            sources={phase: self.root / "unused" for phase in phases},
            rebased_request={"contractEvidence": {"expectedTrustDomain": "release",
                "attestation": "contract-original/attestation.json",
                "attestationSignature": "contract-original/attestation.sig",
                "publicKey": "contract-original/public-key.pub"}},
            plan={"validationCommit": "b" * 40},
            expected_fixed={"versions": {"sdk": "0.8.0", "runtime-release": "0.8.0"}})

        def release_trust(root, revision, destination):
            self.assertEqual("b" * 40, revision)
            trust = destination / "trust"
            keys = trust / "keys"
            keys.mkdir(parents=True)
            ring = trust / "product-signing-keys.json"
            ring.write_bytes(b"ring")
            (keys / "active.pub").write_bytes(b"key")
            return SimpleNamespace(keyring=ring, keys=keys)

        def materialize(state, instance, destination, expected_key, root):
            self.assertIs(state, verified)
            self.assertEqual(policy._VALIDATION, instance)
            self.assertEqual(_KEY, expected_key)
            self.assertIn(root, destination.parents)
            for product, component, phase, target in (
                    ("sdk", "sdk-android", "binary", "android"),
                    ("sdk", "sdk-android", "package", "android"),
                    *(("contract", "contract", contract_phase, "common") for contract_phase in
                      ("binary", "package", "validation", "metadata"))):
                entry = destination / "-".join((product, component, phase, target))
                (entry / "stage").mkdir(parents=True)
                (entry / "stage/output.bin").write_bytes(b"payload")
                if (product, phase) == ("contract", "metadata"):
                    (entry / "stage/contract.zip").write_bytes(b"contract")
                receipt = {
                    "product": product, "component": component, "phase": phase,
                    "target": target, "productVersion": "0.8.0",
                    "outputs": ([{"kind": "contract-bundle", "relativePath": "contract.zip"}]
                                if (product, phase) == ("contract", "metadata") else []),
                }
                policy.write_canonical_json(entry / "phase-receipt.json", receipt)
                if product == "contract":
                    (closure / (phase + ".json")).write_bytes(
                        (entry / "phase-receipt.json").read_bytes())
            return ready

        sdk = self.root / "official-sdk-inputs"
        sdk.mkdir()
        (sdk / policy.REQUEST_NAME).write_bytes(b"{}\n")
        selected = False

        @contextmanager
        def original_inputs(*args, **kwargs):
            self.assertEqual(19, kwargs["artifact_id"])
            self.assertEqual(_KEY, kwargs["artifact_sha256"])
            consumers = ([{"product": "sdk", "component": "sdk-android",
                "phase": "validation", "target": "android"}] if selected else [])
            yield {"selection": {"consumers": consumers}, "sdk": {"directory": sdk,
                "compatibility": {"sdkVersion": "0.8.0", "contract": {"version": "0.8.0"},
                    "runtime": {"defaultRuntimeVersion": "0.8.0"}}}}

        with (patch.object(policy.product_reuse, "_verified_product_state", return_value=verified),
              patch.object(policy.product_reuse, "_release_trust", side_effect=release_trust),
              patch.object(policy.product_reuse, "_materialize_product_predecessors", side_effect=materialize),
              patch.object(policy.product_reuse, "verify_contract_attestation", return_value=({}, None, None)),
              patch.object(policy, "_record", side_effect=lambda record, *_: (record,)),
              patch.object(policy, "validate_phase_receipt", side_effect=lambda value: value),
              patch.object(policy, "verify_output_manifest_identity", return_value={"outputs": []}),
              patch.object(policy.sdk_workflow, "verified_inputs", side_effect=original_inputs)):
            with self.assertRaisesRegex(ValueError, "selection does not include"):
                policy.prepare(**self.args())
            self.assertFalse(self.destination.exists())
            selected = True
            for destination in (self.destination, self.root.parent / "runner-temp/policy"):
                with self.subTest(destination=destination):
                    result = policy.prepare(**self.args(destination=destination))
                    self.assertEqual(destination / "predecessors/sdk-sdk-android-package-android/stage",
                                     Path(result["packageStage"]))
                    self.assertEqual(destination / "predecessors/sdk-sdk-android-binary-android/phase-receipt.json",
                                     Path(result["binaryReceipt"]))
                    self.assertEqual(destination / "sdk-inputs" / policy.REQUEST_NAME,
                                     Path(result["compatibilityRequest"]))
                    evidence = policy.load_canonical_json_bytes(
                        policy.read_regular_file_bytes(Path(result["binaryContractEvidence"])))
                    self.assertEqual("release", evidence["expectedTrustDomain"])
                    for phase in ("binary", "package", "validation", "metadata"):
                        self.assertEqual((closure / (phase + ".json")).read_bytes(),
                            (destination / "contract-input/execution-closure/receipts" / (phase + ".json")).read_bytes())
            tampered = self.root.parent / "runner-temp/tampered-policy"
            original_publish = policy.publish_regular_tree
            def mutate_before_publish(source, destination, **kwargs):
                (source / "late-mutation.bin").write_bytes(b"late mutation")
                return original_publish(source, destination, **kwargs)
            with patch.object(policy, "publish_regular_tree", side_effect=mutate_before_publish):
                with self.assertRaisesRegex(ValueError, "pinned inventory"):
                    policy.prepare(**self.args(destination=tampered))
            self.assertFalse(tampered.exists())


if __name__ == "__main__":
    unittest.main()
