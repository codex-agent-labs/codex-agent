"""Original JVM/Node host-result checks; no receipt, index or hosted-trust token."""

from __future__ import annotations

import base64
from pathlib import Path
import tempfile
from typing import Any
import xml.etree.ElementTree as ET

from .inventory import load_json_bytes, read_regular_file_bytes, require_array, require_exact_keys, require_integer
from .runtime_evidence import (
    DESKTOP_RUNTIME_TEST_CLASS, DESKTOP_RUNTIME_TEST_METHODS, NODE_RUNTIME_TEST_CLASS,
    PINNED_NODE_VERSION, PRODUCT_RUNTIME_TARGETS, RUNTIME_ADAPTER_COMPONENTS, RUNTIME_TARGETS,
    inspect_classifier, jvm_evidence_filename, node_evidence_filename,
    read_distribution_manifest, verify_adapter_report,
)
from .test_results import CanonicalTestStatus, read_canonical_test_report


def verify_adapter_host_evidence(
    *, component: str, target: str, commit: str, report: Path, execution: Path,
    junit: Path, distribution_manifest: Path, classifier: Path, runner: Path,
) -> dict[str, Any]:
    """Read one private snapshot, retaining every original input unchanged.

    This semantic primitive must be composed with authenticated original stages
    and receipts before any caller may use its result for content comparison.
    """
    if component not in RUNTIME_ADAPTER_COMPONENTS or target not in RUNTIME_TARGETS:
        raise ValueError("Adapter host evidence component/target mismatch")
    sources = dict(report=report, execution=execution, junit=junit,
                   distribution_manifest=distribution_manifest, classifier=classifier, runner=runner)
    with tempfile.TemporaryDirectory(prefix="runtime-adapter-host-") as temporary:
        captured = {}
        for name, path in sources.items():
            path = Path(path)
            contents = read_regular_file_bytes(path, max_bytes=1024 * 1024 * 1024,
                                               reject_symlink_parents=True)
            destination = Path(temporary) / name / path.name
            destination.parent.mkdir()
            destination.write_bytes(contents)
            captured[name] = destination
        return _verify_adapter_host_snapshot(component, target, commit, **captured)


def _verify_adapter_host_snapshot(
    component: str, target: str, commit: str, *, report: Path, execution: Path,
    junit: Path, distribution_manifest: Path, classifier: Path, runner: Path,
) -> dict[str, Any]:
    backend = component.removeprefix("node-")
    report_name = jvm_evidence_filename(target) if component == "jvm" else node_evidence_filename(target, backend)
    test_class = DESKTOP_RUNTIME_TEST_CLASS if component == "jvm" else NODE_RUNTIME_TEST_CLASS
    prefix = "nodeRuntime" if component == "node-js" else "nodeWasmRuntime"
    junit_name = (f"TEST-jvm-runtime-{target}.xml" if component == "jvm" else
                  f"TEST-{prefix}{target[0].upper() + target[1:]}Test.{test_class}.xml")
    if (report.name != report_name or execution.name != report_name.removesuffix(".json") + "-execution.json"
            or junit.name != junit_name):
        raise ValueError("Adapter original evidence filename mismatch")
    proof = inspect_classifier(target, read_distribution_manifest(distribution_manifest), classifier)
    value = verify_adapter_report(report, component, target, commit, proof, runner)
    verify_runtime_process_capture(execution, component, target, test_class)
    cases = read_canonical_test_report(junit)
    expected_cases = {f"{test_class}#{method}" for method in DESKTOP_RUNTIME_TEST_METHODS}
    if (len(cases) != len(expected_cases) or {case.test_id for case in cases} != expected_cases
            or any(case.status != CanonicalTestStatus.PASSED for case in cases)):
        raise ValueError("Adapter JUnit case inventory/result mismatch")
    return _verify_adapter_report_format(value, junit, component)


