"""Protected native Runtime caller; execute only from independently pinned code.

This composition verifies originals and signs external evidence only. It does
not build products, authorize itself, or replace workflow environment approval.
"""

from collections.abc import Mapping
import os
from pathlib import Path
import tempfile
from typing import Any

from product_release_context import verify_product_release_context
from product_reuse import _release_trust, capture_runtime_original_ci_phases
from products.contract_projection import verify_contract_component_projection
from products.inventory import (
    publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_semver, sha256_file, snapshot_regular_tree, write_canonical_json,
)
from products.runtime_attestation import build_runtime_variant_attestation, read_runtime_variant_handoff
from products.sdk_runtime_content import (
    _native_desktop_report, _native_runtime_capture, verify_native_runtime_presigning_content,
)
from products.signatures import load_keyring, require_active_release_key


def attest_runtime_variant_ci(
    repository_root: Path, destination: Path, *, target: str,
    trusted_source_sha: str, trusted_workflow_sha: str,
    transport_producer: Mapping[str, Any], event_payload: dict[str, Any],
    environment: Mapping[str, str], runtime_stage_root: Path,
    phase_receipts: dict[str, Path], variant_payload: Path,
    contract: Mapping[str, Path], contract_version: str,
    token: str | None = None, release_handoffs: tuple[Path, ...] = (),
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
        projection = verify_contract_component_projection(
            captured_contract["stage"], captured_contract["receipt"], captured_contract["attestation"],
            captured_contract["signature"], captured_contract["public_key"],
            expected_trust_domain="release", expected_contract_version=contract_version,
            required_components=("common", target), keyring=trust.keyring, keys_directory=trust.keys)
        with _native_runtime_capture(target, runtime_stage_root, phase_receipts,
                                     variant_payload, Path(contract["payload"])) as captured:
            runtime, receipts, payload, contract_payload = captured
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
