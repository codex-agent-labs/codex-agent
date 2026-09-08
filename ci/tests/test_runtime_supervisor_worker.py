"""Control composition only; real replay/content/process gates have separate tests."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock

from ci.tests.test_runtime_supervisor_capture import product_reuse as worker
from ci.products.inventory import write_canonical_json


class RuntimeSupervisorWorkerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="supervisor-worker-control-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "discovery").mkdir()
        self.destination = self.root / "build/worker"
        self.instance = worker.PhaseInstanceId("runtime", "linux-arm64", "binary", "linux-arm64")
        self.ready = {"buildKey": "sha256:" + "a" * 64}
        self.producer = {"commit": "c" * 40}
        self.state = SimpleNamespace(prior_ready_plans={self.instance: self.ready},
                                     producer=self.producer, expected_fixed={"versions": {"runtime-release": "0.2.0"}},
                                     plan={"event": "pull_request"})
        self.properties = {"codexAgent.runtimeBinaryPlan": str(self.destination / "inputs/full-plan.json")}
        self.manifest = {"fixture": "in-memory verified manifest"}
        self.upload = {"artifactId": 1, "artifactSha256": "sha256:" + "b" * 64,
                       "trustedWorkflowSha": "d" * 40}
        self.stack = self.enterContext(ExitStack())
        self.replay = self.stack.enter_context(mock.patch.object(worker, "_verified_product_state", return_value=self.state))
        self.stack.enter_context(mock.patch.object(worker, "_runtime_worker_checkout"))
        self.stack.enter_context(mock.patch.object(worker, "_runtime_worker_environment", return_value=({}, self.root / "gradlew")))
        self.host = self.stack.enter_context(mock.patch("native_wrappers.host_classifier", return_value="linux-arm64"))
        self.prepare = self.stack.enter_context(mock.patch.object(worker, "_prepare_runtime_phase", side_effect=self.prepared))
        self.capture = self.stack.enter_context(mock.patch.object(worker, "capture_runtime_supervisor_upload",
                                                                return_value={"captureProducer": self.producer}))
        self.content = self.stack.enter_context(mock.patch("runtime_supervisor.verify_supervisor_handoff"))
        self.supervisor = self.stack.enter_context(mock.patch("runtime_supervisor.execute_supervisor", return_value={"fixture": True}))
        self.process = self.stack.enter_context(mock.patch.object(worker.subprocess, "run", return_value=SimpleNamespace(returncode=0)))
        self.finalize = self.stack.enter_context(mock.patch.object(worker, "finalize_phase_object", return_value={"fixture": True}))

    def prepared(self, *_arguments):
        write_canonical_json(Path(self.properties["codexAgent.runtimeBinaryPlan"]),
                             {**self.ready, "runtimeBinaryIdentity": {"fixture": True}})
        return dict(self.properties), self.manifest

    def execute_supervisor(self, key=None):
        return worker.execute_runtime_supervisor(
            self.root / "plan", self.root / "discovery", None, self.destination,
            expected_build_key=self.ready["buildKey"] if key is None else key,
            repository_root=self.root, environ={})

    def execute_binary(self, upload=None):
        self.host.return_value = "linux-x64"
        with mock.patch("runtime_native_phase.route", return_value={
            "runnerOs": "Linux", "runnerArch": "X64", "supervisor": {"runnerArch": "ARM64"},
        }):
            return worker.execute_runtime_phase(
                self.root / "plan", self.root / "discovery", None, self.instance, self.destination,
                expected_build_key=self.ready["buildKey"], repository_root=self.root, environ={},
                supervisor_upload=upload)

    def test_supervisor_entry_uses_elected_key_and_in_memory_manifest(self):
        with self.assertRaisesRegex(ValueError, "elected build key"):
            self.execute_supervisor("sha256:" + "f" * 64)
        self.prepare.assert_not_called()
        self.host.return_value = "linux-x64"
        with self.assertRaisesRegex(ValueError, "actual Linux ARM64"):
            self.execute_supervisor()
        self.prepare.assert_not_called()
        self.host.return_value = "linux-arm64"
        self.assertEqual({"fixture": True}, self.execute_supervisor())
        supplied = self.supervisor.call_args.kwargs
        self.assertIs(self.manifest, supplied["contract_manifest"])
        self.assertEqual(self.producer, supplied["producer"])
        self.assertEqual(self.ready["buildKey"], supplied["phase_plan"]["buildKey"])
        self.assertEqual(self.destination / "supervisor", supplied["destination"])

    def test_cross_builder_captures_then_verifies_before_fixed_process(self):
        events = []
        self.capture.side_effect = lambda *_args, **_kwargs: (events.append("capture") or {"captureProducer": self.producer})
        self.content.side_effect = lambda *_args, **_kwargs: events.append("content")
        self.process.side_effect = lambda *_args, **_kwargs: (events.append("process") or SimpleNamespace(returncode=0))
        self.assertEqual({"fixture": True}, self.execute_binary(self.upload))
        self.assertEqual(["capture", "content", "process"], events)
        self.assertEqual(self.ready["buildKey"], self.capture.call_args.kwargs["expected_build_key"])
        self.assertIs(self.manifest, self.content.call_args.kwargs["contract_manifest"])
        self.assertIn(f"-PcodexAgent.desktopSupervisorDirectory={self.destination}/inputs/supervisor-upload/original",
                      self.process.call_args.args[0])
        self.finalize.assert_called_once()

    def test_missing_upload_and_untrusted_content_cannot_start_cross_builder(self):
        with self.assertRaisesRegex(ValueError, "authenticated supervisor"):
            self.execute_binary()
        self.prepare.assert_not_called()
        self.content.side_effect = ValueError("bad original content")
        with self.assertRaisesRegex(ValueError, "bad original content"):
            self.execute_binary(self.upload)
        self.process.assert_not_called()
        self.finalize.assert_not_called()

    def test_cli_rejects_partial_supervisor_authority_before_execution(self):
        with mock.patch.object(worker, "execute_runtime_phase") as execute, \
                mock.patch("sys.stderr"), self.assertRaises(SystemExit):
            worker.main([
                "execute-runtime-phase", "--plan", "plan", "--discovery-root", "discovery",
                "--destination", "destination", "--product", "runtime", "--component", "linux-arm64",
                "--phase", "binary", "--target", "linux-arm64", "--expected-build-key", self.ready["buildKey"],
                "--supervisor-artifact-id", "1"])
        execute.assert_not_called()

    def test_changed_prepared_generic_plan_cannot_reselect_supervisor_work(self):
        def changed(*arguments):
            result = self.prepared(*arguments)
            write_canonical_json(Path(self.properties["codexAgent.runtimeBinaryPlan"]),
                                 {"buildKey": "sha256:" + "f" * 64, "runtimeBinaryIdentity": {}})
            return result
        self.prepare.side_effect = changed
        with self.assertRaisesRegex(ValueError, "original elected plan"):
            self.execute_supervisor()
        self.supervisor.assert_not_called()

    def test_cross_builder_rejects_original_producer_rebinding_before_content(self):
        self.capture.return_value = {"captureProducer": {"commit": "f" * 40}}
        with self.assertRaisesRegex(ValueError, "current elected producer"):
            self.execute_binary(self.upload)
        self.content.assert_not_called()
        self.process.assert_not_called()
        self.finalize.assert_not_called()
