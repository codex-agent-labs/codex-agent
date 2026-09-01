from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock
import zipfile

import ci.products.contract as contract_product
import ci.products.contract_model as contract_model
from ci.products.contract import build_contract_bundle
from ci.products.contract_model import verify_extracted_contract_directory
from ci.products.inventory import sha256_bytes, write_canonical_json
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.test_contract_bundle import ARCHIVE_NAME, PRODUCER, VERSION, _write_staging


class ExtractedContractDirectoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("ssh-keygen") is None:
            raise unittest.SkipTest("ssh-keygen is required for Contract directory tests")
        cls._temporary = tempfile.TemporaryDirectory(prefix="contract-directory-")
        root = Path(cls._temporary.name).resolve()
        cls.private_key, cls.public_key, cls.signing = generate_development_key(root / "key")
        staging = root / "staging"
        _write_staging(staging)
        archive = root / ARCHIVE_NAME
        build_contract_bundle(
            staging,
            archive,
            VERSION,
            PRODUCER,
            cls.private_key,
            cls.public_key,
            cls.signing,
        )
        cls.extracted = root / "extracted"
        with zipfile.ZipFile(archive) as source:
            source.extractall(cls.extracted)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary.cleanup()

    def test_exact_directory_and_runtime_cli_verify(self) -> None:
        with mock.patch.object(
            contract_model,
            "snapshot_regular_tree",
            wraps=contract_model.snapshot_regular_tree,
        ) as snapshot:
            manifest = verify_extracted_contract_directory(
                self.extracted,
                self.public_key,
                expected_trust_domain="development",
                expected_contract_version=VERSION,
                required_components=("common", "macos-arm64"),
            )
        snapshot.assert_called_once()
        self.assertNotEqual(self.extracted, snapshot.call_args.args[1])
        self.assertEqual(VERSION, manifest["contractVersion"])
        self.assertEqual(
            0,
            contract_product.main([
                "verify-directory",
                "--directory", str(self.extracted),
                "--public-key", str(self.public_key),
                "--expected-trust-domain", "development",
                "--expected-contract-version", VERSION,
                "--required-component", "common",
                "--required-component", "macos-arm64",
            ]),
        )
        with self.assertRaisesRegex(ValueError, "expected Contract version"):
            verify_extracted_contract_directory(
                self.extracted,
                self.public_key,
                expected_trust_domain="development",
                expected_contract_version="0.2.1",
            )
        with self.assertRaisesRegex(ValueError, "unsupported component"):
            verify_extracted_contract_directory(
                self.extracted,
                self.public_key,
                expected_trust_domain="development",
                required_components=("not-a-contract-component",),
            )
        with self.assertRaisesRegex(ValueError, "requires a keyring"):
            verify_extracted_contract_directory(
                self.extracted,
                self.public_key,
                expected_trust_domain="release",
            )
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as release_cli:
            contract_product.main([
                "verify-directory",
                "--directory", str(self.extracted),
                "--public-key", str(self.public_key),
                "--expected-trust-domain", "release",
            ])
        self.assertEqual(2, release_cli.exception.code)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as development_cli:
            contract_product.main([
                "verify-directory",
                "--directory", str(self.extracted),
                "--public-key", str(self.public_key),
                "--expected-trust-domain", "development",
                "--keyring", str(self.extracted / "contract-manifest.json"),
                "--keys-directory", str(self.extracted),
            ])
        self.assertEqual(2, development_cli.exception.code)
        with self.assertRaisesRegex(ValueError, "development or release"):
            verify_extracted_contract_directory(
                self.extracted,
                self.public_key,
                expected_trust_domain="other",
            )

    def test_runtime_cli_prints_the_fully_verified_canonical_projection(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                0,
                contract_product.main([
                    "verify-directory",
                    "--directory", str(self.extracted),
                    "--public-key", str(self.public_key),
                    "--expected-trust-domain", "development",
                    "--expected-contract-version", VERSION,
                    "--required-component", "common",
                    "--required-component", "macos-arm64",
                    "--print-canonical-api",
                ]),
            )
        projection = json.loads(output.getvalue())
        self.assertEqual(1, projection["schemaVersion"])
        self.assertEqual(556, len(projection["memberKeys"]))
        self.assertEqual(sorted(projection["memberKeys"]), projection["memberKeys"])
        self.assertEqual({"native", "wasm", "jvm-classes"}, set(projection["targetSha256"]))
        self.assertEqual(output.getvalue(), output.getvalue().strip() + "\n")

    def test_runtime_projection_uses_the_verified_snapshot_when_the_source_changes(self) -> None:
        source = self.extracted / "evidence/canonical-api.json"
        original = source.read_bytes()
        expected_digest = sha256_bytes(original).removeprefix("sha256:")
        verify_tree = contract_model._verify_contract_tree

        def mutate_source_after_verification(*args, **kwargs):
            manifest = verify_tree(*args, **kwargs)
            source.write_bytes(original + b" ")
            return manifest

        output = io.StringIO()
        try:
            with mock.patch.object(
                contract_model,
                "_verify_contract_tree",
                side_effect=mutate_source_after_verification,
            ), redirect_stdout(output):
                self.assertEqual(
                    0,
                    contract_product.main([
                        "verify-directory",
                        "--directory", str(self.extracted),
                        "--public-key", str(self.public_key),
                        "--expected-trust-domain", "development",
                        "--expected-contract-version", VERSION,
                        "--required-component", "common",
                        "--required-component", "macos-arm64",
                        "--print-canonical-api",
                    ]),
                )
        finally:
            source.write_bytes(original)

        self.assertEqual(expected_digest, json.loads(output.getvalue())["canonical"]["apiReportSha256"])

    def test_runtime_cli_publishes_the_exact_verified_snapshot(self) -> None:
        source = self.extracted / "evidence/canonical-api.json"
        original = source.read_bytes()
        with tempfile.TemporaryDirectory(prefix="verified-contract-output-") as temporary:
            output = Path(temporary) / "verified"
            verify_tree = contract_model._verify_contract_tree

            def mutate_source_after_verification(*args, **kwargs):
                manifest = verify_tree(*args, **kwargs)
                source.write_bytes(original + b" ")
                return manifest

            try:
                with mock.patch.object(
                    contract_model,
                    "_verify_contract_tree",
                    side_effect=mutate_source_after_verification,
                ):
                    self.assertEqual(0, contract_product.main([
                        "verify-directory",
                        "--directory", str(self.extracted),
                        "--public-key", str(self.public_key),
                        "--expected-trust-domain", "development",
                        "--expected-contract-version", VERSION,
                        "--required-component", "common",
                        "--required-component", "macos-arm64",
                        "--output-directory", str(output),
                    ]))
            finally:
                source.write_bytes(original)

            self.assertEqual(original, (output / "evidence/canonical-api.json").read_bytes())
            with self.assertRaisesRegex(ValueError, "must not exist"):
                verify_extracted_contract_directory(
                    self.extracted,
                    self.public_key,
                    expected_trust_domain="development",
                    output_directory=output,
                )
            self.assertEqual(0, contract_product.main([
                "verify-directory",
                "--directory", str(self.extracted),
                "--public-key", str(self.public_key),
                "--expected-trust-domain", "development",
                "--output-directory", str(output),
                "--reuse-output-directory",
            ]))
            (output / "evidence/canonical-api.json").write_bytes(original + b" ")
            with self.assertRaisesRegex(ValueError, "differs from the authenticated snapshot"):
                verify_extracted_contract_directory(
                    self.extracted,
                    self.public_key,
                    expected_trust_domain="development",
                    output_directory=output,
                    reuse_output_directory=True,
                )

    def test_complete_tree_canonical_signature_and_maven_mutations_fail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="contract-directory-mutations-") as temporary:
            root = Path(temporary).resolve() / "tree"
            shutil.copytree(self.extracted, root)

            extra = root / "evidence/extra.json"
            extra.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "complete allow-list"):
                self._verify(root)
            extra.unlink()

            empty = root / "unexpected-empty-directory"
            empty.mkdir()
            with self.assertRaisesRegex(ValueError, "directory set"):
                self._verify(root)
            empty.rmdir()

            maven = next(path for path in sorted((root / "maven").rglob("*")) if path.is_file())
            original = maven.read_bytes()
            maven.unlink()
            with self.assertRaisesRegex(ValueError, "missing declared"):
                self._verify(root)
            maven.write_bytes(original)

            maven.write_bytes(original + b"changed")
            with self.assertRaisesRegex(ValueError, "declared bytes or digest"):
                self._verify(root)
            maven.write_bytes(original)

            manifest_path = root / "contract-manifest.json"
            canonical = manifest_path.read_bytes()
            manifest_path.write_bytes(canonical.rstrip(b"\n"))
            with self.assertRaisesRegex(ValueError, "canonical"):
                self._verify(root)
            manifest_path.write_bytes(canonical)

            signature = root / "contract-manifest.sig"
            signed = signature.read_bytes()
            signature.write_bytes(signed[:-2] + b"A\n")
            with self.assertRaises(ValueError):
                self._verify(root)
            signature.write_bytes(signed)

            outside = Path(temporary) / "maven-primary"
            outside.write_bytes(original)
            maven.unlink()
            maven.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "unsafe entry"):
                self._verify(root)

    def test_resigned_stale_evidence_identity_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="contract-directory-evidence-") as temporary:
            root = Path(temporary).resolve() / "tree"
            shutil.copytree(self.extracted, root)
            evidence = root / "evidence/canonical-api.json"
            value = json.loads(evidence.read_bytes())
            value["owners"][0]["capabilities"][0] += "-stale"
            write_canonical_json(evidence, value)
            manifest_path = root / "contract-manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            record = next(item for item in manifest["evidenceFiles"] if item["path"] == "evidence/canonical-api.json")
            contents = evidence.read_bytes()
            record["bytes"] = len(contents)
            record["sha256"] = sha256_bytes(contents)
            write_canonical_json(manifest_path, manifest)
            (root / "contract-manifest.sig").unlink()
            sign_manifest(manifest_path, self.private_key, self.signing)
            with self.assertRaises(ValueError):
                self._verify(root)

    def test_release_directory_requires_an_allowed_tracked_key(self) -> None:
        with tempfile.TemporaryDirectory(prefix="contract-directory-release-") as temporary:
            base = Path(temporary).resolve()
            root = base / "tree"
            shutil.copytree(self.extracted, root)
            release_signing = {**self.signing, "trustDomain": "release"}
            manifest_path = root / "contract-manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            manifest["signing"] = release_signing
            write_canonical_json(manifest_path, manifest)
            (root / "contract-manifest.sig").unlink()
            sign_manifest(manifest_path, self.private_key, release_signing)

            keys = base / "keys"
            keys.mkdir()
            tracked_key = keys / f"{release_signing['keyId']}.pub"
            shutil.copyfile(self.public_key, tracked_key)
            keyring = base / "keyring.json"
            write_canonical_json(keyring, {
                "schemaVersion": 1,
                "namespace": release_signing["namespace"],
                "algorithm": release_signing["algorithm"],
                "trustDomain": "release",
                "activeKey": None,
                "retiredKeys": [{
                    "keyId": release_signing["keyId"],
                    "fingerprint": release_signing["fingerprint"],
                }],
            })
            verified = verify_extracted_contract_directory(
                root,
                self.public_key,
                expected_trust_domain="release",
                expected_contract_version=VERSION,
                required_components=("common",),
                keyring=keyring,
                keys_directory=keys,
            )
            self.assertEqual("release", verified["signing"]["trustDomain"])

            write_canonical_json(keyring, {
                "schemaVersion": 1,
                "namespace": release_signing["namespace"],
                "algorithm": release_signing["algorithm"],
                "trustDomain": "release",
                "activeKey": None,
                "retiredKeys": [],
            })
            with self.assertRaisesRegex(ValueError, "allowed release key"):
                verify_extracted_contract_directory(
                    root,
                    self.public_key,
                    expected_trust_domain="release",
                    keyring=keyring,
                    keys_directory=keys,
                )

    def _verify(self, root: Path) -> dict:
        return verify_extracted_contract_directory(
            root,
            self.public_key,
            expected_trust_domain="development",
        )


if __name__ == "__main__":
    unittest.main()
