"""Two-step Core14 context handoff for one protected, pinned-source job.

The first entry runs without a signing secret and replays every original. The
second entry signs only its exact checkpoint bytes. A workflow must run both
entries in that order on the same protected runner, with no candidate command
between them; possession of a checkpoint path alone is not remote authority.
"""

import argparse
import os
from pathlib import Path
import tempfile

from .products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_exact_keys, require_integer, require_sha256,
    sha256_bytes, write_canonical_json,
)
from .products.receipt import validate_phase_receipt
from .products.sdk_package import _require_capability_output_separate
from .products.signing_isolation import require_no_signing_secret
from .products.signatures import (
    load_keyring, require_active_release_key, sign_manifest,
    validate_signing_metadata, verify_manifest_signature,
)
from .sdk_core_metadata_context_preparation import prepare_from_caller_policy
from .sdk_core_metadata_context_policy import prepare_original_core_caller_policy
from .sdk_facade_metadata_original import _context


def prepare_protected_core_context(caller_policy, destination, *, repository_root,
        trusted_workflow_sha, signing_keyring, signing_keys_directory, environ, token):
    """Run the full original reader, then publish its exact unsigned checkpoint."""
    require_no_signing_secret(environ)
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink() or destination.resolve(strict=False) != destination:
        raise ValueError("Protected Core checkpoint destination must be fresh and non-symbolic")
    with tempfile.TemporaryDirectory(prefix="core-protected-replay-") as temporary:
        root = Path(temporary).resolve()
        replayed = root / "replayed"
        manifest = prepare_from_caller_policy(caller_policy, replayed,
            repository_root=repository_root, trusted_workflow_sha=trusted_workflow_sha,
            signing_keyring=signing_keyring, signing_keys_directory=signing_keys_directory,
            environ=environ, token=token)
        raw = read_regular_file_bytes(manifest, max_bytes=64 * 1024, reject_symlink_parents=True)
        record = _record(raw)
        checkpoint = {"schemaVersion": 1, "kind": "sdk-core-metadata-protected-replay",
            "contextSha256": sha256_bytes(raw), "buildKey": record["buildKey"],
            "receiptSha256": record["receiptSha256"], "artifactId": record["artifactId"],
            "artifactSha256": record["artifactSha256"]}
        write_canonical_json(replayed / "replay-checkpoint.json", checkpoint)
        if (read_regular_file_bytes(manifest, max_bytes=64 * 1024, reject_symlink_parents=True) != raw
                or read_regular_file_bytes(replayed / "replay-checkpoint.json") != canonical_json_bytes(checkpoint)):
            raise ValueError("Protected Core replay changed before checkpoint publication")
        publish_regular_tree(replayed, destination, expected_inventory=[
            {"relativePath": name, "bytes": len(value), "sha256": sha256_bytes(value)}
            for name, value in (("original-context.json", raw),
                ("replay-checkpoint.json", canonical_json_bytes(checkpoint)))])
    return checkpoint


def prepare_protected_core_context_from_election(plan, discovery, state, bootstrap_policy,
        metadata_receipt, destination, *, expected_build_key, expected_receipt_sha256,
        metadata_artifact_id, metadata_artifact_sha256, original_context,
        trusted_workflow_sha, repository_root, signing_keyring,
        signing_keys_directory, environ, token, sdk_apple_validation_policy_path=None):
    """Reconstruct caller authority, then replay; never accept a supplied policy alone."""
    require_no_signing_secret(environ)
    with tempfile.TemporaryDirectory(prefix="core-protected-election-") as temporary:
        elected = prepare_original_core_caller_policy(plan, discovery, state,
            bootstrap_policy, metadata_receipt, Path(temporary).resolve() / "policy",
            expected_build_key=expected_build_key,
            expected_receipt_sha256=expected_receipt_sha256,
            metadata_artifact_id=metadata_artifact_id,
            metadata_artifact_sha256=metadata_artifact_sha256,
            original_context=original_context,
            trusted_workflow_sha=trusted_workflow_sha,
            repository_root=repository_root, environ=environ, token=token,
            sdk_apple_validation_policy_path=sdk_apple_validation_policy_path)
        return prepare_protected_core_context(elected, destination,
            repository_root=repository_root, trusted_workflow_sha=trusted_workflow_sha,
            signing_keyring=signing_keyring, signing_keys_directory=signing_keys_directory,
            environ=environ, token=token)


