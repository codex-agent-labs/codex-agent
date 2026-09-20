"""Deterministic Android metadata join, never original-validation admission.

The caller authenticates the original package and validation receipts, runs
the complete Firebase/AAR gate, and supplies the independently selected AAR
and Runtime digests.  This writer only binds those inputs into content; it
does not grant receipt, producer, source, host, tooling, or reuse authority.
"""

import argparse
import os
from pathlib import Path
import tempfile

from .inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_regular_directory, require_semver, require_string,
    write_canonical_json,
)
from .plan import _upstream_record
from .receipt import output_inventory_digest, validate_phase_receipt, verify_output_manifest_identity
from .sdk_android_validation_content import android_metadata_content
from .sdk_android_validation_phase import OUTPUT_KIND as _VALIDATION_KIND, OUTPUT_PATH as _VALIDATION_PATH
from .sdk_package import _require_capability_output_separate


OUTPUT_PATH = "outputs/evidence/android-metadata.json"
OUTPUT_KIND = "android-metadata-content"
_LIMIT = 16 * 1024 * 1024


def write_android_metadata_content(request_path: Path, output: Path):
    """Write content from caller-authenticated originals without admitting them."""
    request_path, output = Path(request_path).absolute(), Path(output).absolute()

    def read(path):
        return read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)

    request_bytes = read(request_path)
    request = require_exact_keys(load_canonical_json_bytes(request_bytes), {
        "sdkVersion", "packageStage", "packageReceipt", "validationStage",
        "validationReceipt", "releaseAarSha256", "bundledRuntimeSha256",
    }, "Android metadata request")
    version = require_semver(request["sdkVersion"], "Android metadata SDK version")

    def path(value, label):
        selected = Path(require_string(value, label))
        if not selected.is_absolute() or selected.resolve(strict=False) != selected:
            raise ValueError(f"{label} must be absolute, normalized and non-symbolic")
        return selected

    stages = {
        "package": path(request["packageStage"], "Android metadata package stage"),
        "validation": path(request["validationStage"], "Android metadata validation stage"),
    }
    receipts = {
        "package": path(request["packageReceipt"], "Android metadata package receipt"),
        "validation": path(request["validationReceipt"], "Android metadata validation receipt"),
    }

    def inventory(directory):
        for ancestor in (directory, *directory.parents):
            require_regular_directory(ancestor, "Android metadata original stage ancestry")
        return regular_file_inventory(directory)

    def output_safe():
        _require_capability_output_separate(output, [request_path, *stages.values(), *receipts.values()])
        if output != output.resolve(strict=False) or output.exists() or output.is_symlink():
            raise ValueError("Android metadata output must be fresh, normalized and non-symbolic")
        for ancestor in output.parents:
            if ancestor.exists() or ancestor.is_symlink():
                require_regular_directory(ancestor, "Android metadata output ancestry")

    output_safe()
    before = {name: inventory(stage) for name, stage in stages.items()}
    receipt_bytes = {name: read(receipt) for name, receipt in receipts.items()}

    def unchanged():
        if (read(request_path) != request_bytes
                or any(inventory(stage) != before[name] for name, stage in stages.items())
                or any(read(receipt) != receipt_bytes[name] for name, receipt in receipts.items())):
            raise ValueError("Android metadata original request, stage or receipt changed")

    try:
        originals = {name: validate_phase_receipt(load_canonical_json_bytes(raw))
                     for name, raw in receipt_bytes.items()}
        for name, phase in (("package", "package"), ("validation", "validation")):
            receipt = originals[name]
            if (tuple(receipt[field] for field in ("product", "component", "phase", "target")) !=
                    ("sdk", "sdk-android", phase, "android") or receipt["productVersion"] != version):
                raise ValueError("Android metadata original receipt has the wrong phase/version identity")
            manifest = verify_output_manifest_identity(
                stages[name], "sdk", "sdk-android", phase, "android", version)
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Android metadata stage differs from its exact original receipt")

        validation = originals["validation"]
        if (len(validation["outputs"]) != 1
                or validation["outputs"][0]["kind"] != _VALIDATION_KIND
                or validation["outputs"][0]["relativePath"] != _VALIDATION_PATH):
            raise ValueError("Android metadata requires the exact singleton validation content output")
        package_records = [record for record in validation["inputs"]["upstreamArtifacts"]
                           if (record["product"], record["component"], record["phase"]) ==
                           ("sdk", "sdk-android", "package")]
        if package_records != [_upstream_record(originals["package"])]:
            raise ValueError("Android metadata validation differs from the selected original package lineage")
        content = android_metadata_content(
            sdk_version=version,
            package_outputs_digest=output_inventory_digest(originals["package"]["outputs"]),
            expected_release_aar_sha256=request["releaseAarSha256"],
            expected_bundled_runtime_sha256=request["bundledRuntimeSha256"],
            validation_content=load_canonical_json_bytes(read(stages["validation"] / _VALIDATION_PATH)),
        )
        unchanged()
        output_safe()
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".android-metadata-", dir=output.parent) as temporary:
            staged = Path(temporary) / "content.json"
            write_canonical_json(staged, content)
            unchanged()
            output_safe()
            os.link(staged, output, follow_symlinks=False)
        return content
    finally:
        unchanged()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        write_android_metadata_content(arguments.request, arguments.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
