"""Pure Android content projections; fixtures grant no execution authority."""

from copy import deepcopy
from pathlib import Path
import re
import unittest

from ci.products import sdk_android_validation_content as content
from ci.products.inventory import canonical_json_bytes


class AndroidValidationContentTest(unittest.TestCase):
    def setUp(self):
        self.arguments = {
            "sdk_version": "0.8.7",
            "package_outputs_digest": "sha256:" + "a" * 64,
            "release_aar_sha256": "sha256:" + "b" * 64,
            "bundled_runtime_sha256": "sha256:" + "c" * 64,
        }

    def test_fixed_test_identities_are_independently_bound_to_kotlin_policy(self):
        repository = Path(__file__).resolve().parents[2]
        kotlin = (repository /
                  "gradle/build-logic/src/main/kotlin/AndroidRuntimeEvidenceSupport.kt")
        self.assertTrue(kotlin.is_file())
        source = kotlin.read_text()
        class_name = re.search(r'ANDROID_RUNTIME_TEST_CLASS\s*=\s*\n?\s*"([^"]+)"', source)
        block = re.search(r'REQUIRED_ANDROID_RUNTIME_TESTS\s*=\s*setOf\((.*?)\)', source, re.S)
        self.assertIsNotNone(class_name)
        self.assertIsNotNone(block)
        self.assertEqual(class_name.group(1), content.ANDROID_RUNTIME_TEST_CLASS)
        self.assertEqual(tuple(sorted(re.findall(r'"([^"]+)"', block.group(1)))),
                         content.ANDROID_RUNTIME_TESTS)

    def test_validation_is_exact_deterministic_detached_content(self):
        first = content.android_validation_content(**self.arguments)
        second = content.android_validation_content(**dict(reversed(list(self.arguments.items()))))
        self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))
        self.assertEqual({"schemaVersion", "kind", "component", "target", "sdkVersion",
                          "packageOutputsDigest", "releaseAarSha256", "bundledRuntimeSha256",
                          "testClassName", "executedTests", "result"}, set(first))
        self.assertEqual(list(content.ANDROID_RUNTIME_TESTS), first["executedTests"])
        detached = content.validate_android_validation_content(first)
        detached["executedTests"].clear()
        self.assertTrue(first["executedTests"])
        serialized = canonical_json_bytes(first).decode()
        for forbidden in ("candidate", "producer", "source", "runid", "matrix", "report", "apk"):
            self.assertNotIn(forbidden, serialized.lower())

    def test_validation_rejects_identity_digest_test_and_raw_provenance_changes(self):
        baseline = content.android_validation_content(**self.arguments)
        mutations = {
            "schema-bool": lambda value: value.update(schemaVersion=True),
            "kind": lambda value: value.update(kind="firebase-runtime-evidence"),
            "component": lambda value: value.update(component="sdk-core"),
            "target": lambda value: value.update(target="common"),
            "version": lambda value: value.update(sdkVersion="0.8"),
            "digest": lambda value: value.update(releaseAarSha256="b" * 64),
            "class": lambda value: value.update(testClassName="AnotherTest"),
            "missing-test": lambda value: value["executedTests"].pop(),
            "reordered-tests": lambda value: value["executedTests"].reverse(),
            "extra-test": lambda value: value["executedTests"].append("invented"),
            "tuple-tests": lambda value: value.update(executedTests=tuple(value["executedTests"])),
            "failed": lambda value: value.update(result="failed"),
            "raw": lambda value: value.update(matrixSha256="sha256:" + "d" * 64),
        }
        for name, mutate in mutations.items():
            value = deepcopy(baseline)
            mutate(value)
            with self.subTest(name=name), self.assertRaises(ValueError):
                content.validate_android_validation_content(value)

    def test_metadata_binds_independent_package_aar_runtime_and_validation(self):
        validation = content.android_validation_content(**self.arguments)
        arguments = {
            "sdk_version": self.arguments["sdk_version"],
            "package_outputs_digest": self.arguments["package_outputs_digest"],
            "expected_release_aar_sha256": self.arguments["release_aar_sha256"],
            "expected_bundled_runtime_sha256": self.arguments["bundled_runtime_sha256"],
            "validation_content": validation,
        }
        metadata = content.android_metadata_content(**arguments)
        self.assertEqual({"schemaVersion", "kind", "component", "sdkVersion",
                          "packageOutputsDigest", "releaseAarSha256", "bundledRuntimeSha256",
                          "validation"}, set(metadata))
        self.assertEqual(validation, metadata["validation"])
        validation["executedTests"].clear()
        self.assertTrue(metadata["validation"]["executedTests"])
        self.assertEqual(metadata, content.validate_android_metadata_content(metadata))

    def test_metadata_rejects_self_selected_or_malformed_nested_identity(self):
        validation = content.android_validation_content(**self.arguments)
        base = dict(sdk_version=self.arguments["sdk_version"],
            package_outputs_digest=self.arguments["package_outputs_digest"],
            expected_release_aar_sha256=self.arguments["release_aar_sha256"],
            expected_bundled_runtime_sha256=self.arguments["bundled_runtime_sha256"],
            validation_content=validation)
        changes = {
            "sdk_version": "0.8.8",
            "package_outputs_digest": "sha256:" + "d" * 64,
            "expected_release_aar_sha256": "sha256:" + "e" * 64,
            "expected_bundled_runtime_sha256": "sha256:" + "f" * 64,
        }
        for field, replacement in changes.items():
            with self.subTest(field=field), self.assertRaises(ValueError):
                content.android_metadata_content(**{**base, field: replacement})
        for mutation in (lambda value: value.update(schemaVersion="1"),
                         lambda value: value.update(kind="sdk-android-validation-content"),
                         lambda value: value.update(component="sdk-core"),
                         lambda value: value.update(producer={"runId": 1}),
                         lambda value: value["validation"].update(result="failed")):
            value = content.android_metadata_content(**base)
            mutation(value)
            with self.assertRaises(ValueError):
                content.validate_android_metadata_content(value)


if __name__ == "__main__":
    unittest.main()
