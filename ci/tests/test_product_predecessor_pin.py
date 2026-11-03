"""Late-copy regression for authenticated SDK predecessor materialization."""

import unittest
from unittest.mock import patch

from ci.tests import test_product_predecessor_materialization as fixture
from products.inventory import publish_regular_tree


class ProductPredecessorPinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.SdkRuntimePredecessorMaterializationTest.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.SdkRuntimePredecessorMaterializationTest.doClassCleanups()

    def test_late_runtime_predecessor_mutation_does_not_publish(self):
        source = fixture.SdkRuntimePredecessorMaterializationTest(
            "test_external_runtime_preserves_original_bytes_and_never_substitutes_old_contract"
        )
        source.setUp()
        self.addCleanup(source.tearDown)
        state, ready, _, captured = source.inputs()
        identity = fixture.PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        output = captured[identity]["receipt"]["outputs"][0]["relativePath"]

        def mutate_before_copy(prepared, destination, **kwargs):
            member = prepared / "runtime-linux-x64-binary-linux-x64/stage" / output
            member.write_bytes(member.read_bytes() + b"late mutation\n")
            return publish_regular_tree(prepared, destination, **kwargs)

        destination = source.scratch / "late-predecessor"
        with patch.object(fixture.adapter, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            fixture.adapter._materialize_product_predecessors(
                state, source.SDK, destination, ready["buildKey"], source.repository,
                sdk_runtime_originals=captured,
            )
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
