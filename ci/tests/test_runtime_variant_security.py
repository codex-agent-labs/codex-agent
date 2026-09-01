from __future__ import annotations

import copy
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import zipfile

import ci.products.aggregate as aggregate_product
from ci.products.aggregate import (
    RUNTIME_TARGETS,
    runtime_component_id,
    validate_runtime_aggregate,
    validate_runtime_variant,
    verify_runtime_aggregate_artifacts,
)
from ci.products.inventory import (
    load_canonical_json,
    load_canonical_json_bytes,
    sha256_file,
    write_canonical_json,
)
from ci.products.receipt import compute_build_key
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.test_products import (
    DIGEST_A,
    DIGEST_B,
    DIGEST_C,
    producer,
    runtime_aggregate,
    runtime_aggregate_artifacts,
    runtime_variant,
)


def _sign_aggregate(root: Path, value: dict, private_key: Path) -> tuple[Path, Path]:
    root.mkdir()
    manifest = root / f"codex-agent-runtime-{value['runtimeVersion']}-manifest.json"
    write_canonical_json(manifest, value)
    return manifest, sign_manifest(manifest, private_key, value["signing"])


def _write_zip(path: Path, members: dict[str, bytes], *, canonical: bool) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            if canonical:
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                archive.writestr(info, members[name])
            else:
                archive.writestr(name, members[name])


