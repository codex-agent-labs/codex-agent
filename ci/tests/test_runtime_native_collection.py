"""Native transport collection only: state replay and shard verification are mocked.

These fixtures test original upload binding and sibling retention, not native
execution, valid product receipts, or final campaign admission.
"""
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from ci.tests import test_runtime_supervisor_capture as supervisor_fixture
from ci.tests.test_product_resume_capture import archive, product_reuse
from products.inventory import canonical_json_bytes, load_canonical_json, sha256_bytes
from products.registry import NATIVE_TARGETS, PhaseInstanceId


class RuntimeNativeCollectionTest(unittest.TestCase):
    def setUp(self):
        fixture = supervisor_fixture.RuntimeSupervisorCaptureTest()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        for name in ("root", "plan_path", "environment", "producer", "pin", "run", "commit", "job"):
            setattr(self, name, copy.deepcopy(getattr(fixture, name)))
        self.job["name"] = "product-validation / product-resume"
        self.discovery = self.root / "build/discovery"
        self.state_root = self.root / "build/state"
        self.discovery.mkdir(parents=True)
        self.state_root.mkdir()
        self.ready, self.receipts, self.artifacts, self.raw = {}, {}, [], {}
        self.jobs = [self.job]
        self.contents = {}
        for index, component in enumerate(NATIVE_TARGETS, 1):
            instance = PhaseInstanceId("runtime", component, "binary", component)
            key = "sha256:" + f"{index:064x}"
            identity = {"product": "runtime", "component": component, "phase": "binary", "target": component}
            self.ready[instance] = {"schemaVersion": 1, **identity, "buildKey": key, "inputs": {}}
            self.receipts[instance] = {"schemaVersion": 1, **identity, "buildKey": key,
                                       "producer": self.producer, "productVersion": "0.2.4",
                                       "trustDomain": "development", "result": "success"}
            job_name = f"product-validation / runtime-{component}-binary-{component}"
            self.jobs.append({**self.job, "id": 910 + index, "name": job_name,
                              "started_at": "2026-09-08T10:00:00Z", "completed_at": "2026-09-08T10:10:00Z"})
            artifact_id = 100 + index
            members = {
                "shard/phase-receipt.json": canonical_json_bytes(self.receipts[instance]),
                "shard/mock-object.txt": b"synthetic shard boundary; verifier mocked\n",
                "inputs/original-proof.txt": b"preserved original input; replay mocked\n",
                "gradle.log": b"", "execution.json": b"raw process fixture\n",
            }
            self.contents[component] = members
            self.raw[artifact_id] = archive(members)
            url = f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/{artifact_id}"
            self.artifacts.append({
                "id": artifact_id, "digest": sha256_bytes(self.raw[artifact_id]), "expired": False,
                "name": f"codex-agent-runtime-worker-{component}-binary-{component}-{key.removeprefix('sha256:')}-"
                        f"{self.producer['tree']}-attempt-{self.producer['runAttempt']}",
                "size_in_bytes": len(self.raw[artifact_id]), "archive_download_url": url + "/zip",
                "created_at": "2026-09-08T10:05:00Z",
                "workflow_run": {"id": self.producer["runId"], "head_sha": self.producer["commit"]},
            })
        self.state = SimpleNamespace(
            plan=product_reuse._validate_plan(self.plan_path, self.root), producer=self.producer,
            prior_ready_plans=self.ready, expected_fixed={"versions": {"runtime-release": "0.2.4"}})

    def collect(self, destination, *, shard_failure=None, receipt_changes=None,
                runtime_aggregate_only=False):
        prefix = "https://api.github.com/repos/codex-agent-labs/codex-agent"
        def query(url, token):
            self.assertEqual("not-a-real-token", token)
            if url == prefix + "/actions/runs/91/attempts/3":
                return self.run
            if url == prefix + "/git/commits/" + self.producer["commit"]:
                return self.commit
            matches = [artifact for artifact in self.artifacts if url == prefix + f"/actions/artifacts/{artifact['id']}"]
            if len(matches) == 1:
                return matches[0]
            raise AssertionError(f"Unexpected API request: {url}")
        def listing(url, key, token):
            self.assertEqual("not-a-real-token", token)
            if (url, key) == (prefix + "/actions/runs/91/attempts/3/jobs", "jobs"):
                return self.jobs
            if (url, key) == (prefix + "/actions/runs/91/artifacts", "artifacts"):
                return self.artifacts
            raise AssertionError(f"Unexpected listing: {(url, key)}")
        def verify(root, instance):
            self.assertEqual("shard", Path(root).name)
            self.assertEqual(canonical_json_bytes(self.receipts[instance]), (Path(root) / "phase-receipt.json").read_bytes())
            if instance.component == shard_failure:
                raise ValueError("synthetic shard verifier rejection")
            changes = (receipt_changes or {}).get(instance.component, {})
            return {"receipt": {**self.receipts[instance], **changes}}
        with mock.patch.object(product_reuse, "_verified_product_state", return_value=self.state), \
                mock.patch.object(product_reuse, "api_json", side_effect=query) as api, \
                mock.patch.object(product_reuse, "paginated_items", side_effect=listing) as lists, \
                mock.patch.object(product_reuse, "download_artifact_to_file", side_effect=lambda artifact, token, destination, **kwargs:
                    Path(destination).write_bytes(self.raw[artifact["id"]])) as download, \
                mock.patch.object(product_reuse, "verify_phase_shard", side_effect=verify) as verifier:
            result = product_reuse.collect_runtime_workers(
                self.plan_path, self.discovery, self.state_root, destination,
                trusted_workflow_sha=self.pin, repository_root=self.root,
                environ=self.environment, token="not-a-real-token",
                runtime_aggregate_only=runtime_aggregate_only)
        return result, api, lists, download, verifier

    def test_aggregate_collection_binds_exact_original_and_excludes_native_workers(self):
        instance = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        identity = product_reuse._identity_record(instance)
        original = next(iter(self.receipts.values()))
        receipt = {**original, **identity}
        key = receipt["buildKey"]
        self.ready[instance] = {**identity, "buildKey": key}
        self.receipts[instance] = receipt
        name = "runtime-aggregate-metadata-aggregate"
        self.jobs.append({**self.jobs[1], "id": 999,
                          "name": f"product-validation / runtime-{name}"})
        raw = archive({"shard/phase-receipt.json": canonical_json_bytes(receipt),
                       "execution.json": b"synthetic aggregate execution\n"})
        self.raw[999] = raw
        self.artifacts.append({**self.artifacts[0], "id": 999,
            "name": f"codex-agent-runtime-worker-{name}-{key.removeprefix('sha256:')}-"
                    f"{self.producer['tree']}-attempt-{self.producer['runAttempt']}",
            "digest": sha256_bytes(raw), "size_in_bytes": len(raw),
            "archive_download_url": "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/999/zip"})
        result, _, _, download, verifier = self.collect(
            self.root / "build/aggregate-only", runtime_aggregate_only=True)
        self.assertEqual(1, len(result["rows"]))
        row = result["rows"][0]
        self.assertEqual(instance, product_reuse._identity(row))
        self.assertEqual("success", row["result"])
        self.assertEqual(1, download.call_count)
        self.assertEqual(1, verifier.call_count)
        bad, _, _, _, _ = self.collect(self.root / "build/bad-aggregate",
            runtime_aggregate_only=True, receipt_changes={"runtime-aggregate": {"buildKey": "sha256:" + "f" * 64}})
        self.assertEqual("failure", bad["rows"][0]["result"])
        self.assertIsNone(bad["rows"][0]["shardDirectory"])

    def rows(self, result):
        self.assertEqual(5, len(result["rows"]))
        return {row["component"]: row for row in result["rows"]}

    def test_all_five_native_uploads_preserve_originals_and_use_one_original_attempt_listing(self):
        destination = self.root / "build/native-collection"
        before = self.plan_path.read_bytes()
        result, _, lists, download, verifier = self.collect(destination)
        self.assertEqual(result, load_canonical_json(destination / "collection.json"))
        self.assertEqual(self.producer, result["producer"])
        self.assertEqual(self.run, result["observed"][0]["run"])
        rows = self.rows(result)
        self.assertEqual(set(NATIVE_TARGETS), set(rows))
        for component, row in rows.items():
            self.assertEqual("success", row["result"])
            self.assertEqual(f"product-validation / runtime-{component}-binary-{component}", row["jobName"])
            original = destination / row["originalDirectory"]
            self.assertEqual(original / "shard", destination / row["shardDirectory"])
            for name, contents in self.contents[component].items():
                self.assertEqual(contents, (original / name).read_bytes())
        self.assertEqual(before, self.plan_path.read_bytes())
        self.assertEqual(5, download.call_count)
        self.assertEqual(5, verifier.call_count)
        self.assertEqual(1, sum(call.args[1] == "artifacts" for call in lists.call_args_list))
        self.assertEqual(1, sum(call.args[1] == "jobs" for call in lists.call_args_list))

    def test_cli_forwards_current_state_and_only_caller_pinned_workflow(self):
        destination = self.root / "build/cli-native-collection"
        with mock.patch.object(product_reuse, "collect_runtime_workers") as collect, \
                mock.patch.dict(product_reuse.os.environ, {"GITHUB_TOKEN": "not-a-real-token"}, clear=True):
            self.assertEqual(0, product_reuse.main([
                "collect-runtime-workers", "--plan", str(self.plan_path),
                "--discovery-root", str(self.discovery), "--state-root", str(self.state_root),
                "--destination", str(destination), "--trusted-workflow-sha", self.pin]))
        collect.assert_called_once_with(
            self.plan_path, self.discovery, self.state_root, destination,
            trusted_workflow_sha=self.pin, token="not-a-real-token", sdk_validation_tooling=None)

    def test_each_native_family_failure_leaves_the_other_four_original_shards_available(self):
        for component in NATIVE_TARGETS:
            with self.subTest(component=component):
                destination = self.root / f"build/native-isolated-{component}"
                result, _, _, _, _ = self.collect(destination, shard_failure=component)
                rows = self.rows(result)
                self.assertEqual("failure", rows[component]["result"])
                self.assertIsNone(rows[component]["shardDirectory"])
                for other in NATIVE_TARGETS:
                    if other != component:
                        self.assertEqual("success", rows[other]["result"])
                        self.assertTrue((destination / rows[other]["shardDirectory"]).is_dir())

    def test_failed_job_and_bad_shard_retain_diagnostics_and_all_successful_siblings(self):
        failed, invalid, *successful = NATIVE_TARGETS
        next(job for job in self.jobs if job["name"] == f"product-validation / runtime-{failed}-binary-{failed}")["conclusion"] = "failure"
        destination = self.root / "build/native-mixed"
        result, _, _, _, _ = self.collect(destination, shard_failure=invalid)
        rows = self.rows(result)
        for component in (failed, invalid):
            row = rows[component]
            self.assertEqual("failure", row["result"])
            self.assertTrue(row["reason"])
            self.assertIsNone(row["shardDirectory"])
            self.assertEqual(b"", (destination / row["originalDirectory"] / "gradle.log").read_bytes())
        for component in successful:
            self.assertEqual("success", rows[component]["result"])
            self.assertTrue((destination / rows[component]["shardDirectory"]).is_dir())

    def test_wrong_attempt_timestamp_digest_duplicate_and_missing_uploads_do_not_discard_siblings(self):
        cases = ("attempt", "before", "after", "digest", "duplicate", "missing")
        for index, case in enumerate(cases):
            artifacts, raw = copy.deepcopy(self.artifacts), dict(self.raw)
            first = self.artifacts[0]
            try:
                if case == "attempt":
                    first["name"] = first["name"].replace("-attempt-3", "-attempt-2")
                elif case == "before":
                    first["created_at"] = "2026-09-08T09:59:59Z"
                elif case == "after":
                    first["created_at"] = "2026-09-08T10:10:01Z"
                elif case == "digest":
                    self.raw[first["id"]] = b"changed upload bytes"
                elif case == "duplicate":
                    self.artifacts.append({**first, "id": 999})
                else:
                    self.artifacts.pop(0)
                with self.subTest(case=case):
                    result, _, _, _, _ = self.collect(self.root / f"build/native-upload-negative-{index}")
                    rows = self.rows(result)
                    self.assertEqual("failure", rows[NATIVE_TARGETS[0]]["result"])
                    for component in NATIVE_TARGETS[1:]:
                        self.assertEqual("success", rows[component]["result"])
            finally:
                self.artifacts, self.raw = artifacts, raw

    def test_missing_duplicate_and_crosspaired_jobs_are_local_failures_but_live_job_blocks_collection(self):
        first = self.jobs[1]
        for index, case in enumerate(("missing", "duplicate", "run", "head")):
            original = copy.deepcopy(self.jobs)
            try:
                if case == "missing":
                    self.jobs.pop(1)
                elif case == "duplicate":
                    self.jobs.append(copy.deepcopy(first))
                else:
                    self.jobs[1]["run_id" if case == "run" else "head_sha"] = 92 if case == "run" else "f" * 40
                with self.subTest(case=case):
                    result, _, _, _, _ = self.collect(self.root / f"build/native-job-negative-{index}")
                    rows = self.rows(result)
                    self.assertEqual("failure", rows[NATIVE_TARGETS[0]]["result"])
                    self.assertTrue(all(rows[component]["result"] == "success" for component in NATIVE_TARGETS[1:]))
            finally:
                self.jobs = original
        self.jobs[1].update(status="in_progress", conclusion=None, completed_at=None)
        destination = self.root / "build/native-still-running"
        with self.assertRaisesRegex(ValueError, "running|terminal|completed"):
            self.collect(destination)
        self.assertFalse(destination.exists())

    def test_wrong_original_run_attempt_never_becomes_per_row_success(self):
        self.run["run_attempt"] = 2
        destination = self.root / "build/native-wrong-original-attempt"
        with self.assertRaises(ValueError):
            self.collect(destination)
        self.assertFalse(destination.exists())

    def test_verified_shard_must_still_match_current_key_producer_version_and_trust(self):
        component = NATIVE_TARGETS[0]
        for index, changes in enumerate((
            {"buildKey": "sha256:" + "f" * 64}, {"productVersion": "0.2.3"},
            {"trustDomain": "release"}, {"producer": {**self.producer, "runAttempt": 2}},
        )):
            with self.subTest(changes=changes):
                result, _, _, _, _ = self.collect(
                    self.root / f"build/native-receipt-negative-{index}", receipt_changes={component: changes})
                rows = self.rows(result)
                self.assertEqual("failure", rows[component]["result"])
                self.assertIsNone(rows[component]["shardDirectory"])
                self.assertTrue(all(rows[other]["result"] == "success" for other in NATIVE_TARGETS[1:]))
