"""The SDK authority file must match one official, caller-pinned job upload."""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from ci import sdk_campaign_authority_upload as locator
from ci.sdk_campaign_catalog_producer import held_sdk_campaign_candidate_from_official_authority
from products.inventory import canonical_json_bytes, sha256_bytes, sha256_file


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
        self.dispatch = {**self.producer, "commit": "d" * 40,
            "tree": "e" * 40, "event": "workflow_dispatch", "runId": 88,
            "runAttempt": 1, "pullRequest": None}

    def hold(self, *, digest=None, authorized=True, archive=None,
             original_run_id=41, original_run_attempt=2,
             dispatch=None, dispatch_pin=None):
        calls = []
        dispatch = self.dispatch if dispatch is None else dispatch

        def download(artifact_id, transport_digest, name, producer, _run, _token,
                *, destination, max_bytes):
            self.assertEqual(2 * 1024 * 1024, max_bytes)
            destination.write_bytes((archive or self.archive).read_bytes())
            calls.append((artifact_id, transport_digest, name, producer))
            return {"id": artifact_id}, destination

        with (patch.object(locator.products, "_validate_plan", return_value={
                "remoteBuildAuthorized": authorized, "event": "pull_request"}),
              patch.object(locator.products, "_consumer",
                return_value={"producer": self.producer}) as consumer,
              patch.object(locator.products, "_observe_ci_producer_jobs",
                return_value=[{"run": {"head_sha": "d" * 40,
                                       "status": "completed", "conclusion": "success"},
                               "jobs": []}]) as observed,
              patch.object(locator.products, "_download_contract_ci_upload",
                side_effect=download),
              patch.object(locator.products, "_require_artifact_job_window") as window):
            with locator.held_official_sdk_campaign_authority(
                    self.plan, self.root, artifact_id=17,
                    artifact_sha256=sha256_file(self.archive),
                    expected_authority_sha256=digest or sha256_bytes(self.authority),
                    trusted_workflow_sha="c" * 40,
                    trusted_workflow_path=locator._WORKFLOW,
                    trusted_job_name=locator._JOB,
                    authority_producer=dispatch,
                    expected_authority_producer_sha256=(dispatch_pin or
                        sha256_bytes(canonical_json_bytes(dispatch))),
                    token="local-test-token", environ={},
                    original_run_id=original_run_id,
                    original_run_attempt=original_run_attempt) as (path, evidence):
                self.assertEqual(self.authority, path.read_bytes())
                self.assertEqual(self.producer, evidence["originalProducer"])
                self.assertEqual(dispatch, evidence["authorityProducer"])
            self.assertEqual(original_run_id, consumer.call_args.kwargs["original_run_id"])
            self.assertEqual(original_run_attempt,
                consumer.call_args.kwargs["original_run_attempt"])
            return calls, observed, window

    def test_exact_official_upload_and_job_window(self):
        calls, observed, window = self.hold()
        self.assertEqual(1, len(calls))
        self.assertEqual("codex-agent-sdk-campaign-authority-" + "b" * 40 +
                         "-attestation-88-attempt-1", calls[0][2])
        self.assertEqual(self.dispatch, calls[0][3])
        self.assertEqual(locator._WORKFLOW,
            observed.call_args.kwargs["trusted_workflows_by_phase"]["authority"]["path"])
        self.assertIsNone(observed.call_args.kwargs["dispatch_authorization_job"])
        observed.assert_called_once()
        window.assert_called_once()

    def test_later_run_observes_explicit_original_authority_producer(self):
        self.hold(original_run_id=41, original_run_attempt=2)

    def test_dispatch_must_be_distinct_and_independently_pinned(self):
        with self.assertRaisesRegex(ValueError, "independent producer pin"):
            self.hold(dispatch_pin=sha256_bytes(b"wrong"))
        same = {**self.producer, "event": "workflow_dispatch",
                "pullRequest": None}
        with self.assertRaisesRegex(ValueError, "distinct original PR"):
            self.hold(dispatch=same)

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
        forwarding = []

        @contextmanager
        def upload(*_args, **kwargs):
            events.append("upload-enter")
            forwarding.append(("upload", kwargs["original_run_id"],
                kwargs["original_run_attempt"]))
            yield self.root / "authority.json", {"artifactId": 17}
            events.append("upload-exit")

        @contextmanager
        def candidate(*_args, **kwargs):
            events.append("candidate-enter")
            forwarding.append(("candidate", kwargs["original_run_id"],
                kwargs["original_run_attempt"]))
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
                    authority_workflow_path=locator._WORKFLOW,
                    authority_job_name=locator._JOB,
                    authority_producer=self.dispatch,
                    expected_authority_producer_sha256=sha256_bytes(
                        canonical_json_bytes(self.dispatch)),
                    trusted_workflow_sha="c" * 40,
                    election_files={}, semantic_files={}, token="local-test-token",
                    environ={}, original_run_id=41,
                    original_run_attempt=2) as (verified, transport):
                self.assertEqual(("verified", {"artifactId": 17}), (verified, transport))
        self.assertEqual(["upload-enter", "candidate-enter", "candidate-exit",
                          "upload-exit"], events)
        self.assertEqual([("upload", 41, 2), ("candidate", 41, 2)], forwarding)
