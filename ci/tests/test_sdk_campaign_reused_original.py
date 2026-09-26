"""Synthetic official catalog transport with real signature and original object."""

from dataclasses import replace
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch

from ci import sdk_campaign_reused_original as reused
from ci import sdk_campaign_original_locator as locator
from ci.sdk_campaign_catalog_producer import ReusedSdkOriginalPin
from ci.sdk_campaign_observation import ObservedSdkOriginal
from ci.sdk_campaign_original_locator import fresh_sdk_worker_route
from ci.tests import test_sdk_worker_collection as fixture_module
from ci.tests.test_product_resume_capture import archive
from products.index import IndexEntrySource, build_product_index
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes
from products.signatures import generate_development_key, sign_manifest


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ReusedSdkOriginalTest(unittest.TestCase):
    def setUp(self):
        fixture = fixture_module.SdkWorkerCollectionTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.instance, self.ready, shard, descriptor, worker_files = fixture.shard("package")
        self.worker_files = worker_files
        self.descriptor = descriptor
        self.original_object = shard / descriptor["objectPath"]
        self.worker_raw = archive(worker_files)
        _, worker_name = fresh_sdk_worker_route(self.instance, descriptor["receipt"])
        self.worker_artifact = {"id": 901, "digest": sha256_bytes(self.worker_raw),
            "expired": False, "name": worker_name,
            "archive_download_url": "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/901/zip",
            "size_in_bytes": len(self.worker_raw), "created_at": "2026-01-01T00:05:00Z",
            "workflow_run": {"id": fixture.producer["runId"], "head_sha": fixture.producer["commit"]}}
        catalog = fixture.repository / "independent-catalog"
        catalog.mkdir()
        private, self.key, signing = generate_development_key(catalog / "key")
        self.other_key = generate_development_key(catalog / "other-key")[1]
        receipt = descriptor["receipt"]
        output = receipt["outputs"][0]
        index = build_product_index([IndexEntrySource(descriptor["receiptBytes"], output["relativePath"])],
            repository=fixture.producer["repository"],
            context={"kind": "pull-request", **{field: fixture.producer[field] for field in
                ("pullRequest", "commit", "tree", "runId", "runAttempt")}},
            trust_domain="development", signing=signing, producer=fixture.producer, stable_history=None)
        manifest = catalog / "product-index.json"
        manifest.write_bytes(canonical_json_bytes(index))
        signature = sign_manifest(manifest, private, signing)
        files = {"product-index.json": manifest.read_bytes(), "product-index.sig": signature.read_bytes(),
                 "public-key.pub": self.key.read_bytes(),
                 descriptor["objectPath"]: self.original_object.read_bytes()}
        self.raw = archive(files)
        self.catalog_artifact = {
            "id": 902, "digest": sha256_bytes(self.raw), "expired": False,
            "name": "codex-agent-product-catalog-v1-pull-request-31-original",
            "archive_download_url": "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/902/zip",
            "size_in_bytes": len(self.raw), "created_at": "2026-01-01T00:05:00Z",
            "workflow_run": {"id": fixture.producer["runId"], "head_sha": fixture.producer["commit"]},
        }
        self.record = {"product": self.instance.product, "component": self.instance.component,
            "phase": self.instance.phase, "target": self.instance.target,
            "buildKey": self.ready["buildKey"], "receiptSha256": descriptor["receiptSha256"],
            "objectSha256": descriptor["objectSha256"], "state": "reused", "source": "same-pr",
            "transportSource": {"kind": "same-pr", "indexSha256": sha256_bytes(manifest.read_bytes()),
                "artifactName": output["relativePath"], "artifactSha256": output["sha256"]},
            "misses": []}
        self.original = ObservedSdkOriginal(descriptor["receiptBytes"], canonical_json_bytes(self.record),
            self.original_object, shard.parent / "stage")
        self.transport = canonical_json_bytes({"captureProducer": fixture.producer})
        self.run = {"id": 7, "run_attempt": 2, "path": ".github/workflows/ci.yml",
                    "head_sha": fixture.producer["commit"]}
        self.tested = {"sha": fixture.producer["commit"], "tree": {"sha": fixture.producer["tree"]}}
        self.catalog_job = {"name": "product-validation / sdk-catalog",
            "started_at": "2026-01-01T00:00:00Z", "completed_at": "2026-01-01T00:10:00Z"}
        worker_job, _ = fresh_sdk_worker_route(self.instance, descriptor["receipt"])
        self.worker_job = {**self.catalog_job, "name": worker_job}
        self.observed_routes = []

    def held(self, *, original=None, key=None, key_digest=None, raw=None, **routes):
        return reused.held_reused_sdk_original(self.instance, original or self.original, self.transport,
            expected_receipt_sha256=self.descriptor["receiptSha256"], catalog_artifact_id=902,
            catalog_artifact_sha256=sha256_bytes(raw or self.raw), catalog_public_key=key or self.key,
            original_artifact_id=901, original_artifact_sha256=sha256_bytes(self.worker_raw),
            expected_public_key_sha256=key_digest or sha256_bytes(self.key.read_bytes()),
            pull_request=31, trusted_workflow_sha=fixture_module.PIN, token="synthetic-token", environ={},
            **routes)

    def official(self, raw=None):
        artifact = {**self.catalog_artifact, "digest": sha256_bytes(raw or self.raw),
                    "size_in_bytes": len(raw or self.raw)}
        observed = {"run": self.run, "testedCommit": self.tested}
        def producer_jobs(producers, *, jobs_by_phase, **kwargs):
            self.observed_routes.append((jobs_by_phase, kwargs))
            if jobs_by_phase == {"catalog": "product-validation / sdk-catalog"}:
                return [{**observed, "jobs": [self.catalog_job]}]
            self.assertEqual({"worker": self.fixture.producer}, producers)
            return [{**observed, "jobs": [self.worker_job]}]
        def api_json(url, _token):
            return self.worker_artifact if url.endswith("/901") else artifact
        def download_artifact(detail, _token):
            return self.worker_raw if detail["id"] == 901 else raw or self.raw
        return patch.multiple(reused.product_reuse,
            api_json=api_json,
            download_artifact=download_artifact,
            _observe_ci_producer_jobs=producer_jobs,
            _same_pr_run=lambda *_args, **_kwargs: observed)

    def test_exact_signed_catalog_and_original_object(self):
        before = regular_file_inventory(self.original_object.parent)
        with self.official():
            with self.held() as (evidence, object_path):
                self.assertEqual(self.original_object.read_bytes(), object_path.read_bytes())
                self.assertEqual(self.descriptor["receiptSha256"], evidence["originalReceiptSha256"])
        self.assertEqual(before, regular_file_inventory(self.original_object.parent))

    def test_independent_catalog_and_worker_discovery(self):
        path = ".github/workflows/product-validation.yml"
        arguments = dict(expected_build_key=self.ready["buildKey"],
            expected_product_version="0.3.0", pull_request=31,
            repository=self.fixture.producer["repository"],
            catalog_artifact_name=self.catalog_artifact["name"], catalog_public_key=self.key,
            expected_public_key_sha256=sha256_bytes(self.key.read_bytes()),
            trusted_workflow_sha=fixture_module.PIN,
            trusted_worker_workflow_path=path, trusted_worker_job_name=self.worker_job["name"],
            trusted_catalog_workflow_path=path, trusted_catalog_job_name=self.catalog_job["name"],
            token="synthetic-token", environ={})
        def download_to_file(artifact, _token, destination, **_kwargs):
            Path(destination).write_bytes(self.worker_raw if artifact["id"] == 901 else self.raw)
        with self.official(), \
             patch.object(locator.products, "paginated_items", return_value=[self.catalog_artifact]), \
             patch.object(locator.products, "download_artifact_to_file", side_effect=download_to_file), \
             patch.object(locator, "_locate", return_value={
                 "artifact_id": 901, "artifact_sha256": sha256_bytes(self.worker_raw)}):
            pin = locator.discover_reused_sdk_original_pin(self.instance, **arguments)
            self.assertEqual(self.descriptor["receiptSha256"], pin["receipt_sha256"])
            self.assertEqual(902, pin["catalog_artifact_id"])
            self.assertEqual(901, pin["original_artifact_id"])
            self.assertIsInstance(ReusedSdkOriginalPin(**pin), ReusedSdkOriginalPin)
            with reused.held_reused_sdk_original(self.instance, self.original, self.transport,
                    expected_receipt_sha256=pin["receipt_sha256"],
                    catalog_artifact_id=pin["catalog_artifact_id"],
                    catalog_artifact_sha256=pin["catalog_artifact_sha256"],
                    original_artifact_id=pin["original_artifact_id"],
                    original_artifact_sha256=pin["original_artifact_sha256"],
                    catalog_public_key=pin["catalog_public_key"],
                    expected_public_key_sha256=pin["catalog_public_key_sha256"],
                    pull_request=pin["pull_request"], trusted_workflow_sha=fixture_module.PIN,
                    token="synthetic-token", environ={},
                    trusted_worker_workflow_path=pin["worker_workflow_path"],
                    trusted_worker_job_name=pin["worker_job_name"],
                    trusted_catalog_workflow_path=pin["catalog_workflow_path"],
                    trusted_catalog_job_name=pin["catalog_job_name"]):
                pass
            with self.assertRaisesRegex(ValueError, "independent digest"):
                locator.discover_reused_sdk_original_pin(self.instance,
                    **{**arguments, "expected_public_key_sha256": "sha256:" + "0" * 64})

    def test_independent_worker_and_catalog_workflow_pairs(self):
        path = ".github/workflows/product-validation.yml"
        with self.official():
            with self.held(trusted_worker_workflow_path=path,
                    trusted_worker_job_name=self.worker_job["name"],
                    trusted_catalog_workflow_path=path,
                    trusted_catalog_job_name=self.catalog_job["name"]):
                pass
        self.assertEqual([{"worker": {"path": path, "sha": fixture_module.PIN}},
                          {"catalog": {"path": path, "sha": fixture_module.PIN}}],
            [route[1]["trusted_workflows_by_phase"] for route in self.observed_routes])
        for routes in ({"trusted_worker_workflow_path": path},
                       {"trusted_catalog_job_name": self.catalog_job["name"]}):
            self.observed_routes.clear()
            with self.official(), self.assertRaisesRegex(ValueError, "pinned together"):
                with self.held(**routes):
                    pass
            self.assertFalse(self.observed_routes)

    def test_catalog_requires_future_attempt_bound_job(self):
        original = self.catalog_job
        self.catalog_job = {**original, "completed_at": "2026-01-01T00:01:00Z"}
        with self.official(), self.assertRaisesRegex(ValueError, "outside its original job-attempt window"):
            with self.held():
                pass

    def test_original_worker_upload_cannot_crosspair_object(self):
        self.worker_raw = archive({**self.worker_files,
            "shard/" + self.descriptor["objectPath"]: b"different original object"})
        self.worker_artifact.update(digest=sha256_bytes(self.worker_raw),
                                    size_in_bytes=len(self.worker_raw))
        with self.official(), self.assertRaises(ValueError):
            with self.held():
                pass

    def test_crosspaired_key_producer_and_object_fail_closed(self):
        with patch.object(reused.product_reuse, "api_json") as api, \
                self.assertRaisesRegex(ValueError, "independent digest"):
            with self.held(key=self.other_key):
                pass
        api.assert_not_called()
        with patch.object(reused.product_reuse, "api_json") as api, \
                self.assertRaisesRegex(ValueError, "must not be a held original"):
            with self.held(key=self.original_object):
                pass
        api.assert_not_called()
        crossed_run = {**self.run, "run_attempt": 99}
        with self.official(), patch.object(reused.product_reuse, "_same_pr_run",
                return_value={"run": crossed_run, "testedCommit": self.tested}), \
                self.assertRaisesRegex(ValueError, "workflow provenance"):
            with self.held():
                pass
        raw = archive({"product-index.json": (self.fixture.repository / "independent-catalog/product-index.json").read_bytes(),
            "product-index.sig": (self.fixture.repository / "independent-catalog/product-index.sig").read_bytes(),
            "public-key.pub": self.key.read_bytes(),
            self.descriptor["objectPath"]: b"cross-paired object"})
        with self.official(raw), self.assertRaises(ValueError):
            with self.held(raw=raw):
                pass

    def test_release_source_and_replay_mutation_reject_before_network(self):
        for changes in ({"source": "stable"}, {"state": "retained"}):
            with self.subTest(changes=changes), patch.object(reused.product_reuse, "api_json") as api, \
                    self.assertRaises(ValueError):
                changed = replace(self.original,
                    replay_record_canonical=canonical_json_bytes({**self.record, **changes}))
                with self.held(original=changed):
                    pass
            api.assert_not_called()
        changed = replace(self.original, replay_record_canonical=canonical_json_bytes({
            **self.record, "transportSource": {**self.record["transportSource"],
                "indexSha256": "sha256:" + "0" * 64}}))
        with self.official(), self.assertRaisesRegex(ValueError, "signed catalog"):
            with self.held(original=changed):
                pass
