"""One hosted content check of preserved local iOS B/P; never a product build.

Original local producers and four explicitly synthetic Runtime targets remain
unchanged. The hosted verifier's observations are separate, not phase admission.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'ci'))

from ci.tests import phase9_ios_mutation as mutation
from products.inventory import (canonical_json_bytes, git_regular_blob_bytes,
    load_canonical_json_bytes, read_regular_file_bytes, require_relative_path,
    require_regular_directory, sha256_bytes, sha256_file, write_canonical_json)
from products.restore import verification_session
from products.sdk_apple_content import copy_apple_file
from products.sdk_apple_package_source import _PIN_FILE, _toolchain_expectations
from products.sdk_apple_toolchain_evidence import _versions
from products.sdk_compatibility import load_sdk_compatibility_request
from products.sdk_package import verify_sdk_package_inputs

TRANSFER_SHA256 = 'sha256:a39a4bc1d44b22377078527e8c881780d6e6ef82073790f2e35fd5d1eaddada8'
LABEL = 'ci:phase9-ios-package-check'


def specification():
    raw = read_regular_file_bytes(Path(__file__).with_name('fixtures') /
        'phase9-ios-package-transfer.json', reject_symlink_parents=True)
    if sha256_bytes(raw) != TRANSFER_SHA256:
        raise ValueError('Package check transfer differs from reviewed original pins')
    result = load_canonical_json_bytes(raw)
    if (result['originalSource'] != mutation.manifest()['sourceCommit']
            or result['originalTree'] != mutation.manifest()['sourceTree']
            or result['originalTrustDomain'] != 'development'
            or result['purpose'] != 'phase9-ios-package-verification-only'
            or result['fixtureRuntimeTargets'] != ['linux-arm64', 'linux-x64', 'macos-x64', 'windows-x64']):
        raise ValueError('Package check cannot change original source or fixture scope')
    names = [require_relative_path(row['relativePath'], 'Package check input') for row in result['files']]
    if names != sorted(set(names)) or any(name.split('/')[0] not in
            {'binary', 'package', 'receipts', 'fixture', 'sdk-inputs', 'tooling'} for name in names):
        raise ValueError('Package check input inventory is not exact and unique')
    return result


def receive(records, destination, storage):
    """One acquisition per digest; independent clones, no writable cache aliases."""
    require_regular_directory(storage, 'Package check LFS cache')
    if storage.resolve(strict=True) != storage:
        raise ValueError('Package check cache must be normalized')
    destination.mkdir()
    environment = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_CONFIG_COUNT='4',
        GIT_CONFIG_KEY_0='lfs.storage', GIT_CONFIG_VALUE_0=str(storage),
        GIT_CONFIG_KEY_1='lfs.url', GIT_CONFIG_VALUE_1=mutation.LFS_URL,
        GIT_CONFIG_KEY_2='credential.helper', GIT_CONFIG_VALUE_2='',
        GIT_CONFIG_KEY_3='credential.helper', GIT_CONFIG_VALUE_3='!gh auth git-credential')
    environment.pop('GIT_LFS_SKIP_SMUDGE', None)
    unique = {row['sha256']: row for row in records}
    started = time.monotonic_ns()
    with ThreadPoolExecutor(max_workers=4) as pool:
        objects = dict(zip(unique, pool.map(
            lambda row: mutation.lfs_object(row, storage, environment, ('git', 'lfs')), unique.values())))
    acquired = time.monotonic_ns()
    for row in records:
        target = destination / require_relative_path(row['relativePath'], 'Package check input')
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_apple_file(objects[row['sha256']][0], target)
        if target.stat().st_size != row['bytes'] or target.stat().st_nlink != 1:
            raise ValueError('Package check requires independent exact input files')
    return dict(uniqueObjects=len(unique), downloadedBytes=sum(value[1] for value in objects.values()),
        uniqueBytes=sum(row['bytes'] for row in unique.values()), acquisitionNs=acquired-started,
        materializationNs=time.monotonic_ns()-acquired, elapsedNs=time.monotonic_ns()-started)


def hosted_context():
    source = mutation.git('rev-parse', 'HEAD')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    pr = event.get('pull_request', {})
    head = pr.get('head', {})
    repository = 'codex-agent-labs/codex-agent'
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_EVENT_NAME') != 'pull_request'
            or os.environ.get('GITHUB_REPOSITORY') != repository or pr.get('number') != 31
            or head.get('repo', {}).get('full_name') != repository
            or head.get('repo', {}).get('fork') is not False or head.get('sha') != source
            or event.get('label', {}).get('name') != LABEL or mutation.git('diff', 'HEAD', '--')):
        raise ValueError('Package check requires its exact same-repository labeled PR source')
    from native_wrappers import host_classifier
    if host_classifier() != 'macos-arm64':
        raise ValueError('Package check requires a genuine macOS ARM64 runner')
    tools = _toolchain_expectations(git_regular_blob_bytes(ROOT,
        mutation.manifest()['sourcePrerequisite'], _PIN_FILE, max_bytes=1024*1024))
    xcode = subprocess.check_output(['/usr/bin/xcodebuild', '-version'], text=True)
    swift = subprocess.check_output(['/usr/bin/xcrun', 'swift', '--version'], text=True)
    _versions(xcode, swift, tools)
    if shutil.disk_usage(ROOT).free < 60*1024**3:
        raise ValueError('Package check needs scratch headroom before input transfer')
    return dict(sourceCommit=source, sourceTree=mutation.git('rev-parse', 'HEAD^{tree}'),
        workflowEventCommit=os.environ['GITHUB_SHA'], runId=int(os.environ['GITHUB_RUN_ID']),
        runAttempt=int(os.environ['GITHUB_RUN_ATTEMPT']), runnerOS=os.environ['RUNNER_OS'],
        runnerArch=os.environ['RUNNER_ARCH'], image=os.environ.get('ImageOS'),
        imageVersion=os.environ.get('ImageVersion'), xcode=xcode, swift=swift,
        availableBytes=shutil.disk_usage(ROOT).free, productBuilds=0, releaseAdmission=False)


def hosted(destination, storage, java):
    context = hosted_context()  # Wrong source/host/capacity fails before bulk intake.
    spec = specification()
    destination.mkdir()
    write_canonical_json(destination / 'context.json', context)
    started = time.monotonic_ns()
    inputs = destination / 'inputs'
    intake = receive(spec['files'], inputs, storage)
    write_canonical_json(destination / 'intake.json', intake)
    if shutil.disk_usage(destination).free < 48*1024**3:
        raise ValueError('Insufficient private replay headroom; retained B/P stay untouched')
    fixture, environment = mutation.source_fixture(destination, inputs / 'fixture')
    request = inputs / 'sdk-inputs/sdk-compatibility-request.json'
    arguments = load_sdk_compatibility_request(request)
    contract = inputs / 'fixture/contract'
    receipt = load_canonical_json_bytes(read_regular_file_bytes(contract / 'metadata-receipt.json'))
    stage = destination / 'contract-stage'
    (stage / 'outputs').mkdir(parents=True)
    copy_apple_file(contract / (mutation.STEM + '.zip'), stage / 'outputs' / (mutation.STEM + '.zip'))
    write_canonical_json(stage / 'output-manifest.json', dict(schemaVersion=1,
        **{key: receipt[key] for key in ('product', 'component', 'phase', 'target', 'productVersion', 'outputs')}))
    evidence = dict(stageRoot=str(stage), phaseReceipt=str(contract / 'metadata-receipt.json'),
        attestation=str(arguments['contract_attestation']),
        attestationSignature=str(arguments['contract_attestation_signature']),
        publicKey=str(arguments['contract_public_key']), expectedTrustDomain='development',
        keyring=None, keysDirectory=None)
    apple = dict(developer_directory=Path(os.environ['DEVELOPER_DIR']).resolve(strict=True),
        repository=fixture, tooling_evidence=inputs / 'tooling/evidence',
        tooling_public_key=inputs / 'tooling/policy/keys/product-2026-09.pub', java_executable=java,
        policy_revision=spec['originalSource'], required_trust_domain='development',
        tooling_keyring=inputs / 'tooling/policy/product-signing-keys.json',
        tooling_keys_directory=inputs / 'tooling/policy/keys')
    receipts = {phase: inputs / 'receipts' / (phase + '.json') for phase in ('binary', 'package')}
    for phase, path in receipts.items():
        if sha256_file(path) != spec[phase + 'ReceiptSha256']:
            raise ValueError('Original local receipt changed')
    tick = time.monotonic_ns()
    with mutation.fixture_environment(environment), verification_session():
        verified, raw = verify_sdk_package_inputs(fixture, inputs / 'package', receipts['package'], request,
            binary_stage_root=inputs / 'binary', binary_receipt_path=receipts['binary'],
            binary_contract_evidence=evidence, apple_binary_verification=apple,
            apple_execution_capture_directory=destination / 'apple-execution')
    if raw != read_regular_file_bytes(receipts['package']) or sha256_bytes(raw) != spec['packageReceiptSha256']:
        raise ValueError('Verification rewrote the original package receipt')
    result = dict(passed=True, packageKey=verified['buildKey'], originalProducer=verified['producer'],
        originalReceiptSha256=sha256_bytes(raw), verifier=context, intake=intake,
        verificationNs=time.monotonic_ns()-tick, elapsedNs=time.monotonic_ns()-started,
        captureBindingSha256=sha256_file(destination / 'apple-execution/input-binding.json'),
        fixtureRuntimeTargets=spec['fixtureRuntimeTargets'], productBuilds=0,
        scope='Full content/source/signature gate and hosted Apple replay only; not platform validation or phase admission')
    write_canonical_json(destination / 'result.json', result)
    print(canonical_json_bytes(result).decode(), flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('usage: phase9_ios_package_check.py DESTINATION LFS_STORAGE JAVA_EXECUTABLE')
    hosted(*(Path(argument).resolve() for argument in sys.argv[1:]))
