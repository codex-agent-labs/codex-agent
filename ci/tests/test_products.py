from __future__ import annotations

import copy
import os
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

import ci.products.aggregate as aggregate_product
import ci.products.inventory as inventory_product
import ci.products.signatures as signatures_product
from ci.products.aggregate import (
    CONTRACT_CHECKSUM_SUFFIXES,
    CONTRACT_COMPONENTS,
    RUNTIME_MAVEN_COMPONENTS,
    RUNTIME_TARGETS,
    contract_component_digest,
    contract_digest,
    contract_maven_identity,
    contract_required_primary_paths,
    runtime_component_id,
    validate_contract_manifest,
    validate_product_index,
    validate_runtime_aggregate,
    validate_runtime_variant,
    validate_sdk_compatibility,
    verify_contract_bundle,
    verify_immutable_product_indexes,
    verify_repository_evidence,
    verify_runtime_aggregate_artifacts,
)
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json,
    load_canonical_json_bytes,
    regular_file_inventory,
    read_regular_file_bytes,
    require_relative_path,
    require_sha256,
    sha256_bytes,
    sha256_file,
    verified_zip_contents,
    verified_zip_inventory,
    verify_regular_file_inventory,
    write_canonical_json,
)
from ci.products.receipt import (
    compute_build_key,
    output_inventory_digest,
    require_release_receipt,
    validate_output_manifest,
    validate_phase_receipt,
    verify_output_manifest,
)
from ci.products.signatures import (
    ALGORITHM,
    NAMESPACE,
    generate_development_key,
    public_key_for_metadata,
    require_active_release_key,
    require_release_signing_metadata,
    sign_manifest,
    validate_keyring,
    validate_signing_metadata,
    verify_manifest_signature,
)


DIGEST_A = sha256_bytes(b"a")
DIGEST_B = sha256_bytes(b"b")
DIGEST_C = sha256_bytes(b"c")
COMMIT = "0123456789abcdef0123456789abcdef01234567"
TREE = "89abcdef0123456789abcdef0123456789abcdef"


def signing(trust: str = "development", fingerprint: str = DIGEST_A, key_id: str = "development-test"):
    return {
        "algorithm": ALGORITHM,
        "namespace": NAMESPACE,
        "trustDomain": trust,
        "keyId": key_id,
        "fingerprint": fingerprint,
    }


def producer():
    return {
        "repository": "codex-agent-labs/codex-agent",
        "workflowPath": ".github/workflows/product-validation.yml",
        "commit": COMMIT,
        "tree": TREE,
        "event": "pull_request",
        "runId": 7,
        "runAttempt": 1,
        "pullRequest": 31,
    }


def output(path: str = "payload/value.bin", digest: str = DIGEST_A):
    return {"kind": "binary", "relativePath": path, "bytes": 1, "sha256": digest}


def output_manifest():
    return {
        "schemaVersion": 1,
        "product": "contract",
        "component": "contract",
        "phase": "binary",
        "target": "common",
        "productVersion": "0.2.0",
        "outputs": [output()],
    }


def phase_receipt(trust: str = "development"):
    inputs = {
        "inventory": [{"relativePath": "source/value.kt", "bytes": 1, "sha256": DIGEST_A}],
        "phaseInputDigest": DIGEST_A,
        "versionIdentity": "0.2.0",
        "upstreamArtifacts": [],
        "toolchainProfileDigest": DIGEST_B,
        "flagsDigest": DIGEST_C,
        "outputSchemaVersion": 1,
    }
    value = {
        "schemaVersion": 1,
        "product": "contract",
        "component": "contract",
        "phase": "binary",
        "target": "common",
        "productVersion": "0.2.0",
        "buildKey": "",
        "inputs": inputs,
        "outputs": [output()],
        "producer": producer(),
        "trustDomain": trust,
        "result": "success",
    }
    value["buildKey"] = compute_build_key(
        product=value["product"],
        component=value["component"],
        phase=value["phase"],
        target=value["target"],
        inputs=inputs,
    )
    return value


def repository_receipt(
    product: str,
    component: str,
    target: str,
    version: str,
    payload: bytes,
    upstream: list[dict] | None = None,
    trust: str = "development",
    producer_value: dict | None = None,
):
    output_record = {
        "kind": "product-evidence",
        "relativePath": f"{product}.bin",
        "bytes": len(payload),
        "sha256": sha256_bytes(payload),
    }
    inputs = {
        "inventory": [{"relativePath": f"source/{product}.txt", "bytes": 1, "sha256": DIGEST_A}],
        "phaseInputDigest": DIGEST_A,
        "versionIdentity": version,
        "upstreamArtifacts": sorted(
            upstream or [],
            key=lambda value: (
                value["product"], value["component"], value["phase"],
                value["target"], value["buildKey"],
            ),
        ),
        "toolchainProfileDigest": DIGEST_B,
        "flagsDigest": DIGEST_C,
        "outputSchemaVersion": 1,
    }
    value = {
        "schemaVersion": 1,
        "product": product,
        "component": component,
        "phase": "metadata",
        "target": target,
        "productVersion": version,
        "buildKey": "",
        "inputs": inputs,
        "outputs": [output_record],
        "producer": copy.deepcopy(producer_value or producer()),
        "trustDomain": trust,
        "result": "success",
    }
    value["buildKey"] = compute_build_key(
        product=product,
        component=component,
        phase="metadata",
        target=target,
        inputs=inputs,
    )
    return value


def repository_reference(receipt: dict):
    return {
        "product": receipt["product"],
        "component": receipt["component"],
        "phase": receipt["phase"],
        "target": receipt["target"],
        "buildKey": receipt["buildKey"],
        "outputsDigest": output_inventory_digest(receipt["outputs"]),
    }


def rewrite_repository_receipt(path: Path, receipt: dict):
    receipt["inputs"]["upstreamArtifacts"].sort(key=lambda value: (
        value["product"], value["component"], value["phase"], value["target"], value["buildKey"],
    ))
    receipt["buildKey"] = compute_build_key(
        product=receipt["product"],
        component=receipt["component"],
        phase=receipt["phase"],
        target=receipt["target"],
        inputs=receipt["inputs"],
    )
    write_canonical_json(path / "phase-receipt.json", receipt)


def repository_evidence_fixture(root: Path, trust: str = "development"):
    versions = {"contract": "1.2.3", "runtime": "2.3.4", "sdk": "3.4.5"}
    producers = []
    for character in "123":
        value = producer()
        value["commit"] = character * 40
        value["tree"] = chr(ord(character) + 3) * 40
        producers.append(value)
    contract = repository_receipt(
        "contract", "contract", "common", versions["contract"], b"contract", producer_value=producers[0],
        trust=trust,
    )
    runtime = repository_receipt(
        "runtime", "runtime-aggregate", "aggregate", versions["runtime"], b"runtime",
        upstream=[repository_reference(contract)], producer_value=producers[1], trust=trust,
    )
    sdk = repository_receipt(
        "sdk", "sdk-core", "common", versions["sdk"], b"sdk",
        upstream=[repository_reference(contract), repository_reference(runtime)],
        producer_value=producers[2], trust=trust,
    )
    receipts = {"contract": contract, "runtime": runtime, "sdk": sdk}
    directories = {}
    for product, receipt in receipts.items():
        directory = root / product
        outputs = directory / "outputs"
        outputs.mkdir(parents=True)
        payload = product.encode()
        (outputs / f"{product}.bin").write_bytes(payload)
        write_canonical_json(directory / "phase-receipt.json", receipt)
        write_canonical_json(outputs / "output-manifest.json", {
            "schemaVersion": 1,
            "product": receipt["product"],
            "component": receipt["component"],
            "phase": receipt["phase"],
            "target": receipt["target"],
            "productVersion": receipt["productVersion"],
            "outputs": receipt["outputs"],
        })
        directories[product] = directory
    return versions, directories, receipts


def artifact(path: str, *, role: str = "runtime-resolution", component: str | None = None,
             target: str | None = None, digest: str = DIGEST_A):
    value = {"path": path, "role": role, "bytes": 1, "sha256": digest}
    if component is not None:
        value["component"] = component
    if target is not None:
        value["target"] = target
    return value


