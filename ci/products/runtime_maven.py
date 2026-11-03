"""Exact Runtime Maven content checks, not original-receipt or host admission.

The aggregate caller separately binds every primary to authenticated originals.
This verifier consumes bytes only; it never resolves dependencies or runs tools.
"""
from __future__ import annotations

import hashlib
from xml.etree import ElementTree

from .contract_model import (
    CONTRACT_ARTIFACT_COMPONENTS, CONTRACT_CHECKSUM_SUFFIXES, CONTRACT_VARIANT_PREFIXES,
    _contract_expected_variant_attributes, _contract_target_variant_roles,
    _contract_variant_role, _pom_dependencies, _xml_child, _xml_name, _xml_text,
)
from .inventory import (
    load_json_bytes, require_array, require_exact_keys, require_integer,
    require_object, require_semver, require_string,
)
from .sdk_maven import _verify_pom


GROUP = "io.github.codex-agent-labs"
COMPONENTS = ("jvm", "node-js", "node-wasm", "macos-arm64", "macos-x64",
              "linux-arm64", "linux-x64", "windows-x64")
_CORE = {component: artifact for artifact, component in CONTRACT_ARTIFACT_COMPONENTS.items()
         if component in COMPONENTS}
_ADAPTERS = {"jvm", "node-js", "node-wasm"}
_CINTEROPS = {"-cinterop-codexDesktop.klib", "-cinterop-codexAgentC.klib"}
_API_DEPENDENCIES = {(GROUP, "codex-agent-core"), ("org.jetbrains.kotlin", "kotlin-stdlib")}
_IMPLEMENTATION_DEPENDENCIES = {("org.jetbrains.kotlinx", "kotlinx-coroutines-core"),
                              ("com.squareup.okio", "okio")}


def _require(condition, label):
    if not condition:
        raise ValueError(label)


def _suffixes(component):
    result = {".jar" if component == "jvm" else ".klib", "-sources.jar", "-javadoc.jar",
              ".pom", ".module"}
    if component not in _ADAPTERS:
        result |= _CINTEROPS
    if component in {"macos-arm64", "macos-x64"}:
        result.add("-metadata.jar")
    return result


def _role(suffix):
    return ("sources" if suffix == "-sources.jar" else
            "javadoc" if suffix == "-javadoc.jar" else
            "module-metadata" if suffix in {".pom", ".module"} else "runtime-resolution")


def _pom(contents, component, artifact, core, runtime_version, contract_version):
    _verify_pom(contents, GROUP, artifact, runtime_version)
    root = ElementTree.fromstring(contents)
    _require(all(element.tag.startswith("{http://maven.apache.org/POM/4.0.0}")
                 for element in root.iter()), "Runtime POM contains a foreign namespace")
    allowed = {"modelVersion", "groupId", "artifactId", "version", "packaging", "name",
               "description", "url", "inceptionYear", "licenses", "developers", "scm", "dependencies"}
    _require(all(_xml_name(child) in allowed for child in root), "Runtime POM has unsupported semantics")
    _require(_xml_text(root, "packaging", default="jar") ==
             ("jar" if core.endswith("-jvm") else "klib"), "Runtime POM packaging mismatch")
    dependencies = _pom_dependencies(_xml_child(root, "dependencies"))
    identities = [(item["group"], item["module"]) for item in dependencies]
    _require(len(identities) == len(set(identities)), "Runtime POM has duplicate dependencies")
    own = [item for item in dependencies if item["group"] == GROUP]
    _require(own == [{"group": GROUP, "module": core, "version": contract_version,
                      "scope": "compile", "type": "jar", "optional": "false", "exclusions": []}],
             "Runtime POM Contract dependency differs from the exact target/version")
    suffix = core.removeprefix("codex-agent-core-")
    expected = {(GROUP, core): ((GROUP, "codex-agent-core"), "compile"),
                ("org.jetbrains.kotlin", "kotlin-stdlib-" + suffix
                 if component in {"node-js", "node-wasm"} else "kotlin-stdlib"):
                (("org.jetbrains.kotlin", "kotlin-stdlib"), "compile")}
    for group, name in _IMPLEMENTATION_DEPENDENCIES:
        expected[group, name + "-" + suffix] = ((group, name), "runtime" if component in _ADAPTERS else "compile")
    if component == "node-js":
        expected["org.jetbrains.kotlin", "kotlin-dom-api-compat"] = (
            ("org.jetbrains.kotlin", "kotlin-dom-api-compat"), "compile")
    _require(set(identities) == set(expected), "Runtime POM dependency target inventory mismatch")
    versions = {}
    for item in dependencies:
        key, scope = expected[item["group"], item["module"]]
        _require(item == {"group": item["group"], "module": item["module"], "version": item["version"],
                          "scope": scope, "type": "jar", "optional": "false", "exclusions": []},
                 "Runtime POM dependency scope/type/exclusions mismatch")
        versions[key] = item["version"]
    return versions


