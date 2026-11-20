"""Android metadata writer checks; fixtures grant no original authority."""

from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products import sdk_android_metadata as metadata
from ci.products.inventory import canonical_json_bytes, write_canonical_json
from ci.products.plan import _upstream_record
from ci.products.receipt import output_inventory_digest, write_output_manifest
from ci.products.sdk_android_validation_content import android_validation_content
from ci.tests.product_chain_support import write_receipt


class AndroidMetadataWriterTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="android-metadata-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.version = "0.8.7"
        self.context = {"producer": {
            "repository": "fixture/repository", "commit": "a" * 40, "tree": "b" * 40,
            "event": "local", "workflowPath": None, "runId": None,
            "runAttempt": None, "pullRequest": None,
        }}
        self.package_stage = self.root / "package-stage"
        payload = self.package_stage / "outputs/maven/package.bin"
        payload.parent.mkdir(parents=True)
        payload.write_bytes(b"synthetic package")
        package_manifest = write_output_manifest(
            self.package_stage, "sdk", "sdk-android", "package", "android", self.version,
            {"maven": "outputs/maven"})
        self.package_receipt = self.root / "package.json"
        self.package = write_receipt(
            self.package_receipt, product="sdk", component="sdk-android", phase="package",
            target="android", version=self.version, version_identity=self.version,
            outputs=package_manifest["outputs"], upstream=[], context=self.context)
        self.release = "sha256:" + "a" * 64
        self.runtime = "sha256:" + "b" * 64
        self.validation_content = android_validation_content(
            sdk_version=self.version,
            package_outputs_digest=output_inventory_digest(self.package["outputs"]),
            release_aar_sha256=self.release, bundled_runtime_sha256=self.runtime)
        self.validation_stage = self.root / "validation-stage"
        validation = self.validation_stage / metadata._VALIDATION_PATH
        validation.parent.mkdir(parents=True)
        validation.write_bytes(canonical_json_bytes(self.validation_content))
        validation_manifest = write_output_manifest(
            self.validation_stage, "sdk", "sdk-android", "validation", "android", self.version,
            {metadata._VALIDATION_KIND: "outputs/validation"},
            expected_output_paths=[metadata._VALIDATION_PATH])
        self.validation_receipt = self.root / "validation.json"
        self.validation = write_receipt(
            self.validation_receipt, product="sdk", component="sdk-android", phase="validation",
            target="android", version=self.version, version_identity=self.version,
            outputs=validation_manifest["outputs"], upstream=[_upstream_record(self.package)],
            context=self.context)
        self.request = {
            "sdkVersion": self.version,
            "packageStage": str(self.package_stage), "packageReceipt": str(self.package_receipt),
            "validationStage": str(self.validation_stage), "validationReceipt": str(self.validation_receipt),
            "releaseAarSha256": self.release, "bundledRuntimeSha256": self.runtime,
        }
        self.request_path = self.root / "request.json"
        self.output = self.root / "result/content.json"
        self.save_request()

    def save_request(self):
        write_canonical_json(self.request_path, self.request)

    def write_validation(self, *, upstream=None, kind=None, content=None, version=None):
        content = self.validation_content if content is None else content
        path = self.validation_stage / metadata._VALIDATION_PATH
        path.write_bytes(canonical_json_bytes(content))
        manifest = write_output_manifest(
            self.validation_stage, "sdk", "sdk-android", "validation", "android",
            self.version if version is None else version,
            {metadata._VALIDATION_KIND if kind is None else kind: "outputs/validation"},
            expected_output_paths=[metadata._VALIDATION_PATH])
        self.validation = write_receipt(
            self.validation_receipt, product="sdk", component="sdk-android", phase="validation",
            target="android", version=self.version if version is None else version,
            version_identity=self.version if version is None else version,
            outputs=manifest["outputs"],
            upstream=[_upstream_record(self.package)] if upstream is None else upstream,
            context=self.context)

    def test_writer_and_cli_emit_exact_deterministic_content(self):
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result = metadata.write_android_metadata_content(self.request_path, self.output)
        self.assertEqual(canonical_json_bytes(result), self.output.read_bytes())
        self.assertEqual(self.validation_content, result["validation"])
        self.assertEqual(output_inventory_digest(self.package["outputs"]), result["packageOutputsDigest"])
        self.assertEqual((self.release, self.runtime),
                         (result["releaseAarSha256"], result["bundledRuntimeSha256"]))
        self.assertEqual(before, {path: path.read_bytes() for path in before})
        second = self.root / "second.json"
        self.assertEqual(0, metadata.main(["--request", str(self.request_path), "--output", str(second)]))
        self.assertEqual(self.output.read_bytes(), second.read_bytes())

    def test_exact_receipt_stage_identity_singleton_and_package_lineage_are_required(self):
        self.write_validation(version="0.8.8")
        with self.assertRaisesRegex(ValueError, "phase/version"):
            metadata.write_android_metadata_content(self.request_path, self.output)
        self.write_validation()
        self.write_validation(upstream=[])
        with self.assertRaisesRegex(ValueError, "package lineage"):
            metadata.write_android_metadata_content(self.request_path, self.output)
        self.write_validation(kind="wrong-kind")
        with self.assertRaisesRegex(ValueError, "singleton"):
            metadata.write_android_metadata_content(self.request_path, self.output)
        self.write_validation()
        (self.validation_stage / metadata._VALIDATION_PATH).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            metadata.write_android_metadata_content(self.request_path, self.output)
        self.assertFalse(self.output.exists())

    def test_independent_expected_digests_and_canonical_validation_must_match(self):
        for field in ("releaseAarSha256", "bundledRuntimeSha256"):
            original = self.request[field]
            self.request[field] = "sha256:" + "e" * 64
            self.save_request()
            with self.subTest(field=field), self.assertRaises(ValueError):
                metadata.write_android_metadata_content(self.request_path, self.output)
            self.request[field] = original
        self.save_request()
        path = self.validation_stage / metadata._VALIDATION_PATH
        path.write_bytes(path.read_bytes() + b" ")
        manifest = write_output_manifest(
            self.validation_stage, "sdk", "sdk-android", "validation", "android", self.version,
            {metadata._VALIDATION_KIND: "outputs/validation"},
            expected_output_paths=[metadata._VALIDATION_PATH])
        write_receipt(self.validation_receipt, product="sdk", component="sdk-android", phase="validation",
            target="android", version=self.version, version_identity=self.version,
            outputs=manifest["outputs"], upstream=[_upstream_record(self.package)], context=self.context)
        with self.assertRaises(ValueError):
            metadata.write_android_metadata_content(self.request_path, self.output)

    def test_request_paths_and_output_are_strict_fresh_and_no_clobber(self):
        existing = self.root / "existing.json"
        existing.write_bytes(b"preserve")
        alias = self.root / "alias"
        alias.symlink_to(self.root / "result", target_is_directory=True)
        for output in (existing, self.request_path, self.package_receipt,
                       self.package_stage / "nested.json", self.validation_stage / "nested.json",
                       alias / "content.json"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                metadata.write_android_metadata_content(self.request_path, output)
        self.assertEqual(b"preserve", existing.read_bytes())
        self.request["packageStage"] = "relative-stage"
        self.save_request()
        with self.assertRaises(ValueError):
            metadata.write_android_metadata_content(self.request_path, self.output)

    def test_original_mutation_and_racing_output_reject_without_overwrite(self):
        join = metadata.android_metadata_content
        for original in (self.request_path, self.package_receipt,
                         self.validation_stage / metadata._VALIDATION_PATH):
            raw = original.read_bytes()
            def mutate(**kwargs):
                result = join(**kwargs)
                original.write_bytes(raw + b" ")
                return result
            with self.subTest(original=original), patch.object(
                    metadata, "android_metadata_content", side_effect=mutate), \
                    self.assertRaisesRegex(ValueError, "changed"):
                metadata.write_android_metadata_content(self.request_path, self.output)
            self.assertFalse(self.output.exists())
            original.write_bytes(raw)

        link = os.link
        def race(source, destination, **kwargs):
            Path(destination).write_bytes(b"concurrent owner")
            return link(source, destination, **kwargs)
        with patch.object(metadata.os, "link", side_effect=race), self.assertRaises(FileExistsError):
            metadata.write_android_metadata_content(self.request_path, self.output)
        self.assertEqual(b"concurrent owner", self.output.read_bytes())

    def test_cli_rejects_unknown_abbreviated_and_noncanonical_requests(self):
        cases = [
            ["--req", str(self.request_path), "--output", str(self.output)],
            ["--request", str(self.request_path), "--output", str(self.output), "--extra"],
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments), redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                metadata.main(arguments)
            self.assertEqual(2, error.exception.code)
        self.request_path.write_bytes(self.request_path.read_bytes() + b" ")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            metadata.main(["--request", str(self.request_path), "--output", str(self.output)])
        self.assertEqual(2, error.exception.code)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
