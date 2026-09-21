"""Mocked process/source boundaries, real file/manifest guards; no compilation."""

from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdk_facade_validation_phase as phase
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_file
from products.receipt import write_output_manifest
from products.registry import SDK_FACADE_CONTRACT_COMPONENTS, SDK_FACADE_TARGETS
from products.sdk_facade_validation import FACADE_CONSUMER_TASKS
from products import sdk_facade_source as source
from ci.tests import test_sdk_facade_inputs as fixtures


class FacadeValidationPhaseTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.FacadeInputsTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root, self.request = self.f.root, self.f.request
        self.producer = deepcopy(self.f.producer)
        self.plan = {"schemaVersion": 1, "product": "sdk", "component": "sdk-core",
                     "phase": "validation", "target": "jvm", "buildKey": "sha256:" + "f" * 64, "inputs": {}}
        self.destination = self.root / "build/worker-diagnostics"
        self.environment = {"PATH": "/mock/bin"}
        self.host = self.enterContext(patch.object(phase, "host_classifier", return_value="linux-x64"))
        self.checkout = self.enterContext(patch.object(phase, "_runtime_worker_checkout"))
        self.environment_gate = self.enterContext(patch.object(phase, "_runtime_worker_environment",
            side_effect=lambda root, producer, destination, environ: (dict(environ), root / "gradlew")))
        self.enterContext(patch.object(phase, "_request_inventory", side_effect=lambda path: {path: sha256_file(path)}))
        self.process = self.enterContext(patch.object(phase.subprocess, "run", side_effect=self.run_producer))
        self.source_capture = self.enterContext(patch.object(phase, "capture_facade_validation_sources",
            side_effect=self.capture_source))
        self.observation_active = False
        self.observation_exit_failure = False
        self.observation = self.enterContext(patch.object(phase, "capture_facade_execution_observation",
            side_effect=self.observe))

    @contextmanager
    def observe(self, **kwargs):
        self.assertEqual(self.root, kwargs["repository"])
        self.assertEqual(self.producer, kwargs["producer"])
        self.assertEqual(self.plan["target"], kwargs["target"])
        self.assertEqual(self.environment, kwargs["environment"])
        self.assertEqual(self.destination / "host-observation", kwargs["destination"])
        kwargs["destination"].mkdir()
        (kwargs["destination"] / "observation.json").write_bytes(b"mocked fixed-probe boundary\n")
        self.observation_active = True
        try:
            yield {}
        finally:
            self.observation_active = False
            if self.observation_exit_failure:
                raise ValueError("launcher observation changed on exit")

    def capture_source(self, repository, revision, destination):
        self.assertEqual((self.root, self.producer["commit"]), (repository, revision))
        self.assertNotIn(self.root, destination.parents)
        template = destination / "gradle/release/sdk-facade-consumer-template"
        template.mkdir(parents=True)
        (template / "settings.gradle.kts").write_bytes(b"mock producer bytes\n")
        return {"tree": self.producer["tree"], "files": phase._inventory(destination)}

    def execute(self, **changes):
        return phase.execute(self.plan, **{**dict(producer=self.producer, repository_root=self.root,
            destination=self.destination, facade_request=self.request, environ=self.environment), **changes})

    @property
    def work(self):
        return self.root / f"build/imported-sdk-facade-validation/{self.producer['tree']}/{self.plan['target']}"

    @property
    def stage(self):
        return self.root / f"build/product-stage/sdk/sdk-core/validation/{self.plan['target']}"

    def run_producer(self, command, **kwargs):
        self.assertTrue(self.observation_active)
        self.assertEqual(self.root, kwargs["cwd"])
        self.assertEqual(self.environment, kwargs["env"])
        self.assertIs(False, kwargs["check"])
        self.assertEqual(subprocess.STDOUT, kwargs["stderr"])
        kwargs["stdout"].write(b"retained compiler diagnostics\xff\n")
        target = self.plan["target"]
        self.assertEqual(1, command.count("ciProductPhase"))
        self.assertIn("--offline", command)
        self.assertEqual(".", command[command.index("-p") + 1])
        expected = {
            "codexAgent.product": "sdk", "codexAgent.component": "sdk-core",
            "codexAgent.phase": "validation", "codexAgent.target": target,
            "codexAgent.sdkVersion": self.f.value["sdkVersion"],
            "codexAgent.candidateCommit": self.producer["commit"], "codexAgent.candidateTree": self.producer["tree"],
            "codexAgent.sdkFacadeValidationRequest": str(self.destination / "facade-request.json"),
        }
        self.assertEqual(expected, dict(arg[2:].split("=", 1) for arg in command if arg.startswith("-P")))
        self.assertEqual(self.request.read_bytes(), (self.destination / "facade-request.json").read_bytes())
        for directory in ("inputs", "consumer", "consumer-inputs", "execution/process"):
            (self.work / directory).mkdir(parents=True)
        for name in ("inputs/inputs.json", "inputs/maven-inventory.json", "consumer/build.gradle.kts",
                     "publication-metadata.json", "report.json"):
            (self.work / name).write_bytes(b"mock producer bytes\n")
        template = self.destination / "source/gradle/release/sdk-facade-consumer-template"
        names = {row["relativePath"] for row in phase._inventory(template)}
        names.update({"local.properties", ".codex-consumer-task-outcomes.init.gradle.kts"})
        for name in names:
            for directory in ("consumer", "consumer-inputs"):
                path = self.work / directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((template / name).read_bytes() if (template / name).exists() else b"generated fixture bytes\n")
        for name in phase._FILES:
            (self.work / "execution" / name).write_bytes(b"mock producer bytes\n")
        content = {"schemaVersion": 1, "kind": phase.OUTPUT_KIND, "component": "sdk-core",
            "target": target, "sdkVersion": self.f.value["sdkVersion"],
            "packageOutputsDigest": "sha256:" + "1" * 64, "contractDigest": "sha256:" + "2" * 64,
            "componentDigests": [{"component": SDK_FACADE_CONTRACT_COMPONENTS[target], "sha256": "sha256:" + "3" * 64}],
            "tasks": [FACADE_CONSUMER_TASKS[target]], "result": "passed"}
        output = self.stage / phase.OUTPUT_PATH
        output.parent.mkdir(parents=True)
        output.write_bytes(canonical_json_bytes(content))
        write_output_manifest(self.stage, "sdk", "sdk-core", "validation", target, self.f.value["sdkVersion"],
                              {phase.OUTPUT_KIND: "outputs/validation"})
        return SimpleNamespace(returncode=0)

    def test_all_eleven_actual_routes_preserve_fixed_command_and_external_evidence(self):
        for target in SDK_FACADE_TARGETS:
            with self.subTest(target=target):
                self.plan["target"] = self.f.value["target"] = target
                self.request.write_bytes(canonical_json_bytes(self.f.value))
                topology = phase.route(self.plan)
                self.host.return_value = next(host for host, values in phase._HOSTS.items()
                    if values[1:] == (topology["runnerOs"], topology["runnerArch"]))
                result = self.execute()
                self.assertEqual(self.stage, result["stage"])
                self.assertEqual(self.work, result["work"])
                self.assertEqual(self.work / "execution", result["execution"])
                self.assertEqual(self.work / "consumer-inputs", result["consumerInputs"])
                self.assertEqual(self.request.read_bytes(), result["request"].read_bytes())
                self.assertNotIn("receipt", result)
                self.assertNotIn("shard", result)
                self.assertFalse(self.observation_active)
                self.assertEqual(self.destination / "host-observation", result["hostObservation"])
                record = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
                self.assertEqual(self.producer, record["producer"])
                self.assertEqual(0, record["returnCode"])
                self.assertEqual(b"retained compiler diagnostics\xff\n", (self.destination / "gradle.log").read_bytes())
                shutil.rmtree(self.stage)
                shutil.rmtree(self.work)
                shutil.rmtree(self.destination)

    def test_launcher_observation_exit_failure_rejects_worker_success(self):
        self.observation_exit_failure = True
        with self.assertRaisesRegex(ValueError, "launcher observation changed on exit"):
            self.execute()
        self.assertFalse(self.observation_active)
        self.assertTrue((self.destination / "execution.json").is_file())

    def test_wrong_identity_request_host_or_secret_rejects_before_execution(self):
        for field, value in (("phase", "metadata"), ("target", "desktop"), ("schemaVersion", True)):
            old = self.plan[field]
            self.plan[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.execute()
            self.plan[field] = old
        self.host.return_value = "macos-arm64"
        with self.assertRaisesRegex(ValueError, "actual elected host"):
            self.execute()
        self.host.return_value = "linux-x64"
        with self.assertRaisesRegex(ValueError, "signing-secret"):
            self.execute(environ={"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""})
        self.f.value["target"] = "android"
        self.request.write_bytes(canonical_json_bytes(self.f.value))
        with self.assertRaisesRegex(ValueError, "elected target"):
            self.execute()
        self.process.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_real_source_capture_uses_external_temporary_root_then_exact_retention(self):
        from products.inventory import sha256_bytes
        paths = sorted({*source._FILES, *(f"{source._TEMPLATE}/{name}" for name in source._REQUIRED_TEMPLATE_FILES)})
        blobs = {name: (name + "\n").encode() for name in paths}
        inventory = [{"relativePath": name, "bytes": len(blobs[name]), "sha256": sha256_bytes(blobs[name])} for name in paths]
        self.source_capture.side_effect = source.capture_facade_validation_sources
        with patch.object(source, "_immutable_tree", return_value=self.producer["tree"]), \
             patch.object(source, "tree_entries", return_value=[(name, "100644\tblob\t" + "a" * 40 + "\t" + name) for name in paths]), \
             patch.object(source, "git_file_inventory", return_value=inventory), \
             patch.object(source, "git_regular_blob_bytes", side_effect=lambda repo, tree, name, **kw: blobs[name]):
            result = self.execute()
        self.assertEqual(inventory, phase._inventory(result["source"]))
        self.assertEqual(self.destination / "source", result["source"])
        self.assertNotIn(self.root, self.source_capture.call_args.args[2].parents)

    def test_stale_overlap_symlink_outputs_reject_without_removing_anything(self):
        for path in (self.stage, self.work, self.destination):
            with self.subTest(path=path):
                path.mkdir(parents=True)
                marker = path / "existing.bin"
                marker.write_bytes(b"keep")
                with self.assertRaisesRegex(ValueError, "fresh"):
                    self.execute()
                self.assertEqual(b"keep", marker.read_bytes())
                shutil.rmtree(path)
        with self.assertRaises(ValueError):
            self.execute(destination=self.f.f.package / "diagnostics")
        alias = self.root / "alias"
        alias.symlink_to(self.root / "build", target_is_directory=True)
        with self.assertRaises(ValueError):
            self.execute(destination=alias / "diagnostics")
        self.process.assert_not_called()

    def test_failed_or_unlaunched_process_preserves_diagnostics_without_stage_success(self):
        for failure in (SimpleNamespace(returncode=9), OSError("mock launch failure")):
            with self.subTest(failure=failure):
                self.process.side_effect = failure if isinstance(failure, OSError) else None
                self.process.return_value = failure
                with self.assertRaises((OSError, ValueError)):
                    self.execute()
                record = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
                self.assertEqual(None if isinstance(failure, OSError) else 9, record["returnCode"])
                self.assertEqual(self.request.read_bytes(), (self.destination / "facade-request.json").read_bytes())
                self.assertFalse(self.stage.exists())
                shutil.rmtree(self.destination)

    def test_original_or_retained_request_mutation_and_late_checkout_failure_reject(self):
        original_bytes = self.request.read_bytes()
        for mutate in (
            lambda: self.request.write_bytes(b"changed\n"),
            lambda: (self.destination / "facade-request.json").write_bytes(b"changed\n"),
            lambda: (self.destination / "python-bytecode").mkdir(),
            lambda: (self.destination / "source/gradle/release/sdk-facade-consumer-template/settings.gradle.kts").write_bytes(b"changed\n"),
            lambda: setattr(self.checkout, "side_effect", ValueError("late checkout changed")),
        ):
            with self.subTest(mutation=mutate):
                def run(*args, **kwargs):
                    result = self.run_producer(*args, **kwargs)
                    mutate()
                    return result
                self.process.side_effect = run
                with self.assertRaises(ValueError):
                    self.execute()
                self.assertTrue((self.destination / "execution.json").is_file())
                self.checkout.side_effect = None
                self.request.write_bytes(original_bytes)
                for path in (self.destination, self.stage, self.work):
                    shutil.rmtree(path)

    def test_success_exit_does_not_replace_missing_or_ambiguous_evidence(self):
        def run(*args, **kwargs):
            result = self.run_producer(*args, **kwargs)
            (self.work / "execution/process/stdout.bin").unlink()
            return result
        self.process.side_effect = run
        with self.assertRaisesRegex(ValueError, "raw execution evidence"):
            self.execute()

    def test_empty_process_streams_gradle_log_and_consumer_cache_are_retained(self):
        def run(*args, **kwargs):
            result = self.run_producer(*args, **kwargs)
            kwargs["stdout"].seek(0)
            kwargs["stdout"].truncate()
            for name in ("stdout.bin", "stderr.bin"):
                (self.work / "execution/process" / name).write_bytes(b"")
            cache = self.work / "consumer/.gradle/empty-cache-marker"
            cache.parent.mkdir()
            cache.write_bytes(b"")
            return result
        self.process.side_effect = run
        result = self.execute()
        empty = {row["relativePath"] for row in result["workInventory"] if row["bytes"] == 0}
        self.assertEqual({"execution/process/stdout.bin", "execution/process/stderr.bin",
                          "consumer/.gradle/empty-cache-marker"}, empty)
        self.assertEqual(b"", (result["diagnostics"] / "gradle.log").read_bytes())
