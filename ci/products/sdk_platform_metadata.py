"""Deterministic Core metadata joins, never original-validation admission.

The caller authenticates all eleven original validation receipts, their complete
execution/source/toolchain evidence, and common package/Contract lineage first.
These ordinary dictionaries and shape checks cannot grant any such authority.
Android is intentionally absent until its validation content contract exists.
"""

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, require_array,
    require_exact_keys, require_integer, require_semver, require_sha256,
)
from .registry import SDK_FACADE_CONTRACT_COMPONENTS, SDK_FACADE_TARGETS
from .sdk_facade_validation import validate_facade_validation_content


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
