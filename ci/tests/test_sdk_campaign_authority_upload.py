"""The SDK authority file must match one official, caller-pinned job upload."""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from ci import sdk_campaign_authority_upload as locator
from ci.sdk_campaign_catalog_producer import held_sdk_campaign_candidate_from_official_authority
from products.inventory import sha256_bytes, sha256_file


class SdkCampaignAuthorityUploadTest(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"reviewed plan\n")
        self.authority = b'{"schemaVersion":1}\n'
        self.archive = self.root / "upload.zip"
        with ZipFile(self.archive, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr("sdk-campaign-authority.json", self.authority)
        self.producer = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40,
            "tree": "b" * 40, "event": "pull_request", "runId": 41,
            "runAttempt": 2, "pullRequest": 31}

    def hold(self, *, digest=None, authorized=True, archive=None):
        calls = []

        def download(artifact_id, transport_digest, name, producer, _run, _token,
                *, destination, max_bytes):
            self.assertEqual(2 * 1024 * 1024, max_bytes)
            destination.write_bytes((archive or self.archive).read_bytes())
            calls.append((artifact_id, transport_digest, name, producer))
            return {"id": artifact_id}, destination

        with (patch.object(locator.products, "_validate_plan", return_value={
                "remoteBuildAuthorized": authorized, "event": "pull_request"}),
              patch.object(locator.products, "_consumer",
                return_value={"producer": self.producer}),
              patch.object(locator.products, "_observe_ci_producer_jobs",
                return_value=[{"run": {"head_sha": "a" * 40}}]) as observed,
              patch.object(locator.products, "_download_contract_ci_upload",
                side_effect=download),
              patch.object(locator.products, "_require_artifact_job_window") as window):
            with locator.held_official_sdk_campaign_authority(
                    self.plan, self.root, artifact_id=17,
                    artifact_sha256=sha256_file(self.archive),
                    expected_authority_sha256=digest or sha256_bytes(self.authority),
                    trusted_workflow_sha="c" * 40,
                    trusted_workflow_path=".github/workflows/product-validation.yml",
                    trusted_job_name="product-validation / sdk-authority-upload",
                    token="local-test-token", environ={}) as (path, evidence):
                self.assertEqual(self.authority, path.read_bytes())
                self.assertEqual(self.producer, evidence["producer"])
            return calls, observed, window

    def test_exact_official_upload_and_job_window(self):
        calls, observed, window = self.hold()
        self.assertEqual(1, len(calls))
        self.assertEqual("codex-agent-sdk-campaign-authority-" + "b" * 40 +
                         "-attempt-2", calls[0][2])
        observed.assert_called_once()
        window.assert_called_once()

    def test_wrong_authority_digest_and_extra_member_reject(self):
        with self.assertRaisesRegex(ValueError, "independently pinned bytes"):
            self.hold(digest="sha256:" + "0" * 64)
        extra = self.root / "extra.zip"
        with ZipFile(extra, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr("sdk-campaign-authority.json", self.authority)
            zipped.writestr("unreviewed.json", b"{}\n")
        with self.assertRaises(ValueError):
            self.hold(archive=extra)

    def test_unauthorized_plan_rejects_before_official_lookup(self):
        with self.assertRaisesRegex(ValueError, "authorized PR plan"):
            self.hold(authorized=False)

    def test_composite_holds_official_upload_through_candidate_replay(self):
        events = []

        @contextmanager
        def upload(*_args, **_kwargs):
            events.append("upload-enter")
            yield self.root / "authority.json", {"artifactId": 17}
            events.append("upload-exit")

        @contextmanager
        def candidate(*_args, **_kwargs):
            events.append("candidate-enter")
            yield "verified"
            events.append("candidate-exit")

        with patch("ci.sdk_campaign_authority_upload.held_official_sdk_campaign_authority",
                   upload), patch(
                   "ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate_from_authority",
                   candidate):
            with held_sdk_campaign_candidate_from_official_authority(
                    self.plan, self.root, authority_artifact_id=17,
                    authority_artifact_sha256=sha256_file(self.archive),
                    expected_authority_sha256=sha256_bytes(self.authority),
                    authority_workflow_sha="c" * 40,
                    authority_workflow_path=".github/workflows/product-validation.yml",
                    authority_job_name="product-validation / sdk-authority-upload",
                    trusted_workflow_sha="c" * 40,
                    election_files={}, semantic_files={}, token="local-test-token",
                    environ={}) as (verified, transport):
                self.assertEqual(("verified", {"artifactId": 17}), (verified, transport))
        self.assertEqual(["upload-enter", "candidate-enter", "candidate-exit",
                          "upload-exit"], events)
