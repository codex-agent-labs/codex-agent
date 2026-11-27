"""Exact-input SDK parity reuse within the consumer's PR scope (9.5.0)."""

from copy import deepcopy
import io
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci import sdk_completion as completion  # noqa: E402
import producer_scope  # noqa: E402
import sdk_parity_reuse as reuse  # noqa: E402
from products import selection  # noqa: E402
from products.inventory import canonical_json_bytes  # noqa: E402
from products.registry import PHASE_INSTANCE_IDS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REPO = producer_scope.REPOSITORY
API = "https://api.github.com/repos/" + REPO
PUBLISHER, TREE, COMMIT = "d" * 40, "b" * 40, "a" * 40
RUN_HEAD, BASE_SHA, PR_HEAD, CONSUMER = "9" * 40, "8" * 40, "c" * 40, "e" * 40
CONSUMER_HEAD = "f" * 40
RUN = 500
TREES = {"ci": "3" * 40, ".github": "4" * 40}
ENVIRONMENT = {"GITHUB_REPOSITORY": REPO, "GITHUB_EVENT_NAME": "pull_request",
               "GITHUB_REF": "refs/pull/33/merge", "GITHUB_SHA": CONSUMER}
JOB_WINDOW = ("2026-11-20T12:00:00Z", "2026-11-20T13:00:00Z")


def phase(identity):
    return {"product": identity.product, "component": identity.component, "phase": identity.phase,
            "target": identity.target, "state": "retained", "buildKey": "sha256:" + "a" * 64,
            "receiptSha256": "sha256:" + "b" * 64, "objectSha256": "sha256:" + "c" * 64,
            "source": None, "transportSource": None, "misses": []}


ROWS = [phase(item) for item in sorted(PHASE_INSTANCE_IDS)]


def plan_archive(**changes):
    plan = {"repository": REPO, "event": "pull_request", "pullRequest": 33,
            "validationCommit": COMMIT, "validationTree": TREE, **changes}
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as bundle:
        bundle.writestr("impact-plan.json", canonical_json_bytes(plan))
    return stream.getvalue()


