"""Authenticate imported native SDK staging against original Runtime products."""

from pathlib import Path
import tempfile
from typing import Any

from .c_abi import (
    C_ABI_PACKAGE_MANIFEST, TARGET_SPECS, _check_identity, _json_bytes,
    c_abi_archive_file_name, portable_verify_c_abi_package_evidence,
)
from .inventory import (
    load_canonical_json_bytes, load_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_integer, require_semver, sha256_bytes,
    snapshot_regular_tree,
)
from .sdk_compatibility import load_sdk_compatibility_request, produce_sdk_compatibility
from .receipt import validate_phase_receipt, verify_output_manifest_identity
from .registry import NATIVE_BINDINGS


INDEX_NAME = "codex-agent-native-wrapper-sdks.json"
_LIMIT = 16 * 1024 * 1024
_POLICIES = {"mach-o": "macos.exports", "elf": "linux.map", "pe": "windows.def"}


def verify_staged_native_sdk_inputs(
    staged_sdks: Path, compatibility_request: Path, runtime_stage_root: Path,
) -> dict[str, Any]:
    """Verify all five staged targets without compiling or trusting their index.

    Original Runtime receipt/attestation validation is performed by the existing
    compatibility producer. Portable C-ABI inspection then derives the exact
    expected staging bytes from those authenticated package/validation inputs.
    The returned index is ordinary provenance-bearing data, never admission.
    Its root producer describes staging, not the original Runtime producers.
    """
    source = Path(staged_sdks)
    runtime_source = Path(runtime_stage_root)
    request = Path(compatibility_request)
    request_bytes = read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True)
    before = regular_file_inventory(source)
    runtime_before = regular_file_inventory(runtime_source)
    with tempfile.TemporaryDirectory(prefix="native-sdk-inputs-") as temporary:
        root = Path(temporary).resolve()
        staged, runtime, expected = root / "staged", root / "runtime", root / "expected"
        snapshot_regular_tree(source, staged)
        snapshot_regular_tree(runtime_source, runtime)
        if regular_file_inventory(staged) != before or regular_file_inventory(runtime) != runtime_before:
            raise ValueError("Native SDK inputs changed during snapshot")
        expected.mkdir()
        captured_request = root / "request.json"
        captured_request.write_bytes(request_bytes)
        compatibility = produce_sdk_compatibility(
            **load_sdk_compatibility_request(captured_request, request_directory=request.parent),
            runtime_stage_root=runtime,
            output=expected / "sdk-compatibility.json",
        )
        compatibility_bytes = (expected / "sdk-compatibility.json").read_bytes()
        index_bytes = read_regular_file_bytes(staged / INDEX_NAME, max_bytes=_LIMIT)
        index = require_exact_keys(load_json_bytes(index_bytes), {
            "schemaVersion", "libraryVersion", "runtimeProductVersion", "sdkVersion",
            "sdkCompatibilitySha256", "producerCommit", "producerTree", "targets",
        }, "Native SDK index")
        if index_bytes != _json_bytes(index) or require_integer(index["schemaVersion"], "Native SDK schema", 1) != 2:
            raise ValueError("Native SDK index encoding or schema mismatch")
        version = require_semver(index["libraryVersion"], "Native SDK library version")
        _check_identity(version, index["producerCommit"], index["producerTree"])
        if (index["sdkVersion"] != compatibility["sdkVersion"]
                or index["runtimeProductVersion"] != compatibility["runtime"]["defaultRuntimeVersion"]
                or index["sdkCompatibilitySha256"] != sha256_bytes(compatibility_bytes).removeprefix("sha256:")):
            raise ValueError("Native SDK index differs from authenticated compatibility")
        records = []
        for target, spec in sorted(TARGET_SPECS.items()):
            classifier = spec.classifier.removeprefix("c-abi-")
            package = runtime / classifier / "package/outputs/c-abi"
            validation = runtime / classifier / "validation/outputs"
            reference = validation / "c-abi-reference"
            evidence = validation / "c-abi" / f"c-abi-package-{classifier}.json"
            evidence_bytes = read_regular_file_bytes(evidence, max_bytes=_LIMIT)
            original = load_json_bytes(evidence_bytes)
            # These original producer fields are already bound to the exact
            # signed validation receipt by produce_sdk_compatibility above.
            report = portable_verify_c_abi_package_evidence(
                target, version, original["producerCommit"], original["producerTree"],
                package / c_abi_archive_file_name(version, target), evidence,
                reference / "include/codex_agent.h", reference / "legal/LICENSE",
                reference / "legal/THIRD_PARTY_NOTICES.md",
                reference / "export-policy" / _POLICIES[spec.format],
                tuple((reference / "consumer").iterdir()), expected / classifier,
            )
            embedded = next(item for item in compatibility["runtime"]["embeddedVariants"]
                            if item["target"] == classifier)
            if "sha256:" + report["librarySha256"] != embedded["runtimeLibrarySha256"]:
                raise ValueError(f"Native SDK library differs from authenticated variant: {classifier}")
            records.append({
                "target": target, "classifier": classifier,
                "archiveSha256": report["archiveSha256"],
                "evidenceSha256": sha256_bytes(evidence_bytes).removeprefix("sha256:"),
                "libraryPath": spec.library_path, "librarySha256": report["librarySha256"],
                "manifestSha256": sha256_bytes((expected / classifier / C_ABI_PACKAGE_MANIFEST).read_bytes()).removeprefix("sha256:"),
                "producerCommit": original["producerCommit"], "producerTree": original["producerTree"],
            })
        if index["targets"] != records:
            raise ValueError("Native SDK index differs from original verified Runtime evidence")
        if regular_file_inventory(staged, excluded_paths=(INDEX_NAME,)) != regular_file_inventory(expected):
            raise ValueError("Native SDK staged bytes differ from authenticated Runtime inputs")
    if (regular_file_inventory(source) != before or regular_file_inventory(runtime_source) != runtime_before
            or read_regular_file_bytes(request, max_bytes=_LIMIT, reject_symlink_parents=True) != request_bytes):
        raise ValueError("Native SDK source inputs changed during verification")
    return index


