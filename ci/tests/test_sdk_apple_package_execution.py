from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci.tests.product_chain_support import output, write_receipt
from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, sha256_bytes
from ci.products.sdk_apple_package_execution import (
    build_apple_package_execution_context, verify_apple_package_execution_context,
)


EVENTS = tuple(
    f"{index:02d}-{name}" for index, name in enumerate((
        "toolchain-before-xcode", "toolchain-before-swift", "device-platform", "device-architecture",
        "simulator-platform", "simulator-architecture", "assemble-xcframework", "device-strip",
        "device-normalize", "device-path-scan", "simulator-strip", "simulator-normalize",
        "simulator-path-scan", "available-libraries", "rewrite-available-libraries",
        "toolchain-after-xcode", "toolchain-after-swift",
    ))
)


class SdkApplePackageExecutionTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="sdk-apple-package-execution-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.producer = {
            "repository": "owner/repository",
            "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40,
            "tree": "b" * 40,
            "event": "pull_request",
            "runId": 7,
            "runAttempt": 2,
            "pullRequest": 3,
        }
        self.context = {"producer": self.producer}
        self.receipts = {
            "package": self.receipt("sdk", "sdk-ios", "package", "ios", "0.8.0"),
            "binary": self.receipt("sdk", "sdk-ios", "binary", "ios", "0.8.0"),
            "contractBinary": self.receipt("contract", "contract", "binary", "common", "0.2.0"),
            "contractMetadata": self.receipt("contract", "contract", "metadata", "common", "0.2.0"),
        }
        self.compatibility = self.root / "sdk-compatibility.json"
        self.compatibility.write_bytes(b'{"schemaVersion":1,"sdkVersion":"0.8.0"}\n')
        self.capture = self.root / "capture"
        self.capture.mkdir()
        (self.capture / "input-binding.json").write_bytes(b'{"schemaVersion":1}\n')
        events = self.capture / "events"
        events.mkdir()
        for event in EVENTS:
            directory = events / event
            directory.mkdir()
            (directory / "combined.bin").write_bytes(b"" if "strip" in event else event.encode())

    def receipt(self, product: str, component: str, phase: str, target: str, version: str) -> Path:
        path = self.root / f"{product}-{component}-{phase}-{target}-{version}.json"
        payload = f"{product}/{component}/{phase}/{target}".encode()
        write_receipt(
            path,
            product=product,
            component=component,
            phase=phase,
            target=target,
            version=version,
            version_identity=version,
            outputs=[output("fixture", "outputs/value.bin", payload)],
            upstream=[],
            context=self.context,
        )
        return path

    def arguments(self):
        return {
            "capture_directory": self.capture,
            "package_receipt": self.receipts["package"],
            "binary_receipt": self.receipts["binary"],
            "contract_binary_receipt": self.receipts["contractBinary"],
            "contract_metadata_receipt": self.receipts["contractMetadata"],
            "producer": self.producer,
            "sdk_compatibility": self.compatibility,
            "sdk_inputs_artifact_id": 11,
            "sdk_inputs_artifact_sha256": "sha256:" + "1" * 64,
        }

    def invoke(self, **changes):
        return build_apple_package_execution_context(**{**self.arguments(), **changes})

    def retained_descriptor(self):
        path = self.root / "apple-package-execution.json"
        path.write_bytes(canonical_json_bytes(self.invoke()))
        return path

    def test_retained_descriptor_verification_preserves_exact_original_bytes(self):
        descriptor = self.retained_descriptor()
        before = regular_file_inventory(self.root, allow_empty=True)
        result = verify_apple_package_execution_context(descriptor, **self.arguments())
        self.assertEqual(result, self.invoke())
        self.assertEqual(canonical_json_bytes(result), descriptor.read_bytes())
        self.assertEqual(before, regular_file_inventory(self.root, allow_empty=True))

    def test_retained_descriptor_rejects_altered_missing_and_unknown_fields(self):
        descriptor = self.retained_descriptor()
        original = descriptor.read_bytes()
        for mutation in ("altered", "missing", "unknown", "nested-unknown"):
            with self.subTest(mutation=mutation):
                descriptor.write_bytes(original)
                verify_apple_package_execution_context(descriptor, **self.arguments())
                value = load_canonical_json_bytes(original)
                if mutation == "altered":
                    value["sdkInputsArtifact"]["artifactId"] += 1
                elif mutation == "missing":
                    del value["receiptSha256"]
                elif mutation == "unknown":
                    value["admitted"] = True
                else:
                    value["sdkInputsArtifact"]["admitted"] = True
                descriptor.write_bytes(canonical_json_bytes(value))
                with self.assertRaisesRegex(ValueError, "differs from caller inputs"):
                    verify_apple_package_execution_context(descriptor, **self.arguments())

    def test_retained_descriptor_rejects_duplicate_noncanonical_and_symbolic_bytes(self):
        descriptor = self.retained_descriptor()
        original = descriptor.read_bytes()
        verify_apple_package_execution_context(descriptor, **self.arguments())
        for changed in (original + b" ", b'{"schemaVersion":1,' + original[1:]):
            with self.subTest(changed=changed[:40]):
                descriptor.write_bytes(changed)
                with self.assertRaises(ValueError):
                    verify_apple_package_execution_context(descriptor, **self.arguments())
        descriptor.write_bytes(original)
        alias = self.root / "descriptor-alias.json"
        alias.symlink_to(descriptor)
        with self.assertRaises(ValueError):
            verify_apple_package_execution_context(alias, **self.arguments())

    def test_retained_descriptor_rejects_current_capture_receipt_and_compatibility_mismatch(self):
        descriptor = self.retained_descriptor()
        paths = (self.capture / "events" / EVENTS[0] / "combined.bin", self.compatibility,
                 self.receipts["binary"])
        for path in paths:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                verify_apple_package_execution_context(descriptor, **self.arguments())
                try:
                    if path == self.receipts["binary"]:
                        value = load_canonical_json_bytes(original)
                        value["producer"]["runId"] += 1
                        path.write_bytes(canonical_json_bytes(value))
                    elif path == self.compatibility:
                        path.write_bytes(canonical_json_bytes({
                            **load_canonical_json_bytes(original), "note": "changed",
                        }))
                    else:
                        path.write_bytes(original + b" ")
                    with self.assertRaisesRegex(ValueError, "differs from caller inputs"):
                        verify_apple_package_execution_context(descriptor, **self.arguments())
                finally:
                    path.write_bytes(original)
        for change in ({"sdk_inputs_artifact_id": 12},
                       {"sdk_inputs_artifact_sha256": "sha256:" + "2" * 64}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "differs from caller inputs"):
                verify_apple_package_execution_context(descriptor, **{**self.arguments(), **change})

    def test_retained_descriptor_rechecks_original_after_real_builder_returns(self):
        descriptor = self.retained_descriptor()
        original = descriptor.read_bytes()
        verify_apple_package_execution_context(descriptor, **self.arguments())

        def mutate(**arguments):
            result = build_apple_package_execution_context(**arguments)
            descriptor.write_bytes(original + b" ")
            return result

        with patch("ci.products.sdk_apple_package_execution.build_apple_package_execution_context", side_effect=mutate):
            with self.assertRaisesRegex(ValueError, "descriptor changed during verification"):
                verify_apple_package_execution_context(descriptor, **self.arguments())

    def test_binds_exact_receipts_compatibility_and_complete_capture_without_verdict(self):
        before = regular_file_inventory(self.capture, allow_empty=True)
        descriptor = self.invoke()
        self.assertEqual({
            "schemaVersion", "kind", "producer", "receiptSha256",
            "sdkCompatibilitySha256", "captureFiles", "sdkInputsArtifact",
        }, set(descriptor))
        self.assertEqual({"artifactId": 11, "artifactSha256": "sha256:" + "1" * 64},
                         descriptor["sdkInputsArtifact"])
        self.assertEqual("apple-package-execution", descriptor["kind"])
        self.assertEqual(self.producer, descriptor["producer"])
        self.assertEqual(before, descriptor["captureFiles"])
        self.assertEqual(sha256_bytes(self.compatibility.read_bytes()), descriptor["sdkCompatibilitySha256"])
        self.assertEqual({
            name: sha256_bytes(path.read_bytes()) for name, path in self.receipts.items()
        }, descriptor["receiptSha256"])
        self.assertNotIn("result", descriptor)
        self.assertNotIn("trust", descriptor)
        self.assertEqual(before, regular_file_inventory(self.capture, allow_empty=True))

    def test_rejects_wrong_identity_producer_and_sdk_version_pair(self):
        cases = []
        wrong_identity = self.receipt("sdk", "sdk-ios", "validation", "ios", "0.8.0")
        cases.append(({"binary_receipt": wrong_identity}, "identity mismatch"))
        wrong_version = self.receipt("sdk", "sdk-ios", "binary", "ios", "0.9.0")
        cases.append(({"binary_receipt": wrong_version}, "versions differ"))
        cases.append(({"producer": {**self.producer, "runAttempt": 4}}, "producer differs"))
        for changes, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self.invoke(**changes)

    def test_rejects_compatibility_for_another_sdk_package_version(self):
        self.compatibility.write_bytes(b'{"schemaVersion":1,"sdkVersion":"0.9.0"}\n')
        with self.assertRaisesRegex(ValueError, "compatibility version differs from package"):
            self.invoke()

    def test_rejects_missing_extra_unsafe_and_empty_capture_members(self):
        for mutation, message in (
            ("missing", "event directory inventory mismatch"),
            ("extra", "capture entry is invalid"),
            ("empty-binding", "missing or empty"),
            ("empty-event", "event is empty"),
            ("unsafe", "unsafe file"),
        ):
            with self.subTest(mutation=mutation):
                with tempfile.TemporaryDirectory(prefix="capture-copy-") as temporary:
                    copied = Path(temporary).resolve() / "capture"
                    shutil.copytree(self.capture, copied)
                    if mutation == "missing":
                        shutil.rmtree(copied / "events" / EVENTS[0])
                    elif mutation == "extra":
                        (copied / "extra").mkdir()
                    elif mutation == "empty-binding":
                        (copied / "input-binding.json").write_bytes(b"")
                    elif mutation == "empty-event":
                        (copied / "events" / EVENTS[0] / "combined.bin").unlink()
                    else:
                        link = copied / "events" / EVENTS[0] / "unsafe-link"
                        link.symlink_to(copied / "input-binding.json")
                    with self.assertRaisesRegex(ValueError, message):
                        self.invoke(capture_directory=copied)

    def test_requires_exact_original_sdk_input_upload_locator(self):
        for changes in ({"sdk_inputs_artifact_id": 0}, {"sdk_inputs_artifact_id": True},
                        {"sdk_inputs_artifact_sha256": "1" * 64}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.invoke(**changes)

    def test_rechecks_capture_receipts_and_compatibility(self):
        real_inventory = regular_file_inventory
        calls = 0

        def mutate_on_recheck(root, **kwargs):
            nonlocal calls
            result = real_inventory(root, **kwargs)
            calls += 1
            if calls == 2:
                self.receipts["package"].write_bytes(self.receipts["package"].read_bytes() + b" ")
            return result

        with patch("ci.products.sdk_apple_package_execution.regular_file_inventory", side_effect=mutate_on_recheck):
            with self.assertRaisesRegex(ValueError, "receipt changed"):
                self.invoke()


if __name__ == "__main__":
    unittest.main()
