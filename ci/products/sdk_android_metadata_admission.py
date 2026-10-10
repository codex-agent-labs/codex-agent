"""Concrete Android metadata admission through the complete retained replay."""

import os
from pathlib import Path
import re
import tempfile

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    read_regular_file_bytes, require_array, require_exact_keys, require_relative_path,
    require_regular_directory, require_sha256, require_string,
)
from .registry import PhaseInstanceId
from .restore import verify_phase_shard
from .sdk_package import _require_capability_output_separate
from .sdk_validation_inputs import _request_inventory
from .signing_isolation import require_no_signing_secret
from . import sdk_android_validation_phase as validation_phase


_METADATA = PhaseInstanceId("sdk", "sdk-android", "metadata", "android")
_VALIDATION = PhaseInstanceId("sdk", "sdk-android", "validation", "android")
_OID = re.compile(r"[0-9a-f]{40}")
_PATHS = {
    "plan": "plan", "validationCapture": "validation_capture",
    "packageStage": "package_stage", "packageReceipt": "package_receipt",
    "binaryStage": "binary_stage", "binaryReceipt": "binary_receipt",
    "compatibilityRequest": "compatibility_request",
    "toolingEvidence": "tooling_evidence",
    "toolingPublicKey": "tooling_public_key",
    "javaExecutable": "java_executable",
    "apkanalyzerExecutable": "apkanalyzer_executable",
    "toolingKeyring": "tooling_keyring",
    "toolingKeysDirectory": "tooling_keys_directory",
}
_POLICY_KEYS = {*_PATHS, "binaryContractEvidence", "trustedSourceCommit",
                "trustedSourceTree", "originalContext", "toolingTrustDomain"}


def _policy_arguments(policy):
    policy = require_exact_keys(policy, _POLICY_KEYS, "Android metadata caller policy")
    trust = policy["toolingTrustDomain"]
    if trust not in {"development", "release"}:
        raise ValueError("Android metadata requires an exact tooling trust domain")
    optional = ("toolingKeyring", "toolingKeysDirectory")
    if ((trust == "release" and any(policy[name] is None for name in optional))
            or (trust == "development" and any(policy[name] is not None for name in optional))):
        raise ValueError("Android metadata tooling trust requires the exact caller keyring pair")
    arguments = {}
    for field, name in _PATHS.items():
        if field in optional and policy[field] is None:
            arguments[name] = None
            continue
        path = Path(require_string(policy[field], f"Android metadata caller {field}"))
        if not path.is_absolute() or path.resolve(strict=True) != path:
            raise ValueError("Android metadata caller paths must be absolute, normalized and non-symbolic")
        arguments[name] = path
    for name in ("trustedSourceCommit", "trustedSourceTree"):
        if type(policy[name]) is not str or _OID.fullmatch(policy[name]) is None:
            raise ValueError("Android metadata requires exact caller source identities")
    # The retained reader validates both fixed-shape objects and every path they
    # select. Canonical copies ensure later caller mutation is still observable.
    arguments.update(
        binary_contract_evidence=load_canonical_json_bytes(
            canonical_json_bytes(policy["binaryContractEvidence"])),
        trusted_source_commit=policy["trustedSourceCommit"],
        trusted_source_tree=policy["trustedSourceTree"],
        original_context=load_canonical_json_bytes(
            canonical_json_bytes(policy["originalContext"])),
        required_trust_domain=trust,
    )
    return arguments


def _binding(envelope):
    return (envelope["receiptBytes"], envelope["receiptSha256"],
            envelope["objectSha256"], canonical_json_bytes(envelope["receipt"]))


def _arguments_view(arguments):
    return canonical_json_bytes({name: str(value) if isinstance(value, Path) else value
                                 for name, value in arguments.items()})


def _returned_view(value):
    return canonical_json_bytes({
        "stage": str(value["stage"]), "receiptPath": str(value["receiptPath"]),
        "receiptBytes": (value["receiptBytes"].hex()
                         if isinstance(value["receiptBytes"], bytes)
                         else value["receiptBytes"]),
        "receipt": value["receipt"],
        "original": str(value["original"]), "capture": str(value["capture"]),
        "transport": value["transport"],
    })


