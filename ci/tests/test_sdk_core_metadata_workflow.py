"""Core metadata child wave14 wiring; hosted originals remain pending."""

from pathlib import Path
import json
import os
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci.tests.test_sdk_native_continuation import locator, needs_for


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml"
CHILD = WORKFLOW.with_name("sdk-core-metadata-validation.yml")


class CoreMetadataWorkflowTest(unittest.TestCase):
    def test_wave_fourteen_waits_for_original_validation_and_fails_after_collection(self):
        source = CHILD.read_text()

        def job(name):
            found = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
            self.assertIsNotNone(found, name)
            return found[0]

        parent = WORKFLOW.read_text()
        plan, worker, collect, result = (job(name) for name in (
            "sdk-core-metadata-plan", "sdk-core-metadata", "sdk-collect-14",
            "sdk-core-metadata-result"))
        self.assertIn("uses: ./.github/workflows/sdk-core-metadata-validation.yml", parent)
        self.assertIn("sdk-core-metadata-wave", parent.split("  sdk-completion:\n", 1)[1].split("\n", 1)[0])
        for block in (plan, worker, collect, result):
            self.assertIn("fromJSON(inputs.planOutputs).remote_build_authorized == 'true'", block)
            self.assertIn("fromJSON(inputs.validationWave).result == 'success'", block)
        self.assertIn("sdk-family: core-metadata", plan)
        self.assertIn("sdk-family: core-metadata", collect)
        self.assertIn("wave: '14'", collect)
        self.assertIn("sdk-worker-workflow-path: .github/workflows/sdk-core-metadata-validation.yml", collect)
        self.assertIn("sdk-worker-job-name: product-validation / sdk-core-metadata-wave / sdk-core-metadata-common", collect)
        self.assertIn("fail-fast: false", worker)
        self.assertIn("fromJSON(inputs.sdkInputs).result == 'success'", worker)
        self.assertIn("uses: ./.github/actions/capture-sdk-tooling", worker)
        self.assertIn("name: Provision each Git-pinned Core native compiler archive\n        shell: bash", worker)
        self.assertEqual(4, worker.count("$(native_archive "))
        self.assertIn("native-compiler-archive-linux-arm64: ${{ steps.native-archives.outputs.linux_x86_64 }}", worker)
        self.assertLess(worker.index("ci.sdk_core_native_archive_provision"),
                        worker.index("uses: ./.github/actions/sdk-core-metadata-worker"))
        self.assertIn("metadata_build_key: ${{ steps.metadata.outputs.metadata-artifact-id != '' && matrix.buildKey || '' }}", worker)
        for target in ("ios-arm64", "ios-simulator-arm64", "linux-arm64", "linux-x64",
                       "macos-arm64", "macos-x64", "windows-x64"):
            self.assertIn("native-compiler-archive-" + target + ":", worker)
        for field in ("sdk-inputs-id", "sdk-inputs-sha256", "sdk-validation-tooling",
                      "sdk-apple-validation-policy", "keyring", "keys-directory", "build-key", "tree"):
            self.assertIn(field + ":", worker)
        self.assertIn("needs['sdk-core-validation-wave'] = json.loads(os.environ['VALIDATION_RESULT'])", result)
        self.assertIn("select_native_state(needs, stage='core-metadata')", result)
        self.assertIn("metadata_build_key: ${{ steps.result.outcome == 'success' && ", result)
        self.assertIn("needs.sdk-core-metadata.outputs.metadata_build_key", result)
        for field in ("metadata_original_context", "metadata_receipt_sha256",
                      "metadata_artifact_id", "metadata_artifact_sha256"):
            self.assertIn(field + ": ${{ steps.result.outcome == 'success' && ", result)
            self.assertIn("needs.sdk-core-metadata.outputs." + field, result)
            self.assertIn("      " + field + ":\n        value: ${{ jobs.sdk-core-metadata-result.outputs."
                          + field + " }}", source)
        self.assertNotIn("sdk-facade-metadata-policy", result)

    def test_child_result_rejoins_validation_parent_before_selection(self):
        block = CHILD.read_text().split("  sdk-core-metadata-result:\n", 1)[1]
        script = textwrap.dedent(block.split("          python3 - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        for required in (False, True):
            needs = needs_for("core-metadata", required=required, state=locator("13", "0"))
            validation = needs.pop("sdk-core-validation-wave")
            with self.subTest(required=required), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "output"
                with patch.dict(os.environ, {"RESULTS": json.dumps(needs),
                                          "VALIDATION_RESULT": json.dumps(validation),
                                          "GITHUB_OUTPUT": str(output)}, clear=True):
                    exec(compile(script, "sdk-core-metadata-result", "exec"), {})
                values = dict(line.split("=", 1) for line in output.read_text().splitlines())
                self.assertEqual("14" if required else "13", values["sdk_state_wave"])
                validation["result"] = "failure"
                with patch.dict(os.environ, {"RESULTS": json.dumps(needs),
                                          "VALIDATION_RESULT": json.dumps(validation),
                                          "GITHUB_OUTPUT": str(output)}, clear=True), self.assertRaises(ValueError):
                    exec(compile(script, "sdk-core-metadata-result", "exec"), {})


if __name__ == "__main__":
    unittest.main()
