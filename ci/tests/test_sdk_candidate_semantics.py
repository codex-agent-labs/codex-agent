"""SDK candidate dependency joins use exact original package evidence and S1048 pins."""

from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_candidate_semantics as candidate
from ci.products.aggregate import RUNTIME_TARGETS
from ci.products.inventory import canonical_json_bytes, sha256_bytes
from ci.products.restore import object_relative_path


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
    return {"schemaVersion": 1, "joinPins": pins,
            "dependencies": {"contractVersion": "0.8.0", "contractDigest": _CONTRACT,
                             "runtimeVersion": "0.8.0", "runtimeManifestSha256": _RUNTIME,
                             "sdkCompatibilitySha256": sha256_bytes(raw)}}


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
        self.entries = []
        for instance in sorted(candidate._PACKAGES):
            row = {"product": "sdk", "component": instance.component,
                   "phase": "package", "target": instance.target,
                   "buildKey": _KEY, "receiptSha256": _RECEIPT}
            self.entries.append(row)
            path = self.objects / "objects" / object_relative_path(_KEY, _RECEIPT)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"object\n")

    def _verify(self, *, raw=None, selection=None, per_component=None):
        raw = self.raw if raw is None else raw
        selection = self.selected if selection is None else selection
        def restore(_archive, stage, **_kwargs):
            package_bytes = (per_component or {}).get(stage.name, raw)
            (stage / "outputs/evidence").mkdir(parents=True)
            (stage / candidate._RESOURCE).write_bytes(package_bytes)
            return {"receipt": {"productVersion": "0.8.0", "phase": "package",
                    "component": stage.name, "target": next(instance.target
                        for instance in candidate._PACKAGES if instance.component == stage.name),
                    "outputs": [{"kind": "evidence", "relativePath": candidate._RESOURCE,
                                 "sha256": sha256_bytes(package_bytes)}]}}
        with patch.object(candidate, "verify_sdk_candidate_join",
                          return_value={"product": "sdk", "originalObjectCount": 62}) as join, \
             patch.object(candidate, "verify_release_product_index",
                          return_value=({"entries": self.entries}, self.index_bytes)), \
             patch.object(candidate, "restore_object", side_effect=restore) as restored:
            result = candidate.verify_sdk_candidate_semantics(
                self.root / "promoted", self.objects, self.root / "maven", selection)
        self.assertEqual(1, join.call_count)
        self.assertEqual(3, restored.call_count)
        return result

    def test_three_original_maven_packages_bind_exact_krs_dependencies(self):
        result = self._verify()
        self.assertFalse(result["admitted"])
        self.assertEqual(result["contractDigest"], _CONTRACT)
        self.assertEqual(result["runtimeManifestSha256"], _RUNTIME)

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
                            "--forwarded-maven", str(self.root)])
        verify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
