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

Before that gate, every proposal must also pass (9.5.0 security fixes):

* ``producer_scope.admit`` (T1-T6: same repository, ``ci.yml``, allowed
  event, exact attempt/job/artifact window, verified PR-N binding, same scope);
* exact equality of the producer's ``ci`` and ``.github`` tree IDs with the
  consumer revision's (B1). A PR-controlled producer ``ci.yml`` could define
  its own job graph; with equal trees the producer ran the consumer's own
  reviewed workflow definitions. No landed/main alternative applies here.
* the proposed tree is bound to GitHub-recorded evidence, never to the
  proposal alone (B1 re-review): ``git merge-tree --write-tree`` of the
  verified base and ``run.head_sha`` must merge cleanly to exactly
  ``producer.tree`` (``[scope:merge-tree]``), and the control trees of
  ``run.head_sha`` must equal those of the consumer's own PR head. A crafted
  commit with the real parents and a clean tree therefore rejects.

Any rejection, missing candidate or API failure returns ``None``: the caller
then runs parity fresh exactly as before. Nothing here grants acceptance.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import io
import json
from pathlib import Path
import re
import subprocess
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


def git_control_trees(root: Path, revision: str) -> dict[str, str]:
    """The ``ci`` and ``.github`` tree IDs at a local commit or tree object."""
    if not isinstance(revision, str) or _OID.fullmatch(revision) is None:
        raise producer_scope.ScopeRejected("control-tree", "Control-tree revision is not an exact object ID")
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-d", "--full-tree", revision, "--",
             *producer_scope.CONTROL_TREES],
            check=True, capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise producer_scope.ScopeRejected("control-tree", f"Control trees of {revision} are unreadable") from error
    trees = {}
    for line in listed.splitlines():
        meta, _, name = line.partition("\t")
        fields = meta.split()
        if len(fields) != 3 or fields[:2] != ["040000", "tree"] or name in trees:
            raise producer_scope.ScopeRejected("control-tree", f"Control trees of {revision} are malformed")
        trees[name] = fields[2]
    return trees


MERGE_TREE_MINIMUM = (2, 38)


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], check=check, capture_output=True, text=True,
                          timeout=120)


def git_version(root: Path) -> tuple[int, int]:
    """The runner's ``git`` (major, minor) version."""
    try:
        text = _git(root, "--version").stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise producer_scope.ScopeRejected("merge-tree", "git version is unreadable") from error
    match = re.match(r"git version ([0-9]+)\.([0-9]+)", text)
    if match is None:
        raise producer_scope.ScopeRejected("merge-tree", f"git version is unrecognised: {text.strip()!r}")
    return int(match.group(1)), int(match.group(2))


