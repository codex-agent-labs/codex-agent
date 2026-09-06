from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Mapping
from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import stat
import subprocess
import tempfile
from typing import Any, Iterable, Iterator
from weakref import WeakKeyDictionary

from .aggregate import validate_product_index, verify_immutable_product_indexes
from .contract_projection import verify_contract_execution_projection
from .restore import restore_object, verify_object
from .inventory import (
    _is_windows,
    _open_directory,
    _open_regular_file,
    _stat_identity,
    _windows_directory_path,
    canonical_json_bytes,
    load_canonical_json_bytes,
    read_regular_file_bytes,
    require_exact_keys,
    require_relative_path,
    require_semver,
    require_sha256,
    sha256_bytes,
    write_canonical_json,
)
from .receipt import output_inventory_digest, validate_phase_receipt
from .registry import published_coordinate
from .sdk_runtime_content import VerifiedNativeRuntimeProjection
from .runtime_adapter_content import VerifiedAdapterRuntimeProjection
from .signatures import (
    load_keyring,
    public_key_for_metadata,
    sign_manifest,
    verify_manifest_signature,
)


_INDEX_LIMIT = 16 * 1024 * 1024
_SIGNATURE_LIMIT = 1024 * 1024
_HISTORY_TOKEN = object()
_RELEASE_ADMISSION_TOKEN = object()


class ReleaseIndexAdmission:
    __slots__ = ("__weakref__",)

    def __new__(cls, token: object) -> ReleaseIndexAdmission:
        if token is not _RELEASE_ADMISSION_TOKEN:
            raise TypeError("Release-index admission is verifier-produced")
        return super().__new__(cls)


@dataclass(frozen=True, slots=True)
class _ReleaseAdmissionBinding:
    _token: object
    _identity: tuple[str, str, str, str]
    _build_key: str
    _receipt_sha256: str
    _outputs: bytes
    _output_inventory_digest: str
    _artifact_name: str
    _artifact_sha256: str


_RELEASE_ADMISSIONS: WeakKeyDictionary[
    ReleaseIndexAdmission, _ReleaseAdmissionBinding,
] = WeakKeyDictionary()


@dataclass(frozen=True, slots=True)
class IndexEntrySource:
    receipt_bytes: bytes
    artifact_path: str
    release_admission: ReleaseIndexAdmission | None = None


@dataclass(frozen=True, slots=True)
class SignedProductIndex:
    manifest: Path
    signature: Path


@dataclass(frozen=True, slots=True)
class VerifiedStableIndexHistory:
    _repository: str
    _index_bytes: tuple[bytes, ...]
    _token: object
    _contract_objects: tuple[tuple[str, Path], ...] = ()
    _native_runtime_objects: tuple[tuple[str, Path], ...] = ()
    _adapter_runtime_objects: tuple[tuple[str, Path], ...] = ()


def _verify_signed_bytes(
    contents: bytes,
    signature: bytes,
    public_key: Path,
    signing: dict[str, Any],
) -> None:
    public_key_bytes = read_regular_file_bytes(
        Path(public_key), max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True,
    )
    with tempfile.TemporaryDirectory(prefix="codex-agent-product-index-verify-") as temporary:
        root = Path(temporary).resolve()
        manifest = root / "product-index.json"
        detached = root / "product-index.sig"
        key = root / "public-key.pub"
        manifest.write_bytes(contents)
        detached.write_bytes(signature)
        key.write_bytes(public_key_bytes)
        verify_manifest_signature(manifest, detached, key, signing)


def verify_signed_product_index(
    source: SignedProductIndex,
    public_key: Path,
) -> tuple[dict[str, Any], bytes]:
    if not isinstance(source, SignedProductIndex):
        raise ValueError("Signed product-index source is invalid")
    contents = read_regular_file_bytes(
        Path(source.manifest), max_bytes=_INDEX_LIMIT, reject_symlink_parents=True,
    )
    signature = read_regular_file_bytes(
        Path(source.signature), max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True,
    )
    index = validate_product_index(load_canonical_json_bytes(contents))
    _verify_signed_bytes(contents, signature, public_key, index["signing"])
    return index, contents


def verify_release_product_index(
    source: SignedProductIndex,
    *,
    keyring_path: Path,
    keys_directory: Path,
) -> tuple[dict[str, Any], bytes]:
    keyring = load_keyring(Path(keyring_path), Path(keys_directory))
    index, contents, _ = _verify_release_product_index_with_keyring(
        source, keyring, Path(keys_directory),
    )
    return index, contents


