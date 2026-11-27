"""Official Android locator metadata only; no download or content admission."""

from contextlib import nullcontext
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_android_upload_locator as locator
from ci.tests import test_runtime_aggregate_upload as fixture


class AndroidUploadLocatorTest(unittest.TestCase):
    def test_actual_metadata_route_selects_original_authority_without_device_rebuild(self):
        source = (Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml").read_text()
        step = source.split("      - id: retained-device\n", 1)[1].split("\n  android-sdk-apk:", 1)[0]
        script = textwrap.dedent(step.split("          python3 -B - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        key = "sha256:6390796ea14dbff3a02840ccbe8683f08976985da6dbc3a4dec533d8937c50ba"
        metadata = dict(product="sdk", component="sdk-android", phase="metadata", target="android", buildKey=key)
        successor = {**metadata, "buildKey": "sha256:0cb03e6e5ea0f2b262139a8ff9ec37a88a7502892923e2af6f3d5d65caf7b83d"}
        authority = dict(schemaVersion=1,
            trustedAndroidWorkflowSha="50b21ae250d6a515f29a2d067628ad4e0bf6f213",
            trustedSourceCommit="d8fff91c7fde6e3721fe4979fe911e2020dc7eda",
            trustedSourceTree="678cbafb596df74e698560c4ff6e8319883fb8a6")
        with tempfile.TemporaryDirectory() as temporary:
            for index, (changes, ready, expected) in enumerate((
                    ({}, [metadata], True),
                    ({"GITHUB_RUN_ID": "44795649341"}, [successor], True),
                    ({"GITHUB_RUN_ID": "44785322796"}, [successor], False),
                    ({}, [{**metadata, "buildKey": "sha256:" + "0" * 64}], False),
                    ({"PULL_REQUEST": "32"}, [metadata], False),
                    ({"GITHUB_REPOSITORY": "other/repo"}, [metadata], False),
                    ({"GITHUB_EVENT_NAME": "merge_group"}, [metadata], False),
                    ({"GITHUB_RUN_ID": "40140521274", "GITHUB_RUN_ATTEMPT": "2"}, [metadata], False),
                    ({"GITHUB_RUN_ID": "40140521273"}, [metadata], False),
                    ({}, [metadata, metadata], False))):
                output = Path(temporary) / str(index)
                environment = dict(MATRIX='{"include":[]}', REQUIRED="false", PULL_REQUEST="31",
                    GITHUB_REPOSITORY=locator.REPOSITORY, GITHUB_EVENT_NAME="pull_request",
                    GITHUB_RUN_ID="40148209559", GITHUB_RUN_ATTEMPT="1", GITHUB_OUTPUT=str(output),
                    ROUTING=json.dumps({"decisions": {"ready": ready}}))
                with patch.dict(os.environ, {**environment, **changes}, clear=True):
                    exec(compile(script, "<actual-retained-metadata-routing>", "exec"), {})
                self.assertEqual(expected, output.exists())
                if expected:
                    raw = output.read_text().removeprefix("authority<<ANDROID_AUTHORITY\n").removesuffix("\nANDROID_AUTHORITY\n")
                    self.assertEqual(locator.canonical_json_bytes(authority), raw.encode())
        consumer = dict(repository=locator.REPOSITORY, workflowPath=".github/workflows/ci.yml",
            event="pull_request", pullRequest=31, runId=40148209559, runAttempt=1)
        self.assertIsNone(locator.retained_android_evidence_origin(key, consumer))

    def test_actual_routing_step_skips_only_the_exact_retained_device_key(self):
        source = (Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml").read_text()
        step = source.split("      - id: retained-device\n", 1)[1].split("\n  android-sdk-apk:", 1)[0]
        script = textwrap.dedent(step.split("          python3 -B - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        key = "sha256:2ff282b398d370be407038bdbf3e4cace0ef024c1c9d2e2f0fca5ba20a228637"
        metadata = {'product': 'sdk', 'component': 'sdk-android', 'phase': 'metadata', 'target': 'android',
            'buildKey': 'sha256:a0b5893e50c08d2f0386781d732032a075d4032717fe36648becd8c43e22b93d'}
        with tempfile.TemporaryDirectory() as temporary:
            for index, (selected, required, ready, expected) in enumerate((
                    (key, 'true', [], True), ('sha256:' + '0' * 64, 'true', [], False), (key, 'false', [], False),
                    (key, 'false', [metadata], True),
                    (key, 'false', [{**metadata, 'buildKey': 'sha256:' + '0' * 64}], False),
                    (key, 'false', [{**metadata, 'component': 'sdk-ios'}], False),
                    (key, 'false', [metadata, metadata], False))):
                output = Path(temporary) / str(index)
                environment = {'MATRIX': json.dumps({'include': [{'buildKey': selected}]}),
                    'REQUIRED': required, 'PULL_REQUEST': '31', 'GITHUB_REPOSITORY': locator.REPOSITORY,
                    'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_RUN_ID': '39012954523',
                    'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_OUTPUT': str(output),
                    'ROUTING': json.dumps({'decisions': {'ready': ready}})}
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

    def test_fixture_successor_reuses_exact_original_device_evidence_only(self):
        key = "sha256:812589fb951acd978bded008066d57eb59113c597a4ebbef66873cada8332571"
        consumer = {"repository": locator.REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
            "event": "pull_request", "pullRequest": 31, "runId": 40140521275, "runAttempt": 1}
        origin = locator.retained_android_evidence_origin(key, consumer)
        self.assertEqual((40140521274, 2, "db89763a59757d36b72da56117f5498efe02acd6"),
            (origin["producer"]["runId"], origin["producer"]["runAttempt"], origin["producer"]["commit"]))
        self.assertEqual("50b21ae250d6a515f29a2d067628ad4e0bf6f213", origin["workflowSha"])
        self.assertEqual({"artifact_id": 12579597166,
            "artifact_sha256": "sha256:d3c5d81e248085b1801a931853d76904f0ec4306b7cda1cbac8566be83ab9aab"}, origin["final"])
        self.assertEqual({"artifact_id": 12579348524,
            "artifact_sha256": "sha256:decfa84a095914eb4a7231f05f88bcbdef95fe987e36b796adc079531998fd6c"}, origin["protected"])
        self.assertIsNone(locator.retained_android_evidence_origin(key, consumer, phase="metadata"))
        for field, value in (("repository", "other/repo"), ("workflowPath", "other.yml"),
                ("event", "merge_group"), ("pullRequest", 32), ("runId", 40140521274), ("runAttempt", True)):
            with self.subTest(field=field):
                self.assertIsNone(locator.retained_android_evidence_origin(key, {**consumer, field: value}))
        pins = dict(trusted_source_commit="d8fff91c7fde6e3721fe4979fe911e2020dc7eda",
            trusted_source_tree="678cbafb596df74e698560c4ff6e8319883fb8a6",
            trusted_android_workflow_sha=origin["workflowSha"])
        locator.require_retained_android_authority(origin, **pins)
        for field in pins:
            with self.subTest(authority=field), self.assertRaises(ValueError):
                locator.require_retained_android_authority(origin, **{**pins, field: "0" * 40})
        captures = [{"captureProducer": origin["producer"], "locator": origin[name]}
                    for name in ("final", "protected")]
        locator.require_retained_android_capture(origin, *captures)
        for index in range(2):
            changed = deepcopy(captures)
            changed[index]["captureProducer"]["runAttempt"] = 1
            with self.subTest(capture=index), self.assertRaises(ValueError):
                locator.require_retained_android_capture(origin, *changed)

    def test_fixture_successor_actual_selector_preserves_missing_or_wrong_key_denial(self):
        source = (Path(__file__).resolve().parents[2] / ".github/workflows/product-validation.yml").read_text()
        step = source.split("      - id: retained-device\n", 1)[1].split("\n  android-sdk-apk:", 1)[0]
        script = textwrap.dedent(step.split("          python3 -B - <<'PY'\n", 1)[1].split("\n          PY", 1)[0])
        key = "sha256:812589fb951acd978bded008066d57eb59113c597a4ebbef66873cada8332571"
        with tempfile.TemporaryDirectory() as temporary:
            for index, (rows, required, expected) in enumerate((
                    ([{"buildKey": key}], "true", True), ([], "true", False),
                    ([{"buildKey": key}, {"buildKey": key}], "true", False),
                    ([{"buildKey": "sha256:" + "0" * 64}], "true", False),
                    ([{"buildKey": key}], "false", False))):
                output = Path(temporary) / str(index)
                environment = dict(MATRIX=json.dumps({"include": rows}), REQUIRED=required,
                    PULL_REQUEST="31", GITHUB_REPOSITORY=locator.REPOSITORY,
                    GITHUB_EVENT_NAME="pull_request", GITHUB_RUN_ID="40140521275",
                    GITHUB_RUN_ATTEMPT="1", GITHUB_OUTPUT=str(output))
                with patch.dict(os.environ, environment, clear=True):
                    exec(compile(script, "<actual-fixture-successor-selector>", "exec"), {})
                self.assertEqual(expected, output.exists())
                if expected:
                    value = json.loads(output.read_text().split("\n", 1)[1].rsplit("\nANDROID_AUTHORITY", 1)[0])
                    self.assertEqual("50b21ae250d6a515f29a2d067628ad4e0bf6f213", value["trustedAndroidWorkflowSha"])
                    self.assertEqual("d8fff91c7fde6e3721fe4979fe911e2020dc7eda", value["trustedSourceCommit"])

    def test_fixture_successor_plan_reads_exact_four_controls_after_original_window(self):
        import runtime_reference_archive as archive_reader
        consumer = dict(repository=locator.REPOSITORY, workflowPath=".github/workflows/ci.yml",
            event="pull_request", pullRequest=31, runId=40140521275, runAttempt=1)
        origin = locator.retained_android_evidence_origin(
            "sha256:812589fb951acd978bded008066d57eb59113c597a4ebbef66873cada8332571", consumer)
        observed, artifact, archive = {"run": {}}, {"id": 12578322474}, object()
        def copy_member(_archive, name, destination, record):
            self.assertIs(archive, _archive)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"control")
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary).resolve() / "plan"
            with patch.object(locator.products, "_observe_ci_producer_jobs", return_value=[observed]) as observe, \
                    patch.object(locator.products, "_contract_ci_upload_metadata", return_value=artifact) as metadata, \
                    patch.object(locator.products, "_require_artifact_job_window") as window, \
                    patch.object(archive_reader, "open_reference_archive",
                        return_value=nullcontext((archive, SimpleNamespace(transferred=0)))) as opened, \
                    patch.object(archive_reader, "copy_reference_member", side_effect=copy_member) as copied, \
                    patch.object(locator.products, "_validate_plan") as validate:
                self.assertEqual(destination / "impact-plan.json",
                    locator.capture_retained_android_plan(origin, self.f.root, destination, token="fixture"))
                planner = {**origin["producer"], "runAttempt": 1}
                observe.assert_called_once_with({"plan": planner},
                    jobs_by_phase={"plan": "product-validation / plan"},
                    trusted_workflow_sha=origin["workflowSha"], token="fixture")
                metadata.assert_called_once_with(12578322474,
                    "sha256:0273d9f7eeb167276732148a7e9080d1585bee747435baf5fdd68bec30e95569",
                    "codex-agent-ci-plan-" + planner["tree"], planner, observed["run"], "fixture")
                window.assert_called_once_with(observed, "product-validation / plan", artifact)
                self.assertEqual({
                    "impact-plan.json": {"bytes": 170201,
                        "sha256": "sha256:8d9d69af893b1416f746e07b0c983f841a0bf64b4383dc550189fa1e3cf325f4"},
                    "inventories/android/production-inputs.git-tree": {"bytes": 120991,
                        "sha256": "sha256:fada8575a9ef1e5c47b2e567fd57e3e662296542c17c5f0d6decf510b502ac8b"},
                    "inventories/android/test-inputs.git-tree": {"bytes": 1911,
                        "sha256": "sha256:65be67ce424143079d3ee33943cb5161f0a7a136447af8a42a2a3d3f29bf2cf3"},
                    "inventories/android/metadata-inputs.git-tree": {"bytes": 314,
                        "sha256": "sha256:04f68e123cb2c77b5863adc88dfe4930d401ef99d4e7e7881f198de93fbc9f4c"}},
                    {call.args[1]: call.args[3] for call in copied.call_args_list})
                validate.assert_called_once_with(destination / "impact-plan.json", self.f.root,
                    expected_revision=planner["commit"])
                opened.reset_mock()
                window.side_effect = ValueError("wrong original job window")
                with self.assertRaisesRegex(ValueError, "wrong original job window"):
                    locator.capture_retained_android_plan(origin, self.f.root, destination.parent / "denied", token="fixture")
                opened.assert_not_called()

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
