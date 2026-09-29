"""Original upload authentication with synthetic products; HTTP is the only mock."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ci.tests import test_contract_ci_originals as fixture
from ci.tests.test_products import phase_receipt
from products.inventory import publish_regular_tree as actual_publish_regular_tree
from products.registry import PhaseInstanceId

adapter = fixture.product_reuse
TARGET = "linux-x64"


class RuntimeOriginalCiTest(unittest.TestCase):
    api = fixture.ContractOriginalCiCaptureTest.api

    def download_fixture(self, artifact, token, destination, **_):
        phase = next(phase for phase, value in self.artifacts.items() if value["id"] == artifact["id"])
        Path(destination).write_bytes(self.archives[phase])

    def setUp(self):
        # Reuse the real original-CI run/attempt/commit/HTTP fixture, not a
        # mocked observer or shard verifier. No native execution is claimed.
        fixture.ContractOriginalCiCaptureTest.setUp(self)
        self.receipts = {}
        self.jobs = []
        from products.receipt import compute_build_key, write_output_manifest
        for index, phase in enumerate(fixture.PHASES, 101):
            stage = self.root / "runtime-stages" / phase
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/value.bin").write_bytes(f"synthetic {phase}\n".encode())
            write_output_manifest(stage, "runtime", TARGET, phase, TARGET, "0.2.0", {"binary": "outputs"})
            identity = {"product": "runtime", "component": TARGET, "phase": phase, "target": TARGET}
            inputs = phase_receipt()["inputs"]
            plan = {"schemaVersion": 1, **identity, "inputs": inputs,
                    "buildKey": compute_build_key(**identity, inputs=inputs)}
            upload = self.root / "runtime-uploads" / phase
            fixture.finalize_phase_object(stage_root=stage, phase_plan=plan, producer=self.producer,
                product_version="0.2.0", trust_domain="development", destination=upload / "shard")
            self.receipts[phase] = upload / "shard/phase-receipt.json"
            raw = fixture.archive_tree(upload)
            name = (f"codex-agent-runtime-worker-{TARGET}-{phase}-{TARGET}-"
                    f"{plan['buildKey'][7:]}-{self.producer['tree']}-attempt-2")
            self.artifacts[phase].update(name=name, digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw))
            self.archives[phase] = raw
            self.jobs.append({"id": index, "name": f"product-validation / runtime-{TARGET}-{phase}-{TARGET}",
                "run_id": 71, "head_sha": self.run["head_sha"], "status": "completed", "conclusion": "success",
                "started_at": "2026-09-06T10:00:00Z", "completed_at": "2026-09-06T10:30:00Z"})

    def capture(self, **changes):
        with mock.patch("reuse.api_request", side_effect=self.api(**changes)):
            return adapter.capture_runtime_original_ci_phases(self.receipts, self.output,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token")

    def failed_run(self, run_id=71, attempt=2):
        return {**self.run, "id": run_id, "run_attempt": attempt,
                "status": "completed", "conclusion": "failure"}

    def second_attempt_phase(self, phase, *, changed_output=False):
        """Make one genuine shard from another producer without changing its build key."""
        producer = {**self.producer, "runId": 72, "runAttempt": 3}
        original = fixture.load_canonical_json_bytes(self.receipts[phase].read_bytes())
        phase_plan = {key: original[key] for key in
                      ("schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        stage = self.root / "runtime-stages" / phase
        if changed_output:
            from products.receipt import write_output_manifest
            stage = self.root / "changed-runtime-stage" / phase
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/value.bin").write_bytes(b"different product bytes\n")
            write_output_manifest(stage, "runtime", TARGET, phase, TARGET, "0.2.0",
                                  {"binary": "outputs"})
        upload = self.root / "second-attempt" / phase
        fixture.finalize_phase_object(stage_root=stage, phase_plan=phase_plan, producer=producer,
            product_version="0.2.0", trust_domain="development", destination=upload / "shard")
        raw = fixture.archive_tree(upload)
        artifact = {**self.artifacts[phase], "id": 201 + fixture.PHASES.index(phase),
                    "name": f"codex-agent-runtime-worker-{TARGET}-{phase}-{TARGET}-"
                            f"{original['buildKey'][7:]}-{producer['tree']}-attempt-3",
                    "digest": fixture.sha256_bytes(raw), "size_in_bytes": len(raw),
                    "workflow_run": {"id": 72, "head_sha": self.run["head_sha"]}}
        artifact["archive_download_url"] = (
            f"https://api.github.com/repos/{fixture.REPOSITORY}/actions/artifacts/{artifact['id']}/zip")
        job = {**self.jobs[fixture.PHASES.index(phase)], "id": 201 + fixture.PHASES.index(phase),
               "run_id": 72}
        return upload / "shard/phase-receipt.json", artifact, raw, job

    def two_attempt_api(self, later_artifacts, later_jobs, later_archives, *, first_artifacts=None,
                        first_jobs=None):
        original_api = self.api(artifacts=self.artifacts if first_artifacts is None else first_artifacts,
                                jobs=self.jobs if first_jobs is None else first_jobs,
                                run=self.failed_run())
        prefix = f"https://api.github.com/repos/{fixture.REPOSITORY}"
        by_id = {artifact["id"]: artifact for artifact in later_artifacts.values()}
        by_url = {later_artifacts[phase]["archive_download_url"]: raw
                  for phase, raw in later_archives.items()}

        def request(url, token):
            self.assertEqual("not-a-real-token", token)
            if url == prefix + "/actions/runs/72/attempts/3":
                return json.dumps(self.failed_run(72, 3)).encode()
            if url.startswith(prefix + "/actions/runs/72/attempts/3/jobs?"):
                return json.dumps({"jobs": later_jobs}).encode()
            if url.startswith(prefix + "/actions/runs/72/artifacts?"):
                return json.dumps({"artifacts": list(later_artifacts.values())}).encode()
            if url in by_url:
                return by_url[url]
            if url.startswith(prefix + "/actions/artifacts/"):
                artifact_id = url.removeprefix(prefix + "/actions/artifacts/")
                if artifact_id.isdigit() and int(artifact_id) in by_id:
                    return json.dumps(by_id[int(artifact_id)]).encode()
            return original_api(url, token)

        return request

    def download_two_attempt_fixture(self, later_artifacts, later_archives, *, first_archives=None):
        raw_by_id = {artifact["id"]: later_archives[phase]
                     for phase, artifact in later_artifacts.items()}
        raw_by_id.update({artifact["id"]: (self.archives if first_archives is None else first_archives)[phase]
                          for phase, artifact in self.artifacts.items()})

        def download(artifact, token, destination, **_):
            self.assertEqual("not-a-real-token", token)
            Path(destination).write_bytes(raw_by_id[artifact["id"]])

        return download

    def test_original_uploads_and_receipts_are_retained_exactly(self):
        before = {phase: path.read_bytes() for phase, path in self.receipts.items()}
        result = self.capture()
        self.assertEqual(TARGET, result["target"])
        for phase in fixture.PHASES:
            retained = self.output / "phases" / phase
            self.assertEqual(self.archives[phase], (retained / "transport.zip").read_bytes())
            self.assertEqual(before[phase], (retained / "original/shard/phase-receipt.json").read_bytes())
            self.assertEqual(before[phase], self.receipts[phase].read_bytes())
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.capture()

    def test_successful_phase_jobs_remain_authentic_after_overall_run_failure(self):
        failed_run = {**self.run, "status": "completed", "conclusion": "failure"}
        originals = {phase: path.read_bytes() for phase, path in self.receipts.items()}
        result = self.capture(run=failed_run)
        self.assertEqual("failure", result["observed"][0]["run"]["conclusion"])
        for phase in fixture.PHASES:
            self.assertEqual(originals[phase],
                (self.output / "phases" / phase / "original/shard/phase-receipt.json").read_bytes())

    def test_ci_capture_accepts_independent_phases_but_release_requires_all_four(self):
        failed_run = {**self.run, "status": "completed", "conclusion": "failure"}
        receipts = {phase: self.receipts[phase] for phase in ("package", "validation")}
        with mock.patch("reuse.api_request", side_effect=self.api(run=failed_run)):
            result = adapter.capture_runtime_original_ci_phases(receipts, self.output,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token")
        self.assertEqual({"package", "validation"}, set(result["artifacts"]))
        self.assertFalse((self.output / "phases/binary").exists())
        self.assertFalse((self.output / "phases/metadata").exists())
        for phase, source in receipts.items():
            self.assertEqual(source.read_bytes(),
                (self.output / "phases" / phase / "original/shard/phase-receipt.json").read_bytes())

        with self.assertRaisesRegex(ValueError, "release requires all four"):
            adapter.capture_runtime_original_ci_phases(receipts, self.root / "incomplete-release",
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token",
                release_handoffs=(self.root / "release-handoff",),
                keyring=self.root / "keyring.json", keys_directory=self.root / "keys")

    def test_prior_failed_attempt_discovers_and_authenticates_requested_phases(self):
        failed_run = self.failed_run()
        listed = {phase: self.artifacts[phase] for phase in ("binary", "package")}
        plan = {"event": "pull_request", "pullRequest": 31,
                "repository": fixture.REPOSITORY}
        destination = self.root / "prior-capture"
        requested = {PhaseInstanceId("runtime", TARGET, phase, TARGET):
                     fixture.load_canonical_json_bytes(self.receipts[phase].read_bytes())["buildKey"]
                     for phase in ("binary", "package")}
        with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                mock.patch("reuse.api_request", side_effect=self.api(run=failed_run, artifacts=listed)):
            result = adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, requested, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token", attempts=(failed_run,))
            real_temp = self.root / "real-temp"
            real_temp.mkdir()
            linked_temp = self.root / "linked-temp"
            linked_temp.symlink_to(real_temp, target_is_directory=True)
            with mock.patch.object(tempfile, "tempdir", str(linked_temp)):
                records = adapter._prior_failed_runtime_objects(
                    destination, self.root, trusted_workflow_sha=self.pin,
                    token="not-a-real-token")
        self.assertEqual(set(requested), set(result))
        self.assertEqual({"binary", "package"}, {record["phase"] for record in records})
        for phase in ("binary", "package"):
            self.assertEqual(self.receipts[phase].read_bytes(),
                (destination / TARGET / phase / TARGET / "phases" / phase / "original/shard/phase-receipt.json").read_bytes())
        self.assertFalse((destination / TARGET / "validation").exists())
        # Replay authenticates the pinned producer even if a later failed run
        # becomes the newest recovery candidate.
        with mock.patch("reuse.api_request", side_effect=self.api(run=failed_run)):
            replayed = adapter._prior_failed_runtime_objects(
                destination, self.root, trusted_workflow_sha=self.pin,
                token="not-a-real-token", plan=plan,
                consumer_producer={"runId": 100, "runAttempt": 1})
            same_run = adapter._prior_failed_runtime_objects(
                destination, self.root, trusted_workflow_sha=self.pin,
                token="not-a-real-token", plan=plan,
                consumer_producer={"runId": 71, "runAttempt": 3})
        self.assertEqual({"binary", "package"}, {record["phase"] for record in replayed})
        self.assertEqual(replayed, same_run)

    def test_reviewed_original_workflow_survives_current_workflow_pin_rotation(self):
        legacy = adapter._PRIOR_RUNTIME_WORKFLOW_SHA
        current = "b4148a6320d3dfe8bfb556c6327937c6b304cf4c"
        self.pin = legacy
        self.run["referenced_workflows"] = [{
            "path": f"{fixture.REPOSITORY}/.github/workflows/product-validation.yml@{legacy}",
            "sha": legacy,
        }]
        failed_run = self.failed_run()
        instance = PhaseInstanceId("runtime", TARGET, "binary", TARGET)
        key = fixture.load_canonical_json_bytes(self.receipts["binary"].read_bytes())["buildKey"]
        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        destination = self.root / "rotated-pin-capture"
        with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                mock.patch("reuse.api_request", side_effect=self.api(
                    run=failed_run, artifacts={"binary": self.artifacts["binary"]})):
            captured = adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, {instance: key}, destination,
                trusted_workflow_sha=current, token="not-a-real-token", attempts=(failed_run,))
            records = adapter._prior_failed_runtime_objects(
                destination, self.root, trusted_workflow_sha=current, token="not-a-real-token",
                plan=plan, consumer_producer={"runId": 100, "runAttempt": 1})
        self.assertEqual({instance}, set(captured))
        self.assertEqual(key, records[0]["buildKey"])
        self.assertEqual(self.receipts["binary"].read_bytes(),
                         (destination / TARGET / "binary" / TARGET / "phases/binary/original/shard/phase-receipt.json").read_bytes())

    def test_prior_failed_phase_upload_is_diagnostic_not_a_reusable_shard(self):
        failed_run = self.failed_run()
        jobs = copy.deepcopy(self.jobs)
        jobs[1]["conclusion"] = "failure"
        listed = {phase: self.artifacts[phase] for phase in ("binary", "package")}
        destination = self.root / "prior-capture"
        plan = {"event": "pull_request", "pullRequest": 31,
                "repository": fixture.REPOSITORY}
        requested = {PhaseInstanceId("runtime", TARGET, phase, TARGET):
                     fixture.load_canonical_json_bytes(self.receipts[phase].read_bytes())["buildKey"]
                     for phase in ("binary", "package")}
        with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                mock.patch("reuse.api_request", side_effect=self.api(run=failed_run, jobs=jobs,
                                                            artifacts=listed)):
            result = adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, requested, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token", attempts=(failed_run,))
        self.assertEqual({PhaseInstanceId("runtime", TARGET, "binary", TARGET)}, set(result))
        self.assertFalse((destination / TARGET / "package").exists())

    def test_prior_failed_attempt_rejects_tampered_phase_without_publishing(self):
        failed_run = self.failed_run()
        malformed = copy.deepcopy(self.artifacts)
        malformed["binary"]["name"] = malformed["binary"]["name"].replace(
            self.producer["tree"], "0" * 40)
        destination = self.root / "prior-capture"
        plan = {"event": "pull_request", "pullRequest": 31,
                "repository": fixture.REPOSITORY}
        requested = {PhaseInstanceId("runtime", TARGET, "binary", TARGET):
                     fixture.load_canonical_json_bytes(self.receipts["binary"].read_bytes())["buildKey"]}
        with mock.patch.object(adapter, "download_artifact_to_file", side_effect=self.download_fixture), \
                mock.patch("reuse.api_request", side_effect=self.api(run=failed_run, artifacts=malformed,
                                                            details=malformed)), \
                self.assertRaisesRegex(ValueError, "selected attempt"):
            adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, requested, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token", attempts=(failed_run,))
        self.assertFalse(destination.exists())

    def test_prior_failed_phases_recover_independently_from_different_attempts(self):
        _, later_validation, raw_validation, later_job = self.second_attempt_phase("validation")
        requested = {
            PhaseInstanceId("runtime", TARGET, phase, TARGET):
                fixture.load_canonical_json_bytes(self.receipts[phase].read_bytes())["buildKey"]
            for phase in ("package", "validation")
        }
        destination = self.root / "phase-wise-capture"
        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        with mock.patch("reuse.api_request", side_effect=self.two_attempt_api(
                {"validation": later_validation}, [later_job], {"validation": raw_validation},
                first_artifacts={"package": self.artifacts["package"]})), \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=
                                  self.download_two_attempt_fixture(
                                      {"validation": later_validation}, {"validation": raw_validation})):
            adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, requested, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token",
                attempts=(self.failed_run(), self.failed_run(72, 3)))
            records = adapter._prior_failed_runtime_objects(
                destination, self.root, trusted_workflow_sha=self.pin,
                token="not-a-real-token", plan=plan,
                consumer_producer={"runId": 100, "runAttempt": 1})
        self.assertEqual({"package", "validation"}, {record["phase"] for record in records})
        for phase in ("package", "validation"):
            retained = destination / TARGET / phase / TARGET / "phases" / phase / "original/shard/phase-receipt.json"
            self.assertTrue(retained.is_file())
        package = fixture.load_canonical_json_bytes(
            (destination / TARGET / "package" / TARGET / "phases/package/original/shard/phase-receipt.json").read_bytes())
        validation = fixture.load_canonical_json_bytes(
            (destination / TARGET / "validation" / TARGET / "phases/validation/original/shard/phase-receipt.json").read_bytes())
        self.assertEqual((71, 2), (package["producer"]["runId"], package["producer"]["runAttempt"]))
        self.assertEqual((72, 3), (validation["producer"]["runId"], validation["producer"]["runAttempt"]))

    def test_prior_failed_adapter_validation_target_is_captured_independently(self):
        from products.receipt import compute_build_key, write_output_manifest

        instance = PhaseInstanceId("runtime", "jvm", "validation", TARGET)
        stage = self.root / "adapter-validation-stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/value.bin").write_bytes(b"jvm validation on linux x64\n")
        write_output_manifest(stage, "runtime", "jvm", "validation", TARGET, "0.2.0",
                              {"binary": "outputs"})
        inputs = phase_receipt()["inputs"]
        phase_plan = {"schemaVersion": 1, "product": "runtime", "component": "jvm",
                      "phase": "validation", "target": TARGET, "inputs": inputs,
                      "buildKey": compute_build_key(product="runtime", component="jvm",
                          phase="validation", target=TARGET, inputs=inputs)}
        upload = self.root / "adapter-validation-upload"
        fixture.finalize_phase_object(stage_root=stage, phase_plan=phase_plan, producer=self.producer,
            product_version="0.2.0", trust_domain="development", destination=upload / "shard")
        raw = fixture.archive_tree(upload)
        artifact = {**self.artifacts["validation"], "id": 501,
                    "name": f"codex-agent-runtime-worker-jvm-validation-{TARGET}-"
                            f"{phase_plan['buildKey'][7:]}-{self.producer['tree']}-attempt-2",
                    "digest": fixture.sha256_bytes(raw), "size_in_bytes": len(raw)}
        artifact["archive_download_url"] = (
            f"https://api.github.com/repos/{fixture.REPOSITORY}/actions/artifacts/501/zip")
        job = {**self.jobs[2], "id": 501,
               "name": f"product-validation / runtime-jvm-validation-{TARGET}"}
        original_api = self.api(run=self.failed_run())
        prefix = f"https://api.github.com/repos/{fixture.REPOSITORY}"

        def request(url, token):
            if url.startswith(prefix + "/actions/runs/71/artifacts?"):
                return json.dumps({"artifacts": [artifact]}).encode()
            if url.startswith(prefix + "/actions/runs/71/attempts/2/jobs?"):
                return json.dumps({"jobs": [job]}).encode()
            if url == prefix + "/actions/artifacts/501":
                return json.dumps(artifact).encode()
            if url == artifact["archive_download_url"]:
                return raw
            return original_api(url, token)

        def download(candidate, token, destination, **_):
            self.assertEqual(501, candidate["id"])
            Path(destination).write_bytes(raw)

        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        destination = self.root / "adapter-phase-capture"
        with mock.patch("reuse.api_request", side_effect=request), \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=download):
            captured = adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, {instance: phase_plan["buildKey"]}, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token",
                attempts=(self.failed_run(),))
            records = adapter._prior_failed_runtime_objects(
                destination, self.root, trusted_workflow_sha=self.pin,
                token="not-a-real-token", plan=plan,
                consumer_producer={"runId": 100, "runAttempt": 1})
        self.assertEqual({instance}, set(captured))
        self.assertEqual([(instance.component, instance.phase, instance.target)],
                         [(record["component"], record["phase"], record["target"]) for record in records])
        self.assertEqual((upload / "shard/phase-receipt.json").read_bytes(),
            (destination / "jvm/validation" / TARGET / "phases/validation/original/shard/phase-receipt.json").read_bytes())

    def test_prior_failed_phase_rejects_failed_or_partial_job_upload(self):
        instance = PhaseInstanceId("runtime", TARGET, "package", TARGET)
        requested = {instance: fixture.load_canonical_json_bytes(self.receipts["package"].read_bytes())["buildKey"]}
        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        failed_jobs = copy.deepcopy(self.jobs)
        failed_jobs[1]["conclusion"] = "failure"
        destination = self.root / "failed-phase-capture"
        with mock.patch("reuse.api_request", side_effect=self.two_attempt_api({}, [], {},
                first_jobs=failed_jobs)), \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=
                                  self.download_two_attempt_fixture({}, {})):
            result = adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, requested, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token",
                attempts=(self.failed_run(),))
        self.assertFalse(result)
        self.assertFalse(destination.exists())

        # A success-labelled job with only a diagnostic upload cannot become
        # a successful phase shard.
        partial = self.root / "partial-upload"
        partial.mkdir()
        (partial / "gradle.log").write_text("phase failed\n", encoding="utf-8")
        raw = fixture.archive_tree(partial)
        artifact = {**self.artifacts["package"], "digest": fixture.sha256_bytes(raw),
                    "size_in_bytes": len(raw)}
        original_api = self.api(artifacts={"package": artifact}, details={"package": artifact},
                                archives={**self.archives, "package": raw}, run=self.failed_run())
        with mock.patch("reuse.api_request", side_effect=original_api), \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=
                                  self.download_two_attempt_fixture({}, {},
                                      first_archives={**self.archives, "package": raw})), \
                self.assertRaises(ValueError):
            adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, requested, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token",
                attempts=(self.failed_run(),))
        self.assertFalse(destination.exists())

    def test_prior_failed_same_key_different_product_object_is_rejected(self):
        _, second_artifact, second_raw, second_job = self.second_attempt_phase(
            "package", changed_output=True)
        instance = PhaseInstanceId("runtime", TARGET, "package", TARGET)
        key = fixture.load_canonical_json_bytes(self.receipts["package"].read_bytes())["buildKey"]
        destination = self.root / "conflicting-phase-capture"
        plan = {"event": "pull_request", "pullRequest": 31, "repository": fixture.REPOSITORY}
        with mock.patch("reuse.api_request", side_effect=self.two_attempt_api(
                {"package": second_artifact}, [second_job], {"package": second_raw})), \
                mock.patch.object(adapter, "download_artifact_to_file", side_effect=
                                  self.download_two_attempt_fixture(
                                      {"package": second_artifact}, {"package": second_raw})), \
                self.assertRaisesRegex(ValueError, "conflict|different|same.key"):
            adapter.capture_prior_failed_runtime_phases(
                plan, {"runId": 100, "runAttempt": 1}, {instance: key}, destination,
                trusted_workflow_sha=self.pin, token="not-a-real-token",
                attempts=(self.failed_run(), self.failed_run(72, 3)))
        self.assertFalse(destination.exists())

    def test_late_original_shard_mutation_cannot_publish(self):
        def mutate_before_copy(source, destination, **kwargs):
            (Path(source) / "phases/binary/original/shard/phase-receipt.json").write_bytes(
                b"changed after verification")
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch.object(adapter, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_failed_job_wrong_attempt_window_digest_and_workflow_reject(self):
        failed = copy.deepcopy(self.jobs)
        failed[2]["conclusion"] = "failure"
        window = copy.deepcopy(self.artifacts)
        window["metadata"]["created_at"] = "2026-09-06T11:00:00Z"
        wrong_pin = copy.deepcopy(self.run)
        wrong_pin["referenced_workflows"][0]["sha"] = "a" * 40
        for changes in ({"jobs": failed}, {"artifacts": window, "details": window},
                        {"run": wrong_pin}, {"archives": {**self.archives, "binary": b"changed"}}):
            with self.subTest(changes=list(changes)), self.assertRaises(ValueError):
                self.capture(**changes)
            self.assertFalse(self.output.exists())

    def test_wrong_receipt_and_missing_upload_reject_without_output(self):
        self.receipts["metadata"] = self.receipts["binary"]
        with self.assertRaisesRegex(ValueError, "phase identity"):
            self.capture()
        self.receipts["metadata"] = self.root / "runtime-uploads/metadata/shard/phase-receipt.json"
        missing = {phase: value for phase, value in self.artifacts.items() if phase != "metadata"}
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.capture(artifacts=missing)
        self.assertFalse(self.output.exists())

    def test_valid_but_different_receipt_is_not_laundered_by_the_upload(self):
        path = self.receipts["metadata"]
        value = fixture.load_canonical_json_bytes(path.read_bytes())
        value["productVersion"] = "0.2.1"
        path.write_bytes(fixture.canonical_json_bytes(value))
        with self.assertRaisesRegex(ValueError, "differs from the requested original receipt"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_mixed_original_run_attempts_keep_their_receipts(self):
        producer = {**self.producer, "runId": 72, "runAttempt": 3}
        prior = fixture.load_canonical_json_bytes(self.receipts["metadata"].read_bytes())
        plan = {key: prior[key] for key in ("schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        upload = self.root / "later-original"
        fixture.finalize_phase_object(stage_root=self.root / "runtime-stages/metadata", phase_plan=plan,
            producer=producer, product_version="0.2.0", trust_domain="development", destination=upload / "shard")
        self.receipts["metadata"] = upload / "shard/phase-receipt.json"
        raw = fixture.archive_tree(upload)
        self.archives["metadata"] = raw
        artifact = self.artifacts["metadata"]
        artifact.update(name=artifact["name"].removesuffix("attempt-2") + "attempt-3",
                        digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw),
                        workflow_run={"id": 72, "head_sha": self.run["head_sha"]})
        later_run = {**self.run, "id": 72, "run_attempt": 3}
        later_job = {**self.jobs[-1], "run_id": 72}
        original_api = self.api()
        prefix = f"https://api.github.com/repos/{fixture.REPOSITORY}/actions/runs/72"

        def request(url, token):
            if url == prefix + "/attempts/3":
                return json.dumps(later_run).encode()
            if url.startswith(prefix + "/attempts/3/jobs?"):
                return json.dumps({"jobs": [later_job]}).encode()
            if url.startswith(prefix + "/artifacts?"):
                return json.dumps({"artifacts": [artifact]}).encode()
            return original_api(url, token)

        with mock.patch("reuse.api_request", side_effect=request):
            result = adapter.capture_runtime_original_ci_phases(self.receipts, self.output,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token")
        self.assertEqual(2, len(result["observed"]))
        self.assertEqual(self.receipts["metadata"].read_bytes(),
            (self.output / "phases/metadata/original/shard/phase-receipt.json").read_bytes())


class RuntimeRetainedOriginalTest(unittest.TestCase):
    api = fixture.ContractOriginalCiCaptureTest.api

    def setUp(self):
        RuntimeOriginalCiTest.setUp(self)
        from ci.tests import test_product_runtime_variant as variant
        from products.runtime_attestation import build_runtime_variant_attestation
        from products.signatures import generate_development_key
        self.private, self.public, signing = generate_development_key(self.root / "release-key")
        self.signing = {**signing, "trustDomain": "release", "keyId": "retained-fixture"}
        self.keys = self.root / "public-policy/keys"
        self.keys.mkdir(parents=True)
        (self.keys / "retained-fixture.pub").write_bytes(self.public.read_bytes())
        self.keyring = self.keys.parent / "keyring.json"
        policy = {"schemaVersion": 1, **{key: self.signing[key] for key in ("algorithm", "namespace", "trustDomain")},
                  "activeKey": {key: self.signing[key] for key in ("keyId", "fingerprint")}, "retiredKeys": []}
        self.keyring.write_bytes(fixture.canonical_json_bytes(policy))
        original = variant.Fixture(self.root / "native-original", self.private, self.public, signing)
        self.payload = variant.produce_runtime_variant(**original.arguments())["bundlePath"]
        self.receipts = {**original.receipt_paths, "metadata": variant._write_metadata_receipt(original, self.payload)}
        self.handoff = self.root / "release-handoff"
        build_runtime_variant_attestation(self.payload, *(self.receipts[phase] for phase in fixture.PHASES),
            original.validation, self.signing, self.private, self.public, self.handoff,
            keyring=self.keyring, keys_directory=self.keys, complete_handoff=True)

    def capture(self, **changes):
        arguments = dict(target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token",
                         release_handoffs=(self.handoff,), keyring=self.keyring, keys_directory=self.keys)
        arguments.update(changes)
        return adapter.capture_runtime_original_ci_phases(self.receipts, self.output, **arguments)

    def test_complete_retired_release_reuses_without_network_or_signing(self):
        policy = fixture.load_canonical_json_bytes(self.keyring.read_bytes())
        policy["retiredKeys"] = [policy["activeKey"]]
        policy["activeKey"] = None
        self.keyring.write_bytes(fixture.canonical_json_bytes(policy))
        before = fixture.regular_file_inventory(self.handoff)
        with mock.patch("reuse.api_request", side_effect=AssertionError("network")), \
                mock.patch("products.runtime_attestation.sign_manifest", side_effect=AssertionError("sign")):
            result = self.capture()
        self.assertEqual([], result["observed"])
        self.assertEqual({}, result["artifacts"])
        self.assertEqual(dict.fromkeys(fixture.PHASES, 0), result["releaseAttestations"])
        self.assertEqual(before, fixture.regular_file_inventory(self.output / "release-handoffs/0"))
        self.assertEqual(before, fixture.regular_file_inventory(self.handoff))

    def test_private_release_policy_swap_cannot_publish(self):
        original = adapter.load_keyring
        caller_bytes = self.keyring.read_bytes()
        swapped = False

        def swap_after_private_copy(keyring, keys):
            nonlocal swapped
            result = original(keyring, keys)
            keyring, keys = Path(keyring), Path(keys)
            if not swapped and keys.parent == keyring.parent:
                value = fixture.load_canonical_json_bytes(keyring.read_bytes())
                value["retiredKeys"] = [value["activeKey"]]
                value["activeKey"] = None
                keyring.write_bytes(fixture.canonical_json_bytes(value))
                swapped = True
            return result

        with mock.patch.object(adapter, "load_keyring", side_effect=swap_after_private_copy), \
                mock.patch("reuse.api_request", side_effect=AssertionError("network")), \
                self.assertRaisesRegex(ValueError, "release policy differs from caller"):
            self.capture()
        self.assertTrue(swapped)
        self.assertEqual(caller_bytes, self.keyring.read_bytes())
        self.assertFalse(self.output.exists())

    def test_mixed_release_and_ci_preserves_originals_and_fetches_only_missing_phase(self):
        from products.receipt import write_output_manifest
        receipt = fixture.load_canonical_json_bytes(self.receipts["metadata"].read_bytes())
        stage = self.root / "new-metadata-stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs" / self.payload.name).write_bytes(self.payload.read_bytes())
        write_output_manifest(stage, "runtime", TARGET, "metadata", TARGET, receipt["productVersion"],
                              {"runtime-variant": "outputs"})
        upload = self.root / "new-metadata-upload"
        plan = {key: receipt[key] for key in ("schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        fixture.finalize_phase_object(stage_root=stage, phase_plan=plan, producer=self.producer,
            product_version=receipt["productVersion"], trust_domain="development", destination=upload / "shard")
        self.receipts["metadata"] = upload / "shard/phase-receipt.json"
        raw = fixture.archive_tree(upload)
        self.archives["metadata"] = raw
        self.artifacts["metadata"].update(digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw),
            name=f"codex-agent-runtime-worker-{TARGET}-metadata-{TARGET}-{receipt['buildKey'][7:]}-{self.producer['tree']}-attempt-2")
        with mock.patch("reuse.api_request", side_effect=self.api()) as http:
            result = self.capture()
        self.assertEqual({"metadata"}, set(result["artifacts"]))
        self.assertEqual(dict.fromkeys(("binary", "package", "validation"), 0), result["releaseAttestations"])
        downloaded = [call.args[0] for call in http.call_args_list if call.args[0].endswith("/zip")]
        self.assertEqual([self.artifacts["metadata"]["archive_download_url"]], downloaded)

    def test_invalid_retained_evidence_never_falls_back_to_ci(self):
        with mock.patch("reuse.api_request", side_effect=AssertionError("network")):
            for changes in ({"keyring": None}, {"keys_directory": None}, {"release_handoffs": ()},
                            {"target": "macos-x64"}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    self.capture(**changes)
                self.assertFalse(self.output.exists())
            (self.handoff / "unexpected").write_bytes(b"untrusted")
            with self.assertRaises(ValueError):
                self.capture()
            self.assertFalse(self.output.exists())
