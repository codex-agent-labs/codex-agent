"""The caller control action pins independent inputs, but grants no Firebase trust."""

import io
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes


ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / ".github/actions/sdk-android-firebase-controls/action.yml"


class AndroidFirebaseControlsActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = ACTION.read_text()
        match = re.search(r"(?ms)^    - id: prepare\n.*?(?=^    - |\Z)", cls.action)
        assert match is not None
        cls.script = textwrap.dedent(
            match[0].split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0])
        compile(cls.script, str(ACTION), "exec")

    def fixture(self, root):
        workspace, discovery, state, scratch, independent = (
            root / name for name in ("workspace", "discovery", "state", "scratch", "independent"))
        for directory in (workspace, discovery, state, scratch, independent):
            directory.mkdir()
        source = independent / "source"
        source.write_bytes(b"original\n")
        evidence = independent / "tooling"
        evidence.mkdir()
        (evidence / "receipt").write_bytes(b"original\n")
        base = {
            "compatibilityRequest": str(source), "binaryContractEvidence": str(source),
            "trustedSourceCommit": "a" * 40, "trustedSourceTree": "b" * 40,
            "toolingEvidence": str(evidence), "toolingPublicKey": str(source),
            "javaExecutable": str(source), "apkanalyzerExecutable": str(source),
            "toolingTrustDomain": "development", "toolingKeyring": None,
            "toolingKeysDirectory": None, "trustedAndroidWorkflowSha": "c" * 40,
        }
        base_path = independent / "base-policy.json"
        raw = canonical_json_bytes(base)
        base_path.write_bytes(raw)
        output = root / "output"
        environment = {
            "GITHUB_WORKSPACE": str(workspace), "RUNNER_TEMP": str(scratch),
            "DISCOVERY_ROOT": str(discovery), "STATE_ROOT": str(state),
            "BASE_POLICY": str(base_path), "BASE_POLICY_SHA256": sha256_bytes(raw),
            "VALIDATION_RECEIPT_SHA256": "sha256:" + "d" * 64,
            "VALIDATION_ARTIFACT_ID": "17",
            "VALIDATION_ARTIFACT_SHA256": "sha256:" + "e" * 64,
            "VALIDATION_RUN_ID": "29", "VALIDATION_RUN_ATTEMPT": "2",
            "VALIDATION_ORIGINAL_MODE": "fresh",
            "GITHUB_RUN_ID": "29", "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_OUTPUT": str(output),
        }
        return environment, base, base_path, output

    def execute(self, environment):
        with patch.dict(os.environ, environment, clear=True):
            exec(compile(self.script, str(ACTION), "exec"), {})

    def test_binds_pinned_external_base_to_successful_current_run_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment, base, _, output = self.fixture(Path(temporary).resolve())
            self.execute(environment)
            control = Path(output.read_text().split("=", 1)[1].strip())
            self.assertTrue(control.is_relative_to(Path(environment["RUNNER_TEMP"])))
            value = load_canonical_json_bytes(control.read_bytes())
            self.assertEqual(base["trustedAndroidWorkflowSha"], value["trustedAndroidWorkflowSha"])
            self.assertEqual(17, value["validationArtifactId"])
            self.assertEqual((29, 2), (value["expectedOriginalRunId"],
                                       value["expectedOriginalRunAttempt"]))

    def test_rejects_unpinned_base_retained_authority_and_other_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment, base, base_path, output = self.fixture(Path(temporary).resolve())
            for changes, error, message in (
                    ({"BASE_POLICY_SHA256": "sha256:" + "0" * 64}, ValueError, "pinned digest"),
                    ({"BASE_POLICY": str(Path(environment["STATE_ROOT"]) / "base.json")},
                     ValueError, "outside checkout and retained state")):
                with self.subTest(changes=changes):
                    if "BASE_POLICY" in changes:
                        Path(changes["BASE_POLICY"]).write_bytes(base_path.read_bytes())
                    with self.assertRaisesRegex(error, message):
                        self.execute({**environment, **changes})
                    self.assertFalse(output.exists())
            stderr = io.StringIO()
            with patch("sys.stderr", stderr), self.assertRaises(SystemExit) as rejected:
                self.execute({**environment, "VALIDATION_RUN_ATTEMPT": "1"})
            self.assertEqual(2, rejected.exception.code)
            self.assertIn("selected campaign attempt", stderr.getvalue())
            self.assertFalse(output.exists())
            base["compatibilityRequest"] = str(Path(environment["STATE_ROOT"]) / "request.json")
            Path(base["compatibilityRequest"]).write_bytes(b"retained\n")
            raw = canonical_json_bytes(base)
            base_path.write_bytes(raw)
            with self.assertRaisesRegex(ValueError, "authority must be outside"):
                self.execute({**environment, "BASE_POLICY_SHA256": sha256_bytes(raw)})
            self.assertFalse(output.exists())

    def test_retained_original_keeps_older_run_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            environment, _, _, output = self.fixture(Path(temporary).resolve())
            self.execute({**environment, "VALIDATION_ORIGINAL_MODE": "retained",
                          "VALIDATION_RUN_ID": "19", "VALIDATION_RUN_ATTEMPT": "1"})
            control = Path(output.read_text().split("=", 1)[1].strip())
            value = load_canonical_json_bytes(control.read_bytes())
            self.assertEqual((19, 1), (value["expectedOriginalRunId"],
                                       value["expectedOriginalRunAttempt"]))

    def test_does_not_treat_worker_upload_as_firebase_or_release_authority(self):
        for expected in ("base-policy-sha256:", "validation-artifact-id:",
                         "validation-artifact-sha256:", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
                         "compose_control(arguments)"):
            self.assertIn(expected, self.action)
        for forbidden in ("secrets.", "PRIVATE_KEY", "ssh-keygen", "gradlew ",
                          "firebase deploy", "actions/download-artifact", "actions/upload-artifact"):
            self.assertNotIn(forbidden, self.action)


if __name__ == "__main__":
    unittest.main()
