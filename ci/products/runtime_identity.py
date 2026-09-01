"""Pure derivation of reusable Runtime component identity."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from .c_abi import verify_c_abi_contract
from .contract_projection import VerifiedContractProjection, _VERIFIED
from .inventory import (
    canonical_json_bytes,
    file_inventory,
    git_regular_blob_bytes,
    load_canonical_json_bytes,
    load_json_bytes,
    read_regular_file_bytes,
    require_array,
    require_exact_keys,
    require_identifier,
    require_integer,
    require_object,
    require_semver,
    require_sha256,
    sha256_bytes,
    write_canonical_json,
    run_git,
    tree_entries,
)
from .runtime_flags import load_runtime_binary_flags_bytes
from .receipt import compute_build_key, validate_receipt_inputs
from .registry import NATIVE_TARGETS, PhaseInstanceId, required_contract_components
from .selection import classify_paths, phase_git_inventory, phase_inventory_paths
from .toolchain import load_toolchain_profile_bytes


SCHEMA_VERSION = 1
SOURCE_FIELDS = (
    "schemaVersion",
    "binaryBuildKey",
    "runtimeCompatibilityVersion",
    "target",
    "contract",
    "cAbi",
    "appServer",
    "toolchainProfile",
)
ENVELOPE_FIELDS = (*SOURCE_FIELDS, "componentId", "runtimeIdentityJson")
_ABI_ROOT = "codex-agent-runtime-desktop/native/c-api"
_APP_SERVER_MANIFEST = "codex-agent-runtime-desktop/codex-app-server-distributions.json"
_BINARY_FLAGS_PATH = f"{_ABI_ROOT}/binary-flags.json"
_TOOLCHAIN_PROFILE_ROOT = "gradle/release/toolchains/runtime"
_APP_SERVER_TARGETS = {
    "macos-arm64": "macosArm64",
    "macos-x64": "macosX64",
    "linux-arm64": "linuxArm64",
    "linux-x64": "linuxX64",
    "windows-x64": "mingwX64",
}
_GIT_OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def _stable_semver(value: Any, label: str) -> str:
    version = require_semver(value, label)
    if "-" in version:
        raise ValueError(f"{label} must be a stable SemVer")
    return version


def _validate_source(value: Any) -> dict[str, Any]:
    source = require_exact_keys(value, SOURCE_FIELDS, "Runtime binary identity source")
    if require_integer(source["schemaVersion"], "Runtime binary identity source.schemaVersion", 1) != SCHEMA_VERSION:
        raise ValueError("Unsupported Runtime binary identity source schemaVersion")

    binary_build_key = require_sha256(
        source["binaryBuildKey"], "Runtime binary identity source.binaryBuildKey",
    )
    compatibility = _stable_semver(
        source["runtimeCompatibilityVersion"],
        "Runtime binary identity source.runtimeCompatibilityVersion",
    )
    if not compatibility.endswith(".0"):
        raise ValueError("Runtime binary identity compatibility version must be MAJOR.MINOR.0")
    target = require_identifier(source["target"], "Runtime binary identity source.target")
    if target not in NATIVE_TARGETS:
        raise ValueError("Runtime binary identity source.target is unsupported")

    contract = require_exact_keys(
        source["contract"], {"digest", "componentDigest"},
        "Runtime binary identity source.contract",
    )
    contract_value = {
        "digest": require_sha256(contract["digest"], "Runtime binary identity source.contract.digest"),
        "componentDigest": require_sha256(
            contract["componentDigest"],
            "Runtime binary identity source.contract.componentDigest",
        ),
    }

    c_abi = require_exact_keys(
        source["cAbi"],
        {
            "version",
            "minimumCompatibleVersion",
            "identitySchemaVersion",
            "headerSha256",
            "symbolSetSha256",
            "symbolCount",
        },
        "Runtime binary identity source.cAbi",
    )
    current_version = _stable_semver(c_abi["version"], "Runtime binary identity source.cAbi.version")
    minimum_version = _stable_semver(
        c_abi["minimumCompatibleVersion"],
        "Runtime binary identity source.cAbi.minimumCompatibleVersion",
    )
    current_parts = tuple(int(part) for part in current_version.split("."))
    minimum_parts = tuple(int(part) for part in minimum_version.split("."))
    if minimum_parts[0] != current_parts[0] or minimum_parts > current_parts:
        raise ValueError("Runtime binary identity minimum C ABI must share the current major and not exceed it")
    identity_schema = require_integer(
        c_abi["identitySchemaVersion"],
        "Runtime binary identity source.cAbi.identitySchemaVersion",
        1,
    )
    if identity_schema > 0xFFFFFFFF:
        raise ValueError("Runtime binary identity C ABI schema version is out of range")
    c_abi_value = {
        "version": current_version,
        "minimumCompatibleVersion": minimum_version,
        "identitySchemaVersion": identity_schema,
        "headerSha256": require_sha256(
            c_abi["headerSha256"], "Runtime binary identity source.cAbi.headerSha256",
        ),
        "symbolSetSha256": require_sha256(
            c_abi["symbolSetSha256"], "Runtime binary identity source.cAbi.symbolSetSha256",
        ),
        "symbolCount": require_integer(
            c_abi["symbolCount"], "Runtime binary identity source.cAbi.symbolCount", 1,
        ),
    }

    app_server = require_exact_keys(
        source["appServer"], {"version", "releaseTag", "binarySha256"},
        "Runtime binary identity source.appServer",
    )
    app_server_version = _stable_semver(
        app_server["version"], "Runtime binary identity source.appServer.version",
    )
    if app_server["releaseTag"] != f"rust-v{app_server_version}":
        raise ValueError("Runtime binary identity app-server release tag/version mismatch")
    app_server_value = {
        "version": app_server_version,
        "releaseTag": app_server["releaseTag"],
        "binarySha256": require_sha256(
            app_server["binarySha256"],
            "Runtime binary identity source.appServer.binarySha256",
        ),
    }

    toolchain = require_exact_keys(
        source["toolchainProfile"], {"id", "digest"},
        "Runtime binary identity source.toolchainProfile",
    )
    toolchain_id = require_identifier(
        toolchain["id"], "Runtime binary identity source.toolchainProfile.id",
    )
    if toolchain_id != target:
        raise ValueError("Runtime binary identity toolchain profile ID must equal its target")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "binaryBuildKey": binary_build_key,
        "runtimeCompatibilityVersion": compatibility,
        "target": target,
        "contract": contract_value,
        "cAbi": c_abi_value,
        "appServer": app_server_value,
        "toolchainProfile": {
            "id": toolchain_id,
            "digest": require_sha256(
                toolchain["digest"],
                "Runtime binary identity source.toolchainProfile.digest",
            ),
        },
    }


def derive_runtime_identity(value: Any) -> dict[str, Any]:
    """Validate primary inputs and return the exact derived identity envelope."""
    source = _validate_source(value)
    component_id = sha256_bytes(canonical_json_bytes({
        "appServer": source["appServer"],
        "binaryBuildKey": source["binaryBuildKey"],
        "cAbi": source["cAbi"],
        "contract": source["contract"],
        "runtimeCompatibilityVersion": source["runtimeCompatibilityVersion"],
        "target": source["target"],
        "toolchainProfile": source["toolchainProfile"],
    }))
    identity = {
        "appServerVersion": source["appServer"]["version"],
        "buildInputDigest": source["binaryBuildKey"],
        "cAbiVersion": source["cAbi"]["version"],
        "componentId": component_id,
        "contractComponentDigest": source["contract"]["componentDigest"],
        "contractDigest": source["contract"]["digest"],
        "runtimeCompatibilityVersion": source["runtimeCompatibilityVersion"],
        "schemaVersion": source["cAbi"]["identitySchemaVersion"],
        "target": source["target"],
    }
    return {
        **source,
        "componentId": component_id,
        "runtimeIdentityJson": canonical_json_bytes(identity)[:-1].decode("utf-8"),
    }


def validate_runtime_identity(value: Any) -> dict[str, Any]:
    """Reject any envelope that is not the exact deterministic derivation."""
    envelope = require_exact_keys(value, ENVELOPE_FIELDS, "Runtime binary identity envelope")
    expected = derive_runtime_identity({field: envelope[field] for field in SOURCE_FIELDS})
    if envelope != expected:
        raise ValueError("Runtime binary identity envelope does not match its derived identity")
    return envelope


def derive_runtime_identity_from_git(
    root: Path,
    revision: str,
    plan: Any,
    contract_projection: VerifiedContractProjection,
) -> dict[str, Any]:
    """Derive the post-build-key envelope from exact Git and authenticated Contract inputs."""
    if type(revision) is not str or _GIT_OBJECT_ID.fullmatch(revision) is None:
        raise ValueError("Repository revision must be an exact lowercase Git object ID")
    planned = require_exact_keys(
        plan,
        {"schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs"},
        "Runtime binary plan",
    )
    target = planned["target"]
    if (
        planned["schemaVersion"] != 1
        or planned["product"] != "runtime"
        or planned["component"] != target
        or planned["phase"] != "binary"
        or target not in NATIVE_TARGETS
    ):
        raise ValueError("Runtime binary plan identity is invalid")
    if type(contract_projection) is not VerifiedContractProjection:
        raise ValueError("Authenticated Contract projection is required for Runtime identity")
    projection = contract_projection.receipt_value()
    inputs = validate_receipt_inputs(planned["inputs"])
    expected_build_key = compute_build_key(
        product=planned["product"],
        component=planned["component"],
        phase=planned["phase"],
        target=planned["target"],
        inputs=inputs,
    )
    if planned["buildKey"] != expected_build_key:
        raise ValueError("Runtime binary plan buildKey does not match its canonical inputs")
    instance = PhaseInstanceId("runtime", target, "binary", target)
    if inputs["inventory"] != phase_git_inventory(Path(root), revision, instance):
        raise ValueError("Runtime binary plan inventory does not match the exact Git revision")
    contract_inputs = [
        upstream for upstream in inputs["upstreamArtifacts"]
        if (
            upstream["product"], upstream["component"], upstream["phase"], upstream["target"]
        ) == ("contract", "contract", "metadata", "common")
    ]
    if len(contract_inputs) != 1 or contract_inputs[0].get("contractProjection") != projection:
        raise ValueError("Runtime binary plan Contract projection does not match authenticated evidence")
    component_digests = {
        record["component"]: record["sha256"]
        for record in require_array(projection["componentDigests"], "Contract component digests")
    }
    if target not in component_digests:
        raise ValueError("Contract projection lacks the Runtime target component")

    def blob(relative: str, limit: int = 8 * 1024 * 1024) -> bytes:
        return git_regular_blob_bytes(Path(root), revision, relative, max_bytes=limit)

    with tempfile.TemporaryDirectory(prefix="codex-agent-runtime-identity-") as temporary:
        directory = Path(temporary)
        paths = {
            "contract": directory / "abi-contract.json",
            "header": directory / "codex_agent.h",
            "macos": directory / "macos.exports",
            "linux": directory / "linux.map",
            "windows": directory / "windows.def",
        }
        sources = {
            "contract": f"{_ABI_ROOT}/abi-contract.json",
            "header": f"{_ABI_ROOT}/include/codex_agent.h",
            "macos": f"{_ABI_ROOT}/exports/macos.exports",
            "linux": f"{_ABI_ROOT}/exports/linux.map",
            "windows": f"{_ABI_ROOT}/exports/windows.def",
        }
        for name, path in paths.items():
            path.write_bytes(blob(sources[name]))
        abi = verify_c_abi_contract(
            paths["contract"], paths["header"], paths["macos"], paths["linux"], paths["windows"],
        )

    app_manifest = require_exact_keys(
        load_json_bytes(blob(_APP_SERVER_MANIFEST)),
        {"version", "releaseTag", "distributions"},
        "App-server distribution manifest",
    )
    distributions = [
        require_exact_keys(
            value,
            {
                "target", "classifier", "asset", "archiveSha256", "archiveEntry",
                "binarySha256", "executableName", "supervisorExecutableName",
            },
            f"App-server distribution[{index}]",
        )
        for index, value in enumerate(require_array(
            app_manifest["distributions"], "App-server distributions",
        ))
    ]
    app_records = [
        value for value in distributions if value["target"] == _APP_SERVER_TARGETS[target]
    ]
    if len(app_records) != 1:
        raise ValueError("App-server distribution manifest lacks one exact Runtime target")
    app = app_records[0]
    return derive_runtime_identity({
        "schemaVersion": 1,
        "binaryBuildKey": planned["buildKey"],
        "runtimeCompatibilityVersion": inputs.get("versionIdentity"),
        "target": target,
        "contract": {
            "digest": projection["contractDigest"],
            "componentDigest": component_digests[target],
        },
        "cAbi": {
            "version": abi["current"]["semver"],
            "minimumCompatibleVersion": abi["minimumCompatible"]["semver"],
            "identitySchemaVersion": abi["runtimeIdentitySchemaVersion"],
            "headerSha256": sha256_bytes(blob(sources["header"])),
            "symbolSetSha256": "sha256:" + abi["publicSymbolsSha256"],
            "symbolCount": abi["publicSymbolCount"],
        },
        "appServer": {
            "version": app_manifest["version"],
            "releaseTag": app_manifest["releaseTag"],
            "binarySha256": "sha256:" + app["binarySha256"],
        },
        "toolchainProfile": {
            "id": target,
            "digest": inputs.get("toolchainProfileDigest"),
        },
    })


def verify_runtime_binary_plan(
    root: Path,
    revision: str,
    value: Any,
    verified_contract_manifest: Any,
    *,
    expected_target: str,
    expected_runtime_version: str,
    expected_flags_digest: str,
) -> dict[str, Any]:
    """Verify a serialized plan against Git, checkout bytes, and a settings-verified Contract."""
    plan = require_exact_keys(
        value,
        {
            "schemaVersion", "product", "component", "phase", "target",
            "buildKey", "inputs", "runtimeBinaryIdentity",
        },
        "Runtime binary plan",
    )
    inputs = validate_receipt_inputs(plan["inputs"])
    target = require_identifier(expected_target, "Expected Runtime target")
    if target not in NATIVE_TARGETS or plan["target"] != target or plan["component"] != target:
        raise ValueError("Runtime binary plan target does not match the requested Runtime target")
    runtime_version = require_semver(expected_runtime_version, "Expected Runtime version")
    if "+" in runtime_version:
        raise ValueError("Expected Runtime version must not contain build metadata")
    major, minor, _ = runtime_version.split("-", 1)[0].split(".")
    compatibility = f"{major}.{minor}.0"
    if inputs["versionIdentity"] != compatibility:
        raise ValueError("Runtime binary plan compatibility does not match the requested Runtime version")
    instance = PhaseInstanceId("runtime", target, "binary", target)
    flags_digest = load_runtime_binary_flags_bytes(git_regular_blob_bytes(
        Path(root), revision, _BINARY_FLAGS_PATH, max_bytes=65_536,
    ))[target].digest
    if (
        require_sha256(expected_flags_digest, "Expected Runtime flags digest") != flags_digest
        or inputs["flagsDigest"] != flags_digest
    ):
        raise ValueError("Runtime binary plan flags do not match the tracked target authority")
    profile = load_toolchain_profile_bytes(git_regular_blob_bytes(
        Path(root),
        revision,
        f"{_TOOLCHAIN_PROFILE_ROOT}/{target}.json",
        max_bytes=65_536,
    ), target)
    if inputs["toolchainProfileDigest"] != profile.digest:
        raise ValueError("Runtime binary plan toolchain does not match the tracked target authority")
    checked_out_flags = load_runtime_binary_flags_bytes(read_regular_file_bytes(
        Path(root) / _BINARY_FLAGS_PATH,
        max_bytes=65_536,
        reject_symlink_parents=True,
    ))[target].digest
    checked_out_profile = load_toolchain_profile_bytes(read_regular_file_bytes(
        Path(root) / f"{_TOOLCHAIN_PROFILE_ROOT}/{target}.json",
        max_bytes=65_536,
        reject_symlink_parents=True,
    ), target).digest
    if checked_out_flags != flags_digest or checked_out_profile != profile.digest:
        raise ValueError("Runtime binary checkout derived authorities do not match the exact Git revision")
    contract_upstreams = [
        upstream for upstream in inputs["upstreamArtifacts"]
        if (
            upstream["product"], upstream["component"], upstream["phase"], upstream["target"]
        ) == ("contract", "contract", "metadata", "common")
    ]
    if len(contract_upstreams) != 1 or "contractProjection" not in contract_upstreams[0]:
        raise ValueError("Runtime binary plan requires one Contract metadata projection")
    projection = contract_upstreams[0]["contractProjection"]
    if tuple(record["component"] for record in projection["componentDigests"]) != \
            required_contract_components(instance):
        raise ValueError("Runtime binary plan Contract projection has the wrong component set")
    manifest = require_exact_keys(
        verified_contract_manifest,
        {
            "schemaVersion", "product", "contractVersion", "contractDigest",
            "canonicalApiDigest", "canonicalCoverageDigest", "protocolDigest",
            "capabilityCount", "components", "mavenFiles", "evidenceFiles",
            "signing", "producer",
        },
        "Verified Contract manifest",
    )
    if manifest["schemaVersion"] != 1 or manifest["product"] != "contract":
        raise ValueError("Verified Contract manifest identity is invalid")
    if (
        projection["contractVersion"] != manifest["contractVersion"]
        or projection["contractDigest"] != manifest["contractDigest"]
        or projection["manifestSha256"] != sha256_bytes(canonical_json_bytes(manifest))
    ):
        raise ValueError("Runtime binary plan Contract identity does not match the verified manifest")
    components = require_object(manifest["components"], "Verified Contract manifest.components")
    for record in projection["componentDigests"]:
        component = record["component"]
        manifest_component = require_exact_keys(
            components.get(component),
            {"mavenPaths", "sha256"},
            f"Verified Contract manifest.components.{component}",
        )
        if record["sha256"] != manifest_component["sha256"]:
            raise ValueError("Runtime binary plan Contract component does not match the verified manifest")

    authenticated = VerifiedContractProjection(projection, _VERIFIED)
    base_plan = {key: plan[key] for key in (
        "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs",
    )}
    expected = derive_runtime_identity_from_git(root, revision, base_plan, authenticated)
    if validate_runtime_identity(plan["runtimeBinaryIdentity"]) != expected:
        raise ValueError("Runtime binary plan identity does not match its exact authorities")
    checkout_inventory = file_inventory(
        Path(root),
        [record["relativePath"] for record in inputs["inventory"]],
    )
    if checkout_inventory != inputs["inventory"]:
        raise ValueError("Runtime binary checkout bytes do not match the planned inventory")
    try:
        repository_paths = {path for path, _ in tree_entries(Path(root), revision)}
        working_paths = set(run_git(Path(root), "ls-files", "-z", binary=True).decode().split("\0"))
        working_paths.update(
            run_git(
                Path(root), "ls-files", "--others", "-z", binary=True,
            ).decode().split("\0")
        )
    except (subprocess.CalledProcessError, UnicodeDecodeError) as error:
        raise ValueError("Runtime binary checkout inventory cannot be verified") from error
    known_extra_paths = sorted(
        path for path in working_paths - repository_paths - {""}
        if not classify_paths((path,)).unknown_paths
    )
    owned_extra_paths = set(phase_inventory_paths(known_extra_paths, instance))
    if owned_extra_paths:
        raise ValueError(
            "Runtime binary checkout contains unplanned build inputs: "
            + ", ".join(sorted(owned_extra_paths))
        )
    return expected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a derived Runtime binary identity plan")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--repository-revision", required=True)
    parser.add_argument("--verified-contract-manifest", type=Path, required=True)
    parser.add_argument("--expected-target", required=True)
    parser.add_argument("--expected-runtime-version", required=True)
    parser.add_argument("--expected-flags-digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        plan = load_canonical_json_bytes(read_regular_file_bytes(
            arguments.plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
        ))
        manifest = load_canonical_json_bytes(read_regular_file_bytes(
            arguments.verified_contract_manifest,
            max_bytes=16 * 1024 * 1024,
            reject_symlink_parents=True,
        ))
        write_canonical_json(arguments.output, verify_runtime_binary_plan(
            arguments.repository_root,
            arguments.repository_revision,
            plan,
            manifest,
            expected_target=arguments.expected_target,
            expected_runtime_version=arguments.expected_runtime_version,
            expected_flags_digest=arguments.expected_flags_digest,
        ))
    except (OSError, ValueError) as error:
        try:
            arguments.output.unlink(missing_ok=True)
        except OSError:
            pass
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
