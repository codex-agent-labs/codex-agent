"""Collect successful Runtime siblings without laundering failed workers."""

from contextlib import ExitStack
from pathlib import Path
import shutil
import unittest
from unittest import mock

from ci.products.inventory import (
    load_canonical_json,
    regular_file_inventory,
    write_canonical_json,
)
from ci.tests import test_runtime_resumed_phase as fixture


adapter = fixture.adapter
JVM = fixture.JVM
PhaseInstanceId = adapter.PhaseInstanceId
NODE = PhaseInstanceId("runtime", "node-js", "binary", "node-js")
WASM = PhaseInstanceId("runtime", "node-wasm", "binary", "node-wasm")
CONTRACT = PhaseInstanceId("contract", "contract", "metadata", "common")
CONTRACT_BINARY = PhaseInstanceId("contract", "contract", "binary", "common")


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class RuntimeWorkerCollectionTest(unittest.TestCase):
    # Delegate the real Contract-to-Runtime fixture, changing only its existing
    # selection seam so two independent Runtime binary siblings are elected.
    setUpClass = classmethod(fixture.RuntimeResumedPhaseTest.setUpClass.__func__)
    setUp = fixture.RuntimeResumedPhaseTest.setUp
    tearDown = fixture.RuntimeResumedPhaseTest.tearDown
    resume = fixture.RuntimeResumedPhaseTest.resume
    binary_shard = fixture.RuntimeResumedPhaseTest.binary_shard

    @classmethod
    def control_seams(cls):
        stack = ExitStack()
        stack.enter_context(mock.patch.object(adapter, "_validate_plan", return_value=cls.plan))
        stack.enter_context(mock.patch.object(adapter, "_requested", return_value=(JVM, NODE)))
        return stack

    def advance(
        self,
        resumed: Path,
        shards: list[Path],
        destination: Path,
        *,
        failed: tuple[PhaseInstanceId, ...],
    ):
        with self.control_seams():
            return adapter.advance_products(
                self.plan_path,
                resumed,
                None,
                shards,
                destination,
                self.scratch / f"{destination.name}-github-output",
                repository_root=self.repository,
                environ=self.environment,
                failed_instances=failed,
            )

    def contract_seams(self):
        stack = ExitStack()
        stack.enter_context(mock.patch.object(adapter, "_validate_plan", return_value=self.plan))
        stack.enter_context(mock.patch.object(adapter, "_requested", return_value=(CONTRACT,)))
        return stack

    def test_successful_jvm_sibling_is_retained_while_node_failure_remains_elected(self):
        resumed = self.resume()
        jvm_shard, descriptor = self.binary_shard(resumed, "collected-jvm")
        resumed_before = regular_file_inventory(resumed)
        shard_before = regular_file_inventory(jvm_shard)
        destination = self.scratch / "collected"
        node_plan = load_canonical_json(
            resumed / "phase-plans/runtime-node-js-binary-node-js.json"
        )

        result = self.advance(resumed, [jvm_shard], destination, failed=(NODE,))
        with self.control_seams():
            inspected = adapter.inspect_products(
                self.plan_path,
                resumed,
                destination,
                repository_root=self.repository,
                environ=self.environment,
            )

        phases = {adapter._identity(value): value for value in result["phases"]}
        self.assertEqual("retained", phases[JVM]["state"])
        self.assertEqual(descriptor["receiptSha256"], phases[JVM]["receiptSha256"])
        self.assertEqual("build", phases[NODE]["state"])
        self.assertEqual(
            [{**adapter._identity_record(NODE), "buildKey": node_plan["buildKey"]}],
            result["matrices"]["runtime"],
        )
        self.assertFalse(result["fullReuse"])
        self.assertEqual(
            {
                "schemaVersion": 1,
                "producer": self.producer,
                "failedPhases": [{
                    **adapter._identity_record(NODE),
                    "buildKey": node_plan["buildKey"],
                }],
            },
            load_canonical_json(destination / "wave-failures.json"),
        )
        self.assertEqual(
            (resumed / "phase-plans/runtime-node-js-binary-node-js.json").read_bytes(),
            (destination / "phase-plans/runtime-node-js-binary-node-js.json").read_bytes(),
        )
        self.assertFalse(
            (destination / "phase-plans/runtime-jvm-binary-jvm.json").exists()
        )
        self.assertEqual({"result": result, "readyPlans": [node_plan], "runtimeAggregateReleaseEvidence": []}, inspected)
        self.assertIn(
            "wave_failed=true",
            (self.scratch / "collected-github-output").read_text(encoding="utf-8").splitlines(),
        )
        selected = tuple(
            sorted(
                adapter._identity(value)
                for value in result["phases"]
                if value["state"] in {"retained", "reused"}
            )
        )
        carrier = adapter.verify_carrier(
            destination / "reused-carrier",
            selected,
            adapter._consumer(self.plan, self.environment),
        )
        retained_jvm = next(
            value for value in carrier["objects"] if adapter._identity(value) == JVM
        )
        self.assertEqual(descriptor["receiptSha256"], retained_jvm["receiptSha256"])
        self.assertEqual(resumed_before, regular_file_inventory(resumed))
        self.assertEqual(shard_before, regular_file_inventory(jvm_shard))

    def test_failures_and_shards_must_exactly_partition_the_elected_wave(self):
        resumed = self.resume()
        shard, _ = self.binary_shard(resumed, "partition-jvm")
        original = regular_file_inventory(resumed)
        shard_original = regular_file_inventory(shard)
        cases = (
            ("omitted-failure", [shard], (), "exactly partition"),
            ("omitted-success", [], (NODE,), "exactly partition"),
            ("overlap", [shard], (JVM, NODE), "exactly partition"),
            ("unexpected", [shard], (WASM,), "distinct elected build phases"),
            ("duplicate", [shard], (NODE, NODE), "distinct elected build phases"),
        )
        for name, shards, failed, error in cases:
            destination = self.scratch / name
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, error):
                self.advance(resumed, shards, destination, failed=failed)
            self.assertFalse(destination.exists())
            self.assertEqual(original, regular_file_inventory(resumed))
            self.assertEqual(shard_original, regular_file_inventory(shard))

    def test_all_failed_first_phase_retains_no_empty_carrier_and_remains_inspectable(self):
        initial = self.scratch / "initial-contract-wave"
        shutil.copytree(self.discovery, initial)
        shutil.copyfile(
            initial / "contract-reuse-request.json",
            initial / "reuse-wave-request.json",
        )
        self.assertFalse((initial / "reused-carrier").exists())
        binary_plan = load_canonical_json(
            initial / "phase-plans/contract-contract-binary-common.json"
        )
        original = regular_file_inventory(initial)
        destination = self.scratch / "all-failed"

        with self.contract_seams():
            result = adapter.advance_products(
                self.plan_path,
                initial,
                None,
                [],
                destination,
                self.scratch / "all-failed-github-output",
                repository_root=self.repository,
                environ=self.environment,
                failed_instances=(CONTRACT_BINARY,),
            )
            inspected = adapter.inspect_products(
                self.plan_path,
                initial,
                destination,
                repository_root=self.repository,
                environ=self.environment,
            )

        self.assertFalse(result["fullReuse"])
        self.assertEqual(
            [{**adapter._identity_record(CONTRACT_BINARY), "buildKey": binary_plan["buildKey"]}],
            result["matrices"]["contract"],
        )
        self.assertEqual(
            {"result": result, "readyPlans": [binary_plan], "runtimeAggregateReleaseEvidence": []},
            inspected,
        )
        self.assertFalse((destination / "reused-carrier").exists())
        self.assertFalse((destination / "carrier").exists())
        self.assertIn(
            "wave_failed=true",
            (self.scratch / "all-failed-github-output").read_text(encoding="utf-8").splitlines(),
        )
        self.assertEqual(
            {
                "schemaVersion": 1,
                "producer": self.producer,
                "failedPhases": [{
                    **adapter._identity_record(CONTRACT_BINARY),
                    "buildKey": binary_plan["buildKey"],
                }],
            },
            load_canonical_json(destination / "wave-failures.json"),
        )
        self.assertEqual(original, regular_file_inventory(initial))

    def test_wrong_shard_identity_key_and_producer_never_publish(self):
        resumed = self.resume()
        original = regular_file_inventory(resumed)
        valid, _ = self.binary_shard(resumed, "valid-routing")
        wrong_producer, _ = self.binary_shard(
            resumed,
            "wrong-producer",
            producer={**self.producer, "runAttempt": self.producer["runAttempt"] + 1},
        )
        cases = []
        for name, change, error in (
            (
                "identity",
                lambda value: value.update(
                    component=WASM.component,
                    target=WASM.target,
                ),
                "Unexpected product phase shard",
            ),
            (
                "key",
                lambda value: value.update(buildKey="sha256:" + "0" * 64),
                "",
            ),
        ):
            changed = self.scratch / f"wrong-{name}-shard"
            shutil.copytree(valid, changed)
            descriptor_path = changed / adapter.PHASE_SHARD_NAME
            descriptor = load_canonical_json(descriptor_path)
            change(descriptor)
            write_canonical_json(descriptor_path, descriptor)
            cases.append((name, changed, error))
        cases.append(("producer", wrong_producer, "elected plan and producer"))

        for name, shard, error in cases:
            destination = self.scratch / f"rejected-{name}"
            context = self.assertRaises(ValueError) if not error else self.assertRaisesRegex(
                ValueError, error,
            )
            with self.subTest(name=name), context:
                self.advance(resumed, [shard], destination, failed=(NODE,))
            self.assertFalse(destination.exists())
            self.assertEqual(original, regular_file_inventory(resumed))


if __name__ == "__main__":
    unittest.main()
