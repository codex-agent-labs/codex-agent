"""Exercise the protected action's exact checkout repair without authority/network calls."""
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
ACTION = ROOT / ".github/actions/restore-reuse-qualification/action.yml"


def program():
    text = ACTION.read_text()
    body = text.split("python3 -I -B - <<'WINDOWS_GIT_BYTES'\n", 1)[1].split("        WINDOWS_GIT_BYTES\n", 1)[0]
    source = "\n".join(line[8:] for line in body.splitlines())
    result = {"__name__": "checkout_fixture"}
    exec(compile(source, str(ACTION), "exec"), result)
    return result


class Fixture:
    def __init__(self, root, raw=None):
        self.root = root
        self.raw = raw or {"ci/control.py": b"first\nsecond\n", ".github/action.yml": b"name: original\n"}
        self.objects = {str(i + 1) * 40: value for i, value in enumerate(self.raw.values())}
        self.entries = [(name, str(i + 1) * 40) for i, name in enumerate(self.raw)]
        self.head = b"a" * 40 + b"\n"
        self.tree = b"".join(f"100644 blob {oid}\t{name}\0".encode() for name, oid in self.entries)
        self.index = b"".join(f"100644 {oid} 0\t{name}\0".encode() for name, oid in self.entries)
        self.attrs = {}
        self.calls = []
        self.on_git = None
        self.on_read = None
        self.reads = 0
        for name, raw in self.raw.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw.replace(b"\n", b"\r\n"))
        self.consumer = SimpleNamespace(git=self.git, blobs=lambda _root, ids: {oid: self.objects[oid] for oid in ids},
                                        regular=self.regular, SUFFIXES={".py", ".yml"}, IGNORED={"tests", "__pycache__", "node_modules"})

    def regular(self, path):
        self.reads += 1
        if self.on_read:
            self.on_read(path, self.reads)
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError("not a regular file")
        return path.read_bytes()

    def git(self, root, *args, data=None):
        self.calls.append(args)
        if self.on_git:
            self.on_git(args)
        if args[:1] == ("rev-parse",):
            return self.head
        if args[:1] == ("ls-tree",):
            return self.tree
        if args[:1] == ("ls-files",):
            return self.index
        if args[:1] == ("check-attr",):
            return b"".join(name + b"\0" + attr.encode() + b"\0" +
                            self.attrs.get((name.decode(), attr, "--cached" in args), "unspecified").encode() + b"\0"
                            for name in data.split(b"\0") if name
                            for attr in ("text", "eol", "filter", "working-tree-encoding"))
        raise AssertionError(args)


class RestoreReuseWindowsCheckoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.code = program()

    def restore(self, fixture):
        self.code["restore_exact_controls"](self.root, fixture.consumer)

    def test_exact_crlf_becomes_original_blob_and_already_exact_is_untouched(self):
        fixture = Fixture(self.root)
        unchanged = self.root / ".github/action.yml"
        unchanged.write_bytes(fixture.raw[".github/action.yml"])
        with patch.object(self.code["os"], "replace", wraps=self.code["os"].replace) as replace:
            self.restore(fixture)
        self.assertEqual(replace.call_count, 1)
        for name, raw in fixture.raw.items():
            self.assertEqual((self.root / name).read_bytes(), raw)
        self.assertFalse(list(self.root.rglob(".exact-git-control-*")))
        self.assertFalse(any(args[0] in {"fetch", "checkout", "reset", "update-index"} for args in fixture.calls))

    def test_any_non_crlf_edit_prevents_all_writes(self):
        fixture = Fixture(self.root)
        first = (self.root / "ci/control.py").read_bytes()
        for invalid in (b"first\r\nsecond\n", b"unrelated change\r\n", b"first\r\nsecond\r\nextra"):
            with self.subTest(invalid=invalid):
                (self.root / ".github/action.yml").write_bytes(invalid)
                with self.assertRaisesRegex(ValueError, "beyond the exact"):
                    self.restore(fixture)
                self.assertEqual((self.root / "ci/control.py").read_bytes(), first)

    def test_binary_cr_utf8_and_attribute_transformations_are_rejected(self):
        for raw in (b"a\0b\n", b"a\rb\n", b"a\xff\n", b"a\x1bb\n"):
            with self.subTest(raw=raw):
                fixture = Fixture(self.root, {"ci/control.py": raw, ".github/action.yml": b"original\n"})
                with self.assertRaises((ValueError, UnicodeDecodeError)):
                    self.restore(fixture)
        for attr, value in (("text", "unset"), ("eol", "lf"), ("filter", "lfs"), ("working-tree-encoding", "UTF-16")):
            with self.subTest(attr=attr):
                fixture = Fixture(self.root)
                for cached in (False, True):
                    fixture.attrs[("ci/control.py", attr, cached)] = value
                with self.assertRaisesRegex(ValueError, "beyond the exact"):
                    self.restore(fixture)
                self.assertIn(b"\r\n", (self.root / "ci/control.py").read_bytes())

    def test_index_or_working_attributes_and_extra_controls_are_rejected(self):
        fixture = Fixture(self.root)
        fixture.index = fixture.index.replace(b"1" * 40, b"9" * 40)
        with self.assertRaisesRegex(ValueError, "index differs"):
            self.restore(fixture)
        fixture = Fixture(self.root)
        fixture.attrs[("ci/control.py", "text", False)] = "unset"
        with self.assertRaisesRegex(ValueError, "attributes differ"):
            self.restore(fixture)
        fixture = Fixture(self.root)
        (self.root / "ci/extra.py").write_text("untracked\n")
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            self.restore(fixture)

    def test_link_and_unresolved_index_are_rejected(self):
        fixture = Fixture(self.root)
        target = self.root / "ci/control.py"
        target.unlink()
        target.symlink_to(self.root / ".github/action.yml")
        with self.assertRaisesRegex(ValueError, "link or reparse"):
            self.restore(fixture)
        target.unlink()
        fixture = Fixture(self.root)
        fixture.index = fixture.index.replace(b" 0\t", b" 2\t")
        with self.assertRaisesRegex(ValueError, "unresolved index"):
            self.restore(fixture)

    def test_reparse_point_and_nonregular_git_mode_are_rejected(self):
        fixture = Fixture(self.root)
        original_lstat = Path.lstat
        def reparse(path):
            info = original_lstat(path)
            if path == self.root / "ci":
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
            return info
        with patch.object(Path, "lstat", reparse):
            with self.assertRaisesRegex(ValueError, "reparse point"):
                self.restore(fixture)
        fixture.tree = fixture.tree.replace(b"100644", b"120000")
        with self.assertRaisesRegex(ValueError, "regular Git path"):
            self.restore(fixture)

    def test_identity_or_bytes_mutating_before_write_cannot_succeed(self):
        fixture = Fixture(self.root)
        def mutation(path, count):
            if count == 3:
                path.write_bytes(b"changed during validation\n")
        fixture.on_read = mutation
        with self.assertRaisesRegex(ValueError, "changed before"):
            self.restore(fixture)
        fixture = Fixture(self.root)
        count = 0
        def head_rotation(args):
            nonlocal count
            if args[0] == "rev-parse":
                count += 1
                if count == 2:
                    fixture.head = b"b" * 40 + b"\n"
        fixture.on_git = head_rotation
        with self.assertRaisesRegex(ValueError, "Git identity changed"):
            self.restore(fixture)
        self.assertIn(b"\r\n", (self.root / "ci/control.py").read_bytes())

    def test_no_inventory_or_module_load_outside_windows_true_autocrlf(self):
        with patch.object(self.code["sys"], "platform", "linux"), patch.object(self.code["subprocess"], "run") as run:
            self.code["main"]()
            run.assert_not_called()
        for value in (b"false\n", b"input\n", b"0\n", b"\n"):
            with self.subTest(value=value), patch.object(self.code["sys"], "platform", "win32"), \
                    patch.dict(self.code["os"].environ, {"CONSUMER_ROOT": str(self.root)}), \
                    patch.object(self.code["subprocess"], "run", return_value=subprocess.CompletedProcess([], 0, value, b"")) as run, \
                    patch.object(self.code["importlib"].util, "spec_from_file_location") as load:
                self.code["main"]()
                self.assertEqual(run.call_count, 1)
                load.assert_not_called()
        self.assertIn("if: runner.os == 'Windows'", ACTION.read_text())
        self.assertIn("python3 -I -B -", ACTION.read_text())


if __name__ == "__main__":
    unittest.main()
