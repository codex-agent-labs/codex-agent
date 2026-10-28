from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import (
    canonical_json_bytes, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory, sha256_bytes, write_canonical_json,
)
from ci.products.runtime_attestation import (
    build_runtime_variant_attestation, derive_runtime_component_attestation,
    read_runtime_variant_handoff, verify_runtime_validation_inputs, verify_runtime_variant_attestation,
)
from ci.products.receipt import output_inventory_digest
from ci.products.runtime_identity import derive_runtime_identity
from ci.products.runtime_variant import produce_runtime_variant
from ci.products.signatures import generate_development_key, sign_manifest
from ci.tests.test_product_runtime_variant import Fixture, _write_metadata_receipt


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
    record["buildKey"] = sha256_bytes(canonical_json_bytes({
        field: record[field]
        for field in {
            "schemaVersion", "product", "component", "phase", "target",
            "versionIdentity", "phaseInputDigest", "upstreamArtifacts",
            "toolchainProfileDigest", "flagsDigest", "outputSchemaVersion",
        }
    }))


def artifacts() -> list[dict]:
    return [
        {"path": "app-server/codex.zip", "role": "app-server", "bytes": 2, "sha256": DIGEST_A},
        {"path": "c-abi/codex-agent-c.zip", "role": "c-abi", "bytes": 1, "sha256": DIGEST_B},
    ]


