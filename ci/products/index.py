from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import stat
import subprocess
import tempfile
from typing import Any, Iterable, Iterator

from .aggregate import validate_product_index, verify_immutable_product_indexes
from .inventory import (
    _is_windows,
    _open_directory,
    _open_regular_file,
    _stat_identity,
    _windows_directory_path,
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
from .signatures import (
    load_keyring,
    public_key_for_metadata,
    sign_manifest,
    verify_manifest_signature,
)


_INDEX_LIMIT = 16 * 1024 * 1024
_SIGNATURE_LIMIT = 1024 * 1024
_HISTORY_TOKEN = object()


@dataclass(frozen=True, slots=True)
class IndexEntrySource:
    receipt_bytes: bytes
    artifact_path: str


@dataclass(frozen=True, slots=True)
class SignedProductIndex:
    manifest: Path
    signature: Path


@dataclass(frozen=True, slots=True)
class VerifiedStableIndexHistory:
    _repository: str
    _index_bytes: tuple[bytes, ...]
    _token: object


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


def verify_stable_index_history(
    sources: Iterable[SignedProductIndex],
    *,
    repository: str,
    keyring_path: Path,
    keys_directory: Path,
) -> VerifiedStableIndexHistory:
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
            verify_immutable_product_indexes(prior, index)
        indexes.append(index)
        verified.append(contents)
    if len(tags) != len(set(tags)) or set(tags) != set(authoritative_refs):
        raise ValueError(
            "Stable product-index sources do not match the current protected stable-tag inventory"
        )
    return VerifiedStableIndexHistory(repository, tuple(verified), _HISTORY_TOKEN)


def _entry(
    source: IndexEntrySource,
    *,
    repository: str,
    trust_domain: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(source, IndexEntrySource) or type(source.receipt_bytes) is not bytes:
        raise ValueError("Product index entry source is invalid")
    receipt = validate_phase_receipt(load_canonical_json_bytes(source.receipt_bytes))
    if receipt["trustDomain"] != trust_domain:
        raise ValueError("Product index receipt trust domain does not match the index")
    if receipt["producer"]["repository"] != repository:
        raise ValueError("Product index receipt repository does not match the index")
    artifact_path = require_relative_path(source.artifact_path, "Product index entry artifact path")
    artifacts = [
        output for output in receipt["outputs"] if output["relativePath"] == artifact_path
    ]
    if len(artifacts) != 1:
        raise ValueError("Product index artifact must name exactly one receipt output")
    artifact = artifacts[0]
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
    }, receipt)


def build_product_index(
    sources: Iterable[IndexEntrySource],
    *,
    repository: str,
    context: dict[str, Any],
    trust_domain: str,
    signing: dict[str, Any],
    producer: dict[str, Any],
    stable_history: VerifiedStableIndexHistory | None,
) -> dict[str, Any]:
    pairs = sorted(
        (_entry(source, repository=repository, trust_domain=trust_domain) for source in sources),
        key=lambda pair: pair[0]["buildKey"],
    )
    entries = [entry for entry, _ in pairs]
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
            for _, receipt in pairs
        ):
            raise ValueError("Pull-request product index contains a receipt from another context")
    elif any(receipt["producer"]["event"] != "push" for _, receipt in pairs):
        raise ValueError("Release product index contains a non-push receipt")
    if index["context"]["kind"] == "stable":
        stable_index_identity(index)
        if not isinstance(stable_history, VerifiedStableIndexHistory) or \
                stable_history._token is not _HISTORY_TOKEN or \
                stable_history._repository != repository:
            raise ValueError("Stable product index requires explicit authenticated history")
        for contents in stable_history._index_bytes:
            verify_immutable_product_indexes(
                validate_product_index(load_canonical_json_bytes(contents)), index,
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
) -> dict[str, Any]:
    index = build_product_index(
        sources,
        repository=repository,
        context=context,
        trust_domain=trust_domain,
        signing=signing,
        producer=producer,
        stable_history=stable_history,
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
