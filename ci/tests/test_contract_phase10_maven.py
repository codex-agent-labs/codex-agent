"""Local Contract Maven PGP evidence; not protected-run acceptance."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from ci.products.contract_model import CONTRACT_CHECKSUM_SUFFIXES, verify_contract_bundle
from ci.products.contract_phase10_maven import (
    produce_contract_phase10_maven_sidecars, verify_contract_phase10_maven,
)
from ci.products.inventory import sha256_bytes
from ci.tests.test_contract_attestation import VERSION, _payload


class ContractPhase10MavenTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="ct-p10-", dir="/private/tmp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.payload = self.root / f"codex-agent-contract-{VERSION}.zip"
        _payload(self.payload)
        self.sidecars = self.root / "sidecars"
        self.key = self.root / "public.asc"

    def test_invalid_payload_cannot_reach_signer_or_publish(self) -> None:
        self.payload.write_bytes(b"not a verified Contract payload\n")
        self.key.write_bytes(b"fixture public key\n")
        with mock.patch("ci.products.contract_phase10_maven.subprocess.run") as signer:
            with self.assertRaises(ValueError):
                produce_contract_phase10_maven_sidecars(
                    self.payload, self.sidecars, self.key, sha256_bytes(self.key.read_bytes()),
                    self.root, "A" * 40, "",
                )
            signer.assert_not_called()
        self.assertFalse(self.sidecars.exists())

    @unittest.skipUnless(shutil.which("gpg"), "GnuPG is required")
    def test_real_gpg_external_sidecars_and_tamper_rejection(self) -> None:
        home = self.root / "gnupg"
        home.mkdir(mode=0o700)
        command = ["gpg", "--homedir", str(home), "--batch", "--no-tty",
                   "--pinentry-mode", "loopback", "--passphrase", ""]
        generated = subprocess.run(
            [*command, "--quick-generate-key", "Contract Fixture <contract@example.test>",
             "ed25519", "sign", "0"], capture_output=True, timeout=60,
        )
        self.assertEqual(0, generated.returncode, generated.stderr.decode())
        self.key.write_bytes(subprocess.run(
            [*command, "--armor", "--export", "contract@example.test"],
            check=True, capture_output=True, timeout=60,
        ).stdout)
        listing = subprocess.run(
            [*command, "--with-colons", "--fingerprint", "--list-secret-keys"],
            check=True, capture_output=True, timeout=60,
        ).stdout.decode()
        fingerprint = next(line.split(":")[9] for line in listing.splitlines()
                           if line.startswith("fpr:"))
        run = subprocess.run
        with mock.patch("ci.products.contract_phase10_maven.subprocess.run", wraps=run) as commands:
            with self.assertRaisesRegex(ValueError, "signer differs from pinned PGP key"):
                produce_contract_phase10_maven_sidecars(
                    self.payload, self.sidecars, self.key, sha256_bytes(self.key.read_bytes()),
                    home, "B" * 40, "",
                )
            self.assertFalse(any("--detach-sign" in call.args[0] for call in commands.call_args_list))
        self.assertFalse(self.sidecars.exists())
        original = self.payload.read_bytes()
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        invoked = subprocess.run(
            [sys.executable, "-B", "-m", "ci.products.contract_phase10_maven",
             "--payload", str(self.payload), "--sidecars", str(self.sidecars),
             "--pgp-public-key", str(self.key),
             "--pgp-public-key-sha256", sha256_bytes(self.key.read_bytes()),
             "--signing-home", str(home), "--signing-fingerprint", fingerprint],
            cwd=Path(__file__).resolve().parents[2], env=environment,
            input="", capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(0, invoked.returncode, invoked.stderr)
        result = json.loads(invoked.stdout)
        self.assertEqual(original, self.payload.read_bytes())
        self.assertEqual("contract", result["product"])
        self.assertEqual(fingerprint, result["pgpPublicKey"]["fingerprint"])
        manifest = verify_contract_bundle(self.payload)
        primaries = sum(record["role"] != "checksum" for record in manifest["mavenFiles"])
        self.assertEqual(5 * primaries, len(result["sidecarFiles"]))
        self.assertEqual(result, verify_contract_phase10_maven(
            self.payload, self.sidecars, self.key, sha256_bytes(self.key.read_bytes())))
        with self.assertRaisesRegex(ValueError, "already exists"):
            produce_contract_phase10_maven_sidecars(
                self.payload, self.sidecars, self.key, sha256_bytes(self.key.read_bytes()),
                home, fingerprint, "",
            )
        damaged = next(self.sidecars.rglob("*.asc"))
        damaged.write_bytes(damaged.read_bytes().replace(b"A", b"B", 1))
        for suffix in CONTRACT_CHECKSUM_SUFFIXES:
            damaged.with_name(damaged.name + suffix).write_bytes(
                (hashlib.new(suffix[1:], damaged.read_bytes()).hexdigest() + "\n").encode("ascii"),
            )
        with self.assertRaisesRegex(ValueError, "PGP verification failed"):
            verify_contract_phase10_maven(
                self.payload, self.sidecars, self.key, sha256_bytes(self.key.read_bytes()),
            )


if __name__ == "__main__":
    unittest.main()