def _verify_release_product_index_with_keyring(
    source: SignedProductIndex,
    keyring: dict[str, Any],
    keys_directory: Path,
) -> tuple[dict[str, Any], bytes, bytes]:
    if not isinstance(source, SignedProductIndex):
        raise ValueError("Signed product-index source is invalid")
    contents = read_regular_file_bytes(
        Path(source.manifest), max_bytes=_INDEX_LIMIT, reject_symlink_parents=True,
    )
    signature = read_regular_file_bytes(
        Path(source.signature), max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True,
    )
    index = validate_product_index(load_canonical_json_bytes(contents))
    public_key = public_key_for_metadata(
        index["signing"], keyring, keys_directory, allow_retired=True,
    )
    _verify_signed_bytes(contents, signature, public_key, index["signing"])
    return index, contents, signature


def stable_index_identity(index: dict[str, Any]) -> tuple[str, str]:
    if index["trustDomain"] != "release" or index["context"]["kind"] != "stable":
        raise ValueError("Stable product-index history requires release-trust stable indexes")
    product, marker, version = index["context"]["tag"].partition("/v")
    identities = {(entry["product"], entry["productVersion"]) for entry in index["entries"]}
    if marker != "/v" or "-" in version or identities != {(product, version)}:
        raise ValueError("Stable product index tag does not match one stable product identity")
    return product, version


