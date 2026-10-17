"""Native carrier collection: real signed K/R, carrier loader and phase shards.

Election and official HTTP are explicit seams. Original SDK source capture and
the full executable projection are mocked as in the existing carrier fixture;
these tests prove transport/pairing, not SDK semantic or hosted acceptance.
"""

from unittest.mock import patch
import unittest

from ci.tests import test_sdk_validation_inputs as evidence_fixture
from ci.tests import test_sdk_worker_collection as transport_fixture
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_resume_capture import archive
from products.inventory import canonical_json_bytes, load_canonical_json, regular_file_inventory, sha256_bytes
from products.receipt import write_output_manifest
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object
import products.sdk_validation as projection
import products.sdk_validation_inputs as evidence


adapter = transport_fixture.adapter


class SdkNativeCollectionTest(unittest.TestCase):
    sources = staticmethod(evidence_fixture.SdkValidationInputsTest.sources)
    proof = staticmethod(evidence_fixture.SdkValidationInputsTest.proof)
    official_api = transport_fixture.SdkWorkerCollectionTest.official_api
    names = transport_fixture.SdkWorkerCollectionTest.names

    @classmethod
    def setUpClass(cls):
        # Build the existing real signed K/R fixture once, without inheriting
        # or rerunning its unrelated test methods.
        evidence_fixture.SdkValidationInputsTest.setUpClass.__func__(cls)

    def setUp(self):
        transport_fixture.SdkWorkerCollectionTest.setUp(self)
        self.plan["validationCommit"] = self.producer["commit"]

    @staticmethod
    def runtime_proof(**arguments):
        # The shared signed-fixture setup uses ci.products, while the standalone
        # collector uses products. Keep its mocked content bytes, but construct
        # the exact class required by this gate; never relax production type checks.
        proof = evidence_fixture.SdkValidationInputsTest.proof(**arguments)
        return projection.VerifiedSdkValidationProjection(proof._receipt, proof._content, projection._VERIFIED)

    def shard(self, component, target, *, different_key=False):
        self.counter += 1
        base = self.repository / f"build/native-original-{self.counter}"
        source = base / "source"
        source.mkdir(parents=True)
        (source / "request.json").write_bytes((self.original / "request.json").read_bytes())
        record = {"component": component, "target": target, "compatibilityRequest": "request.json"}
        for name in ("packageStage", "validationStage", "runtimeStages", "stagedSdks"):
            (source / name / "outputs").mkdir(parents=True)
            (source / name / "outputs/original.log").write_bytes(b"original synthetic SDK bytes\xff\n")
            record[name] = name
        for phase, phase_target in (("package", "desktop"), ("validation", target)):
            manifest = write_output_manifest(source / record[phase + "Stage"], "sdk", component,
                phase, phase_target, "0.2.9", {"evidence": "outputs"})
            receipt_path = source / (phase + "Receipt")
            receipt = write_receipt(receipt_path, product="sdk", component=component, phase=phase,
                target=phase_target, version="0.2.9", version_identity="0.2.9", outputs=manifest["outputs"],
                upstream=[], context={"producer": self.producer},
                **({"toolchain": sha256_bytes(b"different synthetic original key")} if different_key else {}))
            record[phase + "Receipt"] = receipt_path.name
        ready = {name: receipt[name] for name in PHASE_PLAN_KEYS}
        shard = base / "shard"
        finalized = finalize_phase_object(stage_root=source / "validationStage", phase_plan=ready,
            producer=self.producer, product_version="0.2.9", trust_domain="development", destination=shard)
        self.assertEqual((source / "validationReceipt").read_bytes(), finalized["receiptBytes"])
        record["receiptSha256"] = sha256_bytes(finalized["receiptBytes"])
        carrier = base / "carrier"
        with patch.object(evidence, "_capture_validation_sources", self.sources), \
                patch.object(projection, "verify_sdk_validation_projection", side_effect=self.runtime_proof):
            records = evidence.stage_sdk_validation_evidence([record], source, carrier,
                repository=self.repository, policy_revision=self.producer["commit"], tooling=self.tooling)
        self.assertEqual(records, evidence.load_sdk_validation_evidence(carrier))
        files = {"shard/" + row["relativePath"]: (shard / row["relativePath"]).read_bytes()
                 for row in regular_file_inventory(shard)}
        files.update({"sdk-validation-evidence/" + row["relativePath"]: (carrier / row["relativePath"]).read_bytes()
                      for row in regular_file_inventory(carrier, allow_empty=True)})
        files["worker/gradle.log"] = b""
        return PhaseInstanceId("sdk", component, "validation", target), ready, finalized, carrier, files

    def collect(self, ready, uploads, destination, *, proof=None):
        state = transport_fixture.SdkWorkerCollectionTest.state(self, ready)
        state.expected_fixed["versions"]["sdk"] = "0.2.9"
        with patch.object(adapter, "_verified_product_state", return_value=state), \
                self.official_api(ready, uploads), \
                patch.object(evidence, "_capture_validation_sources", self.sources), \
                patch.object(projection, "verify_sdk_validation_projection", side_effect=proof or self.runtime_proof):
            return adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery, destination,
                trusted_workflow_sha=transport_fixture.PIN, repository_root=self.repository,
                environ=self.environment, token="synthetic-token", sdk_family="native-validation",
                sdk_validation_tooling=self.tooling)

    def test_exact_original_shard_and_single_full_carrier_are_retained_separately(self):
        instance, ready, finalized, carrier, files = self.shard("rust", "linux-x64")
        before = regular_file_inventory(carrier, allow_empty=True)
        destination = self.repository / "build/collected"
        raw = archive(files)
        result = self.collect({instance: ready}, {instance: raw}, destination)
        self.assertEqual(result, load_canonical_json(destination / "collection.json"))
        row = result["rows"][0]
        self.assertEqual("success", row["result"])
        self.assertEqual(finalized["receiptBytes"], (destination / row["shardDirectory"] / "phase-receipt.json").read_bytes())
        admitted = destination / row["sdkValidationEvidenceDirectory"]
        original = destination / row["originalDirectory"]
        self.assertEqual(original.parent / "sdk-validation-evidence", admitted)
        self.assertFalse(admitted.is_relative_to(original))
        self.assertEqual(before, regular_file_inventory(admitted, allow_empty=True))
        self.assertEqual(before, regular_file_inventory(carrier, allow_empty=True))
        self.assertEqual(raw, (original.parent / "transport.zip").read_bytes())
        records = evidence.load_sdk_validation_evidence(admitted)
        self.assertEqual(1, len(records))
        self.assertEqual((instance.component, instance.target, sha256_bytes(finalized["receiptBytes"])),
            (records[0]["component"], records[0]["target"], records[0]["receiptSha256"]))
        self.assertEqual(b"", (original / "worker/gradle.log").read_bytes())

    def test_missing_wrong_or_extra_carriers_fail_only_the_affected_sibling(self):
        bad = self.shard("rust", "linux-x64")
        good = self.shard("python", "windows-x64")
        alternate = self.shard("rust", "linux-x64", different_key=True)
        wrong_target = self.shard("rust", "macos-arm64")
        before = {item[3]: regular_file_inventory(item[3], allow_empty=True)
                  for item in (bad, good, alternate, wrong_target)}
        request = "sdk-validation-evidence/" + evidence.REQUEST_NAME
        for failure in ("missing", "empty", "component", "target", "receipt", "extra"):
            files = {name: raw for name, raw in bad[4].items() if not name.startswith("sdk-validation-evidence/")}
            if failure == "empty":
                files[request] = canonical_json_bytes([])
            elif failure in ("component", "target", "receipt"):
                selected = {"component": good, "target": wrong_target, "receipt": alternate}[failure]
                files.update({name: raw for name, raw in selected[4].items() if name.startswith("sdk-validation-evidence/")})
            elif failure == "extra":
                for item in (bad, good):
                    files.update({name: raw for name, raw in item[4].items() if name.startswith("sdk-validation-evidence/")})
                combined = [*evidence.load_sdk_validation_evidence(bad[3]), *evidence.load_sdk_validation_evidence(good[3])]
                files[request] = canonical_json_bytes(sorted(combined, key=lambda row: row["receiptSha256"]))
            destination = self.repository / f"build/failure-{failure}"
            with self.subTest(failure=failure):
                result = self.collect({bad[0]: bad[1], good[0]: good[1]},
                    {bad[0]: archive(files), good[0]: archive(good[4])}, destination)
                rows = {adapter._identity(row): row for row in result["rows"]}
                self.assertEqual("failure", rows[bad[0]]["result"])
                self.assertTrue(rows[bad[0]]["reason"])
                self.assertIsNone(rows[bad[0]]["shardDirectory"])
                self.assertIsNone(rows[bad[0]].get("sdkValidationEvidenceDirectory"))
                self.assertIsNotNone(rows[bad[0]]["originalDirectory"])
                if failure != "missing":
                    self.assertIn("differs from its elected original shard", rows[bad[0]]["reason"])
                self.assertEqual("success", rows[good[0]]["result"])
                self.assertEqual(good[2]["receiptBytes"],
                    (destination / rows[good[0]]["shardDirectory"] / "phase-receipt.json").read_bytes())
        for path, inventory in before.items():
            self.assertEqual(inventory, regular_file_inventory(path, allow_empty=True))

    def test_full_projection_rejection_is_a_row_failure_after_exact_record_pairing(self):
        bad = self.shard("rust", "linux-x64")
        good = self.shard("python", "windows-x64")
        calls = []
        def proof(**arguments):
            calls.append((arguments["component"], arguments["target"]))
            if arguments["component"] == "rust":
                raise ValueError("synthetic full SDK projection rejection")
            return self.runtime_proof(**arguments)
        destination = self.repository / "build/full-gate-rejection"
        result = self.collect({bad[0]: bad[1], good[0]: good[1]},
            {bad[0]: archive(bad[4]), good[0]: archive(good[4])}, destination, proof=proof)
        rows = {adapter._identity(row): row for row in result["rows"]}
        self.assertEqual({("rust", "linux-x64"), ("python", "windows-x64")}, set(calls))
        self.assertEqual("failure", rows[bad[0]]["result"])
        self.assertIn("synthetic full SDK projection rejection", rows[bad[0]]["reason"])
        self.assertIsNone(rows[bad[0]].get("sdkValidationEvidenceDirectory"))
        self.assertEqual("success", rows[good[0]]["result"])
        self.assertIsNotNone(rows[good[0]]["sdkValidationEvidenceDirectory"])


if __name__ == "__main__":
    unittest.main()
