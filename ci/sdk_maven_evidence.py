"""Retain complete original Maven proof without granting reuse or host authority.

The caller authenticates the enclosing capture and supplies independent policy
and original invocation context. The index contains locators, never that policy.
Staging reuses the original source/content/Contract gates; their deliberately
limited compiler/host scope is unchanged. Collection/catalog admission is separate.
"""

from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_regular_directory, require_semver, require_sha256, sha256_bytes, sha256_file,
    snapshot_regular_tree, write_canonical_json,
)
from products.receipt import validate_phase_receipt, validate_producer
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, PHASE_RECEIPT_NAME, verify_phase_shard
from products.sdk_facade_inputs import _EVIDENCE_FIELDS, _path
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from sdk_facade_capture import verify_retained_sdk_phase_upload
from sdk_maven_original import verified_retained_maven_phase


REQUEST_NAME = "sdk-maven-evidence.json"
_FIELDS = {"component", "phase", "target", "receiptSha256", "receipt", "capture"}
_TARGETS = {"sdk-core": "common", "sdk-android": "android"}
_LIMIT = 16 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _record(raw):
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if (receipt["product"] != "sdk" or receipt["component"] not in _TARGETS
            or receipt["target"] != _TARGETS[receipt["component"]]
            or receipt["phase"] not in ("binary", "package")):
        raise ValueError("Maven evidence requires Core/Android binary or package")
    digest = sha256_bytes(raw)
    prefix = "originals/" + digest.removeprefix("sha256:")
    return {**{key: receipt[key] for key in ("component", "phase", "target")},
            "receiptSha256": digest, "receipt": prefix + "/receipt.json",
            "capture": prefix + "/capture"}


def load_sdk_maven_evidence(root):
    """Validate confined complete transport bytes, not their authenticity."""
    root = Path(root).absolute()
    before = regular_file_inventory(root, allow_empty=True)
    raw = _read(root / REQUEST_NAME)
    records = load_canonical_json_bytes(raw)
    if type(records) is not list or not records:
        raise ValueError("Maven evidence requires a nonempty receipt index")
    expected, digests = {REQUEST_NAME}, []
    for record in records:
        require_exact_keys(record, _FIELDS, "Maven evidence record")
        digest = require_sha256(record["receiptSha256"], "Maven evidence receipt digest")
        prefix = "originals/" + digest.removeprefix("sha256:")
        if (record["receipt"] != prefix + "/receipt.json"
                or record["capture"] != prefix + "/capture"):
            raise ValueError("Maven evidence paths differ from their receipt layout")
        receipt_bytes = _read(root / record["receipt"])
        if _record(receipt_bytes) != record:
            raise ValueError("Maven evidence record differs from its exact original receipt")
        capture = root / record["capture"]
        verify_retained_sdk_phase_upload(capture, receipt_bytes)
        expected.add(record["receipt"])
        expected.update((Path(record["capture"]) / item["relativePath"]).as_posix()
                        for item in regular_file_inventory(capture, allow_empty=True))
        digests.append(digest)
    if digests != sorted(set(digests)):
        raise ValueError("Maven evidence receipt index must be unique and sorted")
    if expected != {item["relativePath"] for item in before}:
        raise ValueError("Maven evidence contains missing or unexpected files")
    if (regular_file_inventory(root, allow_empty=True) != before
            or _read(root / REQUEST_NAME) != raw):
        raise ValueError("Maven evidence changed during loading")
    return records


def _caller_sources(plan, receipt_path, capture_root, binary_contract_evidence,
                    keyring, keys_directory, android_runtime_archive):
    evidence = require_exact_keys(binary_contract_evidence, _EVIDENCE_FIELDS,
                                  "Caller original binary Contract")
    sources = {plan, receipt_path, capture_root}
    for name in _EVIDENCE_FIELDS - {"expectedTrustDomain"}:
        if evidence[name] is not None:
            sources.add(Path(_path(evidence[name], "Caller Contract " + name)))
    sources.add(Path(_path(evidence["attestation"], "Caller Contract attestation")).parent /
                CONTRACT_EXECUTION_CLOSURE_DIRECTORY)
    sources.update(Path(value).absolute() for value in
                   (keyring, keys_directory, android_runtime_archive) if value is not None)
    return sources


def _output_safe(destination, repository_root, sources):
    _require_capability_output_separate(destination, [repository_root, *sources])
    if (destination.resolve(strict=False) != destination or destination.exists()
            or destination.is_symlink()):
        raise ValueError("Maven evidence destination must be fresh, normalized and non-symbolic")
    for parent in destination.parents:
        if parent.exists() or parent.is_symlink():
            require_regular_directory(parent, "Maven evidence destination ancestry")


