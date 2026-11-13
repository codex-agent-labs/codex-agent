"""Store original Apple validation evidence without granting admission authority.

Canonical structure and byte bindings are not signatures, observed CI identity,
or semantic acceptance. Callers must separately authenticate the enclosing
carrier and run the complete original validation gate before admission.
"""

from pathlib import Path
import tempfile

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_array, require_exact_keys, require_integer,
    require_regular_directory, require_relative_path, require_sha256, sha256_bytes,
    snapshot_regular_tree,
)
from .sdk_apple_content import _input_inventory
from .sdk_apple_validation_attestation import (
    ATTESTATION_NAME, SIGNATURE_NAME, validate_apple_validation_attestation, verify_apple_validation_binding,
)
from .sdk_package import _require_capability_output_separate


REQUEST_NAME = "sdk-apple-validation-evidence.json"
_LIMIT = 16 * 1024 * 1024
_TARGETS = {"ios-arm64", "ios-simulator-arm64"}


def _references(records):
    result = []
    for record in require_array(records, "Apple validation evidence records"):
        record = require_exact_keys(record, {"receiptSha256", "target", "evidenceRoot"},
                                    "Apple validation evidence record")
        digest = require_sha256(record["receiptSha256"], "Apple validation receipt digest")
        if type(record["target"]) is not str or record["target"] not in _TARGETS:
            raise ValueError("Apple validation evidence requires an exact iOS target")
        path = require_relative_path(record["evidenceRoot"], "Apple evidence root")
        if Path(path).parts[-2:] != ("originals", digest.removeprefix("sha256:")):
            raise ValueError("Apple validation evidence root differs from its receipt")
        result.append(dict(record))
    digests = [record["receiptSha256"] for record in result]
    if digests != sorted(set(digests)):
        raise ValueError("Apple validation evidence receipts must be sorted and unique")
    return result


def _records(records):
    result = _references(records)
    if any(record["evidenceRoot"] != f"originals/{record['receiptSha256'].removeprefix('sha256:')}"
           for record in result):
        raise ValueError("Apple validation storage roots must use the canonical receipt layout")
    return result


def _entry(root):
    before = _input_inventory(root, allow_empty=True)
    if {path.name for path in root.iterdir()} != {"capture", ATTESTATION_NAME, SIGNATURE_NAME}:
        raise ValueError("Apple validation evidence entry has unexpected files")
    capture = root / "capture"
    require_regular_directory(capture, "Apple validation capture")
    if {path.name for path in capture.iterdir()} != {"plan", "original", "transport.zip", "capture-transport.json"}:
        raise ValueError("Apple validation capture has unexpected roots")
    require_regular_directory(capture / "original", "Apple validation original upload")
    files = {record["relativePath"]: record for record in before}
    if any(files.get(f"capture/{name}", {}).get("bytes", 0) == 0 for name in ("transport.zip", "capture-transport.json")):
        raise ValueError("Apple validation capture transport files must be regular and nonempty")
    if ({record["relativePath"] for record in _input_inventory(capture / "plan", allow_empty=False)} != {"impact-plan.json"}
            or {path.name for path in (capture / "plan").iterdir()} != {"impact-plan.json"}):
        raise ValueError("Apple validation capture plan has unexpected files")
    receipt_bytes = read_regular_file_bytes(capture / "original/shard/phase-receipt.json",
        max_bytes=_LIMIT, reject_symlink_parents=True)
    attestation = validate_apple_validation_attestation(load_canonical_json_bytes(
        read_regular_file_bytes(root / ATTESTATION_NAME, max_bytes=_LIMIT, reject_symlink_parents=True)))
    if not read_regular_file_bytes(root / SIGNATURE_NAME, max_bytes=_LIMIT, reject_symlink_parents=True):
        raise ValueError("Apple validation evidence signature must be retained and nonempty")
    verify_apple_validation_binding(capture, receipt_bytes, attestation)
    if _input_inventory(root, allow_empty=True) != before:
        raise ValueError("Apple validation evidence entry changed during inspection")
    digest = sha256_bytes(receipt_bytes)
    return {"receiptSha256": digest, "target": attestation["target"],
            "evidenceRoot": f"originals/{digest.removeprefix('sha256:')}"}


