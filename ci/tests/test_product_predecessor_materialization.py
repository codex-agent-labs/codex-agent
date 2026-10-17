"""Materialize authenticated predecessors for an elected product phase."""

from dataclasses import replace
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from ci.products.inventory import load_canonical_json, regular_file_inventory
from ci.products.receipt import verify_output_manifest_identity
from ci.tests import test_runtime_resumed_phase as fixture
from ci.tests import test_runtime_aggregate_handoff as aggregate_fixture


adapter = fixture.adapter
JVM = fixture.JVM
PhaseInstanceId = adapter.PhaseInstanceId
CONTRACT_METADATA = PhaseInstanceId("contract", "contract", "metadata", "common")
CONTRACT_PHASES = tuple(sorted(
    PhaseInstanceId("contract", "contract", phase, "common")
    for phase in ("binary", "package", "validation", "metadata")
))


class OriginalSdkSourceProvisioningTest(unittest.TestCase):
    def test_only_a_verified_consumed_sdk_receipt_can_provision_original_git(self):
        sdk = PhaseInstanceId('sdk', 'javascript', 'package', 'node')
        original = {'commit': 'original-merge', 'tree': 'original-tree'}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            body = root / 'original.zip'
            body.write_bytes(b'fixture-object')
            state = SimpleNamespace(prior_carrier_phases={sdk: {
                'buildKey': 'key', 'receiptSha256': 'receipt', 'objectSha256': 'object'}},
                sources={sdk: body}, ensure_original_source=mock.Mock())
            destination = root / 'inputs'
            destination.mkdir()
            verified = {'receiptBytes': b'original-receipt', 'receipt': {'producer': original}}
            with mock.patch.object(adapter, 'restore_object', return_value=verified) as restore:
                adapter._restore_product_objects(state, (sdk,), destination)
            restore.assert_called_once()
            state.ensure_original_source.assert_called_once_with(original)
            state.ensure_original_source.reset_mock()
            rejected = root / 'rejected'
            rejected.mkdir()
            with mock.patch.object(adapter, 'restore_object', side_effect=ValueError('invalid object')), \
                    self.assertRaisesRegex(ValueError, 'invalid object'):
                adapter._restore_product_objects(state, (sdk,), rejected)
            state.ensure_original_source.assert_not_called()


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ProductPredecessorMaterializationTest(unittest.TestCase):
    # Delegate the real resumed-state fixture without collecting its test cases.
    setUpClass = classmethod(fixture.RuntimeResumedPhaseTest.setUpClass.__func__)
    control_seams = classmethod(fixture.RuntimeResumedPhaseTest.control_seams.__func__)
    setUp = fixture.RuntimeResumedPhaseTest.setUp
    tearDown = fixture.RuntimeResumedPhaseTest.tearDown
    resume = fixture.RuntimeResumedPhaseTest.resume

    def materialize(
        self,
        resumed: Path,
        destination: Path,
        *,
        instance: PhaseInstanceId = JVM,
        build_key: str | None = None,
    ):
        ready = load_canonical_json(resumed / "phase-plans/runtime-jvm-binary-jvm.json")
        with self.control_seams():
            result = adapter.materialize_product_predecessors(
                self.plan_path,
                resumed,
                resumed,
                instance,
                destination,
                expected_build_key=ready["buildKey"] if build_key is None else build_key,
                repository_root=self.repository,
                environ=self.environment,
            )
        return ready, result

    def test_jvm_binary_materializes_its_exact_contract_predecessor_closure(self):
        resumed = self.resume()
        original = regular_file_inventory(resumed)
        destination = self.scratch / "materialized"

        ready, result = self.materialize(resumed, destination)

        self.assertEqual(
            CONTRACT_PHASES,
            tuple(
                dependency
                for dependency in adapter._dependency_closure((JVM,))
                if dependency != JVM
            ),
        )
        self.assertEqual(ready, result)
        self.assertEqual(
            (resumed / "phase-plans/runtime-jvm-binary-jvm.json").read_bytes(),
            (destination / "phase-plan.json").read_bytes(),
        )
        self.assertEqual(
            (resumed / "producer.json").read_bytes(),
            (destination / "producer.json").read_bytes(),
        )
        for dependency in CONTRACT_PHASES:
            predecessor = destination / "-".join((
                dependency.product,
                dependency.component,
                dependency.phase,
                dependency.target,
            ))
            self.assertEqual(
                self.original_bytes[dependency.phase],
                (predecessor / "phase-receipt.json").read_bytes(),
            )
            receipt = load_canonical_json(predecessor / "phase-receipt.json")
            verify_output_manifest_identity(
                predecessor / "stage",
                dependency.product,
                dependency.component,
                dependency.phase,
                dependency.target,
                receipt["productVersion"],
            )
        self.assertEqual(
            {
                "phase-plan.json",
                "producer.json",
                *(
                    "-".join((value.product, value.component, value.phase, value.target))
                    for value in CONTRACT_PHASES
                ),
            },
            {path.name for path in destination.iterdir()},
        )
        self.assertEqual(original, regular_file_inventory(resumed))

    def test_wrong_key_nonready_and_unknown_phase_reject_without_output(self):
        resumed = self.resume()
        original = regular_file_inventory(resumed)
        cases = (
            ("wrong-key", JVM, "sha256:" + "0" * 64, "not ready"),
            (
                "nonready",
                PhaseInstanceId("runtime", "jvm", "package", "jvm"),
                None,
                "not ready",
            ),
            (
                "unknown",
                PhaseInstanceId("runtime", "jvm", "binary", "unknown"),
                None,
                "Unknown product phase instance",
            ),
        )
        for name, instance, build_key, error in cases:
            destination = self.scratch / name
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, error):
                self.materialize(
                    resumed, destination, instance=instance, build_key=build_key,
                )
            self.assertFalse(destination.exists())
            self.assertEqual(original, regular_file_inventory(resumed))

    def test_changed_authenticated_carrier_object_rejects_without_publication(self):
        resumed = self.resume()
        changed = self.scratch / "changed-state"
        shutil.copytree(resumed, changed)
        request = load_canonical_json(changed / "reuse-wave-request.json")
        record = next(
            value for value in request["availableObjects"]
            if adapter._identity(value) == CONTRACT_METADATA
        )
        archive = changed / record["objectPath"]
        archive.write_bytes(archive.read_bytes() + b"changed")
        changed_inventory = regular_file_inventory(changed)
        destination = self.scratch / "rejected-carrier"

        with self.assertRaises(ValueError):
            self.materialize(changed, destination)

        self.assertFalse(destination.exists())
        self.assertEqual(changed_inventory, regular_file_inventory(changed))

    def test_destination_overlap_and_nonempty_output_reject_without_mutation(self):
        resumed = self.resume()
        original = regular_file_inventory(resumed)
        overlap = resumed / "materialized-predecessors"
        with self.assertRaisesRegex(ValueError, "overlaps original state"):
            self.materialize(resumed, overlap)
        self.assertFalse(overlap.exists())

        destination = self.scratch / "existing"
        destination.mkdir()
        sentinel = destination / "sentinel"
        sentinel.write_bytes(b"preserve me")
        with self.assertRaisesRegex(ValueError, "absent or empty"):
            self.materialize(resumed, destination)
        self.assertEqual(b"preserve me", sentinel.read_bytes())
        self.assertEqual(original, regular_file_inventory(resumed))

    def test_restore_failure_does_not_publish_partial_predecessors(self):
        resumed = self.resume()
        original = regular_file_inventory(resumed)
        destination = self.scratch / "failed-restore"
        restore = adapter.restore_object

        def fail_after_verified_restore(*arguments, **keywords):
            restore(*arguments, **keywords)
            raise OSError("fixture failure after verified restore")

        with mock.patch.object(adapter, "restore_object", side_effect=fail_after_verified_restore):
            with self.assertRaisesRegex(OSError, "fixture failure after verified restore"):
                self.materialize(resumed, destination)

        self.assertFalse(destination.exists())
        self.assertEqual(original, regular_file_inventory(resumed))


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class SdkRuntimePredecessorMaterializationTest(unittest.TestCase):
    """Real original objects; SDK readiness is an explicitly substituted state boundary."""

    control_seams = classmethod(fixture.RuntimeResumedPhaseTest.control_seams.__func__)
    setUp = fixture.RuntimeResumedPhaseTest.setUp
    tearDown = fixture.RuntimeResumedPhaseTest.tearDown
    resume = fixture.RuntimeResumedPhaseTest.resume
    SDK = PhaseInstanceId("sdk", "python", "package", "desktop")

    @classmethod
    def setUpClass(cls):
        fixture.RuntimeResumedPhaseTest.setUpClass.__func__(cls)
        aggregate_fixture.RuntimeAggregateHandoffTest.setUpClass()
        cls.addClassCleanup(aggregate_fixture.RuntimeAggregateHandoffTest.doClassCleanups)
        cls.released = aggregate_fixture.RuntimeAggregateHandoffTest.carrier

    def inputs(self):
        resumed = self.resume()
        with self.control_seams():
            state = adapter._verified_product_state(self.plan_path, resumed, resumed,
                                                    self.repository, self.environment, None)
        # The shared authenticated-state boundary is the only substituted
        # authority here. No SDK execution/projection admission is claimed.
        ready = {"product": "sdk", "component": "python", "phase": "package", "target": "desktop",
                 "buildKey": "sha256:" + "a" * 64}
        state = replace(state, prior_ready_plans={self.SDK: ready},
                        rebased_request={**state.rebased_request, "sdkRuntimeSource": "released-default"})
        selection = load_canonical_json(self.released / "selected-inputs/selection.json")
        originals, raw = {}, {}
        for record in selection["originals"]:
            identity = PhaseInstanceId(**{name: record[name] for name in ("product", "component", "phase", "target")})
            directory = self.released / "selected-inputs" / record["directory"]
            path = directory / "phase-receipt.json"
            originals[identity] = {"stage": directory / "stage", "receiptPath": path,
                                   "receipt": load_canonical_json(path)}
            raw[identity] = path.read_bytes()
        selected = {"handoff": {"originalPhases": originals, "receiptBytes": raw}}
        captured = adapter._capture_sdk_runtime_predecessors(selected, self.scratch / "external-runtime")
        return state, ready, selected, captured

    def materialize(self, state, ready, captured, name="sdk-inputs"):
        destination = self.scratch / name
        result = adapter._materialize_product_predecessors(state, self.SDK, destination,
            ready["buildKey"], self.repository, sdk_runtime_originals=captured)
        return destination, result

    def test_external_runtime_preserves_original_bytes_and_never_substitutes_old_contract(self):
        state, ready, selected, captured = self.inputs()
        before = regular_file_inventory(self.released, allow_empty=True)
        runtime = {identity for identity in selected["handoff"]["originalPhases"] if identity.product == "runtime"}
        self.assertEqual(runtime, set(captured))
        self.assertFalse(any(identity.product == "contract" for identity in captured))
        destination, result = self.materialize(state, ready, captured)
        self.assertEqual(ready, result)
        for identity, original in captured.items():
            directory = destination / "-".join((identity.product, identity.component, identity.phase, identity.target))
            self.assertEqual(selected["handoff"]["receiptBytes"][identity], original["receiptBytes"])
            self.assertEqual(original["receiptBytes"], (directory / "phase-receipt.json").read_bytes())
            self.assertEqual(regular_file_inventory(original["stage"]), regular_file_inventory(directory / "stage"))
        for identity in CONTRACT_PHASES:
            directory = destination / "-".join((identity.product, identity.component, identity.phase, identity.target))
            current = self.original_bytes[identity.phase]
            self.assertNotEqual(selected["handoff"]["receiptBytes"][identity], current)
            self.assertEqual(current, (directory / "phase-receipt.json").read_bytes())
        self.assertEqual({"phase-plan.json", "producer.json", *(
            "-".join((identity.product, identity.component, identity.phase, identity.target))
            for identity in (*CONTRACT_PHASES, *runtime))}, {path.name for path in destination.iterdir()})
        self.assertEqual(before, regular_file_inventory(self.released, allow_empty=True))

    def test_contract_only_scope_keeps_original_contract_without_external_runtime_bodies(self):
        state, ready, _, _ = self.inputs()
        destination = self.scratch / "contract-only"
        with mock.patch.object(adapter, "_restore_product_objects", wraps=adapter._restore_product_objects) as restore:
            result = adapter._materialize_product_predecessors(state, self.SDK, destination,
                ready["buildKey"], self.repository, materialized_scope=CONTRACT_PHASES)
        self.assertEqual(ready, result)
        self.assertEqual(CONTRACT_PHASES, restore.call_args.args[1])
        self.assertEqual({"phase-plan.json", "producer.json", *(
            "-".join((i.product, i.component, i.phase, i.target)) for i in CONTRACT_PHASES)},
            {path.name for path in destination.iterdir()})
        for identity in CONTRACT_PHASES:
            original = destination / f"contract-contract-{identity.phase}-common/phase-receipt.json"
            self.assertEqual(self.original_bytes[identity.phase], original.read_bytes())
        runtime = PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        with self.assertRaisesRegex(ValueError, "original Runtime predecessor"):
            adapter._materialize_product_predecessors(state, self.SDK, self.scratch / "missing-runtime",
                ready["buildKey"], self.repository, materialized_scope=(runtime,))
        self.assertFalse((self.scratch / "missing-runtime").exists())

    def test_missing_external_original_rejects_before_publication(self):
        state, ready, _, captured = self.inputs()
        missing = dict(captured)
        del missing[PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")]
        with self.assertRaisesRegex(ValueError, "original Runtime predecessor"):
            self.materialize(state, ready, missing)
        self.assertFalse((self.scratch / "sdk-inputs").exists())

    def test_changed_captured_receipt_or_stage_rejects_without_output(self):
        state, ready, _, captured = self.inputs()
        original = captured[PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")]
        output = original["stage"] / original["receipt"]["outputs"][0]["relativePath"]
        for label, path in (("receipt", original["receiptPath"]), ("stage", output)):
            raw = path.read_bytes()
            mode = path.stat().st_mode
            try:
                path.chmod(0o600)
                path.write_bytes(raw + b"changed captured original\n")
                with self.subTest(label=label), self.assertRaises(ValueError):
                    self.materialize(state, ready, captured, name=label)
                self.assertFalse((self.scratch / label).exists())
            finally:
                path.write_bytes(raw)
                path.chmod(mode)

    def test_nonexternal_runtime_route_ignores_sdk_original_map(self):
        resumed = self.resume()
        with self.control_seams():
            state = adapter._verified_product_state(self.plan_path, resumed, resumed,
                                                    self.repository, self.environment, None)
        ready = state.prior_ready_plans[JVM]
        destination = self.scratch / "runtime-inputs"
        result = adapter._materialize_product_predecessors(state, JVM, destination, ready["buildKey"], self.repository,
            sdk_runtime_originals={PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64"): {}})
        self.assertEqual(ready, result)
        self.assertEqual({"phase-plan.json", "producer.json", *(
            "-".join((identity.product, identity.component, identity.phase, identity.target))
            for identity in CONTRACT_PHASES)}, {path.name for path in destination.iterdir()})


if __name__ == "__main__":
    unittest.main()
