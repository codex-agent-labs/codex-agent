"""Verify an external Runtime using only the SDK's pinned trust root."""

from __future__ import annotations

import base64
import ctypes
import hashlib
import os
import re
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from ._ffi import (_canonical_json, _in_range, _range, _semver, _sha256,
                   _strict_json, _validate_absolute_regular_path)


_PRODUCT_NAMESPACE = "codex-agent-product-v1"
_ROOT_NAMESPACE = "codex-agent-sdk-runtime-root-v1"
_KEY_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")


def _read(path: Path, limit: int = 1024 * 1024) -> bytes:
    _validate_absolute_regular_path(path, "Runtime evidence")
    if path.stat().st_size > limit:
        raise OSError("Runtime evidence exceeds its size limit")
    return path.read_bytes()


def _json(raw: bytes, label: str) -> dict[str, Any]:
    value = _strict_json(raw, label)
    if raw != _canonical_json(value, True):
        raise OSError(f"{label} is not canonical JSON")
    return value


def _exact(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise OSError(f"invalid {label}")
    return value


def _fingerprint(public: bytes) -> str:
    match = re.fullmatch(rb"ssh-ed25519 ([A-Za-z0-9+/]+={0,2})\n", public)
    if match is None:
        raise OSError("invalid Ed25519 public key")
    try:
        blob = base64.b64decode(match.group(1), validate=True)
    except ValueError as error:
        raise OSError("invalid Ed25519 public key") from error
    prefix = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32)
    if len(blob) != len(prefix) + 32 or not blob.startswith(prefix) or base64.b64encode(blob) != match.group(1):
        raise OSError("invalid Ed25519 public key")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


