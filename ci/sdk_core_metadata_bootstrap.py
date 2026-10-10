"""Build caller-owned Core metadata policy from elected originals, never uploads.

This is a pre-worker input preparer, not metadata or hosted-toolchain admission.
Each native host requires its own immutable archive pin; missing pins fail closed.
"""

import argparse
import os
from pathlib import Path
import sys
import tempfile
import tomllib

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys, require_semver, require_sha256,
    sha256_bytes, sha256_file, write_canonical_json)
from products.plan import _contract_projection_from_request
from products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId, SDK_FACADE_CONTRACT_COMPONENTS, SDK_FACADE_TARGETS
from products.sdk_facade_inputs import _request
from products.sdk_facade_validation_admission import _NON_NATIVE_TARGETS, _native_archive_path
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from products.toolchain import HOSTS, _metadata_checksum, RUNTIME_VERIFICATION_METADATA, VERSION_CATALOG
from sdk_core_validation_policy import prepare as prepare_validation_request
from sdk_phase import route


_METADATA = PhaseInstanceId("sdk", "sdk-core", "metadata", "common")
_NATIVE = set(SDK_FACADE_TARGETS) - _NON_NATIVE_TARGETS


def _native_archives(root, revision, values):
    values = require_exact_keys(values, _NATIVE, "Core metadata native archive policy")
    catalog = tomllib.loads(git_regular_blob_bytes(root, revision, VERSION_CATALOG,
        max_bytes=4 * 1024 * 1024).decode("utf-8", errors="strict"))
    version = require_semver(catalog["versions"]["kotlin"], "Git-pinned Kotlin version")
    verification = git_regular_blob_bytes(root, revision, RUNTIME_VERIFICATION_METADATA,
        max_bytes=4 * 1024 * 1024)
    archives = {target: _native_archive_path(target, values[target]) for target in _NATIVE}
    if any(path.is_relative_to(root) for path in archives.values()):
        raise ValueError("Core metadata native archive must be caller-owned outside the checkout")
    digests = {path: sha256_file(path, reject_symlink_parents=True) for path in set(archives.values())}
    for target, path in archives.items():
        host = route({"product": "sdk", "component": "sdk-core", "phase": "validation",
                      "target": target})
        platform = (host["runnerOs"], host["runnerArch"])
        suffix = (HOSTS[platform][1] if platform in HOSTS else
                  "linux-aarch64" if platform == ("Linux", "ARM64") else None)
        if suffix is None:
            raise ValueError("Core metadata native host lacks an exact archive mapping")
        extension = "zip" if suffix == "windows-x86_64" else "tar.gz"
        name = f"kotlin-native-prebuilt-{version}-{suffix}.{extension}"
        expected = _metadata_checksum(verification, name)
        if digests[path] != expected:
            raise ValueError("Core metadata native archive differs from its immutable Git pin")
    return archives, digests


