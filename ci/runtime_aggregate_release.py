"""Protected aggregate attestation over completed originals, never a rebuild.

Execute only from independently pinned caller code. CI26 capture authenticates
original uploads; existing signed Contract/native and semantic gates authenticate
their contents. Retained releases use the complete signed carrier reader;
their original bytes and provenance are forwarded without re-signing.
"""

from collections.abc import Mapping
import os
from pathlib import Path
import tempfile
from typing import Any

from product_release_context import verify_product_release_context
from product_reuse import (
    _dependency_closure, _release_trust, capture_runtime_resume_upload,
    materialize_runtime_attestation_inputs,
    materialize_runtime_aggregate_release_evidence,
)
from runtime_aggregate_phase import collect_finalized_inputs
from runtime_original_ci import capture_runtime_aggregate_original_ci
from products.contract_projection import verify_contract_component_projection
from products.inventory import (
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_regular_directory,
    require_semver, require_sha256, sha256_bytes, sha256_file, snapshot_regular_tree,
    write_canonical_json,
)
from products.receipt import validate_phase_receipt
from products.registry import NATIVE_TARGETS, PhaseInstanceId
from products.runtime_aggregate import (
    build_runtime_aggregate_attestation, verify_runtime_aggregate_presigning_content,
)
from products.runtime_attestation import read_runtime_variant_handoff
from products.sdk_runtime_content import verify_native_runtime_presigning_content
from products.signing_isolation import require_no_signing_secret
from products.signatures import load_keyring, private_key_bytes, require_active_release_key


_METADATA = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
_PHASES = ("binary", "package", "validation", "metadata")


def _destination(destination: Path, originals) -> Path:
    path = Path(os.path.abspath(destination))
    if path.exists() or path.is_symlink():
        raise ValueError("Runtime aggregate caller destination must not exist")
    for ancestor in path.parents:
        if ancestor.exists() or ancestor.is_symlink():
            require_regular_directory(ancestor, "Runtime aggregate caller output ancestry")
    resolved = path.resolve(strict=False)
    for original in originals:
        source = Path(original).resolve(strict=True)
        if source == resolved or source in resolved.parents or resolved in source.parents:
            raise ValueError("Runtime aggregate caller destination overlaps an original input")
    return path


def _selected_originals(root: Path, selection: dict[str, Any], producer, expected_build_key):
    if load_canonical_json_bytes(read_regular_file_bytes(
            root / "selection.json", max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)) != selection:
        raise ValueError("Runtime aggregate captured selection differs from the elected selection")
    require_exact_keys(selection, {
        "schemaVersion", "target", "metadata", "producer", "contractVersion", "aggregateStage",
        "aggregateReceipt", "aggregateManifest", "originals", "contractHandoff",
    }, "Selected Runtime aggregate")
    if (type(selection["schemaVersion"]) is not int or selection["schemaVersion"] != 1
            or selection["target"] != "aggregate" or selection["producer"] != producer):
        raise ValueError("Runtime aggregate selected state differs from protected caller context")
    originals = {}
    identities = _dependency_closure((_METADATA,))
    if not isinstance(selection["originals"], list) or len(selection["originals"]) != len(identities):
        raise ValueError("Runtime aggregate selection requires all fifty originals")
    for record, instance in zip(selection["originals"], identities, strict=True):
        require_exact_keys(record, {"product", "component", "phase", "target", "receiptSha256", "directory"},
                           "Selected Runtime aggregate original")
        identity = (instance.product, instance.component, instance.phase, instance.target)
        directory = "predecessors/" + "-".join(identity)
        if tuple(record[name] for name in ("product", "component", "phase", "target")) != identity or \
                record["directory"] != directory:
            raise ValueError("Runtime aggregate original selection identity/path mismatch")
        receipt_path = root / directory / "phase-receipt.json"
        if sha256_file(receipt_path) != require_sha256(record["receiptSha256"], "Selected original receipt digest"):
            raise ValueError("Runtime aggregate receipt differs from its selected original")
        receipt = validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(
            receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)))
        if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != identity:
            raise ValueError("Runtime aggregate selected receipt identity mismatch")
        originals[identity] = {"stage": root / directory / "stage", "receiptPath": receipt_path, "receipt": receipt}
    aggregate = originals[("runtime", "runtime-aggregate", "metadata", "aggregate")]
    if (aggregate["receipt"]["buildKey"] != expected_build_key
            or selection["metadata"]["buildKey"] != expected_build_key
            or selection["metadata"]["receiptSha256"] != sha256_file(aggregate["receiptPath"])):
        raise ValueError("Runtime aggregate receipt differs from the selected metadata key/receipt")
    if (selection["aggregateStage"] != aggregate["stage"].relative_to(root).as_posix()
            or selection["aggregateReceipt"] != aggregate["receiptPath"].relative_to(root).as_posix()
            or selection["contractHandoff"] != "contract-input"):
        raise ValueError("Runtime aggregate selected paths differ from the original closure")
    return originals


