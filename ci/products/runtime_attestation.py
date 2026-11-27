"""Deterministic compatibility evidence for one Runtime component."""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from .c_abi import TARGET_SPECS
from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    load_json_bytes,
    require_array,
    require_exact_keys,
    require_identifier,
    require_integer,
    require_relative_path,
    require_regular_directory,
    require_sha256,
    require_string,
    publish_regular_tree,
    read_regular_file_bytes,
    regular_file_inventory,
    sha256_bytes,
    verified_zip_contents,
    write_canonical_json,
)
from .receipt import build_key_payload, output_inventory_digest, validate_phase_receipt, verify_output_manifest_identity
from .runtime_evidence import (
    DESKTOP_KEYS,
    DESKTOP_RUNTIME_TEST_CLASS,
    DESKTOP_RUNTIME_TEST_METHODS,
    RUNTIME_TARGETS,
    desktop_test_task,
    imported_desktop_test_task,
)
from .runtime_identity import derive_runtime_identity, validate_runtime_identity
from .signatures import (
    load_keyring,
    public_key_for_metadata,
    sign_manifest,
    validate_signing_metadata,
    verify_manifest_signature,
)


_PHASES = ("binary", "package", "validation")
_PHASE_FIELDS = {
    "schemaVersion",
    "product",
    "component",
    "phase",
    "target",
    "buildKey",
    "phaseInputDigest",
    "versionIdentity",
    "upstreamArtifacts",
    "toolchainProfileDigest",
    "flagsDigest",
    "outputSchemaVersion",
}
_CONTRACT_UPSTREAM_FIELDS = {
    "schemaVersion",
    "kind",
    "product",
    "component",
    "phase",
    "target",
    "contractDigest",
    "componentDigests",
}
_RUNTIME_UPSTREAM_FIELDS = {
    "product",
    "component",
    "phase",
    "target",
    "buildKey",
    "outputsDigest",
}
_ARTIFACT_FIELDS = {"path", "role", "bytes", "sha256"}
_PRODUCT_TO_EVIDENCE_TARGET = {
    "macos-arm64": "macosArm64",
    "macos-x64": "macosX64",
    "linux-arm64": "linuxArm64",
    "linux-x64": "linuxX64",
    "windows-x64": "mingwX64",
}
_JSON_LIMIT = 16 * 1024 * 1024
_PAYLOAD_LIMIT = 1024 * 1024 * 1024
_MANIFEST_NAME = "runtime-variant-manifest.json"
_ATTESTATION_PHASES = ("binary", "package", "validation", "metadata")


def verify_runtime_stages(
    root: Path,
    target: str,
    phase_receipts: dict[str, Path],
    authenticated_attestation: dict[str, Any],
) -> None:
    """Check raw stage inventories against the exact bound original receipts.

    This is not a signature or trust gate. Signed consumers first verify the
    variant attestation; pre-sign consumers supply receipt digests established
    by _bound_inputs over their exact private originals. CI/release source
    authorization remains caller-owned. No SDK product dependency is introduced.
    """
    for phase in ("package", "validation"):
        receipt_bytes = read_regular_file_bytes(
            phase_receipts[phase], max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
        )
        if sha256_bytes(receipt_bytes) != authenticated_attestation["phaseReceipts"][phase]:
            raise ValueError(f"Runtime original {phase} receipt changed: {target}")
        receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
        if (receipt["product"], receipt["component"], receipt["phase"], receipt["target"]) != (
            "runtime", target, phase, target,
        ):
            raise ValueError(f"Runtime original {phase} receipt identity mismatch: {target}")
        stage = root / target / phase
        manifest = verify_output_manifest_identity(
            stage, "runtime", target, phase, target, receipt["productVersion"],
        )
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError(f"Runtime {phase} stage differs from authenticated receipt: {target}")
        if phase == "validation":
            spec = next(spec for spec in TARGET_SPECS.values()
                        if spec.classifier.removeprefix("c-abi-") == target)
            proof_path = f"outputs/c-abi/c-abi-package-{target}.json"
            if not any(output["kind"] == "c-abi" and output["relativePath"] == proof_path
                       for output in receipt["outputs"]):
                raise ValueError(f"Runtime C ABI evidence output identity mismatch: {target}")
            # Preserve the original legacy encoding; portable verification owns semantics.
            proof = load_json_bytes(read_regular_file_bytes(
                stage / proof_path,
                max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
            ))
            if (type(proof) is not dict or proof.get("target") != spec.target
                    or (proof.get("schemaVersion") == 1 and (
                        proof.get("producerCommit") != receipt["producer"]["commit"]
                        or proof.get("producerTree") != receipt["producer"]["tree"]))
                    or (proof.get("schemaVersion") == 2 and (
                        "producerCommit" in proof or "producerTree" in proof))
                    or proof.get("schemaVersion") not in (1, 2)):
                raise ValueError(f"Runtime C ABI evidence original producer mismatch: {target}")


