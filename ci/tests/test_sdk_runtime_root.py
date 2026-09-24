from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from ci.products.inventory import (
    public_key_fingerprint, sha256_bytes, write_canonical_json,
)
from ci.products.sdk_runtime_root import verify_external_library_authorization
from ci.products.signatures import ALGORITHM, NAMESPACE, generate_development_key
from ci.tests.test_products import sdk_compatibility


class SdkRuntimeRootTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="sdk-runtime-root-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.root_private, self.root_public, _ = generate_development_key(self.root / "root-key")
        self.library = self.root / "runtime-library.bin"
        self.library.write_bytes(b"verified external runtime")
        self.compatibility = sdk_compatibility()
        self.compatibility["sdkVersion"] = "0.8.0"
        self.compatibility["contract"]["version"] = "0.8.0"
        self.compatibility["runtime"]["compatibleReleaseRange"] = ">=0.8.0 <0.9.0"
        self.compatibility["runtime"]["compatibleRuntimeCompatibilityRange"] = ">=0.8.0 <0.9.0"
        self.compatibility["runtime"]["defaultRuntimeVersion"] = "0.8.0"

    @staticmethod
    def _sign(path: Path, private_key: Path, namespace: str, destination: Path) -> None:
        subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n", namespace, str(path)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        Path(f"{path}.sig").replace(destination)

    def evidence(self, name: str, *, runtime_version: str = "0.8.4",
                 abi_version: str = "1.13.0") -> Path:
        signer_private, signer_public, _ = generate_development_key(self.root / f"signer-{name}")
        evidence = self.root / f"evidence-{name}"
        keys = evidence / "keys"
        keys.mkdir(parents=True)
        signer_bytes = signer_public.read_bytes()
        (keys / f"{name}.pub").write_bytes(signer_bytes)
        fingerprint = public_key_fingerprint(signer_bytes)
        keyring = {
            "schemaVersion": 1, "namespace": NAMESPACE, "algorithm": ALGORITHM,
            "trustDomain": "release", "activeKey": {"keyId": name, "fingerprint": fingerprint},
            "retiredKeys": [],
        }
        keyring_path = evidence / "release-keyring.json"
        write_canonical_json(keyring_path, keyring)
        delegation_path = evidence / "root-delegation.json"
        write_canonical_json(delegation_path, {
            "schemaVersion": 1, "kind": "sdk-runtime-release-keyring-delegation",
            "scope": "desktop-runtime-library",
            "rootFingerprint": public_key_fingerprint(self.root_public.read_bytes()),
            "keyringSha256": sha256_bytes(keyring_path.read_bytes()),
        })
        self._sign(delegation_path, self.root_private, "codex-agent-sdk-runtime-root-v1",
                   evidence / "root-delegation.sig")
        claim_path = evidence / "runtime-library-authorization.json"
        write_canonical_json(claim_path, {
            "schemaVersion": 1, "kind": "desktop-runtime-library-authorization",
            "runtimeVersion": runtime_version,
            "runtimeIdentity": {
                "schemaVersion": 1, "componentId": sha256_bytes(b"component"),
                "runtimeCompatibilityVersion": "0.8.0",
                "contractDigest": self.compatibility["contract"]["digest"],
                "contractComponentDigest": sha256_bytes(b"component-contract"),
                "cAbiVersion": abi_version, "target": "macos-arm64",
                "appServerVersion": "0.149.0", "buildInputDigest": sha256_bytes(b"input"),
            },
            "runtimeLibrarySha256": sha256_bytes(self.library.read_bytes()),
            "variantBundleSha256": sha256_bytes(b"variant"),
            "variantManifestSha256": sha256_bytes(b"variant-manifest"),
            "aggregateManifestSha256": sha256_bytes(b"aggregate"),
            "variantAttestationSha256": sha256_bytes(b"variant-attestation"),
            "aggregateAttestationSha256": sha256_bytes(b"aggregate-attestation"),
            "signing": {
                "algorithm": ALGORITHM, "namespace": NAMESPACE, "trustDomain": "release",
                "keyId": name, "fingerprint": fingerprint,
            },
        })
        self._sign(claim_path, signer_private, NAMESPACE,
                   evidence / "runtime-library-authorization.sig")
        return evidence

    def verify(self, evidence: Path, *, root_key: bytes | None = None) -> dict:
        return verify_external_library_authorization(
            evidence,
            sdk_pinned_root_public_key=self.root_public.read_bytes() if root_key is None else root_key,
            sdk_compatibility=self.compatibility,
            target="macos-arm64",
            library_snapshot=self.library,
        )

    def test_root_approved_signer_rotation_preserves_sdk_and_library_bytes(self) -> None:
        first = self.evidence("release-a")
        second = self.evidence("release-b")
        self.assertEqual(self.verify(first)["runtimeLibrarySha256"],
                         self.verify(second)["runtimeLibrarySha256"])
        self.assertNotEqual((first / "release-keyring.json").read_bytes(),
                            (second / "release-keyring.json").read_bytes())

    def test_unapproved_bytes_fail_before_the_library_can_be_loaded(self) -> None:
        evidence = self.evidence("release-a")
        for relative in (
            "root-delegation.json", "root-delegation.sig", "release-keyring.json",
            "runtime-library-authorization.json", "runtime-library-authorization.sig",
            "keys/release-a.pub",
        ):
            path = evidence / relative
            original = path.read_bytes()
            path.write_bytes(original + b"x")
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                self.verify(evidence)
            path.write_bytes(original)
        original = self.library.read_bytes()
        self.library.write_bytes(original + b"x")
        with self.assertRaisesRegex(ValueError, "signed authorization"):
            self.verify(evidence)
        self.library.write_bytes(original)
        (evidence / "extra").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "extra or missing"):
            self.verify(evidence)

    def test_self_supplied_root_and_out_of_range_release_fail(self) -> None:
        evidence = self.evidence("release-a")
        _, wrong_public, _ = generate_development_key(self.root / "wrong-root")
        with self.assertRaisesRegex(ValueError, "SDK-pinned root"):
            self.verify(evidence, root_key=wrong_public.read_bytes())
        out_of_range = self.evidence("release-b", runtime_version="0.9.0")
        with self.assertRaisesRegex(ValueError, "incompatible"):
            self.verify(out_of_range)
        overflow_abi = self.evidence("release-c", abi_version="1.256.0")
        with self.assertRaisesRegex(ValueError, "encoded field widths"):
            self.verify(overflow_abi)
