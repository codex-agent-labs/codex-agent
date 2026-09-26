"""Structural SDK campaign selection fixtures, not hosted release evidence."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ci.products.sdk_campaign_dev_catalog as dev_catalog
from ci import sdk_campaign_reused_original as reused_catalog
from ci.sdk_campaign_catalog_caller import (
    SDK_CAMPAIGN_INSTANCES as CALLER_SDK_INSTANCES,
    main as catalog_caller_main,
    stage_completed_sdk_catalog,
)
import ci.sdk_campaign_catalog_caller as catalog_caller
from ci.products.index import IndexEntrySource
from ci.products.index import SignedProductIndex, verify_signed_product_index
from ci.products.receipt import write_output_manifest
from ci.products.restore import finalize_phase_object, object_relative_path
from ci.products.inventory import sha256_bytes
from ci.products.sdk_campaign_dev_catalog import stage_sdk_same_pr_catalog
from ci.products.sdk_campaign_selection import (
    SDK_CAMPAIGN_INSTANCES, held_sdk_campaign_selection, verify_sdk_campaign_objects,
    verify_sdk_campaign_selection,
)
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_resume_capture import archive


class SdkCampaignSelectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-campaign-selection-")
        cls.root = Path(cls.temporary.name).resolve()
        cls.sources, cls.envelopes, cls.archives, cls.stages = {}, {}, {}, {}
        producer = {"repository": "owner/repository", "workflowPath": ".github/workflows/product-validation.yml",
                    "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
                    "runId": 3, "runAttempt": 1, "pullRequest": 31}
        for position, instance in enumerate(sorted(SDK_CAMPAIGN_INSTANCES)):
            directory = cls.root / str(position)
            stage = directory / "stage"
            output = stage / "outputs/fixture"
            output.mkdir(parents=True)
            (output / "content.bin").write_bytes(str(instance).encode())
            manifest = write_output_manifest(stage, instance.product, instance.component,
                instance.phase, instance.target, "0.8.0", {"fixture": "outputs/fixture"})
            receipt = write_receipt(directory / "planned.json", product="sdk",
                component=instance.component, phase=instance.phase, target=instance.target,
                version="0.8.0", version_identity="0.8.0", outputs=manifest["outputs"],
                upstream=[], context={"producer": producer})
            plan = {name: receipt[name] for name in (
                "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
            shard = directory / "shard"
            finalized = finalize_phase_object(stage_root=stage, phase_plan=plan,
                producer=producer, product_version="0.8.0", trust_domain="development",
                destination=shard)
            cls.sources[instance] = IndexEntrySource(finalized["receiptBytes"],
                "outputs/fixture/content.bin")
            cls.envelopes[instance] = {name: finalized[name] for name in (
                "receipt", "receiptBytes", "receiptSha256", "objectSha256")}
            cls.archives[instance] = shard / finalized["objectPath"]
            cls.stages[instance] = stage

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_complete_exact_selection(self):
        selected = verify_sdk_campaign_selection(
            self.sources, self.envelopes, self.archives, self.stages)
        self.assertEqual(verify_sdk_campaign_objects(
            self.sources, self.envelopes, self.archives), selected)
        self.assertEqual(set(selected), SDK_CAMPAIGN_INSTANCES)
        self.assertEqual({receipt["productVersion"] for receipt in selected.values()}, {"0.8.0"})

    def test_same_pr_catalog_keeps_all_originals_and_development_trust(self):
        with tempfile.TemporaryDirectory(prefix="sdk-campaign-catalog-") as temporary:
            destination = Path(temporary).resolve() / "catalog"
            producer = next(iter(self.envelopes.values()))["receipt"]["producer"]
            index = stage_sdk_same_pr_catalog(self.sources, self.envelopes,
                self.archives, producer=producer, destination=destination)
            signed, _ = verify_signed_product_index(SignedProductIndex(
                destination / "product-index.json", destination / "product-index.sig"),
                destination / "public-key.pub")
            self.assertEqual(signed, index)
            self.assertEqual(len(index["entries"]), len(SDK_CAMPAIGN_INSTANCES))
            self.assertEqual(index["trustDomain"], "development")
            first = min(SDK_CAMPAIGN_INSTANCES)
            self.assertEqual(
                (destination / object_relative_path(self.envelopes[first]["receipt"]["buildKey"],
                    sha256_bytes(self.sources[first].receipt_bytes))).read_bytes(),
                self.archives[first].read_bytes(),
            )

    def test_completed_pin_checks_real_signed_exact_61_catalog(self):
        producer = next(iter(self.envelopes.values()))["receipt"]["producer"]
        name = (f"codex-agent-product-catalog-v1-pull-request-{producer['pullRequest']}-"
                f"{producer['tree']}-attempt-{producer['runAttempt']}")
        with tempfile.TemporaryDirectory(prefix="sdk-completed-catalog-") as temporary:
            destination = Path(temporary).resolve() / "catalog"
            stage_sdk_same_pr_catalog(self.sources, self.envelopes, self.archives,
                producer=producer, destination=destination)
            raw = archive({row["relativePath"]: (destination / row["relativePath"]).read_bytes()
                for row in dev_catalog.regular_file_inventory(destination)})
            digest = sha256_bytes(raw)
            index_sha = sha256_bytes((destination / "product-index.json").read_bytes())
            key_sha = sha256_bytes((destination / "public-key.pub").read_bytes())
            api = f"https://api.github.com/repos/{producer['repository']}/actions/artifacts/901"
            artifact = {"id": 901, "name": name, "digest": digest,
                "expired": False, "size_in_bytes": len(raw),
                "archive_download_url": api + "/zip",
                "created_at": "2026-01-01T00:05:00Z",
                "workflow_run": {"id": producer["runId"], "head_sha": producer["commit"]}}
            run = {"id": producer["runId"], "run_attempt": producer["runAttempt"],
                "path": producer["workflowPath"], "head_sha": producer["commit"]}
            observed = {"run": run, "testedCommit": {"sha": producer["commit"],
                "tree": {"sha": producer["tree"]}}}
            job = {"name": "product-validation / sdk-catalog",
                "started_at": "2026-01-01T00:00:00Z", "completed_at": "2026-01-01T00:10:00Z"}
            def download(_artifact, _token, path, **_kwargs):
                Path(path).write_bytes(raw)
            with patch.object(reused_catalog.product_reuse, "api_json", return_value=artifact), \
                 patch.object(reused_catalog.product_reuse, "download_artifact_to_file", side_effect=download), \
                 patch.object(reused_catalog.product_reuse, "_same_pr_run", return_value=observed), \
                 patch.object(reused_catalog.product_reuse, "_observe_ci_producer_jobs",
                     return_value=[{**observed, "jobs": [job]}]):
                with reused_catalog.held_completed_sdk_catalog(
                        producer=producer, artifact_name=name,
                        artifact_id=901, artifact_sha256=digest,
                        index_sha256=index_sha, public_key_sha256=key_sha,
                        trusted_workflow_sha="a" * 40, token="synthetic-token", environ={},
                        trusted_workflow_path=".github/workflows/product-validation.yml",
                        trusted_job_name=job["name"]) as held:
                    self.assertEqual(index_sha, held.values["indexSha256"])
                with self.assertRaisesRegex(ValueError, "independent digest"):
                    with reused_catalog.held_completed_sdk_catalog(
                            producer=producer, artifact_name=name, artifact_id=901,
                            artifact_sha256=digest, index_sha256=index_sha,
                            public_key_sha256="sha256:" + "0" * 64,
                            trusted_workflow_sha="a" * 40, token="synthetic-token", environ={},
                            trusted_workflow_path=".github/workflows/product-validation.yml",
                            trusted_job_name=job["name"]):
                        pass
                with self.assertRaisesRegex(ValueError, "current attempt"):
                    with reused_catalog.held_completed_sdk_catalog(
                            producer=producer, artifact_name=name + "-stale", artifact_id=901,
                            artifact_sha256=digest, index_sha256=index_sha,
                            public_key_sha256=key_sha,
                            trusted_workflow_sha="a" * 40, token="synthetic-token", environ={},
                            trusted_workflow_path=".github/workflows/product-validation.yml",
                            trusted_job_name=job["name"]):
                        pass

    def test_same_pr_catalog_rejects_partial_selection_before_output(self):
        with tempfile.TemporaryDirectory(prefix="sdk-campaign-catalog-") as temporary:
            destination = Path(temporary).resolve() / "catalog"
            producer = next(iter(self.envelopes.values()))["receipt"]["producer"]
            first = min(SDK_CAMPAIGN_INSTANCES)
            with self.assertRaisesRegex(ValueError, "all 61 phases"):
                stage_sdk_same_pr_catalog({key: value for key, value in self.sources.items()
                    if key != first}, self.envelopes, self.archives,
                    producer=producer, destination=destination)
            self.assertFalse(destination.exists())

    def test_same_pr_catalog_rejects_changed_selected_artifact_path(self):
        with tempfile.TemporaryDirectory(prefix="sdk-campaign-catalog-") as temporary:
            destination = Path(temporary).resolve() / "catalog"
            producer = next(iter(self.envelopes.values()))["receipt"]["producer"]
            first = min(SDK_CAMPAIGN_INSTANCES)
            sources = dict(self.sources)
            original_writer = dev_catalog.write_signed_product_index

            def mutate_selection(*args, **kwargs):
                sources[first] = IndexEntrySource(sources[first].receipt_bytes, "outputs/other")
                return original_writer(*args, **kwargs)

            with patch.object(dev_catalog, "write_signed_product_index", side_effect=mutate_selection):
                with self.assertRaisesRegex(ValueError, "selection changed"):
                    stage_sdk_same_pr_catalog(sources, self.envelopes, self.archives,
                        producer=producer, destination=destination)
            self.assertFalse(destination.exists())

    def test_completed_state_caller_keeps_original_receipts(self):
        producer = next(iter(self.envelopes.values()))["receipt"]["producer"]
        caller_id = type(next(iter(CALLER_SDK_INSTANCES)))
        converted = {instance: caller_id(instance.product, instance.component, instance.phase, instance.target)
            for instance in SDK_CAMPAIGN_INSTANCES}
        records = {converted[instance]: {"state": "retained", "buildKey": envelope["receipt"]["buildKey"],
            "receiptSha256": envelope["receiptSha256"], "objectSha256": envelope["objectSha256"]}
            for instance, envelope in self.envelopes.items()}
        archives = {converted[instance]: archive for instance, archive in self.archives.items()}
        state = SimpleNamespace(prior_by_instance=records, sources=archives,
            expected_fixed={"versions": {"sdk": "0.8.0"}}, producer=producer)
        with tempfile.TemporaryDirectory(prefix="sdk-campaign-caller-") as temporary:
            destination = Path(temporary).resolve() / "catalog"
            result = stage_completed_sdk_catalog(state, destination)
            self.assertEqual(result["phaseCount"], len(SDK_CAMPAIGN_INSTANCES))
            self.assertGreater(result["objectBytes"], 0)
            self.assertTrue((destination / "product-index.sig").is_file())
            oversized = Path(temporary).resolve() / "oversized"
            with patch.object(catalog_caller.products, "_CATALOG_LIMIT",
                    result["objectBytes"] + 32 * 1024 * 1024 - 1):
                with self.assertRaisesRegex(ValueError, "bounded transport capacity"):
                    stage_completed_sdk_catalog(state, oversized)
            self.assertFalse(oversized.exists())
            incomplete = dict(records)
            incomplete[min(CALLER_SDK_INSTANCES)] = {
                **incomplete[min(CALLER_SDK_INSTANCES)], "state": "build"}
            with self.assertRaisesRegex(ValueError, "unresolved phase"):
                stage_completed_sdk_catalog(SimpleNamespace(prior_by_instance=incomplete,
                    sources=archives, expected_fixed=state.expected_fixed, producer=producer),
                    Path(temporary).resolve() / "rejected")

            with patch.object(catalog_caller.products, "_verified_product_state", return_value=state) as replay:
                stdout = StringIO()
                repository = Path(__file__).resolve().parents[2]
                github_output = Path(temporary).resolve() / "github-output"
                with redirect_stdout(stdout):
                    self.assertEqual(catalog_caller_main([
                        "--plan", str(self.root / "plan.json"),
                        "--discovery-root", str(repository / "build/catalog-fixture-discovery"),
                        "--state-root", str(repository / "build/catalog-fixture-state"),
                        "--repository-root", str(repository),
                        "--destination", str(Path(temporary).resolve() / "from-cli"),
                        "--github-output", str(github_output),
                        "--sdk-original-workflow-sha", "a" * 40,
                    ]), 0)
                self.assertIn('"phaseCount":61', stdout.getvalue())
                self.assertEqual(json.loads(stdout.getvalue()), {
                    key: int(value) if key in {"phaseCount", "objectBytes"} else value
                    for key, value in (row.split("=", 1)
                        for row in github_output.read_text().splitlines())})
                replay.assert_called_once()
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                    catalog_caller_main([
                        "--plan", str(self.root / "plan.json"),
                        "--discovery-root", str(repository / "build/catalog-fixture-discovery"),
                        "--state-root", str(repository / "build/catalog-fixture-state"),
                        "--repository-root", str(repository),
                        "--destination", str(repository / "build/catalog-fixture-state/catalog"),
                        "--sdk-original-workflow-sha", "a" * 40,
                    ])
                replay.assert_called_once()
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                    catalog_caller_main([
                        "--plan", str(self.root / "plan.json"),
                        "--discovery-root", str(repository / "build/catalog-fixture-discovery"),
                        "--state-root", str(repository / "build/catalog-fixture-state"),
                        "--repository-root", str(repository),
                        "--destination", str(Path(temporary).resolve() / "separate"),
                        "--github-output", str(repository / "build/catalog-fixture-state/output"),
                        "--sdk-original-workflow-sha", "a" * 40,
                    ])
                replay.assert_called_once()

    def test_partial_or_cross_paired_selection_fails(self):
        first, second = sorted(SDK_CAMPAIGN_INSTANCES)[:2]
        with self.assertRaisesRegex(ValueError, "every exact SDK phase"):
            verify_sdk_campaign_selection({key: value for key, value in self.sources.items()
                if key != first}, self.envelopes, self.archives, self.stages)
        envelopes = dict(self.envelopes)
        envelopes[first], envelopes[second] = envelopes[second], envelopes[first]
        with self.assertRaisesRegex(ValueError, "wrong phase identity"):
            verify_sdk_campaign_selection(self.sources, envelopes, self.archives, self.stages)

    def test_wrong_object_or_changed_stage_fails(self):
        first = min(SDK_CAMPAIGN_INSTANCES)
        envelopes = dict(self.envelopes)
        envelopes[first] = {**envelopes[first], "objectSha256": "sha256:" + "0" * 64}
        with self.assertRaisesRegex(ValueError, "expected transport identity"):
            verify_sdk_campaign_selection(self.sources, envelopes, self.archives, self.stages)
        file = self.stages[first] / "outputs/fixture/content.bin"
        original = file.read_bytes()
        try:
            file.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify_sdk_campaign_selection(self.sources, self.envelopes,
                    self.archives, self.stages)
        finally:
            file.write_bytes(original)

    def test_held_selection_uses_private_exact_stages_and_detects_late_change(self):
        first = min(SDK_CAMPAIGN_INSTANCES)
        with held_sdk_campaign_selection(self.sources, self.envelopes,
                self.archives, self.stages) as (sources, envelopes, stages, receipts):
            self.assertEqual(set(stages), SDK_CAMPAIGN_INSTANCES)
            self.assertEqual(sources[first].receipt_bytes, self.sources[first].receipt_bytes)
            self.assertEqual(envelopes[first], self.envelopes[first])
            self.assertEqual(receipts[first]["productVersion"], "0.8.0")
            self.assertNotEqual(stages[first], self.stages[first])
            self.assertEqual((stages[first] / "outputs/fixture/content.bin").read_bytes(),
                             (self.stages[first] / "outputs/fixture/content.bin").read_bytes())
        with self.assertRaisesRegex(ValueError, "Held SDK campaign selection changed"):
            with held_sdk_campaign_selection(self.sources, self.envelopes,
                    self.archives, self.stages) as (_, _, stages, _):
                (stages[first] / "outputs/fixture/content.bin").write_bytes(b"changed")
        extra = self.stages[first] / "unrelated-file"
        try:
            with self.assertRaisesRegex(ValueError, "Held SDK campaign selection changed"):
                with held_sdk_campaign_selection(self.sources, self.envelopes,
                        self.archives, self.stages):
                    extra.write_bytes(b"late")
        finally:
            extra.unlink(missing_ok=True)
        original_digest = self.envelopes[first]["objectSha256"]
        try:
            with self.assertRaises(ValueError):
                with held_sdk_campaign_selection(self.sources, self.envelopes,
                        self.archives, self.stages):
                    self.envelopes[first]["objectSha256"] = "sha256:" + "0" * 64
        finally:
            self.envelopes[first]["objectSha256"] = original_digest


if __name__ == "__main__":
    unittest.main()
