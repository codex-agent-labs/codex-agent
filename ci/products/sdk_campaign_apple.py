"""Bind a selected Apple binary to both complete original validation handoffs.

This is a family verifier, not release admission. The protected campaign owns
the selected envelopes, restored stage, signed handoff paths and caller policy.
"""

from contextlib import ExitStack
from copy import deepcopy
import os
from pathlib import Path
import tempfile

from .inventory import (canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
                        require_exact_keys, require_relative_path)
from .receipt import verify_output_manifest_identity
from .registry import PhaseInstanceId
from .restore import verify_phase_shard
from .sdk_apple_validation_admission import apple_validation_policy_arguments
from .sdk_apple_validation_attestation import verified_apple_validation_handoff
from .sdk_apple_package_admission import verified_selected_ios_package
from .sdk_apple_metadata_admission import verify_sdk_apple_metadata_admission
from .signing_isolation import require_no_signing_secret


_BINARY = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
_PACKAGE = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
_TARGETS = ("ios-arm64", "ios-simulator-arm64")


def _envelope_binding(envelope):
    from .reuse import _validate_envelope

    identity, value = _validate_envelope(envelope)
    return identity, (value["receiptBytes"], value["receiptSha256"], value["objectSha256"],
                      canonical_json_bytes(value["receipt"]))


def verify_campaign_apple_binary(binary_envelope, binary_stage, package_envelope,
        validation_envelopes, handoffs, *, repository, policy_revision, policy,
        package_stage=None, validation_stages=None):
    """Return original binary receipt bytes after both full handoffs cleanly exit."""
    from .reuse import _validate_envelope

    require_no_signing_secret(os.environ)
    binary_id, binary = _validate_envelope(binary_envelope)
    package_id, package = _validate_envelope(package_envelope)
    if binary_id != _BINARY or package_id != _PACKAGE:
        raise ValueError("Apple campaign requires exact selected binary and package envelopes")
    selected = require_exact_keys(validation_envelopes, _TARGETS, "Apple campaign validation envelopes")
    roots = require_exact_keys(handoffs, _TARGETS, "Apple campaign signed handoffs")
    validations = {}
    selected_before = {}
    for target in _TARGETS:
        identity, validations[target] = _validate_envelope(selected[target])
        if identity != PhaseInstanceId("sdk", "sdk-ios", "validation", target):
            raise ValueError("Apple campaign validation envelope has the wrong target")
        selected_before[target] = _envelope_binding(selected[target])
    if len({str(Path(roots[target]).absolute()) for target in _TARGETS}) != 2:
        raise ValueError("Apple campaign requires two distinct signed handoffs")
    arguments = apple_validation_policy_arguments(policy)
    stage = Path(binary_stage)
    manifest = verify_output_manifest_identity(stage, "sdk", "sdk-ios", "binary", "ios",
                                               binary["receipt"]["productVersion"])
    if manifest["outputs"] != binary["receipt"]["outputs"]:
        raise ValueError("Selected Apple binary stage differs from its receipt")
    stage_before = regular_file_inventory(stage)
    stages = {} if validation_stages is None else require_exact_keys(
        validation_stages, _TARGETS, "Apple campaign validation stages")
    selected_stages = {}
    if package_stage is not None:
        selected_stages["package"] = Path(package_stage)
    for target in stages:
        selected_stages[target] = Path(stages[target])
    stage_inventories = {}
    for name, selected_stage in selected_stages.items():
        selected_receipt = package["receipt"] if name == "package" else validations[name]["receipt"]
        selected_phase, selected_target = ("package", "ios") if name == "package" else ("validation", name)
        selected_manifest = verify_output_manifest_identity(selected_stage, "sdk", "sdk-ios",
            selected_phase, selected_target, selected_receipt["productVersion"])
        if selected_manifest["outputs"] != selected_receipt["outputs"]:
            raise ValueError("Selected Apple stage differs from its receipt")
        stage_inventories[name] = regular_file_inventory(selected_stage)
    bindings = [(value, (value["receiptBytes"], value["receiptSha256"], value["objectSha256"],
                          canonical_json_bytes(value["receipt"])))
                for value in (binary, package, *validations.values())]
    policy_before = canonical_json_bytes(policy)
    handoff_before = {target: Path(roots[target]).absolute() for target in _TARGETS}

    def unchanged():
        require_no_signing_secret(os.environ)
        if (regular_file_inventory(stage) != stage_before or canonical_json_bytes(policy) != policy_before
                or any(regular_file_inventory(selected_stages[name]) != before
                       for name, before in stage_inventories.items())
                or set(validation_envelopes) != set(_TARGETS)
                or any(_envelope_binding(validation_envelopes[target]) != selected_before[target]
                       for target in _TARGETS)
                or set(handoffs) != set(_TARGETS)
                or any(Path(roots[target]).absolute() != handoff_before[target] for target in _TARGETS)
                or any((value["receiptBytes"], value["receiptSha256"], value["objectSha256"],
                        canonical_json_bytes(value["receipt"])) != before for value, before in bindings)):
            raise ValueError("Apple campaign selected evidence changed during full replay")

    try:
        with ExitStack() as stack:
            for target in _TARGETS:
                verified = stack.enter_context(verified_apple_validation_handoff(
                    handoff_before[target], target=target,
                    expected_receipt_sha256=validations[target]["receiptSha256"],
                    repository_root=Path(repository), policy_revision=policy_revision, **arguments))
                if verified["receiptBytes"] != validations[target]["receiptBytes"]:
                    raise ValueError("Apple campaign validation differs from the selected receipt")
                if target in stage_inventories and regular_file_inventory(verified["stage"]) != stage_inventories[target]:
                    raise ValueError("Apple campaign validation stage differs from its original handoff")
                original = verified["original"]
                validation_shard = verify_phase_shard(
                    original / "shard", PhaseInstanceId("sdk", "sdk-ios", "validation", target))
                if (validation_shard["receiptBytes"] != validations[target]["receiptBytes"]
                        or validation_shard["objectSha256"] != validations[target]["objectSha256"]):
                    raise ValueError("Apple campaign validation differs from its original shard")
                shard = verify_phase_shard(original / "originals/binary/original/shard", _BINARY)
                if (shard["receiptBytes"] != binary["receiptBytes"]
                        or shard["receiptSha256"] != binary["receiptSha256"]
                        or shard["objectSha256"] != binary["objectSha256"]):
                    raise ValueError("Apple campaign binary differs from the original shard")
                package_original = verified["package"]
                if package_original["receiptBytes"] != package["receiptBytes"]:
                    raise ValueError("Apple campaign validations differ from the selected package lineage")
                if "package" in stage_inventories and regular_file_inventory(package_original["stage"]) != stage_inventories["package"]:
                    raise ValueError("Apple campaign package stage differs from its original handoff")
                package_shard = verify_phase_shard(package_original["original"] / "shard", _PACKAGE)
                if (package_shard["receiptBytes"] != package["receiptBytes"]
                        or package_shard["objectSha256"] != package["objectSha256"]):
                    raise ValueError("Apple campaign package differs from its original shard")
                predecessor = package_original["original"] / "inputs/sdk-sdk-ios-binary-ios"
                if (read_regular_file_bytes(predecessor / "phase-receipt.json") != binary["receiptBytes"]
                        or regular_file_inventory(predecessor / "stage") != stage_before):
                    raise ValueError("Apple campaign binary differs from the package predecessor")
                unchanged()
    finally:
        unchanged()
    return binary["receiptBytes"]


