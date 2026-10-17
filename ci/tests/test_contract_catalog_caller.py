"""Synthetic official originals; this does not establish hosted S1048 authority."""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import unittest
from unittest import mock

from ci.contract_catalog_caller import (
    capture_promotable_contract_originals, sign_promoted_contract_catalog,
)
from ci.products.contract_attestation import build_contract_attestation, capture_contract_execution_closure
from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes
from ci.products.signatures import generate_development_key
from ci.tests.test_contract_ci_originals import ContractOriginalCiCaptureTest, PHASES


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen required")
class ContractCatalogCallerTest(unittest.TestCase):
    api = ContractOriginalCiCaptureTest.api

    def setUp(self):
        ContractOriginalCiCaptureTest.setUp(self)
        closure = self.root / "closure"
        capture_contract_execution_closure(self.payload, self.receipts, self.execution_archive, closure)
        private, public, signing = generate_development_key(self.root / "signer")
        self.private = private
        self.keys = self.root / "keys"
        self.keys.mkdir()
        (self.keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        self.keyring = self.root / "product-signing-keys.json"
        self.keyring.write_bytes(canonical_json_bytes({
            "schemaVersion": 1, "namespace": signing["namespace"],
            "algorithm": signing["algorithm"], "trustDomain": "release",
            "activeKey": {"keyId": signing["keyId"],
                          "fingerprint": signing["fingerprint"]}, "retiredKeys": [],
        }))
        self.handoff = self.root / "handoff"
        build_contract_attestation(self.payload, self.receipts["metadata"],
            {**signing, "trustDomain": "release"}, private, public, self.handoff,
            execution_closure=closure, keyring=self.keyring,
            keys_directory=self.keys, complete_handoff=True)
        self.selection = {}
        for phase in PHASES:
            receipt = load_canonical_json_bytes(self.receipts[phase].read_bytes())
            shard = load_canonical_json_bytes((self.shards[phase] / "phase-object.json").read_bytes())
            self.selection[phase] = {
                "producer": self.producer,
                "workflowPath": ".github/workflows/product-validation.yml",
                "workflowSha": self.pin,
                "jobName": ("product-validation / product-contracts" if phase == "binary"
                            else "product-validation / contract-continuation"),
                "artifactId": self.artifacts[phase]["id"],
                "artifactSha256": self.artifacts[phase]["digest"],
                "buildKey": shard["buildKey"], "receiptSha256": shard["receiptSha256"],
                "objectSha256": shard["objectSha256"],
                "artifactPath": receipt["outputs"][0]["relativePath"],
            }
        self.elected = self.root / "elected"
        self.promoted = self.root / "promoted"

    def _capture(self, selection=None, *, jobs=None):
        def download(artifact, token, destination, *, max_bytes):
            self.assertEqual("not-a-real-token", token)
            raw = self.archives[next(phase for phase in PHASES
                                      if self.artifacts[phase]["id"] == artifact["id"])]
            self.assertLessEqual(len(raw), max_bytes)
            Path(destination).write_bytes(raw)
        with mock.patch("reuse.api_request", side_effect=self.api(jobs=jobs)), \
             mock.patch("ci.product_reuse.download_artifact_to_file", side_effect=download):
            return capture_promotable_contract_originals(
                self.handoff, self.elected, selection=self.selection if selection is None else selection,
                token="not-a-real-token", environ={})

    def _sign(self, digest, selection=None, environ=None):
        producer = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/promote.yml", "event": "push",
            "commit": "a" * 40, "tree": "b" * 40, "pullRequest": None,
            "runId": 81, "runAttempt": 1}
        return sign_promoted_contract_catalog(
            self.handoff, self.elected, self.promoted,
            selection=self.selection if selection is None else selection,
            expected_capture_inventory_sha256=digest,
            repository="codex-agent-labs/codex-agent",
            context={"kind": "promoted-main", "commit": producer["commit"],
                     "tree": producer["tree"], "promotionRunId": 81,
                     "promotionRunAttempt": 1}, producer=producer,
            keyring=self.keyring, keys_directory=self.keys, private_key=self.private,
            environ={} if environ is None else environ)

    def test_four_pinned_official_originals_feed_token_free_catalog(self):
        previous = {phase: self.archives[phase] for phase in PHASES}
        capture = self._capture()
        index = self._sign(capture["inventorySha256"])
        self.assertEqual(4, len(index["entries"]))
        self.assertEqual(previous, {phase: (self.elected / "uploads" / f"{phase}.zip").read_bytes()
                                    for phase in PHASES})
        for phase in PHASES:
            self.assertEqual(self.selection[phase]["objectSha256"],
                sha256_bytes((self.elected / "objects" / f"{phase}.zip").read_bytes()))

    def test_unpinned_original_and_signer_token_fail_closed(self):
        changed = {phase: dict(pin) for phase, pin in self.selection.items()}
        changed["binary"]["artifactSha256"] = sha256_bytes(b"wrong")
        with self.assertRaises(ValueError):
            self._capture(changed)
        self.assertFalse(self.elected.exists())
        capture = self._capture()
        with self.assertRaisesRegex(ValueError, "observation token"):
            self._sign(capture["inventorySha256"], environ={"GITHUB_TOKEN": ""})
        with self.assertRaisesRegex(ValueError, "independent S1048 pin"):
            self._sign(sha256_bytes(b"wrong"))
        self.assertFalse(self.promoted.exists())

    def test_shared_attempt_still_binds_each_phase_to_its_own_job_window(self):
        jobs = [dict(job) for job in self.jobs]
        jobs[0]["completed_at"] = "2026-09-06T10:10:00Z"
        with self.assertRaisesRegex(ValueError, "original job-attempt window"):
            self._capture(jobs=jobs)
        self.assertFalse(self.elected.exists())


if __name__ == "__main__":
    unittest.main()
