from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Any

from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    read_regular_file_bytes,
    regular_file_inventory,
    require_array,
    require_boolean,
    require_exact_keys,
    require_identifier,
    require_integer,
    require_object,
    require_relative_path,
    require_semver,
    require_sha256,
    require_string,
    sha256_bytes,
    verified_zip_contents,
    write_canonical_json,
)
from .receipt import (
    output_inventory_digest,
    validate_output_manifest,
    validate_phase_receipt,
    validate_producer,
    verify_output_manifest,
)
from .signatures import validate_signing_metadata, verify_manifest_signature
from .contract_model import (
    CONTRACT_ARTIFACT_COMPONENTS,
    CONTRACT_CHECKSUM_SUFFIXES,
    CONTRACT_COMPONENTS,
    CONTRACT_MAVEN_ROLES,
    contract_component_digest,
    contract_digest,
    contract_evidence_identity,
    contract_maven_identity,
    contract_required_primary_paths,
    validate_contract_manifest,
    validate_contract_maven_inventory,
    verify_contract_bundle,
    verify_contract_git_inventories,
)


RUNTIME_TARGETS = ("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64")
RUNTIME_ADAPTERS = ("jvm", "node-js", "node-wasm")
RUNTIME_MAVEN_COMPONENTS = (
    "jvm",
    "linux-arm64",
    "linux-x64",
    "macos-arm64",
    "macos-x64",
    "node-js",
    "node-wasm",
    "windows-x64",
)
RUNTIME_VARIANT_ZIP_LIMITS = {
    "max_archive_bytes": 512 * 1024 * 1024,
    "max_central_directory_bytes": 32 * 1024 * 1024,
    "max_members": 4096,
    "max_entry_bytes": 256 * 1024 * 1024,
    "max_total_bytes": 1024 * 1024 * 1024,
    "max_compression_ratio": 200,
}
COMPATIBLE_RANGE = re.compile(
    r">=(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*) "
    r"<(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
)
REPOSITORY_EVIDENCE_IDENTITIES = {
    "contract": ("contract", "metadata", "common"),
    "runtime": ("runtime-aggregate", "metadata", "aggregate"),
    "sdk": ("sdk-core", "metadata", "common"),
}
REPOSITORY_EDGES = (
    ("contract", "runtime"),
    ("contract", "sdk"),
    ("runtime", "sdk"),
)
REPOSITORY_JSON_LIMIT = 16 * 1024 * 1024


def _sorted_unique(values: list[str], label: str) -> None:
    if values != sorted(values) or len(values) != len(set(values)):
        raise ValueError(f"{label} must be sorted and unique")


def _repository_evidence_root(value: Any, label: str) -> Path:
    root = Path(value)
    try:
        metadata = root.lstat()
        reparse = getattr(metadata, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0,
        )
        if stat.S_ISLNK(metadata.st_mode) or reparse or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError(f"{label} is missing or unsafe")
        return root.resolve(strict=True)
    except ValueError:
        raise
    except OSError as error:
        raise ValueError(f"{label} is missing or unsafe") from error


def _reject_repository_report_parent(path: Path) -> None:
    parent = path.parent
    for ancestor in (parent, *parent.parents):
        try:
            metadata = ancestor.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise ValueError("Repository evidence report parent is unsafe") from error
        reparse = getattr(metadata, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0,
        )
        if stat.S_ISLNK(metadata.st_mode) or reparse or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("Repository evidence report parent is unsafe")


def _invalidate_repository_report(output: Any, evidence_values: tuple[Any, ...]) -> Path:
    output_path = Path(os.path.abspath(output))
    output_candidates = {output_path, output_path.resolve(strict=False)}
    evidence_candidates = {
        candidate
        for value in evidence_values
        for candidate in {
            Path(os.path.abspath(value)),
            Path(os.path.abspath(value)).resolve(strict=False),
        }
    }
    if any(
        output_candidate == evidence_candidate
        or output_candidate.is_relative_to(evidence_candidate)
        or evidence_candidate.is_relative_to(output_candidate)
        for output_candidate in output_candidates
        for evidence_candidate in evidence_candidates
    ):
        raise ValueError("Repository evidence report overlaps an evidence directory")
    _reject_repository_report_parent(output_path)
    try:
        metadata = output_path.lstat()
    except FileNotFoundError:
        return output_path
    except OSError as error:
        raise ValueError("Repository evidence report is unsafe") from error
    reparse = getattr(metadata, "st_file_attributes", 0) & getattr(
        stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0,
    )
    if stat.S_ISLNK(metadata.st_mode) or reparse or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Repository evidence report is unsafe")
    output_path.unlink()
    return output_path


def _repository_directory_paths(root: Path) -> set[str]:
    result = set()
    for current, directories, _ in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in directories:
            path = current_path / name
            metadata = path.lstat()
            reparse = getattr(metadata, "st_file_attributes", 0) & getattr(
                stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0,
            )
            if stat.S_ISLNK(metadata.st_mode) or reparse or not stat.S_ISDIR(metadata.st_mode):
                raise ValueError("Repository evidence contains an unsafe directory")
            result.add(path.relative_to(root).as_posix())
    return result


def _repository_reference(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "product": receipt["product"],
        "component": receipt["component"],
        "phase": receipt["phase"],
        "target": receipt["target"],
        "buildKey": receipt["buildKey"],
        "outputsDigest": output_inventory_digest(receipt["outputs"]),
    }