def _authoritative_stable_refs(repository: str) -> dict[str, str]:
    repository = require_relative_path(repository, "Stable product-index repository")
    if repository.count("/") != 1:
        raise ValueError("Stable product-index repository must be an owner/repository pair")
    command = [
        "git", "ls-remote", "--refs", "--tags", f"https://github.com/{repository}.git",
        "refs/tags/contract/v*", "refs/tags/runtime/v*", "refs/tags/sdk/v*",
    ]
    try:
        output = subprocess.run(
            command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Current protected stable-tag inventory is unavailable") from error
    refs: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 2 or len(fields[0]) != 40 or any(
            character not in "0123456789abcdef" for character in fields[0]
        ) or not fields[1].startswith("refs/tags/"):
            raise ValueError("Current protected stable-tag inventory is malformed")
        tag = fields[1][len("refs/tags/"):]
        product, marker, version = tag.partition("/v")
        if product not in {"contract", "runtime", "sdk"} or marker != "/v" or \
                "-" in require_semver(version, "Stable product tag version"):
            raise ValueError("Current protected stable-tag inventory contains an invalid tag")
        if tag in refs:
            raise ValueError("Current protected stable-tag inventory contains a duplicate tag")
        refs[tag] = fields[0]
    return refs


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


def verify_contract_index_object(entry: dict[str, Any], archive: Path):
    """Authenticate retained execution bytes against one already-validated index entry."""
    verified = verify_object(archive, build_key=entry["buildKey"], receipt_sha256=entry["receiptSha256"])
    _verify_index_receipt(entry, {
        **verified, "receiptSha256": sha256_bytes(verified["receiptBytes"]),
    })
    with tempfile.TemporaryDirectory(prefix="contract-index-execution-") as temporary:
        stage = Path(temporary).resolve() / "stage"
        restore_object(
            archive, stage, build_key=entry["buildKey"], receipt_sha256=entry["receiptSha256"],
            object_sha256=verified["objectSha256"],
        )
        return verify_contract_execution_projection(
            stage, verified["receiptBytes"], expected_receipt_sha256=entry["receiptSha256"],
        )


def verify_native_runtime_index_object(entry: dict[str, Any], archive: Path, projection_provider):
    """Bind complete K/R proof to actual retained bytes, not an index-supplied SHA."""
    from .registry import NATIVE_TARGETS
    if (entry["product"] != "runtime" or entry["phase"] != "validation"
            or entry["component"] != entry["target"] or entry["target"] not in NATIVE_TARGETS):
        raise ValueError("Native Runtime comparison requires an exact native validation entry")
    if not callable(projection_provider):
        raise ValueError("Native Runtime comparison requires authenticated original evidence")
    verified = verify_object(archive, build_key=entry["buildKey"], receipt_sha256=entry["receiptSha256"])
    _verify_index_receipt(entry, {**verified, "receiptSha256": sha256_bytes(verified["receiptBytes"])})
    proof = projection_provider(entry, archive)
    if type(proof) is not VerifiedNativeRuntimeProjection:
        raise ValueError("Verified native Runtime projection is required for index consistency")
    proof.output_inventory(entry["receiptSha256"], verified["receipt"]["outputs"], identity=entry)
    return proof


def verify_adapter_runtime_index_object(entry: dict[str, Any], archive: Path, projection_provider):
    """Require the retained original object and complete signed adapter-stage proof."""
    from .aggregate import RUNTIME_ADAPTERS
    from .registry import NATIVE_TARGETS
    if (entry["product"] != "runtime" or entry["phase"] != "validation"
            or entry["component"] not in RUNTIME_ADAPTERS or entry["target"] not in NATIVE_TARGETS):
        raise ValueError("Adapter Runtime comparison requires an exact adapter host validation entry")
    if not callable(projection_provider):
        raise ValueError("Adapter Runtime comparison requires authenticated original evidence")
    verified = verify_object(archive, build_key=entry["buildKey"], receipt_sha256=entry["receiptSha256"])
    _verify_index_receipt(entry, {**verified, "receiptSha256": sha256_bytes(verified["receiptBytes"])})
    proof = projection_provider(entry, archive)
    if type(proof) is not VerifiedAdapterRuntimeProjection:
        raise ValueError("Verified adapter Runtime projection is required for index consistency")
    proof.output_inventory(entry["receiptSha256"], verified["receipt"]["outputs"], identity=entry)
    return proof


def _contract_object_references(objects, label="Contract"):
    if objects is None:
        return {}
    if not isinstance(objects, Mapping):
        raise ValueError(f"{label} index objects must be a receipt-qualified mapping")
    result = {}
    for key, value in objects.items():
        digest = require_sha256(key, f"{label} index object receipt digest")
        if not isinstance(value, (str, Path)):
            raise ValueError(f"{label} index object path must be a filesystem path")
        result[digest] = Path(os.path.abspath(value))
    return result


def _contract_object_projection(objects):
    proofs = {}

    def verify(entry):
        key = canonical_json_bytes(entry)
        if key not in proofs:
            archive = objects.get(entry["receiptSha256"])
            if archive is None:
                raise ValueError("Conflicting Contract execution inventories require both authenticated objects")
            proofs[key] = verify_contract_index_object(entry, archive)
        return proofs[key]

    return verify


def _runtime_object_projection(objects, provider, *, adapter=False):
    if provider is None:
        return None
    if not callable(provider):
        raise ValueError("Runtime projection provider must be callable")
    proofs = {}

    def verify(entry):
        key = canonical_json_bytes(entry)
        if key not in proofs:
            archive = objects.get(entry["receiptSha256"])
            if archive is None:
                raise ValueError("Conflicting Runtime inventories require both authenticated objects")
            verifier = verify_adapter_runtime_index_object if adapter else verify_native_runtime_index_object
            proofs[key] = verifier(entry, archive, provider)
        return proofs[key]

    return verify


def verify_stable_index_history(
    sources: Iterable[SignedProductIndex],
    *,
    repository: str,
    keyring_path: Path,
    keys_directory: Path,
    contract_objects: Mapping[str, Path] | None = None,
    native_runtime_objects: Mapping[str, Path] | None = None,
    native_runtime_projection=None,
    adapter_runtime_objects: Mapping[str, Path] | None = None,
    adapter_runtime_projection=None,
) -> VerifiedStableIndexHistory:
    objects = _contract_object_references(contract_objects)
    execution_projection = _contract_object_projection(objects)
    native_objects = _contract_object_references(native_runtime_objects, "Native Runtime")
    native_projection = _runtime_object_projection(native_objects, native_runtime_projection)
    adapter_objects = _contract_object_references(adapter_runtime_objects, "Adapter Runtime")
    adapter_projection = _runtime_object_projection(adapter_objects, adapter_runtime_projection, adapter=True)
    keyring = load_keyring(Path(keyring_path), Path(keys_directory))
    authoritative_refs = _authoritative_stable_refs(repository)
    verified: list[bytes] = []
    indexes: list[dict[str, Any]] = []
    tags = []
    for source in sources:
        if not isinstance(source, SignedProductIndex):
            raise ValueError("Stable product-index history source is invalid")
        index, contents, _ = _verify_release_product_index_with_keyring(
            source, keyring, Path(keys_directory),
        )
        if index["repository"] != repository:
            raise ValueError("Stable product-index history repository mismatch")
        stable_index_identity(index)
        tags.append(index["context"]["tag"])
        for prior in indexes:
            verify_immutable_product_indexes(prior, index, contract_execution_projection=execution_projection,
                                             native_runtime_projection=native_projection,
                                             adapter_runtime_projection=adapter_projection)
        indexes.append(index)
        verified.append(contents)
    if len(tags) != len(set(tags)) or set(tags) != set(authoritative_refs):
        raise ValueError(
            "Stable product-index sources do not match the current protected stable-tag inventory"
        )
    return VerifiedStableIndexHistory(repository, tuple(verified), _HISTORY_TOKEN,
                                      tuple(objects.items()), tuple(native_objects.items()), tuple(adapter_objects.items()))


def _validated_entry_source(
    source: IndexEntrySource,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    if not isinstance(source, IndexEntrySource) or type(source.receipt_bytes) is not bytes:
        raise ValueError("Product index entry source is invalid")
    receipt = validate_phase_receipt(load_canonical_json_bytes(source.receipt_bytes))
    artifact_path = require_relative_path(source.artifact_path, "Product index entry artifact path")
    artifacts = [
        output for output in receipt["outputs"] if output["relativePath"] == artifact_path
    ]
    if len(artifacts) != 1:
        raise ValueError("Product index artifact must name exactly one receipt output")
    return receipt, artifact_path, artifacts[0]


def _mint_release_admission(
    source: IndexEntrySource,
    verified_receipt: dict[str, Any],
    verified_receipt_bytes: bytes,
    expected_identity: tuple[str, str, str, str],
) -> ReleaseIndexAdmission:
    receipt, artifact_path, artifact = _validated_entry_source(source)
    identity = tuple(receipt[field] for field in ("product", "component", "phase", "target"))
    if source.release_admission is not None or receipt["trustDomain"] != "development":
        raise ValueError("Release admission requires an unadmitted development receipt")
    if identity != expected_identity or receipt != verified_receipt or \
            source.receipt_bytes != verified_receipt_bytes:
        raise ValueError("Release admission verifier result does not match the exact receipt")
    admission = ReleaseIndexAdmission(_RELEASE_ADMISSION_TOKEN)
    _RELEASE_ADMISSIONS[admission] = _ReleaseAdmissionBinding(
        _RELEASE_ADMISSION_TOKEN,
        identity,
        receipt["buildKey"],
        sha256_bytes(source.receipt_bytes),
        canonical_json_bytes(receipt["outputs"]),
        output_inventory_digest(receipt["outputs"]),
        artifact_path,
        artifact["sha256"],
    )
    return admission


def release_attested_contract_admission(
    source: IndexEntrySource,
    *,
    payload: Path,
    metadata_receipt: Path,
    attestation: Path,
    signature: Path,
    public_key: Path,
    keyring: Path,
    keys_directory: Path,
) -> ReleaseIndexAdmission:
    from .contract_attestation import verify_contract_attestation

    _, verified_receipt, _ = verify_contract_attestation(
        Path(payload), Path(metadata_receipt), Path(attestation), Path(signature),
        Path(public_key), required_trust_domain="release",
        keyring=Path(keyring), keys_directory=Path(keys_directory),
    )
    receipt_bytes = read_regular_file_bytes(
        Path(metadata_receipt), max_bytes=_INDEX_LIMIT, reject_symlink_parents=True,
    )
    return _mint_release_admission(
        source, verified_receipt, receipt_bytes,
        ("contract", "contract", "metadata", "common"),
    )


def release_attested_runtime_variant_admission(
    source: IndexEntrySource,
    *,
    payload: Path,
    binary_receipt: Path,
    package_receipt: Path,
    validation_receipt: Path,
    metadata_receipt: Path,
    validation_evidence: Path,
    attestation: Path,
    signature: Path,
    public_key: Path,
    keyring: Path,
    keys_directory: Path,
) -> ReleaseIndexAdmission:
    from .runtime_attestation import verify_runtime_variant_attestation

    manifest, receipts, _ = verify_runtime_variant_attestation(
        Path(payload), Path(binary_receipt), Path(package_receipt), Path(validation_receipt),
        Path(metadata_receipt), Path(attestation), Path(signature), Path(public_key),
        required_trust_domain="release", validation_evidence=Path(validation_evidence),
        keyring=Path(keyring), keys_directory=Path(keys_directory),
    )
    receipt, _, _ = _validated_entry_source(source)
    phase = receipt["phase"]
    paths = {
        "binary": binary_receipt,
        "package": package_receipt,
        "validation": validation_receipt,
        "metadata": metadata_receipt,
    }
    if phase not in paths:
        raise ValueError("Runtime variant release admission receipt phase is invalid")
    receipt_bytes = read_regular_file_bytes(
        Path(paths[phase]), max_bytes=_INDEX_LIMIT, reject_symlink_parents=True,
    )
    return _mint_release_admission(
        source, receipts[phase], receipt_bytes,
        ("runtime", manifest["target"], phase, manifest["target"]),
    )


def release_attested_runtime_aggregate_admission(
    source: IndexEntrySource,
    *,
    manifest: Path,
    metadata_receipt: Path,
    attestation: Path,
    signature: Path,
    public_key: Path,
    variant_bundles: dict[str, Path],
    variant_phase_receipts: dict[str, dict[str, Path]],
    variant_attestations: dict[str, Path],
    variant_attestation_signatures: dict[str, Path],
    variant_public_keys: dict[str, Path],
    variant_validation_evidence: dict[str, Path],
    adapter_receipts: list[dict[str, Any]],
    keyring: Path,
    keys_directory: Path,
    variant_keyring: Path,
    variant_keys_directory: Path,
) -> ReleaseIndexAdmission:
    from .runtime_aggregate import (
        verify_runtime_aggregate_attestation,
        verify_runtime_aggregate_attestation_closure,
    )

    aggregate, verified_receipt, verified_attestation = verify_runtime_aggregate_attestation(
        Path(manifest), Path(metadata_receipt), Path(attestation), Path(signature),
        Path(public_key), required_trust_domain="release",
        keyring=Path(keyring), keys_directory=Path(keys_directory),
    )
    verify_runtime_aggregate_attestation_closure(
        aggregate, verified_attestation,
        variant_bundles=variant_bundles,
        variant_phase_receipts=variant_phase_receipts,
        variant_attestations=variant_attestations,
        variant_attestation_signatures=variant_attestation_signatures,
        variant_public_keys=variant_public_keys,
        adapter_receipts=adapter_receipts,
        required_variant_trust_domain="release",
        variant_validation_evidence=variant_validation_evidence,
        variant_keyring=Path(variant_keyring),
        variant_keys_directory=Path(variant_keys_directory),
    )
    receipt_bytes = read_regular_file_bytes(
        Path(metadata_receipt), max_bytes=_INDEX_LIMIT, reject_symlink_parents=True,
    )
    return _mint_release_admission(
        source, verified_receipt, receipt_bytes,
        ("runtime", "runtime-aggregate", "metadata", "aggregate"),
    )


def _entry(
    source: IndexEntrySource,
    *,
    repository: str,
    trust_domain: str,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    receipt, artifact_path, artifact = _validated_entry_source(source)
    identity = tuple(receipt[field] for field in ("product", "component", "phase", "target"))
    admission = (
        _RELEASE_ADMISSIONS.get(source.release_admission)
        if isinstance(source.release_admission, ReleaseIndexAdmission) else None
    )
    release_admitted = (
        trust_domain == "release"
        and receipt["trustDomain"] == "development"
        and admission is not None
        and admission._token is _RELEASE_ADMISSION_TOKEN
        and admission._identity == identity
        and admission._build_key == receipt["buildKey"]
        and admission._receipt_sha256 == sha256_bytes(source.receipt_bytes)
        and admission._outputs == canonical_json_bytes(receipt["outputs"])
        and admission._output_inventory_digest
        == output_inventory_digest(receipt["outputs"])
        and admission._artifact_name == artifact_path
        and admission._artifact_sha256 == artifact["sha256"]
    )
    if receipt["trustDomain"] != trust_domain and not release_admitted:
        raise ValueError("Product index receipt trust domain does not match the index")
    if receipt["trustDomain"] == trust_domain and source.release_admission is not None:
        raise ValueError("Product index release admission is not applicable to this receipt")
    if receipt["producer"]["repository"] != repository:
        raise ValueError("Product index receipt repository does not match the index")
    return ({
        "buildKey": receipt["buildKey"],
        "product": receipt["product"],
        "component": receipt["component"],
        "phase": receipt["phase"],
        "target": receipt["target"],
        "productVersion": receipt["productVersion"],
        "coordinate": published_coordinate(receipt["product"], receipt["component"]),
        "outputInventoryDigest": output_inventory_digest(receipt["outputs"]),
        "outputs": receipt["outputs"],
        "artifactName": artifact_path,
        "artifactSha256": artifact["sha256"],
        "receiptSha256": sha256_bytes(source.receipt_bytes),
    }, receipt, release_admitted)


def build_product_index(
    sources: Iterable[IndexEntrySource],
    *,
    repository: str,
    context: dict[str, Any],
    trust_domain: str,
    signing: dict[str, Any],
    producer: dict[str, Any],
    stable_history: VerifiedStableIndexHistory | None,
    contract_objects: Mapping[str, Path] | None = None,
    native_runtime_objects: Mapping[str, Path] | None = None,
    native_runtime_projection=None,
    adapter_runtime_objects: Mapping[str, Path] | None = None,
    adapter_runtime_projection=None,
) -> dict[str, Any]:
    objects = _contract_object_references(contract_objects)
    native_objects = _contract_object_references(native_runtime_objects, "Native Runtime")
    adapter_objects = _contract_object_references(adapter_runtime_objects, "Adapter Runtime")
    pairs = sorted(
        (_entry(source, repository=repository, trust_domain=trust_domain) for source in sources),
        key=lambda pair: pair[0]["buildKey"],
    )
    entries = [entry for entry, _, _ in pairs]
    keys = [entry["buildKey"] for entry in entries]
    if len(keys) != len(set(keys)):
        raise ValueError("Product index entry build keys must be unique")
    index = validate_product_index({
        "schemaVersion": 1,
        "repository": repository,
        "context": context,
        "entries": entries,
        "trustDomain": trust_domain,
        "signing": signing,
        "producer": producer,
    })
    if index["context"]["kind"] == "pull-request":
        if index["trustDomain"] != "development":
            raise ValueError("Pull-request product index requires development trust")
        pull_request = index["context"]["pullRequest"]
        if any(
            receipt["producer"]["event"] != "pull_request"
            or receipt["producer"]["pullRequest"] != pull_request
            for _, receipt, _ in pairs
        ):
            raise ValueError("Pull-request product index contains a receipt from another context")
    elif any(
        receipt["producer"]["event"] != "push" and not release_admitted
        for _, receipt, release_admitted in pairs
    ):
        raise ValueError("Release product index contains a non-push receipt")
    if index["context"]["kind"] == "stable":
        stable_index_identity(index)
        if not isinstance(stable_history, VerifiedStableIndexHistory) or \
                stable_history._token is not _HISTORY_TOKEN or \
                stable_history._repository != repository:
            raise ValueError("Stable product index requires explicit authenticated history")
        execution_projection = _contract_object_projection({**dict(stable_history._contract_objects), **objects})
        native_projection = _runtime_object_projection(
            {**dict(stable_history._native_runtime_objects), **native_objects}, native_runtime_projection)
        adapter_projection = _runtime_object_projection(
            {**dict(stable_history._adapter_runtime_objects), **adapter_objects}, adapter_runtime_projection, adapter=True)
        for contents in stable_history._index_bytes:
            verify_immutable_product_indexes(
                validate_product_index(load_canonical_json_bytes(contents)), index,
                contract_execution_projection=execution_projection,
                native_runtime_projection=native_projection,
                adapter_runtime_projection=adapter_projection,
            )
    elif stable_history is not None:
        raise ValueError("Only a stable product index accepts stable history")
    return index


@contextmanager
def _held_output_parent(path: Path) -> Iterator[tuple[int, Path]]:
    parent = Path(os.path.abspath(path))
    if _is_windows():
        parent = _windows_directory_path(parent, "Product index output parent")
        before = parent.lstat()
        import ctypes
        import msvcrt
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        handle = create_file(
            str(parent), 0x0080, 0x0001 | 0x0002, None, 3,
            0x02000000 | 0x00200000, None,
        )
        if handle == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), "Product index output parent is unsafe")
        try:
            descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDONLY)
        except Exception:
            kernel32.CloseHandle(handle)
            raise
        try:
            opened = os.fstat(descriptor)
            if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
                raise ValueError("Product index output parent changed while opening")
            yield descriptor, parent
        finally:
            os.close(descriptor)
        return

    descriptor = _open_directory(parent, "Product index output parent")
    try:
        yield descriptor, parent
    finally:
        os.close(descriptor)


