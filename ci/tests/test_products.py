from __future__ import annotations

import copy
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
import warnings
import zipfile

from ci.products.aggregate import (
    CONTRACT_COMPONENTS,
    RUNTIME_MAVEN_COMPONENTS,
    RUNTIME_TARGETS,
    contract_component_digest,
    contract_digest,
    runtime_component_id,
    validate_contract_manifest,
    validate_product_index,
    validate_runtime_aggregate,
    validate_runtime_variant,
    validate_sdk_compatibility,
    verify_contract_bundle,
    verify_immutable_product_indexes,
    verify_runtime_aggregate_artifacts,
)
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json,
    load_canonical_json_bytes,
    regular_file_inventory,
    require_relative_path,
    require_sha256,
    sha256_bytes,
    sha256_file,
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


def artifact(path: str, *, role: str = "runtime-resolution", component: str | None = None,
             target: str | None = None, digest: str = DIGEST_A):
    value = {"path": path, "role": role, "bytes": 1, "sha256": digest}
    if component is not None:
        value["component"] = component
    if target is not None:
        value["target"] = target
    return value


def contract_manifest():
    maven = [
        artifact(f"maven/{component}/artifact.jar", component=component)
        for component in sorted(CONTRACT_COMPONENTS)
    ]
    components = {}
    for component in CONTRACT_COMPONENTS:
        records = [record for record in maven if record["component"] == component]
        components[component] = {
            "mavenPaths": [record["path"] for record in records],
            "sha256": contract_component_digest(records),
        }
    value = {
        "schemaVersion": 1,
        "product": "contract",
        "contractVersion": "0.2.0",
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
            artifact("evidence/kotlin-parity.json", role="kotlin-parity"),
            artifact("evidence/protocol-descriptor.bin", role="protocol-descriptor"),
            artifact("evidence/protocol-provenance.json", role="protocol-provenance"),
            artifact("evidence/protocol-schema.json", role="protocol-schema"),
            artifact("evidence/protocol-source-verification.json", role="protocol-source-verification"),
            artifact("inventories/contract-inputs.git-tree", role="inventory"),
        ],
        "signing": signing(),
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
            root = Path(temporary)
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
            root = Path(temporary)
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
            root = Path(temporary)
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
                invalid["components"]["common"]["sha256"] = DIGEST_A
            else:
                invalid["producer"] = producer()
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
        manifest = contract_manifest()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_canonical_json(root / "contract-manifest.json", manifest)
            (root / "contract-manifest.sig").write_bytes(b"signature")
            for record in manifest["mavenFiles"] + manifest["evidenceFiles"]:
                path = root / record["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"a")
            verify_contract_bundle(root, manifest)

            extra = root / "evidence/extra.json"
            extra.write_bytes(b"a")
            with self.assertRaises(ValueError):
                verify_contract_bundle(root, manifest)
            extra.unlink()

            declared = root / manifest["evidenceFiles"][0]["path"]
            declared.write_bytes(b"b")
            with self.assertRaises(ValueError):
                verify_contract_bundle(root, manifest)
            declared.write_bytes(b"a")

            missing = root / manifest["evidenceFiles"][1]["path"]
            missing.unlink()
            with self.assertRaises(ValueError):
                verify_contract_bundle(root, manifest)
            missing.write_bytes(b"a")

            link = root / "evidence/link"
            try:
                link.symlink_to(declared)
            except OSError:
                return
            with self.assertRaises(ValueError):
                verify_contract_bundle(root, manifest)

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
            root = Path(temporary)
            private_key, public_key, metadata = generate_development_key(root / "keys")
            manifest = root / "manifest.json"
            write_canonical_json(manifest, {"schemaVersion": 1, "signing": metadata})
            signature = sign_manifest(manifest, private_key, metadata)
            verify_manifest_signature(manifest, signature, public_key, metadata)
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
            root = Path(temporary)
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

    def test_keyring_is_fail_closed_and_retired_keys_are_verify_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
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