def _snapshot_sources(sources):
    trees = {path: regular_file_inventory(path, allow_empty=True)
             for path in sources if path.is_dir()}
    files = {path: sha256_file(path) for path in sources if path not in trees}
    return trees, files


def _sources_unchanged(trees, files):
    return (all(regular_file_inventory(path, allow_empty=True) == before for path, before in trees.items())
            and all(sha256_file(path) == before for path, before in files.items()))


def stage_sdk_maven_evidence(plan, receipt_path, capture_root, destination, *,
        binary_contract_evidence, original_context, repository_root, environ,
        keyring=None, keys_directory=None, android_runtime_archive=None,
        binary_original_context=None):
    """Retain one caller-authenticated capture after its held original replay.

    No key, original context, policy, success token or synthesized receipt is
    added to the carrier. The complete existing upload, including nested binary
    proof for packages, is preserved. This does not enable a collector family.
    """
    require_no_signing_secret(environ)
    plan, receipt_path, capture_root, destination = (Path(value).absolute() for value in
        (plan, receipt_path, capture_root, destination))
    repository_root = Path(repository_root).resolve(strict=True)
    sources = _caller_sources(plan, receipt_path, capture_root, binary_contract_evidence,
                              keyring, keys_directory, android_runtime_archive)
    _output_safe(destination, repository_root, sources)
    require_regular_directory(capture_root, "Caller-authenticated Maven capture")
    trees, files = _snapshot_sources(sources)
    raw = _read(receipt_path)
    record = _record(raw)
    policy = lambda: canonical_json_bytes({"contract": binary_contract_evidence,
        "context": original_context, "binaryContext": binary_original_context})
    policy_bytes = policy()

    def unchanged():
        require_no_signing_secret(environ)
        if (policy() != policy_bytes or _read(receipt_path) != raw
                or not _sources_unchanged(trees, files)):
            raise ValueError("Maven evidence originals or caller policy changed during staging")

    try:
        with tempfile.TemporaryDirectory(prefix="sdk-maven-evidence-") as temporary:
            candidate = Path(temporary).resolve() / "carrier"
            _require_capability_output_separate(candidate, [repository_root, destination, *sources])
            unchanged()
            with verified_retained_maven_phase(plan, receipt_path, capture_root=capture_root,
                    binary_contract_evidence=binary_contract_evidence, original_context=original_context,
                    repository_root=repository_root, environ=environ, keyring=keyring,
                    keys_directory=keys_directory, android_runtime_archive=android_runtime_archive,
                    binary_original_context=binary_original_context) as original:
                if (original["receiptBytes"] != raw or canonical_json_bytes(original["receipt"]) != raw
                        or _read(original["receiptPath"]) != raw
                        or regular_file_inventory(original["capture"], allow_empty=True) != trees[capture_root]):
                    raise ValueError("Held Maven original differs from the selected receipt or capture")
                snapshot_regular_tree(original["capture"], candidate / record["capture"], allow_empty=True)
                (candidate / record["receipt"]).write_bytes(raw)
                write_canonical_json(candidate / REQUEST_NAME, [record])
                if load_sdk_maven_evidence(candidate) != [record]:
                    raise ValueError("Staged Maven evidence differs from its selected original")
                candidate_inventory = regular_file_inventory(candidate, allow_empty=True)
                unchanged()
            # A failing original-reader exit must never leave a published carrier.
            unchanged()
            if regular_file_inventory(candidate, allow_empty=True) != candidate_inventory:
                raise ValueError("Staged Maven evidence changed after original replay")
            _output_safe(destination, repository_root, sources)
            publish_regular_tree(candidate, destination, allow_empty=True)
            if regular_file_inventory(destination, allow_empty=True) != candidate_inventory:
                raise ValueError("Published Maven evidence differs from the verified candidate")
        unchanged()
        return [record]
    finally:
        unchanged()