def _verify_repository_product_evidence(
    root: Path,
    product: str,
    version: str,
    trust_domain: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt_path = root / "phase-receipt.json"
    outputs_root = root / "outputs"
    manifest_path = outputs_root / "output-manifest.json"
    receipt_bytes = read_regular_file_bytes(receipt_path, max_bytes=REPOSITORY_JSON_LIMIT)
    manifest_bytes = read_regular_file_bytes(manifest_path, max_bytes=REPOSITORY_JSON_LIMIT)
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    manifest = validate_output_manifest(load_canonical_json_bytes(manifest_bytes))
    component, phase, target = REPOSITORY_EVIDENCE_IDENTITIES[product]
    identity = (product, component, phase, target, version)
    if (
        receipt["product"],
        receipt["component"],
        receipt["phase"],
        receipt["target"],
        receipt["productVersion"],
    ) != identity:
        raise ValueError(f"{product} repository receipt identity is invalid")
    if receipt["inputs"]["versionIdentity"] != version:
        raise ValueError(f"{product} repository receipt version identity is invalid")
    if receipt["trustDomain"] != trust_domain:
        raise ValueError(f"{product} repository receipt trust domain is invalid")
    if (
        manifest["product"],
        manifest["component"],
        manifest["phase"],
        manifest["target"],
        manifest["productVersion"],
    ) != identity:
        raise ValueError(f"{product} repository output manifest identity is invalid")
    if receipt["outputs"] != manifest["outputs"]:
        raise ValueError(f"{product} repository receipt and output manifest disagree")
    verify_output_manifest(outputs_root, manifest)
    files = regular_file_inventory(root)
    expected_files = [
        {
            "relativePath": "phase-receipt.json",
            "bytes": len(receipt_bytes),
            "sha256": sha256_bytes(receipt_bytes),
        },
        {
            "relativePath": "outputs/output-manifest.json",
            "bytes": len(manifest_bytes),
            "sha256": sha256_bytes(manifest_bytes),
        },
        *[
            {
                "relativePath": f"outputs/{output['relativePath']}",
                "bytes": output["bytes"],
                "sha256": output["sha256"],
            }
            for output in manifest["outputs"]
        ],
    ]
    expected_files.sort(key=lambda record: record["relativePath"])
    expected_directories = {"outputs"}
    for output in manifest["outputs"]:
        path = PurePosixPath("outputs") / output["relativePath"]
        expected_directories.update(
            str(parent) for parent in path.parents if str(parent) not in {".", ""}
        )
    if files != expected_files or _repository_directory_paths(root) != expected_directories:
        raise ValueError(f"{product} repository evidence file set is incomplete or unexpected")
    if (
        read_regular_file_bytes(receipt_path, max_bytes=REPOSITORY_JSON_LIMIT) != receipt_bytes
        or read_regular_file_bytes(manifest_path, max_bytes=REPOSITORY_JSON_LIMIT) != manifest_bytes
    ):
        raise ValueError(f"{product} repository evidence changed during verification")
    return receipt, {
        "product": product,
        "component": component,
        "phase": phase,
        "target": target,
        "productVersion": version,
        "buildKey": receipt["buildKey"],
        "outputsDigest": output_inventory_digest(receipt["outputs"]),
        "receiptSha256": sha256_bytes(receipt_bytes),
        "outputManifestSha256": sha256_bytes(manifest_bytes),
        "files": files,
    }


def verify_repository_evidence(
    *,
    contract_evidence: Any,
    runtime_evidence: Any,
    sdk_evidence: Any,
    contract_version: Any,
    runtime_version: Any,
    sdk_version: Any,
    trust_domain: Any,
    output: Any,
) -> dict[str, Any]:
    evidence_values = (contract_evidence, runtime_evidence, sdk_evidence)
    output_path = _invalidate_repository_report(output, evidence_values)
    if trust_domain not in {"development", "release"}:
        raise ValueError("Repository evidence trust domain is invalid")
    versions = {
        "contract": require_semver(contract_version, "Contract version"),
        "runtime": require_semver(runtime_version, "Runtime version"),
        "sdk": require_semver(sdk_version, "SDK version"),
    }
    roots = {
        "contract": _repository_evidence_root(contract_evidence, "Contract evidence directory"),
        "runtime": _repository_evidence_root(runtime_evidence, "Runtime evidence directory"),
        "sdk": _repository_evidence_root(sdk_evidence, "SDK evidence directory"),
    }
    for product, root in roots.items():
        for other_product, other_root in roots.items():
            if product != other_product and (root == other_root or root.is_relative_to(other_root)):
                raise ValueError("Repository evidence directories must be distinct and non-nested")
    receipts: dict[str, dict[str, Any]] = {}
    product_records = []
    for product in ("contract", "runtime", "sdk"):
        receipt, record = _verify_repository_product_evidence(
            roots[product], product, versions[product], trust_domain,
        )
        receipts[product] = receipt
        product_records.append(record)
    references = {product: _repository_reference(receipt) for product, receipt in receipts.items()}
    for consumer in ("contract", "runtime", "sdk"):
        actual = [
            reference
            for reference in receipts[consumer]["inputs"]["upstreamArtifacts"]
            if reference["product"] != consumer
        ]
        expected = [
            references[producer]
            for producer, expected_consumer in REPOSITORY_EDGES
            if expected_consumer == consumer
        ]
        expected.sort(key=lambda reference: (
            reference["product"], reference["component"], reference["phase"],
            reference["target"], reference["buildKey"],
        ))
        if actual != expected:
            raise ValueError(f"{consumer} repository receipt has invalid cross-product references")
    report = {
        "schemaVersion": 1,
        "result": "passed",
        "trustDomain": trust_domain,
        "products": product_records,
        "edges": [
            {
                "producerProduct": producer,
                "consumerProduct": consumer,
                "buildKey": references[producer]["buildKey"],
                "outputsDigest": references[producer]["outputsDigest"],
            }
            for producer, consumer in REPOSITORY_EDGES
        ],
    }
    write_canonical_json(output_path, report)
    return report


def _stable_semver_tuple(value: Any, label: str) -> tuple[int, int, int]:
    version = require_semver(value, label)
    if "-" in version:
        raise ValueError(f"{label} must be a stable SemVer")
    return tuple(int(part) for part in version.split("."))


def _compatible_range(value: Any, label: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    text = require_string(value, label)
    if COMPATIBLE_RANGE.fullmatch(text) is None:
        raise ValueError(f"{label} must use exact '>=MAJOR.MINOR.PATCH <MAJOR.MINOR.PATCH' syntax")
    lower, upper = text[2:].split(" <", 1)
    bounds = tuple(tuple(int(part) for part in version.split(".")) for version in (lower, upper))
    if bounds[0] >= bounds[1]:
        raise ValueError(f"{label} lower bound must precede its upper bound")
    return bounds


def _artifact_record(value: Any, label: str, *, component: bool = False, target: bool = False) -> dict[str, Any]:
    keys = {"path", "role", "bytes", "sha256"}
    if component:
        keys.add("component")
    if target:
        keys.add("target")
    record = require_exact_keys(value, keys, label)
    require_relative_path(record["path"], f"{label}.path")
    require_identifier(record["role"], f"{label}.role")
    require_integer(record["bytes"], f"{label}.bytes", 1)
    require_sha256(record["sha256"], f"{label}.sha256")
    if component:
        require_identifier(record["component"], f"{label}.component")
    if target:
        require_identifier(record["target"], f"{label}.target")
    return record


def _artifact_records(
    values: Any,
    label: str,
    *,
    component: bool = False,
    target: bool = False,
    nonempty: bool = True,
) -> list[dict[str, Any]]:
    records = [
        _artifact_record(member, f"{label}[{index}]", component=component, target=target)
        for index, member in enumerate(require_array(values, label))
    ]
    paths = [record["path"] for record in records]
    _sorted_unique(paths, label)
    if nonempty and not records:
        raise ValueError(f"{label} must not be empty")
    return records


def _contract_reference(value: Any, label: str, *, with_component: bool) -> dict[str, Any]:
    keys = {"version", "digest"}
    if with_component:
        keys.add("componentDigest")
    reference = require_exact_keys(value, keys, label)
    require_semver(reference["version"], f"{label}.version")
    require_sha256(reference["digest"], f"{label}.digest")
    if with_component:
        require_sha256(reference["componentDigest"], f"{label}.componentDigest")
    return reference


def runtime_component_id(value: dict[str, Any]) -> str:
    identity = {
        "appServer": value["appServer"],
        "cAbi": value["cAbi"],
        "contract": value["contract"],
        "runtimeCompatibilityVersion": value["runtimeCompatibilityVersion"],
        "target": value["target"],
        "binaryBuildKey": value["inputs"]["binaryBuildKey"],
        "binaryOutputInventoryDigest": value["inputs"]["binaryOutputInventoryDigest"],
        "toolchainProfile": value["toolchainProfile"],
    }
    return sha256_bytes(canonical_json_bytes(identity))


def validate_runtime_variant(value: Any) -> dict[str, Any]:
    variant = require_exact_keys(
        value,
        {
            "schemaVersion",
            "product",
            "componentId",
            "runtimeCompatibilityVersion",
            "target",
            "contract",
            "cAbi",
            "appServer",
            "inputs",
            "innerArtifacts",
            "toolchainProfile",
            "signing",
        },
        "Runtime variant manifest",
    )
    if require_integer(variant["schemaVersion"], "Runtime variant.schemaVersion", 1) != 1:
        raise ValueError("Unsupported Runtime variant schemaVersion")
    if variant["product"] != "runtime":
        raise ValueError("Runtime variant product must be runtime")
    require_semver(variant["runtimeCompatibilityVersion"], "Runtime variant.runtimeCompatibilityVersion")
    if variant["target"] not in RUNTIME_TARGETS:
        raise ValueError("Runtime variant target is unsupported")
    _contract_reference(variant["contract"], "Runtime variant.contract", with_component=True)
    c_abi = require_exact_keys(
        variant["cAbi"],
        {
            "version",
            "minimumCompatibleVersion",
            "identitySchemaVersion",
            "headerSha256",
            "symbolSetSha256",
            "symbolCount",
        },
        "Runtime variant.cAbi",
    )
    current_abi = _stable_semver_tuple(c_abi["version"], "Runtime variant.cAbi.version")
    minimum_abi = _stable_semver_tuple(
        c_abi["minimumCompatibleVersion"], "Runtime variant.cAbi.minimumCompatibleVersion",
    )
    if minimum_abi[0] != current_abi[0] or minimum_abi > current_abi:
        raise ValueError("Runtime variant minimum C ABI must share the current major and not exceed current")
    require_integer(c_abi["identitySchemaVersion"], "Runtime variant.cAbi.identitySchemaVersion", 1)
    require_sha256(c_abi["headerSha256"], "Runtime variant.cAbi.headerSha256")
    require_sha256(c_abi["symbolSetSha256"], "Runtime variant.cAbi.symbolSetSha256")
    require_integer(c_abi["symbolCount"], "Runtime variant.cAbi.symbolCount", 1)
    app_server = require_exact_keys(
        variant["appServer"], {"version", "releaseTag", "binarySha256"}, "Runtime variant.appServer",
    )
    require_semver(app_server["version"], "Runtime variant.appServer.version")
    if app_server["releaseTag"] != f"rust-v{app_server['version']}":
        raise ValueError("Runtime variant app-server release tag/version mismatch")
    require_sha256(app_server["binarySha256"], "Runtime variant.appServer.binarySha256")
    inputs = require_exact_keys(
        variant["inputs"],
        {
            "binaryBuildKey",
            "binaryOutputInventoryDigest",
            "binaryReceiptSha256",
            "packageReceiptSha256",
            "validationReceiptSha256",
        },
        "Runtime variant.inputs",
    )
    for field in inputs:
        require_sha256(inputs[field], f"Runtime variant.inputs.{field}")
    artifacts = _artifact_records(variant["innerArtifacts"], "Runtime variant.innerArtifacts")
    if any(record["path"] in {"runtime-variant-manifest.json", "runtime-variant-manifest.sig"}
           for record in artifacts):
        raise ValueError("Runtime variant innerArtifacts cannot contain its manifest or signature")
    required_prefixes = {"c-abi", "app-server", "evidence"}
    if {record["path"].split("/", 1)[0] for record in artifacts} != required_prefixes:
        raise ValueError("Runtime variant innerArtifacts must cover c-abi, app-server, and evidence")
    required_roles = {
        "app-server-archive",
        "binary-receipt",
        "c-abi-archive",
        "package-receipt",
        "provenance",
        "sbom",
        "validation",
        "validation-receipt",
    }
    roles = [record["role"] for record in artifacts]
    if set(roles) != required_roles or len(roles) != len(required_roles):
        raise ValueError("Runtime variant innerArtifacts role inventory is incomplete")
    expected_prefix = {
        "app-server-archive": "app-server/",
        "c-abi-archive": "c-abi/",
    }
    if any(not record["path"].startswith(expected_prefix.get(record["role"], "evidence/"))
           for record in artifacts):
        raise ValueError("Runtime variant inner artifact role/path scope mismatch")
    role_records = {record["role"]: record for record in artifacts}
    for role, field in (
        ("binary-receipt", "binaryReceiptSha256"),
        ("package-receipt", "packageReceiptSha256"),
        ("validation-receipt", "validationReceiptSha256"),
    ):
        if role_records[role]["sha256"] != inputs[field]:
            raise ValueError(f"Runtime variant {role} digest does not match inputs.{field}")
    toolchain = require_exact_keys(variant["toolchainProfile"], {"id", "digest"}, "Runtime variant.toolchainProfile")
    if require_identifier(toolchain["id"], "Runtime variant.toolchainProfile.id") != variant["target"]:
        raise ValueError("Runtime variant toolchain profile ID must equal its target")
    require_sha256(toolchain["digest"], "Runtime variant.toolchainProfile.digest")
    if require_sha256(variant["componentId"], "Runtime variant.componentId") != runtime_component_id(variant):
        raise ValueError("Runtime variant componentId mismatch")
    validate_signing_metadata(variant["signing"])
    return variant


def _runtime_variant_record(value: Any, label: str) -> dict[str, Any]:
    record = require_exact_keys(
        value,
        {
            "target",
            "componentId",
            "bundleSha256",
            "manifestSha256",
            "receiptSha256",
            "sourceRuntimeVersion",
            "reused",
            "producer",
        },
        label,
    )
    if record["target"] not in RUNTIME_TARGETS:
        raise ValueError(f"{label}.target is unsupported")
    for field in ("componentId", "bundleSha256", "manifestSha256", "receiptSha256"):
        require_sha256(record[field], f"{label}.{field}")
    require_semver(record["sourceRuntimeVersion"], f"{label}.sourceRuntimeVersion")
    require_boolean(record["reused"], f"{label}.reused")
    validate_producer(record["producer"], f"{label}.producer")
    return record


def validate_runtime_aggregate(value: Any) -> dict[str, Any]:
    aggregate = require_exact_keys(
        value,
        {
            "schemaVersion",
            "product",
            "runtimeVersion",
            "runtimeCompatibilityVersion",
            "contract",
            "variants",
            "runtimeMavenFiles",
            "adapterEvidence",
            "compatibility",
            "signing",
        },
        "Runtime aggregate",
    )
    if require_integer(aggregate["schemaVersion"], "Runtime aggregate.schemaVersion", 1) != 1:
        raise ValueError("Unsupported Runtime aggregate schemaVersion")
    if aggregate["product"] != "runtime":
        raise ValueError("Runtime aggregate product must be runtime")
    require_semver(aggregate["runtimeVersion"], "Runtime aggregate.runtimeVersion")
    require_semver(aggregate["runtimeCompatibilityVersion"], "Runtime aggregate.runtimeCompatibilityVersion")
    _contract_reference(aggregate["contract"], "Runtime aggregate.contract", with_component=False)
    variants = [
        _runtime_variant_record(member, f"Runtime aggregate.variants[{index}]")
        for index, member in enumerate(require_array(aggregate["variants"], "Runtime aggregate.variants"))
    ]
    targets = [record["target"] for record in variants]
    if tuple(targets) != RUNTIME_TARGETS:
        raise ValueError("Runtime aggregate must contain exactly five sorted supported targets")
    if len({record["componentId"] for record in variants}) != len(variants):
        raise ValueError("Runtime aggregate component IDs must be distinct")
    maven_files = _artifact_records(aggregate["runtimeMavenFiles"], "Runtime aggregate.runtimeMavenFiles", component=True)
    if any(
        not record["path"].startswith("maven/") or record["role"] not in CONTRACT_MAVEN_ROLES
        for record in maven_files
    ):
        raise ValueError("Runtime aggregate Maven inventory has an unsupported scope or role")
    if set(record["component"] for record in maven_files) != set(RUNTIME_MAVEN_COMPONENTS):
        raise ValueError("Runtime aggregate Maven inventory must cover JVM, Native, Node JS, and Node Wasm")
    if {
        record["component"] for record in maven_files if record["role"] == "runtime-resolution"
    } != set(RUNTIME_MAVEN_COMPONENTS):
        raise ValueError("Every Runtime Maven component requires a runtime-resolution artifact")
    evidence = _artifact_records(aggregate["adapterEvidence"], "Runtime aggregate.adapterEvidence", target=True)
    if any(record["role"] != "adapter" or not record["path"].startswith("evidence/") for record in evidence):
        raise ValueError("Runtime aggregate adapter evidence scope and role are invalid")
    if set(record["target"] for record in evidence) != set(RUNTIME_ADAPTERS):
        raise ValueError("Runtime aggregate adapter evidence must cover JVM, Node JS, and Node Wasm")
    compatibility = require_exact_keys(
        aggregate["compatibility"],
        {
            "cAbiVersion",
            "minimumCAbiVersion",
            "identitySchema",
            "headerSha256",
            "symbolSetSha256",
            "symbolCount",
            "appServerVersion",
            "appServerReleaseTag",
            "toolchainProfileDigests",
        },
        "Runtime aggregate.compatibility",
    )
    current_abi = _stable_semver_tuple(
        compatibility["cAbiVersion"], "Runtime aggregate.compatibility.cAbiVersion",
    )
    minimum_abi = _stable_semver_tuple(
        compatibility["minimumCAbiVersion"], "Runtime aggregate.compatibility.minimumCAbiVersion",
    )
    if minimum_abi[0] != current_abi[0] or minimum_abi > current_abi:
        raise ValueError("Runtime aggregate minimum C ABI must share the current major and not exceed current")
    require_integer(compatibility["identitySchema"], "Runtime aggregate.compatibility.identitySchema", 1)
    require_sha256(compatibility["headerSha256"], "Runtime aggregate.compatibility.headerSha256")
    require_sha256(compatibility["symbolSetSha256"], "Runtime aggregate.compatibility.symbolSetSha256")
    require_integer(compatibility["symbolCount"], "Runtime aggregate.compatibility.symbolCount", 1)
    require_semver(compatibility["appServerVersion"], "Runtime aggregate.compatibility.appServerVersion")
    if compatibility["appServerReleaseTag"] != f"rust-v{compatibility['appServerVersion']}":
        raise ValueError("Runtime aggregate app-server release tag/version mismatch")
    profiles = require_exact_keys(
        compatibility["toolchainProfileDigests"], RUNTIME_TARGETS,
        "Runtime aggregate.compatibility.toolchainProfileDigests",
    )
    for target, digest in profiles.items():
        require_sha256(digest, f"Runtime aggregate toolchain profile {target}")
    validate_signing_metadata(aggregate["signing"])
    return aggregate


def _runtime_variant_bundle_name(target: str, component_id: str) -> str:
    return f"codex-agent-runtime-variant-{target}-{component_id.removeprefix('sha256:')}.zip"


def verify_runtime_aggregate_artifacts(
    value: Any,
    *,
    contract_manifest: Any,
    variant_bundles: dict[str, Path],
    metadata_receipts: dict[str, Path],
    trusted_public_keys: dict[str, Path],
    required_trust_domain: str,
) -> dict[str, Any]:
    aggregate = validate_runtime_aggregate(value)
    contract = validate_contract_manifest(contract_manifest)
    if required_trust_domain not in {"development", "release"}:
        raise ValueError("Required Runtime aggregate trust domain is invalid")
    for mapping, label in (
        (variant_bundles, "Runtime variant bundles"),
        (metadata_receipts, "Runtime metadata receipts"),
        (trusted_public_keys, "Runtime variant public keys"),
    ):
        if type(mapping) is not dict or set(mapping) != set(RUNTIME_TARGETS):
            raise ValueError(f"{label} must contain exactly the five Runtime targets")
    if aggregate["signing"]["trustDomain"] != required_trust_domain:
        raise ValueError("Runtime aggregate signing trust domain mismatch")
    if contract["signing"]["trustDomain"] != required_trust_domain:
        raise ValueError("Contract signing trust domain mismatch")
    if (
        aggregate["contract"]["version"] != contract["contractVersion"]
        or aggregate["contract"]["digest"] != contract["contractDigest"]
    ):
        raise ValueError("Runtime aggregate does not reference the authenticated Contract")

    records = {record["target"]: record for record in aggregate["variants"]}
    compatibility = aggregate["compatibility"]
    for target in RUNTIME_TARGETS:
        record = records[target]
        bundle = Path(variant_bundles[target])
        expected_name = _runtime_variant_bundle_name(target, record["componentId"])
        if bundle.name != expected_name:
            raise ValueError(f"Runtime variant bundle identity mismatch: {target}")

        manifest_name = "runtime-variant-manifest.json"
        signature_name = "runtime-variant-manifest.sig"
        zip_records, authenticated_contents, archive_identity = verified_zip_contents(
            bundle,
            **RUNTIME_VARIANT_ZIP_LIMITS,
            retained_paths={manifest_name, signature_name},
            max_retained_bytes=2 * 1024 * 1024,
        )
        if archive_identity["sha256"] != record["bundleSha256"]:
            raise ValueError(f"Runtime variant bundle identity mismatch: {target}")
        inventory = {member["relativePath"]: member for member in zip_records}
        if manifest_name not in inventory or signature_name not in inventory:
            raise ValueError(f"Runtime variant bundle lacks its manifest or signature: {target}")
        manifest_bytes = authenticated_contents[manifest_name]
        signature_bytes = authenticated_contents[signature_name]
        if sha256_bytes(manifest_bytes) != record["manifestSha256"]:
            raise ValueError(f"Runtime variant manifest digest mismatch: {target}")
        variant = validate_runtime_variant(load_canonical_json_bytes(manifest_bytes))
        declared = {
            member["path"]: {
                "relativePath": member["path"],
                "bytes": member["bytes"],
                "sha256": member["sha256"],
            }
            for member in variant["innerArtifacts"]
        }
        if set(inventory) != {manifest_name, signature_name} | set(declared) or any(
            inventory[path] != member for path, member in declared.items()
        ):
            raise ValueError(f"Runtime variant bundle file set or inner artifact differs: {target}")

        with tempfile.TemporaryDirectory(prefix="codex-agent-variant-signature-") as temporary:
            manifest_path = Path(temporary) / manifest_name
            signature_path = Path(temporary) / signature_name
            manifest_path.write_bytes(manifest_bytes)
            signature_path.write_bytes(signature_bytes)
            verify_manifest_signature(
                manifest_path,
                signature_path,
                Path(trusted_public_keys[target]),
                variant["signing"],
            )

        if variant["signing"]["trustDomain"] != required_trust_domain:
            raise ValueError(f"Runtime variant signing trust domain mismatch: {target}")
        role_records = {member["role"]: member for member in variant["innerArtifacts"]}
        receipt_paths = {
            role_records[role]["path"]
            for role in ("binary-receipt", "package-receipt", "validation-receipt")
        }
        receipt_zip_records, receipt_contents, receipt_archive_identity = verified_zip_contents(
            bundle,
            **RUNTIME_VARIANT_ZIP_LIMITS,
            retained_paths=receipt_paths,
            max_retained_bytes=16 * 1024 * 1024,
        )
        if receipt_zip_records != zip_records or receipt_archive_identity != archive_identity:
            raise ValueError(f"Runtime variant bundle changed during verification: {target}")
        phase_receipts = {
            phase: validate_phase_receipt(
                load_canonical_json_bytes(receipt_contents[role_records[role]["path"]])
            )
            for phase, role in (
                ("binary", "binary-receipt"),
                ("package", "package-receipt"),
                ("validation", "validation-receipt"),
            )
        }
        for phase, receipt in phase_receipts.items():
            if (
                receipt["product"] != "runtime"
                or receipt["component"] != f"runtime-{target}"
                or receipt["phase"] != phase
                or receipt["target"] != target
                or receipt["inputs"]["versionIdentity"] != aggregate["runtimeCompatibilityVersion"]
                or receipt["trustDomain"] != required_trust_domain
            ):
                raise ValueError(f"Runtime variant {phase} receipt disagrees with its manifest: {target}")
        binary_receipt = phase_receipts["binary"]
        if (
            binary_receipt["buildKey"] != variant["inputs"]["binaryBuildKey"]
            or output_inventory_digest(binary_receipt["outputs"]) !=
                variant["inputs"]["binaryOutputInventoryDigest"]
        ):
            raise ValueError(f"Runtime variant binary receipt identity mismatch: {target}")
        expected_c_abi = {
            "version": compatibility["cAbiVersion"],
            "minimumCompatibleVersion": compatibility["minimumCAbiVersion"],
            "identitySchemaVersion": compatibility["identitySchema"],
            "headerSha256": compatibility["headerSha256"],
            "symbolSetSha256": compatibility["symbolSetSha256"],
            "symbolCount": compatibility["symbolCount"],
        }
        if (
            variant["target"] != target
            or variant["componentId"] != record["componentId"]
            or variant["runtimeCompatibilityVersion"] != aggregate["runtimeCompatibilityVersion"]
            or variant["contract"] != {
                "version": contract["contractVersion"],
                "digest": contract["contractDigest"],
                "componentDigest": contract["components"][target]["sha256"],
            }
            or variant["cAbi"] != expected_c_abi
            or variant["appServer"]["version"] != compatibility["appServerVersion"]
            or variant["appServer"]["releaseTag"] != compatibility["appServerReleaseTag"]
            or variant["toolchainProfile"] != {
                "id": target,
                "digest": compatibility["toolchainProfileDigests"][target],
            }
        ):
            raise ValueError(f"Runtime variant manifest disagrees with its aggregate: {target}")

        receipt_path = Path(metadata_receipts[target])
        receipt_bytes = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024)
        if sha256_bytes(receipt_bytes) != record["receiptSha256"]:
            raise ValueError(f"Runtime variant metadata receipt digest mismatch: {target}")
        receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
        bundle_output = {
            "kind": "runtime-variant",
            "relativePath": bundle.name,
            "bytes": archive_identity["bytes"],
            "sha256": record["bundleSha256"],
        }
        if (
            receipt["product"] != "runtime"
            or receipt["component"] != f"runtime-{target}"
            or receipt["phase"] != "metadata"
            or receipt["target"] != target
            or receipt["productVersion"] != record["sourceRuntimeVersion"]
            or receipt["inputs"]["versionIdentity"] != aggregate["runtimeCompatibilityVersion"]
            or receipt["trustDomain"] != required_trust_domain
            or receipt["producer"] != record["producer"]
            or receipt["outputs"] != [bundle_output]
        ):
            raise ValueError(f"Runtime variant metadata receipt disagrees with its aggregate: {target}")
    return aggregate


def validate_sdk_compatibility(value: Any) -> dict[str, Any]:
    compatibility = require_exact_keys(
        value, {"schemaVersion", "sdkVersion", "contract", "runtime", "platformRuntime"},
        "SDK compatibility",
    )
    if require_integer(compatibility["schemaVersion"], "SDK compatibility.schemaVersion", 1) != 1:
        raise ValueError("Unsupported SDK compatibility schemaVersion")
    require_semver(compatibility["sdkVersion"], "SDK compatibility.sdkVersion")
    contract = _contract_reference(compatibility["contract"], "SDK compatibility.contract", with_component=False)
    runtime = require_exact_keys(
        compatibility["runtime"],
        {
            "compatibleReleaseRange",
            "compatibleRuntimeCompatibilityRange",
            "requiredIdentitySchema",
            "requiredContractDigest",
            "requiredAbiMajor",
            "minimumAbiMinor",
            "defaultRuntimeVersion",
            "defaultManifestSha256",
            "embeddedVariants",
        },
        "SDK compatibility.runtime",
    )
    release_bounds = _compatible_range(
        runtime["compatibleReleaseRange"], "SDK compatibility.runtime.compatibleReleaseRange",
    )
    _compatible_range(
        runtime["compatibleRuntimeCompatibilityRange"],
        "SDK compatibility.runtime.compatibleRuntimeCompatibilityRange",
    )
    if require_integer(runtime["requiredIdentitySchema"], "SDK compatibility.runtime.requiredIdentitySchema", 1) != 1:
        raise ValueError("SDK compatibility requires Runtime identity schema 1")
    if require_sha256(runtime["requiredContractDigest"], "SDK compatibility.runtime.requiredContractDigest") != \
            contract["digest"]:
        raise ValueError("SDK compatibility required Contract digest mismatch")
    if require_integer(runtime["requiredAbiMajor"], "SDK compatibility.runtime.requiredAbiMajor", 1) != 1:
        raise ValueError("SDK compatibility requires C ABI major 1")
    if require_integer(runtime["minimumAbiMinor"], "SDK compatibility.runtime.minimumAbiMinor", 0) != 13:
        raise ValueError("SDK compatibility minimum C ABI minor must be 13")
    default_runtime = require_semver(
        runtime["defaultRuntimeVersion"], "SDK compatibility.runtime.defaultRuntimeVersion",
    )
    if "-" in default_runtime:
        raise ValueError("SDK compatibility default Runtime version must be a stable SemVer")
    default_tuple = tuple(int(part) for part in default_runtime.split("."))
    if not release_bounds[0] <= default_tuple < release_bounds[1]:
        raise ValueError("SDK compatibility default Runtime version is outside compatibleReleaseRange")
    require_sha256(runtime["defaultManifestSha256"], "SDK compatibility.runtime.defaultManifestSha256")
    embedded = []
    for index, member in enumerate(require_array(runtime["embeddedVariants"], "SDK compatibility.runtime.embeddedVariants")):
        record = require_exact_keys(
            member,
            {"target", "componentId", "bundleSha256", "manifestSha256", "runtimeLibrarySha256"},
            f"SDK compatibility embedded variant[{index}]",
        )
        if record["target"] not in RUNTIME_TARGETS:
            raise ValueError("SDK compatibility embedded target is unsupported")
        for field in ("componentId", "bundleSha256", "manifestSha256", "runtimeLibrarySha256"):
            require_sha256(record[field], f"SDK compatibility embedded variant[{index}].{field}")
        embedded.append(record)
    targets = [record["target"] for record in embedded]
    if targets != sorted(RUNTIME_TARGETS):
        raise ValueError("SDK compatibility embedded variants must contain exactly five sorted Desktop targets")
    if len({record["componentId"] for record in embedded}) != len(embedded):
        raise ValueError("SDK compatibility embedded component IDs must be unique")
    if len({record["manifestSha256"] for record in embedded}) != len(embedded):
        raise ValueError("SDK compatibility embedded manifest digests must be unique")
    platform = require_exact_keys(compatibility["platformRuntime"], {"android", "ios"}, "SDK platformRuntime")
    for name in ("android", "ios"):
        record = require_exact_keys(platform[name], {"owner", "desktopRuntimeApplicable"}, f"SDK platformRuntime.{name}")
        if record["owner"] != "sdk" or require_boolean(
            record["desktopRuntimeApplicable"], f"SDK platformRuntime.{name}.desktopRuntimeApplicable",
        ):
            raise ValueError(f"SDK platformRuntime.{name} must be SDK-owned and Desktop-inapplicable")
    return compatibility


def _index_entry(value: Any, label: str) -> dict[str, Any]:
    entry = require_exact_keys(
        value,
        {
            "buildKey",
            "product",
            "component",
            "phase",
            "target",
            "productVersion",
            "coordinate",
            "outputInventoryDigest",
            "outputs",
            "artifactName",
            "artifactSha256",
            "receiptSha256",
        },
        label,
    )
    require_sha256(entry["buildKey"], f"{label}.buildKey")
    if entry["product"] not in {"contract", "runtime", "sdk"}:
        raise ValueError(f"{label}.product is unsupported")
    require_identifier(entry["component"], f"{label}.component")
    if entry["phase"] not in {"binary", "package", "validation", "metadata"}:
        raise ValueError(f"{label}.phase is unsupported")
    require_identifier(entry["target"], f"{label}.target")
    require_semver(entry["productVersion"], f"{label}.productVersion")
    require_string(entry["coordinate"], f"{label}.coordinate")
    require_relative_path(entry["artifactName"], f"{label}.artifactName")
    require_sha256(entry["artifactSha256"], f"{label}.artifactSha256")
    require_sha256(entry["receiptSha256"], f"{label}.receiptSha256")
    outputs = entry["outputs"]
    if not require_array(outputs, f"{label}.outputs"):
        raise ValueError(f"{label}.outputs must not be empty")
    if require_sha256(entry["outputInventoryDigest"], f"{label}.outputInventoryDigest") != \
            output_inventory_digest(outputs):
        raise ValueError(f"{label}.outputInventoryDigest mismatch")
    artifact_outputs = [output for output in outputs if output["relativePath"] == entry["artifactName"]]
    if len(artifact_outputs) != 1 or artifact_outputs[0]["sha256"] != entry["artifactSha256"]:
        raise ValueError(f"{label} artifact must name one digest-matching declared output")
    return entry


def _sha(value: Any, label: str) -> str:
    text = require_string(value, label)
    if len(text) != 40 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{label} must be 40 lowercase hexadecimal characters")
    return text


def _index_context(value: Any) -> dict[str, Any]:
    context = require_object(value, "product index.context")
    kind = context.get("kind")
    if kind == "stable":
        context = require_exact_keys(context, {"kind", "tag"}, "product index.context")
        require_relative_path(context["tag"], "product index.context.tag")
    elif kind == "promoted-main":
        context = require_exact_keys(
            context,
            {"kind", "commit", "tree", "promotionRunId", "promotionRunAttempt"},
            "product index.context",
        )
        _sha(context["commit"], "product index.context.commit")
        _sha(context["tree"], "product index.context.tree")
        require_integer(context["promotionRunId"], "product index.context.promotionRunId", 1)
        require_integer(context["promotionRunAttempt"], "product index.context.promotionRunAttempt", 1)
    elif kind == "pull-request":
        context = require_exact_keys(
            context,
            {"kind", "pullRequest", "commit", "tree", "runId", "runAttempt"},
            "product index.context",
        )
        require_integer(context["pullRequest"], "product index.context.pullRequest", 1)
        _sha(context["commit"], "product index.context.commit")
        _sha(context["tree"], "product index.context.tree")
        require_integer(context["runId"], "product index.context.runId", 1)
        require_integer(context["runAttempt"], "product index.context.runAttempt", 1)
    else:
        raise ValueError("Product index context kind is unsupported")
    return context


def _release_identity(entry: dict[str, Any]) -> tuple[str, str]:
    return entry["product"], entry["productVersion"]


def _logical_asset_identity(entry: dict[str, Any]) -> tuple[str, str, str]:
    return entry["component"], entry["phase"], entry["target"]


def _release_output_projection(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "component": entry["component"],
            "phase": entry["phase"],
            "target": entry["target"],
            "coordinate": entry["coordinate"],
            "artifactName": entry["artifactName"],
            "artifactSha256": entry["artifactSha256"],
            "outputInventoryDigest": entry["outputInventoryDigest"],
            "outputs": entry["outputs"],
        }
        for entry in sorted(entries, key=_logical_asset_identity)
    ]


