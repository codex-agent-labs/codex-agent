"""Saved Core validation child wiring; real eleven-host evidence remains pending."""

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
CHILD = WORKFLOW.with_name("sdk-core-validation.yml")


class CoreValidationWorkflowTest(unittest.TestCase):
    def test_wave_thirteen_uses_original_inputs_and_fails_after_collection(self):
        source = CHILD.read_text()

        def job(name):
            found = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
            self.assertIsNotNone(found, name)
            return found[0]

        parent = WORKFLOW.read_text()
        plan, worker, collect, result = (job(name) for name in (
            "sdk-core-validation-plan", "sdk-core-validation", "sdk-collect-13",
            "sdk-core-validation-result"))
        self.assertIn("uses: ./.github/workflows/sdk-core-validation.yml", parent)
        self.assertIn("sdk-core-validation-wave", parent.split("  sdk-completion:\n", 1)[1].split("\n", 1)[0])
        for block in (plan, worker, collect, result):
            self.assertIn("fromJSON(inputs.planOutputs).remote_build_authorized == 'true'", block)
            self.assertIn("fromJSON(inputs.packageWave).result == 'success'", block)
        self.assertIn("sdk-family: core-validation", plan)
        self.assertIn("sdk-family: core-validation", collect)
        self.assertIn("wave: '13'", collect)
        self.assertIn("sdk-worker-workflow-path: .github/workflows/sdk-core-validation.yml", collect)
        self.assertIn("sdk-worker-job-name: product-validation / sdk-core-validation-wave / sdk-core-validation-{target}", collect)
        self.assertIn("runs-on: ${{ matrix.runner }}", worker)
        self.assertIn("fail-fast: false", worker)
        self.assertIn("fromJSON(inputs.sdkInputs).result == 'success'", worker)
        self.assertIn("uses: ./.github/actions/capture-sdk-tooling", worker)
        self.assertIn("ci.sdk_core_native_archive_provision", worker)
        self.assertIn("name: Provision only Git-pinned native compiler archives\n        shell: bash", worker)
        self.assertIn("name: Select installed caller Java\n        shell: bash", worker)
        self.assertIn("uses: ./.github/actions/sdk-core-validation-worker", worker)
        self.assertLess(worker.index("ci.sdk_core_native_archive_provision"),
                        worker.index("uses: ./.github/actions/sdk-core-validation-worker"))
        for field in ("sdk-inputs-id", "sdk-inputs-sha256", "sdk-validation-tooling",
                      "sdk-apple-validation-policy", "native-compiler-archive", "build-key", "tree"):
            self.assertIn(field + ":", worker)
        self.assertIn("needs['sdk-core-package-wave'] = json.loads(os.environ['PACKAGE_RESULT'])", result)
        self.assertIn("select_native_state(needs, stage='core-validation')", result)

    def test_child_result_rejoins_package_parent_before_selection(self):
        block = CHILD.read_text().split("  sdk-core-validation-result:\n", 1)[1]
        script = textwrap.dedent(block.split("          python3 - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        for required in (False, True):
            needs = needs_for("core-validation", required=required, state=locator("12", "0"))
            package = needs.pop("sdk-core-package-wave")
            with self.subTest(required=required), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / "output"
                with patch.dict(os.environ, {"RESULTS": json.dumps(needs),
                                          "PACKAGE_RESULT": json.dumps(package),
                                          "GITHUB_OUTPUT": str(output)}, clear=True):
                    exec(compile(script, "sdk-core-validation-result", "exec"), {})
                values = dict(line.split("=", 1) for line in output.read_text().splitlines())
                self.assertEqual("13" if required else "12", values["sdk_state_wave"])
                package["result"] = "failure"
                with patch.dict(os.environ, {"RESULTS": json.dumps(needs),
                                          "PACKAGE_RESULT": json.dumps(package),
                                          "GITHUB_OUTPUT": str(output)}, clear=True), self.assertRaises(ValueError):
                    exec(compile(script, "sdk-core-validation-result", "exec"), {})


if __name__ == "__main__":
    unittest.main()