def stage_collected_sdk_maven_evidence(plan, shard_root, capture_root, destination, *,
        expected_phase_plan, expected_producer, expected_sdk_version,
        binary_contract_evidence, original_context, repository_root, environ,
        keyring=None, keys_directory=None, android_runtime_archive=None,
        binary_original_context=None):
    """Pair an elected shard with its independently authenticated full capture.

    The collector supplies its authenticated election and producer, not uploaded
    claims. Exact receipt AND object binding precedes existing held original
    replay. This is proof retention only, not compiler/host or catalog admission.
    """
    require_no_signing_secret(environ)
    plan, shard_root, capture_root, destination = (Path(value).absolute() for value in
        (plan, shard_root, capture_root, destination))
    repository_root = Path(repository_root).resolve(strict=True)
    elected = require_exact_keys(expected_phase_plan, PHASE_PLAN_KEYS, "Elected Maven phase plan")
    identity = tuple(elected[name] for name in ("product", "component", "phase", "target"))
    if (any(type(value) is not str for value in identity) or identity[0] != "sdk"
            or identity[1] not in _TARGETS or identity[2] not in ("binary", "package")
            or identity[3] != _TARGETS[identity[1]]):
        raise ValueError("Collected Maven evidence requires an exact Core/Android binary or package election")
    instance = PhaseInstanceId(*identity)
    producer = validate_producer(expected_producer, "Elected Maven producer")
    require_semver(expected_sdk_version, "Elected Maven SDK version")
    authority = lambda: canonical_json_bytes({"plan": expected_phase_plan,
        "producer": expected_producer, "sdkVersion": expected_sdk_version,
        "contract": binary_contract_evidence, "context": original_context,
        "binaryContext": binary_original_context})
    authority_bytes = authority()
    receipt_path = shard_root / PHASE_RECEIPT_NAME
    sources = _caller_sources(plan, receipt_path, capture_root, binary_contract_evidence,
                              keyring, keys_directory, android_runtime_archive) | {shard_root}
    _output_safe(destination, repository_root, sources)
    require_regular_directory(capture_root, "Collected Maven original capture")
    require_regular_directory(shard_root, "Collected Maven worker shard")
    trees, files = _snapshot_sources(sources)
    raw = _read(receipt_path)

    def unchanged():
        require_no_signing_secret(environ)
        if (authority() != authority_bytes or _read(receipt_path) != raw
                or not _sources_unchanged(trees, files)):
            raise ValueError("Collected Maven election, shard, capture or caller policy changed")

    try:
        unchanged()
        selected = verify_phase_shard(shard_root, instance)
        receipt = selected["receipt"]
        if (selected["receiptBytes"] != raw or canonical_json_bytes(receipt) != raw
                or canonical_json_bytes({name: receipt[name] for name in PHASE_PLAN_KEYS}) !=
                   canonical_json_bytes(elected)
                or receipt["producer"] != producer or receipt["productVersion"] != expected_sdk_version
                or receipt["trustDomain"] != ("development" if producer["event"] == "pull_request" else "release")):
            raise ValueError("Collected Maven shard differs from its independent elected plan or producer")
        captured = verify_phase_shard(capture_root / "original/shard", instance)
        if captured != selected:
            raise ValueError("Collected Maven capture differs from the exact selected receipt and object")
        selected_inventory = regular_file_inventory(shard_root)
        if regular_file_inventory(capture_root / "original/shard") != selected_inventory:
            raise ValueError("Collected Maven original shard bytes differ from the selected worker shard")
        unchanged()
        with tempfile.TemporaryDirectory(prefix="collected-sdk-maven-") as temporary:
            candidate = Path(temporary).resolve() / "carrier"
            _require_capability_output_separate(candidate, [destination, repository_root, *sources])
            records = stage_sdk_maven_evidence(plan, receipt_path, capture_root, candidate,
                binary_contract_evidence=binary_contract_evidence, original_context=original_context,
                repository_root=repository_root, environ=environ, keyring=keyring,
                keys_directory=keys_directory, android_runtime_archive=android_runtime_archive,
                binary_original_context=binary_original_context)
            candidate_inventory = regular_file_inventory(candidate, allow_empty=True)
            if records != [_record(raw)] or load_sdk_maven_evidence(candidate) != records:
                raise ValueError("Collected Maven carrier differs from its selected original receipt")
            unchanged()
            if (verify_phase_shard(shard_root, instance) != selected
                    or verify_phase_shard(capture_root / "original/shard", instance) != selected
                    or regular_file_inventory(candidate, allow_empty=True) != candidate_inventory):
                raise ValueError("Collected Maven proof changed before publication")
            _output_safe(destination, repository_root, sources)
            publish_regular_tree(candidate, destination, allow_empty=True)
            if regular_file_inventory(destination, allow_empty=True) != candidate_inventory:
                raise ValueError("Published collected Maven carrier differs from its private candidate")
        unchanged()
        return records
    finally:
        unchanged()
