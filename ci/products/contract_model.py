from __future__ import annotations

import hashlib
from pathlib import Path
import re
import tempfile
from typing import Any
from xml.etree import ElementTree

from .inventory import (
    canonical_json_bytes,
    load_canonical_json,
    load_canonical_json_bytes,
    load_json,
    load_json_bytes,
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
    verified_zip_contents,
)
from .receipt import validate_producer
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
CONTRACT_ARTIFACT_COMPONENTS = {
    "codex-agent-core": "common",
    "codex-agent-core-android": "android",
    "codex-agent-core-jvm": "jvm",
    "codex-agent-core-iosarm64": "ios-arm64",
    "codex-agent-core-iossimulatorarm64": "ios-simulator-arm64",
    "codex-agent-core-macosarm64": "macos-arm64",
    "codex-agent-core-macosx64": "macos-x64",
    "codex-agent-core-linuxarm64": "linux-arm64",
    "codex-agent-core-linuxx64": "linux-x64",
    "codex-agent-core-mingwx64": "windows-x64",
    "codex-agent-core-js": "node-js",
    "codex-agent-core-wasm-js": "node-wasm",
}
CONTRACT_MAVEN_ROLES = {
    "runtime-resolution", "module-metadata", "sources", "javadoc", "signature", "checksum",
}
CONTRACT_PAYLOAD_SUFFIXES = (".aar", ".jar", ".klib")
CONTRACT_CHECKSUM_SUFFIXES = (".md5", ".sha1", ".sha256", ".sha512")
CONTRACT_ANCILLARY_SUFFIXES = ("-javadoc.jar", "-sources.jar")
CONTRACT_KLIB_FILE_NAMES = {
    "codex-agent-core-iosarm64": "iosArm64Main",
    "codex-agent-core-iossimulatorarm64": "iosSimulatorArm64Main",
    "codex-agent-core-macosarm64": "macosArm64Main",
    "codex-agent-core-macosx64": "macosX64Main",
    "codex-agent-core-linuxarm64": "linuxArm64Main",
    "codex-agent-core-linuxx64": "linuxX64Main",
    "codex-agent-core-mingwx64": "mingwX64Main",
}
CONTRACT_AVAILABLE_AT_TARGETS = {
    "androidJvm": ("codex-agent-core-android", "android"),
    "jvm": ("codex-agent-core-jvm", "jvm"),
    "js": ("codex-agent-core-js", "js"),
    "wasm": ("codex-agent-core-wasm-js", "wasmJs"),
    "ios_arm64": ("codex-agent-core-iosarm64", "iosArm64"),
    "ios_simulator_arm64": ("codex-agent-core-iossimulatorarm64", "iosSimulatorArm64"),
    "macos_arm64": ("codex-agent-core-macosarm64", "macosArm64"),
    "macos_x64": ("codex-agent-core-macosx64", "macosX64"),
    "linux_arm64": ("codex-agent-core-linuxarm64", "linuxArm64"),
    "linux_x64": ("codex-agent-core-linuxx64", "linuxX64"),
    "mingw_x64": ("codex-agent-core-mingwx64", "mingwX64"),
}
CONTRACT_VARIANT_PREFIXES = {
    artifact: prefix for artifact, prefix in CONTRACT_AVAILABLE_AT_TARGETS.values()
}
CONTRACT_VARIANT_TARGET_KEYS = {
    artifact: target for target, (artifact, _) in CONTRACT_AVAILABLE_AT_TARGETS.items()
}
SHA256_HEX = re.compile(r"[0-9a-f]{64}")
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
CONTRACT_EVIDENCE_PATH_ROLES = {
    "evidence/canonical-api.json": "canonical-api",
    "evidence/canonical-coverage.json": "canonical-coverage",
    "evidence/codex_app_server_protocol.schemas.json": "protocol-schema",
    "evidence/codex_app_server_protocol.v2.schemas.json": "protocol-schema",
    "evidence/descriptors.json": "protocol-descriptor",
    "evidence/kotlin-parity.json": "kotlin-parity",
    "evidence/protocol-source-verification.json": "protocol-source-verification",
    "evidence/provenance.json": "protocol-provenance",
    "inventories/contract-binary-inputs.git-tree": "inventory",
    "inventories/contract-validation-inputs.git-tree": "inventory",
}

def _sorted_unique(values: list[str], label: str) -> None:
    if values != sorted(values) or len(values) != len(set(values)):
        raise ValueError(f"{label} must be sorted and unique")


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


def contract_maven_identity(path: Any, contract_version: str) -> dict[str, str]:
    relative = require_relative_path(path, "Contract Maven path")
    version = require_semver(contract_version, "Contract Maven version")
    parts = relative.split("/")
    if len(parts) != 7 or parts[:4] != ["maven", "io", "github", "codex-agent-labs"]:
        raise ValueError(f"Contract Maven path is outside the canonical group: {relative}")
    artifact, path_version, filename = parts[4:]
    component = CONTRACT_ARTIFACT_COMPONENTS.get(artifact)
    if component is None or path_version != version:
        raise ValueError(f"Contract Maven artifact or version is invalid: {relative}")
    checksum = next((suffix for suffix in CONTRACT_CHECKSUM_SUFFIXES if filename.endswith(suffix)), None)
    primary = filename.removesuffix(checksum) if checksum else filename
    signed = primary.endswith(".asc")
    unsigned = primary.removesuffix(".asc") if signed else primary
    stem = f"{artifact}-{version}"
    if unsigned == f"{stem}-sources.jar":
        base_role, kind = "sources", "sources"
    elif unsigned == f"{stem}-javadoc.jar":
        base_role, kind = "javadoc", "javadoc"
    elif unsigned == f"{stem}.pom":
        base_role, kind = "module-metadata", "pom"
    elif unsigned == f"{stem}.module":
        base_role, kind = "module-metadata", "gradle-module"
    elif unsigned == f"{stem}-kotlin-tooling-metadata.json":
        base_role, kind = "module-metadata", "kotlin-tooling-metadata"
    elif unsigned == f"{stem}-metadata.jar":
        base_role, kind = "runtime-resolution", "metadata-jar"
    elif any(unsigned == f"{stem}{suffix}" for suffix in CONTRACT_PAYLOAD_SUFFIXES):
        base_role, kind = "runtime-resolution", unsigned.rsplit(".", 1)[-1]
    else:
        raise ValueError(f"Contract Maven filename is invalid: {relative}")
    role = "checksum" if checksum else "signature" if signed else base_role
    return {"artifact": artifact, "component": component, "role": role, "kind": kind}


