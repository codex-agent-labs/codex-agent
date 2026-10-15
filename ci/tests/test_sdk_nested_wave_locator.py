"""The nested failed-wave locator selects only exact official collector uploads."""

from pathlib import Path
import subprocess
import sys
from unittest import TestCase
from unittest.mock import patch

from ci import sdk_nested_wave_locator as locator


_PRODUCER = {"repository": "codex-agent-labs/codex-agent",
    "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40,
    "tree": "b" * 40, "event": "pull_request", "runId": 7,
    "runAttempt": 2, "pullRequest": 31}
_SHA = "c" * 40
_PIN = {"artifact_id": 901, "artifact_sha256": "sha256:" + "d" * 64}
_CURRENT = {"GITHUB_REPOSITORY": _PRODUCER["repository"],
    "GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"}


class NestedSdkWaveLocatorTest(TestCase):
    def test_direct_script_reference_reader_reaches_original_authentication(self):
        # Hosted issuers run ci/reuse_qualification.py, without the checkout
        # root on sys.path. Exercise the actual nested transport branch.
        script = '''
import sys
sys.path.insert(0, sys.argv[1])
import reuse_qualification
import product_reuse as products
from pathlib import Path
from unittest.mock import patch
class ReachedOriginalGate(Exception):
    pass
with patch.object(products, '_observe_ci_producer_jobs', side_effect=ReachedOriginalGate) as observe:
    try:
        products._capture_runtime_reference_members({}, b'plan',
            {'tree': 'a' * 40, 'runAttempt': 1},
            {'stateWave': 0, 'sdkStateWave': 11}, Path('unused'),
            trusted_workflow_sha='b' * 40, token='fixture', wanted={})
    except ReachedOriginalGate:
        pass
    else:
        raise AssertionError('Original authentication was not reached')
    assert observe.call_args.kwargs['jobs_by_phase'] == {
        'resume': 'product-validation / sdk-core-binary-wave / sdk-collect-11'}
    assert observe.call_args.kwargs['trusted_workflows_by_phase'] == {'resume': {
        'path': '.github/workflows/sdk-core-binary-validation.yml', 'sha': 'b' * 40}}
assert 'ci' not in sys.modules
'''
        subprocess.run([sys.executable, '-I', '-B', '-c', script,
                        str(Path(__file__).resolve().parents[1])], check=True,
                       capture_output=True, text=True)

    def test_all_top_level_checkpoints_retain_successful_collectors_after_cancellation(self):
        for wave in (*range(1, 11), 19):
            with self.subTest(wave=wave), \
                    patch.object(locator.products, '_observe_ci_producer_jobs',
                        return_value=[{'run': {'status': 'completed', 'conclusion': 'cancelled'}}]) as observe, \
                    patch.object(locator, '_locate', return_value=_PIN) as locate:
                self.assertEqual(_PIN, locator.locate_failed_sdk_wave(_PRODUCER, wave=wave,
                    trusted_workflow_sha=_SHA, token='fixture', environ={}))
                self.assertEqual({'collector': f'product-validation / sdk-collect-{wave}'},
                                 observe.call_args.kwargs['jobs_by_phase'])
                self.assertEqual('.github/workflows/product-validation.yml',
                    locate.call_args.kwargs['trusted_workflows_by_phase']['collector']['path'])

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

    def test_current_run_accepts_in_progress_only_after_successful_child_observation(self):
        for wave in range(11, 17):
            with self.subTest(wave=wave), \
                    patch.object(locator.products, "_observe_ci_producer_jobs",
                        return_value=[{"run": {"status": "in_progress"}}]) as observe, \
                    patch.object(locator, "_locate", return_value=_PIN) as find:
                self.assertEqual(_PIN, locator.locate_current_failed_nested_sdk_wave(
                    _PRODUCER, wave=wave, trusted_workflow_sha=_SHA,
                    token="test-token", environ=_CURRENT))
                workflow, parent = locator._COLLECTORS[wave]
                job = f"product-validation / {parent} / sdk-collect-{wave}"
                policy = {"collector": {"path": f".github/workflows/{workflow}.yml",
                    "sha": _SHA}}
                observe.assert_called_once_with({"collector": _PRODUCER},
                    jobs_by_phase={"collector": job}, trusted_workflows_by_phase=policy,
                    token="test-token")
                find.assert_called_once_with(_PRODUCER, phase="collector", job=job,
                    name=f"codex-agent-sdk-wave-{wave}-state-{'b' * 40}-attempt-2",
                    token="test-token", trusted_workflows_by_phase=policy)

    def test_current_run_rejects_wrong_context_or_run_status_before_lookup(self):
        for env, status, conclusion in (
            ({**_CURRENT, "GITHUB_RUN_ID": "8"}, "in_progress", None),
            (_CURRENT, "queued", None),
            (_CURRENT, "in_progress", "failure"),
            (_CURRENT, "completed", "success"),
        ):
            with self.subTest(env=env, status=status), \
                    patch.object(locator.products, "_observe_ci_producer_jobs",
                        return_value=[{"run": {"status": status,
                            "conclusion": conclusion}}]) as observe, \
                    patch.object(locator, "_locate") as find, \
                    self.assertRaises(ValueError):
                locator.locate_current_failed_nested_sdk_wave(_PRODUCER, wave=11,
                    trusted_workflow_sha=_SHA, token="test-token", environ=env)
                find.assert_not_called()
            if env != _CURRENT:
                observe.assert_not_called()

    def test_current_locator_keeps_completed_failed_route_separate(self):
        with patch.object(locator.products, "_observe_ci_producer_jobs",
                return_value=[{"run": {"status": "completed",
                    "conclusion": "failure"}}]), \
                patch.object(locator, "_locate", return_value=_PIN):
            self.assertEqual(_PIN, locator.locate_current_failed_nested_sdk_wave(
                _PRODUCER, wave=16, trusted_workflow_sha=_SHA,
                token="test-token", environ=_CURRENT))
        with patch.object(locator.products, "_observe_ci_producer_jobs") as observe, \
                self.assertRaisesRegex(ValueError, "Unknown current"):
            locator.locate_current_failed_nested_sdk_wave(_PRODUCER, wave=17,
                trusted_workflow_sha=_SHA, token="test-token", environ=_CURRENT)
        observe.assert_not_called()
