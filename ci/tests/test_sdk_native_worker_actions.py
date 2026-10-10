"""Action wiring and executed election guards, not hosted/package acceptance."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


class SdkNativeWorkerActionsTest(unittest.TestCase):
    def setUp(self):
        self.prepare = (ROOT / ".github/actions/sdk-native-prepare/action.yml").read_text()
        self.package = (ROOT / ".github/actions/sdk-native-package-worker/action.yml").read_text()

    def test_original_elections_precede_every_tool_setup_and_fixed_execution(self):
        for action, command in ((self.prepare, "native-prepare"), (self.package, "native-package")):
            with self.subTest(command=command):
                family = "${{ format('native-{0}', inputs.preparation-phase) }}" if command == "native-prepare" else "native-package"
                self.assertIn("product: sdk\n        sdk-family: " + family, action)
                self.assertLess(action.index("./.github/actions/capture-runtime-state"), action.index("- id: identity"))
                self.assertLess(action.index("- id: identity"), action.index("./.github/actions/setup-kmp"))
                self.assertLess(action.index("./.github/actions/setup-kmp"), action.index("ci.sdk_workflow " + command))
                self.assertIn("cache-read-only: 'true'", action)
                self.assertIn("product-worker: 'true'", action)
                self.assertIn('--keyring "$GITHUB_WORKSPACE/gradle/release/product-signing-keys.json"', action)
                self.assertIn('--keys-directory "$GITHUB_WORKSPACE/gradle/release/keys"', action)
                self.assertIn("GITHUB_TOKEN: ${{ github.token }}", action)
                self.assertNotIn("run: ./gradlew", action)

    def test_preparation_is_once_and_uploads_only_its_complete_envelope(self):
        self.assertEqual(1, self.prepare.count("ci.sdk_workflow native-prepare"))
        self.assertNotIn("ci.sdk_workflow native-prepare", self.package)
        self.assertNotIn("prepareNativeWrapperPackageSources", self.package)
        self.assertIn("if: success() && steps.execute.outcome == 'success'", self.prepare)
        self.assertIn("name: codex-agent-sdk-native-prepared-${{ inputs.tree }}-attempt-${{ github.run_attempt }}", self.prepare)
        self.assertIn("path: build/sdk-native-prepare/upload", self.prepare)
        self.assertIn("path: build/sdk-native-prepare/worker", self.prepare)
        self.assertIn("steps.execute.outcome != 'success'", self.prepare)
        for key in ("artifact-id", "artifact-sha256", "state-wave", "sdk-state-wave", "component", "build-key"):
            self.assertIn("value: ${{ inputs." + key + " }}", self.prepare)
        self.assertIn("value: sha256:${{ steps.upload.outputs.artifact-digest }}", self.prepare)

    def test_package_recaptures_original_preparation_state_without_overwriting_current(self):
        action = self.package
        self.assertEqual(1, action.count("uses: ./.github/actions/capture-runtime-state"))
        self.assertIn("ARTIFACT_ID: ${{ inputs.preparation-state-id }}", action)
        self.assertIn("ARTIFACT_SHA256: ${{ inputs.preparation-state-sha256 }}", action)
        self.assertIn("STATE_WAVE: ${{ inputs.preparation-state-wave }}", action)
        self.assertIn("SDK_STATE_WAVE: ${{ inputs.preparation-sdk-state-wave }}", action)
        self.assertIn('ci.sdk_workflow capture --family native-package --plan "$PLAN"', action)
        self.assertIn('--destination "$GITHUB_WORKSPACE/build/native-preparation-input"', action)
        self.assertIn("PREPARATION_MATRIX: ${{ steps.preparation.outputs.sdk_matrix }}", action)
        self.assertIn("STATE: ${{ steps.captured.outputs.state-root }}", action)
        self.assertIn("PREPARATION_STATE: ${{ steps.preparation.outputs.state_root }}", action)
        self.assertIn('--state-root "$STATE" --preparation-state-root "$PREPARATION_STATE"', action)
        self.assertIn('--preparation-component "$PREPARATION_COMPONENT" --preparation-build-key "$PREPARATION_BUILD_KEY"', action)
        self.assertIn('--prepared-artifact-id "$PREPARED_ARTIFACT_ID" --prepared-artifact-sha256 "$PREPARED_ARTIFACT_SHA256"', action)
        self.assertNotIn("actions/download-artifact", action)
        self.assertNotIn("--phase-plan", action)
        self.assertLess(action.index("- id: preparation"), action.index("- id: identity"))

    def test_package_provisions_only_selected_existing_pinned_toolchains(self):
        action = self.package
        for component in ("python", "csharp", "rust", "dart"):
            self.assertIn("if: inputs.component == '" + component + "'", action)
        for pin in ("ece7cb06caefa5fff74198d8649806c4678c61a1", "a98b56852c35b8e3190ac28c8c2271da59106c68",
                    "a5f673d0ba8626c3977bb416a1612774bc82181b", "65eb853c7ba17dde3be364c3d2858773e7144260"):
            self.assertIn(pin, action)
        self.assertIn("build==1.3.0 setuptools==80.9.0 wheel==0.45.1", action)
        self.assertIn("dotnet-version: '8.0.419'", action)
        self.assertIn("sdk: '3.13.2'", action)
        self.assertIn('cargo fetch --manifest-path "$GITHUB_WORKSPACE/codex-agent-bindings/rust/Cargo.toml" --locked', action)
        self.assertNotIn("cargo package", action)
        self.assertNotIn("native_wrappers.py package", action)

    def test_original_preparation_shell_handles_empty_optional_array_under_nounset(self):
        block = self.package.split("    - id: preparation\n", 1)[1].split("    - id: identity\n", 1)[0]
        script = textwrap.dedent(block.split("      run: |\n", 1)[1])
        self.assertIn('${selected[@]+"${selected[@]}"}', script)
        shell = shutil.which("bash")
        self.assertIsNotNone(shell)
        with tempfile.TemporaryDirectory(prefix="native-preparation-shell-") as temporary:
            root = Path(temporary)
            binary = root / "bin"
            binary.mkdir()
            stub = binary / "python3"
            stub.write_text("#!/bin/sh\nprintf '%s\\0' \"$@\" > \"$RECORDED_ARGS\"\n")
            stub.chmod(0o700)
            recorded = root / "arguments"
            environment = {"PATH": str(binary), "RECORDED_ARGS": str(recorded),
                "PLAN": "/original capture/impact-plan.json", "GITHUB_WORKSPACE": str(root),
                "ARTIFACT_ID": "71", "ARTIFACT_SHA256": "sha256:" + "a" * 64,
                "STATE_WAVE": "0", "TRUSTED_WORKFLOW_SHA": "b" * 40,
                "GITHUB_OUTPUT": str(root / "output with spaces")}
            for wave in ("", "3"):
                with self.subTest(sdk_state_wave=wave):
                    result = subprocess.run([shell, "--noprofile", "--norc", "-c", script], cwd=root,
                        env={**environment, "SDK_STATE_WAVE": wave}, capture_output=True, text=True, check=False)
                    self.assertEqual(0, result.returncode, result.stderr)
                    expected = ["-B", "-m", "ci.sdk_workflow", "capture", "--family", "native-package",
                        "--plan", environment["PLAN"], "--destination", str(root / "build/native-preparation-input"),
                        "--repository-root", str(root), "--artifact-id", "71", "--artifact-sha256", "sha256:" + "a" * 64,
                        "--state-wave", "0", "--trusted-workflow-sha", "b" * 40,
                        "--github-output", environment["GITHUB_OUTPUT"],
                        *(["--sdk-state-wave", wave] if wave else [])]
                    self.assertEqual(expected, recorded.read_bytes().decode().split("\0")[:-1])

    def test_exact_attempt_uploads_never_overwrite_and_failed_workers_retain_diagnostics(self):
        for action in (self.prepare, self.package):
            for block in action.split("uses: actions/upload-artifact@")[1:]:
                self.assertIn("overwrite: false", block)
                self.assertIn("include-hidden-files: true", block)
                self.assertIn("compression-level: 0", block)
                self.assertIn("attempt-${{ github.run_attempt }}", block)
        self.assertIn("if: always() && steps.identity.outcome == 'success'", self.package)
        self.assertIn("codex-agent-sdk-worker-${{ inputs.component }}-package-desktop-${{ steps.identity.outputs.key_hex }}-${{ inputs.tree }}-attempt-${{ github.run_attempt }}", self.package)
        self.assertIn("path: build/sdk-worker", self.package)

    def guard(self, action, environment):
        match = re.search(r"(?ms)^        python3 - <<'PY'\n(.*?)^        PY$", action)
        self.assertIsNotNone(match)
        with patch.dict(os.environ, environment, clear=True):
            exec(compile(textwrap.dedent(match[1]), "native-action-election-guard", "exec"), {})

    def test_actual_election_guards_require_both_exact_native_plans_and_tree(self):
        with tempfile.TemporaryDirectory(prefix="native-action-guard-") as temporary:
            directory = Path(temporary)
            plan, output = directory / "plan.json", directory / "output"
            plan.write_text(json.dumps({"validationTree": "a" * 40}))
            current = {"product": "sdk", "component": "python", "phase": "package", "target": "desktop",
                       "buildKey": "sha256:" + "b" * 64, "runnerOs": "Linux", "runnerArch": "X64"}
            original = {**current, "component": "rust", "buildKey": "sha256:" + "c" * 64}
            base = {"MATRIX": json.dumps({"include": [current]}), "COMPONENT": "python",
                "BUILD_KEY": current["buildKey"], "PREPARATION_MATRIX": json.dumps({"include": [original]}),
                "PREPARATION_COMPONENT": "rust", "PREPARATION_BUILD_KEY": original["buildKey"],
                "PREPARATION_PHASE": "package", "PREPARATION_TARGET": "desktop",
                "PLAN": str(plan), "TREE": "a" * 40, "GITHUB_OUTPUT": str(output)}
            self.guard(self.prepare, base)
            self.guard(self.package, base)
            self.assertEqual("key_hex=" + "b" * 64 + "\n", output.read_text())
            for action in (self.prepare, self.package):
                prefixes = ("", "PREPARATION_") if action == self.package else ("",)
                for prefix in prefixes:
                    for failure in ("missing", "duplicate", "key", "phase", "target", "host"):
                        environment = deepcopy(base)
                        row = deepcopy(original if prefix else current)
                        rows = [row]
                        if failure == "missing": rows = []
                        elif failure == "duplicate": rows *= 2
                        elif failure == "key": row["buildKey"] = "sha256:" + "d" * 64
                        elif failure == "phase": row["phase"] = "validation"
                        elif failure == "target": row["target"] = "linux-x64"
                        else: row["runnerArch"] = "ARM64"
                        environment[prefix + "MATRIX"] = json.dumps({"include": rows})
                        with self.subTest(action=action[:30], prefix=prefix, failure=failure), self.assertRaises(ValueError):
                            self.guard(action, environment)
                with self.subTest(action=action[:30], failure="tree"), self.assertRaises(ValueError):
                    self.guard(action, {**base, "TREE": "d" * 40})

    def test_preparation_preserves_exact_validation_and_metadata_anchor_identity(self):
        with tempfile.TemporaryDirectory(prefix="native-action-anchor-") as temporary:
            plan = Path(temporary) / "plan.json"
            plan.write_text(json.dumps({"validationTree": "a" * 40}))
            anchors = [("metadata", "desktop", "Linux", "X64"),
                       ("validation", "macos-arm64", "macOS", "ARM64"),
                       ("validation", "macos-x64", "macOS", "X64"),
                       ("validation", "linux-arm64", "Linux", "ARM64"),
                       ("validation", "linux-x64", "Linux", "X64"),
                       ("validation", "windows-x64", "Windows", "X64")]
            for phase, target, runner_os, runner_arch in anchors:
                row = {"product": "sdk", "component": "python", "phase": phase, "target": target,
                       "buildKey": "sha256:" + "b" * 64, "runnerOs": runner_os, "runnerArch": runner_arch}
                environment = {"MATRIX": json.dumps({"include": [row]}), "COMPONENT": "python",
                    "BUILD_KEY": row["buildKey"], "PREPARATION_PHASE": phase, "PREPARATION_TARGET": target,
                    "PLAN": str(plan), "TREE": "a" * 40}
                with self.subTest(phase=phase, target=target):
                    self.guard(self.prepare, environment)
                    for changes in ({"PREPARATION_PHASE": "binary"}, {"PREPARATION_TARGET": "unknown"},
                                    {"PREPARATION_PHASE": "package"}, {"TREE": "c" * 40}):
                        with self.subTest(changes=changes), self.assertRaises(ValueError):
                            self.guard(self.prepare, {**environment, **changes})
                    mismatched = {**row, "runnerArch": "X64" if runner_arch == "ARM64" else "ARM64"}
                    with self.assertRaises(ValueError):
                        self.guard(self.prepare, {**environment, "MATRIX": json.dumps({"include": [mismatched]})})


if __name__ == "__main__":
    unittest.main()
