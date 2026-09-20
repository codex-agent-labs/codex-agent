"""Gate composition tests with mocked leaves, not genuine Apple evidence."""

from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products import sdk_apple_validation_execution as gate


class AppleValidationExecutionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.evidence = self.root / "evidence"
        self.product = self.root / "product"
        for directory in (self.evidence / "device-package", self.evidence / "consumer", self.product):
            directory.mkdir(parents=True)
            (directory / "file").write_bytes(b"unchanged")
        self.files = {}
        for name in ("sdk_compatibility", "canonical_api", "canonical_coverage"):
            self.files[name] = self.root / name
            self.files[name].write_bytes(b"original expected input")
        self.sources = {"testApplicationInventory": [{"source": "immutable"}],
                        "toolchain": {"pin": "immutable"}}
        self.arguments = dict(evidence_root=self.evidence, product_directory=self.product,
            sdk_version="0.8.0", **self.files, repository=self.root, source_revision="a" * 40,
            original_working_directory="/original/project", original_device_work_directory="/original/device",
            original_test_application_directory="/original/consumer/CodexAgentTestApp",
            developer_directory="/original/Xcode", tooling_evidence=self.root / "tooling",
            tooling_public_key=self.root / "key", java_executable=self.root / "java",
            policy_revision="b" * 40, required_trust_domain="release")
        self.calls = []

    def run_gate(self, failure=None, mutation=None):
        leaves = (
            "verify_apple_validation_sources", "read_apple_validation_simulator_policy",
            "verify_sdk_apple_validation_binding_content", "verify_sdk_apple_simulator_execution",
            "verify_apple_device_evidence", "verify_apple_toolchain_evidence",
        )
        def call(name, args, kwargs):
            self.calls.append(name)
            if name == failure:
                raise ValueError("leaf rejected")
            if name == leaves[0]:
                self.assertEqual((self.root, "a" * 40, self.evidence), args)
                return self.sources
            if name == leaves[1]:
                return {"runtimeName": "independent runtime", "deviceTypeIdentifier": "independent device"}
            if name == leaves[3]:
                self.assertEqual(self.evidence, kwargs["evidence_directory"])
                self.assertEqual("independent runtime", kwargs["expected_runtime_name"])
                self.assertEqual("independent device", kwargs["expected_device_type_identifier"])
            if name == leaves[2]:
                consumers = kwargs["consumer_source_directory"]
                self.assertNotIn(self.evidence, consumers.parents)
                self.assertEqual(gate.regular_file_inventory(self.evidence / "consumer"),
                                 gate.regular_file_inventory(consumers))
            if name == leaves[4]:
                self.assertEqual(self.sources["testApplicationInventory"], kwargs["expected_test_application_inventory"])
                self.assertEqual(gate.regular_file_inventory(self.evidence / "device-package"),
                                 kwargs["expected_package_inventory"])
            if name == leaves[5]:
                self.assertEqual(self.sources["toolchain"], kwargs["expected_toolchain"])
                if mutation:
                    mutation.write_bytes(b"changed")
        with ExitStack() as stack:
            for name in leaves:
                stack.enter_context(patch.object(gate, name,
                    side_effect=lambda *args, _name=name, **kwargs: call(_name, args, kwargs)))
            return gate.verify_apple_validation_execution(**self.arguments)

    def test_all_full_gates_run_in_order_without_minting_authority(self):
        self.assertIsNone(self.run_gate())
        self.assertEqual(6, len(self.calls))
        self.assertLess(self.calls.index("verify_sdk_apple_validation_binding_content"),
                        self.calls.index("verify_apple_device_evidence"))

    def test_each_failure_prevents_later_gates(self):
        self.run_gate()
        expected = self.calls[:]
        for index, name in enumerate(expected):
            self.calls.clear()
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "leaf rejected"):
                self.run_gate(failure=name)
            self.assertEqual(expected[:index + 1], self.calls)

    def test_evidence_product_and_expectation_mutations_reject(self):
        for path in (self.evidence / "device-package/file", self.product / "file", *self.files.values()):
            original = path.read_bytes()
            try:
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, "inputs changed"):
                    self.run_gate(mutation=path)
            finally:
                path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
