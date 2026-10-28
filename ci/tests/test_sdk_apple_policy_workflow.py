"""Caller-policy routing only; stub processes do not authenticate hosted state."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


class SdkApplePolicyWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / '.github/workflows/product-validation.yml').read_text()
        cls.jobs = dict(re.findall(r'^  ([a-z][a-z0-9-]*):\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)',
                                  source, re.M | re.S))
        child = (ROOT / '.github/workflows/contract-validation.yml').read_text()
        cls.jobs.update(re.findall(r'^  ([a-z][a-z0-9-]*):\n(.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)',
                                   child, re.M | re.S))

    @staticmethod
    def steps(job):
        return re.split(r'(?=^      - )', job, flags=re.M)[1:]

    def policy_output(self, job):
        return ('steps.apple-policy.outputs.apple-policy' if
                'uses: ./.github/actions/prepare-sdk-apple-policy' in job else
                'steps.tooling.outputs.apple-policy')

    def test_every_tooling_capture_constructs_policy_locally_before_replay(self):
        count = 0
        for name, job in self.jobs.items():
            for step in self.steps(job):
                if 'uses: ./.github/actions/capture-sdk-tooling' not in step:
                    continue
                count += 1
                with self.subTest(job=name):
                    self.assertIn('- id: tooling', step)
                    explicit = [part for part in self.steps(job)
                                if 'uses: ./.github/actions/prepare-sdk-apple-policy' in part]
                    if explicit:
                        self.assertEqual(1, len(explicit))
                        self.assertLess(job.index(step), job.index(explicit[0]))
                        self.assertIn('tooling-policy: ${{ steps.tooling.outputs.tooling-policy }}', explicit[0])
                        self.assertIn('plan-path:', explicit[0])
                    else:
                        self.assertTrue(
                            'plan-id: ${{ needs.plan.outputs.plan_id }}' in step or
                            'plan-id: ${{ fromJSON(inputs.planOutputs).plan_id }}' in step)
                    header = job.split('    steps:', 1)[0]
                    self.assertNotIn('outputs.apple-policy', header)
        self.assertGreaterEqual(count, 40)

    def test_every_state_and_worker_action_receives_supported_local_policy(self):
        count = 0
        for name, job in self.jobs.items():
            for step in self.steps(job):
                use = re.search(r'uses: (\./\.github/actions/[^\s]+)', step)
                if not use:
                    continue
                action = (ROOT / use[1] / 'action.yml').read_text()
                if 'inputs:\n' not in action:
                    continue
                inputs = action.split('inputs:\n', 1)[1].split('\nruns:', 1)[0]
                if not re.search(r'^  sdk-validation-tooling:', inputs, re.M):
                    continue
                count += 1
                with self.subTest(job=name, action=use[1]):
                    self.assertRegex(inputs, r'(?m)^  sdk-apple-validation-policy:')
                    self.assertIn('sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}', step)
                    self.assertIn('sdk-apple-validation-policy: ${{ ' + self.policy_output(job) + ' }}', step)
                    self.assertLess(job.index('uses: ./.github/actions/capture-sdk-tooling'), job.index(step))
                    if 'steps.apple-policy.outputs.apple-policy' == self.policy_output(job):
                        self.assertLess(job.index('uses: ./.github/actions/prepare-sdk-apple-policy'), job.index(step))
        self.assertGreaterEqual(count, 30)

    def test_all_inline_original_state_replay_routes_forward_policy(self):
        # Initial discovery owns acquisition itself. Transport-only capture,
        # Contract-only materialization and detached variant trust are not replay.
        replay = re.compile(r'python3[^\n]*(?:'
            r'ci/product_reuse\.py (?:advance-contract|resume-products|execute-runtime-[a-z-]+)|'
            r'ci/runtime_workflow\.py (?:matrix|continuation)|'
            r'-m ci\.sdk_workflow --plan\b|'
            r'-m ci\.sdk_completion\b)')
        count = 0
        for name, job in self.jobs.items():
            for step in self.steps(job):
                if not replay.search(step) and 'inspected = inspect_products(' not in step:
                    continue
                count += 1
                with self.subTest(job=name, step=step.splitlines()[0]):
                    self.assertIn('SDK_APPLE_VALIDATION_POLICY: ${{ ' + self.policy_output(job) + ' }}', step)
                    if 'inspected = inspect_products(' in step:
                        self.assertIn("tooling['sdk_apple_validation_policy'] = _canonical_control(", step)
                        self.assertIn('environ=os.environ,', step)
                        self.assertIn("sdk_original_workflow_sha=os.environ['TRUSTED_WORKFLOW_SHA'], **tooling)", step)
                    else:
                        self.assertIn('--sdk-apple-validation-policy "$SDK_APPLE_VALIDATION_POLICY"', step)
                        self.assertIn('${tooling[@]+"${tooling[@]}"}', step)
        self.assertGreaterEqual(count, 12)

    def test_representative_shells_preserve_optional_arguments_and_child_failure(self):
        selected = []
        for name, command in (('contract-continuation', 'ci/product_reuse.py advance-contract'),
                              ('product-resume', 'ci/product_reuse.py resume-products'),
                              ('product-resume', 'ci/runtime_workflow.py matrix'),
                              ('runtime-continuation', 'ci/runtime_workflow.py continuation'),
                              ('runtime-aggregate', 'ci/product_reuse.py execute-runtime-aggregate'),
                              ('sdk-inputs', '-m ci.sdk_workflow --plan'),
                              ('sdk-completion', '-m ci.sdk_completion --plan')):
            step = next(step for step in self.steps(self.jobs[name]) if command in step)
            selected.append((name, textwrap.dedent(step.split('        run: |\n', 1)[1])
                             .replace('${{ inputs.trustedWorkflowSha }}', 'fixture-caller-workflow-sha')))
        with tempfile.TemporaryDirectory(prefix='apple-policy-workflow-') as temporary:
            root = Path(temporary)
            stub = root / 'python3'
            stub.write_text('#!/bin/sh\nprintf \'%s\\0\' "$@" > "$RECORDED_ARGS"\nexit "$CHILD_STATUS"\n')
            stub.chmod(0o700)
            for name, script in selected:
                for policy in ('', '/caller policies/apple validation.json'):
                    for status in (0, 17):
                        with self.subTest(job=name, policy=policy, status=status):
                            recorded, output = root / 'argv', root / 'output'
                            output.unlink(missing_ok=True)
                            environment = {key: '/original inputs/' + key for key in
                                ('PLAN', 'DISCOVERY', 'STATE', 'DISCOVERY_ROOT', 'STATE_ROOT')}
                            environment.update(PATH=str(root), RECORDED_ARGS=str(recorded), CHILD_STATUS=str(status),
                                GITHUB_OUTPUT=str(output), GITHUB_WORKSPACE=str(root / 'checkout'),
                                SDK_SOURCE='released-default', SDK_VALIDATION_TOOLING='/caller policies/tooling.json',
                                SDK_APPLE_VALIDATION_POLICY=policy, BUILD_KEY='sha256:' + 'a' * 64,
                                TRUSTED_WORKFLOW_SHA='fixture-caller-workflow-sha')
                            completed = subprocess.run([shutil.which('bash'), '-e', '-c', script], env=environment,
                                                       capture_output=True, text=True, cwd=root)
                            self.assertEqual(status, completed.returncode, completed.stderr)
                            arguments = recorded.read_bytes().decode().split('\0')[:-1]
                            self.assertEqual(1, arguments.count('--sdk-validation-tooling'))
                            self.assertEqual('/caller policies/tooling.json', arguments[arguments.index('--sdk-validation-tooling') + 1])
                            self.assertEqual(bool(policy), '--sdk-apple-validation-policy' in arguments)
                            if policy:
                                self.assertEqual(1, arguments.count('--sdk-apple-validation-policy'))
                                self.assertEqual(policy, arguments[arguments.index('--sdk-apple-validation-policy') + 1])
                            if status:
                                self.assertFalse(output.exists())

    def test_native_preparation_inspection_parses_only_current_caller_policy(self):
        # Real canonical reader, mocked replay boundary: not source/evidence admission.
        if str(ROOT / 'ci') not in sys.path:
            sys.path.insert(0, str(ROOT / 'ci'))
        from ci import product_reuse, reuse
        from ci.products.inventory import canonical_json_bytes
        step = next(step for step in self.steps(self.jobs['sdk-native-plan'])
                    if 'inspected = inspect_products(' in step)
        script = textwrap.dedent(step.split("          python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0])
        with tempfile.TemporaryDirectory(prefix='apple-policy-inspection-') as temporary:
            root = Path(temporary).resolve(strict=True)
            policy_path = root / 'caller apple policy.json'
            policy = {'fixture': 'caller policy forwarded, semantic replay explicitly mocked'}
            policy_path.write_bytes(canonical_json_bytes(policy))
            for selected in ('', str(policy_path)):
                environment = {key: str(root / key) for key in ('PLAN', 'DISCOVERY', 'STATE', 'GITHUB_OUTPUT')}
                environment.update(SDK_VALIDATION_TOOLING='', SDK_APPLE_VALIDATION_POLICY=selected,
                                   TRUSTED_WORKFLOW_SHA='fixture-caller-workflow-sha')
                with self.subTest(policy=selected), patch.dict(os.environ, environment, clear=True), \
                        patch.object(product_reuse, 'inspect_products', return_value={'readyPlans': []}) as inspect, \
                        patch.object(reuse, 'github_output'), patch.object(Path, 'cwd', return_value=ROOT):
                    exec(compile(script, '<native-preparation-policy>', 'exec'), {})
                if selected:
                    self.assertEqual(policy, inspect.call_args.kwargs['sdk_apple_validation_policy'])
                else:
                    self.assertNotIn('sdk_apple_validation_policy', inspect.call_args.kwargs)
                self.assertEqual('fixture-caller-workflow-sha',
                                 inspect.call_args.kwargs['sdk_original_workflow_sha'])
                self.assertEqual(canonical_json_bytes(policy), policy_path.read_bytes())


if __name__ == '__main__':
    unittest.main()
