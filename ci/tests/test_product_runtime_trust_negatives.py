from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile

from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    write_canonical_json,
)
from ci.products.runtime_aggregate import verify_runtime_aggregate_attestation
from ci.products.runtime_attestation import (
    build_runtime_variant_attestation,
    verify_runtime_variant_attestation,
)
from ci.products.runtime_variant import produce_runtime_variant
from ci.products.signatures import generate_development_key
from ci.tests.test_product_runtime_aggregate import Fixture as AggregateFixture
from ci.tests.test_product_runtime_aggregate import VERSION as AGGREGATE_VERSION
from ci.tests.test_product_runtime_variant import Fixture as VariantFixture
from ci.tests.test_product_runtime_variant import (
    _attestation_paths,
    _write_metadata_receipt,
    _write_zip,
)


TAMPERED_DIGEST = sha256_bytes(b"tampered")


def _rewrite_variant_member(payload: Path, destination: Path, role: str, contents: bytes) -> None:
    with zipfile.ZipFile(payload) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = load_canonical_json_bytes(members["runtime-variant-manifest.json"])
    record = next(item for item in manifest["innerArtifacts"] if item["role"] == role)
    members[record["path"]] = contents
    record["bytes"] = len(contents)
    record["sha256"] = sha256_bytes(contents)
    members["runtime-variant-manifest.json"] = canonical_json_bytes(manifest)
    _write_zip(destination, members)


class RuntimeVariantTrustNegativeTest(unittest.TestCase):
    def test_bundle_and_provenance_tamper_survive_inventory_rebinding_but_fail_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, signing = generate_development_key(root / "keys")
            fixture = VariantFixture(root / "fixture", private_key, public_key, signing)
            payload = produce_runtime_variant(**fixture.arguments())["bundlePath"]

            cases = (
                ("c-abi-archive", b"inventory-rebound archive tamper\n", "exact package output"),
                ("provenance", canonical_json_bytes({"tampered": True}), "deterministic evidence"),
            )
            for role, contents, message in cases:
                with self.subTest(role=role):
                    directory = root / role
                    directory.mkdir()
                    tampered = directory / payload.name
                    _rewrite_variant_member(payload, tampered, role, contents)
                    metadata = _write_metadata_receipt(fixture, tampered)
                    with self.assertRaisesRegex(ValueError, message):
                        build_runtime_variant_attestation(
                            tampered,
                            fixture.receipt_paths["binary"],
                            fixture.receipt_paths["package"],
                            fixture.receipt_paths["validation"],
                            metadata,
                            fixture.validation,
                            signing,
                            private_key,
                            public_key,
                            root / f"{role}-attestation",
                        )

    def test_detached_envelope_names_canonical_bytes_and_bound_fields_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, signing = generate_development_key(root / "keys")
            fixture = VariantFixture(root / "fixture", private_key, public_key, signing)
            payload = produce_runtime_variant(**fixture.arguments())["bundlePath"]
            metadata = _write_metadata_receipt(fixture, payload)
            output = root / "attestation"
            build_runtime_variant_attestation(
                payload,
                fixture.receipt_paths["binary"],
                fixture.receipt_paths["package"],
                fixture.receipt_paths["validation"],
                metadata,
                fixture.validation,
                signing,
                private_key,
                public_key,
                output,
            )
            attestation, signature = _attestation_paths(payload, output)

            def verify(**overrides: Path) -> None:
                arguments = {
                    "payload": payload,
                    "binary_receipt": fixture.receipt_paths["binary"],
                    "package_receipt": fixture.receipt_paths["package"],
                    "validation_receipt": fixture.receipt_paths["validation"],
                    "metadata_receipt": metadata,
                    "attestation": attestation,
                    "signature": signature,
                    "public_key": public_key,
                }
                arguments.update(overrides)
                verify_runtime_variant_attestation(
                    **arguments,
                    required_trust_domain="development",
                    validation_evidence=fixture.validation,
                )

            verify()

            wrong_attestation = root / "wrong.attestation.json"
            wrong_attestation.write_bytes(attestation.read_bytes())
            wrong_signature = root / "wrong.attestation.sig"
            wrong_signature.write_bytes(signature.read_bytes())
            noncanonical_root = root / "noncanonical"
            noncanonical_root.mkdir()
            noncanonical = noncanonical_root / attestation.name
            noncanonical.write_bytes(b" " + attestation.read_bytes())
            for label, replacement in (
                ("attestation-name", {"attestation": wrong_attestation}),
                ("signature-name", {"signature": wrong_signature}),
                ("canonical-attestation", {"attestation": noncanonical}),
            ):
                with self.subTest(label=label), self.assertRaises(ValueError):
                    verify(**replacement)

            for label, mutate in (
                ("payload", lambda value: value["payload"].update(sha256=TAMPERED_DIGEST)),
                (
                    "receipt",
                    lambda value: value["phaseReceipts"].update(binary=TAMPERED_DIGEST),
                ),
            ):
                value = load_canonical_json_bytes(attestation.read_bytes())
                mutate(value)
                directory = root / f"tampered-{label}"
                directory.mkdir()
                path = directory / attestation.name
                write_canonical_json(path, value)
                with self.subTest(label=label), self.assertRaisesRegex(
                    ValueError, "does not bind its exact payload and receipts",
                ):
                    verify(attestation=path)


