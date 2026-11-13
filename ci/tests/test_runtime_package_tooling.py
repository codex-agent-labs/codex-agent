"""Tiny original-upload/signature fixtures; no product or tooling builds/network."""

from argparse import Namespace
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

from ci import tooling_capture, tooling_release
from ci.products import tooling
from ci.receipt import create_receipt
from ci.tests import test_tooling_release as fixture


WORKFLOW = ".github/workflows/contract-validation.yml"
BUILD_JOB = "product-validation / contract-validation / product-contracts"
SIGN_JOB = "product-validation / tooling-attestation"
_BUNDLES = {f'dependencies/kotlinx-serialization-{name}-jvm-1.9.0.jar':
            f'synthetic {name} dependency, never executed'.encode() for name in ('core', 'json')}


def profile_fixture():
    return {
        'schemaVersion': 1, 'gradleVersion': '9.7.1',
        'distribution': {'url': 'https://services.gradle.org/distributions/gradle-9.7.1-bin.zip',
                         'bytes': 151433392, 'sha256': 'a' * 64},
        'libraries': [{'relativePath': 'lib/fixture.jar', 'bytes': 1, 'sha256': 'b' * 64}],
        'excludedCompilerJars': [f'lib/kotlin-{name}-embeddable-2.4.0.jar' for name in
                                ('compiler', 'scripting-compiler', 'scripting-compiler-impl')],
        'excludedLibraries': [f'lib/kotlinx-serialization-{name}-jvm-1.11.0.jar' for name in ('core', 'json')],
        'bundledLibraries': [{'moduleId': f'org.jetbrains.kotlinx:{Path(path).name.removesuffix("-1.9.0.jar")}:1.9.0',
                             'resourcePath': path, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                            for path, raw in _BUNDLES.items()],
    }


class RuntimePackageToolingTest(unittest.TestCase):
    def setUp(self):
        class Seeded(fixture.tooling_fixture.ToolingAttestationTest):
            def make_plan(self, *args, **kwargs):
                for path in tooling._RUNTIME_PACKAGE_COMPILER_INPUTS:
                    if not (self.root / path).exists():
                        if path == tooling._RUNTIME_PACKAGE_PROFILE:
                            from ci.products.inventory import canonical_json_bytes
                            data = canonical_json_bytes(profile_fixture()).decode()
                        elif path == 'gradle/wrapper/gradle-wrapper.properties':
                            data = ('distributionUrl=https\\://services.gradle.org/distributions/gradle-9.7.1-bin.zip\n'
                                    'distributionSha256Sum=' + 'a' * 64 + '\n')
                        else:
                            data = '// fixture\n'
                        self.commit(path, data)
                return super().make_plan(*args, **kwargs)

        with mock.patch.object(fixture.tooling_fixture, "ToolingAttestationTest", Seeded):
            source = fixture.ToolingReleaseTest(methodName="runTest")
            source.setUp()
        self.addCleanup(source.doCleanups)
        self.addCleanup(source.tearDown)
        self.source = source
        source.name = f"codex-agent-ci-contracts-runtime-package-{source.producer['tree']}"
        source.jobs[0]['name'] = BUILD_JOB
        source.run['referenced_workflows'] = [{
            'path': f"{fixture.REPOSITORY}/{WORKFLOW}@{fixture.WORKFLOW_PIN}",
            'sha': fixture.WORKFLOW_PIN,
        }]
        self.files = {name: b'synthetic class, never executed' for name in tooling._RUNTIME_PACKAGE_CLASSES}
        self.files.update({
            'META-INF/MANIFEST.MF': b'Manifest-Version: 1.0\r\nMain-Class: RuntimePackageMain\r\n\r\n',
            'META-INF/runtime-package-tooling.kotlin_module': b'synthetic Kotlin module',
            'runtime-package-tooling-libraries.json': (source.repository / tooling._RUNTIME_PACKAGE_PROFILE).read_bytes(),
        })
        self.files.update(_BUNDLES)
        self.stage()
        temporary = tempfile.TemporaryDirectory(prefix='runtime-tooling-capture-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.java = self.root / 'java'
        self.java.write_bytes(b'caller Java fixture, never executed')

    def stage(self):
        source = self.source
        with zipfile.ZipFile(source.lane / tooling.JAR, 'w') as archive:
            for name, data in self.files.items():
                archive.writestr(name, data)
        create_receipt(Namespace(plan=source.plan_path, lane='contracts', output=source.lane,
            workflow_path=source.producer['workflowPath'], artifact_name=source.name,
            run_id=source.producer['runId'], run_attempt=source.producer['runAttempt'],
            runner=['os=fixture', 'arch=fixture'], toolchain=['java=fixture', 'validationActions=build'],
            artifact=[f'{tooling.JAR}=release-tooling'], evidence=[]))
        source.archive = fixture.archive_tree(source.lane)
        source.artifact = source.artifact_for(source.archive)

    def attest(self, **changes):
        args = dict(purpose='runtime-package', trusted_workflow_path=WORKFLOW, trusted_job_name=BUILD_JOB)
        args.update(changes)
        with mock.patch('reuse.api_request', side_effect=self.source.api()):
            return self.source.attest(**args)

    def capture(self, **changes):
        source = self.source
        raw = fixture.archive_tree(source.destination)
        artifact = source.artifact_for(raw)
        artifact['name'] = (f"codex-agent-runtime-package-tooling-{source.producer['tree']}"
                            f"-attempt-{source.producer['runAttempt']}")
        jobs = copy.deepcopy(source.jobs)
        jobs[0]['name'] = SIGN_JOB
        args = dict(artifact_id=artifact['id'], artifact_sha256=artifact['digest'],
            transport_producer=source.producer, trusted_workflow_sha=fixture.WORKFLOW_PIN,
            policy_revision=source.source_sha, java_executable=self.java, token='not-a-real-token',
            trusted_workflow_path=WORKFLOW, trusted_job_name=SIGN_JOB, tooling_use='runtime-package')
        args.update(changes)
        with mock.patch('reuse.api_request', side_effect=source.api(
                jobs=jobs, artifact=artifact, archive=raw)):
            return tooling_capture.capture_tooling_ci(self.root / 'capture', source.repository, **args)

    def test_original_signature_capture_and_private_lifetime_with_distinct_role(self):
        receipt = (self.source.lane / 'lane-receipt.json').read_bytes()
        self.attest()
        policy = self.capture()
        with tooling.verified_tooling_capture(Path(policy['evidence']), self.source.repository,
                Path(policy['publicKey']), required_trust_domain='release',
                keyring=Path(policy['keyring']), keys_directory=Path(policy['keysDirectory']),
                policy_revision=self.source.source_sha, use='runtime-package') as private:
            self.assertEqual((self.source.lane / tooling.JAR).read_bytes(), private.read_bytes())
        self.assertFalse(private.exists())
        self.assertEqual(receipt, (Path(policy['evidence']) / 'original/lane/lane-receipt.json').read_bytes())
        self.assertEqual(1, json.loads((Path(policy['evidence']) / tooling.ATTESTATION).read_bytes())['schemaVersion'])

    def test_incomplete_or_cross_purpose_jar_rejected_before_signing_key(self):
        self.source.environment.forbid_secret = True
        for kind in ('missing-class', 'sdk-resource', 'profile', 'bundle'):
            before = dict(self.files)
            if kind == 'missing-class':
                del self.files['RuntimePackageMain.class']
            elif kind == 'sdk-resource':
                self.files['python/ci/products/sdk_package.py'] = b'wrong purpose'
            elif kind == 'profile':
                self.files['runtime-package-tooling-libraries.json'] += b'changed'
            else:
                self.files[next(iter(_BUNDLES))] += b'changed'
            self.stage()
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, 'Runtime package tooling'):
                self.attest()
            self.files = before
        self.assertEqual(0, self.source.environment.secret_reads)

    def test_runtime_source_change_rejects_signing_before_key_read(self):
        self.source.environment.forbid_secret = True
        self.source.fixture.commit('runtime/build-logic/src/main/kotlin/RuntimeReleaseIo.kt', '// changed\n')
        from ci.products.inventory import run_git
        current = run_git(self.source.repository, 'rev-parse', 'HEAD').strip()
        with mock.patch.object(tooling_release, 'verify_product_release_context', return_value=(
                self.source.repository, self.source.producer, self.source.producer['tree'], {}, 'fixture')):
            with self.assertRaisesRegex(ValueError, 'Runtime package compiler/build inputs differ'):
                self.attest(trusted_source_sha=current)
        self.assertEqual(0, self.source.environment.secret_reads)

    def test_runtime_requires_explicit_job_and_rejects_sdk_recovery(self):
        for changes in ({'trusted_job_name': None}, {'trusted_workflow_path': None},
                        {'original_tooling': tooling_release.RETAINED_UNSIGNED_TOOLING}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'exact original workflow/job'):
                self.attest(**changes)
        self.assertEqual(0, self.source.environment.secret_reads)
        self.attest()
        with self.assertRaisesRegex(ValueError, 'exact original workflow/job'):
            self.capture(trusted_job_name=None)

    def test_wrong_job_signature_and_late_mutation_remain_rejected(self):
        self.attest()
        with self.assertRaises(ValueError):
            self.capture(trusted_job_name='different job')
        policy = self.capture()
        evidence = Path(policy['evidence'])
        args = dict(required_trust_domain='release', keyring=Path(policy['keyring']),
                    keys_directory=Path(policy['keysDirectory']), policy_revision=self.source.source_sha,
                    use='runtime-package')
        with self.assertRaisesRegex(ValueError, 'changed during use'):
            with tooling.verified_tooling_capture(evidence, self.source.repository, Path(policy['publicKey']), **args) as private:
                private.write_bytes(b'changed after authentication')
        signature = evidence / tooling.SIGNATURE
        signature.write_bytes(b'wrong signature')
        with self.assertRaises(ValueError), tooling.verified_tooling_capture(
                evidence, self.source.repository, Path(policy['publicKey']), **args):
            self.fail('wrong signature admitted')

    def test_build_recipe_does_not_compile_or_package_sdk_or_all_runtime_sources(self):
        root = Path(__file__).resolve().parents[2]
        text = (root / '.github/actions/run-ci-lane/runtime_package_tooling.init.gradle').read_text()
        for token in ('DesktopRuntimePackageTask', 'DesktopRuntimeZipModes', 'RuntimeReleaseIo', 'RuntimeDownload',
                      "owner.configurations.named('compileClasspath')", 'original.compilerOptions', 'checkLibraries()'):
            self.assertIn(token, text)
        for token in ('sourceSets.main', "dependsOn('classes')", 'releaseToolingJar', 'buildCSharpRuntimeInspector'):
            self.assertNotIn(token, text)
        self.assertNotIn('.github/actions/run-ci-lane/runtime_package_tooling.init.gradle', tooling._COMPILER_INPUTS)


class RuntimePackageToolingCliTest(unittest.TestCase):
    def test_fixed_purpose_and_explicit_job_survive_both_cli_boundaries(self):
        from ci.products.inventory import write_canonical_json
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            event = root / 'event.json'
            write_canonical_json(event, {'number': 31})
            shared = ['--repository-root', str(root), '--destination', str(root / 'out'),
                      '--trusted-workflow-sha', 'b' * 40, '--trusted-workflow-path', WORKFLOW,
                      '--purpose', 'runtime-package']
            env = {'GITHUB_EVENT_PATH': str(event), 'GITHUB_EVENT_NAME': 'pull_request',
                   'GITHUB_REPOSITORY': fixture.REPOSITORY, 'GITHUB_SHA': 'c' * 40,
                   'GITHUB_RUN_ID': '31', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_TOKEN': 'fixture'}
            with mock.patch.dict(os.environ, env, clear=True), \
                    mock.patch.object(tooling_release, 'attest_tooling_ci') as sign, \
                    mock.patch.object(tooling_capture, 'capture_tooling_ci') as capture:
                self.assertEqual(0, tooling_release.main(shared + [
                    '--plan', str(root / 'plan'), '--trusted-source-sha', 'a' * 40,
                    '--validation-tree', 'd' * 40, '--trusted-job-name', BUILD_JOB]))
                self.assertEqual('runtime-package', sign.call_args.kwargs['purpose'])
                self.assertEqual(BUILD_JOB, sign.call_args.kwargs['trusted_job_name'])
                self.assertEqual(0, tooling_capture.main(shared + [
                    '--transport-producer', str(event), '--java-executable', str(root / 'java'),
                    '--artifact-id', '7', '--artifact-sha256', 'sha256:' + 'e' * 64,
                    '--policy-revision', 'a' * 40, '--trusted-job-name', SIGN_JOB]))
                self.assertEqual('runtime-package', capture.call_args.kwargs['tooling_use'])
                self.assertEqual(SIGN_JOB, capture.call_args.kwargs['trusted_job_name'])


if __name__ == '__main__':
    unittest.main()
