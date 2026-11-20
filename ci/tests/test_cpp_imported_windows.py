"""Exercise the Windows reader locally; not genuine Windows package acceptance."""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

from ci.products import inventory


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("cpp_imported_fixtures",
    ROOT / "codex-agent-bindings/cpp/tools/tests/test_imported_package_verifier.py")
fixtures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixtures)
verifier = fixtures.verifier


class WindowsImportedPackageTest(unittest.TestCase):
    def test_existing_admission_and_mutation_cases_use_no_directory_descriptors(self):
        names = (
            "test_original_seven_cases_no_install_and_all_raw_artifacts_retained",
            "test_empty_package_files_are_preserved_and_compared",
            "test_corrupted_package_copy_is_rejected_before_any_configure",
            "test_final_input_check_cannot_accept_or_delete_late_replacement",
            "test_publication_checks_entire_evidence_and_identity",
            "test_unsafe_output_and_member_paths_and_symbolic_package_are_rejected",
        )
        result = unittest.TestResult()
        with patch.object(inventory, "_is_windows", return_value=True), \
                patch.object(verifier, "_is_windows", return_value=True), \
                patch.object(verifier, "_open_directory", side_effect=AssertionError("Unix directory API")):
            unittest.TestSuite(fixtures.ImportedPackageVerifierTest(name) for name in names).run(result)
        self.assertEqual([], result.errors)
        self.assertEqual([], result.failures)
        self.assertEqual(len(names), result.testsRun)

    def test_windows_scan_rejects_empty_directory_changes_and_hash_time_mutation(self):
        fixture = fixtures.ImportedPackageVerifierTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with patch.object(inventory, "_is_windows", return_value=True), \
                patch.object(verifier, "_is_windows", return_value=True):
            before = verifier._package_inventory(fixture.package)
            (fixture.package / "empty").mkdir()
            self.assertNotEqual(before, verifier._package_inventory(fixture.package))
            digest = verifier._regular_file_digest

            def mutate(path, **kwargs):
                result = digest(path, **kwargs)
                (fixture.package / "extra").write_bytes(b"late mutation")
                return result

            with patch.object(verifier, "_regular_file_digest", side_effect=mutate), \
                    self.assertRaisesRegex(ValueError, "tree changed"):
                verifier._package_inventory(fixture.package)

    def test_windows_reparse_member_and_parent_are_rejected(self):
        fixture = fixtures.ImportedPackageVerifierTest()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        for rejected in (fixture.package, fixture.package / fixture.library):
            identity = rejected.stat().st_ino
            with self.subTest(path=rejected), \
                    patch.object(inventory, "_is_windows", return_value=True), \
                    patch.object(verifier, "_is_windows", return_value=True), \
                    patch.object(inventory, "_is_reparse_point", side_effect=lambda s: s.st_ino == identity), \
                    self.assertRaisesRegex(ValueError, "unsafe"):
                verifier._package_inventory(fixture.package)


if __name__ == "__main__":
    unittest.main()
