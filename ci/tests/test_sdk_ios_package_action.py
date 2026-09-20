"""iOS package composite routing checks; no Apple or product execution."""

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
KEY = "sha256:" + "a" * 64
TREE = "b" * 40


class SdkIosPackageActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = (ROOT / ".github/actions/sdk-ios-package-worker/action.yml").read_text()

    def block(self, step):
        match = re.search(rf"(?ms)^    - id: {re.escape(step)}\n.*?(?=^    - |\Z)", self.action)
        self.assertIsNotNone(match, step)
        return match[0]

    def identity(self, *, rows, required="true", component="sdk-ios", host="macos-arm64"):
        block = self.block("identity")
        source = textwrap.dedent(block.split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0])
        with tempfile.TemporaryDirectory(prefix="sdk-ios-package-action-") as temporary:
            root = Path(temporary).resolve()
            plan, policy, output = (root / name for name in ("plan", "policy", "output"))
            plan.write_text(json.dumps({"validationTree": TREE}))
            policy.write_bytes(b"policy\n")
            environment = {"MATRIX": json.dumps({"include": rows}), "REQUIRED": required,
                "PLAN": str(plan), "COMPONENT": component, "BUILD_KEY": KEY, "TREE": TREE,
                "SDK_VALIDATION_TOOLING": str(policy),
                "POLICY_SHA256": "sha256:" + __import__("hashlib").sha256(policy.read_bytes()).hexdigest(),
                "GITHUB_OUTPUT": str(output)}
            with patch.dict(os.environ, environment, clear=True), \
                    patch("native_wrappers.host_classifier", return_value=host):
                valid = (required, component, host) == ("true", "sdk-ios", "macos-arm64") and len(rows) == 1 and rows[0] == {
                    "product": "sdk", "component": "sdk-ios", "phase": "package", "target": "ios",
                    "buildKey": KEY, "runnerOs": "macOS", "runnerArch": "ARM64",
                }
                if not valid:
                    with self.assertRaises(ValueError):
                        exec(compile(source, "ios-package-identity", "exec"), {})
                    self.assertFalse(output.exists())
                    return
                exec(compile(source, "ios-package-identity", "exec"), {})
            self.assertEqual("key_hex=" + "a" * 64 + "\n", output.read_text())

    def test_policy_state_and_exact_identity_precede_read_only_apple_setup(self):
        policy = self.action.index("- id: policy")
        capture = self.action.index("- id: captured")
        identity = self.action.index("- id: identity")
        setup = self.action.index("uses: ./.github/actions/setup-kmp")
        self.assertLess(policy, capture)
        self.assertLess(capture, identity)
        self.assertLess(identity, setup)
        for value in ("product: sdk", "sdk-family: ios-package", "cache-read-only: 'true'",
                      "product-worker: 'true'", "xcode-fingerprint: auto"):
            self.assertIn(value, self.action)
        row = {"product": "sdk", "component": "sdk-ios", "phase": "package", "target": "ios",
               "buildKey": KEY, "runnerOs": "macOS", "runnerArch": "ARM64"}
        self.identity(rows=[row])
        for changes in ({"required": "false"}, {"component": "other"}, {"host": "macos-x64"},
                        {"rows": []}, {"rows": [{**row, "runnerArch": "X64"}]}):
            with self.subTest(changes=changes):
                self.identity(rows=changes.get("rows", [row]), required=changes.get("required", "true"),
                              component=changes.get("component", "sdk-ios"), host=changes.get("host", "macos-arm64"))

    def test_fixed_cli_forwards_every_authenticated_locator_and_policy_input(self):
        self.assertIn("'-m', 'ci.sdk_workflow', 'ios-package'", self.action)
        for flag in (
            "--plan", "--discovery-root", "--state-root", "--destination", "--repository-root",
            "--expected-build-key", "--sdk-inputs-artifact-id", "--sdk-inputs-artifact-sha256",
            "--trusted-workflow-sha",
            "--keyring", "--keys-directory", "--developer-directory", "--tooling-evidence",
            "--tooling-public-key", "--java-executable", "--policy-revision", "--required-trust-domain",
        ):
            self.assertIn(f"'{flag}'", self.action)
        self.assertIn("fields['--tooling-keyring']", self.action)
        self.assertIn("fields['--tooling-keys-directory']", self.action)
        for forbidden in ("secrets.", "PRIVATE_KEY", "ssh-keygen", "xcodebuild", "gradlew "):
            self.assertNotIn(forbidden, self.action)
        for forbidden in ("apple-artifact", "native-tests-artifact", "rust-device-artifact",
                          "rust-simulator-artifact", "expected-distribution-proof", "PROOF_SHA256"):
            self.assertNotIn(forbidden, self.action)
        self.assertIn("DEVELOPER_DIR: ${{ inputs.developer-directory }}", self.action)
        self.assertIn("'--developer-directory': os.environ['DEVELOPER_DIR']", self.action)

    def test_caller_policy_is_pinned_across_capture_and_before_execution(self):
        policy = self.block("policy")
        identity = self.block("identity")
        execute = self.action.split("    - name: Execute exact iOS package", 1)[1].split("\n    - ", 1)[0]
        self.assertIn("reject_symlink_parents=True", policy)
        self.assertIn("require_exact_keys", policy)
        self.assertIn("POLICY_SHA256", identity)
        self.assertIn("POLICY_SHA256", execute)
        self.assertIn("policy_revision", execute.replace("-", "_"))
        for block in (policy, identity, execute):
            source = textwrap.dedent(block.split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0])
            compile(source, "ios-package-action", "exec")

    def test_failed_execution_retains_attempt_unique_immutable_complete_worker_tree(self):
        upload = self.action.split("uses: actions/upload-artifact@", 1)[1]
        self.assertIn("if: always() && steps.identity.outcome == 'success'", self.action)
        self.assertIn(
            "name: codex-agent-sdk-worker-sdk-ios-package-ios-${{ steps.identity.outputs.key_hex }}-"
            "${{ inputs.tree }}-attempt-${{ github.run_attempt }}", upload,
        )
        for value in ("path: build/sdk-ios-worker", "if-no-files-found: warn", "overwrite: false",
                      "include-hidden-files: true", "compression-level: 0"):
            self.assertIn(value, upload)


if __name__ == "__main__":
    unittest.main()
