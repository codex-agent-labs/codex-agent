"""Official Android locator metadata only; no download or content admission."""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from ci import sdk_android_upload_locator as locator
from ci.tests import test_runtime_aggregate_upload as fixture


class AndroidUploadLocatorTest(unittest.TestCase):
    def test_actual_routing_step_skips_only_the_exact_retained_device_key(self):
        source = (Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml").read_text()
        step = source.split("      - id: retained-device\n", 1)[1].split("\n  android-sdk-apk:", 1)[0]
        script = textwrap.dedent(step.split("          python3 -B - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        key = "sha256:2ff282b398d370be407038bdbf3e4cace0ef024c1c9d2e2f0fca5ba20a228637"
        with tempfile.TemporaryDirectory() as temporary:
            for index, (selected, required, expected) in enumerate((
                    (key, 'true', True), ('sha256:' + '0' * 64, 'true', False), (key, 'false', False))):
                output = Path(temporary) / str(index)
                environment = {'MATRIX': json.dumps({'include': [{'buildKey': selected}]}),
                    'REQUIRED': required, 'PULL_REQUEST': '31', 'GITHUB_REPOSITORY': locator.REPOSITORY,
                    'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_RUN_ID': '39012954523',
                    'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_OUTPUT': str(output)}
                with patch.dict(os.environ, environment, clear=True):
                    exec(compile(script, '<actual-retained-device-routing>', 'exec'), {})
                self.assertEqual(expected, output.exists())
                if expected:
                    raw = output.read_text().removeprefix('authority<<ANDROID_AUTHORITY\n').removesuffix('\nANDROID_AUTHORITY\n')
                    self.assertTrue(raw.endswith('\n'))
                    self.assertEqual('26622ad8247c4c411890d22bc3519332ad11fb25',
                        json.loads(raw)['trustedAndroidWorkflowSha'])
                    child = (Path(__file__).resolve().parents[2] / '.github/workflows/sdk-android-validation.yml').read_text()
                    gate = textwrap.dedent(child.split("          python3 -I -B - <<'PY'\n", 1)[1].split('\n          PY', 1)[0])
                    with patch.dict(os.environ, {'AUTHORITY': raw, 'GITHUB_OUTPUT': str(output) + '-child'}, clear=True):
                        exec(compile(gate, '<actual-protected-authority-gate>', 'exec'), {})
        apk = source.split('\n  android-sdk-apk:\n', 1)[1].split('\n  sdk-android-validation-result:', 1)[0]
        self.assertIn("needs.sdk-android-validation-plan.outputs.retained_android_authority == ''", apk)
        self.assertEqual(2, source.count('protectedAndroidAuthority: ${{ needs.sdk-android-validation-plan.outputs.retained_android_authority ||'))

    def test_retained_device_selection_binds_key_scope_and_immutable_originals(self):
        key = "sha256:2ff282b398d370be407038bdbf3e4cace0ef024c1c9d2e2f0fca5ba20a228637"
        consumer = {"repository": locator.REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
            "event": "pull_request", "pullRequest": 31, "runId": 39012954523, "runAttempt": 1}
        origin = locator.retained_android_evidence_origin(key, consumer)
        self.assertEqual((39012954522, 2), (origin["producer"]["runId"], origin["producer"]["runAttempt"]))
        self.assertIsNone(locator.retained_android_evidence_origin("sha256:" + "0" * 64, consumer))
        for field, value in (("repository", "other/repo"), ("workflowPath", "other.yml"),
                ("event", "merge_group"), ("pullRequest", 32), ("runId", 1), ("runAttempt", True)):
            with self.subTest(field=field):
                self.assertIsNone(locator.retained_android_evidence_origin(key, {**consumer, field: value}))
        self.assertIsNone(locator.retained_android_evidence_origin(key, origin["producer"]))
        pins = dict(trusted_source_commit=origin["authority"]["trustedSourceCommit"],
            trusted_source_tree=origin["authority"]["trustedSourceTree"],
            trusted_android_workflow_sha=origin["authority"]["trustedAndroidWorkflowSha"])
        locator.require_retained_android_authority(origin, **pins)
        for field in pins:
            with self.subTest(field=field), self.assertRaises(ValueError):
                locator.require_retained_android_authority(origin, **{**pins, field: "0" * 40})
        captures = [{"captureProducer": origin["producer"], "locator": origin[name]}
                    for name in ("final", "protected")]
        locator.require_retained_android_capture(origin, *captures)
        for index in range(2):
            changed = deepcopy(captures)
            changed[index]["locator"]["artifact_id"] += 1
            with self.assertRaises(ValueError):
                locator.require_retained_android_capture(origin, *changed)

    def setUp(self):
        self.f = fixture.RuntimeAggregateUploadTest(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.environment = {"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"}
        self.android_pin = "d" * 40
        self.f.plan.update(androidEvidenceRequired=True, lanes={
            "android": {"build": True, "test": True, "metadata": False},
        })
        self.f.plan_path.write_bytes(locator.canonical_json_bytes(self.f.plan))
        self.f.run["referenced_workflows"].append({
            "path": f"{locator.REPOSITORY}/{locator.ANDROID_WORKFLOW}@reuse-authority",
            "sha": self.android_pin,
        })
        common = {"run_id": 71, "head_sha": self.f.run["head_sha"],
                  "status": "completed", "conclusion": "success"}
        self.f.jobs = [
            {**common, "id": 81, "name": locator.FIREBASE_JOB,
             "started_at": "2026-09-11T09:00:00Z", "completed_at": "2026-09-11T10:00:00Z"},
            {**common, "id": 82, "name": locator.ATTACH_JOB,
             "started_at": "2026-09-11T10:05:00Z", "completed_at": "2026-09-11T10:30:00Z"},
        ]
        self.f.artifact.update(name="codex-agent-ci-android-" + "b" * 40,
                               created_at="2026-09-11T10:15:00Z")
        self.listing = [deepcopy(self.f.artifact)]
        self.requests = []
        self.enterContext(patch.dict(os.environ, {}, clear=True))

    def api(self, url, token):
        self.requests.append(url)
        if "/actions/runs/71/artifacts?" in url:
            self.assertEqual("synthetic-token", token)
            return json.dumps({"artifacts": self.listing}).encode()
        self.assertFalse(url.endswith("/zip"), "Locator cannot download Android bytes")
        return self.f.api(url, token)

    def call(self, **changes):
        arguments = {"trusted_workflow_sha": self.f.pin,
            "trusted_android_workflow_sha": self.android_pin, "environ": self.environment,
            "token": "synthetic-token"}
        arguments.update(changes)
        with patch.object(locator.products, "_validate_plan", return_value=self.f.plan), \
                patch("reuse.api_request", side_effect=self.api):
            return locator.locate_android_validation_upload(self.f.plan_path, self.f.root, **arguments)

    def test_exact_post_attach_locator_uses_fixed_local_workflow_topology_without_download(self):
        caller = (Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml").read_text()
        workflow = (Path(__file__).resolve().parents[2] / locator.ANDROID_WORKFLOW).read_text()
        self.assertIn("android-runtime-evidence:", caller)
        self.assertTrue(".github/workflows/android-runtime-evidence.yml@reuse-authority" in caller)
        self.assertIn("  firebase-arm64-runtime:", workflow)
        self.assertIn("  attach-evidence:", workflow)
        self.assertEqual({"artifact_id": 701, "artifact_sha256": self.f.artifact["digest"]}, self.call())
        self.assertEqual(1, sum("/actions/runs/71/artifacts?" in value for value in self.requests))
        self.assertEqual(1, sum(value.endswith("/actions/artifacts/701") for value in self.requests))
        self.assertEqual(self.f.plan_path.read_bytes(), locator.canonical_json_bytes(self.f.plan))

    def test_dispatch_locator_requires_successful_original_authorization(self):
        commit = self.f.plan["validationCommit"]
        self.f.plan.update(event="workflow_dispatch", pullRequest=None,
            remoteBuildAuthorizationReason="workflow-dispatch")
        self.f.plan_path.write_bytes(locator.canonical_json_bytes(self.f.plan))
        self.f.run.update(event="workflow_dispatch", head_sha=commit, pull_requests=[])
        self.f.artifact["workflow_run"]["head_sha"] = commit
        self.listing = [deepcopy(self.f.artifact)]
        for job in self.f.jobs:
            job["head_sha"] = commit
        self.f.jobs.append({**self.f.jobs[0], "id": 83,
            "name": "product-validation / dispatch-authorization",
            "started_at": "2026-09-11T08:00:00Z", "completed_at": "2026-09-11T08:30:00Z"})
        self.assertEqual(701, self.call()["artifact_id"])
        self.f.jobs[-1]["conclusion"] = "failure"
        with self.assertRaises(ValueError):
            self.call()

    def test_pre_attach_upload_and_failed_missing_ambiguous_or_reordered_jobs_reject(self):
        baseline = deepcopy((self.f.jobs, self.f.artifact))
        for case in ("pre-attach", "firebase-failed", "attach-failed", "missing", "ambiguous", "reordered"):
            self.f.jobs, self.f.artifact = deepcopy(baseline)
            if case == "pre-attach": self.f.artifact["created_at"] = "2026-09-11T09:30:00Z"
            elif case == "firebase-failed": self.f.jobs[0]["conclusion"] = "failure"
            elif case == "attach-failed": self.f.jobs[1]["conclusion"] = "failure"
            elif case == "missing": self.f.jobs.pop(0)
            elif case == "ambiguous": self.f.jobs.append(deepcopy(self.f.jobs[1]))
            else: self.f.jobs[0]["completed_at"] = "2026-09-11T10:10:00Z"
            self.listing = [deepcopy(self.f.artifact)]
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()

    def test_reusable_pin_artifact_listing_and_detail_are_exact(self):
        baseline = deepcopy((self.f.run, self.f.artifact))
        for case in ("pin", "path", "old-main", "missing-ref", "missing", "ambiguous", "expired",
                     "id", "digest", "name", "run", "head", "detail", "url"):
            self.f.run, self.f.artifact = deepcopy(baseline)
            if case == "pin": self.f.run["referenced_workflows"][1]["sha"] = "e" * 40
            elif case == "path": self.f.run["referenced_workflows"][1]["path"] = (
                f"{locator.REPOSITORY}/{locator.ANDROID_WORKFLOW}@{self.android_pin}")
            elif case == "old-main": self.f.run["referenced_workflows"][1]["path"] = (
                f"{locator.REPOSITORY}/{locator.ANDROID_WORKFLOW}@main")
            elif case == "missing-ref": self.f.run["referenced_workflows"].pop()
            self.listing = [deepcopy(self.f.artifact)]
            if case == "missing": self.listing = []
            elif case == "ambiguous": self.listing.append(deepcopy(self.f.artifact))
            elif case == "expired": self.listing[0]["expired"] = True
            elif case == "id": self.listing[0]["id"] = True
            elif case == "digest": self.listing[0]["digest"] = "invalid"
            elif case == "name": self.listing[0]["name"] += "-wrong"
            elif case == "run": self.listing[0]["workflow_run"]["id"] = 72
            elif case == "head": self.listing[0]["workflow_run"]["head_sha"] = "e" * 40
            elif case == "url": self.listing[0]["archive_download_url"] = "https://elsewhere.invalid/zip"
            if case == "detail": self.f.artifact["digest"] = "sha256:" + "f" * 64
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()

    def test_denied_non_android_dispatch_secret_and_mutation_fail_closed(self):
        baseline = deepcopy(self.f.plan)
        changes = (
            {"remoteBuildAuthorized": False}, {"androidEvidenceRequired": False},
            {"lanes": {"android": {"build": False, "test": False, "metadata": False}}},
            {"event": "push", "pullRequest": None},
        )
        for change in changes:
            self.f.plan = {**baseline, **change}
            with self.subTest(change=change), patch.object(
                    locator.products, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()
        self.f.plan = baseline
        for arguments in ({"trusted_android_workflow_sha": "main"}, {"token": ""}):
            with self.subTest(arguments=arguments), patch.object(
                    locator.products, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
                self.call(**arguments)
            observe.assert_not_called()
        for selected in (self.environment, os.environ):
            selected["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
            try:
                with patch.object(locator, "read_regular_file_bytes") as read, self.assertRaises(ValueError):
                    self.call()
                read.assert_not_called()
            finally:
                del selected["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"]

        gate = locator.products._require_artifact_job_window
        original = self.f.plan_path.read_bytes()
        for mutation in ("source", "private", "parsed", "environment", "secret"):
            self.f.plan_path.write_bytes(original)
            self.f.plan = deepcopy(baseline)
            captured = []
            self.environment["GITHUB_RUN_ATTEMPT"] = "2"
            def validate(path, root, *, expected_revision=None):
                captured.append(path)
                return self.f.plan
            def mutate(*args):
                gate(*args)
                if mutation == "source": self.f.plan_path.write_bytes(b"changed\n")
                elif mutation == "private": captured[0].write_bytes(b"changed\n")
                elif mutation == "parsed": self.f.plan["androidEvidenceRequired"] = False
                elif mutation == "environment": self.environment["GITHUB_RUN_ATTEMPT"] = "3"
                else: self.environment["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
            try:
                with self.subTest(mutation=mutation), patch.object(
                        locator.products, "_validate_plan", side_effect=validate), \
                        patch("reuse.api_request", side_effect=self.api), \
                        patch.object(locator.products, "_require_artifact_job_window", side_effect=mutate), \
                        self.assertRaises(ValueError):
                    locator.locate_android_validation_upload(
                        self.f.plan_path, self.f.root, trusted_workflow_sha=self.f.pin,
                        trusted_android_workflow_sha=self.android_pin, environ=self.environment,
                        token="synthetic-token",
                    )
            finally:
                self.environment.pop("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", None)


if __name__ == "__main__":
    unittest.main()
