"""The Phase-10 Contract PGP cutover follows original-CI release admission."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ci import contract_phase10_maven_caller as caller
from ci.tests.test_contract_bundle import VERSION
from ci.tests import test_contract_release_capture as release_fixture
from products.contract_phase10_maven import verify_contract_phase10_maven
from products.inventory import (
    load_canonical_json, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory, sha256_bytes,
    write_canonical_json as actual_write_canonical_json,
)


@unittest.skipUnless(shutil.which("gpg") and shutil.which("ssh-keygen"),
                     "GnuPG and ssh-keygen are required")
class ContractPhase10MavenCallerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        home = tempfile.TemporaryDirectory(prefix="contract-p10-pgp-", dir="/private/tmp")
        cls.addClassCleanup(home.cleanup)
        cls.home = Path(home.name)
        command = ["gpg", "--homedir", str(cls.home), "--batch", "--no-tty",
                   "--pinentry-mode", "loopback", "--passphrase", ""]
        generated = subprocess.run(
            [*command, "--quick-generate-key", "Contract P10 <contract@example.test>",
             "ed25519", "sign", "0"], capture_output=True, timeout=60,
        )
        if generated.returncode != 0:
            raise RuntimeError(generated.stderr.decode())
        cls.public_key = subprocess.run(
            [*command, "--armor", "--export", "contract@example.test"],
            check=True, capture_output=True, timeout=60,
        ).stdout
        listing = subprocess.run(
            [*command, "--with-colons", "--fingerprint", "--list-secret-keys"],
            check=True, capture_output=True, timeout=60,
        ).stdout.decode()
        cls.fingerprint = next(line.split(":")[9] for line in listing.splitlines()
                               if line.startswith("fpr:"))

    def setUp(self) -> None:
        fixture = release_fixture.ContractReleaseCaptureTest(
            "test_complete_original_ci_pipeline_signs_exact_payload_and_preserves_external_originals",
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.destination = fixture.root / "phase10-maven"
        self.key = fixture.root / "maven-public.asc"
        self.key.write_bytes(self.public_key)

    def invoke(self, *, key_digest: str | None = None):
        f = self.fixture
        with mock.patch("reuse.api_request", side_effect=f.api()):
            return caller.produce_contract_phase10_maven_handoff(
                f.repository_root, self.destination, trusted_source_sha=f.source_sha,
                trusted_workflow_sha=f.pin, artifact_id=f.upload_artifact["id"],
                artifact_sha256=f.upload_artifact["digest"], transport_producer=f.producer,
                contract_version=VERSION, event_payload=f.event, environment=f.environment,
                token="not-a-real-token", pgp_public_key=self.key,
                expected_pgp_key_sha256=key_digest or sha256_bytes(self.key.read_bytes()),
                signing_home=self.home, signing_fingerprint=self.fingerprint, passphrase="",
            )

    def test_exact_original_payload_and_external_phase10_maven_sidecars(self) -> None:
        result = self.invoke()
        release = self.destination / "contract-release-evidence"
        payload = release / "contract-input" / f"codex-agent-contract-{VERSION}.zip"
        self.assertEqual(self.fixture.payload.read_bytes(), payload.read_bytes())
        self.assertEqual(result["releaseFiles"], regular_file_inventory(release))
        self.assertEqual(result["mavenSidecars"], verify_contract_phase10_maven(
            payload, self.destination / "maven-sidecars",
            self.destination / "publication-pgp-public-key.asc", sha256_bytes(self.key.read_bytes()),
        ))
        self.assertEqual(result, load_canonical_json(self.destination / "sidecar-selection.json"))
        self.assertEqual(self.fixture.public_key.read_bytes(),
                         (release / "contract-input/public-key.pub").read_bytes())
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.invoke()

    def test_wrong_independent_pgp_pin_prevents_original_capture_and_signing(self) -> None:
        with mock.patch.object(caller, "attest_contract_ci") as original, \
                mock.patch.object(caller, "produce_contract_phase10_maven_sidecars") as signer:
            with self.assertRaisesRegex(ValueError, "independent pin"):
                self.invoke(key_digest="sha256:" + "0" * 64)
            original.assert_not_called()
            signer.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_failed_original_admission_never_invokes_pgp_signer(self) -> None:
        old = self.fixture.upload_artifact["digest"]
        self.fixture.upload_artifact["digest"] = "sha256:" + "0" * 64
        try:
            with mock.patch.object(caller, "produce_contract_phase10_maven_sidecars") as signer:
                with self.assertRaises(ValueError):
                    self.invoke()
                signer.assert_not_called()
        finally:
            self.fixture.upload_artifact["digest"] = old
        self.assertFalse(self.destination.exists())

    def test_public_key_mutated_during_publication_cannot_return_success(self) -> None:
        def mutate_then_publish(source, destination, **kwargs):
            (Path(source) / "publication-pgp-public-key.asc").write_bytes(b"mutated key\n")
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch.object(caller, "publish_regular_tree", side_effect=mutate_then_publish):
            with self.assertRaisesRegex(ValueError, "pinned inventory"):
                self.invoke()
        self.assertFalse(self.destination.exists())

    def test_sidecar_changed_before_inventory_pin_cannot_be_published(self) -> None:
        def write_then_mutate(path, value):
            actual_write_canonical_json(path, value)
            if Path(path).name == "sidecar-selection.json":
                next((Path(path).parent / "maven-sidecars").rglob("*.asc")).write_bytes(b"changed before pin\n")

        with mock.patch.object(caller, "write_canonical_json", side_effect=write_then_mutate), \
                self.assertRaises(ValueError):
            self.invoke()
        self.assertFalse(self.destination.exists())

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
