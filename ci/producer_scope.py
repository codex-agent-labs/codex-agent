"""Durable producer and consumer scope for reuse admission (trust rule T1-T6).

GitHub fills ``run.pull_requests`` only while a pull request is open, so a
merged PR's historical runs lose their live association. This control-only
module binds a producer to its pull request through durable evidence instead:

* the tested merge commit's parents ``[base, run.head_sha]``;
* ``GET commits/{run.head_sha}/pulls`` (exactly one same-repository PR);
* Git ancestry through ``GET compare``: the run head is an ancestor of the
  PR head, a merged PR head is an ancestor of its merge commit, and the tested
  base is an ancestor of ``main``.

Every function is pure over caller-fetched JSON and fails closed with a
structured ``ScopeRejected`` reason. Callers keep their own identity pins
(T2/T5); this module only decides association and scope (T1, T3, T4, T6).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Mapping

REPOSITORY = "codex-agent-labs/codex-agent"
MAIN = "main"
CI_WORKFLOW = ".github/workflows/ci.yml"
PRODUCER_EVENTS = frozenset({"pull_request", "merge_group", "workflow_dispatch"})
CONSUMER_EVENTS = frozenset({"pull_request", "merge_group"})
DISPATCH_AUTHORIZATION_JOB = "product-validation / dispatch-authorization"

_OID = re.compile(r"[0-9a-f]{40}")
_QUEUE_BRANCH = re.compile(r"gh-readonly-queue/main/pr-([1-9][0-9]{0,9})-[0-9a-f]{40}")
_PULL_REF = re.compile(r"refs/pull/([1-9][0-9]{0,9})/merge")

REASONS = frozenset({
    "malformed", "repository", "fork", "workflow", "event", "dispatch-unauthorized",
    "run-identity", "attempt", "job", "artifact-expired", "artifact-window", "artifact-identity",
    "association-missing", "association-ambiguous", "association-disagrees", "ancestry",
    "base-not-main", "not-merged", "merge-group-ref", "foreign-scope", "producer-tree-unapproved",
    "consumer",
})


class ScopeRejected(ValueError):
    """A structured, fail-closed scope refusal."""

    def __init__(self, reason: str, detail: str):
        if reason not in REASONS:
            raise ValueError(f"Unknown scope rejection reason: {reason}")
        self.reason = reason
        super().__init__(f"{detail} [scope:{reason}]")


def _oid(value: Any, label: str) -> str:
    if not isinstance(value, str) or _OID.fullmatch(value) is None:
        raise ScopeRejected("malformed", f"{label} is not an exact Git object ID")
    return value


def _positive(value: Any, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ScopeRejected("malformed", f"{label} must be a positive integer")
    return value


def _sha(value: Any, label: str) -> str:
    return value.get("sha") if isinstance(value, dict) else None


# T1 -------------------------------------------------------------------------

def require_same_repository_run(run: Mapping[str, Any], repository: str = REPOSITORY) -> None:
    """The run and its head belong to the canonical repository and are not forks."""
    if repository != REPOSITORY:
        raise ScopeRejected("repository", "Reuse scope requires the canonical repository")
    for field in ("repository", "head_repository"):
        value = run.get(field)
        if not isinstance(value, dict) or value.get("full_name") != repository:
            raise ScopeRejected("repository", f"Run {field} is not the canonical repository")
        if value.get("fork") is not False:
            raise ScopeRejected("fork", f"Run {field} is a fork or lacks fork state")


def _require_same_repository_pull(pull: Mapping[str, Any], number: int, repository: str, label: str) -> None:
    if not isinstance(pull, dict) or pull.get("number") != number:
        raise ScopeRejected("association-disagrees", f"{label} names another pull request")
    head, base = pull.get("head"), pull.get("base")
    head_repo = head.get("repo") if isinstance(head, dict) else None
    base_repo = base.get("repo") if isinstance(base, dict) else None
    if not isinstance(head_repo, dict) or not isinstance(base_repo, dict):
        raise ScopeRejected("malformed", f"{label} lacks its head/base repositories")
    if head_repo.get("fork") is not False:
        raise ScopeRejected("fork", f"{label} head is a fork")
    if head_repo.get("full_name") != repository or base_repo.get("full_name") != repository:
        raise ScopeRejected("repository", f"{label} is not a same-repository pull request")
    if base.get("ref") != MAIN:
        raise ScopeRejected("base-not-main", f"{label} does not target {MAIN}")
    _oid(head.get("sha"), f"{label} head")


# Association -----------------------------------------------------------------

def unassociated_pull_request_run(run: Mapping[str, Any]) -> bool:
    """A pull_request run whose live association GitHub dropped (merged/closed PR).

    Only callers that then bind the run durably through ``_validate_tested_commit``
    with an association fetcher may treat this as a candidate for scope N.
    """
    return run.get("event") == "pull_request" and run.get("pull_requests") == []


def _live_binding(run, commit, *, expected_commit, pull_request):
    requests = run.get("pull_requests")
    if not isinstance(requests, list):
        raise ValueError("Original CI pull requests must be an array")
    requests = [value for value in requests
                if isinstance(value, dict) and value.get("number") == pull_request]
    if len(requests) != 1:
        raise ScopeRejected("association-ambiguous", "Original CI attempt has ambiguous pull-request identity")
    identities = []
    for field in ("base", "head"):
        oid = _sha(requests[0].get(field), field)
        if not isinstance(oid, str) or _OID.fullmatch(oid) is None:
            raise ScopeRejected("malformed", "Original CI attempt lacks exact pull-request base/head")
        identities.append(oid)
    parents = commit.get("parents")
    if not isinstance(parents, list):
        raise ValueError("Tested merge parents must be an array")
    trigger_head = run.get("head_sha")
    if not isinstance(trigger_head, str) or _OID.fullmatch(trigger_head) is None:
        raise ScopeRejected("malformed", "Original CI attempt lacks exact triggering head")
    # GitHub updates a historical run's pull_requests[].head.sha when the
    # PR moves; run.head_sha retains the head that triggered this attempt.
    original_head = trigger_head if trigger_head != expected_commit else identities[1]
    if [_sha(value, "parent") for value in parents] != [identities[0], original_head]:
        raise ScopeRejected("association-disagrees",
                            "Tested merge does not bind the original CI pull-request base/head")
    return {"number": pull_request, "base": identities[0], "head": original_head,
            "source": "pull_requests", "merged": None, "mergeCommit": None}


def durable_association_reads(run: Mapping[str, Any], commit: Mapping[str, Any], *, pull_request: int,
                              fetch: Callable[[str], Any]) -> dict[str, Any]:
    """Fetch the immutable durable association evidence for one pull_request run.

    ``fetch`` resolves a repository-relative API path (``commits/...``) to JSON.
    Only exact object IDs are interpolated into paths; validation is separate.
    """
    number = _positive(pull_request, "Association pull request")
    head = _oid(run.get("head_sha"), "Run head")
    parents = commit.get("parents")
    if not isinstance(parents, list) or len(parents) != 2:
        raise ScopeRejected("association-disagrees", "Tested commit is not a two-parent PR merge")
    base = _oid(_sha(parents[0], "parent"), "Tested merge base")
    commit_pulls = fetch(f"commits/{head}/pulls")
    pull = fetch(f"pulls/{number}")
    if not isinstance(pull, dict):
        raise ScopeRejected("malformed", "Pull request response is not an object")
    pull_head = _oid(_sha(pull.get("head"), "head"), "Pull request head")
    reads = {"commitPulls": commit_pulls, "pull": pull,
             "headAncestry": fetch(f"compare/{head}...{pull_head}?per_page=1"),
             "baseAncestry": fetch(f"compare/{base}...{MAIN}?per_page=1"),
             "mergeAncestry": None}
    if pull.get("merged") is True:
        merge = _oid(pull.get("merge_commit_sha"), "Pull request merge commit")
        reads["mergeAncestry"] = fetch(f"compare/{pull_head}...{merge}?per_page=1")
    return reads


def _require_ancestor(compare: Any, ancestor: str, label: str, *, reason: str = "ancestry") -> None:
    if (not isinstance(compare, dict)
            or _sha(compare.get("base_commit"), "base") != ancestor
            or _sha(compare.get("merge_base_commit"), "merge base") != ancestor
            or compare.get("behind_by") != 0
            or compare.get("status") not in {"ahead", "identical"}):
        raise ScopeRejected(reason, f"{label} is not proved by Git ancestry")


def durable_binding(run: Mapping[str, Any], commit: Mapping[str, Any], *, expected_commit: str,
                    pull_request: int, reads: Mapping[str, Any],
                    repository: str = REPOSITORY) -> dict[str, Any]:
    """Validate durable PR association (T4a scope evidence) for an unassociated run."""
    number = _positive(pull_request, "Association pull request")
    require_same_repository_run(run, repository)
    if not unassociated_pull_request_run(run):
        raise ScopeRejected("association-disagrees",
                            "Durable association applies only when the live association is empty")
    if not isinstance(reads, dict) or set(reads) != {
            "commitPulls", "pull", "headAncestry", "baseAncestry", "mergeAncestry"}:
        raise ScopeRejected("malformed", "Durable association evidence is incomplete")
    head = _oid(run.get("head_sha"), "Run head")
    if head == expected_commit:
        raise ScopeRejected("association-disagrees", "Run head cannot be its own tested merge")
    parents = commit.get("parents")
    if not isinstance(parents, list) or len(parents) != 2 or _sha(parents[1], "parent") != head:
        raise ScopeRejected("association-disagrees", "Tested merge does not bind the triggering head")
    base = _oid(_sha(parents[0], "parent"), "Tested merge base")
    listed = reads["commitPulls"]
    if not isinstance(listed, list):
        raise ScopeRejected("malformed", "Commit pull-request association is not an array")
    if not listed:
        raise ScopeRejected("association-missing", "Run head has no durable pull-request association")
    if len(listed) != 1:
        raise ScopeRejected("association-ambiguous", "Run head is associated with more than one pull request")
    if not isinstance(listed[0], dict) or listed[0].get("number") != number:
        raise ScopeRejected("association-disagrees", "Run head belongs to another pull request")
    _require_same_repository_pull(listed[0], number, repository, "Commit association")
    pull = reads["pull"]
    _require_same_repository_pull(pull, number, repository, "Pull request")
    pull_head = pull["head"]["sha"]
    if listed[0]["head"]["sha"] != pull_head:
        raise ScopeRejected("association-disagrees", "Commit association and pull request disagree on head")
    _require_ancestor(reads["headAncestry"], head, "Run head within its pull request")
    merged = pull.get("merged")
    merge_commit = None
    if merged is True:
        if pull.get("state") != "closed":
            raise ScopeRejected("malformed", "Merged pull request is not closed")
        merge_commit = _oid(pull.get("merge_commit_sha"), "Pull request merge commit")
        _require_ancestor(reads["mergeAncestry"], pull_head, "Pull request head within its merge")
    elif merged is False and pull.get("state") == "open":
        if reads["mergeAncestry"] is not None:
            raise ScopeRejected("malformed", "Open pull request carries merge evidence")
    else:
        raise ScopeRejected("not-merged", "Closed pull request was not merged")
    _require_ancestor(reads["baseAncestry"], base, f"Tested base on {MAIN}", reason="base-not-main")
    return {"number": number, "base": base, "head": head, "source": "durable",
            "merged": merged, "mergeCommit": merge_commit}


def pull_request_binding(run: Mapping[str, Any], commit: Mapping[str, Any], *, expected_commit: str,
                         pull_request: int, fetch: Callable[[str], Any] | None = None,
                         reads: Mapping[str, Any] | None = None,
                         repository: str = REPOSITORY) -> dict[str, Any]:
    """Bind a pull_request run to PR N through its live or, if dropped, durable association.

    A non-empty live association is authoritative and must name N exactly once;
    it never falls back to durable evidence (a disagreement rejects).
    """
    requests = run.get("pull_requests")
    if requests != []:
        return _live_binding(run, commit, expected_commit=expected_commit, pull_request=pull_request)
    if reads is None:
        if fetch is None:
            raise ScopeRejected("association-ambiguous",
                                "Original CI attempt has ambiguous pull-request identity")
        reads = durable_association_reads(run, commit, pull_request=pull_request, fetch=fetch)
    return durable_binding(run, commit, expected_commit=expected_commit, pull_request=pull_request,
                           reads=reads, repository=repository)


def signed_binding(run: Mapping[str, Any], commit: Mapping[str, Any], *, expected_commit: str,
                   pull_request: int) -> dict[str, Any]:
    """Binding for observations inside a signed proof (no fresh API authority).

    A live association is checked as before. An empty one is admitted only
    because the signer ran ``pull_request_binding`` with durable evidence; the
    tested merge must still bind the triggering head as its second parent.
    """
    if run.get("pull_requests") != []:
        return _live_binding(run, commit, expected_commit=expected_commit, pull_request=pull_request)
    _positive(pull_request, "Association pull request")
    head = _oid(run.get("head_sha"), "Run head")
    parents = commit.get("parents")
    if (head == expected_commit or not isinstance(parents, list) or len(parents) != 2
            or _sha(parents[1], "parent") != head):
        raise ScopeRejected("association-disagrees", "Tested merge does not bind the triggering head")
    base = _oid(_sha(parents[0], "parent"), "Tested merge base")
    return {"number": pull_request, "base": base, "head": head, "source": "signed",
            "merged": None, "mergeCommit": None}


def merge_group_scope(run: Mapping[str, Any]) -> int:
    """PR N of a merge_group producer from ``gh-readonly-queue/main/pr-N-<sha>``."""
    if run.get("event") != "merge_group":
        raise ScopeRejected("event", "Merge-group scope requires a merge_group run")
    branch = run.get("head_branch")
    match = _QUEUE_BRANCH.fullmatch(branch) if isinstance(branch, str) else None
    if match is None:
        raise ScopeRejected("merge-group-ref", "Merge-group head branch does not identify one pull request")
    _oid(run.get("head_sha"), "Merge-group head")
    return int(match.group(1))


# Consumer scope ----------------------------------------------------------------

def consumer_scope(environ: Mapping[str, str]) -> dict[str, Any]:
    """The executing run's scope from the runner environment (not from transported data)."""
    if environ.get("GITHUB_REPOSITORY") != REPOSITORY:
        raise ScopeRejected("repository", "Consumer is not the canonical repository")
    event, ref = environ.get("GITHUB_EVENT_NAME"), environ.get("GITHUB_REF")
    if not isinstance(ref, str):
        raise ScopeRejected("consumer", "Consumer lacks its runner ref")
    if event == "pull_request":
        match = _PULL_REF.fullmatch(ref)
    elif event == "merge_group":
        match = _QUEUE_BRANCH.fullmatch(ref.removeprefix("refs/heads/")) if ref.startswith("refs/heads/") else None
    else:
        raise ScopeRejected("event", "Consumer event cannot carry reuse scope")
    if match is None:
        raise ScopeRejected("merge-group-ref" if event == "merge_group" else "consumer",
                            "Consumer ref does not identify one pull request")
    return {"repository": REPOSITORY, "event": event, "pullRequest": int(match.group(1))}


