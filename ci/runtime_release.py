"""Protected native Runtime caller; execute only from independently pinned code.

This composition verifies originals and signs external evidence only. It does
not build products, authorize itself, or replace workflow environment approval.
"""

from collections.abc import Mapping
import argparse
import os
from pathlib import Path
import tempfile
from typing import Any

from product_release_context import verify_product_release_context
from product_reuse import (
    _release_trust, capture_runtime_original_ci_phases, capture_runtime_resume_upload,
    materialize_runtime_attestation_inputs,
)
from products.contract_projection import verify_contract_component_projection
from products.inventory import (
    load_canonical_json_bytes, load_json_bytes, publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_semver, require_sha256, sha256_file, snapshot_regular_tree, write_canonical_json,
)
from products.runtime_attestation import build_runtime_variant_attestation, read_runtime_variant_handoff
from products.registry import NATIVE_TARGETS
from products.sdk_runtime_content import (
    _native_desktop_report, _native_runtime_capture, verify_native_runtime_presigning_content,
)
from products.signatures import load_keyring, require_active_release_key
from products.signing_isolation import require_no_signing_secret


def attest_runtime_variant_ci(
    repository_root: Path, destination: Path, *, target: str,
    trusted_source_sha: str, trusted_workflow_sha: str,
    transport_producer: Mapping[str, Any], event_payload: dict[str, Any],
    environment: Mapping[str, str], runtime_stage_root: Path,
    phase_receipts: dict[str, Path], variant_payload: Path,
    contract: Mapping[str, Path], contract_version: str,
    token: str | None = None, release_handoffs: tuple[Path, ...] = (),
    expected_receipt_sha256s: Mapping[str, str] | None = None,
    expected_contract_receipt_sha256: str | None = None,
    expected_build_key: str | None = None,
) -> dict[str, Any]:
    """Admit exact originals before key access; retain full external proof once.

The caller must still bind this selection to the authenticated elected Runtime
state before aggregate/SDK continuation. A success here does not elect a plan.
"""
    repository_root, producer, source_tree, expected_environment, reason = verify_product_release_context(
        repository_root, trusted_source_sha=trusted_source_sha, trusted_workflow_sha=trusted_workflow_sha,
        transport_producer=transport_producer, event_payload=event_payload, environment=environment)
    require_semver(contract_version, "Runtime caller Contract version")
    require_exact_keys(contract, {"stage", "receipt", "attestation", "signature", "public_key", "payload"},
                       "Runtime caller Contract inputs")
    destination = Path(os.path.abspath(destination))
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime caller destination must not exist")
    resolved_output = destination.parent.resolve(strict=False) / destination.name
    for original in (repository_root, runtime_stage_root, variant_payload, *phase_receipts.values(),
                     *contract.values(), *release_handoffs):
        source = Path(original).resolve(strict=True)
        if source == resolved_output or source in resolved_output.parents or resolved_output in source.parents:
            raise ValueError("Runtime caller destination overlaps original input or trusted source")

    with tempfile.TemporaryDirectory(prefix="runtime-release-caller-") as temporary:
        root = Path(temporary).resolve()
        trust = _release_trust(repository_root, trusted_source_sha, root)
        if trust is None:
            raise ValueError("Runtime caller has no release verification policy")
        policy = load_keyring(trust.keyring, trust.keys)
        prepared = root / "prepared"
        contract_root = prepared / "contract-input"
        snapshot_regular_tree(Path(contract["stage"]), contract_root / "stage")
        captured_contract = {"stage": contract_root / "stage"}
        for name in ("receipt", "attestation", "signature", "public_key"):
            captured_contract[name] = contract_root / Path(contract[name]).name
            if captured_contract[name].exists():
                raise ValueError("Runtime caller Contract input basenames collide")
            captured_contract[name].write_bytes(read_regular_file_bytes(
                Path(contract[name]), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        snapshot_regular_tree(Path(contract["attestation"]).parent / "execution-closure",
                              contract_root / "execution-closure")
        if expected_contract_receipt_sha256 is not None and sha256_file(captured_contract["receipt"]) != \
                require_sha256(expected_contract_receipt_sha256, "Selected Contract metadata receipt digest"):
            raise ValueError("Runtime caller Contract receipt differs from the selected original")
        projection = verify_contract_component_projection(
            captured_contract["stage"], captured_contract["receipt"], captured_contract["attestation"],
            captured_contract["signature"], captured_contract["public_key"],
            expected_trust_domain="release", expected_contract_version=contract_version,
            required_components=("common", target), keyring=trust.keyring, keys_directory=trust.keys)
        with _native_runtime_capture(target, runtime_stage_root, phase_receipts,
                                     variant_payload, Path(contract["payload"])) as captured:
            runtime, receipts, payload, contract_payload = captured
            if expected_build_key is not None:
                expected = require_sha256(expected_build_key, "Selected Runtime metadata build key")
                metadata = load_canonical_json_bytes(read_regular_file_bytes(
                    receipts["metadata"], max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
                if metadata["buildKey"] != expected:
                    raise ValueError("Runtime metadata receipt differs from the caller's selected build key")
            if expected_receipt_sha256s is not None:
                require_exact_keys(expected_receipt_sha256s, set(receipts), "Selected Runtime receipt digests")
                if any(sha256_file(path) != require_sha256(expected_receipt_sha256s[phase], "Selected Runtime receipt digest")
                       for phase, path in receipts.items()):
                    raise ValueError("Runtime caller receipts differ from the selected originals")
            # Source authentication is separate from semantic content validation.
            originals = prepared / "original-evidence"
            capture_runtime_original_ci_phases(
                receipts, originals, target=target, trusted_workflow_sha=trusted_workflow_sha,
                token=token, release_handoffs=release_handoffs,
                keyring=trust.keyring if release_handoffs else None,
                keys_directory=trust.keys if release_handoffs else None)
            verify_native_runtime_presigning_content(
                target, runtime, receipts, payload, projection, contract_payload)
            # Preserve raw package/process/JUnit/C-ABI/Apple proof externally.
            snapshot_regular_tree(runtime, prepared / "runtime-stages")
            baseline = regular_file_inventory(prepared, allow_empty=True)
            retained = None
            for number in range(len(release_handoffs)):
                candidate = originals / "release-handoffs" / str(number)
                verified = read_runtime_variant_handoff(candidate, target=target,
                    keyring=trust.keyring, keys_directory=trust.keys)
                if all(verified["receiptBytes"][phase] == path.read_bytes() for phase, path in receipts.items()) and \
                        verified["attestation"]["payload"]["sha256"] == sha256_file(payload):
                    retained = verified["files"]
                    break
            if retained is not None:
                for name, raw in retained.items():
                    path = root / "handoff" / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
            else:
                active, public_key = require_active_release_key(policy, trust.keys)
                signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
                signing.update(active)
                secret = environment.get("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY")
                if type(secret) is not str or not secret:
                    raise ValueError("Protected Runtime signing key is unavailable")
                private_key = root / "private-key"
                private_key.touch(mode=0o600, exist_ok=False)
                private_key.write_bytes(secret.encode("utf-8"))
                build_runtime_variant_attestation(
                    payload, *(receipts[phase] for phase in ("binary", "package", "validation", "metadata")),
                    _native_desktop_report(runtime, target), signing, private_key, public_key, root / "handoff",
                    keyring=trust.keyring, keys_directory=trust.keys, complete_handoff=True)
            if regular_file_inventory(prepared, allow_empty=True) != baseline:
                raise ValueError("Runtime caller captured proof changed during attestation")
        # Leaving the capture scope rechecks originals before anything is published.
        snapshot_regular_tree(root / "handoff", prepared / "runtime-input")
        snapshot_regular_tree(root / "trust", prepared / "caller-policy")
        caller = {
            "schemaVersion": 1, "target": target, "trustedSourceCommit": trusted_source_sha,
            "trustedSourceTree": source_tree, "trustedWorkflowSha": trusted_workflow_sha,
            "transportProducer": producer, "authorizationReason": reason,
            "event": event_payload,
            "environment": {**expected_environment, "GITHUB_REF": environment.get("GITHUB_REF")},
        }
        write_canonical_json(prepared / "caller.json", caller)
        publish_regular_tree(prepared, destination, allow_empty=True)
    return caller


def attest_runtime_state_ci(
    repository_root: Path, candidate_root: Path, plan_path: Path, destination: Path, *,
    target: str, expected_build_key: str, artifact_id: int, artifact_sha256: str,
    state_wave: int, trusted_source_sha: str, trusted_workflow_sha: str,
    transport_producer: Mapping[str, Any], event_payload: dict[str, Any],
    environment: Mapping[str, str], token: str,
    release_handoffs: tuple[Path, ...] = (),
    sdk_validation_tooling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind the original selected state to the protected native caller, build-free.

Candidate source is data for Git inventory only; no candidate script, Gradle
process or product compiler is executed. The reviewed source remains separate.
"""
    if sdk_validation_tooling is not None:
        require_no_signing_secret(environment)
    trusted, producer, _, _, _ = verify_product_release_context(
        repository_root, trusted_source_sha=trusted_source_sha, trusted_workflow_sha=trusted_workflow_sha,
        transport_producer=transport_producer, event_payload=event_payload, environment=environment)
    if target not in NATIVE_TARGETS:
        raise ValueError("Runtime state caller requires a native target")
    require_sha256(expected_build_key, "Selected Runtime metadata build key")
    candidate = Path(candidate_root).resolve(strict=True)
    if trusted == candidate or trusted in candidate.parents or candidate in trusted.parents:
        raise ValueError("Runtime signing needs separate trusted and candidate checkouts")
    output = Path(os.path.abspath(destination))
    if output.exists() or output.is_symlink():
        raise ValueError("Runtime state caller destination must not exist")
    resolved_output = output.parent.resolve(strict=False) / output.name
    for original in (trusted, candidate, Path(plan_path), *release_handoffs):
        source = Path(original).resolve(strict=True)
        if source == resolved_output or source in resolved_output.parents or resolved_output in source.parents:
            raise ValueError("Runtime state caller output overlaps original input")
    if type(token) is not str or not token:
        raise ValueError("Runtime state capture requires an observation token")
    with tempfile.TemporaryDirectory(prefix="runtime-selected-caller-", dir=candidate) as temporary:
        root = Path(temporary).resolve()
        capture = root / "current-state"
        capture_runtime_resume_upload(
            plan_path, capture, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, repository_root=candidate,
            environ=environment, token=token, state_wave=state_wave)
        originals = capture / "original"
        selected_root = root / "selected"
        retained_policy = _release_trust(trusted, trusted_source_sha, root / "retained-policy")
        if retained_policy is None:
            raise ValueError("Runtime state caller has no pinned release verification policy")
        selection = materialize_runtime_attestation_inputs(
            originals / "product-resume-inputs/plan/impact-plan.json",
            originals / "product-resume-state",
            originals / ("runtime-state" if state_wave else "product-resume-state"),
            selected_root, target=target, expected_build_key=expected_build_key,
            repository_root=candidate, environ=environment, sdk_validation_tooling=sdk_validation_tooling,
            retained_release_keyring=retained_policy.keyring,
            retained_release_keys_directory=retained_policy.keys)
        if selection["producer"] != producer:
            raise ValueError("Runtime selected state differs from protected caller context")
        before = regular_file_inventory(root, allow_empty=True)
        # This private output is outside the candidate directory to satisfy the
        # leaf caller's strict original-input/output overlap checks.
        with tempfile.TemporaryDirectory(prefix="runtime-selected-result-") as result_temporary:
            prepared = Path(result_temporary).resolve() / "result"
            result = attest_runtime_variant_ci(
                trusted, prepared, target=target, trusted_source_sha=trusted_source_sha,
                trusted_workflow_sha=trusted_workflow_sha, transport_producer=producer,
                event_payload=event_payload, environment=environment,
                runtime_stage_root=selected_root / selection["runtimeStageRoot"],
                phase_receipts={phase: selected_root / path for phase, path in selection["phaseReceipts"].items()},
                variant_payload=selected_root / selection["variantPayload"],
                contract={name: selected_root / path for name, path in selection["contract"].items()},
                contract_version=selection["contractVersion"], token=token,
                release_handoffs=(*release_handoffs, *(selected_root / path for path in selection["releaseHandoffs"])),
                expected_receipt_sha256s=selection["receiptSha256s"],
                expected_contract_receipt_sha256=selection["contractReceiptSha256"],
                expected_build_key=expected_build_key)
            if regular_file_inventory(root, allow_empty=True) != before:
                raise ValueError("Runtime selected originals changed during protected verification")
            snapshot_regular_tree(capture, prepared / "selected-state-transport", allow_empty=True)
            # Persist exact selected identities, not private temporary path names.
            write_canonical_json(prepared / "selected-state.json", {name: selection[name] for name in (
                "schemaVersion", "target", "metadata", "producer", "contractVersion",
                "contractReceiptSha256", "receiptSha256s")})
            publish_regular_tree(prepared, output, allow_empty=True)
    return result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repository-root", "candidate-root", "plan", "destination"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--target", choices=(*NATIVE_TARGETS, "aggregate"), required=True)
    parser.add_argument("--variant-handoff", action="append", default=[], metavar="TARGET=PATH")
    for name in ("expected-build-key", "artifact-sha256", "trusted-source-sha", "trusted-workflow-sha", "validation-tree"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--state-wave", type=int, choices=range(6), required=True)
    parser.add_argument("--release-handoff", type=Path, action="append", default=[])
    parser.add_argument("--sdk-validation-tooling", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    parser.add_argument("--prepare-only", action="store_true",
                        help="Materialize original signing inputs on a non-secret runner; never sign")
    parser.add_argument("--preparation-artifact-id", type=int)
    parser.add_argument("--preparation-artifact-sha256")
    args = parser.parse_args(argv)
    prepared_mode = args.preparation_artifact_id is not None or args.preparation_artifact_sha256 is not None
    if prepared_mode and (args.preparation_artifact_id is None or args.preparation_artifact_sha256 is None):
        parser.error("prepared release requires paired preparation artifact ID and digest")
    if prepared_mode and args.prepare_only:
        parser.error("prepared release and preparation-only modes are mutually exclusive")
    if prepared_mode and args.sdk_validation_tooling is not None:
        parser.error("prepared release does not accept SDK tooling")
    if args.sdk_apple_validation_policy is not None and not args.prepare_only:
        parser.error("Apple validation policy is accepted only by non-secret preparation")
    if prepared_mode and args.release_handoff:
        parser.error("prepared release does not accept release handoff overrides")
    if args.prepare_only:
        require_no_signing_secret(os.environ)
        if args.variant_handoff or args.release_handoff:
            parser.error("preparation selects retained evidence from original state, not handoff overrides")
    variants = {}
    for value in args.variant_handoff:
        target, separator, path = value.partition("=")
        if not separator or target not in NATIVE_TARGETS or not path or target in variants:
            parser.error("variant handoffs require unique native TARGET=PATH entries")
        variants[target] = Path(path)
    if args.target == "aggregate":
        if args.release_handoff:
            if len(args.release_handoff) != 1 or variants:
                parser.error("aggregate reuse requires one direct release carrier and no variant handoffs")
        elif variants and set(variants) != set(NATIVE_TARGETS):
            parser.error("aggregate attestation requires exactly five native variant handoffs")
    elif variants:
        parser.error("native attestation does not accept aggregate variant handoffs")
    event_payload = load_json_bytes(read_regular_file_bytes(
        Path(os.environ["GITHUB_EVENT_PATH"]), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
    event = os.environ.get("GITHUB_EVENT_NAME")
    producer = {
        "repository": os.environ.get("GITHUB_REPOSITORY"), "workflowPath": ".github/workflows/ci.yml",
        "commit": os.environ.get("GITHUB_SHA"), "tree": args.validation_tree, "event": event,
        "runId": int(os.environ["GITHUB_RUN_ID"]), "runAttempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "pullRequest": event_payload.get("number") if event == "pull_request" else None,
    }
    tooling = None
    if args.sdk_validation_tooling is not None:
        from product_reuse import _canonical_control
        tooling = _canonical_control(args.sdk_validation_tooling, "Caller SDK tooling policy")
    apple = {}
    if args.sdk_apple_validation_policy is not None:
        from product_reuse import _canonical_control
        apple["sdk_apple_validation_policy"] = _canonical_control(
            args.sdk_apple_validation_policy, "Caller Apple validation policy")
    if prepared_mode:
        from runtime_prepared_release import attest_prepared_runtime_ci
        caller = attest_prepared_runtime_ci
        component_arguments = {
            "target": args.target, "variant_handoffs": variants,
            "preparation_artifact_id": args.preparation_artifact_id,
            "preparation_artifact_sha256": args.preparation_artifact_sha256,
        }
    elif args.prepare_only:
        from runtime_signing_preparation import prepare_runtime_signing_inputs
        caller = prepare_runtime_signing_inputs
        component_arguments = {"target": args.target}
    elif args.target == "aggregate":
        from runtime_aggregate_release import attest_runtime_aggregate_state_ci
        caller = attest_runtime_aggregate_state_ci
        component_arguments = {"variant_handoffs": variants}
    else:
        caller = attest_runtime_state_ci
        component_arguments = {"target": args.target}
    if not args.prepare_only and not prepared_mode:
        component_arguments["release_handoffs"] = tuple(args.release_handoff)
    caller(
        args.repository_root, args.candidate_root, args.plan, args.destination, **component_arguments,
        expected_build_key=args.expected_build_key, artifact_id=args.artifact_id,
        artifact_sha256=args.artifact_sha256, state_wave=args.state_wave,
        trusted_source_sha=args.trusted_source_sha, trusted_workflow_sha=args.trusted_workflow_sha,
        transport_producer=producer, event_payload=event_payload, environment=os.environ,
        token=os.environ.get("GITHUB_TOKEN"),
        **({} if prepared_mode else {"sdk_validation_tooling": tooling}), **apple)


if __name__ == "__main__":
    main()
