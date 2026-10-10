"""Concrete receipt-bound admission through the complete Apple handoff gate."""

from pathlib import Path
import os
import re
import tempfile

from .inventory import (
    canonical_json_bytes, publish_regular_tree, regular_file_inventory, require_exact_keys,
    require_regular_directory, require_string, snapshot_regular_tree,
)
from .sdk_apple_validation_attestation import verified_apple_validation_handoff
from .sdk_apple_validation_inputs import load_sdk_apple_validation_evidence, rebase_sdk_apple_validation_records
from .sdk_package import _require_capability_output_separate
from .signing_isolation import require_no_signing_secret


_PATHS = {
    "plan": "plan", "attestationPublicKey": "attestation_public_key",
    "keyring": "keyring", "keysDirectory": "keys_directory",
    "toolingEvidence": "tooling_evidence", "toolingPublicKey": "tooling_public_key",
    "javaExecutable": "java_executable", "toolingKeyring": "tooling_keyring",
    "toolingKeysDirectory": "tooling_keys_directory",
}


def apple_validation_policy_arguments(policy):
    """Parse caller-owned paths/trust, without selecting or authenticating keys.

    A release attestation may omit its explicit public key: the full handoff
    must then resolve the signed key identity against the caller's pinned
    keyring. Development attestations always require an explicit caller key.
    """
    policy = require_exact_keys(policy, {*_PATHS, "attestationTrustDomain", "toolingTrustDomain"},
                                "Apple validation caller policy")
    for name in ("attestationTrustDomain", "toolingTrustDomain"):
        if type(policy[name]) is not str or policy[name] not in {"development", "release"}:
            raise ValueError("Apple admission requires explicit caller trust domains")
    optional = ("toolingKeyring", "toolingKeysDirectory")
    if (policy["toolingTrustDomain"] == "release" and any(policy[name] is None for name in optional)
            or policy["toolingTrustDomain"] == "development" and any(policy[name] is not None for name in optional)):
        raise ValueError("Apple tooling trust requires the exact caller keyring pair")
    arguments = {}
    for field, name in _PATHS.items():
        if policy[field] is None and (field in optional or
                (field == "attestationPublicKey" and policy["attestationTrustDomain"] == "release")):
            arguments[name] = None
            continue
        path = Path(require_string(policy[field], f"Apple caller {field}"))
        if not path.is_absolute():
            raise ValueError("Apple caller policy paths must be absolute")
        arguments[name] = path
    return {**arguments, "attestation_trust_domain": policy["attestationTrustDomain"],
            "required_trust_domain": policy["toolingTrustDomain"]}


class AppleValidationAdmission:
    """Run signature AND original semantic replay without caching acceptance.

    The caller owns the selected envelope, repository revision and all policy
    paths. Transported observations and signing metadata cannot select policy.
    Successful return occurs only after the complete handoff context exits.
    """

    def __init__(self, root, records, *, repository, policy_revision, policy):
        if type(policy_revision) is not str or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", policy_revision) is None:
            raise ValueError("Apple admission requires an exact caller policy revision")
        arguments = apple_validation_policy_arguments(policy)
        self._root = Path(root).absolute()
        self._records = {record["receiptSha256"]: record for record in
                         rebase_sdk_apple_validation_records(records, self._root, self._root)}
        self._arguments = {**arguments, "repository_root": Path(repository), "policy_revision": policy_revision}
        self._policy = {**policy}

    def verify_metadata(self, envelope, validation_envelopes):
        """Verify exact joined bytes after lookup has authenticated the phase object."""
        from .reuse import _validate_envelope
        from .sdk_apple_metadata_admission import verify_sdk_apple_metadata_receipt_admission

        require_no_signing_secret(os.environ)
        instance, envelope = _validate_envelope(envelope)
        if (instance.product, instance.component, instance.phase, instance.target) != (
                "sdk", "sdk-ios", "metadata", "ios"):
            raise ValueError("Apple metadata admission requires the exact metadata envelope")
        def binding(value):
            return (value["receiptBytes"], value["receiptSha256"], value["objectSha256"],
                    canonical_json_bytes(value["receipt"]))

        selected = [(envelope, binding(envelope))]
        originals = {}
        for value in validation_envelopes:
            identity, value = _validate_envelope(value)
            if ((identity.product, identity.component, identity.phase) != ("sdk", "sdk-ios", "validation")
                    or identity.target not in ("ios-arm64", "ios-simulator-arm64")
                    or identity.target in originals):
                raise ValueError("Apple metadata requires exact unique validation predecessors")
            originals[identity.target] = value["receiptBytes"]
            selected.append((value, binding(value)))
        if set(originals) != {"ios-arm64", "ios-simulator-arm64"}:
            raise ValueError("Apple metadata requires both original validation predecessors")
        raw = envelope["receiptBytes"]
        with tempfile.TemporaryDirectory(prefix="apple-metadata-receipts-") as temporary:
            root = Path(temporary).resolve()
            paths = {target: root / f"{target}.json" for target in originals}
            for target, path in paths.items():
                path.write_bytes(originals[target])
            verified, verified_bytes = verify_sdk_apple_metadata_receipt_admission(
                repository=self._arguments["repository_root"], metadata_receipt_bytes=raw,
                validation_receipts=paths, evidence_root=self._root,
                evidence_records=list(self._records.values()),
                policy_revision=self._arguments["policy_revision"], policy=self._policy)
            if verified_bytes != raw or canonical_json_bytes(verified) != raw:
                raise ValueError("Apple metadata full gate returned a different original receipt")
        require_no_signing_secret(os.environ)
        if any(binding(value) != original for value, original in selected):
            raise ValueError("Apple metadata or predecessor envelope changed during admission")

    def verify(self, envelope):
        require_no_signing_secret(os.environ)
        # Local import preserves the existing envelope validator without an
        # import cycle when the reuse engine constructs this admission object.
        from .reuse import _validate_envelope

        instance, envelope = _validate_envelope(envelope)
        if ((instance.product, instance.component, instance.phase) != ("sdk", "sdk-ios", "validation")
                or instance.target not in ("ios-arm64", "ios-simulator-arm64")):
            raise ValueError("Apple admission requires an exact SDK iOS validation envelope")
        raw, digest = envelope["receiptBytes"], envelope["receiptSha256"]
        record = self._records.get(digest)
        if record is None or record["target"] != instance.target:
            raise ValueError("Apple validation admission lacks the exact original receipt/target evidence")
        with verified_apple_validation_handoff(self._root / record["evidenceRoot"],
                expected_receipt_sha256=digest, target=instance.target, **self._arguments) as verified:
            if verified["receiptBytes"] != raw or canonical_json_bytes(verified["receipt"]) != raw:
                raise ValueError("Apple validation handoff differs from the selected envelope")
        require_no_signing_secret(os.environ)
        if (envelope["receiptBytes"] != raw or envelope["receiptSha256"] != digest
                or canonical_json_bytes(envelope["receipt"]) != raw
                or verified["receiptBytes"] != raw or canonical_json_bytes(verified["receipt"]) != raw):
            raise ValueError("Apple validation receipt changed before admission completed")


