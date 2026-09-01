from __future__ import annotations

import copy
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

from ci.products.aggregate import (
    RUNTIME_MAVEN_COMPONENTS,
    RUNTIME_TARGETS,
    runtime_component_id,
    validate_sdk_compatibility,
)
from ci.products.c_abi import TARGET_SPECS
from ci.products.contract_model import (
    CONTRACT_CHECKSUM_SUFFIXES,
    CONTRACT_COMPONENTS,
    contract_digest,
    contract_maven_identity,
    contract_required_primary_paths,
)
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    sha256_bytes,
    write_canonical_json,
)
from ci.products.sdk_compatibility import produce_sdk_compatibility
from ci.products.signatures import generate_development_key, sign_manifest


DIGEST_A = sha256_bytes(b"a")
DIGEST_B = sha256_bytes(b"b")
DIGEST_C = sha256_bytes(b"c")
COMMIT = "0123456789abcdef0123456789abcdef01234567"
TREE = "89abcdef0123456789abcdef0123456789abcdef"
LIBRARY_PATHS = {
    spec.classifier.removeprefix("c-abi-"): spec.library_path
    for spec in TARGET_SPECS.values()
}


def _producer() -> dict:
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


def _artifact(
    path: str,
    *,
    role: str = "runtime-resolution",
    component: str | None = None,
    target: str | None = None,
    contents: bytes = b"x",
) -> dict:
    value = {
        "path": path,
        "role": role,
        "bytes": len(contents),
        "sha256": sha256_bytes(contents),
    }
    if component is not None:
        value["component"] = component
    if target is not None:
        value["target"] = target
    return value


def _contract(signing: dict) -> dict:
    version = "0.2.0"
    primary = contract_required_primary_paths(version)
    paths = primary | {path + suffix for path in primary for suffix in CONTRACT_CHECKSUM_SUFFIXES}
    maven = []
    for path in sorted(paths):
        identity = contract_maven_identity(path, version)
        maven.append(_artifact(path, role=identity["role"], component=identity["component"]))
    components = {}
    for component in CONTRACT_COMPONENTS:
        owners = ("common",) if component == "common" else ("common", component)
        records = sorted(
            [
                record for record in maven
                if record["component"] in owners and (
                    record["role"] == "runtime-resolution"
                    or (
                        record["role"] == "module-metadata"
                        and contract_maven_identity(record["path"], version)["kind"]
                        in {"pom", "gradle-module"}
                    )
                )
            ],
            key=lambda record: record["path"],
        )
        components[component] = {
            "mavenPaths": [record["path"] for record in records],
            "sha256": sha256_bytes(component.encode()),
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
            _artifact("evidence/canonical-api.json", role="canonical-api"),
            _artifact("evidence/canonical-coverage.json", role="canonical-coverage"),
            _artifact("evidence/codex_app_server_protocol.schemas.json", role="protocol-schema"),
            _artifact("evidence/codex_app_server_protocol.v2.schemas.json", role="protocol-schema"),
            _artifact("evidence/descriptors.json", role="protocol-descriptor"),
            _artifact("evidence/kotlin-parity.json", role="kotlin-parity"),
            _artifact("evidence/protocol-source-verification.json", role="protocol-source-verification"),
            _artifact("evidence/provenance.json", role="protocol-provenance"),
            _artifact("inventories/contract-binary-inputs.git-tree", role="inventory"),
            _artifact("inventories/contract-validation-inputs.git-tree", role="inventory"),
        ],
        "signing": signing,
        "producer": _producer(),
    }
    value["contractDigest"] = contract_digest(
        value["canonicalApiDigest"], value["protocolDigest"], components["common"]["sha256"],
    )
    return value


def _zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name, contents in sorted(members.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, contents)


