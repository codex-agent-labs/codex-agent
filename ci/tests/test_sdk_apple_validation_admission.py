"""Concrete admission routing; mocked handoff is not signature/native acceptance."""

import copy
from contextlib import contextmanager
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from ci.products import sdk_apple_validation_admission as admission
from ci.products.inventory import canonical_json_bytes, sha256_bytes
from ci.products.sdk_apple_validation_inputs import capture_sdk_apple_validation_evidence
from ci.tests import test_sdk_apple_validation_inputs as fixtures
from ci.tests.product_chain_support import output, write_receipt


class AppleValidationAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.AppleValidationInputsTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        entry = self.fixture.entry()
        self.raw = (entry / "capture/original/shard/phase-receipt.json").read_bytes()
        self.receipt = json.loads(self.raw)
        self.envelope = {"receipt": self.receipt, "receiptBytes": self.raw,
                         "receiptSha256": sha256_bytes(self.raw), "objectSha256": "sha256:" + "8" * 64}
        self.carrier = self.root / "carrier"
        self.records = capture_sdk_apple_validation_evidence([entry], self.carrier)
        self.policy = {name: str(self.root / name) for name in (
            "plan", "attestationPublicKey", "keyring", "keysDirectory", "toolingEvidence",
            "toolingPublicKey", "javaExecutable", "toolingKeyring", "toolingKeysDirectory")}
        self.policy.update(attestationTrustDomain="development", toolingTrustDomain="release")

    def make(self, **changes):
        values = dict(repository=self.root, policy_revision="c" * 40, policy=self.policy)
        values.update(changes)
        return admission.AppleValidationAdmission(self.carrier, self.records, **values)

    def test_exact_policy_forwarding_and_receipt_pairing_return_only_after_exit_without_cache(self):
        gate = self.make()
        events = []

        @contextmanager
        def handoff(root, **arguments):
            self.assertEqual(self.carrier / self.records[0]["evidenceRoot"], root)
            self.assertEqual({"expected_receipt_sha256": sha256_bytes(self.raw), "target": "ios-arm64",
                "plan": Path(self.policy["plan"]), "attestation_public_key": Path(self.policy["attestationPublicKey"]),
                "attestation_trust_domain": "development", "keyring": Path(self.policy["keyring"]),
                "keys_directory": Path(self.policy["keysDirectory"]), "repository_root": self.root,
                "tooling_evidence": Path(self.policy["toolingEvidence"]),
                "tooling_public_key": Path(self.policy["toolingPublicKey"]),
                "java_executable": Path(self.policy["javaExecutable"]), "policy_revision": "c" * 40,
                "required_trust_domain": "release", "tooling_keyring": Path(self.policy["toolingKeyring"]),
                "tooling_keys_directory": Path(self.policy["toolingKeysDirectory"])}, arguments)
            events.append("enter")
            yield {"receiptBytes": self.raw, "receipt": copy.deepcopy(self.receipt)}
            events.append("exit")

        with patch.object(admission, "verified_apple_validation_handoff", side_effect=handoff) as verify:
            self.assertIsNone(gate.verify(self.envelope))
            self.assertEqual(["enter", "exit"], events)
            self.assertIsNone(gate.verify(self.envelope))
            self.assertEqual(2, verify.call_count)
            self.assertEqual(["enter", "exit", "enter", "exit"], events)

    def test_handoff_receipt_mismatch_entry_failure_and_exit_failure_reject(self):
        gate = self.make()
        for mutation in ("raw", "receipt", "enter", "exit", "late-receipt"):
            @contextmanager
            def handoff(*args, **kwargs):
                if mutation == "enter":
                    raise ValueError("full replay entry rejected")
                value = {"receiptBytes": self.raw, "receipt": copy.deepcopy(self.receipt)}
                if mutation == "raw":
                    value["receiptBytes"] += b"changed"
                if mutation == "receipt":
                    value["receipt"]["producer"]["runAttempt"] += 1
                yield value
                if mutation == "exit":
                    raise ValueError("full replay exit rejected")
                if mutation == "late-receipt":
                    value["receipt"]["producer"]["runAttempt"] += 1

            with self.subTest(mutation=mutation), patch.object(admission, "verified_apple_validation_handoff", side_effect=handoff), \
                    self.assertRaises(ValueError):
                gate.verify(self.envelope)

    def test_missing_record_wrong_phase_and_malformed_envelope_do_not_enter_handoff(self):
        gate = self.make()
        simulator = self.fixture.entry("simulator", "ios-simulator-arm64")
        simulator_raw = (simulator / "capture/original/shard/phase-receipt.json").read_bytes()
        package = write_receipt(self.root / "package.json", product="sdk", component="sdk-ios", phase="package", target="ios",
            version="0.8.0", version_identity="0.8.0", upstream=[], context={"producer": self.fixture.producer},
            outputs=[output("fixture", "outputs/package.zip", b"package")])
        package_raw = canonical_json_bytes(package)
        candidates = [{**self.envelope, "receipt": json.loads(raw), "receiptBytes": raw, "receiptSha256": sha256_bytes(raw)}
                      for raw in (simulator_raw, package_raw)]
        candidates.extend(({**self.envelope, "receiptBytes": self.raw + b"changed"},
                           {**self.envelope, "receiptSha256": "sha256:" + "0" * 64}))
        with patch.object(admission, "verified_apple_validation_handoff") as verify:
            for index, envelope in enumerate(candidates):
                with self.subTest(case=index), self.assertRaises(ValueError):
                    gate.verify(envelope)
            verify.assert_not_called()

    def test_metadata_forwards_both_originals_and_rejects_late_envelope_mutation(self):
        from ci.products import sdk_apple_metadata_admission as metadata

        simulator = self.fixture.entry("simulator", "ios-simulator-arm64")
        simulator_raw = (simulator / "capture/original/shard/phase-receipt.json").read_bytes()
        receipt = write_receipt(self.root / "metadata.json", product="sdk", component="sdk-ios",
            phase="metadata", target="ios", version="0.8.0", version_identity="0.8.0", upstream=[],
            context={"producer": self.fixture.producer},
            outputs=[output("apple-metadata-content", "outputs/evidence/apple-metadata.json", b"fixture")])
        raw = canonical_json_bytes(receipt)

        def envelope(contents):
            return {"receipt": json.loads(contents), "receiptBytes": contents,
                    "receiptSha256": sha256_bytes(contents), "objectSha256": "sha256:" + "8" * 64}

        for mutation in (None, "metadata-digest", "metadata-object", "validation-digest", "validation-receipt"):
            selected = envelope(raw)
            predecessors = (envelope(self.raw), envelope(simulator_raw))
            gate = self.make()

            def verify(**arguments):
                self.assertEqual(raw, arguments["metadata_receipt_bytes"])
                self.assertEqual({"ios-arm64": self.raw, "ios-simulator-arm64": simulator_raw},
                    {target: path.read_bytes() for target, path in arguments["validation_receipts"].items()})
                self.assertEqual(self.policy, arguments["policy"])
                if mutation == "metadata-digest": selected["receiptSha256"] = "sha256:" + "0" * 64
                if mutation == "metadata-object": selected["objectSha256"] = "sha256:" + "0" * 64
                if mutation == "validation-digest": predecessors[0]["receiptSha256"] = "sha256:" + "0" * 64
                if mutation == "validation-receipt": predecessors[1]["receipt"]["producer"]["runAttempt"] += 1
                return receipt, raw

            with self.subTest(mutation=mutation), patch.object(metadata,
                    "verify_sdk_apple_metadata_receipt_admission", side_effect=verify):
                if mutation is None:
                    self.assertIsNone(gate.verify_metadata(selected, predecessors))
                else:
                    with self.assertRaisesRegex(ValueError, "envelope changed"):
                        gate.verify_metadata(selected, predecessors)
        with patch.object(metadata, "verify_sdk_apple_metadata_receipt_admission") as verify:
            for predecessors in ((), (envelope(self.raw),), (envelope(self.raw), envelope(self.raw))):
                with self.subTest(predecessors=len(predecessors)), self.assertRaises(ValueError):
                    self.make().verify_metadata(envelope(raw), predecessors)
            verify.assert_not_called()

    def test_caller_policy_is_strict_and_detached_from_later_dictionary_changes(self):
        for changed in ({"extra": "unknown"}, {"plan": "relative/plan"}, {"attestationPublicKey": None},
                        {"keyring": None}, {"attestationTrustDomain": "untrusted"},
                        {"toolingTrustDomain": "release", "toolingKeyring": None},
                        {"toolingTrustDomain": "development"}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.make(policy={**self.policy, **changed})
        with self.assertRaises(ValueError):
            self.make(policy_revision="HEAD")
        gate = self.make()
        original_plan = self.policy["plan"]
        self.policy["plan"] = str(self.root / "replacement")
        self.records[0]["target"] = "ios-simulator-arm64"

        @contextmanager
        def handoff(*args, **kwargs):
            self.assertEqual(Path(original_plan), kwargs["plan"])
            self.assertEqual("ios-arm64", kwargs["target"])
            yield {"receiptBytes": self.raw, "receipt": copy.deepcopy(self.receipt)}

        with patch.object(admission, "verified_apple_validation_handoff", side_effect=handoff):
            self.assertIsNone(gate.verify(self.envelope))

    def test_development_tooling_requires_no_release_key_overrides(self):
        gate = self.make(policy_revision="d" * 64, policy={**self.policy, "toolingTrustDomain": "development",
                                "toolingKeyring": None, "toolingKeysDirectory": None})

        @contextmanager
        def handoff(*args, **kwargs):
            self.assertEqual("d" * 64, kwargs["policy_revision"])
            self.assertEqual("development", kwargs["required_trust_domain"])
            self.assertIsNone(kwargs["tooling_keyring"])
            self.assertIsNone(kwargs["tooling_keys_directory"])
            yield {"receiptBytes": self.raw, "receipt": copy.deepcopy(self.receipt)}

        with patch.object(admission, "verified_apple_validation_handoff", side_effect=handoff):
            self.assertIsNone(gate.verify(self.envelope))

    def test_release_null_attestation_key_uses_shared_parser_and_forwards_pinned_keyring(self):
        policy = {**self.policy, "attestationTrustDomain": "release", "attestationPublicKey": None}
        parsed = admission.apple_validation_policy_arguments(policy)
        self.assertIsNone(parsed["attestation_public_key"])
        self.assertEqual("release", parsed["attestation_trust_domain"])
        self.assertEqual(Path(policy["keyring"]), parsed["keyring"])
        self.assertEqual(Path(policy["keysDirectory"]), parsed["keys_directory"])
        with patch.object(admission, "apple_validation_policy_arguments", wraps=admission.apple_validation_policy_arguments) as parser:
            gate = self.make(policy=policy)
            parser.assert_called_once_with(policy)

        @contextmanager
        def handoff(*args, **kwargs):
            self.assertEqual(parsed, {name: kwargs[name] for name in parsed})
            yield {"receiptBytes": self.raw, "receipt": copy.deepcopy(self.receipt)}

        with patch.object(admission, "verified_apple_validation_handoff", side_effect=handoff):
            self.assertIsNone(gate.verify(self.envelope))

    def test_shared_parser_rejects_development_null_key_and_incomplete_or_cross_domain_policy(self):
        for change in ({"attestationPublicKey": None}, {"attestationTrustDomain": "other"},
                       {"attestationTrustDomain": "release", "attestationPublicKey": None, "keyring": None},
                       {"attestationTrustDomain": "release", "attestationPublicKey": None, "keysDirectory": None},
                       {"toolingTrustDomain": "release", "toolingKeysDirectory": None},
                       {"toolingTrustDomain": "development", "toolingKeyring": None},
                       {"plan": "relative/plan"}, {"extra": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                admission.apple_validation_policy_arguments({**self.policy, **change})
        missing = dict(self.policy)
        missing.pop("attestationPublicKey")
        with self.assertRaises(ValueError):
            admission.apple_validation_policy_arguments(missing)


if __name__ == "__main__":
    unittest.main()
