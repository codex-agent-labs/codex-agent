"""Exercise the fixed Runtime worker boundary with synthetic process bytes."""

from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from ci.products.inventory import load_canonical_json, regular_file_inventory
from ci.products.receipt import write_output_manifest
from ci.tests import test_runtime_resumed_phase as fixture
from ci.tests.test_runtime_evidence import write_zip


adapter = fixture.adapter
JVM = fixture.JVM


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class RuntimePhaseExecutionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        owner = fixture.resume_fixture.fixture.ProductReuseAdapterTest
        create_repository = owner.contract_repository

        def repository_with_wrapper(helper):
            repository, _, _ = create_repository(helper)
            wrapper = repository / "gradlew"
            wrapper.write_bytes(b"#!/bin/sh\nexit 99\n")
            wrapper.chmod(0o755)
            (repository / "gradlew.bat").write_bytes(b"@exit /b 99\r\n")
            launcher = repository / "gradle/wrapper/gradle-wrapper.jar"
            launcher.parent.mkdir(parents=True)
            launcher.write_bytes(b"synthetic tracked Gradle launcher\n")
            (repository / ".gitignore").write_text(
                "runtime/ignored-source.pyc\n"
                "/sitecustomize.py\n"
                "/sitecustomize/\n",
                encoding="utf-8",
            )
            subprocess.run((
                "git",
                "add",
                "gradlew",
                "gradlew.bat",
                "gradle/wrapper/gradle-wrapper.jar",
                ".gitignore",
            ),
                           cwd=repository, check=True)
            subprocess.run(("git", "commit", "-qm", "synthetic tracked Gradle wrapper"),
                           cwd=repository, check=True)
            commit = subprocess.run(
                ("git", "rev-parse", "HEAD"), cwd=repository, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            tree = subprocess.run(
                ("git", "rev-parse", "HEAD^{tree}"), cwd=repository, check=True,
                capture_output=True, text=True,
            ).stdout.strip()
            return repository, commit, tree

        with mock.patch.object(owner, "contract_repository", repository_with_wrapper):
            fixture.RuntimeResumedPhaseTest.setUpClass.__func__(cls)

    control_seams = classmethod(fixture.RuntimeResumedPhaseTest.control_seams.__func__)
    tearDown = fixture.RuntimeResumedPhaseTest.tearDown
    resume = fixture.RuntimeResumedPhaseTest.resume

    def setUp(self):
        fixture.RuntimeResumedPhaseTest.setUp(self)
        self.stage = (
            self.repository
            / "codex-agent-runtime-desktop/build/product-stage/runtime/jvm/binary"
        )
        self.addCleanup(shutil.rmtree, self.stage, ignore_errors=True)

    def execution_environment(self):
        return {
            **self.environment,
            "GRADLE_USER_HOME": str(self.scratch / "gradle-user-home"),
            "JAVA_HOME": str(self.scratch / "synthetic-java-home"),
        }

    def write_stage(self):
        jar = self.stage / "outputs/adapter/codex-agent-runtime-desktop-jvm-0.2.0.jar"
        jar.parent.mkdir(parents=True)
        write_zip(jar, {
            "META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\n\n",
            "fixture/SyntheticRuntime.class": b"synthetic process output\n",
        })
        runner = self.stage / "outputs/validation-runner/runtime-jvm-runner.jar"
        runner.parent.mkdir(parents=True)
        write_zip(runner, {
            "META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\n\n",
            "fixture/SyntheticRunner.class": b"synthetic runner output\n",
        })
        write_output_manifest(
            self.stage,
            "runtime",
            "jvm",
            "binary",
            "jvm",
            "0.2.0",
            {
                "adapter": "outputs/adapter",
                "validation-runner": "outputs/validation-runner",
            },
        )

    @contextmanager
    def process(
        self,
        destination: Path,
        *,
        return_code: int,
        output: bytes,
        during=None,
    ):
        real_run = subprocess.run
        calls = []

        def run(command, *arguments, **keywords):
            if "ciProductPhase" not in command:
                return real_run(command, *arguments, **keywords)
            calls.append(command)
            properties = load_canonical_json(destination / "inputs/gradle-properties.json")
            fixed = [
                str(self.repository / ("gradlew.bat" if os.name == "nt" else "gradlew")),
                "--offline",
                "--no-daemon",
                "--configuration-cache",
                "--configuration-cache-problems=fail",
                "-p",
                "runtime",
                "ciProductPhase",
                *(f"-P{key}={value}" for key, value in sorted(properties.items())),
            ]
            expected = (
                [
                    adapter.ntpath.join(
                        keywords["env"]["JAVA_HOME"], "bin", "java.exe",
                    ),
                    "-Xmx64m",
                    "-Xms64m",
                    "-Dorg.gradle.appname=gradlew",
                    "-jar",
                    adapter.ntpath.join(
                        adapter.ntpath.dirname(str(self.repository / "gradlew.bat")),
                        "gradle",
                        "wrapper",
                        "gradle-wrapper.jar",
                    ),
                    *fixed[1:],
                ]
                if os.name == "nt"
                else fixed
            )
            self.assertEqual(expected, command)
            self.assertEqual(self.repository, keywords["cwd"])
            self.assertFalse(keywords["check"])
            self.assertIs(subprocess.STDOUT, keywords["stderr"])
            self.assertEqual("true", keywords["env"]["npm_config_offline"])
            self.assertEqual(
                str(destination / "python-bytecode"),
                keywords["env"]["PYTHONPYCACHEPREFIX"],
            )
            keywords["stdout"].write(output)
            keywords["stdout"].flush()
            if return_code == 0:
                self.write_stage()
            if during is not None:
                during(keywords["env"])
            return subprocess.CompletedProcess(command, return_code)

        with mock.patch("native_wrappers.host_classifier", return_value="linux-x64"), \
                mock.patch.object(adapter.subprocess, "run", side_effect=run):
            yield calls

    @contextmanager
    def reject_worker_process(self, *, host: str):
        real_run = subprocess.run
        worker_calls = []

        def run(command, *arguments, **keywords):
            if "ciProductPhase" in command:
                worker_calls.append(command)
                raise AssertionError("Runtime worker process unexpectedly started")
            return real_run(command, *arguments, **keywords)

        with mock.patch("native_wrappers.host_classifier", return_value=host), \
                mock.patch.object(adapter.subprocess, "run", side_effect=run):
            yield worker_calls

    def execute(self, resumed: Path, destination: Path, *, build_key: str | None = None):
        ready = load_canonical_json(resumed / "phase-plans/runtime-jvm-binary-jvm.json")
        with self.control_seams():
            result = adapter.execute_runtime_phase(
                self.plan_path,
                resumed,
                None,
                JVM,
                destination,
                expected_build_key=ready["buildKey"] if build_key is None else build_key,
                repository_root=self.repository,
                environ=self.execution_environment(),
            )
        return ready, result

    def test_success_finalizes_real_shard_only_after_observed_process_success(self):
        resumed = self.resume()
        original = regular_file_inventory(resumed)
        destination = self.scratch / "successful-execution"
        output = b"synthetic Gradle stdout\x00\xff\r\n"

        with self.process(destination, return_code=0, output=output) as calls:
            ready, result = self.execute(resumed, destination)

        self.assertEqual(1, len(calls))
        self.assertEqual(output, (destination / "gradle.log").read_bytes())
        execution = load_canonical_json(destination / "execution.json")
        self.assertEqual(
            {
                "schemaVersion",
                "producer",
                "buildKey",
                "command",
                "host",
                "observations",
                "returnCode",
                "elapsedNs",
            },
            set(execution),
        )
        self.assertEqual(self.producer, execution["producer"])
        self.assertEqual(ready["buildKey"], execution["buildKey"])
        self.assertEqual("linux-x64", execution["host"])
        self.assertEqual({}, execution["observations"])
        self.assertEqual(0, execution["returnCode"])
        self.assertIs(type(execution["elapsedNs"]), int)
        self.assertGreaterEqual(execution["elapsedNs"], 0)
        verified = adapter.verify_phase_shard(destination / "shard", JVM)
        self.assertEqual(result["receiptBytes"], verified["receiptBytes"])
        self.assertEqual(self.producer, verified["receipt"]["producer"])
        self.assertEqual(ready["buildKey"], verified["receipt"]["buildKey"])
        self.assertEqual(original, regular_file_inventory(resumed))

    def test_process_failure_keeps_diagnostics_and_never_mints_a_shard(self):
        resumed = self.resume()
        original = regular_file_inventory(resumed)
        destination = self.scratch / "failed-execution"
        output = b"synthetic failure bytes\xff\x00\n"

        with self.process(destination, return_code=7, output=output) as calls:
            with self.assertRaisesRegex(ValueError, "failed with exit code 7"):
                self.execute(resumed, destination)

        self.assertEqual(1, len(calls))
        self.assertEqual(output, (destination / "gradle.log").read_bytes())
        self.assertEqual(7, load_canonical_json(destination / "execution.json")["returnCode"])
        self.assertTrue((destination / "inputs/gradle-properties.json").is_file())
        self.assertFalse((destination / "shard").exists())
        self.assertEqual(original, regular_file_inventory(resumed))

    def test_success_cannot_mutate_source_private_inputs_or_bytecode_namespace(self):
        resumed = self.resume()
        original = regular_file_inventory(resumed)
        wrapper = self.repository / ("gradlew.bat" if os.name == "nt" else "gradlew")
        wrapper_bytes = wrapper.read_bytes()

        def source(_environment):
            wrapper.write_bytes(wrapper_bytes + b"changed during execution")

        def inputs(_environment):
            path = self.scratch / "changed-inputs/inputs/gradle-properties.json"
            path.write_bytes(path.read_bytes() + b" ")

        def bytecode(environment):
            path = Path(environment["PYTHONPYCACHEPREFIX"])
            path.mkdir()
            (path / "unexpected.pyc").write_bytes(b"synthetic bytecode")

        for name, change, error in (
            ("source", source, "unchanged tracked checkout"),
            ("inputs", inputs, "inputs changed"),
            # The checkout guard also detects the injected orphan .pyc when
            # the fixture's worker directory is outside an excluded build path.
            ("bytecode", bytecode, "untracked source|bytecode namespace"),
        ):
            destination = self.scratch / f"changed-{name}"
            try:
                with self.process(
                    destination,
                    return_code=0,
                    output=f"synthetic {name}\n".encode(),
                    during=change,
                ):
                    with self.assertRaisesRegex(ValueError, error):
                        self.execute(resumed, destination)
            finally:
                wrapper.write_bytes(wrapper_bytes)
            self.assertTrue((destination / "execution.json").is_file())
            self.assertFalse((destination / "shard").exists())
            shutil.rmtree(self.stage, ignore_errors=True)
        self.assertEqual(original, regular_file_inventory(resumed))

    def test_host_key_source_and_stale_stage_fail_before_process_or_output(self):
        resumed = self.resume()
        original = regular_file_inventory(resumed)
        ready = load_canonical_json(resumed / "phase-plans/runtime-jvm-binary-jvm.json")
        cases = []

        cases.append(("key", "sha256:" + "0" * 64, None, "expected elected build key"))
        cases.append(("host", ready["buildKey"], "macos-arm64", "actual host"))
        for name, build_key, host, error in cases:
            destination = self.scratch / f"rejected-{name}"
            with self.control_seams(), self.reject_worker_process(
                    host=host or "linux-x64") as worker_calls:
                with self.assertRaisesRegex(ValueError, error):
                    adapter.execute_runtime_phase(
                        self.plan_path,
                        resumed,
                        None,
                        JVM,
                        destination,
                        expected_build_key=build_key,
                        repository_root=self.repository,
                        environ=self.execution_environment(),
                    )
            self.assertEqual([], worker_calls)
            self.assertFalse(destination.exists())

        for number, relative in enumerate((
            "runtime/ignored-source.pyc",
            "sitecustomize.py",
            "sitecustomize/__init__.py",
        )):
            ignored = self.repository / relative
            ignored.parent.mkdir(parents=True, exist_ok=True)
            ignored.write_bytes(b"ignored source residue")
            try:
                destination = self.scratch / f"rejected-ignored-{number}"
                with self.control_seams(), self.reject_worker_process(
                        host="linux-x64") as worker_calls:
                    with self.assertRaisesRegex(ValueError, "untracked source"):
                        adapter.execute_runtime_phase(
                            self.plan_path,
                            resumed,
                            None,
                            JVM,
                            destination,
                            expected_build_key=ready["buildKey"],
                            repository_root=self.repository,
                            environ=self.execution_environment(),
                        )
                self.assertEqual([], worker_calls)
                self.assertFalse(destination.exists())
                self.assertEqual(b"ignored source residue", ignored.read_bytes())
            finally:
                ignored.unlink()

        wrapper = self.repository / ("gradlew.bat" if os.name == "nt" else "gradlew")
        wrapper_bytes = wrapper.read_bytes()
        try:
            wrapper.write_bytes(wrapper_bytes + b"dirty")
            destination = self.scratch / "rejected-dirty"
            with self.control_seams(), self.reject_worker_process(
                    host="linux-x64") as worker_calls:
                with self.assertRaisesRegex(ValueError, "unchanged tracked checkout"):
                    adapter.execute_runtime_phase(
                        self.plan_path,
                        resumed,
                        None,
                        JVM,
                        destination,
                        expected_build_key=ready["buildKey"],
                        repository_root=self.repository,
                        environ=self.execution_environment(),
                    )
            self.assertEqual([], worker_calls)
            self.assertFalse(destination.exists())
        finally:
            wrapper.write_bytes(wrapper_bytes)

        self.stage.mkdir(parents=True)
        sentinel = self.stage / "sentinel"
        sentinel.write_bytes(b"preserve prior output")
        destination = self.scratch / "rejected-stale"
        with self.control_seams(), self.reject_worker_process(
                host="linux-x64") as worker_calls:
            with self.assertRaisesRegex(ValueError, "pre-existing output stage"):
                adapter.execute_runtime_phase(
                    self.plan_path,
                    resumed,
                    None,
                    JVM,
                    destination,
                    expected_build_key=ready["buildKey"],
                    repository_root=self.repository,
                    environ=self.execution_environment(),
                )
        self.assertEqual([], worker_calls)
        self.assertEqual(b"preserve prior output", sentinel.read_bytes())
        self.assertFalse(destination.exists())
        self.assertEqual(original, regular_file_inventory(resumed))


class ProductWorkerCheckoutTest(unittest.TestCase):
    def test_shared_command_only_selects_fixed_runtime_or_sdk_build(self):
        with mock.patch.object(adapter.os, "name", "posix"):
            for directory in ("runtime", "."):
                command = adapter._runtime_worker_command(Path("/trusted/gradlew"), {}, {}, build_directory=directory)
                self.assertEqual(directory, command[command.index("-p") + 1])
                self.assertIn("--offline", command)
            with self.assertRaisesRegex(ValueError, "fixed Runtime or root SDK"):
                adapter._runtime_worker_command(Path("/trusted/gradlew"), {}, {}, build_directory="/untrusted")

    def test_shared_guard_rejects_untracked_sdk_sources_without_rejecting_user_notes(self):
        with tempfile.TemporaryDirectory(prefix="product-checkout-fixture-") as temporary:
            root = Path(temporary)
            def git(*args):
                return subprocess.run(["git", *args], cwd=root, check=True,
                                      capture_output=True, text=True).stdout.strip()
            git("init", "-q")
            git("config", "user.email", "fixture@example.invalid")
            git("config", "user.name", "Fixture")
            (root / "tracked.txt").write_text("baseline\n")
            git("add", "tracked.txt")
            git("commit", "-qm", "fixture")
            producer = {"commit": git("rev-parse", "HEAD"), "tree": git("rev-parse", "HEAD^{tree}")}
            (root / "DRAFT_TODO.md").write_text("user note\n")
            adapter._runtime_worker_checkout(root, producer)
            for path in (
                "codex-agent-core/src/commonMain/Injected.kt",
                "codex-agent-sdk/src/commonMain/Injected.kt",
                "codex-agent-bindings/rust/src/injected.rs",
                "codex-agent-runtime-ios/native/injected.c",
                "codex-agent-runtime-android/src/main/Injected.kt",
            ):
                source = root / path
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(b"untracked source")
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, "untracked source"):
                    adapter._runtime_worker_checkout(root, producer)
                self.assertEqual(b"untracked source", source.read_bytes())
                source.unlink()
            self.assertEqual("user note\n", (root / "DRAFT_TODO.md").read_text())


if __name__ == "__main__":
    unittest.main()