def stage_collected_apple_validation(shard_root, carrier_root, destination, *,
        target, repository, policy_revision, policy):
    """Admit one selected shard's separately captured carrier, then retain it.

    The collector authenticates/elects the worker shard and carrier upload first.
    This adds the mandatory signature AND complete semantic replay before success;
    structural storage or a successful signer job alone cannot replace this gate.
    """
    from .registry import PhaseInstanceId
    from .restore import verify_phase_shard

    if target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("Apple collection requires an exact validation target")
    arguments = apple_validation_policy_arguments(policy)
    shard_root, carrier_root, destination = map(lambda value: Path(value).absolute(),
                                               (shard_root, carrier_root, destination))
    inputs = [shard_root, carrier_root, Path(repository),
              *(value for value in arguments.values() if isinstance(value, Path))]

    def output_safe():
        _require_capability_output_separate(destination, inputs)
        if destination.exists() or destination.is_symlink():
            raise ValueError("Collected Apple evidence destination must not exist")
        for parent in destination.parents:
            if parent.exists() or parent.is_symlink():
                require_regular_directory(parent, "Collected Apple evidence output ancestry")

    output_safe()
    policy_bytes = canonical_json_bytes(policy)
    instance = PhaseInstanceId("sdk", "sdk-ios", "validation", target)
    selected = verify_phase_shard(shard_root, instance)
    before = {path: regular_file_inventory(path, allow_empty=True) for path in (shard_root, carrier_root)}
    with tempfile.TemporaryDirectory(prefix="collected-apple-validation-") as temporary:
        captured = Path(temporary).resolve() / "carrier"
        snapshot_regular_tree(carrier_root, captured, allow_empty=True)

        def unchanged():
            if (canonical_json_bytes(policy) != policy_bytes
                    or any(regular_file_inventory(path, allow_empty=True) != inventory
                           for path, inventory in before.items())
                    or regular_file_inventory(captured, allow_empty=True) != before[carrier_root]
                    or verify_phase_shard(shard_root, instance) != selected):
                raise ValueError("Collected Apple shard, carrier or policy changed during admission")

        unchanged()
        records = load_sdk_apple_validation_evidence(captured)
        if (len(records) != 1 or records[0]["receiptSha256"] != selected["receiptSha256"]
                or records[0]["target"] != target):
            raise ValueError("Collected Apple carrier differs from its selected original shard")
        AppleValidationAdmission(captured, records, repository=repository,
            policy_revision=policy_revision, policy=policy).verify({
                name: selected[name] for name in ("receipt", "receiptBytes", "receiptSha256", "objectSha256")})
        unchanged()
        output_safe()
        publish_regular_tree(captured, destination, allow_empty=True)
    return records
