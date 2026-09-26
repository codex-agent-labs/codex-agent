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
            self.assertIsNotNone(failed["originalDirectory"])
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

    def test_core_validation_child_binds_each_target_job(self):
        child_path = ".github/workflows/sdk-core-validation.yml"
        job_template = "product-validation / sdk-core-validation-wave / sdk-core-validation-{target}"
        shards = [self.shard("validation", component="sdk-core", target=target)
                  for target in ("jvm", "linux-x64")]
        ready = {instance: plan for instance, plan, _, _, _ in shards}
        uploads = {instance: archive(files) for instance, _, _, _, files in shards}
        names = self.names

        def child_names(instance, key):
            return job_template.replace("{target}", instance.target), names(instance, key)[1]

        with patch.object(self, "names", side_effect=child_names), \
                patch.object(adapter, "_verified_product_state", return_value=self.state(ready)), \
                self.official_api(ready, uploads) as (query, _, _):
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
        self.assertEqual(2, len(result["rows"]))
        self.assertEqual({"success"}, {row["result"] for row in result["rows"]})
        self.assertEqual({job_template.replace("{target}", target) for target in ("jvm", "linux-x64")},
                         {row["jobName"] for row in result["rows"]})

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
        instance, ready, _, _, files = self.shard("package", component="sdk-android", target="android")
        child_path = ".github/workflows/sdk-android-package-validation.yml"
        child_job = "product-validation / sdk-android-package-result / sdk-android-package-android"
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
                self.repository / "build/android-package-child", trusted_workflow_sha=PIN,
                repository_root=self.repository, environ=self.environment, token="synthetic-token",
                sdk_family="android-package", sdk_worker_workflow_path=child_path,
                sdk_worker_job_name=child_job)
            query.side_effect = original_query
            with self.assertRaisesRegex(ValueError, "caller-pinned workflow"):
                adapter.collect_runtime_workers(self.plan_path, self.discovery, self.discovery,
                    self.repository / "build/android-package-unpinned", trusted_workflow_sha=PIN,
                    repository_root=self.repository, environ=self.environment, token="synthetic-token",
                    sdk_family="android-package", sdk_worker_workflow_path=child_path,
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
