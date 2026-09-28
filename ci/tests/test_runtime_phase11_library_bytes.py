"""Synthetic offline Runtime library forwarding; no hosted S1048 authority."""

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from ci import runtime_phase10_library_caller as phase10
from ci import runtime_phase11_library_bytes as phase11
from ci.tests import test_runtime_aggregate_handoff as fixture
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes, snapshot_regular_tree,
)
from products.signatures import generate_development_key


class RuntimePhase11LibraryBytesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.RuntimeAggregateHandoffTest.setUpClass()
        cls.addClassCleanup(fixture.RuntimeAggregateHandoffTest.doClassCleanups)
        cls.source = fixture.RuntimeAggregateHandoffTest()
        cls.source.setUp()
        cls.addClassCleanup(cls.source.doCleanups)
        temporary = tempfile.TemporaryDirectory(prefix="runtime-phase11-library-test-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name).resolve()
        private, cls.root_public, _ = generate_development_key(cls.root / "root")
        cls.delegation = cls.root / "delegation"
        phase10.issue_authenticated_runtime_root_delegation(
            cls.delegation, keyring=cls.source.keyring, keys_directory=cls.source.keys,
            root_public_key=cls.root_public,
            expected_root_public_key_sha256=sha256_bytes(cls.root_public.read_bytes()),
            expected_keyring_sha256=sha256_bytes(cls.source.keyring.read_bytes()),
            expected_keys_inventory_sha256=phase11._inventory_digest(cls.source.keys),
            root_private_key=private)
        cls.receipt = (cls.source.carrier / "aggregate-input/metadata-receipt.json").read_bytes()
        cls.auth = cls.root / "authorizations"
        phase10.produce_authenticated_runtime_libraries(
            cls.source.carrier, cls.auth,
            expected_metadata_receipt_sha256=sha256_bytes(cls.receipt),
            expected_build_key=load_canonical_json_bytes(cls.receipt)["buildKey"],
            keyring=cls.source.keyring, keys_directory=cls.source.keys,
            root_public_key=cls.root_public,
            expected_root_fingerprint=phase10.public_key_fingerprint(cls.root_public.read_bytes()),
            expected_root_public_key_sha256=sha256_bytes(cls.root_public.read_bytes()),
            root_delegation=cls.delegation,
            expected_delegation_inventory_sha256=phase11._inventory_digest(cls.delegation),
            release_private_key=cls.source.source.context["private_key"])

    def pins(self, *, authorizations=None):
        authorizations = self.auth if authorizations is None else authorizations
        return dict(
            keyring=self.source.keyring, keys_directory=self.source.keys,
            root_public_key=self.root_public,
            expected_protected_inventory_sha256=phase11._inventory_digest(
                self.source.carrier, allow_empty=True),
            expected_delegation_inventory_sha256=phase11._inventory_digest(self.delegation),
            expected_authorizations_inventory_sha256=phase11._inventory_digest(authorizations),
            expected_keyring_sha256=sha256_bytes(self.source.keyring.read_bytes()),
            expected_keys_inventory_sha256=phase11._inventory_digest(self.source.keys),
            expected_root_public_key_sha256=sha256_bytes(self.root_public.read_bytes()),
            expected_metadata_receipt_sha256=sha256_bytes(self.receipt),
            expected_build_key=load_canonical_json_bytes(self.receipt)["buildKey"],
        )

    def test_forwards_exact_root_and_five_claim_bytes(self):
        destination = self.root / "forwarded"
        result = phase11.forward_verified_runtime_library_bytes(
            self.source.carrier, self.delegation, self.auth, destination, **self.pins())
        self.assertEqual(5, len(result["targets"]))
        self.assertEqual(regular_file_inventory(self.delegation),
                         regular_file_inventory(destination / "root-delegation"))
        self.assertEqual(regular_file_inventory(self.auth),
                         regular_file_inventory(destination / "library-authorizations"))
        self.assertEqual(self.root_public.read_bytes(),
                         (destination / "sdk-runtime-root.pub").read_bytes())

    def test_repinned_changed_claim_cannot_be_forwarded(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-claim-mutation-") as temporary:
            work = Path(temporary).resolve()
            altered = work / "altered"
            snapshot_regular_tree(self.auth, altered)
            claim = next(altered.glob("*/libcodex_agent.*.evidence/runtime-library-authorization.json"), None)
            if claim is None:
                claim = next(altered.glob("*/codex_agent.dll.evidence/runtime-library-authorization.json"))
            value = load_canonical_json_bytes(claim.read_bytes())
            value["runtimeVersion"] = "0.8.1"
            claim.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(ValueError, "claim differs from signed aggregate"):
                phase11.forward_verified_runtime_library_bytes(
                    self.source.carrier, self.delegation, altered, work / "rejected",
                    **self.pins(authorizations=altered))
            self.assertFalse((work / "rejected").exists())

    def test_late_copy_mutation_cannot_be_published(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-late-copy-") as temporary:
            destination = Path(temporary) / "rejected"
            def mutate_after_snapshot(source, output, **options):
                snapshot_regular_tree(source, output, **options)
                if output.name == "library-authorizations":
                    claim = next(output.glob("*/*.evidence/runtime-library-authorization.json"))
                    claim.write_bytes(claim.read_bytes() + b"x")
            with patch.object(phase11, "snapshot_regular_tree", side_effect=mutate_after_snapshot), \
                    self.assertRaisesRegex(ValueError, "Forwarded Runtime library evidence differs"):
                phase11.forward_verified_runtime_library_bytes(
                    self.source.carrier, self.delegation, self.auth, destination,
                    **self.pins())
            self.assertFalse(destination.exists())

    def test_token_and_signing_secrets_rejected_before_verification(self):
        for name in ("GITHUB_TOKEN", "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY",
                     "CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY"):
            with self.subTest(name=name), patch.dict(os.environ, {name: "forbidden"}), \
                    self.assertRaisesRegex(ValueError, "signing|token"):
                phase11.forward_verified_runtime_library_bytes(
                    self.source.carrier, self.delegation, self.auth,
                    self.root / "unauthorized", **self.pins())
            self.assertFalse((self.root / "unauthorized").exists())


if __name__ == "__main__":
    unittest.main()
