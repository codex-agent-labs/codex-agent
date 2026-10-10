"""Fixed probes mocked; real capture/lifetime checks, no hosted/compiler proof."""

from copy import deepcopy
from contextlib import nullcontext
from pathlib import Path, PureWindowsPath
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from products import sdk_facade_execution_observation as observation
from products.inventory import load_canonical_json_bytes
from products.registry import SDK_FACADE_TARGETS
from sdk_phase import route
from native_wrappers import HOSTS
import product_reuse


class FacadeExecutionObservationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.output = self.root / "observed"
        self.java_home = self.root / "jdk"
        (self.java_home / "bin").mkdir(parents=True)
        for name in ("java", "java.exe"):
            (self.java_home / "bin" / name).write_bytes(b"fixture launcher, never executed")
        self.producer = {"repository": "fixture/repository", "commit": "a" * 40, "tree": "b" * 40,
            "event": "pull_request", "workflowPath": ".github/workflows/ci.yml",
            "runId": 1, "runAttempt": 2, "pullRequest": 3}
        self.environment = {"JAVA_HOME": str(self.java_home), "PATH": "/fixture/bin"}
        self.sources = {"gradlew": b"fixture posix wrapper", "gradlew.bat": b"fixture Windows wrapper",
            "gradle/wrapper/gradle-wrapper.jar": b"fixture jar", observation.WRAPPER_PROPERTIES:
            b"distributionUrl=https\\://services.gradle.org/distributions/gradle-9.1.0-bin.zip\ndistributionSha256Sum=" + b"a" * 64 + b"\n"}
        for name, raw in self.sources.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.enterContext(patch.object(observation, "_authority", side_effect=self.authority))
        self.enterContext(patch.object(observation, "git_regular_blob_bytes", side_effect=lambda root, commit, name, **kw: self.sources[name]))
        self.enterContext(patch.object(observation, "run_git", side_effect=lambda root, command, value:
            self.producer["tree" if value.endswith("{tree}") else "commit"] + "\n"))
        self.system = self.enterContext(patch.object(observation.platform, "system", return_value="Linux"))
        self.machine = self.enterContext(patch.object(observation.platform, "machine", return_value="x86_64"))
        self.process = self.enterContext(patch.object(observation.subprocess, "run", side_effect=self.probe))
        self.bootstrap = self.enterContext(patch.object(observation, "require_preprovisioned_gradle"))
        self.gradle_version = "9.1.0"
        self.java_arch = "amd64"

    def authority(self, root, commit, name):
        self.assertEqual((self.root, self.producer["commit"]), (root, commit))
        if (root / name).read_bytes() != self.sources[name]:
            raise ValueError("source differs from immutable Git fixture")
        return self.sources[name]

    def probe(self, command, **kwargs):
        self.assertEqual(self.root, kwargs["cwd"])
        self.assertEqual(self.environment, kwargs["env"])
        self.assertEqual(observation.subprocess.DEVNULL, kwargs["stdin"])
        if command[-1] == "-version":
            self.assertEqual(["-XshowSettings:properties", "-version"], command[1:])
            raw = f"Property settings:\n    os.arch = {self.java_arch}\n    java.runtime.version = 17.0.12+7\n".encode()
        else:
            self.assertEqual(["--offline", "--no-daemon", "--version"], command[-3:])
            self.assertNotIn("ciProductPhase", command)
            raw = f"\nGradle {self.gradle_version}\n\n".encode()
        return SimpleNamespace(returncode=0, stdout=raw)

    def call(self, **changes):
        return observation.capture_facade_execution_observation(**{**dict(repository=self.root, producer=self.producer,
            target="jvm", environment=self.environment, destination=self.output), **changes})

    def test_fixed_probes_retain_exact_raw_and_do_not_claim_compiler_admission(self):
        with self.call() as value:
            self.assertEqual("sdk-facade-launcher-observation", value["kind"])
            self.assertEqual("linux-x64", value["host"]["classifier"])
            self.assertEqual("9.1.0", value["gradle"]["version"])
            self.assertEqual(self.producer, value["producer"])
            self.assertEqual(value, load_canonical_json_bytes((self.output / "observation.json").read_bytes()))
            self.assertEqual({"observation.json", "java-execution.json", "gradle-execution.json"},
                             {path.name for path in self.output.iterdir()})
            self.assertNotIn("compiler", value)
        self.assertEqual(2, self.process.call_count)
        self.bootstrap.assert_called_once_with(self.sources[observation.WRAPPER_PROPERTIES], self.environment)

    def test_missing_preprovisioned_distribution_blocks_every_probe(self):
        self.bootstrap.side_effect = ValueError("distribution is not provisioned")
        with self.assertRaisesRegex(ValueError, "not provisioned"), self.call():
            self.fail("must not yield")
        self.process.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_all_eleven_routes_use_actual_platform_not_caller_runner_labels(self):
        for index, target in enumerate(SDK_FACADE_TARGETS):
            topology = route({"product": "sdk", "component": "sdk-core", "phase": "validation", "target": target})
            classifier = next(name for name, value in HOSTS.items() if value[2:4] == (topology["runnerOs"], topology["runnerArch"]))
            system, arches, *_ = HOSTS[classifier]
            self.system.return_value = system
            self.machine.return_value = self.java_arch = sorted(arches)[0]
            # POSIX fixture files cannot be Windows absolute paths. Only this
            # filesystem-to-launcher boundary is adapted; the real shared
            # launcher still validates and constructs genuine Windows argv.
            shared_command = product_reuse._runtime_worker_command
            launcher = patch.object(product_reuse, "_runtime_worker_command", side_effect=
                lambda wrapper, properties, environment, **kwargs: shared_command(
                    r"C:\checkout\gradlew.bat", properties, {**environment, "JAVA_HOME": r"C:\jdk"}, **kwargs)) \
                if system == "Windows" else nullcontext()
            with self.subTest(target=target), launcher, self.call(target=target, destination=self.root / f"observed-{index}") as value:
                self.assertEqual(classifier, value["host"]["classifier"])
                if system == "Windows":
                    self.assertEqual("java.exe", PureWindowsPath(self.process.call_args.args[0][0]).name)
                    self.assertIn("-Dorg.gradle.appname=gradlew", self.process.call_args.args[0])

    def test_wrong_host_missing_java_home_options_and_existing_output_fail_before_probe(self):
        for changes in ({"target": "macos-arm64"}, {"environment": {}},
                        {"environment": {**self.environment, "JAVA_OPTS": "-agentlib:bad"}}):
            with self.subTest(changes=changes), self.assertRaises(ValueError), self.call(**changes):
                pass
        self.output.mkdir()
        (self.output / "keep").write_bytes(b"keep")
        with self.assertRaises(ValueError), self.call():
            pass
        self.assertEqual(b"keep", (self.output / "keep").read_bytes())
        self.process.assert_not_called()

    def test_wrong_gradle_version_and_java_arch_retain_raw_but_no_success(self):
        for index, mismatch in enumerate(("gradle", "java")):
            self.gradle_version, self.java_arch = ("8.0", "amd64") if mismatch == "gradle" else ("9.1.0", "aarch64")
            destination = self.root / f"failed-{index}"
            with self.subTest(mismatch=mismatch), self.assertRaises(ValueError), self.call(destination=destination):
                pass
            self.assertTrue((destination / "java-execution.json").is_file())
            self.assertFalse((destination / "observation.json").exists())

    def test_failed_and_unlaunched_probes_preserve_diagnostics(self):
        for index, failure in enumerate((SimpleNamespace(returncode=7, stdout=b"failure\xff"), OSError("launch failed"))):
            destination = self.root / f"failed-{index}"
            self.process.side_effect = failure if isinstance(failure, OSError) else None
            self.process.return_value = failure
            with self.subTest(failure=failure), self.assertRaises((OSError, ValueError)), self.call(destination=destination):
                pass
            self.assertFalse((destination / "observation.json").exists())
            self.assertTrue((destination / ("launch-failure.json" if isinstance(failure, OSError) else "java-execution.json")).exists())

    def test_launcher_source_environment_and_retained_record_mutations_reject_at_exit(self):
        java = self.java_home / "bin/java"
        mutations = [lambda: java.write_bytes(b"changed"),
            lambda: (self.root / "gradlew").write_bytes(b"changed"),
            lambda: self.environment.update(JAVA_HOME="/other/java"),
            lambda: (self.output / "observation.json").write_bytes(b"changed")]
        for index, mutate in enumerate(mutations):
            java.write_bytes(b"fixture launcher, never executed")
            (self.root / "gradlew").write_bytes(self.sources["gradlew"])
            self.environment["JAVA_HOME"] = str(self.java_home)
            self.output = self.root / f"mutation-{index}"
            with self.subTest(index=index), self.assertRaises(ValueError), self.call():
                mutate()

    def test_mutable_producer_and_returned_observation_are_not_authority(self):
        before = deepcopy(self.producer)
        with self.assertRaises(ValueError), self.call():
            self.producer["runId"] += 1
        self.producer = before
        with self.assertRaises(ValueError), self.call(destination=self.root / "second") as value:
            value["host"]["classifier"] = "macos-arm64"

    def test_read_only_replay_binds_raw_source_and_explicit_original_context(self):
        with self.call():
            pass
        self.process.reset_mock()
        arguments = dict(repository=self.root, producer=self.producer, target="jvm",
            original_repository_root=str(self.root), original_java_executable=str(self.java_home / "bin/java"))
        observation.verify_facade_execution_observation(self.output, **arguments)
        self.process.assert_not_called()
        with self.assertRaisesRegex(ValueError, "wrapper differs"):
            observation.verify_facade_execution_observation(self.output, **{**arguments, "original_repository_root": "/other/checkout"})
        with self.assertRaisesRegex(ValueError, "Java differs"):
            observation.verify_facade_execution_observation(self.output, **{**arguments, "original_java_executable": "/other/bin/java"})
        with self.assertRaisesRegex(ValueError, "repository path platform differs"):
            observation.verify_facade_execution_observation(self.output, **{**arguments, "original_repository_root": r"C:\checkout"})
        record_path = self.output / "observation.json"
        record_bytes = record_path.read_bytes()
        record = load_canonical_json_bytes(record_bytes)
        record["java"]["executable"] = r"C:\jdk\bin\java.exe"
        record_path.write_bytes(observation.canonical_json_bytes(record))
        with self.assertRaisesRegex(ValueError, "Java path platform differs"):
            observation.verify_facade_execution_observation(self.output, **arguments)
        record_path.write_bytes(record_bytes)
        path = self.output / "java-execution.json"
        original_bytes = path.read_bytes()
        value = load_canonical_json_bytes(original_bytes)
        value["command"][1] = "-other"
        path.write_bytes(observation.canonical_json_bytes(value))
        with self.assertRaisesRegex(ValueError, "probe command differs"):
            observation.verify_facade_execution_observation(self.output, **arguments)
        path.write_bytes(original_bytes)
        self.sources["gradlew"] += b"changed"
        with self.assertRaisesRegex(ValueError, "launcher bytes differ"):
            observation.verify_facade_execution_observation(self.output, **arguments)

    def test_windows_original_replay_uses_real_shared_launcher_and_lexical_paths(self):
        # Manufacture retained probe bytes explicitly; this is cross-platform
        # replay coverage, not a Windows process or observed-host acceptance.
        with self.call():
            pass
        record_path = self.output / "observation.json"
        record = load_canonical_json_bytes(record_path.read_bytes())
        original_root, java = r"C:\original\checkout", r"C:\original\jdk\bin\java.exe"
        wrapper = original_root + r"\gradlew.bat"
        record.update(target="windows-x64", host={"system": "Windows", "machine": "AMD64", "classifier": "windows-x64"})
        record["java"]["executable"] = java
        record["gradle"]["wrapper"] = wrapper
        names = ("gradlew.bat", "gradle/wrapper/gradle-wrapper.jar", observation.WRAPPER_PROPERTIES)
        record["gradle"]["sourceFiles"] = [{"relativePath": name, "bytes": len(self.sources[name]),
            "sha256": observation.sha256_bytes(self.sources[name])} for name in sorted(names)]
        prefix = product_reuse._runtime_worker_command(wrapper, {}, {"JAVA_HOME": r"C:\original\jdk"},
            build_directory=".", platform_name="nt")
        prefix = prefix[:prefix.index("--offline")]
        for name, command in (("java-execution.json", [java, "-XshowSettings:properties", "-version"]),
                              ("gradle-execution.json", prefix + ["--offline", "--no-daemon", "--version"])):
            path = self.output / name
            raw = load_canonical_json_bytes(path.read_bytes())
            raw["command"] = command
            path.write_bytes(observation.canonical_json_bytes(raw))
        record["executions"] = [row for row in observation._inventory(self.output) if row["relativePath"] != "observation.json"]
        record_path.write_bytes(observation.canonical_json_bytes(record))
        self.process.reset_mock()
        arguments = dict(repository=self.root, producer=self.producer, target="windows-x64",
                         original_repository_root=original_root, original_java_executable=java)
        observation.verify_facade_execution_observation(self.output, **arguments)
        self.process.assert_not_called()
        with self.assertRaisesRegex(ValueError, "repository path platform differs"):
            observation.verify_facade_execution_observation(self.output, **{**arguments, "original_repository_root": "/posix/root"})
        record["java"]["executable"] = "/posix/jdk/bin/java.exe"
        record_path.write_bytes(observation.canonical_json_bytes(record))
        with self.assertRaisesRegex(ValueError, "Java path platform differs"):
            observation.verify_facade_execution_observation(self.output, **arguments)


if __name__ == "__main__":
    unittest.main()
