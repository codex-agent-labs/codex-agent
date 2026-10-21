"""Fixed Phase-9 mutation diagnostic; never ordinary product/release admission.

The original Contract receipts stay local-producer evidence. A hosted caller
records its real workflow/run separately from this private fixture's Git source.
"""
from concurrent.futures import ThreadPoolExecutor
from argparse import Namespace
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ci'))

from products.contract_projection import verify_contract_component_projection
from products.inventory import (git_product_versions,
    load_canonical_json_bytes, read_regular_file_bytes, require_relative_path,
    require_regular_directory, sha256_bytes, sha256_file, write_canonical_json)
from products.plan import (NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase)
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.registry import PhaseInstanceId, required_contract_components
from products.selection import phase_git_inventory

MANIFEST_SHA256 = 'sha256:1428966a543eb3c73533e3c6ea7e36e096a42ef6133f468c5280b1baa2f7d6ff'
BUILD_KEY = 'sha256:a23e3cb0fcae15b30e488ccf5eb4a7fca8f86e6cc60bdd1a8db5db2c03efaa9d'
INSTANCE = PhaseInstanceId('sdk', 'sdk-ios', 'binary', 'ios')
STEM = 'codex-agent-contract-0.8.0'
LFS_URL = 'https://github.com/codex-agent-labs/codex-agent.git/info/lfs'
NATIVE_PRODUCERS = {
    'tests': dict(commit='2bc9a1a03d7ec503e60f365fabc76626f75f9b17', tree='3c54c793cb53b2549e41d32464e7e096132c2a39',
        runId=38823321421, runAttempt=1, event='pull_request', pullRequest=31,
        repository='codex-agent-labs/codex-agent', workflowPath='.github/workflows/ci.yml'),
    'rust': dict(commit='0a5c3e6054671b5dd61658a1c735c0b2d9fadd3a', tree='784fb6d005e2c13699da5e64a5a50c5d64310706',
        runId=38807951170, runAttempt=1, event='pull_request', pullRequest=31,
        repository='codex-agent-labs/codex-agent', workflowPath='.github/workflows/ci.yml'),
}
NATIVE_PINS = {
    'ios-native-tests': ('tests', 12015585535,
        'sha256:152b38e9813bd95281d945ca18e844d20f6dee0eed1d8c56c9311bfa782f906b',
        'e07a185513acf0b73c0ab3114f7694999bab1845'),
    'ios-rust-device': ('rust', 12011219468,
        'sha256:80047c768d518b71ad8fcd711974012031aa04b31048fb850d859718d2d321a8',
        'cdcad0d7bb1be2633ba24ba65ca5e694f0e9222e'),
    'ios-rust-simulator': ('rust', 12012276513,
        'sha256:6792faf970fd65420d50877b80e0879a64fbdd2a569af750c85eb7f3b4e3375a',
        'cdcad0d7bb1be2633ba24ba65ca5e694f0e9222e'),
}
# Original observations, not a claim about today's runner. The full original
# upload/receipt/job gate below must match these independently selected values.
NATIVE_TOOLCHAIN = dict(cargo='cargo 1.95.0 (f2d3ce0bd 2026-03-21)', gradle='9.7.1',
    javaRuntime='17.0.20.1+1', javaVendor='Eclipse Adoptium', kotlinPlugin='2.3.10', node='unavailable',
    rustc='release=1.95.0;commit=59807616e1fa2540724bfbac14d7976d7e4a3860;host=aarch64-apple-darwin',
    swift='Apple Swift version 6.3.3 (swiftlang-6.3.3.1.3 clang-2100.1.1.101) Target: arm64-apple-macosx26.0',
    xcode='Xcode 26.6;Build version 17F113')


def native_expectations(lane):
    family = NATIVE_PINS[lane][0]
    runner = dict(os='macOS', arch='ARM64', image='macos26',
        imageVersion='20261013.0424.1' if family == 'tests' else '20260907.0351.1')
    return dict(runner=[f'{key}={value}' for key, value in runner.items()],
        toolchain=[f'{key}={value}' for key, value in NATIVE_TOOLCHAIN.items()])


@contextmanager
def fixture_environment(environment):
    previous = {name: os.environ.get(name) for name in environment}
    try:
        os.environ.update(environment)
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def manifest():
    raw = read_regular_file_bytes(Path(__file__).with_name('fixtures') /
        'phase9-ios-mutation-transfer.json', reject_symlink_parents=True)
    if sha256_bytes(raw) != MANIFEST_SHA256:
        raise ValueError('Mutation manifest differs from the explicitly approved export')
    return load_canonical_json_bytes(raw)