class GitHub:
    """Read-only canned API with mutable fixture state."""

    def __init__(self):
        repo = {"full_name": REPO, "fork": False}
        self.pull = {"number": 33, "state": "open", "merged": False,
                     "head": {"ref": "phase95/0", "sha": PR_HEAD, "repo": dict(repo)},
                     "base": {"ref": "main", "repo": dict(repo)}}
        self.runs = [{"id": RUN, "run_attempt": 2, "event": "pull_request", "path": producer_scope.CI_WORKFLOW,
                      "head_branch": "phase95/0", "head_sha": RUN_HEAD,
                      "pull_requests": [{"number": 33, "base": {"sha": BASE_SHA, "ref": "main"},
                                         "head": {"sha": RUN_HEAD, "ref": "phase95/0"}}],
                      "repository": dict(repo), "head_repository": dict(repo)}]
        self.attempt_runs = {}
        self.artifacts = [
            {"id": 71, "name": reuse.PARITY_PREFIX + TREE, "expired": False, "workflow_run": {"id": RUN},
             "digest": "sha256:" + "7" * 64, "created_at": "2026-11-20T12:30:00Z"},
            {"id": 72, "name": reuse.PLAN_PREFIX + TREE, "expired": False, "workflow_run": {"id": RUN},
             "digest": "sha256:" + "8" * 64}]
        self.jobs = {2: [self.job("success")], 1: []}
        self.plan = plan_archive()
        self.tested = {"sha": COMMIT, "tree": {"sha": TREE}, "parents": [{"sha": BASE_SHA}, {"sha": RUN_HEAD}]}
        self.association = {
            "pulls/33": self.pull,
            f"compare/{RUN_HEAD}...{PR_HEAD}?per_page=1": self.compare(RUN_HEAD),
            f"compare/{BASE_SHA}...main?per_page=1": self.compare(BASE_SHA)}
        self.trees = {CONSUMER: dict(TREES), TREE: dict(TREES), RUN_HEAD: dict(TREES), CONSUMER_HEAD: dict(TREES)}
        self.merged = TREE
        self.merges = []
        self.reads = []

    @staticmethod
    def compare(ancestor, *, behind=0, status="ahead"):
        return {"status": status, "behind_by": behind, "base_commit": {"sha": ancestor},
                "merge_base_commit": {"sha": ancestor}}

    def job(self, conclusion, window=JOB_WINDOW):
        return {"id": 90, "name": reuse.PARITY_JOB, "status": "completed", "conclusion": conclusion,
                "run_id": RUN, "head_sha": RUN_HEAD, "started_at": window[0], "completed_at": window[1]}

    def association_fetch(self, path):
        self.reads.append(path)
        if path not in self.association:
            raise AssertionError(path)
        return deepcopy(self.association[path])

    def merge_tree(self, base, head, tree):
        self.merges.append((base, head, tree))
        if self.merged != tree:
            raise producer_scope.ScopeRejected("merge-tree", "fixture merge differs")

    def control_trees(self, revision):
        if revision not in self.trees:
            raise producer_scope.ScopeRejected("control-tree", f"no tree for {revision}")
        return deepcopy(self.trees[revision])

    def api_json(self, url):
        self.reads.append(url)
        if url == f"{API}/pulls/33":
            return deepcopy(self.pull)
        match = re.fullmatch(re.escape(f"{API}/actions/runs/{RUN}/attempts/") + r"([0-9]+)", url)
        if match:
            attempt = int(match.group(1))
            return deepcopy(self.attempt_runs.get(attempt, {**self.runs[0], "run_attempt": attempt}))
        if url == f"{API}/git/commits/{COMMIT}":
            return deepcopy(self.tested)
        if url.startswith(f"{API}/actions/workflows/ci.yml/runs?"):
            self.query = url
            return {"workflow_runs": deepcopy(self.runs)}
        if url == f"{API}/actions/runs/{RUN}/artifacts?per_page=100":
            return {"artifacts": deepcopy(self.artifacts)}
        raise AssertionError(url)

    def list_jobs(self, url):
        attempt = int(re.search(r"/attempts/([0-9]+)/jobs$", url).group(1))
        return deepcopy(self.jobs.get(attempt, []))

    def download(self, artifact):
        self.assertion = artifact
        if artifact["id"] != 72:
            raise AssertionError("only the plan control is downloaded during discovery")
        return self.plan

    def candidates(self, rejected=None):
        return [policy for policy, _ in reuse.candidates(33, current_run=RUN + 10, trusted_workflow_sha=PUBLISHER,
            api_json=self.api_json, jobs=self.list_jobs, download=self.download,
            association_fetch=self.association_fetch, consumer=producer_scope.consumer_scope(ENVIRONMENT),
            reject=(rejected.append if rejected is not None else lambda reason: None))]


