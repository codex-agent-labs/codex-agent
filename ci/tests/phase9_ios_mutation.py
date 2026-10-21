"""Fixed Phase-9 mutation diagnostic; never ordinary product/release admission.

The original Contract receipts stay local-producer evidence. A hosted caller
records its real workflow/run separately from this private fixture's Git source.
"""
from concurrent.futures import ThreadPoolExecutor
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
    previous = {name: os.environ.get(name) for name in environment}
    try:
        os.environ.update(environment)
        plan = plan_phase(INSTANCE,
            inventory=phase_git_inventory(fixture, specification['sourceCommit'], INSTANCE),
            versions=git_product_versions(fixture, specification['sourceCommit']), upstream_receipts=[receipt],
            toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, contract_projection=projection)
        if plan['buildKey'] != BUILD_KEY:
            raise ValueError('Mutation iOS binary no longer matches the preserved missing election')
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    write_canonical_json(destination / 'plan.json', plan)
    result = dict(schemaVersion=1, sourceCommit=specification['sourceCommit'], sourceTree=specification['sourceTree'],
        environment=environment, originalContractProducer=receipt['producer'], buildKey=plan['buildKey'],
        manifestSha256=MANIFEST_SHA256, intake=intake, contractVerificationNs=verification_ns,
        elapsedNs=time.monotonic_ns()-started, productExecutions=0,
        scope='Authenticated development fixture intake and key reproduction; no new product phase admission')
    write_canonical_json(destination / 'prepared.json', result)
    print(json.dumps({key: value for key, value in result.items() if key != 'environment'}), flush=True)
    return result


if __name__ == '__main__':
    if len(sys.argv) != 4 or sys.argv[1] != 'prepare':
        raise SystemExit('usage: phase9_ios_mutation.py prepare DESTINATION LFS_STORAGE')
    prepare(Path(sys.argv[2]).absolute(), Path(sys.argv[3]).absolute())
