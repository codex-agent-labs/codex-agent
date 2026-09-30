"""Synthetic original shards and mocked HTTP, not aggregate workflow execution."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_contract_ci_originals as fixture
from ci.tests.test_products import phase_receipt
from ci import runtime_original_ci as original_ci
from ci.runtime_original_ci import capture_runtime_aggregate_original_ci
from products.inventory import (
    publish_regular_tree as actual_publish_regular_tree,
    write_canonical_json as actual_write_canonical_json,
)
from products.receipt import compute_build_key, write_output_manifest
from products.runtime_aggregate import _adapter_receipt_identities


AGGREGATE = "runtime-aggregate-metadata-aggregate"


class RuntimeAggregateOriginalCiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = fixture.ContractOriginalCiCaptureTest()
        cls.base.setUp()
        cls.addClassCleanup(cls.base.doCleanups)
        cls.root = cls.base.root
        cls.original_receipts, cls.stages, cls.plans = {}, {}, {}
        cls.original_archives, cls.original_artifacts, cls.original_jobs = {}, {}, []
        cls.adapter_inputs = []
        identities = [*_adapter_receipt_identities(), ("runtime-aggregate", "metadata", "aggregate")]
        for number, (component, phase, target) in enumerate(identities, 1001):
            name = "-".join((component, phase, target))
            stage = cls.root / "aggregate-source-stages" / name
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/value.bin").write_bytes(f"synthetic original {name}\n".encode())
            write_output_manifest(stage, "runtime", component, phase, target, "0.2.0", {"binary": "outputs"})
            identity = {"product": "runtime", "component": component, "phase": phase, "target": target}
            inputs = phase_receipt()["inputs"]
            plan = {"schemaVersion": 1, **identity, "inputs": inputs,
                    "buildKey": compute_build_key(**identity, inputs=inputs)}
            upload = cls.root / "aggregate-source-uploads" / name
            fixture.finalize_phase_object(stage_root=stage, phase_plan=plan, producer=cls.base.producer,
                product_version="0.2.0", trust_domain="development", destination=upload / "shard")
            (upload / "empty-diagnostic.log").write_bytes(b"")
            receipt = upload / "shard/phase-receipt.json"
            cls.original_receipts[name], cls.stages[name], cls.plans[name] = receipt, stage, plan
            raw = fixture.archive_tree(upload)
            url = f"https://api.github.com/repos/{fixture.REPOSITORY}/actions/artifacts/{number}"
            cls.original_archives[name] = raw
            cls.original_artifacts[name] = {
                "id": number, "name": f"codex-agent-runtime-worker-{name}-{plan['buildKey'][7:]}-{cls.base.producer['tree']}-attempt-2",
                "digest": fixture.sha256_bytes(raw), "size_in_bytes": len(raw), "expired": False,
                "created_at": "2026-09-06T10:15:00Z", "archive_download_url": url + "/zip",
                "workflow_run": {"id": 71, "head_sha": cls.base.run["head_sha"]},
            }
            cls.original_jobs.append({"id": number, "name": f"product-validation / runtime-{name}",
                "run_id": 71, "head_sha": cls.base.run["head_sha"], "status": "completed", "conclusion": "success",
                "started_at": "2026-09-06T10:00:00Z", "completed_at": "2026-09-06T10:30:00Z"})
            if component != "runtime-aggregate":
                cls.adapter_inputs.append({"component": component, "phase": phase, "target": target, "receipt": receipt})

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aggregate-original-capture-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.output = self.work / "captured"
        self.receipts = dict(self.original_receipts)
        self.adapters = [dict(record) for record in self.adapter_inputs]
        self.artifacts = copy.deepcopy(self.original_artifacts)
        self.archives = dict(self.original_archives)
        self.jobs = copy.deepcopy(self.original_jobs)
        self.runs = {(71, 2): copy.deepcopy(self.base.run)}

    def api(self, url, token):
        self.assertEqual("not-a-real-token", token)
        prefix = f"https://api.github.com/repos/{fixture.REPOSITORY}"
        if url == prefix + f"/git/commits/{self.base.producer['commit']}":
            return json.dumps(self.base.commit).encode()
        for (run_id, attempt), run in self.runs.items():
            run_url = prefix + f"/actions/runs/{run_id}"
            if url == run_url + f"/attempts/{attempt}":
                return json.dumps(run).encode()
            if url.startswith(run_url + f"/attempts/{attempt}/jobs?"):
                return json.dumps({"jobs": [job for job in self.jobs if job["run_id"] == run_id]}).encode()
            if url.startswith(run_url + "/artifacts?"):
                return json.dumps({"artifacts": [value for value in self.artifacts.values()
                                                 if value["workflow_run"]["id"] == run_id]}).encode()
        for name, artifact in self.artifacts.items():
            if url == artifact["archive_download_url"]:
                return self.archives[name]
            if url == artifact["archive_download_url"].removesuffix("/zip"):
                return json.dumps(artifact).encode()
        raise AssertionError(f"Unexpected HTTP request: {url}")

    def capture(self, **changes):
        inputs = dict(aggregate_receipt=self.receipts[AGGREGATE], adapter_receipts=self.adapters,
                      destination=self.output, trusted_workflow_sha=self.base.pin, token="not-a-real-token")
        inputs.update(changes)
        return capture_runtime_aggregate_original_ci(**inputs)

    def test_exact_26_original_uploads_receipts_and_empty_diagnostics_are_preserved(self):
        before = {name: path.read_bytes() for name, path in self.receipts.items()}
        with patch("reuse.api_request", side_effect=self.api) as http:
            result = self.capture()
        self.assertEqual("aggregate", result["target"])
        self.assertEqual(26, len(result["artifacts"]))
        self.assertEqual(1, len(result["observed"]))
        self.assertEqual(1, sum("/actions/runs/71/artifacts?" in call.args[0] for call in http.call_args_list))
        for name, raw in before.items():
            retained = self.output / "phases" / name
            self.assertEqual(self.archives[name], (retained / "transport.zip").read_bytes())
            self.assertEqual(raw, (retained / "original/shard/phase-receipt.json").read_bytes())
            self.assertEqual(b"", (retained / "original/empty-diagnostic.log").read_bytes())
            self.assertEqual(raw, self.receipts[name].read_bytes())
            self.assertEqual(fixture.sha256_bytes(raw), result["receiptSha256s"][name])

    def test_fixed_scope_and_hostile_inputs_reject_before_http(self):
        alias = self.work / "receipt-link"
        alias.symlink_to(self.receipts[AGGREGATE])
        wrong = [dict(record) for record in self.adapters]
        wrong[0]["receipt"] = self.receipts[AGGREGATE]
        for changes in ({"adapter_receipts": self.adapters[:-1]}, {"adapter_receipts": list(reversed(self.adapters))},
                        {"adapter_receipts": [self.adapters[0], *self.adapters[:-1]]}, {"adapter_receipts": wrong},
                        {"aggregate_receipt": alias}, {"destination": self.receipts[AGGREGATE] / "nested"}, {"token": None}):
            with self.subTest(changes=list(changes)), patch("reuse.api_request", side_effect=AssertionError("HTTP")), \
                    self.assertRaises((ValueError, OSError)):
                self.capture(**changes)
        self.assertFalse(self.output.exists())

    def test_failed_job_wrong_attempt_workflow_window_digest_and_missing_upload_reject_atomically(self):
        def failed_job(): self.jobs[-1].update(conclusion="failure")
        def wrong_attempt(): self.runs[(71, 2)]["run_attempt"] = 3
        def wrong_workflow():
            self.runs[(71, 2)]["referenced_workflows"][0].update(
                path=f"{fixture.REPOSITORY}/.github/workflows/product-validation.yml@{'0' * 40}",
                sha="0" * 40)
        def outside_window(): self.artifacts[AGGREGATE]["created_at"] = "2026-09-06T11:00:00Z"
        def changed_archive(): self.archives[AGGREGATE] = b"not the original upload"
        def missing_upload(): self.artifacts.pop(AGGREGATE)
        for mutation in (failed_job, wrong_attempt, wrong_workflow, outside_window, changed_archive, missing_upload):
            try:
                mutation()
                with self.subTest(mutation=mutation.__name__), patch("reuse.api_request", side_effect=self.api), \
                        self.assertRaises(ValueError):
                    self.capture()
                self.assertFalse(self.output.exists())
            finally:
                self.jobs = copy.deepcopy(self.original_jobs)
                self.runs = {(71, 2): copy.deepcopy(self.base.run)}
                self.artifacts = copy.deepcopy(self.original_artifacts)
                self.archives = dict(self.original_archives)

    def test_valid_different_receipt_is_not_laundered_by_the_original_upload(self):
        receipt = fixture.load_canonical_json_bytes(Path(self.adapters[0]["receipt"]).read_bytes())
        receipt["productVersion"] = "0.2.1"
        replacement = self.work / "different-original.json"
        replacement.write_bytes(fixture.canonical_json_bytes(receipt))
        self.adapters[0]["receipt"] = replacement
        with patch("reuse.api_request", side_effect=self.api), \
                self.assertRaisesRegex(ValueError, "differs from its requested original receipt"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_pre_pin_and_late_copy_mutations_do_not_publish_originals(self):
        def mutate_before_pin(path, value):
            actual_write_canonical_json(path, value)
            next((Path(path).parent.parent / "phases").rglob("transport.zip")).write_bytes(b"changed before pin\n")

        with patch("reuse.api_request", side_effect=self.api), \
                patch.object(original_ci, "write_canonical_json", side_effect=mutate_before_pin), \
                self.assertRaisesRegex(ValueError, "changed before publication"):
            self.capture()
        self.assertFalse(self.output.exists())

        def mutate_before_copy(source, destination, **kwargs):
            next((Path(source) / "phases").rglob("transport.zip")).write_bytes(b"changed after pin\n")
            actual_publish_regular_tree(source, destination, **kwargs)

        with patch("reuse.api_request", side_effect=self.api), \
                patch.object(original_ci, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_mixed_reviewed_workflows_and_original_attempts_preserve_receipt_identity(self):
        producer = {**self.base.producer, "runId": 72, "runAttempt": 3}
        upload = self.work / "later-original"
        fixture.finalize_phase_object(stage_root=self.stages[AGGREGATE], phase_plan=self.plans[AGGREGATE],
            producer=producer, product_version="0.2.0", trust_domain="development", destination=upload / "shard")
        self.receipts[AGGREGATE] = upload / "shard/phase-receipt.json"
        raw = fixture.archive_tree(upload)
        self.archives[AGGREGATE] = raw
        artifact = self.artifacts[AGGREGATE]
        artifact.update(name=artifact["name"].removesuffix("attempt-2") + "attempt-3", digest=fixture.sha256_bytes(raw),
                        size_in_bytes=len(raw), workflow_run={"id": 72, "head_sha": self.base.run["head_sha"]})
        self.jobs[-1]["run_id"] = 72
        self.runs[(72, 3)] = {**copy.deepcopy(self.base.run), "id": 72, "run_attempt": 3}
        old_pin = "8a1c2a0c9a9ee1f3c5629d2d77278580f48a489c"
        self.runs[(71, 2)]["referenced_workflows"][0].update(
            path=f"{fixture.REPOSITORY}/.github/workflows/product-validation.yml@{old_pin}", sha=old_pin)
        before = {name: path.read_bytes() for name, path in self.receipts.items()}
        with patch("reuse.api_request", side_effect=self.api):
            result = self.capture()
        self.assertEqual(2, len(result["observed"]))
        self.assertEqual({old_pin, self.base.pin}, {
            value["run"]["referenced_workflows"][0]["sha"] for value in result["observed"]})
        for name, original in before.items():
            self.assertEqual(original, (self.output / "phases" / name / "original/shard/phase-receipt.json").read_bytes())
            self.assertEqual(original, self.receipts[name].read_bytes())
        self.assertEqual(self.receipts[AGGREGATE].read_bytes(),
                         (self.output / "phases" / AGGREGATE / "original/shard/phase-receipt.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
