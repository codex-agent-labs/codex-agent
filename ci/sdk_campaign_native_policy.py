"""Decode the independently pinned native-family SDK campaign election.

This only snapshots caller policy before observation. It does not authenticate
the policy file or admit any SDK product for release.
"""

import os
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_integer, require_relative_path, require_semver, require_sha256,
    require_string, sha256_bytes,
)
from products.receipt import validate_producer
from products.registry import PhaseInstanceId
from products.sdk_campaign_native import NATIVE_CAMPAIGN_INSTANCES
from ci.sdk_campaign_catalog_producer import (
    _CUSTODY_REUSED_SELECTION_KEYS, _FRESH_SELECTION_KEYS, _REUSED_SELECTION_KEYS,
)


_IDENTITY_KEYS = {"product", "component", "phase", "target"}


def _route(request, path_field, job_field):
    path = require_relative_path(request[path_field], "Native SDK workflow path")
    parts = PurePosixPath(path).parts
    if (len(parts) != 3 or parts[:2] != (".github", "workflows")
            or not parts[2].endswith((".yml", ".yaml"))):
        raise ValueError("Native SDK workflow must be a reviewed workflow file")
    job = require_string(request[job_field], "Native SDK workflow job")
    if job != job.strip() or any(ord(char) < 32 or ord(char) == 127 for char in job):
        raise ValueError("Native SDK workflow job is not canonical text")


def load_native_election(path: Path):
    """Return exact native fresh/reused requests and the original pinned bytes."""
    raw = read_regular_file_bytes(Path(path), max_bytes=1024 * 1024,
        reject_symlink_parents=True)
    policy = require_exact_keys(load_canonical_json_bytes(raw),
        {"schemaVersion", "family", "selections"}, "Native SDK election")
    if type(policy["schemaVersion"]) is not int or policy["schemaVersion"] != 1 or policy["family"] != "native":
        raise ValueError("Native SDK election has the wrong schema or family")
    rows = policy["selections"]
    if type(rows) is not list or len(rows) != len(NATIVE_CAMPAIGN_INSTANCES):
        raise ValueError("Native SDK election requires exactly 36 selections")
    fresh, reused = {}, {}
    previous = None
    for row in rows:
        row = require_exact_keys(row, {"identity", "route", "request"},
            "Native SDK election row")
        identity = require_exact_keys(row["identity"], _IDENTITY_KEYS,
            "Native SDK election identity")
        instance = PhaseInstanceId(*(require_string(identity[field],
            f"Native SDK identity {field}") for field in
            ("product", "component", "phase", "target")))
        if instance not in NATIVE_CAMPAIGN_INSTANCES or (previous is not None and instance <= previous):
            raise ValueError("Native SDK election identities must be exact, unique, and sorted")
        previous = instance
        request = row["request"]
        if row["route"] == "fresh":
            request = dict(require_exact_keys(request, _FRESH_SELECTION_KEYS,
                "Fresh native SDK election"))
            request["producer"] = dict(validate_producer(request["producer"]))
            _route(request, "trusted_workflow_path", "trusted_job_name")
            target = fresh
        elif row["route"] == "same-pr":
            custody = type(request) is dict and "custody_ref" in request
            keys = (_CUSTODY_REUSED_SELECTION_KEYS if custody else
                _REUSED_SELECTION_KEYS |
                ({"failed_catalog_producer"} if type(request) is dict and
                    "failed_catalog_producer" in request else set()))
            request = dict(require_exact_keys(request, keys, "Reused native SDK election"))
            if "failed_catalog_producer" in request:
                request["failed_catalog_producer"] = dict(validate_producer(
                    request["failed_catalog_producer"]))
            if custody:
                require_string(request["custody_ref"], "Native SDK custody reference")
            else:
                key = require_string(request["catalog_public_key"], "Native SDK catalog public key")
                if not Path(key).is_absolute() or os.path.normpath(key) != key:
                    raise ValueError("Native SDK catalog key path must be absolute and normalized")
                pinned = read_regular_file_bytes(Path(key), max_bytes=64 * 1024,
                    reject_symlink_parents=True)
                if sha256_bytes(pinned) != require_sha256(request["expected_public_key_sha256"],
                        "Native SDK catalog key digest"):
                    raise ValueError("Native SDK catalog key differs from caller-owned digest")
                request["catalog_public_key"] = Path(key)
                _route(request, "trusted_catalog_workflow_path", "trusted_catalog_job_name")
            _route(request, "trusted_worker_workflow_path", "trusted_worker_job_name")
            require_integer(request["pull_request"], "Native SDK pull request", 1)
            if "failed_catalog_producer" in request:
                failed = request["failed_catalog_producer"]
                if (failed["event"] != "pull_request"
                        or failed["repository"] != request["repository"]
                        or failed["pullRequest"] != request["pull_request"]):
                    raise ValueError("Native SDK failed catalog differs from selected repository or PR")
            target = reused
        else:
            raise ValueError("Native SDK election route must be fresh or same-pr")
        require_sha256(request["expected_build_key"], "Native SDK build key")
        require_semver(request["expected_product_version"], "Native SDK version")
        target[instance] = request
    if set(fresh) | set(reused) != NATIVE_CAMPAIGN_INSTANCES:
        raise ValueError("Native SDK election is missing a phase")
    return MappingProxyType(fresh), MappingProxyType(reused), raw
