"""Lossless Core/Android metadata carrier transport, never semantic admission.

The caller authenticates the enclosing capture independently. Neither this
receipt index nor stored workflow observations confer trust. Concrete metadata
admission must separately hold the complete original semantic/source replay
under caller-owned policy; no such policy is stored or inferred here.
"""

import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_sha256, sha256_bytes,
    snapshot_regular_tree, write_canonical_json,
)
from products.receipt import validate_phase_receipt
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from sdk_facade_capture import verify_retained_sdk_phase_upload


REQUEST_NAME = "sdk-metadata-evidence.json"
_FIELDS = {"component", "phase", "target", "receiptSha256", "receipt", "capture"}
_TARGETS = {"sdk-core": "common", "sdk-android": "android"}
_LIMIT = 16 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _path(value):
    path = Path(value).absolute()
    if path.resolve(strict=False) != path:
        raise ValueError("Metadata evidence paths must be normalized and non-symbolic")
    return path


def _record(raw):
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if (receipt["product"] != "sdk" or receipt["component"] not in _TARGETS
            or receipt["phase"] != "metadata"
            or receipt["target"] != _TARGETS[receipt["component"]]):
        raise ValueError("Metadata evidence requires exact Core/common or Android/android metadata")
    digest = sha256_bytes(raw)
    prefix = "originals/" + digest.removeprefix("sha256:")
    return {**{name: receipt[name] for name in ("component", "phase", "target")},
            "receiptSha256": digest, "receipt": prefix + "/receipt.json",
            "capture": prefix + "/capture"}


def load_sdk_metadata_evidence(root):
    """Return confined complete transport records, not authenticated products."""
    root = _path(root)
    before = regular_file_inventory(root, allow_empty=True)
    raw = _read(root / REQUEST_NAME)
    try:
        records = load_canonical_json_bytes(raw)
        if type(records) is not list or not records:
            raise ValueError("Metadata evidence requires a nonempty receipt index")
        expected, digests = {REQUEST_NAME}, []
        for record in records:
            require_exact_keys(record, _FIELDS, "Metadata evidence record")
            digest = require_sha256(record["receiptSha256"], "Metadata evidence receipt digest")
            prefix = "originals/" + digest.removeprefix("sha256:")
            if record["receipt"] != prefix + "/receipt.json" or record["capture"] != prefix + "/capture":
                raise ValueError("Metadata evidence paths differ from their fixed receipt layout")
            receipt_bytes = _read(root / record["receipt"])
            if _record(receipt_bytes) != record:
                raise ValueError("Metadata evidence record differs from its exact original receipt")
            capture = root / record["capture"]
            verify_retained_sdk_phase_upload(capture, receipt_bytes)
            expected.add(record["receipt"])
            expected.update((Path(record["capture"]) / row["relativePath"]).as_posix()
                            for row in regular_file_inventory(capture, allow_empty=True))
            digests.append(digest)
        if digests != sorted(set(digests)):
            raise ValueError("Metadata evidence index must be unique and sorted")
        if expected != {row["relativePath"] for row in before}:
            raise ValueError("Metadata evidence contains missing or unexpected files")
        return records
    finally:
        if regular_file_inventory(root, allow_empty=True) != before or _read(root / REQUEST_NAME) != raw:
            raise ValueError("Metadata evidence changed during loading")


def retain_sdk_metadata_evidence(receipt_path, capture_root, destination):
    """Preserve one exact receipt/capture after structural transport checks only.

    This intentionally does not invoke, replace, or mint semantic admission.
    The destination is a fresh external carrier, never reusable product content.
    """
    require_no_signing_secret(os.environ)
    receipt_path, capture_root, destination = map(_path, (receipt_path, capture_root, destination))

    def output_safe():
        _require_capability_output_separate(destination, [receipt_path, capture_root])
        if destination.exists() or destination.is_symlink() or destination.resolve(strict=False) != destination:
            raise ValueError("Metadata evidence destination must be fresh and non-symbolic")

    output_safe()
    raw = _read(receipt_path)
    record = _record(raw)
    before = regular_file_inventory(capture_root, allow_empty=True)

    def unchanged():
        require_no_signing_secret(os.environ)
        if _read(receipt_path) != raw or regular_file_inventory(capture_root, allow_empty=True) != before:
            raise ValueError("Metadata evidence original receipt or capture changed during retention")

    try:
        verify_retained_sdk_phase_upload(capture_root, raw)
        unchanged()
        with tempfile.TemporaryDirectory(prefix="sdk-metadata-evidence-") as temporary:
            candidate = Path(temporary).resolve() / "carrier"
            _require_capability_output_separate(candidate, [receipt_path, capture_root, destination])
            snapshot_regular_tree(capture_root, candidate / record["capture"], allow_empty=True)
            if regular_file_inventory(candidate / record["capture"], allow_empty=True) != before:
                raise ValueError("Retained metadata capture differs from original bytes")
            (candidate / record["receipt"]).write_bytes(raw)
            write_canonical_json(candidate / REQUEST_NAME, [record])
            if load_sdk_metadata_evidence(candidate) != [record]:
                raise ValueError("Retained metadata carrier differs from its selected original")
            candidate_inventory = regular_file_inventory(candidate, allow_empty=True)
            unchanged()
            output_safe()
            publish_regular_tree(candidate, destination, allow_empty=True)
            if regular_file_inventory(destination, allow_empty=True) != candidate_inventory:
                raise ValueError("Published metadata carrier differs from its private candidate")
        unchanged()
        return [record]
    finally:
        unchanged()
