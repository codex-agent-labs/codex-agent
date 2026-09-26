"""A failed nested attempt is replayed from its exact original state upload."""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_nested_wave_replay as replay


_PRODUCER = {"repository": "codex-agent-labs/codex-agent",
    "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40,
    "tree": "b" * 40, "event": "pull_request", "runId": 7,
    "runAttempt": 2, "pullRequest": 31}
_PIN = {"artifact_id": 901, "artifact_sha256": "sha256:" + "d" * 64}


class NestedSdkWaveReplayTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="sdk-nested-replay-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"prior plan\n")
        self.destination = self.root / "catalog"
        self.plan_value = {"repository": _PRODUCER["repository"], "event": "pull_request",
            "pullRequest": 31, "validationCommit": _PRODUCER["commit"],
            "validationTree": _PRODUCER["tree"]}

    def _capture(self, plan_path, destination, **kwargs):
        self.assertEqual(kwargs["sdk_state_wave"], 11)
        self.assertEqual(kwargs["artifact_id"], _PIN["artifact_id"])
        self.assertEqual(kwargs["artifact_sha256"], _PIN["artifact_sha256"])
        self.assertEqual(kwargs["environ"]["GITHUB_RUN_ID"], "7")
        self.assertEqual(kwargs["environ"]["GITHUB_RUN_ATTEMPT"], "2")
        (destination / "original/product-resume-inputs/plan").mkdir(parents=True)
        (destination / "original/product-resume-inputs/plan/impact-plan.json").write_bytes(self.plan.read_bytes())
        (destination / "original/product-resume-state").mkdir()
        (destination / "original/runtime-state").mkdir()
        return {"captureProducer": _PRODUCER, "sdkStateWave": 11,
            "artifact": {"id": _PIN["artifact_id"], "digest": _PIN["artifact_sha256"]}}

    def _stage(self, state, destination):
        self.assertEqual(state.producer, _PRODUCER)
        destination.mkdir()
        (destination / "index.json").write_bytes(b"verified partial catalog\n")
        return {"phaseCount": 2, "indexSha256": "sha256:" + "e" * 64}

    def test_prior_failed_attempt_is_replayed_and_published_only_after_checks(self):
        with patch.object(replay.products, "_validate_plan", return_value=self.plan_value), \
                patch.object(replay, "locate_failed_nested_sdk_wave", return_value=_PIN) as locate, \
                patch.object(replay.products, "capture_runtime_resume_upload", side_effect=self._capture) as capture, \
                patch.object(replay.products, "_verified_product_state",
                    return_value=SimpleNamespace(producer=_PRODUCER)) as verified, \
                patch.object(replay, "stage_partial_sdk_catalog", side_effect=self._stage):
            result = replay.replay_failed_nested_sdk_wave(self.plan, self.destination,
                producer=_PRODUCER, wave=11, trusted_workflow_sha="c" * 40,
                repository_root=self.root, environ={"GITHUB_RUN_ID": "99",
                    "GITHUB_RUN_ATTEMPT": "5"}, token="test-token")
        locate.assert_called_once_with(_PRODUCER, wave=11,
            trusted_workflow_sha="c" * 40, token="test-token",
            environ={"GITHUB_RUN_ID": "99", "GITHUB_RUN_ATTEMPT": "5"})
        self.assertEqual(capture.call_count, 1)
        self.assertEqual(verified.call_count, 1)
        self.assertEqual(verified.call_args.args[2].name, "runtime-state")
        self.assertEqual((self.destination / "index.json").read_bytes(), b"verified partial catalog\n")
        self.assertEqual(result["stateArtifactSha256"], _PIN["artifact_sha256"])

    def test_cross_commit_and_wrong_wave_reject_before_official_lookup(self):
        with patch.object(replay.products, "_validate_plan", return_value=self.plan_value), \
                patch.object(replay, "locate_failed_nested_sdk_wave") as locate:
            with self.assertRaisesRegex(ValueError, "prior attempt at checkout HEAD"):
                replay.replay_failed_nested_sdk_wave(self.plan, self.destination,
                    producer={**_PRODUCER, "commit": "f" * 40}, wave=11,
                    trusted_workflow_sha="c" * 40, repository_root=self.root,
                    environ={}, token="test-token")
            with self.assertRaisesRegex(ValueError, "wave 11–16"):
                replay.replay_failed_nested_sdk_wave(self.plan, self.destination,
                    producer=_PRODUCER, wave=17, trusted_workflow_sha="c" * 40,
                    repository_root=self.root, environ={}, token="test-token")
        locate.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_failed_capture_does_not_publish_partial_catalog(self):
        def wrong_capture(*args, **kwargs):
            return {**self._capture(*args, **kwargs), "sdkStateWave": 12}
        with patch.object(replay.products, "_validate_plan", return_value=self.plan_value), \
                patch.object(replay, "locate_failed_nested_sdk_wave", return_value=_PIN), \
                patch.object(replay.products, "capture_runtime_resume_upload", side_effect=wrong_capture), \
                patch.object(replay.products, "_verified_product_state") as verified, \
                self.assertRaisesRegex(ValueError, "selected failed attempt"):
            replay.replay_failed_nested_sdk_wave(self.plan, self.destination,
                producer=_PRODUCER, wave=11, trusted_workflow_sha="c" * 40,
                repository_root=self.root, environ={}, token="test-token")
        verified.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_phase_object_mismatch_does_not_publish_partial_catalog(self):
        with patch.object(replay.products, "_validate_plan", return_value=self.plan_value), \
                patch.object(replay, "locate_failed_nested_sdk_wave", return_value=_PIN), \
                patch.object(replay.products, "capture_runtime_resume_upload", side_effect=self._capture), \
                patch.object(replay.products, "_verified_product_state",
                    return_value=SimpleNamespace(producer=_PRODUCER)), \
                patch.object(replay, "stage_partial_sdk_catalog",
                    side_effect=ValueError("Original SDK phase object differs from receipt")), \
                self.assertRaisesRegex(ValueError, "phase object differs"):
            replay.replay_failed_nested_sdk_wave(self.plan, self.destination,
                producer=_PRODUCER, wave=11, trusted_workflow_sha="c" * 40,
                repository_root=self.root, environ={}, token="test-token")
        self.assertFalse(self.destination.exists())

    def test_signing_secret_rejects_before_lookup_or_capture(self):
        with patch.object(replay.products, "_validate_plan") as validate, \
                patch.object(replay, "locate_failed_nested_sdk_wave") as locate, \
                self.assertRaisesRegex(ValueError, "signing-secret"):
            replay.replay_failed_nested_sdk_wave(self.plan, self.destination,
                producer=_PRODUCER, wave=11, trusted_workflow_sha="c" * 40,
                repository_root=self.root,
                environ={"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "secret"},
                token="test-token")
        validate.assert_not_called()
        locate.assert_not_called()
