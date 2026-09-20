"""Deterministic two-target Apple metadata, never receipt or admission authority.

Both original validation receipts, their complete external evidence, and their
original package lineage must be authenticated by the caller before using this
content. This serializer cannot replace either independent full validation gate.
"""

import argparse
import os
from pathlib import Path
import tempfile

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_regular_directory,
    require_semver, require_sha256, require_string, write_canonical_json,
)
from .receipt import output_inventory_digest, verify_output_manifest_identity
from .sdk_apple_validation_content import validate_apple_validation_content
from .sdk_package import _require_capability_output_separate


OUTPUT_PATH = "outputs/evidence/apple-metadata.json"
OUTPUT_KIND = "apple-metadata-content"
_TARGETS = ("ios-arm64", "ios-simulator-arm64")
_LIMIT = 16 * 1024 * 1024


def apple_metadata_content(*, sdk_version, package_outputs_digest, contract_digest,
                           expected_canonical, validation_contents):
    """Join exact already-authenticated content without importing producer identity.

    Independently supplied expectations bind both targets to the same selected
    package and Contract. Matching these values establishes byte consistency,
    not signatures, source authority, compiler execution or hosted acceptance.
    """
    version = require_semver(sdk_version, "Apple metadata SDK version")
    package = require_sha256(package_outputs_digest, "Apple metadata package inventory")
    contract = require_sha256(contract_digest, "Apple metadata Contract identity")
    canonical = require_exact_keys(expected_canonical,
        {"apiReportSha256", "coverageReceiptSha256"}, "Apple metadata expected canonical identity")
    for name, value in canonical.items():
        require_sha256("sha256:" + require_string(value, "Apple metadata " + name), "Apple metadata " + name)
    contents = require_exact_keys(validation_contents, _TARGETS, "Apple metadata validation targets")
    validations = []
    for target in _TARGETS:
        value = validate_apple_validation_content(contents[target])
        if (value["target"] != target or value["sdkVersion"] != version
                or value["packageOutputsDigest"] != package or value["contractDigest"] != contract
                or value["canonical"] != canonical):
            raise ValueError("Apple metadata validation differs from its selected target/package/Contract identity")
        validations.append(value)
    return load_canonical_json_bytes(canonical_json_bytes({
        "schemaVersion": 1, "kind": "sdk-apple-metadata-content", "component": "sdk-ios",
        "sdkVersion": version, "packageOutputsDigest": package, "contractDigest": contract,
        "canonical": canonical, "validations": validations,
    }))


def write_apple_metadata_content(*, sdk_version, package_stage, device_validation,
                                simulator_validation, output):
    """Write a fresh canonical join, preserving every original input unchanged.

    The original package manifest supplies the complete content inventory. The
    two canonical validation files must agree on Contract identity; their data
    does not authenticate that Contract or their own original receipt lineage.
    All such authority remains with the caller's full original-input contexts.
    """
    package_stage, output = Path(package_stage).absolute(), Path(output).absolute()
    paths = {"ios-arm64": Path(device_validation), "ios-simulator-arm64": Path(simulator_validation)}

    def output_safe():
        _require_capability_output_separate(output, [package_stage, *paths.values()])
        if output != output.resolve(strict=False) or output.exists() or output.is_symlink():
            raise ValueError("Apple metadata output must be fresh, normalized and non-symbolic")
        for parent in output.parents:
            if parent.exists() or parent.is_symlink():
                require_regular_directory(parent, "Apple metadata output ancestry")

    output_safe()
    for parent in (package_stage, *package_stage.parents):
        require_regular_directory(parent, "Apple metadata package ancestry")
    before = regular_file_inventory(package_stage)
    originals = {target: read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
                 for target, path in paths.items()}

    def unchanged():
        if (regular_file_inventory(package_stage) != before or any(
                read_regular_file_bytes(paths[target], max_bytes=_LIMIT, reject_symlink_parents=True) != raw
                for target, raw in originals.items())):
            raise ValueError("Apple metadata original package or validation content changed")

    try:
        manifest = verify_output_manifest_identity(package_stage, "sdk", "sdk-ios", "package", "ios", sdk_version)
        contents = {target: load_canonical_json_bytes(raw) for target, raw in originals.items()}
        selected = validate_apple_validation_content(contents["ios-arm64"])
        content = apple_metadata_content(sdk_version=sdk_version,
            package_outputs_digest=output_inventory_digest(manifest["outputs"]),
            contract_digest=selected["contractDigest"], expected_canonical=selected["canonical"],
            validation_contents=contents)
    finally:
        unchanged()
    output_safe()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".apple-metadata-", dir=output.parent) as temporary:
        staged = Path(temporary) / "content.json"
        write_canonical_json(staged, content)
        unchanged()
        output_safe()
        os.link(staged, output, follow_symlinks=False)
    return content


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--sdk-version", required=True)
    for name in ("package-stage", "device-validation", "simulator-validation", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        write_apple_metadata_content(**vars(args))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