def _record(raw):
    record = require_exact_keys(load_canonical_json_bytes(raw), {
        "schemaVersion", "kind", "buildKey", "receiptSha256", "artifactId",
        "artifactSha256", "producer", "originalContext", "signing",
    }, "Protected Core original context")
    if (require_integer(record["schemaVersion"], "Core context schema", 1) != 1
            or record["kind"] != "sdk-core-metadata-original-context"):
        raise ValueError("Unsupported protected Core original context")
    for name in ("buildKey", "receiptSha256", "artifactSha256"):
        require_sha256(record[name], "Protected Core " + name)
    require_integer(record["artifactId"], "Protected Core upload ID", 1)
    _context(record["originalContext"])
    return record


def sign_protected_core_context(checkpoint_directory, metadata_receipt, destination, *,
        expected_context_sha256, expected_build_key, expected_receipt_sha256,
        expected_artifact_id, expected_artifact_sha256, expected_public_key_sha256, signing_keyring,
        signing_keys_directory, private_key_text, candidate_root):
    """Sign replayed bytes only; never execute the reader or candidate code."""
    for value in (expected_context_sha256, expected_build_key, expected_receipt_sha256,
                  expected_artifact_sha256, expected_public_key_sha256):
        require_sha256(value, "Protected Core selected digest")
    require_integer(expected_artifact_id, "Protected Core selected upload ID", 1)
    if type(private_key_text) is not str or not private_key_text:
        raise ValueError("Protected Core signing key is unavailable")
    root = Path(checkpoint_directory).resolve(strict=True)
    candidate = Path(candidate_root).resolve(strict=True)
    if root == candidate or root.is_relative_to(candidate):
        raise ValueError("Protected Core checkpoint cannot come from candidate source")
    if any(path.resolve(strict=True).is_relative_to(candidate) for path in
           (Path(signing_keyring), Path(signing_keys_directory))):
        raise ValueError("Protected Core signing policy cannot come from candidate source")
    if {path.name for path in root.iterdir()} != {"original-context.json", "replay-checkpoint.json"}:
        raise ValueError("Protected Core checkpoint has an unexpected layout")
    output = Path(destination).absolute()
    _require_capability_output_separate(output, (root, candidate, Path(metadata_receipt),
        Path(signing_keyring), Path(signing_keys_directory)))
    if output.exists() or output.is_symlink() or output.resolve(strict=False) != output:
        raise ValueError("Protected Core signing destination must be fresh and non-symbolic")
    raw = read_regular_file_bytes(root / "original-context.json", max_bytes=64 * 1024,
                                  reject_symlink_parents=True)
    checkpoint_raw = read_regular_file_bytes(root / "replay-checkpoint.json",
        max_bytes=64 * 1024, reject_symlink_parents=True)
    checkpoint = require_exact_keys(load_canonical_json_bytes(checkpoint_raw), {
        "schemaVersion", "kind", "contextSha256", "buildKey", "receiptSha256",
        "artifactId", "artifactSha256"}, "Protected Core replay checkpoint")
    record = _record(raw)
    receipt_raw = read_regular_file_bytes(Path(metadata_receipt), max_bytes=16 * 1024 * 1024,
                                          reject_symlink_parents=True)
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_raw))
    expected = {"buildKey": expected_build_key, "receiptSha256": expected_receipt_sha256,
        "artifactId": expected_artifact_id, "artifactSha256": expected_artifact_sha256}
    if (checkpoint["schemaVersion"] != 1 or checkpoint["kind"] != "sdk-core-metadata-protected-replay"
            or checkpoint["contextSha256"] != expected_context_sha256
            or sha256_bytes(raw) != expected_context_sha256
            or any(checkpoint[name] != value or record[name] != value for name, value in expected.items())
            or tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
                ("sdk", "sdk-core", "metadata", "common")
            or receipt["buildKey"] != expected_build_key
            or sha256_bytes(receipt_raw) != expected_receipt_sha256
            or receipt["producer"] != record["producer"]):
        raise ValueError("Protected Core replay differs from selected original receipt/upload")
    keyring = load_keyring(Path(signing_keyring), Path(signing_keys_directory))
    active, public_key = require_active_release_key(keyring, Path(signing_keys_directory))
    signing = validate_signing_metadata({name: keyring[name] for name in
        ("algorithm", "namespace", "trustDomain")} | active, trust_domain="release")
    if record["signing"] != signing:
        raise ValueError("Protected Core replay signing identity is no longer active")
    public_raw = read_regular_file_bytes(public_key, reject_symlink_parents=True)
    keyring_raw = read_regular_file_bytes(Path(signing_keyring), reject_symlink_parents=True)
    if sha256_bytes(public_raw) != expected_public_key_sha256:
        raise ValueError("Protected Core public key differs from caller-pinned bytes")

    def unchanged():
        if (read_regular_file_bytes(root / "original-context.json", max_bytes=64 * 1024,
                    reject_symlink_parents=True) != raw
                or read_regular_file_bytes(root / "replay-checkpoint.json",
                    max_bytes=64 * 1024, reject_symlink_parents=True) != checkpoint_raw
                or read_regular_file_bytes(Path(metadata_receipt), max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != receipt_raw
                or read_regular_file_bytes(public_key, reject_symlink_parents=True) != public_raw
                or read_regular_file_bytes(Path(signing_keyring), reject_symlink_parents=True) != keyring_raw):
            raise ValueError("Protected Core replay or signing policy changed during signing")

    with tempfile.TemporaryDirectory(prefix="core-protected-sign-") as temporary:
        staged = Path(temporary).resolve()
        manifest = staged / "original-context.json"
        manifest.write_bytes(raw)
        private = staged / "private-key"
        private.touch(mode=0o600, exist_ok=False)
        private.write_bytes(private_key_text.encode("utf-8"))
        unchanged()
        signature = sign_manifest(manifest, private, signing)
        verify_manifest_signature(manifest, signature, public_key, signing)
        private.unlink()
        if read_regular_file_bytes(manifest) != raw:
            raise ValueError("Protected Core context changed while signing")
        unchanged()
        publish_regular_tree(staged, output, expected_inventory=[
            {"relativePath": "original-context.json", "bytes": len(raw), "sha256": sha256_bytes(raw)},
            {"relativePath": signature.name, "bytes": signature.stat().st_size,
             "sha256": sha256_bytes(read_regular_file_bytes(signature))}])
    return output / "original-context.json", output / "original-context.sig"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", allow_abbrev=False)
    for name in ("plan", "discovery", "state", "bootstrap-policy", "metadata-receipt",
                 "destination", "repository-root", "signing-keyring", "signing-keys-directory"):
        prepare.add_argument("--" + name, type=Path, required=True)
    for name in ("trusted-workflow-sha", "expected-build-key", "expected-receipt-sha256",
                 "metadata-artifact-sha256", "original-context"):
        prepare.add_argument("--" + name, required=True)
    prepare.add_argument("--metadata-artifact-id", type=int, required=True)
    prepare.add_argument("--sdk-apple-validation-policy", dest="sdk_apple_validation_policy_path", type=Path)
    sign = commands.add_parser("sign", allow_abbrev=False)
    for name in ("checkpoint-directory", "metadata-receipt", "destination", "signing-keyring",
                 "signing-keys-directory", "candidate-root"):
        sign.add_argument("--" + name, type=Path, required=True)
    for name in ("expected-context-sha256", "expected-build-key", "expected-receipt-sha256",
                 "expected-artifact-sha256", "expected-public-key-sha256"):
        sign.add_argument("--" + name, required=True)
    sign.add_argument("--expected-artifact-id", type=int, required=True)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    try:
        if command == "prepare":
            require_no_signing_secret(os.environ)
            original_context = args.pop("original_context")
            decoded = load_json_bytes(original_context.encode("utf-8"))
            if canonical_json_bytes(decoded).decode().strip() != original_context:
                raise ValueError("Core original context CLI input must be canonical JSON")
            args["original_context"] = decoded
            print(canonical_json_bytes(prepare_protected_core_context_from_election(**args,
                environ=os.environ, token=os.environ["GITHUB_TOKEN"])).decode().strip())
        else:
            sign_protected_core_context(**args,
                private_key_text=os.environ["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"])
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
