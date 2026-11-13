"""Execute fixed routing selectors; these checks do not establish hosted evidence."""

from contextlib import chdir
from itertools import product
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class InstalledConsumerWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.parent = (ROOT / '.github/workflows/product-validation.yml').read_text()
        self.child = (ROOT / '.github/workflows/sdk-consumer-validation.yml').read_text()
        self.apple = (ROOT / '.github/workflows/apple-runtime-evidence.yml').read_text()

    def test_authorized_native_selection_is_exact_and_does_not_change_plan(self):
        step = self.parent.split('      - id: retained-consumer-selection\n', 1)[1].split('      - name:', 1)[0]
        script = textwrap.dedent(step.split("          python3 -B - <<'PYCODE'\n", 1)[1].split('          PYCODE', 1)[0])
        self.assertIn("CONSUMER_MODE: ${{ !inputs.fullReuseAcceptanceOnly && !inputs.runtimeRecoveryOnly && !inputs.toolingOnly }}", step)
        self.assertNotIn('!inputs.sdkRecoveryOnly', step)
        lanes = ('common', 'android', 'desktop', 'node-js', 'node-wasm', 'ios-device', 'ios-simulator')
        with tempfile.TemporaryDirectory() as temporary, chdir(temporary):
            plan = Path('build/ci/impact-plan.json')
            plan.parent.mkdir(parents=True)
            value = {'lanes': {'consumer-' + lane: dict(build=False, test=True, metadata=False) for lane in lanes}}
            plan.write_text(json.dumps(value))
            original = plan.read_bytes()
            output = Path('result')
            keys = ('CONSUMER_MODE', 'AUTHORIZED', 'VALIDATION_REUSED', 'NATIVE_READY', 'NATIVE_FULL_REUSE')
            for flags in product(('true', 'false'), repeat=5):
                with self.subTest(flags=flags), patch.dict(os.environ, dict(zip(keys, flags), GITHUB_OUTPUT=str(output))):
                    output.unlink(missing_ok=True)
                    exec(compile(script, 'saved-consumer-selector', 'exec'), {})
                    result = dict(line.split('=', 1) for line in output.read_text().splitlines())
                    expected = flags == ('true', 'true', 'false', 'true', 'true')
                    self.assertEqual(str(expected).lower(), result['enabled'])
                    matrix = json.loads(result['matrix'])
                    self.assertEqual({'consumer-' + lane for lane in lanes} if expected else set(), {row['lane'] for row in matrix})
                    for row in matrix:
                        self.assertEqual(dict(build=False, test=True, metadata=False), {key: row[key] for key in ('build', 'test', 'metadata')})
                    self.assertEqual(original, plan.read_bytes())
            with patch.dict(os.environ, dict(zip(keys, ('true', 'true', 'false', 'bad', 'true')), GITHUB_OUTPUT=str(output))):
                with self.assertRaises(ValueError):
                    exec(compile(script, 'saved-consumer-selector', 'exec'), {})
            for lane in value['lanes'].values():
                lane['test'] = False
            plan.write_text(json.dumps(value))
            with patch.dict(os.environ, dict(zip(keys, ('true', 'true', 'false', 'true', 'true')), GITHUB_OUTPUT=str(output))):
                output.unlink()
                exec(compile(script, 'saved-consumer-selector', 'exec'), {})
                self.assertEqual('enabled=false\nmatrix=[]\n', output.read_text())

    def test_consumers_start_from_early_state_and_forward_only_controls(self):
        early = self.parent.split('\n  retained-consumers:\n', 1)[1].split('\n  sdk-ios-binary-plan:', 1)[0]
        self.assertIn('needs: [workflow-lint, plan, product-resume]', early)
        self.assertIn("needs.product-resume.result == 'success'", early)
        self.assertIn('sdkOutputs: ${{ toJSON(needs.product-resume.outputs) }}', early)
        self.assertNotIn('sdk-completion', early)
        worker = self.child.split('\n  installed-consumer:\n', 1)[1]
        self.assertIn('name: ${{ matrix.lane }}', worker)
        self.assertIn('fail-fast: false', worker)
        self.assertIn("CODEX_AGENT_THROUGHPUT_TRACE: '1'", worker)
        self.assertIn('restore-reuse-qualification@reuse-authority', worker)
        self.assertIn('--completed-frozen-policy "${CODEX_AGENT_COMPLETED_REUSE_POLICY:?native authority required}"', worker)
        self.assertIn('--installed-consumer "$LANE"', worker)
        self.assertIn('--installed-consumer-output "$RUNNER_TEMP/installed-consumer-controls"', worker)
        self.assertIn('path: ${{ runner.temp }}/installed-consumer-controls', worker)
        self.assertIn('overwrite: false', worker)
        for obsolete in ('run-ci-lane', 'ci/stage.py', 'codex-agent-ci-', 'desktop-classifiers', 'rust-toolchain'):
            self.assertNotIn(obsolete, worker)
        self.assertIn("if: ${{ !inputs.retainedInstalledConsumers }}", self.child)

    def test_apple_selection_preserves_every_nonconsumer_duty(self):
        step = self.apple.split('      - id: lanes\n', 1)[1].split('\n  native-tests:', 1)[0]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1])
        # Capture only the selector's arguments; no source test or Gradle runs.
        script = 'python3() { printf "%s\\n" "$@"; }\n' + script
        results = {}
        for binary, retained in product(('true', 'false'), repeat=2):
            env = dict(os.environ, SDK_BINARY_ONLY=binary, RETAINED_CONSUMERS=retained, GITHUB_OUTPUT='/unused')
            result = subprocess.run(['bash', '-e', '-c', script], env=env, text=True, capture_output=True, check=True)
            args = result.stdout.splitlines()
            results[binary, retained] = {args[i + 1] for i, arg in enumerate(args) if arg == '--lane'}
        consumers = {'consumer-common', 'consumer-ios-device', 'consumer-ios-simulator'}
        self.assertEqual(consumers, results['false', 'false'] - results['false', 'true'])
        self.assertEqual(results['true', 'false'], results['true', 'true'])
        self.assertEqual({'ios-native-tests', 'ios-rust-device', 'ios-rust-simulator'}, results['true', 'true'])

    def test_merge_requires_actual_consumers_and_never_stages_legacy_authority(self):
        gate = self.parent.split('\n  merge-gate:\n', 1)[1]
        needs = re.search(r'^    needs: \[(.*)\]$', gate, re.M)[1].split(', ')
        self.assertIn('retained-consumers', needs)
        self.assertIn('test "$RETAINED_CONSUMERS_RESULT" = success || exit 1', gate)
        self.assertIn("installed_consumers=os.environ['RETAINED_CONSUMERS'] == 'true'", gate)
        for name in ('Require an exact receipt set', 'Stage the exact reusable validation artifact'):
            condition = gate.split('      - name: ' + name + '\n', 1)[1].splitlines()[0]
            self.assertIn("needs.plan.outputs.retained_consumers != 'true'", condition)
        completion = self.parent.split('\n  sdk-completion:\n', 1)[1].split('\n  sdk-completion-full-reuse:', 1)[0]
        self.assertIn('tooling+=(--include-installed-consumers)', completion)
        self.assertEqual(1, completion.count('--validation-contribution-directory'))


if __name__ == '__main__':
    unittest.main()
