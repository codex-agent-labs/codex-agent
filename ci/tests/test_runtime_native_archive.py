"""Synthetic pinned input capture; no upstream downloads or Runtime production."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_native_phase
from products.inventory import canonical_json_bytes, sha256_bytes, write_canonical_json
from products.receipt import compute_build_key
from products.registry import NATIVE_TARGETS, PhaseInstanceId
from products.runtime_evidence import PRODUCT_RUNTIME_TARGETS
from products.selection import phase_git_inventory


class RuntimeNativeArchiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="native-archive-authority-")
        cls.addClassCleanup(temporary.cleanup)
        cls.repository = Path(temporary.name).resolve()
        cls.archives = {target: f"synthetic original upstream bytes for {target}\n".encode() for target in NATIVE_TARGETS}
        cls.manifest = {
            "version": "0.149.0", "releaseTag": "rust-v0.149.0", "distributions": [{
                "target": kotlin, "classifier": f"app-server-{target}", "asset": f"codex-{target}.tar.gz",
                "archiveSha256": sha256_bytes(cls.archives[target]).removeprefix("sha256:"),
                "archiveEntry": f"codex-{target}", "binarySha256": "b" * 64,
                "executableName": "codex-app-server", "supervisorExecutableName": "codex-process-supervisor",
            } for kotlin, target in PRODUCT_RUNTIME_TARGETS.items()],
        }
        cls.manifest_path = cls.repository / runtime_native_phase._DISTRIBUTION_MANIFEST
        write_canonical_json(cls.manifest_path, cls.manifest)
        def git(*arguments):
            return subprocess.run(["git", *arguments], cwd=cls.repository, check=True,
                                  capture_output=True, text=True).stdout.strip()
        git("init", "-q")
        git("config", "user.name", "Synthetic pinned upstream fixture")
        git("config", "user.email", "fixture@example.invalid")
        git("add", ".")
        git("commit", "-qm", "synthetic pinned archive authority")
        cls.revision = git("rev-parse", "HEAD")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="native-archive-capture-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.source = self.work / "original-download"
        self.source.write_bytes(self.archives["linux-arm64"])
        self.destination = self.work / "captured"

    def plan(self, target="linux-arm64"):
        inventory = phase_git_inventory(self.repository, self.revision, PhaseInstanceId("runtime", target, "binary", target))
        inputs = {"inventory": inventory, "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
                  "upstreamArtifacts": [], "versionIdentity": "0.2.0", "flagsDigest": "sha256:" + "1" * 64,
                  "toolchainProfileDigest": "sha256:" + "2" * 64, "outputSchemaVersion": 1}
        return {"schemaVersion": 1, "product": "runtime", "component": target, "phase": "binary",
                "target": target, "inputs": inputs, "buildKey": compute_build_key(
                    product="runtime", component=target, phase="binary", target=target, inputs=inputs)}

    def capture(self, plan=None, **changes):
        return runtime_native_phase.capture_archive(self.plan() if plan is None else plan, **{
            "repository_root": self.repository, "revision": self.revision,
            "source": self.source, "destination": self.destination, **changes,
        })

    def test_all_five_exact_assets_capture_without_unpacking_or_modifying_original(self):
        for target in NATIVE_TARGETS:
            with self.subTest(target=target):
                self.source.write_bytes(self.archives[target])
                before = self.source.read_bytes()
                destination = self.work / target
                self.assertEqual(destination, self.capture(self.plan(target), destination=destination))
                self.assertEqual([f"codex-{target}.tar.gz"], [path.name for path in destination.iterdir()])
                self.assertEqual(before, (destination / f"codex-{target}.tar.gz").read_bytes())
                self.assertEqual(before, self.source.read_bytes())

    def test_git_authority_ignores_working_copy_override_and_rejects_unbound_plan(self):
        original = self.manifest_path.read_bytes()
        altered = copy.deepcopy(self.manifest)
        for record in altered["distributions"]:
            record["archiveSha256"] = "c" * 64
        try:
            write_canonical_json(self.manifest_path, altered)
            self.capture()
        finally:
            self.manifest_path.write_bytes(original)
        self.assertEqual(self.archives["linux-arm64"], (self.destination / "codex-linux-arm64.tar.gz").read_bytes())
        plan = self.plan()
        plan["inputs"]["inventory"] = []
        plan["inputs"]["phaseInputDigest"] = sha256_bytes(canonical_json_bytes([]))
        plan["buildKey"] = compute_build_key(product="runtime", component="linux-arm64", phase="binary",
                                              target="linux-arm64", inputs=plan["inputs"])
        with self.assertRaisesRegex(ValueError, "manifest differs"):
            self.capture(plan, destination=self.work / "unbound")
        self.assertFalse((self.work / "unbound").exists())

    def test_wrong_phase_target_revision_key_and_hash_reject_without_destination(self):
        for changes in ({"phase": "package"}, {"product": "sdk"}, {"target": "linux-x64"},
                        {"component": "jvm", "target": "jvm"}, {"buildKey": "sha256:" + "4" * 64}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.capture({**self.plan(), **changes})
        with self.assertRaisesRegex(ValueError, "exact Git"):
            self.capture(revision="HEAD")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.capture(self.plan("linux-x64"))
        self.source.write_bytes(b"wrong original download bytes")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.capture()
        self.assertFalse(self.destination.exists())

    def test_unsafe_source_destination_and_oversized_input_preserve_sentinels(self):
        original = self.source.read_bytes()
        link = self.work / "source-link"
        link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            self.capture(source=link)
        parent_link = self.work / "parent-link"
        parent_link.symlink_to(self.work, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.capture(source=parent_link / self.source.name)
        with self.assertRaises(ValueError):
            self.capture(destination=parent_link / "escaped")
        with self.assertRaises(ValueError):
            self.capture(destination=self.source / "child")
        self.destination.mkdir()
        sentinel = self.destination / "original"
        sentinel.write_bytes(b"prior immutable capture")
        with self.assertRaises(ValueError):
            self.capture()
        self.assertEqual(b"prior immutable capture", sentinel.read_bytes())
        self.assertEqual(original, self.source.read_bytes())
        oversized = self.work / "oversized"
        with oversized.open("wb") as file:
            file.truncate(runtime_native_phase._PINNED_ARCHIVE_LIMIT + 1)
        with self.assertRaisesRegex(ValueError, "too large"):
            self.capture(source=oversized, destination=self.work / "oversized-capture")
        self.assertFalse((self.work / "oversized-capture").exists())

    def test_input_changed_after_hash_cannot_be_published(self):
        original_read = runtime_native_phase.read_regular_file_bytes
        reads = 0
        def read(path, **kwargs):
            nonlocal reads
            data = original_read(path, **kwargs)
            if path == self.source:
                reads += 1
                if reads == 1:
                    self.source.write_bytes(b"changed after the first exact hash")
            return data
        with mock.patch.object(runtime_native_phase, "read_regular_file_bytes", side_effect=read):
            with self.assertRaisesRegex(ValueError, "changed during"):
                self.capture()
        self.assertFalse(self.destination.exists())
