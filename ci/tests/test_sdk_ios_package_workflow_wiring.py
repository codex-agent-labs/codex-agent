"""iOS package wave-five wiring, not hosted Apple package admission."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci import sdk_workflow  # Bootstrap the script-module import namespace.
from ci import sdk_native_continuation


ROOT = Path(__file__).resolve().parents[2]


class SdkIosPackageWorkflowWiringTest(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text()

    def job(self, name):
        match = re.search(
            rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)",
            self.workflow,
        )
        self.assertIsNotNone(match, name)
        return match[0]

    @staticmethod
    def locator(artifact="84", sdk_wave="4", digest="a"):
        return {
            "artifact_id": artifact,
            "artifact_digest": "sha256:" + digest * 64,
            "state_wave": "0",
            "sdk_state_wave": sdk_wave,
        }

    def needs(self, *, required="true", worker="success", collector="success", failed="false"):
        return {
            "sdk-native-packages": {"result": "success", "outputs": self.locator()},
            "sdk-ios-package-plan": {
                "result": "success",
                "outputs": {"sdk_workers_required": required},
            },
            "sdk-ios-package": {"result": worker, "outputs": {}},
            "sdk-collect-5": {
                "result": collector,
                "outputs": {
                    "artifact_id": "85",
                    "artifact_digest": "sha256:" + "b" * 64,
                    "wave_failed": failed,
                },
            },
        }

    def result(self, needs):
        source = self.job("sdk-ios-packages")
        match = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", source)
        self.assertIsNotNone(match)
        with tempfile.TemporaryDirectory(prefix="sdk-ios-package-result-") as temporary:
            output = Path(temporary) / "output"
            output.write_bytes(b"")
            with patch.dict(
                os.environ,
                {"RESULTS": json.dumps(needs), "GITHUB_OUTPUT": str(output)},
                clear=True,
            ), patch.object(
                sdk_native_continuation,
                "select_native_state",
                wraps=sdk_native_continuation.select_native_state,
            ) as select:
                try:
                    exec(compile(textwrap.dedent(match[1]), "ios-package-result", "exec"), {})
                except Exception:
                    self.assertEqual(b"", output.read_bytes())
                    raise
            select.assert_called_once_with(needs, stage="ios-package")
            return dict(line.split("=", 1) for line in output.read_text().splitlines())

    def test_plan_and_worker_use_the_authenticated_parent_inputs_and_fixed_apple_route(self):
        planned = self.job("sdk-ios-package-plan")
        condition = planned.split("    if: >-\n", 1)[1].split("    runs-on:", 1)[0]
        self.assertIn("needs.plan.outputs.event_authorized == 'true'", condition)
        self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", condition)
        self.assertIn("needs.sdk-native-packages.result == 'success'", condition)
        self.assertIn("needs.sdk-native-packages.outputs.artifact_id != ''", condition)
        self.assertIn("sdk-family: ios-package", planned)
        self.assertLess(planned.index("capture-sdk-tooling"), planned.index("capture-runtime-state"))

        worker = self.job("sdk-ios-package")
        self.assertIn("name: sdk-sdk-ios-package-ios", worker)
        self.assertIn("fail-fast: false", worker)
        self.assertIn("runs-on: ${{ matrix.runner }}", worker)
        self.assertIn("uses: ./.github/actions/sdk-ios-package-worker", worker)
        self.assertIn("developer-directory: /Applications/Xcode_26.6.app/Contents/Developer", worker)
        self.assertIn("policy-revision: ${{ needs.plan.outputs.validation_commit }}", worker)
        self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", worker)
        self.assertIn("sdk-inputs-id: ${{ needs.sdk-inputs.outputs.artifact_id }}", worker)
        self.assertIn("sdk-inputs-sha256: ${{ needs.sdk-inputs.outputs.artifact_digest }}", worker)
        worker_condition = worker.split("    if: >-\n", 1)[1].split("    strategy:", 1)[0]
        self.assertIn("needs.plan.outputs.event_authorized == 'true'", worker_condition)
        self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", worker_condition)

        for source in (planned, worker):
            for argument, field in (
                ("artifact-id", "artifact_id"),
                ("artifact-sha256", "artifact_digest"),
                ("state-wave", "state_wave"),
                ("sdk-state-wave", "sdk_state_wave"),
            ):
                self.assertIn(
                    f"{argument}: ${{{{ needs.sdk-native-packages.outputs.{field} }}}}", source,
                )

    def test_collection_final_gate_and_javascript_parent_are_exact(self):
        collector = self.job("sdk-collect-5")
        self.assertIn("sdk-ios-package]", collector)
        condition = collector.split("    if: >-\n", 1)[1].split("    runs-on:", 1)[0]
        self.assertIn("always()", condition)
        self.assertIn("needs.sdk-ios-package-plan.outputs.sdk_workers_required == 'true'", condition)
        self.assertNotIn("needs.sdk-ios-package.result", condition)
        self.assertIn("sdk-family: ios-package", collector)
        self.assertIn("wave: '5'", collector)

        final = self.job("sdk-ios-packages")
        for dependency in (
            "sdk-native-packages",
            "sdk-ios-package-plan",
            "sdk-ios-package",
            "sdk-collect-5",
        ):
            self.assertIn(dependency, final.split("    runs-on:", 1)[0])
        self.assertIn("stage='ios-package'", final)
        self.assertIn("sdk-ios-packages", self.job("merge-gate").split("    runs-on:", 1)[0])

        for name in (
            "sdk-javascript-metadata-plan",
            "sdk-javascript-metadata",
            "sdk-collect-6",
            "sdk-javascript-metadata-result",
        ):
            job = self.job(name)
            header = job.split("    runs-on:", 1)[0]
            self.assertIn("sdk-ios-packages", header)
            self.assertNotIn("sdk-native-packages", job)

    def test_selector_returns_wave_five_only_after_successful_collection(self):
        self.assertEqual(self.locator("85", "5", "b"), self.result(self.needs()))

        for mutation in (
            ("sdk-ios-package", "result", "failure"),
            ("sdk-collect-5", "result", "failure"),
            ("sdk-collect-5", "wave_failed", "true"),
            ("sdk-native-packages", "artifact_digest", "sha256:" + "c" * 63),
        ):
            invalid = deepcopy(self.needs())
            job, field, value = mutation
            if field == "result":
                invalid[job][field] = value
            else:
                invalid[job]["outputs"][field] = value
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.result(invalid)

    def test_selector_noop_preserves_the_exact_parent_and_rejects_phantom_work(self):
        noop = self.needs(required="false", worker="skipped", collector="skipped")
        noop["sdk-collect-5"]["outputs"] = {}
        parent = self.locator("91", "4", "d")
        noop["sdk-native-packages"]["outputs"] = parent
        self.assertEqual(parent, self.result(noop))

        for job in ("sdk-ios-package", "sdk-collect-5"):
            invalid = deepcopy(noop)
            invalid[job]["result"] = "success"
            with self.subTest(job=job), self.assertRaises(ValueError):
                self.result(invalid)


if __name__ == "__main__":
    unittest.main()