def contract_manifest():
    version = "0.2.0"
    primary = contract_required_primary_paths(version)
    paths = primary | {path + suffix for path in primary for suffix in CONTRACT_CHECKSUM_SUFFIXES}
    maven = []
    for path in sorted(paths):
        identity = contract_maven_identity(path, version)
        maven.append(artifact(path, role=identity["role"], component=identity["component"]))
    components = {}
    for component in CONTRACT_COMPONENTS:
        owners = ("common",) if component == "common" else ("common", component)
        records = sorted(
            [
                record for record in maven
                if record["component"] in owners and (
                    record["role"] == "runtime-resolution" or
                    (record["role"] == "module-metadata" and
                     contract_maven_identity(record["path"], version)["kind"] in {"pom", "gradle-module"})
                )
            ],
            key=lambda record: record["path"],
        )
        components[component] = {
            "mavenPaths": [record["path"] for record in records],
            "sha256": DIGEST_A,
        }
    value = {
        "schemaVersion": 1,
        "product": "contract",
        "contractVersion": version,
        "contractDigest": "",
        "canonicalApiDigest": DIGEST_A,
        "canonicalCoverageDigest": DIGEST_B,
        "protocolDigest": DIGEST_C,
        "capabilityCount": 556,
        "components": components,
        "mavenFiles": maven,
        "evidenceFiles": [
            artifact("evidence/canonical-api.json", role="canonical-api"),
            artifact("evidence/canonical-coverage.json", role="canonical-coverage"),
            artifact("evidence/codex_app_server_protocol.schemas.json", role="protocol-schema"),
            artifact("evidence/codex_app_server_protocol.v2.schemas.json", role="protocol-schema"),
            artifact("evidence/descriptors.json", role="protocol-descriptor"),
            artifact("evidence/kotlin-parity.json", role="kotlin-parity"),
            artifact("evidence/protocol-source-verification.json", role="protocol-source-verification"),
            artifact("evidence/provenance.json", role="protocol-provenance"),
            artifact("inventories/contract-binary-inputs.git-tree", role="inventory"),
            artifact("inventories/contract-validation-inputs.git-tree", role="inventory"),
        ],
        "signing": signing(),
        "producer": producer(),
    }
    value["contractDigest"] = contract_digest(DIGEST_A, DIGEST_C, components["common"]["sha256"])
    return value


def runtime_variant(target: str = "macos-arm64", signing_metadata=None):
    value = {
        "schemaVersion": 1,
        "product": "runtime",
        "componentId": "",
        "runtimeCompatibilityVersion": "0.2.0",
        "target": target,
        "contract": {"version": "0.2.0", "digest": DIGEST_A, "componentDigest": DIGEST_B},
        "cAbi": {
            "version": "1.13.0",
            "minimumCompatibleVersion": "1.0.0",
            "identitySchemaVersion": 1,
            "headerSha256": DIGEST_A,
            "symbolSetSha256": DIGEST_B,
            "symbolCount": 778,
        },
        "appServer": {"version": "0.149.0", "releaseTag": "rust-v0.149.0", "binarySha256": DIGEST_C},
        "inputs": {
            "binaryBuildKey": DIGEST_A,
            "binaryOutputInventoryDigest": DIGEST_B,
            "binaryReceiptSha256": DIGEST_C,
            "packageReceiptSha256": DIGEST_A,
            "validationReceiptSha256": DIGEST_B,
        },
        "innerArtifacts": [
            artifact("app-server/codex.zip", role="app-server-archive"),
            artifact("c-abi/codex-agent-c.zip", role="c-abi-archive"),
            artifact("evidence/binary-receipt.json", role="binary-receipt", digest=DIGEST_C),
            artifact("evidence/package-receipt.json", role="package-receipt", digest=DIGEST_A),
            artifact("evidence/provenance.json", role="provenance"),
            artifact("evidence/sbom.json", role="sbom"),
            artifact("evidence/validation-receipt.json", role="validation-receipt", digest=DIGEST_B),
            artifact("evidence/validation.json", role="validation"),
        ],
        "toolchainProfile": {"id": target, "digest": DIGEST_A},
        "signing": signing_metadata or signing(),
    }
    value["componentId"] = runtime_component_id(value)
    return value


def runtime_aggregate():
    variants = []
    for index, target in enumerate(RUNTIME_TARGETS):
        variants.append({
            "target": target,
            "componentId": sha256_bytes(f"component-{index}".encode()),
            "bundleSha256": sha256_bytes(f"bundle-{index}".encode()),
            "manifestSha256": sha256_bytes(f"manifest-{index}".encode()),
            "receiptSha256": sha256_bytes(f"receipt-{index}".encode()),
            "sourceRuntimeVersion": "0.2.0" if index % 2 == 0 else "0.2.1",
            "reused": index != 0,
            "producer": producer(),
        })
    return {
        "schemaVersion": 1,
        "product": "runtime",
        "runtimeVersion": "0.2.2",
        "runtimeCompatibilityVersion": "0.2.0",
        "contract": {"version": "0.2.0", "digest": DIGEST_A},
        "variants": variants,
        "runtimeMavenFiles": [
            artifact(f"maven/{component}/runtime.bin", component=component)
            for component in sorted(RUNTIME_MAVEN_COMPONENTS)
        ],
        "adapterEvidence": [
            artifact("evidence/jvm.json", role="adapter", target="jvm"),
            artifact("evidence/node-js.json", role="adapter", target="node-js"),
            artifact("evidence/node-wasm.json", role="adapter", target="node-wasm"),
        ],
        "compatibility": {
            "cAbiVersion": "1.13.0",
            "minimumCAbiVersion": "1.0.0",
            "identitySchema": 1,
            "headerSha256": DIGEST_A,
            "symbolSetSha256": DIGEST_B,
            "symbolCount": 778,
            "appServerVersion": "0.149.0",
            "appServerReleaseTag": "rust-v0.149.0",
            "toolchainProfileDigests": {target: DIGEST_A for target in RUNTIME_TARGETS},
        },
        "signing": signing(),
    }


def sdk_compatibility():
    return {
        "schemaVersion": 1,
        "sdkVersion": "0.2.0",
        "contract": {"version": "0.2.0", "digest": DIGEST_A},
        "runtime": {
            "compatibleReleaseRange": ">=0.2.0 <0.3.0",
            "compatibleRuntimeCompatibilityRange": ">=0.2.0 <0.3.0",
            "requiredIdentitySchema": 1,
            "requiredContractDigest": DIGEST_A,
            "requiredAbiMajor": 1,
            "minimumAbiMinor": 13,
            "defaultRuntimeVersion": "0.2.0",
            "defaultManifestSha256": DIGEST_B,
            "embeddedVariants": [
                {
                    "target": target,
                    "componentId": sha256_bytes(f"component-{target}".encode()),
                    "bundleSha256": DIGEST_A,
                    "manifestSha256": sha256_bytes(f"manifest-{target}".encode()),
                    "runtimeLibrarySha256": DIGEST_C,
                }
                for target in sorted(RUNTIME_TARGETS)
            ],
        },
        "platformRuntime": {
            "android": {"owner": "sdk", "desktopRuntimeApplicable": False},
            "ios": {"owner": "sdk", "desktopRuntimeApplicable": False},
        },
    }


def product_index(version: str = "0.2.0"):
    artifact_name = f"codex-agent-contract-{version}.zip"
    outputs = [output(artifact_name)]
    entry = {
        "buildKey": sha256_bytes(f"build-{version}".encode()),
        "product": "contract",
        "component": "contract",
        "phase": "metadata",
        "target": "common",
        "productVersion": version,
        "coordinate": "io.github.codex-agent-labs:codex-agent-core",
        "outputInventoryDigest": output_inventory_digest(outputs),
        "outputs": outputs,
        "artifactName": artifact_name,
        "artifactSha256": DIGEST_A,
        "receiptSha256": DIGEST_B,
    }
    return {
        "schemaVersion": 1,
        "repository": "codex-agent-labs/codex-agent",
        "context": {
            "kind": "pull-request",
            "pullRequest": 31,
            "commit": COMMIT,
            "tree": TREE,
            "runId": 7,
            "runAttempt": 1,
        },
        "entries": [entry],
        "trustDomain": "development",
        "signing": signing(),
        "producer": producer(),
    }


def stable_product_index(version: str = "0.2.0"):
    value = product_index(version)
    value["context"] = {"kind": "stable", "tag": f"contract/v{version}"}
    value["trustDomain"] = "release"
    value["signing"] = signing("release")
    value["producer"]["event"] = "push"
    value["producer"]["pullRequest"] = None
    return value


