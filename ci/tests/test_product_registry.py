from __future__ import annotations

import unittest

from ci.products.registry import (
    COMPONENTS,
    NATIVE_TARGETS,
    PHASE_IDS,
    PHASE_INSTANCE_IDS,
    PUBLISHED_COORDINATES,
    PhaseId,
    PhaseInstanceId,
    phase_instance_dependencies,
    phase_targets,
    required_contract_components,
    required_toolchain_profile,
    validate_registry,
)


class ProductRegistryTest(unittest.TestCase):
    def test_registry_has_exact_logical_and_concrete_cardinality(self) -> None:
        self.assertEqual(19, len(COMPONENTS))
        self.assertEqual(67, len(PHASE_IDS))
        self.assertEqual(111, len(PHASE_INSTANCE_IDS))
        validate_registry()

    def test_every_component_has_one_registry_owned_product_family_coordinate(self) -> None:
        self.assertEqual(
            {(component.product, component.component) for component in COMPONENTS},
            set(PUBLISHED_COORDINATES),
        )
        self.assertEqual(
            {"io.github.codex-agent-labs:codex-agent-runtime-desktop"},
            {
                coordinate
                for (product, _), coordinate in PUBLISHED_COORDINATES.items()
                if product == "runtime"
            },
        )
        self.assertEqual(
            "CodexAgent::CodexAgent",
            PUBLISHED_COORDINATES[("sdk", "cpp")],
        )

    def test_runtime_adapter_validation_targets_match_workflow_evidence(self) -> None:
        self.assertEqual(NATIVE_TARGETS, phase_targets(PhaseId("runtime", "jvm", "validation")))
        self.assertEqual(NATIVE_TARGETS, phase_targets(PhaseId("runtime", "node-wasm", "validation")))
        self.assertEqual(
            tuple(sorted((*NATIVE_TARGETS, "node-js-binding"))),
            phase_targets(PhaseId("runtime", "node-js", "validation")),
        )
        for component in ("jvm", "node-js", "node-wasm"):
            self.assertNotIn(
                component,
                phase_targets(PhaseId("runtime", component, "validation")),
            )

    def test_adapter_host_validation_keeps_adapter_and_matching_host_inputs(self) -> None:
        instance = PhaseInstanceId("runtime", "jvm", "validation", "linux-x64")
        self.assertEqual(
            (
                PhaseInstanceId("runtime", "jvm", "package", "jvm"),
                PhaseInstanceId("runtime", "linux-x64", "package", "linux-x64"),
            ),
            phase_instance_dependencies(instance),
        )

    def test_javascript_sdk_uses_distinct_node_binding_evidence(self) -> None:
        dependencies = phase_instance_dependencies(
            PhaseInstanceId("sdk", "javascript", "validation", "node"),
        )
        self.assertIn(
            PhaseInstanceId("runtime", "node-js", "validation", "node-js-binding"),
            dependencies,
        )
        self.assertNotIn(
            PhaseInstanceId("runtime", "node-js", "validation", "node-js"),
            dependencies,
        )

    def test_native_sdk_packages_require_authenticated_runtime_metadata(self) -> None:
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        aggregate = PhaseInstanceId(
            "runtime", "runtime-aggregate", "metadata", "aggregate",
        )
        expected = {contract, aggregate}
        for target in NATIVE_TARGETS:
            expected.update({
                PhaseInstanceId("runtime", target, phase, target)
                for phase in ("package", "validation", "metadata")
            })
        for language in ("cpp", "csharp", "dart", "python", "rust"):
            with self.subTest(language=language):
                self.assertEqual(
                    tuple(sorted(expected)),
                    phase_instance_dependencies(
                        PhaseInstanceId("sdk", language, "package", "desktop"),
                    ),
                )

    def test_every_sdk_distribution_package_requires_the_shared_compatibility_products(self) -> None:
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        aggregate = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        runtime_metadata = {
            PhaseInstanceId("runtime", target, "metadata", target)
            for target in NATIVE_TARGETS
        }
        for component, target in (
            ("sdk-core", "common"),
            ("sdk-android", "android"),
            ("sdk-ios", "ios"),
            ("javascript", "node"),
        ):
            with self.subTest(component=component):
                dependencies = set(phase_instance_dependencies(
                    PhaseInstanceId("sdk", component, "package", target),
                ))
                self.assertTrue({contract, aggregate, *runtime_metadata} <= dependencies)
                self.assertFalse(any(
                    dependency.product == "runtime"
                    and dependency.component in NATIVE_TARGETS
                    and dependency.phase in {"binary", "package", "validation"}
                    for dependency in dependencies
                ))

    def test_unsupported_adapter_default_validation_target_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported target"):
            phase_instance_dependencies(
                PhaseInstanceId("runtime", "node-wasm", "validation", "node-wasm"),
            )

    def test_contract_consumers_use_metadata_and_exact_component_ownership(self) -> None:
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        cases = {
            PhaseInstanceId("runtime", "jvm", "binary", "jvm"): ("jvm",),
            PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64"): ("linux-x64",),
            PhaseInstanceId("sdk", "sdk-core", "binary", "common"): ("common",),
            PhaseInstanceId("sdk", "sdk-core", "validation", "node-wasm"): ("node-wasm",),
            PhaseInstanceId("sdk", "sdk-android", "binary", "android"): ("android",),
            PhaseInstanceId("sdk", "sdk-ios", "binary", "ios"): (
                "ios-arm64", "ios-simulator-arm64",
            ),
            PhaseInstanceId("sdk", "python", "package", "desktop"): ("common",),
            PhaseInstanceId("sdk", "javascript", "package", "node"): ("node-js",),
        }
        for instance, components in cases.items():
            with self.subTest(instance=instance):
                self.assertIn(contract, phase_instance_dependencies(instance))
                self.assertEqual(components, required_contract_components(instance))
                self.assertNotIn(
                    PhaseInstanceId("contract", "contract", "binary", "common"),
                    phase_instance_dependencies(instance),
                )

    def test_only_five_native_runtime_binaries_have_classified_toolchain_profiles(self) -> None:
        classified = {
            instance: required_toolchain_profile(instance)
            for instance in PHASE_INSTANCE_IDS
            if required_toolchain_profile(instance) is not None
        }
        self.assertEqual({
            PhaseInstanceId("runtime", target, "binary", target): target
            for target in NATIVE_TARGETS
        }, classified)
        self.assertEqual(106, sum(
            required_toolchain_profile(instance) is None
            for instance in PHASE_INSTANCE_IDS
        ))
        with self.assertRaisesRegex(ValueError, "Unknown product phase instance"):
            required_toolchain_profile(
                PhaseInstanceId("runtime", "linux-x64", "package", "wrong-target")
            )


if __name__ == "__main__":
    unittest.main()
