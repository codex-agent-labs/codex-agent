"""Pure Core content joins only; fixtures do not confer original admission."""

from copy import deepcopy
import unittest

from ci.products import sdk_platform_metadata as metadata
from ci.products.inventory import canonical_json_bytes
from ci.products.registry import (
    PhaseInstanceId, SDK_FACADE_CONTRACT_COMPONENTS, SDK_FACADE_TARGETS,
    phase_instance_dependencies,
)
from ci.products.sdk_facade_validation import FACADE_CONSUMER_TASKS


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


if __name__ == "__main__":
    unittest.main()
