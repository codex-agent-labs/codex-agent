"""Deterministic Core metadata joins, never original-validation admission.

The caller authenticates all eleven original validation receipts, their complete
execution/source/toolchain evidence, and common package/Contract lineage first.
These ordinary dictionaries and shape checks cannot grant any such authority.
Android has a separate content model; this module only joins Core targets.
"""

import argparse
import os
from pathlib import Path
import tempfile

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, require_array,
    require_exact_keys, require_integer, require_semver, require_sha256,
    read_regular_file_bytes, regular_file_inventory, require_regular_directory,
    require_string, write_canonical_json,
)
from .plan import _upstream_record
from .receipt import output_inventory_digest, validate_phase_receipt, verify_output_manifest_identity
from .registry import SDK_FACADE_CONTRACT_COMPONENTS, SDK_FACADE_TARGETS
from .sdk_facade_validation import validate_facade_validation_content
from .sdk_package import _require_capability_output_separate


OUTPUT_PATH = "outputs/evidence/facade-metadata.json"
OUTPUT_KIND = "sdk-facade-metadata-content"
_VALIDATION_PATH = "outputs/validation/facade-validation.json"
_VALIDATION_KIND = "sdk-facade-validation-content"
_LIMIT = 16 * 1024 * 1024


def validate_facade_metadata_content(value):
    """Validate exact content shape and internal consistency, not authenticity."""
    value = require_exact_keys(value, {
        "schemaVersion", "kind", "component", "sdkVersion", "packageOutputsDigest",
        "contractDigest", "validations",
    }, "Core metadata content")
    if (require_integer(value["schemaVersion"], "Core metadata schema") != 1
            or value["kind"] != "sdk-facade-metadata-content" or value["component"] != "sdk-core"):
        raise ValueError("Core metadata content identity is invalid")
    version = require_semver(value["sdkVersion"], "Core metadata SDK version")
    package = require_sha256(value["packageOutputsDigest"], "Core metadata package inventory")
    contract = require_sha256(value["contractDigest"], "Core metadata Contract identity")
    validations = [validate_facade_validation_content(member) for member in
                   require_array(value["validations"], "Core metadata validations")]
    if [member["target"] for member in validations] != list(SDK_FACADE_TARGETS):
        raise ValueError("Core metadata requires exactly all eleven ordered validation targets")
    if any(member["sdkVersion"] != version or member["packageOutputsDigest"] != package
           or member["contractDigest"] != contract for member in validations):
        raise ValueError("Core metadata validation differs from its common SDK/package/Contract identity")
    return load_canonical_json_bytes(canonical_json_bytes(value))


def facade_metadata_content(*, sdk_version, package_outputs_digest, contract_digest,
                            expected_component_digests, validation_contents):
    """Join caller-authenticated contents against independently selected identities.

    Only key-bound semantic content enters the join. Full Contract bundle hashes,
    raw logs, cache outcomes, original paths, receipts and signatures stay external.
    Different original producers may legitimately prove the same selected content.
    """
    components = require_exact_keys(expected_component_digests,
        set(SDK_FACADE_CONTRACT_COMPONENTS.values()), "Core metadata expected Contract components")
    for component, digest in components.items():
        require_sha256(digest, "Core metadata expected Contract component " + component)
    contents = require_exact_keys(validation_contents, SDK_FACADE_TARGETS,
                                  "Core metadata validation targets")
    result = validate_facade_metadata_content({
        "schemaVersion": 1, "kind": "sdk-facade-metadata-content", "component": "sdk-core",
        "sdkVersion": sdk_version, "packageOutputsDigest": package_outputs_digest,
        "contractDigest": contract_digest,
        "validations": [contents[target] for target in SDK_FACADE_TARGETS],
    })
    for member in result["validations"]:
        component = SDK_FACADE_CONTRACT_COMPONENTS[member["target"]]
        if member["componentDigests"] != [{"component": component, "sha256": components[component]}]:
            raise ValueError("Core metadata validation differs from its selected Contract component")
    return result


