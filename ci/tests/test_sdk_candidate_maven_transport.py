"""Offline SDK Maven official-upload custody and token-free forwarding stopgates."""

from __future__ import annotations

import copy
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from ci import sdk_candidate_maven_transport as candidate
from ci.products.inventory import (
    canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file,
)


_COMMIT = "a" * 40
_TREE = "b" * 40
_SHA = "c" * 40
_DIGEST = "sha256:" + "1" * 64


def _selection() -> dict:
    phase11 = {name: _DIGEST for name in candidate._PHASE11 if name.endswith("_sha256")}
    phase11.update(expected_sdk_version="0.8.0", expected_source_commit=_COMMIT,
                   expected_source_tree=_TREE, expected_validation_tree=_TREE)
    return {"schemaVersion": 1,
            "producer": {"repository": candidate._REPOSITORY,
                         "workflowPath": ".github/workflows/ci.yml",
                         "event": "workflow_dispatch", "commit": _COMMIT,
                         "tree": _TREE, "pullRequest": None,
                         "runId": 10, "runAttempt": 1},
            "trustedWorkflowSha": _SHA, "artifactId": 20,
            "artifactSha256": _DIGEST, "artifactSize": 1,
            "signedInventorySha256": _DIGEST, "phase11Pins": phase11}


class SdkCandidateMavenTransportTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "control.json").write_bytes(b"{}\n")
        (self.source / "maven-sidecars").mkdir()
        (self.source / "maven-sidecars/sdk-core.asc").write_bytes(b"signature\n")
        self.archive = self.root / "official.zip"
        with ZipFile(self.archive, "w") as output:
            for path in sorted(self.source.rglob("*")):
                if path.is_file():
                    output.write(path, path.relative_to(self.source).as_posix())
        self.selected = _selection()
        self.selected.update(artifactSha256=sha256_file(self.archive),
                             artifactSize=self.archive.stat().st_size,
                             signedInventorySha256=sha256_bytes(canonical_json_bytes(
                                 regular_file_inventory(self.source))))
        self.selected["phase11Pins"]["expected_signed_inventory_sha256"] = \
            self.selected["signedInventorySha256"]
        self.observed = {"run": {"id": 10, "status": "completed", "conclusion": "success"},
                         "jobs": [{"name": candidate._JOB}]}

    def _capture(self):
        def observe(producers, **kwargs):
            self.assertEqual(producers, {"maven": self.selected["producer"]})
            self.assertEqual(kwargs["jobs_by_phase"], {"maven": candidate._JOB})
            self.assertEqual(kwargs["trusted_workflows_by_phase"], {"maven": {
                "path": candidate._WORKFLOW, "sha": _SHA}})
            self.assertTrue(kwargs["allow_protected_dispatch"])
            return [self.observed]
        def download(artifact_id, digest, name, producer, observed_run, token, *, destination):
            self.assertEqual(artifact_id, 20)
            self.assertEqual(digest, self.selected["artifactSha256"])
            self.assertEqual(name, candidate._name(self.selected))
            self.assertEqual(producer, self.selected["producer"])
            self.assertEqual(observed_run, self.observed["run"])
            self.assertEqual(token, "token")
            shutil.copyfile(self.archive, destination)
            return {"id": 20, "name": name, "digest": digest,
                    "size_in_bytes": self.archive.stat().st_size}, destination
        with patch.object(candidate.transport, "_observe_ci_producer_jobs",
                          side_effect=observe), \
             patch.object(candidate.transport, "_download_contract_ci_upload",
                          side_effect=download), \
             patch.object(candidate.transport, "_require_artifact_job_window") as window:
            result = candidate.capture_sdk_candidate_maven(
                self.selected, self.root / "captured", token="token", environ={})
        window.assert_called_once()
        return result

    def test_selected_official_upload_is_captured_without_admission(self):
        result = self._capture()
        self.assertFalse(result["admitted"])
        self.assertEqual(regular_file_inventory(self.root / "captured/signed"),
                         regular_file_inventory(self.source))
        self.assertEqual(sha256_file(self.root / "captured/official-upload.zip"),
                         self.selected["artifactSha256"])

    def test_selection_and_secret_negatives_fail_before_observation(self):
        selected = copy.deepcopy(self.selected)
        selected["producer"]["event"] = "pull_request"
        selected["producer"]["pullRequest"] = 31
        with self.assertRaisesRegex(ValueError, "protected dispatch"):
            candidate._selection(selected)
        selected = copy.deepcopy(self.selected)
        selected["phase11Pins"]["expected_signed_inventory_sha256"] = _DIGEST
        with self.assertRaisesRegex(ValueError, "identities disagree"):
            candidate._selection(selected)
        with patch.object(candidate.transport, "_observe_ci_producer_jobs") as observe, \
             self.assertRaisesRegex(ValueError, "signing secrets"):
            candidate.capture_sdk_candidate_maven(
                self.selected, self.root / "blocked", token="token",
                environ={"SIGNING_IN_MEMORY_KEY": ""})
        observe.assert_not_called()

    def test_forwarder_requires_identical_official_bytes_and_no_token(self):
        self._capture()
        landed = self.root / "landed"
        landed.mkdir()
        def forward(source, destination, **kwargs):
            self.assertEqual(source, self.root / "captured/signed")
            self.assertEqual(kwargs["landed_repository"], landed)
            self.assertEqual(kwargs["expected_signed_inventory_sha256"],
                             self.selected["signedInventorySha256"])
            shutil.copytree(source, destination)
            return {"product": "sdk", "sdkVersion": "0.8.0"}
        with patch.object(candidate, "forward_verified_sdk_phase10_maven",
                          side_effect=forward) as forwarded:
            result = candidate.forward_sdk_candidate_maven(
                self.root / "captured", landed, self.root / "forwarded", self.selected,
                expected_capture_inventory_sha256=sha256_bytes(canonical_json_bytes(
                    regular_file_inventory(self.root / "captured"))))
        forwarded.assert_called_once()
        self.assertFalse(result["admitted"])
        self.assertEqual(regular_file_inventory(self.root / "forwarded"),
                         regular_file_inventory(self.source))
        with patch.dict(os.environ, {"GITHUB_TOKEN": ""}), \
             self.assertRaisesRegex(ValueError, "token or signing secret"):
            candidate.forward_sdk_candidate_maven(
                self.root / "captured", landed, self.root / "blocked", self.selected,
                expected_capture_inventory_sha256=sha256_bytes(canonical_json_bytes(
                    regular_file_inventory(self.root / "captured"))))

    def test_tampered_capture_or_late_change_cannot_publish(self):
        self._capture()
        landed = self.root / "landed"
        landed.mkdir()
        expected = sha256_bytes(canonical_json_bytes(regular_file_inventory(
            self.root / "captured")))
        (self.root / "captured/signed/control.json").write_bytes(b"changed\n")
        with self.assertRaisesRegex(ValueError, "S1048 approved inventory"):
            candidate.forward_sdk_candidate_maven(
                self.root / "captured", landed, self.root / "bad", self.selected,
                expected_capture_inventory_sha256=expected)
        self.assertFalse((self.root / "bad").exists())
        (self.root / "captured/signed/control.json").write_bytes(b"{}\n")
        expected = sha256_bytes(canonical_json_bytes(regular_file_inventory(
            self.root / "captured")))
        def mutate(source, destination, **_kwargs):
            shutil.copytree(source, destination)
            (self.root / "captured/signed/control.json").write_bytes(b"late\n")
            return {"product": "sdk"}
        with patch.object(candidate, "forward_verified_sdk_phase10_maven",
                          side_effect=mutate), \
             self.assertRaisesRegex(ValueError, "changed before exact-byte forwarding"):
            candidate.forward_sdk_candidate_maven(
                self.root / "captured", landed, self.root / "late", self.selected,
                expected_capture_inventory_sha256=expected)
        self.assertFalse((self.root / "late").exists())


if __name__ == "__main__":
    unittest.main()
