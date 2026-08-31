from __future__ import annotations

import base64
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any

from .inventory import (
    load_canonical_json,
    public_key_fingerprint,
    require_array,
    require_exact_keys,
    require_integer,
    require_sha256,
)


ALGORITHM = "ssh-ed25519"
NAMESPACE = "codex-agent-product-v1"
KEY_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
SSHSIG_HEADER = b"-----BEGIN SSH SIGNATURE-----\n"
SSHSIG_FOOTER = b"-----END SSH SIGNATURE-----\n"


def _require_canonical_sshsig(contents: bytes) -> None:
    if type(contents) is not bytes or not contents.startswith(SSHSIG_HEADER) or not contents.endswith(SSHSIG_FOOTER):
        raise ValueError("Product SSHSIG armor is malformed")
    body = contents[len(SSHSIG_HEADER):-len(SSHSIG_FOOTER)]
    lines = body.splitlines(keepends=True)
    if not lines or any(not line.endswith(b"\n") for line in lines):
        raise ValueError("Product SSHSIG body is not LF-terminated")
    encoded_lines = [line[:-1] for line in lines]
    if any(not line or len(line) > 70 for line in encoded_lines) or \
            any(len(line) != 70 for line in encoded_lines[:-1]):
        raise ValueError("Product SSHSIG body wrapping is noncanonical")
    encoded = b"".join(encoded_lines)
    try:
        blob = base64.b64decode(encoded, validate=True)
    except ValueError as error:
        raise ValueError("Product SSHSIG body is not strict Base64") from error
    canonical_body = b"".join(encoded[index:index + 70] + b"\n" for index in range(0, len(encoded), 70))
    if base64.b64encode(blob) != encoded or contents != SSHSIG_HEADER + canonical_body + SSHSIG_FOOTER:
        raise ValueError("Product SSHSIG armor is noncanonical")
    if not blob.startswith(b"SSHSIG"):
        raise ValueError("Product SSHSIG binary envelope is invalid")


def validate_signing_metadata(value: Any, *, trust_domain: str | None = None) -> dict[str, Any]:
    metadata = require_exact_keys(
        value,
        {"algorithm", "namespace", "trustDomain", "keyId", "fingerprint"},
        "signing metadata",
    )
    if metadata["algorithm"] != ALGORITHM:
        raise ValueError("Product signing algorithm must be ssh-ed25519")
    if metadata["namespace"] != NAMESPACE:
        raise ValueError("Product signing namespace is invalid")
    if metadata["trustDomain"] not in {"development", "release"}:
        raise ValueError("Product signing trustDomain is invalid")
    if trust_domain is not None and metadata["trustDomain"] != trust_domain:
        raise ValueError(f"Product signing metadata is not {trust_domain} trust")
    if type(metadata["keyId"]) is not str or KEY_ID.fullmatch(metadata["keyId"]) is None:
        raise ValueError("Signing metadata keyId is invalid")
    require_sha256(metadata["fingerprint"], "signing metadata.fingerprint")
    return metadata


def _key_record(value: Any, label: str) -> dict[str, Any]:
    record = require_exact_keys(value, {"keyId", "fingerprint"}, label)
    if type(record["keyId"]) is not str or KEY_ID.fullmatch(record["keyId"]) is None:
        raise ValueError(f"{label}.keyId is invalid")
    require_sha256(record["fingerprint"], f"{label}.fingerprint")
    return record


def public_key_path(keys_directory: Path, key_id: str) -> Path:
    if type(key_id) is not str or KEY_ID.fullmatch(key_id) is None:
        raise ValueError("Product signing key ID is invalid")
    return Path(keys_directory) / f"{key_id}.pub"


def _verify_public_key(record: dict[str, Any], keys_directory: Path) -> Path:
    path = public_key_path(keys_directory, record["keyId"])
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Product public key is missing or unsafe: {path}")
    contents = path.read_bytes()
    if public_key_fingerprint(contents) != record["fingerprint"]:
        raise ValueError(f"Product public key fingerprint mismatch: {record['keyId']}")
    return path


def validate_keyring(value: Any, keys_directory: Path) -> dict[str, Any]:
    keyring = require_exact_keys(
        value,
        {"schemaVersion", "namespace", "algorithm", "trustDomain", "activeKey", "retiredKeys"},
        "product signing keyring",
    )
    if require_integer(keyring["schemaVersion"], "product signing keyring.schemaVersion", 1) != 1:
        raise ValueError("Unsupported product signing keyring schemaVersion")
    if keyring["namespace"] != NAMESPACE or keyring["algorithm"] != ALGORITHM:
        raise ValueError("Product signing keyring algorithm or namespace is invalid")
    if keyring["trustDomain"] != "release":
        raise ValueError("Tracked product signing keyring must be release trust")
    active = None if keyring["activeKey"] is None else _key_record(keyring["activeKey"], "active key")
    retired_values = require_array(keyring["retiredKeys"], "product signing keyring.retiredKeys")
    retired = [_key_record(member, f"retired key[{index}]") for index, member in enumerate(retired_values)]
    retired_ids = [record["keyId"] for record in retired]
    if retired_ids != sorted(retired_ids) or len(retired_ids) != len(set(retired_ids)):
        raise ValueError("Retired product keys must be sorted and unique")
    if active is not None and active["keyId"] in retired_ids:
        raise ValueError("Active product key cannot also be retired")
    records = ([active] if active is not None else []) + retired
    fingerprints = [record["fingerprint"] for record in records]
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError("Product key fingerprints must be unique")
    for record in records:
        _verify_public_key(record, Path(keys_directory))
    return keyring


