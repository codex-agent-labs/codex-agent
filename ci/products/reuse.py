from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any

from .aggregate import verified_index_content, verify_immutable_product_indexes
from .contract_projection import VerifiedContractProjection, VerifiedContractExecutionProjection, verify_contract_component_projection
from .inventory import (
    load_canonical_json_bytes,
    require_array,
    require_exact_keys,
    require_integer,
    require_relative_path,
    require_sha256,
    require_string,
    sha256_bytes,
)
from .index import (
    _verify_index_receipt,
    verify_contract_index_object,
    SignedProductIndex,
    stable_index_identity,
    verify_release_product_index,
    verify_signed_product_index,
)
from .plan import (
    verify_contract_execution_projection,
    VerifiedRuntimeValidationProjection,
    _validated_versions,
    attach_runtime_binary_identity,
    plan_phase,
    runtime_validation_dependencies,
    verified_phase_flags_digest,
    verified_phase_toolchain_digest,
    verify_build_key_output_consistency,
    verify_runtime_validation_projection,
    native_runtime_validation_dependencies, _native_runtime_projections_from_request,
    NATIVE_RUNTIME_EVIDENCE_KEYS, VerifiedNativeRuntimeProjection,
)
from .receipt import output_inventory_digest, validate_phase_receipt
from .receipt import build_key_payload
from .registry import (
    NATIVE_TARGETS,
    PHASE_INSTANCE_IDS,
    PhaseInstanceId,
    phase_instance_dependencies,
    required_contract_components,
    required_toolchain_profile,
)
from .restore import (
    CacheObjectError,
    object_relative_path,
    restore_local_object,
    restore_object,
    verify_object,
)
from .selection import phase_git_inventory


SOURCES = ("stable", "promoted-main", "same-pr", "local")
MATRIX_PRODUCTS = ("contract", "runtime", "sdk")
_ENVELOPE_KEYS = {"receipt", "receiptBytes", "receiptSha256", "objectSha256"}
_PHASE_INPUT_KEYS = {
    "inventory",
    "versions",
    "toolchain_profile_digest",
    "flags_digest",
}
_GIT_OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_IDENTITY_KEYS = {"product", "component", "phase", "target"}
_AUTHORITY_KEYS = _IDENTITY_KEYS | {
    "toolchainProfileDigest",
    "flagsDigest",
    "outputSchemaVersion",
}
_AVAILABLE_OBJECT_KEYS = _IDENTITY_KEYS | {
    "buildKey",
    "receiptSha256",
    "objectSha256",
    "objectPath",
}
_REMOTE_CATALOG_KEYS = {
    "manifest",
    "signature",
    "publicKey",
    "keyring",
    "keysDirectory",
    "contractAttestation",
    "contractAttestationSignature",
    "contractPublicKey",
    "objects",
}
_CONTRACT_EVIDENCE_KEYS = {
    "attestation",
    "attestationSignature",
    "publicKey",
    "expectedTrustDomain",
    "keyring",
    "keysDirectory",
}
_RUNTIME_VALIDATION_EVIDENCE_KEYS = _IDENTITY_KEYS | {"reports"}


class ReuseLookupError(ValueError):
    """A matching remote or local reuse candidate failed verification."""


@dataclass(frozen=True, slots=True)
class RemoteCatalog:
    manifest: Path
    signature: Path
    objects: Mapping[str, Path | None]
    public_key: Path | None = None
    keyring: Path | None = None
    keys_directory: Path | None = None
    contract_attestation: Path | None = None
    contract_attestation_signature: Path | None = None
    contract_public_key: Path | None = None


@dataclass(frozen=True, slots=True)
class LocalCandidate:
    receipt_sha256: str
    destination: Path


@dataclass(frozen=True, slots=True)
class LocalCatalog:
    cache_root: Path
    candidates: Mapping[str, tuple[LocalCandidate, ...]]


@dataclass(frozen=True, slots=True)
class _RemoteCandidate:
    entry: dict[str, Any]
    object_path: Path | None
    index_sha256: str
    catalog: RemoteCatalog


@dataclass(frozen=True, slots=True)
class _LookupResult:
    envelope: dict[str, Any] | None
    reason: str | None
    transport_source: dict[str, Any] | None = None


def _identity(receipt: dict[str, Any]) -> PhaseInstanceId:
    return PhaseInstanceId(
        receipt["product"],
        receipt["component"],
        receipt["phase"],
        receipt["target"],
    )


def _runtime_compatibility_version(product_version: str) -> str:
    major, minor, _ = product_version.split("-", 1)[0].split(".")
    return f"{major}.{minor}.0"


def _validate_envelope(
    value: Any,
    *,
    expected_plan: dict[str, Any] | None = None,
) -> tuple[PhaseInstanceId, dict[str, Any]]:
    envelope = require_exact_keys(value, _ENVELOPE_KEYS, "receipt envelope")
    receipt_bytes = envelope["receiptBytes"]
    if type(receipt_bytes) is not bytes:
        raise ValueError("receipt envelope.receiptBytes must be bytes")
    receipt = validate_phase_receipt(envelope["receipt"])
    if load_canonical_json_bytes(receipt_bytes) != receipt:
        raise ValueError("receipt envelope bytes do not match its receipt")
    if require_sha256(envelope["receiptSha256"], "receipt envelope.receiptSha256") != sha256_bytes(
        receipt_bytes
    ):
        raise ValueError("receipt envelope SHA-256 does not match its receipt bytes")
    require_sha256(envelope["objectSha256"], "receipt envelope.objectSha256")

    instance = _identity(receipt)
    if instance not in PHASE_INSTANCE_IDS:
        raise ValueError(f"Receipt envelope has an unknown phase instance: {instance}")
    if receipt["product"] == "runtime" and receipt["component"] != "runtime-aggregate":
        compatibility = _runtime_compatibility_version(receipt["productVersion"])
        if receipt["inputs"]["versionIdentity"] != compatibility:
            raise ValueError("Runtime receipt productVersion has an incompatible compatibility identity")
    if expected_plan is not None:
        planned = PhaseInstanceId(
            expected_plan["product"],
            expected_plan["component"],
            expected_plan["phase"],
            expected_plan["target"],
        )
        if instance != planned:
            raise ValueError("Receipt envelope identity does not match the planned phase")
        if (
            receipt["buildKey"] != expected_plan["buildKey"]
            or build_key_payload(
                product=receipt["product"],
                component=receipt["component"],
                phase=receipt["phase"],
                target=receipt["target"],
                inputs=receipt["inputs"],
            ) != build_key_payload(
                product=expected_plan["product"],
                component=expected_plan["component"],
                phase=expected_plan["phase"],
                target=expected_plan["target"],
                inputs=expected_plan["inputs"],
            )
        ):
            raise ValueError("Receipt envelope build-key inputs do not match the planned phase")
    return instance, envelope


