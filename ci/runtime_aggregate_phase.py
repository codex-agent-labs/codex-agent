"""Translate restored original Runtime phases; never supply signing authority.

The caller authenticates the original receipt closure. This module checks its
exact staged bytes and existing semantic projections, returning only paths/data
for the existing aggregate producer and later external attestation verifier.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from products.aggregate import (
    RUNTIME_ADAPTERS, RUNTIME_EVIDENCE_TARGETS, RUNTIME_TARGETS,
    require_runtime_adapter_maven_primary, validate_runtime_maven_inventory,
)
from products.contract_model import CONTRACT_CHECKSUM_SUFFIXES
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys
from products.receipt import (
    compute_build_key, output_inventory_digest, validate_phase_receipt,
    validate_receipt_inputs, verify_output_manifest_identity,
)
from products.runtime_aggregate import _adapter_receipt_identities
from products.runtime_evidence import (
    derive_authenticated_runtime_validation_projection, desktop_evidence_filename,
    jvm_evidence_filename, node_evidence_filename,
)


def collect_inputs(
    plan: Mapping[str, Any],
    predecessor: Callable[[str, str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    """Return the fixed 45-original-receipt closure, without modifying any input.

``predecessor(component, phase, target)`` supplies ``stage``, ``receiptPath``
and ``receipt`` from the caller's authenticated restored original state.
No fallback compilation, publication reconstruction, or attestation is allowed.
"""
    value = require_exact_keys(dict(plan), {
        "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs",
    }, "Runtime aggregate phase plan")
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1 or tuple(
        value[key] for key in ("product", "component", "phase", "target")
    ) != ("runtime", "runtime-aggregate", "metadata", "aggregate"):
        raise ValueError("Unsupported Runtime aggregate phase identity")
    inputs = validate_receipt_inputs(value["inputs"])
    if compute_build_key(product="runtime", component="runtime-aggregate", phase="metadata",
                         target="aggregate", inputs=inputs) != value["buildKey"]:
        raise ValueError("Runtime aggregate build key differs from its inputs")

    originals: dict[tuple[str, str, str], dict[str, Any]] = {}
    identities = sorted([
        *((target, phase, target) for target in RUNTIME_TARGETS
          for phase in ("binary", "package", "validation", "metadata")),
        *_adapter_receipt_identities(),
    ])
    for identity in identities:
        original = dict(predecessor(*identity))
        for key in ("stage", "receiptPath"):
            path = original[key]
            if not isinstance(path, Path) or not path.is_absolute() or path.resolve(strict=True) != path:
                raise ValueError("Runtime aggregate original paths must be absolute and non-symbolic")
        raw = read_regular_file_bytes(original["receiptPath"], max_bytes=16 * 1024 * 1024,
                                      reject_symlink_parents=True)
        receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
        if receipt != original["receipt"] or tuple(receipt[key] for key in (
            "product", "component", "phase", "target",
        )) != ("runtime", *identity):
            raise ValueError("Runtime aggregate original receipt identity/content mismatch")
        manifest = verify_output_manifest_identity(original["stage"], "runtime", *identity, receipt["productVersion"])
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError("Runtime aggregate stage differs from its original receipt")
        originals[identity] = original

    metadata = [original["receipt"] for identity, original in originals.items() if identity[1] == "metadata"]
    references = sorted([{
        **{key: receipt[key] for key in ("product", "component", "phase", "target", "buildKey")},
        "outputsDigest": output_inventory_digest(receipt["outputs"]),
    } for receipt in metadata], key=lambda record: tuple(record[key] for key in (
        "product", "component", "phase", "target", "buildKey",
    )))
    if inputs["upstreamArtifacts"] != references:
        raise ValueError("Runtime aggregate plan differs from its exact eight metadata predecessors")

    def selected(identity: tuple[str, str, str], kind: str, relative: str | None = None) -> Path:
        original = originals[identity]
        matches = [record for record in original["receipt"]["outputs"] if record["kind"] == kind
                   and (relative is None or record["relativePath"] == relative)]
        if len(matches) != 1:
            raise ValueError(f"Runtime aggregate requires one exact {kind} output for {identity}")
        return original["stage"] / matches[0]["relativePath"]

    bundles, phases, validation = {}, {}, {}
    for target in RUNTIME_TARGETS:
        bundles[target] = selected((target, "metadata", target), "runtime-variant")
        phases[target] = {phase: originals[(target, phase, target)]["receiptPath"]
                          for phase in ("binary", "package", "validation", "metadata")}
        validation[target] = selected((target, "validation", target), "native",
                                      f"outputs/native/{desktop_evidence_filename(RUNTIME_EVIDENCE_TARGETS[target])}")
        derive_authenticated_runtime_validation_projection(
            target, [validation[target]], [originals[(target, "validation", target)]["receipt"]])

    reports, evidence = {}, {}
    for component in RUNTIME_ADAPTERS:
        reports[component] = {}
        for target in RUNTIME_TARGETS:
            evidence_target = RUNTIME_EVIDENCE_TARGETS[target]
            kind = "jvm-evidence" if component == "jvm" else "node-evidence"
            name = (jvm_evidence_filename(evidence_target) if component == "jvm" else
                    node_evidence_filename(evidence_target, "js" if component == "node-js" else "wasm"))
            reports[component][target] = selected((component, "validation", target), kind, f"outputs/{kind}/{name}")
        projection = derive_authenticated_runtime_validation_projection(
            component, reports[component].values(),
            [originals[(component, "validation", target)]["receipt"] for target in RUNTIME_TARGETS])
        evidence[component] = selected((component, "metadata", component), "adapter-evidence",
                                       f"outputs/evidence/{component}.json")
        if read_regular_file_bytes(evidence[component], max_bytes=16 * 1024 * 1024,
                                   reject_symlink_parents=True) != canonical_json_bytes(projection):
            raise ValueError("Runtime aggregate adapter projection differs from original reports")

    maven, maven_records, contents = [], [], {}
    receipts = {identity: original["receipt"] for identity, original in originals.items()}
    for component in (*RUNTIME_TARGETS, *RUNTIME_ADAPTERS):
        original = originals[(component, "package" if component in RUNTIME_TARGETS else "metadata", component)]
        outputs = [record for record in original["receipt"]["outputs"] if record["kind"] == "maven"]
        if not outputs:
            raise ValueError(f"Runtime aggregate requires original {component} Maven outputs")
        for record in outputs:
            if not record["relativePath"].startswith(f"outputs/maven/{component}/"):
                raise ValueError("Runtime aggregate Maven output escapes its original component")
            logical = record["relativePath"].removeprefix("outputs/")
            name = Path(logical).name
            role = ("checksum" if any(name.endswith(suffix) for suffix in CONTRACT_CHECKSUM_SUFFIXES)
                    else "module-metadata" if name.endswith((".pom", ".module")) or name == "maven-metadata.xml"
                    else "sources" if name == "sources.jar" or name.endswith("-sources.jar")
                    else "javadoc" if name == "javadoc.jar" or name.endswith("-javadoc.jar")
                    else "runtime-resolution")
            require_runtime_adapter_maven_primary(component, role, record, receipts)
            path = original["stage"] / record["relativePath"]
            maven.append({"path": logical, "role": role, "component": component, "file": path})
            maven_records.append({"path": logical, "role": role, "component": component,
                                  "bytes": record["bytes"], "sha256": record["sha256"]})
            contents[logical] = read_regular_file_bytes(path, reject_symlink_parents=True)
    validate_runtime_maven_inventory(maven_records, contents)
    return {
        "variant_bundles": bundles, "variant_phase_receipts": phases, "variant_validation_evidence": validation,
        "runtime_maven_files": sorted(maven, key=lambda record: record["path"]), "adapter_evidence": evidence,
        "adapter_receipts": [{"component": component, "phase": phase, "target": target,
                              "receipt": originals[(component, phase, target)]["receiptPath"]}
                             for component, phase, target in _adapter_receipt_identities()],
        "adapter_report_files": reports,
    }
