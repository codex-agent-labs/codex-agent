"""Local API/ZIP fixtures exercise transport, not real hosted execution."""

import copy
from unittest import mock

from ci.tests.test_ci import GitFixture
from ci.tests.test_product_resume_capture import archive, product_reuse
from ci.products.inventory import load_canonical_json, sha256_bytes


class RuntimeSupervisorCaptureTest(GitFixture):
    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        _, self.plan_path, _ = self.make_plan("configured/contracts.txt")
        self.plan_path = self.plan_path.resolve()
        self.environment = {"GITHUB_RUN_ID": "91", "GITHUB_RUN_ATTEMPT": "3"}
        self.producer = product_reuse._consumer(
            product_reuse._validate_plan(self.plan_path, self.root), self.environment)["producer"]
        self.pin = "c" * 40
        self.key = "sha256:" + "d" * 64
        self.run = {
            "id": 91, "run_attempt": 3, "path": self.producer["workflowPath"],
            "event": "pull_request", "status": "completed", "conclusion": "failure",
            "head_sha": self.producer["commit"],
            "repository": {"full_name": self.producer["repository"], "fork": False},
            "head_repository": {"full_name": self.producer["repository"], "fork": False},
            "pull_requests": [{"number": self.producer["pullRequest"],
                               "base": {"sha": "1" * 40}, "head": {"sha": "2" * 40}}],
            "referenced_workflows": [{
                "path": f"{self.producer['repository']}/.github/workflows/product-validation.yml@{self.pin}",
                "sha": self.pin,
            }],
        }
        self.commit = {"sha": self.producer["commit"], "tree": {"sha": self.producer["tree"]},
                       "parents": [{"sha": "1" * 40}, {"sha": "2" * 40}]}
        self.job = {"id": 901, "run_id": 91, "head_sha": self.producer["commit"],
                    "name": "product-validation / runtime-linux-arm64-supervisor",
                    "status": "completed", "conclusion": "success"}
        # Deliberately NOT a valid supervisor closure: transport cannot grant
        # content admission or convert arbitrary files into product evidence.
        self.raw = archive({"raw-evidence.txt": b"original synthetic bytes\n"})
        self.url = "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/101"
        self.artifact = {
            "id": 101, "digest": sha256_bytes(self.raw), "expired": False,
            "name": f"codex-agent-runtime-supervisor-linux-arm64-{'d' * 64}-{self.producer['tree']}",
            "size_in_bytes": len(self.raw), "archive_download_url": self.url + "/zip",
            "workflow_run": {"id": 91, "head_sha": self.producer["commit"]},
        }

    def capture(self, destination, *, run=None, jobs=None, artifact=None, raw=None):
        with mock.patch.object(product_reuse, "api_json", side_effect=[
            self.run if run is None else run, self.commit,
            self.artifact if artifact is None else artifact,
        ]) as query, mock.patch.object(product_reuse, "paginated_items", return_value=(
            [self.job] if jobs is None else jobs
        )) as listing, mock.patch.object(product_reuse, "download_artifact", return_value=(
            self.raw if raw is None else raw
        )) as download:
            result = product_reuse.capture_runtime_supervisor_upload(
                self.plan_path, destination, artifact_id=101,
                artifact_sha256=self.artifact["digest"], expected_build_key=self.key,
                trusted_workflow_sha=self.pin, repository_root=self.root,
                environ=self.environment, token="not-a-real-token")
        return result, query, listing, download

    def test_exact_original_upload_and_successful_job_survive_sibling_failure(self):
        original_plan = self.plan_path.read_bytes()
        destination = self.root / "build/supervisor-capture"
        result, query, listing, download = self.capture(destination)
        self.assertEqual(b"original synthetic bytes\n", (destination / "original/raw-evidence.txt").read_bytes())
        self.assertEqual(result, load_canonical_json(destination / "capture-transport.json"))
        self.assertEqual(self.producer, result["captureProducer"])
        self.assertEqual(self.key, result["buildKey"])
        self.assertEqual(self.run, result["observed"][0]["run"])
        self.assertEqual([self.job], result["observed"][0]["jobs"])
        self.assertEqual(original_plan, self.plan_path.read_bytes())
        self.assertEqual(3, query.call_count)
        listing.assert_called_once_with(
            "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/91/attempts/3/jobs",
            "jobs", "not-a-real-token")
        download.assert_called_once_with(self.artifact, "not-a-real-token")

    def test_cli_forwards_only_explicit_transport_bindings(self):
        destination = self.root / "build/cli-capture"
        with mock.patch.object(product_reuse, "capture_runtime_supervisor_upload") as capture, \
                mock.patch.dict(product_reuse.os.environ, {"GITHUB_TOKEN": "not-a-real-token"}, clear=True):
            self.assertEqual(0, product_reuse.main([
                "capture-runtime-supervisor-upload", "--plan", str(self.plan_path),
                "--destination", str(destination), "--artifact-id", "101",
                "--artifact-sha256", self.artifact["digest"], "--expected-build-key", self.key,
                "--trusted-workflow-sha", self.pin]))
        capture.assert_called_once_with(
            self.plan_path, destination, artifact_id=101, artifact_sha256=self.artifact["digest"],
            expected_build_key=self.key, trusted_workflow_sha=self.pin, token="not-a-real-token")

    def test_unrelated_failed_duplicate_or_wrong_attempt_producer_is_rejected(self):
        cases = [dict(jobs=[]), dict(jobs=[self.job, self.job])]
        for changes in ({"name": "product-validation / contract-continuation"},
                        {"conclusion": "failure"}, {"status": "in_progress"},
                        {"run_id": 92}, {"head_sha": "f" * 40}):
            cases.append(dict(jobs=[{**self.job, **changes}]))
        for changes in ({"run_attempt": 2}, {"referenced_workflows": []}, {"event": "push"}):
            cases.append(dict(run={**self.run, **changes}))
        for index, case in enumerate(cases):
            destination = self.root / f"build/rejected-producer-{index}"
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.capture(destination, **case)
            self.assertFalse(destination.exists())

    def test_caller_upload_binding_and_archive_integrity_are_mandatory(self):
        cases = [dict(raw=b"changed archive")]
        for changes in ({"name": "wrong"}, {"id": 102}, {"expired": True},
                        {"digest": "sha256:" + "0" * 64}, {"size_in_bytes": 1},
                        {"workflow_run": {"id": 92, "head_sha": self.producer["commit"]}}):
            cases.append(dict(artifact={**self.artifact, **changes}))
        for index, case in enumerate(cases):
            destination = self.root / f"build/rejected-upload-{index}"
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.capture(destination, **case)
            self.assertFalse(destination.exists())
        traversal = archive({"../escape": b"bad"})
        original = copy.deepcopy(self.artifact)
        self.artifact.update(digest=sha256_bytes(traversal), size_in_bytes=len(traversal))
        destination = self.root / "build/rejected-archive"
        with self.assertRaises(ValueError):
            self.capture(destination, raw=traversal)
        self.assertFalse(destination.exists())
        self.assertFalse((self.root / "escape").exists())
        self.artifact = original