def recomputed_merge_tree(root: Path, base: str, head: str, *, version=git_version) -> str:
    """The clean ``git merge-tree --write-tree`` result of ``base`` and ``head``.

    Requires git >= 2.38; an older git, a conflict or any other failure rejects
    (the check is never skipped).
    """
    for label, value in (("base", base), ("head", head)):
        if not isinstance(value, str) or _OID.fullmatch(value) is None:
            raise producer_scope.ScopeRejected("merge-tree", f"Merge {label} is not an exact object ID")
    found = version(root)
    if tuple(found) < MERGE_TREE_MINIMUM:
        raise producer_scope.ScopeRejected(
            "merge-tree", f"git {found[0]}.{found[1]} cannot recompute the merge (needs >= 2.38)")
    try:
        merged = _git(root, "merge-tree", "--write-tree", "--no-messages", base, head, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        raise producer_scope.ScopeRejected("merge-tree", "Merge recomputation failed") from error
    if merged.returncode == 1:
        raise producer_scope.ScopeRejected("merge-tree", "Producer base and head do not merge cleanly")
    lines = merged.stdout.splitlines()
    if merged.returncode != 0 or len(lines) != 1 or _OID.fullmatch(lines[0]) is None:
        raise producer_scope.ScopeRejected("merge-tree", "Merge recomputation did not yield one tree")
    return lines[0]


def require_recomputed_merge(root: Path, base: str, head: str, tree: str, *, version=git_version) -> None:
    """The proposed producer tree is the clean merge of the verified base and run head."""
    if recomputed_merge_tree(root, base, head, version=version) != tree:
        raise producer_scope.ScopeRejected("merge-tree", "Producer tree is not the merge of its base and run head")


def consumer_pull_request_head(root: Path, consumer_commit: str) -> str:
    """The PR-side (second) parent of the consumer's two-parent merge commit."""
    if not isinstance(consumer_commit, str) or _OID.fullmatch(consumer_commit) is None:
        raise producer_scope.ScopeRejected("control-tree", "Consumer commit is not an exact object ID")
    try:
        listed = _git(root, "rev-list", "--parents", "-n", "1", consumer_commit, "--").stdout.split()
    except (OSError, subprocess.SubprocessError) as error:
        raise producer_scope.ScopeRejected("control-tree", "Consumer merge parents are unreadable") from error
    if len(listed) != 3 or listed[0] != consumer_commit or any(_OID.fullmatch(oid) is None for oid in listed):
        raise producer_scope.ScopeRejected("control-tree", "Consumer commit is not a two-parent merge")
    return listed[2]


def candidates(pull_request: int, *, current_run: int, trusted_workflow_sha: str,
               api_json: Callable[[str], Any], jobs: Callable[[str], list],
               download: Callable[[Mapping[str, Any]], bytes],
               association_fetch: Callable[[str], Any], consumer: Mapping[str, Any],
               reject: Callable[[str], None] = lambda reason: None) -> Iterator[dict[str, Any]]:
    """Yield caller-shaped parity policies proposed from PR N's earlier CI runs, newest first.

    Yields ``(policy, evidence)``; each policy already passed
    ``producer_scope.admit`` for ``consumer``, and ``evidence`` holds the
    verified tested-merge ``base`` and GitHub-recorded run ``head``.
    """
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
            yield _candidate(run, pull_request, branch, trusted_workflow_sha, api_json, jobs, download,
                             association_fetch, consumer)
        except (ParityCandidateRejected, producer_scope.ScopeRejected, KeyError, ValueError,
                zipfile.BadZipFile, json.JSONDecodeError) as error:
            reject(f"run {run['id']}: {error}")


def _admit(policy, attempt_jobs, parity, pull_request, api_json, association_fetch, consumer):
    """I1: the composite T1-T6 rule over fresh attempt, commit and association reads."""
    producer = policy["producer"]
    run = api_json(f"{_API}/actions/runs/{producer['runId']}/attempts/{producer['runAttempt']}")
    tested = api_json(f"{_API}/git/commits/{producer['commit']}")
    if (not isinstance(run, dict) or not isinstance(tested, dict) or tested.get("sha") != producer["commit"]
            or not isinstance(tested.get("tree"), dict) or tested["tree"].get("sha") != producer["tree"]):
        raise ParityCandidateRejected("Parity candidate tested commit differs from its plan")
    binding = producer_scope.pull_request_binding(run, tested, expected_commit=producer["commit"],
                                                  pull_request=pull_request, fetch=association_fetch)
    verdict = producer_scope.admit(producer, {
        "run": run, "jobs": attempt_jobs, "artifact": parity, "jobName": PARITY_JOB, "binding": binding,
    }, consumer)
    if verdict.get("rule") != "same-scope" or verdict.get("scope") != pull_request:
        raise ParityCandidateRejected("Parity candidate is not admitted within the consumer's own scope")
    if binding["head"] != run.get("head_sha"):
        raise ParityCandidateRejected("Parity candidate binding differs from its recorded run head")
    return {"base": binding["base"], "head": run["head_sha"]}


def _candidate(run, pull_request, branch, trusted_workflow_sha, api_json, jobs, download,
               association_fetch, consumer):
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
        attempt_jobs = jobs(f"{_API}/actions/runs/{run_id}/attempts/{attempt}/jobs")
        selected = [job for job in attempt_jobs if isinstance(job, dict) and job.get("name") == PARITY_JOB]
        if (len(selected) == 1 and selected[0].get("status") == "completed"
                and selected[0].get("conclusion") == "success" and type(selected[0].get("id")) is int
                and _time(selected[0].get("started_at")) <= created <= _time(selected[0].get("completed_at"))):
            policy = {"schemaVersion": 1, "kind": "completed-sdk-parity", "producer": {
                "repository": producer_scope.REPOSITORY, "workflowPath": producer_scope.CI_WORKFLOW,
                "commit": commit, "tree": tree, "event": "pull_request", "pullRequest": pull_request,
                "runId": run_id, "runAttempt": attempt},
                "workflowSha": trusted_workflow_sha, "jobId": selected[0]["id"],
                "artifactId": parity["id"], "artifactSha256": parity["digest"]}
            evidence = _admit(policy, attempt_jobs, parity, pull_request, api_json, association_fetch, consumer)
            return policy, evidence
    raise ParityCandidateRejected("Parity candidate has no successful parity job for its upload")


def discover(root: Path, state: Any, *, environ: Mapping[str, str], token: str, trusted_workflow_sha: str,
             completed_parity: Callable[..., dict[str, Any]], api_json=None, jobs=None, download=None,
             association_fetch=None, control_trees=None, merge_tree=None, consumer_head=None,
             log=lambda message: print(message, file=sys.stderr, flush=True)) -> dict[str, Any] | None:
    """Return authenticated original parity for the current state, or None to run fresh."""
    from products.inventory import canonical_json_bytes
    if api_json is None or jobs is None or download is None:
        from runtime_reference_transport import api_json as fetch, download_artifact, paginated_items
        api_json = api_json or (lambda url: fetch(url, token))
        jobs = jobs or (lambda url: paginated_items(url, "jobs", token))
        download = download or (lambda artifact: download_artifact(artifact, token))
    if association_fetch is None:
        from product_reuse import _association_fetch
        association_fetch = _association_fetch("https://api.github.com", producer_scope.REPOSITORY, token)
    if control_trees is None:
        control_trees = lambda revision: git_control_trees(root, revision)
    if merge_tree is None:
        merge_tree = lambda base, head, tree: require_recomputed_merge(root, base, head, tree)
    if consumer_head is None:
        consumer_head = lambda commit: consumer_pull_request_head(root, commit)
    scope = reuse_scope(state.plan, state.consumer, environ)
    consumer = producer_scope.consumer_scope(environ)
    try:
        consumer_trees = control_trees(state.plan["validationCommit"])
        head = consumer_head(state.plan["validationCommit"])
        if consumer["event"] == "merge_group":
            # The queue group head's PR side must be PR N's current head.
            pull = api_json(f"{_API}/pulls/{scope}")
            if not isinstance(pull, dict) or not isinstance(pull.get("head"), dict) or pull["head"].get("sha") != head:
                raise producer_scope.ScopeRejected("control-tree",
                                                   "Merge-queue group head's PR side is not the PR head")
        consumer_head_trees = control_trees(head)
    except producer_scope.ScopeRejected as error:
        log(f"sdk-parity reuse: consumer control trees unavailable ({error}); running fresh")
        return None
    current_run = state.consumer["producer"]["runId"]
    trials = 0
    for policy, evidence in candidates(scope, current_run=current_run, trusted_workflow_sha=trusted_workflow_sha,
                             api_json=api_json, jobs=jobs, download=download,
                             association_fetch=association_fetch, consumer=consumer,
                             reject=lambda reason: log(f"sdk-parity reuse candidate rejected: {reason}")):
        if trials == MAX_TRIALS:
            break
        trials += 1
        try:
            # B1: bind the proposed tree to GitHub-recorded evidence (the run head
            # and the verified base), then require the consumer's own reviewed
            # ci/ and .github trees at both the producer head and the merge.
            merge_tree(evidence["base"], evidence["head"], policy["producer"]["tree"])
            producer_scope.require_equal_control_trees(control_trees(evidence["head"]), consumer_head_trees)
            producer_scope.require_equal_control_trees(control_trees(policy["producer"]["tree"]), consumer_trees)
        except producer_scope.ScopeRejected as error:
            log(f"sdk-parity reuse candidate rejected: run {policy['producer']['runId']}: {error}")
            continue
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
