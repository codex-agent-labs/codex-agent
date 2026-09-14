"""Preparation action composition; no remote, tooling or signing process runs."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci import sdk_workflow
from products.inventory import canonical_json_bytes


ROOT = Path(__file__).resolve().parents[2]
product_reuse = sdk_workflow.product_reuse


class PrepareRuntimeSigningActionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='prepare-signing-action-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.trusted = self.root / 'trusted-source'
        self.action_path = self.trusted / '.github/actions/prepare-runtime-signing'
        self.action_path.mkdir(parents=True)
        self.candidate = self.root / 'candidate-source'
        self.candidate.mkdir()
        self.scratch = self.root / 'runner-temp'
        self.scratch.mkdir()
        self.destination = self.scratch / 'prepared'
        self.plan_path = self.root / 'original-plan.json'
        self.plan = {'validationCommit': 'a' * 40, 'validationTree': 'b' * 40}
        self.plan_path.write_bytes(canonical_json_bytes(self.plan))
        self.java_home = self.root / 'installed java'
        self.java = self.java_home / 'bin' / ('java.exe' if os.name == 'nt' else 'java')
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b'synthetic installed Java boundary')
        self.producer = {'repository': 'codex-agent-labs/codex-agent', 'workflowPath': '.github/workflows/ci.yml',
            'commit': 'a' * 40, 'tree': 'b' * 40, 'event': 'pull_request', 'runId': 71,
            'runAttempt': 2, 'pullRequest': 31}
        self.output = self.root / 'github-output'
        self.environment = {'GITHUB_ACTION_PATH': str(self.action_path), 'CANDIDATE_ROOT': str(self.candidate),
            'ORIGINAL_PLAN': str(self.plan_path), 'DESTINATION': str(self.destination), 'SOURCE_SHA': 'c' * 40,
            'WORKFLOW_SHA': 'd' * 40, 'VALIDATION_TREE': 'b' * 40, 'TARGET': 'linux-x64',
            'BUILD_KEY': 'sha256:' + 'e' * 64, 'ARTIFACT_ID': '71', 'ARTIFACT_SHA256': 'sha256:' + 'f' * 64,
            'STATE_WAVE': '4', 'TOOLING_ARTIFACT_ID': '', 'TOOLING_ARTIFACT_SHA256': '',
            'TOOLING_TRANSPORT_PRODUCER': '', 'RUNNER_TEMP': str(self.scratch), 'RUNNER_ARCH': 'X64',
            'JAVA_HOME_17_X64': str(self.java_home), 'GITHUB_TOKEN': 'caller-token', 'GITHUB_OUTPUT': str(self.output)}
        self.source = (ROOT / '.github/actions/prepare-runtime-signing/action.yml').read_text()

    def execute(self):
        code = self.source.split("        python3 -B - <<'PY'\n", 1)[1].split('\n        PY', 1)[0]
        with patch.dict(os.environ, self.environment, clear=True), \
                patch('products.inventory.run_git', side_effect=lambda root, *args: 'c' * 40 if args == ('rev-parse', 'HEAD') else ''), \
                patch.object(product_reuse, '_validate_plan', return_value=self.plan), \
                patch('sys.path', list(__import__('sys').path)):
            exec(compile(textwrap.dedent(code), '<prepare-runtime-signing-action>', 'exec'), {})

    def process(self, command, **kwargs):
        self.assertEqual(self.trusted, kwargs['cwd'])
        self.assertEqual('caller-token', kwargs['env']['GITHUB_TOKEN'])
        self.assertTrue(kwargs['check'])
        self.assertNotIn('shell', kwargs)
        script = Path(command[2])
        self.assertEqual(self.trusted / 'ci', script.parent)
        if script.name == 'tooling_capture.py':
            fields = dict(zip(command[3::2], command[4::2]))
            self.assertEqual(str(self.candidate), fields['--repository-root'])
            self.assertEqual(self.plan['validationCommit'], fields['--policy-revision'])
            self.assertEqual(str(self.java), fields['--java-executable'])
            producer_path = Path(fields['--transport-producer'])
            self.assertEqual(canonical_json_bytes(self.producer), producer_path.read_bytes())
            self.policy = Path(fields['--destination']) / 'tooling-policy.json'
            self.assertTrue(self.policy.is_relative_to(self.scratch))
            self.policy.parent.mkdir()
            self.policy.write_bytes(b'{"synthetic":"authenticated capture seam"}\n')
        else:
            self.assertEqual('runtime_release.py', script.name)
            self.assertEqual('--prepare-only', command[3])
            fields = dict(zip(command[4::2], command[5::2]))
            expected = {'--repository-root': str(self.trusted), '--candidate-root': str(self.candidate),
                '--plan': str(self.plan_path), '--destination': str(self.destination), '--target': 'linux-x64',
                '--expected-build-key': self.environment['BUILD_KEY'], '--artifact-id': '71',
                '--artifact-sha256': self.environment['ARTIFACT_SHA256'], '--state-wave': '4',
                '--trusted-source-sha': self.environment['SOURCE_SHA'], '--trusted-workflow-sha': self.environment['WORKFLOW_SHA'],
                '--validation-tree': self.environment['VALIDATION_TREE']}
            if self.environment['TOOLING_ARTIFACT_ID']:
                expected['--sdk-validation-tooling'] = str(self.policy)
            self.assertEqual(expected, fields)
            self.destination.mkdir()
            (self.destination / 'preparation.json').write_bytes(b'{"synthetic":"preparation boundary"}\n')
        return subprocess.CompletedProcess(command, 0)

    def test_optional_tooling_uses_trusted_scripts_and_candidate_git_policy(self):
        for supplied in (False, True):
            self.destination = self.scratch / f'prepared-{supplied}'
            self.environment['DESTINATION'] = str(self.destination)
            if supplied:
                self.environment.update(TOOLING_ARTIFACT_ID='72', TOOLING_ARTIFACT_SHA256='sha256:' + '1' * 64,
                    TOOLING_TRANSPORT_PRODUCER=canonical_json_bytes(self.producer).decode())
            with self.subTest(supplied=supplied), patch('subprocess.run', side_effect=self.process) as run:
                self.execute()
                self.assertEqual(2 if supplied else 1, run.call_count)
            self.assertIn('preparation_path=' + str(self.destination) + '\n', self.output.read_text())

    def test_partial_tuple_secret_overlap_and_failure_never_emit_output(self):
        baseline = dict(self.environment)
        for changes in ({'TOOLING_ARTIFACT_ID': '72'}, {'CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY': ''},
                        {'CANDIDATE_ROOT': str(self.trusted)}, {'DESTINATION': str(self.candidate / 'output')}):
            self.environment = {**baseline, **changes}
            with self.subTest(changes=changes), patch('subprocess.run') as run, self.assertRaises(ValueError):
                self.execute()
            run.assert_not_called()
            self.assertFalse(self.output.exists())
        self.environment = baseline
        with patch('subprocess.run', side_effect=subprocess.CalledProcessError(17, ['fixed preparation'])), \
                self.assertRaises(subprocess.CalledProcessError):
            self.execute()
        self.assertFalse(self.output.exists())

    def test_static_only_trusted_fixed_commands_no_signing_or_candidate_action(self):
        self.assertIn('cd "$GITHUB_ACTION_PATH/../../.."', self.source)
        self.assertIn("trusted / 'ci/tooling_capture.py'", self.source)
        self.assertIn("trusted / 'ci/runtime_release.py'", self.source)
        self.assertIn("'--prepare-only'", self.source)
        self.assertIn("'JAVA_HOME_17_' + os.environ['RUNNER_ARCH']", self.source)
        self.assertEqual(1, self.source.count('GITHUB_TOKEN: ${{ github.token }}'))
        for forbidden in ('secrets.', 'environment:', 'uses:', 'gradlew', 'java -jar', '--release-handoff', '--variant-handoff'):
            self.assertNotIn(forbidden, self.source)
        outputs = self.source.split('outputs:\n', 1)[1].split('runs:\n', 1)[0]
        self.assertEqual(['preparation-path'], re.findall(r'^  ([a-z-]+):', outputs, re.M))


if __name__ == '__main__':
    unittest.main()
