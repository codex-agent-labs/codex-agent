"""Replay the full retained Firebase Android content gate without minting trust.

The caller must independently authenticate both official capture transports,
the original binary/package receipt chain that selected the AAR and original
producer, the current capture producer, source policy, tooling, Java and
apkanalyzer.  This module only proves that those caller-owned values compose;
it emits no receipt, host verdict, producer authority or reusable payload.
"""

import os
from pathlib import Path
import re
import subprocess
import tempfile

from ci.receipt import LANE_RECEIPT_SCHEMA_VERSION

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_sha256, sha256_bytes, sha256_file,
    snapshot_regular_tree, verified_zip_contents,
)
from .receipt import validate_producer
from .signing_isolation import require_no_signing_secret
from .tooling import verified_tooling_capture


_OID = re.compile(r"[0-9a-f]{40}")
_FINAL_KEYS = {
    "schemaVersion", "kind", "artifact", "locator", "captureProducer",
    "laneReceiptSha256",
}
_PROTECTED_KEYS = _FINAL_KEYS | {
    "inputBindingSha256", "linkedFinalCaptureSha256",
    "linkedFinalLaneReceiptSha256",
}


def _receipt_producer(receipt, label):
    if type(receipt) is not dict:
        raise ValueError(f"{label} is not an object")
    return validate_producer({
        "repository": receipt.get("repository"),
        "workflowPath": receipt.get("workflowPath"),
        "commit": receipt.get("validationCommit"),
        "tree": receipt.get("validationTree"),
        "event": receipt.get("event"),
        "runId": receipt.get("runId"),
        "runAttempt": receipt.get("runAttempt"),
        "pullRequest": receipt.get("pullRequest"),
    }, label)


