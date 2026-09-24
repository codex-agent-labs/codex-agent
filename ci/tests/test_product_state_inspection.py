"""Read-only inspection of an authenticated resumed product state."""

from pathlib import Path
import json
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from ci.products.inventory import load_canonical_json, regular_file_inventory, write_canonical_json
from ci.tests import test_runtime_resumed_phase as fixture


adapter = fixture.adapter
JVM = fixture.JVM


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ProductStateInspectionTest(unittest.TestCase):
    # Delegate the real resumed-state fixture without inheriting its test cases.
    setUpClass = classmethod(fixture.RuntimeResumedPhaseTest.setUpClass.__func__)
    control_seams = classmethod(fixture.RuntimeResumedPhaseTest.control_seams.__func__)
    setUp = fixture.RuntimeResumedPhaseTest.setUp
    tearDown = fixture.RuntimeResumedPhaseTest.tearDown
    resume = fixture.RuntimeResumedPhaseTest.resume
    binary_shard = fixture.RuntimeResumedPhaseTest.binary_shard
    advance = fixture.RuntimeResumedPhaseTest.advance

    def inspect(self, discovery: Path, state: Path | None = None):
        with self.control_seams():
            return adapter.inspect_products(
                self.plan_path, discovery, state,
                repository_root=self.repository, environ=self.environment,
            )

    def matrix(self, discovery: Path, state: Path | None = None):
        with self.control_seams():
            return adapter.runtime_worker_matrix(
                self.plan_path, discovery, state,
                repository_root=self.repository, environ=self.environment)

    def test_initial_resumed_state_re_elects_the_exact_runtime_plan_without_original_locations(self):
        resumed = self.resume()
        before = regular_file_inventory(resumed)
        expected = {
            "result": load_canonical_json(resumed / "reuse-wave-result.json"),
            "runtimeAggregateReleaseEvidence": [],
            "readyPlans": [load_canonical_json(resumed / "phase-plans/runtime-jvm-binary-jvm.json")],
        }
        hidden = []
        try:
            for source in (self.original, self.discovery, self.state, self.handoff):
                target = source.with_name(source.name + "-inspection-hidden")
                source.rename(target)
                hidden.append((source, target))
            self.assertEqual(expected, self.inspect(resumed))
            self.assertEqual({"include": [{
                "product": "runtime", "component": "jvm", "phase": "binary", "target": "jvm",
                "buildKey": expected["readyPlans"][0]["buildKey"],
                "toolchainProfileDigest": adapter.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                "runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64",
                "toolchainProfile": None, "producerRole": None, "supervisor": None,
            }]}, self.matrix(resumed))
        finally:
            for source, target in reversed(hidden):
                target.rename(source)
        self.assertEqual(before, regular_file_inventory(resumed))

    def test_advanced_runtime_state_replays_its_exact_result_and_original_receipts(self):
        resumed = self.resume()
        shard, descriptor = self.binary_shard(resumed, "inspection-advanced")
        advanced = self.scratch / "advanced-inspection"
        result = self.advance(resumed, shard, advanced)
        before = {
            path: regular_file_inventory(path)
            for path in (resumed, shard, advanced)
        }

        self.assertEqual({"result": result, "readyPlans": [], "runtimeAggregateReleaseEvidence": []},
                         self.inspect(resumed, advanced))
        self.assertEqual({"include": []}, self.matrix(resumed, advanced))
        selected = tuple(sorted(
            adapter._identity(phase) for phase in result["phases"]
            if phase["state"] in {"retained", "reused"}
        ))
        carrier = adapter.verify_carrier(
            advanced / "carrier", selected, adapter._consumer(self.plan, self.environment),
        )
        records = {adapter._identity(record): record for record in carrier["objects"]}
        for instance, expected in {
            JVM: descriptor["receiptBytes"],
            **{
                adapter.PhaseInstanceId("contract", "contract", phase, "common"): raw
                for phase, raw in self.original_bytes.items()
            },
        }.items():
            record = records[instance]
            restored = adapter.verify_object(
                advanced / "carrier" / adapter.object_relative_path(
                    record["buildKey"], record["receiptSha256"],
                ),
                build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
                object_sha256=record["objectSha256"],
            )
            self.assertEqual(expected, restored["receiptBytes"])
        for path, inventory in before.items():
            self.assertEqual(inventory, regular_file_inventory(path), str(path))

    def test_request_carrier_producer_and_current_result_mutations_are_rejected_read_only(self):
        resumed = self.resume()

        def change_request(root: Path) -> None:
            path = root / "reuse-wave-request.json"
            value = load_canonical_json(path)
            value["unexpected"] = True
            write_canonical_json(path, value)

        def change_carrier(root: Path) -> None:
            path = root / "reused-carrier/carrier.json"
            value = load_canonical_json(path)
            value["unexpected"] = True
            write_canonical_json(path, value)

        def change_producer(root: Path) -> None:
            path = root / "producer.json"
            value = load_canonical_json(path)
            value["runAttempt"] += 1
            write_canonical_json(path, value)

        def change_result(root: Path) -> None:
            path = root / "reuse-wave-result.json"
            value = load_canonical_json(path)
            selected = next(phase for phase in value["phases"] if adapter._identity(phase) == JVM)
            selected["buildKey"] = "sha256:" + "0" * 64
            matrix = next(phase for phase in value["matrices"]["runtime"] if adapter._identity(phase) == JVM)
            matrix["buildKey"] = selected["buildKey"]
            write_canonical_json(path, value)

        original = regular_file_inventory(resumed)
        for name, mutate, error in (
            ("request", change_request, "Reuse-wave request"),
            ("carrier", change_carrier, "[Cc]arrier"),
            ("producer", change_producer, "current workflow run"),
            ("result", change_result, "not reproducible"),
        ):
            state = self.scratch / f"changed-{name}"
            shutil.copytree(resumed, state)
            mutate(state)
            changed = regular_file_inventory(state)
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, error):
                self.matrix(resumed, state) if name in {"carrier", "result"} else self.matrix(state)
            self.assertEqual(changed, regular_file_inventory(state))
            self.assertEqual(original, regular_file_inventory(resumed))


