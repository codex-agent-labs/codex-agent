"""Runner orchestration only; mocked execution is not Apple semantic/host proof."""

from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import regular_file_inventory
from ci.products.sdk_apple_content import verify_sdk_apple_package_content


class SdkAppleContentTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-apple-adapter-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.product = self.root / "product"
        self.product.mkdir()
        for name in ("CodexAgentPackage-0.2.0.zip", "CodexAgent-0.2.0.xcframework.zip",
                     "CodexAgent-0.2.0.xcframework.zip.sha256"):
            (self.product / name).write_bytes(f"synthetic original {name}\n".encode())
        self.validation = self.root / "validation"
        (self.validation / "verified-distribution/reports").mkdir(parents=True)
        (self.validation / "verified-distribution/reports/empty.log").write_bytes(b"")
        (self.validation / "original-receipt.json").write_bytes(b"original raw receipt\n")
        self.compatibility = self.root / "sdk-compatibility.json"
        self.compatibility.write_bytes(b"caller authenticated compatibility\n")
        self.proof = self.root / "verified-distribution-proof.json"
        self.proof.write_bytes(b"caller authenticated original proof\n")
        self.java = self.root / "jdk/bin/java"
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b"synthetic Java, never executed\n")
        self.jar = self.root / "tooling.jar"
        self.jar.write_bytes(b"synthetic captured tooling\n")
        self.args = dict(product_directory=self.product, validation_evidence_directory=self.validation,
            sdk_version="0.2.0", expected_sdk_compatibility=self.compatibility,
            expected_distribution_proof=self.proof, repository=self.root,
            tooling_evidence=self.root / "tooling", tooling_public_key=self.root / "pinned.pub",
            java_executable=self.java, policy_revision="a" * 40, required_trust_domain="development")
        self.calls = []
        self.mutate = lambda fields: None

    @contextmanager
    def capture(self, evidence, repository, public_key, **policy):
        self.assertEqual((self.args["tooling_evidence"], self.root, self.args["tooling_public_key"]),
                         (evidence, repository, public_key))
        self.assertEqual(dict(required_trust_domain="development", keyring=None, keys_directory=None,
                              policy_revision="a" * 40), policy)
        yield self.jar

    def execute(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual([str(self.java), "-jar", str(self.jar),
                          "verify-transported-apple-sdk-package-closure"], command[:4])
        fields = dict(zip(command[4::2], command[5::2], strict=True))
        self.assertEqual({"--product-directory", "--validation-evidence-directory", "--version",
                          "--owned-build-directory", "--work-directory", "--expected-sdk-compatibility",
                          "--expected-distribution-proof"}, set(fields))
        self.assertEqual("0.2.0", fields.pop("--version"))
        fields = {name: Path(value) for name, value in fields.items()}
        for option, source, empty in (("--product-directory", self.product, False),
                                      ("--validation-evidence-directory", self.validation, True)):
            self.assertNotEqual(source, fields[option])
            self.assertEqual(regular_file_inventory(source, allow_empty=empty),
                             regular_file_inventory(fields[option], allow_empty=empty))
        for option, source in (("--expected-sdk-compatibility", self.compatibility),
                               ("--expected-distribution-proof", self.proof)):
            self.assertNotEqual(source, fields[option])
            self.assertEqual(source.read_bytes(), fields[option].read_bytes())
        self.assertEqual(fields["--owned-build-directory"] / "work", fields["--work-directory"])
        self.assertEqual(fields["--product-directory"].parent, kwargs["cwd"])
        self.assertTrue(kwargs["check"])
        self.assertEqual(subprocess.PIPE, kwargs["stdout"])
        self.assertEqual(subprocess.PIPE, kwargs["stderr"])
        self.assertFalse({"JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH", "PYTHONPATH"} & set(kwargs["env"]))
        self.mutate(fields)
        return subprocess.CompletedProcess(command, 0)

    def verify(self, **changes):
        with patch("ci.products.sdk_apple_content.verified_tooling_capture", self.capture), \
                patch("ci.products.sdk_apple_content.subprocess.run", side_effect=self.execute):
            return verify_sdk_apple_package_content(**{**self.args, **changes})

    def test_fixed_verified_tool_command_private_bytes_empty_diagnostics_and_no_publication(self):
        before = regular_file_inventory(self.root, allow_empty=True)
        with patch.dict("os.environ", {"JAVA_TOOL_OPTIONS": "injected", "CLASSPATH": "injected"}):
            inventory = self.verify()
        self.assertIs(type(inventory), list)
        self.assertEqual(regular_file_inventory(self.product), inventory)
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))
        self.assertEqual(1, len(self.calls))

    def test_tooling_rejection_prevents_any_process(self):
        with patch("ci.products.sdk_apple_content.verified_tooling_capture", side_effect=ValueError("tooling authority")), \
                patch("ci.products.sdk_apple_content.subprocess.run", side_effect=AssertionError("execution")), \
                self.assertRaisesRegex(ValueError, "tooling authority"):
            verify_sdk_apple_package_content(**self.args)

    def test_cli_failure_is_never_converted_to_inventory(self):
        def fail(fields):
            raise subprocess.CalledProcessError(1, "fixed verifier", output=b"raw stdout", stderr=b"raw stderr")
        self.mutate = fail
        before = regular_file_inventory(self.root, allow_empty=True)
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.verify()
        self.assertEqual(b"raw stderr", caught.exception.stderr)
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))

    def test_original_or_private_mutation_prevents_inventory_return(self):
        for option, source in (("--product-directory", self.product / "CodexAgentPackage-0.2.0.zip"),
                               ("--validation-evidence-directory", self.validation / "original-receipt.json"),
                               ("--expected-sdk-compatibility", self.compatibility),
                               ("--expected-distribution-proof", self.proof)):
            original = source.read_bytes()
            for private in (False, True):
                def mutate(fields):
                    target = fields[option] if private else source
                    if private and target.is_dir():
                        target = target / source.name
                    target.chmod(0o600)
                    target.write_bytes(b"changed original or capture\n")
                self.mutate = mutate
                try:
                    with self.subTest(option=option, private=private), self.assertRaisesRegex(ValueError, "changed during verification"):
                        self.verify()
                finally:
                    source.write_bytes(original)

    def test_source_swap_and_restore_does_not_change_private_bytes(self):
        expected = self.proof.read_bytes()
        def swap(fields):
            try:
                self.proof.write_bytes(b"temporary replacement\n")
                self.assertEqual(expected, fields["--expected-distribution-proof"].read_bytes())
            finally:
                self.proof.write_bytes(expected)
        self.mutate = swap
        self.assertEqual(regular_file_inventory(self.product), self.verify())

    def test_unsafe_missing_empty_inputs_and_unpinned_policy_fail_before_execution(self):
        alias = self.root / "linked"
        alias.symlink_to(self.validation, target_is_directory=True)
        empty = self.root / "empty"
        empty.write_bytes(b"")
        changes = ({"validation_evidence_directory": alias},
                   {"product_directory": self.validation},
                   {"expected_distribution_proof": self.root / "missing"},
                   {"expected_sdk_compatibility": empty},
                   {"java_executable": Path("java")},
                   {"policy_revision": None}, {"policy_revision": "main"},
                   {"sdk_version": "0.2"})
        for change in changes:
            with self.subTest(change=change), self.assertRaises((ValueError, OSError)):
                self.verify(**change)
        self.assertEqual([], self.calls)

    def test_java_identity_change_prevents_inventory_return(self):
        original = self.java.read_bytes()
        self.mutate = lambda fields: self.java.write_bytes(b"changed Java\n")
        try:
            with self.assertRaisesRegex(ValueError, "Trusted Java executable changed"):
                self.verify()
        finally:
            self.java.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