def _module(contents, component, artifact, core, runtime_version, contract_version, primaries):
    module = require_exact_keys(load_json_bytes(contents),
                                {"formatVersion", "component", "createdBy", "variants"}, "Runtime GMM")
    _require(module["formatVersion"] == "1.1", "Runtime GMM format mismatch")
    _require(module["component"] == {"group": GROUP, "module": artifact, "version": runtime_version,
                                      "attributes": {"org.gradle.status": "release"}},
             "Runtime GMM coordinate identity mismatch")
    creator = require_exact_keys(module["createdBy"], {"gradle"}, "Runtime GMM creator")
    gradle = require_exact_keys(creator["gradle"], {"version"}, "Runtime GMM Gradle")
    require_semver(gradle["version"], "Runtime GMM Gradle version")
    variants = require_array(module["variants"], "Runtime GMM variants")
    expected_roles = _contract_target_variant_roles(core)
    role_order = (["api", "runtime", "sources"] if "runtime" in expected_roles else
                  ["api", "sources", "metadata"] if "metadata" in expected_roles else ["api", "sources"])
    title = {"node-js": "NodeJs", "node-wasm": "NodeWasm"}.get(component)
    if title is None:
        prefix = CONTRACT_VARIANT_PREFIXES[core]
        title = prefix[0].upper() + prefix[1:]
    roles, names, dependencies_by_role = set(), set(), {}
    for index, variant in enumerate(variants):
        variant = require_object(variant, "Runtime GMM variant")
        _require({"name", "attributes", "files"} <= variant.keys() <=
                 {"name", "attributes", "files", "dependencies"}, "Runtime GMM variant shape mismatch")
        name = require_string(variant["name"], "Runtime GMM variant name")
        attributes = require_object(variant["attributes"], "Runtime GMM variant attributes")
        role = _contract_variant_role(attributes, name)
        _require(index < len(role_order) and role == role_order[index] and
                 name == f"imported{title}RuntimeVariant{index}",
                 "Runtime GMM original target variant order/name mismatch")
        _require(name not in names and role not in roles, "Runtime GMM duplicate variant name/role")
        names.add(name)
        roles.add(role)
        _require(attributes == _contract_expected_variant_attributes(core, role),
                 "Runtime GMM target/usage attributes mismatch")
        dependencies = {}
        for record in require_array(variant.get("dependencies", []), "Runtime GMM dependencies"):
            record = require_exact_keys(record, {"group", "module", "version"}, "Runtime GMM dependency")
            version = require_exact_keys(record["version"], {"requires"}, "Runtime GMM dependency version")
            key = (require_string(record["group"], "Runtime dependency group"),
                   require_string(record["module"], "Runtime dependency module"))
            _require(key not in dependencies, "Runtime GMM duplicate dependency")
            dependencies[key] = require_semver(version["requires"], "Runtime dependency version")
        if role == "sources":
            _require(not dependencies, "Runtime sources variant must not carry dependencies")
        else:
            _require({key: version for key, version in dependencies.items() if key[0] == GROUP} ==
                     {(GROUP, "codex-agent-core"): contract_version},
                     "Runtime GMM Contract dependency differs from exact common/version")
        expected_dependencies = set() if role == "sources" else set(_API_DEPENDENCIES)
        if role != "sources" and (component not in _ADAPTERS or role == "runtime"):
            expected_dependencies |= _IMPLEMENTATION_DEPENDENCIES
        if component == "node-js" and role != "sources":
            expected_dependencies.add(("org.jetbrains.kotlin", "kotlin-dom-api-compat"))
        _require(set(dependencies) == expected_dependencies, "Runtime GMM dependency target/usage inventory mismatch")
        dependencies_by_role[role] = dependencies
        prefix = f"{artifact}-{runtime_version}"
        suffix = ("-sources.jar" if role == "sources" else "-metadata.jar" if role == "metadata" else
                  ".jar" if component == "jvm" else ".klib")
        required = prefix + suffix
        allowed = {required}
        # Actual all-eight KGP imported publications retain both native
        # cinterops in their API usage, not only in the repository inventory.
        if component not in _ADAPTERS and role == "api":
            allowed |= {prefix + value for value in _CINTEROPS}
        actual = set()
        for record in require_array(variant["files"], "Runtime GMM files"):
            record = require_exact_keys(record, {"name", "url", "size", "md5", "sha1", "sha256", "sha512"},
                                        "Runtime GMM file")
            filename = require_string(record["name"], "Runtime GMM file name")
            _require(filename in allowed and filename not in actual and record["url"] == filename,
                     "Runtime GMM file path/role mismatch")
            actual.add(filename)
            payload = primaries[filename]
            _require(require_integer(record["size"], "Runtime GMM file size", 1) == len(payload) and
                     all(record[algorithm] == hashlib.new(algorithm, payload).hexdigest()
                         for algorithm in ("md5", "sha1", "sha256", "sha512")),
                     "Runtime GMM file differs from exact publication bytes")
        _require(actual == allowed, "Runtime GMM lacks its exact primary/cinterop inventory")
    _require(roles == _contract_target_variant_roles(core), "Runtime GMM target variant roles mismatch")
    return dependencies_by_role


