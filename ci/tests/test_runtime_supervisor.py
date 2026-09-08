"""Synthetic original content, never actual supervisor execution or transport trust."""
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_supervisor
from runtime_native_phase import binary_plan
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, write_canonical_json
from products.toolchain import _verification_record, assemble_profile
from ci.tests import test_runtime_native_phase as native_fixture
from ci.tests.test_product_toolchain import observation


class RuntimeSupervisorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse real tiny Git authority setup without inheriting its test suite.
        native_fixture.RuntimeNativeBinaryPlanTest.setUpClass.__func__(cls)
        source = cls.root / runtime_supervisor.SOURCE
        source.parent.mkdir(parents=True)
        source.write_bytes((Path(__file__).resolve().parents[2] / runtime_supervisor.SOURCE).read_bytes())
        (cls.root / "gradlew").write_bytes(b"#!/bin/sh\nexit 99 # never executed by these process-boundary fixtures\n")
        cls.observation = observation("linux-arm64", "supervisor-builder", "Linux", "ARM64")
        cls.cross_observation = observation("linux-arm64", "cross-builder", "Linux", "X64")
        profile = cls.root / "gradle/release/toolchains/runtime/linux-arm64.json"
        write_canonical_json(profile, assemble_profile([cls.cross_observation, cls.observation], "linux-arm64"))
        cls.profiles["linux-arm64"] = sha256_bytes(profile.read_bytes())
        def git(*arguments):
            return subprocess.run(["git", *arguments], cwd=cls.root, check=True,
                                  capture_output=True, text=True).stdout.strip()
        git("add", ".")
        git("commit", "-qm", "synthetic supervisor source and observation fixture")
        cls.revision, cls.tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
        for record in (cls.observation, cls.cross_observation):
            record["repositoryRevision"], record["repositoryTree"] = cls.revision, cls.tree

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="supervisor-content-")
        self.addCleanup(temporary.cleanup)
        self.handoff = Path(temporary.name).resolve() / "original"
        self.handoff.mkdir()
        self.plan, arguments = native_fixture.RuntimeNativeBinaryPlanTest.inputs(self, "linux-arm64")
        self.plan = binary_plan(self.plan, **arguments)
        self.producer = {"repository": "fixture/codex-agent", "workflowPath": None,
                         "commit": self.revision, "tree": self.tree, "event": "local",
                         "runId": None, "runAttempt": None, "pullRequest": None}
        write_canonical_json(self.handoff / "runtime-binary-plan.json", self.plan)
        write_canonical_json(self.handoff / "toolchain-verification.json", _verification_record(
            self.root, self.revision, self.plan, self.observation))
        source = self.handoff / "source/codex_process_supervisor.c"
        source.parent.mkdir()
        source.write_bytes((self.root / runtime_supervisor.SOURCE).read_bytes())
        # Architecture fixture only: not compiled, executed, or accepted as a real producer.
        elf = bytearray(124)
        elf[:7] = b"\x7fELF\x02\x01\x01"
        struct.pack_into("<HHIQQ", elf, 16, 3, 183, 1, 0x400078, 64)
        struct.pack_into("<HHH", elf, 52, 64, 56, 1)
        struct.pack_into("<IIQQQQQQ", elf, 64, 1, 5, 0, 0x400000, 0, len(elf), len(elf), 4096)
        elf[120:] = b"\xc0\x03\x5f\xd6"
        executable = self.handoff / runtime_supervisor.EXECUTABLE
        executable.parent.mkdir()
        executable.write_bytes(elf)
        (self.handoff / "gradle.log").write_bytes(b"\xffsynthetic raw diagnostics\x00\n")
        self.execution = {
            "schemaVersion": 1, "kind": "runtime-supervisor-execution", "producer": self.producer,
            "buildKey": self.plan["buildKey"], "task": runtime_supervisor.TASK, "host": "linux-arm64",
            "returnCode": 0, "elapsedNs": 1, "files": [],
        }
        self.refresh_execution()

    def refresh_execution(self):
        self.execution["files"] = regular_file_inventory(
            self.handoff, excluded_paths=("execution.json",), allow_empty=True)
        write_canonical_json(self.handoff / "execution.json", self.execution)

    def verify(self, **changes):
        return runtime_supervisor.verify_supervisor_handoff(self.handoff, **{
            "repository_root": self.root, "revision": self.revision, "phase_plan": self.plan,
            "contract_manifest": self.manifest, "producer": self.producer, "runtime_version": "0.2.4",
            **changes,
        })

    def test_exact_content_returns_data_preserves_all_originals_and_accepts_empty_raw_log(self):
        before = regular_file_inventory(self.handoff, allow_empty=True)
        result = self.verify()
        self.assertIs(type(result), dict)
        self.assertEqual(self.handoff / runtime_supervisor.EXECUTABLE, result["executable"])
        self.assertEqual(self.execution, result["execution"])
        self.assertEqual(before, regular_file_inventory(self.handoff, allow_empty=True))
        (self.handoff / "gradle.log").write_bytes(b"")
        self.refresh_execution()
        self.assertEqual(self.execution, self.verify()["execution"])

    def test_extra_missing_symbolic_and_non_normalized_inputs_reject_without_mutation(self):
        original = regular_file_inventory(self.handoff, allow_empty=True)
        extra = self.handoff / "extra"
        extra.mkdir()
        with self.assertRaises(ValueError):
            self.verify()
        extra.rmdir()
        extra.write_bytes(b"extra")
        with self.assertRaises(ValueError):
            self.verify()
        extra.unlink()
        source = self.handoff / "source/codex_process_supervisor.c"
        contents = source.read_bytes()
        source.unlink()
        try:
            with self.assertRaises(ValueError):
                self.verify()
            source.symlink_to(self.root / runtime_supervisor.SOURCE)
            with self.assertRaises(ValueError):
                self.verify()
        finally:
            source.unlink(missing_ok=True)
            source.write_bytes(contents)
        with self.assertRaises(ValueError):
            runtime_supervisor.verify_supervisor_handoff(
                self.handoff / ".." / "original", repository_root=self.root, revision=self.revision,
                phase_plan=self.plan, contract_manifest=self.manifest,
                producer=self.producer, runtime_version="0.2.4")
        self.assertEqual(original, regular_file_inventory(self.handoff, allow_empty=True))

    def test_wrong_source_executable_architecture_and_cross_builder_reject_even_with_rebound_inventory(self):
        for relative, replacement in (
            ("source/codex_process_supervisor.c", b"unrelated source"),
            (runtime_supervisor.EXECUTABLE, b"not an ELF executable"),
            ("toolchain-verification.json", canonical_json_bytes(_verification_record(
                self.root, self.revision, self.plan, self.cross_observation))),
        ):
            path = self.handoff / relative
            original = path.read_bytes()
            try:
                path.write_bytes(replacement)
                self.refresh_execution()
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    self.verify()
            finally:
                path.write_bytes(original)
                self.refresh_execution()
        path = self.handoff / runtime_supervisor.EXECUTABLE
        original = path.read_bytes()
        try:
            for offset, replacement in ((18, b"\x3e\x00"), (24, bytes(8)), (68, bytes(4))):
                modified = bytearray(original)
                modified[offset:offset + len(replacement)] = replacement
                path.write_bytes(modified)
                self.refresh_execution()
                with self.subTest(offset=offset), self.assertRaises(ValueError):
                    self.verify()
        finally:
            path.write_bytes(original)
            self.refresh_execution()

    def test_raw_inventory_and_original_plan_bytes_are_exact(self):
        log = self.handoff / "gradle.log"
        original = log.read_bytes()
        try:
            log.write_bytes(original + b"changed without original execution inventory")
            with self.assertRaisesRegex(ValueError, "inventory"):
                self.verify()
        finally:
            log.write_bytes(original)
        plan_path = self.handoff / "runtime-binary-plan.json"
        original = plan_path.read_bytes()
        try:
            write_canonical_json(plan_path, {**self.plan, "schemaVersion": True})
            self.refresh_execution()
            with self.assertRaisesRegex(ValueError, "full binary plan"):
                self.verify()
        finally:
            plan_path.write_bytes(original)
            self.refresh_execution()

    def test_cross_key_producer_result_profile_and_manifest_reject(self):
        for field, bad in (("buildKey", "sha256:" + "4" * 64), ("host", "linux-x64"),
                           ("task", "ciProductPhase"), ("returnCode", 1), ("returnCode", False),
                           ("schemaVersion", True), ("elapsedNs", -1),
                           ("producer", {**self.producer, "commit": "a" * 40})):
            old = self.execution[field]
            try:
                self.execution[field] = bad
                self.refresh_execution()
                with self.subTest(field=field), self.assertRaises(ValueError):
                    self.verify()
            finally:
                self.execution[field] = old
                self.refresh_execution()
        for changes in (
            {"producer": {**self.producer, "tree": "b" * 40}},
            {"phase_plan": {**self.plan, "buildKey": "sha256:" + "4" * 64}},
            {"contract_manifest": {**self.manifest, "contractDigest": "sha256:" + "4" * 64}},
            {"runtime_version": "0.3.0"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.verify(**changes)
        record_path = self.handoff / "toolchain-verification.json"
        original = record_path.read_bytes()
        record = _verification_record(self.root, self.revision, self.plan, self.observation)
        record["profileDigest"] = "sha256:" + "4" * 64
        try:
            write_canonical_json(record_path, record)
            self.refresh_execution()
            with self.assertRaises(ValueError):
                self.verify()
        finally:
            record_path.write_bytes(original)
            self.refresh_execution()

    def test_original_bytes_changed_during_verification_cannot_pass(self):
        original = runtime_supervisor._verification_record
        def change_after_real_gate(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.handoff / "gradle.log").write_bytes(b"changed after original capture")
            return result
        with mock.patch.object(runtime_supervisor, "_verification_record", side_effect=change_after_real_gate):
            with self.assertRaisesRegex(ValueError, "changed during"):
                self.verify()

    def producer_arguments(self):
        build = self.root / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="supervisor-worker-", dir=build)
        self.addCleanup(temporary.cleanup)
        work = Path(temporary.name)
        inputs = work / "inputs"
        inputs.mkdir()
        write_canonical_json(inputs / "runtime-binary-plan.json", self.plan)
        names = {
            "contractPayload": "contract-input/codex-agent-contract-0.2.0.zip",
            "contractMetadataReceipt": "predecessors/contract-contract-metadata-common/phase-receipt.json",
            "contractAttestation": "contract-input/codex-agent-contract-0.2.0.attestation.json",
            "contractAttestationSignature": "contract-input/codex-agent-contract-0.2.0.attestation.sig",
            "contractPublicKey": "contract-input/public-key.pub",
        }
        for name in (*names.values(), "contract-input/execution-closure/original-proof.json", "trust/policy.json"):
            path = inputs / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"synthetic prepared input; root admission is separately tested\n")
        properties = {
            "codexAgent.product": "runtime", "codexAgent.component": "linux-arm64",
            "codexAgent.phase": "binary", "codexAgent.target": "linux-arm64",
            "codexAgent.runtimeVersion": "0.2.4", "codexAgent.contractVersion": "0.2.0",
            "codexAgent.candidateCommit": self.revision, "codexAgent.candidateTree": self.tree,
            "codexAgent.repositoryRevision": self.revision,
            "codexAgent.runtimeBinaryFlagsDigest": self.plan["inputs"]["flagsDigest"],
            "codexAgent.runtimeBinaryPlan": str(inputs / "runtime-binary-plan.json"),
            **{f"codexAgent.{key}": str(inputs / value) for key, value in names.items()},
        }
        outputs = self.root / "codex-agent-runtime-desktop/build"
        self.addCleanup(lambda: shutil.rmtree(outputs) if outputs.exists() else None)
        return {"repository_root": self.root, "producer": self.producer, "properties": properties,
                "phase_plan": self.plan, "contract_manifest": self.manifest, "runtime_version": "0.2.4",
                "destination": work / "supervisor", "environ": {"GRADLE_USER_HOME": str(work / "gradle-home")}}

    def process_fixture(self, *, returncode=0, mutate=None):
        real_run = subprocess.run
        commands = []
        def run(command, *args, **kwargs):
            if Path(command[0]).name == "git":
                return real_run(command, *args, **kwargs)
            self.assertEqual(str(self.root / "gradlew"), command[0])
            commands.append(command)
            self.assertEqual(1, command.count(runtime_supervisor.TASK))
            self.assertNotIn("ciProductPhase", command)
            self.assertIn("--offline", command)
            self.assertIn("--no-daemon", command)
            for selector in ("product", "component", "phase"):
                self.assertFalse(any(value.startswith(f"-PcodexAgent.{selector}=") for value in command))
            self.assertIn("-PcodexAgent.target=linux-arm64", command)
            kwargs["stdout"].write(b"\xfforiginal mocked Gradle process bytes\x00\n")
            if returncode == 0:
                output = self.root / "codex-agent-runtime-desktop/build/supervisor" / runtime_supervisor.EXECUTABLE
                output.parent.mkdir(parents=True)
                output.write_bytes((self.handoff / runtime_supervisor.EXECUTABLE).read_bytes())
                record = self.root / "codex-agent-runtime-desktop/build/toolchain-verification/linux-arm64-supervisor-builder.json"
                write_canonical_json(record, _verification_record(self.root, self.revision, self.plan, self.observation))
            if mutate is not None:
                mutate(command, kwargs)
            return subprocess.CompletedProcess(command, returncode)
        return commands, run

    def test_fixed_producer_observes_process_captures_six_files_and_preserves_private_original_inputs(self):
        arguments = self.producer_arguments()
        inputs = Path(arguments["properties"]["codexAgent.runtimeBinaryPlan"]).parent
        before = regular_file_inventory(inputs, allow_empty=True)
        commands, run = self.process_fixture()
        with mock.patch("native_wrappers.host_classifier", return_value="linux-arm64"), \
                mock.patch.object(runtime_supervisor.subprocess, "run", side_effect=run):
            result = runtime_supervisor.execute_supervisor(**arguments)
        destination = arguments["destination"]
        self.assertEqual(destination / runtime_supervisor.EXECUTABLE, result["executable"])
        self.assertEqual(set(runtime_supervisor._LIMITS), {row["relativePath"] for row in regular_file_inventory(destination)})
        self.assertEqual(before, regular_file_inventory(inputs, allow_empty=True))
        self.assertEqual(1, len(commands))
        selected = dict(value[2:].split("=", 1) for value in commands[0] if value.startswith("-P"))
        private = destination.with_name("supervisor-diagnostics") / "inputs"
        self.assertEqual(str(private / "runtime-binary-plan.json"), selected["codexAgent.runtimeBinaryPlan"])
        self.assertEqual(before, regular_file_inventory(private, allow_empty=True))
        self.assertEqual(b"\xfforiginal mocked Gradle process bytes\x00\n", (destination / "gradle.log").read_bytes())

    def test_failed_process_retains_exact_diagnostics_without_publishing_success(self):
        arguments = self.producer_arguments()
        commands, run = self.process_fixture(returncode=23)
        with mock.patch("native_wrappers.host_classifier", return_value="linux-arm64"), \
                mock.patch.object(runtime_supervisor.subprocess, "run", side_effect=run):
            with self.assertRaisesRegex(ValueError, "exit code 23"):
                runtime_supervisor.execute_supervisor(**arguments)
        self.assertEqual(1, len(commands))
        self.assertFalse(arguments["destination"].exists())
        diagnostics = arguments["destination"].with_name("supervisor-diagnostics")
        self.assertEqual(b"\xfforiginal mocked Gradle process bytes\x00\n", (diagnostics / "gradle.log").read_bytes())
        result = runtime_supervisor.load_canonical_json_bytes((diagnostics / "process.json").read_bytes())
        self.assertEqual(23, result["returnCode"])

    def test_producer_rejects_wrong_host_properties_existing_outputs_and_input_overlap_before_process(self):
        arguments = self.producer_arguments()
        commands, run = self.process_fixture()
        with mock.patch("native_wrappers.host_classifier", return_value="linux-x64"), \
                mock.patch.object(runtime_supervisor.subprocess, "run", side_effect=run):
            with self.assertRaisesRegex(ValueError, "actual Linux ARM64"):
                runtime_supervisor.execute_supervisor(**arguments)
        with mock.patch("native_wrappers.host_classifier", return_value="linux-arm64"), \
                mock.patch.object(runtime_supervisor.subprocess, "run", side_effect=run):
            for changes in (
                {"properties": {**arguments["properties"], "codexAgent.desktopSupervisorCompiler": "caller"}},
                {"properties": {**arguments["properties"], "codexAgent.phase": "metadata"}},
                {"destination": Path(arguments["properties"]["codexAgent.runtimeBinaryPlan"]).parent / "inside-originals"},
                {"environ": {**arguments["environ"], "GRADLE_OPTS": "-Icaller.gradle"}},
            ):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    runtime_supervisor.execute_supervisor(**{**arguments, **changes})
            output = self.root / "codex-agent-runtime-desktop/build/supervisor/linuxArm64"
            output.mkdir(parents=True)
            sentinel = output / "prior"
            sentinel.write_bytes(b"immutable previous output")
            with self.assertRaisesRegex(ValueError, "pre-existing"):
                runtime_supervisor.execute_supervisor(**arguments)
            self.assertEqual(b"immutable previous output", sentinel.read_bytes())
        self.assertEqual([], commands)
        self.assertFalse(arguments["destination"].exists())

    def test_producer_rejects_private_input_and_wrong_architecture_output_mutations_after_success(self):
        for kind in ("inputs", "executable", "observation"):
            arguments = self.producer_arguments()
            def mutate(command, _kwargs):
                if kind == "inputs":
                    plan_arg = next(value for value in command if value.startswith("-PcodexAgent.runtimeBinaryPlan="))
                    private = Path(plan_arg.split("=", 1)[1]).parent
                    (private / "trust/policy.json").write_bytes(b"changed private trust")
                elif kind == "executable":
                    path = self.root / "codex-agent-runtime-desktop/build/supervisor" / runtime_supervisor.EXECUTABLE
                    data = bytearray(path.read_bytes())
                    data[18:20] = b"\x3e\x00"
                    path.write_bytes(data)
                else:
                    path = self.root / "codex-agent-runtime-desktop/build/toolchain-verification/linux-arm64-supervisor-builder.json"
                    write_canonical_json(path, _verification_record(self.root, self.revision, self.plan, self.cross_observation))
            _, run = self.process_fixture(mutate=mutate)
            try:
                with self.subTest(kind=kind), mock.patch("native_wrappers.host_classifier", return_value="linux-arm64"), \
                        mock.patch.object(runtime_supervisor.subprocess, "run", side_effect=run):
                    with self.assertRaises(ValueError):
                        runtime_supervisor.execute_supervisor(**arguments)
                self.assertFalse(arguments["destination"].exists())
            finally:
                outputs = self.root / "codex-agent-runtime-desktop/build"
                if outputs.exists():
                    shutil.rmtree(outputs)
