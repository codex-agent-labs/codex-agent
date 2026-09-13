"""One caller-ordered signed-tooling lookup; never a second product planner."""

import argparse
import os
from pathlib import Path
import re
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from product_reuse import _CATALOG_LIMIT, _CATALOG_ZIP_LIMITS, _release_trust
from reuse import api_json, download_artifact, paginated_items
from tooling_capture import capture_tooling_ci
from products.inventory import (
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    require_integer, require_sha256, run_git, verified_zip_contents, write_canonical_json,
)
from products.receipt import validate_producer


_API = "https://api.github.com/repos/codex-agent-labs/codex-agent/actions"
_NAME = re.compile(r"codex-agent-release-tooling-([0-9a-f]{40})-attempt-([1-9][0-9]*)")


def candidate_run_ids(artifacts):
    """Reuse the caller's global listing; hints still require full authentication."""
    candidates = []
    for artifact in artifacts:
        if (type(artifact) is not dict or type(artifact.get("name")) is not str
                or _NAME.fullmatch(artifact["name"]) is None or artifact.get("expired") is not False):
            continue
        identifier = artifact.get("id")
        run = artifact.get("workflow_run")
        run_id = run.get("id") if type(run) is dict else None
        if type(identifier) is int and identifier > 0 and type(run_id) is int and run_id > 0:
            candidates.append((identifier, run_id))
    return tuple(dict.fromkeys(run_id for _, run_id in sorted(candidates, reverse=True)))


def discover_tooling_ci(destination, repository_root, *, candidate_run_ids,
                        trusted_workflow_sha, policy_revision, java_executable, token):
    """Candidate hints cannot bypass capture's original job/signature/policy gate."""
    runs = tuple(dict.fromkeys(require_integer(value, "Candidate tooling run ID", 1)
                               for value in candidate_run_ids))
    repository = Path(repository_root).resolve(strict=True)
    if run_git(repository, "rev-parse", f"{policy_revision}^{{commit}}").strip() != policy_revision:
        raise ValueError("Tooling discovery requires an exact caller policy commit")
    if not isinstance(trusted_workflow_sha, str) or re.fullmatch(r"[0-9a-f]{40}", trusted_workflow_sha) is None:
        raise ValueError("Tooling discovery requires a pinned workflow SHA")
    java = Path(java_executable)
    if not java.is_absolute():
        raise ValueError("Tooling discovery requires an absolute caller Java path")
    java_bytes = read_regular_file_bytes(java, max_bytes=128 * 1024 * 1024, reject_symlink_parents=True)
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Tooling discovery destination must not exist")
    if destination != destination.parent.resolve(strict=False) / destination.name:
        raise ValueError("Tooling discovery requires a real absolute destination")
    for source in (repository, java):
        if destination == source or destination in source.parents or source in destination.parents:
            raise ValueError("Tooling discovery output overlaps caller inputs")
    report = {"schemaVersion": 1, "selected": None, "attempts": [], "toolingPolicy": None}
    with tempfile.TemporaryDirectory(prefix="tooling-discovery-") as temporary:
        root = Path(temporary).resolve()
        if _release_trust(repository, policy_revision, root) is None:
            raise ValueError("Tooling discovery requires caller-pinned release keys")
        prepared = root / "prepared"
        prepared.mkdir()
        for run_id in runs:
            artifacts = paginated_items(f"{_API}/runs/{run_id}/artifacts", "artifacts", token)
            for artifact in artifacts:
                match = _NAME.fullmatch(artifact.get("name", "")) if type(artifact) is dict and type(artifact.get("name")) is str else None
                if match is None or artifact.get("expired") is not False:
                    continue
                identifier_hint = artifact.get("id")
                attempt = {"runId": run_id, "artifactId": identifier_hint
                           if type(identifier_hint) is int and identifier_hint > 0 else None}
                try:
                    identifier = require_integer(artifact.get("id"), "Tooling candidate artifact ID", 1)
                    digest = require_sha256(artifact.get("digest"), "Tooling candidate digest")
                    detail_url = f"{_API}/artifacts/{identifier}"
                    detail = api_json(detail_url, token)
                    if any(detail.get(field) != artifact.get(field) for field in
                           ("id", "name", "digest", "expired", "size_in_bytes", "workflow_run")):
                        raise ValueError("Tooling candidate changed after listing")
                    size = require_integer(detail.get("size_in_bytes"), "Tooling candidate bytes", 1)
                    if (size > _CATALOG_LIMIT or detail.get("archive_download_url") != detail_url + "/zip"
                            or type(detail.get("workflow_run")) is not dict
                            or detail["workflow_run"].get("id") != run_id):
                        raise ValueError("Tooling candidate transport is not the expected run/upload")
                    raw = download_artifact(detail, token)
                    if len(raw) != size:
                        raise ValueError("Tooling candidate transport length differs")
                    archive = root / "locator.zip"
                    archive.write_bytes(raw)
                    _, contents, _ = verified_zip_contents(archive, retained_paths=("caller.json",),
                        max_retained_bytes=16 * 1024 * 1024, allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
                    caller = load_canonical_json_bytes(contents.get("caller.json", b""))
                    producer = validate_producer(caller.get("transportProducer") if type(caller) is dict else None)
                    if (producer["runId"] != run_id or producer["tree"] != match[1]
                            or producer["runAttempt"] != int(match[2])):
                        raise ValueError("Tooling locator differs from original upload identity")
                    policy = capture_tooling_ci(prepared / "capture", repository,
                        artifact_id=identifier, artifact_sha256=digest, transport_producer=producer,
                        trusted_workflow_sha=trusted_workflow_sha, policy_revision=policy_revision,
                        java_executable=java, token=token)
                except (ValueError, OSError) as error:
                    attempt.update(result="miss", reason=str(error))
                    report["attempts"].append(attempt)
                    continue
                # Only invocation paths change; signed evidence/original receipts do not.
                for field in ("evidence", "publicKey", "keyring", "keysDirectory"):
                    policy[field] = str(destination / Path(policy[field]).relative_to(prepared))
                write_canonical_json(prepared / "capture/tooling-policy.json", policy)
                report["selected"] = {"artifactId": identifier, "artifactSha256": digest,
                                      "transportProducer": producer}
                report["toolingPolicy"] = policy
                attempt.update(result="selected", reason="authenticated-compatible-tooling")
                report["attempts"].append(attempt)
                break
            if report["selected"] is not None:
                break
        if read_regular_file_bytes(java, reject_symlink_parents=True) != java_bytes:
            raise ValueError("Caller Java changed during tooling discovery")
        write_canonical_json(prepared / "discovery.json", report)
        publish_regular_tree(prepared, destination, allow_empty=True)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("destination", "repository-root", "java-executable"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("trusted-workflow-sha", "policy-revision"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--candidate-run-id", type=int, action="append", default=[])
    args = parser.parse_args(argv)
    try:
        discover_tooling_ci(args.destination, args.repository_root, candidate_run_ids=args.candidate_run_id,
            trusted_workflow_sha=args.trusted_workflow_sha, policy_revision=args.policy_revision,
            java_executable=args.java_executable, token=os.environ["GITHUB_TOKEN"])
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
