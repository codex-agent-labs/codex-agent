"""Decode the independently pinned Apple/JavaScript SDK campaign election.

This selects original lookup routes before campaign observation; it does not
authenticate an original upload or grant release admission.
"""

from pathlib import Path

from ci.sdk_campaign_catalog_producer import (
    _CUSTODY_REUSED_SELECTION_KEYS, _FRESH_SELECTION_KEYS,
    _REUSED_SELECTION_KEYS,
)
from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_integer, require_relative_path, require_semver, require_sha256,
    sha256_bytes,
)
from products.receipt import validate_producer
from products.registry import PhaseInstanceId
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES


APPLE_JS_INSTANCES = frozenset(instance for instance in SDK_CAMPAIGN_INSTANCES
    if instance.component in {"sdk-ios", "javascript"})
_IDENTITY_FIELDS = {"product", "component", "phase", "target"}


def _text(value, label):
    if type(value) is not str or not value or any(ord(character) < 0x20
            or ord(character) == 0x7f for character in value):
        raise ValueError(f"{label} must be nonempty text without controls")
    return value


def _common_request(request):
    require_sha256(request["expected_build_key"], "Apple/JavaScript build key")
    require_semver(request["expected_product_version"], "Apple/JavaScript SDK version")


def _failed_producer(selected):
    producer = validate_producer(selected["failed_catalog_producer"])
    if (producer["event"] != "pull_request"
            or producer["repository"] != selected["repository"]
            or producer["pullRequest"] != selected["pull_request"]):
        raise ValueError("Apple/JavaScript failed catalog differs from selected PR")


def load_family_election(path: Path):
    """Return fresh/reused lookup requests and the exact immutable policy bytes."""
    raw = read_regular_file_bytes(Path(path), max_bytes=1024 * 1024,
        reject_symlink_parents=True)
    policy = require_exact_keys(load_canonical_json_bytes(raw),
        {"schemaVersion", "family", "selections"}, "Apple/JavaScript election")
    if (type(policy["schemaVersion"]) is not int or policy["schemaVersion"] != 1
            or policy["family"] != "apple-js"
            or type(policy["selections"]) is not list
            or len(policy["selections"]) != len(APPLE_JS_INSTANCES)):
        raise ValueError("Apple/JavaScript election requires its exact eight phases")
    fresh, reused, identities = {}, {}, []
    for row in policy["selections"]:
        row = require_exact_keys(row, {"identity", "route", "request"},
            "Apple/JavaScript election row")
        identity = require_exact_keys(row["identity"], _IDENTITY_FIELDS,
            "Apple/JavaScript phase identity")
        if any(type(identity[field]) is not str for field in _IDENTITY_FIELDS):
            raise ValueError("Apple/JavaScript phase identity must contain text")
        instance = PhaseInstanceId(**identity)
        if instance not in APPLE_JS_INSTANCES:
            raise ValueError("Apple/JavaScript election contains another SDK phase")
        identities.append(instance)
        request = row["request"]
        if row["route"] == "fresh":
            selected = dict(require_exact_keys(request, _FRESH_SELECTION_KEYS,
                "Fresh Apple/JavaScript selection"))
            _common_request(selected)
            validate_producer(selected["producer"])
            require_relative_path(selected["trusted_workflow_path"], "Apple/JavaScript worker path")
            _text(selected["trusted_job_name"], "Apple/JavaScript worker job")
            fresh[instance] = selected
        elif row["route"] == "same-pr":
            keys = (_CUSTODY_REUSED_SELECTION_KEYS if type(request) is dict
                and "custody_ref" in request else _REUSED_SELECTION_KEYS |
                ({"failed_catalog_producer"} if type(request) is dict
                    and "failed_catalog_producer" in request else set()))
            selected = dict(require_exact_keys(request, keys,
                "Reused Apple/JavaScript selection"))
            _common_request(selected)
            require_integer(selected["pull_request"], "Apple/JavaScript PR", 1)
            repository = require_relative_path(selected["repository"], "Apple/JavaScript repository")
            if repository.count("/") != 1:
                raise ValueError("Apple/JavaScript repository must be owner/name")
            require_relative_path(selected["trusted_worker_workflow_path"],
                "Apple/JavaScript worker path")
            _text(selected["trusted_worker_job_name"], "Apple/JavaScript worker job")
            if "custody_ref" in selected:
                _text(selected["custody_ref"], "Apple/JavaScript custody reference")
                _failed_producer(selected)
            else:
                _text(selected["catalog_artifact_name"], "Apple/JavaScript catalog name")
                require_sha256(selected["expected_public_key_sha256"],
                    "Apple/JavaScript catalog public key")
                require_relative_path(selected["trusted_catalog_workflow_path"],
                    "Apple/JavaScript catalog path")
                _text(selected["trusted_catalog_job_name"], "Apple/JavaScript catalog job")
                if "failed_catalog_producer" in selected:
                    _failed_producer(selected)
            if "catalog_public_key" in selected:
                key_path = _text(selected["catalog_public_key"],
                    "Apple/JavaScript catalog key path")
                key = Path(key_path)
                if (not key.is_absolute() or key.as_posix() != key_path
                        or ".." in key.parts or "\\" in key_path):
                    raise ValueError("Apple/JavaScript catalog key path must be normalized and absolute")
                key_bytes = read_regular_file_bytes(key, max_bytes=64 * 1024,
                    reject_symlink_parents=True)
                if sha256_bytes(key_bytes) != selected["expected_public_key_sha256"]:
                    raise ValueError("Apple/JavaScript catalog public key differs from pinned bytes")
                selected["catalog_public_key"] = key
            reused[instance] = selected
        else:
            raise ValueError("Apple/JavaScript election has an unknown lookup route")
    if identities != sorted(APPLE_JS_INSTANCES):
        raise ValueError("Apple/JavaScript election phases must be exact, unique and sorted")
    return fresh, reused, raw
