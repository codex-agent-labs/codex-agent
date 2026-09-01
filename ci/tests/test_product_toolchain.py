from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from ci.products.inventory import canonical_json_bytes, sha256_bytes
from ci.products.toolchain import (
    PROFILE_SHAPES,
    PROFILE_TOOL_NAMES,
    load_and_verify_toolchain_profile,
    load_toolchain_profile,
    load_toolchain_profile_bytes,
    verify_toolchain_profile,
)


FIXTURE_SHA = "sha256:" + "1" * 64


def identity(name: str, os_name: str, arch: str) -> str:
    return {
        "gradleWrapper": "Gradle 9.4.1;distributionSha256=" + FIXTURE_SHA,
        "javaRuntime": "Temurin 17.0.20+8;VM=17.0.20+8",
        "konanDependencies": "targetClosureSha256=" + FIXTURE_SHA,
        "kotlinNativeCompiler": (
            f"Kotlin/Native 2.3.10;build=fixture;host={os_name}-{arch};archiveSha256={FIXTURE_SHA}"
        ),
        "kotlinPlugin": "Kotlin Gradle plugin 2.3.10",
        "supervisorCompiler": f"native compiler;build=fixture;target={os_name}-{arch}",
    }[name]


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
        tools["kotlinNativeCompiler"] = (
            f"Kotlin/Native 2.3.10;build=changed;host=Linux-X64;archiveSha256={FIXTURE_SHA}"
        )
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


if __name__ == "__main__":
    unittest.main()
