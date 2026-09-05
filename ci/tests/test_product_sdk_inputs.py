"""Real trust verification over synthetic products; no hosted/package acceptance."""

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes, snapshot_regular_tree, verify_regular_file_inventory,
)
from ci.products.sdk_compatibility import load_sdk_compatibility_request, produce_sdk_compatibility
from ci.products.sdk_inputs import COMPATIBILITY_NAME, INVENTORY_NAME, REQUEST_NAME, main, stage_sdk_inputs
from ci.products.signatures import sign_manifest
from ci.tests.test_product_native_chain import build_chain


def _request(arguments: dict) -> dict:
    def paths(value):
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {key: paths(member) for key, member in value.items()}
        return value

    result = {"schemaVersion": 1}
    for name, value in arguments.items():
        if value is None or name == "runtime_stage_root":
            continue
        head, *tail = name.split("_")
        result[head + "".join(part.title() for part in tail)] = paths(value)
    return result


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class SdkInputsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-inputs-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chain = build_chain(cls.root / "synthetic-products", 17)
        cls.original_request = cls.root / "original-request.json"
        cls.original_request.write_bytes(canonical_json_bytes(_request(cls.chain["compatibility_args"])))
        cls.handoff = cls.root / "handoff"
        cls.result = stage_sdk_inputs(cls.original_request, cls.handoff)

    def test_relocatable_exact_inputs_and_immutable_publication(self):
        inventory_bytes = (self.handoff / INVENTORY_NAME).read_bytes()
        self.assertEqual(self.result["inventorySha256"], sha256_bytes(inventory_bytes))
        verify_regular_file_inventory(
            self.handoff, self.result["inventory"]["files"], with_kind=False,
            excluded_paths=(INVENTORY_NAME,),
        )
        self.assertEqual((self.handoff / COMPATIBILITY_NAME).read_bytes(), self.chain["compatibility"].read_bytes())
        staged = load_sdk_compatibility_request(self.handoff / REQUEST_NAME)
        original = load_sdk_compatibility_request(self.original_request)

        def exact(left, right):
            if isinstance(left, Path):
                self.assertTrue(right.is_relative_to(self.handoff))
                self.assertEqual(left.read_bytes(), right.read_bytes())
            elif isinstance(left, dict):
                self.assertEqual(left.keys(), right.keys())
                for key in left:
                    exact(left[key], right[key])
            else:
                self.assertEqual(left, right)

        exact(original, staged)
        self.assertEqual(
            regular_file_inventory(original["contract_attestation"].parent / "execution-closure"),
            regular_file_inventory(staged["contract_attestation"].parent / "execution-closure"),
        )
        self.assertNotIn(str(self.root), (self.handoff / REQUEST_NAME).read_text())
        with tempfile.TemporaryDirectory() as temporary:
            relocated = Path(temporary).resolve() / "relocated"
            snapshot_regular_tree(self.handoff, relocated)
            # Hide only test-owned originals. Success must depend on the handoff.
            source = self.chain["root"]
            hidden = source.with_name("hidden-originals")
            source.rename(hidden)
            try:
                replay = relocated.parent / "replayed"
                self.assertEqual(self.result, stage_sdk_inputs(relocated / REQUEST_NAME, replay))
                before = regular_file_inventory(replay)
                with self.assertRaisesRegex(ValueError, "must not exist"):
                    stage_sdk_inputs(relocated / REQUEST_NAME, replay)
                self.assertEqual(before, regular_file_inventory(replay))
            finally:
                hidden.rename(source)

    def test_tampered_or_missing_evidence_never_publishes(self):
        for case in ("receipt", "signature", "payload", "closure", "symlink", "missing-target"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                copied = root / "inputs"
                snapshot_regular_tree(self.handoff, copied)
                request = copied / REQUEST_NAME
                values = load_sdk_compatibility_request(request)
                if case == "receipt":
                    path = values["variant_phase_receipts"]["linux-x64"]["metadata"]
                    value = load_canonical_json_bytes(path.read_bytes())
                    value["producer"]["runId"] += 1
                    path.write_bytes(canonical_json_bytes(value))
                elif case == "signature":
                    values["runtime_attestation_signature"].write_bytes(b"invalid signature\n")
                elif case == "payload":
                    path = values["variant_bundles"]["linux-x64"]
                    path.write_bytes(path.read_bytes() + b"tamper")
                elif case == "closure":
                    (values["contract_attestation"].parent / "execution-closure/receipts/binary.json").unlink()
                elif case == "symlink":
                    path = values["contract_payload"]
                    moved = path.with_suffix(".original")
                    path.rename(moved)
                    path.symlink_to(moved)
                else:
                    value = load_canonical_json_bytes(request.read_bytes())
                    del value["variantBundles"]["linux-x64"]
                    request.write_bytes(canonical_json_bytes(value))
                output = root / "must-not-exist"
                with self.assertRaises((OSError, ValueError)):
                    stage_sdk_inputs(request, output)
                self.assertFalse(output.exists())

    def test_release_keyring_transport_is_public_only_and_preserves_product_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "release-fixture"
            snapshot_regular_tree(self.handoff, source)
            request = source / REQUEST_NAME
            values = load_sdk_compatibility_request(request)
            raw = load_canonical_json_bytes(request.read_bytes())
            signing = {**self.chain["context"]["signing"], "trustDomain": "release", "keyId": "fixture-release"}
            keys = root / "keys"
            keys.mkdir()
            (keys / "fixture-release.pub").write_bytes(self.chain["context"]["public_key"].read_bytes())
            # A directory snapshot would disclose this unrequested private key.
            (keys / "private-key").write_bytes(self.chain["context"]["private_key"].read_bytes())
            keyring = root / "keyring.json"
            keyring.write_bytes(canonical_json_bytes({
                "schemaVersion": 1, "namespace": signing["namespace"], "algorithm": signing["algorithm"],
                "trustDomain": "release", "activeKey": {"keyId": signing["keyId"], "fingerprint": signing["fingerprint"]},
                "retiredKeys": [],
            }))
            # Fixture-only external reattestation, never payload or original receipt rewriting.
            def attest(path, signature, value):
                value["signing"] = signing
                path.write_bytes(canonical_json_bytes(value))
                signature.unlink()
                sign_manifest(path, self.chain["context"]["private_key"], signing).rename(signature)

            attest(values["contract_attestation"], values["contract_attestation_signature"],
                   load_canonical_json_bytes(values["contract_attestation"].read_bytes()))
            aggregate = load_canonical_json_bytes(values["runtime_attestation"].read_bytes())
            for record in aggregate["variants"]:
                target = record["target"]
                path = values["variant_attestations"][target]
                attest(path, values["variant_attestation_signatures"][target], load_canonical_json_bytes(path.read_bytes()))
                record["variantAttestationSha256"] = sha256_bytes(path.read_bytes())
            attest(values["runtime_attestation"], values["runtime_attestation_signature"], aggregate)
            raw["requiredTrustDomain"] = "release"
            for product in ("contract", "runtime"):
                raw[f"{product}Keyring"] = str(keyring)
                raw[f"{product}KeysDirectory"] = str(keys)
            request.write_bytes(canonical_json_bytes(raw))
            output = root / "release-handoff"
            self.assertEqual(main(["--request", str(request), "--output", str(output)]), 0)
            staged = load_sdk_compatibility_request(output / REQUEST_NAME)
            for product in ("contract", "runtime"):
                self.assertEqual({path.name for path in staged[f"{product}_keys_directory"].iterdir()}, {"fixture-release.pub"})
                self.assertEqual(staged[f"{product}_keyring"].read_bytes(), keyring.read_bytes())
            self.assertEqual((output / COMPATIBILITY_NAME).read_bytes(), (self.handoff / COMPATIBILITY_NAME).read_bytes())
            (root / "verified").mkdir()
            produce_sdk_compatibility(output=root / "verified" / COMPATIBILITY_NAME, **staged)

    def test_size_limit_and_symlink_destination_do_not_publish(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch("ci.products.sdk_inputs._FILE_LIMIT", 1):
                with self.assertRaisesRegex(ValueError, "size is invalid"):
                    stage_sdk_inputs(self.original_request, root / "oversized")
            self.assertFalse((root / "oversized").exists())
            outside = root / "outside"
            outside.mkdir()
            (root / "linked").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                stage_sdk_inputs(self.original_request, root / "linked/result")
            self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