class CandidateTest(unittest.TestCase):
    def test_same_pr_successful_parity_is_proposed_with_its_exact_identity(self):
        github = GitHub()
        policy, = github.candidates()
        self.assertEqual({"schemaVersion": 1, "kind": "completed-sdk-parity", "producer": {
            "repository": REPO, "workflowPath": producer_scope.CI_WORKFLOW, "commit": COMMIT, "tree": TREE,
            "event": "pull_request", "pullRequest": 33, "runId": RUN, "runAttempt": 2},
            "workflowSha": PUBLISHER, "jobId": 90, "artifactId": 71, "artifactSha256": "sha256:" + "7" * 64},
            policy)
        self.assertIn("branch=phase95%2F0", github.query)
        self.assertIn("event=pull_request", github.query)

    def test_wrong_attempt_is_never_used(self):
        github = GitHub()
        github.jobs = {2: [github.job("success", ("2026-11-20T14:00:00Z", "2026-11-20T15:00:00Z"))],
                       1: [github.job("success")]}
        policy, = github.candidates()
        self.assertEqual(1, policy["producer"]["runAttempt"])  # the attempt whose window holds the upload
        github.jobs = {2: [github.job("success", ("2026-11-20T14:00:00Z", "2026-11-20T15:00:00Z"))], 1: []}
        self.assertEqual([], github.candidates())

    def test_failed_expired_or_out_of_window_results_are_rejected(self):
        cases = {
            "failed": lambda github: github.jobs.update({2: [github.job("failure")]}),
            "expired": lambda github: github.artifacts[0].update(expired=True),
            "plan expired": lambda github: github.artifacts[1].update(expired=True),
            "window": lambda github: github.artifacts[0].update(created_at="2026-11-20T13:00:01Z"),
            "ambiguous": lambda github: github.artifacts.append({**github.artifacts[0], "id": 73}),
        }
        for name, change in cases.items():
            with self.subTest(name):
                github = GitHub()
                change(github)
                rejected = []
                self.assertEqual([], github.candidates(rejected))
                self.assertEqual(1, len(rejected))

    def test_foreign_fork_or_unrelated_pr_results_are_rejected(self):
        cases = {
            "other branch": lambda github: github.runs[0].update(head_branch="someone-else"),
            "fork run": lambda github: github.runs[0].update(head_repository={"full_name": "x/y", "fork": True}),
            "merge group": lambda github: github.runs[0].update(event="merge_group"),
            "other workflow": lambda github: github.runs[0].update(path=".github/workflows/other.yml"),
            "other PR plan": lambda github: setattr(github, "plan", plan_archive(pullRequest=34)),
            "other tree plan": lambda github: setattr(github, "plan", plan_archive(validationTree="c" * 40)),
            "later run": lambda github: github.runs[0].update(id=RUN + 20),
        }
        for name, change in cases.items():
            with self.subTest(name):
                github = GitHub()
                change(github)
                self.assertEqual([], github.candidates())
        github = GitHub()
        github.pull["head"]["repo"] = {"full_name": "fork/codex-agent", "fork": True}
        with self.assertRaises(producer_scope.ScopeRejected):
            github.candidates()

    def test_admit_runs_t1_to_t6_on_fresh_attempt_reads(self):
        # I1: producer_scope.admit gates every proposal (T2 workflow, T3 event,
        # exact attempt/job identity, verified PR-N binding).
        cases = {
            "attempt path": lambda github: github.attempt_runs.update({2: {**github.runs[0], "path":
                                                                          ".github/workflows/other.yml"}}),
            "attempt event": lambda github: github.attempt_runs.update({2: {**github.runs[0], "event": "push"}}),
            "attempt fork": lambda github: github.attempt_runs.update({2: {**github.runs[0], "head_repository":
                                                                          {"full_name": REPO, "fork": True}}}),
            "job of another head": lambda github: github.jobs[2][0].update(head_sha="1" * 40),
            "artifact of another run": lambda github: github.artifacts[0].update(workflow_run={"id": RUN + 1}),
            "tested tree": lambda github: github.tested["tree"].update(sha="1" * 40),
            "force-pushed head": lambda github: github.association.update({
                f"compare/{RUN_HEAD}...{PR_HEAD}?per_page=1": github.compare(PR_HEAD, behind=2, status="diverged")}),
            "retargeted base": lambda github: github.runs[0]["pull_requests"][0]["base"].update(ref="evil-base"),
            "base off main": lambda github: github.association.update({
                f"compare/{BASE_SHA}...main?per_page=1": github.compare("1" * 40, behind=1, status="diverged")}),
        }
        for name, change in cases.items():
            with self.subTest(name):
                github = GitHub()
                change(github)
                rejected = []
                self.assertEqual([], github.candidates(rejected))
                self.assertEqual(1, len(rejected), rejected)
        github = GitHub()
        github.candidates()
        self.assertIn(f"{API}/actions/runs/{RUN}/attempts/2", github.reads)
        self.assertIn(f"compare/{RUN_HEAD}...{PR_HEAD}?per_page=1", github.reads)


