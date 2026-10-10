"""Real signed S858 consumer checks over synthetic products, not hosted acceptance."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_sdk_handoff as fixture
from products import sdk_inputs_verification as verifier
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from products.sdk_compatibility import load_sdk_compatibility_request
from products.sdk_inputs import COMPATIBILITY_NAME, INVENTORY_NAME, REQUEST_NAME
from products.signatures import generate_development_key


class VerifiedSdkInputsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.RuntimeSdkHandoffTest.setUpClass()
        cls.addClassCleanup(fixture.RuntimeSdkHandoffTest.doClassCleanups)
        source = fixture.RuntimeSdkHandoffTest()
        source.setUp()
        cls.addClassCleanup(source.doCleanups)
        cls.policy_repository, cls.revision = source.selection()
        source.stage(selection_repository_root=cls.policy_repository, selection_revision=cls.revision)
        cls.original, cls.keyring, cls.keys = source.output, source.keyring, source.keys
        arguments = load_sdk_compatibility_request(cls.original / REQUEST_NAME)
        receipt = load_canonical_json_bytes(arguments["contract_metadata_receipt"].read_bytes())
        cls.payload_digest = next(record["sha256"] for record in receipt["outputs"] if record["kind"] == "contract-bundle")
        cls.before = regular_file_inventory(cls.original)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-input-consumer-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()

    def tearDown(self):
        self.assertEqual(self.before, regular_file_inventory(self.original))

    def verify(self, root=None, **changes):
        return verifier.verified_sdk_inputs(self.original if root is None else root,
            **{"keyring": self.keyring, "keys_directory": self.keys,
               "selection_repository_root": self.policy_repository, "selection_revision": self.revision,
               "expected_contract_payload_sha256": self.payload_digest, **changes})

    def copy(self, name="inputs"):
        root = self.work / name
        snapshot_regular_tree(self.original, root)
        return root

    def inventory(self, root):
        # A self-consistent transport inventory must never replace product verification.
        (root / INVENTORY_NAME).write_bytes(canonical_json_bytes({"schemaVersion": 1, "kind": "sdk-inputs",
            "files": regular_file_inventory(root, excluded_paths=(INVENTORY_NAME,))}))

    def test_real_signed_recomputation_uses_private_originals_and_caller_policy(self):
        with patch("reuse.api_request", side_effect=AssertionError("SDK consumer contacted CI")), \
                patch.object(verifier, "produce_sdk_compatibility", wraps=verifier.produce_sdk_compatibility) as producer:
            with self.verify() as value:
                captured = value["directory"]
                self.assertNotEqual(self.original, captured)
                self.assertEqual(self.before, regular_file_inventory(captured))
                self.assertEqual((self.original / COMPATIBILITY_NAME).read_bytes(), canonical_json_bytes(value["compatibility"]))
                self.assertEqual("release", value["arguments"]["required_trust_domain"])
                for product in ("contract", "runtime"):
                    keyring = value["arguments"][f"{product}_keyring"]
                    self.assertFalse(keyring.is_relative_to(captured))
                    self.assertNotEqual(self.keyring, keyring)
                    self.assertEqual(self.keyring.read_bytes(), keyring.read_bytes())
                    self.assertEqual(regular_file_inventory(self.keys),
                                     regular_file_inventory(value["arguments"][f"{product}_keys_directory"]))
                self.assertTrue(value["arguments"]["contract_payload"].is_relative_to(captured))
            producer.assert_called_once()
        self.assertFalse(captured.exists())
        self.assertFalse(keyring.exists())

    def test_absolute_traversing_and_windows_request_paths_reject_before_producer(self):
        root = self.copy()
        request = load_canonical_json_bytes((root / REQUEST_NAME).read_bytes())
        for field, path in (("contractPayload", str(self.work / "external.zip")),
                            ("runtimeManifest", "../source/manifest.json"),
                            ("runtimeKeyring", "C:\\source\\policy.json"),
                            ("contractKeysDirectory", "C:/source/keys")):
            (root / REQUEST_NAME).write_bytes(canonical_json_bytes({**request, field: path}))
            self.inventory(root)
            with self.subTest(field=field), patch.object(verifier, "produce_sdk_compatibility") as producer:
                with self.assertRaises(ValueError):
                    with self.verify(root):
                        self.fail("transported path escaped the private inputs")
                producer.assert_not_called()

    def test_inventory_schema_file_tamper_and_symlinks_are_not_accepted(self):
        root = self.copy()
        inventory = (root / INVENTORY_NAME).read_bytes()
        for raw in (b"{}\n", inventory + b"\n", canonical_json_bytes({
                **load_canonical_json_bytes(inventory), "schemaVersion": True})):
            (root / INVENTORY_NAME).write_bytes(raw)
            with self.subTest(raw=raw[:40]), self.assertRaises(ValueError):
                with self.verify(root):
                    self.fail("malformed inventory admitted")
        (root / INVENTORY_NAME).write_bytes(inventory)
        path = root / COMPATIBILITY_NAME
        raw = path.read_bytes()
        path.write_bytes(raw + b"\n")
        with self.assertRaises(ValueError):
            with self.verify(root):
                self.fail("modified unlisted bytes admitted")
        path.write_bytes(raw)
        alias = self.work / "alias"
        alias.symlink_to(root, target_is_directory=True)
        with self.assertRaises(ValueError):
            with self.verify(alias):
                self.fail("symbolic input root admitted")

    def test_transported_policy_cannot_override_wrong_caller_policy_or_release_requirement(self):
        _, public, signing = generate_development_key(self.work / "unrelated-key")
        keys = self.work / "policy/keys"
        keys.mkdir(parents=True)
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        policy = load_canonical_json_bytes(self.keyring.read_bytes())
        keyring = keys.parent / "product-signing-keys.json"
        keyring.write_bytes(canonical_json_bytes({**policy, "retiredKeys": [],
            "activeKey": {name: signing[name] for name in ("keyId", "fingerprint")}}))
        with self.assertRaises(ValueError):
            with self.verify(keyring=keyring, keys_directory=keys):
                self.fail("transported trust replaced the caller's unrelated policy")
        root = self.copy()
        request = load_canonical_json_bytes((root / REQUEST_NAME).read_bytes())
        (root / REQUEST_NAME).write_bytes(canonical_json_bytes({**request, "requiredTrustDomain": "development"}))
        self.inventory(root)
        with self.assertRaisesRegex(ValueError, "release trust"):
            with self.verify(root):
                self.fail("development inputs admitted")

    def test_compatibility_git_policy_and_expected_payload_remain_independent_checks(self):
        root = self.copy()
        compatibility = load_canonical_json_bytes((root / COMPATIBILITY_NAME).read_bytes())
        (root / COMPATIBILITY_NAME).write_bytes(canonical_json_bytes({**compatibility, "sdkVersion": "0.2.10"}))
        self.inventory(root)
        with self.assertRaisesRegex(ValueError, "authenticated recomputation"):
            with self.verify(root):
                self.fail("self-consistent inventory replaced authenticated compatibility")
        wrong = "sha256:" + ("0" if self.payload_digest != "sha256:" + "0" * 64 else "1") * 64
        with self.assertRaisesRegex(ValueError, "selected Contract payload"):
            with self.verify(expected_contract_payload_sha256=wrong):
                self.fail("different current Contract payload admitted")
        repository, revision = fixture.RuntimeSdkHandoffTest.selection(self, contract="0.2.1")
        with self.assertRaisesRegex(ValueError, "original SDK Contract version"):
            with self.verify(selection_repository_root=repository, selection_revision=revision):
                self.fail("different original SDK Contract version admitted")

    def test_context_exit_rejects_original_captured_and_public_policy_mutation(self):
        for target in ("original", "captured", "policy"):
            root = self.copy(target)
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "changed during verification"):
                with self.verify(root) as value:
                    captured = value["directory"]
                    path = {"original": root / REQUEST_NAME, "captured": captured / REQUEST_NAME,
                            "policy": value["arguments"]["contract_keyring"]}[target]
                    path.write_bytes(path.read_bytes() + b"changed\n")
            self.assertFalse(captured.exists())


if __name__ == "__main__":
    unittest.main()
