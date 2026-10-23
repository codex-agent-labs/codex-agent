"""Transport-only deltas over authenticated immutable Runtime uploads.

References never grant phase admission. The existing original-CI observers,
object verifiers and complete planner replay still authenticate the resolved
bytes. Old full uploads remain valid and are never edited or replaced.
"""
from __future__ import annotations

import hashlib
import base64
from datetime import datetime, timezone
import re
import subprocess
from threading import Event, Lock, Thread
import os
import json
import sys
import time
import shutil
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import reuse

from products.inventory import (
    PRODUCT_JSON_LIMIT, _open_regular_file, _stat_identity,
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_integer,
    require_relative_path, require_sha256, require_sorted_unique_records,
    validate_file_record, write_canonical_json,
)

REPOSITORY = 'codex-agent-labs/codex-agent'
REPOSITORY_ID = 1320780624
PERMISSIONS = {'actions': 'read', 'contents': 'read'}
ENVIRONMENT = ('CODEX_AGENT_READ_APP_ID', 'CODEX_AGENT_READ_INSTALLATION_ID',
               'CODEX_AGENT_READ_APP_KEY_FILE')
_lock = Lock()
_cached = None


def configure_read_app():
    """Install the protected caller credential outside all artifact/workspace roots."""
    for name in ('READ_APP_ID', 'READ_INSTALLATION_ID'):
        if not re.fullmatch(r'[1-9][0-9]{0,19}', os.environ[name]):
            raise ValueError('Protected GitHub App identity is missing or invalid')
    key = os.environ.pop('READ_APP_PRIVATE_KEY')
    if not key or '\x00' in key:
        raise ValueError('Protected GitHub App private key is missing or invalid')
    root = Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    workspace = Path(os.environ['GITHUB_WORKSPACE']).resolve(strict=True)
    if root.is_relative_to(workspace) or workspace.is_relative_to(root):
        raise ValueError('Read credential scratch must be outside the checkout')
    private = Path(tempfile.mkdtemp(prefix='github-read-app-', dir=root))
    key_path = private / 'key.pem'
    with open(os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        stream.write(key)
    values = {
        'CODEX_AGENT_READ_APP_ID': os.environ['READ_APP_ID'],
        'CODEX_AGENT_READ_INSTALLATION_ID': os.environ['READ_INSTALLATION_ID'],
        'CODEX_AGENT_READ_APP_KEY_FILE': str(key_path),
    }
    if any('\n' in value or '\r' in value for value in values.values()):
        raise ValueError('GitHub App environment values must occupy one line')
    with open(os.environ['GITHUB_ENV'], 'a') as stream:
        for name, value in values.items():
            stream.write(f'{name}={value}\n')
    print('Protected read-only GitHub App configured; tokens renew five minutes before expiry.')
    os.environ.update(values)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _encoded(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=')


def _mint(configuration):
    app, installation, key = configuration
    now = int(time.time())
    message = b'.'.join(_encoded(json.dumps(value, separators=(',', ':')).encode())
                        for value in ({'alg': 'RS256', 'typ': 'JWT'},
                                      {'iat': now - 60, 'exp': now + 540, 'iss': app}))
    signed = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', key],
                            input=message, capture_output=True, check=False)
    if signed.returncode:
        raise ValueError('GitHub read App JWT signing failed')
    jwt = (message + b'.' + _encoded(signed.stdout)).decode('ascii')
    request = urllib.request.Request(
        f'https://api.github.com/app/installations/{installation}/access_tokens',
        data=json.dumps({'repository_ids': [REPOSITORY_ID], 'permissions': PERMISSIONS}).encode(),
        headers={'Authorization': f'Bearer {jwt}', 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'})
    with urllib.request.build_opener(_NoRedirect()).open(request, timeout=60) as response:
        value = json.loads(response.read(1024 * 1024))
    permissions = value.get('permissions', {})
    repositories = value.get('repositories', [])
    if (permissions != {**PERMISSIONS, 'metadata': 'read'}
            or len(repositories) != 1 or repositories[0].get('id') != REPOSITORY_ID
            or repositories[0].get('full_name') != REPOSITORY):
        raise ValueError('GitHub read App token has unexpected repository or permission scope')
    token = value.get('token', '')
    if not isinstance(token, str) or re.fullmatch(r'[A-Za-z0-9_.-]{20,8192}', token) is None:
        raise ValueError('GitHub read App returned an invalid token')
    expires = datetime.strptime(value['expires_at'], '%Y-%m-%dT%H:%M:%SZ').replace(
        tzinfo=timezone.utc).timestamp()
    if not time.time() + 300 < expires <= time.time() + 3660:
        raise ValueError('GitHub read App returned an invalid token lifetime')
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        print(f'::add-mask::{token}', flush=True)
    count('githubAppTokenRenewals')
    return token, expires


def token_for(url, fallback):
    """Replace only official same-repository Actions/Git reads, before expiry."""
    global _cached
    parsed = urllib.parse.urlsplit(url)
    prefix = f'/repos/{REPOSITORY}/'
    if (parsed.scheme != 'https' or parsed.netloc != 'api.github.com'
            or not parsed.path.startswith(prefix)
            or parsed.path[len(prefix):].split('/')[0] not in {'actions', 'git', 'contents', 'commits'}):
        return fallback
    configuration = tuple(os.environ.get(name, '') for name in ENVIRONMENT)
    if not any(configuration):
        return fallback
    app, installation, key = configuration
    if (not all(configuration) or not re.fullmatch(r'[1-9][0-9]{0,19}', app)
            or not re.fullmatch(r'[1-9][0-9]{0,19}', installation)
            or not Path(key).is_absolute() or Path(key).resolve(strict=True) != Path(key)
            or not Path(key).is_file()):
        raise ValueError('GitHub read App caller configuration is incomplete or invalid')
    if os.name != 'nt' and Path(key).stat().st_mode & 0o077:
        raise ValueError('GitHub read App private key must not be accessible to other users')
    count('githubAppCredentialLookups')
    with _lock:
        if _cached is None or _cached[0] != configuration or _cached[2] <= time.time() + 300:
            token, expires = _mint(configuration)
            _cached = configuration, token, expires
        return _cached[1]


def api_json(url, token):
    return reuse.api_json(url, token_for(url, token))


def paginated_items(url, key, token, *, request_json=None):
    # Renew at each page, not merely at the beginning of a long discovery call.
    result, page = [], 1
    separator = '&' if '?' in url else '?'
    while True:
        value = (api_json if request_json is None else request_json)(
            f'{url}{separator}per_page=100&page={page}', token).get(key)
        if not isinstance(value, list):
            raise ValueError(f'GitHub response is missing {key}')
        result.extend(value)
        if len(value) < 100:
            return result
        page += 1


def download_artifact(artifact, token):
    return reuse.download_artifact(artifact, token_for(artifact['archive_download_url'], token))


def download_artifact_to_file(artifact, token, destination, *, max_bytes):
    return reuse.download_artifact_to_file(artifact,
        token_for(artifact['archive_download_url'], token), destination, max_bytes=max_bytes)


REFERENCE_NAME = "runtime-references.json"
ORIGINAL_REFERENCE_NAME = "runtime-original-references.json"
SDK_REFERENCE_NAME = 'sdk-runtime-reference.json'
SDK_INPUT_REFERENCE_NAME = 'sdk-input-reference.json'
_ROOTS = {"product-resume-inputs", "product-resume-state", "runtime-state"}
_MEASUREMENTS = ContextVar('throughput_measurements', default=())
_MEASUREMENT_LOCK = Lock()
_VOLUMES = ContextVar('throughput_volumes', default=())


def count(name, amount=1):
    """Inclusive operation counters; never identifiers, arguments or credentials."""
    # Context propagation shares parent counters across bounded verifier threads.
    measurements = _MEASUREMENTS.get()
    if measurements:
        with _MEASUREMENT_LOCK:
            for counters in measurements:
                counters[name] = counters.get(name, 0) + amount


def report_api_error(error: urllib.error.HTTPError) -> None:
    """Report bounded classifications and numeric headers, never URLs or credentials."""
    details = {"status": error.code, "messageKind": "unclassified", "rateLimit": {}}
    for name in ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-used",
                 "x-ratelimit-reset", "retry-after"):
        value = error.headers.get(name, "") if error.headers else ""
        if isinstance(value, str) and len(value) <= 20 and value.isascii() and value.isdecimal():
            details["rateLimit"][name] = int(value)
    try:
        body = error.read(4096).lower()
        for phrase, kind in ((b"secondary rate limit", "secondary-rate-limit"),
                             (b"rate limit exceeded", "primary-rate-limit"),
                             (b"resource not accessible", "resource-not-accessible"),
                             (b"bad credentials", "bad-credentials")):
            if phrase in body:
                details["messageKind"] = kind
                break
    except (OSError, ValueError, AttributeError, TypeError):
        pass  # Diagnostic failure must not replace the original HTTP failure.
    print("github-api-error " + json.dumps(details, sort_keys=True), file=sys.stderr, flush=True)


def measured(operation):
    @wraps(operation)
    def timed(*args, **kwargs):
        if os.environ.get('CODEX_AGENT_THROUGHPUT_TRACE') != '1':
            return operation(*args, **kwargs)
        counters = {}
        token = _MEASUREMENTS.set((*_MEASUREMENTS.get(), counters))
        wall, cpu, succeeded = time.perf_counter(), time.process_time(), False
        try:
            result = operation(*args, **kwargs)
            succeeded = True
            return result
        except urllib.error.HTTPError as error:
            report_api_error(error)
            raise
        finally:
            _MEASUREMENTS.reset(token)
            print('throughput ' + json.dumps(dict(operation=operation.__name__, success=succeeded,
                elapsedSeconds=round(time.perf_counter() - wall, 6),
                processCpuSeconds=round(time.process_time() - cpu, 6),
                inclusiveCounters=counters), sort_keys=True), file=sys.stderr)
    return timed


@contextmanager
def measured_volume(operation, root):
    """Observe volume free space, not attributable bytes or unique APFS extents.

    Periodic sampling is at most 1 Hz, plus explicit operation endpoints.
    Nested contexts on this volume share the outer sampler and its observation.
    """
    if os.environ.get('CODEX_AGENT_THROUGHPUT_TRACE') != '1':
        yield
        return
    started, succeeded = time.perf_counter(), False
    lock, stop = Lock(), Event()
    state = {'sampleCount': 0, 'sampleErrors': 0, 'minimumObservedFreeBytes': None}
    token, thread, first, last, path = None, None, None, None, None

    def sample():
        try:
            free = shutil.disk_usage(path).free
        except Exception:
            with lock:
                state['sampleErrors'] += 1
            return None
        with lock:
            state['sampleCount'] += 1
            minimum = state['minimumObservedFreeBytes']
            state['minimumObservedFreeBytes'] = free if minimum is None else min(minimum, free)
        return free

    def poll():
        while not stop.wait(1):
            sample()

    try:
        path = Path(root)
        device = path.stat().st_dev
    except Exception:
        state['sampleErrors'] += 1
        path = None
    else:
        if device in _VOLUMES.get():
            yield
            return
        token = _VOLUMES.set((*_VOLUMES.get(), device))
        first = sample()
        try:
            thread = Thread(target=poll, name='throughput-volume', daemon=True)
            thread.start()
        except Exception:
            with lock:
                state['sampleErrors'] += 1
            thread = None
    try:
        yield
        succeeded = True
    finally:
        try:
            stop.set()
            if thread is not None:
                thread.join(timeout=2)
            stopped = thread is None or not thread.is_alive()
            if path is not None and stopped:
                last = sample()
            with lock:
                observation = dict(state)
            minimum = observation['minimumObservedFreeBytes']
            observation.update(operation=operation, success=succeeded, samplerStopped=stopped,
                elapsedSeconds=round(time.perf_counter() - started, 6), sampleIntervalSeconds=1,
                freeBytesAtStart=first, freeBytesAtEnd=last,
                observedFreeBytesDelta=None if first is None or last is None else last - first,
                maximumObservedFreeBytesDecrease=None if first is None or minimum is None else first - minimum)
            print('throughput-volume ' + json.dumps(observation, sort_keys=True), file=sys.stderr)
        except Exception:
            pass  # Diagnostics must never replace the operation's result or original exception.
        finally:
            if token is not None:
                _VOLUMES.reset(token)


def _path(value):
    path = require_relative_path(value, "Runtime reference path")
    if path.split("/")[0] not in _ROOTS or "/" not in path:
        raise ValueError("Runtime reference is outside the original handoff roots")
    return path


def validate_references(value, state_wave, *, sdk_state_wave=None):
    value = require_exact_keys(value, {"schemaVersion", "base", "inventory", "references"},
                               "Runtime references")
    if require_integer(value["schemaVersion"], "Runtime references schema", 1) != 1:
        raise ValueError("Unsupported Runtime references schema")
    base_keys = {"artifactId", "artifactSha256", "stateWave"}
    if isinstance(value["base"], dict) and "referenceControlSha256" in value["base"]:
        base_keys.add("referenceControlSha256")
    if isinstance(value["base"], dict) and "sdkStateWave" in value["base"]:
        base_keys.add("sdkStateWave")
    if isinstance(value["base"], dict) and "runAttempt" in value["base"]:
        base_keys.add("runAttempt")
    base = require_exact_keys(value["base"], base_keys,
                              "Runtime reference base")
    require_integer(base["artifactId"], "Runtime reference upload ID", 1)
    require_sha256(base["artifactSha256"], "Runtime reference upload digest")
    if "runAttempt" in base:
        require_integer(base["runAttempt"], "Runtime reference original attempt", 1)
    if "referenceControlSha256" in base:
        require_sha256(base["referenceControlSha256"], "Runtime reference control digest")
    wave = require_integer(base["stateWave"], "Runtime reference base wave")
    sdk_order = (3, 1, 2, 6, 19, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18)
    base_sdk = (require_integer(base["sdkStateWave"], "SDK reference base wave", 1)
                if "sdkStateWave" in base else None)
    if sdk_state_wave is None:
        if base_sdk is not None or type(state_wave) is not int or not 0 <= wave < state_wave <= 5:
            raise ValueError("Runtime reference must identify a strictly earlier Runtime wave")
    elif (type(sdk_state_wave) is not int or sdk_state_wave not in sdk_order
            or type(state_wave) is not int or state_wave != 0
            or not 0 <= wave <= 5
            or base_sdk is not None and (type(base_sdk) is not int or base_sdk not in sdk_order
                or wave != 0 or sdk_order.index(base_sdk) >= sdk_order.index(sdk_state_wave))):
        raise ValueError("SDK reference must identify a strictly earlier campaign wave")
    inventory = require_sorted_unique_records(value["inventory"], "Runtime reference inventory")
    if not inventory or len(inventory) > 16_384:
        raise ValueError("Runtime reference inventory exceeds its fixed bound")
    files = {}
    for record in inventory:
        validate_file_record(record, "Runtime reference file", with_kind=False, allow_empty=True)
        files[_path(record["relativePath"])] = record
    # SDK carriers retain large iOS aliases; archive and individual-file bounds stay unchanged.
    expanded_limit = (32 if sdk_state_wave is not None else 16) * 1024**3
    if (sum(record["bytes"] for record in inventory) > expanded_limit
            or any(record["bytes"] > 8 * 1024 * 1024 * 1024 for record in inventory)):
        raise ValueError("Expanded Runtime reference inventory exceeds the transport byte bounds")
    references = require_sorted_unique_records(value["references"], "Runtime references")
    if not references:
        raise ValueError("Runtime reference transport requires inherited files")
    for record in references:
        require_exact_keys(record, {"relativePath", "sourcePath", "bytes", "sha256"},
                           "Runtime reference")
        _path(record["sourcePath"])
        target = _path(record["relativePath"])
        if {key: record[key] for key in ("relativePath", "bytes", "sha256")} != files.get(target):
            raise ValueError("Runtime reference differs from its exact file inventory")
    return value


def _copy_exact(source, destination, record, *, destination_directory=None):
    descriptor, before = _open_regular_file(source, "Runtime reference source", reject_symlink_parents=True)
    try:
        if before.st_size != record["bytes"]:
            raise ValueError("Runtime reference source size differs from its immutable identity")
        if destination_directory is None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            output = destination.open("xb")
        else:
            # Cache publication holds the verified parent descriptor through
            # creation and rename; caller-controlled parents cannot redirect it.
            require_relative_path(destination.name, "Runtime reference destination member")
            output = os.fdopen(os.open(destination.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                       0o600, dir_fd=destination_directory), "wb")
        digest = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=False) as incoming, output as outgoing:
            remaining = before.st_size
            while remaining:
                chunk = incoming.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("Runtime reference source was truncated")
                digest.update(chunk)
                outgoing.write(chunk)
                remaining -= len(chunk)
            if incoming.read(1) or _stat_identity(before) != _stat_identity(os.fstat(descriptor)):
                raise ValueError("Runtime reference source changed during resolution")
        if "sha256:" + digest.hexdigest() != record["sha256"]:
            raise ValueError("Runtime reference source digest differs from its immutable identity")
        count('verifiedCopyBytes', record['bytes'])
        count('verifiedCopies')
    finally:
        os.close(descriptor)


def stage_reference_handoff(handoff, base_root, base_capture, destination, *, state_wave, sdk_state_wave=None):
    """Emit only changed files and exact references; never mutate the full handoff."""
    transport = load_canonical_json_bytes(read_regular_file_bytes(
        base_capture, max_bytes=PRODUCT_JSON_LIMIT, reject_symlink_parents=True))
    artifact = transport["artifact"]
    base = {"artifactId": artifact["id"], "artifactSha256": artifact["digest"],
            "stateWave": transport.get("stateWave", 0)}
    if "captureProducer" in transport:
        base["runAttempt"] = transport["captureProducer"]["runAttempt"]
    if "sdkStateWave" in transport:
        base["sdkStateWave"] = transport["sdkStateWave"]
    if "referenceControlSha256" in transport:
        base["referenceControlSha256"] = transport["referenceControlSha256"]
    inventory = regular_file_inventory(handoff, allow_empty=True)
    original = regular_file_inventory(base_root, allow_empty=True)
    by_content = {}
    for record in original:
        by_content.setdefault((record["bytes"], record["sha256"]), record["relativePath"])
    references = [{**record, "sourcePath": by_content[(record["bytes"], record["sha256"])]}
                  for record in inventory if (record["bytes"], record["sha256"]) in by_content]
    if not references:
        raise ValueError("Runtime reference export has no existing immutable files")
    value = validate_references({"schemaVersion": 1, "base": base,
                                "inventory": inventory, "references": references}, state_wave, sdk_state_wave=sdk_state_wave)
    inherited = {record["relativePath"] for record in references}
    with tempfile.TemporaryDirectory(prefix="runtime-reference-export-") as temporary:
        prepared = Path(temporary).resolve() / "handoff"
        prepared.mkdir()
        for record in inventory:
            if record["relativePath"] not in inherited:
                _copy_exact(Path(handoff) / record["relativePath"], prepared / record["relativePath"], record)
        write_canonical_json(prepared / REFERENCE_NAME, value)
        if (regular_file_inventory(handoff, allow_empty=True) != inventory
                or regular_file_inventory(base_root, allow_empty=True) != original):
            raise ValueError("Runtime reference export inputs changed")
        publish_regular_tree(prepared, destination, allow_empty=True)
    return value


def selected_reference_paths(value, *, omit_sdk_ios_binary=False, completed_frozen=None,
                             omit_resume_input_aliases=False):
    """Select physical bodies while retaining all authenticated controls.

    The full authenticated manifest still declares every preserved byte. This
    selects materialization only. An unrelated iOS worker scope grants no phase
    trust; a completed native proof may separately defer its exact Runtime bodies.
    Concrete legacy members remain present. New original references make the
    large binary and its aliases selectable before downloading any body.

    Scoped SDK workers read the current plan and product-resume-state, never
    the earlier input snapshots. Omit only their redundant reference targets;
    physical source members and the complete authenticated state remain intact.
    """
    if type(omit_sdk_ios_binary) is not bool or type(omit_resume_input_aliases) is not bool:
        raise ValueError("SDK reference selection must be boolean")
    deferred = frozenset()
    if completed_frozen is not None:
        from reuse_qualification import CompletedFrozenReuse
        if type(completed_frozen) is not CompletedFrozenReuse:
            raise ValueError("Deferred Runtime objects require native completed evidence")
        # Legacy handoffs still use the ordinary body-backed Contract verifier.
        # The small manifest only selects transport; native semantic admission
        # independently authenticates all of its bytes before planning.
        contract_controls = any(row['relativePath'] ==
            'product-resume-state/authenticated-contract/contract-input/contract-manifest.json'
            for row in value['inventory'])
        deferred = completed_frozen.deferred_objects(include_contract=contract_controls)
    bodies = {(row['bytes'], row['sha256']) for row in value['inventory']
        if omit_sdk_ios_binary and row['relativePath'].startswith(
            'product-resume-state/prior-failed-sdk/sdk-ios/binary/ios/original/shard/')
        and '/v1/objects/sha256/' in row['relativePath'] and row['relativePath'].endswith('.zip')}
    inherited = {row['relativePath'] for row in value['references']}
    return {row['relativePath'] for row in value['inventory']
        if row['relativePath'] not in inherited or
        ((row['bytes'], row['sha256']) not in bodies and row['sha256'] not in deferred
         and not (omit_resume_input_aliases
                  and row['relativePath'].startswith('product-resume-inputs/')
                  and row['relativePath'] != 'product-resume-inputs/plan/impact-plan.json'))}


def validate_sdk_input_source(value):
    """Validate a locator; the caller must independently authorize its selection."""
    from products.receipt import validate_producer
    source = require_exact_keys(value, {'artifactId', 'artifactSha256', 'producer',
        'workflowSha'}, 'SDK original source')
    require_integer(source['artifactId'], 'SDK Runtime original artifact ID', 1)
    require_sha256(source['artifactSha256'], 'SDK original artifact digest')
    import re
    if type(source['workflowSha']) is not str or re.fullmatch('[0-9a-f]{40}', source['workflowSha']) is None:
        raise ValueError('SDK original workflow is not exact')
    validate_producer(source['producer'])
    return source


def validate_sdk_runtime_source(value):
    source = require_exact_keys(value, {'artifactId', 'artifactSha256', 'producer',
        'workflowSha', 'buildKey', 'metadataReceiptSha256'}, 'SDK Runtime original source')
    validate_sdk_input_source({key: source[key] for key in
        ('artifactId', 'artifactSha256', 'producer', 'workflowSha')})
    for field in ('buildKey', 'metadataReceiptSha256'):
        require_sha256(source[field], 'SDK Runtime original ' + field)
    return source


def validate_sdk_input_binding(value):
    value = require_exact_keys(value, {'schemaVersion', 'source', 'runtimeSource',
        'planSha256'}, 'SDK input binding')
    if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1:
        raise ValueError('Unsupported SDK input binding schema')
    validate_sdk_input_source(value['source'])
    validate_sdk_runtime_source(value['runtimeSource'])
    require_sha256(value['planSha256'], 'SDK input binding plan digest')
    return value


def sdk_input_binding(archive, physical):
    """Read a bounded control-only envelope after complete ZIP authentication."""
    paths = {row['relativePath'] for row in physical}
    if SDK_INPUT_REFERENCE_NAME not in paths:
        return None
    plan_name = 'runtime-capture/plan/impact-plan.json'
    if paths != {SDK_INPUT_REFERENCE_NAME, plan_name}:
        raise ValueError('SDK input binding must contain only reference and current plan')
    import zipfile
    with zipfile.ZipFile(archive) as zipped:
        if zipped.getinfo(SDK_INPUT_REFERENCE_NAME).file_size > PRODUCT_JSON_LIMIT:
            raise ValueError('SDK input binding exceeds its control bound')
        value = validate_sdk_input_binding(load_canonical_json_bytes(zipped.read(SDK_INPUT_REFERENCE_NAME)))
    if next(row['sha256'] for row in physical if row['relativePath'] == plan_name) != value['planSha256']:
        raise ValueError('SDK input binding differs from its current plan')
    return value


def validate_sdk_runtime_reference(value):
    """Current-plan SDK transport may refer to its exact original Runtime upload."""
    value = require_exact_keys(value, {'schemaVersion', 'source', 'inventory'}, 'SDK Runtime reference')
    if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1:
        raise ValueError('Unsupported SDK Runtime reference schema')
    validate_sdk_runtime_source(value['source'])
    inventory = require_sorted_unique_records(value['inventory'], 'SDK Runtime logical inventory')
    if not inventory or len(inventory) > 16_384:
        raise ValueError('SDK Runtime reference exceeds the member bound')
    for row in inventory:
        validate_file_record(row, 'SDK Runtime reference file', with_kind=False, allow_empty=True)
        path = require_relative_path(row['relativePath'], 'SDK Runtime reference path')
        if path.split('/')[0] not in {'runtime-capture', 'sdk-inputs'} or '/' not in path:
            raise ValueError('SDK Runtime reference changes the standard input layout')
    if (sum(row['bytes'] for row in inventory) > 16 * 1024**3
            or any(row['bytes'] > 8 * 1024**3 for row in inventory)):
        raise ValueError('SDK Runtime reference exceeds the byte bound')
    if not any(row['relativePath'].startswith('runtime-capture/original/') for row in inventory):
        raise ValueError('SDK Runtime reference has no original body')
    return value


def sdk_runtime_reference_inventory(archive, physical):
    """Read only after complete enclosing ZIP authentication; return logical files."""
    if SDK_REFERENCE_NAME not in {row['relativePath'] for row in physical}:
        return None
    import zipfile
    with zipfile.ZipFile(archive) as zipped:
        if zipped.getinfo(SDK_REFERENCE_NAME).file_size > PRODUCT_JSON_LIMIT:
            raise ValueError('SDK Runtime reference exceeds its control bound')
        value = validate_sdk_runtime_reference(load_canonical_json_bytes(zipped.read(SDK_REFERENCE_NAME)))
    expected = [row for row in value['inventory']
                if not row['relativePath'].startswith('runtime-capture/original/')]
    if [row for row in physical if row['relativePath'] != SDK_REFERENCE_NAME] != expected:
        raise ValueError('SDK Runtime reference has missing, overlapping or unexpected concrete bytes')
    return value


def resolve_reference_handoff(original, base_root, value, *, state_wave, sdk_state_wave=None,
                              selected_paths=None, capture_source=None):
    """Resolve a freshly authenticated base; caller must still admit all phases."""
    if (base_root is None) != (capture_source is not None):
        raise ValueError("Runtime references require exactly one private source")
    value = validate_references(value, state_wave, sdk_state_wave=sdk_state_wave)
    referenced = {record["relativePath"] for record in value["references"]}
    materialized = regular_file_inventory(original, allow_empty=True, excluded_paths=(REFERENCE_NAME,))
    if materialized != [record for record in value["inventory"] if record["relativePath"] not in referenced]:
        raise ValueError("Runtime reference delta has missing, overlapping or unexpected files")
    selected = [record for record in value["references"]
                if selected_paths is None or record['relativePath'] in selected_paths]
    if capture_source is not None:
        # The same authenticated reader may write straight into private custody;
        # the complete inventory below still rejects missing or altered bytes.
        capture_source(selected, Path(original))
    else:
        for record in selected:
            _copy_exact(Path(base_root) / record["sourcePath"], Path(original) / record["relativePath"], record)
    (Path(original) / REFERENCE_NAME).unlink()
    inventory = [row for row in value['inventory'] if selected_paths is None or row['relativePath'] in selected_paths]
    if regular_file_inventory(original, allow_empty=True) != inventory:
        raise ValueError("Resolved Runtime reference inventory differs from the frozen bytes")
    return inventory


def validate_original_references(value):
    """Validate locators only; caller authenticates the enclosing upload first."""
    from products.receipt import validate_phase_receipt
    from products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId
    from sdk_phase import SDK_FAMILY_INSTANCES, completed_recovery_folder
    value = require_exact_keys(value, {"schemaVersion", "inventory", "sources", "references"},
                               "Runtime original references")
    if value["schemaVersion"] not in (1, 2, 3) or type(value["schemaVersion"]) is not int:
        raise ValueError("Unsupported Runtime original references schema")
    inventory = require_sorted_unique_records(value["inventory"], "Original reference inventory")
    if not inventory or len(inventory) > 16_384:
        raise ValueError("Original reference inventory exceeds its fixed bound")
    files = {}
    for record in inventory:
        validate_file_record(record, "Original reference file", with_kind=False, allow_empty=True)
        if record["relativePath"].split("/")[0] not in {"product-resume-inputs", "product-resume-state"}:
            raise ValueError("Original reference inventory has unexpected roots")
        files[_path(record["relativePath"])] = record
    if (sum(row["bytes"] for row in inventory) > 16 * 1024**3
            or any(row["bytes"] > 8 * 1024**3 for row in inventory)):
        raise ValueError("Original reference inventory exceeds the transport byte bounds")
    sources = require_sorted_unique_records(value["sources"], "Original reference sources")
    if len(sources) > {1: 47, 2: 48, 3: 49 + len(SDK_FAMILY_INSTANCES["native-package"])}[value["schemaVersion"]]:
        raise ValueError("Original references exceed the registered Runtime source bound")
    by_source = {}
    for source in sources:
        require_exact_keys(source, {"relativePath", "kind", "receipt", "artifactId", "artifactSha256"},
                           "Original reference source")
        receipt = validate_phase_receipt(source["receipt"])
        instance = PhaseInstanceId(*(receipt[key] for key in ("product", "component", "phase", "target")))
        sdk_binary = (value["schemaVersion"] in (2, 3) and source["kind"] == "sdk-binary"
                      and instance == PhaseInstanceId("sdk", "sdk-ios", "binary", "ios"))
        sdk_package = (value["schemaVersion"] == 3 and source["kind"] == "sdk-package"
                       and (instance == PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
                            or instance in SDK_FAMILY_INSTANCES["native-package"]))
        if instance not in PHASE_INSTANCE_IDS or instance.product != "runtime" and not (sdk_binary or sdk_package):
            raise ValueError("Original reference is not a registered Runtime phase")
        if sdk_binary:
            prefix = "product-resume-state/prior-failed-sdk/sdk-ios/binary/ios/original"
        elif sdk_package:
            prefix = (f"product-resume-state/{completed_recovery_folder(instance)}/"
                      f"{instance.component}/package/{instance.target}/original")
        elif source["kind"] == "phase":
            prefix = (f"product-resume-state/prior-failed-runtime/{instance.component}/{instance.phase}/"
                      f"{instance.target}/phases/{instance.phase}/original")
        elif source["kind"] == "aggregate" and instance == PhaseInstanceId(
                "runtime", "runtime-aggregate", "metadata", "aggregate"):
            from products.inventory import canonical_json_bytes, sha256_bytes
            prefix = ("product-resume-state/runtime-aggregate-release-evidence/0/handoffs/"
                      + sha256_bytes(canonical_json_bytes(receipt))[7:])
        else:
            raise ValueError("Original reference source kind differs from its phase")
        if source["relativePath"] != prefix:
            raise ValueError("Original reference source changes its registered destination")
        require_integer(source["artifactId"], "Original reference upload ID", 1)
        require_sha256(source["artifactSha256"], "Original reference upload SHA")
        by_source[prefix] = source
    references = require_sorted_unique_records(value["references"], "Original member references")
    mappings = {row["relativePath"]: row for row in references}
    targets = {row["relativePath"] for row in references}
    if not references:
        raise ValueError("Original reference transport has no references")
    used = set()
    for row in references:
        require_exact_keys(row, {"relativePath", "source", "sourcePath", "bytes", "sha256"},
                           "Original member reference")
        target = _path(row["relativePath"])
        if {key: row[key] for key in ("relativePath", "bytes", "sha256")} != files.get(target):
            raise ValueError("Original member reference changes its qualified inventory")
        source_path = require_relative_path(row["sourcePath"], "Original reference member")
        if row["source"] is None:
            source = files.get(_path(source_path))
            if (source_path in targets or source is None
                    or any(source[key] != row[key] for key in ("bytes", "sha256"))):
                raise ValueError("Local reference is missing, cyclic or changes byte identity")
        else:
            prefix = _path(row["source"])
            primary = prefix + "/" + source_path
            primary_file = files.get(primary)
            primary_reference = mappings.get(primary)
            if (prefix not in by_source or primary_file is None or primary_reference is None
                    or primary_reference.get("source") != prefix
                    or primary_reference.get("sourcePath") != source_path
                    or any(primary_file[key] != row[key] for key in ("bytes", "sha256"))):
                raise ValueError("Original member reference changes its registered source path")
            if by_source[prefix]["kind"] == "phase" and source_path.startswith("inputs/"):
                raise ValueError("Original phase reference includes unretained predecessor inputs")
            if by_source[prefix]["kind"] in {"sdk-binary", "sdk-package"} and not source_path.startswith("shard/"):
                raise ValueError("SDK original references are limited to their authenticated binary shard")
            used.add(prefix)
    if used != set(by_source):
        raise ValueError("Original reference transport has unused source locators")
    return value


def stage_original_reference_handoff(roots, sources, destination):
    """Keep one concrete copy of local bytes; leave immutable originals upstream."""
    if set(roots) != {"product-resume-inputs", "product-resume-state"}:
        raise ValueError("Initial original references require both original roots")
    inventory, paths = [], {}
    for name, root in roots.items():
        if name not in {"product-resume-inputs", "product-resume-state"}:
            raise ValueError("Initial original reference has unexpected roots")
        for row in regular_file_inventory(root, allow_empty=True):
            path = name + "/" + row["relativePath"]
            inventory.append({**row, "relativePath": path})
            paths[path] = Path(root) / row["relativePath"]
    inventory.sort(key=lambda row: row["relativePath"])
    upstream = {}
    for row in inventory:
        prefix = next((source["relativePath"] for source in sources
                       if row["relativePath"].startswith(source["relativePath"] +
                           ("/shard/" if source["kind"] in {"sdk-binary", "sdk-package"} else "/"))), None)
        if prefix is not None:
            upstream.setdefault((row["bytes"], row["sha256"]),
                                (prefix, row["relativePath"][len(prefix) + 1:]))
    references, concrete, contents, used = [], [], {}, set()
    for row in inventory:
        prefix = next((source["relativePath"] for source in sources
                       if row["relativePath"].startswith(source["relativePath"] +
                           ("/shard/" if source["kind"] in {"sdk-binary", "sdk-package"} else "/"))), None)
        identity = row["bytes"], row["sha256"]
        if prefix is not None:
            references.append({**row, "source": prefix,
                               "sourcePath": row["relativePath"][len(prefix) + 1:]})
            used.add(prefix)
        elif identity in upstream:
            source, path = upstream[identity]
            references.append({**row, "source": source, "sourcePath": path})
            used.add(source)
        elif identity in contents:
            references.append({**row, "source": None, "sourcePath": contents[identity]})
        else:
            concrete.append(row)
            contents[identity] = row["relativePath"]
    schema = (3 if any(source["kind"] == "sdk-package" for source in sources) else
              2 if any(source["kind"] == "sdk-binary" for source in sources) else 1)
    value = validate_original_references({"schemaVersion": schema,
        "inventory": inventory,
        "sources": sorted((source for source in sources if source["relativePath"] in used),
                          key=lambda row: row["relativePath"]), "references": references})
    with tempfile.TemporaryDirectory(prefix="runtime-original-reference-export-") as temporary:
        prepared = Path(temporary).resolve() / "handoff"
        prepared.mkdir()
        for row in concrete:
            _copy_exact(paths[row["relativePath"]], prepared / row["relativePath"], row)
        write_canonical_json(prepared / ORIGINAL_REFERENCE_NAME, value)
        after = sorted(({**row, "relativePath": name + "/" + row["relativePath"]}
                        for name, root in roots.items()
                        for row in regular_file_inventory(root, allow_empty=True)),
                       key=lambda row: row["relativePath"])
        if after != inventory:
            raise ValueError("Original reference export inputs changed")
        publish_regular_tree(prepared, destination, allow_empty=True)
    return value


def resolve_original_reference_handoff(original, value, capture_source, *, selected_paths=None):
    """Resolve qualified members, then let existing admission replay authenticate phases."""
    value = validate_original_references(value)
    targets = {row["relativePath"] for row in value["references"]}
    if regular_file_inventory(original, allow_empty=True, excluded_paths=(ORIGINAL_REFERENCE_NAME,)) != [
            row for row in value["inventory"] if row["relativePath"] not in targets]:
        raise ValueError("Original reference delta has missing, overlapping or unexpected files")
    for source in value["sources"]:
        records = [row for row in value['references'] if row['source'] == source['relativePath']
                   and (selected_paths is None or row['relativePath'] in selected_paths)]
        if records:
            capture_source(source, records, Path(original))
    for row in value["references"]:
        if row["source"] is None and (selected_paths is None or row['relativePath'] in selected_paths):
            _copy_exact(Path(original) / row["sourcePath"], Path(original) / row["relativePath"], row)
    inventory = [row for row in value['inventory'] if selected_paths is None or row['relativePath'] in selected_paths]
    if regular_file_inventory(original, allow_empty=True, excluded_paths=(ORIGINAL_REFERENCE_NAME,)) != inventory:
        raise ValueError("Resolved original reference inventory differs from its frozen bytes")
    (Path(original) / ORIGINAL_REFERENCE_NAME).unlink()
    return inventory