def require_consumer_environment(environ: Mapping[str, str], plan: Mapping[str, Any]) -> dict[str, Any]:
    """The executing attempt is the planned PR merge ref or planned merge-group ref."""
    scope = consumer_scope(environ)
    if (plan.get("repository") != REPOSITORY or plan.get("event") != scope["event"]
            or plan.get("pullRequest") != scope["pullRequest"]):
        raise ScopeRejected("consumer", "Consumer environment differs from its plan scope")
    if environ.get("GITHUB_SHA") != plan.get("validationCommit"):
        raise ScopeRejected("consumer", "Consumer commit differs from its plan")
    return scope


def current_pull_request(environ: Mapping[str, str]) -> int | None:
    """The executing run's PR scope, or None when the environment carries none."""
    try:
        return consumer_scope(environ)["pullRequest"]
    except ScopeRejected:
        return None


def require_ci_consumer(consumer: Mapping[str, Any]) -> dict[str, Any]:
    """Completed-carrier consumer rule: same-repository CI, PR or merge queue.

    The PR number is not consulted: carriers are owner-pinned (T4c) and the
    consumer's code is bound to the approved verifier bytes separately.
    """
    if not isinstance(consumer, dict) or consumer.get("kind") != "ci":
        raise ScopeRejected("consumer", "Completed frozen carrier requires a same-repository CI consumer")
    producer = consumer.get("producer")
    if not isinstance(producer, dict) or producer.get("repository") != REPOSITORY:
        raise ScopeRejected("repository", "Completed frozen carrier requires a same-repository CI consumer")
    event, number = producer.get("event"), producer.get("pullRequest")
    if event == "pull_request" and type(number) is int and number > 0:
        return {"repository": REPOSITORY, "event": event, "pullRequest": number}
    if event == "merge_group" and number is None:
        return {"repository": REPOSITORY, "event": event, "pullRequest": None}
    raise ScopeRejected("event", "Completed frozen carrier requires a same-repository CI consumer")


