"""Original upload authentication with synthetic products; HTTP is the only mock."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from ci.tests import test_contract_ci_originals as fixture
from ci.tests.test_products import phase_receipt

adapter = fixture.product_reuse
TARGET = "linux-x64"


class RuntimeOriginalCiTest(unittest.TestCase):
    api = fixture.ContractOriginalCiCaptureTest.api

    def setUp(self):
        # Reuse the real original-CI run/attempt/commit/HTTP fixture, not a
        # mocked observer or shard verifier. No native execution is claimed.
        fixture.ContractOriginalCiCaptureTest.setUp(self)
        self.receipts = {}
        self.jobs = []
        from products.receipt import compute_build_key, write_output_manifest
        for index, phase in enumerate(fixture.PHASES, 101):
            stage = self.root / "runtime-stages" / phase
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/value.bin").write_bytes(f"synthetic {phase}\n".encode())
            write_output_manifest(stage, "runtime", TARGET, phase, TARGET, "0.2.0", {"binary": "outputs"})
            identity = {"product": "runtime", "component": TARGET, "phase": phase, "target": TARGET}
            inputs = phase_receipt()["inputs"]
            plan = {"schemaVersion": 1, **identity, "inputs": inputs,
                    "buildKey": compute_build_key(**identity, inputs=inputs)}
            upload = self.root / "runtime-uploads" / phase
            fixture.finalize_phase_object(stage_root=stage, phase_plan=plan, producer=self.producer,
                product_version="0.2.0", trust_domain="development", destination=upload / "shard")
            self.receipts[phase] = upload / "shard/phase-receipt.json"
            raw = fixture.archive_tree(upload)
            name = (f"codex-agent-runtime-worker-{TARGET}-{phase}-{TARGET}-"
                    f"{plan['buildKey'][7:]}-{self.producer['tree']}-attempt-2")
            self.artifacts[phase].update(name=name, digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw))
            self.archives[phase] = raw
            self.jobs.append({"id": index, "name": f"product-validation / runtime-{TARGET}-{phase}-{TARGET}",
                "run_id": 71, "head_sha": self.run["head_sha"], "status": "completed", "conclusion": "success",
                "started_at": "2026-09-06T10:00:00Z", "completed_at": "2026-09-06T10:30:00Z"})

    def capture(self, **changes):
        with mock.patch("reuse.api_request", side_effect=self.api(**changes)):
            return adapter.capture_runtime_original_ci_phases(self.receipts, self.output,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token")

    def test_original_uploads_and_receipts_are_retained_exactly(self):
        before = {phase: path.read_bytes() for phase, path in self.receipts.items()}
        result = self.capture()
        self.assertEqual(TARGET, result["target"])
        for phase in fixture.PHASES:
            retained = self.output / "phases" / phase
            self.assertEqual(self.archives[phase], (retained / "transport.zip").read_bytes())
            self.assertEqual(before[phase], (retained / "original/shard/phase-receipt.json").read_bytes())
            self.assertEqual(before[phase], self.receipts[phase].read_bytes())
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.capture()

    def test_failed_job_wrong_attempt_window_digest_and_workflow_reject(self):
        failed = copy.deepcopy(self.jobs)
        failed[2]["conclusion"] = "failure"
        window = copy.deepcopy(self.artifacts)
        window["metadata"]["created_at"] = "2026-09-06T11:00:00Z"
        wrong_pin = copy.deepcopy(self.run)
        wrong_pin["referenced_workflows"][0]["sha"] = "a" * 40
        for changes in ({"jobs": failed}, {"artifacts": window, "details": window},
                        {"run": wrong_pin}, {"archives": {**self.archives, "binary": b"changed"}}):
            with self.subTest(changes=list(changes)), self.assertRaises(ValueError):
                self.capture(**changes)
            self.assertFalse(self.output.exists())

    def test_wrong_receipt_and_missing_upload_reject_without_output(self):
        self.receipts["metadata"] = self.receipts["binary"]
        with self.assertRaisesRegex(ValueError, "phase identity"):
            self.capture()
        self.receipts["metadata"] = self.root / "runtime-uploads/metadata/shard/phase-receipt.json"
        missing = {phase: value for phase, value in self.artifacts.items() if phase != "metadata"}
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.capture(artifacts=missing)
        self.assertFalse(self.output.exists())

    def test_valid_but_different_receipt_is_not_laundered_by_the_upload(self):
        path = self.receipts["metadata"]
        value = fixture.load_canonical_json_bytes(path.read_bytes())
        value["productVersion"] = "0.2.1"
        path.write_bytes(fixture.canonical_json_bytes(value))
        with self.assertRaisesRegex(ValueError, "differs from the requested original receipt"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_mixed_original_run_attempts_keep_their_receipts(self):
        producer = {**self.producer, "runId": 72, "runAttempt": 3}
        prior = fixture.load_canonical_json_bytes(self.receipts["metadata"].read_bytes())
        plan = {key: prior[key] for key in ("schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        upload = self.root / "later-original"
        fixture.finalize_phase_object(stage_root=self.root / "runtime-stages/metadata", phase_plan=plan,
            producer=producer, product_version="0.2.0", trust_domain="development", destination=upload / "shard")
        self.receipts["metadata"] = upload / "shard/phase-receipt.json"
        raw = fixture.archive_tree(upload)
        self.archives["metadata"] = raw
        artifact = self.artifacts["metadata"]
        artifact.update(name=artifact["name"].removesuffix("attempt-2") + "attempt-3",
                        digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw),
                        workflow_run={"id": 72, "head_sha": self.run["head_sha"]})
        later_run = {**self.run, "id": 72, "run_attempt": 3}
        later_job = {**self.jobs[-1], "run_id": 72}
        original_api = self.api()
        prefix = f"https://api.github.com/repos/{fixture.REPOSITORY}/actions/runs/72"

        def request(url, token):
            if url == prefix + "/attempts/3":
                return json.dumps(later_run).encode()
            if url.startswith(prefix + "/attempts/3/jobs?"):
                return json.dumps({"jobs": [later_job]}).encode()
            if url.startswith(prefix + "/artifacts?"):
                return json.dumps({"artifacts": [artifact]}).encode()
            return original_api(url, token)

        with mock.patch("reuse.api_request", side_effect=request):
            result = adapter.capture_runtime_original_ci_phases(self.receipts, self.output,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token")
        self.assertEqual(2, len(result["observed"]))
        self.assertEqual(self.receipts["metadata"].read_bytes(),
            (self.output / "phases/metadata/original/shard/phase-receipt.json").read_bytes())
