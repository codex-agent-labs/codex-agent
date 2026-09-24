"""Reference verifier for an SDK-pinned root and a release-signed Runtime library.

The caller must supply the SDK-embedded root public key, never one discovered
beside an external Runtime. The returned claim does not authorize loading a
different file: language loaders must hash their private library snapshot.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from typing import Any

from .aggregate import RUNTIME_TARGETS, _compatible_range, _stable_semver_tuple, validate_sdk_compatibility
from .inventory import (
    load_canonical_json_bytes, publish_regular_tree,
    public_key_fingerprint,
    read_regular_file_bytes,
    regular_file_inventory,
    require_exact_keys,
    require_integer,
    require_sha256,
    sha256_bytes,
    sha256_file, write_canonical_json,
)
from .signatures import (
    NAMESPACE,
    _require_canonical_sshsig,
    public_key_for_metadata,
    validate_keyring,
    validate_signing_metadata,
)


ROOT_NAMESPACE = "codex-agent-sdk-runtime-root-v1"
ROOT_SCOPE = "desktop-runtime-library"
ROOT_PRINCIPAL = b"codex-agent-sdk-runtime-root"
PRODUCT_PRINCIPAL = b"codex-agent-product"
_JSON_LIMIT = 1024 * 1024
_SIGNATURE_LIMIT = 1024 * 1024
_IDENTITY_FIELDS = {
    "schemaVersion", "componentId", "runtimeCompatibilityVersion", "contractDigest",
    "contractComponentDigest", "cAbiVersion", "target", "appServerVersion", "buildInputDigest",
}
_AUTHORIZATION_FIELDS = {
    "schemaVersion", "kind", "runtimeVersion", "runtimeIdentity", "runtimeLibrarySha256",
    "variantBundleSha256", "variantManifestSha256", "aggregateManifestSha256",
    "variantAttestationSha256", "aggregateAttestationSha256", "signing",
}


def validate_root_delegation(value: Any) -> dict[str, Any]:
    delegation = require_exact_keys(value, {
        "schemaVersion", "kind", "scope", "rootFingerprint", "keyringSha256",
    }, "SDK Runtime root delegation")
    if (require_integer(delegation["schemaVersion"], "root delegation schema", 1) != 1
            or delegation["kind"] != "sdk-runtime-release-keyring-delegation"
            or delegation["scope"] != ROOT_SCOPE):
        raise ValueError("SDK Runtime root delegation identity is invalid")
    require_sha256(delegation["rootFingerprint"], "root delegation fingerprint")
    require_sha256(delegation["keyringSha256"], "root delegation keyring digest")
    return delegation


def validate_library_authorization(value: Any) -> dict[str, Any]:
    claim = require_exact_keys(value, _AUTHORIZATION_FIELDS, "Runtime library authorization")
    if (require_integer(claim["schemaVersion"], "library authorization schema", 1) != 1
            or claim["kind"] != "desktop-runtime-library-authorization"):
        raise ValueError("Runtime library authorization identity is invalid")
    _stable_semver_tuple(claim["runtimeVersion"], "authorized Runtime version")
    identity = require_exact_keys(claim["runtimeIdentity"], _IDENTITY_FIELDS, "authorized Runtime identity")
    if require_integer(identity["schemaVersion"], "authorized identity schema", 1) != 1:
        raise ValueError("Authorized Runtime identity schema is unsupported")
    if identity["target"] not in RUNTIME_TARGETS:
        raise ValueError("Authorized Runtime target is unsupported")
    for field in ("componentId", "contractDigest", "contractComponentDigest", "buildInputDigest"):
        require_sha256(identity[field], f"authorized Runtime identity.{field}")
    for field in ("runtimeCompatibilityVersion", "cAbiVersion", "appServerVersion"):
        _stable_semver_tuple(identity[field], f"authorized Runtime identity.{field}")
    abi_major, abi_minor, abi_patch = _stable_semver_tuple(identity["cAbiVersion"], "authorized Runtime ABI")
    if abi_major > 255 or abi_minor > 255 or abi_patch > 65535:
        raise ValueError("Authorized Runtime ABI exceeds its encoded field widths")
    for field in (
        "runtimeLibrarySha256", "variantBundleSha256", "variantManifestSha256",
        "aggregateManifestSha256", "variantAttestationSha256", "aggregateAttestationSha256",
    ):
        require_sha256(claim[field], f"Runtime library authorization.{field}")
    validate_signing_metadata(claim["signing"], trust_domain="release")
    return claim


def _verify_sshsig(contents: bytes, signature: bytes, public_key: bytes, *, namespace: str,
                   principal: bytes) -> None:
    _require_canonical_sshsig(signature)
    public_key_fingerprint(public_key)
    with tempfile.TemporaryDirectory(prefix="sdk-runtime-sshsig-") as temporary:
        root = Path(temporary)
        allowed = root / "allowed-signers"
        detached = root / "signature.sig"
        allowed.write_bytes(principal + b" " + public_key)
        detached.write_bytes(signature)
        try:
            result = subprocess.run(
                ["ssh-keygen", "-Y", "verify", "-f", str(allowed), "-I", principal.decode("ascii"),
                 "-n", namespace, "-s", str(detached)],
                input=contents, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except OSError as error:
            raise ValueError("OpenSSH signature verifier is unavailable") from error
    if result.returncode != 0:
        raise ValueError("SDK Runtime release signature verification failed")


def issue_root_delegation(
    keyring_path: Path, keys_directory: Path, root_public_key: Path,
    root_private_key: Path, destination: Path,
) -> dict[str, Any]:
    """Publish root-approved signer policy; protected caller owns root-key custody."""
    keyring_bytes = read_regular_file_bytes(keyring_path, max_bytes=_JSON_LIMIT,
                                            reject_symlink_parents=True)
    keyring = validate_keyring(load_canonical_json_bytes(keyring_bytes), keys_directory)
    root_public_bytes = read_regular_file_bytes(root_public_key, max_bytes=4096,
                                               reject_symlink_parents=True)
    delegation = validate_root_delegation({
        "schemaVersion": 1, "kind": "sdk-runtime-release-keyring-delegation",
        "scope": ROOT_SCOPE, "rootFingerprint": public_key_fingerprint(root_public_bytes),
        "keyringSha256": sha256_bytes(keyring_bytes),
    })
    records = ([keyring["activeKey"]] if keyring["activeKey"] is not None else []) + keyring["retiredKeys"]
    with tempfile.TemporaryDirectory(prefix="sdk-runtime-root-issue-") as temporary:
        staged = Path(temporary).resolve() / "evidence"
        (staged / "keys").mkdir(parents=True)
        (staged / "release-keyring.json").write_bytes(keyring_bytes)
        for record in records:
            name = f"{record['keyId']}.pub"
            contents = read_regular_file_bytes(Path(keys_directory) / name, max_bytes=4096,
                                               reject_symlink_parents=True)
            (staged / "keys" / name).write_bytes(contents)
        validate_keyring(load_canonical_json_bytes(keyring_bytes), staged / "keys")
        manifest = staged / "root-delegation.json"
        write_canonical_json(manifest, delegation)
        try:
            subprocess.run(
                ["ssh-keygen", "-Y", "sign", "-f", str(root_private_key),
                 "-n", ROOT_NAMESPACE, str(manifest)],
                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ValueError("SDK Runtime root delegation signing failed") from error
        signature = Path(f"{manifest}.sig")
        signature_bytes = read_regular_file_bytes(signature, max_bytes=_SIGNATURE_LIMIT,
                                                  reject_symlink_parents=True)
        _verify_sshsig(manifest.read_bytes(), signature_bytes, root_public_bytes,
                       namespace=ROOT_NAMESPACE, principal=ROOT_PRINCIPAL)
        signature.replace(staged / "root-delegation.sig")
        if read_regular_file_bytes(keyring_path, max_bytes=_JSON_LIMIT,
                                   reject_symlink_parents=True) != keyring_bytes:
            raise ValueError("Release keyring changed while root delegation was issued")
        publish_regular_tree(staged, destination, expected_inventory=regular_file_inventory(staged))
    return delegation


def verify_external_library_authorization(
    evidence_root: Path,
    *,
    sdk_pinned_root_public_key: bytes,
    sdk_compatibility: dict[str, Any],
    target: str,
    library_snapshot: Path,
) -> dict[str, Any]:
    """Verify exact external evidence and one already-snapshotted library file.

    Production callers must take ``sdk_pinned_root_public_key`` from their own
    shipped SDK bytes and load only ``library_snapshot`` after this returns.
    """
    compatibility = validate_sdk_compatibility(sdk_compatibility)
    if target not in RUNTIME_TARGETS:
        raise ValueError("External Runtime target is unsupported")
    root = Path(evidence_root)
    keyring_bytes = read_regular_file_bytes(root / "release-keyring.json", max_bytes=_JSON_LIMIT,
                                            reject_symlink_parents=True)
    delegation_bytes = read_regular_file_bytes(root / "root-delegation.json", max_bytes=_JSON_LIMIT,
                                               reject_symlink_parents=True)
    delegation_signature = read_regular_file_bytes(root / "root-delegation.sig",
                                                   max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True)
    claim_bytes = read_regular_file_bytes(root / "runtime-library-authorization.json",
                                         max_bytes=_JSON_LIMIT, reject_symlink_parents=True)
    claim_signature = read_regular_file_bytes(root / "runtime-library-authorization.sig",
                                             max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True)
    delegation = validate_root_delegation(load_canonical_json_bytes(delegation_bytes))
    if (delegation["rootFingerprint"] != public_key_fingerprint(sdk_pinned_root_public_key)
            or delegation["keyringSha256"] != sha256_bytes(keyring_bytes)):
        raise ValueError("SDK Runtime delegation differs from the SDK-pinned root or exact keyring")
    _verify_sshsig(delegation_bytes, delegation_signature, sdk_pinned_root_public_key,
                   namespace=ROOT_NAMESPACE, principal=ROOT_PRINCIPAL)
    keyring = validate_keyring(load_canonical_json_bytes(keyring_bytes), root / "keys")
    claim = validate_library_authorization(load_canonical_json_bytes(claim_bytes))
    signer = public_key_for_metadata(claim["signing"], keyring, root / "keys", allow_retired=True)
    signer_bytes = read_regular_file_bytes(signer, max_bytes=4096, reject_symlink_parents=True)
    _verify_sshsig(claim_bytes, claim_signature, signer_bytes,
                   namespace=NAMESPACE, principal=PRODUCT_PRINCIPAL)
    expected_files = {
        "release-keyring.json", "root-delegation.json", "root-delegation.sig",
        "runtime-library-authorization.json", "runtime-library-authorization.sig",
    } | {
        f"keys/{record['keyId']}.pub"
        for record in ([keyring["activeKey"]] if keyring["activeKey"] is not None else [])
        + keyring["retiredKeys"]
    }
    if {record["relativePath"] for record in regular_file_inventory(root)} != expected_files:
        raise ValueError("External Runtime evidence contains extra or missing files")
    runtime = compatibility["runtime"]
    identity = claim["runtimeIdentity"]
    release_bounds = _compatible_range(runtime["compatibleReleaseRange"], "SDK Runtime release range")
    compatibility_bounds = _compatible_range(
        runtime["compatibleRuntimeCompatibilityRange"], "SDK Runtime compatibility range",
    )
    release_version = _stable_semver_tuple(claim["runtimeVersion"], "external Runtime release")
    compatibility_version = _stable_semver_tuple(
        identity["runtimeCompatibilityVersion"], "external Runtime compatibility",
    )
    abi = _stable_semver_tuple(identity["cAbiVersion"], "external Runtime ABI")
    if (identity["target"] != target or identity["contractDigest"] != runtime["requiredContractDigest"]
            or identity["schemaVersion"] != runtime["requiredIdentitySchema"]
            or not release_bounds[0] <= release_version < release_bounds[1]
            or not compatibility_bounds[0] <= compatibility_version < compatibility_bounds[1]
            or abi[0] != runtime["requiredAbiMajor"] or abi[1] < runtime["minimumAbiMinor"]):
        raise ValueError("External Runtime authorization is incompatible with this SDK")
    if sha256_file(library_snapshot, reject_symlink_parents=True) != claim["runtimeLibrarySha256"]:
        raise ValueError("External Runtime library differs from its signed authorization")
    return claim
