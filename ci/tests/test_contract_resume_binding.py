"""Signed synthetic Contract/state binding, not hosted or full-wave acceptance."""

import copy
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest import mock

from ci.tests import test_contract_release_capture as release_fixture
from ci import product_reuse
from ci.tests.test_contract_execution_closure import execution_closure_fixture
from ci.tests.test_contract_bundle import VERSION
from products.contract_attestation import (
    build_contract_attestation, capture_contract_execution_closure, verify_contract_attestation,
)
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes
from products.registry import PhaseInstanceId
from products.restore import PHASE_SHARD_NAME, verify_phase_shard, write_carrier


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class ContractResumeBindingTest(unittest.TestCase):
    def setUp(self):
        # Construct original signed-source fixtures only; do not inherit their
        # test methods or replace any carrier/object/attestation admission.
        release_fixture.ContractReleaseCaptureTest.setUp(self)
        self.state = self.repository_root / "completed-contract"
        self.state.mkdir()
        tree = subprocess.run(
            ("git", "rev-parse", "HEAD^{tree}"), cwd=self.repository_root,
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        self.plan = {
            "repository": self.producer["repository"], "event": "pull_request", "pullRequest": 31,
            "validationCommit": self.source_sha, "validationTree": tree, "remoteBuildAuthorized": True,
        }
        self.consumer_environment = {"GITHUB_RUN_ID": "901", "GITHUB_RUN_ATTEMPT": "3"}
        self.consumer = product_reuse._consumer(self.plan, self.consumer_environment)
        self.plan_path = self.repository_root / "impact-plan.json"
        self.plan_path.write_bytes(canonical_json_bytes(self.plan))
        instances = tuple(sorted(PhaseInstanceId("contract", "contract", phase, "common")
                                 for phase in self.receipts))
        phases, carrier_phases, sources = [], [], {}
        self.descriptors = {}
        for instance in instances:
            shard = self.shards[instance.phase]
            descriptor = verify_phase_shard(shard, instance)
            self.descriptors[instance.phase] = descriptor
            self.assertEqual(self.receipts[instance.phase].read_bytes(), descriptor["receiptBytes"])
            sources[instance] = shard / descriptor["objectPath"]
            phases.append({
                **product_reuse._identity_record(instance),
                **{name: descriptor[name] for name in ("buildKey", "receiptSha256", "objectSha256")},
                "state": "retained", "source": None, "transportSource": None, "misses": [],
            })
            carrier_phases.append({
                **phases[-1], "state": "reused", "source": "phase-shard",
                "transportSource": {
                    "kind": "phase-shard",
                    "descriptorSha256": sha256_bytes((shard / PHASE_SHARD_NAME).read_bytes()),
                    "producer": descriptor["receipt"]["producer"],
                },
                "misses": [{"source": source, "reason": "fixture-miss"}
                           for source in product_reuse.SOURCES],
            })
        resolution = {"schemaVersion": 1, "result": "complete", "fullReuse": True,
                      "phases": phases, "matrices": {"contract": [], "runtime": [], "sdk": []}}
        write_carrier(self.state / "carrier", {**resolution, "phases": carrier_phases},
                      instances, sources, self.consumer)
        (self.state / "producer.json").write_bytes(canonical_json_bytes(self.consumer["producer"]))
        (self.state / "contract-reuse-result.json").write_bytes(canonical_json_bytes({
            **resolution, "continuationRequirements": [],
        }))
        self.handoff = self.repository_root / "original-release-handoff"
        self.sign_handoff(self.payload, self.receipts, self.capture_root / "execution-closure", self.handoff)
        self.destination = self.repository_root / "bound-contract"

    def sign_handoff(self, payload, receipts, closure, destination):
        build_contract_attestation(
            payload, receipts["metadata"], self.signing, self.private_key, self.public_key,
            destination, execution_closure=closure, keyring=self.keyring,
            keys_directory=self.keys, complete_handoff=True,
        )

    def capture(self, handoff=None, destination=None, environment=None):
        # Impact authorization is outside this seam. Every original carrier,
        # restored object, Git public policy and full signature is real.
        with mock.patch.object(product_reuse, "_validate_plan", return_value=copy.deepcopy(self.plan)):
            return product_reuse._capture_completed_contract_handoff(
                self.plan_path, self.state, self.handoff if handoff is None else handoff,
                self.destination if destination is None else destination,
                repository_root=self.repository_root,
                environ=self.consumer_environment if environment is None else environment,
            )

    def test_binds_exact_original_carrier_and_preserves_complete_release_handoff(self):
        originals = regular_file_inventory(self.source, allow_empty=True)
        state = regular_file_inventory(self.state)
        handoff = regular_file_inventory(self.handoff)
        evidence = self.capture()
        self.assertEqual({"attestation", "attestationSignature", "publicKey", "expectedTrustDomain",
                          "keyring", "keysDirectory"}, set(evidence))
        self.assertEqual("release", evidence["expectedTrustDomain"])
        for field in set(evidence) - {"expectedTrustDomain"}:
            path = Path(evidence[field])
            self.assertFalse(path.is_absolute())
            self.assertNotIn("..", path.parts)
            self.assertTrue((self.destination / path).exists())
        captured = self.destination / "contract-input"
        self.assertEqual(10, len(handoff))
        self.assertEqual(handoff, regular_file_inventory(captured))
        self.assertEqual({"contract-input", "trust"}, {path.name for path in self.destination.iterdir()})
        self.assertEqual({"product-signing-keys.json", f"keys/{self.signing['keyId']}.pub"},
                         {record["relativePath"] for record in regular_file_inventory(self.destination / "trust")})
        stem = f"codex-agent-contract-{VERSION}"
        verify_contract_attestation(
            captured / f"{stem}.zip", captured / "execution-closure/receipts/metadata.json",
            self.destination / evidence["attestation"], self.destination / evidence["attestationSignature"],
            self.destination / evidence["publicKey"], required_trust_domain="release",
            keyring=self.destination / evidence["keyring"], keys_directory=self.destination / evidence["keysDirectory"],
        )
        for phase, original in self.receipts.items():
            self.assertEqual(original.read_bytes(), (captured / f"execution-closure/receipts/{phase}.json").read_bytes())
        self.assertNotEqual(self.consumer["producer"], self.producer)
        self.assertEqual(originals, regular_file_inventory(self.source, allow_empty=True))
        self.assertEqual(state, regular_file_inventory(self.state))
        self.assertEqual(handoff, regular_file_inventory(self.handoff))

    def test_valid_signed_same_payload_from_another_original_execution_is_not_current_state(self):
        other_source = self.root / "other-source"
        payload, receipts, archive = execution_closure_fixture(
            other_source, "different-original-run", producer={**self.producer, "runId": 72},
        )
        self.assertEqual(self.payload.read_bytes(), payload.read_bytes())
        self.assertNotEqual(self.receipts["binary"].read_bytes(), receipts["binary"].read_bytes())
        closure = self.root / "other-closure"
        capture_contract_execution_closure(payload, receipts, archive, closure)
        other = self.repository_root / "other-valid-release"
        # This really signs and fully verifies the alternate closure before the
        # state-binding negative; signature failure cannot explain rejection.
        self.sign_handoff(payload, receipts, closure, other)
        before = regular_file_inventory(other)
        with self.assertRaises(ValueError):
            self.capture(handoff=other)
        self.assertFalse(self.destination.exists())
        self.assertEqual(before, regular_file_inventory(other))

    def test_missing_tampered_or_extra_original_handoff_members_never_publish(self):
        cases = (("missing", "execution-closure/receipts/package.json"),
                 ("tampered", "execution-closure/execution/contract-execution.zip"),
                 ("tampered", f"codex-agent-contract-{VERSION}.zip"),
                 ("extra", "caller-policy.json"))
        for index, (operation, relative) in enumerate(cases):
            with self.subTest(operation=operation, relative=relative):
                bad = self.repository_root / f"bad-handoff-{index}"
                shutil.copytree(self.handoff, bad)
                path = bad / relative
                if operation == "missing":
                    path.unlink()
                elif operation == "extra":
                    path.write_bytes(b"{}\n")
                else:
                    path.write_bytes(path.read_bytes() + b"tampered")
                before = regular_file_inventory(bad)
                with self.assertRaises(ValueError):
                    self.capture(handoff=bad)
                self.assertFalse(self.destination.exists())
                self.assertEqual(before, regular_file_inventory(bad))

    def test_wrong_consumer_or_corrupt_original_carrier_cannot_authorize_release_handoff(self):
        with self.assertRaises(ValueError):
            self.capture(environment={**self.consumer_environment, "GITHUB_RUN_ATTEMPT": "4"})
        self.assertFalse(self.destination.exists())
        descriptor = self.descriptors["binary"]
        original = self.state / "carrier" / descriptor["objectPath"]
        raw = original.read_bytes()
        original.write_bytes(raw + b"changed-original-object")
        try:
            with self.assertRaises(ValueError):
                self.capture()
            self.assertFalse(self.destination.exists())
        finally:
            original.write_bytes(raw)

    def test_existing_or_overlapping_destination_preserves_originals(self):
        self.destination.mkdir()
        sentinel = self.destination / "sentinel"
        sentinel.write_bytes(b"keep original output")
        with self.assertRaises(ValueError):
            self.capture()
        self.assertEqual(b"keep original output", sentinel.read_bytes())
        for source in (self.state, self.handoff):
            before = regular_file_inventory(source)
            with self.subTest(source=source.name), self.assertRaises(ValueError):
                self.capture(destination=source / "overlapping-output")
            self.assertFalse((source / "overlapping-output").exists())
            self.assertEqual(before, regular_file_inventory(source))
