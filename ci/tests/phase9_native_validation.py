"""Validate the preserved Mac x64 package on Intel; development evidence only.

No Runtime source build, Contract resolution, binary/package production or release
admission. The pinned local executor is NOT the signed release-toolkit artifact.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'ci')]

from ci.tests.phase9_ios_mutation import git
from ci.tests.phase9_ios_package_check import receive
from products.inventory import (canonical_json_bytes, git_product_versions,
    load_canonical_json_bytes, read_regular_file_bytes, sha256_bytes, sha256_file,
    write_canonical_json)
from products.plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase
from products.receipt import (output_inventory_digest, validate_phase_receipt,
    validate_producer, verify_output_manifest_identity, write_phase_receipt)
from products.registry import PhaseInstanceId, required_contract_components
from products.runtime_validation_projection import project_native_validation_stage
from products.selection import phase_git_inventory

FIXTURES = Path(__file__).with_name('fixtures')
TRANSFER_SHA256 = 'sha256:57637ce9d3846178bcf08f0b6a1321b6510b1fe91dc2d7fc520d583e131c9d3b'
LABEL = 'ci:phase9-native-artifact-validation'
INSTANCE = PhaseInstanceId('runtime', 'macos-x64', 'validation', 'macos-x64')
TASK = ':codex-agent-runtime-desktop:writeMacosX64RuntimeValidationOutputManifest'


def specification():
    raw = read_regular_file_bytes(FIXTURES / 'phase9-native-validation-transfer.json',
                                  reject_symlink_parents=True)
    if sha256_bytes(raw) != TRANSFER_SHA256:
        raise ValueError('Native validation transfer differs from reviewed original pins')
    return load_canonical_json_bytes(raw)


def prepare(inputs, revision):
    """Authenticate only consumed bytes, original lineage and the current V key."""
    spec = specification()
    for row in spec['files']:
        path = inputs / row['relativePath']
        raw = read_regular_file_bytes(path, reject_symlink_parents=True)
        if len(raw) != row['bytes'] or sha256_bytes(raw) != row['sha256']:
            raise ValueError('Native validation input differs from its immutable original')
    receipts = {phase: validate_phase_receipt(load_canonical_json_bytes(
        read_regular_file_bytes(inputs / 'receipts' / (phase + '.json'))))
        for phase in ('binary', 'package')}
    for phase, receipt in receipts.items():
        if (receipt['producer'] != spec['originalProducer'] or receipt['trustDomain'] != 'development'
                or receipt['buildKey'] != spec[phase + 'BuildKey']
                or [receipt[name] for name in ('product', 'component', 'phase', 'target', 'productVersion')]
                != ['runtime', 'macos-x64', phase, 'macos-x64', spec['productVersion']]):
            raise ValueError('Original native phase identity/provenance mismatch')
    binary = receipts['binary']
    predecessor = {key: binary[key] for key in ('product', 'component', 'phase', 'target', 'buildKey')}
    predecessor['outputsDigest'] = output_inventory_digest(binary['outputs'])
    if receipts['package']['inputs']['upstreamArtifacts'] != [predecessor]:
        raise ValueError('Original package does not bind the preserved binary')
    package = verify_output_manifest_identity(inputs / 'package', 'runtime', 'macos-x64',
        'package', 'macos-x64', spec['productVersion'])
    if package['outputs'] != receipts['package']['outputs']:
        raise ValueError('Original package output inventory changed')
    if (required_contract_components(INSTANCE)
            or git('rev-parse', revision + ':runtime/build-logic') != spec['buildLogicTree']):
        raise ValueError('Artifact executor source/Contract boundary changed')
    plan = plan_phase(INSTANCE, inventory=phase_git_inventory(ROOT, revision, INSTANCE),
        versions=git_product_versions(ROOT, revision), upstream_receipts=[receipts['package']],
        toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST, flags_digest=NOT_APPLICABLE_FLAGS_DIGEST)
    if (plan['buildKey'] != spec['validationBuildKey']
            or plan['inputs']['phaseInputDigest'] != spec['validationInputDigest']):
        raise ValueError('Validation inputs/key changed; do not execute an obsolete election')
    return plan


def hosted_context():
    revision = git('rev-parse', 'HEAD')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    pr = event.get('pull_request', {})
    head = pr.get('head', {})
    repository = 'codex-agent-labs/codex-agent'
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_EVENT_NAME') != 'pull_request'
            or os.environ.get('GITHUB_REPOSITORY') != repository or pr.get('number') != 31
            or head.get('repo', {}).get('full_name') != repository or head.get('repo', {}).get('fork') is not False
            or head.get('sha') != revision or event.get('label', {}).get('name') != LABEL
            or git('diff', 'HEAD', '--')):
        raise ValueError('Native validation requires its exact same-repository labeled PR source')
    from native_wrappers import host_classifier
    translated = subprocess.run(['/usr/sbin/sysctl', '-n', 'sysctl.proc_translated'],
        capture_output=True, text=True)
    xcode = subprocess.check_output(['/usr/bin/xcodebuild', '-version'], text=True)
    if (host_classifier() != 'macos-x64' or os.environ.get('RUNNER_ARCH') != 'X64'
            or translated.stdout.strip() not in ('', '0')
            or xcode.strip() != 'Xcode 26.6\nBuild version 17F113'):
        raise ValueError('Native validation requires real Intel and the reviewed Xcode installation')
    producer = validate_producer(dict(commit=revision, tree=git('rev-parse', 'HEAD^{tree}'),
        repository=repository, event='pull_request', pullRequest=31,
        workflowPath='.github/workflows/portable-reuse-proof.yml',
        runId=int(os.environ['GITHUB_RUN_ID']), runAttempt=int(os.environ['GITHUB_RUN_ATTEMPT'])))
    return dict(producer=producer, workflowEventCommit=os.environ['GITHUB_SHA'], xcode=xcode,
        java=subprocess.check_output(['java', '-version'], stderr=subprocess.STDOUT, text=True),
        runnerOS=os.environ['RUNNER_OS'], runnerArch=os.environ['RUNNER_ARCH'],
        image=os.environ.get('ImageOS'), imageVersion=os.environ.get('ImageVersion'),
        translationProbe=dict(exitCode=translated.returncode, stdout=translated.stdout, stderr=translated.stderr),
        productBuilds=0, releaseAdmission=False)


def hosted(destination, storage):
    context = hosted_context()  # Source/host guard before any artifact acquisition.
    spec = specification()
    destination.mkdir()
    write_canonical_json(destination / 'context.json', context)
    started = time.monotonic_ns()
    inputs = destination / 'inputs'
    intake = receive(spec['files'], inputs, storage)
    write_canonical_json(destination / 'intake.json', intake)
    tick = time.monotonic_ns()
    producer = context['producer']
    plan = prepare(inputs, producer['commit'])
    write_canonical_json(destination / 'plan.json', plan)
    preparation_ns = time.monotonic_ns() - tick
    fixture = destination / 'executor'
    shutil.copytree(FIXTURES / 'phase9-native-validation', fixture)
    execution_context = dict(classpath=[str(inputs / row['relativePath']) for row in spec['files']
        if row['relativePath'].startswith('executor/')], packageStage=str(inputs / 'package'),
        repositoryRoot=str(ROOT), evidenceRoot=str(destination / 'reports'), stageRoot=str(destination / 'stage'),
        producerCommit=producer['commit'], producerTree=producer['tree'])
    write_canonical_json(destination / 'executor-context.json', execution_context)
    command = [str(ROOT / 'gradlew'), '-p', str(fixture), '--offline', '--no-daemon',
        '--no-configuration-cache', '--max-workers=2', '--console=plain',
        '-Pphase9.context=' + str(destination / 'executor-context.json'), TASK]
    tick = time.monotonic_ns()
    with (destination / 'validation.log').open('xb') as log:
        process = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            env=dict(os.environ, GH_TOKEN='', GITHUB_TOKEN=''))
    execution_ns = time.monotonic_ns() - tick
    write_canonical_json(destination / 'execution.json', dict(command=command, exitCode=process.returncode,
        elapsedNs=execution_ns, logSha256=sha256_file(destination / 'validation.log')))
    if process.returncode:
        raise ValueError('Native validation failed; preserve diagnostics and do not emit a receipt')
    # Preserve raw producer-bearing reports separately; only verified stable facts enter the phase.
    project_native_validation_stage(destination / 'stage', inputs / 'package', destination / 'raw',
        target='macos-x64', version=spec['productVersion'], producer=producer)
    receipt = write_phase_receipt(destination / 'stage', destination, 'runtime', 'macos-x64', 'validation',
        'macos-x64', spec['productVersion'], plan['buildKey'], plan['inputs'], producer, 'development')
    result = dict(passed=True, buildKey=receipt['buildKey'], originalProducer=spec['originalProducer'],
        verifier=context, intake=intake, preparationNs=preparation_ns, executionNs=execution_ns,
        elapsedNs=time.monotonic_ns()-started, receiptSha256=sha256_file(destination / 'phase-receipt.json'),
        productBuilds=0, releaseAdmission=False)
    write_canonical_json(destination / 'result.json', result)
    print(canonical_json_bytes(result).decode(), flush=True)


WINDOWS_LABEL = 'ci:phase9-native-windows-artifact-validation'
WINDOWS_TRANSFER_SHA256 = 'sha256:e874f177105798d3b95d0506302dd8e25160f083f3a6eddf99115356be5a6e8c'
WINDOWS_INSTANCE = PhaseInstanceId('runtime', 'windows-x64', 'validation', 'windows-x64')
WINDOWS_TASK = ':codex-agent-runtime-desktop:writeMingwX64RuntimeValidationOutputManifest'


def windows_specification():
    from ci.tests import phase9_ios_mutation as mutation
    from ci.tests.phase9_runtime_mutation import WINDOWS_BUNDLE, WINDOWS_SOURCE, WINDOWS_TREE
    raw = read_regular_file_bytes(FIXTURES / 'phase9-native-windows-validation-transfer.json',
                                  reject_symlink_parents=True)
    if sha256_bytes(raw) != WINDOWS_TRANSFER_SHA256:
        raise ValueError('Windows validation transfer differs from reviewed original pins')
    spec = load_canonical_json_bytes(raw)
    source_rows = [row for row in spec['files'] if row['relativePath'].startswith('source/')]
    old_source = [row for row in mutation.manifest()['files']
                  if row['relativePath'] == 'source/mutation-source.bundle']
    if (spec['purpose'] != 'phase9-native-windows-artifact-validation'
            or (spec['sourceCommit'], spec['sourceTree']) != (WINDOWS_SOURCE, WINDOWS_TREE)
            or source_rows != [*old_source, WINDOWS_BUNDLE]
            or [row for row in spec['files'] if row['relativePath'].startswith('executor/')]
                != [row for row in specification()['files'] if row['relativePath'].startswith('executor/')]):
        raise ValueError('Windows validation must reuse the exact source bundles and reviewed executor')
    return spec


def prepare_windows(inputs, source):
    """Exact original hosted B/local P lineage; no B bodies or Contract intake."""
    spec = windows_specification()
    for row in spec['files']:
        if row['relativePath'].startswith(('source/', 'package/outputs/')):
            continue  # Source helper verifies bundles; the complete package verifier checks outputs once.
        raw = read_regular_file_bytes(inputs / row['relativePath'], reject_symlink_parents=True)
        if len(raw) != row['bytes'] or sha256_bytes(raw) != row['sha256']:
            raise ValueError('Windows validation control/executor differs from its immutable original')
    receipts = {phase: validate_phase_receipt(load_canonical_json_bytes(
        read_regular_file_bytes(inputs / 'receipts' / (phase + '.json'), reject_symlink_parents=True)))
        for phase in ('binary', 'package')}
    for phase, receipt in receipts.items():
        if (receipt['producer'] != spec[phase + 'Producer'] or receipt['trustDomain'] != 'development'
                or receipt['result'] != 'success' or receipt['buildKey'] != spec[phase + 'BuildKey']
                or [receipt[name] for name in ('product', 'component', 'phase', 'target', 'productVersion')]
                != ['runtime', 'windows-x64', phase, 'windows-x64', spec['productVersion']]):
            raise ValueError('Original Windows phase identity/provenance mismatch')
    binary, package = receipts['binary'], receipts['package']
    predecessor = {key: binary[key] for key in ('product', 'component', 'phase', 'target', 'buildKey')}
    predecessor['outputsDigest'] = output_inventory_digest(binary['outputs'])
    if package['inputs']['upstreamArtifacts'] != [predecessor]:
        raise ValueError('Original Windows package does not bind the hosted binary')
    records = [dict(relativePath='package/' + row['relativePath'], bytes=row['bytes'], sha256=row['sha256'])
               for row in package['outputs']]
    if records != [row for row in spec['files'] if row['relativePath'].startswith('package/outputs/')]:
        raise ValueError('Windows package transfer must contain exactly its seven original outputs')
    verified = verify_output_manifest_identity(inputs / 'package', 'runtime', 'windows-x64',
        'package', 'windows-x64', spec['productVersion'])
    if verified['outputs'] != package['outputs']:
        raise ValueError('Original Windows package output inventory changed')
    if (required_contract_components(WINDOWS_INSTANCE)
            or git('rev-parse', 'HEAD', cwd=source) != spec['sourceCommit']
            or git('rev-parse', 'HEAD^{tree}', cwd=source) != spec['sourceTree']
            or git('rev-parse', spec['sourceCommit'] + ':runtime/build-logic', cwd=source) != spec['buildLogicTree']):
        raise ValueError('Windows artifact executor source/Contract boundary changed')
    plan = plan_phase(WINDOWS_INSTANCE, inventory=phase_git_inventory(source, spec['sourceCommit'], WINDOWS_INSTANCE),
        versions=git_product_versions(source, spec['sourceCommit']), upstream_receipts=[package],
        toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST, flags_digest=NOT_APPLICABLE_FLAGS_DIGEST)
    if (plan['buildKey'] != spec['validationBuildKey']
            or plan['inputs']['phaseInputDigest'] != spec['validationInputDigest']):
        raise ValueError('Windows validation inputs/key changed; do not execute an obsolete election')
    return plan


def windows_hosted_context():
    from native_wrappers import host_classifier
    from products.signing_isolation import require_no_signing_secret
    require_no_signing_secret(os.environ)
    revision = git('rev-parse', 'HEAD')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    pr = event.get('pull_request', {})
    head = pr.get('head', {})
    repository = 'codex-agent-labs/codex-agent'
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_EVENT_NAME') != 'pull_request'
            or os.environ.get('GITHUB_REPOSITORY') != repository or pr.get('number') != 31
            or head.get('repo', {}).get('full_name') != repository or head.get('repo', {}).get('fork') is not False
            or head.get('sha') != revision or event.get('label', {}).get('name') != WINDOWS_LABEL
            or git('diff', 'HEAD', '--')):
        raise ValueError('Windows validation requires its exact same-repository labeled PR source')
    if (host_classifier(), os.environ.get('RUNNER_OS'), os.environ.get('RUNNER_ARCH')) != ('windows-x64', 'Windows', 'X64'):
        raise ValueError('Windows validation requires the real Windows x64 host')
    if any(shutil.which(tool) is None for tool in ('java', 'cl', 'gcc', 'g++', 'dumpbin', 'lib', 'nm')):
        raise ValueError('Windows validation requires all existing MSVC/GNU consumer tools')
    java_home = Path(os.environ.get('JAVA_HOME', ''))
    java_executable = java_home / 'bin/java.exe'
    if not java_home.is_absolute() or not java_executable.is_file():
        raise ValueError('Windows validation requires the selected absolute JAVA_HOME')
    java = subprocess.check_output([str(java_executable), '-version'], stderr=subprocess.STDOUT, text=True)
    msvc = subprocess.run(['cl'], capture_output=True, text=True)
    if ('version "17.' not in java or msvc.returncode not in (0, 2)
            or 'Microsoft' not in msvc.stdout + msvc.stderr):
        raise ValueError('Windows validation requires the selected Java17/MSVC environment')
    producer = validate_producer(dict(commit=revision, tree=git('rev-parse', 'HEAD^{tree}'),
        repository=repository, event='pull_request', pullRequest=31,
        workflowPath='.github/workflows/portable-reuse-proof.yml',
        runId=int(os.environ['GITHUB_RUN_ID']), runAttempt=int(os.environ['GITHUB_RUN_ATTEMPT'])))
    return dict(producer=producer, workflowEventCommit=os.environ['GITHUB_SHA'], java=java,
        javaExecutable=str(java_executable),
        msvc=dict(returnCode=msvc.returncode, stdout=msvc.stdout, stderr=msvc.stderr),
        runnerOS=os.environ['RUNNER_OS'], runnerArch=os.environ['RUNNER_ARCH'],
        image=os.environ.get('ImageOS'), imageVersion=os.environ.get('ImageVersion'),
        productBuilds=0, releaseAdmission=False)


def hosted_windows(destination, storage):
    from ci.tests import phase9_ios_mutation as mutation
    from ci.tests.phase9_runtime_mutation import prepare_windows_source
    from product_reuse import _runtime_worker_checkout, _runtime_worker_environment
    from products.inventory import regular_file_inventory
    controller = windows_hosted_context()  # Actual host/tool/event rejection precedes every transfer.
    spec = windows_specification()
    started = time.monotonic_ns()
    prepared, _ = prepare_windows_source(destination, storage)  # Only the two existing tiny bundles.
    source = destination / 'source'
    producer = dict(controller['producer'], commit=spec['sourceCommit'], tree=spec['sourceTree'])
    context = dict(controller=controller, fixtureExecution=producer,
        scope='Actual Windows validation of the private source; controller and original B/P producers stay distinct.')
    write_canonical_json(destination / 'context.json', context)
    with mutation.fixture_environment(prepared['environment']):
        _runtime_worker_checkout(source, producer)
        if git('rev-parse', spec['sourceCommit'] + ':runtime/build-logic', cwd=source) != spec['buildLogicTree']:
            raise ValueError('Existing executor source differs; stop before package intake')
        inputs = destination / 'inputs'
        intake = receive([row for row in spec['files'] if not row['relativePath'].startswith('source/')], inputs, storage)
        write_canonical_json(destination / 'intake.json', intake)
        tick = time.monotonic_ns()
        plan = prepare_windows(inputs, source)
        write_canonical_json(destination / 'plan.json', plan)
        preparation_ns = time.monotonic_ns() - tick
        source_inputs = regular_file_inventory(destination / 'source-inputs')
        fixture = destination / 'executor'
        fixture.mkdir()
        (fixture / 'codex-agent-runtime-desktop').mkdir()
        shutil.copyfile(FIXTURES / 'phase9-native-validation/settings.gradle', fixture / 'settings.gradle')
        shutil.copyfile(FIXTURES / 'phase9-native-validation-windows.gradle',
            fixture / 'codex-agent-runtime-desktop/build.gradle')
        execution_context = dict(classpath=[str(inputs / row['relativePath']) for row in spec['files']
            if row['relativePath'].startswith('executor/')], packageStage=str(inputs / 'package'),
            repositoryRoot=str(source), evidenceRoot=str(destination / 'reports'), stageRoot=str(destination / 'stage'),
            producerCommit=producer['commit'], producerTree=producer['tree'])
        write_canonical_json(destination / 'executor-context.json', execution_context)
        fixture_inventory = {name: sha256_file(fixture / name) for name in
            ('settings.gradle', 'codex-agent-runtime-desktop/build.gradle')}
        execution_context_sha256 = sha256_file(destination / 'executor-context.json')
        environment, wrapper = _runtime_worker_environment(source, producer, destination / 'diagnostics', os.environ)
        java = Path(environment['JAVA_HOME']) / 'bin/java.exe'
        if not java.is_absolute() or not java.is_file():
            raise ValueError('Windows validation requires its exact selected Java launcher')
        command = [str(java), '-Xmx64m', '-Xms64m', '-Dorg.gradle.appname=gradlew', '-jar',
            str(wrapper.parent / 'gradle/wrapper/gradle-wrapper.jar'), '-p', str(fixture), '--offline',
            '--no-daemon', '--no-configuration-cache', '--max-workers=2', '--console=plain',
            '-Pphase9.context=' + str(destination / 'executor-context.json'), WINDOWS_TASK]
        tick = time.monotonic_ns()
        with (destination / 'validation.log').open('xb') as log:
            process = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT,
                env=dict(environment, GH_TOKEN='', GITHUB_TOKEN=''))
        execution_ns = time.monotonic_ns() - tick
        write_canonical_json(destination / 'execution.json', dict(command=command, exitCode=process.returncode,
            elapsedNs=execution_ns, logSha256=sha256_file(destination / 'validation.log')))
        if process.returncode:
            raise ValueError('Windows validation failed; preserve diagnostics and do not emit a receipt')
        _runtime_worker_checkout(source, producer)
        if (prepare_windows(inputs, source) != plan
                or regular_file_inventory(destination / 'source-inputs') != source_inputs
                or any(sha256_file(fixture / name) != digest for name, digest in fixture_inventory.items())
                or sha256_file(destination / 'executor-context.json') != execution_context_sha256
                or (destination / 'diagnostics/python-bytecode').exists()):
            raise ValueError('Windows validation changed its original inputs, source or Python lifetime')
        project_native_validation_stage(destination / 'stage', inputs / 'package', destination / 'raw',
            target='windows-x64', version=spec['productVersion'], producer=producer)
        receipt = write_phase_receipt(destination / 'stage', destination, 'runtime', 'windows-x64', 'validation',
            'windows-x64', spec['productVersion'], plan['buildKey'], plan['inputs'], producer, 'development')
        result = dict(passed=True, buildKey=receipt['buildKey'],
            originalProducers={phase: spec[phase + 'Producer'] for phase in ('binary', 'package')},
            verifier=context, intake=intake, preparationNs=preparation_ns, executionNs=execution_ns,
            elapsedNs=time.monotonic_ns()-started, receiptSha256=sha256_file(destination / 'phase-receipt.json'),
            productBuilds=0, validationExecutions=1, releaseAdmission=False)
        write_canonical_json(destination / 'result.json', result)
        print(canonical_json_bytes(result).decode(), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == '--windows':
        hosted_windows(*(Path(argument).resolve() for argument in sys.argv[2:]))
    elif len(sys.argv) == 3:
        hosted(*(Path(argument).resolve() for argument in sys.argv[1:]))
    else:
        raise SystemExit('usage: phase9_native_validation.py [--windows] DESTINATION LFS_STORAGE')
