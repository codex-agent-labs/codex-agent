from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import Any

from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    load_json_bytes,
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
    build_key_payload,
    output_inventory_digest,
    validate_output_manifest,
    validate_phase_receipt,
    validate_producer,
    verify_output_manifest,
)
from .registry import NATIVE_TARGETS, PhaseInstanceId
from .sdk_runtime_content import VerifiedNativeRuntimeProjection
from .runtime_adapter_content import VerifiedAdapterRuntimeProjection
from .sdk_validation import VerifiedSdkValidationProjection
from .restore import (
    PHASE_RECEIPT_NAME,
    object_relative_path,
    restore_object,
    verify_carrier,
)
from .signatures import validate_signing_metadata
from .runtime_identity import derive_runtime_identity
from .contract_attestation import verify_contract_attestation
from .contract_projection import VerifiedContractExecutionProjection
from .contract_model import (
    CONTRACT_ARTIFACT_COMPONENTS,
    CONTRACT_CHECKSUM_SUFFIXES,
    CONTRACT_COMPONENTS,
    contract_component_digest,
    contract_digest,
    contract_evidence_identity,
    contract_maven_identity,
    contract_required_primary_paths,
    validate_contract_manifest,
    validate_contract_maven_inventory,
    verify_contract_git_inventories,
)


RUNTIME_TARGETS = ("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64")
RUNTIME_EVIDENCE_TARGETS = {
    "macos-arm64": "macosArm64",
    "macos-x64": "macosX64",
    "linux-arm64": "linuxArm64",
    "linux-x64": "linuxX64",
    "windows-x64": "mingwX64",
}
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
RUNTIME_MAVEN_PRIMARY_ROLES = {
    "runtime-resolution", "module-metadata", "sources", "javadoc",
}
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


