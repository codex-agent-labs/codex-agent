"""Non-secret Runtime original-input preparation, never signing authorization.

Run from independently pinned source. Workflow approval and the subsequent
original-source/full semantic/signature gates remain consumer-owned.
"""

from collections.abc import Mapping
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from product_release_context import verify_product_release_context
from product_reuse import (
    _release_trust, capture_runtime_resume_upload, materialize_runtime_attestation_inputs,
    materialize_runtime_aggregate_release_evidence,
)
from runtime_aggregate_release import _destination
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_relative_path, require_sha256, require_string, sha256_bytes,
    snapshot_regular_tree,
    write_canonical_json,
)
from products.registry import NATIVE_TARGETS
from products.restore import memoized_file_inventory as regular_file_inventory, verification_scoped
from products.signing_isolation import require_no_signing_secret
from products.sdk_apple_validation_admission import apple_validation_policy_arguments


_AGGREGATE_IDENTITY = {"product": "runtime", "component": "runtime-aggregate", "phase": "metadata", "target": "aggregate"}
SCRATCH_ENVIRONMENT = "CODEX_AGENT_PREPARATION_SCRATCH"
_GIB = 1024 ** 3
_RESERVE = 2 * _GIB
# Measured copies of one carrier of N bytes (stored zip, compression level 0):
# capture holds transport.zip + extraction and publishes both (4N), then signature
# staging snapshots the extraction while the capture still exists (<= 2N more).
_SCRATCH_CARRIERS = 6
# The verified carrier is staged once beside the selection; the prepared copy
# lives on the scratch volume and the staged source is removed once copied.
_OUTPUT_CARRIERS = 1


def preparation_scratch(environment: Mapping[str, str]) -> Path:
    """The caller-provisioned large volume when present, else the default temporary root."""
    candidates = [Path(tempfile.gettempdir())]
    provided = environment.get(SCRATCH_ENVIRONMENT, "")
    if provided:
        path = Path(provided)
        if not path.is_absolute() or path.is_symlink() or not path.is_dir():
            raise ValueError(f"{SCRATCH_ENVIRONMENT} must be an existing absolute directory")
        candidates.insert(0, path)
    return max(candidates, key=lambda path: shutil.disk_usage(path).free)


@contextmanager
def _temporary_root(path: Path):
    """Route nested private temporaries (capture, staging) onto the scratch volume."""
    previous = tempfile.tempdir
    tempfile.tempdir = str(path)
    try:
        yield
    finally:
        tempfile.tempdir = previous


