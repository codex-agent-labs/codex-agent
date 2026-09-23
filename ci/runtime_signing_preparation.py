"""Non-secret Runtime original-input preparation, never signing authorization.

Run from independently pinned source. Workflow approval and the subsequent
original-source/full semantic/signature gates remain consumer-owned.
"""

from collections.abc import Mapping
from pathlib import Path
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
    regular_file_inventory, require_exact_keys, require_sha256, require_string, sha256_bytes, snapshot_regular_tree,
    write_canonical_json,
)
from products.registry import NATIVE_TARGETS
from products.signing_isolation import require_no_signing_secret
from products.sdk_apple_validation_admission import apple_validation_policy_arguments


def prepare_runtime_signing_inputs(
    repository_root: Path, candidate_root: Path, plan_path: Path, destination: Path, *,
    target: str, expected_build_key: str, artifact_id: int, artifact_sha256: str,
    state_wave: int, trusted_source_sha: str, trusted_workflow_sha: str,
    transport_producer: Mapping[str, Any], event_payload: dict[str, Any],
    environment: Mapping[str, str], token: str,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
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
    if apple_bytes is not None:
        tooling["sdk_apple_validation_policy"] = load_canonical_json_bytes(apple_bytes)
    with tempfile.TemporaryDirectory(prefix="runtime-signing-inputs-", dir=candidate) as temporary:
        root = Path(temporary).resolve()
        capture = root / "capture"
        capture_runtime_resume_upload(plan_path, capture, artifact_id=artifact_id,
            artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            state_wave=state_wave, repository_root=candidate, environ=environment, token=token)
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
        retained = None
        if target == "aggregate":
            retained = materialize_runtime_aggregate_release_evidence(captured_plan, discovery, state,
                root / "retained", expected_build_key=expected_build_key,
                keyring=trust.keyring, keys_directory=trust.keys,
                repository_root=candidate, environ=environment, **tooling)
            unchanged()
            if retained is not None:
                retained = Path(retained)
                retained.relative_to(root / "retained")
                baselines[retained] = regular_file_inventory(retained, allow_empty=True)
        record = {"schemaVersion": 1, "target": target, "expectedBuildKey": expected_build_key,
            "stateWave": state_wave, "producer": producer, "planSha256": sha256_bytes(plan_bytes),
            "stateArtifact": {"artifactId": artifact_id, "artifactSha256": artifact_sha256},
            "selectionSha256": sha256_bytes(selection_bytes)}
        with tempfile.TemporaryDirectory(prefix="runtime-signing-prepared-") as result_temporary:
            prepared = Path(result_temporary).resolve() / "prepared"
            copies = [(selected, "selected-inputs"), (capture, "selected-state-transport")]
            if retained is not None:
                copies.append((retained, "release-handoff"))
            for source, name in copies:
                snapshot_regular_tree(source, prepared / name, allow_empty=True)
                if regular_file_inventory(prepared / name, allow_empty=True) != baselines[source]:
                    raise ValueError("Runtime signing preparation changed while copying original bytes")
            write_canonical_json(prepared / "preparation.json", record)
            unchanged()
            _destination(output, protected)
            publish_regular_tree(prepared, output, allow_empty=True)
    return record