def _attest_selected_runtime_aggregate(
    repository_root: Path, destination: Path, *, selected_root: Path, selection: dict[str, Any],
    expected_build_key: str, trusted_source_sha: str, trusted_workflow_sha: str,
    transport_producer: Mapping[str, Any], event_payload: dict[str, Any], environment: Mapping[str, str],
    token: str | None, variant_handoffs: dict[str, Path], release_handoff: Path | None = None,
) -> dict[str, Any]:
    """Private composition seam; the public entry elects/restores the selection."""
    trusted, producer, source_tree, expected_environment, reason = verify_product_release_context(
        repository_root, trusted_source_sha=trusted_source_sha, trusted_workflow_sha=trusted_workflow_sha,
        transport_producer=transport_producer, event_payload=event_payload, environment=environment)
    require_sha256(expected_build_key, "Selected Runtime aggregate metadata build key")
    require_exact_keys(variant_handoffs, set(NATIVE_TARGETS) if release_handoff is None else set(),
                       "Original signed Runtime variant handoffs")
    if release_handoff is None and (type(token) is not str or not token):
        raise ValueError("Runtime aggregate original CI capture requires an observation token")
    output = _destination(destination, (trusted, selected_root, *variant_handoffs.values(),
                                       *((release_handoff,) if release_handoff is not None else ())))
    sources = {"selected-inputs": Path(selected_root),
               **{f"variant-inputs/{target}": Path(path) for target, path in variant_handoffs.items()}}
    before = {name: regular_file_inventory(path, allow_empty=name == "selected-inputs")
              for name, path in sources.items()}
    with tempfile.TemporaryDirectory(prefix="runtime-aggregate-release-") as temporary:
        root = Path(temporary).resolve()
        prepared = root / "prepared"
        for name, source in sources.items():
            snapshot_regular_tree(source, prepared / name, allow_empty=name == "selected-inputs")
            if regular_file_inventory(prepared / name, allow_empty=name == "selected-inputs") != before[name]:
                raise ValueError("Runtime aggregate original changed during capture")
        trust = _release_trust(trusted, trusted_source_sha, prepared)
        if trust is None:
            raise ValueError("Runtime aggregate caller has no release verification policy")
        policy = load_keyring(trust.keyring, trust.keys)
        tracked_keyring = git_regular_blob_bytes(
            trusted, trusted_source_sha, "gradle/release/product-signing-keys.json", max_bytes=64 * 1024,
        )
        trusted_policy_files = [{"relativePath": "product-signing-keys.json",
                                 "bytes": len(tracked_keyring), "sha256": sha256_bytes(tracked_keyring)}]
        for record in (policy["activeKey"], *policy["retiredKeys"]):
            if record is not None:
                name = f"{record['keyId']}.pub"
                raw = git_regular_blob_bytes(
                    trusted, trusted_source_sha, f"gradle/release/keys/{name}", max_bytes=64 * 1024,
                )
                trusted_policy_files.append({"relativePath": f"keys/{name}",
                                             "bytes": len(raw), "sha256": sha256_bytes(raw)})
        trusted_policy_files.sort(key=lambda record: record["relativePath"])
        base_files = [
            *({**record, "relativePath": f"{name}/{record['relativePath']}"}
              for name, records in before.items() for record in records),
            *({**record, "relativePath": f"trust/{record['relativePath']}"}
              for record in trusted_policy_files),
        ]
        base_files.sort(key=lambda record: record["relativePath"])
        selected = prepared / "selected-inputs"
        originals = _selected_originals(selected, selection, producer, expected_build_key)
        if regular_file_inventory(prepared, allow_empty=True) != base_files:
            raise ValueError("Runtime aggregate captured inputs differ from selected originals or pinned Git trust")

        if release_handoff is not None:
            from products.runtime_aggregate_handoff import verified_runtime_aggregate_handoff
            with verified_runtime_aggregate_handoff(
                release_handoff, keyring=trust.keyring, keys_directory=trust.keys,
            ) as retained:
                for identity, original in originals.items():
                    instance = PhaseInstanceId(*identity)
                    if read_regular_file_bytes(original["receiptPath"]) != retained["receiptBytes"][instance]:
                        raise ValueError("Retained aggregate differs from a selected original receipt")
                    retained_stage = retained["directory"] / "selected-inputs/predecessors" / (
                        "-".join(identity)) / "stage"
                    if regular_file_inventory(original["stage"]) != regular_file_inventory(retained_stage):
                        raise ValueError("Retained aggregate differs from a selected original stage")
                snapshot_regular_tree(retained["directory"], prepared / "retained-release", allow_empty=True)
                if regular_file_inventory(prepared / "retained-release", allow_empty=True) != retained["inventory"]:
                    raise ValueError("Retained aggregate changed during forwarding")
                retained_inventory = retained["inventory"]
            # The direct original carrier stays byte-identical. Current selection
            # and consumer provenance live beside it, never inside that carrier.
            caller = {"schemaVersion": 1, "target": "aggregate", "trustedSourceCommit": trusted_source_sha,
                "trustedSourceTree": source_tree, "trustedWorkflowSha": trusted_workflow_sha,
                "transportProducer": producer, "authorizationReason": reason, "event": event_payload,
                "environment": {**expected_environment, "GITHUB_REF": environment.get("GITHUB_REF")},
                "metadataReceiptSha256": sha256_file(originals[("runtime", "runtime-aggregate", "metadata", "aggregate")]["receiptPath"]),
                "releaseDirectory": "retained-release"}
            for name, source in sources.items():
                if any(regular_file_inventory(path, allow_empty=name == "selected-inputs") != before[name]
                       for path in (source, prepared / name)):
                    raise ValueError("Runtime aggregate selected evidence changed during reuse")
            write_canonical_json(prepared / "caller.json", caller)
            caller_bytes = canonical_json_bytes(caller)
            expected_files = [
                *base_files,
                *({**record, "relativePath": f"retained-release/{record['relativePath']}"}
                  for record in retained_inventory),
                {"relativePath": "caller.json", "bytes": len(caller_bytes),
                 "sha256": sha256_bytes(caller_bytes)},
            ]
            expected_files.sort(key=lambda record: record["relativePath"])
            if (regular_file_inventory(release_handoff, allow_empty=True) != retained_inventory
                    or regular_file_inventory(prepared, allow_empty=True) != expected_files):
                raise ValueError("Retained aggregate changed before publication")
            publish_regular_tree(prepared, output, allow_empty=True,
                                 expected_inventory=expected_files)
            return caller

        def original(component, phase, target):
            return originals[("runtime", component, phase, target)]

        aggregate = original("runtime-aggregate", "metadata", "aggregate")
        contract = originals[("contract", "contract", "metadata", "common")]
        version = require_semver(selection["contractVersion"], "Selected Contract version")
        if contract["receipt"]["productVersion"] != version:
            raise ValueError("Runtime aggregate selected Contract version mismatch")
        handoff = selected / "contract-input"
        stem = f"codex-agent-contract-{version}"
        for phase in _PHASES:
            if read_regular_file_bytes(originals[("contract", "contract", phase, "common")]["receiptPath"]) != \
                    read_regular_file_bytes(handoff / f"execution-closure/receipts/{phase}.json"):
                raise ValueError("Runtime aggregate Contract handoff changes an original receipt")
        contract_args = dict(contract_payload=handoff / f"{stem}.zip",
            contract_metadata_receipt=contract["receiptPath"], contract_attestation=handoff / f"{stem}.attestation.json",
            contract_attestation_signature=handoff / f"{stem}.attestation.sig", contract_public_key=handoff / "public-key.pub")
        records = collect_finalized_inputs(aggregate["stage"], aggregate["receiptPath"], version, original)
        if records["manifest"].relative_to(selected).as_posix() != selection["aggregateManifest"]:
            raise ValueError("Runtime aggregate manifest differs from its selected original")
        signatures = {key: {} for key in ("variant_attestations", "variant_attestation_signatures", "variant_public_keys")}
        for target in NATIVE_TARGETS:
            native = prepared / "variant-inputs" / target
            verified = read_runtime_variant_handoff(native, target=target, keyring=trust.keyring, keys_directory=trust.keys)
            if (any(verified["receiptBytes"][phase] != records["variant_phase_receipts"][target][phase].read_bytes()
                    for phase in _PHASES)
                    or verified["files"][verified["attestation"]["payload"]["fileName"]] != records["variant_bundles"][target].read_bytes()
                    or verified["files"]["validation-evidence.json"] != records["variant_validation_evidence"][target].read_bytes()):
                raise ValueError("Signed Runtime handoff differs from selected original receipts/payload/report")
            payload_stem = Path(verified["attestation"]["payload"]["fileName"]).stem
            signatures["variant_attestations"][target] = native / f"{payload_stem}.attestation.json"
            signatures["variant_attestation_signatures"][target] = native / f"{payload_stem}.attestation.sig"
            signatures["variant_public_keys"][target] = native / "public-key.pub"
            projection = verify_contract_component_projection(
                contract["stage"], contract["receiptPath"], contract_args["contract_attestation"],
                contract_args["contract_attestation_signature"], contract_args["contract_public_key"],
                expected_trust_domain="release", expected_contract_version=version,
                required_components=("common", target), keyring=trust.keyring, keys_directory=trust.keys)
            # Only private restored copies are arranged for the existing verifier.
            for phase in ("package", "validation"):
                snapshot_regular_tree(original(target, phase, target)["stage"], prepared / "runtime-stages" / target / phase)
            verify_native_runtime_presigning_content(target, prepared / "runtime-stages",
                records["variant_phase_receipts"][target], records["variant_bundles"][target],
                projection, contract_args["contract_payload"])
        capture_runtime_aggregate_original_ci(aggregate["receiptPath"], records["adapter_receipts"],
            prepared / "original-evidence", trusted_workflow_sha=trusted_workflow_sha, token=token)
        arguments = {**records, **contract_args, **signatures,
                     "contract_keyring": trust.keyring, "contract_keys_directory": trust.keys,
                     "variant_keyring": trust.keyring, "variant_keys_directory": trust.keys}
        baseline = regular_file_inventory(prepared, allow_empty=True)

        def unchanged():
            if (regular_file_inventory(prepared, allow_empty=True) != baseline
                    or any(regular_file_inventory(path, allow_empty=name == "selected-inputs") != before[name]
                           or regular_file_inventory(prepared / name, allow_empty=name == "selected-inputs") != before[name]
                           for name, path in sources.items())):
                raise ValueError("Runtime aggregate original or captured evidence changed during verification")

        verify_runtime_aggregate_presigning_content(**arguments, required_trust_domain="release")
        unchanged()
        active, public_key = require_active_release_key(policy, trust.keys)
        publication = {
            records["manifest"].name: read_regular_file_bytes(records["manifest"], reject_symlink_parents=True),
            "metadata-receipt.json": read_regular_file_bytes(aggregate["receiptPath"], reject_symlink_parents=True),
            "public-key.pub": read_regular_file_bytes(public_key, reject_symlink_parents=True),
        }
        signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        secret = environment.get("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY")
        if type(secret) is not str or not secret:
            raise ValueError("Protected Runtime aggregate signing key is unavailable")
        private_key = root / "private-key"
        private_key.touch(mode=0o600, exist_ok=False)
        private_key.write_bytes(private_key_bytes(secret))
        attestation = build_runtime_aggregate_attestation(**arguments, signing_metadata=signing,
            private_key=private_key, public_key=public_key, output_directory=root / "signed",
            required_variant_trust_domain="release", keyring=trust.keyring, keys_directory=trust.keys)
        signed_files = regular_file_inventory(root / "signed")
        unchanged()
        snapshot_regular_tree(root / "signed", prepared / "aggregate-input")
        for name, raw in publication.items():
            (prepared / "aggregate-input" / name).write_bytes(raw)
        expected_files = [
            *baseline,
            *({**record, "relativePath": f"aggregate-input/{record['relativePath']}"}
              for record in signed_files),
            *({"relativePath": f"aggregate-input/{name}", "bytes": len(raw),
               "sha256": sha256_bytes(raw)} for name, raw in publication.items()),
        ]
        expected_files.sort(key=lambda record: record["relativePath"])
        caller = {"schemaVersion": 1, "target": "aggregate", "trustedSourceCommit": trusted_source_sha,
            "trustedSourceTree": source_tree, "trustedWorkflowSha": trusted_workflow_sha,
            "transportProducer": producer, "authorizationReason": reason, "event": event_payload,
            "environment": {**expected_environment, "GITHUB_REF": environment.get("GITHUB_REF")},
            "metadataReceiptSha256": attestation["metadataReceiptSha256"]}
        write_canonical_json(prepared / "caller.json", caller)
        caller_bytes = canonical_json_bytes(caller)
        expected_files.append({"relativePath": "caller.json", "bytes": len(caller_bytes),
                               "sha256": sha256_bytes(caller_bytes)})
        expected_files.sort(key=lambda record: record["relativePath"])
        if (regular_file_inventory(root / "signed") != signed_files
                or regular_file_inventory(prepared, allow_empty=True) != expected_files
                or any(regular_file_inventory(source, allow_empty=name == "selected-inputs") != before[name]
                       for name, source in sources.items())):
            raise ValueError("Runtime aggregate verified evidence changed before publication")
        publish_regular_tree(prepared, output, allow_empty=True,
                             expected_inventory=expected_files)
    return caller