# T4(b) landed ------------------------------------------------------------------

def landed(binding: Mapping[str, Any], *, consumer_base: str, merge_to_consumer: Any,
           producer_trees: Mapping[str, str], approved_trees: Iterable[Mapping[str, str]],
           main_trees: Iterable[Mapping[str, str]]) -> bool:
    """T4(b): PR M merged into main below the consumer, with an approved control tree.

    ``producer_trees`` holds the ``ci`` and ``.github`` tree IDs at the producer
    commit; it must equal an approved verifier's or a main first-parent commit's.
    """
    if binding.get("merged") is not True:
        raise ScopeRejected("not-merged", "Landed admission requires a merged pull request")
    merge = _oid(binding.get("mergeCommit"), "Landed merge commit")
    _oid(consumer_base, "Consumer base")
    _require_ancestor(merge_to_consumer, merge, "Landed merge below the consumer base", reason="base-not-main")
    if (not isinstance(producer_trees, dict) or set(producer_trees) != {"ci", ".github"}):
        raise ScopeRejected("malformed", "Producer control trees are incomplete")
    trees = {field: _oid(producer_trees[field], f"Producer {field} tree") for field in ("ci", ".github")}
    allowed = [dict(row) for row in (*approved_trees, *main_trees)]
    if trees not in allowed:
        raise ScopeRejected("producer-tree-unapproved",
                            "Producer control tree is neither an approved verifier nor on main")
    return True