def lfs_object(record, storage, environment, client):
    """Use standard LFS once per missing digest; cached bytes remain untrusted."""
    oid = record['sha256'].removeprefix('sha256:')
    path = storage / 'objects' / oid[:2] / oid[2:4] / oid
    downloaded = not (path.exists() or path.is_symlink())
    if downloaded:
        pointer = f'version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize {record["bytes"]}\n'.encode()
        subprocess.run([*client, 'smudge', record['relativePath']], input=pointer,
            stdout=subprocess.DEVNULL, check=True, env=environment, cwd=ROOT)
    if (not path.is_file() or path.is_symlink() or path.resolve(strict=True) != path
            or path.stat().st_size != record['bytes'] or sha256_file(path) != record['sha256']):
        raise ValueError('Mutation LFS object differs from its pinned size/digest/path')
    return path, record['bytes'] if downloaded else 0


def receive(destination, storage, *, client=('git', 'lfs')):
    """One immutable fixture intake, no extra body copy or duplicated metadata fetch."""
    specification = manifest()
    require_regular_directory(storage, 'Private mutation LFS cache')
    if storage.resolve(strict=True) != storage:
        raise ValueError('Mutation LFS cache must be normalized and non-symbolic')
    destination.mkdir()
    require_regular_directory(destination, 'Private mutation input directory')
    environment = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_CONFIG_COUNT='6',
        GIT_CONFIG_KEY_0='lfs.storage', GIT_CONFIG_VALUE_0=str(storage),
        GIT_CONFIG_KEY_1='lfs.url', GIT_CONFIG_VALUE_1=LFS_URL,
        GIT_CONFIG_KEY_2='credential.helper', GIT_CONFIG_VALUE_2='',
        GIT_CONFIG_KEY_3='credential.helper', GIT_CONFIG_VALUE_3='!gh auth git-credential',
        GIT_CONFIG_KEY_4='lfs.fetchinclude', GIT_CONFIG_VALUE_4='',
        GIT_CONFIG_KEY_5='lfs.fetchexclude', GIT_CONFIG_VALUE_5='')
    environment.pop('GIT_LFS_SKIP_SMUDGE', None)
    unique = {row['sha256']: row for row in specification['files']}
    started = time.monotonic_ns()
    with ThreadPoolExecutor(max_workers=4) as pool:
        objects = dict(zip(unique, pool.map(
            lambda row: lfs_object(row, storage, environment, client), unique.values())))
    for row in specification['files']:
        relative = require_relative_path(row['relativePath'], 'Mutation input path')
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        os.link(objects[row['sha256']][0], output)
    return dict(elapsedNs=time.monotonic_ns()-started, uniqueObjects=len(objects),
        uniqueBytes=sum(row['bytes'] for row in unique.values()),
        downloadedBytes=sum(value[1] for value in objects.values()), payloadCopies=0)


def git(*arguments, cwd=ROOT, environment=None):
    return subprocess.check_output(['git', '--no-replace-objects', *arguments], cwd=cwd,
        env=environment, stderr=subprocess.PIPE).decode().strip()