def _capture(root: Path, *, kind: str, keys: set[str]):
    before = regular_file_inventory(root, allow_empty=True)
    transport_path = root / "capture-transport.json"
    transport_bytes = read_regular_file_bytes(
        transport_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    transport = require_exact_keys(
        load_canonical_json_bytes(transport_bytes), keys, f"{kind} transport")
    artifact = transport["artifact"]
    locator = require_exact_keys(
        transport["locator"], {"artifact_id", "artifact_sha256"}, f"{kind} locator")
    artifact_id = require_integer(locator["artifact_id"], f"{kind} artifact ID", 1)
    artifact_sha = require_sha256(locator["artifact_sha256"], f"{kind} artifact digest")
    if (require_integer(transport["schemaVersion"], f"{kind} schema") != 1
            or transport["kind"] != kind or type(artifact) is not dict
            or artifact.get("id") != artifact_id or artifact.get("digest") != artifact_sha):
        raise ValueError(f"{kind} transport identity is invalid")
    archive = root / "original-upload.zip"
    if sha256_file(archive) != artifact_sha:
        raise ValueError(f"{kind} original upload digest changed")
    zipped, _, _ = verified_zip_contents(
        archive, retained_paths=(), allow_empty_members=True,
        max_archive_bytes=4 * 1024 * 1024 * 1024,
        max_central_directory_bytes=32 * 1024 * 1024,
        max_members=8192, max_entry_bytes=2 * 1024 * 1024 * 1024,
        max_total_bytes=4 * 1024 * 1024 * 1024,
        max_compression_ratio=200, require_sorted=False,
    )
    original = root / "original"
    original_inventory = regular_file_inventory(original, allow_empty=True)
    if original_inventory != zipped:
        raise ValueError(f"{kind} extracted original differs from its exact upload")
    producer = validate_producer(transport["captureProducer"], f"{kind} capture producer")
    return {
        "before": before, "transport": transport, "transportBytes": transport_bytes,
        "original": original, "originalInventory": original_inventory,
        "producer": producer,
    }


def verify_sdk_android_validation_original_content(
    *, final_capture: Path, protected_capture: Path, expected_binary_aar: Path,
    expected_capture_producer: dict, expected_original_producer: dict,
    trusted_source_commit: str, trusted_source_tree: str,
    repository: Path, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, apkanalyzer_executable: Path,
    policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None,
    tooling_keys_directory: Path | None = None,
) -> None:
    """Compose caller-authenticated originals through the packaged full gate.

    Transport dictionaries and retained receipts are comparison inputs only.
    The caller must authenticate the two expected producers and every policy
    path independently before invoking this function.
    """
    require_no_signing_secret(os.environ)
    authority_bytes = canonical_json_bytes({
        "captureProducer": expected_capture_producer,
        "originalProducer": expected_original_producer,
    })
    capture_producer = validate_producer(expected_capture_producer, "expected capture producer")
    original_producer = validate_producer(expected_original_producer, "expected original producer")
    if any(type(value) is not str or _OID.fullmatch(value) is None
           for value in (trusted_source_commit, trusted_source_tree, policy_revision)):
        raise ValueError("Android validation requires exact caller Git policy identities")
    stable = ("repository", "workflowPath", "commit", "tree", "event", "pullRequest")
    if any(capture_producer[field] != original_producer[field] for field in stable):
        raise ValueError("Android current and original producers select different candidate identities")

    final_root = Path(final_capture).absolute()
    protected_root = Path(protected_capture).absolute()
    expected_aar = Path(expected_binary_aar).absolute()
    resolved = [path.resolve(strict=True) for path in (final_root, protected_root, expected_aar)]
    if any(path != resolved[index] for index, path in enumerate(
            (final_root, protected_root, expected_aar))):
        raise ValueError("Android validation inputs must be normalized and non-symbolic")
    if any(left == right or left in right.parents or right in left.parents
           for index, left in enumerate(resolved) for right in resolved[index + 1:]):
        raise ValueError("Android validation inputs must not overlap")
    aar_bytes = read_regular_file_bytes(
        expected_aar, max_bytes=512 * 1024 * 1024, reject_symlink_parents=True)
    if expected_aar.name != "codex-agent-runtime-android-release.aar" or not aar_bytes:
        raise ValueError("Authenticated Android binary AAR is missing, misnamed, or empty")

    final = _capture(final_root, kind="android-evidence-transport", keys=_FINAL_KEYS)
    protected = _capture(
        protected_root, kind="android-firebase-transport", keys=_PROTECTED_KEYS)
    if final["producer"] != capture_producer or protected["producer"] != capture_producer:
        raise ValueError("Android captures differ from the caller-authenticated current producer")
    final_evidence_aar = read_regular_file_bytes(
        final["original"] / (
            "payload/external/android-runtime-evidence/"
            "codex-agent-runtime-android-release.aar"
        ),
        max_bytes=512 * 1024 * 1024, reject_symlink_parents=True,
    )
    if final_evidence_aar != aar_bytes:
        raise ValueError("Android final Firebase AAR differs from the authenticated binary")
    final_receipt_bytes = read_regular_file_bytes(
        final["original"] / "lane-receipt.json", max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True)
    protected_receipt_bytes = read_regular_file_bytes(
        protected["original"] / "lane-receipt.json", max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True)
    final_receipt = load_json_bytes(final_receipt_bytes)
    protected_receipt = load_json_bytes(protected_receipt_bytes)
    if (_receipt_producer(final_receipt, "final original lane producer") != original_producer
            or _receipt_producer(protected_receipt, "protected original lane producer") != original_producer
            or any(type(value) is not dict
                   or require_integer(value.get("schemaVersion"), "Android lane receipt schema")
                        != LANE_RECEIPT_SCHEMA_VERSION
                   or value.get("lane") != "android" or value.get("result") != "passed"
                   or value.get("artifactName") != f"codex-agent-ci-android-{original_producer['tree']}"
                   for value in (final_receipt, protected_receipt))):
        raise ValueError("Android protected and final original lane identities differ from caller authority")

    linked_transport = read_regular_file_bytes(
        protected_root / "linked-final/capture-transport.json",
        max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    linked_receipt = read_regular_file_bytes(
        protected_root / "linked-final/lane-receipt.json",
        max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    binding_bytes = read_regular_file_bytes(
        protected["original"] / "input-binding.json", max_bytes=64 * 1024,
        reject_symlink_parents=True)
    binding = require_exact_keys(load_canonical_json_bytes(binding_bytes), {
        "schemaVersion", "kind", "candidateCommit", "candidateTree",
        "trustedSourceCommit", "trustedSourceTree", "files",
    }, "protected Android input binding")
    if (protected["transport"]["laneReceiptSha256"] != sha256_bytes(protected_receipt_bytes)
            or protected["transport"]["inputBindingSha256"] != sha256_bytes(binding_bytes)
            or protected["transport"]["linkedFinalCaptureSha256"] != sha256_bytes(linked_transport)
            or protected["transport"]["linkedFinalLaneReceiptSha256"] != sha256_bytes(linked_receipt)
            or linked_transport != final["transportBytes"] or linked_receipt != final_receipt_bytes
            or final["transport"]["laneReceiptSha256"] != sha256_bytes(final_receipt_bytes)
            or require_integer(binding["schemaVersion"], "protected Android binding schema") != 1
            or binding["kind"] != "firebase-android-input-binding"
            or binding["candidateCommit"] != original_producer["commit"]
            or binding["candidateTree"] != original_producer["tree"]
            or binding["trustedSourceCommit"] != trusted_source_commit
            or binding["trustedSourceTree"] != trusted_source_tree):
        raise ValueError("Android protected observation linkage differs from caller policy")

    java = Path(java_executable).absolute()
    analyzer = Path(apkanalyzer_executable).absolute()
    if (java.name not in {"java", "java.exe"} or java.resolve(strict=True) != java
            or analyzer.resolve(strict=True) != analyzer):
        raise ValueError("Android validation requires normalized caller-selected tools")
    java_bytes = read_regular_file_bytes(
        java, max_bytes=128 * 1024 * 1024, reject_symlink_parents=True)
    analyzer_bytes = read_regular_file_bytes(
        analyzer, max_bytes=128 * 1024 * 1024, reject_symlink_parents=True)
    tooling_arguments = dict(
        required_trust_domain=required_trust_domain, keyring=tooling_keyring,
        keys_directory=tooling_keys_directory, policy_revision=policy_revision,
    )
    with tempfile.TemporaryDirectory(prefix="sdk-android-validation-") as temporary:
        private = Path(temporary).resolve()
        private_final = private / "final"
        private_protected = private / "protected"
        private_aar = private / expected_aar.name
        snapshot_regular_tree(final_root, private_final, allow_empty=True)
        snapshot_regular_tree(protected_root, private_protected, allow_empty=True)
        private_aar.write_bytes(aar_bytes)

        def unchanged():
            require_no_signing_secret(os.environ)
            if (canonical_json_bytes({
                        "captureProducer": expected_capture_producer,
                        "originalProducer": expected_original_producer,
                    }) != authority_bytes
                    or regular_file_inventory(final_root, allow_empty=True) != final["before"]
                    or regular_file_inventory(protected_root, allow_empty=True) != protected["before"]
                    or regular_file_inventory(private_final, allow_empty=True) != final["before"]
                    or regular_file_inventory(private_protected, allow_empty=True) != protected["before"]
                    or read_regular_file_bytes(expected_aar, max_bytes=512 * 1024 * 1024,
                                               reject_symlink_parents=True) != aar_bytes
                    or read_regular_file_bytes(private_aar, max_bytes=512 * 1024 * 1024,
                                               reject_symlink_parents=True) != aar_bytes
                    or read_regular_file_bytes(java, max_bytes=128 * 1024 * 1024,
                                               reject_symlink_parents=True) != java_bytes
                    or read_regular_file_bytes(analyzer, max_bytes=128 * 1024 * 1024,
                                               reject_symlink_parents=True) != analyzer_bytes):
                raise ValueError("Android validation original inputs or trusted tools changed")

        unchanged()
        try:
            with verified_tooling_capture(
                    tooling_evidence, repository, tooling_public_key, **tooling_arguments) as jar:
                command = [str(java), "-jar", str(jar), "verify-original-firebase-android-evidence",
                    "--evidence-directory",
                    str(private_final / "original/payload/external/android-runtime-evidence"),
                    "--protected-observation-directory", str(private_protected / "original"),
                    "--expected-release-aar", str(private_aar),
                    "--candidate-commit", original_producer["commit"],
                    "--candidate-tree", original_producer["tree"],
                    "--trusted-source-commit", trusted_source_commit,
                    "--trusted-source-tree", trusted_source_tree,
                    "--apkanalyzer-executable", str(analyzer),
                ]
                environment = {key: value for key, value in os.environ.items() if key in {
                    "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR",
                    "LANG", "LC_ALL", "ANDROID_HOME", "ANDROID_SDK_ROOT", "JAVA_HOME",
                }}
                subprocess.run(command, cwd=private, env=environment, check=True,
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            unchanged()
