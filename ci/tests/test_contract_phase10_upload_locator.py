import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from ci import contract_phase10_upload_locator as locator


class ContractPhase10UploadLocatorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ct-phase10-locator-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"reviewed plan\n")
        self.output = self.root / "phase10"
        self.output.mkdir()
        (self.output / "sidecar-selection.json").write_bytes(b"selected\n")
        self.producer = {
            "repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/ci.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 41, "runAttempt": 2, "pullRequest": 31,
        }
        self.archive = self.root / "upload.zip"
        with ZipFile(self.archive, "w", ZIP_DEFLATED) as zipped:
            zipped.write(self.output / "sidecar-selection.json", "sidecar-selection.json")

    def invoke(self, *, archive=None, plan_authorized=True,
               original_run_id=None, original_run_attempt=None):
        archive = self.archive if archive is None else archive
        seen = []

        def download(_id, _digest, name, producer, _run, _token, *, destination):
            destination.write_bytes(archive.read_bytes())
            seen.append((name, producer))
            return {"id": 17}, destination

        with (patch.object(locator.products, "_validate_plan", return_value={
                "remoteBuildAuthorized": plan_authorized, "event": "pull_request"}),
              patch.object(locator.products, "_consumer", return_value={"producer": self.producer}) as consumer,
              patch.object(locator.products, "_observe_ci_producer_jobs", return_value=[{
                  "run": {"status": "completed", "conclusion": "failure", "head_sha": "a" * 40}}]),
              patch.object(locator.products, "_download_contract_ci_upload", side_effect=download),
              patch.object(locator.products, "_require_artifact_job_window") as window):
            result = locator.observe_contract_phase10_upload(
                self.plan, self.root, self.output, trusted_workflow_sha="c" * 40,
                trusted_workflow_path=".github/workflows/product-validation.yml",
                trusted_job_name="product-validation / contract-phase10-maven",
                artifact_id=17, artifact_sha256="sha256:" + "d" * 64,
                environ={}, token="local-test-token",
                original_run_id=original_run_id,
                original_run_attempt=original_run_attempt)
            self.assertEqual(original_run_id, consumer.call_args.kwargs["original_run_id"])
            self.assertEqual(original_run_attempt, consumer.call_args.kwargs["original_run_attempt"])
        return result, seen, window

    def test_exact_job_upload_survives_sibling_failure(self):
        result, seen, window = self.invoke()
        self.assertEqual(17, result["artifactId"])
        self.assertEqual(self.producer, result["producer"])
        self.assertEqual("codex-agent-contract-phase10-maven-" + "b" * 40 + "-attempt-2",
                         result["artifactName"])
        self.assertEqual([(result["artifactName"], self.producer)], seen)
        window.assert_called_once()

    def test_changed_uploaded_member_fails(self):
        altered = self.root / "altered.zip"
        with ZipFile(altered, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr("sidecar-selection.json", b"changed\n")
        with self.assertRaisesRegex(ValueError, "differs from finalized output"):
            self.invoke(archive=altered)

    def test_later_dispatch_selects_pinned_original_run(self):
        result, _, _ = self.invoke(original_run_id=41, original_run_attempt=2)
        self.assertEqual(self.producer, result["producer"])

    def test_unauthorized_plan_fails_before_official_lookup(self):
        with self.assertRaisesRegex(ValueError, "authorized plan"):
            self.invoke(plan_authorized=False)

    def test_signing_secret_is_rejected_before_official_lookup(self):
        with patch.dict("os.environ", {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "not-a-key"}):
            with self.assertRaises(ValueError):
                self.invoke()

    def test_cli_writes_only_scalar_github_outputs(self):
        output = self.root / "github-output"
        selected = {"artifactId": 17, "artifactSha256": "sha256:" + "d" * 64,
                    "artifactName": "selected", "inventorySha256": "sha256:" + "e" * 64,
                    "producer": self.producer}
        with (patch.object(locator, "observe_contract_phase10_upload", return_value=selected),
              patch.dict("os.environ", {"GITHUB_TOKEN": "local-test-token"}),
              redirect_stdout(StringIO())):
            self.assertEqual(0, locator.main([
                "--plan", str(self.plan), "--repository-root", str(self.root),
                "--protected-output", str(self.output), "--trusted-workflow-sha", "c" * 40,
                "--trusted-workflow-path", ".github/workflows/product-validation.yml",
                "--trusted-job-name", "product-validation / contract-phase10-maven",
                "--artifact-id", "17", "--artifact-sha256", "sha256:" + "d" * 64,
                "--github-output", str(output)]))
        self.assertEqual(4, len(output.read_text().splitlines()))
        self.assertNotIn("producer", output.read_text())


if __name__ == "__main__":
    unittest.main()
