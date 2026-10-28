"""Recover original iOS binary inputs and verify their original native content."""

from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_integer, require_object, sha256_bytes,
    snapshot_regular_tree,
)
from products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId
from products.restore import restore_object, verify_phase_shard
from products.sdk_apple_native_replay import verify_sdk_apple_original_native_content
from products.sdk_apple_content import _input_inventory
from sdk_apple_native import (LANES, NATIVE_TOOLCHAINS, verified_sdk_apple_native_inputs,
                              verified_retained_sdk_apple_native_inputs)


@contextmanager
def verified_original_ios_binary(plan, binary_receipt_path, *, artifact_id, artifact_sha256,
        trusted_workflow_sha, repository_root, environ, token, rust_host,
        tooling_evidence, tooling_public_key, java_executable, policy_revision, required_trust_domain,
        tooling_keyring=None, tooling_keys_directory=None):
    with _verified_ios_binary(plan, binary_receipt_path, binary_capture=None,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            repository_root=repository_root, environ=environ, token=token, rust_host=rust_host,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
            java_executable=java_executable, policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory) as value:
        yield value


@contextmanager
def verified_retained_ios_binary(plan, binary_receipt_path, *, binary_capture,
        repository_root, rust_host, tooling_evidence, tooling_public_key, java_executable,
        policy_revision, required_trust_domain, tooling_keyring=None, tooling_keys_directory=None):
    """Replay bytes within an independently authenticated enclosing capture/catalog.

    Stored transport records do not confer authority. This entrypoint runs the
    same full native source/toolchain gate without reacquiring remote uploads.
    """
    with _verified_ios_binary(plan, binary_receipt_path, binary_capture=Path(binary_capture),
            repository_root=repository_root, rust_host=rust_host,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
            java_executable=java_executable, policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory) as value:
        yield value


