"""Dependency-seed control checks, not genuine Gradle/product acceptance."""

from pathlib import Path, PureWindowsPath
import subprocess
import json
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from ci.products import gradle_bootstrap as bootstrap


class SdkDependencySeedTest(unittest.TestCase):
    def test_exact_git_fixture_merges_all_pins_and_only_resolves_dependencies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            namespace = {'v': 'https://schema.gradle.org/dependency-verification'}
            document = ET.fromstring(self.metadata('first'))
            for name in ('second', 'sdk'):
                document.find('v:components', namespace).extend(
                    ET.fromstring(self.metadata(name)).find('v:components', namespace))

            def blob(repository, revision, relative, **limits):
                self.assertEqual((root, 'a' * 40), (repository, revision))
                if relative.endswith('.xml'):
                    self.assertEqual('.github/actions/sdk-ios-binary-worker/verification-metadata.xml', relative)
                    return ET.tostring(document)
                return b'// exact Git build input\n'

            with patch.object(bootstrap, 'git_regular_blob_bytes', side_effect=blob), \
                    patch.object(bootstrap.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                destination = root / 'seed'
                bootstrap.seed_sdk_gradle_dependencies(root, 'a' * 40, root / 'gradlew', {}, destination)
            metadata = ET.parse(destination / 'gradle/build-logic/gradle/verification-metadata.xml')
            self.assertIn(b'<verification-metadata xmlns=',
                (destination / 'gradle/build-logic/gradle/verification-metadata.xml').read_bytes())
            namespace = {'v': 'https://schema.gradle.org/dependency-verification'}
            self.assertEqual(['first', 'sdk', 'second'], [item.get('name') for item in
                metadata.findall('v:components/v:component', namespace)])
            command = run.call_args.args[0]
            self.assertIn('--dependency-verification=strict', command)
            self.assertIn('resolveSdkBuildDependencies', command)
            self.assertNotIn('ciProductPhase', command)
            self.assertNotIn('compileKotlin', command)
            self.assertIn("'kotlinCompilerClasspath'", bootstrap._SDK_SEED_SCRIPT)
            self.assertNotIn("kotlinAbiValidationCompatClasspath", bootstrap._SDK_SEED_SCRIPT)
            self.assertNotIn("findAll", bootstrap._SDK_SEED_SCRIPT)

    @staticmethod
    def metadata(name, digest='a' * 64):
        return (f'<verification-metadata xmlns="https://schema.gradle.org/dependency-verification">'
                f'<configuration><verify-metadata>true</verify-metadata></configuration><components>'
                f'<component group="example" name="{name}" version="1.0.0"><artifact name="{name}.jar">'
                f'<sha256 value="{digest}"/></artifact></component></components></verification-metadata>').encode()

    def test_conflicting_pins_fail_before_gradle_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            namespace = {'v': 'https://schema.gradle.org/dependency-verification'}
            document = ET.fromstring(self.metadata('same'))
            document.find('v:components', namespace).extend(
                ET.fromstring(self.metadata('same', 'b' * 64)).find('v:components', namespace))
            with patch.object(bootstrap, 'git_regular_blob_bytes', side_effect=lambda *a, **k:
                    ET.tostring(document) if a[2].endswith('.xml') else b'// Git input\n'), \
                    patch.object(bootstrap.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'conflicting checksums'):
                    bootstrap.seed_sdk_gradle_dependencies(root, 'a' * 40, root / 'gradlew', {}, root / 'seed')
                run.assert_not_called()

    def test_windows_seed_reuses_direct_java_launcher_without_a_command_shell(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with patch.object(bootstrap, 'git_regular_blob_bytes', side_effect=lambda *a, **k:
                    self.metadata('same') if a[2].endswith('.xml') else b'// Git input\n'), \
                    patch.object(bootstrap.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                bootstrap.seed_sdk_gradle_dependencies(root, 'a' * 40,
                    PureWindowsPath(r'C:\checkout\gradlew.bat'), {'JAVA_HOME': r'C:\Java17'}, root / 'seed',
                    platform_name='nt')
            command = run.call_args.args[0]
            self.assertEqual([r'C:\Java17\bin\java.exe', '-Xmx64m', '-Xms64m',
                '-Dorg.gradle.appname=gradlew', '-jar', r'C:\checkout\gradle\wrapper\gradle-wrapper.jar'], command[:6])
            self.assertNotIn('--offline', command)
            self.assertIn('--dependency-verification=strict', command)
            self.assertNotIn('shell', run.call_args.kwargs)

    def test_native_setup_only_requests_prebuilt_distribution_without_product_tasks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            def blob(*args, **limits):
                if args[2].endswith('.json'):
                    return (json.dumps({'schemaVersion': 1, 'host': 'macos_arm64', 'kotlinVersion': '2.3.10',
                        'dependencies': [{'name': name, 'treeSha256': 'sha256:' + 'a' * 64} for name in
                            ('libffi-3.3-1-macos-arm64', 'llvm-19-aarch64-macos-essentials-79')]},
                        sort_keys=True, separators=(',', ':')) + '\n').encode()
                return b'[versions]\nkotlin="2.3.10"\n' if args[2].endswith('.toml') else self.metadata('native')
            with patch.object(bootstrap, 'git_regular_blob_bytes', side_effect=blob), \
                    patch('ci.products.toolchain._tree_digest', return_value='sha256:' + 'a' * 64), \
                    patch.object(bootstrap.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                bootstrap.seed_sdk_ios_native_distribution(root, 'a' * 40, root / 'gradlew',
                    {'KONAN_DATA_DIR': str(root)}, root / 'native')
            command = run.call_args.args[0]
            self.assertIn('downloadKotlinNativeDistribution', command)
            self.assertIn('--dependency-verification=strict', command)
            self.assertIn('-Pkotlin.native.distribution.type=prebuilt', command)
            self.assertNotIn('ciProductPhase', command)
            self.assertNotIn('compileKotlinIosArm64', command)

    def test_shared_environment_seeds_only_explicit_sdk_after_wrapper_admission(self):
        from ci import product_reuse as worker
        for directory in ('runtime', '.'):
            with self.subTest(directory=directory), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                (root / 'gradle/wrapper').mkdir(parents=True)
                (root / 'gradlew').write_bytes(b'// admitted fixture wrapper\n')
                (root / 'gradle/wrapper/gradle-wrapper.properties').write_bytes(b'// admitted properties\n')
                destination = root / 'build/worker'
                events = []
                with patch.object(worker, '_runtime_worker_checkout', side_effect=lambda *a: events.append('checkout')), \
                        patch.object(worker, 'git_regular_blob_bytes', side_effect=lambda *a, **k: (root / a[2]).read_bytes()), \
                        patch('products.gradle_bootstrap.require_preprovisioned_gradle', side_effect=lambda *a: events.append('wrapper')), \
                        patch('products.gradle_bootstrap.seed_sdk_gradle_dependencies', side_effect=lambda *a: events.append('seed')) as seed:
                    worker._runtime_worker_environment(root, {'commit': 'a' * 40}, destination,
                        {'GRADLE_USER_HOME': str(root / 'empty-home')}, build_directory=directory)
                self.assertFalse(destination.exists())
                if directory == '.':
                    self.assertEqual(['checkout', 'wrapper', 'seed', 'checkout'], events)
                    self.assertEqual(root / 'build/worker-dependency-seed', seed.call_args.args[-1])
                else:
                    self.assertEqual(['checkout', 'wrapper'], events)
                    seed.assert_not_called()

        with patch.object(worker, '_runtime_worker_checkout') as checkout:
            with self.assertRaisesRegex(ValueError, 'fixed Runtime or root SDK'):
                worker._runtime_worker_environment(None, None, None, {}, build_directory='other')
            with self.assertRaisesRegex(ValueError, 'remain offline'):
                worker._runtime_worker_environment(None, None, None,
                    {'CODEX_AGENT_VERIFIED_DEPENDENCY_FETCH': 'true'}, build_directory='.')
            checkout.assert_not_called()


if __name__ == '__main__':
    unittest.main()