def _require_parent_identity(descriptor: int, parent: Path) -> None:
    try:
        current = parent.lstat()
    except OSError as error:
        raise ValueError("Product index output parent changed during publication") from error
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (
        opened.st_dev, opened.st_ino,
    ):
        raise ValueError("Product index output parent changed during publication")


def _read_parent_file(
    descriptor: int,
    parent: Path,
    name: str,
    *,
    max_bytes: int,
) -> bytes | None:
    _require_parent_identity(descriptor, parent)
    try:
        if _is_windows():
            try:
                (parent / name).lstat()
            except FileNotFoundError:
                return None
            file_descriptor, before = _open_regular_file(parent / name, "Product index output")
        else:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            file_descriptor = os.open(name, flags, dir_fd=descriptor)
            before = os.fstat(file_descriptor)
            if not stat.S_ISREG(before.st_mode):
                os.close(file_descriptor)
                raise ValueError("Product index output is not a regular file")
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ValueError("Product index output is missing or unsafe") from error
    try:
        if before.st_size > max_bytes:
            raise ValueError("Product index output exceeds its fixed bound")
        with os.fdopen(file_descriptor, "rb", closefd=False) as source:
            contents = source.read(before.st_size + 1)
        if len(contents) != before.st_size or _stat_identity(before) != _stat_identity(
            os.fstat(file_descriptor)
        ):
            raise ValueError("Product index output changed while reading")
        return contents
    finally:
        os.close(file_descriptor)


