"""Offline original-plan transport checks; no hosted acceptance is asserted."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from ci import sdk_phase10_original_plan as capture
from ci.products.inventory import (
    canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file,
)


class SdkPhase10OriginalPlanTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-original-plan-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        subprocess.run(["git", "-C", str(self.root), "init", "-q"], check=True)
        (self.root / "ci/lanes").mkdir(parents=True)
        (self.root / "ci/lanes/shared.test.pathspec").write_text("ci/**\n")
        subprocess.run(["git", "-C", str(self.root), "add",
            "ci/lanes/shared.test.pathspec"], check=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test",
            "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        self.commit = subprocess.check_output(["git", "-C", str(self.root),
            "rev-parse", "HEAD"], text=True).strip()
        self.tree = subprocess.check_output(["git", "-C", str(self.root),
            "rev-parse", "HEAD^{tree}"], text=True).strip()
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"approved original plan\n")
        self.archive = self.root / "plan-upload.zip"
        with ZipFile(self.archive, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr("impact-plan.json", self.plan.read_bytes())
            zipped.writestr("planner-control.json", b"{}\n")
        self.producer = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml", "commit": self.commit,
            "tree": self.tree, "event": "pull_request", "runId": 41,
            "runAttempt": 2, "pullRequest": 31}
        self.destination = self.root / "capture"

    def invoke(self, *, producer=None, producer_pin=None, plan_pin=None,
               artifact_pin=None, archive=None, run_conclusion="success",
               mutate_plan=False):
        producer = self.producer if producer is None else producer
        source_archive = self.archive if archive is None else archive
        calls = []

        def download(artifact_id, digest, name, selected, _run, _token, *,
                destination, max_bytes):
            calls.append((artifact_id, digest, name, selected, max_bytes))
            destination.write_bytes(source_archive.read_bytes())
            return {"id": artifact_id, "digest": digest}, destination

        def window(*_args):
            if mutate_plan:
                self.plan.write_bytes(b"changed during observation\n")

        with (patch.object(capture.products, "_validate_plan", return_value={
                    "remoteBuildAuthorized": True, "event": "pull_request"}),
              patch.object(capture.products, "_consumer", return_value={
                    "producer": self.producer}) as consumer,
              patch.object(capture.products, "_observe_ci_producer_jobs",
                  return_value=[{"run": {"status": "completed",
                      "conclusion": run_conclusion}, "jobs": []}]) as observe,
              patch.object(capture.products, "_download_contract_ci_upload",
                  side_effect=download),
              patch.object(capture.products, "_require_artifact_job_window",
                  side_effect=window) as window_check):
            result = capture.capture_sdk_phase10_original_plan(
                self.plan, self.root, self.destination,
                original_producer=producer,
                expected_original_producer_sha256=producer_pin or
                    sha256_bytes(canonical_json_bytes(self.producer)),
                plan_artifact_id=17,
                plan_artifact_sha256=artifact_pin or sha256_file(self.archive),
                expected_plan_sha256=plan_pin or sha256_file(self.plan),
                trusted_workflow_sha="c" * 40, token="observer", environ={})
        return result, calls, consumer, observe, window_check

    def test_exact_official_plan_and_original_producer_are_retained(self):
        result, calls, consumer, observe, window = self.invoke()
        self.assertEqual(sha256_file(self.archive), result["artifactSha256"])
        self.assertEqual(self.archive.read_bytes(),
            (self.destination / "official-plan.zip").read_bytes())
        self.assertEqual(self.plan.read_bytes(),
            (self.destination / "plan/impact-plan.json").read_bytes())
        self.assertEqual("codex-agent-ci-plan-" + self.tree, calls[0][2])
        self.assertEqual(self.producer, calls[0][3])
        self.assertEqual(capture.products._CATALOG_ZIP_LIMITS["max_archive_bytes"],
            calls[0][4])
        self.assertEqual(41, consumer.call_args.kwargs["original_run_id"])
        self.assertEqual(2, consumer.call_args.kwargs["original_run_attempt"])
        self.assertEqual({"plan": capture._PLAN_JOB},
            observe.call_args.kwargs["jobs_by_phase"])
        window.assert_called_once()

    def test_wrong_producer_plan_and_hosted_upload_fail_closed(self):
        cases = [
            ({"producer_pin": sha256_bytes(b"wrong")}, "independent approval"),
            ({"plan_pin": sha256_bytes(b"wrong")}, "independent file approval"),
            ({"artifact_pin": sha256_bytes(b"wrong")}, "pinned official upload"),
            ({"run_conclusion": "failure"}, "did not complete"),
            ({"mutate_plan": True}, "changed before capture"),
        ]
        for changes, message in cases:
            with self.subTest(changes=changes):
                self.plan.write_bytes(b"approved original plan\n")
                with self.assertRaisesRegex(ValueError, message):
                    self.invoke(**changes)
                self.assertFalse(self.destination.exists())
        changed = self.root / "different-plan.zip"
        with ZipFile(changed, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr("impact-plan.json", b"different original plan\n")
        with self.assertRaisesRegex(ValueError, "pinned official upload"):
            self.invoke(archive=changed)
        self.assertFalse(self.destination.exists())

    def test_dispatch_cannot_spoof_the_original_pr_producer(self):
        dispatch = {**self.producer, "event": "workflow_dispatch", "pullRequest": None}
        with self.assertRaisesRegex(ValueError, "approved PR producer"):
            self.invoke(producer=dispatch,
                producer_pin=sha256_bytes(canonical_json_bytes(dispatch)))
        self.assertFalse(self.destination.exists())

    def test_original_checkout_must_match_plan_before_official_observation(self):
        with (patch.object(capture.products, "_validate_plan",
                    side_effect=ValueError("Checkout commit does not match the impact plan")),
              patch.object(capture.products, "_observe_ci_producer_jobs") as observe,
              self.assertRaisesRegex(ValueError, "Checkout commit")):
            capture.capture_sdk_phase10_original_plan(
                self.plan, self.root, self.destination,
                original_producer=self.producer,
                expected_original_producer_sha256=sha256_bytes(
                    canonical_json_bytes(self.producer)),
                plan_artifact_id=17, plan_artifact_sha256=sha256_file(self.archive),
                expected_plan_sha256=sha256_file(self.plan),
                trusted_workflow_sha="c" * 40, token="observer", environ={})
        observe.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_mutated_or_extra_lane_pathspec_rejects_before_observation(self):
        policy = self.root / "ci/lanes/shared.test.pathspec"
        policy.write_text("tampered/**\n")
        with (patch.object(capture.products, "_validate_plan") as validate,
              patch.object(capture.products, "_observe_ci_producer_jobs") as observe,
              self.assertRaisesRegex(ValueError, "lane policy differs")):
            capture.capture_sdk_phase10_original_plan(
                self.plan, self.root, self.destination,
                original_producer=self.producer,
                expected_original_producer_sha256=sha256_bytes(
                    canonical_json_bytes(self.producer)),
                plan_artifact_id=17, plan_artifact_sha256=sha256_file(self.archive),
                expected_plan_sha256=sha256_file(self.plan),
                trusted_workflow_sha="c" * 40, token="observer", environ={})
        validate.assert_not_called()
        observe.assert_not_called()
        self.assertFalse(self.destination.exists())
        policy.write_text("ci/**\n")
        (self.root / "ci/lanes/extra.test.pathspec").write_text("untracked/**\n")
        with self.assertRaisesRegex(ValueError, "lane policy differs"):
            capture.capture_sdk_phase10_original_plan(
                self.plan, self.root, self.destination,
                original_producer=self.producer,
                expected_original_producer_sha256=sha256_bytes(
                    canonical_json_bytes(self.producer)),
                plan_artifact_id=17, plan_artifact_sha256=sha256_file(self.archive),
                expected_plan_sha256=sha256_file(self.plan),
                trusted_workflow_sha="c" * 40, token="observer", environ={})
        self.assertFalse(self.destination.exists())

    def test_lane_policy_mutated_during_plan_validation_rejects(self):
        policy = self.root / "ci/lanes/shared.test.pathspec"

        def mutate(_plan, _root):
            policy.write_text("changed during validation/**\n")
            return {"remoteBuildAuthorized": True, "event": "pull_request"}

        with (patch.object(capture.products, "_validate_plan", side_effect=mutate),
              patch.object(capture.products, "_observe_ci_producer_jobs") as observe,
              self.assertRaisesRegex(ValueError, "lane policy differs")):
            capture.capture_sdk_phase10_original_plan(
                self.plan, self.root, self.destination,
                original_producer=self.producer,
                expected_original_producer_sha256=sha256_bytes(
                    canonical_json_bytes(self.producer)),
                plan_artifact_id=17, plan_artifact_sha256=sha256_file(self.archive),
                expected_plan_sha256=sha256_file(self.plan),
                trusted_workflow_sha="c" * 40, token="observer", environ={})
        observe.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_cli_late_producer_mutation_does_not_publish(self):
        producer_file = self.root / "producer.json"
        producer_file.write_bytes(canonical_json_bytes(self.producer))
        arguments = ["--plan", str(self.plan), "--repository-root", str(self.root),
            "--destination", str(self.destination), "--original-producer", str(producer_file),
            "--expected-original-producer-sha256", sha256_file(producer_file),
            "--plan-artifact-id", "17", "--plan-artifact-sha256", sha256_file(self.archive),
            "--expected-plan-sha256", sha256_file(self.plan),
            "--trusted-workflow-sha", "c" * 40]

        def changed(_plan, _root, private, **_kwargs):
            private.mkdir()
            (private / "transport.json").write_bytes(b"{}\n")
            producer_file.write_bytes(b"changed after original capture\n")
            return {"files": regular_file_inventory(private)}

        with patch.dict(os.environ, {"GITHUB_TOKEN": "observer"}, clear=True), \
                patch.object(capture, "capture_sdk_phase10_original_plan",
                    side_effect=changed), \
                patch("sys.stderr"), self.assertRaises(SystemExit):
            capture.main(arguments)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
