from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path
import tempfile
import unittest

from ci.products.inventory import sha256_bytes
from ci.products.plan import plan_phase, NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST
from ci.products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS, RUNTIME_COMPONENTS, PhaseInstanceId
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
    def test_zip64_transport_preflight_does_not_invalidate_contract_binary(self) -> None:
        path = "ci/products/zip_central_directory.py"
        canonical = "ci/products/inventory.py"
        binary = PhaseInstanceId("contract", "contract", "binary", "common")
        selected = classify_paths([path])
        self.assertEqual(set(PHASE_INSTANCE_IDS), identities(selected))
        self.assertEqual((), selected.inventory_paths)
        self.assertEqual((canonical,), phase_inventory_paths([canonical, path], binary))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ci/products").mkdir(parents=True)
            (root / canonical).write_bytes(b"canonical-v1")
            (root / path).write_bytes(b"transport-v1")
            first = phase_file_inventory(root, [canonical, path], binary)
            (root / path).write_bytes(b"transport-v2")
            self.assertEqual(first, phase_file_inventory(root, [canonical, path], binary))
            (root / canonical).write_bytes(b"canonical-v2")
            self.assertNotEqual(first, phase_file_inventory(root, [canonical, path], binary))

    def test_new_release_controls_select_owning_phases_without_entering_payload_keys(self) -> None:
        sdk = {instance for instance in PHASE_INSTANCE_IDS if instance.product == "sdk"}
        cases = {
            "ci/contract_phase11_bytes.py": {PhaseInstanceId("contract", "contract", "metadata", "common")},
            "ci/products/runtime_phase10_maven.py": {PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")},
            "ci/products/runtime_library_authorization.py": {PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")},
            "ci/runtime_phase10_library_caller.py": {PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")},
            "ci/products/sdk_phase10_maven.py": {
                PhaseInstanceId("sdk", "sdk-core", "metadata", "common"),
                PhaseInstanceId("sdk", "sdk-android", "metadata", "android"),
            },
            "ci/products/sdk_campaign_semantics.py": sdk,
            "ci/products/sdk_campaign_maven.py": {
                instance for instance in sdk if instance.component in {"sdk-core", "sdk-android"}
            },
            "ci/products/sdk_campaign_javascript.py": {
                instance for instance in sdk if instance.component == "javascript"
                and instance.phase in {"package", "validation", "metadata"}
            },
            "ci/sdk_android_validation_policy.py": {
                instance for instance in sdk if instance.component == "sdk-android"
                and instance.phase in {"validation", "metadata"}
            },
            "ci/sdk_core_metadata_bootstrap.py": {
                PhaseInstanceId("sdk", "sdk-core", "metadata", "common")
            },
            "ci/sdk_facade_upload_locator.py": {
                instance for instance in sdk if instance.component in {"sdk-core", "sdk-android"}
            },
            "ci/sdk_android_archive_provision.py": {
                instance for instance in sdk if instance.component == "sdk-android"
                or (instance.component == "sdk-core" and instance.phase in {"validation", "metadata"})
            },
            ".github/actions/sdk-android-core14-caller/action.yml": {
                instance for instance in sdk if instance.component == "sdk-android"
            },
            ".github/actions/sdk-core-validation-worker/action.yml": {
                instance for instance in sdk if instance.component == "sdk-core"
                and instance.phase in {"validation", "metadata"}
            },
            ".github/workflows/sdk-core-binary-validation.yml": {
                instance for instance in sdk if instance.component == "sdk-core"
            },
            ".github/workflows/sdk-core-package-validation.yml": {
                instance for instance in sdk if instance.component == "sdk-core"
                and instance.phase in {"package", "validation", "metadata"}
            },
            ".github/workflows/sdk-core-validation.yml": {
                instance for instance in sdk if instance.component == "sdk-core"
                and instance.phase in {"validation", "metadata"}
            },
            ".github/workflows/sdk-core-metadata-validation.yml": {
                instance for instance in sdk if instance.component == "sdk-core"
                and instance.phase == "metadata"
            },
            ".github/workflows/sdk-android-binary-validation.yml": {
                instance for instance in sdk if instance.component == "sdk-android"
            },
            ".github/workflows/sdk-android-package-validation.yml": {
                instance for instance in sdk if instance.component == "sdk-android"
                and instance.phase in {"package", "validation", "metadata"}
            },
            ".github/workflows/sdk-android-validation.yml": {
                instance for instance in sdk if instance.component == "sdk-android"
                and instance.phase in {"validation", "metadata"}
            },
            ".github/workflows/sdk-android-metadata-validation.yml": {
                instance for instance in sdk if instance.component == "sdk-android"
                and instance.phase == "metadata"
            },
            ".github/workflows/sdk-validation.yml": sdk,
            ".github/workflows/sdk-binding-parity.yml": sdk,
            ".github/workflows/sdk-consumer-validation.yml": sdk,
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual(expected, identities(result))
                self.assertEqual((), result.unknown_paths)
                self.assertEqual((), result.inventory_paths)
                for instance in PHASE_INSTANCE_IDS:
                    self.assertEqual((), phase_inventory_paths([path], instance))

        contract_workflow = ".github/workflows/contract-validation.yml"
        contract_selection = classify_paths([contract_workflow])
        self.assertTrue(any(instance.product == "contract" for instance in contract_selection.instances))
        self.assertEqual((), contract_selection.unknown_paths)
        self.assertEqual((), contract_selection.inventory_paths)

        future = classify_paths(["ci/products/sdk_campaign_unreviewed.py"])
        self.assertEqual(("ci/products/sdk_campaign_unreviewed.py",), future.unknown_paths)
        self.assertFalse(future.reuse_allowed)

    def test_bootstrap_guard_rechecks_all_plans_without_changing_payload_keys(self):
        result = classify_paths(("ci/products/gradle_bootstrap.py",))
        self.assertEqual(set(PHASE_INSTANCE_IDS), set(result.instances))
        self.assertEqual((), result.inventory_paths)
        self.assertEqual((), result.unknown_paths)

    def test_native_prepared_receiver_selects_only_its_bindings_without_payload_keys(self):
        path = "ci/sdk_native_prepared_receiver.py"
        result = classify_paths((path,))
        expected = {instance for instance in PHASE_INSTANCE_IDS
                    if instance.product == "sdk" and instance.component in NATIVE_BINDINGS
                    and instance.phase in {"package", "validation", "metadata"}}
        self.assertEqual(expected, identities(result))
        self.assertEqual((), result.unknown_paths)
        self.assertEqual((), result.inventory_paths)
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((), phase_inventory_paths((path,), instance))

    def test_original_transport_and_signing_controls_do_not_change_payload_keys(self) -> None:
        paths = (
            "ci/products/signing_isolation.py", "ci/runtime_preparation_capture.py",
            "ci/runtime_preparation_locator.py", "ci/runtime_prepared_aggregate.py",
            "ci/runtime_prepared_native.py", "ci/runtime_prepared_release.py",
            "ci/runtime_prepared_state.py", "ci/runtime_signing_preparation.py",
            "ci/sdk_javascript_validation_locator.py", "ci/sdk_native_continuation.py",
            ".github/actions/capture-sdk-tooling/action.yml",
            ".github/actions/prepare-runtime-signing/action.yml",
            ".github/actions/provision-sdk-dart-cache/action.yml",
            ".github/actions/sdk-ios-package-worker/action.yml",
            ".github/actions/sdk-javascript-metadata-worker/action.yml",
        )
        for path in paths:
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual((), result.unknown_paths)
                self.assertTrue(result.instances)
                self.assertEqual((), result.inventory_paths)
                for instance in PHASE_INSTANCE_IDS:
                    self.assertEqual((), phase_inventory_paths([path], instance))

    def test_apple_validation_package_inputs_do_not_invalidate_binary_or_package(self) -> None:
        expected = {item for item in PHASE_INSTANCE_IDS
                    if item.product == "sdk" and item.component == "sdk-ios"
                    and item.phase in {"validation", "metadata"}}
        for name in ("AppleDeviceValidationTask.kt", "AppleValidationDeviceInputs.kt",
                     "AppleValidationEvidenceArchive.kt", "AppleValidationEvidenceTask.kt",
                     "AppleValidationContentTasks.kt",
                     "AppleValidationPackageInputs.kt", "AppleValidationPackageTask.kt",
                     "IosSdkValidationPackageTasks.kt", "IosSdkValidationConsumerTasks.kt"):
            with self.subTest(name=name):
                path = f"gradle/build-logic/src/main/kotlin/{name}"
                result = classify_paths([path])
                self.assertEqual(expected, identities(result))
                self.assertEqual((), result.unknown_paths)
                for instance in PHASE_INSTANCE_IDS:
                    self.assertEqual((path,) if instance in expected and instance.phase == "validation" else (),
                                     phase_inventory_paths([path], instance))

    def test_apple_metadata_writer_selects_only_metadata_and_owns_its_bytes(self) -> None:
        expected = {PhaseInstanceId("sdk", "sdk-ios", "metadata", "ios")}
        for path in ("ci/products/sdk_apple_metadata.py",
                     "gradle/build-logic/src/main/kotlin/IosSdkMetadataContentTask.kt"):
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual(expected, identities(result))
                self.assertEqual((), result.unknown_paths)
                for instance in PHASE_INSTANCE_IDS:
                    self.assertEqual((path,) if instance in expected else (), phase_inventory_paths([path], instance))

    def test_facade_content_and_android_transport_have_separate_owners(self) -> None:
        for path, component_name, owns_bytes in (
            ("ci/products/sdk_facade_validation.py", "sdk-core", True),
            ("ci/products/sdk_facade_inputs.py", "sdk-core", True),
            ("ci/products/sdk_facade_source.py", "sdk-core", False),
            ("ci/products/sdk_facade_native_policy.py", "sdk-core", False),
            ("ci/products/sdk_facade_compiler_policy.py", "sdk-core", False),
            ("ci/products/sdk_facade_validation_admission.py", "sdk-core", False),
            ("ci/products/sdk_facade_execution_observation.py", "sdk-core", False),
            ("ci/sdk_facade_original_validation.py", "sdk-core", False),
            ("ci/sdk_facade_workflow.py", "sdk-core", False),
            ("ci/sdk_facade_validation_phase.py", "sdk-core", False),
            ("gradle/build-logic/src/main/kotlin/SdkFacadeOriginalExecution.kt", "sdk-core", False),
            ("gradle/build-logic/src/main/kotlin/SdkFacadeCompilerCapture.kt", "sdk-core", False),
            ("gradle/build-logic/src/main/kotlin/SdkFacadeValidationTasks.kt", "sdk-core", True),
            ("gradle/build-logic/src/main/kotlin/ImportedSdkFacadePublicationVerification.kt", "sdk-core", True),
            ("ci/sdk_android_upload_locator.py", "sdk-android", False),
            ("ci/sdk_android_dispatch_observer.py", "sdk-android", False),
            ("ci/products/sdk_android_validation_admission.py", "sdk-android", False),
            ("ci/products/sdk_android_validation_phase.py", "sdk-android", False),
            ("ci/sdk_android_evidence_capture.py", "sdk-android", False),
            ("ci/sdk_android_firebase_capture.py", "sdk-android", False),
            ("ci/products/sdk_android_observation.py", "sdk-android", False),
            ("gradle/build-logic/src/main/kotlin/FirebaseAndroidOriginalEvidence.kt", "sdk-android", False),
        ):
            with self.subTest(path=path):
                expected = {item for item in PHASE_INSTANCE_IDS
                            if item.product == "sdk" and item.component == component_name
                            and item.phase in {"validation", "metadata"}}
                result = classify_paths([path])
                self.assertEqual(expected, identities(result))
                self.assertEqual((), result.unknown_paths)
                for instance in PHASE_INSTANCE_IDS:
                    self.assertEqual(
                        (path,) if owns_bytes and instance in expected and instance.phase == "validation" else (),
                        phase_inventory_paths([path], instance),
                    )

    def test_core_metadata_join_owns_only_core_metadata_bytes(self) -> None:
        path = "ci/products/sdk_platform_metadata.py"
        expected = {PhaseInstanceId("sdk", "sdk-core", "metadata", "common")}
        result = classify_paths([path])
        self.assertEqual(expected, identities(result))
        self.assertEqual((), result.unknown_paths)
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((path,) if instance in expected else (), phase_inventory_paths([path], instance))

    def test_android_original_metadata_replans_only_metadata_without_payload_bytes(self):
        path = "ci/sdk_android_metadata_original.py"
        result = classify_paths([path])
        self.assertEqual({PhaseInstanceId("sdk", "sdk-android", "metadata", "android")}, identities(result))
        self.assertEqual((), result.unknown_paths)
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((), phase_inventory_paths([path], instance))

    def test_metadata_admission_and_carrier_are_control_only(self):
        core = PhaseInstanceId("sdk", "sdk-core", "metadata", "common")
        android = PhaseInstanceId("sdk", "sdk-android", "metadata", "android")
        for path, expected in (
                ("ci/products/sdk_facade_metadata_admission.py", {core}),
                ("ci/products/sdk_android_metadata_admission.py", {android}),
                ("ci/sdk_facade_metadata_policy.py", {core}),
                ("ci/sdk_android_metadata_policy.py", {android}),
                ("ci/sdk_facade_metadata_selection.py", {core}),
                ("ci/sdk_android_metadata_selection.py", {android}),
                ("ci/sdk_metadata_evidence.py", {core, android}),
                ("ci/sdk_metadata_policy.py", {core, android})):
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual(expected, identities(result))
                self.assertEqual((), result.unknown_paths)
                for instance in PHASE_INSTANCE_IDS:
                    self.assertEqual((), phase_inventory_paths([path], instance))

    def test_protected_contract_and_sdk_custody_controls_do_not_change_product_bytes(self):
        contract_metadata = {PhaseInstanceId("contract", "contract", "metadata", "common")}
        runtime_metadata = {PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")}
        sdk = {instance for instance in PHASE_INSTANCE_IDS if instance.product == "sdk"}
        sdk_metadata = {instance for instance in sdk if instance.phase == "metadata"}
        for path, expected in (
                (".github/workflows/contract-phase10-maven.yml", contract_metadata),
                (".github/workflows/contract-phase10-output-record.yml", contract_metadata),
                ("ci/contract_phase10_reuse_admission.py", contract_metadata),
                (".github/workflows/runtime-phase10-maven.yml", runtime_metadata),
                (".github/workflows/runtime-phase10-output-record.yml", runtime_metadata),
                ("ci/runtime_phase10_sidecar_upload.py", runtime_metadata),
                (".github/workflows/sdk-failed-catalog-custody.yml", sdk),
                ("ci/sdk_campaign_release_issuer.py", sdk_metadata),
                ("ci/sdk_catalog_custody.py", sdk),
                ("ci/sdk_catalog_custody_locator.py", sdk),
                ("ci/sdk_catalog_custody_signer.py", sdk)):
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual(expected, identities(result))
                self.assertEqual((), result.unknown_paths)
                for instance in PHASE_INSTANCE_IDS:
                    self.assertEqual((), phase_inventory_paths([path], instance))

    def test_platform_metadata_producers_own_only_their_metadata_phase(self) -> None:
        for path, component, target in (
            ("ci/products/sdk_android_metadata.py", "sdk-android", "android"),
            ("gradle/build-logic/src/main/kotlin/SdkAndroidMetadataTasks.kt", "sdk-android", "android"),
            ("gradle/build-logic/src/main/kotlin/SdkFacadeMetadataTasks.kt", "sdk-core", "common"),
        ):
            with self.subTest(path=path):
                expected = {PhaseInstanceId("sdk", component, "metadata", target)}
                result = classify_paths([path])
                self.assertEqual(expected, identities(result))
                self.assertEqual((), result.unknown_paths)
                for instance in PHASE_INSTANCE_IDS:
                    self.assertEqual((path,) if instance in expected else (), phase_inventory_paths([path], instance))

    def test_maven_executor_selects_only_core_and_android_without_owning_payload_bytes(self):
        path = "ci/sdk_maven_phase.py"
        result = classify_paths([path])
        self.assertEqual({instance for instance in PHASE_INSTANCE_IDS
                          if instance.product == "sdk" and instance.component in {"sdk-core", "sdk-android"}},
                         identities(result))
        self.assertEqual((), result.unknown_paths)
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((), phase_inventory_paths([path], instance))

    def test_platform_controllers_select_only_consumers_without_owning_payload_bytes(self):
        for path, components, phases in (
            ("ci/sdk_facade_metadata_inputs.py", {"sdk-core"}, {"metadata"}),
            ("ci/sdk_facade_metadata_workflow.py", {"sdk-core"}, {"metadata"}),
            ("ci/sdk_facade_metadata_original.py", {"sdk-core"}, {"metadata"}),
            ("ci/sdk_android_metadata_workflow.py", {"sdk-android"}, {"metadata"}),
            ("ci/sdk_maven_binary_workflow.py", {"sdk-core", "sdk-android"}, {"binary", "package", "validation", "metadata"}),
            ("ci/sdk_maven_original.py", {"sdk-core", "sdk-android"}, {"binary", "package", "validation", "metadata"}),
            ("ci/sdk_facade_capture.py", {"sdk-core", "sdk-android"}, {"binary", "package", "validation", "metadata"}),
            ("ci/sdk_maven_package_workflow.py", {"sdk-core", "sdk-android"}, {"package", "validation", "metadata"}),
            ("ci/sdk_android_validation_workflow.py", {"sdk-android"}, {"validation", "metadata"}),
            ("ci/sdk_android_original_validation.py", {"sdk-android"}, {"validation", "metadata"}),
        ):
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual({instance for instance in PHASE_INSTANCE_IDS if instance.product == "sdk"
                                  and instance.component in components and instance.phase in phases}, identities(result))
                self.assertEqual((), result.unknown_paths)
                for instance in PHASE_INSTANCE_IDS:
                    self.assertEqual((), phase_inventory_paths([path], instance))

    def test_android_projections_own_validation_and_metadata_not_compilation(self) -> None:
        path = "ci/products/sdk_android_validation_content.py"
        expected = {PhaseInstanceId("sdk", "sdk-android", phase, "android")
                    for phase in ("validation", "metadata")}
        result = classify_paths([path])
        self.assertEqual(expected, identities(result))
        self.assertEqual((), result.unknown_paths)
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((path,) if instance in expected else (), phase_inventory_paths([path], instance))

    def test_apple_metadata_admission_and_controller_are_control_not_payload_inputs(self) -> None:
        for path in ("ci/products/sdk_apple_metadata_admission.py", "ci/sdk_ios_metadata_workflow.py"):
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual(set(PHASE_INSTANCE_IDS), identities(result))
                self.assertEqual((), result.unknown_paths)
                for instance in PHASE_INSTANCE_IDS:
                    self.assertEqual((), phase_inventory_paths([path], instance))

    def test_scoped_product_actions_select_only_their_existing_consumers(self) -> None:
        owners = {
            "sdk-ios-metadata-worker": {PhaseInstanceId("sdk", "sdk-ios", "metadata", "ios")},
            "prepare-runtime-signing": {item for item in PHASE_INSTANCE_IDS
                if item.product == "runtime" and item.phase == "metadata"
                and item.component in {*NATIVE_TARGETS, "runtime-aggregate"}},
            "provision-sdk-dart-cache": {item for item in PHASE_INSTANCE_IDS
                if item.product == "sdk" and item.component == "dart"
                and item.phase in {"validation", "metadata"}},
            "sdk-ios-package-worker": {item for item in PHASE_INSTANCE_IDS
                if item.product == "sdk" and item.component == "sdk-ios"
                and item.phase in {"package", "validation", "metadata"}},
            "sdk-ios-validation-worker": {item for item in PHASE_INSTANCE_IDS
                if item.product == "sdk" and item.component == "sdk-ios"
                and item.phase in {"validation", "metadata"}},
            "prepare-sdk-apple-signing": {item for item in PHASE_INSTANCE_IDS
                if item.product == "sdk" and item.component == "sdk-ios"
                and item.phase in {"validation", "metadata"}},
            "attest-sdk-apple-validation": {item for item in PHASE_INSTANCE_IDS
                if item.product == "sdk" and item.component == "sdk-ios"
                and item.phase in {"validation", "metadata"}},
            "sdk-javascript-metadata-worker": {item for item in PHASE_INSTANCE_IDS
                if item.product == "sdk" and item.component == "javascript" and item.phase == "metadata"},
        }
        for action, expected in owners.items():
            with self.subTest(action=action):
                self.assertEqual(expected, identities(classify_paths([f".github/actions/{action}/action.yml"])))

    def test_apple_authenticated_tooling_adapter_is_control_only(self) -> None:
        for path in ("ci/products/sdk_apple_content.py", "ci/products/sdk_apple_package_source.py",
                     "ci/products/sdk_apple_validation_source.py",
                     "ci/products/sdk_apple_validation_execution.py",
                     "ci/products/sdk_apple_validation_evidence.py",
                     "ci/products/sdk_apple_device_evidence.py",
                     "ci/products/sdk_apple_toolchain_evidence.py",
                     "ci/products/sdk_apple_simulator_evidence.py",
                     "ci/products/sdk_apple_simulator_replay.py",
                     "ci/products/sdk_apple_original_inputs.py",
                     "ci/products/sdk_apple_package_replay.py",
                     "ci/sdk_ios_original_package.py",
                     "ci/sdk_ios_original_binary.py",
                     "ci/sdk_ios_validation_workflow.py",
                     "ci/sdk_apple_policy.py",
                     "ci/sdk_apple_upload_locator.py",
                     "ci/sdk_apple_worker_capture.py",
                     "ci/products/sdk_apple_package_execution.py",
                     "gradle/build-logic/src/main/kotlin/ApplePackageExecutionEvidence.kt",
                     "gradle/build-logic/src/main/kotlin/AppleOriginalPackageExecution.kt",
                     "gradle/build-logic/src/main/kotlin/ApplePackageExecutionBinding.kt",
                     "gradle/build-logic/src/main/kotlin/AppleOriginalSimulatorExecution.kt",
                     "gradle/build-logic/src/main/kotlin/AppleValidationBindingReplay.kt",
                     "gradle/build-logic/src/main/kotlin/AppleBinaryPackageContent.kt",
                     "gradle/build-logic/src/main/kotlin/AppleBinaryPackageReplay.kt"):
            with self.subTest(path=path):
                result = classify_paths([path])
                self.assertEqual(set(PHASE_INSTANCE_IDS), identities(result))
                self.assertEqual((), result.inventory_paths)
                self.assertEqual((), result.unknown_paths)
                for instance in PHASE_INSTANCE_IDS:
                    self.assertEqual((), phase_inventory_paths([path], instance))

    def test_apple_validation_projection_owns_only_validation_content(self) -> None:
        path = "ci/products/sdk_apple_validation_content.py"
        expected = {item for item in PHASE_INSTANCE_IDS
                    if item.product == "sdk" and item.component == "sdk-ios"
                    and item.phase in {"validation", "metadata"}}
        result = classify_paths([path])
        self.assertEqual(expected, identities(result))
        self.assertEqual((), result.unknown_paths)
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((path,) if instance in expected and instance.phase == "validation" else (),
                             phase_inventory_paths([path], instance))

    def test_pure_apple_package_verifier_selects_no_compilation(self) -> None:
        path = "gradle/build-logic/src/main/kotlin/AppleVerifiedDistributionVerification.kt"
        selected = identities(classify_paths([path]))
        self.assertEqual({item for item in PHASE_INSTANCE_IDS
                          if item.product == "sdk" and item.component == "sdk-ios"
                          and item.phase in {"package", "validation", "metadata"}}, selected)

    def test_fresh_apple_package_stage_selects_no_binary_work(self) -> None:
        path = "gradle/build-logic/src/main/kotlin/AppleBinaryPackageStageTask.kt"
        selected = identities(classify_paths([path]))
        self.assertEqual({item for item in PHASE_INSTANCE_IDS
                          if item.product == "sdk" and item.component == "sdk-ios"
                          and item.phase in {"package", "validation", "metadata"}}, selected)

    def test_shared_capture_owns_adapter_and_native_host_validation_keys(self) -> None:
        self._assert_adapter_host_validation_keys("runtime/build-logic/src/main/kotlin/RuntimeEvidenceExecutionCapture.kt", native=True)

    def test_raw_validator_owns_adapter_and_native_sdk_admission_keys(self) -> None:
        self._assert_adapter_host_validation_keys("ci/products/runtime_adapter_validation.py", sdk=True)

    def test_distribution_manifest_owns_adapter_host_validation_and_existing_binary_keys(self) -> None:
        from ci.tests.test_product_plan import plan
        path = "codex-agent-runtime-desktop/codex-app-server-distributions.json"
        host_validation = {item for item in PHASE_INSTANCE_IDS if item.product == "runtime"
                           and item.component in {"jvm", "node-js", "node-wasm"}
                           and item.phase == "validation" and item.target in NATIVE_TARGETS}
        binary = {PhaseInstanceId("runtime", name, "binary", name) for name in RUNTIME_COMPONENTS}
        owners = binary | host_validation
        self.assertEqual(15, len(host_validation))
        self.assertEqual({item for item in PHASE_INSTANCE_IDS if item.product == "runtime"},
                         identities(classify_paths([path])))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / path
            source.parent.mkdir(parents=True)
            for instance in PHASE_INSTANCE_IDS:
                with self.subTest(instance=instance):
                    # Broad Runtime selection is not direct ownership: package,
                    # native validation, binding validation, metadata and SDK
                    # do not independently read this source through this edge.
                    self.assertEqual((path,) if instance in owners else (),
                                     phase_inventory_paths([path], instance))
                    if instance.product != "runtime":
                        continue
                    keys = []
                    for contents in (b"a", b"b"):
                        source.write_bytes(contents)
                        inventory = phase_file_inventory(root, [path], instance)
                        if instance in owners:
                            self.assertEqual([{"relativePath": path, "bytes": 1, "sha256": sha256_bytes(contents)}],
                                             inventory)
                        else:
                            self.assertEqual([], inventory)
                        # Predecessors remain fixed, isolating this direct input
                        # from legitimate downstream invalidation via artifacts.
                        keys.append(plan(instance, inventory=inventory)["buildKey"])
                    self.assertEqual(instance in owners, keys[0] != keys[1])

    def _assert_adapter_host_validation_keys(self, path: str, *, native: bool = False, sdk: bool = False) -> None:
        from ci.tests.test_product_plan import plan
        owners = {item for item in PHASE_INSTANCE_IDS if item.product == "runtime"
                  and item.component in {"jvm", "node-js", "node-wasm"}
                  and item.phase == "validation" and item.target in NATIVE_TARGETS}
        if native:
            owners |= {PhaseInstanceId("runtime", target, "validation", target) for target in NATIVE_TARGETS}
        if sdk:
            owners |= {item for item in PHASE_INSTANCE_IDS if item.product == "sdk"
                       and item.component in NATIVE_BINDINGS and item.phase in {"package", "validation", "metadata"}}
            owners.add(PhaseInstanceId("runtime", "macos-arm64", "validation", "macos-arm64"))
        selected = owners | {PhaseInstanceId("runtime", name, "metadata", name)
                             for name in ("jvm", "node-js", "node-wasm")}
        selected.add(PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"))
        if native:
            selected |= {PhaseInstanceId("runtime", target, "metadata", target) for target in NATIVE_TARGETS}
        if sdk:
            selected.add(PhaseInstanceId("runtime", "macos-arm64", "metadata", "macos-arm64"))
        self.assertEqual(selected, identities(classify_paths([path])))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / path
            source.parent.mkdir(parents=True)
            for instance in PHASE_INSTANCE_IDS:
                self.assertEqual((path,) if instance in owners else (), phase_inventory_paths([path], instance))
                if instance.product != "runtime":
                    continue
                keys = []
                for contents in (b"a", b"b"):
                    source.write_bytes(contents)
                    keys.append(plan(instance, inventory=phase_file_inventory(root, [path], instance))["buildKey"])
                self.assertEqual(instance in owners, keys[0] != keys[1], instance)

    def test_bootstrap_content_projector_owns_runtime_validation_and_sdk_admission(self) -> None:
        path = "ci/products/sdk_runtime_content.py"
        owner = PhaseInstanceId("runtime", "macos-arm64", "validation", "macos-arm64")
        result = classify_paths([path])
        self.assertIn(owner, result.instances)
        self.assertFalse(any(instance.phase == "binary" for instance in result.instances))
        for instance in PHASE_INSTANCE_IDS:
            owns = instance == owner or (instance.product == "sdk" and instance.component in NATIVE_BINDINGS
                                         and instance.phase in {"package", "validation", "metadata"})
            self.assertEqual((path,) if owns else (), phase_inventory_paths([path], instance), instance)

    def test_runtime_raw_stage_verifier_retains_metadata_and_actual_sdk_owners(self):
        path = "ci/products/runtime_attestation.py"
        expected = {item for item in PHASE_INSTANCE_IDS if (
            item.product == "runtime" and item.component in NATIVE_TARGETS and item.phase == "metadata"
            or item.product == "sdk" and item.phase == "package"
            or item.product == "sdk" and item.component in NATIVE_BINDINGS and item.phase in {"validation", "metadata"}
        )}
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((path,) if instance in expected else (), phase_inventory_paths([path], instance), instance)
        self.assertFalse(any(instance.phase == "binary" for instance in classify_paths([path]).instances))

    def test_imported_runtime_variant_task_owns_only_native_metadata(self) -> None:
        from ci.tests.test_product_plan import plan

        path = "runtime/build-logic/src/main/kotlin/ImportedRuntimeVariantTask.kt"
        owners = {PhaseInstanceId("runtime", target, "metadata", target) for target in NATIVE_TARGETS}
        selected = owners | {PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")}
        self.assertEqual(selected, identities(classify_paths([path])))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / path
            source.parent.mkdir(parents=True)
            for instance in PHASE_INSTANCE_IDS:
                self.assertEqual((path,) if instance in owners else (), phase_inventory_paths([path], instance))
                if instance.product == "runtime":
                    keys = []
                    for content in (b"a", b"b"):
                        source.write_bytes(content)
                        keys.append(plan(instance, inventory=phase_file_inventory(root, [path], instance))["buildKey"])
                    self.assertEqual(instance in owners, keys[0] != keys[1], instance)

    def test_root_build_scripts_do_not_enter_standalone_runtime_keys(self) -> None:
        from ci.tests.test_product_plan import plan, upstreams

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in ("gradle/build-logic/build.gradle.kts", "gradle/build-logic/settings.gradle.kts",
                         "gradle/libs.versions.toml", "gradle/wrapper/gradle-wrapper.properties"):
                source = root / path
                source.parent.mkdir(parents=True, exist_ok=True)
                self.assertEqual(set(PHASE_INSTANCE_IDS), identities(classify_paths([path])))
                for instance in PHASE_INSTANCE_IDS:
                    owned = (instance.phase == "binary" or
                             (instance.product == "sdk" and instance.component in (*NATIVE_BINDINGS, "javascript")
                              and instance.phase == "package"))
                    if instance.product == "runtime":
                        owned = instance.phase == "binary" and not path.startswith("gradle/build-logic/")
                    if (path == "gradle/build-logic/build.gradle.kts" and instance.product == "sdk"
                            and instance.component in NATIVE_BINDINGS and instance.phase in {"validation", "metadata"}):
                        owned = True
                    self.assertEqual((path,) if owned else (), phase_inventory_paths([path], instance),
                                     (path, instance))
                    if not owned and not (instance.product == "runtime" and instance.phase == "binary"):
                        continue
                    parents = upstreams(instance)
                    if instance.product == "sdk" and instance.component in NATIVE_BINDINGS and instance.phase == "validation":
                        # Match the existing strict embedded-Runtime lineage; a bare fixture
                        # package receipt intentionally has no upstreams and cannot prove it.
                        package = next(value for value in parents if value["product"] == "sdk")
                        package_plan = plan(PhaseInstanceId("sdk", instance.component, "package", "desktop"))
                        package.update(inputs=package_plan["inputs"], buildKey=package_plan["buildKey"])
                    keys = []
                    for content in (b"a", b"b"):
                        source.write_bytes(content)
                        keys.append(plan(instance, upstream_receipts=parents,
                                         inventory=phase_file_inventory(root, [path], instance))["buildKey"])
                    self.assertEqual(owned, keys[0] != keys[1], (path, instance))

    def test_contract_coverage_producers_select_evidence_consumers_without_runtime_compilation(self):
        paths = ("codex-agent-core/src/commonTest/kotlin/ContractTest.kt",
                 "codex-agent-core/src/jvmTest/java/ContractTest.java",
                 "ci/products/contract.py", "ci/products/contract_model.py",
                 "gradle/build-logic/src/main/kotlin/CrossLanguageApiCoverage.kt")
        for path in paths:
            with self.subTest(path=path):
                selected = classify_paths([path])
                self.assertIn(PhaseInstanceId("runtime", "macos-arm64", "validation", "macos-arm64"), selected.instances)
                self.assertIn(PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"), selected.instances)
                self.assertFalse(any(item.product == "runtime" and item.phase in {"binary", "package"}
                                     for item in selected.instances))
                self.assertEqual({"macos-arm64"}, {item.component for item in selected.instances
                    if item.product == "runtime" and item.phase == "validation"})
                for language in NATIVE_BINDINGS:
                    self.assertIn(PhaseInstanceId("sdk", language, "package", "desktop"), selected.instances)
                self.assertEqual((path,) if path == "ci/products/contract_model.py" else (), phase_inventory_paths([path], PhaseInstanceId(
                    "runtime", "macos-arm64", "validation", "macos-arm64")))

    def test_bootstrap_shared_parsers_enter_actual_package_and_validation_keys(self):
        from ci.tests.test_product_plan import plan, receipt, upstreams

        owners = [PhaseInstanceId("runtime", "macos-arm64", "validation", "macos-arm64")] + [
            item for item in PHASE_INSTANCE_IDS if item.product == "sdk"
            and item.component in NATIVE_BINDINGS and item.phase in {"package", "validation"}
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in ("ci/products/contract_model.py", "ci/products/inventory.py", "ci/products/test_results.py"):
                source = root / path
                source.parent.mkdir(parents=True, exist_ok=True)
                for owner in owners:
                    self.assertEqual((path,), phase_inventory_paths([path], owner), (path, owner))
                    predecessors = upstreams(owner)
                    if owner.product == "sdk" and owner.phase == "validation":
                        package = PhaseInstanceId("sdk", owner.component, "package", "desktop")
                        package_plan = plan(package)
                        package_receipt = receipt(package)
                        package_receipt.update(inputs=package_plan["inputs"], buildKey=package_plan["buildKey"])
                        predecessors = [package_receipt if value["product"] == "sdk" else value for value in predecessors]
                    keys = []
                    for data in (b"original", b"changed shared validation helper"):
                        source.write_bytes(data)
                        keys.append(plan(owner, upstream_receipts=predecessors,
                                         inventory=phase_file_inventory(root, [path], owner))["buildKey"])
                    self.assertNotEqual(*keys, (path, owner))
                for target in NATIVE_TARGETS:
                    self.assertEqual((), phase_inventory_paths([path], PhaseInstanceId("runtime", target, "binary", target)))

    def test_native_installed_consumer_and_policy_helpers_are_direct_validation_inputs(self) -> None:
        from ci.tests.test_product_plan import plan, receipt, upstreams

        instances = [item for item in PHASE_INSTANCE_IDS if item.product == "sdk" and
                     item.component in NATIVE_BINDINGS and item.phase == "validation"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in ("ci/native_wrappers.py", "ci/products/aggregate.py", "ci/products/inventory.py"):
                source = root / path
                source.parent.mkdir(parents=True, exist_ok=True)
                for instance in instances:
                    self.assertEqual((path,), phase_inventory_paths([path], instance))
                    package = PhaseInstanceId("sdk", instance.component, "package", "desktop")
                    package_plan = plan(package)
                    package_receipt = receipt(package)
                    package_receipt.update(inputs=package_plan["inputs"], buildKey=package_plan["buildKey"])
                    predecessors = [package_receipt if value["product"] == "sdk" else value
                                    for value in upstreams(instance)]
                    keys = []
                    for content in (b"a", b"b"):
                        source.write_bytes(content)
                        keys.append(plan(instance, upstream_receipts=predecessors,
                                         inventory=phase_file_inventory(root, [path], instance))["buildKey"])
                    self.assertNotEqual(*keys)
                for language in NATIVE_BINDINGS:
                    package = PhaseInstanceId("sdk", language, "package", "desktop")
                self.assertEqual((path,) if path in {"ci/native_wrappers.py", "ci/products/inventory.py"} else (),
                                     phase_inventory_paths([path], package))

    def test_node_binding_validator_key_owns_execution_and_shared_copy_without_recompiling(self) -> None:
        from ci.tests.test_product_plan import plan

        validation = PhaseInstanceId("runtime", "node-js", "validation", "node-js-binding")
        binary = PhaseInstanceId("runtime", "node-js", "binary", "node-js")
        package = PhaseInstanceId("runtime", "node-js", "package", "node-js")
        execution = "runtime/build-logic/src/main/kotlin/NodeBindingValidationExecution.kt"
        shared = "runtime/build-logic/src/main/kotlin/NodeBindingValidationTask.kt"
        self.assertEqual(
            {validation, PhaseInstanceId("runtime", "node-js", "metadata", "node-js"),
             PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")},
            identities(classify_paths([execution])),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in (execution, shared, "runtime/build-logic/src/main/kotlin/DesktopRuntimeZipModes.kt"):
                source = root / path
                source.parent.mkdir(parents=True, exist_ok=True)
                for instance in (validation, binary, package):
                    keys = []
                    for content in (b"a", b"b"):
                        source.write_bytes(content)
                        keys.append(plan(instance, inventory=phase_file_inventory(root, [path], instance))["buildKey"])
                    self.assertEqual(instance == validation or (path == shared and instance == binary),
                                     keys[0] != keys[1], (path, instance))

    def test_imported_c_abi_bootstrap_hashes_its_executed_validation_helpers(self) -> None:
        from ci.tests.test_product_plan import plan

        validation = PhaseInstanceId("runtime", "macos-arm64", "validation", "macos-arm64")
        helper = "runtime/build-logic/src/main/kotlin/ImportedCAbiBootstrapTasks.kt"
        self.assertEqual({validation, PhaseInstanceId("runtime", "macos-arm64", "metadata", "macos-arm64"),
                          PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")},
                         identities(classify_paths([helper])))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("ImportedCAbiBootstrapTasks.kt", "RuntimeCAbiClient.kt",
                         "RuntimeAdapterMetadataInputsTask.kt", "CrossLanguageCAbiRuntimeProduction.kt"):
                path = f"runtime/build-logic/src/main/kotlin/{name}"
                self.assertEqual((path,), phase_inventory_paths([path], validation))
                source = root / path
                source.parent.mkdir(parents=True, exist_ok=True)
                keys = []
                for content in (b"a", b"b"):
                    source.write_bytes(content)
                    keys.append(plan(validation, inventory=phase_file_inventory(root, [path], validation))["buildKey"])
                self.assertNotEqual(*keys)
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((helper,) if instance == validation else (), phase_inventory_paths([helper], instance))

    def test_runtime_compiled_runner_and_distribution_inputs_change_exact_binary_keys(self) -> None:
        from ci.tests.test_product_plan import plan

        runners = {*NATIVE_TARGETS, "jvm", "node-js"}
        cases = {
            "codex-agent-runtime-desktop/src/jvmTest/kotlin/Runner.kt": {"jvm"},
            "codex-agent-runtime-desktop/src/nativeTest/kotlin/Runner.kt": set(NATIVE_TARGETS),
            "codex-agent-runtime-desktop/src/commonTest/kotlin/Runner.kt": runners,
            "codex-agent-runtime-desktop/src/desktopTest/kotlin/Runner.kt": {*NATIVE_TARGETS, "jvm"},
            "codex-agent-runtime-desktop/src/jsTest/kotlin/Runner.kt": {"node-js"},
            "codex-agent-runtime-desktop/src/webTest/kotlin/Runner.kt": {"node-js"},
            "codex-agent-runtime-desktop/src/wasmJsTest/kotlin/Runner.kt": set(),
            "runtime/build-logic/src/main/kotlin/JvmRuntimeEvidenceExecution.kt": set(),
            "runtime/build-logic/src/main/kotlin/NodeRuntimeEvidenceExecution.kt": set(),
            "runtime/build-logic/src/main/kotlin/DesktopRuntimeEvidenceTasks.kt": set(),
            "runtime/build-logic/src/main/kotlin/GenerateDesktopDistributionSourceTask.kt": set(RUNTIME_COMPONENTS),
            "runtime/build-logic/src/main/kotlin/DesktopRuntimeModel.kt": set(RUNTIME_COMPONENTS),
            "codex-agent-runtime-desktop/codex-app-server-distributions.json": set(RUNTIME_COMPONENTS),
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for path, owners in cases.items():
                with self.subTest(path=path):
                    selected = classify_paths([path])
                    self.assertEqual(owners, {item.component for item in selected.instances
                                              if item.product == "runtime" and item.phase == "binary"})
                    self.assertFalse(any(item.product == "sdk" for item in selected.instances))
                    source = root / path
                    source.parent.mkdir(parents=True, exist_ok=True)
                    for runtime in RUNTIME_COMPONENTS:
                        instance = PhaseInstanceId("runtime", runtime, "binary", runtime)
                        keys = []
                        for content in (b"a", b"b"):
                            source.write_bytes(content)
                            keys.append(plan(instance, inventory=phase_file_inventory(root, [path], instance))["buildKey"])
                        self.assertEqual(runtime in owners, keys[0] != keys[1], (path, runtime))

    def test_contract_binary_owns_its_actual_evidence_producers_and_tests(self) -> None:
        paths = [
            *(f"ci/products/{name}.py" for name in (
                "__init__", "__main__", "contract", "contract_model", "inventory", "receipt", "test_results",
            )),
            *(f"ci/lanes/contract-product.{kind}.pathspec" for kind in ("production", "test")),
            *(f"gradle/build-logic/src/main/kotlin/{name}" for name in (
                "CanonicalTestResultsClient.kt", "CrossLanguageApiCoverage.kt",
                "CrossLanguageApiDiscovery.kt", "CrossLanguageApiDiscoveryCli.kt",
                "CrossLanguageApiEvidence.kt", "CrossLanguageApiReportCodec.kt", "CrossLanguageApiTasks.kt",
                "CrossLanguageBindingParity.kt", "CrossLanguageBindingReceipt.kt", "CrossLanguageBindingTasks.kt",
                "CrossLanguageKotlinBindingEvidence.kt", "ReleaseIo.kt", "VerifyProtocolSourceTask.kt",
                "codexagent.contract-product.gradle.kts", "codexagent.core-verification.gradle.kts",
                "codexagent.root-release.gradle.kts",
            )),
            "codex-agent-core/src/commonTest/kotlin/example/ContractTest.kt",
            "codex-agent-core/src/jvmTest/java/example/ContractTest.java",
        ]
        instance = PhaseInstanceId("contract", "contract", "binary", "common")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for path in paths:
                with self.subTest(path=path):
                    selected = classify_paths([path])
                    self.assertIn(instance, selected.instances)
                    self.assertEqual((path,), phase_inventory_paths([path], instance))
                    self.assertFalse(any(item.product == "runtime" and item.phase == "binary"
                                         for item in selected.instances))
                    source = root / path
                    source.parent.mkdir(parents=True, exist_ok=True)
                    keys = []
                    for content in (b"a", b"b"):
                        source.write_bytes(content)
                        keys.append(plan_phase(
                            instance, inventory=phase_file_inventory(root, [path], instance),
                            versions={name: "0.2.0" for name in
                                      ("contract", "runtime-release", "runtime-compatibility", "sdk")},
                            upstream_receipts=[], toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                            flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1,
                        )["buildKey"])
                    self.assertNotEqual(*keys)
        for path in (
            "ci/products/signatures.py",
            "ci/tests/test_contract_bundle.py", "README.md",
            "gradle/build-logic/src/test/kotlin/ContractIsolationFixtureTest.kt",
            "gradle/build-logic/src/main/kotlin/CrossLanguageNativeWrapperBindingEvidence.kt",
            "codex-agent-bindings/python/src/codex_agent/_ffi.py",
        ):
            with self.subTest(unrelated=path):
                self.assertNotIn(instance, classify_paths([path]).instances)
                self.assertEqual((), phase_inventory_paths([path], instance))
        # Control changes can request broad reuse planning, but cannot change payload keys.
        for path in ("ci/products/contract_attestation.py", "ci/products/contract_projection.py",
                     "ci/products/reuse.py", "ci/products/native_runtime_inputs.py", "ci/products/selection.py"):
            self.assertEqual((), phase_inventory_paths([path], instance))

    def test_embedded_contract_git_inventories_are_a_subset_of_binary_key_inputs(self) -> None:
        root = Path(__file__).resolve().parents[2]
        tracked = tracked_product_paths()
        embedded = set()
        for kind in ("production", "test"):
            policy = f"ci/lanes/contract-product.{kind}.pathspec"
            patterns = (root / policy).read_text().splitlines()
            self.assertEqual(sorted(set(patterns)), patterns)
            self.assertIn(policy, patterns)
            embedded.update(path for path in tracked if any(fnmatch.fnmatchcase(path, pattern)
                                                           for pattern in patterns))
        self.assertGreater(len(embedded), 100)
        binary = PhaseInstanceId("contract", "contract", "binary", "common")
        self.assertEqual(set(), embedded - set(phase_inventory_paths(tracked, binary)))
        self.assertFalse(any(path.startswith(("ci/tests/", "gradle/build-logic/src/test/"))
                             for path in embedded))
        self.assertNotIn("ci/products/signatures.py", embedded)
        self.assertNotIn("ci/products/c_abi.py", embedded)

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

    def test_sdk_compatibility_policy_selects_the_same_packages_as_default_runtime(self) -> None:
        self.assertEqual(
            identities(classify_paths(["gradle/release/sdk-default-runtime.txt"])),
            identities(classify_paths(["gradle/release/sdk-runtime-compatibility.json"])),
        )

    def test_sdk_root_rotation_selects_only_native_sdk_packages(self) -> None:
        selected = identities(classify_paths(["gradle/release/keys/sdk-runtime-root.pub"]))
        self.assertEqual(set(NATIVE_BINDINGS), {item.component for item in selected})
        self.assertTrue(all(item.product == "sdk" and item.phase != "binary" for item in selected))

    def test_csharp_root_inspector_changes_only_csharp_validation(self) -> None:
        selected = identities(classify_paths([
            "codex-agent-bindings/csharp/tools/VerifySdkRuntimeRoot/Program.cs",
        ]))
        self.assertEqual({"csharp"}, {item.component for item in selected})
        self.assertEqual({"validation", "metadata"}, {item.phase for item in selected})

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

    def test_native_staging_helpers_select_packages_but_proof_matchers_only_validation(self) -> None:
        for name in (
            "CrossLanguageNativeWrapperSdkStaging.kt",
            "CrossLanguageNativeWrapperGradleTasks.kt",
            "CrossLanguageCAbiClient.kt",
            "CrossLanguageNativeWrapperBindingEvidence.kt",
            "CrossLanguageNativeWrapperValidationEvidence.kt",
            "NativeWrapperInstalledConsumerTask.kt",
            "NativeWrapperCapabilityEvidenceTask.kt",
        ):
            with self.subTest(name=name):
                selected = identities(classify_paths([f"gradle/build-logic/src/main/kotlin/{name}"]))
                self.assertEqual({"sdk"}, {instance.product for instance in selected})
                self.assertEqual(set(NATIVE_BINDINGS), {instance.component for instance in selected})
                phases = {"validation", "metadata"}
                if name not in {"CrossLanguageNativeWrapperBindingEvidence.kt", "CrossLanguageNativeWrapperValidationEvidence.kt",
                                "NativeWrapperInstalledConsumerTask.kt",
                                "NativeWrapperCapabilityEvidenceTask.kt"}:
                    phases.add("package")
                for binding in NATIVE_BINDINGS:
                    self.assertEqual(phases, {instance.phase for instance in selected
                                              if instance.component == binding})
                if name in {"NativeWrapperCapabilityEvidenceTask.kt", "CrossLanguageNativeWrapperValidationEvidence.kt"}:
                    path = f"gradle/build-logic/src/main/kotlin/{name}"
                    for instance in PHASE_INSTANCE_IDS:
                        owns = (instance.product == "sdk" and instance.component in NATIVE_BINDINGS
                                and (instance.phase == "validation" or
                                     name == "CrossLanguageNativeWrapperValidationEvidence.kt" and instance.phase == "metadata"))
                        self.assertEqual((path,) if owns else (), phase_inventory_paths([path], instance))

    def test_current_runtime_version_does_not_select_mobile_sdk_products(self) -> None:
        selected = identities(classify_paths(["gradle/release/versions/runtime.txt"]))
        self.assertEqual(
            {PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")},
            selected,
        )
        self.assertFalse(any(instance.product == "sdk" for instance in selected))

    def test_imported_apple_contract_evidence_selects_only_ios_validation(self) -> None:
        selected = identities(classify_paths([
            "gradle/build-logic/src/main/kotlin/IosImportedContractEvidenceTasks.kt",
        ]))
        self.assertEqual(
            {item for item in PHASE_INSTANCE_IDS if item.product == "sdk" and
             item.component == "sdk-ios" and item.phase in {"validation", "metadata"}},
            selected,
        )

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

    def test_shared_native_compiled_runner_change_selects_binary_and_successors(self) -> None:
        result = classify_paths([
            "codex-agent-runtime-desktop/src/nativeTest/kotlin/example/RuntimeValidationTest.kt"
        ])
        selected = identities(result)
        for target in NATIVE_TARGETS:
            self.assertEqual({"binary", "package", "validation", "metadata"}, {
                instance.phase for instance in component(result, "runtime", target)
            })
        self.assertIn(PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"), selected)
        self.assertFalse(any(instance.component in {"jvm", "node-js", "node-wasm"} for instance in selected))
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

    def test_jvm_contract_change_selects_jvm_binary_and_coverage_evidence_consumers(self) -> None:
        result = classify_paths([
            "codex-agent-core/src/jvmMain/kotlin/example/JvmProjection.kt"
        ])
        self.assertEqual({"binary", "package", "validation", "metadata"}, {
            instance.phase for instance in component(result, "contract", "contract")
        })
        self.assertTrue(component(result, "runtime", "jvm"))
        self.assertEqual({"package", "validation", "metadata"}, {
            instance.phase for instance in component(result, "sdk", "sdk-core")
        })
        self.assertIn(PhaseInstanceId("sdk", "sdk-core", "validation", "jvm"), result.instances)
        self.assertFalse(component(result, "runtime", "node-js"))
        self.assertEqual({"jvm"}, {item.component for item in result.instances
                                  if item.product == "runtime" and item.phase in {"binary", "package"}})
        self.assertIn(PhaseInstanceId("runtime", "macos-arm64", "validation", "macos-arm64"), result.instances)

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

    def test_app_server_identity_selects_all_runtimes_embedding_distribution_table(self) -> None:
        result = classify_paths(["codex-agent-runtime-desktop/codex-app-server-distributions.json"])
        for target in RUNTIME_COMPONENTS:
            self.assertTrue(component(result, "runtime", target))
        self.assertFalse(any(instance.product == "sdk" for instance in result.instances))

    def test_metadata_policy_retains_metadata_and_executed_native_policy_owners(self) -> None:
        for path in (
            "ci/products/aggregate.py",
            "ci/products/index.py",
            "ci/products/signatures.py",
            "gradle/build-logic/src/main/kotlin/PromotedCandidateTasks.kt",
            "gradle/release/product-signing-keys.json",
        ):
            with self.subTest(path=path):
                result = classify_paths([path])
                expected = set(ALL_METADATA)
                if path == "ci/products/aggregate.py":
                    expected.update(item for item in PHASE_INSTANCE_IDS if item.product == "sdk" and
                                    item.component in NATIVE_BINDINGS and item.phase == "validation")
                self.assertEqual(expected, identities(result))
                self.assertFalse(any(instance.phase in {"binary", "package"} for instance in result.instances))
                self.assertFalse(result.unknown_paths)
                self.assertTrue(result.reuse_allowed)

    def test_shared_toolchain_authority_selects_exact_native_binary_lines(self) -> None:
        for path in ("ci/products/toolchain.py", ".github/workflows/runtime-toolchain-capture.yml"):
            with self.subTest(path=path):
                result = classify_paths([path])
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
            "runtime/build-logic/src/main/kotlin/RuntimeBinaryFlags.kt",
        ):
            with self.subTest(path=path):
                result = classify_paths([path])
                for target in NATIVE_TARGETS:
                    instance = PhaseInstanceId("runtime", target, "binary", target)
                    self.assertIn(instance, result.instances)
                    inventory = phase_inventory_paths(set(paths) | {path}, instance)
                    if path.endswith(("runtime_flags.py", "RuntimeBinaryFlags.kt")):
                        self.assertIn(path, inventory)
                    else:
                        self.assertNotIn(path, inventory)
                self.assertFalse(component(result, "runtime", "jvm"))
                self.assertFalse(component(result, "runtime", "node-js"))
                self.assertFalse(any(instance.product == "sdk" for instance in result.instances))
                for adapter in ("jvm", "node-js", "node-wasm"):
                    self.assertNotIn(
                        path,
                        phase_inventory_paths(
                            set(paths) | {path},
                            PhaseInstanceId("runtime", adapter, "binary", adapter),
                        ),
                    )

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
            (paths[2], paths[3]),
            phase_inventory_paths(paths, PhaseInstanceId("runtime", "jvm", "binary", "jvm")),
        )
        self.assertEqual(
            (),  # Compiled test inputs are represented by the upstream binary digest.
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
                {*NATIVE_TARGETS, "runtime-aggregate"}, {"validation", "metadata"},
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

    def test_raw_producers_are_validation_only_and_native_test_sources_have_both_owners(self) -> None:
        for language in NATIVE_BINDINGS:
            directory = "tool" if language == "dart" else "tools"
            producer = f"codex-agent-bindings/{language}/{directory}/produce_sdk_validation_evidence.py"
            expected = {item for item in PHASE_INSTANCE_IDS if item.product == "sdk" and
                        item.component == language and item.phase in {"validation", "metadata"}}
            self.assertEqual(expected, identities(classify_paths([producer])))
            for instance in PHASE_INSTANCE_IDS:
                if instance in expected and instance.phase == "validation":
                    self.assertEqual((producer,), phase_inventory_paths([producer], instance))
                else:
                    self.assertEqual((), phase_inventory_paths([producer], instance))
        for language in NATIVE_BINDINGS:
            path = f"codex-agent-bindings/{language}/tests/fixture.py"
            for instance in PHASE_INSTANCE_IDS:
                if instance.product == "sdk" and instance.component == language and instance.phase in {"package", "validation"}:
                    self.assertEqual((path,), phase_inventory_paths([path], instance))

    def test_cpp_imported_package_verifier_is_a_direct_validation_and_metadata_input(self) -> None:
        path = "codex-agent-bindings/cpp/tools/verify_imported_package.py"
        expected = {item for item in PHASE_INSTANCE_IDS if item.product == "sdk" and
                    item.component == "cpp" and item.phase in {"validation", "metadata"}}
        self.assertEqual(expected, identities(classify_paths([path])))
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual(
                (path,) if instance in expected else (),
                phase_inventory_paths([path], instance),
            )

    def test_raw_verifier_cli_and_digest_helper_directly_own_native_validation(self) -> None:
        for name in ("ReleaseToolingCli.kt", "ReleaseIo.kt"):
            path = f"gradle/build-logic/src/main/kotlin/{name}"
            selected = identities(classify_paths([path]))
            validation = {instance for instance in PHASE_INSTANCE_IDS if instance.product == "sdk" and
                          instance.component in NATIVE_BINDINGS and instance.phase == "validation"}
            self.assertTrue(validation.issubset(selected))
            for instance in validation:
                self.assertEqual((path,), phase_inventory_paths([path], instance))
            self.assertFalse(any(item.product == "runtime" and item.phase in {"binary", "package"} for item in selected))
            self.assertEqual({"macos-arm64"} if name == "ReleaseIo.kt" else set(), {
                item.component for item in selected if item.product == "runtime" and item.phase == "validation"})

    def test_cpp_configure_and_generated_dispatch_check_are_direct_validation_inputs(self) -> None:
        for path in ("codex-agent-bindings/cpp/CMakeLists.txt",
                     "codex-agent-bindings/cpp/tools/generate_native_dispatch.py"):
            selected = identities(classify_paths([path]))
            expected = {instance for instance in PHASE_INSTANCE_IDS if instance.product == "sdk" and
                        instance.component == "cpp" and instance.phase in {"package", "validation", "metadata"}}
            self.assertEqual(expected, selected)
            for instance in expected:
                if instance.phase in {"package", "validation"}:
                    self.assertEqual((path,), phase_inventory_paths([path], instance))

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
        self.assertEqual(set(RUNTIME_COMPONENTS) | {"runtime-aggregate"}, {
            instance.component for instance in result.instances
        })
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
            set(NATIVE_TARGETS) | {"runtime-aggregate", "sdk-core", "sdk-android", "sdk-ios", *NATIVE_BINDINGS, "javascript"},
            {instance.component for instance in runtime.instances},
        )
        self.assertTrue(all(
            instance.phase == "metadata" if instance.product == "runtime"
            else instance.phase in {"package", "validation", "metadata"}
            for instance in runtime.instances
        ))

        aggregate = classify_paths(["ci/products/runtime_aggregate.py"])
        translated = classify_paths(["ci/runtime_aggregate_phase.py"])
        aggregate_phase = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        self.assertEqual((aggregate_phase,), translated.instances)
        self.assertEqual(("ci/runtime_aggregate_phase.py",), phase_inventory_paths(
            ["ci/runtime_aggregate_phase.py"], aggregate_phase))
        self.assertEqual((), phase_inventory_paths(["ci/runtime_aggregate_phase.py"],
            PhaseInstanceId("runtime", "linux-arm64", "binary", "linux-arm64")))
        self.assertEqual(
            {("runtime", "runtime-aggregate", "metadata", "aggregate")} |
            {("sdk", language, "metadata", "desktop") for language in NATIVE_BINDINGS},
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

        root = classify_paths(["ci/products/sdk_runtime_root.py"])
        self.assertEqual(set(NATIVE_BINDINGS), {instance.component for instance in root.instances})
        self.assertTrue(all(instance.product == "sdk" and instance.phase in {
            "package", "validation", "metadata",
        } for instance in root.instances))

    def test_sdk_package_and_runtime_identity_tools_have_exact_product_owners(self) -> None:
        maven = classify_paths(["ci/products/sdk_maven.py"])
        self.assertEqual(
            {"sdk-core", "sdk-android", "sdk-ios", "runtime-aggregate", *NATIVE_BINDINGS},
            {instance.component for instance in maven.instances},
        )
        self.assertTrue(all(instance.product == "sdk" or
                            (instance.component == "runtime-aggregate" and instance.phase == "metadata")
                            for instance in maven.instances))
        self.assertEqual({"binary", "package", "validation", "metadata"}, {instance.phase for instance in maven.instances})
        paths = (
            "ci/products/sdk_maven.py",
            "gradle/build-logic/src/main/kotlin/MavenRepositoryTasks.kt",
            "gradle/build-logic/src/main/kotlin/codexagent.contract-product.gradle.kts",
        )
        for name in ("sdk-core", "sdk-android", "sdk-ios"):
            binary = next(instance for instance in PHASE_INSTANCE_IDS
                          if instance.product == "sdk" and instance.component == name and instance.phase == "binary")
            self.assertEqual(tuple(sorted(paths)), phase_inventory_paths(paths, binary))
        for path in paths:
            selected = classify_paths([path]).instances
            self.assertFalse(any(instance.product == "runtime" and instance.phase == "binary" for instance in selected))
        sdk_script = classify_paths([
            "gradle/build-logic/src/main/kotlin/codexagent.sdk-product.gradle.kts",
        ]).instances
        self.assertEqual({"sdk-core", "sdk-android", "sdk-ios"},
                         {instance.component for instance in sdk_script})
        self.assertTrue(all(instance.product == "sdk" for instance in sdk_script))
        self.assertEqual({"binary", "package", "validation", "metadata"},
                         {instance.phase for instance in sdk_script})
        capture_path = "ci/sdk_core_context_preparation_capture.py"
        self.assertEqual({("sdk", "sdk-core", "metadata")},
                         {(instance.product, instance.component, instance.phase)
                          for instance in classify_paths([capture_path]).instances})
        self.assertEqual((), phase_inventory_paths([capture_path],
            PhaseInstanceId("sdk", "sdk-core", "metadata", "common")))

        archive = classify_paths(["ci/products/sdk_archive.py"])
        self.assertEqual({"sdk-core", "sdk-android", "sdk-ios", "javascript"},
                         {instance.component for instance in archive.instances})
        self.assertTrue(all(instance.product == "sdk" for instance in archive.instances))
        self.assertTrue(all(instance.phase in {"package", "validation", "metadata"} for instance in archive.instances))
        shared_packages = classify_paths([
            "gradle/build-logic/src/main/kotlin/codexagent.native-wrapper-sdk.gradle.kts",
        ])
        self.assertEqual({"sdk-core", "sdk-android", "sdk-ios", *NATIVE_BINDINGS},
                         {instance.component for instance in shared_packages.instances})
        self.assertTrue(all(instance.product == "sdk" and instance.phase != "binary"
                            for instance in shared_packages.instances))

        gradle = classify_paths([
            "gradle/build-logic/src/main/kotlin/SdkMavenPackageTask.kt",
        ])
        self.assertEqual(
            {"sdk-core", "sdk-android", "sdk-ios", "javascript"},
            {instance.component for instance in gradle.instances},
        )
        self.assertTrue(all(instance.product == "sdk" for instance in gradle.instances))
        self.assertTrue(all(instance.phase in {"package", "validation", "metadata"} for instance in gradle.instances))

        runtime = classify_paths([
            "runtime/build-logic/src/main/kotlin/GenerateRuntimeAbiSourceTask.kt",
        ])
        self.assertEqual(
            set(NATIVE_TARGETS) | {"runtime-aggregate"},
            {instance.component for instance in runtime.instances},
        )
        self.assertTrue(all(instance.product == "runtime" for instance in runtime.instances))
        self.assertEqual(
            set(NATIVE_TARGETS),
            {instance.component for instance in runtime.instances if instance.phase == "binary"},
        )
        self.assertFalse(any(instance.product == "sdk" for instance in runtime.instances))

    def test_javascript_metadata_replay_keys_only_its_metadata_phase(self):
        selected = classify_paths([
            "gradle/build-logic/src/main/kotlin/CrossLanguageJavaScriptMetadataEvidence.kt",
            "gradle/build-logic/src/main/kotlin/CrossLanguageJavaScriptStagedMetadata.kt",
        ])
        self.assertEqual(
            {PhaseInstanceId("sdk", "javascript", "metadata", "node")},
            set(selected.instances),
        )

    def test_current_untracked_product_authorities_are_explicit_controls(self) -> None:
        paths = (
            "ci/sdk_completion.py",
            "ci/sdk_completion_state.py",
            "ci/products/sdk_apple_framework.py",
            "ci/legacy_lanes.py",
            "ci/product_legacy.py",
            "ci/product_reuse.py",
            "ci/runtime_native_phase.py",
            "ci/runtime_original_ci.py",
            "ci/runtime_aggregate_release.py",
            "ci/products/runtime_aggregate_handoff.py",
            "ci/products/runtime_aggregate_inputs.py",
            "ci/products/runtime_variant_handoff.py",
            "ci/products/runtime_variant_trust.py",
            "ci/products/sdk_release_selection.py",
            "ci/sdk_apple_source.py",
            "ci/products/sdk_native_metadata.py",
            "ci/products/sdk_javascript_metadata.py",
            "ci/products/sdk_javascript_metadata_admission.py",
            "ci/products/sdk_native_metadata_admission.py",
            "ci/products/runtime_sdk_handoff.py",
            "ci/products/sdk_inputs_verification.py",
            "ci/products/sdk_protected_runtime.py",
            "ci/sdk_handoff.py",
            "ci/sdk_workflow.py",
            "ci/runtime_catalog_promotion.py",
            "gradle/build-logic/src/main/kotlin/AppleOriginalExecutionVerification.kt",
            "ci/runtime_adapter_phase.py",
            "ci/runtime_supervisor.py",
            "ci/runtime_workflow.py",
            "ci/sdk_phase.py",
            "ci/sdk_ios_phase.py",
            "ci/sdk_ios_package.py",
            "ci/sdk_ios_package_workflow.py",
            "ci/sdk_ios_binary.py",
            "ci/sdk_metadata_phase.py",
            "ci/sdk_javascript_phase.py",
            "ci/sdk_native_phase.py",
            "ci/sdk_native_package_workflow.py",
            "ci/sdk_javascript_metadata_phase.py",
            "ci/sdk_javascript_metadata_workflow.py",
            "ci/sdk_native_prepare.py",
            "ci/sdk_apple_export.py",
            "ci/sdk_apple_native.py",
            "ci/products/sdk_apple_source.py",
            "ci/contract_release.py",
            "ci/product_release_context.py",
            "ci/runtime_release.py",
            "ci/products/contract_projection.py",
            "ci/products/plan.py",
            "ci/products/registry.py",
            "ci/products/restore.py",
            "ci/products/reuse.py",
            "ci/products/native_runtime_inputs.py",
            "ci/products/runtime_adapter_content.py",
            "ci/products/adapter_runtime_inputs.py",
            "ci/products/selection.py",
        )
        result = classify_paths(paths)
        self.assertEqual(set(PHASE_INSTANCE_IDS), identities(result))
        self.assertEqual((), result.unknown_paths)
        self.assertEqual((), result.inventory_paths)
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((), phase_inventory_paths(paths, instance))

    def test_sdk_worker_and_shared_collection_controls_have_exact_owners(self):
        sdk = {item for item in PHASE_INSTANCE_IDS if item.product == "sdk" and
               item.component == "javascript" and item.phase in {"package", "validation", "metadata"}}
        for name in ("sdk-javascript-worker", "capture-runtime-state", "collect-runtime-wave"):
            path = f".github/actions/{name}/action.yml"
            expected = sdk if name == "sdk-javascript-worker" else sdk | {
                item for item in PHASE_INSTANCE_IDS if item.product == "runtime" or
                item.product == "sdk" and item.component in {"sdk-ios", "python", "csharp", "rust", "cpp", "dart"}}
            result = classify_paths((path,))
            self.assertEqual(expected, identities(result))
            self.assertEqual((), result.unknown_paths)
            self.assertEqual((), result.inventory_paths)
            for instance in PHASE_INSTANCE_IDS:
                self.assertEqual((), phase_inventory_paths((path,), instance))

        ios = ".github/actions/sdk-ios-binary-worker/action.yml"
        self.assertEqual({item for item in PHASE_INSTANCE_IDS if item.product == "sdk" and item.component == "sdk-ios"},
                         identities(classify_paths((ios,))))
        self.assertEqual((), classify_paths((ios,)).inventory_paths)

        for name in ("sdk-native-prepare", "sdk-native-package-worker"):
            path = f".github/actions/{name}/action.yml"
            self.assertEqual({item for item in PHASE_INSTANCE_IDS if item.product == "sdk" and
                              item.component in {"python", "csharp", "rust", "cpp", "dart"}},
                             identities(classify_paths((path,))))
            self.assertEqual((), classify_paths((path,)).inventory_paths)

    def test_sdk_campaign_controls_never_enter_contract_binary_inventory(self):
        paths = (
            "ci/sdk_campaign_catalog_producer.py",
            "ci/sdk_campaign_catalog_caller.py",
            "ci/sdk_campaign_authority_upload.py",
            "ci/sdk_campaign_authority_producer.py",
            "ci/sdk_apple_js_campaign_election.py",
            "ci/sdk_campaign_apple_js_semantic_policy.py",
            "ci/sdk_campaign_core_android_election.py",
            "ci/sdk_campaign_core_android_semantic_policy.py",
            "ci/sdk_campaign_native_policy.py",
            "ci/sdk_campaign_native_semantic_policy.py",
            "ci/sdk_campaign_pinned_election.py",
            "ci/products/sdk_campaign_dev_catalog.py",
            "ci/sdk_campaign_reused_original.py",
            "ci/sdk_nested_wave_locator.py",
            "ci/sdk_nested_partial_state.py",
            "ci/sdk_nested_wave_replay.py",
            "ci/sdk_partial_state.py",
            "ci/sdk_core_metadata_protected_handoff.py",
        )
        for path in paths:
            result = classify_paths((path,))
            self.assertEqual((), result.unknown_paths)
            self.assertEqual((), result.inventory_paths)
            self.assertFalse(any(instance.product == "contract" for instance in result.instances))
            self.assertTrue(all(instance.product == "sdk" for instance in result.instances))
            self.assertEqual((), phase_inventory_paths(
                (path,), PhaseInstanceId("contract", "contract", "binary", "common")))
        self.assertEqual(("ci/truly-unknown-control.py",), phase_inventory_paths(
            ("ci/truly-unknown-control.py",),
            PhaseInstanceId("contract", "contract", "binary", "common")))

    def test_phase10_output_records_select_only_their_product_metadata(self):
        for path, product, component, target in (
            ("ci/contract_phase10_output_record.py", "contract", "contract", "common"),
            ("ci/contract_phase10_record_signer.py", "contract", "contract", "common"),
            ("ci/runtime_phase10_output_record.py", "runtime", "runtime-aggregate", "aggregate"),
            ("ci/runtime_phase10_record_signer.py", "runtime", "runtime-aggregate", "aggregate"),
        ):
            result = classify_paths((path,))
            self.assertEqual((), result.unknown_paths)
            self.assertEqual((), result.inventory_paths)
            self.assertEqual({PhaseInstanceId(product, component, "metadata", target)},
                             identities(result))

    def test_native_validation_and_metadata_actions_replan_only_their_owners_without_binary_inputs(self):
        for phase, phases in (("validation", {"validation", "metadata"}), ("metadata", {"metadata"})):
            path = f".github/actions/sdk-native-{phase}-worker/action.yml"
            result = classify_paths((path,))
            self.assertEqual({item for item in PHASE_INSTANCE_IDS if item.product == "sdk" and
                              item.component in {"python", "csharp", "rust", "cpp", "dart"} and item.phase in phases},
                             identities(result))
            self.assertEqual((), result.unknown_paths)
            self.assertEqual((), result.inventory_paths)
            for instance in PHASE_INSTANCE_IDS:
                self.assertEqual((), phase_inventory_paths((path,), instance))

    def test_authenticated_native_handoff_and_metadata_join_have_exact_direct_owners(self):
        paths = ("ci/products/sdk_inputs.py", "ci/products/sdk_native.py", "ci/products/sdk_package.py")
        for instance in PHASE_INSTANCE_IDS:
            expected = paths if (instance.product == "sdk" and instance.component in
                {"python", "csharp", "rust", "cpp", "dart"} and instance.phase == "validation") else ()
            if instance.product == "sdk" and instance.component in {"python", "csharp", "rust", "cpp", "dart"} \
                    and instance.phase == "metadata":
                expected = paths
            with self.subTest(instance=instance):
                self.assertEqual(tuple(sorted(expected)), phase_inventory_paths(paths, instance))
        path = "gradle/build-logic/src/main/kotlin/CrossLanguageNativeWrapperValidationEvidence.kt"
        for instance in PHASE_INSTANCE_IDS:
            expected = (path,) if instance.product == "sdk" and instance.component in \
                {"python", "csharp", "rust", "cpp", "dart"} and instance.phase in {"validation", "metadata"} else ()
            self.assertEqual(expected, phase_inventory_paths((path,), instance))

    def test_native_metadata_independently_keys_executed_verifiers_not_compiler_producers(self):
        from ci.products.selection import _NATIVE_METADATA_VERIFIERS
        languages = {"python", "csharp", "rust", "cpp", "dart"}
        for path in (*_NATIVE_METADATA_VERIFIERS, "codex-agent-bindings/cpp/tools/verify_imported_package.py"):
            expected_languages = {"cpp"} if path.startswith("codex-agent-bindings/") else languages
            selected = identities(classify_paths((path,)))
            for language in languages:
                instance = PhaseInstanceId("sdk", language, "metadata", "desktop")
                with self.subTest(path=path, language=language):
                    self.assertEqual((path,) if language in expected_languages else (), phase_inventory_paths((path,), instance))
                    if language in expected_languages:
                        self.assertIn(instance, selected)
        for path in ("ci/products/plan.py", "ci/products/selection.py", "ci/products/registry.py",
                     "ci/products/contract_projection.py", "ci/products/contract_attestation.py",
                     "codex-agent-bindings/python/tools/produce_sdk_validation_evidence.py"):
            for language in languages:
                self.assertEqual((), phase_inventory_paths((path,), PhaseInstanceId("sdk", language, "metadata", "desktop")))

    def test_packaged_native_verifier_and_resource_policy_are_direct_validation_and_metadata_inputs(self):
        paths = ("gradle/build-logic/build.gradle.kts",
                 "gradle/build-logic/src/main/kotlin/ProductPythonTooling.kt")
        for language in ("python", "csharp", "rust", "cpp", "dart"):
            for phase, target in [("validation", target) for target in NATIVE_TARGETS] + [("metadata", "desktop")]:
                self.assertEqual(paths, phase_inventory_paths(paths, PhaseInstanceId("sdk", language, phase, target)))
        # Resource ownership stays in the SDK build, never the standalone Runtime compiler.
        for instance in PHASE_INSTANCE_IDS:
            if instance.product == "runtime":
                self.assertEqual((), phase_inventory_paths(paths, instance))

    def test_sdk_python_dispatch_does_not_invalidate_contract_payloads(self):
        dispatch = "gradle/build-logic/src/main/kotlin/ProductPythonTooling.kt"
        runner = "gradle/build-logic/src/main/kotlin/PackagedProductPython.kt"
        pathspec = Path("ci/lanes/contract-product.production.pathspec").read_text().splitlines()
        self.assertNotIn(dispatch, pathspec)
        self.assertIn(runner, pathspec)
        for instance in PHASE_INSTANCE_IDS:
            if instance.product == "contract":
                self.assertEqual((), phase_inventory_paths((dispatch,), instance))
        binary = PhaseInstanceId("contract", "contract", "binary", "common")
        self.assertEqual((runner,), phase_inventory_paths((runner,), binary))
        sdk = PhaseInstanceId("sdk", "python", "validation", "macos-arm64")
        self.assertEqual(tuple(sorted((dispatch, runner))), phase_inventory_paths((dispatch, runner), sdk))

    def test_runtime_adapter_metadata_safety_keys_only_metadata_and_shared_mac_validation(self):
        path = "runtime/build-logic/src/main/kotlin/RuntimeAdapterMetadataInputsTask.kt"
        direct = {PhaseInstanceId("runtime", component, "metadata", component) for component in ("jvm", "node-js", "node-wasm")}
        direct.add(PhaseInstanceId("runtime", "macos-arm64", "validation", "macos-arm64"))
        selected = identities(classify_paths((path,)))
        self.assertFalse(any(instance.phase in {"binary", "package"} for instance in selected))
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((path,) if instance in direct else (), phase_inventory_paths((path,), instance))

    def test_runtime_adapter_metadata_directly_keys_shared_capture_digest(self):
        path = "runtime/build-logic/src/main/kotlin/RuntimeReleaseIo.kt"
        expected = {instance for instance in PHASE_INSTANCE_IDS if instance.product == "runtime" and (
            instance.phase in {"binary", "validation"} or
            (instance.phase == "package" and instance.component in NATIVE_TARGETS) or
            (instance.phase == "metadata" and instance.component in {"jvm", "node-js", "node-wasm", "runtime-aggregate"}))}
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((path,) if instance in expected else (), phase_inventory_paths((path,), instance))

    def test_runtime_maven_handoff_keys_binary_capture_and_exact_imported_phase(self):
        from ci.tests.test_product_plan import plan
        path = "runtime/build-logic/src/main/kotlin/RuntimeAdapterMavenHandoff.kt"
        adapters = {"jvm", "node-js", "node-wasm"}
        direct = {instance for instance in PHASE_INSTANCE_IDS if instance.product == "runtime" and (
            (instance.component in RUNTIME_COMPONENTS and instance.phase == "binary") or
            (instance.component == "runtime-aggregate" and instance.phase == "metadata"))}
        selected = identities(classify_paths((path,)))
        self.assertEqual(9, len(direct))
        self.assertTrue({instance for instance in PHASE_INSTANCE_IDS
                         if instance.product == "runtime" and instance.component in adapters}.issubset(selected))
        self.assertIn(PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"), selected)
        self.assertTrue(direct.issubset(selected))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / path
            source.parent.mkdir(parents=True)
            for instance in PHASE_INSTANCE_IDS:
                with self.subTest(instance=instance):
                    self.assertEqual((path,) if instance in direct else (),
                                     phase_inventory_paths((path,), instance))
                    if instance.product != "runtime":
                        continue
                    keys = []
                    for contents in (b"a", b"b"):
                        source.write_bytes(contents)
                        inventory = phase_file_inventory(root, (path,), instance)
                        self.assertEqual(
                            [{"relativePath": path, "bytes": 1, "sha256": sha256_bytes(contents)}]
                            if instance in direct else [], inventory,
                        )
                        # Fixed original predecessors isolate direct execution
                        # ownership from normal artifact-driven successor misses.
                        keys.append(plan(instance, inventory=inventory)["buildKey"])
                    self.assertEqual(instance in direct, keys[0] != keys[1])

    def test_standalone_python_capture_keys_every_independent_caller(self):
        path = "runtime/build-logic/src/main/kotlin/RuntimeProductPythonTooling.kt"
        expected = {instance for instance in PHASE_INSTANCE_IDS if instance.product == "runtime" and (
            instance.phase == "binary" or
            (instance.phase == "package" and instance.component in NATIVE_TARGETS) or
            (instance.phase == "validation" and instance.target in NATIVE_TARGETS) or
            (instance.phase == "metadata" and instance.component in {"jvm", "node-js", "node-wasm", "runtime-aggregate"}))}
        self.assertEqual(37, len(expected))
        self.assertTrue(expected.issubset(identities(classify_paths((path,)))))
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((path,) if instance in expected else (), phase_inventory_paths((path,), instance))

    def test_runtime_maven_semantic_helpers_key_aggregate_and_independent_native_validation(self):
        from ci.tests.test_product_plan import plan
        aggregate = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        paths = ("ci/products/runtime_maven.py", "ci/products/contract_model.py", "ci/products/sdk_maven.py")
        for path in paths:
            self.assertEqual((path,), phase_inventory_paths((path,), aggregate))
            for language in NATIVE_BINDINGS:
                for target in NATIVE_TARGETS:
                    instance = PhaseInstanceId("sdk", language, "validation", target)
                    self.assertEqual((path,), phase_inventory_paths((path,), instance))
            for target in NATIVE_TARGETS:
                self.assertEqual((), phase_inventory_paths((path,), PhaseInstanceId("runtime", target, "binary", target)))
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / path
                source.parent.mkdir(parents=True)
                keys = []
                for contents in (b"first semantic policy", b"changed semantic policy"):
                    source.write_bytes(contents)
                    keys.append(plan(aggregate, inventory=phase_file_inventory(root, (path,), aggregate))["buildKey"])
                self.assertNotEqual(*keys)

    def test_native_metadata_task_keys_only_five_sdk_metadata_phases(self):
        path = "gradle/build-logic/src/main/kotlin/NativeWrapperMetadataContentTask.kt"
        expected = {PhaseInstanceId("sdk", language, "metadata", "desktop")
                    for language in ("python", "csharp", "rust", "cpp", "dart")}
        self.assertEqual(expected, identities(classify_paths((path,))))
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((path,) if instance in expected else (), phase_inventory_paths((path,), instance))

    def test_root_gradle_inputs_do_not_enter_standalone_runtime_inventories(self) -> None:
        paths = ("build.gradle.kts", "gradle.properties", "settings-gradle.lockfile", "settings.gradle.kts")
        result = classify_paths(paths)
        self.assertFalse(any(instance.product == "runtime" and instance.phase in {"binary", "package"}
                             for instance in result.instances))
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
        self.assertEqual(set(NATIVE_BINDINGS),
                         {instance.component for instance in result.instances if instance.product == "sdk"})
        self.assertEqual((), result.inventory_paths)
        self.assertEqual((), result.unknown_paths)
        for instance in PHASE_INSTANCE_IDS:
            self.assertEqual((), phase_inventory_paths(paths, instance))

    def test_desktop_workflow_change_selects_its_five_sdk_binding_owners_only(self) -> None:
        result = classify_paths([".github/workflows/desktop-runtime-evidence.yml"])
        sdk = {instance for instance in result.instances if instance.product == "sdk"}
        self.assertEqual({instance for instance in PHASE_INSTANCE_IDS
                          if instance.product == "sdk" and instance.component in NATIVE_BINDINGS}, sdk)
        self.assertFalse(any(instance.product == "contract" for instance in result.instances))
        self.assertEqual((), result.inventory_paths)


if __name__ == "__main__":
    unittest.main()