def contract_required_primary_paths(contract_version: str) -> set[str]:
    version = require_semver(contract_version, "Contract Maven version")
    paths: set[str] = set()
    for artifact, component in CONTRACT_ARTIFACT_COMPONENTS.items():
        stem = f"maven/io/github/codex-agent-labs/{artifact}/{version}/{artifact}-{version}"
        suffixes = [*CONTRACT_ANCILLARY_SUFFIXES, ".module", ".pom"]
        if component == "common":
            suffixes += ["-kotlin-tooling-metadata.json", ".jar"]
        elif component == "android":
            suffixes += [".aar"]
        elif component in {"jvm"}:
            suffixes += [".jar"]
        elif component in {"ios-arm64", "ios-simulator-arm64", "macos-arm64", "macos-x64"}:
            suffixes += ["-metadata.jar", ".klib"]
        else:
            suffixes += [".klib"]
        paths.update(stem + suffix for suffix in suffixes)
    return paths


def validate_contract_maven_inventory(
    records: list[dict[str, Any]],
    contract_version: str,
    contents: dict[str, bytes] | None = None,
) -> list[dict[str, Any]]:
    paths = [require_relative_path(record["path"], "Contract Maven inventory path") for record in records]
    _sorted_unique(paths, "Contract Maven inventory paths")
    required_primary = contract_required_primary_paths(contract_version)
    actual_primary: set[str] = set()
    signatures: set[str] = set()
    for record in records:
        identity = contract_maven_identity(record["path"], contract_version)
        if record.get("role") != identity["role"] or record.get("component") != identity["component"]:
            raise ValueError("Contract Maven inventory role or component is not canonical")
        if identity["role"] not in {"checksum", "signature"}:
            actual_primary.add(record["path"])
        elif identity["role"] == "signature":
            signatures.add(record["path"])
    if actual_primary != required_primary:
        raise ValueError("Contract Maven primary publication inventory is incomplete or unexpected")
    if signatures:
        raise ValueError("Contract Maven signatures are not accepted without PGP verification")
    expected_paths = required_primary | signatures | {
        path + suffix for path in required_primary for suffix in CONTRACT_CHECKSUM_SUFFIXES
    }
    if set(paths) != expected_paths:
        raise ValueError("Contract Maven sidecar inventory is incomplete or unexpected")
    if contents is not None:
        missing = set(paths) - set(contents)
        if missing:
            raise ValueError(f"Contract Maven contents are missing declared files: {sorted(missing)}")
        records_by_path = {record["path"]: record for record in records}
        for path in paths:
            member = contents[path]
            record = records_by_path[path]
            if len(member) != record["bytes"] or sha256_bytes(member) != record["sha256"]:
                raise ValueError(f"Contract Maven declared bytes or digest mismatch: {path}")
        for primary in required_primary:
            primary_contents = contents[primary]
            for suffix in CONTRACT_CHECKSUM_SUFFIXES:
                expected = hashlib.new(suffix[1:], primary_contents).hexdigest().encode("ascii")
                if contents[primary + suffix] != expected:
                    raise ValueError(f"Contract Maven checksum content mismatch: {primary + suffix}")
    return records


