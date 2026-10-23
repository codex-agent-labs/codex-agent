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
from products import restore as product_restore
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
        def ranges(artifact, token, **_policy):
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

    def test_sdk_original_reference_keeps_binary_upstream_and_authenticates_selected_members(self):
        from runtime_reference_transport import (stage_original_reference_handoff,
            resolve_original_reference_handoff, validate_original_references)
        from products.inventory import snapshot_regular_tree
        from ci.tests.test_runtime_reference_transport import RangeOpener
        receipt = load_canonical_json_bytes(self.receipt_bytes)
        prefix = 'product-resume-state/prior-failed-sdk/sdk-ios/binary/ios/original'
        with self.gates():
            cold = self.work / 'reference-cold'
            recovery.products.capture_sdk_ios_binary_upload(self.plan_path, cold,
                binary_receipt_path=self.receipt_path, artifact_id=self.artifact['id'],
                artifact_sha256=self.artifact['digest'], trusted_workflow_sha=self.pin,
                repository_root=self.root, environ={}, token='synthetic-token', compact_recovery=True)
            roots = {name: self.work / 'reference-inputs' / name for name in
                     ('product-resume-inputs', 'product-resume-state')}
            roots['product-resume-inputs'].mkdir(parents=True)
            (roots['product-resume-inputs'] / 'control').write_bytes(b'current plan')
            snapshot_regular_tree(cold / 'original', self.work / 'reference-inputs' / prefix)
            source = dict(relativePath=prefix, kind='sdk-binary', receipt=receipt,
                          artifactId=self.artifact['id'], artifactSha256=self.artifact['digest'])
            thin = self.work / 'thin-sdk'
            value = stage_original_reference_handoff(roots, [source], thin)
            self.assertEqual(2, value['schemaVersion'])
            self.assertFalse((thin / prefix).exists())
            self.assertTrue(all(row['sourcePath'].startswith('shard/') for row in value['references']))
            for mutate in (
                    lambda v: v.update(schemaVersion=1),
                    lambda v: v['sources'][0].update(kind='phase'),
                    lambda v: v['sources'][0].update(relativePath=prefix + '-other'),
                    lambda v: v['references'][0].update(sourcePath='native-original/unqualified')):
                changed = deepcopy(value)
                mutate(changed)
                with self.assertRaises(ValueError):
                    validate_original_references(changed)
            from runtime_reference_transport import selected_reference_paths
            selected = selected_reference_paths(value, omit_sdk_ios_binary=True)
            omitted = [row for row in value['inventory'] if row['relativePath'] not in selected]
            self.assertEqual(1, len(omitted))
            self.assertTrue(omitted[0]['relativePath'].endswith('.zip'))
            partial = self.work / 'scoped-sdk'
            snapshot_regular_tree(thin, partial)
            ranges = RangeOpener({self.artifact['id']: self.raw})
            def capture(source, records, target):
                return recovery.products._capture_runtime_original_reference_members(self.plan,
                    {**self.producer, 'runId': 72}, source, records, target,
                    trusted_workflow_sha=self.pin, token='synthetic-token')
            with patch('runtime_reference_archive.urllib.request.build_opener', return_value=ranges), \
                    patch.object(recovery.products, 'download_artifact_to_file',
                                 side_effect=AssertionError('whole SDK original downloaded')):
                resolve_original_reference_handoff(thin, value, capture)
                def scoped_capture(source, records, target):
                    self.assertFalse(any(row['sourcePath'].endswith('.zip') for row in records))
                    return capture(source, records, target)
                resolve_original_reference_handoff(partial, value, scoped_capture, selected_paths=selected)
            self.assertEqual([row for row in value['inventory'] if row['relativePath'] in selected],
                             regular_file_inventory(partial, allow_empty=True))
            with self.assertRaises((ValueError, FileNotFoundError)):
                product_restore.verify_phase_shard(partial / prefix / 'shard', recovery.INSTANCE)
            self.assertEqual(value['inventory'], regular_file_inventory(thin, allow_empty=True))
            self.assertEqual(receipt, value['sources'][0]['receipt'])

    def test_explicit_sdk_qualification_preserves_originals_and_skips_whole_archive_only_after_native_gate(self):
        import json
        import subprocess
        import hydrated_evidence
        import reuse_qualification as qualification
        from products.verified_evidence import runtime_original_cache
        from products.inventory import sha256_bytes
        receipt = load_canonical_json_bytes(self.receipt_bytes)
        cold = self.work / 'qualified-cold'
        key = self.work / 'private-authority'
        cache = self.work / 'private-records'
        raw_cache = self.work / 'hydrated-bodies'
        with self.gates(), patch('products.verified_evidence._authority_root', return_value=key), \
                patch('products.verified_evidence.native_cache_root', return_value=cache), \
                patch.dict(os.environ, {'CODEX_AGENT_HYDRATED_EVIDENCE': str(raw_cache)}):
            arguments = dict(binary_receipt_path=self.receipt_path, artifact_id=self.artifact['id'],
                artifact_sha256=self.artifact['digest'], trusted_workflow_sha=self.pin,
                repository_root=self.root, environ={}, token='synthetic-token', compact_recovery=True)
            captured = recovery.products.capture_sdk_ios_binary_upload(self.plan_path, cold,
                **arguments, qualify_original=True)
            self.assertEqual(1, recovery.products.download_artifact_to_file.call_count)
            source = dict(kind='sdk-binary', receipt=receipt, artifactId=self.artifact['id'],
                          artifactSha256=self.artifact['digest'])
            subject = self.work / 'sdk-qualification.json'
            claim = qualification.export_originals([source], subject, plan=self.plan,
                producer={**self.producer, 'runId': 72}, source_commit='a' * 40,
                trusted_workflow_sha=self.pin, token='synthetic-token')
            self.assertEqual(2, claim['schemaVersion'])
            self.assertEqual(receipt, claim['originals'][0]['receipt'])
            with self.assertRaises(ValueError):
                qualification.validate({**claim, 'schemaVersion': 1})
            for row in claim['originals'][0]['originalFiles']:
                self.assertTrue(row['relativePath'].startswith('shard/'))
                hydrated_evidence.retain(row, cold / 'original' / row['relativePath'])
            bundle = self.work / 'native-bundle'
            bundle.write_bytes(b'synthetic native authority boundary; not hosted acceptance')
            options = dict(CODEX_AGENT_REUSE_QUALIFICATION=str(subject),
                CODEX_AGENT_REUSE_QUALIFICATION_BUNDLE=str(bundle),
                CODEX_AGENT_REUSE_QUALIFICATION_ISSUER='a' * 40,
                CODEX_AGENT_REUSE_QUALIFICATION_SOURCE='b' * 40)
            native = subprocess.CompletedProcess([], 0, b'[{"verificationResult":{"fixture":true}}]', b'')
            with patch.dict(os.environ, options), verification_session(), \
                    patch.object(qualification.subprocess, 'run', return_value=native) as authority, \
                    patch.object(recovery.products, 'download_artifact_to_file', side_effect=AssertionError('whole archive')):
                warm = self.work / 'qualified-warm'
                observed = recovery.products.capture_sdk_ios_binary_upload(self.plan_path, warm, **arguments)
                self.assertEqual(captured, observed)
                self.assertEqual(regular_file_inventory(cold), regular_file_inventory(warm))
                authority.assert_called_once()
                with patch.dict(self.jobs[0], {'conclusion': 'failure'}), self.assertRaises(ValueError):
                    recovery.products.capture_sdk_ios_binary_upload(self.plan_path, self.work / 'failed-job', **arguments)
            member = claim['originals'][0]['originalFiles'][0]
            hydrated_evidence.blob(member).write_bytes(b'corrupt qualified body')
            with patch.dict(os.environ, options), verification_session(), \
                    patch.object(qualification.subprocess, 'run', return_value=native), self.assertRaises(ValueError):
                recovery.products.capture_sdk_ios_binary_upload(self.plan_path, self.work / 'corrupt', **arguments)

    def test_initial_capture_seals_only_its_completed_operation(self):
        with self.gates():
            download = recovery.products.download_artifact_to_file
            with verification_session(), patch.object(product_restore, "_uncached_file_inventory",
                    wraps=product_restore._uncached_file_inventory) as inventory:
                original = self.capture()
                self.assertEqual(1, download.call_count)
                initial_scans = inventory.call_count
                for _ in range(2):
                    self.assertEqual(original, self.replay())
                self.assertEqual(1, download.call_count)
                self.assertEqual(initial_scans, inventory.call_count)
                with patch.dict(self.artifact, {"expired": True}), self.assertRaises(ValueError):
                    self.replay()
                self.assertEqual(1, download.call_count)
            with verification_session():
                self.assertEqual(original, self.replay())
            self.assertEqual(2, download.call_count)

    def test_family_history_discovery_shares_run_lists_without_admission(self):
        attempts = [{**self.run, "id": run, "conclusion": "failure"} for run in range(68, 72)]
        arguments = {"trusted_workflow_sha": self.pin, "token": "synthetic-token", "environ": {},
                     "attempts": attempts, "artifacts_by_run": {}, "jobs_by_attempt": {}}
        producer = {**self.producer, "runId": 72}
        key = load_canonical_json_bytes(self.receipt_bytes)["buildKey"]
        with patch.object(recovery.products, "paginated_items", return_value=[]) as lists, \
                patch.object(recovery.products, "_runtime_prior_workflow_sha", return_value=self.pin):
            self.assertEqual([], recovery.capture_prior_ios_binary(self.plan_path, self.plan, producer,
                key, self.work / "absent-ios", self.work, repository_root=self.root, **arguments))
            self.assertEqual([], recovery.capture_prior_javascript_package(self.plan, producer,
                key, self.work / "absent-js", self.work, **arguments))
        self.assertEqual(4, lists.call_count)
        self.assertEqual(4, len({call.args[0] for call in lists.call_args_list}))

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

    def test_requalified_binary_uses_original_reference_and_private_physical_custody(self):
        from ci.tests.test_completed_frozen_reuse import CompletedFrozenReuseTest
        native = CompletedFrozenReuseTest()
        native.setUp()
        proof = self.work / "native-proof"
        proof.mkdir()
        cap, _ = native.fetched(proof)
        cap._eligible = frozenset()
        # Historical SDK controls remain available for unchanged Contract input.
        cap._sdk = canonical_json_bytes({"spec": {"completedPhase": {"product": "sdk",
            "component": "sdk-ios", "phase": "binary", "target": "ios"}}})
        inputs, state = self.work / "product-resume-inputs", self.work / "product-resume-state"
        inputs.mkdir()
        (inputs / "control").write_bytes(b"current plan")
        self.output = state / "prior-failed-sdk"
        with self.gates():
            records = self.capture()
            manifest = recovery.products._publish_runtime_original_reference_handoff(
                inputs, state, self.work / "thin-requalified", completed_frozen=cap)
            self.assertEqual(["sdk-binary"], [row["kind"] for row in manifest["sources"]])
            self.assertFalse(any(path.suffix == ".zip" for path in (self.work / "thin-requalified").rglob("*")))
            transport = load_canonical_json_bytes((self.output / "sdk-ios/binary/ios/capture-transport.json").read_bytes())
            with verification_session() as session, patch("hydrated_evidence.root", return_value=None), \
                    patch.object(recovery.products, "download_artifact_to_file",
                                 side_effect=AssertionError("duplicate whole SDK upload")):
                changed = deepcopy(transport)
                changed["artifact"]["id"] += 1
                with self.assertRaisesRegex(ValueError, "original authenticated provenance"):
                    recovery.products._register_qualified_original_projections(self.work, manifest, [changed],
                        trusted_workflow_sha=self.pin, completed_frozen=cap)
                self.assertFalse(session.get("qualifiedOriginalProjections"))
                recovery.products._register_qualified_original_projections(self.work, manifest, [transport],
                    trusted_workflow_sha=self.pin, completed_frozen=cap)
                self.assertEqual(1, len(session["qualifiedOriginalProjections"]))
                replay = recovery.replay_prior_ios_binary(self.output, self.work, plan=self.plan,
                    plan_path=self.plan_path, repository_root=self.root,
                    consumer_producer={**self.producer, "runId": 72}, trusted_workflow_sha=self.pin,
                    token="synthetic-token", environ={}, completed_frozen=cap)
                self.assertEqual(records, replay)
                receipt = self.output / "sdk-ios/binary/ios/original/shard/phase-receipt.json"
                receipt.write_bytes(b"mutated")
                with self.assertRaisesRegex(ValueError, "custody changed"):
                    recovery.products.capture_sdk_ios_binary_upload(self.plan_path, self.work / "changed-custody",
                        binary_receipt_path=self.receipt_path, artifact_id=self.artifact["id"],
                        artifact_sha256=self.artifact["digest"], trusted_workflow_sha=self.pin,
                        repository_root=self.root, environ={}, token="synthetic-token", compact_recovery=True)

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
    javascript_phase = "package"
    recovery_component, recovery_target = "javascript", "node"

    def setUp(self):
        fixture.SdkIosBinaryUploadTest.setUp(self)
        stage = self.work / "javascript-stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/package.tgz").write_bytes(b"synthetic packaged JavaScript bytes\n")
        (stage / "outputs/package-inventory.json").write_bytes(b'{"synthetic":true}\n')
        (stage / "outputs/package-evidence.txt").write_bytes(b"synthetic evidence, not host acceptance\n")
        manifest = write_output_manifest(stage, "sdk", self.recovery_component, self.javascript_phase, self.recovery_target, "0.3.0",
                                         {"package": "outputs"})
        receipt = write_receipt(self.work / "js-receipt.json", product="sdk", component=self.recovery_component,
            phase=self.javascript_phase, target=self.recovery_target, outputs=manifest["outputs"], upstream=[], version="0.3.0",
            version_identity="0.3.0", context={"producer": self.producer})
        shard = self.work / "js-shard"
        verified = finalize_phase_object(stage_root=stage,
            phase_plan={name: receipt[name] for name in PHASE_PLAN_KEYS}, producer=self.producer,
            product_version="0.3.0", trust_domain="development", destination=shard)
        self.key = receipt["buildKey"]
        self.receipt_bytes = verified["receiptBytes"]
        self.jobs[0]["name"] = f"product-validation / sdk-{self.recovery_component}-{self.javascript_phase}-{self.recovery_target}"
        self.artifact["name"] = (recovery.products._worker_artifact_prefix("sdk", recovery._javascript_instance(self.javascript_phase, self.recovery_component)) + f"{self.key.removeprefix('sha256:')}-"
                                 f"{self.producer['tree']}-attempt-2")
        self.files = {"shard/" + row["relativePath"]: (shard / row["relativePath"]).read_bytes()
                      for row in regular_file_inventory(shard)}
        self.files["execution/diagnostic.log"] = b""
        self.archive()

    def capture(self, **options):
        return recovery.capture_prior_javascript_package(self.plan, {**self.producer, "runId": 72},
            self.key, self.output, self.work, trusted_workflow_sha=self.pin,
            token="synthetic-token", environ={}, attempts=(self.run,), phase=self.javascript_phase,
            component=self.recovery_component, **options)

    def replay(self, **options):
        return recovery.replay_prior_javascript_package(self.output, self.work, plan=self.plan,
            consumer_producer={**self.producer, "runId": 72}, trusted_workflow_sha=self.pin,
            token="synthetic-token", environ={}, phase=self.javascript_phase, component=self.recovery_component, **options)

    def test_invalidated_historical_completion_replays_the_full_original(self):
        import reuse_qualification as native
        receipt = load_canonical_json_bytes(self.receipt_bytes)
        with self.gates(), verification_session(), \
                patch.object(recovery.products, "download_artifact", wraps=recovery.products.download_artifact) as download:
            records = self.capture()
            inventory = regular_file_inventory(self.output, allow_empty=True)
            cap = native.CompletedFrozenReuse(
                {"request": {}, "expectedResult": {"phases": []}}, [], native._COMPLETED_FROZEN,
                revision=receipt["producer"]["commit"],
                sdk={"extension": {"spec": {"completedPhases": records}, "proof": {}}})
            with patch.object(native.CompletedFrozenReuse, "observe_extended_sdk",
                              side_effect=AssertionError("invalidated native completion")), \
                    patch.object(recovery, "_capture_javascript_package",
                                 wraps=recovery._capture_javascript_package) as authenticate:
                self.assertEqual(records, self.replay(completed_frozen=cap))
                authenticate.assert_called_once()
                self.assertEqual(inventory, regular_file_inventory(self.output, allow_empty=True))
                self.assertEqual(1, download.call_count)
                # An invalidated native phase still requires the ordinary whole-upload gate.
                self.jobs[0]["conclusion"] = "failure"
                with self.assertRaises(ValueError):
                    self.replay(completed_frozen=cap)

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
        capture = self.output / f"{self.recovery_component}/{self.javascript_phase}/{self.recovery_target}"
        self.assertEqual(self.receipt_bytes, (capture / "original/shard/phase-receipt.json").read_bytes())
        self.assertEqual(self.raw, (capture / "transport.zip").read_bytes())
        for name, contents in self.files.items():
            self.assertEqual(contents, (capture / "original" / name).read_bytes())

    def test_reviewed_original_publisher_remains_selectable_after_rotation(self):
        for original in ("53d6ad1e4d7cfba9267894af9b302e07f7cb6656",
                         "288f994ff7d4fd4aaa09317db5a4c30cf8205a7f",
                         "d31b16736102f634665c351e6d0ed139250e8e48",
                         "493d0554ec86651303a221a97d904933903b775e",
                         "e8d67392cb9e7103eb36d2c43a5ce324cc86cd20"):
            with self.subTest(original=original):
                run = {**self.run, "referenced_workflows": [{
                    "path": f"codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@{original}",
                    "sha": original, "ref": "refs/heads/reuse-authority"}]}
                self.assertEqual(original, recovery.products._runtime_prior_workflow_sha(run, "e" * 40))
                run["referenced_workflows"][0]["sha"] = "f" * 40
                self.assertIsNone(recovery.products._runtime_prior_workflow_sha(run, "e" * 40))

    def test_cold_source_is_provisioned_only_after_original_authentication(self):
        with self.gates(), verification_session(), \
                patch("sdk_handoff._ensure_observed_sdk_commit") as source:
            self.jobs[0]["conclusion"] = "failure"
            self.assertEqual([], self.capture(repository_root=self.work))
            source.assert_not_called()
            self.jobs[0]["conclusion"] = "success"
            source.side_effect = ValueError("authenticated Git unavailable")
            with self.assertRaisesRegex(ValueError, "authenticated Git unavailable"):
                self.capture(repository_root=self.work)
            self.assertFalse(self.output.exists())
            source.reset_mock(side_effect=True)
            records = self.capture(repository_root=self.work)
            source.assert_called_once_with(self.work, self.producer, "synthetic-token")
            source.reset_mock()
            self.assertEqual(records, self.replay(repository_root=self.work))
            source.assert_called_once_with(self.work, self.producer, "synthetic-token")
            source.reset_mock()
            self.jobs[0]["conclusion"] = "failure"
            with self.assertRaises(ValueError):
                self.replay(repository_root=self.work)
            source.assert_not_called()

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
            original = self.output / f"{self.recovery_component}/{self.javascript_phase}/{self.recovery_target}/original/execution/diagnostic.log"
            original.write_bytes(b"tampered")
            with self.assertRaisesRegex(ValueError, "authenticated original upload"):
                self.replay()
            original.write_bytes(b"")
            transport = self.output / f"{self.recovery_component}/{self.javascript_phase}/{self.recovery_target}/capture-transport.json"
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
                    token="synthetic-token", environ={}, attempts=(self.run, other), phase=self.javascript_phase, component=self.recovery_component)
        self.assertFalse(self.output.exists())


