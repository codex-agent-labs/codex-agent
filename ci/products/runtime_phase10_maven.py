"""Verify Runtime Maven release sidecars without changing reusable payload bytes.

The caller must independently authenticate the aggregate and pin the PGP public
key digest. This check does not grant protected-run or publication authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any

from .aggregate import validate_runtime_aggregate
from .contract_model import CONTRACT_CHECKSUM_SUFFIXES
from .inventory import (
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_sha256, sha256_bytes, snapshot_regular_tree,
)
from .runtime_maven import validate_runtime_maven_publications


def _run_gpg(*arguments: str) -> str:
    result = subprocess.run(
        ["gpg", *arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=60,
    )
    if result.returncode:
        raise ValueError("Runtime Maven detached PGP verification failed")
    return result.stdout.decode("utf-8", errors="strict")


def _validated_payload(payload: Path, manifest_path: Path) -> tuple[dict[str, Any], bytes, list[str]]:
    """Authenticate the complete reusable Maven closure before any signing."""
    manifest_bytes = read_regular_file_bytes(
        manifest_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    manifest = validate_runtime_aggregate(load_canonical_json_bytes(manifest_bytes))
    expected_name = f"codex-agent-runtime-{manifest['runtimeVersion']}-manifest.json"
    if manifest_path.name != expected_name:
        raise ValueError("Runtime aggregate manifest filename differs from release version")
    records = manifest["runtimeMavenFiles"]
    expected_payload = {expected_name: {"relativePath": expected_name, "bytes": len(manifest_bytes),
                                       "sha256": sha256_bytes(manifest_bytes)}}
    contents = {}
    for record in records:
        path = record["path"]
        contents[path] = read_regular_file_bytes(payload / path, reject_symlink_parents=True)
        expected_payload[path] = {"relativePath": path, "bytes": record["bytes"],
                                  "sha256": record["sha256"]}
    if regular_file_inventory(payload) != sorted(expected_payload.values(),
                                                 key=lambda item: item["relativePath"]):
        raise ValueError("Runtime aggregate payload has missing, extra, or changed Maven bytes")
    validate_runtime_maven_publications(
        manifest["runtimeVersion"], manifest["contract"]["version"], records, contents,
    )
    primaries = [record["path"] for record in records
                 if not record["path"].endswith(CONTRACT_CHECKSUM_SUFFIXES)]
    return manifest, manifest_bytes, primaries


def produce_runtime_phase10_maven_sidecars(
    payload_directory: Path,
    aggregate_manifest: Path,
    sidecar_directory: Path,
    pgp_public_key: Path,
    expected_pgp_key_sha256: str,
    signing_home: Path,
    signing_fingerprint: str,
    passphrase: str,
) -> dict[str, Any]:
    """Sign finalized primaries externally; never rewrite reusable Maven bytes.

    The protected caller supplies an isolated GPG home containing its secret key.
    This local producer does not establish protected-run or original-upload trust.
    """
    payload_directory = Path(payload_directory)
    aggregate_manifest = Path(aggregate_manifest)
    sidecar_directory = Path(sidecar_directory)
    pgp_public_key = Path(pgp_public_key)
    signing_home = Path(signing_home)
    expected_pgp_key_sha256 = require_sha256(expected_pgp_key_sha256, "Runtime PGP key digest")
    if not re.fullmatch(r"[0-9A-F]{40}|[0-9A-F]{64}", signing_fingerprint):
        raise ValueError("Runtime signing fingerprint must be an uppercase PGP fingerprint")
    if aggregate_manifest.parent.resolve(strict=True) != payload_directory.resolve(strict=True):
        raise ValueError("Runtime aggregate manifest must be in the payload root")
    if sidecar_directory.exists() or sidecar_directory.is_symlink():
        raise ValueError("Runtime Maven sidecar output already exists")
    if sidecar_directory.resolve().is_relative_to(payload_directory.resolve(strict=True)):
        raise ValueError("Runtime Maven sidecars must be outside reusable payload")
    signing_home.resolve(strict=True)
    source_inventory = regular_file_inventory(payload_directory)
    key = read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024,
                                  reject_symlink_parents=True)
    if not key or sha256_bytes(key) != expected_pgp_key_sha256:
        raise ValueError("Runtime PGP public key differs from pinned bytes")

    with tempfile.TemporaryDirectory(prefix="rt-sign-",
                                     dir=sidecar_directory.parent) as temporary:
        root = Path(temporary)
        payload = root / "payload"
        sidecars = root / "sidecars"
        snapshot_regular_tree(payload_directory, payload)
        if regular_file_inventory(payload) != source_inventory:
            raise ValueError("Runtime Maven snapshot differs from its initial inputs")
        _, _, primaries = _validated_payload(payload, payload / aggregate_manifest.name)
        sidecars.mkdir()
        for path in primaries:
            signature = sidecars / (path + ".asc")
            signature.parent.mkdir(parents=True, exist_ok=True)
            signed = subprocess.run(
                ["gpg", "--homedir", str(signing_home), "--batch", "--no-tty",
                 "--pinentry-mode", "loopback", "--passphrase-fd", "0",
                 "--local-user", signing_fingerprint, "--armor", "--detach-sign",
                 "--output", str(signature), str(payload / path)],
                input=passphrase.encode("utf-8"), stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False, timeout=60,
            )
            if signed.returncode:
                raise ValueError("Runtime Maven PGP signing failed")
            signed_bytes = read_regular_file_bytes(signature, reject_symlink_parents=True)
            for suffix in CONTRACT_CHECKSUM_SUFFIXES:
                signature.with_name(signature.name + suffix).write_bytes(
                    (hashlib.new(suffix[1:], signed_bytes).hexdigest() + "\n").encode("ascii"),
                )
        result = verify_runtime_phase10_maven(
            payload, payload / aggregate_manifest.name, sidecars,
            pgp_public_key, expected_pgp_key_sha256,
        )
        if result["pgpPublicKey"]["fingerprint"] != signing_fingerprint:
            raise ValueError("Runtime Maven signer differs from pinned PGP key")
        if (regular_file_inventory(payload_directory) != source_inventory
                or read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024,
                                           reject_symlink_parents=True) != key):
            raise ValueError("Runtime Maven payload or verifier key changed during signing")
        if sidecar_directory.exists() or sidecar_directory.is_symlink():
            raise ValueError("Runtime Maven sidecar output already exists")
        if regular_file_inventory(sidecars) != result["sidecarFiles"]:
            raise ValueError("Runtime Maven verified sidecars changed before publication")
        publish_regular_tree(sidecars, sidecar_directory)
        if regular_file_inventory(sidecar_directory) != result["sidecarFiles"]:
            raise ValueError("Runtime Maven published sidecars differ from verified bytes")
        return result


def verify_runtime_phase10_maven(
    payload_directory: Path,
    aggregate_manifest: Path,
    sidecar_directory: Path,
    pgp_public_key: Path,
    expected_pgp_key_sha256: str,
) -> dict[str, Any]:
    """Check the exact aggregate-owned Maven bytes and detached release files.

    The sidecar tree contains one `.asc` and four checksums per Maven primary.
    Existing product-stage primary checksums are verified and selected, never
    regenerated. Signature checksums are external release-control bytes.
    """
    payload_directory = Path(payload_directory)
    aggregate_manifest = Path(aggregate_manifest)
    sidecar_directory = Path(sidecar_directory)
    pgp_public_key = Path(pgp_public_key)
    expected_pgp_key_sha256 = require_sha256(expected_pgp_key_sha256, "Runtime PGP key digest")
    key = read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024, reject_symlink_parents=True)
    if not key or sha256_bytes(key) != expected_pgp_key_sha256:
        raise ValueError("Runtime PGP public key differs from pinned bytes")
    if aggregate_manifest.parent.resolve(strict=True) != payload_directory.resolve(strict=True):
        raise ValueError("Runtime aggregate manifest must be in the payload root")

    original_payload = regular_file_inventory(payload_directory)
    original_sidecars = regular_file_inventory(sidecar_directory)
    # Keep the isolated GPG home short enough for Unix agent socket paths.
    temporary_root = Path("/tmp") if Path("/tmp").is_dir() else Path(tempfile.gettempdir())
    with tempfile.TemporaryDirectory(prefix="rt-maven-",
                                     dir=temporary_root.resolve(strict=True)) as temporary:
        root = Path(temporary)
        payload = root / "payload"
        sidecars = root / "sidecars"
        snapshot_regular_tree(payload_directory, payload)
        snapshot_regular_tree(sidecar_directory, sidecars)
        if (regular_file_inventory(payload) != original_payload
                or regular_file_inventory(sidecars) != original_sidecars):
            raise ValueError("Runtime Phase-10 Maven snapshot differs from its initial inputs")
        copied_key = root / "pgp-public-key.asc"
        copied_key.write_bytes(key)
        manifest, manifest_bytes, primaries = _validated_payload(
            payload, payload / aggregate_manifest.name,
        )
        expected_sidecars = {path + ".asc" + suffix for path in primaries
                             for suffix in ("", *CONTRACT_CHECKSUM_SUFFIXES)}
        sidecar_inventory = regular_file_inventory(sidecars)
        if {record["relativePath"] for record in sidecar_inventory} != expected_sidecars:
            raise ValueError("Runtime Maven PGP signature inventory is incomplete or unexpected")
        for path in primaries:
            signature = read_regular_file_bytes(sidecars / (path + ".asc"), reject_symlink_parents=True)
            for suffix in CONTRACT_CHECKSUM_SUFFIXES:
                checksum = read_regular_file_bytes(
                    sidecars / (path + ".asc" + suffix), reject_symlink_parents=True,
                )
                if checksum != (hashlib.new(suffix[1:], signature).hexdigest() + "\n").encode("ascii"):
                    raise ValueError("Runtime Maven PGP signature checksum differs from its signature")

        home = root / "gnupg"
        home.mkdir(mode=0o700)
        _run_gpg("--homedir", str(home), "--batch", "--no-tty", "--import", str(copied_key))
        listing = _run_gpg("--homedir", str(home), "--batch", "--no-tty", "--with-colons",
                           "--fingerprint", "--list-keys")
        lines = [line.split(":") for line in listing.splitlines()]
        fingerprints = [line[9] for line in lines if line[0] == "fpr"]
        if sum(line[0] == "pub" for line in lines) != 1 or not fingerprints or not re.fullmatch(
            r"[0-9A-F]{40}|[0-9A-F]{64}", fingerprints[0],
        ):
            raise ValueError("Runtime PGP public key must contain one identifiable primary key")
        for path in primaries:
            _run_gpg("--homedir", str(home), "--batch", "--no-tty", "--verify",
                     str(sidecars / (path + ".asc")), str(payload / path))
        if (regular_file_inventory(payload_directory) != original_payload
                or regular_file_inventory(sidecar_directory) != original_sidecars
                or read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024,
                                           reject_symlink_parents=True) != key):
            raise ValueError("Runtime Phase-10 Maven inputs changed during verification")
        return {
            "schemaVersion": 1,
            "product": "runtime",
            "runtimeVersion": manifest["runtimeVersion"],
            "manifestSha256": sha256_bytes(manifest_bytes),
            "payloadFiles": original_payload,
            "sidecarFiles": original_sidecars,
            "pgpPublicKey": {"bytes": len(key), "sha256": expected_pgp_key_sha256,
                             "fingerprint": fingerprints[0]},
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Produce external Phase-10 Runtime Maven PGP sidecars; read passphrase from stdin.",
    )
    for option in ("payload", "aggregate-manifest", "sidecars", "pgp-public-key",
                   "pgp-public-key-sha256", "signing-home", "signing-fingerprint"):
        parser.add_argument(f"--{option}", required=True)
    arguments = parser.parse_args(argv)
    result = produce_runtime_phase10_maven_sidecars(
        Path(arguments.payload), Path(arguments.aggregate_manifest), Path(arguments.sidecars),
        Path(arguments.pgp_public_key), arguments.pgp_public_key_sha256,
        Path(arguments.signing_home), arguments.signing_fingerprint, sys.stdin.read(),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
