"""Execute the actual completed-state selector, without hosted/product admission."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest

from ci.tests.test_contract_attestation_workflow import workflow_job


class RuntimeAggregateContinuationWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml").read_text()
        cls.job = workflow_job(cls.source, "runtime-aggregate-continuation")
        scripts = re.findall(r"^          python3 - <<'PY'\n(.*?)^          PY$", cls.job, re.M | re.S)
        if len(scripts) != 1:
            raise AssertionError("Expected the sole completed-state selector")
        cls.script = textwrap.dedent(scripts[0])

    def fixture(self, fresh):
        output = {"aggregate_required": str(fresh).lower(), "aggregate_state": "ready" if fresh else "completed",
                  "aggregate_payload_complete": str(not fresh).lower(), "aggregate_key": "sha256:" + "a" * 64,
                  "aggregate_receipt_sha256": "" if fresh else "sha256:" + "b" * 64,
                  "artifact_id": "101", "artifact_digest": "sha256:" + "c" * 64, "state_wave": "2"}
        collected = {**output, "aggregate_payload_complete": "true", "aggregate_receipt_sha256": "sha256:" + "d" * 64,
                     "artifact_id": "105", "artifact_digest": "sha256:" + "e" * 64, "wave_failed": "false"}
        return {"runtime-continuation": {"result": "success", "outputs": output},
                "runtime-collect-5": {"result": "success" if fresh else "skipped", "outputs": collected if fresh else {}}}

    def run_selector(self, needs, expected_wave=None):
        with tempfile.TemporaryDirectory(prefix="aggregate-selection-") as temporary:
            output = Path(temporary) / "output"
            environment = {key: value for key, value in os.environ.items() if key in {"SYSTEMROOT", "WINDIR"}}
            environment.update(PREDECESSORS=json.dumps(needs), GITHUB_OUTPUT=str(output))
            result = subprocess.run([sys.executable, "-I", "-B", "-c", self.script], cwd=temporary,
                                    env=environment, capture_output=True, text=True)
            if expected_wave is None:
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(output.exists(), "Rejected selection emitted partial outputs")
            else:
                self.assertEqual(0, result.returncode, result.stderr)
                parent = needs["runtime-collect-5" if expected_wave == "5" else "runtime-continuation"]["outputs"]
                self.assertEqual({"state_wave": expected_wave, "artifact_id": parent["artifact_id"],
                                  "artifact_digest": parent["artifact_digest"]},
                                 dict(line.split("=", 1) for line in output.read_text().splitlines()))

    def test_fresh_wave_five_and_every_retained_original_wave_preserve_upload_identity(self):
        self.run_selector(self.fixture(True), "5")
        for wave in range(5):
            needs = self.fixture(False)
            needs["runtime-continuation"]["outputs"]["state_wave"] = str(wave)
            self.run_selector(needs, str(wave))

    def test_failed_skipped_cancelled_and_unexpected_collection_reject(self):
        for fresh in (True, False):
            for name in ("runtime-continuation", "runtime-collect-5"):
                for result in ("failure", "cancelled", "in_progress", "skipped", "success"):
                    needs = self.fixture(fresh)
                    if needs[name]["result"] == result:
                        continue
                    needs[name]["result"] = result
                    with self.subTest(fresh=fresh, name=name, result=result):
                        self.run_selector(needs)

    def test_missing_malformed_crosspaired_and_incomplete_outputs_never_route(self):
        for fresh in (True, False):
            good = self.fixture(fresh)
            selected = "runtime-collect-5" if fresh else "runtime-continuation"
            for field, value in (("artifact_id", "0"), ("artifact_id", "001"), ("artifact_digest", "sha256:" + "A" * 64),
                                 ("aggregate_receipt_sha256", ""), ("aggregate_key", "sha256:" + "f" * 64),
                                 ("aggregate_payload_complete", "false")):
                if not fresh and field == "aggregate_key":
                    value = "invalid"
                needs = deepcopy(good)
                needs[selected]["outputs"][field] = value
                self.run_selector(needs)
            for field in ("artifact_id", "artifact_digest", "aggregate_receipt_sha256", "aggregate_key"):
                needs = deepcopy(good)
                del needs[selected]["outputs"][field]
                self.run_selector(needs)
        for field, value in (("wave_failed", "true"), ("wave_failed", "")):
            needs = self.fixture(True)
            needs["runtime-collect-5"]["outputs"][field] = value
            self.run_selector(needs)
        for wave in ("5", "-1", "02", ""):
            needs = self.fixture(False)
            needs["runtime-continuation"]["outputs"]["state_wave"] = wave
            self.run_selector(needs)

    def test_authorization_capture_and_full_completed_replay_precede_signing_consumers(self):
        guard = self.job.split("    runs-on:")[0]
        for value in ("always()", "remote_build_authorized == 'true'", "event_authorized == 'true'",
                      "aggregate_state != 'not-selected'", "!contains(needs.*.result, 'failure')"):
            self.assertIn(value, guard)
        self.assertLess(self.job.index("id: parent"), self.job.index("id: captured"))
        self.assertLess(self.job.index("id: captured"), self.job.index("id: route"))
        self.assertIn("ci/runtime_workflow.py continuation --require-completed", self.job)
        self.assertNotRegex(self.job, r"secrets\.|PRIVATE_KEY|actions/setup-|setup-kmp|\./gradlew")
        self.assertIn("runtime-aggregate-continuation", workflow_job(self.source, "merge-gate"))


if __name__ == "__main__":
    unittest.main()
