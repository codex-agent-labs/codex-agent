"""Verify original SDK package inputs using the existing product planner."""

from pathlib import Path
import subprocess
import tempfile
from typing import Any

from .contract import verify_contract_bundle
from .contract_projection import verify_contract_component_projection
from .inventory import (
    git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_semver, run_git, snapshot_regular_tree,
)
from .plan import (
    NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST,
    _contract_projection_from_request, plan_phase,
)
from .receipt import validate_phase_receipt, write_output_manifest
from .registry import (
    NATIVE_BINDINGS, PhaseInstanceId, phase_instance_dependencies, required_contract_components,
)
from .sdk_compatibility import load_sdk_compatibility_request
from .sdk_inputs import COMPATIBILITY_NAME, REQUEST_NAME, _copy_file, stage_sdk_inputs
from .selection import phase_git_inventory


_LIMIT = 16 * 1024 * 1024


def _receipt(path: Path) -> tuple[dict[str, Any], bytes]:
    contents = read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)
    return validate_phase_receipt(load_canonical_json_bytes(contents)), contents


def _instance(receipt: dict[str, Any]) -> PhaseInstanceId:
    return PhaseInstanceId(*(receipt[key] for key in ("product", "component", "phase", "target")))


def _verify_plan(repository: Path, receipt: dict[str, Any], versions: dict[str, str], upstream: list, projection) -> None:
    """Replay the sole planner from original Git inputs, never receipt-supplied hashes."""
    commit, tree = receipt["producer"]["commit"], receipt["producer"]["tree"]
    try:
        actual_commit = run_git(repository, "rev-parse", f"{commit}^{{commit}}").strip()
        actual_tree = run_git(repository, "rev-parse", f"{commit}^{{tree}}").strip()
    except subprocess.CalledProcessError as error:
        raise ValueError("SDK receipt original source commit is unavailable") from error
    if actual_commit != commit or actual_tree != tree:
        raise ValueError("SDK receipt original commit/tree differs from repository history")
    version_bytes = git_regular_blob_bytes(repository, commit, "gradle/release/versions/sdk.txt", max_bytes=256)
    if version_bytes != (require_semver(receipt["productVersion"], "SDK product version") + "\n").encode():
        raise ValueError("SDK receipt version differs from its original source version")
    result = plan_phase(
        _instance(receipt), inventory=phase_git_inventory(repository, commit, _instance(receipt)),
        versions=versions, upstream_receipts=upstream,
        toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
        flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1,
        contract_projection=projection,
    )
    if receipt["inputs"] != result["inputs"] or receipt["buildKey"] != result["buildKey"]:
        raise ValueError("SDK receipt inputs/build key differ from its original authenticated plan")


