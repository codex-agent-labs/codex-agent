"""Original Apple metadata admission through both complete signed handoffs.

No structural carrier or deterministic projection grants authority here. Each
target is independently signature-verified and fully replayed by the existing
handoff, including its original package, binary, sources and native evidence.
"""

from contextlib import ExitStack, contextmanager
import os
from pathlib import Path
import re
import subprocess

from .inventory import (
    canonical_json_bytes, git_product_versions, load_canonical_json_bytes,
    read_regular_file_bytes, require_array, require_exact_keys, require_relative_path, run_git, sha256_bytes,
)
from .plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase
from .receipt import output_inventory_digest, validate_phase_receipt, verify_output_manifest_identity
from .registry import PhaseInstanceId
from .sdk_apple_content import _input_inventory
from .sdk_apple_metadata import OUTPUT_KIND, OUTPUT_PATH, apple_metadata_content
from .sdk_apple_validation_admission import apple_validation_policy_arguments
from .sdk_apple_validation_attestation import verified_apple_validation_handoff
from .sdk_apple_validation_inputs import rebase_sdk_apple_validation_records
from .selection import phase_git_inventory
from .signing_isolation import require_no_signing_secret


_TARGETS = ("ios-arm64", "ios-simulator-arm64")
_VALIDATION_PATH = "outputs/validation/apple-validation.json"
_LIMIT = 16 * 1024 * 1024
_INSTANCE = PhaseInstanceId("sdk", "sdk-ios", "metadata", "ios")


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _receipt(raw, phase, target):
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
            "sdk", "sdk-ios", phase, target):
        raise ValueError("Apple metadata original receipt has the wrong identity")
    return receipt


def _stage(stage, receipt, kind, path):
    manifest = verify_output_manifest_identity(stage, "sdk", "sdk-ios", receipt["phase"],
                                               receipt["target"], receipt["productVersion"])
    if (manifest["outputs"] != receipt["outputs"] or len(manifest["outputs"]) != 1
            or manifest["outputs"][0]["kind"] != kind or manifest["outputs"][0]["relativePath"] != path):
        raise ValueError("Apple metadata stage differs from the exact original receipt output")
    return load_canonical_json_bytes(_read(Path(stage) / path))


