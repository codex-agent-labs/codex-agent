"""Prepare exact authenticated inputs for an elected Runtime worker phase."""

from pathlib import Path
import shutil
import unittest
from unittest import mock

from ci.products.contract_attestation import build_contract_attestation
from ci.products.inventory import (
    load_canonical_json,
    publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory,
    write_canonical_json,
)
from ci.products.signatures import generate_development_key
from ci.tests import test_runtime_resumed_phase as fixture


adapter = fixture.adapter
JVM = fixture.JVM
PhaseInstanceId = adapter.PhaseInstanceId
CONTRACT_PHASES = tuple(sorted(
    PhaseInstanceId("contract", "contract", phase, "common")
    for phase in ("binary", "package", "validation", "metadata")
))


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class RuntimePhasePreparationTest(unittest.TestCase):
    # Delegate the real resumed-state fixture without collecting its tests.
    setUpClass = classmethod(fixture.RuntimeResumedPhaseTest.setUpClass.__func__)
    control_seams = classmethod(fixture.RuntimeResumedPhaseTest.control_seams.__func__)
    setUp = fixture.RuntimeResumedPhaseTest.setUp
    tearDown = fixture.RuntimeResumedPhaseTest.tearDown
    resume = fixture.RuntimeResumedPhaseTest.resume

    def prepare(self, resumed: Path, destination: Path, *, build_key: str | None = None):
        ready = load_canonical_json(resumed / "phase-plans/runtime-jvm-binary-jvm.json")
        with self.control_seams():
            properties = adapter.prepare_runtime_phase(
                self.plan_path,
                resumed,
                resumed,
                JVM,
                destination,
                expected_build_key=ready["buildKey"] if build_key is None else build_key,
                repository_root=self.repository,
                environ=self.environment,
            )
        return ready, properties

    def test_jvm_binary_prepares_exact_contract_handoff_and_final_properties(self):
        resumed = self.resume()
        original = regular_file_inventory(resumed)
        destination = self.scratch / "runtime-worker"

        ready, properties = self.prepare(resumed, destination)

        self.assertEqual(properties, load_canonical_json(destination / "gradle-properties.json"))
        self.assertEqual(
            (resumed / "phase-plans/runtime-jvm-binary-jvm.json").read_bytes(),
            (destination / "predecessors/phase-plan.json").read_bytes(),
        )
        self.assertEqual(
            (resumed / "producer.json").read_bytes(),
            (destination / "predecessors/producer.json").read_bytes(),
        )
        for dependency in CONTRACT_PHASES:
            name = "-".join((
                dependency.product,
                dependency.component,
                dependency.phase,
                dependency.target,
            ))
            self.assertEqual(
                self.original_bytes[dependency.phase],
                (destination / f"predecessors/{name}/phase-receipt.json").read_bytes(),
            )

        handoff = destination / "contract-input"
        self.assertEqual(
            regular_file_inventory(self.handoff),
            regular_file_inventory(handoff),
        )
        metadata_receipt = destination / (
            "predecessors/contract-contract-metadata-common/phase-receipt.json"
        )
        metadata = load_canonical_json(metadata_receipt)
        stem = f"codex-agent-contract-{metadata['productVersion']}"
        adapter.verify_contract_attestation(
            handoff / f"{stem}.zip",
            metadata_receipt,
            handoff / f"{stem}.attestation.json",
            handoff / f"{stem}.attestation.sig",
            handoff / "public-key.pub",
            required_trust_domain="release",
            keyring=self.repository / "gradle/release/product-signing-keys.json",
            keys_directory=self.repository / "gradle/release/keys",
        )
        expected = {
            "codexAgent.product": JVM.product,
            "codexAgent.component": JVM.component,
            "codexAgent.phase": JVM.phase,
            "codexAgent.target": JVM.target,
            "codexAgent.contractVersion": metadata["productVersion"],
            "codexAgent.runtimeVersion": adapter._versions(
                self.repository, self.commit,
            )["runtime-release"],
            "codexAgent.candidateCommit": self.producer["commit"],
            "codexAgent.candidateTree": self.producer["tree"],
            "codexAgent.contractPayload": str(destination / f"contract-input/{stem}.zip"),
            "codexAgent.contractMetadataReceipt": str(metadata_receipt),
            "codexAgent.contractAttestation": str(
                destination / f"contract-input/{stem}.attestation.json"
            ),
            "codexAgent.contractAttestationSignature": str(
                destination / f"contract-input/{stem}.attestation.sig"
            ),
            "codexAgent.contractPublicKey": str(destination / "contract-input/public-key.pub"),
        }
        self.assertEqual(expected, properties)
        self.assertEqual(
            {"contract-input", "gradle-properties.json", "predecessors", "trust"},
            {path.name for path in destination.iterdir()},
        )
        tracked_keyring = self.repository / "gradle/release/product-signing-keys.json"
        retained_keyring = destination / "trust/product-signing-keys.json"
        self.assertEqual(tracked_keyring.read_bytes(), retained_keyring.read_bytes())
        key_id = load_canonical_json(tracked_keyring)["activeKey"]["keyId"]
        self.assertEqual(
            (self.repository / f"gradle/release/keys/{key_id}.pub").read_bytes(),
            (destination / f"trust/keys/{key_id}.pub").read_bytes(),
        )
        self.assertEqual(
            {"product-signing-keys.json", f"keys/{key_id}.pub"},
            {
                record["relativePath"]
                for record in regular_file_inventory(destination / "trust")
            },
        )
        self.assertEqual(original, regular_file_inventory(resumed))

    def test_wrong_elected_key_rejects_without_output_or_input_mutation(self):
        resumed = self.resume()
        original = regular_file_inventory(resumed)
        destination = self.scratch / "wrong-key"

        with self.assertRaisesRegex(ValueError, "not ready"):
            self.prepare(resumed, destination, build_key="sha256:" + "0" * 64)

        self.assertFalse(destination.exists())
        self.assertEqual(original, regular_file_inventory(resumed))

    def test_changed_original_contract_handoff_rejects_without_output(self):
        resumed = self.resume()
        changed = self.scratch / "changed-state"
        shutil.copytree(resumed, changed)
        signature = next(
            (changed / "authenticated-contract/contract-input").glob("*.attestation.sig")
        )
        signature.write_bytes(signature.read_bytes() + b"changed")
        changed_inventory = regular_file_inventory(changed)
        destination = self.scratch / "changed-contract"

        with self.assertRaises(ValueError):
            self.prepare(changed, destination)

        self.assertFalse(destination.exists())
        self.assertEqual(changed_inventory, regular_file_inventory(changed))

    def test_late_worker_predecessor_mutation_cannot_publish(self):
        resumed = self.resume()
        original = regular_file_inventory(resumed)
        destination = self.scratch / "late-worker"
        mutated = False

        def mutate_before_copy(source, output, **kwargs):
            nonlocal mutated
            phase_plan = Path(source) / "predecessors/phase-plan.json"
            if (Path(source) / "gradle-properties.json").exists() and phase_plan.exists():
                phase_plan.write_bytes(b"changed after verification")
                mutated = True
            return actual_publish_regular_tree(source, output, **kwargs)

        with mock.patch.object(adapter, "publish_regular_tree", side_effect=mutate_before_copy):
            try:
                with self.assertRaisesRegex(ValueError, "pinned inventory"):
                    self.prepare(resumed, destination)
            finally:
                self.assertTrue(mutated)
        self.assertFalse(destination.exists())
        self.assertEqual(original, regular_file_inventory(resumed))

    def test_post_replay_valid_signer_swap_rejects_against_captured_git_policy(self):
        resumed = self.resume()
        changed = self.scratch / "policy-swap-state"
        shutil.copytree(resumed, changed)
        original_handoff = changed / "authenticated-contract/contract-input"
        metadata = load_canonical_json(
            original_handoff / "execution-closure/receipts/metadata.json"
        )
        stem = f"codex-agent-contract-{metadata['productVersion']}"

        private, public, development = generate_development_key(
            self.scratch / "policy-b-signing"
        )
        signing = {
            **development,
            "trustDomain": "release",
            "keyId": "fixture-policy-b",
        }
        policy = self.scratch / "policy-b"
        keys = policy / "keys"
        keys.mkdir(parents=True)
        shutil.copyfile(public, keys / "fixture-policy-b.pub")
        keyring = policy / "product-signing-keys.json"
        write_canonical_json(keyring, {
            "schemaVersion": 1,
            "algorithm": signing["algorithm"],
            "namespace": signing["namespace"],
            "trustDomain": "release",
            "activeKey": {
                "keyId": signing["keyId"],
                "fingerprint": signing["fingerprint"],
            },
            "retiredKeys": [],
        })
        replacement = self.scratch / "policy-b-handoff"
        build_contract_attestation(
            original_handoff / f"{stem}.zip",
            original_handoff / "execution-closure/receipts/metadata.json",
            signing,
            private,
            public,
            replacement,
            execution_closure=original_handoff / "execution-closure",
            keyring=keyring,
            keys_directory=keys,
            complete_handoff=True,
        )

        restore = adapter._materialize_product_predecessors
        swapped_inventory = []

        def restore_then_swap(state, *arguments, **keywords):
            ready = restore(state, *arguments, **keywords)
            evidence = state.rebased_request["contractEvidence"]
            for field, source in (
                ("attestation", replacement / f"{stem}.attestation.json"),
                ("attestationSignature", replacement / f"{stem}.attestation.sig"),
                ("publicKey", replacement / "public-key.pub"),
            ):
                (self.repository / evidence[field]).write_bytes(source.read_bytes())
            target_keyring = self.repository / evidence["keyring"]
            target_keyring.write_bytes(keyring.read_bytes())
            target_keys = self.repository / evidence["keysDirectory"]
            shutil.rmtree(target_keys)
            shutil.copytree(keys, target_keys)
            swapped_inventory.append(regular_file_inventory(changed))
            return ready

        destination = self.scratch / "policy-swap-worker"
        with mock.patch.object(
            adapter,
            "_materialize_product_predecessors",
            side_effect=restore_then_swap,
        ):
            with self.assertRaises(ValueError):
                self.prepare(changed, destination)

        self.assertFalse(destination.exists())
        self.assertEqual(1, len(swapped_inventory))
        self.assertEqual(swapped_inventory[0], regular_file_inventory(changed))


if __name__ == "__main__":
    unittest.main()