def verify_native_sdk_package_phase(
    stage_root: Path, receipt_path: Path, compatibility_request: Path,
    runtime_stage_root: Path, staged_sdks: Path,
) -> tuple[dict[str, Any], bytes]:
    """Bind final native package semantics to authenticated content and a receipt.

    This is not upstream plan/execution verification or release admission. The
    caller must separately verify the original receipt's complete planned input
    closure; the return value is ordinary data, not a caller-mintable trust token.
    """
    from ..native_wrappers import verify_native_wrapper_sdk_packages

    stage_root, receipt_path, staged_sdks = map(Path, (stage_root, receipt_path, staged_sdks))
    receipt_bytes = read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True)
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    language = receipt["component"]
    if (receipt["product"] != "sdk" or language not in NATIVE_BINDINGS
            or receipt["phase"] != "package" or receipt["target"] != "desktop"):
        raise ValueError("Native SDK verification requires one native package phase")
    before, sdk_before = regular_file_inventory(stage_root), regular_file_inventory(staged_sdks)
    with tempfile.TemporaryDirectory(prefix="native-sdk-package-") as temporary:
        root = Path(temporary).resolve()
        stage, sdks = root / "stage", root / "sdks"
        snapshot_regular_tree(stage_root, stage)
        snapshot_regular_tree(staged_sdks, sdks)
        if regular_file_inventory(stage) != before or regular_file_inventory(sdks) != sdk_before:
            raise ValueError("Native SDK package inputs changed during snapshot")
        manifest = verify_output_manifest_identity(
            stage, "sdk", language, "package", "desktop", receipt["productVersion"],
        )
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError("Native SDK package receipt and stage outputs differ")
        evidence_path = "outputs/evidence/sdk-compatibility.json"
        evidence = [record for record in receipt["outputs"] if record["kind"] == "evidence"]
        if (len(evidence) != 1 or evidence[0]["relativePath"] != evidence_path or any(
            record["kind"] != "package" or not record["relativePath"].startswith(f"outputs/{language}/")
            for record in receipt["outputs"] if record not in evidence
        )):
            raise ValueError("Native SDK package output kinds or paths are invalid")
        index = verify_staged_native_sdk_inputs(sdks, compatibility_request, runtime_stage_root)
        if index["sdkVersion"] != receipt["productVersion"]:
            raise ValueError("Native SDK authenticated version differs from package receipt")
        if (stage / evidence_path).read_bytes() != (sdks / "sdk-compatibility.json").read_bytes():
            raise ValueError("Native SDK evidence differs from authenticated compatibility")
        verify_native_wrapper_sdk_packages(stage / "outputs", sdks, receipt["productVersion"], language)
    if (regular_file_inventory(stage_root) != before or regular_file_inventory(staged_sdks) != sdk_before
            or read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True) != receipt_bytes):
        raise ValueError("Native SDK package sources changed during verification")
    return receipt, receipt_bytes
