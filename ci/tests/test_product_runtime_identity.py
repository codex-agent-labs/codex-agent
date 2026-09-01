from __future__ import annotations

import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

import ci.products.contract_projection as contract_projection
from ci.products.inventory import canonical_json_bytes, sha256_bytes, write_canonical_json
from ci.products.receipt import compute_build_key, validate_receipt_inputs
from ci.products.registry import PhaseInstanceId
from ci.products.runtime_flags import load_runtime_binary_flags
from ci.products.runtime_identity import (
    derive_runtime_identity,
    derive_runtime_identity_from_git,
    main,
    validate_runtime_identity,
    verify_runtime_binary_plan,
)
from ci.products.selection import phase_git_inventory


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def source() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "binaryBuildKey": DIGEST_A,
        "runtimeCompatibilityVersion": "0.2.0",
        "target": "macos-arm64",
        "contract": {"digest": DIGEST_A, "componentDigest": DIGEST_B},
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
        "toolchainProfile": {"id": "macos-arm64", "digest": DIGEST_A},
    }


class ProductRuntimeIdentityTest(unittest.TestCase):
    def test_exact_git_authorities_and_authenticated_contract_derive_the_envelope(self) -> None:
        checkout = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for relative in (
                "codex-agent-runtime-desktop/native/c-api/abi-contract.json",
                "codex-agent-runtime-desktop/native/c-api/binary-flags.json",
                "codex-agent-runtime-desktop/native/c-api/include/codex_agent.h",
                "codex-agent-runtime-desktop/native/c-api/exports/macos.exports",
                "codex-agent-runtime-desktop/native/c-api/exports/linux.map",
                "codex-agent-runtime-desktop/native/c-api/exports/windows.def",
                "codex-agent-runtime-desktop/codex-app-server-distributions.json",
            ):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((checkout / relative).read_bytes())
            profile_file = root / "gradle/release/toolchains/runtime/macos-arm64.json"
            profile_file.parent.mkdir(parents=True)
            write_canonical_json(profile_file, {
                "schemaVersion": 2,
                "id": "macos-arm64",
                "producers": [{
                    "role": "builder",
                    "runner": {"os": "macOS", "arch": "ARM64"},
                    "tools": [
                        {"name": name, "identity": f"fixture-{name}"}
                        for name in (
                            "gradleWrapper", "javaRuntime", "konanDependencies",
                            "kotlinNativeCompiler", "kotlinPlugin", "supervisorCompiler",
                        )
                    ],
                }],
            })
            subprocess.run(("git", "init", "-q"), cwd=root, check=True)
            subprocess.run(("git", "config", "user.email", "fixture@example.invalid"), cwd=root, check=True)
            subprocess.run(("git", "config", "user.name", "Fixture"), cwd=root, check=True)
            subprocess.run(("git", "add", "."), cwd=root, check=True)
            subprocess.run(("git", "commit", "-qm", "authorities"), cwd=root, check=True)
            revision = subprocess.run(
                ("git", "rev-parse", "HEAD"), cwd=root, check=True, capture_output=True, text=True,
            ).stdout.strip()
            manifest = {
                "schemaVersion": 1,
                "product": "contract",
                "contractVersion": "0.2.0",
                "contractDigest": DIGEST_A,
                "canonicalApiDigest": DIGEST_A,
                "canonicalCoverageDigest": DIGEST_A,
                "protocolDigest": DIGEST_A,
                "capabilityCount": 556,
                "components": {
                    "common": {"mavenPaths": ["maven/common"], "sha256": DIGEST_A},
                    "macos-arm64": {"mavenPaths": ["maven/macos"], "sha256": DIGEST_B},
                },
                "mavenFiles": [],
                "evidenceFiles": [],
                "signing": {},
                "producer": {},
            }
            flags_digest = load_runtime_binary_flags(
                root / "codex-agent-runtime-desktop/native/c-api/binary-flags.json"
            )["macos-arm64"].digest
            profile_digest = sha256_bytes(profile_file.read_bytes())
            projection = contract_projection.VerifiedContractProjection({
                "schemaVersion": 1,
                "receiptSha256": DIGEST_A,
                "bundlePath": "outputs/codex-agent-contract-0.2.0.zip",
                "bundleSha256": DIGEST_A,
                "manifestSha256": sha256_bytes(canonical_json_bytes(manifest)),
                "contractVersion": "0.2.0",
                "contractDigest": DIGEST_A,
                "componentDigests": [
                    {"component": "macos-arm64", "sha256": DIGEST_B},
                ],
            }, contract_projection._VERIFIED)
            projection_value = projection.receipt_value()
            inventory = phase_git_inventory(
                root,
                revision,
                PhaseInstanceId("runtime", "macos-arm64", "binary", "macos-arm64"),
            )
            inputs = validate_receipt_inputs({
                "inventory": inventory,
                "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
                "versionIdentity": "0.2.0",
                "upstreamArtifacts": [{
                    "product": "contract",
                    "component": "contract",
                    "phase": "metadata",
                    "target": "common",
                    "buildKey": DIGEST_A,
                    "outputsDigest": DIGEST_A,
                    "contractProjection": projection_value,
                }],
                "toolchainProfileDigest": profile_digest,
                "flagsDigest": flags_digest,
                "outputSchemaVersion": 1,
            })
            plan = {
                "schemaVersion": 1,
                "product": "runtime",
                "component": "macos-arm64",
                "phase": "binary",
                "target": "macos-arm64",
                "buildKey": compute_build_key(
                    product="runtime",
                    component="macos-arm64",
                    phase="binary",
                    target="macos-arm64",
                    inputs=inputs,
                ),
                "inputs": inputs,
            }

            envelope = derive_runtime_identity_from_git(root, revision, plan, projection)
            complete_plan = {**plan, "runtimeBinaryIdentity": envelope}

            self.assertEqual(DIGEST_A, envelope["contract"]["digest"])
            self.assertEqual(DIGEST_B, envelope["contract"]["componentDigest"])
            self.assertEqual(profile_digest, envelope["toolchainProfile"]["digest"])
            self.assertEqual("1.13.0", envelope["cAbi"]["version"])
            self.assertEqual(778, envelope["cAbi"]["symbolCount"])
            self.assertEqual("0.149.0", envelope["appServer"]["version"])
            self.assertEqual(
                envelope,
                verify_runtime_binary_plan(
                    root,
                    revision,
                    complete_plan,
                    manifest,
                    expected_target="macos-arm64",
                    expected_runtime_version="0.2.0",
                    expected_flags_digest=flags_digest,
                ),
            )
            plan_file = root / "plan.json"
            manifest_file = root / "verified-contract-manifest.json"
            output_file = root / "verified-runtime-identity.json"
            write_canonical_json(plan_file, complete_plan)
            write_canonical_json(manifest_file, manifest)
            self.assertEqual(0, main([
                "--plan", str(plan_file),
                "--repository-root", str(root),
                "--repository-revision", revision,
                "--verified-contract-manifest", str(manifest_file),
                "--expected-target", "macos-arm64",
                "--expected-runtime-version", "0.2.0",
                "--expected-flags-digest", flags_digest,
                "--output", str(output_file),
            ]))
            self.assertEqual(canonical_json_bytes(envelope), output_file.read_bytes())
            with self.assertRaisesRegex(ValueError, "exact lowercase Git object ID"):
                derive_runtime_identity_from_git(root, "HEAD", plan, projection)
            forged_plan = copy.deepcopy(plan)
            forged_plan["buildKey"] = DIGEST_A
            with self.assertRaisesRegex(ValueError, "buildKey"):
                derive_runtime_identity_from_git(root, revision, forged_plan, projection)
            mismatched_projection = contract_projection.VerifiedContractProjection({
                **projection_value,
                "contractDigest": DIGEST_C,
            }, contract_projection._VERIFIED)
            with self.assertRaisesRegex(ValueError, "Contract projection"):
                derive_runtime_identity_from_git(root, revision, plan, mismatched_projection)
            header = root / "codex-agent-runtime-desktop/native/c-api/include/codex_agent.h"
            original_header = header.read_bytes()
            header.write_bytes(original_header + b"\n")
            with self.assertRaisesRegex(ValueError, "checkout bytes"):
                verify_runtime_binary_plan(
                    root, revision, complete_plan, manifest,
                    expected_target="macos-arm64",
                    expected_runtime_version="0.2.0",
                    expected_flags_digest=flags_digest,
                )
            header.write_bytes(original_header)
            extra = root / "codex-agent-runtime-desktop/src/nativeMain/kotlin/example/Extra.kt"
            extra.parent.mkdir(parents=True)
            extra.write_text("package example\n")
            with self.assertRaisesRegex(ValueError, "unplanned build inputs"):
                verify_runtime_binary_plan(
                    root, revision, complete_plan, manifest,
                    expected_target="macos-arm64",
                    expected_runtime_version="0.2.0",
                    expected_flags_digest=flags_digest,
                )
            extra.unlink()
            profile_bytes = profile_file.read_bytes()
            profile_file.write_bytes(profile_bytes.replace(b"fixture-gradleWrapper", b"changed-gradleWrapper"))
            with self.assertRaisesRegex(ValueError, "derived authorities"):
                verify_runtime_binary_plan(
                    root, revision, complete_plan, manifest,
                    expected_target="macos-arm64",
                    expected_runtime_version="0.2.0",
                    expected_flags_digest=flags_digest,
                )
            profile_file.write_bytes(profile_bytes)
            for expected_target, expected_version, expected_flags, message in (
                ("linux-x64", "0.2.0", flags_digest, "target"),
                ("macos-arm64", "0.3.0", flags_digest, "compatibility"),
                ("macos-arm64", "0.2.0", DIGEST_A, "flags"),
            ):
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    verify_runtime_binary_plan(
                        root, revision, complete_plan, manifest,
                        expected_target=expected_target,
                        expected_runtime_version=expected_version,
                        expected_flags_digest=expected_flags,
                    )
            wrong_manifest = copy.deepcopy(manifest)
            wrong_manifest["canonicalCoverageDigest"] = DIGEST_B
            with self.assertRaisesRegex(ValueError, "Contract identity"):
                verify_runtime_binary_plan(
                    root, revision, complete_plan, wrong_manifest,
                    expected_target="macos-arm64",
                    expected_runtime_version="0.2.0",
                    expected_flags_digest=flags_digest,
                )

    def test_derives_exact_component_preimage_and_canonical_no_lf_identity(self) -> None:
        value = source()
        envelope = derive_runtime_identity(value)
        expected_component = sha256_bytes(canonical_json_bytes({
            "appServer": value["appServer"],
            "binaryBuildKey": value["binaryBuildKey"],
            "cAbi": value["cAbi"],
            "contract": value["contract"],
            "runtimeCompatibilityVersion": value["runtimeCompatibilityVersion"],
            "target": value["target"],
            "toolchainProfile": value["toolchainProfile"],
        }))
        self.assertEqual(expected_component, envelope["componentId"])
        self.assertEqual(
            '{"appServerVersion":"0.149.0","buildInputDigest":"' + DIGEST_A +
            '","cAbiVersion":"1.13.0","componentId":"' + expected_component +
            '","contractComponentDigest":"' + DIGEST_B +
            '","contractDigest":"' + DIGEST_A +
            '","runtimeCompatibilityVersion":"0.2.0","schemaVersion":1,'
            '"target":"macos-arm64"}',
            envelope["runtimeIdentityJson"],
        )
        self.assertNotIn("\n", envelope["runtimeIdentityJson"])
        self.assertEqual(envelope, validate_runtime_identity(envelope))
        self.assertEqual(envelope, derive_runtime_identity(value))

    def test_every_byte_affecting_preimage_member_changes_component_id(self) -> None:
        original = derive_runtime_identity(source())["componentId"]
        cases = []

        changed = source(); changed["binaryBuildKey"] = DIGEST_B; cases.append(("binaryBuildKey", changed))
        changed = source(); changed["runtimeCompatibilityVersion"] = "0.3.0"; cases.append(("compatibility", changed))
        changed = source(); changed["target"] = "linux-x64"; changed["toolchainProfile"]["id"] = "linux-x64"; cases.append(("target", changed))
        changed = source(); changed["contract"]["digest"] = DIGEST_C; cases.append(("contractDigest", changed))
        changed = source(); changed["contract"]["componentDigest"] = DIGEST_C; cases.append(("contractComponent", changed))
        changed = source(); changed["cAbi"]["version"] = "1.14.0"; cases.append(("cAbiVersion", changed))
        changed = source(); changed["cAbi"]["minimumCompatibleVersion"] = "1.1.0"; cases.append(("cAbiMinimum", changed))
        changed = source(); changed["cAbi"]["identitySchemaVersion"] = 2; cases.append(("identitySchema", changed))
        changed = source(); changed["cAbi"]["headerSha256"] = DIGEST_C; cases.append(("header", changed))
        changed = source(); changed["cAbi"]["symbolSetSha256"] = DIGEST_C; cases.append(("symbols", changed))
        changed = source(); changed["cAbi"]["symbolCount"] = 779; cases.append(("symbolCount", changed))
        changed = source(); changed["appServer"]["version"] = "0.150.0"; changed["appServer"]["releaseTag"] = "rust-v0.150.0"; cases.append(("appServerVersionAndTag", changed))
        changed = source(); changed["appServer"]["binarySha256"] = DIGEST_B; cases.append(("appServerBinary", changed))
        changed = source(); changed["toolchainProfile"]["digest"] = DIGEST_C; cases.append(("toolchain", changed))

        for name, changed in cases:
            with self.subTest(name=name):
                derived = derive_runtime_identity(changed)
                self.assertNotEqual(original, derived["componentId"])
                self.assertIn(derived["componentId"], derived["runtimeIdentityJson"])

    def test_rejects_release_and_provenance_members_outside_the_projection(self) -> None:
        cases = []
        for field in ("runtimeVersion", "producer", "binaryOutputInventoryDigest", "outputs"):
            changed = source(); changed[field] = "excluded"; cases.append((field, changed))
        changed = source(); changed["contract"]["version"] = "0.2.0"; cases.append(("contract.version", changed))

        for name, changed in cases:
            with self.subTest(name=name), self.assertRaises(ValueError):
                derive_runtime_identity(changed)

    def test_strictly_rejects_invalid_primary_fields(self) -> None:
        cases = []
        changed = source(); changed["schemaVersion"] = 2; cases.append(changed)
        changed = source(); changed["binaryBuildKey"] = "a" * 64; cases.append(changed)
        changed = source(); changed["runtimeCompatibilityVersion"] = "0.2.1"; cases.append(changed)
        changed = source(); changed["runtimeCompatibilityVersion"] = "0.2.0-rc.1"; cases.append(changed)
        changed = source(); changed["target"] = "android"; changed["toolchainProfile"]["id"] = "android"; cases.append(changed)
        changed = source(); changed["cAbi"]["minimumCompatibleVersion"] = "2.0.0"; cases.append(changed)
        changed = source(); changed["cAbi"]["minimumCompatibleVersion"] = "1.14.0"; cases.append(changed)
        changed = source(); changed["cAbi"]["identitySchemaVersion"] = True; cases.append(changed)
        changed = source(); changed["cAbi"]["symbolCount"] = 0; cases.append(changed)
        changed = source(); changed["appServer"]["releaseTag"] = "v0.149.0"; cases.append(changed)
        changed = source(); changed["toolchainProfile"]["id"] = "linux-x64"; cases.append(changed)

        for index, changed in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                derive_runtime_identity(changed)

    def test_rejects_tampered_or_nonexact_derived_envelopes(self) -> None:
        valid = derive_runtime_identity(source())
        cases = []
        changed = copy.deepcopy(valid); changed["componentId"] = DIGEST_B; cases.append(changed)
        changed = copy.deepcopy(valid); changed["runtimeIdentityJson"] += "\n"; cases.append(changed)
        changed = copy.deepcopy(valid); changed["producer"] = {}; cases.append(changed)
        changed = copy.deepcopy(valid); changed.pop("runtimeIdentityJson"); cases.append(changed)

        for index, changed in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                validate_runtime_identity(changed)


if __name__ == "__main__":
    unittest.main()
