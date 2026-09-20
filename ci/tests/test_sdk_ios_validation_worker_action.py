"""Execute action snippets with mocked host/process boundaries; no Apple tools."""

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
from products.inventory import canonical_json_bytes

KEY, TREE = "sha256:" + "a" * 64, "b" * 40


class IosValidationWorkerActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = (ROOT / ".github/actions/sdk-ios-validation-worker/action.yml").read_text()

    def block(self, name):
        match = re.search(rf"(?ms)^    - id: {re.escape(name)}\n.*?(?=^    - |\Z)", self.action)
        self.assertIsNotNone(match, name)
        return match[0]

    def source(self, name):
        return textwrap.dedent(self.block(name).split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ios-validation-action-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.policy = {"evidence": "/caller/tooling", "publicKey": "/caller/tooling.pub",
            "javaExecutable": "/caller/java", "requiredTrustDomain": "release",
            "keyring": "/caller/tooling-keyring", "keysDirectory": "/caller/tooling-keys"}
        self.policy_path = self.root / "policy.json"
        self.policy_path.write_bytes(canonical_json_bytes(self.policy))
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(canonical_json_bytes({"validationTree": TREE}))
        self.output = self.root / "output"
        self.rows = [{"product": "sdk", "component": "sdk-ios", "phase": "validation", "target": target,
                      "buildKey": KEY, "runner": "macos-26", "runnerOs": "macOS", "runnerArch": "ARM64"}
                     for target in ("ios-arm64", "ios-simulator-arm64")]
        self.environment = {"SDK_VALIDATION_TOOLING": str(self.policy_path), "SDK_APPLE_VALIDATION_POLICY": "",
            "GITHUB_OUTPUT": str(self.output), "PLAN": str(self.plan), "MATRIX": json.dumps({"include": self.rows}),
            "REQUIRED": "true", "TARGET": "ios-arm64", "BUILD_KEY": KEY, "TREE": TREE,
            "GITHUB_WORKSPACE": str(ROOT), "DISCOVERY": "/captured/discovery", "STATE": "/captured/state",
            "PACKAGE_ARTIFACT_ID": "91", "PACKAGE_ARTIFACT_SHA256": "sha256:" + "c" * 64,
            "BINARY_ARTIFACT_ID": "92", "BINARY_ARTIFACT_SHA256": "sha256:" + "d" * 64,
            "TRUSTED_WORKFLOW_SHA": "e" * 40, "POLICY_REVISION": "f" * 40,
            "DEVELOPER_DIR": "/caller/Xcode/Contents/Developer", "GITHUB_TOKEN": "observer-token"}

    def run_snippet(self, name, *, host="macos-arm64"):
        with patch.dict(os.environ, self.environment, clear=True), \
                patch("native_wrappers.host_classifier", return_value=host):
            exec(compile(self.source(name), f"ios-validation-action-{name}", "exec"), {})

    def pin(self):
        self.run_snippet("policy")
        values = dict(line.split("=", 1) for line in self.output.read_text().splitlines())
        self.environment.update(POLICY_SHA256=values["policy_sha256"], APPLE_POLICY_SHA256=values["apple_policy_sha256"])
        self.output.unlink()

    def test_capture_and_identity_before_setup_and_complete_attempt_unique_upload(self):
        positions = [self.action.index(value) for value in ("- id: policy", "- id: captured", "- id: identity",
                    "uses: ./.github/actions/setup-kmp", "- id: execute")]
        self.assertEqual(sorted(positions), positions)
        captured = self.block("captured")
        for value in ("product: sdk", "sdk-family: ios-validation",
                      "sdk-validation-tooling: ${{ inputs.sdk-validation-tooling }}",
                      "sdk-apple-validation-policy: ${{ inputs.sdk-apple-validation-policy }}"):
            self.assertIn(value, captured)
        for value in ("cache-read-only: 'true'", "product-worker: 'true'", "xcode-fingerprint: auto",
                      "if: always() && steps.identity.outcome == 'success'",
                      "name: codex-agent-sdk-worker-sdk-ios-validation-${{ inputs.target }}-${{ steps.identity.outputs.key_hex }}-${{ inputs.tree }}-attempt-${{ github.run_attempt }}",
                      "path: build/sdk-ios-validation-worker", "include-hidden-files: true", "overwrite: false",
                      "compression-level: 0", "if-no-files-found: warn"):
            self.assertIn(value, self.action)
        for forbidden in ("secrets.", "PRIVATE_KEY", "ssh-keygen", "xcodebuild", "gradlew ", "--sdk-inputs-artifact"):
            self.assertNotIn(forbidden, self.action)

    def test_both_targets_accept_their_exact_row_from_two_target_election(self):
        self.pin()
        for target in ("ios-arm64", "ios-simulator-arm64"):
            self.environment["TARGET"] = target
            self.run_snippet("identity")
            self.assertEqual("key_hex=" + "a" * 64 + "\n", self.output.read_text())
            self.output.unlink()

    def test_wrong_host_election_target_key_tree_or_changed_policy_reject_before_output(self):
        self.pin()
        baseline = dict(self.environment)
        cases = [{"TARGET": "ios"}, {"BUILD_KEY": "sha256:" + "c" * 64}, {"TREE": "d" * 40},
                 {"REQUIRED": "false"}, {"POLICY_SHA256": "sha256:" + "0" * 64},
                 {"MATRIX": json.dumps({"include": []})},
                 {"MATRIX": json.dumps({"include": [self.rows[0], self.rows[0]]})},
                 {"MATRIX": json.dumps({"include": [{**self.rows[0], "phase": "package"}]})},
                 {"MATRIX": json.dumps({"include": [{**self.rows[0], "runnerArch": "X64"}]})}]
        for changes in cases:
            self.environment = {**baseline, **changes}
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.run_snippet("identity")
            self.assertFalse(self.output.exists())
        self.environment = baseline
        with self.assertRaises(ValueError): self.run_snippet("identity", host="macos-x64")
        self.assertFalse(self.output.exists())

    def test_fixed_cli_exact_original_locators_tooling_and_environment(self):
        self.pin()
        for target in ("ios-arm64", "ios-simulator-arm64"):
            self.environment["TARGET"] = target
            def process(argv, **kwargs):
                self.assertEqual([sys.executable, "-B", "-m", "ci.sdk_workflow", "ios-validation"], argv[:5])
                fields = dict(zip(argv[5::2], argv[6::2]))
                self.assertEqual({"--plan": str(self.plan), "--discovery-root": "/captured/discovery",
                    "--state-root": "/captured/state", "--destination": str(ROOT / "build/sdk-ios-validation-worker"),
                    "--repository-root": str(ROOT), "--expected-build-key": KEY, "--target": target,
                    "--rust-host": "aarch64-apple-darwin", "--package-artifact-id": "91",
                    "--package-artifact-sha256": self.environment["PACKAGE_ARTIFACT_SHA256"],
                    "--binary-artifact-id": "92", "--binary-artifact-sha256": self.environment["BINARY_ARTIFACT_SHA256"],
                    "--trusted-workflow-sha": "e" * 40, "--keyring": str(ROOT / "gradle/release/product-signing-keys.json"),
                    "--keys-directory": str(ROOT / "gradle/release/keys"), "--tooling-evidence": "/caller/tooling",
                    "--tooling-public-key": "/caller/tooling.pub", "--java-executable": "/caller/java",
                    "--policy-revision": "f" * 40, "--required-trust-domain": "release",
                    "--tooling-keyring": "/caller/tooling-keyring", "--tooling-keys-directory": "/caller/tooling-keys"}, fields)
                self.assertEqual({"cwd": ROOT, "check": True}, kwargs)
                self.assertEqual(self.environment["DEVELOPER_DIR"], os.environ["DEVELOPER_DIR"])
                self.assertEqual("observer-token", os.environ["GITHUB_TOKEN"])
            with patch("subprocess.run", side_effect=process) as invoked:
                self.run_snippet("execute")
            invoked.assert_called_once()

    def test_external_apple_policy_is_pinned_forwarded_and_rechecked(self):
        apple = {name: "/caller/" + name for name in (
            "plan", "attestationPublicKey", "keyring", "keysDirectory", "toolingEvidence",
            "toolingPublicKey", "javaExecutable", "toolingKeyring", "toolingKeysDirectory")}
        apple.update(attestationTrustDomain="release", toolingTrustDomain="release")
        path = self.root / "apple.json"
        path.write_bytes(canonical_json_bytes(apple))
        self.environment["SDK_APPLE_VALIDATION_POLICY"] = str(path)
        self.pin()
        self.run_snippet("identity")
        with patch("subprocess.run") as process:
            self.run_snippet("execute")
        args = process.call_args.args[0]
        self.assertEqual(str(path), args[args.index("--sdk-apple-validation-policy") + 1])
        path.write_bytes(canonical_json_bytes({**apple, "plan": "/changed/plan"}))
        for step in ("identity", "execute"):
            with self.subTest(step=step), patch("subprocess.run") as process, self.assertRaises(ValueError):
                self.run_snippet(step)
            process.assert_not_called()

    def test_secret_and_malformed_tooling_fail_before_setup_or_process(self):
        for name in ("evidence", "publicKey", "javaExecutable"):
            self.policy_path.write_bytes(canonical_json_bytes({**self.policy, name: None}))
            with self.subTest(field=name), self.assertRaises(ValueError): self.run_snippet("policy")
            self.assertFalse(self.output.exists())
        self.policy_path.write_bytes(canonical_json_bytes(self.policy))
        self.pin()
        self.environment["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
        for step in ("policy", "identity", "execute"):
            with self.subTest(step=step), patch("subprocess.run") as process, self.assertRaises(ValueError):
                self.run_snippet(step)
            process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
