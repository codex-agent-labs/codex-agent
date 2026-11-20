"""Strict, deterministic JUnit result parsing for product evidence."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import json
import os
from pathlib import Path
import stat
import sys
from xml.dom import Node, minidom
from xml.parsers import expat

from .inventory import read_regular_file_bytes


class CanonicalTestStatus(str, Enum):
    PASSED = "passed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class CanonicalTestResult:
    test_id: str
    status: CanonicalTestStatus


def _is_reparse_point(metadata: os.stat_result) -> bool:
    return bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _is_unsafe_link(metadata: os.stat_result) -> bool:
    return stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata)


def _canonical_reports(results_directory: Path) -> list[Path]:
    root = Path(results_directory)
    try:
        metadata = root.lstat()
    except OSError as error:
        raise ValueError("Canonical test results directory is missing") from error
    if _is_unsafe_link(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("Canonical test results directory is missing")

    reports: list[tuple[str, Path]] = []

    def visit(directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            raise ValueError(f"Canonical test results directory is unsafe: {directory}") from error
        for entry in entries:
            path = Path(entry.path)
            try:
                entry_metadata = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise ValueError(f"Canonical test result changed during discovery: {path}") from error
            if _is_unsafe_link(entry_metadata):
                continue
            if stat.S_ISDIR(entry_metadata.st_mode):
                visit(path)
            elif (
                stat.S_ISREG(entry_metadata.st_mode)
                and entry.name.startswith("TEST-")
                and path.suffix == ".xml"
            ):
                reports.append((path.relative_to(root).as_posix(), path))

    visit(root)
    reports.sort(key=lambda item: item[0])
    if not reports:
        raise ValueError("Canonical JUnit reports are missing")
    return [path for _, path in reports]


def _secure_document(contents: bytes, report: Path):
    def reject_declaration(*_arguments: object) -> None:
        raise ValueError(f"Canonical JUnit report contains a forbidden XML declaration: {report.name}")

    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = reject_declaration
    parser.EntityDeclHandler = reject_declaration
    parser.ExternalEntityRefHandler = reject_declaration
    try:
        parser.Parse(contents, True)
    except ValueError:
        raise
    except expat.ExpatError as error:
        raise ValueError(f"Canonical JUnit report is malformed: {report.name}") from error

    try:
        return minidom.parseString(contents)
    except Exception as error:
        raise ValueError(f"Canonical JUnit report is malformed: {report.name}") from error


def read_canonical_test_report(report: Path) -> list[CanonicalTestResult]:
    path = Path(report)
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ValueError(
            f"Canonical JUnit report is missing, non-regular, or a symlink: {path}",
        ) from error
    if _is_unsafe_link(metadata) or not stat.S_ISREG(metadata.st_mode) or path.suffix != ".xml":
        raise ValueError(f"Canonical JUnit report is missing, non-regular, or a symlink: {path}")

    document = _secure_document(read_regular_file_bytes(path), path)
    try:
        suite = document.documentElement
        if suite is None or suite.tagName != "testsuite":
            raise ValueError(f"Canonical JUnit report has no testsuite root: {path.name}")

        results: list[CanonicalTestResult] = []
        for case in suite.getElementsByTagName("testcase"):
            class_name = case.getAttribute("classname")
            method_name = case.getAttribute("name").split("(", 1)[0]
            if not class_name.strip() or not method_name.strip():
                raise ValueError(f"Canonical JUnit testcase identity is invalid: {path.name}")

            terminal_elements = [
                child.tagName
                for child in case.childNodes
                if child.nodeType == Node.ELEMENT_NODE
            ]
            terminals = [
                name for name in terminal_elements if name in {"skipped", "failure", "error"}
            ]
            test_id = f"{class_name}#{method_name}"
            if len(terminals) > 1:
                raise ValueError(f"Canonical JUnit testcase has conflicting results: {test_id}")
            if any(name in {"failure", "error"} for name in terminal_elements):
                status = CanonicalTestStatus.FAILED
            elif "skipped" in terminal_elements:
                status = CanonicalTestStatus.SKIPPED
            else:
                status = CanonicalTestStatus.PASSED
            results.append(CanonicalTestResult(test_id, status))
        return results
    finally:
        document.unlink()


def read_canonical_test_results(results_directory: Path) -> list[CanonicalTestResult]:
    results = [
        result
        for report in _canonical_reports(Path(results_directory))
        for result in read_canonical_test_report(report)
    ]
    counts: dict[str, int] = {}
    for result in results:
        counts[result.test_id] = counts.get(result.test_id, 0) + 1
    duplicates = sorted(test_id for test_id, count in counts.items() if count != 1)
    if duplicates:
        rendered = f"[{', '.join(duplicates)}]"
        raise ValueError(f"Canonical JUnit test identities are ambiguous: {rendered}")
    return sorted(results, key=lambda result: result.test_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ci.products.test_results")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--directory", type=Path)
    source.add_argument("--report", type=Path)
    arguments = parser.parse_args(argv)
    results = (
        read_canonical_test_results(arguments.directory)
        if arguments.directory is not None
        else read_canonical_test_report(arguments.report)
    )
    document = {
        "schemaVersion": 1,
        "tests": [
            {"status": result.status.value, "testId": result.test_id}
            for result in results
        ],
    }
    sys.stdout.write(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