class ScopeTest(unittest.TestCase):
    def environment(self, event, ref):
        return {"GITHUB_REPOSITORY": REPO, "GITHUB_EVENT_NAME": event, "GITHUB_REF": ref, "GITHUB_SHA": "e" * 40}

    def test_pull_request_and_merge_queue_scope(self):
        plan = {"repository": REPO, "event": "pull_request", "pullRequest": 33, "validationCommit": "e" * 40}
        consumer = {"kind": "ci", "producer": {"event": "pull_request", "pullRequest": 33, "commit": "e" * 40}}
        self.assertEqual(33, reuse.reuse_scope(plan, consumer, self.environment("pull_request", "refs/pull/33/merge")))
        queue = {**plan, "event": "merge_group"}
        queued = {"kind": "ci", "producer": {"event": "merge_group", "pullRequest": None, "commit": "e" * 40}}
        ref = f"refs/heads/gh-readonly-queue/main/pr-33-{'f' * 40}"
        self.assertEqual(33, reuse.reuse_scope(queue, queued, self.environment("merge_group", ref)))
        with self.assertRaises(producer_scope.ScopeRejected):
            reuse.reuse_scope(queue, queued, self.environment("merge_group", ref.replace("pr-33", "pr-34")))
        with self.assertRaises(producer_scope.ScopeRejected):
            reuse.reuse_scope(plan, consumer, self.environment("pull_request", "refs/pull/34/merge"))


def parity_archive(path, originals):
    from products.registry import NATIVE_BINDINGS
    names = {"canonical-api.json", "canonical-coverage.json", "binding-obligations-m11.json",
             *(name + "-parity.json" for name in (*NATIVE_BINDINGS, "kotlin", "java",
                                                   "javascript-typescript", "swift", "objective-c", "c-abi"))}
    evidence = {name: canonical_json_bytes({"fixture": name}) for name in names}
    digest = lambda value: completion.sha256_bytes(value).removeprefix("sha256:")
    report = dict(schemaVersion=2, phase="M11", result="passed", capabilityCount=556, languageCount=11,
                  scenarioCount=14, active=6104, pending=0, excluded=12, satisfied=6104, missing=0,
                  canonicalApiSha256=digest(evidence["canonical-api.json"]),
                  canonicalCoverageSha256=digest(evidence["canonical-coverage.json"]),
                  evidenceFiles=[dict(path=name, bytes=len(raw), sha256=digest(raw))
                                 for name, raw in sorted(evidence.items())])
    with zipfile.ZipFile(path, "w") as zipped:
        for name, raw in evidence.items():
            zipped.writestr("m11/" + name, raw)
        zipped.writestr("sdk-parity.json", canonical_json_bytes(report))
        zipped.writestr("original-phase-identities.json", canonical_json_bytes(originals))
        zipped.writestr("consumer.log", b"fixture only\n")
    return path.read_bytes()