def attest_runtime_aggregate_state_ci(
    repository_root: Path, candidate_root: Path, plan_path: Path, destination: Path, *,
    expected_build_key: str, artifact_id: int, artifact_sha256: str, state_wave: int,
    trusted_source_sha: str, trusted_workflow_sha: str, transport_producer: Mapping[str, Any],
    event_payload: dict[str, Any], environment: Mapping[str, str], token: str,
    variant_handoffs: dict[str, Path], release_handoffs: tuple[Path, ...] = (),
    sdk_validation_tooling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture/elect the completed aggregate and sign only its original bytes.

    Retained aggregate release admission never falls back to original CI or
    re-signs. Current selected-state transport is still authenticated separately.
    """
    if sdk_validation_tooling is not None:
        require_no_signing_secret(environment)
    if len(release_handoffs) > 1:
        raise ValueError("Runtime aggregate reuse requires exactly one direct release carrier")
    trusted, producer, _, _, _ = verify_product_release_context(
        repository_root, trusted_source_sha=trusted_source_sha, trusted_workflow_sha=trusted_workflow_sha,
        transport_producer=transport_producer, event_payload=event_payload, environment=environment)
    require_sha256(expected_build_key, "Selected Runtime aggregate metadata build key")
    require_exact_keys(variant_handoffs, set() if release_handoffs or not variant_handoffs else set(NATIVE_TARGETS),
                       "Original signed Runtime variant handoffs")
    candidate = Path(candidate_root).resolve(strict=True)
    if trusted == candidate or trusted in candidate.parents or candidate in trusted.parents:
        raise ValueError("Runtime aggregate signing requires separate trusted and candidate checkouts")
    output = _destination(destination, (trusted, candidate, plan_path, *variant_handoffs.values(), *release_handoffs))
    if type(token) is not str or not token:
        raise ValueError("Runtime aggregate state capture requires an observation token")
    with tempfile.TemporaryDirectory(prefix="runtime-aggregate-selected-", dir=candidate) as temporary:
        root = Path(temporary).resolve()
        capture = root / "current-state"
        capture_runtime_resume_upload(plan_path, capture, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, repository_root=candidate, environ=environment,
            token=token, state_wave=state_wave)
        original = capture / "original"
        selected = root / "selected"
        selection = materialize_runtime_attestation_inputs(original / "product-resume-inputs/plan/impact-plan.json",
            original / "product-resume-state", original / ("runtime-state" if state_wave else "product-resume-state"),
            selected, target="aggregate", expected_build_key=expected_build_key, repository_root=candidate,
            environ=environment, sdk_validation_tooling=sdk_validation_tooling)
        retained = release_handoffs[0] if release_handoffs else None
        if retained is None:
            trust = _release_trust(trusted, trusted_source_sha, root / "retained-policy")
            if trust is None:
                raise ValueError("Aggregate retained selection requires caller-pinned public policy")
            retained = materialize_runtime_aggregate_release_evidence(
                original / "product-resume-inputs/plan/impact-plan.json", original / "product-resume-state",
                original / ("runtime-state" if state_wave else "product-resume-state"), root / "retained-aggregate",
                expected_build_key=expected_build_key, keyring=trust.keyring, keys_directory=trust.keys,
                repository_root=candidate, environ=environment, sdk_validation_tooling=sdk_validation_tooling)
        selected_variants = {} if retained is not None else variant_handoffs
        require_exact_keys(selected_variants, set() if retained is not None else set(NATIVE_TARGETS),
                           "Selected aggregate requires complete retained release or all five original variants")
        before = regular_file_inventory(root, allow_empty=True)
        with tempfile.TemporaryDirectory(prefix="runtime-aggregate-selected-result-") as result_temporary:
            prepared = Path(result_temporary).resolve() / "result"
            result = _attest_selected_runtime_aggregate(trusted, prepared, selected_root=selected, selection=selection,
                expected_build_key=expected_build_key, trusted_source_sha=trusted_source_sha,
                trusted_workflow_sha=trusted_workflow_sha, transport_producer=producer,
                event_payload=event_payload, environment=environment, token=token, variant_handoffs=selected_variants,
                release_handoff=retained)
            if regular_file_inventory(root, allow_empty=True) != before:
                raise ValueError("Runtime aggregate selected originals changed during protected verification")
            snapshot_regular_tree(capture, prepared / "selected-state-transport", allow_empty=True)
            publish_regular_tree(prepared, output, allow_empty=True)
    return result
