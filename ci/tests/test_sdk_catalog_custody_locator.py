"""Synthetic official upload; no network, protected approval, or release claim."""

from pathlib import Path
import io
import unittest
from unittest.mock import patch
import zipfile

from ci.sdk_catalog_custody_locator import (
    CUSTODY_JOB_NAME, CUSTODY_WORKFLOW_PATH, locate_failed_sdk_catalog_custody, products,
)
from ci.tests.test_product_resume_capture import archive
from ci.tests import test_sdk_catalog_custody as fixture
from ci.products.inventory import sha256_bytes


class FailedSdkCatalogCustodyLocatorTest(unittest.TestCase):
    def setUp(self):
        helper = fixture.FailedSdkCatalogCustodyTest(
            methodName="test_exact_official_failed_upload_can_be_signed_and_reused")
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        self.helper = helper
        prepared, _ = helper.prepare()
        self.signed = helper.sign(prepared)
        self.raw = archive({file.name: file.read_bytes() for file in self.signed.iterdir()})
        self.producer = {**helper.producer, "event": "workflow_dispatch",
            "runId": 903, "runAttempt": 4, "pullRequest": None}
        self.job = CUSTODY_JOB_NAME
        self.name = "codex-agent-sdk-failed-catalog-custody-903-attempt-4"
        self.artifact = {"id": 904, "name": self.name,
            "digest": sha256_bytes(self.raw), "size_in_bytes": len(self.raw),
            "expired": False, "created_at": "2026-01-01T00:05:00Z",
            "archive_download_url": "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/904/zip",
            "workflow_run": {"id": 903, "head_sha": self.producer["commit"]}}
        self.observation = {"run": {"status": "completed", "conclusion": "success",
            "head_sha": self.producer["commit"]}, "jobs": [{"name": self.job,
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-01T00:10:00Z"}]}
        self.selection = dict(destination=helper.root / "located",
            catalog_producer=helper.producer, catalog_artifact_id=902,
            catalog_artifact_sha256=helper.selection["artifact_sha256"],
            catalog_workflow_sha=helper.route["trusted_workflow_sha"],
            catalog_workflow_path=helper.route["trusted_workflow_path"],
            catalog_job_name=helper.route["trusted_job_name"],
            custody_producer=self.producer, custody_artifact_id=904,
            custody_artifact_sha256=sha256_bytes(self.raw),
            custody_workflow_sha=helper.source, custody_job_name=self.job,
            trusted_source_commit=helper.source,
            keyring_path=helper.policy, keys_directory=helper.keys,
            expected_keyring_sha256=helper.keyring_sha,
            expected_keys_inventory_sha256=helper.keys_sha,
            token="synthetic-token", environ={})

    def invoke(self, *, artifact=None, observation=None, raw=None, **changes):
        self.downloaded = []
        observed = []

        def observe(producers, **kwargs):
            observed.append((producers, kwargs))
            return [self.observation if observation is None else observation]

        def download(_artifact, _token, destination, **_kwargs):
            self.downloaded.append(_artifact["id"])
            Path(destination).write_bytes(self.raw if raw is None else raw)

        with patch.object(products, "_observe_ci_producer_jobs", side_effect=observe), \
                patch.object(products, "api_json", return_value=self.artifact if artifact is None else artifact), \
                patch.object(products, "download_artifact_to_file", side_effect=download):
            result = locate_failed_sdk_catalog_custody(**(self.selection | changes))
        return result, observed, self.downloaded

    def test_dispatch_upload_returns_key_only_from_signed_external_custody(self):
        result, observed, downloaded = self.invoke()
        self.assertEqual([904], downloaded)
        self.assertEqual(self.name, result["custodyArtifactName"])
        self.assertEqual(self.helper.base.key.read_bytes(), Path(result["publicKey"]).read_bytes())
        self.assertEqual(self.helper.selection["artifact_sha256"], result["catalogArtifactSha256"])
        self.assertEqual({"custody": self.producer}, observed[0][0])
        self.assertEqual({"custody": self.job}, observed[0][1]["jobs_by_phase"])
        self.assertEqual({"custody": {"path": CUSTODY_WORKFLOW_PATH,
            "sha": self.helper.source}}, observed[0][1]["trusted_workflows_by_phase"])
        self.assertTrue(observed[0][1]["allow_protected_dispatch"])
        self.assertIsNone(observed[0][1]["dispatch_authorization_job"])

    def test_official_transport_order_does_not_change_signed_contents(self):
        files = {file.name: file.read_bytes() for file in self.signed.iterdir()}
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as result:
            for name in sorted(files, reverse=True):
                result.writestr(name, files[name])
        raw = output.getvalue()
        artifact = {**self.artifact, "digest": sha256_bytes(raw),
            "size_in_bytes": len(raw)}
        verified, _, downloaded = self.invoke(raw=raw, artifact=artifact,
            custody_artifact_sha256=sha256_bytes(raw))
        self.assertEqual([904], downloaded)
        self.assertEqual(self.name, verified["custodyArtifactName"])

    def test_wrong_producer_job_and_official_digest_stop_before_download(self):
        for changed in ({"custody_producer": {**self.producer, "runId": self.helper.producer["runId"]}},
                        {"custody_producer": {**self.producer, "event": "workflow_run"}},
                        {"custody_job_name": "product-validation / sdk-catalog-custody / sdk-failed-catalog-custody"}):
            with self.subTest(changed=changed), patch.object(products, "api_json") as api, \
                    self.assertRaises(ValueError):
                locate_failed_sdk_catalog_custody(**(self.selection | changed))
            api.assert_not_called()
        wrong_job = {**self.observation, "jobs": [{**self.observation["jobs"][0],
            "name": "product-validation / wrong"}]}
        with self.assertRaisesRegex(ValueError, "job is missing"):
            self.invoke(observation=wrong_job)
        self.assertEqual([], self.downloaded)
        for artifact in ({**self.artifact, "digest": "sha256:" + "0" * 64},
                         {**self.artifact, "workflow_run": {
                             **self.artifact["workflow_run"], "id": 999}},
                         {**self.artifact, "name": self.name + "-other"}):
            with self.subTest(artifact=artifact), \
                    self.assertRaisesRegex(ValueError, "independently pinned dispatch"):
                self.invoke(artifact=artifact)
            self.assertEqual([], self.downloaded)
        with patch.object(products, "api_json") as api, \
                self.assertRaisesRegex(ValueError, "differs from independent policy"):
            locate_failed_sdk_catalog_custody(**(self.selection | {
                "expected_keyring_sha256": "sha256:" + "0" * 64}))
        api.assert_not_called()

    def test_invalid_window_and_tampered_signed_record_fail_closed(self):
        out_of_window = {**self.artifact, "created_at": "2026-01-01T00:11:00Z"}
        with self.assertRaisesRegex(ValueError, "outside its original job-attempt window"):
            self.invoke(artifact=out_of_window)
        self.assertEqual([], self.downloaded)
        files = {file.name: file.read_bytes() for file in self.signed.iterdir()}
        files["sdk-failed-catalog-custody.sig"] = b"tampered\n"
        tampered = archive(files)
        with self.assertRaises(ValueError):
            self.invoke(raw=tampered, custody_artifact_sha256=sha256_bytes(tampered),
                artifact={**self.artifact, "digest": sha256_bytes(tampered),
                    "size_in_bytes": len(tampered)})
        self.assertFalse((self.helper.root / "located").exists())


if __name__ == "__main__":
    unittest.main()