class DiscoveryTest(unittest.TestCase):
    """Discovery feeds the real ``_completed_parity`` exact-input gate."""

    environment = ENVIRONMENT

    def state(self):
        plan = {"repository": REPO, "event": "pull_request", "pullRequest": 33, "validationCommit": "e" * 40}
        consumer = {"kind": "ci", "producer": {"event": "pull_request", "pullRequest": 33, "commit": "e" * 40,
                                               "runId": RUN + 10, "runAttempt": 1}}
        return Mock(plan=plan, consumer=consumer, prior={"phases": deepcopy(ROWS)})

    def discover(self, root, *, archive_rows=ROWS, recipe="original", github=None, logs=None):
        github = github or GitHub()
        raw = parity_archive(root / "original.zip", deepcopy(archive_rows))
        github.artifacts[0]["digest"] = completion.sha256_bytes(raw)
        metadata = {"size_in_bytes": len(raw), "created_at": "2026-11-20T12:30:00Z",
                    "name": reuse.PARITY_PREFIX + TREE}
        job = {"id": 90, "name": reuse.PARITY_JOB, "started_at": JOB_WINDOW[0], "completed_at": JOB_WINDOW[1]}

        def transport(artifact, token, destination, limit, digest, size):
            destination.write_bytes(raw)
            return artifact, destination
        with patch.object(completion.products, "_observe_ci_producer_jobs",
                          return_value=[{"run": {"head_sha": "c" * 40}, "jobs": [job]}]) as observe, \
                patch.object(completion.products, "_contract_ci_upload_metadata", return_value=metadata), \
                patch.object(completion.products, "_download_contract_ci_upload_bytes", side_effect=transport), \
                patch.object(completion, "git_inventory", side_effect=["original", recipe]), \
                patch("subprocess.run", side_effect=AssertionError("no fresh parity process")), \
                patch("subprocess.Popen", side_effect=AssertionError("no fresh parity process")):
            result = reuse.discover(root, self.state(), environ=self.environment, token="fixture",
                trusted_workflow_sha=PUBLISHER, completed_parity=completion._completed_parity,
                api_json=github.api_json, jobs=github.list_jobs, download=github.download,
                association_fetch=github.association_fetch, control_trees=github.control_trees,
                merge_tree=github.merge_tree, consumer_head=lambda commit: CONSUMER_HEAD,
                log=(logs.append if logs is not None else lambda _: None))
        return result, observe

    def test_identical_inputs_reuse_without_a_fresh_parity_process(self):
        github = GitHub()
        with tempfile.TemporaryDirectory() as temporary:
            result, observe = self.discover(Path(temporary).resolve(), github=github)
        self.assertEqual([(BASE_SHA, RUN_HEAD, TREE)], github.merges)  # GitHub-recorded base and head
        self.assertEqual("passed", result["result"])
        self.assertEqual(33, result["producer"]["pullRequest"])
        self.assertEqual((RUN, 2), (result["producer"]["runId"], result["producer"]["runAttempt"]))
        self.assertEqual({"parity": {"path": ".github/workflows/sdk-binding-parity.yml", "sha": PUBLISHER}},
                         observe.call_args.kwargs["trusted_workflows_by_phase"])

    def test_any_changed_input_digest_or_recipe_runs_fresh(self):
        for field in ("buildKey", "receiptSha256", "objectSha256"):
            changed = deepcopy(ROWS)
            changed[7][field] = "sha256:" + "f" * 64
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                self.assertIsNone(self.discover(Path(temporary).resolve(), archive_rows=changed)[0])
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(self.discover(Path(temporary).resolve(), recipe="changed")[0])

    def test_producer_control_trees_must_equal_the_consumer_exactly(self):
        # B1: a producer whose ci.yml (spoofed or renamed parity job) or other
        # .github / ci content differs runs fresh, before _completed_parity.
        for name, trees in (("spoofed ci.yml (.github differs)", {**TREES, ".github": "5" * 40}),
                            ("ci differs", {**TREES, "ci": "6" * 40}),
                            ("producer tree unreadable", None)):
            github = GitHub()
            if trees is None:
                del github.trees[TREE]
            else:
                github.trees[TREE] = trees
            logs = []
            with self.subTest(name), tempfile.TemporaryDirectory() as temporary:
                result, observe = self.discover(Path(temporary).resolve(), github=github, logs=logs)
                self.assertIsNone(result)
                observe.assert_not_called()
                self.assertTrue(any("[scope:control-tree]" in line for line in logs), logs)
        for missing in (CONSUMER, CONSUMER_HEAD):
            github = GitHub()
            del github.trees[missing]
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temporary:
                result, observe = self.discover(Path(temporary).resolve(), github=github)
                self.assertIsNone(result)
                observe.assert_not_called()

    def test_proposed_tree_must_be_bound_to_the_recorded_run_head(self):
        # B1 re-review: a crafted merge commit names a clean tree; the
        # recomputed merge or the run head's control trees reject it.
        for name, change, reason in (
                ("merge differs", lambda github: setattr(github, "merged", "1" * 40), "[scope:merge-tree]"),
                ("run head .github differs", lambda github: github.trees.update(
                    {RUN_HEAD: {**TREES, ".github": "5" * 40}}), "[scope:control-tree]"),
                ("run head ci differs", lambda github: github.trees.update(
                    {RUN_HEAD: {**TREES, "ci": "6" * 40}}), "[scope:control-tree]")):
            github = GitHub()
            change(github)
            logs = []
            with self.subTest(name), tempfile.TemporaryDirectory() as temporary:
                result, observe = self.discover(Path(temporary).resolve(), github=github, logs=logs)
                self.assertIsNone(result)
                observe.assert_not_called()
                self.assertTrue(any(reason in line for line in logs), logs)

    def test_merge_queue_consumer_head_must_be_the_pr_head(self):
        github = GitHub()
        environment = {**ENVIRONMENT, "GITHUB_EVENT_NAME": "merge_group",
                       "GITHUB_REF": f"refs/heads/gh-readonly-queue/main/pr-33-{'1' * 40}"}
        state = self.state()
        state.plan["event"] = "merge_group"
        state.consumer["producer"].update(event="merge_group", pullRequest=None)
        logs = []
        for pr_head, expected in ((PR_HEAD, None), (CONSUMER_HEAD, "reused")):
            github.pull["head"]["sha"] = pr_head
            with self.subTest(pr_head=pr_head), patch.object(self, "state", return_value=state), \
                    patch.object(self, "environment", environment), tempfile.TemporaryDirectory() as temporary:
                github.association[f"compare/{RUN_HEAD}...{pr_head}?per_page=1"] = github.compare(RUN_HEAD)
                result, _ = self.discover(Path(temporary).resolve(), github=github, logs=logs)
                self.assertEqual(expected, result and "reused")
        self.assertTrue(any("PR side is not the PR head" in line for line in logs), logs)

    def test_no_candidate_runs_fresh(self):
        github = GitHub()
        github.runs = []
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(self.discover(Path(temporary).resolve(), github=github)[0])

    def test_completed_parity_scope_gate(self):
        policy = {"schemaVersion": 1, "kind": "completed-sdk-parity", "producer": {
            "repository": REPO, "workflowPath": producer_scope.CI_WORKFLOW, "commit": COMMIT, "tree": TREE,
            "event": "pull_request", "pullRequest": 33, "runId": RUN, "runAttempt": 1},
            "workflowSha": PUBLISHER, "jobId": 90, "artifactId": 71, "artifactSha256": "sha256:" + "7" * 64}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "policy.json"
            for number, scope in ((33, None), (31, 33), (33, 34)):
                path.write_bytes(canonical_json_bytes({**policy, "producer": {**policy["producer"], "pullRequest": number}}))
                with self.subTest(number=number, scope=scope), \
                        patch.object(completion.products, "_observe_ci_producer_jobs",
                                     side_effect=AssertionError("scope must reject first")), \
                        self.assertRaisesRegex(ValueError, "authorized PR scope"):
                    completion._completed_parity(Path(temporary), "e" * 40, {"phases": ROWS}, path, None, "t",
                                                 admitted_scope=scope)