def load_keyring(path: Path, keys_directory: Path) -> dict[str, Any]:
    return validate_keyring(load_canonical_json(path), keys_directory)


def require_active_release_key(keyring: dict[str, Any], keys_directory: Path) -> tuple[dict[str, Any], Path]:
    validate_keyring(keyring, keys_directory)
    if keyring["activeKey"] is None:
        raise ValueError("No active release product-signing key is configured")
    record = keyring["activeKey"]
    return record, _verify_public_key(record, Path(keys_directory))


def public_key_for_metadata(
    metadata: Any,
    keyring: dict[str, Any],
    keys_directory: Path,
    *,
    allow_retired: bool,
) -> Path:
    signing = validate_signing_metadata(metadata, trust_domain="release")
    validate_keyring(keyring, keys_directory)
    records = []
    if keyring["activeKey"] is not None:
        records.append(keyring["activeKey"])
    if allow_retired:
        records.extend(keyring["retiredKeys"])
    matches = [record for record in records if record["keyId"] == signing["keyId"]]
    if len(matches) != 1 or matches[0]["fingerprint"] != signing["fingerprint"]:
        raise ValueError("Signing metadata does not identify an allowed release key")
    return _verify_public_key(matches[0], Path(keys_directory))


def generate_development_key(directory: Path) -> tuple[Path, Path, dict[str, Any]]:
    if shutil.which("ssh-keygen") is None:
        raise RuntimeError("ssh-keygen is required for product signing")
    directory = Path(directory)
    if directory.is_symlink():
        raise ValueError("Development signing directory is unsafe")
    directory.mkdir(parents=True, exist_ok=True)
    private_key = directory / "development-ed25519"
    if private_key.exists() or private_key.with_suffix(".pub").exists():
        raise ValueError("Development signing key destination already exists")
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    public_key = Path(f"{private_key}.pub")
    if private_key.is_symlink() or public_key.is_symlink():
        raise ValueError("Generated development signing key is unsafe")
    if stat.S_IMODE(private_key.stat().st_mode) & 0o077:
        raise ValueError("Generated development private key permissions are too broad")
    public_parts = public_key.read_text(encoding="ascii").split()
    if len(public_parts) < 2 or public_parts[0] != ALGORITHM:
        raise ValueError("ssh-keygen produced an unexpected public key")
    public_bytes = f"{public_parts[0]} {public_parts[1]}\n".encode("ascii")
    public_key.write_bytes(public_bytes)
    fingerprint = public_key_fingerprint(public_bytes)
    metadata = {
        "algorithm": ALGORITHM,
        "namespace": NAMESPACE,
        "trustDomain": "development",
        "keyId": f"development-{fingerprint.removeprefix('sha256:')[:16]}",
        "fingerprint": fingerprint,
    }
    validate_signing_metadata(metadata, trust_domain="development")
    return private_key, public_key, metadata


def sign_manifest(manifest: Path, private_key: Path, metadata: Any) -> Path:
    signing = validate_signing_metadata(metadata)
    manifest = Path(manifest)
    private_key = Path(private_key)
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Manifest to sign is missing or unsafe")
    if private_key.is_symlink() or not private_key.is_file():
        raise ValueError("Product signing private key is missing or unsafe")
    manifest_value = load_canonical_json(manifest)
    if type(manifest_value) is not dict or manifest_value.get("signing") != signing:
        raise ValueError("Manifest signing metadata does not match the requested signer")
    generated_signature = Path(f"{manifest}.sig")
    signature = manifest.with_suffix(".sig")
    if generated_signature.exists() or generated_signature.is_symlink() or \
            signature.exists() or signature.is_symlink():
        raise ValueError("Product signature destination already exists")
    try:
        subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n", signing["namespace"], str(manifest)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if generated_signature.is_symlink() or not generated_signature.is_file():
            raise ValueError("ssh-keygen did not produce a canonical detached SSHSIG")
        _require_canonical_sshsig(generated_signature.read_bytes())
        os.replace(generated_signature, signature)
    except Exception:
        generated_signature.unlink(missing_ok=True)
        raise
    return signature


def verify_manifest_signature(
    manifest: Path,
    signature: Path,
    public_key: Path,
    metadata: Any,
) -> None:
    signing = validate_signing_metadata(metadata)
    manifest = Path(manifest)
    signature = Path(signature)
    public_key = Path(public_key)
    for path, label in ((manifest, "manifest"), (signature, "signature"), (public_key, "public key")):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Product {label} is missing or unsafe")
    _require_canonical_sshsig(signature.read_bytes())
    manifest_value = load_canonical_json(manifest)
    if type(manifest_value) is not dict or manifest_value.get("signing") != signing:
        raise ValueError("Manifest signing metadata does not match the verifier metadata")
    if public_key_fingerprint(public_key.read_bytes()) != signing["fingerprint"]:
        raise ValueError("Product signature metadata/public-key fingerprint mismatch")
    with tempfile.TemporaryDirectory(prefix="codex-agent-signature-") as temporary:
        allowed_signers = Path(temporary) / "allowed-signers"
        allowed_signers.write_bytes(b"codex-agent-product " + public_key.read_bytes())
        result = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(allowed_signers),
                "-I",
                "codex-agent-product",
                "-n",
                signing["namespace"],
                "-s",
                str(signature),
            ],
            input=manifest.read_bytes(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    if result.returncode != 0:
        raise ValueError("Product SSHSIG verification failed")


def require_release_signing_metadata(value: Any) -> dict[str, Any]:
    return validate_signing_metadata(value, trust_domain="release")
