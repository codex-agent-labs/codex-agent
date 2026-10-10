"""Original Core invocation paths need an independent, receipt-bound signer."""

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ci import sdk_core_metadata_history as history
from ci.products.inventory import canonical_json_bytes, sha256_bytes, write_canonical_json
from ci.products.receipt import compute_build_key, validate_phase_receipt
from ci.products.signatures import generate_development_key, sign_manifest
from ci.sdk_core_metadata_history import verify_signed_original_core_context


class SignedOriginalCoreContextTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="core-context-history-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.key, public, development = generate_development_key(self.root / "ephemeral")
        self.keys = self.root / "release-keys"
        self.keys.mkdir()
        self.signing = {**development, "trustDomain": "release", "keyId": "fixture-release"}
        (self.keys / "fixture-release.pub").write_bytes(public.read_bytes())
        self.keyring = self.root / "keyring.json"
        write_canonical_json(self.keyring, {"schemaVersion": 1,
            "namespace": self.signing["namespace"], "algorithm": self.signing["algorithm"],
            "trustDomain": "release", "activeKey": {"keyId": "fixture-release",
            "fingerprint": self.signing["fingerprint"]}, "retiredKeys": []})
        digest = "sha256:" + "a" * 64
        inputs = {"inventory": [], "phaseInputDigest": sha256_bytes(canonical_json_bytes([])),
            "versionIdentity": "0.8.0", "upstreamArtifacts": [],
            "toolchainProfileDigest": digest, "flagsDigest": digest, "outputSchemaVersion": 1}
        self.receipt = validate_phase_receipt({"schemaVersion": 1, "product": "sdk",
            "component": "sdk-core", "phase": "metadata", "target": "common",
            "productVersion": "0.8.0", "buildKey": compute_build_key(product="sdk",
            component="sdk-core", phase="metadata", target="common", inputs=inputs),
            "inputs": inputs, "outputs": [{"kind": "artifact", "relativePath": "outputs/core.zip",
            "bytes": 1, "sha256": sha256_bytes(b"x")}], "producer": {
                "repository": "codex-agent-labs/codex-agent",
                "workflowPath": ".github/workflows/product-validation.yml",
                "commit": "b" * 40, "tree": "c" * 40, "event": "pull_request",
                "runId": 7, "runAttempt": 1, "pullRequest": 31},
            "trustDomain": "development", "result": "success"})
        self.receipt_path = self.root / "receipt.json"
        write_canonical_json(self.receipt_path, self.receipt)
        self.receipt_sha = sha256_bytes(self.receipt_path.read_bytes())
        self.artifact_sha = "sha256:" + "d" * 64
        self.context = {"repositoryRoot": "/old/workspace",
                        "metadataRequest": "/old/runner-temp/metadata-request.json"}
        self.manifest = self.root / "original-context.json"
        self.record = {"schemaVersion": 1, "kind": "sdk-core-metadata-original-context",
            "buildKey": self.receipt["buildKey"], "receiptSha256": self.receipt_sha,
            "artifactId": 88, "artifactSha256": self.artifact_sha,
            "producer": self.receipt["producer"], "originalContext": dict(self.context),
            "signing": self.signing}

    def sign(self):
        write_canonical_json(self.manifest, self.record)
        return sign_manifest(self.manifest, self.key, self.signing)

    def verify(self, signature, **overrides):
        arguments = {"expected_build_key": self.receipt["buildKey"],
            "expected_receipt_sha256": self.receipt_sha, "expected_artifact_id": 88,
            "expected_artifact_sha256": self.artifact_sha, "keyring_path": self.keyring,
            "keys_directory": self.keys}
        arguments.update(overrides)
        return verify_signed_original_core_context(self.manifest, signature,
            self.receipt_path, **arguments)

    def test_preserves_historical_paths_with_exact_receipt_and_upload(self):
        self.assertEqual(self.context, self.verify(self.sign()))

    def test_rejects_re_signed_wrong_upload_and_receipt_selection(self):
        self.record["artifactId"] = 89
        signature = self.sign()
        with self.assertRaisesRegex(ValueError, "selected receipt/upload"):
            self.verify(signature)
        with self.assertRaisesRegex(ValueError, "selected receipt/upload"):
            self.verify(signature, expected_receipt_sha256="sha256:" + "f" * 64)

    def test_rejects_untrusted_key_and_mutated_context(self):
        signature = self.sign()
        self.record["originalContext"]["metadataRequest"] = "/forged/request"
        write_canonical_json(self.manifest, self.record)
        with self.assertRaisesRegex(ValueError, "SSHSIG verification"):
            self.verify(signature)
        self.record["originalContext"] = self.context
        self.manifest.with_suffix(".sig").unlink()
        signature = self.sign()
        write_canonical_json(self.keyring, {"schemaVersion": 1,
            "namespace": self.signing["namespace"], "algorithm": self.signing["algorithm"],
            "trustDomain": "release", "activeKey": None, "retiredKeys": []})
        with self.assertRaisesRegex(ValueError, "allowed release key"):
            self.verify(signature)

    def test_source_swap_cannot_change_the_signed_snapshot(self):
        signature = self.sign()
        original_verify = history.verify_manifest_signature

        def swap_source(snapshot, detached, public_key, signing):
            self.record["originalContext"]["metadataRequest"] = "/forged/request"
            write_canonical_json(self.manifest, self.record)
            return original_verify(snapshot, detached, public_key, signing)

        with mock.patch.object(history, "verify_manifest_signature", side_effect=swap_source):
            self.assertEqual(self.context, self.verify(signature))
