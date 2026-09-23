"""Core Maven composite guards; source-level checks, not hosted product proof."""

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
from ci.products.inventory import canonical_json_bytes, sha256_bytes

KEY = "sha256:" + "a" * 64
TREE = "b" * 40


class SdkCoreMavenWorkerActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = (ROOT / ".github/actions/sdk-core-maven-worker/action.yml").read_text()

    def source(self, step):
        match = re.search(rf"(?ms)^    - id: {re.escape(step)}\n.*?(?=^    - |\Z)", self.action)
        self.assertIsNotNone(match, step)
        block = match[0]
        script = textwrap.dedent(block.split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0])
        compile(script, "core-maven-" + step, "exec")
        return script

    def environment(self, root, phase):
        values = {name: "" for name in (
            "SDK_INPUTS_ID", "SDK_INPUTS_SHA256", "BINARY_ARTIFACT_ID",
            "BINARY_ARTIFACT_SHA256", "BINARY_CONTRACT_EVIDENCE", "BINARY_ORIGINAL_CONTEXT",
            "SDK_VALIDATION_TOOLING", "SDK_APPLE_VALIDATION_POLICY",
            "SDK_FACADE_METADATA_POLICY", "SDK_ANDROID_METADATA_POLICY")}
        values.update(PHASE=phase, GITHUB_OUTPUT=str(root / "github-output"))
        if phase == "package":
            values.update(SDK_INPUTS_ID="1", SDK_INPUTS_SHA256=KEY,
                          BINARY_ARTIFACT_ID="2", BINARY_ARTIFACT_SHA256=KEY)
            for name in ("BINARY_CONTRACT_EVIDENCE", "BINARY_ORIGINAL_CONTEXT"):
                path = root / (name.lower() + ".json")
                path.write_bytes(canonical_json_bytes({"caller": name}))
                values[name] = str(path)
        return values

    def test_policy_rejects_missing_originals_and_noncanonical_or_relative_policy(self):
        script = self.source("policy")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for phase in ("binary", "package"):
                with patch.dict(os.environ, self.environment(root, phase), clear=True):
                    exec(compile(script, "core-policy", "exec"), {})
            value = self.environment(root, "package")
            value["BINARY_ARTIFACT_SHA256"] = ""
            with patch.dict(os.environ, value, clear=True), self.assertRaisesRegex(ValueError, "all original"):
                exec(compile(script, "core-policy", "exec"), {})
            value = self.environment(root, "package")
            value["BINARY_ARTIFACT_SHA256"] = "sha256:" + "Z" * 64
            with patch.dict(os.environ, value, clear=True), self.assertRaisesRegex(ValueError, "lowercase"):
                exec(compile(script, "core-policy", "exec"), {})
            value = self.environment(root, "package")
            value["BINARY_ARTIFACT_ID"] = "0"
            with patch.dict(os.environ, value, clear=True), self.assertRaisesRegex(ValueError, "positive"):
                exec(compile(script, "core-policy", "exec"), {})
            value = self.environment(root, "binary")
            value["SDK_INPUTS_ID"] = "1"
            with patch.dict(os.environ, value, clear=True), self.assertRaisesRegex(ValueError, "accepts none"):
                exec(compile(script, "core-policy", "exec"), {})
            value = self.environment(root, "binary")
            value["SDK_FACADE_METADATA_POLICY"] = "relative.json"
            with patch.dict(os.environ, value, clear=True), self.assertRaisesRegex(ValueError, "absolute"):
                exec(compile(script, "core-policy", "exec"), {})

    def test_exact_phase_route_host_tree_and_policy_pin_before_setup(self):
        self.assertLess(self.action.index("- id: policy"), self.action.index("- id: captured"))
        self.assertLess(self.action.index("- id: captured"), self.action.index("- id: identity"))
        self.assertLess(self.action.index("- id: identity"), self.action.index("uses: ./.github/actions/setup-kmp"))
        self.assertIn("sdk-family: core-${{ inputs.phase }}", self.action)
        self.assertIn("cache-read-only: 'true'", self.action)
        self.assertIn("product-worker: 'true'", self.action)
        script = self.source("identity")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            plan = root / "plan.json"
            plan.write_text(json.dumps({"validationTree": TREE}))
            for phase, host, runner in (("binary", "macos-arm64", ("macos-26", "macOS", "ARM64")),
                                         ("package", "linux-x64", ("ubuntu-24.04", "Linux", "X64"))):
                row = dict(zip(("runner", "runnerOs", "runnerArch"), runner))
                row.update(product="sdk", component="sdk-core", phase=phase, target="common", buildKey=KEY)
                values = self.environment(root, phase)
                policy = {name: sha256_bytes(Path(values[name]).read_bytes())
                          for name in ("BINARY_CONTRACT_EVIDENCE", "BINARY_ORIGINAL_CONTEXT") if values[name]}
                values.update(MATRIX=json.dumps({"include": [row]}), REQUIRED="true", PLAN=str(plan),
                              BUILD_KEY=KEY, TREE=TREE,
                              POLICY_SHA256=sha256_bytes(canonical_json_bytes(policy)))
                for selected_host, selected_row in ((host, row), ("wrong-host", row),
                                                     (host, {**row, "target": "android"})):
                    values["MATRIX"] = json.dumps({"include": [selected_row]})
                    with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value=selected_host):
                        if selected_host == host and selected_row == row:
                            exec(compile(script, "core-identity", "exec"), {})
                        else:
                            with self.assertRaisesRegex(ValueError, "elected host"):
                                exec(compile(script, "core-identity", "exec"), {})

    def test_existing_controllers_receive_exact_caller_inputs_and_attempt_is_retained(self):
        source = self.source("execute")
        for flag in ("--sdk-inputs-artifact-id", "--sdk-inputs-artifact-sha256",
                     "--binary-artifact-id", "--binary-artifact-sha256",
                     "--binary-contract-evidence", "--binary-original-context",
                     "--trusted-workflow-sha", "--keyring", "--keys-directory",
                     "--sdk-facade-metadata-policy", "--sdk-android-metadata-policy"):
            self.assertIn("'" + flag + "'", source)
        self.assertIn("'maven-' + phase", source)
        self.assertIn("if: always() && steps.identity.outcome == 'success'", self.action)
        self.assertIn("attempt-${{ github.run_attempt }}", self.action)
        self.assertIn("if-no-files-found: warn", self.action)
        self.assertIn("overwrite: false", self.action)
        for forbidden in ("secrets.", "PRIVATE_KEY", "ssh-keygen", "gradlew "):
            self.assertNotIn(forbidden, self.action)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for phase in ("binary", "package"):
                values = self.environment(root, phase)
                policies = {name: sha256_bytes(Path(values[name]).read_bytes())
                            for name in ("BINARY_CONTRACT_EVIDENCE", "BINARY_ORIGINAL_CONTEXT") if values[name]}
                values.update(GITHUB_WORKSPACE=str(ROOT), PLAN=str(root / "plan.json"),
                              DISCOVERY=str(root / "discovery"), STATE=str(root / "state"),
                              BUILD_KEY=KEY, POLICY_SHA256=sha256_bytes(canonical_json_bytes(policies)),
                              TRUSTED_WORKFLOW_SHA="c" * 40)
                with patch.dict(os.environ, values, clear=True), patch("subprocess.run") as run:
                    exec(compile(source, "core-execute", "exec"), {})
                command = run.call_args.args[0]
                self.assertEqual([sys.executable, "-B", "-m", "ci.sdk_workflow", "maven-" + phase],
                                 command[:5])
                self.assertEqual("sdk-core", command[command.index("--component") + 1])
                self.assertEqual(KEY, command[command.index("--expected-build-key") + 1])
                if phase == "package":
                    for flag in ("--sdk-inputs-artifact-id", "--sdk-inputs-artifact-sha256",
                                 "--binary-artifact-id", "--binary-artifact-sha256",
                                 "--binary-contract-evidence", "--binary-original-context"):
                        self.assertIn(flag, command)
                else:
                    self.assertNotIn("--binary-artifact-id", command)


if __name__ == "__main__":
    unittest.main()
