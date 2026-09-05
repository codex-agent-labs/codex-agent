"""S808 JVM/Node adapter chain over synthetic inputs, not hosted evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ci.products.aggregate import RUNTIME_ADAPTERS, RUNTIME_EVIDENCE_TARGETS, RUNTIME_TARGETS
from ci.products.contract_model import CONTRACT_CHECKSUM_SUFFIXES
from ci.products.inventory import load_canonical_json_bytes, sha256_bytes, write_canonical_json
from ci.products.runtime_evidence import (
    derive_runtime_adapter_projection,
    jvm_evidence_filename,
    node_evidence_filename,
)
from ci.tests.product_chain_support import contract_reference, output, reference, write_receipt
from ci.tests.test_runtime_evidence import RuntimeEvidenceFixture


def build_adapters(
    root: Path,
    contract: dict[str, Any],
    variants: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Build deterministic adapter payloads and their authenticated receipt closure."""
    root = Path(root)
    root.mkdir(parents=True)
    raw_root = root / "raw"
    raw_root.mkdir()
    fixture = RuntimeEvidenceFixture(raw_root)
    fixture.commits = dict.fromkeys(fixture.commits, context["producer"]["commit"])
    raw_paths = {
        "jvm": fixture.write_jvm(),
        "node-js": fixture.write_node("js"),
        "node-wasm": fixture.write_node("wasm"),
    }

    adapter_report_files: dict[str, dict[str, Path]] = {}
    adapter_evidence: dict[str, Path] = {}
    for component in RUNTIME_ADAPTERS:
        by_target = {
            load_canonical_json_bytes(path.read_bytes())["target"]: path
            for path in raw_paths[component]
        }
        reports = {
            target: by_target[RUNTIME_EVIDENCE_TARGETS[target]]
            for target in RUNTIME_TARGETS
        }
        projection = derive_runtime_adapter_projection(
            component,
            [load_canonical_json_bytes(path.read_bytes()) for path in reports.values()],
            fixture.commits,
        )
        projection_path = root / "evidence" / f"{component}.json"
        write_canonical_json(projection_path, projection)
        adapter_report_files[component] = reports
        adapter_evidence[component] = projection_path

    runtime_maven_files = list(variants["runtime_maven_files"])
    maven_outputs: dict[str, list[dict[str, Any]]] = {}
    for component in RUNTIME_ADAPTERS:
        contents = f"S808 synthetic {component} Maven Runtime fixture\n".encode()
        logical_path = f"maven/{component}/runtime.bin"
        primary = root / logical_path
        primary.parent.mkdir(parents=True)
        primary.write_bytes(contents)
        files = [{
            "path": logical_path,
            "role": "runtime-resolution",
            "component": component,
            "file": primary,
        }]
        for suffix in CONTRACT_CHECKSUM_SUFFIXES:
            sidecar_contents = (
                hashlib.new(suffix.removeprefix("."), contents).hexdigest().encode("ascii")
                + b"\n"
            )
            sidecar = primary.with_name(primary.name + suffix)
            sidecar.write_bytes(sidecar_contents)
            files.append({
                "path": logical_path + suffix,
                "role": "checksum",
                "component": component,
                "file": sidecar,
            })
        runtime_maven_files.extend(files)
        maven_outputs[component] = [
            output("maven", f"outputs/{record['path']}", Path(record["file"]).read_bytes())
            for record in files
        ]
    runtime_maven_files.sort(key=lambda record: record["path"])

    receipt_paths: dict[tuple[str, str, str], Path] = {}

    def write(
        component: str,
        phase: str,
        target: str,
        *,
        outputs: list[dict[str, Any]],
        upstream: list[dict[str, Any]],
    ) -> dict[str, Any]:
        identity = (component, phase, target)
        path = root / "receipts" / component / f"{phase}-{target}.json"
        receipt = write_receipt(
            path,
            component=component,
            phase=phase,
            target=target,
            outputs=outputs,
            upstream=upstream,
            context=context,
        )
        receipt_paths[identity] = path
        return receipt

    for component in RUNTIME_ADAPTERS:
        binary = write(
            component,
            "binary",
            component,
            outputs=[output(
                "adapter-binary",
                f"outputs/binary/{component}.bin",
                f"S808 synthetic {component} binary fixture\n".encode(),
            )],
            upstream=[contract_reference(contract, component)],
        )
        package = write(
            component,
            "package",
            component,
            outputs=[output(
                "adapter-package",
                f"outputs/package/{component}.bin",
                f"S808 synthetic {component} package fixture\n".encode(),
            )],
            upstream=[reference(binary)],
        )
        metadata_upstream = []
        projection_digest = sha256_bytes(adapter_evidence[component].read_bytes())
        for target in RUNTIME_TARGETS:
            evidence_target = RUNTIME_EVIDENCE_TARGETS[target]
            report = adapter_report_files[component][target]
            if component == "jvm":
                kind = "jvm-evidence"
                relative_path = f"outputs/jvm-evidence/{jvm_evidence_filename(evidence_target)}"
            else:
                backend = "js" if component == "node-js" else "wasm"
                kind = "node-evidence"
                relative_path = (
                    f"outputs/node-evidence/{node_evidence_filename(evidence_target, backend)}"
                )
            validation = write(
                component,
                "validation",
                target,
                outputs=[output(kind, relative_path, report.read_bytes())],
                upstream=[reference(package), reference(variants["receipts"][target]["package"])],
            )
            semantic = reference(validation)
            semantic["semanticProjection"] = {
                "schemaVersion": 1,
                "kind": "runtime-validation-content",
                "sha256": projection_digest,
            }
            metadata_upstream.append(semantic)
        if component == "node-js":
            binding = write(
                component,
                "validation",
                "node-js-binding",
                outputs=[output(
                    "adapter-validation",
                    "outputs/node-js-binding/evidence.json",
                    b"S808 synthetic Node binding validation fixture\n",
                )],
                upstream=[reference(package)],
            )
            metadata_upstream.append(reference(binding))
        projection_contents = adapter_evidence[component].read_bytes()
        write(
            component,
            "metadata",
            component,
            outputs=[
                output(
                    "adapter-evidence",
                    f"outputs/evidence/{component}.json",
                    projection_contents,
                ),
                *maven_outputs[component],
            ],
            upstream=metadata_upstream,
        )

    adapter_receipts = [
        {
            "component": component,
            "phase": phase,
            "target": target,
            "receipt": receipt_paths[(component, phase, target)],
        }
        for component, phase, target in sorted(receipt_paths)
    ]
    return {
        "runtime_maven_files": runtime_maven_files,
        "adapter_evidence": adapter_evidence,
        "adapter_receipts": adapter_receipts,
        "adapter_report_files": adapter_report_files,
    }
