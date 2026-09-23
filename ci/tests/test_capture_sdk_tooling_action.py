"""Executed capture-action composition; authenticated upload gate is mocked."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[2]


class CaptureSdkToolingActionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='capture-sdk-tooling-action-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / 'checkout'
        self.repository.mkdir()
        self.original = self.repository / 'original-source'
        self.original.write_bytes(b'original checkout bytes')
        self.scratch = self.root / 'runner-temp'
        self.scratch.mkdir()
        self.java_home = self.root / 'java home'
        self.java = self.java_home / 'bin' / ('java.exe' if os.name == 'nt' else 'java')
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b'caller installed Java')
        self.output = self.root / 'github-output'
        self.producer = {'repository': 'codex-agent-labs/codex-agent', 'workflowPath': '.github/workflows/ci.yml',
            'commit': 'a' * 40, 'tree': 'b' * 40, 'event': 'pull_request', 'runId': 71, 'runAttempt': 2, 'pullRequest': 31}
        self.environment = {'GITHUB_WORKSPACE': str(self.repository), 'JAVA_HOME': str(self.java_home),
            'RUNNER_TEMP': str(self.scratch), 'GITHUB_OUTPUT': str(self.output), 'GITHUB_TOKEN': 'caller-token',
            'ARTIFACT_ID': '91', 'ARTIFACT_SHA256': 'sha256:' + 'c' * 64,
            'TRANSPORT_PRODUCER': json.dumps(self.producer, indent=2),
            'TRUSTED_WORKFLOW_SHA': 'd' * 40, 'POLICY_REVISION': 'e' * 40}
        self.action = (ROOT / '.github/actions/capture-sdk-tooling/action.yml').read_text()

    def execute(self):
        code = self.action.split("        python3 -B - <<'PY'\n", 1)[1].split('\n        PY', 1)[0]
        with patch.dict(os.environ, self.environment, clear=True):
            exec(compile(textwrap.dedent(code), '<capture-sdk-tooling-action>', 'exec'), {})

    def capture(self, command, **kwargs):
        self.assertEqual([sys.executable, '-B', '-m', 'ci.tooling_capture'], command[:4])
        fields = dict(zip(command[4::2], command[5::2]))
        self.assertEqual({'--destination', '--repository-root', '--transport-producer', '--java-executable',
            '--artifact-id', '--artifact-sha256', '--trusted-workflow-sha', '--policy-revision'}, set(fields))
        self.assertEqual(str(self.repository), fields['--repository-root'])
        self.assertEqual(str(self.java.resolve()), fields['--java-executable'])
        for flag, variable in (('artifact-id', 'ARTIFACT_ID'), ('artifact-sha256', 'ARTIFACT_SHA256'),
                               ('trusted-workflow-sha', 'TRUSTED_WORKFLOW_SHA'), ('policy-revision', 'POLICY_REVISION')):
            self.assertEqual(self.environment[variable], fields['--' + flag])
        producer = Path(fields['--transport-producer'])
        destination = Path(fields['--destination'])
        self.assertEqual(producer.parent, destination.parent)
        self.assertTrue(destination.is_relative_to(self.scratch))
        self.assertFalse(destination.is_relative_to(self.repository))
        self.assertFalse(destination.exists())
        self.assertEqual(canonical_json_bytes(self.producer), producer.read_bytes())
        self.assertEqual(self.repository, kwargs['cwd'])
        self.assertEqual('caller-token', kwargs['env']['GITHUB_TOKEN'])
        self.assertTrue(kwargs['check'])
        self.assertNotIn('shell', kwargs)
        destination.mkdir()
        (destination / 'tooling-policy.json').write_bytes(b'{"mocked":"existing authenticated capture boundary"}\n')
        self.destination = destination
        return subprocess.CompletedProcess(command, 0)

    def test_exact_caller_inputs_real_java_and_external_canonical_producer_forwarded_once(self):
        with patch('subprocess.run', side_effect=self.capture) as run:
            self.execute()
        self.assertEqual(1, run.call_count)
        self.assertEqual('tooling_policy=' + str(self.destination / 'tooling-policy.json') + '\n', self.output.read_text())
        self.assertEqual(b'original checkout bytes', self.original.read_bytes())
        self.assertEqual({'original-source'}, {path.name for path in self.repository.iterdir()})
        self.assertEqual(b'caller installed Java', self.java.read_bytes())

    def test_java_home_alias_is_resolved_to_the_actual_regular_executable(self):
        alias = self.root / 'java-alias'
        try:
            alias.symlink_to(self.java_home, target_is_directory=True)
        except OSError as error:
            self.skipTest(str(error))
        self.environment['JAVA_HOME'] = str(alias)
        with patch('subprocess.run', side_effect=self.capture):
            self.execute()

    def test_optional_plan_directory_is_fresh_external_and_shares_capture_parent(self):
        self.environment['PLAN_ID'] = '123'
        previous = None
        for _ in range(2):
            self.output.unlink(missing_ok=True)
            with patch('subprocess.run', side_effect=self.capture) as run:
                self.execute()
            run.assert_called_once()
            outputs = dict(line.split('=', 1) for line in self.output.read_text().splitlines())
            self.assertEqual({'tooling_policy', 'plan_directory'}, set(outputs))
            plan = Path(outputs['plan_directory'])
            self.assertEqual(self.destination.parent / 'plan', plan)
            self.assertTrue(plan.is_relative_to(self.scratch))
            self.assertFalse(plan.is_relative_to(self.repository))
            self.assertFalse(plan.exists())
            self.assertNotEqual(previous, plan)
            previous = plan
        self.assertEqual(b'original checkout bytes', self.original.read_bytes())

    def test_optional_plan_download_and_policy_reuse_are_guarded_and_exact(self):
        self.assertIn("  plan-id:\n    default: ''", self.action)
        self.assertIn('PLAN_ID: ${{ inputs.plan-id }}', self.action)
        self.assertIn('value: ${{ steps.capture.outputs.plan_directory }}', self.action)
        self.assertIn('value: ${{ steps.apple-policy.outputs.apple-policy }}', self.action)
        download = self.action.split('    - name: Download the exact original plan outside the checkout\n', 1)[1]
        download, policy = download.split('    - id: apple-policy\n', 1)
        self.assertIn("if: inputs.plan-id != ''", download)
        self.assertIn('uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c', download)
        self.assertIn('artifact-ids: ${{ inputs.plan-id }}', download)
        self.assertIn('path: ${{ steps.capture.outputs.plan_directory }}', download)
        self.assertIn('merge-multiple: true', download)
        self.assertIn("if: inputs.plan-id != ''", policy)
        self.assertIn('uses: ./.github/actions/prepare-sdk-apple-policy', policy)
        self.assertIn('plan-path: ${{ steps.capture.outputs.plan_directory }}/impact-plan.json', policy)
        self.assertIn('tooling-policy: ${{ steps.capture.outputs.tooling_policy }}', policy)
        self.assertNotIn('always()', download + policy)
        self.assertNotIn('ci.sdk_apple_policy', self.action)

    def test_invalid_java_scratch_and_duplicate_producer_fail_before_capture(self):
        original = dict(self.environment)
        for changes in ({'JAVA_HOME': 'relative'}, {'JAVA_HOME': str(self.root / 'missing-java')},
                        {'RUNNER_TEMP': str(self.repository)}, {'RUNNER_TEMP': str(self.repository / 'nested')},
                        {'RUNNER_TEMP': str(self.root)}, {'TRANSPORT_PRODUCER': '{"runId":1,"runId":2}'}):
            with self.subTest(changes=changes):
                self.environment = {**original, **changes}
                with patch('subprocess.run') as run, self.assertRaises((ValueError, OSError)):
                    self.execute()
                run.assert_not_called()
                self.assertFalse(self.output.exists())
                self.assertEqual(b'original checkout bytes', self.original.read_bytes())

    def test_capture_failure_or_missing_policy_never_exposes_a_policy_output(self):
        self.environment['PLAN_ID'] = '123'
        for failure in (True, False):
            def capture(command, **kwargs):
                if failure:
                    raise subprocess.CalledProcessError(1, command)
                return subprocess.CompletedProcess(command, 0)
            with self.subTest(failure=failure), patch('subprocess.run', side_effect=capture), \
                    self.assertRaises((subprocess.CalledProcessError, OSError, ValueError)):
                self.execute()
            self.assertFalse(self.output.exists())

    def test_action_exposes_only_capture_identity_and_never_signing_or_tool_setup(self):
        self.assertIn('value: ${{ steps.capture.outputs.tooling_policy }}', self.action)
        self.assertEqual(1, self.action.count('GITHUB_TOKEN: ${{ github.token }}'))
        inputs = self.action.split('inputs:\n', 1)[1].split('outputs:\n', 1)[0]
        import re
        self.assertEqual({'artifact-id', 'artifact-sha256', 'transport-producer', 'trusted-workflow-sha', 'policy-revision', 'plan-id'},
                         set(re.findall(r'^  ([a-z0-9-]+):$', inputs, re.MULTILINE)))
        for forbidden in ('--keyring', '--public-key', '--evidence', 'secrets.', 'setup-java', 'setup-kmp',
                          'java -jar', './gradlew', 'ci.tooling_release'):
            self.assertNotIn(forbidden, self.action)


if __name__ == '__main__':
    unittest.main()
