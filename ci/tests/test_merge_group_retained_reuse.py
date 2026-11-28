"""Merge-queue reuse of a green retained-path PR validation (S1050, Option A')."""

import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import textwrap
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import impact  # noqa: E402
import producer_scope as scope  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REPO = scope.REPOSITORY
PR = 37
TREE = "1" * 40
BASE, HEAD, MERGE = "b" * 40, "a" * 40, "e" * 40
QUEUE_BASE, QUEUE = "c" * 40, "f" * 40
TRUSTED = "9" * 40
RUN, ATTEMPT = 46200000001, 2
GATE_START, GATE_END = "2026-11-28T10:00:00Z", "2026-11-28T10:05:00Z"
CONTRIBUTIONS_NAME = f"codex-agent-current-validation-contributions-{TREE}-attempt-{ATTEMPT}"
PLAN_NAME = f"codex-agent-ci-plan-control-{TREE}"
ENVIRON = {"GITHUB_REPOSITORY": REPO, "GITHUB_EVENT_NAME": "merge_group",
           "GITHUB_REF": f"refs/heads/gh-readonly-queue/main/pr-{PR}-{QUEUE}", "GITHUB_SHA": QUEUE}


def projected(event, changes, *, force_full, reason, android_evidence=True, **identity):
    lanes, full, unknown = impact._legacy_lane_states(ROOT, changes, force_full=force_full,
                                                      remote_authorized=True, remote_reason=reason)
    return {"schemaVersion": 1, "event": event, "repository": REPO, "pullRequest": PR,
            "mergeReady": True, "remoteBuildAuthorized": True, "remoteBuildAuthorizationReason": reason,
            "androidEvidenceRequired": android_evidence, "fullRequested": force_full, "full": full,
            "unknownPaths": unknown, "changedPaths": sorted(changes), "lanes": lanes, **identity}


def current_plan():
    return projected("merge_group", ["ci/producer_scope.py"], force_full=False, reason="merge-group",
                     baseCommit=QUEUE_BASE, headCommit=QUEUE, validationCommit=QUEUE, validationTree=TREE)


def source_plan(**overrides):
    plan = projected("pull_request", ["ci/producer_scope.py"], force_full=True, reason="pull-request-final",
                     baseCommit=BASE, headCommit=HEAD, validationCommit=MERGE, validationTree=TREE)
    plan.update(overrides)
    return plan


