"""Bind selected Android phases to official Firebase and retained metadata replay.

The protected caller authenticates the selected carrier, original upload pins,
Contract/tooling policy and metadata evidence root. This grants no release trust.
"""

from pathlib import Path
import os
import tempfile

from .inventory import canonical_json_bytes, read_regular_file_bytes, regular_file_inventory, require_exact_keys
from .receipt import verify_output_manifest_identity
from .registry import PhaseInstanceId
from .restore import verify_phase_shard
from .reuse import _validate_envelope
from .sdk_android_metadata_admission import AndroidMetadataAdmission, _policy_arguments
from .sdk_package import _require_capability_output_separate
from .signing_isolation import require_no_signing_secret


_IDS = {phase: PhaseInstanceId("sdk", "sdk-android", phase, "android")
        for phase in ("binary", "package", "validation", "metadata")}
_ORIGINAL_KEYS = {
    "validation_artifact_id", "validation_artifact_sha256", "trusted_workflow_sha",
    "trusted_android_workflow_sha", "expected_original_run_id", "expected_original_run_attempt",
    "compatibility_request", "binary_contract_evidence", "trusted_source_commit",
    "trusted_source_tree", "tooling_evidence", "tooling_public_key", "java_executable",
    "apkanalyzer_executable", "required_trust_domain", "tooling_keyring", "tooling_keys_directory",
}
_COMMON_POLICY = {
    "compatibility_request", "binary_contract_evidence", "trusted_source_commit",
    "trusted_source_tree", "tooling_evidence", "tooling_public_key", "java_executable",
    "apkanalyzer_executable", "required_trust_domain", "tooling_keyring", "tooling_keys_directory",
}


