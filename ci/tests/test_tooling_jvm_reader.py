"""Exact tooling-only reader source binding; fixture JARs are never executed."""

import ast
import importlib.util
import stat
import sys
import tempfile
import warnings
from pathlib import Path
import unittest
import zipfile

from ci.products import tooling
from ci.products.inventory import canonical_json_bytes
from ci.tests.test_ci import GitFixture

VERIFIER = ".github/actions/run-ci-lane/verified-consumers/runtime_evidence.py"
RESOURCE = "ci/products/runtime_evidence.py"
RECIPE = ".github/actions/run-ci-lane/release_tooling.init.gradle"
COPY_ALIASES = {
    "ci/products/inventory.py": ".github/actions/run-ci-lane/verified-consumers/inventory.py",
    "ci/products/sdk_inputs.py": ".github/actions/run-ci-lane/verified-consumers/sdk_inputs.py",
}


class ToolingJvmReaderPolicyTest(GitFixture):
    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.write("ci/products/sdk_package.py", "# fixture SDK verifier\n")
        self.write(RESOURCE, "# original producer reader\n")
        for resource in COPY_ALIASES:
            self.write(resource, "# original " + resource + "\n")
        self.write(RECIPE, "// original assembly\n")
        self.write(".github/actions/run-ci-lane/release_tooling_classes.json", '["FixtureTooling"]\n')
        self.git("add", ".")
        self.git("commit", "-qm", "original tooling fixture")
        self.original = self.git("rev-parse", "HEAD")
        self.write(VERIFIER, "# corrected consumer reader\n")
        for resource, consumer in COPY_ALIASES.items():
            self.write(consumer, "# current " + resource + "\n")
        self.write(RECIPE, "// explicit corrected consumer assembly\n")
        self.git("add", ".")
        self.git("commit", "-qm", "current tooling fixture")
        self.current = self.git("rev-parse", "HEAD")
        self.capture = self.root / "capture"
        (self.capture / "original").mkdir(parents=True)
        self.jar = self.root / "fixture.jar"

    def verify(self, revision, producer, reader, *, sdk=b"# fixture SDK verifier\n", copy_resources=None):
        (self.capture / tooling.ATTESTATION).write_bytes(canonical_json_bytes({"schemaVersion": 2}))
        (self.capture / "original/tooling-build-receipt.json").write_bytes(
            canonical_json_bytes({"producer": {"commit": producer}}))
        with zipfile.ZipFile(self.jar, "w") as archive:
            archive.writestr("FixtureTooling.class", b"fixture; never executed")
            archive.writestr("python/ci/products/sdk_package.py", sdk)
            archive.writestr("python/" + RESOURCE, reader)
            actual = copy_resources if copy_resources is not None else {
                path: (("# original " if revision == self.original else "# current ") + path + "\n").encode()
                for path in COPY_ALIASES}
            for path, contents in actual.items():
                archive.writestr("python/" + path, contents)
        tooling._verify_tooling_policy(self.jar, self.capture, self.root, revision)

    def test_old_policy_uses_original_source_and_current_policy_uses_declared_alias(self):
        self.verify(self.original, self.original, b"# original producer reader\n")
        self.verify(self.current, self.current, b"# corrected consumer reader\n")

    def test_wrong_or_tampered_resource_never_gets_a_mismatch_waiver(self):
        for reader in (b"# original producer reader\n", b"# corrected consumer reader\nchanged"):
            with self.subTest(reader=reader), self.assertRaisesRegex(ValueError, "differs from applicable policy"):
                self.verify(self.current, self.current, reader)
        with self.assertRaisesRegex(ValueError, "differs from applicable policy"):
            self.verify(self.original, self.original, b"# corrected consumer reader\n")
        with self.assertRaisesRegex(ValueError, "differs from applicable policy"):
            self.verify(self.current, self.current, b"# corrected consumer reader\n", sdk=b"# corrected consumer reader\n")

    def test_each_native_alias_binds_its_exact_blob_and_other_resources_keep_original_policy(self):
        expected = {path: ("# current " + path + "\n").encode() for path in COPY_ALIASES}
        for path in COPY_ALIASES:
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "differs from applicable policy"):
                self.verify(self.current, self.current, b"# corrected consumer reader\n",
                            copy_resources={**expected, path: ("# original " + path + "\n").encode()})

    def test_old_producer_recipe_cannot_claim_current_consumer(self):
        with self.assertRaisesRegex(ValueError, "compiler/build inputs differ"):
            self.verify(self.current, self.original, b"# corrected consumer reader\n")

    def test_alias_must_be_an_exact_regular_git_blob(self):
        source = self.root / VERIFIER
        source.unlink()
        source.symlink_to(self.root / RESOURCE)
        self.git("add", VERIFIER)
        self.git("commit", "-qm", "invalid symbolic alias fixture")
        bad = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(ValueError, "lacks a regular Git blob"):
            self.verify(bad, bad, b"# original producer reader\n")


