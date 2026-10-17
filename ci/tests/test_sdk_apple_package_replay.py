"""Original Apple package replay orchestration with mocked tooling authority.

No native process, receipt, producer, host, or phase admission is exercised here.
"""

from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from ci.products import sdk_apple_content as content
from ci.products import sdk_apple_package_replay as replay
from ci.products.inventory import canonical_json_bytes, regular_file_inventory


class SdkApplePackageReplayTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-apple-package-replay-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.product = self.root / "product"
        self.binary = self.root / "binary"
        self.evidence = self.root / "execution"
        for directory in (self.product, self.binary, self.evidence):
            directory.mkdir()
        (self.product / "package.zip").write_bytes(b"original product\x00\xff")
        (self.binary / "CodexAgent").write_bytes(b"original framework\n")
        (self.evidence / "execution.json").write_bytes(b"original observation\n")
        (self.evidence / "combined.bin").write_bytes(b"")
        self.compatibility = self.root / "sdk-compatibility.json"
        self.compatibility.write_bytes(b"authenticated compatibility\n")
        self.binding = self.root / "input-binding.json"
        self.binding.write_bytes(canonical_json_bytes({"synthetic": "outer-authenticated binding"}))
        self.execution_files = self.root / "expected-execution-files.json"
        self.execution_files.write_bytes(canonical_json_bytes({"00/execution.json": "2" * 64}))
        self.java = self.root / "jdk/bin/java"
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b"synthetic executable, never launched\n")
        self.jar = self.root / "tooling.jar"
        self.jar.write_bytes(b"synthetic authenticated tooling seam\n")
        self.arguments = dict(
            product_directory=self.product, binary_frameworks=self.binary, sdk_version="0.2.0",
            expected_sdk_compatibility=self.compatibility, source_revision="b" * 40,
            evidence_directory=self.evidence, execution_binding_file=self.binding,
            expected_binding_sha256="sha256:" + "1" * 64,
            expected_execution_files=self.execution_files, repository=self.root,
            tooling_evidence=self.root / "tooling", tooling_public_key=self.root / "public-key.pub",
            java_executable=self.java, policy_revision="a" * 40, required_trust_domain="release",
            tooling_keyring=self.root / "keyring.json", tooling_keys_directory=self.root / "keys",
        )
        self.calls = []
        self.private_fields = None
        self.private_root = None
        self.source = None
        self.mutate = lambda _fields: None
        self.after_tooling = lambda: None
        self.process_failure = None

    def sources(self, repository, revision, output):
        self.assertEqual(self.root, repository)
        self.assertEqual("b" * 40, revision)
        output.mkdir()
        (output / "immutable-source.swift").write_bytes(b"immutable Git source\n")
        self.source = output
        return {"xcodeVersion": "26.6", "xcodeBuild": "17F113", "swiftVersion": "6.3.3"}

    @contextmanager
    def tooling(self, evidence, repository, public_key, **policy):
        self.assertEqual(
            (self.arguments["tooling_evidence"], self.root, self.arguments["tooling_public_key"]),
            (evidence, repository, public_key),
        )
        self.assertEqual({
            "required_trust_domain": "release", "policy_revision": "a" * 40,
            "keyring": self.arguments["tooling_keyring"],
            "keys_directory": self.arguments["tooling_keys_directory"],
        }, policy)
        yield self.jar
        self.after_tooling()

    def execute(self, command, **options):
        self.calls.append(command)
        self.assertEqual(
            [str(self.java), "-jar", str(self.jar), "verify-original-apple-package-execution"],
            command[:4],
        )
        fields = dict(zip(command[4::2], command[5::2], strict=True))
        self.assertEqual({
            "--evidence-directory", "--product-directory", "--version", "--binary-frameworks",
            "--source-snapshot", "--sdk-compatibility", "--work-directory",
            "--execution-binding-file", "--expected-binding-sha256", "--expected-execution-files",
            "--xcode-version", "--xcode-build", "--swift-version",
        }, set(fields))
        self.assertEqual("0.2.0", fields.pop("--version"))
        self.assertEqual(self.arguments["expected_binding_sha256"], fields.pop("--expected-binding-sha256"))
        self.assertEqual("26.6", fields.pop("--xcode-version"))
        self.assertEqual("17F113", fields.pop("--xcode-build"))
        self.assertEqual("6.3.3", fields.pop("--swift-version"))
        fields = {name: Path(value) for name, value in fields.items()}
        for option, original, allow_empty in (
            ("--product-directory", self.product, False),
            ("--binary-frameworks", self.binary, False),
            ("--source-snapshot", self.source, False),
            ("--evidence-directory", self.evidence, True),
        ):
            self.assertNotEqual(original, fields[option])
            self.assertEqual(
                regular_file_inventory(original, allow_empty=allow_empty),
                regular_file_inventory(fields[option], allow_empty=allow_empty),
            )
        for option, original in (
            ("--sdk-compatibility", self.compatibility),
            ("--execution-binding-file", self.binding),
            ("--expected-execution-files", self.execution_files),
        ):
            self.assertNotEqual(original, fields[option])
            self.assertEqual(original.read_bytes(), fields[option].read_bytes())
        self.assertFalse(fields["--work-directory"].exists())
        self.assertEqual(fields["--product-directory"].parent, options["cwd"])
        self.assertTrue(options["check"])
        self.assertEqual(subprocess.PIPE, options["stdout"])
        self.assertEqual(subprocess.PIPE, options["stderr"])
        self.assertFalse({"JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH", "PYTHONPATH"}
                         & set(options["env"]))
        self.private_fields = fields
        self.private_root = options["cwd"]
        self.mutate(fields)
        if self.process_failure is not None:
            raise self.process_failure
        return subprocess.CompletedProcess(command, 0)

    def verify(self, **changes):
        with mock.patch.object(replay, "capture_apple_package_sources", side_effect=self.sources), \
                mock.patch.object(content, "verified_tooling_capture", self.tooling), \
                mock.patch.object(content.subprocess, "run", side_effect=self.execute):
            return replay.verify_sdk_apple_original_package_content(**{**self.arguments, **changes})

    def test_fixed_route_git_pins_private_copies_and_product_inventory_only(self):
        before = regular_file_inventory(self.root, allow_empty=True)
        with mock.patch.dict("os.environ", {"JAVA_TOOL_OPTIONS": "injected", "CLASSPATH": "injected"}):
            self.assertEqual(regular_file_inventory(self.product), self.verify())
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))
        self.assertEqual(1, len(self.calls))
        self.assertFalse(self.private_root.exists())

    def test_invalid_inputs_and_policy_reject_before_process(self):
        for name, value in (
            ("sdk_version", "not-semver"),
            ("expected_binding_sha256", "1" * 64),
            ("policy_revision", "not-a-revision"),
            ("expected_execution_files", self.root / "missing-events.json"),
            ("evidence_directory", self.product),
        ):
            self.calls.clear()
            with self.subTest(name=name), self.assertRaises((TypeError, ValueError)):
                self.verify(**{name: value})
            self.assertEqual([], self.calls)

    def test_tooling_and_process_failures_never_return_product_inventory(self):
        with mock.patch.object(replay, "capture_apple_package_sources", side_effect=self.sources), \
                mock.patch.object(content, "verified_tooling_capture", side_effect=ValueError("tooling rejected")), \
                mock.patch.object(content.subprocess, "run") as process, \
                self.assertRaisesRegex(ValueError, "tooling rejected"):
            replay.verify_sdk_apple_original_package_content(**self.arguments)
        process.assert_not_called()

        self.process_failure = subprocess.CalledProcessError(1, "fixed replay", stderr=b"original failure\n")
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self.verify()
        self.assertEqual(b"original failure\n", error.exception.stderr)
        self.assertFalse(self.private_root.exists())

    def test_original_private_source_and_context_exit_mutations_are_rejected(self):
        cases = (
            ("original-product", self.product / "package.zip", None),
            ("private-execution", None, "--evidence-directory"),
            ("private-binding", None, "--execution-binding-file"),
            ("immutable-source", None, "source"),
            ("context-exit", self.execution_files, None),
        )
        for name, original, private_option in cases:
            self.mutate = lambda _fields: None
            self.after_tooling = lambda: None
            target = original
            if name == "immutable-source":
                def mutate_source(_fields):
                    (self.source / "immutable-source.swift").write_bytes(b"changed source\n")
                self.mutate = mutate_source
            elif private_option is not None:
                def mutate_private(fields, option=private_option):
                    path = fields[option]
                    if path.is_dir():
                        path = next(path.iterdir())
                    path.write_bytes(b"changed private input\n")
                self.mutate = mutate_private
            elif name == "context-exit":
                self.after_tooling = lambda: self.execution_files.write_bytes(b"changed after tooling\n")
            else:
                self.mutate = lambda _fields, path=target: path.write_bytes(b"changed original input\n")
            saved = target.read_bytes() if target is not None else None
            try:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "changed during verification"):
                    self.verify()
                self.assertFalse(self.private_root.exists())
            finally:
                if target is not None and saved is not None:
                    target.write_bytes(saved)


if __name__ == "__main__":
    unittest.main()
