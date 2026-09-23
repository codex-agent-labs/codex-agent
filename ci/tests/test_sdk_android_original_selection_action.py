"""Caller-side Android original selector source gates; no hosted evidence claim."""

import os
from pathlib import Path
import re
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
from products.inventory import canonical_json_bytes


class AndroidOriginalSelectionActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = (ROOT / ".github/actions/sdk-android-original-selection/action.yml").read_text()

    def source(self):
        match = re.search(r"(?ms)^    - id: select\n.*?(?=^    - |\Z)", self.action)
        self.assertIsNotNone(match)
        script = textwrap.dedent(match[0].split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0])
        compile(script, "android-original-selection", "exec")
        return script

    def test_requires_external_exact_caller_control_before_state_authentication(self):
        source = self.source()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            workspace = root / "workspace"
            workspace.mkdir()
            control = root / "original-control.json"
            control.write_bytes(canonical_json_bytes({"schemaVersion": 1}))
            values = {"GITHUB_WORKSPACE": str(workspace), "ORIGINAL_CONTROL": str(control),
                "APPLE_POLICY": "", "CORE_METADATA_POLICY": "", "ANDROID_METADATA_POLICY": ""}
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="macos-arm64"), self.assertRaisesRegex(ValueError, "Linux X64"):
                exec(compile(source, "android-selection", "exec"), {})
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"), self.assertRaises(ValueError):
                exec(compile(source, "android-selection", "exec"), {})  # Missing every original authority.
            values["ORIGINAL_CONTROL"] = str(workspace / "control.json")
            Path(values["ORIGINAL_CONTROL"]).write_bytes(control.read_bytes())
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"), self.assertRaisesRegex(ValueError, "outside source"):
                exec(compile(source, "android-selection", "exec"), {})

    def test_selected_predecessor_and_official_firebase_replay_precede_policy_output(self):
        source = self.source()
        self.assertIn("product_reuse._validate_plan(plan, root)", source)
        self.assertIn("product_reuse.materialize_product_predecessors(", source)
        self.assertIn("PhaseInstanceId('sdk', 'sdk-android', 'metadata', 'android')", source)
        self.assertIn("sha256_bytes(receipt_raw) != control['validationReceiptSha256']", source)
        self.assertIn("locator = locate_sdk_android_validation_upload(", source)
        self.assertIn("expected_receipt_sha256=control['validationReceiptSha256']", source)
        self.assertIn("if locator != {'artifact_id': control['validationArtifactId']", source)
        self.assertIn("with verified_original_android_firebase_validation(", source)
        for field in ("validationArtifactId", "validationArtifactSha256", "trustedAndroidWorkflowSha",
                      "expectedOriginalRunId", "expectedOriginalRunAttempt", "trustedSourceCommit",
                      "trustedSourceTree", "binaryContractEvidence", "compatibilityRequest"):
            self.assertIn("control['" + field + "']", source)
        self.assertLess(source.index("locator = locate_sdk_android_validation_upload("),
                        source.index("with verified_original_android_firebase_validation("))
        self.assertLess(source.index("with verified_original_android_firebase_validation("),
                        source.index("with output.open('xb')"))
        self.assertLess(source.index("with output.open('xb')"), source.index("original_policy_path="))
        self.assertIn("if output == root or root in output.parents:", source)
        self.assertLess(source.index("if output == root or root in output.parents:"),
                        source.index("with output.open('xb')"))
        self.assertIn("snapshot_policy_closure(kind, option_paths[name])", source)
        self.assertIn("regular_file_inventory(prepared, allow_empty=True) != selected_before", source)
        self.assertNotIn("locate_android_validation_upload", source)  # Current-run locator cannot authorize historical reuse.

    def test_transport_handoff_does_not_materialize_target_or_change_firebase_execution(self):
        self.assertIn("discovery-root:", self.action)
        self.assertIn("state-root:", self.action)
        self.assertIn("original-policy-path:", self.action)
        for forbidden in ("uses: ./.github/actions/setup-kmp", "uses: ./.github/actions/capture-runtime-state",
                          "secrets.", "PRIVATE_KEY", "ssh-keygen", "gradlew ",
                          "firebase deploy", "android-runtime-evidence.yml"):
            self.assertNotIn(forbidden, self.action)


if __name__ == "__main__":
    unittest.main()
