"""SDK input translation fixtures, not authenticated products or execution."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sdk_phase import properties, route


class SdkPhaseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-phase-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.request = self.root / "compatibility-request.json"
        self.request.write_bytes(b"caller authenticated request fixture\n")
        self.calls = []
        self.records = {}
        for identity, version in (
            (("contract", "contract", "binary", "common"), "0.2.0"),
            (("runtime", "node-js", "package", "node-js"), "0.2.1"),
            (("runtime", "node-js", "validation", "node-js-binding"), "0.2.3"),
            (("sdk", "javascript", "package", "node"), "0.3.0"),
        ):
            stage = self.root / "-".join(identity)
            stage.mkdir()
            self.records[identity] = {"stage": stage, "receiptPath": stage / "original-receipt.json",
                                      "receipt": dict(zip(("product", "component", "phase", "target"), identity),
                                                      productVersion=version)}

    def plan(self, phase):
        return {"product": "sdk", "component": "javascript", "phase": phase, "target": "node",
                "productVersion": "0.3.0", "runtimeVersion": "0.2.9"}

    def predecessor(self, *identity):
        self.calls.append(identity)
        return self.records[identity]

    def test_package_consumes_exact_contract_runtime_package_and_authenticated_request(self):
        result = properties(self.plan("package"), predecessor=self.predecessor, compatibility_request=self.request)
        self.assertEqual({
            "codexAgent.contractBinaryStage": str(self.records[("contract", "contract", "binary", "common")]["stage"]),
            "codexAgent.runtimePackageStage": str(self.records[("runtime", "node-js", "package", "node-js")]["stage"]),
            "codexAgent.runtimePackageVersion": "0.2.1",
            "codexAgent.sdkCompatibilityRequest": str(self.request),
        }, result)
        self.assertEqual([("contract", "contract", "binary", "common"),
                          ("runtime", "node-js", "package", "node-js")], self.calls)

    def test_validation_uses_original_binding_version_and_sdk_without_package_reconstruction_inputs(self):
        result = properties(self.plan("validation"), predecessor=self.predecessor)
        self.assertEqual({
            "codexAgent.contractBinaryStage": str(self.records[("contract", "contract", "binary", "common")]["stage"]),
            "codexAgent.runtimeBindingValidationStage": str(self.records[("runtime", "node-js", "validation", "node-js-binding")]["stage"]),
            "codexAgent.runtimeBindingValidationVersion": "0.2.3",
            "codexAgent.sdkPackageStageRoot": str(self.records[("sdk", "javascript", "package", "node")]["stage"]),
        }, result)
        self.assertEqual([("contract", "contract", "binary", "common"),
                          ("runtime", "node-js", "validation", "node-js-binding"),
                          ("sdk", "javascript", "package", "node")], self.calls)

    def test_javascript_routes_do_not_create_a_toolchain_profile(self):
        expected = {"runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64",
                    "toolchainProfile": None, "producerRole": None, "supervisor": None}
        for phase in ("package", "validation"):
            self.assertEqual(expected, route({**self.plan(phase), "runner": "injected"}))
        for changes in ({"phase": "binary"}, {"phase": "metadata"}, {"component": "sdk-javascript"},
                        {"component": "sdk-core"}, {"component": "python"}, {"target": "node-js"},
                        {"target": "linux-x64"}, {"product": "runtime"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                route({**self.plan("package"), **changes})

    def test_all_eleven_core_targets_use_existing_host_routes_without_javascript_properties(self):
        from products.registry import SDK_FACADE_TARGETS
        from runtime_adapter_phase import route as runtime_route
        for target in SDK_FACADE_TARGETS:
            plan = {"product": "sdk", "component": "sdk-core", "phase": "validation", "target": target}
            host = ("macos-arm64" if target.startswith("ios-") else
                    "linux-x64" if target == "linux-arm64" else
                    target if target.startswith(("linux-", "macos-", "windows-")) else "linux-x64")
            with self.subTest(target=target):
                self.assertEqual(runtime_route({"product": "runtime", "component": "jvm",
                                                "phase": "validation", "target": host}), route(plan))
                with self.assertRaisesRegex(ValueError, "facade request"):
                    properties(plan, predecessor=self.predecessor)
        self.assertEqual([], self.calls)

    def test_missing_unsafe_or_unused_compatibility_request_is_rejected(self):
        link = self.root / "request-link"
        link.symlink_to(self.request)
        empty = self.root / "empty"
        empty.write_bytes(b"")
        for path in (None, Path("relative.json"), self.root / "absent", self.root, link, empty):
            with self.subTest(path=path), self.assertRaises(ValueError):
                properties(self.plan("package"), predecessor=self.predecessor, compatibility_request=path)
        self.assertEqual([], self.calls)
        with self.assertRaisesRegex(ValueError, "does not consume"):
            properties(self.plan("validation"), predecessor=self.predecessor, compatibility_request=self.request)

    def test_crosspaired_receipt_invalid_version_and_unsafe_stage_fail_closed(self):
        identity = ("contract", "contract", "binary", "common")
        original = self.records[identity]
        for field, value in (("product", "runtime"), ("component", "node-js"),
                             ("phase", "metadata"), ("target", "node"), ("productVersion", "not-semver")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.records[identity] = {**original, "receipt": {**original["receipt"], field: value}}
                properties(self.plan("validation"), predecessor=self.predecessor)
        self.records[identity] = original
        link = self.root / "stage-link"
        link.symlink_to(original["stage"], target_is_directory=True)
        for path in (Path("relative"), self.root / "absent", self.request, link):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.records[identity] = {**original, "stage": path}
                properties(self.plan("validation"), predecessor=self.predecessor)
        self.records[identity] = original


class SdkRoutingContractTests(unittest.TestCase):
    def test_native_consumed_scopes_keep_full_authentication_but_restore_only_read_stages(self):
        from sdk_phase import NATIVE_RUNTIME_PREDECESSORS, native_consumed_predecessors, SDK_FAMILY_INSTANCES
        from products.registry import PhaseInstanceId
        from products.reuse import _dependency_closure
        self.assertEqual(11, len(set(NATIVE_RUNTIME_PREDECESSORS)))
        for phase, count in (("package", 11), ("validation", 12), ("metadata", 6)):
            for instance in SDK_FAMILY_INSTANCES["native-" + phase]:
                with self.subTest(instance=instance):
                    consumed = native_consumed_predecessors(instance)
                    closure = set(_dependency_closure((instance,))) - {instance}
                    self.assertEqual(count + (instance.component == "csharp"), len(consumed))
                    self.assertEqual(len(consumed), len(set(consumed)))
                    self.assertTrue(set(consumed) < closure)
                    self.assertTrue(set(NATIVE_RUNTIME_PREDECESSORS) < closure)
                    self.assertEqual(instance.component == "csharp", PhaseInstanceId(
                        "sdk", "csharp", "binary", "desktop") in consumed)
                    self.assertTrue(all(item.component == instance.component
                        for item in consumed if item.product == "sdk"))
                    if phase == "metadata":
                        self.assertTrue(all(item.product == "sdk" for item in consumed))
        with self.assertRaises(ValueError):
            native_consumed_predecessors(PhaseInstanceId("sdk", "javascript", "package", "node"))

    def test_registered_worker_families_partition_existing_sdk_instances(self):
        from sdk_phase import SDK_FAMILY_ROUTES, SDK_FAMILY_INSTANCES
        from products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId
        families = [row.family for row in SDK_FAMILY_ROUTES]
        self.assertEqual(len(families), len(set(families)))
        self.assertEqual(len(families), len({row.wave for row in SDK_FAMILY_ROUTES}))
        members = [item for family in families for item in SDK_FAMILY_INSTANCES[family]]
        self.assertEqual(len(members), len(set(members)))
        # These three legacy workers precede the family continuation mechanism.
        legacy = {PhaseInstanceId("sdk", "javascript", phase, "node") for phase in ("package", "validation")}
        legacy.add(PhaseInstanceId("sdk", "sdk-ios", "binary", "ios"))
        self.assertEqual({item for item in PHASE_INSTANCE_IDS if item.product == "sdk"} - legacy, set(members))
        root = Path(__file__).resolve().parents[2]
        parent = (root / ".github/workflows/product-validation.yml").read_text()
        for row in SDK_FAMILY_ROUTES:
            with self.subTest(family=row.family):
                self.assertTrue(SDK_FAMILY_INSTANCES[row.family])
                workflow = (root / row.workflow_path).read_text()
                self.assertIn(f"  {row.collector}:\n", workflow)
                if row.child:
                    self.assertIn(f"  {row.parent}:\n", parent)
                    self.assertIn(f"uses: ./{row.workflow_path}", parent)

    def test_consumed_inputs_are_bounded_subsets_not_the_authenticated_closure(self):
        from sdk_phase import maven_consumed_predecessors, SDK_FAMILY_INSTANCES
        from products.registry import PhaseInstanceId
        from products.reuse import _dependency_closure
        metadata = PhaseInstanceId("sdk", "sdk-core", "metadata", "common")
        cases = [(PhaseInstanceId("sdk", "sdk-core", "package", "common"), None, 5),
                 (PhaseInstanceId("sdk", "sdk-android", "package", "android"), None, 5), (metadata, None, 17)]
        cases.append((PhaseInstanceId("sdk", "sdk-android", "validation", "android"), None, 6))
        for validation in sorted(SDK_FAMILY_INSTANCES["core-validation"]):
            cases.extend(((validation, None, 6), (metadata, validation.target, 7)))
        for instance, target, count in cases:
            with self.subTest(instance=instance, target=target):
                consumed = maven_consumed_predecessors(instance, validation_target=target)
                closure = set(_dependency_closure((instance,))) - {instance}
                self.assertEqual(count, len(consumed))
                self.assertEqual(len(consumed), len(set(consumed)))
                self.assertTrue(set(consumed) < closure)
                self.assertFalse(any(item.product == "runtime" for item in consumed))
                self.assertEqual(46, sum(item.product == "runtime" for item in closure))
        for instance, target in ((metadata, "unknown"),
                (cases[0][0], "jvm"), (PhaseInstanceId("sdk", "python", "package", "desktop"), None)):
            with self.subTest(instance=instance, target=target), self.assertRaises(ValueError):
                maven_consumed_predecessors(instance, validation_target=target)


if __name__ == "__main__":
    unittest.main()
