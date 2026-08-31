from __future__ import annotations

import argparse
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from .inventory import (
    canonical_json_bytes,
    load_canonical_json,
    require_array,
    require_boolean,
    require_exact_keys,
    require_identifier,
    require_integer,
    require_object,
    require_relative_path,
    require_regular_directory,
    require_semver,
    require_sha256,
    require_sorted_unique_records,
    require_string,
    regular_file_inventory,
    sha256_bytes,
    snapshot_regular_tree,
    validate_file_record,
    verify_regular_file_inventory,
    write_canonical_json,
)


PRODUCTS = {"contract", "runtime", "sdk"}
PHASES = {"binary", "package", "validation", "metadata"}
TRUST_DOMAINS = {"development", "release"}
EVENTS = {"pull_request", "merge_group", "workflow_dispatch", "push"}
OUTPUT_MANIFEST_NAME = "output-manifest.json"
OUTPUT_MANIFEST_KEYS = {
    "schemaVersion",
    "product",
    "component",
    "phase",
    "target",
    "productVersion",
    "outputs",
}


def _product(value: Any, label: str) -> str:
    product = require_identifier(value, label)
    if product not in PRODUCTS:
        raise ValueError(f"{label} is not a supported product")
    return product


def _phase(value: Any, label: str) -> str:
    phase = require_identifier(value, label)
    if phase not in PHASES:
        raise ValueError(f"{label} is not a supported product phase")
    return phase


def _records(values: Any, label: str, *, with_kind: bool) -> list[dict[str, Any]]:
    records = require_sorted_unique_records(values, label)
    return [
        validate_file_record(record, f"{label}[{index}]", with_kind=with_kind)
        for index, record in enumerate(records)
    ]


def validate_output_manifest(value: Any) -> dict[str, Any]:
    manifest = require_exact_keys(
        value,
        OUTPUT_MANIFEST_KEYS,
        "output manifest",
    )
    if require_integer(manifest["schemaVersion"], "output manifest.schemaVersion", 1) != 1:
        raise ValueError("Unsupported output manifest schemaVersion")
    _product(manifest["product"], "output manifest.product")
    require_identifier(manifest["component"], "output manifest.component")
    _phase(manifest["phase"], "output manifest.phase")
    require_identifier(manifest["target"], "output manifest.target")
    require_semver(manifest["productVersion"], "output manifest.productVersion")
    outputs = _records(manifest["outputs"], "output manifest.outputs", with_kind=True)
    if not outputs:
        raise ValueError("Output manifest must declare at least one output")
    if any(output["relativePath"] == OUTPUT_MANIFEST_NAME for output in outputs):
        raise ValueError("Output manifest cannot inventory itself")
    return manifest


def _remove_output_manifest(root: Path) -> None:
    manifest = root / OUTPUT_MANIFEST_NAME
    try:
        manifest.unlink()
    except FileNotFoundError:
        pass
    except IsADirectoryError as error:
        raise ValueError("Output manifest path must not be a directory") from error


def write_output_manifest(
    root: Any,
    product: Any,
    component: Any,
    phase: Any,
    target: Any,
    product_version: Any,
    output_roots: Any,
) -> dict[str, Any]:
    root = require_regular_directory(Path(root), "Output-manifest root")
    _remove_output_manifest(root)
    try:
        if type(output_roots) is not dict or not output_roots:
            raise ValueError("Output roots must be a non-empty kind-to-path object")
        roots = {
            require_identifier(kind, "output root kind"):
                require_relative_path(path, f"output root {kind}")
            for kind, path in output_roots.items()
        }
        if len(roots) != len(output_roots):
            raise ValueError("Output root kinds must be unique")
        paths = sorted(roots.values())
        if len(paths) != len(set(paths)):
            raise ValueError("Output root paths must be unique")
        parsed = {path: PurePosixPath(path) for path in paths}
        for path, value in parsed.items():
            if any(other_path != path and other in value.parents for other_path, other in parsed.items()):
                raise ValueError("Output root paths must not overlap")

        kinds_by_path = {path: kind for kind, path in roots.items()}

        records = regular_file_inventory(root, excluded_paths={OUTPUT_MANIFEST_NAME})
        counts = {path: 0 for path in paths}
        outputs = []
        for record in records:
            relative = PurePosixPath(record["relativePath"])
            matches = [path for path, value in parsed.items() if value in relative.parents]
            if len(matches) != 1:
                raise ValueError(
                    f"Staged output must belong to exactly one declared output root: {relative}"
                )
            path = matches[0]
            counts[path] += 1
            outputs.append({**record, "kind": kinds_by_path[path]})
        if any(count == 0 for count in counts.values()):
            raise ValueError("Every declared output root must contain at least one regular file")

        manifest = validate_output_manifest({
            "schemaVersion": 1,
            "product": product,
            "component": component,
            "phase": phase,
            "target": target,
            "productVersion": product_version,
            "outputs": outputs,
        })
        write_canonical_json(root / OUTPUT_MANIFEST_NAME, manifest)
        verify_output_manifest(root, manifest)
        return manifest
    except Exception:
        _remove_output_manifest(root)
        raise


