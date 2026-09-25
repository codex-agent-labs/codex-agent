"""Core metadata wave14 wiring; hosted originals remain pending."""

from pathlib import Path
import re
import unittest


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml"


class CoreMetadataWorkflowTest(unittest.TestCase):
    def test_wave_fourteen_waits_for_original_validation_and_fails_after_collection(self):
        source = WORKFLOW.read_text()

        def job(name):
            found = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
            self.assertIsNotNone(found, name)
            return found[0]

        plan, worker, collect, result = (job(name) for name in (
            "sdk-core-metadata-plan", "sdk-core-metadata", "sdk-collect-14",
            "sdk-core-metadata-result"))
        for block in (plan, worker, collect, result):
            self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", block)
            self.assertIn("needs.sdk-core-validation-result.result == 'success'", block)
        self.assertIn("sdk-family: core-metadata", plan)
        self.assertIn("sdk-family: core-metadata", collect)
        self.assertIn("wave: '14'", collect)
        self.assertIn("fail-fast: false", worker)
        self.assertIn("needs.sdk-inputs.result == 'success'", worker)
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
        self.assertIn("select_native_state(json.loads(os.environ['RESULTS']), stage='core-metadata')", result)
        self.assertIn("metadata_build_key: ${{ steps.result.outcome == 'success' && ", result)
        self.assertIn("needs.sdk-core-metadata.outputs.metadata_build_key", result)
        for field in ("metadata_original_context", "metadata_receipt_sha256",
                      "metadata_artifact_id", "metadata_artifact_sha256"):
            self.assertIn(field + ": ${{ steps.result.outcome == 'success' && ", result)
            self.assertIn("needs.sdk-core-metadata.outputs." + field, result)
        self.assertNotIn("sdk-facade-metadata-policy", result)
        self.assertIn("sdk-core-metadata-result", job("sdk-completion").split("    needs:", 1)[1].split("\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
