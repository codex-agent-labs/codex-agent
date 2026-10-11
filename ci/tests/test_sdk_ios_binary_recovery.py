"""Original transport recovery using tiny fixtures, not hosted acceptance."""

from contextlib import contextmanager
from copy import deepcopy
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

from ci.tests import test_sdk_ios_package_upload as fixture
from ci import sdk_ios_binary_recovery as recovery
from products.inventory import canonical_json_bytes, regular_file_inventory, load_canonical_json_bytes
from products.restore import verification_session
from ci.tests.product_chain_support import write_receipt
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object


class IosBinaryRecoveryTest(unittest.TestCase):
    phase, target = "binary", "ios"
    api = fixture.SdkIosBinaryUploadTest.api
    archive = fixture.SdkIosBinaryUploadTest.archive
    setUp = fixture.SdkIosBinaryUploadTest.setUp

    @contextmanager
    def gates(self):
        self.run["conclusion"] = "failure"
        self.jobs[0]["name"] += f" ({load_canonical_json_bytes(self.receipt_bytes)['buildKey']}, ..."
        original_api = self.api
        def api(url, token):
            if url.startswith("https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/71/artifacts?"):
                import json
                return json.dumps({"artifacts": [self.artifact]}).encode()
            return original_api(url, token)
        @contextmanager
        def ranges(artifact, token):
            with zipfile.ZipFile(io.BytesIO(self.raw)) as archive:
                yield archive, None
        with patch.object(recovery.products, "_validate_plan", return_value=self.plan), \
                patch("reuse.api_request", side_effect=api), \
                patch.object(recovery, "open_reference_archive", side_effect=ranges), \
                patch.object(recovery.products, "download_artifact_to_file",
                    side_effect=lambda artifact, token, destination, **kwargs: Path(destination).write_bytes(self.raw)):
            yield

    def capture(self, **changes):
        receipt = load_canonical_json_bytes(self.receipt_bytes)
        return recovery.capture_prior_ios_binary(self.plan_path, self.plan,
            {**self.producer, "runId": 72}, receipt["buildKey"], self.output, self.work,
            repository_root=self.root, environ={}, trusted_workflow_sha=self.pin,
            token="synthetic-token", attempts=(self.run,), **changes)

    def replay(self):
        return recovery.replay_prior_ios_binary(self.output, self.work, plan=self.plan,
            plan_path=self.plan_path, repository_root=self.root,
            consumer_producer={**self.producer, "runId": 72}, trusted_workflow_sha=self.pin,
            token="synthetic-token", environ={})

    def test_session_downloads_once_but_observes_every_replay_and_expires(self):
        with self.gates():
            original = self.capture()
            before = regular_file_inventory(self.output)
            with patch.object(recovery.products, "capture_sdk_ios_binary_upload",
                    wraps=recovery.products.capture_sdk_ios_binary_upload) as capture, \
                    patch.object(recovery, "locate_original_apple_upload",
                        wraps=recovery.locate_original_apple_upload) as observe:
                with verification_session() as session:
                    for _ in range(3):
                        self.assertEqual(original, self.replay())
                    self.assertEqual(1, capture.call_count)
                    self.assertEqual(3, observe.call_count)
                    self.assertEqual(1, session["downloadedArtifactCount"])
                    self.assertEqual(len(self.raw), session["downloadedArtifactBytes"])
                with verification_session():
                    self.assertEqual(original, self.replay())
                self.assertEqual(2, capture.call_count)
                self.assertEqual(original, self.replay())  # No outer session: full authentication.
                self.assertEqual(3, capture.call_count)
            self.assertEqual(before, regular_file_inventory(self.output))

    def test_session_hit_rejects_changed_live_provenance_before_download(self):
        with self.gates():
            self.capture()
            with verification_session(), patch.object(recovery, "_source_identity", return_value="policy"), \
                    patch.object(recovery.products, "capture_sdk_ios_binary_upload",
                        wraps=recovery.products.capture_sdk_ios_binary_upload) as capture:
                self.replay()
                for source, changes in (
                    (self.run, {"conclusion": "success"}),
                    (self.run, {"pull_requests": [{"number": 32}]}),
                    (self.run["head_repository"], {"fork": True}),
                    (self.jobs[0], {"conclusion": "failure"}),
                    (self.artifact, {"expired": True}),
                    (self.artifact, {"size_in_bytes": len(self.raw) + 1}),
                    (self.artifact, {"created_at": "2026-09-11T11:15:00Z"}),
                    (self.artifact, {"digest": "sha256:" + "0" * 64}),
                    (self.plan, {"remoteBuildAuthorized": False}),
                ):
                    with self.subTest(changes=changes), patch.dict(source, changes), self.assertRaises(ValueError):
                        self.replay()
                self.assertEqual(1, capture.call_count)

    def test_session_hit_hashes_actual_compact_bytes_even_with_restored_mtime(self):
        with self.gates():
            record, = self.capture()
            with verification_session(), patch.object(recovery, "_source_identity", return_value="policy"), \
                    patch.object(recovery.products, "capture_sdk_ios_binary_upload",
                        wraps=recovery.products.capture_sdk_ios_binary_upload) as capture:
                self.replay()
                path = self.work / record["objectPath"]
                before = path.stat()
                path.write_bytes(b"x" * before.st_size)
                os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
                with self.assertRaisesRegex(ValueError, "compact shard differs"):
                    self.replay()
                self.assertEqual(1, capture.call_count)

    def test_failed_comparison_and_late_mutation_never_seal_session(self):
        with self.gates():
            self.capture()
            with verification_session() as session, \
                    patch.object(recovery, "_source_identity", return_value="policy"):
                with patch.object(recovery.products, "capture_sdk_ios_binary_upload",
                        side_effect=ValueError("whole archive digest mismatch")), \
                        self.assertRaisesRegex(ValueError, "whole archive digest mismatch"):
                    self.replay()
                self.assertFalse(session.get("sdkIosOriginals"))
                original_record = recovery._record
                original_plan = self.plan_path.read_bytes()
                def mutate(*args):
                    record = original_record(*args)
                    self.plan_path.write_bytes(original_plan + b" ")
                    return record
                with patch.object(recovery, "_record", side_effect=mutate), \
                        self.assertRaisesRegex(ValueError, "changed during readmission"):
                    self.replay()
                self.assertFalse(session.get("sdkIosOriginals"))
                self.plan_path.write_bytes(original_plan)
                with patch.object(recovery.products, "capture_sdk_ios_binary_upload",
                        wraps=recovery.products.capture_sdk_ios_binary_upload) as capture:
                    self.replay()
                    self.replay()
                    self.assertEqual(1, capture.call_count)

    def test_policy_change_reauthenticates_and_windows_keeps_full_path(self):
        with self.gates():
            self.capture()
            with verification_session(), patch.object(recovery, "_source_identity", return_value="policy-1") as policy, \
                    patch.object(recovery.products, "capture_sdk_ios_binary_upload",
                        wraps=recovery.products.capture_sdk_ios_binary_upload) as capture:
                self.replay()
                policy.return_value = "policy-2"
                self.replay()
                self.assertEqual(2, capture.call_count)
                with patch.object(recovery, "_is_windows", return_value=True):
                    self.replay()
                    self.replay()
                self.assertEqual(4, capture.call_count)

    def test_exact_original_capture_and_fresh_replay_preserve_receipt(self):
        with self.gates(), patch.object(recovery.products, "capture_sdk_ios_binary_upload",
                wraps=recovery.products.capture_sdk_ios_binary_upload) as capture:
            records = self.capture()
            before = regular_file_inventory(self.output, allow_empty=True)
            replay = recovery.replay_prior_ios_binary(self.output, self.work, plan=self.plan,
                plan_path=self.plan_path, repository_root=self.root,
                consumer_producer={**self.producer, "runId": 72}, trusted_workflow_sha=self.pin,
                token="synthetic-token", environ={})
        self.assertEqual(2, capture.call_count)
        self.assertTrue(all(call.kwargs["compact_recovery"] is True for call in capture.call_args_list))
        self.assertEqual(records, replay)
        self.assertEqual(before, regular_file_inventory(self.output, allow_empty=True))
        self.assertEqual(self.receipt_bytes,
            (self.output / "sdk-ios/binary/ios/original/shard/phase-receipt.json").read_bytes())
        capture = self.output / "sdk-ios/binary/ios"
        self.assertEqual({"capture-transport.json", "original"}, {path.name for path in capture.iterdir()})
        self.assertEqual({"shard"}, {path.name for path in (capture / "original").iterdir()})
        for name, raw in self.files.items():
            if name.startswith("shard/"):
                self.assertEqual(raw, (capture / "original" / name).read_bytes())
        self.assertEqual({"sdk-ios/binary/ios/capture-transport.json",
            *("sdk-ios/binary/ios/original/" + name for name in self.files if name.startswith("shard/"))},
            {row["relativePath"] for row in before})

    def test_failed_original_job_cannot_be_recovered(self):
        with self.gates(), patch.object(recovery.products, "capture_sdk_ios_binary_upload") as capture:
            self.jobs[0]["conclusion"] = "failure"
            self.assertEqual([], self.capture())
            capture.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_ambiguous_original_job_and_wrong_matrix_key_fail_closed(self):
        with self.gates(), patch.object(recovery.products, "capture_sdk_ios_binary_upload") as capture:
            self.jobs.append(deepcopy(self.jobs[0]))
            with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
                self.capture()
            self.jobs.pop()
            self.jobs[0]["name"] = "product-validation / sdk-sdk-ios-binary-ios (sha256:" + "0" * 64 + ", ..."
            with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
                self.capture()
            capture.assert_not_called()

    def test_same_or_different_pr_attempt_is_not_recovery_authority(self):
        with self.gates():
            prior = deepcopy(self.run)
            prior["id"] = 72
            with self.assertRaisesRegex(ValueError, "earlier failed"):
                recovery._require_prior(self.plan, {**self.producer, "runId": 72}, prior)
            prior = deepcopy(self.run)
            prior["pull_requests"][0]["number"] = 32
            with self.assertRaisesRegex(ValueError, "earlier failed"):
                recovery._require_prior(self.plan, {**self.producer, "runId": 72}, prior)

    def test_tampered_compact_shard_rejected_after_full_original_authentication(self):
        with self.gates():
            record, = self.capture()
            (self.work / record["objectPath"]).write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "compact shard differs"):
                recovery.replay_prior_ios_binary(self.output, self.work, plan=self.plan,
                    plan_path=self.plan_path, repository_root=self.root,
                    consumer_producer={**self.producer, "runId": 72}, trusted_workflow_sha=self.pin,
                    token="synthetic-token", environ={})

    def test_malformed_expiration_and_wrong_discovery_key_reject_before_capture(self):
        with self.gates(), patch.object(recovery.products, "capture_sdk_ios_binary_upload") as capture:
            self.artifact["expired"] = None
            with self.assertRaisesRegex(ValueError, "expiration"):
                self.capture()
            self.artifact["expired"] = False
            actual = recovery.products.validate_phase_receipt
            def wrong(raw):
                receipt = actual(raw)
                return {**receipt, "buildKey": "sha256:" + "0" * 64}
            with patch.object(recovery.products, "validate_phase_receipt", side_effect=wrong), \
                    self.assertRaisesRegex(ValueError, "discovery receipt"):
                self.capture()
            capture.assert_not_called()

    def test_extra_capture_family_rejected(self):
        with self.gates():
            self.capture()
            (self.output / "extra").write_bytes(b"unrelated")
            with self.assertRaisesRegex(ValueError, "unexpected capture family"):
                recovery.replay_prior_ios_binary(self.output, self.work, plan=self.plan,
                    plan_path=self.plan_path, repository_root=self.root,
                    consumer_producer={**self.producer, "runId": 72}, trusted_workflow_sha=self.pin,
                    token="synthetic-token", environ={})

    def test_conflicting_verified_same_key_candidates_never_publish(self):
        # Test only collision selection here. The exact capture/ZIP/shard gates
        # are exercised without these mocks by the original-preservation test.
        with self.gates():
            prior = {**self.run, "id": 70}
            receipts = [load_canonical_json_bytes(self.receipt_bytes)]
            receipts.append({**receipts[0], "producer": {**self.producer, "runId": 70},
                "outputs": [{**receipts[0]["outputs"][0], "sha256": "sha256:" + "0" * 64},
                            *receipts[0]["outputs"][1:]]})
            index = -1
            @contextmanager
            def ranges(artifact, token):
                nonlocal index
                index += 1
                incoming = io.BytesIO()
                with zipfile.ZipFile(incoming, "w") as archive:
                    archive.writestr("shard/phase-receipt.json", canonical_json_bytes(receipts[index]))
                with zipfile.ZipFile(incoming) as archive:
                    yield archive, None
            def listing(url, field, token):
                if field == "artifacts":
                    return [self.artifact]
                run = 70 if "/70/" in url else 71
                return [{**self.jobs[0], "run_id": run}]
            with patch.object(recovery.products, "paginated_items", side_effect=listing), \
                    patch.object(recovery.products, "_contract_ci_upload_metadata", return_value=self.artifact), \
                    patch.object(recovery.products, "_require_artifact_job_window"), \
                    patch.object(recovery, "open_reference_archive", side_effect=ranges), \
                    patch.object(recovery.products, "capture_sdk_ios_binary_upload"), \
                    patch.object(recovery, "verify_phase_shard", side_effect=lambda *args:
                        {"receiptBytes": canonical_json_bytes(receipts[index]), "receipt": receipts[index]}), \
                    self.assertRaisesRegex(ValueError, "conflicting output inventories"):
                recovery.capture_prior_ios_binary(self.plan_path, self.plan,
                    {**self.producer, "runId": 72}, receipts[0]["buildKey"], self.output, self.work,
                    repository_root=self.root, environ={}, trusted_workflow_sha=self.pin,
                    token="synthetic-token", attempts=(self.run, prior))
        self.assertFalse(self.output.exists())

    def test_full_original_authentication_failure_cannot_admit_compact_custody(self):
        with self.gates():
            self.capture()
            before = regular_file_inventory(self.output)
            with patch.object(recovery.products, "capture_sdk_ios_binary_upload",
                              side_effect=ValueError("official whole archive digest mismatch")), \
                    self.assertRaisesRegex(ValueError, "whole archive digest mismatch"):
                recovery.replay_prior_ios_binary(self.output, self.work, plan=self.plan,
                    plan_path=self.plan_path, repository_root=self.root,
                    consumer_producer={**self.producer, "runId": 72}, trusted_workflow_sha=self.pin,
                    token="synthetic-token", environ={})
            self.assertEqual(before, regular_file_inventory(self.output))

    def test_full_capture_mutating_compact_custody_cannot_publish_readmission(self):
        with self.gates():
            self.capture()
            actual = recovery.products.capture_sdk_ios_binary_upload
            def mutate(*args, **kwargs):
                result = actual(*args, **kwargs)
                (self.output / "sdk-ios/binary/ios/extra").write_bytes(b"late mutation")
                return result
            with patch.object(recovery.products, "capture_sdk_ios_binary_upload", side_effect=mutate), \
                    self.assertRaisesRegex(ValueError, "changed during readmission"):
                recovery.replay_prior_ios_binary(self.output, self.work, plan=self.plan,
                    plan_path=self.plan_path, repository_root=self.root,
                    consumer_producer={**self.producer, "runId": 72}, trusted_workflow_sha=self.pin,
                    token="synthetic-token", environ={})


