"""Deterministic Apple content joins, not original producer/host admission."""

from contextlib import redirect_stderr
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products import sdk_apple_metadata as metadata
from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory
from ci.products.receipt import output_inventory_digest, write_output_manifest
from ci.products.sdk_apple_validation_content import apple_validation_content
from ci.tests import test_sdk_apple_validation_content as fixtures


class AppleMetadataTest(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.AppleValidationContentTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.binding_arguments = deepcopy(fixture.arguments)
        self.version = "0.8.7"
        temporary = tempfile.TemporaryDirectory(prefix="apple-metadata-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.stage = self.root / "package"
        payload = self.stage / "outputs/apple/package.zip"
        payload.parent.mkdir(parents=True)
        payload.write_bytes(b"selected deterministic package bytes\n")
        self.manifest = write_output_manifest(self.stage, "sdk", "sdk-ios", "package", "ios", self.version,
                                              {"apple": "outputs/apple"})
        self.package_digest = output_inventory_digest(self.manifest["outputs"])
        self.contents = {target: apple_validation_content(**{
            **self.binding_arguments, "target": target, "sdk_version": self.version,
            "package_outputs_digest": self.package_digest}) for target in ("ios-arm64", "ios-simulator-arm64")}
        self.arguments = {"sdk_version": self.version, "package_outputs_digest": self.package_digest,
            "contract_digest": self.binding_arguments["contract_digest"],
            "expected_canonical": deepcopy(self.binding_arguments["expected_canonical"]),
            "validation_contents": self.contents}
        self.paths = {target: self.root / f"{target}.json" for target in self.contents}
        for target, path in self.paths.items():
            path.write_bytes(canonical_json_bytes(self.contents[target]))
        self.output = self.root / "metadata" / metadata.OUTPUT_PATH
        self.writer_arguments = {"sdk_version": self.version, "package_stage": self.stage,
            "device_validation": self.paths["ios-arm64"], "simulator_validation": self.paths["ios-simulator-arm64"],
            "output": self.output}

    def test_exact_two_target_schema_and_detached_result_without_provenance(self):
        before = deepcopy(self.arguments)
        contents = dict(reversed(list(self.contents.items())))
        value = metadata.apple_metadata_content(**{**self.arguments, "validation_contents": contents})
        self.assertEqual({"schemaVersion", "kind", "component", "sdkVersion", "packageOutputsDigest",
                          "contractDigest", "canonical", "validations"}, set(value))
        self.assertEqual((1, "sdk-apple-metadata-content", "sdk-ios", self.version),
                         (value["schemaVersion"], value["kind"], value["component"], value["sdkVersion"]))
        self.assertEqual([self.contents[target] for target in ("ios-arm64", "ios-simulator-arm64")], value["validations"])
        self.assertEqual(self.package_digest, value["packageOutputsDigest"])
        self.assertEqual(self.arguments["expected_canonical"], value["canonical"])
        self.assertEqual("outputs/evidence/apple-metadata.json", metadata.OUTPUT_PATH)
        self.assertEqual("apple-metadata-content", metadata.OUTPUT_KIND)
        value["validations"][0]["bindings"][0]["claims"].clear()
        value["canonical"]["apiReportSha256"] = "0" * 64
        self.assertEqual(before, self.arguments)

    def test_different_execution_hashes_same_semantics_produce_identical_metadata(self):
        expected = canonical_json_bytes(metadata.apple_metadata_content(**self.arguments))
        raw = deepcopy(self.binding_arguments)
        for receipt in raw["binding_receipts"].values():
            receipt["testProgramSha256"], receipt["testResultsSha256"] = "2" * 64, "3" * 64
            for artifact in receipt["artifacts"]:
                artifact["sha256"] = "4" * 64
        projections = {target: apple_validation_content(**{**raw, "target": target,
            "sdk_version": self.version, "package_outputs_digest": self.package_digest}) for target in self.contents}
        self.assertEqual(expected, canonical_json_bytes(metadata.apple_metadata_content(**{
            **self.arguments, "validation_contents": projections})))
        changed = deepcopy(self.arguments)
        changed["validation_contents"]["ios-arm64"]["bindings"][0]["claims"][0]["publicSymbols"] = ["symbol-b"]
        self.assertNotEqual(expected, canonical_json_bytes(metadata.apple_metadata_content(**changed)))

    def test_targets_versions_package_and_contract_lineage_cannot_be_cross_paired(self):
        for target in self.contents:
            for field, value in (("target", "ios-simulator-arm64" if target == "ios-arm64" else "ios-arm64"),
                                 ("sdkVersion", "0.8.8"), ("packageOutputsDigest", "sha256:" + "9" * 64),
                                 ("contractDigest", "sha256:" + "8" * 64),
                                 ("canonical", {**self.arguments["expected_canonical"], "apiReportSha256": "7" * 64})):
                arguments = deepcopy(self.arguments)
                arguments["validation_contents"][target][field] = value
                with self.subTest(target=target, field=field), self.assertRaises(ValueError):
                    metadata.apple_metadata_content(**arguments)
        for contents in ({"ios-arm64": self.contents["ios-arm64"]},
                         {**self.contents, "ios": self.contents["ios-arm64"]},
                         {"ios-arm64": self.contents["ios-arm64"], "ios-simulator-arm64": self.contents["ios-arm64"]}):
            with self.subTest(targets=list(contents)), self.assertRaises(ValueError):
                metadata.apple_metadata_content(**{**self.arguments, "validation_contents": contents})

    def test_unknown_raw_provenance_and_malformed_semantic_schema_reject(self):
        for mutation in ("producer", "raw", "binding-producer", "language", "test-status", "missing"):
            arguments = deepcopy(self.arguments)
            content = arguments["validation_contents"]["ios-arm64"]
            if mutation == "producer": content["producer"] = {"runId": 71}
            elif mutation == "raw": content["bindings"][0]["testResultsSha256"] = "0" * 64
            elif mutation == "binding-producer": content["bindings"][0]["producer"] = "original"
            elif mutation == "language": content["bindings"].reverse()
            elif mutation == "test-status": content["bindings"][0]["tests"][0]["status"] = "failed"
            else: del content["canonical"]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                metadata.apple_metadata_content(**arguments)

    def test_writer_and_cli_preserve_original_bytes_and_emit_only_canonical_content(self):
        before = regular_file_inventory(self.root)
        argv = [part for key, value in self.writer_arguments.items() for part in ("--" + key.replace("_", "-"), str(value))]
        self.assertEqual(0, metadata.main(argv))
        expected = metadata.apple_metadata_content(**self.arguments)
        self.assertEqual(canonical_json_bytes(expected), self.output.read_bytes())
        self.assertEqual(expected, load_canonical_json_bytes(self.output.read_bytes()))
        relative = self.output.relative_to(self.root).as_posix()
        self.assertEqual(before, [row for row in regular_file_inventory(self.root) if row["relativePath"] != relative])
        second = self.root / "other/content.json"
        metadata.write_apple_metadata_content(**{**self.writer_arguments, "output": second})
        self.assertEqual(self.output.read_bytes(), second.read_bytes())

    def test_noncanonical_files_and_tampered_package_never_publish(self):
        path = self.paths["ios-arm64"]
        original = path.read_bytes()
        for raw in (original.rstrip(b"\n"), original.replace(b'"schemaVersion":1', b'"schemaVersion":1,"schemaVersion":1')):
            path.write_bytes(raw)
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                metadata.write_apple_metadata_content(**self.writer_arguments)
            self.assertFalse(self.output.exists())
        path.write_bytes(original)
        (self.stage / "outputs/apple/package.zip").write_bytes(b"changed selected package")
        with self.assertRaises(ValueError): metadata.write_apple_metadata_content(**self.writer_arguments)
        self.assertFalse(self.output.exists())

    def test_verifier_or_writer_input_mutation_prevents_publication(self):
        original_join, original_write = metadata.apple_metadata_content, metadata.write_canonical_json
        for seam in ("join", "write"):
            path = self.paths["ios-simulator-arm64"]
            raw = path.read_bytes()
            def join(**arguments):
                result = original_join(**arguments)
                path.write_bytes(b"late mutation")
                return result
            def write(destination, value):
                original_write(destination, value)
                path.write_bytes(b"late mutation")
            with self.subTest(seam=seam), patch.object(metadata,
                    "apple_metadata_content" if seam == "join" else "write_canonical_json",
                    side_effect=join if seam == "join" else write), self.assertRaisesRegex(ValueError, "changed"):
                metadata.write_apple_metadata_content(**self.writer_arguments)
            self.assertFalse(self.output.exists())
            path.write_bytes(raw)

    def test_output_overlap_overwrite_and_symlink_are_rejected(self):
        existing = self.root / "existing"
        existing.write_bytes(b"user-owned")
        alias = self.root / "alias"
        alias.symlink_to(self.stage, target_is_directory=True)
        for output in (existing, self.stage / "new.json", self.paths["ios-arm64"], alias / "new.json"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                metadata.write_apple_metadata_content(**{**self.writer_arguments, "output": output})
        self.assertEqual(b"user-owned", existing.read_bytes())
        link = self.root / "linked-validation"
        link.symlink_to(self.paths["ios-arm64"])
        with self.assertRaises(ValueError):
            metadata.write_apple_metadata_content(**{**self.writer_arguments, "device_validation": link})
        self.assertFalse(self.output.exists())

    def test_cli_rejects_missing_or_foreign_flags_before_writer(self):
        fields = {key.replace("_", "-"): str(value) for key, value in self.writer_arguments.items()}
        argv = lambda values: [part for key, value in values.items() for part in ("--" + key, value)]
        cases = [argv({key: value for key, value in fields.items() if key != missing}) for missing in fields]
        cases.extend(argv(fields) + list(extra) for extra in (("--producer", "/untrusted"),
            ("--receipt", "/untrusted"), ("--command", "arbitrary")))
        for arguments in cases:
            with self.subTest(arguments=arguments), patch.object(metadata, "write_apple_metadata_content") as writer, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                metadata.main(arguments)
            writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
