"""The nested failed-wave locator selects only exact official collector uploads."""

from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from ci import sdk_nested_wave_locator as locator


_PRODUCER = {"repository": "codex-agent-labs/codex-agent",
    "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40,
    "tree": "b" * 40, "event": "pull_request", "runId": 7,
    "runAttempt": 2, "pullRequest": 31}
_SHA = "c" * 40
_PIN = {"artifact_id": 901, "artifact_sha256": "sha256:" + "d" * 64}


class NestedSdkWaveLocatorTest(TestCase):
    def test_routes_match_nested_workflow_sources(self):
        workflows = Path(__file__).resolve().parents[2] / ".github/workflows"
        parent = (workflows / "product-validation.yml").read_text()
        for wave, (workflow, caller) in locator._COLLECTORS.items():
            with self.subTest(wave=wave):
                child = (workflows / f"{workflow}.yml").read_text()
                self.assertIn(f"  sdk-collect-{wave}:\n", child)
                self.assertIn(f"wave: '{wave}'", child)
                self.assertIn(f"  {caller}:\n", parent)
                self.assertIn(f"uses: ./.github/workflows/{workflow}.yml", parent)

    def test_all_nested_waves_have_exact_child_routes_and_upload_names(self):
        for wave, (workflow, parent) in locator._COLLECTORS.items():
            with self.subTest(wave=wave), \
                    patch.object(locator.products, "_observe_ci_producer_jobs",
                        return_value=[{"run": {"status": "completed", "conclusion": "failure"}}]) as observe, \
                    patch.object(locator, "_locate", return_value=_PIN) as find:
                self.assertEqual(_PIN, locator.locate_failed_nested_sdk_wave(
                    _PRODUCER, wave=wave, trusted_workflow_sha=_SHA,
                    token="test-token", environ={}))
                job = f"product-validation / {parent} / sdk-collect-{wave}"
                policy = {"collector": {"path": f".github/workflows/{workflow}.yml", "sha": _SHA}}
                observe.assert_called_once_with({"collector": _PRODUCER},
                    jobs_by_phase={"collector": job}, trusted_workflows_by_phase=policy,
                    token="test-token")
                find.assert_called_once_with(_PRODUCER, phase="collector", job=job,
                    name=f"codex-agent-sdk-wave-{wave}-state-{'b' * 40}-attempt-2",
                    token="test-token", trusted_workflows_by_phase=policy)

    def test_rejects_nonfailed_and_unpinned_selections_before_artifact_lookup(self):
        for wave, producer, result, message in (
            (10, _PRODUCER, "failure", "Unknown nested"),
            (19, _PRODUCER, "failure", "Unknown nested"),
            (True, _PRODUCER, "failure", "Unknown nested"),
            (11, {**_PRODUCER, "event": "merge_group", "pullRequest": None}, "failure", "PR producer"),
            (11, _PRODUCER, "success", "completed failed"),
            (11, _PRODUCER, None, "completed failed"),
        ):
            with self.subTest(wave=wave, result=result), \
                    patch.object(locator.products, "_observe_ci_producer_jobs",
                        return_value=[{"run": {"status": "completed", "conclusion": result}}]), \
                    patch.object(locator, "_locate") as find, \
                    self.assertRaisesRegex(ValueError, message):
                locator.locate_failed_nested_sdk_wave(producer, wave=wave,
                    trusted_workflow_sha=_SHA, token="test-token", environ={})
                find.assert_not_called()

    def test_signing_secret_is_rejected_before_official_observation(self):
        with patch.object(locator.products, "_observe_ci_producer_jobs") as observe, \
                self.assertRaisesRegex(ValueError, "signing-secret"):
            locator.locate_failed_nested_sdk_wave(_PRODUCER, wave=11,
                trusted_workflow_sha=_SHA, token="test-token",
                environ={"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "secret"})
        observe.assert_not_called()
