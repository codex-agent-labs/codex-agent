"""Signed synthetic historical SDK/Runtime joins, not CI transport authentication."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_inputs_verification as fixture
from products import sdk_apple_original_inputs as verifier
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, snapshot_regular_tree,
)
from products.registry import PhaseInstanceId
from products.signatures import generate_development_key, sign_manifest


class AppleOriginalInputsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = fixture.VerifiedSdkInputsTest
        source.setUpClass()
        cls.addClassCleanup(source.doClassCleanups)
        cls.sdk, cls.keyring, cls.keys = source.original, source.keyring, source.keys
        cls.repository, cls.revision = source.policy_repository, source.revision
        cls.payload_digest = source.payload_digest
        cls.runtime = fixture.fixture.RuntimeSdkHandoffTest.carrier
        cls.originals = {path: regular_file_inventory(path, allow_empty=True)
                         for path in (cls.sdk, cls.runtime, cls.keyring.parent)}

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-original-inputs-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.capture = self.work / "capture"
        self.source = "released-default"

    def tearDown(self):
        for path, inventory in self.originals.items():
            self.assertEqual(inventory, regular_file_inventory(path, allow_empty=True))

    def stage(self, source="released-default", *, runtime=None):
        self.source = source
        original = self.capture / "original"
        snapshot_regular_tree(self.sdk, original / "sdk-inputs")
        selected_runtime = self.runtime if runtime is None else runtime
        if source == "released-default":
            snapshot_regular_tree(selected_runtime, original / "runtime-original", allow_empty=True)
            (original / "current-contract").mkdir()
            (original / "selection.json").write_bytes(canonical_json_bytes({"source": source}))
            (original / "transport.json").write_bytes(b'{"fixture":"authenticated transport boundary"}\n')
        else:
            snapshot_regular_tree(selected_runtime, original / "runtime-capture/original", allow_empty=True)
            (original / "runtime-capture/plan").mkdir()
            (original / "runtime-capture/plan/impact-plan.json").write_bytes(b'{"fixture":"original plan"}\n')
        # Opaque capture records are caller-authenticated prerequisites, not
        # independently parsed/self-authenticating evidence in this helper.
        (self.capture / "transport.zip").write_bytes(b"opaque original upload bytes")
        (self.capture / "capture-transport.json").write_bytes(b'{"fixture":"observed original upload"}\n')
        (self.capture / "original-package-receipt.json").write_bytes(b'{"fixture":"caller-verified original receipt"}\n')
        (self.capture / "plan").mkdir()
        (self.capture / "plan/impact-plan.json").write_bytes(b'{"fixture":"original plan"}\n')

    def verify(self, **changes):
        return verifier.verified_apple_original_inputs(self.capture, **{
            "expected_source": self.source, "keyring": self.keyring, "keys_directory": self.keys,
            "selection_repository_root": self.repository, "selection_revision": self.revision,
            "expected_contract_payload_sha256": self.payload_digest, **changes})

    def test_both_original_sources_join_real_signed_bytes_and_expire_private_paths(self):
        for source in ("released-default", "current-runtime"):
            self.capture = self.work / source
            self.stage(source)
            before = regular_file_inventory(self.capture, allow_empty=True)
            with self.subTest(source=source), patch("reuse.api_request", side_effect=AssertionError("no network")):
                with self.verify() as value:
                    self.assertEqual({"sdk", "runtime"}, set(value))
                    sdk, runtime = value["sdk"], value["runtime"]
                    self.assertEqual(self.originals[self.sdk], regular_file_inventory(sdk["directory"]))
                    self.assertEqual(self.originals[self.runtime], regular_file_inventory(runtime["directory"], allow_empty=True))
                    self.assertEqual(50, len(runtime["originalPhases"]))
                    for product, component, target in (("contract", "contract", "common"),
                                                       ("runtime", "runtime-aggregate", "aggregate")):
                        identity = PhaseInstanceId(product, component, "metadata", target)
                        self.assertEqual(runtime["receiptBytes"][identity],
                                         sdk["arguments"][f"{product}_metadata_receipt"].read_bytes())
                    paths = (sdk["directory"], runtime["directory"], sdk["arguments"]["runtime_keyring"])
                    self.assertTrue(all(path.exists() and not path.is_relative_to(self.capture) for path in paths))
                self.assertTrue(all(not path.exists() for path in paths))
            self.assertEqual(before, regular_file_inventory(self.capture, allow_empty=True))

    def test_wrong_or_missing_original_authority_does_not_fall_back_to_current_selection(self):
        self.stage()
        for changes in ({"expected_source": "newest"}, {"expected_source": "current-runtime"},
                        {"selection_revision": None}, {"keyring": None}, {"keys_directory": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError), \
                    patch.object(verifier, "verified_sdk_inputs") as sdk:
                with self.verify(**changes):
                    self.fail("missing or contradictory caller authority accepted")
            sdk.assert_not_called()
        for changes in ({"selection_revision": "HEAD"},
                        {"expected_contract_payload_sha256": "sha256:" + "0" * 64}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                with self.verify(**changes):
                    self.fail("wrong original Git selection or Contract payload accepted")
        repository, revision = fixture.fixture.RuntimeSdkHandoffTest.selection(self, contract="9.0.0")
        with self.assertRaisesRegex(ValueError, "original SDK Contract version"):
            with self.verify(selection_repository_root=repository, selection_revision=revision):
                self.fail("different exact original Contract version accepted")

    def test_wrong_caller_keys_cannot_be_replaced_by_transported_policy(self):
        self.stage()
        _, public, signing = generate_development_key(self.work / "wrong-key")
        keys = self.work / "wrong-policy/keys"
        keys.mkdir(parents=True)
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        keyring = keys.parent / "product-signing-keys.json"
        original = load_canonical_json_bytes(self.keyring.read_bytes())
        keyring.write_bytes(canonical_json_bytes({**original, "retiredKeys": [],
            "activeKey": {field: signing[field] for field in ("keyId", "fingerprint")}}))
        with self.assertRaises(ValueError):
            with self.verify(keyring=keyring, keys_directory=keys):
                self.fail("transported keys overrode unrelated caller policy")

    def test_distinct_valid_attestation_with_identical_receipts_is_rejected(self):
        private, public, signing = generate_development_key(self.work / "rotated-key")
        signing = {**signing, "trustDomain": "release"}
        keys = self.work / "rotated-policy/keys"
        snapshot_regular_tree(self.keys, keys)
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        policy = load_canonical_json_bytes(self.keyring.read_bytes())
        keyring = keys.parent / "product-signing-keys.json"
        keyring.write_bytes(canonical_json_bytes({**policy,
            "activeKey": {field: signing[field] for field in ("keyId", "fingerprint")},
            "retiredKeys": sorted([*policy["retiredKeys"], policy["activeKey"]], key=lambda row: row["keyId"])}))
        runtime = self.work / "rotated-runtime"
        snapshot_regular_tree(self.runtime, runtime, allow_empty=True)
        name = "codex-agent-runtime-0.2.7.attestation.json"
        attestation = load_canonical_json_bytes((runtime / "aggregate-input" / name).read_bytes())
        signed = self.work / "signed" / name
        signed.parent.mkdir()
        signed.write_bytes(canonical_json_bytes({**attestation, "signing": signing}))
        signature = sign_manifest(signed, private, signing)
        (runtime / "aggregate-input" / name).write_bytes(signed.read_bytes())
        (runtime / "aggregate-input" / signature.name).write_bytes(signature.read_bytes())
        (runtime / "aggregate-input/public-key.pub").write_bytes(public.read_bytes())
        # Both signatures are genuinely valid under the same caller policy;
        # the join must still enforce the exact original attestation identity.
        with verifier.verified_runtime_aggregate_handoff(runtime, keyring=keyring, keys_directory=keys):
            pass
        self.stage(runtime=runtime)
        with self.assertRaisesRegex(ValueError, "different original attestations"):
            with self.verify(keyring=keyring, keys_directory=keys):
                self.fail("distinct trusted original attestations were joined")

    def test_exact_metadata_receipt_pairing_is_checked_after_full_gates(self):
        self.stage()
        full = verifier.verified_runtime_aggregate_handoff

        @contextmanager
        def changed_receipt(*args, **kwargs):
            # A bounded fault injection AFTER the real full signed verifier,
            # testing the joining comparison, not alternate receipt admission.
            with full(*args, **kwargs) as value:
                identity = PhaseInstanceId("contract", "contract", "metadata", "common")
                yield {**value, "receiptBytes": {**value["receiptBytes"], identity: b"different original"}}

        with patch.object(verifier, "verified_runtime_aggregate_handoff", changed_receipt), \
                self.assertRaisesRegex(ValueError, "different original receipts"):
            with self.verify():
                self.fail("mismatched original metadata receipt joined")

    def test_complete_capture_private_inputs_and_caller_policy_are_rechecked(self):
        for target in ("opaque-archive", "private-sdk", "caller-policy"):
            self.capture = self.work / target
            self.stage()
            policy = self.work / f"{target}-policy"
            snapshot_regular_tree(self.keys, policy / "keys")
            (policy / self.keyring.name).write_bytes(self.keyring.read_bytes())
            with self.subTest(target=target), self.assertRaises(ValueError):
                with self.verify(keyring=policy / self.keyring.name, keys_directory=policy / "keys") as value:
                    paths = (value["sdk"]["directory"], value["runtime"]["directory"])
                    path = (self.capture / "transport.zip" if target == "opaque-archive" else
                            value["sdk"]["arguments"]["runtime_metadata_receipt"] if target == "private-sdk" else
                            policy / self.keyring.name)
                    path.write_bytes(path.read_bytes() + b"changed during original replay\n")
            self.assertTrue(all(not path.exists() for path in paths))

    def test_symbolic_capture_rejects_and_consumer_exception_still_checks_originals(self):
        self.stage()
        alias = self.work / "alias"
        alias.symlink_to(self.capture, target_is_directory=True)
        original = self.capture
        self.capture = alias
        with self.assertRaises(ValueError):
            with self.verify():
                self.fail("symbolic capture accepted")
        self.capture = original
        with self.assertRaisesRegex(ValueError, "capture or caller policy changed"):
            with self.verify():
                path = self.capture / "original-package-receipt.json"
                path.write_bytes(path.read_bytes() + b"late mutation\n")
                raise RuntimeError("consumer failed too")


if __name__ == "__main__":
    unittest.main()
