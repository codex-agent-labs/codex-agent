"""Phase-11 Contract forwarding preserves the exact authenticated Phase-10 tree."""

from __future__ import annotations

from pathlib import Path
import shutil
import unittest
from unittest import mock

from ci import contract_phase11_bytes as candidate
from ci.tests.test_contract_bundle import VERSION
from ci.tests import test_contract_phase10_maven_caller as phase10_tests
from products.inventory import (
    canonical_json_bytes, read_regular_file_bytes, regular_file_inventory, sha256_bytes,
)


@unittest.skipUnless(shutil.which("gpg") and shutil.which("ssh-keygen"),
                     "GnuPG and ssh-keygen are required")
class ContractPhase11BytesTest(unittest.TestCase):
    def test_exact_forwarding_and_independent_pin_or_sidecar_mutation_reject(self) -> None:
        phase10 = phase10_tests.ContractPhase10MavenCallerTest(
            "test_exact_original_payload_and_external_phase10_maven_sidecars",
        )
        self.addCleanup(phase10.doCleanups)
        phase10.setUp()
        with mock.patch("reuse.api_request", side_effect=phase10.fixture.api()):
            control = phase10.invoke()
        source = phase10.destination
        release = source / "contract-release-evidence"
        payload = release / "contract-input" / f"codex-agent-contract-{VERSION}.zip"
        policy = release / "caller-policy"
        pins = dict(
            expected_inventory_sha256=sha256_bytes(canonical_json_bytes(regular_file_inventory(source))),
            expected_contract_version=VERSION,
            expected_payload_sha256=control["mavenSidecars"]["payloadSha256"],
            expected_metadata_build_key=control["contractInventory"]["metadataBuildKey"],
            expected_source_commit=phase10.fixture.source_sha,
            expected_source_tree=control["releaseCaller"]["trustedSourceTree"],
            expected_workflow_sha=phase10.fixture.pin,
            expected_caller_sha256=sha256_bytes(read_regular_file_bytes(release / "caller.json")),
            expected_keyring_sha256=sha256_bytes(read_regular_file_bytes(
                policy / "product-signing-keys.json")),
            expected_keys_inventory_sha256=sha256_bytes(canonical_json_bytes(
                regular_file_inventory(policy / "keys"))),
            expected_pgp_key_sha256=sha256_bytes(read_regular_file_bytes(
                source / "publication-pgp-public-key.asc")),
        )
        destination = phase10.fixture.root / "contract-candidate"
        result = candidate.forward_verified_contract_phase10_bytes(source, destination, **pins)
        self.assertEqual(pins["expected_inventory_sha256"], result["phase10InventorySha256"])
        self.assertEqual(regular_file_inventory(source), regular_file_inventory(destination))
        self.assertEqual(payload.read_bytes(),
                         (destination / "contract-release-evidence/contract-input" / payload.name).read_bytes())
        with self.assertRaisesRegex(ValueError, "already exists"):
            candidate.forward_verified_contract_phase10_bytes(source, destination, **pins)
        with self.assertRaisesRegex(ValueError, "caller differs"):
            candidate.forward_verified_contract_phase10_bytes(
                source, phase10.fixture.root / "bad-caller", **{
                    **pins, "expected_caller_sha256": "sha256:" + "0" * 64,
                },
            )
        with self.assertRaisesRegex(ValueError, "verifier keys differ"):
            candidate.forward_verified_contract_phase10_bytes(
                source, phase10.fixture.root / "bad-key", **{
                    **pins, "expected_pgp_key_sha256": "sha256:" + "0" * 64,
                },
            )
        sidecar = next((source / "maven-sidecars").rglob("*.asc"))
        sidecar.write_bytes(b"not a valid detached signature\n")
        with self.assertRaises(ValueError):
            candidate.forward_verified_contract_phase10_bytes(
                source, phase10.fixture.root / "bad-signature", **{
                    **pins, "expected_inventory_sha256": sha256_bytes(canonical_json_bytes(
                        regular_file_inventory(source))),
                },
            )
        self.assertFalse((phase10.fixture.root / "bad-signature").exists())


if __name__ == "__main__":
    unittest.main()
