"""Real signed SDK/Runtime join; selection and official upload transport are explicit seams."""

from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci import sdk_workflow as receiver
from ci.tests import test_sdk_inputs_verification as fixture
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from products.registry import PhaseInstanceId
from products.runtime_aggregate_handoff import verified_runtime_aggregate_handoff
from products.sdk_inputs import COMPATIBILITY_NAME
from products.signatures import generate_development_key, sign_manifest


class SdkInputReceiverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = fixture.VerifiedSdkInputsTest
        source.setUpClass()
        cls.addClassCleanup(source.doClassCleanups)
        cls.sdk, cls.keyring, cls.keys = source.original, source.keyring, source.keys
        cls.repository, cls.revision, cls.payload_digest = source.policy_repository, source.revision, source.payload_digest
        cls.runtime = fixture.fixture.RuntimeSdkHandoffTest.carrier
        cls.original_inventories = {path: regular_file_inventory(path, allow_empty=True)
                                   for path in (cls.sdk, cls.runtime, cls.keyring.parent)}

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-input-receiver-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.plan = self.work / "impact-plan.json"
        self.plan.write_bytes(b'{"synthetic":"already replayed selection seam"}\n')
        self.plan_bytes = self.plan.read_bytes()
        self.discovery, self.state = self.work / "discovery", self.work / "state"
        self.selection = {"source": "released-default", "sdkVersion": "0.2.9", "defaultRuntimeVersion": "0.2.7",
            "contractVersion": "0.2.0", "contractPayloadSha256": self.payload_digest,
            "compatibleReleaseRange": ">=0.2.0 <0.3.0", "compatibleRuntimeCompatibilityRange": ">=0.2.0 <0.3.0",
            "consumers": [{"product": "sdk", "component": "python", "phase": "package", "target": "desktop"}]}
        self.options = {"artifact_id": 71, "artifact_sha256": "sha256:" + "a" * 64,
            "trusted_workflow_sha": "b" * 40, "keyring": self.keyring, "keys_directory": self.keys,
            "repository_root": self.repository, "environ": {"GITHUB_RUN_ID": "7"}, "token": "synthetic-token"}
        self.captures = []

    def tearDown(self):
        for path, inventory in self.original_inventories.items():
            self.assertEqual(inventory, regular_file_inventory(path, allow_empty=True))

    def capture(self, plan, destination, **arguments):
        self.assertEqual(self.plan, plan)
        self.assertEqual({name: self.options[name] for name in (
            "artifact_id", "artifact_sha256", "trusted_workflow_sha", "repository_root", "environ", "token")}
            | {"expected_source": self.selection["source"]}, arguments)
        self.captures.append(destination)
        original = destination / "original"
        snapshot_regular_tree(self.sdk, original / "sdk-inputs")
        if self.selection["source"] == "released-default":
            snapshot_regular_tree(self.runtime, original / "runtime-original", allow_empty=True)
            for phase in ("binary", "package", "validation", "metadata"):
                name = f"contract-contract-{phase}-common"
                snapshot_regular_tree(self.runtime / "selected-inputs/predecessors" / name,
                                      original / "current-contract" / name)
            (original / "selection.json").write_bytes(canonical_json_bytes(self.selection))
            (original / "transport.json").write_bytes(b'{"synthetic":"mocked official upload boundary"}\n')
        else:
            snapshot_regular_tree(self.runtime, original / "runtime-capture/original", allow_empty=True)
            (original / "runtime-capture/plan").mkdir()
            (original / "runtime-capture/plan/impact-plan.json").write_bytes(self.plan_bytes)
        with zipfile.ZipFile(destination / "transport.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for row in regular_file_inventory(original, allow_empty=True):
                archive.writestr(row["relativePath"], (original / row["relativePath"]).read_bytes())
        (destination / "plan").mkdir()
        (destination / "plan/impact-plan.json").write_bytes(self.plan_bytes)
        (destination / "capture-transport.json").write_bytes(b'{"synthetic":"mocked official upload boundary"}\n')

    @contextmanager
    def receive(self, **changes):
        with patch.object(receiver, "_selection", return_value=(
                {"validationCommit": self.revision}, self.selection, self.plan_bytes)) as selection, \
                patch.object(receiver.product_reuse, "capture_sdk_inputs_upload", side_effect=self.capture), \
                patch("reuse.api_request", side_effect=AssertionError("unexpected receiver network")):
            with receiver.verified_inputs(self.plan, self.discovery, self.state, **{**self.options, **changes}) as value:
                selection.assert_called_once_with(self.plan, self.discovery, self.state, self.repository,
                                                self.options["environ"], sdk_validation_tooling=None)
                yield value

    def test_both_layouts_join_exact_signed_receipts_full_runtime_and_sdk_inputs(self):
        for source in ("released-default", "current-runtime"):
            self.selection["source"] = source
            with self.subTest(source=source), self.receive() as value:
                self.assertEqual(self.selection, value["selection"])
                sdk, runtime = value["sdk"], value["runtime"]
                self.assertEqual(self.original_inventories[self.sdk], regular_file_inventory(sdk["directory"]))
                self.assertEqual(self.original_inventories[self.runtime], regular_file_inventory(runtime["directory"], allow_empty=True))
                self.assertEqual(load_canonical_json_bytes((self.sdk / COMPATIBILITY_NAME).read_bytes()), sdk["compatibility"])
                for product, component, target in (("contract", "contract", "common"),
                                                   ("runtime", "runtime-aggregate", "aggregate")):
                    identity = PhaseInstanceId(product, component, "metadata", target)
                    sdk_receipt = sdk["arguments"][f"{product}_metadata_receipt"]
                    self.assertEqual(runtime["receiptBytes"][identity], sdk_receipt.read_bytes())
                    self.assertNotEqual(runtime["originalPhases"][identity]["receiptPath"], sdk_receipt)
                self.assertEqual(50, len(runtime["originalPhases"]))
                paths = (value["capture"], sdk["directory"], runtime["directory"], sdk["arguments"]["runtime_keyring"])
                self.assertTrue(all(path.exists() for path in paths))
            self.assertTrue(all(not path.exists() for path in paths))
        self.assertEqual(self.plan_bytes, self.plan.read_bytes())

    def test_unrelated_caller_policy_cannot_use_the_transported_original_keys(self):
        _, public, signing = generate_development_key(self.work / "wrong-key")
        keys = self.work / "wrong-policy/keys"
        keys.mkdir(parents=True)
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        keyring = keys.parent / "product-signing-keys.json"
        policy = load_canonical_json_bytes(self.keyring.read_bytes())
        keyring.write_bytes(canonical_json_bytes({**policy, "retiredKeys": [],
            "activeKey": {name: signing[name] for name in ("keyId", "fingerprint")}}))
        with self.assertRaises(ValueError):
            with self.receive(keyring=keyring, keys_directory=keys):
                self.fail("transported keys substituted for caller policy")
        self.assertEqual(1, len(self.captures))
        self.assertFalse(self.captures[0].exists())

    def test_same_receipts_with_distinct_trusted_aggregate_attestations_do_not_join(self):
        # Genuine synthetic key rotation, not an alternate raw product chain:
        # all content and 50 receipts remain identical. Both signatures are
        # trusted, but the consumer must pair the exact attestation it verified.
        private, public, signing = generate_development_key(self.work / "rotated-key")
        signing = {**signing, "trustDomain": "release"}
        policy = load_canonical_json_bytes(self.keyring.read_bytes())
        keys = self.work / "rotated-policy/keys"
        snapshot_regular_tree(self.keys, keys)
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        keyring = keys.parent / "product-signing-keys.json"
        retired = [*policy["retiredKeys"], policy["activeKey"]]
        keyring.write_bytes(canonical_json_bytes({**policy,
            "activeKey": {name: signing[name] for name in ("keyId", "fingerprint")},
            "retiredKeys": sorted(retired, key=lambda record: record["keyId"])}))

        original_runtime = self.runtime
        self.runtime = self.work / "rotated-runtime"
        snapshot_regular_tree(original_runtime, self.runtime, allow_empty=True)
        name = "codex-agent-runtime-0.2.7.attestation.json"
        original_attestation = load_canonical_json_bytes((original_runtime / "aggregate-input" / name).read_bytes())
        signed = self.work / "new-signature" / name
        signed.parent.mkdir()
        replacement = {**original_attestation, "signing": signing}
        signed.write_bytes(canonical_json_bytes(replacement))
        signature = sign_manifest(signed, private, signing)
        (self.runtime / "aggregate-input" / name).write_bytes(signed.read_bytes())
        (self.runtime / "aggregate-input" / signature.name).write_bytes(signature.read_bytes())
        (self.runtime / "aggregate-input/public-key.pub").write_bytes(public.read_bytes())
        self.options.update(keyring=keyring, keys_directory=keys)

        # Full original carrier verification, not a mocked signature-only proof.
        with verified_runtime_aggregate_handoff(self.runtime, keyring=keyring, keys_directory=keys) as verified:
            self.assertEqual(replacement, verified["attestation"])
            self.assertNotEqual(original_attestation, verified["attestation"])
            self.assertEqual(50, len(verified["receiptBytes"]))
            for identity, raw in verified["receiptBytes"].items():
                relative = verified["originalPhases"][identity]["receiptPath"].relative_to(verified["directory"])
                self.assertEqual((original_runtime / relative).read_bytes(), raw)
        before = regular_file_inventory(self.runtime, allow_empty=True)
        with self.assertRaisesRegex(ValueError, "different.*attestation"):
            with self.receive():
                self.fail("distinct trusted attestations joined despite identical original receipts")
        self.assertEqual(before, regular_file_inventory(self.runtime, allow_empty=True))
        self.assertEqual(1, len(self.captures))
        self.assertFalse(self.captures[0].exists())

    def test_plan_and_captured_archive_changes_during_use_reject_and_clean_all_contexts(self):
        for target in ("plan", "archive"):
            try:
                with self.subTest(target=target), self.assertRaisesRegex(ValueError, "changed during use"):
                    with self.receive() as value:
                        paths = (value["capture"], value["sdk"]["directory"], value["runtime"]["directory"])
                        path = self.plan if target == "plan" else value["capture"] / "transport.zip"
                        path.write_bytes(path.read_bytes() + b"mutation during consumer use\n")
                self.assertTrue(all(not path.exists() for path in paths))
            finally:
                self.plan.write_bytes(self.plan_bytes)


if __name__ == "__main__":
    unittest.main()