def verify_sdk_package_inputs(
    repository: Path, stage_root: Path, receipt_path: Path, compatibility_request: Path,
    *, runtime_stage_root: Path | None = None, staged_sdks: Path | None = None,
    binary_stage_root: Path | None = None, binary_receipt_path: Path | None = None,
    binary_contract_evidence: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Verify package semantics, original artifacts and the complete source-input plan.

    This proves content/input binding, not that a claimed CI run actually ran.
    Hosted execution provenance, per-language behavior receipts and protected
    release admission remain separate mandatory checks. No token is minted here.
    """
    repository = Path(repository)
    stage_root = Path(stage_root)
    receipt, original = _receipt(receipt_path)
    instance = _instance(receipt)
    native = instance.component in NATIVE_BINDINGS
    if instance.product != "sdk" or instance.phase != "package" or (
        not native and instance.component not in {"sdk-core", "sdk-android", "sdk-ios"}
    ):
        raise ValueError("SDK input verification requires a native or Maven package phase")
    if native:
        if runtime_stage_root is None or staged_sdks is None or any(value is not None for value in (
            binary_stage_root, binary_receipt_path, binary_contract_evidence,
        )):
            raise ValueError("Native SDK input verification requires only its Runtime staging inputs")
    elif binary_stage_root is None or binary_receipt_path is None or binary_contract_evidence is None or \
            runtime_stage_root is not None or staged_sdks is not None:
        raise ValueError("Maven SDK input verification requires its original binary and Contract evidence")

    with tempfile.TemporaryDirectory(prefix="sdk-package-plan-") as temporary:
        root = Path(temporary).resolve()
        original_inventory = regular_file_inventory(stage_root)
        stage = root / "package-stage"
        snapshot_regular_tree(stage_root, stage)
        if regular_file_inventory(stage) != original_inventory:
            raise ValueError("SDK package stage changed during input snapshot")
        captured_receipt = root / "package-receipt.json"
        captured_receipt.write_bytes(original)
        handoff = root / "inputs"
        stage_sdk_inputs(Path(compatibility_request), handoff)
        arguments = load_sdk_compatibility_request(handoff / REQUEST_NAME)
        compatibility = load_canonical_json_bytes((handoff / COMPATIBILITY_NAME).read_bytes())
        aggregate = load_canonical_json_bytes(arguments["runtime_manifest"].read_bytes())
        versions = {
            "sdk": compatibility["sdkVersion"], "contract": compatibility["contract"]["version"],
            "runtime-release": aggregate["runtimeVersion"],
            "runtime-compatibility": aggregate["runtimeCompatibilityVersion"],
        }
        if receipt["productVersion"] != versions["sdk"]:
            raise ValueError("SDK receipt version differs from authenticated selected products")
        contract, contract_bytes = _receipt(arguments["contract_metadata_receipt"])
        upstream = {_instance(contract): contract}
        for path in [arguments["runtime_metadata_receipt"], *(
            path for phases in arguments["variant_phase_receipts"].values() for path in phases.values()
        )]:
            value, _ = _receipt(path)
            upstream[_instance(value)] = value
        # Reconstitute the deterministic metadata stage from the exact original
        # payload/receipt; no producer evidence or reusable payload is rewritten.
        contract_stage = root / "contract-stage"
        _copy_file(arguments["contract_payload"], contract_stage / "outputs" / arguments["contract_payload"].name)
        write_output_manifest(contract_stage, "contract", "contract", "metadata", "common",
                              versions["contract"], {"contract-bundle": "outputs"})
        projection = verify_contract_component_projection(
            contract_stage, contract_bytes, arguments["contract_attestation"],
            arguments["contract_attestation_signature"], arguments["contract_public_key"],
            expected_trust_domain=arguments["required_trust_domain"], expected_contract_version=versions["contract"],
            required_components=required_contract_components(instance),
            keyring=arguments["contract_keyring"], keys_directory=arguments["contract_keys_directory"],
        )
        if native:
            from .sdk_native import verify_native_sdk_package_phase
            verified, verified_bytes = verify_native_sdk_package_phase(
                stage, captured_receipt, handoff / REQUEST_NAME, runtime_stage_root, staged_sdks,
            )
        else:
            from .sdk_maven import verify_packaged_sdk_maven_phase, verify_sdk_maven_binary_predecessor
            if binary_contract_evidence.get("expectedTrustDomain") != arguments["required_trust_domain"]:
                raise ValueError("SDK binary Contract evidence cannot change the required trust domain")
            verified, verified_bytes = verify_packaged_sdk_maven_phase(stage, captured_receipt, handoff / REQUEST_NAME)
            binary, _ = verify_sdk_maven_binary_predecessor(
                binary_stage_root, binary_receipt_path, stage, captured_receipt, handoff / COMPATIBILITY_NAME,
            )
            binary_projection = _contract_projection_from_request(_instance(binary), versions, binary_contract_evidence)
            binary_contract, _ = _receipt(Path(binary_contract_evidence["phaseReceipt"]))
            _verify_plan(repository, binary, versions, [binary_contract], binary_projection)
            manifest = verify_contract_bundle(arguments["contract_payload"])
            if any(record["sha256"] != manifest["components"][record["component"]]["sha256"]
                   for record in binary_projection.receipt_value()["componentDigests"]):
                raise ValueError("SDK binary original Contract components differ from package-selected Contract")
            upstream[_instance(binary)] = binary
        if verified != receipt or verified_bytes != original:
            raise ValueError("SDK package receipt changed during semantic verification")
        _verify_plan(repository, receipt, versions,
                     [upstream[identity] for identity in phase_instance_dependencies(instance)], projection)
    if _receipt(receipt_path)[1] != original or regular_file_inventory(stage_root) != original_inventory:
        raise ValueError("SDK package stage or receipt changed during input verification")
    return receipt, original