# Composite admission (T1-T6) -----------------------------------------------------

def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ScopeRejected("malformed", f"{label} timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ScopeRejected("malformed", f"{label} timestamp is malformed") from error
    if parsed.utcoffset() != timedelta(0):
        raise ScopeRejected("malformed", f"{label} timestamp is not UTC")
    return parsed


def _successful_job(jobs: Any, name: str, run: Mapping[str, Any], reason: str) -> Mapping[str, Any]:
    if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
        raise ScopeRejected("malformed", "Producer jobs are malformed")
    selected = [job for job in jobs if job.get("name") == name]
    if len(selected) != 1:
        raise ScopeRejected(reason, f"Producer job {name} is missing or ambiguous")
    job = selected[0]
    if (job.get("run_id") != run.get("id") or job.get("head_sha") != run.get("head_sha")
            or job.get("status") != "completed" or job.get("conclusion") != "success"):
        raise ScopeRejected(reason, f"Producer job {name} did not succeed for its exact run")
    return job


def admit(producer: Mapping[str, Any], observation: Mapping[str, Any],
          consumer: Mapping[str, Any], pins: Iterable[tuple[int, int, int, str]] = (),
          *, workflow_path: str = CI_WORKFLOW) -> dict[str, Any]:
    """Admit producer P to consumer C iff T1-T6 hold; otherwise raise ``ScopeRejected``.

    ``observation`` carries freshly observed ``run``, ``jobs``, ``artifact``,
    the caller-pinned ``jobName``, an optional ``binding`` (from
    ``pull_request_binding``) and an optional ``landed`` verdict (``landed()``).
    ``consumer`` is ``consumer_scope()`` output. ``pins`` are RA-controlled
    ``(runId, runAttempt, artifactId, artifactSha256)`` originals.
    """
    if not isinstance(producer, dict) or not isinstance(observation, dict) or not isinstance(consumer, dict):
        raise ScopeRejected("malformed", "Admission inputs are malformed")
    run, jobs, artifact = (observation.get(field) for field in ("run", "jobs", "artifact"))
    if not isinstance(run, dict) or not isinstance(artifact, dict):
        raise ScopeRejected("malformed", "Admission observation is incomplete")
    # T1
    if producer.get("repository") != REPOSITORY or consumer.get("repository") != REPOSITORY:
        raise ScopeRejected("repository", "Producer or consumer is not the canonical repository")
    require_same_repository_run(run)
    # T3
    event = producer.get("event")
    if event not in PRODUCER_EVENTS or run.get("event") != event:
        raise ScopeRejected("event", "Producer event is not an eligible original event")
    if consumer.get("event") not in CONSUMER_EVENTS:
        raise ScopeRejected("event", "Consumer event cannot carry reuse scope")
    # T2
    if producer.get("workflowPath") != workflow_path or run.get("path") != workflow_path:
        raise ScopeRejected("workflow", "Producer workflow is not the fixed producer workflow")
    run_id = _positive(producer.get("runId"), "Producer run")
    attempt = _positive(producer.get("runAttempt"), "Producer attempt")
    if run.get("id") != run_id:
        raise ScopeRejected("run-identity", "Observed run differs from its producer")
    if run.get("run_attempt") != attempt:
        raise ScopeRejected("attempt", "Observed run attempt differs from its producer")
    if event == "merge_group" and run.get("head_sha") != producer.get("commit"):
        raise ScopeRejected("run-identity", "Merge-group run differs from its tested commit")
    job_name = observation.get("jobName")
    if type(job_name) is not str or not job_name:
        raise ScopeRejected("malformed", "Producer job must be caller-pinned text")
    job = _successful_job(jobs, job_name, run, "job")
    if event == "workflow_dispatch":
        _successful_job(jobs, DISPATCH_AUTHORIZATION_JOB, run, "dispatch-unauthorized")
    artifact_id = _positive(artifact.get("id"), "Producer artifact")
    digest = artifact.get("digest")
    if not isinstance(digest, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
        raise ScopeRejected("malformed", "Producer artifact digest is malformed")
    transport = artifact.get("workflow_run")
    if not isinstance(transport, dict) or transport.get("id") != run_id:
        raise ScopeRejected("artifact-identity", "Producer artifact belongs to another run")
    if artifact.get("expired") is not False:
        raise ScopeRejected("artifact-expired", "Producer artifact is expired or lacks expiry state")
    started, created, completed = (_timestamp(value, label) for value, label in (
        (job.get("started_at"), "Job start"), (artifact.get("created_at"), "Artifact"),
        (job.get("completed_at"), "Job completion")))
    if not started <= created <= completed:
        raise ScopeRejected("artifact-window", "Producer artifact is outside its job-attempt window")
    # T4(c) pinned
    if (run_id, attempt, artifact_id, digest) in {tuple(pin) for pin in pins}:
        return {"admitted": True, "rule": "pinned", "scope": None}
    # T4(a)/(b) scope
    if event == "pull_request":
        binding = observation.get("binding")
        if (not isinstance(binding, dict) or binding.get("number") != producer.get("pullRequest")
                or binding.get("head") != run.get("head_sha")):
            raise ScopeRejected("association-missing", "Producer lacks its verified pull-request binding")
        scope = binding["number"]
    elif event == "merge_group":
        scope = merge_group_scope(run)
    else:
        scope = None
    if scope is not None and scope == consumer.get("pullRequest"):
        return {"admitted": True, "rule": "same-scope", "scope": scope}
    if event in CONSUMER_EVENTS and observation.get("landed") is True:
        return {"admitted": True, "rule": "landed", "scope": scope}
    raise ScopeRejected("foreign-scope", "Producer scope is neither the consumer's, landed, nor pinned")