class LookupSession:
    """A run-scoped, preverified catalog and cache lookup session."""

    def __init__(
        self,
        *,
        repository: str,
        pull_request: int | None,
        restore_root: Path | None = None,
        stable: Iterable[RemoteCatalog] = (),
        promoted_main: RemoteCatalog | None = None,
        same_pr: RemoteCatalog | None = None,
        local: LocalCatalog | None = None,
    ) -> None:
        self.repository = require_relative_path(repository, "lookup repository")
        if self.repository.count("/") != 1:
            raise ValueError("lookup repository must be an owner/repository pair")
        self.pull_request = (
            None if pull_request is None else require_integer(pull_request, "lookup pull request", 1)
        )
        self._restore_root = None if restore_root is None else Path(restore_root)
        self._contract_stages: dict[tuple[str, str], Path] = {}
        self._execution_projections: dict[tuple[str, str, str], VerifiedContractExecutionProjection] = {}
        self._remote: dict[str, dict[str, list[_RemoteCandidate]]] = {
            source: {} for source in SOURCES[:-1]
        }
        loaded_indexes: list[dict[str, Any]] = []
        stable_indexes = []
        for catalog in stable:
            index = self._load_catalog("stable", catalog)
            for prior in stable_indexes:
                verify_immutable_product_indexes(
                    prior, index, contract_execution_projection=self._catalog_execution_projection,
                )
            stable_indexes.append(index)
            loaded_indexes.append(index)
        if promoted_main is not None:
            loaded_indexes.append(self._load_catalog("promoted-main", promoted_main))
        if same_pr is not None:
            loaded_indexes.append(self._load_catalog("same-pr", same_pr))
        self._reject_conflicting_catalog_outputs(loaded_indexes)
        self._local = self._snapshot_local(local)

    def _load_catalog(self, source: str, catalog: RemoteCatalog) -> dict[str, Any]:
        if not isinstance(catalog, RemoteCatalog):
            raise ValueError(f"{source} catalog must be a RemoteCatalog")
        manifest = Path(catalog.manifest)
        signed = SignedProductIndex(manifest, Path(catalog.signature))
        if source in {"stable", "promoted-main"}:
            if catalog.public_key is not None or catalog.keyring is None or catalog.keys_directory is None:
                raise ValueError(
                    f"{source} catalog requires release trust through tracked release key inputs",
                )
            index, contents = verify_release_product_index(
                signed,
                keyring_path=Path(catalog.keyring),
                keys_directory=Path(catalog.keys_directory),
            )
        else:
            if catalog.public_key is None or catalog.keyring is not None or catalog.keys_directory is not None:
                raise ValueError("same-pr catalog requires only an explicit development public key")
            index, contents = verify_signed_product_index(signed, Path(catalog.public_key))
        if index["repository"] != self.repository:
            raise ValueError(f"{source} product index repository mismatch")
        context = index["context"]
        expected_kind = {
            "stable": "stable",
            "promoted-main": "promoted-main",
            "same-pr": "pull-request",
        }[source]
        if context["kind"] != expected_kind:
            raise ValueError(f"{source} product index context mismatch")
        if source in {"stable", "promoted-main"} and index["trustDomain"] != "release":
            raise ValueError(f"{source} product index must have release trust")
        if source == "same-pr" and (
            index["trustDomain"] != "development"
            or self.pull_request is None
            or context["pullRequest"] != self.pull_request
        ):
            raise ValueError("same-pr product index must have development trust for the current PR")
        if source == "stable":
            stable_index_identity(index)

        if not isinstance(catalog.objects, Mapping):
            raise ValueError(f"{source} catalog objects must be a mapping")
        entries = {entry["buildKey"]: entry for entry in index["entries"]}
        if not set(catalog.objects).issubset(entries):
            raise ValueError(f"{source} catalog contains an object without an index entry")
        for build_key, entry in entries.items():
            supplied = catalog.objects.get(build_key)
            object_path = None if supplied is None else Path(supplied)
            self._remote[source].setdefault(build_key, []).append(
                _RemoteCandidate(entry, object_path, sha256_bytes(contents), catalog)
            )
        return index

    def _catalog_execution_projection(self, entry: dict[str, Any]) -> VerifiedContractExecutionProjection:
        key = (entry["buildKey"], entry["receiptSha256"], entry["outputInventoryDigest"])
        if key in self._execution_projections:
            return self._execution_projections[key]
        for catalog in self._remote.values():
            for candidate in catalog.get(entry["buildKey"], ()):
                if candidate.entry != entry or candidate.object_path is None:
                    continue
                try:
                    proof = verify_contract_index_object(entry, candidate.object_path)
                except FileNotFoundError:
                    continue
                self._execution_projections[key] = proof
                return proof
        raise ValueError("Conflicting Contract execution inventories require both authenticated objects")

    def _reject_conflicting_catalog_outputs(self, indexes: list[dict[str, Any]]) -> None:
        entries_by_key: dict[str, dict[str, Any]] = {}
        for index in indexes:
            for entry in index["entries"]:
                prior = entries_by_key.setdefault(entry["buildKey"], entry)
                if prior["outputs"] != entry["outputs"]:
                    left = verified_index_content(prior, self._catalog_execution_projection)
                    right = verified_index_content(entry, self._catalog_execution_projection)
                    if left["outputs"] != right["outputs"]:
                        raise ValueError("Signed product indexes conflict for an identical build key")

    @staticmethod
    def _snapshot_local(local: LocalCatalog | None) -> LocalCatalog | None:
        if local is None:
            return None
        if not isinstance(local, LocalCatalog) or not isinstance(local.candidates, Mapping):
            raise ValueError("local catalog is invalid")
        candidates: dict[str, tuple[LocalCandidate, ...]] = {}
        for build_key, values in local.candidates.items():
            require_sha256(build_key, "local catalog build key")
            if type(values) is not tuple or any(not isinstance(value, LocalCandidate) for value in values):
                raise ValueError("local catalog candidates must be tuples of LocalCandidate")
            for value in values:
                require_sha256(value.receipt_sha256, "local candidate receipt SHA-256")
            candidates[build_key] = values
        return LocalCatalog(Path(local.cache_root), candidates)

    def _remote_lookup(self, source: str, plan: dict[str, Any]) -> _LookupResult:
        catalogs = self._remote[source]
        if not catalogs:
            return _LookupResult(None, "no-index")
        candidates = catalogs.get(plan["buildKey"])
        if not candidates:
            return _LookupResult(None, "no-entry")
        for candidate in candidates:
            path = candidate.object_path
            if path is None:
                continue
            try:
                path.lstat()
            except FileNotFoundError:
                continue
            except OSError as error:
                raise ReuseLookupError(f"{source} matching object availability check failed") from error
            try:
                verified = verify_object(
                    path,
                    build_key=plan["buildKey"],
                    receipt_sha256=candidate.entry["receiptSha256"],
                )
                envelope = {
                    "receipt": verified["receipt"],
                    "receiptBytes": verified["receiptBytes"],
                    "receiptSha256": candidate.entry["receiptSha256"],
                    "objectSha256": verified["objectSha256"],
                }
                _validate_envelope(envelope, expected_plan=plan)
                _verify_index_receipt(candidate.entry, envelope)
                identity = _identity(envelope["receipt"])
                expected_trust = "development" if source == "same-pr" else "release"
                if envelope["receipt"]["trustDomain"] != expected_trust:
                    if not (
                        source in {"stable", "promoted-main"}
                        and envelope["receipt"]["trustDomain"] == "development"
                        and identity == PhaseInstanceId("contract", "contract", "metadata", "common")
                    ):
                        raise ValueError("Restored receipt trust does not match its product index source")
                    self._verify_release_attested_contract(path, envelope, candidate.catalog)
                if identity.product == "contract" and identity.phase in {"binary", "metadata"} and self._restore_root is not None:
                    self._restore_contract_stage(path, envelope)
            except (CacheObjectError, TypeError, ValueError) as error:
                raise ReuseLookupError(f"{source} matching object or index entry is corrupt") from error
            return _LookupResult(envelope, None, {
                "kind": source,
                "indexSha256": candidate.index_sha256,
                "artifactName": candidate.entry["artifactName"],
                "artifactSha256": candidate.entry["artifactSha256"],
            })
        return _LookupResult(None, "artifact-unavailable")

    @staticmethod
    def _verify_release_attested_contract(
        archive: Path,
        envelope: dict[str, Any],
        catalog: RemoteCatalog,
    ) -> None:
        if (
            catalog.contract_attestation is None
            or catalog.contract_attestation_signature is None
            or catalog.contract_public_key is None
            or catalog.keyring is None
            or catalog.keys_directory is None
        ):
            raise ValueError("Release Contract reuse lacks its detached release attestation")
        with tempfile.TemporaryDirectory(prefix="release-contract-reuse-") as temporary:
            stage = Path(temporary).resolve() / "stage"
            restore_object(
                archive,
                stage,
                build_key=envelope["receipt"]["buildKey"],
                receipt_sha256=envelope["receiptSha256"],
                object_sha256=envelope["objectSha256"],
            )
            verify_contract_component_projection(
                stage,
                envelope["receiptBytes"],
                catalog.contract_attestation,
                catalog.contract_attestation_signature,
                catalog.contract_public_key,
                expected_trust_domain="release",
                expected_contract_version=envelope["receipt"]["productVersion"],
                required_components=("common",),
                keyring=catalog.keyring,
                keys_directory=catalog.keys_directory,
            )

    def _local_lookup(self, plan: dict[str, Any]) -> _LookupResult:
        if self._local is None:
            return _LookupResult(None, "local-missing")
        candidates = self._local.candidates.get(plan["buildKey"], ())
        if not candidates:
            return _LookupResult(None, "local-missing")
        saw_corrupt = False
        for candidate in candidates:
            result = restore_local_object(
                self._local.cache_root,
                plan["buildKey"],
                candidate.receipt_sha256,
                candidate.destination,
            )
            if result["status"] == "miss":
                if result["reason"] == "local-corrupt":
                    saw_corrupt = True
                elif result["reason"] != "local-missing":
                    raise ReuseLookupError("Local restore returned an unsupported miss")
                continue
            if result["status"] != "hit" or result["reason"] != "local-hit":
                raise ReuseLookupError("Local restore returned an unsupported result")
            envelope = {
                "receipt": result["receipt"],
                "receiptBytes": result["receiptBytes"],
                "receiptSha256": candidate.receipt_sha256,
                "objectSha256": result["objectSha256"],
            }
            try:
                _validate_envelope(envelope, expected_plan=plan)
            except (TypeError, ValueError) as error:
                raise ReuseLookupError("Local restored object is incompatible with the plan") from error
            identity = _identity(envelope["receipt"])
            if identity.product == "contract" and identity.phase in {"binary", "metadata"}:
                self._contract_stages[(plan["buildKey"], candidate.receipt_sha256)] = candidate.destination
            return _LookupResult(envelope, None, {
                "kind": "local",
                "cacheRelativePath": object_relative_path(
                    plan["buildKey"],
                    candidate.receipt_sha256,
                ),
            })
        return _LookupResult(None, "local-corrupt" if saw_corrupt else "local-missing")

    def lookup(self, source: str, plan: dict[str, Any]) -> _LookupResult:
        if source == "local":
            return self._local_lookup(plan)
        if source not in self._remote:
            raise ValueError(f"Unsupported lookup source: {source}")
        return self._remote_lookup(source, plan)

    def _restore_contract_stage(self, archive: Path, envelope: dict[str, Any]) -> Path:
        if self._restore_root is None:
            raise ValueError("Contract reuse requires a fixed restore root")
        key = (envelope["receipt"]["buildKey"], envelope["receiptSha256"])
        existing = self._contract_stages.get(key)
        if existing is not None:
            return existing
        destination = self._restore_root / "contract-stages" / key[0].removeprefix("sha256:") / key[1].removeprefix("sha256:")
        restore_object(
            archive,
            destination,
            build_key=key[0],
            receipt_sha256=key[1],
            object_sha256=envelope["objectSha256"],
        )
        self._contract_stages[key] = destination
        return destination

    def register_contract_stage(
        self,
        archive: Path,
        envelope: dict[str, Any],
    ) -> None:
        self._restore_contract_stage(archive, envelope)

    def contract_stage(self, envelope: dict[str, Any]) -> Path:
        key = (envelope["receipt"]["buildKey"], envelope["receiptSha256"])
        try:
            return self._contract_stages[key]
        except KeyError as error:
            raise ValueError("Authenticated Contract metadata stage was not restored") from error


