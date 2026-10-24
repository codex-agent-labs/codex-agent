"""SDK candidate dependency joins use exact original package evidence and S1048 pins."""

from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from ci import sdk_candidate_semantics as candidate
from ci.products import restore
from ci.products.aggregate import RUNTIME_TARGETS
from ci.products.inventory import canonical_json_bytes, sha256_bytes, sha256_file
from ci.products.receipt import compute_build_key, write_output_manifest, write_phase_receipt
from ci.products.registry import NATIVE_BINDINGS, PHASE_INSTANCE_IDS, PhaseInstanceId
from ci.products.restore import object_relative_path
from ci.tests.test_sdk_completion import phase


_DIGEST = "sha256:" + "1" * 64
_CONTRACT = "sha256:" + "2" * 64
_RUNTIME = "sha256:" + "3" * 64
_KEY = "sha256:" + "4" * 64
_RECEIPT = "sha256:" + "5" * 64


def _compatibility() -> dict:
    return {"schemaVersion": 1, "sdkVersion": "0.8.0",
            "contract": {"version": "0.8.0", "digest": _CONTRACT},
            "runtime": {"compatibleReleaseRange": ">=0.8.0 <0.9.0",
                        "compatibleRuntimeCompatibilityRange": ">=0.8.0 <0.9.0",
                        "requiredIdentitySchema": 1,
                        "requiredContractDigest": _CONTRACT,
                        "requiredAbiMajor": 1, "minimumAbiMinor": 13,
                        "defaultRuntimeVersion": "0.8.0",
                        "defaultManifestSha256": _RUNTIME,
                        "embeddedVariants": [{"target": target,
                            "componentId": "sha256:" + f"{number + 1:064x}",
                            "bundleSha256": _DIGEST,
                            "manifestSha256": "sha256:" + f"{number + 11:064x}",
                            "runtimeLibrarySha256": _DIGEST}
                            for number, target in enumerate(sorted(RUNTIME_TARGETS))]},
            "platformRuntime": {name: {"owner": "sdk", "desktopRuntimeApplicable": False}
                                for name in ("android", "ios")}}


def _selection(raw: bytes) -> dict:
    pins = {name: _DIGEST for name in candidate._JOIN if name.endswith("_sha256")}
    pins.update(expected_sdk_version="0.8.0", expected_validation_tree="a" * 40)
    return {"schemaVersion": 2, "joinPins": pins,
            "dependencies": {"contractVersion": "0.8.0", "contractDigest": _CONTRACT,
                             "runtimeVersion": "0.8.0", "runtimeManifestSha256": _RUNTIME,
                             "sdkCompatibilitySha256": sha256_bytes(raw)},
            "parity": {"archiveSha256": _DIGEST, "archiveBytes": 1,
                       "phaseIdentitiesSha256": _DIGEST}}


def _parity_fixture(root, phases):
    # Content-join fixture only; official custody/signed campaign is mocked below.
    # This deliberately does not claim execution or manufacture hosted identities.
    names = {"canonical-api.json", "canonical-coverage.json", "binding-obligations-m11.json",
             *(name + "-parity.json" for name in (*NATIVE_BINDINGS, "kotlin", "java",
                 "javascript-typescript", "swift", "objective-c", "c-abi"))}
    evidence = {name: canonical_json_bytes({"fixture": name}) for name in names}
    digest = lambda raw: sha256_bytes(raw).removeprefix("sha256:")
    report = dict(schemaVersion=2, phase="M11", result="passed", capabilityCount=556,
        languageCount=11, scenarioCount=14, active=6104, pending=0, excluded=12, satisfied=6104, missing=0,
        canonicalApiSha256=digest(evidence["canonical-api.json"]),
        canonicalCoverageSha256=digest(evidence["canonical-coverage.json"]),
        evidenceFiles=[dict(path=name, bytes=len(raw), sha256=digest(raw))
                       for name, raw in sorted(evidence.items())])
    archive = root / "parity.zip"
    phase_file = root / "phases.json"
    phase_file.write_bytes(canonical_json_bytes(phases))
    with zipfile.ZipFile(archive, "w") as zipped:
        for name, raw in evidence.items():
            zipped.writestr("m11/" + name, raw)
        zipped.writestr("sdk-parity.json", canonical_json_bytes(report))
        zipped.writestr("original-phase-identities.json", phase_file.read_bytes())
        zipped.writestr("consumer.log", b"fixture only\n")
    return archive, phase_file


class SdkCandidateSemanticsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.objects = self.root / "objects"
        pair = self.objects / "signed-campaign/signed-pair"
        pair.mkdir(parents=True)
        self.index_bytes = b"signed index\n"
        self.signature_bytes = b"signed signature\n"
        (pair / "product-index.json").write_bytes(self.index_bytes)
        (pair / "product-index.sig").write_bytes(self.signature_bytes)
        self.raw = canonical_json_bytes(_compatibility())
        self.selected = _selection(self.raw)
        self.selected["joinPins"].update(
            expected_phase10_index_sha256=sha256_bytes(self.index_bytes),
            expected_phase10_signature_sha256=sha256_bytes(self.signature_bytes))
        self.phases = [dict(phase(instance), buildKey=_KEY, receiptSha256=_RECEIPT)
                       for instance in sorted(PHASE_INSTANCE_IDS)]
        self.entries = []
        for row in self.phases:
            if row["product"] != "sdk":
                continue
            self.entries.append(row)
            path = self.objects / "objects" / object_relative_path(_KEY, _RECEIPT)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"object\n")
        object_pins = canonical_json_bytes({"objects": self.entries})
        (self.objects / "object-pins.json").write_bytes(object_pins)
        self.selected["joinPins"]["expected_object_pins_sha256"] = sha256_bytes(object_pins)
        self.parity_archive, self.parity_phases = _parity_fixture(self.root, self.phases)
        self.selected["parity"].update(archiveSha256=sha256_file(self.parity_archive),
            archiveBytes=self.parity_archive.stat().st_size,
            phaseIdentitiesSha256=sha256_file(self.parity_phases))

    def _verify(self, *, raw=None, selection=None, per_component=None,
                use_promoted_objects=False, mutate_catalog=False):
        raw = self.raw if raw is None else raw
        selection = self.selected if selection is None else selection
        def compatibility(archive, entry, _digest, _version):
            if mutate_catalog:
                archive.write_bytes(b"changed after admission")
            return (per_component or {}).get(entry["component"], raw)
        with patch.object(candidate, "verify_sdk_candidate_join",
                          return_value={"product": "sdk", "originalObjectCount": 62}) as join, \
             patch.object(candidate, "verify_release_product_index",
                          return_value=({"entries": self.entries}, self.index_bytes)), \
             patch.object(candidate, "_package_compatibility", side_effect=compatibility) as consumed:
            result = candidate.verify_sdk_candidate_semantics(
                self.root / "promoted", self.objects, self.root / "maven", selection,
                parity_archive=self.parity_archive, parity_phase_identities=self.parity_phases,
                use_promoted_objects=use_promoted_objects)
        self.assertEqual(1, join.call_count)
        self.assertIs(use_promoted_objects, join.call_args.kwargs["use_promoted_objects"])
        self.assertEqual(3, consumed.call_count)
        object_root = self.root / "promoted" if use_promoted_objects else self.objects / "objects"
        self.assertTrue(all(call.args[0].is_relative_to(object_root) for call in consumed.call_args_list))
        return result

    def test_shared_catalog_consumes_original_packages_and_rejects_late_mutation(self):
        (self.objects / "objects").rename(self.root / "promoted")
        self.assertEqual(112, self._verify(use_promoted_objects=True)["parity"]["phaseCount"])
        self.assertFalse((self.objects / "objects").exists())
        with self.assertRaisesRegex(ValueError, "objects changed"):
            self._verify(use_promoted_objects=True, mutate_catalog=True)

    def test_three_original_maven_packages_bind_exact_krs_dependencies(self):
        result = self._verify()
        self.assertFalse(result["admitted"])
        self.assertEqual(result["contractDigest"], _CONTRACT)
        self.assertEqual(result["runtimeManifestSha256"], _RUNTIME)
        self.assertEqual(result["parity"]["phaseCount"], 112)
        self.assertEqual(result["parity"]["satisfied"], 6104)

    def test_contract_runtime_and_compatibility_mutations_reject(self):
        for field, value in (("contractDigest", _DIGEST),
                             ("contractVersion", "0.8.1"),
                             ("runtimeVersion", "0.8.1"),
                             ("runtimeManifestSha256", _DIGEST)):
            selected = copy.deepcopy(self.selected)
            selected["dependencies"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,
                                                                  "dependency identity"):
                self._verify(selection=selected)
        raw = self.raw.replace(b'"sdkVersion":"0.8.0"', b'"sdkVersion":"0.8.1"')
        with self.assertRaisesRegex(ValueError, "compatibility bytes"):
            self._verify(raw=raw)

    def test_three_packages_must_embed_identical_valid_schema(self):
        changed = self.raw.replace(b'"sdkVersion":"0.8.0"', b'"sdkVersion":"0.8.1"')
        with self.assertRaisesRegex(ValueError, "compatibility bytes"):
            self._verify(per_component={"sdk-ios": changed})
        invalid = canonical_json_bytes({"schemaVersion": 1, "sdkVersion": "0.8.0"})
        selected = copy.deepcopy(self.selected)
        selected["dependencies"]["sdkCompatibilitySha256"] = sha256_bytes(invalid)
        with self.assertRaises(ValueError):
            self._verify(raw=invalid, selection=selected)

    def test_selection_schema_and_cli_digest_fail_closed(self):
        selected = copy.deepcopy(self.selected)
        del selected["dependencies"]["runtimeManifestSha256"]
        with self.assertRaises(ValueError):
            candidate._selection(selected)
        selected = self.root / "selection.json"
        selected.write_bytes(canonical_json_bytes(self.selected))
        with patch.object(candidate, "verify_sdk_candidate_semantics") as verify, \
             self.assertRaisesRegex(ValueError, "S1048 approval"):
            candidate.main(["--selection", str(selected),
                            "--expected-selection-sha256", _DIGEST,
                            "--promoted-catalog", str(self.root),
                            "--forwarded-objects", str(self.objects),
                            "--forwarded-maven", str(self.root),
                            "--parity-archive", str(self.parity_archive),
                            "--parity-phase-identities", str(self.parity_phases)])
        verify.assert_not_called()

    def test_parity_must_bind_independent_pins_and_exact_sdk_objects(self):
        for field, value in (("archiveSha256", _DIGEST), ("archiveBytes", 1),
                             ("phaseIdentitiesSha256", _DIGEST)):
            selected = copy.deepcopy(self.selected)
            selected["parity"][field] = value
            with self.subTest(pin=field), self.assertRaises(ValueError):
                self._verify(selection=selected)
        entries = {PhaseInstanceId(*(row[k] for k in ("product", "component", "phase", "target"))): row
                   for row in self.entries}
        for field in ("buildKey", "receiptSha256", "objectSha256"):
            objects = copy.deepcopy(entries)
            objects[next(iter(objects))][field] = _DIGEST
            with self.subTest(object_field=field), self.assertRaisesRegex(ValueError, "signed SDK campaign"):
                candidate.verify_candidate_sdk_parity(self.parity_archive, self.parity_phases,
                    self.selected["parity"], entries, objects)
        for phases in (self.phases[:-1], self.phases + self.phases[:1]):
            raw = canonical_json_bytes(phases)
            self.parity_phases.write_bytes(raw)
            pins = dict(self.selected["parity"], phaseIdentitiesSha256=sha256_bytes(raw))
            with self.assertRaisesRegex(ValueError, "phase set"):
                candidate.verify_candidate_sdk_parity(self.parity_archive, self.parity_phases,
                    pins, entries, entries)

    def test_old_selection_and_mutated_object_pins_cannot_skip_parity(self):
        for mutation in ("schema", "missing"):
            selected = copy.deepcopy(self.selected)
            if mutation == "schema":
                selected["schemaVersion"] = 1
            else:
                del selected["parity"]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                candidate._selection(selected)
        (self.objects / "object-pins.json").write_bytes(b"{}\n")
        with self.assertRaisesRegex(ValueError, "object pins changed"):
            self._verify()


