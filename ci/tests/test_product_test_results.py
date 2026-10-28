from __future__ import annotations

from pathlib import Path
import contextlib
import io
import json
import tempfile
import unittest

from ci.products.test_results import (
    CanonicalTestResult,
    CanonicalTestStatus,
    main,
    read_canonical_test_report,
    read_canonical_test_results,
)


class ProductTestResultsTest(unittest.TestCase):
    def test_results_are_status_aware_normalized_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="product-test-results-") as temporary:
            root = Path(temporary)
            self._write(
                root / "z/TEST-second.xml",
                """
                <testsuite xmlns="urn:junit">
                  <testcase classname="fixture.CoverageTest" name="skipped()[jvm]"><skipped/></testcase>
                  <testcase classname="fixture.CoverageTest" name="failed"><failure message="no"/></testcase>
                </testsuite>
                """,
            )
            self._write(
                root / "a/TEST-first.xml",
                """
                <testsuite>
                  <testcase classname="fixture.CoverageTest" name="passed()[jvm]"><system-out>ok</system-out></testcase>
                  <testcase classname="fixture.CoverageTest" name="errored"><error/></testcase>
                </testsuite>
                """,
            )
            self._write(root / "TEST-ignored.XML", "<not-xml")
            self._write(root / "other.xml", "<not-xml")

            self.assertEqual(
                [
                    CanonicalTestResult("fixture.CoverageTest#errored", CanonicalTestStatus.FAILED),
                    CanonicalTestResult("fixture.CoverageTest#failed", CanonicalTestStatus.FAILED),
                    CanonicalTestResult("fixture.CoverageTest#passed", CanonicalTestStatus.PASSED),
                    CanonicalTestResult("fixture.CoverageTest#skipped", CanonicalTestStatus.SKIPPED),
                ],
                read_canonical_test_results(root),
            )

    def test_duplicate_test_identities_are_rejected_in_sorted_order(self) -> None:
        with tempfile.TemporaryDirectory(prefix="product-test-duplicates-") as temporary:
            root = Path(temporary)
            self._write(
                root / "TEST-one.xml",
                "<testsuite><testcase classname='z.Class' name='same'/></testsuite>",
            )
            self._write(
                root / "nested/TEST-two.xml",
                "<testsuite><testcase classname='z.Class' name='same()'><failure/></testcase></testsuite>",
            )

            with self.assertRaisesRegex(
                ValueError,
                r"identities are ambiguous: \[z\.Class#same\]",
            ):
                read_canonical_test_results(root)

    def test_missing_non_directory_and_empty_inputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="product-test-inputs-") as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "directory is missing"):
                read_canonical_test_results(root / "missing")
            file = root / "file"
            file.write_text("not a directory", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "directory is missing"):
                read_canonical_test_results(file)
            empty = root / "empty"
            empty.mkdir()
            self._write(empty / "unrelated.xml", "<testsuite/>")
            with self.assertRaisesRegex(ValueError, "reports are missing"):
                read_canonical_test_results(empty)

    def test_symlinked_reports_and_directories_are_not_report_identities(self) -> None:
        with tempfile.TemporaryDirectory(prefix="product-test-symlinks-") as temporary:
            workspace = Path(temporary)
            root = workspace / "results"
            root.mkdir()
            actual = workspace / "actual"
            actual.mkdir()
            report = actual / "TEST-actual.xml"
            self._write(report, "<testsuite><testcase classname='fixture.Test' name='ok'/></testsuite>")
            linked_root = root / "linked-root"
            linked_report = root / "TEST-linked.xml"
            linked_directory = root / "linked-directory"
            try:
                linked_root.symlink_to(actual, target_is_directory=True)
                linked_report.symlink_to(report)
                linked_directory.symlink_to(actual, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("symlinks are unavailable")

            with self.assertRaisesRegex(ValueError, "directory is missing"):
                read_canonical_test_results(linked_root)
            with self.assertRaisesRegex(ValueError, "missing, non-regular, or a symlink"):
                read_canonical_test_report(linked_report)
            with self.assertRaisesRegex(ValueError, "reports are missing"):
                read_canonical_test_results(root)

    def test_report_identity_root_and_testcase_identity_are_strict(self) -> None:
        with tempfile.TemporaryDirectory(prefix="product-test-identity-") as temporary:
            root = Path(temporary)
            wrong_extension = root / "TEST-report.txt"
            self._write(wrong_extension, "<testsuite/>")
            with self.assertRaisesRegex(ValueError, "missing, non-regular, or a symlink"):
                read_canonical_test_report(wrong_extension)

            wrong_root = root / "wrong.xml"
            self._write(wrong_root, "<testsuites><testsuite/></testsuites>")
            with self.assertRaisesRegex(ValueError, "no testsuite root"):
                read_canonical_test_report(wrong_root)

            for index, testcase in enumerate((
                "<testcase classname='' name='method'/>",
                "<testcase classname='fixture.Test' name='()[jvm]'/>",
                "<testcase classname='  ' name='method'/>",
            )):
                report = root / f"invalid-{index}.xml"
                self._write(report, f"<testsuite>{testcase}</testsuite>")
                with self.subTest(testcase=testcase), self.assertRaisesRegex(
                    ValueError,
                    "testcase identity is invalid",
                ):
                    read_canonical_test_report(report)

    def test_only_direct_terminal_elements_determine_status_and_conflicts_fail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="product-test-terminals-") as temporary:
            root = Path(temporary)
            accepted = root / "accepted.xml"
            self._write(
                accepted,
                """
                <testsuite>
                  <testcase classname="fixture.Test" name="nested"><wrapper><failure/></wrapper></testcase>
                  <testcase classname="fixture.Test" name="one"><failure><error/></failure></testcase>
                </testsuite>
                """,
            )
            self.assertEqual(
                [
                    CanonicalTestResult("fixture.Test#nested", CanonicalTestStatus.PASSED),
                    CanonicalTestResult("fixture.Test#one", CanonicalTestStatus.FAILED),
                ],
                read_canonical_test_report(accepted),
            )

            for index, body in enumerate((
                "<skipped/><failure/>",
                "<failure/><error/>",
                "<skipped/><skipped/>",
            )):
                report = root / f"conflict-{index}.xml"
                self._write(
                    report,
                    f"<testsuite><testcase classname='fixture.Test' name='conflict'>{body}</testcase></testsuite>",
                )
                with self.subTest(body=body), self.assertRaisesRegex(
                    ValueError,
                    "testcase has conflicting results: fixture.Test#conflict",
                ):
                    read_canonical_test_report(report)

    def test_doctype_entities_external_references_and_malformed_xml_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="product-test-xml-") as temporary:
            root = Path(temporary)
            secret = root / "secret.txt"
            secret.write_text("must-not-be-read", encoding="utf-8")
            reports = (
                "<!DOCTYPE testsuite><testsuite/>",
                "<!DOCTYPE testsuite [<!ENTITY value 'expanded'>]><testsuite>&value;</testsuite>",
                (
                    "<!DOCTYPE testsuite [<!ENTITY value SYSTEM "
                    f"'{secret.as_uri()}'>]><testsuite>&value;</testsuite>"
                ),
            )
            for index, contents in enumerate(reports):
                report = root / f"forbidden-{index}.xml"
                self._write(report, contents)
                with self.subTest(contents=contents), self.assertRaisesRegex(
                    ValueError,
                    "forbidden XML declaration",
                ):
                    read_canonical_test_report(report)

            malformed = root / "malformed.xml"
            self._write(malformed, "<testsuite>")
            with self.assertRaisesRegex(ValueError, "report is malformed"):
                read_canonical_test_report(malformed)

    def test_cli_emits_one_canonical_machine_readable_inventory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="product-test-cli-") as temporary:
            root = Path(temporary)
            report = root / "TEST-one.xml"
            self._write(
                report,
                "<testsuite><testcase classname='fixture.Test' name='passes()'/></testsuite>",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(0, main(["--directory", str(root)]))
            self.assertEqual(
                {
                    "schemaVersion": 1,
                    "tests": [{"status": "passed", "testId": "fixture.Test#passes"}],
                },
                json.loads(output.getvalue()),
            )
            self.assertEqual(output.getvalue(), output.getvalue().strip() + "\n")

    @staticmethod
    def _write(path: Path, contents: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents.strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
