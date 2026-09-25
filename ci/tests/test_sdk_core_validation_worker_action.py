"""Core validation composite caller checks; these do not claim hosted execution."""

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


class CoreValidationWorkerActionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.action = (ROOT / ".github/actions/sdk-core-validation-worker/action.yml").read_text()

    def script(self, step):
        match = re.search(rf"(?ms)^    - id: {re.escape(step)}\n.*?(?=^    - |\Z)", self.action)
        self.assertIsNotNone(match, step)
        script = textwrap.dedent(match[0].split("        python3 -B - <<'PY'\n", 1)[1].split("\n        PY", 1)[0])
        compile(script, "core-validation-" + step, "exec")
        return script

    def fixture(self, root):
        (root / "checkout").mkdir()
        for name in ("evidence", "keys"):
            (root / name).mkdir()
            (root / name / "original").write_bytes(b"original\n")
        for name in ("public-key", "java", "keyring"):
            (root / name).write_bytes(b"original\n")
        tooling = {"evidence": str(root / "evidence"), "publicKey": str(root / "public-key"),
            "javaExecutable": str(root / "java"), "requiredTrustDomain": "release",
            "keyring": str(root / "keyring"), "keysDirectory": str(root / "keys")}
        (root / "tooling.json").write_bytes(canonical_json_bytes(tooling))
        return {"TARGET": "jvm", "SDK_INPUTS_ID": "7", "SDK_INPUTS_SHA256": KEY,
            "GITHUB_WORKSPACE": str(root / "checkout"),
            "SDK_VALIDATION_TOOLING": str(root / "tooling.json"),
            "SDK_APPLE_VALIDATION_POLICY": "", "SDK_FACADE_METADATA_POLICY": "",
            "SDK_ANDROID_METADATA_POLICY": "", "NATIVE_COMPILER_ARCHIVE": "",
            "GITHUB_OUTPUT": str(root / "output")}

    def test_independent_inputs_are_pinned_before_capture_and_host_checked_before_setup(self):
        for first, second in (("- id: policy", "- id: captured"),
                              ("- id: captured", "- id: identity"),
                              ("- id: identity", "- id: request"),
                              ("- id: request", "uses: ./.github/actions/setup-kmp")):
            self.assertLess(self.action.index(first), self.action.index(second))
        self.assertIn("sdk-family: core-validation", self.action)
        self.assertIn("cache-read-only: 'true'", self.action)
        self.assertIn("product-worker: 'true'", self.action)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = self.fixture(root)
            with patch.dict(os.environ, values, clear=True):
                exec(self.script("policy"), {})
            pin = (root / "output").read_text().splitlines()[0].split("=", 1)[1]
            plan = root / "plan.json"
            plan.write_bytes(canonical_json_bytes({"validationTree": TREE, "validationCommit": "c" * 40}))
            row = {"product": "sdk", "component": "sdk-core", "phase": "validation",
                "target": "jvm", "buildKey": KEY, "runner": "ubuntu-24.04",
                "runnerOs": "Linux", "runnerArch": "X64"}
            values.update(MATRIX=json.dumps({"include": [row, {**row, "target": "android"}]}),
                          REQUIRED="true", PLAN=str(plan), BUILD_KEY=KEY, TREE=TREE,
                          POLICY_SHA256=pin, RUNNER_OS="Linux", RUNNER_ARCH="X64")
            with patch.dict(os.environ, values, clear=True), patch("native_wrappers.host_classifier", return_value="linux-x64"):
                exec(self.script("identity"), {})
                (root / "evidence/original").write_bytes(b"mutated\n")
                with self.assertRaisesRegex(ValueError, "changed during state capture"):
                    exec(self.script("identity"), {})
                (root / "evidence/original").write_bytes(b"original\n")
                os.environ["RUNNER_ARCH"] = "ARM64"
                with self.assertRaisesRegex(ValueError, "physical host"):
                    exec(self.script("identity"), {})

    def test_unregistered_native_target_and_unsigned_tooling_fail_before_capture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = self.fixture(root)
            archive = root / "compiler.tar.gz"
            archive.write_bytes(b"archive")
            values.update(TARGET="unknown-native", NATIVE_COMPILER_ARCHIVE=str(archive))
            with patch.dict(os.environ, values, clear=True), self.assertRaisesRegex(ValueError, "registered target"):
                exec(self.script("policy"), {})
            values.update(TARGET="jvm", NATIVE_COMPILER_ARCHIVE="")
            captured_policy = root / "checkout/tooling.json"
            captured_policy.write_bytes((root / "tooling.json").read_bytes())
            values["SDK_VALIDATION_TOOLING"] = str(captured_policy)
            with patch.dict(os.environ, values, clear=True), self.assertRaisesRegex(ValueError, "external"):
                exec(self.script("policy"), {})
            values["SDK_VALIDATION_TOOLING"] = str(root / "tooling.json")
            tooling = json.loads((root / "tooling.json").read_bytes())
            tooling["requiredTrustDomain"] = "development"
            (root / "tooling.json").write_bytes(canonical_json_bytes(tooling))
            with patch.dict(os.environ, values, clear=True), self.assertRaisesRegex(ValueError, "release tooling"):
                exec(self.script("policy"), {})

    def test_linux_arm64_target_requires_the_elected_x64_compiler_host(self):
        from sdk_phase import route
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = self.fixture(root)
            archive = root / "compiler.tar.gz"
            archive.write_bytes(b"caller-owned compiler archive")
            values.update(TARGET="linux-arm64", NATIVE_COMPILER_ARCHIVE=str(archive))
            with patch.dict(os.environ, values, clear=True):
                exec(self.script("policy"), {})
            pin = (root / "output").read_text().splitlines()[0].split("=", 1)[1]
            plan = root / "plan.json"
            plan.write_bytes(canonical_json_bytes({"validationTree": TREE, "validationCommit": "c" * 40}))
            row = {"product": "sdk", "component": "sdk-core", "phase": "validation",
                   "target": "linux-arm64", "buildKey": KEY}
            row.update(route(row))
            self.assertEqual(("ubuntu-24.04", "Linux", "X64"),
                             tuple(row[name] for name in ("runner", "runnerOs", "runnerArch")))
            values.update(MATRIX=json.dumps({"include": [row]}), REQUIRED="true", PLAN=str(plan),
                          BUILD_KEY=KEY, TREE=TREE, POLICY_SHA256=pin,
                          RUNNER_OS="Linux", RUNNER_ARCH="X64")
            with patch.dict(os.environ, values, clear=True), \
                    patch("native_wrappers.host_classifier", return_value="linux-x64"):
                exec(self.script("identity"), {})
            with patch.dict(os.environ, values, clear=True), \
                    patch("native_wrappers.host_classifier", return_value="linux-arm64"):
                with self.assertRaisesRegex(ValueError, "physical host"):
                    exec(self.script("identity"), {})

    def test_registered_x64_native_hosts_pass_preflight_only_on_matching_runner(self):
        from sdk_phase import route
        for target, host in (("macos-x64", "macos-x64"), ("windows-x64", "windows-x64")):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                values = self.fixture(root)
                archive = root / "caller-owned-compiler-archive"
                archive.write_bytes(b"caller-owned compiler archive")
                values.update(TARGET=target, NATIVE_COMPILER_ARCHIVE=str(archive))
                with patch.dict(os.environ, values, clear=True):
                    exec(self.script("policy"), {})
                pin = (root / "output").read_text().splitlines()[0].split("=", 1)[1]
                plan = root / "plan.json"
                plan.write_bytes(canonical_json_bytes({"validationTree": TREE, "validationCommit": "c" * 40}))
                row = {"product": "sdk", "component": "sdk-core", "phase": "validation",
                       "target": target, "buildKey": KEY}
                row.update(route(row))
                values.update(MATRIX=json.dumps({"include": [row]}), REQUIRED="true", PLAN=str(plan),
                              BUILD_KEY=KEY, TREE=TREE, POLICY_SHA256=pin,
                              RUNNER_OS=row["runnerOs"], RUNNER_ARCH=row["runnerArch"])
                with patch.dict(os.environ, values, clear=True), \
                        patch("native_wrappers.host_classifier", return_value=host):
                    exec(self.script("identity"), {})
                with patch.dict(os.environ, values, clear=True), \
                        patch("native_wrappers.host_classifier", return_value="linux-x64"):
                    with self.assertRaisesRegex(ValueError, "physical host"):
                        exec(self.script("identity"), {})

    def test_existing_full_controller_receives_request_and_separate_original_authorities(self):
        command = self.script("execute")
        for flag in ("--facade-request", "--sdk-apple-validation-policy", "--native-compiler-archive",
                     "--tooling-evidence", "--tooling-public-key", "--tooling-keyring",
                     "--tooling-keys-directory", "--java-executable", "--required-trust-domain",
                     "--policy-revision", "--trusted-workflow-sha", "--android-sdk-directory"):
            self.assertIn("'" + flag + "'", command)
        self.assertIn("'core-validation'", command)
        self.assertIn("ci.sdk_core_validation_policy", self.action)
        self.assertLess(self.action.index("Core validation caller authority changed before request preparation"),
                        self.action.index("python3 -B -m ci.sdk_core_validation_policy"))
        self.assertLess(self.script("execute").index("Core validation caller authority changed before execution"),
                        self.script("execute").index("subprocess.run(command"))
        self.assertIn("--sdk-inputs-artifact-id", self.action)
        self.assertIn("--sdk-inputs-artifact-sha256", self.action)
        self.assertIn("if: always() && steps.identity.outcome == 'success'", self.action)
        self.assertIn("attempt-${{ github.run_attempt }}", self.action)
        self.assertIn("if-no-files-found: warn", self.action)
        self.assertIn("overwrite: false", self.action)
        for forbidden in ("secrets.", "PRIVATE_KEY", "ssh-keygen", "gradlew "):
            self.assertNotIn(forbidden, self.action)

    def test_tooling_and_archive_mutation_after_identity_stop_both_controllers(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            values = self.fixture(root)
            archive = root / "compiler.tar.gz"
            archive.write_bytes(b"original archive")
            values.update(TARGET="macos-arm64", NATIVE_COMPILER_ARCHIVE=str(archive))
            with patch.dict(os.environ, values, clear=True):
                exec(self.script("policy"), {})
            pin = (root / "output").read_text().splitlines()[0].split("=", 1)[1]
            values.update(POLICY_SHA256=pin)
            for path in (root / "evidence/original", archive):
                original = path.read_bytes()
                path.write_bytes(b"mutated")
                with self.subTest(path=path), patch.dict(os.environ, values, clear=True), \
                        patch.object(subprocess, "run") as controller:
                    with self.assertRaisesRegex(ValueError, "before request preparation"):
                        exec(self.script("request"), {})
                    with self.assertRaisesRegex(ValueError, "before execution"):
                        exec(self.script("execute"), {})
                    controller.assert_not_called()
                path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
