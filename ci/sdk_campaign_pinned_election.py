"""Hold independently pinned SDK phase selections before observing a campaign.

The protected caller supplies policy files and their independently approved
digests. This is input custody, not original-upload or release admission.
"""

from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
import os
from pathlib import Path
from types import MappingProxyType

from ci.sdk_apple_js_campaign_election import load_family_election as load_apple_js
from ci.sdk_campaign_core_android_election import load_core_android_election
from ci.sdk_campaign_native_policy import load_native_election
from ci.sdk_campaign_apple_js_semantic_policy import load_apple_js_semantic_policy
from ci.sdk_campaign_core_android_semantic_policy import load_core_android_semantic_policy
from ci.sdk_campaign_native_semantic_policy import load_native_semantic_policy
from products.inventory import read_regular_file_bytes, require_sha256, sha256_bytes
from products.inventory import (
    load_canonical_json_bytes, require_exact_keys, require_integer,
    require_relative_path, require_semver, require_string,
)
from products.receipt import validate_producer
from products.registry import PhaseInstanceId
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from products.signing_isolation import require_no_signing_secret


_LOADERS = {
    "core-android": load_core_android_election,
    "native": load_native_election,
    "apple-js": load_apple_js,
}


@contextmanager
def held_pinned_sdk_campaign_authority(path: Path, expected_sha256: str):
    """Hold one externally approved input manifest, never an observed state file."""
    require_no_signing_secret(os.environ)
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.resolve(strict=True) != path):
        raise ValueError("SDK campaign authority requires a canonical absolute file")
    expected = require_sha256(expected_sha256, "SDK campaign authority digest")
    raw = read_regular_file_bytes(path, max_bytes=1024 * 1024,
        reject_symlink_parents=True)
    if sha256_bytes(raw) != expected:
        raise ValueError("SDK campaign authority differs from independent digest")
    document = require_exact_keys(load_canonical_json_bytes(raw),
        {"schemaVersion", "product", "sdkVersion", "electionSha256",
         "semanticSha256", "artifactPaths", "completedCatalogPin"},
        "SDK campaign authority")
    if type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1 \
            or document["product"] != "sdk":
        raise ValueError("SDK campaign authority has the wrong schema or product")
    sdk_version = require_semver(document["sdkVersion"], "SDK campaign version")
    digests = {}
    for name in ("electionSha256", "semanticSha256"):
        selected = require_exact_keys(document[name], set(_LOADERS),
            f"SDK campaign {name}")
        digests[name] = {family: require_sha256(value, f"{family} {name}")
                         for family, value in selected.items()}
    rows = document["artifactPaths"]
    if type(rows) is not list or len(rows) != len(SDK_CAMPAIGN_INSTANCES):
        raise ValueError("SDK campaign authority requires exactly 62 artifact paths")
    artifact_paths, order = {}, []
    for row in rows:
        row = require_exact_keys(row, {"identity", "relativePath"},
            "SDK campaign artifact path")
        identity = require_exact_keys(row["identity"],
            {"product", "component", "phase", "target"},
            "SDK campaign artifact identity")
        instance = PhaseInstanceId(*(require_string(identity[field], field) for field in
            ("product", "component", "phase", "target")))
        if instance not in SDK_CAMPAIGN_INSTANCES or instance in artifact_paths:
            raise ValueError("SDK campaign authority has an unknown or duplicate artifact")
        artifact_paths[instance] = require_relative_path(row["relativePath"],
            "SDK campaign artifact path")
        order.append(instance)
    if order != sorted(SDK_CAMPAIGN_INSTANCES):
        raise ValueError("SDK campaign authority artifact paths must be exact and sorted")
    from ci.sdk_campaign_catalog_producer import _COMPLETED_CATALOG_PIN_KEYS
    catalog = dict(require_exact_keys(document["completedCatalogPin"],
        _COMPLETED_CATALOG_PIN_KEYS, "SDK campaign completed catalog pin"))
    producer = validate_producer(catalog["producer"])
    if producer["event"] != "pull_request":
        raise ValueError("SDK campaign completed catalog must be a PR producer")
    catalog["producer"] = dict(producer)
    require_integer(catalog["artifact_id"], "SDK campaign catalog artifact ID", 1)
    for field in ("artifact_sha256", "index_sha256", "public_key_sha256"):
        require_sha256(catalog[field], "SDK campaign catalog " + field)
    for field in ("artifact_name", "trusted_job_name"):
        require_string(catalog[field], "SDK campaign catalog " + field)
    require_relative_path(catalog["trusted_workflow_path"],
        "SDK campaign catalog workflow")
    authority = {"sdkVersion": sdk_version, **digests,
                 "artifactPaths": artifact_paths, "completedCatalogPin": catalog}
    before = deepcopy(authority)
    try:
        yield MappingProxyType(authority)
    finally:
        require_no_signing_secret(os.environ)
        if authority != before or read_regular_file_bytes(path, max_bytes=1024 * 1024,
                reject_symlink_parents=True) != raw:
            raise ValueError("SDK campaign authority changed during replay")


