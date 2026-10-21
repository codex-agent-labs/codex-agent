"""Read-only matching-Xcode provisioning probe; no product or toolchain export."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ci.products.inventory import git_regular_blob_bytes, write_canonical_json
from ci.products.sdk_apple_package_source import _PIN_FILE, _toolchain_expectations
from ci.products.sdk_apple_toolchain_evidence import _versions
from ci.tests.phase9_ios_mutation import manifest


def probe(destination):
    specification = manifest()
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    if (os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('GITHUB_EVENT_NAME') != 'pull_request'
            or os.environ.get('GITHUB_REPOSITORY') != 'codex-agent-labs/codex-agent'
            or event['pull_request']['number'] != 31
            or event['pull_request']['head']['repo']['full_name'] != os.environ['GITHUB_REPOSITORY']
            or event['pull_request']['head']['repo']['fork'] is not False
            or event['pull_request']['head']['sha'] != source
            or event['label']['name'] != 'ci:phase9-xcode-probe'
            or subprocess.check_output(['git', 'diff', 'HEAD', '--'], cwd=ROOT)):
        raise ValueError('Xcode probe requires the exact same-repository labeled PR source')
    expected = _toolchain_expectations(git_regular_blob_bytes(
        ROOT, specification['sourcePrerequisite'], _PIN_FILE, max_bytes=1024 * 1024))
    application = Path('/Applications/Xcode_' + expected['xcodeVersion'] + '.app')
    if (not application.is_dir() or application.is_symlink()
            or os.environ.get('DEVELOPER_DIR') != str(application / 'Contents/Developer')
            or os.environ.get('RUNNER_OS') != 'macOS' or os.environ.get('RUNNER_ARCH') != 'ARM64'):
        raise ValueError('Xcode probe requires the pinned installed toolchain on a macOS ARM64 runner')
    destination.mkdir()
    commands = {
        'xcode': ['/usr/bin/xcodebuild', '-version'],
        'swift': ['/usr/bin/xcrun', 'swift', '--version'],
        'signature': ['/usr/bin/codesign', '--verify', '--deep', '--strict', '--verbose=2',
                      '-R=anchor apple', str(application)],
        'signature-details': ['/usr/bin/codesign', '--display', '--verbose=4', str(application)],
        'size': ['/usr/bin/du', '-sk', str(application)],
        'disk': ['/bin/df', '-k', str(application)],
    }
    for sdk in ('iphoneos', 'iphonesimulator'):
        for field in ('version', 'build-version'):
            commands[sdk + '-' + field] = ['/usr/bin/xcrun', '--sdk', sdk, '--show-sdk-' + field]
    records = {}
    started = time.monotonic_ns()
    for name, command in commands.items():
        tick = time.monotonic_ns()
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=300)
            records[name] = dict(command=command, returnCode=result.returncode,
                stdout=result.stdout, stderr=result.stderr, elapsedNs=time.monotonic_ns()-tick)
        except subprocess.TimeoutExpired:
            records[name] = dict(command=command, timedOut=True, elapsedNs=time.monotonic_ns()-tick)
        write_canonical_json(destination / 'observations.json', dict(schemaVersion=1,
            purpose='phase9-matching-xcode-provisioning-feasibility', sourceCommit=source,
            eventCommit=os.environ['GITHUB_SHA'], runId=os.environ['GITHUB_RUN_ID'],
            runAttempt=os.environ['GITHUB_RUN_ATTEMPT'], runnerOS=os.environ['RUNNER_OS'],
            runnerArch=os.environ['RUNNER_ARCH'], expected=expected, observations=records,
            elapsedNs=time.monotonic_ns()-started, productExecutions=0,
            toolchainExported=False, releaseAdmission=False))
    if any(row.get('returnCode') != 0 for row in records.values()):
        raise ValueError('Xcode provisioning probe failed; retain exact observations')
    _versions(records['xcode']['stdout'], records['swift']['stdout'], expected)
    return records


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: phase9_xcode_probe.py DESTINATION')
    probe(Path(sys.argv[1]).absolute())