class SdkCandidatePackageReadTest(unittest.TestCase):
    def test_verified_scoped_member_reuse_without_stage_extraction(self):
        # Real object/receipt/manifest checks; not a release or hosted fixture.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            stage = root / "stage"
            resource = stage / candidate._RESOURCE
            resource.parent.mkdir(parents=True)
            raw = canonical_json_bytes(_compatibility())
            resource.write_bytes(raw)
            (resource.parent / "unconsumed.bin").write_bytes(b"unconsumed package evidence")
            identity = dict(product="sdk", component="sdk-core", phase="package", target="common")
            inputs = dict(inventory=[], phaseInputDigest=sha256_bytes(canonical_json_bytes([])),
                versionIdentity="0.8.0", upstreamArtifacts=[], toolchainProfileDigest=_DIGEST,
                flagsDigest=_DIGEST, outputSchemaVersion=1)
            producer = dict(repository="example/fixture", workflowPath=".github/workflows/ci.yml",
                commit="a" * 40, tree="b" * 40, event="pull_request", runId=1, runAttempt=1, pullRequest=1)
            key = compute_build_key(**identity, inputs=inputs)
            write_output_manifest(stage, *identity.values(), "0.8.0", {"evidence": "outputs/evidence"})
            write_phase_receipt(stage, root, *identity.values(), "0.8.0", key, inputs, producer, "development")
            stored = restore.store_local_object(stage, root / "phase-receipt.json", root / "cache")
            entry = dict(identity, buildKey=key, receiptSha256=stored["receiptSha256"])
            with restore.verification_session() as session, \
                 patch.object(restore, "_verify_snapshot", wraps=restore._verify_snapshot) as scan, \
                 patch.object(restore, "_extract_verified_stage", side_effect=AssertionError("full extraction")), \
                 patch.object(zipfile.ZipFile, "extractall", side_effect=AssertionError("full extraction")):
                for _ in range(2):
                    self.assertEqual(raw, candidate._package_compatibility(
                        stored["path"], entry, stored["objectSha256"], "0.8.0"))
                self.assertEqual(1, scan.call_count)
                self.assertEqual(1, session["hits"])
                for changed, digest, version in (
                    (dict(entry, component="sdk-android"), stored["objectSha256"], "0.8.0"),
                    (entry, stored["objectSha256"], "0.8.1"),
                    (entry, _DIGEST, "0.8.0"),
                    (dict(entry, receiptSha256=_DIGEST), stored["objectSha256"], "0.8.0")):
                    with self.subTest(entry=changed, digest=digest, version=version), self.assertRaises(ValueError):
                        candidate._package_compatibility(stored["path"], changed, digest, version)
                original = stored["path"].read_bytes()
                stored["path"].chmod(0o600)
                stored["path"].write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
                with self.assertRaises(ValueError):
                    candidate._package_compatibility(stored["path"], entry, stored["objectSha256"], "0.8.0")


if __name__ == "__main__":
    unittest.main()