@contextmanager
def verified_sdk_apple_metadata_inputs(*, repository, validation_receipts, evidence_root,
                                       evidence_records, policy_revision, policy):
    """Hold both full gates and the common original package through caller use.

    Returned paths are private handoff paths valid only inside this context.
    Distinct validation producers are permitted; both must have consumed the
    very same original package receipt, not merely similar package contents.
    """
    require_no_signing_secret(os.environ)
    if not isinstance(policy_revision, str) or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", policy_revision):
        raise ValueError("Apple metadata requires an exact caller policy revision")
    root = Path(evidence_root).absolute()
    paths = {target: Path(path) for target, path in
             require_exact_keys(validation_receipts, _TARGETS, "Apple metadata validation receipts").items()}
    originals = {target: _read(path) for target, path in paths.items()}
    policy_bytes, record_bytes = canonical_json_bytes(policy), canonical_json_bytes(evidence_records)
    # Records may be rebased against the checkout or an enclosing artifact.
    # Only referenced entries are inputs, never the entire enclosing root.
    entry_paths = [root / require_relative_path(require_exact_keys(record,
        {"receiptSha256", "target", "evidenceRoot"}, "Apple metadata evidence record")["evidenceRoot"],
        "Apple metadata evidence root") for record in require_array(evidence_records, "Apple metadata evidence records")]
    before = {path: _input_inventory(path, allow_empty=True) for path in entry_paths}
    arguments = apple_validation_policy_arguments(load_canonical_json_bytes(policy_bytes))
    records = {row["receiptSha256"]: row for row in
               rebase_sdk_apple_validation_records(evidence_records, root, root)}
    receipts = {target: _receipt(raw, "validation", target) for target, raw in originals.items()}
    stages, stage_inventories, verified_rows = {}, {}, {}
    package_bytes = None
    package = None

    def unchanged():
        require_no_signing_secret(os.environ)
        if (any(_input_inventory(path, allow_empty=True) != inventory for path, inventory in before.items())
                or canonical_json_bytes(policy) != policy_bytes
                or canonical_json_bytes(evidence_records) != record_bytes
                or any(_read(paths[target]) != raw for target, raw in originals.items())
                or any(canonical_json_bytes(receipts[target]) != raw for target, raw in originals.items())):
            raise ValueError("Apple metadata original receipts, carrier or caller policy changed")
        for target, verified in verified_rows.items():
            if verified["receiptBytes"] != originals[target] or canonical_json_bytes(verified["receipt"]) != originals[target]:
                raise ValueError("Apple metadata full handoff receipt changed")
            if package_bytes is not None and (verified["package"]["receiptBytes"] != package_bytes
                    or canonical_json_bytes(verified["package"]["receipt"]) != package_bytes):
                raise ValueError("Apple metadata common package receipt changed")
        if package is not None and (package["receiptBytes"] != package_bytes
                or canonical_json_bytes(package["receipt"]) != package_bytes):
            raise ValueError("Apple metadata common package receipt changed")

    try:
        with ExitStack() as stack:
            for target in _TARGETS:
                digest = sha256_bytes(originals[target])
                record = records.get(digest)
                if record is None or record["target"] != target:
                    raise ValueError("Apple metadata lacks an exact original validation evidence record")
                verified = stack.enter_context(verified_apple_validation_handoff(
                    root / record["evidenceRoot"], target=target, expected_receipt_sha256=digest,
                    repository_root=Path(repository), policy_revision=policy_revision, **arguments))
                verified_rows[target] = verified
                unchanged()
                current_package = verified["package"]
                current_raw = current_package["receiptBytes"]
                selected_package = _receipt(current_raw, "package", "ios")
                if (canonical_json_bytes(current_package["receipt"]) != current_raw
                        or selected_package["productVersion"] != receipts[target]["productVersion"]):
                    raise ValueError("Apple metadata validation and original package versions differ")
                if package_bytes is None:
                    package_bytes, package = current_raw, current_package
                elif current_raw != package_bytes:
                    raise ValueError("Apple metadata validations have different original package lineage")
                stages[target] = Path(verified["stage"])
                stage_inventories[target] = _input_inventory(stages[target], allow_empty=False)
            package_stage = Path(package["stage"])
            package_inventory = _input_inventory(package_stage, allow_empty=False)
            package_manifest = verify_output_manifest_identity(package_stage, "sdk", "sdk-ios", "package", "ios",
                                                               package["receipt"]["productVersion"])
            if package_manifest["outputs"] != package["receipt"]["outputs"]:
                raise ValueError("Apple metadata common package stage differs from its original receipt")
            contents = {target: _stage(stages[target], receipts[target], "apple-validation-content", _VALIDATION_PATH)
                        for target in _TARGETS}
            content = apple_metadata_content(sdk_version=package["receipt"]["productVersion"],
                package_outputs_digest=output_inventory_digest(package_manifest["outputs"]),
                contract_digest=contents[_TARGETS[0]]["contractDigest"],
                expected_canonical=contents[_TARGETS[0]]["canonical"], validation_contents=contents)
            content_bytes = canonical_json_bytes(content)
            try:
                unchanged()
                yield {"package_stage": package_stage, "package_receipt": package["receipt"],
                       "package_receipt_bytes": package_bytes,
                       "validation_contents": {target: stages[target] / _VALIDATION_PATH for target in _TARGETS},
                       "validation_receipts": receipts, "validation_receipt_bytes": dict(originals), "content": content}
            finally:
                if (canonical_json_bytes(content) != content_bytes
                        or _input_inventory(package_stage, allow_empty=False) != package_inventory
                        or any(_input_inventory(stages[target], allow_empty=False) != inventory
                               for target, inventory in stage_inventories.items())):
                    raise ValueError("Apple metadata private package or validation contents changed")
                unchanged()
    finally:
        unchanged()


