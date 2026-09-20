"""Control coverage for collecting only elected standalone Runtime workers."""

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ci.products.inventory import load_canonical_json, write_canonical_json
from ci.tests import test_runtime_resumed_phase as fixture


adapter = fixture.adapter
PhaseInstanceId = adapter.PhaseInstanceId
JVM = PhaseInstanceId("runtime", "jvm", "binary", "jvm")
NODE = PhaseInstanceId("runtime", "node-js", "binary", "node-js")
SDK = PhaseInstanceId("sdk", "sdk-core", "binary", "common")
AGGREGATE = PhaseInstanceId(
    "runtime", "runtime-aggregate", "metadata", "aggregate",
)


class RuntimeCollectionScopeTest(unittest.TestCase):
    """Synthetic planner mechanics only; this is not Runtime execution evidence."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.producer = {
            "repository": "example/repository",
            "commit": "a" * 40,
            "tree": "b" * 40,
            "event": "pull_request",
            "workflowPath": ".github/workflows/product-validation.yml",
            "runId": 17,
            "runAttempt": 1,
            "pullRequest": 9,
        }
        self.instances = (JVM, NODE, SDK, AGGREGATE)
        self.plans = {
            instance: {
                "schemaVersion": 1,
                **adapter._identity_record(instance),
                "buildKey": self._digest(str(index + 1)),
                "inputs": {},
            }
            for index, instance in enumerate(self.instances)
        }
        phases = [self._build_phase(instance) for instance in self.instances]
        prior = {
            "schemaVersion": 1,
            "result": "build-required",
            "fullReuse": False,
            "phases": phases,
            "matrices": {
                "contract": [],
                "runtime": [
                    {**adapter._identity_record(instance),
                     "buildKey": self.plans[instance]["buildKey"]}
                    for instance in (JVM, NODE, AGGREGATE)
                ],
                "sdk": [{**adapter._identity_record(SDK),
                         "buildKey": self.plans[SDK]["buildKey"]}],
            },
            "continuationRequirements": [],
        }
        self.state = adapter._VerifiedProductState(
            plan={"event": "pull_request", "validationCommit": "a" * 40},
            producer=self.producer,
            consumer={"producer": self.producer},
            requested=self.instances,
            closure=self.instances,
            expected_fixed={
                "versions": {"runtime-release": "0.2.0", "sdk": "0.2.0"},
            },
            rebased_request={"availableObjects": [], "runtimeValidationEvidence": []},
            prior=prior,
            prior_by_instance={instance: phase for instance, phase in zip(self.instances, phases)},
            sources={},
            prior_carrier_phases={},
            prior_ready_plans=self.plans,
        )

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def _digest(character: str) -> str:
        return "sha256:" + character * 64

    def _build_phase(self, instance: PhaseInstanceId) -> dict:
        return {
            **adapter._identity_record(instance),
            "buildKey": self.plans[instance]["buildKey"],
            "state": "build",
            "source": None,
            "transportSource": None,
            "receiptSha256": None,
            "objectSha256": None,
            "misses": [],
        }

    def _retained_phase(self, instance: PhaseInstanceId) -> dict:
        return {
            **adapter._identity_record(instance),
            "buildKey": self.plans[instance]["buildKey"],
            "state": "retained",
            "source": "phase-shard",
            "transportSource": {
                "kind": "phase-shard",
                "descriptorSha256": self._digest("8"),
                "producer": self.producer,
            },
            "receiptSha256": self._digest("6"),
            "objectSha256": self._digest("7"),
            "misses": [],
        }

    def _shard(self, instance: PhaseInstanceId) -> Path:
        root = self.root / f"shard-{instance.component}"
        root.mkdir()
        write_canonical_json(root / adapter.PHASE_SHARD_NAME, {
            "schemaVersion": 1,
            **adapter._identity_record(instance),
            "buildKey": self.plans[instance]["buildKey"],
            "receiptSha256": self._digest("6"),
            "objectSha256": self._digest("7"),
            "objectPath": "object",
        })
        return root

    def _verified_shard(self, root: Path, instance: PhaseInstanceId) -> dict:
        descriptor = load_canonical_json(root / adapter.PHASE_SHARD_NAME)
        return {
            **descriptor,
            "receipt": {
                "producer": self.producer,
                "trustDomain": "development",
                "productVersion": "0.2.0",
                "buildKey": descriptor["buildKey"],
            },
        }

    def _advance(
        self,
        successes: tuple[PhaseInstanceId, ...],
        failures: tuple[PhaseInstanceId, ...],
        name: str,
        *,
        runtime_workers_only: bool = True,
        runtime_aggregate_only: bool = False,
    ) -> tuple[dict, Path, Path]:
        shards = [self._shard(instance) for instance in successes]
        retained = set(successes)
        phases = [
            self._retained_phase(instance) if instance in retained
            else self._build_phase(instance)
            for instance in self.instances
        ]
        advanced = {
            "schemaVersion": 1,
            "result": "build-required",
            "fullReuse": False,
            "phases": phases,
            "matrices": {
                "contract": [],
                "runtime": [
                    {**adapter._identity_record(instance),
                     "buildKey": self.plans[instance]["buildKey"]}
                    for instance in (JVM, NODE, AGGREGATE) if instance not in retained
                ],
                "sdk": [{**adapter._identity_record(SDK),
                         "buildKey": self.plans[SDK]["buildKey"]}],
            },
            "continuationRequirements": [],
        }

        def plan(_request, _tooling, *, apple_policy=None, build_plan_consumer=None):
            self.assertIsNone(apple_policy)
            if build_plan_consumer is not None:
                for instance in self.instances:
                    if instance not in retained:
                        build_plan_consumer(instance, self.plans[instance])
            return deepcopy(advanced)

        selected = tuple(instance for instance in self.instances if instance in retained)
        selected_phases = tuple(
            next(phase for phase in phases if adapter._identity(phase) == instance)
            for instance in selected
        )
        destination = self.root / name
        output = self.root / f"{name}-github-output"
        with (
            mock.patch.object(adapter, "_verified_product_state", return_value=self.state),
            mock.patch.object(adapter, "verify_phase_shard", side_effect=self._verified_shard),
            mock.patch.object(adapter, "_materialize_runtime_validation_handoffs", return_value=[]),
            mock.patch.object(adapter, "_available_object_records", return_value=[]),
            mock.patch.object(adapter, "_retained_native_handoffs", return_value=[]),
            mock.patch.object(adapter, "_retained_sdk_handoffs", return_value=[]),
            mock.patch.object(adapter, "_plan_with_sdk_tooling", side_effect=plan),
            mock.patch.object(
                adapter, "_validate_reuse_result",
                return_value=(advanced, selected, selected_phases),
            ),
            mock.patch.object(adapter, "_catalog_object_sources", return_value={}),
            mock.patch.object(adapter, "write_carrier"),
        ):
            result = adapter.advance_products(
                self.root / "plan.json",
                self.root,
                None,
                shards,
                destination,
                output,
                repository_root=self.root,
                environ={},
                failed_instances=failures,
                runtime_workers_only=runtime_workers_only,
                runtime_aggregate_only=runtime_aggregate_only,
            )
        return result, destination, output

    def test_aggregate_scope_preserves_unrelated_ready_rows(self):
        result, destination, output = self._advance(
            (AGGREGATE,), (), "aggregate-only", runtime_workers_only=False,
            runtime_aggregate_only=True)
        phases = {adapter._identity(phase): phase for phase in result["phases"]}
        self.assertEqual("retained", phases[AGGREGATE]["state"])
        for instance in (JVM, NODE, SDK):
            self.assertEqual("build", phases[instance]["state"])
        self.assertIn("wave_failed=false", output.read_text())

    def test_aggregate_scope_rejects_unrelated_shard_and_conflicting_flags(self):
        for index, (successes, workers) in enumerate((((JVM,), False), ((AGGREGATE,), True))):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self._advance(successes, (), f"bad-aggregate-{index}",
                              runtime_workers_only=workers, runtime_aggregate_only=True)

    def test_runtime_scope_preserves_unrelated_ready_rows_without_reporting_failures(self):
        result, destination, output = self._advance(
            (JVM, NODE), (), "runtime-success",
        )

        by_instance = {adapter._identity(phase): phase for phase in result["phases"]}
        self.assertEqual("retained", by_instance[JVM]["state"])
        self.assertEqual("retained", by_instance[NODE]["state"])
        self.assertEqual("build", by_instance[SDK]["state"])
        self.assertEqual("build", by_instance[AGGREGATE]["state"])
        self.assertFalse((destination / "wave-failures.json").exists())
        self.assertEqual(
            {SDK, AGGREGATE},
            {
                adapter._identity(load_canonical_json(path))
                for path in (destination / "phase-plans").iterdir()
            },
        )
        self.assertIn("wave_failed=false", output.read_text(encoding="utf-8").splitlines())

    def test_runtime_successes_and_failures_exactly_partition_only_runtime_rows(self):
        result, destination, output = self._advance(
            (JVM,), (NODE,), "runtime-partial",
        )

        self.assertEqual("build", next(
            phase["state"] for phase in result["phases"]
            if adapter._identity(phase) == NODE
        ))
        failures = load_canonical_json(destination / "wave-failures.json")
        self.assertEqual(
            [{**adapter._identity_record(NODE), "buildKey": self.plans[NODE]["buildKey"]}],
            failures["failedPhases"],
        )
        self.assertNotIn(SDK, {adapter._identity(value) for value in failures["failedPhases"]})
        self.assertNotIn(AGGREGATE, {adapter._identity(value) for value in failures["failedPhases"]})
        self.assertIn("wave_failed=true", output.read_text(encoding="utf-8").splitlines())

    def test_runtime_scope_rejects_omitted_and_unrelated_rows(self):
        jvm = self._shard(JVM)
        sdk = self._shard(SDK)
        cases = (
            ("omitted-runtime", [jvm], (), "exactly partition"),
            ("unrelated-shard", [jvm, sdk], (NODE,), "Unexpected product phase shard"),
            ("unrelated-failure", [jvm], (NODE, SDK), "distinct elected build phases"),
            ("aggregate-failure", [jvm], (NODE, AGGREGATE), "distinct elected build phases"),
        )
        for name, shards, failures, message in cases:
            destination = self.root / name
            with (
                self.subTest(name=name),
                mock.patch.object(adapter, "_verified_product_state", return_value=self.state),
                mock.patch.object(
                    adapter, "verify_phase_shard", side_effect=self._verified_shard,
                ),
                self.assertRaisesRegex(ValueError, message),
            ):
                adapter.advance_products(
                    self.root / "plan.json", self.root, None, shards, destination,
                    self.root / f"{name}-output", repository_root=self.root,
                    environ={}, failed_instances=failures, runtime_workers_only=True,
                )
            self.assertFalse(destination.exists())

    def test_default_scope_still_requires_the_entire_ready_wave(self):
        with self.assertRaisesRegex(ValueError, "exactly partition"):
            self._advance((JVM, NODE), (), "default-scope", runtime_workers_only=False)
        self.assertFalse((self.root / "default-scope").exists())

    def test_cli_forwards_runtime_scope_only_when_requested(self):
        common = [
            "advance-products", "--plan", "plan", "--discovery-root", "discovery",
            "--destination", "destination", "--github-output", "output",
        ]
        with mock.patch.object(adapter, "advance_products") as advance:
            self.assertEqual(0, adapter.main([*common, "--runtime-workers-only"]))
            self.assertIs(True, advance.call_args.kwargs["runtime_workers_only"])
        with mock.patch.object(adapter, "advance_products") as advance:
            self.assertEqual(0, adapter.main(common))
            self.assertNotIn("runtime_workers_only", advance.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
