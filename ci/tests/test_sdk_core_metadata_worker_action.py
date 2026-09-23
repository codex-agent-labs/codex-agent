"""Core metadata composite source gates; no hosted compiler or product proof."""

import json
import os
from contextlib import contextmanager
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

    def test_fresh_policy_rejects_prebuilt_metadata_descriptor(self):
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
            with patch.dict(os.environ, values, clear=True), self.assertRaisesRegex(
                    ValueError, "Fresh Core metadata policy"):
                exec(compile(source, "core-policy", "exec"), {})

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
            values["POLICY_SHA256"] = sha256_bytes(canonical_json_bytes({"CORE_POLICY": snapshot("core-metadata-bootstrap", policy)}))
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
        source = self.source("execute")
        for required in ("metadata_admission_options(options)", "held_fresh_facade_metadata_policy(plan,", "execute(plan=plan", "validations=policy['validations']",
                         "contract_digest=policy['contract_digest']", "component_digests=policy['component_digests']",
                         "policy_revision=current['validationCommit']", "**admissions"):
            self.assertIn(required, source)
        self.assertNotIn("'sdk_facade_metadata_policy': policy_path", source)
        self.assertIn("if descriptor['records'] != []:", source)
        self.assertIn("fresh_metadata_arguments(descriptor['policy'])", source)
        self.assertLess(source.index("as descriptor_path:"), source.index("if held_policy_digest() != os.environ['POLICY_SHA256'] or"))
        self.assertLess(source.index("if held_policy_digest() != os.environ['POLICY_SHA256'] or"), source.index("execute(plan=plan"))
        self.assertIn("load_canonical_json_bytes(optional_raw['APPLE_POLICY'])", source)
        self.assertIn("options['expected_policy_bytes'] = {'sdk_android_metadata_policy': optional_raw['ANDROID_POLICY']}", source)
        self.assertIn("for name, pinned in optional_raw.items()", source)
        self.assertNotIn("from products.sdk_facade_metadata_admission import _arguments", source)
        self.assertEqual(3, self.action.count("('CORE_POLICY', 'core-metadata-bootstrap')"))
        self.assertGreaterEqual(self.action.count("snapshot_policy_closure(kind, "), 3)
        self.assertIn("- id: upload\n      if: always() && steps.identity.outcome == 'success'", self.action)
        self.assertIn("attempt-${{ github.run_attempt }}", self.action)
        for forbidden in ("secrets.", "PRIVATE_KEY", "ssh-keygen", "gradlew "):
            self.assertNotIn(forbidden, self.action)

    def test_original_context_and_upload_identity_expose_success_only(self):
        for name in ("metadata-original-context", "metadata-receipt-sha256",
                     "metadata-artifact-id", "metadata-artifact-sha256"):
            block = re.search(rf"(?ms)^  {name}:\n(.*?)(?=^  [a-z][a-z0-9-]*:|^runs:)",
                              self.action).group(1)
            self.assertIn("steps.execute.outcome == 'success'", block)
            self.assertIn("steps.upload.outcome == 'success'", block)
            self.assertIn("steps.upload.outputs.artifact-id != ''", block)
            self.assertIn("steps.upload.outputs.artifact-digest != ''", block)
        self.assertIn("format('sha256:{0}', steps.upload.outputs.artifact-digest)", self.action)
        self.assertIn("- id: upload\n      if: always() && steps.identity.outcome == 'success'", self.action)
        self.assertLess(self.action.index("- id: execute"), self.action.index("- id: upload"))
        self.assertIn("result = execute(plan=plan", self.source("execute"))
        self.assertIn("original_metadata_context(result['originalContext'])", self.source("execute"))
        self.assertIn("require_sha256(result['shard']['receiptSha256']", self.source("execute"))

        source = self.source("execute")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            workspace = root / "checkout"
            workspace.mkdir()
            plan, bootstrap, descriptor = (root / name for name in
                                           ("plan.json", "bootstrap.json", "descriptor.json"))
            plan.write_bytes(canonical_json_bytes({"validationCommit": TREE}))
            bootstrap.write_bytes(canonical_json_bytes({"plan": str(plan)}))
            descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": str(root),
                "records": [], "policy": {}}))
            snapshot = sha256_bytes(b"typed caller closure")
            output = root / "github-output"
            values = {"GITHUB_WORKSPACE": str(workspace), "CORE_POLICY": str(bootstrap),
                "APPLE_POLICY": "", "ANDROID_POLICY": "", "PLAN": str(plan),
                "DISCOVERY": str(root / "discovery"), "STATE": str(root / "state"),
                "BUILD_KEY": KEY, "TRUSTED_WORKFLOW_SHA": TREE, "GITHUB_TOKEN": "test",
                "GITHUB_OUTPUT": str(output),
                "POLICY_SHA256": sha256_bytes(canonical_json_bytes({"CORE_POLICY": snapshot}))}
            exited = []

            @contextmanager
            def held(*_args, **_kwargs):
                yield descriptor
                exited.append(True)

            @contextmanager
            def options(*_args, **_kwargs):
                yield {}

            def execute(*_args, **_kwargs):
                self.assertFalse(exited)
                return {"originalContext": {"repositoryRoot": str(workspace),
                    "metadataRequest": str(root / "private/metadata-request.json")},
                    "shard": {"receiptSha256": KEY}}

            policy = {"plan": plan, "validations": {}, "contract_digest": KEY,
                "component_digests": {}, "tooling_evidence": root, "tooling_public_key": plan,
                "java_executable": plan, "required_trust_domain": "release",
                "tooling_keyring": plan, "tooling_keys_directory": root}
            with patch.dict(os.environ, values, clear=True), patch(
                    "ci.sdk_policy_snapshot.snapshot_policy_closure", return_value=snapshot), patch(
                    "product_reuse._validate_plan", return_value={"validationCommit": TREE}), patch(
                    "sdk_metadata_policy.metadata_admission_options", side_effect=options), patch(
                    "sdk_facade_original_inputs.held_fresh_facade_metadata_policy", side_effect=held), patch(
                    "products.sdk_facade_metadata_admission.fresh_metadata_arguments", return_value=policy), patch(
                    "sdk_facade_metadata_workflow.execute", side_effect=execute):
                exec(compile(source, "core-metadata-success-output", "exec"), {})
            self.assertEqual([True], exited)
            self.assertEqual("original_context=" + canonical_json_bytes({
                "repositoryRoot": str(workspace),
                "metadataRequest": str(root / "private/metadata-request.json")}).decode().strip() + "\n" +
                "receipt_sha256=" + KEY + "\n",
                output.read_text())

    def test_fresh_policy_must_bind_exact_current_plan_before_controller(self):
        source = self.source("execute")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            workspace = root / "workspace"
            workspace.mkdir()
            current, other = root / "current.json", root / "other.json"
            current.write_bytes(canonical_json_bytes({"version": 1}))
            other.write_bytes(canonical_json_bytes({"version": 2}))
            bootstrap = root / "bootstrap.json"
            bootstrap.write_bytes(canonical_json_bytes({"plan": str(current)}))
            descriptor = root / "fresh.json"
            descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": str(root / "evidence"),
                "records": [], "policy": {}}))
            snapshot = sha256_bytes(b"typed closure")
            values = {"GITHUB_WORKSPACE": str(workspace), "CORE_POLICY": str(bootstrap),
                "APPLE_POLICY": "", "ANDROID_POLICY": "", "PLAN": str(current),
                "DISCOVERY": str(root / "discovery"), "STATE": str(root / "state"),
                "BUILD_KEY": KEY, "TRUSTED_WORKFLOW_SHA": TREE, "GITHUB_TOKEN": "test",
                "POLICY_SHA256": sha256_bytes(canonical_json_bytes({"CORE_POLICY": snapshot}))}
            @contextmanager
            def held(*_args, **_kwargs):
                yield descriptor
            @contextmanager
            def options(*_args, **_kwargs):
                yield {}
            with patch.dict(os.environ, values, clear=True), patch(
                    "ci.sdk_policy_snapshot.snapshot_policy_closure", return_value=snapshot), patch(
                    "products.sdk_facade_metadata_admission.fresh_metadata_arguments",
                    return_value={"plan": other}), patch(
                    "product_reuse._validate_plan", return_value={"validationCommit": TREE}), patch(
                    "sdk_metadata_policy.metadata_admission_options", side_effect=options), patch(
                    "sdk_facade_original_inputs.held_fresh_facade_metadata_policy", side_effect=held), self.assertRaisesRegex(
                    ValueError, "differs from the current authenticated plan"):
                exec(compile(source, "core-metadata-plan-binding", "exec"), {})


if __name__ == "__main__":
    unittest.main()
