"""Wave 18 reuses authenticated waves 16–17 and refuses missing Firebase authority."""

from pathlib import Path
import json
import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from unittest.mock import patch


WORKFLOW = (Path(__file__).resolve().parents[2] /
            ".github/workflows/sdk-android-metadata-validation.yml")


def job(source, name):
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
    if match is None:
        raise AssertionError(f"Missing Android metadata job: {name}")
    return match[0]


class AndroidMetadataChildWorkflowTest(unittest.TestCase):
    def test_recovered_original_skips_all_fresh_preparation_and_execution(self):
        worker = job(WORKFLOW.read_text(), "sdk-android-metadata")
        retained = worker.split("      - id: retained\n", 1)[1].split("      - id: policy\n", 1)[0]
        self.assertLess(worker.index("- id: validation-state"), worker.index("- id: retained"))
        self.assertIn("locate_retained_core_binary_upload", retained)
        self.assertIn("phase='metadata', component='sdk-android', target='android'", retained)
        for name in ("policy", "apkanalyzer", "base", "validation-handoff", "control", "original", "metadata"):
            self.assertIn(f"- id: {name}\n        if: steps.retained.outputs.reused != 'true'", worker)

    def test_both_policy_callers_forward_only_explicit_retained_sdk_source(self):
        callers = (WORKFLOW, WORKFLOW.parents[1] /
                   "actions/sdk-android-validation-worker/prepare/action.yml")
        for caller in callers:
            source = caller.read_text().split("python3 -B -m ci.sdk_android_validation_policy", 1)[0]
            options = textwrap.dedent("policy=()" + source.rsplit("policy=()", 1)[1])
            for retained in (None, "/caller/retained SDK source.json"):
                with self.subTest(caller=caller.name, retained=retained):
                    env = {"APPLE_POLICY": "", "CODEX_AGENT_COMPLETED_REUSE_POLICY": "/caller/native.json"}
                    if retained is not None:
                        env["CODEX_AGENT_RETAINED_SDK_INPUTS_SOURCE"] = retained
                    result = subprocess.check_output(
                        ["bash", "-eu", "-c", options + '\nprintf "%s\\0" "${policy[@]}"'], env=env)
                    expected = ["--completed-frozen-policy", "/caller/native.json"]
                    if retained is not None:
                        expected += ["--retained-sdk-inputs-source", retained]
                    self.assertEqual(expected, result.decode().split("\0")[:-1])

    def test_protected_authority_is_exact_canonical_json(self):
        worker = job(WORKFLOW.read_text(), "sdk-android-metadata")
        script = worker.split("          python3 -I -B - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
        value = {"schemaVersion": 1, "trustedAndroidWorkflowSha": "c" * 40,
                 "trustedSourceCommit": "a" * 40, "trustedSourceTree": "b" * 40}
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            for payload, valid in ((raw, True), (raw.removesuffix("\n"), False),
                                   (raw.replace('"schemaVersion":1',
                                                '"schemaVersion":1,"schemaVersion":1'), False)):
                with self.subTest(payload=payload):
                    output.unlink(missing_ok=True)
                    with patch.dict(os.environ, {"AUTHORITY": payload,
                                              "GITHUB_OUTPUT": str(output)}, clear=True):
                        if valid:
                            exec(compile(textwrap.dedent(script), "android18-authority", "exec"), {})
                            self.assertIn("trustedSourceCommit=" + "a" * 40, output.read_text())
                        else:
                            with self.assertRaises(ValueError):
                                exec(compile(textwrap.dedent(script), "android18-authority", "exec"), {})
                            self.assertFalse(output.exists())

    def test_fresh_worker_has_protected_pre_setup_gate(self):
        worker = job(WORKFLOW.read_text(), "sdk-android-metadata")
        for required in ("remote_build_authorized == 'true'",
                         "inputs.protectedAndroidAuthority != ''",
                         "fromJSON(inputs.validationWave).result == 'success'",
                         "outputs.sdk_workers_required == 'true'"):
            self.assertIn(required, worker)
        self.assertNotIn("validation_receipt_sha256 != ''", worker.split("    strategy:", 1)[0])
        self.assertNotIn("outputs.sdk_state_wave ==", worker.split("    strategy:", 1)[0])
        self.assertLess(worker.index("- id: authority"), worker.index("android-actions/setup-android"))
        self.assertLess(worker.index("- id: authority"), worker.index("sdk-android-metadata-worker"))

    def test_same_job_restages_independent_inputs_before_original_replay(self):
        worker = job(WORKFLOW.read_text(), "sdk-android-metadata")
        for required in ("sdk-family: android-metadata",
                         "ci.sdk_android_validation_policy",
                         "--destination \"$RUNNER_TEMP/android18-validation-policy\"",
                         "--sdk-inputs-artifact-id \"$SDK_INPUTS_ID\"",
                         "--phase metadata",
                         "ci.sdk_android_validation_handoff",
                         "sdk-android-firebase-controls",
                         "sdk-android-original-selection",
                         "sdk-android-metadata-worker"):
            self.assertIn(required, worker)
        ordered = ("- id: authority", "- id: validation-state", "- id: policy",
                   "- id: base", "- id: validation-handoff", "- id: control",
                   "- id: original", "- id: metadata")
        self.assertEqual(list(sorted(ordered, key=worker.index)), list(ordered))
        self.assertEqual(1, worker.count("uses: ./.github/actions/capture-runtime-state"))
        self.assertNotIn("inputs.packageWave", worker)
        self.assertNotIn("steps.package-state", worker)
        self.assertIn("rows[0].get('buildKey') != os.environ['BUILD_KEY']", worker)
        self.assertEqual(2, worker.count('--completed-frozen-policy "$CODEX_AGENT_COMPLETED_REUSE_POLICY"'))
        self.assertIn("--expected-build-key \"$build_key\"", worker)
        self.assertNotIn("validation_build_key", worker)
        handoff = worker.split("      - id: validation-handoff\n", 1)[1].split("      - id: control\n", 1)[0]
        self.assertIn('test "$present" -eq 0 || test "$present" -eq 5', handoff)
        self.assertIn('--expected-metadata-build-key "${{ matrix.buildKey }}"', handoff)
        self.assertIn('--trusted-workflow-sha "$TRUSTED_WORKFLOW_SHA"', handoff)
        self.assertIn('--github-output "$GITHUB_OUTPUT"', handoff)
        control = worker.split("      - id: control\n", 1)[1].split("      - id: original\n", 1)[0]
        for name in ("validation-receipt-sha256", "validation-artifact-id",
                     "validation-artifact-sha256", "validation-run-id",
                     "validation-run-attempt", "validation-original-mode"):
            self.assertIn("steps.validation-handoff.outputs." + name, control)
        self.assertNotIn("fromJSON(inputs.validationWave).outputs.validation_", control)

    def test_collection_and_final_gate_cannot_upgrade_missing_authority(self):
        source = WORKFLOW.read_text()
        collector = job(source, "sdk-collect-18")
        result = job(source, "sdk-android-metadata-result")
        self.assertIn("inputs.protectedAndroidAuthority != ''", collector)
        self.assertIn("sdk-worker-workflow-path: .github/workflows/sdk-android-metadata-validation.yml", collector)
        self.assertIn("sdk-worker-job-name: product-validation / sdk-android-metadata-result / sdk-android-metadata-android", collector)
        self.assertIn("Fresh Android metadata lacks protected Firebase/source authority", result)
        self.assertIn("select_native_state(needs, stage='android-metadata')", result)
        self.assertIn("needs['sdk-android-validation-result']", result)
        self.assertIn("needs['sdk-android-metadata-plan']", result)
        self.assertNotIn("sdk-android-metadata-policy:", source)


if __name__ == "__main__":
    unittest.main()
