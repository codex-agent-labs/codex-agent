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
        self.producers = {lane: {**fixture.producer, "commit": str(index + 1) * 40}
                          for index, lane in enumerate(workflow.LANES)}
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
        for lane, relative in workflow.NATIVE_TOOLCHAINS.items():
            path = self.native / "lanes" / lane / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(canonical_json_bytes({"synthetic-original-observations": lane}))
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
        self.tooling = {"rust_host": "aarch64-apple-darwin", "tooling_evidence": fixture.work / "tooling",
            "tooling_public_key": fixture.work / "key.pub", "java_executable": fixture.work / "java",
            "policy_revision": "c" * 40, "required_trust_domain": "release",
            "tooling_keyring": fixture.work / "keyring", "tooling_keys_directory": fixture.work / "keys"}

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
               "directory": self.native / "native-evidence", "originalProducers": self.producers,
               "transport": {**self.transport, "binaryReceiptSha256":
                   "sha256:" + "f" * 64 if self.mutation == "receipt-binding" else sha256_bytes(self.fixture.receipt_bytes)}}
        self.events.append("native-exit")
        if self.mutation == "exit":
            raise ValueError("native context rejected")

    def semantics(self, **arguments):
        self.events.append("semantic-verify")
        self.assertEqual(self.fixture.producer["commit"], arguments["source_revision"])
        self.assertEqual(self.producers, arguments["original_producers"])
        self.assertEqual(self.native / "native-evidence", arguments["evidence_directory"])
        self.assertEqual(self.fixture.root, arguments["repository"])
        for name, value in self.tooling.items():
            self.assertEqual(value, arguments[name])
        copied = arguments["toolchain_directory"]
        self.toolchain_copy = copied
        self.assertEqual({Path(path).name for path in workflow.NATIVE_TOOLCHAINS.values()},
                         {path.name for path in copied.iterdir()})
        for lane, relative in workflow.NATIVE_TOOLCHAINS.items():
            self.assertEqual((self.native / "lanes" / lane / relative).read_bytes(),
                             (copied / Path(relative).name).read_bytes())
        if self.mutation == "semantic-rejection":
            raise ValueError("native semantic proof rejected")
        if self.mutation == "semantic-copy":
            next(copied.iterdir()).write_bytes(b"changed")

    @contextmanager
    def context(self):
        with patch.object(workflow.product_reuse, "capture_sdk_ios_binary_upload", side_effect=self.capture), \
                patch.object(workflow, "verified_sdk_apple_native_inputs", side_effect=self.native_inputs), \
                patch.object(workflow, "verify_sdk_apple_original_native_content", side_effect=self.semantics):
            with workflow.verified_original_ios_binary(self.fixture.plan_path, self.fixture.receipt_path,
                    artifact_id=701, artifact_sha256=self.fixture.artifact["digest"],
                    trusted_workflow_sha=self.fixture.pin, repository_root=self.fixture.root,
                    environ={}, token="mock-token", **self.tooling) as value:
                yield value

    def test_exact_original_restore_and_native_pairing_remain_live_until_exit(self):
        with self.context() as value:
            self.assertEqual(self.fixture.receipt_bytes, value["receiptBytes"])
            self.assertEqual(self.fixture.receipt_bytes, value["receiptPath"].read_bytes())
            self.assertEqual(value["original"].parent, value["binaryCapture"])
            self.assertTrue(value["binaryCapture"].is_dir())
            stage = value["stage"]
            self.assertTrue(stage.exists())
            self.assertEqual(["capture", "native-enter", "semantic-verify"], self.events)
        self.assertEqual(["capture", "native-enter", "semantic-verify", "native-exit"], self.events)
        self.assertFalse(stage.exists())
        self.assertFalse(self.toolchain_copy.exists())

    def test_native_recapture_or_exit_rejection_never_returns_completed_context(self):
        for mutation in ("recapture", "exit", "receipt-binding", "semantic-rejection", "semantic-copy"):
            self.mutation = mutation
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                with self.context():
                    if mutation != "exit":
                        self.fail("different native original yielded")
            (self.native / "native-evidence/ios-native-tests.bin").write_bytes(b"original evidence")

    def test_consumer_stage_or_plan_mutation_fails_exit(self):
        for mutation in ("stage", "plan", "toolchain", "capture"):
            try:
                with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "changed during recovery"):
                    with self.context() as value:
                        path = (value["stage"] / "injected" if mutation == "stage" else
                                next(self.toolchain_copy.iterdir()) if mutation == "toolchain" else
                                value["binaryCapture"] / "original/native-original/native-transport.json"
                                if mutation == "capture" else self.fixture.plan_path)
                        path.write_bytes(b"changed")
            finally:
                self.fixture.plan_path.write_bytes(self.fixture.original_plan)


if __name__ == "__main__":
    unittest.main()