def validate_runtime_maven_publications(runtime_version, contract_version, records, contents):
    """Validate all eight exact release publications, without creating authority."""
    from .aggregate import _artifact_records, validate_runtime_maven_inventory

    require_semver(runtime_version, "Runtime Maven version")
    require_semver(contract_version, "Runtime Maven Contract version")
    records = _artifact_records(records, "Runtime Maven publications", component=True)
    require_object(contents, "Runtime Maven publication contents")
    _require(all(type(value) is bytes for value in contents.values()), "Runtime Maven contents must be bytes")
    validate_runtime_maven_inventory(records, contents)
    expected = {}
    for component in COMPONENTS:
        artifact = _CORE[component].replace("codex-agent-core-", "codex-agent-runtime-desktop-")
        prefix = f"maven/{component}/{GROUP.replace('.', '/')}/{artifact}/{runtime_version}/{artifact}-{runtime_version}"
        for suffix in _suffixes(component):
            for checksum in ("", *CONTRACT_CHECKSUM_SUFFIXES):
                expected[prefix + suffix + checksum] = (component, "checksum" if checksum else _role(suffix))
    _require(set(contents) == set(expected) == {record["path"] for record in records},
             "Runtime Maven exact eight-target GAV/primary inventory mismatch")
    _require(all((record["component"], record["role"]) == expected[record["path"]] for record in records),
             "Runtime Maven exact component/role mismatch")
    for component in COMPONENTS:
        core = _CORE[component]
        artifact = core.replace("codex-agent-core-", "codex-agent-runtime-desktop-")
        prefix = f"maven/{component}/{GROUP.replace('.', '/')}/{artifact}/{runtime_version}/"
        primaries = {f"{artifact}-{runtime_version}{suffix}": contents[prefix + f"{artifact}-{runtime_version}{suffix}"]
                     for suffix in _suffixes(component)}
        pom = _pom(primaries[f"{artifact}-{runtime_version}.pom"], component, artifact, core, runtime_version, contract_version)
        module = _module(primaries[f"{artifact}-{runtime_version}.module"], component, artifact, core,
                         runtime_version, contract_version, primaries)
        # Literal third-party versions must agree across Maven and Gradle views.
        # Their selection belongs to the source-keyed publication, not a second
        # version catalog hidden in this verifier.
        for key, version in pom.items():
            versions = {values[key] for values in module.values() if key in values}
            _require(versions == {version}, "Runtime POM/GMM dependency versions disagree")
