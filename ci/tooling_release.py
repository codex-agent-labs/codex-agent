"""Protected original-tooling caller; only independently pinned code may invoke it.

Context checks do not grant environment approval. Original CI observation and
the existing complete tooling closure gate precede every private-key read.
"""

from collections.abc import Mapping
import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from product_release_context import verify_product_release_context
from product_reuse import (
    _CATALOG_ZIP_LIMITS, _download_contract_ci_upload, _observe_ci_producer_jobs,
    _release_trust, _require_artifact_job_window, paginated_items, safe_extract,
    verified_zip_contents,
)
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, sha256_bytes, snapshot_regular_tree, write_canonical_json,
)
from products.signatures import load_keyring, public_key_for_metadata, require_active_release_key, sign_manifest
from products.tooling import ATTESTATION, INPUT_NAMES, _value, _verify_capture, _verify_original


def attest_tooling_ci(repository_root, plan_path, destination, *, trusted_source_sha,
                     trusted_workflow_sha, transport_producer, event_payload,
                     environment: Mapping[str, str], token=None, release_handoffs=(),
                     trusted_workflow_path=None, trusted_job_name=None):
    """Sign exact original tooling bytes, or forward their existing release envelope.

release_handoffs contains complete tooling-evidence directories, not raw JARs
or caller-policy files. An exact match preserves its original signature bytes.
No executable or product bytes are built, executed or repacked here.
"""
    context = verify_product_release_context(repository_root,
        trusted_source_sha=trusted_source_sha, trusted_workflow_sha=trusted_workflow_sha,
        transport_producer=transport_producer, event_payload=event_payload, environment=environment)
    repository_root, producer, source_tree, expected_environment, reason = context
    if (trusted_workflow_path is None) != (trusted_job_name is None):
        raise ValueError("Tooling original workflow path and job must be pinned together")
    release_handoffs = tuple(Path(path) for path in release_handoffs)
    plan_path = Path(plan_path).absolute()
    destination = Path(os.path.abspath(destination))
    if destination.exists() or destination.is_symlink():
        raise ValueError("Tooling caller destination must not exist")
    resolved = destination.parent.resolve(strict=False) / destination.name
    for source in (repository_root, plan_path.parent, *release_handoffs):
        source = Path(source).resolve(strict=True)
        if source == resolved or source in resolved.parents or resolved in source.parents:
            raise ValueError("Tooling caller destination overlaps original inputs or trusted source")
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    plan = load_json_bytes(plan_bytes)
    if type(plan) is not dict or any(plan.get(field) != producer[name] for field, name in (
            ("repository", "repository"), ("event", "event"), ("pullRequest", "pullRequest"),
            ("validationCommit", "commit"), ("validationTree", "tree"))):
        raise ValueError("Tooling original plan differs from protected caller producer")
    inventories = {name: read_regular_file_bytes(plan_path.parent / "inventories/contracts" / name,
                    reject_symlink_parents=True) for name in INPUT_NAMES.values()}
    event_bytes = canonical_json_bytes(event_payload)

    def unchanged():
        if (read_regular_file_bytes(plan_path, reject_symlink_parents=True) != plan_bytes
                or any(read_regular_file_bytes(plan_path.parent / "inventories/contracts" / name,
                    reject_symlink_parents=True) != raw for name, raw in inventories.items())
                or canonical_json_bytes(event_payload) != event_bytes
                or verify_product_release_context(repository_root,
                    trusted_source_sha=trusted_source_sha, trusted_workflow_sha=trusted_workflow_sha,
                    transport_producer=producer, event_payload=event_payload, environment=environment) != context):
            raise ValueError("Tooling caller original inputs or context changed")

    with tempfile.TemporaryDirectory(prefix="tooling-release-caller-") as temporary:
        root = Path(temporary).resolve()
        trust = _release_trust(repository_root, trusted_source_sha, root)
        if trust is None:
            raise ValueError("No active release product-signing key is configured")
        policy = load_keyring(trust.keyring, trust.keys)
        active, public_key = require_active_release_key(policy, trust.keys)
        signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        if token is None:
            token = environment.get("GITHUB_TOKEN")
        if type(token) is not str or not token:
            raise ValueError("Tooling caller requires a GitHub observation token")
        job = ("product-validation / product-contracts"
               if trusted_job_name is None else trusted_job_name)
        workflow_policy = (
            {"trusted_workflow_sha": trusted_workflow_sha}
            if trusted_workflow_path is None else
            {"trusted_workflows_by_phase": {"tooling": {
                "path": trusted_workflow_path, "sha": trusted_workflow_sha,
            }}})
        observed = _observe_ci_producer_jobs({"tooling": producer}, jobs_by_phase={"tooling": job},
            token=token, **workflow_policy)
        name = f"codex-agent-ci-contracts-{producer['tree']}"
        artifacts = paginated_items(
            f"https://api.github.com/repos/{producer['repository']}/actions/runs/{producer['runId']}/artifacts",
            "artifacts", token)
        selected = [item for item in artifacts if type(item) is dict and item.get("name") == name]
        if len(selected) != 1:
            raise ValueError("Original tooling upload is missing or ambiguous")
        artifact, raw = _download_contract_ci_upload(selected[0].get("id"), selected[0].get("digest"),
            name, producer, observed[0]["run"], token)
        _require_artifact_job_window(observed[0], job, artifact)
        prepared = root / "prepared"
        transport = prepared / "transport"
        transport.mkdir(parents=True)
        archive = transport / "original-ci.zip"
        archive.write_bytes(raw)
        verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
        fresh = root / "fresh-evidence"
        original = fresh / "original"
        safe_extract(archive, original / "lane")
        (original / "plan.json").write_bytes(plan_bytes)
        (original / "inventories/contracts").mkdir(parents=True)
        for filename, contents in inventories.items():
            (original / "inventories/contracts" / filename).write_bytes(contents)
        receipt, inventory = _verify_original(original, repository_root)
        expected = {"repository": producer["repository"], "workflowPath": producer["workflowPath"],
            "validationCommit": producer["commit"], "validationTree": producer["tree"],
            "event": producer["event"], "runId": producer["runId"], "runAttempt": producer["runAttempt"],
            "pullRequest": producer["pullRequest"], "artifactName": name}
        if any(receipt.get(field) != value for field, value in expected.items()):
            raise ValueError("Original tooling receipt differs from observed producer/upload")
        value = _value(original, signing, repository_root)
        unchanged()
        retained = None
        for number, candidate in enumerate(release_handoffs):
            before = regular_file_inventory(candidate, allow_empty=True)
            private = root / "reusable" / str(number)
            snapshot_regular_tree(candidate, private, allow_empty=True)
            # Admission authenticates retired keys too, without changing their signatures.
            envelope = load_canonical_json_bytes(read_regular_file_bytes(private / ATTESTATION))
            original_key = public_key_for_metadata(envelope.get("signing") if type(envelope) is dict else None,
                policy, trust.keys, allow_retired=True)
            _verify_capture(private, repository_root, original_key, "release", trust.keyring, trust.keys)
            if before != regular_file_inventory(candidate, allow_empty=True):
                raise ValueError("Original tooling release envelope changed during capture")
            if regular_file_inventory(private / "original", allow_empty=True) == inventory:
                retained = private
                break
        if retained is None:
            unchanged()
            secret = environment.get("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY")
            if type(secret) is not str or not secret:
                raise ValueError("Protected tooling signing key is unavailable")
            private_key = root / "private-key"
            private_key.touch(mode=0o600, exist_ok=False)
            private_key.write_bytes(secret.encode("utf-8"))
            write_canonical_json(fresh / ATTESTATION, value)
            sign_manifest(fresh / ATTESTATION, private_key, signing)
            _verify_capture(fresh, repository_root, public_key, "release", trust.keyring, trust.keys)
            retained = fresh
        unchanged()
        snapshot_regular_tree(retained, prepared / "tooling-evidence", allow_empty=True)
        if regular_file_inventory(prepared / "tooling-evidence/original", allow_empty=True) != inventory:
            raise ValueError("Tooling publication differs from its authenticated original closure")
        snapshot_regular_tree(root / "trust", prepared / "caller-policy")
        write_canonical_json(transport / "original-ci.json", {"artifact": artifact, "observed": observed,
            "producer": producer, "laneReceiptSha256": sha256_bytes(
                read_regular_file_bytes(original / "lane/lane-receipt.json"))})
        caller = {"schemaVersion": 1, "trustedSourceCommit": trusted_source_sha,
            "trustedSourceTree": source_tree, "trustedWorkflowSha": trusted_workflow_sha,
            "transportProducer": producer, "authorizationReason": reason,
            "event": event_payload, "environment": {**expected_environment, "GITHUB_REF": environment.get("GITHUB_REF")}}
        write_canonical_json(prepared / "caller.json", caller)
        publish_regular_tree(prepared, destination, allow_empty=True)
    return caller


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("repository-root", "plan", "destination"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("trusted-source-sha", "trusted-workflow-sha", "validation-tree"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--trusted-workflow-path")
    parser.add_argument("--trusted-job-name")
    parser.add_argument("--release-handoff", type=Path, action="append", default=[])
    arguments = parser.parse_args(argv)
    try:
        payload = load_json_bytes(read_regular_file_bytes(Path(os.environ["GITHUB_EVENT_PATH"]),
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        event = os.environ.get("GITHUB_EVENT_NAME")
        producer = {"repository": os.environ.get("GITHUB_REPOSITORY"), "workflowPath": ".github/workflows/ci.yml",
            "commit": os.environ.get("GITHUB_SHA"), "tree": arguments.validation_tree, "event": event,
            "runId": int(os.environ["GITHUB_RUN_ID"]), "runAttempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
            "pullRequest": payload.get("number") if event == "pull_request" else None}
        attest_tooling_ci(arguments.repository_root, arguments.plan, arguments.destination,
            trusted_source_sha=arguments.trusted_source_sha, trusted_workflow_sha=arguments.trusted_workflow_sha,
            transport_producer=producer, event_payload=payload, environment=os.environ,
            release_handoffs=arguments.release_handoff,
            trusted_workflow_path=arguments.trusted_workflow_path,
            trusted_job_name=arguments.trusted_job_name)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
