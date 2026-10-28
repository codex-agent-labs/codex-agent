"""Real immutable source capture; mocked tooling/Java, not native admission."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import subprocess
import unittest
from unittest import mock

from ci.products import sdk_apple_content as content
from ci.products import sdk_apple_native_replay as replay
from ci.products.inventory import regular_file_inventory
from ci.tests import test_sdk_apple_native_source as fixtures


class SdkAppleNativeReplayTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.native_fixture()
        self.addCleanup(self.fixture.temporary.cleanup)
        self.revision = self.fixture.commit()
        self.root = self.fixture.root
        self.evidence = self.root / "native-evidence"
        self.toolchain = self.root / "toolchain"
        self.evidence.mkdir()
        self.toolchain.mkdir()
        for name in ("native-tests-proof.json", "codex-agent-ios-arm64.a",
                     "codex-agent-ios-arm64-proof.json", "codex-agent-ios-simulator-arm64.a",
                     "codex-agent-ios-simulator-arm64-proof.json"):
            (self.evidence / name).write_bytes(b"synthetic raw bytes, never authority\n")
        for name in ("codex-agent-ios-arm64-toolchain.json", "codex-agent-ios-simulator-arm64-toolchain.json"):
            (self.toolchain / name).write_bytes(b"synthetic toolchain observation\n")
        self.producers = {
            lane: {"repository": "owner/repository", "workflowPath": ".github/workflows/ci.yml",
                   "commit": str(index) * 40, "tree": str(index + 3) * 40,
                   "event": "pull_request", "runId": 100 + index, "runAttempt": index, "pullRequest": 7}
            for index, lane in enumerate(("ios-native-tests", "ios-rust-device", "ios-rust-simulator"), 1)
        }
        self.java = self.root / "jdk/bin/java"
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b"not executed\n")
        self.jar = self.root / "tooling.jar"
        self.jar.write_bytes(b"mocked signed tooling boundary\n")
        self.arguments = dict(
            evidence_directory=self.evidence, toolchain_directory=self.toolchain,
            original_producers=self.producers, source_revision=self.revision,
            rust_host="aarch64-apple-darwin", repository=self.fixture.repository,
            tooling_evidence=self.root / "tooling", tooling_public_key=self.root / "public-key.pub",
            java_executable=self.java, policy_revision="a" * 40, required_trust_domain="release",
            tooling_keyring=self.root / "keyring.json", tooling_keys_directory=self.root / "keys",
        )
        self.calls = []
        self.private = {}
        self.mutate = lambda: None
        self.after_tooling = lambda: None
        self.real_run = subprocess.run

    @contextmanager
    def tooling(self, evidence, repository, public_key, **policy):
        self.assertEqual((self.arguments["tooling_evidence"], self.fixture.repository,
                          self.arguments["tooling_public_key"]), (evidence, repository, public_key))
        self.assertEqual({"required_trust_domain": "release", "policy_revision": "a" * 40,
                          "keyring": self.arguments["tooling_keyring"],
                          "keys_directory": self.arguments["tooling_keys_directory"]}, policy)
        yield self.jar
        self.after_tooling()

    def process(self, command, **options):
        # Source capture still performs real immutable local Git reads.
        if str(command[0]) != str(self.java):
            return self.real_run(command, **options)
        self.calls.append(command)
        self.assertEqual([str(self.java), "-jar", str(self.jar),
                          "verify-original-apple-native-evidence"], command[:4])
        fields = dict(zip(command[4::2], command[5::2], strict=True))
        expected = {
            "--rust-host": "aarch64-apple-darwin", "--xcode-version": "26.6",
            "--xcode-build": "17F113", "--swift-version": "6.3.3",
        }
        for short, lane in (("device", "ios-rust-device"), ("simulator", "ios-rust-simulator"),
                            ("tests", "ios-native-tests")):
            for field in ("commit", "tree"):
                expected[f"--{short}-{field}"] = self.producers[lane][field]
        self.assertEqual(set(expected) | {"--evidence-directory", "--source-snapshot", "--toolchain-directory"},
                         set(fields))
        self.assertEqual(expected, {key: fields[key] for key in expected})
        for name, flag in (("evidence", "--evidence-directory"), ("source", "--source-snapshot"),
                           ("toolchain", "--toolchain-directory")):
            self.private[name] = Path(fields[flag])
            self.assertEqual(options["cwd"], self.private[name].parent)
        for name, original in (("evidence", self.evidence), ("toolchain", self.toolchain)):
            self.assertNotEqual(original, self.private[name])
            self.assertEqual(regular_file_inventory(original), regular_file_inventory(self.private[name]))
        self.assertEqual({fixtures._ROOT + name for name in fixtures._FILES},
                         {row["relativePath"] for row in regular_file_inventory(self.private["source"])})
        for name, contents in fixtures._FILES.items():
            self.assertEqual(contents.encode(), (self.private["source"] / (fixtures._ROOT + name)).read_bytes())
        self.assertTrue(options["check"])
        self.assertEqual(subprocess.PIPE, options["stdout"])
        self.assertEqual(subprocess.PIPE, options["stderr"])
        self.assertFalse({"JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH", "PYTHONPATH"} & set(options["env"]))
        self.mutate()
        return subprocess.CompletedProcess(command, 0)

    def verify(self, **changes):
        with mock.patch.object(content, "verified_tooling_capture", self.tooling), \
                mock.patch.object(content.subprocess, "run", side_effect=self.process):
            return replay.verify_sdk_apple_original_native_content(**{**self.arguments, **changes})

    def test_exact_mixed_producers_original_revision_private_inputs_policy_and_no_token(self):
        self.fixture.write(fixtures._ROOT + "bridge/src/lib.rs", "new HEAD source\n")
        self.fixture.write(self.fixture.pin_path, self.fixture.pins("99.0", "99A1", "99.0"))
        self.assertNotEqual(self.revision, self.fixture.commit())
        self.fixture.write(fixtures._ROOT + "include/codex_agent_ios.h", "dirty header\n")
        before = {path: regular_file_inventory(path) for path in (self.evidence, self.toolchain)}
        with mock.patch.dict("os.environ", {"JAVA_TOOL_OPTIONS": "injection", "CLASSPATH": "injection"}):
            self.assertIsNone(self.verify())
        self.assertEqual(before, {path: regular_file_inventory(path) for path in before})
        self.assertEqual(1, len(self.calls))
        self.assertTrue(all(not path.exists() for path in self.private.values()))
        self.assertEqual(b"dirty header\n", (self.fixture.repository / (fixtures._ROOT + "include/codex_agent_ios.h")).read_bytes())

    def test_bad_producers_host_and_exact_file_sets_fail_before_tooling(self):
        bad_maps = [None, {}, {**self.producers, "extra": self.producers["ios-native-tests"]}]
        for field, value in (("commit", "A" * 40), ("tree", "a" * 39), ("runId", True)):
            changed = deepcopy(self.producers)
            changed["ios-rust-device"][field] = value
            bad_maps.append(changed)
        with mock.patch.object(content, "verified_tooling_capture") as gate:
            for producers in bad_maps:
                with self.subTest(producers=producers), self.assertRaises(ValueError):
                    replay.verify_sdk_apple_original_native_content(**{**self.arguments, "original_producers": producers})
            for host in (None, "", " aarch64-apple-darwin", "aarch64-apple-darwin\n", "x86_64-unknown-linux-gnu"):
                with self.subTest(host=host), self.assertRaises(ValueError):
                    replay.verify_sdk_apple_original_native_content(**{**self.arguments, "rust_host": host})
            for directory in (self.evidence, self.toolchain):
                extra = directory / "unexpected.json"
                extra.write_bytes(b"extra\n")
                with self.assertRaisesRegex(ValueError, "exactly its fixed files"):
                    replay.verify_sdk_apple_original_native_content(**self.arguments)
                extra.unlink()
                member = next(directory.iterdir())
                contents = member.read_bytes()
                member.unlink()
                with self.assertRaises(ValueError):
                    replay.verify_sdk_apple_original_native_content(**self.arguments)
                member.write_bytes(contents)
            gate.assert_not_called()

    def test_symbolic_original_root_or_member_reject_before_tooling(self):
        alias = self.root / "evidence-link"
        alias.symlink_to(self.evidence, target_is_directory=True)
        with mock.patch.object(content, "verified_tooling_capture") as gate:
            with self.assertRaises(ValueError):
                replay.verify_sdk_apple_original_native_content(**{**self.arguments, "evidence_directory": alias})
            member = self.toolchain / "codex-agent-ios-arm64-toolchain.json"
            original = member.read_bytes()
            member.unlink()
            member.symlink_to(self.evidence / "native-tests-proof.json")
            try:
                with self.assertRaises(ValueError):
                    replay.verify_sdk_apple_original_native_content(**self.arguments)
            finally:
                member.unlink()
                member.write_bytes(original)
            gate.assert_not_called()

    def test_original_private_and_tooling_exit_mutations_fail_and_clean_private_trees(self):
        for where in ("original-evidence", "original-toolchain", "private-evidence", "private-toolchain",
                      "private-source", "producer", "context-exit"):
            with self.subTest(where=where):
                saved_producers = deepcopy(self.producers)
                evidence = self.evidence / "native-tests-proof.json"
                sidecar = self.toolchain / "codex-agent-ios-arm64-toolchain.json"
                saved = {path: path.read_bytes() for path in (evidence, sidecar)}
                def mutate():
                    if where == "producer":
                        self.producers["ios-native-tests"]["tree"] = "f" * 40
                        return
                    path = {
                        "original-evidence": evidence, "original-toolchain": sidecar,
                        "private-evidence": self.private["evidence"] / evidence.name,
                        "private-toolchain": self.private["toolchain"] / sidecar.name,
                        "private-source": self.private["source"] / (fixtures._ROOT + "bridge/src/lib.rs"),
                        "context-exit": evidence,
                    }[where]
                    path.write_bytes(b"changed\n")
                self.mutate = mutate if where != "context-exit" else lambda: None
                self.after_tooling = mutate if where == "context-exit" else lambda: None
                try:
                    with self.assertRaisesRegex(ValueError, "changed during verification"):
                        self.verify()
                    self.assertTrue(all(not path.exists() for path in self.private.values()))
                finally:
                    for path, contents in saved.items():
                        path.write_bytes(contents)
                    self.producers.clear()
                    self.producers.update(saved_producers)

    def test_source_capture_cannot_replace_originals_before_tooling_baseline(self):
        original_capture = replay.capture_apple_native_sources
        def capture(*arguments):
            result = original_capture(*arguments)
            (self.evidence / "native-tests-proof.json").write_bytes(b"replaced before verifier\n")
            return result
        with mock.patch.object(replay, "capture_apple_native_sources", side_effect=capture), \
                mock.patch.object(content, "verified_tooling_capture") as gate:
            with self.assertRaisesRegex(ValueError, "changed during verification"):
                replay.verify_sdk_apple_original_native_content(**self.arguments)
            gate.assert_not_called()

    def test_tooling_and_process_failure_propagate_without_result(self):
        with mock.patch.object(content, "verified_tooling_capture", side_effect=ValueError("policy rejected")):
            with self.assertRaisesRegex(ValueError, "policy rejected"):
                replay.verify_sdk_apple_original_native_content(**self.arguments)
        def fail():
            raise subprocess.CalledProcessError(1, "fixed verifier", stderr=b"original diagnostics\n")
        self.mutate = fail
        with self.assertRaises(subprocess.CalledProcessError) as error:
            self.verify()
        self.assertEqual(b"original diagnostics\n", error.exception.stderr)
        self.assertTrue(all(not path.exists() for path in self.private.values()))


if __name__ == "__main__":
    unittest.main()
