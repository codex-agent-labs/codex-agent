from __future__ import annotations

import argparse
from pathlib import Path
import re
import stat
import sys
from typing import Any

from .contract_projection import (
    VerifiedContractProjection,
    verify_contract_component_projection,
)
from .inventory import (
    canonical_json_bytes,
    git_regular_blob_bytes,
    load_canonical_json_bytes,
    read_regular_file_bytes,
    require_array,
    require_exact_keys,
    require_integer,
    require_object,
    require_semver,
    require_string,
    sha256_bytes,
    write_canonical_json,
)
from .receipt import (
    compute_build_key,
    output_inventory_digest,
    validate_phase_receipt,
    validate_receipt_inputs,
)
from .registry import (
    COMPONENTS_BY_IDENTITY,
    NATIVE_BINDINGS,
    NATIVE_TARGETS,
    PHASE_INSTANCE_IDS,
    SDK_COMPATIBILITY_COMPONENTS,
    VERSIONLESS_PHASE_IDS,
    VERSION_IDENTITIES,
    PhaseInstanceId,
    phase_instance_dependencies,
    required_contract_components,
    required_toolchain_profile,
)
from .selection import phase_git_inventory
from .runtime_flags import load_runtime_binary_flags_bytes
from .runtime_identity import derive_runtime_identity_from_git
from .toolchain import load_toolchain_profile_bytes


_RUNTIME_BINARY_FLAGS_PATH = "codex-agent-runtime-desktop/native/c-api/binary-flags.json"
_RUNTIME_TOOLCHAIN_PROFILE_ROOT = "gradle/release/toolchains/runtime"
_GIT_OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def _runtime_compatibility_version(release_version: str) -> str:
    major, minor, _ = release_version.split("-", 1)[0].split(".")
    return f"{major}.{minor}.0"


def verified_phase_flags_digest(
    root: Path,
    revision: str,
    instance: PhaseInstanceId,
    supplied_digest: str,
) -> str:
    if type(revision) is not str or _GIT_OBJECT_ID.fullmatch(revision) is None:
        raise ValueError("Repository revision must be an exact lowercase Git object ID")
    if (
        instance.product == "runtime"
        and instance.component in NATIVE_TARGETS
        and instance.phase == "binary"
    ):
        expected = load_runtime_binary_flags_bytes(
            git_regular_blob_bytes(
                root,
                revision,
                _RUNTIME_BINARY_FLAGS_PATH,
                max_bytes=65_536,
            )
        )[instance.component].digest
        if supplied_digest != expected:
            raise ValueError("Plan request flagsDigest does not match the tracked target authority")
        return expected
    return supplied_digest


def verified_phase_toolchain_digest(
    root: Path,
    revision: str,
    instance: PhaseInstanceId,
    supplied_digest: str,
) -> str:
    profile_id = required_toolchain_profile(instance)
    if profile_id is None:
        return supplied_digest
    if type(revision) is not str or _GIT_OBJECT_ID.fullmatch(revision) is None:
        raise ValueError("Repository revision must be an exact lowercase Git object ID")
    profile = load_toolchain_profile_bytes(
        git_regular_blob_bytes(
            root,
            revision,
            f"{_RUNTIME_TOOLCHAIN_PROFILE_ROOT}/{profile_id}.json",
            max_bytes=65_536,
        ),
        profile_id,
    )
    if supplied_digest != profile.digest:
        raise ValueError("Plan request toolchainProfileDigest does not match the tracked target authority")
    return profile.digest


def _validated_versions(versions: Any) -> dict[str, str]:
    values = require_exact_keys(versions, VERSION_IDENTITIES, "product versions")
    validated = {
        name: require_semver(value, f"product versions.{name}")
        for name, value in values.items()
    }
    if validated["runtime-compatibility"] != _runtime_compatibility_version(
        validated["runtime-release"]
    ):
        raise ValueError("Runtime compatibility identity does not match Runtime release")
    return validated


