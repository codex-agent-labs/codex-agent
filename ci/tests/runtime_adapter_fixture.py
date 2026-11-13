"""Synthetic host reports and process captures, never execution/admission proof.

Existing artifact inspectors verify the fixture archives. No product compiler,
runtime process, signer, receipt writer, or hosted runner is invoked here.
"""

import base64
from pathlib import Path

from ci.products.inventory import load_canonical_json_bytes, write_canonical_json
from ci.products.runtime_evidence import (
    DESKTOP_RUNTIME_TEST_CLASS, DESKTOP_RUNTIME_TEST_METHODS,
    NODE_RUNTIME_TEST_CLASS, NODE_RUNTIME_TEST_METHODS, PINNED_NODE_VERSION,
    RUNTIME_TARGETS,
)
from ci.tests.test_runtime_evidence import RuntimeEvidenceFixture


class AdapterHostFixture:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.fixture = RuntimeEvidenceFixture(self.root)
        self._reports = {}
        self._inputs = {}

    def inputs(self, component: str, target: str) -> dict:
        """Return original verifier inputs; repeat calls never rewrite mutations."""
        if component not in {"jvm", "node-js", "node-wasm"} or target not in RUNTIME_TARGETS:
            raise ValueError("Unsupported synthetic adapter host")
        identity = (component, target)
        if identity in self._inputs:
            return dict(self._inputs[identity])
        if component not in self._reports:
            paths = (self.fixture.write_jvm() if component == "jvm"
                     else self.fixture.write_node("js" if component == "node-js" else "wasm"))
            self._reports[component] = {
                load_canonical_json_bytes(path.read_bytes())["target"]: path for path in paths
            }
        report = self._reports[component][target]
        execution = report.with_name(f"{report.stem}-execution.json")
        is_jvm = component == "jvm"
        test_class = DESKTOP_RUNTIME_TEST_CLASS if is_jvm else NODE_RUNTIME_TEST_CLASS
        methods = DESKTOP_RUNTIME_TEST_METHODS if is_jvm else NODE_RUNTIME_TEST_METHODS
        if is_jvm:
            junit = self.root / f"TEST-jvm-runtime-{target}.xml"
            runner = self.fixture.jvm_runner
        else:
            prefix = "nodeRuntime" if component == "node-js" else "nodeWasmRuntime"
            junit = self.root / f"TEST-{prefix}{target[0].upper()}{target[1:]}Test.{test_class}.xml"
            runner = self.fixture.node_runner if component == "node-js" else self.fixture.wasm_runner

        def capture(identifier, raw):
            return {"id": identifier, "exitCode": 0,
                    "outputBase64": base64.b64encode(raw).decode("ascii")}

        executions = [] if is_jvm else [capture("version", f"v{PINNED_NODE_VERSION}\n".encode())]
        listing = f"{test_class}.\n" + "".join(f"  {method}\n" for method in methods)
        executions.append(capture("discovery", listing.encode()))
        executions.extend(capture(method, b"" if index == len(methods) - 1
                                  else b"\xff\x00Synthetic adapter execution fixture\r\n")
                          for index, method in enumerate(methods))
        write_canonical_json(execution, {
            "schemaVersion": 1, "component": component, "target": target,
            "testClass": test_class, "executions": executions,
        })
        junit.write_text(
            f'<testsuite tests="{len(methods)}" skipped="0" failures="0" errors="0">\n'
            + "".join(f'  <testcase classname="{test_class}" name="{method}"/>\n' for method in methods)
            + "</testsuite>\n", encoding="utf-8", newline="\n",
        )
        self._inputs[identity] = {
            "component": component, "target": target, "commit": self.fixture.commits[target],
            "report": report, "execution": execution, "junit": junit,
            "distribution_manifest": self.fixture.manifest_path,
            "classifier": self.fixture.classifiers[target], "runner": runner,
        }
        return dict(self._inputs[identity])