class RuntimeMatrixControlTest(unittest.TestCase):
    """Control translation only; synthetic inspected rows are not admission proof."""

    def test_inspection_forwards_discovery_and_advanced_carrier_records_only_after_replay(self):
        first = {"receiptSha256": "sha256:" + "a" * 64, "handoffRoot": "discovery/original"}
        second = {"receiptSha256": "sha256:" + "b" * 64, "handoffRoot": "state/original"}
        state = SimpleNamespace(prior={"phases": []}, prior_ready_plans={},
            rebased_request={"runtimeAggregateReleaseEvidence": [first]})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with mock.patch.object(adapter, "_verified_product_state", return_value=state) as replay, \
                    mock.patch.object(adapter, "_retained_aggregate_handoffs", return_value=[second]) as retained:
                result = adapter.inspect_products(root / "plan", root / "discovery", root / "state",
                    repository_root=root, environ={})
            replay.assert_called_once_with(root / "plan", root / "discovery", root / "state", root, {}, None,
                sdk_original_workflow_sha=None)
            retained.assert_called_once_with(root / "state", root)
            self.assertEqual([first, second], result["runtimeAggregateReleaseEvidence"])
            self.assertNotIn("sdkInputSelection", result)
            self.assertEqual([first], state.rebased_request["runtimeAggregateReleaseEvidence"])
            with mock.patch.object(adapter, "_verified_product_state", side_effect=ValueError("replay rejected")), \
                    mock.patch.object(adapter, "_retained_aggregate_handoffs") as retained, \
                    self.assertRaisesRegex(ValueError, "replay rejected"):
                adapter.inspect_products(root / "plan", root / "discovery", repository_root=root)
            retained.assert_not_called()

    def test_sdk_inspection_flag_rejects_non_boolean_before_replay(self):
        for value in (1, "true", None):
            with self.subTest(value=value), mock.patch.object(adapter, "_verified_product_state") as replay:
                with self.assertRaisesRegex(ValueError, "boolean"):
                    adapter.inspect_products(Path("plan"), Path("discovery"), include_sdk_selection=value)
                replay.assert_not_called()

    def test_worker_command_keeps_fixed_task_and_windows_arguments_out_of_a_shell(self):
        wrapper = "/fixture path/gradlew"
        properties = {"codexAgent.phase": "package", "codexAgent.product": "runtime"}
        with mock.patch.object(adapter.os, "name", "posix"):
            command = adapter._runtime_worker_command(wrapper, properties, {})
        self.assertEqual([wrapper, "--offline", "--no-daemon", "--configuration-cache",
            "--configuration-cache-problems=fail", "-p", "runtime", "ciProductPhase",
            "-PcodexAgent.phase=package", "-PcodexAgent.product=runtime"], command)
        wrapper = "C:\\fixture path\\gradlew.bat"
        with mock.patch.object(adapter.os, "name", "nt"):
            environment = {"JAVA_HOME": "C:\\java path", "ComSpec": "never-invoked"}
            command = adapter._runtime_worker_command(wrapper, properties, environment)
            self.assertEqual(["C:\\java path\\bin\\java.exe", "-Xmx64m", "-Xms64m",
                "-Dorg.gradle.appname=gradlew", "-jar",
                "C:\\fixture path\\gradle\\wrapper\\gradle-wrapper.jar"], command[:6])
            self.assertNotIn("never-invoked", command)
            for character in '&|<>()^%!':
                with self.subTest(character=character):
                    command = adapter._runtime_worker_command(wrapper,
                        {"codexAgent.contractPayload": f"C:\\a{character}b"}, environment)
                    self.assertEqual(f"-PcodexAgent.contractPayload=C:\\a{character}b", command[-1])
            with self.assertRaisesRegex(ValueError, "JAVA_HOME"):
                adapter._runtime_worker_command(wrapper, properties, {})

    def test_only_standalone_runtime_rows_are_routed_and_profile_mismatch_fails(self):
        common = {"schemaVersion": 1, "buildKey": "sha256:" + "1" * 64,
                  "inputs": {"toolchainProfileDigest": adapter.NOT_APPLICABLE_TOOLCHAIN_DIGEST}}
        plan = {**common, "product": "runtime", "component": "jvm", "phase": "binary", "target": "jvm"}
        ignored = [{**common, "product": product, "component": component, "phase": "metadata", "target": target}
                   for product, component, target in (("contract", "contract", "common"),
                       ("sdk", "sdk-core", "common"), ("runtime", "runtime-aggregate", "aggregate"))]
        with mock.patch.object(adapter, "inspect_products", return_value={"readyPlans": [*ignored, plan]}):
            rows = adapter.runtime_worker_matrix(Path("plan"), Path("discovery"))["include"]
            self.assertEqual(["jvm"], [row["component"] for row in rows])
            plan["inputs"] = {"toolchainProfileDigest": "sha256:" + "2" * 64}
            with self.assertRaisesRegex(ValueError, "elected toolchain authority"):
                adapter.runtime_worker_matrix(Path("plan"), Path("discovery"))

    def test_cli_outputs_json_and_failure_declarations_are_exact_four_part_arguments(self):
        matrix = {"include": [{"toolchainProfile": None, "supervisor": None, "runner": "ubuntu-24.04"}]}
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            with mock.patch.object(adapter, "runtime_worker_matrix", return_value=matrix):
                self.assertEqual(0, adapter.main(["runtime-worker-matrix", "--plan", "plan",
                    "--discovery-root", "discovery", "--github-output", str(output)]))
            fields = dict(line.split("=", 1) for line in output.read_text().splitlines())
            self.assertEqual(matrix, json.loads(fields["runtime_matrix"]))
            self.assertEqual("true", fields["runtime_workers_required"])
        with mock.patch.object(adapter, "advance_products") as advance:
            self.assertEqual(0, adapter.main(["advance-products", "--plan", "plan",
                "--discovery-root", "discovery", "--destination", "result", "--github-output", "output",
                "--failed-phase", "runtime", "node-js", "binary", "node-js"]))
            self.assertEqual((adapter.PhaseInstanceId("runtime", "node-js", "binary", "node-js"),),
                             advance.call_args.kwargs["failed_instances"])


if __name__ == "__main__":
    unittest.main()
