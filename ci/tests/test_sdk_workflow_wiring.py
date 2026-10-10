"""Static SDK job wiring and executed summary controls, not hosted execution."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]


class SdkWorkflowWiringTest(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text()

    def job(self, name):
        return re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", self.workflow)[0]

    def test_portable_authority_is_optional_and_precedes_all_core_consumers(self):
        parent = self.job("sdk-core-validation-wave")
        self.assertIn("reuseQualification: ${{ inputs.reuseQualification }}", parent)
        self.assertIn("secrets:\n      authority_read_token: ${{ secrets.REUSE_AUTHORITY_READ_TOKEN }}", parent)
        self.assertNotIn("REUSE_AUTHORITY_READ_TOKEN", parent.split("    secrets:")[0])
        self.workflow = (ROOT / ".github/workflows/sdk-core-validation.yml").read_text()
        self.assertRegex(self.workflow, r"(?s)reuseQualification:\n.*?default: ''\n")
        self.assertRegex(self.workflow, r"(?s)    secrets:\n      authority_read_token:\n.*?required: false\n")
        self.assertEqual(6, self.workflow.count("${{ secrets.authority_read_token }}"))
        self.assertIn("independently reviewed", self.workflow)
        fields = {"artifact-id": "artifactId", "artifact-sha256": "artifactSha256",
                  "run-id": "runId", "run-attempt": "runAttempt",
                  "issuer-sha": "issuerSha", "source-sha": "sourceSha"}
        for name in ("sdk-core-validation-plan", "sdk-core-validation", "sdk-collect-13"):
            with self.subTest(job=name):
                job = self.job(name)
                restore = re.search(r"(?ms)^      - if: inputs.reuseQualification != ''\n"
                                    r".*?(?=^      -|\Z)", job)[0]
                self.assertIn("./.github/actions/restore-reuse-qualification", restore)
                self.assertIn("authority-read-token: ${{ secrets.authority_read_token }}", restore)
                approved = re.search(r"(?ms)^      - if: inputs.reuseQualification == ''\n"
                                     r".*?(?=^      -|\Z)", job)[0]
                self.assertIn("restore-reuse-qualification@reuse-authority", approved)
                self.assertNotIn("secrets.authority_read_token", job.replace(restore, "").replace(approved, ""))
                for argument, field in fields.items():
                    self.assertIn(f"{argument}: ${{{{ fromJSON(inputs.reuseQualification).{field} }}}}", restore)
                self.assertNotRegex(restore, r"planOutputs|sdkPlan|packageWave|github.event")
                self.assertLess(job.index(restore), job.index("./.github/actions/capture-sdk-tooling"))
                self.assertIn("remote_build_authorized == 'true'", job)

    def test_sdk_entry_restore_is_scoped_and_precedes_evidence_consumers(self):
        child_names = set()
        restored = 0
        for path in (ROOT / ".github/workflows").glob("*.yml"):
            text = path.read_text()
            if path.name != "product-validation.yml" and not path.name.startswith("sdk-"):
                continue
            jobs = re.findall(r"(?ms)^  ([a-z][a-z0-9-]*):\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)", text)
            for name, job in jobs:
                if "uses: codex-agent-labs/codex-agent/.github/actions/restore-reuse-qualification@reuse-authority" not in job:
                    continue
                restored += 1
                root = path.name == "product-validation.yml"
                token = "REUSE_AUTHORITY_READ_TOKEN" if root else "authority_read_token"
                step = re.search(r"(?ms)^      - (?:if: [^\n]+\n        )?uses: codex-agent-labs/codex-agent/"
                                 r"\.github/actions/restore-reuse-qualification@reuse-authority\n"
                                 r".*?(?=^      -|\Z)", job)[0]
                self.assertIn(f"authority-read-token: ${{{{ secrets.{token} }}}}", step)
                self.assertNotIn("env:", step)
                self.assertNotIn("github.event", step)
                self.assertLess(job.index("uses: actions/checkout@"), job.index(step))
                consumer = re.search(r"uses: \./\.github/actions/(?:capture-runtime-state|capture-sdk-transport|sdk-[a-z-]+-worker)", job)
                if consumer:
                    self.assertLess(job.index(step), consumer.start())
                if not root:
                    child_names.add(path.name)
                    self.assertRegex(text, r"(?s)    secrets:\n      authority_read_token:\n.*?required: false\n")
        self.assertEqual(63, restored)
        parent = (ROOT / ".github/workflows/product-validation.yml").read_text()
        for name in child_names:
            job = next(body for _, body in re.findall(
                r"(?ms)^  ([a-z][a-z0-9-]*):\n(.*?)(?=^  [a-z][a-z0-9-]*:|\Z)", parent)
                if f"uses: ./.github/workflows/{name}\n" in body)
            self.assertIn("secrets:\n      authority_read_token: ${{ secrets.REUSE_AUTHORITY_READ_TOKEN }}", job)

    def test_qualification_refresh_uses_existing_native_issuer_without_product_builds(self):
        caller = (ROOT / ".github/workflows/portable-reuse-proof.yml").read_text()
        cold = caller.split("  cold:\n", 1)[1].split("  warm:\n", 1)[0]
        self.assertIn("github.event.label.name == 'ci:reuse-refresh-proof'", cold)
        self.assertIn("github.event.pull_request.number == 31", cold)
        self.assertIn("github.event.pull_request.head.repo.fork == false", cold)
        self.assertIn("uses: ./.github/workflows/reuse-qualification.yml", cold)
        self.assertIn("refresh: true", cold)
        text = (ROOT / ".github/workflows/reuse-qualification.yml").read_text()
        self.assertRegex(text, r"(?s)refresh:\n.*?default: false\n")
        self.assertIn("if: inputs.refresh != true", text)
        self.assertIn("ref: ${{ job.workflow_sha }}", text)
        self.assertIn("ISSUER_SHA: ${{ job.workflow_sha }}", text)
        self.assertIn("ci/reuse_qualification.py issue-frozen", text)
        self.assertIn("subject-path: ${{ env.PROOF_WORK }}/qualification.json", text)
        self.assertIn("overwrite: false", text)
        self.assertNotRegex(text, r"gradlew|cargo build|cmake --build|xcodebuild")

    def test_elected_workers_capture_before_isolated_setup_and_always_collect(self):
        action = (ROOT / ".github/actions/sdk-javascript-worker/action.yml").read_text()
        self.assertLess(action.index("./.github/actions/capture-runtime-state"), action.index("./.github/actions/setup-kmp"))
        self.assertLess(action.index("JavaScript worker differs"), action.index("./.github/actions/setup-kmp"))
        self.assertIn("product-worker: 'true'", action)
        self.assertIn("ci.sdk_workflow javascript", action)
        self.assertIn("if: always() && steps.identity.outcome == 'success'", action)
        self.assertIn("overwrite: false", action)
        self.assertIn("attempt-${{ github.run_attempt }}", action)
        plan = self.job("sdk-plan")
        self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", plan)
        self.assertIn("runtime-continuation' if aggregate_state == 'not-selected' else 'runtime-aggregate-continuation'", plan)
        self.assertNotIn("setup-kmp", plan)
        for wave in (1, 2):
            worker = self.job(f"sdk-workers-{wave}")
            self.assertIn("fail-fast: false", worker)
            self.assertIn("remote_build_authorized == 'true'", worker)
            self.assertIn("name: sdk-javascript-${{ matrix.phase }}-node", worker)
            self.assertIn("./.github/actions/sdk-javascript-worker", worker)
            collector = self.job(f"sdk-collect-{wave}")
            self.assertIn("always()", collector)
            self.assertIn(f"sdk-workers-{wave}]", collector)
            self.assertIn("product: sdk", collector)
        self.assertNotIn("one_directory", self.job("sdk-javascript"))

    def summary(self, needs):
        source = self.job("sdk-javascript").split("python3 - <<'PY'\n", 1)[1].rsplit("          PY", 1)[0]
        with tempfile.TemporaryDirectory(prefix="sdk-summary-output-") as temporary:
            output = Path(temporary) / "github-output"
            output.write_bytes(b"")
            with patch.dict(os.environ, {"RESULTS": json.dumps(needs), "GITHUB_OUTPUT": str(output)}):
                try:
                    exec(compile(textwrap.dedent(source), "sdk-summary-fixture", "exec"), {})
                except Exception:
                    self.assertEqual(b"", output.read_bytes(), "Failed summary must not publish a parent state")
                    raise
            rows = [line.split("=", 1) for line in output.read_text().splitlines()]
            self.assertEqual(len(rows), len(dict(rows)), "Summary must not overwrite a selected state field")
            return dict(rows)

    @staticmethod
    def summary_fixture():
        return {"runtime-continuation": {"outputs": {"sdk_handoff_required": "true"}},
            "sdk-plan": {"result": "success", "outputs": {"sdk_workers_required": "true",
                "artifact_id": "101", "artifact_digest": "sha256:" + "a" * 64,
                "state_wave": "5", "sdk_state_wave": ""}},
            "sdk-collect-1": {"result": "success", "outputs": {"wave_failed": "false", "sdk_workers_required": "true",
                "artifact_id": "102", "artifact_digest": "sha256:" + "b" * 64}},
            "sdk-collect-2": {"result": "success", "outputs": {"wave_failed": "false",
                "artifact_id": "103", "artifact_digest": "sha256:" + "c" * 64}}}

    def test_summary_requires_every_elected_collection_and_explicit_next_wave(self):
        base = self.summary_fixture()
        self.summary(base)
        cases = (("sdk-plan", "result", "failure"), ("sdk-collect-1", "result", "skipped"),
                 ("sdk-collect-2", "result", "failure"), ("sdk-collect-1", "wave_failed", "true"),
                 ("sdk-collect-1", "sdk_workers_required", None))
        for job, field, value in cases:
            needs = deepcopy(base)
            target = needs[job] if field == "result" else needs[job]["outputs"]
            target[field] = value
            with self.subTest(job=job, field=field), self.assertRaises(ValueError):
                self.summary(needs)
        one_wave = deepcopy(base)
        one_wave["sdk-collect-1"]["outputs"]["sdk_workers_required"] = "false"
        one_wave["sdk-collect-2"] = {"result": "skipped", "outputs": {}}
        self.summary(one_wave)
        none = deepcopy(one_wave)
        none["sdk-plan"]["outputs"]["sdk_workers_required"] = "false"
        none["sdk-collect-1"] = {"result": "skipped", "outputs": {}}
        self.summary(none)
        none["sdk-plan"]["result"] = "skipped"
        with self.assertRaises(ValueError):
            self.summary(none)
        none["runtime-continuation"]["outputs"]["sdk_handoff_required"] = "false"
        self.assertEqual({}, self.summary(none))

    def test_summary_exports_exact_initial_or_last_elected_collection_state(self):
        for waves in (0, 1, 2):
            needs = self.summary_fixture()
            if waves == 0:
                needs["sdk-plan"]["outputs"]["sdk_workers_required"] = "false"
                needs["sdk-collect-1"] = {"result": "skipped", "outputs": {}}
            if waves < 2:
                needs["sdk-collect-2"] = {"result": "skipped", "outputs": {}}
            if waves == 1:
                needs["sdk-collect-1"]["outputs"]["sdk_workers_required"] = "false"
            selected = needs["sdk-plan" if waves == 0 else f"sdk-collect-{waves}"]["outputs"]
            expected = {"artifact_id": selected["artifact_id"], "artifact_digest": selected["artifact_digest"],
                        "state_wave": "5" if waves == 0 else "0", "sdk_state_wave": "" if waves == 0 else str(waves)}
            with self.subTest(waves=waves):
                self.assertEqual(expected, self.summary(needs))
            if waves == 0:
                needs["sdk-plan"]["outputs"].update(state_wave="0", sdk_state_wave="3")
                self.assertEqual({**expected, "state_wave": "0", "sdk_state_wave": "3"}, self.summary(needs))

    def test_summary_rejects_missing_malformed_or_failed_terminal_state_without_outputs(self):
        for wave in (0, 1, 2):
            for field, invalid in (("artifact_id", ""), ("artifact_id", "0"), ("artifact_id", "not-an-id"),
                                   ("artifact_digest", ""), ("artifact_digest", "sha256:" + "f" * 63),
                                   ("artifact_digest", "sha256:" + "f" * 64 + "\nartifact_id=999"),
                                   ("artifact_id", None)):
                needs = self.summary_fixture()
                if wave == 0:
                    needs["sdk-plan"]["outputs"]["sdk_workers_required"] = "false"
                    needs["sdk-collect-1"] = {"result": "skipped", "outputs": {}}
                if wave < 2:
                    needs["sdk-collect-2"] = {"result": "skipped", "outputs": {}}
                if wave == 1:
                    needs["sdk-collect-1"]["outputs"]["sdk_workers_required"] = "false"
                job = "sdk-plan" if wave == 0 else f"sdk-collect-{wave}"
                needs[job]["outputs"][field] = invalid
                with self.subTest(wave=wave, field=field, invalid=invalid), self.assertRaises(ValueError):
                    self.summary(needs)
        for result in ("failure", "cancelled", "skipped"):
            needs = self.summary_fixture()
            needs["sdk-collect-2"]["result"] = result
            with self.subTest(result=result), self.assertRaises(ValueError):
                self.summary(needs)

    def test_initial_state_wave_identity_must_be_complete_and_coherent(self):
        for runtime_wave, sdk_wave in (("", ""), ("6", ""), ("not-a-wave", ""), ("0", "99"), ("5", "3")):
            needs = self.summary_fixture()
            needs["sdk-plan"]["outputs"].update(sdk_workers_required="false", state_wave=runtime_wave, sdk_state_wave=sdk_wave)
            for wave in (1, 2):
                needs[f"sdk-collect-{wave}"] = {"result": "skipped", "outputs": {}}
            with self.subTest(runtime_wave=runtime_wave, sdk_wave=sdk_wave), self.assertRaises(ValueError):
                self.summary(needs)


if __name__ == "__main__":
    unittest.main()
