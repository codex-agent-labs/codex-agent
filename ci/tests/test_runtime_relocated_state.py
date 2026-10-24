"""Real signed resumed-state replay with synthetic cross-checkout control roots.

Only the two producer control-root pairs are changed before transport capture.
Original product bytes, receipts, signatures, planner and authority gates remain
real; this is relocation evidence, not compiler or hosted-runner acceptance.
"""

from pathlib import Path
import shutil
import unittest

from ci.products.inventory import (
    load_canonical_json,
    regular_file_inventory,
    snapshot_regular_tree,
    write_canonical_json,
)
from ci.tests import test_runtime_phase_preparation as fixture


adapter = fixture.adapter
CONTROLS = ("reuse-wave-request.json", "discovery/contract-reuse-request.json")


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class RuntimeRelocatedStateTest(unittest.TestCase):
    setUpClass = classmethod(fixture.RuntimePhasePreparationTest.setUpClass.__func__)
    control_seams = classmethod(fixture.RuntimePhasePreparationTest.control_seams.__func__)
    setUp = fixture.RuntimePhasePreparationTest.setUp
    tearDown = fixture.RuntimePhasePreparationTest.tearDown
    resume = fixture.RuntimePhasePreparationTest.resume
    prepare = fixture.RuntimePhasePreparationTest.prepare

    def captured_state(self, resumed, name, roots, *, nested_roots=None):
        producer = self.scratch / f"{name}-producer"
        shutil.copytree(resumed, producer)
        for relative, pair in zip(CONTROLS, (roots, roots if nested_roots is None else nested_roots)):
            path = producer / relative
            control = load_canonical_json(path)
            control.update(repositoryRoot=pair[0], artifactRoot=pair[1])
            write_canonical_json(path, control)
        # The upload equivalent starts here: no captured original is rewritten.
        original = regular_file_inventory(producer)
        captured = self.scratch / f"{name}-capture"
        snapshot_regular_tree(producer, captured)
        self.assertEqual(original, regular_file_inventory(captured))
        return producer, captured, original

    def advance_contract(self, captured, destination):
        with self.control_seams():
            return adapter.advance_contract(
                self.plan_path,
                captured / "discovery",
                captured / "contract-state",
                [],
                destination,
                self.scratch / f"{destination.name}-outputs",
                repository_root=self.repository,
                environ=self.environment,
            )

    def test_linux_macos_and_windows_controls_prepare_exact_original_closure(self):
        resumed = self.resume()
        resumed_before = regular_file_inventory(resumed)
        roots = (
            ("linux", "/home/runner/work/codex-agent/codex-agent",
             "/home/runner/work/codex-agent/codex-agent/build/product-reuse"),
            ("macos", "/Users/runner/work/codex-agent/codex-agent",
             "/Users/runner/work/codex-agent/codex-agent/build/product-reuse"),
            ("windows", r"D:\a\codex-agent\codex-agent",
             r"D:\a\codex-agent\codex-agent\build\product-reuse"),
        )
        for name, repository, artifacts in roots:
            with self.subTest(producer_platform=name):
                producer, captured, original = self.captured_state(
                    resumed, name, (repository, artifacts),
                )
                destination = self.scratch / f"{name}-worker"
                ready, properties = self.prepare(captured, destination)
                self.assertEqual(
                    (resumed / "phase-plans/runtime-jvm-binary-jvm.json").read_bytes(),
                    (destination / "predecessors/phase-plan.json").read_bytes(),
                )
                self.assertEqual(ready["buildKey"], load_canonical_json(
                    destination / "predecessors/phase-plan.json",
                )["buildKey"])
                for phase, raw in self.original_bytes.items():
                    self.assertEqual(raw, (destination / (
                        f"predecessors/contract-contract-{phase}-common/phase-receipt.json"
                    )).read_bytes())
                self.assertEqual(
                    regular_file_inventory(self.handoff),
                    regular_file_inventory(destination / "contract-input"),
                )
                for field in (
                    "contractPayload", "contractMetadataReceipt", "contractAttestation",
                    "contractAttestationSignature", "contractPublicKey",
                ):
                    path = Path(properties[f"codexAgent.{field}"])
                    self.assertTrue(path.is_relative_to(destination), field)
                    self.assertTrue(path.is_file(), field)
                if name == "windows":
                    result = self.advance_contract(captured, self.scratch / "nested-contract-replay")
                    self.assertTrue(result["fullReuse"])
                self.assertEqual(original, regular_file_inventory(producer))
                self.assertEqual(original, regular_file_inventory(captured))
        self.assertEqual(resumed_before, regular_file_inventory(resumed))

    def test_relocation_derives_only_two_fields_without_rewriting_transport(self):
        resumed = self.resume()
        producer, captured, original = self.captured_state(
            resumed, "memory-only", (r"C:\agent\worktree", r"C:\agent\worktree\build\product-reuse"),
        )
        for relative in CONTROLS:
            with self.subTest(control=relative):
                path = captured / relative
                supplied = load_canonical_json(path)
                expected = {**supplied, "repositoryRoot": str(self.repository),
                            "artifactRoot": str(self.repository / "build/product-reuse")}
                self.assertEqual(expected, adapter._relocated_wave_control(
                    path, "Synthetic original control", self.repository,
                ))
        self.assertEqual(original, regular_file_inventory(producer))
        self.assertEqual(original, regular_file_inventory(captured))

    def test_malformed_original_roots_reject_before_worker_output(self):
        resumed = self.resume()
        invalid = (
            ("relative", "relative/build/product-reuse"),
            ("C:relative", "C:relative/build/product-reuse"),
            ("C:/agent/worktree", "C:/agent/worktree/build/product-reuse"),
            (r"C:\agent/worktree", r"C:\agent/worktree\build\product-reuse"),
            ("/producer/work", "/other/work/build/product-reuse"),
            ("/producer/work", "/producer/work/build/product-reuse/child"),
            ("/producer/../work", "/producer/../work/build/product-reuse"),
            ("/producer//work", "/producer//work/build/product-reuse"),
            (r"C:\producer\work", r"D:\producer\work\build\product-reuse"),
            (r"\\server\share\work", r"\\server\share\work\build\product-reuse"),
            (None, "/producer/work/build/product-reuse"),
            ("/producer/work", 7),
        )
        for index, pair in enumerate(invalid):
            with self.subTest(roots=pair):
                producer, captured, original = self.captured_state(resumed, f"invalid-{index}", pair)
                destination = self.scratch / f"invalid-{index}-worker"
                with self.assertRaises(ValueError):
                    self.prepare(captured, destination)
                self.assertFalse(destination.exists())
                self.assertEqual(original, regular_file_inventory(producer))
                self.assertEqual(original, regular_file_inventory(captured))

    def test_nested_contract_control_cannot_use_an_incoherent_root_pair(self):
        resumed = self.resume()
        valid = ("/producer/work", "/producer/work/build/product-reuse")
        invalid = ("/producer/work", "/another/work/build/product-reuse")
        producer, captured, original = self.captured_state(
            resumed, "invalid-nested", valid, nested_roots=invalid,
        )
        destination = self.scratch / "invalid-nested-replay"
        with self.assertRaises(ValueError):
            self.advance_contract(captured, destination)
        self.assertFalse(destination.exists())
        self.assertEqual(original, regular_file_inventory(producer))
        self.assertEqual(original, regular_file_inventory(captured))


if __name__ == "__main__":
    unittest.main()
