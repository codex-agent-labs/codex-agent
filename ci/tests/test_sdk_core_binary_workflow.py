"""Saved Core binary wave wiring; hosted compiler evidence remains separate."""

from pathlib import Path
import json
import os
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci import sdk_native_continuation


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml"
CHILD = WORKFLOW.with_name("sdk-core-binary-validation.yml")


class SdkCoreBinaryWorkflowTest(unittest.TestCase):
    def test_wave_eleven_is_elected_collected_and_selected_before_completion(self):
        source = CHILD.read_text()

        def job(name):
            match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
            self.assertIsNotNone(match, name)
            return match[0]

        plan = job("sdk-core-binary-plan")
        worker = job("sdk-core-binary")
        collect = job("sdk-collect-11")
        result = job("sdk-core-binary-result")
        for name, block in (("plan", plan), ("worker", worker), ("collect", collect)):
            with self.subTest(name=name):
                self.assertIn("fromJSON(inputs.planOutputs).remote_build_authorized == 'true'", block)
                self.assertIn("fromJSON(inputs.iosMetadataResult).result == 'success'", block)
                self.assertIn("fromJSON(inputs.iosMetadataResult).outputs.artifact_id", block)
        self.assertIn("sdk-family: core-binary", plan)
        self.assertIn("sdk-family: core-binary", collect)
        self.assertIn("runs-on: ${{ matrix.runner }}", worker)
        self.assertIn("uses: ./.github/actions/sdk-core-maven-worker", worker)
        self.assertIn("- id: binary\n        uses: ./.github/actions/sdk-core-maven-worker", worker)
        self.assertIn("phase: binary", worker)
        self.assertIn("build-key: ${{ matrix.buildKey }}", worker)
        for output in ("binary-artifact-id", "binary-artifact-sha256", "binary-original-context"):
            self.assertIn(f"steps.binary.outputs.{output}", worker)
        self.assertIn("wave: '11'", collect)
        self.assertIn("sdk-worker-workflow-path: .github/workflows/sdk-core-binary-validation.yml", collect)
        self.assertIn("sdk-worker-job-name: product-validation / sdk-core-binary-wave / sdk-core-binary-common", collect)
        self.assertIn("select_native_state(needs, stage='core-binary')", result)
        parent = WORKFLOW.read_text()
        self.assertIn("uses: ./.github/workflows/sdk-core-binary-validation.yml", parent)
        self.assertIn("sdk-core-binary-wave", parent.split("  sdk-completion:\n", 1)[1].split("\n", 1)[0])
        package = WORKFLOW.with_name("sdk-core-package-validation.yml").read_text()
        self.assertIn("binary-original-workflow-path: .github/workflows/sdk-core-binary-validation.yml", package)
        self.assertIn("binary-original-job-name: product-validation / sdk-core-binary-wave / sdk-core-binary-common", package)

    def test_collected_original_outputs_require_successful_fresh_wave(self):
        source = CHILD.read_text()
        block = source.split("  sdk-core-binary-result:\n", 1)[1]
        script = textwrap.dedent(block.split("          python3 - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        context = '{"repositoryRoot":"/original/repo","workerRoot":"/original/repo/build/sdk-core-maven-worker"}'
        original = {"binary_artifact_id": "71", "binary_artifact_sha256": "sha256:" + "a" * 64,
                    "binary_original_context": context}
        for wave, outputs, accepted in (("11", original, True), ("11", {}, False),
                                        ("10", original, False), ("10", {}, True)):
            with self.subTest(wave=wave, outputs=bool(outputs)), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "github-output"
                needs = {"sdk-core-binary": {"outputs": outputs}}
                selected = {"artifact_id": "52", "artifact_digest": "sha256:" + "b" * 64,
                            "state_wave": "0", "sdk_state_wave": wave}
                with patch.dict(os.environ, {"RESULTS": json.dumps(needs), "GITHUB_OUTPUT": str(output),
                                         "IOS_METADATA_RESULT": json.dumps({"result": "success", "outputs": {}})}, clear=True), \
                        patch.object(sdk_native_continuation, "select_native_state", return_value=selected):
                    if accepted:
                        exec(compile(script, "saved-core-binary-result", "exec"), {})
                        rows = dict(line.split("=", 1) for line in output.read_text().splitlines())
                        self.assertEqual(original if wave == "11" else {},
                                         {name: rows[name] for name in original if name in rows})
                    else:
                        with self.assertRaises(ValueError):
                            exec(compile(script, "saved-core-binary-result", "exec"), {})
                        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
