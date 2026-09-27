"""Decode caller-pinned Apple/JavaScript semantic controls before observation.

The caller authenticates the returned canonical bytes against an independent
digest and holds them unchanged through replay. This reader grants no trust to
any observed receipt, stage, handoff, or evidence record.
"""

import re
from pathlib import Path

from products.inventory import (load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, require_relative_path, require_sha256)
from products.sdk_apple_validation_admission import apple_validation_policy_arguments


_TARGETS = {"ios-arm64", "ios-simulator-arm64"}
_APPLE_KEYS = {"handoffs", "package_capture", "sdk_capture",
    "metadata_evidence_root", "metadata_evidence_records", "repository",
    "policy_revision", "policy"}
_JS_PATHS = {"repository", "compatibility_request", "package_receipt",
    "validation_receipt", "metadata_receipt", "contract_stage", "contract_receipt",
    "runtime_package_stage", "runtime_package_receipt", "runtime_validation_stage",
    "runtime_validation_receipt", "original_consumer_directory", "tooling_evidence",
    "tooling_public_key", "java_executable"}
_JS_OPTIONAL = {"tooling_keyring", "tooling_keys_directory"}
_JS_KEYS = _JS_PATHS | _JS_OPTIONAL | {"policy_revision", "required_trust_domain"}
_APPLE_POLICY_PATHS = {"plan", "attestationPublicKey", "keyring", "keysDirectory",
    "toolingEvidence", "toolingPublicKey", "javaExecutable", "toolingKeyring",
    "toolingKeysDirectory"}


def _path(value, label):
    if type(value) is not str or not value or "\\" in value or any(
            ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{label} must be a canonical absolute path")
    path = Path(value)
    if not path.is_absolute() or str(path) != value or ".." in path.parts:
        raise ValueError(f"{label} must be a canonical absolute path")
    return path


def _revision(value):
    if type(value) is not str or re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value) is None:
        raise ValueError("Apple/JavaScript policy revision must be a full lowercase Git object ID")
    return value


def load_apple_js_semantic_policy(path: Path):
    """Return (Apple kwargs, JavaScript kwargs, exact bytes) from pinned policy."""
    raw = read_regular_file_bytes(Path(path), max_bytes=1024 * 1024,
                                  reject_symlink_parents=True)
    document = require_exact_keys(load_canonical_json_bytes(raw),
        {"schemaVersion", "family", "apple", "javascript"}, "Apple/JavaScript semantic policy")
    if (type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1
            or document["family"] != "apple-js"):
        raise ValueError("Apple/JavaScript semantic policy has the wrong schema or family")

    apple = dict(require_exact_keys(document["apple"], _APPLE_KEYS, "Apple semantic control"))
    apple["repository"] = _path(apple["repository"], "Apple repository")
    apple["policy_revision"] = _revision(apple["policy_revision"])
    for field in ("package_capture", "sdk_capture", "metadata_evidence_root"):
        apple[field] = _path(apple[field], f"Apple {field}")
    apple["handoffs"] = {target: _path(value, f"Apple {target} handoff")
        for target, value in require_exact_keys(apple["handoffs"], _TARGETS,
            "Apple signed handoffs").items()}
    records = require_exact_keys(apple["metadata_evidence_records"], _TARGETS,
        "Apple metadata evidence records")
    for target, value in records.items():
        record = require_exact_keys(value, {"receiptSha256", "target", "evidenceRoot"},
            f"Apple {target} evidence record")
        require_sha256(record["receiptSha256"], f"Apple {target} receipt digest")
        if type(record["target"]) is not str or record["target"] != target:
            raise ValueError("Apple evidence record has the wrong target")
        require_relative_path(record["evidenceRoot"], f"Apple {target} evidence root")
        if apple["metadata_evidence_root"] / record["evidenceRoot"] != apple["handoffs"][target]:
            raise ValueError("Apple evidence record differs from its pinned handoff")
    if (len(set(apple["handoffs"].values())) != len(_TARGETS)
            or len({record["receiptSha256"] for record in records.values()}) != len(_TARGETS)):
        raise ValueError("Apple validation handoffs and receipt digests must be distinct")
    policy = apple["policy"]
    apple_validation_policy_arguments(policy)
    for field in _APPLE_POLICY_PATHS:
        if policy[field] is not None:
            _path(policy[field], f"Apple policy {field}")

    javascript = dict(require_exact_keys(document["javascript"], _JS_KEYS,
        "JavaScript semantic control"))
    for field in _JS_PATHS:
        javascript[field] = _path(javascript[field], f"JavaScript {field}")
    javascript["policy_revision"] = _revision(javascript["policy_revision"])
    if type(javascript["required_trust_domain"]) is not str or javascript["required_trust_domain"] not in {"development", "release"}:
        raise ValueError("JavaScript tooling trust domain must be development or release")
    for field in _JS_OPTIONAL:
        if javascript[field] is not None:
            javascript[field] = _path(javascript[field], f"JavaScript {field}")
    if (javascript["tooling_keyring"] is None) != (javascript["tooling_keys_directory"] is None):
        raise ValueError("JavaScript tooling keyring and directory must be supplied together")
    if (javascript["required_trust_domain"] == "release") != (javascript["tooling_keyring"] is not None):
        raise ValueError("JavaScript tooling trust requires the exact caller keyring pair")
    return apple, javascript, raw