class GitControlTreeTest(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True,
                              env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                                   "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
                                   "HOME": str(root), "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"}
                              ).stdout.strip()

    def test_spoofed_parity_job_in_ci_yml_changes_the_github_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            self.git(root, "init", "-q")
            (root / "ci").mkdir()
            (root / "ci" / "tool.py").write_text("print('x')\n")
            (root / ".github" / "workflows").mkdir(parents=True)
            ci = root / ".github" / "workflows" / "ci.yml"
            ci.write_text("jobs:\n  product-validation:\n    uses: ./.github/workflows/product-validation.yml\n")
            self.git(root, "add", "-A")
            self.git(root, "commit", "-q", "-m", "reviewed")
            reviewed = self.git(root, "rev-parse", "HEAD")
            ci.write_text("jobs:\n  pv:\n    uses: ./.github/workflows/product-validation.yml\n"
                          "  fake:\n    name: product-validation / sdk-parity / sdk-parity\n"
                          "    runs-on: ubuntu-latest\n    steps: [{run: 'true'}]\n")
            self.git(root, "commit", "-q", "-am", "spoof")
            spoofed_tree = self.git(root, "rev-parse", "HEAD^{tree}")
            consumer = reuse.git_control_trees(root, reviewed)
            producer = reuse.git_control_trees(root, spoofed_tree)  # tree objects work too
            self.assertEqual(set(producer_scope.CONTROL_TREES), set(producer))
            self.assertEqual(consumer["ci"], producer["ci"])
            self.assertNotEqual(consumer[".github"], producer[".github"])
            with self.assertRaises(producer_scope.ScopeRejected) as raised:
                producer_scope.require_equal_control_trees(producer, consumer)
            self.assertEqual("control-tree", raised.exception.reason)
            self.assertIn("'.github'", str(raised.exception))
            for revision in ("1" * 40, "HEAD"):
                with self.subTest(revision=revision), self.assertRaises(producer_scope.ScopeRejected):
                    reuse.git_control_trees(root, revision)