class Fixture:
    def __init__(self, root: Path, *, runtime_version: str = "0.2.0") -> None:
        self.root = root
        root.mkdir()
        self.private_key, self.public_key, self.signing = generate_development_key(root / "keys")
        self.contract = _contract(self.signing)
        self.contract_manifest = root / "contract-manifest.json"
        write_canonical_json(self.contract_manifest, self.contract)
        self.contract_signature = sign_manifest(
            self.contract_manifest, self.private_key, self.signing,
        )
        self.variant_bundles = {}
        self.variant_public_keys = {}
        aggregate_variants = []
        compatibility = {
            "cAbiVersion": "1.13.0",
            "minimumCAbiVersion": "1.0.0",
            "identitySchema": 1,
            "headerSha256": DIGEST_A,
            "symbolSetSha256": DIGEST_B,
            "symbolCount": 778,
            "appServerVersion": "0.149.0",
            "appServerReleaseTag": "rust-v0.149.0",
            "toolchainProfileDigests": {target: DIGEST_A for target in RUNTIME_TARGETS},
        }
        for index, target in enumerate(RUNTIME_TARGETS):
            library = f"runtime-library-{target}\n".encode()
            c_abi_path = root / f"c-abi-{target}.zip"
            _zip(c_abi_path, {
                "include/codex_agent.h": b"header\n",
                LIBRARY_PATHS[target]: library,
            })
            members = {
                "app-server/runtime.zip": f"app-server-{target}\n".encode(),
                "c-abi/runtime.zip": c_abi_path.read_bytes(),
                "evidence/binary-phase.json": b"binary\n",
                "evidence/package-phase.json": b"package\n",
                "evidence/provenance.json": b"provenance\n",
                "evidence/sbom.json": b"sbom\n",
                "evidence/validation-phase.json": b"validation phase\n",
                "evidence/validation.json": b"validation\n",
            }
            roles = {
                "app-server/runtime.zip": "app-server-archive",
                "c-abi/runtime.zip": "c-abi-archive",
                "evidence/binary-phase.json": "binary-phase-evidence",
                "evidence/package-phase.json": "package-phase-evidence",
                "evidence/provenance.json": "provenance",
                "evidence/sbom.json": "sbom",
                "evidence/validation-phase.json": "validation-phase-evidence",
                "evidence/validation.json": "validation",
            }
            variant = {
                "schemaVersion": 1,
                "product": "runtime",
                "componentId": "",
                "runtimeCompatibilityVersion": "0.2.0",
                "target": target,
                "contract": {
                    "digest": self.contract["contractDigest"],
                    "componentDigest": self.contract["components"][target]["sha256"],
                },
                "cAbi": {
                    "version": compatibility["cAbiVersion"],
                    "minimumCompatibleVersion": compatibility["minimumCAbiVersion"],
                    "identitySchemaVersion": compatibility["identitySchema"],
                    "headerSha256": compatibility["headerSha256"],
                    "symbolSetSha256": compatibility["symbolSetSha256"],
                    "symbolCount": compatibility["symbolCount"],
                },
                "appServer": {
                    "version": compatibility["appServerVersion"],
                    "releaseTag": compatibility["appServerReleaseTag"],
                    "binarySha256": DIGEST_C,
                },
                "inputs": {
                    "binaryBuildKey": sha256_bytes(f"build-{target}".encode()),
                    "binaryOutputInventoryDigest": DIGEST_B,
                },
                "innerArtifacts": [
                    _artifact(path, role=roles[path], contents=contents)
                    for path, contents in sorted(members.items())
                ],
                "toolchainProfile": {"id": target, "digest": DIGEST_A},
                "signing": self.signing,
            }
            variant["componentId"] = runtime_component_id(variant)
            variant_directory = root / f"variant-{target}"
            variant_directory.mkdir()
            variant_manifest = variant_directory / "runtime-variant-manifest.json"
            write_canonical_json(variant_manifest, variant)
            variant_signature = sign_manifest(variant_manifest, self.private_key, self.signing)
            bundle = root / (
                f"codex-agent-runtime-variant-{target}-"
                f"{variant['componentId'].removeprefix('sha256:')}.zip"
            )
            _zip(bundle, {
                **members,
                "runtime-variant-manifest.json": variant_manifest.read_bytes(),
                "runtime-variant-manifest.sig": variant_signature.read_bytes(),
            })
            self.variant_bundles[target] = bundle
            self.variant_public_keys[target] = self.public_key
            aggregate_variants.append({
                "target": target,
                "componentId": variant["componentId"],
                "bundleSha256": sha256_bytes(bundle.read_bytes()),
                "manifestSha256": sha256_bytes(variant_manifest.read_bytes()),
                "receiptSha256": sha256_bytes(f"receipt-{target}".encode()),
                "phaseReceipts": {
                    phase: {
                        "sha256": sha256_bytes(f"{phase}-receipt-{target}".encode()),
                        "producer": _producer(),
                    }
                    for phase in ("binary", "package", "validation")
                },
                "sourceRuntimeVersion": "0.2.0",
                "producer": _producer(),
            })
        self.aggregate = {
            "schemaVersion": 1,
            "product": "runtime",
            "runtimeVersion": runtime_version,
            "runtimeCompatibilityVersion": "0.2.0",
            "contract": {
                "version": self.contract["contractVersion"],
                "digest": self.contract["contractDigest"],
            },
            "variants": aggregate_variants,
            "runtimeMavenFiles": [
                _artifact(f"maven/{component}/runtime.bin", component=component)
                for component in sorted(RUNTIME_MAVEN_COMPONENTS)
            ],
            "adapterEvidence": [
                _artifact("evidence/jvm.json", role="adapter", target="jvm"),
                _artifact("evidence/node-js.json", role="adapter", target="node-js"),
                _artifact("evidence/node-wasm.json", role="adapter", target="node-wasm"),
            ],
            "compatibility": compatibility,
            "signing": self.signing,
        }
        self.runtime_manifest = root / f"codex-agent-runtime-{runtime_version}-manifest.json"
        write_canonical_json(self.runtime_manifest, self.aggregate)
        self.runtime_signature = sign_manifest(
            self.runtime_manifest, self.private_key, self.signing,
        )

    def arguments(self, output: Path) -> dict:
        return {
            "sdk_version": "0.2.0",
            "compatible_release_range": ">=0.2.0 <0.3.0",
            "compatible_runtime_compatibility_range": ">=0.2.0 <0.3.0",
            "contract_manifest": self.contract_manifest,
            "contract_signature": self.contract_signature,
            "contract_public_key": self.public_key,
            "runtime_manifest": self.runtime_manifest,
            "runtime_signature": self.runtime_signature,
            "runtime_public_key": self.public_key,
            "variant_bundles": self.variant_bundles,
            "variant_public_keys": self.variant_public_keys,
            "required_trust_domain": "development",
            "output": output,
        }

    def request(self) -> dict:
        return {
            "schemaVersion": 1,
            "sdkVersion": "0.2.0",
            "compatibleReleaseRange": ">=0.2.0 <0.3.0",
            "compatibleRuntimeCompatibilityRange": ">=0.2.0 <0.3.0",
            "contractManifest": str(self.contract_manifest),
            "contractSignature": str(self.contract_signature),
            "contractPublicKey": str(self.public_key),
            "runtimeManifest": str(self.runtime_manifest),
            "runtimeSignature": str(self.runtime_signature),
            "runtimePublicKey": str(self.public_key),
            "variantBundles": {
                target: str(path) for target, path in self.variant_bundles.items()
            },
            "variantPublicKeys": {
                target: str(path) for target, path in self.variant_public_keys.items()
            },
            "requiredTrustDomain": "development",
        }