class JavascriptPackageRecoveryTest(unittest.TestCase):
    """Synthetic official API transport fixtures, not genuine hosted acceptance."""
    phase, target = "binary", "ios"
    api = fixture.SdkIosBinaryUploadTest.api
    archive = fixture.SdkIosBinaryUploadTest.archive
    gates = IosBinaryRecoveryTest.gates

    def setUp(self):
        fixture.SdkIosBinaryUploadTest.setUp(self)
        stage = self.work / "javascript-stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/package.tgz").write_bytes(b"synthetic packaged JavaScript bytes\n")
        (stage / "outputs/package-inventory.json").write_bytes(b'{"synthetic":true}\n')
        (stage / "outputs/package-evidence.txt").write_bytes(b"synthetic evidence, not host acceptance\n")
        manifest = write_output_manifest(stage, "sdk", "javascript", "package", "node", "0.3.0",
                                         {"package": "outputs"})
        receipt = write_receipt(self.work / "js-receipt.json", product="sdk", component="javascript",
            phase="package", target="node", outputs=manifest["outputs"], upstream=[], version="0.3.0",
            version_identity="0.3.0", context={"producer": self.producer})
        shard = self.work / "js-shard"
        verified = finalize_phase_object(stage_root=stage,
            phase_plan={name: receipt[name] for name in PHASE_PLAN_KEYS}, producer=self.producer,
            product_version="0.3.0", trust_domain="development", destination=shard)
        self.key = receipt["buildKey"]
        self.receipt_bytes = verified["receiptBytes"]
        self.jobs[0]["name"] = "product-validation / sdk-javascript-package-node"
        self.artifact["name"] = (f"codex-agent-sdk-worker-javascript-package-node-{self.key.removeprefix('sha256:')}-"
                                 f"{self.producer['tree']}-attempt-2")
        self.files = {"shard/" + row["relativePath"]: (shard / row["relativePath"]).read_bytes()
                      for row in regular_file_inventory(shard)}
        self.files["execution/diagnostic.log"] = b""
        self.archive()

    def capture(self):
        return recovery.capture_prior_javascript_package(self.plan, {**self.producer, "runId": 72},
            self.key, self.output, self.work, trusted_workflow_sha=self.pin,
            token="synthetic-token", environ={}, attempts=(self.run,))

    def replay(self):
        return recovery.replay_prior_javascript_package(self.output, self.work, plan=self.plan,
            consumer_producer={**self.producer, "runId": 72}, trusted_workflow_sha=self.pin,
            token="synthetic-token", environ={})

    def test_original_successful_package_from_failed_parent_is_preserved_and_replayed(self):
        with self.gates(), verification_session(), \
                patch.object(recovery.products, "download_artifact", wraps=recovery.products.download_artifact) as download, \
                patch.object(recovery.products, "_observe_ci_producer_jobs",
                             wraps=recovery.products._observe_ci_producer_jobs) as observe:
            records = self.capture()
            inventory = regular_file_inventory(self.output, allow_empty=True)
            self.assertEqual(records, self.replay())
            self.assertEqual(inventory, regular_file_inventory(self.output, allow_empty=True))
            self.assertEqual(1, download.call_count)
            self.assertEqual(2, observe.call_count)
        capture = self.output / "javascript/package/node"
        self.assertEqual(self.receipt_bytes, (capture / "original/shard/phase-receipt.json").read_bytes())
        self.assertEqual(self.raw, (capture / "transport.zip").read_bytes())
        for name, contents in self.files.items():
            self.assertEqual(contents, (capture / "original" / name).read_bytes())

    def test_reviewed_original_publisher_remains_selectable_after_rotation(self):
        original = "53d6ad1e4d7cfba9267894af9b302e07f7cb6656"
        run = {**self.run, "referenced_workflows": [{
            "path": f"codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@{original}",
            "sha": original, "ref": "refs/heads/reuse-authority"}]}
        self.assertEqual(original, recovery.products._runtime_prior_workflow_sha(run, "e" * 40))
        run["referenced_workflows"][0]["sha"] = "f" * 40
        self.assertIsNone(recovery.products._runtime_prior_workflow_sha(run, "e" * 40))

    def test_failed_or_live_job_is_not_admitted_and_wrong_key_is_a_miss(self):
        with self.gates():
            self.jobs[0]["conclusion"] = "failure"
            with patch.object(recovery, "_capture_javascript_package") as acquire:
                self.assertEqual([], self.capture())
                acquire.assert_not_called()
            self.jobs[0].update(conclusion=None, status="in_progress")
            with self.assertRaisesRegex(ValueError, "successful attempt"):
                self.capture()
            self.artifact["name"] = self.artifact["name"].replace(self.key.removeprefix("sha256:"), "0" * 64)
            self.assertEqual([], self.capture())

    def test_ambiguous_upload_and_wrong_window_fail_closed(self):
        with self.gates():
            listing = recovery.products.paginated_items
            def duplicate(url, field, token):
                rows = listing(url, field, token)
                return rows * 2 if field == "artifacts" else rows
            with patch.object(recovery.products, "paginated_items", side_effect=duplicate), \
                    self.assertRaisesRegex(ValueError, "ambiguous"):
                self.capture()
            self.artifact["created_at"] = "2026-09-11T11:15:00Z"
            with self.assertRaises(ValueError):
                self.capture()
        self.assertFalse(self.output.exists())

    def test_tampered_materialization_or_transport_cannot_replay(self):
        with self.gates():
            self.capture()
            original = self.output / "javascript/package/node/original/execution/diagnostic.log"
            original.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "authenticated original upload"):
                self.replay()
            original.write_bytes(b"")
            transport = self.output / "javascript/package/node/capture-transport.json"
            value = load_canonical_json_bytes(transport.read_bytes())
            value["artifact"]["size_in_bytes"] += 1
            transport.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(ValueError, "authenticated original upload"):
                self.replay()

    def test_conflicting_same_key_packages_never_publish(self):
        with self.gates():
            other = {**self.run, "id": 70}
            original = load_canonical_json_bytes(self.receipt_bytes)
            changed = {**original, "outputs": [{**original["outputs"][0], "sha256": "sha256:" + "0" * 64}]}
            listing = recovery.products.paginated_items
            def prior_listing(url, field, token):
                rows = listing(url.replace("/70/", "/71/"), field, token)
                return [{**row, "run_id": 70} for row in rows] if field == "jobs" and "/70/" in url else rows
            with patch.object(recovery.products, "paginated_items", side_effect=prior_listing), \
                    patch.object(recovery, "_capture_javascript_package", side_effect=(original, changed)), \
                    self.assertRaisesRegex(ValueError, "conflicting output inventories"):
                recovery.capture_prior_javascript_package(self.plan, {**self.producer, "runId": 72},
                    self.key, self.output, self.work, trusted_workflow_sha=self.pin,
                    token="synthetic-token", environ={}, attempts=(self.run, other))
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
