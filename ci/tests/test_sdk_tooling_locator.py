"""SDK workflow selection of one authenticated tooling transport locator."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/product-validation.yml"
DIGEST = "sha256:" + "d" * 64
PRODUCER = {
    "repository": "codex-agent-labs/codex-agent",
    "workflowPath": ".github/workflows/ci.yml",
    "commit": "a" * 40,
    "tree": "b" * 40,
    "event": "merge_group",
    "runId": 71,
    "runAttempt": 2,
    "pullRequest": None,
}


class SdkToolingLocatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_text = WORKFLOW.read_text(encoding="utf-8")
        cls.child_text = (WORKFLOW.parent / "contract-validation.yml").read_text(encoding="utf-8")
        cls.job = cls.source_text.split("\n  sdk-plan:\n", 1)[1].split("\n  sdk-workers-1:\n", 1)[0]
        cls.locator_job = cls.child_text.split("\n  product-tooling:\n", 1)[1].split(
            "\n  contract-continuation:\n", 1)[0]
        locator = cls.locator_job.split("      - id: tooling-locator\n", 1)[1]
        embedded = locator.split("          python3 - <<'PY'\n", 1)[1].rsplit("          PY", 1)[0]
        cls.script = textwrap.dedent(embedded)

    @staticmethod
    def source(result, identifier, digest, producer, *, prefix=""):
        return {"result": result, "outputs": {
            prefix + "artifact_id": identifier,
            prefix + "artifact_sha256": digest,
            prefix + "transport_producer": producer,
        }}

    def predecessors(self, miss="false"):
        return {
            "plan": {
                **self.source("success", "31", DIGEST, json.dumps(PRODUCER), prefix="tooling_"),
                "outputs": {
                    "tooling_miss": miss,
                    "tooling_artifact_id": "31",
                    "tooling_artifact_sha256": DIGEST,
                    "tooling_transport_producer": json.dumps(PRODUCER),
                },
            },
            "tooling-attestation": self.source(
                "success", "47", "sha256:" + "e" * 64,
                json.dumps({**PRODUCER, "runId": 73}),
            ),
        }

    def locate(self, needs):
        plan_outputs = needs["plan"]["outputs"]
        with tempfile.TemporaryDirectory(prefix="sdk-tooling-locator-") as temporary:
            output = Path(temporary) / "github-output"
            result = subprocess.run(
                [sys.executable, "-B", "-c", self.script],
                cwd=ROOT,
                env={"PREDECESSORS": json.dumps({"tooling-attestation": needs["tooling-attestation"]}),
                     "PLAN_OUTPUTS": json.dumps(plan_outputs), "GITHUB_OUTPUT": str(output)},
                text=True,
                capture_output=True,
            )
            values = None
            if output.exists():
                values = dict(line.split("=", 1)
                              for line in output.read_text(encoding="utf-8").splitlines())
            return result, values

    def test_hit_selects_only_the_existing_plan_locator(self):
        result, values = self.locate(self.predecessors())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("31", values["artifact_id"])
        self.assertEqual(DIGEST, values["artifact_sha256"])
        self.assertEqual(PRODUCER, json.loads(values["transport_producer"]))

    def test_miss_selects_only_the_fresh_attestation_locator(self):
        needs = self.predecessors("true")
        result, values = self.locate(needs)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("47", values["artifact_id"])
        self.assertEqual("sha256:" + "e" * 64, values["artifact_sha256"])
        self.assertEqual(73, json.loads(values["transport_producer"])["runId"])

    def test_selected_failure_has_no_fallback_to_the_other_source(self):
        for miss, failed in (("true", "tooling-attestation"),):
            needs = self.predecessors(miss)
            needs[failed]["result"] = "failure"
            with self.subTest(miss=miss):
                result, values = self.locate(needs)
                self.assertNotEqual(0, result.returncode)
                self.assertIsNone(values)
                self.assertIn("Selected tooling producer is incomplete", result.stderr)

    def test_incomplete_or_malformed_locator_is_rejected(self):
        cases = []
        for miss in ("", "TRUE"):
            cases.append(self.predecessors(miss))
        for field, value in (
            ("tooling_artifact_id", "0"),
            ("tooling_artifact_sha256", "d" * 64),
            ("tooling_transport_producer", "{}"),
        ):
            needs = self.predecessors()
            needs["plan"]["outputs"][field] = value
            cases.append(needs)
        for number, needs in enumerate(cases):
            with self.subTest(case=number):
                result, values = self.locate(needs)
                self.assertNotEqual(0, result.returncode)
                self.assertIsNone(values)

    def test_tooling_capture_precedes_state_capture_and_forwards_only_its_policy(self):
        self.assertIn("needs: [plan, contract-validation,", self.job)
        self.assertIn("needs: [tooling-attestation]", self.locator_job)
        self.assertNotIn("runtime-continuation", self.locator_job)
        self.assertNotIn("sdk-inputs", self.locator_job)
        tooling = self.job.index("      - id: tooling\n")
        parent = self.job.index("      - id: parent\n")
        capture = self.job.index("      - id: capture\n")
        self.assertLess(tooling, parent)
        self.assertLess(parent, capture)
        self.assertIn("fromJSON(inputs.planOutputs).tooling_required == 'true'", self.locator_job)
        for binding in (
            "artifact-id: ${{ needs.contract-validation.outputs.tooling_artifact_id }}",
            "artifact-sha256: ${{ needs.contract-validation.outputs.tooling_artifact_sha256 }}",
            "transport-producer: ${{ needs.contract-validation.outputs.tooling_transport_producer }}",
        ):
            self.assertIn(binding, self.job[tooling:parent])
        self.assertIn(
            "sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}",
            self.job[capture:],
        )

    def test_each_worker_and_collector_captures_the_immutable_locator_locally(self):
        jobs = (
            ("sdk-workers-1", "sdk-collect-1", "      - uses: ./.github/actions/sdk-javascript-worker\n"),
            ("sdk-collect-1", "sdk-workers-2", "      - id: collect\n"),
            ("sdk-workers-2", "sdk-collect-2", "      - uses: ./.github/actions/sdk-javascript-worker\n"),
            ("sdk-collect-2", "sdk-javascript", "      - id: collect\n"),
            ("sdk-native-plan", "sdk-native-prepare", "      - id: capture\n"),
            ("sdk-native-prepare", "sdk-native-workers", "      - id: prepare\n"),
            ("sdk-native-workers", "sdk-collect-4", "      - uses: ./.github/actions/sdk-native-package-worker\n"),
            ("sdk-collect-4", "sdk-native-packages", "      - id: collect\n"),
        )
        for name, following, consumer_marker in jobs:
            job = self.source_text.split(f"\n  {name}:\n", 1)[1].split(
                f"\n  {following}:\n", 1,
            )[0]
            with self.subTest(job=name):
                self.assertIn("sdk-plan", job.split("    steps:\n", 1)[0])
                checkout = job.index("      - uses: actions/checkout@")
                tooling = job.index("      - id: tooling\n")
                consumer = job.index(consumer_marker)
                self.assertLess(checkout, tooling)
                self.assertLess(tooling, consumer)
                self.assertEqual(1, job.count("uses: ./.github/actions/capture-sdk-tooling"))
                capture = job[tooling:consumer]
                self.assertIn("if: needs.plan.outputs.tooling_required == 'true'", capture)
                for binding in (
                    "artifact-id: ${{ needs.sdk-plan.outputs.tooling_artifact_id }}",
                    "artifact-sha256: ${{ needs.sdk-plan.outputs.tooling_artifact_sha256 }}",
                    "transport-producer: ${{ needs.sdk-plan.outputs.tooling_transport_producer }}",
                    "trusted-workflow-sha: ${{ inputs.trustedWorkflowSha }}",
                    "trusted-workflow-path: .github/workflows/contract-validation.yml",
                    "trusted-job-name: product-validation / contract-validation / product-contracts",
                    "policy-revision: ${{ needs.plan.outputs.validation_commit }}",
                ):
                    self.assertIn(binding, capture)
                self.assertNotIn("needs.tooling-attestation", capture)
                self.assertNotIn("needs.plan.outputs.tooling_artifact", capture)
                self.assertIn(
                    "sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}",
                    job[consumer:],
                )
                outputs = job.split("    steps:\n", 1)[0]
                self.assertNotIn("tooling-policy", outputs)
                self.assertNotIn("tooling_artifact", outputs)

    def test_upstream_resume_and_sdk_input_jobs_capture_before_semantic_replay(self):
        gate = self.source_text.split('\n  merge-gate:\n', 1)[1]
        self.assertIn('contract-validation', gate.split('    steps:', 1)[0])
        for name, end, marker in (
            ('product-resume', 'runtime-linux-arm64-supervisor', 'ci/product_reuse.py resume-products'),
            ('sdk-inputs', 'android', 'uses: ./.github/actions/capture-runtime-state'),
        ):
            job = self.source_text.split(f'\n  {name}:\n', 1)[1].split(f'\n  {end}:\n', 1)[0]
            with self.subTest(job=name):
                header = job.split('    steps:', 1)[0]
                self.assertIn('contract-validation', header)
                self.assertIn('always()', header)
                self.assertLess(job.index('uses: ./.github/actions/capture-sdk-tooling'), job.index(marker))
                self.assertIn('artifact-id: ${{ needs.contract-validation.outputs.tooling_artifact_id }}', job)
                self.assertIn('SDK_VALIDATION_TOOLING: ${{ steps.tooling.outputs.tooling-policy }}', job)
                self.assertIn('--sdk-validation-tooling "$SDK_VALIDATION_TOOLING"', job)
                self.assertNotIn('tooling-policy', header)


if __name__ == "__main__":
    unittest.main()
