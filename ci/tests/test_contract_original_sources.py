from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock


from ci.products.contract_attestation import (
    build_contract_attestation,
    capture_contract_execution_closure,
)
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    public_key_fingerprint,
    regular_file_inventory,
    sha256_bytes,
    write_canonical_json,
)
from ci.products.signatures import generate_development_key
from ci.tests import test_contract_ci_originals as base_module
from ci.tests.test_contract_bundle import VERSION
from ci.tests.test_contract_execution_closure import execution_closure_fixture


PHASES = base_module.PHASES
product_reuse = base_module.product_reuse


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ContractOriginalReleaseSourcesTest(unittest.TestCase):
    def setUp(self) -> None:
        base_module.ContractOriginalCiCaptureTest.setUp(self)
        self.private_key, self.public_key, signing = generate_development_key(
            self.root / "release-signer",
        )
        self.signing = {**signing, "trustDomain": "release"}
        self.keys = self.root / "release-keys"
        self.keys.mkdir()
        (self.keys / f"{self.signing['keyId']}.pub").write_bytes(self.public_key.read_bytes())
        self.keyring = self.root / "release-keyring.json"
        write_canonical_json(self.keyring, {
            "schemaVersion": 1,
            "namespace": self.signing["namespace"],
            "algorithm": self.signing["algorithm"],
            "trustDomain": "release",
            "activeKey": {
                "keyId": self.signing["keyId"],
                "fingerprint": public_key_fingerprint(self.public_key.read_bytes()),
            },
            "retiredKeys": [],
        })
        self.private_marker = self.keys / "private-marker.txt"
        self.private_marker.write_bytes(b"caller-private-marker\n")

    def handoff(self, name: str, *, matched_phases=PHASES, release: bool = True) -> Path:
        selected = set(matched_phases)
        payload = self.payload
        execution_archive = self.execution_archive
        source_receipts = self.receipts
        if not selected:
            other = {**self.producer, "runId": 72}
            payload, source_receipts, execution_archive = execution_closure_fixture(
                self.root / f"{name}-source",
                producer=other,
            )
        receipts = {}
        receipt_root = self.root / f"{name}-receipts"
        receipt_root.mkdir()
        for phase in PHASES:
            value = load_canonical_json_bytes(source_receipts[phase].read_bytes())
            if selected and phase not in selected:
                value["producer"] = {**value["producer"], "runId": 72}
            path = receipt_root / f"{phase}.json"
            path.write_bytes(canonical_json_bytes(value))
            receipts[phase] = path
        closure = self.root / f"{name}-closure"
        capture_contract_execution_closure(
            payload,
            receipts,
            execution_archive,
            closure,
        )
        output = self.root / name
        signing = self.signing if release else {**self.signing, "trustDomain": "development"}
        build_contract_attestation(
            payload,
            receipts["metadata"],
            signing,
            self.private_key,
            self.public_key,
            output,
            execution_closure=closure,
            keyring=self.keyring if release else None,
            keys_directory=self.keys if release else None,
            complete_handoff=True,
        )
        return output

    def capture(self, handoffs: tuple[Path, ...], *, keyring=None, keys=None) -> dict:
        return product_reuse.capture_contract_original_ci_phases(
            self.capture_root,
            self.output,
            contract_version=VERSION,
            trusted_workflow_sha=self.pin,
            token="not-a-real-token",
            release_handoffs=handoffs,
            keyring=self.keyring if keyring is None else keyring,
            keys_directory=self.keys if keys is None else keys,
        )

    def test_all_release_receipts_require_no_ci_api_and_preserve_complete_handoff(self) -> None:
        handoff = self.handoff("all-release")
        before_capture = regular_file_inventory(self.capture_root)
        before_handoff = regular_file_inventory(handoff)
        with mock.patch("reuse.api_request", side_effect=AssertionError("CI API used")), \
                mock.patch.dict(os.environ, {"GITHUB_TOKEN": "not-a-real-token"}):
            self.assertEqual(0, product_reuse.main([
                "capture-contract-original-ci",
                "--capture-root", str(self.capture_root),
                "--destination", str(self.output),
                "--contract-version", VERSION,
                "--trusted-workflow-sha", self.pin,
                "--release-handoff", str(handoff),
                "--keyring", str(self.keyring),
                "--keys-directory", str(self.keys),
            ]))
        evidence = load_canonical_json_bytes(
            (self.output / "transport/original-ci-phases.json").read_bytes(),
        )
        self.assertEqual(before_capture, regular_file_inventory(self.capture_root))
        self.assertEqual(before_handoff, regular_file_inventory(handoff))
        self.assertEqual(before_capture, regular_file_inventory(self.output / "contract-input"))
        self.assertEqual(before_handoff, regular_file_inventory(self.output / "release-handoffs/0"))
        self.assertEqual(self.keyring.read_bytes(),
                         (self.output / "release-policy/keyring.json").read_bytes())
        self.assertEqual(
            [f"{self.signing['keyId']}.pub"],
            [record["relativePath"] for record in regular_file_inventory(
                self.output / "release-policy/keys",
            )],
        )
        self.assertEqual(b"caller-private-marker\n", self.private_marker.read_bytes())
        self.assertEqual([], evidence["observed"])
        self.assertEqual({}, evidence["artifacts"])
        self.assertEqual({phase: 0 for phase in PHASES}, evidence["releaseAttestations"])
        self.assertEqual(
            {phase: sha256_bytes(self.receipts[phase].read_bytes()) for phase in PHASES},
            evidence["receiptSha256s"],
        )
        self.assertFalse((self.output / "original-phases").exists())

    def test_release_binary_package_and_ci_validation_metadata_keep_exact_originals(self) -> None:
        handoff = self.handoff("mixed-release", matched_phases=("binary", "package"))
        request = base_module.ContractOriginalCiCaptureTest.api(self)
        with mock.patch("reuse.api_request", side_effect=request) as api:
            evidence = self.capture((handoff,))
        urls = [call.args[0] for call in api.call_args_list]
        self.assertFalse(any(url.endswith("/101") or url.endswith("/101/zip") for url in urls))
        self.assertFalse(any(url.endswith("/102") or url.endswith("/102/zip") for url in urls))
        self.assertEqual(
            {"binary": 0, "package": 0},
            evidence["releaseAttestations"],
        )
        self.assertEqual(
            {phase: self.artifacts[phase] for phase in ("validation", "metadata")},
            evidence["artifacts"],
        )
        before = regular_file_inventory(handoff)
        self.assertEqual(before, regular_file_inventory(self.output / "release-handoffs/0"))
        self.assertEqual(before, regular_file_inventory(handoff))
        for phase in ("validation", "metadata"):
            self.assertEqual(
                self.receipts[phase].read_bytes(),
                (self.output / f"original-phases/{phase}/phase-receipt.json").read_bytes(),
            )
        for phase in ("binary", "package"):
            self.assertFalse((self.output / "original-phases" / phase).exists())

    def test_invalid_release_sources_never_publish_partial_output(self) -> None:
        release = self.handoff("valid-release")
        development = self.handoff("development-handoff", release=False)
        bad_signature = self.root / "tampered-release"
        shutil.copytree(release, bad_signature)
        signature = bad_signature / f"codex-agent-contract-{VERSION}.attestation.sig"
        signature.write_bytes(signature.read_bytes() + b"tampered")
        _, wrong_public, wrong_signing = generate_development_key(self.root / "wrong-key")
        wrong_keys = self.root / "wrong-keys"
        wrong_keys.mkdir()
        (wrong_keys / f"{wrong_signing['keyId']}.pub").write_bytes(wrong_public.read_bytes())
        wrong_keyring = self.root / "wrong-keyring.json"
        write_canonical_json(wrong_keyring, {
            "schemaVersion": 1,
            "namespace": wrong_signing["namespace"],
            "algorithm": wrong_signing["algorithm"],
            "trustDomain": "release",
            "activeKey": {
                "keyId": wrong_signing["keyId"],
                "fingerprint": public_key_fingerprint(wrong_public.read_bytes()),
            },
            "retiredKeys": [],
        })
        unmatched = self.handoff("unmatched-release", matched_phases=())
        partial = self.handoff("partial-release", matched_phases=("binary", "package"))
        cases = (
            ((bad_signature,), self.keyring, self.keys),
            ((development,), self.keyring, self.keys),
            ((release,), wrong_keyring, wrong_keys),
            ((unmatched,), self.keyring, self.keys),
            ((partial,), self.keyring, self.keys),
        )
        inputs = {path: regular_file_inventory(path) for path in {
            bad_signature, development, release, unmatched, partial,
        }}
        capture_before = regular_file_inventory(self.capture_root)
        for handoffs, keyring, keys in cases:
            with self.subTest(handoff=handoffs[0].name), \
                    mock.patch("reuse.api_request", side_effect=ValueError("no original CI evidence")), \
                    self.assertRaises((ValueError, OSError)):
                self.capture(handoffs, keyring=keyring, keys=keys)
            self.assertFalse(self.output.exists())
        self.assertEqual(
            inputs,
            {path: regular_file_inventory(path) for path in inputs},
        )
        self.assertEqual(capture_before, regular_file_inventory(self.capture_root))


if __name__ == "__main__":
    unittest.main()