def verify_campaign_android_family(*, envelopes, stages, receipts, plan, repository,
        original_validation, metadata_evidence_root, metadata_evidence_records,
        metadata_policy, policy_revision, token, environ=None):
    """Replay four selected phases; return their immutable original receipt bytes.

    Original-validation fields and metadata policy are independent caller inputs.
    The observed upload cannot supply either one. Maven binary/package semantic
    admission remains with the separate Maven family verifier.
    """
    if __package__ == "products":
        from sdk_android_firebase_original import verified_original_android_firebase_validation
    else:
        from ..sdk_android_firebase_original import verified_original_android_firebase_validation

    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    selected = require_exact_keys(envelopes, set(_IDS), "Android campaign envelopes")
    stage_source = require_exact_keys(stages, set(_IDS), "Android campaign stages")
    receipt_source = require_exact_keys(receipts, {"binary", "package"},
                                        "Android campaign predecessor receipts")
    stage_paths = {name: Path(value) for name, value in stage_source.items()}
    receipt_paths = {name: Path(value) for name, value in receipt_source.items()}
    original = require_exact_keys(original_validation, _ORIGINAL_KEYS,
                                  "Independent Android original validation control")
    policy = _policy_arguments(metadata_policy)
    expected_paths = {"plan": Path(plan), "package_stage": stage_paths["package"],
                      "package_receipt": receipt_paths["package"],
                      "binary_stage": stage_paths["binary"],
                      "binary_receipt": receipt_paths["binary"]}
    if any(policy[name] != path for name, path in expected_paths.items()):
        raise ValueError("Android metadata policy differs from the selected predecessors")
    if any(canonical_json_bytes(policy[name] if not isinstance(policy[name], Path) else str(policy[name])) !=
           canonical_json_bytes(value if not isinstance(value, Path) else str(value))
           for name, value in original.items() if name in _COMMON_POLICY):
        raise ValueError("Android metadata and original validation caller authority differ")
    rows = metadata_evidence_records
    if not isinstance(rows, (list, tuple)) or len(rows) != 1:
        raise ValueError("Android campaign requires exactly one original metadata evidence record")
    bindings = {}
    inventories = {}
    versions = set()

    def binding(name):
        identity, value = _validate_envelope(selected[name])
        if identity != _IDS[name]:
            raise ValueError("Android campaign selected the wrong phase identity")
        return (value["receiptBytes"], value["receiptSha256"], value["objectSha256"],
                canonical_json_bytes(value["receipt"]))

    for name in _IDS:
        bindings[name] = binding(name)
        value = selected[name]["receipt"]
        versions.add(value["productVersion"])
        manifest = verify_output_manifest_identity(stage_paths[name], "sdk", "sdk-android", name,
                                                   "android", value["productVersion"])
        if manifest["outputs"] != value["outputs"]:
            raise ValueError("Android campaign selected stage differs from its receipt")
        inventories[name] = regular_file_inventory(stage_paths[name])
    if len(versions) != 1:
        raise ValueError("Android campaign requires one exact SDK version")
    for name, path in receipt_paths.items():
        if read_regular_file_bytes(path, reject_symlink_parents=True) != bindings[name][0]:
            raise ValueError("Android campaign predecessor receipt differs from selected bytes")
    policy_before = canonical_json_bytes(metadata_policy)
    original_before = canonical_json_bytes({name: str(value) if isinstance(value, Path) else value
                                            for name, value in original.items()})
    records_before = canonical_json_bytes(rows)
    evidence_root = Path(metadata_evidence_root)
    evidence_before = regular_file_inventory(evidence_root, allow_empty=True)

    def unchanged():
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        if (any(binding(name) != bindings[name] or
                regular_file_inventory(stage_paths[name]) != inventories[name] for name in _IDS)
                or set(envelopes) != set(_IDS)
                or set(stage_source) != set(_IDS)
                or any(Path(stage_source[name]) != stage_paths[name] for name in _IDS)
                or set(receipt_source) != {"binary", "package"}
                or any(Path(receipt_source[name]) != receipt_paths[name] for name in receipt_paths)
                or any(read_regular_file_bytes(path, reject_symlink_parents=True) != bindings[name][0]
                       for name, path in receipt_paths.items())
                or canonical_json_bytes(metadata_policy) != policy_before
                or canonical_json_bytes({name: str(value) if isinstance(value, Path) else value
                                         for name, value in original.items()}) != original_before
                or canonical_json_bytes(rows) != records_before
                or regular_file_inventory(evidence_root, allow_empty=True) != evidence_before):
            raise ValueError("Android campaign selected evidence or caller authority changed")

    unchanged()
    try:
        with tempfile.TemporaryDirectory(prefix="campaign-android-original-") as temporary:
            private = Path(temporary).resolve()
            receipt = private / "validation-receipt.json"
            _require_capability_output_separate(private, (repository, plan, evidence_root,
                *stage_paths.values(), *receipt_paths.values(),
                *(value for value in original.values() if isinstance(value, Path)),
                *(value for value in policy.values() if isinstance(value, Path))))
            receipt.write_bytes(bindings["validation"][0])
            with verified_original_android_firebase_validation(
                    plan, receipt, repository_root=repository, environ=environment, token=token,
                    package_stage=stage_paths["package"], package_receipt=receipt_paths["package"],
                    binary_stage=stage_paths["binary"], binary_receipt=receipt_paths["binary"],
                    policy_revision=policy_revision, **original) as held:
                shard = verify_phase_shard(Path(held["original"]) / "shard", _IDS["validation"])
                if (held["receiptBytes"] != bindings["validation"][0]
                        or any(shard[name] != value for name, value in (
                            ("receiptBytes", bindings["validation"][0]),
                            ("receiptSha256", bindings["validation"][1]),
                            ("objectSha256", bindings["validation"][2]),
                            ("buildKey", selected["validation"]["receipt"]["buildKey"])))
                        or regular_file_inventory(Path(held["stage"])) != inventories["validation"]
                        or regular_file_inventory(Path(held["capture"]) / "original") !=
                           regular_file_inventory(policy["validation_capture"] / "original")):
                    raise ValueError("Android official original differs from selected validation or metadata lineage")
                unchanged()
                AndroidMetadataAdmission(metadata_evidence_root, rows, repository=repository,
                    policy_revision=policy_revision, policy=metadata_policy).verify_metadata(
                        selected["metadata"], [selected["validation"]])
                unchanged()
            unchanged()
            if read_regular_file_bytes(receipt, reject_symlink_parents=True) != bindings["validation"][0]:
                raise ValueError("Android campaign private receipt changed during replay")
    finally:
        unchanged()
    return {name: bindings[name][0] for name in _IDS}