def _dependency_closure(requested: Iterable[PhaseInstanceId]) -> tuple[PhaseInstanceId, ...]:
    closure: set[PhaseInstanceId] = set()

    def add(instance: PhaseInstanceId) -> None:
        if not isinstance(instance, PhaseInstanceId) or instance not in PHASE_INSTANCE_IDS:
            raise ValueError(f"Unknown requested phase instance: {instance}")
        if instance in closure:
            return
        closure.add(instance)
        for dependency in phase_instance_dependencies(instance):
            add(dependency)

    for instance in requested:
        add(instance)
    return tuple(sorted(closure))


def _absolute_path(value: Any, label: str) -> Path:
    path = Path(require_string(value, label))
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute")
    return path


def _artifact_path(root: Path, value: Any, label: str) -> Path:
    relative = require_relative_path(value, label)
    return root.joinpath(*PurePosixPath(relative).parts)


def _request_identity(value: Any, label: str) -> PhaseInstanceId:
    record = require_exact_keys(value, _IDENTITY_KEYS, label)
    instance = PhaseInstanceId(
        require_string(record["product"], f"{label}.product"),
        require_string(record["component"], f"{label}.component"),
        require_string(record["phase"], f"{label}.phase"),
        require_string(record["target"], f"{label}.target"),
    )
    if instance not in PHASE_INSTANCE_IDS:
        raise ValueError(f"{label} is not a registered phase instance: {instance}")
    return instance


