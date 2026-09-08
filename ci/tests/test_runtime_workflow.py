"""Workflow composition checks; mocked gates are not product/host admission.

The retained byte trees are real. Planner, transport and execution assertions
below only verify delegation to their existing separately tested authorities.
"""

from pathlib import Path
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


def row(instance, **extra):
    return {**workflow.products._identity_record(instance), "buildKey": KEY, **extra}


class RuntimeWorkflowTest(unittest.TestCase):
    def test_fixed_workflow_collects_all_four_waves_before_final_failure(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / '.github/workflows/product-validation.yml').read_text()
        for wave in range(1, 5):
            worker = source.split(f'  runtime-workers-{wave}:\n', 1)[1].split(f'  runtime-collect-{wave}:\n', 1)[0]
            collector = source.split(f'  runtime-collect-{wave}:\n', 1)[1].split('\n\n', 1)[0]
            self.assertIn('always()', collector)
            self.assertIn(f'runtime-workers-{wave}]', collector)
            self.assertNotIn(f"needs.runtime-workers-{wave}.result == 'success'", collector)
            self.assertIn(f"wave: '{wave}'", collector)
            self.assertIn('fail-fast: false', worker)
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
        self.assertIn('path: build/runtime-next/handoff', collected)
        self.assertIn('build/runtime-next/collection', collected)
        self.assertIn("failure() && 'build/runtime-next'", collected)
        self.assertNotIn('overwrite: true', collected)

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

    def collect(self, destination, wave=1):
        return workflow.collect(self.input, destination, self.output, wave=wave,
                                trusted_workflow_sha=PIN, repository_root=self.root,
                                environ=self.environment, token="synthetic-token")

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

    def test_capture_uses_caller_upload_then_current_captured_paths_for_each_wave(self):
        for wave in (0, 1, 4):
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
                                             repository_root=self.root, environ=self.environment)
                self.assertEqual({"input_root": original, "plan_path": plan, "discovery_root": discovery,
                                  "state_root": state, "phase_plan": state / "phase-plans/runtime-node-js-validation-node-js-binding.json",
                                  "matrix": value}, result)
                for name, raw in self.base.items():
                    self.assertEqual(raw, (original / name).read_bytes())

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
                                                environ=self.environment, token="synthetic-token")
                handoff = destination / "handoff"
                advance.assert_called_once_with(plan, discovery, state, [destination / "collection/good/shard"],
                                                handoff / "runtime-state", self.output,
                                                repository_root=self.root, environ=self.environment,
                                                failed_instances=(), runtime_workers_only=True)
                gate.assert_called_once_with(handoff / "product-resume-inputs/plan/impact-plan.json",
                                             handoff / "product-resume-state", handoff / "runtime-state",
                                             repository_root=self.root, environ=self.environment)
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

    def test_invalid_wave_existing_output_and_input_overlap_reject_before_collection(self):
        before = regular_file_inventory(self.input, allow_empty=True)
        existing = self.root / "existing"
        self.write_tree(existing, {"sentinel": b"previous output"})
        for destination, wave in ((self.root / "bad-wave", 0), (self.root / "bad-wave-5", 5),
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
