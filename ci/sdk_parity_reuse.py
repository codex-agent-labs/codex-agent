"""Exact-input reuse of an earlier attested SDK parity result (9.5.0).

Discovery only *proposes* candidates from the consumer's own PR scope (T4a:
the PR's earlier ``pull_request`` runs, which also serve its merge-queue
group ``pr-N``). Every proposal is then authenticated by the existing
``sdk_completion._completed_parity`` gate, which binds the reuse key to the
exact consumed inputs:

* every current SDK/Contract/Runtime phase identity, build key, receipt and
  object digest (``original-phase-identities.json`` must equal the current
  result exactly);
* the parity verifier recipe (compiler inputs, ``ci/sdk_workflow.py`` and
  ``ci/products/sdk_package.py``) at the producer tree and current revision;
* the ``sdk-binding-parity.yml`` publisher SHA (must equal the current one);
* the exact producer run/attempt, successful job, upload window, artifact ID
  and SHA-256, and the durable PR association (``producer_scope``).

Any rejection, missing candidate or API failure returns ``None``: the caller
then runs parity fresh exactly as before. Nothing here grants acceptance.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import re
import sys
import tempfile
import urllib.parse
import zipfile
from typing import Any, Callable, Iterator, Mapping

import producer_scope

PARITY_JOB = "product-validation / sdk-parity / sdk-parity"
PARITY_PREFIX = "codex-agent-sdk-binding-parity-"
PLAN_PREFIX = "codex-agent-ci-plan-control-"
MAX_RUNS = 30
MAX_ATTEMPTS = 3
MAX_TRIALS = 4
PLAN_LIMIT = 4 * 1024 * 1024
_OID = re.compile(r"[0-9a-f]{40}")
_API = "https://api.github.com/repos/" + producer_scope.REPOSITORY


class ParityCandidateRejected(ValueError):
    pass


def reuse_scope(plan: Mapping[str, Any], consumer: Mapping[str, Any], environ: Mapping[str, str]) -> int:
    """The consumer's PR scope N (pull_request N, or merge group ``pr-N``)."""
    scope = producer_scope.require_consumer_environment(environ, plan)
    producer = consumer.get("producer") if isinstance(consumer, dict) else None
    if (not isinstance(producer, dict) or producer.get("event") != scope["event"]
            or producer.get("commit") != plan.get("validationCommit")
            or scope["event"] == "pull_request" and producer.get("pullRequest") != scope["pullRequest"]):
        raise producer_scope.ScopeRejected("consumer", "Parity consumer differs from its plan scope")
    return scope["pullRequest"]


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ParityCandidateRejected("Parity candidate timestamp is missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() != timedelta(0):
        raise ParityCandidateRejected("Parity candidate timestamp is not UTC")
    return parsed


def _read_plan(archive: bytes, *, tree: str, pull_request: int) -> str:
    """Untrusted proposal only: the commit is re-proved by the tested-merge gate."""
    if len(archive) > PLAN_LIMIT:
        raise ParityCandidateRejected("Parity candidate plan exceeds its bound")
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        members = [info for info in bundle.infolist() if not info.is_dir()]
        if [info.filename for info in members] != ["impact-plan.json"] or members[0].file_size > PLAN_LIMIT:
            raise ParityCandidateRejected("Parity candidate plan archive is not one impact plan")
        plan = json.loads(bundle.read(members[0]))
    commit = plan.get("validationCommit") if isinstance(plan, dict) else None
    if (not isinstance(commit, str) or _OID.fullmatch(commit) is None or plan.get("validationTree") != tree
            or plan.get("event") != "pull_request" or plan.get("pullRequest") != pull_request
            or plan.get("repository") != producer_scope.REPOSITORY):
        raise ParityCandidateRejected("Parity candidate plan is not this PR's tested commit")
    return commit


def candidates(pull_request: int, *, current_run: int, trusted_workflow_sha: str,
               api_json: Callable[[str], Any], jobs: Callable[[str], list],
               download: Callable[[Mapping[str, Any]], bytes],
               reject: Callable[[str], None] = lambda reason: None) -> Iterator[dict[str, Any]]:
    """Yield caller-shaped parity policies proposed from PR N's earlier CI runs, newest first."""
    if type(pull_request) is not int or pull_request < 1 or type(current_run) is not int or current_run < 1:
        raise ValueError("Parity discovery requires an exact PR scope and current run")
    if not isinstance(trusted_workflow_sha, str) or _OID.fullmatch(trusted_workflow_sha) is None:
        raise ValueError("Parity discovery requires the exact current publisher SHA")
    pull = api_json(f"{_API}/pulls/{pull_request}")
    head = pull.get("head") if isinstance(pull, dict) else None
    head_repo = head.get("repo") if isinstance(head, dict) else None
    if (not isinstance(head_repo, dict) or head_repo.get("full_name") != producer_scope.REPOSITORY
            or head_repo.get("fork") is not False or not isinstance(head.get("ref"), str) or not head["ref"]):
        raise producer_scope.ScopeRejected("fork", "Parity scope pull request is not a same-repository branch")
    branch = head["ref"]
    query = urllib.parse.urlencode({"event": "pull_request", "status": "completed", "branch": branch,
                                    "per_page": MAX_RUNS})
    listed = api_json(f"{_API}/actions/workflows/ci.yml/runs?{query}").get("workflow_runs")
    if not isinstance(listed, list):
        raise ValueError("GitHub response is missing workflow_runs")
    for run in sorted((row for row in listed if isinstance(row, dict) and type(row.get("id")) is int
                       and 0 < row["id"] < current_run), key=lambda row: row["id"], reverse=True):
        try:
            yield _candidate(run, pull_request, branch, trusted_workflow_sha, api_json, jobs, download)
        except (ParityCandidateRejected, producer_scope.ScopeRejected, KeyError, ValueError,
                zipfile.BadZipFile, json.JSONDecodeError) as error:
            reject(f"run {run['id']}: {error}")


def _candidate(run, pull_request, branch, trusted_workflow_sha, api_json, jobs, download):
    producer_scope.require_same_repository_run(run)
    if (run.get("event") != "pull_request" or run.get("path") != producer_scope.CI_WORKFLOW
            or run.get("head_branch") != branch):
        raise ParityCandidateRejected("Parity candidate is not this PR's CI run")
    run_id = run["id"]
    artifacts = api_json(f"{_API}/actions/runs/{run_id}/artifacts?per_page=100").get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("GitHub response is missing artifacts")
    live = [row for row in artifacts if isinstance(row, dict) and row.get("expired") is False
            and isinstance(row.get("name"), str)]
    parity = [row for row in live if row["name"].startswith(PARITY_PREFIX)]
    if len(parity) != 1:
        raise ParityCandidateRejected("Parity candidate has no single unexpired parity upload")
    parity = parity[0]
    tree = parity["name"].removeprefix(PARITY_PREFIX)
    if _OID.fullmatch(tree) is None:
        raise ParityCandidateRejected("Parity candidate upload does not name its tree")
    plans = [row for row in live if row["name"] == PLAN_PREFIX + tree]
    if len(plans) != 1:
        raise ParityCandidateRejected("Parity candidate lacks its unexpired plan")
    commit = _read_plan(download(plans[0]), tree=tree, pull_request=pull_request)
    created = _time(parity.get("created_at"))
    latest = run.get("run_attempt")
    if type(latest) is not int or latest < 1:
        raise ParityCandidateRejected("Parity candidate run attempt is malformed")
    for attempt in range(latest, max(0, latest - MAX_ATTEMPTS), -1):
        selected = [job for job in jobs(f"{_API}/actions/runs/{run_id}/attempts/{attempt}/jobs")
                    if isinstance(job, dict) and job.get("name") == PARITY_JOB]
        if (len(selected) == 1 and selected[0].get("status") == "completed"
                and selected[0].get("conclusion") == "success" and type(selected[0].get("id")) is int
                and _time(selected[0].get("started_at")) <= created <= _time(selected[0].get("completed_at"))):
            return {"schemaVersion": 1, "kind": "completed-sdk-parity", "producer": {
                "repository": producer_scope.REPOSITORY, "workflowPath": producer_scope.CI_WORKFLOW,
                "commit": commit, "tree": tree, "event": "pull_request", "pullRequest": pull_request,
                "runId": run_id, "runAttempt": attempt},
                "workflowSha": trusted_workflow_sha, "jobId": selected[0]["id"],
                "artifactId": parity["id"], "artifactSha256": parity["digest"]}
    raise ParityCandidateRejected("Parity candidate has no successful parity job for its upload")


def discover(root: Path, state: Any, *, environ: Mapping[str, str], token: str, trusted_workflow_sha: str,
             completed_parity: Callable[..., dict[str, Any]], api_json=None, jobs=None, download=None,
             log=lambda message: print(message, file=sys.stderr, flush=True)) -> dict[str, Any] | None:
    """Return authenticated original parity for the current state, or None to run fresh."""
    from products.inventory import canonical_json_bytes
    if api_json is None or jobs is None or download is None:
        from runtime_reference_transport import api_json as fetch, download_artifact, paginated_items
        api_json = api_json or (lambda url: fetch(url, token))
        jobs = jobs or (lambda url: paginated_items(url, "jobs", token))
        download = download or (lambda artifact: download_artifact(artifact, token))
    scope = reuse_scope(state.plan, state.consumer, environ)
    current_run = state.consumer["producer"]["runId"]
    trials = 0
    for policy in candidates(scope, current_run=current_run, trusted_workflow_sha=trusted_workflow_sha,
                             api_json=api_json, jobs=jobs, download=download,
                             reject=lambda reason: log(f"sdk-parity reuse candidate rejected: {reason}")):
        if trials == MAX_TRIALS:
            break
        trials += 1
        with tempfile.TemporaryDirectory(prefix="sdk-parity-discovered-") as temporary:
            path = Path(temporary).resolve() / "parity-policy.json"
            path.write_bytes(canonical_json_bytes(policy))
            try:
                return completed_parity(root, state.plan["validationCommit"], state.prior, path, None, token,
                                        admitted_scope=scope)
            except ValueError as error:
                log(f"sdk-parity reuse candidate rejected: run {policy['producer']['runId']}: {error}")
    log("sdk-parity reuse: no admissible exact-input parity; running fresh")
    return None