def _phase_version_identity(
    instance: PhaseInstanceId,
    versions: dict[str, str],
) -> str | None:
    if instance.logical_phase in VERSIONLESS_PHASE_IDS:
        return None
    component = COMPONENTS_BY_IDENTITY[(instance.product, instance.component)]
    return versions[component.version_identity]


def _validate_upstream_version(
    consumer: PhaseInstanceId,
    instance: PhaseInstanceId,
    receipt: dict[str, Any],
    versions: dict[str, str],
) -> None:
    compatible_embedded_runtime = (
        consumer.product == "sdk"
        and (
            consumer.phase == "package" and consumer.component in SDK_COMPATIBILITY_COMPONENTS
            or consumer.phase == "validation" and consumer.component in NATIVE_BINDINGS
        )
        and instance.product == "runtime"
    )
    if compatible_embedded_runtime:
        expected_identity = (
            receipt["productVersion"]
            if instance.component == "runtime-aggregate"
            else _runtime_compatibility_version(receipt["productVersion"])
        )
        if receipt["inputs"]["versionIdentity"] != expected_identity:
            raise ValueError(f"Incompatible embedded Runtime version identity: {instance}")
        return
    if instance.product == "runtime" and instance.component != "runtime-aggregate":
        if _runtime_compatibility_version(receipt["productVersion"]) != versions["runtime-compatibility"]:
            raise ValueError(f"Incompatible upstream Runtime release: {instance}")
    else:
        release_identity = {
            "contract": "contract",
            "runtime": "runtime-release",
            "sdk": "sdk",
        }[instance.product]
        if receipt["productVersion"] != versions[release_identity]:
            raise ValueError(f"Incompatible upstream product release: {instance}")
    if receipt["inputs"]["versionIdentity"] != _phase_version_identity(instance, versions):
        raise ValueError(f"Incompatible upstream version identity: {instance}")


def _receipt_identity(receipt: dict[str, Any]) -> PhaseInstanceId:
    return PhaseInstanceId(
        receipt["product"],
        receipt["component"],
        receipt["phase"],
        receipt["target"],
    )


def _upstream_record(
    receipt: dict[str, Any],
    contract_projection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "product": receipt["product"],
        "component": receipt["component"],
        "phase": receipt["phase"],
        "target": receipt["target"],
        "buildKey": receipt["buildKey"],
        "outputsDigest": output_inventory_digest(receipt["outputs"]),
    }
    if contract_projection is not None:
        record["contractProjection"] = contract_projection
    return record


def _contract_projection_value(
    instance: PhaseInstanceId,
    receipt: dict[str, Any],
    projection: VerifiedContractProjection | None,
) -> dict[str, Any] | None:
    required = required_contract_components(instance)
    if not required:
        if projection is not None:
            raise ValueError("Unexpected authenticated Contract projection")
        return None
    if type(projection) is not VerifiedContractProjection:
        raise ValueError("Authenticated Contract projection is required")
    value = projection.receipt_value()
    if tuple(record["component"] for record in value["componentDigests"]) != required:
        raise ValueError("Contract projection does not contain the exact required components")
    if value["contractVersion"] != receipt["productVersion"]:
        raise ValueError("Contract projection and metadata receipt versions differ")
    if value["receiptSha256"] != sha256_bytes(canonical_json_bytes(receipt)):
        raise ValueError("Contract projection and metadata receipt bytes differ")
    bundles = [
        output
        for output in receipt["outputs"]
        if output["kind"] == "contract-bundle"
        and output["relativePath"] == value["bundlePath"]
    ]
    if len(bundles) != 1 or bundles[0]["sha256"] != value["bundleSha256"]:
        raise ValueError("Contract projection and metadata receipt Bundle differ")
    return value


