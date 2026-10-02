"""Admit one reviewed Runtime recovery without claiming current full acceptance."""

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "ci"))

import product_reuse as products
from impact import evaluate_remote_build_authorization, require_oid
from products.inventory import (
    canonical_json_bytes, git_regular_blob_bytes, load_json_bytes,
    read_regular_file_bytes, run_git,
)
from reuse import github_output


BASELINE_PRODUCER = {
    "commit": "71334f47d32446cc1cfec2998aa2f9ce0328ac9a",
    "event": "pull_request", "pullRequest": 31,
    "repository": "codex-agent-labs/codex-agent", "runAttempt": 1,
    "runId": 36915181232, "tree": "10c7271a886a805e74a8aeb51e8eee0b1f478944",
    "workflowPath": ".github/workflows/ci.yml",
}
BASELINE_WORKFLOW = "6dd15c192538a8e65d47a45224984e864c78e6c7"
BASELINE_JOB = 110550763407
JOB_NAME = "product-validation / workflow-lint"
CORRECTION_REVISION = "1ff05773e873e64633a050b4cef33f37167c2f38"
CI = ".github/workflows/ci.yml"
CORRECTED_FILES = {
    ".github/actions/prepare-runtime-signing/action.yml",
    "ci/tests/test_prepare_runtime_signing_action.py",
}
HELPER = ".github/actions/prepare-runtime-signing/recovery_acceptance.py"
NEW_FILES = {HELPER, "ci/tests/test_runtime_recovery_acceptance.py"}
CONTROL_FILES = CORRECTED_FILES | NEW_FILES | {
    CI, ".github/workflows/product-validation.yml",
    "ci/runtime_preparation_capture.py", "ci/tests/test_runtime_preparation_capture.py",
    "ci/runtime_workflow.py", "ci/tests/test_runtime_workflow.py",
    "ci/runtime_prepared_release.py", "ci/tests/test_runtime_prepared_release.py",
    "ci/runtime_original_ci.py", "ci/tests/test_runtime_aggregate_original_ci.py",
    "ci/runtime_aggregate_release.py", "ci/tests/test_runtime_aggregate_release.py",
    "ci/products/runtime_aggregate_handoff.py", "ci/tests/test_runtime_aggregate_handoff.py",
    "ci/tests/test_runtime_native_attestation_workflow.py",
    "ci/tests/test_runtime_aggregate_attestation_workflow.py",
}


def _tree(root, revision):
    entries = {}
    for record in run_git(root, "ls-tree", "-r", "-z", revision, binary=True).split(b"\0"):
        if record:
            metadata, path = record.split(b"\t", 1)
            entries[path.decode("utf-8")] = tuple(metadata.decode("ascii").split())
    return entries


def _blob(root, revision, path):
    return git_regular_blob_bytes(root, revision, path, max_bytes=16 * 1024 * 1024)


def _activated_ci(original, sha):
    """Only these two literal substitutions may differ from the reviewed tree."""
    result = original
    for prefix in (
        b"    uses: codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@",
        b"      trustedWorkflowSha: ",
    ):
        pattern = re.compile(b"^" + re.escape(prefix) + b"[0-9a-f]{40}$", re.MULTILINE)
        if len(pattern.findall(result)) != 1:
            raise ValueError("Recovery caller must have exactly two literal activation pins")
        result = pattern.sub(lambda match: prefix + sha.encode("ascii"), result)
    return result


def _reviewed_scope(trusted, candidate, sha):
    baseline = _tree(trusted, BASELINE_PRODUCER["tree"])
    reviewed = _tree(trusted, sha)
    changed = {path for path in baseline.keys() | reviewed.keys() if baseline.get(path) != reviewed.get(path)}
    if not changed <= CONTROL_FILES or any(
        reviewed.get(path, ())[:2] != ("100644", "blob")
        or (path in baseline and baseline[path][:2] != ("100644", "blob"))
        or (path not in baseline and path not in NEW_FILES)
        for path in changed
    ):
        raise ValueError("Recovery reviewed delta contains unrelated content, modes or deletions")
    if not NEW_FILES <= reviewed.keys():
        raise ValueError("Reviewed recovery helper and focused test are missing")
    corrected = _tree(trusted, CORRECTION_REVISION)
    if any(corrected.get(path, ())[:2] != ("100644", "blob")
           or reviewed.get(path) != corrected[path] for path in CORRECTED_FILES):
        raise ValueError("Recovery action or composition test differs from the reviewed correction")
    current = _tree(candidate, "HEAD")
    if current.keys() != reviewed.keys() or any(
        current[path] != reviewed[path] for path in current if path != CI
    ) or current.get(CI, ())[:2] != ("100644", "blob"):
        raise ValueError("Recovery candidate differs from the independently reviewed control tree")
    if _blob(candidate, "HEAD", CI) != _activated_ci(_blob(trusted, sha, CI), sha):
        raise ValueError("Recovery candidate caller has changes beyond exact activation pins")


