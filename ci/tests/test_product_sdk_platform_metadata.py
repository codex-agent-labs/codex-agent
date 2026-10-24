"""Pure Core content joins only; fixtures do not confer original admission."""

from copy import deepcopy
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products import sdk_platform_metadata as metadata
from ci.products.inventory import canonical_json_bytes, write_canonical_json
from ci.products.plan import _upstream_record
from ci.products.receipt import output_inventory_digest, write_output_manifest
from ci.products.registry import (
    PhaseInstanceId, SDK_FACADE_CONTRACT_COMPONENTS, SDK_FACADE_TARGETS,
    phase_instance_dependencies,
)
from ci.products.sdk_facade_validation import FACADE_CONSUMER_TASKS
from ci.tests.product_chain_support import write_receipt


class PlatformMetadataTest(unittest.TestCase):
    def setUp(self):
        self.components = {SDK_FACADE_CONTRACT_COMPONENTS[target]: "sha256:" + f"{index + 1:064x}"
                           for index, target in enumerate(SDK_FACADE_TARGETS)}
        self.contents = {target: {
            "schemaVersion": 1, "kind": "sdk-facade-validation-content", "component": "sdk-core",
            "target": target, "sdkVersion": "0.8.7", "packageOutputsDigest": "sha256:" + "a" * 64,
            "contractDigest": "sha256:" + "b" * 64,
            "componentDigests": [{"component": SDK_FACADE_CONTRACT_COMPONENTS[target],
                                 "sha256": self.components[SDK_FACADE_CONTRACT_COMPONENTS[target]]}],
            "tasks": [FACADE_CONSUMER_TASKS[target]], "result": "passed",
        } for target in SDK_FACADE_TARGETS}
        self.arguments = {
            "sdk_version": "0.8.7", "package_outputs_digest": "sha256:" + "a" * 64,
            "contract_digest": "sha256:" + "b" * 64,
            "expected_component_digests": self.components, "validation_contents": self.contents,
        }

    def test_exact_registry_closure_and_ordered_detached_content(self):
        dependencies = phase_instance_dependencies(PhaseInstanceId("sdk", "sdk-core", "metadata", "common"))
        self.assertEqual({PhaseInstanceId("sdk", "sdk-core", "validation", target)
                          for target in SDK_FACADE_TARGETS}, set(dependencies))
        self.assertEqual(11, len(dependencies))
        before = deepcopy(self.arguments)
        result = metadata.facade_metadata_content(**self.arguments)
        self.assertEqual({"schemaVersion", "kind", "component", "sdkVersion", "packageOutputsDigest",
                          "contractDigest", "validations"}, set(result))
        self.assertEqual((1, "sdk-facade-metadata-content", "sdk-core"),
                         (result["schemaVersion"], result["kind"], result["component"]))
        self.assertEqual([self.contents[target] for target in SDK_FACADE_TARGETS], result["validations"])
        self.assertEqual(result, metadata.validate_facade_metadata_content(result))
        detached = metadata.validate_facade_metadata_content(result)
        detached["validations"][0]["tasks"].clear()
        self.assertTrue(result["validations"][0]["tasks"])
        result["validations"][0]["componentDigests"].clear()
        self.assertEqual(before, self.arguments)

    def test_caller_mapping_order_does_not_change_canonical_content(self):
        expected = canonical_json_bytes(metadata.facade_metadata_content(**self.arguments))
        reversed_inputs = {**self.arguments,
            "validation_contents": dict(reversed(list(self.contents.items()))),
            "expected_component_digests": dict(reversed(list(self.components.items())))}
        self.assertEqual(expected, canonical_json_bytes(metadata.facade_metadata_content(**reversed_inputs)))
        changed = deepcopy(self.arguments)
        component = SDK_FACADE_CONTRACT_COMPONENTS["jvm"]
        changed["expected_component_digests"][component] = "sha256:" + "e" * 64
        changed["validation_contents"]["jvm"]["componentDigests"][0]["sha256"] = "sha256:" + "e" * 64
        self.assertNotEqual(expected, canonical_json_bytes(metadata.facade_metadata_content(**changed)))

    def test_missing_extra_duplicate_or_mislabelled_target_cannot_complete_join(self):
        for mutation in ("missing", "extra", "duplicate", "wrong-key"):
            arguments = deepcopy(self.arguments)
            contents = arguments["validation_contents"]
            if mutation == "missing": del contents["android"]
            elif mutation == "extra": contents["common"] = deepcopy(contents["jvm"])
            elif mutation == "duplicate": contents["android"] = deepcopy(contents["jvm"])
            else: contents["desktop"] = contents.pop("jvm")
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                metadata.facade_metadata_content(**arguments)

    def test_each_target_binds_selected_version_package_contract_and_component(self):
        for target in SDK_FACADE_TARGETS:
            for field, changed in (("sdkVersion", "0.8.8"), ("packageOutputsDigest", "sha256:" + "d" * 64),
                                   ("contractDigest", "sha256:" + "e" * 64), ("componentDigests", [
                                       {"component": SDK_FACADE_CONTRACT_COMPONENTS[target], "sha256": "sha256:" + "f" * 64}])):
                arguments = deepcopy(self.arguments)
                arguments["validation_contents"][target][field] = changed
                with self.subTest(target=target, field=field), self.assertRaises(ValueError):
                    metadata.facade_metadata_content(**arguments)

    def test_expected_component_map_requires_complete_strict_independent_digests(self):
        for mutation in ("missing", "extra", "bad-hash", "bool", "not-map"):
            arguments = deepcopy(self.arguments)
            components = arguments["expected_component_digests"]
            if mutation == "missing": del components["jvm"]
            elif mutation == "extra": components["common"] = "sha256:" + "a" * 64
            elif mutation == "bad-hash": components["jvm"] = "a" * 64
            elif mutation == "bool": components["jvm"] = True
            else: arguments["expected_component_digests"] = list(components)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                metadata.facade_metadata_content(**arguments)

    def test_shape_validator_rejects_unknown_fields_raw_provenance_and_noncanonical_target_lists(self):
        baseline = metadata.facade_metadata_content(**self.arguments)
        for mutation in ("bool-schema", "text-schema", "kind", "component", "extra", "missing",
                         "reordered", "duplicate", "short", "tuple", "raw", "task", "failed", "leaf-schema"):
            value = deepcopy(baseline)
            if mutation == "bool-schema": value["schemaVersion"] = True
            elif mutation == "text-schema": value["schemaVersion"] = "1"
            elif mutation == "kind": value["kind"] = "sdk-android-metadata-content"
            elif mutation == "component": value["component"] = "sdk-android"
            elif mutation == "extra": value["producer"] = {"runId": 123}
            elif mutation == "missing": del value["contractDigest"]
            elif mutation == "reordered": value["validations"].reverse()
            elif mutation == "duplicate": value["validations"][0] = deepcopy(value["validations"][1])
            elif mutation == "short": value["validations"].pop()
            elif mutation == "tuple": value["validations"] = tuple(value["validations"])
            elif mutation == "raw": value["validations"][0]["rawEvidenceSha256"] = "sha256:" + "0" * 64
            elif mutation == "task": value["validations"][0]["tasks"] = ["unrequestedTask"]
            elif mutation == "failed": value["validations"][0]["result"] = "failed"
            else: value["validations"][0]["schemaVersion"] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                metadata.validate_facade_metadata_content(value)

    def test_caller_expectations_are_not_taken_from_validation_data(self):
        for field, value in (("sdk_version", "0.8.8"), ("package_outputs_digest", "sha256:" + "e" * 64),
                             ("contract_digest", "sha256:" + "f" * 64), ("sdk_version", "0.8.7+build"),
                             ("package_outputs_digest", "e" * 64), ("contract_digest", False)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                metadata.facade_metadata_content(**{**self.arguments, field: value})


class PlatformMetadataWriterTest(unittest.TestCase):
    """Real schema/manifest fixtures; no signature or execution admission claimed."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        pure = PlatformMetadataTest(methodName="runTest")
        pure.setUp()
        self.context = {"producer": {
            "repository": "fixture/repository", "commit": "a" * 40, "tree": "b" * 40,
            "event": "local", "workflowPath": None, "runId": None,
            "runAttempt": None, "pullRequest": None,
        }}
        self.stages, self.receipts, self.originals = {}, {}, {}
        self.stage("package", "outputs/package.bin", b"synthetic package", "sdk-package")
        package_digest = output_inventory_digest(self.originals["package"]["outputs"])
        for target in SDK_FACADE_TARGETS:
            content = {**pure.contents[target], "packageOutputsDigest": package_digest}
            self.stage(target, metadata._VALIDATION_PATH, canonical_json_bytes(content),
                       metadata._VALIDATION_KIND)
        self.request = {
            "sdkVersion": "0.8.7", "packageStage": str(self.stages["package"]),
            "packageReceipt": str(self.receipts["package"]),
            "contractDigest": pure.arguments["contract_digest"], "componentDigests": pure.components,
            "validations": {target: {"stageRoot": str(self.stages[target]),
                                     "phaseReceipt": str(self.receipts[target])}
                            for target in SDK_FACADE_TARGETS},
        }
        self.request_path = self.root / "request.json"
        self.output = self.root / "result" / "content.json"
        self.save_request()

    def stage(self, name, relative, contents, kind, *, upstream=None):
        stage = self.root / "stages" / name
        payload = stage / relative
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_bytes(contents)
        phase, target = ("package", "common") if name == "package" else ("validation", name)
        manifest = write_output_manifest(stage, "sdk", "sdk-core", phase, target, "0.8.7", {kind: relative})
        self.stages[name] = stage
        self.receipts[name] = self.root / "receipts" / (name + ".json")
        self.originals[name] = write_receipt(self.receipts[name], product="sdk", component="sdk-core",
            phase=phase, target=target, version="0.8.7", version_identity="0.8.7",
            outputs=manifest["outputs"], context=self.context,
            upstream=upstream if upstream is not None else (
                [] if name == "package" else [_upstream_record(self.originals["package"])]))

    def save_request(self):
        write_canonical_json(self.request_path, self.request)

    def test_writer_and_cli_emit_only_identical_canonical_content(self):
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result = metadata.write_facade_metadata_content(self.request_path, self.output)
        self.assertEqual(canonical_json_bytes(result), self.output.read_bytes())
        self.assertEqual(list(SDK_FACADE_TARGETS), [item["target"] for item in result["validations"]])
        self.assertEqual([self.output], list(self.output.parent.iterdir()))
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        second = self.root / "second.json"
        self.assertEqual(0, metadata.main(["--request", str(self.request_path), "--output", str(second)]))
        self.assertEqual(self.output.read_bytes(), second.read_bytes())

    def test_fresh_output_cannot_clobber_overlap_or_follow_symbols(self):
        existing = self.root / "existing.json"
        existing.write_bytes(b"untouched")
        linked = self.root / "linked"
        linked.symlink_to(self.root / "stages", target_is_directory=True)
        for output in (existing, self.request_path, self.receipts["jvm"],
                       self.stages["package"] / "new.json", self.stages["jvm"] / "new.json",
                       linked / "new.json"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                metadata.write_facade_metadata_content(self.request_path, output)
        self.assertEqual(b"untouched", existing.read_bytes())

    def test_request_requires_exact_eleven_records_and_absolute_paths(self):
        baseline = deepcopy(self.request)
        for mutation in ("missing", "extra", "record-extra", "relative", "policy-extra"):
            self.request = deepcopy(baseline)
            if mutation == "missing": del self.request["validations"]["jvm"]
            elif mutation == "extra": self.request["validations"]["common"] = self.request["validations"]["jvm"]
            elif mutation == "record-extra": self.request["validations"]["jvm"]["trusted"] = True
            elif mutation == "relative": self.request["packageReceipt"] = "receipts/package.json"
            else: self.request["authenticated"] = True
            self.save_request()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                metadata.write_facade_metadata_content(self.request_path, self.output)
            self.assertFalse(self.output.exists())

    def test_receipt_canonical_identity_and_stage_binding(self):
        path = self.receipts["jvm"]
        original = path.read_bytes()
        for mutation in ("noncanonical", "version", "output"):
            value = deepcopy(self.originals["jvm"])
            if mutation == "version": value["productVersion"] = "0.8.8"
            elif mutation == "output": value["outputs"][0]["sha256"] = "sha256:" + "e" * 64
            path.write_bytes(canonical_json_bytes(value) + (b" " if mutation == "noncanonical" else b""))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                metadata.write_facade_metadata_content(self.request_path, self.output)
            self.assertFalse(self.output.exists())
        path.write_bytes(original)

    def test_full_original_package_record_not_just_output_digest_is_required(self):
        payload = (self.stages["jvm"] / metadata._VALIDATION_PATH).read_bytes()
        for field, value in (("buildKey", "sha256:" + "e" * 64),
                             ("outputsDigest", "sha256:" + "f" * 64)):
            record = _upstream_record(self.originals["package"])
            record[field] = value
            self.stage("jvm", metadata._VALIDATION_PATH, payload, metadata._VALIDATION_KIND, upstream=[record])
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "package lineage"):
                metadata.write_facade_metadata_content(self.request_path, self.output)
        self.assertFalse(self.output.exists())

    def test_singleton_kind_and_canonical_content_are_required(self):
        payload = (self.stages["jvm"] / metadata._VALIDATION_PATH).read_bytes()
        self.stage("jvm", metadata._VALIDATION_PATH, payload, "wrong-kind")
        with self.assertRaisesRegex(ValueError, "singleton"):
            metadata.write_facade_metadata_content(self.request_path, self.output)
        self.stage("jvm", metadata._VALIDATION_PATH, payload + b" ", metadata._VALIDATION_KIND)
        with self.assertRaises(ValueError):
            metadata.write_facade_metadata_content(self.request_path, self.output)
        self.assertFalse(self.output.exists())

    def test_original_mutation_during_join_fails_before_publication(self):
        join = metadata.facade_metadata_content
        for original in (self.request_path, self.receipts["jvm"],
                         self.stages["jvm"] / metadata._VALIDATION_PATH):
            raw = original.read_bytes()
            def mutate(**kwargs):
                result = join(**kwargs)
                original.write_bytes(raw + b" ")
                return result
            with self.subTest(original=original), patch.object(metadata, "facade_metadata_content", side_effect=mutate):
                with self.assertRaisesRegex(ValueError, "changed"):
                    metadata.write_facade_metadata_content(self.request_path, self.output)
            self.assertFalse(self.output.exists())
            original.write_bytes(raw)

    def test_atomic_publication_never_overwrites_racing_output(self):
        link = os.link
        def race(source, destination, **kwargs):
            Path(destination).write_bytes(b"concurrent owner")
            return link(source, destination, **kwargs)
        with patch.object(metadata.os, "link", side_effect=race), self.assertRaises(FileExistsError):
            metadata.write_facade_metadata_content(self.request_path, self.output)
        self.assertEqual(b"concurrent owner", self.output.read_bytes())

    def test_cli_rejects_abbreviated_flags_and_reports_invalid_input(self):
        for arguments in (["--req", str(self.request_path), "--output", str(self.output)],
                          ["--request", str(self.root / "missing"), "--output", str(self.output)]):
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                metadata.main(arguments)
            self.assertEqual(2, error.exception.code)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