def plan_phase(
    instance: PhaseInstanceId,
    *,
    inventory: list[dict[str, Any]],
    versions: dict[str, str],
    upstream_receipts: list[dict[str, Any]],
    toolchain_profile_digest: str,
    flags_digest: str,
    output_schema_version: int = 1,
    contract_projection: VerifiedContractProjection | None = None,
) -> dict[str, Any]:
    """Return the exact canonical inputs and build key for one registry phase."""
    if instance not in PHASE_INSTANCE_IDS:
        raise ValueError(f"Unknown product phase instance: {instance}")

    validated_versions = _validated_versions(versions)

    expected_dependencies = set(phase_instance_dependencies(instance))
    receipts = require_array(upstream_receipts, "upstream receipts")
    upstream_by_identity: dict[PhaseInstanceId, dict[str, Any]] = {}
    for value in receipts:
        receipt = validate_phase_receipt(value)
        identity = _receipt_identity(receipt)
        if identity in upstream_by_identity:
            raise ValueError(f"Duplicate upstream receipt: {identity}")
        if identity not in expected_dependencies:
            raise ValueError(f"Unexpected upstream receipt: {identity}")
        _validate_upstream_version(instance, identity, receipt, validated_versions)
        upstream_by_identity[identity] = receipt
    missing = expected_dependencies - set(upstream_by_identity)
    if missing:
        raise ValueError(f"Missing upstream receipt: {sorted(missing)[0]}")
    if (
        instance.product == "sdk"
        and instance.component in SDK_COMPATIBILITY_COMPONENTS
        and instance.phase == "package"
    ):
        compatibility_lines = {
            _runtime_compatibility_version(receipt["productVersion"])
            for identity, receipt in upstream_by_identity.items()
            if identity.product == "runtime"
        }
        if len(compatibility_lines) != 1:
            raise ValueError("Embedded Runtime receipts span incompatible release lines")
    if instance.product == "sdk" and instance.component in NATIVE_BINDINGS and instance.phase == "validation":
        package_identity = PhaseInstanceId("sdk", instance.component, "package", "desktop")
        runtime_identity = PhaseInstanceId("runtime", instance.target, "validation", instance.target)
        package_receipt = upstream_by_identity[package_identity]
        runtime_receipt = upstream_by_identity[runtime_identity]
        expected_runtime = _upstream_record(runtime_receipt)
        if expected_runtime not in package_receipt["inputs"]["upstreamArtifacts"]:
            raise ValueError("SDK validation Runtime receipt differs from its embedded package input")

    contract_identity = PhaseInstanceId("contract", "contract", "metadata", "common")
    contract_value = _contract_projection_value(
        instance,
        upstream_by_identity[contract_identity] if contract_identity in upstream_by_identity else {},
        contract_projection,
    )
    upstream_artifacts = sorted(
        (
            _upstream_record(
                receipt,
                contract_value if identity == contract_identity else None,
            )
            for identity, receipt in upstream_by_identity.items()
        ),
        key=lambda record: (
            record["product"],
            record["component"],
            record["phase"],
            record["target"],
            record["buildKey"],
        ),
    )
    inputs = validate_receipt_inputs({
        "inventory": inventory,
        "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
        "versionIdentity": _phase_version_identity(instance, validated_versions),
        "upstreamArtifacts": upstream_artifacts,
        "toolchainProfileDigest": toolchain_profile_digest,
        "flagsDigest": flags_digest,
        "outputSchemaVersion": output_schema_version,
    })
    build_key = compute_build_key(
        product=instance.product,
        component=instance.component,
        phase=instance.phase,
        target=instance.target,
        inputs=inputs,
    )
    return {
        "schemaVersion": 1,
        "product": instance.product,
        "component": instance.component,
        "phase": instance.phase,
        "target": instance.target,
        "buildKey": build_key,
        "inputs": inputs,
    }


def verify_build_key_output_consistency(receipts: list[dict[str, Any]]) -> None:
    """Reject a build key observed with more than one exact output inventory."""
    outputs_by_key: dict[str, str] = {}
    for value in require_array(receipts, "phase receipts"):
        receipt = validate_phase_receipt(value)
        outputs_digest = output_inventory_digest(receipt["outputs"])
        previous = outputs_by_key.setdefault(receipt["buildKey"], outputs_digest)
        if previous != outputs_digest:
            raise ValueError(
                f"Build key has conflicting output inventories: {receipt['buildKey']}"
            )


