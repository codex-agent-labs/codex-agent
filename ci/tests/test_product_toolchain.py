from __future__ import annotations

import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import ci.products.runtime_identity as runtime_identity
from ci.products.inventory import canonical_json_bytes, sha256_bytes
from ci.products.receipt import compute_build_key
from ci.products.runtime_identity import derive_runtime_identity
from ci.products.toolchain import (
    PROFILE_SHAPES,
    PROFILE_TOOL_NAMES,
    assemble_profile,
    load_and_verify_toolchain_profile,
    load_toolchain_profile,
    load_toolchain_profile_bytes,
    observe_producer,
    validate_producer_observation,
    validate_verification_record,
    verify_capture,
    _supervisor_observation,
    _verification_record,
    verify_toolchain_profile,
)


FIXTURE_SHA = "sha256:" + "1" * 64


def identity(name: str, os_name: str, arch: str) -> str:
    value = tool_value(name, os_name, arch)
    return sha256_bytes(canonical_json_bytes({"name": name, "value": value}))


def producer(role: str, os_name: str, arch: str) -> dict[str, object]:
    profile_id = "linux-arm64" if role != "builder" else next(
        profile_id
        for profile_id, shapes in PROFILE_SHAPES.items()
        if shapes == ((role, os_name, arch),)
    )
    return {
        "role": role,
        "runner": {"os": os_name, "arch": arch},
        "tools": [
            {"name": name, "identity": identity(name, os_name, arch)}
            for name in PROFILE_TOOL_NAMES[(profile_id, role)]
        ],
    }


def profile(profile_id: str) -> dict[str, object]:
    return {
        "schemaVersion": 2,
        "id": profile_id,
        "producers": [producer(*shape) for shape in PROFILE_SHAPES[profile_id]],
    }


def observed_tools(value: dict[str, object], role: str) -> dict[str, str]:
    record = next(item for item in value["producers"] if item["role"] == role)
    return {item["name"]: item["identity"] for item in record["tools"]}


def tool_value(name: str, os_name: str, arch: str) -> dict[str, object]:
    return {
        "gradleWrapper": {
            "distributionSha256": FIXTURE_SHA, "launcherSha256": FIXTURE_SHA, "version": "9.4.1",
        },
        "javaRuntime": {
            "arch": arch.lower(), "binarySha256": FIXTURE_SHA,
            "runtimeVersion": "17.0.20+8", "vendor": "Eclipse Adoptium",
            "vendorVersion": "Temurin-17.0.20+8", "vmName": "OpenJDK VM", "vmVersion": "17.0.20+8",
        },
        "konanDependencies": {
            "entries": [{"name": "llvm", "treeSha256": FIXTURE_SHA}],
            "host": f"{os_name.lower()}_{arch.lower()}", "target": "fixture_target",
        },
        "kotlinNativeCompiler": {
            "archiveName": "kotlin-native.tar.gz", "archiveSha256": FIXTURE_SHA,
            "compilerFingerprint": "1" * 40, "compilerTreeSha256": FIXTURE_SHA,
            "compilerVersion": "2.3.10",
            "host": f"{os_name.lower()}_{arch.lower()}",
        },
        "kotlinPlugin": {
            "artifactName": "kotlin-gradle-plugin.jar", "artifactSha256": FIXTURE_SHA,
            "version": "2.3.10",
        },
        "supervisorCompiler": {
            "compilerBinarySha256": FIXTURE_SHA, "compilerVersion": "compiler 1",
            "family": "fixture", "linkerBinarySha256": FIXTURE_SHA,
            "linkerVersion": "linker 1", "platformBuild": "none",
            "platformVersion": "none", "target": f"{os_name}-{arch}",
        },
    }[name]


def observation(profile_id: str, role: str, os_name: str, arch: str) -> dict[str, object]:
    details = []
    for name in PROFILE_TOOL_NAMES[(profile_id, role)]:
        value = tool_value(name, os_name, arch)
        details.append({
            "identity": sha256_bytes(canonical_json_bytes({"name": name, "value": value})),
            "name": name,
            "value": value,
        })
    return {
        "imageProvenance": {"image": "fixture", "imageVersion": "fixture-1"},
        "producer": {
            "role": role,
            "runner": {"arch": arch, "os": os_name},
            "tools": [{"identity": item["identity"], "name": item["name"]} for item in details],
        },
        "profileId": profile_id,
        "repositoryRevision": "a" * 40,
        "repositoryTree": "b" * 40,
        "schemaVersion": 1,
        "toolObservations": details,
    }


class ProductToolchainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.profiles = self.root / "profiles"
        self.profiles.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(
        self,
        value: dict[str, object],
        name: str | None = None,
    ) -> tuple[Path, str]:
        contents = canonical_json_bytes(value)
        path = self.profiles / (name or f"{value['id']}.json")
        path.write_bytes(contents)
        return path, sha256_bytes(contents)

    def test_exact_five_target_topologies_load_and_each_producer_executes(self) -> None:
        for profile_id, shapes in PROFILE_SHAPES.items():
            value = profile(profile_id)
            _, digest = self.write(value)
            loaded = load_toolchain_profile(self.profiles, profile_id)
            self.assertEqual(
                shapes,
                tuple(
                    (item.role, item.runner_os, item.runner_arch)
                    for item in loaded.producers
                ),
            )
            for role, os_name, arch in shapes:
                calls = []
                with self.subTest(profile=profile_id, role=role):
                    self.assertEqual(
                        digest,
                        verify_toolchain_profile(
                            loaded,
                            digest,
                            role,
                            {"os": os_name, "arch": arch},
                            observed_tools(value, role),
                            executor=lambda: calls.append("executed"),
                        ),
                    )
                    self.assertEqual(["executed"], calls)

    def test_exact_canonical_bytes_bind_the_expected_profile_id(self) -> None:
        value = profile("linux-x64")
        contents = canonical_json_bytes(value)
        loaded = load_toolchain_profile_bytes(contents, "linux-x64")
        self.assertEqual(sha256_bytes(contents), loaded.digest)
        with self.assertRaisesRegex(ValueError, "does not match its authority"):
            load_toolchain_profile_bytes(contents, "macos-x64")

    def test_schema_rejects_wrong_keys_order_duplicates_and_topology(self) -> None:
        cases = []
        base = profile("linux-x64")
        missing = copy.deepcopy(base); missing.pop("id"); cases.append(missing)
        extra = copy.deepcopy(base); extra["imageVersion"] = "mutable"; cases.append(extra)
        old = copy.deepcopy(base); old["schemaVersion"] = 1; cases.append(old)
        producer_extra = copy.deepcopy(base); producer_extra["producers"][0]["extra"] = True; cases.append(producer_extra)
        runner_extra = copy.deepcopy(base); runner_extra["producers"][0]["runner"]["image"] = "mutable"; cases.append(runner_extra)
        tool_extra = copy.deepcopy(base); tool_extra["producers"][0]["tools"][0]["version"] = "9.4.1"; cases.append(tool_extra)
        reversed_tools = copy.deepcopy(base); reversed_tools["producers"][0]["tools"].reverse(); cases.append(reversed_tools)
        duplicate_tool = copy.deepcopy(base); duplicate_tool["producers"][0]["tools"].append(copy.deepcopy(duplicate_tool["producers"][0]["tools"][0])); duplicate_tool["producers"][0]["tools"].sort(key=lambda item: item["name"]); cases.append(duplicate_tool)
        unknown_tool = copy.deepcopy(base); unknown_tool["producers"][0]["tools"] = [{"name": "madeUpTool", "identity": "anything exact-looking"}]; cases.append(unknown_tool)
        wrong_runner_type = copy.deepcopy(base); wrong_runner_type["producers"][0]["runner"]["os"] = []; cases.append(wrong_runner_type)
        reversed_producers = profile("linux-arm64"); reversed_producers["producers"].reverse(); cases.append(reversed_producers)
        duplicate_producer = profile("linux-arm64"); duplicate_producer["producers"][1] = copy.deepcopy(duplicate_producer["producers"][0]); cases.append(duplicate_producer)
        wrong_topology = profile("linux-arm64"); wrong_topology["producers"] = wrong_topology["producers"][:1]; cases.append(wrong_topology)

        for index, value in enumerate(cases):
            with self.subTest(index=index):
                self.write(value, "linux-x64.json")
                with self.assertRaises(ValueError):
                    load_toolchain_profile(self.profiles, "linux-x64")

    def test_canonical_json_and_identity_strings_are_strict(self) -> None:
        value = profile("linux-x64")
        (self.profiles / "linux-x64.json").write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not canonical"):
            load_toolchain_profile(self.profiles, "linux-x64")

        (self.profiles / "linux-x64.json").write_bytes(
            b'{"id":"linux-x64","id":"linux-x64","producers":[],"schemaVersion":2}\n'
        )
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            load_toolchain_profile(self.profiles, "linux-x64")

        for identity in ("", " leading", "trailing ", "line\nbreak", "tab\tinside", "unicode\u2028line"):
            with self.subTest(identity=identity):
                malformed = profile("linux-x64")
                malformed["producers"][0]["tools"][0]["identity"] = identity
                self.write(malformed)
                with self.assertRaisesRegex(ValueError, "single-line identity"):
                    load_toolchain_profile(self.profiles, "linux-x64")

    def test_same_semver_identity_detail_mutation_fails_before_executor(self) -> None:
        value = profile("linux-arm64")
        _, digest = self.write(value)
        loaded = load_toolchain_profile(self.profiles, "linux-arm64")
        tools = observed_tools(value, "cross-builder")
        tools["kotlinNativeCompiler"] = "sha256:" + "2" * 64
        calls = []

        with self.assertRaisesRegex(ValueError, "identities do not match"):
            verify_toolchain_profile(
                loaded,
                digest,
                "cross-builder",
                {"os": "Linux", "arch": "X64"},
                tools,
                executor=lambda: calls.append("executed"),
            )
        self.assertEqual([], calls)

    def test_role_runner_tool_and_digest_failures_precede_executor(self) -> None:
        value = profile("linux-x64")
        _, digest = self.write(value)
        loaded = load_toolchain_profile(self.profiles, "linux-x64")
        runner = {"os": "Linux", "arch": "X64"}
        tools = observed_tools(value, "builder")
        invalid = (
            ("sha256:" + "0" * 64, "builder", runner, tools),
            (digest, "cross-builder", runner, tools),
            (digest, "builder", {"os": "Linux", "arch": "ARM64"}, tools),
            (digest, "builder", {"os": "Windows", "arch": "X64"}, tools),
            (digest, "builder", runner, {name: identity for name, identity in tools.items() if name != "gradleWrapper"}),
            (digest, "builder", runner, {**tools, "node": "Node 24.0.0"}),
        )
        for expected, role, actual_runner, actual_tools in invalid:
            calls = []
            with self.subTest(role=role, runner=actual_runner, tools=actual_tools):
                with self.assertRaises(ValueError):
                    verify_toolchain_profile(
                        loaded,
                        expected,
                        role,
                        actual_runner,
                        actual_tools,
                        executor=lambda: calls.append("executed"),
                    )
                self.assertEqual([], calls)

    def test_profile_is_revalidated_from_canonical_bytes_before_executor(self) -> None:
        value = profile("linux-x64")
        _, digest = self.write(value)
        loaded = load_toolchain_profile(self.profiles, "linux-x64")
        tampered = replace(loaded, id="macos-x64")
        calls = []

        with self.assertRaisesRegex(ValueError, "canonical bytes"):
            verify_toolchain_profile(
                tampered,
                digest,
                "builder",
                {"os": "Linux", "arch": "X64"},
                observed_tools(value, "builder"),
                executor=lambda: calls.append("executed"),
            )
        self.assertEqual([], calls)

    def test_mutable_image_provenance_never_changes_profile_digest(self) -> None:
        value = profile("linux-x64")
        _, digest = self.write(value)
        loaded = load_toolchain_profile(self.profiles, "linux-x64")
        calls = []
        for image_version in ("ubuntu-24.04@20260801.1", "ubuntu-24.04@20260829.7"):
            self.assertEqual(
                digest,
                verify_toolchain_profile(
                    loaded,
                    digest,
                    "builder",
                    {"os": "Linux", "arch": "X64"},
                    observed_tools(value, "builder"),
                    image_provenance={"imageVersion": image_version},
                    executor=lambda: calls.append("executed"),
                ),
            )
        self.assertEqual(["executed", "executed"], calls)
        self.assertEqual(digest, loaded.digest)
        self.assertNotIn("image", loaded._canonical.decode())

    def test_load_and_verify_selects_exact_profile_filename(self) -> None:
        value = profile("windows-x64")
        _, digest = self.write(value)
        self.assertEqual(
            digest,
            load_and_verify_toolchain_profile(
                self.profiles,
                "windows-x64",
                digest,
                "builder",
                {"os": "Windows", "arch": "X64"},
                observed_tools(value, "builder"),
            ),
        )
        mismatched = profile("linux-x64")
        self.write(mismatched, "windows-x64.json")
        with self.assertRaisesRegex(ValueError, "file name"):
            load_toolchain_profile(self.profiles, "windows-x64")

    def test_observer_hashes_all_exact_tool_objects_without_product_compilation(self) -> None:
        gradle_home = self.root / "gradle-home"
        konan_home = self.root / "konan-home"
        kgp = gradle_home / "caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-gradle-plugin/2.3.10/x/kotlin-gradle-plugin-2.3.10-gradle813.jar"
        sources = kgp.with_name("kotlin-gradle-plugin-2.3.10-gradle813-sources.jar")
        common_sources = kgp.with_name("kotlin-gradle-plugin-2.3.10-sources.jar")
        javadoc = kgp.with_name("kotlin-gradle-plugin-2.3.10-gradle813-javadoc.jar")
        archive = gradle_home / "caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-native-prebuilt/2.3.10/x/kotlin-native-prebuilt-2.3.10-linux-x86_64.tar.gz"
        compiler = konan_home / "kotlin-native-prebuilt-linux-x86_64-2.3.10"
        cc, ld, java = self.root / "tools/cc", self.root / "tools/ld", self.root / "tools/java"
        for path, contents in (
            (kgp, b"kgp"), (sources, b"sources"), (common_sources, b"common sources"), (javadoc, b"javadoc"),
            (archive, b"native"), (cc, b"cc"), (ld, b"ld"), (java, b"java"),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        (compiler / "bin").mkdir(parents=True)
        (compiler / "bin/konanc").write_bytes(b"konanc")
        (compiler / "konan").mkdir()
        (compiler / "konan/compiler.fingerprint").write_text("1" * 40, encoding="ascii")
        (compiler / "konan/konan.properties").write_text(
            "llvmHome.linux_x64=$llvm.linux_x64.dev\n"
            "llvm.linux_x64.dev=llvm-1\n"
            "libffiDir.linux_x64=libffi-1\n"
            "dependencies.linux_x64=toolchain-1 lldb-1\n",
            encoding="utf-8",
        )
        for name in ("llvm-1", "libffi-1", "toolchain-1", "lldb-1"):
            path = konan_home / "dependencies" / name / "payload"
            path.parent.mkdir(parents=True)
            path.write_bytes(name.encode())
        kgp_sha = sha256_bytes(b"kgp").removeprefix("sha256:")
        archive_sha = sha256_bytes(b"native").removeprefix("sha256:")
        authorities = {
            "gradle/wrapper/gradle-wrapper.properties": (
                b"distributionUrl=https\\://services.gradle.org/distributions/gradle-9.4.1-bin.zip\n"
                b"distributionSha256Sum=" + (b"1" * 64) + b"\n"
            ),
            "gradlew": b"#!/bin/sh\n",
            "gradle/libs.versions.toml": b'[versions]\nkotlin = "2.3.10"\n',
            "runtime/gradle/verification-metadata.xml": (
                '<verification-metadata><components><component>'
                f'<artifact name="{kgp.name}"><sha256 value="{kgp_sha}"/></artifact>'
                f'<artifact name="{archive.name}"><sha256 value="{archive_sha}"/></artifact>'
                '</component></components></verification-metadata>'
            ).encode(),
        }
        commands = []

        def execute(command: tuple[str, ...], root: Path) -> str:
            commands.append(command)
            if command[0].endswith("gradlew"):
                return "Gradle 9.4.1\n"
            if command[0] == str(java):
                return (
                    " java.runtime.version = 17.0.20+8\n java.vendor = Eclipse Adoptium\n"
                    " java.vendor.version = Temurin-17.0.20+8\n java.vm.name = OpenJDK VM\n"
                    " java.vm.version = 17.0.20+8\n os.arch = amd64\n"
                )
            if command[0].endswith("konanc"):
                return "Kotlin/Native: 2.3.10\n"
            if command[0] == str(cc):
                return {"--version": "gcc 14.1", "-dumpmachine": "x86_64-linux-gnu", "-print-prog-name=ld": str(ld)}[command[1]]
            if command[0] == str(ld):
                return "GNU ld 2.42"
            raise AssertionError(command)

        with mock.patch("ci.products.toolchain._authority", side_effect=lambda _, __, path: authorities[path]), \
                mock.patch("ci.products.toolchain.run_git", return_value="b" * 40 + "\n"):
            result = observe_producer(
                self.root, "a" * 40, "linux-x64", "builder", "linux-x64",
                gradle_user_home=gradle_home,
                konan_data_dir=konan_home,
                environment={"RUNNER_OS": "Linux", "RUNNER_ARCH": "X64"},
                execute=execute,
                find_executable=lambda name: {
                    "cc": str(cc), "java": str(java), "ld": str(ld),
                }.get(name),
            )
        validated = validate_producer_observation(result)
        self.assertEqual(PROFILE_TOOL_NAMES[("linux-x64", "builder")], tuple(
            item["name"] for item in validated["toolObservations"]
        ))
        self.assertTrue(all(item["identity"].startswith("sha256:") for item in validated["toolObservations"]))
        self.assertEqual({
            "--no-daemon", "--version", "-XshowSettings:properties", "-dumpmachine",
            "-print-prog-name=ld", "-version",
        }, {
            argument for command in commands for argument in command[1:] if argument.startswith("-")
        })
        self.assertIn((str(ld), "--version"), commands)
        self.assertFalse(any("compile" in " ".join(command).lower() for command in commands))

    def test_macos_supervisor_observer_uses_apple_linker_version_option(self) -> None:
        cc, ld = self.root / "tools/cc", self.root / "tools/ld"
        for path in (cc, ld):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(path.name.encode())
        commands = []

        def execute(command: tuple[str, ...], root: Path) -> str:
            commands.append(command)
            if command[0] == str(cc):
                return {
                    "--version": "Apple clang 21.0.0", "-dumpmachine": "arm64-apple-darwin25.6.0",
                    "-print-prog-name=ld": str(ld),
                }[command[1]]
            if command == (str(ld), "-v"):
                return "@(#)PROGRAM:ld PROJECT:ld-1267"
            if command == ("xcodebuild", "-version"):
                return "Xcode 26.6\nBuild version 17F113"
            if command[:3] == ("xcrun", "--sdk", "macosx"):
                return {"--show-sdk-version": "26.5", "--show-sdk-build-version": "25F70"}[command[3]]
            raise AssertionError(command)

        result = _supervisor_observation(
            self.root, "macOS", "cc", {}, execute,
            lambda name: {"cc": str(cc), "ld": str(ld)}.get(name),
        )
        self.assertEqual("@(#)PROGRAM:ld PROJECT:ld-1267", result["linkerVersion"])
        self.assertIn((str(ld), "-v"), commands)
        self.assertNotIn((str(ld), "--version"), commands)

    def test_observer_rejects_unpinned_native_archive_before_invoking_konanc(self) -> None:
        with self.assertRaisesRegex(ValueError, "metadata lacks one exact checksum"):
            from ci.products.toolchain import _metadata_checksum
            _metadata_checksum(b"<verification-metadata/>", "kotlin-native-prebuilt.tar.gz")

    def test_linux_arm64_supervisor_observer_needs_no_kotlin_cache(self) -> None:
        java, cc, ld = self.root / "tools/java", self.root / "tools/cc", self.root / "tools/ld"
        for path in (java, cc, ld):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(path.name.encode())
        authorities = {
            "gradle/wrapper/gradle-wrapper.properties": (
                b"distributionUrl=https\\://services.gradle.org/distributions/gradle-9.4.1-bin.zip\n"
                b"distributionSha256Sum=" + (b"1" * 64) + b"\n"
            ),
            "gradlew": b"#!/bin/sh\n",
        }

        def execute(command: tuple[str, ...], root: Path) -> str:
            if command[0].endswith("gradlew"):
                return "Gradle 9.4.1\n"
            if command[0] == str(java):
                return (
                    " java.runtime.version = 17.0.20+8\n java.vendor = Eclipse Adoptium\n"
                    " java.vendor.version = Temurin-17.0.20+8\n java.vm.name = OpenJDK VM\n"
                    " java.vm.version = 17.0.20+8\n os.arch = aarch64\n"
                )
            if command[0] == str(cc):
                return {
                    "--version": "gcc 14.1", "-dumpmachine": "aarch64-linux-gnu",
                    "-print-prog-name=ld": str(ld),
                }[command[1]]
            if command[0] == str(ld):
                return "GNU ld 2.42"
            raise AssertionError(command)

        with mock.patch(
            "ci.products.toolchain._authority", side_effect=lambda _, __, path: authorities[path]
        ), mock.patch("ci.products.toolchain.run_git", return_value="b" * 40 + "\n"):
            result = observe_producer(
                self.root, "a" * 40, "linux-arm64", "supervisor-builder", "linux-arm64",
                environment={"RUNNER_OS": "Linux", "RUNNER_ARCH": "ARM64"},
                execute=execute,
                find_executable=lambda name: {"cc": str(cc), "java": str(java), "ld": str(ld)}.get(name),
            )
        self.assertEqual(
            ("gradleWrapper", "javaRuntime", "supervisorCompiler"),
            tuple(item["name"] for item in result["toolObservations"]),
        )

    def test_linux_arm64_assembly_requires_both_exact_producers(self) -> None:
        cross = observation("linux-arm64", "cross-builder", "Linux", "X64")
        supervisor = observation("linux-arm64", "supervisor-builder", "Linux", "ARM64")
        value = assemble_profile([supervisor, cross], "linux-arm64")
        self.assertEqual(["cross-builder", "supervisor-builder"], [item["role"] for item in value["producers"]])
        with self.assertRaisesRegex(ValueError, "topology"):
            assemble_profile([cross], "linux-arm64")
        changed = copy.deepcopy(supervisor)
        changed["repositoryTree"] = "c" * 40
        with self.assertRaisesRegex(ValueError, "one exact repository"):
            assemble_profile([cross, changed], "linux-arm64")

    def test_direct_module_cli_assembles_canonical_profile_and_removes_stale_failure(self) -> None:
        observed = observation("linux-x64", "builder", "Linux", "X64")
        producer_path = self.root / "builder.json"
        producer_path.write_bytes(canonical_json_bytes(observed))
        output = self.root / "linux-x64.json"
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        command = [
            sys.executable, "-m", "ci.products.toolchain", "assemble-profile",
            "--profile-id", "linux-x64", "--producer", str(producer_path),
            "--output", str(output),
        ]
        result = subprocess.run(
            command, cwd=Path(__file__).resolve().parents[2], env=environment,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(canonical_json_bytes(assemble_profile([observed], "linux-x64")), output.read_bytes())
        producer_path.write_text('{"stale":true}\n', encoding="utf-8")
        result = subprocess.run(
            command, cwd=Path(__file__).resolve().parents[2], env=environment,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(output.exists())

    def test_capture_requires_exact_five_profile_six_observation_inventory(self) -> None:
        capture = self.root / "capture"
        for profile_id, shapes in PROFILE_SHAPES.items():
            records = [observation(profile_id, *shape) for shape in shapes]
            for record in records:
                path = capture / "observations" / profile_id / f"{record['producer']['role']}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(canonical_json_bytes(record))
            path = capture / "profiles" / f"{profile_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(canonical_json_bytes(assemble_profile(records, profile_id)))
        verify_capture(capture, "a" * 40, "b" * 40)
        (capture / "extra.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inventory"):
            verify_capture(capture, "a" * 40, "b" * 40)

    def test_verification_record_binds_exact_git_profile_and_binary_plan(self) -> None:
        repository = self.root / "repository"
        profile_value = assemble_profile([
            observation("linux-x64", "builder", "Linux", "X64")
        ], "linux-x64")
        profile_path = repository / "gradle/release/toolchains/runtime/linux-x64.json"
        profile_path.parent.mkdir(parents=True)
        profile_path.write_bytes(canonical_json_bytes(profile_value))
        subprocess.run(["git", "init", "-q", repository], check=True)
        subprocess.run(["git", "-C", repository, "add", "."], check=True)
        subprocess.run(
            ["git", "-C", repository, "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-qm", "fixture"],
            check=True,
        )
        revision = subprocess.check_output(["git", "-C", repository, "rev-parse", "HEAD"], text=True).strip()
        tree = subprocess.check_output(["git", "-C", repository, "rev-parse", "HEAD^{tree}"], text=True).strip()
        observed = observation("linux-x64", "builder", "Linux", "X64")
        observed["repositoryRevision"], observed["repositoryTree"] = revision, tree
        profile_digest = sha256_bytes(canonical_json_bytes(profile_value))
        inputs = {
            "inventory": [], "phaseInputDigest": sha256_bytes(canonical_json_bytes([])),
            "versionIdentity": "0.2.0", "upstreamArtifacts": [],
            "toolchainProfileDigest": profile_digest, "flagsDigest": FIXTURE_SHA,
            "outputSchemaVersion": 1,
        }
        plan = {
            "buildKey": compute_build_key(
                product="runtime", component="linux-x64", phase="binary", target="linux-x64", inputs=inputs,
            ),
            "component": "linux-x64", "inputs": inputs, "phase": "binary", "product": "runtime",
            "runtimeBinaryIdentity": derive_runtime_identity({
                "schemaVersion": 1,
                "binaryBuildKey": compute_build_key(
                    product="runtime", component="linux-x64", phase="binary",
                    target="linux-x64", inputs=inputs,
                ),
                "runtimeCompatibilityVersion": "0.2.0",
                "target": "linux-x64",
                "contract": {"digest": FIXTURE_SHA, "componentDigest": FIXTURE_SHA},
                "cAbi": {
                    "version": "1.13.0", "minimumCompatibleVersion": "1.0.0",
                    "identitySchemaVersion": 1, "headerSha256": FIXTURE_SHA,
                    "symbolSetSha256": FIXTURE_SHA, "symbolCount": 778,
                },
                "appServer": {
                    "version": "0.149.0", "releaseTag": "rust-v0.149.0",
                    "binarySha256": FIXTURE_SHA,
                },
                "toolchainProfile": {"id": "linux-x64", "digest": profile_digest},
            }),
            "schemaVersion": 1, "target": "linux-x64",
        }
        plan_path = repository / "plan.json"
        plan_path.write_bytes(canonical_json_bytes(plan))
        record = _verification_record(repository, revision, plan, observed)
        self.assertEqual(profile_digest, validate_verification_record(record)["profileDigest"])
        record["profileDigest"] = FIXTURE_SHA
        with self.assertRaisesRegex(ValueError, "current authorities"):
            current = _verification_record(repository, revision, plan, observed)
            if current != record:
                raise ValueError("Toolchain verification record does not match current authorities")

    def test_verify_cli_rejects_invalid_binary_plan_before_observing_tools(self) -> None:
        plan = self.root / "invalid-plan.json"
        plan.write_bytes(canonical_json_bytes({"invalid": True}))
        output = self.root / "stale.json"
        output.write_text("stale", encoding="utf-8")
        observe = mock.Mock()
        arguments = [
            "verify-producer", "--repository-root", str(self.root),
            "--repository-revision", "a" * 40, "--profile-id", "linux-x64",
            "--producer-role", "builder", "--target", "linux-x64",
            "--binary-plan", str(plan), "--output", str(output),
            "--verified-contract-manifest", str(plan),
            "--expected-runtime-version", "0.2.0",
            "--expected-flags-digest", FIXTURE_SHA,
        ]
        with mock.patch("ci.products.toolchain.observe_producer", observe), \
                mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            from ci.products.toolchain import main
            main(arguments)
        observe.assert_not_called()
        self.assertFalse(output.exists())

    def test_verify_cli_delegates_all_runtime_authorities_before_observing_tools(self) -> None:
        plan = self.root / "plan.json"
        manifest = self.root / "contract-manifest.json"
        plan.write_bytes(canonical_json_bytes({"plan": True}))
        manifest.write_bytes(canonical_json_bytes({"manifest": True}))
        output = self.root / "stale.json"
        output.write_text("stale", encoding="utf-8")
        observe = mock.Mock()
        arguments = [
            "verify-producer", "--repository-root", str(self.root),
            "--repository-revision", "a" * 40, "--profile-id", "linux-x64",
            "--producer-role", "builder", "--target", "linux-x64",
            "--binary-plan", str(plan), "--output", str(output),
            "--verified-contract-manifest", str(manifest),
            "--expected-runtime-version", "0.2.0",
            "--expected-flags-digest", FIXTURE_SHA,
        ]
        authority = mock.Mock(side_effect=ValueError("Runtime Contract authority mismatch"))
        with mock.patch.object(runtime_identity, "verify_runtime_binary_plan", authority), \
                mock.patch("ci.products.toolchain.observe_producer", observe), \
                mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            from ci.products.toolchain import main
            main(arguments)
        authority.assert_called_once()
        observe.assert_not_called()
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
