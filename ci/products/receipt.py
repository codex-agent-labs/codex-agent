from __future__ import annotations

from pathlib import Path
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
    require_semver,
    require_sha256,
    require_sorted_unique_records,
    require_string,
    sha256_bytes,
    validate_file_record,
    verify_regular_file_inventory,
)


PRODUCTS = {"contract", "runtime", "sdk"}
PHASES = {"binary", "package", "validation", "metadata"}
TRUST_DOMAINS = {"development", "release"}
EVENTS = {"pull_request", "merge_group", "workflow_dispatch", "push"}
OUTPUT_MANIFEST_NAME = "output-manifest.json"


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
        {
            "schemaVersion",
            "product",
            "component",
            "phase",
            "target",
            "productVersion",
            "outputs",
        },
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


def verify_output_manifest(root: Any, value: Any) -> dict[str, Any]:
    manifest = validate_output_manifest(value)
    root = Path(root)
    if load_canonical_json(root / OUTPUT_MANIFEST_NAME) != manifest:
        raise ValueError("Staged output-manifest.json does not match the supplied manifest")
    verify_regular_file_inventory(
        root,
        manifest["outputs"],
        with_kind=True,
        excluded_paths={OUTPUT_MANIFEST_NAME},
    )
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
