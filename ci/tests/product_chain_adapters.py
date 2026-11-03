"""S808 JVM/Node adapter chain over synthetic inputs, not hosted evidence."""

from __future__ import annotations

import json
import base64
from pathlib import Path
from typing import Any

from ci.products.aggregate import RUNTIME_ADAPTERS, RUNTIME_EVIDENCE_TARGETS, RUNTIME_TARGETS
from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, load_json_bytes, sha256_bytes, write_canonical_json
from ci.products.receipt import write_output_manifest
from ci.products.registry import PhaseInstanceId
from ci.products.runtime_evidence import (
    DESKTOP_RUNTIME_TEST_CLASS, DESKTOP_RUNTIME_TEST_METHODS,
    NODE_RUNTIME_TEST_CLASS, NODE_RUNTIME_TEST_METHODS, PINNED_NODE_VERSION,
    derive_runtime_adapter_projection,
    inspect_classifier,
    jvm_evidence_filename,
    node_evidence_filename,
    read_distribution_manifest,
)
from ci.tests.product_chain_support import contract_reference, output, reference, write_receipt
from ci.tests.test_runtime_evidence import RuntimeEvidenceFixture


def _synthetic_host_capture(component: str, target: str, report: Path) -> dict[str, bytes]:
    """Fixture-only returned process bytes and JUnit; no runtime is executed."""
    is_jvm = component == "jvm"
    test_class = DESKTOP_RUNTIME_TEST_CLASS if is_jvm else NODE_RUNTIME_TEST_CLASS
    methods = DESKTOP_RUNTIME_TEST_METHODS if is_jvm else NODE_RUNTIME_TEST_METHODS

    def capture(identifier, raw):
        return {"id": identifier, "exitCode": 0, "outputBase64": base64.b64encode(raw).decode("ascii")}

    executions = [] if is_jvm else [capture("version", f"v{PINNED_NODE_VERSION}\n".encode())]
    executions.append(capture("discovery", (f"{test_class}.\n" + "".join(f"  {method}\n" for method in methods)).encode()))
    executions.extend(capture(method, b"" if index == len(methods) - 1 else b"\xff\x00Synthetic fixture output\n")
                      for index, method in enumerate(methods))
    prefix = "nodeRuntime" if component == "node-js" else "nodeWasmRuntime"
    junit_name = (f"TEST-jvm-runtime-{target}.xml" if is_jvm
                  else f"TEST-{prefix}{target[0].upper()}{target[1:]}Test.{test_class}.xml")
    return {
        f"{report.stem}-execution.json": canonical_json_bytes({
            "schemaVersion": 1, "component": component, "target": target,
            "testClass": test_class, "executions": executions,
        }),
        junit_name: (
            f'<testsuite tests="{len(methods)}" skipped="0" failures="0" errors="0">\n'
            + "".join(f'  <testcase classname="{test_class}" name="{method}"/>\n' for method in methods)
            + "</testsuite>\n"
        ).encode("utf-8"),
    }