def verify_sdk_apple_metadata_receipt_admission(*, repository, metadata_receipt_bytes,
        validation_receipts, evidence_root, evidence_records, policy_revision, policy):
    """Bind original receipt outputs to full replay; caller verifies object bytes.

    This is not an observed metadata-worker or publication attestation. No
    receipt is minted, product stage written, or host provenance manufactured.
    """
    if type(metadata_receipt_bytes) is not bytes:
        raise ValueError("Apple metadata receipt must be immutable original bytes")
    raw = metadata_receipt_bytes
    receipt = _receipt(raw, "metadata", "ios")
    try:
        with verified_sdk_apple_metadata_inputs(repository=repository, validation_receipts=validation_receipts,
                evidence_root=evidence_root, evidence_records=evidence_records,
                policy_revision=policy_revision, policy=policy) as inputs:
            commit, tree = receipt["producer"]["commit"], receipt["producer"]["tree"]
            try:
                if (run_git(Path(repository), "rev-parse", f"{commit}^{{commit}}").strip() != commit
                        or run_git(Path(repository), "rev-parse", f"{commit}^{{tree}}").strip() != tree):
                    raise ValueError("Apple metadata original source differs from its producer")
            except subprocess.CalledProcessError as error:
                raise ValueError("Apple metadata original source is unavailable") from error
            versions = git_product_versions(Path(repository), commit)
            if versions["sdk"] != receipt["productVersion"] or inputs["content"]["sdkVersion"] != receipt["productVersion"]:
                raise ValueError("Apple metadata version differs from its original Git source or package")
            planned = plan_phase(_INSTANCE, inventory=phase_git_inventory(Path(repository), commit, _INSTANCE),
                versions=versions, upstream_receipts=[inputs["validation_receipts"][target] for target in _TARGETS],
                toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1)
            if planned["inputs"] != receipt["inputs"] or planned["buildKey"] != receipt["buildKey"]:
                raise ValueError("Apple metadata original inputs/build key differ from its authenticated plan")
            content = canonical_json_bytes(inputs["content"])
            expected_outputs = [{"kind": OUTPUT_KIND, "relativePath": OUTPUT_PATH,
                                 "bytes": len(content), "sha256": sha256_bytes(content)}]
            if receipt["outputs"] != expected_outputs:
                raise ValueError("Apple metadata content differs from its fully replayed original validations")
    finally:
        if canonical_json_bytes(receipt) != raw:
            raise ValueError("Apple metadata original receipt changed during admission")
    return receipt, raw


def verify_sdk_apple_metadata_admission(*, repository, metadata_stage, metadata_receipt,
        validation_receipts, evidence_root, evidence_records, policy_revision, policy):
    """Verify stage bytes plus the same receipt-only original admission gate."""
    stage, receipt_path = Path(metadata_stage), Path(metadata_receipt)
    before, raw = _input_inventory(stage, allow_empty=False), _read(receipt_path)
    try:
        receipt, returned = verify_sdk_apple_metadata_receipt_admission(repository=repository,
            metadata_receipt_bytes=raw, validation_receipts=validation_receipts,
            evidence_root=evidence_root, evidence_records=evidence_records,
            policy_revision=policy_revision, policy=policy)
        if returned != raw or canonical_json_bytes(receipt) != raw:
            raise ValueError("Apple metadata admission returned a different original receipt")
        _stage(stage, receipt, OUTPUT_KIND, OUTPUT_PATH)
    finally:
        if _input_inventory(stage, allow_empty=False) != before or _read(receipt_path) != raw:
            raise ValueError("Apple metadata stage or original receipt changed during admission")
    return receipt, raw