class RuntimeComponentAttestationTest(unittest.TestCase):
    def test_mac_bootstrap_contract_projection_preserves_content_only_phase_chain(self) -> None:
        records = phases()
        for index, record in enumerate(records):
            record["component"] = record["target"] = "macos-arm64"
            if index == 0:
                record["upstreamArtifacts"][0]["componentDigests"][0]["component"] = "macos-arm64"
            else:
                predecessor = record["upstreamArtifacts"][0]
                predecessor["component"] = predecessor["target"] = "macos-arm64"
                predecessor["buildKey"] = records[index - 1]["buildKey"]
            rekey(record)
        source = identity()
        del source["componentId"], source["runtimeIdentityJson"]
        source["target"] = source["toolchainProfile"]["id"] = "macos-arm64"
        source["binaryBuildKey"] = records[0]["buildKey"]
        envelope = derive_runtime_identity(source)
        # Old immutable lifecycle-only evidence remains verifiable, not upgraded.
        derive_runtime_component_attestation(envelope, records, artifacts())
        contract = copy.deepcopy(records[0]["upstreamArtifacts"][0])
        contract["componentDigests"].insert(0, {"component": "common", "sha256": DIGEST_A})
        records[2]["upstreamArtifacts"].insert(0, contract)
        rekey(records[2])
        first = derive_runtime_component_attestation(envelope, records, artifacts())
        self.assertEqual(first, derive_runtime_component_attestation(envelope, records, artifacts()))
        coverage_records = copy.deepcopy(records)
        coverage_records[2]["upstreamArtifacts"][0].update(schemaVersion=2, canonicalCoverageDigest=DIGEST_A)
        rekey(coverage_records[2])
        with_coverage = derive_runtime_component_attestation(envelope, coverage_records, artifacts())
        coverage_records[2]["upstreamArtifacts"][0]["canonicalCoverageDigest"] = DIGEST_D
        rekey(coverage_records[2])
        self.assertNotEqual(with_coverage["componentProvenanceBytes"],
            derive_runtime_component_attestation(envelope, coverage_records, artifacts())["componentProvenanceBytes"])
        for field, value in (("schemaVersion", True), ("contractDigest", DIGEST_A),
                             ("target", "linux-x64"), ("producer", {"runId": 1}),
                             ("componentDigests", contract["componentDigests"][:1]),
                             ("componentDigests", list(reversed(contract["componentDigests"]))),
                             ("componentDigests", [{"component": "common", "sha256": DIGEST_A},
                                                   {"component": "macos-arm64", "sha256": DIGEST_D}])):
            changed = copy.deepcopy(records)
            changed[2]["upstreamArtifacts"][0][field] = value
            rekey(changed[2])
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                derive_runtime_component_attestation(envelope, changed, artifacts())

    def test_raw_bootstrap_receipt_keeps_provenance_but_checks_exact_package(self) -> None:
        package = {"product": "runtime", "component": "macos-arm64", "phase": "package",
                   "target": "macos-arm64", "buildKey": DIGEST_A,
                   "outputs": [{"kind": "c-abi", "relativePath": "outputs/sdk.zip",
                                "bytes": 1, "sha256": DIGEST_B}]}
        reference = {key: package[key] for key in ("product", "component", "phase", "target", "buildKey")}
        reference["outputsDigest"] = output_inventory_digest(package["outputs"])
        contract = {"product": "contract", "component": "contract", "phase": "metadata",
                    "target": "common", "buildKey": DIGEST_A, "outputsDigest": DIGEST_B,
                    "contractProjection": {
                        "schemaVersion": 1, "receiptSha256": DIGEST_A,
                        "bundlePath": "outputs/codex-agent-contract-0.2.0.zip",
                        "bundleSha256": DIGEST_B, "manifestSha256": DIGEST_C,
                        "contractVersion": "0.2.0", "contractDigest": DIGEST_B,
                        "componentDigests": [{"component": "common", "sha256": DIGEST_A},
                                             {"component": "macos-arm64", "sha256": DIGEST_C}]}}
        validation = {"product": "runtime", "component": "macos-arm64", "phase": "validation",
                      "target": "macos-arm64", "inputs": {
                          "versionIdentity": "0.2.0", "phaseInputDigest": DIGEST_D,
                          "upstreamArtifacts": [contract, reference], "toolchainProfileDigest": DIGEST_A,
                          "flagsDigest": DIGEST_B, "outputSchemaVersion": 1}}
        envelope = {"target": "macos-arm64", "contract": {"digest": DIGEST_B, "componentDigest": DIGEST_C}}
        original = canonical_json_bytes(validation)
        verify_runtime_validation_inputs(validation, package, envelope)
        self.assertEqual(original, canonical_json_bytes(validation))
        # Producer receipt changes cannot leak through the content projection.
        contract["contractProjection"]["receiptSha256"] = DIGEST_D
        verify_runtime_validation_inputs(validation, package, envelope)
        contract["contractProjection"].update(schemaVersion=2, canonicalCoverageDigest=DIGEST_A)
        verify_runtime_validation_inputs(validation, package, envelope)
        for inputs in ([reference, contract], [contract, reference, reference], [contract]):
            changed = copy.deepcopy(validation)
            changed["inputs"]["upstreamArtifacts"] = inputs
            with self.subTest(inputs=inputs), self.assertRaises(ValueError):
                verify_runtime_validation_inputs(changed, package, envelope)
        reference["outputsDigest"] = DIGEST_D
        with self.assertRaises(ValueError):
            verify_runtime_validation_inputs(validation, package, envelope)

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