def build_adapters(
    root: Path,
    contract: dict[str, Any],
    variants: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Build deterministic adapter payloads and their authenticated receipt closure."""
    root = Path(root)
    package_suffix = context.get("adapter_package_suffix", b"")
    if type(package_suffix) is not bytes:
        raise ValueError("Synthetic adapter package suffix must be bytes")
    root.mkdir(parents=True)
    raw_root = root / "raw"
    raw_root.mkdir()
    fixture = RuntimeEvidenceFixture(raw_root)
    fixture.commits = dict.fromkeys(fixture.commits, context["producer"]["commit"])
    raw_closure = context.get("adapter_raw_closure") is True
    if raw_closure:
        fixture.manifest_path = variants["stages"].parent / "inputs/codex-app-server-distributions.json"
        fixture.manifest = read_distribution_manifest(fixture.manifest_path)
        fixture.classifiers = {}
        for target in RUNTIME_TARGETS:
            archives = [record["relativePath"] for record in variants["receipts"][target]["package"]["outputs"]
                        if record["kind"] == "app-server" and record["relativePath"].endswith(".zip")]
            if len(archives) != 1:
                raise ValueError("Synthetic adapter requires one original native package classifier")
            fixture.classifiers[RUNTIME_EVIDENCE_TARGETS[target]] = variants["stages"] / target / "package" / archives[0]
        fixture.proofs = {target: inspect_classifier(target, fixture.manifest, archive)
                          for target, archive in fixture.classifiers.items()}
    raw_paths = {
        "jvm": fixture.write_jvm(),
        "node-js": fixture.write_node("js"),
        "node-wasm": fixture.write_node("wasm"),
    }
    pretty_reports = context.get("adapter_report_format") == "pretty"
    if pretty_reports:
        # Match the Kotlin raw producer before any original receipt binds bytes.
        # This does not alter the canonical deterministic content projection.
        for paths in raw_paths.values():
            for path in paths:
                value = load_json_bytes(path.read_bytes())
                path.write_bytes((json.dumps(value, indent=4) + "\n").encode("utf-8"))
    read_report = load_json_bytes if pretty_reports else load_canonical_json_bytes

    adapter_report_files: dict[str, dict[str, Path]] = {}
    adapter_evidence: dict[str, Path] = {}
    for component in RUNTIME_ADAPTERS:
        by_target = {
            read_report(path.read_bytes())["target"]: path
            for path in raw_paths[component]
        }
        reports = {
            target: by_target[RUNTIME_EVIDENCE_TARGETS[target]]
            for target in RUNTIME_TARGETS
        }
        projection = derive_runtime_adapter_projection(
            component,
            [read_report(path.read_bytes()) for path in reports.values()],
            fixture.commits,
        )
        projection_path = root / "evidence" / f"{component}.json"
        write_canonical_json(projection_path, projection)
        adapter_report_files[component] = reports
        adapter_evidence[component] = projection_path

    publication_outputs: dict[str, list[dict[str, Any]]] = {}
    publication_contents: dict[str, dict[str, bytes]] = {}
    publication_primaries: dict[str, dict[str, Path]] = {}
    for component in RUNTIME_ADAPTERS:
        contents = {
            "main.jar" if component == "jvm" else "main.klib":
                f"S808 synthetic {component} Runtime publication fixture\n".encode(),
            "sources.jar": f"S808 synthetic {component} sources publication fixture\n".encode(),
            "javadoc.jar": f"S808 synthetic {component} documentation publication fixture\n".encode(),
        }
        publication_contents[component] = {
            f"outputs/publication/{name}": value for name, value in contents.items()
        }
        publication_outputs[component] = [
            output("publication", path, value)
            for path, value in publication_contents[component].items()
        ]

    receipt_paths: dict[tuple[str, str, str], Path] = {}
    phase_stages: dict[PhaseInstanceId, Path] = {}

    def write(
        component: str,
        phase: str,
        target: str,
        *,
        outputs: list[dict[str, Any]],
        contents: dict[str, bytes],
        upstream: list[dict[str, Any]],
        inventory: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        identity = (component, phase, target)
        stage = root / "stages" / component / (
            "package" if component == "node-js" and phase == "package" else f"{phase}-{target}"
        )
        if set(contents) != {value["relativePath"] for value in outputs}:
            raise ValueError("Adapter fixture stage requires the exact original output bytes")
        for value in outputs:
            relative = value["relativePath"]
            if output(value["kind"], relative, contents[relative]) != value:
                raise ValueError("Adapter fixture source bytes differ from declared outputs")
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if destination.read_bytes() != contents[relative]:
                    raise ValueError("Adapter fixture must not overwrite different original stage bytes")
            else:
                destination.write_bytes(contents[relative])
        staged = write_output_manifest(stage, "runtime", component, phase, target, "0.2.7", {
            value["kind"]: "/".join(value["relativePath"].split("/")[:2]) for value in outputs
        })["outputs"]
        if staged != sorted(outputs, key=lambda value: value["relativePath"]):
            raise ValueError("Adapter fixture stage differs from the original output inventory")
        instance = PhaseInstanceId("runtime", component, phase, target)
        phase_stages[instance] = stage
        context.setdefault("phase_stages", {})[instance] = stage
        path = root / "receipts" / component / f"{phase}-{target}.json"
        receipt = write_receipt(
            path,
            component=component,
            phase=phase,
            target=target,
            outputs=outputs,
            upstream=upstream,
            context=context,
            **({"inventory": inventory} if inventory is not None else {}),
        )
        receipt_paths[identity] = path
        return receipt

    package_stages = {}
    for component in RUNTIME_ADAPTERS:
        runner = {"jvm": fixture.jvm_runner, "node-js": fixture.node_runner, "node-wasm": fixture.wasm_runner}[component]
        runner_contents = {f"outputs/validation-runner/{runner.name}": runner.read_bytes()} if raw_closure else {}
        runner_outputs = [output("validation-runner", relative, contents)
                          for relative, contents in runner_contents.items()]
        binary = write(
            component,
            "binary",
            component,
            outputs=[output(
                "adapter-binary",
                f"outputs/binary/{component}.bin",
                f"S808 synthetic {component} binary fixture\n".encode(),
            ), *publication_outputs[component], *runner_outputs],
            contents={f"outputs/binary/{component}.bin": f"S808 synthetic {component} binary fixture\n".encode(),
                      **publication_contents[component], **runner_contents},
            upstream=[contract_reference(contract, component)],
        )
        package_payload = f"S808 synthetic {component} package fixture\n".encode() + package_suffix
        package_outputs = [output(
            "adapter-package", f"outputs/package/{component}.bin",
            package_payload,
        )]
        package_contents = {
            f"outputs/package/{component}.bin": package_payload,
        }
        if component == "node-js":
            stage = root / "stages/node-js/package"
            adapter = stage / "outputs/adapter"
            adapter.mkdir(parents=True)
            for name, contents in {
                "runtime.js": b"export const runtime = 1;\n" + package_suffix,
                "runtime.js.map": b'{"version":3}\n',
                "runtime.d.ts": b"export declare const generated: number;\n",
            }.items():
                (adapter / name).write_bytes(contents)
            package_outputs = write_output_manifest(
                stage, "runtime", component, "package", component, "0.2.7",
                {"adapter": "outputs/adapter"},
            )["outputs"]
            package_stages[component] = stage
            package_contents = {value["relativePath"]: (stage / value["relativePath"]).read_bytes()
                                for value in package_outputs}
        package_outputs.extend((*publication_outputs[component], *runner_outputs))
        package_contents.update(publication_contents[component])
        package_contents.update(runner_contents)
        package = write(
            component,
            "package",
            component,
            outputs=package_outputs,
            contents=package_contents,
            upstream=[reference(binary)],
        )
        publication_primaries[component] = {
            Path(path).name: root / "stages" / component / f"binary-{component}" / path
            for path in publication_contents[component]
        }
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
            validation_contents = {relative_path: report.read_bytes()}
            validation_outputs = [output(kind, relative_path, validation_contents[relative_path])]
            validation_inventory = None
            if raw_closure:
                for name, contents in _synthetic_host_capture(component, evidence_target, report).items():
                    capture_kind = "test-report" if name.endswith(".xml") else "execution"
                    capture_path = f"outputs/{capture_kind}/{name}"
                    validation_contents[capture_path] = contents
                    validation_outputs.append(output(capture_kind, capture_path, contents))
                manifest_bytes = fixture.manifest_path.read_bytes()
                validation_inventory = [{
                    "relativePath": "codex-agent-runtime-desktop/codex-app-server-distributions.json",
                    "bytes": len(manifest_bytes), "sha256": sha256_bytes(manifest_bytes),
                }]
            validation = write(
                component,
                "validation",
                target,
                outputs=validation_outputs,
                contents=validation_contents,
                upstream=[reference(package), reference(variants["receipts"][target]["package"])],
                inventory=validation_inventory,
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
                contents={"outputs/node-js-binding/evidence.json": b"S808 synthetic Node binding validation fixture\n"},
                upstream=[reference(package)],
            )
            metadata_upstream.append(reference(binding))
        projection_contents = adapter_evidence[component].read_bytes()
        write(
            component,
            "metadata",
            component,
            outputs=[output(
                "adapter-evidence",
                f"outputs/evidence/{component}.json",
                projection_contents,
            )],
            contents={f"outputs/evidence/{component}.json": projection_contents},
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
        "publication_primaries": publication_primaries,
        "adapter_evidence": adapter_evidence,
        "adapter_receipts": adapter_receipts,
        "adapter_report_files": adapter_report_files,
        "package_stages": package_stages,
        "phase_stages": phase_stages,
        "distribution_manifest": fixture.manifest_path,
    }
