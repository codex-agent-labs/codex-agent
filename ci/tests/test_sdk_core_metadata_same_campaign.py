"""Same-run Core metadata must be independently observed and re-admitted."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from ci import sdk_core_metadata_same_campaign as selected
from ci.products.inventory import sha256_bytes, snapshot_regular_tree, write_canonical_json
from ci.products.registry import SDK_FACADE_TARGETS


class SameCampaignCoreMetadataTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="same-campaign-core-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.discovery = self.root / "discovery"
        self.before = self.root / "before"
        self.after = self.root / "after"
        for path in (self.discovery, self.before, self.after):
            path.mkdir()
            (path / "record").write_bytes(b"fixed")
        self.receipt_path = self.root / "metadata-receipt.json"
        self.key = "sha256:" + "a" * 64
        self.producer = {"commit": "b" * 40}
        self.receipt = {"product": "sdk", "component": "sdk-core", "phase": "metadata",
                        "target": "common", "buildKey": self.key, "producer": self.producer}
        write_canonical_json(self.receipt_path, self.receipt)
        self.digest = sha256_bytes(self.receipt_path.read_bytes())
        self.outside = self.root / "outside"
        self.captures = self.outside / "evidence"
        self.captures.mkdir(parents=True)
        self.validations = {}
        for target in SDK_FACADE_TARGETS:
            capture = self.captures / target
            capture.mkdir()
            (capture / "record").write_bytes(b"original validation")
            receipt = self.root / (target + ".json")
            receipt.write_bytes(target.encode())
            self.validations[target] = {"captureRoot": str(capture),
                                        "validationReceipt": str(receipt)}
        self.fresh = self.outside / "policy.json"
        write_canonical_json(self.fresh, {"evidenceRoot": str(self.captures),
                              "records": [], "policy": {"validations": self.validations,
                              "toolingEvidence": "/tooling", "toolingPublicKey": "/key",
                              "javaExecutable": "/java", "toolingTrustDomain": "release",
                              "toolingKeyring": "/keyring", "toolingKeysDirectory": "/keys"}})

    def invoke(self, *, selected_object=None, fresh_records=None,
               expected_artifact_id=7, expected_artifact_sha256="sha256:" + "d" * 64):
        if fresh_records is not None:
            value = selected.load_canonical_json_bytes(self.fresh.read_bytes())
            value["records"] = fresh_records
            write_canonical_json(self.fresh, value)

        @contextmanager
        def fresh(*args, **kwargs):
            yield self.fresh

        def capture(_plan, destination, **kwargs):
            self.assertEqual(self.digest, sha256_bytes(kwargs["metadata_receipt_path"].read_bytes()))
            destination.mkdir()
            (destination / "record").write_bytes(b"official metadata")

        def shard(path, instance):
            raw = (self.receipt_path.read_bytes() if instance.phase == "metadata"
                   else Path(self.validations[instance.target]["validationReceipt"]).read_bytes())
            return {"receipt": self.receipt if instance.phase == "metadata" else {"target": instance.target},
                    "receiptBytes": raw, "receiptSha256": sha256_bytes(raw),
                    "objectSha256": "sha256:" + "c" * 64}

        def write(_plan, destination, **kwargs):
            self.assertEqual(12, len(kwargs["records"]))
            self.assertEqual(self.outside, kwargs["evidence_root"])
            self.assertEqual(self.digest, kwargs["metadata_envelope"]["receiptSha256"])
            self.assertEqual(11, len(kwargs["validation_envelopes"]))
            write_canonical_json(destination, {"evidenceRoot": str(kwargs["evidence_root"]),
                                  "records": kwargs["records"], "policy": kwargs["policy"]})

        phase = {"state": "retained", "source": None, "transportSource": None,
                 "buildKey": self.key, "receiptSha256": self.digest,
                 "objectSha256": "sha256:" + "c" * 64}
        if selected_object is not None:
            phase.update(selected_object)
        state = SimpleNamespace(producer=self.producer,
            prior_by_instance={selected._METADATA: phase})
        with mock.patch.object(selected.product_reuse, "_product_materialization_paths",
                               return_value=(self.discovery, self.after, self.root / "unused")), \
             mock.patch.object(selected, "validate_phase_receipt", return_value=self.receipt), \
             mock.patch.object(selected, "_context", return_value={"repositoryRoot": "/original",
                                                                  "metadataRequest": "/original/request"}), \
             mock.patch.object(selected, "held_fresh_facade_metadata_policy", side_effect=fresh), \
             mock.patch.object(selected, "locate_original_facade_upload", return_value={
                 "artifact_id": 7, "artifact_sha256": "sha256:" + "d" * 64}) as locator, \
             mock.patch.object(selected, "capture_sdk_facade_metadata_upload", side_effect=capture) as captured, \
             mock.patch.object(selected, "verify_phase_shard", side_effect=shard), \
             mock.patch.object(selected, "write_facade_metadata_policy", side_effect=write) as writer, \
             mock.patch.object(selected, "FacadeMetadataAdmission", return_value=object()), \
             mock.patch.object(selected.product_reuse, "_verified_product_state", return_value=state) as verified:
            with selected.held_same_campaign_core_metadata_policy(
                    self.root / "plan.json", self.discovery, self.before, self.after,
                    self.receipt_path, expected_build_key=self.key,
                    expected_receipt_sha256=self.digest,
                    expected_artifact_id=expected_artifact_id,
                    expected_artifact_sha256=expected_artifact_sha256, replay_policy={},
                    original_context={}, trusted_workflow_sha="e" * 40,
                    repository_root=self.root, environ={}, token="token") as policy:
                self.assertTrue(policy.is_file())
            return locator, captured, writer, verified

    def test_binds_official_metadata_to_all_originals_and_current_state(self):
        locator, captured, writer, verified = self.invoke()
        locator.assert_called_once()
        captured.assert_called_once()
        writer.assert_called_once()
        verified.assert_called_once()
        self.assertIsNotNone(verified.call_args.kwargs["sdk_facade_metadata_admission"])

    def test_rejects_worker_upload_different_from_independent_success_pins(self):
        with self.assertRaisesRegex(ValueError, "successful worker pins"):
            self.invoke(expected_artifact_id=8)
        with self.assertRaisesRegex(ValueError, "successful worker pins"):
            self.invoke(expected_artifact_sha256="sha256:" + "f" * 64)

    def test_rejects_fresh_descriptor_as_reuse_authority_and_cross_pair(self):
        with self.assertRaisesRegex(ValueError, "cannot certify reuse"):
            self.invoke(fresh_records=[{"self": "certified"}])
        write_canonical_json(self.fresh, {"evidenceRoot": str(self.captures), "records": [],
            "policy": {"validations": self.validations, "toolingEvidence": "/tooling",
                       "toolingPublicKey": "/key", "javaExecutable": "/java",
                       "toolingTrustDomain": "release", "toolingKeyring": "/keyring",
                       "toolingKeysDirectory": "/keys"}})
        with self.assertRaisesRegex(ValueError, "differs from original upload"):
            self.invoke(selected_object={"objectSha256": "sha256:" + "f" * 64})

    def test_real_shards_and_concrete_admission_accept_twelve_capture_layout(self):
        from ci.tests.test_sdk_facade_metadata_admission import FacadeMetadataAdmissionTest
        fixture = FacadeMetadataAdmissionTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.records = [{"receiptSha256": fixture.envelope["receiptSha256"],
                            "captureRoot": fixture.f.retained.relative_to(fixture.root).as_posix()}]
        for envelope in fixture.predecessors:
            target = envelope["receipt"]["target"]
            capture = Path(fixture.policy["validations"][target]["captureRoot"])
            fixture.records.append({"receiptSha256": envelope["receiptSha256"],
                                    "captureRoot": capture.relative_to(fixture.root).as_posix()})
        fixture.records.sort(key=lambda row: row["receiptSha256"])
        self.assertEqual(12, len(fixture.records))
        fixture.make().verify_metadata(fixture.envelope, fixture.predecessors)
        self.assertEqual(["enter", "exit"], fixture.events)

    def test_helper_uses_real_shards_writer_and_concrete_admission(self):
        from ci.tests.test_sdk_facade_metadata_admission import FacadeMetadataAdmissionTest
        fixture = FacadeMetadataAdmissionTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        outside = self.root / "held-originals"
        captures = outside / "evidence"
        captures.mkdir(parents=True)
        for target in SDK_FACADE_TARGETS:
            source = Path(fixture.policy["validations"][target]["captureRoot"])
            target_capture = captures / target
            snapshot_regular_tree(source, target_capture, allow_empty=True)
            fixture.policy["validations"][target]["captureRoot"] = str(target_capture)
        fresh = outside / "policy.json"
        fresh_policy = deepcopy(fixture.policy)
        del fresh_policy["originalContext"]
        write_canonical_json(fresh, {"evidenceRoot": str(captures),
                                     "records": [], "policy": fresh_policy})
        previous_metadata_capture = fixture.f.retained
        receipt_path = fixture.f.receipt_path
        receipt = fixture.envelope["receipt"]
        completed = SimpleNamespace(producer=receipt["producer"], prior_by_instance={
            selected._METADATA: {"state": "retained", "source": None, "transportSource": None,
                                 "buildKey": receipt["buildKey"],
                                 "receiptSha256": fixture.envelope["receiptSha256"],
                                 "objectSha256": fixture.envelope["objectSha256"]}})

        @contextmanager
        def held(*args, **kwargs):
            yield fresh

        def captured(_plan, destination, **kwargs):
            self.assertEqual(receipt_path.read_bytes(), kwargs["metadata_receipt_path"].read_bytes())
            snapshot_regular_tree(previous_metadata_capture, destination, allow_empty=True)
            fixture.f.retained = destination

        def git_value(_root, _operation, revision):
            return receipt["producer"]["tree" if revision == "HEAD^{tree}" else "commit"]

        @contextmanager
        def replay(**kwargs):
            self.assertEqual(receipt["producer"]["commit"], kwargs["policy_revision"])
            with fixture.replay(**{**kwargs, "policy_revision": "c" * 40}) as value:
                yield value

        writer = sys.modules[selected.write_facade_metadata_policy.__module__]
        original = sys.modules["sdk_facade_metadata_original"]
        with mock.patch.object(selected.product_reuse, "_product_materialization_paths",
                               return_value=(self.discovery, self.after, self.root / "unused")), \
             mock.patch.object(selected, "held_fresh_facade_metadata_policy", side_effect=held), \
             mock.patch.object(selected, "locate_original_facade_upload", return_value={
                 "artifact_id": 123, "artifact_sha256": "sha256:" + "d" * 64}), \
             mock.patch.object(selected, "capture_sdk_facade_metadata_upload", side_effect=captured), \
             mock.patch.object(selected.product_reuse, "_verified_product_state", return_value=completed), \
             mock.patch.object(selected.product_reuse, "_git_value", side_effect=git_value), \
             mock.patch.object(writer, "_request_inventory",
                               side_effect=lambda path: {path: writer.sha256_file(path)}), \
             mock.patch.object(original, "verified_retained_sdk_facade_metadata",
                               side_effect=replay), \
             mock.patch.object(selected.product_reuse, "_validate_plan", return_value={
                 "remoteBuildAuthorized": True, "event": "pull_request",
                 "validationCommit": receipt["producer"]["commit"],
                 "validationTree": receipt["producer"]["tree"]}):
            with selected.held_same_campaign_core_metadata_policy(
                    Path(fresh_policy["plan"]), self.discovery, self.before, self.after,
                    receipt_path, expected_build_key=receipt["buildKey"],
                    expected_receipt_sha256=fixture.envelope["receiptSha256"],
                    expected_artifact_id=123,
                    expected_artifact_sha256="sha256:" + "d" * 64,
                    replay_policy=fresh_policy, original_context=fixture.f.context,
                    trusted_workflow_sha="e" * 40, repository_root=fixture.root,
                    environ={}, token="explicit-caller-token") as descriptor:
                self.assertTrue(descriptor.is_file())
                self.assertEqual(["enter", "exit"], fixture.events)


if __name__ == "__main__":
    unittest.main()
