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

    def test_native_setup_seeds_exact_catalog_ios_dependencies_without_product_tasks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            catalog = (b'[versions]\nkotlin="2.3.10"\ncoroutines="1.10.2"\n'
                b'serialization="1.9.0"\nokio="3.16.2"\n[libraries]\n'
                b'kotlinx-coroutines-core={module="org.jetbrains.kotlinx:kotlinx-coroutines-core",version.ref="coroutines"}\n'
                b'kotlinx-serialization-json={module="org.jetbrains.kotlinx:kotlinx-serialization-json",version.ref="serialization"}\n'
                b'okio={module="com.squareup.okio:okio",version.ref="okio"}\n')
            def blob(*args, **limits):
                self.assertEqual((root, 'a' * 40), args[:2])
                if args[2].endswith('.json'):
                    return (json.dumps({'schemaVersion': 1, 'host': 'macos_arm64', 'kotlinVersion': '2.3.10',
                        'dependencies': [{'name': name, 'treeSha256': 'sha256:' + 'a' * 64} for name in
                            ('libffi-3.3-1-macos-arm64', 'llvm-19-aarch64-macos-essentials-79')]},
                        sort_keys=True, separators=(',', ':')) + '\n').encode()
                return catalog if args[2].endswith('.toml') else self.metadata('native')
            with patch.object(bootstrap, 'git_regular_blob_bytes', side_effect=blob), \
                    patch('ci.products.toolchain._tree_digest', return_value='sha256:' + 'a' * 64), \
                    patch.object(bootstrap.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                bootstrap.seed_sdk_ios_native_distribution(root, 'a' * 40, root / 'gradlew',
                    {'KONAN_DATA_DIR': str(root)}, root / 'native')
            command = run.call_args.args[0]
            self.assertIn('downloadKotlinNativeDistribution', command)
            self.assertIn('resolveSdkIosDependencies', command)
            self.assertIn('--dependency-verification=strict', command)
            self.assertIn('-Pkotlin.native.distribution.type=prebuilt', command)
            self.assertNotIn('ciProductPhase', command)
            self.assertNotIn('compileKotlinIosArm64', command)
            self.assertNotIn('--offline', command)
            self.assertEqual(catalog, (root / 'native/gradle/libs.versions.toml').read_bytes())
            self.assertEqual(self.metadata('native'),
                (root / 'native/gradle/verification-metadata.xml').read_bytes())
            script = (root / 'native/build.gradle.kts').read_text()
            for dependency in ('libs.kotlinx.coroutines.core', 'libs.kotlinx.serialization.json', 'libs.okio'):
                self.assertIn(f'implementation({dependency})', script)
            self.assertIn('listOf("iosArm64CompileKlibraries", "iosSimulatorArm64CompileKlibraries", "kotlinCompilerClasspath", "kotlinKlibCommonizerClasspath", "allSourceSetsCompileDependenciesMetadata", "iosArm64CompilationDependenciesMetadata", "iosSimulatorArm64CompilationDependenciesMetadata")', script)
            self.assertIn('configurations.getByName(name).files', script)
            self.assertNotIn('dependsOn', script)
            self.assertNotIn('findAll', script)

    def test_android_seed_requires_authenticated_contract_locked_dependencies_and_strict_tools(self):
        from ci.products import contract_attestation
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            catalog = b'[versions]\nkotlin="2.3.10"\nagp="9.2.1"\n'
            payload = b'authenticated aar'
            import hashlib
            digest = 'sha256:' + hashlib.sha256(payload).hexdigest()
            module = b'{"variants":[{"files":[{"name":"codex-agent-core.aar","url":"core-0.8.0.aar"}]}]}'
            manifest = {'mavenFiles': [
                {'path': 'maven/example/core/0.8.0/core-0.8.0.aar', 'sha256': digest},
                {'path': 'maven/example/core/0.8.0/core-0.8.0.module',
                 'sha256': 'sha256:' + hashlib.sha256(module).hexdigest()},
            ]}
            def blob(*args, **limits):
                if args[2].endswith('.toml'): return catalog
                if args[2].endswith('.xml'): return self.metadata('native')
                return b'# exact authenticated dependency lock\n'
            def materialize(*args, **kwargs):
                self.assertEqual('release', kwargs['required_trust_domain'])
                self.assertEqual(('android',), kwargs['required_components'])
                self.assertEqual(root / 'gradle/release/product-signing-keys.json', kwargs['keyring'])
                target = args[5] / 'maven/example/core/0.8.0'
                target.mkdir(parents=True)
                (target / 'core-0.8.0.aar').write_bytes(payload)
                (target / 'core-0.8.0.module').write_bytes(module)
                return manifest
            properties = {'codexAgent.component': 'sdk-android', 'codexAgent.contractVersion': '0.8.0', **{
                'codexAgent.' + name: str(root / name) for name in
                ('contractPayload', 'contractMetadataReceipt', 'contractAttestation',
                 'contractAttestationSignature', 'contractPublicKey')}}
            with patch.object(bootstrap, 'git_regular_blob_bytes', side_effect=blob), \
                    patch.object(contract_attestation, 'materialize_contract_payload', side_effect=materialize), \
                    patch.object(bootstrap.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                destination = root / 'android-seed'
                bootstrap.seed_sdk_maven_binary_dependencies(root, 'a' * 40, root / 'gradlew',
                    {'GITHUB_ACTIONS': 'true'}, destination, properties)
            command = run.call_args.args[0]
            self.assertIn('resolveSdkAndroidDependencies', command)
            self.assertIn('--dependency-verification=strict', command)
            self.assertNotIn('ciProductPhase', command)
            self.assertNotIn('--offline', command)
            script = (destination / 'build.gradle.kts').read_text()
            self.assertIn('androidLintTool', script)
            self.assertIn('dependencyLocking { lockAllConfigurations() }', script)
            self.assertIn('Aapt2FromMaven.create(project) { null }', script)
            settings = (destination / 'settings.gradle.kts').read_text()
            self.assertIn('exclusiveContent', settings)
            self.assertIn('contract/maven', settings)
            metadata = (destination / 'gradle/verification-metadata.xml').read_bytes()
            self.assertIn(b'name="codex-agent-core.aar"', metadata)
            self.assertIn(digest.removeprefix('sha256:').encode(), metadata)

    def test_core_seed_uses_full_signed_contract_lock_and_only_main_dependencies(self):
        from ci.products import contract_attestation
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            requested = []
            def blob(*args, **limits):
                requested.append(args[2])
                if args[2].endswith('.toml'):
                    return b'[versions]\nkotlin="2.3.10"\nagp="9.2.1"\n'
                if args[2].endswith('.xml'): return self.metadata('native')
                return b'# exact facade authenticated lock\n'
            fields = {'codexAgent.component': 'sdk-core', 'codexAgent.contractVersion': '0.8.0', **{
                'codexAgent.' + name: str(root / name) for name in
                ('contractPayload', 'contractMetadataReceipt', 'contractAttestation',
                 'contractAttestationSignature', 'contractPublicKey')}}
            with patch.object(bootstrap, 'git_regular_blob_bytes', side_effect=blob), \
                    patch.object(contract_attestation, 'materialize_contract_payload',
                        return_value={'mavenFiles': []}) as materialize, \
                    patch.object(bootstrap.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
                destination = root / 'core-seed'
                bootstrap.seed_sdk_maven_binary_dependencies(root, 'a' * 40, root / 'gradlew',
                    {}, destination, fields)
            self.assertIn('codex-agent-sdk/gradle-authenticated-contract.lockfile', requested)
            self.assertEqual(12, len(materialize.call_args.kwargs['required_components']))
            self.assertIn('node-wasm', materialize.call_args.kwargs['required_components'])
            command = run.call_args.args[0]
            self.assertIn('resolveSdkCoreDependencies', command)
            self.assertIn('--dependency-verification=strict', command)
            self.assertIn('-Pkotlin.native.distribution.type=prebuilt', command)
            self.assertNotIn('ciProductPhase', command)
            script = (destination / 'build.gradle.kts').read_text()
            for name in ('jsNpmAggregated', 'wasmJsNpmAggregated', 'kotlinKlibCommonizerClasspath',
                         'kotlinNativeBundleConfiguration', 'mingwX64CompileKlibraries',
                         'linuxArm64CompilationDependenciesMetadata'):
                self.assertIn('"' + name + '"', script)
            self.assertNotIn('findAll', script)

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