def derive_desktop_validation_projection(
    report_value: Any,
    *,
    identity_envelope: Any,
    expected_commit: str,
    classifier_archive_sha256: str,
) -> dict[str, Any]:
    """Validate run evidence and remove only run/task provenance from reusable bytes."""
    identity = validate_runtime_identity(identity_envelope)
    projected = type(report_value) is dict and report_value.get("schemaVersion") == 4
    report = require_exact_keys(
        report_value,
        DESKTOP_KEYS - {"candidateCommit", "testTask"} if projected else DESKTOP_KEYS,
        "Desktop Runtime validation evidence",
    )
    evidence_target = _PRODUCT_TO_EVIDENCE_TARGET[identity["target"]]
    expected = RUNTIME_TARGETS[evidence_target]
    if (
        require_integer(report["schemaVersion"], "Desktop evidence.schemaVersion", 1) != (4 if projected else 3)
        or (not projected and report["candidateCommit"] != expected_commit)
        or report["target"] != evidence_target
        or report["classifier"] != expected.classifier
        or report["runnerOs"] != expected.runner_os
        or report["runnerArch"] != expected.runner_arch
        or (not projected and report["testTask"] not in {
            desktop_test_task(evidence_target), imported_desktop_test_task(evidence_target),
        })
        or report["testClass"] != DESKTOP_RUNTIME_TEST_CLASS
        or report["testMethods"] != list(DESKTOP_RUNTIME_TEST_METHODS)
        or require_integer(report["tests"], "Desktop evidence.tests", 0) !=
            len(DESKTOP_RUNTIME_TEST_METHODS)
        or any(
            require_integer(report[field], f"Desktop evidence.{field}", 0) != 0
            for field in ("skipped", "failures", "errors")
        )
        or report["result"] != "passed"
    ):
        raise ValueError("Desktop Runtime validation evidence identity or result mismatch")
    for field in ("binarySha256", "supervisorSha256", "classifierArchiveSha256"):
        value = require_string(report[field], f"Desktop evidence.{field}")
        require_sha256(f"sha256:{value}", f"Desktop evidence.{field}")
    if (
        f"sha256:{report['binarySha256']}" != identity["appServer"]["binarySha256"]
        or f"sha256:{report['classifierArchiveSha256']}" != classifier_archive_sha256
    ):
        raise ValueError("Desktop Runtime validation evidence artifact identity mismatch")
    return {
        "schemaVersion": 1,
        "target": identity["target"],
        "classifier": report["classifier"],
        "runnerOs": report["runnerOs"],
        "runnerArch": report["runnerArch"],
        "testClass": report["testClass"],
        "testMethods": report["testMethods"],
        "tests": report["tests"],
        "skipped": report["skipped"],
        "failures": report["failures"],
        "errors": report["errors"],
        "binarySha256": f"sha256:{report['binarySha256']}",
        "supervisorSha256": f"sha256:{report['supervisorSha256']}",
        "classifierArchiveSha256": f"sha256:{report['classifierArchiveSha256']}",
        "result": "passed",
    }


def _verify_bootstrap_contract_input(value: Any, identity: dict[str, Any]) -> None:
    schema = value.get("schemaVersion") if type(value) is dict else None
    record = require_exact_keys(value, _CONTRACT_UPSTREAM_FIELDS | (
        {"canonicalCoverageDigest"} if schema == 2 else set()), "Runtime bootstrap Contract input")
    if schema == 2:
        require_sha256(record["canonicalCoverageDigest"], "Runtime bootstrap Contract coverage digest")
    components = require_array(record["componentDigests"], "Runtime bootstrap Contract components")
    for component in components:
        require_exact_keys(component, {"component", "sha256"}, "Runtime bootstrap Contract component")
        require_sha256(component["sha256"], "Runtime bootstrap Contract component digest")
    if (
        identity["target"] != "macos-arm64"
        or require_integer(record["schemaVersion"], "Runtime bootstrap Contract schema", 1) not in (1, 2)
        or record["kind"] != "contract-components"
        or (record["product"], record["component"], record["phase"], record["target"])
        != ("contract", "contract", "metadata", "common")
        or record["contractDigest"] != identity["contract"]["digest"]
        or [component["component"] for component in components] != ["common", "macos-arm64"]
        or components[-1]["sha256"] != identity["contract"]["componentDigest"]
    ):
        raise ValueError("Runtime bootstrap Contract input does not match the component identity")


def verify_runtime_validation_inputs(
    validation: dict[str, Any], package: dict[str, Any], identity: dict[str, Any],
) -> None:
    upstream = validation["inputs"]["upstreamArtifacts"]
    # Original pre-bootstrap receipts remain immutable/verifiable. New canonical
    # Mac validation plans require this second input in registry.py; a legacy
    # lifecycle-only receipt cannot establish the separately required bootstrap proof.
    if len(upstream) == 2:
        projected = build_key_payload(
            product=validation["product"], component=validation["component"], phase=validation["phase"],
            target=validation["target"], inputs=validation["inputs"],
        )["upstreamArtifacts"]
        _verify_bootstrap_contract_input(projected[0], identity)
        upstream = upstream[1:]
    if upstream != [_receipt_reference(package)]:
        raise ValueError("Runtime validation receipt does not link exactly to the package receipt")


