"""Protected signing of authenticated prepared originals, without SDK replay.

Execute this module from independently pinned source on a fresh runner. The
preparation upload authenticates the non-secret job's election; original carrier
binding and existing signing leaves retain the full content and trust gates.
"""

from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from product_release_context import verify_product_release_context
from product_reuse import _validate_plan, _consumer, capture_runtime_resume_upload
from runtime_preparation_capture import capture_runtime_signing_preparation
from runtime_prepared_state import restore_prepared_runtime_originals
from runtime_prepared_native import verify_native_prepared_selection
from runtime_prepared_aggregate import verify_aggregate_prepared_selection
from runtime_release import attest_runtime_variant_ci
from runtime_aggregate_release import _destination, _attest_selected_runtime_aggregate
from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_integer, require_sha256, publish_regular_tree,
    sha256_bytes,
    require_sorted_unique_records, validate_file_record,
)
from products.registry import NATIVE_TARGETS
from products.restore import memoized_file_inventory as regular_file_inventory, verification_scoped
from products.receipt import validate_producer


@verification_scoped
def attest_prepared_runtime_ci(
    repository_root, candidate_root, plan_path, destination, *, target,
    expected_build_key, artifact_id, artifact_sha256, state_wave,
    preparation_artifact_id, preparation_artifact_sha256,
    trusted_source_sha, trusted_workflow_sha, transport_producer,
    event_payload, environment, token, variant_handoffs=None,
):
    """Bind two exact uploads before invoking build-free signing-only leaves."""
    if target not in (*NATIVE_TARGETS, "aggregate"):
        raise ValueError("Prepared Runtime caller requires an exact target")
    for digest in (expected_build_key, artifact_sha256, preparation_artifact_sha256):
        require_sha256(digest, "Prepared Runtime caller digest")
    for identifier in (artifact_id, preparation_artifact_id):
        require_integer(identifier, "Prepared Runtime caller artifact ID", 1)
    if type(state_wave) is not int or not 0 <= state_wave <= 5:
        raise ValueError("Prepared Runtime caller requires state wave zero through five")
    if type(token) is not str or not token:
        raise ValueError("Prepared Runtime caller requires an observation token")
    handoffs = {} if variant_handoffs is None else dict(variant_handoffs)
    if target != "aggregate" and handoffs:
        raise ValueError("Native prepared signing does not accept variant overrides")
    trusted, producer, _, _, _ = verify_product_release_context(
        repository_root, trusted_source_sha=trusted_source_sha,
        trusted_workflow_sha=trusted_workflow_sha, transport_producer=transport_producer,
        event_payload=event_payload, environment=environment)
    candidate = Path(candidate_root).resolve(strict=True)
    if trusted == candidate or trusted in candidate.parents or candidate in trusted.parents:
        raise ValueError("Prepared signing requires separate trusted and candidate checkouts")
    protected = (trusted, candidate, Path(plan_path), *handoffs.values())
    output = _destination(destination, protected)
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="runtime-prepared-consumer-") as temporary, \
            tempfile.TemporaryDirectory(prefix="runtime-original-state-", dir=candidate) as state_temporary:
        private = Path(temporary).resolve()
        captured_plan = private / "impact-plan.json"
        captured_plan.write_bytes(plan_bytes)
        plan = _validate_plan(captured_plan, candidate)
        if (plan["remoteBuildAuthorized"] is not True
                or plan["event"] not in {"pull_request", "merge_group"}
                or _consumer(plan, environment)["producer"] != producer):
            raise ValueError("Prepared Runtime plan differs from protected caller context")
        prepared_capture = private / "preparation-capture"
        capture_runtime_signing_preparation(captured_plan, prepared_capture,
            target=target, artifact_id=preparation_artifact_id,
            artifact_sha256=preparation_artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            repository_root=candidate, environ=environment, token=token)
        original_capture = Path(state_temporary).resolve() / "state-capture"
        capture_runtime_resume_upload(captured_plan, original_capture,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256, state_wave=state_wave,
            trusted_workflow_sha=trusted_workflow_sha, repository_root=candidate,
            environ=environment, token=token)
        prepared = prepared_capture / "original"
        selected = prepared / "selected-inputs"
        selection_bytes = read_regular_file_bytes(selected / "selection.json",
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
        selection = load_canonical_json_bytes(selection_bytes)
        record = load_canonical_json_bytes(read_regular_file_bytes(prepared / "preparation.json",
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        expected = {"schemaVersion": 1, "target": target, "expectedBuildKey": expected_build_key,
            "stateWave": state_wave, "producer": producer, "planSha256": sha256_bytes(plan_bytes),
            "stateArtifact": {"artifactId": artifact_id, "artifactSha256": artifact_sha256},
            "selectionSha256": sha256_bytes(selection_bytes)}
        require_exact_keys(record, expected, "Runtime preparation record")
        require_exact_keys(record["stateArtifact"], expected["stateArtifact"], "Prepared original state")
        validate_producer(record["producer"], "Runtime preparation producer")
        if (type(record["schemaVersion"]) is not int or type(record["stateWave"]) is not int
                or type(record["stateArtifact"]["artifactId"]) is not int or record != expected):
            raise ValueError("Runtime preparation differs from exact caller-owned identities")
        original = original_capture / "original"
        state_transport = prepared / "selected-state-transport"
        if (state_transport / "reference.json").exists() or (state_transport / "reference.json").is_symlink():
            if {item.name for item in state_transport.iterdir()} != {"reference.json"}:
                raise ValueError("Prepared Runtime state reference has unexpected files")
            reference = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
                state_transport / "reference.json", max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)),
                {"schemaVersion", "stateArtifact", "stateWave", "producer", "inventory"}, "Prepared Runtime state reference")
            require_exact_keys(reference["stateArtifact"], expected["stateArtifact"], "Prepared referenced state artifact")
            require_integer(reference["stateArtifact"]["artifactId"], "Prepared referenced state artifact ID", 1)
            require_sha256(reference["stateArtifact"]["artifactSha256"], "Prepared referenced state artifact digest")
            validate_producer(reference["producer"], "Prepared referenced state producer")
            if (type(reference["schemaVersion"]) is not int or reference["schemaVersion"] != 1
                    or reference["stateArtifact"] != expected["stateArtifact"]
                    or type(reference["stateWave"]) is not int or reference["stateWave"] != state_wave
                    or reference["producer"] != producer):
                raise ValueError("Prepared Runtime state reference changes its original identity")
            prepared_inventory = require_sorted_unique_records(reference["inventory"], "Prepared Runtime state inventory")
            if len(prepared_inventory) > 16_384:
                raise ValueError("Prepared Runtime state inventory exceeds its fixed bound")
            for item in prepared_inventory:
                validate_file_record(item, "Prepared Runtime state file", with_kind=False, allow_empty=True)
        else:
            prepared_inventory = regular_file_inventory(state_transport / "original", allow_empty=True)
        if prepared_inventory != regular_file_inventory(original, allow_empty=True):
            raise ValueError("Prepared Runtime original state differs from independent capture")
        baselines = {path: regular_file_inventory(path, allow_empty=True)
                     for path in (prepared_capture, original_capture, *handoffs.values())}

        def unchanged():
            if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != plan_bytes
                    or read_regular_file_bytes(captured_plan) != plan_bytes
                    or any(regular_file_inventory(path, allow_empty=True) != inventory
                           for path, inventory in baselines.items())):
                raise ValueError("Prepared Runtime original inputs changed during protected use")

        originals_root = private / "authenticated-originals"
        originals = restore_prepared_runtime_originals(plan, original, originals_root,
            producer=producer, target=target, expected_build_key=expected_build_key,
            selection=selection, state_wave=state_wave, repository_root=candidate)
        baselines[originals_root] = regular_file_inventory(originals_root, allow_empty=True)
        context = dict(trusted_source_sha=trusted_source_sha, trusted_workflow_sha=trusted_workflow_sha,
            transport_producer=producer, event_payload=event_payload, environment=environment, token=token)
        result_path = private / "result"
        unchanged()
        if target == "aggregate":
            verify_aggregate_prepared_selection(selected, selection, producer=producer,
                expected_build_key=expected_build_key, originals=originals)
            retained = prepared / "release-handoff"
            release = retained if retained.exists() else None
            if release is not None and handoffs:
                raise ValueError("Prepared aggregate retained release cannot mix variant overrides")
            unchanged()
            result = _attest_selected_runtime_aggregate(trusted, result_path,
                selected_root=selected, selection=selection, expected_build_key=expected_build_key,
                variant_handoffs=handoffs, release_handoff=release, **context)
        else:
            arguments = verify_native_prepared_selection(selected, selection, producer=producer,
                target=target, expected_build_key=expected_build_key, originals=originals)
            unchanged()
            result = attest_runtime_variant_ci(trusted, result_path, target=target, **context, **arguments)
        expected_result_files = regular_file_inventory(result_path, allow_empty=True)
        # Original uploads remain external custody. The signing leaf already
        # carries original phase evidence; publish its exact verified layout.
        unchanged()
        if regular_file_inventory(result_path, allow_empty=True) != expected_result_files:
            raise ValueError("Prepared Runtime result changed before publication")
        _destination(output, protected)
        publish_regular_tree(result_path, output, allow_empty=True,
                             expected_inventory=expected_result_files)
    return result