def source_fixture(destination, inputs):
    specification = manifest()
    fixture, gitdir = destination / 'source', destination / 'git'
    fixture.mkdir()
    git('init', '--bare', str(gitdir))
    git('--git-dir', str(gitdir), 'config', 'core.bare', 'false')
    git('--git-dir', str(gitdir), 'config', 'core.worktree', str(fixture))
    environment = dict(os.environ, GIT_DIR=str(gitdir), GIT_WORK_TREE=str(fixture),
        GIT_ALTERNATE_OBJECT_DIRECTORIES=str(Path(git('rev-parse', '--git-path', 'objects')).resolve()))
    bundle = inputs / 'source/mutation-source.bundle'
    git('bundle', 'verify', str(bundle), environment=environment)
    if git('bundle', 'list-heads', str(bundle), environment=environment) != specification['sourceCommit'] + ' HEAD':
        raise ValueError('Mutation source bundle has unexpected heads')
    git('bundle', 'unbundle', str(bundle), environment=environment)
    commit = specification['sourceCommit']
    if git('rev-parse', commit + '^{tree}', environment=environment) != specification['sourceTree']:
        raise ValueError('Mutation source tree differs')
    git('read-tree', commit, environment=environment)
    git('update-ref', '--no-deref', 'HEAD', commit, environment=environment)
    git('checkout-index', '--all', '--prefix=' + str(fixture) + '/', environment=environment)
    if git('diff', 'HEAD', '--', cwd=fixture, environment=environment) or git('for-each-ref', environment=environment):
        raise ValueError('Mutation fixture is not the exact detached source')
    return fixture, {name: environment[name] for name in
        ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_ALTERNATE_OBJECT_DIRECTORIES')}


def prepare(destination, storage, *, client=('git', 'lfs')):
    """Authenticate exact transported originals and reproduce only the missing key."""
    started = time.monotonic_ns()
    destination.mkdir()
    require_regular_directory(destination, 'Mutation diagnostic directory')
    inputs = destination / 'inputs'
    intake = receive(inputs, storage, client=client)
    specification = manifest()
    contract = inputs / 'contract'
    receipt_path = contract / 'metadata-receipt.json'
    receipt = validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(receipt_path)))
    if receipt['producer'] != specification['originalContractProducer']:
        raise ValueError('Original local Contract producer changed')
    stage = destination / 'contract-stage'
    (stage / 'outputs').mkdir(parents=True)
    os.link(contract / (STEM + '.zip'), stage / 'outputs' / (STEM + '.zip'))
    # Reconstitute only the canonical staging descriptor, never the product ZIP.
    write_canonical_json(stage / 'output-manifest.json', {
        'schemaVersion': 1, **{key: receipt[key] for key in
            ('product', 'component', 'phase', 'target', 'productVersion', 'outputs')}})
    if verify_output_manifest_identity(stage, 'contract', 'contract', 'metadata', 'common', '0.8.0')['outputs'] != receipt['outputs']:
        raise ValueError('Contract staging differs from its original receipt')
    tick = time.monotonic_ns()
    projection = verify_contract_component_projection(stage, receipt_path,
        contract / (STEM + '.attestation.json'), contract / (STEM + '.attestation.sig'),
        contract / 'development.pub', expected_trust_domain='development',
        expected_contract_version='0.8.0', required_components=required_contract_components(INSTANCE))
    verification_ns = time.monotonic_ns() - tick
    fixture, environment = source_fixture(destination, inputs)
    with fixture_environment(environment):
        plan = plan_phase(INSTANCE,
            inventory=phase_git_inventory(fixture, specification['sourceCommit'], INSTANCE),
            versions=git_product_versions(fixture, specification['sourceCommit']), upstream_receipts=[receipt],
            toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, contract_projection=projection)
        if plan['buildKey'] != BUILD_KEY:
            raise ValueError('Mutation iOS binary no longer matches the preserved missing election')
    write_canonical_json(destination / 'plan.json', plan)
    result = dict(schemaVersion=1, sourceCommit=specification['sourceCommit'], sourceTree=specification['sourceTree'],
        environment=environment, originalContractProducer=receipt['producer'], buildKey=plan['buildKey'],
        manifestSha256=MANIFEST_SHA256, intake=intake, contractVerificationNs=verification_ns,
        elapsedNs=time.monotonic_ns()-started, productExecutions=0,
        scope='Authenticated development fixture intake and key reproduction; no new product phase admission')
    write_canonical_json(destination / 'prepared.json', result)
    print(json.dumps({key: value for key, value in result.items() if key != 'environment'}), flush=True)
    return result