def _phase_evidence(values: Any, identity: dict[str, Any]) -> list[dict[str, Any]]:
    records = require_array(values, "Runtime component phase evidence")
    if len(records) != len(_PHASES):
        raise ValueError("Runtime component phase evidence must contain exactly three phases")
    validated = []
    for index, expected_phase in enumerate(_PHASES):
        label = f"Runtime component phase evidence[{index}]"
        output_field = "validationEvidenceDigest" if expected_phase == "validation" else \
            "outputInventoryDigest"
        record = require_exact_keys(records[index], _PHASE_FIELDS | {output_field}, label)
        phase = require_identifier(record["phase"], f"{label}.phase")
        if phase != expected_phase:
            raise ValueError("Runtime component phase evidence must be sorted and unique by phase")
        if (
            require_integer(record["schemaVersion"], f"{label}.schemaVersion", 1) != 1
            or record["product"] != "runtime"
            or record["component"] != identity["target"]
            or record["target"] != identity["target"]
            or record["versionIdentity"] != identity["runtimeCompatibilityVersion"]
        ):
            raise ValueError(f"{label} does not match the Runtime identity")
        require_sha256(record["buildKey"], f"{label}.buildKey")
        require_sha256(record["phaseInputDigest"], f"{label}.phaseInputDigest")
        require_sha256(record["toolchainProfileDigest"], f"{label}.toolchainProfileDigest")
        require_sha256(record["flagsDigest"], f"{label}.flagsDigest")
        if require_integer(record["outputSchemaVersion"], f"{label}.outputSchemaVersion", 1) != 1:
            raise ValueError(f"{label}.outputSchemaVersion is unsupported")
        require_sha256(record[output_field], f"{label}.{output_field}")

        upstream = require_array(record["upstreamArtifacts"], f"{label}.upstreamArtifacts")
        if phase == "validation" and len(upstream) == 2:
            _verify_bootstrap_contract_input(upstream[0], identity)
            upstream = upstream[1:]
        if len(upstream) != 1:
            raise ValueError(f"{label}.upstreamArtifacts must contain exactly one predecessor")
        if phase == "binary":
            predecessor = require_exact_keys(
                upstream[0], _CONTRACT_UPSTREAM_FIELDS, f"{label}.upstreamArtifacts[0]",
            )
            component_digests = require_array(
                predecessor["componentDigests"],
                f"{label}.upstreamArtifacts[0].componentDigests",
            )
            if len(component_digests) != 1:
                raise ValueError("Runtime binary phase evidence must select exactly one Contract component")
            component_digest = require_exact_keys(
                component_digests[0], {"component", "sha256"},
                f"{label}.upstreamArtifacts[0].componentDigests[0]",
            )
            if (
                require_integer(
                    predecessor["schemaVersion"],
                    f"{label}.upstreamArtifacts[0].schemaVersion",
                    1,
                ) != 1
                or predecessor["kind"] != "contract-components"
                or (
                    predecessor["product"], predecessor["component"],
                    predecessor["phase"], predecessor["target"],
                )
                != ("contract", "contract", "metadata", "common")
                or predecessor["contractDigest"] != identity["contract"]["digest"]
                or component_digest != {
                    "component": identity["target"],
                    "sha256": identity["contract"]["componentDigest"],
                }
            ):
                raise ValueError("Runtime binary phase evidence Contract identity mismatch")
            require_sha256(predecessor["contractDigest"], "Runtime Contract digest")
            require_identifier(component_digest["component"], "Runtime Contract component")
            require_sha256(component_digest["sha256"], "Runtime Contract component digest")
        else:
            predecessor = require_exact_keys(
                upstream[0], _RUNTIME_UPSTREAM_FIELDS, f"{label}.upstreamArtifacts[0]",
            )
            previous = validated[index - 1]
            if (
                (
                    predecessor["product"], predecessor["component"],
                    predecessor["phase"], predecessor["target"],
                )
                != ("runtime", identity["target"], previous["phase"], identity["target"])
                or predecessor["buildKey"] != previous["buildKey"]
                or predecessor["outputsDigest"] != previous["outputInventoryDigest"]
            ):
                raise ValueError(f"Runtime {phase} phase evidence predecessor mismatch")
            require_sha256(predecessor["buildKey"], f"{label} predecessor buildKey")
            require_sha256(predecessor["outputsDigest"], f"{label} predecessor outputsDigest")

        key_payload = {
            field: record[field] for field in _PHASE_FIELDS if field != "buildKey"
        }
        if record["buildKey"] != sha256_bytes(canonical_json_bytes(key_payload)):
            raise ValueError(f"Runtime {phase} phase evidence buildKey mismatch")
        if phase == "binary" and (
            record["buildKey"] != identity["binaryBuildKey"]
            or record["toolchainProfileDigest"] != identity["toolchainProfile"]["digest"]
        ):
            raise ValueError("Runtime binary phase evidence build or toolchain identity mismatch")
        validated.append(record)
    return validated


def _artifacts(values: Any) -> list[dict[str, Any]]:
    records = require_array(values, "Runtime component artifacts")
    if not records:
        raise ValueError("Runtime component artifacts must not be empty")
    validated = []
    for index, value in enumerate(records):
        label = f"Runtime component artifacts[{index}]"
        record = require_exact_keys(value, _ARTIFACT_FIELDS, label)
        validated.append({
            "path": require_relative_path(record["path"], f"{label}.path"),
            "role": require_identifier(record["role"], f"{label}.role"),
            "bytes": require_integer(record["bytes"], f"{label}.bytes", 1),
            "sha256": require_sha256(record["sha256"], f"{label}.sha256"),
        })
    paths = [record["path"] for record in validated]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ValueError("Runtime component artifacts must be sorted by path and unique")
    return validated