class RecomputedMergeTest(unittest.TestCase):
    """B1 re-review regressions in a real temporary git repository."""

    ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_NOSYSTEM": "1",
           "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}

    def git(self, *args, stdin=None):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True,
                              input=stdin, env={**self.ENV, "HOME": str(self.root)}).stdout.strip()

    def commit(self, files, message, *, parent=None):
        if parent is not None:
            self.git("checkout", "-q", "--detach", parent)
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.git("init", "-q")
        reviewed = "jobs:\n  product-validation:\n    uses: ./.github/workflows/product-validation.yml\n"
        self.malicious = ("jobs:\n  pv:\n    uses: ./.github/workflows/product-validation.yml\n"
                          "  fake:\n    name: product-validation / sdk-parity / sdk-parity\n")
        self.base = self.commit({"ci/tool.py": "print('x')\n", ".github/workflows/ci.yml": reviewed,
                                 "product/src.txt": "v1\n"}, "main")
        # Producer PR head X2 carries the malicious ci.yml; consumer PR head Y reverts it.
        self.x2 = self.commit({"product/src.txt": "v2\n", ".github/workflows/ci.yml": self.malicious}, "x2",
                              parent=self.base)
        self.y = self.commit({".github/workflows/ci.yml": reviewed}, "y", parent=self.x2)
        clean = self.git("rev-parse", self.y + "^{tree}")
        self.consumer = self.git("commit-tree", clean, "-p", self.base, "-p", self.y, "-m", "consumer merge")
        # The attacker's crafted C': real parents [base, X2], clean tree T'.
        self.crafted_tree = clean
        self.crafted = self.git("commit-tree", clean, "-p", self.base, "-p", self.x2, "-m", "crafted")

    def tearDown(self):
        self.temporary.cleanup()

    def test_crafted_merge_is_rejected_by_the_recomputed_merge(self):
        genuine = reuse.recomputed_merge_tree(self.root, self.base, self.x2)
        self.assertNotEqual(self.crafted_tree, genuine)
        with self.assertRaises(producer_scope.ScopeRejected) as raised:
            reuse.require_recomputed_merge(self.root, self.base, self.x2, self.crafted_tree)
        self.assertEqual("merge-tree", raised.exception.reason)
        # The old check alone is fooled: T' carries the reviewed control trees.
        producer_scope.require_equal_control_trees(reuse.git_control_trees(self.root, self.crafted_tree),
                                                   reuse.git_control_trees(self.root, self.consumer))

    def test_crafted_merge_is_rejected_by_the_run_head_control_trees(self):
        consumer_head = reuse.consumer_pull_request_head(self.root, self.consumer)
        self.assertEqual(self.y, consumer_head)
        with self.assertRaises(producer_scope.ScopeRejected) as raised:
            producer_scope.require_equal_control_trees(reuse.git_control_trees(self.root, self.x2),
                                                       reuse.git_control_trees(self.root, consumer_head))
        self.assertEqual("control-tree", raised.exception.reason)
        self.assertIn("'.github'", str(raised.exception))
        with self.assertRaises(producer_scope.ScopeRejected):
            reuse.consumer_pull_request_head(self.root, self.base)  # not a two-parent merge

    def test_genuine_merge_is_accepted(self):
        producer_head = self.commit({"product/src.txt": "v3\n"}, "reviewed head", parent=self.y)
        tree = reuse.recomputed_merge_tree(self.root, self.base, producer_head)
        reuse.require_recomputed_merge(self.root, self.base, producer_head, tree)
        producer_scope.require_equal_control_trees(
            reuse.git_control_trees(self.root, producer_head),
            reuse.git_control_trees(self.root, reuse.consumer_pull_request_head(self.root, self.consumer)))
        producer_scope.require_equal_control_trees(reuse.git_control_trees(self.root, tree),
                                                   reuse.git_control_trees(self.root, self.consumer))

    def test_conflicting_merge_is_rejected(self):
        moved = self.commit({"product/src.txt": "main moved\n"}, "main moved", parent=self.base)
        with self.assertRaises(producer_scope.ScopeRejected) as raised:
            reuse.recomputed_merge_tree(self.root, moved, self.x2)
        self.assertEqual("merge-tree", raised.exception.reason)
        self.assertIn("do not merge cleanly", str(raised.exception))

    def test_too_old_git_is_rejected_never_skipped(self):
        genuine = reuse.recomputed_merge_tree(self.root, self.base, self.y)
        for version in ((2, 37), (1, 99)):
            with self.subTest(version=version), self.assertRaises(producer_scope.ScopeRejected) as raised:
                reuse.require_recomputed_merge(self.root, self.base, self.y, genuine, version=lambda _: version)
            self.assertEqual("merge-tree", raised.exception.reason)
        with patch.object(reuse, "_git", return_value=Mock(stdout="git version 2.37.9\n")), \
                self.assertRaises(producer_scope.ScopeRejected):
            reuse.require_recomputed_merge(self.root, self.base, self.y, genuine)
        self.assertGreaterEqual(reuse.git_version(self.root), reuse.MERGE_TREE_MINIMUM)


