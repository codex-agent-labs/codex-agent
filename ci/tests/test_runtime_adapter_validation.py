"""Original raw host evidence fixtures, not signed receipt or execution admission."""

import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory
from ci.products.runtime_adapter_validation import verify_adapter_host_evidence
from ci.products.runtime_evidence import RUNTIME_TARGETS
from ci.tests.runtime_adapter_fixture import AdapterHostFixture
from ci.tests.test_runtime_evidence import digest, write_zip


class RuntimeAdapterValidationTest(unittest.TestCase):
    components = ("jvm", "node-js", "node-wasm")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="adapter-host-validation-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.fixture = AdapterHostFixture(self.root)

    def reject_bytes(self, inputs, name, contents):
        path = inputs[name]
        original = path.read_bytes()
        path.write_bytes(contents)
        before = regular_file_inventory(self.root)
        try:
            with self.assertRaises(ValueError):
                verify_adapter_host_evidence(**inputs)
            self.assertEqual(before, regular_file_inventory(self.root))
        finally:
            path.write_bytes(original)

    def test_all_three_components_and_five_hosts_verify_without_changing_originals(self):
        for component in self.components:
            for target in RUNTIME_TARGETS:
                with self.subTest(component=component, target=target):
                    inputs = self.fixture.inputs(component, target)
                    before = regular_file_inventory(self.root)
                    content = verify_adapter_host_evidence(**inputs)
                    self.assertIsInstance(content, dict)
                    self.assertEqual(content, verify_adapter_host_evidence(**inputs))
                    self.assertEqual(before, regular_file_inventory(self.root))

    def test_host_report_classifier_and_compiled_runner_cross_pairs_fail(self):
        for component in self.components:
            inputs = self.fixture.inputs(component, "linuxX64")
            other = self.fixture.inputs(component, "macosArm64")
            for field in ("report", "execution", "classifier"):
                with self.subTest(component=component, field=field), self.assertRaises(ValueError):
                    verify_adapter_host_evidence(**{**inputs, field: other[field]})
            different = self.fixture.inputs("node-js" if component == "jvm" else "jvm", "linuxX64")
            with self.subTest(component=component, field="runner"), self.assertRaises(ValueError):
                verify_adapter_host_evidence(**{**inputs, "runner": different["runner"]})
            for field in ("classifier", "runner"):
                with self.subTest(component=component, changed=field):
                    self.reject_bytes(inputs, field, inputs[field].read_bytes() + b"changed original package bytes")

    def test_raw_execution_schema_identity_order_and_terminal_results_are_exact(self):
        for component in self.components:
            inputs = self.fixture.inputs(component, "linuxX64")
            original = load_canonical_json_bytes(inputs["execution"].read_bytes())
            mutations = []
            for field, value in (("schemaVersion", 2), ("component", "wrong"),
                                 ("target", "macosArm64"), ("testClass", "Wrong.Class"), ("extra", True)):
                mutations.append({**original, field: value})
            missing = copy.deepcopy(original)
            del missing["testClass"]
            mutations.append(missing)
            for records in ([], original["executions"][:-1], list(reversed(original["executions"])),
                            original["executions"] + [original["executions"][-1]]):
                mutations.append({**original, "executions": records})
            for field, value in (("id", "unobserved"), ("exitCode", 1), ("exitCode", True),
                                 ("exitCode", "0"), ("outputBase64", "!invalid!"),
                                 ("outputBase64", "Zh=="), ("extra", 0)):
                changed = copy.deepcopy(original)
                changed["executions"][-1][field] = value
                mutations.append(changed)
            for index, value in enumerate(mutations):
                with self.subTest(component=component, mutation=index):
                    self.reject_bytes(inputs, "execution", canonical_json_bytes(value))
            duplicate_key = inputs["execution"].read_bytes().replace(b'{', b'{"schemaVersion":1,', 1)
            self.reject_bytes(inputs, "execution", duplicate_key)

    def test_external_capture_formatting_preserves_content_and_exact_original_bytes(self):
        # Kotlin's existing raw evidence writer pretty-prints JSON. External
        # execution bytes are preserved, not forced into canonical payload form.
        for component in self.components:
            inputs = self.fixture.inputs(component, "linuxX64")
            expected = verify_adapter_host_evidence(**inputs)
            raw = inputs["execution"].read_bytes()
            value = load_canonical_json_bytes(raw)
            for formatted in (raw + b"\n", json.dumps(value, indent=4).encode("utf-8") + b"\n\n"):
                inputs["execution"].write_bytes(formatted)
                before = regular_file_inventory(self.root)
                self.assertEqual(expected, verify_adapter_host_evidence(**inputs))
                self.assertEqual(formatted, inputs["execution"].read_bytes())
                self.assertEqual(before, regular_file_inventory(self.root))

    def test_raw_discovery_and_node_version_are_observed_and_exact(self):
        for component in self.components:
            inputs = self.fixture.inputs(component, "linuxX64")
            original = load_canonical_json_bytes(inputs["execution"].read_bytes())
            for execution_id in (["discovery"] if component == "jvm" else ["version", "discovery"]):
                for output in (b"", b"v0.0.0\n", b"unexpected test inventory\n"):
                    changed = copy.deepcopy(original)
                    record = next(item for item in changed["executions"] if item["id"] == execution_id)
                    record["outputBase64"] = base64.b64encode(output).decode("ascii")
                    with self.subTest(component=component, execution=execution_id, output=output):
                        self.reject_bytes(inputs, "execution", canonical_json_bytes(changed))

    def test_junit_failures_skips_duplicates_wrong_class_and_unsafe_xml_fail(self):
        for component in self.components:
            inputs = self.fixture.inputs(component, "linuxX64")
            original = inputs["junit"].read_bytes()
            report = load_canonical_json_bytes(inputs["report"].read_bytes())
            case = (f'<testcase classname="{report["testClass"]}" name="{report["testMethods"][0]}"/>').encode()
            mutations = [
                original.replace(b'skipped="0"', b'skipped="1"'),
                original.replace(b'failures="0"', b'failures="1"'),
                original.replace(b'errors="0"', b'errors="1"'),
                original.replace(report["testClass"].encode(), b"Wrong.Class"),
                original.replace(b"</testsuite>", case + b"</testsuite>"),
                original.replace(b"/>", b"><failure/></testcase>", 1),
                original.replace(b"/>", b"><skipped/></testcase>", 1),
                b'<!DOCTYPE testsuite [<!ENTITY injected "bad">]>' + original,
            ]
            for index, value in enumerate(mutations):
                with self.subTest(component=component, mutation=index):
                    self.assertNotEqual(original, value)
                    self.reject_bytes(inputs, "junit", value)

    def test_missing_and_symbolic_original_inputs_fail(self):
        inputs = self.fixture.inputs("node-js", "linuxX64")
        for field in ("report", "execution", "junit", "distribution_manifest", "classifier", "runner"):
            with self.subTest(field=field, missing=True), self.assertRaises(ValueError):
                verify_adapter_host_evidence(**{**inputs, field: self.root / "missing"})
            symbolic = self.root / f"symbolic-{field}"
            symbolic.symlink_to(inputs[field])
            with self.subTest(field=field, symbolic=True), self.assertRaises(ValueError):
                verify_adapter_host_evidence(**{**inputs, field: symbolic})

    def test_run_commit_and_method_stdout_changes_do_not_change_validated_content(self):
        for component in self.components:
            inputs = self.fixture.inputs(component, "linuxX64")
            expected = verify_adapter_host_evidence(**inputs)
            report = load_canonical_json_bytes(inputs["report"].read_bytes())
            report["candidateCommit"] = "f" * 40
            inputs["report"].write_bytes(canonical_json_bytes(report))
            execution = load_canonical_json_bytes(inputs["execution"].read_bytes())
            execution["executions"][-1]["outputBase64"] = base64.b64encode(
                b"another producer's run path and diagnostic output\x00\xff").decode("ascii")
            inputs["execution"].write_bytes(canonical_json_bytes(execution))
            self.assertEqual(expected, verify_adapter_host_evidence(**{**inputs, "commit": "f" * 40}))

    def test_valid_rebound_compiled_runner_content_remains_meaningful(self):
        for component in self.components:
            inputs = self.fixture.inputs(component, "linuxX64")
            expected = verify_adapter_host_evidence(**inputs)
            with zipfile.ZipFile(inputs["runner"]) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            members[next(iter(members))] += b"different compiled content"
            write_zip(inputs["runner"], members)
            report = load_canonical_json_bytes(inputs["report"].read_bytes())
            prefix = "compiledJvmTestRuntime" if component == "jvm" else "compiledNodeTestRuntime"
            raw = inputs["runner"].read_bytes()
            report[f"{prefix}Bytes"] = len(raw)
            report[f"{prefix}Sha256"] = digest(raw)
            inputs["report"].write_bytes(canonical_json_bytes(report))
            self.assertNotEqual(expected, verify_adapter_host_evidence(**inputs))


if __name__ == "__main__":
    unittest.main()
