"""Executed action guards/dispatch with mocked commands, not hosted admission."""

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
from products.inventory import canonical_json_bytes, sha256_bytes


class SdkNativeMetadataWorkerActionTest(unittest.TestCase):
    def setUp(self):
        self.action = (ROOT / ".github/actions/sdk-native-metadata-worker/action.yml").read_text()
        temporary = tempfile.TemporaryDirectory(prefix="native-metadata-action-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.host = "linux-x64"

    def block(self, name):
        return self.action.split(f"    - id: {name}\n", 1)[1].split("    - ", 1)[0]

    def python(self, name, environment):
        block = self.block(name)
        script = textwrap.dedent(block.split("        python3 -B - <<'PY'\n", 1)[1].rsplit("        PY", 1)[0])
        with patch.dict(os.environ, environment, clear=True), \
                patch("native_wrappers.host_classifier", return_value=self.host):
            exec(compile(script, f"native-metadata-action-{name}", "exec"), {})

    def test_fixed_capture_election_setup_execution_and_attempt_upload_order(self):
        self.assertIn("product: sdk\n        sdk-family: native-metadata", self.action)
        self.assertIn("sdk-validation-tooling: ${{ inputs.sdk-validation-tooling }}", self.action)
        self.assertIn("sdk-apple-validation-policy: ${{ inputs.sdk-apple-validation-policy }}", self.block("captured"))
        self.assertEqual(1, self.action.count("uses: ./.github/actions/capture-runtime-state"))
        self.assertLess(self.action.index("id: policy"), self.action.index("id: captured"))
        self.assertLess(self.action.index("id: captured"), self.action.index("id: preparation"))
        self.assertLess(self.action.index("id: preparation"), self.action.index("id: identity"))
        self.assertLess(self.action.index("id: identity"), self.action.index("uses: ./.github/actions/setup-kmp"))
        self.assertLess(self.action.index("uses: ./.github/actions/setup-kmp"), self.action.index("id: execute"))
        for text in ("cache-read-only: 'true'", "product-worker: 'true'", "GITHUB_TOKEN: ${{ github.token }}",
                     "if: always() && steps.identity.outcome == 'success'", "path: build/sdk-worker",
                     "overwrite: false", "include-hidden-files: true", "compression-level: 0"):
            self.assertIn(text, self.action)
        self.assertIn("name: codex-agent-sdk-worker-${{ inputs.component }}-metadata-desktop-${{ steps.identity.outputs.key_hex }}-${{ inputs.tree }}-attempt-${{ github.run_attempt }}", self.action)
        for prohibited in ("setup-python", "setup-dotnet", "rust-toolchain", "setup-dart", "cargo fetch", "pip install",
                           "prepareNativeWrapperPackageSources", "ci.sdk_workflow native-prepare", "run: ./gradlew", "actions/download-artifact"):
            self.assertNotIn(prohibited, self.action)

    def test_preparation_shell_preserves_independent_ids_waves_and_caller_policy(self):
        block = self.block("preparation")
        for field in ("id", "sha256"):
            self.assertIn("${{ inputs.preparation-state-" + field + " }}", block)
        script = textwrap.dedent(block.split("      run: |\n", 1)[1])
        self.assertIn('${selected[@]+"${selected[@]}"}', script)
        binary = self.root / "bin"
        binary.mkdir()
        stub = binary / "python3"
        stub.write_text("#!/bin/sh\nprintf '%s\\0' \"$@\" > \"$RECORDED_ARGS\"\n")
        stub.chmod(0o700)
        recorded = self.root / "arguments"
        environment = {"PATH": str(binary), "RECORDED_ARGS": str(recorded),
            "PLAN": "/original capture/plan.json", "GITHUB_WORKSPACE": str(self.root),
            "ARTIFACT_ID": "71", "ARTIFACT_SHA256": "sha256:" + "a" * 64,
            "STATE_WAVE": "4", "TRUSTED_WORKFLOW_SHA": "b" * 40,
            "SDK_VALIDATION_TOOLING": "/caller policy/tooling.json", "GITHUB_OUTPUT": str(self.root / "output")}
        shell = shutil.which("bash")
        self.assertIsNotNone(shell)
        for wave, apple_policy in ((wave, policy) for wave in ("", "4")
                                   for policy in ("", "/caller policies/apple validation.json")):
            with self.subTest(wave=wave, apple_policy=apple_policy):
                result = subprocess.run([shell, "--noprofile", "--norc", "-c", script], cwd=self.root,
                    env={**environment, "SDK_STATE_WAVE": wave, "SDK_APPLE_VALIDATION_POLICY": apple_policy},
                    capture_output=True, text=True, check=False)
                self.assertEqual(0, result.returncode, result.stderr)
                expected = ["-B", "-m", "ci.sdk_workflow", "capture", "--family", "native-package",
                    "--plan", environment["PLAN"], "--destination", str(self.root / "build/native-preparation-input"),
                    "--repository-root", str(self.root), "--artifact-id", "71", "--artifact-sha256", environment["ARTIFACT_SHA256"],
                    "--state-wave", "4", "--sdk-validation-tooling", environment["SDK_VALIDATION_TOOLING"],
                    "--trusted-workflow-sha", environment["TRUSTED_WORKFLOW_SHA"], "--github-output", environment["GITHUB_OUTPUT"],
                    *(["--sdk-state-wave", wave] if wave else []),
                    *(["--sdk-apple-validation-policy", apple_policy] if apple_policy else [])]
                self.assertEqual(expected, recorded.read_bytes().decode().split("\0")[:-1])

    def test_both_exact_replayed_elections_and_tree_are_required(self):
        plan, output = self.root / "plan.json", self.root / "output"
        plan.write_text(json.dumps({"validationTree": "a" * 40}))
        current = {"product": "sdk", "component": "python", "phase": "metadata", "target": "desktop",
                   "buildKey": "sha256:" + "b" * 64, "runnerOs": "Linux", "runnerArch": "X64"}
        preparation = {**current, "component": "rust", "phase": "package", "buildKey": "sha256:" + "c" * 64}
        environment = {"MATRIX": json.dumps({"include": [current]}), "PREPARATION_MATRIX": json.dumps({"include": [preparation]}),
            "COMPONENT": "python", "PREPARATION_COMPONENT": "rust", "BUILD_KEY": current["buildKey"],
            "PREPARATION_BUILD_KEY": preparation["buildKey"], "TREE": "a" * 40, "PLAN": str(plan), "GITHUB_OUTPUT": str(output)}
        policy_path, policy, _ = self.execution_fixture()
        raw = canonical_json_bytes(policy)
        policy_path.write_bytes(raw)
        environment.update(SDK_VALIDATION_TOOLING=str(policy_path), POLICY_SHA256=sha256_bytes(raw))
        self.python("identity", environment)
        self.assertEqual("key_hex=" + "b" * 64 + "\n", output.read_text())
        for prefix, original in (("", current), ("PREPARATION_", preparation)):
            for failure in ("missing", "duplicate", "component", "phase", "target", "key", "host"):
                row, changed = deepcopy(original), dict(environment)
                rows = [row]
                if failure == "missing": rows = []
                elif failure == "duplicate": rows *= 2
                elif failure == "component":
                    row["component"] = changed[prefix + "COMPONENT"] = "javascript"
                elif failure == "phase": row["phase"] = "validation"
                elif failure == "target": row["target"] = "linux-x64"
                elif failure == "key": row["buildKey"] = "sha256:" + "d" * 64
                else: row["runnerArch"] = "ARM64"
                changed[prefix + "MATRIX"] = json.dumps({"include": rows})
                with self.subTest(prefix=prefix, failure=failure), self.assertRaises(ValueError):
                    self.python("identity", changed)
        with self.assertRaises(ValueError): self.python("identity", {**environment, "TREE": "d" * 40})

    def test_actual_non_linux_x64_host_rejects_before_election_output(self):
        output = self.root / "identity-output"
        for host in ("macos-arm64", "linux-arm64", "windows-x64"):
            self.host = host
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, "elected Linux X64 host"):
                self.python("identity", {"GITHUB_OUTPUT": str(output)})
            self.assertFalse(output.exists())

    def execution_fixture(self):
        policy_path = self.root / "caller policy.json"
        policy = {"evidence": "/caller evidence/tooling", "publicKey": "/caller key/tooling.pub",
            "javaExecutable": "/caller java/bin/java", "requiredTrustDomain": "development", "keyring": None, "keysDirectory": None}
        environment = {name: "/original inputs/" + name for name in ("PLAN", "DISCOVERY", "STATE", "PREPARATION_STATE")}
        environment.update(GITHUB_WORKSPACE=str(ROOT), SDK_VALIDATION_TOOLING=str(policy_path), COMPONENT="python",
            BUILD_KEY="sha256:" + "a" * 64, PREPARATION_COMPONENT="rust", PREPARATION_BUILD_KEY="sha256:" + "b" * 64,
            PREPARED_ARTIFACT_ID="71", PREPARED_ARTIFACT_SHA256="sha256:" + "c" * 64,
            SDK_INPUTS_ID="72", SDK_INPUTS_SHA256="sha256:" + "d" * 64, TRUSTED_WORKFLOW_SHA="e" * 40,
            GITHUB_TOKEN="environment only")
        return policy_path, policy, environment

    def test_exact_controller_dispatch_parses_caller_policy_without_transport_or_command_overrides(self):
        policy_path, policy, environment = self.execution_fixture()
        for trust in ("development", "release"):
            value = {**policy, "requiredTrustDomain": trust,
                **({"keyring": "/caller/policy.json", "keysDirectory": "/caller/keys"} if trust == "release" else {})}
            raw = canonical_json_bytes(value)
            policy_path.write_bytes(raw)
            environment["POLICY_SHA256"] = sha256_bytes(raw)
            with self.subTest(trust=trust), patch.object(subprocess, "run") as run:
                self.python("execute", environment)
            run.assert_called_once()
            command = run.call_args.args[0]
            self.assertEqual([sys.executable, "-B", "-m", "ci.sdk_workflow", "native-metadata"], command[:5])
            self.assertEqual({"cwd": ROOT, "check": True}, run.call_args.kwargs)
            fields = dict(zip(command[5::2], command[6::2]))
            self.assertEqual({"--plan": environment["PLAN"], "--discovery-root": environment["DISCOVERY"],
                "--state-root": environment["STATE"], "--preparation-state": environment["PREPARATION_STATE"],
                "--destination": str(ROOT / "build/sdk-worker"), "--repository-root": str(ROOT),
                "--component": "python", "--expected-build-key": environment["BUILD_KEY"],
                "--preparation-component": "rust", "--preparation-build-key": environment["PREPARATION_BUILD_KEY"],
                "--prepared-artifact-id": "71", "--prepared-artifact-sha256": environment["PREPARED_ARTIFACT_SHA256"],
                "--sdk-inputs-artifact-id": "72", "--sdk-inputs-artifact-sha256": environment["SDK_INPUTS_SHA256"],
                "--trusted-workflow-sha": environment["TRUSTED_WORKFLOW_SHA"],
                "--keyring": str(ROOT / "gradle/release/product-signing-keys.json"),
                "--keys-directory": str(ROOT / "gradle/release/keys"), "--required-trust-domain": trust,
                "--tooling-evidence": value["evidence"], "--tooling-public-key": value["publicKey"],
                "--java-executable": value["javaExecutable"],
                **({"--tooling-keyring": value["keyring"], "--tooling-keys-directory": value["keysDirectory"]}
                   if trust == "release" else {})}, fields)
            self.assertEqual(raw, policy_path.read_bytes())

    def test_malformed_relative_or_wrong_trust_policy_never_launches_controller(self):
        policy_path, policy, environment = self.execution_fixture()
        invalid = [b"{", b"[]\n", canonical_json_bytes({**policy, "command": "override"}),
            canonical_json_bytes({**policy, "evidence": "relative"}),
            canonical_json_bytes({**policy, "javaExecutable": None}),
            canonical_json_bytes({**policy, "requiredTrustDomain": "other"}),
            canonical_json_bytes({**policy, "requiredTrustDomain": "release"}),
            canonical_json_bytes({**policy, "keyring": "/unpaired/policy.json"})]
        for raw in invalid:
            policy_path.write_bytes(raw)
            environment["POLICY_SHA256"] = sha256_bytes(raw)
            for step in ("policy", "execute"):
                with self.subTest(raw=raw, step=step), patch.object(subprocess, "run") as run, self.assertRaises(ValueError):
                    self.python(step, environment)
                run.assert_not_called()
        policy_path.write_bytes(canonical_json_bytes(policy))
        with patch.object(subprocess, "run") as run, self.assertRaises(ValueError):
            self.python("execute", {**environment, "SDK_VALIDATION_TOOLING": "relative.json"})
        run.assert_not_called()

    def test_optional_apple_policy_is_forwarded_only_when_supplied(self):
        self.assertIn("  sdk-apple-validation-policy:\n    default: ''", self.action)
        for step in ("preparation", "execute"):
            self.assertIn("SDK_APPLE_VALIDATION_POLICY: ${{ inputs.sdk-apple-validation-policy }}", self.block(step))
        policy_path, policy, environment = self.execution_fixture()
        raw = canonical_json_bytes(policy)
        policy_path.write_bytes(raw)
        environment["POLICY_SHA256"] = sha256_bytes(raw)
        for apple_policy in ("", "/caller policies/apple validation.json"):
            environment["SDK_APPLE_VALIDATION_POLICY"] = apple_policy
            with self.subTest(apple_policy=apple_policy), patch.object(subprocess, "run") as run:
                self.python("execute", environment)
            command = run.call_args.args[0]
            fields = dict(zip(command[5::2], command[6::2]))
            self.assertEqual(apple_policy or None, fields.get("--sdk-apple-validation-policy"))
            self.assertEqual(environment["PREPARATION_STATE"], fields["--preparation-state"])

    def test_policy_is_pinned_before_capture_and_mutation_rejects_identity_and_controller(self):
        policy_path, policy, environment = self.execution_fixture()
        original = canonical_json_bytes(policy)
        policy_path.write_bytes(original)
        pin_output = self.root / "policy-output"
        self.python("policy", {**environment, "GITHUB_OUTPUT": str(pin_output)})
        self.assertEqual("sha256=" + sha256_bytes(original) + "\n", pin_output.read_text())
        environment["POLICY_SHA256"] = pin_output.read_text().strip().split("=", 1)[1]
        changed = canonical_json_bytes({**policy, "evidence": "/another caller/tooling"})
        policy_path.write_bytes(changed)
        for step in ("identity", "execute"):
            with self.subTest(step=step), patch.object(subprocess, "run") as run, \
                    self.assertRaisesRegex(ValueError, "Caller tooling policy changed"):
                self.python(step, environment)
            run.assert_not_called()
        self.assertEqual(changed, policy_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