def verify_repository_carrier(
    *,
    carrier: Any,
    expected_instances: Any,
    consumer: Any,
    contract_version: Any,
    runtime_version: Any,
    sdk_version: Any,
    trust_domain: Any,
    output: Any,
) -> dict[str, Any]:
    output_path = _invalidate_repository_report(output, (carrier,))
    carrier_root = _repository_evidence_root(carrier, "Product carrier directory")
    verified = verify_carrier(carrier_root, expected_instances, consumer)
    terminal = {
        PhaseInstanceId(product, component, phase, target): product
        for product, (component, phase, target) in REPOSITORY_EVIDENCE_IDENTITIES.items()
    }
    objects = {
        PhaseInstanceId(record["product"], record["component"], record["phase"], record["target"]): record
        for record in verified["objects"]
    }
    if not terminal.keys() <= objects.keys():
        raise ValueError("Product carrier lacks the exact repository terminal phases")

    with tempfile.TemporaryDirectory(prefix="codex-agent-repository-carrier-") as temporary:
        roots = {}
        for instance, product in terminal.items():
            record = objects[instance]
            root = Path(temporary).resolve() / product
            restored = restore_object(
                carrier_root / object_relative_path(record["buildKey"], record["receiptSha256"]),
                root / "outputs",
                build_key=record["buildKey"],
                receipt_sha256=record["receiptSha256"],
                object_sha256=record["objectSha256"],
            )
            if restored["receiptBytes"] != record["receiptBytes"]:
                raise ValueError("Product carrier terminal receipt changed during restore")
            (root / PHASE_RECEIPT_NAME).write_bytes(restored["receiptBytes"])
            roots[product] = root
        return verify_repository_evidence(
            contract_evidence=roots["contract"],
            runtime_evidence=roots["runtime"],
            sdk_evidence=roots["sdk"],
            contract_version=contract_version,
            runtime_version=runtime_version,
            sdk_version=sdk_version,
            trust_domain=trust_domain,
            output=output_path,
        )


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
    return derive_runtime_identity({
        "schemaVersion": 1,
        "binaryBuildKey": value["inputs"]["binaryBuildKey"],
        "runtimeCompatibilityVersion": value["runtimeCompatibilityVersion"],
        "target": value["target"],
        "contract": {
            "digest": value["contract"]["digest"],
            "componentDigest": value["contract"]["componentDigest"],
        },
        "cAbi": value["cAbi"],
        "appServer": value["appServer"],
        "toolchainProfile": value["toolchainProfile"],
    })["componentId"]


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
    contract = require_exact_keys(
        variant["contract"], {"digest", "componentDigest"}, "Runtime variant.contract",
    )
    require_sha256(contract["digest"], "Runtime variant.contract.digest")
    require_sha256(contract["componentDigest"], "Runtime variant.contract.componentDigest")
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
        {"binaryBuildKey", "binaryOutputInventoryDigest"},
        "Runtime variant.inputs",
    )
    for field in inputs:
        require_sha256(inputs[field], f"Runtime variant.inputs.{field}")
    artifacts = _artifact_records(variant["innerArtifacts"], "Runtime variant.innerArtifacts")
    if any(record["path"] == "runtime-variant-manifest.json" for record in artifacts):
        raise ValueError("Runtime variant innerArtifacts cannot contain its manifest")
    required_prefixes = {"c-abi", "app-server", "evidence"}
    if {record["path"].split("/", 1)[0] for record in artifacts} != required_prefixes:
        raise ValueError("Runtime variant innerArtifacts must cover c-abi, app-server, and evidence")
    required_roles = {
        "app-server-archive",
        "binary-phase-evidence",
        "c-abi-archive",
        "package-phase-evidence",
        "provenance",
        "sbom",
        "validation",
        "validation-phase-evidence",
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
    toolchain = require_exact_keys(variant["toolchainProfile"], {"id", "digest"}, "Runtime variant.toolchainProfile")
    if require_identifier(toolchain["id"], "Runtime variant.toolchainProfile.id") != variant["target"]:
        raise ValueError("Runtime variant toolchain profile ID must equal its target")
    require_sha256(toolchain["digest"], "Runtime variant.toolchainProfile.digest")
    if require_sha256(variant["componentId"], "Runtime variant.componentId") != runtime_component_id(variant):
        raise ValueError("Runtime variant componentId mismatch")
    return variant


def _runtime_variant_record(value: Any, label: str) -> dict[str, Any]:
    record = require_exact_keys(
        value,
        {
            "target",
            "componentId",
            "bundleSha256",
            "manifestSha256",
        },
        label,
    )
    if record["target"] not in RUNTIME_TARGETS:
        raise ValueError(f"{label}.target is unsupported")
    for field in ("componentId", "bundleSha256", "manifestSha256"):
        require_sha256(record[field], f"{label}.{field}")
    return record


def validate_runtime_maven_inventory(
    records: list[dict[str, Any]],
    contents: dict[str, bytes] | None = None,
) -> list[dict[str, Any]]:
    records_by_path = {record["path"]: record for record in records}
    if len(records_by_path) != len(records):
        raise ValueError("Runtime Maven publication inventory paths must be unique")
    primaries: list[str] = []
    sidecars: list[tuple[str, str]] = []
    for record in records:
        path = record["path"]
        role = record["role"]
        component = record["component"]
        if component not in RUNTIME_MAVEN_COMPONENTS or not path.startswith(
            f"maven/{component}/"
        ):
            raise ValueError("Runtime Maven path does not match its component")
        suffix = next(
            (value for value in CONTRACT_CHECKSUM_SUFFIXES if path.endswith(value)),
            None,
        )
        primary_path = path.removesuffix(suffix) if suffix else path
        filename = PurePosixPath(path).name
        primary_filename = PurePosixPath(primary_path).name
        if (
            primary_filename.endswith((".asc", ".sig"))
            or filename.endswith((".asc", ".sig"))
            or ".asc." in filename
            or ".sig." in filename
        ):
            raise ValueError("Runtime Maven signatures and checksums of signatures are forbidden")
        if filename.endswith(("-inventory.json", ".inventory.json")):
            raise ValueError("Runtime Maven publication inventories are forbidden")
        if suffix is None and re.search(r"\.(?:md|sha)[0-9]+$", path):
            raise ValueError("Runtime Maven checksum suffix is unsupported")
        if suffix is not None:
            if role != "checksum":
                raise ValueError("Runtime Maven checksum sidecar role is not canonical")
            primary = records_by_path.get(primary_path)
            if primary is None:
                raise ValueError("Runtime Maven checksum sidecar is orphaned")
            if primary["component"] != record["component"]:
                raise ValueError("Runtime Maven checksum sidecar component differs from its primary")
            if primary["role"] not in RUNTIME_MAVEN_PRIMARY_ROLES:
                raise ValueError("Runtime Maven checksum sidecar primary role is unsupported")
            sidecars.append((path, suffix))
        elif role not in RUNTIME_MAVEN_PRIMARY_ROLES:
            raise ValueError("Runtime Maven primary role is unsupported")
        else:
            primaries.append(path)
    expected_sidecars = {
        primary + suffix for primary in primaries for suffix in CONTRACT_CHECKSUM_SUFFIXES
    }
    actual_sidecars = {path for path, _ in sidecars}
    if actual_sidecars != expected_sidecars:
        raise ValueError("Runtime Maven checksum inventory is incomplete or unexpected")
    if contents is not None:
        if set(contents) != set(records_by_path):
            raise ValueError("Runtime Maven publication contents differ from its inventory")
        for path, record in records_by_path.items():
            member = contents[path]
            if len(member) != record["bytes"] or sha256_bytes(member) != record["sha256"]:
                raise ValueError(f"Runtime Maven declared bytes or digest mismatch: {path}")
        for path, suffix in sidecars:
            primary_path = path.removesuffix(suffix)
            expected = (
                hashlib.new(suffix[1:], contents[primary_path]).hexdigest().encode("ascii")
                + b"\n"
            )
            if contents[path] != expected:
                raise ValueError(f"Runtime Maven checksum content is noncanonical: {path}")
    return records


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
        },
        "Runtime aggregate",
    )
    if require_integer(aggregate["schemaVersion"], "Runtime aggregate.schemaVersion", 1) != 1:
        raise ValueError("Unsupported Runtime aggregate schemaVersion")
    if aggregate["product"] != "runtime":
        raise ValueError("Runtime aggregate product must be runtime")
    runtime_version = require_semver(aggregate["runtimeVersion"], "Runtime aggregate.runtimeVersion")
    require_semver(aggregate["runtimeCompatibilityVersion"], "Runtime aggregate.runtimeCompatibilityVersion")
    major, minor, _ = runtime_version.split("-", 1)[0].split(".")
    if aggregate["runtimeCompatibilityVersion"] != f"{major}.{minor}.0":
        raise ValueError("Runtime aggregate compatibility version does not match its release")
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
    if any(not record["path"].startswith("maven/") for record in maven_files):
        raise ValueError("Runtime aggregate Maven inventory has an unsupported scope or role")
    validate_runtime_maven_inventory(maven_files)
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
    return aggregate


