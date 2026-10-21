"""Fixed changed-Contract host preflight; no product/signing/admission authority.

Reuse only the source member of the already-approved transfer. Observations retain
the actual hosted controller separately from the immutable private fixture.
Linux ARM64 still needs both independently observed producer roles.
"""
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'ci'))

from ci.tests import phase9_ios_mutation as mutation
from ci.tests.phase9_ios_package_check import receive
from native_wrappers import host_classifier
from product_reuse import _runtime_worker_environment, _provision_runtime_native_toolchain
from products.inventory import git_regular_blob_bytes, sha256_file, write_canonical_json
from products.signing_isolation import require_no_signing_secret
from products.toolchain import load_toolchain_profile_bytes, observe_producer, verify_toolchain_profile

LABEL = 'ci:phase9-runtime-mutation-preflight'
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


def hosted_context(target, role):
    expected_host = selected_role(target, role)
    require_no_signing_secret(os.environ)
    source = mutation.git('rev-parse', 'HEAD')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    pr = event.get('pull_request', {})
    head = pr.get('head', {})
    repository = 'codex-agent-labs/codex-agent'
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('GITHUB_EVENT_NAME') != 'pull_request'
            or os.environ.get('GITHUB_REPOSITORY') != repository or pr.get('number') != 31
            or head.get('repo', {}).get('full_name') != repository or head.get('repo', {}).get('fork') is not False
            or head.get('sha') != source or event.get('label', {}).get('name') != LABEL
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
                native_archive=Path(tools['codexAgent.nativeArchive']) if tools else None, environment=environment)
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


if __name__ == '__main__':
    if len(sys.argv) != 6 or sys.argv[1] != 'hosted':
        raise SystemExit('usage: phase9_runtime_mutation.py hosted TARGET ROLE DESTINATION LFS_STORAGE')
    hosted(sys.argv[2], sys.argv[3], Path(sys.argv[4]).absolute(), Path(sys.argv[5]).absolute())
