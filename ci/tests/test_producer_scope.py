"""Durable producer/consumer scope (9.5.0 trust rule T1-T6)."""

import copy
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import producer_scope as scope  # noqa: E402
from products import selection  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REPO = scope.REPOSITORY
BASE, HEAD, PR_HEAD, MERGE, TESTED = ("b" * 40, "a" * 40, "c" * 40, "d" * 40, "e" * 40)
QUEUE_HEAD = "f" * 40


def repository(fork=False, name=REPO):
    return {"full_name": name, "fork": fork}


def pull(number=31, *, merged=True, state="closed", head=PR_HEAD, fork=False, head_name=REPO, base_ref="main"):
    return {"number": number, "state": state, "merged": merged, "merge_commit_sha": MERGE if merged else None,
            "head": {"sha": head, "repo": repository(fork, head_name)},
            "base": {"ref": base_ref, "repo": repository()}}


def compare(ancestor, *, behind=0, status="ahead"):
    return {"status": status, "behind_by": behind, "ahead_by": 1,
            "base_commit": {"sha": ancestor}, "merge_base_commit": {"sha": ancestor}}


def run(event="pull_request", *, pull_requests=(), run_id=100, attempt=1, head=HEAD, fork=False,
        branch="feature", path=scope.CI_WORKFLOW):
    return {"id": run_id, "run_attempt": attempt, "event": event, "path": path, "head_sha": head,
            "head_branch": branch, "pull_requests": list(pull_requests),
            "repository": repository(), "head_repository": repository(fork)}


def commit(parents=(BASE, HEAD)):
    return {"sha": TESTED, "tree": {"sha": "9" * 40}, "parents": [{"sha": value} for value in parents]}


class Fetcher:
    """Canned read-only GitHub responses keyed by repository-relative path."""

    def __init__(self, **overrides):
        self.responses = {
            f"commits/{HEAD}/pulls": [pull()],
            "pulls/31": pull(),
            f"compare/{HEAD}...{PR_HEAD}?per_page=1": compare(HEAD),
            f"compare/{BASE}...main?per_page=1": compare(BASE),
            f"compare/{PR_HEAD}...{MERGE}?per_page=1": compare(PR_HEAD),
        }
        self.responses.update(overrides)
        self.paths = []

    def __call__(self, path):
        self.paths.append(path)
        if path not in self.responses:
            raise AssertionError(f"unexpected read {path}")
        return copy.deepcopy(self.responses[path])


def bind(observed=None, tested=None, fetch=None, number=31):
    return scope.pull_request_binding(observed or run(), tested or commit(), expected_commit=TESTED,
                                      pull_request=number, fetch=fetch or Fetcher())


