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
from products.runtime_aggregate_handoff import _verify_original_ci_proof, _verify_raw_original_ci
from products.registry import PhaseInstanceId
from products.signatures import generate_development_key, sign_manifest
from products.inventory import regular_file_inventory


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

    def test_original_binary_uploads_retain_distinct_contract_handoff_once(self):
        # Capture proof only; the shared semantic gate separately authenticates
        # signatures/closure/content. No synthetic handoff is release admission.
        raw_contract = b"synthetic historical Contract receipt\n"
        digest = fixture.sha256_bytes(raw_contract)
        for component in ("jvm", "node-js", "node-wasm"):
            name = f"{component}-binary-{component}"
            plan = copy.deepcopy(self.plans[name])
            plan["inputs"]["upstreamArtifacts"] = [{
                "product": "contract", "component": "contract", "phase": "metadata", "target": "common",
                "buildKey": digest, "outputsDigest": digest,
                "contractProjection": {"schemaVersion": 1, "receiptSha256": digest,
                    "bundlePath": "outputs/codex-agent-contract-0.2.0.zip", "bundleSha256": digest,
                    "manifestSha256": digest, "contractVersion": "0.2.0", "contractDigest": digest,
                    "componentDigests": [{"component": component, "sha256": digest}]},
            }]
            plan["buildKey"] = compute_build_key(product="runtime", component=component,
                phase="binary", target=component, inputs=plan["inputs"])
            upload = self.work / name
            fixture.finalize_phase_object(stage_root=self.stages[name], phase_plan=plan,
                producer=self.base.producer, product_version="0.2.0", trust_domain="development",
                destination=upload / "shard")
            handoff = upload / "inputs/contract-input/execution-closure/receipts/metadata.json"
            handoff.parent.mkdir(parents=True)
            handoff.write_bytes(raw_contract)
            self.receipts[name] = upload / "shard/phase-receipt.json"
            for record in self.adapters:
                if record["component"] == component and record["phase"] == "binary":
                    record["receipt"] = self.receipts[name]
            raw = fixture.archive_tree(upload)
            self.archives[name] = raw
            self.artifacts[name].update(digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw),
                name=f"codex-agent-runtime-worker-{name}-{plan['buildKey'][7:]}-{self.base.producer['tree']}-attempt-2")
        with patch("reuse.api_request", side_effect=self.api):
            self.capture(selected_contract_receipt_sha256="sha256:" + "0" * 64)
        retained = self.output / "adapter-contracts"
        self.assertEqual([digest[7:]], [path.name for path in retained.iterdir()])
        self.assertEqual(raw_contract, (retained / digest[7:] / "execution-closure/receipts/metadata.json").read_bytes())

    def test_compact_release_proof_is_signed_exactly_and_binds_all_originals(self):
        private, public, signing = generate_development_key(self.work / "key")
        signing["trustDomain"] = "release"
        destinations = []

        def stream(artifact, token, destination, *, max_bytes):
            self.assertTrue(all(not path.exists() for path in destinations))
            destinations.append(Path(destination))
            raw = self.api(artifact["archive_download_url"], token)
            self.assertLessEqual(len(raw), max_bytes)
            Path(destination).write_bytes(raw)

        with patch("reuse.api_request", side_effect=self.api), \
                patch("product_reuse.download_artifact_to_file", side_effect=stream):
            proof = self.capture(signing_metadata=signing)
        self.assertEqual(26, len(destinations))
        self.assertTrue(all(not path.exists() for path in destinations))
        self.assertEqual(["transport/original-ci-phases.json"],
                         [record["relativePath"] for record in regular_file_inventory(self.output)])
        path = self.output / "transport/original-ci-phases.json"
        signature = sign_manifest(path, private, signing)
        receipts = {PhaseInstanceId("runtime", *identity): self.receipts["-".join(identity)].read_bytes()
                    for identity in [*_adapter_receipt_identities(), ("runtime-aggregate", "metadata", "aggregate")]}

        def verify():
            return _verify_original_ci_proof(path, signature, public, signing, receipts, self.base.pin)

        self.assertEqual(proof, verify())
        signature_raw = signature.read_bytes()
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            verify()
        actual_write_canonical_json(path, proof)
        signature.write_bytes(signature_raw[:-2] + b"x\n")
        with self.assertRaises(ValueError):
            verify()
        signature.write_bytes(signature_raw)

        def wrong_receipt(value): value["receiptSha256s"][AGGREGATE] = "sha256:" + "0" * 64
        def wrong_artifact(value): value["artifacts"][AGGREGATE]["workflow_run"]["id"] += 1
        def wrong_job(value): value["observed"][0]["jobs"][-1]["conclusion"] = "failure"
        def wrong_commit(value): value["observed"][0]["testedCommit"]["tree"]["sha"] = "0" * 40
        def wrong_window(value): value["artifacts"][AGGREGATE]["created_at"] = "2026-09-06T11:00:00Z"
        for mutate in (wrong_receipt, wrong_artifact, wrong_job, wrong_commit, wrong_window):
            value = copy.deepcopy(proof)
            mutate(value)
            actual_write_canonical_json(path, value)
            signature.unlink()
            sign_manifest(path, private, signing)
            with self.subTest(mutation=mutate.__name__), self.assertRaises(ValueError):
                verify()
        actual_write_canonical_json(path, proof)
        signature.unlink()
        sign_manifest(path, private, signing)
        with self.assertRaisesRegex(ValueError, "authenticated aggregate signer"):
            _verify_original_ci_proof(path, signature, public, {**signing, "keyId": "other-key"}, receipts, self.base.pin)

    def test_legacy_raw_proof_remains_fully_verified(self):
        with patch("reuse.api_request", side_effect=self.api):
            self.capture()
        receipts = {PhaseInstanceId("runtime", *identity): self.receipts["-".join(identity)].read_bytes()
                    for identity in [*_adapter_receipt_identities(), ("runtime-aggregate", "metadata", "aggregate")]}
        def verify():
            _verify_raw_original_ci(self.output.parent, self.output / "transport/original-ci-phases.json", receipts,
                                    lambda path: None, lambda path, **kwargs: regular_file_inventory(path, **kwargs))
        # The reader's historical layout is named original-evidence.
        legacy = self.work / "original-evidence"
        self.output.rename(legacy)
        self.output = legacy
        verify()
        archive = legacy / "phases" / AGGREGATE / "transport.zip"
        archive.write_bytes(archive.read_bytes() + b"altered\n")
        with self.assertRaises(ValueError):
            verify()

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