class AndroidMetadataAdmission:
    """Replay one receipt-bound retained carrier without caching acceptance."""

    def __init__(self, root, records, *, repository, policy_revision, policy):
        require_no_signing_secret(os.environ)
        if type(policy_revision) is not str or _OID.fullmatch(policy_revision) is None:
            raise ValueError("Android metadata admission requires an exact policy revision")
        root = Path(root).absolute()
        if root.resolve(strict=True) != root:
            raise ValueError("Android metadata evidence root must be normalized and non-symbolic")
        require_regular_directory(root, "Android metadata evidence root")
        repository = Path(repository).absolute()
        if repository.resolve(strict=True) != repository:
            raise ValueError("Android metadata repository must be normalized and non-symbolic")
        require_regular_directory(repository, "Android metadata repository")
        values = require_array(records, "Android metadata evidence records")
        parsed = []
        for index, value in enumerate(values):
            record = require_exact_keys(
                value, {"receiptSha256", "captureRoot"},
                f"Android metadata evidence records[{index}]")
            digest = require_sha256(record["receiptSha256"], "Android metadata evidence receipt")
            relative = require_relative_path(record["captureRoot"], "Android metadata capture root")
            capture = root / relative
            if capture.resolve(strict=True) != capture:
                raise ValueError("Android metadata capture root escapes or uses symbolic paths")
            require_regular_directory(capture, "Android metadata retained capture")
            parsed.append({"receiptSha256": digest, "captureRoot": relative})
        if (parsed != sorted(parsed, key=lambda value: value["receiptSha256"])
                or len({value["receiptSha256"] for value in parsed}) != len(parsed)
                or len({value["captureRoot"] for value in parsed}) != len(parsed)):
            raise ValueError("Android metadata evidence records must be sorted and unique")
        self._root = root
        self._repository = repository
        self._policy_revision = policy_revision
        self._policy_source = policy
        self._policy_bytes = canonical_json_bytes(policy)
        self._arguments = _policy_arguments(policy)
        self._arguments_bytes = _arguments_view(self._arguments)
        contract_trees, contract_files = validation_phase._contract_sources(
            self._arguments["binary_contract_evidence"])
        self._policy_paths = {
            value for value in self._arguments.values() if isinstance(value, Path)
        } | set(contract_trees.values()) | set(contract_files.values()) | set(
            _request_inventory(self._arguments["compatibility_request"]))
        self._records_source = records
        self._records_bytes = canonical_json_bytes(records)
        self._records = {record["receiptSha256"]: record for record in parsed}

    def verify_metadata(self, envelope, validation_envelopes):
        """Verify the exact metadata and its one selected validation receipt."""
        from .reuse import _validate_envelope
        if __package__ == "products":
            from sdk_android_metadata_original import verified_retained_sdk_android_metadata
        else:
            from ..sdk_android_metadata_original import verified_retained_sdk_android_metadata

        require_no_signing_secret(os.environ)
        identity, metadata = _validate_envelope(envelope)
        if identity != _METADATA:
            raise ValueError("Android metadata admission requires the exact metadata envelope")
        if not isinstance(validation_envelopes, (list, tuple)) or len(validation_envelopes) != 1:
            raise ValueError("Android metadata admission requires exactly one validation predecessor")
        validation_identity, validation = _validate_envelope(validation_envelopes[0])
        if validation_identity != _VALIDATION:
            raise ValueError("Android metadata admission requires the exact Android validation predecessor")
        record = self._records.get(metadata["receiptSha256"])
        if record is None:
            raise ValueError("Android metadata admission lacks the exact retained receipt evidence")
        validation_capture = self._arguments["validation_capture"]
        before_validation_capture = regular_file_inventory(validation_capture, allow_empty=True)

        def validation_capture_unchanged():
            if regular_file_inventory(validation_capture, allow_empty=True) != before_validation_capture:
                raise ValueError("Android metadata validation capture changed during admission")

        try:
            validation_shard = verify_phase_shard(
                validation_capture / "original/shard", _VALIDATION)
            if (validation_shard["receiptBytes"] != validation["receiptBytes"]
                    or validation_shard["receiptSha256"] != validation["receiptSha256"]
                    or validation_shard["objectSha256"] != validation["objectSha256"]
                    or canonical_json_bytes(validation_shard["receipt"]) !=
                       canonical_json_bytes(validation["receipt"])):
                raise ValueError("Android metadata validation capture differs from the selected predecessor")
            selected = ((metadata, _binding(metadata)), (validation, _binding(validation)))
            predecessor_source = validation_envelopes
            before_root = regular_file_inventory(self._root, allow_empty=True)
            raw = metadata["receiptBytes"]
            returned = returned_before = None

            def unchanged():
                require_no_signing_secret(os.environ)
                if (canonical_json_bytes(self._policy_source) != self._policy_bytes
                        or _arguments_view(self._arguments) != self._arguments_bytes
                        or canonical_json_bytes(self._records_source) != self._records_bytes
                        or regular_file_inventory(self._root, allow_empty=True) != before_root
                        or any(_binding(value) != before for value, before in selected)
                        or not isinstance(predecessor_source, (list, tuple))
                        or len(predecessor_source) != 1
                        or _binding(predecessor_source[0]) != selected[1][1]
                        or (returned is not None and _returned_view(returned) != returned_before)):
                    raise ValueError(
                        "Android metadata envelope, evidence or caller policy changed during admission")
                validation_capture_unchanged()

            try:
                unchanged()
                with tempfile.TemporaryDirectory(prefix="android-metadata-admission-") as temporary:
                    private = Path(temporary).resolve()
                    _require_capability_output_separate(
                        private, [self._root, self._repository, *self._policy_paths])
                    receipt = private / "metadata-receipt.json"
                    receipt.write_bytes(raw)
                    with verified_retained_sdk_android_metadata(
                            self._arguments["plan"], metadata_receipt_path=receipt,
                            metadata_capture=self._root / record["captureRoot"],
                            repository_root=self._repository,
                            policy_revision=self._policy_revision,
                            environ=os.environ,
                            **{name: value for name, value in self._arguments.items()
                               if name != "plan"}) as verified:
                        if (verified["receiptBytes"] != raw
                                or canonical_json_bytes(verified["receipt"]) != raw):
                            raise ValueError(
                                "Android metadata full gate returned a different original receipt")
                        original_shard = verify_phase_shard(
                            verified["original"] / "shard", _METADATA)
                        if (original_shard["receiptSha256"] != metadata["receiptSha256"]
                                or original_shard["objectSha256"] != metadata["objectSha256"]):
                            raise ValueError(
                                "Android metadata retained shard differs from the selected envelope")
                        nested = (verified["original"] /
                                  "inputs/sdk-sdk-android-validation-android/phase-receipt.json")
                        if (read_regular_file_bytes(nested, reject_symlink_parents=True) !=
                                validation["receiptBytes"]):
                            raise ValueError(
                                "Android metadata retained validation differs from its selected predecessor")
                        returned = verified
                        returned_before = _returned_view(verified)
                        unchanged()
                    if (read_regular_file_bytes(receipt, reject_symlink_parents=True) != raw
                            or _returned_view(returned) != returned_before):
                        raise ValueError("Android metadata private receipt or replay result changed")
            finally:
                unchanged()
        finally:
            validation_capture_unchanged()