class SdkCompatibilityProducerTest(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "ci.products.sdk_compatibility", *arguments],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_produces_deterministic_authenticated_compatibility(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            first_directory = root / "first"
            second_directory = root / "second"
            first_directory.mkdir()
            second_directory.mkdir()
            first_path = first_directory / "sdk-compatibility.json"
            second_path = second_directory / "sdk-compatibility.json"
            first = produce_sdk_compatibility(**fixture.arguments(first_path))
            second = produce_sdk_compatibility(**fixture.arguments(second_path))
            self.assertEqual(first_path.read_bytes(), second_path.read_bytes())
            self.assertEqual(first, second)
            self.assertEqual(canonical_json_bytes(first), first_path.read_bytes())
            validate_sdk_compatibility(first)
            self.assertEqual(
                sha256_bytes(fixture.runtime_manifest.read_bytes()),
                first["runtime"]["defaultManifestSha256"],
            )
            self.assertEqual(
                [target for target in sorted(RUNTIME_TARGETS)],
                [record["target"] for record in first["runtime"]["embeddedVariants"]],
            )
            aggregate_records = {record["target"]: record for record in fixture.aggregate["variants"]}
            for record in first["runtime"]["embeddedVariants"]:
                aggregate_record = aggregate_records[record["target"]]
                self.assertEqual(aggregate_record["componentId"], record["componentId"])
                self.assertEqual(aggregate_record["bundleSha256"], record["bundleSha256"])
                self.assertEqual(aggregate_record["manifestSha256"], record["manifestSha256"])
                expected = sha256_bytes(f"runtime-library-{record['target']}\n".encode())
                self.assertEqual(expected, record["runtimeLibrarySha256"])
            self.assertEqual(
                {"android": {"owner": "sdk", "desktopRuntimeApplicable": False},
                 "ios": {"owner": "sdk", "desktopRuntimeApplicable": False}},
                first["platformRuntime"],
            )

    def test_rejects_signature_identity_bundle_and_range_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            cases = []
            bad_contract_signature = root / "contract-manifest.sig"
            bad_contract_signature.write_bytes(fixture.contract_signature.read_bytes()[:-1] + b"x")
            arguments = fixture.arguments(root / "bad-contract" / "sdk-compatibility.json")
            arguments["contract_signature"] = bad_contract_signature
            cases.append(arguments)

            runtime_signature_directory = root / "runtime-signature"
            runtime_signature_directory.mkdir()
            bad_runtime_signature = runtime_signature_directory / fixture.runtime_signature.name
            bad_runtime_signature.write_bytes(fixture.runtime_signature.read_bytes()[:-1] + b"x")
            arguments = fixture.arguments(root / "bad-runtime" / "sdk-compatibility.json")
            arguments["runtime_signature"] = bad_runtime_signature
            cases.append(arguments)

            swapped = dict(fixture.variant_bundles)
            swapped["macos-arm64"], swapped["macos-x64"] = swapped["macos-x64"], swapped["macos-arm64"]
            arguments = fixture.arguments(root / "swapped" / "sdk-compatibility.json")
            arguments["variant_bundles"] = swapped
            cases.append(arguments)

            arguments = fixture.arguments(root / "range" / "sdk-compatibility.json")
            arguments["compatible_runtime_compatibility_range"] = ">=0.3.0 <0.4.0"
            cases.append(arguments)

            arguments = fixture.arguments(root / "missing-target" / "sdk-compatibility.json")
            arguments["variant_bundles"] = dict(fixture.variant_bundles)
            arguments["variant_bundles"].pop("windows-x64")
            cases.append(arguments)

            target = "linux-x64"
            original = fixture.variant_bundles[target]
            tampered_directory = root / "tampered-bundle"
            tampered_directory.mkdir()
            tampered = tampered_directory / original.name
            tampered.write_bytes(original.read_bytes() + b"tampered")
            bundles = dict(fixture.variant_bundles)
            bundles[target] = tampered
            arguments = fixture.arguments(root / "tampered" / "sdk-compatibility.json")
            arguments["variant_bundles"] = bundles
            cases.append(arguments)
            for arguments in cases:
                arguments["output"].parent.mkdir()
                with self.assertRaises(ValueError):
                    produce_sdk_compatibility(**arguments)
                self.assertFalse(arguments["output"].exists())

    def test_selecting_a_new_embedded_default_changes_declared_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture", runtime_version="0.2.0")
            old_output = root / "old-output" / "sdk-compatibility.json"
            unchanged_output = root / "unchanged-output" / "sdk-compatibility.json"
            new_output = root / "new-output" / "sdk-compatibility.json"
            old_output.parent.mkdir()
            unchanged_output.parent.mkdir()
            new_output.parent.mkdir()
            old = produce_sdk_compatibility(**fixture.arguments(old_output))

            patch_directory = root / "runtime-patch"
            patch_directory.mkdir()
            patch = copy.deepcopy(fixture.aggregate)
            patch["runtimeVersion"] = "0.2.1"
            patch_manifest = patch_directory / "codex-agent-runtime-0.2.1-manifest.json"
            write_canonical_json(patch_manifest, patch)
            patch_signature = sign_manifest(patch_manifest, fixture.private_key, fixture.signing)

            # A compatible newer Runtime existing beside the selected default is not an SDK input.
            produce_sdk_compatibility(**fixture.arguments(unchanged_output))
            arguments = fixture.arguments(new_output)
            arguments["runtime_manifest"] = patch_manifest
            arguments["runtime_signature"] = patch_signature
            new = produce_sdk_compatibility(**arguments)
            self.assertEqual(old_output.read_bytes(), unchanged_output.read_bytes())
            self.assertNotEqual(old_output.read_bytes(), new_output.read_bytes())
            self.assertEqual(old["runtime"]["embeddedVariants"], new["runtime"]["embeddedVariants"])
            self.assertEqual("0.2.0", old["runtime"]["defaultRuntimeVersion"])
            self.assertEqual("0.2.1", new["runtime"]["defaultRuntimeVersion"])
            self.assertNotEqual(
                old["runtime"]["defaultManifestSha256"], new["runtime"]["defaultManifestSha256"],
            )

    def test_direct_module_cli_writes_the_canonical_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            request = root / "request.json"
            write_canonical_json(request, fixture.request())
            output = root / "output" / "sdk-compatibility.json"
            output.parent.mkdir()
            result = self.run_cli("--request", str(request), "--output", str(output))
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(
                canonical_json_bytes(validate_sdk_compatibility(
                    load_canonical_json_bytes(output.read_bytes()),
                )),
                output.read_bytes(),
            )

    def test_direct_module_cli_rejects_invalid_requests_without_removing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            fixture = Fixture(root / "fixture")
            output = root / "output" / "sdk-compatibility.json"
            output.parent.mkdir()
            output.write_bytes(b"keep\n")
            valid = fixture.request()
            cases = {
                "unknown": {**valid, "unknown": "value"},
                "missing": {key: value for key, value in valid.items() if key != "sdkVersion"},
                "non-string": {**valid, "sdkVersion": 2},
                "traversal": {**valid, "contractManifest": "../contract-manifest.json"},
                "missing-target": {
                    **valid,
                    "variantBundles": {
                        target: value for target, value in valid["variantBundles"].items()
                        if target != "windows-x64"
                    },
                },
            }
            for name, value in cases.items():
                request = root / f"{name}.json"
                write_canonical_json(request, value)
                result = self.run_cli(
                    "--request", str(request), "--output", str(output),
                )
                self.assertEqual(2, result.returncode, (name, result.stderr))
                self.assertEqual(b"keep\n", output.read_bytes(), name)

            canonical_request = root / "canonical-request.json"
            write_canonical_json(canonical_request, valid)
            existing = self.run_cli(
                "--request", str(canonical_request), "--output", str(output),
            )
            self.assertEqual(2, existing.returncode, existing.stderr)
            self.assertEqual(b"keep\n", output.read_bytes())

            noncanonical_request = root / "noncanonical-request.json"
            noncanonical_request.write_text("{\n  \"schemaVersion\": 1\n}\n", encoding="utf-8")
            noncanonical = self.run_cli(
                "--request", str(noncanonical_request), "--output", str(output),
            )
            self.assertEqual(2, noncanonical.returncode, noncanonical.stderr)
            self.assertEqual(b"keep\n", output.read_bytes())

            request_link = root / "request-link.json"
            request_link.symlink_to(canonical_request)
            linked = self.run_cli(
                "--request", str(request_link), "--output", str(output),
            )
            self.assertEqual(2, linked.returncode, linked.stderr)
            self.assertEqual(b"keep\n", output.read_bytes())

            unknown_argument = self.run_cli(
                "--request", str(canonical_request), "--output", str(output), "--unknown",
            )
            self.assertEqual(2, unknown_argument.returncode, unknown_argument.stderr)
            self.assertEqual(b"keep\n", output.read_bytes())


if __name__ == "__main__":
    unittest.main()