def recover_original_aggregate_release(plan_path: Path, selected: Path, selection: Mapping[str, Any],
                                       destination: Path, *, keyring: Path, keys_directory: Path,
                                       repository_root: Path, environment: Mapping[str, str],
                                       trusted_workflow_sha: str, token: str,
                                       scratch: Path | None = None, completed_frozen=None) -> Path | None:
    """Forward the exact earlier signed carrier of a retained aggregate, never a new signature.

    Completed-frozen discovery restores retained aggregate metadata without
    rehydrating its release carrier. Ordinary mode then has neither native
    variant handoffs nor a retained carrier. The selected receipt names the
    original producer; that run's protected upload is captured with its
    original CI/job/name/digest gates and staged through the full signature
    check. The signer later re-verifies the carrier against selected originals.
    A completed-frozen caller passes its native capability: the capture gate
    then admits the owner-pinned (T4c) PR-31 producer of the exact selected
    receipt for the consumer scope that capability admits.
    """
    from product_reuse import (
        _runtime_prior_workflow_sha, api_json, capture_runtime_aggregate_release_upload, paginated_items,
    )
    from products.receipt import validate_producer
    from products.runtime_aggregate_inputs import stage_runtime_aggregate_release_evidence

    metadata = selection.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("Aggregate selection lacks its selected metadata")
    key = require_sha256(metadata.get("buildKey"), "Selected aggregate key")
    digest = require_sha256(metadata.get("receiptSha256"), "Selected aggregate receipt")
    receipt_path = Path(selected) / require_relative_path(
        require_string(selection.get("aggregateReceipt"), "Selected aggregate receipt path"),
        "Selected aggregate receipt path")
    receipt_bytes = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    if sha256_bytes(receipt_bytes) != digest:
        raise ValueError("Selected aggregate receipt differs from its selected digest")
    receipt = load_canonical_json_bytes(receipt_bytes)
    if (any(receipt.get(field) != value for field, value in _AGGREGATE_IDENTITY.items())
            or receipt.get("buildKey") != key):
        raise ValueError("Selected aggregate receipt changes its phase identity")
    original = validate_producer(receipt.get("producer"))
    current = validate_producer(selection.get("producer"))
    if (original["runId"], original["runAttempt"]) >= (current["runId"], current["runAttempt"]):
        return None  # A current aggregate is attested from fresh native variant handoffs.
    run = api_json(f"https://api.github.com/repos/{original['repository']}/actions/runs/"
                   f"{original['runId']}/attempts/{original['runAttempt']}", token)
    workflow = _runtime_prior_workflow_sha(run, trusted_workflow_sha)
    if workflow is None:
        raise ValueError("Retained aggregate source lacks its reviewed original workflow")
    name = f"codex-agent-runtime-aggregate-release-handoff-{original['tree']}-attempt-{original['runAttempt']}"
    uploads = paginated_items(f"https://api.github.com/repos/{original['repository']}/actions/runs/"
                              f"{original['runId']}/artifacts", "artifacts", token)
    matches = [item for item in uploads if isinstance(item, Mapping) and item.get("name") == name]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("Retained aggregate release upload is ambiguous")
    size = matches[0].get("size_in_bytes")
    if type(size) is not int or size <= 0:
        raise ValueError("Retained aggregate release upload lacks its transport size")
    from runtime_reference_transport import require_volume_headroom
    scratch = preparation_scratch(environment) if scratch is None else Path(scratch)
    staged = Path(destination)
    # Fail before downloading when either volume cannot hold the measured copies.
    require_volume_headroom(scratch, _SCRATCH_CARRIERS * size + _RESERVE,
                            stage="runtime-aggregate-release-recovery-scratch")
    require_volume_headroom(staged.parent, _OUTPUT_CARRIERS * size + _RESERVE,
                            stage="runtime-aggregate-release-recovery-output")
    # Capture outside the candidate checkout; only the signature-verified carrier is staged back.
    with tempfile.TemporaryDirectory(prefix="runtime-retained-aggregate-", dir=scratch) as temporary, \
            _temporary_root(Path(temporary).resolve()):
        capture = Path(temporary).resolve() / "capture"
        capture_runtime_aggregate_release_upload(plan_path, capture, artifact_id=matches[0].get("id"),
            artifact_sha256=matches[0].get("digest"), trusted_workflow_sha=workflow,
            expected_build_key=key, expected_metadata_receipt_sha256=digest, original_producer=original,
            repository_root=repository_root, environ=environment, token=token,
            **({} if completed_frozen is None else {"completed_frozen": completed_frozen,
                                                    "original_receipt": receipt}))
        records = stage_runtime_aggregate_release_evidence(
            [{"receiptSha256": digest, "handoffRoot": "original"}],
            capture, staged, keyring=keyring, keys_directory=keys_directory)
    if len(records) != 1 or records[0]["receiptSha256"] != digest:
        raise ValueError("Retained aggregate release staging changed its selected receipt")
    return staged / records[0]["handoffRoot"]


