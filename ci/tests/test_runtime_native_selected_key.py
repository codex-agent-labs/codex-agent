"""Native leaf selected-key binding over the existing signed fixture."""

import unittest
from unittest.mock import patch

from ci.tests import test_runtime_release_caller as fixture
from ci import runtime_release
from ci.products.inventory import load_canonical_json_bytes


class RuntimeNativeSelectedKeyTest(unittest.TestCase):
    setUpClass = classmethod(fixture.RuntimeReleaseCallerTest.setUpClass.__func__)
    commit_policy = classmethod(fixture.RuntimeReleaseCallerTest.commit_policy.__func__)
    setUp = fixture.RuntimeReleaseCallerTest.setUp
    invoke = fixture.RuntimeReleaseCallerTest.invoke

    def metadata_key(self):
        return load_canonical_json_bytes(self.receipts["metadata"].read_bytes())["buildKey"]

    def retained(self, **changes):
        self.environment.forbid_secret = True
        with patch("reuse.api_request", side_effect=AssertionError("HTTP on complete reuse")):
            return self.invoke(release_handoffs=(self.handoff,), token=None, **changes)

    def test_matching_selected_metadata_key_is_accepted(self):
        self.retained(expected_build_key=self.metadata_key())
        self.assertTrue((self.destination / "runtime-input").is_dir())
        self.assertEqual(0, self.environment.secret_reads)

    def test_omitted_selected_key_preserves_existing_leaf_behavior(self):
        self.retained()
        self.assertTrue((self.destination / "runtime-input").is_dir())
        self.assertEqual(0, self.environment.secret_reads)

    def test_wrong_selected_key_rejects_before_original_source_or_private_key(self):
        self.environment.forbid_secret = True
        with patch.object(runtime_release, "capture_runtime_original_ci_phases",
                          side_effect=AssertionError("original source capture before selected key")), \
                patch.object(runtime_release, "require_active_release_key",
                             side_effect=AssertionError("signing key before selected key")), \
                self.assertRaisesRegex(ValueError, "differs from the caller's selected build key"):
            self.invoke(expected_build_key="sha256:" + "0" * 64)
        self.assertFalse(self.destination.exists())
        self.assertEqual(0, self.environment.secret_reads)

    def test_invalid_selected_key_rejects_before_original_source_or_private_key(self):
        self.environment.forbid_secret = True
        with patch.object(runtime_release, "capture_runtime_original_ci_phases",
                          side_effect=AssertionError("original source capture before selected key")), \
                patch.object(runtime_release, "require_active_release_key",
                             side_effect=AssertionError("signing key before selected key")), \
                self.assertRaisesRegex(ValueError, "Selected Runtime metadata build key"):
            self.invoke(expected_build_key="not-a-build-key")
        self.assertFalse(self.destination.exists())
        self.assertEqual(0, self.environment.secret_reads)


if __name__ == "__main__":
    unittest.main()
