"""Native carrier collection: real signed K/R, carrier loader and phase shards.

Election and official HTTP are explicit seams. Original SDK source capture and
the full executable projection are mocked as in the existing carrier fixture;
these tests prove transport/pairing, not SDK semantic or hosted acceptance.
"""

from unittest.mock import patch
import subprocess
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
        self.predecessors = {}

    @staticmethod
    def runtime_proof(**arguments):
        # The shared signed-fixture setup uses ci.products, while the standalone
        # collector uses products. Keep its mocked content bytes, but construct
        # the exact class required by this gate; never relax production type checks.
        proof = evidence_fixture.SdkValidationInputsTest.proof(**arguments)
        return projection.VerifiedSdkValidationProjection(proof._receipt, proof._content, projection._VERIFIED)

    def shard(self, component, target, *, different_key=False, binary_producer=None):
        self.counter += 1
        base = self.repository / f"build/native-original-{self.counter}"
        source = base / "source"
        source.mkdir(parents=True)
        (source / "request.json").write_bytes((self.original / "request.json").read_bytes())
        record = {"component": component, "target": target, "compatibilityRequest": "request.json"}
        for name in ("packageStage", "validationStage", "runtimeStages", "stagedSdks", "runtimeAuthorization",
                     *(("binaryStage",) if component == "csharp" else ())):
            (source / name / "outputs").mkdir(parents=True)
            (source / name / "outputs/original.log").write_bytes(b"original synthetic SDK bytes\xff\n")
            record[name] = name
        for phase, phase_target in (*(( ("binary", "desktop"),) if component == "csharp" else ()),
                                    ("package", "desktop"), ("validation", target)):
            manifest = write_output_manifest(source / record[phase + "Stage"], "sdk", component,
                phase, phase_target, "0.2.9", {"evidence": "outputs"})
            receipt_path = source / (phase + "Receipt")
            receipt = write_receipt(receipt_path, product="sdk", component=component, phase=phase,
                target=phase_target, version="0.2.9", version_identity="0.2.9", outputs=manifest["outputs"],
                upstream=[], context={"producer": binary_producer if phase == "binary" and binary_producer else self.producer},
                **({"toolchain": sha256_bytes(b"different synthetic original key")} if different_key else {}))
            record[phase + "Receipt"] = receipt_path.name
            if phase != "validation":
                self.predecessors[PhaseInstanceId("sdk", component, phase, phase_target)] = {
                    **{name: receipt[name] for name in ("product", "component", "phase", "target", "buildKey")},
                    "receiptSha256": sha256_bytes(receipt_path.read_bytes()),
                }
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

    def collect(self, ready, uploads, destination, *, proof=None, ensure_source=None):
        state = transport_fixture.SdkWorkerCollectionTest.state(self, ready)
        state.expected_fixed["versions"]["sdk"] = "0.2.9"
        state.prior_carrier_phases = self.predecessors
        with patch.object(adapter, "_verified_product_state", return_value=state), \
                patch("sdk_handoff._ensure_observed_sdk_commit", side_effect=ensure_source), \
                self.official_api(ready, uploads), \
                patch.object(evidence, "_capture_validation_sources", self.sources), \
                patch.object(projection, "verify_sdk_validation_projection", side_effect=proof or self.runtime_proof):
            return adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery, destination,
                trusted_workflow_sha=transport_fixture.PIN, repository_root=self.repository,
                environ=self.environment, token="synthetic-token", sdk_family="native-validation",
                sdk_validation_tooling=self.tooling)

    def test_exact_original_shard_and_single_full_carrier_are_retained_separately(self):
        instance, ready, finalized, carrier, files = self.shard("rust", "linux-x64")
        files["inputs/unused-predecessor"] = b"original input, not consumed during collection"
        files["prepared-upload/transport.zip"] = b"original preparation, not consumed during collection"
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
        self.assertEqual(destination / "sdk-validation-evidence", admitted)
        self.assertFalse(admitted.is_relative_to(original))
        self.assertEqual(before, regular_file_inventory(carrier, allow_empty=True))
        self.assertFalse((original.parent / "transport.zip").exists())
        self.assertFalse((original / "inputs").exists())
        self.assertFalse((original / "prepared-upload").exists())
        self.assertFalse((original / "sdk-validation-evidence").exists())
        inventory = load_canonical_json(original.parent / "original-inventory.json")["files"]
        self.assertEqual(set(files), {record["relativePath"] for record in inventory})
        for record in inventory:
            self.assertEqual(len(files[record["relativePath"]]), record["bytes"])
            self.assertEqual(sha256_bytes(files[record["relativePath"]]), record["sha256"])
        records = evidence.load_sdk_validation_evidence(admitted)
        self.assertEqual(1, len(records))
        original_record = evidence.load_sdk_validation_evidence(carrier)[0]
        for name in evidence._record_paths(records[0])[0]:
            self.assertEqual(regular_file_inventory(carrier / original_record[name]),
                             regular_file_inventory(admitted / records[0][name]))
        for name in evidence._record_paths(records[0])[1]:
            self.assertEqual((carrier / original_record[name]).read_bytes(),
                             (admitted / records[0][name]).read_bytes())
        self.assertEqual((instance.component, instance.target, sha256_bytes(finalized["receiptBytes"])),
            (records[0]["component"], records[0]["target"], records[0]["receiptSha256"]))
        self.assertEqual(b"", (original / "worker/gradle.log").read_bytes())

    def test_cross_run_native_original_requires_fresh_job_and_exact_receipt_object(self):
        instance, ready, finalized, _, files = self.shard("rust", "linux-x64")
        raw = archive(files)
        original = dict(self.producer)
        job_name, artifact_name = self.names(instance, ready["buildKey"])
        self.producer = {**original, "runId": 8, "runAttempt": 1, "commit": "d" * 40, "tree": "e" * 40}
        self.environment.update(GITHUB_RUN_ID="8", GITHUB_RUN_ATTEMPT="1")
        origin = {"producer": original, "artifact_id": 901, "artifact_sha256": sha256_bytes(raw),
            "receipt_sha256": finalized["receiptSha256"], "object_sha256": finalized["objectSha256"],
            "job_id": 901, "workflow_sha": "f" * 40,
            "workflow_path": ".github/workflows/product-validation.yml", "job_name": job_name}
        original_job = {"id": 901, "name": f"{job_name} ({ready['buildKey']}, ..."[:118] + "...",
            "run_id": original["runId"], "head_sha": original["commit"], "status": "completed", "conclusion": "success",
            "started_at": "2026-09-08T10:00:00Z", "completed_at": "2026-09-08T10:10:00Z"}
        observe = adapter._observe_ci_producer_jobs
        def observed(producers, **kwargs):
            if "worker" not in producers:
                return observe(producers, **kwargs)
            self.assertEqual(original, producers["worker"])
            self.assertEqual(origin["workflow_sha"], kwargs["trusted_workflow_sha"])
            self.assertEqual({"worker": ready["buildKey"]}, kwargs["build_keys_by_phase"])
            return [{"run": {"head_sha": original["commit"]}, "jobs": [original_job]}]
        state = transport_fixture.SdkWorkerCollectionTest.state(self, {instance: ready})
        state.expected_fixed["versions"]["sdk"] = "0.2.9"
        state.prior_carrier_phases = self.predecessors
        destination = self.repository / "build/cross-run-native"
        with adapter.verification_session(), \
                patch.object(adapter, "_verified_product_state", return_value=state), \
                self.official_api({instance: ready}, {instance: raw}) as (query, listing, downloaded), \
                patch("sdk_campaign_original_locator.retained_core_origin", return_value=origin), \
                patch.object(adapter, "_observe_ci_producer_jobs", side_effect=observed), \
                patch("sdk_handoff._ensure_observed_sdk_commit") as source, \
                patch.object(evidence, "_capture_validation_sources", self.sources), \
                patch.object(projection, "verify_sdk_validation_projection", side_effect=self.runtime_proof):
            original_query, original_listing = query.side_effect, listing.side_effect
            def metadata(url, token):
                value = original_query(url, token)
                if "/actions/artifacts/" in url:
                    return {**value, "name": artifact_name,
                        "workflow_run": {"id": original["runId"], "head_sha": original["commit"]}}
                return value
            query.side_effect = metadata
            listing.side_effect = lambda url, field, token: [] if field == "artifacts" else original_listing(url, field, token)
            def collect(path):
                return adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery, path,
                    trusted_workflow_sha=transport_fixture.PIN, repository_root=self.repository,
                    environ=self.environment, token="synthetic-token", sdk_family="native-validation",
                    sdk_validation_tooling=self.tooling)
            result = collect(destination)
            row, = result["rows"]
            self.assertEqual("success", row["result"], row["reason"])
            source.assert_called_once_with(self.repository, original, "synthetic-token")
            downloaded.assert_called_once()
            shard = destination / row["shardDirectory"]
            verified = adapter.verify_phase_shard(shard, instance)
            self.assertEqual(finalized["receiptBytes"], (shard / "phase-receipt.json").read_bytes())
            self.assertEqual(original, adapter._require_collected_sdk_original(
                shard, verified, {"producer": self.producer}, transport_fixture.PIN))
            for field in ("receipt_sha256", "object_sha256"):
                with patch.dict(origin, {field: "sha256:" + "0" * 64}), \
                        self.assertRaisesRegex(ValueError, "reviewed original"):
                    adapter._require_collected_sdk_original(shard, verified, {"producer": self.producer}, transport_fixture.PIN)
            original_job["id"] = 902
            failed = collect(self.repository / "build/wrong-native-job")
            self.assertIn("reviewed successful job", failed["rows"][0]["reason"])
            downloaded.assert_called_once()
            listing.side_effect = original_listing
            failed = collect(self.repository / "build/conflicting-native-upload")
            self.assertIn("conflicts with a current worker", failed["rows"][0]["reason"])
            downloaded.assert_called_once()
        with patch("sdk_campaign_original_locator.retained_core_origin", return_value=origin), \
                self.assertRaisesRegex(ValueError, "fresh authenticated"):
            adapter._require_collected_sdk_original(shard, verified, {"producer": self.producer}, transport_fixture.PIN)

    def test_sibling_hosts_share_categories_without_rewriting_original_receipts(self):
        first, second = self.shard("rust", "linux-x64"), self.shard("rust", "linux-arm64")
        destination = self.repository / "build/shared-native"
        result = self.collect({item[0]: item[1] for item in (first, second)},
            {item[0]: archive(item[4]) for item in (first, second)}, destination)
        self.assertEqual(["success", "success"], [row["result"] for row in result["rows"]])
        self.assertEqual({"sdk-validation-evidence"}, {row["sdkValidationEvidenceDirectory"] for row in result["rows"]})
        shared = destination / "sdk-validation-evidence"
        records = evidence.load_sdk_validation_evidence(shared)
        for name in ("runtimeStages", "stagedSdks", "packageStage", "compatibilityRequest"):
            self.assertEqual(1, len({row[name] for row in records}), name)
        self.assertEqual({item[2]["receiptBytes"] for item in (first, second)},
                         {(shared / record["validationReceipt"]).read_bytes() for record in records})
        recaptured = self.repository / "build/shared-native-recaptured"
        with patch.object(evidence, "_capture_validation_sources", self.sources), \
                patch.object(projection, "verify_sdk_validation_projection", side_effect=self.runtime_proof) as verify:
            self.assertEqual(records, evidence.stage_sdk_validation_evidence(records, shared, recaptured,
                repository=self.repository, policy_revision=self.producer["commit"], tooling=self.tooling))
        self.assertEqual(2, verify.call_count)
        self.assertEqual(regular_file_inventory(shared, allow_empty=True),
                         regular_file_inventory(recaptured, allow_empty=True))

    def test_projection_still_authenticates_unconsumed_original_bytes(self):
        instance, ready, _, _, files = self.shard("rust", "linux-x64")
        unused = b"unconsumed original input whose CRC must still be verified"
        files["inputs/unused-predecessor"] = unused
        raw = archive(files)
        self.assertEqual(1, raw.count(unused))
        corrupt = raw.replace(unused, b"X" + unused[1:])
        with patch.object(adapter, "_extract_runtime_original_projection") as extract:
            result = self.collect({instance: ready}, {instance: corrupt},
                self.repository / "build/corrupt-native-original")
        self.assertEqual("failure", result["rows"][0]["result"])
        self.assertIsNone(result["rows"][0]["shardDirectory"])
        extract.assert_not_called()

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
        process_error = subprocess.CalledProcessError(1, ["java", "-jar", "signed-tooling.jar"])
        process_error.add_note("synthetic full SDK projection rejection")
        for index, error in enumerate((ValueError("synthetic full SDK projection rejection"), process_error)):
            with self.subTest(error=type(error).__name__):
                calls.clear()
                def proof(**arguments):
                    calls.append((arguments["component"], arguments["target"]))
                    if arguments["component"] == "rust":
                        raise error
                    return self.runtime_proof(**arguments)
                destination = self.repository / f"build/full-gate-rejection-{index}"
                result = self.collect({bad[0]: bad[1], good[0]: good[1]},
                    {bad[0]: archive(bad[4]), good[0]: archive(good[4])}, destination, proof=proof)
                rows = {adapter._identity(row): row for row in result["rows"]}
                self.assertEqual({("rust", "linux-x64"), ("python", "windows-x64")}, set(calls))
                self.assertEqual("failure", rows[bad[0]]["result"])
                self.assertIn("synthetic full SDK projection rejection", rows[bad[0]]["reason"])
                self.assertIsNone(rows[bad[0]].get("sdkValidationEvidenceDirectory"))
                self.assertEqual("success", rows[good[0]]["result"])
                self.assertIsNotNone(rows[good[0]]["sdkValidationEvidenceDirectory"])

    def test_original_binary_and_package_sources_are_bound_and_prepared_once_before_admission(self):
        original = {**self.producer, "commit": "9" * 40, "tree": "8" * 40, "runId": 3}
        items = [self.shard("csharp", target, binary_producer=original)
                 for target in ("linux-arm64", "windows-x64")]
        prepared = []
        def ensure(repository, producer, token):
            self.assertEqual(self.repository, repository)
            self.assertEqual("synthetic-token", token)
            prepared.append(producer)
        def proof(**arguments):
            self.assertIn(original, prepared)
            self.assertIn(self.producer, prepared)
            return self.runtime_proof(**arguments)
        result = self.collect({item[0]:item[1] for item in items},
            {item[0]:archive(item[4]) for item in items}, self.repository/"build/predecessor-sources",
            proof=proof, ensure_source=ensure)
        self.assertEqual(["success", "success"], [row["result"] for row in result["rows"]])
        self.assertEqual([original, self.producer], prepared)

    def test_unbound_predecessor_receipt_cannot_request_source_or_admit_validation(self):
        item = self.shard("csharp", "linux-arm64")
        predecessor = self.predecessors[PhaseInstanceId("sdk", "csharp", "binary", "desktop")]
        predecessor["receiptSha256"] = "sha256:" + "0" * 64
        calls = []
        result = self.collect({item[0]:item[1]}, {item[0]:archive(item[4])},
            self.repository/"build/unbound-predecessor",
            ensure_source=lambda *args: calls.append(args),
            proof=lambda **kwargs: self.fail("Unbound source reached semantic admission"))
        self.assertEqual([], calls)
        self.assertEqual("failure", result["rows"][0]["result"])
        self.assertIn("verified predecessor", result["rows"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
