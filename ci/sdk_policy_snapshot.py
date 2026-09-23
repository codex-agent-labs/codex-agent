"""Content snapshot of caller-owned SDK admission policies and their path closure.

The digest is invocation-only: it pins independently supplied inputs across
state capture and platform setup. It is not product evidence or a trust token.
"""

import os
from pathlib import Path

from ci.products.inventory import (canonical_json_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys, sha256_bytes, sha256_file)
from ci.products.sdk_android_metadata_admission import _policy_arguments as android_arguments
from ci.products.sdk_apple_validation_admission import apple_validation_policy_arguments
from ci.products.sdk_facade_inputs import _request as facade_request, _sources as facade_sources
from ci.products.sdk_facade_metadata_admission import _arguments as core_arguments
from ci.products.sdk_validation_inputs import _request_inventory
from ci.products import sdk_android_validation_phase
from ci.products.signing_isolation import require_no_signing_secret


def _snapshot(paths):
    result = []
    for path in sorted({Path(value) for value in paths}, key=str):
        if not path.is_absolute() or path.resolve(strict=True) != path:
            raise ValueError("SDK caller policy paths must be absolute and non-symbolic")
        if path.is_dir():
            result.append({"path": str(path), "kind": "directory",
                           "inventory": regular_file_inventory(path, allow_empty=True)})
        elif path.is_file():
            result.append({"path": str(path), "kind": "file",
                           "sha256": sha256_file(path, reject_symlink_parents=True)})
        else:
            raise ValueError("SDK caller policy path must be a regular file or directory")
    return sha256_bytes(canonical_json_bytes(result))


def snapshot_policy_closure(kind, path):
    """Hash one strict policy and all paths selected by its typed schema."""
    require_no_signing_secret(os.environ)
    path = Path(path)
    raw = read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                  reject_symlink_parents=True)
    policy = load_canonical_json_bytes(raw)
    paths = {path}
    if kind == "apple-validation":
        arguments = apple_validation_policy_arguments(policy)
        paths.update(value for value in arguments.values() if isinstance(value, Path))
    elif kind == "core-metadata":
        descriptor = require_exact_keys(policy, {"evidenceRoot", "records", "policy"}, "Core metadata descriptor")
        arguments = core_arguments(descriptor["policy"])
        paths.add(Path(descriptor["evidenceRoot"]))
        paths.update(value for value in arguments.values() if isinstance(value, Path))
        for original in arguments["validations"].values():
            paths.update(Path(original[name]) for name in ("captureRoot", "facadeRequest", "validationReceipt"))
            if "nativeCompilerArchive" in original:
                paths.add(Path(original["nativeCompilerArchive"]))
            request, _ = facade_request(Path(original["facadeRequest"]))
            _, trees, files = facade_sources(request)
            paths.update(trees.values())
            paths.update(files.values())
            paths.update(_request_inventory(Path(request["compatibilityRequest"])))
    elif kind == "android-metadata":
        descriptor = require_exact_keys(policy, {"evidenceRoot", "records", "policy"}, "Android metadata descriptor")
        arguments = android_arguments(descriptor["policy"])
        paths.add(Path(descriptor["evidenceRoot"]))
        paths.update(value for value in arguments.values() if isinstance(value, Path))
        trees, files = sdk_android_validation_phase._contract_sources(arguments["binary_contract_evidence"])
        paths.update(trees.values())
        paths.update(files.values())
        paths.update(_request_inventory(arguments["compatibility_request"]))
    else:
        raise ValueError("Unsupported SDK caller policy kind")
    digest = _snapshot(paths)
    if read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                               reject_symlink_parents=True) != raw:
        raise ValueError("SDK caller policy changed during snapshot")
    return digest
