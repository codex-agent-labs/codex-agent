"""SDK collection with an explicit authenticated-state seam and real shards.

Official API responses/downloads are synthetic; existing observer, ZIP and shard
verifiers execute normally. This does not establish SDK election or host proof.
"""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_adapter_collection as transport_fixture
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_resume_capture import archive
from products.inventory import load_canonical_json, regular_file_inventory, sha256_bytes
from products.receipt import write_output_manifest
from products.restore import PHASE_PLAN_KEYS, finalize_phase_object


adapter = transport_fixture.adapter
PhaseInstanceId = adapter.PhaseInstanceId
PIN = transport_fixture.PIN


class SdkWorkerCollectionTest(unittest.TestCase):
    official_api = transport_fixture.RuntimeAdapterCollectionTest.official_api
    child_path = ".github/workflows/sdk-core-binary-validation.yml"
    child_job = "product-validation / sdk-core-binary-wave / sdk-core-binary-common"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-worker-collection-")
        self.addCleanup(temporary.cleanup)
        self.repository = Path(temporary.name).resolve()
        self.discovery = self.repository / "build/discovery"
        self.discovery.mkdir(parents=True)
        self.plan_path = self.repository / "plan.json"
        self.plan_path.write_bytes(b'{"synthetic":"authenticated state seam"}\n')
        self.plan = {"event": "pull_request"}
        self.environment = {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"}
        self.producer = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml", "commit": "a" * 40, "tree": "b" * 40,
            "event": "pull_request", "runId": 7, "runAttempt": 2, "pullRequest": 31}
        self.counter = 0

    def names(self, instance, key):
        identity = f"{instance.component}-{instance.phase}-{instance.target}"
        if instance == PhaseInstanceId("sdk", "csharp", "binary", "desktop"):
            identity = "sdk-csharp-binary-desktop"
        component = instance.component if instance.component in {"sdk-core", "sdk-android"} else f"sdk-{instance.component}"
        return (f"product-validation / {component}-{instance.phase}-{instance.target}",
            f"codex-agent-sdk-worker-{identity}-{key.removeprefix('sha256:')}-"
            f"{self.producer['tree']}-attempt-{self.producer['runAttempt']}")

    def shard(self, phase, *, wrong=None, component="javascript", target="node"):
        self.counter += 1
        base = self.repository / f"build/original-{self.counter}"
        stage = base / "stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/synthetic").write_bytes(b"original synthetic SDK output\x00\xff")
        version = "0.2.7" if wrong == "version" else "0.3.0"
        manifest = write_output_manifest(stage, "sdk", component, phase, target, version,
                                         {"evidence": "outputs"})
        receipt = write_receipt(base / "fixture-receipt.json", product="sdk", component=component,
            phase=phase, target=target, outputs=manifest["outputs"], upstream=[], version=version,
            version_identity=version, context={"producer": self.producer})
        ready = {name: receipt[name] for name in PHASE_PLAN_KEYS}
        emitted_plan = ready
        if wrong == "key":
            other = write_receipt(base / "different-receipt.json", product="sdk", component=component,
                phase=phase, target=target, outputs=manifest["outputs"], upstream=[], version="0.3.0",
                version_identity="0.3.0", context={"producer": self.producer},
                toolchain=sha256_bytes(b"different synthetic elected key"))
            emitted_plan = {name: other[name] for name in PHASE_PLAN_KEYS}
        producer = {**self.producer, "runAttempt": 3} if wrong == "producer" else self.producer
        original = base / "shard"
        descriptor = finalize_phase_object(stage_root=stage, phase_plan=emitted_plan,
            producer=producer, product_version=version, trust_domain="development", destination=original)
        if wrong == "version":
            # Isolate the collector's SDK-version check: the emitted old shard
            # and its key are internally valid, unlike the selected SDK 0.3.0.
            self.assertEqual("0.2.7", descriptor["receipt"]["productVersion"])
            self.assertEqual("0.2.7", descriptor["receipt"]["inputs"]["versionIdentity"])
            self.assertEqual(ready["buildKey"], descriptor["buildKey"])
        files = {"shard/" + row["relativePath"]: (original / row["relativePath"]).read_bytes()
                 for row in regular_file_inventory(original)}
        files.update({"gradle.log": b"", "execution.json": b'{"synthetic":"not execution proof"}\n',
                      "inputs/original.bin": b"exact original input\x00\xff"})
        return PhaseInstanceId("sdk", component, phase, target), ready, original, descriptor, files

    def state(self, ready):
        return SimpleNamespace(producer=self.producer, plan=self.plan, prior_ready_plans=ready,
            expected_fixed={"versions": {"sdk": "0.3.0", "runtime-release": "0.2.7"}})

    def collect(self, ready, uploads, destination, *, family=None):
        with patch.object(adapter, "_verified_product_state", return_value=self.state(ready)), \
                self.official_api(ready, uploads):
            return adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery, destination,
                trusted_workflow_sha=PIN, repository_root=self.repository, environ=self.environment,
                token="synthetic-token", sdk_javascript_only=family is None, sdk_family=family)

    def test_failed_original_is_retained_by_reference_without_body_and_keeps_successful_sibling(self):
        failed, failed_plan, _, _, failed_files = self.shard('package')
        good, good_plan, _, expected, good_files = self.shard('validation')
        failed_raw = archive(failed_files)
        failed_name = self.names(failed, failed_plan['buildKey'])[0]
        for case in ('failed', 'digest', 'expired', 'window', 'url', 'size', 'wrong-upload-run',
                     'wrong-job-run', 'wrong-job-head', 'ambiguous-job', 'ambiguous-artifact', 'running'):
            ready, uploads = {failed: failed_plan}, {failed: failed_raw}
            if case == 'failed':
                ready[good], uploads[good] = good_plan, archive(good_files)
            destination = self.repository / ('collected-failure-' + case)
            with self.subTest(case=case), \
                    patch.object(adapter, '_verified_product_state', return_value=self.state(ready)), \
                    self.official_api(ready, uploads) as (query, listing, downloaded):
                original_query, original_listing = query.side_effect, listing.side_effect
                def list_originals(url, field, token):
                    rows = [dict(row) for row in original_listing(url, field, token)]
                    if field == 'jobs':
                        for row in rows:
                            if row['name'] != failed_name:
                                continue
                            row['conclusion'] = 'failure'
                            if case == 'running': row['status'] = 'in_progress'
                            if case == 'wrong-job-run': row['run_id'] += 1
                            if case == 'wrong-job-head': row['head_sha'] = 'f' * 40
                        if case == 'ambiguous-job':
                            rows.extend(dict(row) for row in list(rows) if row['name'] == failed_name)
                    elif case == 'ambiguous-artifact': rows.append(dict(rows[0]))
                    return rows
                def observe_original(url, token):
                    value = dict(original_query(url, token))
                    if '/actions/artifacts/' in url:
                        value.update({'digest': {'digest': 'sha256:' + 'f' * 64},
                            'expired': {'expired': True}, 'window': {'created_at': '2026-09-08T09:00:00Z'},
                            'url': {'archive_download_url': 'https://untrusted.invalid/zip'},
                            'size': {'size_in_bytes': 0}}.get(case, {}))
                        if case == 'wrong-upload-run': value['workflow_run'] = {**value['workflow_run'], 'id': 999}
                    return value
                listing.side_effect, query.side_effect = list_originals, observe_original
                def collect():
                    return adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                        destination, trusted_workflow_sha=PIN, repository_root=self.repository,
                        environ=self.environment, token='synthetic-token', sdk_javascript_only=True)
                if case == 'running':
                    with self.assertRaisesRegex(ValueError, 'still running'): collect()
                    downloaded.assert_not_called()
                    self.assertFalse(destination.exists())
                    continue
                result = collect()
                row = next(row for row in result['rows'] if row['phase'] == 'package')
                self.assertEqual('failure', row['result'])
                self.assertIsNone(row['shardDirectory'])
                self.assertIsNone(row['originalDirectory'])
                if case != 'failed':
                    downloaded.assert_not_called()
                    self.assertIsNone(row['artifact'])
                    continue
                self.assertEqual(1, downloaded.call_count)
                self.assertEqual(sha256_bytes(failed_raw), row['artifact']['digest'])
                self.assertEqual(result, load_canonical_json(destination / 'collection.json'))
                self.assertTrue(any(job['name'] == failed_name and job['conclusion'] == 'failure'
                                    for job in result['observed'][0]['jobs']))
                sibling = next(row for row in result['rows'] if row['phase'] == 'validation')
                self.assertEqual('success', sibling['result'])
                actual = adapter.verify_phase_shard(destination / sibling['shardDirectory'], good)
                self.assertEqual(expected['receiptSha256'], actual['receiptSha256'])
                self.assertEqual(expected['objectSha256'], actual['objectSha256'])

    def test_full_key_ellipsis_without_comma_selects_only_exact_candidates(self):
        name = "product-validation / sdk-core-metadata-wave / sdk-core-metadata-common"
        key = "sha256:7b8511fe614ab935af4333da9210808083d5f134a89ac013085dff52c0aefc5a"
        job = {"id": 1, "name": f"{name} ({key}..."}
        self.assertEqual([job], adapter._matching_ci_jobs([job], name, expected_build_key=key))
        for changed in (key[:-1] + "0", "sha256:" + "f" * 64):
            self.assertEqual([], adapter._matching_ci_jobs([job], name, expected_build_key=changed))
        self.assertEqual([], adapter._matching_ci_jobs([job], name))
        duplicate = {**job, "id": 2}
        self.assertEqual([job, duplicate], adapter._matching_ci_jobs(
            [job, duplicate], name, expected_build_key=key))

    def test_actual_nested_android_leaf_truncation_locates_only_candidates(self):
        name = 'product-validation / sdk-android-binary-result / sdk-android-binary-android'
        key = 'sha256:9205c174e60f6bc6ef02676aa030aeaebe24b33c6171a888ea618201b6d6e06c'
        # Actual official job117231503731; only its display name is truncated.
        job = {'id': 117231503731, 'name': name + ' (sha256:9205c174e60f6bc6ef02676aa030aeaebe24b33c6171a888ea618201b6d6e0...'}
        self.assertEqual([job], adapter._matching_ci_jobs([job], name, expected_build_key=key))
        self.assertEqual([], adapter._matching_ci_jobs([job], name))
        self.assertEqual([], adapter._matching_ci_jobs([job], name, expected_build_key='sha256:' + '0' * 64))
        duplicate = {**job, 'id': 2}
        self.assertEqual([job, duplicate], adapter._matching_ci_jobs([job, duplicate], name, expected_build_key=key))
        # A display cannot authenticate unseen suffix bytes. Original full-key
        # artifact/receipt checks remain mandatory in the collection test below.

    def test_truncated_matrix_display_preserves_full_key_and_ambiguity_gates(self):
        for case in ("valid", "wrong-receipt-key", "wrong-display-key", "ambiguous"):
            with self.subTest(case=case):
                instance, ready, _, _, files = self.shard("metadata",
                    wrong="key" if case == "wrong-receipt-key" else None)
                with patch.object(adapter, "_verified_product_state", return_value=self.state({instance: ready})), \
                        self.official_api({instance: ready}, {instance: archive(files)}) as (_, listing, _):
                    original_listing = listing.side_effect
                    def truncated(url, field, token):
                        rows = original_listing(url, field, token)
                        if field != "jobs":
                            return rows
                        jobs = [dict(row) for row in rows]
                        key = "sha256:" + "f" * 64 if case == "wrong-display-key" else ready["buildKey"]
                        jobs[-1]["name"] = f"{jobs[-1]['name']} ({key}, ..."[:118] + "..."
                        if case == "ambiguous":
                            jobs.append({**jobs[-1], "id": jobs[-1]["id"] + 1})
                        return jobs
                    listing.side_effect = truncated
                    result = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                        self.repository / ("collected-" + case), trusted_workflow_sha=PIN,
                        repository_root=self.repository, environ=self.environment,
                        token="synthetic-token", sdk_family="javascript-metadata")
                row = result["rows"][0]
                self.assertEqual("success" if case == "valid" else "failure", row["result"], row["reason"])
                if case == "wrong-receipt-key":
                    self.assertIn("elected plan and producer", row["reason"])
                elif case != "valid":
                    self.assertIn("missing or ambiguous", row["reason"])

    def test_csharp_binary_collects_the_existing_producer_upload_spelling(self):
        instance, ready, _, _, files = self.shard('binary', component='csharp', target='desktop')
        result = self.collect({instance: ready}, {instance: archive(files)},
                              self.repository / 'collected-csharp', family='csharp-binary')
        self.assertEqual('success', result['rows'][0]['result'], result['rows'][0]['reason'])
        self.assertTrue(result['rows'][0]['artifactName'].startswith(
            'codex-agent-sdk-worker-sdk-csharp-binary-desktop-'))
        from sdk_campaign_original_locator import fresh_sdk_worker_route
        _, name = fresh_sdk_worker_route(instance, {'producer': self.producer, 'buildKey': ready['buildKey']})
        self.assertEqual(result['rows'][0]['artifactName'], name)

    def test_retry_reuses_original_sibling_only_with_private_completed_collection(self):
        from products.inventory import write_canonical_json
        instance, ready, _, _, files = self.shard("package")
        write_canonical_json(self.discovery / "producer.json", self.producer)
        current = {**self.producer, "runAttempt": 3}
        state = self.state({instance: ready})
        state.producer = current
        destination = self.repository / "build/retry-collected"
        with adapter.verification_session(), \
                patch.object(adapter, "_verified_product_state", return_value=state), \
                self.official_api({instance: ready}, {instance: archive(files)}) as (_, listing, _):
            original_listing = listing.side_effect
            listing.side_effect = lambda url, *args: ([] if "/attempts/3/" in url else original_listing(url, *args))
            result = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery, destination,
                trusted_workflow_sha=PIN, repository_root=self.repository,
                environ={**self.environment, "GITHUB_RUN_ATTEMPT": "3"}, token="synthetic-token",
                sdk_javascript_only=True)
            listing.side_effect = lambda url, *args: ([{"name": self.names(instance, ready["buildKey"])[0],
                "status": "in_progress"}] if "/attempts/3/" in url else original_listing(url, *args))
            with self.assertRaisesRegex(ValueError, "still running"):
                adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                    self.repository / "build/running-retry", trusted_workflow_sha=PIN,
                    repository_root=self.repository, environ={**self.environment, "GITHUB_RUN_ATTEMPT": "3"},
                    token="synthetic-token", sdk_javascript_only=True)
            row = result["rows"][0]
            self.assertEqual("success", row["result"], row["reason"])
            self.assertEqual(current, result["producer"])
            shard = destination / row["shardDirectory"]
            verified = adapter.verify_phase_shard(shard, instance)
            self.assertEqual(self.producer, verified["receipt"]["producer"])
            self.assertEqual(self.producer, adapter._require_collected_sdk_original(
                shard, verified, {"producer": current}, PIN))
            for changed, pin in (({**verified, "objectSha256": "sha256:" + "d" * 64}, PIN),
                                 (verified, "d" * 40)):
                with self.assertRaisesRegex(ValueError, "fresh authenticated"):
                    adapter._require_collected_sdk_original(shard, changed, {"producer": current}, pin)
        with self.assertRaisesRegex(ValueError, "fresh authenticated"):
            adapter._require_collected_sdk_original(shard, verified, {"producer": current}, PIN)

    def test_core_worker_uses_exact_workflow_job_without_extra_sdk_prefix(self):
        instance, ready, _, _, files = self.shard("binary", component="sdk-core", target="common")
        result = self.collect({instance: ready}, {instance: archive(files)},
                              self.repository / "build/collected-core", family="core-binary")
        self.assertEqual("success", result["rows"][0]["result"])
        self.assertEqual("product-validation / sdk-core-binary-common", result["rows"][0]["jobName"])

    def test_core_child_collection_binds_workflow_and_job(self):
        instance, ready, _, _, files = self.shard("binary", component="sdk-core", target="common")
        original_names = self.names
        with patch.object(self, "names", side_effect=lambda row, key: (self.child_job, original_names(row, key)[1])), \
                patch.object(adapter, "_verified_product_state", return_value=self.state({instance: ready})), \
                self.official_api({instance: ready}, {instance: archive(files)}) as (query, listed, _):
            original_query = query.side_effect

            def child_run(url, token):
                result = original_query(url, token)
                if url.endswith(f"/attempts/{self.producer['runAttempt']}"):
                    return {**result, "referenced_workflows": [*result["referenced_workflows"], {
                        "path": f"{self.producer['repository']}/{self.child_path}@{PIN}", "sha": PIN}]}
                return result

            query.side_effect = child_run
            result = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                self.repository / "build/collected-child", trusted_workflow_sha=PIN,
                repository_root=self.repository, environ=self.environment, token="synthetic-token",
                sdk_family="core-binary", sdk_worker_workflow_path=self.child_path,
                sdk_worker_job_name=self.child_job)
            self.assertEqual("success", result["rows"][0]["result"])
            self.assertEqual(self.child_job, result["rows"][0]["jobName"])

    def test_retained_core_original_needs_fresh_collection_session_and_exact_child(self):
        self.check_retained_core_original("binary")

    def test_retained_core_package_needs_fresh_collection_session_and_exact_child(self):
        self.check_retained_core_original("package")

    def test_retained_core_validation_needs_fresh_collection_session_and_exact_child(self):
        self.check_retained_core_original("validation", "android")

    def test_retained_core_metadata_needs_fresh_collection_session_and_exact_child(self):
        self.check_retained_core_original("metadata")

    def test_retained_android_binary_needs_fresh_collection_session_and_exact_child(self):
        self.check_retained_core_original("binary", "android", component="sdk-android")

    def test_retained_android_metadata_needs_fresh_collection_session_and_exact_child(self):
        instance = PhaseInstanceId("sdk", "sdk-android", "metadata", "android")
        self.assertEqual(adapter._CATALOG_ZIP_LIMITS, adapter._worker_upload_zip_limits(instance))
        self.check_retained_core_original("metadata", "android", component="sdk-android")

    def check_retained_core_original(self, phase, target="common", component="sdk-core"):
        self.child_path = (".github/workflows/sdk-core-validation.yml" if phase == "validation" else
                           f".github/workflows/sdk-core-{phase}-validation.yml")
        self.child_job = f"product-validation / sdk-core-{phase}-wave / sdk-core-{phase}-{target}"
        if component == "sdk-android":
            self.child_path = f".github/workflows/sdk-android-{phase}-validation.yml"
            self.child_job = f"product-validation / sdk-android-{phase}-result / sdk-android-{phase}-{target}"
        instance, ready, _, _, files = self.shard(phase, component=component, target=target)
        raw = archive(files)
        original = dict(self.producer)
        artifact_name = self.names(instance, ready["buildKey"])[1]
        self.producer = {**original, "runId": 8, "runAttempt": 1, "commit": "d" * 40, "tree": "e" * 40}
        self.environment.update(GITHUB_RUN_ID="8", GITHUB_RUN_ATTEMPT="1")
        origin = {"producer": original, "artifact_id": 901, "artifact_sha256": sha256_bytes(raw),
            "job_id": 901, "workflow_sha": "f" * 40, "workflow_path": self.child_path, "job_name": self.child_job}
        original_job = {"id": 901, "name": f"{self.child_job} ({ready['buildKey']}, ..."[:118] + "...",
            "run_id": original["runId"], "head_sha": original["commit"], "status": "completed", "conclusion": "success",
            "started_at": "2026-09-08T10:00:00Z", "completed_at": "2026-09-08T10:10:00Z"}
        if component == 'sdk-android':
            prefix, separator, _ = self.child_job.rpartition(' / ')
            original_job['name'] = f"{self.child_job} ({ready['buildKey']}, ..."[:len(prefix) + len(separator) + 97] + '...'
        observe = adapter._observe_ci_producer_jobs
        def observed(producers, **kwargs):
            if "worker" not in producers: return observe(producers, **kwargs)
            self.assertEqual(original, producers["worker"])
            self.assertEqual({"worker": {"path": self.child_path, "sha": origin["workflow_sha"]}},
                             kwargs["trusted_workflows_by_phase"])
            self.assertEqual({"worker": ready["buildKey"]}, kwargs["build_keys_by_phase"])
            return [{"run": {"head_sha": original["commit"]}, "jobs": [original_job]}]
        destination = self.repository / "build/retained-core"
        with adapter.verification_session(), \
                patch.object(adapter, "_verified_product_state", return_value=self.state({instance: ready})), \
                self.official_api({instance: ready}, {instance: raw}) as (query, _, downloaded), \
                patch("sdk_campaign_original_locator.retained_core_origin", return_value=origin), \
                patch.object(adapter, "_observe_ci_producer_jobs", side_effect=observed), \
                patch("sdk_handoff._ensure_observed_sdk_commit") as source:
            old_query = query.side_effect
            def original_metadata(url, token):
                value = old_query(url, token)
                if "/actions/artifacts/" in url:
                    return {**value, "name": artifact_name,
                            "workflow_run": {"id": original["runId"], "head_sha": original["commit"]}}
                if url.endswith("/attempts/1"):
                    return {**value, "referenced_workflows": [*value["referenced_workflows"],
                        {"path": f"{self.producer['repository']}/{self.child_path}@{PIN}", "sha": PIN}]}
                return value
            query.side_effect = original_metadata
            def collect(path, child=self.child_path):
                return adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                    path, trusted_workflow_sha=PIN, repository_root=self.repository, environ=self.environment,
                    token="synthetic-token", sdk_family=component.removeprefix("sdk-") + "-" + phase,
                    sdk_worker_workflow_path=child, sdk_worker_job_name=(self.child_job.removesuffix(target) + "{target}"
                        if phase == "validation" else self.child_job))
            result = collect(destination)
            row, = result["rows"]
            self.assertEqual("success", row["result"], row["reason"])
            source.assert_called_once_with(self.repository, original, "synthetic-token")
            downloaded.assert_called_once()
            shard = destination / row["shardDirectory"]
            verified = adapter.verify_phase_shard(shard, instance)
            self.assertEqual(original, verified["receipt"]["producer"])
            self.assertEqual(original, adapter._require_collected_sdk_original(
                shard, verified, {"producer": self.producer}, PIN))
            with self.assertRaisesRegex(ValueError, "fresh authenticated"):
                adapter._require_collected_sdk_original(shard, verified, {"producer": self.producer}, "d" * 40)
            original_job["id"] = 902
            failed = collect(self.repository / "build/wrong-original-job")
            self.assertIn("reviewed successful job", failed["rows"][0]["reason"])
            downloaded.assert_called_once()
        with patch("sdk_campaign_original_locator.retained_core_origin", return_value=origin), \
                self.assertRaisesRegex(ValueError, "fresh authenticated"):
            adapter._require_collected_sdk_original(shard, verified, {"producer": self.producer}, PIN)

            for mutation in ("missing", "duplicate", "sha"):
                def wrong_run(url, token):
                    result = child_run(url, token)
                    if url.endswith(f"/attempts/{self.producer['runAttempt']}"):
                        references = result["referenced_workflows"]
                        if mutation == "missing": references = references[:-1]
                        elif mutation == "duplicate": references = [*references, references[-1]]
                        else: references = [*references[:-1], {**references[-1], "sha": "f" * 40}]
                        return {**result, "referenced_workflows": references}
                    return result
                query.side_effect = wrong_run
                with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, "caller-pinned workflow"):
                    adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                        self.repository / f"build/rejected-child-{mutation}", trusted_workflow_sha=PIN,
                        repository_root=self.repository, environ=self.environment, token="synthetic-token",
                        sdk_family="core-binary", sdk_worker_workflow_path=self.child_path,
                        sdk_worker_job_name=self.child_job)
            query.side_effect = child_run
            original_listing = listed.side_effect
            def failed_worker(url, field, token):
                rows = original_listing(url, field, token)
                if field == "jobs":
                    return [{**row, "conclusion": "failure"} if row["name"] == self.child_job else row for row in rows]
                return rows
            listed.side_effect = failed_worker
            failed = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                self.repository / "build/failed-child", trusted_workflow_sha=PIN,
                repository_root=self.repository, environ=self.environment, token="synthetic-token",
                sdk_family="core-binary", sdk_worker_workflow_path=self.child_path,
                sdk_worker_job_name=self.child_job)["rows"][0]
            self.assertEqual("failure", failed["result"])
            self.assertIsNone(failed["originalDirectory"])
            self.assertIsNotNone(failed["artifact"])
            self.assertIsNone(failed["shardDirectory"])

    def test_child_path_and_job_are_inseparable_before_state_replay(self):
        for route in ({"sdk_worker_workflow_path": self.child_path},
                      {"sdk_worker_job_name": self.child_job},
                      {"sdk_worker_workflow_path": "../other.yml", "sdk_worker_job_name": self.child_job},
                      {"sdk_worker_workflow_path": self.child_path, "sdk_worker_job_name": self.child_job,
                       "sdk_family": "ios-validation"}):
            with self.subTest(route=route), patch.object(adapter, "_verified_product_state", side_effect=AssertionError):
                with self.assertRaises(ValueError):
                    adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                        self.repository / "build/invalid-child", trusted_workflow_sha=PIN,
                        repository_root=self.repository, environ=self.environment, token="synthetic-token",
                        **({"sdk_family": "core-binary"} | route))

    def test_child_matrix_job_keeps_key_ambiguity_live_and_retry_guards(self):
        from products.inventory import write_canonical_json
        for case in ("valid", "compact", "truncated", "retry", "wrong-key", "wrong-key-compact",
                     "ambiguous", "ambiguous-compact", "running"):
            with self.subTest(case=case):
                instance, ready, _, expected, files = self.shard("binary", component="sdk-core", target="common")
                state = self.state({instance: ready})
                write_canonical_json(self.discovery / "producer.json", self.producer)
                if case == "retry":
                    state.producer = {**self.producer, "runAttempt": 3}
                names = self.names
                with patch.object(self, "names", side_effect=lambda row, key: (self.child_job, names(row, key)[1])), \
                        patch.object(adapter, "_verified_product_state", return_value=state), \
                        self.official_api({instance: ready}, {instance: archive(files)}) as (query, listed, downloaded):
                    original_query, original_listing = query.side_effect, listed.side_effect
                    def child_run(url, token):
                        result = original_query(url, token)
                        if url.endswith(f"/attempts/{self.producer['runAttempt']}"):
                            return {**result, "referenced_workflows": [*result["referenced_workflows"], {
                                "path": f"{self.producer['repository']}/{self.child_path}@{PIN}", "sha": PIN}]}
                        return result
                    def matrix_jobs(url, field, token):
                        if "/attempts/3/jobs" in url:
                            return []
                        rows = original_listing(url, field, token)
                        if field != "jobs":
                            return rows
                        key = "sha256:" + "f" * 64 if case.startswith("wrong-key") else ready["buildKey"]
                        name = f"{self.child_job} ({key}, ..."
                        if case.endswith("compact"):
                            name = name.replace(", ...", ",...")
                        if case == "truncated":
                            name = name[:118] + "..."
                        jobs = [{**row, "name": name,
                                 "status": "in_progress" if case == "running" else "completed"}
                                if row["name"] == self.child_job else row for row in rows]
                        if case.startswith("ambiguous"):
                            jobs.extend(row for row in rows if row["name"] == self.child_job)
                        return jobs
                    query.side_effect, listed.side_effect = child_run, matrix_jobs
                    destination = self.repository / ("child-matrix-" + case)
                    def collect():
                        return adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                            destination, trusted_workflow_sha=PIN, repository_root=self.repository,
                            environ={**self.environment, "GITHUB_RUN_ATTEMPT": str(state.producer["runAttempt"])},
                            token="synthetic-token", sdk_family="core-binary",
                            sdk_worker_workflow_path=self.child_path, sdk_worker_job_name=self.child_job)
                    if case == "running":
                        with self.assertRaisesRegex(ValueError, "still running"):
                            collect()
                        downloaded.assert_not_called()
                        continue
                    row = collect()["rows"][0]
                    if case.startswith(("wrong-key", "ambiguous")):
                        self.assertEqual("failure", row["result"])
                        downloaded.assert_not_called()
                    else:
                        self.assertEqual("success", row["result"], row["reason"])
                        actual = adapter.verify_phase_shard(destination / row["shardDirectory"], instance)
                        self.assertEqual(expected["receiptSha256"], actual["receiptSha256"])
                        self.assertEqual(expected["objectSha256"], actual["objectSha256"])

    def test_core_validation_child_binds_each_target_job(self):
        child_path = ".github/workflows/sdk-core-validation.yml"
        job_template = "product-validation / sdk-core-validation-wave / sdk-core-validation-{target}"
        shards = [self.shard("validation", component="sdk-core", target=target)
                  for target in sorted(row.target for row in adapter.SDK_FAMILY_INSTANCES["core-validation"])]
        for _, _, _, _, files in shards:
            files["inputs/unselected-large.bin"] = b"unchanged input fixture" * 4096
        ready = {instance: plan for instance, plan, _, _, _ in shards}
        uploads = {instance: archive(files) for instance, _, _, _, files in shards}
        names = self.names

        def child_names(instance, key):
            return job_template.replace("{target}", instance.target), names(instance, key)[1]

        with patch.object(self, "names", side_effect=child_names), \
                patch.object(adapter, "_verified_product_state", return_value=self.state(ready)), \
                self.official_api(ready, uploads) as (query, _, downloaded):
            original_query = query.side_effect

            def child_run(url, token):
                result = original_query(url, token)
                if url.endswith(f"/attempts/{self.producer['runAttempt']}"):
                    return {**result, "referenced_workflows": [*result["referenced_workflows"], {
                        "path": f"{self.producer['repository']}/{child_path}@{PIN}", "sha": PIN}]}
                return result

            query.side_effect = child_run
            result = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                self.repository / "build/validation-child", trusted_workflow_sha=PIN,
                repository_root=self.repository, environ=self.environment, token="synthetic-token",
                sdk_family="core-validation", sdk_worker_workflow_path=child_path,
                sdk_worker_job_name=job_template)
        self.assertEqual(11, downloaded.call_count)
        self.assertEqual(11, len(result["rows"]))
        self.assertEqual({"success"}, {row["result"] for row in result["rows"]})
        self.assertEqual({job_template.replace("{target}", target) for target in (row.target for row in ready)},
                         {row["jobName"] for row in result["rows"]})

        expected = {instance: (original, descriptor, files) for instance, _, original, descriptor, files in shards}
        for row in result["rows"]:
            instance = adapter._identity(row)
            original, descriptor, files = expected[instance]
            retained = self.repository / "build/validation-child" / row["originalDirectory"]
            self.assertEqual(regular_file_inventory(original), regular_file_inventory(retained / "shard"))
            verified = adapter.verify_phase_shard(retained / "shard", instance)
            self.assertEqual(descriptor["receiptSha256"], verified["receiptSha256"])
            self.assertEqual(descriptor["objectSha256"], verified["objectSha256"])
            self.assertEqual(self.producer, verified["receipt"]["producer"])
            self.assertNotIn(instance, adapter._LARGE_SDK_UPLOADS)
            self.assertEqual(adapter._CATALOG_ZIP_LIMITS, adapter._worker_upload_zip_limits(instance))
            self.assertEqual({"shard"}, {path.name for path in retained.iterdir()})
            self.assertFalse((retained.parent / "transport.zip").exists())
            self.assertEqual({"schemaVersion": 1, "files": [
                {"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)}
                for name, raw in sorted(files.items())]}, load_canonical_json(retained.parent / "original-inventory.json"))

    def test_core_validation_projection_rejects_invalid_unselected_archive_members(self):
        import io, stat, warnings, zipfile
        instance, ready, _, _, files = self.shard("validation", component="sdk-core", target="jvm")
        raw = archive(files)
        original = files["inputs/original.bin"]
        self.assertEqual(1, raw.count(original))
        cases = {"crc": raw.replace(original, b"X" + original[1:])}
        for case in ("traversal", "symlink", "duplicate", "file-directory-overlap"):
            stream = io.BytesIO(raw)
            with warnings.catch_warnings(), zipfile.ZipFile(stream, "a") as zipped:
                warnings.simplefilter("ignore", UserWarning)
                if case == "traversal": zipped.writestr("inputs/../../escape", b"bad")
                elif case == "symlink":
                    info = zipfile.ZipInfo("inputs/link"); info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16; zipped.writestr(info, b"original.bin")
                elif case == "duplicate": zipped.writestr("inputs/original.bin", original)
                else: zipped.writestr("inputs", b"not a directory")
            cases[case] = stream.getvalue()
        for case, body in cases.items():
            with self.subTest(case=case), patch.object(adapter, "_extract_runtime_original_projection") as extract:
                result = self.collect({instance: ready}, {instance: body},
                    self.repository / ("build/invalid-core-validation-" + case), family="core-validation")
                row, = result["rows"]
                self.assertEqual("failure", row["result"])
                self.assertIsNone(row["shardDirectory"])
                extract.assert_not_called()

    def test_core_validation_projection_keeps_selected_receipt_and_object_gates(self):
        for fault in ("producer", "key", "version", "object"):
            with self.subTest(fault=fault):
                instance, ready, _, descriptor, files = self.shard("validation", component="sdk-core", target="jvm",
                    wrong=fault if fault != "object" else None)
                if fault == "object":
                    name = "shard/" + descriptor["objectPath"]
                    files[name] += b"changed object"
                result = self.collect({instance: ready}, {instance: archive(files)},
                    self.repository / ("build/wrong-core-validation-" + fault), family="core-validation")
                row, = result["rows"]
                self.assertEqual("failure", row["result"])
                self.assertIsNone(row["shardDirectory"])

    def test_core_validation_child_rejects_non_target_template_before_replay(self):
        for job in ("product-validation / sdk-core-validation-wave / sdk-core-validation-jvm",
                    "product-validation / sdk-core-validation-wave / sdk-core-validation-{target}-{target}"):
            with self.subTest(job=job), patch.object(adapter, "_verified_product_state", side_effect=AssertionError):
                with self.assertRaisesRegex(ValueError, "target job template"):
                    adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                        self.repository / "build/invalid-validation-child", trusted_workflow_sha=PIN,
                        repository_root=self.repository, environ=self.environment, token="synthetic-token",
                        sdk_family="core-validation", sdk_worker_workflow_path=".github/workflows/sdk-core-validation.yml",
                        sdk_worker_job_name=job)

    def test_core_metadata_child_binds_original_workflow_and_job(self):
        instance, ready, _, _, files = self.shard("metadata", component="sdk-core", target="common")
        child_path = ".github/workflows/sdk-core-metadata-validation.yml"
        child_job = "product-validation / sdk-core-metadata-wave / sdk-core-metadata-common"
        names = self.names
        with patch.object(self, "names", side_effect=lambda row, key: (child_job, names(row, key)[1])), \
                patch.object(adapter, "_verified_product_state", return_value=self.state({instance: ready})), \
                self.official_api({instance: ready}, {instance: archive(files)}) as (query, _, _):
            original_query = query.side_effect

            def child_run(url, token):
                result = original_query(url, token)
                if url.endswith(f"/attempts/{self.producer['runAttempt']}"):
                    return {**result, "referenced_workflows": [*result["referenced_workflows"], {
                        "path": f"{self.producer['repository']}/{child_path}@{PIN}", "sha": PIN}]}
                return result

            query.side_effect = child_run
            result = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                self.repository / "build/metadata-child", trusted_workflow_sha=PIN,
                repository_root=self.repository, environ=self.environment, token="synthetic-token",
                sdk_family="core-metadata", sdk_worker_workflow_path=child_path,
                sdk_worker_job_name=child_job)
        self.assertEqual("success", result["rows"][0]["result"])
        self.assertEqual(child_job, result["rows"][0]["jobName"])
        retained = self.repository / "build/metadata-child" / result["rows"][0]["originalDirectory"]
        self.assertFalse((retained.parent / "transport.zip").exists())
        self.assertEqual({"shard"}, {path.name for path in retained.iterdir()})
        self.assertEqual({"schemaVersion": 1, "files": [
            {"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)}
            for name, raw in sorted(files.items())]}, load_canonical_json(retained.parent / "original-inventory.json"))

    def test_core_metadata_projection_still_authenticates_unconsumed_original_bytes(self):
        instance, ready, _, _, files = self.shard("metadata", component="sdk-core", target="common")
        raw = archive(files)
        original = files["inputs/original.bin"]
        self.assertEqual(1, raw.count(original))
        corrupt = raw.replace(original, b"X" + original[1:])
        with patch.object(adapter, "_extract_runtime_original_projection") as extract:
            result = self.collect({instance: ready}, {instance: corrupt},
                self.repository / "build/corrupt-core-metadata", family="core-metadata")
        self.assertEqual("failure", result["rows"][0]["result"])
        self.assertIsNone(result["rows"][0]["shardDirectory"])
        extract.assert_not_called()

    def test_android_binary_child_binds_original_workflow_and_job(self):
        instance, ready, _, _, files = self.shard("binary", component="sdk-android", target="android")
        child_path = ".github/workflows/sdk-android-binary-validation.yml"
        child_job = "product-validation / sdk-android-binary-result / sdk-android-binary-android"
        names = self.names
        with patch.object(self, "names", side_effect=lambda row, key: (child_job, names(row, key)[1])), \
                patch.object(adapter, "_verified_product_state", return_value=self.state({instance: ready})), \
                self.official_api({instance: ready}, {instance: archive(files)}) as (query, _, _):
            original_query = query.side_effect

            def child_run(url, token):
                result = original_query(url, token)
                if url.endswith(f"/attempts/{self.producer['runAttempt']}"):
                    return {**result, "referenced_workflows": [*result["referenced_workflows"], {
                        "path": f"{self.producer['repository']}/{child_path}@{PIN}", "sha": PIN}]}
                return result

            query.side_effect = child_run
            result = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                self.repository / "build/android-binary-child", trusted_workflow_sha=PIN,
                repository_root=self.repository, environ=self.environment, token="synthetic-token",
                sdk_family="android-binary", sdk_worker_workflow_path=child_path,
                sdk_worker_job_name=child_job)
            query.side_effect = original_query
            with self.assertRaisesRegex(ValueError, "caller-pinned workflow"):
                adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                    self.repository / "build/android-binary-unpinned", trusted_workflow_sha=PIN,
                    repository_root=self.repository, environ=self.environment, token="synthetic-token",
                    sdk_family="android-binary", sdk_worker_workflow_path=child_path,
                    sdk_worker_job_name=child_job)
        self.assertEqual("success", result["rows"][0]["result"])
        self.assertEqual(child_job, result["rows"][0]["jobName"])

    def test_android_package_child_binds_original_workflow_and_job(self):
        for phase in ("package", "validation", "metadata"):
            with self.subTest(phase=phase):
                self.check_android_child_binds_original_workflow_and_job(phase)

    def check_android_child_binds_original_workflow_and_job(self, phase):
        instance, ready, _, _, files = self.shard(phase, component="sdk-android", target="android")
        workflow = "validation" if phase == "validation" else phase + "-validation"
        child_path = f".github/workflows/sdk-android-{workflow}.yml"
        child_job = f"product-validation / sdk-android-{phase}-result / sdk-android-{phase}-android"
        names = self.names
        with patch.object(self, "names", side_effect=lambda row, key: (child_job, names(row, key)[1])), \
                patch.object(adapter, "_verified_product_state", return_value=self.state({instance: ready})), \
                self.official_api({instance: ready}, {instance: archive(files)}) as (query, _, _):
            original_query = query.side_effect

            def child_run(url, token):
                result = original_query(url, token)
                if url.endswith(f"/attempts/{self.producer['runAttempt']}"):
                    return {**result, "referenced_workflows": [*result["referenced_workflows"], {
                        "path": f"{self.producer['repository']}/{child_path}@{PIN}", "sha": PIN}]}
                return result

            query.side_effect = child_run
            result = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                self.repository / f"build/android-{phase}-child", trusted_workflow_sha=PIN,
                repository_root=self.repository, environ=self.environment, token="synthetic-token",
                sdk_family="android-" + phase, sdk_worker_workflow_path=child_path,
                sdk_worker_job_name=child_job)
            query.side_effect = original_query
            with self.assertRaisesRegex(ValueError, "caller-pinned workflow"):
                adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                    self.repository / f"build/android-{phase}-unpinned", trusted_workflow_sha=PIN,
                    repository_root=self.repository, environ=self.environment, token="synthetic-token",
                    sdk_family="android-" + phase, sdk_worker_workflow_path=child_path,
                    sdk_worker_job_name=child_job)
        self.assertEqual("success", result["rows"][0]["result"])
        self.assertEqual(child_job, result["rows"][0]["jobName"])

    def test_each_js_phase_preserves_exact_original_shard_and_whole_worker_upload(self):
        for phase in ("package", "validation"):
            with self.subTest(phase=phase):
                instance, ready, shard, descriptor, files = self.shard(phase)
                before = regular_file_inventory(shard)
                raw = archive(files)
                destination = self.repository / f"build/collected-{phase}"
                result = self.collect({instance: ready}, {instance: raw}, destination)
                self.assertEqual(result, load_canonical_json(destination / "collection.json"))
                self.assertEqual(1, len(result["rows"]))
                row = result["rows"][0]
                self.assertEqual("success", row["result"])
                self.assertEqual(instance, adapter._identity(row))
                self.assertEqual(self.names(instance, ready["buildKey"]), (row["jobName"], row["artifactName"]))
                restored = destination / row["shardDirectory"]
                self.assertEqual(descriptor["receiptBytes"], (restored / "phase-receipt.json").read_bytes())
                self.assertEqual(before, regular_file_inventory(restored))
                original = destination / row["originalDirectory"]
                self.assertEqual(raw, (original.parent / "transport.zip").read_bytes())
                self.assertEqual(set(files), {item["relativePath"] for item in regular_file_inventory(original, allow_empty=True)})
                for name, contents in files.items():
                    self.assertEqual(contents, (original / name).read_bytes(), name)
                self.assertEqual(before, regular_file_inventory(shard))

    def test_wrong_sdk_version_producer_or_key_retains_diagnostics_but_rejects_shard(self):
        for wrong in ("version", "producer", "key"):
            with self.subTest(wrong=wrong):
                instance, ready, shard, _, files = self.shard("package", wrong=wrong)
                before = regular_file_inventory(shard)
                destination = self.repository / f"build/rejected-{wrong}"
                result = self.collect({instance: ready}, {instance: archive(files)}, destination)
                row = result["rows"][0]
                self.assertEqual("failure", row["result"])
                self.assertIn("elected plan and producer", row["reason"])
                self.assertIsNone(row["shardDirectory"])
                self.assertIsNotNone(row["originalDirectory"])
                self.assertEqual(b"", (destination / row["originalDirectory"] / "gradle.log").read_bytes())
                self.assertEqual(before, regular_file_inventory(shard))

    def test_unrelated_runtime_contract_and_sdk_rows_are_not_collected(self):
        instance, ready, _, _, files = self.shard("package")
        unrelated = [PhaseInstanceId(*identity) for identity in (
            ("runtime", "jvm", "binary", "jvm"),
            ("runtime", "runtime-aggregate", "metadata", "aggregate"),
            ("contract", "contract", "metadata", "common"),
            ("sdk", "sdk-core", "package", "common"),
            ("sdk", "python", "validation", "linux-x64"),
            ("sdk", "javascript", "metadata", "node"),
        )]
        state_ready = {instance: ready, **{identity: {"buildKey": "sha256:" + "c" * 64} for identity in unrelated}}
        with patch.object(adapter, "_verified_product_state", return_value=self.state(state_ready)), \
                self.official_api({instance: ready}, {instance: archive(files)}):
            result = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                self.repository / "build/only-js", trusted_workflow_sha=PIN, repository_root=self.repository,
                environ=self.environment, token="synthetic-token", sdk_javascript_only=True)
        self.assertEqual([instance], [adapter._identity(row) for row in result["rows"]])
        self.assertEqual("success", result["rows"][0]["result"])

    def test_no_sdk_ready_work_makes_no_official_requests(self):
        unrelated = PhaseInstanceId("runtime", "jvm", "binary", "jvm")
        with patch.object(adapter, "_verified_product_state", return_value=self.state({unrelated: {}})), \
                patch.object(adapter, "api_json") as query, patch.object(adapter, "paginated_items") as listing, \
                patch.object(adapter, "download_artifact_to_file") as download:
            result = adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                self.repository / "build/empty-sdk", trusted_workflow_sha=PIN, repository_root=self.repository,
                environ=self.environment, token="synthetic-token", sdk_javascript_only=True)
        self.assertEqual([], result["rows"])
        self.assertEqual([], result["observed"])
        query.assert_not_called()
        listing.assert_not_called()
        download.assert_not_called()

    def test_invalid_collection_scopes_fail_before_replay_or_network(self):
        for options in ({"sdk_javascript_only": 1}, {"sdk_javascript_only": "true"},
                        {"sdk_javascript_only": True, "runtime_aggregate_only": True}):
            with self.subTest(options=options), patch.object(adapter, "_verified_product_state") as replay, \
                    patch.object(adapter, "api_json") as query, self.assertRaisesRegex(ValueError, "boolean.*exclusive"):
                adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                    self.repository / "build/invalid", trusted_workflow_sha=PIN, repository_root=self.repository,
                    environ=self.environment, token="synthetic-token", **options)
            replay.assert_not_called()
            query.assert_not_called()

    def test_advancement_scope_cannot_count_runtime_failure_or_omit_sdk_row(self):
        instance, ready, _, _, _ = self.shard("package")
        runtime = PhaseInstanceId("runtime", "jvm", "binary", "jvm")
        state = self.state({instance: ready, runtime: {"buildKey": "sha256:" + "f" * 64}})
        state.consumer, state.requested, state.closure = {}, (instance, runtime), (instance, runtime)
        state.rebased_request, state.prior_by_instance = {}, {}
        state.sources, state.prior_carrier_phases = {}, {}
        state.prior = {"phases": [{**adapter._identity_record(identity), "state": "build",
            "buildKey": value["buildKey"]} for identity, value in state.prior_ready_plans.items()]}
        cases = (
            ({"runtime_workers_only": True}, (), "mutually exclusive"),
            ({"runtime_aggregate_only": True}, (), "mutually exclusive"),
            ({"sdk_javascript_only": 1}, (), "boolean"),
            ({}, (runtime,), "distinct elected build phases"),
            ({}, (), "exactly partition"),
        )
        for number, (options, failed, error) in enumerate(cases):
            destination = self.repository / f"build/advance-{number}"
            output = self.repository / f"github-output-{number}"
            with self.subTest(number=number), patch.object(adapter, "_verified_product_state", return_value=state), \
                    self.assertRaisesRegex(ValueError, error):
                adapter.advance_products(self.plan_path, self.discovery, self.discovery, [], destination, output,
                    repository_root=self.repository, environ=self.environment, failed_instances=failed,
                    **{"sdk_javascript_only": True, **options})
            self.assertFalse(destination.exists())
            self.assertIn("wave_failed=true", output.read_text())


if __name__ == "__main__":
    unittest.main()