def load_sdk_apple_validation_evidence(root):
    """Load exact retained structure and byte consistency, never trust a signer."""
    root = Path(root).absolute()
    before = _input_inventory(root, allow_empty=True)
    manifest = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
        root / REQUEST_NAME, max_bytes=_LIMIT, reject_symlink_parents=True)),
        {"schemaVersion", "records"}, "Apple validation evidence manifest")
    if require_integer(manifest["schemaVersion"], "Apple evidence schema", 1) != 1:
        raise ValueError("Unsupported Apple validation evidence schema")
    records = _records(manifest["records"])
    if {path.name for path in root.iterdir()} != {REQUEST_NAME, "originals"}:
        raise ValueError("Apple validation carrier has unexpected roots")
    originals = root / "originals"
    require_regular_directory(originals, "Apple validation originals")
    if {path.name for path in originals.iterdir()} != {Path(record["evidenceRoot"]).name for record in records}:
        raise ValueError("Apple validation carrier has missing or unexpected entries")
    for record in records:
        if _entry(root / record["evidenceRoot"]) != record:
            raise ValueError("Apple validation entry differs from its original record")
    if _input_inventory(root, allow_empty=True) != before:
        raise ValueError("Apple validation carrier changed during inspection")
    return records


def rebase_sdk_apple_validation_records(records, source_root, artifact_root):
    """Rebase storage references inside an enclosing artifact; confer no trust."""
    source_root, artifact_root = Path(source_root).absolute(), Path(artifact_root).absolute()
    records = _references(records)
    for record in records:
        entry = _entry(source_root / record["evidenceRoot"])
        if any(entry[name] != record[name] for name in ("receiptSha256", "target")):
            raise ValueError("Apple validation reference differs from its retained entry")
    return [{**record, "evidenceRoot": require_relative_path(
        (source_root / record["evidenceRoot"]).relative_to(artifact_root).as_posix(), "Rebased Apple evidence root")}
        for record in records]


def capture_sdk_apple_validation_evidence(evidence_roots, destination):
    """Privately snapshot complete original entries, then atomically publish.

    Signature files are preserved opaque bytes. Neither this function nor the
    resulting manifest authenticates them or grants phase acceptance.
    """
    if not isinstance(evidence_roots, (list, tuple)):
        raise ValueError("Apple validation evidence roots must be an explicit sequence")
    roots = [Path(path).absolute() for path in evidence_roots]
    destination = Path(destination).absolute()

    def output_safe():
        _require_capability_output_separate(destination, roots)
        if destination.exists() or destination.is_symlink():
            raise ValueError("Apple validation evidence destination must not exist")
        for parent in destination.parents:
            if parent.exists() or parent.is_symlink():
                require_regular_directory(parent, "Apple validation output ancestry")

    output_safe()
    before = [_input_inventory(path, allow_empty=True) for path in roots]
    with tempfile.TemporaryDirectory(prefix="sdk-apple-validation-evidence-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [destination, *roots])
        staged = private / "carrier"
        (staged / "originals").mkdir(parents=True)
        records = []
        for index, source in enumerate(roots):
            entry = private / f"entry-{index}"
            snapshot_regular_tree(source, entry, allow_empty=True)
            if _input_inventory(entry, allow_empty=True) != before[index]:
                raise ValueError("Original Apple validation evidence changed during capture")
            record = _entry(entry)
            if any(previous["receiptSha256"] == record["receiptSha256"] for previous in records):
                raise ValueError("Apple validation evidence receipts must be unique")
            entry.rename(staged / record["evidenceRoot"])
            records.append(record)
        records.sort(key=lambda record: record["receiptSha256"])
        (staged / REQUEST_NAME).write_bytes(canonical_json_bytes({"schemaVersion": 1, "records": records}))
        captured = _input_inventory(staged, allow_empty=True)
        if load_sdk_apple_validation_evidence(staged) != records:
            raise ValueError("Captured Apple validation records changed")
        if (_input_inventory(staged, allow_empty=True) != captured
                or any(_input_inventory(path, allow_empty=True) != inventory for path, inventory in zip(roots, before))):
            raise ValueError("Apple validation evidence changed before publication")
        output_safe()
        publish_regular_tree(staged, destination, allow_empty=True)
    return records
