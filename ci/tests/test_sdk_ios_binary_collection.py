"""Exact iOS binary collection over real synthetic shards and mocked HTTP/state.

Existing transport, archive and shard verifiers are exercised; this fixture does
not authenticate election or claim actual KMP/native compilation or host proof.
"""

import unittest
from unittest.mock import patch

from ci.tests import test_sdk_worker_collection as fixture
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_resume_capture import archive
from products.inventory import load_canonical_json, regular_file_inventory, sha256_bytes
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object


adapter, PhaseInstanceId, PIN = fixture.adapter, fixture.PhaseInstanceId, fixture.PIN
IOS = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")


class SdkIosBinaryCollectionTest(unittest.TestCase):
    # Reuse fixture setup/HTTP helpers only, never inherit unrelated JS tests.
    setUp = fixture.SdkWorkerCollectionTest.setUp
    names = fixture.SdkWorkerCollectionTest.names
    state = fixture.SdkWorkerCollectionTest.state
    official_api = fixture.SdkWorkerCollectionTest.official_api

    def shard(self, *, wrong=None):
        self.counter += 1
        base = self.repository / f"build/original-ios-{self.counter}"
        stage = base / "stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/synthetic").write_bytes(b"original synthetic iOS binary bytes\x00\xff")
        version = "0.2.7" if wrong == "version" else "0.3.0"
        manifest = write_output_manifest(stage, "sdk", "sdk-ios", "binary", "ios", version, {"evidence": "outputs"})
        receipt = write_receipt(base / "fixture-receipt.json", product="sdk", component="sdk-ios",
            phase="binary", target="ios", outputs=manifest["outputs"], upstream=[], version=version,
            version_identity=version, context={"producer": self.producer})
        ready = {name: receipt[name] for name in PHASE_PLAN_KEYS}
        emitted = ready
        if wrong == "key":
            other = write_receipt(base / "other-receipt.json", product="sdk", component="sdk-ios",
                phase="binary", target="ios", outputs=manifest["outputs"], upstream=[], version=version,
                version_identity=version, context={"producer": self.producer},
                toolchain=sha256_bytes(b"different synthetic iOS binary key"))
            emitted = {name: other[name] for name in PHASE_PLAN_KEYS}
        producer = {**self.producer, "runAttempt": 3} if wrong == "producer" else self.producer
        original = base / "shard"
        descriptor = finalize_phase_object(stage_root=stage, phase_plan=emitted, producer=producer,
            product_version=version, trust_domain="development", destination=original)
        files = {"shard/" + row["relativePath"]: (original / row["relativePath"]).read_bytes()
                 for row in regular_file_inventory(original)}
        files.update({"gradle.log": b"", "execution.json": b'{"synthetic":"not execution proof"}\n',
                      "inputs/original.bin": b"original imported inputs\x00\xff"})
        return ready, original, descriptor, files

    def collect(self, ready, uploads, destination, *, elected=None):
        with patch.object(adapter, "_verified_product_state", return_value=self.state(ready if elected is None else elected)), \
                self.official_api(ready, uploads):
            return adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery, destination,
                trusted_workflow_sha=PIN, repository_root=self.repository, environ=self.environment,
                token="synthetic-token", sdk_ios_binary_only=True)

    def test_exact_original_binary_shard_and_complete_worker_upload_are_preserved(self):
        ready, shard, descriptor, files = self.shard()
        before = regular_file_inventory(shard)
        raw = archive(files)
        destination = self.repository / "build/collected-ios"
        result = self.collect({IOS: ready}, {IOS: raw}, destination)
        self.assertEqual(result, load_canonical_json(destination / "collection.json"))
        row, = result["rows"]
        self.assertEqual("success", row["result"])
        self.assertEqual(IOS, adapter._identity(row))
        self.assertEqual("product-validation / sdk-sdk-ios-binary-ios", row["jobName"])
        self.assertEqual(f"codex-agent-sdk-worker-sdk-ios-binary-ios-{ready['buildKey'].removeprefix('sha256:')}-"
                         f"{self.producer['tree']}-attempt-2", row["artifactName"])
        restored = destination / row["shardDirectory"]
        self.assertEqual(descriptor["receiptBytes"], (restored / "phase-receipt.json").read_bytes())
        self.assertEqual(before, regular_file_inventory(restored))
        original = destination / row["originalDirectory"]
        self.assertEqual(raw, (original.parent / "transport.zip").read_bytes())
        self.assertEqual(set(files), {row["relativePath"] for row in regular_file_inventory(original, allow_empty=True)})
        for name, contents in files.items():
            self.assertEqual(contents, (original / name).read_bytes(), name)
        self.assertEqual(before, regular_file_inventory(shard))

    def test_wrong_original_sdk_version_producer_or_key_rejects_without_losing_diagnostics(self):
        for wrong in ("version", "producer", "key"):
            with self.subTest(wrong=wrong):
                ready, shard, descriptor, files = self.shard(wrong=wrong)
                before = regular_file_inventory(shard)
                if wrong == "version":
                    self.assertEqual("0.2.7", descriptor["receipt"]["productVersion"])
                    self.assertEqual(ready["buildKey"], descriptor["buildKey"])
                destination = self.repository / f"build/rejected-ios-{wrong}"
                result = self.collect({IOS: ready}, {IOS: archive(files)}, destination)
                row, = result["rows"]
                self.assertEqual("failure", row["result"])
                self.assertIn("elected plan and producer", row["reason"])
                self.assertIsNone(row["shardDirectory"])
                self.assertIsNotNone(row["originalDirectory"])
                self.assertEqual(b"", (destination / row["originalDirectory"] / "gradle.log").read_bytes())
                self.assertEqual(before, regular_file_inventory(shard))

    def test_only_ios_binary_is_collected_among_other_sdk_runtime_and_contract_work(self):
        ready, _, _, files = self.shard()
        unrelated = [PhaseInstanceId(*identity) for identity in (
            ("sdk", "sdk-ios", "package", "ios"),
            ("sdk", "sdk-ios", "validation", "ios-arm64"),
            ("sdk", "javascript", "package", "node"),
            ("sdk", "javascript", "validation", "node"),
            ("sdk", "sdk-core", "binary", "common"),
            ("runtime", "macos-arm64", "binary", "macos-arm64"),
            ("runtime", "runtime-aggregate", "metadata", "aggregate"),
            ("contract", "contract", "metadata", "common"),
        )]
        elected = {IOS: ready, **{identity: {"buildKey": "sha256:" + "c" * 64} for identity in unrelated}}
        result = self.collect({IOS: ready}, {IOS: archive(files)}, self.repository / "build/only-ios", elected=elected)
        self.assertEqual([IOS], [adapter._identity(row) for row in result["rows"]])
        self.assertEqual("success", result["rows"][0]["result"])

    def test_no_elected_ios_binary_causes_no_official_requests(self):
        other = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
        with patch.object(adapter, "_verified_product_state", return_value=self.state({other: {}})), \
                patch.object(adapter, "api_json") as query, patch.object(adapter, "paginated_items") as listing, \
                patch.object(adapter, "download_artifact_to_file") as download:
            result = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                self.repository / "build/no-ios", trusted_workflow_sha=PIN, repository_root=self.repository,
                environ=self.environment, token="synthetic-token", sdk_ios_binary_only=True)
        self.assertEqual([], result["rows"])
        self.assertEqual([], result["observed"])
        for mocked in (query, listing, download):
            mocked.assert_not_called()

    def test_invalid_mixed_collection_scopes_reject_before_replay(self):
        for options in ({"sdk_ios_binary_only": 1}, {"sdk_ios_binary_only": "true"},
                        {"sdk_ios_binary_only": True, "sdk_javascript_only": True},
                        {"sdk_ios_binary_only": True, "runtime_aggregate_only": True}):
            with self.subTest(options=options), patch.object(adapter, "_verified_product_state") as replay, \
                    patch.object(adapter, "api_json") as query, self.assertRaisesRegex(ValueError, "boolean.*exclusive"):
                adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                    self.repository / "build/invalid-ios", trusted_workflow_sha=PIN, repository_root=self.repository,
                    environ=self.environment, token="synthetic-token", **options)
            replay.assert_not_called()
            query.assert_not_called()

    def test_advancement_requires_exact_ios_partition_and_exclusive_scope(self):
        ready, _, _, _ = self.shard()
        other = PhaseInstanceId("sdk", "javascript", "package", "node")
        state = self.state({IOS: ready, other: {"buildKey": "sha256:" + "f" * 64}})
        state.consumer, state.requested, state.closure = {}, (IOS, other), (IOS, other)
        state.rebased_request, state.prior_by_instance = {}, {}
        state.sources, state.prior_carrier_phases = {}, {}
        state.prior = {"phases": [{**adapter._identity_record(identity), "state": "build",
            "buildKey": value["buildKey"]} for identity, value in state.prior_ready_plans.items()]}
        cases = (({"runtime_workers_only": True}, (), "mutually exclusive"),
                 ({"runtime_aggregate_only": True}, (), "mutually exclusive"),
                 ({"sdk_javascript_only": True}, (), "mutually exclusive"),
                 ({"sdk_ios_binary_only": 1}, (), "boolean"),
                 ({}, (other,), "distinct elected build phases"),
                 ({}, (), "exactly partition"))
        for number, (options, failed, message) in enumerate(cases):
            destination = self.repository / f"build/advance-ios-{number}"
            output = self.repository / f"ios-output-{number}"
            with self.subTest(number=number), patch.object(adapter, "_verified_product_state", return_value=state), \
                    self.assertRaisesRegex(ValueError, message):
                adapter.advance_products(self.plan_path, self.discovery, self.discovery, [], destination, output,
                    repository_root=self.repository, environ=self.environment, failed_instances=failed,
                    **{"sdk_ios_binary_only": True, **options})
            self.assertFalse(destination.exists())
            self.assertIn("wave_failed=true", output.read_text())


if __name__ == "__main__":
    unittest.main()
