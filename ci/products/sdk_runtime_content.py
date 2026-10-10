"""Deterministic bootstrap content, emitted only after the full Runtime raw gate.

The raw projector grants no admission; the separate verified projection factory
requires full captured K/R authentication. Original raw compiler/JUnit evidence
and receipts remain mandatory external proof.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import io
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
import zipfile

from .contract_model import (
    _canonical_api_projection, _execution_tree_digest, _verify_extracted_contract_directory,
    validate_contract_manifest,
)
from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_array, require_exact_keys, require_integer,
    require_relative_path, require_sha256, sha256_bytes, snapshot_regular_tree,
)
from .test_results import read_canonical_test_report
from .runtime_adapter_validation import verify_runtime_process_capture


_VERIFIED_NATIVE_RUNTIME = object()


class VerifiedNativeRuntimeProjection:
    """One exact original Runtime receipt authenticated for native SDK key use."""

    __slots__ = ("_receipt", "_value", "_contract", "_verified", "_content")

    def __init__(self, receipt: bytes, digest: str, contract: dict[str, Any], verified: object,
                 content: bytes | None = None):
        if verified is not _VERIFIED_NATIVE_RUNTIME:
            raise TypeError("Native Runtime projection must come from full K/R verification")
        self._receipt = receipt
        self._value = canonical_json_bytes({
            "schemaVersion": 1, "kind": "runtime-native-validation-content",
            "sha256": require_sha256(digest, "Native Runtime content digest"),
            "receiptSha256": sha256_bytes(receipt),
        })
        self._contract = canonical_json_bytes(contract)
        self._verified = verified
        self._content = content

    def receipt_value(self, receipt: dict[str, Any], contract_projection: Any) -> dict[str, Any]:
        from .contract_projection import VerifiedContractProjection
        if self._verified is not _VERIFIED_NATIVE_RUNTIME or type(contract_projection) is not VerifiedContractProjection:
            raise ValueError("Native Runtime projection is not authenticated")
        if canonical_json_bytes(receipt) != self._receipt:
            raise ValueError("Native Runtime projection belongs to another original receipt")
        if self._contract != canonical_json_bytes(_native_contract_identity(contract_projection, receipt["target"])):
            raise ValueError("Native Runtime projection belongs to another Contract content identity")
        return load_canonical_json_bytes(self._value)

    @property
    def target(self) -> str:
        return load_canonical_json_bytes(self._receipt)["target"]

    def output_inventory(self, receipt_sha256: str, outputs: list[dict[str, Any]], *,
                         identity: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Comparison-only content inventory; never a replacement stage or receipt."""
        if self._verified is not _VERIFIED_NATIVE_RUNTIME or self._content is None:
            raise ValueError("Verified native Runtime content is required for comparison")
        value = load_canonical_json_bytes(self._value)
        if receipt_sha256 != sha256_bytes(self._receipt) or value["receiptSha256"] != receipt_sha256:
            raise ValueError("Native Runtime content requires its exact original receipt")
        receipt = load_canonical_json_bytes(self._receipt)
        if identity is not None and any(identity.get(key) != receipt[key] for key in
                ("product", "component", "phase", "target", "productVersion", "buildKey")):
            raise ValueError("Native Runtime comparison identity differs from its original receipt")
        if outputs != receipt["outputs"]:
            raise ValueError("Native Runtime content and original output inventory differ")
        if sha256_bytes(self._content) != value["sha256"]:
            raise ValueError("Native Runtime content digest differs from verified bytes")
        return [{"kind": "runtime-native-validation-content",
                 "relativePath": "outputs/runtime-native-validation-content.json",
                 "bytes": len(self._content), "sha256": value["sha256"]}]


def _native_contract_identity(projection: Any, target: str) -> dict[str, Any]:
    value = projection.receipt_value(include_coverage=target == "macos-arm64")
    components = {item["component"]: item["sha256"] for item in value["componentDigests"]}
    if not {"common", target} <= set(components):
        raise ValueError("Native Runtime projection lacks required Contract components")
    return {
        "contractDigest": value["contractDigest"],
        "componentDigests": {name: components[name] for name in ("common", target)},
        **({"canonicalCoverageDigest": value["canonicalCoverageDigest"]} if target == "macos-arm64" else {}),
    }


