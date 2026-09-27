"""The uninvoked failed-SDK-catalog carrier requires independent protected pins."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

from ci.products.inventory import sha256_bytes
from ci.tests.test_contract_attestation_workflow import workflow_job


WORKFLOW = (Path(__file__).resolve().parents[2] /
            ".github/workflows/sdk-failed-catalog-custody.yml")


class SdkCatalogCustodyWorkflowTest(unittest.TestCase):
    def test_later_dispatch_is_isolated_from_product_validation_and_merge_gate(self):
        caller = WORKFLOW.with_name("ci.yml").read_text(encoding="utf-8")
        dispatch = caller.split("  workflow_dispatch:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertIn("default: validation", dispatch)
        self.assertIn("options: [validation, sdk-catalog-custody, runtime-phase10-record, contract-phase10-record, sdk-phase10-authority, sdk-phase10-record]", dispatch)
        self.assertEqual(10, len(re.findall(r"^      [A-Za-z][A-Za-z0-9]*:\s*$", dispatch, re.MULTILINE)))
        validation = workflow_job(caller, "product-validation")
        custody = workflow_job(caller, "sdk-failed-catalog-custody")
        gate = workflow_job(caller, "merge-gate")
        self.assertIn("if: github.event_name != 'workflow_dispatch' || inputs.purpose == 'validation'", validation)
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.purpose == 'sdk-catalog-custody'", custody)
        self.assertIn("'SDK custody / complete' ||", gate)
        self.assertIn("if: always()", gate)
        self.assertIn("needs: [product-validation, sdk-failed-catalog-custody, runtime-phase10-record, contract-phase10-record, sdk-phase10-authority, sdk-phase10-record]", gate)
        gate_script = textwrap.dedent(gate.split("        run: |\n", 1)[1])
        for event, purpose, product, custody_result, accepted in (
                ("pull_request", "", "success", "skipped", True),
                ("workflow_dispatch", "validation", "success", "skipped", True),
                ("workflow_dispatch", "sdk-catalog-custody", "skipped", "success", True),
                ("workflow_dispatch", "sdk-catalog-custody", "success", "success", False),
                ("workflow_dispatch", "other", "skipped", "skipped", False)):
            environment = {**os.environ, "EVENT": event, "PURPOSE": purpose,
                "PRODUCT_VALIDATION_RESULT": product, "SDK_CUSTODY_RESULT": custody_result,
                "RUNTIME_RECORD_RESULT": "skipped", "CONTRACT_RECORD_RESULT": "skipped",
                "SDK_AUTHORITY_RESULT": "skipped", "SDK_RECORD_RESULT": "skipped"}
            result = subprocess.run(["bash", "-e", "-c", gate_script], env=environment,
                capture_output=True, text=True, timeout=10)
            self.assertEqual(0 if accepted else 1, result.returncode,
                (event, purpose, product, custody_result, result.stderr))
        self.assertIn("secrets: inherit", custody)
        pin = re.search(r"sdk-failed-catalog-custody\.yml@([0-9a-f]{40})", custody)
        self.assertIsNotNone(pin)
        selected = subprocess.run(["git", "show", f"{pin.group(1)}:.github/workflows/sdk-failed-catalog-custody.yml"],
            cwd=WORKFLOW.parents[2], capture_output=True, text=True, check=True)
        self.assertEqual(WORKFLOW.read_text(encoding="utf-8"), selected.stdout)

    def test_protected_selection_precedes_checkout_and_rejects_substitution(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        step = workflow.split(
            "      - name: Require independently approved catalog and source before checkout\n", 1
        )[1]
        script = textwrap.dedent(step.split("        run: |\n", 1)[1].split(
            "      - name: Check out reviewed custody verifier and signing policy\n", 1
        )[0])
        producer = '{"commit":"' + 'a' * 40 + '"}\n'
        protected = {
            "PROTECTED_SOURCE_SHA": "a" * 40,
            "PROTECTED_PRODUCER_SHA256": sha256_bytes(producer.encode()),
            "PROTECTED_ARTIFACT_ID": "123",
            "PROTECTED_ARTIFACT_SHA256": "sha256:" + "b" * 64,
            "PROTECTED_WORKFLOW_SHA": "c" * 40,
            "PROTECTED_WORKFLOW_PATH": ".github/workflows/product-validation.yml",
            "PROTECTED_JOB_NAME": "product-validation / sdk-partial-catalog",
        }
        caller = {
            "CALLER_ARTIFACT_ID": protected["PROTECTED_ARTIFACT_ID"],
            "CALLER_ARTIFACT_SHA256": protected["PROTECTED_ARTIFACT_SHA256"],
            "CALLER_WORKFLOW_SHA": protected["PROTECTED_WORKFLOW_SHA"],
            "CALLER_WORKFLOW_PATH": protected["PROTECTED_WORKFLOW_PATH"],
            "CALLER_JOB_NAME": protected["PROTECTED_JOB_NAME"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for changed in (None, *protected, *caller,
                            ("PROTECTED_SOURCE_SHA", "z" * 40),
                            ("PROTECTED_ARTIFACT_ID", "not-number"),
                            ("PROTECTED_ARTIFACT_SHA256", "sha256:bad"),
                            ("PROTECTED_WORKFLOW_SHA", "z" * 40),
                            ("PROTECTED_JOB_NAME", "job\nforged=1")):
                output = root / "output"
                env = {**os.environ, **protected, **caller,
                       "PRODUCER_JSON": producer,
                       "GITHUB_REPOSITORY": "codex-agent-labs/codex-agent",
                       "RUNNER_TEMP": temporary, "GITHUB_OUTPUT": str(output)}
                if changed:
                    key, value = (changed, "") if isinstance(changed, str) else changed
                    env[key] = value
                result = subprocess.run(["bash", "-c", script], env=env,
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(0 if changed is None else 1, result.returncode,
                                 (changed, result.stderr))
                if changed:
                    self.assertFalse(output.exists())
                else:
                    self.assertEqual(7, len(output.read_text().splitlines()))
                    output.unlink()

    def test_signing_is_scoped_and_no_catalog_is_repacked(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("  workflow_call:\n", workflow)
        self.assertNotIn("  workflow_dispatch:\n", workflow)
        self.assertIn("    environment: product-attestation\n", workflow)
        self.assertIn("ref: ${{ steps.authority.outputs.source_sha }}", workflow)
        self.assertIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY: ${{ secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY }}", workflow)
        self.assertEqual(1, workflow.count("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY:"))
        self.assertIn("unset GITHUB_TOKEN GH_TOKEN ACTIONS_RUNTIME_TOKEN", workflow)
        self.assertIn("sdk_catalog_custody.py prepare", workflow)
        self.assertIn("sdk_catalog_custody_signer.py", workflow)
        self.assertIn("sdk_catalog_custody.py verify", workflow)
        self.assertLess(workflow.index("sdk_catalog_custody.py verify"),
                        workflow.index("uses: actions/upload-artifact@"))
        self.assertNotIn("./gradlew", workflow)
        self.assertNotIn("build/ci/sdk-partial-catalog", workflow)


if __name__ == "__main__":
    unittest.main()
