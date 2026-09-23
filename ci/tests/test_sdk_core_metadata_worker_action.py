"""Core metadata composite source gates; no hosted compiler or product proof."""

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


class CoreMetadataWorkerActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = (ROOT / ".github/actions/sdk-core-metadata-worker/action.yml").read_text()

    def source(self, step):
        match = re.search(rf"(?ms)^    - id: {re.escape(step)}\n.*?(?=^    - |\Z)", self.action)
        self.assertIsNotNone(match, step)
        source = textwrap.dedent(match[0].split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0])
        compile(source, "core-metadata-" + step, "exec")
        return source

    def test_independent_policy_and_wave_gate_before_capture_and_setup(self):
        self.assertLess(self.action.index("- id: policy"), self.action.index("- id: captured"))
        self.assertLess(self.action.index("- id: captured"), self.action.index("- id: identity"))
        self.assertLess(self.action.index("- id: identity"), self.action.index("uses: ./.github/actions/setup-kmp"))
        self.assertIn("sdk-family: core-metadata", self.action)
        self.assertIn("sdk-state-wave: ${{ inputs.sdk-state-wave }}", self.action)
        capture = self.action.split("- id: captured", 1)[1].split("- id: identity", 1)[0]
        self.assertNotIn("sdk-facade-metadata-policy:", capture)
        source = self.source("policy")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            workspace = root / "workspace"
            workspace.mkdir()
            policy = root / "policy.json"
            policy.write_bytes(canonical_json_bytes({"evidenceRoot": str(root / "evidence"),
                "records": [], "policy": {}}))
            values = {"GITHUB_WORKSPACE": str(workspace), "GITHUB_OUTPUT": str(root / "github-output"),
                "SDK_STATE_WAVE": "12", "CORE_POLICY": str(policy), "APPLE_POLICY": "", "ANDROID_POLICY": ""}
            with patch.dict(os.environ, values, clear=True), self.assertRaisesRegex(ValueError, "wave 13"):
                exec(compile(source, "core-policy", "exec"), {})
            values["SDK_STATE_WAVE"] = "13"
            with patch.dict(os.environ, values, clear=True), self.assertRaises(ValueError):
                exec(compile(source, "core-policy", "exec"), {})  # No eleven-target caller policy.
            with patch.dict(os.environ, values, clear=True), patch(
                    "ci.sdk_policy_snapshot.snapshot_policy_closure",
                    return_value=sha256_bytes(policy.read_bytes())):
                exec(compile(source, "core-policy", "exec"), {})
            self.assertEqual(sha256_bytes(canonical_json_bytes({"CORE_POLICY": sha256_bytes(policy.read_bytes())})),
                             (root / "github-output").read_text().strip().split("=", 1)[1])
            values["CORE_POLICY"] = str(workspace / "policy.json")
            Path(values["CORE_POLICY"]).write_bytes(policy.read_bytes())
            with patch.dict(os.environ, values, clear=True), self.assertRaisesRegex(ValueError, "external"):
                exec(compile(source, "core-policy", "exec"), {})

    def test_fresh_policy_rejects_self_referential_metadata_receipt(self):
        source = self.source("policy")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            workspace = root / "workspace"
            workspace.mkdir()
            policy = root / "policy.json"
            policy.write_bytes(canonical_json_bytes({"evidenceRoot": str(root / "evidence"),
                "records": [{"receiptSha256": KEY, "captureRoot": "metadata"}], "policy": {}}))
            values = {"GITHUB_WORKSPACE": str(workspace), "GITHUB_OUTPUT": str(root / "github-output"),
                "SDK_STATE_WAVE": "13", "CORE_POLICY": str(policy), "APPLE_POLICY": "", "ANDROID_POLICY": ""}
            with patch.dict(os.environ, values, clear=True), patch(
                    "ci.sdk_policy_snapshot.snapshot_policy_closure") as snapshot, \
                    self.assertRaisesRegex(ValueError, "must not claim a metadata receipt"):
                exec(compile(source, "core-policy", "exec"), {})
            snapshot.assert_not_called()

    def test_exact_common_election_and_linux_host(self):
        source = self.source("identity")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            policy = root / "policy.json"
            policy.write_bytes(canonical_json_bytes({"x": 1}))
            plan = root / "plan.json"
            plan.write_text(json.dumps({"validationTree": TREE}))
            row = {"product": "sdk", "component": "sdk-core", "phase": "metadata", "target": "common",
                   "runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64", "buildKey": KEY}
            values = {"MATRIX": json.dumps({"include": [row]}), "REQUIRED": "true", "PLAN": str(plan),
                "BUILD_KEY": KEY, "TREE": TREE, "CORE_POLICY": str(policy), "APPLE_POLICY": "",
                "ANDROID_POLICY": "", "GITHUB_OUTPUT": str(root / "github-output"),
                "POLICY_SHA256": sha256_bytes(canonical_json_bytes({"CORE_POLICY": sha256_bytes(policy.read_bytes())}))}
            transitive = root / "original-evidence"
            transitive.write_bytes(b"original")
            def snapshot(_kind, path):
                return sha256_bytes(Path(path).read_bytes() + transitive.read_bytes())
            values["POLICY_SHA256"] = sha256_bytes(canonical_json_bytes({"CORE_POLICY": snapshot("core-metadata", policy)}))
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"), \
                    patch("ci.sdk_policy_snapshot.snapshot_policy_closure", side_effect=snapshot):
                exec(compile(source, "core-identity", "exec"), {})
            self.assertIn("key_hex=" + "a" * 64, (root / "github-output").read_text())
            for changed in ({"target": "jvm"}, {"runner": "ubuntu-latest"}, {"buildKey": "sha256:" + "0" * 64}):
                values["MATRIX"] = json.dumps({"include": [{**row, **changed}]})
                with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"), \
                        patch("ci.sdk_policy_snapshot.snapshot_policy_closure", side_effect=snapshot), \
                        self.assertRaisesRegex(ValueError, "elected host"):
                    exec(compile(source, "core-identity", "exec"), {})
            values["MATRIX"] = json.dumps({"include": [row]})
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="macos-arm64"), \
                    patch("ci.sdk_policy_snapshot.snapshot_policy_closure", side_effect=snapshot), \
                    self.assertRaisesRegex(ValueError, "elected host"):
                exec(compile(source, "core-identity", "exec"), {})
            transitive.write_bytes(b"mutated")
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"), \
                    patch("ci.sdk_policy_snapshot.snapshot_policy_closure", side_effect=snapshot), \
                    self.assertRaisesRegex(ValueError, "changed during state capture"):
                exec(compile(source, "core-identity", "exec"), {})
            transitive.write_bytes(b"original")
            apple = root / "apple.json"
            apple.write_bytes(canonical_json_bytes({"x": 1}))
            values["APPLE_POLICY"] = str(apple)
            with patch.dict(os.environ, values, clear=True), patch(
                    "ci.sdk_policy_snapshot.snapshot_policy_closure", side_effect=snapshot), \
                    self.assertRaisesRegex(ValueError, "changed during state capture"):
                exec(compile(source, "core-identity", "exec"), {})

    def test_existing_controller_retains_full_original_replay_and_diagnostics(self):
        source = self.action.split("- name: Execute exact Core metadata controller", 1)[1]
        compile(textwrap.dedent(source.split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0]),
                "core-metadata-execute", "exec")
        for required in ("metadata_admission_options(options)", "execute(plan=plan", "validations=policy['validations']",
                         "contract_digest=policy['contract_digest']", "component_digests=policy['component_digests']",
                         "policy_revision=current['validationCommit']", "**admissions"):
            self.assertIn(required, source)
        self.assertNotIn("'sdk_facade_metadata_policy': policy_path", source)
        self.assertIn("if descriptor['records'] != []:", source)
        self.assertGreaterEqual(self.action.count("snapshot_policy_closure(kind, "), 3)
        self.assertIn("if: always() && steps.identity.outcome == 'success'", self.action)
        self.assertIn("attempt-${{ github.run_attempt }}", self.action)
        for forbidden in ("secrets.", "PRIVATE_KEY", "ssh-keygen", "gradlew "):
            self.assertNotIn(forbidden, self.action)


if __name__ == "__main__":
    unittest.main()