class RuntimeVariantSecurityTest(unittest.TestCase):
    def fixture(self, root: Path, **mutators):
        private_key, public_key, signing = generate_development_key(root / "keys")
        values = runtime_aggregate_artifacts(
            root / "variants",
            private_key,
            public_key,
            signing,
            **mutators,
        )
        return private_key, values

    def verify(self, values, *, manifest=None, signature=None, aggregate_key=None):
        (
            aggregate_manifest, aggregate_signature, aggregate_public_key, contract_bundle,
            bundles, receipts, phase_receipts, validation_evidence, keys,
            runtime_maven_files, adapter_evidence,
        ) = values
        return verify_runtime_aggregate_artifacts(
            manifest or aggregate_manifest,
            aggregate_signature=signature or aggregate_signature,
            aggregate_public_key=aggregate_key or aggregate_public_key,
            contract_bundle=contract_bundle,
            contract_public_key=aggregate_public_key,
            variant_bundles=bundles,
            metadata_receipts=receipts,
            phase_receipts=phase_receipts,
            validation_evidence=validation_evidence,
            trusted_public_keys=keys,
            runtime_maven_files=runtime_maven_files,
            adapter_evidence=adapter_evidence,
            required_trust_domain="development",
        )

    def test_reusable_variant_rejects_run_specific_producer(self):
        variant = runtime_variant()
        variant["producer"] = producer()
        with self.assertRaisesRegex(ValueError, "extra=\\['producer'\\]"):
            validate_runtime_variant(variant)

    def test_component_id_uses_contract_compatibility_not_release_version(self):
        variant = runtime_variant()
        identity = variant["componentId"]

        version_only = copy.deepcopy(variant)
        version_only["contract"]["version"] = "0.2.1"
        self.assertEqual(identity, runtime_component_id(version_only))
        with self.assertRaisesRegex(ValueError, "extra=\\['version'\\]"):
            validate_runtime_variant(version_only)

        for field in ("digest", "componentDigest"):
            changed = copy.deepcopy(variant)
            changed["contract"][field] = DIGEST_C
            with self.subTest(field=field):
                self.assertNotEqual(identity, runtime_component_id(changed))

    def test_aggregate_requires_an_exact_detached_signature(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, values = self.fixture(root)
            bad = root / "bad-signature"
            bad.mkdir()
            signature = bad / values[1].name
            signature.write_bytes(values[1].read_bytes() + b"UNSIGNED\n")
            with self.assertRaises(ValueError):
                self.verify(values, signature=signature)

            _, wrong_public, _ = generate_development_key(root / "wrong-key")
            with self.assertRaises(ValueError):
                self.verify(values, aggregate_key=wrong_public)

    def test_aggregate_and_source_releases_must_share_the_compatibility_line(self):
        wrong_aggregate = runtime_aggregate()
        wrong_aggregate["runtimeCompatibilityVersion"] = "0.3.0"
        wrong_source = runtime_aggregate()
        wrong_source["variants"][0]["sourceRuntimeVersion"] = "9.0.0"
        for value in (wrong_aggregate, wrong_source):
            with self.assertRaises(ValueError):
                validate_runtime_aggregate(value)

    def test_variant_zip_must_use_the_canonical_stored_encoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, values = self.fixture(root)
            aggregate = load_canonical_json(values[0])
            target = RUNTIME_TARGETS[0]
            bundle = values[4][target]
            with zipfile.ZipFile(bundle) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            _write_zip(bundle, members, canonical=False)
            aggregate["variants"][0]["bundleSha256"] = sha256_file(bundle)
            manifest, signature = _sign_aggregate(root / "candidate", aggregate, private_key)
            with self.assertRaisesRegex(ValueError, "metadata is not canonical"):
                self.verify(values, manifest=manifest, signature=signature)

    def test_canonical_variant_pass_retains_only_deterministic_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, values = self.fixture(root)
            observed = []
            original = aggregate_product.verified_zip_contents

            def record_retained(*arguments, **keywords):
                result = original(*arguments, **keywords)
                if keywords.get("canonical_stored"):
                    observed.append((set(keywords["retained_paths"]), set(result[1])))
                return result

            with mock.patch.object(
                aggregate_product,
                "verified_zip_contents",
                side_effect=record_retained,
            ):
                self.verify(values)

            self.assertEqual(5, len(observed))
            for retained, materialized in observed:
                self.assertEqual(retained, materialized)
                self.assertEqual(6, len(retained))

    def test_binary_receipt_toolchain_must_equal_the_variant_profile(self):
        def mutate(target, phase, value):
            if target == RUNTIME_TARGETS[0] and phase == "binary":
                value["inputs"]["toolchainProfileDigest"] = DIGEST_C

        with tempfile.TemporaryDirectory() as temporary:
            _, values = self.fixture(Path(temporary).resolve(), receipt_mutator=mutate)
            with self.assertRaisesRegex(ValueError, "binary receipt projection mismatch"):
                self.verify(values)

    def test_package_receipt_must_contain_each_exact_inner_archive(self):
        for role, replacement in (("c-abi-archive", DIGEST_A), ("app-server-archive", DIGEST_B)):
            def mutate(target, phase, value, selected_role=role, digest=replacement):
                if target == RUNTIME_TARGETS[0] and phase == "package":
                    index = 0 if selected_role == "app-server-archive" else 1
                    value["outputs"][index]["sha256"] = digest

            with self.subTest(role=role), tempfile.TemporaryDirectory() as temporary:
                _, values = self.fixture(
                    Path(temporary).resolve(), phase_receipt_mutator=mutate,
                )
                with self.assertRaisesRegex(ValueError, "not an exact package output"):
                    self.verify(values)

    def test_validation_evidence_must_be_an_exact_validation_receipt_output(self):
        def mutate(target, phase, value):
            if target == RUNTIME_TARGETS[0] and phase == "validation":
                value["outputs"][0]["sha256"] = DIGEST_B

        with tempfile.TemporaryDirectory() as temporary:
            _, values = self.fixture(
                Path(temporary).resolve(), phase_receipt_mutator=mutate,
            )
            with self.assertRaisesRegex(ValueError, "not one exact validation output"):
                self.verify(values)

    def test_metadata_receipt_must_link_exactly_to_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, values = self.fixture(root)
            aggregate = load_canonical_json(values[0])
            target = RUNTIME_TARGETS[0]
            receipt_path = values[5][target]
            receipt = load_canonical_json(receipt_path)
            receipt["inputs"]["upstreamArtifacts"] = []
            receipt["buildKey"] = compute_build_key(
                product=receipt["product"], component=receipt["component"],
                phase=receipt["phase"], target=receipt["target"], inputs=receipt["inputs"],
            )
            write_canonical_json(receipt_path, receipt)
            aggregate["variants"][0]["receiptSha256"] = sha256_file(receipt_path)
            manifest, signature = _sign_aggregate(root / "candidate", aggregate, private_key)
            with self.assertRaisesRegex(ValueError, "metadata receipt disagrees"):
                self.verify(values, manifest=manifest, signature=signature)

    def test_signed_inventory_rejects_sbom_provenance_or_validation_byte_tampering(self):
        for role in ("sbom", "provenance", "validation"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                private_key, values = self.fixture(root)
                aggregate = load_canonical_json(values[0])
                bundle = values[4][RUNTIME_TARGETS[0]]
                variant_path = "runtime-variant-manifest.json"
                with zipfile.ZipFile(bundle) as archive:
                    members = {name: archive.read(name) for name in archive.namelist()}
                variant = load_canonical_json_bytes(members[variant_path])
                evidence_path = next(
                    member["path"] for member in variant["innerArtifacts"] if member["role"] == role
                )
                members[evidence_path] += b"tamper"
                _write_zip(bundle, members, canonical=True)
                aggregate["variants"][0]["bundleSha256"] = sha256_file(bundle)
                manifest, signature = _sign_aggregate(root / "candidate", aggregate, private_key)
                with self.assertRaisesRegex(ValueError, "file set or inner artifact differs"):
                    self.verify(values, manifest=manifest, signature=signature)


if __name__ == "__main__":
    unittest.main()
