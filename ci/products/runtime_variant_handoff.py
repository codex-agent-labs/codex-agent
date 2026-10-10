"""Recover original signed native phase proofs from receipt-qualified transport.

This translates existing bytes into the existing nine-file handoff layout. It
does not sign, elect state, contact CI, or replace the caller's full K/R/raw gate.
A partially matching handoff proves only its matching original phases; the
protected caller may reuse its entire signature only when all originals match.
"""

from pathlib import Path
import tempfile

from .inventory import (
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_regular_directory,
    sha256_bytes, sha256_file,
)
from .receipt import validate_phase_receipt
from .registry import NATIVE_TARGETS
from .reuse import _native_comparison_records
from .runtime_aggregate_handoff import _public_policy
from .runtime_attestation import read_runtime_variant_handoff
from .sdk_inputs import _copy_file
from .sdk_package import _require_capability_output_separate
from .sdk_runtime_content import _native_desktop_report


_PHASES = ("binary", "package", "validation", "metadata")
_JSON_LIMIT = 16 * 1024 * 1024


def capture_runtime_variant_handoffs(records, artifact_root: Path, destination: Path, *,
                                     target: str, phase_receipts, keyring: Path,
                                     keys_directory: Path,
                                     original_inventories: dict[Path, list] | None = None,
                                     expected_policy: dict[str, bytes] | None = None) -> tuple[Path, ...]:
    """Publish matching release proofs unchanged, or return empty when absent.

    Candidate discovery is data-only. Every matching release candidate must pass
    the existing full release reader with caller-pinned policy; invalid matching
    evidence never becomes a silent miss. Development/nonmatching records grant
    no release reuse. The caller supplies selected originals after state replay.
    """
    if target not in NATIVE_TARGETS:
        raise ValueError("Retained native handoffs require an exact Runtime target")
    require_exact_keys(phase_receipts, set(_PHASES), "Selected original Runtime receipts")
    selected_paths = {phase: Path(phase_receipts[phase]) for phase in _PHASES}
    selected = {phase: read_regular_file_bytes(path, max_bytes=_JSON_LIMIT, reject_symlink_parents=True)
                for phase, path in selected_paths.items()}
    for phase, raw in selected.items():
        receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
        if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
                "runtime", target, phase, target):
            raise ValueError("Selected Runtime receipt identity differs from its target/phase")
    decoded = _native_comparison_records(Path(artifact_root), records)
    destination = Path(destination).absolute()
    inputs = [*selected_paths.values(), *(path.parent for path in selected_paths.values())]
    for contract, runtime in decoded.values():
        inputs.extend(Path(value) for value in runtime["phaseReceipts"].values())
        inputs.extend(Path(value) for name, value in runtime.items()
                      if name not in {"target", "phaseReceipts"} and value is not None)
        inputs.extend(Path(value) for name, value in contract.items()
                      if name != "expectedTrustDomain" and value is not None)
        inputs.extend((Path(runtime["attestation"]).parent, Path(contract["attestation"]).parent))
    inputs.extend(Path(value) for value in (keyring, keys_directory) if value is not None)

    def output_safe():
        for path in (destination, *destination.parents):
            if path.is_symlink():
                raise ValueError("Retained native output has symbolic ancestry")
            if path.exists():
                require_regular_directory(path, "Retained native output ancestry")
        if destination.exists():
            raise ValueError("Retained native output must not exist")
        _require_capability_output_separate(destination, inputs)

    output_safe()
    observed_receipts = {}
    candidates = []
    for digest, (contract, runtime) in decoded.items():
        if contract["expectedTrustDomain"] not in {"development", "release"}:
            raise ValueError("Retained native evidence has an invalid trust domain")
        if runtime["target"] != target or contract["expectedTrustDomain"] == "development":
            continue
        originals = {}
        for phase, value in runtime["phaseReceipts"].items():
            path = Path(value)
            originals[phase] = read_regular_file_bytes(path, max_bytes=_JSON_LIMIT, reject_symlink_parents=True)
            if path in observed_receipts and observed_receipts[path] != originals[phase]:
                raise ValueError("Retained Runtime receipt changed during discovery")
            observed_receipts[path] = originals[phase]
        if any(originals[phase] == selected[phase] for phase in _PHASES):
            if sha256_bytes(originals["validation"]) != digest:
                raise ValueError("Retained native record differs from its original validation receipt")
            candidates.append((digest, runtime, originals))

    def receipts_unchanged():
        for path, raw in [*((selected_paths[phase], selected[phase]) for phase in _PHASES),
                          *observed_receipts.items()]:
            if read_regular_file_bytes(path, max_bytes=_JSON_LIMIT, reject_symlink_parents=True) != raw:
                raise ValueError("Selected or retained Runtime receipt changed during capture")

    if not candidates:
        receipts_unchanged()
        return ()
    with tempfile.TemporaryDirectory(prefix="retained-native-handoffs-") as temporary:
        private = Path(temporary).resolve()
        policy = private / "policy"
        policy_paths, policy_bytes = _public_policy(keyring, keys_directory, policy)
        if expected_policy is not None and policy_bytes != expected_policy:
            raise ValueError("Retained native policy differs from caller-pinned bytes")
        policy_inventory = sorted(
            ({"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)}
             for name, raw in policy_bytes.items()), key=lambda record: record["relativePath"])
        if regular_file_inventory(policy) != policy_inventory:
            raise ValueError("Retained native private policy differs from caller-pinned bytes")
        handoffs = private / "handoffs"
        source_digests = {}
        inventories = {}
        published = []
        for digest, runtime, originals in candidates:
            payload = Path(runtime["payload"])
            stem = payload.stem
            sources = {
                payload.name: (payload, 1024 * 1024 * 1024),
                f"{stem}.attestation.json": (Path(runtime["attestation"]), _JSON_LIMIT),
                f"{stem}.attestation.sig": (Path(runtime["attestationSignature"]), 1024 * 1024),
                "public-key.pub": (Path(runtime["publicKey"]), 1024 * 1024),
                "validation-evidence.json": (_native_desktop_report(Path(runtime["stageRoot"]), target), 64 * 1024 * 1024),
            }
            name = digest.removeprefix("sha256:")
            captured = handoffs / name
            original_files = []
            for relative, (source, limit) in sources.items():
                size = source.stat(follow_symlinks=False).st_size
                if not 0 < size <= limit:
                    raise ValueError("Retained native original exceeds its handoff size bound")
                before = sha256_file(source)
                original_files.append({"relativePath": relative, "bytes": size, "sha256": before})
                if source in source_digests and source_digests[source] != before:
                    raise ValueError("Retained native original changed during capture")
                source_digests[source] = before
                _copy_file(source, captured / relative, max_bytes=limit)
                if sha256_file(captured / relative) != before:
                    raise ValueError("Retained native original changed while copying")
            for phase, raw in originals.items():
                path = captured / "receipts" / f"{phase}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                original_files.append({"relativePath": f"receipts/{phase}.json",
                                       "bytes": len(raw), "sha256": sha256_bytes(raw)})
            before = regular_file_inventory(captured)
            if before != sorted(original_files, key=lambda record: record["relativePath"]):
                raise ValueError("Retained native copy differs from original source bytes")
            verified = read_runtime_variant_handoff(captured, target=target,
                keyring=policy / "product-signing-keys.json", keys_directory=policy / "keys")
            if (verified["receiptBytes"] != originals or regular_file_inventory(captured) != before
                    or any(read_regular_file_bytes(captured / relative, reject_symlink_parents=True) != raw
                           for relative, raw in verified["files"].items())):
                raise ValueError("Verified retained native handoff differs from captured originals")
            inventories[name] = before
            published.append(destination / name)
        receipts_unchanged()
        if (any(regular_file_inventory(handoffs / name) != inventory for name, inventory in inventories.items())
                or any(sha256_file(path) != digest for path, digest in source_digests.items())
                or regular_file_inventory(policy) != policy_inventory
                or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True) != policy_bytes[name]
                       for name, path in policy_paths.items())):
            raise ValueError("Retained native original or caller policy changed before publication")
        output_safe()
        expected = sorted(
            ({**record, "relativePath": f"{name}/{record['relativePath']}"}
             for name, inventory in inventories.items() for record in inventory),
            key=lambda record: record["relativePath"])
        publish_regular_tree(handoffs, destination, expected_inventory=expected)
    if original_inventories is not None:
        original_inventories.update({destination / name: inventory for name, inventory in inventories.items()})
    return tuple(published)
