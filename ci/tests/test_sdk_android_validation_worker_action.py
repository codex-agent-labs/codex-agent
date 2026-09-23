"""Android validation composite authority checks; no hosted Firebase claim."""

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
from ci.products.inventory import canonical_json_bytes

KEY = "sha256:" + "a" * 64
TREE = "b" * 40


class AndroidValidationWorkerActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = (ROOT / ".github/actions/sdk-android-validation-worker/action.yml").read_text()

    def script(self, step):
        match = re.search(rf"(?ms)^    - id: {re.escape(step)}\n.*?(?=^    - |\Z)", self.action)
        self.assertIsNotNone(match, step)
        script = textwrap.dedent(match[0].split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0])
        compile(script, "android-validation-" + step, "exec")
        return script

    def fixture(self, root):
        for name in ("package", "binary", "tooling"):
            (root / name).mkdir()
        for name in ("package-receipt", "binary-receipt", "compatibility", "public-key", "java", "apkanalyzer"):
            (root / name).write_bytes(b"original\n")
        evidence = {name: None for name in ("stageRoot", "phaseReceipt", "attestation",
            "attestationSignature", "publicKey", "expectedTrustDomain", "keyring", "keysDirectory")}
        evidence["expectedTrustDomain"] = "release"
        (root / "contract.json").write_bytes(canonical_json_bytes(evidence))
        tooling = {"evidence": str(root / "tooling"), "publicKey": str(root / "public-key"),
            "javaExecutable": str(root / "java"), "requiredTrustDomain": "development",
            "keyring": None, "keysDirectory": None}
        (root / "tooling.json").write_bytes(canonical_json_bytes(tooling))
        values = {"PACKAGE_STAGE": str(root / "package"), "BINARY_STAGE": str(root / "binary"),
            "PACKAGE_RECEIPT": str(root / "package-receipt"), "BINARY_RECEIPT": str(root / "binary-receipt"),
            "COMPATIBILITY_REQUEST": str(root / "compatibility"),
            "BINARY_CONTRACT_EVIDENCE": str(root / "contract.json"),
            "SDK_VALIDATION_TOOLING": str(root / "tooling.json"),
            "APKANALYZER_EXECUTABLE": str(root / "apkanalyzer"),
            "SDK_APPLE_VALIDATION_POLICY": "", "SDK_FACADE_METADATA_POLICY": "",
            "SDK_ANDROID_METADATA_POLICY": "", "GITHUB_OUTPUT": str(root / "output")}
        return values

    def test_policy_pins_original_inputs_before_capture_and_rejects_mutation(self):
        self.assertLess(self.action.index("- id: policy"), self.action.index("- id: captured"))
        self.assertLess(self.action.index("- id: captured"), self.action.index("- id: identity"))
        self.assertLess(self.action.index("- id: identity"), self.action.index("uses: ./.github/actions/setup-kmp"))
        self.assertLess(self.action.index("- id: identity"), self.action.index("uses: android-actions/setup-android@"))
        self.assertIn("sdk-family: android-validation", self.action)
        self.assertIn("cache-read-only: 'true'", self.action)
        self.assertIn("product-worker: 'true'", self.action)
        from ci.products import sdk_android_validation_phase as phase
        from ci.products import sdk_validation_inputs as inputs
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as temporary:
            root = Path(temporary).resolve()
            values = self.fixture(root)
            with patch.object(phase, "_contract_sources", return_value=({}, {})), \
                    patch.object(inputs, "_request_inventory", return_value={}), \
                    patch.dict(os.environ, values, clear=True):
                exec(compile(self.script("policy"), "android-policy", "exec"), {})
            pin = (root / "output").read_text().splitlines()[0].split("=", 1)[1]
            plan = root / "plan"
            plan.write_bytes(canonical_json_bytes({"validationTree": TREE}))
            state = root / "state"
            state.mkdir()
            row = {"product": "sdk", "component": "sdk-android", "phase": "validation",
                   "target": "android", "runner": "ubuntu-24.04", "runnerOs": "Linux",
                   "runnerArch": "X64", "buildKey": KEY}
            values.update(MATRIX=json.dumps({"include": [row]}), REQUIRED="true", PLAN=str(plan),
                          STATE=str(state), BUILD_KEY=KEY, TREE=TREE, POLICY_SHA256=pin,
                          POLICY_REVISION="c" * 40, TRUSTED_WORKFLOW_SHA="d" * 40,
                          TRUSTED_ANDROID_WORKFLOW_SHA="e" * 40,
                          TRUSTED_SOURCE_COMMIT="f" * 40, TRUSTED_SOURCE_TREE="0" * 40)
            import products.sdk_android_validation_phase as worker_phase
            import products.sdk_validation_inputs as worker_inputs
            with patch.object(worker_phase, "_contract_sources", return_value=({}, {})), \
                    patch.object(worker_inputs, "_request_inventory", return_value={}), \
                    patch("native_wrappers.host_classifier", return_value="linux-x64"), \
                    patch.dict(os.environ, values, clear=True):
                exec(compile(self.script("identity"), "android-identity", "exec"), {})
                os.environ["MATRIX"] = json.dumps({"include": [{**row, "runner": "other"}]})
                with self.assertRaisesRegex(ValueError, "elected phase"):
                    exec(compile(self.script("identity"), "android-identity", "exec"), {})
                os.environ["MATRIX"] = json.dumps({"include": [row]})
                (root / "binary-receipt").write_bytes(b"mutated\n")
                with self.assertRaisesRegex(ValueError, "changed during state capture"):
                    exec(compile(self.script("identity"), "android-identity", "exec"), {})

    def test_optional_apple_and_metadata_transitive_evidence_is_pinned(self):
        from ci.products import sdk_android_validation_phase as phase
        from ci.products import sdk_validation_inputs as inputs
        from ci.products import sdk_facade_metadata_admission as core_policy
        import products.sdk_android_validation_phase as worker_phase
        import products.sdk_validation_inputs as worker_inputs
        import products.sdk_facade_metadata_admission as worker_core_policy
        with tempfile.TemporaryDirectory(dir=Path(tempfile.gettempdir()).resolve()) as temporary:
            root = Path(temporary).resolve()
            values = self.fixture(root)
            apple_evidence, meta_evidence, keys = (root / name for name in
                ("apple-evidence", "metadata-evidence", "apple-keys"))
            for directory in (apple_evidence, meta_evidence, keys):
                directory.mkdir()
                (directory / "record").write_bytes(b"original\n")
            apple = {"plan": str(root / "package-receipt"),
                     "attestationPublicKey": str(root / "public-key"),
                     "keyring": str(root / "package-receipt"),
                     "keysDirectory": str(keys), "toolingEvidence": str(apple_evidence),
                     "toolingPublicKey": str(root / "public-key"), "javaExecutable": str(root / "java"),
                     "toolingKeyring": None, "toolingKeysDirectory": None,
                     "attestationTrustDomain": "development", "toolingTrustDomain": "development"}
            (root / "apple.json").write_bytes(canonical_json_bytes(apple))
            (root / "metadata.json").write_bytes(canonical_json_bytes({
                "evidenceRoot": str(meta_evidence), "records": [], "policy": {}}))
            values.update(SDK_APPLE_VALIDATION_POLICY=str(root / "apple.json"),
                          SDK_FACADE_METADATA_POLICY=str(root / "metadata.json"))
            original_args = {"plan": root / "package-receipt", "validations": {}}
            with patch.object(phase, "_contract_sources", return_value=({}, {})), \
                    patch.object(inputs, "_request_inventory", return_value={}), \
                    patch.object(core_policy, "_arguments", return_value=original_args), \
                    patch.dict(os.environ, values, clear=True):
                exec(compile(self.script("policy"), "android-policy", "exec"), {})
            pin = (root / "output").read_text().splitlines()[0].split("=", 1)[1]
            plan = root / "plan"
            plan.write_bytes(canonical_json_bytes({"validationTree": TREE}))
            state = root / "state"
            state.mkdir()
            row = {"product": "sdk", "component": "sdk-android", "phase": "validation",
                   "target": "android", "runner": "ubuntu-24.04", "runnerOs": "Linux",
                   "runnerArch": "X64", "buildKey": KEY}
            values.update(MATRIX=json.dumps({"include": [row]}), REQUIRED="true", PLAN=str(plan),
                          STATE=str(state), BUILD_KEY=KEY, TREE=TREE, POLICY_SHA256=pin,
                          POLICY_REVISION="c" * 40, TRUSTED_WORKFLOW_SHA="d" * 40,
                          TRUSTED_ANDROID_WORKFLOW_SHA="e" * 40,
                          TRUSTED_SOURCE_COMMIT="f" * 40, TRUSTED_SOURCE_TREE="0" * 40)
            with patch.object(worker_phase, "_contract_sources", return_value=({}, {})), \
                    patch.object(worker_inputs, "_request_inventory", return_value={}), \
                    patch.object(worker_core_policy, "_arguments", return_value=original_args), \
                    patch("native_wrappers.host_classifier", return_value="linux-x64"), \
                    patch.dict(os.environ, values, clear=True):
                exec(compile(self.script("identity"), "android-identity", "exec"), {})
                for directory in (apple_evidence, meta_evidence):
                    (directory / "record").write_bytes(b"mutated\n")
                    with self.subTest(directory=directory), self.assertRaisesRegex(ValueError, "changed during state capture"):
                        exec(compile(self.script("identity"), "android-identity", "exec"), {})
                    (directory / "record").write_bytes(b"original\n")

    def test_exact_cli_forwards_originals_and_retains_attempt(self):
        source = self.script("execute")
        for flag in ("--package-stage", "--package-receipt", "--binary-stage", "--binary-receipt",
                     "--compatibility-request", "--binary-contract-evidence", "--trusted-workflow-sha",
                     "--trusted-android-workflow-sha", "--trusted-source-commit", "--trusted-source-tree",
                     "--tooling-evidence", "--tooling-public-key", "--java-executable",
                     "--apkanalyzer-executable", "--policy-revision", "--required-trust-domain"):
            self.assertIn("'" + flag + "'", source)
        self.assertIn("'android-validation'", source)
        self.assertIn("if: always() && steps.identity.outcome == 'success'", self.action)
        self.assertIn("attempt-${{ github.run_attempt }}", self.action)
        self.assertIn("if-no-files-found: warn", self.action)
        self.assertIn("overwrite: false", self.action)
        for forbidden in ("secrets.", "PRIVATE_KEY", "ssh-keygen", "gradlew ", "firebase deploy"):
            self.assertNotIn(forbidden, self.action)

    def test_original_handoff_requires_successful_execution_upload_and_current_producer(self):
        source = self.script("execute")
        handoff = source[source.index("subprocess.run(command, cwd=root, check=True)"):]
        for name in ("validation-receipt-sha256", "validation-artifact-id",
                     "validation-artifact-sha256", "validation-run-id", "validation-run-attempt"):
            self.assertIn("  " + name + ":", self.action)
        self.assertEqual(self.action.count("steps.execute.outcome == 'success' && steps.upload.outcome == 'success'"), 5)
        self.assertIn("steps.upload.outputs.artifact-id != ''", self.action)
        self.assertIn("steps.upload.outputs.artifact-digest != ''", self.action)
        self.assertIn("steps.execute.outputs.receipt_sha256 != ''", self.action)
        self.assertIn("- id: upload", self.action)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            output = root / "output"
            values = {"BUILD_KEY": KEY, "TREE": TREE, "POLICY_REVISION": "d" * 40,
                      "GITHUB_RUN_ID": "23", "GITHUB_RUN_ATTEMPT": "2",
                      "GITHUB_OUTPUT": str(output)}
            shard = {"buildKey": KEY, "receiptSha256": "sha256:" + "c" * 64,
                     "receipt": {"producer": {"tree": TREE, "commit": "d" * 40,
                                               "runId": 23, "runAttempt": 2}}}
            import subprocess
            from products.registry import PhaseInstanceId
            with patch.dict(os.environ, values, clear=True), patch.object(subprocess, "run"), \
                    patch("products.restore.verify_phase_shard", return_value=shard) as verified:
                scope = {"subprocess": subprocess, "command": [], "root": root, "os": os,
                         "require_no_signing_secret": lambda _: None,
                         "PhaseInstanceId": PhaseInstanceId,
                         "verify_phase_shard": verified,
                         "validate_producer": lambda value, _: value}
                exec(compile(handoff, "android-handoff", "exec"), scope)
                self.assertEqual(output.read_text(), "receipt_sha256=sha256:" + "c" * 64 + "\n")
                output.unlink()
                shard["receipt"]["producer"]["runAttempt"] = 1
                with self.assertRaisesRegex(ValueError, "current producer"):
                    exec(compile(handoff, "android-handoff", "exec"), scope)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