def derive_runtime_component_attestation(
    identity_envelope: Any,
    phase_evidence: Any,
    artifacts: Any,
) -> dict[str, Any]:
    """Return canonical deterministic SBOM and component-provenance evidence."""
    identity = validate_runtime_identity(identity_envelope)
    phases = _phase_evidence(phase_evidence, identity)
    files = _artifacts(artifacts)
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "bom-ref": identity["componentId"],
                "type": "library",
                "name": f"codex-agent-runtime-variant-{identity['target']}",
                "version": identity["runtimeCompatibilityVersion"],
            },
        },
        "components": [
            {
                "bom-ref": artifact["path"],
                "type": "file",
                "name": artifact["path"],
                "hashes": [{
                    "alg": "SHA-256",
                    "content": artifact["sha256"].removeprefix("sha256:"),
                }],
            }
            for artifact in files
        ],
    }
    provenance = {
        "schemaVersion": 1,
        "product": "runtime",
        "componentId": identity["componentId"],
        "runtimeCompatibilityVersion": identity["runtimeCompatibilityVersion"],
        "target": identity["target"],
        "contract": identity["contract"],
        "binaryBuildKey": identity["binaryBuildKey"],
        "toolchainProfile": identity["toolchainProfile"],
        "phaseEvidence": phases,
        "artifacts": files,
    }
    sbom_bytes = canonical_json_bytes(sbom)
    provenance_bytes = canonical_json_bytes(provenance)
    return {
        "sbom": load_canonical_json_bytes(sbom_bytes),
        "sbomBytes": sbom_bytes,
        "componentProvenance": load_canonical_json_bytes(provenance_bytes),
        "componentProvenanceBytes": provenance_bytes,
    }


def validate_runtime_variant_attestation(value: Any) -> dict[str, Any]:
    attestation = require_exact_keys(value, {
        "schemaVersion", "product", "target", "componentId", "payload",
        "manifestSha256", "phaseReceipts", "signing",
    }, "Runtime variant attestation")
    if require_integer(
        attestation["schemaVersion"], "Runtime variant attestation.schemaVersion", 1,
    ) != 1:
        raise ValueError("Unsupported Runtime variant attestation schemaVersion")
    if attestation["product"] != "runtime":
        raise ValueError("Runtime variant attestation product must be runtime")
    target = require_identifier(attestation["target"], "Runtime variant attestation.target")
    if target not in _PRODUCT_TO_EVIDENCE_TARGET:
        raise ValueError("Runtime variant attestation target is unsupported")
    component_id = require_sha256(
        attestation["componentId"], "Runtime variant attestation.componentId",
    )
    payload = require_exact_keys(
        attestation["payload"], {"fileName", "bytes", "sha256"},
        "Runtime variant attestation.payload",
    )
    expected_name = (
        f"codex-agent-runtime-variant-{target}-"
        f"{component_id.removeprefix('sha256:')}.zip"
    )
    if require_string(
        payload["fileName"], "Runtime variant attestation.payload.fileName",
    ) != expected_name:
        raise ValueError("Runtime variant attestation payload filename is invalid")
    require_integer(payload["bytes"], "Runtime variant attestation.payload.bytes", 1)
    require_sha256(payload["sha256"], "Runtime variant attestation.payload.sha256")
    require_sha256(
        attestation["manifestSha256"], "Runtime variant attestation.manifestSha256",
    )
    receipts = require_exact_keys(
        attestation["phaseReceipts"], set(_ATTESTATION_PHASES),
        "Runtime variant attestation.phaseReceipts",
    )
    for phase in _ATTESTATION_PHASES:
        require_sha256(receipts[phase], f"Runtime variant attestation.phaseReceipts.{phase}")
    validate_signing_metadata(attestation["signing"])
    return attestation


def _receipt_reference(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "product": receipt["product"],
        "component": receipt["component"],
        "phase": receipt["phase"],
        "target": receipt["target"],
        "buildKey": receipt["buildKey"],
        "outputsDigest": output_inventory_digest(receipt["outputs"]),
    }


