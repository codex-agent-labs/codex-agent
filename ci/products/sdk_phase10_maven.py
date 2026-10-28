"""External Phase-10 PGP sidecars for one authenticated SDK Maven package stage.

The caller authenticates the selected original receipt and campaign authority.
This module verifies package-stage bytes, not original host execution or release
admission, and never changes the reusable stage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from .inventory import (
    _open_regular_file, load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_regular_directory, require_semver, require_sha256,
    sha256_bytes, snapshot_regular_tree,
)
from .contract_phase10_maven import central_maven_files, verify_central_bundle, write_central_bundle
from .receipt import validate_phase_receipt, verify_output_manifest_identity
from .registry import PhaseId, phase_targets
from .sdk_maven import CHECKSUMS, COMPONENT_ARTIFACTS, MAVEN_GROUPS, verify_packaged_sdk_maven_repository


def _run_gpg(*arguments: str, input_bytes: bytes | None = None) -> str:
    result = subprocess.run(
        ["gpg", *arguments], input=input_bytes, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False, timeout=60,
    )
    if result.returncode:
        raise ValueError("SDK Maven PGP operation failed")
    return result.stdout.decode("utf-8", errors="strict")


def _stage(stage: Path, receipt_bytes: bytes) -> tuple[dict, list[str]]:
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    component = receipt["component"]
    if (receipt["product"] != "sdk" or receipt["phase"] != "package"
            or component not in MAVEN_GROUPS
            or receipt["target"] not in phase_targets(PhaseId("sdk", component, "package"))):
        raise ValueError("SDK Maven sidecars require an exact package-stage receipt")
    manifest = verify_output_manifest_identity(
        stage, "sdk", component, "package", receipt["target"], receipt["productVersion"],
    )
    if manifest["outputs"] != receipt["outputs"]:
        raise ValueError("SDK Maven stage differs from its selected receipt")
    compatibility = stage / "outputs/evidence/sdk-compatibility.json"
    verify_packaged_sdk_maven_repository(
        stage / "outputs/maven", compatibility,
        MAVEN_GROUPS[component], receipt["productVersion"], component,
    )
    paths = [record["relativePath"] for record in regular_file_inventory(stage / "outputs/maven")]
    primaries = [path for path in paths if not path.endswith(tuple(CHECKSUMS))]
    if not primaries:
        raise ValueError("SDK Maven package has no primaries")
    return receipt, primaries


def _key(path: Path, expected_sha256: str) -> bytes:
    key = read_regular_file_bytes(path, max_bytes=1024 * 1024, reject_symlink_parents=True)
    if not key or sha256_bytes(key) != expected_sha256:
        raise ValueError("SDK PGP public key differs from pinned bytes")
    return key


def verify_sdk_phase10_maven(
    stage: Path, receipt_path: Path, sidecar_directory: Path,
    pgp_public_key: Path, expected_pgp_key_sha256: str,
) -> dict:
    """Verify exact external `.asc` and four checksum files per Maven primary."""
    stage, receipt_path, sidecar_directory, pgp_public_key = map(
        Path, (stage, receipt_path, sidecar_directory, pgp_public_key),
    )
    expected_pgp_key_sha256 = require_sha256(expected_pgp_key_sha256, "SDK PGP key digest")
    key = _key(pgp_public_key, expected_pgp_key_sha256)
    receipt_bytes = read_regular_file_bytes(
        receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    source_stage, source_sidecars = regular_file_inventory(stage), regular_file_inventory(sidecar_directory)
    temporary_root = Path("/tmp") if Path("/tmp").is_dir() else Path(tempfile.gettempdir())
    with tempfile.TemporaryDirectory(prefix="sdk-maven-", dir=temporary_root.resolve(strict=True)) as temporary:
        root = Path(temporary)
        payload, sidecars = root / "stage", root / "sidecars"
        snapshot_regular_tree(stage, payload)
        snapshot_regular_tree(sidecar_directory, sidecars)
        if (regular_file_inventory(payload) != source_stage
                or regular_file_inventory(sidecars) != source_sidecars):
            raise ValueError("SDK Maven snapshot differs from its initial inputs")
        receipt, primaries = _stage(payload, receipt_bytes)
        expected = {path + ".asc" + suffix for path in primaries for suffix in ("", *CHECKSUMS)}
        if {item["relativePath"] for item in source_sidecars} != expected:
            raise ValueError("SDK Maven sidecar inventory is incomplete or unexpected")
        for path in primaries:
            signature = read_regular_file_bytes(sidecars / (path + ".asc"), reject_symlink_parents=True)
            for suffix, algorithm in CHECKSUMS.items():
                checksum = read_regular_file_bytes(
                    sidecars / (path + ".asc" + suffix), reject_symlink_parents=True,
                )
                if checksum != (hashlib.new(algorithm, signature).hexdigest() + "\n").encode("ascii"):
                    raise ValueError("SDK Maven signature checksum differs from signature")
        copied_key = root / "public.asc"
        copied_key.write_bytes(key)
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
            raise ValueError("SDK PGP public key must contain one identifiable primary key")
        for path in primaries:
            _run_gpg("--homedir", str(home), "--batch", "--no-tty", "--verify",
                     str(sidecars / (path + ".asc")), str(payload / "outputs/maven" / path))
        if (regular_file_inventory(stage) != source_stage
                or regular_file_inventory(sidecar_directory) != source_sidecars
                or read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != receipt_bytes
                or _key(pgp_public_key, expected_pgp_key_sha256) != key):
            raise ValueError("SDK Maven source changed during verification")
        return {
            "schemaVersion": 1, "product": "sdk", "component": receipt["component"],
            "sdkVersion": receipt["productVersion"], "receiptSha256": sha256_bytes(receipt_bytes),
            "stageFiles": source_stage, "sidecarFiles": source_sidecars,
            "pgpPublicKey": {"bytes": len(key), "sha256": expected_pgp_key_sha256,
                             "fingerprint": fingerprints[0]},
        }


def produce_sdk_phase10_maven_sidecars(
    stage: Path, receipt_path: Path, sidecar_directory: Path,
    pgp_public_key: Path, expected_pgp_key_sha256: str,
    signing_home: Path, signing_fingerprint: str, passphrase: str,
) -> dict:
    """Sign selected finalized Maven primaries outside the reusable stage."""
    stage, receipt_path, sidecar_directory, pgp_public_key, signing_home = map(
        Path, (stage, receipt_path, sidecar_directory, pgp_public_key, signing_home),
    )
    expected_pgp_key_sha256 = require_sha256(expected_pgp_key_sha256, "SDK PGP key digest")
    if not re.fullmatch(r"[0-9A-F]{40}|[0-9A-F]{64}", signing_fingerprint):
        raise ValueError("SDK signing fingerprint must be uppercase PGP fingerprint")
    if sidecar_directory.exists() or sidecar_directory.is_symlink():
        raise ValueError("SDK Maven sidecar output already exists")
    if sidecar_directory.resolve().is_relative_to(stage.resolve(strict=True)):
        raise ValueError("SDK Maven sidecars must be outside reusable stage")
    signing_home.resolve(strict=True)
    key = _key(pgp_public_key, expected_pgp_key_sha256)
    receipt_bytes = read_regular_file_bytes(
        receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    source_stage = regular_file_inventory(stage)
    with tempfile.TemporaryDirectory(prefix="sdk-sign-", dir=sidecar_directory.parent) as temporary:
        root = Path(temporary)
        payload, sidecars = root / "stage", root / "sidecars"
        snapshot_regular_tree(stage, payload)
        if regular_file_inventory(payload) != source_stage:
            raise ValueError("SDK Maven snapshot differs from its initial inputs")
        _, primaries = _stage(payload, receipt_bytes)  # Authenticate before private-key use.
        sidecars.mkdir()
        for path in primaries:
            signature = sidecars / (path + ".asc")
            signature.parent.mkdir(parents=True, exist_ok=True)
            _run_gpg(
                "--homedir", str(signing_home), "--batch", "--no-tty",
                "--pinentry-mode", "loopback", "--passphrase-fd", "0",
                "--local-user", signing_fingerprint, "--armor", "--detach-sign",
                "--output", str(signature), str(payload / "outputs/maven" / path),
                input_bytes=passphrase.encode("utf-8"),
            )
            signed = read_regular_file_bytes(signature, reject_symlink_parents=True)
            for suffix, algorithm in CHECKSUMS.items():
                signature.with_name(signature.name + suffix).write_bytes(
                    (hashlib.new(algorithm, signed).hexdigest() + "\n").encode("ascii"),
                )
        result = verify_sdk_phase10_maven(
            payload, receipt_path, sidecars, pgp_public_key, expected_pgp_key_sha256,
        )
        if result["pgpPublicKey"]["fingerprint"] != signing_fingerprint:
            raise ValueError("SDK Maven signer differs from pinned PGP key")
        if (regular_file_inventory(stage) != source_stage
                or read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != receipt_bytes
                or _key(pgp_public_key, expected_pgp_key_sha256) != key):
            raise ValueError("SDK Maven source changed during signing")
        if sidecar_directory.exists() or sidecar_directory.is_symlink():
            raise ValueError("SDK Maven sidecar output already exists")
        if regular_file_inventory(sidecars) != result["sidecarFiles"]:
            raise ValueError("SDK Maven verified sidecars changed before publication")
        publish_regular_tree(sidecars, sidecar_directory,
                             expected_inventory=result["sidecarFiles"])
        if regular_file_inventory(sidecar_directory) != result["sidecarFiles"]:
            raise ValueError("SDK Maven published sidecars differ from verified bytes")
        return result


def _central_layout(verified_maven: list[dict]) -> tuple[list[dict], dict]:
    """Project all three freshly verified packages into the existing SDK shards."""
    if (len(verified_maven) != 3
            or {row["component"] for row in verified_maven} != set(MAVEN_GROUPS)
            or any(row["schemaVersion"] != 1 or row["product"] != "sdk" for row in verified_maven)
            or len({row["sdkVersion"] for row in verified_maven}) != 1):
        raise ValueError("SDK Central requires exactly three verified same-version packages")
    version = require_semver(verified_maven[0]["sdkVersion"], "SDK Central version")
    grouped = {name: [] for name in ("main", "ios-arm64", "ios-simulator-arm64")}
    sources = {}
    for result in verified_maven:
        component = result["component"]
        rows = [(False, row) for row in result["stageFiles"]
                if row["relativePath"].startswith("outputs/maven/")]
        rows.extend((True, row) for row in result["sidecarFiles"]
                    if row["relativePath"].endswith(".asc"))
        for signature, row in rows:
            path = ("maven/" + row["relativePath"] if signature else
                    row["relativePath"].removeprefix("outputs/"))
            prefix = "maven/" + MAVEN_GROUPS[component].replace(".", "/") + "/"
            coordinate = path.removeprefix(prefix).split("/", 2)
            if (not path.startswith(prefix) or len(coordinate) != 3
                    or coordinate[0] not in COMPONENT_ARTIFACTS[component] or coordinate[1] != version):
                raise ValueError("SDK Central coordinate differs from its package owner/version")
            if path in sources:
                raise ValueError("SDK Central input is duplicated across packages")
            sources[path] = (component, signature, row["relativePath"])
            shard = {"codex-agent-runtime-ios-iosarm64": "ios-arm64",
                     "codex-agent-runtime-ios-iossimulatorarm64": "ios-simulator-arm64"}.get(
                         coordinate[0], "main")
            grouped[shard].append({**row, "relativePath": path})
    # iOS cinterop inputs exceed 512 MiB; each complete shard must still be <1GB.
    return ([{"fileName": f"codex-agent-{version}-central-{shard}.zip",
              "files": central_maven_files(files, [], max_entry_bytes=1_000_000_000 - 1)}
             for shard, files in grouped.items()], sources)


def verify_sdk_central_bundles(directory: Path, verified_maven: list[dict]) -> list[dict]:
    """Verify exact finalized envelopes against freshly authenticated package bytes."""
    directory = require_regular_directory(Path(directory), "SDK Central directory")
    layout, _ = _central_layout(verified_maven)
    if {path.name for path in directory.iterdir()} != {row["fileName"] for row in layout}:
        raise ValueError("SDK Central shard inventory is incomplete or unexpected")
    return [verify_central_bundle(directory / row["fileName"], row["files"],
                                  max_entry_bytes=1_000_000_000 - 1) for row in layout]


def produce_sdk_central_bundles(stages: dict[str, Path], sidecars: Path,
                                destination: Path, verified_maven: list[dict]) -> list[dict]:
    """Phase10 only: stream exact selected Maven/signature bytes into three ZIPs.

    The protected caller supplies results from the existing full package/PGP
    verifier. This helper neither authenticates originals nor grants release trust.
    """
    layout, sources = _central_layout(verified_maven)
    if set(stages) != set(MAVEN_GROUPS):
        raise ValueError("SDK Central stages do not cover the three packages")
    destination, sidecars = Path(destination), Path(sidecars)
    output = destination.resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK Central destination already exists")
    for source in (*stages.values(), sidecars):
        source = Path(source).resolve(strict=True)
        if output == source or output in source.parents or source in output.parents:
            raise ValueError("SDK Central destination overlaps an input")

    def open_member(path):
        component, signature, relative = sources[path]
        source = (sidecars / component if signature else Path(stages[component])) / relative
        descriptor, _ = _open_regular_file(source, "SDK Central input", reject_symlink_parents=True)
        return os.fdopen(descriptor, "rb")

    with tempfile.TemporaryDirectory(prefix="sdk-central-", dir=destination.parent) as temporary:
        prepared = Path(temporary)
        for row in layout:
            write_central_bundle(prepared / row["fileName"], row["files"], open_member)
        result = verify_sdk_central_bundles(prepared, verified_maven)
        publish_regular_tree(prepared, destination, expected_inventory=[
            {"relativePath": row["fileName"], "bytes": row["bytes"], "sha256": row["sha256"]}
            for row in sorted(result, key=lambda row: row["fileName"])])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("stage", "receipt", "sidecars", "pgp-public-key",
                   "pgp-public-key-sha256", "signing-home", "signing-fingerprint"):
        parser.add_argument(f"--{option}", required=True)
    arguments = parser.parse_args(argv)
    result = produce_sdk_phase10_maven_sidecars(
        Path(arguments.stage), Path(arguments.receipt), Path(arguments.sidecars),
        Path(arguments.pgp_public_key), arguments.pgp_public_key_sha256,
        Path(arguments.signing_home), arguments.signing_fingerprint, sys.stdin.read(),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