class RuntimeAggregateTrustNegativeTest(unittest.TestCase):
    def test_detached_attestation_rejects_names_tamper_receipt_and_provenance_rebinding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = AggregateFixture(root / "fixture")
            payload_root = root / "payload"
            payload_root.mkdir()
            manifest = fixture.produce(payload_root)["manifestPath"]
            metadata = fixture.metadata_receipt(manifest)
            output = root / "attestation"
            fixture.build_attestation(manifest, metadata, output)
            attestation = output / f"codex-agent-runtime-{AGGREGATE_VERSION}.attestation.json"
            signature = output / f"codex-agent-runtime-{AGGREGATE_VERSION}.attestation.sig"

            def verify(**overrides: Path) -> None:
                arguments = {
                    "manifest": manifest,
                    "metadata_receipt": metadata,
                    "attestation": attestation,
                    "signature": signature,
                    "public_key": fixture.public_key,
                }
                arguments.update(overrides)
                verify_runtime_aggregate_attestation(
                    **arguments, required_trust_domain="development",
                )

            verify()

            wrong_attestation = root / "wrong.attestation.json"
            wrong_attestation.write_bytes(attestation.read_bytes())
            wrong_signature = root / "wrong.attestation.sig"
            wrong_signature.write_bytes(signature.read_bytes())
            noncanonical_root = root / "noncanonical"
            noncanonical_root.mkdir()
            noncanonical = noncanonical_root / attestation.name
            noncanonical.write_bytes(b" " + attestation.read_bytes())
            for label, replacement in (
                ("attestation-name", {"attestation": wrong_attestation}),
                ("signature-name", {"signature": wrong_signature}),
                ("canonical-attestation", {"attestation": noncanonical}),
            ):
                with self.subTest(label=label), self.assertRaises(ValueError):
                    verify(**replacement)

            mutations = (
                ("payload", lambda value: value["payload"].update(sha256=TAMPERED_DIGEST)),
                (
                    "metadata-receipt",
                    lambda value: value.update(metadataReceiptSha256=TAMPERED_DIGEST),
                ),
                (
                    "variant-bundle",
                    lambda value: value["variants"][0].update(bundleSha256=TAMPERED_DIGEST),
                ),
            )
            for label, mutate in mutations:
                value = load_canonical_json_bytes(attestation.read_bytes())
                mutate(value)
                directory = root / f"tampered-{label}"
                directory.mkdir()
                path = directory / attestation.name
                write_canonical_json(path, value)
                with self.subTest(label=label), self.assertRaises(ValueError):
                    verify(attestation=path)

            changed_receipt = root / "changed-metadata.receipt.json"
            receipt = load_canonical_json_bytes(metadata.read_bytes())
            receipt["producer"]["runId"] += 1
            write_canonical_json(changed_receipt, receipt)
            with self.assertRaisesRegex(ValueError, "does not bind its payload and receipt"):
                verify(metadata_receipt=changed_receipt)

            rebound_root = root / "rebound"
            rebound_root.mkdir()
            rebound_manifest = rebound_root / manifest.name
            aggregate = load_canonical_json_bytes(manifest.read_bytes())
            aggregate["adapterEvidence"][0]["sha256"] = TAMPERED_DIGEST
            write_canonical_json(rebound_manifest, aggregate)
            rebound_receipt = rebound_root / "metadata.receipt.json"
            receipt = load_canonical_json_bytes(metadata.read_bytes())
            receipt["outputs"][0]["bytes"] = rebound_manifest.stat().st_size
            receipt["outputs"][0]["sha256"] = sha256_file(rebound_manifest)
            write_canonical_json(rebound_receipt, receipt)
            with self.assertRaisesRegex(ValueError, "does not bind its payload and receipt"):
                verify(manifest=rebound_manifest, metadata_receipt=rebound_receipt)


if __name__ == "__main__":
    unittest.main()
