"""Validation-only handoff regressions; never change the shipped C++ package."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("cpp_root_fixture", ROOT /
    "codex-agent-bindings/cpp/tools/tests/test_sdk_validation_evidence_producer.py")
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


class RootOverlayTest(unittest.TestCase):
    def setUp(self):
        self.case = fixture.ProducerTest()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.root = self.case.write(self.case.compatibility.with_name("sdk-runtime-root.pub"),
                                   "authenticated public root\n")

    def test_original_root_is_overlaid_only_in_private_sdk(self):
        self.case.produce()
        resource = Path("share/CodexAgent/native/sdk-runtime-root.pub")
        self.assertEqual(self.root.read_bytes(),
                         (self.case.output / "imported-c-sdk" / resource).read_bytes())
        self.assertFalse((self.case.sdk / resource).exists())
        self.assertEqual("authenticated public root\n", self.root.read_text())
        self.assertEqual(4, len(self.case.calls))

    def test_bad_root_rejects_before_execution_or_old_evidence_deletion(self):
        for mutation in ("empty", "symlink", "conflict"):
            with self.subTest(mutation=mutation):
                root = self.root
                if mutation == "empty":
                    root.write_bytes(b"")
                elif mutation == "symlink":
                    root.unlink()
                    root.symlink_to(self.case.api)
                else:
                    self.case.write(self.case.sdk /
                        "share/CodexAgent/native/sdk-runtime-root.pub", "different root\n")
                with mock.patch.object(fixture.producer, "_invalidate") as invalidate:
                    with self.assertRaises(ValueError):
                        self.case.produce()
                    invalidate.assert_not_called()
                if root.is_symlink():
                    root.unlink()
                root.write_text("authenticated public root\n")
        self.assertEqual([], self.case.calls)


if __name__ == "__main__":
    unittest.main()
