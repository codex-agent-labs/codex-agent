"""SDK upload transport over synthetic HTTP, not product/signature admission.

Reuse only the existing transport fixture setup/helpers, never its test methods.
Plan replay and HTTP are substituted; observation, archive and publication gates
are real. Deliberately non-product bytes demonstrate the content-gate boundary.
"""

from copy import deepcopy
import io
import json
from pathlib import Path
import stat
import unittest
from unittest.mock import call, patch
import zipfile

from ci.tests import test_runtime_aggregate_upload as fixture
from ci.tests.product_chain_support import output, write_receipt
from products.inventory import canonical_json_bytes, publish_regular_tree, regular_file_inventory, sha256_bytes


capture = fixture.capture
JOB = "product-validation / sdk-inputs"


class SdkInputsUploadTest(unittest.TestCase):
    archive = fixture.RuntimeAggregateUploadTest.archive
    api = fixture.RuntimeAggregateUploadTest.api

    def setUp(self):
        fixture.RuntimeAggregateUploadTest.setUp(self)
        self.jobs[0]["name"] = JOB
        self.artifact["name"] = f"codex-agent-sdk-inputs-{self.producer['tree']}-attempt-2"
        self.source("released-default")
        self.original_plan = self.plan_path.read_bytes()

    def source(self, source):
        self.expected_source = source
        self.files = {"sdk-inputs/synthetic-input.json": b"not authenticated SDK product content\n"}
        if source == "released-default":
            self.files.update({
                "runtime-original/original-receipt.json": b"original opaque transport bytes\n",
                "runtime-original/empty-diagnostics.log": b"",
                "current-contract/original-receipt.json": b"current opaque transport bytes\n",
                "selection.json": canonical_json_bytes({"source": source}),
                "transport.json": canonical_json_bytes({"consumer": {"kind": "ci", "producer": self.producer}}),
            })
        else:
            self.files.update({
                "runtime-capture/plan/impact-plan.json": self.plan_path.read_bytes(),
                "runtime-capture/empty-diagnostics.log": b"",
            })
        self.archive()

    def call(self, **changes):
        with patch.object(capture, "_validate_plan", return_value=self.plan) as validate, \
                patch("reuse.api_request", side_effect=self.api), \
                patch.object(capture, "download_artifact_to_file",
                    side_effect=lambda artifact, token, destination, **kwargs:
                        Path(destination).write_bytes(self.raw)):
            result = capture.capture_sdk_inputs_upload(self.plan_path, self.output, **{
                "artifact_id": 701, "artifact_sha256": self.artifact["digest"],
                "trusted_workflow_sha": self.pin, "expected_source": self.expected_source,
                "repository_root": self.root,
                "environ": {"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"},
                "token": "synthetic-token", **changes})
            self.plan_validation_call = validate.call_args
            return result

    def test_current_plan_reference_resolves_original_runtime_and_retains_archive_proof(self):
        from runtime_reference_transport import SDK_REFERENCE_NAME
        self.source('current-runtime')
        member = 'runtime-capture/original/body.bin'
        body = b'original signed Runtime carrier remains subject to the full consumer gate'
        files = {**self.files, member: body}
        inventory = sorted([dict(relativePath=name, bytes=len(raw), sha256=sha256_bytes(raw))
                            for name, raw in files.items()], key=lambda row: row['relativePath'])
        source = dict(artifactId=702, artifactSha256='sha256:' + 'e' * 64, producer=self.producer,
            workflowSha=self.pin, buildKey='sha256:' + 'f' * 64,
            metadataReceiptSha256='sha256:' + 'd' * 64)
        self.files[SDK_REFERENCE_NAME] = canonical_json_bytes(dict(schemaVersion=1,
            source=source, inventory=inventory))
        self.archive()
        def original(plan, destination, **kwargs):
            self.assertEqual(source['artifactId'], kwargs['artifact_id'])
            self.assertEqual(source['artifactSha256'], kwargs['artifact_sha256'])
            self.assertEqual(source['workflowSha'], kwargs['trusted_workflow_sha'])
            self.assertEqual(source['buildKey'], kwargs['expected_build_key'])
            self.assertEqual(source['metadataReceiptSha256'], kwargs['expected_metadata_receipt_sha256'])
            self.assertEqual(self.plan['validationCommit'], kwargs['expected_plan_revision'])
            (destination / 'original').mkdir(parents=True)
            (destination / 'original/body.bin').write_bytes(body)
        with patch.object(capture, 'capture_runtime_aggregate_release_upload', side_effect=original) as gate:
            self.call()
        gate.assert_called_once()
        self.assertEqual(inventory, regular_file_inventory(self.output / 'original', allow_empty=True))
        self.assertEqual(self.raw, (self.output / 'transport.zip').read_bytes())
        capture._verify_retained_sdk_upload_archive(self.output, self.artifact)
        (self.output / 'original' / member).write_bytes(b'changed original')
        with self.assertRaisesRegex(ValueError, 'differs from its original archive'):
            capture._verify_retained_sdk_upload_archive(self.output, self.artifact)
        self.output = self.work / 'member-reference'
        def member_capture(plan, producer, reference, original_root, **kwargs):
            # Routing only; the member test exercises actual authentication.
            path = original_root / member
            path.parent.mkdir(parents=True)
            path.write_bytes(body)
            return True
        with patch.object(capture, '_capture_sdk_runtime_reference', side_effect=member_capture) as members, \
                patch.object(capture, 'capture_runtime_aggregate_release_upload', side_effect=AssertionError('Duplicate aggregate capture')):
            self.call()
        members.assert_called_once()
        self.assertEqual(inventory, regular_file_inventory(self.output / 'original', allow_empty=True))
        capture._verify_retained_sdk_upload_archive(self.output, self.artifact)
        self.output = self.work / 'rejected-reference'
        with patch.object(capture, 'capture_runtime_aggregate_release_upload', side_effect=ValueError('failed original source')):
            with self.assertRaisesRegex(ValueError, 'failed original source'):
                self.call()
        self.assertFalse(self.output.exists())

    def test_retry_keeps_original_source_attempt_and_environment(self):
        environment = {"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "3"}
        before = dict(environment)
        result = self.call(environ=environment)
        self.assertEqual(self.producer, result["captureProducer"])
        self.assertEqual(before, environment)
        self.assertEqual(self.raw, (self.output / "transport.zip").read_bytes())

    def test_prior_runtime_reference_reuses_hydrated_members_with_fresh_original_checks(self):
        import os
        import hydrated_evidence
        from products.sdk_inputs import REQUEST_NAME
        origin = fixture.RuntimeAggregateUploadTest()
        origin.setUp()
        self.addCleanup(origin.doCleanups)
        origin.files["body.bin"] = b"x" * (16 * 1024 * 1024)
        origin.archive()
        source = dict(artifactId=701, artifactSha256=origin.artifact["digest"], producer=origin.producer,
            workflowSha=origin.pin, buildKey=origin.key, metadataReceiptSha256=origin.digest)
        rows = [dict(relativePath="runtime-capture/original/" + name, bytes=len(raw), sha256=sha256_bytes(raw))
                for name, raw in sorted(origin.files.items())]
        reference = dict(source=source, inventory=rows)
        consumer = {**origin.producer, "runId": 72, "runAttempt": 1}

        def inputs(name):
            original = self.work / name
            sdk = original / "sdk-inputs"
            sdk.mkdir(parents=True)
            (sdk / REQUEST_NAME).write_bytes(canonical_json_bytes({"runtimeMetadataReceipt": "receipt.json"}))
            (sdk / "receipt.json").write_bytes(origin.files["aggregate-input/metadata-receipt.json"])
            return original

        with patch.dict(os.environ, {"CODEX_AGENT_HYDRATED_EVIDENCE": str(self.work / "hydrated")}), \
                patch("reuse.api_request", side_effect=origin.api), \
                patch("runtime_reference_archive.open_reference_archive", side_effect=AssertionError("Repeated Runtime transfer")), \
                patch.object(capture, "_observe_ci_producer_jobs", wraps=capture._observe_ci_producer_jobs) as observe:
            for row in rows:
                path = self.work / "seed" / row["relativePath"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(origin.files[row["relativePath"].removeprefix("runtime-capture/original/")])
                hydrated_evidence.retain(row, path)
            original = inputs("warm")
            self.assertTrue(capture._capture_sdk_runtime_reference(origin.plan, consumer, reference, original,
                                                                   token="synthetic-token"))
            observe.assert_called_once()
            self.assertEqual(origin.files, {row["relativePath"]: (original / "runtime-capture/original" / row["relativePath"]).read_bytes()
                for row in regular_file_inventory(original / "runtime-capture/original", allow_empty=True)})
            with self.assertRaisesRegex(ValueError, "original aggregate receipt"):
                capture._capture_sdk_runtime_reference(origin.plan, consumer,
                    {**reference, "source": {**source, "metadataReceiptSha256": "sha256:" + "e" * 64}},
                    inputs("wrong-receipt"), token="synthetic-token")
            origin.jobs[0]["conclusion"] = "failure"
            with self.assertRaises(ValueError):
                capture._capture_sdk_runtime_reference(origin.plan, consumer, reference, inputs("failed-original"),
                                                      token="synthetic-token")
            origin.jobs[0]["conclusion"] = "success"
            hydrated_evidence.blob(next(row for row in rows if row["relativePath"].endswith("/body.bin"))).write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                capture._capture_sdk_runtime_reference(origin.plan, consumer, reference, inputs("corrupt-cache"),
                                                      token="synthetic-token")
            self.assertFalse(capture._capture_sdk_runtime_reference(origin.plan, origin.producer, reference,
                inputs("same-run"), token="synthetic-token"))
            self.assertFalse(capture._capture_sdk_runtime_reference(origin.plan, consumer,
                {**reference, "source": {**source, "producer": {**origin.producer, "runId": 70}}},
                inputs("reattested"), token="synthetic-token"))

    def original_package_receipt(self, *, product="sdk", component="sdk-ios", phase="package", target="ios"):
        path = self.work / "original-package" / f"{product}-{component}-{phase}-{target}.json"
        write_receipt(
            path, product=product, component=component, phase=phase, target=target,
            version="0.8.0", version_identity="0.8.0",
            outputs=[output("fixture", "outputs/original.bin", b"synthetic original package")],
            upstream=[], context={"producer": self.producer},
        )
        return path

    def test_historical_package_producer_ignores_current_environment_for_both_layouts(self):
        receipt = self.original_package_receipt()
        original_receipt = receipt.read_bytes()
        for source in ("released-default", "current-runtime"):
            with self.subTest(source=source):
                self.source(source)
                self.output = self.work / f"historical-{source}"
                result = self.call(original_package_receipt_path=receipt, environ={
                    "GITHUB_RUN_ID": "unrelated-current-run", "GITHUB_RUN_ATTEMPT": "not-the-original-attempt",
                    "GITHUB_SHA": "e" * 40, "GITHUB_EVENT_NAME": "workflow_dispatch",
                })
                self.assertEqual(self.producer, result["captureProducer"])
                self.assertEqual({"expected_revision": self.producer["commit"]},
                                 self.plan_validation_call.kwargs)
                self.assertEqual(self.run, result["observed"][0]["run"])
                self.assertEqual(self.raw, (self.output / "transport.zip").read_bytes())
                self.assertEqual(self.original_plan, (self.output / "plan/impact-plan.json").read_bytes())
                self.assertEqual(original_receipt, (self.output / "original-package-receipt.json").read_bytes())
                self.assertEqual(sha256_bytes(original_receipt), result["packageReceiptSha256"])
                for relative, contents in self.files.items():
                    self.assertEqual(contents, (self.output / "original" / relative).read_bytes())
                self.assertEqual(original_receipt, receipt.read_bytes())

    def test_historical_receipt_requires_exact_ios_package_identity_before_observation(self):
        identities = (
            dict(phase="binary"),
            dict(component="javascript", target="node"),
            dict(product="contract", component="contract", phase="metadata", target="common"),
        )
        for identity in identities:
            receipt = self.original_package_receipt(**identity)
            before = receipt.read_bytes()
            with self.subTest(identity=identity), patch.object(capture, "_observe_ci_producer_jobs") as observe:
                with self.assertRaises(ValueError):
                    self.call(original_package_receipt_path=receipt)
                observe.assert_not_called()
                self.assertFalse(self.output.exists())
                self.assertEqual(before, receipt.read_bytes())

    def test_historical_plan_must_match_all_original_producer_fields_before_observation(self):
        receipt = self.original_package_receipt()
        original_plan = deepcopy(self.plan)
        changes = (
            {"validationCommit": "e" * 40}, {"validationTree": "e" * 40},
            {"pullRequest": 32}, {"event": "merge_group", "pullRequest": None},
            {"repository": "another/repository"},
        )
        for change in changes:
            self.plan = {**deepcopy(original_plan), **change}
            self.plan_path.write_bytes(canonical_json_bytes(self.plan))
            with self.subTest(change=change), patch.object(capture, "_observe_ci_producer_jobs") as observe:
                with self.assertRaises(ValueError):
                    self.call(original_package_receipt_path=receipt)
                observe.assert_not_called()
                self.assertFalse(self.output.exists())
        self.plan = original_plan
        self.plan_path.write_bytes(self.original_plan)
        # Workflow is fixed by _consumer, not accepted from a claimed receipt.
        value = json.loads(receipt.read_bytes())
        value["producer"]["workflowPath"] = ".github/workflows/other.yml"
        receipt.write_bytes(canonical_json_bytes(value))
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
            self.call(original_package_receipt_path=receipt)
        observe.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_historical_current_runtime_upload_still_requires_original_plan_bytes(self):
        receipt = self.original_package_receipt()
        self.source("current-runtime")
        self.files["runtime-capture/plan/impact-plan.json"] = canonical_json_bytes({
            **self.plan, "validationCommit": "e" * 40,
        })
        self.archive()
        with self.assertRaisesRegex(ValueError, "original plan differs"):
            self.call(original_package_receipt_path=receipt, environ={})
        self.assertFalse(self.output.exists())

    def test_historical_receipt_mutation_rejects_before_publication(self):
        receipt = self.original_package_receipt()
        original = receipt.read_bytes()
        gate = capture._require_artifact_job_window

        def mutate_after_observation(*arguments):
            result = gate(*arguments)
            receipt.write_bytes(original + b" ")
            return result

        with patch.object(capture, "_require_artifact_job_window", side_effect=mutate_after_observation):
            with self.assertRaisesRegex(ValueError, "changed"):
                self.call(original_package_receipt_path=receipt, environ={})
        self.assertFalse(self.output.exists())
        self.assertEqual(self.original_plan, self.plan_path.read_bytes())

    def test_historical_receipt_output_overlap_rejects_before_observation(self):
        receipt = self.original_package_receipt()
        before = regular_file_inventory(self.work, allow_empty=True)
        for destination in (receipt, receipt.parent):
            self.output = destination
            with self.subTest(destination=destination), patch.object(capture, "_observe_ci_producer_jobs") as observe:
                with self.assertRaisesRegex(ValueError, "overlaps an original input"):
                    self.call(original_package_receipt_path=receipt)
                observe.assert_not_called()
            self.assertEqual(before, regular_file_inventory(self.work, allow_empty=True))

    def plan_for_validation(self):
        # Exact existing impact schema. Authorization and legacy projection are
        # explicit seams below; the real selected-revision checks are exercised.
        plan = {**self.plan, "schemaVersion": 1,
                "baseCommit": "1" * 40, "headCommit": "f" * 40, "mergeReady": True,
                "remoteBuildAuthorizationReason": "synthetic authorized fixture",
                "androidEvidenceRequired": False, "fullRequested": False, "full": False,
                "unknownPaths": [], "changedPaths": [], "lanes": {}}
        self.plan_path.write_bytes(canonical_json_bytes(plan))
        return plan

    def test_real_plan_validator_selects_exact_historical_object_without_head(self):
        plan = self.plan_for_validation()
        revision = plan["validationCommit"]
        identities = {f"{revision}^{{commit}}": revision, f"{revision}^{{tree}}": plan["validationTree"],
                      "HEAD^{commit}": "e" * 40, "HEAD^{tree}": "d" * 40}
        with patch.object(capture, "validate_remote_build_authorization") as authorize, \
                patch.object(capture, "validate_legacy_lane_projection") as projection, \
                patch.object(capture, "_git_value", side_effect=lambda root, operation, name: identities[name]) as git:
            self.assertEqual(plan, capture._validate_plan(self.plan_path, self.root, expected_revision=revision))
            self.assertEqual([call(self.root, "rev-parse", f"{revision}^{{commit}}"),
                              call(self.root, "rev-parse", f"{revision}^{{tree}}")], git.call_args_list)
            authorize.assert_called_once_with(plan)
            projection.assert_called_once_with(plan, repository_root=self.root, plan_path=self.plan_path)
            git.reset_mock()
            with self.assertRaisesRegex(ValueError, "Checkout commit"):
                capture._validate_plan(self.plan_path, self.root)
            git.assert_called_once_with(self.root, "rev-parse", "HEAD^{commit}")
            identities.update({"HEAD^{commit}": revision, "HEAD^{tree}": plan["validationTree"]})
            git.reset_mock()
            self.assertEqual(plan, capture._validate_plan(self.plan_path, self.root))
            self.assertEqual([call(self.root, "rev-parse", "HEAD^{commit}"),
                              call(self.root, "rev-parse", "HEAD^{tree}")], git.call_args_list)

    def test_real_historical_plan_validator_rejects_wrong_revision_commit_and_tree(self):
        plan = self.plan_for_validation()
        revision = plan["validationCommit"]
        with patch.object(capture, "validate_remote_build_authorization"), \
                patch.object(capture, "validate_legacy_lane_projection"), \
                patch.object(capture, "_git_value") as git:
            for invalid in ("HEAD", revision[:12], revision.upper(), "e" * 40, True):
                with self.subTest(revision=invalid), self.assertRaisesRegex(ValueError, "selected revision"):
                    capture._validate_plan(self.plan_path, self.root, expected_revision=invalid)
                git.assert_not_called()
            for values, message in ((("e" * 40, plan["validationTree"]), "Checkout commit"),
                                    ((revision, "d" * 40), "Checkout tree")):
                git.side_effect = values
                with self.subTest(values=values), self.assertRaisesRegex(ValueError, message):
                    capture._validate_plan(self.plan_path, self.root, expected_revision=revision)

    def test_historical_revision_does_not_skip_authorization_or_legacy_projection(self):
        plan = self.plan_for_validation()
        for rejecting in ("validate_remote_build_authorization", "validate_legacy_lane_projection"):
            with self.subTest(rejecting=rejecting), \
                    patch.object(capture, "validate_remote_build_authorization") as authorize, \
                    patch.object(capture, "validate_legacy_lane_projection") as projection, \
                    patch.object(capture, "_git_value") as git:
                gate = authorize if rejecting == "validate_remote_build_authorization" else projection
                gate.side_effect = ValueError("original policy rejected")
                with self.assertRaisesRegex(ValueError, "original policy rejected"):
                    capture._validate_plan(self.plan_path, self.root, expected_revision=plan["validationCommit"])
                gate.assert_called_once()
                git.assert_not_called()

    def test_both_exact_layouts_preserve_original_archive_and_empty_diagnostics(self):
        for source in ("released-default", "current-runtime"):
            with self.subTest(source=source):
                self.source(source)
                self.output = self.work / source
                if source == "current-runtime":
                    # Other jobs may remain live; the fixed upload owner must
                    # already have its exact successful completed attempt.
                    self.run.update(status="in_progress", conclusion=None)
                result = self.call()
                self.assertEqual(self.producer, result["captureProducer"])
                self.assertEqual(source, result["sdkRuntimeSource"])
                self.assertEqual(self.artifact, result["artifact"])
                self.assertEqual(self.raw, (self.output / "transport.zip").read_bytes())
                self.assertEqual(self.original_plan, (self.output / "plan/impact-plan.json").read_bytes())
                self.assertEqual(result, json.loads((self.output / "capture-transport.json").read_bytes()))
                self.assertEqual({"original", "transport.zip", "plan", "capture-transport.json"},
                                 {path.name for path in self.output.iterdir()})
                for name, raw in self.files.items():
                    self.assertEqual(raw, (self.output / "original" / name).read_bytes())
                self.assertEqual(sorted(self.files), [row["relativePath"] for row in
                    regular_file_inventory(self.output / "original", allow_empty=True)])
        self.assertEqual(self.original_plan, self.plan_path.read_bytes())

    def test_exact_observed_run_job_attempt_pin_and_upload_identity_required(self):
        baseline = deepcopy((self.run, self.jobs, self.artifact, self.commit))
        cases = ("run", "attempt", "job", "job-status", "job-run", "job-head",
                 "duplicate-job", "missing-job", "pin", "commit-tree", "parents", "artifact-run",
                 "artifact-head", "name", "unqualified-name", "digest", "expired", "before", "after")
        for case in cases:
            self.run, self.jobs, self.artifact, self.commit = deepcopy(baseline)
            if case == "run": self.run["id"] = 72
            elif case == "attempt": self.run["run_attempt"] = 1
            elif case == "job": self.jobs[0]["name"] = "product-validation / runtime-aggregate-attestation"
            elif case == "job-status": self.jobs[0]["conclusion"] = "failure"
            elif case == "job-run": self.jobs[0]["run_id"] = 72
            elif case == "job-head": self.jobs[0]["head_sha"] = "e" * 40
            elif case == "duplicate-job": self.jobs.append(deepcopy(self.jobs[0]))
            elif case == "missing-job": self.jobs.clear()
            elif case == "pin": self.run["referenced_workflows"][0]["sha"] = "d" * 40
            elif case == "commit-tree": self.commit["tree"]["sha"] = "e" * 40
            elif case == "parents": self.commit["parents"].reverse()
            elif case == "artifact-run": self.artifact["workflow_run"]["id"] = 72
            elif case == "artifact-head": self.artifact["workflow_run"]["head_sha"] = "e" * 40
            elif case == "name": self.artifact["name"] = self.artifact["name"].replace("attempt-2", "attempt-3")
            elif case == "unqualified-name": self.artifact["name"] = self.artifact["name"].removesuffix("-attempt-2")
            elif case == "digest": self.artifact["digest"] = "sha256:" + "d" * 64
            elif case == "expired": self.artifact["expired"] = True
            elif case == "before": self.artifact["created_at"] = "2026-09-11T09:15:00Z"
            else: self.artifact["created_at"] = "2026-09-11T10:31:00Z"
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())
        self.assertEqual(self.original_plan, self.plan_path.read_bytes())

    def test_completed_original_uploader_survives_enclosing_run_status_regression(self):
        self.source("current-runtime")
        self.run["status"] = "queued"
        result = self.call()
        self.assertEqual(self.run, result["observed"][0]["run"])
        self.assertEqual(self.producer, result["captureProducer"])
        self.assertEqual(self.raw, (self.output / "transport.zip").read_bytes())

    def test_wrong_source_layout_and_observed_consumer_reject(self):
        for case in ("wrong-layout", "extra-root", "missing-root", "directory-is-file", "wrong-selection",
                     "selection-type", "consumer-type", "wrong-producer", "current-plan"):
            self.source("current-runtime" if case == "current-plan" else "released-default")
            changes = {}
            if case == "wrong-layout": changes["expected_source"] = "current-runtime"
            elif case == "extra-root": self.files["unselected/file"] = b"extra"
            elif case == "missing-root": del self.files["current-contract/original-receipt.json"]
            elif case == "directory-is-file":
                del self.files["current-contract/original-receipt.json"]
                self.files["current-contract"] = b"not a directory"
            elif case == "wrong-selection": self.files["selection.json"] = canonical_json_bytes({"source": "current-runtime"})
            elif case == "selection-type": self.files["selection.json"] = b"[]\n"
            elif case == "consumer-type": self.files["transport.json"] = canonical_json_bytes({"consumer": []})
            elif case == "wrong-producer":
                self.files["transport.json"] = canonical_json_bytes({"consumer": {
                    "producer": {**self.producer, "runAttempt": 1}}})
            else: self.files["runtime-capture/plan/impact-plan.json"] = canonical_json_bytes({**self.plan, "pullRequest": 32})
            self.archive()
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call(**changes)
            self.assertFalse(self.output.exists())

    def test_archive_escape_symlink_duplicate_and_tamper_reject(self):
        for case in ("escape", "absolute", "symlink", "duplicate", "tamper"):
            self.source("released-default")
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                for name, raw in self.files.items():
                    archive.writestr(name, raw)
                if case in ("escape", "absolute"):
                    archive.writestr("../escaped" if case == "escape" else "/escaped", b"unsafe")
                elif case == "symlink":
                    link = zipfile.ZipInfo("sdk-inputs/link")
                    link.create_system = 3
                    link.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(link, "../../escaped")
                elif case == "duplicate":
                    with self.assertWarns(UserWarning):
                        archive.writestr("selection.json", self.files["selection.json"])
            self.raw = output.getvalue()
            self.artifact.update(digest=sha256_bytes(self.raw), size_in_bytes=len(self.raw))
            if case == "tamper": self.raw += b"changed download bytes"
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())
            self.assertFalse((self.work / "escaped").exists())

    def test_original_plan_and_privately_extracted_input_rechecks_prevent_publication(self):
        extract = capture.safe_extract
        for case in ("source-plan", "captured-plan", "extracted-input", "archive"):
            def mutate_after_real_extract(archive, destination, *args, **kwargs):
                result = extract(archive, destination, *args, **kwargs)
                path = {"source-plan": self.plan_path,
                        "captured-plan": Path(destination).parent / "plan/impact-plan.json",
                        "extracted-input": Path(destination) / "sdk-inputs/synthetic-input.json",
                        "archive": Path(archive)}[case]
                path.write_bytes(path.read_bytes() + b"changed after capture\n")
                return result
            try:
                with self.subTest(case=case), patch.object(capture, "safe_extract", side_effect=mutate_after_real_extract), \
                        self.assertRaisesRegex(ValueError, "changed before capture publication"):
                    self.call()
                self.assertFalse(self.output.exists())
            finally:
                self.plan_path.write_bytes(self.original_plan)

    def test_late_extracted_input_mutation_rejects_before_publication(self):
        def mutate_before_copy(source, destination, **kwargs):
            input_path = source / "original/sdk-inputs/synthetic-input.json"
            input_path.write_bytes(input_path.read_bytes() + b"late mutation\n")
            return publish_regular_tree(source, destination, **kwargs)

        with patch.object(capture, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.call()
        self.assertFalse(self.output.exists())

    def test_invalid_authority_and_output_overlap_reject_before_http(self):
        cases = ({"expected_source": "unknown"}, {"expected_source": []}, {"token": None}, {"token": ""},
                 {"artifact_id": True}, {"artifact_id": 0}, {"artifact_sha256": "not-a-digest"})
        for arguments in cases:
            with self.subTest(arguments=arguments), patch.object(capture, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaises(ValueError):
                self.call(**arguments)
            observe.assert_not_called()
            self.assertFalse(self.output.exists())
        self.plan["remoteBuildAuthorized"] = False
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaisesRegex(ValueError, "authorized"):
            self.call()
        observe.assert_not_called()
        self.plan["remoteBuildAuthorized"] = True
        linked = self.work / "linked"
        linked.symlink_to(self.root, target_is_directory=True)
        for destination in (self.root, self.root / "nested", linked / "nested", self.plan_path):
            self.output = destination
            before = regular_file_inventory(self.root)
            with self.subTest(destination=destination), patch.object(capture, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()
            self.assertEqual(before, regular_file_inventory(self.root))

    def test_existing_output_is_never_overwritten(self):
        self.call()
        before = regular_file_inventory(self.output, allow_empty=True)
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaisesRegex(ValueError, "must not exist"):
            self.call()
        observe.assert_not_called()
        self.assertEqual(before, regular_file_inventory(self.output, allow_empty=True))



import sdk_handoff
from runtime_reference_transport import SDK_INPUT_REFERENCE_NAME, SDK_REFERENCE_NAME

class SdkBindingTest(unittest.TestCase):
    archive = fixture.RuntimeAggregateUploadTest.archive
    def setUp(self):
        fixture.RuntimeAggregateUploadTest.setUp(self)
        self.jobs[0]['name']='product-validation / sdk-inputs'
        self.jobs.append({**self.jobs[0],'id':82,'name':'product-validation / runtime-aggregate-attestation'})
        self.artifact['name']=f"codex-agent-sdk-inputs-{self.producer['tree']}-attempt-2"
        self.current_producer={**self.producer,'runId':72,'runAttempt':1,'commit':'d'*40,'tree':'e'*40}
        self.current_plan={**self.plan,'validationCommit':'d'*40,'validationTree':'e'*40}
        self.current_run={**deepcopy(self.run),'id':72,'run_attempt':1}
        self.current_jobs=[{**self.jobs[0],'id':83,'run_id':72}]
        self.current_commit={**self.commit,'sha':'d'*40,'tree':{'sha':'e'*40}}
        self.runtime_artifact={**deepcopy(self.artifact),'id':703,'digest':'sha256:'+'e'*64,
            'archive_download_url':self.artifact['archive_download_url'].replace('701','703'),
            'name':f"codex-agent-runtime-aggregate-release-handoff-{self.producer['tree']}-attempt-2"}
        self.runtime_source=dict(artifactId=703,artifactSha256=self.runtime_artifact['digest'],
            producer=self.producer,workflowSha=self.pin,buildKey=self.key,metadataReceiptSha256=self.digest)
        self.transport=dict(artifact=self.runtime_artifact,captureProducer=self.producer,
            observed=[],aggregateBuildKey=self.key,aggregateReceiptSha256=self.digest)
        self.files={'sdk-inputs/content':b'opaque SDK product bytes remain subject to full signed gates',
            'runtime-capture/plan/impact-plan.json':canonical_json_bytes(self.plan),
            'runtime-capture/capture-transport.json':canonical_json_bytes(self.transport),
            'runtime-capture/original/body.bin':b'opaque original Runtime body'}
        self.plan_path.write_bytes(canonical_json_bytes(self.current_plan))
        self.downloads=[]
        self.prepare()
    def prepare(self,thin=False):
        def archive(files):
            out=io.BytesIO()
            with zipfile.ZipFile(out,'w') as z:
                for name,raw in files.items():z.writestr(name,raw)
            return out.getvalue()
        files=deepcopy(self.files)
        if thin:
            inventory=sorted([dict(relativePath=k,bytes=len(v),sha256=sha256_bytes(v)) for k,v in files.items()],key=lambda r:r['relativePath'])
            del files['runtime-capture/original/body.bin']
            files[SDK_REFERENCE_NAME]=canonical_json_bytes(dict(schemaVersion=1,source=self.runtime_source,inventory=inventory))
        self.raw=archive(files)
        self.artifact.update(digest=sha256_bytes(self.raw),size_in_bytes=len(self.raw))
        self.source=dict(artifactId=701,artifactSha256=self.artifact['digest'],producer=self.producer,workflowSha=self.pin)
        self.binding=dict(schemaVersion=1,source=deepcopy(self.source),runtimeSource=deepcopy(self.runtime_source),
            planSha256=sha256_bytes(canonical_json_bytes(self.current_plan)))
        self.wrapper(archive)
    def wrapper(self,archive=None):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            z.writestr(SDK_INPUT_REFERENCE_NAME,canonical_json_bytes(self.binding))
            z.writestr('runtime-capture/plan/impact-plan.json',canonical_json_bytes(self.current_plan))
        self.current_raw=out.getvalue()
        self.current_artifact={**deepcopy(self.artifact),'id':702,'name':f"codex-agent-sdk-inputs-{'e'*40}-attempt-1",
            'archive_download_url':self.artifact['archive_download_url'].replace('701','702'),
            'workflow_run':{**deepcopy(self.artifact['workflow_run']),'id':72},
            'digest':sha256_bytes(self.current_raw),'size_in_bytes':len(self.current_raw)}
    def api(self,url,token):
        self.assertEqual('synthetic-token',token)
        if '/actions/artifacts/702' in url:return json.dumps(self.current_artifact).encode()
        if '/actions/artifacts/703' in url:return json.dumps(self.runtime_artifact).encode()
        if '/actions/runs/72/attempts/1/jobs?' in url:return json.dumps({'jobs':self.current_jobs}).encode()
        if url.endswith('/actions/runs/72/attempts/1'):return json.dumps(self.current_run).encode()
        if url.endswith('/git/commits/'+'d'*40):return json.dumps(self.current_commit).encode()
        return fixture.RuntimeAggregateUploadTest.api(self,url,token)
    def call(self,**changes):
        def validate(path,root,**kwargs):
            value=json.loads(path.read_bytes())
            expected=self.plan if 'expected_revision' in kwargs else self.current_plan
            if value!=expected:raise ValueError('original plan mismatch')
            return deepcopy(expected)
        def download(artifact,token,destination,**kwargs):
            self.downloads.append(artifact['id'])
            Path(destination).write_bytes({701:self.raw,702:self.current_raw}[artifact['id']])
        def runtime(plan,destination,**kwargs):
            if changes.get('completed_frozen') is not None:
                raise AssertionError('Completed SDK input capture rehydrated raw Runtime')
            self.assertEqual(self.runtime_source['artifactId'],kwargs['artifact_id'])
            self.assertEqual(self.producer,kwargs['original_producer'])
            (destination/'original').mkdir(parents=True)
            (destination/'original/body.bin').write_bytes(self.files['runtime-capture/original/body.bin'])
        with patch.object(capture,'_validate_plan',side_effect=validate),patch('reuse.api_request',side_effect=self.api), \
                patch.object(capture,'download_artifact_to_file',side_effect=download), \
                patch.object(sdk_handoff,'_ensure_observed_sdk_commit'), \
                patch.object(capture,'capture_runtime_aggregate_release_upload',side_effect=runtime):
            return capture.capture_sdk_inputs_upload(self.plan_path,self.output,
                artifact_id=702,artifact_sha256=self.current_artifact['digest'],trusted_workflow_sha=self.pin,
                expected_source='current-runtime',repository_root=self.root,environ={'GITHUB_RUN_ID':'72','GITHUB_RUN_ATTEMPT':'1'},
                token='synthetic-token',**{'retained_sdk_inputs_source':self.source,**changes})
    def test_legacy_and_thin_sources_preserve_origin_and_one_worker_body_read(self):
        for thin in (False,True):
            with self.subTest(thin=thin):
                self.prepare(thin);self.output=self.work/f'output-{thin}';self.downloads=[]
                self.call()
                self.assertEqual([702,701],self.downloads)
                self.assertEqual(self.raw,(self.output/'plan/sdk-input-source.zip').read_bytes())
                self.assertEqual(canonical_json_bytes(self.plan),(self.output/'plan/sdk-input-source-plan.json').read_bytes())
                self.assertEqual(self.plan_path.read_bytes(),(self.output/'original/runtime-capture/plan/impact-plan.json').read_bytes())
                capture._verify_retained_sdk_upload_archive(self.output,self.current_artifact)
                (self.output/'original/sdk-inputs/content').write_bytes(b'changed')
                with self.assertRaises(ValueError):capture._verify_retained_sdk_upload_archive(self.output,self.current_artifact)
    def test_completed_runtime_keeps_sdk_bytes_and_native_origin_without_raw_hydration(self):
        from ci.tests.test_completed_frozen_reuse import CompletedFrozenReuseTest
        native = CompletedFrozenReuseTest()
        native.setUp()
        cap, _ = native.fetched(self.work)
        for thin in (False, True):
            with self.subTest(thin=thin):
                self.prepare(thin)
                self.output = self.work / f'deferred-{thin}'
                self.downloads = []
                transport = self.call(completed_frozen=cap)
                self.assertEqual('completed-frozen-runtime', transport['readScope'])
                self.assertEqual([702, 701], self.downloads)
                self.assertFalse((self.output / 'original/runtime-capture/original').exists())
                self.assertEqual(self.files['sdk-inputs/content'],
                    (self.output / 'original/sdk-inputs/content').read_bytes())
                self.assertEqual(self.raw, (self.output / 'plan/sdk-input-source.zip').read_bytes())
                # A full historical reader must not accept a deferred private capture.
                with self.assertRaises(ValueError):
                    capture._verify_retained_sdk_upload_archive(self.output, self.current_artifact)

    def test_native_sdk_members_avoid_whole_source_transfer_but_reject_changed_bytes(self):
        from contextlib import contextmanager
        import reuse_qualification as qualification
        from ci.tests.test_completed_frozen_reuse import CompletedFrozenReuseTest
        native = CompletedFrozenReuseTest()
        native.setUp()
        sdk, _, _, _ = native.sdk_fixture()
        sdk['spec']['sdkInputs'] = dict(source=self.source, runtimeSource=self.runtime_source,
            bytes=len(self.raw), jobId=self.jobs[0]['id'])
        def download(*args, **kwargs):
            self.assertEqual(self.source['artifactId'], args[0])
            self.assertEqual(self.source['artifactSha256'], args[1])
            kwargs['destination'].write_bytes(self.raw)
            return self.artifact, kwargs['destination']
        with patch('reuse.api_request', side_effect=self.api), \
                patch.object(capture, '_download_contract_ci_upload', side_effect=download) as whole, \
                patch.object(sdk_handoff, '_ensure_observed_sdk_commit'), \
                patch.object(capture, '_validate_plan', return_value=self.plan):
            sdk['proof']['sdkInputs'] = qualification._issue_sdk_input_members(
                sdk['spec'], self.work, self.root, 'synthetic-token')
        whole.assert_called_once()
        self.assertEqual(3, len(sdk['proof']['sdkInputs']['files']))
        cap = qualification.CompletedFrozenReuse(native.spec, native.receipts.values(),
            qualification._COMPLETED_FROZEN, revision='d' * 40, originals=native.qualified['originals'], sdk=sdk)
        @contextmanager
        def ranges(*args):
            with zipfile.ZipFile(io.BytesIO(self.raw)) as archive:
                yield archive, None
        with patch('runtime_reference_archive.open_reference_archive', side_effect=ranges) as opened, \
                patch('hydrated_evidence.copy', return_value=False):
            self.call(completed_frozen=cap)
            self.assertEqual([702], self.downloads)
            opened.assert_called_once()
            self.assertFalse((self.output / 'plan/sdk-input-source.zip').exists())
            self.assertFalse((self.output / 'original/runtime-capture/original').exists())
            self.assertEqual(self.files['sdk-inputs/content'], (self.output / 'original/sdk-inputs/content').read_bytes())
            self.assertEqual(canonical_json_bytes(self.plan), (self.output / 'plan/sdk-input-source-plan.json').read_bytes())
            self.assertEqual(self.plan_path.read_bytes(), (self.output / 'original/runtime-capture/plan/impact-plan.json').read_bytes())
            with self.assertRaises(ValueError):
                capture._verify_retained_sdk_upload_archive(self.output, self.current_artifact)
            original = self.raw
            output = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(output, 'w') as changed:
                for row in source.infolist():
                    body = source.read(row)
                    changed.writestr(row.filename, b'x' * len(body) if row.filename == 'sdk-inputs/content' else body)
            self.raw = output.getvalue()
            self.output = self.work / 'changed-native-member'
            with self.assertRaisesRegex(ValueError, 'immutable digest'):
                self.call(completed_frozen=cap)
            self.assertFalse(self.output.exists())

    def test_pin_and_native_origin_failures_never_publish(self):
        for case in ('no-pin','wrong-pin','source-failed','source-window','runtime-failed','wrong-runtime','source-digest','old-plan'):
            self.prepare();self.output=self.work/case
            original=deepcopy((self.jobs,self.artifact,self.raw))
            kwargs={}
            if case=='no-pin':kwargs['retained_sdk_inputs_source']=None
            elif case=='wrong-pin':kwargs['retained_sdk_inputs_source']={**self.source,'artifactId':999}
            elif case=='source-failed':self.jobs[0]['conclusion']='failure'
            elif case=='source-window':self.artifact['created_at']='2026-09-11T11:15:00Z'
            elif case=='runtime-failed':self.jobs[1]['conclusion']='failure'
            elif case=='wrong-runtime':self.binding['runtimeSource']['buildKey']='sha256:'+'0'*64;self.wrapper()
            elif case=='source-digest':self.raw+=b'changed'
            else:
                self.files['runtime-capture/plan/impact-plan.json']=canonical_json_bytes(self.current_plan);self.prepare()
            with self.subTest(case=case),self.assertRaises(ValueError):self.call(**kwargs)
            self.assertFalse(self.output.exists())
            self.jobs,self.artifact,self.raw=original
            self.files['runtime-capture/plan/impact-plan.json']=canonical_json_bytes(self.plan)
    def test_staging_is_control_only_and_performs_no_download_or_content_admission(self):
        with patch.object(capture,'_validate_plan',return_value=self.current_plan), \
                patch.object(capture,'_observe_ci_producer_jobs',side_effect=AssertionError('routing observes body')), \
                patch.object(capture,'_download_contract_ci_upload',side_effect=AssertionError('routing downloads body')):
            sdk_handoff.stage_sdk_input_binding(self.plan_path,self.output,sdk_inputs_source=self.source,
                runtime_source=self.runtime_source,repository_root=self.root,environ={'GITHUB_RUN_ID':'72','GITHUB_RUN_ATTEMPT':'1'})
        rows=regular_file_inventory(self.output)
        self.assertEqual(2,len(rows));self.assertLess(sum(row['bytes'] for row in rows),4096)

    def test_binding_cannot_chain_sources_or_change_current_plan(self):
        original_files=deepcopy(self.files)
        for case in ('nested-source', 'current-plan', 'future-sdk', 'foreign-runtime'):
            self.files=deepcopy(original_files);self.prepare();self.output=self.work/case
            if case=='nested-source':
                self.files[SDK_INPUT_REFERENCE_NAME]=canonical_json_bytes(self.binding);self.prepare()
            elif case=='current-plan':self.binding['planSha256']='sha256:'+'0'*64
            elif case=='future-sdk':
                self.source['producer']={**self.source['producer'],'runId':73}
                self.binding['source']=deepcopy(self.source)
            else:self.binding['runtimeSource']['producer']['repository']='foreign/repository'
            self.wrapper()
            with self.subTest(case=case),self.assertRaises(ValueError):self.call()
            self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
