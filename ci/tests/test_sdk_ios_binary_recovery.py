"""Original transport recovery using tiny fixtures, not hosted acceptance."""

from contextlib import contextmanager
from copy import deepcopy
import io
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

from ci.tests import test_sdk_ios_package_upload as fixture
from ci import sdk_ios_binary_recovery as recovery
from products.inventory import canonical_json_bytes, regular_file_inventory, load_canonical_json_bytes


class IosBinaryRecoveryTest(unittest.TestCase):
    phase, target = "binary", "ios"
    api = fixture.SdkIosBinaryUploadTest.api
    archive = fixture.SdkIosBinaryUploadTest.archive
    setUp = fixture.SdkIosBinaryUploadTest.setUp

    @contextmanager
    def gates(self):
        self.run["conclusion"] = "failure"
        self.jobs[0]["name"] += f" ({load_canonical_json_bytes(self.receipt_bytes)['buildKey']}, ..."
        original_api = self.api
        def api(url, token):
            if url.startswith("https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/71/artifacts?"):
                import json
                return json.dumps({"artifacts": [self.artifact]}).encode()
            return original_api(url, token)
        @contextmanager
        def ranges(artifact, token):
            with zipfile.ZipFile(io.BytesIO(self.raw)) as archive:
                yield archive, None
        with patch.object(recovery.products, "_validate_plan", return_value=self.plan), \
                patch("reuse.api_request", side_effect=api), \
                patch.object(recovery, "open_reference_archive", side_effect=ranges), \
                patch.object(recovery.products, "download_artifact_to_file",
                    side_effect=lambda artifact, token, destination, **kwargs: Path(destination).write_bytes(self.raw)):
            yield

    def capture(self, **changes):
        receipt = load_canonical_json_bytes(self.receipt_bytes)
        return recovery.capture_prior_ios_binary(self.plan_path, self.plan,
            {**self.producer, "runId": 72}, receipt["buildKey"], self.output, self.work,
            repository_root=self.root, environ={}, trusted_workflow_sha=self.pin,
            token="synthetic-token", attempts=(self.run,), **changes)

    def test_exact_original_capture_and_fresh_replay_preserve_receipt(self):
        with self.gates():
            records = self.capture()
            before = regular_file_inventory(self.output, allow_empty=True)
            replay = recovery.replay_prior_ios_binary(self.output, self.work, plan=self.plan,
                consumer_producer={**self.producer, "runId": 72}, trusted_workflow_sha=self.pin,
                token="synthetic-token", environ={})
        self.assertEqual(records, replay)
        self.assertEqual(before, regular_file_inventory(self.output, allow_empty=True))
        self.assertEqual(self.receipt_bytes,
            (self.output / "sdk-ios/binary/ios/original/shard/phase-receipt.json").read_bytes())
        self.assertEqual(self.raw, (self.output / "sdk-ios/binary/ios/transport.zip").read_bytes())

    def test_failed_original_job_cannot_be_recovered(self):
        with self.gates(), patch.object(recovery.products, "capture_sdk_ios_binary_upload") as capture:
            self.jobs[0]["conclusion"] = "failure"
            self.assertEqual([], self.capture())
            capture.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_ambiguous_original_job_and_wrong_matrix_key_fail_closed(self):
        with self.gates(), patch.object(recovery.products, "capture_sdk_ios_binary_upload") as capture:
            self.jobs.append(deepcopy(self.jobs[0]))
            with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
                self.capture()
            self.jobs.pop()
            self.jobs[0]["name"] = "product-validation / sdk-sdk-ios-binary-ios (sha256:" + "0" * 64 + ", ..."
            with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
                self.capture()
            capture.assert_not_called()

    def test_same_or_different_pr_attempt_is_not_recovery_authority(self):
        with self.gates():
            prior = deepcopy(self.run)
            prior["id"] = 72
            with self.assertRaisesRegex(ValueError, "earlier failed"):
                recovery._require_prior(self.plan, {**self.producer, "runId": 72}, prior)
            prior = deepcopy(self.run)
            prior["pull_requests"][0]["number"] = 32
            with self.assertRaisesRegex(ValueError, "earlier failed"):
                recovery._require_prior(self.plan, {**self.producer, "runId": 72}, prior)

    def test_tampered_retained_archive_rejected_without_redownload(self):
        with self.gates():
            self.capture()
            (self.output / "sdk-ios/binary/ios/transport.zip").write_bytes(b"corrupt")
            with patch.object(recovery.products, "download_artifact_to_file", side_effect=AssertionError("redownload")), \
                    self.assertRaises(ValueError):
                recovery.replay_prior_ios_binary(self.output, self.work, plan=self.plan,
                    consumer_producer={**self.producer, "runId": 72}, trusted_workflow_sha=self.pin,
                    token="synthetic-token", environ={})

    def test_malformed_expiration_and_wrong_discovery_key_reject_before_capture(self):
        with self.gates(), patch.object(recovery.products, "capture_sdk_ios_binary_upload") as capture:
            self.artifact["expired"] = None
            with self.assertRaisesRegex(ValueError, "expiration"):
                self.capture()
            self.artifact["expired"] = False
            actual = recovery.products.validate_phase_receipt
            def wrong(raw):
                receipt = actual(raw)
                return {**receipt, "buildKey": "sha256:" + "0" * 64}
            with patch.object(recovery.products, "validate_phase_receipt", side_effect=wrong), \
                    self.assertRaisesRegex(ValueError, "discovery receipt"):
                self.capture()
            capture.assert_not_called()

    def test_extra_capture_family_rejected(self):
        with self.gates():
            self.capture()
            (self.output / "extra").write_bytes(b"unrelated")
            with self.assertRaisesRegex(ValueError, "unexpected capture family"):
                recovery.replay_prior_ios_binary(self.output, self.work, plan=self.plan,
                    consumer_producer={**self.producer, "runId": 72}, trusted_workflow_sha=self.pin,
                    token="synthetic-token", environ={})

    def test_conflicting_verified_same_key_candidates_never_publish(self):
        # Test only collision selection here. The exact capture/ZIP/shard gates
        # are exercised without these mocks by the original-preservation test.
        with self.gates():
            prior = {**self.run, "id": 70}
            receipts = [load_canonical_json_bytes(self.receipt_bytes)]
            receipts.append({**receipts[0], "producer": {**self.producer, "runId": 70},
                "outputs": [{**receipts[0]["outputs"][0], "sha256": "sha256:" + "0" * 64},
                            *receipts[0]["outputs"][1:]]})
            index = -1
            @contextmanager
            def ranges(artifact, token):
                nonlocal index
                index += 1
                incoming = io.BytesIO()
                with zipfile.ZipFile(incoming, "w") as archive:
                    archive.writestr("shard/phase-receipt.json", canonical_json_bytes(receipts[index]))
                with zipfile.ZipFile(incoming) as archive:
                    yield archive, None
            def listing(url, field, token):
                if field == "artifacts":
                    return [self.artifact]
                run = 70 if "/70/" in url else 71
                return [{**self.jobs[0], "run_id": run}]
            with patch.object(recovery.products, "paginated_items", side_effect=listing), \
                    patch.object(recovery.products, "_contract_ci_upload_metadata", return_value=self.artifact), \
                    patch.object(recovery.products, "_require_artifact_job_window"), \
                    patch.object(recovery, "open_reference_archive", side_effect=ranges), \
                    patch.object(recovery.products, "capture_sdk_ios_binary_upload"), \
                    patch.object(recovery, "verify_phase_shard", side_effect=lambda *args:
                        {"receiptBytes": canonical_json_bytes(receipts[index]), "receipt": receipts[index]}), \
                    self.assertRaisesRegex(ValueError, "conflicting output inventories"):
                recovery.capture_prior_ios_binary(self.plan_path, self.plan,
                    {**self.producer, "runId": 72}, receipts[0]["buildKey"], self.output, self.work,
                    repository_root=self.root, environ={}, trusted_workflow_sha=self.pin,
                    token="synthetic-token", attempts=(self.run, prior))
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