def validate_product_index(value: Any) -> dict[str, Any]:
    index = require_exact_keys(
        value,
        {"schemaVersion", "repository", "context", "entries", "trustDomain", "signing", "producer"},
        "product index",
    )
    if require_integer(index["schemaVersion"], "product index.schemaVersion", 1) != 1:
        raise ValueError("Unsupported product index schemaVersion")
    repository = require_relative_path(index["repository"], "product index.repository")
    if repository.count("/") != 1:
        raise ValueError("Product index repository must be an owner/repository pair")
    context = _index_context(index["context"])
    entries = [
        _index_entry(member, f"product index.entries[{position}]")
        for position, member in enumerate(require_array(index["entries"], "product index.entries"))
    ]
    if not entries:
        raise ValueError("Product index entries must not be empty")
    keys = [entry["buildKey"] for entry in entries]
    _sorted_unique(keys, "product index.entries")
    release_assets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in entries:
        release_assets.setdefault(_release_identity(entry), []).append(entry)
    for identity, assets in release_assets.items():
        logical = [_logical_asset_identity(entry) for entry in assets]
        names = [entry["artifactName"] for entry in assets]
        if len(logical) != len(set(logical)) or len(names) != len(set(names)):
            raise ValueError(f"Product index contains duplicate release assets for {identity}")
    signing = validate_signing_metadata(index["signing"])
    if index["trustDomain"] not in {"development", "release"} or signing["trustDomain"] != index["trustDomain"]:
        raise ValueError("Product index trustDomain does not match signing metadata")
    producer = validate_producer(index["producer"], "product index.producer")
    if producer["repository"] != repository:
        raise ValueError("Product index producer repository mismatch")
    if context["kind"] == "pull-request" and (
        producer["event"] != "pull_request"
        or producer["pullRequest"] != context["pullRequest"]
        or producer["commit"] != context["commit"]
        or producer["tree"] != context["tree"]
        or producer["runId"] != context["runId"]
        or producer["runAttempt"] != context["runAttempt"]
    ):
        raise ValueError("Pull-request product index context/producer mismatch")
    if context["kind"] in {"stable", "promoted-main"} and index["trustDomain"] != "release":
        raise ValueError("Stable and promoted-main product indexes require release trust")
    if context["kind"] in {"stable", "promoted-main"} and producer["event"] != "push":
        raise ValueError("Stable and promoted-main product indexes require a push producer")
    if context["kind"] == "promoted-main" and (
        producer["commit"] != context["commit"]
        or producer["tree"] != context["tree"]
        or producer["runId"] != context["promotionRunId"]
        or producer["runAttempt"] != context["promotionRunAttempt"]
    ):
        raise ValueError("Promoted-main product index context/producer mismatch")
    return index


