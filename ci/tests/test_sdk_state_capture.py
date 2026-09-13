"""SDK state transport with mocked HTTP, not product replay or hosted evidence."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_resume_capture as fixture
from ci.tests.test_runtime_resume_capture import archive, product_reuse
from ci.products.inventory import load_canonical_json, sha256_bytes


class SdkStateCaptureTest(unittest.TestCase):
    def setUp(self):
        self.source = fixture.RuntimeResumeCaptureTest()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.root = self.source.root
        self.contents = {**self.source.contents,
            "runtime-state/reuse-wave-result.json": b"synthetic SDK-advanced product state\n"}
        self.raw = archive(self.contents)
        self.job = {**self.source.job, "name": "product-validation / sdk-collect-1",
                    "started_at": "2026-09-13T10:00:00Z", "completed_at": "2026-09-13T10:02:00Z"}
        self.artifact = {**self.source.artifact, "digest": sha256_bytes(self.raw), "size_in_bytes": len(self.raw),
            "created_at": "2026-09-13T10:01:00Z",
            "name": f"codex-agent-sdk-wave-1-state-{self.source.producer['tree']}-attempt-3"}
        self.destination = self.root / "build/sdk-capture"

    def capture(self, **changes):
        source = self.source
        with patch.object(product_reuse, "api_json", side_effect=[source.run, source.commit, self.artifact]), \
                patch.object(product_reuse, "paginated_items", return_value=[self.job]), \
                patch.object(product_reuse, "download_artifact", return_value=self.raw):
            return product_reuse.capture_runtime_resume_upload(source.plan_path, self.destination,
                artifact_id=101, artifact_sha256=sha256_bytes(self.raw), trusted_workflow_sha=source.pin,
                repository_root=self.root, environ=source.environment, token="synthetic-token",
                **{"sdk_state_wave": 1, **changes})

    def test_exact_sdk_wave_retains_all_original_bytes_and_distinct_transport_identity(self):
        result = self.capture()
        self.assertEqual(1, result["sdkStateWave"])
        self.assertNotIn("stateWave", result)
        self.assertEqual(self.source.producer, result["captureProducer"])
        self.assertEqual(result, load_canonical_json(self.destination / "capture-transport.json"))
        for name, raw in self.contents.items():
            self.assertEqual(raw, (self.destination / "original" / name).read_bytes())

    def test_wrong_job_name_attempt_and_upload_window_reject(self):
        original_job, original_artifact = deepcopy(self.job), deepcopy(self.artifact)
        for target, field, value in (("job", "name", "product-validation / runtime-collect-1"),
                ("artifact", "name", self.artifact["name"].replace("attempt-3", "attempt-2")),
                ("artifact", "created_at", "2026-09-13T09:59:59Z")):
            self.job, self.artifact = deepcopy(original_job), deepcopy(original_artifact)
            getattr(self, target)[field] = value
            with self.subTest(target=target, field=field), self.assertRaises(ValueError):
                self.capture()
            self.assertFalse(self.destination.exists())

    def test_invalid_or_mixed_scope_rejects_before_remote_observation(self):
        for changes in ({"sdk_state_wave": True}, {"sdk_state_wave": 0}, {"sdk_state_wave": 4},
                        {"sdk_state_wave": 1, "state_wave": 5}):
            with self.subTest(changes=changes), patch.object(product_reuse, "api_json") as query, \
                    self.assertRaisesRegex(ValueError, "SDK state wave"):
                product_reuse.capture_runtime_resume_upload(self.source.plan_path, self.destination,
                    artifact_id=101, artifact_sha256=sha256_bytes(self.raw), trusted_workflow_sha=self.source.pin,
                    repository_root=self.root, environ=self.source.environment, token="synthetic-token", **changes)
            query.assert_not_called()
            self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