class ToolingJvmReaderBoundaryTest(unittest.TestCase):
    def test_copy_differs_only_in_the_two_reviewed_archive_reader_definitions(self):
        root = Path(__file__).resolve().parents[2]
        original = ast.parse((root / RESOURCE).read_bytes())
        consumer = ast.parse((root / VERIFIER).read_bytes())
        allowed = {"_zip_entries", "inspect_jvm_runner"}
        for module in (original, consumer):
            module.body = [node for node in module.body
                           if not isinstance(node, ast.FunctionDef) or node.name not in allowed]
        self.assertEqual(ast.dump(original, include_attributes=False), ast.dump(consumer, include_attributes=False))

    def test_existing_directory_safety_cases_against_current_consumer(self):
        source = Path(__file__).resolve().parents[2] / VERIFIER
        spec = importlib.util.spec_from_file_location("ci.products.current_tooling_runtime_evidence", source)
        reader = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = reader
        self.addCleanup(sys.modules.pop, spec.name)
        spec.loader.exec_module(reader)
        entry = "classes/" + reader.JVM_RUNTIME_RUNNER_ENTRYPOINT.replace(".", "/") + ".class"
        files = [(entry, b"class"), ("lib/one.jar", b"jar")]

        def directory(name, data=b"", mode=stat.S_IFDIR | 0o755):
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = mode << 16
            return info, data

        cases = [("traversal", [directory("classes/../bad/")]),
                 ("absolute", [directory("/classes/")]),
                 ("backslash", [directory("classes\\bad/")]),
                 ("colon", [directory("classes:bad/")]),
                 ("nonempty", [directory("classes/", b"x")]),
                 ("symlink", [directory("classes/", mode=stat.S_IFLNK | 0o777)]),
                 ("duplicate", [directory("classes/"), directory("classes/")]),
                 ("shadow", [directory("classes/"), ("classes", b"file")]),
                 ("descendant", [directory("classes/x/y/"), ("classes/x", b"file"), ("classes/x/y/z", b"file")]),
                 ("orphan", [directory("classes/orphan/")]),
                 ("normalized", [directory("classes//")])]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / reader.JVM_RUNTIME_RUNNER_ARCHIVE
            for label, extra in cases:
                with self.subTest(case=label), warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with zipfile.ZipFile(path, "w") as archive:
                        for name, data in [*files, *extra]:
                            archive.writestr(name, data)
                    with self.assertRaises(ValueError):
                        reader.inspect_jvm_runner(path)
            with zipfile.ZipFile(path, "w") as archive:
                for name, data in [*files, directory("classes/"), directory("lib/")]:
                    archive.writestr(name, data)
            self.assertEqual(2, len(reader.inspect_jvm_runner(path)))
            with self.assertRaises(ValueError):
                reader._zip_entries(path, root_only=False)
            with self.assertRaises(ValueError):
                reader._zip_entries(path, root_only=True, allow_directories=True)
