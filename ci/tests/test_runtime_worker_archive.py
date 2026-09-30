"""Control tests for the native worker's caller-supplied app-server archive."""

from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest import mock

from ci.products.inventory import write_canonical_json
from ci.tests.test_runtime_supervisor_capture import product_reuse as worker


class RuntimeWorkerArchiveTest(unittest.TestCase):
    def test_linux_x64_bootstrap_uses_a_fresh_stable_home(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner_temp = Path(temporary).resolve()
            environment = {"RUNNER_TEMP": str(runner_temp), "CODEX_AGENT_VERIFIED_DEPENDENCY_FETCH": "true"}
            with mock.patch("products.toolchain_capture_bootstrap.prepare", return_value={
                    "plugin": "plugin.jar", "archive": "native.tar.gz", "compiler": "compiler"}) as prepare:
                worker._provision_runtime_native_toolchain(
                    runner_temp, "c" * 40, "linux-x64", runner_temp / "worker", environment)
                home = runner_temp / "codex-runtime-konan-linux-x64"
                self.assertEqual(str(home), environment["KONAN_DATA_DIR"])
                self.assertEqual(home, prepare.call_args.args[-1])
                self.assertTrue(home.is_dir())
                with self.assertRaises(FileExistsError):
                    worker._provision_runtime_native_toolchain(
                        runner_temp, "c" * 40, "linux-x64", runner_temp / "retry", environment)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-worker-archive-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "discovery").mkdir()
        self.destination = self.root / "build/worker"
        self.archive = self.root / "inputs/codex-app-server.zip"
        self.archive.parent.mkdir()
        self.archive.write_bytes(b"synthetic pinned archive\x00\xff\n")
        self.linker_scripts = {}
        for target, source_set in (("macos-arm64", "macosArm64Main"), ("macos-x64", "macosX64Main"),
                                   ("linux-x64", "linuxX64Main")):
            relative = f"codex-agent-runtime-desktop/src/{source_set}/gradle/deterministic-native-link.init.gradle"
            path = self.root / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(f"// synthetic {target} linker policy\n".encode())
            self.linker_scripts[target] = path
        self.git_bytes = self.enterContext(mock.patch.object(
            worker, "git_regular_blob_bytes",
            side_effect=lambda root, revision, relative, **kwargs: (root / relative).read_bytes(),
        ))
        self.instance = worker.PhaseInstanceId(
            "runtime", "macos-arm64", "binary", "macos-arm64",
        )
        self.ready = {"schemaVersion": 1, "product": "runtime", "component": "macos-arm64",
                      "phase": "binary", "target": "macos-arm64", "inputs": {},
                      "buildKey": "sha256:" + "a" * 64}
        self.producer = {"commit": "c" * 40}
        self.state = SimpleNamespace(
            prior_ready_plans={self.instance: self.ready},
            producer=self.producer,
            expected_fixed={"versions": {"runtime-release": "0.2.0"}},
            plan={"event": "pull_request"},
        )
        self.replay = self.enterContext(mock.patch.object(
            worker, "_verified_product_state", return_value=self.state,
        ))
        self.enterContext(mock.patch.object(worker, "_runtime_worker_checkout"))
        self.environment = self.enterContext(mock.patch.object(
            worker,
            "_runtime_worker_environment",
            return_value=({}, self.root / "gradlew"),
        ))
        self.host = self.enterContext(mock.patch(
            "native_wrappers.host_classifier", return_value="macos-arm64",
        ))
        self.route = self.enterContext(mock.patch(
            "runtime_native_phase.route",
            return_value={
                "runnerOs": "macOS",
                "runnerArch": "ARM64",
                "supervisor": None,
            },
        ))
        self.prepare = self.enterContext(mock.patch.object(
            worker, "_prepare_runtime_phase", side_effect=self.prepared,
        ))
        self.capture = self.enterContext(mock.patch(
            "runtime_native_phase.capture_archive", side_effect=self.capture_archive,
        ))
        self.process = self.enterContext(mock.patch.object(
            worker.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 0),
        ))
        self.finalize = self.enterContext(mock.patch.object(
            worker, "finalize_phase_object", return_value={"fixture": True},
        ))

    def prepared(self, _state, _instance, destination, *_arguments):
        destination.mkdir(parents=True)
        write_canonical_json(destination / "gradle-properties.json", {"fixture": "input"})
        return {"fixture": "property"}, {"fixture": "verified manifest"}

    def capture_archive(self, _plan, *, source, destination, **_keywords):
        destination.mkdir(parents=True)
        (destination / source.name).write_bytes(source.read_bytes())
        return destination

    def execute(self, *, archive=True):
        return worker.execute_runtime_phase(
            self.root / "plan",
            self.root / "discovery",
            None,
            self.instance,
            self.destination,
            expected_build_key=self.ready["buildKey"],
            repository_root=self.root,
            environ={},
            app_server_archive=self.archive if archive else None,
        )

    def test_native_binary_captures_archive_before_process_and_uses_private_directory(self):
        events = []

        def capture(*arguments, **keywords):
            events.append("capture")
            return self.capture_archive(*arguments, **keywords)

        def process(*_arguments, **_keywords):
            events.append("process")
            return subprocess.CompletedProcess([], 0)

        self.capture.side_effect = capture
        self.process.side_effect = process
        self.assertEqual({"fixture": True}, self.execute())

        self.assertEqual(["capture", "process"], events)
        supplied = self.capture.call_args
        self.assertIs(self.ready, supplied.args[0])
        self.assertEqual(self.root, supplied.kwargs["repository_root"])
        self.assertEqual(self.producer["commit"], supplied.kwargs["revision"])
        self.assertEqual(self.archive, supplied.kwargs["source"])
        captured = self.destination / "inputs/app-server-archive"
        self.assertEqual(captured, supplied.kwargs["destination"])
        self.assertEqual(self.archive.read_bytes(), (captured / self.archive.name).read_bytes())
        self.assertIn(
            f"-PcodexAgent.desktopArchiveDirectory={captured}",
            self.process.call_args.args[0],
        )
        self.finalize.assert_called_once()
        command = self.process.call_args.args[0]
        self.assertEqual(str(self.linker_scripts["macos-arm64"]), command[command.index("-I") + 1])
        self.git_bytes.assert_called_once_with(
            self.root, self.producer["commit"], self.linker_scripts["macos-arm64"].relative_to(self.root).as_posix(),
            max_bytes=64 * 1024,
        )

    def test_macos_x64_uses_its_exact_target_linker_policy(self):
        self.instance = worker.PhaseInstanceId("runtime", "macos-x64", "binary", "macos-x64")
        self.ready.update(component="macos-x64", target="macos-x64")
        self.state.prior_ready_plans = {self.instance: self.ready}
        self.host.return_value = "macos-x64"
        self.route.return_value = {"runnerOs": "macOS", "runnerArch": "X64", "supervisor": None}
        self.assertEqual({"fixture": True}, self.execute())
        command = self.process.call_args.args[0]
        self.assertEqual(str(self.linker_scripts["macos-x64"]), command[command.index("-I") + 1])
        self.git_bytes.assert_called_once_with(
            self.root, self.producer["commit"], self.linker_scripts["macos-x64"].relative_to(self.root).as_posix(),
            max_bytes=64 * 1024,
        )

    def test_linux_x64_uses_its_exact_path_policy(self):
        self.instance = worker.PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        self.ready.update(component="linux-x64", target="linux-x64")
        self.state.prior_ready_plans = {self.instance: self.ready}
        self.host.return_value = "linux-x64"
        self.route.return_value = {"runnerOs": "Linux", "runnerArch": "X64", "supervisor": None}
        self.assertEqual({"fixture": True}, self.execute())
        command = self.process.call_args.args[0]
        self.assertEqual(str(self.linker_scripts["linux-x64"]), command[command.index("-I") + 1])
        self.git_bytes.assert_called_once_with(
            self.root, self.producer["commit"], self.linker_scripts["linux-x64"].relative_to(self.root).as_posix(),
            max_bytes=64 * 1024,
        )

    def test_captured_archive_is_part_of_the_immutable_worker_inputs(self):
        def mutate(*_arguments, **_keywords):
            captured = self.destination / "inputs/app-server-archive" / self.archive.name
            captured.write_bytes(captured.read_bytes() + b"changed")
            return subprocess.CompletedProcess([], 0)

        self.process.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.execute()
        self.finalize.assert_not_called()
        self.assertEqual(b"synthetic pinned archive\x00\xff\n", self.archive.read_bytes())

    def test_missing_or_unrelated_archive_rejects_before_preparation_or_process(self):
        with self.assertRaisesRegex(ValueError, "Native binary requires a pinned app-server archive"):
            self.execute(archive=False)
        self.environment.assert_not_called()
        self.prepare.assert_not_called()
        self.process.assert_not_called()

        for instance, route in (
            (
                worker.PhaseInstanceId("runtime", "macos-arm64", "package", "macos-arm64"),
                {"runnerOs": "Linux", "runnerArch": "X64", "supervisor": None},
            ),
            (
                worker.PhaseInstanceId("runtime", "jvm", "binary", "jvm"),
                {"runnerOs": "Linux", "runnerArch": "X64", "supervisor": None},
            ),
        ):
            with self.subTest(instance=instance):
                self.instance = instance
                self.state.prior_ready_plans = {instance: self.ready}
                self.route.return_value = route
                self.host.return_value = "linux-x64"
                with mock.patch("runtime_adapter_phase.route", return_value=route), \
                        self.assertRaisesRegex(
                            ValueError, "App-server archive is only valid for native binary production",
                        ):
                    self.execute()
                self.prepare.assert_not_called()
                self.process.assert_not_called()

    def test_capture_failure_never_starts_process_or_finalizes(self):
        self.capture.side_effect = ValueError("archive capture rejected")
        with self.assertRaisesRegex(ValueError, "archive capture rejected"):
            self.execute()
        self.process.assert_not_called()
        self.finalize.assert_not_called()
        self.assertFalse((self.destination / "shard").exists())
        self.assertEqual(b"synthetic pinned archive\x00\xff\n", self.archive.read_bytes())

    def test_cli_forwards_only_the_explicit_archive_path(self):
        arguments = [
            "execute-runtime-phase",
            "--plan", "plan",
            "--discovery-root", "discovery",
            "--destination", "destination",
            "--product", "runtime",
            "--component", "macos-arm64",
            "--phase", "binary",
            "--target", "macos-arm64",
            "--expected-build-key", self.ready["buildKey"],
        ]
        with mock.patch.object(worker, "execute_runtime_phase") as execute:
            self.assertEqual(0, worker.main([*arguments, "--app-server-archive", str(self.archive)]))
            self.assertEqual(self.archive, execute.call_args.kwargs["app_server_archive"])

        with mock.patch.object(worker, "execute_runtime_phase") as execute:
            self.assertEqual(0, worker.main(arguments))
            self.assertNotIn("app_server_archive", execute.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
