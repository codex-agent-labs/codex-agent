"""Runner orchestration only; mocked execution is not Apple semantic/host proof."""

from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import regular_file_inventory
from ci.products.sdk_apple_content import (
    verify_sdk_apple_original_execution, verify_sdk_apple_package_content, verify_sdk_apple_binary_package_content,
    verify_sdk_apple_validation_binding_content,
)


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
        self.distribution = self.root / "original-distribution"
        self.distribution.mkdir()
        (self.distribution / "verified-distribution-proof.json").write_bytes(self.proof.read_bytes())
        self.execution = self.root / "original-execution"
        (self.execution / "compiler-raw").mkdir(parents=True)
        (self.execution / "compiler-raw/raw-observation.json").write_bytes(b"synthetic raw observation\n")
        (self.execution / "compiler-raw/empty-stderr.bin").write_bytes(b"")
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
        self.binary = self.root / "binary"
        self.binary.mkdir()
        (self.binary / "synthetic-framework").write_bytes(b"original binary\n")
        self.developer = self.root / "Developer"
        self.developer.mkdir()

    @contextmanager
    def capture(self, evidence, repository, public_key, **policy):
        self.assertEqual((self.args["tooling_evidence"], self.root, self.args["tooling_public_key"]),
                         (evidence, repository, public_key))
        self.assertEqual(dict(required_trust_domain="development", keyring=None, keys_directory=None,
                              policy_revision="a" * 40), policy)
        yield self.jar

    def execute(self, command, **kwargs):
        self.calls.append(command)
        self.assertEqual([str(self.java), "-jar", str(self.jar)], command[:3])
        fields = dict(zip(command[4::2], command[5::2], strict=True))
        if command[3] == "verify-apple-validation-binding-content":
            self.assertEqual("0.2.0", fields.pop("--version"))
            self.assertEqual({"--product-directory", "--evidence-directory", "--consumer-source-directory",
                              "--sdk-compatibility", "--canonical-api", "--canonical-coverage",
                              "--work-directory"}, set(fields))
            fields = {name: Path(value) for name, value in fields.items()}
            for option, source, empty in (("--product-directory", self.product, False),
                                         ("--evidence-directory", self.execution, True),
                                         ("--consumer-source-directory", self.consumers, False)):
                self.assertNotEqual(source, fields[option])
                self.assertEqual(regular_file_inventory(source, allow_empty=empty),
                                 regular_file_inventory(fields[option], allow_empty=empty))
            for option, source in (("--sdk-compatibility", self.compatibility),
                                   ("--canonical-api", self.api), ("--canonical-coverage", self.coverage)):
                self.assertNotEqual(source, fields[option])
                self.assertEqual(source.read_bytes(), fields[option].read_bytes())
            self.assertFalse(fields["--work-directory"].exists())
            self.assertFalse({"JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH"} & set(kwargs["env"]))
            self.mutate(fields)
            return subprocess.CompletedProcess(command, 0)
        if command[3] == "verify-apple-binary-package":
            self.assertEqual("0.2.0", fields.pop("--version"))
            self.assertEqual("26.6", fields.pop("--xcode-version"))
            self.assertEqual("17F113", fields.pop("--xcode-build"))
            self.assertEqual("6.3.3", fields.pop("--swift-version"))
            self.assertEqual({"--product-directory", "--binary-frameworks", "--source-snapshot",
                              "--sdk-compatibility", "--work-directory", "--developer-directory"}, set(fields))
            fields = {name: Path(value) for name, value in fields.items()}
            self.assertEqual(self.developer, fields["--developer-directory"])
            self.assertFalse(fields["--work-directory"].exists())
            for option, original in (("--product-directory", self.product), ("--binary-frameworks", self.binary)):
                self.assertNotEqual(original, fields[option])
                self.assertEqual(regular_file_inventory(original), regular_file_inventory(fields[option]))
            self.assertEqual(b"immutable source\n", (fields["--source-snapshot"] / "source.txt").read_bytes())
            self.assertEqual(self.compatibility.read_bytes(), fields["--sdk-compatibility"].read_bytes())
            self.assertNotIn("JAVA_TOOL_OPTIONS", kwargs["env"])
            self.mutate(fields)
            return subprocess.CompletedProcess(command, 0)
        if command[3] == "verify-original-apple-execution":
            self.assertEqual({"--distribution-directory", "--execution-directory",
                              "--expected-sdk-compatibility", "--expected-distribution-proof"}, set(fields))
            fields = {name: Path(value) for name, value in fields.items()}
            for option, source in (("--distribution-directory", self.distribution),
                                   ("--execution-directory", self.execution)):
                self.assertNotEqual(source, fields[option])
                allow_empty = option == "--execution-directory"
                self.assertEqual(regular_file_inventory(source, allow_empty=allow_empty),
                                 regular_file_inventory(fields[option], allow_empty=allow_empty))
            for option, source in (("--expected-sdk-compatibility", self.compatibility),
                                   ("--expected-distribution-proof", self.proof)):
                self.assertNotEqual(source, fields[option])
                self.assertEqual(source.read_bytes(), fields[option].read_bytes())
            self.assertEqual(fields["--distribution-directory"].parent, kwargs["cwd"])
            self.assertTrue(kwargs["check"])
            self.assertEqual(subprocess.PIPE, kwargs["stdout"])
            self.assertEqual(subprocess.PIPE, kwargs["stderr"])
            self.assertFalse({"JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH", "PYTHONPATH"}
                             & set(kwargs["env"]))
            self.mutate(fields)
            return subprocess.CompletedProcess(command, 0)
        self.assertEqual("verify-transported-apple-sdk-package-closure", command[3])
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

    def verify_original(self, **changes):
        arguments = {**self.args, "distribution_directory": self.distribution,
                     "execution_directory": self.execution}
        arguments.pop("product_directory")
        arguments.pop("validation_evidence_directory")
        arguments.pop("sdk_version")
        with patch("ci.products.sdk_apple_content.verified_tooling_capture", self.capture), \
                patch("ci.products.sdk_apple_content.subprocess.run", side_effect=self.execute):
            return verify_sdk_apple_original_execution(**{**arguments, **changes})

    def verify_binary(self, **changes):
        arguments = {key: value for key, value in self.args.items()
                     if key not in {"validation_evidence_directory", "expected_distribution_proof"}}
        arguments.update(binary_frameworks=self.binary, source_revision="b" * 40, developer_directory=self.developer)

        def sources(repository, revision, output):
            self.assertEqual(self.root, repository)
            self.assertEqual("b" * 40, revision)
            output.mkdir()
            (output / "source.txt").write_bytes(b"immutable source\n")
            return {"xcodeVersion": "26.6", "xcodeBuild": "17F113", "swiftVersion": "6.3.3"}

        with patch("ci.products.sdk_apple_content.capture_apple_package_sources", side_effect=sources), \
                patch("ci.products.sdk_apple_content.verified_tooling_capture", self.capture), \
                patch("ci.products.sdk_apple_content.subprocess.run", side_effect=self.execute):
            return verify_sdk_apple_binary_package_content(**{**arguments, **changes})

    def validation_binding_inputs(self):
        self.consumers = self.root / "selected-consumers"
        self.consumers.mkdir()
        (self.consumers / "consumer.swift").write_bytes(b"selected immutable consumer\n")
        self.api = self.root / "api.json"
        self.api.write_bytes(b"authenticated canonical API\n")
        self.coverage = self.root / "coverage.json"
        self.coverage.write_bytes(b"authenticated canonical coverage\n")

    def verify_validation_binding(self, **changes):
        arguments = {key: value for key, value in self.args.items()
                     if key not in {"validation_evidence_directory", "expected_distribution_proof"}}
        arguments.update(evidence_directory=self.execution, canonical_api=self.api,
                         canonical_coverage=self.coverage, consumer_source_directory=self.consumers)
        with patch("ci.products.sdk_apple_content.verified_tooling_capture", self.capture), \
                patch("ci.products.sdk_apple_content.subprocess.run", side_effect=self.execute):
            return verify_sdk_apple_validation_binding_content(**{**arguments, **changes})

    def test_validation_binding_replay_uses_private_selected_inputs_and_no_output(self):
        self.validation_binding_inputs()
        before = regular_file_inventory(self.root, allow_empty=True)
        with patch.dict("os.environ", {"JAVA_TOOL_OPTIONS": "injected"}):
            self.assertIsNone(self.verify_validation_binding())
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))

    def test_validation_binding_replay_rejects_each_private_authority_mutation_and_failure(self):
        self.validation_binding_inputs()
        for option, member in (("--evidence-directory", "compiler-raw/raw-observation.json"),
                               ("--product-directory", "CodexAgentPackage-0.2.0.zip"),
                               ("--consumer-source-directory", "consumer.swift"),
                               ("--canonical-api", None), ("--canonical-coverage", None),
                               ("--sdk-compatibility", None)):
            with self.subTest(option=option):
                def mutate(fields):
                    path = fields[option] / member if member else fields[option]
                    path.write_bytes(b"tampered expectation\n")
                self.mutate = mutate
                with self.assertRaisesRegex(ValueError, "changed during verification"):
                    self.verify_validation_binding()
        self.mutate = lambda fields: (_ for _ in ()).throw(subprocess.CalledProcessError(1, "replay"))
        with self.assertRaises(subprocess.CalledProcessError):
            self.verify_validation_binding()

    def test_binary_replay_uses_git_source_pins_private_inputs_and_fixed_command(self):
        before = regular_file_inventory(self.root, allow_empty=True)
        with patch.dict("os.environ", {"JAVA_TOOL_OPTIONS": "injected"}):
            self.assertEqual(regular_file_inventory(self.product), self.verify_binary())
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))
        self.assertEqual(1, len(self.calls))

    def test_binary_replay_rejects_private_mutation_and_process_failure(self):
        for option, member in (("--binary-frameworks", "synthetic-framework"), ("--source-snapshot", "source.txt")):
            with self.subTest(option=option):
                self.mutate = lambda fields: (fields[option] / member).write_bytes(b"mutated")
                with self.assertRaisesRegex(ValueError, "changed during verification"):
                    self.verify_binary()
        def fail(_fields):
            raise subprocess.CalledProcessError(1, "verifier")
        self.mutate = fail
        with self.assertRaises(subprocess.CalledProcessError):
            self.verify_binary()

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

    def test_original_execution_uses_only_private_caller_bound_inputs_and_returns_no_authority(self):
        before = regular_file_inventory(self.root, allow_empty=True)
        self.assertIsNone(self.verify_original())
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))
        self.assertEqual("verify-original-apple-execution", self.calls[-1][3])

    def test_original_execution_failure_or_mutation_never_returns_success(self):
        original = (self.execution / "compiler-raw/raw-observation.json").read_bytes()
        for private in (False, True):
            def mutate(fields):
                target = (fields["--execution-directory"] if private else self.execution) / \
                    "compiler-raw/raw-observation.json"
                target.write_bytes(b"changed observation\n")
            self.mutate = mutate
            try:
                with self.subTest(private=private), \
                        self.assertRaisesRegex(ValueError, "changed during verification"):
                    self.verify_original()
            finally:
                (self.execution / "compiler-raw/raw-observation.json").write_bytes(original)
        self.mutate = lambda fields: (_ for _ in ()).throw(
            subprocess.CalledProcessError(9, "original replay", output=b"stdout", stderr=b"stderr"))
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            self.verify_original()
        self.assertEqual(b"stderr", caught.exception.stderr)

    def test_original_execution_overlap_and_untrusted_tooling_fail_before_replay(self):
        with self.assertRaisesRegex(ValueError, "source inputs must not overlap"):
            self.verify_original(execution_directory=self.distribution)
        with patch("ci.products.sdk_apple_content.verified_tooling_capture",
                   side_effect=ValueError("tooling authority")), \
                patch("ci.products.sdk_apple_content.subprocess.run",
                      side_effect=AssertionError("execution")), \
                self.assertRaisesRegex(ValueError, "tooling authority"):
            verify_sdk_apple_original_execution(
                **{key: value for key, value in {
                    **self.args, "distribution_directory": self.distribution,
                    "execution_directory": self.execution,
                }.items() if key not in {"product_directory", "validation_evidence_directory", "sdk_version"}}
            )


if __name__ == "__main__":
    unittest.main()
