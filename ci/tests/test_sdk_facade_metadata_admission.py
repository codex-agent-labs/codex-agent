"""Concrete routing with real receipts/shards and an explicitly mocked full reader.

No fixture is genuine compiler, hosted execution or full tool-policy evidence.
"""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import unittest
from unittest.mock import patch

from ci.products import sdk_facade_metadata_admission as admission
from ci.products.registry import PhaseInstanceId
from ci.products.restore import PHASE_PLAN_KEYS, finalize_phase_object
from ci.tests import test_sdk_facade_metadata_original as fixtures


class FacadeMetadataAdmissionTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.FacadeMetadataOriginalTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.f.prepare_retained()
        self.root = self.f.root
        self.raw = self.f.receipt_path.read_bytes()
        shard = admission.verify_phase_shard(self.f.retained / "original/shard",
                                            PhaseInstanceId("sdk", "sdk-core", "metadata", "common"))
        self.envelope = {key: shard[key] for key in ("receipt", "receiptBytes", "receiptSha256", "objectSha256")}
        self.records = [{"receiptSha256": self.envelope["receiptSha256"],
                         "captureRoot": self.f.retained.relative_to(self.root).as_posix()}]
        arguments = self.f.f.arguments()
        self.policy = {field: str(arguments[key]) for field, key in admission._PATHS.items()
                       if key in arguments}
        self.policy.update(toolingKeyring=None, toolingKeysDirectory=None, toolingTrustDomain="development",
            contractDigest=arguments["contract_digest"], componentDigests=deepcopy(arguments["component_digests"]),
            originalContext=deepcopy(self.f.context), validations={target: {
                key: str(value) if isinstance(value, Path) else value for key, value in record.items()}
                for target, record in arguments["validations"].items()})
        self.predecessors = []
        for target in admission.SDK_FACADE_TARGETS:
            raw = Path(self.policy["validations"][target]["validationReceipt"]).read_bytes()
            receipt = admission.load_canonical_json_bytes(raw)
            shard = finalize_phase_object(stage_root=self.f.f.f.f.stages[target],
                phase_plan={key: receipt[key] for key in PHASE_PLAN_KEYS}, producer=receipt["producer"],
                product_version=receipt["productVersion"], trust_domain=receipt["trustDomain"],
                destination=Path(self.policy["validations"][target]["captureRoot"]) / "original/shard")
            self.assertEqual(raw, shard["receiptBytes"])
            self.predecessors.append({key: shard[key]
                                     for key in ("receipt", "receiptBytes", "receiptSha256", "objectSha256")})
        self.events = []
        self.mutation = None
        self.reader = self.enterContext(patch.object(fixtures.original, "verified_retained_sdk_facade_metadata",
                                                     side_effect=self.replay))

    def make(self, **changes):
        arguments = dict(repository=self.root, policy_revision="c" * 40, policy=self.policy)
        arguments.update(changes)
        return admission.FacadeMetadataAdmission(self.root, self.records, **arguments)

    def test_fresh_policy_requires_exact_eleven_inputs_but_no_future_context(self):
        fresh = deepcopy(self.policy)
        del fresh["originalContext"]
        arguments = admission.fresh_metadata_arguments(fresh)
        self.assertEqual(set(admission.SDK_FACADE_TARGETS), set(arguments["validations"]))
        self.assertNotIn("original_context", arguments)
        with self.assertRaises(ValueError):
            admission.fresh_metadata_arguments(self.policy)
        del fresh["validations"]["jvm"]
        with self.assertRaises(ValueError):
            admission.fresh_metadata_arguments(fresh)

    @contextmanager
    def replay(self, **arguments):
        self.assertEqual(self.root, arguments["repository_root"])
        self.assertEqual("c" * 40, arguments["policy_revision"])
        self.assertEqual(self.f.retained, arguments["capture_root"])
        self.assertEqual(self.raw, arguments["metadata_receipt_path"].read_bytes())
        self.assertEqual(self.policy["validations"], arguments["validations"])
        self.assertEqual(self.policy["originalContext"], arguments["original_context"])
        self.assertEqual(self.policy["contractDigest"], arguments["contract_digest"])
        self.assertEqual(self.policy["componentDigests"], arguments["component_digests"])
        for field, name in admission._PATHS.items():
            self.assertEqual(None if self.policy[field] is None else Path(self.policy[field]), arguments[name])
        self.assertEqual(self.policy["toolingTrustDomain"], arguments["required_trust_domain"])
        self.assertFalse({"token", "artifact_id", "artifact_sha256", "trusted_workflow_sha"} & set(arguments))
        value = {"receipt": deepcopy(self.envelope["receipt"]), "receiptBytes": self.raw,
            "receiptPath": arguments["metadata_receipt_path"], "capture": self.f.retained,
            "original": self.f.retained / "original",
            "stage": self.root / "build/product-stage/sdk/sdk-core/metadata/common",
            "transport": admission.load_canonical_json_bytes((self.f.retained / "capture-transport.json").read_bytes())}
        self.events.append("enter")
        if self.mutation is not None:
            self.mutation("enter", value, arguments)
        yield value
        if self.mutation is not None:
            self.mutation("exit", value, arguments)
        self.events.append("exit")

    def test_exact_eleven_predecessors_and_explicit_policy_complete_before_return_without_cache(self):
        gate = self.make()
        self.assertIsNone(gate.verify_metadata(self.envelope, self.predecessors))
        self.assertEqual(["enter", "exit"], self.events)
        self.assertIsNone(gate.verify_metadata(self.envelope, self.predecessors))
        self.assertEqual(2, self.reader.call_count)
        self.assertEqual(["enter", "exit", "enter", "exit"], self.events)

    def test_missing_duplicate_wrong_or_changed_selected_predecessors_never_enter_reader(self):
        gate = self.make()
        wrong = deepcopy(self.predecessors)
        wrong[0]["receipt"]["producer"]["commit"] = "d" * 40
        wrong[0]["receiptBytes"] = admission.canonical_json_bytes(wrong[0]["receipt"])
        wrong[0]["receiptSha256"] = fixtures.sha256_bytes(wrong[0]["receiptBytes"])
        for predecessors in ([], self.predecessors[:-1], self.predecessors + self.predecessors[:1], wrong):
            with self.subTest(count=len(predecessors)), self.assertRaises(ValueError):
                gate.verify_metadata(self.envelope, predecessors)
        self.reader.assert_not_called()

    def test_missing_record_and_foreign_metadata_identity_do_not_enter_reader(self):
        self.records.clear()
        gate = self.make()
        with self.assertRaisesRegex(ValueError, "receipt-bound"):
            gate.verify_metadata(self.envelope, self.predecessors)
        with self.assertRaisesRegex(ValueError, "exact metadata"):
            gate.verify_metadata(self.predecessors[0], self.predecessors)
        self.reader.assert_not_called()

    def test_exact_object_digest_and_output_inventory_are_mandatory(self):
        selected = {**self.envelope, "objectSha256": "sha256:" + "e" * 64}
        with self.assertRaisesRegex(ValueError, "object differs"):
            self.make().verify_metadata(selected, self.predecessors)
        content = self.root / "build/product-stage/sdk/sdk-core/metadata/common/outputs/evidence/facade-metadata.json"
        content.write_bytes(b"changed outputs")
        with self.assertRaises(ValueError):
            self.make().verify_metadata(self.envelope, self.predecessors)

    def test_each_predecessor_object_digest_is_bound_to_its_retained_shard(self):
        for index, predecessor in enumerate(self.predecessors):
            changed = deepcopy(self.predecessors)
            changed[index]["objectSha256"] = "sha256:" + "e" * 64
            with self.subTest(target=predecessor["receipt"]["target"]), self.assertRaisesRegex(
                    ValueError, "predecessor object differs"):
                self.make().verify_metadata(self.envelope, changed)
        self.reader.assert_not_called()

    def test_reader_entry_exit_and_late_returned_identity_failures_reject(self):
        for mode in ("enter", "exit", "receipt", "raw", "path"):
            def mutate(phase, value, arguments):
                if phase == mode:
                    raise ValueError("full replay " + mode + " rejected")
                if phase == "exit":
                    if mode == "receipt": value["receipt"]["producer"]["runAttempt"] = 9
                    if mode == "raw": value["receiptBytes"] += b"changed"
                    if mode == "path": value["receiptPath"] = self.root / "foreign.json"
            self.mutation = mutate
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.make().verify_metadata(self.envelope, self.predecessors)

    def test_late_envelope_caller_and_forwarded_policy_mutations_reject(self):
        baseline_policy, baseline_records = deepcopy(self.policy), deepcopy(self.records)
        baseline_envelope, baseline_predecessors = deepcopy(self.envelope), deepcopy(self.predecessors)
        for mode in ("metadata-object", "predecessor", "collection", "policy", "forwarded", "records"):
            self.policy, self.records = deepcopy(baseline_policy), deepcopy(baseline_records)
            self.envelope, self.predecessors = deepcopy(baseline_envelope), deepcopy(baseline_predecessors)
            def mutate(phase, value, arguments):
                if phase != "exit": return
                if mode == "metadata-object": self.envelope["objectSha256"] = "sha256:" + "b" * 64
                elif mode == "predecessor": self.predecessors[0]["objectSha256"] = "sha256:" + "b" * 64
                elif mode == "collection": self.predecessors.pop()
                elif mode == "policy": self.policy["originalContext"]["repositoryRoot"] = "/changed"
                elif mode == "forwarded": arguments["original_context"]["repositoryRoot"] = "/changed"
                else: self.records[0]["captureRoot"] = "changed"
            self.mutation = mutate
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "changed"):
                self.make().verify_metadata(self.envelope, self.predecessors)

    def test_late_capture_or_selected_receipt_file_mutation_rejects(self):
        receipt_path = Path(self.policy["validations"]["jvm"]["validationReceipt"])
        receipt_bytes = receipt_path.read_bytes()
        for mode in ("receipt", "predecessor-capture", "capture"):
            def mutate(phase, value, arguments):
                if phase != "exit": return
                if mode == "receipt": receipt_path.write_bytes(b"changed selected predecessor")
                elif mode == "predecessor-capture":
                    (Path(self.policy["validations"]["jvm"]["captureRoot"]) / "original/gradle.log").write_bytes(
                        b"late predecessor capture mutation")
                else: (self.f.retained / "original/worker/gradle.log").write_bytes(b"late capture mutation")
            self.mutation = mutate
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, "changed"):
                self.make().verify_metadata(self.envelope, self.predecessors)
            receipt_path.write_bytes(receipt_bytes)

    def test_strict_policy_and_confined_records_reject_before_replay(self):
        for mutation in ("extra", "trust", "unpaired", "development-key", "relative", "live"):
            policy = deepcopy(self.policy)
            if mutation == "extra": policy["trusted"] = True
            elif mutation == "trust": policy["toolingTrustDomain"] = "any"
            elif mutation == "unpaired": policy["toolingTrustDomain"] = "release"
            elif mutation == "development-key": policy["toolingKeyring"] = policy["toolingPublicKey"]
            elif mutation == "relative": policy["plan"] = "relative.json"
            else:
                row = policy["validations"]["jvm"]
                del row["captureRoot"]
                row.update(artifactId=1, artifactSha256="sha256:" + "e" * 64)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.make(policy=policy)
        baseline = deepcopy(self.records)
        for path in ("../escape", str(self.f.retained), "./caller-authenticated-metadata-capture"):
            self.records = [{**baseline[0], "captureRoot": path}]
            with self.subTest(path=path), self.assertRaises(ValueError): self.make()
        self.records = baseline * 2
        with self.assertRaises(ValueError): self.make()
        self.reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