def _read_receipt(path: Path, phase: str) -> tuple[dict[str, Any], bytes]:
    contents = read_regular_file_bytes(
        Path(path), max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    if not contents:
        raise ValueError(f"Runtime {phase} receipt must not be empty")
    return validate_phase_receipt(load_canonical_json_bytes(contents)), contents


def _payload_identity(
    path: Path,
) -> tuple[dict[str, Any], dict[str, Any], str, dict[str, bytes]]:
    payload_bytes = read_regular_file_bytes(
        Path(path), max_bytes=_PAYLOAD_LIMIT, reject_symlink_parents=True,
    )
    if not payload_bytes:
        raise ValueError("Runtime variant payload must not be empty")
    with tempfile.TemporaryDirectory(prefix="runtime-variant-payload-") as temporary:
        snapshot = Path(temporary).resolve() / Path(path).name
        snapshot.write_bytes(payload_bytes)
        # Aggregate owns the shared manifest schema and imports this module.
        from .aggregate import RUNTIME_VARIANT_ZIP_LIMITS, validate_runtime_variant

        records, retained, archive = verified_zip_contents(
            snapshot,
            **RUNTIME_VARIANT_ZIP_LIMITS,
            retained_paths=(_MANIFEST_NAME,),
            max_retained_bytes=_JSON_LIMIT,
            canonical_stored=True,
        )
        try:
            manifest_bytes = retained[_MANIFEST_NAME]
        except KeyError as error:
            raise ValueError("Runtime variant payload is missing its manifest") from error
        manifest = validate_runtime_variant(load_canonical_json_bytes(manifest_bytes))
        expected_name = (
            f"codex-agent-runtime-variant-{manifest['target']}-"
            f"{manifest['componentId'].removeprefix('sha256:')}.zip"
        )
        if Path(path).name != expected_name:
            raise ValueError("Runtime variant payload filename does not match its manifest")
        inventory = {record["relativePath"]: record for record in records}
        declared = {
            member["path"]: {
                "relativePath": member["path"],
                "bytes": member["bytes"],
                "sha256": member["sha256"],
            }
            for member in manifest["innerArtifacts"]
        }
        if set(inventory) != {_MANIFEST_NAME} | set(declared) or any(
            inventory[path] != record for path, record in declared.items()
        ):
            raise ValueError("Runtime variant payload inventory differs from its manifest")
        roles = {member["role"]: member for member in manifest["innerArtifacts"]}
        evidence_paths = {
            roles[role]["path"] for role in (
                "binary-phase-evidence", "package-phase-evidence",
                "validation-phase-evidence", "validation", "provenance", "sbom",
            )
        }
        repeated_records, evidence, repeated_identity = verified_zip_contents(
            snapshot,
            **RUNTIME_VARIANT_ZIP_LIMITS,
            retained_paths=evidence_paths,
            max_retained_bytes=64 * 1024 * 1024,
            canonical_stored=True,
        )
        if repeated_records != records or repeated_identity != archive:
            raise ValueError("Runtime variant payload changed during evidence verification")
        return manifest, {
            "fileName": expected_name,
            "bytes": archive["bytes"],
            "sha256": archive["sha256"],
        }, sha256_bytes(manifest_bytes), evidence


def _project_receipt(
    receipt: dict[str, Any], *, validation_evidence_digest: str | None = None,
) -> dict[str, Any]:
    projection = {
        **build_key_payload(
            product=receipt["product"], component=receipt["component"],
            phase=receipt["phase"], target=receipt["target"], inputs=receipt["inputs"],
        ),
        "buildKey": receipt["buildKey"],
    }
    if receipt["phase"] == "validation":
        if validation_evidence_digest is None:
            raise ValueError("Runtime validation receipt requires deterministic evidence")
        projection["validationEvidenceDigest"] = validation_evidence_digest
    else:
        projection["outputInventoryDigest"] = output_inventory_digest(receipt["outputs"])
    return projection


def _bound_inputs(
    payload: Path,
    binary_receipt: Path,
    package_receipt: Path,
    validation_receipt: Path,
    metadata_receipt: Path,
    validation_evidence: Path | None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, bytes], dict[str, Any], str]:
    manifest, payload_identity, manifest_sha256, evidence = _payload_identity(Path(payload))
    paths = {
        "binary": binary_receipt,
        "package": package_receipt,
        "validation": validation_receipt,
        "metadata": metadata_receipt,
    }
    receipts: dict[str, dict[str, Any]] = {}
    receipt_bytes: dict[str, bytes] = {}
    for phase in _ATTESTATION_PHASES:
        receipts[phase], receipt_bytes[phase] = _read_receipt(Path(paths[phase]), phase)
    target = manifest["target"]
    for phase in _ATTESTATION_PHASES:
        receipt = receipts[phase]
        if (
            (receipt["product"], receipt["component"], receipt["phase"], receipt["target"])
            != ("runtime", target, phase, target)
            or receipt["inputs"]["versionIdentity"] != manifest["runtimeCompatibilityVersion"]
        ):
            raise ValueError(f"Runtime {phase} receipt identity does not match the variant payload")
    binary = receipts["binary"]
    package = receipts["package"]
    validation = receipts["validation"]
    metadata = receipts["metadata"]
    if (
        manifest["inputs"]["binaryBuildKey"] != binary["buildKey"]
        or manifest["inputs"]["binaryOutputInventoryDigest"]
        != output_inventory_digest(binary["outputs"])
    ):
        raise ValueError("Runtime binary receipt does not bind the variant manifest")
    upstream = binary["inputs"]["upstreamArtifacts"]
    projection = upstream[0].get("contractProjection") if len(upstream) == 1 else None
    component_digests = {} if projection is None else {
        record["component"]: record["sha256"] for record in projection["componentDigests"]
    }
    if projection is None or (
        projection["contractDigest"] != manifest["contract"]["digest"]
        or component_digests.get(target) != manifest["contract"]["componentDigest"]
    ):
        raise ValueError("Runtime binary receipt Contract projection does not match the payload")
    if package["inputs"]["upstreamArtifacts"] != [_receipt_reference(binary)]:
        raise ValueError("Runtime package receipt does not link exactly to the binary receipt")
    verify_runtime_validation_inputs(validation, package, manifest)
    expected_output = {
        "kind": "runtime-variant",
        "relativePath": f"outputs/{payload_identity['fileName']}",
        "bytes": payload_identity["bytes"],
        "sha256": payload_identity["sha256"],
    }
    if metadata["outputs"] != [expected_output]:
        raise ValueError("Runtime metadata receipt does not bind the exact variant payload")
    roles = {member["role"]: member for member in manifest["innerArtifacts"]}
    for role, kind, prefix in (
        ("c-abi-archive", "c-abi", "outputs/c-abi/"),
        ("app-server-archive", "app-server", "outputs/app-server/"),
    ):
        artifact = roles[role]
        if sum(
            output["kind"] == kind
            and output["relativePath"].startswith(prefix)
            and output["bytes"] == artifact["bytes"]
            and output["sha256"] == artifact["sha256"]
            for output in package["outputs"]
        ) != 1:
            raise ValueError(f"Runtime variant {role} is not one exact package output")
    identity = derive_runtime_identity({
        "schemaVersion": 1,
        "binaryBuildKey": manifest["inputs"]["binaryBuildKey"],
        "runtimeCompatibilityVersion": manifest["runtimeCompatibilityVersion"],
        "target": manifest["target"],
        "contract": manifest["contract"],
        "cAbi": manifest["cAbi"],
        "appServer": manifest["appServer"],
        "toolchainProfile": manifest["toolchainProfile"],
    })
    validation_projection_bytes = evidence[roles["validation"]["path"]]
    load_canonical_json_bytes(validation_projection_bytes)
    metadata_upstream = _receipt_reference(validation)
    metadata_upstream["semanticProjection"] = {
        "schemaVersion": 1,
        "kind": "runtime-validation-content",
        "sha256": sha256_bytes(validation_projection_bytes),
    }
    if metadata["inputs"]["upstreamArtifacts"] != [metadata_upstream]:
        raise ValueError(
            "Runtime metadata receipt does not link exactly to the validation content",
        )
    if validation_evidence is not None:
        validation_bytes = read_regular_file_bytes(
            Path(validation_evidence), max_bytes=64 * 1024 * 1024,
            reject_symlink_parents=True,
        )
        matching_validation = [
            output for output in validation["outputs"]
            if output["kind"] == "native"
            and output["relativePath"].startswith("outputs/native/")
            and output["bytes"] == len(validation_bytes)
            and output["sha256"] == sha256_bytes(validation_bytes)
        ]
        if len(matching_validation) != 1:
            raise ValueError("Runtime validation evidence is not one exact validation output")
        validation_projection = derive_desktop_validation_projection(
            load_json_bytes(validation_bytes),
            identity_envelope=identity,
            expected_commit=validation["producer"]["commit"],
            classifier_archive_sha256=roles["app-server-archive"]["sha256"],
        )
        if validation_projection_bytes != canonical_json_bytes(validation_projection):
            raise ValueError("Runtime variant validation projection is invalid")
    phase_evidence = [
        load_canonical_json_bytes(evidence[roles[f"{phase}-phase-evidence"]["path"]])
        for phase in ("binary", "package", "validation")
    ]
    expected_phase_evidence = [
        _project_receipt(
            receipts[phase],
            validation_evidence_digest=(
                sha256_bytes(validation_projection_bytes) if phase == "validation" else None
            ),
        )
        for phase in ("binary", "package", "validation")
    ]
    if phase_evidence != expected_phase_evidence:
        raise ValueError("Runtime variant phase receipt projections are invalid")
    deterministic_artifacts = [
        member for member in manifest["innerArtifacts"]
        if member["role"] in {"app-server-archive", "c-abi-archive", "validation"}
    ]
    deterministic = derive_runtime_component_attestation(
        identity, phase_evidence, deterministic_artifacts,
    )
    if (
        evidence[roles["sbom"]["path"]] != deterministic["sbomBytes"]
        or evidence[roles["provenance"]["path"]] != deterministic["componentProvenanceBytes"]
    ):
        raise ValueError("Runtime variant deterministic evidence is invalid")
    return manifest, receipts, receipt_bytes, payload_identity, manifest_sha256