def qualification_module():
    spec = importlib.util.spec_from_file_location('phase9_native_qualification',
        ROOT / '.github/actions/run-ci-lane/sdk_native_qualification.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def native_inputs(destination, *, token, lanes=tuple(NATIVE_PINS)):
    """Authenticate direct original lanes once; do not forward their bulk captures."""
    import product_reuse as reuse
    from sdk_apple_native import JOBS, NATIVE_FILES
    from sdk_apple_source import _PLAN_JOB, _original_upload, _private_original_repository
    from products.restore import bounded_verify, verification_session
    from products.inventory import regular_file_inventory

    if not token or not lanes or len(set(lanes)) != len(lanes) or not set(lanes) <= set(NATIVE_PINS):
        raise ValueError('Mutation native input selection is invalid')
    destination.mkdir()
    evidence = destination / 'evidence'
    evidence.mkdir()
    helper = qualification_module()
    started = time.monotonic_ns()
    # Reuse the original authorized PR plan, never invent a PR plan for the local fixture.
    consumer = NATIVE_PRODUCERS['tests']
    workflow = NATIVE_PINS['ios-native-tests'][3]
    with verification_session(), reuse._ci_observation_batch():
        observation, = reuse._observe_ci_producer_jobs({'plan': consumer},
            jobs_by_phase={'plan': _PLAN_JOB}, token=token, trusted_workflow_sha=workflow)
        artifacts = reuse.paginated_items(
            f"https://api.github.com/repos/{consumer['repository']}/actions/runs/{consumer['runId']}/artifacts",
            'artifacts', token)
        plan_artifact, plan_raw = _original_upload(name=f"codex-agent-ci-plan-{consumer['tree']}",
            producer=consumer, observation=observation, job=_PLAN_JOB, artifacts=artifacts, token=token)
        archive = destination / 'original-plan-upload.zip'
        with archive.open('xb') as output:
            output.write(plan_raw)
        helper._extract(archive, destination / 'original-plan')
        # Fetch each authenticated Git revision once, before parallel readers use it.
        helper._acquire_original_revision(ROOT, consumer)
        for family in dict.fromkeys(NATIVE_PINS[lane][0] for lane in lanes):
            original = NATIVE_PRODUCERS[family]
            members = [lane for lane in lanes if NATIVE_PINS[lane][0] == family]
            observed, = reuse._observe_ci_producer_jobs({lane: original for lane in members},
                jobs_by_phase={lane: JOBS[lane] for lane in members}, token=token,
                trusted_workflow_sha=NATIVE_PINS[members[0]][3])
            write_canonical_json(destination / (family + '-observation.json'), observed)
            helper._acquire_original_revision(ROOT, original)
        repository = _private_original_repository(ROOT, destination / 'repository',
            consumer['commit'], consumer['commit'])
        # Make both already authenticated original revisions available without another remote fetch.
        for family in dict.fromkeys(NATIVE_PINS[lane][0] for lane in lanes):
            git('fetch', '--quiet', '--no-tags', '--depth=1', str(ROOT), NATIVE_PRODUCERS[family]['commit'], cwd=repository)
        plan_path = destination / 'original-plan/impact-plan.json'

        def qualify(lane):
            family, identifier, digest, expected_workflow = NATIVE_PINS[lane]
            output = destination / lane
            result = helper.qualify_candidate(Namespace(plan=plan_path, lane=lane, token=token,
                **native_expectations(lane)), {'id': identifier, 'digest': digest},
                trusted_workflow_sha=workflow, repository_root=repository, output=output)
            if (result['originalProducer'] != NATIVE_PRODUCERS[family]
                    or result['originalWorkflowSha'] != expected_workflow
                    or result['originalArtifact']['id'] != identifier
                    or result['originalArtifact']['digest'] != digest):
                raise ValueError('Native qualification differs from the independently pinned original')
            for relative, name in NATIVE_FILES[lane].items():
                os.link(output / 'lane' / relative, evidence / name)
            return lane, result

        results = dict(bounded_verify(qualify, lanes))
        inventory = regular_file_inventory(evidence)
        expected_paths = {name for lane in lanes for name in NATIVE_FILES[lane].values()}
        if {row['relativePath'] for row in inventory} != expected_paths:
            raise ValueError('Native fixture intake has incomplete or extra evidence')
        result = dict(schemaVersion=1, lanes=results, evidenceInventory=inventory,
            elapsedNs=time.monotonic_ns()-started, originalPlanArtifact=plan_artifact,
            productExecutions=0, semanticAdmissionRequired=True)
        write_canonical_json(destination / 'result.json', result)
    return result


def hosted(destination, storage):
    """Execute only the missing fixture binary, with actual hosted context kept separate."""
    from products.inventory import regular_file_inventory
    from sdk_ios_binary import execute
    specification = manifest()
    source = git('rev-parse', 'HEAD')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_EVENT_NAME') != 'pull_request'
            or os.environ.get('GITHUB_REPOSITORY') != 'codex-agent-labs/codex-agent'
            or event['pull_request']['number'] != 31
            or event['pull_request']['head']['repo']['full_name'] != os.environ['GITHUB_REPOSITORY']
            or event['pull_request']['head']['repo']['fork'] is not False
            or event['pull_request']['head']['sha'] != source
            or event['label']['name'] != 'ci:phase9-ios-mutation' or git('diff', 'HEAD', '--')):
        raise ValueError('Mutation execution requires its exact same-repository labeled PR source')
    # Reject a wrong runner before transferring the multi-GB native predecessors.
    from native_wrappers import host_classifier
    from products.inventory import git_regular_blob_bytes
    from products.sdk_apple_package_source import _PIN_FILE, _toolchain_expectations
    from products.sdk_apple_toolchain_evidence import _versions
    if host_classifier() != 'macos-arm64':
        raise ValueError('Mutation requires a genuine macOS ARM64 runner')
    expected_tools = _toolchain_expectations(git_regular_blob_bytes(
        ROOT, specification['sourcePrerequisite'], _PIN_FILE, max_bytes=1024*1024))
    xcode = subprocess.check_output(['/usr/bin/xcodebuild', '-version'], text=True)
    swift = subprocess.check_output(['/usr/bin/xcrun', 'swift', '--version'], text=True)
    _versions(xcode, swift, expected_tools)
    rust = subprocess.check_output(['rustc', '-vV'], text=True)
    provenance = json.loads(git_regular_blob_bytes(ROOT, specification['sourcePrerequisite'],
        'codex-agent-runtime-ios/native/provenance.json', max_bytes=1024*1024))
    if ([line for line in rust.splitlines() if line.startswith('release:')] != ['release: ' + provenance['rustToolchain']]
            or [line for line in rust.splitlines() if line.startswith('host:')] != ['host: aarch64-apple-darwin']):
        raise ValueError('Mutation Rust compiler differs from the original native policy')
    started = time.monotonic_ns()
    prepared = prepare(destination, storage)
    write_canonical_json(destination / 'observed-toolchain.json', dict(expected=expected_tools,
        xcode=xcode, swift=swift, rust=rust, runnerOS=os.environ['RUNNER_OS'], runnerArch=os.environ['RUNNER_ARCH']))
    native = native_inputs(destination / 'native', token=os.environ['GITHUB_TOKEN'])
    fixture = destination / 'source'
    evidence = destination / 'native/evidence'
    helper = qualification_module()
    with fixture_environment(prepared['environment']):
        for lane, qualified in native['lanes'].items():
            helper.compatible_source_inventories(fixture, qualified['originalProducer']['commit'],
                specification['sourceCommit'], lane)
        contract = destination / 'inputs/contract'
        os.link(contract / 'development.pub', contract / 'public-key.pub')
        # The source actually compiled is private ae8b, NOT the workflow's source commit.
        # No receipt is issued: normal original-CI admission must not accept this diagnostic.
        producer = dict(repository=os.environ['GITHUB_REPOSITORY'], workflowPath='.github/workflows/portable-reuse-proof.yml',
            event='pull_request', pullRequest=31, runId=int(os.environ['GITHUB_RUN_ID']),
            runAttempt=int(os.environ['GITHUB_RUN_ATTEMPT']), commit=specification['sourceCommit'], tree=specification['sourceTree'])
        context = dict(workflowSourceCommit=source, workflowSourceTree=git('rev-parse', source + '^{tree}'),
            workflowEventCommit=os.environ['GITHUB_SHA'], fixtureExecution=producer,
            originalContractProducer=specification['originalContractProducer'],
            scope='Actual hosted development fixture execution; no ordinary product or release admission')
        write_canonical_json(destination / 'hosted-context.json', context)
        plan = load_canonical_json_bytes(read_regular_file_bytes(destination / 'plan.json'))
        receipt_path = contract / 'metadata-receipt.json'
        receipt = load_canonical_json_bytes(read_regular_file_bytes(receipt_path))
        result = execute(plan, producer=producer, sdk_version='0.8.0',
            contract_metadata=dict(stage=destination / 'contract-stage', receiptPath=receipt_path, receipt=receipt),
            verified_contract_handoff=contract, native_evidence=evidence, repository_root=fixture,
            destination=fixture / 'build/mutation-worker', environ=dict(os.environ))
        if regular_file_inventory(evidence) != native['evidenceInventory']:
            raise ValueError('Original native evidence changed during fixture execution')
        log = (result['diagnostics'] / 'gradle.log').read_text()
        if any(':buildCodexIos' + target + 'Rust' in log for target in ('Arm64', 'SimulatorArm64')):
            raise ValueError('Mutation diagnostic rebuilt a completed native Rust predecessor')
        write_canonical_json(destination / 'result.json', dict(schemaVersion=1,
            buildKey=plan['buildKey'], outputInventory=result['outputInventory'], context=context,
            elapsedNs=time.monotonic_ns()-started, intake=prepared['intake'],
            nativeCaptureNs=native['elapsedNs'], originalReceiptsRewritten=0, baselineAdmission=False))


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] not in {'prepare', 'hosted'}:
        raise SystemExit('usage: phase9_ios_mutation.py {prepare|hosted} DESTINATION LFS_STORAGE')
    (prepare if sys.argv[1] == 'prepare' else hosted)(Path(sys.argv[2]).absolute(), Path(sys.argv[3]).absolute())
