"""Compose authenticated protected-upload capture with the existing S858 bridge.

The caller selects upload, metadata, workflow and SDK Git policy identities.
This command neither elects them nor chooses compatibility ranges or signs.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    # Use the same products namespace as the established standalone CI entrypoints.
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from runtime_reference_transport import measured

from products.inventory import (
    publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_regular_directory, require_sha256, snapshot_regular_tree,
)
from products.runtime_aggregate_handoff import _public_policy
from products.sdk_package import _require_capability_output_separate
from products.sdk_protected_runtime import stage_protected_runtime_sdk_inputs
from products.restore import memoized_file_inventory as regular_file_inventory, verification_scoped
from products.sdk_release_selection import read_sdk_release_selection, require_sdk_runtime_compatibility_policy


def stage_sdk_input_binding(plan_path, destination, *, sdk_inputs_source,
        runtime_source, repository_root, environ):
    """Publish routing only; workers must independently pin/authenticate sources.

    No body download, SDK staging, signature admission or product trust occurs.
    Use only after caller-owned current selection; missing source uses the full
    capture path. A binding must always name an original body, never a binding.
    """
    from products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes
    from runtime_reference_transport import SDK_INPUT_REFERENCE_NAME, validate_sdk_input_binding
    plan_path, destination = Path(plan_path).absolute(), Path(destination).absolute()
    root = Path(repository_root).resolve(strict=True)
    _require_capability_output_separate(destination, [root, plan_path])
    if destination.exists() or destination.is_symlink():
        raise ValueError('SDK input binding requires a fresh destination')
    raw = read_regular_file_bytes(plan_path, max_bytes=16*1024*1024, reject_symlink_parents=True)
    plan = product_reuse._validate_plan(plan_path, root)
    current = product_reuse.validate_producer(product_reuse._consumer(plan, environ)['producer'])
    if plan['remoteBuildAuthorized'] is not True or plan['event'] == 'workflow_dispatch':
        raise ValueError('SDK input binding requires an authorized PR or merge-group plan')
    value = validate_sdk_input_binding(load_canonical_json_bytes(canonical_json_bytes(dict(
        schemaVersion=1, source=sdk_inputs_source, runtimeSource=runtime_source, planSha256=sha256_bytes(raw)))))
    for source in (value['source'], value['runtimeSource']):
        prior = source['producer']
        if (any(prior[key] != current[key] for key in ('repository', 'event', 'pullRequest'))
                or (prior['runId'], prior['runAttempt']) >= (current['runId'], current['runAttempt'])):
            raise ValueError('SDK binding requires earlier original sources for this selection')
    with tempfile.TemporaryDirectory(prefix='sdk-input-binding-') as temporary:
        prepared = Path(temporary).resolve() / 'binding'
        (prepared / 'runtime-capture/plan').mkdir(parents=True)
        (prepared / 'runtime-capture/plan/impact-plan.json').write_bytes(raw)
        (prepared / SDK_INPUT_REFERENCE_NAME).write_bytes(canonical_json_bytes(value))
        inventory = regular_file_inventory(prepared)
        if read_regular_file_bytes(plan_path, reject_symlink_parents=True) != raw:
            raise ValueError('SDK binding plan changed before publication')
        publish_regular_tree(prepared, destination, expected_inventory=inventory)
    return value


def _ensure_observed_sdk_commit(repository, producer, token):
    """Fetch only a freshly authenticated immutable producer; leave refs/HEAD alone."""
    import base64
    import subprocess
    command = ['git', '--no-replace-objects', '-C', str(repository)]
    commit = producer['commit']
    present = subprocess.run([*command, 'cat-file', '-e', commit + '^{commit}'],
                             capture_output=True, timeout=30)
    if present.returncode == 0:
        return
    # Credentials live in this child environment, never command text or config.
    environment = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_CONFIG_COUNT': '1',
        'GIT_CONFIG_KEY_0': 'http.https://github.com/.extraheader',
        'GIT_CONFIG_VALUE_0': 'Authorization: Basic ' + base64.b64encode(
            ('x-access-token:' + token).encode()).decode()}
    try:
        subprocess.run([*command, 'fetch', '--no-tags', '--no-write-fetch-head',
            'https://github.com/' + producer['repository'] + '.git', commit],
            env=environment, check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError:
        raise ValueError('Cannot fetch the authenticated original SDK commit') from None


@verification_scoped
@measured
def capture_reused_sdk_handoff(plan_path, destination, *, sdk_inputs_source,
        artifact_id, artifact_sha256, trusted_workflow_sha, expected_build_key,
        expected_metadata_receipt_sha256, sdk_version, compatible_release_range,
        compatible_runtime_compatibility_range, keyring, keys_directory,
        selection_repository_root, selection_revision, repository_root, environ,
        token, expected_contract_payload_sha256, original_producer=None,
        reference_runtime=True):
    """Reuse an original SDK bundle without expanding its Runtime history.

    Both native source observations and the complete SDK archive are verified.
    The existing full signed SDK reader rechecks current policy/content. The
    new envelope binds the current plan separately; original evidence is kept.
    Consumers retain their full Runtime and product-admission gates.
    """
    import hashlib
    import zipfile
    from products.inventory import (
        canonical_json_bytes, load_canonical_json_bytes, require_exact_keys,
        require_integer, sha256_bytes, sha256_file, verified_zip_contents,
        write_canonical_json,
    )
    from products.sdk_inputs_verification import verified_sdk_inputs
    from runtime_reference_transport import (
        SDK_REFERENCE_NAME, sdk_runtime_reference_inventory, validate_sdk_runtime_reference,
    )

    if reference_runtime is not True or not isinstance(token, str) or not token:
        raise ValueError('Retained SDK inputs require reference transport and an observation token')
    source = require_exact_keys(load_canonical_json_bytes(canonical_json_bytes(sdk_inputs_source)),
        {'artifactId', 'artifactSha256', 'producer', 'workflowSha'}, 'Retained SDK input source')
    require_integer(source['artifactId'], 'Retained SDK artifact ID', 1)
    require_sha256(source['artifactSha256'], 'Retained SDK artifact SHA-256')
    import re
    if type(source['workflowSha']) is not str or re.fullmatch('[0-9a-f]{40}', source['workflowSha']) is None:
        raise ValueError('Retained SDK workflow pin must be immutable')
    if original_producer is not None:
        original_producer = load_canonical_json_bytes(canonical_json_bytes(original_producer))
    producer = product_reuse.validate_producer(source['producer'])
    repository, selection = Path(repository_root).resolve(strict=True), Path(selection_repository_root).absolute()
    plan_path, destination = Path(plan_path).absolute(), Path(destination).absolute()
    originals = [repository, selection, plan_path, Path(keyring), Path(keys_directory)]

    def output_safe():
        _require_capability_output_separate(destination, originals)
        for path in (destination, *destination.parents):
            if path.is_symlink():
                raise ValueError('Retained SDK destination has symbolic ancestry')
            if path.exists():
                require_regular_directory(path, 'Retained SDK destination ancestry')
        if destination.exists():
            raise ValueError('Retained SDK destination must not exist')

    output_safe()
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16*1024*1024, reject_symlink_parents=True)
    plan = product_reuse._validate_plan(plan_path, repository)
    if plan['remoteBuildAuthorized'] is not True or plan['event'] == 'workflow_dispatch':
        raise ValueError('Retained SDK inputs require an authorized PR or merge-group plan')
    current = product_reuse.validate_producer(product_reuse._consumer(plan, environ)['producer'])
    for prior in (producer, original_producer):
        if prior is None:
            continue
        prior = product_reuse.validate_producer(prior)
        if (any(prior[k] != current[k] for k in ('repository', 'event', 'pullRequest'))
                or (prior['runId'], prior['runAttempt']) >= (current['runId'], current['runAttempt'])):
            raise ValueError('Retained SDK/Runtime source must be an earlier producer for this selection')
    if (selection_revision != plan['validationCommit']
            or read_sdk_release_selection(selection, selection_revision)['sdkVersion'] != sdk_version):
        raise ValueError('Retained SDK selection differs from current plan/version')
    require_sdk_runtime_compatibility_policy(selection, selection_revision,
        compatible_release_range=compatible_release_range,
        compatible_runtime_compatibility_range=compatible_runtime_compatibility_range)
    require_sha256(expected_contract_payload_sha256, 'Selected Contract payload')
    runtime_producer = current if original_producer is None else original_producer
    runtime_source = dict(artifactId=artifact_id, artifactSha256=artifact_sha256,
        producer=runtime_producer, workflowSha=trusted_workflow_sha, buildKey=expected_build_key,
        metadataReceiptSha256=expected_metadata_receipt_sha256)
    with tempfile.TemporaryDirectory(prefix='reused-sdk-handoff-') as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, originals)
        policy = private / 'policy'
        policy_paths, policy_bytes = _public_policy(keyring, keys_directory, policy)
        policy_inventory = regular_file_inventory(policy)
        job = 'product-validation / sdk-inputs'
        observed = product_reuse._observe_ci_producer_jobs({'sdk-inputs': producer},
            jobs_by_phase={'sdk-inputs': job}, trusted_workflow_sha=source['workflowSha'], token=token)
        _ensure_observed_sdk_commit(repository, producer, token)
        name = f"codex-agent-sdk-inputs-{producer['tree']}-attempt-{producer['runAttempt']}"
        archive = private / 'original-sdk.zip'
        sdk_artifact, _ = product_reuse._download_contract_ci_upload(source['artifactId'],
            source['artifactSha256'], name, producer, observed[0]['run'], token, destination=archive)
        product_reuse._require_artifact_job_window(observed[0], job, sdk_artifact)
        controls = ('runtime-capture/plan/impact-plan.json', 'runtime-capture/capture-transport.json')
        physical, retained, archive_identity = verified_zip_contents(archive,
            retained_paths=controls, max_retained_bytes=16*1024*1024,
            allow_empty_members=True, **product_reuse._CATALOG_ZIP_LIMITS)
        if archive_identity != {'bytes': sdk_artifact['size_in_bytes'], 'sha256': source['artifactSha256']}:
            raise ValueError('Retained SDK archive differs from native source identity')
        if set(retained) != set(controls):
            raise ValueError('Retained SDK source is not a complete current-Runtime input upload')
        original_plan = private / 'original-plan.json'
        original_plan.write_bytes(retained[controls[0]])
        selected = product_reuse._validate_plan(original_plan, repository, expected_revision=producer['commit'])
        if (selected['remoteBuildAuthorized'] is not True or selected['event'] == 'workflow_dispatch'
                or product_reuse._consumer(selected, environ, original_run_id=producer['runId'],
                    original_run_attempt=producer['runAttempt'])['producer'] != producer):
            raise ValueError('Retained SDK original plan differs from its authenticated producer')
        reference = sdk_runtime_reference_inventory(archive, physical)
        logical = physical if reference is None else reference['inventory']
        transport = load_canonical_json_bytes(retained[controls[1]])
        if (transport['artifact']['id'] != artifact_id or transport['artifact']['digest'] != artifact_sha256
                or transport['captureProducer'] != runtime_producer
                or transport['aggregateBuildKey'] != expected_build_key
                or transport['aggregateReceiptSha256'] != expected_metadata_receipt_sha256
                or reference is not None and reference['source'] != runtime_source):
            raise ValueError('Retained SDK Runtime origin differs from current selected original')
        if {row['relativePath'].split('/')[0] for row in logical} != {'runtime-capture', 'sdk-inputs'}:
            raise ValueError('Retained SDK source has an unsupported layout')
        runtime_job = 'product-validation / runtime-aggregate-attestation'
        runtime_observed = product_reuse._observe_ci_producer_jobs({'aggregate': runtime_producer},
            jobs_by_phase={'aggregate': runtime_job}, trusted_workflow_sha=trusted_workflow_sha, token=token)
        runtime_name = (f"codex-agent-runtime-aggregate-release-handoff-{runtime_producer['tree']}"
                        f"-attempt-{runtime_producer['runAttempt']}")
        runtime_artifact = product_reuse._contract_ci_upload_metadata(artifact_id, artifact_sha256,
            runtime_name, runtime_producer, runtime_observed[0]['run'], token)
        product_reuse._require_artifact_job_window(runtime_observed[0], runtime_job, runtime_artifact)
        sdk_rows = [row for row in physical if row['relativePath'].startswith('sdk-inputs/')]
        captured = private / 'capture'
        # Full ZIP path/type/size/CRC checks completed above. Only SDK bytes are
        # extracted; every streamed member must still match its verified hash.
        with zipfile.ZipFile(archive) as zipped:
            for row in sdk_rows:
                target = captured / row['relativePath']
                target.parent.mkdir(parents=True, exist_ok=True)
                count, digest = 0, hashlib.sha256()
                with zipped.open(row['relativePath']) as incoming, target.open('xb') as output:
                    while chunk := incoming.read(1024*1024):
                        count += len(chunk)
                        if count > row['bytes']:
                            raise ValueError('Retained SDK member exceeds its authenticated size')
                        digest.update(chunk)
                        output.write(chunk)
                if count != row['bytes'] or 'sha256:' + digest.hexdigest() != row['sha256']:
                    raise ValueError('Retained SDK member differs from its authenticated bytes')
        prepared = private / 'prepared'
        with verified_sdk_inputs(captured / 'sdk-inputs', keyring=policy / 'product-signing-keys.json',
                keys_directory=policy / 'keys',
                selection_repository_root=selection, selection_revision=selection_revision,
                expected_contract_payload_sha256=expected_contract_payload_sha256) as verified:
            metadata = read_regular_file_bytes(verified['arguments']['runtime_metadata_receipt'])
            if (sha256_bytes(metadata) != expected_metadata_receipt_sha256
                    or load_canonical_json_bytes(metadata)['buildKey'] != expected_build_key):
                raise ValueError('Retained SDK signed Runtime receipt differs from current selection')
            snapshot_regular_tree(verified['directory'], prepared / 'sdk-inputs')
            sdk_inventory_bytes = read_regular_file_bytes(verified['directory'] / 'sdk-inputs-inventory.json',
                max_bytes=16*1024*1024, reject_symlink_parents=True)
        capture = prepared / 'runtime-capture'
        (capture / 'plan').mkdir(parents=True)
        (capture / 'plan/impact-plan.json').write_bytes(plan_bytes)
        write_canonical_json(capture / 'capture-transport.json', dict(artifact=runtime_artifact,
            captureProducer=runtime_producer, observed=runtime_observed,
            aggregateBuildKey=expected_build_key, aggregateReceiptSha256=expected_metadata_receipt_sha256))
        origin = capture / 'sdk-input-origin'
        origin.mkdir()
        (origin / 'impact-plan.json').write_bytes(retained[controls[0]])
        write_canonical_json(origin / 'capture-transport.json', dict(artifact=sdk_artifact,
            captureProducer=producer, observed=observed, trustedWorkflowSha=source['workflowSha']))
        (origin / 'runtime-capture-transport.json').write_bytes(retained[controls[1]])
        inventory = regular_file_inventory(prepared)
        runtime_inventory = [row for row in logical if row['relativePath'].startswith('runtime-capture/original/')]
        value = validate_sdk_runtime_reference(dict(schemaVersion=1, source=runtime_source,
            inventory=sorted([*inventory, *runtime_inventory], key=lambda row: row['relativePath'])))
        write_canonical_json(prepared / SDK_REFERENCE_NAME, value)
        if (read_regular_file_bytes(plan_path, reject_symlink_parents=True) != plan_bytes
                or sha256_file(archive, reject_symlink_parents=True) != source['artifactSha256']
                or regular_file_inventory(policy) != policy_inventory
                or any(read_regular_file_bytes(path, max_bytes=64*1024, reject_symlink_parents=True)
                       != policy_bytes[name] for name, path in policy_paths.items())):
            raise ValueError('Retained SDK original source or current plan changed before publication')
        output_safe()
        publish_regular_tree(prepared, destination, expected_inventory=sorted([
            *inventory, dict(relativePath=SDK_REFERENCE_NAME, bytes=len(canonical_json_bytes(value)),
                            sha256=sha256_bytes(canonical_json_bytes(value)))], key=lambda row: row['relativePath']))
    return dict(inventorySha256=sha256_bytes(sdk_inventory_bytes),
                inventory=load_canonical_json_bytes(sdk_inventory_bytes))


@verification_scoped
@measured
def capture_sdk_handoff(
    plan_path: Path, destination: Path, *, artifact_id: int, artifact_sha256: str,
    trusted_workflow_sha: str, expected_build_key: str, expected_metadata_receipt_sha256: str,
    sdk_version: str, compatible_release_range: str, compatible_runtime_compatibility_range: str,
    keyring: Path, keys_directory: Path, selection_repository_root: Path, selection_revision: str,
    repository_root: Path | None = None, environ=None, token: str,
    expected_contract_payload_sha256: str | None = None,
    original_producer=None, reference_runtime=False,
) -> dict:
    """Publish original upload evidence and SDK inputs only after both gates exit."""
    if expected_contract_payload_sha256 is not None:
        require_sha256(expected_contract_payload_sha256, "Expected Contract payload SHA-256")
    if type(reference_runtime) is not bool:
        raise ValueError('SDK Runtime reference selection must be boolean')
    repository = (Path(__file__).resolve().parents[1] if repository_root is None else Path(repository_root)).resolve(strict=True)
    selection = Path(selection_repository_root).absolute()
    plan, destination = Path(plan_path).absolute(), Path(destination).absolute()
    originals = [repository, selection, plan, Path(keyring), Path(keys_directory)]

    def output_safe():
        _require_capability_output_separate(destination, originals)
        for path in (destination, *destination.parents):
            if path.is_symlink():
                raise ValueError("SDK handoff output has symbolic ancestry")
            if path.exists():
                require_regular_directory(path, "SDK handoff output ancestry")
        if destination.exists():
            raise ValueError("SDK handoff destination must not exist")

    output_safe()
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    selected_policy = read_sdk_release_selection(selection, selection_revision)
    selected_ranges = require_sdk_runtime_compatibility_policy(selection, selection_revision,
        compatible_release_range=compatible_release_range,
        compatible_runtime_compatibility_range=compatible_runtime_compatibility_range)
    environment = dict(os.environ if environ is None else environ)
    with tempfile.TemporaryDirectory(prefix="sdk-handoff-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, originals)
        policy = private / "policy"
        paths, policy_bytes = _public_policy(keyring, keys_directory, policy)
        policy_inventory = regular_file_inventory(policy)
        prepared = private / "output"
        capture = private / "runtime-capture"
        product_reuse.capture_runtime_aggregate_release_upload(plan, capture,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            expected_build_key=expected_build_key, expected_metadata_receipt_sha256=expected_metadata_receipt_sha256,
            repository_root=repository, environ=environment, token=token,
            **({"original_producer": original_producer} if original_producer is not None else {}))
        if read_regular_file_bytes(capture / "plan/impact-plan.json", reject_symlink_parents=True) != plan_bytes:
            raise ValueError("Captured SDK handoff plan differs from its original bytes")
        capture_inventory = regular_file_inventory(capture, allow_empty=True)
        forwarded = private / "forwarded"
        result = stage_protected_runtime_sdk_inputs(capture / "original", forwarded,
            retain_runtime=False,
            expected_metadata_receipt_sha256=expected_metadata_receipt_sha256, expected_build_key=expected_build_key,
            sdk_version=sdk_version, compatible_release_range=compatible_release_range,
            compatible_runtime_compatibility_range=compatible_runtime_compatibility_range,
            keyring=policy / "product-signing-keys.json", keys_directory=policy / "keys",
            selection_repository_root=selection, selection_revision=selection_revision,
            **({"expected_contract_payload_sha256": expected_contract_payload_sha256}
               if expected_contract_payload_sha256 is not None else {}))
        # SDK consumers authenticate their own complete SDK upload and verify
        # the raw signed Runtime carrier. They never use its enclosing ZIP.
        for name in (("plan",) if reference_runtime else ("plan", "original")):
            snapshot_regular_tree(capture / name, prepared / "runtime-capture" / name, allow_empty=True)
        transport_bytes = read_regular_file_bytes(capture / "capture-transport.json", reject_symlink_parents=True)
        (prepared / "runtime-capture/capture-transport.json").write_bytes(transport_bytes)
        sdk_inventory = regular_file_inventory(forwarded / "sdk-inputs")
        snapshot_regular_tree(forwarded / "sdk-inputs", prepared / "sdk-inputs")
        logical_capture = [record for record in capture_inventory if record['relativePath'] != 'transport.zip']
        if reference_runtime:
            from runtime_reference_transport import SDK_REFERENCE_NAME, validate_sdk_runtime_reference
            from products.inventory import load_canonical_json_bytes, write_canonical_json
            transport = load_canonical_json_bytes(transport_bytes)
            if (transport['artifact']['id'] != artifact_id or transport['artifact']['digest'] != artifact_sha256
                    or transport['aggregateBuildKey'] != expected_build_key
                    or transport['aggregateReceiptSha256'] != expected_metadata_receipt_sha256):
                raise ValueError('SDK Runtime reference differs from its authenticated capture')
            value = validate_sdk_runtime_reference(dict(schemaVersion=1,
                source=dict(artifactId=artifact_id, artifactSha256=artifact_sha256,
                    producer=transport['captureProducer'], workflowSha=trusted_workflow_sha,
                    buildKey=expected_build_key, metadataReceiptSha256=expected_metadata_receipt_sha256),
                inventory=sorted([
                    *({**row, 'relativePath': 'runtime-capture/' + row['relativePath']} for row in logical_capture),
                    *({**row, 'relativePath': 'sdk-inputs/' + row['relativePath']} for row in sdk_inventory),
                ], key=lambda row: row['relativePath'])))
            write_canonical_json(prepared / SDK_REFERENCE_NAME, value)
        if (regular_file_inventory(capture, allow_empty=True) != capture_inventory
                or regular_file_inventory(prepared / "runtime-capture", allow_empty=True)
                   != [record for record in logical_capture
                       if not reference_runtime or not record['relativePath'].startswith('original/')]
                or regular_file_inventory(forwarded / "sdk-inputs") != sdk_inventory
                or regular_file_inventory(prepared / "sdk-inputs") != sdk_inventory
                or read_regular_file_bytes(plan, reject_symlink_parents=True) != plan_bytes
                or read_sdk_release_selection(selection, selection_revision) != selected_policy
                or require_sdk_runtime_compatibility_policy(selection, selection_revision,
                    compatible_release_range=compatible_release_range,
                    compatible_runtime_compatibility_range=compatible_runtime_compatibility_range) != selected_ranges
                or regular_file_inventory(policy) != policy_inventory
                or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True)
                       != policy_bytes[name] for name, path in paths.items())):
            raise ValueError("SDK handoff inputs or caller policy changed before publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True)
    return result


def main_released_default(argv=None):
    parser = argparse.ArgumentParser(description="Stage SDK inputs from the authenticated released-default replay.")
    for name in ("plan", "discovery-root", "destination", "keyring", "keys-directory", "repository-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--sdk-validation-tooling", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    parser.add_argument("--trusted-workflow-sha")
    arguments = parser.parse_args(argv)
    try:
        tooling = None if arguments.sdk_validation_tooling is None else product_reuse._canonical_control(
            arguments.sdk_validation_tooling, "Caller SDK tooling policy")
        apple = {} if arguments.sdk_apple_validation_policy is None else {
            "sdk_apple_validation_policy": product_reuse._canonical_control(
                arguments.sdk_apple_validation_policy, "Caller Apple validation policy")}
        product_reuse.materialize_sdk_default_inputs(arguments.plan, arguments.discovery_root,
            arguments.state_root, arguments.destination, keyring=arguments.keyring,
            keys_directory=arguments.keys_directory, repository_root=arguments.repository_root,
            environ=os.environ, sdk_validation_tooling=tooling,
            **({"sdk_original_workflow_sha": arguments.trusted_workflow_sha}
               if arguments.trusted_workflow_sha is not None else {}), **apple)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "released-default":
        return main_released_default(argv[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "destination", "repository-root", "selection-repository-root", "keyring", "keys-directory"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    for name in ("artifact-sha256", "trusted-workflow-sha", "expected-build-key", "expected-metadata-receipt-sha256",
                 "sdk-version", "compatible-release-range", "compatible-runtime-compatibility-range", "selection-revision"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--expected-contract-payload-sha256", default=argparse.SUPPRESS,
                        type=lambda value: require_sha256(value, "Expected Contract payload SHA-256"))
    arguments = vars(parser.parse_args(argv))
    plan, destination = arguments.pop("plan"), arguments.pop("destination")
    try:
        capture_sdk_handoff(plan, destination, **arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
