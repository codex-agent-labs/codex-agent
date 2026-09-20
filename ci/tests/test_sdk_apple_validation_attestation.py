"""Real detached signature tests; synthetic captures are not compiler/host proof."""

from pathlib import Path
from contextlib import contextmanager
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci.products import sdk_apple_validation_attestation as binding
from ci.products.inventory import load_canonical_json_bytes, regular_file_inventory, sha256_bytes, write_canonical_json
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.product_chain_support import output, write_receipt


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen required")
class AppleValidationAttestationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-evidence-signature-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.capture = self.root / "capture"
        self.receipt = self.capture / "original/shard/phase-receipt.json"
        self.producer = {"repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/ci.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request", "runId": 91, "runAttempt": 2, "pullRequest": 31}
        write_receipt(self.receipt, product="sdk", component="sdk-ios", phase="validation", target="ios-arm64",
            version="0.8.0", version_identity="0.8.0", upstream=[], context={"producer": self.producer},
            outputs=[output("apple-validation-content", "outputs/validation/apple-validation.json", b"synthetic content")])
        self.raw = self.receipt.read_bytes()
        (self.capture / "original/raw-evidence.bin").write_bytes(b"synthetic execution data\x00\xff")
        self.key, self.public, self.signing = generate_development_key(self.root / "keys")
        self.manifest = self.root / binding.ATTESTATION_NAME
        self.value = binding.derive_apple_validation_attestation(self.capture, self.raw, self.signing)
        write_canonical_json(self.manifest, self.value)
        self.signature = sign_manifest(self.manifest, self.key, self.signing)

    def context(self, **options):
        return binding.verified_apple_validation_attestation(self.capture, self.receipt, self.manifest, self.signature,
            **{"public_key": self.public, "required_trust_domain": "development", **options})

    def test_real_signature_preserves_originals_and_private_lifetime(self):
        before = regular_file_inventory(self.capture)
        signature = self.signature.read_bytes()
        with self.context() as authenticated:
            self.assertEqual(self.raw, authenticated["receiptBytes"])
            self.assertEqual(signature, authenticated["signatureBytes"])
            self.assertEqual(before, regular_file_inventory(authenticated["capture"]))
            self.assertNotEqual(self.capture, authenticated["capture"])
        self.assertFalse(authenticated["capture"].exists())
        self.assertEqual(before, regular_file_inventory(self.capture))
        self.assertEqual(signature, self.signature.read_bytes())

    def test_signer_changes_only_external_binding_not_capture_or_receipt(self):
        before = regular_file_inventory(self.capture)
        _, _, another = generate_development_key(self.root / "another")
        other = binding.derive_apple_validation_attestation(self.capture, self.raw, another)
        self.assertNotEqual(self.value["signing"], other["signing"])
        self.assertEqual({key: value for key, value in self.value.items() if key != "signing"},
                         {key: value for key, value in other.items() if key != "signing"})
        self.assertEqual(before, regular_file_inventory(self.capture))
        self.assertEqual(self.raw, self.receipt.read_bytes())

    def test_tampered_signature_capture_manifest_and_wrong_key_are_rejected(self):
        signature, manifest = self.signature.read_bytes(), self.manifest.read_bytes()
        evidence = self.capture / "original/raw-evidence.bin"
        original = evidence.read_bytes()
        _, wrong_key, _ = generate_development_key(self.root / "wrong")
        for mutation in ("signature", "capture", "manifest", "key"):
            if mutation == "signature": self.signature.write_bytes(b"not a signature")
            if mutation == "capture": evidence.write_bytes(b"changed capture")
            if mutation == "manifest":
                write_canonical_json(self.manifest, {**self.value, "target": "ios-simulator-arm64"})
            try:
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    with self.context(**({"public_key": wrong_key} if mutation == "key" else {})):
                        self.fail("tampered signed evidence accepted")
            finally:
                self.signature.write_bytes(signature)
                self.manifest.write_bytes(manifest)
                evidence.write_bytes(original)

    def test_strict_schema_and_exact_receipt_binding(self):
        for field, value in (("schemaVersion", True), ("target", "ios"), ("phase", "package"),
                             ("captureDigest", "sha256:" + "0" * 64), ("receiptSha256", "sha256:" + "1" * 64),
                             ("extra", "unknown")):
            candidate = {**self.value, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                binding.verify_apple_validation_binding(self.capture, self.raw, candidate)
        other = self.raw.replace(b'"runId":91', b'"runId":92')
        with self.assertRaises(ValueError):
            binding.verify_apple_validation_binding(self.capture, other, self.value)

    def test_context_exit_rechecks_source_private_attestation_and_caller_key(self):
        for mutation in ("source", "private", "value", "key", "receipt"):
            key, receipt = self.public.read_bytes(), self.receipt.read_bytes()
            source = self.capture / "original/raw-evidence.bin"
            raw = source.read_bytes()
            try:
                with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "changed during use"):
                    with self.context() as value:
                        if mutation == "source": source.write_bytes(b"changed")
                        if mutation == "private": (value["capture"] / "original/raw-evidence.bin").write_bytes(b"changed")
                        if mutation == "value": value["attestation"]["captureDigest"] = "sha256:" + "0" * 64
                        if mutation == "key": self.public.write_bytes(b"changed")
                        if mutation == "receipt": self.receipt.write_bytes(b"changed")
            finally:
                self.public.write_bytes(key)
                self.receipt.write_bytes(receipt)
                source.write_bytes(raw)

    def test_release_requires_pinned_active_or_retired_key_and_preserves_development_receipt(self):
        release = {**self.signing, "trustDomain": "release", "keyId": "test-release"}
        keys = self.root / "release-keys"
        keys.mkdir()
        (keys / "test-release.pub").write_bytes(self.public.read_bytes())
        ring = self.root / "keyring.json"
        record = {name: release[name] for name in ("keyId", "fingerprint")}
        self.signature.unlink()
        value = binding.derive_apple_validation_attestation(self.capture, self.raw, release)
        write_canonical_json(self.manifest, value)
        sign_manifest(self.manifest, self.key, release)
        for retired in (False, True):
            write_canonical_json(ring, {"schemaVersion": 1, "namespace": release["namespace"], "algorithm": release["algorithm"],
                "trustDomain": "release", "activeKey": None if retired else record, "retiredKeys": [record] if retired else []})
            with self.context(required_trust_domain="release", keyring=ring, keys_directory=keys) as authenticated:
                self.assertEqual(self.raw, authenticated["receiptBytes"])
            self.assertEqual(self.raw, self.receipt.read_bytes())
        for options in ({"required_trust_domain": "release"}, {"keyring": ring, "keys_directory": keys},
                        {"required_trust_domain": "release", "keyring": ring}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                with self.context(**options):
                    self.fail("unpinned or cross-domain key accepted")
        original_ring = ring.read_bytes()
        copy = binding.snapshot_regular_tree

        def mutate_policy(*args, **kwargs):
            copy(*args, **kwargs)
            ring.write_bytes(b"changed during evidence snapshot")

        try:
            with patch.object(binding, "snapshot_regular_tree", side_effect=mutate_policy), \
                    self.assertRaisesRegex(ValueError, "changed during use"):
                with self.context(required_trust_domain="release", keyring=ring, keys_directory=keys):
                    self.fail("caller policy mutation accepted as a new baseline")
        finally:
            ring.write_bytes(original_ring)

    def test_authenticated_handoff_requires_selected_identity_and_complete_replay(self):
        from ci import sdk_ios_original_validation as reader
        evidence = self.root / "handoff"
        evidence.mkdir()
        self.capture.rename(evidence / "capture")
        self.capture = evidence / "capture"
        self.receipt = self.capture / "original/shard/phase-receipt.json"
        self.manifest.rename(evidence / binding.ATTESTATION_NAME)
        self.signature.rename(evidence / binding.SIGNATURE_NAME)
        arguments = dict(plan=self.root / "caller-plan", expected_receipt_sha256=sha256_bytes(self.raw), target="ios-arm64",
            attestation_public_key=self.public, attestation_trust_domain="development",
            keyring=self.root / "product-keyring", keys_directory=self.root / "product-keys",
            repository_root=self.root, tooling_evidence=self.root / "tooling", tooling_public_key=self.root / "tooling.pub",
            java_executable=self.root / "java", policy_revision="c" * 40, required_trust_domain="release",
            tooling_keyring=self.root / "tooling-keyring", tooling_keys_directory=self.root / "tooling-keys")
        events = []

        @contextmanager
        def replay(plan, receipt, **options):
            events.append("full-replay-enter")
            self.assertEqual(arguments["plan"], plan)
            self.assertEqual(self.raw, receipt.read_bytes())
            self.assertNotEqual(self.capture, options["validation_capture"])
            for name in ("keyring", "keys_directory", "repository_root", "tooling_evidence", "tooling_public_key",
                         "java_executable", "policy_revision", "required_trust_domain", "tooling_keyring", "tooling_keys_directory"):
                self.assertEqual(arguments[name], options[name])
            yield {"receiptBytes": self.raw, "receipt": load_canonical_json_bytes(self.raw),
                   "capture": options["validation_capture"]}
            events.append("full-replay-exit")

        with patch.object(reader, "verified_retained_ios_validation", side_effect=replay):
            with binding.verified_apple_validation_handoff(evidence, **arguments) as value:
                self.assertEqual(self.raw, value["receiptBytes"])
                self.assertEqual(["full-replay-enter"], events)
            self.assertEqual(["full-replay-enter", "full-replay-exit"], events)
        for changed in ({"target": "ios-simulator-arm64"}, {"expected_receipt_sha256": "sha256:" + "0" * 64}):
            with self.subTest(changed=changed), patch.object(reader, "verified_retained_ios_validation") as full_gate, \
                    self.assertRaises(ValueError):
                with binding.verified_apple_validation_handoff(evidence, **{**arguments, **changed}):
                    self.fail("unselected evidence reached admission")
            full_gate.assert_not_called()
        with patch.object(reader, "verified_retained_ios_validation", side_effect=ValueError("semantic rejection")), \
                self.assertRaisesRegex(ValueError, "semantic rejection"):
            with binding.verified_apple_validation_handoff(evidence, **arguments):
                self.fail("signature substituted for full replay")


if __name__ == "__main__":
    unittest.main()
