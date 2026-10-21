"""Create and verify external Contract Maven PGP sidecars over a finalized ZIP.

The protected caller authenticates the original Contract handoff and independently
pins the PGP key. This module never changes the deterministic Contract payload.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from .contract_model import CONTRACT_CHECKSUM_SUFFIXES, verify_contract_bundle
from .inventory import (
    publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_integer, require_relative_path, require_semver, require_sha256, sha256_bytes, sha256_file,
    snapshot_regular_tree, verified_zip_contents,
)


_LIMIT = 512 * 1024 * 1024


def _gpg(*arguments: str) -> str:
    result = subprocess.run(["gpg", *arguments], capture_output=True, timeout=60)
    if result.returncode:
        raise ValueError("Contract Maven detached PGP verification failed")
    return result.stdout.decode("utf-8", errors="strict")


def _payload_snapshot(payload: Path, root: Path) -> tuple[dict[str, Any], bytes, Path, list[str]]:
    """Verify the whole ZIP before exposing any primary to the signer."""
    original = read_regular_file_bytes(payload, max_bytes=_LIMIT, reject_symlink_parents=True)
    snapshot = root / payload.name
    snapshot.write_bytes(original)
    manifest = verify_contract_bundle(snapshot)
    primaries = [record for record in manifest["mavenFiles"] if record["role"] != "checksum"]
    extracted = root / "primaries"
    with ZipFile(snapshot) as archive:
        for record in primaries:
            path = record["path"]
            contents = archive.read(path)
            if len(contents) != record["bytes"] or sha256_bytes(contents) != record["sha256"]:
                raise ValueError("Contract Maven primary changed after bundle verification")
            destination = extracted / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(contents)
    if read_regular_file_bytes(payload, max_bytes=_LIMIT, reject_symlink_parents=True) != original:
        raise ValueError("Contract payload changed during snapshot verification")
    return manifest, original, extracted, [record["path"] for record in primaries]


def _pinned_key(path: Path, expected_sha256: str) -> bytes:
    raw = read_regular_file_bytes(path, max_bytes=1024 * 1024, reject_symlink_parents=True)
    if not raw or sha256_bytes(raw) != require_sha256(expected_sha256, "Contract PGP key digest"):
        raise ValueError("Contract PGP public key differs from pinned bytes")
    return raw


def _public_key_fingerprint(key: bytes, root: Path) -> str:
    home = root / "gnupg"
    home.mkdir(mode=0o700)
    verifier = root / "pgp-public-key.asc"
    verifier.write_bytes(key)
    _gpg("--homedir", str(home), "--batch", "--no-tty", "--import", str(verifier))
    listing = _gpg("--homedir", str(home), "--batch", "--no-tty", "--with-colons",
                   "--fingerprint", "--list-keys")
    lines = [line.split(":") for line in listing.splitlines()]
    fingerprints = [line[9] for line in lines if line[0] == "fpr"]
    if sum(line[0] == "pub" for line in lines) != 1 or not fingerprints or not re.fullmatch(
        r"[0-9A-F]{40}|[0-9A-F]{64}", fingerprints[0],
    ):
        raise ValueError("Contract PGP public key must contain one identifiable primary key")
    return fingerprints[0]


def verify_contract_phase10_maven(
    payload: Path, sidecar_directory: Path, pgp_public_key: Path,
    expected_pgp_key_sha256: str,
) -> dict[str, Any]:
    """Verify exact signatures/checksums against every bundle-declared primary."""
    payload, sidecar_directory, pgp_public_key = map(
        Path, (payload, sidecar_directory, pgp_public_key),
    )
    key = _pinned_key(pgp_public_key, expected_pgp_key_sha256)
    original_sidecars = regular_file_inventory(sidecar_directory)
    temporary_root = Path("/tmp") if Path("/tmp").is_dir() else Path(tempfile.gettempdir())
    with tempfile.TemporaryDirectory(prefix="ct-maven-",
                                     dir=temporary_root.resolve(strict=True)) as temporary:
        root = Path(temporary)
        manifest, original, primaries_root, primaries = _payload_snapshot(payload, root)
        captured = root / "sidecars"
        snapshot_regular_tree(sidecar_directory, captured)
        if regular_file_inventory(captured) != original_sidecars:
            raise ValueError("Contract Maven sidecar snapshot differs from its initial inventory")
        expected = {path + ".asc" + suffix for path in primaries
                    for suffix in ("", *CONTRACT_CHECKSUM_SUFFIXES)}
        if {record["relativePath"] for record in original_sidecars} != expected:
            raise ValueError("Contract Maven PGP sidecar inventory is incomplete or unexpected")
        for path in primaries:
            signature = read_regular_file_bytes(captured / (path + ".asc"), reject_symlink_parents=True)
            for suffix in CONTRACT_CHECKSUM_SUFFIXES:
                checksum = read_regular_file_bytes(captured / (path + ".asc" + suffix),
                                                   reject_symlink_parents=True)
                if checksum != (hashlib.new(suffix[1:], signature).hexdigest() + "\n").encode("ascii"):
                    raise ValueError("Contract Maven PGP signature checksum mismatch")
        fingerprint = _public_key_fingerprint(key, root)
        for path in primaries:
            _gpg("--homedir", str(root / "gnupg"), "--batch", "--no-tty", "--verify",
                 str(captured / (path + ".asc")), str(primaries_root / path))
        if (read_regular_file_bytes(payload, max_bytes=_LIMIT, reject_symlink_parents=True) != original
                or regular_file_inventory(sidecar_directory) != original_sidecars
                or _pinned_key(pgp_public_key, expected_pgp_key_sha256) != key):
            raise ValueError("Contract Maven payload, sidecars, or key changed during verification")
        return {"schemaVersion": 2, "product": "contract",
                "contractVersion": manifest["contractVersion"],
                "payloadSha256": sha256_bytes(original),
                "payloadBytes": len(original), "sidecarFiles": original_sidecars,
                "mavenFiles": [{"relativePath": row["path"], "bytes": row["bytes"],
                                "sha256": row["sha256"]} for row in manifest["mavenFiles"]],
                "pgpPublicKey": {"bytes": len(key), "sha256": sha256_bytes(key),
                                 "fingerprint": fingerprint}}


def _central_files(verified_maven: dict) -> tuple[str, list[dict]]:
    """Project an already authenticated Maven inventory, not a new trust authority."""
    if verified_maven["schemaVersion"] != 2 or verified_maven["product"] != "contract":
        raise ValueError("Central envelope requires the current verified Contract Maven inventory")
    version = require_semver(verified_maven["contractVersion"], "Contract Central version")
    records = central_maven_files(verified_maven["mavenFiles"], verified_maven["sidecarFiles"])
    return f"codex-agent-contract-{version}-central.zip", records


def central_maven_files(maven_files: list[dict], sidecar_files: list[dict]) -> list[dict]:
    """Shared release-only projection; callers authenticate product/signature bytes."""
    records = []
    for row in [*maven_files, *[
            row for row in sidecar_files if row["relativePath"].endswith(".asc")]]:
        path = require_relative_path(row["relativePath"], "Central input")
        if not path.startswith("maven/"):
            raise ValueError("Central input is outside Maven")
        require_integer(row["bytes"], "Central input length", 1)
        require_sha256(row["sha256"], "Central input digest")
        records.append({**row, "relativePath": path.removeprefix("maven/")})
    if not records or len({row["relativePath"] for row in records}) != len(records):
        raise ValueError("Central input inventory is empty or duplicated")
    # Stored ZIP headers have a known size; reject before allocating the output.
    if len(records) > 16_384 or any(row["bytes"] > _LIMIT for row in records) or 22 + sum(
            row["bytes"] + 76 + 2 * len(row["relativePath"].encode("utf-8")) for row in records
    ) >= 1_000_000_000:
        raise ValueError("Central envelope exceeds the existing upload limit")
    return sorted(records, key=lambda row: row["relativePath"])


def verify_contract_central_bundle(bundle: Path, verified_maven: dict) -> dict:
    """Verify the release-only envelope against freshly verified primaries/signatures."""
    name, expected = _central_files(verified_maven)
    if bundle.name != name:
        raise ValueError("Contract Central filename differs from its release identity")
    return verify_central_bundle(bundle, expected)


def verify_central_bundle(bundle: Path, expected: list[dict]) -> dict:
    """Shared bounded verification of an already-finalized release envelope."""
    # The original verified inventory supplies the exact semantic closure; retain
    # no member bodies and do not extract, copy, sign, or repack this envelope.
    actual, _, identity = verified_zip_contents(
        bundle, retained_paths=(), canonical_stored=True, max_archive_bytes=1_000_000_000 - 1,
        max_total_bytes=1_000_000_000 - 1, max_members=16_384, max_entry_bytes=_LIMIT,
    )
    if actual != expected:
        raise ValueError("Central members differ from verified Maven bytes")
    return {"fileName": bundle.name, **identity, "files": actual}


def write_central_bundle(bundle: Path, records: list[dict], read_member) -> None:
    """Enclose exact selected bytes once; the caller verifies before publication."""
    with ZipFile(bundle, "x", compression=ZIP_STORED) as archive:
        for row in records:
            contents = read_member("maven/" + row["relativePath"])
            if len(contents) != row["bytes"] or sha256_bytes(contents) != row["sha256"]:
                raise ValueError("Central input changed after verification")
            info = ZipInfo(row["relativePath"], (1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, contents)


def produce_contract_central_bundle(
    payload: Path, sidecars: Path, destination: Path, verified_maven: dict,
) -> dict:
    """Phase10 only: enclose exact verified Maven bytes once, outside the payload.

    The protected caller must first obtain verified_maven from the existing full
    PGP verifier. This writer does not grant release or original-producer trust.
    """
    payload, sidecars, destination = map(Path, (payload, sidecars, destination))
    name, records = _central_files(verified_maven)
    output = destination.resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract Central destination already exists")
    for source in (payload, sidecars):
        source = source.resolve(strict=True)
        if output == source or output in source.parents or source in output.parents:
            raise ValueError("Contract Central destination overlaps a verified input")
    # One bounded in-memory input snapshot, no extracted Maven tree or duplicate
    # staged primaries. Signatures are tiny and read only when consumed.
    raw = read_regular_file_bytes(payload, max_bytes=_LIMIT, reject_symlink_parents=True)
    if len(raw) != verified_maven["payloadBytes"] or sha256_bytes(raw) != verified_maven["payloadSha256"]:
        raise ValueError("Contract Central payload differs from verified bytes")
    with tempfile.TemporaryDirectory(prefix="ct-central-", dir=destination.parent) as temporary:
        prepared = Path(temporary)
        with ZipFile(io.BytesIO(raw)) as source:
            write_central_bundle(prepared / name, records, lambda path: (
                read_regular_file_bytes(sidecars / path, max_bytes=1024 * 1024,
                                        reject_symlink_parents=True)
                if path.endswith(".asc") else source.read(path)))
        result = verify_contract_central_bundle(prepared / name, verified_maven)
        if (sha256_file(payload, reject_symlink_parents=True) != verified_maven["payloadSha256"]
                or regular_file_inventory(sidecars) != verified_maven["sidecarFiles"]):
            raise ValueError("Contract Central inputs changed before publication")
        publish_regular_tree(prepared, destination, expected_inventory=[{
            "relativePath": name, "bytes": result["bytes"], "sha256": result["sha256"]}])
    return result


def produce_contract_phase10_maven_sidecars(
    payload: Path, sidecar_directory: Path, pgp_public_key: Path,
    expected_pgp_key_sha256: str, signing_home: Path,
    signing_fingerprint: str, passphrase: str,
) -> dict[str, Any]:
    """Sign only authenticated private-snapshot primaries; publish once."""
    payload, sidecar_directory, pgp_public_key, signing_home = map(
        Path, (payload, sidecar_directory, pgp_public_key, signing_home),
    )
    if sidecar_directory.exists() or sidecar_directory.is_symlink():
        raise ValueError("Contract Maven sidecar output already exists")
    if not re.fullmatch(r"[0-9A-F]{40}|[0-9A-F]{64}", signing_fingerprint):
        raise ValueError("Contract signing fingerprint must be an uppercase PGP fingerprint")
    signing_home.resolve(strict=True)
    key = _pinned_key(pgp_public_key, expected_pgp_key_sha256)
    with tempfile.TemporaryDirectory(prefix="ct-sign-", dir=sidecar_directory.parent) as temporary:
        root = Path(temporary)
        _, original, primaries_root, primaries = _payload_snapshot(payload, root)
        temporary_root = Path("/tmp") if Path("/tmp").is_dir() else Path(tempfile.gettempdir())
        with tempfile.TemporaryDirectory(prefix="ct-key-",
                                         dir=temporary_root.resolve(strict=True)) as preflight:
            if _public_key_fingerprint(key, Path(preflight)) != signing_fingerprint:
                raise ValueError("Contract Maven signer differs from pinned PGP key")
        sidecars = root / "sidecars"
        sidecars.mkdir()
        for path in primaries:
            signature = sidecars / (path + ".asc")
            signature.parent.mkdir(parents=True, exist_ok=True)
            signed = subprocess.run(
                ["gpg", "--homedir", str(signing_home), "--batch", "--no-tty",
                 "--pinentry-mode", "loopback", "--passphrase-fd", "0",
                 "--local-user", signing_fingerprint, "--armor", "--detach-sign",
                 "--output", str(signature), str(primaries_root / path)],
                input=passphrase.encode("utf-8"), capture_output=True, timeout=60,
            )
            if signed.returncode:
                raise ValueError("Contract Maven PGP signing failed")
            raw = read_regular_file_bytes(signature, reject_symlink_parents=True)
            for suffix in CONTRACT_CHECKSUM_SUFFIXES:
                signature.with_name(signature.name + suffix).write_bytes(
                    (hashlib.new(suffix[1:], raw).hexdigest() + "\n").encode("ascii"),
                )
        result = verify_contract_phase10_maven(root / payload.name, sidecars,
                                               pgp_public_key, expected_pgp_key_sha256)
        if result["pgpPublicKey"]["fingerprint"] != signing_fingerprint:
            raise ValueError("Contract Maven signer differs from pinned PGP key")
        if (read_regular_file_bytes(payload, max_bytes=_LIMIT, reject_symlink_parents=True) != original
                or _pinned_key(pgp_public_key, expected_pgp_key_sha256) != key
                or regular_file_inventory(sidecars) != result["sidecarFiles"]):
            raise ValueError("Contract Maven input or verified sidecars changed before publication")
        publish_regular_tree(sidecars, sidecar_directory, expected_inventory=result["sidecarFiles"])
        if regular_file_inventory(sidecar_directory) != result["sidecarFiles"]:
            raise ValueError("Contract Maven published sidecars differ from verified bytes")
        return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("payload", "sidecars", "pgp-public-key", "pgp-public-key-sha256",
                   "signing-home", "signing-fingerprint"):
        parser.add_argument(f"--{option}", required=True)
    args = parser.parse_args(argv)
    result = produce_contract_phase10_maven_sidecars(
        Path(args.payload), Path(args.sidecars), Path(args.pgp_public_key),
        args.pgp_public_key_sha256, Path(args.signing_home),
        args.signing_fingerprint, sys.stdin.read(),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