@contextmanager
def _held_parent_file(
    parent_descriptor: int,
    parent: Path,
    name: str,
) -> Iterator[tuple[int, os.stat_result]]:
    _require_parent_identity(parent_descriptor, parent)
    if _is_windows():
        import ctypes
        import msvcrt
        from ctypes import wintypes

        path = parent / name
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or bool(
            getattr(before, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
        ):
            raise ValueError("Product index output is missing or unsafe")
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        handle = create_file(
            str(path), 0x80000000, 0x0001, None, 3, 0x00200000, None,
        )
        if handle == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), "Product index output is unsafe")
        try:
            descriptor = msvcrt.open_osfhandle(
                int(handle), os.O_RDONLY | getattr(os, "O_BINARY", 0),
            )
        except Exception:
            kernel32.CloseHandle(handle)
            raise
    else:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        before = os.fstat(descriptor)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (
            opened.st_dev, opened.st_ino,
        ):
            raise ValueError("Product index output changed while opening")
        yield descriptor, opened
    finally:
        os.close(descriptor)


def _read_held_file(descriptor: int, identity: os.stat_result, max_bytes: int) -> bytes:
    before = os.fstat(descriptor)
    if _stat_identity(before) != _stat_identity(identity) or before.st_size > max_bytes:
        raise ValueError("Product index output changed during final verification")
    os.lseek(descriptor, 0, os.SEEK_SET)
    contents = b""
    while len(contents) <= before.st_size:
        chunk = os.read(descriptor, min(1024 * 1024, before.st_size + 1 - len(contents)))
        if not chunk:
            break
        contents += chunk
    if len(contents) != before.st_size or _stat_identity(before) != _stat_identity(
        os.fstat(descriptor)
    ):
        raise ValueError("Product index output changed during final verification")
    return contents