def verify_native_runtime_projection(*args: Any, **kwargs: Any) -> VerifiedNativeRuntimeProjection:
    """Mint only after the complete captured K/R gate; never accept a supplied digest."""
    content, receipt = verify_native_runtime_validation_content(*args, **kwargs)
    projection = kwargs.get("contract_projection") if "contract_projection" in kwargs else args[7]
    data = canonical_json_bytes(content)
    return VerifiedNativeRuntimeProjection(receipt, sha256_bytes(data),
        _native_contract_identity(projection, content["target"]), _VERIFIED_NATIVE_RUNTIME, data)


def verify_native_runtime_validation_content(
    target: str, runtime_stage_root: Path, phase_receipts: dict[str, Path],
    variant_payload: Path, attestation: Path, signature: Path, public_key: Path,
    contract_projection: Any, contract_payload: Path, *, required_trust_domain: str,
    keyring: Path | None = None, keys_directory: Path | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Use the same private K/R captures for authentication and semantic reads."""
    with _native_runtime_capture(target, runtime_stage_root, phase_receipts,
                                 variant_payload, contract_payload) as captured:
        runtime, receipts, variant, contract = captured
        return _verify_native_runtime_validation_snapshot(
            target, runtime, receipts, variant, attestation, signature, public_key,
            contract_projection, contract, required_trust_domain=required_trust_domain,
            keyring=keyring, keys_directory=keys_directory,
        )


def verify_native_runtime_presigning_content(
    target: str, runtime_stage_root: Path, phase_receipts: dict[str, Path],
    variant_payload: Path, contract_projection: Any, contract_payload: Path,
) -> dict[str, Any]:
    """Check original unsigned Runtime semantics before any signing-key access.

    The Contract projection remains authenticated. Runtime source/CI authority
    belongs to the protected caller; this ordinary dict grants no admission.
    """
    from .runtime_attestation import _bound_inputs

    with _native_runtime_capture(target, runtime_stage_root, phase_receipts,
                                 variant_payload, contract_payload) as captured:
        runtime, receipt_paths, payload, contract = captured
        variant, receipts, original_bytes, _, _ = _bound_inputs(
            payload, *(receipt_paths[phase] for phase in ("binary", "package", "validation", "metadata")),
            _native_desktop_report(runtime, target),
        )
        # Exact byte binding only, deliberately not an attestation/signature.
        binding = {"phaseReceipts": {phase: sha256_bytes(data) for phase, data in original_bytes.items()}}
        content, _ = _verify_native_runtime_semantics(
            target, runtime, receipt_paths, contract_projection, contract, variant, receipts, binding,
        )
        return content


@contextmanager
def _native_runtime_capture(target, runtime_stage_root, phase_receipts, variant_payload, contract_payload):
    """Both entry points consume and recheck the same exact private originals."""
    from .c_abi import TARGET_SPECS

    targets = {spec.classifier.removeprefix("c-abi-") for spec in TARGET_SPECS.values()}
    if target not in targets or set(phase_receipts) != {"binary", "package", "validation", "metadata"}:
        raise ValueError("Native Runtime content requires one exact target and four original receipts")
    roots = [runtime_stage_root / target / phase for phase in ("package", "validation")]
    before = [regular_file_inventory(root) for root in roots]
    original_receipts = {phase: read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                                       reject_symlink_parents=True)
                         for phase, path in phase_receipts.items()}
    payload_paths = {"variant": Path(variant_payload), "contract": Path(contract_payload)}
    payload_bytes = {name: read_regular_file_bytes(path, max_bytes=1024 * 1024 * 1024,
                                                  reject_symlink_parents=True)
                     for name, path in payload_paths.items()}
    with tempfile.TemporaryDirectory(prefix="runtime-native-inputs-") as temporary:
        root = Path(temporary).resolve()
        runtime = root / "runtime"
        for source, inventory in zip(roots, before, strict=True):
            captured = runtime / target / source.name
            snapshot_regular_tree(source, captured)
            if regular_file_inventory(captured) != inventory:
                raise ValueError("Native Runtime inputs changed during snapshot")
        captured_receipts = {}
        for phase, data in original_receipts.items():
            captured_receipts[phase] = root / f"{phase}-receipt.json"
            captured_receipts[phase].write_bytes(data)
        captured_payloads = {}
        for name, source in payload_paths.items():
            captured_payloads[name] = root / name / source.name
            captured_payloads[name].parent.mkdir()
            captured_payloads[name].write_bytes(payload_bytes[name])
        yield runtime, captured_receipts, captured_payloads["variant"], captured_payloads["contract"]
        if before != [regular_file_inventory(source) for source in roots] or any(
            data != read_regular_file_bytes(phase_receipts[phase], max_bytes=16 * 1024 * 1024,
                                            reject_symlink_parents=True)
            for phase, data in original_receipts.items()
        ):
            raise ValueError("Native Runtime original evidence changed during content verification")
        if before != [regular_file_inventory(runtime / target / source.name) for source in roots] or any(
            data != read_regular_file_bytes(captured_receipts[phase], max_bytes=16 * 1024 * 1024,
                                            reject_symlink_parents=True)
            for phase, data in original_receipts.items()
        ):
            raise ValueError("Native Runtime captured evidence changed during content verification")
        for name, source in payload_paths.items():
            if any(read_regular_file_bytes(path, max_bytes=1024 * 1024 * 1024,
                                           reject_symlink_parents=True) != payload_bytes[name]
                   for path in (source, captured_payloads[name])):
                raise ValueError("Native Runtime original or captured payload changed during content verification")


def _native_desktop_report(runtime_stage_root: Path, target: str) -> Path:
    from .c_abi import TARGET_SPECS
    spec = next(spec for spec in TARGET_SPECS.values() if spec.classifier.removeprefix("c-abi-") == target)
    return runtime_stage_root / target / "validation/outputs/native" / f"desktop-runtime-{spec.target}.json"


def _verify_native_runtime_validation_snapshot(
    target: str, runtime_stage_root: Path, phase_receipts: dict[str, Path],
    variant_payload: Path, attestation: Path, signature: Path, public_key: Path,
    contract_projection: Any, contract_payload: Path, *, required_trust_domain: str,
    keyring: Path | None = None, keys_directory: Path | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Signed admission never falls back to unsigned content verification."""
    from .runtime_attestation import verify_runtime_variant_attestation

    variant, receipts, authenticated = verify_runtime_variant_attestation(
        variant_payload, *(phase_receipts[phase] for phase in ("binary", "package", "validation", "metadata")),
        attestation, signature, public_key, required_trust_domain=required_trust_domain,
        validation_evidence=_native_desktop_report(runtime_stage_root, target),
        keyring=keyring, keys_directory=keys_directory,
    )
    return _verify_native_runtime_semantics(
        target, runtime_stage_root, phase_receipts, contract_projection, contract_payload,
        variant, receipts, authenticated,
    )


def _verify_native_runtime_semantics(
    target: str, runtime_stage_root: Path, phase_receipts: dict[str, Path],
    contract_projection: Any, contract_payload: Path, variant: dict[str, Any],
    receipts: dict[str, dict[str, Any]], binding: dict[str, Any],
) -> tuple[dict[str, Any], bytes]:
    """Check the same bound originals for signed and protected pre-sign callers.

    This is not a planner/host token. Contract projection must come from the
    existing full Contract verifier; no SDK product or compatibility declaration
    participates. Original signatures and execution evidence remain external.
    """
    from .c_abi import TARGET_SPECS, c_abi_archive_file_name, portable_verify_c_abi_package_evidence
    from .contract_projection import VerifiedContractProjection
    from .runtime_attestation import verify_runtime_stages
    from .runtime_evidence import (
        DESKTOP_RUNTIME_TEST_CLASS, DESKTOP_RUNTIME_TEST_METHODS,
        derive_authenticated_runtime_validation_projection, verify_desktop_test_report,
    )

    specs = {spec.classifier.removeprefix("c-abi-"): spec for spec in TARGET_SPECS.values()}
    if target not in specs or set(phase_receipts) != {"binary", "package", "validation", "metadata"}:
        raise ValueError("Native Runtime content requires one exact target and four original receipts")
    if type(contract_projection) is not VerifiedContractProjection:
        raise ValueError("Native Runtime content requires authenticated Contract projection")
    contract = contract_projection.receipt_value(include_coverage=target == "macos-arm64")
    components = {item["component"]: item["sha256"] for item in contract["componentDigests"]}
    if not {"common", target} <= set(components):
        raise ValueError("Native Runtime content lacks its authenticated Contract components")
    payload = read_regular_file_bytes(contract_payload, max_bytes=1024 * 1024 * 1024,
                                      reject_symlink_parents=True)
    if sha256_bytes(payload) != contract["bundleSha256"]:
        raise ValueError("Native Runtime Contract payload differs from authenticated projection")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        manifest_bytes = archive.read("contract-manifest.json")
        if sha256_bytes(manifest_bytes) != contract["manifestSha256"]:
            raise ValueError("Native Runtime Contract manifest differs from authenticated projection")
        contract_manifest = validate_contract_manifest(load_canonical_json_bytes(manifest_bytes))
        evidence = {"contract-manifest.json": manifest_bytes}
        if target == "macos-arm64":
            evidence.update({name: archive.read("evidence/" + name) for name in
                             ("canonical-api.json", "canonical-coverage.json")})
    if (contract_manifest["contractDigest"] != contract["contractDigest"] or any(
        contract_manifest["components"][name]["sha256"] != components[name] for name in ("common", target)
    )):
        raise ValueError("Native Runtime Contract manifest component mismatch")
    spec = specs[target]
    package, validation = (runtime_stage_root / target / phase for phase in ("package", "validation"))
    roots = (package, validation)
    before = [regular_file_inventory(root) for root in roots]
    original_receipts = {phase: read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                                       reject_symlink_parents=True)
                         for phase, path in phase_receipts.items()}
    desktop_report = validation / "outputs/native" / f"desktop-runtime-{spec.target}.json"
    if variant["target"] != target or variant["contract"] != {
        "digest": contract["contractDigest"], "componentDigest": components[target],
    }:
        raise ValueError("Native Runtime variant differs from authenticated Contract/target")
    verify_runtime_stages(runtime_stage_root, target, phase_receipts, binding)
    receipt = receipts["validation"]
    execution_name = f"outputs/execution/desktop-runtime-{spec.target}-execution.json"
    exact_outputs = {
        f"outputs/native/desktop-runtime-{spec.target}.json": "native",
        f"outputs/native/TEST-{spec.target}Test.{DESKTOP_RUNTIME_TEST_CLASS}.xml": "native",
        f"outputs/c-abi/c-abi-package-{target}.json": "c-abi",
        execution_name: "execution",
    }
    for item in receipt["outputs"]:
        path = item["relativePath"]
        kind = ("c-abi-reference" if path.startswith("outputs/c-abi-reference/") else
                "c-abi-bootstrap" if target == "macos-arm64" and path.startswith("outputs/c-abi-bootstrap/")
                else exact_outputs.get(path))
        if kind is None or item["kind"] != kind:
            raise ValueError("Native Runtime content has an unprojected validation output")
    if any(sha256_bytes(original_receipts[phase]) != binding["phaseReceipts"][phase]
           for phase in phase_receipts):
        raise ValueError("Native Runtime original receipt changed during authentication")
    if target == "macos-arm64":
        projections = [item["contractProjection"] for item in receipt["inputs"]["upstreamArtifacts"]
                       if item["product"] == "contract" and "contractProjection" in item]
        if (len(projections) != 1 or projections[0].get("canonicalCoverageDigest") != contract["canonicalCoverageDigest"]
                or projections[0]["contractDigest"] != contract["contractDigest"]
                or projections[0]["componentDigests"] != [
                    {"component": name, "sha256": components[name]} for name in ("common", target)]):
            raise ValueError("Native Runtime bootstrap requires its exact authenticated Contract coverage")
    junit_name = f"outputs/native/TEST-{spec.target}Test.{DESKTOP_RUNTIME_TEST_CLASS}.xml"
    if not any(item["kind"] == "native" and item["relativePath"] == junit_name for item in receipt["outputs"]):
        raise ValueError("Native Runtime validation lacks its exact raw Desktop JUnit")
    junit = validation / junit_name
    if not any(item["kind"] == "execution" and item["relativePath"] == execution_name for item in receipt["outputs"]):
        raise ValueError("Native SDK admission requires original Desktop process execution evidence")
    verify_runtime_process_capture(validation / execution_name, target, spec.target, DESKTOP_RUNTIME_TEST_CLASS)
    verify_desktop_test_report(junit, spec.target)
    cases = read_canonical_test_report(junit)
    expected_cases = {f"{spec.target}Test.{DESKTOP_RUNTIME_TEST_CLASS}#{method}"
                      for method in DESKTOP_RUNTIME_TEST_METHODS}
    # Imported producers use bare method names; fresh native Gradle adds only its target suffix.
    actual_cases = {case.test_id.removesuffix(f"[{spec.target}]") for case in cases}
    if len(cases) != len(expected_cases) or actual_cases != expected_cases or any(
        case.status.value != "passed" for case in cases
    ):
        raise ValueError("Native Runtime Desktop JUnit cases are not exact passed target tests")
    desktop = derive_authenticated_runtime_validation_projection(target, [desktop_report], [receipt])
    reference = validation / "outputs/c-abi-reference"
    c_abi_evidence = validation / "outputs/c-abi" / f"c-abi-package-{target}.json"
    archive = package / "outputs/c-abi" / c_abi_archive_file_name(variant["runtimeCompatibilityVersion"], spec.target)
    c_abi_artifact = next(item for item in variant["innerArtifacts"] if item["role"] == "c-abi-archive")
    archive_bytes = read_regular_file_bytes(archive, reject_symlink_parents=True)
    if len(archive_bytes) != c_abi_artifact["bytes"] or sha256_bytes(archive_bytes) != c_abi_artifact["sha256"]:
        raise ValueError("Native Runtime portable C ABI input differs from its authenticated variant")
    policy = {"mach-o": "macos.exports", "elf": "linux.map", "pe": "windows.def"}[spec.format]
    with tempfile.TemporaryDirectory(prefix="runtime-native-content-") as temporary:
        root = Path(temporary).resolve()
        from .runtime_validation_projection import verify_projected_c_abi_evidence
        verifier = (verify_projected_c_abi_evidence if load_json_bytes(read_regular_file_bytes(
            c_abi_evidence, reject_symlink_parents=True)).get("schemaVersion") == 2
            else portable_verify_c_abi_package_evidence)
        report = verifier(
            spec.target, variant["runtimeCompatibilityVersion"], receipt["producer"]["commit"],
            receipt["producer"]["tree"], archive, c_abi_evidence,
            reference / "include/codex_agent.h", reference / "legal/LICENSE",
            reference / "legal/THIRD_PARTY_NOTICES.md", reference / "export-policy" / policy,
            tuple((reference / "consumer").iterdir()), root / "c-abi",
        )
        bootstrap = None
        if target == "macos-arm64":
            contract_directory = root / "contract"
            contract_directory.mkdir()
            for name, data in evidence.items():
                (contract_directory / name).write_bytes(data)
            bootstrap = verify_runtime_bootstrap_content(
                validation / "outputs/c-abi-bootstrap", reference, contract_directory, root / "c-abi",
            )
    # The portable verifier above owns the exact schema and full execution proof.
    # Only its execution-envelope digests are excluded from reusable semantic facts.
    c_abi = {name: value for name, value in report.items()
             if name not in {"producerCommit", "producerTree", "tools", "consumers", "gnuConsumers"}}
    for name in c_abi:
        if name.endswith("Sha256"):
            c_abi[name] = _digest(c_abi[name], name)
    c_abi["importLibraries"] = [{"path": item["path"], "sha256": _digest(item["sha256"], "import library")}
                                for item in report["importLibraries"]]
    c_abi["tools"] = [{"id": item["id"]} for item in report["tools"]]
    for name in ("consumers", "gnuConsumers"):
        c_abi[name] = [{key: item[key] for key in ("source", "sourceSha256", "language", "linked", "executed", "exitCode")}
                       for item in report[name]]
        for item in c_abi[name]:
            item["sourceSha256"] = _digest(item["sourceSha256"], "consumer source")
    content = {
        "schemaVersion": 1, "kind": "runtime-native-validation-content", "target": target,
        "componentId": variant["componentId"], "contract": dict(variant["contract"]),
        "validationInputs": {name: receipt["inputs"][name] for name in
                             ("phaseInputDigest", "toolchainProfileDigest", "flagsDigest", "outputSchemaVersion")},
        "referenceFiles": regular_file_inventory(reference), "desktop": desktop,
        "cAbi": c_abi, "bootstrap": bootstrap,
    }
    if before != [regular_file_inventory(root) for root in roots] or any(
        original_receipts[phase] != read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                                           reject_symlink_parents=True)
        for phase, path in phase_receipts.items()
    ):
        raise ValueError("Native Runtime original evidence changed during content verification")
    return content, original_receipts["validation"]