def verify_output_manifest(root: Any, value: Any) -> dict[str, Any]:
    manifest = validate_output_manifest(value)
    root = require_regular_directory(Path(root), "Output-manifest root")
    if load_canonical_json(root / OUTPUT_MANIFEST_NAME) != manifest:
        raise ValueError("Staged output-manifest.json does not match the supplied manifest")
    verify_regular_file_inventory(
        root,
        manifest["outputs"],
        with_kind=True,
        excluded_paths={OUTPUT_MANIFEST_NAME},
    )
    return manifest


def verify_output_manifest_identity(
    root: Any,
    product: Any,
    component: Any,
    phase: Any,
    target: Any,
    product_version: Any,
) -> dict[str, Any]:
    root = Path(root)
    manifest = verify_output_manifest(root, load_canonical_json(root / OUTPUT_MANIFEST_NAME))
    expected = {
        "product": _product(product, "expected product"),
        "component": require_identifier(component, "expected component"),
        "phase": _phase(phase, "expected phase"),
        "target": require_identifier(target, "expected target"),
        "productVersion": require_semver(product_version, "expected productVersion"),
    }
    for field, value in expected.items():
        if manifest[field] != value:
            raise ValueError(f"Output manifest {field} does not match the expected identity")
    return manifest


def validate_producer(value: Any, label: str = "producer") -> dict[str, Any]:
    producer = require_exact_keys(
        value,
        {"repository", "workflowPath", "commit", "tree", "event", "runId", "runAttempt", "pullRequest"},
        label,
    )
    repository = require_relative_path(producer["repository"], f"{label}.repository")
    if repository.count("/") != 1:
        raise ValueError(f"{label}.repository must be an owner/repository pair")
    workflow = require_relative_path(producer["workflowPath"], f"{label}.workflowPath")
    if not workflow.startswith(".github/workflows/"):
        raise ValueError(f"{label}.workflowPath is not a workflow path")
    for field in ("commit", "tree"):
        value = require_string(producer[field], f"{label}.{field}")
        if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(f"{label}.{field} must be 40 lowercase hexadecimal characters")
    if producer["event"] not in EVENTS:
        raise ValueError(f"{label}.event is unsupported")
    require_integer(producer["runId"], f"{label}.runId", 1)
    require_integer(producer["runAttempt"], f"{label}.runAttempt", 1)
    if producer["event"] == "pull_request":
        require_integer(producer["pullRequest"], f"{label}.pullRequest", 1)
    elif producer["pullRequest"] is not None:
        raise ValueError(f"{label}.pullRequest must be null outside pull_request events")
    return producer


def validate_upstream(value: Any, label: str) -> dict[str, Any]:
    upstream = require_exact_keys(
        value,
        {"product", "component", "phase", "target", "buildKey", "outputsDigest"},
        label,
    )
    _product(upstream["product"], f"{label}.product")
    require_identifier(upstream["component"], f"{label}.component")
    _phase(upstream["phase"], f"{label}.phase")
    require_identifier(upstream["target"], f"{label}.target")
    require_sha256(upstream["buildKey"], f"{label}.buildKey")
    require_sha256(upstream["outputsDigest"], f"{label}.outputsDigest")
    return upstream


def validate_receipt_inputs(value: Any) -> dict[str, Any]:
    inputs = require_exact_keys(
        value,
        {
            "inventory",
            "phaseInputDigest",
            "versionIdentity",
            "upstreamArtifacts",
            "toolchainProfileDigest",
            "flagsDigest",
            "outputSchemaVersion",
        },
        "phase receipt.inputs",
    )
    _records(inputs["inventory"], "phase receipt.inputs.inventory", with_kind=False)
    require_sha256(inputs["phaseInputDigest"], "phase receipt.inputs.phaseInputDigest")
    if inputs["versionIdentity"] is not None:
        require_semver(inputs["versionIdentity"], "phase receipt.inputs.versionIdentity")
    upstream = require_array(inputs["upstreamArtifacts"], "phase receipt.inputs.upstreamArtifacts")
    validated = [validate_upstream(member, f"phase receipt.inputs.upstreamArtifacts[{index}]")
                 for index, member in enumerate(upstream)]
    identities = [
        (member["product"], member["component"], member["phase"], member["target"], member["buildKey"])
        for member in validated
    ]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise ValueError("phase receipt.inputs.upstreamArtifacts must be sorted and unique")
    require_sha256(inputs["toolchainProfileDigest"], "phase receipt.inputs.toolchainProfileDigest")
    require_sha256(inputs["flagsDigest"], "phase receipt.inputs.flagsDigest")
    if require_integer(inputs["outputSchemaVersion"], "phase receipt.inputs.outputSchemaVersion", 1) != 1:
        raise ValueError("Unsupported output schema version")
    return inputs