def attach_runtime_binary_identity(
    root: Path,
    revision: str,
    instance: PhaseInstanceId,
    plan: dict[str, Any],
    contract_projection: VerifiedContractProjection | None,
) -> dict[str, Any]:
    if required_toolchain_profile(instance) is None:
        return plan
    result = dict(plan)
    result["runtimeBinaryIdentity"] = derive_runtime_identity_from_git(
        root,
        revision,
        plan,
        contract_projection,
    )
    return result


def _remove_output(path: str) -> None:
    if path == "-":
        return
    output = Path(path)
    try:
        metadata = output.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISREG(metadata.st_mode):
        output.unlink()


def _write_output(path: str, value: Any) -> None:
    if path == "-":
        sys.stdout.buffer.write(canonical_json_bytes(value))
    else:
        write_canonical_json(Path(path), value)


def _contract_projection_from_request(
    instance: PhaseInstanceId,
    versions: dict[str, Any],
    value: Any,
) -> VerifiedContractProjection | None:
    components = required_contract_components(instance)
    if not components:
        if value is not None:
            raise ValueError("Plan request has unexpected Contract evidence")
        return None
    evidence = require_exact_keys(
        require_object(value, "plan request.contractEvidence"),
        {
            "stageRoot",
            "phaseReceipt",
            "publicKey",
            "expectedTrustDomain",
            "keyring",
            "keysDirectory",
        },
        "plan request.contractEvidence",
    )

    def path(field: str, *, optional: bool = False) -> Path | None:
        member = evidence[field]
        if optional and member is None:
            return None
        return Path(require_string(member, f"plan request.contractEvidence.{field}"))

    return verify_contract_component_projection(
        path("stageRoot"),
        path("phaseReceipt"),
        path("publicKey"),
        expected_trust_domain=require_string(
            evidence["expectedTrustDomain"],
            "plan request.contractEvidence.expectedTrustDomain",
        ),
        expected_contract_version=require_semver(
            versions["contract"],
            "plan request.versions.contract",
        ),
        required_components=components,
        keyring=path("keyring", optional=True),
        keys_directory=path("keysDirectory", optional=True),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ci.products plan")
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args(argv)
    try:
        request = require_exact_keys(
            load_canonical_json_bytes(
                read_regular_file_bytes(
                    Path(arguments.request),
                    max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True,
                ),
            ),
            {
                "schemaVersion",
                "product",
                "component",
                "phase",
                "target",
                "repositoryRoot",
                "repositoryRevision",
                "versions",
                "upstreamReceipts",
                "contractEvidence",
                "toolchainProfileDigest",
                "flagsDigest",
                "outputSchemaVersion",
            },
            "plan request",
        )
        if require_integer(request["schemaVersion"], "plan request.schemaVersion", 1) != 1:
            raise ValueError("Unsupported plan request schemaVersion")
        instance = PhaseInstanceId(
            request["product"],
            request["component"],
            request["phase"],
            request["target"],
        )
        versions = _validated_versions(request["versions"])
        repository_root = Path(require_string(request["repositoryRoot"], "plan request.repositoryRoot"))
        repository_revision = require_string(
            request["repositoryRevision"], "plan request.repositoryRevision"
        )
        contract_projection = _contract_projection_from_request(
            instance,
            versions,
            request["contractEvidence"],
        )
        result = plan_phase(
            instance,
            inventory=phase_git_inventory(
                repository_root,
                repository_revision,
                instance,
            ),
            versions=versions,
            upstream_receipts=request["upstreamReceipts"],
            toolchain_profile_digest=verified_phase_toolchain_digest(
                repository_root,
                repository_revision,
                instance,
                request["toolchainProfileDigest"],
            ),
            flags_digest=verified_phase_flags_digest(
                repository_root,
                repository_revision,
                instance,
                request["flagsDigest"],
            ),
            output_schema_version=request["outputSchemaVersion"],
            contract_projection=contract_projection,
        )
        result = attach_runtime_binary_identity(
            repository_root,
            repository_revision,
            instance,
            result,
            contract_projection,
        )
        _write_output(arguments.output, result)
    except (OSError, ValueError) as error:
        _remove_output(arguments.output)
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
