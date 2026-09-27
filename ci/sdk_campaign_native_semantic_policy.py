"""Decode independently pinned caller controls for all five native SDKs.

The digest must come from protected policy outside the observed campaign.
This reader grants no original, tooling, or release admission.
"""

import os
from pathlib import Path

from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_sha256, require_string, sha256_bytes,
)


_PATHS = {"repository", "compatibility_request", "runtime_stages", "staged_sdks",
          "tooling_evidence", "tooling_public_key", "java_executable"}
_OPTIONAL_PATHS = {"tooling_keyring", "tooling_keys_directory"}
_TEXT = {"policy_revision", "required_trust_domain"}


def load_native_semantic_policy(path: Path, expected_sha256: str):
    """Return verifier-ready controls and their exact canonical policy bytes."""
    expected = require_sha256(expected_sha256, "Native semantic policy digest")
    if not isinstance(path, Path) or not path.is_absolute() or os.path.normpath(str(path)) != str(path):
        raise ValueError("Native semantic policy path must be absolute and normalized")
    raw = read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True)
    if sha256_bytes(raw) != expected:
        raise ValueError("Native semantic policy differs from independent digest")
    policy = require_exact_keys(load_canonical_json_bytes(raw),
        {"schemaVersion", "family", "controls"}, "Native semantic policy")
    if type(policy["schemaVersion"]) is not int or policy["schemaVersion"] != 1 or policy["family"] != "native":
        raise ValueError("Native semantic policy has the wrong schema or family")
    controls = require_exact_keys(policy["controls"], _PATHS | _OPTIONAL_PATHS | _TEXT,
        "Native semantic controls")
    result = {}
    for name in _PATHS | _OPTIONAL_PATHS:
        value = controls[name]
        if name in _OPTIONAL_PATHS and value is None:
            result[name] = None
            continue
        value = require_string(value, f"Native semantic {name}")
        if (not Path(value).is_absolute() or os.path.normpath(value) != value
                or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ValueError(f"Native semantic {name} must be an absolute normalized path")
        result[name] = Path(value)
    for name in _TEXT:
        value = require_string(controls[name], f"Native semantic {name}")
        if value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError(f"Native semantic {name} must be canonical text")
        result[name] = value
    release = result["required_trust_domain"] == "release"
    if result["required_trust_domain"] not in {"release", "development"} or release != (
            result["tooling_keyring"] is not None and result["tooling_keys_directory"] is not None):
        raise ValueError("Native semantic tooling trust requires the exact release key pair")
    if result["java_executable"].name not in {"java", "java.exe"}:
        raise ValueError("Native semantic Java executable has the wrong name")
    return result, raw
