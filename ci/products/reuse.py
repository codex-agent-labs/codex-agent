from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .aggregate import verify_immutable_product_indexes
from .inventory import (
    load_canonical_json_bytes,
    require_exact_keys,
    require_integer,
    require_relative_path,
    require_sha256,
    sha256_bytes,
)
from .index import (
    SignedProductIndex,
    stable_index_identity,
    verify_release_product_index,
    verify_signed_product_index,
)
from .plan import (
    attach_runtime_binary_identity,
    plan_phase,
    verified_phase_flags_digest,
    verified_phase_toolchain_digest,
    verify_build_key_output_consistency,
)
from .receipt import output_inventory_digest, validate_phase_receipt
from .receipt import build_key_payload
from .registry import (
    NATIVE_TARGETS,
    PHASE_INSTANCE_IDS,
    PhaseInstanceId,
    phase_instance_dependencies,
    required_toolchain_profile,
)
from .restore import CacheObjectError, object_relative_path, restore_local_object, verify_object


SOURCES = ("stable", "promoted-main", "same-pr", "local")
MATRIX_PRODUCTS = ("contract", "runtime", "sdk")
_ENVELOPE_KEYS = {"receipt", "receiptBytes", "receiptSha256", "objectSha256"}
_PHASE_INPUT_KEYS = {
    "inventory",
    "versions",
    "toolchain_profile_digest",
    "flags_digest",
}


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


def _verify_index_receipt(entry: dict[str, Any], envelope: dict[str, Any]) -> None:
    receipt = envelope["receipt"]
    expected_identity = (
        entry["product"],
        entry["component"],
        entry["phase"],
        entry["target"],
        entry["productVersion"],
        entry["buildKey"],
    )
    actual_identity = (
        receipt["product"],
        receipt["component"],
        receipt["phase"],
        receipt["target"],
        receipt["productVersion"],
        receipt["buildKey"],
    )
    if actual_identity != expected_identity:
        raise ValueError("Product index entry and restored receipt identity disagree")
    if envelope["receiptSha256"] != entry["receiptSha256"]:
        raise ValueError("Product index entry and restored receipt digest disagree")
    if receipt["outputs"] != entry["outputs"] or \
            output_inventory_digest(receipt["outputs"]) != entry["outputInventoryDigest"]:
        raise ValueError("Product index entry and restored receipt outputs disagree")
    artifacts = [
        output for output in receipt["outputs"]
        if output["relativePath"] == entry["artifactName"]
        and output["sha256"] == entry["artifactSha256"]
    ]
    if len(artifacts) != 1:
        raise ValueError("Product index entry artifact disagrees with the restored receipt")


class LookupSession:
    """A run-scoped, preverified catalog and cache lookup session."""

    def __init__(
        self,
        *,
        repository: str,
        pull_request: int | None,
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
        self._remote: dict[str, dict[str, list[_RemoteCandidate]]] = {
            source: {} for source in SOURCES[:-1]
        }
        loaded_indexes: list[dict[str, Any]] = []
        stable_indexes = []
        for catalog in stable:
            index = self._load_catalog("stable", catalog)
            for prior in stable_indexes:
                verify_immutable_product_indexes(prior, index)
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
                _RemoteCandidate(entry, object_path, sha256_bytes(contents))
            )
        return index

    @staticmethod
    def _reject_conflicting_catalog_outputs(indexes: list[dict[str, Any]]) -> None:
        outputs_by_key: dict[str, tuple[str, list[dict[str, Any]]]] = {}
        for index in indexes:
            for entry in index["entries"]:
                current = (entry["outputInventoryDigest"], entry["outputs"])
                prior = outputs_by_key.setdefault(entry["buildKey"], current)
                if prior != current:
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
                expected_trust = "development" if source == "same-pr" else "release"
                if envelope["receipt"]["trustDomain"] != expected_trust:
                    raise ValueError("Restored receipt trust does not match its product index source")
                _verify_index_receipt(candidate.entry, envelope)
            except (CacheObjectError, TypeError, ValueError) as error:
                raise ReuseLookupError(f"{source} matching object or index entry is corrupt") from error
            return _LookupResult(envelope, None, {
                "kind": source,
                "indexSha256": candidate.index_sha256,
                "artifactName": candidate.entry["artifactName"],
                "artifactSha256": candidate.entry["artifactSha256"],
            })
        return _LookupResult(None, "artifact-unavailable")

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
    allowed = _PHASE_INPUT_KEYS | {"output_schema_version", "contract_projection"}
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
    if required_toolchain_profile(instance) is not None:
        if repository_root is None or repository_revision is None:
            raise ValueError("Profiled reuse requires an exact repository root and revision")
        arguments["toolchain_profile_digest"] = verified_phase_toolchain_digest(
            repository_root,
            repository_revision,
            instance,
            arguments["toolchain_profile_digest"],
        )
    if needs_native_authority:
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
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    """Resolve verified reuse and return only the next dependency-ready build wave."""
    if not isinstance(session, LookupSession):
        raise ValueError("Reuse resolution requires a LookupSession")
    if (repository_root is None) != (repository_revision is None):
        raise ValueError("Reuse repository root and revision must be supplied together")
    resolved_repository_root = None if repository_root is None else Path(repository_root)
    closure = _dependency_closure(requested_instances)
    if not isinstance(phase_inputs, Mapping) or set(phase_inputs) != set(closure):
        raise ValueError("Phase inputs must exactly match the requested dependency closure")

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
    while True:
        progressed = False
        ready = [
            instance for instance in closure
            if instance not in resolved
            and instance not in build_plans
            and all(dependency in resolved for dependency in phase_instance_dependencies(instance))
        ]
        for instance in ready:
            plan = _plan(
                instance,
                phase_inputs,
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
    return {
        "schemaVersion": 1,
        "result": "complete" if full_reuse else "build-required",
        "fullReuse": full_reuse,
        "phases": phases,
        "matrices": matrices,
    }, tuple(resolved[instance] for instance in sorted(resolved))