def verify_campaign_apple_family(binary_envelope, binary_stage, package_envelope, package_stage,
        validation_envelopes, validation_stages, metadata_envelope, metadata_stage, handoffs,
        *, package_capture, sdk_capture, metadata_evidence_root, metadata_evidence_records,
        repository, policy_revision, policy):
    """Replay all five selected Apple phases; return exact original receipt bytes.

    The caller independently authenticates every envelope, stage, retained
    package/SDK capture, signed validation handoff, evidence record and policy.
    This function only binds those inputs through existing full original gates.
    """
    from .reuse import _validate_envelope

    require_no_signing_secret(os.environ)
    metadata_id, metadata = _validate_envelope(metadata_envelope)
    if metadata_id != PhaseInstanceId("sdk", "sdk-ios", "metadata", "ios"):
        raise ValueError("Apple campaign requires the exact selected metadata envelope")
    selected = require_exact_keys(validation_envelopes, _TARGETS, "Apple campaign validation envelopes")
    roots = require_exact_keys(handoffs, _TARGETS, "Apple campaign signed handoffs")
    stage_roots = require_exact_keys(validation_stages, _TARGETS, "Apple campaign validation stages")
    evidence = require_exact_keys(metadata_evidence_records, _TARGETS, "Apple campaign metadata evidence records")
    evidence_root = Path(metadata_evidence_root).absolute()
    records = []
    for target in _TARGETS:
        _, value = _validate_envelope(selected[target])
        row = require_exact_keys(evidence[target], {"receiptSha256", "target", "evidenceRoot"},
                                 "Apple campaign metadata evidence record")
        if (row["target"] != target or row["receiptSha256"] != value["receiptSha256"]
                or evidence_root / require_relative_path(row["evidenceRoot"], "Apple campaign handoff") !=
                   Path(roots[target]).absolute()):
            raise ValueError("Apple campaign metadata evidence differs from the selected handoff")
        records.append(dict(row))
    arguments = apple_validation_policy_arguments(policy)
    package_id, package = _validate_envelope(package_envelope)
    if package_id != _PACKAGE:
        raise ValueError("Apple campaign requires the exact selected package envelope")
    binary_id, binary = _validate_envelope(binary_envelope)
    if binary_id != _BINARY:
        raise ValueError("Apple campaign requires the exact selected binary envelope")
    bound = {"binary": _envelope_binding(binary_envelope), "package": _envelope_binding(package_envelope),
             "metadata": _envelope_binding(metadata_envelope),
             **{target: _envelope_binding(selected[target]) for target in _TARGETS}}
    roots_before = {target: Path(roots[target]).absolute() for target in _TARGETS}
    stage_roots_before = {target: Path(stage_roots[target]) for target in _TARGETS}
    evidence_before = canonical_json_bytes(metadata_evidence_records)
    frozen_binary, frozen_package = deepcopy(binary_envelope), deepcopy(package_envelope)
    frozen_validations = {target: deepcopy(selected[target]) for target in _TARGETS}
    policy_bytes = canonical_json_bytes(policy)
    stage_paths = (Path(binary_stage), Path(package_stage), Path(metadata_stage),
                   *(Path(stage_roots[target]) for target in _TARGETS))
    stage_before = tuple(regular_file_inventory(path) for path in stage_paths)
    with tempfile.TemporaryDirectory(prefix="apple-campaign-receipts-") as temporary:
        private = Path(temporary).resolve()
        receipt_paths = {name: private / f"{name}.json" for name in ("package", "metadata", *_TARGETS)}
        for name in ("package", "metadata", *_TARGETS):
            receipt_paths[name].write_bytes(bound[name][1][0])
        with verified_selected_ios_package(package_stage, receipt_paths["package"],
                plan=arguments["plan"], package_capture=package_capture, sdk_capture=sdk_capture,
                keyring=arguments["keyring"], keys_directory=arguments["keys_directory"],
                repository_root=Path(repository), tooling_evidence=arguments["tooling_evidence"],
                tooling_public_key=arguments["tooling_public_key"],
                java_executable=arguments["java_executable"], policy_revision=policy_revision,
                required_trust_domain=arguments["required_trust_domain"],
                tooling_keyring=arguments["tooling_keyring"],
                tooling_keys_directory=arguments["tooling_keys_directory"]) as original_package:
            shard = verify_phase_shard(original_package["original"] / "shard", _PACKAGE)
            if (shard["receiptBytes"] != bound["package"][1][0]
                    or shard["receiptSha256"] != bound["package"][1][1]
                    or shard["objectSha256"] != bound["package"][1][2]):
                raise ValueError("Apple campaign original package differs from its selected object")
        binary_raw = verify_campaign_apple_binary(frozen_binary, binary_stage, frozen_package,
            frozen_validations, roots_before, repository=repository, policy_revision=policy_revision, policy=policy,
            package_stage=package_stage, validation_stages=stage_roots_before)
        if binary_raw != bound["binary"][1][0]:
            raise ValueError("Apple campaign binary replay returned another selected receipt")
        verified, metadata_raw = verify_sdk_apple_metadata_admission(repository=repository,
            metadata_stage=metadata_stage, metadata_receipt=receipt_paths["metadata"],
            validation_receipts={target: receipt_paths[target] for target in _TARGETS},
            evidence_root=evidence_root, evidence_records=records,
            policy_revision=policy_revision, policy=policy)
        if metadata_raw != bound["metadata"][1][0] or canonical_json_bytes(verified) != metadata_raw:
            raise ValueError("Apple campaign metadata differs from the selected receipt")
        if (canonical_json_bytes(policy) != policy_bytes
                or canonical_json_bytes(metadata_evidence_records) != evidence_before
                or set(handoffs) != set(_TARGETS)
                or any(Path(handoffs[target]).absolute() != roots_before[target] for target in _TARGETS)
                or set(validation_stages) != set(_TARGETS)
                or any(Path(validation_stages[target]) != stage_roots_before[target] for target in _TARGETS)
                or set(validation_envelopes) != set(_TARGETS)
                or _envelope_binding(binary_envelope) != bound["binary"]
                or _envelope_binding(package_envelope) != bound["package"]
                or _envelope_binding(metadata_envelope) != bound["metadata"]
                or any(_envelope_binding(validation_envelopes[target]) != bound[target] for target in _TARGETS)
                or any(regular_file_inventory(path) != before
                       for path, before in zip(stage_paths, stage_before))):
            raise ValueError("Apple campaign selected evidence changed during full replay")
    return {"binary": bound["binary"][1][0], "package": bound["package"][1][0],
            "validation": {target: bound[target][1][0] for target in _TARGETS},
            "metadata": bound["metadata"][1][0]}