class AssociationTest(unittest.TestCase):
    def rejected(self, reason, function, *args, **kwargs):
        with self.assertRaises(scope.ScopeRejected) as raised:
            function(*args, **kwargs)
        self.assertEqual(reason, raised.exception.reason, str(raised.exception))

    def test_merged_pr_with_empty_pull_requests_is_admitted_durably(self):
        fetch = Fetcher()
        binding = bind(fetch=fetch)
        self.assertEqual({"number": 31, "base": BASE, "head": HEAD, "source": "durable",
                          "merged": True, "mergeCommit": MERGE}, binding)
        self.assertIn(f"commits/{HEAD}/pulls", fetch.paths)
        self.assertIn(f"compare/{PR_HEAD}...{MERGE}?per_page=1", fetch.paths)

    def test_open_pr_live_association_needs_no_read(self):
        live = run(pull_requests=[{"number": 31, "base": {"sha": BASE}, "head": {"sha": HEAD}}])
        fetch = Fetcher()
        self.assertEqual("pull_requests", bind(live, fetch=fetch)["source"])
        self.assertEqual([], fetch.paths)

    def test_live_association_disagreement_never_falls_back(self):
        other = run(pull_requests=[{"number": 32, "base": {"sha": BASE}, "head": {"sha": HEAD}}])
        fetch = Fetcher()
        self.rejected("association-ambiguous", bind, other, fetch=fetch)
        self.assertEqual([], fetch.paths)

    def test_empty_association_without_durable_reader_rejects(self):
        self.rejected("association-ambiguous", scope.pull_request_binding, run(), commit(),
                      expected_commit=TESTED, pull_request=31)

    def test_commit_pulls_disagreeing_or_ambiguous_rejects(self):
        self.rejected("association-disagrees", bind, fetch=Fetcher(**{f"commits/{HEAD}/pulls": [pull(32)]}))
        self.rejected("association-ambiguous", bind, fetch=Fetcher(**{f"commits/{HEAD}/pulls": [pull(), pull(32)]}))
        self.rejected("association-missing", bind, fetch=Fetcher(**{f"commits/{HEAD}/pulls": []}))
        self.rejected("association-disagrees", bind,
                      fetch=Fetcher(**{f"commits/{HEAD}/pulls": [pull(head="1" * 40)]}))

    def test_fork_rejects_at_run_and_pull(self):
        self.rejected("fork", bind, run(fork=True))
        self.rejected("fork", bind, fetch=Fetcher(**{f"commits/{HEAD}/pulls": [pull(fork=True)],
                                                     "pulls/31": pull(fork=True)}))
        self.rejected("repository", bind, fetch=Fetcher(**{"pulls/31": pull(head_name="other/repo")}))

    def test_closed_unmerged_pr_rejects(self):
        self.rejected("not-merged", bind, fetch=Fetcher(**{"pulls/31": pull(merged=False)}))

    def test_open_pr_with_dropped_association_binds_without_merge(self):
        open_pull = pull(merged=False, state="open")
        binding = bind(fetch=Fetcher(**{"pulls/31": open_pull, f"commits/{HEAD}/pulls": [open_pull]}))
        self.assertEqual((False, None), (binding["merged"], binding["mergeCommit"]))

    def test_ancestry_and_main_base_are_required(self):
        self.rejected("ancestry", bind, fetch=Fetcher(**{
            f"compare/{HEAD}...{PR_HEAD}?per_page=1": compare(HEAD, behind=3, status="diverged")}))
        self.rejected("ancestry", bind, fetch=Fetcher(**{
            f"compare/{PR_HEAD}...{MERGE}?per_page=1": compare("1" * 40)}))
        self.rejected("base-not-main", bind, fetch=Fetcher(**{
            f"compare/{BASE}...main?per_page=1": compare(BASE, behind=1, status="diverged")}))
        self.rejected("base-not-main", bind, fetch=Fetcher(**{"pulls/31": pull(base_ref="release")}))

    def test_tested_merge_must_bind_the_trigger_head(self):
        self.rejected("association-disagrees", bind, tested=commit((BASE, "1" * 40)))
        self.rejected("association-disagrees", bind, tested=commit((BASE,)))

    def test_signed_binding_requires_head_as_second_parent(self):
        self.assertEqual("signed", scope.signed_binding(run(), commit(), expected_commit=TESTED,
                                                         pull_request=31)["source"])
        self.rejected("association-disagrees", scope.signed_binding, run(), commit((BASE, "1" * 40)),
                      expected_commit=TESTED, pull_request=31)


class ConsumerScopeTest(unittest.TestCase):
    def environment(self, event, ref):
        return {"GITHUB_REPOSITORY": REPO, "GITHUB_EVENT_NAME": event, "GITHUB_REF": ref, "GITHUB_SHA": TESTED}

    def test_pull_request_and_merge_group_scope(self):
        self.assertEqual(33, scope.consumer_scope(self.environment("pull_request", "refs/pull/33/merge"))["pullRequest"])
        queue = f"refs/heads/gh-readonly-queue/main/pr-33-{BASE}"
        self.assertEqual({"repository": REPO, "event": "merge_group", "pullRequest": 33},
                         scope.consumer_scope(self.environment("merge_group", queue)))

    def test_bad_refs_and_events_reject(self):
        for event, ref, reason in (
                ("merge_group", "refs/heads/gh-readonly-queue/main/feature", "merge-group-ref"),
                ("merge_group", f"refs/heads/gh-readonly-queue/release/pr-33-{BASE}", "merge-group-ref"),
                ("merge_group", f"gh-readonly-queue/main/pr-33-{BASE}", "merge-group-ref"),
                ("pull_request", "refs/pull/33/head", "consumer"),
                ("push", "refs/heads/main", "event"),
                ("workflow_dispatch", "refs/heads/main", "event")):
            with self.subTest(ref=ref), self.assertRaises(scope.ScopeRejected) as raised:
                scope.consumer_scope(self.environment(event, ref))
            self.assertEqual(reason, raised.exception.reason)
        self.assertIsNone(scope.current_pull_request({}))

    def test_consumer_environment_must_match_its_plan(self):
        environment = self.environment("pull_request", "refs/pull/33/merge")
        plan = {"repository": REPO, "event": "pull_request", "pullRequest": 33, "validationCommit": TESTED}
        scope.require_consumer_environment(environment, plan)
        for changed in ({"pullRequest": 31}, {"event": "merge_group"}, {"validationCommit": BASE}):
            with self.subTest(changed=changed), self.assertRaises(scope.ScopeRejected):
                scope.require_consumer_environment(environment, {**plan, **changed})

    def test_ci_consumer_rule(self):
        producer = {"repository": REPO, "event": "pull_request", "pullRequest": 33}
        self.assertEqual(33, scope.require_ci_consumer({"kind": "ci", "producer": producer})["pullRequest"])
        self.assertIsNone(scope.require_ci_consumer({"kind": "ci", "producer": {
            **producer, "event": "merge_group", "pullRequest": None}})["pullRequest"])
        for consumer in ({"kind": "local", "producer": producer},
                         {"kind": "ci", "producer": {**producer, "repository": "fork/codex-agent"}},
                         {"kind": "ci", "producer": {**producer, "pullRequest": None}},
                         {"kind": "ci", "producer": {**producer, "event": "merge_group"}},
                         {"kind": "ci", "producer": {**producer, "event": "workflow_dispatch", "pullRequest": None}},
                         {"kind": "ci", "producer": {**producer, "event": "push", "pullRequest": None}}):
            with self.subTest(consumer=consumer), self.assertRaises(scope.ScopeRejected):
                scope.require_ci_consumer(consumer)