class RuntimeVariantCompleteHandoffTest(unittest.TestCase):
    """Real signatures over synthetic originals; not CI or native-host admission."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.private, self.public, self.signing = generate_development_key(self.root / "keys")
        self.fixture = Fixture(self.root / "original", self.private, self.public, self.signing)
        self.payload = produce_runtime_variant(**self.fixture.arguments())["bundlePath"]
        # Fault-injection fixture only: generated payloads normally publish read-only.
        self.payload.chmod(0o600)
        self.receipts = {**self.fixture.receipt_paths,
                         "metadata": _write_metadata_receipt(self.fixture, self.payload)}
        self.originals = {self.payload.name: self.payload, "public-key.pub": self.public,
                          "validation-evidence.json": self.fixture.validation,
                          **{f"receipts/{phase}.json": path for phase, path in self.receipts.items()}}
        self.before = {name: path.read_bytes() for name, path in self.originals.items()}

    def build(self, output: Path, **changes):
        arguments = dict(payload=self.payload, binary_receipt=self.receipts["binary"],
            package_receipt=self.receipts["package"], validation_receipt=self.receipts["validation"],
            metadata_receipt=self.receipts["metadata"], validation_evidence=self.fixture.validation,
            signing_metadata=self.signing, private_key=self.private, public_key=self.public,
            output_directory=output, complete_handoff=True)
        arguments.update(changes)
        return build_runtime_variant_attestation(**arguments)

    def verify(self, root: Path, **changes):
        arguments = dict(payload=root / self.payload.name,
            **{f"{phase}_receipt": root / f"receipts/{phase}.json" for phase in self.receipts},
            attestation=root / f"{self.payload.stem}.attestation.json",
            signature=root / f"{self.payload.stem}.attestation.sig", public_key=root / "public-key.pub",
            required_trust_domain="development", validation_evidence=root / "validation-evidence.json")
        arguments.update(changes)
        return verify_runtime_variant_attestation(**arguments)

    def test_exact_originals_relocate_and_default_still_publishes_only_detached_files(self) -> None:
        detached = self.root / "detached"
        previous = self.build(detached, complete_handoff=False)
        self.assertEqual({f"{self.payload.stem}.attestation.json", f"{self.payload.stem}.attestation.sig"},
                         {item["relativePath"] for item in regular_file_inventory(detached)})
        output = self.root / "handoff"
        with patch("ci.products.runtime_variant.produce_runtime_variant", side_effect=AssertionError("rebuild")):
            value = self.build(output)
        self.assertEqual(previous, value)
        expected = set(self.before) | {f"{self.payload.stem}.attestation.json", f"{self.payload.stem}.attestation.sig"}
        self.assertEqual(9, len(expected))
        self.assertEqual(expected, {item["relativePath"] for item in regular_file_inventory(output)})
        self.assertEqual(self.before, {name: path.read_bytes() for name, path in self.originals.items()})
        self.assertEqual(self.before, {name: (output / name).read_bytes() for name in self.before})
        retained = regular_file_inventory(output)
        moved = self.root / "relocated"
        output.rename(moved)
        self.fixture.root.rename(self.root / "hidden-original")
        self.private.parent.rename(self.root / "hidden-keys")
        self.assertEqual(value, self.verify(moved)[2])
        self.assertEqual(retained, regular_file_inventory(moved))
        with patch("ci.products.runtime_attestation.sign_manifest", side_effect=AssertionError("resign")), \
                self.assertRaisesRegex(ValueError, "destination must not exist"):
            self.build(moved)

    def test_attestation_changed_after_verification_cannot_publish(self) -> None:
        def mutate_before_copy(source, destination, *, expected_inventory):
            next(Path(source).glob("*.attestation.json")).write_bytes(b"changed after verification\n")
            actual_publish_regular_tree(source, destination,
                                        expected_inventory=expected_inventory)

        for complete_handoff in (False, True):
            output = self.root / f"late-mutation-{complete_handoff}"
            with self.subTest(complete_handoff=complete_handoff), \
                    patch("ci.products.runtime_attestation.publish_regular_tree",
                          side_effect=mutate_before_copy), \
                    self.assertRaisesRegex(ValueError, "pinned inventory"):
                self.build(output, complete_handoff=complete_handoff)
            self.assertFalse(output.exists())

    def test_hostile_destinations_and_inputs_never_sign_or_replace_originals(self) -> None:
        link = self.root / "linked-original"
        link.symlink_to(self.fixture.root, target_is_directory=True)
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "absent", target_is_directory=True)
        existing = self.root / "existing"
        existing.mkdir()
        (existing / "sentinel").write_bytes(b"keep")
        outputs = (existing, self.root, self.payload / "nested", link / "fresh",
                   link / ".." / "fresh", dangling / "fresh")
        with patch("ci.products.runtime_attestation.sign_manifest", side_effect=AssertionError("sign")):
            for output in outputs:
                with self.subTest(output=output), self.assertRaises((ValueError, OSError)):
                    self.build(output)
            for selection in (1, "true", None):
                with self.subTest(selection=selection), self.assertRaisesRegex(ValueError, "boolean"):
                    self.build(self.root / "bad-selection", complete_handoff=selection)
            for field, source in (("binary_receipt", self.receipts["binary"]),
                                  ("validation_evidence", self.fixture.validation),
                                  ("public_key", self.public), ("payload", self.payload)):
                alias = self.root / f"unsafe-{field}"
                alias.symlink_to(source)
                with self.subTest(field=field), self.assertRaises((ValueError, OSError)):
                    self.build(self.root / f"rejected-{field}", **{field: alias})
        self.assertEqual(b"keep", (existing / "sentinel").read_bytes())
        self.assertEqual(self.before, {name: path.read_bytes() for name, path in self.originals.items()})

    def test_original_mutation_during_signing_never_publishes(self) -> None:
        for name, path in self.originals.items():
            def mutate(attestation, private, signing):
                signature = sign_manifest(attestation, private, signing)
                path.write_bytes(b"changed original\n")
                return signature
            output = self.root / "rejected-original"
            try:
                with self.subTest(name=name), patch("ci.products.runtime_attestation.sign_manifest", side_effect=mutate), \
                        self.assertRaisesRegex(ValueError, "Original Runtime inputs changed"):
                    self.build(output)
                self.assertFalse(output.exists())
            finally:
                path.write_bytes(self.before[name])

    def test_missing_or_unbound_original_evidence_is_rejected_before_signing(self) -> None:
        with patch("ci.products.runtime_attestation.sign_manifest", side_effect=AssertionError("sign")):
            for name, path in self.originals.items():
                if name == "public-key.pub":
                    continue
                try:
                    path.write_bytes(b"not original evidence\n")
                    with self.subTest(name=name), self.assertRaises((ValueError, OSError)):
                        self.build(self.root / "invalid-original")
                    self.assertFalse((self.root / "invalid-original").exists())
                finally:
                    path.write_bytes(self.before[name])
            with self.assertRaises((ValueError, OSError)):
                self.build(self.root / "missing-original", validation_evidence=self.root / "absent.json")
            with patch("ci.products.runtime_attestation._PAYLOAD_LIMIT", self.payload.stat().st_size - 1), \
                    self.assertRaises(ValueError):
                self.build(self.root / "oversized-original")
        self.assertFalse((self.root / "missing-original").exists())
        self.assertFalse((self.root / "oversized-original").exists())

    def test_captured_mutation_or_extra_file_never_publishes(self) -> None:
        for relative in (*self.before, "extra-private-key"):
            def mutate(attestation, private, signing):
                signature = sign_manifest(attestation, private, signing)
                (attestation.parent / relative).write_bytes(b"changed capture\n")
                return signature
            output = self.root / "rejected-capture"
            with self.subTest(relative=relative), patch("ci.products.runtime_attestation.sign_manifest", side_effect=mutate), \
                    self.assertRaises((ValueError, OSError)):
                self.build(output)
            self.assertFalse(output.exists())
        # The captured closure also remains immutable across a successful full verifier.
        def mutate_after_verify(*args, **kwargs):
            result = verify_runtime_variant_attestation(*args, **kwargs)
            args[5].write_bytes(b"changed verified attestation\n")
            return result
        with patch("ci.products.runtime_attestation.verify_runtime_variant_attestation", side_effect=mutate_after_verify), \
                self.assertRaisesRegex(ValueError, "changed during verification"):
            self.build(self.root / "rejected-late-capture")
        self.assertFalse((self.root / "rejected-late-capture").exists())
        self.assertEqual(self.before, {name: path.read_bytes() for name, path in self.originals.items()})

    def test_release_handoff_requires_external_caller_policy_and_preserves_receipt_trust(self) -> None:
        signing = {**self.signing, "trustDomain": "release", "keyId": "release-fixture"}
        keys = self.root / "public-policy-keys"
        keys.mkdir()
        (keys / "release-fixture.pub").write_bytes(self.public.read_bytes())
        keyring = self.root / "keyring.json"
        write_canonical_json(keyring, {
            "schemaVersion": 1, "namespace": signing["namespace"], "algorithm": signing["algorithm"],
            "trustDomain": "release", "activeKey": {
                "keyId": signing["keyId"], "fingerprint": signing["fingerprint"],
            }, "retiredKeys": [],
        })
        with patch("ci.products.runtime_attestation.sign_manifest", side_effect=AssertionError("sign")), \
                self.assertRaisesRegex(ValueError, "requires a keyring"):
            self.build(self.root / "untrusted", signing_metadata=signing)
        output = self.root / "release-handoff"
        value = self.build(output, signing_metadata=signing, keyring=keyring, keys_directory=keys)
        with self.assertRaisesRegex(ValueError, "requires a keyring"):
            self.verify(output, required_trust_domain="release")
        _, receipts, verified = self.verify(output, required_trust_domain="release", keyring=keyring, keys_directory=keys)
        self.assertEqual(value, verified)
        self.assertEqual({"development"}, {receipt["trustDomain"] for receipt in receipts.values()})
        self.assertEqual(self.before, {name: (output / name).read_bytes() for name in self.before})
        self.assertEqual(9, len(regular_file_inventory(output)))
        self.assertFalse((output / "keyring.json").exists())
        self.assertFalse((output / self.private.name).exists())
        _, other_public, _ = generate_development_key(self.root / "unrelated-key")
        (keys / "release-fixture.pub").write_bytes(other_public.read_bytes())
        with self.assertRaises(ValueError):
            self.verify(output, required_trust_domain="release", keyring=keyring, keys_directory=keys)

    def release_handoff(self):
        signing = {**self.signing, "trustDomain": "release", "keyId": "release-fixture"}
        keys = self.root / "reader-policy-keys"
        keys.mkdir()
        (keys / "release-fixture.pub").write_bytes(self.public.read_bytes())
        keyring = self.root / "reader-keyring.json"
        policy = {"schemaVersion": 1, "namespace": signing["namespace"], "algorithm": signing["algorithm"],
                  "trustDomain": "release", "activeKey": {
                      "keyId": signing["keyId"], "fingerprint": signing["fingerprint"],
                  }, "retiredKeys": []}
        write_canonical_json(keyring, policy)
        output = self.root / "reader-handoff"
        self.build(output, signing_metadata=signing, keyring=keyring, keys_directory=keys)
        return output, keyring, keys, policy

    def test_release_reader_returns_exact_original_bytes_without_signing_and_accepts_retired_key(self) -> None:
        output, keyring, keys, policy = self.release_handoff()
        before = regular_file_inventory(output)
        files = {record["relativePath"]: (output / record["relativePath"]).read_bytes() for record in before}
        with patch("ci.products.runtime_attestation.sign_manifest", side_effect=AssertionError("reader signed")):
            active = read_runtime_variant_handoff(output, target="linux-x64", keyring=keyring, keys_directory=keys)
            policy["retiredKeys"] = [policy.pop("activeKey")]
            policy["activeKey"] = None
            write_canonical_json(keyring, policy)
            retired = read_runtime_variant_handoff(output, target="linux-x64", keyring=keyring, keys_directory=keys)
        self.assertEqual(active, retired)
        self.assertEqual({"manifest", "receipts", "receiptBytes", "attestation", "files"}, set(active))
        self.assertEqual(files, active["files"])
        self.assertEqual({phase: self.before[f"receipts/{phase}.json"] for phase in self.receipts}, active["receiptBytes"])
        self.assertEqual({"development"}, {value["trustDomain"] for value in active["receipts"].values()})
        self.assertEqual(before, regular_file_inventory(output))
        output.rename(self.root / "moved-after-read")
        self.assertEqual(files, active["files"])

    def test_release_reader_rejects_every_tampered_member_missing_extra_symlink_and_wrong_name(self) -> None:
        output, keyring, keys, _ = self.release_handoff()
        originals = {record["relativePath"]: (output / record["relativePath"]).read_bytes()
                     for record in regular_file_inventory(output)}
        cases = [("tamper", name) for name in originals] + [
            ("missing", "receipts/binary.json"), ("extra", "unexpected.json"),
            ("symlink", "validation-evidence.json"), ("extra-receipt", "receipts/unexpected.json"),
            ("wrong-name", f"{self.payload.stem}.attestation.json"),
        ]
        for index, (kind, name) in enumerate(cases):
            # Mutable transport fixtures; the published original handoff remains unchanged.
            mutant = self.root / f"reader-mutant-{index}"
            for relative, raw in originals.items():
                path = mutant / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            path = mutant / name
            if kind == "missing":
                path.unlink()
            elif kind == "symlink":
                path.unlink()
                path.symlink_to(output / name)
            elif kind == "wrong-name":
                path.rename(mutant / "wrong.attestation.json")
            else:
                path.write_bytes(b"unverified handoff bytes\n")
            with self.subTest(kind=kind, name=name), \
                    patch("ci.products.runtime_attestation.sign_manifest", side_effect=AssertionError("reader signed")), \
                    self.assertRaises((ValueError, OSError)):
                read_runtime_variant_handoff(mutant, target="linux-x64", keyring=keyring, keys_directory=keys)
        self.assertEqual(originals, {name: (output / name).read_bytes() for name in originals})

    def test_release_reader_rejects_wrong_target_unpinned_policy_and_development_handoff(self) -> None:
        output, keyring, keys, policy = self.release_handoff()
        with patch("ci.products.runtime_attestation.sign_manifest", side_effect=AssertionError("reader signed")):
            for target in ("macos-arm64", "unsupported", "../linux-x64"):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    read_runtime_variant_handoff(output, target=target, keyring=keyring, keys_directory=keys)
            with self.assertRaises(ValueError):
                read_runtime_variant_handoff(output, target="linux-x64", keyring=None, keys_directory=None)
            alias = self.root / "reader-symlink"
            alias.symlink_to(output, target_is_directory=True)
            with self.assertRaises(ValueError):
                read_runtime_variant_handoff(alias, target="linux-x64", keyring=keyring, keys_directory=keys)
        development = self.root / "reader-development"
        self.build(development)
        with self.assertRaisesRegex(ValueError, "not release trust"):
            read_runtime_variant_handoff(development, target="linux-x64", keyring=keyring, keys_directory=keys)
        _, other_public, other_signing = generate_development_key(self.root / "reader-other-key")
        (keys / "other.pub").write_bytes(other_public.read_bytes())
        policy["activeKey"] = {"keyId": "other", "fingerprint": other_signing["fingerprint"]}
        write_canonical_json(keyring, policy)
        with self.assertRaises(ValueError):
            read_runtime_variant_handoff(output, target="linux-x64", keyring=keyring, keys_directory=keys)

    def test_release_reader_rejects_original_or_private_capture_mutation_during_verification(self) -> None:
        output, keyring, keys, _ = self.release_handoff()
        original = output / "validation-evidence.json"
        raw = original.read_bytes()
        for changed in ("original", "private"):
            def mutate(*args, **kwargs):
                result = verify_runtime_variant_attestation(*args, **kwargs)
                path = original if changed == "original" else kwargs["validation_evidence"]
                path.chmod(0o600)
                path.write_bytes(b"changed after full verification\n")
                return result
            try:
                with self.subTest(changed=changed), \
                        patch("ci.products.runtime_attestation.verify_runtime_variant_attestation", side_effect=mutate), \
                        self.assertRaisesRegex(ValueError, "changed during verification"):
                    read_runtime_variant_handoff(output, target="linux-x64", keyring=keyring, keys_directory=keys)
            finally:
                original.chmod(0o600)
                original.write_bytes(raw)


if __name__ == "__main__":
    unittest.main()
