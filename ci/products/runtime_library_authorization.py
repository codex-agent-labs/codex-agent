"""Project exact native libraries from an already verified signed Runtime handoff."""

from pathlib import Path
import tempfile

from .aggregate import RUNTIME_VARIANT_ZIP_LIMITS, validate_runtime_variant
from .c_abi import TARGET_SPECS
from .inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, sha256_bytes,
    verified_zip_contents,
)
from .registry import NATIVE_TARGETS, PhaseInstanceId
from .runtime_identity import derive_runtime_identity
from .sdk_runtime_root import validate_library_authorization


_LIBRARY_PATHS = {
    spec.classifier.removeprefix("c-abi-"): spec.library_path
    for spec in TARGET_SPECS.values()
}
_MANIFEST = "runtime-variant-manifest.json"


def verified_runtime_libraries(verified: dict, signing: dict) -> dict[str, dict]:
    """Use only inside ``verified_runtime_aggregate_handoff``'s live context.

    The handoff authenticates original receipts, Contract, five variants and
    signed aggregate. This projection additionally binds the exact library
    member that an external loader will open; it is not an admission function.
    """
    aggregate = verified["manifest"]
    attestation = verified["attestation"]
    index = verified["indexInputs"]
    if set(index["variant_bundles"]) != set(NATIVE_TARGETS):
        raise ValueError("Runtime library authorization needs exactly five verified variants")
    aggregate_digest = sha256_bytes(read_regular_file_bytes(index["manifest"], reject_symlink_parents=True))
    attestation_digest = sha256_bytes(read_regular_file_bytes(index["attestation"], reject_symlink_parents=True))
    if aggregate_digest != attestation["payload"]["sha256"]:
        raise ValueError("Runtime library authorization aggregate payload changed")
    variants = {record["target"]: record for record in aggregate["variants"]}
    attestations = {record["target"]: record for record in attestation["variants"]}
    if set(variants) != set(NATIVE_TARGETS) or set(attestations) != set(NATIVE_TARGETS):
        raise ValueError("Runtime library authorization variant set changed")
    result = {}
    for target in NATIVE_TARGETS:
        bundle = Path(index["variant_bundles"][target])
        _, first, bundle_record = verified_zip_contents(
            bundle, **RUNTIME_VARIANT_ZIP_LIMITS,
            retained_paths={_MANIFEST}, canonical_stored=True,
        )
        variant_bytes = first[_MANIFEST]
        variant = validate_runtime_variant(load_canonical_json_bytes(variant_bytes))
        record, signed = variants[target], attestations[target]
        variant_attestation = read_regular_file_bytes(
            index["variant_attestations"][target], reject_symlink_parents=True,
        )
        if (variant["target"] != target or variant["componentId"] != record["componentId"]
                or bundle_record["sha256"] != record["bundleSha256"]
                or sha256_bytes(variant_bytes) != record["manifestSha256"]
                or signed["bundleSha256"] != record["bundleSha256"]
                or signed["manifestSha256"] != record["manifestSha256"]
                or signed["variantAttestationSha256"] != sha256_bytes(variant_attestation)):
            raise ValueError(f"Runtime library authorization variant changed: {target}")
        binary = verified["originalPhases"][PhaseInstanceId("runtime", target, "binary", target)]["receipt"]
        if binary["buildKey"] != variant["inputs"]["binaryBuildKey"]:
            raise ValueError(f"Runtime library authorization binary receipt changed: {target}")
        identity = derive_runtime_identity({
            "schemaVersion": 1,
            "binaryBuildKey": binary["buildKey"],
            "runtimeCompatibilityVersion": variant["runtimeCompatibilityVersion"],
            "target": target,
            "contract": variant["contract"],
            "cAbi": variant["cAbi"],
            "appServer": variant["appServer"],
            "toolchainProfile": variant["toolchainProfile"],
        })
        if identity["componentId"] != variant["componentId"]:
            raise ValueError(f"Runtime library authorization identity changed: {target}")
        c_abi = [item for item in variant["innerArtifacts"] if item["role"] == "c-abi-archive"]
        if len(c_abi) != 1:
            raise ValueError(f"Runtime library authorization C ABI inventory changed: {target}")
        c_abi = c_abi[0]
        _, contents, second_bundle = verified_zip_contents(
            bundle, **RUNTIME_VARIANT_ZIP_LIMITS,
            retained_paths={_MANIFEST, c_abi["path"]}, canonical_stored=True,
        )
        archive = contents[c_abi["path"]]
        if (second_bundle != bundle_record or contents[_MANIFEST] != variant_bytes
                or len(archive) != c_abi["bytes"] or sha256_bytes(archive) != c_abi["sha256"]):
            raise ValueError(f"Runtime library authorization C ABI archive changed: {target}")
        with tempfile.TemporaryDirectory(prefix="runtime-library-member-") as temporary:
            archive_path = Path(temporary) / "c-abi.zip"
            archive_path.write_bytes(archive)
            _, libraries, _ = verified_zip_contents(
                archive_path, **RUNTIME_VARIANT_ZIP_LIMITS,
                retained_paths={_LIBRARY_PATHS[target]},
            )
        library = libraries[_LIBRARY_PATHS[target]]
        claim = validate_library_authorization({
            "schemaVersion": 1,
            "kind": "desktop-runtime-library-authorization",
            "runtimeVersion": aggregate["runtimeVersion"],
            "runtimeIdentity": load_canonical_json_bytes(
                (identity["runtimeIdentityJson"] + "\n").encode("utf-8")),
            "runtimeLibrarySha256": sha256_bytes(library),
            "variantBundleSha256": record["bundleSha256"],
            "variantManifestSha256": record["manifestSha256"],
            "aggregateManifestSha256": aggregate_digest,
            "variantAttestationSha256": signed["variantAttestationSha256"],
            "aggregateAttestationSha256": attestation_digest,
            "signing": signing,
        })
        result[target] = {"claim": claim, "library": library,
                          "fileName": Path(_LIBRARY_PATHS[target]).name}
    return result
