"""Real signed synthetic protected-output to S858 forwarding, not hosted evidence."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_aggregate_handoff as fixture
from ci import runtime_aggregate_release as protected
from products import sdk_protected_runtime as forwarding
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    publish_regular_tree as actual_publish_regular_tree, sha256_bytes, snapshot_regular_tree,
)
from products.sdk_inputs import INVENTORY_NAME


class SdkProtectedRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = fixture.RuntimeAggregateHandoffTest
        source.setUpClass()
        cls.addClassCleanup(source.doClassCleanups)
        cls.source = source
        cls.carrier, cls.keyring, cls.keys = source.carrier, source.keyring, source.keys
        cls.raw_receipt = (cls.carrier / "aggregate-input/metadata-receipt.json").read_bytes()
        cls.digest = sha256_bytes(cls.raw_receipt)
        cls.key = load_canonical_json_bytes(cls.raw_receipt)["buildKey"]
        contract_receipt = load_canonical_json_bytes((cls.carrier /
            "selected-inputs/contract-input/execution-closure/receipts/metadata.json").read_bytes())
        cls.contract_payload_digest = next(record["sha256"] for record in contract_receipt["outputs"]
                                           if record["kind"] == "contract-bundle")
        cls.retained = source.source.work / "sdk-protected-retained"
        args = {**source.source.arguments(), "selected_root": cls.carrier / "selected-inputs",
                "release_handoff": cls.carrier, "variant_handoffs": {}, "token": None}
        with patch("reuse.api_request", side_effect=AssertionError("retained output contacted CI")), \
                patch.object(protected, "build_runtime_aggregate_attestation", side_effect=AssertionError("re-signing")):
            protected._attest_selected_runtime_aggregate(source.source.repository, cls.retained, **args)
        cls.selection = source.source.work / "sdk-selection"
        versions = cls.selection / "gradle/release/versions"
        versions.mkdir(parents=True)
        (versions / "sdk.txt").write_bytes(b"0.2.9\n")
        (versions / "contract.txt").write_bytes(b"0.2.0\n")
        (versions.parent / "sdk-default-runtime.txt").write_bytes(b"0.2.7\n")
        (versions.parent / "sdk-runtime-compatibility.json").write_bytes(canonical_json_bytes({
            "compatibleReleaseRange": ">=0.2.0 <0.3.0",
            "compatibleRuntimeCompatibilityRange": ">=0.2.0 <0.3.0"}))
        for arguments in (("init", "-q"), ("add", "gradle"),
                          ("-c", "user.name=Synthetic", "-c", "user.email=test@example.invalid",
                           "commit", "-qm", "synthetic SDK selection")):
            subprocess.run(["git", *arguments], cwd=cls.selection, check=True, capture_output=True)
        cls.revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cls.selection,
                                      check=True, capture_output=True, text=True).stdout.strip()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-protected-runtime-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.output = self.work / "forwarded"

    def stage(self, original=None, **changes):
        arguments = dict(expected_metadata_receipt_sha256=self.digest, expected_build_key=self.key,
            sdk_version="0.2.9", compatible_release_range=">=0.2.0 <0.3.0",
            compatible_runtime_compatibility_range=">=0.2.0 <0.3.0", keyring=self.keyring, keys_directory=self.keys,
            selection_repository_root=self.selection, selection_revision=self.revision)
        return forwarding.stage_protected_runtime_sdk_inputs(
            self.carrier if original is None else original, self.output, **{**arguments, **changes})

    def copy(self, source):
        destination = self.work / "original"
        snapshot_regular_tree(source, destination, allow_empty=True)
        return destination

    def test_real_fresh_and_retained_outputs_use_existing_full_bridge_and_preserve_history(self):
        inventories = []
        for name, original in (("fresh", self.carrier), ("retained", self.retained)):
            self.output = self.work / name
            before = regular_file_inventory(original, allow_empty=True)
            with patch("reuse.api_request", side_effect=AssertionError("forwarding contacted CI")), \
                    patch("products.runtime_aggregate.sign_manifest", side_effect=AssertionError("forwarding signed")), \
                    patch.object(forwarding, "stage_runtime_sdk_handoff", wraps=forwarding.stage_runtime_sdk_handoff) as bridge:
                options = {"expected_contract_payload_sha256": self.contract_payload_digest} if name == "fresh" else {}
                result = self.stage(original, **options)
            bridge.assert_called_once()
            if name == "fresh":
                self.assertEqual(self.contract_payload_digest, bridge.call_args.kwargs["expected_contract_payload_sha256"])
            else:
                self.assertNotIn("expected_contract_payload_sha256", bridge.call_args.kwargs)
            self.assertEqual({"sdk-inputs", "runtime-release"}, {path.name for path in self.output.iterdir()})
            self.assertEqual(before, regular_file_inventory(self.output / "runtime-release", allow_empty=True))
            self.assertEqual(before, regular_file_inventory(original, allow_empty=True))
            inventories.append(regular_file_inventory(self.output / "sdk-inputs"))
            self.assertEqual(result["inventory"], load_canonical_json_bytes(
                (self.output / "sdk-inputs" / INVENTORY_NAME).read_bytes()))
        self.assertEqual(inventories[0], inventories[1])

    def test_optional_contract_payload_mismatch_does_not_publish_protected_history(self):
        before = regular_file_inventory(self.carrier, allow_empty=True)
        self.assertNotEqual(self.contract_payload_digest, self.digest)
        with self.assertRaisesRegex(ValueError, "selected Contract payload"):
            self.stage(expected_contract_payload_sha256=self.digest)
        self.assertFalse(self.output.exists())
        self.assertEqual(before, regular_file_inventory(self.carrier, allow_empty=True))

    def test_malformed_optional_contract_payload_rejects_before_bridge(self):
        with patch.object(forwarding, "stage_runtime_sdk_handoff") as bridge:
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                self.stage(expected_contract_payload_sha256="not-a-digest")
            bridge.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_caller_pins_and_complete_git_policy_are_required_before_bridge(self):
        for changes in ({"expected_metadata_receipt_sha256": "sha256:" + "0" * 64},
                        {"expected_build_key": "sha256:" + "1" * 64},
                        {"expected_metadata_receipt_sha256": None}, {"keyring": None},
                        {"selection_repository_root": None}, {"selection_revision": None}):
            with self.subTest(changes=changes), patch.object(forwarding, "stage_runtime_sdk_handoff") as bridge, \
                    self.assertRaises(ValueError):
                self.stage(**changes)
            bridge.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_retained_layout_and_control_cannot_select_another_carrier(self):
        original = self.copy(self.retained)
        caller_path = original / "caller.json"
        raw = caller_path.read_bytes()
        caller = load_canonical_json_bytes(raw)
        for fields in ({"releaseDirectory": "../elsewhere"}, {"metadataReceiptSha256": "sha256:" + "0" * 64}):
            caller_path.write_bytes(canonical_json_bytes({**caller, **fields}))
            with self.subTest(fields=fields), patch.object(forwarding, "stage_runtime_sdk_handoff") as bridge, \
                    self.assertRaises(ValueError):
                self.stage(original)
            bridge.assert_not_called()
            self.assertFalse(self.output.exists())
        caller_path.write_bytes(raw)
        (original / "unexpected").write_bytes(b"not declared\n")
        with self.assertRaisesRegex(ValueError, "layout"):
            self.stage(original)
        self.assertFalse(self.output.exists())
        (original / "unexpected").unlink()
        (original / "retained-release/unexpected").write_bytes(b"not a signed original carrier file\n")
        with self.assertRaisesRegex(ValueError, "direct original carrier layout"):
            self.stage(original)
        self.assertFalse(self.output.exists())

    def test_existing_full_gate_rejects_bad_signature_and_git_version_mismatch(self):
        original = self.copy(self.carrier)
        signature = original / "aggregate-input/codex-agent-runtime-0.2.7.attestation.sig"
        raw = signature.read_bytes()
        signature.write_bytes(b"invalid signature\n")
        with self.assertRaises(ValueError):
            self.stage(original)
        self.assertFalse(self.output.exists())
        signature.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "SDK version differs"):
            self.stage(original, sdk_version="0.3.0")
        self.assertFalse(self.output.exists())
        extra = original / "unexpected"
        extra.write_bytes(b"not an original carrier\n")
        with self.assertRaises(ValueError):
            self.stage(original)
        self.assertFalse(self.output.exists())

    def test_original_late_mutation_fails_after_real_bridge_before_publication(self):
        original = self.copy(self.carrier)
        bridge = forwarding.stage_runtime_sdk_handoff
        path = original / "caller.json"
        raw = path.read_bytes()

        def mutate(*args, **kwargs):
            result = bridge(*args, **kwargs)
            self.assertFalse(self.output.exists())
            path.write_bytes(raw + b"late mutation\n")
            return result

        with patch.object(forwarding, "stage_runtime_sdk_handoff", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed before publication"):
            self.stage(original)
        self.assertFalse(self.output.exists())

    def test_prepared_late_mutation_cannot_publish_protected_sdk_inputs(self):
        def mutate_before_copy(source, destination, **kwargs):
            manifest = Path(source) / "sdk-inputs" / INVENTORY_NAME
            manifest.write_bytes(manifest.read_bytes() + b"late mutation\n")
            actual_publish_regular_tree(source, destination, **kwargs)

        with patch.object(forwarding, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.stage()
        self.assertFalse(self.output.exists())

    def test_bridge_result_mutation_before_outer_pin_cannot_be_baselined(self):
        bridge = forwarding.stage_runtime_sdk_handoff

        def mutate_after_bridge(carrier, destination, **kwargs):
            result = bridge(carrier, destination, **kwargs)
            manifest = Path(destination) / INVENTORY_NAME
            manifest.write_bytes(manifest.read_bytes() + b"late mutation\n")
            return result

        with patch.object(forwarding, "stage_runtime_sdk_handoff", side_effect=mutate_after_bridge), \
                self.assertRaisesRegex(ValueError, "inventory differs from verified bridge result"):
            self.stage()
        self.assertFalse(self.output.exists())

    def test_existing_destination_and_symbolic_or_overlapping_paths_preserve_originals(self):
        original = self.copy(self.carrier)
        before = regular_file_inventory(original, allow_empty=True)
        self.output.mkdir()
        sentinel = self.output / "sentinel"
        sentinel.write_bytes(b"preserve\n")
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.stage(original)
        self.assertEqual(b"preserve\n", sentinel.read_bytes())
        alias = self.work / "alias"
        alias.symlink_to(original, target_is_directory=True)
        for output in (original / "nested", alias / "nested"):
            self.output = output
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.stage(original)
        self.output = self.work / "safe-output"
        with self.assertRaises(ValueError):
            self.stage(alias)
        link = original / "symbolic"
        link.symlink_to(self.keyring)
        with self.assertRaises(ValueError):
            self.stage(original)
        link.unlink()
        self.assertEqual(before, regular_file_inventory(original, allow_empty=True))

    def test_output_inside_selection_checkout_rejects_before_bridge_without_modification(self):
        before = regular_file_inventory(self.selection, allow_empty=True)
        self.output = self.selection / "build/protected-sdk-handoff"
        with patch.object(forwarding, "stage_runtime_sdk_handoff") as bridge, \
                self.assertRaisesRegex(ValueError, "overlaps an original input"):
            self.stage()
        bridge.assert_not_called()
        self.assertFalse(self.output.exists())
        self.assertEqual(before, regular_file_inventory(self.selection, allow_empty=True))


if __name__ == "__main__":
    unittest.main()
