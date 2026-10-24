from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path
import re
import stat
import sys
from typing import Any

from .contract_projection import (
    VerifiedContractProjection,
    VerifiedContractExecutionProjection,
    verify_contract_execution_projection,
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
    require_sha256,
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
from .sdk_runtime_content import VerifiedNativeRuntimeProjection, verify_native_runtime_projection
from .runtime_adapter_content import VerifiedAdapterRuntimeProjection
from .sdk_validation import VerifiedSdkValidationProjection, sdk_validation_provider


_RUNTIME_BINARY_FLAGS_PATH = "codex-agent-runtime-desktop/native/c-api/binary-flags.json"
_RUNTIME_TOOLCHAIN_PROFILE_ROOT = "gradle/release/toolchains/runtime"
_GIT_OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
NOT_APPLICABLE_TOOLCHAIN_DIGEST = sha256_bytes(canonical_json_bytes({
    "authority": "toolchain-profile",
    "schemaVersion": 1,
    "state": "not-applicable",
}))
NOT_APPLICABLE_FLAGS_DIGEST = sha256_bytes(canonical_json_bytes({
    "authority": "flags",
    "schemaVersion": 1,
    "state": "not-applicable",
}))
_VERIFIED_RUNTIME_VALIDATION_PROJECTION = object()


class VerifiedRuntimeValidationProjection:
    """Planner capability for content-derived Runtime validation identity."""

    __slots__ = ("_canonical", "_component", "_targets", "_token")

    def __init__(
        self,
        component: str,
        targets: tuple[str, ...],
        sha256: str,
        token: object,
    ) -> None:
        if token is not _VERIFIED_RUNTIME_VALIDATION_PROJECTION:
            raise ValueError("Runtime validation projection is not authenticated")
        if not targets or targets != tuple(sorted(set(targets))):
            raise ValueError("Runtime validation projection targets must be sorted and unique")
        self._component = component
        self._targets = targets
        self._canonical = canonical_json_bytes({
            "schemaVersion": 1,
            "kind": "runtime-validation-content",
            "sha256": require_sha256(sha256, "Runtime validation projection SHA-256"),
        })
        self._token = token

    @property
    def component(self) -> str:
        return self._component

    @property
    def targets(self) -> tuple[str, ...]:
        return self._targets

    def receipt_value(self) -> dict[str, Any]:
        if self._token is not _VERIFIED_RUNTIME_VALIDATION_PROJECTION:
            raise ValueError("Runtime validation projection is not authenticated")
        return load_canonical_json_bytes(self._canonical)


def _runtime_compatibility_version(release_version: str) -> str:
    major, minor, _ = release_version.split("-", 1)[0].split(".")
    return f"{major}.{minor}.0"


def verified_phase_flags_digest(
    root: Path | None,
    revision: str | None,
    instance: PhaseInstanceId,
    supplied_digest: str,
) -> str:
    if (
        instance.product == "runtime"
        and instance.component in NATIVE_TARGETS
        and instance.phase == "binary"
    ):
        if type(revision) is not str or _GIT_OBJECT_ID.fullmatch(revision) is None:
            raise ValueError("Repository revision must be an exact lowercase Git object ID")
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
    if supplied_digest != NOT_APPLICABLE_FLAGS_DIGEST:
        raise ValueError("Plan request flagsDigest must use the not-applicable authority")
    return NOT_APPLICABLE_FLAGS_DIGEST


def verified_phase_toolchain_digest(
    root: Path | None,
    revision: str | None,
    instance: PhaseInstanceId,
    supplied_digest: str,
) -> str:
    profile_id = required_toolchain_profile(instance)
    if profile_id is None:
        if supplied_digest != NOT_APPLICABLE_TOOLCHAIN_DIGEST:
            raise ValueError("Plan request toolchainProfileDigest must use the not-applicable authority")
        return NOT_APPLICABLE_TOOLCHAIN_DIGEST
    if type(revision) is not str or _GIT_OBJECT_ID.fullmatch(revision) is None:
        raise ValueError("Repository revision must be an exact lowercase Git object ID")
    if profile_id == "sdk-csharp":
        from .sdk_dotnet_toolchain import load_sdk_dotnet_profile_bytes
        profile = load_sdk_dotnet_profile_bytes(git_regular_blob_bytes(
            root, revision, "gradle/release/toolchains/sdk/csharp.json", max_bytes=65_536,
        ))
    else:
        profile = load_toolchain_profile_bytes(
            git_regular_blob_bytes(root, revision,
                f"{_RUNTIME_TOOLCHAIN_PROFILE_ROOT}/{profile_id}.json", max_bytes=65_536),
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
            (consumer.phase == "binary" and consumer.component == "csharp")
            or
            consumer.phase == "package" and consumer.component in SDK_COMPATIBILITY_COMPONENTS
            or consumer.phase == "validation" and consumer.component in (*NATIVE_BINDINGS, "javascript")
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
    semantic_projection: dict[str, Any] | None = None,
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
    if semantic_projection is not None:
        record["semanticProjection"] = semantic_projection
    return record


def runtime_validation_dependencies(
    instance: PhaseInstanceId,
) -> tuple[PhaseInstanceId, ...]:
    """Return only validation edges whose raw execution identity is projected."""
    return tuple(
        identity for identity in sorted(phase_instance_dependencies(instance))
        if (
            instance.product == "runtime"
            and instance.phase == "metadata"
            and identity.product == "runtime"
            and identity.phase == "validation"
            and identity.target != "node-js-binding"
        )
    )


def javascript_validation_dependencies(instance: PhaseInstanceId) -> tuple[PhaseInstanceId, ...]:
    return ((PhaseInstanceId("sdk", "javascript", "validation", "node"),)
            if instance == PhaseInstanceId("sdk", "javascript", "metadata", "node") else ())


def native_runtime_validation_dependencies(instance: PhaseInstanceId) -> tuple[PhaseInstanceId, ...]:
    return tuple(identity for identity in sorted(phase_instance_dependencies(instance)) if (
        instance.product == "sdk" and instance.component in NATIVE_BINDINGS
        and instance.phase in {"package", "validation"}
        and identity.product == "runtime" and identity.phase == "validation"
        and identity.component == identity.target and identity.target in NATIVE_TARGETS
    ))


def sdk_validation_dependencies(instance: PhaseInstanceId) -> tuple[PhaseInstanceId, ...]:
    return tuple(identity for identity in sorted(phase_instance_dependencies(instance)) if (
        instance.product == "sdk" and instance.component in NATIVE_BINDINGS and instance.phase == "metadata"
        and identity.product == "sdk" and identity.component == instance.component
        and identity.phase == "validation" and identity.target in NATIVE_TARGETS
    ))


def verify_runtime_validation_projection(
    instance: PhaseInstanceId,
    report_files: Iterable[Path],
    validation_receipts: Iterable[dict[str, Any]],
) -> VerifiedRuntimeValidationProjection:
    """Authenticate raw reports against receipts before minting a planner capability."""
    semantic_dependencies = runtime_validation_dependencies(instance)
    if not semantic_dependencies:
        raise ValueError("Runtime validation projection is not applicable to this phase")
    receipts = require_array(validation_receipts, "Runtime validation receipts")
    expected = set(semantic_dependencies)
    actual = {
        _receipt_identity(validate_phase_receipt(value))
        for value in receipts
    }
    if len(actual) != len(receipts) or actual != expected:
        raise ValueError("Runtime validation receipts do not match the metadata edge")
    from .runtime_evidence import derive_authenticated_runtime_validation_projection

    projection = derive_authenticated_runtime_validation_projection(
        instance.component,
        report_files,
        receipts,
    )
    return VerifiedRuntimeValidationProjection(
        instance.component,
        tuple(identity.target for identity in semantic_dependencies),
        sha256_bytes(canonical_json_bytes(projection)),
        _VERIFIED_RUNTIME_VALIDATION_PROJECTION,
    )


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
    from .registry import requires_contract_coverage
    value = projection.receipt_value(include_coverage=requires_contract_coverage(instance))
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
    runtime_validation_projection: VerifiedRuntimeValidationProjection | None = None,
    native_runtime_projections: tuple[VerifiedNativeRuntimeProjection, ...] | None = None,
    contract_execution_projection: VerifiedContractExecutionProjection | None = None,
    sdk_validation_projections: tuple[VerifiedSdkValidationProjection, ...] | None = None,
    sdk_javascript_validation_projection=None,
    sdk_javascript_legacy_metadata_receipt=None,
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
        package_receipt = upstream_by_identity[package_identity]
        for target in {instance.target, "macos-arm64"}:
            runtime_identity = PhaseInstanceId("runtime", target, "validation", target)
            expected_runtime = _upstream_record(upstream_by_identity[runtime_identity])
            package_runtime = [{key: value for key, value in record.items() if key != "semanticProjection"}
                               for record in package_receipt["inputs"]["upstreamArtifacts"]]
            if expected_runtime not in package_runtime:
                raise ValueError("SDK validation Runtime receipt differs from its embedded package input")

    contract_identity = PhaseInstanceId("contract", "contract", "metadata", "common")
    contract_value = _contract_projection_value(
        instance,
        upstream_by_identity[contract_identity] if contract_identity in upstream_by_identity else {},
        contract_projection,
    )
    semantic_dependencies = runtime_validation_dependencies(instance)
    native_dependencies = native_runtime_validation_dependencies(instance)
    native_values = {}
    sdk_dependencies = sdk_validation_dependencies(instance)
    sdk_values = {}
    if sdk_dependencies:
        if not isinstance(sdk_validation_projections, (tuple, list)) or len(sdk_validation_projections) != len(sdk_dependencies):
            raise ValueError("Authenticated SDK validation projections are required for all five metadata hosts")
        package = upstream_by_identity[PhaseInstanceId("sdk", instance.component, "package", "desktop")]
        for identity, proof in zip(sdk_dependencies, sdk_validation_projections, strict=True):
            if type(proof) is not VerifiedSdkValidationProjection:
                raise ValueError("SDK validation projection is not authenticated")
            sdk_values[identity] = proof.receipt_value(upstream_by_identity[identity], package)
    elif sdk_validation_projections is not None:
        raise ValueError("Unexpected authenticated SDK validation projections")
    javascript_upstream = None
    javascript_identity = PhaseInstanceId("sdk", "javascript", "validation", "node")
    if instance == PhaseInstanceId("sdk", "javascript", "metadata", "node"):
        from .sdk_javascript_validation_phase import VerifiedJavaScriptValidationProjection
        if type(sdk_javascript_validation_projection) is not VerifiedJavaScriptValidationProjection:
            raise ValueError("Authenticated JavaScript validation projection is required for metadata")
        javascript_upstream = sdk_javascript_validation_projection.upstream_record(
            upstream_by_identity[javascript_identity])
        if sdk_javascript_legacy_metadata_receipt is not None:
            from .sdk_javascript_metadata import javascript_metadata_uses_raw_validation
            legacy = validate_phase_receipt(sdk_javascript_legacy_metadata_receipt)
            if (not javascript_metadata_uses_raw_validation(legacy)
                    or legacy["inputs"]["inventory"] != inventory):
                raise ValueError("JavaScript legacy metadata requires its exact reviewed original recipe")
            javascript_upstream = _upstream_record(upstream_by_identity[javascript_identity])
    elif sdk_javascript_validation_projection is not None or sdk_javascript_legacy_metadata_receipt is not None:
        raise ValueError("Unexpected JavaScript validation projection or legacy metadata")
    if native_dependencies:
        if not isinstance(native_runtime_projections, (tuple, list)) or len(native_runtime_projections) != len(native_dependencies):
            raise ValueError("Authenticated native Runtime projections are required for every SDK dependency")
        for identity, projection in zip(native_dependencies, native_runtime_projections, strict=True):
            if type(projection) is not VerifiedNativeRuntimeProjection:
                raise ValueError("Native Runtime projection is not authenticated")
            native_values[identity] = projection.receipt_value(upstream_by_identity[identity], contract_projection)
    elif native_runtime_projections is not None:
        raise ValueError("Unexpected authenticated native Runtime projections")
    semantic_value = None
    if semantic_dependencies:
        if type(runtime_validation_projection) is not VerifiedRuntimeValidationProjection:
            raise ValueError("Authenticated Runtime validation projection is required")
        if (
            not semantic_dependencies
            or runtime_validation_projection.component != instance.component
            or runtime_validation_projection.targets
            != tuple(identity.target for identity in semantic_dependencies)
        ):
            raise ValueError("Runtime validation projection does not match the metadata edge")
        semantic_value = runtime_validation_projection.receipt_value()
    elif runtime_validation_projection is not None:
        raise ValueError("Unexpected authenticated Runtime validation projection")
    execution_identity = PhaseInstanceId("contract", "contract", "binary", "common")
    execution_value = None
    if instance == PhaseInstanceId("contract", "contract", "package", "common"):
        if type(contract_execution_projection) is not VerifiedContractExecutionProjection:
            raise ValueError("Authenticated Contract execution projection is required")
        execution_value = contract_execution_projection.receipt_value()
        if execution_value["receiptSha256"] != sha256_bytes(canonical_json_bytes(upstream_by_identity[execution_identity])):
            raise ValueError("Contract execution projection and binary receipt differ")
    elif contract_execution_projection is not None:
        raise ValueError("Unexpected authenticated Contract execution projection")
    upstream_artifacts = sorted(
        (
            javascript_upstream if identity == javascript_identity and javascript_upstream is not None else _upstream_record(
                receipt,
                contract_value if identity == contract_identity else None,
                execution_value if identity == execution_identity else
                native_values.get(identity) if identity in native_values else
                sdk_values.get(identity) if identity in sdk_values else
                semantic_value if identity in semantic_dependencies else None,
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
    if sdk_javascript_legacy_metadata_receipt is not None and (
            sdk_javascript_legacy_metadata_receipt["inputs"] != inputs
            or sdk_javascript_legacy_metadata_receipt["buildKey"] != build_key):
        raise ValueError("JavaScript legacy metadata differs from its exact original inputs/key")
    return {
        "schemaVersion": 1,
        "product": instance.product,
        "component": instance.component,
        "phase": instance.phase,
        "target": instance.target,
        "buildKey": build_key,
        "inputs": inputs,
    }


def verify_build_key_output_consistency(
    receipts: list[dict[str, Any]], *, contract_execution_projection=None, native_runtime_projection=None,
    adapter_runtime_projection=None, sdk_validation_projection=None,
) -> None:
    """Reject conflicting content; differing raw execution requires verified proof."""
    receipts_by_key: dict[str, dict[str, Any]] = {}
    for value in require_array(receipts, "phase receipts"):
        receipt = validate_phase_receipt(value)
        previous = receipts_by_key.setdefault(receipt["buildKey"], receipt)
        if previous["outputs"] != receipt["outputs"]:
            if sdk_validation_projection is not None and all(
                member["product"] == "sdk" and member["phase"] == "validation"
                and member["component"] in NATIVE_BINDINGS and member["target"] in NATIVE_TARGETS
                for member in (previous, receipt)
            ):
                content = []
                for member in (previous, receipt):
                    proof = sdk_validation_projection(member)
                    if type(proof) is not VerifiedSdkValidationProjection:
                        raise ValueError("Verified SDK validation projection is required for consistency")
                    content.append(proof.output_inventory(sha256_bytes(canonical_json_bytes(member)),
                                                          member["outputs"], identity=member))
                if content[0] == content[1]:
                    continue
            if adapter_runtime_projection is not None and all(
                member["product"] == "runtime" and member["phase"] == "validation"
                and member["component"] in {"jvm", "node-js", "node-wasm"} and member["target"] in NATIVE_TARGETS
                for member in (previous, receipt)
            ):
                content = []
                for member in (previous, receipt):
                    proof = adapter_runtime_projection(member)
                    if type(proof) is not VerifiedAdapterRuntimeProjection:
                        raise ValueError("Verified adapter Runtime projection is required for consistency")
                    content.append(proof.output_inventory(sha256_bytes(canonical_json_bytes(member)),
                                                          member["outputs"], identity=member))
                if content[0] == content[1]:
                    continue
            if native_runtime_projection is not None and all(
                member["product"] == "runtime" and member["phase"] == "validation"
                and member["component"] == member["target"] and member["target"] in NATIVE_TARGETS
                for member in (previous, receipt)
            ):
                content = []
                for member in (previous, receipt):
                    proof = native_runtime_projection(member)
                    if type(proof) is not VerifiedNativeRuntimeProjection:
                        raise ValueError("Verified native Runtime projection is required for consistency")
                    content.append(proof.output_inventory(sha256_bytes(canonical_json_bytes(member)), member["outputs"]))
                if content[0] == content[1]:
                    continue
            if contract_execution_projection is not None and all(
                _receipt_identity(member) == PhaseInstanceId("contract", "contract", "binary", "common")
                for member in (previous, receipt)
            ):
                content = []
                for member in (previous, receipt):
                    proof = contract_execution_projection(member)
                    if type(proof) is not VerifiedContractExecutionProjection:
                        raise ValueError("Verified Contract execution projection is required for consistency")
                    content.append(proof.output_inventory(sha256_bytes(canonical_json_bytes(member)), member["outputs"]))
                if content[0] == content[1]:
                    continue
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
    if instance.product != "runtime" or required_toolchain_profile(instance) is None:
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
    return _contract_projection_from_request_components(versions, value, components)


def _contract_projection_from_request_components(
    versions: dict[str, Any],
    value: Any,
    components: Iterable[str],
) -> VerifiedContractProjection | None:
    components = tuple(components)
    if not components:
        if value is not None:
            raise ValueError("Plan request has unexpected Contract evidence")
        return None
    evidence = require_exact_keys(
        require_object(value, "plan request.contractEvidence"),
        {
            "stageRoot",
            "phaseReceipt",
            "attestation",
            "attestationSignature",
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
        path("attestation"),
        path("attestationSignature"),
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


def _runtime_validation_projection_from_request(
    instance: PhaseInstanceId,
    upstream_receipts: Any,
    value: Any,
) -> VerifiedRuntimeValidationProjection | None:
    dependencies = runtime_validation_dependencies(instance)
    if not dependencies:
        if value is not None:
            raise ValueError("Plan request has unexpected Runtime validation evidence")
        return None
    evidence = require_exact_keys(
        require_object(value, "plan request.runtimeValidationEvidence"),
        {"reports"},
        "plan request.runtimeValidationEvidence",
    )
    reports = [
        Path(require_string(path, f"plan request.runtimeValidationEvidence.reports[{index}]"))
        for index, path in enumerate(require_array(
            evidence["reports"], "plan request.runtimeValidationEvidence.reports",
        ))
    ]
    semantic_identities = set(dependencies)
    semantic_receipts = [
        value
        for value in require_array(upstream_receipts, "plan request.upstreamReceipts")
        if _receipt_identity(validate_phase_receipt(value)) in semantic_identities
    ]
    return verify_runtime_validation_projection(instance, reports, semantic_receipts)


NATIVE_RUNTIME_EVIDENCE_KEYS = {
    "target", "stageRoot", "phaseReceipts", "payload", "attestation",
    "attestationSignature", "publicKey", "keyring", "keysDirectory",
}


def _native_runtime_projection_from_record(value, contract_projection, contract_payload, expected_trust_domain):
    record = require_exact_keys(value, NATIVE_RUNTIME_EVIDENCE_KEYS, "native Runtime evidence")
    def path(name: str, optional: bool = False) -> Path | None:
        return None if optional and record[name] is None else Path(require_string(record[name], f"native Runtime {name}"))
    phases = require_exact_keys(record["phaseReceipts"], {"binary", "package", "validation", "metadata"},
                                "native Runtime phase receipts")
    return verify_native_runtime_projection(
        target=require_string(record["target"], "native Runtime target"), runtime_stage_root=path("stageRoot"),
        phase_receipts={phase: Path(require_string(source, f"native Runtime {phase} receipt")) for phase, source in phases.items()},
        variant_payload=path("payload"), attestation=path("attestation"), signature=path("attestationSignature"),
        public_key=path("publicKey"), contract_projection=contract_projection, contract_payload=contract_payload,
        required_trust_domain=expected_trust_domain, keyring=path("keyring", True), keys_directory=path("keysDirectory", True),
    )


def _native_runtime_projections_from_request(
    instance: PhaseInstanceId, upstream_receipts: Any, value: Any,
    contract_projection: VerifiedContractProjection | None, contract_payload: Path | None,
    expected_trust_domain: str | None,
) -> tuple[VerifiedNativeRuntimeProjection, ...] | None:
    dependencies = native_runtime_validation_dependencies(instance)
    if not dependencies:
        if value not in (None, []):
            raise ValueError("Unexpected native Runtime evidence")
        return None
    records = require_array(value, "native Runtime evidence")
    if [record.get("target") if type(record) is dict else None for record in records] != [item.target for item in dependencies]:
        raise ValueError("Native Runtime evidence must cover the exact sorted SDK dependency targets")
    receipts = {_receipt_identity(validate_phase_receipt(item)): item for item in upstream_receipts}
    projections = []
    for identity, member in zip(dependencies, records, strict=True):
        projection = _native_runtime_projection_from_record(member, contract_projection, contract_payload, expected_trust_domain)
        if identity not in receipts:
            raise ValueError("Native Runtime evidence lacks its exact upstream receipt")
        projection.receipt_value(receipts[identity], contract_projection)
        projections.append(projection)
    return tuple(projections)


def _contract_execution_projection_from_request(
    instance: PhaseInstanceId, receipts: Any, value: Any,
) -> VerifiedContractExecutionProjection | None:
    if instance != PhaseInstanceId("contract", "contract", "package", "common"):
        if value is not None:
            raise ValueError("Unexpected Contract execution evidence")
        return None
    evidence = require_exact_keys(value, {"stageRoot", "receiptSha256"}, "Contract execution evidence")
    candidates = [receipt for receipt in require_array(receipts, "upstream receipts")
                  if _receipt_identity(validate_phase_receipt(receipt)) ==
                  PhaseInstanceId("contract", "contract", "binary", "common")]
    if len(candidates) != 1:
        raise ValueError("Contract execution evidence requires exactly one binary receipt")
    return verify_contract_execution_projection(
        Path(require_string(evidence["stageRoot"], "Contract execution stage root")),
        canonical_json_bytes(candidates[0]),
        expected_receipt_sha256=evidence["receiptSha256"],
    )


def _sdk_validation_projections_from_request(instance, receipts, value, repository, revision):
    dependencies = sdk_validation_dependencies(instance)
    if not dependencies:
        if value is not None:
            raise ValueError("Unexpected SDK validation evidence")
        return None
    evidence = require_exact_keys(value, {"artifactRoot", "records", "tooling"}, "SDK validation evidence request")
    root = Path(require_string(evidence["artifactRoot"], "SDK evidence artifact root"))
    if not root.is_absolute():
        raise ValueError("SDK evidence artifact root must be absolute")
    provider = sdk_validation_provider(root, evidence["records"], repository=repository,
                                       policy_revision=revision, tooling=evidence["tooling"])
    selected = {_receipt_identity(validate_phase_receipt(receipt)): receipt for receipt in receipts}
    if not set(dependencies) <= selected.keys():
        raise ValueError("SDK metadata lacks one or more original host receipts")
    required = {sha256_bytes(canonical_json_bytes(selected[identity])) for identity in dependencies}
    if {record["receiptSha256"] for record in evidence["records"]} != required:
        raise ValueError("SDK metadata evidence must name exactly its five original validation receipts")
    if provider is None:
        raise ValueError("SDK metadata requires all five authenticated validation originals")
    return tuple(provider({**selected[identity], "receiptSha256": sha256_bytes(canonical_json_bytes(selected[identity]))})
                 for identity in dependencies)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ci.products plan")
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args(argv)
    try:
        request_value = load_canonical_json_bytes(
            read_regular_file_bytes(
                Path(arguments.request),
                max_bytes=16 * 1024 * 1024,
                reject_symlink_parents=True,
            ),
        )
        if type(request_value) is dict and "requestType" in request_value:
            from .reuse import plan_reuse_wave

            result = plan_reuse_wave(request_value)
            _write_output(arguments.output, result)
            return 0
        request = require_exact_keys(
            request_value,
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
                "runtimeValidationEvidence",
                "toolchainProfileDigest",
                "flagsDigest",
                "outputSchemaVersion",
            } | ({"contractExecutionEvidence"} if type(request_value) is dict and "contractExecutionEvidence" in request_value else set())
            | ({"nativeRuntimeEvidence"} if type(request_value) is dict and "nativeRuntimeEvidence" in request_value else set())
            | ({"sdkValidationEvidence"} if type(request_value) is dict and "sdkValidationEvidence" in request_value else set()),
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
        runtime_validation_projection = _runtime_validation_projection_from_request(
            instance,
            request["upstreamReceipts"],
            request["runtimeValidationEvidence"],
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
            runtime_validation_projection=runtime_validation_projection,
            native_runtime_projections=_native_runtime_projections_from_request(
                instance, request["upstreamReceipts"], request.get("nativeRuntimeEvidence"), contract_projection,
                Path(request["contractEvidence"]["stageRoot"]) / contract_projection.receipt_value()["bundlePath"]
                if contract_projection is not None else None,
                request["contractEvidence"]["expectedTrustDomain"] if contract_projection is not None else None,
            ),
            contract_execution_projection=_contract_execution_projection_from_request(
                instance, request["upstreamReceipts"], request.get("contractExecutionEvidence"),
            ),
            sdk_validation_projections=_sdk_validation_projections_from_request(
                instance, request["upstreamReceipts"], request.get("sdkValidationEvidence"), repository_root, repository_revision),
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
