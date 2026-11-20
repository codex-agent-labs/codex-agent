"""Decode caller-owned Core/Android campaign policy before observing a run.

This is a byte snapshot, not source authentication or release admission. The
protected caller must independently pin its digest before using selections.
"""

from pathlib import Path

from ci.sdk_campaign_catalog_producer import (
    _CUSTODY_REUSED_SELECTION_KEYS, _FRESH_SELECTION_KEYS,
    _REUSED_SELECTION_KEYS,
)
from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_integer, require_relative_path, require_semver, require_sha256,
    require_string, sha256_bytes,
)
from products.receipt import validate_producer
from products.registry import PhaseInstanceId
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES


CORE_ANDROID_INSTANCES = frozenset(instance for instance in SDK_CAMPAIGN_INSTANCES
                                   if instance.component in {"sdk-core", "sdk-android"})
_IDENTITY_KEYS = {"product", "component", "phase", "target"}


def _parse(contents: bytes):
    policy = require_exact_keys(load_canonical_json_bytes(contents),
                                {"schemaVersion", "family", "selections"},
                                "Core/Android election")
    if type(policy["schemaVersion"]) is not int or policy["schemaVersion"] != 1 \
            or policy["family"] != "core-android":
        raise ValueError("Core/Android election schema or family differs")
    rows = policy["selections"]
    if type(rows) is not list or len(rows) != len(CORE_ANDROID_INSTANCES):
        raise ValueError("Core/Android election requires exactly 18 rows")
    fresh, reused, order = {}, {}, []
    for row in rows:
        row = require_exact_keys(row, {"identity", "route", "request"},
                                 "Core/Android election row")
        identity = require_exact_keys(row["identity"], _IDENTITY_KEYS,
                                      "Core/Android phase identity")
        if any(type(identity[name]) is not str for name in _IDENTITY_KEYS):
            raise ValueError("Core/Android phase identity requires text fields")
        instance = PhaseInstanceId(**identity)
        if instance not in CORE_ANDROID_INSTANCES or instance in fresh or instance in reused:
            raise ValueError("Core/Android election has an unknown or duplicate phase")
        request = row["request"]
        if row["route"] == "fresh":
            request = dict(require_exact_keys(request, _FRESH_SELECTION_KEYS,
                                              "Fresh Core/Android election request"))
            request["producer"] = dict(validate_producer(request["producer"]))
            workflow_fields = ("trusted_workflow_path", "trusted_job_name")
            destination = fresh
        elif row["route"] == "same-pr":
            fields = (_CUSTODY_REUSED_SELECTION_KEYS if type(request) is dict and
                      "custody_ref" in request else _REUSED_SELECTION_KEYS |
                      ({"failed_catalog_producer"} if type(request) is dict and
                       "failed_catalog_producer" in request else set()))
            request = dict(require_exact_keys(request, fields,
                                              "Reused Core/Android election request"))
            require_integer(request["pull_request"], "Core/Android original PR", 1)
            repository = require_relative_path(request["repository"],
                                               "Core/Android original repository")
            if repository.count("/") != 1:
                raise ValueError("Core/Android original repository must be owner/repository")
            if "failed_catalog_producer" in request:
                producer = validate_producer(request["failed_catalog_producer"])
                if (producer["event"] != "pull_request" or
                        producer["repository"] != repository or
                        producer["pullRequest"] != request["pull_request"]):
                    raise ValueError("Core/Android failed catalog producer differs from selected PR")
                request["failed_catalog_producer"] = dict(producer)
            if "custody_ref" in request:
                require_string(request["custody_ref"], "Core/Android custody reference")
                workflow_fields = ("trusted_worker_workflow_path", "trusted_worker_job_name")
            else:
                require_string(request["catalog_artifact_name"], "Core/Android catalog name")
                require_sha256(request["expected_public_key_sha256"],
                               "Core/Android catalog key digest")
                key_text = require_string(request["catalog_public_key"],
                                          "Core/Android catalog key path")
                key = Path(key_text)
                if not key.is_absolute() or str(key) != key_text:
                    raise ValueError("Core/Android catalog key requires a canonical absolute path")
                try:
                    canonical = key.resolve(strict=True)
                except OSError as error:
                    raise ValueError("Core/Android catalog key is unavailable") from error
                if canonical != key:
                    raise ValueError("Core/Android catalog key requires a canonical absolute path")
                key_bytes = read_regular_file_bytes(key, max_bytes=64 * 1024,
                                                    reject_symlink_parents=True)
                if sha256_bytes(key_bytes) != request["expected_public_key_sha256"]:
                    raise ValueError("Core/Android catalog key differs from pinned digest")
                request["catalog_public_key"] = key
                workflow_fields = ("trusted_worker_workflow_path", "trusted_worker_job_name",
                                   "trusted_catalog_workflow_path", "trusted_catalog_job_name")
            destination = reused
        else:
            raise ValueError("Core/Android election route must be fresh or same-pr")
        require_sha256(request["expected_build_key"], "Core/Android build key")
        require_semver(request["expected_product_version"], "Core/Android SDK version")
        for field in workflow_fields:
            (require_relative_path if field.endswith("path") else require_string)(
                request[field], f"Core/Android {field}")
        destination[instance] = request
        order.append(instance)
    if set(fresh) | set(reused) != CORE_ANDROID_INSTANCES or order != sorted(order):
        raise ValueError("Core/Android election must list all 18 phases once in order")
    return fresh, reused


def load_core_android_election(path: Path):
    """Return fresh, reused and the exact bytes read once for caller pinning."""
    contents = read_regular_file_bytes(Path(path), max_bytes=1024 * 1024,
                                       reject_symlink_parents=True)
    fresh, reused = _parse(contents)
    return fresh, reused, contents
