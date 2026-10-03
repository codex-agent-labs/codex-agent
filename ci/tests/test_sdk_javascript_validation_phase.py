"""Original validation boundaries; simulated tooling is not parity acceptance."""

from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes
from ci.products.sdk_javascript_validation_phase import verify_sdk_javascript_validation_phase
from ci.tests import test_sdk_javascript_metadata_admission as admission_fixture


class JavaScriptValidationPhaseTest(unittest.TestCase):
    def setUp(self):
        fixture = admission_fixture.SdkJavaScriptMetadataAdmissionTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        support = fixture.support
        self.arguments = {name: support.args[name] for name in (
            "repository", "contract_stage", "contract_receipt", "package_stage", "package_receipt",
            "validation_stage", "validation_receipt", "runtime_validation_stage",
            "runtime_validation_receipt", "original_consumer_directory", "tooling_evidence",
            "tooling_public_key", "java_executable", "policy_revision", "required_trust_domain",
        )}
        self.arguments["tooling_keyring"] = None
        self.arguments["tooling_keys_directory"] = None
        self.replay_bytes = support.content
        self.calls = []

    @contextmanager
    def tooling(self, evidence, repository, public_key, **kwargs):
        self.assertEqual((evidence, repository, public_key), (
            self.arguments["tooling_evidence"], self.arguments["repository"],
            self.arguments["tooling_public_key"]))
        self.assertEqual(kwargs["policy_revision"], self.arguments["policy_revision"])
        yield self.fixture.support.jar

    def process(self, command, **kwargs):
        if command[0] == "git":
            return admission_fixture._RUN(command, **kwargs)
        self.assertEqual(command[:4], [str(self.arguments["java_executable"]), "-jar",
            str(self.fixture.support.jar), "write-javascript-metadata-content"])
        fields = dict(zip(command[4::2], command[5::2]))
        self.calls.append(fields)
        self.assertEqual(fields["--original-consumer-directory"], str(self.arguments["original_consumer_directory"]))
        self.assertEqual(fields["--runtime-version"], "0.2.7")
        self.assertTrue(kwargs["check"])
        self.assertEqual((kwargs["stdout"], kwargs["stderr"]), (subprocess.PIPE, subprocess.PIPE))
        self.assertNotIn("JAVA_TOOL_OPTIONS", kwargs["env"])
        Path(fields["--content-output"]).write_bytes(self.replay_bytes)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    def verify(self, **overrides):
        with patch("ci.products.sdk_javascript_validation_phase.verified_tooling_capture", self.tooling), \
                patch("ci.products.sdk_javascript_validation_phase.subprocess.run", self.process):
            return verify_sdk_javascript_validation_phase(**(self.arguments | overrides))

    def test_original_git_plan_runtime_predecessor_and_complete_replay(self):
        receipt, raw = self.verify()
        self.assertEqual(raw, self.arguments["validation_receipt"].read_bytes())
        self.assertEqual(receipt["producer"]["commit"], self.fixture.validation_commit)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["--contract-version"], "0.2.0")
        self.assertEqual(self.calls[0]["--sdk-version"], "0.3.0")

    def test_wrong_runtime_receipt_rejected_before_matcher(self):
        runtime = self.arguments["runtime_validation_receipt"]
        changed = self.fixture.support.receipts["runtime"].copy()
        changed["outputs"] = [dict(record) for record in changed["outputs"]]
        changed["outputs"][0]["sha256"] = "sha256:" + "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "runtime.json"
            path.write_bytes(canonical_json_bytes(changed))
            with self.assertRaisesRegex(ValueError, "original producer plan"):
                self.verify(runtime_validation_receipt=path)
        self.assertFalse(self.calls)

    def test_original_consumer_source_and_replayed_behavior_must_match(self):
        program = self.arguments["validation_stage"] / "outputs/test-program/smoke.cjs"
        original = program.read_bytes()
        try:
            program.write_bytes(b"changed consumer program\n")
            with self.assertRaisesRegex(ValueError, "original Git source"):
                self.verify()
            self.assertFalse(self.calls)
        finally:
            program.write_bytes(original)
        self.replay_bytes = b'{"different":"behavior"}\n'
        with self.assertRaisesRegex(ValueError, "full authenticated replay"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