def runtime_aggregate_artifacts(
    root: Path,
    private_key: Path,
    public_key: Path,
    signing_metadata,
    *,
    receipt_mutator=None,
    variant_mutator=None,
):
    root.mkdir()
    contract = contract_manifest()
    contract["signing"] = signing_metadata
    aggregate = runtime_aggregate()
    aggregate["signing"] = signing_metadata
    aggregate["contract"] = {
        "version": contract["contractVersion"],
        "digest": contract["contractDigest"],
    }
    compatibility = aggregate["compatibility"]
    contents_by_digest = {DIGEST_A: b"a", DIGEST_B: b"b", DIGEST_C: b"c"}
    bundles = {}
    receipts = {}
    public_keys = {target: public_key for target in RUNTIME_TARGETS}

    for target, record in zip(RUNTIME_TARGETS, aggregate["variants"]):
        variant = runtime_variant(target, signing_metadata)
        variant["contract"] = {
            "version": contract["contractVersion"],
            "digest": contract["contractDigest"],
            "componentDigest": contract["components"][target]["sha256"],
        }
        variant["cAbi"] = {
            "version": compatibility["cAbiVersion"],
            "minimumCompatibleVersion": compatibility["minimumCAbiVersion"],
            "identitySchemaVersion": compatibility["identitySchema"],
            "headerSha256": compatibility["headerSha256"],
            "symbolSetSha256": compatibility["symbolSetSha256"],
            "symbolCount": compatibility["symbolCount"],
        }
        variant["appServer"]["version"] = compatibility["appServerVersion"]
        variant["appServer"]["releaseTag"] = compatibility["appServerReleaseTag"]
        variant["toolchainProfile"]["digest"] = compatibility["toolchainProfileDigests"][target]
        inner_receipt_bytes = {}
        for phase, role, input_field in (
            ("binary", "binary-receipt", "binaryReceiptSha256"),
            ("package", "package-receipt", "packageReceiptSha256"),
            ("validation", "validation-receipt", "validationReceiptSha256"),
        ):
            phase_value = phase_receipt(signing_metadata["trustDomain"])
            phase_value["product"] = "runtime"
            phase_value["component"] = f"runtime-{target}"
            phase_value["phase"] = phase
            phase_value["target"] = target
            phase_value["productVersion"] = record["sourceRuntimeVersion"]
            phase_value["inputs"]["versionIdentity"] = aggregate["runtimeCompatibilityVersion"]
            phase_value["outputs"] = [output(
                f"{phase}/{target}.bin",
                sha256_bytes(f"{phase}-{target}".encode()),
            )]
            replacement = None if receipt_mutator is None else receipt_mutator(
                target, phase, phase_value,
            )
            phase_value["buildKey"] = compute_build_key(
                product=phase_value["product"],
                component=phase_value["component"],
                phase=phase_value["phase"],
                target=phase_value["target"],
                inputs=phase_value["inputs"],
            )
            contents = canonical_json_bytes(phase_value) if replacement is None else replacement
            inner_receipt_bytes[role] = contents
            inner_record = next(member for member in variant["innerArtifacts"] if member["role"] == role)
            inner_record["bytes"] = len(contents)
            inner_record["sha256"] = sha256_bytes(contents)
            variant["inputs"][input_field] = inner_record["sha256"]
            if phase == "binary":
                variant["inputs"]["binaryBuildKey"] = phase_value["buildKey"]
                variant["inputs"]["binaryOutputInventoryDigest"] = output_inventory_digest(
                    phase_value["outputs"],
                )
        if variant_mutator is not None:
            variant_mutator(target, variant)
        variant["componentId"] = runtime_component_id(variant)
        record["componentId"] = variant["componentId"]

        with tempfile.TemporaryDirectory() as staging:
            stage = Path(staging)
            manifest = stage / "runtime-variant-manifest.json"
            write_canonical_json(manifest, variant)
            signature = sign_manifest(manifest, private_key, signing_metadata)
            members = {
                member["path"]: inner_receipt_bytes.get(
                    member["role"],
                    contents_by_digest.get(member["sha256"]),
                )
                for member in variant["innerArtifacts"]
            }
            members[manifest.name] = manifest.read_bytes()
            members[signature.name] = signature.read_bytes()
            name = (
                f"codex-agent-runtime-variant-{target}-"
                f"{variant['componentId'].removeprefix('sha256:')}.zip"
            )
            bundle = root / name
            with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_STORED) as archive:
                for path in sorted(members):
                    archive.writestr(path, members[path])

        record["bundleSha256"] = sha256_file(bundle)
        record["manifestSha256"] = sha256_bytes(canonical_json_bytes(variant))
        receipt = phase_receipt(signing_metadata["trustDomain"])
        receipt["product"] = "runtime"
        receipt["component"] = f"runtime-{target}"
        receipt["phase"] = "metadata"
        receipt["target"] = target
        receipt["productVersion"] = record["sourceRuntimeVersion"]
        receipt["inputs"]["versionIdentity"] = aggregate["runtimeCompatibilityVersion"]
        receipt["outputs"] = [{
            "kind": "runtime-variant",
            "relativePath": bundle.name,
            "bytes": bundle.stat().st_size,
            "sha256": record["bundleSha256"],
        }]
        receipt["buildKey"] = compute_build_key(
            product=receipt["product"],
            component=receipt["component"],
            phase=receipt["phase"],
            target=receipt["target"],
            inputs=receipt["inputs"],
        )
        receipt_path = bundle.with_suffix(".receipt.json")
        write_canonical_json(receipt_path, receipt)
        record["receiptSha256"] = sha256_file(receipt_path)
        record["producer"] = receipt["producer"]
        bundles[target] = bundle
        receipts[target] = receipt_path
    return aggregate, contract, bundles, receipts, public_keys


