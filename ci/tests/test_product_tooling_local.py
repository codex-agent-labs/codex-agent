"""Synthetic command/signing fixtures, not actual Gradle or hosted acceptance."""

import base64
import json
import os
from pathlib import Path
import subprocess
from unittest import mock

from ci.products import tooling_local as local
from ci.products.inventory import regular_file_inventory, write_canonical_json
from ci.products.signatures import generate_development_key, sign_manifest
from ci.products.tooling import ATTESTATION, SIGNATURE, JAR, verified_tooling_capture
from ci.tests.test_ci import GitFixture


class LocalToolingTest(GitFixture):
    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.commit("gradle/wrapper/gradle-wrapper.properties", "distributionUrl=https\\://example.invalid/gradle-9.4.1-bin.zip\n")
        self.commit("gradle/build-logic/build.gradle.kts", "// synthetic build source\n")
        self.java_home = self.root / "java"
        self.java = self.java_home / "bin" / ("java.exe" if os.name == "nt" else "java")
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b"synthetic Java, never executed")
        self.gradle = self.root / "gradle-installation"
        launcher = self.gradle / "lib/gradle-gradle-cli-main-9.4.1.jar"
        launcher.parent.mkdir(parents=True)
        launcher.write_bytes(b"synthetic Gradle, never executed")
        self.cache = self.root / "gradle-cache"
        dependency = self.cache / "caches/modules-2/files-2.1/test/dependency.jar"
        dependency.parent.mkdir(parents=True)
        dependency.write_bytes(b"synthetic dependency artifact")
        (self.cache / "caches/modules-2/modules-2.lock").write_bytes(b"")
        self.private, self.public, self.signing = generate_development_key(self.root / "keys")
        # Output is a sibling of the repository, never allowed to overlap inputs.
        self.output = self.root.parent / (self.root.name + "-tooling-output")
        self.addCleanup(self._remove_output)
        self.real_run = subprocess.run
        self.commands = []

    def _remove_output(self):
        if self.output.exists():
            import shutil
            shutil.rmtree(self.output)

    def execute(self, command, **kwargs):
        if Path(command[0]).name != self.java.name:
            return self.real_run(command, **kwargs)
        self.commands.append(command)
        source = Path(kwargs["cwd"])
        if command[-1] == "releaseToolingJar":
            self.assertIn("--offline", command)
            self.assertNotIn("JAVA_TOOL_OPTIONS", kwargs["env"])
            jar = source / JAR.removeprefix("payload/")
            jar.parent.mkdir(parents=True)
            jar.write_bytes(b"exact synthetic tooling JAR bytes\n")
            output = b"build\xff\0\r\n"
        else:
            output = b"Gradle 9.4.1\n" if command[-1] == "--version" else b"observed synthetic Java\n"
        return subprocess.CompletedProcess(command, 0, output)

    def produce(self, **overrides):
        values = dict(repository=self.root, java_home=self.java_home, gradle_installation=self.gradle,
            gradle_user_home=self.cache, signing_metadata=self.signing, private_key=self.private,
            public_key=self.public, output=self.output)
        values.update(overrides)
        with mock.patch.object(local.subprocess, "run", side_effect=self.execute):
            return local.produce_local_tooling_attestation(**values)

    def capture(self, **overrides):
        values = dict(evidence=self.output, repository=self.root, public_key=self.public,
                      required_trust_domain="development")
        values.update(overrides)
        return verified_tooling_capture(**values)

    def test_actual_fixed_command_path_records_local_producer_and_exact_raw_bytes(self):
        self.produce()
        original = self.output / "original"
        receipt = json.loads((original / local.RECEIPT).read_bytes())
        self.assertEqual("local", receipt["producer"]["event"])
        for key in ("workflowPath", "runId", "runAttempt", "pullRequest"):
            self.assertIsNone(receipt["producer"][key])
        execution = json.loads((original / "build-execution.json").read_bytes())
        self.assertEqual(b"build\xff\0\r\n", base64.b64decode(execution["outputBase64"]))
        before = regular_file_inventory(self.output, allow_empty=True)
        with self.capture() as jar:
            self.assertEqual(b"exact synthetic tooling JAR bytes\n", jar.read_bytes())
            captured = jar
        self.assertFalse(captured.exists())
        self.assertEqual(before, regular_file_inventory(self.output, allow_empty=True))
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.produce()

    def test_local_provenance_cannot_be_relabelled_release_even_with_valid_signature(self):
        with self.assertRaisesRegex(ValueError, "not development trust"):
            self.produce(signing_metadata={**self.signing, "trustDomain": "release"})
        self.produce()
        attestation = self.output / ATTESTATION
        value = json.loads(attestation.read_bytes())
        value["signing"]["trustDomain"] = "release"
        write_canonical_json(attestation, value)
        (self.output / SIGNATURE).unlink()
        sign_manifest(attestation, self.private, value["signing"])
        with self.assertRaisesRegex(ValueError, "cannot claim release"), self.capture(required_trust_domain="release"):
            self.fail("local producer became release")

    def test_failed_or_changed_build_never_publishes_success(self):
        execute = self.execute
        for change in ("failure", "source", "java", "gradle", "private-java", "private-gradle",
                       "dependencies", "private-dependencies"):
            def changed(command, **kwargs):
                result = execute(command, **kwargs)
                if command[-1] == "releaseToolingJar":
                    if change == "failure":
                        return subprocess.CompletedProcess(command, 1, b"failed native bytes\xff\n")
                    path = {"source": Path(kwargs["cwd"]) / "gradle/build-logic/build.gradle.kts",
                            "java": self.java, "gradle": self.gradle / "lib/gradle-gradle-cli-main-9.4.1.jar",
                            "private-java": Path(command[0]), "private-gradle": Path(command[2]),
                            "dependencies": self.cache / "caches/modules-2/files-2.1/test/dependency.jar",
                            "private-dependencies": Path(command[10]) / "caches/modules-2/files-2.1/test/dependency.jar"}[change]
                    path.write_bytes(path.read_bytes() + b"changed")
                return result
            with self.subTest(change=change), mock.patch.object(self, "execute", side_effect=changed), self.assertRaises(ValueError):
                self.produce()
            self.assertFalse(self.output.exists())

    def test_unknown_hosted_identity_source_command_and_raw_inventory_fail_closed(self):
        self.produce()
        original = self.output / "original"
        path = original / local.RECEIPT
        before = path.read_bytes()
        for mutate in (lambda value: value["producer"].update(runId=99),
                       lambda value: value.update(sourceInventorySha256="sha256:" + "0" * 64),
                       lambda value: value.update(outputs=[])):
            value = json.loads(before)
            mutate(value)
            write_canonical_json(path, value)
            with self.assertRaises(ValueError):
                local.verify_local_original(original, self.root)
        path.write_bytes(before)
        execution = original / "build-execution.json"
        value = json.loads(execution.read_bytes())
        value["command"][-1] = "publish"
        write_canonical_json(execution, value)
        with self.assertRaisesRegex(ValueError, "fixed offline task"):
            local.verify_local_original(original, self.root)

    def test_inputs_are_immutable_git_sources_and_external_initialization_is_rejected(self):
        (self.root / "gradle/build-logic/build.gradle.kts").write_bytes(b"dirty current source")
        self.produce()
        self.assertEqual(b"dirty current source", (self.root / "gradle/build-logic/build.gradle.kts").read_bytes())
        self._remove_output()
        for name in ("init.gradle", "init.gradle.kts", "gradle.properties"):
            (self.cache / name).write_bytes(b"external build injection")
            with self.assertRaisesRegex(ValueError, "external Gradle"):
                self.produce()
            (self.cache / name).unlink()
        with self.assertRaisesRegex(ValueError, "overlaps"):
            self.produce(output=self.root / "overlap")
