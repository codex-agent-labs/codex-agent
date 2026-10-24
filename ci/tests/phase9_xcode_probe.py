"""Matching-Xcode observation and separately selected private provisioning; no products."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from ci.products.inventory import git_regular_blob_bytes, sha256_file, write_canonical_json
from ci.products.sdk_apple_package_source import _PIN_FILE, _toolchain_expectations
from ci.products.sdk_apple_toolchain_evidence import _versions
from ci.tests.phase9_ios_mutation import manifest


def probe(destination, *, provision=False):
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
            or event['label']['name'] != ('ci:phase9-xcode-provision' if provision else 'ci:phase9-xcode-probe')
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
    if provision:
        export_private_image(destination, application, records)
    return records


def export_private_image(destination, application, records):
    """External encrypted transport, not deterministic product or release bytes."""
    code_hash = '502eca5e95e1b8eaaf52e9b38617e8e7d23f46db1d7122169443c05837c40cff'
    if 'CandidateCDHashFull sha256=' + code_hash not in records['signature-details']['stderr'].splitlines():
        raise ValueError('Installed Xcode differs from the independently observed Apple code identity')
    recipient = ROOT / 'ci/tests/fixtures/phase9-xcode-recipient.pem'
    recipient_digest = 'sha256:8111e312e095ba0202c4740eaf1101fca0b3e927d310fcf2b2d73557cc770ca5'
    if sha256_file(recipient, reject_symlink_parents=True) != recipient_digest:
        raise ValueError('Xcode transport recipient differs from the approved local-only key')
    started = time.monotonic_ns()
    image = destination.parent / 'xcode-26.6.dmg'
    encrypted = destination / 'xcode-26.6.dmg.cms'
    partial = encrypted.with_suffix('.partial')
    if any(path.exists() or path.is_symlink() for path in (image, encrypted, partial)):
        raise ValueError('Xcode transport must not overwrite an existing input')
    subprocess.run(['/usr/bin/hdiutil', 'create', '-srcfolder', str(application), '-format', 'ULFO',
        '-fs', 'HFS+', '-volname', 'Phase9Xcode266', str(image)], check=True, timeout=1800)
    image_bytes = image.stat().st_size
    if not 0 < image_bytes < 5 * 1024**3:
        raise ValueError(f'Xcode image exceeds the bounded local provisioning capacity: {image_bytes} bytes')
    image_digest = sha256_file(image)
    image_ns = time.monotonic_ns() - started
    subprocess.run(['/usr/bin/openssl', 'cms', '-encrypt', '-binary', '-stream', '-aes256',
        '-in', str(image), '-out', str(partial), '-outform', 'DER', str(recipient)], check=True, timeout=600)
    if partial.stat().st_size > 5 * 1024**3:
        raise ValueError('Encrypted Xcode image exceeds the transport limit')
    partial.rename(encrypted)
    write_canonical_json(destination / 'provisioning.json', dict(schemaVersion=1,
        purpose='private-local-toolchain-provisioning-not-product-admission',
        observationSha256=sha256_file(destination / 'observations.json'), appleCodeHash=code_hash,
        recipientSha256=recipient_digest, imageSha256=image_digest, imageBytes=image_bytes,
        encryptedSha256=sha256_file(encrypted), encryptedBytes=encrypted.stat().st_size,
        imageElapsedNs=image_ns, elapsedNs=time.monotonic_ns()-started,
        productExecutions=0, privateKeyTransferred=False, plaintextUploaded=False))


if __name__ == '__main__':
    if len(sys.argv) not in (2, 3) or (len(sys.argv) == 3 and sys.argv[2] != '--provision'):
        raise SystemExit('usage: phase9_xcode_probe.py DESTINATION [--provision]')
    probe(Path(sys.argv[1]).absolute(), provision=len(sys.argv) == 3)
