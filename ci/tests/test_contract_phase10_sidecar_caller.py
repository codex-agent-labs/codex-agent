"""Synthetic official API plus real local signed Contract/PGP caller evidence."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ci import contract_phase10_sidecar_caller as caller
from ci.tests import test_contract_equal_tree_original as original_fixture
from products.contract_phase10_inventory import verify_contract_phase10_inventory
from products.contract_phase10_maven import verify_contract_phase10_maven
from products.inventory import (
    load_canonical_json, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory, sha256_bytes, write_canonical_json as actual_write_canonical_json,
)


class ContractPhase10SidecarCallerTest(unittest.TestCase):
    def setUp(self) -> None:
        fixture = original_fixture.ContractEqualTreeOriginalTest(
            "test_exact_equal_tree_original_retains_signed_handoff_and_public_policy",
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.destination = fixture.root / "contract-sidecar-release"
        self.key = fixture.root / "publication-pgp-key.asc"
        home = tempfile.TemporaryDirectory(prefix="ct-gpg-", dir="/private/tmp")
        self.addCleanup(home.cleanup)
        self.home = Path(home.name)

    def invoke(self, fingerprint: str) -> dict:
        fixture = self.fixture
        with mock.patch("reuse.api_request", side_effect=fixture.api):
            return caller.produce_authenticated_contract_maven_sidecars(
                fixture.trusted, fixture.candidate, self.destination,
                trusted_source_sha=fixture.source_sha,
                trusted_workflow_sha=fixture.workflow_sha,
                trusted_promotion_workflow_sha=fixture.promotion_sha,
                final_commit=fixture.final, event_payload=fixture.event,
                environment=fixture.environment, token="synthetic-token",
                pgp_public_key=self.key,
                expected_pgp_key_sha256=sha256_bytes(self.key.read_bytes()),
                signing_home=self.home, signing_fingerprint=fingerprint, passphrase="",
            )

    def test_wrong_official_upload_cannot_reach_pgp_signer(self) -> None:
        self.key.write_bytes(b"independently pinned fixture PGP key\n")
        original = self.fixture.artifact["digest"]
        self.fixture.artifact["digest"] = "sha256:" + "0" * 64
        try:
            with mock.patch.object(caller, "produce_contract_phase10_maven_sidecars") as signer:
                with self.assertRaises(ValueError):
                    self.invoke("A" * 40)
                signer.assert_not_called()
        finally:
            self.fixture.artifact["digest"] = original
        self.assertFalse(self.destination.exists())

    def test_mutated_public_key_at_publication_cannot_return_success(self) -> None:
        self.key.write_bytes(b"independently pinned fixture PGP key\n")
        fixture = self.fixture
        captured = {}

        def signed(payload, sidecars, *_args):
            sidecars.mkdir()
            (sidecars / "fixture.asc").write_bytes(b"external signature\n")
            captured["signed"] = {"contractVersion": original_fixture.VERSION,
                                  "payloadSha256": sha256_bytes(payload.read_bytes()),
                                  "sidecarFiles": regular_file_inventory(sidecars)}
            return captured["signed"]

        def mutate_then_publish(source, destination, **kwargs):
            (Path(source) / "publication-pgp-public-key.asc").write_bytes(b"changed after verification\n")
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch.object(caller, "produce_contract_phase10_maven_sidecars", side_effect=signed), \
                mock.patch.object(caller, "verify_contract_phase10_maven",
                                  side_effect=lambda *_: captured["signed"]), \
                mock.patch.object(caller, "publish_regular_tree", side_effect=mutate_then_publish):
            with self.assertRaisesRegex(ValueError, "pinned inventory"):
                self.invoke("A" * 40)
        self.assertFalse(self.destination.exists())

    def test_mutated_selection_before_inventory_cannot_become_baseline(self) -> None:
        self.key.write_bytes(b"independently pinned fixture PGP key\n")
        captured = {}

        def signed(payload, sidecars, *_args):
            sidecars.mkdir()
            (sidecars / "fixture.asc").write_bytes(b"external signature\n")
            captured["signed"] = {"contractVersion": original_fixture.VERSION,
                                  "payloadSha256": sha256_bytes(payload.read_bytes()),
                                  "sidecarFiles": regular_file_inventory(sidecars)}
            return captured["signed"]

        def altered_control(path, value):
            actual_write_canonical_json(path, value)
            if Path(path).name == "sidecar-selection.json":
                Path(path).write_bytes(b"{}\n")

        with mock.patch.object(caller, "produce_contract_phase10_maven_sidecars", side_effect=signed), \
                mock.patch.object(caller, "verify_contract_phase10_maven",
                                  side_effect=lambda *_: captured["signed"]), \
                mock.patch.object(caller, "write_canonical_json", side_effect=altered_control), \
                mock.patch.object(caller, "publish_regular_tree") as publish:
            with self.assertRaisesRegex(ValueError, "original or PGP key changed"):
                self.invoke("A" * 40)
            publish.assert_not_called()
        self.assertFalse(self.destination.exists())

    @unittest.skipUnless(shutil.which("gpg") and shutil.which("ssh-keygen"),
                         "GnuPG and ssh-keygen are required")
    def test_official_original_is_retained_and_only_external_sidecars_are_new(self) -> None:
        command = ["gpg", "--homedir", str(self.home), "--batch", "--no-tty",
                   "--pinentry-mode", "loopback", "--passphrase", ""]
        generated = subprocess.run(
            [*command, "--quick-generate-key", "Contract Caller <caller@example.test>",
             "ed25519", "sign", "0"], capture_output=True, timeout=60,
        )
        self.assertEqual(0, generated.returncode, generated.stderr.decode())
        self.key.write_bytes(subprocess.run(
            [*command, "--armor", "--export", "caller@example.test"],
            check=True, capture_output=True, timeout=60,
        ).stdout)
        listing = subprocess.run(
            [*command, "--with-colons", "--fingerprint", "--list-secret-keys"],
            check=True, capture_output=True, timeout=60,
        ).stdout.decode()
        fingerprint = next(line.split(":")[9] for line in listing.splitlines()
                           if line.startswith("fpr:"))
        output = self.invoke(fingerprint)
        captured = self.destination / "original"
        record = verify_contract_phase10_inventory(captured / "contract-record")
        self.assertEqual(record, output["originalSelection"]["handoffInventory"])
        payload = (captured / "contract-record/handoff" /
                   f"codex-agent-contract-{record['contractVersion']}.zip")
        self.assertEqual(output["mavenSidecars"], verify_contract_phase10_maven(
            payload, self.destination / "maven-sidecars",
            self.destination / "publication-pgp-public-key.asc", sha256_bytes(self.key.read_bytes()),
        ))
        self.assertEqual(self.fixture.archive,
                         (captured / "original-evidence/upload.zip").read_bytes())
        self.assertEqual(self.key.read_bytes(),
                         (self.destination / "publication-pgp-public-key.asc").read_bytes())
        self.assertEqual(output["mavenSidecars"]["sidecarFiles"],
                         regular_file_inventory(self.destination / "maven-sidecars"))
        selected = load_canonical_json(self.destination / "sidecar-selection.json")
        self.assertEqual(output["originalSelection"], selected["originalSelection"])
        self.assertEqual(output["mavenSidecars"], selected["mavenSidecars"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.invoke(fingerprint)

    def test_cli_help_without_pythonpath(self) -> None:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        checked = subprocess.run(
            [sys.executable, "-B", str(Path(caller.__file__).resolve()), "--help"],
            cwd=self.fixture.root, env=environment, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, checked.returncode, checked.stderr)
        self.assertIn("--expected-pgp-key-sha256", checked.stdout)


if __name__ == "__main__":
    unittest.main()
