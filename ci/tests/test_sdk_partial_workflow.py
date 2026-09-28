"""Saved partial-catalog wiring; not hosted recovery or release admission."""

import json
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci import sdk_nested_wave_locator
from ci.tests.test_sdk_nested_partial_state import _CHILDREN, children
from ci.tests.test_sdk_partial_state import jobs

product_reuse = sdk_nested_wave_locator.products


ROOT = Path(__file__).resolve().parents[2]


class SdkPartialWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / ".github/workflows/product-validation.yml").read_text()
        cls.job = source.split("  sdk-partial-catalog:\n", 1)[1].split("\n  sdk-catalog:\n", 1)[0]
        cls.completion = source.split("  sdk-completion:\n", 1)[1].split("\n  sdk-partial-catalog:\n", 1)[0]
        cls.merge_gate = source.split("  merge-gate:\n", 1)[1]

    def test_failed_collector_is_selected_before_capture_or_tool_setup(self):
        job = self.job
        self.assertLess(job.index("select_failed_sdk_wave_state"), job.index("capture-sdk-tooling"))
        self.assertLess(job.index("capture-runtime-state"), job.index("sdk_campaign_partial_catalog_caller"))
        self.assertIn("needs.sdk-completion.result == 'failure'", job)
        self.assertIn("product: sdk", job)
        for wave in (3, 1, 2, 19, 4, 5, 6, 7, 8, 9, 10):
            self.assertIn(f"sdk-collect-{wave}.outputs.wave_failed == 'true'", job)
        for name in ("sdk-core-binary-wave", "sdk-core-package-wave",
                     "sdk-core-validation-wave", "sdk-core-metadata-wave",
                     "sdk-android-binary-result", "sdk-android-package-result"):
            self.assertIn(f"needs.{name}.result == 'failure'", job)
        self.assertLess(job.index("select_failed_nested_sdk_wave"), job.index("capture-sdk-tooling"))
        self.assertLess(job.index("locate_current_failed_nested_sdk_wave"), job.index("capture-runtime-state"))
        self.assertIn("codex-agent-sdk-partial-catalog-v1-pull-request-$PR-$TREE-attempt-$ATTEMPT", job)
        self.assertIn("overwrite: false", job)
        self.assertNotIn("sdk-partial-catalog", self.completion)
        self.assertNotIn("sdk-partial-catalog", self.merge_gate)

    def test_saved_selector_forwards_only_exact_failed_original(self):
        script = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", self.job)
        self.assertIsNotNone(script)
        for wave in (19, 7):
            with self.subTest(wave=wave), tempfile.TemporaryDirectory(prefix="sdk-partial-workflow-") as temporary:
                output = Path(temporary) / "output"
                needs = jobs(wave)
                needs.update({name: {"result": "skipped", "outputs": {}} for name in _CHILDREN})
                with patch.dict(os.environ, {"RESULTS": json.dumps(needs),
                                          "GITHUB_OUTPUT": str(output)}, clear=True):
                    exec(compile(textwrap.dedent(script[1]), "saved-sdk-partial-parent", "exec"), {})
                self.assertEqual({"artifact_id": str(100 + wave), "artifact_digest": "sha256:" + "a" * 64,
                                  "state_wave": "0", "sdk_state_wave": str(wave)},
                                 dict(line.split("=", 1) for line in output.read_text().splitlines()))

    def test_saved_selector_recovers_exact_current_nested_collector(self):
        script = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", self.job)
        self.assertIsNotNone(script)
        needs = jobs(10)
        needs["sdk-collect-10"]["outputs"]["wave_failed"] = "false"
        needs.update(children(12))
        pin = {"artifact_id": 912, "artifact_sha256": "sha256:" + "b" * 64}
        with tempfile.TemporaryDirectory(prefix="sdk-nested-partial-workflow-") as temporary:
            output = Path(temporary) / "output"
            environment = {"RESULTS": json.dumps(needs), "GITHUB_OUTPUT": str(output),
                           "GITHUB_WORKSPACE": temporary,
                           "PLAN": str(Path(temporary) / "plan.json"),
                           "TRUSTED_WORKFLOW_SHA": "c" * 40,
                           "GITHUB_TOKEN": "test-token"}
            with patch.dict(os.environ, environment, clear=True), \
                    patch.object(product_reuse, "_validate_plan", return_value={"event": "pull_request"}), \
                    patch.object(product_reuse, "_consumer", return_value={"producer": {"runId": 7}}), \
                    patch.object(sdk_nested_wave_locator,
                        "locate_current_failed_nested_sdk_wave", return_value=pin) as locate:
                exec(compile(textwrap.dedent(script[1]), "saved-sdk-nested-partial-parent", "exec"), {})
            self.assertEqual({"artifact_id": "912", "artifact_digest": pin["artifact_sha256"],
                              "state_wave": "0", "sdk_state_wave": "12"},
                             dict(line.split("=", 1) for line in output.read_text().splitlines()))
            locate.assert_called_once_with({"runId": 7}, wave=12,
                trusted_workflow_sha="c" * 40, token="test-token", environ=os.environ)


if __name__ == "__main__":
    unittest.main()