class CanonicalProductJsonTest(unittest.TestCase):
    def test_canonical_bytes_are_compact_sorted_utf8_and_lf_terminated(self):
        value = {"z": [True, None, 7], "é": {"b": "é", "a": "value"}}
        contents = canonical_json_bytes(value)
        self.assertEqual(b'{"z":[true,null,7],"\xc3\xa9":{"a":"value","b":"\xc3\xa9"}}\n', contents)
        self.assertEqual(value, load_canonical_json_bytes(contents))

    def test_noncanonical_duplicate_float_and_invalid_utf8_inputs_fail(self):
        invalid = [
            b'{"a":1, "b":2}\n',
            b'{"a":1}',
            b'{"a":1}\r\n',
            b'{"a":{"x":1,"x":2}}\n',
            b'{"a":1.0}\n',
            b'{"a":NaN}\n',
            b'{"a":Infinity}\n',
            b'\xff\n',
        ]
        for contents in invalid:
            with self.subTest(contents=contents), self.assertRaises(ValueError):
                load_canonical_json_bytes(contents)
        for value in ({"value": 1.0}, {"value": (1, 2)}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_json_bytes(value)

    def test_writer_round_trips_only_exact_canonical_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            write_canonical_json(path, {"schemaVersion": 1})
            self.assertEqual({"schemaVersion": 1}, load_canonical_json(path))
            self.assertEqual(b'{"schemaVersion":1}\n', path.read_bytes())
            link = Path(temporary) / "link.json"
            try:
                link.symlink_to(path)
            except OSError:
                return
            with self.assertRaises(ValueError):
                load_canonical_json(link)


class ProductInventoryTest(unittest.TestCase):
    def test_paths_and_digests_are_exact(self):
        for path in ("", "/absolute", "../escape", "a/../b", "a//b", "a/./b", "a\\b", "C:/a", "a:\\b", "a\x00b", "a/"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                require_relative_path(path, "path")
        self.assertEqual("a/b-c_1.txt", require_relative_path("a/b-c_1.txt", "path"))
        self.assertEqual(DIGEST_A, require_sha256(DIGEST_A, "digest"))
        for digest in (DIGEST_A.upper(), DIGEST_A.removeprefix("sha256:"), "sha256:abc"):
            with self.assertRaises(ValueError):
                require_sha256(digest, "digest")

    def test_complete_regular_file_inventory_rejects_drift_empty_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / "a").mkdir()
            (root / "a/value").write_bytes(b"a")
            (root / "z").write_bytes(b"b")
            inventory = regular_file_inventory(root)
            self.assertEqual(["a/value", "z"], [record["relativePath"] for record in inventory])
            verify_regular_file_inventory(root, inventory, with_kind=False)
            changed = copy.deepcopy(inventory)
            changed[0]["sha256"] = DIGEST_C
            with self.assertRaises(ValueError):
                verify_regular_file_inventory(root, changed, with_kind=False)
            (root / "extra").write_bytes(b"x")
            with self.assertRaises(ValueError):
                verify_regular_file_inventory(root, inventory, with_kind=False)
            (root / "extra").unlink()
            (root / "empty").touch()
            with self.assertRaises(ValueError):
                regular_file_inventory(root)
            (root / "empty").unlink()
            try:
                (root / "link").symlink_to(root / "z")
            except OSError:
                return
            with self.assertRaises(ValueError):
                regular_file_inventory(root)

    def test_zip_inventory_rejects_unsafe_duplicate_special_and_noncanonical_members(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            valid = root / "valid.zip"
            with zipfile.ZipFile(valid, "w") as archive:
                archive.writestr("a/value", b"a")
                archive.writestr("z", b"z")
            self.assertEqual(["a/value", "z"], [record["relativePath"] for record in verified_zip_inventory(valid)])

            bad_paths = ("../escape", "a\\b", "a//b")
            for index, path in enumerate(bad_paths):
                archive_path = root / f"bad-{index}.zip"
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr(path, b"x")
                with self.subTest(path=path), self.assertRaises((ValueError, zipfile.BadZipFile)):
                    verified_zip_inventory(archive_path)

            duplicate = root / "duplicate.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                with zipfile.ZipFile(duplicate, "w") as archive:
                    archive.writestr("value", b"a")
                    archive.writestr("value", b"b")
            with self.assertRaises(ValueError):
                verified_zip_inventory(duplicate)

            special = root / "special.zip"
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(special, "w") as archive:
                archive.writestr(info, b"target")
            with self.assertRaises(ValueError):
                verified_zip_inventory(special)

            nul = root / "nul.zip"
            with zipfile.ZipFile(nul, "w") as archive:
                archive.writestr("nulmarker", b"x")
            raw = nul.read_bytes()
            self.assertEqual(2, raw.count(b"nulmarker"))
            nul.write_bytes(raw.replace(b"nulmarker", b"nul\0arker"))
            with self.assertRaises(ValueError):
                verified_zip_inventory(nul)

    def test_zip_inventory_can_hash_all_members_without_retaining_payloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / "selective.zip"
            with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("manifest.json", b"{}\n")
                archive.writestr("payload.bin", b"x" * (2 * 1024 * 1024))

            records, contents, _ = verified_zip_contents(
                archive_path,
                retained_paths={"manifest.json"},
                max_retained_bytes=3,
            )
            self.assertEqual(["manifest.json", "payload.bin"], [record["relativePath"] for record in records])
            self.assertEqual({"manifest.json": b"{}\n"}, contents)
            with self.assertRaisesRegex(ValueError, "Retained ZIP member contents are too large"):
                verified_zip_contents(
                    archive_path,
                    retained_paths={"manifest.json"},
                    max_retained_bytes=2,
                )

    def test_file_and_zip_snapshots_reject_concurrent_growth_and_reparse_points(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            value = root / "value.json"
            value.write_bytes(b"a")
            original_open = inventory_product._open_regular_file

            def open_then_append(path, label, **kwargs):
                descriptor, metadata = original_open(path, label, **kwargs)
                with Path(path).open("ab") as target:
                    target.write(b"x" * (1024 * 1024))
                return descriptor, metadata

            with mock.patch.object(
                inventory_product,
                "_open_regular_file",
                side_effect=open_then_append,
            ), self.assertRaisesRegex(ValueError, "changed"):
                read_regular_file_bytes(value, max_bytes=1)

            archive = root / "archive.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output_archive:
                output_archive.writestr("value", b"a")
            with mock.patch.object(
                inventory_product,
                "_open_regular_file",
                side_effect=open_then_append,
            ), self.assertRaisesRegex(ValueError, "changed"):
                verified_zip_contents(archive, max_archive_bytes=archive.stat().st_size)

            metadata = mock.Mock(st_mode=stat.S_IFREG, st_file_attributes=0x400)
            with mock.patch.object(Path, "lstat", return_value=metadata), mock.patch.object(
                inventory_product.stat,
                "FILE_ATTRIBUTE_REPARSE_POINT",
                0x400,
                create=True,
            ), self.assertRaisesRegex(ValueError, "unsafe"):
                read_regular_file_bytes(value)


class ProductReceiptTest(unittest.TestCase):
    def test_output_manifest_and_receipt_validate_exact_shapes_and_identity(self):
        self.assertEqual("contract", validate_output_manifest(output_manifest())["product"])
        receipt = phase_receipt()
        self.assertEqual(receipt, validate_phase_receipt(receipt))
        with self.assertRaises(ValueError):
            require_release_receipt(receipt)
        self.assertEqual("release", require_release_receipt(phase_receipt("release"))["trustDomain"])

        mutations = []
        extra = copy.deepcopy(receipt); extra["extra"] = True; mutations.append(extra)
        stale = copy.deepcopy(receipt); stale["buildKey"] = DIGEST_A; mutations.append(stale)
        wrong_version = copy.deepcopy(receipt); wrong_version["productVersion"] = "0.2.1"; mutations.append(wrong_version)
        boolean_size = copy.deepcopy(receipt); boolean_size["outputs"][0]["bytes"] = True; mutations.append(boolean_size)
        unsorted = copy.deepcopy(receipt); unsorted["outputs"] = [output("z"), output("a")]; mutations.append(unsorted)
        wrong_event = copy.deepcopy(receipt); wrong_event["producer"]["event"] = "push"; mutations.append(wrong_event)
        missing_pr = copy.deepcopy(receipt); missing_pr["producer"]["pullRequest"] = None; mutations.append(missing_pr)
        wrong_trust = copy.deepcopy(receipt); wrong_trust["trustDomain"] = "untrusted"; mutations.append(wrong_trust)
        wrong_result = copy.deepcopy(receipt); wrong_result["result"] = "failed"; mutations.append(wrong_result)
        for value in mutations:
            with self.assertRaises(ValueError):
                validate_phase_receipt(value)

    def test_output_manifest_verifies_the_complete_staged_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = root / "payload/value.bin"
            path.parent.mkdir()
            path.write_bytes(b"a")
            manifest = output_manifest()
            write_canonical_json(root / "output-manifest.json", manifest)
            verify_output_manifest(root, manifest)
            (root / "extra").write_bytes(b"x")
            with self.assertRaises(ValueError):
                verify_output_manifest(root, manifest)
            (root / "extra").unlink()
            wrong = copy.deepcopy(manifest); wrong["outputs"][0]["sha256"] = DIGEST_C
            with self.assertRaises(ValueError):
                verify_output_manifest(root, wrong)

    def test_runtime_component_key_uses_compatibility_identity_not_aggregate_patch(self):
        first = phase_receipt()
        first["product"] = "runtime"
        first["component"] = "macos-arm64"
        first["target"] = "macos-arm64"
        first["inputs"]["versionIdentity"] = "0.2.0"
        first["buildKey"] = compute_build_key(
            product=first["product"],
            component=first["component"],
            phase=first["phase"],
            target=first["target"],
            inputs=first["inputs"],
        )
        second = copy.deepcopy(first)
        second["productVersion"] = "0.2.1"
        validate_phase_receipt(first)
        validate_phase_receipt(second)
        self.assertEqual(first["buildKey"], second["buildKey"])
        self.assertEqual(first["outputs"], second["outputs"])

    def test_repository_evidence_aggregates_exact_products_edges_and_unequal_versions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            versions, directories, _ = repository_evidence_fixture(root)
            first = root / "repository-a.json"
            report = verify_repository_evidence(
                contract_evidence=directories["contract"],
                runtime_evidence=directories["runtime"],
                sdk_evidence=directories["sdk"],
                contract_version=versions["contract"],
                runtime_version=versions["runtime"],
                sdk_version=versions["sdk"],
                trust_domain="development",
                output=first,
            )
            self.assertEqual(["contract", "runtime", "sdk"], [value["product"] for value in report["products"]])
            self.assertEqual(
                [("contract", "runtime"), ("contract", "sdk"), ("runtime", "sdk")],
                [(value["producerProduct"], value["consumerProduct"]) for value in report["edges"]],
            )
            self.assertEqual(report, load_canonical_json(first))
            second = root / "repository-b.json"
            self.assertEqual(0, aggregate_product.main([
                "verify-repository",
                "--contract-evidence", str(directories["contract"]),
                "--runtime-evidence", str(directories["runtime"]),
                "--sdk-evidence", str(directories["sdk"]),
                "--contract-version", versions["contract"],
                "--runtime-version", versions["runtime"],
                "--sdk-version", versions["sdk"],
                "--trust-domain", "development",
                "--output", str(second),
            ]))
            self.assertEqual(first.read_bytes(), second.read_bytes())

            release_root = root / "release"
            release_versions, release_directories, _ = repository_evidence_fixture(release_root, "release")
            release = verify_repository_evidence(
                contract_evidence=release_directories["contract"],
                runtime_evidence=release_directories["runtime"],
                sdk_evidence=release_directories["sdk"],
                contract_version=release_versions["contract"],
                runtime_version=release_versions["runtime"],
                sdk_version=release_versions["sdk"],
                trust_domain="release",
                output=root / "release.json",
            )
            self.assertEqual("release", release["trustDomain"])

    def test_repository_evidence_rejects_stale_reverse_missing_and_unsafe_inputs_without_stale_success(self):
        def verify(root, versions, directories, output):
            return verify_repository_evidence(
                contract_evidence=directories["contract"],
                runtime_evidence=directories["runtime"],
                sdk_evidence=directories["sdk"],
                contract_version=versions["contract"],
                runtime_version=versions["runtime"],
                sdk_version=versions["sdk"],
                trust_domain="development",
                output=output,
            )

        mutations = (
            "stale", "reverse", "missing", "mixed-trust", "extra", "empty-directory", "manifest", "version",
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                versions, directories, receipts = repository_evidence_fixture(root)
                report = root / "repository.json"
                report.write_text("stale passed report\n")
                if mutation == "stale":
                    stale = copy.deepcopy(repository_reference(receipts["contract"]))
                    stale["buildKey"] = DIGEST_C
                    receipts["runtime"]["inputs"]["upstreamArtifacts"] = [stale]
                    rewrite_repository_receipt(directories["runtime"], receipts["runtime"])
                elif mutation == "reverse":
                    receipts["contract"]["inputs"]["upstreamArtifacts"] = [
                        repository_reference(receipts["runtime"]),
                    ]
                    rewrite_repository_receipt(directories["contract"], receipts["contract"])
                elif mutation == "missing":
                    receipts["sdk"]["inputs"]["upstreamArtifacts"] = [
                        repository_reference(receipts["contract"]),
                    ]
                    rewrite_repository_receipt(directories["sdk"], receipts["sdk"])
                elif mutation == "mixed-trust":
                    receipts["sdk"]["trustDomain"] = "release"
                    rewrite_repository_receipt(directories["sdk"], receipts["sdk"])
                elif mutation == "extra":
                    (directories["runtime"] / "unexpected.txt").write_text("unexpected\n")
                elif mutation == "empty-directory":
                    (directories["runtime"] / "outputs/unexpected").mkdir()
                elif mutation == "manifest":
                    manifest = load_canonical_json(directories["sdk"] / "outputs/output-manifest.json")
                    manifest["productVersion"] = "3.4.6"
                    write_canonical_json(directories["sdk"] / "outputs/output-manifest.json", manifest)
                else:
                    versions["contract"] = "1.2.4"
                with self.assertRaises(ValueError):
                    verify(root, versions, directories, report)
                self.assertFalse(report.exists())

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            versions, directories, _ = repository_evidence_fixture(root)
            report = root / "repository.json"
            report.write_text("stale passed report\n")
            nested = directories["contract"] / "nested-runtime"
            nested.mkdir()
            with self.assertRaisesRegex(ValueError, "distinct and non-nested"):
                verify_repository_evidence(
                    contract_evidence=directories["contract"],
                    runtime_evidence=nested,
                    sdk_evidence=directories["sdk"],
                    contract_version=versions["contract"],
                    runtime_version=versions["runtime"],
                    sdk_version=versions["sdk"],
                    trust_domain="development",
                    output=report,
                )
            self.assertFalse(report.exists())

            report.write_text("stale passed report\n")
            with self.assertRaisesRegex(ValueError, "trust domain"):
                verify_repository_evidence(
                    contract_evidence=directories["contract"],
                    runtime_evidence=directories["runtime"],
                    sdk_evidence=directories["sdk"],
                    contract_version=versions["contract"],
                    runtime_version=versions["runtime"],
                    sdk_version=versions["sdk"],
                    trust_domain="invalid",
                    output=report,
                )
            self.assertFalse(report.exists())

            linked_root = root / "linked-sdk"
            directories["sdk"].rename(root / "real-sdk")
            linked_root.symlink_to(root / "real-sdk", target_is_directory=True)
            report.write_text("stale passed report\n")
            with self.assertRaisesRegex(ValueError, "missing or unsafe"):
                verify_repository_evidence(
                    contract_evidence=directories["contract"],
                    runtime_evidence=directories["runtime"],
                    sdk_evidence=linked_root,
                    contract_version=versions["contract"],
                    runtime_version=versions["runtime"],
                    sdk_version=versions["sdk"],
                    trust_domain="development",
                    output=report,
                )
            self.assertFalse(report.exists())

    def test_repository_evidence_rejects_output_overlap_and_payload_swap(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            versions, directories, _ = repository_evidence_fixture(root)
            receipt = directories["contract"] / "phase-receipt.json"
            original_receipt = receipt.read_bytes()
            outside = root / "outside.json"
            outside.write_text("outside\n")
            linked_output = directories["contract"] / "report.json"
            linked_output.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "overlaps"):
                verify_repository_evidence(
                    contract_evidence=directories["contract"],
                    runtime_evidence=directories["runtime"],
                    sdk_evidence=directories["sdk"],
                    contract_version=versions["contract"],
                    runtime_version=versions["runtime"],
                    sdk_version=versions["sdk"],
                    trust_domain="development",
                    output=linked_output,
                )
            self.assertTrue(linked_output.is_symlink())
            self.assertEqual(b"outside\n", outside.read_bytes())
            self.assertEqual(original_receipt, receipt.read_bytes())
            linked_output.unlink()

            real_parent = root / "real-reports"
            real_parent.mkdir()
            linked_parent = root / "linked-reports"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "parent is unsafe"):
                verify_repository_evidence(
                    contract_evidence=directories["contract"],
                    runtime_evidence=directories["runtime"],
                    sdk_evidence=directories["sdk"],
                    contract_version=versions["contract"],
                    runtime_version=versions["runtime"],
                    sdk_version=versions["sdk"],
                    trust_domain="development",
                    output=linked_parent / "repository.json",
                )
            self.assertFalse((real_parent / "repository.json").exists())

            output = root / "repository.json"
            original_inventory = aggregate_product.regular_file_inventory
            changed = False

            def mutate_then_inventory(path, *arguments, **keywords):
                nonlocal changed
                if Path(path) == directories["contract"] and not changed:
                    changed = True
                    (directories["contract"] / "outputs/contract.bin").write_bytes(b"changed")
                return original_inventory(path, *arguments, **keywords)

            with mock.patch.object(
                aggregate_product,
                "regular_file_inventory",
                side_effect=mutate_then_inventory,
            ), self.assertRaisesRegex(ValueError, "file set"):
                verify_repository_evidence(
                    contract_evidence=directories["contract"],
                    runtime_evidence=directories["runtime"],
                    sdk_evidence=directories["sdk"],
                    contract_version=versions["contract"],
                    runtime_version=versions["runtime"],
                    sdk_version=versions["sdk"],
                    trust_domain="development",
                    output=output,
                )
            self.assertFalse(output.exists())


class ProductAggregateTest(unittest.TestCase):
    def test_contract_manifest_is_complete_and_coverage_is_not_runtime_identity(self):
        manifest = contract_manifest()
        validate_contract_manifest(manifest)
        changed_coverage = copy.deepcopy(manifest)
        changed_coverage["canonicalCoverageDigest"] = DIGEST_C
        validate_contract_manifest(changed_coverage)
        self.assertEqual(manifest["contractDigest"], changed_coverage["contractDigest"])

        for mutation in ("capabilities", "component", "producer"):
            invalid = copy.deepcopy(manifest)
            if mutation == "capabilities":
                invalid["capabilityCount"] = 555
            elif mutation == "component":
                invalid["components"]["common"]["sha256"] = DIGEST_B
            else:
                invalid["producer"]["commit"] = "invalid"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_contract_manifest(invalid)

        unscoped = copy.deepcopy(manifest)
        unscoped["evidenceFiles"][0]["path"] = "unscoped.bin"
        arbitrary_role = copy.deepcopy(manifest)
        arbitrary_role["evidenceFiles"][0]["role"] = "anything"
        missing_role = copy.deepcopy(manifest)
        missing_role["evidenceFiles"].pop()
        for invalid in (unscoped, arbitrary_role, missing_role):
            with self.assertRaises(ValueError):
                validate_contract_manifest(invalid)

    def test_contract_bundle_verifies_complete_declared_tree(self):
        from ci.products.contract import build_contract_bundle
        from ci.tests.test_contract_bundle import (
            PRODUCER,
            VERSION,
            _write_staging,
            _write_zip,
            _zip_entries,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            staging = root / "staging"
            _write_staging(staging)
            private_key, public_key, signing_metadata = generate_development_key(root / "key")
            archive = root / f"codex-agent-contract-{VERSION}.zip"
            build_contract_bundle(
                staging,
                archive,
                VERSION,
                PRODUCER,
                private_key,
                public_key,
                signing_metadata,
            )
            verify_contract_bundle(archive, public_key, expected_trust_domain="development")
            entries = _zip_entries(archive)
            declared = next(entry for entry in entries if entry[0].startswith("maven/"))
            variants = {
                "extra": sorted(entries + [("evidence/extra.json", b"a", 0o644 << 16)]),
                "changed": [
                    (name, b"changed" if name == declared[0] else contents, attributes)
                    for name, contents, attributes in entries
                ],
                "missing": [entry for entry in entries if entry[0] != declared[0]],
                "symlink": [
                    (name, contents, (stat.S_IFLNK | 0o777) << 16 if name == declared[0] else attributes)
                    for name, contents, attributes in entries
                ],
            }
            for name, mutated_entries in variants.items():
                mutated = root / f"{name}.zip"
                _write_zip(mutated, mutated_entries)
                with self.subTest(name=name), self.assertRaises(ValueError):
                    verify_contract_bundle(mutated, public_key, expected_trust_domain="development")

    def test_runtime_variant_excludes_aggregate_and_self_identity(self):
        variant = runtime_variant()
        validate_runtime_variant(variant)
        for field in ("runtimeVersion", "sourceRuntimeVersion", "producer", "selfDigest"):
            invalid = copy.deepcopy(variant)
            invalid[field] = "0.2.0"
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_runtime_variant(invalid)
        invalid = copy.deepcopy(variant)
        invalid["componentId"] = DIGEST_A
        with self.assertRaises(ValueError):
            validate_runtime_variant(invalid)

        changed_receipt = copy.deepcopy(variant)
        changed_receipt["inputs"]["binaryReceiptSha256"] = DIGEST_A
        next(record for record in changed_receipt["innerArtifacts"]
             if record["role"] == "binary-receipt")["sha256"] = DIGEST_A
        self.assertEqual(variant["componentId"], runtime_component_id(changed_receipt))
        validate_runtime_variant(changed_receipt)

        changed_build = copy.deepcopy(variant)
        changed_build["inputs"]["binaryBuildKey"] = DIGEST_C
        self.assertNotEqual(variant["componentId"], runtime_component_id(changed_build))

        wrong_toolchain = copy.deepcopy(variant)
        wrong_toolchain["toolchainProfile"]["id"] = "linux-x64"
        wrong_toolchain["componentId"] = runtime_component_id(wrong_toolchain)
        impossible_minimum = copy.deepcopy(variant)
        impossible_minimum["cAbi"]["minimumCompatibleVersion"] = "9.0.0"
        impossible_minimum["componentId"] = runtime_component_id(impossible_minimum)
        for invalid in (wrong_toolchain, impossible_minimum):
            with self.assertRaises(ValueError):
                validate_runtime_variant(invalid)

    def test_runtime_aggregate_requires_exact_targets_and_preserves_mixed_original_producers(self):
        aggregate = runtime_aggregate()
        validate_runtime_aggregate(aggregate)
        self.assertEqual({"0.2.0", "0.2.1"}, {record["sourceRuntimeVersion"] for record in aggregate["variants"]})
        missing = copy.deepcopy(aggregate); missing["variants"].pop()
        duplicate = copy.deepcopy(aggregate); duplicate["variants"][1]["target"] = duplicate["variants"][0]["target"]
        wrong_profile = copy.deepcopy(aggregate); wrong_profile["compatibility"]["toolchainProfileDigests"].pop("windows-x64")
        impossible_minimum = copy.deepcopy(aggregate)
        impossible_minimum["compatibility"]["minimumCAbiVersion"] = "9.0.0"
        wrong_server_tag = copy.deepcopy(aggregate)
        wrong_server_tag["compatibility"]["appServerReleaseTag"] = "rust-v0.148.0"
        bad_maven_role = copy.deepcopy(aggregate); bad_maven_role["runtimeMavenFiles"][0]["role"] = "anything"
        bad_adapter_role = copy.deepcopy(aggregate); bad_adapter_role["adapterEvidence"][0]["role"] = "anything"
        sources_only = copy.deepcopy(aggregate)
        for record in sources_only["runtimeMavenFiles"]:
            record["role"] = "sources"
        unscoped_maven = copy.deepcopy(aggregate); unscoped_maven["runtimeMavenFiles"][0]["path"] = "outside.jar"
        unscoped_maven["runtimeMavenFiles"].sort(key=lambda record: record["path"])
        unscoped_adapter = copy.deepcopy(aggregate); unscoped_adapter["adapterEvidence"][0]["path"] = "jvm.json"
        unscoped_adapter["adapterEvidence"].sort(key=lambda record: record["path"])
        for value in (
            missing, duplicate, wrong_profile, impossible_minimum, wrong_server_tag,
            bad_maven_role, bad_adapter_role, sources_only, unscoped_maven, unscoped_adapter,
        ):
            with self.assertRaises(ValueError):
                validate_runtime_aggregate(value)

    def test_aggregate_patch_version_does_not_change_variant_component_bytes(self):
        variant = runtime_variant()
        before = canonical_json_bytes(variant)
        first = runtime_aggregate()
        second = copy.deepcopy(first)
        second["runtimeVersion"] = "0.2.3"
        validate_runtime_aggregate(first)
        validate_runtime_aggregate(second)
        self.assertEqual(before, canonical_json_bytes(variant))
        self.assertEqual(variant["componentId"], runtime_component_id(variant))

    def test_sdk_compatibility_binds_contract_runtime_and_platform_ownership(self):
        compatibility = sdk_compatibility()
        validate_sdk_compatibility(compatibility)
        wrong_contract = copy.deepcopy(compatibility); wrong_contract["runtime"]["requiredContractDigest"] = DIGEST_B
        desktop_android = copy.deepcopy(compatibility); desktop_android["platformRuntime"]["android"]["desktopRuntimeApplicable"] = True
        duplicate = copy.deepcopy(compatibility); duplicate["runtime"]["embeddedVariants"][1]["target"] = RUNTIME_TARGETS[0]
        empty = copy.deepcopy(compatibility); empty["runtime"]["embeddedVariants"] = []
        malformed = copy.deepcopy(compatibility); malformed["runtime"]["compatibleReleaseRange"] = "banana"
        inverted = copy.deepcopy(compatibility); inverted["runtime"]["compatibleReleaseRange"] = ">=0.3.0 <0.2.0"
        outside = copy.deepcopy(compatibility); outside["runtime"]["compatibleReleaseRange"] = ">=0.3.0 <0.4.0"
        wrong_schema = copy.deepcopy(compatibility); wrong_schema["runtime"]["requiredIdentitySchema"] = 2
        wrong_abi = copy.deepcopy(compatibility); wrong_abi["runtime"]["minimumAbiMinor"] = 12
        duplicate_component = copy.deepcopy(compatibility)
        duplicate_component["runtime"]["embeddedVariants"][1]["componentId"] = \
            duplicate_component["runtime"]["embeddedVariants"][0]["componentId"]
        duplicate_manifest = copy.deepcopy(compatibility)
        duplicate_manifest["runtime"]["embeddedVariants"][1]["manifestSha256"] = \
            duplicate_manifest["runtime"]["embeddedVariants"][0]["manifestSha256"]
        for value in (
            wrong_contract, desktop_android, duplicate, empty, malformed, inverted, outside, wrong_schema, wrong_abi,
            duplicate_component, duplicate_manifest,
        ):
            with self.assertRaises(ValueError):
                validate_sdk_compatibility(value)

    def test_product_index_rejects_conflicting_build_keys_and_stable_bytes(self):
        existing = stable_product_index()
        validate_product_index(existing)
        verify_immutable_product_indexes(existing, copy.deepcopy(existing))

        changed = copy.deepcopy(existing)
        changed["entries"][0]["buildKey"] = DIGEST_C
        changed["entries"][0]["artifactName"] = "renamed.zip"
        changed["entries"][0]["artifactSha256"] = DIGEST_C
        changed["entries"][0]["outputs"] = [output("renamed.zip", DIGEST_C)]
        changed["entries"][0]["outputInventoryDigest"] = output_inventory_digest(changed["entries"][0]["outputs"])
        with self.assertRaises(ValueError):
            verify_immutable_product_indexes(existing, changed)

        transport_only = copy.deepcopy(existing)
        transport_only["entries"][0]["receiptSha256"] = DIGEST_C
        verify_immutable_product_indexes(existing, transport_only)

        duplicate = copy.deepcopy(existing)
        second = copy.deepcopy(duplicate["entries"][0])
        second["buildKey"] = DIGEST_C
        duplicate["entries"].append(second)
        duplicate["entries"].sort(key=lambda entry: entry["buildKey"])
        with self.assertRaises(ValueError):
            validate_product_index(duplicate)

        new_version = stable_product_index("0.2.1")
        verify_immutable_product_indexes(existing, new_version)

        same_key = stable_product_index("0.2.1")
        same_key["entries"][0]["buildKey"] = existing["entries"][0]["buildKey"]
        with self.assertRaises(ValueError):
            verify_immutable_product_indexes(existing, same_key)

    def test_sdk_default_runtime_change_requires_a_new_sdk_version(self):
        def sdk_index(compatibility):
            version = compatibility["sdkVersion"]
            artifact_name = f"codex-agent-sdk-{version}.zip"
            digest = sha256_bytes(canonical_json_bytes(compatibility))
            outputs = [output(artifact_name, digest)]
            index = product_index(version)
            index["entries"] = [{
                "buildKey": sha256_bytes(canonical_json_bytes({
                    "product": "sdk",
                    "sdkVersion": version,
                    "defaultManifestSha256": compatibility["runtime"]["defaultManifestSha256"],
                })),
                "product": "sdk",
                "component": "sdk-core",
                "phase": "metadata",
                "target": "common",
                "productVersion": version,
                "coordinate": "io.github.codex-agent-labs:codex-agent",
                "outputInventoryDigest": output_inventory_digest(outputs),
                "outputs": outputs,
                "artifactName": artifact_name,
                "artifactSha256": digest,
                "receiptSha256": DIGEST_B,
            }]
            return index

        current = sdk_compatibility()
        changed_default = copy.deepcopy(current)
        changed_default["runtime"]["defaultManifestSha256"] = DIGEST_C
        with self.assertRaises(ValueError):
            verify_immutable_product_indexes(sdk_index(current), sdk_index(changed_default))

        changed_default["sdkVersion"] = "0.2.1"
        verify_immutable_product_indexes(sdk_index(current), sdk_index(changed_default))

    def test_product_index_context_and_release_trust_are_exact(self):
        pull_request = product_index()

        promoted = copy.deepcopy(pull_request)
        promoted["context"] = {
            "kind": "promoted-main",
            "commit": COMMIT,
            "tree": TREE,
            "promotionRunId": 7,
            "promotionRunAttempt": 1,
        }
        promoted["trustDomain"] = "release"
        promoted["signing"] = signing("release")
        promoted["producer"]["event"] = "push"
        promoted["producer"]["pullRequest"] = None
        validate_product_index(promoted)

        wrong_context = copy.deepcopy(promoted); wrong_context["context"]["commit"] = "f" * 40
        development = copy.deepcopy(promoted); development["trustDomain"] = "development"; development["signing"] = signing()
        pull_producer = copy.deepcopy(promoted); pull_producer["producer"] = producer()
        stable_development = copy.deepcopy(pull_request)
        stable_development["context"] = {"kind": "stable", "tag": "contract/v0.2.0"}
        for invalid in (wrong_context, development, pull_producer, stable_development):
            with self.assertRaises(ValueError):
                validate_product_index(invalid)


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ProductSigningTest(unittest.TestCase):
    def test_development_signing_and_all_cryptographic_negatives(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, metadata = generate_development_key(root / "keys")
            manifest = root / "manifest.json"
            write_canonical_json(manifest, {"schemaVersion": 1, "signing": metadata})
            signature = sign_manifest(manifest, private_key, metadata)
            verify_manifest_signature(manifest, signature, public_key, metadata)
            if os.name != "nt":
                linked_parent = root / "linked-keys"
                linked_parent.symlink_to(public_key.parent, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "unsafe directory"):
                    verify_manifest_signature(
                        manifest,
                        signature,
                        linked_parent / public_key.name,
                        metadata,
                    )
            public_key_bytes = public_key.read_bytes()
            fingerprint = signatures_product.public_key_fingerprint

            def replace_key_after_fingerprint(contents):
                result = fingerprint(contents)
                public_key.write_bytes(public_key_bytes + b" ")
                return result

            try:
                with mock.patch.object(
                    signatures_product,
                    "public_key_fingerprint",
                    side_effect=replace_key_after_fingerprint,
                ):
                    verify_manifest_signature(manifest, signature, public_key, metadata)
            finally:
                public_key.write_bytes(public_key_bytes)
            with self.assertRaises(ValueError):
                require_release_signing_metadata(metadata)

            relabeled = copy.deepcopy(metadata); relabeled["trustDomain"] = "release"
            with self.assertRaises(ValueError):
                verify_manifest_signature(manifest, signature, public_key, relabeled)

            wrong_namespace = copy.deepcopy(metadata); wrong_namespace["namespace"] = "wrong"
            with self.assertRaises(ValueError):
                validate_signing_metadata(wrong_namespace)

            original = manifest.read_bytes()
            manifest.write_bytes(canonical_json_bytes({"schemaVersion": 2, "signing": metadata}))
            with self.assertRaises(ValueError):
                verify_manifest_signature(manifest, signature, public_key, metadata)
            manifest.write_bytes(original)

            signature_bytes = signature.read_bytes()
            signature.write_bytes(signature_bytes[:-2] + b"x\n")
            with self.assertRaises(ValueError):
                verify_manifest_signature(manifest, signature, public_key, metadata)
            signature.write_bytes(signature_bytes)
            for malformed in (
                signature_bytes + b"UNSIGNED-TRAILER\n",
                signature_bytes + signature_bytes,
                signature_bytes.replace(b"\n", b"\r\n"),
                signature_bytes.rstrip(b"\n"),
            ):
                signature.write_bytes(malformed)
                with self.assertRaises(ValueError):
                    verify_manifest_signature(manifest, signature, public_key, metadata)
            signature.write_bytes(signature_bytes)

            _, other_public, other_metadata = generate_development_key(root / "other")
            with self.assertRaises(ValueError):
                verify_manifest_signature(manifest, signature, other_public, metadata)
            wrong_fingerprint = copy.deepcopy(metadata); wrong_fingerprint["fingerprint"] = other_metadata["fingerprint"]
            with self.assertRaises(ValueError):
                verify_manifest_signature(manifest, signature, public_key, wrong_fingerprint)

    def test_runtime_aggregate_verifies_exact_signed_variant_artifacts_and_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, metadata = generate_development_key(root / "keys")
            aggregate, contract, bundles, receipts, public_keys = runtime_aggregate_artifacts(
                root / "variants", private_key, public_key, metadata,
            )

            def verify(value=aggregate, *, keys=public_keys, trust="development"):
                return verify_runtime_aggregate_artifacts(
                    value,
                    contract_manifest=contract,
                    variant_bundles=bundles,
                    metadata_receipts=receipts,
                    trusted_public_keys=keys,
                    required_trust_domain=trust,
                )

            verify()
            self.assertEqual(
                {"0.2.0", "0.2.1"},
                {record["sourceRuntimeVersion"] for record in aggregate["variants"]},
            )

            bundle_digest = copy.deepcopy(aggregate); bundle_digest["variants"][0]["bundleSha256"] = DIGEST_A
            manifest_digest = copy.deepcopy(aggregate); manifest_digest["variants"][0]["manifestSha256"] = DIGEST_A
            receipt_digest = copy.deepcopy(aggregate); receipt_digest["variants"][0]["receiptSha256"] = DIGEST_A
            contract_digest = copy.deepcopy(aggregate); contract_digest["contract"]["digest"] = DIGEST_B
            header_digest = copy.deepcopy(aggregate); header_digest["compatibility"]["headerSha256"] = DIGEST_C
            producer_mismatch = copy.deepcopy(aggregate); producer_mismatch["variants"][0]["producer"]["runId"] = 8
            for invalid in (
                bundle_digest, manifest_digest, receipt_digest, contract_digest, header_digest, producer_mismatch,
            ):
                with self.assertRaises(ValueError):
                    verify(invalid)

            missing_bundle = dict(bundles); missing_bundle.pop(RUNTIME_TARGETS[0])
            with self.assertRaises(ValueError):
                verify_runtime_aggregate_artifacts(
                    aggregate,
                    contract_manifest=contract,
                    variant_bundles=missing_bundle,
                    metadata_receipts=receipts,
                    trusted_public_keys=public_keys,
                    required_trust_domain="development",
                )
            with self.assertRaises(ValueError):
                verify(trust="release")

            _, wrong_public_key, _ = generate_development_key(root / "wrong-key")
            wrong_keys = dict(public_keys); wrong_keys[RUNTIME_TARGETS[0]] = wrong_public_key
            with self.assertRaises(ValueError):
                verify(keys=wrong_keys)

            target = RUNTIME_TARGETS[0]
            bundle = bundles[target]
            original_bundle = bundle.read_bytes()
            with zipfile.ZipFile(bundle) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            signature_name = "runtime-variant-manifest.sig"
            members[signature_name] += b"UNSIGNED-TRAILER\n"
            replacement = bundle.with_suffix(".replacement")
            with zipfile.ZipFile(replacement, "w", compression=zipfile.ZIP_STORED) as archive:
                for name in sorted(members):
                    archive.writestr(name, members[name])
            replacement.replace(bundle)
            bad_signature = copy.deepcopy(aggregate)
            bad_signature["variants"][0]["bundleSha256"] = sha256_file(bundle)
            try:
                with self.assertRaisesRegex(ValueError, "SSHSIG"):
                    verify(bad_signature)
            finally:
                bundle.write_bytes(original_bundle)

            def assert_invalid_artifacts(name, **mutators):
                values = runtime_aggregate_artifacts(
                    root / name,
                    private_key,
                    public_key,
                    metadata,
                    **mutators,
                )
                with self.assertRaises(ValueError):
                    verify_runtime_aggregate_artifacts(
                        values[0],
                        contract_manifest=values[1],
                        variant_bundles=values[2],
                        metadata_receipts=values[3],
                        trusted_public_keys=values[4],
                        required_trust_domain="development",
                    )

            assert_invalid_artifacts(
                "non-json-receipt",
                receipt_mutator=lambda target, phase, _: (
                    b"not-json\n" if target == RUNTIME_TARGETS[0] and phase == "binary" else None
                ),
            )

            def wrong_phase(target, phase, value):
                if target == RUNTIME_TARGETS[0] and phase == "binary":
                    value["phase"] = "package"

            assert_invalid_artifacts("wrong-phase-receipt", receipt_mutator=wrong_phase)

            def wrong_build_key(target, variant):
                if target == RUNTIME_TARGETS[0]:
                    variant["inputs"]["binaryBuildKey"] = sha256_bytes(b"wrong-build-key")

            assert_invalid_artifacts("wrong-binary-build-key", variant_mutator=wrong_build_key)

            def wrong_output_inventory(target, variant):
                if target == RUNTIME_TARGETS[0]:
                    variant["inputs"]["binaryOutputInventoryDigest"] = sha256_bytes(b"wrong-outputs")

            assert_invalid_artifacts("wrong-binary-outputs", variant_mutator=wrong_output_inventory)

    def test_runtime_variant_zip_limits_are_mandatory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, metadata = generate_development_key(root / "keys")
            aggregate, contract, bundles, receipts, public_keys = runtime_aggregate_artifacts(
                root / "variants", private_key, public_key, metadata,
            )
            arguments = {
                "contract_manifest": contract,
                "variant_bundles": bundles,
                "metadata_receipts": receipts,
                "trusted_public_keys": public_keys,
                "required_trust_domain": "development",
            }
            for limit in (
                "max_archive_bytes",
                "max_central_directory_bytes",
                "max_members",
                "max_entry_bytes",
                "max_total_bytes",
                "max_compression_ratio",
            ):
                with self.subTest(limit=limit), mock.patch.dict(
                    aggregate_product.RUNTIME_VARIANT_ZIP_LIMITS,
                    {limit: 0},
                ), self.assertRaises(ValueError):
                    verify_runtime_aggregate_artifacts(aggregate, **arguments)

    def test_runtime_metadata_receipt_uses_one_immutable_byte_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, metadata = generate_development_key(root / "keys")
            aggregate, contract, bundles, receipts, public_keys = runtime_aggregate_artifacts(
                root / "variants", private_key, public_key, metadata,
            )
            target = RUNTIME_TARGETS[0]
            receipt_path = receipts[target]
            valid_bytes = receipt_path.read_bytes()
            invalid = load_canonical_json_bytes(valid_bytes)
            invalid["inputs"]["flagsDigest"] = DIGEST_B
            invalid["productVersion"] = "9.9.9"
            invalid["buildKey"] = compute_build_key(
                product=invalid["product"],
                component=invalid["component"],
                phase=invalid["phase"],
                target=invalid["target"],
                inputs=invalid["inputs"],
            )
            invalid_bytes = canonical_json_bytes(invalid)
            receipt_path.write_bytes(invalid_bytes)
            next(record for record in aggregate["variants"] if record["target"] == target)[
                "receiptSha256"
            ] = sha256_bytes(invalid_bytes)
            original = aggregate_product.read_regular_file_bytes

            def read_then_replace(path, **keywords):
                contents = original(path, **keywords)
                if Path(path) == receipt_path:
                    receipt_path.write_bytes(valid_bytes)
                return contents

            with mock.patch.object(
                aggregate_product,
                "read_regular_file_bytes",
                side_effect=read_then_replace,
            ), self.assertRaises(ValueError):
                verify_runtime_aggregate_artifacts(
                    aggregate,
                    contract_manifest=contract,
                    variant_bundles=bundles,
                    metadata_receipts=receipts,
                    trusted_public_keys=public_keys,
                    required_trust_domain="development",
                )

    def test_runtime_variant_retains_only_authentication_material_before_signature_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            private_key, public_key, metadata = generate_development_key(root / "keys")
            aggregate, contract, bundles, receipts, public_keys = runtime_aggregate_artifacts(
                root / "variants", private_key, public_key, metadata,
            )
            observed: list[tuple[set[str], set[str]]] = []
            original = aggregate_product.verified_zip_contents

            def record_retained_paths(*arguments, **keywords):
                records, contents, archive_identity = original(*arguments, **keywords)
                observed.append((set(keywords["retained_paths"]), set(contents)))
                return records, contents, archive_identity

            with mock.patch.object(
                aggregate_product,
                "verified_zip_contents",
                side_effect=record_retained_paths,
            ), mock.patch.object(
                aggregate_product,
                "verify_manifest_signature",
                side_effect=ValueError("stop-after-authentication-material"),
            ), self.assertRaisesRegex(ValueError, "stop-after-authentication-material"):
                verify_runtime_aggregate_artifacts(
                    aggregate,
                    contract_manifest=contract,
                    variant_bundles=bundles,
                    metadata_receipts=receipts,
                    trusted_public_keys=public_keys,
                    required_trust_domain="development",
                )
            expected = {"runtime-variant-manifest.json", "runtime-variant-manifest.sig"}
            self.assertEqual([(expected, expected)], observed)

    def test_keyring_is_fail_closed_and_retired_keys_are_verify_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            _, public_key, metadata = generate_development_key(root / "generated")
            keys = root / "keys"; keys.mkdir()
            key_id = "release-test"
            (keys / f"{key_id}.pub").write_bytes(public_key.read_bytes())
            record = {"keyId": key_id, "fingerprint": metadata["fingerprint"]}
            empty = {
                "schemaVersion": 1,
                "namespace": NAMESPACE,
                "algorithm": ALGORITHM,
                "trustDomain": "release",
                "activeKey": None,
                "retiredKeys": [],
            }
            validate_keyring(empty, keys)
            with self.assertRaises(ValueError):
                require_active_release_key(empty, keys)

            active = copy.deepcopy(empty); active["activeKey"] = record
            self.assertEqual(record, require_active_release_key(active, keys)[0])
            release_metadata = signing("release", metadata["fingerprint"], key_id)
            self.assertEqual(keys / f"{key_id}.pub", public_key_for_metadata(
                release_metadata, active, keys, allow_retired=False,
            ))

            retired = copy.deepcopy(empty); retired["retiredKeys"] = [record]
            with self.assertRaises(ValueError):
                public_key_for_metadata(release_metadata, retired, keys, allow_retired=False)
            self.assertEqual(keys / f"{key_id}.pub", public_key_for_metadata(
                release_metadata, retired, keys, allow_retired=True,
            ))
            mismatch = copy.deepcopy(active); mismatch["activeKey"]["fingerprint"] = DIGEST_A
            with self.assertRaises(ValueError):
                validate_keyring(mismatch, keys)

            duplicate_fingerprint = copy.deepcopy(active)
            duplicate_fingerprint["retiredKeys"] = [{
                "keyId": "release-copy",
                "fingerprint": metadata["fingerprint"],
            }]
            (keys / "release-copy.pub").write_bytes(public_key.read_bytes())
            with self.assertRaises(ValueError):
                validate_keyring(duplicate_fingerprint, keys)

            malformed = root / "malformed-keys"; malformed.mkdir()
            malformed_key = b"ssh-ed25519 YQ==\n"
            (malformed / "release-bad.pub").write_bytes(malformed_key)
            invalid_keyring = copy.deepcopy(empty)
            invalid_keyring["activeKey"] = {
                "keyId": "release-bad",
                "fingerprint": sha256_bytes(b"a"),
            }
            with self.assertRaises(ValueError):
                validate_keyring(invalid_keyring, malformed)

    def test_tracked_keyring_is_canonical_and_has_no_invented_release_key(self):
        repository = Path(__file__).resolve().parents[2]
        keyring = load_canonical_json(repository / "gradle/release/product-signing-keys.json")
        validate_keyring(keyring, repository / "gradle/release/keys")
        self.assertIsNone(keyring["activeKey"])
        with self.assertRaises(ValueError):
            require_active_release_key(keyring, repository / "gradle/release/keys")


if __name__ == "__main__":
    unittest.main()