def verify_recovery_acceptance(repository_root, trusted_workflow_sha, *, token, environ):
    sha = require_oid(trusted_workflow_sha, "Reviewed recovery workflow SHA")
    trusted = Path(__file__).resolve().parents[3]
    candidate = Path(repository_root).resolve(strict=True)
    if (candidate == trusted
            or Path(run_git(candidate, "rev-parse", "--show-toplevel").strip()).resolve() != candidate
            or Path(run_git(trusted, "rev-parse", "--show-toplevel").strip()).resolve() != trusted):
        raise ValueError("Recovery requires distinct candidate and reviewed Git checkout roots")
    if (run_git(trusted, "rev-parse", "HEAD").strip() != sha
            or run_git(trusted, "status", "--porcelain", "--untracked-files=no").strip()
            or run_git(candidate, "status", "--porcelain", "--untracked-files=no").strip()):
        raise ValueError("Recovery executable or candidate tracked checkout is not its clean pinned source")
    commit = require_oid(environ.get("GITHUB_SHA"), "Current recovery GitHub SHA")
    if (environ.get("GITHUB_ACTIONS") != "true"
            or environ.get("GITHUB_EVENT_NAME") != "pull_request"
            or environ.get("GITHUB_REPOSITORY") != BASELINE_PRODUCER["repository"]
            or run_git(candidate, "rev-parse", "HEAD").strip() != commit):
        raise ValueError("Recovery requires the actual current same-repository PR checkout")
    payload = load_json_bytes(read_regular_file_bytes(Path(environ["GITHUB_EVENT_PATH"]),
        max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
    request = payload["pull_request"]
    base, head = request["base"]["sha"], request["head"]["sha"]
    if run_git(candidate, "rev-list", "--parents", "-n", "1", "HEAD").split() != [commit, base, head]:
        raise ValueError("Recovery tested merge does not bind the actual event base/head")
    authorized, _, _ = evaluate_remote_build_authorization(
        event="pull_request", event_payload=payload, repository=BASELINE_PRODUCER["repository"],
        pull_request=31, base_commit=base, head_commit=head, validation_commit=commit,
        validation_tree=run_git(candidate, "rev-parse", "HEAD^{tree}").strip(),
        github_ref=environ.get("GITHUB_REF"), github_sha=commit, dispatch_approved=False,
    )
    if not authorized:
        raise ValueError("Recovery current PR event is not authorized for remote continuation")
    _reviewed_scope(trusted, candidate, sha)
    observed = products._observe_ci_producer_jobs(
        {"acceptance": dict(BASELINE_PRODUCER)}, jobs_by_phase={"acceptance": JOB_NAME},
        trusted_workflow_sha=BASELINE_WORKFLOW, token=token,
    )
    jobs = products._matching_ci_jobs(observed[0]["jobs"], JOB_NAME)
    if len(jobs) != 1 or jobs[0]["id"] != BASELINE_JOB:
        raise ValueError("Recovery acceptance is not the fixed successful historical job")
    return {"recovery_control_admitted": True, "full_acceptance_current": False,
        "historical_acceptance_producer": dict(BASELINE_PRODUCER),
        "historical_acceptance_job_id": BASELINE_JOB,
        "historical_acceptance_workflow_sha": BASELINE_WORKFLOW}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_recovery_acceptance(args.repository_root, args.trusted_workflow_sha,
            token=os.environ["GITHUB_TOKEN"], environ=os.environ)
        result["historical_acceptance_producer"] = canonical_json_bytes(
            result["historical_acceptance_producer"]).decode().strip()
        github_output(args.github_output, result)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
