"""Bind a selected Apple binary to both complete original validation handoffs.

This is a family verifier, not release admission. The protected campaign owns
the selected envelopes, restored stage, signed handoff paths and caller policy.
"""

from contextlib import ExitStack
import os
from pathlib import Path

from .inventory import canonical_json_bytes, read_regular_file_bytes, regular_file_inventory, require_exact_keys
from .receipt import verify_output_manifest_identity
from .registry import PhaseInstanceId
from .restore import verify_phase_shard
from .sdk_apple_validation_admission import apple_validation_policy_arguments
from .sdk_apple_validation_attestation import verified_apple_validation_handoff
from .signing_isolation import require_no_signing_secret


_BINARY = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
_PACKAGE = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
_TARGETS = ("ios-arm64", "ios-simulator-arm64")


def verify_campaign_apple_binary(binary_envelope, binary_stage, package_envelope,
        validation_envelopes, handoffs, *, repository, policy_revision, policy):
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
    for target in _TARGETS:
        identity, validations[target] = _validate_envelope(selected[target])
        if identity != PhaseInstanceId("sdk", "sdk-ios", "validation", target):
            raise ValueError("Apple campaign validation envelope has the wrong target")
    if len({str(Path(roots[target]).absolute()) for target in _TARGETS}) != 2:
        raise ValueError("Apple campaign requires two distinct signed handoffs")
    arguments = apple_validation_policy_arguments(policy)
    stage = Path(binary_stage)
    manifest = verify_output_manifest_identity(stage, "sdk", "sdk-ios", "binary", "ios",
                                               binary["receipt"]["productVersion"])
    if manifest["outputs"] != binary["receipt"]["outputs"]:
        raise ValueError("Selected Apple binary stage differs from its receipt")
    stage_before = regular_file_inventory(stage)
    bindings = [(value, (value["receiptBytes"], value["receiptSha256"], value["objectSha256"],
                          canonical_json_bytes(value["receipt"])))
                for value in (binary, package, *validations.values())]
    policy_before = canonical_json_bytes(policy)
    handoff_before = {target: Path(roots[target]).absolute() for target in _TARGETS}

    def unchanged():
        require_no_signing_secret(os.environ)
        if (regular_file_inventory(stage) != stage_before or canonical_json_bytes(policy) != policy_before
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