def verify_immutable_product_indexes(existing: Any, candidate: Any) -> None:
    prior = validate_product_index(existing)["entries"]
    proposed = validate_product_index(candidate)["entries"]
    by_build_key = {entry["buildKey"]: entry for entry in prior}
    prior_releases: dict[tuple[str, str], list[dict[str, Any]]] = {}
    proposed_releases: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in prior:
        prior_releases.setdefault(_release_identity(entry), []).append(entry)
    for entry in proposed:
        proposed_releases.setdefault(_release_identity(entry), []).append(entry)
    for entry in proposed:
        if entry["buildKey"] in by_build_key and (
            by_build_key[entry["buildKey"]]["outputInventoryDigest"] != entry["outputInventoryDigest"]
            or by_build_key[entry["buildKey"]]["outputs"] != entry["outputs"]
        ):
            raise ValueError("Identical product build key has a conflicting output inventory")
    for identity in set(prior_releases) & set(proposed_releases):
        if _release_output_projection(prior_releases[identity]) != \
                _release_output_projection(proposed_releases[identity]):
            raise ValueError("Stable product identity has different asset names or output bytes")


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify aggregate product evidence")
    commands = parser.add_subparsers(dest="command", required=True)
    repository = commands.add_parser(
        "verify-repository",
        help="Verify independently supplied Contract, Runtime, and SDK evidence",
    )
    repository.add_argument("--contract-evidence", required=True)
    repository.add_argument("--runtime-evidence", required=True)
    repository.add_argument("--sdk-evidence", required=True)
    repository.add_argument("--contract-version", required=True)
    repository.add_argument("--runtime-version", required=True)
    repository.add_argument("--sdk-version", required=True)
    repository.add_argument("--trust-domain", required=True)
    repository.add_argument("--output", required=True)
    values = parser.parse_args(arguments)
    if values.command == "verify-repository":
        verify_repository_evidence(
            contract_evidence=values.contract_evidence,
            runtime_evidence=values.runtime_evidence,
            sdk_evidence=values.sdk_evidence,
            contract_version=values.contract_version,
            runtime_version=values.runtime_version,
            sdk_version=values.sdk_version,
            trust_domain=values.trust_domain,
            output=values.output,
        )
        return 0
    parser.error("Unsupported aggregate command")


if __name__ == "__main__":
    raise SystemExit(main())
