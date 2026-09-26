"""Saved partial-catalog wiring; not hosted recovery or release admission."""

import json
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci.tests.test_sdk_partial_state import jobs


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
        for wave in (3, 1, 2, 4, 5, 6, 7, 8, 9, 10):
            self.assertIn(f"sdk-collect-{wave}.outputs.wave_failed == 'true'", job)
        self.assertIn("codex-agent-sdk-partial-catalog-v1-pull-request-$PR-$TREE-attempt-$ATTEMPT", job)
        self.assertIn("overwrite: false", job)
        self.assertNotIn("sdk-partial-catalog", self.completion)
        self.assertNotIn("sdk-partial-catalog", self.merge_gate)

    def test_saved_selector_forwards_only_exact_failed_original(self):
        script = re.search(r"(?ms)^          python3 - <<'PY'\n(.*?)^          PY$", self.job)
        self.assertIsNotNone(script)
        with tempfile.TemporaryDirectory(prefix="sdk-partial-workflow-") as temporary:
            output = Path(temporary) / "output"
            with patch.dict(os.environ, {"RESULTS": json.dumps(jobs(7)),
                                      "GITHUB_OUTPUT": str(output)}, clear=True):
                exec(compile(textwrap.dedent(script[1]), "saved-sdk-partial-parent", "exec"), {})
            self.assertEqual({"artifact_id": "107", "artifact_digest": "sha256:" + "a" * 64,
                              "state_wave": "0", "sdk_state_wave": "7"},
                             dict(line.split("=", 1) for line in output.read_text().splitlines()))


if __name__ == "__main__":
    unittest.main()
