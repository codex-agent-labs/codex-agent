from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'ci'))
PARENT = (ROOT / '.github/workflows/product-validation.yml').read_text()
CHILD = (ROOT / '.github/workflows/desktop-runtime-evidence.yml').read_text()
SELECT = PARENT.split('      - id: retained-native-source-selection\n', 1)[1].split('      - id: retained-consumer-selection\n', 1)[0]
NATIVE = CHILD.split('  retained-native-source:\n', 1)[1].split('  runtime:\n', 1)[0]


def code(text):
    return textwrap.dedent(text.split("<<'PYCODE'\n", 1)[1].split('\n          PYCODE', 1)[0])


class NativeSourceCallerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'build/ci').mkdir(parents=True)
        self.plan = {'lanes': {'desktop-' + x: {'test': True} for x in ('linux-x64', 'macos-x64', 'windows-x64')}}
        self.rows = [{'lane': 'desktop-' + x, 'build': True, 'test': True, 'metadata': True}
                     for x in ('linux-x64', 'macos-x64', 'windows-x64', 'macos-arm64')]
        self.environment = dict(ORDINARY_MODE='true', AUTHORIZED='true', VALIDATION_REUSED='false',
            NATIVE_READY='true', NATIVE_FULL_REUSE='true', DESKTOP_MATRIX=json.dumps(self.rows),
            ANY_DESKTOP='true', LINUX_ARM64='false')

    def run_code(self, source, env):
        output = self.root / 'output'
        if output.exists():
            output.unlink()
        (self.root / 'build/ci/impact-plan.json').write_text(json.dumps(self.plan))
        old = Path.cwd()
        try:
            os.chdir(self.root)
            with patch.dict(os.environ, {**env, 'GITHUB_OUTPUT': str(output)}, clear=True):
                exec(compile(source, '<exact-workflow-inline>', 'exec'), {})
        finally:
            os.chdir(old)
        return dict(line.split('=', 1) for line in output.read_text().splitlines())

    def test_fixed_three_hosts_no_duplicate_legacy_rows(self):
        result = self.run_code(code(SELECT), self.environment)
        selected = json.loads(result['matrix'])
        self.assertEqual(['linux-x64', 'macos-x64', 'windows-x64'], [r['target'] for r in selected])
        self.assertEqual(['ubuntu-24.04', 'macos-26-intel', 'windows-2025'], [r['runner'] for r in selected])
        self.assertEqual([self.rows[-1]], json.loads(result['legacy_matrix']))
        self.assertFalse({r['lane'] for r in selected} & {r['lane'] for r in json.loads(result['legacy_matrix'])})
        self.plan['lanes']['desktop-linux-x64']['test'] = False
        result = self.run_code(code(SELECT), self.environment)
        self.assertEqual([self.rows[0], self.rows[-1]], json.loads(result['legacy_matrix']))

    def test_disabled_routes_preserve_exact_legacy_and_bad_flags_fail(self):
        for key in ('ORDINARY_MODE', 'AUTHORIZED', 'NATIVE_READY', 'NATIVE_FULL_REUSE', 'VALIDATION_REUSED'):
            for value in ('', 'false' if key != 'VALIDATION_REUSED' else 'true'):
                with self.subTest(key=key, value=value):
                    result = self.run_code(code(SELECT), {**self.environment, key: value})
                    self.assertEqual('[]', result['matrix'])
                    self.assertEqual(self.environment['DESKTOP_MATRIX'], result['legacy_matrix'])
                    self.assertEqual('true', result['any_desktop'])
        with self.assertRaises(ValueError):
            self.run_code(code(SELECT), {**self.environment, 'AUTHORIZED': 'yes'})
        self.plan['lanes']['desktop-linux-x64']['test'] = 'true'
        with self.assertRaises(ValueError):
            self.run_code(code(SELECT), self.environment)

    def test_only_missing_source_validations_reach_workers(self):
        step = code(PARENT.split('      - id: source-validation-originals\n', 1)[1])
        self.plan['validationCommit'] = 'a' * 40
        matrix = self.rows[:2]
        first, second = (row['lane'] for row in matrix)
        swift = 'ios-swift-build'
        env = dict(GITHUB_WORKSPACE=str(self.root), TRUSTED_WORKFLOW_SHA='b' * 40,
                   CODEX_AGENT_COMPLETED_REUSE_POLICY=str(self.root / 'protected.json'),
                   NATIVE_MATRIX=json.dumps(matrix), SWIFT_SELECTED='true')
        for reused, pending, swift_miss in (([], matrix, 'true'), ([first], [matrix[1]], 'true'),
                                            (sorted([first, second, swift]), [], 'false')):
            with self.subTest(reused=reused), patch(
                'ci.sdk_android_evidence_capture.select_source_validation_reuse', return_value=reused
            ) as reader:
                result = self.run_code(step, env)
                self.assertEqual(pending, json.loads(result['matrix']))
                self.assertEqual(swift_miss, result['swift_miss'])
                self.assertEqual(reused, json.loads(result['reused']))
                reader.assert_called_once_with(self.plan, repository_root=self.root, revision='a' * 40,
                    trusted_workflow_sha='b' * 40, completed_frozen_policy=self.root / 'protected.json',
                    native_source_tests=True, apple_source_tests=True)
        with patch('ci.sdk_android_evidence_capture.select_source_validation_reuse', return_value=['desktop-windows-x64']):
            with self.assertRaisesRegex(ValueError, 'selected lanes'):
                self.run_code(step, env)

    def test_exact_resume_locator_rejects_failed_state_wave_or_host(self):
        outputs = dict(full_reuse='true', wave_failed='false', artifact_id='123',
            artifact_digest='sha256:'+'a'*64, state_wave='0', sdk_state_wave='')
        env = dict(RESUME_OUTPUTS=json.dumps(outputs), TARGET='linux-x64', LANE='desktop-linux-x64', HOST_RUNNER='ubuntu-24.04')
        got = self.run_code(code(NATIVE), env)
        self.assertEqual('123', got['artifact_id'])
        self.assertEqual('0', got['state_wave'])
        for field, value in (('full_reuse', 'false'), ('wave_failed', 'true'), ('state_wave', '1'), ('artifact_id', '')):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_code(code(NATIVE), {**env, 'RESUME_OUTPUTS': json.dumps({**outputs, field: value})})
        with self.assertRaises(ValueError):
            self.run_code(code(NATIVE), {**env, 'HOST_RUNNER': 'windows-2025'})

    def test_worker_controls_only_parallel_and_legacy_bodies_preserved(self):
        job = PARENT.split('  retained-native-source:\n', 1)[1].split('  desktop:\n', 1)[0]
        self.assertIn('needs: [workflow-lint, plan, product-resume]', job)
        self.assertIn('!inputs.sdkRecoveryOnly', job)
        self.assertIn('!inputs.fullReuseAcceptanceOnly', job)
        self.assertIn('fail-fast: false', NATIVE)
        self.assertIn('artifact-ids: ${{ inputs.planControlId }}', NATIVE)
        self.assertIn('${CODEX_AGENT_COMPLETED_REUSE_POLICY:?native authority required}', NATIVE)
        self.assertIn('overwrite: false', NATIVE)
        self.assertIn('failure.log', NATIVE)
        self.assertIn("inputs.retainedNativeSource && '-retained-source' || ''", CHILD)
        for forbidden in ('setup-kmp', 'setup-msvc', './gradlew', 'ciProductPhase', 'ci-portable', 'cp -R', 'sdk-completion'):
            self.assertNotIn(forbidden, NATIVE)
        legacy = CHILD.split("  runtime:\n", 1)[1]
        self.assertIn("if: ${{ !inputs.retainedNativeSource && inputs.matrix != '[]' }}", legacy)



if __name__ == '__main__':
    unittest.main()
