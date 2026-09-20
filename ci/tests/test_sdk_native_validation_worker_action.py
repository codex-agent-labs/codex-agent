"""Executed action guards and fixed argv only; no hosted or content acceptance."""

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
CI_ROOT = ROOT / 'ci'
if str(CI_ROOT) not in sys.path:
    sys.path.insert(0, str(CI_ROOT))

import native_wrappers
from ci.products.inventory import canonical_json_bytes, sha256_bytes


class SdkNativeValidationWorkerActionTest(unittest.TestCase):
    def setUp(self):
        self.action = (ROOT / '.github/actions/sdk-native-validation-worker/action.yml').read_text()
        self.temporary = tempfile.TemporaryDirectory(prefix='native-validation-action-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.policy_path = self.root / 'caller-policy.json'
        self.policy = {'evidence': str(self.root / 'evidence'), 'publicKey': str(self.root / 'public.pub'),
            'javaExecutable': str(self.root / 'java'), 'requiredTrustDomain': 'release',
            'keyring': str(self.root / 'keyring.json'), 'keysDirectory': str(self.root / 'keys')}
        self.policy_path.write_bytes(canonical_json_bytes(self.policy))
        self.output = self.root / 'github-output'
        self.plan = self.root / 'plan.json'
        self.plan.write_text(json.dumps({'validationTree': 'b' * 40, 'validationCommit': 'c' * 40}))
        self.environment = {'SDK_VALIDATION_TOOLING': str(self.policy_path), 'GITHUB_OUTPUT': str(self.output),
            'POLICY_SHA256': sha256_bytes(self.policy_path.read_bytes()), 'GITHUB_WORKSPACE': str(self.root),
            'PLAN': str(self.plan), 'COMPONENT': 'python', 'TARGET': 'linux-x64', 'BUILD_KEY': 'sha256:' + 'a' * 64,
            'PREPARATION_COMPONENT': 'rust', 'PREPARATION_BUILD_KEY': 'sha256:' + 'd' * 64, 'TREE': 'b' * 40,
            'PREPARATION_PHASE': 'package', 'PREPARATION_TARGET': 'desktop',
            'DISCOVERY': str(self.root / 'current/discovery'), 'STATE': str(self.root / 'current/state'),
            'PREPARATION_STATE': str(self.root / 'original-preparation/state'),
            'PREPARED_ARTIFACT_ID': '91', 'PREPARED_ARTIFACT_SHA256': 'sha256:' + 'e' * 64,
            'SDK_INPUTS_ID': '92', 'SDK_INPUTS_SHA256': 'sha256:' + 'f' * 64,
            'TRUSTED_WORKFLOW_SHA': '1' * 40, 'POLICY_REVISION': 'c' * 40,
            'DOTNET_EXECUTABLE': '', 'DART_EXECUTABLE': '', 'DART_PACKAGE_CONFIG': '',
            'DART_PUB_CACHE': '', 'GITHUB_TOKEN': 'caller-token'}
        self.current = {'product': 'sdk', 'component': 'python', 'phase': 'validation', 'target': 'linux-x64',
            'buildKey': self.environment['BUILD_KEY'], 'runnerOs': 'Linux', 'runnerArch': 'X64'}
        self.preparation = {'product': 'sdk', 'component': 'rust', 'phase': 'package', 'target': 'desktop',
            'buildKey': self.environment['PREPARATION_BUILD_KEY'], 'runnerOs': 'Linux', 'runnerArch': 'X64'}
        self.matrices()

    def matrices(self, current=None, preparation=None):
        self.environment['MATRIX'] = json.dumps({'include': current if current is not None else [self.current]})
        self.environment['PREPARATION_MATRIX'] = json.dumps({'include': preparation if preparation is not None else [self.preparation]})

    def block(self, step):
        return self.action.split('    - id: ' + step + '\n', 1)[1].split('\n    - ', 1)[0]

    def execute(self, step):
        code = self.block(step).split("        python3 -B - <<'PY'\n", 1)[1].split('\n        PY', 1)[0]
        with patch.dict(os.environ, self.environment, clear=True):
            exec(compile(textwrap.dedent(code), '<action-' + step + '>', 'exec'), {})

    @staticmethod
    def worker_environment(root, producer, destination, environ):
        # Shared checkout/wrapper/environment admission is an explicit mock seam.
        return dict(environ, PYTHONPYCACHEPREFIX=str(destination / 'python-bytecode'),
                    PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONSAFEPATH='1',
                    PYTHONPATH=str(root)), root / 'gradlew'

    def test_policy_is_exact_caller_input_and_rejects_missing_required_values_before_output(self):
        self.execute('policy')
        self.assertEqual('sha256=' + self.environment['POLICY_SHA256'] + '\n', self.output.read_text())
        for field in ('evidence', 'publicKey', 'javaExecutable'):
            for value in (None, 'relative/path'):
                with self.subTest(field=field, value=value):
                    policy = dict(self.policy, **{field: value})
                    self.policy_path.write_bytes(canonical_json_bytes(policy))
                    self.output.unlink(missing_ok=True)
                    with self.assertRaises(ValueError):
                        self.execute('policy')
                    self.assertFalse(self.output.exists())
        for policy in (dict(self.policy, extra='unknown'), dict(self.policy, keysDirectory=None),
                       dict(self.policy, requiredTrustDomain='development')):
            self.policy_path.write_bytes(canonical_json_bytes(policy))
            with self.assertRaises(ValueError):
                self.execute('policy')
            self.assertFalse(self.output.exists())

    def test_elections_match_actual_host_for_all_five_hosts_before_output(self):
        for host, values in native_wrappers.HOSTS.items():
            with self.subTest(host=host), patch.object(native_wrappers, 'host_classifier', return_value=host):
                self.environment['TARGET'] = host
                self.current.update(target=host, runnerOs=values[2], runnerArch=values[3])
                self.matrices()
                self.output.unlink(missing_ok=True)
                self.execute('identity')
                self.assertEqual('key_hex=' + 'a' * 64 + '\npolicy_revision=' + 'c' * 40 + '\n', self.output.read_text())

    def test_wrong_election_duplicate_preparation_host_and_policy_swap_fail_without_output(self):
        cases = [('current-key', lambda: self.current.update(buildKey='sha256:' + '0' * 64)),
                 ('preparation-target', lambda: self.preparation.update(target='linux-x64')),
                 ('current-host', lambda: self.current.update(runnerArch='ARM64')),
                 ('actual-host', lambda: self.environment.update(TARGET='macos-arm64')),
                 ('tree', lambda: self.environment.update(TREE='0' * 40)),
                 ('policy', lambda: self.policy_path.write_bytes(canonical_json_bytes(dict(self.policy, evidence='/changed'))))]
        for label, mutate in cases:
            with self.subTest(label=label):
                current, preparation, environment = deepcopy(self.current), deepcopy(self.preparation), dict(self.environment)
                mutate()
                self.matrices()
                with patch.object(native_wrappers, 'host_classifier', return_value='linux-x64'), self.assertRaises(ValueError):
                    self.execute('identity')
                self.assertFalse(self.output.exists())
                self.current, self.preparation, self.environment = current, preparation, environment
                self.policy_path.write_bytes(canonical_json_bytes(self.policy))
        self.matrices(preparation=[self.preparation, self.preparation])
        with patch.object(native_wrappers, 'host_classifier', return_value='linux-x64'), self.assertRaises(ValueError):
            self.execute('identity')
        self.assertFalse(self.output.exists())

    def test_fixed_controller_forwards_original_inputs_and_exact_caller_policy(self):
        self.environment.update(DOTNET_EXECUTABLE='/caller/dotnet', DART_EXECUTABLE='/caller/dart', DART_PACKAGE_CONFIG='/caller/package.json')
        with patch('subprocess.run') as run:
            self.execute('execute')
        command = run.call_args.args[0]
        self.assertEqual([sys.executable, '-B', '-m', 'ci.sdk_workflow', 'native-validation'], command[:5])
        arguments = dict(zip(command[5::2], command[6::2]))
        for flag, variable in (('state-root', 'STATE'), ('preparation-state-root', 'PREPARATION_STATE'),
                ('prepared-artifact-id', 'PREPARED_ARTIFACT_ID'), ('sdk-inputs-artifact-sha256', 'SDK_INPUTS_SHA256'),
                ('expected-build-key', 'BUILD_KEY'), ('target', 'TARGET'), ('policy-revision', 'POLICY_REVISION')):
            self.assertEqual(self.environment[variable], arguments['--' + flag])
        for flag, field in (('tooling-evidence', 'evidence'), ('tooling-public-key', 'publicKey'),
                ('java-executable', 'javaExecutable'), ('tooling-keyring', 'keyring'), ('tooling-keys-directory', 'keysDirectory')):
            self.assertEqual(self.policy[field], arguments['--' + flag])
        self.assertEqual('/caller/package.json', arguments['--dart-package-config'])
        self.assertEqual(str(self.root / 'build/sdk-worker'), arguments['--destination'])
        self.assertEqual(str(self.root), run.call_args.kwargs['cwd'])
        self.assertTrue(run.call_args.kwargs['check'])
        self.assertNotIn('shell', run.call_args.kwargs)
        self.policy_path.write_bytes(canonical_json_bytes(dict(self.policy, evidence='/changed')))
        with patch('subprocess.run') as run, self.assertRaises(ValueError):
            self.execute('execute')
        run.assert_not_called()

    def test_independent_preparation_capture_shell_preserves_optional_wave_and_policy(self):
        script = textwrap.dedent(self.block('preparation').split('      run: |\n', 1)[1])
        binary = self.root / 'bin'
        binary.mkdir()
        stub = binary / 'python3'
        stub.write_text('#!/bin/sh\nprintf \'%s\\0\' "$@" > "$RECORDED_ARGS"\n')
        stub.chmod(0o700)
        recorded = self.root / 'argv'
        for wave, apple_policy in ((wave, policy) for wave in ('', '4')
                                   for policy in ('', '/caller policies/apple validation.json')):
            environment = dict(self.environment, PATH=str(binary), ARTIFACT_ID='78', ARTIFACT_SHA256='sha256:' + '8' * 64,
                STATE_WAVE='0', SDK_STATE_WAVE=wave, SDK_APPLE_VALIDATION_POLICY=apple_policy,
                RECORDED_ARGS=str(recorded))
            completed = subprocess.run([shutil.which('bash'), '-c', script], env=environment, capture_output=True, text=True)
            self.assertEqual(0, completed.returncode, completed.stderr)
            arguments = recorded.read_bytes().decode().split('\0')[:-1]
            self.assertEqual(['-B', '-m', 'ci.sdk_workflow', 'capture'], arguments[:4])
            flags = dict(zip(arguments[4::2], arguments[5::2]))
            self.assertEqual('native-package', flags['--family'])
            self.assertEqual('78', flags['--artifact-id'])
            self.assertEqual(str(self.policy_path), flags['--sdk-validation-tooling'])
            self.assertEqual(wave or None, flags.get('--sdk-state-wave'))
            self.assertEqual(apple_policy or None, flags.get('--sdk-apple-validation-policy'))
            self.assertEqual(str(self.root / 'build/native-preparation-input'), flags['--destination'])

    def test_dart_preflight_requires_external_existing_config_or_populated_cache(self):
        with tempfile.TemporaryDirectory(prefix='caller-dart-') as temporary:
            external = Path(temporary).resolve()
            cache = external / 'pub-cache'
            cache.mkdir()
            (cache / 'cached-package').mkdir()
            config = external / 'package_config.json'
            config.write_text('{"configVersion":2,"packages":[]}\n')
            self.environment.update(DART_PUB_CACHE=str(cache))
            self.execute('dart-inputs')
            self.environment.update(DART_PACKAGE_CONFIG=str(config), DART_PUB_CACHE='')
            self.execute('dart-inputs')
            linked = external / 'linked-cache'
            linked.symlink_to(cache, target_is_directory=True)
            empty = external / 'empty-cache'
            empty.mkdir()
            for config_value, cache_value in (('', ''), ('', 'relative/cache'), ('', str(empty)),
                    ('', str(linked)), ('', str(self.root)), (str(self.plan), ''),
                    (str(external / 'missing.json'), '')):
                with self.subTest(config=config_value, cache=cache_value), patch('subprocess.run') as run:
                    self.environment.update(DART_PACKAGE_CONFIG=config_value, DART_PUB_CACHE=cache_value)
                    with self.assertRaises((ValueError, OSError)):
                        self.execute('dart-inputs')
                    run.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_dart_uses_fixed_offline_provisioner_once_before_controller_without_checkout_writes(self):
        with tempfile.TemporaryDirectory(prefix='caller-dart-') as temporary:
            external = Path(temporary).resolve()
            dart = external / 'dart'
            dart.write_bytes(b'caller installed tool')
            cache = external / 'pub-cache'
            cache.mkdir()
            (cache / 'cached-package').mkdir()
            self.environment.update(COMPONENT='dart', DART_PUB_CACHE=str(cache), RUNNER_TEMP=str(external))
            self.execute('dart-inputs')
            events = []
            def process(command, **kwargs):
                events.append(command)
                if command[2].endswith('provision_dependencies.py'):
                    flags = dict(zip(command[3::2], command[4::2]))
                    self.assertEqual(str(dart), flags['--dart-executable'])
                    self.assertEqual(str(cache), flags['--pub-cache'])
                    output = Path(flags['--output'])
                    self.assertTrue(output.is_relative_to(external))
                    self.assertFalse(output.exists())
                    self.assertEqual('dart_diagnostics=' + str(output) + '\n', self.output.read_text())
                    self.assertEqual(str(output.parent / 'python-bytecode'), kwargs['env']['PYTHONPYCACHEPREFIX'])
                    self.assertFalse(Path(kwargs['env']['PYTHONPYCACHEPREFIX']).exists())
                    self.assertEqual('1', kwargs['env']['PYTHONDONTWRITEBYTECODE'])
                    self.assertEqual('1', kwargs['env']['PYTHONNOUSERSITE'])
                    self.assertEqual('1', kwargs['env']['PYTHONSAFEPATH'])
                    output.mkdir()
                    (output / 'package_config.json').write_text('mocked provisioner output\n')
                return subprocess.CompletedProcess(command, 0)
            with patch('shutil.which', return_value=str(dart)), \
                    patch('ci.product_reuse._runtime_worker_environment', side_effect=self.worker_environment) as environment_guard, \
                    patch('ci.product_reuse._runtime_worker_checkout', side_effect=lambda *args: events.append('checkout')) as checkout, \
                    patch('subprocess.run', side_effect=process) as run:
                self.execute('execute')
            self.assertEqual(2, run.call_count)
            environment_guard.assert_called_once()
            self.assertEqual((self.root, {'commit': 'c' * 40, 'tree': 'b' * 40}), environment_guard.call_args.args[:2])
            self.assertEqual('checkout', events[0])
            self.assertEqual('checkout', events[2])
            checkout.assert_called_with(self.root, {'commit': 'c' * 40, 'tree': 'b' * 40})
            self.assertEqual([sys.executable, '-B', str(self.root / 'codex-agent-bindings/dart/tool/provision_dependencies.py')], events[1][:3])
            arguments = dict(zip(events[3][5::2], events[3][6::2]))
            self.assertEqual(str(dart), arguments['--dart-executable'])
            self.assertEqual('mocked provisioner output\n', Path(arguments['--dart-package-config']).read_text())
            self.assertFalse((self.root / '.dart_tool').exists())
            self.assertFalse((self.root / 'codex-agent-bindings').exists())

    def test_dart_explicit_config_skips_provisioning_and_failed_provision_or_checkout_never_launches_controller(self):
        with tempfile.TemporaryDirectory(prefix='caller-dart-') as temporary:
            external = Path(temporary).resolve()
            dart = external / 'dart'
            dart.write_bytes(b'caller installed tool')
            config = external / 'config.json'
            config.write_bytes(b'caller original config\n')
            cache = external / 'cache'
            cache.mkdir()
            (cache / 'cached-package').mkdir()
            self.environment.update(COMPONENT='dart', DART_EXECUTABLE=str(dart),
                DART_PACKAGE_CONFIG=str(config), RUNNER_TEMP=str(external), DART_PUB_CACHE=str(cache))
            with patch('subprocess.run') as run:
                self.execute('execute')
            run.assert_called_once()
            command = run.call_args.args[0]
            self.assertEqual('native-validation', command[4])
            self.assertEqual(str(config), command[command.index('--dart-package-config') + 1])
            self.assertEqual(b'caller original config\n', config.read_bytes())
            self.assertFalse(self.output.exists())
            self.environment['DART_EXECUTABLE'] = ''
            with patch('shutil.which', return_value=None), patch('subprocess.run') as run, self.assertRaisesRegex(ValueError, 'installed pinned Dart'):
                self.execute('execute')
            run.assert_not_called()
            self.environment['DART_EXECUTABLE'] = str(dart)
            self.environment['DART_PACKAGE_CONFIG'] = ''
            for failure in ('provision', 'checkout', 'bytecode'):
                self.output.unlink(missing_ok=True)
                def process(command, **kwargs):
                    if failure == 'provision':
                        raise subprocess.CalledProcessError(1, command)
                    if failure == 'bytecode':
                        Path(kwargs['env']['PYTHONPYCACHEPREFIX']).mkdir()
                with self.subTest(failure=failure), \
                        patch('ci.product_reuse._runtime_worker_environment', side_effect=self.worker_environment), \
                        patch('ci.product_reuse._runtime_worker_checkout', side_effect=([None, ValueError('source changed')] if failure == 'checkout' else None)), \
                        patch('subprocess.run', side_effect=process) as run, \
                        self.assertRaises((ValueError, subprocess.CalledProcessError)) as rejected:
                    self.execute('execute')
                if failure == 'bytecode':
                    self.assertIn('private Python bytecode namespace was modified', str(rejected.exception))
                run.assert_called_once()
                self.assertTrue(run.call_args.args[0][2].endswith('provision_dependencies.py'))
                command = run.call_args.args[0]
                chosen_output = command[command.index('--output') + 1]
                self.assertEqual('dart_diagnostics=' + chosen_output + '\n', self.output.read_text())

    def test_dart_diagnostics_upload_is_separate_exact_and_attempt_qualified_on_failure(self):
        block = self.action.split('    - name: Retain exact external Dart provisioning diagnostics, including failures\n', 1)[1].split('\n    - ', 1)[0]
        self.assertIn("if: always() && steps.identity.outcome == 'success' && steps.execute.outputs.dart_diagnostics != ''", block)
        self.assertIn('uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a', block)
        self.assertIn('name: codex-agent-sdk-dart-dependencies-validation-${{ inputs.target }}-${{ steps.identity.outputs.key_hex }}-${{ inputs.tree }}-attempt-${{ github.run_attempt }}', block)
        self.assertIn('path: ${{ steps.execute.outputs.dart_diagnostics }}\n', block)
        self.assertIn('include-hidden-files: true', block)
        self.assertIn('overwrite: false', block)
        self.assertNotIn('build/sdk-worker', block)
        self.assertNotIn('RUNNER_TEMP', block)

    def test_capture_identity_setup_and_whole_worker_upload_order(self):
        action = self.action
        self.assertLess(action.index('- id: policy'), action.index('- id: captured'))
        self.assertLess(action.index('- id: dart-inputs'), action.index('- id: captured'))
        self.assertIn("if: inputs.component == 'dart'", self.block('dart-inputs'))
        self.assertLess(action.index('- id: preparation'), action.index('- id: identity'))
        self.assertLess(action.index('- id: identity'), action.index('./.github/actions/setup-kmp'))
        self.assertIn('sdk-family: native-validation', self.block('captured'))
        self.assertIn('sdk-validation-tooling: ${{ inputs.sdk-validation-tooling }}', self.block('captured'))
        self.assertIn('sdk-apple-validation-policy: ${{ inputs.sdk-apple-validation-policy }}', self.block('captured'))
        self.assertIn("product-worker: 'true'", action)
        self.assertIn("cache-read-only: 'true'", action)
        self.assertIn('path: build/sdk-worker\n', action)
        self.assertIn('name: codex-agent-sdk-worker-${{ inputs.component }}-validation-${{ inputs.target }}-${{ steps.identity.outputs.key_hex }}-${{ inputs.tree }}-attempt-${{ github.run_attempt }}', action)
        self.assertIn("if: always() && steps.identity.outcome == 'success'", action)
        self.assertIn('overwrite: false', action)
        for forbidden in ('dotnet restore', 'dart pub get', 'native-prepare --', 'actions/download-artifact', 'run: ./gradlew'):
            self.assertNotIn(forbidden, action)

    def test_optional_apple_policy_is_forwarded_only_when_supplied(self):
        self.assertIn("  sdk-apple-validation-policy:\n    default: ''", self.action)
        for step in ('preparation', 'execute'):
            self.assertIn('SDK_APPLE_VALIDATION_POLICY: ${{ inputs.sdk-apple-validation-policy }}', self.block(step))
        for policy in ('', '/caller policies/apple validation.json'):
            with self.subTest(policy=policy), patch('subprocess.run') as run:
                self.environment['SDK_APPLE_VALIDATION_POLICY'] = policy
                self.execute('execute')
            command = run.call_args.args[0]
            fields = dict(zip(command[5::2], command[6::2]))
            self.assertEqual(policy or None, fields.get('--sdk-apple-validation-policy'))
            self.assertEqual(self.environment['PREPARATION_STATE'], fields['--preparation-state-root'])


if __name__ == '__main__':
    unittest.main()
