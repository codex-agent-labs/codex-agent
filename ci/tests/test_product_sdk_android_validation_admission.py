"""Android original validation composition tests; all tools are mocked."""

from contextlib import contextmanager
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci.products import sdk_android_validation_admission as admission
from ci.products.inventory import canonical_json_bytes, sha256_bytes


class AndroidValidationAdmissionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="android-validation-admission-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.final = self.root / "final"
        self.protected = self.root / "protected"
        self.aar = self.root / "binary/codex-agent-runtime-android-release.aar"
        self.aar.parent.mkdir()
        self.aar.write_bytes(b"authenticated aar")
        self.java = self.root / "tools/java"
        self.analyzer = self.root / "tools/apkanalyzer"
        self.java.parent.mkdir()
        self.java.write_bytes(b"java")
        self.analyzer.write_bytes(b"apkanalyzer")
        self.tooling = self.root / "tooling"
        self.tooling.mkdir()
        self.public_key = self.root / "tooling.pub"
        self.public_key.write_bytes(b"key")
        self.repository = self.root / "repository"
        self.repository.mkdir()
        self.jar = self.root / "tooling.jar"
        self.jar.write_bytes(b"jar")
        self.source_commit, self.source_tree = "8" * 40, "9" * 40
        self.capture_producer = self.producer(2)
        self.original_producer = self.producer(1)
        self.write_captures()

    def producer(self, attempt):
        return {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40,
            "tree": "b" * 40, "event": "pull_request", "runId": 17,
            "runAttempt": attempt, "pullRequest": 3}

    def receipt(self):
        producer = self.original_producer
        return {"schemaVersion": 2, "repository": producer["repository"],
            "workflowPath": producer["workflowPath"], "event": producer["event"],
            "runId": producer["runId"], "runAttempt": producer["runAttempt"],
            "pullRequest": producer["pullRequest"], "validationCommit": producer["commit"],
            "validationTree": producer["tree"], "lane": "android",
            "artifactName": "codex-agent-ci-android-" + producer["tree"], "result": "passed"}

    def zip_tree(self, root):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for path in reversed(sorted(path for path in root.rglob("*") if path.is_file())):
                archive.writestr(path.relative_to(root).as_posix(), path.read_bytes())
        return stream.getvalue()

    def write_captures(self):
        final_original = self.final / "original"
        evidence = final_original / "payload/external/android-runtime-evidence"
        evidence.mkdir(parents=True)
        for name, raw in {
            "android-runtime-evidence.json": b"{}\n", "firebase-test-matrix.json": b"{}\n",
            "RuntimeBootstrapDeviceTest.xml": b"<testsuite/>\n",
            "android-runtime-evidence-debug.apk": b"app",
            "android-runtime-evidence-debug-androidTest.apk": b"test",
            "codex-agent-runtime-android-release.aar": self.aar.read_bytes(),
            "firebase-android-runtime-verification.json": b"{}\n",
        }.items():
            (evidence / name).write_bytes(raw)
        final_receipt = canonical_json_bytes(self.receipt())
        (final_original / "lane-receipt.json").write_bytes(final_receipt)
        final_zip = self.zip_tree(final_original)
        (self.final / "original-upload.zip").write_bytes(final_zip)
        final_transport = {"schemaVersion": 1, "kind": "android-evidence-transport",
            "artifact": {"id": 41, "digest": sha256_bytes(final_zip)},
            "locator": {"artifact_id": 41, "artifact_sha256": sha256_bytes(final_zip)},
            "captureProducer": self.capture_producer,
            "laneReceiptSha256": sha256_bytes(final_receipt)}
        (self.final / "capture-transport.json").write_bytes(canonical_json_bytes(final_transport))

        protected_original = self.protected / "original"
        (protected_original / "results").mkdir(parents=True)
        (protected_original / "lane-receipt.json").write_bytes(final_receipt)
        (protected_original / "matrix.json").write_bytes(b"{}\n")
        (protected_original / "results/result.xml").write_bytes(b"")
        bound = {"application.apk": b"app", "lane-receipt.json": final_receipt,
                 "runtime.aar": self.aar.read_bytes(), "test.apk": b"test"}
        binding = {"schemaVersion": 1, "kind": "firebase-android-input-binding",
            "candidateCommit": self.original_producer["commit"],
            "candidateTree": self.original_producer["tree"],
            "trustedSourceCommit": self.source_commit, "trustedSourceTree": self.source_tree,
            "files": [{"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)}
                      for name, raw in sorted(bound.items())]}
        binding_bytes = canonical_json_bytes(binding)
        (protected_original / "input-binding.json").write_bytes(binding_bytes)
        protected_zip = self.zip_tree(protected_original)
        (self.protected / "original-upload.zip").write_bytes(protected_zip)
        linked = self.protected / "linked-final"
        linked.mkdir()
        final_transport_bytes = (self.final / "capture-transport.json").read_bytes()
        (linked / "capture-transport.json").write_bytes(final_transport_bytes)
        (linked / "lane-receipt.json").write_bytes(final_receipt)
        protected_transport = {"schemaVersion": 1, "kind": "android-firebase-transport",
            "artifact": {"id": 42, "digest": sha256_bytes(protected_zip)},
            "locator": {"artifact_id": 42, "artifact_sha256": sha256_bytes(protected_zip)},
            "captureProducer": self.capture_producer,
            "inputBindingSha256": sha256_bytes(binding_bytes),
            "laneReceiptSha256": sha256_bytes(final_receipt),
            "linkedFinalCaptureSha256": sha256_bytes(final_transport_bytes),
            "linkedFinalLaneReceiptSha256": sha256_bytes(final_receipt)}
        (self.protected / "capture-transport.json").write_bytes(
            canonical_json_bytes(protected_transport))

    @contextmanager
    def verified_tooling(self, *args, **kwargs):
        self.tooling_call = (args, kwargs)
        yield self.jar

    def call(self, process=None, **changes):
        arguments = dict(final_capture=self.final, protected_capture=self.protected,
            expected_binary_aar=self.aar, expected_capture_producer=self.capture_producer,
            expected_original_producer=self.original_producer,
            trusted_source_commit=self.source_commit, trusted_source_tree=self.source_tree,
            repository=self.repository, tooling_evidence=self.tooling,
            tooling_public_key=self.public_key, java_executable=self.java,
            apkanalyzer_executable=self.analyzer, policy_revision="c" * 40,
            required_trust_domain="development")
        arguments.update(changes)
        invoked = process or (lambda *args, **kwargs: subprocess.CompletedProcess(args, 0))
        with patch.object(admission, "verified_tooling_capture", side_effect=self.verified_tooling), \
                patch.object(admission.subprocess, "run", side_effect=invoked) as run:
            result = admission.verify_sdk_android_validation_original_content(**arguments)
        return result, run

    def test_exact_two_producers_source_policy_and_private_full_gate_are_forwarded(self):
        observed = {}
        def inspect(command, **kwargs):
            values = dict(zip(command[4::2], command[5::2]))
            observed["aar"] = Path(values["--expected-release-aar"]).read_bytes()
            return subprocess.CompletedProcess(command, 0)
        result, run = self.call(process=inspect)
        self.assertIsNone(result)
        command = run.call_args.args[0]
        self.assertEqual([str(self.java), "-jar", str(self.jar),
                          "verify-original-firebase-android-evidence"], command[:4])
        values = dict(zip(command[4::2], command[5::2]))
        self.assertEqual(self.original_producer["commit"], values["--candidate-commit"])
        self.assertEqual(self.original_producer["tree"], values["--candidate-tree"])
        self.assertEqual(self.source_commit, values["--trusted-source-commit"])
        self.assertEqual(self.source_tree, values["--trusted-source-tree"])
        self.assertEqual(str(self.analyzer), values["--apkanalyzer-executable"])
        self.assertNotEqual(str(self.final), values["--evidence-directory"])
        self.assertNotEqual(str(self.protected), values["--protected-observation-directory"])
        self.assertEqual(self.aar.read_bytes(), observed["aar"])
        self.assertEqual(2, self.capture_producer["runAttempt"])
        self.assertEqual(1, self.original_producer["runAttempt"])
        self.assertEqual("development", self.tooling_call[1]["required_trust_domain"])

    def test_transports_cannot_select_current_original_or_source_authority(self):
        for name, change in (
            ("capture", {"expected_capture_producer": self.producer(3)}),
            ("original", {"expected_original_producer": self.producer(3)}),
            ("source", {"trusted_source_commit": "f" * 40}),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.call(**change)

    def test_zip_extraction_linkage_and_authenticated_aar_are_immutable(self):
        cases = {
            "final-original": self.final / "original/lane-receipt.json",
            "protected-original": self.protected / "original/matrix.json",
            "linked-final": self.protected / "linked-final/capture-transport.json",
            "binary": self.aar,
        }
        for name, path in cases.items():
            raw = path.read_bytes()
            path.write_bytes(raw + b"changed")
            try:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    self.call()
            finally:
                path.write_bytes(raw)

    def test_tool_failure_and_late_original_mutation_never_become_success(self):
        def fail(*args, **kwargs):
            raise subprocess.CalledProcessError(7, args[0])
        with self.assertRaises(subprocess.CalledProcessError):
            self.call(process=fail)

        raw = self.aar.read_bytes()
        def mutate(*args, **kwargs):
            self.aar.write_bytes(b"late mutation")
            return subprocess.CompletedProcess(args, 0)
        try:
            with self.assertRaisesRegex(ValueError, "inputs or trusted tools changed"):
                self.call(process=mutate)
        finally:
            self.aar.write_bytes(raw)


if __name__ == "__main__":
    unittest.main()
