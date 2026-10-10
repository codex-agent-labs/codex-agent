"""Local official-upload fixtures; no GitHub request or product build."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from ci import runtime_phase10_sidecar_upload as capture
from products.inventory import regular_file_inventory, sha256_file


class RuntimePhase10SidecarUploadTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="rt-sidecar-upload-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.plan = self.repository / "impact-plan.json"
        self.plan.write_bytes(b"original plan\n")
        self.destination = self.root / "capture"
        self.plan_zip = self.root / "plan.zip"
        self.sidecar_zip = self.root / "sidecars.zip"
        with ZipFile(self.plan_zip, "w", ZIP_DEFLATED) as archive:
            archive.writestr("impact-plan.json", self.plan.read_bytes())
        with ZipFile(self.sidecar_zip, "w", ZIP_DEFLATED) as archive:
            archive.writestr("maven/runtime.asc", b"original signature\n")
        self.plan_digest = sha256_file(self.plan_zip)
        self.sidecar_digest = sha256_file(self.sidecar_zip)
        self.producer = {
            "repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 41, "runAttempt": 2, "pullRequest": 31,
        }
        self.artifact = {
            "id": 17, "name": "codex-agent-runtime-phase10-maven-" + "b" * 40 + "-attempt-2",
            "digest": self.sidecar_digest, "size_in_bytes": self.sidecar_zip.stat().st_size,
            "expired": False, "workflow_run": {"id": 41, "head_sha": "a" * 40},
            "created_at": "2026-09-27T12:00:00Z",
        }

    def invoke(self, *, change_plan=False, change_sidecar=False, token_secret=False,
               listed_artifact=None):
        routes = []

        def download(artifact_id, digest, name, producer, run, token, *, destination):
            self.assertEqual(self.producer, producer)
            archive = self.plan_zip if artifact_id == 16 else self.sidecar_zip
            if artifact_id == 16 and change_plan:
                altered = self.root / "changed-plan.zip"
                with ZipFile(altered, "w", ZIP_DEFLATED) as zipped:
                    zipped.writestr("impact-plan.json", b"other plan\n")
                archive = altered
            if artifact_id == 17 and change_sidecar:
                altered = self.root / "changed-sidecars.zip"
                with ZipFile(altered, "w", ZIP_DEFLATED) as zipped:
                    zipped.writestr("maven/runtime.asc", b"changed signature\n")
                archive = altered
            destination.write_bytes(archive.read_bytes())
            return (self.artifact if artifact_id == 17 else {"id": 16}), destination

        def observe(*args, **kwargs):
            routes.append(kwargs["trusted_workflows_by_phase"])
            self.assertEqual({"sidecars": capture._JOB}, kwargs["jobs_by_phase"])
            self.assertEqual(self.producer, args[0]["sidecars"])
            return [{"run": {"head_sha": "a" * 40}, "jobs": []}]

        environment = {"GITHUB_TOKEN": "observer"}
        if token_secret:
            environment["SIGNING_IN_MEMORY_KEY"] = "forbidden"
        with patch.object(capture.products, "_validate_plan", return_value={
                    "remoteBuildAuthorized": True, "event": "pull_request"}), \
                patch.object(capture.products, "_consumer", return_value={"producer": self.producer}), \
                patch.object(capture.products, "_observe_ci_producer_jobs", side_effect=observe), \
                patch.object(capture.products, "_download_contract_ci_upload", side_effect=download) as downloaded, \
                patch.object(capture.products, "paginated_items", return_value=[
                    self.artifact if listed_artifact is None else listed_artifact]), \
                patch.object(capture.products, "_require_artifact_job_window") as window:
            value = capture.capture_runtime_phase10_maven_sidecar_upload(
                self.plan, self.repository, self.destination,
                plan_artifact_id=16, plan_artifact_sha256=self.plan_digest,
                original_run_id=41, original_run_attempt=2,
                trusted_workflow_sha="c" * 40,
                artifact_id=17, artifact_sha256=self.sidecar_digest,
                token="observer", environ=environment,
            )
        return value, routes, downloaded, window

    def test_exact_nested_original_is_retained_atomically(self):
        value, routes, downloaded, window = self.invoke()
        self.assertEqual(self.artifact, value["artifact"])
        self.assertEqual([{"sidecars": {"path": capture._WORKFLOW,
                            "sha": "c" * 40}}], routes)
        self.assertEqual(2, downloaded.call_count)
        window.assert_called_once()
        self.assertEqual(b"original signature\n",
                         (self.destination / "original/maven/runtime.asc").read_bytes())
        self.assertEqual(self.sidecar_digest, sha256_file(self.destination / "transport.zip"))
        self.assertEqual({"capture-transport.json", "plan/impact-plan.json", "transport.zip",
                          "original/maven/runtime.asc"},
                         {item["relativePath"] for item in regular_file_inventory(self.destination)})

    def test_changed_official_plan_rejected_before_sidecar_download(self):
        with self.assertRaisesRegex(ValueError, "pinned official upload"):
            self.invoke(change_plan=True)
        self.assertFalse(self.destination.exists())

    def test_changed_sidecar_archive_rejected_before_retention(self):
        with self.assertRaisesRegex(ValueError, "changed before retention"):
            self.invoke(change_sidecar=True)
        self.assertFalse(self.destination.exists())

    def test_pgp_secret_rejected_before_observation(self):
        with self.assertRaisesRegex(ValueError, "PGP signing secret"):
            self.invoke(token_secret=True)
        self.assertFalse(self.destination.exists())

    def test_official_list_and_detail_mismatch_rejected(self):
        listed = {**self.artifact, "size_in_bytes": self.artifact["size_in_bytes"] + 1}
        with self.assertRaisesRegex(ValueError, "official listing"):
            self.invoke(listed_artifact=listed)
        self.assertFalse(self.destination.exists())

    def test_wrong_nested_job_or_child_workflow_cannot_be_selected(self):
        self.assertEqual("product-validation / runtime-phase10-maven / runtime-phase10-maven-sidecars",
                         capture._JOB)
        self.assertEqual(".github/workflows/runtime-phase10-maven.yml", capture._WORKFLOW)


if __name__ == "__main__":
    unittest.main()