def _require_held_leaf_identity(
    parent_descriptor: int,
    parent: Path,
    name: str,
    descriptor: int,
    identity: os.stat_result,
) -> None:
    _require_parent_identity(parent_descriptor, parent)
    current = (parent / name).lstat() if _is_windows() else os.stat(
        name, dir_fd=parent_descriptor, follow_symlinks=False,
    )
    if (
        not stat.S_ISREG(current.st_mode)
        or (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino)
        or _stat_identity(os.fstat(descriptor)) != _stat_identity(identity)
    ):
        raise ValueError("Product index output changed during final verification")


def _publish_output(
    expected: bytes,
    descriptor: int,
    parent: Path,
    name: str,
    *,
    max_bytes: int,
) -> bool:
    _require_parent_identity(descriptor, parent)
    temporary_name = f".{name}-{secrets.token_hex(16)}"
    temporary_path = parent / temporary_name
    temporary_descriptor: int | None = None
    try:
        if _is_windows():
            temporary_descriptor = os.open(
                temporary_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o600,
            )
        else:
            temporary_descriptor = os.open(
                temporary_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o600,
                dir_fd=descriptor,
            )
        remaining = memoryview(expected)
        while remaining:
            written = os.write(temporary_descriptor, remaining)
            if written <= 0:
                raise ValueError("Immutable product index temporary output could not be written")
            remaining = remaining[written:]
        os.fsync(temporary_descriptor)
        os.close(temporary_descriptor)
        temporary_descriptor = None
        if _is_windows():
            os.link(temporary_path, parent / name, follow_symlinks=False)
        else:
            os.link(
                temporary_name,
                name,
                src_dir_fd=descriptor,
                dst_dir_fd=descriptor,
                follow_symlinks=False,
            )
    except FileExistsError:
        existing = _read_parent_file(descriptor, parent, name, max_bytes=max_bytes)
        if existing == expected:
            return False
        raise ValueError("Immutable product index output conflicts with existing bytes")
    except OSError as error:
        raise ValueError("Immutable product index output could not be published") from error
    finally:
        if temporary_descriptor is not None:
            os.close(temporary_descriptor)
        try:
            if _is_windows():
                temporary_path.unlink()
            else:
                os.unlink(temporary_name, dir_fd=descriptor)
        except FileNotFoundError:
            pass
    _require_parent_identity(descriptor, parent)
    return True


