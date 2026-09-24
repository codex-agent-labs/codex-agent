"""Execute saved action snippets; host, process and authority remain mocked."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
from products.inventory import canonical_json_bytes

KEY, TREE = "sha256:" + "a" * 64, "b" * 40


class IosMetadataActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = (ROOT / ".github/actions/sdk-ios-metadata-worker/action.yml").read_text()

    def block(self, name):
        match = re.search(rf"(?ms)^    - id: {re.escape(name)}\n.*?(?=^    - |\Z)", self.action)
        self.assertIsNotNone(match, name)
        return match[0]

    def source(self, name):
        return textwrap.dedent(self.block(name).split("        python3 -B - <<'PY'\n", 1)[1]
                               .split("\n        PY", 1)[0])

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ios-metadata-action-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.tooling = {"evidence": "/caller/tooling", "publicKey": "/caller/tooling.pub",
            "javaExecutable": "/caller/java", "requiredTrustDomain": "release",
            "keyring": "/caller/tooling-keyring", "keysDirectory": "/caller/tooling-keys"}
        self.apple = {"plan": "/caller/plan.json", "attestationPublicKey": None,
            "attestationTrustDomain": "release", "keyring": "/caller/keyring", "keysDirectory": "/caller/keys",
            "toolingEvidence": self.tooling["evidence"], "toolingPublicKey": self.tooling["publicKey"],
            "javaExecutable": self.tooling["javaExecutable"], "toolingTrustDomain": "release",
            "toolingKeyring": self.tooling["keyring"], "toolingKeysDirectory": self.tooling["keysDirectory"]}
        self.tooling_path, self.apple_path = self.root / "tooling policy.json", self.root / "apple policy.json"
        self.tooling_path.write_bytes(canonical_json_bytes(self.tooling))
        self.apple_path.write_bytes(canonical_json_bytes(self.apple))
        self.plan, self.output = self.root / "plan.json", self.root / "output"
        self.plan.write_bytes(canonical_json_bytes({"validationTree": TREE}))
        self.row = {"product": "sdk", "component": "sdk-ios", "phase": "metadata", "target": "ios",
                    "buildKey": KEY, "runner": "macos-26", "runnerOs": "macOS", "runnerArch": "ARM64"}
        self.environment = {"SDK_VALIDATION_TOOLING": str(self.tooling_path),
            "SDK_APPLE_VALIDATION_POLICY": str(self.apple_path), "GITHUB_OUTPUT": str(self.output),
            "PLAN": str(self.plan), "MATRIX": json.dumps({"include": [self.row]}), "REQUIRED": "true",
            "BUILD_KEY": KEY, "TREE": TREE, "GITHUB_WORKSPACE": str(ROOT),
            "TRUSTED_WORKFLOW_SHA": "c" * 40,
            "DISCOVERY": "/captured/discovery", "STATE": "/captured/state"}

    def run_snippet(self, name, *, host="macos-arm64"):
        with patch.dict(os.environ, self.environment, clear=True), \
                patch("native_wrappers.host_classifier", return_value=host):
            exec(compile(self.source(name), f"ios-metadata-action-{name}", "exec"), {})

    def pin(self):
        self.run_snippet("policy")
        values = dict(line.split("=", 1) for line in self.output.read_text().splitlines())
        self.environment.update(POLICY_SHA256=values["policy_sha256"],
                                APPLE_POLICY_SHA256=values["apple_policy_sha256"])
        self.output.unlink()

    def test_capture_election_setup_and_full_attempt_unique_upload(self):
        positions = [self.action.index(value) for value in ("- id: policy", "- id: captured", "- id: identity",
                     "uses: ./.github/actions/setup-kmp", "- id: execute")]
        self.assertEqual(sorted(positions), positions)
        captured = self.block("captured")
        self.assertIn("product: sdk", captured)
        self.assertIn("sdk-family: ios-metadata", captured)
        self.assertIn("TRUSTED_WORKFLOW_SHA: ${{ inputs.trusted-workflow-sha }}", self.block("execute"))
        for name in ("plan-id", "artifact-id", "artifact-sha256", "state-wave", "sdk-state-wave",
                     "trusted-workflow-sha", "sdk-validation-tooling", "sdk-apple-validation-policy"):
            self.assertIn(name + ": ${{ inputs." + name + " }}", captured)
        for value in ("cache-read-only: 'true'", "product-worker: 'true'", "xcode-fingerprint: none",
                      "if: always() && steps.identity.outcome == 'success'",
                      "name: codex-agent-sdk-worker-sdk-ios-metadata-ios-${{ steps.identity.outputs.key_hex }}-${{ inputs.tree }}-attempt-${{ github.run_attempt }}",
                      "path: build/sdk-ios-metadata-worker", "overwrite: false", "include-hidden-files: true",
                      "compression-level: 0", "if-no-files-found: warn"):
            self.assertIn(value, self.action)
        for value in ("secrets.", "ssh-keygen", "xcodebuild", "gradlew ", "--rust-host", "DEVELOPER_DIR",
                      "--package-artifact-id", "--binary-artifact-id", "--tooling-evidence"):
            self.assertNotIn(value, self.action)

    def test_exact_election_and_controller_arguments(self):
        self.pin()
        self.run_snippet("identity")
        self.assertEqual("key_hex=" + "a" * 64 + "\n", self.output.read_text())
        with patch("subprocess.run") as process:
            self.run_snippet("execute")
        process.assert_called_once()
        argv = process.call_args.args[0]
        self.assertEqual([sys.executable, "-B", "-m", "ci.sdk_workflow", "ios-metadata"], argv[:5])
        self.assertEqual({"--plan": str(self.plan), "--discovery-root": "/captured/discovery",
            "--state-root": "/captured/state", "--destination": str(ROOT / "build/sdk-ios-metadata-worker"),
            "--repository-root": str(ROOT), "--expected-build-key": KEY,
            "--sdk-apple-validation-policy": str(self.apple_path),
            "--trusted-workflow-sha": "c" * 40}, dict(zip(argv[5::2], argv[6::2])))
        self.assertEqual({"cwd": ROOT, "check": True}, process.call_args.kwargs)

    def test_wrong_election_or_host_rejects_before_output(self):
        self.pin()
        baseline = dict(self.environment)
        rows = [[], [self.row, self.row], [{**self.row, "product": "runtime"}],
                [{**self.row, "component": "sdk-core"}], [{**self.row, "phase": "validation"}],
                [{**self.row, "target": "ios-arm64"}], [{**self.row, "runner": "ubuntu-24.04"}],
                [{**self.row, "runnerArch": "X64"}], [{**self.row, "runnerOs": "Linux"}]]
        changes = [{"MATRIX": json.dumps({"include": row})} for row in rows]
        changes += [{"REQUIRED": "false"}, {"BUILD_KEY": "sha256:" + "c" * 64},
                    {"BUILD_KEY": "a" * 64}, {"TREE": "d" * 40}, {"TREE": "b" * 64}]
        for values in changes:
            self.environment = {**baseline, **values}
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.run_snippet("identity")
            self.assertFalse(self.output.exists())
        self.environment = baseline
        for host in ("linux-x64", "macos-x64"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                self.run_snippet("identity", host=host)
            self.assertFalse(self.output.exists())

    def test_each_policy_mutation_blocks_identity_and_process(self):
        self.pin()
        for path, original in ((self.tooling_path, self.tooling), (self.apple_path, self.apple)):
            path.write_bytes(canonical_json_bytes({**original, "unexpected": "changed"}))
            for step in ("identity", "execute"):
                with self.subTest(path=path, step=step), patch("subprocess.run") as process, \
                        self.assertRaisesRegex(ValueError, "changed after pinning"):
                    self.run_snippet(step)
                process.assert_not_called()
                self.assertFalse(self.output.exists())
            path.write_bytes(canonical_json_bytes(original))

    def test_missing_malformed_mismatched_policies_and_secret_fail_closed(self):
        for policy in ({}, {**self.tooling, "evidence": "/different"},
                       {**self.tooling, "javaExecutable": None}):
            self.tooling_path.write_bytes(canonical_json_bytes(policy))
            with self.subTest(policy=policy), self.assertRaises(ValueError): self.run_snippet("policy")
            self.assertFalse(self.output.exists())
        self.tooling_path.write_bytes(canonical_json_bytes(self.tooling))
        for policy in ({}, {**self.apple, "attestationTrustDomain": "development"},
                       {**self.apple, "toolingEvidence": "relative"}):
            self.apple_path.write_bytes(canonical_json_bytes(policy))
            with self.subTest(policy=policy), self.assertRaises(ValueError): self.run_snippet("policy")
            self.assertFalse(self.output.exists())
        self.apple_path.write_bytes(canonical_json_bytes(self.apple))
        for name in ("SDK_VALIDATION_TOOLING", "SDK_APPLE_VALIDATION_POLICY"):
            original = self.environment[name]
            self.environment[name] = ""
            with self.subTest(name=name), self.assertRaises(ValueError): self.run_snippet("policy")
            self.assertFalse(self.output.exists())
            self.environment[name] = original
        self.pin()
        self.environment["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
        for step in ("policy", "identity", "execute"):
            with self.subTest(step=step), patch("subprocess.run") as process, self.assertRaises(ValueError):
                self.run_snippet(step)
            process.assert_not_called()
            self.assertFalse(self.output.exists())

    def test_controller_failure_is_not_swallowed(self):
        self.pin()
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(9, "controller")), \
                self.assertRaises(subprocess.CalledProcessError):
            self.run_snippet("execute")
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