def verify_runtime_process_capture(execution: Path, component: str, target: str, test_class: str) -> None:
    """Shared original process gate; caller supplies authenticated component/host."""
    if target not in RUNTIME_TARGETS or (component not in RUNTIME_ADAPTER_COMPONENTS
            and component != PRODUCT_RUNTIME_TARGETS[target]):
        raise ValueError("Runtime raw execution component/target mismatch")
    raw = require_exact_keys(load_json_bytes(read_regular_file_bytes(execution)),
                             {"schemaVersion", "component", "target", "testClass", "executions"},
                             "Adapter raw execution")
    if (require_integer(raw["schemaVersion"], "execution schema", minimum=1) != 1
            or raw["component"] != component or raw["target"] != target or raw["testClass"] != test_class):
        raise ValueError("Adapter raw execution identity mismatch")
    entries = require_array(raw["executions"], "Adapter executions")
    ids = (["version"] if component in {"node-js", "node-wasm"} else []) + ["discovery", *DESKTOP_RUNTIME_TEST_METHODS]
    if len(entries) != len(ids):
        raise ValueError("Adapter raw execution inventory is incomplete")
    for entry, expected in zip(entries, ids, strict=True):
        entry = require_exact_keys(entry, {"id", "exitCode", "outputBase64"}, "Adapter execution")
        if (entry["id"] != expected or type(entry["exitCode"]) is not int or entry["exitCode"] != 0
                or type(entry["outputBase64"]) is not str):
            raise ValueError("Adapter raw execution order or result mismatch")
        try:
            output = base64.b64decode(entry["outputBase64"], validate=True)
            if base64.b64encode(output).decode("ascii") != entry["outputBase64"]:
                raise ValueError("Adapter execution output is not canonical base64")
            if expected in {"version", "discovery"}:
                text = output.decode("utf-8").replace("\r", "")
                if expected == "version" and text.strip() != f"v{PINNED_NODE_VERSION}":
                    raise ValueError("Adapter raw Node version mismatch")
                if expected == "discovery":
                    lines = [line for line in text.split("\n") if line.strip()]
                    if component in PRODUCT_RUNTIME_TARGETS.values():
                        # Native test executables also contain the independently
                        # verified C-ABI suites; select exactly the Desktop class.
                        if lines.count(f"{test_class}.") != 1:
                            raise ValueError("Native Desktop test class is missing or duplicated")
                        start = lines.index(f"{test_class}.") + 1
                        methods = []
                        for line in lines[start:]:
                            if not line.startswith("  "):
                                break
                            methods.append(line.strip())
                        if len(methods) != len(DESKTOP_RUNTIME_TEST_METHODS) or set(methods) != set(DESKTOP_RUNTIME_TEST_METHODS):
                            raise ValueError("Native Desktop raw discovered tests mismatch")
                    elif lines != [f"{test_class}.", *(f"  {method}" for method in DESKTOP_RUNTIME_TEST_METHODS)]:
                        raise ValueError("Adapter raw discovered tests mismatch")
        except (UnicodeError, ValueError) as error:
            raise ValueError("Adapter raw process output is invalid") from error


def _verify_adapter_report_format(value: dict[str, Any], junit: Path, component: str) -> dict[str, Any]:
    # The shared secure parser above rejects declarations before this exact producer-format check.
    suite = ET.fromstring(read_regular_file_bytes(junit))
    if (suite.tag != "testsuite" or any(suite.get(key) != expected for key, expected in
            (("tests", "4"), ("skipped", "0"), ("failures", "0"), ("errors", "0")))
            or any(list(suite.iter(tag)) for tag in ("skipped", "failure", "error"))
            or {case.get("name") for case in suite.iter("testcase")} != set(DESKTOP_RUNTIME_TEST_METHODS)):
        raise ValueError("Adapter JUnit exact suite result mismatch")
    return {"schemaVersion": 1, "component": component,
            "report": {key: item for key, item in value.items() if key not in {"candidateCommit", "testTask"}}}
