"""Android package policy must be independent of retained binary authority."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_android_package_policy as policy


_DIGEST = "sha256:" + "a" * 64


class AndroidPackagePolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve(strict=True)
        self.root = base / "checkout"
        self.root.mkdir()
        self.discovery = self.root / "build/capture/original/product-resume-state"
        self.state = self.root / "build/capture/original/runtime-state"
        self.discovery.mkdir(parents=True)
        self.state.mkdir(parents=True)
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"plan\n")
        self.archive = base / "codex-arm64.tar.gz"
        self.archive.write_bytes(b"pinned Android archive")
        self.destination = base / "caller-policy"
        self.context = {"repositoryRoot": str(self.root),
                        "workerRoot": str(self.root / "build/sdk-android-maven-worker")}
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
        self.receipt_bytes = policy.canonical_json_bytes(self.receipt)
        (closure / "metadata.json").write_bytes(self.receipt_bytes)
        self.verified = SimpleNamespace(
            plan={"validationCommit": "b" * 40},
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
            binary_original_context=policy.canonical_json_bytes(self.context).decode().strip(),
            android_runtime_archive=self.archive, trusted_workflow_sha="c" * 40,
            repository_root=self.root, environ={})
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
        pinned = ("codexAgent.codexVersion=0.149.0\n"
                  "codexAgent.codexArchiveSha256=" + policy.sha256_file(self.archive)[7:] + "\n").encode()
        with (patch.object(policy.product_reuse, "_verified_product_state", return_value=self.verified),
              patch.object(policy, "git_regular_blob_bytes", return_value=pinned),
              patch.object(policy, "restore_object", side_effect=self.fake_restore),
              patch.object(policy, "validate_phase_receipt", return_value=self.receipt),
              patch.object(policy, "verify_output_manifest_identity", return_value={"outputs": self.receipt["outputs"]}),
              patch.object(policy, "verify_contract_attestation") as attestation):
            result = policy.prepare(**self.args(**changes))
            attestation.assert_called_once()
            return result

    def test_policy_binds_original_contract_archive_and_context_without_binary_object(self):
        result = self.invoke()
        evidence = policy.load_canonical_json_bytes(Path(result["binary-contract-evidence"]).read_bytes())
        self.assertEqual(str(self.destination / "contract-metadata/stage"), evidence["stageRoot"])
        self.assertEqual(str(self.destination / "contract-metadata/phase-receipt.json"), evidence["phaseReceipt"])
        self.assertEqual(self.context, policy.load_canonical_json_bytes(
            Path(result["binary-original-context"]).read_bytes()))
        self.assertEqual(str(self.archive), result["android-runtime-archive"])
        self.assertFalse((self.root / "binary-object.zip").exists())

    def test_reused_or_missing_current_binary_fails_closed(self):
        for value in ("reused", "missing"):
            with self.subTest(value=value):
                self.verified.prior_by_instance[policy._BINARY]["state"] = value
                with self.assertRaisesRegex(ValueError, "retained binary"):
                    self.invoke()
        self.assertFalse(self.destination.exists())

    def test_archive_and_caller_context_must_be_independent_and_exact(self):
        different = self.archive.parent / "different.tar.gz"
        different.write_bytes(b"wrong archive")
        with self.assertRaisesRegex(ValueError, "immutable candidate Git pin"):
            self.invoke(android_runtime_archive=different)
        with self.assertRaisesRegex(ValueError, "separate normalized caller file"):
            self.invoke(android_runtime_archive=self.plan)
        with self.assertRaisesRegex(ValueError, "same-campaign worker"):
            self.invoke(binary_original_context=policy.canonical_json_bytes({
                **self.context, "workerRoot": str(self.root / "build/other")}).decode().strip())
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            self.invoke(binary_original_context=json.dumps(self.context, indent=2))
        self.assertFalse(self.destination.exists())

    def test_missing_original_authority_or_contract_mismatch_fails(self):
        with self.assertRaises(ValueError):
            self.invoke(binary_artifact_id=0)
        self.verified.rebased_request["contractEvidence"] = None
        with self.assertRaisesRegex(ValueError, "authenticated release Contract"):
            self.invoke()
        self.verified.rebased_request["contractEvidence"] = self.source
        handoff = self.discovery / "authenticated-contract/contract-input"
        (handoff / "codex-agent-contract-0.8.0.zip").write_bytes(b"different")
        with self.assertRaisesRegex(ValueError, "metadata differs"):
            self.invoke()
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
