"""Exact-input SDK parity reuse within the consumer's PR scope (9.5.0)."""

from copy import deepcopy
import io
from pathlib import Path
import re
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
RUN = 500
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
        self.pull = {"number": 33, "head": {"ref": "phase95/0", "repo": {"full_name": REPO, "fork": False}}}
        self.runs = [{"id": RUN, "run_attempt": 2, "event": "pull_request", "path": producer_scope.CI_WORKFLOW,
                      "head_branch": "phase95/0", "repository": {"full_name": REPO, "fork": False},
                      "head_repository": {"full_name": REPO, "fork": False}}]
        self.artifacts = [
            {"id": 71, "name": reuse.PARITY_PREFIX + TREE, "expired": False,
             "digest": "sha256:" + "7" * 64, "created_at": "2026-11-20T12:30:00Z"},
            {"id": 72, "name": reuse.PLAN_PREFIX + TREE, "expired": False, "digest": "sha256:" + "8" * 64}]
        self.jobs = {2: [self.job("success")], 1: []}
        self.plan = plan_archive()
        self.reads = []

    def job(self, conclusion, window=JOB_WINDOW):
        return {"id": 90, "name": reuse.PARITY_JOB, "status": "completed", "conclusion": conclusion,
                "started_at": window[0], "completed_at": window[1]}

    def api_json(self, url):
        self.reads.append(url)
        if url == f"{API}/pulls/33":
            return deepcopy(self.pull)
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
        return list(reuse.candidates(33, current_run=RUN + 10, trusted_workflow_sha=PUBLISHER,
            api_json=self.api_json, jobs=self.list_jobs, download=self.download,
            reject=(rejected.append if rejected is not None else lambda reason: None)))


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

    environment = {"GITHUB_REPOSITORY": REPO, "GITHUB_EVENT_NAME": "pull_request",
                   "GITHUB_REF": "refs/pull/33/merge", "GITHUB_SHA": "e" * 40}

    def state(self):
        plan = {"repository": REPO, "event": "pull_request", "pullRequest": 33, "validationCommit": "e" * 40}
        consumer = {"kind": "ci", "producer": {"event": "pull_request", "pullRequest": 33, "commit": "e" * 40,
                                               "runId": RUN + 10, "runAttempt": 1}}
        return Mock(plan=plan, consumer=consumer, prior={"phases": deepcopy(ROWS)})

    def discover(self, root, *, archive_rows=ROWS, recipe="original", github=None):
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
                api_json=github.api_json, jobs=github.list_jobs, download=github.download, log=lambda _: None)
        return result, observe

    def test_identical_inputs_reuse_without_a_fresh_parity_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, observe = self.discover(Path(temporary).resolve())
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
        self.assertIn("if: inputs.importedOnly && !inputs.reuseCompletedParity && "
                      "steps.discover-parity.outputs.reused != 'true'", parity)
        self.assertIn("if: ${{ !inputs.reuseCompletedParity && steps.discover-parity.outputs.reused != 'true' }}", parity)
        self.assertIn("REUSE_COMPLETED_PARITY: ${{ inputs.reuseCompletedParity || "
                      "steps.discover-parity.outputs.reused == 'true' }}", parity)
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
