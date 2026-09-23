"""Synthetic sidecar checks, not protected-run or real PGP acceptance."""

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import sha256_bytes
from ci.products.inventory import snapshot_regular_tree as actual_snapshot_regular_tree
from ci.products.contract_model import CONTRACT_CHECKSUM_SUFFIXES
from ci.products.runtime_phase10_maven import verify_runtime_phase10_maven
from ci.tests.test_product_runtime_aggregate import Fixture


_FINGERPRINT = "A" * 40


class RuntimePhase10MavenTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.fixture = Fixture(root / "source")
        self.payload = root / "payload"
        self.payload.mkdir()
        self.manifest = self.fixture.produce(self.payload)["manifestPath"]
        for source in self.fixture.maven_inputs:
            destination = self.payload / source["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(Path(source["file"]).read_bytes())
        self.sidecars = root / "sidecars"
        self.sidecars.mkdir()
        for source in self.fixture.maven_inputs:
            if source["role"] != "checksum":
                path = self.sidecars / (source["path"] + ".asc")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"synthetic detached signature\n")
                for suffix in CONTRACT_CHECKSUM_SUFFIXES:
                    (path.parent / (path.name + suffix)).write_bytes(
                        (hashlib.new(suffix[1:], path.read_bytes()).hexdigest() + "\n").encode(),
                    )
        self.key = root / "pgp-key.asc"
        self.key.write_bytes(b"synthetic public key\n")

    @staticmethod
    def fake_gpg(*arguments):
        if "--list-keys" in arguments:
            return f"pub:::::::::\nfpr:::::::::{_FINGERPRINT}:\n"
        return ""

    def verify(self):
        with patch("ci.products.runtime_phase10_maven._run_gpg", side_effect=self.fake_gpg) as gpg:
            record = verify_runtime_phase10_maven(
                self.payload, self.manifest, self.sidecars, self.key,
                sha256_bytes(self.key.read_bytes()),
            )
        return record, gpg.call_args_list

    def test_exact_aggregate_owned_primaries_and_detached_sidecars(self):
        record, calls = self.verify()
        self.assertEqual("runtime", record["product"])
        self.assertEqual(len(self.fixture.maven_inputs) + 1, len(record["payloadFiles"]))
        self.assertEqual(5 * sum(source["role"] != "checksum" for source in self.fixture.maven_inputs),
                         len(record["sidecarFiles"]))
        self.assertEqual(len(record["sidecarFiles"]) // 5,
                         sum("--verify" in call.args for call in calls))
        self.assertEqual(_FINGERPRINT, record["pgpPublicKey"]["fingerprint"])

    def test_missing_extra_or_changed_sidecar_fails_before_pgp(self):
        signature = next(self.sidecars.rglob("*.asc"))
        signature.unlink()
        with patch("ci.products.runtime_phase10_maven._run_gpg") as gpg:
            with self.assertRaisesRegex(ValueError, "signature inventory"):
                self.verify()
            gpg.assert_not_called()
        signature.write_bytes(b"synthetic detached signature\n")
        extra = self.sidecars / "extra.asc"
        extra.write_bytes(b"extra\n")
        with self.assertRaisesRegex(ValueError, "signature inventory"):
            self.verify()

    def test_signature_checksum_must_match_exact_signature_bytes(self):
        checksum = next(self.sidecars.rglob("*.asc.sha256"))
        checksum.write_bytes(b"0" * 64 + b"\n")
        with self.assertRaisesRegex(ValueError, "signature checksum"):
            self.verify()

    def test_changed_private_snapshot_fails_before_pgp_even_if_source_is_restored(self):
        primary = next(source for source in self.fixture.maven_inputs if source["role"] != "checksum")

        def substitute(source, destination):
            actual_snapshot_regular_tree(source, destination)
            if Path(source) == self.payload:
                (Path(destination) / primary["path"]).write_bytes(b"different snapshot bytes\n")

        with patch("ci.products.runtime_phase10_maven.snapshot_regular_tree", side_effect=substitute), \
                patch("ci.products.runtime_phase10_maven._run_gpg") as gpg:
            with self.assertRaisesRegex(ValueError, "snapshot differs"):
                verify_runtime_phase10_maven(
                    self.payload, self.manifest, self.sidecars, self.key,
                    sha256_bytes(self.key.read_bytes()),
                )
            gpg.assert_not_called()

    def test_changed_primary_and_unpinned_key_fail(self):
        with self.assertRaisesRegex(ValueError, "pinned bytes"):
            verify_runtime_phase10_maven(
                self.payload, self.manifest, self.sidecars, self.key, sha256_bytes(b"another key"),
            )
        primary = next(source for source in self.fixture.maven_inputs if source["role"] != "checksum")
        (self.payload / primary["path"]).write_bytes(b"tampered primary\n")
        with self.assertRaisesRegex(ValueError, "Maven bytes"):
            self.verify()

    def test_pgp_failure_and_multi_key_fail_closed(self):
        with patch("ci.products.runtime_phase10_maven._run_gpg", side_effect=ValueError("PGP failed")):
            with self.assertRaisesRegex(ValueError, "PGP failed"):
                verify_runtime_phase10_maven(
                    self.payload, self.manifest, self.sidecars, self.key,
                    sha256_bytes(self.key.read_bytes()),
                )
        with patch("ci.products.runtime_phase10_maven._run_gpg",
                   side_effect=lambda *args: f"pub:::::::::\nfpr:::::::::{_FINGERPRINT}:\n"
                   "pub:::::::::\nfpr:::::::::BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB:\n"
                   if "--list-keys" in args else ""):
            with self.assertRaisesRegex(ValueError, "one identifiable primary key"):
                verify_runtime_phase10_maven(
                    self.payload, self.manifest, self.sidecars, self.key,
                    sha256_bytes(self.key.read_bytes()),
                )

    @unittest.skipUnless(shutil.which("gpg"), "GnuPG unavailable")
    def test_real_gpg_rejects_synthetic_public_key_and_signatures(self):
        with self.assertRaisesRegex(ValueError, "PGP verification failed"):
            verify_runtime_phase10_maven(
                self.payload, self.manifest, self.sidecars, self.key,
                sha256_bytes(self.key.read_bytes()),
            )

    @unittest.skipUnless(shutil.which("gpg"), "GnuPG unavailable")
    def test_real_gpg_round_trip_and_mutated_signature(self):
        home = Path(self.temporary.name) / "fixture-gnupg"
        home.mkdir(mode=0o700)
        command = ["gpg", "--homedir", str(home), "--batch", "--no-tty",
                   "--pinentry-mode", "loopback", "--passphrase", ""]
        generated = subprocess.run(
            [*command, "--quick-generate-key", "Runtime Fixture <runtime@example.test>",
             "ed25519", "sign", "0"], capture_output=True, timeout=60,
        )
        self.assertEqual(0, generated.returncode, generated.stderr.decode())
        exported = subprocess.run(
            [*command, "--armor", "--export", "runtime@example.test"],
            check=True, capture_output=True, timeout=60,
        ).stdout
        self.key.write_bytes(exported)
        signatures = []
        for source in self.fixture.maven_inputs:
            if source["role"] == "checksum":
                continue
            signature = self.sidecars / (source["path"] + ".asc")
            signed = subprocess.run(
                [*command, "--yes", "--armor", "--detach-sign", "--output", str(signature),
                 str(self.payload / source["path"])],
                capture_output=True, timeout=60,
            )
            self.assertEqual(0, signed.returncode, signed.stderr.decode())
            signatures.append(signature)
            for suffix in CONTRACT_CHECKSUM_SUFFIXES:
                signature.with_name(signature.name + suffix).write_bytes(
                    (hashlib.new(suffix[1:], signature.read_bytes()).hexdigest() + "\n").encode(),
                )
        result = verify_runtime_phase10_maven(
            self.payload, self.manifest, self.sidecars, self.key, sha256_bytes(exported),
        )
        self.assertEqual(len(signatures) * 5, len(result["sidecarFiles"]))
        damaged = signatures[0]
        damaged.write_bytes(damaged.read_bytes().replace(b"A", b"B", 1))
        for suffix in CONTRACT_CHECKSUM_SUFFIXES:
            damaged.with_name(damaged.name + suffix).write_bytes(
                (hashlib.new(suffix[1:], damaged.read_bytes()).hexdigest() + "\n").encode(),
            )
        with self.assertRaisesRegex(ValueError, "PGP verification failed"):
            verify_runtime_phase10_maven(
                self.payload, self.manifest, self.sidecars, self.key, sha256_bytes(exported),
            )


if __name__ == "__main__":
    unittest.main()
