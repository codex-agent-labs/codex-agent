from __future__ import annotations

from pathlib import Path
import re
import tempfile
from typing import Any
import zipfile

from .inventory import (
    canonical_json_bytes,
    load_canonical_json,
    load_canonical_json_bytes,
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
    sha256_file,
    verified_zip_inventory,
)
from .receipt import output_inventory_digest, validate_phase_receipt, validate_producer
from .signatures import validate_signing_metadata, verify_manifest_signature


CONTRACT_COMPONENTS = (
    "common",
    "android",
    "jvm",
    "ios-arm64",
    "ios-simulator-arm64",
    "macos-arm64",
    "macos-x64",
    "linux-arm64",
    "linux-x64",
    "windows-x64",
    "node-js",
    "node-wasm",
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
CONTRACT_MAVEN_ROLES = {"runtime-resolution", "sources", "javadoc", "signature", "checksum"}
CONTRACT_EVIDENCE_ROLES = {
    "canonical-api",
    "canonical-coverage",
    "inventory",
    "kotlin-parity",
    "protocol-descriptor",
    "protocol-provenance",
    "protocol-schema",
    "protocol-source-verification",
}
COMPATIBLE_RANGE = re.compile(
    r">=(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*) "
    r"<(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
)


def _sorted_unique(values: list[str], label: str) -> None:
    if values != sorted(values) or len(values) != len(set(values)):
        raise ValueError(f"{label} must be sorted and unique")


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


def contract_component_digest(records: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_json_bytes(records))


def contract_digest(canonical_api_digest: str, protocol_digest: str, common_component_digest: str) -> str:
    for value, label in (
        (canonical_api_digest, "canonical API digest"),
        (protocol_digest, "protocol digest"),
        (common_component_digest, "common Contract component digest"),
    ):
        require_sha256(value, label)
    return sha256_bytes(canonical_json_bytes({
        "canonicalApiDigest": canonical_api_digest,
        "commonComponentDigest": common_component_digest,
        "protocolDigest": protocol_digest,
    }))


def validate_contract_manifest(value: Any) -> dict[str, Any]:
    manifest = require_exact_keys(
        value,
        {
            "schemaVersion",
            "product",
            "contractVersion",
            "contractDigest",
            "canonicalApiDigest",
            "canonicalCoverageDigest",
            "protocolDigest",
            "capabilityCount",
            "components",
            "mavenFiles",
            "evidenceFiles",
            "signing",
        },
        "Contract manifest",
    )
    if require_integer(manifest["schemaVersion"], "Contract manifest.schemaVersion", 1) != 1:
        raise ValueError("Unsupported Contract manifest schemaVersion")
    if manifest["product"] != "contract":
        raise ValueError("Contract manifest product must be contract")
    require_semver(manifest["contractVersion"], "Contract manifest.contractVersion")
    require_sha256(manifest["contractDigest"], "Contract manifest.contractDigest")
    require_sha256(manifest["canonicalApiDigest"], "Contract manifest.canonicalApiDigest")
    require_sha256(manifest["canonicalCoverageDigest"], "Contract manifest.canonicalCoverageDigest")
    require_sha256(manifest["protocolDigest"], "Contract manifest.protocolDigest")
    if require_integer(manifest["capabilityCount"], "Contract manifest.capabilityCount", 1) != 556:
        raise ValueError("Contract manifest capabilityCount must be exactly 556")

    components = require_exact_keys(manifest["components"], CONTRACT_COMPONENTS, "Contract manifest.components")
    maven_files = _artifact_records(manifest["mavenFiles"], "Contract manifest.mavenFiles", component=True)
    evidence_files = _artifact_records(manifest["evidenceFiles"], "Contract manifest.evidenceFiles")
    if set(record["component"] for record in maven_files) - set(CONTRACT_COMPONENTS):
        raise ValueError("Contract Maven file names an unsupported component")
    if set(record["path"] for record in maven_files) & set(record["path"] for record in evidence_files):
        raise ValueError("Contract Maven and evidence file paths overlap")
    if any(not record["path"].startswith("maven/") or record["role"] not in CONTRACT_MAVEN_ROLES
           for record in maven_files):
        raise ValueError("Contract Maven files must use the maven/ scope and a supported role")
    for record in evidence_files:
        prefix = record["path"].split("/", 1)[0]
        if prefix not in {"evidence", "inventories"} or record["role"] not in CONTRACT_EVIDENCE_ROLES:
            raise ValueError("Contract evidence files must use a supported scope and role")
        if (prefix == "inventories") != (record["role"] == "inventory"):
            raise ValueError("Contract inventory role and inventories/ scope must agree")
    evidence_roles = {record["role"] for record in evidence_files}
    if evidence_roles != CONTRACT_EVIDENCE_ROLES:
        raise ValueError("Contract evidence roles are incomplete")
    for component_name in CONTRACT_COMPONENTS:
        component = require_exact_keys(
            components[component_name], {"mavenPaths", "sha256"}, f"Contract component {component_name}",
        )
        paths = [
            require_relative_path(path, f"Contract component {component_name}.mavenPaths[]")
            for path in require_array(component["mavenPaths"], f"Contract component {component_name}.mavenPaths")
        ]
        _sorted_unique(paths, f"Contract component {component_name}.mavenPaths")
        resolution_records = [
            record for record in maven_files
            if record["component"] == component_name and record["role"] == "runtime-resolution"
        ]
        if not resolution_records or paths != [record["path"] for record in resolution_records]:
            raise ValueError(f"Contract component {component_name} runtime-resolution closure is incomplete")
        if require_sha256(component["sha256"], f"Contract component {component_name}.sha256") != \
                contract_component_digest(resolution_records):
            raise ValueError(f"Contract component {component_name} digest mismatch")
    expected_contract_digest = contract_digest(
        manifest["canonicalApiDigest"],
        manifest["protocolDigest"],
        components["common"]["sha256"],
    )
    if manifest["contractDigest"] != expected_contract_digest:
        raise ValueError("Contract manifest contractDigest mismatch")
    validate_signing_metadata(manifest["signing"])
    return manifest


def verify_contract_bundle(root: Path, value: Any) -> dict[str, Any]:
    manifest = validate_contract_manifest(value)
    root = Path(root)
    if load_canonical_json(root / "contract-manifest.json") != manifest:
        raise ValueError("Contract Bundle manifest bytes do not match the supplied manifest")
    actual = {record["relativePath"]: record for record in regular_file_inventory(root)}
    declared = {
        record["path"]: {"relativePath": record["path"], "bytes": record["bytes"], "sha256": record["sha256"]}
        for record in manifest["mavenFiles"] + manifest["evidenceFiles"]
    }
    special = {"contract-manifest.json", "contract-manifest.sig"}
    if set(actual) != special | set(declared):
        raise ValueError("Contract Bundle file set differs from its complete allow-list")
    if any(actual[path] != record for path, record in declared.items()):
        raise ValueError("Contract Bundle declared file bytes or digest differ")
    return manifest


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
        if bundle.name != expected_name or sha256_file(bundle) != record["bundleSha256"]:
            raise ValueError(f"Runtime variant bundle identity mismatch: {target}")

        inventory = {member["relativePath"]: member for member in verified_zip_inventory(bundle)}
        manifest_name = "runtime-variant-manifest.json"
        signature_name = "runtime-variant-manifest.sig"
        if manifest_name not in inventory or signature_name not in inventory:
            raise ValueError(f"Runtime variant bundle lacks its manifest or signature: {target}")
        with zipfile.ZipFile(bundle) as archive:
            manifest_bytes = archive.read(manifest_name)
            signature_bytes = archive.read(signature_name)
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
        with zipfile.ZipFile(bundle) as archive:
            phase_receipts = {
                phase: validate_phase_receipt(load_canonical_json_bytes(archive.read(role_records[role]["path"])))
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
        if sha256_file(receipt_path) != record["receiptSha256"]:
            raise ValueError(f"Runtime variant metadata receipt digest mismatch: {target}")
        receipt = validate_phase_receipt(load_canonical_json(receipt_path))
        bundle_output = {
            "kind": "runtime-variant",
            "relativePath": bundle.name,
            "bytes": bundle.stat().st_size,
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