@contextmanager
def held_pinned_sdk_campaign_semantics(policy_files: Mapping[str, Path],
        expected_sha256: Mapping[str, str]):
    """Hold all eight typed semantic controls from three independently pinned files."""
    require_no_signing_secret(os.environ)
    if (not isinstance(policy_files, Mapping) or not isinstance(expected_sha256, Mapping)
            or set(policy_files) != set(_LOADERS) or set(expected_sha256) != set(_LOADERS)):
        raise ValueError("SDK semantic policy requires all three independent families")
    pinned, controls, seen_paths = {}, {}, set()
    for family in _LOADERS:
        path = policy_files[family]
        if (not isinstance(path, Path) or not path.is_absolute()
                or path.resolve(strict=True) != path or path in seen_paths):
            raise ValueError("SDK semantic policy requires distinct canonical absolute files")
        seen_paths.add(path)
        raw = read_regular_file_bytes(path, max_bytes=1024 * 1024,
            reject_symlink_parents=True)
        expected = require_sha256(expected_sha256[family], f"{family} semantic digest")
        if sha256_bytes(raw) != expected:
            raise ValueError(f"{family} semantic policy differs from independent digest")
        if family == "core-android":
            maven, core_validation, core_policy, core_metadata, android, reread = \
                load_core_android_semantic_policy(path)
            controls.update(maven_controls=maven,
                core_validation_controls=core_validation,
                core_validation_policy=core_policy,
                core_metadata_control=core_metadata, android_control=android)
        elif family == "native":
            native, reread = load_native_semantic_policy(path, expected)
            controls["native_control"] = native
        else:
            apple, javascript, reread = load_apple_js_semantic_policy(path)
            controls.update(apple_control=apple, javascript_control=javascript)
        if reread != raw:
            raise ValueError(f"{family} semantic policy changed while reading")
        pinned[family] = (path, raw)
    if set(controls) != {"maven_controls", "core_validation_controls",
            "core_validation_policy", "core_metadata_control", "android_control",
            "native_control", "apple_control", "javascript_control"}:
        raise ValueError("SDK semantic policy lacks an exact verifier control")
    before = deepcopy(controls)
    try:
        yield MappingProxyType(controls)
    finally:
        require_no_signing_secret(os.environ)
        if controls != before or any(read_regular_file_bytes(path,
                max_bytes=1024 * 1024, reject_symlink_parents=True) != raw
                for path, raw in pinned.values()):
            raise ValueError("SDK semantic policy changed during campaign replay")


@contextmanager
def held_pinned_sdk_campaign_election(policy_files: Mapping[str, Path],
        expected_sha256: Mapping[str, str]):
    """Yield exact 62 caller selections, rechecking every pinned file on exit.

    Enter this context before any state/catalog observation. The digest source
    must be protected independently of these files; matching self-supplied
    digests do not grant trust.
    """
    require_no_signing_secret(os.environ)
    if (not isinstance(policy_files, Mapping) or not isinstance(expected_sha256, Mapping)
            or set(policy_files) != set(_LOADERS) or set(expected_sha256) != set(_LOADERS)):
        raise ValueError("SDK campaign election requires all three independent families")
    fresh, reused, pinned, seen_paths = {}, {}, {}, set()
    for family, loader in _LOADERS.items():
        path = policy_files[family]
        if (not isinstance(path, Path) or not path.is_absolute()
                or path.resolve(strict=True) != path):
            raise ValueError("SDK election policy requires an absolute normalized caller-owned file")
        if path in seen_paths:
            raise ValueError("SDK election policy files must be distinct")
        seen_paths.add(path)
        expected = require_sha256(expected_sha256[family], f"{family} SDK election digest")
        family_fresh, family_reused, raw = loader(path)
        if sha256_bytes(raw) != expected:
            raise ValueError(f"{family} SDK election differs from its independent digest")
        if set(fresh) & (set(family_fresh) | set(family_reused)) or \
                set(reused) & (set(family_fresh) | set(family_reused)):
            raise ValueError("SDK election repeats a phase across families")
        fresh.update(family_fresh)
        reused.update(family_reused)
        pinned[family] = (path, raw)
    if set(fresh) & set(reused) or set(fresh) | set(reused) != SDK_CAMPAIGN_INSTANCES:
        raise ValueError("SDK election does not cover exactly 62 disjoint phases")
    if len({request["expected_product_version"] for request in (*fresh.values(), *reused.values())}) != 1:
        raise ValueError("SDK election requires one exact SDK version")
    selections_before = deepcopy((fresh, reused))
    try:
        yield MappingProxyType(fresh), MappingProxyType(reused)
    finally:
        require_no_signing_secret(os.environ)
        if (fresh, reused) != selections_before or any(
                read_regular_file_bytes(path, max_bytes=1024 * 1024,
                    reject_symlink_parents=True) != raw for path, raw in pinned.values()):
            raise ValueError("SDK election changed during campaign observation")
