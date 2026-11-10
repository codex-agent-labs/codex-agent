import copy
import importlib.util
import os
from pathlib import Path
import unittest
from unittest import mock

import ci.tests.test_product_restore as fixtures

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "storage_diagnostic", ROOT / ".github/actions/run-ci-lane/storage-diagnostic.py")
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


class HostedStorageDiagnosticTest(unittest.TestCase):
    def fixture(self):
        value = fixtures.ProductRestoreTest()
        value.setUp()
        self.addCleanup(value.tearDown)
        stored = value.store()
        envelope = dict(receipt=value.receipt, receiptBytes=value.receipt_bytes,
                        receiptSha256=value.receipt_sha256, objectSha256=stored["objectSha256"])
        return value, stored, envelope

    def test_consumer_temp_alignment_is_step_scoped_to_measured_runner_volume(self):
        workflow = (ROOT / ".github/workflows/portable-reuse-proof.yml").read_text()
        before, consumer = workflow.split("      - id: consumer\n", 1)
        consumer, after = consumer.split("      - name: Preserve filesystem observations", 1)
        environment = consumer.split("        env:\n", 1)[1].split("        run: |\n", 1)[0]
        for name in ("TMPDIR", "TMP", "TEMP"):
            binding = name + ": ${{ runner.temp }}"
            self.assertIn("          " + binding + "\n", environment)
            self.assertNotIn(binding, before)
            self.assertNotIn(binding, after)
        self.assertIn('--output "$RUNNER_TEMP/storage-diagnostics"', consumer)

    def test_first_repeat_reference_and_independent_stage_exit_without_changing_original(self):
        value, stored, envelope = self.fixture()
        archive = stored["path"]
        before = archive.read_bytes()
        with diagnostic.verification_session():
            first = diagnostic.consume("first", archive, envelope,
                                       value.remote_transport()["consumer"], value.root)
            repeat = diagnostic.consume("repeat", archive, envelope,
                                        value.remote_transport()["consumer"], value.root)
        self.assertEqual(first["stagedInventorySha256"], repeat["stagedInventorySha256"])
        for result in (first, repeat):
            self.assertEqual(0, result["forwardedObjectBytes"])
            self.assertTrue(result["independentInodes"])
            self.assertTrue(result["absentAfterExit"])
            for field in ("freeBytesAfterRestore", "freeBytesAfterReference", "freeBytesAfterStaging"):
                self.assertIsInstance(result[field], int)
                self.assertGreaterEqual(result[field], 0)
        self.assertEqual(before, archive.read_bytes())
        self.assertFalse(list(value.root.glob("first-*")))
        self.assertFalse(list(value.root.glob("repeat-*")))

    def test_ordinary_fallback_and_permission_failure_keep_cleanup_and_original(self):
        from products import sdk_apple_content
        value, stored, envelope = self.fixture()
        before = stored["path"].read_bytes()
        with diagnostic.verification_session(), mock.patch.object(
                sdk_apple_content, "_apple_clone_operation", return_value=None):
            result = diagnostic.consume("fallback", stored["path"], envelope,
                                        value.remote_transport()["consumer"], value.root)
        self.assertTrue(result["independentInodes"])
        def denied(*args):
            raise PermissionError("test permission failure")
        with diagnostic.verification_session(), mock.patch.object(
                sdk_apple_content, "_apple_clone_operation", return_value=denied):
            with self.assertRaises(PermissionError):
                diagnostic.consume("denied", stored["path"], envelope,
                                   value.remote_transport()["consumer"], value.root)
        self.assertFalse(list(value.root.glob("denied-*")))
        self.assertEqual(before, stored["path"].read_bytes())

    def test_selected_original_rejects_wrong_identity_or_bulk_member_before_capture(self):
        extension = {"spec": {"schemaVersion": 4, "completedPhases": [diagnostic.OBJECT],
                              "originals": [diagnostic.ORIGINAL]},
                     "proof": {"members": [{"sha256": diagnostic.OBJECT["objectSha256"],
                                             "bytes": diagnostic.OBJECT_BYTES}]}}
        capability = mock.Mock()
        capability.completed_phases.return_value = diagnostic.PHASE_INSTANCE_IDS
        for field in ("object", "original", "size"):
            changed = copy.deepcopy(extension)
            if field == "object":
                changed["spec"]["completedPhases"][0]["objectSha256"] = "sha256:" + "0" * 64
            elif field == "original":
                changed["spec"]["originals"][0]["artifactId"] += 1
            else:
                changed["proof"]["members"][0]["bytes"] += 1
            capability.sdk_extension.return_value = changed
            with self.subTest(field=field), self.assertRaises(ValueError):
                diagnostic.selected_original(capability)
        capability.envelope.assert_not_called()
        capability.capture_object.assert_not_called()

    @unittest.skipIf(os.name == "nt", "Unix block-operation observation")
    def test_io_observation_does_not_convert_unix_block_counts_into_bytes(self):
        with mock.patch.object(diagnostic.sys, "platform", "darwin"):
            value = diagnostic.io_observation()
        self.assertIsNone(value["storageWriteBytes"])
        self.assertIsNone(value["descendantStorageBytes"])
        if os.name != "nt":
            self.assertIn("selfBlockOperations", value)

