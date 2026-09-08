"""Materialize authenticated predecessors for an elected product phase."""

from pathlib import Path
import shutil
import unittest
from unittest import mock

from ci.products.inventory import load_canonical_json, regular_file_inventory
from ci.products.receipt import verify_output_manifest_identity
from ci.tests import test_runtime_resumed_phase as fixture


adapter = fixture.adapter
JVM = fixture.JVM
PhaseInstanceId = adapter.PhaseInstanceId
CONTRACT_METADATA = PhaseInstanceId("contract", "contract", "metadata", "common")
CONTRACT_PHASES = tuple(sorted(
    PhaseInstanceId("contract", "contract", phase, "common")
    for phase in ("binary", "package", "validation", "metadata")
))


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
        carrier = load_canonical_json(changed / "reused-carrier/carrier.json")
        record = next(
            value for value in carrier["objects"]
            if adapter._identity(value) == CONTRACT_METADATA
        )
        archive = changed / "reused-carrier" / adapter.object_relative_path(
            record["buildKey"], record["receiptSha256"],
        )
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


if __name__ == "__main__":
    unittest.main()
