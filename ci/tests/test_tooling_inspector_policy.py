"""Real Git/JAR policy checks; fixture DLL bytes are never compiled or executed.

Signature/provenance ordering is covered by the existing tooling capture tests.
These cases enter only the subsequent policy gate, with explicit receipt fixtures.
"""

import json
from pathlib import Path
from unittest import mock
import zipfile

from ci import tooling_inspector as inspector
from ci.products import tooling
from ci.products.inventory import canonical_json_bytes
from ci.tests.test_ci import GitFixture
from ci.tests import test_tooling_inspector as inspector_fixture


class ToolingInspectorPolicyTest(GitFixture):
    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        fixture = inspector_fixture.ToolingInspectorTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.write("ci/products/sdk_package.py", "# synthetic packaged verifier\n")
        self.write(".github/actions/run-ci-lane/release_tooling.init.gradle", "// synthetic recipe\n")
        self.legacy = self.commit(".github/actions/run-ci-lane/release_tooling_classes.json",
                                  '["ApplePackageExecutionContext"]\n')
        self.git("add", "ci/products/sdk_package.py",
                 ".github/actions/run-ci-lane/release_tooling.init.gradle")
        self.git("commit", "-qm", "legacy tooling inputs")
        self.legacy = self.git("rev-parse", "HEAD")
        repository = Path(__file__).resolve().parents[2]
        for relative in tooling._INSPECTOR_INPUTS:
            self.write(relative, (repository / relative).read_text())
        self.git("add", *tooling._INSPECTOR_INPUTS)
        self.git("commit", "-qm", "inspector compiler inputs")
        self.current = self.git("rev-parse", "HEAD")
        self.captured = self.root / "captured"
        (self.captured / "original/lane").mkdir(parents=True)
        self.jar = self.root / "fixture.jar"
        self.tool = dict(fixture.payload)
        self.tool["inspector-manifest.json"] = fixture.manifest(self.tool)

    def verify(self, files=None, *, revision=None, original=None, schema=1):
        revision = revision or self.current
        original = original or self.current
        (self.captured / tooling.ATTESTATION).write_bytes(canonical_json_bytes({"schemaVersion": schema}))
        receipt = (self.captured / "original/tooling-build-receipt.json" if schema == 2
                   else self.captured / "original/lane/lane-receipt.json")
        receipt.write_bytes(canonical_json_bytes({"producer": {"commit": original}} if schema == 2
                                                else {"validationCommit": original}))
        with zipfile.ZipFile(self.jar, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("ApplePackageExecutionContext.class", b"fixture class; never executed")
            archive.writestr("python/ci/products/sdk_package.py", b"# synthetic packaged verifier\n")
            for name, raw in (self.tool if files is None else files).items():
                archive.writestr(tooling._INSPECTOR_PREFIX + name, raw)
        tooling._verify_tooling_policy(self.jar, self.captured, self.root, revision)

    def test_current_policy_requires_exact_git_sources_profile_and_canonical_manifest(self):
        self.verify()
        for field in ("sourceFiles", "toolchainProfileSha256", "canonicalBytes"):
            with self.subTest(field=field):
                files = dict(self.tool)
                manifest = json.loads(files["inspector-manifest.json"])
                if field == "sourceFiles":
                    manifest[field][0]["sha256"] = "sha256:" + "0" * 64
                elif field == "toolchainProfileSha256":
                    manifest[field] = "sha256:" + "0" * 64
                files["inspector-manifest.json"] = (json.dumps(manifest, indent=2).encode()
                    if field == "canonicalBytes" else canonical_json_bytes(manifest))
                with self.assertRaises(ValueError):
                    self.verify(files)

    def test_original_and_current_compiler_inputs_must_match(self):
        with self.assertRaisesRegex(ValueError, "compiler/build inputs differ"):
            self.verify(original=self.legacy)
        for relative in tooling._INSPECTOR_INPUTS:
            with self.subTest(path=relative):
                original = (self.root / relative).read_text()
                changed = self.commit(relative, original + "\nchanged compiler input\n")
                try:
                    with self.assertRaisesRegex(ValueError, "compiler/build inputs differ"):
                        self.verify(revision=changed)
                finally:
                    self.commit(relative, original)

    def test_derived_inventory_missing_extra_tampered_and_oversized_files_fail(self):
        for name in self.tool:
            with self.subTest(missing=name):
                files = {key: value for key, value in self.tool.items() if key != name}
                with self.assertRaises(ValueError):
                    self.verify(files)
        for name in inspector.FILES:
            with self.subTest(tampered=name):
                with self.assertRaises(ValueError):
                    self.verify({**self.tool, name: self.tool[name] + b"tamper"})
        for name, raw in (("unexpected.dll", b"extra"),
                          ("VerifySdkRuntimeRoot.dll", b"x" * (inspector._LIMITS["VerifySdkRuntimeRoot.dll"] + 1))):
            with self.subTest(rejected_before_read=name):
                reads = []
                read = zipfile.ZipFile.read

                def observed(archive, member, *args, **kwargs):
                    reads.append(member.filename if isinstance(member, zipfile.ZipInfo) else member)
                    return read(archive, member, *args, **kwargs)

                with mock.patch.object(zipfile.ZipFile, "read", observed), \
                        self.assertRaisesRegex(ValueError, "undeclared or oversized"):
                    self.verify({**self.tool, name: raw})
                self.assertNotIn(tooling._INSPECTOR_PREFIX + name, reads)

    def test_legacy_policy_accepts_original_jar_but_rejects_unexpected_inspector(self):
        self.verify({}, revision=self.legacy, original=self.legacy)
        with self.assertRaisesRegex(ValueError, "undeclared or oversized"):
            self.verify(revision=self.legacy, original=self.legacy)

    def test_local_schema_two_cannot_claim_hosted_inspector(self):
        self.verify({}, revision=self.legacy, original=self.legacy, schema=2)
        with mock.patch.object(zipfile.ZipFile, "read", side_effect=AssertionError("read before schema gate")), \
                self.assertRaisesRegex(ValueError, "original hosted tooling compiler receipt"):
            self.verify(schema=2)
