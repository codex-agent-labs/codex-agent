"""Same-campaign Core policy must not recover caller authority from binary bytes."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_core_package_policy as policy

canonical_json_bytes = policy.canonical_json_bytes
load_canonical_json_bytes = policy.load_canonical_json_bytes


_DIGEST = "sha256:" + "a" * 64


class CorePackagePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name).resolve(strict=True)
        self.root = base / "checkout"
        self.root.mkdir()
        self.discovery = self.root / "build/capture/original/product-resume-state"
        self.state = self.root / "build/capture/original/runtime-state"
        self.discovery.mkdir(parents=True)
        self.state.mkdir(parents=True)
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"plan\n")
        self.destination = base / "caller-policy"
        self.context = {"repositoryRoot": str(self.root),
                        "workerRoot": str(self.root / "build/sdk-core-maven-worker")}
        handoff = self.discovery / "authenticated-contract/contract-input"
        handoff.mkdir(parents=True)
        self.source = {}
        for name, filename in (("attestation", "codex-agent-contract-0.8.0.attestation.json"),
                               ("attestationSignature", "codex-agent-contract-0.8.0.attestation.sig"),
                               ("publicKey", "public-key.pub")):
            path = handoff / filename
            path.write_bytes(name.encode())
            self.source[name] = path.relative_to(self.root).as_posix()
        keyring = self.discovery / "keyring"
        keyring.write_bytes(b"keyring")
        self.source["keyring"] = keyring.relative_to(self.root).as_posix()
        key_dir = self.discovery / "keys"
        key_dir.mkdir()
        (key_dir / "active.pub").write_bytes(b"key")
        self.source["keysDirectory"] = key_dir.relative_to(self.root).as_posix()
        self.source["expectedTrustDomain"] = "release"
        (handoff / "codex-agent-contract-0.8.0.zip").write_bytes(b"payload")
        closure = handoff / "execution-closure/receipts"
        closure.mkdir(parents=True)
        self.receipt = {"product": "contract", "component": "contract", "phase": "metadata",
                        "target": "common", "productVersion": "0.8.0",
                        "outputs": [{"kind": "contract-bundle", "relativePath": "outputs/contract.zip"}]}
        self.receipt_bytes = canonical_json_bytes(self.receipt)
        (closure / "metadata.json").write_bytes(self.receipt_bytes)
        self.verified = SimpleNamespace(
            prior_ready_plans={policy._PACKAGE: {"buildKey": _DIGEST}},
            prior_by_instance={policy._BINARY: {"state": "retained"}},
            sources={policy._BINARY: self.root / "binary-object.zip",
                     policy._CONTRACT: self.root / "contract-object.zip"},
            prior_carrier_phases={policy._CONTRACT: {"buildKey": _DIGEST,
                "receiptSha256": _DIGEST, "objectSha256": _DIGEST}},
            rebased_request={"contractEvidence": self.source},
        )

    def args(self, **changes):
        result = dict(plan=self.plan, discovery=self.discovery, state=self.state,
            destination=self.destination, expected_build_key=_DIGEST, binary_artifact_id=17,
            binary_artifact_sha256=_DIGEST,
            binary_original_context=canonical_json_bytes(self.context).decode().strip(),
            trusted_workflow_sha="b" * 40, repository_root=self.root, environ={})
        result.update(changes)
        return result

    def fake_restore(self, archive, destination, **kwargs):
        self.assertEqual(self.verified.sources[policy._CONTRACT], archive)
        self.assertEqual(_DIGEST, kwargs["object_sha256"])
        target = destination / "outputs/contract.zip"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"payload")
        return {"receiptBytes": self.receipt_bytes}

    def invoke(self, **changes):
        with (patch.object(policy.product_reuse, "_verified_product_state", return_value=self.verified),
              patch.object(policy, "restore_object", side_effect=self.fake_restore),
              patch.object(policy, "validate_phase_receipt", return_value=self.receipt),
              patch.object(policy, "verify_output_manifest_identity", return_value={"outputs": self.receipt["outputs"]}),
              patch.object(policy, "verify_contract_attestation") as attestation):
            result = policy.prepare(**self.args(**changes))
            attestation.assert_called_once()
            return result

    def test_original_contract_policy_is_external_and_independent_of_binary_object(self):
        result = self.invoke()
        evidence = load_canonical_json_bytes(Path(result["binary-contract-evidence"]).read_bytes())
        self.assertEqual(str(self.destination / "contract-metadata/stage"), evidence["stageRoot"])
        self.assertEqual(str(self.destination / "contract-metadata/phase-receipt.json"), evidence["phaseReceipt"])
        self.assertEqual(self.context, load_canonical_json_bytes(
            Path(result["binary-original-context"]).read_bytes()))
        self.assertFalse((self.root / "binary-object.zip").exists())
        self.assertNotIn(self.root, self.destination.parents)

    def test_reused_or_missing_current_binary_is_not_a_same_campaign_policy(self):
        for value in ("reused", "missing"):
            with self.subTest(value=value):
                self.verified.prior_by_instance[policy._BINARY]["state"] = value
                with self.assertRaisesRegex(ValueError, "retained binary"):
                    self.invoke()
        self.assertFalse(self.destination.exists())

    def test_incomplete_or_noncanonical_caller_context_fails_before_state_replay(self):
        for value in ('{}', json.dumps(self.context, indent=2), 'not-json'):
            with self.subTest(value=value):
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    self.invoke(binary_original_context=value)
        self.assertFalse(self.destination.exists())

    def test_missing_original_contract_evidence_fails_closed(self):
        self.verified.rebased_request["contractEvidence"] = None
        with self.assertRaisesRegex(ValueError, "authenticated release Contract"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_contract_payload_must_equal_the_authenticated_predecessor(self):
        handoff = self.discovery / "authenticated-contract/contract-input"
        (handoff / "codex-agent-contract-0.8.0.zip").write_bytes(b"different")
        with self.assertRaisesRegex(ValueError, "metadata differs"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_missing_official_binary_upload_is_rejected_before_replay(self):
        with self.assertRaises(ValueError):
            self.invoke(binary_artifact_id=0)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
