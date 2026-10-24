"""Validation-only handoff regressions; never change the shipped C++ package."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock
from ci.products.sdk_package import project_cpp_capability_linkage


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

    def test_mock_object_projection_changes_only_retained_private_test_linkage(self):
        self.case.write(self.case.source / "tests/CMakeLists.txt",
                        "add_library(codex_agent_mock STATIC mock_codex_agent.cpp)\n")
        original = (self.case.source / "tests/CMakeLists.txt").read_bytes()
        self.case.produce()
        project_cpp_capability_linkage(self.case.output / "source")
        projected = (self.case.output / "source/tests/CMakeLists.txt").read_bytes()
        self.assertEqual(original, projected.replace(b"OBJECT", b"STATIC"))
        self.assertIn(b"codex_agent_mock OBJECT", projected)
        self.assertEqual(original, (self.case.source / "tests/CMakeLists.txt").read_bytes())

    def test_unknown_mock_linkage_rejects_before_compilation(self):
        self.case.write(self.case.source / "tests/CMakeLists.txt", "unknown declaration\n")
        with self.assertRaisesRegex(ValueError, "mock test linkage declaration changed"):
            project_cpp_capability_linkage(self.case.source)
        self.assertEqual([], self.case.calls)
        self.assertFalse(self.case.output.exists())

    def test_fixed_width_fixture_header_is_only_added_to_private_test_source(self):
        path = self.case.write(self.case.source / "tests/native_loader_fixture.cpp",
                               "std::int32_t fixture();\n")
        original = path.read_bytes()
        self.case.produce()
        self.assertEqual(original, path.read_bytes())
        self.assertEqual(b"#include <cstdint>\n" + original,
                         (self.case.output / "source/tests/native_loader_fixture.cpp").read_bytes())

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
