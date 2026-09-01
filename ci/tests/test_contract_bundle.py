from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

import ci.products.contract as contract_product
from ci.impact import read_pathspecs
from ci.products.contract_model import verify_contract_bundle, verify_contract_git_inventories
from ci.products.contract import (
    build_contract_bundle,
    build_development_contract_bundle,
    prepare_contract_inputs,
)
from ci.products.inventory import (
    canonical_json_bytes,
    regular_file_inventory,
    sha256_bytes,
    sha256_file,
    verified_zip_contents,
    write_canonical_json,
)
from ci.products.signatures import generate_development_key, sign_manifest


VERSION = "0.2.0"
ARCHIVE_NAME = f"codex-agent-contract-{VERSION}.zip"
TREE = "89abcdef0123456789abcdef0123456789abcdef"
ARTIFACT_COMPONENTS = {
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
PRIMARY_SUFFIXES = {
    "codex-agent-core": (
        "-javadoc.jar", "-kotlin-tooling-metadata.json", "-sources.jar", ".jar", ".module", ".pom",
    ),
    "codex-agent-core-android": ("-javadoc.jar", "-sources.jar", ".aar", ".module", ".pom"),
    "codex-agent-core-jvm": ("-javadoc.jar", "-sources.jar", ".jar", ".module", ".pom"),
    "codex-agent-core-iosarm64": (
        "-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom",
    ),
    "codex-agent-core-iossimulatorarm64": (
        "-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom",
    ),
    "codex-agent-core-macosarm64": (
        "-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom",
    ),
    "codex-agent-core-macosx64": (
        "-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom",
    ),
    "codex-agent-core-linuxarm64": ("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"),
    "codex-agent-core-linuxx64": ("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"),
    "codex-agent-core-mingwx64": ("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"),
    "codex-agent-core-js": ("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"),
    "codex-agent-core-wasm-js": ("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"),
}
SCENARIOS = sorted({
    "async-failure",
    "async-success",
    "cancellation",
    "collection-immutability-ordering",
    "identity",
    "nullability",
    "parent-child-ownership",
    "repeated-close-dispose",
    "state-current-value",
    "state-subsequent-value",
    "structured-failure",
    "subscription-cancellation",
    "terminal-delivery",
    "value-conversion",
})
CAPABILITIES = [f"capability-{index:03d}" for index in range(556)]
PRODUCER = {
    "repository": "codex-agent-labs/codex-agent",
    "workflowPath": ".github/workflows/contract.yml",
    "commit": "0123456789abcdef0123456789abcdef01234567",
    "tree": TREE,
    "event": "pull_request",
    "runId": 7,
    "runAttempt": 1,
    "pullRequest": 31,
}
CANONICAL_MODE = (stat.S_IFREG | 0o644) << 16
CHECKSUM_ALGORITHMS = {
    ".md5": "md5",
    ".sha1": "sha1",
    ".sha256": "sha256",
    ".sha512": "sha512",
}
RUNTIME_SUFFIXES = {".aar", ".jar", ".klib", "-metadata.jar"}
VARIANT_TARGETS = {
    "codex-agent-core-android": ("android", "androidJvm", None),
    "codex-agent-core-iosarm64": ("iosArm64", "native", "ios_arm64"),
    "codex-agent-core-iossimulatorarm64": (
        "iosSimulatorArm64",
        "native",
        "ios_simulator_arm64",
    ),
    "codex-agent-core-js": ("js", "js", None),
    "codex-agent-core-jvm": ("jvm", "jvm", None),
    "codex-agent-core-linuxarm64": ("linuxArm64", "native", "linux_arm64"),
    "codex-agent-core-linuxx64": ("linuxX64", "native", "linux_x64"),
    "codex-agent-core-macosarm64": ("macosArm64", "native", "macos_arm64"),
    "codex-agent-core-macosx64": ("macosX64", "native", "macos_x64"),
    "codex-agent-core-mingwx64": ("mingwX64", "native", "mingw_x64"),
    "codex-agent-core-wasm-js": ("wasmJs", "wasm", None),
}
KLIB_DISPLAY_TARGETS = {
    "codex-agent-core-iosarm64": "iosArm64Main",
    "codex-agent-core-iossimulatorarm64": "iosSimulatorArm64Main",
    "codex-agent-core-macosarm64": "macosArm64Main",
    "codex-agent-core-macosx64": "macosX64Main",
    "codex-agent-core-linuxarm64": "linuxArm64Main",
    "codex-agent-core-linuxx64": "linuxX64Main",
    "codex-agent-core-mingwx64": "mingwX64Main",
}


def _raw_digest(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _archive_name(version: str) -> str:
    return f"codex-agent-contract-{version}.zip"


def _maven_path(root: Path, artifact: str, suffix: str, version: str = VERSION) -> Path:
    return (
        root
        / "maven/io/github/codex-agent-labs"
        / artifact
        / version
        / f"{artifact}-{version}{suffix}"
    )


def _write_file(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)


def _write_jar(path: Path, contents: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        info = zipfile.ZipInfo("payload.bin", (1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        info.create_system = 3
        info.external_attr = CANONICAL_MODE
        archive.writestr(info, contents)


def _write_checksum_sidecars(path: Path) -> None:
    contents = path.read_bytes()
    for suffix, algorithm in CHECKSUM_ALGORITHMS.items():
        digest = hashlib.new(algorithm, contents).hexdigest().encode("ascii")
        _write_file(Path(f"{path}{suffix}"), digest)


def _module_file_record(path: Path, name: str | None = None) -> dict[str, object]:
    contents = path.read_bytes()
    return {
        "name": name or path.name,
        "url": path.name,
        "size": len(contents),
        **{
            algorithm: hashlib.new(algorithm, contents).hexdigest()
            for algorithm in ("md5", "sha1", "sha256", "sha512")
        },
    }


def _variant_roles(artifact: str) -> tuple[str, ...]:
    component = ARTIFACT_COMPONENTS[artifact]
    if component in {"android", "jvm", "node-js", "node-wasm"}:
        return ("api", "runtime", "sources")
    if component in {"ios-arm64", "ios-simulator-arm64", "macos-arm64", "macos-x64"}:
        return ("api", "sources", "metadata")
    return ("api", "sources")


def _variant_name(artifact: str, role: str) -> str:
    prefix = VARIANT_TARGETS[artifact][0]
    suffix = {
        "api": "ApiElements",
        "runtime": "RuntimeElements",
        "metadata": "MetadataElements",
        "sources": "SourcesElements",
    }[role]
    return f"{prefix}{suffix}-published"


def _variant_attributes(artifact: str, role: str) -> dict[str, str]:
    _, platform, native_target = VARIANT_TARGETS[artifact]
    documentation = role == "sources"
    java = platform in {"androidJvm", "jvm"}
    attributes = {
        "org.gradle.category": "documentation" if documentation else "library",
        "org.gradle.jvm.environment": (
            "android" if platform == "androidJvm" else "standard-jvm" if platform == "jvm" else "non-jvm"
        ),
        "org.gradle.usage": (
            "java-runtime" if documentation and java
            else "kotlin-runtime" if documentation
            else "java-api" if role == "api" and java
            else "kotlin-api" if role == "api"
            else "java-runtime" if role == "runtime" and java
            else "kotlin-runtime" if role == "runtime"
            else "kotlin-metadata"
        ),
        "org.jetbrains.kotlin.platform.type": platform,
    }
    if documentation:
        attributes.update({
            "org.gradle.dependency.bundling": "external",
            "org.gradle.docstype": "sources",
        })
    if platform in {"androidJvm", "jvm"}:
        attributes["org.gradle.libraryelements"] = "jar" if documentation or platform == "jvm" else "aar"
    if platform == "native":
        attributes["org.jetbrains.kotlin.native.target"] = native_target or ""
    elif platform == "js":
        attributes["org.jetbrains.kotlin.js.compiler"] = "ir"
    elif platform == "wasm":
        attributes["org.jetbrains.kotlin.wasm.target"] = "js"
    return attributes


def _variant_payload_suffix(artifact: str, role: str) -> str:
    component = ARTIFACT_COMPONENTS[artifact]
    if role == "sources":
        return "-sources.jar"
    if role == "metadata":
        return "-metadata.jar"
    if component == "android":
        return ".aar"
    if component == "jvm":
        return ".jar"
    return ".klib"


def _module_display_name(artifact: str, suffix: str, contract_version: str) -> str:
    if artifact == "codex-agent-core" and suffix == ".jar":
        return f"codex-agent-core-metadata-{contract_version}.jar"
    if artifact == "codex-agent-core" and suffix == "-sources.jar":
        return f"codex-agent-core-kotlin-{contract_version}-sources.jar"
    if artifact == "codex-agent-core-android" and suffix == ".aar":
        return "codex-agent-core.aar"
    if suffix == ".klib" and artifact in KLIB_DISPLAY_TARGETS:
        return f"codex-agent-core-{KLIB_DISPLAY_TARGETS[artifact]}-{contract_version}.klib"
    return _maven_path(Path(), artifact, suffix, contract_version).name


def _local_module_variant(
    root: Path,
    artifact: str,
    role: str,
    contract_version: str,
    dependency_version: str,
) -> dict[str, object]:
    suffix = _variant_payload_suffix(artifact, role)
    variant: dict[str, object] = {
        "name": _variant_name(artifact, role),
        "attributes": _variant_attributes(artifact, role),
        "files": [_module_file_record(
            _maven_path(root, artifact, suffix, contract_version),
            _module_display_name(artifact, suffix, contract_version),
        )],
    }
    if role != "sources":
        variant["dependencies"] = [{
            "group": "org.jetbrains.kotlinx",
            "module": "kotlinx-coroutines-core",
            "version": {"requires": dependency_version},
        }]
    return variant


def _common_module_variants(
    root: Path,
    contract_version: str,
    dependency_version: str,
) -> list[dict[str, object]]:
    dependency = [{
        "group": "org.jetbrains.kotlinx",
        "module": "kotlinx-coroutines-core",
        "version": {"requires": dependency_version},
    }]
    variants: list[dict[str, object]] = [
        {
            "name": "metadataApiElements",
            "attributes": {
                "org.gradle.category": "library",
                "org.gradle.jvm.environment": "non-jvm",
                "org.gradle.usage": "kotlin-metadata",
                "org.jetbrains.kotlin.platform.type": "common",
            },
            "dependencies": dependency,
            "files": [_module_file_record(
                _maven_path(root, "codex-agent-core", ".jar", contract_version),
                _module_display_name("codex-agent-core", ".jar", contract_version),
            )],
        },
        {
            "name": "metadataSourcesElements",
            "attributes": {
                "org.gradle.category": "documentation",
                "org.gradle.dependency.bundling": "external",
                "org.gradle.docstype": "sources",
                "org.gradle.jvm.environment": "non-jvm",
                "org.gradle.usage": "kotlin-runtime",
                "org.jetbrains.kotlin.platform.type": "common",
            },
            "files": [_module_file_record(
                _maven_path(root, "codex-agent-core", "-sources.jar", contract_version),
                _module_display_name("codex-agent-core", "-sources.jar", contract_version),
            )],
        },
    ]
    for target_artifact in VARIANT_TARGETS:
        for role in _variant_roles(target_artifact):
            variants.append({
                "name": _variant_name(target_artifact, role),
                "attributes": _variant_attributes(target_artifact, role),
                "available-at": {
                    "group": "io.github.codex-agent-labs",
                    "module": target_artifact,
                    "version": contract_version,
                    "url": (
                        f"../../{target_artifact}/{contract_version}/"
                        f"{target_artifact}-{contract_version}.module"
                    ),
                },
            })
    return variants


def _refresh_module_files(
    root: Path,
    artifact: str,
    contract_version: str = VERSION,
) -> None:
    module_path = _maven_path(root, artifact, ".module", contract_version)
    module = json.loads(module_path.read_bytes())
    for variant in module["variants"]:
        for record in variant.get("files", []):
            path = module_path.parent / record["url"]
            record.update(_module_file_record(path, record["name"]))
    write_canonical_json(module_path, module)
    _write_checksum_sidecars(module_path)


def _remove_primary(path: Path) -> None:
    path.unlink()
    for suffix in CHECKSUM_ALGORITHMS:
        Path(f"{path}{suffix}").unlink()


def _write_maven_publication(
    root: Path,
    artifact: str,
    component: str,
    *,
    contract_version: str,
    dependency_version: str,
) -> None:
    packaging = (
        ""
        if artifact in {"codex-agent-core", "codex-agent-core-jvm"}
        else "<packaging>aar</packaging>"
        if artifact == "codex-agent-core-android"
        else "<packaging>klib</packaging>"
    )
    pom = (
        '<project xmlns="http://maven.apache.org/POM/4.0.0">'
        "<modelVersion>4.0.0</modelVersion>"
        "<groupId>io.github.codex-agent-labs</groupId>"
        f"<artifactId>{artifact}</artifactId>"
        f"<version>{contract_version}</version>"
        f"{packaging}"
        "<dependencies><dependency>"
        "<groupId>org.jetbrains.kotlinx</groupId>"
        "<artifactId>kotlinx-coroutines-core</artifactId>"
        f"<version>{dependency_version}</version>"
        "</dependency></dependencies>"
        "</project>\n"
    ).encode()
    _write_file(_maven_path(root, artifact, ".pom", contract_version), pom)
    component_identity = {
        "attributes": {"org.gradle.status": "release"},
        "group": "io.github.codex-agent-labs",
        "module": "codex-agent-core",
        "version": contract_version,
    }
    if artifact != "codex-agent-core":
        component_identity["url"] = (
            f"../../codex-agent-core/{contract_version}/codex-agent-core-{contract_version}.module"
        )
    for suffix in PRIMARY_SUFFIXES[artifact]:
        if suffix in {".pom", ".module"}:
            continue
        path = _maven_path(root, artifact, suffix, contract_version)
        if suffix == "-kotlin-tooling-metadata.json":
            write_canonical_json(path, {"buildSystem": "Gradle", "buildSystemVersion": "8.14.3"})
        else:
            _write_jar(path, f"{suffix}:{component}\n".encode())
    write_canonical_json(
        _maven_path(root, artifact, ".module", contract_version),
        {
            "component": component_identity,
            "createdBy": {"gradle": {"version": "8.14.3"}},
            "formatVersion": "1.1",
            "variants": (
                _common_module_variants(root, contract_version, dependency_version)
                if artifact == "codex-agent-core"
                else [
                    _local_module_variant(
                        root,
                        artifact,
                        role,
                        contract_version,
                        dependency_version,
                    )
                    for role in _variant_roles(artifact)
                ]
            ),
        },
    )
    for suffix in PRIMARY_SUFFIXES[artifact]:
        _write_checksum_sidecars(_maven_path(root, artifact, suffix, contract_version))


def _write_staging(
    root: Path,
    *,
    target_hash_salt: bytes = b"",
    mutate_capability: bool = False,
    common_dependency_version: str = "1.10.2",
    contract_version: str = VERSION,
) -> None:
    for artifact, component in ARTIFACT_COMPONENTS.items():
        _write_maven_publication(
            root,
            artifact,
            component,
            contract_version=contract_version,
            dependency_version=common_dependency_version if component == "common" else "1.10.2",
        )

    capabilities = list(CAPABILITIES)
    if mutate_capability:
        capabilities[0] = "capability-000-mutated"
    target_hashes = {
        kind: _raw_digest(kind.encode() + target_hash_salt)
        for kind in ("jvm-classes", "native", "wasm")
    }
    api = {
        "schema": 2,
        "libraryUniqueName": "io.github.codex-agent-labs:codex-agent-core",
        "markerAnnotation": "io.github.codex_agent_labs.codexagent.agent.CodexBindingApi",
        "signatureVersion": 2,
        "boundaryTypes": [],
        "memberExclusionAnnotation": (
            "io.github.codex_agent_labs.codexagent.agent.CodexBindingApiKotlinOnly"
        ),
        "excludedReachableTypes": [],
        "excludedMemberKeys": [],
        "dataClassMetadataAvailable": True,
        "dataClassNames": [],
        "owners": [{"name": "canonical-owner", "capabilities": capabilities}],
        "targets": [
            {"kind": kind, "sha256": target_hashes[kind]}
            for kind in sorted(target_hashes)
        ],
    }
    api_file = root / "evidence/canonical-api.json"
    write_canonical_json(api_file, api)

    coverage = {
        "schema": 2,
        "result": "passed",
        "kotlinCompilerVersion": "2.2.0",
        "canonicalTestTask": ":codex-agent-core:jvmTest",
        "apiReportSha256": sha256_file(api_file).removeprefix("sha256:"),
        "compiledTestsSha256": _raw_digest(b"compiled tests"),
        "testResultsSha256": _raw_digest(b"test results"),
        "capabilities": capabilities,
        "claims": [{"testId": "ContractCoverageTest#all", "capabilities": capabilities}],
    }
    coverage_file = root / "evidence/canonical-coverage.json"
    write_canonical_json(coverage_file, coverage)

    test_ids = [f"ContractScenarioTest#test{index:02d}" for index in range(14)]
    kotlin = {
        "schema": 4,
        "result": "passed",
        "phase": "M8",
        "language": "kotlin",
        "canonical": {
            "apiReportSha256": sha256_file(api_file).removeprefix("sha256:"),
            "coverageReceiptSha256": sha256_file(coverage_file).removeprefix("sha256:"),
        },
        "artifacts": [{"id": "kotlin-public-api", "sha256": target_hashes["jvm-classes"]}],
        "hostConsumerProofs": [],
        "testProgramSha256": _raw_digest(b"test program"),
        "testResultsSha256": _raw_digest(b"kotlin test results"),
        "publicSymbols": capabilities,
        "tests": [{"id": test_id, "status": "passed"} for test_id in test_ids],
        "scenarios": [
            {"id": scenario, "testIds": [test_ids[index]]}
            for index, scenario in enumerate(SCENARIOS)
        ],
        "claims": [],
        "exclusions": [],
    }
    write_canonical_json(root / "evidence/kotlin-parity.json", kotlin)

    protocol_files = {
        "evidence/codex_app_server_protocol.schemas.json": b'{"schema":1}\n',
        "evidence/codex_app_server_protocol.v2.schemas.json": b'{"schema":2}\n',
        "evidence/descriptors.json": b'{"descriptors":[]}\n',
        "evidence/provenance.json": b'{"source":"fixture"}\n',
    }
    for relative, contents in protocol_files.items():
        _write_file(root / relative, contents)
    write_canonical_json(
        root / "evidence/protocol-source-verification.json",
        {
            "schemaVersion": 1,
            "result": "passed",
            "schemaSha256": sha256_file(
                root / "evidence/codex_app_server_protocol.v2.schemas.json"
            ).removeprefix("sha256:"),
            "completeSchemaSha256": sha256_file(
                root / "evidence/codex_app_server_protocol.schemas.json"
            ).removeprefix("sha256:"),
            "descriptorSha256": sha256_file(
                root / "evidence/descriptors.json"
            ).removeprefix("sha256:"),
            "provenanceSha256": sha256_file(
                root / "evidence/provenance.json"
            ).removeprefix("sha256:"),
            "generatedOutputCount": 1,
        },
    )

    inventory = (
        f"tree\t{TREE}\n"
        "100644\tblob\t0123456789abcdef0123456789abcdef01234567\t"
        "codex-agent-core/src/commonMain/kotlin/Contract.kt\n"
    ).encode()
    _write_file(root / "inventories/contract-binary-inputs.git-tree", inventory)
    _write_file(root / "inventories/contract-validation-inputs.git-tree", inventory)


def _zip_entries(archive: Path) -> list[tuple[str, bytes, int]]:
    with zipfile.ZipFile(archive) as source:
        return [
            (entry.filename, source.read(entry), entry.external_attr)
            for entry in source.infolist()
        ]


def _write_zip(
    archive: Path,
    entries: list[tuple[str, bytes, int]],
    *,
    compression: int = zipfile.ZIP_STORED,
    timestamp: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0),
    comment: bytes = b"",
    create_version: int = 20,
    extract_version: int = 20,
    internal_attr: int = 0,
) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=compression) as output:
        output.comment = comment
        for name, contents, attributes in entries:
            info = zipfile.ZipInfo(name, timestamp)
            info.compress_type = compression
            info.create_system = 3
            info.create_version = create_version
            info.extract_version = extract_version
            info.external_attr = attributes
            info.internal_attr = internal_attr
            output.writestr(info, contents)


def _patch_first_zip_flags(archive: Path, flags: int) -> None:
    with zipfile.ZipFile(archive) as source:
        local_offset = source.infolist()[0].header_offset
        central_offset = source.start_dir
    contents = bytearray(archive.read_bytes())
    if contents[local_offset:local_offset + 4] != b"PK\x03\x04" or \
            contents[central_offset:central_offset + 4] != b"PK\x01\x02":
        raise AssertionError("test ZIP does not have the expected header layout")
    encoded = flags.to_bytes(2, "little")
    contents[local_offset + 6:local_offset + 8] = encoded
    contents[central_offset + 8:central_offset + 10] = encoded
    archive.write_bytes(contents)


def _patch_first_zip_volume(archive: Path, volume: int) -> None:
    with zipfile.ZipFile(archive) as source:
        central_offset = source.start_dir
    contents = bytearray(archive.read_bytes())
    if contents[central_offset:central_offset + 4] != b"PK\x01\x02":
        raise AssertionError("test ZIP does not have the expected central-directory header")
    contents[central_offset + 34:central_offset + 36] = volume.to_bytes(2, "little")
    archive.write_bytes(contents)


def _patch_first_zip_local_timestamp(archive: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        local_offset = source.infolist()[0].header_offset
    contents = bytearray(archive.read_bytes())
    if contents[local_offset:local_offset + 4] != b"PK\x03\x04":
        raise AssertionError("test ZIP does not have the expected local header")
    contents[local_offset + 10] ^= 1
    archive.write_bytes(contents)


def _insert_zip_central_directory_gap(archive: Path) -> None:
    with zipfile.ZipFile(archive) as source:
        central_offset = source.start_dir
    contents = bytearray(archive.read_bytes())
    eocd_offset = contents.rfind(b"PK\x05\x06")
    if eocd_offset < central_offset or contents[central_offset:central_offset + 4] != b"PK\x01\x02":
        raise AssertionError("test ZIP does not have the expected central directory")
    contents[central_offset:central_offset] = b"x"
    eocd_offset += 1
    contents[eocd_offset + 16:eocd_offset + 20] = (central_offset + 1).to_bytes(4, "little")
    archive.write_bytes(contents)


class ContractBundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("ssh-keygen") is None:
            raise unittest.SkipTest("ssh-keygen is required for Contract Bundle tests")
        cls._key_directory = tempfile.TemporaryDirectory(prefix="contract-bundle-key-")
        cls.private_key, cls.public_key, cls.signing = generate_development_key(
            Path(cls._key_directory.name).resolve()
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._key_directory.cleanup()

    def _build(
        self,
        root: Path,
        name: str,
        *,
        contract_version: str = VERSION,
        **staging_options,
    ) -> tuple[Path, Path, dict]:
        staging = root / f"{name}-staging"
        _write_staging(staging, contract_version=contract_version, **staging_options)
        archive = root / name / _archive_name(contract_version)
        manifest = build_contract_bundle(
            staging,
            archive,
            contract_version,
            PRODUCER,
            self.private_key,
            self.public_key,
            self.signing,
        )
        self.assertEqual(
            manifest,
            verify_contract_bundle(
                archive,
                self.public_key,
                expected_trust_domain="development",
            ),
        )
        return staging, archive, manifest

    def _resigned_archive(
        self,
        root: Path,
        name: str,
        entries: list[tuple[str, bytes, int]],
        updates: dict[str, bytes],
    ) -> Path:
        manifest = json.loads(next(contents for path, contents, _ in entries if path == "contract-manifest.json"))
        for path, contents in updates.items():
            record = next(
                value
                for value in manifest["evidenceFiles"] + manifest["mavenFiles"]
                if value["path"] == path
            )
            record["bytes"] = len(contents)
            record["sha256"] = sha256_bytes(contents)
        signing_directory = root / f"{name}-signing"
        manifest_path = signing_directory / "contract-manifest.json"
        write_canonical_json(manifest_path, manifest)
        signature_path = sign_manifest(manifest_path, self.private_key, self.signing)
        replacements = {
            **updates,
            "contract-manifest.json": manifest_path.read_bytes(),
            "contract-manifest.sig": signature_path.read_bytes(),
        }
        archive = root / name / ARCHIVE_NAME
        _write_zip(
            archive,
            [
                (path, replacements.get(path, contents), attributes)
                for path, contents, attributes in entries
            ],
        )
        return archive

    def test_development_build_keeps_only_public_verification_material(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            staging = root / "staging"
            _write_staging(staging)
            staging_before = regular_file_inventory(staging)
            with self.assertRaisesRegex(ValueError, "overlaps its staging input"):
                build_development_contract_bundle(staging, staging / "output", VERSION, PRODUCER)
            self.assertEqual(staging_before, regular_file_inventory(staging))
            output = root / "output"
            manifest = build_development_contract_bundle(staging, output, VERSION, PRODUCER)
            archive = output / ARCHIVE_NAME
            public_key = output / "development-ed25519.pub"
            self.assertTrue(archive.is_file())
            self.assertTrue(public_key.is_file())
            self.assertFalse(any(path.name == "development-ed25519" for path in root.rglob("*")))
            self.assertEqual(
                manifest,
                verify_contract_bundle(archive, public_key, expected_trust_domain="development"),
            )
            first_fingerprint = manifest["signing"]["fingerprint"]
            replaced = build_development_contract_bundle(staging, output, VERSION, PRODUCER)
            self.assertNotEqual(first_fingerprint, replaced["signing"]["fingerprint"])
            self.assertEqual(
                replaced,
                verify_contract_bundle(archive, public_key, expected_trust_domain="development"),
            )
            self.assertFalse(any(path.name == "development-ed25519" for path in root.rglob("*")))

    def test_development_build_verifies_pair_before_replacing_prior_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            staging = root / "staging"
            output = root / "output"
            _write_staging(staging)
            build_development_contract_bundle(staging, output, VERSION, PRODUCER)
            prior = regular_file_inventory(output)
            original_verify = contract_product.verify_contract_bundle

            def fail_prepublication_pair(archive, public_key, **arguments):
                if Path(archive).parent == Path(public_key).parent:
                    raise ValueError("simulated prepared-pair verification failure")
                return original_verify(archive, public_key, **arguments)

            with mock.patch.object(
                contract_product,
                "verify_contract_bundle",
                side_effect=fail_prepublication_pair,
            ):
                with self.assertRaisesRegex(ValueError, "prepared-pair verification failure"):
                    build_development_contract_bundle(staging, output, VERSION, PRODUCER)

            self.assertEqual(prior, regular_file_inventory(output))
            verify_contract_bundle(
                output / ARCHIVE_NAME,
                output / "development-ed25519.pub",
                expected_trust_domain="development",
            )
            self.assertFalse(any(path.name == "development-ed25519" for path in root.rglob("*")))

    def test_build_is_deterministic_and_component_closures_are_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, first_archive, first = self._build(root, "first")
            _, second_archive, second = self._build(root, "second")

            self.assertEqual(first, second)
            self.assertEqual(first_archive.read_bytes(), second_archive.read_bytes())
            closure = {
                component: sorted(
                    record["path"]
                    for record in first["mavenFiles"]
                    if record["component"] == component and (
                        record["role"] == "runtime-resolution" or
                        record["path"].endswith((".module", ".pom"))
                    )
                )
                for component in ARTIFACT_COMPONENTS.values()
            }
            self.assertEqual(set(ARTIFACT_COMPONENTS.values()), set(closure))
            self.assertEqual(12, len(closure))
            self.assertEqual(closure["common"], first["components"]["common"]["mavenPaths"])
            for component in sorted(set(ARTIFACT_COMPONENTS.values()) - {"common"}):
                self.assertEqual(
                    sorted(closure["common"] + closure[component]),
                    first["components"][component]["mavenPaths"],
                )

    def test_real_primary_inventory_is_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            staging, _, manifest = self._build(root, "valid")
            expected = {
                (
                    "maven/io/github/codex-agent-labs/"
                    f"{artifact}/{VERSION}/{artifact}-{VERSION}{suffix}"
                )
                for artifact, suffixes in PRIMARY_SUFFIXES.items()
                for suffix in suffixes
            }
            actual = {
                record["path"]
                for record in manifest["mavenFiles"]
                if record["role"] not in {"checksum", "signature"}
            }
            self.assertEqual(expected, actual)
            self.assertEqual(
                expected | {path + suffix for path in expected for suffix in CHECKSUM_ALGORITHMS},
                {record["path"] for record in manifest["mavenFiles"]},
            )
            self.assertIn(
                _maven_path(Path(), "codex-agent-core", "-kotlin-tooling-metadata.json").as_posix(),
                expected,
            )
            for artifact in (
                "codex-agent-core-iosarm64",
                "codex-agent-core-iossimulatorarm64",
                "codex-agent-core-macosarm64",
                "codex-agent-core-macosx64",
            ):
                self.assertIn(_maven_path(Path(), artifact, "-metadata.jar").as_posix(), expected)

            stale = root / "stale-staging"
            shutil.copytree(staging, stale)
            stale_tooling = _maven_path(
                stale,
                "codex-agent-core-android",
                "-kotlin-tooling-metadata.json",
            )
            write_canonical_json(
                stale_tooling,
                {"buildSystem": "Gradle", "buildSystemVersion": "8.14.3"},
            )
            _write_checksum_sidecars(stale_tooling)
            with self.assertRaises(ValueError):
                build_contract_bundle(
                    stale,
                    root / "stale" / ARCHIVE_NAME,
                    VERSION,
                    PRODUCER,
                    self.private_key,
                    self.public_key,
                    self.signing,
                )

            for index, relative in enumerate(sorted(expected)):
                incomplete = root / f"missing-{index:02d}-staging"
                shutil.copytree(staging, incomplete)
                _remove_primary(incomplete / relative)
                with self.subTest(path=relative), self.assertRaises(ValueError):
                    build_contract_bundle(
                        incomplete,
                        root / f"missing-{index:02d}" / ARCHIVE_NAME,
                        VERSION,
                        PRODUCER,
                        self.private_key,
                        self.public_key,
                        self.signing,
                    )

            missing_checksum = root / "missing-checksum-staging"
            shutil.copytree(staging, missing_checksum)
            checksum = Path(f"{missing_checksum / sorted(expected)[0]}.sha256")
            checksum.unlink()
            with self.assertRaises(ValueError):
                build_contract_bundle(
                    missing_checksum,
                    root / "missing-checksum" / ARCHIVE_NAME,
                    VERSION,
                    PRODUCER,
                    self.private_key,
                    self.public_key,
                    self.signing,
                )

    def test_unverified_maven_signatures_are_rejected_before_manifest_signing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            staging = root / "staging"
            _write_staging(staging)
            for artifact, suffixes in PRIMARY_SUFFIXES.items():
                for suffix in suffixes:
                    signature = Path(f"{_maven_path(staging, artifact, suffix)}.asc")
                    _write_file(signature, b"stale-or-forged-signature\n")
                    _write_checksum_sidecars(signature)

            with self.assertRaisesRegex(
                ValueError,
                "signatures are not accepted without PGP verification",
            ):
                build_contract_bundle(
                    staging,
                    root / "bundle" / ARCHIVE_NAME,
                    VERSION,
                    PRODUCER,
                    self.private_key,
                    self.public_key,
                    self.signing,
                )
            self.assertFalse((root / "bundle" / ARCHIVE_NAME).exists())

    def test_dependency_semantics_change_identity_but_self_version_does_not(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, _, baseline = self._build(root, "baseline")
            _, _, dependency = self._build(
                root,
                "dependency",
                common_dependency_version="1.10.3",
            )
            _, _, self_version = self._build(
                root,
                "self-version",
                contract_version="0.2.1",
            )

            self.assertNotEqual(
                baseline["components"]["common"]["sha256"],
                dependency["components"]["common"]["sha256"],
            )
            self.assertNotEqual(baseline["contractDigest"], dependency["contractDigest"])
            self.assertEqual(
                baseline["components"]["common"]["sha256"],
                self_version["components"]["common"]["sha256"],
            )
            self.assertEqual(baseline["contractDigest"], self_version["contractDigest"])

    def test_semantic_api_ignores_target_hashes_but_changes_for_capabilities(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, _, baseline = self._build(root, "baseline")
            _, _, target_hash = self._build(root, "target-hash", target_hash_salt=b"changed")
            _, _, capability = self._build(root, "capability", mutate_capability=True)

            self.assertEqual(baseline["canonicalApiDigest"], target_hash["canonicalApiDigest"])
            self.assertEqual(baseline["contractDigest"], target_hash["contractDigest"])
            self.assertNotEqual(
                baseline["canonicalCoverageDigest"],
                target_hash["canonicalCoverageDigest"],
            )
            self.assertNotEqual(baseline["canonicalApiDigest"], capability["canonicalApiDigest"])
            self.assertNotEqual(baseline["contractDigest"], capability["contractDigest"])

    def test_ancillary_files_do_not_change_components_but_resolution_files_do(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, _, baseline = self._build(root, "baseline")

            ancillary_stage = root / "ancillary-staging"
            _write_staging(ancillary_stage)
            for suffix, contents in (
                ("-sources.jar", b"new sources\n"),
                ("-javadoc.jar", b"new docs\n"),
            ):
                path = _maven_path(ancillary_stage, "codex-agent-core", suffix)
                _write_jar(path, contents)
                _write_checksum_sidecars(path)
            _refresh_module_files(ancillary_stage, "codex-agent-core")
            ancillary = build_contract_bundle(
                ancillary_stage,
                root / "ancillary" / ARCHIVE_NAME,
                VERSION,
                PRODUCER,
                self.private_key,
                self.public_key,
                self.signing,
            )
            self.assertEqual(baseline["components"], ancillary["components"])
            self.assertEqual(baseline["contractDigest"], ancillary["contractDigest"])

            target_stage = root / "target-staging"
            _write_staging(target_stage)
            target_path = _maven_path(target_stage, "codex-agent-core-jvm", ".jar")
            _write_jar(target_path, b"changed JVM\n")
            _write_checksum_sidecars(target_path)
            _refresh_module_files(target_stage, "codex-agent-core-jvm")
            target = build_contract_bundle(
                target_stage,
                root / "target" / ARCHIVE_NAME,
                VERSION,
                PRODUCER,
                self.private_key,
                self.public_key,
                self.signing,
            )
            for component in ARTIFACT_COMPONENTS.values():
                if component == "jvm":
                    self.assertNotEqual(baseline["components"][component], target["components"][component])
                else:
                    self.assertEqual(baseline["components"][component], target["components"][component])

            common_stage = root / "common-staging"
            _write_staging(common_stage)
            common_path = _maven_path(common_stage, "codex-agent-core", ".jar")
            _write_jar(common_path, b"changed common\n")
            _write_checksum_sidecars(common_path)
            _refresh_module_files(common_stage, "codex-agent-core")
            common = build_contract_bundle(
                common_stage,
                root / "common" / ARCHIVE_NAME,
                VERSION,
                PRODUCER,
                self.private_key,
                self.public_key,
                self.signing,
            )
            for component in ARTIFACT_COMPONENTS.values():
                self.assertNotEqual(baseline["components"][component], common["components"][component])

    def test_maven_version_role_component_and_publication_completeness_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, archive, _ = self._build(root, "valid")
            entries = _zip_entries(archive)
            manifest_bytes = next(contents for path, contents, _ in entries if path == "contract-manifest.json")
            manifest = json.loads(manifest_bytes)
            payload_index = next(
                index
                for index, record in enumerate(manifest["mavenFiles"])
                if record["component"] == "common" and record["role"] == "runtime-resolution"
            )
            for name, field, value in (
                ("wrong-role", "role", "sources"),
                ("wrong-component", "component", "jvm"),
            ):
                invalid = copy.deepcopy(manifest)
                invalid["mavenFiles"][payload_index][field] = value
                mutated = root / name / ARCHIVE_NAME
                _write_zip(
                    mutated,
                    [
                        (
                            path,
                            canonical_json_bytes(invalid) if path == "contract-manifest.json" else contents,
                            attributes,
                        )
                        for path, contents, attributes in entries
                    ],
                )
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "role or component"):
                    verify_contract_bundle(
                        mutated,
                        self.public_key,
                        expected_trust_domain="development",
                    )

            wrong_version = root / "wrong-version-staging"
            _write_staging(wrong_version)
            version_directory = (
                wrong_version
                / "maven/io/github/codex-agent-labs/codex-agent-core-jvm"
                / VERSION
            )
            version_directory.rename(version_directory.with_name("0.2.1"))
            with self.assertRaisesRegex(ValueError, "artifact or version"):
                build_contract_bundle(
                    wrong_version,
                    root / "wrong-version" / ARCHIVE_NAME,
                    VERSION,
                    PRODUCER,
                    self.private_key,
                    self.public_key,
                    self.signing,
                )

            for name, suffix in (("pom-self-version", ".pom"), ("module-self-version", ".module")):
                mismatched = root / f"{name}-staging"
                _write_staging(mismatched)
                metadata = _maven_path(mismatched, "codex-agent-core", suffix)
                if suffix == ".pom":
                    metadata.write_bytes(
                        metadata.read_bytes().replace(
                            b"<version>0.2.0</version>",
                            b"<version>0.2.1</version>",
                            1,
                        )
                    )
                else:
                    module = json.loads(metadata.read_bytes())
                    module["component"]["version"] = "0.2.1"
                    write_canonical_json(metadata, module)
                _write_checksum_sidecars(metadata)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    build_contract_bundle(
                        mismatched,
                        root / name / ARCHIVE_NAME,
                        VERSION,
                        PRODUCER,
                        self.private_key,
                        self.public_key,
                        self.signing,
                    )

            incomplete = root / "incomplete-staging"
            _write_staging(incomplete)
            _remove_primary(_maven_path(incomplete, "codex-agent-core-jvm", ".pom"))
            with self.assertRaises(ValueError):
                build_contract_bundle(
                    incomplete,
                    root / "incomplete" / ARCHIVE_NAME,
                    VERSION,
                    PRODUCER,
                    self.private_key,
                    self.public_key,
                    self.signing,
                )

    def test_maven_checksums_module_files_and_pom_resolution_semantics_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()

            bad_checksum = root / "bad-checksum-staging"
            _write_staging(bad_checksum)
            Path(f"{_maven_path(bad_checksum, 'codex-agent-core-jvm', '.jar')}.sha256").write_text(
                "0" * 64,
                encoding="ascii",
            )
            with self.assertRaisesRegex(ValueError, "checksum content mismatch"):
                build_contract_bundle(
                    bad_checksum,
                    root / "bad-checksum" / ARCHIVE_NAME,
                    VERSION,
                    PRODUCER,
                    self.private_key,
                    self.public_key,
                    self.signing,
                )

            stale_module = root / "stale-module-staging"
            _write_staging(stale_module)
            payload = _maven_path(stale_module, "codex-agent-core-jvm", ".jar")
            _write_jar(payload, b"changed without module evidence\n")
            _write_checksum_sidecars(payload)
            with self.assertRaisesRegex(ValueError, "size or digest"):
                build_contract_bundle(
                    stale_module,
                    root / "stale-module" / ARCHIVE_NAME,
                    VERSION,
                    PRODUCER,
                    self.private_key,
                    self.public_key,
                    self.signing,
                )

            incomplete_module = root / "incomplete-module-staging"
            _write_staging(incomplete_module)
            module_path = _maven_path(incomplete_module, "codex-agent-core-iosarm64", ".module")
            module = json.loads(module_path.read_bytes())
            module["variants"][0]["files"].pop()
            write_canonical_json(module_path, module)
            _write_checksum_sidecars(module_path)
            with self.assertRaisesRegex(ValueError, "does not reference its canonical payload"):
                build_contract_bundle(
                    incomplete_module,
                    root / "incomplete-module" / ARCHIVE_NAME,
                    VERSION,
                    PRODUCER,
                    self.private_key,
                    self.public_key,
                    self.signing,
                )

            for name, injected in (
                (
                    "pom-parent",
                    "<parent><groupId>example</groupId><artifactId>parent</artifactId>"
                    "<version>1.0.0</version></parent>",
                ),
                (
                    "pom-relocation",
                    "<distributionManagement><relocation><groupId>example</groupId>"
                    "<artifactId>replacement</artifactId><version>1.0.0</version>"
                    "</relocation></distributionManagement>",
                ),
            ):
                staging = root / f"{name}-staging"
                _write_staging(staging)
                pom_path = _maven_path(staging, "codex-agent-core", ".pom")
                pom_path.write_bytes(pom_path.read_bytes().replace(b"<modelVersion>", injected.encode() + b"<modelVersion>"))
                _write_checksum_sidecars(pom_path)
                with self.subTest(name=name), self.assertRaisesRegex(
                    ValueError,
                    "unsupported resolution semantics",
                ):
                    build_contract_bundle(
                        staging,
                        root / name / ARCHIVE_NAME,
                        VERSION,
                        PRODUCER,
                        self.private_key,
                        self.public_key,
                        self.signing,
                    )

    def test_archive_structure_metadata_size_evidence_and_signature_mutations_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, archive, _ = self._build(root, "valid")
            entries = _zip_entries(archive)

            for name, limits, message in (
                ("archive-bytes", {"max_archive_bytes": archive.stat().st_size - 1}, "too large"),
                ("central-bytes", {"max_central_directory_bytes": 1}, "central directory"),
                ("member-count", {"max_members": len(entries) - 1}, "too many members"),
                (
                    "entry-bytes",
                    {"max_entry_bytes": max(len(contents) for _, contents, _ in entries) - 1},
                    "member is too large",
                ),
                (
                    "total-bytes",
                    {"max_total_bytes": sum(len(contents) for _, contents, _ in entries) - 1},
                    "uncompressed size",
                ),
            ):
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                    verified_zip_contents(archive, **limits)
            compressed_ratio = root / "ratio.zip"
            _write_zip(
                compressed_ratio,
                [("payload", b"0" * 4096, CANONICAL_MODE)],
                compression=zipfile.ZIP_DEFLATED,
            )
            with self.assertRaisesRegex(ValueError, "compression ratio"):
                verified_zip_contents(compressed_ratio, max_compression_ratio=2)

            renamed = root / "renamed" / "renamed.zip"
            renamed.parent.mkdir(parents=True)
            shutil.copyfile(archive, renamed)
            with self.assertRaisesRegex(ValueError, "named codex-agent-contract"):
                verify_contract_bundle(
                    renamed,
                    self.public_key,
                    expected_trust_domain="development",
                )

            prefixed = root / "prefixed" / ARCHIVE_NAME
            prefixed.parent.mkdir(parents=True)
            prefixed.write_bytes(b"self-extracting-stub" + archive.read_bytes())
            with self.assertRaisesRegex(ValueError, "[Cc]anonical"):
                verify_contract_bundle(
                    prefixed,
                    self.public_key,
                    expected_trust_domain="development",
                )

            central_gap = root / "central-gap" / ARCHIVE_NAME
            central_gap.parent.mkdir(parents=True)
            shutil.copyfile(archive, central_gap)
            _insert_zip_central_directory_gap(central_gap)
            with self.assertRaisesRegex(ValueError, "[Cc]anonical"):
                verify_contract_bundle(
                    central_gap,
                    self.public_key,
                    expected_trust_domain="development",
                )

            local_header = root / "local-header" / ARCHIVE_NAME
            local_header.parent.mkdir(parents=True)
            shutil.copyfile(archive, local_header)
            _patch_first_zip_local_timestamp(local_header)
            with self.assertRaisesRegex(ValueError, "[Cc]anonical"):
                verify_contract_bundle(
                    local_header,
                    self.public_key,
                    expected_trust_domain="development",
                )

            missing_path = next(path for path, _, _ in entries if path.startswith("maven/"))
            structural = {
                "missing": [entry for entry in entries if entry[0] != missing_path],
                "extra": sorted(
                    entries + [("evidence/extra.json", b"{}\n", CANONICAL_MODE)],
                    key=lambda entry: entry[0],
                ),
                "reordered": list(reversed(entries)),
                "traversal": sorted(
                    entries + [("../escape", b"escape", CANONICAL_MODE)],
                    key=lambda entry: entry[0],
                ),
                "symlink": sorted(
                    entries + [("evidence/link", b"target", (stat.S_IFLNK | 0o777) << 16)],
                    key=lambda entry: entry[0],
                ),
                "duplicate": sorted(entries + [entries[0]], key=lambda entry: entry[0]),
            }
            for name, mutated_entries in structural.items():
                mutated = root / name / ARCHIVE_NAME
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    _write_zip(mutated, mutated_entries)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    verify_contract_bundle(
                        mutated,
                        self.public_key,
                        expected_trust_domain="development",
                    )

            for name, options in (
                ("compressed", {"compression": zipfile.ZIP_DEFLATED}),
                ("timestamp", {"timestamp": (1981, 1, 1, 0, 0, 0)}),
                ("comment", {"comment": b"not canonical"}),
                ("create-version", {"create_version": 99}),
                ("extract-version", {"extract_version": 21}),
                ("internal-attr", {"internal_attr": 1}),
            ):
                mutated = root / name / ARCHIVE_NAME
                _write_zip(mutated, entries, **options)
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "[Cc]anonical"):
                    verify_contract_bundle(
                        mutated,
                        self.public_key,
                        expected_trust_domain="development",
                    )

            flags_archive = root / "flag-bits" / ARCHIVE_NAME
            _write_zip(flags_archive, entries)
            _patch_first_zip_flags(flags_archive, 0x0800)
            with self.assertRaisesRegex(ValueError, "[Cc]anonical"):
                verify_contract_bundle(
                    flags_archive,
                    self.public_key,
                    expected_trust_domain="development",
                )

            volume_archive = root / "volume" / ARCHIVE_NAME
            _write_zip(volume_archive, entries)
            _patch_first_zip_volume(volume_archive, 1)
            with self.assertRaisesRegex(ValueError, "[Cc]anonical"):
                verify_contract_bundle(
                    volume_archive,
                    self.public_key,
                    expected_trust_domain="development",
                )

            extra_count = 4097 - len(entries)
            too_many = sorted(
                entries + [
                    (f"zz-extra/{index:04d}", b"x", CANONICAL_MODE)
                    for index in range(extra_count)
                ],
                key=lambda entry: entry[0],
            )
            too_many_archive = root / "too-many" / ARCHIVE_NAME
            _write_zip(too_many_archive, too_many)
            with self.assertRaisesRegex(ValueError, "too many members"):
                verify_contract_bundle(
                    too_many_archive,
                    self.public_key,
                    expected_trust_domain="development",
                )

            api_name = "evidence/canonical-api.json"
            api = json.loads(next(contents for path, contents, _ in entries if path == api_name))
            api["owners"][0]["capabilities"].pop()
            bad_api = self._resigned_archive(
                root,
                "api-count",
                entries,
                {api_name: canonical_json_bytes(api)},
            )
            with self.assertRaisesRegex(ValueError, "exactly 556"):
                verify_contract_bundle(
                    bad_api,
                    self.public_key,
                    expected_trust_domain="development",
                )

            descriptor = b'{"descriptors":["changed"]}\n'
            bad_evidence = self._resigned_archive(
                root,
                "evidence",
                entries,
                {"evidence/descriptors.json": descriptor},
            )
            with self.assertRaises(ValueError):
                verify_contract_bundle(
                    bad_evidence,
                    self.public_key,
                    expected_trust_domain="development",
                )

            signature = bytearray(
                next(contents for path, contents, _ in entries if path == "contract-manifest.sig")
            )
            body_positions = [
                index
                for index in range(signature.index(b"\n") + 1, signature.rindex(b"-----END"))
                if signature[index:index + 1].isalnum()
            ]
            position = body_positions[len(body_positions) // 2]
            signature[position] = ord("A") if signature[position] != ord("A") else ord("B")
            bad_signature = root / "signature" / ARCHIVE_NAME
            _write_zip(
                bad_signature,
                [
                    (
                        path,
                        bytes(signature) if path == "contract-manifest.sig" else contents,
                        attributes,
                    )
                    for path, contents, attributes in entries
                ],
            )
            with self.assertRaises(ValueError):
                verify_contract_bundle(
                    bad_signature,
                    self.public_key,
                    expected_trust_domain="development",
                )

            with self.assertRaises(ValueError):
                verify_contract_bundle(
                    archive,
                    self.public_key,
                    expected_trust_domain="release",
                )

    def test_existing_different_output_is_not_overwritten_and_failed_build_can_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, archive, _ = self._build(root, "published")
            original = archive.read_bytes()

            staging = root / "retry-staging"
            _write_staging(staging, mutate_capability=True)
            with self.assertRaisesRegex(ValueError, "already exists with different bytes"):
                build_contract_bundle(
                    staging,
                    archive,
                    VERSION,
                    PRODUCER,
                    self.private_key,
                    self.public_key,
                    self.signing,
                )
            self.assertEqual(original, archive.read_bytes())
            self.assertFalse((staging / "contract-manifest.json").exists())
            self.assertFalse((staging / "contract-manifest.sig").exists())
            self.assertFalse(list(archive.parent.glob(f".{ARCHIVE_NAME}-*")))

            retry = root / "retry" / ARCHIVE_NAME
            manifest = build_contract_bundle(
                staging,
                retry,
                VERSION,
                PRODUCER,
                self.private_key,
                self.public_key,
                self.signing,
            )
            self.assertEqual(
                manifest,
                verify_contract_bundle(
                    retry,
                    self.public_key,
                    expected_trust_domain="development",
                ),
            )

    def test_bundle_rejects_symlinked_output_ancestor_without_writing_through_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            staging = root / "staging"
            _write_staging(staging)
            external = root / "external"
            external.mkdir()
            _write_file(external / "must-survive", b"external\n")
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(external, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "output directory is unsafe"):
                build_contract_bundle(
                    staging,
                    linked_parent / ARCHIVE_NAME,
                    VERSION,
                    PRODUCER,
                    self.private_key,
                    self.public_key,
                    self.signing,
                )

            self.assertEqual(b"external\n", (external / "must-survive").read_bytes())
            self.assertFalse((external / ARCHIVE_NAME).exists())
            self.assertFalse((staging / "contract-manifest.json").exists())
            self.assertFalse((staging / "contract-manifest.sig").exists())

    def test_prepared_git_provenance_rejects_dirty_inputs_and_stale_inventories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repository = root / "repository"
            repository.mkdir()
            _git(repository, "init", "--quiet")
            _git(repository, "config", "user.name", "Contract Test")
            _git(repository, "config", "user.email", "contract@example.invalid")
            _write_file(
                repository / "ci/lanes/contract-product.production.pathspec",
                b"ci/lanes/contract-product.production.pathspec\ncontract/**\n",
            )
            _write_file(
                repository / "ci/lanes/contract-product.test.pathspec",
                b"ci/lanes/contract-product.test.pathspec\ntests/**\n",
            )
            _write_file(repository / ".gitignore", b"contract/ignored.kt\n")
            _write_file(repository / ".github/workflows/contract.yml", b"name: Contract fixture\n")
            _write_file(repository / "contract/Contract.kt", b"contract\n")
            _write_file(repository / "tests/ContractTest.kt", b"test\n")
            _git(repository, "add", ".")
            _git(repository, "commit", "--quiet", "-m", "fixture")
            commit = _git(repository, "rev-parse", "HEAD")
            tree = _git(repository, "rev-parse", "HEAD^{tree}")

            missing_workflow_output = root / "missing-workflow-output"
            with self.assertRaisesRegex(ValueError, "producer workflow does not exist"):
                prepare_contract_inputs(
                    repository,
                    missing_workflow_output,
                    "HEAD",
                    "codex-agent-labs/codex-agent",
                    ".github/workflows/missing.yml",
                    "pull_request",
                    6,
                    1,
                    31,
                )
            self.assertFalse(missing_workflow_output.exists())

            prepared = root / "prepared"
            forged = (
                f"tree\t{tree}\n"
                f"100644\tblob\t{'0' * 40}\tcontract/Forged.kt\n"
            ).encode()
            for name in (
                "contract-binary-inputs.git-tree",
                "contract-validation-inputs.git-tree",
            ):
                _write_file(prepared / "inventories" / name, forged)
            _write_file(prepared / "unexpected-stale-file", b"stale\n")
            producer = prepare_contract_inputs(
                repository,
                prepared,
                "HEAD",
                "codex-agent-labs/codex-agent",
                ".github/workflows/contract.yml",
                "pull_request",
                7,
                1,
                31,
            )
            self.assertEqual(commit, producer["commit"])
            self.assertEqual(tree, producer["tree"])
            verify_contract_git_inventories(prepared, producer)
            self.assertNotIn(b"contract/Forged.kt", (prepared / "inventories/contract-binary-inputs.git-tree").read_bytes())
            self.assertFalse((prepared / "unexpected-stale-file").exists())

            tracked_output = root / "tracked-output"
            (repository / "contract/Contract.kt").write_bytes(b"dirty tracked\n")
            with self.assertRaisesRegex(ValueError, "tracked:contract/Contract.kt"):
                prepare_contract_inputs(
                    repository,
                    tracked_output,
                    "HEAD",
                    "codex-agent-labs/codex-agent",
                    ".github/workflows/contract.yml",
                    "pull_request",
                    8,
                    1,
                    31,
                )
            self.assertFalse(tracked_output.exists())
            (repository / "contract/Contract.kt").write_bytes(b"contract\n")

            untracked_output = root / "untracked-output"
            _write_file(repository / "contract/Untracked.kt", b"untracked\n")
            with self.assertRaisesRegex(ValueError, "untracked:contract/Untracked.kt"):
                prepare_contract_inputs(
                    repository,
                    untracked_output,
                    "HEAD",
                    "codex-agent-labs/codex-agent",
                    ".github/workflows/contract.yml",
                    "pull_request",
                    9,
                    1,
                    31,
                )
            self.assertFalse(untracked_output.exists())
            (repository / "contract/Untracked.kt").unlink()

            ignored_output = root / "ignored-output"
            _write_file(repository / "contract/ignored.kt", b"ignored but build-visible\n")
            with self.assertRaisesRegex(ValueError, "untracked:contract/ignored.kt"):
                prepare_contract_inputs(
                    repository,
                    ignored_output,
                    "HEAD",
                    "codex-agent-labs/codex-agent",
                    ".github/workflows/contract.yml",
                    "pull_request",
                    10,
                    1,
                    31,
                )
            self.assertFalse(ignored_output.exists())
            (repository / "contract/ignored.kt").unlink()

            external = root / "external-output"
            external.mkdir()
            _write_file(external / "must-survive", b"external\n")
            symlink_output = root / "symlink-output"
            symlink_output.symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "output directory is unsafe"):
                prepare_contract_inputs(
                    repository,
                    symlink_output,
                    "HEAD",
                    "codex-agent-labs/codex-agent",
                    ".github/workflows/contract.yml",
                    "pull_request",
                    11,
                    1,
                    31,
                )
            self.assertEqual(b"external\n", (external / "must-survive").read_bytes())

            before_failure = {
                path.relative_to(prepared).as_posix(): path.read_bytes()
                for path in prepared.rglob("*")
                if path.is_file()
            }
            original_atomic_write = contract_product._atomic_write
            calls = 0

            def fail_second_inventory(path: Path, contents: bytes) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated inventory write failure")
                original_atomic_write(path, contents)

            with mock.patch.object(contract_product, "_atomic_write", side_effect=fail_second_inventory):
                with self.assertRaisesRegex(OSError, "simulated inventory write failure"):
                    prepare_contract_inputs(
                        repository,
                        prepared,
                        "HEAD",
                        "codex-agent-labs/codex-agent",
                        ".github/workflows/contract.yml",
                        "pull_request",
                        12,
                        1,
                        31,
                    )
            self.assertEqual(
                before_failure,
                {
                    path.relative_to(prepared).as_posix(): path.read_bytes()
                    for path in prepared.rglob("*")
                    if path.is_file()
                },
            )

            inventory_path = prepared / "inventories/contract-binary-inputs.git-tree"
            inventory_path.write_bytes(inventory_path.read_bytes().replace(tree.encode(), b"0" * 40, 1))
            with self.assertRaisesRegex(ValueError, "not bound to its producer tree"):
                verify_contract_git_inventories(prepared, producer)

    def test_prepared_git_provenance_uses_commit_bound_pathspec_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repository = root / "repository"
            repository.mkdir()
            _git(repository, "init", "--quiet")
            _git(repository, "config", "user.name", "Contract Test")
            _git(repository, "config", "user.email", "contract@example.invalid")
            _write_file(
                repository / "ci/lanes/contract-product.production.pathspec",
                b"ci/lanes/contract-product.production.pathspec\ncontract/**\n",
            )
            _write_file(
                repository / "ci/lanes/contract-product.test.pathspec",
                b"ci/lanes/contract-product.test.pathspec\ntests/**\n",
            )
            _write_file(repository / "contract/Contract.kt", b"contract\n")
            _write_file(repository / "tests/ContractTest.kt", b"test\n")
            _write_file(repository / "README.md", b"fixture\n")
            _write_file(
                repository / ".github/workflows/product-validation.yml",
                b"name: Contract fixture\n",
            )
            _git(repository, "add", ".")
            _git(repository, "commit", "--quiet", "-m", "fixture")

            (repository / "contract/Contract.kt").write_bytes(b"dirty contract\n")
            (repository / "ci/lanes/contract-product.production.pathspec").write_bytes(
                b"README.md\n",
            )
            output = root / "prepared"
            with self.assertRaisesRegex(
                ValueError,
                "tracked:(ci/lanes/contract-product.production.pathspec|contract/Contract.kt)",
            ):
                prepare_contract_inputs(
                    repository,
                    output,
                    "HEAD",
                    "codex-agent-labs/codex-agent",
                    ".github/workflows/product-validation.yml",
                    "pull_request",
                    13,
                    1,
                    31,
                )
            self.assertFalse(output.exists())

    def test_contract_product_pathspecs_are_exact_and_product_owned(self):
        repository = Path(__file__).resolve().parents[2]
        production = read_pathspecs(repository, "contract-product", "production")
        validation = read_pathspecs(repository, "contract-product", "test")
        self.assertEqual(tuple(sorted(set(production))), production)
        self.assertEqual(tuple(sorted(set(validation))), validation)

        def matched(path: str, specs: tuple[str, ...]) -> bool:
            return any(fnmatch.fnmatchcase(path, spec) for spec in specs)

        for path in (
            "gradle/release/versions/contract.txt",
            "gradle/build-logic/src/main/kotlin/ProductVersions.kt",
            "gradle/build-logic/src/main/kotlin/codexagent.root-release.gradle.kts",
            "codex-agent-core/src/commonMain/kotlin/Codex.kt",
            "ci/products/contract.py",
            "ci/products/contract_model.py",
        ):
            self.assertTrue(matched(path, production), path)
        for path in (
            "gradle/release/versions/runtime.txt",
            "gradle/release/versions/sdk.txt",
            "codex-agent-runtime-desktop/src/commonMain/kotlin/Runtime.kt",
            "codex-agent-runtime-android/src/main/kotlin/Runtime.kt",
            "codex-agent-sdk/src/commonMain/kotlin/Facade.kt",
            "ci/products/aggregate.py",
        ):
            self.assertFalse(matched(path, production), path)
        self.assertTrue(matched("ci/tests/test_contract_bundle.py", validation))
        self.assertFalse(matched("ci/tests/test_products.py", validation))
        self.assertFalse(matched("codex-agent-runtime-desktop/src/commonTest/kotlin/RuntimeTest.kt", validation))

    def test_contract_producer_import_closure_is_fully_inventoried_and_contract_only(self):
        repository = Path(__file__).resolve().parents[2]
        production = read_pathspecs(repository, "contract-product", "production")
        script = (
            "import pathlib,sys\n"
            "root=pathlib.Path.cwd().resolve()\n"
            "import ci.products.contract\n"
            "paths=[]\n"
            "for module in sys.modules.values():\n"
            " path=getattr(module,'__file__',None)\n"
            " if path:\n"
            "  resolved=pathlib.Path(path).resolve()\n"
            "  if resolved.is_relative_to(root / 'ci'):\n"
            "   paths.append(resolved.relative_to(root).as_posix())\n"
            "print('\\n'.join(sorted(set(paths))))\n"
        )
        imported = set(subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=repository,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines())
        self.assertEqual(
            {
                "ci/products/__init__.py",
                "ci/products/contract.py",
                "ci/products/contract_model.py",
                "ci/products/inventory.py",
                "ci/products/receipt.py",
                "ci/products/signatures.py",
            },
            imported,
        )
        self.assertTrue(all(
            any(fnmatch.fnmatchcase(path, spec) for spec in production)
            for path in imported
        ))
        self.assertNotIn("ci/products/aggregate.py", imported)


if __name__ == "__main__":
    unittest.main()
