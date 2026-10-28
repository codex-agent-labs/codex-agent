"""Real signature/custody checks; synthetic semantic seam is not Apple host proof."""

from contextlib import contextmanager
import copy
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from ci import sdk_ios_original_validation as reader
from ci.products import sdk_apple_validation_admission as admission
from ci.products import sdk_apple_validation_attestation as binding
from ci.products.inventory import load_canonical_json_bytes, sha256_bytes, write_canonical_json
from ci.products.restore import verification_session
from ci.products.sdk_apple_validation_inputs import capture_sdk_apple_validation_evidence
from ci.products.sdk_validation_inputs import collection_admission_scope
from ci.products.signatures import sign_manifest
from ci.tests.test_sdk_apple_validation_attestation import AppleValidationAttestationTest


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen required")
class AppleCollectionReuseTest(unittest.TestCase):
    def setUp(self):
        AppleValidationAttestationTest.setUp(self)
        (self.capture / "plan").mkdir()
        (self.capture / "plan/impact-plan.json").write_bytes(b'{"synthetic":"plan"}\n')
        (self.capture / "transport.zip").write_bytes(b"synthetic original upload")
        (self.capture / "capture-transport.json").write_bytes(b'{"synthetic":"transport"}\n')
        self.signature.unlink()
        write_canonical_json(self.manifest,
            binding.derive_apple_validation_attestation(self.capture, self.raw, self.signing))
        self.signature = sign_manifest(self.manifest, self.key, self.signing)
        entry = self.root / "entry"
        entry.mkdir()
        self.capture.rename(entry / "capture")
        self.manifest.rename(entry / binding.ATTESTATION_NAME)
        self.signature.rename(entry / binding.SIGNATURE_NAME)
        self.carrier = self.root / "carrier"
        self.records = capture_sdk_apple_validation_evidence([entry], self.carrier)
        self.evidence = self.carrier / self.records[0]["evidenceRoot"]
        self.envelope = {"receipt": load_canonical_json_bytes(self.raw), "receiptBytes": self.raw,
                         "receiptSha256": sha256_bytes(self.raw), "objectSha256": "sha256:" + "8" * 64}
        self.policy = {name: str(self.root / name) for name in (
            "plan", "keyring", "keysDirectory", "toolingEvidence", "toolingPublicKey",
            "javaExecutable", "toolingKeyring", "toolingKeysDirectory")}
        self.policy.update(attestationPublicKey=str(self.public), attestationTrustDomain="development",
                           toolingTrustDomain="release")
        for name in ("keysDirectory", "toolingEvidence", "toolingKeysDirectory"):
            path = Path(self.policy[name]); path.mkdir(); (path / "input").write_bytes(name.encode())
        for name in ("plan", "keyring", "toolingPublicKey", "javaExecutable", "toolingKeyring"):
            Path(self.policy[name]).write_bytes(name.encode())
        (self.root / "ci").mkdir()
        (self.root / "ci/verifier.py").write_bytes(b"synthetic verifier source")
        self.events = []
        self.after_yield = lambda: None
        self.full = self.enterContext(patch.object(reader, "verified_retained_ios_validation",
                                                  side_effect=self.semantic_seam))

    @contextmanager
    def semantic_seam(self, plan, receipt_path, **arguments):
        self.events.append("enter")
        self.assertEqual(self.raw, receipt_path.read_bytes())
        yield {"receiptBytes": self.raw, "receipt": load_canonical_json_bytes(self.raw)}
        self.after_yield()
        self.events.append("exit")

    def make(self, *, carrier=None, **options):
        return admission.AppleValidationAdmission(carrier or self.carrier, self.records,
            repository=self.root, policy_revision="c" * 40, policy=self.policy, **options)

    def test_relocated_same_collection_reuses_semantics_but_rechecks_real_signature_without_copy(self):
        other = self.root / "relocated"
        shutil.copytree(self.carrier, other)
        gate = self.make()

        @collection_admission_scope
        def collect():
            gate.verify(self.envelope)
            self.assertEqual(["enter", "exit"], self.events)
            with patch.object(binding, "snapshot_regular_tree", side_effect=AssertionError("unexpected body snapshot")), \
                    patch.object(binding, "verify_manifest_signature", wraps=binding.verify_manifest_signature) as signature:
                self.assertIsNone(self.make(carrier=other).verify(copy.deepcopy(self.envelope)))
                self.assertIsNone(gate.verify(self.envelope))
                self.assertEqual(2, signature.call_count)
            self.assertEqual(1, self.full.call_count)
        collect()

    def test_new_collection_and_standalone_call_cannot_reuse_expired_admission(self):
        gate = self.make()

        @collection_admission_scope
        def collect():
            gate.verify(self.envelope)
            gate.verify(self.envelope)
        with verification_session():
            collect()
            collect()  # Same outer byte session, different semantic collection lifetime.
            gate.verify(self.envelope)
            gate.verify(self.envelope)
        self.assertEqual(4, self.full.call_count)

    def test_policy_source_tooling_and_object_changes_require_new_full_admission(self):
        paths = [Path(self.policy[name]) for name in
                 ("plan", "keyring", "toolingPublicKey", "javaExecutable", "toolingKeyring")]
        paths += [Path(self.policy[name]) / "input" for name in
                  ("keysDirectory", "toolingEvidence", "toolingKeysDirectory")]
        paths.append(self.root / "ci/verifier.py")
        for path in paths:
            original = path.read_bytes()

            @collection_admission_scope
            def collect():
                gate = self.make()
                before = self.full.call_count
                gate.verify(self.envelope)
                path.write_bytes(original + b"changed")
                gate.verify(self.envelope)
                self.assertEqual(before + 2, self.full.call_count)
            with self.subTest(path=path.name):
                try:
                    collect()
                finally:
                    path.write_bytes(original)

        @collection_admission_scope
        def changed_object():
            before = self.full.call_count
            gate = self.make()
            gate.verify(self.envelope)
            gate.verify({**self.envelope, "objectSha256": "sha256:" + "7" * 64})
            self.assertEqual(before + 2, self.full.call_count)
        changed_object()

    def test_tampered_signature_capture_key_and_symlink_cannot_hit_prior_admission(self):
        paths = [self.evidence / binding.SIGNATURE_NAME,
                 self.evidence / "capture/original/raw-evidence.bin", self.public]
        for path in paths:
            original = path.read_bytes()

            @collection_admission_scope
            def collect():
                gate = self.make()
                gate.verify(self.envelope)
                before = self.full.call_count
                path.write_bytes(b"tampered")
                with self.assertRaises(ValueError):
                    gate.verify(self.envelope)
                self.assertEqual(before, self.full.call_count)
            with self.subTest(path=path.name):
                try:
                    collect()
                finally:
                    path.write_bytes(original)

        @collection_admission_scope
        def linked():
            gate = self.make()
            gate.verify(self.envelope)
            source = self.evidence / "capture/original/raw-evidence.bin"
            saved = source.with_suffix(".saved")
            source.rename(saved)
            source.symlink_to(saved)
            try:
                with self.assertRaises(ValueError):
                    gate.verify(self.envelope)
            finally:
                source.unlink(); saved.rename(source)
        linked()

    def test_failed_full_exit_or_late_authority_mutation_never_publishes_reusable_admission(self):
        @collection_admission_scope
        def collect():
            gate = self.make()
            self.after_yield = lambda: (_ for _ in ()).throw(ValueError("full exit rejected"))
            with self.assertRaisesRegex(ValueError, "full exit rejected"):
                gate.verify(self.envelope)
            self.after_yield = lambda: None
            gate.verify(self.envelope)
            gate.verify(self.envelope)
            self.assertEqual(2, self.full.call_count)
        collect()

        path = Path(self.policy["plan"])
        original = path.read_bytes()

        @collection_admission_scope
        def changed():
            gate = self.make()
            before = self.full.call_count
            self.after_yield = lambda: path.write_bytes(b"late mutation")
            with self.assertRaisesRegex(ValueError, "authority changed"):
                gate.verify(self.envelope)
            path.write_bytes(original)
            self.after_yield = lambda: None
            gate.verify(self.envelope)
            self.assertEqual(before + 2, self.full.call_count)
        changed()

    def test_receipt_only_signature_mode_yields_no_capture_and_checks_exit_mutation(self):
        capture = self.evidence / "capture"
        arguments = dict(capture=capture, receipt_path=capture / "original/shard/phase-receipt.json",
            attestation=self.evidence / binding.ATTESTATION_NAME, signature=self.evidence / binding.SIGNATURE_NAME,
            public_key=self.public, required_trust_domain="development", _receipt_only=True)
        with patch.object(binding, "snapshot_regular_tree", side_effect=AssertionError("body copy forbidden")):
            with binding.verified_apple_validation_attestation(**arguments) as value:
                self.assertNotIn("capture", value)
                self.assertEqual(self.raw, value["receiptBytes"])
            source = capture / "original/raw-evidence.bin"
            original = source.read_bytes()
            try:
                with self.assertRaisesRegex(ValueError, "changed during use"):
                    with binding.verified_apple_validation_attestation(**arguments):
                        source.write_bytes(b"late change")
            finally:
                source.write_bytes(original)
        with self.assertRaises(ValueError):
            with binding.verified_apple_validation_attestation(**{**arguments, "_receipt_only": 1}):
                self.fail("invalid receipt-only mode")

    def test_concrete_completion_changes_and_collection_lifetime_changes_are_not_cache_hits(self):
        from ci.products import sdk_validation_inputs as scopes
        from ci.products.inventory import canonical_json_bytes
        from reuse_qualification import CompletedFrozenReuse, _COMPLETED_FROZEN

        # Synthetic concrete capability for cache invalidation only; no body/host trust claim.
        completed = object.__new__(CompletedFrozenReuse)
        for name in CompletedFrozenReuse.__slots__:
            setattr(completed, name, None)
        completed._verified = _COMPLETED_FROZEN
        completed._spec = canonical_json_bytes({"expectedResult": {"phases": []}})
        completed._revision = "c" * 40

        @collection_admission_scope
        def collect():
            gate = self.make(completed_frozen=completed)
            gate.verify(self.envelope)
            completed._revision = "d" * 40
            gate.verify(self.envelope)
            self.assertEqual(2, self.full.call_count)
            completed._verified = None
            with self.assertRaises(TypeError):
                gate.verify(self.envelope)
        collect()

        @collection_admission_scope
        def changed_lifetime():
            gate = self.make()
            gate.verify(self.envelope)
            tokens = []
            actual = binding.verify_manifest_signature
            def signature(*args, **kwargs):
                actual(*args, **kwargs)
                tokens.append(scopes._COLLECTION.set({}))
            try:
                with patch.object(binding, "verify_manifest_signature", side_effect=signature), \
                        self.assertRaisesRegex(ValueError, "authority changed"):
                    gate.verify(self.envelope)
            finally:
                for token in reversed(tokens):
                    scopes._COLLECTION.reset(token)
        changed_lifetime()


if __name__ == "__main__":
    unittest.main()
