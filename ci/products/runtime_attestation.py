"""Deterministic compatibility evidence for one Runtime component."""

from __future__ import annotations

from typing import Any

from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    require_array,
    require_exact_keys,
    require_identifier,
    require_integer,
    require_relative_path,
    require_sha256,
    require_string,
    sha256_bytes,
)
from .receipt import build_key_payload
from .runtime_evidence import (
    DESKTOP_KEYS,
    DESKTOP_RUNTIME_TEST_CLASS,
    DESKTOP_RUNTIME_TEST_METHODS,
    RUNTIME_TARGETS,
    desktop_test_task,
    imported_desktop_test_task,
)
from .runtime_identity import validate_runtime_identity


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


def derive_desktop_validation_projection(
    report_value: Any,
    *,
    identity_envelope: Any,
    expected_commit: str,
    classifier_archive_sha256: str,
) -> dict[str, Any]:
    """Validate run evidence and remove only run/task provenance from reusable bytes."""
    identity = validate_runtime_identity(identity_envelope)
    report = require_exact_keys(report_value, DESKTOP_KEYS, "Desktop Runtime validation evidence")
    evidence_target = _PRODUCT_TO_EVIDENCE_TARGET[identity["target"]]
    expected = RUNTIME_TARGETS[evidence_target]
    if (
        require_integer(report["schemaVersion"], "Desktop evidence.schemaVersion", 1) != 3
        or report["candidateCommit"] != expected_commit
        or report["target"] != evidence_target
        or report["classifier"] != expected.classifier
        or report["runnerOs"] != expected.runner_os
        or report["runnerArch"] != expected.runner_arch
        or report["testTask"] not in {
            desktop_test_task(evidence_target), imported_desktop_test_task(evidence_target),
        }
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

        key_payload = build_key_payload(
            product=record["product"],
            component=record["component"],
            phase=record["phase"],
            target=record["target"],
            inputs={
                "versionIdentity": record["versionIdentity"],
                "phaseInputDigest": record["phaseInputDigest"],
                "upstreamArtifacts": record["upstreamArtifacts"],
                "toolchainProfileDigest": record["toolchainProfileDigest"],
                "flagsDigest": record["flagsDigest"],
                "outputSchemaVersion": record["outputSchemaVersion"],
            },
        )
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
