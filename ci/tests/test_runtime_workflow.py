"""Workflow composition checks; mocked gates are not product/host admission.

The retained byte trees are real. Planner, transport and execution assertions
below only verify delegation to their existing separately tested authorities.
"""

from pathlib import Path
from copy import deepcopy
import json
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_workflow as workflow
from products.inventory import regular_file_inventory


KEY = "sha256:" + "a" * 64
PIN = "b" * 40
NODE = workflow.PhaseInstanceId("runtime", "node-js", "validation", "node-js-binding")
JVM = workflow.PhaseInstanceId("runtime", "jvm", "binary", "jvm")
SUPERVISOR = workflow.PhaseInstanceId("runtime", "linux-arm64", "binary", "linux-arm64")
AGGREGATE = workflow.PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")


def row(instance, **extra):
    return {**workflow.products._identity_record(instance), "buildKey": KEY, **extra}


class RuntimeWorkflowTest(unittest.TestCase):
    def test_variant_trust_cli_preserves_explicit_paths_and_rejects_duplicate_targets(self):
        arguments = ["variant-trust", "--destination", "output", "--keyring", "policy.json",
                     "--keys-directory", "keys"]
        handoffs = {target: Path(f"original/{target}/runtime-input") for target in workflow.NATIVE_TARGETS}
        selected = [value for target, path in handoffs.items()
                    for value in ("--variant-handoff", f"{target}={path}")]
        with mock.patch("products.runtime_variant_trust.stage_runtime_variant_trust") as stage:
            self.assertEqual(0, workflow.main([*arguments, *selected]))
            stage.assert_called_once_with(handoffs, Path("output"), keyring=Path("policy.json"),
                                          keys_directory=Path("keys"))
        for invalid in (selected[1], "unknown=path", "macos-arm64=", "macos-arm64"):
            with self.subTest(invalid=invalid), \
                    mock.patch("products.runtime_variant_trust.stage_runtime_variant_trust") as stage:
                with self.assertRaises(SystemExit):
                    workflow.main([*arguments, *selected, "--variant-handoff", invalid])
                stage.assert_not_called()

    def test_fixed_workflow_collects_all_four_waves_before_final_failure(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / '.github/workflows/product-validation.yml').read_text()
        for wave in range(1, 5):
            worker = source.split(f'  runtime-workers-{wave}:\n', 1)[1].split(f'  runtime-collect-{wave}:\n', 1)[0]
            collector = source.split(f'  runtime-collect-{wave}:\n', 1)[1].split('\n\n', 1)[0]
            self.assertIn('always()', collector)
            dependencies = collector.split('needs: [', 1)[1].split(']', 1)[0].split(', ')
            self.assertIn(f'runtime-workers-{wave}', dependencies)
            self.assertNotIn(f"needs.runtime-workers-{wave}.result == 'success'", collector)
            self.assertIn(f"wave: '{wave}'", collector)
            self.assertIn('fail-fast: false', worker)
            self.assertIn("GIT_CONFIG_KEY_0: core.autocrlf", worker)
            self.assertIn("GIT_CONFIG_VALUE_0: 'false'", worker)
            self.assertIn("remote_build_authorized == 'true'", worker)
            self.assertIn("runtime_workers_required == 'true'", worker)
            self.assertIn("outputs.wave_failed != 'true'", worker)
            self.assertIn('name: runtime-${{ matrix.component }}-${{ matrix.phase }}-${{ matrix.target }}', worker)
            self.assertIn('path: build/runtime-worker', worker)
            self.assertIn('if: always()', worker)
            self.assertIn(f"state-wave: '{wave - 1}'", worker)
            self.assertNotIn('continue-on-error:', worker)
        gate = source.split('  merge-gate:\n', 1)[1]
        self.assertIn('"$PRODUCT_FULL_REUSE" != true', gate)
        self.assertIn('"$RUNTIME_WAVE_FAILED" = *true*', gate)
        for wave in range(1, 5):
            self.assertIn(f'runtime-workers-{wave}, runtime-collect-{wave}', gate)
        action = (root / '.github/actions/run-runtime-product-phase/action.yml').read_text()
        self.assertLess(action.index('./.github/actions/capture-runtime-state'), action.index('./.github/actions/setup-kmp'))
        self.assertLess(action.index('./.github/actions/capture-runtime-state'), action.index('./.github/actions/setup-msvc'))
        collected = (root / '.github/actions/collect-runtime-wave/action.yml').read_text()
        self.assertIn('runtime_workflow.py export-references', collected)
        self.assertIn("path: ${{ inputs.product == 'runtime' && (inputs.wave == '1' || inputs.wave == '2' || inputs.wave == '3') && 'build/runtime-reference-handoff' || 'build/runtime-next/handoff' }}", collected)
        self.assertIn('build/runtime-next/collection', collected)
        self.assertIn('if: ${{ failure() }}', collected)
        self.assertNotIn('${{ failure() &&', collected)
        self.assertNotIn('overwrite: true', collected)

    def test_sdk_input_job_is_selected_guarded_build_free_and_required_by_gate(self):
        source = (Path(__file__).resolve().parents[2] / '.github/workflows/product-validation.yml').read_text()
        job = source.split('  sdk-inputs:\n', 1)[1].split('  android:\n', 1)[0]
        for guard in ("event_authorized == 'true'", "remote_build_authorized == 'true'",
                      "sdk_handoff_required == 'true'", "runtime-continuation.result == 'success'"):
            self.assertIn(guard, job)
        self.assertIn("source == 'released-default'", job)
        self.assertIn("runtime-aggregate-attestation.result == 'success'", job)
        self.assertIn('./.github/actions/capture-runtime-state', job)
        self.assertIn('python3 -B -m ci.sdk_workflow', job)
        self.assertIn('--expected-metadata-receipt-sha256 "$AGGREGATE_RECEIPT"', job)
        self.assertIn('overwrite: false', job)
        self.assertIn('artifact_digest: sha256:${{ steps.upload.outputs.artifact-digest }}', job)
        self.assertIn('codex-agent-sdk-inputs-${{ needs.plan.outputs.validation_tree }}-attempt-${{ github.run_attempt }}', job)
        aggregate = source.split('  runtime-aggregate-attestation:\n', 1)[1].split('  sdk-inputs:\n', 1)[0]
        self.assertIn('artifact_digest: sha256:${{ steps.upload.outputs.artifact-digest }}', aggregate)
        for forbidden in ('setup-kmp', './gradlew', 'ssh-keygen', 'environment: product-attestation'):
            self.assertNotIn(forbidden, job)
        gate = source.split('  merge-gate:\n', 1)[1]
        dependencies = gate.split('needs: [', 1)[1].split(']', 1)[0].split(', ')
        for required in ('runtime-aggregate-attestation', 'sdk-inputs', 'android'):
            self.assertIn(required, dependencies)
        self.assertIn('if [ "$SDK_INPUTS_REQUIRED" = true ]; then', gate)
        self.assertIn('test "$SDK_INPUTS_RESULT" = success || exit 1', gate)
        self.assertIn('needs.sdk-inputs.outputs.artifact_digest', gate)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-workflow-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.input = self.root / "original"
        self.base = {
            "product-resume-inputs/plan/impact-plan.json": b"{\"original\":true}\n",
            "product-resume-inputs/release/receipt.json": b"original receipt\x00\xff\n",
            "product-resume-inputs/release/raw.log": b"",
            "product-resume-state/reuse-wave-request.json": b"original control bytes\n",
            "product-resume-state/carrier/object.zip": b"original object bytes\x00\xfe",
        }
        self.write_tree(self.input, self.base)
        self.output = self.root / "github-output"
        self.environment = {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"}

    def write_tree(self, root, members):
        for name, raw in members.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

    def outputs(self):
        return dict(line.split("=", 1) for line in self.output.read_text().splitlines())

    def captured(self, _plan, destination, **keywords):
        members = dict(self.base)
        if keywords["state_wave"]:
            members["runtime-state/phase-plans/runtime-node-js-validation-node-js-binding.json"] = b"original current plan\n"
        self.write_tree(destination / "original", members)
        self.write_tree(destination, {"capture-transport.json": b"original external transport\n"})

    def collection(self, _plan, _discovery, _state, destination, **_keywords):
        self.write_tree(destination, {"raw.log": b"", "good/shard/phase-receipt.json": b"original worker receipt\n"})
        return {"rows": [row(JVM, result="success", shardDirectory="good/shard")]}

    def advanced(self, _plan, _discovery, _state, _shards, destination, _output, **_keywords):
        self.write_tree(destination, {"reused-carrier/object.zip": b"new original Runtime object\xff",
                                      "reuse-wave-result.json": b"derived continuation control\n"})
        return {"fullReuse": False, "fixture": "actual gate is mocked"}

    def collect(self, destination, wave=1, **changes):
        return workflow.collect(self.input, destination, self.output, wave=wave,
                                trusted_workflow_sha=PIN, repository_root=self.root,
                                environ=self.environment, token="synthetic-token", **changes)

    def test_matrix_delegates_and_emits_only_the_elected_supervisor_key(self):
        value = {"include": [row(JVM), row(SUPERVISOR)]}
        paths = (self.root / "plan", self.root / "discovery", self.root / "state")
        with mock.patch.object(workflow.products, "runtime_worker_matrix", return_value=value) as gate:
            self.assertEqual(value, workflow.matrix(*paths, self.output,
                             repository_root=self.root, environ=self.environment))
        gate.assert_called_once_with(*paths, repository_root=self.root, environ=self.environment)
        self.assertEqual(KEY, self.outputs()["supervisor_key"])
        self.assertEqual("true", self.outputs()["runtime_workers_required"])
        with mock.patch.object(workflow.products, "runtime_worker_matrix", return_value={"include": []}):
            workflow.matrix(*paths, self.output)
        self.assertEqual("", self.outputs()["supervisor_key"])
        self.assertEqual("false", self.outputs()["runtime_workers_required"])
        with mock.patch.object(workflow.products, "runtime_worker_matrix", return_value={"include": [row(SUPERVISOR), row(SUPERVISOR)]}):
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                workflow.matrix(*paths, self.output)

    def final_fixture(self, state="build"):
        # Explicit replay seam: no raw dictionary below is accepted by the
        # production entrypoint; inspect_products is its sole source of state.
        phases = []
        for index, instance in enumerate(workflow.products._dependency_closure((AGGREGATE,)), 1):
            phases.append({**row(instance), "buildKey": f"sha256:{index:064x}",
                           "state": "retained", "receiptSha256": f"sha256:{index + 100:064x}",
                           "objectSha256": f"sha256:{index + 200:064x}"})
        selected = next(record for record in phases if workflow.products._identity(record) == AGGREGATE)
        selected["state"] = state
        ready = []
        if state == "build":
            selected.update(receiptSha256=None, objectSha256=None)
            ready = [{name: selected[name] for name in ("product", "component", "phase", "target", "buildKey")}]
        return {"result": {"phases": phases, "fullReuse": state == "reused"}, "readyPlans": ready}

    def final_route(self, **changes):
        return workflow.continuation(self.root / "plan", self.root / "discovery", self.root / "state",
                                     self.output, repository_root=self.root, environ=self.environment,
                                     sdk_validation_tooling={"fixture": "caller policy"}, **changes)

    def test_optional_final_route_reports_not_selected_only_after_full_replay(self):
        inspected = self.final_fixture()
        inspected["result"]["phases"] = [record for record in inspected["result"]["phases"]
                                         if workflow.products._identity(record) != AGGREGATE]
        inspected["readyPlans"] = []
        with mock.patch.object(workflow.products, "inspect_products", return_value=inspected) as inspect:
            with self.assertRaisesRegex(ValueError, "selected aggregate"):
                self.final_route()
            self.assertFalse(self.output.exists())
            result = self.final_route(if_selected=True)
        self.assertEqual(2, inspect.call_count)
        self.assertEqual({"nativeAttestationMatrix": {"include": []},
                          "aggregate": {"state": "not-selected", "buildKey": None, "receiptSha256": None}}, result)
        self.assertEqual({"native_attestation_matrix": '{"include":[]}', "aggregate_state": "not-selected",
                          "aggregate_key": "", "aggregate_receipt_sha256": "", "aggregate_required": "false",
                          "aggregate_payload_complete": "false", "sdk_handoff_required": "false",
                          "sdk_input_selection": "null"}, self.outputs())

    def test_sdk_default_handoff_routes_without_selecting_current_aggregate(self):
        selection = {"source": "released-default", "sdkVersion": "0.8.0",
                     "defaultRuntimeVersion": "0.8.0", "contractPayloadSha256": KEY}
        inspected = {"result": {"phases": []}, "readyPlans": [], "sdkInputSelection": selection}
        with mock.patch.object(workflow.products, "inspect_products", return_value=inspected):
            self.final_route(if_selected=True)
        outputs = self.outputs()
        self.assertEqual("true", outputs["sdk_handoff_required"])
        self.assertEqual(workflow.canonical_json_bytes(selection).decode().strip(), outputs["sdk_input_selection"])
        self.assertEqual("false", outputs["aggregate_required"])
        self.assertEqual('{"include":[]}', outputs["native_attestation_matrix"])

    def test_optional_final_route_does_not_bypass_invalid_replay_or_duplicate_elections(self):
        base = self.final_fixture()
        base["result"]["phases"] = [record for record in base["result"]["phases"]
                                    if workflow.products._identity(record) != AGGREGATE]
        base["readyPlans"] = []
        for mutation in ("duplicate-phase", "invalid-identity", "duplicate-plan", "orphan-aggregate-plan", "requires-completed"):
            inspected = deepcopy(base)
            options = {"if_selected": True}
            if mutation == "duplicate-phase":
                inspected["result"]["phases"].append(deepcopy(inspected["result"]["phases"][0]))
            elif mutation == "invalid-identity":
                inspected["result"]["phases"][0]["target"] = "unknown"
            elif mutation == "duplicate-plan":
                inspected["readyPlans"] = [row(JVM), row(JVM)]
            elif mutation == "orphan-aggregate-plan":
                inspected["readyPlans"] = [row(AGGREGATE)]
            else:
                options["require_completed"] = True
            with self.subTest(mutation=mutation), \
                    mock.patch.object(workflow.products, "inspect_products", return_value=inspected), self.assertRaises(ValueError):
                self.final_route(**options)
            self.assertFalse(self.output.exists())
        with mock.patch.object(workflow.products, "inspect_products", side_effect=ValueError("original replay rejected")), \
                self.assertRaisesRegex(ValueError, "original replay rejected"):
            self.final_route(if_selected=True)
        self.assertFalse(self.output.exists())
        with mock.patch.object(workflow.products, "inspect_products") as inspect, self.assertRaisesRegex(ValueError, "boolean"):
            self.final_route(if_selected="true")
        inspect.assert_not_called()

    def test_optional_final_route_keeps_selected_aggregate_predecessor_requirements(self):
        inspected = self.final_fixture()
        with mock.patch.object(workflow.products, "inspect_products", return_value=inspected):
            self.assertEqual("ready", self.final_route(if_selected=True)["aggregate"]["state"])
        inspected["result"]["phases"] = [record for record in inspected["result"]["phases"]
                                         if record["component"] != "linux-x64"]
        before = self.output.read_bytes()
        with mock.patch.object(workflow.products, "inspect_products", return_value=inspected), \
                self.assertRaisesRegex(ValueError, "incomplete original predecessor"):
            self.final_route(if_selected=True)
        self.assertEqual(before, self.output.read_bytes())

    def test_final_route_uses_replay_and_exact_five_native_keys_before_aggregate_build(self):
        inspected = self.final_fixture()
        with mock.patch.object(workflow.products, "inspect_products", return_value=inspected) as gate, \
                mock.patch.object(workflow.products, "runtime_worker_matrix", side_effect=AssertionError("empty matrix is not proof")):
            result = self.final_route()
        gate.assert_called_once_with(self.root / "plan", self.root / "discovery", self.root / "state",
                                    repository_root=self.root, environ=self.environment,
                                    sdk_validation_tooling={"fixture": "caller policy"}, include_sdk_selection=True)
        phases = {workflow.products._identity(record): record for record in inspected["result"]["phases"]}
        expected = {"include": [{"target": target,
            "buildKey": phases[workflow.PhaseInstanceId("runtime", target, "metadata", target)]["buildKey"]}
            for target in workflow.NATIVE_TARGETS]}
        self.assertEqual(expected, result["nativeAttestationMatrix"])
        self.assertEqual({"state": "ready", "buildKey": phases[AGGREGATE]["buildKey"], "receiptSha256": None},
                         result["aggregate"])
        outputs = self.outputs()
        self.assertEqual({"native_attestation_matrix", "aggregate_state", "aggregate_key",
                          "aggregate_receipt_sha256", "aggregate_required", "aggregate_payload_complete",
                          "sdk_handoff_required", "sdk_input_selection", "native_receipt_sha256s"}, set(outputs))
        self.assertEqual({target: {phase: phases[
            workflow.PhaseInstanceId("runtime", target, phase, target)]["receiptSha256"]
            for phase in ("binary", "package", "validation", "metadata")}
            for target in workflow.NATIVE_TARGETS}, json.loads(outputs["native_receipt_sha256s"]))
        self.assertEqual("true", outputs["aggregate_required"])
        self.assertEqual("false", outputs["aggregate_payload_complete"])
        self.assertEqual("", outputs["aggregate_receipt_sha256"])

    def test_native_recovery_cli_publishes_empty_matrix_only_after_capture(self):
        import runtime_preparation_capture

        arguments = ["recover-native-handoffs", "--plan", str(self.root / "plan"),
            "--destination", str(self.root / "recovered"), "--github-output", str(self.output),
            "--trusted-workflow-sha", PIN, "--recovery-json", '{"fixture":"original uploads"}',
            "--selected-receipts-json", '{"fixture":"current replay"}']
        with mock.patch.object(runtime_preparation_capture, "capture_runtime_native_release_handoffs",
                               create=True) as capture:
            self.assertEqual(0, workflow.main(arguments))
        capture.assert_called_once_with(self.root / "plan", self.root / "recovered",
            recovery={"fixture": "original uploads"}, selected_receipt_sha256s={"fixture": "current replay"},
            trusted_workflow_sha=PIN, token=workflow.os.environ.get("GITHUB_TOKEN", ""))
        self.assertEqual('{"include":[]}', self.outputs()["native_attestation_matrix"])
        original = self.output.read_bytes()
        with mock.patch.object(runtime_preparation_capture, "capture_runtime_native_release_handoffs",
                               create=True, side_effect=ValueError("original upload rejected")), \
                self.assertRaises(SystemExit):
            workflow.main(arguments)
        self.assertEqual(original, self.output.read_bytes())

    def test_final_route_completed_and_fully_reused_payloads_still_require_all_originals(self):
        for state in ("retained", "reused"):
            inspected = self.final_fixture(state)
            selected = next(record for record in inspected["result"]["phases"]
                            if workflow.products._identity(record) == AGGREGATE)
            with self.subTest(state=state), mock.patch.object(workflow.products, "inspect_products", return_value=inspected):
                result = self.final_route()
            self.assertEqual({"state": "completed", "buildKey": selected["buildKey"],
                              "receiptSha256": selected["receiptSha256"]}, result["aggregate"])
            self.assertEqual("false", self.outputs()["aggregate_required"])
            self.assertEqual("true", self.outputs()["aggregate_payload_complete"])
            self.assertEqual(5, len(result["nativeAttestationMatrix"]["include"]))

    def test_complete_carrier_routes_without_native_resigning_only_for_exact_completed_receipt(self):
        for state, matching, count in (("reused", True, 0), ("retained", True, 0),
                                      ("reused", False, 5), ("build", True, 5)):
            inspected = self.final_fixture(state)
            selected = next(record for record in inspected["result"]["phases"]
                            if workflow.products._identity(record) == AGGREGATE)
            inspected["runtimeAggregateReleaseEvidence"] = [{
                "receiptSha256": selected["receiptSha256"] if matching and selected["receiptSha256"] else "sha256:" + "f" * 64,
                "handoffRoot": "external/original"}]
            with self.subTest(state=state, matching=matching), \
                    mock.patch.object(workflow.products, "inspect_products", return_value=inspected):
                result = self.final_route()
            self.assertEqual(count, len(result["nativeAttestationMatrix"]["include"]))
            if not count:
                self.assertEqual('{"include":[]}', self.outputs()["native_attestation_matrix"])
                self.assertEqual("true", self.outputs()["aggregate_payload_complete"])
                self.assertEqual(selected["receiptSha256"], result["aggregate"]["receiptSha256"])

    def test_final_route_missing_native_adapter_or_contract_original_rejects_before_outputs(self):
        identities = [workflow.PhaseInstanceId("runtime", target, "metadata", target) for target in workflow.NATIVE_TARGETS]
        identities.extend((workflow.PhaseInstanceId("runtime", "node-js", "validation", "node-js-binding"),
                           workflow.PhaseInstanceId("runtime", "jvm", "metadata", "jvm"),
                           workflow.PhaseInstanceId("contract", "contract", "validation", "common")))
        for identity in identities:
            for state in ("build", "reused"):
                inspected = self.final_fixture(state)
                inspected["result"]["phases"] = [record for record in inspected["result"]["phases"]
                    if workflow.products._identity(record) != identity]
                with self.subTest(identity=identity, aggregate=state), \
                        mock.patch.object(workflow.products, "inspect_products", return_value=inspected), \
                        self.assertRaisesRegex(ValueError, "incomplete original predecessor"):
                    self.final_route()
                self.assertFalse(self.output.exists())

    def test_final_route_incomplete_or_unqualified_originals_are_not_early_native_fanout(self):
        for field, value in (("state", "waiting"), ("state", "build"), ("state", "failed"),
                             ("receiptSha256", None), ("objectSha256", None), ("buildKey", "caller-key")):
            inspected = self.final_fixture("reused")
            predecessor = next(record for record in inspected["result"]["phases"]
                               if record["component"] == "node-wasm" and record["phase"] == "metadata")
            predecessor[field] = value
            with self.subTest(field=field, value=value), \
                    mock.patch.object(workflow.products, "inspect_products", return_value=inspected), \
                    self.assertRaises(ValueError):
                self.final_route()
            self.assertFalse(self.output.exists())

    def test_final_route_requires_exact_aggregate_election_not_empty_workers(self):
        good = self.final_fixture()
        cases = []
        for mutation in ("missing", "waiting", "no-plan", "wrong-key", "duplicate-phase", "duplicate-plan", "completed-plan"):
            value = deepcopy(good)
            selected = next(record for record in value["result"]["phases"]
                            if workflow.products._identity(record) == AGGREGATE)
            if mutation == "missing":
                value["result"]["phases"].remove(selected)
            elif mutation == "waiting":
                selected["state"] = "waiting"
            elif mutation == "no-plan":
                value["readyPlans"] = []
            elif mutation == "wrong-key":
                value["readyPlans"][0]["buildKey"] = KEY
            elif mutation == "duplicate-phase":
                value["result"]["phases"].append(deepcopy(selected))
            elif mutation == "duplicate-plan":
                value["readyPlans"].append(deepcopy(value["readyPlans"][0]))
            else:
                selected.update(state="retained", receiptSha256=KEY, objectSha256=KEY)
            cases.append((mutation, value))
        for mutation, inspected in cases:
            with self.subTest(mutation=mutation), mock.patch.object(workflow.products, "inspect_products", return_value=inspected), \
                    self.assertRaises(ValueError):
                self.final_route()
            self.assertFalse(self.output.exists())

    def test_final_route_rejected_replay_does_not_publish_caller_control(self):
        self.write_tree(self.root / "state", {"reuse-wave-result.json": b'{"fullReuse":true}\n'})
        with mock.patch.object(workflow.products, "inspect_products", side_effect=ValueError("original carrier rejected")), \
                mock.patch.object(workflow, "github_output") as output, \
                self.assertRaisesRegex(ValueError, "original carrier rejected"):
            self.final_route()
        output.assert_not_called()

    def test_final_route_cli_forwards_only_paths_and_explicit_tooling_policy(self):
        args = ["continuation", "--plan", "plan", "--discovery-root", "discovery", "--state-root", "state",
                "--github-output", str(self.output)]
        with mock.patch.object(workflow, "continuation") as route:
            self.assertEqual(0, workflow.main(args))
        route.assert_called_once_with(Path("plan"), Path("discovery"), Path("state"), self.output,
                                      sdk_validation_tooling=None)
        policy = {"fixture": "explicit caller tooling policy"}
        with mock.patch.object(workflow.products, "_canonical_control", return_value=policy) as read, \
                mock.patch.object(workflow, "continuation") as route:
            self.assertEqual(0, workflow.main([*args, "--sdk-validation-tooling", "tooling.json"]))
        read.assert_called_once_with(Path("tooling.json"), "Caller SDK tooling policy")
        self.assertEqual(policy, route.call_args.kwargs["sdk_validation_tooling"])
        with mock.patch.object(workflow, "continuation") as route:
            self.assertEqual(0, workflow.main([*args, "--if-selected"]))
        route.assert_called_once_with(Path("plan"), Path("discovery"), Path("state"), self.output,
                                      sdk_validation_tooling=None, if_selected=True)
        with mock.patch.object(workflow, "continuation") as route:
            self.assertEqual(0, workflow.main([*args, "--require-completed"]))
        route.assert_called_once_with(Path("plan"), Path("discovery"), Path("state"), self.output,
                                      sdk_validation_tooling=None, require_completed=True)
        with mock.patch.object(workflow, "continuation") as route:
            self.assertEqual(0, workflow.main([*args, "--sdk-original-workflow-sha", PIN]))
        self.assertEqual(PIN, route.call_args.kwargs["sdk_original_workflow_sha"])
        matrix_args = ["matrix", "--plan", "plan", "--discovery-root", "discovery",
                       "--state-root", "state", "--github-output", str(self.output)]
        with mock.patch.object(workflow, "matrix") as route:
            self.assertEqual(0, workflow.main([*matrix_args, "--sdk-original-workflow-sha", PIN]))
        self.assertEqual(PIN, route.call_args.kwargs["sdk_original_workflow_sha"])

    def test_capture_uses_caller_upload_then_current_captured_paths_for_each_wave(self):
        for wave in (0, 1, 4, 5):
            with self.subTest(state_wave=wave):
                destination = self.root / f"capture-{wave}"
                value = {"include": [row(NODE)]}
                with mock.patch.object(workflow.products, "capture_runtime_resume_upload", side_effect=self.captured) as capture, \
                        mock.patch.object(workflow.products, "runtime_worker_matrix", return_value=value) as gate:
                    result = workflow.capture(
                        self.root / "caller-plan", destination, self.output,
                        artifact_id=101, artifact_sha256=KEY, trusted_workflow_sha=PIN,
                        state_wave=wave, instance=NODE, expected_build_key=KEY,
                        repository_root=self.root, environ=self.environment, token="synthetic-token")
                capture.assert_called_once_with(
                    self.root / "caller-plan", destination, artifact_id=101, artifact_sha256=KEY,
                    trusted_workflow_sha=PIN, state_wave=wave, repository_root=self.root,
                    environ=self.environment, token="synthetic-token")
                original = destination / "original"
                plan = original / "product-resume-inputs/plan/impact-plan.json"
                discovery = original / "product-resume-state"
                state = original / ("runtime-state" if wave else "product-resume-state")
                gate.assert_called_once_with(plan, discovery, state,
                                             repository_root=self.root, environ=self.environment,
                                             sdk_original_workflow_sha=PIN)
                self.assertEqual({"input_root": original, "plan_path": plan, "discovery_root": discovery,
                                  "state_root": state, "phase_plan": state / "phase-plans/runtime-node-js-validation-node-js-binding.json",
                                  "matrix": value}, result)
                for name, raw in self.base.items():
                    self.assertEqual(raw, (original / name).read_bytes())

    def test_aggregate_capture_requires_exact_ready_closure_not_native_worker_election(self):
        for index, (status, key) in enumerate((("ready", KEY), ("completed", KEY),
                                              ("ready", "sha256:" + "0" * 64))):
            destination = self.root / f"aggregate-capture-{index}"
            with self.subTest(state=status, key=key), \
                    mock.patch.object(workflow.products, "capture_runtime_resume_upload", side_effect=self.captured), \
                    mock.patch.object(workflow.products, "runtime_worker_matrix", return_value={"include": []}), \
                    mock.patch.object(workflow, "continuation", return_value={"aggregate": {
                        "state": status, "buildKey": key}}) as route:
                def capture():
                    return workflow.capture(self.root / "plan", destination, self.output,
                        artifact_id=101, artifact_sha256=KEY, trusted_workflow_sha=PIN,
                        state_wave=4, instance=AGGREGATE, expected_build_key=KEY,
                        repository_root=self.root, environ=self.environment, token="synthetic")
                if index:
                    with self.assertRaisesRegex(ValueError, "aggregate is not elected"):
                        capture()
                else:
                    result = capture()
                    self.assertEqual(destination / "original/runtime-state/phase-plans/"
                                     "runtime-runtime-aggregate-metadata-aggregate.json", result["phase_plan"])
                route.assert_called_once_with(
                    destination / "original/product-resume-inputs/plan/impact-plan.json",
                    destination / "original/product-resume-state", destination / "original/runtime-state",
                    self.output, repository_root=self.root, environ=self.environment,
                    sdk_original_workflow_sha=PIN)

    def test_capture_rejects_failed_transport_partial_identity_wrong_key_and_duplicate_row(self):
        with mock.patch.object(workflow.products, "capture_runtime_resume_upload", side_effect=ValueError("transport rejected")), \
                mock.patch.object(workflow.products, "runtime_worker_matrix") as gate:
            with self.assertRaisesRegex(ValueError, "transport rejected"):
                workflow.capture(self.root / "plan", self.root / "failed", self.output,
                                 artifact_id=1, artifact_sha256=KEY, trusted_workflow_sha=PIN, token="x")
        gate.assert_not_called()
        for index, (instance, key, rows) in enumerate((
            (NODE, None, [row(NODE)]), (None, KEY, [row(NODE)]),
            (NODE, "sha256:" + "0" * 64, [row(NODE)]),
            (NODE, KEY, [row(JVM)]), (NODE, KEY, [row(NODE), row(NODE)]),
        )):
            with self.subTest(case=index), \
                    mock.patch.object(workflow.products, "capture_runtime_resume_upload", side_effect=self.captured), \
                    mock.patch.object(workflow.products, "runtime_worker_matrix", return_value={"include": rows}):
                with self.assertRaises(ValueError):
                    workflow.capture(self.root / "plan", self.root / f"bad-{index}", self.output,
                                     artifact_id=1, artifact_sha256=KEY, trusted_workflow_sha=PIN,
                                     instance=instance, expected_build_key=key, token="x")

    def test_collect_forwards_exact_shards_and_only_base_originals_to_the_next_handoff(self):
        self.write_tree(self.input, {"runtime-state/old-state.json": b"old wave bytes",
                                     "collection/old-diagnostic.log": b"not recursively forwarded"})
        before = regular_file_inventory(self.input, allow_empty=True)
        for wave in (1, 2):
            with self.subTest(wave=wave):
                destination = self.root / f"collected-{wave}"
                with mock.patch.object(workflow.products, "collect_runtime_workers", side_effect=self.collection) as collect, \
                        mock.patch.object(workflow.products, "advance_products", side_effect=self.advanced) as advance, \
                        mock.patch.object(workflow.products, "runtime_worker_matrix", return_value={"include": [row(NODE)]}) as gate:
                    result = self.collect(destination, wave)
                plan = self.input / "product-resume-inputs/plan/impact-plan.json"
                discovery = self.input / "product-resume-state"
                state = self.input / ("runtime-state" if wave > 1 else "product-resume-state")
                collect.assert_called_once_with(plan, discovery, state, destination / "collection",
                                                trusted_workflow_sha=PIN, repository_root=self.root,
                                                environ=self.environment, token="synthetic-token",
                                                sdk_original_workflow_sha=PIN)
                handoff = destination / "handoff"
                advance.assert_called_once_with(plan, discovery, state, [destination / "collection/good/shard"],
                                                handoff / "runtime-state", self.output,
                                                repository_root=self.root, environ=self.environment,
                                                failed_instances=(), runtime_workers_only=True,
                                                sdk_original_workflow_sha=PIN)
                gate.assert_called_once_with(handoff / "product-resume-inputs/plan/impact-plan.json",
                                             handoff / "product-resume-state", handoff / "runtime-state",
                                             repository_root=self.root, environ=self.environment,
                                             sdk_original_workflow_sha=PIN)
                self.assertEqual({"fullReuse": False, "fixture": "actual gate is mocked"}, result)
                self.assertEqual({"product-resume-inputs", "product-resume-state", "runtime-state"},
                                 {path.name for path in handoff.iterdir()})
                for name, raw in self.base.items():
                    self.assertEqual(raw, (handoff / name).read_bytes())
                self.assertFalse((handoff / "runtime-state/old-state.json").exists())
                self.assertEqual(before, regular_file_inventory(self.input, allow_empty=True))

    def test_failed_rows_still_advance_original_successes_but_disable_the_next_wave(self):
        def mixed(*args, **kwargs):
            result = self.collection(*args, **kwargs)
            result["rows"].append(row(NODE, result="failure", shardDirectory=None))
            return result
        destination = self.root / "mixed"
        with mock.patch.object(workflow.products, "collect_runtime_workers", side_effect=mixed), \
                mock.patch.object(workflow.products, "advance_products", side_effect=self.advanced) as advance, \
                mock.patch.object(workflow.products, "runtime_worker_matrix") as gate:
            self.collect(destination)
        self.assertEqual((NODE,), advance.call_args.kwargs["failed_instances"])
        self.assertEqual([destination / "collection/good/shard"], advance.call_args.args[3])
        self.assertTrue((destination / "handoff/runtime-state/reused-carrier/object.zip").is_file())
        self.assertEqual('{"include":[]}', self.outputs()["runtime_matrix"])
        self.assertEqual("false", self.outputs()["runtime_workers_required"])
        gate.assert_not_called()

    def aggregate_collection(self, *args, **kwargs):
        value = self.collection(*args, **kwargs)
        value["rows"] = [row(AGGREGATE, result="success", shardDirectory="good/shard")]
        return value

    def test_fifth_wave_advances_only_aggregate_and_replays_completed_payload_routing(self):
        self.write_tree(self.input, {"runtime-state/old-state.json": b"original wave four state"})
        before = regular_file_inventory(self.input, allow_empty=True)
        destination = self.root / "aggregate-collected"
        with mock.patch.object(workflow.products, "collect_runtime_workers", side_effect=self.aggregate_collection) as collect, \
                mock.patch.object(workflow.products, "advance_products", side_effect=self.advanced) as advance, \
                mock.patch.object(workflow.products, "inspect_products", return_value=self.final_fixture("retained")) as inspect, \
                mock.patch.object(workflow, "continuation", wraps=workflow.continuation) as route, \
                mock.patch.object(workflow.products, "runtime_worker_matrix", side_effect=AssertionError("no fifth worker matrix")):
            self.collect(destination, 5)
        plan = self.input / "product-resume-inputs/plan/impact-plan.json"
        collect.assert_called_once_with(plan, self.input / "product-resume-state", self.input / "runtime-state",
            destination / "collection", trusted_workflow_sha=PIN, repository_root=self.root,
            environ=self.environment, token="synthetic-token", runtime_aggregate_only=True,
            sdk_original_workflow_sha=PIN)
        handoff = destination / "handoff"
        advance.assert_called_once_with(plan, self.input / "product-resume-state", self.input / "runtime-state",
            [destination / "collection/good/shard"], handoff / "runtime-state", self.output,
            repository_root=self.root, environ=self.environment, failed_instances=(), runtime_aggregate_only=True,
            sdk_original_workflow_sha=PIN)
        route.assert_called_once_with(handoff / "product-resume-inputs/plan/impact-plan.json",
            handoff / "product-resume-state", handoff / "runtime-state", self.output,
            repository_root=self.root, environ=self.environment, require_completed=True,
            sdk_original_workflow_sha=PIN)
        inspect.assert_called_once()
        self.assertEqual("completed", self.outputs()["aggregate_state"])
        self.assertEqual("true", self.outputs()["aggregate_payload_complete"])
        self.assertNotIn("runtime_matrix", self.outputs())
        self.assertNotIn("runtime_workers_required", self.outputs())
        self.assertEqual(before, regular_file_inventory(self.input, allow_empty=True))
        for name, raw in self.base.items():
            self.assertEqual(raw, (handoff / name).read_bytes())
        self.assertTrue((destination / "collection/raw.log").is_file())

    def test_fifth_wave_failure_preserves_diagnostics_and_disables_only_final_routing(self):
        def failed(*args, **kwargs):
            value = self.aggregate_collection(*args, **kwargs)
            value["rows"][0].update(result="failure", shardDirectory=None)
            return value
        destination = self.root / "aggregate-failed"
        with mock.patch.object(workflow.products, "collect_runtime_workers", side_effect=failed), \
                mock.patch.object(workflow.products, "advance_products", side_effect=self.advanced) as advance, \
                mock.patch.object(workflow, "continuation") as route, \
                mock.patch.object(workflow.products, "runtime_worker_matrix") as matrix:
            self.collect(destination, 5)
        self.assertEqual([], advance.call_args.args[3])
        self.assertEqual((AGGREGATE,), advance.call_args.kwargs["failed_instances"])
        self.assertTrue(advance.call_args.kwargs["runtime_aggregate_only"])
        self.assertNotIn("runtime_workers_only", advance.call_args.kwargs)
        route.assert_not_called()
        matrix.assert_not_called()
        self.assertEqual({"native_attestation_matrix": '{"include":[]}', "aggregate_state": "failed",
                          "aggregate_key": "", "aggregate_receipt_sha256": "", "aggregate_required": "false",
                          "aggregate_payload_complete": "false"}, self.outputs())
        self.assertEqual(b"", (destination / "collection/raw.log").read_bytes())
        self.assertTrue((destination / "handoff/runtime-state/reused-carrier/object.zip").is_file())

    def test_fifth_wave_rejects_missing_duplicate_or_nonaggregate_rows_before_advancement(self):
        for index, rows in enumerate(([], [row(JVM)], [row(AGGREGATE), row(AGGREGATE)],
                                      [row(AGGREGATE), row(NODE)])):
            def wrong(*args, **kwargs):
                result = self.aggregate_collection(*args, **kwargs)
                result["rows"] = rows
                return result
            destination = self.root / f"aggregate-wrong-{index}"
            with self.subTest(rows=rows), mock.patch.object(workflow.products, "collect_runtime_workers", side_effect=wrong), \
                    mock.patch.object(workflow.products, "advance_products") as advance, \
                    mock.patch.object(workflow, "continuation") as route, \
                    self.assertRaisesRegex(ValueError, "sole elected aggregate"):
                self.collect(destination, 5)
            advance.assert_not_called()
            route.assert_not_called()
            self.assertTrue((destination / "collection/raw.log").exists())
            self.assertFalse(self.output.exists())

    def test_fifth_wave_success_cannot_publish_ready_or_rejected_payload_as_completed(self):
        for index, error in enumerate((None, ValueError("full replay rejected"))):
            destination = self.root / f"aggregate-incomplete-{index}"
            with self.subTest(error=error), \
                    mock.patch.object(workflow.products, "collect_runtime_workers", side_effect=self.aggregate_collection), \
                    mock.patch.object(workflow.products, "advance_products", side_effect=self.advanced), \
                    mock.patch.object(workflow.products, "inspect_products", return_value=self.final_fixture(), side_effect=error), \
                    self.assertRaises(ValueError):
                self.collect(destination, 5)
            self.assertFalse(self.output.exists())
            self.assertTrue((destination / "handoff/runtime-state/reused-carrier/object.zip").is_file())
        with mock.patch.object(workflow.products, "inspect_products") as inspect, self.assertRaisesRegex(ValueError, "boolean"):
            workflow.continuation(self.root / "plan", self.root / "discovery", self.root / "state", self.output,
                                  require_completed="true")
        inspect.assert_not_called()

    def test_fifth_wave_cli_delegates_fixed_scope_without_caller_subset_flags(self):
        with mock.patch.object(workflow, "collect") as collect, \
                mock.patch.dict(workflow.os.environ, {"GITHUB_TOKEN": "fixture-token"}, clear=True):
            self.assertEqual(0, workflow.main(["collect", "--input-root", str(self.input),
                "--destination", str(self.root / "cli-five"), "--github-output", str(self.output),
                "--wave", "5", "--trusted-workflow-sha", PIN]))
        collect.assert_called_once_with(self.input, self.root / "cli-five", self.output,
            wave=5, trusted_workflow_sha=PIN, token="fixture-token")
        with mock.patch.object(workflow, "collect") as collect:
            self.assertEqual(0, workflow.main(["collect", "--input-root", str(self.input),
                "--destination", str(self.root / "cli-five-initial"), "--github-output", str(self.output),
                "--wave", "5", "--state-wave", "0", "--trusted-workflow-sha", PIN]))
        self.assertEqual(0, collect.call_args.kwargs["state_wave"])

    def test_fifth_wave_can_advance_initial_reuse_or_final_native_wave_without_guessing(self):
        for state_wave in (0, 4):
            destination = self.root / f"aggregate-after-{state_wave}"
            if state_wave:
                self.write_tree(self.input, {"runtime-state/previous.json": b"original wave state"})
            before = regular_file_inventory(self.input, allow_empty=True)
            with self.subTest(state_wave=state_wave), \
                    mock.patch.object(workflow.products, "collect_runtime_workers", side_effect=self.aggregate_collection) as collect, \
                    mock.patch.object(workflow.products, "advance_products", side_effect=self.advanced) as advance, \
                    mock.patch.object(workflow.products, "inspect_products", return_value=self.final_fixture("retained")):
                self.collect(destination, 5, state_wave=state_wave)
            expected = self.input / ("runtime-state" if state_wave else "product-resume-state")
            self.assertEqual(expected, collect.call_args.args[2])
            self.assertEqual(expected, advance.call_args.args[2])
            self.assertEqual(before, regular_file_inventory(self.input, allow_empty=True))
            self.assertEqual("completed", self.outputs()["aggregate_state"])

    def test_collection_rejects_forbidden_or_ambiguous_predecessor_wave_before_capture(self):
        for wave, state_wave in ((1, 1), (2, 0), (3, 3), (4, 0), (5, -1), (5, 5),
                                  (5, True), (5, "0"), (5, 0.0)):
            with self.subTest(wave=wave, state_wave=state_wave), \
                    mock.patch.object(workflow.products, "collect_runtime_workers") as collect, \
                    mock.patch.object(workflow.products, "advance_products") as advance, \
                    self.assertRaisesRegex(ValueError, "invalid predecessor state wave"):
                self.collect(self.root / "invalid-predecessor", wave, state_wave=state_wave)
            collect.assert_not_called()
            advance.assert_not_called()
        self.assertFalse((self.root / "invalid-predecessor").exists())

    def test_invalid_wave_existing_output_and_input_overlap_reject_before_collection(self):
        before = regular_file_inventory(self.input, allow_empty=True)
        existing = self.root / "existing"
        self.write_tree(existing, {"sentinel": b"previous output"})
        for destination, wave in ((self.root / "bad-wave", 0), (self.root / "bad-wave-6", 6),
                                  (self.root / "bad-bool", True), (existing, 1),
                                  (self.input / "product-resume-inputs/nested-output", 1)):
            with self.subTest(destination=destination, wave=wave), \
                    mock.patch.object(workflow.products, "collect_runtime_workers") as collect:
                with self.assertRaises(ValueError):
                    self.collect(destination, wave)
                collect.assert_not_called()
        self.assertEqual(b"previous output", (existing / "sentinel").read_bytes())
        self.assertEqual(before, regular_file_inventory(self.input, allow_empty=True))

    def test_fourth_wave_cannot_silently_discard_remaining_workers(self):
        destination = self.root / "wave-four"
        with mock.patch.object(workflow.products, "collect_runtime_workers", side_effect=self.collection), \
                mock.patch.object(workflow.products, "advance_products", side_effect=self.advanced), \
                mock.patch.object(workflow.products, "runtime_worker_matrix", return_value={"include": [row(NODE)]}):
            with self.assertRaisesRegex(ValueError, "remain after four"):
                self.collect(destination, 4)
        self.assertTrue((destination / "collection/good/shard/phase-receipt.json").is_file())
        self.assertTrue((destination / "handoff/runtime-state/reused-carrier/object.zip").is_file())

    def test_cli_requires_complete_worker_identity_and_forwards_current_wave(self):
        capture_args = ["capture", "--plan", "plan", "--destination", str(self.root / "cli-capture"),
                        "--github-output", str(self.output), "--artifact-id", "101",
                        "--artifact-sha256", KEY, "--trusted-workflow-sha", PIN]
        with mock.patch.object(workflow, "capture") as capture, \
                mock.patch.dict(workflow.os.environ, {"GITHUB_TOKEN": "synthetic-token"}, clear=True):
            self.assertEqual(0, workflow.main([*capture_args, "--state-wave", "3", "--component", "node-js",
                                               "--phase", "validation", "--target", "node-js-binding",
                                               "--expected-build-key", KEY]))
        self.assertEqual(NODE, capture.call_args.kwargs["instance"])
        self.assertEqual(3, capture.call_args.kwargs["state_wave"])
        self.assertEqual(PIN, capture.call_args.kwargs["trusted_workflow_sha"])
        self.assertEqual("synthetic-token", capture.call_args.kwargs["token"])
        with mock.patch.object(workflow, "capture") as capture:
            with self.assertRaises(SystemExit):
                workflow.main([*capture_args, "--component", "node-js"])
            capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
