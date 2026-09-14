"""Capture caller-bound tooling transport without granting new signing authority."""

import argparse
import os
from pathlib import Path
import sys
import subprocess
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from product_reuse import (
    _CATALOG_ZIP_LIMITS, _download_contract_ci_upload, _observe_ci_producer_jobs,
    _release_trust, _require_artifact_job_window, safe_extract, verified_zip_contents,
)
from products.inventory import (
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, run_git, snapshot_regular_tree, write_canonical_json,
)
from products.signatures import load_keyring, public_key_for_metadata
from products.tooling import ATTESTATION, verified_tooling_capture
from products.receipt import validate_producer


def _ensure_original_source(repository, producer):
    producer = validate_producer(producer)
    if (producer["repository"] != "codex-agent-labs/codex-agent"
            or producer["workflowPath"] != ".github/workflows/ci.yml"):
        raise ValueError("Original tooling source repository/workflow is unsupported")
    commit = producer["commit"]
    try:
        head = run_git(repository, "rev-parse", "HEAD").strip()
        try:
            run_git(repository, "cat-file", "-e", f"{commit}^{{commit}}")
        except subprocess.CalledProcessError:
            run_git(repository, "fetch", "--no-tags", "--no-write-fetch-head",
                "--no-recurse-submodules", "--no-auto-maintenance",
                "https://github.com/codex-agent-labs/codex-agent.git", commit)
        if (run_git(repository, "rev-parse", f"{commit}^{{commit}}").strip() != commit
                or run_git(repository, "rev-parse", f"{commit}^{{tree}}").strip() != producer["tree"]
                or run_git(repository, "rev-parse", "HEAD").strip() != head):
            raise ValueError("Original tooling source identity or caller HEAD changed")
    except subprocess.CalledProcessError as error:
        raise ValueError("Original tooling source objects are unavailable") from error


def capture_tooling_ci(destination, repository_root, *, artifact_id, artifact_sha256,
                      transport_producer, trusted_workflow_sha, policy_revision,
                      java_executable, token):
    """Create the existing SDK tooling policy from independently authenticated bytes.

    Upload ID/digest and producer come from the trusted caller, not the download.
    The Git policy revision and installed Java path are also caller-owned inputs.
    Original signatures/receipts are preserved; current retrieval is separate.
    """
    repository = Path(repository_root).resolve(strict=True)
    if run_git(repository, "rev-parse", f"{policy_revision}^{{commit}}").strip() != policy_revision:
        raise ValueError("Tooling capture requires an exact caller policy commit")
    java = Path(java_executable)
    if not java.is_absolute():
        raise ValueError("Tooling capture requires an absolute caller Java executable")
    java_bytes = read_regular_file_bytes(java, max_bytes=128 * 1024 * 1024, reject_symlink_parents=True)
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Tooling capture destination must not exist")
    resolved = destination.parent.resolve(strict=False) / destination.name
    for source in (repository, java):
        source = source.resolve(strict=True)
        if source == resolved or source in resolved.parents or resolved in source.parents:
            raise ValueError("Tooling capture output overlaps caller source or Java")
    # Keep policy paths stable even on platforms with a temporary-directory alias.
    if destination != resolved:
        raise ValueError("Tooling capture destination must use its real absolute path")
    with tempfile.TemporaryDirectory(prefix="tooling-ci-capture-") as temporary:
        root = Path(temporary).resolve()
        trust = _release_trust(repository, policy_revision, root)
        if trust is None:
            raise ValueError("Tooling capture requires caller-pinned release keys")
        keyring = load_keyring(trust.keyring, trust.keys)
        job = "product-validation / tooling-attestation"
        observed = _observe_ci_producer_jobs({"tooling": transport_producer},
            jobs_by_phase={"tooling": job}, trusted_workflow_sha=trusted_workflow_sha, token=token)
        name = (f"codex-agent-release-tooling-{transport_producer['tree']}"
                f"-attempt-{transport_producer['runAttempt']}")
        artifact, raw = _download_contract_ci_upload(artifact_id, artifact_sha256, name,
            transport_producer, observed[0]["run"], token)
        _require_artifact_job_window(observed[0], job, artifact)
        prepared = root / "prepared"
        transport = prepared / "transport"
        transport.mkdir(parents=True)
        archive = transport / "original-upload.zip"
        archive.write_bytes(raw)
        verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
        # Downloaded caller.json/caller-policy are retained transport, never authority.
        downloaded = root / "downloaded"
        safe_extract(archive, downloaded)
        evidence = downloaded / "tooling-evidence"
        envelope = load_canonical_json_bytes(read_regular_file_bytes(evidence / ATTESTATION,
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        key = public_key_for_metadata(envelope.get("signing") if type(envelope) is dict else None,
            keyring, trust.keys, allow_retired=True)
        original = regular_file_inventory(evidence, allow_empty=True)
        with verified_tooling_capture(evidence, repository, key, required_trust_domain="release",
                keyring=trust.keyring, keys_directory=trust.keys, policy_revision=policy_revision,
                ensure_original_source=lambda producer: _ensure_original_source(repository, producer)):
            snapshot_regular_tree(evidence, prepared / "evidence", allow_empty=True)
        if regular_file_inventory(prepared / "evidence", allow_empty=True) != original:
            raise ValueError("Tooling capture changed its authenticated original evidence")
        snapshot_regular_tree(root / "trust", prepared / "policy")
        if read_regular_file_bytes(java, reject_symlink_parents=True) != java_bytes:
            raise ValueError("Caller Java executable changed during tooling capture")
        policy = {
            "evidence": str(destination / "evidence"),
            "publicKey": str(destination / "policy/keys" / key.name),
            "javaExecutable": str(java), "requiredTrustDomain": "release",
            "keyring": str(destination / "policy/product-signing-keys.json"),
            "keysDirectory": str(destination / "policy/keys"),
        }
        write_canonical_json(prepared / "tooling-policy.json", policy)
        write_canonical_json(transport / "capture.json", {
            "artifact": artifact, "captureProducer": dict(transport_producer), "observed": observed,
            "policyRevision": policy_revision,
        })
        publish_regular_tree(prepared, destination, allow_empty=True)
    return policy


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("destination", "repository-root", "transport-producer", "java-executable"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    for name in ("artifact-sha256", "trusted-workflow-sha", "policy-revision"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args(argv)
    try:
        producer = load_canonical_json_bytes(read_regular_file_bytes(args.transport_producer,
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        capture_tooling_ci(args.destination, args.repository_root, artifact_id=args.artifact_id,
            artifact_sha256=args.artifact_sha256, transport_producer=producer,
            trusted_workflow_sha=args.trusted_workflow_sha, policy_revision=args.policy_revision,
            java_executable=args.java_executable, token=os.environ["GITHUB_TOKEN"])
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
