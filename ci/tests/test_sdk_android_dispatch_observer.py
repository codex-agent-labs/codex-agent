"""Official API observation is mocked; no hosted or Firebase work runs."""

from copy import deepcopy
import json
import os
import unittest
from unittest.mock import patch

from ci import sdk_android_dispatch_observer as observer
from ci.tests import test_runtime_aggregate_upload as fixture


class AndroidDispatchObserverTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeAggregateUploadTest(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.pin = self.f.pin
        self.android_pin = "d" * 40
        self.producer = {**self.f.producer, "event": "workflow_dispatch", "pullRequest": None}
        self.f.run.update(event="workflow_dispatch", head_sha=self.producer["commit"],
                          pull_requests=[])
        self.f.run["referenced_workflows"].append({
            "path": (f"{observer.upload_locator.REPOSITORY}/"
                     f"{observer.upload_locator.ANDROID_WORKFLOW}@main"),
            "sha": self.android_pin,
        })
        common = {"run_id": self.producer["runId"], "head_sha": self.producer["commit"],
                  "status": "completed", "conclusion": "success"}
        self.f.jobs = [
            {**common, "id": 80, "name": observer.DISPATCH_JOB,
             "started_at": "2026-09-21T08:00:00Z", "completed_at": "2026-09-21T08:05:00Z"},
            {**common, "id": 81, "name": observer.upload_locator.FIREBASE_JOB,
             "started_at": "2026-09-21T08:10:00Z", "completed_at": "2026-09-21T09:00:00Z"},
            {**common, "id": 82, "name": observer.upload_locator.ATTACH_JOB,
             "started_at": "2026-09-21T09:05:00Z", "completed_at": "2026-09-21T09:30:00Z"},
        ]
        self.f.commit = {"sha": self.producer["commit"],
                         "tree": {"sha": self.producer["tree"]}, "parents": []}
        self.requests = []
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def api(self, url, token):
        self.assertEqual("synthetic-token", token)
        self.requests.append(url)
        prefix = f"https://api.github.com/repos/{observer.upload_locator.REPOSITORY}"
        if url == prefix + "/actions/runs/71/attempts/2":
            value = self.f.run
        elif url.startswith(prefix + "/actions/runs/71/attempts/2/jobs?"):
            value = {"jobs": self.f.jobs}
        elif url == prefix + "/git/commits/" + self.producer["commit"]:
            value = self.f.commit
        else:
            raise AssertionError(f"Unexpected HTTP request: {url}")
        return json.dumps(value).encode()

    def call(self, **changes):
        arguments = {"trusted_workflow_sha": self.pin,
            "trusted_android_workflow_sha": self.android_pin,
            "token": "synthetic-token"}
        arguments.update(changes)
        with patch("reuse.api_request", side_effect=self.api):
            return observer.observe_android_protected_dispatch(self.producer, **arguments)

    def test_exact_attempt_pins_fixed_environment_jobs_and_order(self):
        result = self.call()
        self.assertEqual(self.f.run, result["run"])
        self.assertEqual(self.f.commit, result["testedCommit"])
        self.assertEqual(self.f.jobs, result["jobs"])
        self.assertEqual(1, sum("/attempts/2" in value and "/jobs?" not in value
                                for value in self.requests))
        self.assertEqual(1, sum("/attempts/2/jobs?" in value for value in self.requests))

    def test_dispatch_approval_firebase_and_attach_must_all_succeed_exactly_once(self):
        baseline = deepcopy(self.f.jobs)
        for case in ("dispatch-missing", "dispatch-duplicate", "dispatch-failed",
                     "firebase-failed", "attach-failed", "wrong-attempt"):
            self.f.jobs = deepcopy(baseline)
            if case == "dispatch-missing": self.f.jobs.pop(0)
            elif case == "dispatch-duplicate": self.f.jobs.append(deepcopy(self.f.jobs[0]))
            elif case == "dispatch-failed": self.f.jobs[0]["conclusion"] = "failure"
            elif case == "firebase-failed": self.f.jobs[1]["conclusion"] = "failure"
            elif case == "attach-failed": self.f.jobs[2]["conclusion"] = "failure"
            else: self.f.run["run_attempt"] = 1
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.f.run["run_attempt"] = 2

    def test_android_reference_is_declared_main_and_independently_pinned(self):
        baseline = deepcopy(self.f.run["referenced_workflows"])
        for case in ("missing", "duplicate", "path", "sha"):
            self.f.run["referenced_workflows"] = deepcopy(baseline)
            if case == "missing": self.f.run["referenced_workflows"].pop()
            elif case == "duplicate": self.f.run["referenced_workflows"].append(
                deepcopy(self.f.run["referenced_workflows"][-1]))
            elif case == "path": self.f.run["referenced_workflows"][-1]["path"] = (
                self.f.run["referenced_workflows"][-1]["path"].removesuffix("@main") +
                "@" + self.android_pin)
            else: self.f.run["referenced_workflows"][-1]["sha"] = "e" * 40
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, "caller-pinned"):
                self.call()

    def test_jobs_must_follow_protected_dispatch_then_firebase_then_attach(self):
        baseline = deepcopy(self.f.jobs)
        for case in ("dispatch-late", "firebase-late", "timezone", "malformed"):
            self.f.jobs = deepcopy(baseline)
            if case == "dispatch-late": self.f.jobs[0]["completed_at"] = "2026-09-21T08:20:00Z"
            elif case == "firebase-late": self.f.jobs[1]["completed_at"] = "2026-09-21T09:20:00Z"
            elif case == "timezone": self.f.jobs[1]["started_at"] = "2026-09-21T09:10:00+01:00"
            else: self.f.jobs[2]["started_at"] = "not-a-time"
            with self.subTest(case=case), self.assertRaises((ValueError, TypeError)):
                self.call()

    def test_only_workflow_dispatch_with_complete_caller_policy_is_supported(self):
        baseline = deepcopy(self.producer)
        for case in ("event", "pull-request", "android-pin", "product-pin", "token"):
            self.producer = deepcopy(baseline)
            changes = {}
            if case == "event": self.producer["event"] = "merge_group"
            elif case == "pull-request": self.producer["pullRequest"] = 1
            elif case == "android-pin": changes["trusted_android_workflow_sha"] = "main"
            elif case == "product-pin": changes["trusted_workflow_sha"] = "main"
            else: changes["token"] = ""
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call(**changes)

    def test_caller_producer_mutation_during_observation_rejects(self):
        api = self.api
        def mutate(url, token):
            value = api(url, token)
            if "/jobs?" in url:
                self.producer["runAttempt"] += 1
            return value
        with patch("reuse.api_request", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "caller policy changed"):
            observer.observe_android_protected_dispatch(
                self.producer, trusted_workflow_sha=self.pin,
                trusted_android_workflow_sha=self.android_pin, token="synthetic-token")


if __name__ == "__main__":
    unittest.main()
