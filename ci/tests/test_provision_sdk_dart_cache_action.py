"""Dart cache action routing with process/Git seams mocked; no Dart/network execution."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci import sdk_workflow


ROOT = Path(__file__).resolve().parents[2]
products = sdk_workflow.product_reuse


class ProvisionSdkDartCacheActionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='dart-cache-action-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.repository = self.root / 'checkout'
        self.binding = self.repository / 'codex-agent-bindings/dart'
        self.binding.mkdir(parents=True)
        self.manifests = {'pubspec.yaml': b'name: codex_agent\n', 'pubspec.lock': b'packages: {}\n'}
        for name, raw in self.manifests.items():
            (self.binding / name).write_bytes(raw)
        self.scratch = self.root / 'scratch'
        self.scratch.mkdir()
        self.executable = self.root / 'dart'
        self.executable.write_bytes(b'synthetic Dart executable')
        self.output = self.root / 'github-output'
        self.environment = {'GITHUB_WORKSPACE': str(self.repository), 'RUNNER_TEMP': str(self.scratch),
            'REVISION': 'a' * 40, 'GITHUB_OUTPUT': str(self.output), 'PATH': '/caller/bin'}
        self.source = (ROOT / '.github/actions/provision-sdk-dart-cache/action.yml').read_text()
        self.status, self.mutation = 0, None

    def execute(self):
        block = self.source.split('    - id: populate\n', 1)[1]
        code = block.split("        python3 -B - <<'PY'\n", 1)[1].split('\n        PY', 1)[0]
        with patch.dict(os.environ, self.environment, clear=True), \
                patch.object(products, '_runtime_worker_checkout') as checkout, \
                patch.object(products, '_runtime_worker_environment', side_effect=lambda root, producer, output, env: (dict(env), root / 'gradlew')), \
                patch('products.inventory.run_git', return_value='b' * 40), \
                patch('products.inventory.git_regular_blob_bytes', side_effect=lambda root, revision, path, **kw: self.manifests[Path(path).name]), \
                patch('shutil.which', return_value=str(self.executable)), \
                patch('subprocess.run', side_effect=self.process), patch('sys.path', list(__import__('sys').path)):
            exec(compile(textwrap.dedent(code), '<dart-cache-action>', 'exec'), {})
            self.assertGreaterEqual(checkout.call_count, 3)

    def process(self, command, **kwargs):
        self.assertEqual([str(self.executable), 'pub', 'get', '--enforce-lockfile'], command)
        self.project = kwargs['cwd']
        self.assertTrue(self.project.is_relative_to(self.scratch))
        self.assertEqual(set(self.manifests), {path.name for path in self.project.iterdir()})
        self.cache = Path(kwargs['env']['PUB_CACHE'])
        self.assertTrue(self.cache.is_relative_to(self.scratch))
        self.assertEqual('https://pub.dev', kwargs['env']['PUB_HOSTED_URL'])
        self.assertFalse(kwargs['check'])
        self.assertEqual(subprocess.STDOUT, kwargs['stderr'])
        kwargs['stdout'].write(b'raw resolution diagnostics\x00\xff')
        (self.cache / 'cached-dependency').write_bytes(b'synthetic cache contents')
        if self.mutation == 'lock':
            (self.project / 'pubspec.lock').write_bytes(b'changed lock\n')
        elif self.mutation == 'source':
            (self.binding / 'pubspec.yaml').write_bytes(b'changed source\n')
        elif self.mutation == 'launch':
            raise OSError('synthetic launch failure')
        return subprocess.CompletedProcess(command, self.status)

    def test_exact_manifest_only_external_resolution_and_cache_output(self):
        self.execute()
        outputs = dict(line.split('=', 1) for line in self.output.read_text().splitlines())
        self.assertEqual(str(self.cache), outputs['pub_cache'])
        diagnostics = Path(outputs['diagnostics'])
        self.assertEqual(b'raw resolution diagnostics\x00\xff', (diagnostics / 'pub.log').read_bytes())
        self.assertEqual(0, json.loads((diagnostics / 'execution.json').read_bytes())['returnCode'])
        for name, raw in self.manifests.items():
            self.assertEqual(raw, (self.binding / name).read_bytes())
            self.assertEqual(raw, (self.project / name).read_bytes())
        self.assertEqual(set(self.manifests), {path.name for path in self.binding.iterdir()})

    def test_failure_and_manifest_mutation_keep_raw_diagnostics_not_cache_output(self):
        for status, mutation in ((17, None), (0, 'lock'), (0, 'source'), (0, 'launch')):
            self.status, self.mutation = status, mutation
            for name, raw in self.manifests.items():
                (self.binding / name).write_bytes(raw)
            self.output = self.root / f'github-output-{status}-{mutation}'
            self.environment['GITHUB_OUTPUT'] = str(self.output)
            with self.subTest(status=status, mutation=mutation), self.assertRaises((ValueError, OSError)):
                self.execute()
            outputs = dict(line.split('=', 1) for line in self.output.read_text().splitlines())
            self.assertNotIn('pub_cache', outputs)
            diagnostics = Path(outputs['diagnostics'])
            self.assertEqual(b'raw resolution diagnostics\x00\xff', (diagnostics / 'pub.log').read_bytes())
            self.assertTrue((diagnostics / 'execution.json').is_file())

    def test_checkout_scratch_and_dirty_manifests_fail_before_process(self):
        self.environment['RUNNER_TEMP'] = str(self.repository)
        with patch.object(self, 'process') as process, self.assertRaises(ValueError):
            self.execute()
        process.assert_not_called()
        self.assertFalse(self.output.exists())
        self.environment['RUNNER_TEMP'] = str(self.scratch)
        (self.binding / 'pubspec.lock').write_bytes(b'dirty checkout lock\n')
        with patch.object(self, 'process') as process, self.assertRaises(ValueError):
            self.execute()
        process.assert_not_called()

    def test_pinned_setup_after_source_guard_and_offline_validation_remains_separate(self):
        self.assertLess(self.source.index('_runtime_worker_checkout'), self.source.index('uses: dart-lang/setup-dart@'))
        self.assertIn("sdk: '3.13.2'", self.source)
        self.assertIn('dart-lang/setup-dart@65eb853c7ba17dde3be364c3d2858773e7144260', self.source)
        self.assertIn("for name in ('pubspec.yaml', 'pubspec.lock')", self.source)
        for forbidden in ('pub upgrade', 'flutter', 'secrets.', 'GITHUB_TOKEN', 'gradlew ', 'package-config:'):
            self.assertNotIn(forbidden, self.source)
        offline = (ROOT / 'codex-agent-bindings/dart/tool/provision_dependencies.py').read_text()
        self.assertIn('"--enforce-lockfile", "--offline"', offline)


if __name__ == '__main__':
    unittest.main()
