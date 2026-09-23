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
            discovery, state = root / "discovery", root / "state"
            discovery.mkdir()
            state.mkdir()
            control = root / "original-control.json"
            control.write_bytes(canonical_json_bytes({"schemaVersion": 1}))
            values = {"GITHUB_WORKSPACE": str(workspace), "ORIGINAL_CONTROL": str(control),
                "DISCOVERY": str(discovery), "STATE": str(state),
                "APPLE_POLICY": "", "CORE_METADATA_POLICY": "", "ANDROID_METADATA_POLICY": ""}
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="macos-arm64"), self.assertRaisesRegex(ValueError, "Linux X64"):
                exec(compile(source, "android-selection", "exec"), {})
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"), self.assertRaises(ValueError):
                exec(compile(source, "android-selection", "exec"), {})  # Missing every original authority.
            values["ORIGINAL_CONTROL"] = str(workspace / "control.json")
            Path(values["ORIGINAL_CONTROL"]).write_bytes(control.read_bytes())
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"), self.assertRaisesRegex(ValueError, "outside source"):
                exec(compile(source, "android-selection", "exec"), {})
            values["ORIGINAL_CONTROL"] = str(state / "control.json")
            Path(values["ORIGINAL_CONTROL"]).write_bytes(control.read_bytes())
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"), self.assertRaisesRegex(ValueError, "retained state"):
                exec(compile(source, "android-selection", "exec"), {})
            values["ORIGINAL_CONTROL"] = str(control)
            values["APPLE_POLICY"] = str(discovery / "apple.json")
            Path(values["APPLE_POLICY"]).write_bytes(control.read_bytes())
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"), self.assertRaisesRegex(ValueError, "retained state"):
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

    def test_all_original_control_authority_paths_exclude_retained_state(self):
        source = self.source()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for name in ("workspace", "discovery", "state", "independent", "independent/tooling",
                         "independent/contract-stage", "independent/execution-closure"):
                (root / name).mkdir(exist_ok=True)
            independent = root / "independent"
            for name in ("compatibility.json", "contract-receipt.json", "contract-attestation.json",
                         "contract-attestation.sig", "contract.pub", "tooling.pub", "java", "apkanalyzer"):
                (independent / name).write_bytes(b"original\n")
            contract = {"stageRoot": str(independent / "contract-stage"),
                "phaseReceipt": str(independent / "contract-receipt.json"),
                "attestation": str(independent / "contract-attestation.json"),
                "attestationSignature": str(independent / "contract-attestation.sig"),
                "publicKey": str(independent / "contract.pub"), "expectedTrustDomain": "release",
                "keyring": None, "keysDirectory": None}
            contract_file = independent / "contract.json"
            control_file = independent / "original-control.json"
            control = {"schemaVersion": 1, "validationReceiptSha256": "sha256:" + "a" * 64,
                "validationArtifactId": 4, "validationArtifactSha256": "sha256:" + "b" * 64,
                "trustedAndroidWorkflowSha": "c" * 40, "expectedOriginalRunId": 5,
                "expectedOriginalRunAttempt": 1, "compatibilityRequest": str(independent / "compatibility.json"),
                "binaryContractEvidence": str(contract_file), "trustedSourceCommit": "d" * 40,
                "trustedSourceTree": "e" * 40, "toolingEvidence": str(independent / "tooling"),
                "toolingPublicKey": str(independent / "tooling.pub"), "javaExecutable": str(independent / "java"),
                "apkanalyzerExecutable": str(independent / "apkanalyzer"), "toolingTrustDomain": "development",
                "toolingKeyring": None, "toolingKeysDirectory": None}
            plan = root / "plan.json"
            plan.write_bytes(b"{}\n")
            values = {"GITHUB_WORKSPACE": str(root / "workspace"), "DISCOVERY": str(root / "discovery"),
                "STATE": str(root / "state"), "ORIGINAL_CONTROL": str(control_file), "PLAN": str(plan),
                "TREE": "f" * 40, "BUILD_KEY": "sha256:" + "0" * 64,
                "TRUSTED_WORKFLOW_SHA": "1" * 40, "APPLE_POLICY": "", "CORE_METADATA_POLICY": "",
                "ANDROID_METADATA_POLICY": ""}

            def run(request_paths=()):
                contract_file.write_bytes(canonical_json_bytes(contract))
                control_file.write_bytes(canonical_json_bytes(control))
                with patch.dict(os.environ, values, clear=True), \
                        patch("native_wrappers.host_classifier", return_value="linux-x64"), \
                        patch("product_reuse._validate_plan", return_value={
                            "validationTree": values["TREE"], "remoteBuildAuthorized": True,
                            "validationCommit": "2" * 40}), \
                        patch("products.sdk_validation_inputs._request_inventory", return_value=set(request_paths)), \
                        patch("product_reuse.materialize_product_predecessors", side_effect=RuntimeError("elected")):
                    exec(compile(source, "android-selection", "exec"), {})

            with self.assertRaisesRegex(RuntimeError, "elected"):
                run()  # Independent sibling controls pass the path boundary.
            for name in ("compatibilityRequest", "toolingEvidence", "toolingPublicKey",
                         "javaExecutable", "apkanalyzerExecutable"):
                original = control[name]
                target = root / "state" / ("tooling" if name == "toolingEvidence" else name)
                if name == "toolingEvidence":
                    target.mkdir()
                else:
                    target.write_bytes(b"retained\n")
                control[name] = str(target)
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "caller authority"):
                    run()
                control[name] = original
            original = contract["stageRoot"]
            (root / "state/contract-stage").mkdir()
            contract["stageRoot"] = str(root / "state/contract-stage")
            with self.assertRaisesRegex(ValueError, "transitive caller authority"):
                run()
            contract["stageRoot"] = original
            original = contract["attestation"]
            (root / "state/attestation.json").write_bytes(b"retained\n")
            (root / "state/execution-closure").mkdir()
            contract["attestation"] = str(root / "state/attestation.json")
            with self.assertRaisesRegex(ValueError, "transitive caller authority"):
                run()
            contract["attestation"] = original
            (root / "state/compatibility-dependency").write_bytes(b"retained\n")
            with self.assertRaisesRegex(ValueError, "transitive caller authority"):
                run({root / "state/compatibility-dependency"})
            (independent / "keys").mkdir()
            apple = {"plan": str(plan), "attestationPublicKey": str(independent / "contract.pub"),
                "attestationTrustDomain": "development", "keyring": str(independent / "contract-receipt.json"),
                "keysDirectory": str(independent / "keys"), "toolingEvidence": str(independent / "tooling"),
                "toolingPublicKey": str(independent / "tooling.pub"), "javaExecutable": str(independent / "java"),
                "toolingTrustDomain": "development", "toolingKeyring": None, "toolingKeysDirectory": None}
            apple_file = independent / "apple-policy.json"
            apple_file.write_bytes(canonical_json_bytes(apple))
            values["APPLE_POLICY"] = str(apple_file)
            with self.assertRaisesRegex(RuntimeError, "elected"):
                run()  # Optional policy with independent trust roots still reaches selection.
            (root / "state/apple-keyring.json").write_bytes(b"retained\n")
            apple["keyring"] = str(root / "state/apple-keyring.json")
            apple_file.write_bytes(canonical_json_bytes(apple))
            with self.assertRaisesRegex(ValueError, "optional admission authority"):
                run()
            values["APPLE_POLICY"] = ""
            (root / "state/tooling-keyring.json").write_bytes(b"retained\n")
            control.update(toolingTrustDomain="release",
                toolingKeyring=str(root / "state/tooling-keyring.json"),
                toolingKeysDirectory=str(independent / "keys"))
            with self.assertRaisesRegex(ValueError, "tooling authority"):
                run()

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
