from __future__ import annotations

import copy
import unittest

from ci.products.inventory import canonical_json_bytes, sha256_bytes
from ci.products.receipt import build_key_payload
from ci.products.runtime_attestation import derive_runtime_component_attestation
from ci.products.runtime_identity import derive_runtime_identity


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64


def identity() -> dict:
    return derive_runtime_identity({
        "schemaVersion": 1,
        "binaryBuildKey": phases()[0]["buildKey"],
        "runtimeCompatibilityVersion": "0.2.0",
        "target": "linux-x64",
        "contract": {"digest": DIGEST_B, "componentDigest": DIGEST_C},
        "cAbi": {
            "version": "1.13.0",
            "minimumCompatibleVersion": "1.0.0",
            "identitySchemaVersion": 1,
            "headerSha256": DIGEST_A,
            "symbolSetSha256": DIGEST_B,
            "symbolCount": 778,
        },
        "appServer": {
            "version": "0.149.0",
            "releaseTag": "rust-v0.149.0",
            "binarySha256": DIGEST_C,
        },
        "toolchainProfile": {"id": "linux-x64", "digest": DIGEST_D},
    })


def phases() -> list[dict]:
    records = []
    for index, phase in enumerate(("binary", "package", "validation")):
        output_digest = (DIGEST_B, DIGEST_C, DIGEST_D)[index]
        upstream = [{
            "schemaVersion": 1,
            "kind": "contract-components",
            "product": "contract",
            "component": "contract",
            "phase": "metadata",
            "target": "common",
            "contractDigest": DIGEST_B,
            "componentDigests": [{"component": "linux-x64", "sha256": DIGEST_C}],
        }] if phase == "binary" else [{
            "product": "runtime",
            "component": "linux-x64",
            "phase": records[index - 1]["phase"],
            "target": "linux-x64",
            "buildKey": records[index - 1]["buildKey"],
            "outputsDigest": records[index - 1]["outputInventoryDigest"],
        }]
        record = {
            "schemaVersion": 1,
            "product": "runtime",
            "component": "linux-x64",
            "phase": phase,
            "target": "linux-x64",
            "buildKey": "",
            "phaseInputDigest": DIGEST_D,
            "versionIdentity": "0.2.0",
            "upstreamArtifacts": upstream,
            "toolchainProfileDigest": DIGEST_D,
            "flagsDigest": DIGEST_A,
            "outputSchemaVersion": 1,
            "outputInventoryDigest": output_digest,
        }
        if phase == "validation":
            record["validationEvidenceDigest"] = record.pop("outputInventoryDigest")
        rekey(record)
        records.append(record)
    return records


def rekey(record: dict) -> None:
    record["buildKey"] = sha256_bytes(canonical_json_bytes(build_key_payload(
        product=record["product"],
        component=record["component"],
        phase=record["phase"],
        target=record["target"],
        inputs={
            field: value
            for field, value in record.items()
            if field in {
                "versionIdentity", "phaseInputDigest", "upstreamArtifacts",
                "toolchainProfileDigest", "flagsDigest", "outputSchemaVersion",
            }
        },
    )))


def artifacts() -> list[dict]:
    return [
        {"path": "app-server/codex.zip", "role": "app-server", "bytes": 2, "sha256": DIGEST_A},
        {"path": "c-abi/codex-agent-c.zip", "role": "c-abi", "bytes": 1, "sha256": DIGEST_B},
    ]


