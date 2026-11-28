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
ATTESTATIONS_NAME = f"codex-agent-retained-validation-attestations-{TREE}-attempt-{ATTEMPT}"
RECORD_START, RECORD_END = "2026-11-28T10:05:10Z", "2026-11-28T10:06:00Z"
SIGNER = f"https://github.com/{REPO}/.github/workflows/product-validation.yml@refs/heads/reuse-authority"
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


def pr_repository(name=REPO, identity=7):
    """The shape of a repository inside a workflow run's ``pull_requests`` entry."""
    return {"id": identity, "url": f"https://api.github.com/repos/{name}", "name": name.split("/")[-1]}


def certificate(*, number=PR, run=RUN, attempt=ATTEMPT, commit=MERGE, signer=SIGNER, signer_digest=TRUSTED,
                trigger="pull_request", runner="github-hosted", repository_uri=f"https://github.com/{REPO}"):
    """The certificate fields ``gh attestation verify --format json`` reports for a GitHub-hosted signer."""
    ref = f"refs/pull/{number}/merge"
    return {
        "issuer": "https://token.actions.githubusercontent.com", "subjectAlternativeName": signer,
        "buildSignerURI": signer, "buildSignerDigest": signer_digest, "runnerEnvironment": runner,
        "githubWorkflowTrigger": trigger, "buildTrigger": trigger, "githubWorkflowSHA": commit,
        "githubWorkflowRef": ref, "githubWorkflowRepository": REPO, "sourceRepositoryURI": repository_uri,
        "sourceRepositoryDigest": commit, "sourceRepositoryRef": ref,
        "buildConfigURI": f"{repository_uri}/.github/workflows/ci.yml@{ref}", "buildConfigDigest": commit,
        "runInvocationURI": f"{repository_uri}/actions/runs/{run}/attempts/{attempt}",
    }