def _record(value: Any, label: str, *, multiline: bool = False) -> str:
    if type(value) is not str or not value or value != value.strip() or any(
        ord(char) < 32 and not (multiline and char == "\n") for char in value
    ) or "\x7f" in value:
        raise ValueError(f"Invalid bootstrap {label}")
    return value


def _strings(value: Any, label: str) -> list[str]:
    rows = [_record(row, label) for row in require_array(value, label)]
    if not rows or rows != sorted(set(rows)):
        raise ValueError(f"Bootstrap {label} must be exact sorted unique records")
    return rows


def _digest(value: Any, label: str) -> str:
    if type(value) is not str or len(value) != 64:
        raise ValueError(f"Invalid bootstrap {label} digest")
    return require_sha256("sha256:" + value, label)


def bootstrap_content(raw: Path, contract_directory: Path) -> dict[str, Any]:
    """Project validated raw facts; never replace the original full compiler gate."""
    manifest, api = _verify_extracted_contract_directory(
        contract_directory, required_components=("common", "macos-arm64"),
        include_canonical_api_projection=True,
    )
    assert api is not None
    return _bootstrap_content(raw, manifest, api)


def _bootstrap_content(raw: Path, manifest: dict, api: dict) -> dict[str, Any]:
    """Shared content model; caller must authenticate the original Contract first."""
    data = read_regular_file_bytes(raw, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    report = require_exact_keys(load_json_bytes(data), {
        "schemaVersion", "protocol", "result", "milestone", "language", "canonical",
        "toolchain", "artifacts", "compilerConsumers", "linkedPublicSymbols", "nativeTests", "claims",
    }, "C ABI bootstrap")
    if require_integer(report["schemaVersion"], "bootstrap schema", 1) != 1 or (
        report["protocol"], report["result"], report["milestone"], report["language"]
    ) != ("codex-agent-c-abi-bootstrap-evidence-v1", "observed", "D104", "c-abi"):
        raise ValueError("Bootstrap identity is not exact observed D104 c-abi evidence")
    canonical = require_exact_keys(report["canonical"], {
        "apiReportSha256", "coverageReceiptSha256", "nativeTargetSha256", "capabilityCount",
        "observedCapabilityCount", "observedCapabilitySha256", "observedCapabilityKeys", "missingCapabilityKeys",
    }, "bootstrap canonical")
    for name in ("apiReportSha256", "coverageReceiptSha256"):
        if canonical[name] != api["canonical"][name]:
            raise ValueError(f"Bootstrap {name} differs from verified Contract")
    if canonical["nativeTargetSha256"] != api["targetSha256"]["native"]:
        raise ValueError("Bootstrap native target differs from verified Contract")
    keys = _strings(canonical["observedCapabilityKeys"], "capability keys")
    if keys != api["memberKeys"] or canonical["missingCapabilityKeys"] != [] or any(
        require_integer(canonical[name], name, 1) != 556
        for name in ("capabilityCount", "observedCapabilityCount")
    ) or _digest(canonical["observedCapabilitySha256"], "capability") != sha256_bytes(
        "".join(key + "\n" for key in keys).encode("utf-8")
    ):
        raise ValueError("Bootstrap capability partition differs from verified Contract")
    toolchain = require_exact_keys(report["toolchain"], {
        "clang", "clangCpp", "clangVersion", "macosSdk",
    }, "bootstrap toolchain")
    for name, value in toolchain.items():
        _record(value, name, multiline=name == "clangVersion")
    artifacts = require_exact_keys(report["artifacts"], {
        "reviewedHeaderSha256", "cinteropDefinitionSha256", "exportPolicySha256", "generatedHeaderSha256",
        "releaseLibrarySha256", "nativeTestExecutableSha256", "nativeMainSourcesSha256",
        "nativeTestSourcesSha256", "nativeTestResultsSha256", "fileIdentity", "installName",
    }, "bootstrap artifacts")
    for name, value in artifacts.items():
        _digest(value, name) if name.endswith("Sha256") else _record(value, name)
    consumers = []
    for row in require_array(report["compilerConsumers"], "bootstrap compiler consumers"):
        consumer = require_exact_keys(row, {
            "id", "sourceSha256", "artifactSha256", "executed",
        }, "bootstrap compiler consumer")
        _record(consumer["id"], "consumer id")
        _digest(consumer["artifactSha256"], "consumer artifact")
        if type(consumer["executed"]) is not bool:
            raise ValueError("Bootstrap consumer executed must be boolean")
        consumers.append({
            "id": consumer["id"], "sourceSha256": _digest(consumer["sourceSha256"], "consumer source"),
            "executed": consumer["executed"],
        })
    consumer_ids = [row["id"] for row in consumers]
    if not consumers or len(consumer_ids) != len(set(consumer_ids)):
        raise ValueError("Bootstrap compiler consumers are missing or duplicated")
    symbols = _strings(report["linkedPublicSymbols"], "linked symbols")
    tests = []
    for row in require_array(report["nativeTests"], "bootstrap native tests"):
        test = require_exact_keys(row, {"testId", "status"}, "bootstrap native test")
        _record(test["testId"], "test ID")
        if test["status"] != "passed":
            raise ValueError("Bootstrap native test did not pass")
        tests.append(test)
    test_ids = _strings([row["testId"] for row in tests], "native test IDs")
    claims = []
    for row in require_array(report["claims"], "bootstrap claims"):
        claim = require_exact_keys(row, {
            "capabilityKey", "headerReferences", "consumerReferences", "publicSymbols", "nativeTestIds",
        }, "bootstrap claim")
        _record(claim["capabilityKey"], "claim key")
        for name in ("headerReferences", "consumerReferences", "publicSymbols", "nativeTestIds"):
            _strings(claim[name], name)
        if not set(claim["publicSymbols"]) <= set(symbols) or not set(claim["nativeTestIds"]) <= set(test_ids):
            raise ValueError("Bootstrap claim lacks passed test or linked symbol")
        claims.append(claim)
    if [row["capabilityKey"] for row in claims] != keys:
        raise ValueError("Bootstrap claims do not match the exact Contract capability set")
    if read_regular_file_bytes(raw, reject_symlink_parents=True) != data:
        raise ValueError("Bootstrap raw evidence changed during projection")
    return {
        "schemaVersion": 1, "kind": "runtime-c-abi-bootstrap-content", "target": "macos-arm64",
        "contractDigest": manifest["contractDigest"],
        "contractComponentDigest": manifest["components"]["macos-arm64"]["sha256"],
        "canonicalApiDigest": manifest["canonicalApiDigest"],
        "canonicalCoverageDigest": manifest["canonicalCoverageDigest"],
        "capabilityCount": 556,
        "artifacts": {name: _digest(artifacts[name], name) for name in (
            "reviewedHeaderSha256", "cinteropDefinitionSha256", "exportPolicySha256",
            "releaseLibrarySha256", "nativeMainSourcesSha256", "nativeTestSourcesSha256",
        )},
        "compilerConsumers": sorted(consumers, key=lambda row: row["id"]),
        "linkedPublicSymbols": symbols, "nativeTests": tests, "claims": claims,
    }


def _verify_bootstrap_handoff(inputs: Path) -> None:
    """Keep SDK private H as a thin adapter to the K/R-only raw gate."""
    verify_runtime_bootstrap_content(
        inputs / "bootstrap", inputs / "bootstrap-reference", inputs / "contract", inputs / "sdks/macos-arm64",
    )


def verify_runtime_bootstrap_content(
    bootstrap: Path, reference: Path, contract: Path, c_abi_sdk: Path,
) -> dict[str, Any]:
    """Rehash explicit K/R inputs already bound to authenticated original outputs.

    Callers must first authenticate original signatures, inventories and plans.
    No SDK package, SDK version or compatibility declaration is required here.
    The returned content is not a planner/host token; the full Kotlin matcher
    still owns per-capability/scenario correspondence. No imported code executes.
    """
    roots = (bootstrap, reference, contract, c_abi_sdk)
    before = [regular_file_inventory(root) for root in roots]
    manifest = validate_contract_manifest(load_canonical_json_bytes(
        read_regular_file_bytes(contract / "contract-manifest.json", reject_symlink_parents=True)))
    api = _canonical_api_projection({f"evidence/{name}": read_regular_file_bytes(contract / name)
                                     for name in ("canonical-api.json", "canonical-coverage.json")})
    raw = bootstrap / "bootstrap-evidence.json"
    content = _bootstrap_content(raw, manifest, api)
    report = load_json_bytes(read_regular_file_bytes(raw))
    artifacts = report["artifacts"]
    for field, path in {
        "reviewedHeaderSha256": reference / "include/codex_agent.h",
        "cinteropDefinitionSha256": bootstrap / "reference/codex_agent_c.def",
        "exportPolicySha256": reference / "export-policy/macos.exports",
        "generatedHeaderSha256": bootstrap / "original-runner/compiler-header/libcodex_agent_api.h",
        "releaseLibrarySha256": c_abi_sdk / "lib/libcodex_agent.dylib",
        "nativeTestExecutableSha256": bootstrap / "original-runner/test.kexe",
    }.items():
        if _digest(artifacts[field], field) != sha256_bytes(read_regular_file_bytes(path, reject_symlink_parents=True)):
            raise ValueError(f"Bootstrap raw artifact differs: {field}")
    for field, path in {
        "nativeMainSourcesSha256": bootstrap / "original-runner/source/nativeMain",
        "nativeTestSourcesSha256": bootstrap / "original-runner/source/nativeTest",
        "nativeTestResultsSha256": bootstrap / "native-junit",
    }.items():
        if artifacts[field] != _execution_tree_digest(path):
            raise ValueError(f"Bootstrap raw tree differs: {field}")
    sources = regular_file_inventory(reference / "consumer")
    consumed = []
    artifact_paths = []
    for consumer in report["compilerConsumers"]:
        identity = require_relative_path(consumer["id"], "Bootstrap compiler consumer ID")
        if "/" in identity:
            raise ValueError("Bootstrap compiler consumer ID must be a filename")
        matching = [record for record in sources if record["sha256"] == _digest(consumer["sourceSha256"], "source")]
        if len(matching) != 1:
            raise ValueError("Bootstrap compiler source is missing or ambiguous")
        consumed.append(read_regular_file_bytes(reference / "consumer" / matching[0]["relativePath"]))
        name = identity if consumer["executed"] else identity + ".o"
        artifact_paths.append(name)
        if _digest(consumer["artifactSha256"], "compiler artifact") != sha256_bytes(
            read_regular_file_bytes(bootstrap / "consumers" / name, reject_symlink_parents=True)
        ):
            raise ValueError("Bootstrap compiled consumer artifact differs")
    if sorted(artifact_paths) != [record["relativePath"] for record in regular_file_inventory(bootstrap / "consumers")]:
        raise ValueError("Bootstrap compiler artifact inventory differs")
    tests = []
    tasks = set()
    for path in sorted((bootstrap / "native-junit").iterdir()):
        if path.suffix != ".xml" or ".capi." not in path.name:
            continue  # Exact same report selection as the original Runtime producer.
        for test in read_canonical_test_report(path):
            task, _, suffix = test.test_id.partition(".")
            tasks.add(task)
            if (task not in {"macosArm64Test", "testImportedMacosArm64CAbi"}
                    or not suffix.startswith("io.github.codex_agent_labs.codexagent.capi.")
                    or not suffix.endswith("[macosArm64]")):
                raise ValueError("Bootstrap JUnit has a foreign task/package/target")
            tests.append({"testId": "macosArm64Test." + suffix, "status": test.status.value})
    if len(tasks) != 1 or sorted(tests, key=lambda row: row["testId"]) != report["nativeTests"]:
        raise ValueError("Bootstrap raw JUnit differs from the exact passed native test inventory")
    symbols = read_regular_file_bytes(reference / "export-policy/macos.exports").decode("utf-8").splitlines()
    if symbols != ["_" + symbol for symbol in report["linkedPublicSymbols"]]:
        raise ValueError("Bootstrap linked symbols differ from authenticated export policy")
    header = read_regular_file_bytes(reference / "include/codex_agent.h").decode("utf-8")
    consumer_text = "\n".join(source.decode("utf-8") for source in consumed)
    for claim in report["claims"]:
        for field, text in (("headerReferences", header), ("consumerReferences", consumer_text)):
            if any(re.search(r"(?<![A-Za-z0-9_])" + re.escape(value) + r"(?![A-Za-z0-9_])", text) is None
                   for value in claim[field]):
                raise ValueError(f"Bootstrap claim lacks authenticated {field}")
    if canonical_json_bytes(content) != read_regular_file_bytes(bootstrap / "bootstrap-content.json"):
        raise ValueError("Bootstrap content sidecar differs from its authenticated raw closure")
    if before != [regular_file_inventory(root) for root in roots]:
        raise ValueError("Bootstrap private inputs changed during verification")
    return content


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("bootstrap",))
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--contract-directory", type=Path, required=True)
    args = parser.parse_args(arguments)
    sys.stdout.buffer.write(canonical_json_bytes(bootstrap_content(args.raw, args.contract_directory)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