@contextmanager
def _verified_ios_binary(plan, binary_receipt_path, *, binary_capture,
        repository_root, rust_host, tooling_evidence, tooling_public_key, java_executable,
        policy_revision, required_trust_domain, tooling_keyring=None, tooling_keys_directory=None,
        artifact_id=None, artifact_sha256=None, trusted_workflow_sha=None, environ=None, token=None):
    """Keep selected binary and independently authenticated native originals alive.

    The authenticated binary upload supplies only native upload locators. Each
    native upload is independently observed against the original binary producer.
    The caller selects the expected Rust host independently of these artifacts.
    Native source/toolchain replay must pass before yielding. Final binary-host
    and phase admission remain separate; no replacement receipt is emitted.
    """
    receipt_path = Path(binary_receipt_path)
    retained_inventory = _input_inventory(binary_capture, allow_empty=True) if binary_capture is not None else None
    plan_bytes = read_regular_file_bytes(Path(plan), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt_bytes = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True)
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    instance = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
    if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
            "sdk", "sdk-ios", "binary", "ios"):
        raise ValueError("Original Apple binary requires an exact binary receipt")
    with tempfile.TemporaryDirectory(prefix="original-ios-binary-") as temporary:
        private = Path(temporary).resolve()
        selected_receipt = private / "selected-binary-receipt.json"
        selected_receipt.write_bytes(receipt_bytes)
        capture = private / "capture"
        if binary_capture is None:
            product_reuse.capture_sdk_ios_binary_upload(plan, capture, binary_receipt_path=receipt_path,
                artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
                repository_root=repository_root, environ=environ, token=token)
        else:
            snapshot_regular_tree(binary_capture, capture, allow_empty=True)
            if regular_file_inventory(capture, allow_empty=True) != retained_inventory:
                raise ValueError("Retained Apple binary changed during private capture")
            product_reuse.verify_retained_sdk_ios_upload(capture, receipt_bytes)
            if regular_file_inventory(capture, allow_empty=True) != retained_inventory:
                raise ValueError("Retained Apple binary changed during archive verification")
        original = capture / "original"
        captured_inventory = regular_file_inventory(capture, allow_empty=True)
        shard = verify_phase_shard(original / "shard", instance)
        stage = private / "stage"
        restored = restore_object(original / "shard" / shard["objectPath"], stage,
            build_key=shard["buildKey"], receipt_sha256=shard["receiptSha256"], object_sha256=shard["objectSha256"])
        if restored["receiptBytes"] != receipt_bytes:
            raise ValueError("Original Apple binary differs from the selected receipt")
        stage_inventory = regular_file_inventory(stage)
        retained = original / "native-original"
        transport = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
            retained / "native-transport.json", max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)),
            {"schemaVersion", "captureProducer", "observed", "artifacts", "receiptSha256s"},
            "Original Apple binary native transport")
        if (require_integer(transport["schemaVersion"], "Apple native transport schema", 1) != 1
                or transport["captureProducer"] != receipt["producer"]):
            raise ValueError("Original Apple native capture differs from the binary producer")
        artifacts = require_exact_keys(transport["artifacts"], LANES, "Original Apple native artifacts")
        uploads = {}
        for lane in LANES:
            artifact = require_object(artifacts[lane], "Original Apple native artifact")
            uploads[lane] = {"artifactId": artifact.get("id"), "artifactSha256": artifact.get("digest")}
        original_plan = retained / "plan/impact-plan.json"
        toolchains = private / "toolchains"
        toolchain_inventory = None

        def unchanged():
            if ((binary_capture is not None and _input_inventory(binary_capture, allow_empty=True) != retained_inventory)
                    or read_regular_file_bytes(Path(plan), max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True) != plan_bytes
                    or read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True) != receipt_bytes
                    or read_regular_file_bytes(selected_receipt) != receipt_bytes
                    or regular_file_inventory(capture, allow_empty=True) != captured_inventory
                    or regular_file_inventory(stage) != stage_inventory
                    or (toolchain_inventory is not None and
                        regular_file_inventory(toolchains) != toolchain_inventory)):
                raise ValueError("Original Apple binary inputs changed during recovery")

        try:
            native_context = (verified_sdk_apple_native_inputs(original_plan, uploads=uploads,
                    original_binary_receipt_path=selected_receipt, trusted_workflow_sha=trusted_workflow_sha,
                    repository_root=repository_root, environ=environ, token=token) if binary_capture is None else
                verified_retained_sdk_apple_native_inputs(retained,
                    original_binary_receipt_path=selected_receipt, repository_root=repository_root))
            with native_context as native:
                binding = native["transport"].get("binaryReceiptSha256") if binary_capture is None else native["binaryReceiptSha256"]
                if (native["producer"] != receipt["producer"]
                        or binding != sha256_bytes(receipt_bytes)):
                    raise ValueError("Recovered Apple native producer differs from the original binary")
                # Compare exact original payloads, not current transport observations.
                for subtree in ("archives", "lanes", "native-evidence", "plan"):
                    if regular_file_inventory(retained / subtree, allow_empty=True) != regular_file_inventory(
                            native["captureRoot"] / subtree, allow_empty=True):
                        raise ValueError("Recovered Apple native originals differ from the binary capture")
                if transport["receiptSha256s"] != native["transport"]["receiptSha256s"]:
                    raise ValueError("Recovered Apple native receipts differ from the binary capture")
                unchanged()
                toolchains.mkdir()
                captured_files = {row["relativePath"]: row for row in captured_inventory}
                for lane, relative in NATIVE_TOOLCHAINS.items():
                    raw = read_regular_file_bytes(native["captureRoot"] / "lanes" / lane / relative,
                        max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
                    expected = captured_files.get(f"original/native-original/lanes/{lane}/{relative}")
                    if expected is None or (len(raw), sha256_bytes(raw)) != (expected["bytes"], expected["sha256"]):
                        raise ValueError("Original Apple toolchain observations differ from the authenticated capture")
                    (toolchains / Path(relative).name).write_bytes(raw)
                toolchain_inventory = regular_file_inventory(toolchains)
                verify_sdk_apple_original_native_content(
                    evidence_directory=native["directory"], toolchain_directory=toolchains,
                    original_producers=native["originalProducers"], source_revision=receipt["producer"]["commit"],
                    rust_host=rust_host, repository=Path(repository_root), tooling_evidence=tooling_evidence,
                    tooling_public_key=tooling_public_key, java_executable=java_executable,
                    policy_revision=policy_revision, required_trust_domain=required_trust_domain,
                    tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
                )
                unchanged()
                yield {"stage": stage, "receiptPath": original / "shard/phase-receipt.json",
                       "receiptBytes": receipt_bytes, "original": original,
                       "binaryCapture": capture, "native": native}
        finally:
            unchanged()
