"""Saved wave-10 workflow routing; no hosted execution or full-gate claim."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_apple_validation_workflow as apple_fixture
from ci.tests import test_sdk_completion_workflow as completion_fixture


JOBS = ('sdk-ios-metadata-plan', 'sdk-ios-metadata', 'sdk-collect-10', 'sdk-ios-metadata-result')
PARENT = 'sdk-ios-validation-result'


class SdkIosMetadataWorkflowTest(unittest.TestCase):
    def setUp(self):
        fixture = apple_fixture.SdkAppleValidationWorkflowTest(methodName='runTest')
        fixture.setUp()
        self.job, self.needs, self.condition = fixture.job, fixture.needs, fixture.condition
        completion = completion_fixture.SdkCompletionWorkflowTest(methodName='runTest')
        completion.setUp()
        self.completion_job = completion.job

    def test_authorization_precedes_runner_expansion_without_new_signing(self):
        for name in JOBS:
            with self.subTest(job=name):
                job = self.job(name)
                for expected in ('always()', "needs.plan.outputs.event_authorized == 'true'",
                                 "needs.plan.outputs.remote_build_authorized == 'true'"):
                    self.assertIn(expected, self.condition(job))
                for forbidden in ('secrets.', 'PRIVATE_KEY', 'environment: product-attestation',
                                  'attest-sdk-apple', 'prepare-sdk-apple-signing', 'release_cli sign',
                                  'sdk-apple-signing-prepare', 'sdk-apple-validation-attestation'):
                    self.assertNotIn(forbidden, job)
        worker = self.job('sdk-ios-metadata')
        self.assertLess(worker.index('    if:'), worker.index('    strategy:'))
        self.assertIn('fail-fast: false', worker)
        self.assertIn('matrix: ${{ fromJSON(needs.sdk-ios-metadata-plan.outputs.sdk_matrix || \'{"include":[]}\') }}', worker)
        self.assertIn('runs-on: ${{ matrix.runner }}', worker)
        self.assertIn('name: sdk-sdk-ios-metadata-${{ matrix.target }}', worker)
        for expected in ("needs.sdk-ios-metadata-plan.result == 'success'",
                         "needs.sdk-ios-metadata-plan.outputs.sdk_workers_required == 'true'"):
            self.assertIn(expected, self.condition(worker))

    def test_election_no_tooling_paths_skip_only_provisioning_not_replay(self):
        job = self.job('sdk-ios-metadata-plan')
        self.assertNotIn('tooling_required', self.condition(job))
        steps = re.split(r'\n      - ', job)[1:]
        for marker in ('name: Select installed caller Java', 'id: tooling\n',
                       'uses: actions/download-artifact@', 'id: apple-policy\n'):
            selected = [step for step in steps if marker in step]
            with self.subTest(step=marker):
                self.assertEqual(1, len(selected))
                self.assertEqual(["needs.plan.outputs.tooling_required == 'true'"],
                                 re.findall(r'(?m)^        if: (.+)$', selected[0]))
        self.assertEqual(4, job.count("if: needs.plan.outputs.tooling_required == 'true'"))
        capture = next(step for step in steps if step.startswith('id: capture\n'))
        self.assertNotRegex(capture, r'(?m)^        if:')
        self.assertIn('sdk-family: ios-metadata', capture)

    def test_all_replay_routes_preserve_parent_and_construct_policy_first(self):
        for name, action in (('sdk-ios-metadata-plan', 'capture-runtime-state'),
                             ('sdk-ios-metadata', 'sdk-ios-metadata-worker'),
                             ('sdk-collect-10', 'collect-runtime-wave')):
            with self.subTest(job=name):
                job = self.job(name)
                self.assertIn(PARENT, self.needs(job))
                self.assertIn('sdk-plan', self.needs(job))
                block = job.split('uses: ./.github/actions/' + action, 1)[1].split('\n      - ', 1)[0]
                for field, output in (('artifact-id', 'artifact_id'), ('artifact-sha256', 'artifact_digest'),
                                      ('state-wave', 'state_wave'), ('sdk-state-wave', 'sdk_state_wave')):
                    self.assertIn(field + ': ${{ needs.' + PARENT + '.outputs.' + output + ' }}', block)
                for expected in ('plan-id: ${{ needs.plan.outputs.plan_id }}',
                                 'sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}',
                                 'sdk-apple-validation-policy: ${{ steps.apple-policy.outputs.apple-policy }}',
                                 'trusted-workflow-sha: ${{ inputs.trustedWorkflowSha }}'):
                    self.assertIn(expected, block)
                self.assertLess(job.index('uses: ./.github/actions/capture-sdk-tooling'),
                                job.index('uses: actions/download-artifact@'))
                self.assertLess(job.index('uses: actions/download-artifact@'),
                                job.index('uses: ./.github/actions/prepare-sdk-apple-policy'))
                self.assertLess(job.index('uses: ./.github/actions/prepare-sdk-apple-policy'),
                                job.index('uses: ./.github/actions/' + action))
                self.assertIn('plan-path: ${{ runner.temp }}/sdk-apple-plan/impact-plan.json', job)
                self.assertIn('tooling-policy: ${{ steps.tooling.outputs.tooling-policy }}', job)
                if name != 'sdk-ios-metadata':
                    self.assertIn('product: sdk', block)
                    self.assertIn('sdk-family: ios-metadata', block)
                else:
                    self.assertIn('build-key: ${{ matrix.buildKey }}', block)
                    self.assertIn('tree: ${{ needs.plan.outputs.validation_tree }}', block)

    def test_collection_waits_for_failed_worker_and_preserves_exact_wave(self):
        job = self.job('sdk-collect-10')
        self.assertEqual({'plan', 'sdk-plan', PARENT, 'sdk-ios-metadata-plan', 'sdk-ios-metadata'}, self.needs(job))
        condition = self.condition(job)
        self.assertIn('always()', condition)
        self.assertIn("needs.sdk-ios-metadata-plan.outputs.sdk_workers_required == 'true'", condition)
        self.assertNotIn('needs.sdk-ios-metadata.result', condition)
        self.assertIn("wave: '10'", job)
        for name, value in (('artifact_id', 'artifact-id'), ('artifact_digest', 'artifact-sha256'),
                            ('wave_failed', 'wave-failed')):
            self.assertIn(name + ': ${{ steps.collect.outputs.' + value + ' }}', job)

    def test_saved_terminal_executes_real_selector_and_never_publishes_failure(self):
        job = self.job('sdk-ios-metadata-result')
        names = {'plan', PARENT, 'sdk-ios-metadata-plan', 'sdk-ios-metadata', 'sdk-collect-10'}
        self.assertEqual(names, self.needs(job))
        self.assertNotIn('sdk_workers_required', self.condition(job))
        match = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", job)
        self.assertIsNotNone(match)
        script = textwrap.dedent(match[1])
        self.assertIn("stage='ios-metadata'", script)
        parent = dict(artifact_id='99', artifact_digest='sha256:' + 'a' * 64, state_wave='0', sdk_state_wave='9')
        final = dict(artifact_id='110', artifact_digest='sha256:' + 'b' * 64, state_wave='0', sdk_state_wave='10')
        def selected(required):
            return {'plan': {'result': 'success', 'outputs': {}},
                PARENT: {'result': 'success', 'outputs': deepcopy(parent)},
                'sdk-ios-metadata-plan': {'result': 'success', 'outputs': {'sdk_workers_required': str(required).lower()}},
                'sdk-ios-metadata': {'result': 'success' if required else 'skipped', 'outputs': {}},
                'sdk-collect-10': {'result': 'success' if required else 'skipped',
                    'outputs': {**final, 'wave_failed': 'false'} if required else {}}}
        cases = [(selected(False), parent), (selected(True), final)]
        for name in (PARENT, 'sdk-ios-metadata-plan', 'sdk-ios-metadata', 'sdk-collect-10'):
            value = selected(True)
            value[name]['result'] = 'failure'
            cases.append((value, None))
        value = selected(True)
        value['sdk-collect-10']['outputs']['wave_failed'] = 'true'
        cases.append((value, None))
        value = selected(False)
        value[PARENT]['outputs'] = {}
        value['sdk-ios-metadata-plan'] = {'result': 'skipped', 'outputs': {}}
        cases.append((value, dict.fromkeys(parent, '')))
        for needs, expected in cases:
            before = deepcopy(needs)
            with self.subTest(needs=needs), tempfile.TemporaryDirectory(prefix='metadata-terminal-') as temporary:
                output = Path(temporary) / 'output'
                with patch.dict(os.environ, {'RESULTS': json.dumps(needs), 'GITHUB_OUTPUT': str(output)}, clear=True):
                    if expected is None:
                        with self.assertRaises(ValueError):
                            exec(compile(script, '<saved-ios-metadata-terminal>', 'exec'), {})
                        self.assertFalse(output.exists())
                    else:
                        exec(compile(script, '<saved-ios-metadata-terminal>', 'exec'), {})
                        self.assertEqual(expected, dict(line.split('=', 1) for line in output.read_text().splitlines()))
                self.assertEqual(before, needs)

    def test_completion_requires_metadata_terminal_and_still_runs_full_sdk_check(self):
        completion = self.completion_job('sdk-completion')
        self.assertTrue({'sdk-native-result', PARENT, 'sdk-ios-metadata-result'} <= self.needs(completion))
        self.assertIn('RESULTS: ${{ toJSON(needs) }}', completion)
        self.assertIn('select_sdk_completion_state', completion)
        self.assertIn('python3 -B -m ci.sdk_completion --plan "$PLAN"', completion)
        self.assertIn('sdk-apple-validation-policy:', completion)
        self.assertNotIn('sdk_workers_required', self.condition(completion))
        self.assertIn('sdk-completion', self.needs(self.job('merge-gate')))


if __name__ == '__main__':
    unittest.main()
