"""The protected SDK Maven child admits official bytes before token-free signing."""

from pathlib import Path
import os
import re
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/sdk-phase10-maven-sidecars.yml"


class SdkPhase10MavenWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_protected_independent_authority_precedes_checkout(self):
        source = self.source
        self.assertIn("environment: product-attestation", source)
        self.assertIn("github.event_name == 'workflow_dispatch'", source)
        approval, later = source.split("      - name: Check out reviewed verifier and signer", 1)
        for name in ("CODEX_AGENT_SDK_MAVEN_CONTROL_APPROVED_SHA256",
                     "CODEX_AGENT_SDK_RECORD_PRODUCER_APPROVED_SHA256",
                     "CODEX_AGENT_SDK_RECORD_ARTIFACT_SHA256",
                     "CODEX_AGENT_SDK_INDEX_APPROVED_SHA256",
                     "CODEX_AGENT_SDK_SIGNATURE_APPROVED_SHA256",
                     "CODEX_AGENT_PRODUCT_PGP_PUBLIC_KEY_SHA256"):
            self.assertIn(name, approval)
        self.assertNotIn("secrets.", approval)
        self.assertIn("ref: ${{ steps.approval.outputs.source_sha }}", later)

    def test_invalid_reviewed_source_and_control_stop_before_checkout(self):
        source = self.source
        block = source.split("      - name: Require independently approved original, signed index and PGP authorities before checkout\n", 1)[1]
        script = textwrap.dedent(block.split("        run: |\n", 1)[1].split(
            "      - name: Check out reviewed verifier and signer\n", 1)[0])
        with tempfile.TemporaryDirectory() as temporary:
            base = {"SOURCE_SHA": "a" * 40, "RECORD_WORKFLOW_SHA": "b" * 40,
                    "RECORD_ARTIFACT_ID": "1", "CAMPAIGN_CONTROL": "{}",
                    "MAVEN_CONTROL": "{}", "RECORD_PRODUCER": "{}",
                    "PGP_PUBLIC_KEY": "dummy"}
            for name in ("CAMPAIGN_CONTROL_SHA256", "MAVEN_CONTROL_SHA256",
                         "RECORD_PRODUCER_SHA256", "RECORD_ARTIFACT_SHA256",
                         "INDEX_SHA256", "SIGNATURE_SHA256", "PGP_KEY_SHA256"):
                base[name] = "sha256:" + "c" * 64
            for change in ({"SOURCE_SHA": "refs/heads/main"},
                           {"MAVEN_CONTROL_SHA256": "sha256:bad"},
                           {"MAVEN_CONTROL": "substituted"}):
                with self.subTest(change=change):
                    output = Path(temporary) / "output"
                    result = subprocess.run(["bash", "-e", "-c", script],
                        env={**os.environ, **base, **change, "RUNNER_TEMP": temporary,
                             "GITHUB_OUTPUT": str(output)}, capture_output=True,
                        text=True, timeout=10)
                    self.assertEqual(1, result.returncode, result.stderr)
                    self.assertFalse(output.exists())

    def test_full_official_index_replay_and_exact_receipts_precede_custody(self):
        source = self.source
        self.assertEqual(4, source.count("merge-multiple: true"))
        self.assertIn("path: original-plan\n", source)
        for component in ("sdk-core", "sdk-android", "sdk-ios"):
            self.assertIn("path: receipt-carriers/" + component + "\n", source)
        for marker in ("sdk_phase10_protected_inputs.py stage",
                       "sdk_phase10_original_plan.py",
                       "sdk_phase10_release_index_admission.py",
                       "sdk_phase10_maven_caller.py prepare"):
            self.assertIn(marker, source)
        self.assertLess(source.index("sdk_phase10_protected_inputs.py stage"),
                        source.index("sdk_phase10_release_index_admission.py"))
        self.assertLess(source.index("sdk_phase10_release_index_admission.py"),
                        source.index("sdk_phase10_maven_caller.py prepare"))
        self.assertIn("from ci.sdk_phase10_maven_caller import _selection", source)
        self.assertIn("'shard/phase-receipt.json'", source)
        self.assertIn("sha256_bytes(raw) != row['receiptSha256']", source)
        self.assertIn("--record-artifact-sha256", source)
        self.assertIn("--trusted-record-workflow-sha", source)
        self.assertIn("--expected-signature-sha256", source)
        self.assertIn("--expected-keys-inventory-sha256", source)
        self.assertIn("--original-root \"$PWD/original-source\"", source)
        self.assertIn("--signed-index \"$RUNNER_TEMP/sdk-admitted-index/signed-pair/product-index.json\"", source)

    def test_optional_replay_controls_use_supported_flags(self):
        source = self.source
        self.assertIn('optional+=("--${flag//_/-}" "$input/$item.json")', source)
        for name in ("SDK_VALIDATION_TOOLING", "SDK_APPLE_VALIDATION_POLICY",
                     "SDK_FACADE_METADATA_POLICY", "SDK_ANDROID_METADATA_POLICY",
                     "CUSTODY_CATALOGS"):
            self.assertIn(name, source)
        self.assertIn('"${optional[@]}" --destination "$RUNNER_TEMP/sdk-protected-inputs"', source)
        self.assertIn('            --original-producer "$input/original-producer.json"', source)
        block = source.split("          optional=()\n", 1)[1].split(
            "          python3 -B trusted-source/ci/sdk_phase10_protected_inputs.py stage", 1)[0]
        # Local macOS Bash 3.2 treats an empty array as unbound under -u;
        # Ubuntu's runner Bash accepts the workflow's set -euo pipefail.
        script = "set -eo pipefail\noptional=()\n" + textwrap.dedent(block) + \
            'printf "%s\\n" "${optional[@]}"\n'
        names = ("SDK_VALIDATION_TOOLING", "SDK_APPLE_VALIDATION_POLICY",
                 "SDK_FACADE_METADATA_POLICY", "SDK_ANDROID_METADATA_POLICY",
                 "CUSTODY_CATALOGS")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            empty = subprocess.run(["bash", "-c", script],
                env={**os.environ, "input": temporary}, capture_output=True,
                text=True, timeout=10)
            self.assertEqual(0, empty.returncode, empty.stderr)
            self.assertEqual("", empty.stdout.strip())
            for name in names:
                (directory / (name + ".json")).write_text("{}\n")
            present = subprocess.run(["bash", "-c", script],
                env={**os.environ, "input": temporary}, capture_output=True,
                text=True, timeout=10)
            self.assertEqual(0, present.returncode, present.stderr)
            expected = [part for name in names for part in
                ("--" + name.lower().replace("_", "-"), str(directory / (name + ".json")))]
            self.assertEqual(expected, present.stdout.splitlines())

    def test_signer_has_no_observation_token_or_product_build(self):
        source = self.source
        observe = source.split("      - name: Authenticate original plan", 1)[1].split(
            "      - name: Sign only held originals", 1)[0]
        signer = source.split("      - name: Sign only held originals", 1)[1].split(
            "      - name: Upload exact Core", 1)[0]
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", observe)
        self.assertNotIn("secrets.", observe)
        self.assertIn("SIGNING_IN_MEMORY_KEY: ${{ secrets.SIGNING_IN_MEMORY_KEY }}", signer)
        self.assertIn("unset GITHUB_TOKEN GH_TOKEN GITHUB_API_TOKEN", signer)
        self.assertNotIn("GITHUB_TOKEN: ${{ github.token }}", signer)
        self.assertLess(signer.index("sdk_phase10_maven_caller.py sign"),
                        signer.index("sdk_phase10_maven_caller.py verify"))
        for command in ("./gradlew", "cargo build", "cmake --build", "xcodebuild", "dotnet build"):
            self.assertNotIn(command, source)

    def test_all_three_sidecars_record_and_official_index_are_explicit_uploads(self):
        source = self.source
        for component, label in (("sdk-core", "core"), ("sdk-android", "android"),
                                 ("sdk-ios", "ios")):
            self.assertIn("path: ${{ runner.temp }}/sdk-maven-signed/maven-sidecars/" + component, source)
            self.assertIn(label + "ArtifactId:", source)
            self.assertIn(label + "ArtifactSha256:", source)
        self.assertIn("recordArtifactId:", source)
        self.assertIn("recordArtifactSha256:", source)
        self.assertIn("path: ${{ runner.temp }}/sdk-maven-signed\n", source)
        self.assertIn("indexAdmissionArtifactId:", source)
        self.assertIn("indexAdmissionArtifactSha256:", source)
        self.assertIn("path: ${{ runner.temp }}/sdk-admitted-index\n", source)
        self.assertEqual(5, source.count("overwrite: false"))

    def test_caller_pins_reviewed_child_and_requires_all_five_uploads(self):
        caller = WORKFLOW.with_name("ci.yml").read_text(encoding="utf-8")
        child = caller.split("  sdk-phase10-maven-sidecars:\n", 1)[1].split("\n  merge-gate:", 1)[0]
        self.assertIn("inputs.purpose == 'sdk-phase10-maven-sidecars'", child)
        pin = re.search(r"sdk-phase10-maven-sidecars\.yml@([0-9a-f]{40})", child)
        self.assertIsNotNone(pin)
        committed = subprocess.check_output(["git", "show", pin.group(1) + ":.github/workflows/sdk-phase10-maven-sidecars.yml"], cwd=WORKFLOW.parents[2], text=True)
        self.assertEqual(self.source, committed)
        gate = caller.split("  merge-gate:\n", 1)[1]
        script = textwrap.dedent(gate.split("        run: |\n", 1)[1])
        env = {**os.environ, "EVENT": "workflow_dispatch", "PURPOSE": "sdk-phase10-maven-sidecars",
               "PRODUCT_VALIDATION_RESULT": "skipped", "SDK_CUSTODY_RESULT": "skipped",
               "TOOLCHAIN_CAPTURE_RESULT": "skipped", "RUNTIME_RECORD_RESULT": "skipped",
               "CONTRACT_RECORD_RESULT": "skipped", "SDK_AUTHORITY_RESULT": "skipped",
               "SDK_RECORD_RESULT": "skipped", "SDK_MAVEN_RESULT": "success"}
        for label in ("CORE", "ANDROID", "IOS", "RECORD", "INDEX"):
            env["SDK_MAVEN_" + label + "_ID"] = "123"
            env["SDK_MAVEN_" + label + "_SHA256"] = "sha256:" + "a" * 64
        for change in ({}, {"SDK_MAVEN_RESULT": "failure"}, {"SDK_MAVEN_CORE_ID": ""},
                       {"SDK_MAVEN_INDEX_SHA256": "sha256:bad"},
                       {"PRODUCT_VALIDATION_RESULT": "success"}):
            result = subprocess.run(["bash", "-e", "-c", script], env={**env, **change},
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(0 if not change else 1, result.returncode, change)


if __name__ == "__main__":
    unittest.main()
