"""Verify final SDK package archives that are not Maven carriers."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import gzip
import io
from pathlib import Path, PurePosixPath
import tarfile
import tempfile
from typing import Any

from .aggregate import validate_runtime_aggregate, validate_sdk_compatibility
from .registry import published_coordinate
from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    load_json_bytes,
    read_regular_file_bytes,
    regular_file_inventory,
    require_semver,
    sha256_bytes,
    snapshot_regular_tree,
    write_canonical_json,
)
from .plan import _runtime_compatibility_version
from .receipt import (
    output_inventory_digest,
    validate_phase_receipt,
    verify_output_manifest_identity,
)


NPM_COMPATIBILITY_PATH = "package/META-INF/codex-agent/sdk-compatibility.json"
_ARCHIVE_LIMIT = 1024 * 1024 * 1024
_JSON_LIMIT = 16 * 1024 * 1024


@contextmanager
def _bounded_tar(contents: bytes):
    """Bound all decompressed TAR bytes, including metadata before member iteration."""
    with tempfile.TemporaryFile() as expanded:
        with gzip.GzipFile(fileobj=io.BytesIO(contents), mode="rb") as source:
            total = 0
            while chunk := source.read(1024 * 1024):
                total += len(chunk)
                if total > _ARCHIVE_LIMIT:
                    raise ValueError("npm archive expanded bytes exceed their limit")
                expanded.write(chunk)
        expanded.seek(0)
        with tarfile.open(fileobj=expanded, mode="r:") as archive:
            yield archive


def validate_sdk_compatibility_bytes(contents: bytes) -> dict[str, Any]:
    return validate_sdk_compatibility(load_canonical_json_bytes(contents))


def _inspect_npm_sdk(
    archive: Path, compatibility_file: Path, *, sdk_version: str,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    require_semver(sdk_version, "npm SDK version")
    if archive.name != f"codex-agent-{sdk_version}.tgz":
        raise ValueError("npm archive SDK version identity mismatch")
    archive_bytes = read_regular_file_bytes(
        archive, max_bytes=_ARCHIVE_LIMIT, reject_symlink_parents=True,
    )
    compatibility = read_regular_file_bytes(
        compatibility_file, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    declaration = validate_sdk_compatibility_bytes(compatibility)
    if declaration["sdkVersion"] != sdk_version:
        raise ValueError("npm compatibility SDK version mismatch")
    declarations: list[tuple[str, bytes]] = []
    runtime_files: dict[str, bytes] = {}
    runtime_size = 0
    package_metadata = None
    with _bounded_tar(archive_bytes) as package:
        seen: set[str] = set()
        for member in package:
            if len(seen) >= 100_000 or member.size < 0:
                raise ValueError("npm archive inventory exceeds its limit")
            path = PurePosixPath(member.name)
            normalized = str(path)
            canonical_name = member.name == normalized or (
                member.isdir() and member.name == normalized + "/"
            )
            if (normalized in seen or not canonical_name or not path.parts or
                    any(ord(character) < 32 or ord(character) == 127 for character in member.name) or
                    "\\" in member.name or path.is_absolute() or ".." in path.parts or
                    member.issym() or member.islnk() or
                    (member.isdir() and member.size != 0) or
                    not (member.isfile() or member.isdir())):
                raise ValueError(f"unsafe or duplicate npm archive member: {member.name}")
            seen.add(normalized)
            if member.isfile() and path.name == "sdk-compatibility.json":
                if member.size > _JSON_LIMIT:
                    raise ValueError("npm compatibility member exceeds its size limit")
                source = package.extractfile(member)
                if source is None:
                    raise ValueError("npm compatibility archive member has no payload")
                contents = source.read(member.size + 1)
                if len(contents) != member.size:
                    raise ValueError("npm compatibility archive member size is invalid")
                declarations.append((member.name, contents))
            if member.isfile() and member.name == "package/package.json":
                if member.size > _JSON_LIMIT:
                    raise ValueError("npm package metadata exceeds its size limit")
                source = package.extractfile(member)
                if source is None:
                    raise ValueError("npm package metadata has no payload")
                contents = source.read(member.size + 1)
                if len(contents) != member.size:
                    raise ValueError("npm package metadata member size is invalid")
                package_metadata = load_json_bytes(contents)
            if member.isfile() and member.name.startswith("package/dist/"):
                runtime_size += member.size
                if (not member.name.endswith((".js", ".js.map"))
                        or member.size <= 0 or runtime_size > _ARCHIVE_LIMIT):
                    raise ValueError("npm Runtime distribution inventory is invalid")
                source = package.extractfile(member)
                if source is None:
                    raise ValueError("npm Runtime distribution member has no payload")
                contents = source.read(member.size + 1)
                if len(contents) != member.size:
                    raise ValueError("npm Runtime distribution member size is invalid")
                runtime_files[member.name] = contents
    if declarations != [(NPM_COMPATIBILITY_PATH, compatibility)]:
        raise ValueError("npm archive SDK compatibility inventory mismatch")
    if (not isinstance(package_metadata, dict)
            or package_metadata.get("name") != published_coordinate("sdk", "javascript")
            or package_metadata.get("version") != sdk_version):
        raise ValueError("npm package name or SDK version identity mismatch")
    return {
        "schemaVersion": 1,
        "result": "passed",
        "sdkVersion": sdk_version,
        "archive": {"path": archive.name, "sha256": sha256_bytes(archive_bytes)},
        "sdkCompatibility": {
            "path": NPM_COMPATIBILITY_PATH,
            "sha256": sha256_bytes(compatibility),
            "embeddedTargets": [
                record["target"]
                for record in declaration["runtime"]["embeddedVariants"]
            ],
        },
    }, runtime_files


def verify_npm_sdk_compatibility(
    archive: Path, compatibility_file: Path, output: Path, *, sdk_version: str,
) -> None:
    report, _ = _inspect_npm_sdk(archive, compatibility_file, sdk_version=sdk_version)
    write_canonical_json(output, report)


def verify_javascript_sdk_package_phase(
    stage_root: Path,
    receipt_path: Path,
    compatibility_request: Path,
    runtime_package_stage: Path,
    runtime_package_receipt: Path,
) -> tuple[dict[str, Any], bytes]:
    """Verify final JavaScript package semantics; planned execution remains external."""
    from .sdk_compatibility import load_sdk_compatibility_request, produce_sdk_compatibility

    stage_root, receipt_path, compatibility_request, runtime_package_stage, \
        runtime_package_receipt = map(Path, (
            stage_root, receipt_path, compatibility_request,
            runtime_package_stage, runtime_package_receipt,
        ))
    receipt_bytes = read_regular_file_bytes(
        receipt_path, max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    runtime_receipt_bytes = read_regular_file_bytes(
        runtime_package_receipt, max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    request_bytes = read_regular_file_bytes(
        compatibility_request, max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    stage_inventory = regular_file_inventory(stage_root)
    runtime_inventory = regular_file_inventory(runtime_package_stage)
    with tempfile.TemporaryDirectory(prefix="javascript-sdk-package-verification-") as temporary:
        private = Path(temporary).resolve()
        stage, runtime = private / "stage", private / "runtime"
        snapshot_regular_tree(stage_root, stage)
        snapshot_regular_tree(runtime_package_stage, runtime)
        if (regular_file_inventory(stage) != stage_inventory or
                regular_file_inventory(runtime) != runtime_inventory):
            raise ValueError("JavaScript SDK package inputs changed during snapshot")

        receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
        if (receipt["product"], receipt["component"], receipt["phase"], receipt["target"]) != (
            "sdk", "javascript", "package", "node",
        ):
            raise ValueError("JavaScript SDK verification requires its exact package phase")
        manifest = verify_output_manifest_identity(
            stage, "sdk", "javascript", "package", "node", receipt["productVersion"],
        )
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError("JavaScript SDK package receipt and stage outputs differ")
        archive_path = f"outputs/package/codex-agent-{receipt['productVersion']}.tgz"
        compatibility_path = "outputs/evidence/sdk-compatibility.json"
        report_path = "outputs/evidence/sdk-compatibility-archive.json"
        expected_outputs = {
            ("package", archive_path),
            ("evidence", compatibility_path),
            ("evidence", report_path),
        }
        if ({(record["kind"], record["relativePath"]) for record in receipt["outputs"]}
                != expected_outputs or len(receipt["outputs"]) != len(expected_outputs)):
            raise ValueError("JavaScript SDK package output kinds or paths are invalid")

        runtime_receipt = validate_phase_receipt(
            load_canonical_json_bytes(runtime_receipt_bytes),
        )
        if (runtime_receipt["product"], runtime_receipt["component"],
                runtime_receipt["phase"], runtime_receipt["target"]) != (
            "runtime", "node-js", "package", "node-js",
        ):
            raise ValueError("JavaScript SDK verification requires the Node Runtime package phase")
        runtime_manifest = verify_output_manifest_identity(
            runtime, "runtime", "node-js", "package", "node-js",
            runtime_receipt["productVersion"],
        )
        if runtime_manifest["outputs"] != runtime_receipt["outputs"]:
            raise ValueError("Node Runtime package receipt and stage outputs differ")

        request = private / "sdk-compatibility-request.json"
        request.write_bytes(request_bytes)
        compatibility = private / "sdk-compatibility.json"
        arguments = load_sdk_compatibility_request(
            request, request_directory=compatibility_request.parent,
        )
        runtime_manifest_bytes = read_regular_file_bytes(
            arguments["runtime_manifest"], max_bytes=_JSON_LIMIT,
            reject_symlink_parents=True,
        )
        runtime_aggregate = validate_runtime_aggregate(
            load_canonical_json_bytes(runtime_manifest_bytes),
        )
        declaration = produce_sdk_compatibility(**arguments, output=compatibility)
        if (declaration["sdkVersion"] != receipt["productVersion"]
                or declaration["runtime"]["defaultManifestSha256"]
                != sha256_bytes(runtime_manifest_bytes)
                or _runtime_compatibility_version(runtime_receipt["productVersion"])
                != runtime_aggregate["runtimeCompatibilityVersion"]
                or runtime_receipt["inputs"]["versionIdentity"]
                != runtime_aggregate["runtimeCompatibilityVersion"]):
            raise ValueError("JavaScript SDK or Runtime package version differs from compatibility")
        if compatibility.read_bytes() != (stage / compatibility_path).read_bytes():
            raise ValueError("JavaScript SDK evidence differs from authenticated compatibility")

        report, packaged_runtime = _inspect_npm_sdk(
            stage / archive_path, compatibility, sdk_version=receipt["productVersion"],
        )
        if canonical_json_bytes(report) != (stage / report_path).read_bytes():
            raise ValueError("JavaScript SDK npm verification report differs")
        expected_runtime = {
            "package/dist/" + record["relativePath"].removeprefix("outputs/adapter/"):
                (runtime / record["relativePath"]).read_bytes()
            for record in runtime_receipt["outputs"]
            if record["kind"] == "adapter"
            and record["relativePath"].startswith("outputs/adapter/")
            and record["relativePath"].endswith((".js", ".js.map"))
        }
        if (not any(path.endswith(".js") for path in expected_runtime)
                or not any(path.endswith(".js.map") for path in expected_runtime)
                or packaged_runtime != expected_runtime):
            raise ValueError("JavaScript SDK Runtime JS/map inventory differs from original package")

        runtime_reference = {
            key: runtime_receipt[key]
            for key in ("product", "component", "phase", "target", "buildKey")
        }
        runtime_reference["outputsDigest"] = output_inventory_digest(runtime_receipt["outputs"])
        if runtime_reference not in receipt["inputs"]["upstreamArtifacts"]:
            raise ValueError("JavaScript SDK receipt does not reference the original Runtime package")

    if (regular_file_inventory(stage_root) != stage_inventory
            or regular_file_inventory(runtime_package_stage) != runtime_inventory
            or read_regular_file_bytes(receipt_path, max_bytes=_JSON_LIMIT,
                                       reject_symlink_parents=True) != receipt_bytes
            or read_regular_file_bytes(runtime_package_receipt, max_bytes=_JSON_LIMIT,
                                       reject_symlink_parents=True) != runtime_receipt_bytes
            or read_regular_file_bytes(compatibility_request, max_bytes=_JSON_LIMIT,
                                       reject_symlink_parents=True) != request_bytes):
        raise ValueError("JavaScript SDK package sources changed during verification")
    return receipt, receipt_bytes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--compatibility", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    verify_npm_sdk_compatibility(
        args.archive.resolve(), args.compatibility.resolve(), args.output.resolve(),
        sdk_version=args.version,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
