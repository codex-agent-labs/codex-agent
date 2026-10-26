"""Static custody checks only; protected approvals and hosted bytes are not simulated."""

from pathlib import Path
from contextlib import chdir
from copy import deepcopy
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch
import zipfile

from ci import product_reuse
from ci.tests.test_contract_attestation_workflow import workflow_job
from ci.products.inventory import canonical_json_bytes, sha256_bytes, sha256_file


WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/runtime-library-authorizations.yml"


class RuntimeLibraryAuthorizationsWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.delegate = workflow_job(cls.source, "delegate")
        cls.capture = workflow_job(cls.source, "capture")
        cls.authorize = workflow_job(cls.source, "authorize")

    def test_protected_jobs_have_distinct_private_keys(self):
        self.assertIn("  workflow_call:", self.source)
        self.assertNotIn("  workflow_dispatch:", self.source)
        self.assertIn("environment: sdk-runtime-root-attestation", self.delegate)
        self.assertIn("environment: product-attestation", self.authorize)
        self.assertNotIn("    environment:", self.capture)
        self.assertIn("secrets.CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY", self.delegate)
        self.assertNotIn("secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", self.delegate)
        self.assertNotIn("GITHUB_TOKEN:", self.delegate)
        self.assertNotIn("secrets.", self.capture)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", self.capture)
        self.assertIn("secrets.CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", self.authorize)
        self.assertNotIn("secrets.CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY", self.authorize)
        self.assertNotIn("GITHUB_TOKEN:", self.authorize)

    def test_control_is_independently_approved_in_both_protected_environments(self):
        for job in (self.delegate, self.authorize):
            self.assertIn("vars.CODEX_AGENT_RUNTIME_PHASE10_CONTROL_APPROVED_SHA256", job)
            self.assertIn("vars.CODEX_AGENT_SDK_RUNTIME_VALIDATION_CONTROL_SHA256", job)
            self.assertIn("vars.CODEX_AGENT_PRODUCT_TRUSTED_SOURCE_SHA", job)
            self.assertIn("vars.CODEX_AGENT_SDK_RUNTIME_ROOT_PUBLIC_KEY_SHA256", job)
            self.assertIn("sha256sum", job)
            self.assertIn("persist-credentials: false", job)
        self.assertIn("CODEX_AGENT_PRODUCT_KEYRING_SHA256", self.delegate)
        self.assertIn("CODEX_AGENT_PRODUCT_KEYS_INVENTORY_SHA256", self.delegate)
        self.assertIn("runtime_phase10_library_caller.py delegate", self.delegate)
        self.assertIn("runtime_phase10_library_caller.py authorize", self.authorize)
        self.assertIn("--expected-delegation-inventory-sha256", self.authorize)

    def test_validation_control_has_separate_exact_schema_and_no_pin_fallback(self):
        control = dict(schemaVersion=1, originalRunId=23, originalRunAttempt=1,
            validationCommit="b" * 40, validationTree="c" * 40, planArtifactId=17,
            aggregateArtifactId=19, trustedSourceCommit="a" * 40,
            aggregateWorkflowSha="d" * 40)
        control.update({name: "sha256:" + "e" * 64 for name in (
            "planArtifactSha256", "aggregateArtifactSha256", "aggregateBuildKey",
            "metadataReceiptSha256")})
        legacy = {**control, "sidecarArtifactId": 21, "sidecarWorkflowSha": "f" * 40,
                  "sidecarArtifactSha256": "sha256:" + "1" * 64,
                  "pgpKeySha256": "sha256:" + "2" * 64}
        validation = {**control, "kind": "sdk-runtime-library-validation"}
        scripts = [textwrap.dedent(job.split("        run: |\n", 1)[1].split("      - name:", 1)[0])
                   for job in (self.delegate, self.authorize)]
        with tempfile.TemporaryDirectory() as temporary:
            environment = {**os.environ, "RUNNER_TEMP": temporary,
                "GITHUB_OUTPUT": str(Path(temporary) / "output"), "SOURCE_SHA": "a" * 40,
                "ROOT_SHA256": "sha256:" + "3" * 64, "KEYRING_SHA256": "sha256:" + "4" * 64,
                "KEYS_INVENTORY_SHA256": "sha256:" + "5" * 64,
                "DELEGATED_SOURCE_SHA": "a" * 40, "DELEGATED_ROOT_SHA256": "sha256:" + "3" * 64,
                "DELEGATION_INVENTORY_SHA256": "sha256:" + "6" * 64,
                "CAPTURE_INVENTORY_SHA256": "sha256:" + "7" * 64}
            cases = [(False, legacy, True), (True, validation, True), (True, legacy, False),
                     (False, validation, False), (True, {**validation, "extra": 1}, False),
                     (True, {**validation, "kind": "runtime-library-authorizations"}, False),
                     (True, {**validation, "originalRunId": True}, False)]
            for mode, value, accepted in cases:
                raw = canonical_json_bytes(value)
                env = {**environment, "VALIDATION_ONLY": str(mode).lower(),
                    "CONTROL_JSON": raw.decode().rstrip("\n"),
                    "CONTROL_SHA256": sha256_bytes(raw), "VALIDATION_CONTROL_SHA256": sha256_bytes(raw),
                    "DELEGATED_CONTROL_SHA256": sha256_bytes(raw)}
                with self.subTest(mode=mode, value=value):
                    result = subprocess.run(["bash", "-e", "-c", scripts[0]], env=env,
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(0 if accepted else 1, result.returncode, result.stderr)
                if accepted:
                    for script in scripts:
                        result = subprocess.run(["bash", "-e", "-c", script], env=env,
                                                capture_output=True, text=True, timeout=10)
                        self.assertEqual(0, result.returncode, result.stderr)
                        if mode:
                            result = subprocess.run(["bash", "-e", "-c", script],
                                env={**env, "VALIDATION_CONTROL_SHA256": ""},
                                capture_output=True, text=True, timeout=10)
                            self.assertNotEqual(0, result.returncode, "Phase-9 pin fell back to Phase 10")

    def test_validation_dispatch_signs_only_sidecars_and_is_not_full_acceptance(self):
        caller = WORKFLOW.with_name("ci.yml").read_text(encoding="utf-8")
        child = workflow_job(caller, "sdk-runtime-library-validation")
        self.assertIn("inputs.purpose == 'sdk-runtime-library-validation'", child)
        self.assertRegex(child, r"runtime-library-authorizations\.yml@[0-9a-f]{40}(?:\s|$)")
        self.assertIn("validation-only: true", child)
        self.assertIn("inputs.validation-only && github.event.inputs.purpose == 'sdk-runtime-library-validation'", self.delegate)
        self.assertIn("true) projection+=(--sidecars-only)", self.authorize)
        self.assertIn('"${projection[@]}"', self.authorize)
        self.assertNotRegex(self.source, r"(?:\./gradlew|cargo build|cmake --build|xcodebuild)")
        gate = workflow_job(caller, "merge-gate")
        self.assertIn("'SDK Runtime trust / complete'", gate)
        script = textwrap.dedent(gate.split("        run: |\n", 1)[1])
        env = {**os.environ, **{name: "skipped" for name in re.findall(r"\b([A-Z_]+_RESULT):", gate)},
            "EVENT": "workflow_dispatch", "PURPOSE": "sdk-runtime-library-validation",
            "SDK_RUNTIME_TRUST_RESULT": "success", "SDK_RUNTIME_TRUST_ID": "123",
            "SDK_RUNTIME_TRUST_SHA256": "sha256:" + "a" * 64}
        for change in ({}, {"SDK_RUNTIME_TRUST_RESULT": "failure"}, {"SDK_RUNTIME_TRUST_ID": ""},
                       {"SDK_RUNTIME_TRUST_SHA256": "sha256:bad"}, {"PRODUCT_VALIDATION_RESULT": "success"},
                       {"RUNTIME_RECORD_RESULT": "success"}, {"SDK_MAVEN_RESULT": "success"}):
            result = subprocess.run(["bash", "-e", "-c", script], env={**env, **change},
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(0 if not change else 1, result.returncode, (change, result.stderr))

    def test_original_capture_is_token_only_and_pinned_before_release_signing(self):
        self.assertIn("needs: delegate", self.capture)
        self.assertIn("needs: [delegate, capture]", self.authorize)
        self.assertIn("products._download_contract_ci_upload(", self.capture)
        self.assertIn("verified_zip_contents(", self.capture)
        self.assertIn("safe_extract(archive, Path('plan'))", self.capture)
        self.assertLess(self.capture.index("products._download_contract_ci_upload("),
                        self.capture.index("safe_extract(archive, Path('plan'))"))
        self.assertIn("regular_file_inventory(Path('plan'), allow_empty=True) != files", self.capture)
        self.assertIn("git -C validation-source rev-parse 'HEAD^{tree}'", self.capture)
        self.assertIn("--original-run-id", self.capture)
        self.assertIn("--original-run-attempt", self.capture)
        self.assertIn("--trusted-workflow-sha", self.capture)
        self.assertIn("runtime_phase10_upload_locator.py", self.capture)
        self.assertIn("--expected-build-key", self.capture)
        self.assertIn("--expected-metadata-receipt-sha256", self.capture)
        self.assertIn("regular_file_inventory(Path(sys.argv[1]), allow_empty=True)", self.authorize)
        self.assertIn("--protected-output capture/original", self.authorize)
        self.assertIn("--root-delegation delegation", self.authorize)
        for job in (self.delegate, self.capture, self.authorize):
            self.assertIn("overwrite: false", job)
            self.assertIn("if-no-files-found: error", job)
            self.assertIn("include-hidden-files: true", job)

    def test_full_authorization_dispatch_is_distinct_and_requires_all_three_uploads(self):
        caller = WORKFLOW.with_name("ci.yml").read_text(encoding="utf-8")
        child = workflow_job(caller, "runtime-library-authorizations")
        self.assertIn("inputs.purpose == 'runtime-library-authorizations'", child)
        self.assertIn("runtime-library-authorizations.yml@reuse-authority", child)
        self.assertIn("validation-only: false", child)
        self.assertIn("!inputs.validation-only && github.event.inputs.purpose == 'runtime-library-authorizations'",
                      self.delegate)
        gate = workflow_job(caller, "merge-gate")
        self.assertIn("'Runtime library authorizations / complete'", gate)
        script = textwrap.dedent(gate.split("        run: |\n", 1)[1])
        results = {name: "skipped" for name in re.findall(r"\b([A-Z_]+_RESULT):", gate)}
        env = {**os.environ, **results, "EVENT": "workflow_dispatch",
               "PURPOSE": "runtime-library-authorizations", "RUNTIME_LIBRARY_RESULT": "success"}
        uploads = ("RUNTIME_LIBRARY_ROOT", "RUNTIME_LIBRARY_CAPTURE", "RUNTIME_LIBRARY")
        env.update({prefix + suffix: value for prefix in uploads
                    for suffix, value in (("_ID", "123"), ("_SHA256", "sha256:" + "a" * 64))})
        cases = [{}, {"RUNTIME_LIBRARY_RESULT": "failure"}, {"EVENT": "pull_request"},
                 {"PURPOSE": "sdk-runtime-library-validation"},
                 *({name: "success"} for name in results if name != "RUNTIME_LIBRARY_RESULT"),
                 *({prefix + suffix: ""} for prefix in uploads for suffix in ("_ID", "_SHA256"))]
        for change in cases:
            with self.subTest(change=change):
                result = subprocess.run(["bash", "-e", "-c", script], env={**env, **change},
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(0 if not change else 1, result.returncode, result.stderr)

    def test_substituted_plan_zip_fails_approved_digest_before_extraction(self):
        with tempfile.TemporaryDirectory(prefix="runtime-library-plan-zip-") as temporary:
            root = Path(temporary)
            original = root / "original.zip"
            substitute = root / "substitute.zip"
            with zipfile.ZipFile(original, "w") as archive:
                archive.writestr("impact-plan.json", b"approved")
            with zipfile.ZipFile(substitute, "w") as archive:
                archive.writestr("impact-plan.json", b"replaced")
            self.assertEqual(original.stat().st_size, substitute.stat().st_size)
            digest = sha256_file(original)
            artifact_id, run_id = 17, 23
            commit, tree = "a" * 40, "b" * 40
            name = f"codex-agent-ci-plan-{tree}"
            url = f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/{artifact_id}"
            detail = {"id": artifact_id, "digest": digest, "expired": False,
                      "name": name, "archive_download_url": url + "/zip",
                      "workflow_run": {"id": run_id, "head_sha": commit},
                      "size_in_bytes": original.stat().st_size}
            with patch.object(product_reuse, "api_json", return_value=detail), \
                    patch.object(product_reuse, "download_artifact_to_file",
                                 side_effect=lambda _artifact, _token, destination, **_kwargs:
                                 destination.write_bytes(substitute.read_bytes())):
                with self.assertRaisesRegex(ValueError, "bytes differ"):
                    product_reuse._download_contract_ci_upload(
                        artifact_id, digest, name, {"runId": run_id},
                        {"head_sha": commit}, "test-observation-token",
                        destination=root / "downloaded.zip", max_bytes=1024 * 1024)

    def test_original_plan_binds_trigger_head_and_tested_merge_separately(self):
        script = textwrap.dedent(self.capture.split(
            'python3 -B - "$RUNNER_TEMP/runtime-original-plan.zip" <<\'PY\'\n', 1)[1].split(
                '          PY\n', 1)[0])
        head, merge, tree, base = ('a' * 40, 'b' * 40, 'c' * 40, 'd' * 40)
        run = {'id': 23, 'run_attempt': 1, 'event': 'pull_request', 'head_sha': head,
               'pull_requests': [{'number': 31, 'base': {'sha': base}, 'head': {'sha': 'e' * 40}}]}
        commit = {'sha': merge, 'tree': {'sha': tree}, 'parents': [{'sha': base}, {'sha': head}]}
        for fault in (None, 'run-attempt', 'artifact-head', 'merge-parent'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary, chdir(temporary):
                original = Path(temporary) / 'original.zip'
                with zipfile.ZipFile(original, 'w') as archive:
                    archive.writestr('impact-plan.json', b'approved plan bytes')
                url = 'https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/17'
                detail = {'id': 17, 'digest': sha256_file(original), 'expired': False,
                    'name': 'codex-agent-ci-plan-' + tree, 'archive_download_url': url + '/zip',
                    'workflow_run': {'id': 23, 'head_sha': head}, 'size_in_bytes': original.stat().st_size}
                observed, tested = deepcopy(run), deepcopy(commit)
                if fault == 'run-attempt': observed['run_attempt'] = 2
                if fault == 'artifact-head': detail['workflow_run']['head_sha'] = merge
                if fault == 'merge-parent': tested['parents'][1]['sha'] = merge
                def api(address, _token):
                    if address.endswith('/runs/23/attempts/1'): return observed
                    if address.endswith('/git/commits/' + merge): return tested
                    self.assertEqual(url, address)
                    return detail
                environment = {'PLAN_ID': '17', 'PLAN_SHA256': detail['digest'], 'ORIGINAL_RUN_ID': '23',
                    'ORIGINAL_RUN_ATTEMPT': '1', 'VALIDATION_COMMIT': merge, 'VALIDATION_TREE': tree,
                    'GITHUB_TOKEN': 'fixture-observation-token'}
                with patch.dict(os.environ, environment), patch.object(sys, 'argv', ['-', 'downloaded.zip']), \
                        patch.dict(sys.modules, {'product_reuse': product_reuse}), \
                        patch.object(product_reuse, 'api_json', side_effect=api), \
                        patch.object(product_reuse, 'download_artifact_to_file', side_effect=lambda _a, _t, destination, **_k:
                            destination.write_bytes(original.read_bytes())) as download:
                    if fault:
                        with self.assertRaises(ValueError): exec(compile(script, str(WORKFLOW), 'exec'), {})
                        download.assert_not_called()
                        self.assertFalse(Path('plan').exists())
                    else:
                        exec(compile(script, str(WORKFLOW), 'exec'), {})
                        download.assert_called_once()
                        self.assertEqual(b'approved plan bytes', Path('plan/impact-plan.json').read_bytes())


if __name__ == "__main__":
    unittest.main()
