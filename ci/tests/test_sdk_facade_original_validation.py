"""Real shard/selection/lifetime composition, mocked official capture/full replay.

These fixtures do not claim genuine worker, signature, compiler or host proof.
"""

from copy import deepcopy
from pathlib import Path, PurePosixPath, PureWindowsPath
import unittest
from unittest.mock import patch

from ci import sdk_facade_original_validation as original
from ci.tests import test_sdk_facade_capture as capture_fixture
from ci.tests import test_sdk_facade_inputs as input_fixture
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, sha256_file
from products.restore import PHASE_PLAN_KEYS


class OriginalFacadeValidationTest(unittest.TestCase):
    def setUp(self):
        self.f = capture_fixture.FacadeCaptureTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.i = input_fixture.FacadeInputsTest(methodName="runTest")
        self.i.setUp()
        self.addCleanup(self.i.doCleanups)
        self.i.value.update(repository=str(self.f.root), sdkVersion="0.8.0")
        self.i.request.write_bytes(canonical_json_bytes(self.i.value))
        self.root = self.f.root
        self.environment = {"GITHUB_RUN_ID": "999", "GITHUB_RUN_ATTEMPT": "99"}
        self.tooling = self.root / "tooling"
        self.tooling.mkdir()
        (self.tooling / "evidence.json").write_bytes(b"opaque tool fixture\n")
        self.key, self.java = self.root / "public.pub", self.root / "java"
        self.key.write_bytes(b"opaque public key")
        self.java.write_bytes(b"opaque Java executable")
        self.setup_upload()
        self.enterContext(patch.object(original, "_request_inventory", side_effect=lambda path: {path: sha256_file(path)}))
        self.capture = self.enterContext(patch.object(original, "capture_sdk_facade_validation_upload", side_effect=self.capture_upload))
        self.plan_gate = self.enterContext(patch.object(original.product_reuse, "_validate_plan", return_value=self.f.plan))
        self.consumer = self.enterContext(patch.object(original.product_reuse, "_consumer", return_value={"producer": self.f.producer}))
        self.source_gate = self.enterContext(patch.object(original, "capture_facade_validation_sources", side_effect=self.capture_source))
        self.full_gate = self.enterContext(patch.object(original, "verify_sdk_facade_validation_original_content", side_effect=self.replay))
        self.observation_gate = self.enterContext(patch.object(original, "verify_facade_execution_observation"))

    def setup_upload(self, target="jvm", windows=False):
        self.f.select(target)
        self.i.value["target"] = target
        self.i.request.write_bytes(canonical_json_bytes(self.i.value))
        path = PureWindowsPath(r"C:\original checkout") if windows else PurePosixPath("/original checkout")
        self.context = {"repositoryRoot": str(path), "androidSdkDirectory": ""}
        if windows:
            self.context["javaExecutable"] = r"C:\Java17\bin\java.exe"
        worker = path / "build/phase-worker"
        self.record = {"schemaVersion": 1, "producer": self.f.producer, "target": target,
            "buildKey": self.f.receipt["buildKey"], "originalContext": self.context, "workerDirectory": str(worker)}
        self.request_record = {**self.i.value, "repository": str(path)}
        fields = {
            "codexAgent.product": "sdk", "codexAgent.component": "sdk-core", "codexAgent.phase": "validation",
            "codexAgent.target": target, "codexAgent.sdkVersion": "0.8.0",
            "codexAgent.candidateCommit": self.f.producer["commit"], "codexAgent.candidateTree": self.f.producer["tree"],
            "codexAgent.sdkFacadeValidationRequest": str(worker / "facade-request.json"),
        }
        command = original.product_reuse._runtime_worker_command(str(path / ("gradlew.bat" if windows else "gradlew")),
            fields, {"JAVA_HOME": r"C:\Java17"} if windows else {}, build_directory=".",
            platform_name="nt" if windows else "posix")
        self.execution = {"schemaVersion": 1, "producer": self.f.producer, "buildKey": self.f.receipt["buildKey"],
            "command": command, "returnCode": 0, "launchError": None, "elapsedNs": 3}
        self.files = {name: raw for name, raw in self.f.files.items() if name.startswith("shard/")}
        self.source_files = {"gradle/template.kt": b"immutable original source fixture\n"}
        self.files.update({"worker/execution.json": canonical_json_bytes(self.execution), "worker/gradle.log": b"",
            "worker/host-observation/observation.json": b"opaque separately tested host observation fixture\n",
            "worker/facade-request.json": canonical_json_bytes(self.request_record),
            **{"worker/source/" + name: raw for name, raw in self.source_files.items()},
            "selection/impact-plan.json": canonical_json_bytes(self.f.plan),
            "selection/producer.json": canonical_json_bytes(self.f.producer),
            "selection/phase-plan.json": canonical_json_bytes({key: self.f.receipt[key] for key in PHASE_PLAN_KEYS}),
            "context/execution-context.json": canonical_json_bytes(self.record),
            "inputs/predecessors.json": b"opaque materialized dependency closure\n",
            "originals/request.json": canonical_json_bytes(self.request_record),
            "retained-execution/inputs/inputs.json": b"opaque retained inputs\n",
            "retained-execution/consumer/build.gradle.kts": b"opaque consumer\n",
            "retained-execution/consumer-inputs/build.gradle.kts": b"opaque captured consumer\n",
            "retained-execution/execution/process/stderr.bin": b"",
            "retained-execution/publication-metadata.json": b"opaque metadata\n",
            "retained-execution/compiler-inputs.json": b"opaque compiler fixture, separately verified\n",
            "retained-execution/report.json": b"opaque report\n"})

    def capture_upload(self, plan, destination, **kwargs):
        self.assertEqual(self.f.plan_path, plan)
        self.assertEqual(self.f.receipt_bytes, Path(kwargs["validation_receipt_path"]).read_bytes())
        self.assertNotEqual(self.f.receipt_path, kwargs["validation_receipt_path"])
        self.assertEqual(self.environment, kwargs["environ"])
        for name, raw in self.files.items():
            path = destination / "original" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        transport = {"artifact": {"id": 701}, "observed": [], "captureProducer": self.f.producer,
                     "validationReceiptSha256": sha256_bytes(self.f.receipt_bytes)}
        (destination / "capture-transport.json").write_bytes(canonical_json_bytes(transport))
        self.captured = destination
        return transport

    def capture_source(self, repository, revision, destination):
        self.assertEqual((self.root, self.f.producer["commit"]), (repository, revision))
        for name, raw in self.source_files.items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        return {"tree": self.f.producer["tree"], "files": regular_file_inventory(destination)}

    def replay(self, **kwargs):
        self.assertEqual(self.i.request, kwargs["facade_request"])
        self.assertEqual(self.context, kwargs["original_context"])
        self.assertEqual(self.f.receipt_bytes, Path(kwargs["validation_receipt"]).read_bytes())
        self.assertEqual(self.captured / "original/retained-execution/inputs", kwargs["prepared_inputs"])
        self.assertEqual(self.captured / "original/retained-execution/consumer-inputs", kwargs["consumer_inputs"])
        self.assertEqual(self.captured / "original/retained-execution/execution", kwargs["execution_directory"])
        self.assertEqual("e" * 40, kwargs["policy_revision"])
        return deepcopy(self.f.receipt), self.f.receipt_bytes

    def context_manager(self):
        return original.verified_original_sdk_facade_validation(self.f.plan_path, self.f.receipt_path,
            artifact_id=701, artifact_sha256=self.f.artifact["digest"], trusted_workflow_sha=self.f.pin,
            facade_request=self.i.request, repository_root=self.root, environ=self.environment, token="synthetic-token",
            tooling_evidence=self.tooling, tooling_public_key=self.key, java_executable=self.java,
            policy_revision="e" * 40, required_trust_domain="development")

    def test_full_gate_holds_observed_originals_and_restored_receipt_through_context(self):
        with self.context_manager() as value:
            self.assertEqual(self.f.receipt_bytes, value["receiptBytes"])
            self.assertTrue(value["stage"].is_dir())
            self.assertEqual(self.f.receipt, value["receipt"])
            self.assertIs(type(value["receipt"]), dict)
            self.full_gate.assert_called_once()
            self.observation_gate.assert_called_once_with(value["original"] / "worker/host-observation",
                repository=self.root, producer=self.f.producer, target=self.f.receipt["target"],
                original_repository_root=self.context["repositoryRoot"],
                original_java_executable=self.context.get("javaExecutable"))
            self.assertEqual({"expected_revision": self.f.producer["commit"]}, self.plan_gate.call_args.kwargs)
            stage = value["stage"]
        self.assertFalse(stage.exists())

    def test_observation_is_mandatory_and_setup_cannot_replace_selected_receipt(self):
        self.observation_gate.side_effect = ValueError("original observation rejected")
        with self.assertRaisesRegex(ValueError, "original observation rejected"), self.context_manager():
            pass
        self.full_gate.assert_not_called()
        self.observation_gate.side_effect = None
        sources = original._sources
        def mutate(value):
            result = sources(value)
            self.f.receipt_path.write_bytes(canonical_json_bytes({**self.f.receipt, "trustDomain": "release"}))
            return result
        self.capture.reset_mock()
        with patch.object(original, "_sources", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed during recovery"), self.context_manager():
            pass
        self.capture.assert_not_called()

    def test_windows_original_java_command_is_checked_independently_of_replay_host(self):
        self.setup_upload("windows-x64", windows=True)
        with self.context_manager() as value:
            self.assertEqual("windows-x64", value["receipt"]["target"])
        self.assertEqual(r"C:\Java17\bin\java.exe", self.execution["command"][0])
        self.execution["command"][0] = r"C:\other\java.exe"
        self.files["worker/execution.json"] = canonical_json_bytes(self.execution)
        with self.assertRaisesRegex(ValueError, "fixed root command"), self.context_manager():
            pass

    def test_execution_identity_argv_success_and_context_path_are_not_advisory(self):
        baseline = deepcopy(self.execution)
        for field, value in (("returnCode", False), ("returnCode", 1), ("launchError", "failure"),
                             ("buildKey", "sha256:" + "d" * 64), ("elapsedNs", -1),
                             ("command", baseline["command"] + ["otherTask"])):
            record = {**deepcopy(baseline), field: value}
            self.files["worker/execution.json"] = canonical_json_bytes(record)
            with self.subTest(field=field, value=value), self.assertRaises(ValueError), self.context_manager():
                pass
        self.files["worker/execution.json"] = canonical_json_bytes(baseline)
        self.files["context/execution-context.json"] = canonical_json_bytes({**self.record, "workerDirectory": "/outside/worker"})
        with self.assertRaisesRegex(ValueError, "original checkout"), self.context_manager():
            pass
        self.full_gate.assert_not_called()

    def test_original_source_selection_and_full_semantics_remain_required(self):
        self.files["worker/source/gradle/template.kt"] = b"different source\n"
        with self.assertRaisesRegex(ValueError, "immutable Git"), self.context_manager():
            pass
        self.files["worker/source/gradle/template.kt"] = self.source_files["gradle/template.kt"]
        self.plan_gate.return_value = {**self.f.plan, "remoteBuildAuthorized": False}
        with self.assertRaisesRegex(ValueError, "not authorized"), self.context_manager():
            pass
        self.plan_gate.return_value = self.f.plan
        self.full_gate.side_effect = ValueError("full semantic replay failed")
        with self.assertRaisesRegex(ValueError, "full semantic replay failed"), self.context_manager():
            pass

    def test_changed_inputs_during_replay_or_caller_use_are_rejected(self):
        before = self.key.read_bytes()
        def mutate(**kwargs):
            result = self.replay(**kwargs)
            self.key.write_bytes(b"changed key")
            return result
        self.full_gate.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "changed during recovery"), self.context_manager():
            pass
        self.key.write_bytes(before)
        self.full_gate.side_effect = self.replay
        with self.assertRaisesRegex(ValueError, "changed during recovery"):
            with self.context_manager() as value:
                (value["original"] / "worker/gradle.log").write_bytes(b"late diagnostics mutation")

    def test_extra_control_root_or_crosspaired_full_gate_receipt_rejects(self):
        self.files["unexpected/data.json"] = b"unrequested control\n"
        with self.assertRaisesRegex(ValueError, "retained layout"), self.context_manager():
            pass
        del self.files["unexpected/data.json"]
        for name in ("inputs/predecessors.json", "originals/request.json"):
            raw = self.files.pop(name)
            with self.subTest(missing=name), self.assertRaisesRegex(ValueError, "retained layout"), self.context_manager():
                pass
            self.files[name] = raw
        self.full_gate.side_effect = lambda **kwargs: ({**self.f.receipt, "trustDomain": "release"}, self.f.receipt_bytes)
        with self.assertRaisesRegex(ValueError, "different original receipt"), self.context_manager():
            pass
