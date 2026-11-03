"""Real ZIP/process/context checks with explicit mocked remote and Git authorities.

These fixtures do not establish hosted provenance or Apple semantic acceptance.
"""

from contextlib import ExitStack
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from ci import sdk_ios_original_validation as reader
from ci import sdk_ios_validation_workflow as worker
from ci.tests import test_sdk_ios_original_validation as fixtures
from products.inventory import canonical_json_bytes, sha256_file, write_canonical_json


class ValidationRecoveryOriginTest(unittest.TestCase):
    def setUp(self):
        self.phase = dict(product="sdk", component="sdk-ios", phase="validation", target="ios-simulator-arm64",
            buildKey="sha256:e7958fc10f983e5ddc41714a80587eacf8cd9ccd715b1829873113fd606917b7")
        self.origin = reader.validation_recovery_origin(self.phase)
        self.producer = self.origin["producer"]
        self.plan = {"repository": self.producer["repository"], "event": "pull_request", "pullRequest": 31}
        self.consumer = {**self.producer, "runId": self.producer["runId"] + 1}
        self.run = {"id": self.producer["runId"], "run_attempt": 1, "event": "pull_request",
            "path": ".github/workflows/ci.yml", "status": "completed", "conclusion": "failure",
            "head_sha": "a" * 40, "pull_requests": [{"number": 31}],
            **{field: {"full_name": self.producer["repository"], "fork": False}
               for field in ("repository", "head_repository")},
            "referenced_workflows": [{"path": "codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@"
                + self.origin["workflowSha"], "sha": self.origin["workflowSha"]}]}
        self.job = {"id": self.origin["jobId"], "run_id": self.producer["runId"], "head_sha": "a" * 40,
            "name": "product-validation / sdk-sdk-ios-validation-ios-simulator-arm64",
            "status": "completed", "conclusion": "failure", "started_at": "2026-10-13T01:00:00Z",
            "completed_at": "2026-10-13T02:00:00Z"}
        name = reader.product_reuse._worker_artifact_prefix("sdk", reader.PhaseInstanceId(
            "sdk", "sdk-ios", "validation", "ios-simulator-arm64"))
        self.artifact = {"id": self.origin["artifactId"], "digest": self.origin["artifactSha256"],
            "name": name + self.phase["buildKey"][7:] + "-" + self.producer["tree"] + "-attempt-1",
            "expired": False, "size_in_bytes": 123, "created_at": "2026-10-13T01:30:00Z",
            "archive_download_url": "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/11887642828/zip",
            "workflow_run": {"id": self.producer["runId"], "head_sha": "a" * 40}}

    def observe(self, *, origin=None, jobs=None):
        with patch.object(reader.product_reuse, "_original_ci_run", return_value=self.run), \
                patch.object(reader.product_reuse, "api_json", return_value=self.artifact), \
                patch.object(reader.product_reuse, "paginated_items", return_value=[self.job] if jobs is None else jobs), \
                patch.object(reader.product_reuse, "_observe_tested_commit") as tested, \
                patch("sdk_handoff._ensure_observed_sdk_commit") as source:
            result = reader.observe_validation_recovery(self.plan, self.consumer, self.phase,
                self.origin if origin is None else origin, repository_root=Path("/synthetic/repository"), token="fixture")
            tested.assert_called_once()
            source.assert_called_once()
            self.assertEqual(self.producer["commit"], tested.call_args.kwargs["expected_commit"])
            return result

    def test_exact_failed_origin_is_checked_without_promoting_it(self):
        self.assertEqual((self.artifact, self.run), self.observe())
        self.assertEqual("failure", self.job["conclusion"])
        for field, value in (("target", "ios-arm64"), ("buildKey", "sha256:" + "0" * 64)):
            self.assertIsNone(reader.validation_recovery_origin({**self.phase, field: value}))
        with self.assertRaisesRegex(ValueError, "independently selected"):
            self.observe(origin={**self.origin, "jobId": self.origin["jobId"] + 1})
        with patch.object(reader.product_reuse, "_original_ci_run", side_effect=AssertionError("Network before rejection")), \
                self.assertRaisesRegex(ValueError, "independently selected"):
            reader.observe_validation_recovery(self.plan, self.consumer, self.phase,
                {**self.origin, "schemaVersion": True}, repository_root=Path("/fixture"), token="no-network")

    def test_other_prs_events_repositories_and_earlier_attempts_keep_ordinary_production(self):
        for change in ({"pullRequest": 32}, {"event": "merge_group", "pullRequest": None},
                {"runId": self.producer["runId"], "runAttempt": 1},
                {"runId": self.producer["runId"] - 1, "runAttempt": 99}, {"repository": "someone/other"}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(worker, "verified_validation_recovery", side_effect=AssertionError("Unrelated recovery")):
                root = Path(temporary)
                destination = root / "must-not-exist"
                result = worker._recover_validation({}, self.phase, {**self.consumer, **change}, {}, destination,
                    repository_root=root, token="no-network", tooling={})
                self.assertIsNone(result)
                self.assertFalse(destination.exists())

    def test_wrong_job_success_duplicate_attempt_workflow_expiry_and_window_reject(self):
        for object_, field, value in ((self.job, "conclusion", "success"), (self.job, "head_sha", "b" * 40),
                (self.job, "id", 1), (self.run, "run_attempt", 2), (self.run, "conclusion", "success"),
                (self.artifact, "expired", True), (self.artifact, "digest", "sha256:" + "0" * 64),
                (self.artifact, "created_at", "2026-10-13T02:01:00Z"),
                (self.run, "referenced_workflows", [])):
            old = object_[field]
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                object_[field] = value
                self.observe()
            object_[field] = old
        with self.assertRaisesRegex(ValueError, "original failed job"):
            self.observe(jobs=[self.job, self.job])


class ValidationRecoveryBytesTest(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.SdkIosOriginalValidationTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.root = fixture, fixture.root
        self.original = fixture.template / "original"
        shutil.rmtree(self.original / "shard")
        shutil.rmtree(self.original / "originals")
        self.completed = self.original / "originals/completed"
        self.completed.mkdir(parents=True)
        (self.completed / "package-receipt.json").write_bytes(canonical_json_bytes(fixture.package_receipt))
        (self.completed / "completed-package.json").write_bytes(b"fixture native closure")
        self.package = {"completedCapture": self.completed, "receipt": fixture.package_receipt,
            "original": fixture.fixture.upload / "original",
            **{name: fixture.execution_context[name] for name in ("packageArtifact", "binaryArtifact")}}
        self.origin = {"schemaVersion": 1, "producer": fixture.producer, "artifactSha256": None}
        self.consumer = {**fixture.producer, "runId": fixture.producer["runId"] + 1, "commit": "e" * 40}
        self.archive = self.root / "production-worker.zip"

    def pack(self):
        with zipfile.ZipFile(self.archive, "w") as archive:
            for path in sorted(self.original.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(self.original).as_posix())
        self.origin["artifactSha256"] = sha256_file(self.archive)

    def context(self, stack):
        for owner, name, options in (
                (reader, "observe_validation_recovery", {"return_value": ({"size_in_bytes": self.archive.stat().st_size}, {})}),
                (reader.product_reuse, "_validate_plan", {"return_value": {"remoteBuildAuthorized": True, "event": "pull_request"}}),
                (reader.product_reuse, "_consumer", {"return_value": {"producer": self.fixture.producer}}),
                (reader, "_replan", {})):
            stack.enter_context(patch.object(owner, name, **options))
        return reader.verified_validation_recovery({}, self.consumer, self.fixture.phase, self.origin,
            self.archive, package=self.package, repository_root=self.root, token="fixture")

    def test_whole_archive_fixed_process_and_context_survive_unchanged(self):
        self.pack()
        with ExitStack() as stack, self.context(stack) as result:
            private = result["original"]
            self.assertEqual(self.fixture.producer, result["producer"])
            self.assertNotEqual(self.consumer, result["producer"])
            self.assertEqual(self.fixture.execution_context, result["context"])
            self.assertFalse((private / "shard").exists())
            self.assertEqual(self.fixture.worker_record, reader._json(private / "worker/execution.json"))
        self.assertFalse(private.exists())
        self.assertFalse((self.root / "build").exists())

    def test_failed_process_other_selection_missing_member_and_mutation_reject(self):
        path = self.original / "worker/execution.json"
        for field, value in (("returnCode", 70), ("returnCode", True), ("launchError", "launch failed"),
                ("buildKey", "sha256:" + "0" * 64), ("producer", self.consumer)):
            write_canonical_json(path, {**self.fixture.worker_record, field: value})
            self.pack()
            with self.subTest(field=field, value=value), ExitStack() as stack, self.assertRaises(ValueError):
                with self.context(stack):
                    self.fail("Bad production yielded")
        write_canonical_json(path, self.fixture.worker_record)
        self.pack()
        with ExitStack() as stack, self.assertRaisesRegex(ValueError, "changed during replay"):
            with self.context(stack) as result:
                (result["original"] / "worker/gradle.log").write_bytes(b"mutation")
        path.unlink()
        self.pack()
        with ExitStack() as stack, self.assertRaisesRegex(ValueError, "unexpected layout"):
            with self.context(stack):
                self.fail("Missing execution yielded")

    def test_recovery_emits_no_stage_when_content_or_origin_exit_fails(self):
        from contextlib import contextmanager
        @contextmanager
        def production(*args, **kwargs):
            yield {"evidenceArchive": self.archive, "context": self.fixture.execution_context}
            if self.exit_failure:
                raise ValueError("original exit rejected")
        inputs = {**self.package, "stage": self.root / "package-stage",
            "sdk": {"directory": self.root, "compatibility": {"contract": {"digest": "sha256:" + "1" * 64}}}}
        for exit_failure in (False, True):
            self.exit_failure = exit_failure
            destination = self.root / ("recover-exit" if exit_failure else "recover-content")
            destination.mkdir()
            with patch.object(worker, "validation_recovery_origin", return_value=self.origin), \
                    patch.object(worker, "verified_validation_recovery", side_effect=production), \
                    patch.object(worker, "replay_apple_validation_content",
                        **({"return_value": {"synthetic": True}} if exit_failure else {"side_effect": ValueError("full replay rejected")})), \
                    self.assertRaisesRegex(ValueError, "rejected"):
                worker._recover_validation({}, self.fixture.phase, self.consumer, inputs, destination,
                    repository_root=self.root, token="fixture", tooling={})
            self.assertFalse((self.root / "build").exists())
            self.assertFalse((destination / "shard").exists())


if __name__ == "__main__":
    unittest.main()
