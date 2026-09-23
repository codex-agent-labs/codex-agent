"""SDK Maven release-sidecar checks use synthetic package stages, not host proof."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import (
    canonical_json_bytes, regular_file_inventory, sha256_bytes,
    snapshot_regular_tree as actual_snapshot_regular_tree,
)
from ci.products.receipt import compute_build_key, write_output_manifest, write_phase_receipt
from ci.products.sdk_maven import CHECKSUMS, MAVEN_GROUPS, package_sdk_maven
from ci.products.sdk_phase10_maven import (
    produce_sdk_phase10_maven_sidecars, verify_sdk_phase10_maven,
)
from ci.tests.test_product_sdk_maven import _repository
from ci.tests.test_products import phase_receipt, sdk_compatibility


_FINGERPRINT = "A" * 40


class SdkPhase10MavenTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-sidecar-", dir="/private/tmp")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.stage = root / "stage"
        compatibility = self.stage / "outputs/evidence/sdk-compatibility.json"
        compatibility.parent.mkdir(parents=True)
        compatibility.write_bytes(canonical_json_bytes(sdk_compatibility()))
        source = _repository(root, "sdk-android", "0.2.0")
        package_sdk_maven(source, self.stage / "outputs/maven", compatibility,
                          MAVEN_GROUPS["sdk-android"], "0.2.0", "sdk-android")
        manifest = write_output_manifest(self.stage, "sdk", "sdk-android", "package",
                                         "android", "0.2.0",
                                         {"maven": "outputs/maven", "evidence": "outputs/evidence"})
        fixture = phase_receipt()
        inputs = fixture["inputs"]
        inputs["versionIdentity"] = "0.2.0"
        receipt_root = root / "receipt"
        receipt_root.mkdir()
        write_phase_receipt(
            self.stage, receipt_root, "sdk", "sdk-android", "package", "android", "0.2.0",
            compute_build_key(product="sdk", component="sdk-android", phase="package",
                              target="android", inputs=inputs),
            inputs, fixture["producer"], "development",
        )
        self.receipt = root / "phase-receipt.json"
        self.receipt.write_bytes((receipt_root / "phase-receipt.json").read_bytes())
        self.sidecars = root / "sidecars"
        self.sidecars.mkdir()
        primaries = [record["relativePath"] for record in regular_file_inventory(
                         self.stage / "outputs/maven")
                     if not record["relativePath"].endswith(tuple(CHECKSUMS))]
        for path in primaries:
            signature = self.sidecars / (path + ".asc")
            signature.parent.mkdir(parents=True, exist_ok=True)
            signature.write_bytes(b"synthetic signature\n")
            for suffix, algorithm in CHECKSUMS.items():
                signature.with_name(signature.name + suffix).write_bytes(
                    (hashlib.new(algorithm, signature.read_bytes()).hexdigest() + "\n").encode(),
                )
        self.key = root / "public.asc"
        self.key.write_bytes(b"synthetic PGP key\n")

    def _verify(self):
        with patch("ci.products.sdk_phase10_maven._run_gpg", side_effect=lambda *args:
                   f"pub:::::::::\nfpr:::::::::{_FINGERPRINT}:\n" if "--list-keys" in args else "") as gpg:
            result = verify_sdk_phase10_maven(
                self.stage, self.receipt, self.sidecars, self.key, sha256_bytes(self.key.read_bytes()),
            )
        return result, gpg

    def test_exact_package_stage_and_all_external_sidecars(self):
        result, gpg = self._verify()
        self.assertEqual("sdk-android", result["component"])
        self.assertEqual("0.2.0", result["sdkVersion"])
        self.assertEqual(5 * sum("--verify" in call.args for call in gpg.call_args_list),
                         len(result["sidecarFiles"]))

    def test_extra_signature_and_stale_primary_fail_closed(self):
        (self.sidecars / "orphan.asc").write_bytes(b"orphan")
        with self.assertRaisesRegex(ValueError, "sidecar inventory"):
            self._verify()
        (self.sidecars / "orphan.asc").unlink()
        primary = next((self.stage / "outputs/maven").rglob("*.aar"))
        primary.write_bytes(b"changed primary")
        with self.assertRaises(ValueError):
            self._verify()

    def test_snapshot_substitution_fails_before_gpg(self):
        def substitute(source, destination):
            actual_snapshot_regular_tree(source, destination)
            if Path(source) == self.stage:
                primary = next((Path(destination) / "outputs/maven").rglob("*.aar"))
                primary.write_bytes(b"substituted")
        with patch("ci.products.sdk_phase10_maven.snapshot_regular_tree", side_effect=substitute), \
                patch("ci.products.sdk_phase10_maven._run_gpg") as gpg:
            with self.assertRaisesRegex(ValueError, "snapshot differs"):
                verify_sdk_phase10_maven(
                    self.stage, self.receipt, self.sidecars, self.key,
                    sha256_bytes(self.key.read_bytes()),
                )
            gpg.assert_not_called()

    def test_signing_never_starts_for_invalid_package_or_replaces_output(self):
        output = self.sidecars.with_name("new-sidecars")
        checksum = next((self.stage / "outputs/maven").rglob("*.aar.sha256"))
        checksum.write_bytes(b"0" * 64 + b"\n")
        with patch("ci.products.sdk_phase10_maven._run_gpg") as gpg:
            with self.assertRaises(ValueError):
                produce_sdk_phase10_maven_sidecars(
                    self.stage, self.receipt, output, self.key, sha256_bytes(self.key.read_bytes()),
                    self.stage.parent, _FINGERPRINT, "",
                )
            gpg.assert_not_called()
        self.assertFalse(output.exists())
        output.mkdir()
        with self.assertRaisesRegex(ValueError, "already exists"):
            produce_sdk_phase10_maven_sidecars(
                self.stage, self.receipt, output, self.key, sha256_bytes(self.key.read_bytes()),
                self.stage.parent, _FINGERPRINT, "",
            )

    def test_cli_help_needs_no_pythonpath(self):
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        executed = subprocess.run(
            [sys.executable, "-B", "-m", "ci.products.sdk_phase10_maven", "--help"],
            cwd=Path(__file__).resolve().parents[2], env=environment,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, executed.returncode, executed.stderr)
        self.assertIn("--signing-fingerprint", executed.stdout)

    @unittest.skipUnless(shutil.which("gpg"), "GnuPG unavailable")
    def test_real_ephemeral_gpg_round_trip_and_signature_negative(self):
        home = self.stage.parent / "gnupg"
        home.mkdir(mode=0o700)
        command = ["gpg", "--homedir", str(home), "--batch", "--no-tty",
                   "--pinentry-mode", "loopback", "--passphrase", ""]
        generated = subprocess.run(
            [*command, "--quick-generate-key", "SDK Fixture <sdk@example.test>",
             "ed25519", "sign", "0"], capture_output=True, timeout=60,
        )
        self.assertEqual(0, generated.returncode, generated.stderr.decode())
        key = subprocess.run([*command, "--armor", "--export", "sdk@example.test"],
                             check=True, capture_output=True, timeout=60).stdout
        self.key.write_bytes(key)
        listing = subprocess.run([*command, "--with-colons", "--fingerprint", "--list-secret-keys"],
                                 check=True, capture_output=True, timeout=60).stdout.decode()
        fingerprint = next(line.split(":")[9] for line in listing.splitlines()
                           if line.startswith("fpr:"))
        before = regular_file_inventory(self.stage)
        output = self.sidecars.with_name("signed")
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        executed = subprocess.run(
            [sys.executable, "-B", "-m", "ci.products.sdk_phase10_maven",
             "--stage", str(self.stage), "--receipt", str(self.receipt),
             "--sidecars", str(output), "--pgp-public-key", str(self.key),
             "--pgp-public-key-sha256", sha256_bytes(key),
             "--signing-home", str(home), "--signing-fingerprint", fingerprint],
            cwd=Path(__file__).resolve().parents[2], env=environment,
            input="", capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(0, executed.returncode, executed.stderr)
        result = json.loads(executed.stdout)
        self.assertEqual(before, regular_file_inventory(self.stage))
        self.assertEqual(fingerprint, result["pgpPublicKey"]["fingerprint"])
        self.assertEqual(result["sidecarFiles"], verify_sdk_phase10_maven(
            self.stage, self.receipt, output, self.key, sha256_bytes(key),
        )["sidecarFiles"])
        signature = next(output.rglob("*.asc"))
        signature.write_bytes(signature.read_bytes().replace(b"A", b"B", 1))
        for suffix, algorithm in CHECKSUMS.items():
            signature.with_name(signature.name + suffix).write_bytes(
                (hashlib.new(algorithm, signature.read_bytes()).hexdigest() + "\n").encode(),
            )
        with self.assertRaisesRegex(ValueError, "PGP operation failed"):
            verify_sdk_phase10_maven(
                self.stage, self.receipt, output, self.key, sha256_bytes(key),
            )


if __name__ == "__main__":
    unittest.main()
