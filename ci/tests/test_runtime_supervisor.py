"""Synthetic original content, never actual supervisor execution or transport trust."""
from pathlib import Path
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
