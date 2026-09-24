"""Android metadata composite gates; source checks, not hosted Firebase proof."""

import json
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
from products.inventory import canonical_json_bytes, sha256_bytes

KEY = "sha256:" + "a" * 64
TREE = "b" * 40


class AndroidMetadataWorkerActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = (ROOT / ".github/actions/sdk-android-metadata-worker/action.yml").read_text()

    def source(self, step):
        match = re.search(rf"(?ms)^    - id: {re.escape(step)}\n.*?(?=^    - |\Z)", self.action)
        self.assertIsNotNone(match, step)
        source = textwrap.dedent(match[0].split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0])
        compile(source, "android-metadata-" + step, "exec")
        return source

    def original(self, root):
        independent = root / "independent"
        independent.mkdir()
        contract = independent / "contract.json"
        contract.write_bytes(canonical_json_bytes({"caller": "contract"}))
        path = independent / "input"
        path.write_text("original")
        return {
            "schemaVersion": 1, "packageStage": str(independent), "packageReceipt": str(path),
            "binaryStage": str(independent), "binaryReceipt": str(path),
            "compatibilityRequest": str(path), "binaryContractEvidence": str(contract),
            "trustedSourceCommit": "c" * 40, "trustedSourceTree": "d" * 40,
            "toolingEvidence": str(independent), "toolingPublicKey": str(path),
            "javaExecutable": str(path), "apkanalyzerExecutable": str(path),
            "toolingTrustDomain": "development", "toolingKeyring": None, "toolingKeysDirectory": None,
            "validationArtifactId": 12, "validationArtifactSha256": KEY,
            "validationReceiptSha256": "sha256:" + "f" * 64,
            "trustedAndroidWorkflowSha": "e" * 40, "expectedOriginalRunId": 23,
            "expectedOriginalRunAttempt": 2,
        }

    def environment(self, root, original):
        workspace = root / "workspace"
        workspace.mkdir(exist_ok=True)
        policy = root / "original-policy.json"
        policy.write_bytes(canonical_json_bytes(original))
        return {"GITHUB_WORKSPACE": str(workspace), "GITHUB_OUTPUT": str(root / "github-output"),
            "SDK_STATE_WAVE": "17", "ORIGINAL_POLICY": str(policy), "APPLE_POLICY": "",
            "CORE_METADATA_POLICY": "", "ANDROID_METADATA_POLICY": ""}

    def test_full_external_original_policy_rejects_missing_firebase_lineage_before_capture(self):
        self.assertLess(self.action.index("- id: policy"), self.action.index("- id: captured"))
        self.assertLess(self.action.index("- id: captured"), self.action.index("- id: identity"))
        self.assertLess(self.action.index("- id: identity"), self.action.index("uses: ./.github/actions/setup-kmp"))
        self.assertIn("sdk-family: android-metadata", self.action)
        source = self.source("policy")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = self.original(root)
            values = self.environment(root, original)
            with patch.dict(os.environ, values, clear=True), patch(
                    "products.sdk_validation_inputs._request_inventory", return_value={}), patch(
                    "products.sdk_android_validation_phase._contract_sources", return_value=({}, {})):
                exec(compile(source, "android-policy", "exec"), {})
            values["SDK_STATE_WAVE"] = "16"
            with patch.dict(os.environ, values, clear=True), self.assertRaisesRegex(ValueError, "wave 17"):
                exec(compile(source, "android-policy", "exec"), {})
            values["SDK_STATE_WAVE"] = "17"
            for field in ("validationArtifactId", "validationArtifactSha256", "validationReceiptSha256",
                          "trustedAndroidWorkflowSha",
                          "expectedOriginalRunId", "expectedOriginalRunAttempt", "binaryContractEvidence"):
                policy = {key: value for key, value in original.items() if key != field}
                Path(values["ORIGINAL_POLICY"]).write_bytes(canonical_json_bytes(policy))
                with self.subTest(field=field), patch.dict(os.environ, values, clear=True), patch(
                        "products.sdk_validation_inputs._request_inventory", return_value={}), patch(
                        "products.sdk_android_validation_phase._contract_sources", return_value=({}, {})), self.assertRaises(ValueError):
                    exec(compile(source, "android-policy", "exec"), {})
            Path(values["ORIGINAL_POLICY"]).write_bytes(canonical_json_bytes(original))
            values["ORIGINAL_POLICY"] = str(Path(values["GITHUB_WORKSPACE"]) / "policy.json")
            Path(values["ORIGINAL_POLICY"]).write_bytes(canonical_json_bytes(original))
            with patch.dict(os.environ, values, clear=True), self.assertRaisesRegex(ValueError, "external"):
                exec(compile(source, "android-policy", "exec"), {})

    def test_exact_android_metadata_election_host_and_control_lifetime(self):
        source = self.source("identity")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = self.original(root)
            values = self.environment(root, original)
            contract = Path(original["binaryContractEvidence"])
            with patch.dict(os.environ, values, clear=True), patch(
                    "products.sdk_validation_inputs._request_inventory", return_value={}), patch(
                    "products.sdk_android_validation_phase._contract_sources", return_value=({}, {})):
                exec(compile(self.source("policy"), "android-policy", "exec"), {})
            digest = (root / "github-output").read_text().strip().split("=", 1)[1]
            plan = root / "plan.json"
            plan.write_text(json.dumps({"validationTree": TREE}))
            state = root / "state"
            state.mkdir()
            (state / "reuse-wave-result.json").write_bytes(canonical_json_bytes({"phases": [{
                "product": "sdk", "component": "sdk-android", "phase": "validation",
                "target": "android", "receiptSha256": original["validationReceiptSha256"]}]}))
            row = {"product": "sdk", "component": "sdk-android", "phase": "metadata", "target": "android",
                   "runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64", "buildKey": KEY}
            values.update(MATRIX=json.dumps({"include": [row]}), REQUIRED="true", PLAN=str(plan),
                          STATE=str(state), BUILD_KEY=KEY, TREE=TREE, POLICY_SHA256=digest)
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"), patch(
                    "products.sdk_validation_inputs._request_inventory", return_value={}), patch(
                    "products.sdk_android_validation_phase._contract_sources", return_value=({}, {})):
                exec(compile(source, "android-identity", "exec"), {})
            (state / "reuse-wave-result.json").write_bytes(canonical_json_bytes({"phases": [{
                "product": "sdk", "component": "sdk-android", "phase": "validation",
                "target": "android", "receiptSha256": "sha256:" + "0" * 64}]}))
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"), patch(
                    "products.sdk_validation_inputs._request_inventory", return_value={}), patch(
                    "products.sdk_android_validation_phase._contract_sources", return_value=({}, {})), self.assertRaisesRegex(ValueError, "successful worker output"):
                exec(compile(source, "android-identity", "exec"), {})
            (state / "reuse-wave-result.json").write_bytes(canonical_json_bytes({"phases": [{
                "product": "sdk", "component": "sdk-android", "phase": "validation",
                "target": "android", "receiptSha256": original["validationReceiptSha256"]}]}))
            for changed in ({"target": "common"}, {"runner": "ubuntu-latest"}, {"buildKey": "sha256:" + "0" * 64}):
                values["MATRIX"] = json.dumps({"include": [{**row, **changed}]})
                with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"), patch(
                        "products.sdk_validation_inputs._request_inventory", return_value={}), patch(
                        "products.sdk_android_validation_phase._contract_sources", return_value=({}, {})), self.assertRaisesRegex(ValueError, "elected host"):
                    exec(compile(source, "android-identity", "exec"), {})
            values["MATRIX"] = json.dumps({"include": [row]})
            contract.write_bytes(canonical_json_bytes({"changed": True}))
            with patch.dict(os.environ, values, clear=True), patch(
                    "products.sdk_validation_inputs._request_inventory", return_value={}), patch(
                    "products.sdk_android_validation_phase._contract_sources", return_value=({}, {})), self.assertRaisesRegex(ValueError, "changed during state capture"):
                exec(compile(source, "android-identity", "exec"), {})
            contract.write_bytes(canonical_json_bytes({"caller": "contract"}))
            (root / "independent/new-file").write_text("mutated stage")
            with patch.dict(os.environ, values, clear=True), patch(
                    "products.sdk_validation_inputs._request_inventory", return_value={}), patch(
                    "products.sdk_android_validation_phase._contract_sources", return_value=({}, {})), self.assertRaisesRegex(ValueError, "changed during state capture"):
                exec(compile(source, "android-identity", "exec"), {})

    def test_optional_admission_closure_is_pinned_not_only_its_json(self):
        policy_source, identity_source = self.source("policy"), self.source("identity")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = self.original(root)
            values = self.environment(root, original)
            apple = root / "apple.json"
            apple.write_bytes(canonical_json_bytes({"caller": "apple"}))
            values["APPLE_POLICY"] = str(apple)
            with patch.dict(os.environ, values, clear=True), patch(
                    "products.sdk_validation_inputs._request_inventory", return_value={}), patch(
                    "products.sdk_android_validation_phase._contract_sources", return_value=({}, {})), patch(
                    "ci.sdk_policy_snapshot.snapshot_policy_closure", return_value=KEY) as closure:
                exec(compile(policy_source, "android-policy", "exec"), {})
            closure.assert_called_once_with("apple-validation", apple)
            values.update(MATRIX=json.dumps({"include": []}), REQUIRED="false", PLAN=str(root / "plan.json"),
                          BUILD_KEY=KEY, TREE=TREE,
                          POLICY_SHA256=(root / "github-output").read_text().strip().split("=", 1)[1])
            with patch.dict(os.environ, values, clear=True), patch(
                    "products.sdk_validation_inputs._request_inventory", return_value={}), patch(
                    "products.sdk_android_validation_phase._contract_sources", return_value=({}, {})), patch(
                    "ci.sdk_policy_snapshot.snapshot_policy_closure", return_value="sha256:" + "0" * 64), self.assertRaisesRegex(ValueError, "changed during state capture"):
                exec(compile(identity_source, "android-identity", "exec"), {})

    def test_existing_observed_controller_receives_every_original_pin_and_diagnostics(self):
        script = self.source("execute")
        compile(script, "android-metadata-execute", "exec")
        for flag in ("--validation-artifact-id", "--validation-artifact-sha256",
                     "--expected-validation-receipt-sha256",
                     "--trusted-workflow-sha", "--trusted-android-workflow-sha",
                     "--expected-original-run-id", "--expected-original-run-attempt",
                     "--binary-contract-evidence", "--trusted-source-commit", "--trusted-source-tree"):
            self.assertIn("'" + flag + "'", script)
        self.assertIn("'ci.sdk_workflow', 'android-metadata'", script)
        self.assertNotIn("--original-validation-capture", script)  # Observed mode; no unauthenticated retained carrier.
        self.assertIn("if: always() && steps.identity.outcome == 'success'", self.action)
        self.assertIn("attempt-${{ github.run_attempt }}", self.action)
        for forbidden in ("secrets.", "PRIVATE_KEY", "ssh-keygen", "gradlew "):
            self.assertNotIn(forbidden, self.action)

    def test_original_locator_outputs_require_execution_and_official_upload(self):
        self.assertIn("- id: execute\n", self.action)
        self.assertIn("- id: upload\n", self.action)
        for name in ("metadata-receipt-sha256", "metadata-artifact-id",
                     "metadata-artifact-sha256", "metadata-run-id", "metadata-run-attempt"):
            match = re.search(rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-z][\w-]*:|^runs:)", self.action)
            self.assertIsNotNone(match, name)
            expression = match[1]
            self.assertIn("steps.execute.outcome == 'success'", expression)
            self.assertIn("steps.upload.outcome == 'success'", expression)
            self.assertIn("steps.execute.outputs.receipt_sha256 != ''", expression)
        script = self.source("execute")
        self.assertIn("verify_phase_shard(root / 'build/sdk-android-metadata-worker/shard'", script)
        self.assertIn("producer['runId'] != int(os.environ['GITHUB_RUN_ID'])", script)
        self.assertIn("producer['runAttempt'] != int(os.environ['GITHUB_RUN_ATTEMPT'])", script)
        self.assertIn("output.write('receipt_sha256=' + shard['receiptSha256']", script)


if __name__ == "__main__":
    unittest.main()
