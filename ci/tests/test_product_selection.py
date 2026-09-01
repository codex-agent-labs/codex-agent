from __future__ import annotations

import subprocess
from pathlib import Path
import tempfile
import unittest

from ci.products.inventory import sha256_bytes
from ci.products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS, PhaseInstanceId
from ci.products.selection import (
    ALL_METADATA,
    PathSelection,
    classify_paths,
    phase_file_inventory,
    phase_inventory_paths,
)


def identities(result: PathSelection) -> set[PhaseInstanceId]:
    return set(result.instances)


def component(result: PathSelection, product: str, name: str) -> set[PhaseInstanceId]:
    return {
        instance for instance in result.instances
        if instance.product == product and instance.component == name
    }


def tracked_product_paths() -> tuple[str, ...]:
    tracked = set(subprocess.run(
        ("git", "ls-files"), check=True, capture_output=True, text=True,
    ).stdout.splitlines())
    tracked.update(subprocess.run(
        (
            "git", "ls-files", "--others", "--exclude-standard", "--",
            ":(glob)ci/*.py", ":(glob)ci/products/*.py",
        ),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines())
    root_files = {
        ".gitattributes", ".github/actionlint.yaml", ".github/dependabot.yml",
        "LICENSE", "Package.swift", "THIRD_PARTY_NOTICES.md", "build.gradle.kts",
        "gradle.properties", "gradle/libs.versions.toml", "gradlew", "gradlew.bat",
        "settings-gradle.lockfile", "settings.gradle.kts",
    }
    prefixes = (
        ".github/actions/", ".github/workflows/", "ci/", "codex-agent-", "legal/",
        "runtime/", "gradle/build-logic/", "gradle/kotlin-js-store/", "gradle/release/",
        "gradle/wrapper/", "tooling/",
    )
    return tuple(sorted(
        path for path in tracked if path in root_files or path.startswith(prefixes)
    ))


class ProductSelectionTest(unittest.TestCase):
    def assert_binding_only(self, path: str, language: str) -> None:
        result = classify_paths([path])
        selected = identities(result)
        self.assertEqual({"package", "validation", "metadata"}, {
            instance.phase for instance in component(result, "sdk", language)
        })
        self.assertEqual({language}, {
            instance.component for instance in selected if instance.product == "sdk"
        })
        self.assertFalse(any(instance.product == "runtime" for instance in selected))
        self.assertEqual((path,), result.inventory_paths)
        self.assertTrue(result.reuse_allowed)

    def test_native_binding_changes_select_only_the_matching_sdk_family_old_or_new(self) -> None:
        examples = {
            "python": "src/codex_agent/_ffi.py",
            "csharp": "src/CodexAgent/CodexAgent.cs",
            "rust": "src/lib.rs",
            "cpp": "include/codex_agent/codex_agent.hpp",
            "dart": "lib/src/ffi.dart",
        }
        for language, suffix in examples.items():
            with self.subTest(language=language, location="new"):
                self.assert_binding_only(f"codex-agent-bindings/{language}/{suffix}", language)
            with self.subTest(language=language, location="old"):
                self.assert_binding_only(
                    f"codex-agent-runtime-desktop/bindings/{language}/{suffix}",
                    language,
                )

    def test_javascript_package_and_declaration_changes_select_only_javascript_sdk(self) -> None:
        for path in (
            "codex-agent-bindings/javascript/package/index.d.ts",
            "codex-agent-runtime-desktop/npm/package/index.d.ts",
        ):
            with self.subTest(path=path):
                self.assert_binding_only(path, "javascript")

    def test_sdk_default_runtime_selects_sdk_packages_without_runtime_rebuild(self) -> None:
        result = classify_paths(["gradle/release/sdk-default-runtime.txt"])
        selected = identities(result)
        self.assertFalse(any(instance.product == "runtime" for instance in selected))
        self.assertEqual(
            {"sdk-core", "sdk-android", "sdk-ios", *NATIVE_BINDINGS, "javascript"},
            {instance.component for instance in selected},
        )
        self.assertFalse(any(instance.phase == "binary" for instance in selected))
        self.assertTrue(all(
            any(instance.component == component_name and instance.phase == "package" for instance in selected)
            for component_name in {"sdk-core", "sdk-android", "sdk-ios", *NATIVE_BINDINGS, "javascript"}
        ))

    def test_current_runtime_version_does_not_select_mobile_sdk_products(self) -> None:
        selected = identities(classify_paths(["gradle/release/versions/runtime.txt"]))
        self.assertEqual(
            {PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")},
            selected,
        )
        self.assertFalse(any(instance.product == "sdk" for instance in selected))

    def test_docs_and_ci_unit_tests_select_no_product_work(self) -> None:
        paths = ("README.md", "docs/repository-boundaries.md", "ci/tests/test_products.py")
        result = classify_paths(paths)
        self.assertEqual((), result.instances)
        self.assertEqual((), result.inventory_paths)
        self.assertEqual(tuple(sorted(paths)), result.ignored_paths)
        self.assertEqual((), result.unknown_paths)
        self.assertTrue(result.reuse_allowed)

    def test_removed_module_paths_are_known_fail_safe_migration_inputs(self) -> None:
        paths = (
            "codex-agent-client/src/commonMain/kotlin/Legacy.kt",
            "codex-agent-runtime-node/src/webMain/kotlin/LegacyNode.kt",
            "runtime-host-shared/src/commonMain/kotlin/LegacyHost.kt",
            "gradle/build-logic/src/main/kotlin/codexagent.node-runtime.gradle.kts",
        )
        result = classify_paths(paths)
        self.assertEqual(set(PHASE_INSTANCE_IDS), identities(result))
        self.assertEqual((), result.unknown_paths)
        self.assertEqual(tuple(sorted(paths)), result.inventory_paths)
        self.assertTrue(result.reuse_allowed)

    def test_shared_native_validation_change_selects_validation_and_metadata_only(self) -> None:
        result = classify_paths([
            "codex-agent-runtime-desktop/src/nativeTest/kotlin/example/RuntimeValidationTest.kt"
        ])
        selected = identities(result)
        for target in NATIVE_TARGETS:
            self.assertEqual({"validation", "metadata"}, {
                instance.phase for instance in component(result, "runtime", target)
            })
        self.assertIn(PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"), selected)
        self.assertFalse(any(instance.phase in {"binary", "package"} for instance in selected))
        self.assertFalse(any(instance.product == "sdk" for instance in selected))

    def test_shared_package_layout_selects_package_and_successors_without_binary(self) -> None:
        result = classify_paths([
            "runtime/build-logic/src/main/kotlin/DesktopRuntimePackageTask.kt"
        ])
        for target in NATIVE_TARGETS:
            self.assertEqual({"package", "validation", "metadata"}, {
                instance.phase for instance in component(result, "runtime", target)
            })
        self.assertFalse(any(instance.phase == "binary" for instance in result.instances))
        self.assertFalse(component(result, "runtime", "jvm"))
        self.assertFalse(any(instance.product == "sdk" for instance in result.instances))

    def test_windows_native_source_selects_one_target_and_runtime_aggregate(self) -> None:
        result = classify_paths([
            "codex-agent-runtime-desktop/src/mingwMain/kotlin/example/WindowsRuntime.kt"
        ])
        self.assertEqual({"binary", "package", "validation", "metadata"}, {
            instance.phase for instance in component(result, "runtime", "windows-x64")
        })
        self.assertIn(
            PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"),
            result.instances,
        )
        self.assertFalse(any(
            instance.component in set(NATIVE_TARGETS) - {"windows-x64"}
            for instance in result.instances
        ))
        self.assertFalse(any(instance.product == "sdk" for instance in result.instances))

    def test_shared_native_source_selects_all_five_targets_but_no_adapters_or_sdk(self) -> None:
        result = classify_paths([
            "codex-agent-runtime-desktop/src/nativeMain/kotlin/example/NativeRuntime.kt"
        ])
        for target in NATIVE_TARGETS:
            self.assertEqual({"binary", "package", "validation", "metadata"}, {
                instance.phase for instance in component(result, "runtime", target)
            })
        self.assertFalse(component(result, "runtime", "jvm"))
        self.assertFalse(component(result, "runtime", "node-js"))
        self.assertFalse(any(instance.product == "sdk" for instance in result.instances))

    def test_c_header_or_export_selects_native_runtime_and_every_native_binding(self) -> None:
        for path in (
            "codex-agent-runtime-desktop/native/c-api/include/codex_agent.h",
            "codex-agent-runtime-desktop/native/c-api/exports/windows.def",
            "ci/products/c_abi.py",
        ):
            with self.subTest(path=path):
                result = classify_paths([path])
                for target in NATIVE_TARGETS:
                    self.assertTrue(component(result, "runtime", target))
                for language in NATIVE_BINDINGS:
                    self.assertTrue(component(result, "sdk", language))
                self.assertFalse(component(result, "runtime", "jvm"))
                self.assertFalse(component(result, "sdk", "javascript"))
                self.assertFalse(component(result, "sdk", "sdk-core"))

    def test_c_abi_generator_authority_is_an_exact_native_binary_input(self) -> None:
        path = "ci/products/c_abi.py"
        paths = tracked_product_paths()
        for target in NATIVE_TARGETS:
            instance = PhaseInstanceId("runtime", target, "binary", target)
            self.assertIn(path, phase_inventory_paths(paths, instance))
        self.assertNotIn(
            path,
            phase_inventory_paths(
                paths,
                PhaseInstanceId("runtime", "jvm", "binary", "jvm"),
            ),
        )

    def test_jvm_contract_change_selects_contract_runtime_jvm_and_jvm_facade_only(self) -> None:
        result = classify_paths([
            "codex-agent-core/src/jvmMain/kotlin/example/JvmProjection.kt"
        ])
        self.assertEqual({"binary", "package", "validation", "metadata"}, {
            instance.phase for instance in component(result, "contract", "contract")
        })
        self.assertTrue(component(result, "runtime", "jvm"))
        self.assertEqual({"validation", "metadata"}, {
            instance.phase for instance in component(result, "sdk", "sdk-core")
        })
        self.assertEqual({"jvm"}, {
            instance.target for instance in component(result, "sdk", "sdk-core")
            if instance.phase == "validation"
        })
        self.assertFalse(component(result, "runtime", "node-js"))
        self.assertFalse(component(result, "sdk", "sdk-android"))
        self.assertFalse(component(result, "sdk", "javascript"))

    def test_js_contract_change_selects_contract_node_js_and_js_consumers_only(self) -> None:
        result = classify_paths([
            "codex-agent-core/src/jsMain/kotlin/example/JsProjection.kt"
        ])
        self.assertTrue(component(result, "contract", "contract"))
        self.assertTrue(component(result, "runtime", "node-js"))
        self.assertTrue(component(result, "sdk", "javascript"))
        self.assertEqual({"node-js"}, {
            instance.target for instance in component(result, "sdk", "sdk-core")
            if instance.phase == "validation"
        })
        self.assertFalse(component(result, "runtime", "jvm"))
        self.assertFalse(component(result, "runtime", "node-wasm"))
        self.assertFalse(any(
            instance.component in NATIVE_BINDINGS for instance in result.instances
        ))

    def test_common_contract_model_selects_every_projection_without_disabling_reuse(self) -> None:
        result = classify_paths([
            "codex-agent-core/src/commonMain/kotlin/example/CanonicalModel.kt"
        ])
        self.assertEqual(set(PHASE_INSTANCE_IDS), identities(result))
        self.assertEqual((), result.unknown_paths)
        self.assertTrue(result.reuse_allowed)

    def test_app_server_identity_selects_five_runtime_variants_only(self) -> None:
        result = classify_paths(["codex-agent-runtime-desktop/codex-app-server-distributions.json"])
        for target in NATIVE_TARGETS:
            self.assertTrue(component(result, "runtime", target))
        self.assertFalse(component(result, "runtime", "jvm"))
        self.assertFalse(component(result, "runtime", "node-js"))
        self.assertFalse(any(instance.product == "sdk" for instance in result.instances))

    def test_metadata_policy_selects_metadata_only(self) -> None:
        for path in (
            "ci/products/aggregate.py",
            "ci/products/index.py",
            "ci/products/signatures.py",
            "gradle/build-logic/src/main/kotlin/PromotedCandidateTasks.kt",
            "gradle/release/product-signing-keys.json",
        ):
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual(set(ALL_METADATA), identities(result))
                self.assertFalse(any(instance.phase != "metadata" for instance in result.instances))
                self.assertFalse(result.unknown_paths)
                self.assertTrue(result.reuse_allowed)

    def test_shared_toolchain_authority_selects_exact_native_binary_lines(self) -> None:
        result = classify_paths(["ci/products/toolchain.py"])
        for target in NATIVE_TARGETS:
            self.assertIn(PhaseInstanceId("runtime", target, "binary", target), result.instances)
        self.assertFalse(component(result, "runtime", "jvm"))
        self.assertFalse(component(result, "runtime", "node-js"))
        self.assertFalse(any(instance.product == "sdk" for instance in result.instances))

    def test_target_toolchain_profile_selects_only_its_native_binary_line(self) -> None:
        path = "gradle/release/toolchains/runtime/linux-x64.json"
        result = classify_paths([path])
        self.assertEqual(
            {"linux-x64", "runtime-aggregate"},
            {instance.component for instance in result.instances},
        )
        self.assertIn(
            PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64"),
            result.instances,
        )
        self.assertFalse(any(
            instance.product == "sdk" or instance.component in {"jvm", "node-js", "node-wasm"}
            for instance in result.instances
        ))
        self.assertNotIn(
            path,
            phase_inventory_paths(
                {path},
                PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64"),
            ),
        )

    def test_runtime_binary_flags_authorities_select_exact_native_binary_lines(self) -> None:
        paths = tracked_product_paths()
        for path in (
            "ci/products/runtime_flags.py",
            "codex-agent-runtime-desktop/native/c-api/binary-flags.json",
        ):
            with self.subTest(path=path):
                result = classify_paths([path])
                for target in NATIVE_TARGETS:
                    instance = PhaseInstanceId("runtime", target, "binary", target)
                    self.assertIn(instance, result.instances)
                    inventory = phase_inventory_paths(set(paths) | {path}, instance)
                    if path.endswith("runtime_flags.py"):
                        self.assertIn(path, inventory)
                    else:
                        self.assertNotIn(path, inventory)
                self.assertFalse(component(result, "runtime", "jvm"))
                self.assertFalse(component(result, "runtime", "node-js"))
                self.assertFalse(any(instance.product == "sdk" for instance in result.instances))

    def test_mixed_runtime_flags_file_broadens_only_to_its_concrete_runtime_owner(self) -> None:
        result = classify_paths([
            "runtime/build-logic/src/main/kotlin/codexagent.desktop-runtime.gradle.kts"
        ])
        self.assertEqual(
            {"jvm", "node-js", "node-wasm", *NATIVE_TARGETS, "runtime-aggregate"},
            {instance.component for instance in result.instances},
        )
        self.assertTrue(all(instance.product == "runtime" for instance in result.instances))
        self.assertTrue(any(instance.phase == "binary" for instance in result.instances))
        self.assertFalse(any(instance.product == "sdk" for instance in result.instances))

    def test_unknown_path_fails_closed_and_disables_reuse(self) -> None:
        path = "unowned/new-product-input.txt"
        result = classify_paths([path])
        self.assertEqual(set(PHASE_INSTANCE_IDS), identities(result))
        self.assertEqual((path,), result.unknown_paths)
        self.assertEqual((path,), result.inventory_paths)
        self.assertFalse(result.reuse_allowed)

    def test_product_tests_select_validation_successors_without_binary_or_package(self) -> None:
        cases = {
            "codex-agent-core/src/commonTest/kotlin/example/ContractTest.kt": (
                "contract", "contract", {"validation", "metadata"},
            ),
            "codex-agent-runtime-android/src/test/kotlin/example/AndroidTest.kt": (
                "sdk", "sdk-android", {"validation", "metadata"},
            ),
            "codex-agent-runtime-ios/src/iosTest/kotlin/example/IosTest.kt": (
                "sdk", "sdk-ios", {"validation", "metadata"},
            ),
        }
        for path, (product, owner, phases) in cases.items():
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual(phases, {
                    instance.phase for instance in component(result, product, owner)
                })
                self.assertFalse(any(
                    instance.phase in {"binary", "package"} for instance in result.instances
                ))
                self.assertEqual({product}, {instance.product for instance in result.instances})

    def test_internal_native_cinterop_change_does_not_select_sdk_bindings(self) -> None:
        result = classify_paths([
            "codex-agent-runtime-desktop/src/nativeInterop/cinterop/codex_desktop.def"
        ])
        self.assertEqual(set(NATIVE_TARGETS) | {"runtime-aggregate"}, {
            instance.component for instance in result.instances
        })
        self.assertFalse(any(instance.product == "sdk" for instance in result.instances))

    def test_selection_and_inventory_are_separate_and_paths_are_canonical(self) -> None:
        result = classify_paths([
            "docs/runtime.md",
            "codex-agent-bindings/python/src/codex_agent/_ffi.py",
        ])
        self.assertTrue(result.instances)
        self.assertEqual(
            ("codex-agent-bindings/python/src/codex_agent/_ffi.py",),
            result.inventory_paths,
        )
        self.assertEqual(("docs/runtime.md",), result.ignored_paths)
        for invalid in (
            "/absolute", "../escape", "a/../b", "a//b", "./a", "a\\b", "a/", "a\x00b",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                classify_paths([invalid])
        with self.assertRaisesRegex(ValueError, "unique"):
            classify_paths(["README.md", "README.md"])

    def test_phase_inventories_contain_only_direct_inputs(self) -> None:
        paths = (
            "README.md",
            "codex-agent-core/src/jvmMain/kotlin/example/JvmProjection.kt",
            "codex-agent-runtime-desktop/src/jvmMain/kotlin/example/JvmRuntime.kt",
            "codex-agent-runtime-desktop/src/jvmTest/kotlin/example/JvmRuntimeTest.kt",
            "codex-agent-bindings/python/src/codex_agent/_ffi.py",
            "ci/products/index.py",
        )
        self.assertEqual(
            (paths[1],),
            phase_inventory_paths(
                paths, PhaseInstanceId("contract", "contract", "binary", "common"),
            ),
        )
        self.assertEqual(
            (paths[2],),
            phase_inventory_paths(paths, PhaseInstanceId("runtime", "jvm", "binary", "jvm")),
        )
        self.assertEqual(
            (paths[3],),
            phase_inventory_paths(
                paths, PhaseInstanceId("runtime", "jvm", "validation", "linux-x64"),
            ),
        )
        self.assertEqual(
            (paths[4],),
            phase_inventory_paths(paths, PhaseInstanceId("sdk", "python", "package", "desktop")),
        )
        self.assertNotIn(
            paths[1],
            phase_inventory_paths(paths, PhaseInstanceId("runtime", "jvm", "binary", "jvm")),
        )
        self.assertEqual(
            (paths[5],),
            phase_inventory_paths(
                paths, PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"),
            ),
        )

    def test_phase_file_inventory_hashes_exact_owned_bytes(self) -> None:
        relative = "codex-agent-bindings/python/src/codex_agent/_ffi.py"
        instance = PhaseInstanceId("sdk", "python", "package", "desktop")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / relative
            source.parent.mkdir(parents=True)
            source.write_bytes(b"a")

            first = phase_file_inventory(root, (relative,), instance)
            source.write_bytes(b"b")
            second = phase_file_inventory(root, (relative,), instance)
            empty = phase_file_inventory(
                root,
                (),
                PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64"),
            )

        self.assertEqual([{
            "relativePath": relative,
            "bytes": 1,
            "sha256": sha256_bytes(b"a"),
        }], first)
        self.assertEqual([{
            "relativePath": relative,
            "bytes": 1,
            "sha256": sha256_bytes(b"b"),
        }], second)
        self.assertEqual([], empty)

    def test_unknown_path_enters_every_phase_inventory_fail_closed(self) -> None:
        for unknown in (
            "unowned/new-product-input.txt",
            "ci/lanes/new-owner.pathspec",
            "gradle/release/toolchains/runtime/unknown.json",
            "gradle/release/toolchains/runtime/linux-x64.txt",
        ):
            result = classify_paths((unknown,))
            self.assertEqual((unknown,), result.unknown_paths)
            self.assertFalse(result.reuse_allowed)
            for instance in PHASE_INSTANCE_IDS:
                with self.subTest(path=unknown, instance=instance):
                    self.assertEqual((unknown,), phase_inventory_paths((unknown,), instance))

    def test_only_exact_runtime_toolchain_profiles_are_derived_authorities(self) -> None:
        for target in NATIVE_TARGETS:
            path = f"gradle/release/toolchains/runtime/{target}.json"
            result = classify_paths((path,))
            self.assertEqual((), result.unknown_paths)
            self.assertEqual((), phase_inventory_paths(
                (path,), PhaseInstanceId("runtime", target, "binary", target),
            ))
            self.assertEqual({target, "runtime-aggregate"}, {
                instance.component for instance in result.instances
            })

    def test_mobile_facade_and_runtime_adapter_paths_have_disjoint_owners(self) -> None:
        android = classify_paths(["codex-agent-runtime-android/src/main/AndroidRuntime.kt"])
        ios = classify_paths(["codex-agent-runtime-ios/src/iosMain/IosRuntime.kt"])
        facade = classify_paths(["codex-agent-sdk/src/commonMain/Facade.kt"])
        self.assertTrue(component(android, "sdk", "sdk-android"))
        self.assertFalse(component(android, "sdk", "sdk-ios"))
        self.assertTrue(component(ios, "sdk", "sdk-ios"))
        self.assertFalse(component(ios, "sdk", "sdk-android"))
        self.assertTrue(component(facade, "sdk", "sdk-core"))
        self.assertFalse(component(facade, "sdk", "sdk-android"))
        self.assertFalse(any(instance.product == "runtime" for instance in facade.instances))

    def test_contract_build_inputs_are_known_and_select_every_projection(self) -> None:
        for path in (
            "codex-agent-core/build.gradle.kts",
            "codex-agent-core/gradle.lockfile",
        ):
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual(set(PHASE_INSTANCE_IDS), identities(result))
                self.assertEqual((), result.unknown_paths)
                self.assertEqual((path,), result.inventory_paths)
                self.assertTrue(result.reuse_allowed)

    def test_runtime_build_and_lock_inputs_select_runtime_only(self) -> None:
        paths = (
            "codex-agent-runtime-desktop/gradle.lockfile",
            "runtime/build-logic/build.gradle.kts",
            "runtime/build-logic/gradle.lockfile",
            "runtime/build-logic/gradle/verification-metadata.xml",
            "runtime/build-logic/settings-gradle.lockfile",
            "runtime/build-logic/settings.gradle.kts",
            "runtime/gradle/verification-metadata.xml",
            "runtime/settings-gradle.lockfile",
        )
        for path in paths:
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertTrue(result.instances)
                self.assertTrue(all(instance.product == "runtime" for instance in result.instances))
                self.assertFalse(any(instance.product in {"contract", "sdk"} for instance in result.instances))
                self.assertFalse(result.unknown_paths)
                self.assertTrue(result.reuse_allowed)

    def test_runtime_javascript_locks_select_the_matching_adapter_only(self) -> None:
        cases = {
            "gradle/kotlin-js-store/package-lock.json": "node-js",
            "gradle/kotlin-js-store/wasm/package-lock.json": "node-wasm",
            "runtime/gradle/kotlin-js-store/package-lock.json": "node-js",
            "runtime/gradle/kotlin-js-store/wasm/package-lock.json": "node-wasm",
        }
        for path, owner in cases.items():
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertTrue(component(result, "runtime", owner))
                self.assertEqual({owner, "runtime-aggregate"}, {
                    instance.component for instance in result.instances
                })
                self.assertFalse(any(instance.product == "sdk" for instance in result.instances))
                self.assertFalse(result.unknown_paths)

    def test_runtime_build_logic_has_concrete_component_and_phase_owners(self) -> None:
        cases = {
            "runtime/build-logic/src/main/kotlin/JvmRuntimeEvidenceTasks.kt": (
                {"jvm", "runtime-aggregate"}, {"validation", "metadata"},
            ),
            "runtime/build-logic/src/main/kotlin/NodeRuntimeEvidenceTasks.kt": (
                {"node-js", "node-wasm", "runtime-aggregate"}, {"validation", "metadata"},
            ),
            "runtime/build-logic/src/main/kotlin/LinuxArm64RuntimeEvidenceBundle.kt": (
                {"linux-arm64", "runtime-aggregate"}, {"validation", "metadata"},
            ),
            "runtime/build-logic/src/main/kotlin/RuntimeCanonicalTestResultsClient.kt": (
                {"jvm", "node-js", "node-wasm", *NATIVE_TARGETS, "runtime-aggregate"},
                {"validation", "metadata"},
            ),
        }
        for path, (owners, phases) in cases.items():
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual(owners, {instance.component for instance in result.instances})
                self.assertTrue(all(instance.phase in phases for instance in result.instances))
                self.assertFalse(any(instance.phase in {"binary", "package"} for instance in result.instances))
                self.assertFalse(any(instance.product == "sdk" for instance in result.instances))

    def test_shipped_native_binding_sources_start_at_package_but_js_consumers_are_validation_only(self) -> None:
        cases = {
            "python": "codex-agent-bindings/python/tests/test_binding.py",
            "csharp": "codex-agent-bindings/csharp/samples/CodexAgent.Consumer/Program.cs",
            "rust": "codex-agent-bindings/rust/consumer/src/main.rs",
            "cpp": "codex-agent-bindings/cpp/tests/wrapper_test.cpp",
            "dart": "codex-agent-bindings/dart/test/package_test.dart",
            "javascript": "codex-agent-bindings/javascript/consumer/smoke.mjs",
        }
        for language, path in cases.items():
            with self.subTest(language=language):
                result = classify_paths([path])
                expected = (
                    {"validation", "metadata"}
                    if language == "javascript"
                    else {"package", "validation", "metadata"}
                )
                self.assertEqual(expected, {
                    instance.phase for instance in component(result, "sdk", language)
                })
                self.assertEqual({language}, {
                    instance.component for instance in result.instances if instance.product == "sdk"
                })
                self.assertEqual(
                    language != "javascript",
                    any(instance.phase == "package" for instance in result.instances),
                )
                self.assertFalse(any(instance.product == "runtime" for instance in result.instances))

    def test_mobile_external_evidence_paths_are_validation_only(self) -> None:
        cases = {
            "sdk-android": (
                "tooling/android-runtime-evidence/src/androidTest/kotlin/RuntimeBootstrapDeviceTest.kt"
            ),
            "sdk-ios": "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureSwiftConsumer.swift",
            "sdk-ios-tests": "codex-agent-runtime-ios/apple/Tests/ObservationTests.swift",
            "sdk-ios-bridge": "codex-agent-runtime-ios/native/bridge/src/tests/protocol.rs",
        }
        for label, path in cases.items():
            owner = "sdk-android" if label == "sdk-android" else "sdk-ios"
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual({"validation", "metadata"}, {
                    instance.phase for instance in component(result, "sdk", owner)
                })
                self.assertFalse(any(instance.phase in {"binary", "package"} for instance in result.instances))
                self.assertFalse(any(instance.product == "runtime" for instance in result.instances))

    def test_internal_native_headers_have_exact_target_owners(self) -> None:
        cases = {
            "codex-agent-runtime-desktop/native/include/codex_desktop_windows.h": {"windows-x64"},
            "codex-agent-runtime-desktop/native/include/codex_desktop_posix.h": set(NATIVE_TARGETS) - {
                "windows-x64"
            },
        }
        for path, targets in cases.items():
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual(targets | {"runtime-aggregate"}, {
                    instance.component for instance in result.instances
                })
                self.assertFalse(any(instance.product == "sdk" for instance in result.instances))
                self.assertFalse(component(result, "runtime", "jvm"))

    def test_provenance_release_policy_and_app_server_inputs_have_exact_owners(self) -> None:
        for path in (
            "gradle/build-logic/src/main/kotlin/CandidateCiProvenance.kt",
            "gradle/release/publication-approvals.json",
        ):
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual(set(ALL_METADATA), identities(result))
                self.assertFalse(any(instance.phase != "metadata" for instance in result.instances))

        ios = classify_paths(["codex-agent-runtime-ios/native/provenance.json"])
        self.assertTrue(component(ios, "sdk", "sdk-ios"))
        self.assertFalse(component(ios, "sdk", "sdk-android"))
        self.assertFalse(any(instance.product == "runtime" for instance in ios.instances))

        result = classify_paths(["codex-agent-runtime-desktop/codex-app-server-distributions.json"])
        self.assertEqual(set(NATIVE_TARGETS) | {"runtime-aggregate"}, {
            instance.component for instance in result.instances
        })
        self.assertFalse(component(result, "runtime", "jvm"))
        self.assertFalse(any(instance.product == "sdk" for instance in result.instances))

    def test_all_physical_build_logic_tests_are_static_only(self) -> None:
        paths = (
            "gradle/build-logic/src/test/kotlin/ProductVersionsTest.kt",
            "runtime/build-logic/src/test/kotlin/RuntimeProductPhaseMappingTest.kt",
        )
        result = classify_paths(paths)
        self.assertEqual((), result.instances)
        self.assertEqual((), result.inventory_paths)
        self.assertEqual(tuple(sorted(paths)), result.ignored_paths)
        self.assertEqual((), result.unknown_paths)
        self.assertTrue(result.reuse_allowed)

    def test_every_tracked_product_authority_has_declared_ownership(self) -> None:
        paths = tracked_product_paths()
        result = classify_paths(paths)
        self.assertGreater(len(paths), 1000)
        self.assertEqual((), result.unknown_paths)
        self.assertTrue(result.reuse_allowed)

    def test_runtime_attestation_and_sdk_compatibility_have_exact_product_owners(self) -> None:
        runtime = classify_paths(["ci/products/runtime_attestation.py"])
        self.assertEqual(
            set(NATIVE_TARGETS) | {"runtime-aggregate"},
            {instance.component for instance in runtime.instances},
        )
        self.assertTrue(all(instance.product == "runtime" and instance.phase == "metadata" for instance in runtime.instances))

        aggregate = classify_paths(["ci/products/runtime_aggregate.py"])
        self.assertEqual(
            {("runtime", "runtime-aggregate", "metadata", "aggregate")},
            {
                (instance.product, instance.component, instance.phase, instance.target)
                for instance in aggregate.instances
            },
        )

        sdk = classify_paths(["ci/products/sdk_compatibility.py"])
        self.assertFalse(any(instance.product != "sdk" for instance in sdk.instances))
        self.assertEqual(
            {"sdk-core", "sdk-android", "sdk-ios", *NATIVE_BINDINGS, "javascript"},
            {instance.component for instance in sdk.instances},
        )
        self.assertTrue(all(instance.phase in {"package", "validation", "metadata"} for instance in sdk.instances))

    def test_current_untracked_product_authorities_are_explicit_controls(self) -> None:
        paths = (
            "ci/legacy_lanes.py",
            "ci/product_legacy.py",
            "ci/products/contract_projection.py",
            "ci/products/plan.py",
            "ci/products/registry.py",
            "ci/products/restore.py",
            "ci/products/reuse.py",
            "ci/products/selection.py",
        )
        result = classify_paths(paths)
        self.assertEqual(set(PHASE_INSTANCE_IDS), identities(result))
        self.assertEqual((), result.unknown_paths)
        self.assertEqual((), result.inventory_paths)
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((), phase_inventory_paths(paths, instance))

    def test_root_gradle_inputs_do_not_enter_standalone_runtime_inventories(self) -> None:
        paths = ("build.gradle.kts", "gradle.properties", "settings-gradle.lockfile", "settings.gradle.kts")
        result = classify_paths(paths)
        self.assertFalse(any(instance.product == "runtime" for instance in result.instances))
        self.assertTrue(any(instance.product == "contract" for instance in result.instances))
        self.assertTrue(any(instance.product == "sdk" for instance in result.instances))
        for instance in PHASE_INSTANCE_IDS:
            if instance.product == "runtime":
                self.assertEqual((), phase_inventory_paths(paths, instance))

    def test_sccache_action_is_ios_rust_control_not_desktop_runtime_input(self) -> None:
        path = ".github/actions/setup-sccache/action.yml"
        result = classify_paths([path])
        self.assertEqual({"sdk-ios"}, {instance.component for instance in result.instances})
        self.assertFalse(any(instance.product == "runtime" for instance in result.instances))
        self.assertEqual((), result.inventory_paths)

    def test_checkout_and_repository_static_controls_are_explicit(self) -> None:
        attributes = classify_paths([".gitattributes"])
        self.assertEqual(set(PHASE_INSTANCE_IDS), identities(attributes))
        self.assertEqual((".gitattributes",), attributes.inventory_paths)
        static = classify_paths([".github/actionlint.yaml", ".github/dependabot.yml"])
        self.assertEqual((), static.instances)
        self.assertEqual((), static.inventory_paths)
        self.assertEqual((".github/actionlint.yaml", ".github/dependabot.yml"), static.ignored_paths)

    def test_all_111_phase_instances_have_nonempty_direct_tracked_inventories(self) -> None:
        paths = tracked_product_paths()
        for instance in PHASE_INSTANCE_IDS:
            with self.subTest(instance=instance):
                inventory = phase_inventory_paths(paths, instance)
                self.assertTrue(inventory)
                if instance.phase != "binary":
                    self.assertFalse(any(
                        path.startswith("codex-agent-runtime-desktop/src/")
                        and "/src/commonMain/" in path
                        for path in inventory
                    ))

    def test_workflow_and_lane_controls_select_work_without_entering_byte_inventory(self) -> None:
        paths = (
            ".github/workflows/desktop-runtime-evidence.yml",
            "ci/lanes/desktop-windows-x64.production.pathspec",
        )
        result = classify_paths(paths)
        self.assertTrue(component(result, "runtime", "windows-x64"))
        self.assertFalse(any(instance.product == "sdk" for instance in result.instances))
        self.assertEqual((), result.inventory_paths)
        self.assertEqual((), result.unknown_paths)
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((), phase_inventory_paths(paths, instance))


if __name__ == "__main__":
    unittest.main()