class NativePackageRecoveryTest(unittest.TestCase):
    def test_other_compact_native_phases_still_require_qualified_authority(self):
        case = JavascriptPackageRecoveryTest()
        case.recovery_component, case.recovery_target = "csharp", "desktop"
        case.javascript_phase = "metadata"
        self.addCleanup(case.doCleanups)
        case.setUp()
        with case.gates():
            case.capture()
            with patch.object(recovery.products, "api_json", side_effect=AssertionError("unqualified replay")), \
                    self.assertRaisesRegex(ValueError, "exact native authority"):
                case.replay()

    def test_five_original_packages_replay_across_runs_and_attempts_without_rewriting_receipts(self):
        from sdk_phase import SDK_FAMILY_INSTANCES
        for instance in sorted(SDK_FAMILY_INSTANCES["native-package"]):
            with self.subTest(component=instance.component):
                case = JavascriptPackageRecoveryTest()
                case.recovery_component, case.recovery_target = instance.component, instance.target
                self.addCleanup(case.doCleanups)
                case.setUp()
                with case.gates(), verification_session(), \
                        patch.object(recovery.products, "download_artifact",
                                     wraps=recovery.products.download_artifact) as download, \
                        patch.object(recovery.products, "_observe_ci_producer_jobs",
                                     wraps=recovery.products._observe_ci_producer_jobs) as observe:
                    records = case.capture()
                    inventory = regular_file_inventory(case.output, allow_empty=True)
                    self.assertEqual(records, case.replay())
                    self.assertEqual(records, recovery.replay_prior_javascript_package(
                        case.output, case.work, plan=case.plan,
                        consumer_producer={**case.producer, "runAttempt": case.producer["runAttempt"] + 1},
                        trusted_workflow_sha=case.pin, token="synthetic-token", environ={},
                        component=instance.component, target=instance.target))
                    self.assertEqual(inventory, regular_file_inventory(case.output, allow_empty=True))
                    self.assertEqual(1, download.call_count)
                    self.assertEqual(3, observe.call_count)
                capture = case.output / f"{instance.component}/package/{instance.target}"
                self.assertEqual(case.receipt_bytes,
                                 (capture / "original/shard/phase-receipt.json").read_bytes())
                self.assertEqual(case.raw, (capture / "transport.zip").read_bytes())


