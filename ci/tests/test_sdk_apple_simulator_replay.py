"""Adapter orchestration with mocked tooling/process authority, not simulator admission."""

from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from ci.products import sdk_apple_content as content
from ci.products import sdk_apple_simulator_replay as replay
from ci.products.inventory import regular_file_inventory


class SdkAppleSimulatorReplayTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-simulator-adapter-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        (self.evidence / "original-observation.json").write_bytes(b"synthetic original observation\n")
        (self.evidence / "stderr.bin").write_bytes(b"")
        self.java = self.root / "jdk/bin/java"
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b"synthetic executable, never launched\n")
        self.jar = self.root / "tooling.jar"
        self.jar.write_bytes(b"synthetic authenticated-tool seam\n")
        self.arguments = dict(
            evidence_directory=self.evidence, expected_runtime_name="iOS 26.5",
            expected_device_type_identifier="com.apple.CoreSimulator.SimDeviceType.iPhone-17",
            original_working_directory="/original/checkout/codex-agent-runtime-ios",
            repository=self.root, tooling_evidence=self.root / "tooling",
            tooling_public_key=self.root / "public-key.pub", java_executable=self.java,
            policy_revision="a" * 40, required_trust_domain="release",
            tooling_keyring=self.root / "keyring.json", tooling_keys_directory=self.root / "keys",
        )
        self.calls = []
        self.private = None
        self.mutate = lambda: None
        self.after_tooling = lambda: None

    @contextmanager
    def tooling(self, evidence, repository, public_key, **policy):
        self.assertEqual((self.arguments["tooling_evidence"], self.root, self.arguments["tooling_public_key"]),
                         (evidence, repository, public_key))
        self.assertEqual({"required_trust_domain": "release", "policy_revision": "a" * 40,
                          "keyring": self.arguments["tooling_keyring"],
                          "keys_directory": self.arguments["tooling_keys_directory"]}, policy)
        yield self.jar
        self.after_tooling()

    def execute(self, command, **options):
        self.calls.append(command)
        self.assertEqual([str(self.java), "-jar", str(self.jar), "verify-original-apple-simulator-execution"], command[:4])
        fields = dict(zip(command[4::2], command[5::2], strict=True))
        self.assertEqual({"--evidence-directory", "--expected-runtime-name",
                          "--expected-device-type-identifier", "--original-working-directory"}, set(fields))
        for flag, name in (("--expected-runtime-name", "expected_runtime_name"),
                           ("--expected-device-type-identifier", "expected_device_type_identifier"),
                           ("--original-working-directory", "original_working_directory")):
            self.assertEqual(self.arguments[name], fields[flag])
        self.private = Path(fields["--evidence-directory"])
        self.assertNotEqual(self.evidence, self.private)
        self.assertEqual(regular_file_inventory(self.evidence, allow_empty=True),
                         regular_file_inventory(self.private, allow_empty=True))
        self.assertEqual(self.private.parent, options["cwd"])
        self.assertTrue(options["check"])
        self.assertEqual(subprocess.PIPE, options["stdout"])
        self.assertEqual(subprocess.PIPE, options["stderr"])
        self.assertFalse({"JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH", "PYTHONPATH"} & set(options["env"]))
        self.mutate()
        return subprocess.CompletedProcess(command, 0)

    def verify(self, **changes):
        with mock.patch.object(content, "verified_tooling_capture", self.tooling), \
                mock.patch.object(content.subprocess, "run", side_effect=self.execute):
            return replay.verify_sdk_apple_simulator_execution(**{**self.arguments, **changes})

    def test_fixed_command_private_unchanged_inputs_filtered_environment_and_no_token(self):
        before = regular_file_inventory(self.root, allow_empty=True)
        with mock.patch.dict("os.environ", {"JAVA_TOOL_OPTIONS": "injection", "CLASSPATH": "injection"}):
            self.assertIsNone(self.verify())
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.private.exists())

    def test_invalid_independent_pins_and_cwd_reject_before_tooling(self):
        with mock.patch.object(replay, "_verify_sdk_apple_with_tooling") as gate:
            for name, value in (("expected_runtime_name", None), ("expected_runtime_name", ""),
                                ("expected_runtime_name", " iOS 26.5"),
                                ("expected_device_type_identifier", True),
                                ("expected_device_type_identifier", "device\n"),
                                ("original_working_directory", None),
                                ("original_working_directory", "relative"),
                                ("original_working_directory", "/original/../other")):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    replay.verify_sdk_apple_simulator_execution(**{**self.arguments, name: value})
            gate.assert_not_called()

    def test_tooling_or_process_failure_never_returns_and_private_capture_is_removed(self):
        with mock.patch.object(content, "verified_tooling_capture", side_effect=ValueError("tooling rejected")), \
                mock.patch.object(content.subprocess, "run") as process:
            with self.assertRaisesRegex(ValueError, "tooling rejected"):
                replay.verify_sdk_apple_simulator_execution(**self.arguments)
            process.assert_not_called()
        def fail():
            raise subprocess.CalledProcessError(1, "fixed verifier", stderr=b"original failure\n")
        self.mutate = fail
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self.verify()
        self.assertEqual(b"original failure\n", error.exception.stderr)
        self.assertFalse(self.private.exists())

    def test_original_private_and_context_exit_mutation_reject(self):
        for where in ("original", "private", "context-exit"):
            with self.subTest(where=where):
                original = self.evidence / "original-observation.json"
                contents = original.read_bytes()
                def mutate():
                    path = self.private / original.name if where == "private" else original
                    path.write_bytes(b"mutation\n")
                self.mutate = mutate if where != "context-exit" else lambda: None
                self.after_tooling = mutate if where == "context-exit" else lambda: None
                try:
                    with self.assertRaisesRegex(ValueError, "changed during verification"):
                        self.verify()
                    self.assertFalse(self.private.exists())
                finally:
                    original.write_bytes(contents)


if __name__ == "__main__":
    unittest.main()
