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

A live association (open PR) is checked as strictly as a durable one, except
for the owner-pinned PR 31 (merged, so no production run of it still carries
a live association). ``admit()`` is called by discovered SDK parity reuse
(``sdk_parity_reuse``). ``landed()`` (T4b) has no production caller yet: no
path proposes cross-PR candidates, so cross-PR reuse is simply not offered.

The merge-group retained-validation section at the end (S1050, Option A')
is the one exception to "pure": ``discover_retained_pr_validation`` issues
fixed read-only GETs through ``GitHubReads`` (or an injected reader) and
``verify_retained_bundle`` re-checks the staged bytes offline.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Mapping

REPOSITORY = "codex-agent-labs/codex-agent"
MAIN = "main"
PINNED_PULL_REQUEST = 31
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
    "consumer", "branch", "control-tree", "merge-tree",
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


def association_reads_required(run: Mapping[str, Any], pull_request: Any) -> bool:
    """Whether binding this pull_request run needs fresh association reads.

    Always for a dropped (durable) association, and for every live association
    except the owner-pinned PR 31, whose runs are all unassociated now.
    """
    return run.get("event") == "pull_request" and (
        run.get("pull_requests") == [] or pull_request != PINNED_PULL_REQUEST)


def association_reads(run: Mapping[str, Any], commit: Mapping[str, Any], *, pull_request: int,
                      fetch: Callable[[str], Any]) -> dict[str, Any]:
    """Fetch the association evidence for a live or dropped association."""
    if run.get("pull_requests") == []:
        return durable_association_reads(run, commit, pull_request=pull_request, fetch=fetch)
    number = _positive(pull_request, "Association pull request")
    head = _oid(run.get("head_sha"), "Run head")
    parents = commit.get("parents")
    if not isinstance(parents, list) or len(parents) != 2:
        raise ScopeRejected("association-disagrees", "Tested commit is not a two-parent PR merge")
    base = _oid(_sha(parents[0], "parent"), "Tested merge base")
    if head == commit.get("sha"):
        # Same head choice as _live_binding: read ancestry for the head it binds.
        entries = [value for value in run.get("pull_requests") or ()
                   if isinstance(value, dict) and value.get("number") == number]
        head = _oid(_sha(entries[0].get("head"), "head") if len(entries) == 1 else None, "Live pull-request head")
    pull = fetch(f"pulls/{number}")
    if not isinstance(pull, dict):
        raise ScopeRejected("malformed", "Pull request response is not an object")
    pull_head = _oid(_sha(pull.get("head"), "head"), "Pull request head")
    return {"pull": pull, "headAncestry": fetch(f"compare/{head}...{pull_head}?per_page=1"),
            "baseAncestry": fetch(f"compare/{base}...{MAIN}?per_page=1")}


def _require_run_branch(run: Mapping[str, Any], pull: Mapping[str, Any], label: str) -> None:
    """I3: the run executed on the PR's own head branch and head repository."""
    head = pull.get("head")
    ref = head.get("ref") if isinstance(head, dict) else None
    if not isinstance(ref, str) or not ref or run.get("head_branch") != ref:
        raise ScopeRejected("branch", f"Run head branch is not the {label} head branch")
    head_repo = run.get("head_repository")
    if (not isinstance(head_repo, dict) or not isinstance(head.get("repo"), dict)
            or head_repo.get("full_name") != head["repo"].get("full_name")):
        raise ScopeRejected("repository", f"Run head repository is not the {label} head repository")


def _live_binding(run, commit, *, expected_commit, pull_request, reads=None, signed=False,
                  repository=REPOSITORY):
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
    binding = {"number": pull_request, "base": identities[0], "head": original_head,
               "source": "pull_requests", "merged": None, "mergeCommit": None}
    if signed or not association_reads_required(run, pull_request):
        # Signed: the signer bound it with fresh reads. PR 31: owner-pinned scope.
        return binding
    # I2: a live association gets the same branch, base and ancestry proof as
    # a durable one, so a force-pushed-away head or a retargeted base rejects.
    if not isinstance(reads, dict) or set(reads) != {"pull", "headAncestry", "baseAncestry"}:
        raise ScopeRejected("association-missing",
                            "Live pull-request association lacks its fresh association evidence")
    require_same_repository_run(run, repository)
    live_base = requests[0].get("base")
    if not isinstance(live_base, dict) or live_base.get("ref") != MAIN:
        raise ScopeRejected("base-not-main", f"Live pull-request association does not target {MAIN}")
    pull = reads["pull"]
    _require_same_repository_pull(pull, pull_request, repository, "Pull request")
    if pull.get("state") != "open" or pull.get("merged") is not False:
        raise ScopeRejected("association-disagrees", "Live pull-request association names a closed pull request")
    _require_run_branch(run, pull, "pull request")
    live_head = requests[0].get("head")
    if not isinstance(live_head, dict) or live_head.get("ref") != pull["head"]["ref"]:
        raise ScopeRejected("branch", "Live pull-request association names another head branch")
    _require_ancestor(reads["headAncestry"], original_head, "Run head within its pull request")
    _require_ancestor(reads["baseAncestry"], identities[0], f"Tested base on {MAIN}", reason="base-not-main")
    return binding


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
    # I3: commits/{sha}/pulls names the PR that *landed* a commit, not the one
    # whose run tested it; the run must have executed on that PR's own branch.
    _require_run_branch(run, pull, "pull request")
    if listed[0]["head"].get("ref") != pull["head"]["ref"]:
        raise ScopeRejected("branch", "Commit association and pull request disagree on head branch")
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
    it never falls back to durable evidence (a disagreement rejects). Both
    paths require the run's branch to be the PR head branch, the run head to
    lie within the PR head, a ``main`` base and a tested base on ``main``.
    """
    requests = run.get("pull_requests")
    if requests != []:
        if reads is None and fetch is not None and association_reads_required(run, pull_request):
            reads = association_reads(run, commit, pull_request=pull_request, fetch=fetch)
        return _live_binding(run, commit, expected_commit=expected_commit, pull_request=pull_request,
                             reads=reads, repository=repository)
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

    A live association's merge parents are rechecked. Branch, base and
    ancestry evidence (live or durable) is not re-read: it is admitted only
    because the signer ran ``pull_request_binding`` with fresh reads in
    ``product_reuse._observe_ci_producer_jobs`` before signing (N5). The
    tested merge must still bind the triggering head as its second parent.
    """
    if run.get("pull_requests") != []:
        return _live_binding(run, commit, expected_commit=expected_commit, pull_request=pull_request,
                             signed=True)
    _positive(pull_request, "Association pull request")
    head = _oid(run.get("head_sha"), "Run head")
    parents = commit.get("parents")
    if (head == expected_commit or not isinstance(parents, list) or len(parents) != 2
            or _sha(parents[1], "parent") != head):
        raise ScopeRejected("association-disagrees", "Tested merge does not bind the triggering head")
    base = _oid(_sha(parents[0], "parent"), "Tested merge base")
    return {"number": pull_request, "base": base, "head": head, "source": "signed",
            "merged": None, "mergeCommit": None}


def queue_pull_request(ref: Any) -> int:
    """PR N from ``gh-readonly-queue/main/pr-N-<sha>`` (optionally ``refs/heads/``-prefixed)."""
    branch = ref.removeprefix("refs/heads/") if isinstance(ref, str) else None
    match = _QUEUE_BRANCH.fullmatch(branch) if branch is not None else None
    if match is None:
        raise ScopeRejected("merge-group-ref", "Merge-group ref does not identify one pull request")
    return int(match.group(1))


def merge_group_scope(run: Mapping[str, Any]) -> int:
    """PR N of a merge_group producer from ``gh-readonly-queue/main/pr-N-<sha>``."""
    if run.get("event") != "merge_group":
        raise ScopeRejected("event", "Merge-group scope requires a merge_group run")
    branch = run.get("head_branch")
    if not isinstance(branch, str) or branch.startswith("refs/"):
        raise ScopeRejected("merge-group-ref", "Merge-group head branch does not identify one pull request")
    number = queue_pull_request(branch)
    _oid(run.get("head_sha"), "Merge-group head")
    return number


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
        if match is None:
            raise ScopeRejected("consumer", "Consumer ref does not identify one pull request")
        number = int(match.group(1))
    elif event == "merge_group":
        if not ref.startswith("refs/heads/"):
            raise ScopeRejected("merge-group-ref", "Consumer ref does not identify one pull request")
        number = queue_pull_request(ref)
        head_ref = environ.get("GITHUB_HEAD_REF")
        if head_ref not in (None, "") and queue_pull_request(head_ref) != number:
            raise ScopeRejected("merge-group-ref", "Consumer head ref names another merge-queue pull request")
    else:
        raise ScopeRejected("event", "Consumer event cannot carry reuse scope")
    return {"repository": REPOSITORY, "event": event, "pullRequest": number}


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


def require_ci_consumer(consumer: Mapping[str, Any], environ: Mapping[str, str]) -> dict[str, Any]:
    """Completed-carrier consumer rule: same-repository CI, PR or merge queue.

    The PR number is not compared to a scope: carriers are owner-pinned (T4c)
    and the consumer's code is bound to the approved verifier bytes separately.
    A merge_group consumer must execute on ``refs/heads/gh-readonly-queue/
    main/pr-N-<sha>`` (N4); N is parsed from that ref and returned.
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
        scope = consumer_scope(environ)
        if scope["event"] != "merge_group":
            raise ScopeRejected("consumer", "Merge-group carrier consumer is not executing in a merge queue")
        return {"repository": REPOSITORY, "event": event, "pullRequest": scope["pullRequest"]}
    raise ScopeRejected("event", "Completed frozen carrier requires a same-repository CI consumer")


# T4(b) landed ------------------------------------------------------------------

def landed(binding: Mapping[str, Any], *, consumer_base: str, merge_to_consumer: Any,
           producer_trees: Mapping[str, str], approved_trees: Iterable[Mapping[str, str]],
           main_trees: Iterable[Mapping[str, str]]) -> bool:
    """T4(b): PR M merged into main below the consumer, with an approved control tree.

    NOT WIRED: no production caller exists yet (9.5.0). Nothing proposes
    cross-PR candidates, so cross-PR reuse is not offered (fail closed).

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


# Control trees (B1) ---------------------------------------------------------------

CONTROL_TREES = ("ci", ".github")


def require_equal_control_trees(producer: Mapping[str, Any], consumer: Mapping[str, Any]) -> None:
    """The producer's ``ci`` and ``.github`` tree IDs equal the consumer's exactly.

    A PR-controlled producer ``ci.yml`` could otherwise define its own job graph
    (for example a plain job carrying a pinned display name). Exact equality
    only: no landed, approved or main alternative.
    """
    rows = []
    for label, trees in (("Producer", producer), ("Consumer", consumer)):
        if not isinstance(trees, dict) or set(trees) != set(CONTROL_TREES):
            raise ScopeRejected("control-tree", f"{label} control trees are incomplete")
        rows.append({field: _oid(trees[field], f"{label} {field} tree") for field in CONTROL_TREES})
    if rows[0] != rows[1]:
        differs = sorted(field for field in CONTROL_TREES if rows[0][field] != rows[1][field])
        raise ScopeRejected("control-tree", f"Producer control trees differ from the consumer's: {differs}")


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


# Merge-group reuse of a retained PR validation (S1050, Option A′) ----------------
#
# A green retained-path PR run publishes no schema-1 ``codex-agent-ci-validation``
# aggregate (its lanes are proven by originals of other runs), so the merge
# queue would otherwise rebuild everything. An identical-tree merge group may
# instead reuse the final green PR attempt's own retained contributions. That
# never relabels them as schema-1 lane provenance: the merge gate publishes a
# distinct ``codex-agent-merge-group-retained-validation-<tree>`` artifact.
# Every check below is exact; any doubt returns ``reused=false`` (full path).

RETAINED_KIND = "retained"
RETAINED_SOURCE_KIND = "merge-group-retained-validation-source"
RETAINED_GATE_JOB = "product-validation / CI / merge-gate"
RETAINED_OUTER_GATE_JOB = "CI / merge-gate"
PRODUCT_VALIDATION_REFERENCE = f"{REPOSITORY}/.github/workflows/product-validation.yml@reuse-authority"
REUSE_AUTHORITY_REF = "refs/heads/reuse-authority"
GITHUB_API = "https://api.github.com"
RETAINED_PLAN_KEYS = frozenset({
    "schemaVersion", "event", "repository", "pullRequest", "baseCommit", "headCommit",
    "validationCommit", "validationTree", "mergeReady", "remoteBuildAuthorized",
    "remoteBuildAuthorizationReason", "androidEvidenceRequired", "fullRequested", "full",
    "unknownPaths", "changedPaths", "lanes",
})
_CONTRIBUTION_REQUIRED_KEYS = frozenset({"schemaVersion", "kind", "result", "consumer", "planSha256", "laneReceipts"})
_CONTRIBUTION_OPTIONAL_KEYS = frozenset({
    "canonical", "sdkParity", "installedConsumers", "nativeSourceTests", "swiftSourceTests", "reviewedRuntime"})
_CONTRIBUTIONS_FILE = "current-validation-contributions.json"
_PLAN_FILE = "impact-plan.json"
_SOURCE_PLAN_FILE = "source-impact-plan.json"
_SOURCE_FILE = "source.json"
_BUNDLE_FILES = frozenset({_SOURCE_PLAN_FILE, _CONTRIBUTIONS_FILE, _SOURCE_FILE})
_ARTIFACT_LIMITS = {"contributions": 64 << 20, "plan": 16 << 20}
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_DECIMAL = re.compile(r"[1-9][0-9]{0,19}")
_OUTPUT_VALUE = re.compile(r"[A-Za-z0-9._-]{1,200}")
_OUTPUT_KEYS = frozenset({"reused", "kind", "source_run_id", "source_run_attempt", "artifact_name"})

RETAINED_REASONS = frozenset({
    "not-merge-group", "consumer", "plan", "pull-request", "no-candidate", "run", "fork", "attempt",
    "workflow", "association", "jobs", "artifact-missing", "artifact-expired", "artifact-identity",
    "artifact-digest", "artifact-window", "artifact-content", "tree", "plan-hash", "contributions",
    "bundle", "error",
})


class RetainedReuseRejected(ValueError):
    """A structured, fail-closed refusal of merge-group retained validation reuse."""

    def __init__(self, reason: str, detail: str):
        if reason not in RETAINED_REASONS:
            raise ValueError(f"Unknown retained reuse rejection reason: {reason}")
        self.reason = reason
        super().__init__(detail)


def route_line(reason: str, detail: str) -> str:
    """One log line that can carry no workflow command or extra line."""
    reason = reason if reason in RETAINED_REASONS or reason == "applied" else "error"
    text = "".join(character if " " <= character <= "~" else "?" for character in str(detail))[:300]
    return f"[route:merge-queue-reuse:{reason}] {text}"


def write_step_outputs(path: Any, values: Mapping[str, Any]) -> None:
    """Append fixed-name, fixed-alphabet outputs only (no GITHUB_OUTPUT injection)."""
    lines = []
    for key, value in values.items():
        value = str(value).lower() if isinstance(value, bool) else str(value)
        if key not in _OUTPUT_KEYS or _OUTPUT_VALUE.fullmatch(value) is None:
            raise ValueError("Retained reuse step output is outside its fixed alphabet")
        lines.append(f"{key}={value}\n")
    with open(path, "a", encoding="utf-8") as output:
        output.write("".join(lines))


def retained_contributions_name(tree: str, attempt: int) -> str:
    return f"codex-agent-current-validation-contributions-{_oid(tree, 'Validation tree')}-attempt-{_positive(attempt, 'Run attempt')}"


def _digest(raw: bytes) -> str:
    import hashlib
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _strict_json(raw: Any, label: str, reason: str = "artifact-content") -> dict[str, Any]:
    import json

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RetainedReuseRejected(reason, f"{label} repeats key {key!r}")
            result[key] = value
        return result

    def constant(value):
        raise RetainedReuseRejected(reason, f"{label} carries non-finite number {value}")

    if type(raw) is not bytes:
        raise RetainedReuseRejected(reason, f"{label} is not exact bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeDecodeError, ValueError) as error:
        if isinstance(error, RetainedReuseRejected):
            raise
        raise RetainedReuseRejected(reason, f"{label} is not strict JSON") from error
    if not isinstance(value, dict):
        raise RetainedReuseRejected(reason, f"{label} is not a JSON object")
    return value


def _require_int(value: Any, label: str, reason: str) -> int:
    if type(value) is not int or value < 1:
        raise RetainedReuseRejected(reason, f"{label} must be a positive integer")
    return value


def require_retained_plan_pair(current: Mapping[str, Any], source: Mapping[str, Any], *,
                               repository_root: Any) -> None:
    """The merge-group plan and its PR source plan name one identical, covered tree."""
    from pathlib import Path
    from impact import validate_legacy_lane_projection, validate_remote_build_authorization
    repository_root = Path(repository_root)
    for label, plan in (("Current", current), ("Source", source)):
        if not isinstance(plan, dict) or set(plan) != RETAINED_PLAN_KEYS or type(plan.get("schemaVersion")) is not int \
                or plan["schemaVersion"] != 1 or plan.get("repository") != REPOSITORY:
            raise RetainedReuseRejected("plan", f"{label} impact plan schema or repository mismatch")
        for field in ("baseCommit", "headCommit", "validationCommit", "validationTree"):
            if not isinstance(plan[field], str) or _OID.fullmatch(plan[field]) is None:
                raise RetainedReuseRejected("plan", f"{label} impact plan {field} is not an exact object ID")
        try:
            authorized = validate_remote_build_authorization(dict(plan))
            validate_legacy_lane_projection(dict(plan), repository_root=repository_root)
        except (KeyError, TypeError, ValueError) as error:
            raise RetainedReuseRejected("plan", f"{label} impact plan is not authoritative: {error}") from error
        expected = ("merge_group", "merge-group") if label == "Current" else ("pull_request", "pull-request-final")
        if plan["event"] != expected[0] or plan["mergeReady"] is not True or authorized != (True, expected[1]):
            raise RetainedReuseRejected("plan", f"{label} impact plan is not an authorized {expected[0]} plan")
    number = current["pullRequest"]
    if type(number) is not int or number < 1 or source["pullRequest"] != number or type(source["pullRequest"]) is not int:
        raise RetainedReuseRejected("plan", "Source impact plan names another pull request")
    if source["validationTree"] != current["validationTree"]:
        raise RetainedReuseRejected("tree", "Source PR validation tree differs from the merge-group tree")
    if current["androidEvidenceRequired"] is True and source["androidEvidenceRequired"] is not True:
        raise RetainedReuseRejected("plan", "Source PR validation lacks required Android evidence")
    lanes, source_lanes = current["lanes"], source["lanes"]
    if not isinstance(lanes, dict) or not isinstance(source_lanes, dict) or set(lanes) != set(source_lanes):
        raise RetainedReuseRejected("plan", "Source PR validation lane set differs")
    for lane, state in lanes.items():
        if any(state.get(action) is True and source_lanes[lane].get(action) is not True
               for action in ("build", "test", "metadata")):
            raise RetainedReuseRejected("plan", f"Source PR validation does not cover merge-group work: {lane}")


def require_retained_contributions(contributions: Mapping[str, Any], *, source_plan_raw: bytes,
                                   source_plan: Mapping[str, Any], run_id: int, run_attempt: int) -> None:
    """The contributions are the passed retained gate of exactly this PR attempt and plan."""
    keys = set(contributions) if isinstance(contributions, dict) else set()
    if not _CONTRIBUTION_REQUIRED_KEYS <= keys or not keys <= _CONTRIBUTION_REQUIRED_KEYS | _CONTRIBUTION_OPTIONAL_KEYS:
        raise RetainedReuseRejected("contributions", "Retained contributions have an unexpected key set")
    if (type(contributions["schemaVersion"]) is not int or contributions["schemaVersion"] != 1
            or contributions["kind"] != "current-validation-contributions" or contributions["result"] != "passed"):
        raise RetainedReuseRejected("contributions", "Retained contributions are not a passed schema-1 gate")
    if contributions["planSha256"] != _digest(source_plan_raw):
        raise RetainedReuseRejected("plan-hash", "Retained contributions bind another impact plan")
    expected = {
        "repository": REPOSITORY, "workflowPath": CI_WORKFLOW, "event": "pull_request",
        "runId": run_id, "runAttempt": run_attempt, "pullRequest": source_plan["pullRequest"],
        "commit": source_plan["validationCommit"], "tree": source_plan["validationTree"],
    }
    consumer = contributions["consumer"]
    if (not isinstance(consumer, dict) or consumer != expected
            or any(type(consumer[field]) is not int for field in ("runId", "runAttempt", "pullRequest"))):
        raise RetainedReuseRejected("contributions", "Retained contributions name another consumer identity")
    receipts = contributions["laneReceipts"]
    if (not isinstance(receipts, dict) or any(type(lane) is not str or not isinstance(value, str)
                                              or _DIGEST.fullmatch(value) is None for lane, value in receipts.items())):
        raise RetainedReuseRejected("contributions", "Retained contributions lane receipts are malformed")


def _require_window(job: Mapping[str, Any], artifact: Mapping[str, Any]) -> None:
    try:
        started, created, completed = (_timestamp(value, label) for value, label in (
            (job.get("started_at"), "Gate start"), (artifact.get("created_at"), "Artifact"),
            (job.get("completed_at"), "Gate completion")))
    except ScopeRejected as error:
        raise RetainedReuseRejected("artifact-window", str(error)) from error
    if not started <= created <= completed:
        raise RetainedReuseRejected("artifact-window", "Retained contributions were not uploaded by the final merge gate")


def _gate_jobs(jobs: Any, run: Mapping[str, Any], attempt: int) -> dict[str, Mapping[str, Any]]:
    if not isinstance(jobs, list) or any(not isinstance(job, dict) for job in jobs):
        raise RetainedReuseRejected("jobs", "Source run jobs are malformed")
    selected = {}
    for name in (RETAINED_GATE_JOB, RETAINED_OUTER_GATE_JOB):
        matches = [job for job in jobs if job.get("name") == name]
        if len(matches) != 1:
            raise RetainedReuseRejected("jobs", f"Source gate {name} is missing or ambiguous")
        job = matches[0]
        if (type(job.get("id")) is not int or job.get("run_id") != run["id"] or job.get("run_attempt") != attempt
                or job.get("head_sha") != run["head_sha"]
                or job.get("status") != "completed" or job.get("conclusion") != "success"):
            raise RetainedReuseRejected("jobs", f"Source gate {name} did not succeed in the final attempt")
        selected[name] = job
    return selected


def _run_artifact(api: Any, run: Mapping[str, Any], name: str, limit: int) -> dict[str, Any]:
    from urllib.parse import urlencode
    items = api.items(f"actions/runs/{run['id']}/artifacts?{urlencode({'name': name})}", "artifacts")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise RetainedReuseRejected("artifact-missing", "Source run artifacts are malformed")
    matches = [item for item in items if item.get("name") == name]
    if not matches:
        raise RetainedReuseRejected("artifact-missing", f"Source run lacks {name}")
    if len(matches) != 1:
        raise RetainedReuseRejected("artifact-identity", f"Source run has ambiguous {name}")
    artifact = matches[0]
    if artifact.get("expired") is not False:
        raise RetainedReuseRejected("artifact-expired", f"{name} is expired or lacks expiry state")
    artifact_id = _require_int(artifact.get("id"), "Source artifact ID", "artifact-identity")
    transport = artifact.get("workflow_run")
    if (not isinstance(transport, dict) or transport.get("id") != run["id"]
            or transport.get("head_sha") != run["head_sha"]
            or transport.get("repository_id") is None
            or transport.get("head_repository_id") != transport.get("repository_id")):
        raise RetainedReuseRejected("artifact-identity", f"{name} belongs to another run or repository")
    if artifact.get("archive_download_url") != f"{GITHUB_API}/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip":
        raise RetainedReuseRejected("artifact-identity", f"{name} has an unexpected transport URL")
    if not isinstance(artifact.get("digest"), str) or _DIGEST.fullmatch(artifact["digest"]) is None:
        raise RetainedReuseRejected("artifact-digest", f"{name} lacks an exact digest")
    size = artifact.get("size_in_bytes")
    if type(size) is not int or not 0 < size <= limit:
        raise RetainedReuseRejected("artifact-content", f"{name} size is outside its fixed bound")
    return artifact


def _single_file(api: Any, artifact: Mapping[str, Any], filename: str, limit: int, work: Any) -> bytes:
    """Download the exact digest and extract exactly one regular root file."""
    from pathlib import Path
    from receipt import safe_extract
    work = Path(work)
    archive, extracted = work / f"{artifact['id']}.zip", work / str(artifact["id"])
    try:
        api.download(artifact, archive, limit)
    except (OSError, ValueError) as error:
        raise RetainedReuseRejected("artifact-digest", f"{artifact['name']} transport failed its digest: {error}") from error
    raw = archive.read_bytes()
    if _digest(raw) != artifact["digest"] or len(raw) != artifact["size_in_bytes"]:
        raise RetainedReuseRejected("artifact-digest", f"{artifact['name']} differs from its API digest")
    try:
        safe_extract(archive, extracted)
    except (OSError, ValueError) as error:
        raise RetainedReuseRejected("artifact-content", f"{artifact['name']} is not a safe archive") from error
    entries = list(extracted.iterdir())
    if (len(entries) != 1 or entries[0].name != filename or entries[0].is_symlink() or not entries[0].is_file()):
        raise RetainedReuseRejected("artifact-content", f"{artifact['name']} must hold exactly {filename}")
    return entries[0].read_bytes()


def _require_reference(run: Mapping[str, Any], trusted_workflow_sha: str) -> None:
    references = run.get("referenced_workflows")
    if not isinstance(references, list):
        raise RetainedReuseRejected("workflow", "Source run lacks its workflow references")
    selected = [value for value in references if isinstance(value, dict)
                and value.get("path") == PRODUCT_VALIDATION_REFERENCE]
    if (len(selected) != 1 or selected[0].get("ref") != REUSE_AUTHORITY_REF
            or selected[0].get("sha") != trusted_workflow_sha):
        raise RetainedReuseRejected("workflow", "Source run did not use the current reviewed product workflow")


def observe_retained_pr_validation(current: Mapping[str, Any], run: Any, pull: Mapping[str, Any], *, api: Any,
                                   repository_root: Any, trusted_workflow_sha: str, work: Any) -> dict[str, Any]:
    """Verify one candidate PR run online; return the exact bundle it proves."""
    if not isinstance(run, dict) or type(run.get("id")) is not int or run["id"] < 1:
        raise RetainedReuseRejected("run", "Source run is malformed")
    if (run.get("path") != CI_WORKFLOW or run.get("event") != "pull_request"
            or run.get("status") != "completed" or run.get("conclusion") != "success"):
        raise RetainedReuseRejected("run", "Source is not a completed successful ci.yml pull_request run")
    try:
        require_same_repository_run(run)
    except ScopeRejected as error:
        raise RetainedReuseRejected("fork" if error.reason == "fork" else "run", str(error)) from error
    attempt = _require_int(run.get("run_attempt"), "Source final attempt", "attempt")
    head = run.get("head_sha")
    if not isinstance(head, str) or _OID.fullmatch(head) is None or head != pull["head"]["sha"]:
        raise RetainedReuseRejected("run", "Source run did not test the pull request's current head")
    number = current["pullRequest"]
    if len([item for item in run.get("pull_requests") or () if isinstance(item, dict)
            and item.get("number") == number]) != 1:
        raise RetainedReuseRejected("association", "Source run lacks one live association with the pull request")
    _require_reference(run, trusted_workflow_sha)
    tree = current["validationTree"]
    contributions_artifact = _run_artifact(api, run, retained_contributions_name(tree, attempt),
                                           _ARTIFACT_LIMITS["contributions"])
    plan_artifact = _run_artifact(api, run, f"codex-agent-ci-plan-control-{tree}", _ARTIFACT_LIMITS["plan"])
    jobs = _gate_jobs(api.items(f"actions/runs/{run['id']}/attempts/{attempt}/jobs", "jobs"), run, attempt)
    _require_window(jobs[RETAINED_GATE_JOB], contributions_artifact)
    source_raw = _single_file(api, plan_artifact, _PLAN_FILE, _ARTIFACT_LIMITS["plan"], work)
    contributions_raw = _single_file(api, contributions_artifact, _CONTRIBUTIONS_FILE,
                                     _ARTIFACT_LIMITS["contributions"], work)
    source = _strict_json(source_raw, "Source impact plan")
    require_retained_plan_pair(current, source, repository_root=repository_root)
    if source["headCommit"] != head:
        raise RetainedReuseRejected("run", "Source impact plan names another PR head")
    tested = api.json(f"git/commits/{source['validationCommit']}")
    parents = tested.get("parents") if isinstance(tested, dict) else None
    if (not isinstance(tested, dict) or tested.get("sha") != source["validationCommit"]
            or not isinstance(tested.get("tree"), dict) or tested["tree"].get("sha") != tree):
        raise RetainedReuseRejected("tree", "Source tested commit does not carry the merge-group tree")
    if not isinstance(parents, list) or [_sha(value, "parent") for value in parents] != [source["baseCommit"], head]:
        raise RetainedReuseRejected("association", "Source tested commit does not merge its PR head")
    try:
        binding = pull_request_binding(run, tested, expected_commit=source["validationCommit"],
                                       pull_request=number, fetch=api.json)
    except (ScopeRejected, ValueError) as error:
        raise RetainedReuseRejected("association", f"Source run is not bound to the pull request: {error}") from error
    if binding.get("number") != number or binding.get("head") != head:
        raise RetainedReuseRejected("association", "Source run binds another pull-request head")
    contributions = _strict_json(contributions_raw, "Retained contributions")
    require_retained_contributions(contributions, source_plan_raw=source_raw, source_plan=source,
                                   run_id=run["id"], run_attempt=attempt)
    pointer = {
        "schemaVersion": 1, "kind": RETAINED_SOURCE_KIND, "repository": REPOSITORY, "pullRequest": number,
        "runId": run["id"], "runAttempt": attempt, "headSha": head, "trustedWorkflowSha": trusted_workflow_sha,
        "validationCommit": source["validationCommit"], "validationTree": tree,
        "gateJobId": jobs[RETAINED_GATE_JOB]["id"], "outerGateJobId": jobs[RETAINED_OUTER_GATE_JOB]["id"],
        "contributions": {"artifactId": contributions_artifact["id"], "artifactName": contributions_artifact["name"],
                          "artifactDigest": contributions_artifact["digest"], "sha256": _digest(contributions_raw)},
        "plan": {"artifactId": plan_artifact["id"], "artifactName": plan_artifact["name"],
                 "artifactDigest": plan_artifact["digest"], "sha256": _digest(source_raw)},
    }
    return {_SOURCE_PLAN_FILE: source_raw, _CONTRIBUTIONS_FILE: contributions_raw, "pointer": pointer}


def verify_retained_bundle(root: Any, current_plan: Any, *, repository_root: Any, environ: Mapping[str, str],
                           trusted_workflow_sha: str, source_run_id: int | None = None,
                           source_run_attempt: int | None = None) -> dict[str, Any]:
    """Offline re-verification of a staged bundle against the current plan and runner."""
    from pathlib import Path
    root, current_plan = Path(root), Path(current_plan)
    if root.is_symlink() or not root.is_dir():
        raise RetainedReuseRejected("bundle", "Retained validation bundle root is unsafe")
    entries = list(root.iterdir())
    if ({entry.name for entry in entries} != _BUNDLE_FILES
            or any(entry.is_symlink() or not entry.is_file() for entry in entries)):
        raise RetainedReuseRejected("bundle", "Retained validation bundle has an unexpected file set")
    if current_plan.is_symlink() or not current_plan.is_file():
        raise RetainedReuseRejected("bundle", "Current impact plan is unsafe")
    current = _strict_json(current_plan.read_bytes(), "Current impact plan", "bundle")
    try:
        require_consumer_environment(environ, current)
    except ScopeRejected as error:
        raise RetainedReuseRejected("consumer", str(error)) from error
    raw = {name: (root / name).read_bytes() for name in _BUNDLE_FILES}
    pointer = _strict_json(raw[_SOURCE_FILE], "Retained validation source", "bundle")
    if set(pointer) != {"schemaVersion", "kind", "repository", "pullRequest", "runId", "runAttempt", "headSha",
                        "trustedWorkflowSha", "validationCommit", "validationTree", "gateJobId", "outerGateJobId",
                        "contributions", "plan"}:
        raise RetainedReuseRejected("bundle", "Retained validation source has an unexpected key set")
    run_id = _require_int(pointer["runId"], "Source run ID", "bundle")
    attempt = _require_int(pointer["runAttempt"], "Source run attempt", "bundle")
    if (pointer["schemaVersion"] != 1 or type(pointer["schemaVersion"]) is not int
            or pointer["kind"] != RETAINED_SOURCE_KIND or pointer["repository"] != REPOSITORY
            or pointer["pullRequest"] != current["pullRequest"] or type(pointer["pullRequest"]) is not int
            or pointer["validationTree"] != current["validationTree"]
            or pointer["trustedWorkflowSha"] != trusted_workflow_sha
            or source_run_id is not None and run_id != source_run_id
            or source_run_attempt is not None and attempt != source_run_attempt):
        raise RetainedReuseRejected("bundle", "Retained validation source differs from this merge group")
    _require_int(pointer["gateJobId"], "Gate job ID", "bundle")
    _require_int(pointer["outerGateJobId"], "Outer gate job ID", "bundle")
    for field, filename, name in (
            ("contributions", _CONTRIBUTIONS_FILE, retained_contributions_name(current["validationTree"], attempt)),
            ("plan", _SOURCE_PLAN_FILE, f"codex-agent-ci-plan-control-{current['validationTree']}")):
        row = pointer[field]
        if (not isinstance(row, dict) or set(row) != {"artifactId", "artifactName", "artifactDigest", "sha256"}
                or type(row["artifactId"]) is not int or row["artifactId"] < 1 or row["artifactName"] != name
                or not isinstance(row["artifactDigest"], str) or _DIGEST.fullmatch(row["artifactDigest"]) is None
                or row["sha256"] != _digest(raw[filename])):
            raise RetainedReuseRejected("bundle", f"Retained validation {field} pointer differs from its bytes")
    source = _strict_json(raw[_SOURCE_PLAN_FILE], "Source impact plan")
    require_retained_plan_pair(current, source, repository_root=repository_root)
    if source["headCommit"] != pointer["headSha"] or source["validationCommit"] != pointer["validationCommit"]:
        raise RetainedReuseRejected("bundle", "Retained validation source names another PR commit")
    require_retained_contributions(_strict_json(raw[_CONTRIBUTIONS_FILE], "Retained contributions"),
                                   source_plan_raw=raw[_SOURCE_PLAN_FILE], source_plan=source,
                                   run_id=run_id, run_attempt=attempt)
    return pointer


def _write_bundle(destination: Any, bundle: Mapping[str, Any]) -> None:
    import json
    import shutil
    import tempfile
    from pathlib import Path
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RetainedReuseRejected("bundle", "Retained validation destination must be fresh")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".retained-", dir=destination.parent))
    try:
        (staged / _SOURCE_PLAN_FILE).write_bytes(bundle[_SOURCE_PLAN_FILE])
        (staged / _CONTRIBUTIONS_FILE).write_bytes(bundle[_CONTRIBUTIONS_FILE])
        (staged / _SOURCE_FILE).write_text(json.dumps(bundle["pointer"], indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8")
        staged.rename(destination)
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise


class GitHubReads:
    """Fixed read-only GETs on the canonical repository (never another origin)."""

    def __init__(self, token: str, api_url: str = GITHUB_API):
        if api_url != GITHUB_API or not isinstance(token, str) or not token:
            raise RetainedReuseRejected("consumer", "Retained reuse reads only the canonical GitHub API")
        self._token = token

    def json(self, path: str) -> Any:
        from reuse import api_json
        return api_json(f"{GITHUB_API}/repos/{REPOSITORY}/{path}", self._token)

    def items(self, path: str, key: str) -> list[Any]:
        from reuse import paginated_items
        return paginated_items(f"{GITHUB_API}/repos/{REPOSITORY}/{path}", key, self._token)

    def download(self, artifact: Mapping[str, Any], destination: Any, max_bytes: int) -> None:
        from reuse import download_artifact_to_file
        download_artifact_to_file(dict(artifact), self._token, destination, max_bytes=max_bytes)


def discover_retained_pr_validation(plan_path: Any, destination: Any, *, environ: Mapping[str, str],
                                    repository_root: Any, trusted_workflow_sha: Any = None, api: Any = None,
                                    source_run_id: int | None = None,
                                    log: Callable[[str], None] = print) -> dict[str, str]:
    """Merge-group plan step: reuse a verified retained PR validation or fail closed.

    Returns step outputs. Every exception (or mismatch) yields ``reused=false``
    and one ``[route:merge-queue-reuse:<reason>]`` line; nothing is staged then.
    """
    import shutil
    import tempfile
    from pathlib import Path
    destination = Path(destination)
    try:
        if environ.get("GITHUB_EVENT_NAME") != "merge_group":
            raise RetainedReuseRejected("not-merge-group", "Retained PR validation reuse is merge-group only")
        if not isinstance(trusted_workflow_sha, str) or _OID.fullmatch(trusted_workflow_sha) is None:
            raise RetainedReuseRejected("workflow", "Current reviewed product workflow SHA is not exact")
        path = Path(plan_path)
        if path.is_symlink() or not path.is_file():
            raise RetainedReuseRejected("plan", "Current impact plan is unsafe")
        current = _strict_json(path.read_bytes(), "Current impact plan", "plan")
        try:
            require_consumer_environment(environ, current)
        except ScopeRejected as error:
            raise RetainedReuseRejected("consumer", str(error)) from error
        if api is None:
            api = GitHubReads(environ.get("GITHUB_TOKEN", ""), environ.get("GITHUB_API_URL", GITHUB_API))
        number = current["pullRequest"]
        if type(number) is not int or number < 1:
            raise RetainedReuseRejected("plan", "Current impact plan lacks its pull request")
        pull = api.json(f"pulls/{number}")
        try:
            _require_same_repository_pull(pull, number, REPOSITORY, "Pull request")
        except ScopeRejected as error:
            raise RetainedReuseRejected("fork" if error.reason == "fork" else "pull-request", str(error)) from error
        if pull.get("state") != "open" or pull.get("merged") is not False:
            raise RetainedReuseRejected("pull-request", "Merge-group pull request is not open")
        head = pull["head"]["sha"]
        if source_run_id is not None:
            candidates = [_require_int(source_run_id, "Requested source run", "run")]
        else:
            runs = api.items(f"actions/workflows/ci.yml/runs?event=pull_request&status=completed&head_sha={head}",
                             "workflow_runs")
            if not isinstance(runs, list) or any(not isinstance(run, dict) for run in runs):
                raise RetainedReuseRejected("run", "Workflow run listing is malformed")
            candidates = sorted({run["id"] for run in runs if type(run.get("id")) is int and run["id"] > 0
                                 and run.get("conclusion") == "success" and run.get("head_sha") == head}, reverse=True)
        if not candidates:
            raise RetainedReuseRejected("no-candidate", f"No green ci.yml pull_request run tested PR head {head}")
        failure = None
        for run_id in candidates:
            with tempfile.TemporaryDirectory(prefix="retained-reuse-") as work:
                try:
                    # The run endpoint (not an attempt) reports the final attempt only.
                    run = api.json(f"actions/runs/{run_id}")
                    if not isinstance(run, dict) or run.get("id") != run_id:
                        raise RetainedReuseRejected("run", "Source run response names another run")
                    bundle = observe_retained_pr_validation(current, run, pull, api=api,
                        repository_root=repository_root, trusted_workflow_sha=trusted_workflow_sha, work=work)
                except RetainedReuseRejected as error:
                    failure = error
                    log(route_line(error.reason, f"run {run_id}: {error}"))
                    continue
            _write_bundle(destination, bundle)
            try:
                pointer = verify_retained_bundle(destination, path, repository_root=repository_root,
                    environ=environ, trusted_workflow_sha=trusted_workflow_sha,
                    source_run_id=run_id, source_run_attempt=bundle["pointer"]["runAttempt"])
            except BaseException:
                shutil.rmtree(destination, ignore_errors=True)
                raise
            outputs = {"reused": "true", "kind": RETAINED_KIND, "source_run_id": str(pointer["runId"]),
                       "source_run_attempt": str(pointer["runAttempt"]),
                       "artifact_name": pointer["contributions"]["artifactName"]}
            log(route_line("applied", f"run {pointer['runId']} attempt {pointer['runAttempt']} "
                                      f"{pointer['contributions']['artifactName']}"))
            return outputs
        raise failure
    except Exception as error:  # Fail closed: any doubt keeps the full merge-group path.
        reason = error.reason if isinstance(error, RetainedReuseRejected) else "error"
        log(route_line(reason, f"reused=false: {type(error).__name__}: {error}"))
        return {"reused": "false"}


def stage_merge_group_retained_validation(bundle: Any, current_plan: Any, destination: Any, *,
                                          repository_root: Any, environ: Mapping[str, str],
                                          trusted_workflow_sha: str, source_run_id: int,
                                          source_run_attempt: int) -> dict[str, Any]:
    """Merge gate: re-verify the plan-job bundle offline and stage its distinct artifact."""
    import shutil
    from pathlib import Path
    if environ.get("GITHUB_EVENT_NAME") != "merge_group":
        raise RetainedReuseRejected("not-merge-group", "Retained PR validation reuse is merge-group only")
    pointer = verify_retained_bundle(bundle, current_plan, repository_root=repository_root, environ=environ,
        trusted_workflow_sha=trusted_workflow_sha, source_run_id=source_run_id,
        source_run_attempt=source_run_attempt)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RetainedReuseRejected("bundle", "Merge-group retained validation destination must be fresh")
    destination.mkdir(parents=True)
    for name in sorted(_BUNDLE_FILES):
        shutil.copyfile(Path(bundle) / name, destination / name)
    shutil.copyfile(current_plan, destination / _PLAN_FILE)
    return pointer


def main(argv: Iterable[str] | None = None) -> int:
    """Read-only dry run: ``merge-group-retained-dry-run --plan P --destination D --source-run-id N``."""
    import argparse
    import os
    import sys
    from pathlib import Path
    parser = argparse.ArgumentParser(description=main.__doc__, allow_abbrev=False)
    parser.add_argument("mode", choices=("merge-group-retained-dry-run",))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--source-run-id", type=int)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    arguments = parser.parse_args(None if argv is None else list(argv))
    outputs = discover_retained_pr_validation(arguments.plan, arguments.destination, environ=os.environ,
        repository_root=arguments.repository_root, trusted_workflow_sha=arguments.trusted_workflow_sha,
        source_run_id=arguments.source_run_id, log=lambda line: print(line, file=sys.stderr))
    for key, value in outputs.items():
        print(f"{key}={value}")
    return 0 if outputs.get("reused") == "true" else 1


if __name__ == "__main__":
    raise SystemExit(main())
