"""Synthetic external-context checks, not upload/signature/Apple acceptance."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, regular_file_inventory, sha256_file
from ci.products import sdk_apple_validation_context as module


class AppleValidationContextTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-validation-context-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.archive = self.root / "apple-validation-evidence.zip"
        self.archive.write_bytes(b"synthetic raw archive; no ZIP or execution admission\x00\xff")
        self.path = self.root / "execution-context.json"
        self.producer = {
            "repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/ci.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 71, "runAttempt": 2, "pullRequest": 8,
        }
        self.working = "/historical/runner/repository/codex-agent-runtime-ios"
        self.value = {
            "schemaVersion": 1, "producer": dict(self.producer), "target": "ios-arm64",
            "packageArtifact": {"artifactId": 21, "artifactSha256": "sha256:" + "1" * 64},
            "binaryArtifact": {"artifactId": 22, "artifactSha256": "sha256:" + "2" * 64},
            "rustHost": "aarch64-apple-darwin", "developerDirectory": "/historical/Xcode.app/Contents/Developer",
            "originalWorkingDirectory": self.working,
            "originalDeviceWorkDirectory": self.execution("ios-arm64") + "/device-execution",
            "originalTestApplicationDirectory": self.execution("ios-arm64") + "/device-consumer/CodexAgentTestApp",
            "evidenceSha256": sha256_file(self.archive),
        }
        self.write()

    def execution(self, target):
        return self.working + "/build/imported-sdk-validation/" + self.producer["tree"] + "/" + target

    def write(self, value=None):
        self.path.write_bytes(canonical_json_bytes(self.value if value is None else value))

    def verify(self, **changes):
        return module.verify_apple_validation_context(self.path, **{
            "producer": self.producer, "target": "ios-arm64", "evidence_archive": self.archive,
            **changes,
        })

    def test_both_targets_preserve_exact_bytes_and_do_not_require_historical_paths(self):
        for target in ("ios-arm64", "ios-simulator-arm64"):
            value = {**self.value, "target": target,
                     "originalDeviceWorkDirectory": self.execution(target) + "/device-execution",
                     "originalTestApplicationDirectory": self.execution(target) + "/device-consumer/CodexAgentTestApp"}
            self.write(value)
            before = regular_file_inventory(self.root)
            result = self.verify(target=target, original_working_directory=self.working)
            self.assertEqual(value, result)
            self.assertEqual(before, regular_file_inventory(self.root))
            result["producer"]["runId"] = 999
            self.assertEqual(71, self.producer["runId"])
            self.assertEqual(canonical_json_bytes(value), self.path.read_bytes())

    def test_schema_producer_target_host_locator_and_digest_mutations_reject(self):
        mutations = [
            lambda v: v.update(schemaVersion=True), lambda v: v.update(schemaVersion="1"),
            lambda v: v.update(schemaVersion=2), lambda v: v.update(unexpected="field"),
            lambda v: v.pop("evidenceSha256"), lambda v: v["producer"].update(runAttempt=3),
            lambda v: v["producer"].update(tree="c" * 40),
            lambda v: v["producer"].update(commit="d" * 40),
            lambda v: v["producer"].update(unexpected="field"),
            lambda v: v.update(target="ios-simulator-arm64"), lambda v: v.update(target="ios"),
            lambda v: v.update(rustHost="x86_64-apple-darwin"),
            lambda v: v.update(evidenceSha256="sha256:" + "0" * 64),
            lambda v: v.update(evidenceSha256="0" * 64),
        ]
        for name in ("packageArtifact", "binaryArtifact"):
            for field, replacement in (("artifactId", True), ("artifactId", 0), ("artifactId", "21"),
                                       ("artifactSha256", "bad"), ("extra", "field")):
                mutations.append(lambda v, name=name, field=field, replacement=replacement:
                                 v[name].update({field: replacement}))
        for index, mutate in enumerate(mutations):
            value = deepcopy(self.value)
            mutate(value)
            self.write(value)
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.verify()

    def test_paths_are_exact_posix_and_derived_from_selected_producer_target(self):
        for name in ("developerDirectory", "originalWorkingDirectory", "originalDeviceWorkDirectory",
                     "originalTestApplicationDirectory"):
            original = self.value[name]
            for value in ("relative", "//host/path", original + "/", original + "/..", original + "/./x",
                          original.replace("/", "//", 1), original + "\\x", original + "\n", original + "\x85",
                          None, 1):
                self.write({**self.value, name: value})
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    self.verify()
        for name, value in (
            ("originalWorkingDirectory", "/historical/not-the-ios-module"),
            ("originalDeviceWorkDirectory", self.execution("ios-simulator-arm64") + "/device-execution"),
            ("originalTestApplicationDirectory", self.execution("ios-arm64") + "/device-consumer/WrongApp"),
        ):
            self.write({**self.value, name: value})
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.verify()
        self.write()
        for expected in ("relative", "/another/codex-agent-runtime-ios"):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                self.verify(original_working_directory=expected)

    def test_malformed_duplicate_noncanonical_and_symlink_inputs_reject(self):
        valid = self.path.read_bytes()
        for raw in (b"\xff", valid + b" ", valid.replace(b'"schemaVersion":1', b'"schemaVersion":1,"schemaVersion":1')):
            self.path.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.verify()
        self.path.write_bytes(valid)
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            module.verify_apple_validation_context(alias / self.path.name, producer=self.producer,
                target="ios-arm64", evidence_archive=self.archive)
        with self.assertRaises(ValueError):
            self.verify(evidence_archive=alias / self.archive.name)
        link = self.root / "archive-link"
        link.symlink_to(self.archive)
        with self.assertRaises(ValueError):
            self.verify(evidence_archive=link)

    def test_late_context_archive_and_caller_mutation_fail_closed(self):
        context_raw, archive_raw = self.path.read_bytes(), self.archive.read_bytes()
        for field in ("context", "archive", "producer"):
            calls = []

            def digest(path):
                value = sha256_file(path)
                calls.append(path)
                if len(calls) == 1:
                    if field == "context":
                        self.path.write_bytes(context_raw + b" ")
                    elif field == "archive":
                        self.archive.write_bytes(archive_raw + b"changed")
                    else:
                        self.producer["runId"] = 999
                return value

            with self.subTest(field=field), patch.object(module, "sha256_file", side_effect=digest), \
                    self.assertRaises(ValueError):
                self.verify()
            self.path.write_bytes(context_raw)
            self.archive.write_bytes(archive_raw)
            self.producer["runId"] = 71


if __name__ == "__main__":
    unittest.main()
