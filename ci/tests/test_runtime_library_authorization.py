"""Synthetic signed original closure, not hosted release authority."""

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from ci import runtime_phase10_library_caller as caller
from ci.tests import test_runtime_aggregate_handoff as fixture
from products.inventory import (canonical_json_bytes, load_canonical_json_bytes,
    public_key_fingerprint, regular_file_inventory, sha256_bytes, snapshot_regular_tree)
from products.registry import NATIVE_TARGETS
from products.runtime_library_authorization import verified_runtime_libraries
from products.sdk_runtime_root import verify_external_library_authorization
from products.signatures import generate_development_key


class RuntimeLibraryAuthorizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.RuntimeAggregateHandoffTest.setUpClass()
        cls.addClassCleanup(fixture.RuntimeAggregateHandoffTest.doClassCleanups)
        cls.source = fixture.RuntimeAggregateHandoffTest()
        cls.source.setUp()
        cls.addClassCleanup(cls.source.doCleanups)
        policy = cls.source.source.policy
        cls.signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        cls.signing.update(policy["activeKey"])

    def test_signed_originals_project_exact_five_libraries_and_identities(self):
        with self.source.read() as verified:
            projected = verified_runtime_libraries(verified, self.signing)
            self.assertEqual(set(NATIVE_TARGETS), set(projected))
            for target, item in projected.items():
                claim = item["claim"]
                self.assertEqual(target, claim["runtimeIdentity"]["target"])
                self.assertEqual("0.2.7", claim["runtimeVersion"])
                self.assertEqual(sha256_bytes(item["library"]), claim["runtimeLibrarySha256"])
                self.assertTrue(item["fileName"])

    def test_observation_token_rejected_before_handoff_or_signing(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-token-negative-") as temporary:
            destination = Path(temporary) / "unauthorized"
            with patch.dict(os.environ, {"GITHUB_TOKEN": "observation-token"}), \
                    patch.object(caller, "verified_runtime_aggregate_handoff") as gate, \
                    patch.object(caller, "issue_root_delegation") as signer, \
                    self.assertRaisesRegex(ValueError, "observation token"):
                caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, destination,
                    expected_metadata_receipt_sha256="sha256:" + "a" * 64,
                    expected_build_key="sha256:" + "b" * 64,
                    keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=Path(temporary) / "missing-root.pub",
                    expected_root_fingerprint="sha256:" + "c" * 64,
                    expected_root_public_key_sha256="sha256:" + "d" * 64,
                    root_delegation=Path(temporary) / "missing-delegation",
                    expected_delegation_inventory_sha256="sha256:" + "e" * 64,
                    release_private_key=Path(temporary) / "missing-release-key",
                )
            gate.assert_not_called()
            signer.assert_not_called()
            self.assertFalse(destination.exists())
            with patch.dict(os.environ, {"GITHUB_TOKEN": "observation-token"}), \
                    patch.object(caller, "issue_root_delegation") as signer, \
                    self.assertRaisesRegex(ValueError, "observation token"):
                caller.issue_authenticated_runtime_root_delegation(
                    destination, keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=Path(temporary) / "missing-root.pub",
                    expected_root_public_key_sha256="sha256:" + "d" * 64,
                    expected_keyring_sha256="sha256:" + "f" * 64,
                    expected_keys_inventory_sha256="sha256:" + "0" * 64,
                    root_private_key=Path(temporary) / "missing-root-key")
            signer.assert_not_called()

    def test_root_and_release_signing_secrets_cannot_share_a_job(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-secret-split-") as temporary:
            work = Path(temporary)
            with patch.dict(os.environ, {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "forbidden"}), \
                    patch.object(caller, "issue_root_delegation") as issuer, \
                    self.assertRaisesRegex(ValueError, "product signing secret"):
                caller.issue_authenticated_runtime_root_delegation(
                    work / "delegation", keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=work / "missing-root.pub",
                    expected_root_public_key_sha256="sha256:" + "a" * 64,
                    expected_keyring_sha256="sha256:" + "b" * 64,
                    expected_keys_inventory_sha256="sha256:" + "c" * 64,
                    root_private_key=work / "missing-root-key")
            issuer.assert_not_called()
            with patch.dict(os.environ, {"CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY": "forbidden"}), \
                    patch.object(caller, "verified_runtime_aggregate_handoff") as gate, \
                    self.assertRaisesRegex(ValueError, "SDK root secret"):
                caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, work / "released",
                    expected_metadata_receipt_sha256="sha256:" + "a" * 64,
                    expected_build_key="sha256:" + "b" * 64,
                    keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=work / "missing-root.pub",
                    expected_root_fingerprint="sha256:" + "c" * 64,
                    expected_root_public_key_sha256="sha256:" + "d" * 64,
                    root_delegation=work / "missing-delegation",
                    expected_delegation_inventory_sha256="sha256:" + "e" * 64,
                    release_private_key=work / "missing-release-key")
            gate.assert_not_called()

    def test_protected_caller_signs_exact_external_bytes_after_full_handoff(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-authorization-test-") as temporary:
            work = Path(temporary).resolve()
            root_private, root_public, _ = generate_development_key(work / "root")
            fingerprint = public_key_fingerprint(root_public.read_bytes())
            root_digest = sha256_bytes(root_public.read_bytes())
            delegation = work / "delegation"
            delegated = caller.issue_authenticated_runtime_root_delegation(
                delegation, keyring=self.source.keyring, keys_directory=self.source.keys,
                root_public_key=root_public, expected_root_public_key_sha256=root_digest,
                expected_keyring_sha256=sha256_bytes(self.source.keyring.read_bytes()),
                expected_keys_inventory_sha256=sha256_bytes(canonical_json_bytes(
                    regular_file_inventory(self.source.keys))), root_private_key=root_private)
            receipt = load_canonical_json_bytes(
                (self.source.carrier / "aggregate-input/metadata-receipt.json").read_bytes())
            arguments = dict(
                expected_metadata_receipt_sha256=sha256_bytes(
                    (self.source.carrier / "aggregate-input/metadata-receipt.json").read_bytes()),
                expected_build_key=receipt["buildKey"], keyring=self.source.keyring,
                keys_directory=self.source.keys, root_public_key=root_public,
                expected_root_fingerprint=fingerprint, expected_root_public_key_sha256=root_digest,
                root_delegation=delegation,
                expected_delegation_inventory_sha256=delegated["inventorySha256"],
                release_private_key=self.source.source.context["private_key"],
            )
            destination = work / "released"
            with patch.object(caller, "verified_runtime_aggregate_handoff",
                              wraps=caller.verified_runtime_aggregate_handoff) as gate:
                result = caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, destination, **arguments)
            gate.assert_called_once()
            self.assertEqual(fingerprint, result["rootFingerprint"])
            self.assertEqual(delegated["inventorySha256"], result["delegationInventorySha256"])
            compatibility = load_canonical_json_bytes(self.source.source.chain["compatibility"].read_bytes())
            for target in NATIVE_TARGETS:
                paths = list((destination / target).glob("libcodex_agent.*")) + \
                    list((destination / target).glob("codex_agent.dll"))
                libraries = [path for path in paths if path.is_file()]
                self.assertEqual(1, len(libraries), target)
                library = libraries[0]
                claim = verify_external_library_authorization(
                    library.with_name(library.name + ".evidence"),
                    sdk_pinned_root_public_key=root_public.read_bytes(),
                    sdk_compatibility=compatibility, target=target, library_snapshot=library,
                )
                self.assertEqual(sha256_bytes(library.read_bytes()), claim["runtimeLibrarySha256"])
            with patch.object(caller, "verified_runtime_aggregate_handoff") as gate, \
                    self.assertRaisesRegex(ValueError, "caller pin"):
                caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, work / "wrong-root", **{
                        **arguments, "expected_root_fingerprint": sha256_bytes(b"wrong"),
                    })
            gate.assert_not_called()
            self.assertFalse((work / "wrong-root").exists())

    def test_corrupt_original_variant_signature_cannot_reach_private_keys_or_publish(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-corrupt-original-") as temporary:
            work = Path(temporary).resolve()
            corrupt = work / "corrupt-original"
            snapshot_regular_tree(self.source.carrier, corrupt, allow_empty=True)
            signatures = list((corrupt / "variant-inputs/macos-arm64").glob("*.attestation.sig"))
            self.assertEqual(1, len(signatures))
            signatures[0].write_bytes(signatures[0].read_bytes() + b"x")
            receipt = (self.source.carrier / "aggregate-input/metadata-receipt.json").read_bytes()
            root_private, root_public, _ = generate_development_key(work / "root")
            delegation = work / "delegation"
            delegated = caller.issue_authenticated_runtime_root_delegation(
                delegation, keyring=self.source.keyring, keys_directory=self.source.keys,
                root_public_key=root_public,
                expected_root_public_key_sha256=sha256_bytes(root_public.read_bytes()),
                expected_keyring_sha256=sha256_bytes(self.source.keyring.read_bytes()),
                expected_keys_inventory_sha256=sha256_bytes(canonical_json_bytes(
                    regular_file_inventory(self.source.keys))), root_private_key=root_private)
            destination = work / "unauthorized"
            with patch.object(caller, "verified_runtime_libraries", side_effect=AssertionError("claim signer reached")) as signer, \
                    self.assertRaises(ValueError):
                caller.produce_authenticated_runtime_libraries(
                    corrupt, destination,
                    expected_metadata_receipt_sha256=sha256_bytes(receipt),
                    expected_build_key=load_canonical_json_bytes(receipt)["buildKey"],
                    keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=root_public,
                    expected_root_fingerprint=public_key_fingerprint(root_public.read_bytes()),
                    expected_root_public_key_sha256=sha256_bytes(root_public.read_bytes()),
                    root_delegation=delegation,
                    expected_delegation_inventory_sha256=delegated["inventorySha256"],
                    release_private_key=work / "no-release-private-key",
                )
            signer.assert_not_called()
            self.assertFalse(destination.exists())

    def test_repinned_bad_delegation_cannot_reach_release_signer(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-bad-delegation-") as temporary:
            work = Path(temporary).resolve()
            root_private, root_public, _ = generate_development_key(work / "root")
            delegation = work / "delegation"
            delegated = caller.issue_authenticated_runtime_root_delegation(
                delegation, keyring=self.source.keyring, keys_directory=self.source.keys,
                root_public_key=root_public,
                expected_root_public_key_sha256=sha256_bytes(root_public.read_bytes()),
                expected_keyring_sha256=sha256_bytes(self.source.keyring.read_bytes()),
                expected_keys_inventory_sha256=sha256_bytes(canonical_json_bytes(
                    regular_file_inventory(self.source.keys))), root_private_key=root_private)
            signature = delegation / "root-delegation.sig"
            signature.write_bytes(signature.read_bytes() + b"tampered")
            tampered_pin = sha256_bytes(canonical_json_bytes(regular_file_inventory(delegation)))
            self.assertNotEqual(delegated["inventorySha256"], tampered_pin)
            receipt = (self.source.carrier / "aggregate-input/metadata-receipt.json").read_bytes()
            destination = work / "unauthorized"
            with patch.object(caller, "verified_runtime_aggregate_handoff") as gate, \
                    self.assertRaises(ValueError):
                caller.produce_authenticated_runtime_libraries(
                    self.source.carrier, destination,
                    expected_metadata_receipt_sha256=sha256_bytes(receipt),
                    expected_build_key=load_canonical_json_bytes(receipt)["buildKey"],
                    keyring=self.source.keyring, keys_directory=self.source.keys,
                    root_public_key=root_public,
                    expected_root_fingerprint=public_key_fingerprint(root_public.read_bytes()),
                    expected_root_public_key_sha256=sha256_bytes(root_public.read_bytes()),
                    root_delegation=delegation,
                    expected_delegation_inventory_sha256=tampered_pin,
                    release_private_key=self.source.source.context["private_key"])
            gate.assert_not_called()
            self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
