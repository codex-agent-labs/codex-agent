from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci.products.sdk_maven import (
    COMPONENT_CARRIERS,
    COMPONENT_ARTIFACTS,
    COMPONENT_PRIMARY_SUFFIXES,
    KLIB_RESOURCE,
    MAVEN_GROUPS,
    RESOURCE,
    ROOT_ARTIFACTS,
    _inject_archive,
    _verify_archive,
    main,
    package_sdk_maven,
    verify_packaged_sdk_maven_phase,
    verify_packaged_sdk_maven_repository,
    verify_sdk_maven_repository,
)
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, snapshot_regular_tree,
)
from ci.products.receipt import compute_build_key, write_output_manifest, write_phase_receipt
from ci.products.registry import PhaseId, phase_targets
from ci.products.sdk_compatibility import load_sdk_compatibility_request
from ci.tests.test_products import phase_receipt, sdk_compatibility
from ci.tests.test_product_native_chain import build_chain
from ci.tests.test_product_sdk_inputs import _request


def _zip(path: Path, members: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, contents in sorted(members.items()):
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(entry, contents)


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, contents in sorted(members.items()):
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(entry, contents)
    return output.getvalue()


def _compatibility() -> bytes:
    return canonical_json_bytes(sdk_compatibility())


def _pom(group: str, artifact: str, version: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
        '  <modelVersion>4.0.0</modelVersion>\n'
        f'  <groupId>{group}</groupId>\n'
        f'  <artifactId>{artifact}</artifactId>\n'
        f'  <version>{version}</version>\n'
        '</project>\n'
    ).encode()


def _checksums(primary: Path) -> None:
    contents = primary.read_bytes()
    for suffix, algorithm in ((".md5", "md5"), (".sha1", "sha1"),
                              (".sha256", "sha256"), (".sha512", "sha512")):
        primary.with_name(primary.name + suffix).write_text(
            hashlib.new(algorithm, contents).hexdigest() + "\n", encoding="ascii",
        )


def _module(
    directory: Path,
    group: str,
    version: str,
    component: str,
    artifact: str,
) -> dict[str, object]:
    owner = artifact if artifact == "codex-agent-bom" else ROOT_ARTIFACTS[component]
    identity: dict[str, object] = {
        "group": group,
        "module": owner,
        "version": version,
        "attributes": {"org.gradle.status": "release"},
    }
    if owner != artifact:
        identity["url"] = f"../../{owner}/{version}/{owner}-{version}.module"
    variants: list[dict[str, object]] = []
    local_files = sorted(
        path for path in directory.iterdir()
        if path.is_file() and not path.name.endswith(
            (".module", ".pom", "-javadoc.jar", "-kotlin-tooling-metadata.json"),
        )
    )
    native_targets = {
        "codex-agent-iosarm64": "ios_arm64",
        "codex-agent-iossimulatorarm64": "ios_simulator_arm64",
        "codex-agent-linuxarm64": "linux_arm64",
        "codex-agent-linuxx64": "linux_x64",
        "codex-agent-macosarm64": "macos_arm64",
        "codex-agent-macosx64": "macos_x64",
        "codex-agent-mingwx64": "mingw_x64",
        "codex-agent-runtime-ios-iosarm64": "ios_arm64",
        "codex-agent-runtime-ios-iossimulatorarm64": "ios_simulator_arm64",
    }
    for index, primary in enumerate(local_files):
        contents = primary.read_bytes()
        attributes = {"org.gradle.category": "library"}
        if artifact in native_targets:
            attributes["org.jetbrains.kotlin.native.target"] = native_targets[artifact]
        variants.append({
            "name": f"published-{index}",
            "attributes": attributes,
            "files": [{
                "name": primary.name,
                "url": primary.name,
                "size": len(contents),
                **{
                    algorithm: hashlib.new(algorithm, contents).hexdigest()
                    for algorithm in ("md5", "sha1", "sha256", "sha512")
                },
            }],
        })
    if artifact == ROOT_ARTIFACTS[component]:
        targets = COMPONENT_ARTIFACTS[component] - {artifact, "codex-agent-bom"}
        for target in sorted(targets):
            variants.append({
                "name": f"{target}-published",
                "attributes": {"org.gradle.category": "library"},
                "available-at": {
                    "url": f"../../{target}/{version}/{target}-{version}.module",
                    "group": group,
                    "module": target,
                    "version": version,
                },
            })
    if not variants:
        variants.append({
            "name": "apiElements",
            "attributes": {"org.gradle.category": "platform"},
            "dependencyConstraints": [],
        })
    return {
        "formatVersion": "1.1",
        "component": identity,
        "createdBy": {"gradle": {"version": "9.4.1"}},
        "variants": variants,
    }


def _repository(root: Path, component: str, version: str = "0.2.0") -> Path:
    source = root / f"source-{component}"
    group_id = MAVEN_GROUPS[component]
    group = source.joinpath(*group_id.split("."))
    for artifact, suffixes in COMPONENT_PRIMARY_SUFFIXES[component].items():
        directory = group / artifact / version
        directory.mkdir(parents=True)
        for suffix in suffixes:
            primary = directory / f"{artifact}-{version}{suffix}"
            if suffix == ".pom":
                primary.write_bytes(_pom(group_id, artifact, version))
            elif suffix == ".module":
                continue
            elif suffix.endswith((".jar", ".aar", ".klib")):
                members = {"payload": f"{artifact}{suffix}".encode()}
                if suffix == ".aar":
                    classes = root / f"{artifact}-classes.jar"
                    _zip(classes, {"payload": artifact.encode()})
                    members = {"classes.jar": classes.read_bytes()}
                _zip(primary, members)
            else:
                primary.write_text("{}\n", encoding="utf-8")
        module = directory / f"{artifact}-{version}.module"
        module.write_text(
            json.dumps(_module(directory, group_id, version, component, artifact), indent=2) + "\n",
            encoding="utf-8",
        )
        for suffix in suffixes:
            _checksums(directory / f"{artifact}-{version}{suffix}")
    return source


def _refresh_module_file(source: Path, component: str, artifact: str, version: str, primary: Path) -> None:
    module = primary.parent / f"{artifact}-{version}.module"
    value = json.loads(module.read_text(encoding="utf-8"))
    contents = primary.read_bytes()
    for variant in value["variants"]:
        for record in variant.get("files", []):
            if record["url"] == primary.name:
                record.update({
                    "size": len(contents),
                    **{
                        algorithm: hashlib.new(algorithm, contents).hexdigest()
                        for algorithm in ("md5", "sha1", "sha256", "sha512")
                    },
                })
    module.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    _checksums(primary)
    _checksums(module)


class SdkMavenPackagingTest(unittest.TestCase):
    def test_every_component_packages_its_exact_carrier_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            version = "0.2.0"
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(_compatibility())
            for component, carriers in COMPONENT_CARRIERS.items():
                with self.subTest(component=component):
                    source = _repository(root, component, version)
                    output = root / f"output-{component}"
                    package_sdk_maven(
                        source, output, compatibility,
                        "io.github.codex-agent-labs", version, component,
                    )
                    before_verification = {
                        path.relative_to(output).as_posix(): path.read_bytes()
                        for path in output.rglob("*") if path.is_file()
                    }
                    verify_packaged_sdk_maven_repository(
                        output, compatibility,
                        "io.github.codex-agent-labs", version, component,
                    )
                    self.assertEqual(before_verification, {
                        path.relative_to(output).as_posix(): path.read_bytes()
                        for path in output.rglob("*") if path.is_file()
                    })
                    repeated = root / f"repeated-{component}"
                    package_sdk_maven(source, repeated, compatibility,
                                      "io.github.codex-agent-labs", version, component)
                    self.assertEqual(
                        {path.relative_to(output).as_posix(): path.read_bytes()
                         for path in output.rglob("*") if path.is_file()},
                        {path.relative_to(repeated).as_posix(): path.read_bytes()
                         for path in repeated.rglob("*") if path.is_file()},
                    )
                    for artifact, (kind, resource) in carriers.items():
                        packaged = output / "io/github/codex-agent-labs" / artifact / version / \
                            f"{artifact}-{version}.{kind}"
                        _verify_archive(packaged, kind, resource, compatibility.read_bytes())

                    wrong_version = sdk_compatibility()
                    wrong_version["sdkVersion"] = "0.2.1"
                    compatibility.write_bytes(canonical_json_bytes(wrong_version))
                    with self.assertRaisesRegex(ValueError, "version does not match"):
                        package_sdk_maven(
                            source, root / f"wrong-version-{component}", compatibility,
                            "io.github.codex-agent-labs", version, component,
                        )
                    compatibility.write_bytes(_compatibility())

    def test_final_verifier_binds_every_carrier_to_exact_compatibility_and_product_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            version = "0.2.0"
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(_compatibility())
            for component, carriers in COMPONENT_CARRIERS.items():
                with self.subTest(component=component, case="version"):
                    source = _repository(root / f"version-{component}", component, version)
                    packaged = root / f"packaged-version-{component}"
                    package_sdk_maven(
                        source, packaged, compatibility,
                        MAVEN_GROUPS[component], version, component,
                    )
                    with self.assertRaisesRegex(ValueError, "Maven product version"):
                        verify_packaged_sdk_maven_repository(
                            packaged, compatibility,
                            MAVEN_GROUPS[component], "0.2.1", component,
                        )

                for artifact, (kind, _resource) in carriers.items():
                    with self.subTest(component=component, artifact=artifact):
                        source = _repository(root / f"carrier-{component}-{artifact}", component, version)
                        packaged = root / f"packaged-{component}-{artifact}"
                        package_sdk_maven(
                            source, packaged, compatibility,
                            MAVEN_GROUPS[component], version, component,
                        )
                        archive = packaged.joinpath(
                            *MAVEN_GROUPS[component].split("."), artifact, version,
                            f"{artifact}-{version}.{kind}",
                        )
                        members = {"payload": b"rebound"}
                        if kind == "aar":
                            members = {"classes.jar": _zip_bytes({"payload": b"rebound"})}
                        _zip(archive, members)
                        _refresh_module_file(packaged, component, artifact, version, archive)
                        verify_sdk_maven_repository(
                            packaged, MAVEN_GROUPS[component], version, component,
                        )
                        with self.assertRaisesRegex(ValueError, "archive inventory mismatch"):
                            verify_packaged_sdk_maven_repository(
                                packaged, compatibility,
                                MAVEN_GROUPS[component], version, component,
                            )

            source = _repository(root / "wrong-bytes", "sdk-android", version)
            packaged = root / "packaged-wrong-bytes"
            package_sdk_maven(
                source, packaged, compatibility,
                MAVEN_GROUPS["sdk-android"], version, "sdk-android",
            )
            different = sdk_compatibility()
            different["runtime"]["defaultManifestSha256"] = "sha256:" + "f" * 64
            compatibility.write_bytes(canonical_json_bytes(different))
            with self.assertRaisesRegex(ValueError, "archive inventory mismatch"):
                verify_packaged_sdk_maven_repository(
                    packaged, compatibility,
                    MAVEN_GROUPS["sdk-android"], version, "sdk-android",
                )

            compatibility.write_bytes(_compatibility())
            wrong_name = root / "compatibility.json"
            wrong_name.write_bytes(compatibility.read_bytes())
            with self.assertRaisesRegex(ValueError, "wrong name"):
                verify_packaged_sdk_maven_repository(
                    packaged, wrong_name,
                    MAVEN_GROUPS["sdk-android"], version, "sdk-android",
                )

            compatibility.write_bytes(
                json.dumps(sdk_compatibility(), indent=2).encode("utf-8"),
            )
            with self.assertRaisesRegex(ValueError, "not canonical"):
                verify_packaged_sdk_maven_repository(
                    packaged, compatibility,
                    MAVEN_GROUPS["sdk-android"], version, "sdk-android",
                )

    def test_direct_archive_carriers_require_one_exact_resource(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            compatibility = _compatibility()
            for kind, resource in (("jar", RESOURCE), ("klib", KLIB_RESOURCE)):
                with self.subTest(kind=kind):
                    archive = root / f"carrier.{kind}"
                    _zip(archive, {"payload": b"binary"})
                    _inject_archive(archive, kind, resource, compatibility)
                    _verify_archive(archive, kind, resource, compatibility)

                    _zip(archive, {"wrong/sdk-compatibility.json": compatibility})
                    with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                        _verify_archive(archive, kind, resource, compatibility)

                    with zipfile.ZipFile(archive, "w") as output:
                        output.writestr(resource, compatibility)
                        output.writestr(resource, compatibility)
                    with self.assertRaisesRegex(ValueError, "duplicate"):
                        _verify_archive(archive, kind, resource, compatibility)

    def test_android_package_injects_nested_resource_and_refreshes_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            version = "0.2.0"
            artifact = "codex-agent-runtime-android"
            source = _repository(root, "sdk-android", version)
            directory = source / "io/github/codex-agent-labs" / artifact / version
            aar = directory / f"{artifact}-{version}.aar"
            module = directory / f"{artifact}-{version}.module"
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(_compatibility())

            output = root / "output"
            package_sdk_maven(
                source, output, compatibility, "io.github.codex-agent-labs", version, "sdk-android",
            )
            packaged = output / aar.relative_to(source)
            _verify_archive(packaged, "aar", RESOURCE, compatibility.read_bytes())
            metadata = json.loads((output / module.relative_to(source)).read_text(encoding="utf-8"))
            record = next(
                record
                for variant in metadata["variants"]
                for record in variant.get("files", [])
                if record["url"] == packaged.name
            )
            self.assertEqual(packaged.stat().st_size, record["size"])
            self.assertEqual(hashlib.sha256(packaged.read_bytes()).hexdigest(), record["sha256"])
            self.assertEqual(
                hashlib.sha256(packaged.read_bytes()).hexdigest(),
                packaged.with_name(packaged.name + ".sha256").read_text().strip(),
            )

            _zip(aar, {
                "classes.jar": _zip_bytes({"payload": b"class"}),
                RESOURCE: b"untrusted",
            })
            _refresh_module_file(source, "sdk-android", artifact, version, aar)
            with self.assertRaisesRegex(ValueError, "raw Android binary"):
                package_sdk_maven(
                    source, root / "outer-declaration", compatibility,
                    "io.github.codex-agent-labs", version, "sdk-android",
                )

    def test_raw_carrier_with_compatibility_and_incomplete_component_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            version = "0.2.0"
            artifact = "codex-agent-runtime-android"
            source = _repository(root, "sdk-android", version)
            directory = source / "io/github/codex-agent-labs" / artifact / version
            aar = directory / f"{artifact}-{version}.aar"
            _zip(aar, {"classes.jar": _zip_bytes({RESOURCE: b"untrusted"})})
            _refresh_module_file(source, "sdk-android", artifact, version, aar)
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(_compatibility())
            with self.assertRaisesRegex(ValueError, "raw Android binary"):
                package_sdk_maven(
                    source, root / "output", compatibility,
                    "io.github.codex-agent-labs", version, "sdk-android",
                )

            empty = root / "empty"
            empty.mkdir()
            with self.assertRaisesRegex(ValueError, "file inventory mismatch"):
                package_sdk_maven(
                    empty, root / "second-output", compatibility,
                    "io.github.codex-agent-labs", version, "sdk-core",
                )

    def test_component_carrier_contract_is_exact(self) -> None:
        self.assertEqual({"sdk-core", "sdk-android", "sdk-ios"}, set(COMPONENT_CARRIERS))
        self.assertEqual(12, len(COMPONENT_CARRIERS["sdk-core"]))
        self.assertEqual(1, len(COMPONENT_CARRIERS["sdk-android"]))
        self.assertEqual(3, len(COMPONENT_CARRIERS["sdk-ios"]))
        self.assertNotIn("codex-agent-runtime-desktop", {
            artifact for carriers in COMPONENT_CARRIERS.values() for artifact in carriers
        })
        self.assertEqual(
            set(COMPONENT_CARRIERS["sdk-core"]) | {"codex-agent-bom"},
            COMPONENT_ARTIFACTS["sdk-core"],
        )
        self.assertEqual(
            {"sdk-core": 67, "sdk-android": 5, "sdk-ios": 20},
            {
                component: sum(map(len, artifacts.values()))
                for component, artifacts in COMPONENT_PRIMARY_SUFFIXES.items()
            },
        )

    def test_read_only_verifier_accepts_real_authority_shaped_repositories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for component in COMPONENT_CARRIERS:
                with self.subTest(component=component):
                    source = _repository(root, component)
                    verify_sdk_maven_repository(
                        source, "io.github.codex-agent-labs", "0.2.0", component,
                    )

            source = root / "source-sdk-android"
            before = {
                path.relative_to(source).as_posix(): path.read_bytes()
                for path in source.rglob("*") if path.is_file()
            }
            self.assertEqual(0, main([
                "--verify-only",
                "--source", str(source),
                "--group-id", "io.github.codex-agent-labs",
                "--version", "0.2.0",
                "--component", "sdk-android",
            ]))
            self.assertEqual(before, {
                path.relative_to(source).as_posix(): path.read_bytes()
                for path in source.rglob("*") if path.is_file()
            })

    def test_inventory_group_version_metadata_and_checksums_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            base = _repository(root, "sdk-android")
            artifact = "codex-agent-runtime-android"
            version_dir = base / "io/github/codex-agent-labs" / artifact / "0.2.0"
            primary = version_dir / f"{artifact}-0.2.0.pom"

            with self.assertRaisesRegex(ValueError, "unexpected SDK Maven group"):
                verify_sdk_maven_repository(base, "evil.example", "0.2.0", "sdk-android")

            metadata = version_dir.parent / "maven-metadata.xml"
            metadata.write_text("<metadata/>\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "mutable discovery metadata"):
                verify_sdk_maven_repository(
                    base, "io.github.codex-agent-labs", "0.2.0", "sdk-android",
                )
            metadata.unlink()

            checksum = primary.with_name(primary.name + ".sha256")
            checksum.write_text(hashlib.sha256(primary.read_bytes()).hexdigest(), encoding="ascii")
            with self.assertRaisesRegex(ValueError, "noncanonical or mismatched"):
                verify_sdk_maven_repository(
                    base, "io.github.codex-agent-labs", "0.2.0", "sdk-android",
                )
            _checksums(primary)

            missing = primary.with_name(primary.name + ".sha512")
            missing.unlink()
            with self.assertRaisesRegex(ValueError, "file inventory mismatch"):
                verify_sdk_maven_repository(
                    base, "io.github.codex-agent-labs", "0.2.0", "sdk-android",
                )
            _checksums(primary)

            extra_version = version_dir.parent / "9.9.9"
            extra_version.mkdir()
            with self.assertRaisesRegex(ValueError, "version inventory mismatch"):
                verify_sdk_maven_repository(
                    base, "io.github.codex-agent-labs", "0.2.0", "sdk-android",
                )
            extra_version.rmdir()

            unknown = version_dir / "unknown.bin"
            unknown.write_bytes(b"unknown")
            with self.assertRaisesRegex(ValueError, "file inventory mismatch"):
                verify_sdk_maven_repository(
                    base, "io.github.codex-agent-labs", "0.2.0", "sdk-android",
                )

    def test_pom_gav_duplicates_and_unsafe_xml_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            artifact = "codex-agent-runtime-android"
            for name, contents, message in (
                ("wrong-group", _pom("evil.example", artifact, "0.2.0"), "groupId"),
                ("wrong-artifact", _pom("io.github.codex-agent-labs", "laundered", "0.2.0"), "artifactId"),
                ("wrong-version", _pom("io.github.codex-agent-labs", artifact, "9.9.9"), "version"),
                (
                    "duplicate-gav",
                    _pom("io.github.codex-agent-labs", artifact, "0.2.0").replace(
                        b"</project>", b"<groupId>io.github.codex-agent-labs</groupId></project>",
                    ),
                    "groupId",
                ),
                (
                    "doctype",
                    _pom("io.github.codex-agent-labs", artifact, "0.2.0").replace(
                        b"<project ", b"<!DOCTYPE project [<!ENTITY x 'x'>]><project ",
                    ),
                    "forbidden declaration",
                ),
                (
                    "relocation",
                    _pom("io.github.codex-agent-labs", artifact, "0.2.0").replace(
                        b"</project>",
                        b"<distributionManagement><relocation><version>9.9.9</version>"
                        b"</relocation></distributionManagement></project>",
                    ),
                    "unsupported resolution semantics",
                ),
                (
                    "utf16",
                    _pom("io.github.codex-agent-labs", artifact, "0.2.0").decode().encode("utf-16"),
                    "not UTF-8",
                ),
            ):
                with self.subTest(name=name):
                    source = _repository(root / name, "sdk-android")
                    pom = source / "io/github/codex-agent-labs" / artifact / "0.2.0" / \
                        f"{artifact}-0.2.0.pom"
                    pom.write_bytes(contents)
                    _checksums(pom)
                    with self.assertRaisesRegex(ValueError, message):
                        verify_sdk_maven_repository(
                            source, "io.github.codex-agent-labs", "0.2.0", "sdk-android",
                        )

    def test_module_owner_version_target_and_duplicate_json_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            artifact = "codex-agent-runtime-ios-iosarm64"
            for name, mutate, message in (
                (
                    "wrong-owner",
                    lambda value: value["component"].update(module=artifact),
                    "publication owner",
                ),
                (
                    "wrong-version",
                    lambda value: value["component"].update(version="9.9.9"),
                    "publication owner",
                ),
                (
                    "wrong-native-target",
                    lambda value: value["variants"][0]["attributes"].update(
                        {"org.jetbrains.kotlin.native.target": "linux_x64"},
                    ),
                    "native target",
                ),
                (
                    "created-by-build-id",
                    lambda value: value["createdBy"]["gradle"].update(buildId="run-specific"),
                    "unsupported execution identity",
                ),
            ):
                with self.subTest(name=name):
                    source = _repository(root / name, "sdk-ios")
                    module = source / "io/github/codex-agent-labs" / artifact / "0.2.0" / \
                        f"{artifact}-0.2.0.module"
                    value = json.loads(module.read_text(encoding="utf-8"))
                    mutate(value)
                    module.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
                    _checksums(module)
                    with self.assertRaisesRegex(ValueError, message):
                        verify_sdk_maven_repository(
                            source, "io.github.codex-agent-labs", "0.2.0", "sdk-ios",
                        )

            source = _repository(root / "wrong-reference", "sdk-ios")
            root_artifact = "codex-agent-runtime-ios"
            module = source / "io/github/codex-agent-labs" / root_artifact / "0.2.0" / \
                f"{root_artifact}-0.2.0.module"
            value = json.loads(module.read_text(encoding="utf-8"))
            reference = next(variant["available-at"] for variant in value["variants"] if "available-at" in variant)
            reference["version"] = "9.9.9"
            module.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            _checksums(module)
            with self.assertRaisesRegex(ValueError, "target reference has conflicting identity"):
                verify_sdk_maven_repository(
                    source, "io.github.codex-agent-labs", "0.2.0", "sdk-ios",
                )

            source = _repository(root / "duplicate-json", "sdk-android")
            artifact = "codex-agent-runtime-android"
            module = source / "io/github/codex-agent-labs" / artifact / "0.2.0" / \
                f"{artifact}-0.2.0.module"
            module.write_bytes(module.read_bytes().replace(
                b'"formatVersion": "1.1",', b'"formatVersion": "1.1",\n  "formatVersion": "1.1",',
            ))
            _checksums(module)
            with self.assertRaisesRegex(ValueError, "duplicate key"):
                verify_sdk_maven_repository(
                    source, "io.github.codex-agent-labs", "0.2.0", "sdk-android",
                )

    def test_archive_paths_and_module_ownership_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for name in ("bad\nname", "a//b", "a/./b"):
                archive = root / "bad.jar"
                with zipfile.ZipFile(archive, "w") as output:
                    output.writestr(name, b"payload")
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "unsafe"):
                    _verify_archive(archive, "jar", RESOURCE, b"compatibility")

            version = "0.2.0"
            artifact = "codex-agent-runtime-android"
            source = _repository(root, "sdk-android", version)
            directory = source / "io/github/codex-agent-labs" / artifact / version
            module = directory / f"{artifact}-{version}.module"
            value = json.loads(module.read_text(encoding="utf-8"))
            value["component"]["module"] = "wrong-owner"
            module.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            _checksums(module)
            compatibility = root / "sdk-compatibility.json"
            compatibility.write_bytes(_compatibility())
            with self.assertRaisesRegex(ValueError, "publication owner"):
                package_sdk_maven(
                    source, root / "output", compatibility,
                    "io.github.codex-agent-labs", version, "sdk-android",
                )


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class SdkMavenPhaseVerificationTest(unittest.TestCase):
    """Signed synthetic products prove semantics, not execution or admission."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-maven-phase-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chain = build_chain(cls.root / "synthetic-products", 61)
        cls.request = cls.root / "sdk-compatibility-request.json"
        cls.request.write_bytes(canonical_json_bytes(_request(cls.chain["compatibility_args"])))
        cls.stages = {}
        for component in COMPONENT_CARRIERS:
            stage = cls.root / component / "stage"
            compatibility = stage / "outputs/evidence/sdk-compatibility.json"
            compatibility.parent.mkdir(parents=True)
            compatibility.write_bytes(cls.chain["compatibility"].read_bytes())
            package_sdk_maven(
                _repository(cls.root / component, component, "0.2.9"),
                stage / "outputs/maven", compatibility,
                MAVEN_GROUPS[component], "0.2.9", component,
            )
            target, = phase_targets(PhaseId("sdk", component, "package"))
            write_output_manifest(
                stage, "sdk", component, "package", target, "0.2.9",
                {"maven": "outputs/maven", "evidence": "outputs/evidence"},
            )
            fixture = phase_receipt()
            inputs = fixture["inputs"]
            inputs["versionIdentity"] = "0.2.9"
            # Deliberately no planned upstream proof: this API verifies only
            # final-stage semantics and must never produce an admission token.
            receipt_root = cls.root / component / "receipt"
            receipt_root.mkdir()
            write_phase_receipt(
                stage, receipt_root, "sdk", component, "package", target, "0.2.9",
                compute_build_key(product="sdk", component=component, phase="package",
                                  target=target, inputs=inputs),
                inputs, cls.chain["context"]["producer"], "development",
            )
            cls.stages[component] = (stage, receipt_root / "phase-receipt.json")

    def _copy(self, root: Path, component: str = "sdk-android") -> tuple[Path, Path]:
        source, original = self.stages[component]
        stage = root / "stage"
        snapshot_regular_tree(source, stage)
        receipt = root / "phase-receipt.json"
        receipt.write_bytes(original.read_bytes())
        return stage, receipt

    def _rebind(self, stage: Path, receipt: Path, **identity) -> None:
        value = load_canonical_json_bytes(receipt.read_bytes())
        value.update(identity)
        value["inputs"]["versionIdentity"] = value["productVersion"]
        manifest = write_output_manifest(
            stage, value["product"], value["component"], value["phase"], value["target"],
            value["productVersion"], {"maven": "outputs/maven", "evidence": "outputs/evidence"},
        )
        value["outputs"] = manifest["outputs"]
        value["buildKey"] = compute_build_key(
            **{key: value[key] for key in ("product", "component", "phase", "target", "inputs")},
        )
        receipt.write_bytes(canonical_json_bytes(value))

    def test_every_maven_family_preserves_exact_original_stage_and_receipt(self) -> None:
        for component, (stage, receipt) in self.stages.items():
            with self.subTest(component=component):
                before = regular_file_inventory(stage)
                original = receipt.read_bytes()
                result, encoded = verify_packaged_sdk_maven_phase(stage, receipt, self.request)
                self.assertIs(type(result), dict)
                self.assertEqual(result, load_canonical_json_bytes(original))
                self.assertEqual(encoded, original)
                self.assertEqual(receipt.read_bytes(), original)
                self.assertEqual(regular_file_inventory(stage), before)

    def test_exact_registry_identity_and_stage_receipt_pairing(self) -> None:
        cases = (
            {"product": "runtime"}, {"component": "python"}, {"phase": "binary"},
            {"target": "common"}, {"productVersion": "0.2.10"},
        )
        for identity in cases:
            with self.subTest(identity=identity), tempfile.TemporaryDirectory() as temporary:
                stage, receipt = self._copy(Path(temporary).resolve())
                self._rebind(stage, receipt, **identity)
                with self.assertRaisesRegex(ValueError, "exact Maven package phase|compatibility version"):
                    verify_packaged_sdk_maven_phase(stage, receipt, self.request)
        with self.assertRaisesRegex(ValueError, "expected identity"):
            verify_packaged_sdk_maven_phase(
                self.stages["sdk-core"][0], self.stages["sdk-ios"][1], self.request,
            )

    def test_missing_extra_crosspaired_and_wrong_kind_outputs_fail(self) -> None:
        for case in ("missing", "extra", "rebound-extra", "wrong-kind", "crosspaired", "extra-evidence"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                stage, receipt = self._copy(Path(temporary).resolve())
                evidence = stage / "outputs/evidence/sdk-compatibility.json"
                if case == "missing":
                    evidence.unlink()
                elif case in {"extra", "rebound-extra", "extra-evidence"}:
                    directory = "evidence" if case == "extra-evidence" else "maven"
                    (stage / f"outputs/{directory}/extra.json").write_bytes(b"{}\n")
                    if case != "extra":
                        self._rebind(stage, receipt)
                else:
                    value = load_canonical_json_bytes(receipt.read_bytes())
                    value["outputs"][0]["kind"] = "binary"
                    receipt.write_bytes(canonical_json_bytes(value))
                    if case == "wrong-kind":
                        manifest_path = stage / "output-manifest.json"
                        manifest = load_canonical_json_bytes(manifest_path.read_bytes())
                        manifest["outputs"] = value["outputs"]
                        manifest_path.write_bytes(canonical_json_bytes(manifest))
                with self.assertRaises(ValueError):
                    verify_packaged_sdk_maven_phase(stage, receipt, self.request)

    def test_canonical_receipt_and_symbolic_inputs_fail(self) -> None:
        for case in ("noncanonical", "receipt-link", "stage-link"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                stage, receipt = self._copy(root)
                if case == "noncanonical":
                    receipt.write_text(json.dumps(json.loads(receipt.read_bytes()), indent=2))
                elif case == "receipt-link":
                    link = root / "receipt-link.json"
                    link.symlink_to(receipt)
                    receipt = link
                else:
                    link = stage / "outputs/evidence/extra-link.json"
                    link.symlink_to(stage / "outputs/evidence/sdk-compatibility.json")
                with self.assertRaises(ValueError):
                    verify_packaged_sdk_maven_phase(stage, receipt, self.request)

    def test_authentication_and_exact_compatibility_are_not_self_asserted(self) -> None:
        for case in ("crosspaired-request", "invalid-signature", "release-with-development-inputs"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                request = _request(self.chain["compatibility_args"])
                if case == "crosspaired-request":
                    request["compatibleReleaseRange"] = ">=0.2.0 <0.4.0"
                elif case == "invalid-signature":
                    signature = root / "invalid.sig"
                    signature.write_bytes(b"not an SSHSIG\n")
                    request["runtimeAttestationSignature"] = str(signature)
                else:
                    request["requiredTrustDomain"] = "release"
                request_path = root / "request.json"
                request_path.write_bytes(canonical_json_bytes(request))
                with self.assertRaises(ValueError):
                    verify_packaged_sdk_maven_phase(*self.stages["sdk-android"], request_path)

    def test_original_mutation_during_private_semantic_verification_is_rejected(self) -> None:
        for case in ("stage", "receipt", "request"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                stage, receipt = self._copy(root)
                request = root / "request.json"
                request.write_bytes(self.request.read_bytes())

                def verify_then_mutate(*args):
                    self.assertNotEqual(args[0], stage / "outputs/maven")
                    verify_packaged_sdk_maven_repository(*args)
                    changed = {"stage": stage / "outputs/evidence/sdk-compatibility.json",
                               "receipt": receipt, "request": request}[case]
                    changed.write_bytes(changed.read_bytes() + b"\n")

                with patch("ci.products.sdk_maven.verify_packaged_sdk_maven_repository",
                           side_effect=verify_then_mutate):
                    with self.assertRaisesRegex(ValueError, "inputs changed"):
                        verify_packaged_sdk_maven_phase(stage, receipt, request)

    def test_captured_request_controls_meaning_during_swap_and_restore(self) -> None:
        def relative(value):
            if isinstance(value, Path):
                return value.relative_to(self.root)
            if isinstance(value, dict):
                return {key: relative(member) for key, member in value.items()}
            return value

        request = self.root / "relative-request.json"
        original = canonical_json_bytes(_request(relative(self.chain["compatibility_args"])))
        request.write_bytes(original)

        def swap_then_decode(captured, *, request_directory):
            self.assertNotEqual(captured, request)
            self.assertEqual(captured.read_bytes(), original)
            self.assertEqual(request_directory, request.parent)
            changed = load_canonical_json_bytes(original)
            changed["sdkVersion"] = "0.2.10"
            request.write_bytes(canonical_json_bytes(changed))
            try:
                return load_sdk_compatibility_request(captured, request_directory=request_directory)
            finally:
                request.write_bytes(original)

        stage, receipt = self.stages["sdk-android"]
        with patch("ci.products.sdk_compatibility.load_sdk_compatibility_request",
                   side_effect=swap_then_decode):
            result, encoded = verify_packaged_sdk_maven_phase(stage, receipt, request)
        self.assertEqual(result["productVersion"], "0.2.9")
        self.assertEqual(encoded, receipt.read_bytes())
        self.assertEqual(request.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