class WiringTest(unittest.TestCase):
    def test_kill_switch_and_fresh_fallback_wiring(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("reuseCompletedParity: ${{ vars.CODEX_AGENT_REUSE_COMPLETED_SDK_PARITY == 'true' }}", ci)
        self.assertIn("discoverCompletedParity: ${{ vars.CODEX_AGENT_REUSE_COMPLETED_SDK_PARITY == 'auto' }}", ci)
        validation = (ROOT / ".github/workflows/product-validation.yml").read_text()
        self.assertIn("discoverCompletedParity: ${{ inputs.discoverCompletedParity && !inputs.reuseCompletedParity && ",
                      validation)
        parity = (ROOT / ".github/workflows/sdk-binding-parity.yml").read_text()
        self.assertIn("if: inputs.importedOnly && !inputs.reuseCompletedParity && inputs.discoverCompletedParity", parity)
        # N2: reuse only on outcome success AND reused == 'true'; anything else is fresh.
        reused = "(steps.discover-parity.outcome == 'success' && steps.discover-parity.outputs.reused == 'true')"
        self.assertIn(f"if: inputs.importedOnly && !inputs.reuseCompletedParity && !{reused}", parity)
        self.assertIn(f"if: ${{{{ !inputs.reuseCompletedParity && !{reused} }}}}", parity)
        self.assertIn(f"REUSE_COMPLETED_PARITY: ${{{{ inputs.reuseCompletedParity || {reused} }}}}", parity)
        self.assertIn(f"if: inputs.reuseCompletedParity || {reused}", parity)
        self.assertEqual(5, parity.count(reused))
        self.assertNotIn("steps.discover-parity.outputs.reused != 'true'", parity)
        self.assertEqual(5, parity.count("steps.discover-parity.outputs.reused"))
        self.assertIn("--hosted-parity --discover-parity", parity)

    def test_cli_routes_reused_false_on_any_discovery_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "out"
            arguments = Mock(plan=Path("p"), discovery_root=Path("d"), state_root=Path("s"),
                             repository_root=Path(temporary), sdk_original_workflow_sha=PUBLISHER,
                             github_output=output)
            with patch.object(completion, "require_hosted_sdk_parity", side_effect=ValueError("no state")), \
                    patch("sys.stderr", io.StringIO()):
                self.assertEqual(0, completion._discover_hosted_parity(arguments, {}))
            self.assertEqual("reused=false\n", output.read_text())
            output.unlink()
            with patch.object(completion, "require_hosted_sdk_parity", return_value={"result": "passed"}), \
                    patch("sys.stdout", io.StringIO()) as stdout:
                completion._discover_hosted_parity(arguments, {})
            self.assertEqual("reused=true\n", output.read_text())
            self.assertIn('"result":"passed"', stdout.getvalue())

    def test_parity_reuse_module_owns_no_phase(self):
        self.assertEqual(frozenset(), selection._inventory_owners("ci/sdk_parity_reuse.py"))


if __name__ == "__main__":
    unittest.main()
