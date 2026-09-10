"""Real signed synthetic Runtime-to-S858 composition, not hosted execution."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_aggregate_handoff as fixture
from products import runtime_sdk_handoff as bridge
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    snapshot_regular_tree, verify_regular_file_inventory,
)
from products.registry import NATIVE_TARGETS
from products.sdk_compatibility import load_sdk_compatibility_request, produce_sdk_compatibility
from products.sdk_inputs import REQUEST_NAME, COMPATIBILITY_NAME, INVENTORY_NAME
from products.signatures import generate_development_key


class RuntimeSdkHandoffTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = fixture.RuntimeAggregateHandoffTest
        source.setUpClass()
        cls.addClassCleanup(source.doClassCleanups)
        cls.carrier, cls.keyring, cls.keys = source.carrier, source.keyring, source.keys

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-sdk-forward-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.output = self.work / "sdk-inputs"

    def stage(self, root=None, **changes):
        return bridge.stage_runtime_sdk_handoff(self.carrier if root is None else root,
            **{"destination": self.output, "sdk_version": "0.2.9",
               "compatible_release_range": ">=0.2.0 <0.3.0",
               "compatible_runtime_compatibility_range": ">=0.2.0 <0.3.0",
               "keyring": self.keyring, "keys_directory": self.keys, **changes})

    def test_full_gate_forwards_exact_original_inputs_and_existing_s858_writer(self):
        before = regular_file_inventory(self.carrier, allow_empty=True)
        with patch("reuse.api_request", side_effect=AssertionError("forwarding contacted CI")), \
                patch("products.runtime_aggregate.sign_manifest", side_effect=AssertionError("forwarding signed")), \
                patch.object(bridge, "verified_runtime_aggregate_handoff",
                             wraps=bridge.verified_runtime_aggregate_handoff) as full, \
                patch.object(bridge, "stage_sdk_inputs", wraps=bridge.stage_sdk_inputs) as writer:
            result = self.stage()
        full.assert_called_once()
        writer.assert_called_once()
        self.assertEqual(before, regular_file_inventory(self.carrier, allow_empty=True))
        self.assertEqual({"inputs", REQUEST_NAME, COMPATIBILITY_NAME, INVENTORY_NAME},
                         {path.name for path in self.output.iterdir()})
        verify_regular_file_inventory(self.output, result["inventory"]["files"], with_kind=False,
                                      excluded_paths=(INVENTORY_NAME,))
        arguments = load_sdk_compatibility_request(self.output / REQUEST_NAME)
        self.assertEqual("release", arguments["required_trust_domain"])
        self.assertEqual((self.carrier / "aggregate-input/metadata-receipt.json").read_bytes(),
                         arguments["runtime_metadata_receipt"].read_bytes())
        self.assertEqual((self.carrier / "selected-inputs/contract-input/execution-closure/receipts/metadata.json").read_bytes(),
                         arguments["contract_metadata_receipt"].read_bytes())
        for target in NATIVE_TARGETS:
            original = self.carrier / "variant-inputs" / target
            for phase in ("binary", "package", "validation", "metadata"):
                self.assertEqual((original / "receipts" / f"{phase}.json").read_bytes(),
                                 arguments["variant_phase_receipts"][target][phase].read_bytes())
            for field in ("variant_bundles", "variant_attestations", "variant_attestation_signatures", "variant_public_keys"):
                staged = arguments[field][target]
                self.assertEqual((original / staged.name).read_bytes(), staged.read_bytes())
        compatibility = load_canonical_json_bytes((self.output / COMPATIBILITY_NAME).read_bytes())
        self.assertEqual("0.2.9", compatibility["sdkVersion"])
        self.assertEqual("0.2.7", compatibility["runtime"]["defaultRuntimeVersion"])

    def test_module_cli_without_pythonpath_forwards_original_signed_evidence(self):
        before = regular_file_inventory(self.carrier, allow_empty=True)
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        result = subprocess.run([
            sys.executable, "-m", "ci.products.sdk_inputs",
            "--runtime-handoff", str(self.carrier), "--output", str(self.output),
            "--sdk-version", "0.2.9",
            "--compatible-release-range", ">=0.2.0 <0.3.0",
            "--compatible-runtime-compatibility-range", ">=0.2.0 <0.3.0",
            "--keyring", str(self.keyring), "--keys-directory", str(self.keys),
        ], cwd=Path(__file__).resolve().parents[2], env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        self.assertEqual(0, result.returncode, result.stderr.decode("utf-8", errors="replace"))
        self.assertEqual({"inputs", REQUEST_NAME, COMPATIBILITY_NAME, INVENTORY_NAME},
                         {path.name for path in self.output.iterdir()})
        inventory = load_canonical_json_bytes((self.output / INVENTORY_NAME).read_bytes())
        verify_regular_file_inventory(self.output, inventory["files"], with_kind=False,
                                      excluded_paths=(INVENTORY_NAME,))
        arguments = load_sdk_compatibility_request(self.output / REQUEST_NAME)
        self.assertEqual("release", arguments["required_trust_domain"])
        aggregate = self.carrier / "aggregate-input"
        for field, filename in (
            ("runtime_metadata_receipt", "metadata-receipt.json"),
            ("runtime_attestation", "codex-agent-runtime-0.2.7.attestation.json"),
            ("runtime_attestation_signature", "codex-agent-runtime-0.2.7.attestation.sig"),
            ("runtime_public_key", "public-key.pub"),
        ):
            self.assertEqual((aggregate / filename).read_bytes(), arguments[field].read_bytes())
        for target in NATIVE_TARGETS:
            for phase in ("binary", "package", "validation", "metadata"):
                self.assertEqual((self.carrier / "variant-inputs" / target / "receipts" / f"{phase}.json").read_bytes(),
                                 arguments["variant_phase_receipts"][target][phase].read_bytes())
        compatibility = load_canonical_json_bytes((self.output / COMPATIBILITY_NAME).read_bytes())
        self.assertEqual("0.2.9", compatibility["sdkVersion"])
        self.assertEqual("0.2.7", compatibility["runtime"]["defaultRuntimeVersion"])
        self.assertEqual(before, regular_file_inventory(self.carrier, allow_empty=True))

    def test_relocated_retired_policy_output_replays_without_original_carrier(self):
        relocated = self.work / "original-carrier"
        snapshot_regular_tree(self.carrier, relocated, allow_empty=True)
        keys = self.work / "retired/keys"
        snapshot_regular_tree(self.keys, keys)
        keyring = keys.parent / "product-signing-keys.json"
        policy = load_canonical_json_bytes(self.keyring.read_bytes())
        keyring.write_bytes(canonical_json_bytes({**policy, "activeKey": None,
            "retiredKeys": [policy["activeKey"], *policy["retiredKeys"]]}))
        self.stage(relocated, keyring=keyring, keys_directory=keys)
        # S858 paths must be self-contained; hide every supplied original input.
        for source in (relocated, keys.parent):
            source.rename(source.with_name(source.name + "-absent"))
        moved = self.work / "moved-sdk-inputs"
        self.output.rename(moved)
        arguments = load_sdk_compatibility_request(moved / REQUEST_NAME)
        output = self.work / "replay" / COMPATIBILITY_NAME
        output.parent.mkdir()
        with patch("reuse.api_request", side_effect=AssertionError("replay contacted CI")):
            produce_sdk_compatibility(output=output, **arguments)
        self.assertEqual((moved / COMPATIBILITY_NAME).read_bytes(), output.read_bytes())

    def test_wrong_caller_policy_and_tampered_original_do_not_publish(self):
        _, public, signing = generate_development_key(self.work / "wrong-key")
        keys = self.work / "wrong-policy/keys"
        keys.mkdir(parents=True)
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        policy = load_canonical_json_bytes(self.keyring.read_bytes())
        keyring = keys.parent / "product-signing-keys.json"
        keyring.write_bytes(canonical_json_bytes({**policy, "retiredKeys": [],
            "activeKey": {name: signing[name] for name in ("keyId", "fingerprint")}}))
        with self.assertRaises(ValueError):
            self.stage(keyring=keyring, keys_directory=keys)
        self.assertFalse(self.output.exists())
        root = self.work / "tampered"
        snapshot_regular_tree(self.carrier, root, allow_empty=True)
        receipt = root / "variant-inputs/linux-x64/receipts/package.json"
        receipt.write_bytes(receipt.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            self.stage(root)
        self.assertFalse(self.output.exists())

    def test_invalid_range_and_late_original_mutation_never_publish(self):
        with self.assertRaises(ValueError):
            self.stage(compatible_release_range=">=9.0.0 <10.0.0")
        self.assertFalse(self.output.exists())
        root = self.work / "mutating"
        snapshot_regular_tree(self.carrier, root, allow_empty=True)
        original = root / "caller.json"
        before = original.read_bytes()
        writer = bridge.stage_sdk_inputs

        def mutate_after_success(*args, **kwargs):
            result = writer(*args, **kwargs)
            original.write_bytes(before + b"\n")
            return result

        try:
            with patch.object(bridge, "stage_sdk_inputs", side_effect=mutate_after_success), \
                    self.assertRaisesRegex(ValueError, "changed"):
                self.stage(root)
            self.assertFalse(self.output.exists())
        finally:
            original.write_bytes(before)

    def test_output_overlap_collision_and_symlink_preserve_originals(self):
        before = regular_file_inventory(self.carrier, allow_empty=True)
        linked = self.work / "linked"
        linked.symlink_to(self.carrier, target_is_directory=True)
        self.output.mkdir()
        (self.output / "sentinel").write_bytes(b"original")
        for destination in (self.carrier / "new-sdk-inputs", self.carrier,
                            self.keys / "new-sdk-inputs", linked / "new-sdk-inputs", self.output):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.stage(destination=destination)
        self.assertEqual(b"original", (self.output / "sentinel").read_bytes())
        self.assertEqual(before, regular_file_inventory(self.carrier, allow_empty=True))


if __name__ == "__main__":
    unittest.main()
