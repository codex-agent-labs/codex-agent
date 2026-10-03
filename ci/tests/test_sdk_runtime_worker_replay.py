"""Controller lifetime tests, not replay/selection authentication evidence.

The replay and final materializer boundaries are explicitly mocked. Original
stage/receipt capture and temporary-directory/publication primitives are real.
"""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.tests import test_sdk_runtime_capture as fixture
import product_reuse
from products.inventory import canonical_json_bytes, publish_regular_tree, regular_file_inventory, snapshot_regular_tree
from products.registry import PhaseInstanceId


class SdkRuntimeWorkerReplayTest(unittest.TestCase):
    def setUp(self):
        # Reuse setup only; do not inherit or collect the capture test family.
        self.fixture = fixture.SdkRuntimeCaptureTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.work
        self.discovery = self.root / "discovery"
        self.discovery.mkdir()
        self.destination = self.root / "published"
        self.instance = PhaseInstanceId("sdk", "javascript", "validation", "node")
        self.state = SimpleNamespace(rebased_request={"sdkRuntimeSource": "released-default"})
        self.request_before = canonical_json_bytes(self.state.rebased_request)
        self.original_before = regular_file_inventory(self.fixture.source)
        self.capture_paths = []
        self.replay_finished = False

    def invoke(self):
        return product_reuse.materialize_product_predecessors(
            self.root / "synthetic-plan.json", self.discovery, None, self.instance, self.destination,
            expected_build_key="sha256:" + "a" * 64, repository_root=self.root, environ={})

    def capture(self, selected, destination):
        self.capture_paths.append(destination)
        result = self.real_capture(selected, destination)
        self.assertFalse(self.destination.exists())
        self.assertTrue(destination.is_dir())
        return result

    def test_callback_capture_remains_private_until_replay_returns_and_is_cleaned_after_publication(self):
        self.real_capture = product_reuse._capture_sdk_runtime_predecessors

        def replay(*args, sdk_runtime_consumer, **kwargs):
            self.assertTrue(callable(sdk_runtime_consumer))
            self.assertIsNone(sdk_runtime_consumer(self.fixture.selected))
            self.assertFalse(self.destination.exists())
            self.assertEqual(self.request_before, canonical_json_bytes(self.state.rebased_request))
            self.replay_finished = True
            return self.state

        def materialize(state, instance, destination, key, root, *, sdk_runtime_originals):
            self.assertTrue(self.replay_finished)
            self.assertIs(self.state, state)
            self.assertEqual(self.instance, instance)
            self.assertEqual({self.fixture.jvm, self.fixture.node}, set(sdk_runtime_originals))
            self.assertEqual(self.request_before, canonical_json_bytes(state.rebased_request))
            # This stub tests publication timing only, not dependency election.
            original = sdk_runtime_originals[self.fixture.node]
            self.assertTrue(original["receiptPath"].is_file())
            self.assertEqual(self.fixture.selected["handoff"]["receiptBytes"][self.fixture.node], original["receiptBytes"])
            prepared = self.capture_paths[0].parent / "ready"
            snapshot_regular_tree(original["stage"], prepared / "stage")
            (prepared / "phase-receipt.json").write_bytes(original["receiptBytes"])
            publish_regular_tree(prepared, destination)
            return {"controller": "returned-after-replay"}

        with patch.object(product_reuse, "_verified_product_state", side_effect=replay), \
                patch.object(product_reuse, "_capture_sdk_runtime_predecessors", side_effect=self.capture), \
                patch.object(product_reuse, "_materialize_product_predecessors", side_effect=materialize) as materializer:
            self.assertEqual({"controller": "returned-after-replay"}, self.invoke())
            materializer.assert_called_once()
        self.assertTrue(self.destination.is_dir())
        self.assertEqual(1, len(self.capture_paths))
        self.assertFalse(self.capture_paths[0].parent.exists())
        self.assertEqual(self.request_before, canonical_json_bytes(self.state.rebased_request))
        self.assertEqual(self.original_before, regular_file_inventory(self.fixture.source))

    def test_replay_failure_after_callback_never_materializes_and_removes_private_capture(self):
        self.real_capture = product_reuse._capture_sdk_runtime_predecessors

        def replay(*args, sdk_runtime_consumer, **kwargs):
            sdk_runtime_consumer(self.fixture.selected)
            self.assertTrue(self.capture_paths[0].is_dir())
            self.assertFalse(self.destination.exists())
            raise ValueError("synthetic final replay rejection")

        with patch.object(product_reuse, "_verified_product_state", side_effect=replay), \
                patch.object(product_reuse, "_capture_sdk_runtime_predecessors", side_effect=self.capture), \
                patch.object(product_reuse, "_materialize_product_predecessors") as materializer, \
                self.assertRaisesRegex(ValueError, "final replay rejection"):
            self.invoke()
        materializer.assert_not_called()
        self.assertFalse(self.destination.exists())
        self.assertEqual(1, len(self.capture_paths))
        self.assertFalse(self.capture_paths[0].parent.exists())
        self.assertEqual(self.request_before, canonical_json_bytes(self.state.rebased_request))
        self.assertEqual(self.original_before, regular_file_inventory(self.fixture.source))


if __name__ == "__main__":
    unittest.main()