def _verify_signature(message: bytes, signature: bytes, public: bytes, namespace: str, principal: str) -> None:
    header = b"-----BEGIN SSH SIGNATURE-----\n"
    footer = b"-----END SSH SIGNATURE-----\n"
    if not signature.startswith(header) or not signature.endswith(footer):
        raise OSError("invalid Runtime evidence signature")
    lines = signature[len(header):-len(footer)].splitlines(keepends=True)
    if not lines or any(not line.endswith(b"\n") or not 1 <= len(line[:-1]) <= 70 for line in lines) or any(
            len(line[:-1]) != 70 for line in lines[:-1]):
        raise OSError("invalid Runtime evidence signature")
    encoded = b"".join(line[:-1] for line in lines)
    try:
        blob = base64.b64decode(encoded, validate=True)
    except ValueError as error:
        raise OSError("invalid Runtime evidence signature") from error
    if not blob.startswith(b"SSHSIG") or base64.b64encode(blob) != encoded:
        raise OSError("invalid Runtime evidence signature")
    _fingerprint(public)
    with tempfile.TemporaryDirectory(prefix="codex-agent-runtime-signature-") as temporary:
        root = Path(temporary)
        allowed = root / "allowed-signers"
        detached = root / "signature.sig"
        allowed.write_bytes(principal.encode("ascii") + b" " + public)
        detached.write_bytes(signature)
        try:
            if os.name == "nt":
                system_directory = ctypes.create_unicode_buffer(32768)
                length = ctypes.windll.kernel32.GetSystemDirectoryW(system_directory, len(system_directory))
                if not 0 < length < len(system_directory):
                    raise OSError("Windows system directory is unavailable")
                verifier = Path(system_directory.value) / "OpenSSH" / "ssh-keygen.exe"
            else:
                verifier = Path("/usr/bin/ssh-keygen")
            if not verifier.is_file():
                raise OSError("System OpenSSH signature verifier is unavailable")
            result = subprocess.run(
                [str(verifier), "-Y", "verify", "-f", str(allowed), "-I", principal,
                 "-n", namespace, "-s", str(detached)],
                input=message, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise OSError("OpenSSH signature verifier is unavailable") from error
    if result.returncode != 0:
        raise OSError("Runtime evidence signature verification failed")


def verify_external_runtime(snapshot: Path, evidence: Path, pinned_root: bytes,
                            compatibility: dict[str, Any], target: str) -> dict[str, Any]:
    """Return the exact signed claim for one already-snapshotted library."""
    if not evidence.is_absolute() or evidence.is_symlink() or not evidence.is_dir():
        raise OSError("Runtime evidence directory is missing or unsafe")
    root_fingerprint = _fingerprint(pinned_root)
    keyring_raw = _read(evidence / "release-keyring.json")
    delegation_raw = _read(evidence / "root-delegation.json")
    delegation = _exact(_json(delegation_raw, "Runtime root delegation"),
                        {"schemaVersion", "kind", "scope", "rootFingerprint", "keyringSha256"},
                        "Runtime root delegation")
    if (type(delegation["schemaVersion"]) is not int or delegation != {
        "schemaVersion": 1, "kind": "sdk-runtime-release-keyring-delegation",
        "scope": "desktop-runtime-library", "rootFingerprint": root_fingerprint,
        "keyringSha256": "sha256:" + hashlib.sha256(keyring_raw).hexdigest(),
    }):
        raise OSError("Runtime delegation differs from the SDK root or keyring")
    _verify_signature(delegation_raw, _read(evidence / "root-delegation.sig"), pinned_root,
                      _ROOT_NAMESPACE, "codex-agent-sdk-runtime-root")
    keyring = _exact(_json(keyring_raw, "Runtime release keyring"),
                     {"schemaVersion", "namespace", "algorithm", "trustDomain", "activeKey", "retiredKeys"},
                     "Runtime release keyring")
    if (type(keyring["schemaVersion"]) is not int or keyring["schemaVersion"] != 1 or keyring["namespace"] != _PRODUCT_NAMESPACE
            or keyring["algorithm"] != "ssh-ed25519" or keyring["trustDomain"] != "release"
            or not isinstance(keyring["retiredKeys"], list)):
        raise OSError("invalid Runtime release keyring")
    records = ([keyring["activeKey"]] if keyring["activeKey"] is not None else []) + keyring["retiredKeys"]
    keys: dict[str, bytes] = {}
    fingerprints: set[str] = set()
    for record in records:
        _exact(record, {"keyId", "fingerprint"}, "Runtime release key")
        key_id = record["keyId"]
        if not isinstance(key_id, str) or _KEY_ID.fullmatch(key_id) is None or key_id in keys:
            raise OSError("invalid Runtime release key ID")
        public = _read(evidence / "keys" / f"{key_id}.pub", 4096)
        fingerprint = _fingerprint(public)
        if fingerprint != record["fingerprint"] or fingerprint in fingerprints:
            raise OSError("Runtime release key fingerprint mismatch")
        keys[key_id] = public
        fingerprints.add(fingerprint)
    retired_ids = [record["keyId"] for record in keyring["retiredKeys"]]
    if retired_ids != sorted(retired_ids):
        raise OSError("invalid Runtime retired keys")
    claim_raw = _read(evidence / "runtime-library-authorization.json")
    claim = _exact(_json(claim_raw, "Runtime library authorization"), {
        "schemaVersion", "kind", "runtimeVersion", "runtimeIdentity", "runtimeLibrarySha256",
        "variantBundleSha256", "variantManifestSha256", "aggregateManifestSha256",
        "variantAttestationSha256", "aggregateAttestationSha256", "signing",
    }, "Runtime library authorization")
    signing = _exact(claim["signing"], {"algorithm", "namespace", "trustDomain", "keyId", "fingerprint"},
                     "Runtime authorization signing")
    if (signing["algorithm"] != "ssh-ed25519" or signing["namespace"] != _PRODUCT_NAMESPACE
            or signing["trustDomain"] != "release" or signing["keyId"] not in keys
            or signing["fingerprint"] != _fingerprint(keys[signing["keyId"]])):
        raise OSError("Runtime authorization signer is not delegated")
    _verify_signature(claim_raw, _read(evidence / "runtime-library-authorization.sig"),
                      keys[signing["keyId"]], _PRODUCT_NAMESPACE, "codex-agent-product")
    expected = {"release-keyring.json", "root-delegation.json", "root-delegation.sig",
                "runtime-library-authorization.json", "runtime-library-authorization.sig"} | {
                    f"keys/{key_id}.pub" for key_id in keys}
    entries = list(evidence.iterdir())
    if any(path.is_symlink() for path in entries) or {
            path.name for path in entries} != {name.split("/", 1)[0] for name in expected}:
        raise OSError("Runtime evidence contains extra or missing files")
    key_directory = evidence / "keys"
    if keys and (key_directory.is_symlink() or not key_directory.is_dir()):
        raise OSError("Runtime evidence key directory is unsafe")
    key_entries = list(key_directory.iterdir()) if key_directory.exists() else []
    actual = {path.name for path in key_entries}
    if any(path.is_symlink() or not path.is_file() for path in key_entries):
        raise OSError("Runtime evidence key directory is unsafe")
    if actual != {f"{key_id}.pub" for key_id in keys}:
        raise OSError("Runtime evidence contains extra or missing files")
    if type(claim["schemaVersion"]) is not int or claim["schemaVersion"] != 1 or claim["kind"] != "desktop-runtime-library-authorization":
        raise OSError("invalid Runtime authorization identity")
    for field in ("runtimeLibrarySha256", "variantBundleSha256", "variantManifestSha256",
                  "aggregateManifestSha256", "variantAttestationSha256", "aggregateAttestationSha256"):
        _sha256(claim[field], f"Runtime authorization {field}")
    identity = _exact(claim["runtimeIdentity"], {
        "schemaVersion", "componentId", "runtimeCompatibilityVersion", "contractDigest",
        "contractComponentDigest", "cAbiVersion", "target", "appServerVersion", "buildInputDigest",
    }, "authorized Runtime identity")
    for field in ("componentId", "contractDigest", "contractComponentDigest", "buildInputDigest"):
        _sha256(identity[field], f"authorized Runtime {field}")
    abi = _semver(identity["cAbiVersion"], "authorized Runtime ABI")
    _semver(identity["appServerVersion"], "authorized app-server version")
    release_range = _range(compatibility["runtime"]["compatibleReleaseRange"], "Runtime release range")
    compatible_range = _range(compatibility["runtime"]["compatibleRuntimeCompatibilityRange"], "Runtime compatibility range")
    if (type(identity["schemaVersion"]) is not int or identity["schemaVersion"] != compatibility["runtime"]["requiredIdentitySchema"]
            or identity["target"] != target
            or identity["contractDigest"] != compatibility["runtime"]["requiredContractDigest"]
            or not _in_range(claim["runtimeVersion"], release_range, "Runtime version")
            or not _in_range(identity["runtimeCompatibilityVersion"], compatible_range, "Runtime compatibility")
            or abi[0] != compatibility["runtime"]["requiredAbiMajor"]
            or abi[1] < compatibility["runtime"]["minimumAbiMinor"]
            or abi[0] > 255 or abi[1] > 255 or abi[2] > 65535):
        raise OSError("Runtime authorization is incompatible with this SDK")
    _validate_absolute_regular_path(snapshot, "Runtime library snapshot")
    if "sha256:" + hashlib.sha256(snapshot.read_bytes()).hexdigest() != claim["runtimeLibrarySha256"]:
        raise OSError("Runtime library differs from its signed authorization")
    return claim