def prepare(plan, discovery, state, requests_root, destination, *, expected_build_key,
        sdk_inputs_artifact_id, sdk_inputs_artifact_sha256, trusted_workflow_sha,
        sdk_validation_tooling, native_compiler_archives, keyring, keys_directory,
        repository_root, environ, token, sdk_apple_validation_policy=None):
    """Create one external bootstrap policy using exact retained wave-13 originals."""
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    plan, discovery, state = (Path(value).absolute() for value in (plan, discovery, state))
    requests_root, destination = Path(requests_root).absolute(), Path(destination).absolute()
    tooling_path = Path(sdk_validation_tooling).absolute()
    if (tooling_path.resolve(strict=True) != tooling_path or
            tooling_path == root or tooling_path.is_relative_to(root)):
        raise ValueError("Core metadata tooling must be independent of the checkout")
    if (requests_root == root or root not in requests_root.parents
            or requests_root.resolve(strict=False) != requests_root
            or requests_root.exists() or requests_root.is_symlink()):
        raise ValueError("Core metadata requests require a fresh checkout-owned directory")
    _require_capability_output_separate(destination, [root, plan, discovery, state,
        requests_root, Path(sdk_validation_tooling), Path(keyring), Path(keys_directory)])
    if (destination.resolve(strict=False) != destination or destination.exists()
            or destination.is_symlink()):
        raise ValueError("Core metadata bootstrap policy must be a fresh external file")
    require_sha256(expected_build_key, "Core metadata elected key")
    tooling_raw = read_regular_file_bytes(tooling_path, reject_symlink_parents=True)
    tooling = require_exact_keys(load_canonical_json_bytes(tooling_raw),
        {"evidence", "publicKey", "javaExecutable", "requiredTrustDomain", "keyring", "keysDirectory"},
        "Core metadata caller tooling")
    if (tooling["requiredTrustDomain"] != "release" or any(tooling[name] is None for name in
            ("evidence", "publicKey", "javaExecutable", "keyring", "keysDirectory"))):
        raise ValueError("Core metadata requires complete release tooling authority")
    plan_bytes = read_regular_file_bytes(plan, reject_symlink_parents=True)
    before = {path: regular_file_inventory(path, allow_empty=True) for path in (discovery, state)}
    verified = product_reuse._verified_product_state(plan, discovery, state, root, environ,
        tooling, sdk_original_workflow_sha=trusted_workflow_sha,
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy}
           if sdk_apple_validation_policy is not None else {}))
    ready = verified.prior_ready_plans.get(_METADATA)
    if ready is None or ready["buildKey"] != expected_build_key:
        raise ValueError("Core metadata is not ready with its exact elected key")
    originals = {}
    for target in SDK_FACADE_TARGETS:
        instance = PhaseInstanceId("sdk", "sdk-core", "validation", target)
        selected = verified.prior_by_instance.get(instance)
        if (selected is None or selected["state"] != "retained" or instance not in verified.sources):
            raise ValueError("Core metadata lacks a selected retained validation original")
        originals[target] = (selected["buildKey"], selected["receiptSha256"])
    archives, archive_digests = _native_archives(root, verified.plan["validationCommit"],
                                                 native_compiler_archives)

    def unchanged():
        require_no_signing_secret(environ)
        if (read_regular_file_bytes(plan, reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(tooling_path, reject_symlink_parents=True) != tooling_raw
                or any(regular_file_inventory(path, allow_empty=True) != inventory
                       for path, inventory in before.items())
                or any(sha256_file(path, reject_symlink_parents=True) != digest
                       for path, digest in archive_digests.items())):
            raise ValueError("Core metadata caller election or archive policy changed")

    requests_root.mkdir(parents=True)
    records, projections = {}, {}
    for target in SDK_FACADE_TARGETS:
        unchanged()
        key, digest = originals[target]
        output = requests_root / target
        prepared = prepare_validation_request(plan, discovery, state, output,
            target=target, expected_build_key=key, expected_metadata_build_key=expected_build_key,
            sdk_inputs_artifact_id=sdk_inputs_artifact_id,
            sdk_inputs_artifact_sha256=sdk_inputs_artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, keyring=keyring,
            keys_directory=keys_directory, repository_root=root, environ=environ, token=token,
            native_compiler_archive=archives.get(target), sdk_validation_tooling=tooling,
            sdk_apple_validation_policy=sdk_apple_validation_policy)
        request = Path(prepared["facadeRequest"])
        receipt_path = output / f"predecessors/sdk-sdk-core-validation-{target}/phase-receipt.json"
        receipt_raw = read_regular_file_bytes(receipt_path, reject_symlink_parents=True)
        receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_raw))
        if (sha256_bytes(receipt_raw) != digest or receipt["buildKey"] != key
                or tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
                   ("sdk", "sdk-core", "validation", target)):
            raise ValueError("Core metadata request differs from its selected original validation")
        value, _ = _request(request)
        versions = {"contract": value["contractVersion"]}
        projection = _contract_projection_from_request(
            PhaseInstanceId("sdk", "sdk-core", "validation", target), versions,
            value["validationContractEvidence"]).receipt_value()
        component = SDK_FACADE_CONTRACT_COMPONENTS[target]
        if [row["component"] for row in projection["componentDigests"]] != [component]:
            raise ValueError("Core metadata request has an unexpected Contract component")
        projections[target] = projection
        records[target] = {"validationReceipt": str(receipt_path), "facadeRequest": str(request),
                           **({"nativeCompilerArchive": str(archives[target])} if target in archives else {})}
    digests = {projection["contractDigest"] for projection in projections.values()}
    if len(digests) != 1 or len({projection["contractVersion"] for projection in projections.values()}) != 1:
        raise ValueError("Core metadata validations disagree on authenticated Contract identity")
    components = {SDK_FACADE_CONTRACT_COMPONENTS[target]: projections[target]["componentDigests"][0]["sha256"]
                  for target in SDK_FACADE_TARGETS}
    policy = {"plan": str(plan), "toolingEvidence": tooling["evidence"],
        "toolingPublicKey": tooling["publicKey"], "javaExecutable": tooling["javaExecutable"],
        "toolingKeyring": tooling["keyring"], "toolingKeysDirectory": tooling["keysDirectory"],
        "toolingTrustDomain": tooling["requiredTrustDomain"], "validations": records,
        "contractDigest": digests.pop(), "componentDigests": components}
    request_inventory = regular_file_inventory(requests_root)
    unchanged()
    with tempfile.TemporaryDirectory(prefix=".core-metadata-bootstrap-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "policy.json"
        write_canonical_json(staged, policy)
        if regular_file_inventory(requests_root) != request_inventory:
            raise ValueError("Core metadata caller requests changed before policy publication")
        unchanged()
        os.link(staged, destination, follow_symlinks=False)
    unchanged()
    if (regular_file_inventory(requests_root) != request_inventory or
            load_canonical_json_bytes(read_regular_file_bytes(destination,
                reject_symlink_parents=True)) != policy):
        raise ValueError("Core metadata bootstrap policy changed during publication")
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery", "state", "requests-root", "destination",
                 "sdk-validation-tooling", "keyring", "keys-directory", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("expected-build-key", "sdk-inputs-artifact-sha256", "trusted-workflow-sha"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--sdk-inputs-artifact-id", type=int, required=True)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    parser.add_argument("--native-compiler-archive", action="append", default=[], metavar="TARGET=PATH")
    args = vars(parser.parse_args(argv))
    try:
        pairs = [value.split("=", 1) for value in args.pop("native_compiler_archive")]
        if (any(len(pair) != 2 or not pair[0] or not pair[1] for pair in pairs)
                or len({pair[0] for pair in pairs}) != len(pairs)):
            raise ValueError("Core metadata native archives require unique TARGET=PATH values")
        prepare(**args, native_compiler_archives={key: value for key, value in pairs},
                environ=os.environ, token=os.environ["GITHUB_TOKEN"])
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
