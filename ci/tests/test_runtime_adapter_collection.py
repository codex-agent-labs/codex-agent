"""Adapter collection over real original shards and synthetic official API data.

The success case uses the existing signed Contract/planner fixture and real
shard/continuation verifiers. No compiler or actual hosted execution is claimed.
"""

from contextlib import contextmanager
from types import SimpleNamespace
import shutil
import unittest
from unittest import mock

from ci.products.inventory import load_canonical_json, regular_file_inventory, sha256_bytes
from ci.tests.test_product_resume_capture import archive
from ci.tests import test_runtime_worker_collection as fixture


adapter = fixture.adapter
PhaseInstanceId = adapter.PhaseInstanceId
PIN = "c" * 40


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class RuntimeAdapterCollectionTest(unittest.TestCase):
    setUpClass = classmethod(fixture.RuntimeWorkerCollectionTest.setUpClass.__func__)
    control_seams = classmethod(fixture.RuntimeWorkerCollectionTest.control_seams.__func__)
    setUp = fixture.RuntimeWorkerCollectionTest.setUp
    tearDown = fixture.RuntimeWorkerCollectionTest.tearDown
    resume = fixture.RuntimeWorkerCollectionTest.resume
    binary_shard = fixture.RuntimeWorkerCollectionTest.binary_shard
    advance = fixture.RuntimeWorkerCollectionTest.advance

    def names(self, instance, key):
        identity = f"{instance.component}-{instance.phase}-{instance.target}"
        return (
            f"product-validation / runtime-{identity}",
            f"codex-agent-runtime-worker-{identity}-{key.removeprefix('sha256:')}-"
            f"{self.producer['tree']}-attempt-{self.producer['runAttempt']}",
        )

    @contextmanager
    def official_api(self, ready, uploads):
        producer = self.producer
        run = {
            "id": producer["runId"], "run_attempt": producer["runAttempt"],
            "path": producer["workflowPath"], "event": producer["event"],
            "status": "completed", "conclusion": "failure", "head_sha": producer["commit"],
            "repository": {"full_name": producer["repository"], "fork": False},
            "head_repository": {"full_name": producer["repository"], "fork": False},
            "pull_requests": [{"number": producer["pullRequest"],
                               "base": {"sha": "1" * 40}, "head": {"sha": "2" * 40}}],
            "referenced_workflows": [{
                "path": f"{producer['repository']}/.github/workflows/product-validation.yml@{PIN}",
                "sha": PIN,
            }],
        }
        commit = {"sha": producer["commit"], "tree": {"sha": producer["tree"]},
                  "parents": [{"sha": "1" * 40}, {"sha": "2" * 40}]}
        base_job = {"run_id": producer["runId"], "head_sha": producer["commit"],
                    "status": "completed", "started_at": "2026-09-08T10:00:00Z",
                    "completed_at": "2026-09-08T10:10:00Z"}
        jobs = [{**base_job, "id": 900, "name": "product-validation / product-resume",
                 "conclusion": "success"}]
        artifacts, downloads = {}, {}
        for index, (instance, plan) in enumerate(sorted(ready.items()), 901):
            job_name, artifact_name = self.names(instance, plan["buildKey"])
            jobs.append({**base_job, "id": index, "name": job_name,
                         "conclusion": "success" if instance in uploads else "failure"})
            if instance not in uploads:
                continue
            raw = uploads[instance]
            url = f"https://api.github.com/repos/{producer['repository']}/actions/artifacts/{index}"
            artifacts[index] = {
                "id": index, "name": artifact_name, "digest": sha256_bytes(raw),
                "size_in_bytes": len(raw), "expired": False, "archive_download_url": url + "/zip",
                "created_at": "2026-09-08T10:05:00Z",
                "workflow_run": {"id": producer["runId"], "head_sha": producer["commit"]},
            }
            downloads[index] = raw

        def api(url, token):
            self.assertEqual("synthetic-token", token)
            if "/actions/artifacts/" in url:
                return artifacts[int(url.rsplit("/", 1)[-1])]
            if "/commits/" in url:
                return commit
            if url.endswith(f"/attempts/{producer['runAttempt']}"):
                return run
            self.fail(f"Unexpected API request: {url}")

        def listing(url, field, token):
            self.assertEqual("synthetic-token", token)
            if field == "jobs":
                self.assertTrue(url.endswith(f"/attempts/{producer['runAttempt']}/jobs"))
                return jobs
            self.assertEqual("artifacts", field)
            self.assertTrue(url.endswith(f"/runs/{producer['runId']}/artifacts"))
            return list(artifacts.values())

        with mock.patch.object(adapter, "api_json", side_effect=api) as query, \
                mock.patch.object(adapter, "paginated_items", side_effect=listing) as listed, \
                mock.patch.object(adapter, "download_artifact", side_effect=lambda item, token: downloads[item["id"]]) as downloaded:
            yield query, listed, downloaded

    def collect(self, resumed, destination):
        with self.control_seams():
            return adapter.collect_runtime_workers(
                self.plan_path, resumed, resumed, destination,
                trusted_workflow_sha=PIN, repository_root=self.repository,
                environ=self.environment, token="synthetic-token",
            )

    def test_good_jvm_shard_survives_bad_node_upload_and_actual_failure_reconciliation(self):
        resumed = self.resume()
        shard, descriptor = self.binary_shard(resumed, "original-collected-jvm")
        ready = {
            instance: load_canonical_json(resumed / f"phase-plans/runtime-{instance.component}-binary-{instance.target}.json")
            for instance in (fixture.JVM, fixture.NODE)
        }
        files = {"shard/" + path.relative_to(shard).as_posix(): path.read_bytes()
                 for path in shard.rglob("*") if path.is_file()}
        files.update({"gradle.log": b"", "execution.json": b"{\"synthetic\":true}\n",
                      "inputs/original-input.bin": b"exact retained synthetic input\x00\xff"})
        original_state = regular_file_inventory(resumed)
        original_shard = regular_file_inventory(shard)
        destination = self.scratch / "collected-uploads"
        # Both official jobs succeed; Node's uploaded content is invalid. The
        # collector must retain JVM and report the bad row without early exit.
        with self.official_api(ready, {fixture.JVM: archive(files), fixture.NODE: archive({"diagnostic.log": b"no shard"})}):
            result = self.collect(resumed, destination)
        self.assertEqual(result, load_canonical_json(destination / "collection.json"))
        self.assertEqual(self.producer, result["producer"])
        rows = {adapter._identity(row): row for row in result["rows"]}
        self.assertEqual({fixture.JVM, fixture.NODE}, set(rows))
        self.assertEqual("success", rows[fixture.JVM]["result"])
        self.assertEqual("failure", rows[fixture.NODE]["result"])
        self.assertTrue(rows[fixture.NODE]["reason"])
        self.assertIsNone(rows[fixture.NODE]["shardDirectory"])
        collected = destination / rows[fixture.JVM]["shardDirectory"]
        self.assertEqual(descriptor["receiptBytes"], (collected / "phase-receipt.json").read_bytes())
        self.assertEqual(original_shard, regular_file_inventory(collected))
        original = destination / rows[fixture.JVM]["originalDirectory"]
        self.assertEqual(set(files), {path.relative_to(original).as_posix() for path in original.rglob("*") if path.is_file()})
        for name, raw in files.items():
            self.assertEqual(raw, (original / name).read_bytes(), name)
        before = regular_file_inventory(destination, allow_empty=True)
        advanced = self.scratch / "advanced-collected"
        replay = self.advance(resumed, [collected], advanced, failed=(fixture.NODE,))
        phases = {adapter._identity(phase): phase for phase in replay["phases"]}
        self.assertEqual("retained", phases[fixture.JVM]["state"])
        self.assertEqual(descriptor["receiptSha256"], phases[fixture.JVM]["receiptSha256"])
        self.assertEqual("build", phases[fixture.NODE]["state"])
        self.assertIn("wave_failed=true", (self.scratch / "advanced-collected-github-output").read_text())
        self.assertEqual(before, regular_file_inventory(destination, allow_empty=True))
        self.assertEqual(original_state, regular_file_inventory(resumed))
        self.assertEqual(original_shard, regular_file_inventory(shard))

    def test_host_validation_rows_have_unique_targets_and_exclude_other_products_and_aggregate(self):
        targets = ("linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64")
        identities = {PhaseInstanceId("runtime", component, "validation", target)
                      for component in ("jvm", "node-js", "node-wasm") for target in targets}
        identities.add(PhaseInstanceId("runtime", "node-js", "validation", "node-js-binding"))
        ready = {instance: {**adapter._identity_record(instance), "buildKey": "sha256:" + "a" * 64}
                 for instance in identities}
        unrelated = (
            PhaseInstanceId("contract", "contract", "metadata", "common"),
            PhaseInstanceId("sdk", "sdk-javascript", "binary", "common"),
            PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"),
        )
        state = SimpleNamespace(producer=self.producer, plan=self.plan,
                                expected_fixed={"versions": {"runtime-release": "0.2.0"}},
                                prior_ready_plans={**ready, **{instance: {"buildKey": "sha256:" + "b" * 64}
                                                           for instance in unrelated}})
        destination = self.scratch / "host-collection"
        with mock.patch.object(adapter, "_verified_product_state", return_value=state), self.official_api(ready, {}):
            result = self.collect(self.discovery, destination)
        rows = result["rows"]
        self.assertEqual(identities, {adapter._identity(row) for row in rows})
        self.assertEqual(16, len({row["jobName"] for row in rows}))
        self.assertEqual(16, len({row["artifactName"] for row in rows}))
        for row in rows:
            self.assertEqual(self.names(adapter._identity(row), row["buildKey"]),
                             (row["jobName"], row["artifactName"]))
            self.assertEqual("failure", row["result"])
            self.assertIsNone(row["artifact"])
            self.assertIsNone(row["shardDirectory"])

    def test_empty_ready_wave_has_no_remote_observation_or_download(self):
        state = SimpleNamespace(producer=self.producer, plan=self.plan, prior_ready_plans={})
        with mock.patch.object(adapter, "_verified_product_state", return_value=state), \
                mock.patch.object(adapter, "api_json") as query, \
                mock.patch.object(adapter, "paginated_items") as listed, \
                mock.patch.object(adapter, "download_artifact") as downloaded:
            result = self.collect(self.discovery, self.scratch / "empty-collection")
        self.assertEqual([], result["rows"])
        self.assertEqual([], result["observed"])
        query.assert_not_called()
        listed.assert_not_called()
        downloaded.assert_not_called()


if __name__ == "__main__":
    unittest.main()
