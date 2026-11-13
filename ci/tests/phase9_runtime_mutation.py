"""Fixed changed-Contract host preflight; no product/signing/admission authority.

Reuse only the source member of the already-approved transfer. Observations retain
the actual hosted controller separately from the immutable private fixture.
Linux ARM64 still needs both independently observed producer roles.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'ci'))

from ci.tests import phase9_ios_mutation as mutation
from ci.tests.phase9_ios_package_check import receive
from native_wrappers import host_classifier
from product_reuse import _runtime_worker_environment, _provision_runtime_native_toolchain
from products.inventory import (git_regular_blob_bytes, git_product_versions,
    sha256_file, write_canonical_json)
from products.signing_isolation import require_no_signing_secret
from products.toolchain import load_toolchain_profile_bytes, observe_producer, verify_toolchain_profile

LABEL = 'ci:phase9-runtime-mutation-preflight'
WINDOWS_LABEL = 'ci:phase9-runtime-windows-preflight'
WINDOWS_BINARY_LABEL = 'ci:phase9-runtime-windows-binary'
WINDOWS_BINARY_KEY = 'sha256:459daab114ea2b62b6994e162f033c959bf95bfdd649bcda6c46b7dc96f2fcc5'
WINDOWS_SOURCE = '8ebc00e3ed977e6e8aa350003f37dfd40c8e9152'
WINDOWS_TREE = 'e2e361dff29d019271c2b489b27b3e583605d104'
WINDOWS_PROFILE = 'sha256:75de15959cd25daeb49a85428d95178bb3bd5dfea9e5d57ea945e87a44798fb7'
WINDOWS_PROFILE_PATH = 'gradle/release/toolchains/runtime/windows-x64.json'
WINDOWS_BUNDLE = dict(relativePath='source/windows-mutation-source.bundle', bytes=2469,
    sha256='sha256:3f459aa191b8b1ac47ef25be7c6a5eb6ac4f3c176222360860cd8fd97a4ebaae')
# Reviewed missing-key decision; this is not a serialized admission capability.
RETAINED_CHECKPOINT = 'sha256:3944685c3a9dcfa21e48adf67b72b1946928b119ad83390c3334842baa65cc5a'
KEYS = {
    'linux-arm64': 'sha256:7ed7ab6469633c492228bcca5d4cbd49b7965f573acc1c8ecd530400e88bf03b',
    'linux-x64': 'sha256:209247419e5bb5d4cd4fe2fbe76126a85f617159079ba94a2e6c2dd01d6d74fe',
    'macos-x64': 'sha256:5769104c7e83325beeb6bfc5113fead406f57cc4bb5c499b4f34ed4a6d8b6c32',
    'windows-x64': 'sha256:b2c00bec1e4a562c922bbb41e2849101999807445e31bda98ba2fef9ca75bf99',
}


def selected_role(target, role):
    if target not in KEYS or role not in (
            ('cross-builder', 'supervisor-builder') if target == 'linux-arm64' else ('builder',)):
        raise ValueError('Preflight requires one missing target and its exact producer role')
    return 'linux-x64' if role == 'cross-builder' else target


def hosted_context(target, role, *, windows_binary=False):
    expected_host = selected_role(target, role)
    if windows_binary and (target, role) != ('windows-x64', 'builder'):
        raise ValueError('Binary diagnostic requires the fixed Windows builder')
    labels = ({WINDOWS_BINARY_LABEL} if windows_binary else
              {LABEL, WINDOWS_LABEL} if target == 'windows-x64' else {LABEL})
    require_no_signing_secret(os.environ)
    source = mutation.git('rev-parse', 'HEAD')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    pr = event.get('pull_request', {})
    head = pr.get('head', {})
    repository = 'codex-agent-labs/codex-agent'
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_EVENT_NAME') != 'pull_request'
            or os.environ.get('GITHUB_REPOSITORY') != repository or pr.get('number') != 31
            or head.get('repo', {}).get('full_name') != repository or head.get('repo', {}).get('fork') is not False
            or head.get('sha') != source or event.get('label', {}).get('name') not in labels
            or mutation.git('diff', 'HEAD', '--')):
        raise ValueError('Preflight requires its exact same-repository labeled PR source')
    if host_classifier() != expected_host:
        raise ValueError('Preflight requires the actual selected producer host')
    return dict(sourceCommit=source, sourceTree=mutation.git('rev-parse', 'HEAD^{tree}'),
        workflowEventCommit=os.environ['GITHUB_SHA'], runId=int(os.environ['GITHUB_RUN_ID']),
        runAttempt=int(os.environ['GITHUB_RUN_ATTEMPT']), target=target, role=role,
        productExecutions=0, releaseAdmission=False)


def prepare(target, destination, storage):
    """Consume source only: tool observation needs no Contract or product bodies."""
    if target not in KEYS:
        raise ValueError('Preflight cannot rebuild an existing target')
    specification = mutation.manifest()
    started = time.monotonic_ns()
    destination.mkdir()
    records = [row for row in specification['files'] if row['relativePath'] == 'source/mutation-source.bundle']
    if len(records) != 1:
        raise ValueError('Preflight requires exactly the reviewed source bundle')
    intake = receive(records, destination / 'inputs', storage)
    write_canonical_json(destination / 'intake.json', intake)
    fixture, environment = mutation.source_fixture(destination, destination / 'inputs')
    with mutation.fixture_environment(environment):
        revision = specification['sourceCommit']
        profile = load_toolchain_profile_bytes(git_regular_blob_bytes(fixture, revision,
            f'gradle/release/toolchains/runtime/{target}.json', max_bytes=1024*1024), target)
    prepared = dict(environment=environment, sourceCommit=revision, sourceTree=specification['sourceTree'],
        originalContractProducer=specification['originalContractProducer'], candidateBuildKey=KEYS[target],
        profileDigest=profile.digest, contractInputBytes=0, productInputBytes=0,
        elapsedNs=time.monotonic_ns()-started, intake=intake, productExecutions=0)
    write_canonical_json(destination / 'prepared.json', prepared)
    return prepared, profile


def hosted(target, role, destination, storage):
    context = hosted_context(target, role)  # Wrong scope/host fails before transfer.
    prepared, profile = prepare(target, destination, storage)
    write_canonical_json(destination / 'hosted-context.json', context)
    fixture = destination / 'source'
    producer = dict(repository='codex-agent-labs/codex-agent', workflowPath='.github/workflows/portable-reuse-proof.yml',
        event='pull_request', pullRequest=31, runId=context['runId'], runAttempt=context['runAttempt'],
        commit=prepared['sourceCommit'], tree=prepared['sourceTree'])
    started = time.monotonic_ns()
    with mutation.fixture_environment(prepared['environment']):
        environment = dict(os.environ, CODEX_AGENT_VERIFIED_DEPENDENCY_FETCH='true')
        diagnostics = fixture / 'build/mutation-preflight'
        environment, _ = _runtime_worker_environment(fixture, producer, diagnostics, environment)
        for name in ('GH_TOKEN', 'GITHUB_TOKEN'):
            # The observer/bootstrap also launch subprocesses through os.environ.
            # Empty values shadow ambient credentials for that scoped lifetime.
            environment[name] = ''
        diagnostics.mkdir(parents=True)
        with mutation.fixture_environment(environment):
            tools = ({} if role == 'supervisor-builder' else _provision_runtime_native_toolchain(
                fixture, prepared['sourceCommit'], target, diagnostics, environment))
            observation = observe_producer(fixture, prepared['sourceCommit'], target, role, target,
                konan_data_dir=Path(environment['KONAN_DATA_DIR']) if tools else None,
                kotlin_plugin_jar=Path(tools['codexAgent.kotlinPluginJar']) if tools else None,
                native_archive=Path(tools['codexAgent.nativeArchive']) if tools else None, environment=os.environ)
        write_canonical_json(destination / 'toolchain-observation.json', observation)
        actual = observation['producer']
        error = None
        try:
            verify_toolchain_profile(profile, prepared['profileDigest'], role,
                actual['runner'], {row['name']: row['identity'] for row in actual['tools']},
                image_provenance=observation['imageProvenance'])
        except ValueError as failure:
            error = str(failure)
        result = dict(context=context, candidateBuildKey=KEYS[target], originalContractProducer=prepared['originalContractProducer'],
            profileMatches=error is None, error=error, elapsedNs=time.monotonic_ns()-started,
            observationSha256=sha256_file(destination / 'toolchain-observation.json'),
            contractInputBytes=0, productInputBytes=0, productExecutions=0,
            scope='Genuine host preflight only; candidate key is not an execution election. No product receipt or admission.')
        write_canonical_json(destination / 'result.json', result)
        print(json.dumps(result), flush=True)
        if error:
            raise ValueError(error)


def prepare_binary(target, destination, storage):
    """One exact Contract/source intake; no other Runtime or SDK bodies."""
    from products.plan import plan_phase
    from products.registry import PhaseInstanceId
    from products.runtime_flags import load_runtime_binary_flags_bytes
    from products.runtime_identity import derive_runtime_identity_from_git
    from products.selection import phase_git_inventory

    if target != 'linux-x64':
        raise ValueError('Binary fixture currently elects only missing Linux x64')
    started = time.monotonic_ns()
    destination.mkdir()
    spec = mutation.manifest()
    intake = receive(spec['files'], destination / 'inputs', storage)
    write_canonical_json(destination / 'intake.json', intake)
    instance = PhaseInstanceId('runtime', target, 'binary', target)
    receipt, projection, verification_ns = mutation.contract_inputs(destination, destination / 'inputs', instance)
    fixture, environment = mutation.source_fixture(destination, destination / 'inputs')
    revision = spec['sourceCommit']
    with mutation.fixture_environment(environment):
        profile = load_toolchain_profile_bytes(git_regular_blob_bytes(fixture, revision,
            f'gradle/release/toolchains/runtime/{target}.json', max_bytes=1024*1024), target)
        flags = load_runtime_binary_flags_bytes(git_regular_blob_bytes(fixture, revision,
            'codex-agent-runtime-desktop/native/c-api/binary-flags.json', max_bytes=1024*1024))
        plan = plan_phase(instance, inventory=phase_git_inventory(fixture, revision, instance),
            versions=git_product_versions(fixture, revision), upstream_receipts=[receipt],
            toolchain_profile_digest=profile.digest, flags_digest=flags[target].digest,
            contract_projection=projection)
        if plan['buildKey'] != KEYS[target]:
            raise ValueError('Native mutation binary differs from the missing reviewed key')
        plan['runtimeBinaryIdentity'] = derive_runtime_identity_from_git(fixture, revision, plan, projection)
    write_canonical_json(destination / 'plan.json', plan)
    prepared = dict(environment=environment, sourceCommit=revision, sourceTree=spec['sourceTree'],
        originalContractProducer=receipt['producer'], buildKey=plan['buildKey'], profileDigest=profile.digest,
        contractVerificationNs=verification_ns, elapsedNs=time.monotonic_ns()-started, intake=intake,
        productExecutions=0, baselineAdmission=False)
    write_canonical_json(destination / 'prepared.json', prepared)
    return prepared, profile, plan


def prepare_windows_source(destination, storage):
    """Bind only the two tiny source bundles before any Contract acquisition."""

    started = time.monotonic_ns()
    destination.mkdir()
    spec = mutation.manifest()
    records = [row for row in spec['files'] if row['relativePath'] == 'source/mutation-source.bundle']
    if len(records) != 1:
        raise ValueError('Windows source requires the one approved baseline bundle')
    intake = receive([*records, WINDOWS_BUNDLE], destination / 'source-inputs', storage)
    fixture, environment = mutation.source_fixture(destination, destination / 'source-inputs')
    with mutation.fixture_environment(environment):
        bundle = destination / 'source-inputs' / WINDOWS_BUNDLE['relativePath']
        if bundle.stat().st_size != WINDOWS_BUNDLE['bytes'] or sha256_file(bundle) != WINDOWS_BUNDLE['sha256']:
            raise ValueError('Windows private source bundle changed after intake')
        mutation.git('bundle', 'verify', str(bundle), cwd=fixture)
        if mutation.git('bundle', 'list-heads', str(bundle), cwd=fixture) != WINDOWS_SOURCE + ' HEAD':
            raise ValueError('Windows private source bundle has unexpected heads')
        mutation.git('bundle', 'unbundle', str(bundle), cwd=fixture)
        if (mutation.git('rev-parse', WINDOWS_SOURCE + '^{tree}', cwd=fixture) != WINDOWS_TREE
                or mutation.git('rev-parse', WINDOWS_SOURCE + '^', cwd=fixture) != spec['sourceCommit']
                or mutation.git('diff', '--name-only', spec['sourceCommit'], WINDOWS_SOURCE, cwd=fixture)
                != WINDOWS_PROFILE_PATH):
            raise ValueError('Windows private source differs beyond the reviewed profile')
        mutation.git('read-tree', WINDOWS_SOURCE, cwd=fixture)
        mutation.git('update-ref', '--no-deref', 'HEAD', WINDOWS_SOURCE, cwd=fixture)
        mutation.git('checkout-index', '--force', WINDOWS_PROFILE_PATH, cwd=fixture)
        if mutation.git('diff', 'HEAD', '--', cwd=fixture) or mutation.git('for-each-ref', cwd=fixture):
            raise ValueError('Windows private source is not the exact detached fixture')
        profile = load_toolchain_profile_bytes(git_regular_blob_bytes(fixture, WINDOWS_SOURCE,
            WINDOWS_PROFILE_PATH, max_bytes=1024*1024), 'windows-x64')
        if profile.digest != WINDOWS_PROFILE:
            raise ValueError('Windows profile differs from the reviewed original observation')
    prepared = dict(environment=environment, sourceCommit=WINDOWS_SOURCE, sourceTree=WINDOWS_TREE,
        profileDigest=profile.digest, originalContractProducer=spec['originalContractProducer'],
        sourceIntake=intake, elapsedNs=time.monotonic_ns()-started, productExecutions=0)
    write_canonical_json(destination / 'source-preparation.json', prepared)
    return prepared, profile


def prepare_windows_binary(destination, storage, prepared, profile):
    """Consume the unchanged Contract only after the actual host profile matches."""
    from products.plan import plan_phase
    from products.registry import PhaseInstanceId
    from products.runtime_flags import load_runtime_binary_flags_bytes
    from products.runtime_identity import derive_runtime_identity_from_git
    from products.selection import phase_git_inventory

    started = time.monotonic_ns()
    spec = mutation.manifest()
    records = [row for row in spec['files'] if row['relativePath'].startswith('contract/')]
    intake = receive(records, destination / 'inputs', storage)
    write_canonical_json(destination / 'intake.json', intake)
    instance = PhaseInstanceId('runtime', 'windows-x64', 'binary', 'windows-x64')
    receipt, projection, verification_ns = mutation.contract_inputs(destination, destination / 'inputs', instance)
    fixture, environment = destination / 'source', prepared['environment']
    with mutation.fixture_environment(environment):
        flags = load_runtime_binary_flags_bytes(git_regular_blob_bytes(fixture, WINDOWS_SOURCE,
            'codex-agent-runtime-desktop/native/c-api/binary-flags.json', max_bytes=1024*1024))
        plan = plan_phase(instance, inventory=phase_git_inventory(fixture, WINDOWS_SOURCE, instance),
            versions=git_product_versions(fixture, WINDOWS_SOURCE), upstream_receipts=[receipt],
            toolchain_profile_digest=profile.digest, flags_digest=flags['windows-x64'].digest,
            contract_projection=projection)
        if plan['buildKey'] != WINDOWS_BINARY_KEY:
            raise ValueError('Windows mutation binary differs from its reviewed missing key')
        plan['runtimeBinaryIdentity'] = derive_runtime_identity_from_git(fixture, WINDOWS_SOURCE, plan, projection)
    write_canonical_json(destination / 'plan.json', plan)
    prepared = dict(environment=environment, sourceCommit=WINDOWS_SOURCE, sourceTree=WINDOWS_TREE,
        originalContractProducer=receipt['producer'], buildKey=plan['buildKey'], profileDigest=profile.digest,
        contractVerificationNs=verification_ns, elapsedNs=time.monotonic_ns()-started, intake=intake,
        retainedCheckpointSha256=RETAINED_CHECKPOINT, retainedKeysSearched=174,
        productExecutions=0, baselineAdmission=False)
    write_canonical_json(destination / 'prepared.json', prepared)
    return prepared, profile, plan


def hosted_windows_binary(destination, storage):
    """One real Windows execution, never ordinary hosted/product admission."""
    from product_reuse import _runtime_worker_checkout, _runtime_worker_command
    from products.inventory import read_regular_file_bytes, regular_file_inventory
    from products.receipt import write_phase_receipt
    from products.toolchain_capture_bootstrap import _pinned_file
    from runtime_native_phase import archive_spec, properties

    context = hosted_context('windows-x64', 'builder', windows_binary=True)
    started = time.monotonic_ns()
    prepared, profile = prepare_windows_source(destination, storage)
    # Real hosted controller and privately compiled source have distinct identities.
    producer = dict(repository='codex-agent-labs/codex-agent',
        workflowPath='.github/workflows/portable-reuse-proof.yml', event='pull_request', pullRequest=31,
        runId=context['runId'], runAttempt=context['runAttempt'], commit=WINDOWS_SOURCE, tree=WINDOWS_TREE)
    write_canonical_json(destination / 'hosted-context.json', dict(controller=context,
        fixtureExecution=producer, originalContractProducer=prepared['originalContractProducer'],
        scope='Hosted development fixture only; private source is not the official run commit.'))
    source = destination / 'source'
    with mutation.fixture_environment(prepared['environment']):
        environment, wrapper = _runtime_worker_environment(source, producer, destination / 'diagnostics',
            dict(os.environ, CODEX_AGENT_VERIFIED_DEPENDENCY_FETCH='true'))
        environment.update(GH_TOKEN='', GITHUB_TOKEN='')
        if environment.get('LINK') not in (None, '', '/Brepro'):
            raise ValueError('Windows worker rejects injected MSVC linker options')
        environment['LINK'] = '/Brepro'
        with mutation.fixture_environment(environment):
            tools = _provision_runtime_native_toolchain(source, WINDOWS_SOURCE, 'windows-x64', destination, environment)
            observation = observe_producer(source, WINDOWS_SOURCE, 'windows-x64', 'builder', 'windows-x64',
                konan_data_dir=Path(environment['KONAN_DATA_DIR']),
                kotlin_plugin_jar=Path(tools['codexAgent.kotlinPluginJar']),
                native_archive=Path(tools['codexAgent.nativeArchive']), environment=os.environ)
        write_canonical_json(destination / 'toolchain-observation.json', observation)
        actual = observation['producer']
        verify_toolchain_profile(profile, WINDOWS_PROFILE, 'builder', actual['runner'],
            {row['name']: row['identity'] for row in actual['tools']}, image_provenance=observation['imageProvenance'])
        prepared, profile, plan = prepare_windows_binary(destination, storage, prepared, profile)
        spec = archive_spec(plan, repository_root=source, revision=WINDOWS_SOURCE)
        archives = destination / 'inputs/app-server'
        archives.mkdir()
        archive = archives / spec['asset']
        _pinned_file(spec['url'], archive, spec['sha256'], None)
        if sha256_file(archive) != spec['sha256'] or archive.stat().st_size > 512*1024*1024:
            raise ValueError('Windows pinned app-server archive changed')
        contract = destination / 'inputs/contract'
        props = {f'codexAgent.{key}': value for key, value in dict(product='runtime', component='windows-x64',
            phase='binary', target='windows-x64', contractVersion='0.8.0', runtimeVersion='0.8.0',
            contractPayload=str(contract / (mutation.STEM + '.zip')),
            contractMetadataReceipt=str(contract / 'metadata-receipt.json'),
            contractAttestation=str(contract / (mutation.STEM + '.attestation.json')),
            contractAttestationSignature=str(contract / (mutation.STEM + '.attestation.sig')),
            contractPublicKey=str(contract / 'development.pub'), candidateCommit=WINDOWS_SOURCE,
            candidateTree=WINDOWS_TREE, desktopArchiveDirectory=str(archives)).items()}
        props.update(properties(plan, plan_path=destination / 'plan.json', revision=WINDOWS_SOURCE,
            predecessor=None, output=None, report=None))
        props.update(tools)
        init_path = 'codex-agent-runtime-desktop/src/mingwMain/gradle/deterministic-native-link.init.gradle'
        if read_regular_file_bytes(source / init_path, reject_symlink_parents=True) != git_regular_blob_bytes(
                source, WINDOWS_SOURCE, init_path, max_bytes=64*1024):
            raise ValueError('Windows compiler policy differs from exact source')
        stage = source / 'codex-agent-runtime-desktop/build/product-stage/runtime/windows-x64/binary'
        if stage.exists() or stage.is_symlink():
            raise ValueError('Windows mutation refuses a pre-existing product stage')
        inventory = regular_file_inventory(destination / 'inputs')
        source_inventory = regular_file_inventory(destination / 'source-inputs')
        command = _runtime_worker_command(wrapper, props, environment, init_script=source / init_path)
        command.extend(['--max-workers=2', '--console=plain', '--info'])
        write_canonical_json(destination / 'binary-election.json', dict(buildKey=WINDOWS_BINARY_KEY,
            producer=producer, command=command, hostedContext=context,
            retainedCheckpointSha256=RETAINED_CHECKPOINT, retainedKeysSearched=174,
            profileObservationSha256=sha256_file(destination / 'toolchain-observation.json'),
            baselineAdmission=False, releaseAdmission=False))
        tick = time.monotonic_ns()
        with (destination / 'binary.log').open('xb') as log:
            # Only this private development fixture uses development Contract trust.
            # Host observation/controller provenance and production workers stay unchanged.
            completed = subprocess.run(command, cwd=source, env=dict(environment, GITHUB_ACTIONS='false'),
                stdout=log, stderr=subprocess.STDOUT, check=False)
        write_canonical_json(destination / 'binary-execution.json', dict(returnCode=completed.returncode,
            elapsedNs=time.monotonic_ns()-tick, command=command, producer=producer,
            buildKey=WINDOWS_BINARY_KEY, logSha256=sha256_file(destination / 'binary.log')))
        if completed.returncode:
            raise ValueError('Windows mutation binary failed; original diagnostics retained')
        _runtime_worker_checkout(source, producer)
        if ((destination / 'diagnostics/python-bytecode').exists()
                or (destination / 'diagnostics/python-bytecode').is_symlink()
                or inventory != regular_file_inventory(destination / 'inputs')
                or source_inventory != regular_file_inventory(destination / 'source-inputs')):
            raise ValueError('Windows mutation inputs or private bytecode changed during execution')
        receipts = destination / 'binary-receipt'
        receipts.mkdir()
        receipt = write_phase_receipt(stage, receipts, 'runtime', 'windows-x64', 'binary', 'windows-x64',
            '0.8.0', WINDOWS_BINARY_KEY, plan['inputs'], producer, 'development')
        write_canonical_json(destination / 'result.json', dict(buildKey=WINDOWS_BINARY_KEY,
            producer=producer, hostedContext=context, receiptSha256=sha256_file(receipts / 'phase-receipt.json'),
            outputCount=len(receipt['outputs']), outputBytes=sum(row['bytes'] for row in receipt['outputs']),
            elapsedNs=time.monotonic_ns()-started, productExecutions=1, baselineAdmission=False,
            releaseAdmission=False, scope='Actual hosted development fixture; local full content acceptance remains separate.'))


if __name__ == '__main__':
    if len(sys.argv) == 4 and sys.argv[1] == 'hosted-windows-binary':
        hosted_windows_binary(Path(sys.argv[2]).absolute(), Path(sys.argv[3]).absolute())
    elif len(sys.argv) == 6 and sys.argv[1] == 'hosted':
        hosted(sys.argv[2], sys.argv[3], Path(sys.argv[4]).absolute(), Path(sys.argv[5]).absolute())
    else:
        raise SystemExit('usage: phase9_runtime_mutation.py hosted TARGET ROLE DESTINATION LFS_STORAGE')
