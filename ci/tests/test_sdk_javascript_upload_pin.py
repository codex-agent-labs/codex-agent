"""Late-copy regression for the observed JavaScript validation upload."""

import unittest
from unittest.mock import patch

from ci.tests import test_sdk_javascript_validation_upload as fixture
from products.inventory import publish_regular_tree


class SdkJavaScriptUploadPinTest(unittest.TestCase):
    def test_authenticated_member_mutated_at_publication_does_not_publish(self):
        source = fixture.SdkJavaScriptValidationUploadTest(
            "test_exact_original_shard_archive_plan_and_consumer_directory_are_preserved"
        )
        source.setUp()
        self.addCleanup(source.doCleanups)

        def mutate_before_copy(prepared, destination, **kwargs):
            member = prepared / "original/inputs/original.bin"
            member.write_bytes(member.read_bytes() + b"late mutation\n")
            return publish_regular_tree(prepared, destination, **kwargs)

        with patch.object(fixture.capture, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            source.call()
        self.assertFalse(source.output.exists())


if __name__ == "__main__":
    unittest.main()