def _runtime_variant_bundle_name(target: str, component_id: str) -> str:
    return f"codex-agent-runtime-variant-{target}-{component_id.removeprefix('sha256:')}.zip"


def require_runtime_adapter_maven_primary(component, role, record, receipts):
    """Bind published primaries to both original artifact-only phase receipts."""
    if component not in RUNTIME_ADAPTERS or role not in {"runtime-resolution", "sources", "javadoc"}:
        return
    primary = {"runtime-resolution": "main.jar" if component == "jvm" else "main.klib",
               "sources": "sources.jar", "javadoc": "javadoc.jar"}[role]
    original = {"kind": "publication", "relativePath": f"outputs/publication/{primary}",
                "bytes": record["bytes"], "sha256": record["sha256"]}
    for phase in ("binary", "package"):
        if original not in receipts[(component, phase, component)]["outputs"]:
            raise ValueError(f"Runtime {component} Maven {role} differs from its original {phase} publication")


def verify_runtime_aggregate_artifacts(
    aggregate_manifest: Path,
    *,
    aggregate_metadata_receipt: Path,
    aggregate_attestation: Path,
    aggregate_attestation_signature: Path,
    aggregate_public_key: Path,
    contract_payload: Path,
    contract_metadata_receipt: Path,
    contract_attestation: Path,
    contract_attestation_signature: Path,
    contract_public_key: Path,
    variant_bundles: dict[str, Path],
    variant_phase_receipts: dict[str, dict[str, Path]],
    variant_attestations: dict[str, Path],
    variant_attestation_signatures: dict[str, Path],
    variant_public_keys: dict[str, Path],
    variant_validation_evidence: dict[str, Path],
    adapter_receipts: list[dict[str, Any]],
    adapter_report_files: dict[str, dict[str, Path]],
    runtime_maven_files: list[dict[str, Any]],
    adapter_evidence: dict[str, Path],
    required_trust_domain: str,
    contract_keyring: Path | None = None,
    contract_keys_directory: Path | None = None,
    aggregate_keyring: Path | None = None,
    aggregate_keys_directory: Path | None = None,
    variant_keyring: Path | None = None,
    variant_keys_directory: Path | None = None,
) -> dict[str, Any]:
    """Verify one Runtime release without copying trust identity into payload bytes."""
    from .runtime_aggregate import (
        verify_runtime_aggregate_attestation,
        verify_runtime_aggregate_attestation_closure,
    )
    from .runtime_evidence import (
        derive_runtime_adapter_projection,
        jvm_evidence_filename,
        node_evidence_filename,
    )

    contract, contract_receipt, contract_attestation_value = verify_contract_attestation(
        Path(contract_payload),
        Path(contract_metadata_receipt),
        Path(contract_attestation),
        Path(contract_attestation_signature),
        Path(contract_public_key),
        required_trust_domain=required_trust_domain,
        keyring=contract_keyring,
        keys_directory=contract_keys_directory,
    )
    aggregate, aggregate_receipt, attestation = verify_runtime_aggregate_attestation(
        Path(aggregate_manifest),
        Path(aggregate_metadata_receipt),
        Path(aggregate_attestation),
        Path(aggregate_attestation_signature),
        Path(aggregate_public_key),
        required_trust_domain=required_trust_domain,
        keyring=aggregate_keyring,
        keys_directory=aggregate_keys_directory,
    )
    variant_manifests, variant_receipts, adapter_receipt_values = (
        verify_runtime_aggregate_attestation_closure(
            aggregate,
            attestation,
            variant_bundles=variant_bundles,
            variant_phase_receipts=variant_phase_receipts,
            variant_attestations=variant_attestations,
            variant_attestation_signatures=variant_attestation_signatures,
            variant_public_keys=variant_public_keys,
            adapter_receipts=adapter_receipts,
            required_variant_trust_domain=required_trust_domain,
            variant_validation_evidence=variant_validation_evidence,
            variant_keyring=variant_keyring,
            variant_keys_directory=variant_keys_directory,
        )
    )
    adapter_receipt_map = {
        (receipt["component"], receipt["phase"], receipt["target"]): receipt
        for receipt in adapter_receipt_values
    }
    expected_aggregate_upstreams = sorted(
        [
            *(
                _repository_reference(variant_receipts[target]["metadata"])
                for target in RUNTIME_TARGETS
            ),
            *(
                _repository_reference(adapter_receipt_map[(component, "metadata", component)])
                for component in RUNTIME_ADAPTERS
            ),
        ],
        key=lambda value: (
            value["product"], value["component"], value["phase"],
            value["target"], value["buildKey"],
        ),
    )
    if aggregate_receipt["inputs"]["upstreamArtifacts"] != expected_aggregate_upstreams:
        raise ValueError("Runtime aggregate metadata receipt predecessor closure mismatch")
    if aggregate["contract"] != {
        "version": contract["contractVersion"],
        "digest": contract["contractDigest"],
    } or any(
        manifest["contract"]["digest"] != contract["contractDigest"]
        for manifest in variant_manifests.values()
    ):
        raise ValueError("Runtime aggregate does not reference the authenticated Contract")

    all_receipts = [
        *(receipt for receipts in variant_receipts.values() for receipt in receipts.values()),
        *adapter_receipt_values,
    ]

    def require_owner(
        kind: str, relative_path: str, byte_count: int, digest: str, label: str,
        expected_receipt: dict[str, Any] | None = None,
    ) -> None:
        expected = {
            "kind": kind,
            "relativePath": relative_path,
            "bytes": byte_count,
            "sha256": digest,
        }
        matches = [
            (receipt, output)
            for receipt in all_receipts
            for output in receipt["outputs"]
            if all(output[field] == value for field, value in expected.items())
        ]
        if len(matches) != 1 or (
            expected_receipt is not None and matches[0][0] is not expected_receipt
        ):
            raise ValueError(f"{label} must be owned by exactly one immutable receipt output")

    actual_maven = []
    actual_maven_contents: dict[str, bytes] = {}
    for index, value in enumerate(require_array(runtime_maven_files, "Runtime Maven file inputs")):
        source = require_exact_keys(
            value, {"path", "role", "component", "file"},
            f"Runtime Maven file input[{index}]",
        )
        logical_path = require_relative_path(
            source["path"], f"Runtime Maven file input[{index}].path",
        )
        role = require_identifier(source["role"], f"Runtime Maven file input[{index}].role")
        component = require_identifier(
            source["component"], f"Runtime Maven file input[{index}].component",
        )
        if not isinstance(source["file"], (str, os.PathLike)) or not os.fspath(source["file"]):
            raise ValueError(f"Runtime Maven file input[{index}].file must be a non-empty path")
        contents = read_regular_file_bytes(Path(source["file"]), reject_symlink_parents=True)
        if not contents:
            raise ValueError(f"Runtime Maven file input is empty: {logical_path}")
        record = {
            "path": logical_path,
            "role": role,
            "component": component,
            "bytes": len(contents),
            "sha256": sha256_bytes(contents),
        }
        actual_maven.append(record)
        actual_maven_contents[logical_path] = contents
        owner_receipt = (
            variant_receipts[component]["package"]
            if component in RUNTIME_TARGETS
            else adapter_receipt_map[(component, "metadata", component)]
        )
        require_owner(
            "maven", f"outputs/{logical_path}", record["bytes"], record["sha256"],
            f"Runtime Maven input {logical_path}", owner_receipt,
        )
        require_runtime_adapter_maven_primary(component, role, record, adapter_receipt_map)
    actual_maven.sort(key=lambda record: record["path"])
    validate_runtime_maven_inventory(actual_maven, actual_maven_contents)
    if actual_maven != aggregate["runtimeMavenFiles"]:
        raise ValueError("Runtime aggregate Maven files differ from the verified inputs")

    if type(adapter_evidence) is not dict or set(adapter_evidence) != set(RUNTIME_ADAPTERS):
        raise ValueError("Runtime adapter projections must contain exactly JVM, Node JS, and Node Wasm")
    if type(adapter_report_files) is not dict or set(adapter_report_files) != set(RUNTIME_ADAPTERS):
        raise ValueError("Runtime adapter reports must contain exactly JVM, Node JS, and Node Wasm")
    receipt_map = adapter_receipt_map
    contract_receipt_bytes = read_regular_file_bytes(
        Path(contract_metadata_receipt), max_bytes=REPOSITORY_JSON_LIMIT,
        reject_symlink_parents=True,
    )

    def sorted_references(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(values, key=lambda value: (
            value["product"], value["component"], value["phase"],
            value["target"], value["buildKey"],
        ))

    actual_adapter_evidence = []
    for component in RUNTIME_ADAPTERS:
        binary_receipt = receipt_map[(component, "binary", component)]
        package_receipt = receipt_map[(component, "package", component)]
        metadata_receipt = receipt_map[(component, "metadata", component)]
        component_digest = contract["components"][component]["sha256"]
        expected_contract_projection = {
            "schemaVersion": 1,
            "receiptSha256": sha256_bytes(contract_receipt_bytes),
            "bundlePath": f"outputs/{contract_attestation_value['payload']['fileName']}",
            "bundleSha256": contract_attestation_value["payload"]["sha256"],
            "manifestSha256": contract_attestation_value["manifestSha256"],
            "contractVersion": contract["contractVersion"],
            "contractDigest": contract["contractDigest"],
            "componentDigests": [{"component": component, "sha256": component_digest}],
        }
        expected_contract_upstream = {
            **_repository_reference(contract_receipt),
            "contractProjection": expected_contract_projection,
        }
        if binary_receipt["inputs"]["upstreamArtifacts"] != [expected_contract_upstream]:
            raise ValueError(f"Runtime {component} binary receipt Contract predecessor mismatch")
        if package_receipt["inputs"]["upstreamArtifacts"] != [
            _repository_reference(binary_receipt)
        ]:
            raise ValueError(f"Runtime {component} package receipt predecessor mismatch")

        reports = adapter_report_files[component]
        # JSON object key order is not target order; the canonical traversal below is.
        if type(reports) is not dict or set(reports) != set(RUNTIME_TARGETS):
            raise ValueError(
                f"Runtime {component} reports must contain exactly the five targets",
            )
        raw_values = []
        expected_commits = {}
        for target in RUNTIME_TARGETS:
            report_path = Path(reports[target])
            report_bytes = read_regular_file_bytes(
                report_path, max_bytes=64 * 1024 * 1024, reject_symlink_parents=True,
            )
            # External producer reports retain their original formatting and receipt hashes.
            report = load_json_bytes(report_bytes)
            receipt = receipt_map[(component, "validation", target)]
            expected_validation_upstreams = [_repository_reference(package_receipt)]
            expected_validation_upstreams.append(
                _repository_reference(variant_receipts[target]["package"]),
            )
            if receipt["inputs"]["upstreamArtifacts"] != sorted_references(
                expected_validation_upstreams,
            ):
                raise ValueError(
                    f"Runtime {component} validation receipt predecessor mismatch: {target}",
                )
            evidence_target = RUNTIME_EVIDENCE_TARGETS[target]
            if component == "jvm":
                output_kind = "jvm-evidence"
                output_path = f"outputs/jvm-evidence/{jvm_evidence_filename(evidence_target)}"
            else:
                output_kind = "node-evidence"
                backend = "js" if component == "node-js" else "wasm"
                output_path = (
                    f"outputs/node-evidence/{node_evidence_filename(evidence_target, backend)}"
                )
            expected_output = {
                "kind": output_kind,
                "relativePath": output_path,
                "bytes": len(report_bytes),
                "sha256": sha256_bytes(report_bytes),
            }
            if receipt["outputs"].count(expected_output) != 1:
                raise ValueError(
                    f"Runtime {component} report is not one exact validation output: {target}",
                )
            require_owner(
                output_kind, output_path, len(report_bytes), sha256_bytes(report_bytes),
                f"Runtime {component} raw report {target}",
            )
            raw_values.append(report)
            expected_commits[evidence_target] = receipt["producer"]["commit"]

        projection = derive_runtime_adapter_projection(component, raw_values, expected_commits)
        projection_bytes = read_regular_file_bytes(
            Path(adapter_evidence[component]),
            max_bytes=64 * 1024 * 1024,
            reject_symlink_parents=True,
        )
        if projection_bytes != canonical_json_bytes(projection):
            raise ValueError(f"Runtime {component} adapter projection differs from its raw reports")
        projection_digest = sha256_bytes(projection_bytes)
        expected_metadata_upstreams = []
        for target in RUNTIME_TARGETS:
            reference = _repository_reference(receipt_map[(component, "validation", target)])
            reference["semanticProjection"] = {
                "schemaVersion": 1,
                "kind": "runtime-validation-content",
                "sha256": projection_digest,
            }
            expected_metadata_upstreams.append(reference)
        if component == "node-js":
            binding_receipt = receipt_map[(component, "validation", "node-js-binding")]
            if binding_receipt["inputs"]["upstreamArtifacts"] != [
                _repository_reference(package_receipt)
            ]:
                raise ValueError("Runtime node-js binding validation predecessor mismatch")
            expected_metadata_upstreams.append(_repository_reference(binding_receipt))
        if metadata_receipt["inputs"]["upstreamArtifacts"] != sorted_references(
            expected_metadata_upstreams,
        ):
            raise ValueError(f"Runtime {component} metadata receipt predecessor mismatch")
        record = {
            "path": f"evidence/{component}.json",
            "role": "adapter",
            "target": component,
            "bytes": len(projection_bytes),
            "sha256": sha256_bytes(projection_bytes),
        }
        actual_adapter_evidence.append(record)
        require_owner(
            "adapter-evidence", f"outputs/{record['path']}",
            record["bytes"], record["sha256"],
            f"Runtime {component} adapter projection",
        )
    actual_adapter_evidence.sort(key=lambda record: record["path"])
    if actual_adapter_evidence != aggregate["adapterEvidence"]:
        raise ValueError("Runtime aggregate adapter evidence differs from the verified projections")
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


def verified_index_content(entry: dict[str, Any], contract_execution_projection=None,
                           native_runtime_projection=None, adapter_runtime_projection=None,
                           sdk_validation_projection=None) -> dict[str, Any]:
    """Comparison-only view; never rewrite the signed index or original receipt."""
    from .registry import NATIVE_BINDINGS
    if (sdk_validation_projection is not None and entry["product"] == "sdk"
            and entry["phase"] == "validation" and entry["component"] in NATIVE_BINDINGS
            and entry["target"] in NATIVE_TARGETS):
        proof = sdk_validation_projection(entry)
        if type(proof) is not VerifiedSdkValidationProjection:
            raise ValueError("Verified SDK validation projection is required for index consistency")
        outputs = proof.output_inventory(entry["receiptSha256"], entry["outputs"], identity=entry)
        return {**entry, "outputs": outputs, "outputInventoryDigest": output_inventory_digest(outputs),
                "artifactName": None, "artifactSha256": None}
    if (adapter_runtime_projection is not None and entry["product"] == "runtime"
            and entry["phase"] == "validation" and entry["component"] in RUNTIME_ADAPTERS
            and entry["target"] in NATIVE_TARGETS):
        proof = adapter_runtime_projection(entry)
        if type(proof) is not VerifiedAdapterRuntimeProjection:
            raise ValueError("Verified adapter Runtime projection is required for index consistency")
        outputs = proof.output_inventory(entry["receiptSha256"], entry["outputs"], identity=entry)
        return {**entry, "outputs": outputs, "outputInventoryDigest": output_inventory_digest(outputs),
                "artifactName": None, "artifactSha256": None}
    if (native_runtime_projection is not None and entry["product"] == "runtime"
            and entry["phase"] == "validation" and entry["component"] == entry["target"]
            and entry["target"] in NATIVE_TARGETS):
        proof = native_runtime_projection(entry)
        if type(proof) is not VerifiedNativeRuntimeProjection:
            raise ValueError("Verified native Runtime projection is required for index consistency")
        outputs = proof.output_inventory(entry["receiptSha256"], entry["outputs"], identity=entry)
        return {**entry, "outputs": outputs, "outputInventoryDigest": output_inventory_digest(outputs),
                "artifactName": None, "artifactSha256": None}
    if contract_execution_projection is None or tuple(entry[field] for field in (
        "product", "component", "phase", "target",
    )) != ("contract", "contract", "binary", "common"):
        return entry
    proof = contract_execution_projection(entry)
    if type(proof) is not VerifiedContractExecutionProjection:
        raise ValueError("Verified Contract execution projection is required for index consistency")
    outputs = proof.output_inventory(entry["receiptSha256"], entry["outputs"])
    result = {**entry, "outputs": outputs, "outputInventoryDigest": output_inventory_digest(outputs)}
    if entry["artifactName"] == "outputs/execution/contract-execution.zip":
        result.update(artifactName=None, artifactSha256=None)
    return result


def verify_immutable_product_indexes(existing: Any, candidate: Any, *, contract_execution_projection=None,
                                     native_runtime_projection=None, adapter_runtime_projection=None,
                                     sdk_validation_projection=None) -> None:
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
            left = verified_index_content(by_build_key[entry["buildKey"]], contract_execution_projection, native_runtime_projection, adapter_runtime_projection, sdk_validation_projection)
            right = verified_index_content(entry, contract_execution_projection, native_runtime_projection, adapter_runtime_projection, sdk_validation_projection)
            if left["outputs"] != right["outputs"]:
                raise ValueError("Identical product build key has a conflicting output inventory")
    for identity in set(prior_releases) & set(proposed_releases):
        if _release_output_projection(prior_releases[identity]) != \
                _release_output_projection(proposed_releases[identity]):
            left = _release_output_projection([
                verified_index_content(entry, contract_execution_projection, native_runtime_projection, adapter_runtime_projection, sdk_validation_projection) for entry in prior_releases[identity]
            ])
            right = _release_output_projection([
                verified_index_content(entry, contract_execution_projection, native_runtime_projection, adapter_runtime_projection, sdk_validation_projection) for entry in proposed_releases[identity]
            ])
            if left != right:
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
