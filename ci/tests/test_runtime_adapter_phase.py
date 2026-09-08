"""Adapter property routing only: no compiled products or authentication claim."""

from pathlib import Path
import sys
import tempfile
import unittest


CI_ROOT = Path(__file__).resolve().parents[1]
if str(CI_ROOT) not in sys.path:
    sys.path.insert(0, str(CI_ROOT))

from runtime_adapter_phase import properties
from products.registry import NATIVE_TARGETS, RUNTIME_ADAPTERS


class RuntimeAdapterPhaseTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.handoff = self.root / "validated-handoff"
        self.handoff.mkdir()
        self.calls = []

    def plan(self, component, phase, target=None):
        return {"product": "runtime", "component": component, "phase": phase,
                "target": component if target is None else target, "productVersion": "0.2.9"}

    def predecessor(self, component, phase, target):
        self.calls.append((component, phase, target))
        stage = self.root / f"{component}-{phase}-{target}"
        stage.mkdir(exist_ok=True)
        return {"stage": stage, "receiptPath": self.root / f"{stage.name}-receipt.json",
                "receipt": {"product": "runtime", "component": component, "phase": phase,
                            "target": target, "productVersion": "0.2.1" if component in RUNTIME_ADAPTERS else "0.2.3"}}

    def expected(self, component, phase, prefix, version="0.2.1"):
        return {f"codexAgent.{prefix}Stage": str(self.root / f"{component}-{phase}-{component}"),
                f"codexAgent.{prefix}Version": version}

    def test_binary_and_package_preserve_original_versions_for_all_adapters(self):
        for component in RUNTIME_ADAPTERS:
            with self.subTest(component=component):
                self.calls.clear()
                self.assertEqual({}, properties(self.plan(component, "binary"), predecessor=self.predecessor))
                self.assertEqual([], self.calls)
                self.assertEqual(self.expected(component, "binary", "runtimeBinary"),
                                 properties(self.plan(component, "package"), predecessor=self.predecessor))
                self.assertEqual([(component, "binary", component)], self.calls)

    def test_host_validation_uses_original_adapter_and_native_versions_on_every_host(self):
        for component in RUNTIME_ADAPTERS:
            for host in NATIVE_TARGETS:
                with self.subTest(component=component, host=host):
                    self.calls.clear()
                    self.assertEqual({**self.expected(component, "package", "runtimePackage"),
                                      **self.expected(host, "package", "runtimeNativePackage", "0.2.3")},
                                     properties(self.plan(component, "validation", host), predecessor=self.predecessor))
                    self.assertEqual([(component, "package", component), (host, "package", host)], self.calls)

    def test_node_binding_imports_only_original_js_package(self):
        self.assertEqual(self.expected("node-js", "package", "runtimePackage"),
                         properties(self.plan("node-js", "validation", "node-js-binding"),
                                    predecessor=self.predecessor))
        self.assertEqual([("node-js", "package", "node-js")], self.calls)

    def test_metadata_imports_original_package_and_exact_validated_handoff_not_maven(self):
        for component in RUNTIME_ADAPTERS:
            with self.subTest(component=component):
                self.calls.clear()
                self.assertEqual({**self.expected(component, "package", "runtimePackage"),
                                  "codexAgent.runtimeValidationHandoff": str(self.handoff)},
                                 properties(self.plan(component, "metadata"), predecessor=self.predecessor,
                                            validation_handoff=self.handoff))
                self.assertEqual([(component, "package", component)], self.calls)

    def test_unsupported_routes_and_missing_or_misplaced_handoff_fail_before_predecessor(self):
        invalid = [{}, {**self.plan("jvm", "binary"), "product": "sdk"},
                   self.plan("linux-x64", "binary"), self.plan("runtime-aggregate", "metadata"),
                   self.plan("jvm", "unknown"), self.plan("jvm", "package", "node-js"),
                   self.plan("node-js", "validation"), self.plan("jvm", "validation", "node-js-binding"),
                   self.plan("node-wasm", "validation", "node-js-binding"),
                   self.plan("node-js", "validation", "linuxX64"), self.plan("jvm", "metadata")]
        for plan in invalid:
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                properties(plan, predecessor=self.predecessor)
        with self.assertRaises(ValueError):
            properties(self.plan("jvm", "binary"), predecessor=self.predecessor, validation_handoff=self.handoff)
        self.assertEqual([], self.calls)

    def test_wrong_original_receipt_identity_or_version_is_not_substituted(self):
        for field, value in (("product", "sdk"), ("component", "node-js"), ("phase", "validation"),
                             ("target", "linux-x64"), ("productVersion", "not-a-version")):
            def wrong(*identity):
                result = self.predecessor(*identity)
                result["receipt"][field] = value
                return result
            with self.subTest(field=field), self.assertRaises(ValueError):
                properties(self.plan("jvm", "package"), predecessor=wrong)

    def test_missing_relative_and_symbolic_directories_fail_without_creation(self):
        link = self.root / "linked-handoff"
        link.symlink_to(self.handoff, target_is_directory=True)
        file = self.root / "not-directory"
        file.write_bytes(b"sentinel")
        for path in (self.root / "absent", Path("relative"), link, file,
                     self.handoff / ".." / self.handoff.name):
            with self.subTest(path=path), self.assertRaises(ValueError):
                properties(self.plan("jvm", "metadata"), predecessor=self.predecessor, validation_handoff=path)
        self.assertEqual([], self.calls)
        self.assertFalse((self.root / "absent").exists())
        self.assertEqual(b"sentinel", file.read_bytes())
        def missing(*identity):
            return {**self.predecessor(*identity), "stage": self.root / "missing-original"}
        with self.assertRaises(ValueError):
            properties(self.plan("node-js", "package"), predecessor=missing)


if __name__ == "__main__":
    unittest.main()