def _request_identities(value: Any, label: str) -> tuple[PhaseInstanceId, ...]:
    instances = tuple(
        _request_identity(member, f"{label}[{index}]")
        for index, member in enumerate(require_array(value, label))
    )
    if not instances or instances != tuple(sorted(set(instances))):
        raise ValueError(f"{label} must be nonempty, sorted, and unique")
    return instances


def _optional_artifact_path(root: Path, value: Any, label: str) -> Path | None:
    return None if value is None else _artifact_path(root, value, label)


def _contract_evidence(root: Path, value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    label = "reuse-wave request.contractEvidence"
    evidence = require_exact_keys(value, _CONTRACT_EVIDENCE_KEYS, label)
    return {
        "attestation": _artifact_path(root, evidence["attestation"], f"{label}.attestation"),
        "attestationSignature": _artifact_path(
            root,
            evidence["attestationSignature"],
            f"{label}.attestationSignature",
        ),
        "publicKey": _artifact_path(root, evidence["publicKey"], f"{label}.publicKey"),
        "expectedTrustDomain": require_string(
            evidence["expectedTrustDomain"],
            f"{label}.expectedTrustDomain",
        ),
        "keyring": _optional_artifact_path(root, evidence["keyring"], f"{label}.keyring"),
        "keysDirectory": _optional_artifact_path(
            root,
            evidence["keysDirectory"],
            f"{label}.keysDirectory",
        ),
    }


def _remote_catalog(root: Path, value: Any, label: str) -> RemoteCatalog:
    catalog = require_exact_keys(value, _REMOTE_CATALOG_KEYS, label)
    object_records = require_array(catalog["objects"], f"{label}.objects")
    objects: dict[str, Path | None] = {}
    previous: str | None = None
    for index, member in enumerate(object_records):
        record = require_exact_keys(
            member,
            {"buildKey", "objectPath"},
            f"{label}.objects[{index}]",
        )
        build_key = require_sha256(record["buildKey"], f"{label}.objects[{index}].buildKey")
        if previous is not None and build_key <= previous:
            raise ValueError(f"{label}.objects must be sorted and unique by buildKey")
        previous = build_key
        objects[build_key] = _optional_artifact_path(
            root,
            record["objectPath"],
            f"{label}.objects[{index}].objectPath",
        )
    return RemoteCatalog(
        manifest=_artifact_path(root, catalog["manifest"], f"{label}.manifest"),
        signature=_artifact_path(root, catalog["signature"], f"{label}.signature"),
        objects=objects,
        public_key=_optional_artifact_path(root, catalog["publicKey"], f"{label}.publicKey"),
        keyring=_optional_artifact_path(root, catalog["keyring"], f"{label}.keyring"),
        keys_directory=_optional_artifact_path(
            root,
            catalog["keysDirectory"],
            f"{label}.keysDirectory",
        ),
        contract_attestation=_optional_artifact_path(
            root, catalog["contractAttestation"], f"{label}.contractAttestation",
        ),
        contract_attestation_signature=_optional_artifact_path(
            root,
            catalog["contractAttestationSignature"],
            f"{label}.contractAttestationSignature",
        ),
        contract_public_key=_optional_artifact_path(
            root, catalog["contractPublicKey"], f"{label}.contractPublicKey",
        ),
    )


def _local_catalog(restore_root: Path, value: Any) -> LocalCatalog | None:
    if value is None:
        return None
    local = require_exact_keys(
        value,
        {"cacheRoot", "candidates"},
        "reuse-wave request.catalogs.local",
    )
    cache_root = _absolute_path(local["cacheRoot"], "reuse-wave request.catalogs.local.cacheRoot")
    candidates: dict[str, list[LocalCandidate]] = {}
    ordered = []
    for index, member in enumerate(require_array(
        local["candidates"],
        "reuse-wave request.catalogs.local.candidates",
    )):
        label = f"reuse-wave request.catalogs.local.candidates[{index}]"
        record = require_exact_keys(
            member,
            {"buildKey", "receiptSha256"},
            label,
        )
        build_key = require_sha256(record["buildKey"], f"{label}.buildKey")
        receipt_sha256 = require_sha256(record["receiptSha256"], f"{label}.receiptSha256")
        destination = restore_root / build_key.removeprefix("sha256:") / receipt_sha256.removeprefix("sha256:")
        identity = (build_key, receipt_sha256)
        ordered.append(identity)
        candidates.setdefault(build_key, []).append(LocalCandidate(receipt_sha256, destination))
    if ordered != sorted(set(ordered)):
        raise ValueError("reuse-wave request.catalogs.local.candidates must be sorted and unique")
    return LocalCatalog(cache_root, {
        build_key: tuple(values) for build_key, values in candidates.items()
    })


def plan_reuse_wave(
    value: Any,
    *,
    build_plan_consumer: Callable[[PhaseInstanceId, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Decode one strict control request and delegate all resolution to advance_reuse."""
    request = require_exact_keys(
        value,
        {
            "schemaVersion",
            "requestType",
            "repository",
            "pullRequest",
            "repositoryRoot",
            "repositoryRevision",
            "artifactRoot",
            "requested",
            "versions",
            "phaseAuthorities",
            "contractEvidence",
            "runtimeValidationEvidence",
            "availableObjects",
            "catalogs",
        } | ({"nativeRuntimeEvidence"} if type(value) is dict and "nativeRuntimeEvidence" in value else set()),
        "reuse-wave request",
    )
    if require_integer(request["schemaVersion"], "reuse-wave request.schemaVersion", 1) != 1:
        raise ValueError("Unsupported reuse-wave request schemaVersion")
    if request["requestType"] != "reuse-wave":
        raise ValueError("Unsupported plan requestType")
    repository_root = _absolute_path(request["repositoryRoot"], "reuse-wave request.repositoryRoot")
    artifact_root = _absolute_path(request["artifactRoot"], "reuse-wave request.artifactRoot")
    revision = require_string(request["repositoryRevision"], "reuse-wave request.repositoryRevision")
    if _GIT_OBJECT_ID.fullmatch(revision) is None:
        raise ValueError("Reuse-wave repositoryRevision must be an exact lowercase Git object ID")
    requested = _request_identities(request["requested"], "reuse-wave request.requested")
    closure = _dependency_closure(requested)
    versions = _validated_versions(request["versions"])

    authorities: dict[PhaseInstanceId, dict[str, Any]] = {}
    ordered_authorities = []
    for index, member in enumerate(require_array(
        request["phaseAuthorities"],
        "reuse-wave request.phaseAuthorities",
    )):
        label = f"reuse-wave request.phaseAuthorities[{index}]"
        record = require_exact_keys(member, _AUTHORITY_KEYS, label)
        instance = _request_identity(
            {key: record[key] for key in _IDENTITY_KEYS},
            label,
        )
        if instance in authorities:
            raise ValueError(f"Duplicate reuse-wave phase authority: {instance}")
        authorities[instance] = record
        ordered_authorities.append(instance)
    if tuple(ordered_authorities) != tuple(sorted(ordered_authorities)):
        raise ValueError("reuse-wave request.phaseAuthorities must be sorted")
    if set(authorities) != set(closure):
        raise ValueError("Reuse-wave phase authorities must exactly match the dependency closure")

    contract_components = tuple(sorted({
        component
        for instance in closure
        for component in required_contract_components(instance)
    }))
    contract_evidence = _contract_evidence(artifact_root, request["contractEvidence"])
    if contract_evidence is not None and not contract_components:
        raise ValueError("Reuse-wave request has unexpected Contract evidence")
    expected_semantic_phases = tuple(
        instance for instance in closure if runtime_validation_dependencies(instance)
    )
    runtime_validation_evidence: dict[PhaseInstanceId, tuple[Path, ...]] = {}
    ordered_runtime_evidence = []
    for index, member in enumerate(require_array(
        request["runtimeValidationEvidence"],
        "reuse-wave request.runtimeValidationEvidence",
    )):
        label = f"reuse-wave request.runtimeValidationEvidence[{index}]"
        record = require_exact_keys(member, _RUNTIME_VALIDATION_EVIDENCE_KEYS, label)
        instance = _request_identity(
            {key: record[key] for key in _IDENTITY_KEYS}, label,
        )
        if instance not in expected_semantic_phases:
            raise ValueError(f"Runtime validation evidence is not applicable: {instance}")
        if instance in runtime_validation_evidence:
            raise ValueError(f"Duplicate Runtime validation evidence: {instance}")
        reports = tuple(
            _artifact_path(artifact_root, path, f"{label}.reports[{report_index}]")
            for report_index, path in enumerate(require_array(
                record["reports"], f"{label}.reports",
            ))
        )
        runtime_validation_evidence[instance] = reports
        ordered_runtime_evidence.append(instance)
    if tuple(ordered_runtime_evidence) != tuple(sorted(ordered_runtime_evidence)):
        raise ValueError("reuse-wave request.runtimeValidationEvidence must be sorted")
    native_targets = {dependency.target for instance in closure for dependency in native_runtime_validation_dependencies(instance)}
    native_evidence = {}
    for member in require_array(request.get("nativeRuntimeEvidence", []), "reuse-wave native Runtime evidence"):
        record = require_exact_keys(member, NATIVE_RUNTIME_EVIDENCE_KEYS, "reuse-wave native Runtime evidence")
        target = record["target"]
        if target not in native_targets or target in native_evidence:
            raise ValueError("Unexpected or duplicate reuse-wave native Runtime evidence target")
        phases = require_exact_keys(record["phaseReceipts"], {"binary", "package", "validation", "metadata"},
                                    "reuse-wave native Runtime phase receipts")
        native_evidence[target] = {
            "target": target,
            "phaseReceipts": {phase: str(_artifact_path(artifact_root, path, f"native Runtime {phase} receipt"))
                              for phase, path in phases.items()},
            **{name: None if record[name] is None and name in {"keyring", "keysDirectory"} else
               str(_artifact_path(artifact_root, record[name], f"native Runtime {name}"))
               for name in NATIVE_RUNTIME_EVIDENCE_KEYS - {"target", "phaseReceipts"}},
        }
    if list(native_evidence) != sorted(native_evidence):
        raise ValueError("Reuse-wave native Runtime evidence targets must be sorted")
    phase_inputs: dict[PhaseInstanceId, dict[str, Any]] = {}
    for instance in closure:
        authority = authorities[instance]
        values = {
            "inventory": phase_git_inventory(repository_root, revision, instance),
            "versions": versions,
            "toolchain_profile_digest": require_sha256(
                authority["toolchainProfileDigest"],
                f"reuse-wave authority {instance}.toolchainProfileDigest",
            ),
            "flags_digest": require_sha256(
                authority["flagsDigest"],
                f"reuse-wave authority {instance}.flagsDigest",
            ),
            "output_schema_version": require_integer(
                authority["outputSchemaVersion"],
                f"reuse-wave authority {instance}.outputSchemaVersion",
                1,
            ),
        }
        phase_inputs[instance] = values

    catalogs = require_exact_keys(
        request["catalogs"],
        {"stable", "promotedMain", "samePr", "local"},
        "reuse-wave request.catalogs",
    )
    stable_values = require_array(catalogs["stable"], "reuse-wave request.catalogs.stable")
    stable_manifests = [
        require_relative_path(
            require_exact_keys(member, _REMOTE_CATALOG_KEYS, label)["manifest"],
            f"{label}.manifest",
        )
        for index, member in enumerate(stable_values)
        for label in (f"reuse-wave request.catalogs.stable[{index}]",)
    ]
    if stable_manifests != sorted(set(stable_manifests)):
        raise ValueError("reuse-wave request.catalogs.stable must be sorted and unique by manifest")
    stable = tuple(
        _remote_catalog(artifact_root, member, f"reuse-wave request.catalogs.stable[{index}]")
        for index, member in enumerate(stable_values)
    )
    promoted_main = None if catalogs["promotedMain"] is None else _remote_catalog(
        artifact_root,
        catalogs["promotedMain"],
        "reuse-wave request.catalogs.promotedMain",
    )
    same_pr = None if catalogs["samePr"] is None else _remote_catalog(
        artifact_root,
        catalogs["samePr"],
        "reuse-wave request.catalogs.samePr",
    )
    pull_request = request["pullRequest"]
    if pull_request is not None:
        pull_request = require_integer(pull_request, "reuse-wave request.pullRequest", 1)
    decoded_objects = []
    for index, member in enumerate(require_array(
        request["availableObjects"],
        "reuse-wave request.availableObjects",
    )):
        label = f"reuse-wave request.availableObjects[{index}]"
        record = require_exact_keys(member, _AVAILABLE_OBJECT_KEYS, label)
        instance = _request_identity(
            {key: record[key] for key in _IDENTITY_KEYS},
            label,
        )
        build_key = require_sha256(record["buildKey"], f"{label}.buildKey")
        receipt_sha256 = require_sha256(record["receiptSha256"], f"{label}.receiptSha256")
        object_sha256 = require_sha256(record["objectSha256"], f"{label}.objectSha256")
        if instance not in closure:
            raise ValueError(f"Available object is outside the requested dependency closure: {instance}")
        decoded_objects.append((
            instance,
            build_key,
            receipt_sha256,
            object_sha256,
            _artifact_path(artifact_root, record["objectPath"], f"{label}.objectPath"),
        ))
    available_identities = [record[0] for record in decoded_objects]
    if available_identities != sorted(set(available_identities)):
        raise ValueError("reuse-wave request.availableObjects must be sorted and unique by phase identity")

    with tempfile.TemporaryDirectory(prefix="codex-agent-reuse-wave-") as temporary:
        restore_root = Path(temporary).resolve()
        session = LookupSession(
            repository=require_string(request["repository"], "reuse-wave request.repository"),
            pull_request=pull_request,
            restore_root=restore_root / "remote",
            stable=stable,
            promoted_main=promoted_main,
            same_pr=same_pr,
            local=_local_catalog(restore_root / "local", catalogs["local"]),
        )
        available = []
        for instance, build_key, receipt_sha256, object_sha256, object_path in decoded_objects:
            verified = verify_object(
                object_path,
                build_key=build_key,
                receipt_sha256=receipt_sha256,
                object_sha256=object_sha256,
            )
            receipt = verified["receipt"]
            if _identity(receipt) != instance:
                raise ValueError("Available object identity does not match its request record")
            envelope = {
                "receipt": receipt,
                "receiptBytes": verified["receiptBytes"],
                "receiptSha256": receipt_sha256,
                "objectSha256": object_sha256,
            }
            available.append(envelope)
            if instance.product == "contract" and instance.phase in {"binary", "metadata"}:
                session.register_contract_stage(object_path, envelope)

        master_projection: VerifiedContractProjection | None = None
        master_contract_stage: Path | None = None

        def contract_projection_provider(
            instance: PhaseInstanceId,
            envelope: dict[str, Any],
        ) -> VerifiedContractProjection:
            nonlocal master_projection, master_contract_stage
            if contract_evidence is None:
                raise ValueError("Contract-consuming reuse requires authenticated Contract evidence")
            if master_projection is None:
                master_contract_stage = session.contract_stage(envelope)
                master_projection = verify_contract_component_projection(
                    master_contract_stage,
                    envelope["receiptBytes"],
                    contract_evidence["attestation"],
                    contract_evidence["attestationSignature"],
                    contract_evidence["publicKey"],
                    expected_trust_domain=contract_evidence["expectedTrustDomain"],
                    expected_contract_version=versions["contract"],
                    required_components=contract_components,
                    keyring=contract_evidence["keyring"],
                    keys_directory=contract_evidence["keysDirectory"],
                )
            return master_projection.restrict(required_contract_components(instance))

        consumed_runtime_validation_evidence: set[PhaseInstanceId] = set()
        consumed_native_evidence: set[str] = set()
        native_projection_cache: dict[tuple[str, str], VerifiedNativeRuntimeProjection] = {}

        def native_runtime_projection_provider(instance, envelopes, projection):
            targets = [dependency.target for dependency in native_runtime_validation_dependencies(instance)]
            if any(target not in native_evidence for target in targets):
                return None
            if master_projection is None or master_contract_stage is None or contract_evidence is None:
                raise ValueError("Native Runtime reuse lacks authenticated Contract evidence")
            keys = [(target, envelope["receiptSha256"]) for target, envelope in zip(targets, envelopes, strict=True)]
            if any(key not in native_projection_cache for key in keys):
                verified = _native_runtime_projections_from_request(
                    instance, [envelope["receipt"] for envelope in envelopes],
                    [native_evidence[target] for target in targets], projection,
                    master_contract_stage / master_projection.receipt_value()["bundlePath"],
                    contract_evidence["expectedTrustDomain"],
                )
                native_projection_cache.update(zip(keys, verified, strict=True))
            consumed_native_evidence.update(targets)
            return tuple(native_projection_cache[key] for key in keys)

        def runtime_validation_projection_provider(
            instance: PhaseInstanceId,
            envelopes: tuple[dict[str, Any], ...],
        ) -> VerifiedRuntimeValidationProjection | None:
            if instance not in runtime_validation_evidence:
                return None
            consumed_runtime_validation_evidence.add(instance)
            return verify_runtime_validation_projection(
                instance,
                runtime_validation_evidence[instance],
                [envelope["receipt"] for envelope in envelopes],
            )

        result, _ = advance_reuse(
            requested,
            phase_inputs,
            available,
            session,
            repository_root=repository_root,
            repository_revision=revision,
            contract_projection_provider=(
                contract_projection_provider if contract_components else None
            ),
            runtime_validation_projection_provider=runtime_validation_projection_provider,
            native_runtime_projection_provider=native_runtime_projection_provider,
            build_plan_consumer=build_plan_consumer,
        )
        unused_evidence = set(runtime_validation_evidence) - consumed_runtime_validation_evidence
        if unused_evidence:
            raise ValueError(
                "Runtime validation evidence was supplied before its metadata phase was ready: "
                f"{sorted(unused_evidence)[0]}"
            )
        if set(native_evidence) - consumed_native_evidence:
            raise ValueError("Native Runtime evidence was supplied before its SDK phase was ready")
        return result


def _plan(
    instance: PhaseInstanceId,
    phase_inputs: Mapping[PhaseInstanceId, Mapping[str, Any]],
    upstream_receipts: list[dict[str, Any]],
    repository_root: Path | None,
    repository_revision: str | None,
) -> dict[str, Any]:
    values = phase_inputs[instance]
    if not isinstance(values, Mapping):
        raise ValueError(f"Phase inputs must be a mapping: {instance}")
    keys = set(values)
    allowed = _PHASE_INPUT_KEYS | {
        "output_schema_version",
        "contract_projection",
        "runtime_validation_projection",
        "native_runtime_projections",
        "contract_execution_projection",
    }
    if not _PHASE_INPUT_KEYS.issubset(keys) or not keys.issubset(allowed):
        raise ValueError(f"Phase inputs fields are invalid: {instance}")
    arguments = dict(values)
    needs_native_authority = (
        instance.product == "runtime"
        and instance.component in NATIVE_TARGETS
        and instance.phase == "binary"
    )
    if needs_native_authority:
        if repository_root is None or repository_revision is None:
            raise ValueError("Native Runtime reuse requires an exact repository root and revision")
    if required_toolchain_profile(instance) is not None and (
        repository_root is None or repository_revision is None
    ):
        raise ValueError("Profiled reuse requires an exact repository root and revision")
    arguments["toolchain_profile_digest"] = verified_phase_toolchain_digest(
        repository_root,
        repository_revision,
        instance,
        arguments["toolchain_profile_digest"],
    )
    arguments["flags_digest"] = verified_phase_flags_digest(
        repository_root,
        repository_revision,
        instance,
        arguments["flags_digest"],
    )
    plan = plan_phase(instance, upstream_receipts=upstream_receipts, **arguments)
    return attach_runtime_binary_identity(
        repository_root,
        repository_revision,
        instance,
        plan,
        arguments.get("contract_projection"),
    ) if needs_native_authority else plan


def advance_reuse(
    requested_instances: Iterable[PhaseInstanceId],
    phase_inputs: Mapping[PhaseInstanceId, Mapping[str, Any]],
    available_receipts: Iterable[dict[str, Any]],
    session: LookupSession,
    *,
    repository_root: Path | None = None,
    repository_revision: str | None = None,
    contract_projection_provider: Callable[
        [PhaseInstanceId, dict[str, Any]], VerifiedContractProjection
    ] | None = None,
    runtime_validation_projection_provider: Callable[
        [PhaseInstanceId, tuple[dict[str, Any], ...]],
        VerifiedRuntimeValidationProjection | None,
    ] | None = None,
    native_runtime_projection_provider: Callable[
        [PhaseInstanceId, tuple[dict[str, Any], ...], VerifiedContractProjection],
        tuple[VerifiedNativeRuntimeProjection, ...] | None,
    ] | None = None,
    contract_execution_projection_provider: Callable[
        [dict[str, Any]], VerifiedContractExecutionProjection
    ] | None = None,
    build_plan_consumer: Callable[[PhaseInstanceId, dict[str, Any]], None] | None = None,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    """Resolve verified reuse and return only the next dependency-ready build wave."""
    if not isinstance(session, LookupSession):
        raise ValueError("Reuse resolution requires a LookupSession")
    if (repository_root is None) != (repository_revision is None):
        raise ValueError("Reuse repository root and revision must be supplied together")
    if contract_projection_provider is not None and not callable(contract_projection_provider):
        raise ValueError("Contract projection provider must be callable")
    if (
        runtime_validation_projection_provider is not None
        and not callable(runtime_validation_projection_provider)
    ):
        raise ValueError("Runtime validation projection provider must be callable")
    if build_plan_consumer is not None and not callable(build_plan_consumer):
        raise ValueError("Build plan consumer must be callable")
    if native_runtime_projection_provider is not None and not callable(native_runtime_projection_provider):
        raise ValueError("Native Runtime projection provider must be callable")
    if contract_execution_projection_provider is not None and not callable(contract_execution_projection_provider):
        raise ValueError("Contract execution projection provider must be callable")
    resolved_repository_root = None if repository_root is None else Path(repository_root)
    closure = _dependency_closure(requested_instances)
    if not isinstance(phase_inputs, Mapping) or set(phase_inputs) != set(closure):
        raise ValueError("Phase inputs must exactly match the requested dependency closure")

    effective_inputs = {}
    for instance, values in phase_inputs.items():
        if not isinstance(values, Mapping):
            raise ValueError(f"Phase inputs must be a mapping: {instance}")
        if {"runtime_validation_projection", "contract_execution_projection", "native_runtime_projections"} & set(values):
            raise ValueError("Callers cannot supply an execution validation projection")
        effective_inputs[instance] = dict(values)
    envelopes: dict[PhaseInstanceId, dict[str, Any]] = {}
    for value in available_receipts:
        instance, envelope = _validate_envelope(value)
        if instance not in closure:
            raise ValueError(f"Receipt envelope is outside the requested dependency closure: {instance}")
        if instance in envelopes:
            raise ValueError(f"Duplicate receipt envelope: {instance}")
        envelopes[instance] = envelope
    verify_build_key_output_consistency([value["receipt"] for value in envelopes.values()])

    resolved: dict[PhaseInstanceId, dict[str, Any]] = {}
    states: dict[PhaseInstanceId, dict[str, Any]] = {}
    build_plans: dict[PhaseInstanceId, dict[str, Any]] = {}
    continuation_requirements: dict[PhaseInstanceId, dict[str, Any]] = {}
    while True:
        progressed = False
        ready = [
            instance for instance in closure
            if instance not in resolved
            and instance not in build_plans
            and all(dependency in resolved for dependency in phase_instance_dependencies(instance))
        ]
        for instance in ready:
            if instance == PhaseInstanceId("contract", "contract", "package", "common"):
                binary = resolved[PhaseInstanceId("contract", "contract", "binary", "common")]
                effective_inputs[instance]["contract_execution_projection"] = (
                    contract_execution_projection_provider(binary)
                    if contract_execution_projection_provider is not None else
                    verify_contract_execution_projection(
                        session.contract_stage(binary), binary["receiptBytes"],
                        expected_receipt_sha256=binary["receiptSha256"],
                    )
                )
            if (
                required_contract_components(instance)
                and "contract_projection" not in effective_inputs[instance]
                and contract_projection_provider is not None
            ):
                contract_identity = PhaseInstanceId(
                    "contract", "contract", "metadata", "common"
                )
                effective_inputs[instance]["contract_projection"] = contract_projection_provider(
                    instance,
                    resolved[contract_identity],
                )
            semantic_dependencies = runtime_validation_dependencies(instance)
            if semantic_dependencies:
                projection = (
                    None
                    if runtime_validation_projection_provider is None
                    else runtime_validation_projection_provider(
                        instance,
                        tuple(resolved[dependency] for dependency in semantic_dependencies),
                    )
                )
                if projection is None:
                    continuation_requirements[instance] = {
                        "kind": "runtime-validation-evidence",
                        "product": instance.product,
                        "component": instance.component,
                        "phase": instance.phase,
                        "target": instance.target,
                        "dependencies": [{
                            "product": dependency.product,
                            "component": dependency.component,
                            "phase": dependency.phase,
                            "target": dependency.target,
                        } for dependency in semantic_dependencies],
                    }
                    continue
                effective_inputs[instance]["runtime_validation_projection"] = projection
                continuation_requirements.pop(instance, None)
            native_dependencies = native_runtime_validation_dependencies(instance)
            if native_dependencies:
                native_projections = None if native_runtime_projection_provider is None else native_runtime_projection_provider(
                    instance, tuple(resolved[dependency] for dependency in native_dependencies),
                    effective_inputs[instance].get("contract_projection"),
                )
                if native_projections is None:
                    continuation_requirements[instance] = {
                        "kind": "native-runtime-validation-evidence", "product": instance.product,
                        "component": instance.component, "phase": instance.phase, "target": instance.target,
                        "dependencies": [{"product": item.product, "component": item.component,
                                          "phase": item.phase, "target": item.target} for item in native_dependencies],
                    }
                    continue
                effective_inputs[instance]["native_runtime_projections"] = native_projections
                continuation_requirements.pop(instance, None)
            plan = _plan(
                instance,
                effective_inputs,
                [resolved[dependency]["receipt"] for dependency in phase_instance_dependencies(instance)],
                resolved_repository_root,
                repository_revision,
            )
            if instance in envelopes:
                try:
                    _, envelope = _validate_envelope(envelopes[instance], expected_plan=plan)
                except ValueError:
                    del envelopes[instance]
                else:
                    resolved[instance] = envelope
                    states[instance] = {
                        "plan": plan,
                        "state": "retained",
                        "source": None,
                        "transportSource": None,
                        "misses": [],
                    }
                    progressed = True
                    continue

            misses = []
            for source in SOURCES:
                outcome = session.lookup(source, plan)
                if outcome.envelope is None:
                    misses.append({"source": source, "reason": outcome.reason})
                    continue
                envelopes[instance] = outcome.envelope
                resolved[instance] = outcome.envelope
                states[instance] = {
                    "plan": plan,
                    "state": "reused",
                    "source": source,
                    "transportSource": outcome.transport_source,
                    "misses": misses,
                }
                verify_build_key_output_consistency(
                    [member["receipt"] for member in envelopes.values()]
                )
                progressed = True
                break
            else:
                build_plans[instance] = plan
                states[instance] = {
                    "plan": plan,
                    "state": "build",
                    "source": None,
                    "transportSource": None,
                    "misses": misses,
                }
        if not progressed:
            break

    phases = []
    for instance in closure:
        state = states.get(instance)
        envelope = resolved.get(instance)
        phases.append({
            "product": instance.product,
            "component": instance.component,
            "phase": instance.phase,
            "target": instance.target,
            "buildKey": state["plan"]["buildKey"] if state is not None else None,
            "state": state["state"] if state is not None else "waiting",
            "source": state["source"] if state is not None else None,
            "transportSource": state["transportSource"] if state is not None else None,
            "receiptSha256": envelope["receiptSha256"] if envelope is not None else None,
            "objectSha256": envelope["objectSha256"] if envelope is not None else None,
            "misses": state["misses"] if state is not None else [],
        })

    matrices = {product: [] for product in MATRIX_PRODUCTS}
    for instance, plan in sorted(build_plans.items()):
        matrices[instance.product].append({
            "product": instance.product,
            "component": instance.component,
            "phase": instance.phase,
            "target": instance.target,
            "buildKey": plan["buildKey"],
        })
    full_reuse = len(resolved) == len(closure)
    if build_plan_consumer is not None:
        for instance, plan in sorted(build_plans.items()):
            build_plan_consumer(instance, dict(plan))
    return {
        "schemaVersion": 1,
        "result": "complete" if full_reuse else "build-required",
        "fullReuse": full_reuse,
        "phases": phases,
        "matrices": matrices,
        "continuationRequirements": [
            continuation_requirements[instance]
            for instance in sorted(continuation_requirements)
        ],
    }, tuple(resolved[instance] for instance in sorted(resolved))
