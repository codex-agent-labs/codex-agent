"""Real private JAR/file lifetimes; external authentication and dotnet are mocked.

Borrowed custody is deliberately not independent signature/source authority.
No fixture DLL is compiled or executed, and no hosted acceptance is claimed.
"""

from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import unittest
from unittest import mock
import zipfile

from ci import tooling_inspector as inspector
from ci.tests import test_tooling_inspector as producer_fixture
from products import tooling
from products.inventory import canonical_json_bytes, sha256_bytes


class CSharpInspectorCaptureTest(unittest.TestCase):
    def setUp(self):
        fixture = producer_fixture.ToolingInspectorTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture, self.root = fixture, fixture.root
        self.files = dict(fixture.payload)
        self.files["inspector-manifest.json"] = fixture.manifest(self.files)
        self.jar = self.root.parent / "authenticated-fixture.jar"
        self.write_jar()
        self.policy = {"evidence": str(self.root / "evidence"),
            "publicKey": str(self.root / "key.pub"), "javaExecutable": str(self.root / "java"),
            "requiredTrustDomain": "release", "keyring": str(self.root / "keys.json"),
            "keysDirectory": str(self.root / "keys")}
        self.revision = "a" * 40
        self.events = []

    def write_jar(self, files=None):
        with zipfile.ZipFile(self.jar, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("python/unrelated.py", b"not an inspector member")
            for name, raw in (self.files if files is None else files).items():
                archive.writestr(tooling._INSPECTOR_PREFIX + name, raw)

    @contextmanager
    def external_capture(self, *args, **kwargs):
        self.events.append("authenticated")
        try:
            yield self.jar
        finally:
            self.events.append("authentication-context-exited")

    @contextmanager
    def captured(self):
        with mock.patch.object(tooling, "verified_tooling_capture", side_effect=self.external_capture) as gate:
            with inspector.authenticated_inspector(self.policy, self.root, self.revision) as capability:
                gate.assert_called_once_with(Path(self.policy["evidence"]), self.root,
                    Path(self.policy["publicKey"]), required_trust_domain="release",
                    keyring=Path(self.policy["keyring"]), keys_directory=Path(self.policy["keysDirectory"]),
                    policy_revision=self.revision)
                yield capability

    def test_bounded_capture_fixed_process_and_nested_parent_child_lifetimes(self):
        reads = []
        real_read = zipfile.ZipFile.read

        def read(archive, member, *args, **kwargs):
            reads.append(member.filename if isinstance(member, zipfile.ZipInfo) else member)
            return real_read(archive, member, *args, **kwargs)

        assembly, root_key, compatibility = (self.root / name for name in ("CodexAgent.dll", "root.pub", "compatibility.json"))
        with mock.patch.object(zipfile.ZipFile, "read", read), \
                mock.patch.object(inspector.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as process:
            with self.captured() as parent:
                self.assertIs(parent, inspector.require_inspector(parent))
                directory, digest = parent.handoff()
                self.assertEqual(self.files, {path.name: path.read_bytes() for path in directory.iterdir()})
                self.assertEqual(sha256_bytes(self.files["inspector-manifest.json"]), digest)
                self.assertEqual(["authenticated"], self.events)
                with inspector.borrowed_inspector(directory, digest) as child:
                    child.verify_resources(assembly, root_key, compatibility)
                with self.assertRaisesRegex(ValueError, "expired"):
                    inspector.require_inspector(child)
                parent.verify_resources(assembly, root_key, compatibility)
                self.assertEqual(["authenticated"], self.events)
                expected = mock.call(["dotnet", str(directory / "VerifySdkRuntimeRoot.dll"),
                    str(assembly), str(root_key), str(compatibility)],
                    capture_output=True, text=True, check=False, timeout=30)
                self.assertEqual([expected, expected], process.call_args_list)
        self.assertEqual([tooling._INSPECTOR_PREFIX + name for name in inspector._LIMITS], reads)
        self.assertFalse(directory.exists())
        self.assertEqual(["authenticated", "authentication-context-exited"], self.events)
        with self.assertRaisesRegex(ValueError, "expired"):
            parent.handoff()

    def test_invalid_external_authentication_never_extracts_or_runs(self):
        for reason in ("invalid signature", "wrong current source policy"):
            with self.subTest(reason=reason), \
                    mock.patch.object(tooling, "verified_tooling_capture", side_effect=ValueError(reason)), \
                    mock.patch.object(zipfile, "ZipFile") as archive, \
                    mock.patch.object(inspector.subprocess, "run") as process:
                with self.assertRaisesRegex(ValueError, reason), \
                        inspector.authenticated_inspector(self.policy, self.root, self.revision):
                    self.fail("Unauthenticated tool was yielded")
                archive.assert_not_called()
                process.assert_not_called()

    def test_oversized_selected_member_is_rejected_before_read(self):
        name = "VerifySdkRuntimeRoot.dll"
        self.write_jar({**self.files, name: b"x" * (inspector._LIMITS[name] + 1)})
        reads = []
        real_read = zipfile.ZipFile.read

        def read(archive, member, *args, **kwargs):
            reads.append(member.filename)
            return real_read(archive, member, *args, **kwargs)

        with mock.patch.object(zipfile.ZipFile, "read", read), \
                mock.patch.object(inspector.subprocess, "run") as process:
            with self.assertRaisesRegex(ValueError, "invalid size"), self.captured():
                self.fail("Oversized inspector was yielded")
            self.assertNotIn(tooling._INSPECTOR_PREFIX + name, reads)
            process.assert_not_called()

    def test_child_rejects_changed_manifest_members_extra_and_symbolic_files(self):
        for change in ("digest", "manifest", "substitution", "member", "missing", "extra", "symlink"):
            with self.subTest(change=change), self.captured() as parent:
                directory, digest = parent.handoff()
                original = {path.name: path.read_bytes() for path in directory.iterdir()}
                dll = directory / "VerifySdkRuntimeRoot.dll"
                try:
                    if change == "digest":
                        digest = "sha256:" + "0" * 64
                    elif change == "manifest":
                        (directory / "inspector-manifest.json").write_bytes(b"{}\n")
                    elif change == "substitution":
                        dll.write_bytes(b"another executable")
                        manifest = json.loads(original["inspector-manifest.json"])
                        row = next(row for row in manifest["files"] if row["relativePath"] == dll.name)
                        row.update(bytes=dll.stat().st_size, sha256=sha256_bytes(dll.read_bytes()))
                        (directory / "inspector-manifest.json").write_bytes(canonical_json_bytes(manifest))
                    elif change == "member":
                        dll.write_bytes(b"tampered executable")
                    elif change == "missing":
                        dll.unlink()
                    elif change == "extra":
                        (directory / "extra.dll").write_bytes(b"unexpected")
                    else:
                        target = self.root / "same-bytes.dll"
                        target.write_bytes(original[dll.name])
                        dll.unlink()
                        dll.symlink_to(target)
                    with self.assertRaises(ValueError), inspector.borrowed_inspector(directory, digest):
                        self.fail("Changed custody was yielded")
                finally:
                    for path in directory.iterdir():
                        path.unlink()
                    for name, raw in original.items():
                        (directory / name).write_bytes(raw)

    def test_process_failure_exception_and_late_mutation_never_fall_back(self):
        for failure in ("return-code", "exception", "mutation"):
            with self.subTest(failure=failure):
                def process(command, **_kwargs):
                    if failure == "exception":
                        raise subprocess.TimeoutExpired(command, 30)
                    if failure == "mutation":
                        Path(command[1]).write_bytes(b"changed during execution")
                    return subprocess.CompletedProcess(command, 1 if failure == "return-code" else 0,
                                                       stderr="invalid resources")

                with mock.patch.object(inspector.subprocess, "run", side_effect=process) as run:
                    with self.assertRaises((ValueError, subprocess.TimeoutExpired)), self.captured() as value:
                        value.verify_resources(self.root / "assembly", self.root / "root", self.root / "compatibility")
                    self.assertEqual(1, run.call_count)
                    self.assertEqual("dotnet", run.call_args.args[0][0])
                    self.assertTrue(run.call_args.args[0][1].endswith("VerifySdkRuntimeRoot.dll"))
                    with self.assertRaisesRegex(ValueError, "expired"):
                        inspector.require_inspector(value)

    def test_only_exact_live_capability_is_accepted(self):
        class Lookalike:
            def verify_resources(self, *_args):
                raise AssertionError("duck-typed inspector must not run")

        class Subclass(inspector._Inspector):
            pass

        for value in (None, {}, self.root, Lookalike(), object.__new__(Subclass)):
            with self.subTest(type=type(value)), self.assertRaisesRegex(ValueError, "live private inspector"):
                inspector.require_inspector(value)
        with self.assertRaisesRegex(ValueError, "private context"):
            inspector._Inspector(self.root, self.files, object())