def signed_bundle(name, data, **fields):
    """A stand-in Sigstore bundle: what the protected signer would attest for ``data``."""
    return raw({"subject": [{"name": name, "digest": {"sha256": hashlib.sha256(data).hexdigest()}}],
                "predicate_type": "https://slsa.dev/provenance/v1", "certificate": certificate(**fields)})


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
        self.sign()
        self.verify_downloads = verify_downloads
        self.verified = []
        pull_entry = {"id": 1, "number": PR, "url": f"https://api.github.com/repos/{REPO}/pulls/{PR}",
                      "base": {"sha": BASE, "ref": "main", "repo": pr_repository()},
                      "head": {"sha": HEAD, "ref": "feature", "repo": pr_repository()}}
        self.run = {"id": RUN, "run_attempt": ATTEMPT, "event": "pull_request", "status": "completed",
                    "conclusion": "success", "path": ".github/workflows/ci.yml", "head_sha": HEAD,
                    "head_branch": "feature", "repository": {**repository(), "id": 7},
                    "head_repository": {**repository(), "id": 7},
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
            f"actions/runs/{RUN}/attempts/{ATTEMPT}": self.run,
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
            f"actions/runs/{RUN}/artifacts?name={ATTESTATIONS_NAME}": [
                self.artifact(903, ATTESTATIONS_NAME, "2026-11-28T10:05:50Z")],
            f"actions/runs/{RUN}/attempts/{ATTEMPT}/jobs": [
                self.job(1, scope.RETAINED_GATE_JOB, GATE_START, GATE_END),
                self.job(2, scope.RETAINED_OUTER_GATE_JOB, "2026-11-28T10:06:01Z", "2026-11-28T10:06:09Z"),
                self.job(3, "product-validation / plan", "2026-11-28T08:00:00Z", "2026-11-28T09:00:05Z"),
                self.job(4, scope.RETAINED_RECORD_JOB, RECORD_START, RECORD_END)],
        }
        self.calls = []

    def sign(self, plan=None, contributions=None, members=None):
        """(Re)build the signer artifact; ``plan``/``contributions`` override certificate fields or bytes."""
        plan, contributions = dict(plan or {}), dict(contributions or {})
        bundles = {
            "plan.bundle.jsonl": plan.pop("bundle", None) or signed_bundle(
                plan.pop("name", PLAN_NAME), plan.pop("data", self.archives[902]), **plan),
            "contributions.bundle.jsonl": contributions.pop("bundle", None) or signed_bundle(
                contributions.pop("name", CONTRIBUTIONS_NAME), contributions.pop("data", self.archives[901]),
                **contributions),
        }
        self.archives[903] = archive(bundles if members is None else members)
        if hasattr(self, "lists"):
            self.lists[f"actions/runs/{RUN}/artifacts?name={ATTESTATIONS_NAME}"] = [
                self.artifact(903, ATTESTATIONS_NAME, "2026-11-28T10:05:50Z")]

    def verify_attestation(self, subject, bundle, *, signer_digest, source_digest):
        """Simulates gh: crypto binds the bundle to the subject bytes, then the CLI pins apply."""
        self.calls.append(("verify", Path(subject).name))
        self.verified.append((signer_digest, source_digest))
        signed = json.loads(Path(bundle).read_bytes())
        if signed["subject"][0]["digest"]["sha256"] != hashlib.sha256(Path(subject).read_bytes()).hexdigest():
            raise ValueError("no matching attestation for the subject digest")
        if (signed["certificate"]["buildSignerDigest"] != signer_digest
                or signed["certificate"]["sourceRepositoryDigest"] != source_digest):
            raise ValueError("certificate does not match the signer or source digest pins")
        return [{"attestation": {"bundle": {}}, "verificationResult": {
            "mediaType": "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
            "statement": {"_type": "https://in-toto.io/Statement/v1", "subject": signed["subject"],
                          "predicate_type": signed["predicate_type"], "predicate": {}},
            "signature": {"certificate": signed["certificate"]}}}]

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
        self.assertEqual({"source-impact-plan.json", "current-validation-contributions.json", "source.json",
                          "source-impact-plan.zip", "current-validation-contributions.zip",
                          "source-impact-plan.bundle.jsonl", "current-validation-contributions.bundle.jsonl"},
                         {path.name for path in self.destination.iterdir()})
        self.assertEqual(api.source_raw, (self.destination / "source-impact-plan.json").read_bytes())
        self.assertEqual(api.contributions_raw,
                         (self.destination / "current-validation-contributions.json").read_bytes())
        pointer = json.loads((self.destination / "source.json").read_text())
        self.assertEqual((RUN, ATTEMPT, TRUSTED, 1, 2), (pointer["runId"], pointer["runAttempt"],
                         pointer["trustedWorkflowSha"], pointer["gateJobId"], pointer["outerGateJobId"]))
        self.assertEqual(digest(api.archives[901]), pointer["contributions"]["artifactDigest"])
        self.assertEqual(4, pointer["recordJobId"])
        self.assertEqual(ATTESTATIONS_NAME, pointer["attestations"]["artifactName"])
        # Both subjects were natively verified online, then again while re-verifying the staged bundle,
        # always pinned to the trusted signer and the tested merge commit.
        self.assertEqual(4, len(api.verified))
        self.assertEqual({(TRUSTED, MERGE)}, set(api.verified))
        # N3: workflow references come from the final attempt itself.
        self.assertIn(("json", f"actions/runs/{RUN}/attempts/{ATTEMPT}"), api.calls)
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
        verifier = FakeAPI()
        pointer = scope.stage_merge_group_retained_validation(self.destination, self.plan_path, staged,
            repository_root=ROOT, environ=ENVIRON, trusted_workflow_sha=TRUSTED,
            source_run_id=RUN, source_run_attempt=ATTEMPT, verifier=verifier)
        self.assertEqual(2, len(verifier.verified))
        self.assertEqual(RUN, pointer["runId"])
        self.assertEqual({"impact-plan.json", "source-impact-plan.json", "current-validation-contributions.json",
                          "source.json", "source-impact-plan.zip", "current-validation-contributions.zip",
                          "source-impact-plan.bundle.jsonl", "current-validation-contributions.bundle.jsonl"},
                         {path.name for path in staged.iterdir()})
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
                # N3: the final attempt's own references decide, never the run-level object.
                api.responses[f"actions/runs/{RUN}/attempts/{ATTEMPT}"] = {**api.run, "referenced_workflows": references}
                self.lines.clear()
                self.assertRejected(api, "workflow")
        api = FakeAPI()
        api.responses[f"actions/runs/{RUN}"] = {**api.run, "referenced_workflows": []}
        self.lines.clear()
        self.assertEqual("true", self.discover(api)["reused"])

    def test_final_attempt_object_must_be_this_successful_attempt(self):
        for change in (dict(run_attempt=1), dict(id=RUN + 1), dict(conclusion="failure"), dict(event="push"),
                       dict(head_sha="0" * 40), dict(path=".github/workflows/promote.yml")):
            with self.subTest(change=change):
                api = FakeAPI()
                api.responses[f"actions/runs/{RUN}/attempts/{ATTEMPT}"] = {**api.run, **change}
                self.lines.clear()
                self.assertRejected(api, "attempt")

    # B1 defense in depth: exact association -----------------------------------------

    def sibling(self, number=38, **change):
        entry = copy.deepcopy(FakeAPI().run["pull_requests"][0])
        entry.update(number=number, url=f"https://api.github.com/repos/{REPO}/pulls/{number}", **change)
        return entry

    def test_sibling_pull_request_entry_is_rejected(self):
        # PR M (38) shares N's head branch: GitHub lists both on M's run.
        for requests in ([FakeAPI().run["pull_requests"][0], self.sibling()],
                         [self.sibling(), FakeAPI().run["pull_requests"][0]]):
            with self.subTest(order=[entry["number"] for entry in requests]):
                api = FakeAPI()
                api.responses[f"actions/runs/{RUN}"] = {**api.run, "pull_requests": requests}
                self.lines.clear()
                self.assertRejected(api, "association")

    def test_association_entry_must_be_main_based_from_this_head_branch(self):
        base = FakeAPI().run["pull_requests"][0]
        evil_base = {**base["base"], "ref": "attacker-base"}
        for entry in ({**base, "base": evil_base}, {**base, "head": {**base["head"], "ref": "other"}},
                      {**base, "head": {**base["head"], "sha": "0" * 40}},
                      {**base, "base": {**base["base"], "repo": pr_repository("x/y", 8)}},
                      {**base, "head": {**base["head"], "repo": pr_repository(REPO, 8)}},
                      {**base, "number": "37"}):
            with self.subTest(entry=entry):
                api = FakeAPI()
                api.responses[f"actions/runs/{RUN}"] = {**api.run, "pull_requests": [entry]}
                self.lines.clear()
                self.assertRejected(api, "association")

    def test_closed_sibling_run_listing_only_n_fails_its_attestation(self):
        # M (38) ran with an attacker base and was closed; its run now lists only N.
        # Its forged plan claims N's merge commit, but the protected signer attested
        # M's own merge ref and commit, so nothing it uploaded is authority.
        api = FakeAPI()
        api.sign(plan={"number": 38, "commit": "d" * 40}, contributions={"number": 38, "commit": "d" * 40})
        self.assertRejected(api, "attestation")
        # With the true commit but M's merge ref, the certificate still names M.
        self.lines.clear()
        api = FakeAPI()
        api.sign(plan={"number": 38}, contributions={"number": 38})
        self.assertRejected(api, "attestation")

    # B1: attestation binding ----------------------------------------------------------

    def test_plan_or_contributions_without_an_attestation_are_rejected(self):
        api = FakeAPI()
        api.lists[f"actions/runs/{RUN}/artifacts?name={ATTESTATIONS_NAME}"] = []
        self.assertRejected(api, "artifact-missing")
        for members in ({"plan.bundle.jsonl": b"{}"}, {"contributions.bundle.jsonl": b"{}"},
                        {"plan.bundle.jsonl": b"{}", "contributions.bundle.jsonl": b"{}", "x.jsonl": b"{}"}):
            with self.subTest(members=list(members)):
                api = FakeAPI()
                api.sign(members=members)
                self.lines.clear()
                self.assertRejected(api, "artifact-content")
        for field in ("plan", "contributions"):
            with self.subTest(field=field):
                api = FakeAPI()
                # A bundle signed over other bytes (e.g. the attacker's own upload) never verifies.
                api.sign(**{field: {"data": b"other bytes"}})
                self.lines.clear()
                self.assertRejected(api, "attestation")

    def test_attestation_identity_fields_are_exact(self):
        cases = {
            "workflow ref": dict(signer=f"https://github.com/{REPO}/.github/workflows/product-validation.yml@refs/pull/38/merge"),
            "caller workflow": dict(signer=f"https://github.com/{REPO}/.github/workflows/ci.yml@refs/pull/37/merge"),
            "workflow sha": dict(signer_digest="8" * 40),
            "run": dict(run=RUN + 1),
            "attempt": dict(attempt=1),
            "commit": dict(commit="d" * 40),
            "event": dict(trigger="merge_group"),
            "runner": dict(runner="self-hosted"),
            "repository": dict(repository_uri="https://github.com/x/codex-agent"),
            "subject name": dict(name="codex-agent-ci-plan-control-" + "2" * 40),
        }
        for field in ("plan", "contributions"):
            for label, change in cases.items():
                if label == "subject name" and field == "contributions":
                    change = dict(name=CONTRIBUTIONS_NAME[:-1] + "1")
                with self.subTest(field=field, case=label):
                    api = FakeAPI()
                    api.sign(**{field: change})
                    self.lines.clear()
                    self.assertRejected(api, "attestation")

    def test_attestation_rows_are_pinned_exactly(self):
        api = FakeAPI()
        good = api.verify_attestation
        arguments = dict(name=PLAN_NAME, digest=digest(api.archives[902]), trusted_workflow_sha=TRUSTED,
                         validation_commit=MERGE, pull_request=PR, run_id=RUN, run_attempt=ATTEMPT)
        with tempfile.TemporaryDirectory() as work:
            subject, bundle = Path(work) / "plan.zip", Path(work) / "plan.bundle.jsonl"
            subject.write_bytes(api.archives[902])
            bundle.write_bytes(signed_bundle(PLAN_NAME, api.archives[902]))
            rows = good(subject, bundle, signer_digest=TRUSTED, source_digest=MERGE)
            scope.require_attested_subject(rows, **arguments)
            mutations = (lambda r: r * 2, lambda r: [], lambda r: None,
                         lambda r: r[0]["verificationResult"]["statement"].update(predicate_type="x"),
                         lambda r: r[0]["verificationResult"]["statement"].update(predicateType="x"),
                         lambda r: r[0]["verificationResult"]["statement"]["subject"].append({}),
                         lambda r: r[0]["verificationResult"]["signature"]["certificate"].pop("buildConfigURI"),
                         lambda r: r[0]["verificationResult"]["signature"]["certificate"].update(
                             issuer="https://evil.invalid"),
                         lambda r: r[0]["verificationResult"].pop("signature"))
            for index, mutate in enumerate(mutations):
                with self.subTest(index=index):
                    value = copy.deepcopy(rows)
                    value = mutate(value) if index < 3 else (mutate(value), value)[1]
                    with self.assertRaises(scope.RetainedReuseRejected) as caught:
                        scope.require_attested_subject(value, **arguments)
                    self.assertEqual("attestation", caught.exception.reason)
            for verifier in (None, object()):
                with self.assertRaises(scope.RetainedReuseRejected) as caught:
                    scope.verify_retained_attestation(verifier, subject, bundle, **arguments)
                self.assertEqual("attestation", caught.exception.reason)

    def test_fake_gate_job_with_the_pinned_name_is_not_authority(self):
        # A caller ci.yml can name a job "product-validation / CI / merge-gate"; it
        # cannot produce the protected signer's attestation over its upload.
        api = FakeAPI()
        path = f"actions/runs/{RUN}/attempts/{ATTEMPT}/jobs"
        api.lists[path] = [job for job in api.lists[path] if job["name"] != scope.RETAINED_RECORD_JOB]
        self.assertRejected(api, "jobs")
        self.lines.clear()
        api = FakeAPI()
        api.lists[path].append(api.job(9, scope.RETAINED_GATE_JOB, GATE_START, GATE_END))
        self.assertRejected(api, "jobs")
        self.lines.clear()
        api = FakeAPI()
        api.sign(contributions={"signer": f"https://github.com/{REPO}/.github/workflows/ci.yml@refs/pull/37/merge"})
        self.assertRejected(api, "attestation")

    def test_signer_must_run_after_the_gate_and_upload_in_its_own_window(self):
        path = f"actions/runs/{RUN}/attempts/{ATTEMPT}/jobs"
        api = FakeAPI()
        api.lists[path][3] = {**api.lists[path][3], "started_at": "2026-11-28T10:04:00Z"}
        self.assertRejected(api, "jobs")
        for created in ("2026-11-28T10:05:00Z", "2026-11-28T10:06:01Z"):
            with self.subTest(created=created):
                api = FakeAPI()
                listing = f"actions/runs/{RUN}/artifacts?name={ATTESTATIONS_NAME}"
                api.lists[listing] = [{**api.lists[listing][0], "created_at": created}]
                self.lines.clear()
                self.assertRejected(api, "artifact-window")

    def test_unexpected_error_on_one_candidate_moves_to_the_next(self):
        # N4: an unexpected exception skips only that candidate; overall still fails closed.
        api = FakeAPI()
        listing = next(path for path in api.lists if path.startswith("actions/workflows/"))
        api.lists[listing].insert(0, {"id": RUN + 5, "conclusion": "success", "head_sha": HEAD})
        api.responses[f"actions/runs/{RUN + 5}"] = RuntimeError("transient")
        self.assertEqual("true", self.discover(api)["reused"])
        self.assertTrue(any(line.startswith(f"[route:merge-queue-reuse:error] run {RUN + 5}: ")
                            for line in self.lines), self.lines)
        self.lines.clear()
        __import__("shutil").rmtree(self.destination)
        api = FakeAPI()
        api.responses[f"actions/runs/{RUN}"] = RuntimeError("transient")
        self.assertRejected(api, "error")

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
        api.sign()
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
                         verifier=FakeAPI(), source_run_id=RUN, source_run_attempt=ATTEMPT)
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
        # A consistent swap of archive, file and pointer still lacks a valid attestation.
        for name in ("current-validation-contributions.zip", "current-validation-contributions.bundle.jsonl"):
            with self.subTest(name=name):
                path = bundle / name
                saved = path.read_bytes()
                path.write_bytes(saved + b" ")
                with self.assertRaises(scope.RetainedReuseRejected) as caught:
                    self.verify(bundle)
                self.assertEqual("bundle", caught.exception.reason)
                path.write_bytes(saved)
        with self.assertRaises(scope.RetainedReuseRejected) as caught:
            self.verify(bundle, verifier=None)
        self.assertEqual("attestation", caught.exception.reason)
        (bundle / "validation-receipt.json").write_text("{}")
        with self.assertRaises(scope.RetainedReuseRejected):
            self.verify(bundle)

    def test_bundle_reverification_reruns_the_native_attestation(self):
        bundle = self.staged()
        pointer_path = bundle / "source.json"
        pointer = json.loads(pointer_path.read_text())
        # Re-signing bytes for another PR's merge ref, recorded consistently, still fails.
        forged = signed_bundle(PLAN_NAME, (bundle / "source-impact-plan.zip").read_bytes(), number=38)
        (bundle / "source-impact-plan.bundle.jsonl").write_bytes(forged)
        pointer["plan"]["bundleSha256"] = digest(forged)
        pointer_path.write_text(json.dumps(pointer))
        with self.assertRaises(scope.RetainedReuseRejected) as caught:
            self.verify(bundle)
        self.assertEqual("attestation", caught.exception.reason)

    def test_stage_requires_a_merge_group_runner_and_fresh_destination(self):
        bundle = self.staged()
        staged = self.scratch / "staged"
        with self.assertRaises(scope.RetainedReuseRejected):
            scope.stage_merge_group_retained_validation(bundle, self.plan_path, staged, repository_root=ROOT,
                environ={**ENVIRON, "GITHUB_EVENT_NAME": "pull_request"}, trusted_workflow_sha=TRUSTED,
                source_run_id=RUN, source_run_attempt=ATTEMPT, verifier=FakeAPI())
        staged.mkdir()
        with self.assertRaises(scope.RetainedReuseRejected):
            scope.stage_merge_group_retained_validation(bundle, self.plan_path, staged, repository_root=ROOT,
                environ=ENVIRON, trusted_workflow_sha=TRUSTED, source_run_id=RUN, source_run_attempt=ATTEMPT,
                verifier=FakeAPI())
        staged.rmdir()
        # Without an injected verifier the gate uses native gh with its token; none means no reuse.
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

    def test_native_attestation_verification_pins_signer_source_and_issuer(self):
        import subprocess
        reads = scope.GitHubReads("secret-token")
        completed = subprocess.CompletedProcess([], 0, stdout=b"[]", stderr=b"")
        with mock.patch("subprocess.run", return_value=completed) as run:
            self.assertEqual([], reads.verify_attestation("/w/a.zip", "/w/a.bundle.jsonl",
                                                          signer_digest=TRUSTED, source_digest=MERGE))
        command = run.call_args.args[0]
        self.assertEqual(["gh", "attestation", "verify", "/w/a.zip", "--bundle", "/w/a.bundle.jsonl",
                          "--repo", REPO, "--signer-workflow", f"{REPO}/.github/workflows/product-validation.yml",
                          "--signer-digest", TRUSTED, "--source-digest", MERGE,
                          "--cert-oidc-issuer", "https://token.actions.githubusercontent.com",
                          "--deny-self-hosted-runners", "--format", "json"], command)
        self.assertNotIn("secret-token", " ".join(command))
        self.assertEqual("secret-token", run.call_args.kwargs["env"]["GH_TOKEN"])
        with self.assertRaises(ValueError):
            reads.verify_attestation("/w/a.zip", "/w/b", signer_digest="x", source_digest=MERGE)
        startup = subprocess.CompletedProcess([], 1, stdout=b"", stderr=scope._SIGSTORE_STARTUP[0])
        invalid = subprocess.CompletedProcess([], 1, stdout=b"", stderr=b"verification failed")
        with mock.patch("subprocess.run", side_effect=[startup, completed]) as run, mock.patch("time.sleep"):
            self.assertEqual([], reads.verify_attestation("/w/a.zip", "/w/b", signer_digest=TRUSTED,
                                                          source_digest=MERGE))
        self.assertEqual(2, run.call_count)
        with mock.patch("subprocess.run", side_effect=[invalid, completed]) as run, mock.patch("time.sleep"):
            with self.assertRaises(ValueError):
                reads.verify_attestation("/w/a.zip", "/w/b", signer_digest=TRUSTED, source_digest=MERGE)
        self.assertEqual(1, run.call_count)


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
            # N1: the same three-part retained decision as the re-verify steps.
            self.assertTrue(condition.endswith(
                "&& !(github.event_name == 'merge_group' && needs.plan.outputs.validation_reused == 'true' "
                "&& needs.plan.outputs.validation_reuse_kind == 'retained') }}"))
            self.assertFalse(self.evaluate(condition, self.values(event="merge_group", reused="true",
                                                                  kind="retained")))
            # Inconsistent combinations keep the schema-1 path (and the consistency step fails the gate).
            for event, reused in (("pull_request", "true"), ("merge_group", "false")):
                self.assertTrue(self.evaluate(condition, self.values(event=event, reused=reused, kind="retained")))
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
        # N2: a gate re-run uploads under its own attempt, never colliding with overwrite: false.
        self.assertIn("name: codex-agent-merge-group-retained-validation-${{ needs.plan.outputs.validation_tree }}"
                      "-attempt-${{ github.run_attempt }}\n", upload)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", verify)
        self.assertIn("bash .github/actions/restore-reuse-qualification/install-gh.sh",
                      self.step(self.gate, "      - id: retained-native-gh\n"))
        self.assertIn("overwrite: false", upload)
        self.assertNotIn("codex-agent-ci-validation-", verify + upload)
        self.assertLess(self.gate.index(verify_marker), self.gate.index(upload_marker))
        self.assertLess(self.gate.index("      - if: ${{ !inputs.fullReuseAcceptanceOnly }}\n"
                                        "        uses: actions/download-artifact@"), self.gate.index(verify_marker))

    def run_consistency(self, event, reused, kind):
        import subprocess
        step = self.step(self.gate, "      - name: Require a consistent merge-group retained reuse decision\n")
        script = textwrap.dedent(step.split("        run: |\n", 1)[1])
        return subprocess.run(["bash", "-c", script], env={"PATH": os.environ["PATH"], "GITHUB_EVENT_NAME": event,
                              "REUSED": reused, "KIND": kind}, capture_output=True, text=True).returncode

    def test_inconsistent_retained_reuse_decision_fails_the_gate(self):
        # Right after the readiness gate and before any schema-1 or retained step acts.
        self.assertLess(self.gate.index("Require readiness and successful prerequisites"),
                        self.gate.index("Require a consistent merge-group retained reuse decision"))
        self.assertLess(self.gate.index("Require a consistent merge-group retained reuse decision"),
                        self.gate.index("Require an exact receipt set"))
        for event, reused, kind, expected in (
                ("merge_group", "true", "retained", 0), ("merge_group", "true", "", 0),
                ("merge_group", "false", "", 0), ("pull_request", "false", "", 0), ("pull_request", "true", "", 0),
                ("merge_group", "false", "retained", 1), ("merge_group", "", "retained", 1),
                ("pull_request", "true", "retained", 1), ("merge_group", "true", "schema-1", 1),
                ("merge_group", "true", "retained\n", 1)):
            with self.subTest(event=event, reused=reused, kind=kind):
                self.assertEqual(expected, 0 if self.run_consistency(event, reused, kind) == 0 else 1)

    def test_plan_installs_native_gh_only_for_merge_group_reuse(self):
        step = self.step(self.plan, "      - id: retained-native-gh\n")
        self.assertIn("github.event_name == 'merge_group'", step)
        self.assertIn("continue-on-error: true", step)
        self.assertLess(self.plan.index("- id: retained-native-gh"), self.plan.index("- id: validation-reuse"))
        self.assertIn("plan_control_digest: ${{ steps.upload_plan_control.outputs.artifact-digest }}", self.plan)
        self.assertIn("retained_contributions_digest: ${{ steps.upload_retained_contributions.outputs.artifact-digest }}",
                      self.gate.split("\n    steps:\n", 1)[0])


class RetainedValidationSignerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workflow = (ROOT / ".github/workflows/product-validation.yml").read_text()
        assert workflow.count("\n  retained-validation-record:\n") == 1
        cls.workflow = workflow
        cls.signer = re.split(r"\n  [a-z][a-z0-9-]*:\n",
                              workflow.split("\n  retained-validation-record:\n", 1)[1])[0]

    def test_signer_never_executes_the_tested_tree(self):
        signer = self.signer
        self.assertIn("    permissions:\n      actions: read\n      contents: read\n"
                      "      id-token: write\n      attestations: write\n", signer)
        for forbidden in ("actions/checkout", "actions/cache", "uses: ./", "secrets.", "PYTHONPATH",
                          "working-directory", "sys.path", "ci/", "download-artifact"):
            self.assertNotIn(forbidden, signer)
        uses = [line.strip() for line in signer.splitlines() if line.strip().startswith("uses:")]
        self.assertEqual(["uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6 # v4.2.2"] * 2
                         + ["uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1"], uses)
        self.assertIn("python3 -I -B - <<'PY'", signer)
        self.assertIn("    needs: [plan, merge-gate]\n", signer)
        steps = signer.split("\n      - ")[1:]
        # Publication never decides a result: only the never-failing decision step lacks continue-on-error.
        self.assertEqual(len(steps) - 1, signer.count("continue-on-error: true"))
        self.assertEqual(2, signer.count("create-storage-record: false"))
        # Nothing waits on the signer.
        self.assertNotIn("needs.retained-validation-record", self.workflow)
        self.assertFalse(re.search(r"needs: \[[^\]]*retained-validation-record", self.workflow))

    def test_signer_signs_only_api_confirmed_digests_of_a_protected_pr_publication(self):
        signer = self.signer
        self.assertIn("github.event_name == 'pull_request'", signer)
        self.assertIn("needs.merge-gate.result == 'success'", signer)
        for line in ("PLAN_DIGEST: ${{ needs.plan.outputs.plan_control_digest }}",
                     "CONTRIBUTIONS_DIGEST: ${{ needs.merge-gate.outputs.retained_contributions_digest }}",
                     "NATIVE_WORKFLOW_SHA: ${{ fromJSON(toJSON(job)).workflow_sha }}",
                     "subject-name: ${{ steps.publication.outputs.plan_name }}",
                     "subject-digest: sha256:${{ steps.publication.outputs.plan_digest }}",
                     "subject-name: ${{ steps.publication.outputs.contributions_name }}",
                     "subject-digest: sha256:${{ steps.publication.outputs.contributions_digest }}",
                     "name: codex-agent-retained-validation-attestations-${{ steps.publication.outputs.tree }}"
                     "-attempt-${{ steps.publication.outputs.attempt }}"):
            self.assertIn(line, signer)
        self.assertEqual(scope.retained_attestations_name(TREE, ATTEMPT), ATTESTATIONS_NAME)
        self.assertEqual(scope.RETAINED_RECORD_JOB, "product-validation / retained-validation-record")

    def run_publication(self, **overrides):
        script = textwrap.dedent(self.signer.split("python3 -I -B - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        tree, plan_digest, contributions_digest = TREE, "a" * 64, "b" * 64
        environ = dict(PUBLISHER_SHA=TRUSTED, NATIVE_WORKFLOW_SHA=TRUSTED, NATIVE_WORKFLOW_REPOSITORY=REPO,
                       NATIVE_WORKFLOW_PATH=".github/workflows/product-validation.yml", FORK="false", TREE=tree,
                       PLAN_DIGEST=plan_digest, CONTRIBUTIONS_DIGEST=contributions_digest, GITHUB_TOKEN="t",
                       GITHUB_REPOSITORY=REPO, GITHUB_EVENT_NAME="pull_request", GITHUB_RUN_ATTEMPT=str(ATTEMPT),
                       GITHUB_RUN_ID=str(RUN))
        listed = overrides.pop("listed", None)
        environ.update(overrides)

        def respond(request, timeout):
            name = request.full_url.split("name=", 1)[1]
            value = "sha256:" + (plan_digest if "plan-control" in name else contributions_digest)
            items = listed(name, value) if listed else [
                {"name": name, "digest": value, "expired": False, "workflow_run": {"id": RUN}}]
            return io.BytesIO(json.dumps({"artifacts": items}).encode())

        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch) / "output"
            environ["GITHUB_OUTPUT"] = str(output)
            with mock.patch.dict(os.environ, environ, clear=True), \
                    mock.patch("urllib.request.urlopen", side_effect=respond):
                exec(compile(script, "<publication>", "exec"), {"__name__": "__main__"})
            return dict(line.split("=", 1) for line in output.read_text().splitlines())

    def test_publication_decision_is_exact_and_never_fails(self):
        outputs = self.run_publication()
        self.assertEqual({"publish": "true", "plan_name": PLAN_NAME, "plan_digest": "a" * 64,
                          "contributions_name": CONTRIBUTIONS_NAME, "contributions_digest": "b" * 64,
                          "tree": TREE, "attempt": str(ATTEMPT)}, outputs)
        for overrides in (dict(NATIVE_WORKFLOW_SHA="8" * 40), dict(FORK="true"), dict(GITHUB_EVENT_NAME="merge_group"),
                          dict(NATIVE_WORKFLOW_PATH=".github/workflows/ci.yml"), dict(GITHUB_REPOSITORY="x/y"),
                          dict(PLAN_DIGEST=""), dict(CONTRIBUTIONS_DIGEST="sha256:" + "b" * 64),
                          dict(TREE="1" * 39 + "\n"), dict(GITHUB_RUN_ATTEMPT="0"),
                          dict(listed=lambda name, value: []),
                          dict(listed=lambda name, value: [{"name": name, "digest": "sha256:" + "c" * 64,
                                                            "expired": False, "workflow_run": {"id": RUN}}]),
                          dict(listed=lambda name, value: [{"name": name, "digest": value, "expired": False,
                                                            "workflow_run": {"id": RUN + 1}}]),
                          dict(listed=lambda name, value: [{"name": name, "digest": value, "expired": False,
                                                            "workflow_run": {"id": RUN}}] * 2)):
            with self.subTest(overrides=list(overrides)):
                self.assertEqual({"publish": "false"}, self.run_publication(**overrides))


# Every job of product-validation.yml that may mint an OIDC token, and why that
# token can never sign for code of the tested tree (security review I1). A
# certificate's SAN names only the workflow file, so any job here signs as
# product-validation.yml@reuse-authority unless it is a reusable-workflow call.
ID_TOKEN_JOBS = {
    # Signs only API-confirmed digests; no checkout and no repository file runs.
    "retained-validation-record": "no-tested-code",
    # The tested tree is checked out as data only; the protected publisher's code runs isolated.
    "workflow-source-record": "protected-source",
    # Reusable-workflow calls: their jobs sign as the called workflow, not as product-validation.yml.
    "android-runtime-evidence": "reusable-call",
    **{f"sdk-checkpoint-{index}": "reusable-call" for index in (4, 6, 7, 8, 9, 10)},
    "sdk-core-binary-wave": "reusable-call",
    "sdk-android-validation-result": "reusable-call",
    "sdk-android-metadata-result": "reusable-call",
}
_PINNED_ACTIONS = {
    "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6 # v4.2.2",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1",
    "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1",
    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
}
# Anything in a run script that could execute or source a file of the checkout.
_REPOSITORY_EXECUTION = re.compile(
    r"(?:^|[\s;&|('\"])(?:\./|ci/|\.github/|tests/|bash\s+[^-\s]|sh\s+[^-\s]|source\s|\.\s+\S|make\b|"
    r"gradlew|npm\b|npx\b|pip\b|python3?\s+(?!-I\s+-B\s+-\s))|PYTHONPATH|sys\.path|working-directory")


def workflow_jobs(text):
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([a-z][a-z0-9-]*):\n", "\n" + body)
    return dict(zip(parts[1::2], parts[2::2]))


def job_permissions(job):
    block = re.search(r"(?m)^    permissions:\n((?:      .*\n)*)", job)
    return dict(line.strip().split(": ", 1) for line in block[1].splitlines()) if block else {}


def job_steps(job):
    steps = job.split("\n    steps:\n", 1)
    return [] if len(steps) == 1 else ["      - " + step for step in steps[1].split("\n      - ")[1:]]


def step_uses(step):
    return [re.sub(r"^(?:-\s*)?uses:\s*", "", line.strip()) for line in step.splitlines()
            if re.match(r"^\s*(?:-\s*)?uses:\s", line)]


def run_script(step):
    """A step's shell script without its whole-line comments."""
    script = step.split("        run: |\n", 1)[1] if "        run: |\n" in step else (
        re.search(r"(?m)^        run: (.+)$", step) or [None, ""])[1]
    return "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))


def id_token_violations(text):
    """Every reason a job holding ``id-token: write`` could sign for tested-tree code."""
    jobs, violations = workflow_jobs(text), []
    top = text.split("\njobs:\n", 1)[0]
    if "id-token" in top or "attestations" in top:
        violations.append(("<workflow>", "workflow-level permissions grant a token"))
    granted = {name for name, job in jobs.items() if job_permissions(job).get("id-token") == "write"}
    for name in sorted(granted - set(ID_TOKEN_JOBS)):
        violations.append((name, "new id-token job not on the reviewed allowlist"))
    for name in sorted(granted & set(ID_TOKEN_JOBS)):
        job, kind = jobs[name], ID_TOKEN_JOBS[name]
        caller = re.search(r"(?m)^    uses: (\S+)$", job)
        if kind == "reusable-call":
            target = caller[1] if caller else ""
            local = re.fullmatch(r"\./\.github/workflows/([a-z0-9-]+\.yml)", target)
            remote = re.fullmatch(r"codex-agent-labs/codex-agent/\.github/workflows/([a-z0-9-]+\.yml)@reuse-authority",
                                  target)
            called = (local or remote)[1] if (local or remote) else None
            if called is None or called == "product-validation.yml" or "\n    steps:\n" in job:
                violations.append((name, "is not a call to another reviewed workflow"))
            continue
        if caller is not None:
            violations.append((name, "signing job unexpectedly calls a workflow"))
        for step in job_steps(job):
            for action in step_uses(step):
                if action not in _PINNED_ACTIONS:
                    violations.append((name, f"runs an unreviewed or local action {action}"))
                elif action.startswith("actions/checkout@") and kind != "protected-source":
                    violations.append((name, "checks out a tree"))
            if re.search(r"(?m)^\s*(?:-\s*)?(?:shell|working-directory):", step):
                violations.append((name, "changes the shell or working directory"))
            script = run_script(step)
            if kind == "protected-source":
                # Only the protected publisher's checkout executes, isolated; the tested tree is data.
                script = re.sub(r"python3 -I -B protected-source/[A-Za-z0-9_./-]+\.py", "PROTECTED",
                                script).replace("--source tested-tree", "--source DATA")
                if re.search(r"(?m)^\s+path: tested-tree$", step) and re.search(r"(?m)^\s+ref:", step):
                    violations.append((name, "tested-tree checkout pins a ref"))
                if re.search(r"(?m)^\s+path: protected-source$", step) and (
                        "ref: ${{ fromJSON(toJSON(job)).workflow_sha }}" not in step
                        or "repository: ${{ fromJSON(toJSON(job)).workflow_repository }}" not in step):
                    violations.append((name, "protected checkout is not the job's own workflow commit"))
                if "tested-tree" in script:
                    violations.append((name, "a run step touches the tested tree"))
            if _REPOSITORY_EXECUTION.search(script) or "secrets." in step or "actions/cache" in step:
                violations.append((name, "a run step may execute repository code"))
    return violations


class IdTokenSignerInvariantTest(unittest.TestCase):
    """I1: no job that can sign as product-validation.yml ever executes the tested tree."""

    @classmethod
    def setUpClass(cls):
        cls.text = (ROOT / ".github/workflows/product-validation.yml").read_text()

    def test_every_id_token_job_is_reviewed_and_cannot_run_tested_code(self):
        self.assertEqual([], id_token_violations(self.text))
        jobs = workflow_jobs(self.text)
        granted = {name for name, job in jobs.items() if job_permissions(job).get("id-token") == "write"}
        self.assertEqual(set(ID_TOKEN_JOBS), granted)
        # Only the two own-identity signers hold attestations without delegating to another workflow.
        signers = {name for name in granted if "\n    steps:\n" in jobs[name]}
        self.assertEqual({"retained-validation-record", "workflow-source-record"}, signers)
        # Same SAN, distinct subjects: the source-check signer only ever attests its own record file,
        # never a name the merge-queue verifier accepts.
        source = jobs["workflow-source-record"]
        self.assertIn("subject-path: ${{ runner.temp }}/source-check-record/source-checks.json", source)
        self.assertNotIn("subject-name", source)
        self.assertEqual(2, jobs["retained-validation-record"].count("subject-name: "))

    def test_detector_flags_new_or_widened_signers(self):
        def add(job):
            return self.text.rstrip("\n") + "\n" + textwrap.indent(textwrap.dedent(job).strip("\n"), "  ") + "\n"

        fresh = """
            evil-signer:
              runs-on: ubuntu-24.04
              permissions:
                id-token: write
              steps:
                - run: echo hi
            """
        self.assertIn(("evil-signer", "new id-token job not on the reviewed allowlist"), id_token_violations(add(fresh)))
        record = workflow_jobs(self.text)["retained-validation-record"]
        mutations = {
            "checkout": record.replace("    steps:\n", "    steps:\n      - uses: actions/checkout@"
                                       "3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1\n", 1),
            "local action": record.replace("    steps:\n", "    steps:\n      - uses: ./.github/actions/x\n", 1),
            "ci script": record.replace("    steps:\n", "    steps:\n      - run: python3 ci/impact.py\n", 1),
            "repo shell": record.replace("    steps:\n", "    steps:\n      - run: bash .github/x.sh\n", 1),
            "relative exec": record.replace("    steps:\n", "    steps:\n      - run: ./gradlew check\n", 1),
            "pythonpath": record.replace("    steps:\n", "    steps:\n      - run: PYTHONPATH=. python3 -c 1\n", 1),
            "working dir": record.replace("    steps:\n", "    steps:\n      - working-directory: x\n"
                                          "        run: echo\n", 1),
        }
        for label, job in mutations.items():
            with self.subTest(label=label):
                self.assertNotEqual([], id_token_violations(self.text.replace(record, job, 1)))
        caller = workflow_jobs(self.text)["sdk-checkpoint-4"]
        for target in ("codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@reuse-authority",
                       "./.github/workflows/product-validation.yml", "evil/repo/.github/workflows/x.yml@main"):
            with self.subTest(target=target):
                job = re.sub(r"(?m)^    uses: \S+$", "    uses: " + target, caller, count=1)
                self.assertNotEqual([], id_token_violations(self.text.replace(caller, job, 1)))
        source = workflow_jobs(self.text)["workflow-source-record"]
        for old, new in (("python3 -I -B protected-source/", "python3 -B tested-tree/"),
                         ("          path: tested-tree\n", "          path: tested-tree\n          ref: main\n")):
            with self.subTest(old=old):
                self.assertIn(old, source)
                self.assertNotEqual([], id_token_violations(self.text.replace(source, source.replace(old, new), 1)))
        top = self.text.replace("permissions:\n  actions: read\n", "permissions:\n  id-token: write\n  actions: read\n", 1)
        self.assertIn(("<workflow>", "workflow-level permissions grant a token"), id_token_violations(top))


if __name__ == "__main__":
    unittest.main()