def write_signed_product_index(
    sources: Iterable[IndexEntrySource],
    *,
    repository: str,
    context: dict[str, Any],
    trust_domain: str,
    signing: dict[str, Any],
    producer: dict[str, Any],
    stable_history: VerifiedStableIndexHistory | None,
    private_key: Path,
    public_key: Path,
    manifest_path: Path,
    contract_objects: Mapping[str, Path] | None = None,
    native_runtime_objects: Mapping[str, Path] | None = None,
    native_runtime_projection=None,
    adapter_runtime_objects: Mapping[str, Path] | None = None,
    adapter_runtime_projection=None,
) -> dict[str, Any]:
    index = build_product_index(
        sources,
        repository=repository,
        context=context,
        trust_domain=trust_domain,
        signing=signing,
        producer=producer,
        stable_history=stable_history,
        contract_objects=contract_objects,
        native_runtime_objects=native_runtime_objects,
        native_runtime_projection=native_runtime_projection,
        adapter_runtime_objects=adapter_runtime_objects,
        adapter_runtime_projection=adapter_runtime_projection,
    )
    manifest = Path(os.path.abspath(manifest_path))
    signature = manifest.with_suffix(".sig")
    if signature == manifest or manifest.parent != signature.parent:
        raise ValueError("Product index manifest and signature paths must differ in one directory")

    with tempfile.TemporaryDirectory(prefix="codex-agent-product-index-") as temporary:
        root = Path(temporary).resolve()
        candidate_manifest = root / manifest.name
        candidate_public_key = root / "public-key.pub"
        candidate_public_key.write_bytes(read_regular_file_bytes(
            Path(public_key), max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True,
        ))
        write_canonical_json(candidate_manifest, index)
        candidate_signature = sign_manifest(candidate_manifest, Path(private_key), signing)
        verify_manifest_signature(
            candidate_manifest, candidate_signature, candidate_public_key, signing,
        )
        manifest_bytes = read_regular_file_bytes(candidate_manifest, max_bytes=_INDEX_LIMIT)
        signature_bytes = read_regular_file_bytes(candidate_signature, max_bytes=_SIGNATURE_LIMIT)

        with _held_output_parent(manifest.parent) as (descriptor, parent):
            existing_manifest = _read_parent_file(
                descriptor, parent, manifest.name, max_bytes=_INDEX_LIMIT,
            )
            existing_signature = _read_parent_file(
                descriptor, parent, signature.name, max_bytes=_SIGNATURE_LIMIT,
            )
            if existing_manifest not in (None, manifest_bytes) or existing_signature not in (
                None, signature_bytes,
            ):
                raise ValueError("Immutable product index output conflicts with existing bytes")
            manifest_published = _publish_output(
                manifest_bytes, descriptor, parent, manifest.name,
                max_bytes=_INDEX_LIMIT,
            )
            signature_published = _publish_output(
                signature_bytes, descriptor, parent, signature.name,
                max_bytes=_SIGNATURE_LIMIT,
            )
            with (
                _held_parent_file(descriptor, parent, manifest.name) as (
                    manifest_descriptor,
                    manifest_identity,
                ),
                _held_parent_file(descriptor, parent, signature.name) as (
                    signature_descriptor,
                    signature_identity,
                ),
            ):
                final_manifest = _read_held_file(
                    manifest_descriptor, manifest_identity, _INDEX_LIMIT,
                )
                final_signature = _read_held_file(
                    signature_descriptor, signature_identity, _SIGNATURE_LIMIT,
                )
                if final_manifest != manifest_bytes or final_signature != signature_bytes or \
                        load_canonical_json_bytes(final_manifest) != index:
                    raise ValueError("Published product index pair changed during final verification")
                verified_manifest = root / "published-product-index.json"
                verified_signature = root / "published-product-index.sig"
                verified_manifest.write_bytes(final_manifest)
                verified_signature.write_bytes(final_signature)
                verify_manifest_signature(
                    verified_manifest, verified_signature, candidate_public_key, signing,
                )
                if (
                    _read_held_file(manifest_descriptor, manifest_identity, _INDEX_LIMIT)
                    != final_manifest
                    or _read_held_file(signature_descriptor, signature_identity, _SIGNATURE_LIMIT)
                    != final_signature
                ):
                    raise ValueError("Published product index pair changed during final verification")
                _require_held_leaf_identity(
                    descriptor, parent, manifest.name, manifest_descriptor, manifest_identity,
                )
                _require_held_leaf_identity(
                    descriptor, parent, signature.name, signature_descriptor, signature_identity,
                )

    return {
        "status": "published" if manifest_published or signature_published else "existing",
        "index": index,
        "manifestPath": manifest,
        "signaturePath": signature,
        "manifestSha256": sha256_bytes(final_manifest),
        "signatureSha256": sha256_bytes(final_signature),
    }