class CsharpBinaryRecoveryTest(JavascriptPackageRecoveryTest):
    """Preserve the exact successful C# binary after a failed collection job."""
    javascript_phase = "binary"
    recovery_component, recovery_target = "csharp", "desktop"


class JavascriptValidationRecoveryTest(JavascriptPackageRecoveryTest):
    """Same independent original gates, including failed-parent and conflict cases."""
    javascript_phase = "validation"


class JavascriptMetadataRecoveryTest(JavascriptPackageRecoveryTest):
    """Recover the original metadata worker with GitHub's truncated display name."""
    javascript_phase = "metadata"

    @contextmanager
    def gates(self):
        with super().gates():
            self.jobs[0]["name"] = self.jobs[0]["name"][:118] + "..."
            yield


class IosSuccessfulPackageRecoveryTest(unittest.TestCase):
    """Tiny successful-original transports; no Apple semantic acceptance claim."""
    phase, target = "package", "ios"
    api = fixture.SdkIosPackageUploadTest.api
    archive = fixture.SdkIosPackageUploadTest.archive
    setUp = fixture.SdkIosPackageUploadTest.setUp
    gates = IosBinaryRecoveryTest.gates

    def capture(self):
        receipt = load_canonical_json_bytes(self.receipt_bytes)
        return recovery.capture_prior_ios_binary(self.plan_path, self.plan,
            {**self.producer, "runId": 72}, receipt['buildKey'], self.output, self.work,
            repository_root=self.root, environ={}, trusted_workflow_sha=self.pin,
            token='synthetic-token', attempts=(self.run,), phase='package')

    def test_successful_original_package_reuses_exact_receipt_and_compact_shard(self):
        with self.gates():
            result = self.capture()
            record = result[0]
            self.assertEqual(('sdk','sdk-ios','package','ios'),
                tuple(record[key] for key in ('product','component','phase','target')))
            saved = self.output / 'sdk-ios/package/ios'
            self.assertEqual(self.receipt_bytes, (saved/'original/shard/phase-receipt.json').read_bytes())
            self.assertEqual({'original','capture-transport.json'}, {p.name for p in saved.iterdir()})
            replay = recovery.replay_prior_ios_binary(self.output, self.work,
                plan=self.plan, plan_path=self.plan_path, repository_root=self.root,
                consumer_producer={**self.producer, 'runId':72}, trusted_workflow_sha=self.pin,
                token='synthetic-token', environ={}, phase='package')
            self.assertEqual(result, replay)

    def test_failed_package_job_is_not_admitted(self):
        with self.gates():
            self.jobs[0]['conclusion']='failure'
            self.assertEqual([], self.capture())
        self.assertFalse(self.output.exists())

    def test_unreviewed_original_is_not_selected(self):
        with self.gates(), patch.object(recovery.products, '_runtime_prior_workflow_sha', return_value=None):
            self.assertEqual([], self.capture())

    def test_package_shard_is_referenced_without_forwarding_the_original_envelope(self):
        from runtime_reference_transport import stage_original_reference_handoff, validate_original_references
        from products.inventory import snapshot_regular_tree
        receipt = load_canonical_json_bytes(self.receipt_bytes)
        prefix = 'product-resume-state/prior-failed-sdk-ios-package/sdk-ios/package/ios/original'
        roots = {'product-resume-inputs': self.work/'reference-inputs',
                 'product-resume-state': self.work/'reference-state'}
        roots['product-resume-inputs'].mkdir()
        (roots['product-resume-inputs']/'control').write_bytes(b'current plan')
        snapshot_regular_tree(self.root/'original-shard', roots['product-resume-state'] /
                              'prior-failed-sdk-ios-package/sdk-ios/package/ios/original/shard')
        source = dict(relativePath=prefix, kind='sdk-package', receipt=receipt,
                      artifactId=self.artifact['id'], artifactSha256=self.artifact['digest'])
        target=self.work/'reference-export'
        manifest=stage_original_reference_handoff(roots,[source],target)
        self.assertEqual(3,manifest['schemaVersion'])
        self.assertFalse((target/prefix).exists())
        self.assertTrue(all(row['sourcePath'].startswith('shard/') for row in manifest['references']))
        changed={**manifest,'schemaVersion':2}
        with self.assertRaises(ValueError):validate_original_references(changed)


if __name__ == "__main__":
    unittest.main()
