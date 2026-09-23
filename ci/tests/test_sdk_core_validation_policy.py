"""Current-campaign Core validation requests never nominate retained bytes as authority."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_core_validation_policy as policy


_KEY = "sha256:" + "a" * 64


class CoreValidationPolicyTests(unittest.TestCase):
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
        self.destination = self.root / "build/core-validation-policy"

    def args(self, **changes):
        values = dict(plan=self.plan, discovery=self.discovery, state=self.state,
            destination=self.destination, target="jvm", expected_build_key=_KEY,
            sdk_inputs_artifact_id=19, sdk_inputs_artifact_sha256=_KEY,
            trusted_workflow_sha="b" * 40, keyring=self.root / "keyring.json",
            keys_directory=self.root / "keys", repository_root=self.root,
            environ={}, token="offline-test-token")
        values.update(changes)
        return values

    def test_unknown_and_unpinned_native_targets_fail_before_state_replay(self):
        with patch.object(policy.product_reuse, "_verified_product_state") as verified:
            for target in ("unknown", "linux-x64", "windows-x64"):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    policy.prepare(**self.args(target=target))
            verified.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_retained_package_and_binary_are_required_before_sdk_upload(self):
        selected = policy.PhaseInstanceId("sdk", "sdk-core", "validation", "jvm")
        for missing in (policy._BINARY, policy._PACKAGE, policy._CONTRACT):
            with self.subTest(missing=missing):
                phases = {phase: {"state": "retained"} for phase in
                          (policy._BINARY, policy._PACKAGE, policy._CONTRACT)}
                phases[missing] = {"state": "reused"}
                verified = SimpleNamespace(
                    prior_ready_plans={selected: {"buildKey": _KEY}},
                    prior_by_instance=phases,
                    sources={phase: self.root / "unused" for phase in phases})
                with (patch.object(policy.product_reuse, "_verified_product_state", return_value=verified),
                      patch.object(policy.sdk_workflow, "verified_inputs") as inputs,
                      self.assertRaisesRegex(ValueError, "same-campaign retained")):
                    policy.prepare(**self.args())
                    inputs.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_request_uses_selected_objects_and_official_sdk_input_capture(self):
        selected = policy.PhaseInstanceId("sdk", "sdk-core", "validation", "jvm")
        phases = {phase: {"state": "retained"} for phase in
                  (policy._BINARY, policy._PACKAGE, policy._CONTRACT)}
        ready = {"buildKey": _KEY}
        verified = SimpleNamespace(
            prior_ready_plans={selected: ready}, prior_by_instance=phases,
            sources={phase: self.root / "unused" for phase in phases},
            rebased_request={"contractEvidence": {"expectedTrustDomain": "release"}},
            plan={"validationCommit": "b" * 40},
            expected_fixed={"versions": {"sdk": "0.8.0", "runtime-release": "0.8.0"}},
        )

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
            self.assertEqual(selected, instance)
            self.assertEqual(_KEY, expected_key)
            for product, component, phase, target in (
                    ("sdk", "sdk-core", "binary", "common"),
                    ("sdk", "sdk-core", "package", "common"),
                    ("contract", "contract", "metadata", "common")):
                entry = destination / "-".join((product, component, phase, target))
                (entry / "stage").mkdir(parents=True)
                (entry / "stage/output.bin").write_bytes(b"payload")
                policy.write_canonical_json(entry / "phase-receipt.json", {
                    "product": product, "component": component, "phase": phase,
                    "target": target, "productVersion": "0.8.0", "outputs": [],
                })
            return ready

        def capture(root, evidence, original, one_output, prepared, trust):
            contract = original("contract", "contract", "metadata", "common")
            handoff = prepared / "contract-input"
            (handoff / "execution-closure").mkdir(parents=True)
            for name in ("codex-agent-contract-0.8.0.attestation.json",
                         "codex-agent-contract-0.8.0.attestation.sig", "public-key.pub"):
                (handoff / name).write_bytes(b"evidence")
            return contract, "0.8.0", handoff, {}

        sdk = self.root / "official-sdk-inputs"
        sdk.mkdir()
        (sdk / "sdk-compatibility-request.json").write_bytes(b"{}\n")

        @contextmanager
        def original_inputs(*args, **kwargs):
            self.assertEqual(19, kwargs["artifact_id"])
            self.assertEqual(_KEY, kwargs["artifact_sha256"])
            yield {"selection": {"consumers": [{"product": "sdk", "component": "sdk-core",
                "phase": "validation", "target": "jvm"}]}, "sdk": {"directory": sdk,
                "compatibility": {"sdkVersion": "0.8.0", "contract": {"version": "0.8.0"},
                    "runtime": {"defaultRuntimeVersion": "0.8.0"}}}}

        with (patch.object(policy.product_reuse, "_verified_product_state", return_value=verified),
              patch.object(policy.product_reuse, "_release_trust", side_effect=release_trust),
              patch.object(policy.product_reuse, "_materialize_product_predecessors", side_effect=materialize),
              patch.object(policy.product_reuse, "_capture_runtime_contract", side_effect=capture),
              patch.object(policy, "_record", side_effect=lambda record, *_: (record,)),
              patch.object(policy, "validate_phase_receipt", side_effect=lambda value: value),
              patch.object(policy, "verify_output_manifest_identity", return_value={"outputs": []}),
              patch.object(policy.sdk_workflow, "verified_inputs", side_effect=original_inputs)):
            result = policy.prepare(**self.args())
        request, _ = policy._request(Path(result["facadeRequest"]))
        self.assertEqual(self.root / "build/core-validation-policy/sdk-inputs/sdk-compatibility-request.json",
                         Path(request["compatibilityRequest"]))
        self.assertEqual(self.destination / "predecessors/sdk-sdk-core-package-common/stage",
                         Path(request["packageStage"]))
        self.assertEqual(request["binaryContractEvidence"], request["validationContractEvidence"])
        self.assertEqual("release", request["validationContractEvidence"]["expectedTrustDomain"])


if __name__ == "__main__":
    unittest.main()
