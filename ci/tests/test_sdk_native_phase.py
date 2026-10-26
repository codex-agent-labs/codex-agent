"""Native package worker controls: simulated process, real original inventories.

No fixture claims package semantics, native compilation, source authentication
or hosted success. The controller still owns full private-candidate admission.
"""

from contextlib import ExitStack
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import product_reuse  # noqa: E402
import sdk_native_phase as worker  # noqa: E402
from products.inventory import load_canonical_json_bytes, regular_file_inventory, sha256_bytes  # noqa: E402
from products.receipt import write_output_manifest  # noqa: E402
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS  # noqa: E402
from products.restore import PHASE_PLAN_KEYS  # noqa: E402
from ci.tests.product_chain_support import write_receipt  # noqa: E402


class SdkNativePhaseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-native-package-worker-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.counter = 0
        self.fixture()

    def fixture(self, language="python"):
        self.counter += 1
        self.root = self.base / str(self.counter)
        self.root.mkdir()
        version = self.root / "gradle/release/versions/sdk.txt"
        version.parent.mkdir(parents=True)
        version.write_bytes(b"0.3.0\n")
        self.destination = self.root / "build/worker"
        self.stage = self.root / f"codex-agent-sdk/build/product-stage/sdk/{language}/package"
        self.producer = {"repository": "fixture/repository", "workflowPath": None,
            "commit": "a" * 40, "tree": "b" * 40, "event": "local",
            "runId": None, "runAttempt": None, "pullRequest": None}
        self.sources = self.root / "prepared/sources"
        for source_language in NATIVE_BINDINGS:
            directory = self.sources / source_language
            directory.mkdir(parents=True)
            (directory / "original-source").write_bytes(b"caller-authenticated source fixture\n")
        self.sdks = self.root / "prepared/sdks"
        self.sdks.mkdir()
        (self.sdks / "synthetic-staging").write_bytes(b"caller-authenticated staging fixture\n")
        self.runtime = self.root / "runtime-originals"
        self.records = {}
        for target in NATIVE_TARGETS:
            for phase in ("package", "validation"):
                identity = ("runtime", target, phase, target)
                version = "0.2.1" if phase == "package" else "0.2.3"
                stage = self.root / "originals" / "-".join(identity)
                (stage / "outputs").mkdir(parents=True)
                (stage / "outputs/original").write_bytes(("synthetic " + "-".join(identity)).encode())
                manifest = write_output_manifest(stage, *identity, version, {"evidence": "outputs"})
                path = stage.parent / f"{stage.name}.json"
                receipt = write_receipt(path, product="runtime", component=target, phase=phase,
                    target=target, outputs=manifest["outputs"], upstream=[], version=version,
                    version_identity=version, context={"producer": self.producer})
                self.records[identity] = {"stage": stage, "receiptPath": path, "receipt": receipt}
                shutil.copytree(stage, self.runtime / target / phase)
        elected = write_receipt(self.root / "elected.json", product="sdk", component=language,
            phase="package", target="desktop", outputs=manifest["outputs"], upstream=[], version="0.3.0",
            version_identity="0.3.0", context={"producer": self.producer})
        self.plan = {name: elected[name] for name in PHASE_PLAN_KEYS}
        self.request = self.root / "authenticated-request.json"
        self.request.write_bytes(b"synthetic caller-verified S858 boundary\n")
        self.request_input = self.root / "authenticated-input"
        self.request_input.write_bytes(b"original caller-verified K/R bytes\n")
        self.binary = None
        if language == "csharp":
            self.binary = self.root / "originals/sdk-csharp-binary-desktop/stage"
            (self.binary / "outputs/csharp").mkdir(parents=True)
            (self.binary / "outputs/csharp/CodexAgent.dll").write_bytes(b"synthetic compiled C#\n")
            write_output_manifest(self.binary, "sdk", "csharp", "binary", "desktop", "0.3.0",
                                  {"csharp-binary": "outputs/csharp"})
            from ci.tests.test_tooling_inspector import ToolingInspectorTest
            fixture = ToolingInspectorTest(methodName="runTest")
            fixture.setUp()
            self.addCleanup(fixture.doCleanups)
            self.inspector_directory = self.root / "private-inspector"
            self.inspector_directory.mkdir()
            payload = {**fixture.payload, "inspector-manifest.json": fixture.manifest(fixture.payload)}
            for name, raw in payload.items():
                (self.inspector_directory / name).write_bytes(raw)
            self.inspector_digest = sha256_bytes(payload["inspector-manifest.json"])
        self.calls, self.predecessor_calls = [], []
        self.host, self.return_code, self.launch_error = "linux-x64", 0, False
        self.output_version = "0.3.0"
        self.after_process = lambda: None

    def predecessor(self, *identity):
        self.predecessor_calls.append(identity)
        return self.records[identity]

    def process(self, command, **arguments):
        self.calls.append(command)
        self.assertEqual(self.root, arguments["cwd"])
        self.assertEqual({"SAFE": "explicit child environment"}, arguments["env"])
        self.assertEqual(subprocess.STDOUT, arguments["stderr"])
        self.assertFalse(arguments["check"])
        self.assertEqual(["python3", "-B", "-m", "ci.sdk_native_phase", "package", str(self.root)], command[:6])
        fields = dict(value[2:].split("=", 1) for value in command if value.startswith("-P"))
        expected_fields = {
            "codexAgent.product": "sdk", "codexAgent.component": self.plan["component"],
            "codexAgent.phase": "package", "codexAgent.target": "desktop",
            "codexAgent.candidateCommit": self.producer["commit"],
            "codexAgent.candidateTree": self.producer["tree"],
            "codexAgent.nativeWrapperRuntimeStageRoot": str(self.runtime),
            "codexAgent.nativeWrapperPackageSourcesRoot": str(self.sources),
            "codexAgent.nativeWrapperPackageSdksRoot": str(self.sdks),
            "codexAgent.sdkCompatibilityRequest": str(self.request),
            "codexAgent.sdkVersion": "0.3.0",
        }
        if self.binary is not None:
            expected_fields["codexAgent.csharpBinaryStageRoot"] = str(self.binary)
            expected_fields["codexAgent.csharpDotnetProfile"] = str(
                self.root / "gradle/release/toolchains/sdk/csharp.json")
            expected_fields["codexAgent.csharpInspectorRoot"] = str(self.inspector_directory)
            expected_fields["codexAgent.csharpInspectorManifestSha256"] = self.inspector_digest
        self.assertEqual(fields, expected_fields)
        arguments["stdout"].write(b"raw Gradle\xff\x00\n")
        if self.launch_error:
            raise OSError("synthetic process launch failure")
        if self.return_code == 0:
            (self.stage / "outputs").mkdir(parents=True)
            (self.stage / "outputs/synthetic-result").write_bytes(b"not a native package\n")
            write_output_manifest(self.stage, "sdk", self.plan["component"], "package", "desktop",
                                  self.output_version, {"evidence": "outputs"})
        self.after_process()
        return subprocess.CompletedProcess(command, self.return_code)

    def invoke(self, **changes):
        arguments = dict(producer=self.producer, sdk_version="0.3.0", repository_root=self.root,
            destination=self.destination, runtime_stages=self.runtime,
            prepared_sources=self.sources, staged_sdks=self.sdks,
            compatibility_request=self.request, predecessor=self.predecessor, environ={},
            csharp_binary_stage=self.binary)
        with ExitStack() as stack:
            if self.binary is not None:
                from tooling_inspector import borrowed_inspector
                arguments["csharp_inspector"] = stack.enter_context(borrowed_inspector(
                    self.inspector_directory, self.inspector_digest))
            stack.enter_context(patch("native_wrappers.host_classifier", return_value=self.host))
            stack.enter_context(patch.object(product_reuse, "_runtime_worker_environment",
                side_effect=AssertionError("No Gradle environment for package-only work")))
            stack.enter_context(patch.object(product_reuse, "_worker_process_environment", return_value=
                {"SAFE": "explicit child environment"}))
            self.checkout = stack.enter_context(patch.object(product_reuse, "_runtime_worker_checkout"))
            stack.enter_context(patch.object(worker, "_request_inventory", side_effect=lambda _: {
                self.request_input: sha256_bytes(self.request_input.read_bytes())}))
            stack.enter_context(patch.object(worker, "verify_sdk_dotnet_toolchain"))
            stack.enter_context(patch.object(worker, "verify_python_package_identity"))
            stack.enter_context(patch.object(worker.subprocess, "run", side_effect=self.process))
            stack.enter_context(patch("products.restore.finalize_phase_object",
                                      side_effect=AssertionError("premature admission")))
            return worker.execute(self.plan, **{**arguments, **changes})

    def test_all_five_packages_return_unadmitted_outputs_and_preserve_ten_originals(self):
        for language in NATIVE_BINDINGS:
            with self.subTest(language=language):
                self.fixture(language)
                original = regular_file_inventory(self.root / "originals")
                imported = regular_file_inventory(self.runtime)
                prepared = regular_file_inventory(self.root / "prepared")
                self.assertEqual(worker.route(self.plan), {
                    "runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64",
                    "toolchainProfile": "sdk-csharp" if language == "csharp" else None,
                    "producerRole": None, "supervisor": None,
                })
                result = self.invoke()
                self.assertEqual(result, {"stage": self.stage, "diagnostics": self.destination,
                    "outputInventory": regular_file_inventory(self.stage), "stagedSdks": self.sdks,
                    "stagedSdkInventory": regular_file_inventory(self.sdks)})
                self.assertEqual(original, regular_file_inventory(self.root / "originals"))
                self.assertEqual(imported, regular_file_inventory(self.runtime))
                self.assertEqual(prepared, regular_file_inventory(self.root / "prepared"))
                build = self.root / "codex-agent-sdk/build"
                self.assertFalse((build / "native-wrapper-c-abi-sdks").exists())
                self.assertFalse((build / "native-wrapper-package-sources").exists())
                self.assertEqual(set(self.records), set(self.predecessor_calls))
                self.assertEqual(10, len(self.predecessor_calls))
                self.assertEqual({"gradle.log", "execution.json"},
                                 {path.name for path in self.destination.iterdir()})
                self.assertEqual(b"raw Gradle\xff\x00\n", (self.destination / "gradle.log").read_bytes())
                self.assertGreaterEqual(self.checkout.call_count, 4)

    def test_wrong_phase_language_target_or_actual_host_never_executes(self):
        for field, value in (("component", "javascript"), ("product", "runtime"),
                             ("phase", "validation"), ("phase", "metadata"),
                             ("target", "linux-x64"), ("host", "linux-arm64")):
            with self.subTest(field=field, value=value):
                self.fixture()
                if field == "host":
                    self.host = value
                else:
                    self.plan[field] = value
                with self.assertRaisesRegex(ValueError, "implemented worker|actual host"):
                    self.invoke()
                self.assertEqual([], self.calls)
                self.assertFalse(self.destination.exists())

    def test_wrong_original_identity_manifest_and_imported_bytes_reject_before_process(self):
        for kind in ("receipt", "original-output", "imported-output", "extra", "missing"):
            with self.subTest(kind=kind):
                self.fixture()
                record = next(iter(self.records.values()))
                if kind == "receipt":
                    record["receipt"] = {**record["receipt"], "target": "wrong-target"}
                elif kind == "original-output":
                    (record["stage"] / "outputs/original").write_bytes(b"changed")
                elif kind == "imported-output":
                    (self.runtime / NATIVE_TARGETS[0] / "package/outputs/original").write_bytes(b"changed")
                elif kind == "extra":
                    (self.runtime / "unrelated").write_bytes(b"undeclared")
                else:
                    (self.runtime / NATIVE_TARGETS[0] / "package/output-manifest.json").unlink()
                with self.assertRaises(ValueError):
                    self.invoke()
                self.assertEqual([], self.calls)
                self.assertFalse(self.destination.exists())

    def test_process_and_launch_failures_retain_raw_diagnostics_without_admission(self):
        for launch in (False, True):
            with self.subTest(launch=launch):
                self.fixture()
                self.return_code, self.launch_error = 7, launch
                with self.assertRaisesRegex(OSError if launch else ValueError,
                                            "launch failure" if launch else "exit code 7"):
                    self.invoke()
                self.assertEqual(b"raw Gradle\xff\x00\n", (self.destination / "gradle.log").read_bytes())
                execution = load_canonical_json_bytes((self.destination / "execution.json").read_bytes())
                self.assertEqual(None if launch else 7, execution["returnCode"])
                self.assertFalse((self.destination / "shard").exists())
                self.assertFalse(self.stage.exists())

    def test_late_original_request_plan_and_bytecode_changes_reject(self):
        for kind in ("original", "receipt", "imported", "sources", "sdks",
                     "request", "request-input", "plan", "bytecode"):
            with self.subTest(kind=kind):
                self.fixture()
                record = next(iter(self.records.values()))
                def mutate():
                    if kind == "plan":
                        self.plan["buildKey"] = "sha256:" + "c" * 64
                        return
                    path = {"original": record["stage"] / "outputs/original",
                        "receipt": record["receiptPath"],
                        "imported": self.runtime / NATIVE_TARGETS[0] / "package/outputs/original",
                        "sources": self.sources / "python/original-source",
                        "sdks": self.sdks / "synthetic-staging",
                        "request": self.request, "request-input": self.request_input,
                        "bytecode": self.destination / "python-bytecode"}[kind]
                    path.write_bytes(b"changed")
                self.after_process = mutate
                with self.assertRaisesRegex(ValueError, "changed|bytecode"):
                    self.invoke()
                self.assertFalse((self.destination / "shard").exists())

    def test_owned_output_collisions_and_input_alias_preserve_originals(self):
        for kind in ("stage", "destination", "input-output-overlap", "alias"):
            with self.subTest(kind=kind):
                self.fixture()
                changes = {}
                path = {"stage": self.stage, "destination": self.destination,
                        "input-output-overlap": self.sdks, "alias": self.stage}[kind]
                if kind == "input-output-overlap":
                    changes["destination"] = self.sdks
                if kind == "alias":
                    path.parent.mkdir(parents=True)
                    path.symlink_to(self.runtime, target_is_directory=True)
                else:
                    path.mkdir(parents=True, exist_ok=True)
                    (path / "sentinel").write_bytes(b"original sentinel")
                before = regular_file_inventory(self.runtime)
                prepared = regular_file_inventory(self.root / "prepared")
                with self.assertRaisesRegex(ValueError, "fresh"):
                    self.invoke(**changes)
                self.assertEqual(before, regular_file_inventory(self.runtime))
                self.assertEqual(prepared, regular_file_inventory(self.root / "prepared"))
                if kind != "alias":
                    self.assertEqual(b"original sentinel", (path / "sentinel").read_bytes())
                self.assertEqual([], self.calls)

    def test_wrong_output_version_rejects_without_shard(self):
        self.output_version = "0.2.0"
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertFalse((self.destination / "shard").exists())

    def test_missing_relative_or_symbolic_prepared_inputs_never_fall_back_to_preparation(self):
        for kind in ("relative-sources", "relative-sdks", "missing-language", "symbolic-sdks"):
            with self.subTest(kind=kind):
                self.fixture()
                changes = {}
                if kind == "relative-sources":
                    changes["prepared_sources"] = Path("prepared/sources")
                elif kind == "relative-sdks":
                    changes["staged_sdks"] = Path("prepared/sdks")
                elif kind == "missing-language":
                    (self.sources / "python").rename(self.sources / "not-python")
                else:
                    alias = self.root / "sdk-alias"
                    alias.symlink_to(self.sdks, target_is_directory=True)
                    changes["staged_sdks"] = alias
                before = regular_file_inventory(self.root / "prepared")
                with self.assertRaises(ValueError):
                    self.invoke(**changes)
                self.assertEqual([], self.calls)
                self.assertFalse(self.destination.exists())
                self.assertEqual(before, regular_file_inventory(self.root / "prepared"))

    def test_static_imported_registration_has_no_preparation_dependency(self):
        # Source wiring only: this does not assert a real Gradle graph or build.
        source = (Path(__file__).resolve().parents[2] /
                  "gradle/build-logic/src/main/kotlin/codexagent.native-wrapper-sdk.gradle.kts").read_text()
        self.assertIn(
            "check(importedNativeWrapperPackageSources.isPresent == importedNativeWrapperPackageSdks.isPresent)",
            source,
        )
        package = source.split("val nativeWrapperSdkPackageManifestTasks =", 1)[1].split(
            "// The snapshot verifier", 1)[0]
        imported, fresh = package.split("if (importedNativeWrapperPackageSources.isPresent) {", 1)[1].split(
            "} else {", 1)
        self.assertNotIn("dependsOn", imported)
        self.assertNotIn("stageNativeWrapperCAbiSdks", imported)
        self.assertNotIn("nativeWrapperPackageSourceTasks", imported)
        self.assertIn("sourcesDirectory.set(layout.dir(importedNativeWrapperPackageSources.map { file(it).resolve(language) }))",
                      imported)
        self.assertIn("sdkDirectory.set(layout.dir(importedNativeWrapperPackageSdks.map(::file)))", imported)
        self.assertIn("dependsOn(nativeWrapperPackageSourceTasks.getValue(language), stageNativeWrapperCAbiSdks)", fresh)
        evidence = package.split('val evidence = tasks.register<Sync>', 1)[1].split(
            "tasks.register<WriteProductOutputManifestTask>", 1)[0]
        self.assertIn("from(stage.flatMap { it.sdkDirectory })", evidence)
        self.assertNotIn("stageNativeWrapperCAbiSdks", evidence)

    def test_python_package_uses_existing_producer_and_exact_evidence_without_snapshot(self):
        for language in NATIVE_BINDINGS:
            with self.subTest(language=language):
                self.fixture(language)
                for name in ("sdk-compatibility.json", "sdk-runtime-root.pub"):
                    (self.sdks / name).write_bytes(("fixture " + name + "\n").encode())
                fields = {"codexAgent.product": "sdk", "codexAgent.component": language,
                    "codexAgent.phase": "package", "codexAgent.target": "desktop",
                    "codexAgent.sdkVersion": "0.3.0", "codexAgent.candidateCommit": "a" * 40,
                    "codexAgent.candidateTree": "b" * 40,
                    "codexAgent.nativeWrapperRuntimeStageRoot": str(self.runtime),
                    "codexAgent.nativeWrapperPackageSourcesRoot": str(self.sources),
                    "codexAgent.nativeWrapperPackageSdksRoot": str(self.sdks),
                    "codexAgent.sdkCompatibilityRequest": str(self.request)}
                if language == "csharp":
                    profile = self.root / "gradle/release/toolchains/sdk/csharp.json"
                    profile.parent.mkdir(parents=True)
                    profile.write_bytes(b"fixture profile; producer mocked\n")
                    fields.update({"codexAgent.csharpBinaryStageRoot": str(self.binary),
                        "codexAgent.csharpDotnetProfile": str(profile),
                        "codexAgent.csharpInspectorRoot": str(self.inspector_directory),
                        "codexAgent.csharpInspectorManifestSha256": self.inspector_digest})
                before = regular_file_inventory(self.root / "prepared")
                def package(sources, sdks, output, version, languages, **options):
                    self.assertEqual((self.sources, self.sdks, self.stage / "outputs", "0.3.0", (language,)),
                                     (sources, sdks, output, version, languages))
                    if language == "csharp":
                        from tooling_inspector import require_inspector
                        require_inspector(options.pop("csharp_inspector"))
                        self.assertEqual({"csharp_binary": self.binary / "outputs/csharp",
                                          "dotnet_profile": profile}, options)
                    else:
                        self.assertEqual({}, options)
                    (output / language).mkdir(parents=True)
                    (output / language / "fixture-package").write_bytes(b"simulated unchanged producer output\n")
                with patch("native_wrappers.host_classifier", return_value="linux-x64"), \
                     patch.object(worker, "verify_python_package_toolchain") as python_tools, \
                     patch("native_wrappers.package_all", side_effect=package) as producer, \
                     patch.object(product_reuse, "_runtime_worker_checkout"), \
                     patch.object(worker, "_inventory", side_effect=AssertionError("No redundant child inventory")), \
                     patch.object(worker, "_request_inventory", side_effect=AssertionError("No redundant request scan")), \
                     patch.object(worker.subprocess, "run", side_effect=AssertionError("No external process")), \
                     patch("products.inventory.snapshot_regular_tree", side_effect=AssertionError("No extra snapshot")), \
                     patch.dict(os.environ, {}, clear=True):
                    worker.main(worker._package_command(self.root, fields)[4:])
                    producer.assert_called_once()
                    self.assertEqual(int(language == "python"), python_tools.call_count)
                self.assertEqual(before, regular_file_inventory(self.root / "prepared"))
                expected = self.root / "expected-stage"
                (expected / f"outputs/{language}").mkdir(parents=True)
                (expected / f"outputs/{language}/fixture-package").write_bytes(b"simulated unchanged producer output\n")
                (expected / "outputs/evidence").mkdir()
                for name in ("sdk-compatibility.json", "sdk-runtime-root.pub"):
                    (expected / "outputs/evidence" / name).write_bytes((self.sdks / name).read_bytes())
                write_output_manifest(expected, "sdk", language, "package", "desktop", "0.3.0",
                                      {"evidence": "outputs/evidence", "package": f"outputs/{language}"})
                self.assertEqual(regular_file_inventory(expected), regular_file_inventory(self.stage))

    def test_csharp_cannot_fall_back_to_building_an_inspector(self):
        for value in (None, "/arbitrary/inspector.dll"):
            with self.subTest(value=value):
                self.fixture("csharp")
                with self.assertRaisesRegex(ValueError, "live private inspector"):
                    self.invoke(csharp_inspector=value)
                self.assertEqual([], self.calls)
        self.fixture("python")
        with self.assertRaisesRegex(ValueError, "Only C#"):
            self.invoke(csharp_inspector="/arbitrary/inspector.dll")
        self.assertEqual([], self.calls)

    def test_python_package_cli_and_original_lifetime_fail_closed(self):
        for kind in ("csharp", "host", "version", "source", "extra", "duplicate", "order",
                     "signing", "online", "relative", "alias", "existing", "toolchain", "source-exit", "failure"):
            with self.subTest(kind=kind):
                self.fixture()
                fields = {"codexAgent.product": "sdk", "codexAgent.component": "python",
                    "codexAgent.phase": "package", "codexAgent.target": "desktop",
                    "codexAgent.sdkVersion": "0.3.0", "codexAgent.candidateCommit": "a" * 40,
                    "codexAgent.candidateTree": "b" * 40,
                    "codexAgent.nativeWrapperRuntimeStageRoot": str(self.runtime),
                    "codexAgent.nativeWrapperPackageSourcesRoot": str(self.sources),
                    "codexAgent.nativeWrapperPackageSdksRoot": str(self.sdks),
                    "codexAgent.sdkCompatibilityRequest": str(self.request)}
                if kind == "csharp": fields["codexAgent.component"] = "csharp"
                if kind == "version": fields["codexAgent.sdkVersion"] = "9.9.9"
                if kind == "source": fields["codexAgent.candidateCommit"] = "unknown"
                if kind == "extra": fields["codexAgent.command"] = "compiler"
                if kind == "relative": fields["codexAgent.nativeWrapperPackageSourcesRoot"] = "relative"
                if kind == "alias":
                    alias = self.root / "source-alias"
                    alias.symlink_to(self.sources, target_is_directory=True)
                    fields["codexAgent.nativeWrapperPackageSourcesRoot"] = str(alias)
                if kind == "existing": self.stage.mkdir(parents=True)
                command = worker._package_command(self.root, fields)[4:]
                if kind == "duplicate": command.append("-PcodexAgent.product=sdk")
                if kind == "order": command[-2:] = reversed(command[-2:])
                environment = {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""} if kind == "signing" else {}
                if kind == "online": environment["CODEX_AGENT_VERIFIED_DEPENDENCY_FETCH"] = "true"
                def package(*args):
                    raise ValueError("fixture producer failure")
                with patch("native_wrappers.host_classifier", return_value="macos-arm64" if kind == "host" else "linux-x64"), \
                     patch.object(worker, "verify_python_package_toolchain", side_effect=
                         ValueError("fixture tool mismatch") if kind == "toolchain" else None), \
                     patch("native_wrappers.package_all", side_effect=package) as producer, \
                     patch.object(product_reuse, "_runtime_worker_checkout", side_effect=
                         [None, ValueError("fixture checkout changed")] if kind == "source-exit" else None) as checkout, \
                     patch.object(worker, "_inventory", side_effect=AssertionError("No redundant child inventory")), \
                     patch.object(worker, "_request_inventory", side_effect=AssertionError("No redundant request scan")), \
                     patch.object(worker.subprocess, "run", side_effect=AssertionError("No external process")), \
                     patch.dict(os.environ, environment, clear=True):
                    with self.assertRaisesRegex(ValueError, "fixture checkout changed" if kind == "source-exit" else
                                                "fixture producer failure" if kind == "failure" else "."):
                        worker.main(command)
                    self.assertEqual(int(kind in {"source-exit", "failure"}), producer.call_count)
                    if kind in {"source-exit", "failure"}:
                        self.assertEqual(2, checkout.call_count)
                self.assertFalse((self.stage / "output-manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