def write_facade_metadata_content(request_path: Path, output: Path):
    """Publish only canonical content from caller-authenticated original inputs.

    The canonical request is invocation policy, not retained-source authority.
    Shape, stage/receipt and lineage comparisons do not authenticate a signature,
    original execution or host. All eleven complete validation gates belong to
    the caller; no receipt, manifest or admission token is produced here.
    """
    request_path, output = Path(request_path).absolute(), Path(output).absolute()

    def read(path):
        return read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)

    request_bytes = read(request_path)
    request = require_exact_keys(load_canonical_json_bytes(request_bytes), {
        "sdkVersion", "packageStage", "packageReceipt", "contractDigest", "componentDigests", "validations",
    }, "Core metadata request")
    version = require_semver(request["sdkVersion"], "Core metadata SDK version")
    records = require_exact_keys(request["validations"], SDK_FACADE_TARGETS, "Core metadata validation records")

    def path(value, label):
        selected = Path(require_string(value, label))
        if not selected.is_absolute() or selected.resolve(strict=False) != selected:
            raise ValueError(f"{label} must be absolute, normalized and non-symbolic")
        return selected

    stages = {"package": path(request["packageStage"], "Core metadata package stage")}
    receipts = {"package": path(request["packageReceipt"], "Core metadata package receipt")}
    for target in SDK_FACADE_TARGETS:
        record = require_exact_keys(records[target], {"stageRoot", "phaseReceipt"},
                                    "Core metadata validation record")
        stages[target] = path(record["stageRoot"], "Core metadata validation stage")
        receipts[target] = path(record["phaseReceipt"], "Core metadata validation receipt")

    def inventory(directory):
        for ancestor in (directory, *directory.parents):
            require_regular_directory(ancestor, "Core metadata original stage ancestry")
        return regular_file_inventory(directory)

    def output_safe():
        _require_capability_output_separate(output, [request_path, *stages.values(), *receipts.values()])
        if output != output.resolve(strict=False) or output.exists() or output.is_symlink():
            raise ValueError("Core metadata output must be fresh, normalized and non-symbolic")
        for ancestor in output.parents:
            if ancestor.exists() or ancestor.is_symlink():
                require_regular_directory(ancestor, "Core metadata output ancestry")

    output_safe()
    before = {name: inventory(stage) for name, stage in stages.items()}
    receipt_bytes = {name: read(receipt) for name, receipt in receipts.items()}

    def unchanged():
        if (read(request_path) != request_bytes
                or any(inventory(stage) != before[name] for name, stage in stages.items())
                or any(read(receipt) != receipt_bytes[name] for name, receipt in receipts.items())):
            raise ValueError("Core metadata original request, stage or receipt changed")

    try:
        originals = {name: validate_phase_receipt(load_canonical_json_bytes(raw))
                     for name, raw in receipt_bytes.items()}
        contents = {}
        for name, stage in stages.items():
            phase, target = ("package", "common") if name == "package" else ("validation", name)
            receipt = originals[name]
            if (tuple(receipt[field] for field in ("product", "component", "phase", "target")) !=
                    ("sdk", "sdk-core", phase, target) or receipt["productVersion"] != version):
                raise ValueError("Core metadata original receipt has the wrong phase/version identity")
            manifest = verify_output_manifest_identity(stage, "sdk", "sdk-core", phase, target, version)
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Core metadata stage differs from its exact original receipt")
            if name == "package":
                continue
            if (len(manifest["outputs"]) != 1
                    or manifest["outputs"][0]["kind"] != _VALIDATION_KIND
                    or manifest["outputs"][0]["relativePath"] != _VALIDATION_PATH):
                raise ValueError("Core metadata requires each exact singleton validation content output")
            package_records = [record for record in receipt["inputs"]["upstreamArtifacts"]
                               if (record["product"], record["component"], record["phase"]) ==
                               ("sdk", "sdk-core", "package")]
            if package_records != [_upstream_record(originals["package"])]:
                raise ValueError("Core metadata validation differs from the selected original package lineage")
            contents[target] = load_canonical_json_bytes(read(stage / _VALIDATION_PATH))
        content = facade_metadata_content(sdk_version=version,
            package_outputs_digest=output_inventory_digest(originals["package"]["outputs"]),
            contract_digest=request["contractDigest"], expected_component_digests=request["componentDigests"],
            validation_contents=contents)
        unchanged()
        output_safe()
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".facade-metadata-", dir=output.parent) as temporary:
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
        write_facade_metadata_content(arguments.request, arguments.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