class RuntimeComponentAttestationTest(unittest.TestCase):
    def test_exact_minimal_cyclonedx_and_component_provenance_are_canonical(self) -> None:
        envelope = identity()
        result = derive_runtime_component_attestation(envelope, phases(), artifacts())

        self.assertEqual(canonical_json_bytes(result["sbom"]), result["sbomBytes"])
        self.assertEqual(
            canonical_json_bytes(result["componentProvenance"]),
            result["componentProvenanceBytes"],
        )
        self.assertEqual(
            {"bomFormat", "specVersion", "version", "metadata", "components"},
            set(result["sbom"]),
        )
        self.assertEqual(
            envelope["componentId"],
            result["sbom"]["metadata"]["component"]["bom-ref"],
        )
        self.assertEqual(
            ["app-server/codex.zip", "c-abi/codex-agent-c.zip"],
            [component["name"] for component in result["sbom"]["components"]],
        )
        self.assertEqual(
            "a" * 64,
            result["sbom"]["components"][0]["hashes"][0]["content"],
        )
        self.assertNotIn(b"sha256:", canonical_json_bytes(result["sbom"]["components"]))

    def test_producer_release_and_run_identity_cannot_enter_reusable_bytes(self) -> None:
        first = derive_runtime_component_attestation(identity(), phases(), artifacts())
        second = derive_runtime_component_attestation(identity(), phases(), artifacts())
        self.assertEqual(first["sbomBytes"], second["sbomBytes"])
        self.assertEqual(first["componentProvenanceBytes"], second["componentProvenanceBytes"])
        for field, value in (
            ("producer", {"runId": 1}),
            ("commit", "a" * 40),
            ("tree", "b" * 40),
            ("runId", 1),
            ("runtimeVersion", "0.2.7"),
        ):
            mutated = phases()
            mutated[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                derive_runtime_component_attestation(identity(), mutated, artifacts())

    def test_each_semantic_byte_change_changes_its_canonical_evidence(self) -> None:
        original = derive_runtime_component_attestation(identity(), phases(), artifacts())
        changed_artifacts = artifacts()
        changed_artifacts[0]["sha256"] = DIGEST_D
        artifact_change = derive_runtime_component_attestation(identity(), phases(), changed_artifacts)
        self.assertNotEqual(original["sbomBytes"], artifact_change["sbomBytes"])
        self.assertNotEqual(
            original["componentProvenanceBytes"], artifact_change["componentProvenanceBytes"],
        )

        changed_phases = phases()
        changed_phases[2]["flagsDigest"] = DIGEST_D
        rekey(changed_phases[2])
        phase_change = derive_runtime_component_attestation(identity(), changed_phases, artifacts())
        self.assertEqual(original["sbomBytes"], phase_change["sbomBytes"])
        self.assertNotEqual(
            original["componentProvenanceBytes"], phase_change["componentProvenanceBytes"],
        )

    def test_artifacts_are_strict_regular_file_records(self) -> None:
        mutations = []
        reversed_records = list(reversed(artifacts()))
        mutations.append(reversed_records)
        duplicate = artifacts()
        duplicate[1]["path"] = duplicate[0]["path"]
        mutations.append(duplicate)
        for invalid_path in ("../escape", "/host/path", "host\\path"):
            invalid = artifacts()
            invalid[0]["path"] = invalid_path
            mutations.append(invalid)
        empty = artifacts()
        empty[0]["bytes"] = 0
        mutations.append(empty)
        symlink = artifacts()
        symlink[0]["symlink"] = True
        mutations.append(symlink)
        for records in mutations:
            with self.subTest(records=records), self.assertRaises(ValueError):
                derive_runtime_component_attestation(identity(), phases(), records)

    def test_phase_evidence_is_exact_sorted_linked_and_identity_bound(self) -> None:
        mutations = []
        unsorted = phases()
        unsorted[0], unsorted[1] = unsorted[1], unsorted[0]
        mutations.append(unsorted)
        for index, field, value in (
            (1, "phase", "binary"),
            (2, "target", "macos-x64"),
            (0, "buildKey", DIGEST_D),
        ):
            invalid = phases()
            invalid[index][field] = value
            mutations.append(invalid)
        unknown = phases()
        unknown[0]["producer"] = {}
        mutations.append(unknown)
        wrong_contract = phases()
        wrong_contract[0]["upstreamArtifacts"][0]["contractDigest"] = DIGEST_A
        mutations.append(wrong_contract)
        broken_chain = phases()
        broken_chain[2]["upstreamArtifacts"][0]["buildKey"] = DIGEST_A
        mutations.append(broken_chain)
        for evidence in mutations:
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                derive_runtime_component_attestation(identity(), evidence, artifacts())

    def test_rekeyed_identity_and_chain_tampering_is_rejected(self) -> None:
        wrong_contract = phases()
        wrong_contract[0]["upstreamArtifacts"][0]["contractDigest"] = DIGEST_A
        rekey(wrong_contract[0])
        wrong_toolchain = phases()
        wrong_toolchain[0]["toolchainProfileDigest"] = DIGEST_A
        rekey(wrong_toolchain[0])
        broken_chain = phases()
        broken_chain[1]["upstreamArtifacts"][0]["buildKey"] = DIGEST_D
        rekey(broken_chain[1])
        for evidence in (wrong_contract, wrong_toolchain, broken_chain):
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                derive_runtime_component_attestation(identity(), evidence, artifacts())

    def test_runtime_identity_envelope_must_be_the_exact_derivation(self) -> None:
        invalid = copy.deepcopy(identity())
        invalid["componentId"] = DIGEST_A
        with self.assertRaisesRegex(ValueError, "derived identity"):
            derive_runtime_component_attestation(invalid, phases(), artifacts())


if __name__ == "__main__":
    unittest.main()