@verification_scoped
def prepare_runtime_signing_inputs(
    repository_root: Path, candidate_root: Path, plan_path: Path, destination: Path, *,
    target: str, expected_build_key: str, artifact_id: int, artifact_sha256: str,
    state_wave: int, trusted_source_sha: str, trusted_workflow_sha: str,
    transport_producer: Mapping[str, Any], event_payload: dict[str, Any],
    environment: Mapping[str, str], token: str,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    completed_frozen=None,
) -> dict[str, Any]:
    """Capture/elect originals without access to the product signing secret.

    The external preparation record binds exact bytes, not new product evidence.
    Native retained handoffs keep the existing selection-relative layout; an
    available aggregate carrier is forwarded directly under release-handoff/.
    """
    require_no_signing_secret(environment)
    if target not in (*NATIVE_TARGETS, "aggregate"):
        raise ValueError("Runtime signing preparation requires a native or aggregate target")
    require_sha256(expected_build_key, "Runtime preparation selected key")
    require_sha256(artifact_sha256, "Runtime preparation state artifact digest")
    if type(artifact_id) is not int or artifact_id <= 0 or type(state_wave) is not int or not 0 <= state_wave <= 5:
        raise ValueError("Runtime preparation requires an exact state artifact and wave")
    if type(token) is not str or not token:
        raise ValueError("Runtime preparation requires an observation token")
    tooling_paths = ()
    if sdk_validation_tooling is not None:
        path_names = ("evidence", "publicKey", "javaExecutable", "keyring", "keysDirectory")
        require_exact_keys(sdk_validation_tooling, (*path_names, "requiredTrustDomain"), "Caller SDK tooling policy")
        if sdk_validation_tooling["requiredTrustDomain"] != "release":
            raise ValueError("Runtime signing preparation requires release tooling trust")
        tooling_paths = tuple(Path(require_string(sdk_validation_tooling[name], f"Caller SDK tooling {name}"))
                             for name in path_names)
        if any(not path.is_absolute() for path in tooling_paths):
            raise ValueError("Caller SDK tooling paths must be absolute")
    apple_paths, apple_bytes = (), None
    if sdk_apple_validation_policy is not None:
        apple_arguments = apple_validation_policy_arguments(sdk_apple_validation_policy)
        if apple_arguments["required_trust_domain"] != "release":
            raise ValueError("Runtime signing preparation requires release Apple tooling trust")
        apple_paths = tuple(value for value in apple_arguments.values() if isinstance(value, Path))
        apple_bytes = canonical_json_bytes(sdk_apple_validation_policy)
    trusted, producer, _, _, _ = verify_product_release_context(
        repository_root, trusted_source_sha=trusted_source_sha, trusted_workflow_sha=trusted_workflow_sha,
        transport_producer=transport_producer, event_payload=event_payload, environment=environment)
    candidate = Path(candidate_root).resolve(strict=True)
    if trusted == candidate or trusted in candidate.parents or candidate in trusted.parents:
        raise ValueError("Runtime preparation requires separate trusted and candidate checkouts")
    protected = (trusted, candidate, Path(plan_path), *tooling_paths, *apple_paths)
    output = _destination(destination, protected)
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    tooling = {"sdk_validation_tooling": sdk_validation_tooling} if sdk_validation_tooling is not None else {}
    tooling["sdk_original_workflow_sha"] = trusted_workflow_sha
    semantic = {} if completed_frozen is None else {"completed_frozen": completed_frozen}
    tooling.update(semantic)
    if apple_bytes is not None:
        tooling["sdk_apple_validation_policy"] = load_canonical_json_bytes(apple_bytes)
    with tempfile.TemporaryDirectory(prefix="runtime-signing-inputs-", dir=candidate) as temporary:
        root = Path(temporary).resolve()
        capture = root / "capture"
        capture_runtime_resume_upload(plan_path, capture, artifact_id=artifact_id,
            artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            state_wave=state_wave, repository_root=candidate, environ=environment, token=token, **semantic)
        baselines = {capture: regular_file_inventory(capture, allow_empty=True)}

        def unchanged():
            require_no_signing_secret(environment)
            if apple_bytes is not None and (
                    canonical_json_bytes(sdk_apple_validation_policy) != apple_bytes
                    or canonical_json_bytes(tooling["sdk_apple_validation_policy"]) != apple_bytes):
                raise ValueError("Runtime preparation caller Apple policy changed during use")
            if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != plan_bytes
                    or any(regular_file_inventory(path, allow_empty=True) != inventory
                           for path, inventory in baselines.items())):
                raise ValueError("Runtime signing preparation originals changed during use")

        original = capture / "original"
        captured_plan = original / "product-resume-inputs/plan/impact-plan.json"
        if read_regular_file_bytes(captured_plan, max_bytes=16 * 1024 * 1024,
                reject_symlink_parents=True) != plan_bytes:
            raise ValueError("Runtime preparation captured plan differs from its caller original")
        discovery = original / "product-resume-state"
        state = original / ("runtime-state" if state_wave else "product-resume-state")
        trust = _release_trust(trusted, trusted_source_sha, root / "policy")
        if trust is None:
            raise ValueError("Runtime signing preparation requires pinned release verification policy")
        baselines[root / "policy"] = regular_file_inventory(root / "policy", allow_empty=True)
        unchanged()
        selected = root / "selected-inputs"
        selection = materialize_runtime_attestation_inputs(captured_plan, discovery, state, selected,
            target=target, expected_build_key=expected_build_key, repository_root=candidate,
            environ=environment, **tooling, **({} if target == "aggregate" else {
                "retained_release_keyring": trust.keyring, "retained_release_keys_directory": trust.keys}))
        unchanged()
        selection_bytes = read_regular_file_bytes(selected / "selection.json",
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
        if (load_canonical_json_bytes(selection_bytes) != selection or selection["producer"] != producer
                or selection["target"] != target or selection["metadata"]["buildKey"] != expected_build_key):
            raise ValueError("Runtime preparation selection differs from its exact caller identity")
        baselines[selected] = regular_file_inventory(selected, allow_empty=True)
        retained = recovered = None
        if target == "aggregate":
            retained = materialize_runtime_aggregate_release_evidence(captured_plan, discovery, state,
                root / "retained", expected_build_key=expected_build_key,
                keyring=trust.keyring, keys_directory=trust.keys,
                repository_root=candidate, environ=environment, **tooling)
            unchanged()
            if retained is None:
                retained = recovered = recover_original_aggregate_release(captured_plan, selected, selection,
                    root / "retained-original", keyring=trust.keyring, keys_directory=trust.keys,
                    repository_root=candidate, environment=environment,
                    trusted_workflow_sha=trusted_workflow_sha, token=token, **semantic)
                unchanged()
            if retained is not None:
                retained = Path(retained)
                retained.relative_to(root / ("retained" if recovered is None else "retained-original"))
                baselines[retained] = regular_file_inventory(retained, allow_empty=True)
        record = {"schemaVersion": 1, "target": target, "expectedBuildKey": expected_build_key,
            "stateWave": state_wave, "producer": producer, "planSha256": sha256_bytes(plan_bytes),
            "stateArtifact": {"artifactId": artifact_id, "artifactSha256": artifact_sha256},
            "selectionSha256": sha256_bytes(selection_bytes)}
        # A recovered carrier is large: prepare it on the scratch volume, not beside the selection.
        prepared_root = None if target != "aggregate" or recovered is None else preparation_scratch(environment)
        with tempfile.TemporaryDirectory(prefix="runtime-signing-prepared-", dir=prepared_root) as result_temporary:
            prepared = Path(result_temporary).resolve() / "prepared"
            copies = [(selected, "selected-inputs")]
            if retained is not None:
                copies.append((retained, "release-handoff"))
            copied = {}
            for source, name in copies:
                snapshot_regular_tree(source, prepared / name, allow_empty=True)
                if regular_file_inventory(prepared / name, allow_empty=True) != baselines[source]:
                    raise ValueError("Runtime signing preparation changed while copying original bytes")
                copied[name] = baselines[source]
                if target == "aggregate" and recovered is not None and source == retained:
                    # The verified copy is the only one still needed; free the staged bytes now.
                    del baselines[source]
                    shutil.rmtree(root / "retained-original")
            # The protected consumer independently captures this exact immutable
            # state already. Forward its qualified inventory, not another body.
            reference = {"schemaVersion": 1, "stateArtifact": record["stateArtifact"],
                "stateWave": state_wave, "producer": producer,
                "inventory": regular_file_inventory(original, allow_empty=True)}
            write_canonical_json(prepared / "selected-state-transport/reference.json", reference)
            reference_bytes = canonical_json_bytes(reference)
            write_canonical_json(prepared / "preparation.json", record)
            record_bytes = canonical_json_bytes(record)
            expected_files = sorted([
                *({**item, "relativePath": f"{name}/{item['relativePath']}"}
                  for name, inventory in copied.items() for item in inventory),
                {"relativePath": "selected-state-transport/reference.json", "bytes": len(reference_bytes),
                 "sha256": sha256_bytes(reference_bytes)},
                {"relativePath": "preparation.json", "bytes": len(record_bytes),
                 "sha256": sha256_bytes(record_bytes)},
            ], key=lambda item: item["relativePath"])
            unchanged()
            _destination(output, protected)
            if regular_file_inventory(prepared, allow_empty=True) != expected_files:
                raise ValueError("Runtime signing preparation differs from verified original inputs")
            publish_regular_tree(prepared, output, allow_empty=True, expected_inventory=expected_files)
    return record
