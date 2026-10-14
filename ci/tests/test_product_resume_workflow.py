"""Workflow source/control checks, not genuine product or hosted acceptance."""

import os
import json
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest
from unittest import mock

from ci.tests.test_contract_attestation_workflow import workflow_job


ROOT = Path(__file__).resolve().parents[2]


class ProductResumeWorkflowTest(unittest.TestCase):
    def test_parallel_recovery_checks_run_every_module_and_propagate_any_failure(self):
        job = workflow_job(self.workflow, 'recovery-controls')
        step = job.split('      - name: Verify reviewed recovery controls only\n', 1)[1].split('\n      - ', 1)[0]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1])
        modules = re.findall(r'ci\.tests\.[a-z_]+', script)
        preserved = ('runtime_recovery_acceptance runtime_workflow prepare_runtime_signing_action '
                     'runtime_preparation_capture runtime_prepared_release runtime_aggregate_original_ci '
                     'runtime_native_attestation_workflow runtime_aggregate_attestation_workflow '
                     'tooling_capture tooling_discovery sdk_prerequisite_reuse sdk_transport_capture '
                     'sdk_ios_binary_worker_wiring sdk_ios_binary_inputs sdk_ios_binary_execution '
                     'reference_archive_download runtime_reference_transport runtime_signing_workflow_isolation '
                     'product_selection').split()
        self.assertLessEqual({'ci.tests.test_' + name for name in preserved}, set(modules))
        self.assertEqual(len(modules), len(set(modules)))
        self.assertIn('xargs -0 -n 1 -P 4 python3 -B -m unittest -v', script)
        for failed in ('', modules[0], modules[-1]):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                records = root / 'records'
                records.mkdir()
                python = root / 'python3'
                python.write_text('#!/bin/sh\nfor module do :; done\n'
                                  'printf "%s\\n" "$@" >> "$RECORDS/$module"\n'
                                  '[ "$module" != "$FAIL_MODULE" ]\n')
                python.chmod(0o700)
                result = subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                    env={**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                         'RECORDS': str(records), 'FAIL_MODULE': failed})
                self.assertEqual(not failed, result.returncode == 0, result.stderr)
                self.assertEqual(set(modules), {path.name for path in records.iterdir()})
                for module in modules:
                    self.assertEqual(['-B', '-m', 'unittest', '-v', module],
                                     (records / module).read_text().splitlines())

    def test_recovery_checks_start_independently_and_gate_the_exact_same_publication(self):
        checks = workflow_job(self.workflow, 'recovery-controls')
        self.assertNotRegex(checks, r'(?m)^    needs:')
        self.assertNotIn('needs.plan.', checks)
        self.assertIn('resolve-product-publication@reuse-authority', checks)
        self.assertIn('native-workflow-sha: ${{ fromJSON(toJSON(job)).workflow_sha }}', checks)
        self.assertIn('ref: ${{ steps.publication.outputs.source-sha }}', checks)
        lint = workflow_job(self.workflow, 'workflow-lint')
        self.assertIn('needs: [plan, recovery-controls]', lint)
        gate = lint.split('      - name: Require the same protected publication', 1)[1].split('\n      - ', 1)[0]
        script = textwrap.dedent(gate.split('        run: |\n', 1)[1])
        good = dict(PLAN_RESULT='success', CHECKS_RESULT='success', PLAN_SOURCE='a' * 40,
                    CHECKS_SOURCE='a' * 40, PLAN_PUBLISHER='b' * 40, CHECKS_PUBLISHER='b' * 40)
        cases = ({}, {'PLAN_RESULT': 'failure'}, {'CHECKS_RESULT': 'skipped'},
                 {'CHECKS_SOURCE': 'c' * 40}, {'CHECKS_PUBLISHER': 'c' * 40},
                 {'PLAN_SOURCE': '', 'CHECKS_SOURCE': ''})
        for changes in cases:
            with self.subTest(changes=changes):
                result = subprocess.run(['bash', '-c', script], env={**os.environ, **good, **changes},
                                        capture_output=True, text=True)
                self.assertEqual(not changes, result.returncode == 0, result.stderr)
        for step in lint.split('      - ')[1:]:
            if 'name: Require the same protected publication' in step or 'id: acceptance-kind' in step:
                continue
            self.assertIn('!inputs.runtimeRecoveryOnly && !inputs.sdkRecoveryOnly', step)
        plan = workflow_job(self.workflow, 'plan')
        self.assertIn('--native-resume-handoff build/native-product-resume-transport', plan)
        self.assertIn("if: steps.product-reuse.outputs.native_resume_ready == 'true'", plan)
        self.assertIn('name: codex-agent-planned-product-resume-', plan)
        resume = workflow_job(self.workflow, 'product-resume')
        for label in ('id: tooling', 'id: apple-policy', 'id: resume'):
            step = next(part for part in resume.split('      - ') if label in part)
            self.assertIn("needs.plan.outputs.native_resume_ready != 'true'", step)
        self.assertIn('capture_planned_native_resume', resume)
        self.assertIn('name: codex-agent-product-resume-', resume)
        self.assertIn("test \"$RUNTIME_WORKERS_REQUIRED\" = false", resume)
        self.assertIn('mode: bind', resume)

    def test_sdk_reference_routing_carries_only_the_planned_locator_without_provisioning_again(self):
        from ci.tests.test_product_routing import ProductRoutingTest
        from products.inventory import canonical_json_bytes
        fixture = ProductRoutingTest()
        fixture.setUp()
        source = dict(artifactId=701, artifactSha256='sha256:' + 'a' * 64,
                      workflowSha='b' * 40, producer=fixture.producer)
        plan = workflow_job(self.workflow, 'plan')
        export = plan.split('      - id: retained-sdk-inputs\n', 1)[1].split('      - id:', 1)[0]
        self.assertIn("if: steps.product-reuse.outputs.native_contract_complete == 'true'", export)
        export_script = textwrap.dedent(export.split("python3 -B - <<'PY'\n", 1)[1].split('\n          PY', 1)[0])
        job = workflow_job(self.workflow, 'sdk-inputs')
        self.assertIn("SDK_REFERENCE_SOURCE: ${{ inputs.sdkRecoveryOnly && fromJSON(needs.runtime-continuation.outputs.sdk_input_selection).source == 'current-runtime' && needs.plan.outputs.retained_sdk_inputs_source || '' }}", job)
        self.assertIn("restore-reuse-qualification@reuse-authority\n        if: env.SDK_REFERENCE_SOURCE == ''", job)
        carry = job.split('      - name: Carry the planned original locator', 1)[1].split('      - name:', 1)[0]
        self.assertIn("if: env.SDK_REFERENCE_SOURCE != ''", carry)
        carry_script = textwrap.dedent(carry.split("python3 -B - <<'PYTHON'\n", 1)[1].split('\n          PYTHON', 1)[0])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original, outputs, envfile = (root / name for name in ('original.json', 'outputs', 'env'))
            original.write_bytes(canonical_json_bytes(source))
            environment = dict(CODEX_AGENT_RETAINED_SDK_INPUTS_SOURCE=str(original),
                               GITHUB_OUTPUT=str(outputs), GITHUB_ENV=str(envfile), RUNNER_TEMP=str(root))
            with mock.patch.dict(os.environ, environment):
                exec(compile(export_script, '<planned-sdk-source>', 'exec'), {})
                encoded = outputs.read_text().strip().removeprefix('source=')
                self.assertEqual(source, json.loads(encoded))
                with mock.patch.dict(os.environ, SDK_REFERENCE_SOURCE=encoded):
                    exec(compile(carry_script, '<sdk-reference-source>', 'exec'), {})
                    retained = Path(envfile.read_text().strip().split('=', 1)[1])
                    self.assertEqual(original.read_bytes(), retained.read_bytes())
                    with self.assertRaises(FileExistsError):
                        exec(compile(carry_script, '<sdk-reference-source>', 'exec'), {})
                outputs.unlink()
                with mock.patch.dict(os.environ, CODEX_AGENT_RETAINED_SDK_INPUTS_SOURCE=''):
                    exec(compile(export_script, '<missing-source>', 'exec'), {})
                self.assertFalse(outputs.exists())
                original.write_bytes(canonical_json_bytes({**source, 'artifactId': 0}))
                with self.assertRaises(ValueError):
                    exec(compile(export_script, '<invalid-source>', 'exec'), {})
                self.assertFalse(outputs.exists())
                with mock.patch.dict(os.environ, SDK_REFERENCE_SOURCE='{}'):
                    with self.assertRaises(ValueError):
                        exec(compile(carry_script, '<invalid-carried-source>', 'exec'), {})

    def test_completed_prefix_skips_jobs_but_keeps_the_original_worker_and_terminal_gate(self):
        from ci import sdk_native_continuation as routing
        from ci.tests.test_product_routing import ProductRoutingTest
        fixture = ProductRoutingTest()
        fixture.setUp()
        fixture.decisions['ready'] = [dict(product='sdk', component='sdk-ios', phase='validation',
                                          target='ios-arm64', buildKey='sha256:' + 'd' * 64)]
        bound = routing.bind(fixture.decisions, fixture.locator, fixture.expected)
        election = routing.select(bound, fixture.locator, fixture.expected, family='javascript')
        self.assertTrue(election['ios_validation_direct'])
        self.assertFalse(election['sdk_workers_required'])
        skipped = ('sdk-javascript', 'sdk-javascript-metadata-plan', 'sdk-javascript-metadata-result',
                   'sdk-csharp-binary-plan', 'sdk-csharp-binary-result', 'sdk-native-plan',
                   'sdk-native-packages', 'sdk-ios-package-plan', 'sdk-ios-packages',
                   'sdk-native-validation-plan', 'sdk-native-validation-result', 'sdk-native-metadata-plan')
        for name in skipped:
            job = workflow_job(self.workflow, name)
            header = job.split('    runs-on:', 1)[0]
            self.assertIn("needs.sdk-plan.outputs.ios_validation_direct != 'true'", header, name)
            self.assertRegex(header, r'needs: \[[^\n]*\bsdk-plan\b', name)
        native = workflow_job(self.workflow, 'sdk-native-result')
        self.assertNotIn("ios_validation_direct != 'true'", native)
        script = textwrap.dedent(native.split("python3 - <<'PY'\n", 1)[1].split('\n          PY', 1)[0])
        parents = (*routing._IOS_PREFIX_RESULTS, 'sdk-native-metadata-plan', 'sdk-native-metadata', 'sdk-collect-8')
        for name in parents:
            self.assertIn(name, native.split('    runs-on:', 1)[0])
        needs = {name: {'result': 'skipped', 'outputs': {}} for name in parents}
        planned = {**fixture.locator, 'routing': json.dumps(bound, separators=(',', ':')),
                   'ios_validation_direct': 'true', 'sdk_workers_required': 'false'}
        needs['sdk-plan'] = {'result': 'success', 'outputs': planned}
        for status in ('skipped', 'failure'):
            needs['sdk-ios-packages']['result'] = status
            with tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary) / 'outputs'
                with mock.patch.dict(os.environ, RESULTS=json.dumps(needs), GITHUB_OUTPUT=str(output)):
                    if status == 'failure':
                        with self.assertRaises(ValueError):
                            exec(compile(script, '<native-prefix-boundary>', 'exec'), {})
                        self.assertFalse(output.exists())
                    else:
                        exec(compile(script, '<native-prefix-boundary>', 'exec'), {})
                        values = dict(line.split('=', 1) for line in output.read_text().splitlines())
                        self.assertEqual(routing.forward_routing(fixture.locator, planned), values)
        for name in ('sdk-ios-validation-plan', 'sdk-ios-validation', 'sdk-collect-9'):
            job = workflow_job(self.workflow, name)
            self.assertIn("needs.sdk-native-result.result == 'success'", job)
            self.assertIn('artifact-id: ${{ needs.sdk-native-result.outputs.artifact_id }}', job)
        worker = workflow_job(self.workflow, 'sdk-ios-validation')
        self.assertIn('uses: ./.github/actions/sdk-ios-validation-worker', worker)
        self.assertIn('restore-reuse-qualification@reuse-authority', worker)
        self.assertIn('sdk_completion --plan', workflow_job(self.workflow, 'sdk-completion'))

    def test_sdk_recovery_full_parity_uses_authenticated_state_and_no_legacy_inputs(self):
        parity = workflow_job(self.workflow, "sdk-parity")
        self.assertIn("needs.sdk-completion.outputs.complete == 'true'", parity)
        self.assertIn("needs.sdk-completion.outputs.phase_count == '62'", parity)
        self.assertIn("importedOnly: ${{ inputs.sdkRecoveryOnly }}", parity)
        imported = (ROOT / ".github/workflows/sdk-binding-parity.yml").read_text()
        self.assertIn("python3 -B -m ci.sdk_workflow parity", imported)
        self.assertIn("uses: ./.github/actions/capture-runtime-state", imported)
        self.assertIn("sdk-validation-tooling: ${{ steps.tooling.outputs.tooling-policy }}", imported)
        self.assertIn("sdk-apple-validation-policy: ${{ steps.apple-policy.outputs.apple-policy }}", imported)
        for name in ("Require complete six-language M8 binding parity", "Stage exact SDK parity evidence"):
            self.assertIn("- name: " + name + "\n        if: ${{ !inputs.importedOnly }}", imported)
        self.assertIn("if: inputs.nativeWrappers && !inputs.importedOnly", imported)
        # A genuine changed auxiliary helper can build through the existing
        # tooling-only route; Contract product ownership must remain complete.
        guard = self.workflow.split("- name: Require unchanged Contract ownership before SDK continuation", 1)[1].split("      - id:", 1)[0]
        self.assertIn('test "$CONTRACT_NEXT_PHASE" = none', guard)
        self.assertNotIn("TOOLING_MISS", guard)
        contract = (ROOT / ".github/workflows/contract-validation.yml").read_text()
        self.assertIn("contract-tooling-only: ${{ fromJSON(inputs.planOutputs).tooling_miss == 'true' && fromJSON(inputs.planOutputs).contract_next_phase != 'binary' }}", contract)

    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text(encoding="utf-8")
        cls.job = workflow_job(cls.workflow, "product-resume")
        cls.gate = workflow_job(cls.workflow, "merge-gate")

    def test_lint_compiler_heap_is_scoped_to_fixture_provisioning_and_build_logic(self):
        lint = workflow_job(self.workflow, "workflow-lint")
        standalone = lint.split("      - name: Verify standalone build logic", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("./gradlew -p gradle/build-logic test", standalone)
        self.assertIn("-Pkotlin.daemon.jvmargs=-Xmx2g", standalone)
        self.assertEqual(2, self.workflow.count("-Pkotlin.daemon.jvmargs=-Xmx2g"))
        self.assertEqual(2, lint.count("-Pkotlin.daemon.jvmargs=-Xmx2g"))
        self.assertIn("./gradlew help -Pkotlin.daemon.jvmargs=-Xmx2g", lint)
        self.assertIn("--configuration-cache --configuration-cache-problems=fail --no-build-cache", standalone)
        self.assertIn("python3 -m unittest discover -s ci/tests -v", lint)
        self.assertNotRegex(standalone, r"ciProductPhase|verifyRepository|verifyRuntime|verifySdk")

    def test_authorization_and_complete_upstreams_are_required_before_runner(self):
        condition = re.search(r"^    if: (?P<body>.*?)(?=^    [a-z][a-z-]*:)",
                              self.job, re.MULTILINE | re.DOTALL)
        self.assertIsNotNone(condition)
        for guard in (
            "needs.plan.outputs.event_authorized == 'true'",
            "needs.plan.outputs.remote_build_authorized == 'true'",
            "needs.plan.outputs.validation_reused != 'true'",
            "github.event_name != 'workflow_dispatch'",
            "needs.contract-validation.outputs.contract_complete == 'true'",
            "needs.contract-validation.outputs.contract_continuation_result == 'success'",
            "needs.contract-validation.outputs.contract_attestation_result == 'success'",
        ):
            self.assertIn(guard, condition.group("body"))
        self.assertLess(condition.start(), self.job.index("    runs-on:"))
        needs = re.search(r"^    needs: \[(.*?)\]$", self.job, re.MULTILINE)
        self.assertIsNotNone(needs)
        self.assertEqual({"plan", "contract-validation"},
                         {value.strip() for value in needs.group(1).split(",")})

    def test_native_contract_route_uses_approved_policy_and_keeps_completion_required(self):
        plan = workflow_job(self.workflow, 'plan')
        self.assertIn('restore-reuse-qualification@reuse-authority', plan)
        self.assertIn('completion=(--completed-frozen-policy "$CODEX_AGENT_COMPLETED_REUSE_POLICY")', plan)
        self.assertIn("needs.plan.outputs.native_contract_complete == 'true' ||", self.job)
        self.assertIn("if: needs.plan.outputs.native_contract_complete != 'true'", self.job)
        self.assertIn('tooling+=(--native-contract-plan build/product-resume-plan/impact-plan.json', self.job)
        self.assertIn('--native-contract-plan-artifact-id "$PLAN_ARTIFACT_ID"', self.job)
        self.assertIn('plan-path: ${{ github.workspace }}/build/product-resume-plan/impact-plan.json', self.job)
        self.assertIn('if [ "$CONTRACT_COMPLETE" = true ] || [ "$NATIVE_CONTRACT_COMPLETE" = true ]; then', self.gate)
        self.assertIn('test "$PRODUCT_RESUME_RESULT" = success', self.gate)
        self.assertIn('test "$SDK_COMPLETE" = true || exit 1', self.gate)

    def test_tooling_refresh_receives_source_inventories_not_plan_only_control(self):
        child = (ROOT / '.github/workflows/contract-validation.yml').read_text()
        signer = workflow_job(child, 'tooling-attestation')
        download = signer.split('      - name: Download original plan and source inventories', 1)[1].split('      - name:', 1)[0]
        self.assertIn('artifact-ids: ${{ fromJSON(inputs.planOutputs).plan_id }}', download)
        self.assertNotIn('plan_control_id', download)

    def test_validation_precheck_only_skips_absent_uploads_and_keeps_full_admission(self):
        step = self.workflow.split('      - id: validation-reuse\n', 1)[1].split('\n      - ', 1)[0]
        script = textwrap.dedent(step.split("python3 - <<'PY'\n", 1)[1].rsplit('\n          PY', 1)[0])
        name = 'codex-agent-ci-validation-' + 'a' * 40
        for artifacts in ([], [{'name': name, 'expired': True}], [{'name': 'other', 'expired': False}],
                          [{'name': name, 'expired': False}], OSError('offline')):
            with self.subTest(artifacts=artifacts), tempfile.TemporaryDirectory() as scratch:
                output = Path(scratch) / 'output'
                with mock.patch.dict(os.environ, GITHUB_API_URL='https://api.invalid', GITHUB_TOKEN='test', GITHUB_OUTPUT=str(output)), \
                        mock.patch('pathlib.Path.read_text', return_value='{"repository":"owner/repo","validationTree":"' + 'a' * 40 + '"}'), \
                        mock.patch('reuse.paginated_items', **({'side_effect': artifacts} if isinstance(artifacts, Exception) else {'return_value': artifacts})) as listing, \
                        mock.patch('subprocess.run') as discover:
                    exec(compile(script, '<validation-precheck>', 'exec'), {})
                listing.assert_called_once_with('https://api.invalid/repos/owner/repo/actions/artifacts?name=' + name, 'artifacts', 'test')
                if artifacts == [{'name': name, 'expired': False}]:
                    self.assertEqual(['ci/validation_reuse.py', 'discover'], discover.call_args.args[0][1:3])
                    self.assertTrue(discover.call_args.kwargs['check'])
                    self.assertFalse(output.exists())
                else:
                    discover.assert_not_called()
                    self.assertEqual('reused=false\n', output.read_text())

    def test_exact_original_uploads_are_authenticated_before_resuming(self):
        downloads = re.findall(r"uses: actions/download-artifact@.*?(?=^      -|\Z)",
                               self.job, re.MULTILINE | re.DOTALL)
        self.assertEqual(1, len(downloads))
        self.assertIn("artifact-ids: ${{ needs.plan.outputs.plan_control_id }}", downloads[0])
        self.assertIn("path: build/product-resume-plan", downloads[0])
        self.assertNotRegex(downloads[0], re.compile(r"^          (?:name|pattern):", re.MULTILINE))
        for reference in (
            "needs.plan.outputs.plan_id", "needs.plan.outputs.plan_digest",
            "needs.contract-validation.outputs.contract_state_id",
            "needs.contract-validation.outputs.contract_state_digest",
            "needs.contract-validation.outputs.contract_attestation_artifact_id",
            "needs.contract-validation.outputs.contract_attestation_artifact_digest",
            "needs.plan.outputs.publisher_sha",
        ):
            self.assertIn(reference, self.job)
        for flag in ("--plan-artifact-id", "--plan-artifact-sha256", "--state-artifact-id", "--state-artifact-sha256",
                     "--release-artifact-id", "--release-artifact-sha256", "--trusted-workflow-sha"):
            self.assertIn(flag, self.job)
        self.assertEqual(1, self.job.count("ci/product_reuse.py capture-product-resume-inputs"))
        for flag in ("--state-control-id", "--state-control-sha256", "--release-control-id", "--release-control-sha256"):
            self.assertIn(flag, self.job)
        self.assertIn('test -n "${CODEX_AGENT_COMPLETED_REUSE_POLICY:-}"', self.job)
        self.assertIn("--trusted-contract-workflow-path .github/workflows/contract-validation.yml", self.job)
        self.assertIn('--trusted-contract-continuation-job "product-validation / contract-validation / contract-continuation"', self.job)
        self.assertEqual(1, self.job.count("ci/product_reuse.py resume-products"))
        self.assertLess(self.job.index("capture-product-resume-inputs"), self.job.index("resume-products"))
        for flag, path in (
            ("--plan", "build/product-resume-inputs/plan/impact-plan.json"),
            ("--discovery-root", "build/product-resume-inputs/plan/product-reuse"),
            ("--state-root", "build/product-resume-inputs/state"),
            ("--contract-handoff", "build/product-resume-inputs/release/contract-input"),
            ("--destination", "build/product-resume-state"),
        ):
            self.assertRegex(self.job, re.escape(flag) + r"\s+[\"']?" + re.escape(path) + r"(?:[\"']|\s|$)")

    def test_resume_has_no_new_discovery_signing_or_product_execution(self):
        self.assertEqual(["REUSE_AUTHORITY_READ_TOKEN"], re.findall(r"secrets\.([A-Z_]+)", self.job))
        self.assertIn("authority-read-token: ${{ secrets.REUSE_AUTHORITY_READ_TOKEN }}", self.job)
        self.assertNotIn("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", self.job)
        self.assertNotIn("ci/contract_release.py", self.job)
        self.assertNotIn("ssh-keygen", self.job)
        self.assertNotRegex(self.job, r"ci/product_reuse\.py\s+(?:discover|advance-products|advance-contract)\b")
        self.assertNotRegex(self.job, r"uses: (?:actions/cache(?:/|@)|actions/setup-)")
        self.assertEqual(["./.github/actions/capture-sdk-tooling", "./.github/actions/prepare-sdk-apple-policy",
                          "./.github/actions/hydrated-evidence-cache", "./.github/actions/capture-runtime-state/route"],
                         re.findall(r"uses: (\./\S+)", self.job))
        self.assertLess(self.job.index("uses: ./.github/actions/capture-sdk-tooling"),
                        self.job.index("ci/product_reuse.py resume-products"))
        self.assertNotRegex(self.job, r"(?:\./gradlew|\bcargo\s+(?:build|test)|\bcmake\s|\bxcodebuild\b|\bnpm\s+(?:ci|install|run)|\bpip\s+install)")

    def test_apple_policy_comes_from_original_plan_before_authenticated_resume(self):
        policy = self.job.split("      - id: apple-policy\n", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("if: needs.plan.outputs.native_resume_ready != 'true' && needs.plan.outputs.tooling_required == 'true'", policy)
        self.assertIn("plan-path: ${{ github.workspace }}/build/product-resume-plan/impact-plan.json", policy)
        self.assertIn("tooling-policy: ${{ steps.tooling.outputs.tooling-policy }}", policy)
        self.assertLess(self.job.index("capture-product-resume-inputs"), self.job.index("      - id: apple-policy"))
        self.assertLess(self.job.index("      - id: apple-policy"), self.job.index(" resume-products"))
        step = self.job.split("      - name: Resume the existing product planner from authenticated Contract bytes", 1)[1].split("\n      - ", 1)[0]
        self.assertIn("SDK_APPLE_VALIDATION_POLICY: ${{ steps.apple-policy.outputs.apple-policy }}", step)
        self.assertIn('tooling+=(--sdk-apple-validation-policy "$SDK_APPLE_VALIDATION_POLICY")', step)

    def test_reference_handoff_for_original_inputs_and_state_is_uploaded_immutably(self):
        uploads = re.findall(r"uses: actions/upload-artifact@.*?(?=^      -|\Z)",
                             self.job, re.MULTILINE | re.DOTALL)
        self.assertEqual(1, len(uploads))
        for value in ("overwrite: false", "if-no-files-found: error", "include-hidden-files: true",
                      "path: build/product-resume-transport"):
            self.assertIn(value, uploads[0])
        self.assertIn("--handoff build/product-resume-transport", self.job)
        self.assertNotIn("release/contract-input", uploads[0])
        header = self.job.split("    steps:", 1)[0]
        for name in ("artifact_id:", "artifact_digest:", "full_reuse:", "target_jobs_required:"):
            self.assertIn(name, header)
        self.assertIn(".outputs.artifact-id", header)
        self.assertIn(".outputs.artifact-digest", header)
        self.assertIn("sha256:", header)
        self.assertIn(".outputs.full_reuse", header)
        self.assertIn(".outputs.target_jobs_required", header)
        child = (ROOT / ".github/workflows/contract-validation.yml").read_text(encoding="utf-8")
        for source, job_name, output_name, step_name in (
            (self.workflow, "plan", "plan", "upload_plan"),
            (child, "contract-continuation", "state", "upload_final_state"),
        ):
            job = workflow_job(source, job_name)
            self.assertIn(f"{output_name}_id: ${{{{ steps.{step_name}.outputs.artifact-id }}}}", job)
            self.assertIn(f"{output_name}_digest: sha256:${{{{ steps.{step_name}.outputs.artifact-digest }}}}", job)

    def test_actual_merge_guard_rejects_missing_required_resume_output(self):
        needs = re.search(r"^    needs: \[(.*?)\]$", self.gate, re.MULTILINE)
        self.assertIsNotNone(needs)
        self.assertIn("product-resume", {value.strip() for value in needs.group(1).split(",")})
        first = re.split(r"(?=^      - )", self.gate, flags=re.MULTILINE)[1]
        for value in ("needs.product-resume.result", "needs.product-resume.outputs.artifact_id",
                      "needs.product-resume.outputs.artifact_digest"):
            self.assertIn(value, first)
        script_match = re.search(r"^        run: \|\n(?P<body>(?:^          .*\n|^\n)+)", first, re.MULTILINE)
        self.assertIsNotNone(script_match)
        script = "\n".join(line[10:] if line.startswith(" " * 10) else line
                           for line in script_match.group("body").splitlines())
        base = {
            "EVENT_AUTHORIZED": "true", "MERGE_READY": "true", "REMOTE_BUILD_AUTHORIZED": "true",
            "REMOTE_BUILD_AUTHORIZATION_REASON": "pull-request-final", "RESULTS": "success success",
            "CONTRACT_COMPLETE": "true", "CONTRACT_ATTESTATION_RESULT": "success",
            "CONTRACT_ATTESTATION_ARTIFACT_ID": "700", "CONTRACT_ATTESTATION_ARTIFACT_DIGEST": "sha256:" + "a" * 64,
            "PRODUCT_RESUME_RESULT": "success", "PRODUCT_RESUME_ARTIFACT_ID": "701",
            "SDK_COMPLETION_RESULT": "success", "SDK_COMPLETE": "true",
            "SDK_CATALOG_REQUIRED": "false", "SDK_CATALOG_RESULT": "skipped",
            "PRODUCT_RESUME_ARTIFACT_DIGEST": "sha256:" + "b" * 64,
            "PRODUCT_FULL_REUSE": "true", "RUNTIME_WAVE_FAILED": "false false false false",
        }
        cases = [({}, True), ({"CONTRACT_COMPLETE": "false", "PRODUCT_RESUME_RESULT": "skipped",
                               "PRODUCT_RESUME_ARTIFACT_ID": "", "PRODUCT_RESUME_ARTIFACT_DIGEST": ""}, True)]
        cases.extend(({"PRODUCT_RESUME_RESULT": value}, False) for value in ("failure", "cancelled", "skipped", ""))
        cases.extend(({field: ""}, False) for field in ("PRODUCT_RESUME_ARTIFACT_ID", "PRODUCT_RESUME_ARTIFACT_DIGEST"))
        cases.append(({"PRODUCT_RESUME_ARTIFACT_DIGEST": "not-a-digest"}, False))
        cases.extend(({"PRODUCT_FULL_REUSE": value}, False) for value in ("false", ""))
        cases.append(({"RUNTIME_WAVE_FAILED": "false true false false"}, False))
        for change, expected in cases:
            with self.subTest(change=change):
                result = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script],
                                        env={"PATH": os.environ.get("PATH", ""), **base, **change},
                                        capture_output=True, text=True)
                self.assertEqual(expected, result.returncode == 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
