"""Original binary context orchestration; mocked transport grants no host proof."""

from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_ios_original_binary as workflow
from ci.tests import test_sdk_ios_package_upload as upload_fixture
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, snapshot_regular_tree


class SdkIosOriginalBinaryTest(unittest.TestCase):
    def setUp(self):
        fixture = upload_fixture.SdkIosBinaryUploadTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.template = fixture.work / "binary-template"
        for relative, raw in fixture.files.items():
            path = self.template / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.native = fixture.work / "native-recapture"
        self.transport = {"schemaVersion": 1, "captureProducer": fixture.producer,
            "observed": [], "artifacts": {}, "receiptSha256s": {}}
        for index, lane in enumerate(workflow.LANES):
            self.transport["artifacts"][lane] = {"id": index + 1, "digest": "sha256:" + str(index + 1) * 64}
            raw = canonical_json_bytes({"original": lane})
            self.transport["receiptSha256s"][lane] = sha256_bytes(raw)
            for relative, data in ((f"lanes/{lane}/lane-receipt.json", raw),
                                   (f"archives/{lane}.zip", b"original native archive"),
                                   (f"native-evidence/{lane}.bin", b"original evidence")):
                path = self.native / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        plan = self.native / "plan/impact-plan.json"
        plan.parent.mkdir()
        plan.write_bytes(fixture.original_plan)
        # Preserve any opaque uploaded files as well as required original roots.
        retained = self.template / "native-original"
        for row in regular_file_inventory(self.native):
            path = retained / row["relativePath"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((self.native / row["relativePath"]).read_bytes())
        for subtree in ("archives", "lanes", "native-evidence", "plan"):
            for row in regular_file_inventory(retained / subtree, allow_empty=True):
                path = self.native / subtree / row["relativePath"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((retained / subtree / row["relativePath"]).read_bytes())
        (retained / "native-transport.json").write_bytes(canonical_json_bytes(self.transport))
        self.events = []
        self.mutation = None

    def capture(self, plan, destination, **arguments):
        self.events.append("capture")
        self.assertEqual(self.fixture.receipt_path, arguments["binary_receipt_path"])
        snapshot_regular_tree(self.template, destination / "original", allow_empty=True)

    @contextmanager
    def native_inputs(self, plan, **arguments):
        self.events.append("native-enter")
        self.assertNotEqual(self.fixture.receipt_path, arguments["original_binary_receipt_path"])
        self.assertEqual(self.fixture.receipt_bytes, arguments["original_binary_receipt_path"].read_bytes())
        self.assertEqual(self.fixture.original_plan, plan.read_bytes())
        self.assertEqual({lane: {"artifactId": row["id"], "artifactSha256": row["digest"]}
                          for lane, row in self.transport["artifacts"].items()}, arguments["uploads"])
        if self.mutation == "recapture":
            (self.native / "native-evidence/ios-native-tests.bin").write_bytes(b"different")
        yield {"producer": self.fixture.producer, "captureRoot": self.native,
               "transport": {**self.transport, "binaryReceiptSha256":
                   "sha256:" + "f" * 64 if self.mutation == "receipt-binding" else sha256_bytes(self.fixture.receipt_bytes)}}
        self.events.append("native-exit")
        if self.mutation == "exit":
            raise ValueError("native context rejected")

    @contextmanager
    def context(self):
        with patch.object(workflow.product_reuse, "capture_sdk_ios_binary_upload", side_effect=self.capture), \
                patch.object(workflow, "verified_sdk_apple_native_inputs", side_effect=self.native_inputs):
            with workflow.verified_original_ios_binary(self.fixture.plan_path, self.fixture.receipt_path,
                    artifact_id=701, artifact_sha256=self.fixture.artifact["digest"],
                    trusted_workflow_sha=self.fixture.pin, repository_root=self.fixture.root,
                    environ={}, token="mock-token") as value:
                yield value

    def test_exact_original_restore_and_native_pairing_remain_live_until_exit(self):
        with self.context() as value:
            self.assertEqual(self.fixture.receipt_bytes, value["receiptBytes"])
            self.assertEqual(self.fixture.receipt_bytes, value["receiptPath"].read_bytes())
            stage = value["stage"]
            self.assertTrue(stage.exists())
            self.assertEqual(["capture", "native-enter"], self.events)
        self.assertEqual(["capture", "native-enter", "native-exit"], self.events)
        self.assertFalse(stage.exists())

    def test_native_recapture_or_exit_rejection_never_returns_completed_context(self):
        for mutation in ("recapture", "exit", "receipt-binding"):
            self.mutation = mutation
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                with self.context():
                    if mutation != "exit":
                        self.fail("different native original yielded")
            (self.native / "native-evidence/ios-native-tests.bin").write_bytes(b"original evidence")

    def test_consumer_stage_or_plan_mutation_fails_exit(self):
        for mutation in ("stage", "plan"):
            try:
                with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "changed during recovery"):
                    with self.context() as value:
                        path = (value["stage"] / "injected" if mutation == "stage" else self.fixture.plan_path)
                        path.write_bytes(b"changed")
            finally:
                self.fixture.plan_path.write_bytes(self.fixture.original_plan)


if __name__ == "__main__":
    unittest.main()
