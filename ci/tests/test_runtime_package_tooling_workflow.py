"""Role/locator routing checks; no hosted or signature-authentication claims."""
import io
import json
import os
from pathlib import Path
import subprocess
import shlex
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
import zipfile

from ci import tooling_discovery
from ci.products.inventory import canonical_json_bytes, sha256_bytes

ROOT = Path(os.environ.get('RUNTIME_PACKAGE_CANDIDATE_ROOT', Path(__file__).resolve().parents[2]))


class RuntimePackageToolingWorkflowTest(unittest.TestCase):
    def test_purpose_selects_only_matching_names_and_passes_full_capture_gate(self):
        producer = {'repository': 'codex-agent-labs/codex-agent', 'workflowPath': '.github/workflows/ci.yml',
                    'commit': 'a' * 40, 'tree': 'b' * 40, 'event': 'pull_request',
                    'runId': 17, 'runAttempt': 1, 'pullRequest': 31}
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('caller.json', canonical_json_bytes({'transportProducer': producer}))
        raw = stream.getvalue()
        for purpose, prefix in [('full', 'codex-agent-release-tooling'),
                                ('runtime-package', 'codex-agent-runtime-package-tooling')]:
            with self.subTest(purpose=purpose), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve(); repository = root / 'repo'; repository.mkdir()
                java = root / 'java'; java.write_bytes(b'not executed')
                destination = root / 'captured'
                def artifact(name, identifier):
                    return {'id': identifier, 'name': name + '-' + producer['tree'] + '-attempt-1',
                            'expired': False, 'size_in_bytes': len(raw), 'digest': sha256_bytes(raw),
                            'archive_download_url': tooling_discovery._API + f'/artifacts/{identifier}/zip',
                            'workflow_run': {'id': 17}}
                matching = artifact(prefix, 19)
                other = artifact('codex-agent-release-tooling' if purpose != 'full' else
                                 'codex-agent-runtime-package-tooling', 20)
                def capture(path, repo, **kwargs):
                    self.assertEqual(repository, repo)
                    self.assertEqual(19, kwargs['artifact_id'])
                    self.assertEqual('c' * 40, kwargs['trusted_workflow_sha'])
                    if purpose == 'full':
                        self.assertNotIn('tooling_use', kwargs)
                    else:
                        self.assertEqual(purpose, kwargs['tooling_use'])
                    path.mkdir()
                    return {key: str(path / key) for key in ('evidence', 'publicKey', 'keyring', 'keysDirectory')}
                with mock.patch.object(tooling_discovery, 'run_git', return_value='a' * 40), \
                     mock.patch.object(tooling_discovery, 'git_inventory', return_value=[]) as inventory, \
                     mock.patch.object(tooling_discovery, '_release_trust', return_value={'fixture': True}), \
                     mock.patch.object(tooling_discovery, 'paginated_items', return_value=[other, matching]) as listing, \
                     mock.patch.object(tooling_discovery, 'api_json', return_value=matching) as metadata, \
                     mock.patch.object(tooling_discovery, 'download_artifact', return_value=raw) as download, \
                     mock.patch.object(tooling_discovery, 'capture_tooling_ci', side_effect=capture) as captured, \
                     mock.patch.object(tooling_discovery, '_original_tooling_workflow', return_value={
                         'trusted_workflow_sha': 'c' * 40}) as authority:
                    result = tooling_discovery.discover_tooling_ci(destination, repository,
                        candidate_run_ids=[17, 17], trusted_workflow_sha='c' * 40,
                        policy_revision='a' * 40, java_executable=java, token='fixture', tooling_use=purpose)
                expected = (tooling_discovery._COMPILER_INPUTS if purpose == 'full' else
                            tooling_discovery._RUNTIME_PACKAGE_COMPILER_INPUTS)
                self.assertTrue(all(call.args[2] == expected for call in inventory.call_args_list))
                for operation in (listing, metadata, download, captured, authority):
                    operation.assert_called_once()
                self.assertEqual(19, result['selected']['artifactId'])
                self.assertEqual(producer, result['selected']['transportProducer'])

    def test_action_rejects_wrong_purpose_before_any_external_action(self):
        action = (ROOT / '.github/actions/run-ci-lane/action.yml').read_text()
        code = textwrap.dedent(action.split('      run: |\n', 1)[1].split('    - uses:', 1)[0])
        with tempfile.TemporaryDirectory() as temporary:
            base = {'PATH': os.environ['PATH'], 'GITHUB_ENV': str(Path(temporary) / 'env'),
                    'TOOLING_ONLY': 'true', 'LANE': 'contracts', 'REUSE_DISABLED': 'true',
                    'REUSE_ONLY': 'false', 'PREPARED_PRODUCTION': 'false', 'PRODUCER_IDENTITIES': ''}
            for purpose, overrides, passes in [('full', {}, True), ('runtime-package', {}, True),
                    ('runtime-package', {'TOOLING_ONLY': 'false'}, False),
                    ('runtime-package', {'LANE': 'desktop-linux-x64'}, False), ('unknown', {}, False)]:
                with self.subTest(purpose=purpose, overrides=overrides):
                    result = subprocess.run(['bash', '-e', '-c', code], env={**base, 'TOOLING_PURPOSE': purpose, **overrides},
                                            capture_output=True, text=True, check=False)
                    self.assertEqual(passes, result.returncode == 0, result.stderr)

    def test_caller_java_alias_is_normalized_without_path_fallback(self):
        action = (ROOT / '.github/actions/run-runtime-product-phase/action.yml').read_text()
        line = next(line for line in action.splitlines() if 'java_executable="$(python3 ' in line)
        code = shlex.split(line.split('$(python3 ', 1)[1].rsplit(')"', 1)[0])[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); home = root / 'home'; (home / 'bin').mkdir(parents=True)
            java = home / 'bin/java'; java.write_bytes(b'not executed')
            alias = root / 'alias'; alias.symlink_to(home, target_is_directory=True)
            for value, passes in [(alias, True), (Path('relative'), False), (root / 'missing', False)]:
                result = subprocess.run([sys.executable, '-B', '-c', code, str(value), 'java'],
                                        capture_output=True, text=True, check=False)
                self.assertEqual(passes, result.returncode == 0)
                if passes:
                    self.assertEqual(str(java), result.stdout.strip())

    def test_native_packages_use_exact_locator_outside_source_and_no_scanning(self):
        action = (ROOT / '.github/actions/run-runtime-product-phase/action.yml').read_text()
        selected = action.split('    - id: package-tooling\n', 1)[1].split('    - id: archive\n', 1)[0]
        self.assertIn("inputs.phase == 'package'", selected)
        self.assertIn('CODEX_AGENT_RUNTIME_PACKAGE_TOOLING_RUN_ID', selected)
        self.assertIn('--candidate-run-id "$TOOLING_RUN_ID"', selected)
        self.assertIn('tooling_destination="$RUNNER_TEMP/runtime-package-tooling"', selected)
        self.assertIn('--purpose runtime-package', selected)
        self.assertNotIn('workflow_runs', selected)
        self.assertNotIn('gradlew', selected)
        self.assertIn('--runtime-package-tooling "$RUNTIME_PACKAGE_TOOLING"', action)
        workflow = (ROOT / '.github/workflows/contract-validation.yml').read_text()
        self.assertIn('runtime-package) flags+=(--purpose runtime-package)', workflow)
        self.assertIn("'codex-agent-runtime-package-tooling' || 'codex-agent-release-tooling'", workflow)


if __name__ == '__main__':
    unittest.main()