class AdmitTest(unittest.TestCase):
    JOB = "product-validation / sdk-parity"

    def setUp(self):
        self.producer = {"repository": REPO, "workflowPath": scope.CI_WORKFLOW, "event": "pull_request",
                         "pullRequest": 31, "commit": TESTED, "tree": "9" * 40, "runId": 100, "runAttempt": 2}
        self.run = run(run_id=100, attempt=2)
        self.observation = {
            "run": self.run, "jobName": self.JOB,
            "jobs": [self.job(self.JOB)],
            "artifact": {"id": 7, "digest": "sha256:" + "1" * 64, "expired": False,
                         "created_at": "2026-11-20T10:30:00Z", "workflow_run": {"id": 100}},
            "binding": bind(),
        }
        self.consumer = {"repository": REPO, "event": "pull_request", "pullRequest": 31}

    def job(self, name, conclusion="success"):
        return {"name": name, "run_id": 100, "head_sha": HEAD, "status": "completed", "conclusion": conclusion,
                "started_at": "2026-11-20T10:00:00Z", "completed_at": "2026-11-20T11:00:00Z"}

    def rejected(self, reason, producer=None, observation=None, consumer=None, pins=()):
        with self.assertRaises(scope.ScopeRejected) as raised:
            scope.admit(producer or self.producer, observation or self.observation, consumer or self.consumer, pins)
        self.assertEqual(reason, raised.exception.reason, str(raised.exception))

    def test_same_scope_merged_pr_with_empty_pull_requests(self):
        self.assertEqual({"admitted": True, "rule": "same-scope", "scope": 31},
                         scope.admit(self.producer, self.observation, self.consumer))

    def test_unmerged_or_merged_other_pr_is_foreign_unless_landed_or_pinned(self):
        foreign = {**self.consumer, "pullRequest": 33}
        self.rejected("foreign-scope", consumer=foreign)
        self.assertEqual("landed", scope.admit(self.producer, {**self.observation, "landed": True}, foreign)["rule"])
        pins = [(100, 2, 7, "sha256:" + "1" * 64)]
        self.assertEqual("pinned", scope.admit(self.producer, self.observation, foreign, pins)["rule"])
        self.rejected("foreign-scope", consumer=foreign, pins=[(100, 1, 7, "sha256:" + "1" * 64)])

    def test_landed_requires_merge_ancestry_and_an_approved_control_tree(self):
        binding = self.observation["binding"]
        trees = {"ci": "3" * 40, ".github": "4" * 40}
        self.assertTrue(scope.landed(binding, consumer_base=BASE, merge_to_consumer=compare(MERGE),
                                     producer_trees=trees, approved_trees=[trees], main_trees=[]))
        self.assertTrue(scope.landed(binding, consumer_base=BASE, merge_to_consumer=compare(MERGE),
                                     producer_trees=trees, approved_trees=[], main_trees=[trees]))
        with self.assertRaises(scope.ScopeRejected) as raised:
            scope.landed(binding, consumer_base=BASE, merge_to_consumer=compare(MERGE),
                         producer_trees=trees, approved_trees=[{**trees, "ci": "5" * 40}], main_trees=[])
        self.assertEqual("producer-tree-unapproved", raised.exception.reason)
        with self.assertRaises(scope.ScopeRejected) as raised:
            scope.landed({**binding, "merged": False}, consumer_base=BASE, merge_to_consumer=compare(MERGE),
                         producer_trees=trees, approved_trees=[trees], main_trees=[])
        self.assertEqual("not-merged", raised.exception.reason)
        with self.assertRaises(scope.ScopeRejected) as raised:
            scope.landed(binding, consumer_base=BASE, merge_to_consumer=compare(MERGE, behind=2, status="diverged"),
                         producer_trees=trees, approved_trees=[trees], main_trees=[])
        self.assertEqual("base-not-main", raised.exception.reason)

    def test_merge_group_scope(self):
        producer = {**self.producer, "event": "merge_group", "pullRequest": None, "commit": QUEUE_HEAD}
        queue = run("merge_group", run_id=100, attempt=2, head=QUEUE_HEAD,
                    branch=f"gh-readonly-queue/main/pr-33-{BASE}")
        jobs = [{**self.job(self.JOB), "head_sha": QUEUE_HEAD}]
        observation = {**self.observation, "run": queue, "jobs": jobs}
        consumer = {**self.consumer, "event": "merge_group", "pullRequest": 33}
        self.assertEqual({"admitted": True, "rule": "same-scope", "scope": 33},
                         scope.admit(producer, observation, consumer))
        self.rejected("foreign-scope", producer, observation, {**consumer, "pullRequest": 34})
        bad = {**observation, "run": {**queue, "head_branch": "gh-readonly-queue/main/feature"}}
        self.rejected("merge-group-ref", producer, bad, consumer)

    def test_dispatch_requires_authorization(self):
        producer = {**self.producer, "event": "workflow_dispatch", "pullRequest": None}
        dispatched = {**self.observation, "run": {**self.run, "event": "workflow_dispatch"}}
        self.rejected("dispatch-unauthorized", producer, dispatched)
        authorized = {**dispatched, "jobs": [*dispatched["jobs"], self.job(scope.DISPATCH_AUTHORIZATION_JOB)]}
        self.rejected("foreign-scope", producer, authorized)  # no scope of its own: needs a pin
        pins = [(100, 2, 7, "sha256:" + "1" * 64)]
        self.assertEqual("pinned", scope.admit(producer, authorized, self.consumer, pins)["rule"])
        failed = {**dispatched, "jobs": [*dispatched["jobs"], self.job(scope.DISPATCH_AUTHORIZATION_JOB, "failure")]}
        self.rejected("dispatch-unauthorized", producer, failed, pins=pins)

    def test_replay_and_transport_failures_reject_even_when_pinned(self):
        pins = [(100, 2, 7, "sha256:" + "1" * 64)]
        artifact = self.observation["artifact"]
        cases = {
            "artifact-expired": {"artifact": {**artifact, "expired": True}},
            "artifact-window": {"artifact": {**artifact, "created_at": "2026-11-20T11:00:01Z"}},
            "artifact-identity": {"artifact": {**artifact, "workflow_run": {"id": 101}}},
            "job": {"jobs": [self.job(self.JOB, "failure")]},
            "attempt": {"run": {**self.run, "run_attempt": 1}},
            "fork": {"run": {**self.run, "head_repository": repository(True)}},
            "workflow": {"run": {**self.run, "path": ".github/workflows/other.yml"}},
            "event": {"run": {**self.run, "event": "push"}},
        }
        for reason, change in cases.items():
            with self.subTest(reason=reason):
                self.rejected(reason, observation={**self.observation, **change}, pins=pins)
        self.rejected("job", observation={**self.observation, "jobs": [self.job(self.JOB), self.job(self.JOB)]})
        self.rejected("event", consumer={**self.consumer, "event": "workflow_dispatch"}, pins=pins)
        self.rejected("association-missing", observation={**self.observation, "binding": {
            **self.observation["binding"], "number": 32}})


class RegistrationTest(unittest.TestCase):
    def test_producer_scope_owns_no_product_phase(self):
        self.assertEqual(frozenset(), selection._inventory_owners("ci/producer_scope.py"))

    def test_no_pr_31_consumer_scope_remains_in_workflows(self):
        for path in sorted((ROOT / ".github").rglob("*.y*ml")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertIsNone(re.search(r"\.number\s*==\s*31\b", text))
                self.assertNotIn("refs/pull/31/merge", text)


if __name__ == "__main__":
    unittest.main()
