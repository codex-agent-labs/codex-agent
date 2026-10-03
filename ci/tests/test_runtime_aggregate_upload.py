"""Real transport checks over synthetic uploads; local plan replay is mocked.

No product, hosted-runner, signature or protected-environment acceptance is
claimed. Full signed carrier admission belongs to the separate SDK bridge.
"""

from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci.tests.test_products import phase_receipt
from ci.tests import test_contract_ci_originals as fixture
from products.inventory import (canonical_json_bytes, publish_regular_tree as actual_publish_regular_tree,
                                regular_file_inventory, sha256_bytes)
from products.receipt import compute_build_key


capture = fixture.product_reuse
JOB = "product-validation / runtime-aggregate-attestation"


class RuntimeAggregateUploadTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aggregate-upload-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.root = self.work / "candidate"
        self.root.mkdir()
        self.output = self.work / "captured"
        self.pin = "c" * 40
        self.producer = {"repository": fixture.REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request", "runId": 71,
            "runAttempt": 2, "pullRequest": 31}
        self.plan = {"repository": fixture.REPOSITORY, "validationCommit": "a" * 40,
            "validationTree": "b" * 40, "event": "pull_request", "pullRequest": 31,
            "remoteBuildAuthorized": True}
        self.plan_path = self.root / "plan.json"
        self.plan_path.write_bytes(canonical_json_bytes(self.plan))
        self.receipt = phase_receipt()
        self.receipt.update(product="runtime", component="runtime-aggregate", phase="metadata", target="aggregate",
                            producer=self.producer)
        self.key = compute_build_key(**{name: self.receipt[name] for name in
                                      ("product", "component", "phase", "target", "inputs")})
        self.receipt["buildKey"] = self.key
        raw = canonical_json_bytes(self.receipt)
        self.digest = sha256_bytes(raw)
        caller = {"transportProducer": self.producer, "target": "aggregate",
                  "trustedWorkflowSha": self.pin, "metadataReceiptSha256": self.digest}
        self.files = {"caller.json": canonical_json_bytes(caller), "aggregate-input/metadata-receipt.json": raw,
                      "empty-diagnostics.log": b""}
        self.run = {"id": 71, "run_attempt": 2, "path": self.producer["workflowPath"], "head_sha": "f" * 40,
            "event": "pull_request", "status": "completed", "conclusion": "success",
            "pull_requests": [{"number": 31, "base": {"sha": "1" * 40}, "head": {"sha": "f" * 40}}],
            "repository": {"full_name": fixture.REPOSITORY, "fork": False},
            "head_repository": {"full_name": fixture.REPOSITORY, "fork": False},
            "referenced_workflows": [{"path": f"{fixture.REPOSITORY}/.github/workflows/product-validation.yml@{self.pin}",
                                      "sha": self.pin}]}
        self.commit = {"sha": "a" * 40, "tree": {"sha": "b" * 40},
                       "parents": [{"sha": "1" * 40}, {"sha": "f" * 40}]}
        self.jobs = [{"id": 81, "name": JOB, "run_id": 71, "head_sha": "f" * 40,
                      "status": "completed", "conclusion": "success",
                      "started_at": "2026-09-11T10:00:00Z", "completed_at": "2026-09-11T10:30:00Z"}]
        self.artifact = {"id": 701, "name": f"codex-agent-runtime-aggregate-release-handoff-{'b' * 40}-attempt-2",
            "expired": False, "created_at": "2026-09-11T10:15:00Z",
            "archive_download_url": f"https://api.github.com/repos/{fixture.REPOSITORY}/actions/artifacts/701/zip",
            "workflow_run": {"id": 71, "head_sha": "f" * 40}}
        self.archive()

    def archive(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, raw in reversed(list(self.files.items())):
                archive.writestr(name, raw)
        self.raw = output.getvalue()
        self.artifact.update(digest=sha256_bytes(self.raw), size_in_bytes=len(self.raw))

    def api(self, url, token):
        self.assertEqual("synthetic-token", token)
        prefix = f"https://api.github.com/repos/{fixture.REPOSITORY}"
        if url == prefix + "/actions/runs/71/attempts/2":
            value = self.run
        elif url.startswith(prefix + "/actions/runs/71/attempts/2/jobs?"):
            value = {"jobs": self.jobs}
        elif url == prefix + "/git/commits/" + "a" * 40:
            value = self.commit
        elif url == self.artifact["archive_download_url"]:
            return self.raw
        elif url == prefix + "/actions/artifacts/701":
            value = self.artifact
        else:
            raise AssertionError(f"Unexpected HTTP request: {url}")
        return json.dumps(value).encode()

    def call(self, **changes):
        with patch.object(capture, "_validate_plan", return_value=self.plan), \
                patch("reuse.api_request", side_effect=self.api), \
                patch.object(capture, "download_artifact_to_file",
                    side_effect=lambda artifact, token, destination, **kwargs:
                        Path(destination).write_bytes(self.raw)):
            return capture.capture_runtime_aggregate_release_upload(self.plan_path, self.output, **{
                "artifact_id": 701, "artifact_sha256": self.artifact["digest"], "trusted_workflow_sha": self.pin,
                "expected_build_key": self.key, "expected_metadata_receipt_sha256": self.digest,
                "repository_root": self.root, "environ": {"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"},
                "token": "synthetic-token", **changes})

    def test_exact_archive_plan_and_originals_are_retained_without_product_admission(self):
        result = self.call()
        self.assertEqual(self.producer, result["captureProducer"])
        self.assertEqual(self.key, result["aggregateBuildKey"])
        self.assertEqual(self.raw, (self.output / "transport.zip").read_bytes())
        self.assertEqual(self.plan_path.read_bytes(), (self.output / "plan/impact-plan.json").read_bytes())
        for name, raw in self.files.items():
            self.assertEqual(raw, (self.output / "original" / name).read_bytes())
        before = regular_file_inventory(self.output, allow_empty=True)
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.call()
        self.assertEqual(before, regular_file_inventory(self.output, allow_empty=True))

    def test_failed_or_wrong_workflow_attempt_and_unqualified_upload_reject(self):
        baseline = deepcopy((self.run, self.jobs, self.artifact))
        for case in ("job", "pin", "attempt", "window", "timezone", "digest", "name"):
            self.run, self.jobs, self.artifact = deepcopy(baseline)
            if case == "job": self.jobs[0]["conclusion"] = "failure"
            elif case == "pin": self.run["referenced_workflows"][0]["sha"] = "d" * 40
            elif case == "attempt": self.run["run_attempt"] = 1
            elif case == "window": self.artifact["created_at"] = "2026-09-11T09:15:00Z"
            elif case == "timezone": self.artifact["created_at"] = "2026-09-11T10:15:00+01:00"
            elif case == "digest": self.artifact["digest"] = "sha256:" + "d" * 64
            else: self.artifact["name"] += "-wrong"
            with self.subTest(case=case), self.assertRaises(ValueError): self.call()
            self.assertFalse(self.output.exists())

    def test_crosspaired_caller_receipt_key_unsafe_archive_and_changed_plan_reject(self):
        with self.assertRaisesRegex(ValueError, "aggregate key"):
            self.call(expected_build_key="sha256:" + "d" * 64)
        caller = json.loads(self.files["caller.json"])
        self.files["caller.json"] = canonical_json_bytes({**caller, "transportProducer": {**self.producer, "runAttempt": 1}})
        self.archive()
        with self.assertRaisesRegex(ValueError, "observed upload"):
            self.call()
        self.files["caller.json"] = canonical_json_bytes(caller)
        self.files["../escape"] = b"unsafe"
        self.archive()
        with self.assertRaises(ValueError): self.call()
        del self.files["../escape"]
        self.archive()
        gate = capture._require_artifact_job_window
        def mutate(*args):
            gate(*args)
            self.plan_path.write_bytes(b"changed original plan\n")
        with patch.object(capture, "_require_artifact_job_window", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed before capture publication"):
            self.call()
        self.assertFalse(self.output.exists())

    def test_denied_plan_and_authority_overlap_reject_before_observation(self):
        self.plan["remoteBuildAuthorized"] = False
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaisesRegex(ValueError, "authorized"):
            self.call()
        observe.assert_not_called()
        self.output = self.root / "nested"
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError): self.call()
        observe.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_late_original_mutation_cannot_publish(self):
        def mutate_during_copy(source, destination, **kwargs):
            (Path(source) / "original/caller.json").write_bytes(b"changed during copy")
            actual_publish_regular_tree(source, destination, **kwargs)

        with patch.object(capture, "publish_regular_tree", side_effect=mutate_during_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.call()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