def _xml_name(element: ElementTree.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _xml_child(element: ElementTree.Element, name: str, *, required: bool = True) -> ElementTree.Element | None:
    matches = [child for child in element if _xml_name(child) == name]
    if len(matches) > 1 or (required and not matches):
        raise ValueError(f"Contract POM requires exactly one {name}")
    return matches[0] if matches else None


def _xml_text(element: ElementTree.Element, name: str, *, default: str | None = None) -> str:
    child = _xml_child(element, name, required=default is None)
    if child is None:
        return default or ""
    value = (child.text or "").strip()
    if not value:
        raise ValueError(f"Contract POM {name} must not be empty")
    return value


def _pom_literal(element: ElementTree.Element, name: str, *, default: str | None = None) -> str:
    value = _xml_text(element, name, default=default)
    if "$" in value:
        raise ValueError(f"Contract POM {name} must not use interpolation")
    return value


def _pom_dependencies(container: ElementTree.Element | None) -> list[dict[str, Any]]:
    if container is None:
        return []
    dependencies: list[dict[str, Any]] = []
    for dependency in container:
        if _xml_name(dependency) != "dependency":
            raise ValueError("Contract POM dependencies contain an unsupported element")
        allowed = {"groupId", "artifactId", "version", "scope", "type", "classifier", "optional", "exclusions"}
        if any(_xml_name(child) not in allowed for child in dependency):
            raise ValueError("Contract POM dependency contains an unsupported field")
        normalized: dict[str, Any] = {
            "group": _pom_literal(dependency, "groupId"),
            "module": _pom_literal(dependency, "artifactId"),
            "version": require_semver(
                _pom_literal(dependency, "version"), "Contract POM dependency version",
            ),
            "scope": _pom_literal(dependency, "scope", default="compile"),
            "type": _pom_literal(dependency, "type", default="jar"),
            "optional": _pom_literal(dependency, "optional", default="false"),
        }
        classifier = _xml_child(dependency, "classifier", required=False)
        if classifier is not None:
            normalized["classifier"] = _pom_literal(dependency, "classifier")
        exclusions_element = _xml_child(dependency, "exclusions", required=False)
        exclusions: list[dict[str, str]] = []
        if exclusions_element is not None:
            for exclusion in exclusions_element:
                if _xml_name(exclusion) != "exclusion":
                    raise ValueError("Contract POM exclusions contain an unsupported element")
                exclusions.append({
                    "group": _pom_literal(exclusion, "groupId"),
                    "module": _pom_literal(exclusion, "artifactId"),
                })
        normalized["exclusions"] = sorted(exclusions, key=lambda value: (value["group"], value["module"]))
        dependencies.append(normalized)
    return dependencies


def _contract_pom_semantics(contents: bytes, artifact: str, contract_version: str) -> dict[str, Any]:
    try:
        text = contents.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Contract POM must be UTF-8") from error
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("Contract POM must not contain a DTD or entity declaration")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as error:
        raise ValueError("Contract POM is malformed") from error
    if _xml_name(root) != "project" or _xml_text(root, "modelVersion") != "4.0.0" or \
            _xml_text(root, "groupId") != "io.github.codex-agent-labs" or \
            _xml_text(root, "artifactId") != artifact or _xml_text(root, "version") != contract_version:
        raise ValueError("Contract POM coordinate identity is invalid")
    forbidden_elements = {"parent", "distributionManagement", "relocation"}
    for element in root.iter():
        if _xml_name(element) in forbidden_elements:
            raise ValueError(
                f"Contract POM uses unsupported resolution semantics: {_xml_name(element)}"
            )
    for forbidden in ("profiles", "repositories", "pluginRepositories"):
        if _xml_child(root, forbidden, required=False) is not None:
            raise ValueError(f"Contract POM uses unsupported resolution semantics: {forbidden}")
    properties_element = _xml_child(root, "properties", required=False)
    properties = {} if properties_element is None else {
        _xml_name(child): (child.text or "").strip() for child in properties_element
    }
    managed_element = _xml_child(root, "dependencyManagement", required=False)
    managed = [] if managed_element is None else _pom_dependencies(_xml_child(managed_element, "dependencies"))
    packaging = _xml_text(root, "packaging", default="jar")
    expected_packaging = "aar" if artifact == "codex-agent-core-android" else \
        "jar" if artifact in {"codex-agent-core", "codex-agent-core-jvm"} else "klib"
    if packaging != expected_packaging:
        raise ValueError(f"Contract POM packaging does not match {artifact}")
    return {
        "artifact": artifact,
        "packaging": packaging,
        "properties": properties,
        "dependencies": _pom_dependencies(_xml_child(root, "dependencies", required=False)),
        "dependencyManagement": managed,
    }


def _version_neutral_file_name(value: Any, label: str, contract_version: str) -> str:
    name = require_relative_path(value, label)
    if "/" in name:
        raise ValueError(f"{label} must be a single Maven file name")
    return name.replace(contract_version, "{contractVersion}")


def _contract_module_file_name(
    artifact: str,
    identity: dict[str, str],
    url: str,
    contract_version: str,
) -> str:
    if artifact == "codex-agent-core" and identity["role"] == "sources":
        return f"codex-agent-core-kotlin-{contract_version}-sources.jar"
    if artifact == "codex-agent-core" and identity["kind"] == "jar":
        return f"codex-agent-core-metadata-{contract_version}.jar"
    if artifact == "codex-agent-core-android" and identity["kind"] == "aar":
        return "codex-agent-core.aar"
    if identity["kind"] == "klib" and artifact in CONTRACT_KLIB_FILE_NAMES:
        return f"codex-agent-core-{CONTRACT_KLIB_FILE_NAMES[artifact]}-{contract_version}.klib"
    return url


def _contract_variant_role(attributes: dict[str, Any], name: str) -> str:
    category = attributes.get("org.gradle.category")
    docstype = attributes.get("org.gradle.docstype")
    if category == "documentation":
        if docstype not in {"sources", "javadoc"}:
            raise ValueError(f"Contract module variant {name} has unsupported documentation attributes")
        return docstype
    if docstype is not None:
        raise ValueError(f"Contract module variant {name} has inconsistent documentation attributes")
    if category != "library":
        raise ValueError(f"Contract module variant {name} must use the library category")
    usage = attributes.get("org.gradle.usage")
    if usage in {"java-api", "kotlin-api"}:
        return "api"
    if usage in {"java-runtime", "kotlin-runtime"}:
        return "runtime"
    if usage == "kotlin-metadata":
        return "metadata"
    raise ValueError(f"Contract module variant {name} has unsupported usage")


def _contract_variant_target(attributes: dict[str, Any], name: str) -> tuple[str, str]:
    platform = attributes.get("org.jetbrains.kotlin.platform.type")
    target_key = attributes.get("org.jetbrains.kotlin.native.target") if platform == "native" else platform
    target = CONTRACT_AVAILABLE_AT_TARGETS.get(target_key)
    if target is None or (platform == "wasm" and attributes.get("org.jetbrains.kotlin.wasm.target") != "js"):
        raise ValueError(f"Contract module variant {name} has unsupported target attributes")
    return target


def _contract_target_variant_name(prefix: str, role: str) -> str:
    suffix = {
        "api": "ApiElements",
        "runtime": "RuntimeElements",
        "metadata": "MetadataElements",
        "sources": "SourcesElements",
        "javadoc": "JavadocElements",
    }[role]
    return f"{prefix}{suffix}-published"


def _contract_target_variant_roles(artifact: str) -> set[str]:
    component = CONTRACT_ARTIFACT_COMPONENTS[artifact]
    if component in {"android", "jvm", "node-js", "node-wasm"}:
        return {"api", "runtime", "sources"}
    if component in {"ios-arm64", "ios-simulator-arm64", "macos-arm64", "macos-x64"}:
        return {"api", "metadata", "sources"}
    return {"api", "sources"}


def _contract_expected_variant_attributes(artifact: str, role: str) -> dict[str, str]:
    if artifact == "codex-agent-core":
        attributes = {
            "org.gradle.jvm.environment": "non-jvm",
            "org.gradle.usage": "kotlin-runtime" if role == "sources" else "kotlin-metadata",
            "org.jetbrains.kotlin.platform.type": "common",
        }
    else:
        component = CONTRACT_ARTIFACT_COMPONENTS[artifact]
        target = CONTRACT_VARIANT_TARGET_KEYS[artifact]
        if component == "android":
            environment, platform = "android", "androidJvm"
            usage = "java-api" if role == "api" else "java-runtime"
        elif component == "jvm":
            environment, platform = "standard-jvm", "jvm"
            usage = "java-api" if role == "api" else "java-runtime"
        else:
            environment = "non-jvm"
            platform = "native" if component not in {"node-js", "node-wasm"} else \
                "js" if component == "node-js" else "wasm"
            usage = "kotlin-api" if role == "api" else \
                "kotlin-metadata" if role == "metadata" else "kotlin-runtime"
        attributes = {
            "org.gradle.jvm.environment": environment,
            "org.gradle.usage": usage,
            "org.jetbrains.kotlin.platform.type": platform,
        }
        if component in {"android", "jvm"}:
            attributes["org.gradle.libraryelements"] = "jar" if role == "sources" else \
                "aar" if component == "android" else "jar"
        elif component == "node-js":
            attributes["org.jetbrains.kotlin.js.compiler"] = "ir"
        elif component == "node-wasm":
            attributes["org.jetbrains.kotlin.wasm.target"] = "js"
        else:
            attributes["org.jetbrains.kotlin.native.target"] = target
    if role in {"sources", "javadoc"}:
        attributes.update({
            "org.gradle.category": "documentation",
            "org.gradle.dependency.bundling": "external",
            "org.gradle.docstype": role,
        })
    else:
        attributes["org.gradle.category"] = "library"
    return attributes


def _contract_expected_variant_names(artifact: str) -> set[str]:
    if artifact != "codex-agent-core":
        prefix = CONTRACT_VARIANT_PREFIXES[artifact]
        return {_contract_target_variant_name(prefix, role) for role in _contract_target_variant_roles(artifact)}
    names = {"metadataApiElements", "metadataSourcesElements"}
    for target_artifact, prefix in CONTRACT_VARIANT_PREFIXES.items():
        names.update(
            _contract_target_variant_name(prefix, role)
            for role in _contract_target_variant_roles(target_artifact)
        )
    return names


def _contract_available_at_target(attributes: dict[str, Any], name: str) -> str:
    artifact, prefix = _contract_variant_target(attributes, name)
    role = _contract_variant_role(attributes, name)
    if role == "javadoc":
        raise ValueError(f"Contract module variant {name} has unsupported available-at documentation")
    if name != _contract_target_variant_name(prefix, role):
        raise ValueError(f"Contract module variant {name} does not match its available-at attributes")
    if attributes != _contract_expected_variant_attributes(artifact, role):
        raise ValueError(f"Contract module variant {name} attributes are not canonical")
    return artifact


def _contract_local_variant_path(
    artifact: str,
    attributes: dict[str, Any],
    name: str,
    contract_version: str,
) -> str:
    role = _contract_variant_role(attributes, name)
    stem = f"maven/io/github/codex-agent-labs/{artifact}/{contract_version}/{artifact}-{contract_version}"
    if artifact == "codex-agent-core":
        expected_name = "metadataSourcesElements" if role == "sources" else "metadataApiElements"
        if role not in {"sources", "metadata"} or name != expected_name:
            raise ValueError(f"Contract module variant {name} is not a canonical common variant")
        if attributes != _contract_expected_variant_attributes(artifact, role):
            raise ValueError(f"Contract module variant {name} attributes are not canonical")
        return stem + ("-sources.jar" if role == "sources" else ".jar")
    expected_artifact, prefix = _contract_variant_target(attributes, name)
    if artifact != expected_artifact or name != _contract_target_variant_name(prefix, role):
        raise ValueError(f"Contract module variant {name} does not match its publication target")
    if attributes != _contract_expected_variant_attributes(artifact, role):
        raise ValueError(f"Contract module variant {name} attributes are not canonical")
    if role == "sources":
        return stem + "-sources.jar"
    if role == "javadoc":
        return stem + "-javadoc.jar"
    component = CONTRACT_ARTIFACT_COMPONENTS[artifact]
    if component == "android" and role in {"api", "runtime"}:
        return stem + ".aar"
    if component == "jvm" and role in {"api", "runtime"}:
        return stem + ".jar"
    if component in {"node-js", "node-wasm"} and role in {"api", "runtime"}:
        return stem + ".klib"
    if component in {"ios-arm64", "ios-simulator-arm64", "macos-arm64", "macos-x64"} and \
            role == "metadata":
        return stem + "-metadata.jar"
    if component not in {"common", "android", "jvm", "node-js", "node-wasm"} and role == "api":
        return stem + ".klib"
    raise ValueError(f"Contract module variant {name} has no canonical publication payload")


def _contract_module_file(
    value: Any,
    artifact: str,
    contract_version: str,
    maven_contents: dict[str, bytes],
    runtime_records: dict[str, dict[str, Any]],
    label: str,
) -> tuple[str, str, dict[str, Any]]:
    member = require_exact_keys(
        value,
        {"name", "url", "size", "sha512", "sha256", "sha1", "md5"},
        label,
    )
    raw_name = require_relative_path(member["name"], f"{label}.name")
    if "/" in raw_name:
        raise ValueError(f"{label}.name must be a single Maven file name")
    url = require_relative_path(member["url"], f"{label}.url")
    if "/" in url:
        raise ValueError(f"{label}.url must be a single Maven file name")
    path = f"maven/io/github/codex-agent-labs/{artifact}/{contract_version}/{url}"
    identity = contract_maven_identity(path, contract_version)
    if identity["artifact"] != artifact or identity["role"] not in {
        "runtime-resolution", "sources", "javadoc",
    }:
        raise ValueError(f"{label} does not reference a canonical publication payload")
    if raw_name != _contract_module_file_name(artifact, identity, url, contract_version):
        raise ValueError(f"{label}.name does not match its Maven primary")
    actual = maven_contents.get(path)
    if actual is None:
        raise ValueError(f"{label} references a missing Maven primary: {path}")
    size = require_integer(member["size"], f"{label}.size", 1)
    expected = {
        "md5": hashlib.md5(actual).hexdigest(),
        "sha1": hashlib.sha1(actual).hexdigest(),
        "sha256": hashlib.sha256(actual).hexdigest(),
        "sha512": hashlib.sha512(actual).hexdigest(),
    }
    if size != len(actual) or any(member[field] != digest for field, digest in expected.items()):
        raise ValueError(f"{label} size or digest does not match its Maven primary")
    if identity["role"] == "runtime-resolution":
        record = runtime_records.get(path)
        if record is None or record["bytes"] != size or record["sha256"] != f"sha256:{expected['sha256']}":
            raise ValueError(f"{label} runtime primary is not in the declared component closure")
    return identity["role"], path, {
        "kind": identity["kind"],
        "name": _version_neutral_file_name(raw_name, f"{label}.name", contract_version),
        "url": url.replace(contract_version, "{contractVersion}"),
        "size": size,
        **expected,
    }


def _contract_module_semantics(
    contents: bytes,
    artifact: str,
    contract_version: str,
    maven_contents: dict[str, bytes],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    value = require_exact_keys(
        load_json_bytes(contents), {"formatVersion", "component", "createdBy", "variants"},
        "Contract Gradle module metadata",
    )
    if value["formatVersion"] != "1.1":
        raise ValueError("Unsupported Contract Gradle module metadata format")
    component_keys = {"group", "module", "version", "attributes"}
    if artifact != "codex-agent-core":
        component_keys.add("url")
    component = require_exact_keys(value["component"], component_keys, "Contract module component")
    if component["group"] != "io.github.codex-agent-labs" or component["module"] != "codex-agent-core" or \
            component["version"] != contract_version:
        raise ValueError("Contract Gradle module component identity is invalid")
    if artifact != "codex-agent-core" and component["url"] != \
            f"../../codex-agent-core/{contract_version}/codex-agent-core-{contract_version}.module":
        raise ValueError("Contract target module does not reference the canonical root module")
    require_object(component["attributes"], "Contract module component attributes")
    created_by = require_exact_keys(value["createdBy"], {"gradle"}, "Contract module createdBy")
    gradle = require_exact_keys(created_by["gradle"], {"version"}, "Contract module Gradle producer")
    require_string(gradle["version"], "Contract module Gradle version")
    variants: list[dict[str, Any]] = []
    names: list[str] = []
    runtime_records = {
        record["path"]: record
        for record in records
        if (identity := contract_maven_identity(record["path"], contract_version))["artifact"] == artifact
        and identity["role"] == "runtime-resolution"
    }
    referenced_runtime: set[str] = set()
    for index, member in enumerate(require_array(value["variants"], "Contract module variants")):
        variant = require_object(member, f"Contract module variants[{index}]")
        allowed_shapes = (
            {"name", "attributes", "files"},
            {"name", "attributes", "dependencies", "files"},
            {"name", "attributes", "available-at"},
        )
        if set(variant) not in allowed_shapes:
            raise ValueError("Contract Gradle module variant shape is unsupported")
        name = require_string(variant["name"], "Contract module variant name")
        names.append(name)
        attributes = require_object(variant["attributes"], "Contract module variant attributes")
        role = _contract_variant_role(attributes, name)
        documentation = role in {"sources", "javadoc"}
        if "files" in variant and ("dependencies" in variant) != (not documentation):
            raise ValueError(f"Contract module variant {name} dependency shape is not canonical")
        normalized: dict[str, Any] = {
            "name": name,
            "attributes": attributes,
        }
        if "dependencies" in variant:
            dependencies = []
            for dependency in require_array(variant["dependencies"], "Contract module dependencies"):
                dependency = require_exact_keys(
                    dependency, {"group", "module", "version"}, "Contract module dependency",
                )
                version = require_exact_keys(
                    dependency["version"], {"requires"}, "Contract module dependency version",
                )
                dependencies.append({
                    "group": require_string(dependency["group"], "Contract module dependency group"),
                    "module": require_string(dependency["module"], "Contract module dependency module"),
                    "version": require_semver(version["requires"], "Contract module dependency version"),
                })
            normalized["dependencies"] = dependencies
        if "available-at" in variant:
            if artifact != "codex-agent-core":
                raise ValueError("Only the Contract root module may declare available-at variants")
            available = require_exact_keys(
                variant["available-at"], {"group", "module", "version", "url"},
                "Contract module available-at",
            )
            target = require_string(available["module"], "Contract module available-at module")
            expected_target = _contract_available_at_target(attributes, name)
            if available["group"] != "io.github.codex-agent-labs" or target != expected_target or \
                    available["version"] != contract_version or \
                    available["url"] != f"../../{target}/{contract_version}/{target}-{contract_version}.module":
                raise ValueError("Contract module available-at identity is invalid")
            normalized["availableAt"] = {"group": available["group"], "module": target}
        if "files" in variant:
            expected_path = _contract_local_variant_path(
                artifact, attributes, name, contract_version,
            )
            runtime_files: list[dict[str, Any]] = []
            file_paths: list[str] = []
            for file_index, file_value in enumerate(require_array(variant["files"], "Contract module files")):
                role, path, file_semantics = _contract_module_file(
                    file_value,
                    artifact,
                    contract_version,
                    maven_contents,
                    runtime_records,
                    f"Contract module variant {name}.files[{file_index}]",
                )
                file_paths.append(path)
                if role == "runtime-resolution":
                    referenced_runtime.add(path)
                    runtime_files.append(file_semantics)
            if len(file_paths) != len(set(file_paths)):
                raise ValueError(f"Contract module variant {name} repeats a Maven primary")
            if file_paths != [expected_path]:
                raise ValueError(f"Contract module variant {name} does not reference its canonical payload")
            if runtime_files:
                normalized["runtimeFiles"] = sorted(runtime_files, key=canonical_json_bytes)
        if not documentation:
            variants.append(normalized)
    if len(names) != len(set(names)):
        raise ValueError("Contract module variant names must be unique")
    if set(names) != _contract_expected_variant_names(artifact):
        raise ValueError("Contract Gradle module variant inventory is incomplete or unexpected")
    if referenced_runtime != set(runtime_records):
        raise ValueError("Contract Gradle module runtime file association is incomplete")
    variants.sort(key=lambda item: item["name"])
    return {"artifact": artifact, "componentAttributes": component["attributes"], "variants": variants}


def contract_component_digest(
    records: list[dict[str, Any]],
    contract_version: str | None = None,
    contents: dict[str, bytes] | None = None,
) -> str:
    if contract_version is None:
        return sha256_bytes(canonical_json_bytes(records))
    identities = []
    for record in records:
        identity = contract_maven_identity(record["path"], contract_version)
        if identity["role"] == "runtime-resolution":
            identities.append({
                "artifact": identity["artifact"],
                "kind": identity["kind"],
                "bytes": record["bytes"],
                "sha256": record["sha256"],
            })
        elif identity["kind"] in {"pom", "gradle-module"}:
            if contents is None or record["path"] not in contents:
                raise ValueError("Contract component metadata bytes are required for semantic identity")
            semantic = _contract_pom_semantics(
                contents[record["path"]], identity["artifact"], contract_version,
            ) if identity["kind"] == "pom" else _contract_module_semantics(
                contents[record["path"]], identity["artifact"], contract_version, contents, records,
            )
            identities.append({"artifact": identity["artifact"], "kind": identity["kind"], "semantic": semantic})
        else:
            raise ValueError("Contract component identity contains ancillary Maven metadata")
    identities.sort(key=canonical_json_bytes)
    return sha256_bytes(canonical_json_bytes(identities))


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


def validate_contract_manifest(
    value: Any,
    maven_contents: dict[str, bytes] | None = None,
) -> dict[str, Any]:
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
            "producer",
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
    maven_identities = []
    for record in maven_files:
        identity = contract_maven_identity(record["path"], manifest["contractVersion"])
        if record["component"] != identity["component"] or record["role"] != identity["role"]:
            raise ValueError("Contract Maven role or component does not match its canonical path")
        maven_identities.append(identity)
    validate_contract_maven_inventory(maven_files, manifest["contractVersion"], maven_contents)
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
    evidence_path_roles = {record["path"]: record["role"] for record in evidence_files}
    if evidence_path_roles != CONTRACT_EVIDENCE_PATH_ROLES:
        raise ValueError("Contract evidence path/role inventory is incomplete or unexpected")
    publication_roles = {
        artifact: {
            identity["kind"]
            for identity in maven_identities
            if identity["artifact"] == artifact and identity["role"] in {"runtime-resolution", "module-metadata"}
        }
        for artifact in CONTRACT_ARTIFACT_COMPONENTS
    }
    if any(
        "pom" not in kinds or "gradle-module" not in kinds or not (kinds & {"aar", "jar", "klib"})
        for kinds in publication_roles.values()
    ):
        raise ValueError("Every Contract publication requires a POM, Gradle module, and runtime payload")
    closure_by_owner = {
        component_name: [
            record for record, identity in zip(maven_files, maven_identities)
            if record["component"] == component_name and (
                identity["role"] == "runtime-resolution" or (
                    identity["role"] == "module-metadata" and identity["kind"] in {"pom", "gradle-module"}
                )
            )
        ]
        for component_name in CONTRACT_COMPONENTS
    }
    if any(not records for records in closure_by_owner.values()):
        raise ValueError("Every Contract component must own a runtime-resolution closure")
    for component_name in CONTRACT_COMPONENTS:
        component = require_exact_keys(
            components[component_name], {"mavenPaths", "sha256"}, f"Contract component {component_name}",
        )
        paths = [
            require_relative_path(path, f"Contract component {component_name}.mavenPaths[]")
            for path in require_array(component["mavenPaths"], f"Contract component {component_name}.mavenPaths")
        ]
        _sorted_unique(paths, f"Contract component {component_name}.mavenPaths")
        owners = ("common",) if component_name == "common" else ("common", component_name)
        resolution_records = sorted(
            [record for owner in owners for record in closure_by_owner[owner]],
            key=lambda record: record["path"],
        )
        if paths != [record["path"] for record in resolution_records]:
            raise ValueError(f"Contract component {component_name} runtime-resolution closure is incomplete")
        component_digest = require_sha256(component["sha256"], f"Contract component {component_name}.sha256")
        if maven_contents is not None and component_digest != contract_component_digest(
            resolution_records, manifest["contractVersion"], maven_contents,
        ):
            raise ValueError(f"Contract component {component_name} digest mismatch")
    expected_contract_digest = contract_digest(
        manifest["canonicalApiDigest"],
        manifest["protocolDigest"],
        components["common"]["sha256"],
    )
    if manifest["contractDigest"] != expected_contract_digest:
        raise ValueError("Contract manifest contractDigest mismatch")
    validate_signing_metadata(manifest["signing"])
    validate_producer(manifest["producer"], "Contract manifest.producer")
    return manifest


def contract_evidence_identity(root: Path) -> dict[str, Any]:
    api_file = root / "evidence/canonical-api.json"
    coverage_file = root / "evidence/canonical-coverage.json"
    kotlin_file = root / "evidence/kotlin-parity.json"
    api = require_exact_keys(
        load_json(api_file),
        {
            "schema", "libraryUniqueName", "markerAnnotation", "signatureVersion", "boundaryTypes",
            "memberExclusionAnnotation", "excludedReachableTypes", "excludedMemberKeys",
            "dataClassMetadataAvailable", "dataClassNames", "owners", "targets",
        },
        "canonical API evidence",
    )
    if require_integer(api["schema"], "canonical API evidence.schema", 1) != 2 or \
            require_integer(api["signatureVersion"], "canonical API evidence.signatureVersion", 1) != 2 or \
            api["libraryUniqueName"] != "io.github.codex-agent-labs:codex-agent-core" or \
            api["markerAnnotation"] != "io.github.codex_agent_labs.codexagent.agent.CodexBindingApi" or \
            api["memberExclusionAnnotation"] != \
            "io.github.codex_agent_labs.codexagent.agent.CodexBindingApiKotlinOnly" or \
            require_boolean(api["dataClassMetadataAvailable"], "canonical API data-class metadata") is not True:
        raise ValueError("Canonical API evidence identity or schema is invalid")
    for field in ("boundaryTypes", "excludedReachableTypes", "excludedMemberKeys", "dataClassNames"):
        values = [
            require_string(member, f"canonical API evidence.{field}[]")
            for member in require_array(api[field], f"canonical API evidence.{field}")
        ]
        _sorted_unique(values, f"canonical API evidence.{field}")
    owners = require_array(api["owners"], "canonical API evidence.owners")
    owner_names: list[str] = []
    capabilities: list[str] = []
    for index, owner_value in enumerate(owners):
        owner = require_exact_keys(
            owner_value, {"name", "capabilities"}, f"canonical API evidence.owners[{index}]",
        )
        owner_names.append(require_string(owner["name"], f"canonical API evidence.owners[{index}].name"))
        members = [
            require_string(member, f"canonical API evidence.owners[{index}].capabilities[]")
            for member in require_array(
                owner["capabilities"], f"canonical API evidence.owners[{index}].capabilities",
            )
        ]
        _sorted_unique(members, f"canonical API evidence.owners[{index}].capabilities")
        capabilities.extend(members)
    _sorted_unique(owner_names, "canonical API evidence owner names")
    if len(capabilities) != 556 or len(capabilities) != len(set(capabilities)):
        raise ValueError("Canonical API evidence must contain exactly 556 unique capabilities")

    targets = [
        require_exact_keys(value, {"kind", "sha256"}, f"canonical API evidence.targets[{index}]")
        for index, value in enumerate(require_array(api["targets"], "canonical API evidence.targets"))
    ]
    if {target["kind"] for target in targets} != {"native", "wasm", "jvm-classes"} or len(targets) != 3 or \
            any(type(target["sha256"]) is not str or SHA256_HEX.fullmatch(target["sha256"]) is None
                for target in targets):
        raise ValueError("Canonical API target evidence is incomplete or malformed")

    coverage = require_exact_keys(
        load_json(coverage_file),
        {
            "schema", "result", "kotlinCompilerVersion", "canonicalTestTask", "apiReportSha256",
            "compiledTestsSha256", "testResultsSha256", "capabilities", "claims",
        },
        "canonical coverage evidence",
    )
    covered = [
        require_string(member, "canonical coverage evidence.capabilities[]")
        for member in require_array(coverage["capabilities"], "canonical coverage evidence.capabilities")
    ]
    _sorted_unique(covered, "canonical coverage evidence.capabilities")
    raw_api_digest = sha256_file(api_file).removeprefix("sha256:")
    if require_integer(coverage["schema"], "canonical coverage evidence.schema", 1) != 2 or \
            coverage["result"] != "passed" or \
            require_string(coverage["kotlinCompilerVersion"], "canonical coverage Kotlin compiler") == "" or \
            coverage["canonicalTestTask"] != ":codex-agent-core:jvmTest" or \
            coverage["apiReportSha256"] != raw_api_digest or \
            any(type(coverage[field]) is not str or SHA256_HEX.fullmatch(coverage[field]) is None
                for field in ("compiledTestsSha256", "testResultsSha256")) or \
            covered != sorted(capabilities):
        raise ValueError("Canonical coverage evidence is not complete for the canonical API")
    claim_test_ids: list[str] = []
    claimed: set[str] = set()
    for index, value in enumerate(require_array(coverage["claims"], "canonical coverage evidence.claims")):
        claim = require_exact_keys(value, {"testId", "capabilities"}, f"canonical coverage claim[{index}]")
        claim_test_ids.append(require_string(claim["testId"], f"canonical coverage claim[{index}].testId"))
        members = [
            require_string(member, f"canonical coverage claim[{index}].capabilities[]")
            for member in require_array(claim["capabilities"], f"canonical coverage claim[{index}].capabilities")
        ]
        _sorted_unique(members, f"canonical coverage claim[{index}].capabilities")
        if not members or not set(members).issubset(set(covered)):
            raise ValueError("Canonical coverage claim is empty or stale")
        claimed.update(members)
    _sorted_unique(claim_test_ids, "canonical coverage claim test IDs")
    if claimed != set(covered):
        raise ValueError("Canonical coverage claims do not cover the complete API")

    semantic_api = {key: value for key, value in api.items() if key != "targets"}
    api_digest = sha256_bytes(canonical_json_bytes(semantic_api))
    coverage_digest = sha256_file(coverage_file)

    kotlin = require_exact_keys(
        load_json(kotlin_file),
        {
            "schema", "result", "phase", "language", "canonical", "artifacts", "hostConsumerProofs",
            "testProgramSha256", "testResultsSha256", "publicSymbols", "tests", "scenarios", "claims",
            "exclusions",
        },
        "Kotlin parity evidence",
    )
    canonical = require_exact_keys(
        kotlin["canonical"], {"apiReportSha256", "coverageReceiptSha256"},
        "Kotlin parity evidence.canonical",
    )
    symbols = [
        require_string(member, "Kotlin parity evidence.publicSymbols[]")
        for member in require_array(kotlin["publicSymbols"], "Kotlin parity evidence.publicSymbols")
    ]
    test_ids: list[str] = []
    for index, value in enumerate(require_array(kotlin["tests"], "Kotlin parity evidence.tests")):
        test = require_exact_keys(value, {"id", "status"}, f"Kotlin parity evidence.tests[{index}]")
        test_ids.append(require_string(test["id"], f"Kotlin parity evidence.tests[{index}].id"))
        if test["status"] != "passed":
            raise ValueError("Kotlin parity test did not pass")
    _sorted_unique(test_ids, "Kotlin parity test IDs")
    scenario_ids: list[str] = []
    for index, value in enumerate(require_array(kotlin["scenarios"], "Kotlin parity evidence.scenarios")):
        scenario = require_exact_keys(value, {"id", "testIds"}, f"Kotlin parity scenario[{index}]")
        scenario_ids.append(require_string(scenario["id"], f"Kotlin parity scenario[{index}].id"))
        scenario_tests = [
            require_string(member, f"Kotlin parity scenario[{index}].testIds[]")
            for member in require_array(scenario["testIds"], f"Kotlin parity scenario[{index}].testIds")
        ]
        _sorted_unique(scenario_tests, f"Kotlin parity scenario[{index}].testIds")
        if not scenario_tests or not set(scenario_tests).issubset(set(test_ids)):
            raise ValueError("Kotlin parity scenario does not name executed tests")
    _sorted_unique(scenario_ids, "Kotlin parity scenario IDs")
    expected_scenarios = {
        "async-failure", "async-success", "cancellation", "collection-immutability-ordering", "identity",
        "nullability", "parent-child-ownership", "repeated-close-dispose", "state-current-value",
        "state-subsequent-value", "structured-failure", "subscription-cancellation", "terminal-delivery",
        "value-conversion",
    }
    artifacts = require_array(kotlin["artifacts"], "Kotlin parity evidence.artifacts")
    artifact = require_exact_keys(
        artifacts[0] if len(artifacts) == 1 else None,
        {"id", "sha256"},
        "Kotlin parity artifact",
    )
    jvm_target = next(target for target in targets if target["kind"] == "jvm-classes")
    if require_integer(kotlin["schema"], "Kotlin parity evidence.schema", 1) != 4 or \
            kotlin["result"] != "passed" or kotlin["phase"] != "M8" or kotlin["language"] != "kotlin" or \
            canonical["apiReportSha256"] != raw_api_digest or \
            canonical["coverageReceiptSha256"] != coverage_digest.removeprefix("sha256:") or \
            symbols != covered or len(test_ids) != 14 or set(scenario_ids) != expected_scenarios or \
            artifact != {"id": "kotlin-public-api", "sha256": jvm_target["sha256"]} or \
            require_array(kotlin["hostConsumerProofs"], "Kotlin host proofs") or \
            require_array(kotlin["claims"], "Kotlin claims") or \
            require_array(kotlin["exclusions"], "Kotlin exclusions") or \
            any(type(kotlin[field]) is not str or SHA256_HEX.fullmatch(kotlin[field]) is None
                for field in ("testProgramSha256", "testResultsSha256")):
        raise ValueError("Kotlin parity evidence is not the complete canonical projection")

    protocol_paths = [
        path for path, role in CONTRACT_EVIDENCE_PATH_ROLES.items()
        if role in {"protocol-schema", "protocol-descriptor"}
    ]
    protocol_records = [
        {
            "path": path,
            "bytes": (root / path).stat().st_size,
            "sha256": sha256_file(root / path),
        }
        for path in sorted(protocol_paths)
    ]
    protocol_report = require_exact_keys(
        load_json(root / "evidence/protocol-source-verification.json"),
        {
            "schemaVersion", "result", "schemaSha256", "completeSchemaSha256", "descriptorSha256",
            "provenanceSha256", "generatedOutputCount",
        },
        "protocol source verification",
    )
    if require_integer(protocol_report["schemaVersion"], "protocol verification schema", 1) != 1 or \
            protocol_report["result"] != "passed" or \
            require_integer(protocol_report["generatedOutputCount"], "generated protocol output count", 1) < 1 or \
            protocol_report["schemaSha256"] != sha256_file(
                root / "evidence/codex_app_server_protocol.v2.schemas.json",
            ).removeprefix("sha256:") or \
            protocol_report["completeSchemaSha256"] != sha256_file(
                root / "evidence/codex_app_server_protocol.schemas.json",
            ).removeprefix("sha256:") or \
            protocol_report["descriptorSha256"] != sha256_file(
                root / "evidence/descriptors.json",
            ).removeprefix("sha256:") or \
            protocol_report["provenanceSha256"] != sha256_file(
                root / "evidence/provenance.json",
            ).removeprefix("sha256:"):
        raise ValueError("Protocol source verification does not bind the bundled protocol evidence")
    return {
        "canonicalApiDigest": api_digest,
        "canonicalCoverageDigest": coverage_digest,
        "protocolDigest": sha256_bytes(canonical_json_bytes(protocol_records)),
        "capabilityCount": len(capabilities),
    }


def verify_contract_git_inventories(root: Path, producer: dict[str, Any]) -> None:
    validate_producer(producer, "Contract inventory producer")
    for relative in (
        "inventories/contract-binary-inputs.git-tree",
        "inventories/contract-validation-inputs.git-tree",
    ):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Contract Git inventory is missing or unsafe: {relative}")
        try:
            lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
        except UnicodeError as error:
            raise ValueError(f"Contract Git inventory is not UTF-8: {relative}") from error
        if len(lines) < 2 or lines[0] != f"tree\t{producer['tree']}" or lines[1:] != sorted(set(lines[1:])):
            raise ValueError(f"Contract Git inventory is incomplete or not bound to its producer tree: {relative}")
        for line in lines[1:]:
            fields = line.split("\t")
            if len(fields) != 4 or fields[0] not in {"100644", "100755"} or fields[1] != "blob" or \
                    len(fields[2]) != 40 or any(character not in "0123456789abcdef" for character in fields[2]):
                raise ValueError(f"Contract Git inventory record is malformed: {relative}")
            require_relative_path(fields[3], f"Contract Git inventory path in {relative}")


def _verify_contract_evidence(root: Path, manifest: dict[str, Any]) -> None:
    identity = contract_evidence_identity(root)
    if any(manifest[field] != value for field, value in identity.items()):
        raise ValueError("Contract manifest evidence digests do not match the bundled evidence")
    verify_contract_git_inventories(root, manifest["producer"])


def verify_contract_bundle(
    archive: Path,
    public_key: Path,
    *,
    expected_trust_domain: str,
) -> dict[str, Any]:
    archive = Path(archive)
    zip_records, contents, _ = verified_zip_contents(
        archive,
        max_archive_bytes=512 * 1024 * 1024,
        max_central_directory_bytes=32 * 1024 * 1024,
        max_members=4096,
        max_entry_bytes=256 * 1024 * 1024,
        max_total_bytes=1024 * 1024 * 1024,
        max_compression_ratio=200,
        canonical_stored=True,
    )
    if set(contents) < {"contract-manifest.json", "contract-manifest.sig"}:
        raise ValueError("Contract Bundle is missing its manifest or signature")
    manifest = validate_contract_manifest(
        load_canonical_json_bytes(contents["contract-manifest.json"]),
        {path: contents[path] for path in contents if path.startswith("maven/")},
    )
    expected_name = f"codex-agent-contract-{manifest['contractVersion']}.zip"
    if archive.name != expected_name:
        raise ValueError(f"Contract Bundle must be named {expected_name}")
    validate_signing_metadata(manifest["signing"], trust_domain=expected_trust_domain)
    actual = {record["relativePath"]: record for record in zip_records}
    declared = {
        record["path"]: {"relativePath": record["path"], "bytes": record["bytes"], "sha256": record["sha256"]}
        for record in manifest["mavenFiles"] + manifest["evidenceFiles"]
    }
    special = {"contract-manifest.json", "contract-manifest.sig"}
    if set(actual) != special | set(declared):
        raise ValueError("Contract Bundle file set differs from its complete allow-list")
    if any(actual[path] != record for path, record in declared.items()):
        raise ValueError("Contract Bundle declared file bytes or digest differ")
    with tempfile.TemporaryDirectory(prefix="codex-agent-contract-bundle-") as temporary:
        root = Path(temporary)
        for path, member_contents in contents.items():
            target = root.joinpath(*path.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(member_contents)
        verify_manifest_signature(
            root / "contract-manifest.json",
            root / "contract-manifest.sig",
            Path(public_key),
            manifest["signing"],
        )
        _verify_contract_evidence(root, manifest)
    return manifest