def raw(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def archive(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as output:
        for name, data in members.items():
            output.writestr(name, data)
    return buffer.getvalue()


def repository(fork=False, name=REPO):
    return {"full_name": name, "fork": fork}


def compare(ancestor):
    return {"base_commit": {"sha": ancestor}, "merge_base_commit": {"sha": ancestor},
            "behind_by": 0, "status": "identical"}


class FakeAPI:
    """Canned read-only GitHub responses for one green retained PR-37 run."""

    def __init__(self, *, source=None, contributions=None, contributions_members=None, verify_downloads=True):
        self.source_raw = raw(source if source is not None else source_plan())
        if contributions is None:
            contributions = {
                "schemaVersion": 1, "kind": "current-validation-contributions", "result": "passed",
                "consumer": {"repository": REPO, "workflowPath": ".github/workflows/ci.yml", "event": "pull_request",
                             "runId": RUN, "runAttempt": ATTEMPT, "pullRequest": PR, "commit": MERGE, "tree": TREE},
                "planSha256": digest(self.source_raw), "laneReceipts": {"ios-package": "sha256:" + "0" * 64},
                "reviewedRuntime": {"lanes": ["contracts"]}}
        self.contributions = contributions
        self.contributions_raw = raw(contributions)
        self.archives = {
            901: archive(contributions_members or {"current-validation-contributions.json": self.contributions_raw}),
            902: archive({"impact-plan.json": self.source_raw}),
        }
        self.verify_downloads = verify_downloads
        pull_entry = {"number": PR, "base": {"sha": BASE, "ref": "main", "repo": repository()},
                      "head": {"sha": HEAD, "ref": "feature", "repo": repository()}}
        self.run = {"id": RUN, "run_attempt": ATTEMPT, "event": "pull_request", "status": "completed",
                    "conclusion": "success", "path": ".github/workflows/ci.yml", "head_sha": HEAD,
                    "head_branch": "feature", "repository": repository(), "head_repository": repository(),
                    "pull_requests": [pull_entry],
                    "referenced_workflows": [
                        {"path": f"{REPO}/.github/workflows/product-validation.yml@reuse-authority",
                         "ref": "refs/heads/reuse-authority", "sha": TRUSTED},
                        {"path": f"{REPO}/.github/workflows/sdk-validation.yml@{TRUSTED}",
                         "ref": "refs/heads/reuse-authority", "sha": TRUSTED}]}
        self.pull = {"number": PR, "state": "open", "merged": False,
                     "head": {"sha": HEAD, "ref": "feature", "repo": repository()},
                     "base": {"ref": "main", "repo": repository()}}
        self.responses = {
            f"pulls/{PR}": self.pull,
            f"actions/runs/{RUN}": self.run,
            f"git/commits/{MERGE}": {"sha": MERGE, "tree": {"sha": TREE}, "parents": [{"sha": BASE}, {"sha": HEAD}]},
            f"compare/{HEAD}...{HEAD}?per_page=1": compare(HEAD),
            f"compare/{BASE}...main?per_page=1": compare(BASE),
        }
        self.lists = {
            f"actions/workflows/ci.yml/runs?event=pull_request&status=completed&head_sha={HEAD}":
                [{"id": RUN, "conclusion": "success", "head_sha": HEAD}],
            f"actions/runs/{RUN}/artifacts?name={CONTRIBUTIONS_NAME}": [self.artifact(901, CONTRIBUTIONS_NAME,
                                                                                       "2026-11-28T10:03:00Z")],
            f"actions/runs/{RUN}/artifacts?name={PLAN_NAME}": [self.artifact(902, PLAN_NAME, "2026-11-28T09:00:00Z")],
            f"actions/runs/{RUN}/attempts/{ATTEMPT}/jobs": [
                self.job(1, scope.RETAINED_GATE_JOB, GATE_START, GATE_END),
                self.job(2, scope.RETAINED_OUTER_GATE_JOB, "2026-11-28T10:05:01Z", "2026-11-28T10:05:09Z"),
                self.job(3, "product-validation / plan", "2026-11-28T08:00:00Z", "2026-11-28T09:00:05Z")],
        }
        self.calls = []

    def artifact(self, identity, name, created):
        data = self.archives[identity]
        return {"id": identity, "name": name, "expired": False, "created_at": created, "size_in_bytes": len(data),
                "digest": digest(data),
                "archive_download_url": f"https://api.github.com/repos/{REPO}/actions/artifacts/{identity}/zip",
                "workflow_run": {"id": RUN, "head_sha": HEAD, "repository_id": 7, "head_repository_id": 7}}

    def job(self, identity, name, started, completed):
        return {"id": identity, "name": name, "run_id": RUN, "run_attempt": ATTEMPT, "head_sha": HEAD,
                "status": "completed", "conclusion": "success", "started_at": started, "completed_at": completed}

    def json(self, path):
        self.calls.append(("json", path))
        if path not in self.responses:
            raise OSError(f"unexpected read {path}")
        value = self.responses[path]
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)

    def items(self, path, key):
        self.calls.append(("items", path, key))
        if path not in self.lists:
            raise OSError(f"unexpected listing {path}")
        return copy.deepcopy(self.lists[path])

    def download(self, artifact, destination, max_bytes):
        self.calls.append(("download", artifact["id"]))
        data = self.archives[artifact["id"]]
        if self.verify_downloads and (digest(data) != artifact["digest"] or len(data) > max_bytes):
            raise ValueError("GitHub artifact transport digest or size mismatch")
        Path(destination).write_bytes(data)

    def listed(self, path):
        return self.lists[path]


class RetainedReuseTest(unittest.TestCase):
    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp(prefix="retained-reuse-test-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.scratch, ignore_errors=True))
        self.plan_path = self.scratch / "impact-plan.json"
        self.plan_path.write_bytes(raw(current_plan()))
        self.destination = self.scratch / "build/ci/reused-retained-validation"
        self.lines = []

    def discover(self, api, *, environ=ENVIRON, plan=None, trusted=TRUSTED, source_run_id=None):
        if plan is not None:
            self.plan_path.write_bytes(raw(plan))
        return scope.discover_retained_pr_validation(self.plan_path, self.destination, environ=dict(environ),
            repository_root=ROOT, trusted_workflow_sha=trusted, api=api, source_run_id=source_run_id,
            log=self.lines.append)

    def assertRejected(self, api, reason, **kwargs):
        outputs = self.discover(api, **kwargs)
        self.assertEqual({"reused": "false"}, outputs)
        self.assertFalse(self.destination.exists())
        self.assertTrue(any(line.startswith(f"[route:merge-queue-reuse:{reason}] ") for line in self.lines),
                        self.lines)
        for line in self.lines:
            self.assertNotIn("\n", line)
            self.assertFalse(line.startswith("::"))

    # Positive ------------------------------------------------------------------

    def test_identical_tree_final_green_attempt_is_reused_as_retained(self):
        api = FakeAPI()
        outputs = self.discover(api)
        self.assertEqual({"reused": "true", "kind": "retained", "source_run_id": str(RUN),
                          "source_run_attempt": str(ATTEMPT), "artifact_name": CONTRIBUTIONS_NAME}, outputs)
        self.assertEqual({"source-impact-plan.json", "current-validation-contributions.json", "source.json"},
                         {path.name for path in self.destination.iterdir()})
        self.assertEqual(api.source_raw, (self.destination / "source-impact-plan.json").read_bytes())
        self.assertEqual(api.contributions_raw,
                         (self.destination / "current-validation-contributions.json").read_bytes())
        pointer = json.loads((self.destination / "source.json").read_text())
        self.assertEqual((RUN, ATTEMPT, TRUSTED, 1, 2), (pointer["runId"], pointer["runAttempt"],
                         pointer["trustedWorkflowSha"], pointer["gateJobId"], pointer["outerGateJobId"]))
        self.assertEqual(digest(api.archives[901]), pointer["contributions"]["artifactDigest"])
        self.assertTrue(self.lines[-1].startswith("[route:merge-queue-reuse:applied] "))
        # Read-only: only fixed GETs, and only the run's final attempt jobs.
        self.assertIn(("items", f"actions/runs/{RUN}/attempts/{ATTEMPT}/jobs", "jobs"), api.calls)
        self.assertFalse(any("attempts/1" in str(call) for call in api.calls))

    def test_explicit_source_run_is_verified_identically(self):
        outputs = self.discover(FakeAPI(), source_run_id=RUN)
        self.assertEqual("true", outputs["reused"])

    def test_newest_failing_candidate_falls_back_to_an_older_verified_run(self):
        api = FakeAPI()
        api.lists[next(path for path in api.lists if path.startswith("actions/workflows/"))].insert(
            0, {"id": RUN + 5, "conclusion": "success", "head_sha": HEAD})
        api.responses[f"actions/runs/{RUN + 5}"] = {**api.run, "id": RUN + 5, "conclusion": "failure"}
        self.assertEqual("true", self.discover(api)["reused"])
        self.assertTrue(any(line.startswith("[route:merge-queue-reuse:run] run %d" % (RUN + 5))
                            for line in self.lines))

    def test_stage_reverifies_offline_and_never_mints_schema1(self):
        self.assertEqual("true", self.discover(FakeAPI())["reused"])
        staged = self.scratch / "build/ci/merge-group-retained-validation"
        pointer = scope.stage_merge_group_retained_validation(self.destination, self.plan_path, staged,
            repository_root=ROOT, environ=ENVIRON, trusted_workflow_sha=TRUSTED,
            source_run_id=RUN, source_run_attempt=ATTEMPT)
        self.assertEqual(RUN, pointer["runId"])
        self.assertEqual({"impact-plan.json", "source-impact-plan.json", "current-validation-contributions.json",
                          "source.json"}, {path.name for path in staged.iterdir()})
        self.assertFalse((staged / "validation-receipt.json").exists())
        self.assertEqual(self.plan_path.read_bytes(), (staged / "impact-plan.json").read_bytes())

    # (a) run, workflow, event, fork, association --------------------------------

    def test_pull_request_event_never_reuses_retained_validation(self):
        environ = {**ENVIRON, "GITHUB_EVENT_NAME": "pull_request", "GITHUB_REF": f"refs/pull/{PR}/merge"}
        self.assertRejected(FakeAPI(), "not-merge-group", environ=environ)

    def test_consumer_runner_must_be_the_planned_merge_group(self):
        self.assertRejected(FakeAPI(), "consumer", environ={**ENVIRON, "GITHUB_SHA": "0" * 40})
        self.lines.clear()
        self.assertRejected(FakeAPI(), "consumer",
                            environ={**ENVIRON, "GITHUB_REF": f"refs/heads/gh-readonly-queue/main/pr-38-{QUEUE}"})
        self.lines.clear()
        self.assertRejected(FakeAPI(), "consumer", environ={**ENVIRON, "GITHUB_REPOSITORY": "fork/codex-agent"})

    def test_untrusted_workflow_sha_is_rejected(self):
        self.assertRejected(FakeAPI(), "workflow", trusted=None)
        self.lines.clear()
        self.assertRejected(FakeAPI(), "workflow", trusted="8" * 40)

    def test_pull_request_must_be_open_same_repository_and_not_a_fork(self):
        for change, reason in ((dict(state="closed"), "pull-request"), (dict(merged=True), "pull-request"),
                               (dict(head={"sha": HEAD, "ref": "feature", "repo": repository(True)}), "fork"),
                               (dict(head={"sha": HEAD, "ref": "feature", "repo": repository(False, "x/y")}),
                                "pull-request"),
                               (dict(base={"ref": "release", "repo": repository()}), "pull-request")):
            with self.subTest(change=change):
                api = FakeAPI()
                api.responses[f"pulls/{PR}"] = {**api.pull, **change}
                self.lines.clear()
                self.assertRejected(api, reason)

    def test_no_green_candidate_for_the_current_head_is_a_miss(self):
        api = FakeAPI()
        listing = next(path for path in api.lists if path.startswith("actions/workflows/"))
        for runs in ([], [{"id": RUN, "conclusion": "failure", "head_sha": HEAD}],
                     [{"id": RUN, "conclusion": "success", "head_sha": "0" * 40}]):
            with self.subTest(runs=runs):
                api.lists[listing] = runs
                self.lines.clear()
                self.assertRejected(api, "no-candidate")

    def test_source_run_must_be_a_completed_successful_ci_pull_request_run(self):
        for change, reason in ((dict(conclusion="failure"), "run"), (dict(status="in_progress"), "run"),
                               (dict(event="merge_group"), "run"), (dict(event="push"), "run"),
                               (dict(path=".github/workflows/promote.yml"), "run"),
                               (dict(head_repository=repository(True)), "fork"),
                               (dict(repository=repository(False, "x/y")), "run"),
                               (dict(head_sha="0" * 40), "run"), (dict(id=RUN + 1), "run")):
            with self.subTest(change=change):
                api = FakeAPI()
                api.responses[f"actions/runs/{RUN}"] = {**api.run, **change}
                self.lines.clear()
                self.assertRejected(api, reason)

    def test_source_run_requires_one_live_association_with_this_pull_request(self):
        for requests in ([], [{"number": 38}], None):
            with self.subTest(requests=requests):
                api = FakeAPI()
                api.responses[f"actions/runs/{RUN}"] = {**api.run, "pull_requests": requests}
                self.lines.clear()
                self.assertRejected(api, "association")

    def test_live_association_requires_branch_and_ancestry_proof(self):
        api = FakeAPI()
        api.responses[f"compare/{BASE}...main?per_page=1"] = {**compare(BASE), "behind_by": 3, "status": "diverged"}
        self.assertRejected(api, "association")
        self.lines.clear()
        api = FakeAPI()
        api.responses[f"actions/runs/{RUN}"] = {**api.run, "head_branch": "other"}
        self.assertRejected(api, "association")

    def test_source_run_must_use_the_current_reviewed_product_workflow(self):
        for references in ([], [{"path": f"{REPO}/.github/workflows/product-validation.yml@reuse-authority",
                                 "ref": "refs/heads/reuse-authority", "sha": "8" * 40}],
                           [{"path": f"{REPO}/.github/workflows/product-validation.yml@reuse-authority",
                             "ref": "refs/pull/37/merge", "sha": TRUSTED}], None):
            with self.subTest(references=references):
                api = FakeAPI()
                api.responses[f"actions/runs/{RUN}"] = {**api.run, "referenced_workflows": references}
                self.lines.clear()
                self.assertRejected(api, "workflow")

    # (b) final attempt, artifact identity, digest, content ------------------------

    def test_only_the_final_attempt_artifact_counts(self):
        api = FakeAPI()
        # The final attempt (2) has no contributions; attempt 1's upload must never count.
        api.lists[f"actions/runs/{RUN}/artifacts?name={CONTRIBUTIONS_NAME}"] = []
        api.lists[f"actions/runs/{RUN}/artifacts?name={CONTRIBUTIONS_NAME[:-1]}1"] = [
            api.artifact(901, CONTRIBUTIONS_NAME[:-1] + "1", "2026-11-28T10:03:00Z")]
        self.assertRejected(api, "artifact-missing")
        self.assertNotIn(("download", 901), api.calls)

    def test_contribution_artifact_identity_is_exact(self):
        path = f"actions/runs/{RUN}/artifacts?name={CONTRIBUTIONS_NAME}"
        for change, reason in ((dict(expired=True), "artifact-expired"), (dict(expired=None), "artifact-expired"),
                               (dict(workflow_run={"id": RUN + 1, "head_sha": HEAD, "repository_id": 7,
                                                   "head_repository_id": 7}), "artifact-identity"),
                               (dict(workflow_run={"id": RUN, "head_sha": HEAD, "repository_id": 7,
                                                   "head_repository_id": 8}), "artifact-identity"),
                               (dict(archive_download_url="https://evil.invalid/zip"), "artifact-identity"),
                               (dict(digest="sha1:abc"), "artifact-digest"),
                               (dict(size_in_bytes=0), "artifact-content"),
                               (dict(size_in_bytes=(64 << 20) + 1), "artifact-content")):
            with self.subTest(change=change):
                api = FakeAPI()
                api.lists[path] = [{**api.lists[path][0], **change}]
                self.lines.clear()
                self.assertRejected(api, reason)
        api = FakeAPI()
        api.lists[path] = api.lists[path] * 2
        self.lines.clear()
        self.assertRejected(api, "artifact-identity")

    def test_downloaded_bytes_must_equal_the_api_digest(self):
        for verify in (True, False):
            with self.subTest(verify=verify):
                api = FakeAPI(verify_downloads=verify)
                api.archives[901] = archive({"current-validation-contributions.json": b"{}"})
                self.lines.clear()
                self.assertRejected(api, "artifact-digest")

    def test_contribution_archive_holds_exactly_one_regular_file(self):
        for members in ({"current-validation-contributions.json": b"{}", "extra.json": b"{}"},
                        {"other.json": b"{}"}, {"../current-validation-contributions.json": b"{}"}):
            with self.subTest(members=list(members)):
                api = FakeAPI(contributions_members=members)
                self.lines.clear()
                self.assertRejected(api, "artifact-content")

    def test_duplicate_keys_and_non_finite_numbers_are_rejected(self):
        api = FakeAPI()
        data = api.contributions_raw.replace(b'"result": "passed"', b'"result": "passed", "result": "passed"')
        api.archives[901] = archive({"current-validation-contributions.json": data})
        api.lists[f"actions/runs/{RUN}/artifacts?name={CONTRIBUTIONS_NAME}"] = [
            api.artifact(901, CONTRIBUTIONS_NAME, "2026-11-28T10:03:00Z")]
        self.assertRejected(api, "artifact-content")
        with self.assertRaises(scope.RetainedReuseRejected):
            scope._strict_json(b'{"a": NaN}', "fixture")

    # (c) plan binding, identical tree, plan authority ----------------------------

    def test_contributions_must_bind_the_source_plan_hash(self):
        api = FakeAPI()
        contributions = {**api.contributions, "planSha256": "sha256:" + "0" * 64}
        self.assertRejected(FakeAPI(contributions=contributions), "plan-hash")

    def test_source_plan_tree_must_equal_the_merge_group_tree(self):
        self.assertRejected(FakeAPI(source=source_plan(validationTree="2" * 40)), "tree")

    def test_tested_commit_must_carry_the_tree_and_merge_the_pr_head(self):
        api = FakeAPI()
        api.responses[f"git/commits/{MERGE}"] = {"sha": MERGE, "tree": {"sha": "2" * 40},
                                                 "parents": [{"sha": BASE}, {"sha": HEAD}]}
        self.assertRejected(api, "tree")
        self.lines.clear()
        api = FakeAPI()
        api.responses[f"git/commits/{MERGE}"] = {"sha": MERGE, "tree": {"sha": TREE},
                                                 "parents": [{"sha": BASE}, {"sha": "0" * 40}]}
        self.assertRejected(api, "association")

    def test_source_plan_must_be_the_authorized_final_pr_plan(self):
        for source in (source_plan(event="merge_group"), source_plan(remoteBuildAuthorizationReason="merge-group"),
                       source_plan(mergeReady=False), source_plan(pullRequest=38), source_plan(repository="x/y"),
                       source_plan(schemaVersion=2), source_plan(headCommit="0" * 40),
                       {**source_plan(), "extra": True}, source_plan(full=False)):
            with self.subTest(source={k: source.get(k) for k in ("event", "pullRequest", "full", "headCommit")}):
                self.lines.clear()
                self.assertRejected(FakeAPI(source=source), "run" if source["headCommit"] != HEAD else "plan")

    def test_source_plan_must_cover_current_work_and_android_evidence(self):
        narrow = projected("pull_request", ["README.md"], force_full=False, reason="pull-request-final",
                           android_evidence=False, baseCommit=BASE, headCommit=HEAD, validationCommit=MERGE,
                           validationTree=TREE)
        self.assertRejected(FakeAPI(source=narrow), "plan")
        self.lines.clear()
        self.assertRejected(FakeAPI(source=source_plan(androidEvidenceRequired=False)), "plan")

    def test_current_plan_must_be_an_authorized_merge_group_plan(self):
        for change in (dict(mergeReady=False), dict(remoteBuildAuthorizationReason="pull-request-final"),
                       dict(lanes={}), dict(pullRequest=None)):
            with self.subTest(change=list(change)):
                self.lines.clear()
                self.assertRejected(FakeAPI(), "consumer" if "pullRequest" in change else "plan",
                                    plan={**current_plan(), **change})

    # (d) contributions document and consumer identity ------------------------------

    def test_contributions_consumer_identity_is_exact(self):
        base = FakeAPI().contributions
        for field, value in (("runId", RUN + 1), ("runAttempt", 1), ("runAttempt", True), ("pullRequest", 38),
                             ("commit", HEAD), ("tree", "2" * 40), ("event", "merge_group"),
                             ("workflowPath", ".github/workflows/promote.yml"), ("repository", "x/y")):
            with self.subTest(field=field, value=value):
                contributions = copy.deepcopy(base)
                contributions["consumer"][field] = value
                self.lines.clear()
                self.assertRejected(FakeAPI(contributions=contributions), "contributions")

    def test_contributions_must_be_a_passed_schema1_retained_gate(self):
        base = FakeAPI().contributions
        for change in (dict(result="failed"), dict(schemaVersion=2), dict(schemaVersion=True),
                       dict(kind="validation-receipt"), dict(extra=1), dict(laneReceipts={"x": "nope"})):
            with self.subTest(change=change):
                self.lines.clear()
                self.assertRejected(FakeAPI(contributions={**base, **change}), "contributions")
        contributions = dict(base)
        del contributions["laneReceipts"]
        self.lines.clear()
        self.assertRejected(FakeAPI(contributions=contributions), "contributions")

    # (e) gate jobs and upload window ------------------------------------------------

    def test_both_merge_gates_must_succeed_in_the_final_attempt(self):
        path = f"actions/runs/{RUN}/attempts/{ATTEMPT}/jobs"
        for index, change in ((0, dict(conclusion="failure")), (1, dict(conclusion="skipped")),
                              (0, dict(run_attempt=1)), (1, dict(status="in_progress")),
                              (0, dict(head_sha="0" * 40)), (0, dict(run_id=RUN + 1)), (0, dict(name="other"))):
            with self.subTest(index=index, change=change):
                api = FakeAPI()
                api.lists[path][index] = {**api.lists[path][index], **change}
                self.lines.clear()
                self.assertRejected(api, "jobs")
        api = FakeAPI()
        api.lists[path].append(api.lists[path][0])
        self.lines.clear()
        self.assertRejected(api, "jobs")

    def test_contributions_must_be_uploaded_inside_the_inner_gate_window(self):
        path = f"actions/runs/{RUN}/artifacts?name={CONTRIBUTIONS_NAME}"
        for created in ("2026-11-28T09:59:59Z", "2026-11-28T10:05:01Z", "2026-11-28T10:03:00+01:00", None):
            with self.subTest(created=created):
                api = FakeAPI()
                api.lists[path] = [{**api.lists[path][0], "created_at": created}]
                self.lines.clear()
                self.assertRejected(api, "artifact-window")

    # (f) fail closed on any exception ----------------------------------------------

    def test_any_exception_returns_reused_false(self):
        for path, error in ((f"pulls/{PR}", OSError("offline")), (f"actions/runs/{RUN}", KeyError("id")),
                            (f"git/commits/{MERGE}", TypeError("bad")), (f"actions/runs/{RUN}", RuntimeError("x"))):
            with self.subTest(path=path, error=error):
                api = FakeAPI()
                api.responses[path] = error
                self.lines.clear()
                outputs = self.discover(api)
                self.assertEqual({"reused": "false"}, outputs)
                self.assertFalse(self.destination.exists())
        api = FakeAPI()
        api.items = mock.Mock(side_effect=ValueError("GitHub response is missing jobs"))
        self.assertEqual({"reused": "false"}, self.discover(api))

    def test_unsafe_plan_or_occupied_destination_fails_closed(self):
        self.destination.mkdir(parents=True)
        self.assertRejected_keep(FakeAPI(), "bundle")
        self.destination.rmdir()
        self.plan_path.write_bytes(b"not json")
        self.assertRejected(FakeAPI(), "plan")

    def assertRejected_keep(self, api, reason):
        self.assertEqual({"reused": "false"}, self.discover(api))
        self.assertEqual([], list(self.destination.iterdir()))
        self.assertTrue(any(line.startswith(f"[route:merge-queue-reuse:{reason}] ") for line in self.lines))

    # Offline bundle re-verification (merge gate) ------------------------------------

    def staged(self):
        self.assertEqual("true", self.discover(FakeAPI())["reused"])
        return self.destination

    def verify(self, bundle, **overrides):
        arguments = dict(repository_root=ROOT, environ=ENVIRON, trusted_workflow_sha=TRUSTED,
                         source_run_id=RUN, source_run_attempt=ATTEMPT)
        arguments.update(overrides)
        return scope.verify_retained_bundle(bundle, self.plan_path, **arguments)

    def test_bundle_reverification_rejects_any_drift(self):
        bundle = self.staged()
        self.assertEqual(RUN, self.verify(bundle)["runId"])
        for overrides in (dict(trusted_workflow_sha="8" * 40), dict(source_run_id=RUN + 1),
                          dict(source_run_attempt=1), dict(environ={**ENVIRON, "GITHUB_SHA": "0" * 40})):
            with self.subTest(overrides=list(overrides)):
                with self.assertRaises(scope.RetainedReuseRejected):
                    self.verify(bundle, **overrides)
        contributions = bundle / "current-validation-contributions.json"
        original = contributions.read_bytes()
        contributions.write_bytes(original.replace(b'"passed"', b'"failed"'))
        with self.assertRaises(scope.RetainedReuseRejected) as caught:
            self.verify(bundle)
        self.assertEqual("bundle", caught.exception.reason)
        contributions.write_bytes(original)
        (bundle / "validation-receipt.json").write_text("{}")
        with self.assertRaises(scope.RetainedReuseRejected):
            self.verify(bundle)

    def test_stage_requires_a_merge_group_runner_and_fresh_destination(self):
        bundle = self.staged()
        staged = self.scratch / "staged"
        with self.assertRaises(scope.RetainedReuseRejected):
            scope.stage_merge_group_retained_validation(bundle, self.plan_path, staged, repository_root=ROOT,
                environ={**ENVIRON, "GITHUB_EVENT_NAME": "pull_request"}, trusted_workflow_sha=TRUSTED,
                source_run_id=RUN, source_run_attempt=ATTEMPT)
        staged.mkdir()
        with self.assertRaises(scope.RetainedReuseRejected):
            scope.stage_merge_group_retained_validation(bundle, self.plan_path, staged, repository_root=ROOT,
                environ=ENVIRON, trusted_workflow_sha=TRUSTED, source_run_id=RUN, source_run_attempt=ATTEMPT)

    # Output and log injection guards ------------------------------------------------

    def test_step_outputs_and_route_lines_cannot_inject(self):
        output = self.scratch / "output"
        scope.write_step_outputs(output, {"reused": True, "kind": "retained", "source_run_id": RUN})
        self.assertEqual(f"reused=true\nkind=retained\nsource_run_id={RUN}\n", output.read_text())
        for values in ({"reused": "true\nkind=retained"}, {"other": "x"}, {"artifact_name": "a b"},
                       {"kind": ""}, {"kind": "x" * 201}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                scope.write_step_outputs(output, values)
        self.assertEqual(f"reused=true\nkind=retained\nsource_run_id={RUN}\n", output.read_text())
        line = scope.route_line("bogus", "a\nb\r::error::x " + "y" * 400)
        self.assertTrue(line.startswith("[route:merge-queue-reuse:error] a?b?::error::x?"))
        self.assertNotIn("\n", line)
        self.assertLessEqual(len(line), 340)

    def test_github_reads_are_pinned_to_the_canonical_api(self):
        with self.assertRaises(scope.RetainedReuseRejected):
            scope.GitHubReads("token", "https://evil.invalid")
        with self.assertRaises(scope.RetainedReuseRejected):
            scope.GitHubReads("", scope.GITHUB_API)
        reads = scope.GitHubReads("token")
        with mock.patch("reuse.api_json", return_value={}) as api_json:
            reads.json(f"pulls/{PR}")
        api_json.assert_called_once_with(f"https://api.github.com/repos/{REPO}/pulls/{PR}", "token")


class RetainedReuseWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/product-validation.yml").read_text()
        cls.plan = cls.workflow.split("\n  plan:\n", 1)[1].split("\n  product:\n", 1)[0]
        cls.gate = cls.workflow.split("\n  merge-gate:\n", 1)[1]

    @staticmethod
    def evaluate(expression, values):
        expression = expression.strip()
        if expression.startswith("${{"):
            expression = expression[3:-2]
        for name in sorted(values, key=len, reverse=True):
            expression = expression.replace(name, repr(values[name]))
        expression = expression.replace("!", " not ").replace(" not =", "!=").replace("&&", " and ").replace(
            "||", " or ")
        return eval(expression, {"__builtins__": {}})

    def step(self, job, marker):
        block = job.split(marker, 1)[1].split("\n      - ", 1)[0]
        return block

    def condition(self, job, marker):
        return re.search(r"^        if: (.+)$", marker + self.step(job, marker), re.M)[1]

    def values(self, *, event, reused, kind, retained=False):
        values = {"inputs.fullReuseAcceptanceOnly": False, "github.event_name": event,
                  "needs.plan.outputs.validation_reused": reused, "needs.plan.outputs.validation_reuse_kind": kind}
        for name in ("retained_android", "retained_node_js", "retained_consumers", "retained_native_source",
                     "retained_apple_source", "reviewed_runtime"):
            values[f"needs.plan.outputs.{name}"] = "true" if retained else "false"
        return values

    def test_plan_exports_kind_and_attempt_of_the_same_reuse_step(self):
        self.assertIn("validation_reused: ${{ steps.validation-reuse.outputs.reused }}", self.plan)
        self.assertIn("validation_reuse_kind: ${{ steps.validation-reuse.outputs.kind }}", self.plan)
        self.assertIn("validation_source_run_attempt: ${{ steps.validation-reuse.outputs.source_run_attempt }}",
                      self.plan)
        step = self.step(self.plan, "      - id: validation-reuse\n")
        self.assertIn("TRUSTED_WORKFLOW_SHA: ${{ steps.publication.outputs.publisher-sha }}", step)
        self.assertIn("Path('build/ci/reused-retained-validation')", step)
        # The retained bundle lives under build/ci, so the plan artifact carries it to the merge gate.
        self.assertIn("name: codex-agent-ci-plan-${{ steps.impact.outputs.validation_tree }}\n          path: build/ci\n",
                      self.plan)
        self.assertLess(self.plan.index("- id: validation-reuse"), self.plan.index("- id: upload_plan\n"))

    def run_reuse_step(self, event, *, legacy=False, outcome=None, error=None):
        step = self.step(self.plan, "      - id: validation-reuse\n")
        script = textwrap.dedent(step.split("python3 - <<'PY'\n", 1)[1].rsplit("\n          PY", 1)[0])
        name = "codex-agent-ci-validation-" + "a" * 40
        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch) / "output"
            environ = dict(GITHUB_API_URL="https://api.invalid", GITHUB_TOKEN="test", GITHUB_OUTPUT=str(output),
                           GITHUB_EVENT_NAME=event, TRUSTED_WORKFLOW_SHA=TRUSTED)
            discover = mock.Mock(return_value=outcome or {"reused": "false"}, side_effect=error)
            with mock.patch.dict(os.environ, environ), \
                    mock.patch("pathlib.Path.read_text",
                               return_value='{"repository":"owner/repo","validationTree":"' + "a" * 40 + '"}'), \
                    mock.patch("reuse.paginated_items",
                               return_value=[{"name": name, "expired": False}] if legacy else []), \
                    mock.patch("producer_scope.discover_retained_pr_validation", discover), \
                    mock.patch("subprocess.run") as legacy_discover:
                exec(compile(script, "<validation-reuse>", "exec"), {})
            return discover, legacy_discover, output.read_text() if output.exists() else ""

    def test_pull_request_runs_never_call_the_retained_branch(self):
        discover, legacy, output = self.run_reuse_step("pull_request")
        discover.assert_not_called()
        legacy.assert_not_called()
        self.assertEqual("reused=false\n", output)
        discover, legacy, output = self.run_reuse_step("pull_request", legacy=True)
        discover.assert_not_called()
        self.assertEqual(["ci/validation_reuse.py", "discover"], legacy.call_args.args[0][1:3])

    def test_merge_group_tries_retained_only_after_a_legacy_miss(self):
        outcome = {"reused": "true", "kind": "retained", "source_run_id": str(RUN),
                   "source_run_attempt": str(ATTEMPT), "artifact_name": CONTRIBUTIONS_NAME}
        discover, legacy, output = self.run_reuse_step("merge_group", outcome=outcome)
        legacy.assert_not_called()
        self.assertEqual(Path("build/ci/reused-retained-validation"), discover.call_args.args[1])
        self.assertEqual(TRUSTED, discover.call_args.kwargs["trusted_workflow_sha"])
        self.assertEqual("".join(f"{key}={value}\n" for key, value in outcome.items()), output)
        discover, legacy, output = self.run_reuse_step("merge_group", legacy=True)
        discover.assert_not_called()
        legacy.assert_called_once()

    def test_merge_group_reuse_step_fails_closed_on_unexpected_errors(self):
        for kwargs in (dict(error=RuntimeError("boom")),
                       dict(outcome={"reused": "true\nkind=retained"}), dict(outcome={"reused": "false"})):
            with self.subTest(kwargs=kwargs):
                _, _, output = self.run_reuse_step("merge_group", **kwargs)
                self.assertEqual("reused=false\n", output)

    def test_retained_kind_skips_every_legacy_schema1_step(self):
        markers = ("      - name: Require an exact receipt set\n",
                   "      - name: Stage the exact reusable validation artifact\n")
        conditions = [self.condition(self.gate, marker) for marker in markers]
        upload = self.gate.split("name: codex-agent-ci-validation-${{ needs.plan.outputs.validation_tree }}", 1)[0]
        conditions.append(re.findall(r"^        if: (.+)$", upload, re.M)[-1])
        for condition in conditions:
            self.assertTrue(condition.endswith("&& needs.plan.outputs.validation_reuse_kind != 'retained' }}"))
            self.assertFalse(self.evaluate(condition, self.values(event="merge_group", reused="true",
                                                                  kind="retained")))
            # Legacy identical-tree reuse and fresh full validation keep the schema-1 path.
            self.assertTrue(self.evaluate(condition, self.values(event="merge_group", reused="true", kind="")))
            self.assertTrue(self.evaluate(condition, self.values(event="pull_request", reused="false", kind="")))
            self.assertFalse(self.evaluate(condition, self.values(event="pull_request", reused="false", kind="",
                                                                  retained=True)))

    def test_retained_kind_reverifies_and_uploads_a_distinct_artifact(self):
        verify_marker = "      - name: Re-verify the merge-group retained PR validation\n"
        upload_marker = "      - name: Preserve the distinct merge-group retained PR validation\n"
        verify, upload = self.step(self.gate, verify_marker), self.step(self.gate, upload_marker)
        for marker in (verify_marker, upload_marker):
            condition = self.condition(self.gate, marker)
            self.assertTrue(self.evaluate(condition, self.values(event="merge_group", reused="true",
                                                                 kind="retained")))
            for event, reused, kind in (("pull_request", "true", "retained"), ("merge_group", "false", "retained"),
                                        ("merge_group", "true", ""), ("pull_request", "false", "")):
                self.assertFalse(self.evaluate(condition, self.values(event=event, reused=reused, kind=kind)))
        self.assertIn("stage_merge_group_retained_validation(Path('build/ci/plan/reused-retained-validation')", verify)
        self.assertIn("TRUSTED_WORKFLOW_SHA: ${{ needs.plan.outputs.publisher_sha }}", verify)
        self.assertIn("SOURCE_RUN_ID: ${{ needs.plan.outputs.validation_source_run_id }}", verify)
        self.assertIn("SOURCE_RUN_ATTEMPT: ${{ needs.plan.outputs.validation_source_run_attempt }}", verify)
        self.assertIn("name: codex-agent-merge-group-retained-validation-${{ needs.plan.outputs.validation_tree }}",
                      upload)
        self.assertIn("overwrite: false", upload)
        self.assertNotIn("codex-agent-ci-validation-", verify + upload)
        self.assertLess(self.gate.index(verify_marker), self.gate.index(upload_marker))
        self.assertLess(self.gate.index("      - if: ${{ !inputs.fullReuseAcceptanceOnly }}\n"
                                        "        uses: actions/download-artifact@"), self.gate.index(verify_marker))


if __name__ == "__main__":
    unittest.main()