def verify_runtime_variant_attestation(
    payload: Path,
    binary_receipt: Path,
    package_receipt: Path,
    validation_receipt: Path,
    metadata_receipt: Path,
    attestation: Path,
    signature: Path,
    public_key: Path,
    *,
    required_trust_domain: str,
    validation_evidence: Path | None = None,
    keyring: Path | None = None,
    keys_directory: Path | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    if type(required_trust_domain) is not str or required_trust_domain not in {
        "development", "release",
    }:
        raise ValueError("Expected Runtime variant attestation trust domain is invalid")
    contents = read_regular_file_bytes(
        Path(attestation), max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    signature_contents = read_regular_file_bytes(
        Path(signature), max_bytes=1024 * 1024, reject_symlink_parents=True,
    )
    public_key_contents = read_regular_file_bytes(
        Path(public_key), max_bytes=1024 * 1024, reject_symlink_parents=True,
    )
    value = validate_runtime_variant_attestation(load_canonical_json_bytes(contents))
    stem = Path(value["payload"]["fileName"]).stem
    if (
        Path(attestation).name != f"{stem}.attestation.json"
        or Path(signature).name != f"{stem}.attestation.sig"
    ):
        raise ValueError("Runtime variant attestation or signature filename is invalid")
    signing = validate_signing_metadata(value["signing"], trust_domain=required_trust_domain)
    manifest, receipts, receipt_bytes, payload_identity, manifest_sha256 = _bound_inputs(
        Path(payload), Path(binary_receipt), Path(package_receipt),
        Path(validation_receipt), Path(metadata_receipt),
        None if validation_evidence is None else Path(validation_evidence),
    )
    expected = {
        "schemaVersion": 1,
        "product": "runtime",
        "target": manifest["target"],
        "componentId": manifest["componentId"],
        "payload": payload_identity,
        "manifestSha256": manifest_sha256,
        "phaseReceipts": {
            phase: sha256_bytes(receipt_bytes[phase]) for phase in _ATTESTATION_PHASES
        },
        "signing": signing,
    }
    if value != expected:
        raise ValueError("Runtime variant attestation does not bind its exact payload and receipts")
    if required_trust_domain == "release":
        if keyring is None or keys_directory is None:
            raise ValueError("Release Runtime variant attestation verification requires a keyring")
        trusted_key = public_key_for_metadata(
            signing, load_keyring(Path(keyring), Path(keys_directory)), Path(keys_directory),
            allow_retired=True,
        )
        if read_regular_file_bytes(trusted_key, reject_symlink_parents=True) != public_key_contents:
            raise ValueError("Runtime variant attestation public key does not match the keyring")
    elif keyring is not None or keys_directory is not None:
        raise ValueError("Development Runtime variant attestation rejects release keyring inputs")
    with tempfile.TemporaryDirectory(prefix="runtime-variant-attestation-verify-") as temporary:
        root = Path(temporary).resolve()
        snapshot_attestation = root / Path(attestation).name
        snapshot_signature = root / Path(signature).name
        snapshot_public_key = root / "runtime.pub"
        snapshot_attestation.write_bytes(contents)
        snapshot_signature.write_bytes(signature_contents)
        snapshot_public_key.write_bytes(public_key_contents)
        verify_manifest_signature(
            snapshot_attestation, snapshot_signature, snapshot_public_key, signing,
        )
    return manifest, receipts, value


def read_runtime_variant_handoff(
    root: Path,
    *,
    target: str,
    keyring: Path,
    keys_directory: Path,
) -> dict[str, Any]:
    """Read a complete release handoff using independently supplied public policy.

    Returned bytes are the verified originals, not paths to reread or a source
    admission token. Original phase matching and complete K/R/raw C ABI admission
    remain caller-owned; this reader never signs, reconstructs or publishes.
    """
    if require_identifier(target, "Runtime handoff target") not in _PRODUCT_TO_EVIDENCE_TARGET:
        raise ValueError("Runtime handoff target is unsupported")
    if keyring is None or keys_directory is None:
        raise ValueError("Runtime release handoff requires caller-owned keyring inputs")
    root = Path(root).absolute()
    for directory in (root, *root.parents):
        require_regular_directory(directory, "Runtime handoff directory")
    names = {path.name for path in root.iterdir()}
    attestation_names = [name for name in names if name.endswith(".attestation.json")]
    if len(names) != 6 or len(attestation_names) != 1:
        raise ValueError("Complete Runtime handoff file inventory is not exact")
    attestation_name = attestation_names[0]
    attestation_bytes = read_regular_file_bytes(
        root / attestation_name, max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    declared = validate_runtime_variant_attestation(load_canonical_json_bytes(attestation_bytes))
    if declared["target"] != target:
        raise ValueError("Runtime handoff target does not match its attestation")
    payload_name = declared["payload"]["fileName"]
    stem = Path(payload_name).stem
    limits = {
        payload_name: _PAYLOAD_LIMIT,
        f"{stem}.attestation.json": _JSON_LIMIT,
        f"{stem}.attestation.sig": 1024 * 1024,
        "public-key.pub": 1024 * 1024,
        "validation-evidence.json": 64 * 1024 * 1024,
        **{f"receipts/{phase}.json": _JSON_LIMIT for phase in _ATTESTATION_PHASES},
    }
    expected_names = {Path(name).parts[0] for name in limits}
    expected_receipts = {f"{phase}.json" for phase in _ATTESTATION_PHASES}
    if names != expected_names:
        raise ValueError("Complete Runtime handoff file inventory is not exact")
    require_regular_directory(root / "receipts", "Runtime handoff receipts")
    if {path.name for path in (root / "receipts").iterdir()} != expected_receipts:
        raise ValueError("Complete Runtime handoff receipt inventory is not exact")
    files = {name: read_regular_file_bytes(root / name, max_bytes=limit, reject_symlink_parents=True)
             for name, limit in limits.items()}
    if files[attestation_name] != attestation_bytes:
        raise ValueError("Runtime handoff attestation changed during capture")
    expected_inventory = [{"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)}
                          for name, raw in sorted(files.items())]
    with tempfile.TemporaryDirectory(prefix="runtime-variant-handoff-read-") as temporary:
        snapshot = Path(temporary).resolve()
        for name, raw in files.items():
            path = snapshot / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        manifest, receipts, attestation = verify_runtime_variant_attestation(
            snapshot / payload_name,
            *(snapshot / f"receipts/{phase}.json" for phase in _ATTESTATION_PHASES),
            snapshot / attestation_name, snapshot / f"{stem}.attestation.sig",
            snapshot / "public-key.pub", required_trust_domain="release",
            validation_evidence=snapshot / "validation-evidence.json",
            keyring=keyring, keys_directory=keys_directory,
        )
        if regular_file_inventory(snapshot) != expected_inventory:
            raise ValueError("Captured Runtime handoff changed during verification")
        if ({path.name for path in root.iterdir()} != expected_names
                or {path.name for path in (root / "receipts").iterdir()} != expected_receipts
                or regular_file_inventory(root) != expected_inventory):
            raise ValueError("Original Runtime handoff changed during verification")
        for name, raw in files.items():
            if read_regular_file_bytes(root / name, max_bytes=limits[name], reject_symlink_parents=True) != raw:
                raise ValueError("Original Runtime handoff changed during verification")
    return {"manifest": manifest, "receipts": receipts, "attestation": attestation,
            "receiptBytes": {phase: files[f"receipts/{phase}.json"] for phase in _ATTESTATION_PHASES},
            "files": files}


def build_runtime_variant_attestation(
    payload: Path,
    binary_receipt: Path,
    package_receipt: Path,
    validation_receipt: Path,
    metadata_receipt: Path,
    validation_evidence: Path,
    signing_metadata: Any,
    private_key: Path,
    public_key: Path,
    output_directory: Path,
    *,
    keyring: Path | None = None,
    keys_directory: Path | None = None,
    complete_handoff: bool = False,
) -> dict[str, Any]:
    """Sign exact originals; optionally retain their external nine-file handoff.

    Assembly does not authorize original CI sources or replace the caller's
    complete K/R and raw C ABI verification. No trust material enters the ZIP.
    """
    if type(complete_handoff) is not bool:
        raise ValueError("Complete Runtime handoff selection must be boolean")
    original_paths = {
        "payload": (Path(payload), _PAYLOAD_LIMIT),
        **{phase: (Path(path), _JSON_LIMIT) for phase, path in (
            ("binary", binary_receipt), ("package", package_receipt),
            ("validation", validation_receipt), ("metadata", metadata_receipt),
        )},
        "validation_evidence": (Path(validation_evidence), 64 * 1024 * 1024),
        "public_key": (Path(public_key), 1024 * 1024),
    }
    originals = {}
    if complete_handoff:
        output = Path(output_directory)
        if output.exists() or output.is_symlink():
            raise ValueError("Complete Runtime handoff destination must not exist")
        ancestor = output.absolute().parent
        while not ancestor.exists() and not ancestor.is_symlink():
            ancestor = ancestor.parent
        for directory in (ancestor, *ancestor.parents):
            require_regular_directory(directory, "Complete Runtime handoff destination ancestor")
        sources = [path for path, _ in original_paths.values()] + [Path(private_key)]
        sources.extend(Path(path) for path in (keyring, keys_directory) if path is not None)
        for source in sources:
            for left, right in ((source.absolute(), output.absolute()), (source.resolve(), output.resolve())):
                if left == right or left in right.parents or right in left.parents:
                    raise ValueError("Complete Runtime handoff output overlaps an original input")
        originals = {
            name: read_regular_file_bytes(path, max_bytes=limit, reject_symlink_parents=True)
            for name, (path, limit) in original_paths.items()
        }
    signing = validate_signing_metadata(signing_metadata)
    if signing["trustDomain"] == "release":
        if keyring is None or keys_directory is None:
            raise ValueError("Release Runtime variant attestation creation requires a keyring")
        trusted_key = public_key_for_metadata(
            signing, load_keyring(Path(keyring), Path(keys_directory)), Path(keys_directory),
            allow_retired=False,
        )
        if read_regular_file_bytes(trusted_key, reject_symlink_parents=True) != \
                read_regular_file_bytes(Path(public_key), reject_symlink_parents=True):
            raise ValueError("Runtime variant attestation public key is not the active release key")
    elif keyring is not None or keys_directory is not None:
        raise ValueError("Development Runtime variant attestation creation rejects keyring inputs")
    with tempfile.TemporaryDirectory(prefix="runtime-variant-attestation-build-") as temporary:
        prepared = Path(temporary).resolve() / "attestation"
        prepared.mkdir()
        captured = {}
        if complete_handoff:
            relative_paths = {
                "payload": Path(payload).name,
                **{phase: f"receipts/{phase}.json" for phase in _ATTESTATION_PHASES},
                "validation_evidence": "validation-evidence.json",
                "public_key": "public-key.pub",
            }
            for name, relative in relative_paths.items():
                captured[name] = prepared / relative
                captured[name].parent.mkdir(parents=True, exist_ok=True)
                captured[name].write_bytes(originals[name])
            payload, binary_receipt, package_receipt, validation_receipt, metadata_receipt, \
                validation_evidence, public_key = (captured[name] for name in (
                    "payload", "binary", "package", "validation", "metadata",
                    "validation_evidence", "public_key",
                ))
        manifest, _, receipt_bytes, payload_identity, manifest_sha256 = _bound_inputs(
            Path(payload), Path(binary_receipt), Path(package_receipt),
            Path(validation_receipt), Path(metadata_receipt), Path(validation_evidence),
        )
        value = validate_runtime_variant_attestation({
            "schemaVersion": 1,
            "product": "runtime",
            "target": manifest["target"],
            "componentId": manifest["componentId"],
            "payload": payload_identity,
            "manifestSha256": manifest_sha256,
            "phaseReceipts": {
                phase: sha256_bytes(receipt_bytes[phase]) for phase in _ATTESTATION_PHASES
            },
            "signing": signing,
        })
        stem = Path(payload_identity["fileName"]).stem
        attestation = prepared / f"{stem}.attestation.json"
        write_canonical_json(attestation, value)
        signature = sign_manifest(attestation, Path(private_key), signing)
        verified_inventory = regular_file_inventory(prepared)
        expected_paths = {attestation.name, signature.name}
        if complete_handoff:
            expected_paths.update(relative_paths.values())
        if {record["relativePath"] for record in verified_inventory} != expected_paths:
            raise ValueError("Runtime attestation file inventory is not exact")
        verify_runtime_variant_attestation(
            Path(payload), Path(binary_receipt), Path(package_receipt),
            Path(validation_receipt), Path(metadata_receipt), attestation, signature,
            Path(public_key),
            required_trust_domain=signing["trustDomain"],
            validation_evidence=Path(validation_evidence),
            keyring=keyring, keys_directory=keys_directory,
        )
        if regular_file_inventory(prepared) != verified_inventory:
            raise ValueError("Captured Runtime handoff changed during verification")
        if complete_handoff:
            for name, (path, limit) in original_paths.items():
                if read_regular_file_bytes(path, max_bytes=limit, reject_symlink_parents=True) != originals[name]:
                    raise ValueError("Original Runtime inputs changed during handoff assembly")
                if read_regular_file_bytes(captured[name], max_bytes=limit, reject_symlink_parents=True) != originals[name]:
                    raise ValueError("Captured Runtime inputs changed during handoff assembly")
        publish_regular_tree(prepared, Path(output_directory),
                             expected_inventory=verified_inventory)
    return value
