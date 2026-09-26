"""Wave 17 never creates a fresh worker without caller-owned protected source pins."""

import json
import os
from pathlib import Path
import re
import tempfile
import textwrap
import unittest
from unittest.mock import patch


WORKFLOW = (Path(__file__).resolve().parents[2] /
            ".github/workflows/sdk-android-validation.yml")
PARENT = WORKFLOW.with_name("product-validation.yml")


def job(source, name):
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
    if match is None:
        raise AssertionError(f"Missing Android validation job: {name}")
    return match[0]


class AndroidValidationChildWorkflowTest(unittest.TestCase):
    def test_parent_elects_only_after_package_and_does_not_invent_authority(self):
        source = PARENT.read_text()
        plan = job(source, "sdk-android-validation-plan")
        caller = job(source, "sdk-android-validation-result")
        self.assertIn("needs.plan.outputs.remote_build_authorized == 'true'", plan)
        self.assertIn("needs.sdk-android-package-result.result == 'success'", plan)
        self.assertIn("sdk-family: android-validation", plan)
        self.assertIn("uses: ./.github/workflows/sdk-android-validation.yml", caller)
        self.assertIn("protectedAndroidAuthority: ''", caller)
        for gate in ("sdk-completion", "sdk-parity", "merge-gate"):
            self.assertIn("sdk-android-validation-result", job(source, gate).split("    needs:", 1)[1])

    def test_fresh_worker_requires_protected_authority_before_setup(self):
        source = WORKFLOW.read_text()
        worker = job(source, "sdk-android-validation")
        collector = job(source, "sdk-collect-17")
        for text in ("remote_build_authorized == 'true'",
                     "sdk_workers_required == 'true'",
                     "inputs.protectedAndroidAuthority != ''"):
            self.assertIn(text, worker)
            self.assertIn(text, collector)
        self.assertLess(worker.index("id: authority"), worker.index("android-actions/setup-android"))
        self.assertLess(worker.index("id: authority"), worker.index("sdk-android-validation-worker"))
        self.assertNotIn("VALIDATION_COMMIT", worker.split("      - id: authority\n", 1)[1].split("      - name:", 1)[0])
        authority = worker.split("- id: authority", 1)[1].split("- name: Select installed caller Java", 1)[0]
        self.assertIn("python3 -I -B -", authority)
        self.assertNotIn("from ci.", authority)
        self.assertIn("ci.sdk_android_validation_policy", worker)
        self.assertIn("sdk-worker-workflow-path: .github/workflows/sdk-android-validation.yml", collector)
        self.assertIn("sdk-worker-job-name: product-validation / sdk-android-validation-result / sdk-android-validation-android", collector)

    def test_worker_decodes_only_exact_canonical_authority(self):
        worker = job(WORKFLOW.read_text(), "sdk-android-validation")
        script = worker.split("          python3 -I -B - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
        value = {"schemaVersion": 1, "trustedAndroidWorkflowSha": "c" * 40,
                 "trustedSourceCommit": "a" * 40, "trustedSourceTree": "b" * 40}
        raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            for payload, valid in ((raw, True), (raw.removesuffix(b"\n"), False),
                                   (raw.replace(b'"schemaVersion":1', b'"schemaVersion":1,"schemaVersion":1'), False)):
                with self.subTest(payload=payload):
                    output.unlink(missing_ok=True)
                    with patch.dict(os.environ, {"AUTHORITY": payload.decode(), "GITHUB_OUTPUT": str(output)}, clear=True):
                        if valid:
                            exec(compile(textwrap.dedent(script), "android-worker-authority", "exec"), {})
                            self.assertIn("trustedSourceCommit=" + "a" * 40, output.read_text())
                        else:
                            with self.assertRaises(ValueError):
                                exec(compile(textwrap.dedent(script), "android-worker-authority", "exec"), {})
                            self.assertFalse(output.exists())

    def test_reuse_only_and_missing_authority_fail_closed(self):
        source = WORKFLOW.read_text()
        result = job(source, "sdk-android-validation-result")
        self.assertIn("Fresh Android validation lacks protected Firebase/source authority", result)
        self.assertIn("select_native_state(needs, stage='android-validation')", result)
        for field in ("validation_receipt_sha256", "validation_artifact_id",
                      "validation_artifact_sha256", "validation_run_id", "validation_run_attempt"):
            self.assertIn(field, result)
            self.assertIn(field + ":", source)


if __name__ == "__main__":
    unittest.main()
