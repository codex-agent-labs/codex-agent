"""Fixed dependency preparation controls; no Gradle or product execution."""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
SPEC = importlib.util.spec_from_file_location("installed_dependencies",
    ROOT / ".github/actions/run-ci-lane/installed-consumer/dependencies.py")
dependencies = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dependencies)

from products.inventory import regular_file_inventory
from products.restore import verification_session


class InstalledConsumerDependenciesTest(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.directory).resolve()
        (self.root / "gradle/wrapper").mkdir(parents=True)
        (self.root / "gradlew").write_bytes(b"synthetic wrapper")
        (self.root / "gradle/wrapper/gradle-wrapper.properties").write_bytes(b"pinned wrapper")
        self.maven = self.root / "maven"
        self.component = self.maven / "io/github/codex-agent-labs/codex-agent/0.8.0"
        self.component.mkdir(parents=True)
        (self.component / "codex-agent-0.8.0.jar").write_bytes(b"native-bound product")
        (self.component / "codex-agent-0.8.0.module").write_text(json.dumps({
            "variants": [{"files": [{"name": "codex-agent.jar", "url": "codex-agent-0.8.0.jar"}]}]}))
        self.rows = regular_file_inventory(self.maven)
        self.blobs = {path: (ROOT / path).read_bytes() for path in (
            dependencies._POLICY, dependencies._TEMPLATE, dependencies._BASE_TEMPLATE, dependencies._SETTINGS,
            "runtime/gradle/verification-metadata.xml")}
        self.blobs.update({"gradlew": b"synthetic wrapper",
                           "gradle/wrapper/gradle-wrapper.properties": b"pinned wrapper"})
        self.git = self.enterContext(patch.object(dependencies, "git_regular_blob_bytes",
            side_effect=lambda root, revision, relative, **limits: self.blobs[relative]))
        self.run = self.enterContext(patch.object(dependencies.subprocess, "run",
            return_value=subprocess.CompletedProcess([], 0)))
        self.enterContext(verification_session())

    def prepare(self, target="common", **changes):
        arguments = dict(repository=self.root, revision="a" * 40, target=target,
            maven=self.maven, maven_inventory=self.rows, sdk_version="0.8.0", runtime_version="0.8.0",
            destination=self.root / "seed", environment={"JAVA_HOME": str(self.root)})
        arguments.update(changes)
        return dependencies.prepare_dependencies(**arguments)

    def test_selected_non_native_dependencies_only_without_compile_or_product_copy(self):
        for target in ("common", "android", "node-js", "node-wasm"):
            with self.subTest(target=target):
                output = self.root / target
                self.prepare(target, destination=output)
                command = self.run.call_args.args[0]
                self.assertIn("resolveInstalledConsumerDependencies", command)
                self.assertIn("--dependency-verification=strict", command)
                self.assertNotIn("--offline", command)
                self.assertNotIn("ciProductPhase", command)
                self.assertFalse(any(value.startswith("compile") for value in command))
                self.assertIn("-PCENTRAL_STAGING=" + str(self.maven), command)
                script = (output / "consumer/resolve.gradle").read_text()
                for name in dependencies._CONFIGURATIONS[target]:
                    self.assertIn('"' + name + '"', script)
                self.assertNotIn("RuntimeClasspath", script)
                self.assertNotIn("NpmAggregated", script)
                template = dependencies._TEMPLATE if target in {"node-js", "node-wasm"} else dependencies._BASE_TEMPLATE
                self.assertEqual(self.blobs[template], (output / "consumer/build.gradle.kts").read_bytes())
                self.assertNotIn("dependsOn", script)
                self.assertFalse((output / "consumer/src").exists())
                self.assertFalse((output / "consumer/maven").exists())
                self.assertFalse((output / "root-build").exists())
                self.assertEqual(self.rows, regular_file_inventory(self.maven))
                result = json.loads((output / "result.json").read_bytes())
                self.assertFalse(result["consumerCompiled"])
                self.assertEqual(0, result["productFilesCopied"])
                self.assertEqual(list(dependencies._CONFIGURATIONS[target]), result["configurations"])
                document = ET.fromstring((output / "consumer/gradle/verification-metadata.xml").read_bytes())
                aliases = [a for a in document.iter() if a.get("name") == "codex-agent.jar"]
                self.assertEqual(1, len(aliases))
                self.assertEqual(hashlib.sha256(b"native-bound product").hexdigest(), aliases[0][0].get("value"))
        self.assertEqual(4, self.run.call_count)

    def test_native_target_uses_only_pinned_host_distribution_and_target_configurations(self):
        with patch.object(dependencies.platform, "system", return_value="Darwin"), \
                patch.object(dependencies.platform, "machine", return_value="arm64"):
            self.prepare("ios-device")
        command = self.run.call_args.args[0]
        self.assertIn("-Pkotlin.native.distribution.type=prebuilt", command)
        script = (self.root / "seed/consumer/resolve.gradle").read_text()
        self.assertIn('"kotlinNativeBundleConfiguration"', script)
        self.assertIn('"iosArm64CompileKlibraries"', script)
        self.assertNotIn("iosSimulatorArm64", script)
        self.assertEqual(self.blobs[dependencies._BASE_TEMPLATE],
            (self.root / "seed/consumer/build.gradle.kts").read_bytes())
        self.assertIn("jvmRuntimeClasspath", dependencies._CONFIGURATIONS["desktop"])
        result = json.loads((self.root / "seed/result.json").read_bytes())
        self.assertEqual(dependencies._metadata_checksum(self.blobs[dependencies._POLICY],
            "kotlin-native-prebuilt-2.3.10-macos-aarch64.tar.gz"), result["nativeArchiveSha256"])

    def test_native_host_or_policy_mismatch_fails_before_execution(self):
        with patch.object(dependencies.platform, "system", return_value="Linux"):
            with self.assertRaisesRegex(ValueError, "elected macOS"):
                self.prepare("desktop")
        with patch.object(dependencies.platform, "system", return_value="Darwin"), \
                patch.object(dependencies.platform, "machine", return_value="arm64"):
            body = self.blobs["runtime/gradle/verification-metadata.xml"]
            digest = dependencies._metadata_checksum(body, "kotlin-native-prebuilt-2.3.10-macos-aarch64.tar.gz").removeprefix("sha256:")
            self.blobs["runtime/gradle/verification-metadata.xml"] = body.replace(digest.encode(), b"0" * 64)
            with self.assertRaisesRegex(ValueError, "between immutable policies"):
                self.prepare("desktop")
        self.run.assert_not_called()

    def test_untrusted_or_changed_input_rejected_without_seed(self):
        with self.assertRaisesRegex(ValueError, "exact target"):
            self.prepare("unregistered")
        with self.assertRaisesRegex(ValueError, "native-bound Maven inventory"):
            self.prepare(maven_inventory=[])
        self.blobs[dependencies._POLICY] = self.blobs[dependencies._POLICY].replace(
            b"<verify-metadata>true</verify-metadata>", b"<verify-metadata>false</verify-metadata>")
        with self.assertRaisesRegex(ValueError, "metadata verification"):
            self.prepare()
        self.run.assert_not_called()

    def test_module_alias_cannot_escape_or_introduce_unrecorded_product(self):
        for url in ("../untrusted.jar", "missing.jar"):
            with self.subTest(url=url):
                (self.component / "codex-agent-0.8.0.module").write_text(json.dumps({
                    "variants": [{"files": [{"name": "alias.jar", "url": url}]}]}))
                self.rows = regular_file_inventory(self.maven)
                with self.assertRaises(ValueError):
                    self.prepare()
        self.run.assert_not_called()

    def test_subprocess_failure_retains_log_and_no_success_record(self):
        self.run.return_value = subprocess.CompletedProcess([], 1)
        with self.assertRaisesRegex(ValueError, "Pinned installed dependency preparation failed"):
            self.prepare()
        self.assertTrue((self.root / "seed/gradle.log").is_file())
        self.assertFalse((self.root / "seed/result.json").exists())

    def test_equal_size_late_product_mutation_is_rejected_in_real_session(self):
        def mutate(*args, **kwargs):
            (self.component / "codex-agent-0.8.0.jar").write_bytes(b"mutated-bound input!")
            return subprocess.CompletedProcess([], 0)
        self.run.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "Maven inputs changed"):
            self.prepare()
        self.assertFalse((self.root / "seed/result.json").exists())

    def test_late_verification_policy_mutation_is_rejected(self):
        def mutate(*args, **kwargs):
            (self.root / "seed/consumer/gradle/verification-metadata.xml").write_text("untrusted")
            return subprocess.CompletedProcess([], 0)
        self.run.side_effect = mutate
        with self.assertRaisesRegex(ValueError, "execution controls changed"):
            self.prepare()
        self.assertFalse((self.root / "seed/result.json").exists())


if __name__ == "__main__":
    unittest.main()