def build_key_payload(
    *,
    product: str,
    component: str,
    phase: str,
    target: str,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "product": product,
        "component": component,
        "phase": phase,
        "target": target,
        "versionIdentity": inputs["versionIdentity"],
        "phaseInputDigest": inputs["phaseInputDigest"],
        "upstreamArtifacts": inputs["upstreamArtifacts"],
        "toolchainProfileDigest": inputs["toolchainProfileDigest"],
        "flagsDigest": inputs["flagsDigest"],
        "outputSchemaVersion": inputs["outputSchemaVersion"],
    }


def compute_build_key(**values: Any) -> str:
    return sha256_bytes(canonical_json_bytes(build_key_payload(**values)))


def output_inventory_digest(outputs: Any) -> str:
    records = _records(outputs, "outputs", with_kind=True)
    return sha256_bytes(canonical_json_bytes(records))


def validate_phase_receipt(value: Any) -> dict[str, Any]:
    receipt = require_exact_keys(
        value,
        {
            "schemaVersion",
            "product",
            "component",
            "phase",
            "target",
            "productVersion",
            "buildKey",
            "inputs",
            "outputs",
            "producer",
            "trustDomain",
            "result",
        },
        "phase receipt",
    )
    if require_integer(receipt["schemaVersion"], "phase receipt.schemaVersion", 1) != 1:
        raise ValueError("Unsupported phase receipt schemaVersion")
    product = _product(receipt["product"], "phase receipt.product")
    component = require_identifier(receipt["component"], "phase receipt.component")
    phase = _phase(receipt["phase"], "phase receipt.phase")
    target = require_identifier(receipt["target"], "phase receipt.target")
    require_semver(receipt["productVersion"], "phase receipt.productVersion")
    inputs = validate_receipt_inputs(receipt["inputs"])
    if (
        inputs["versionIdentity"] is not None
        and inputs["versionIdentity"] != receipt["productVersion"]
        and (product != "runtime" or (component == "runtime-aggregate" and phase == "metadata"))
    ):
        raise ValueError("Phase receipt version identity does not match its product release")
    expected_key = compute_build_key(
        product=product,
        component=component,
        phase=phase,
        target=target,
        inputs=inputs,
    )
    if require_sha256(receipt["buildKey"], "phase receipt.buildKey") != expected_key:
        raise ValueError("Phase receipt buildKey does not match its canonical inputs")
    if not _records(receipt["outputs"], "phase receipt.outputs", with_kind=True):
        raise ValueError("Phase receipt must declare outputs")
    validate_producer(receipt["producer"])
    if receipt["trustDomain"] not in TRUST_DOMAINS:
        raise ValueError("Phase receipt trustDomain is invalid")
    if receipt["result"] != "success":
        raise ValueError("Only successful product phases produce reusable receipts")
    return receipt


def require_release_receipt(value: Any) -> dict[str, Any]:
    receipt = validate_phase_receipt(value)
    if receipt["trustDomain"] != "release":
        raise ValueError("Promotion requires a release-trust phase receipt")
    return receipt


def _parse_output_roots(values: list[str]) -> dict[str, str]:
    roots: dict[str, str] = {}
    for value in values:
        kind, separator, path = value.partition("=")
        if not separator or kind in roots:
            raise ValueError("Each --output-root must be a unique kind=relative/path value")
        roots[kind] = path
    return roots


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ci.products.receipt")
    subcommands = parser.add_subparsers(dest="command", required=True)
    writer = subcommands.add_parser("write-output-manifest")
    writer.add_argument("--root", required=True)
    writer.add_argument("--product", required=True)
    writer.add_argument("--component", required=True)
    writer.add_argument("--phase", required=True)
    writer.add_argument("--target", required=True)
    writer.add_argument("--product-version", required=True)
    writer.add_argument("--output-root", action="append", required=True)
    verifier = subcommands.add_parser("verify-output-manifest")
    verifier.add_argument("--root", required=True)
    verifier.add_argument("--product", required=True)
    verifier.add_argument("--component", required=True)
    verifier.add_argument("--phase", required=True)
    verifier.add_argument("--target", required=True)
    verifier.add_argument("--product-version", required=True)
    snapshot = subcommands.add_parser("snapshot-tree")
    snapshot.add_argument("--source", required=True)
    snapshot.add_argument("--destination", required=True)
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "write-output-manifest":
            write_output_manifest(
                arguments.root,
                arguments.product,
                arguments.component,
                arguments.phase,
                arguments.target,
                arguments.product_version,
                _parse_output_roots(arguments.output_root),
            )
        elif arguments.command == "verify-output-manifest":
            verify_output_manifest_identity(
                arguments.root,
                arguments.product,
                arguments.component,
                arguments.phase,
                arguments.target,
                arguments.product_version,
            )
        else:
            snapshot_regular_tree(Path(arguments.source), Path(arguments.destination))
    except ValueError as error:
        if arguments.command == "write-output-manifest":
            _remove_output_manifest(Path(arguments.root))
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
