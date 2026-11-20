"""Small caller/lifetime fixtures; no product authentication or Java execution."""

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

CI_ROOT = Path(__file__).resolve().parents[1]
if str(CI_ROOT) not in sys.path:
    sys.path.insert(0, str(CI_ROOT))
import product_reuse as worker
from products import gradle_bootstrap, tooling
from products.inventory import write_canonical_json


class RuntimePackageExecutionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-package-caller-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "discovery").mkdir()
        self.destination = self.root / "build/worker"
        self.events = []
        self.owners = set()
        self.java = self.root / "java/bin" / ("java.exe" if worker.os.name == "nt" else "java")
        self.java.parent.mkdir(parents=True)
        self.java.write_bytes(b"synthetic caller Java, never executed")
        self.jar = self.root / "runtime-tooling.jar"
        self.jar.write_bytes(b"synthetic authenticated-scope sentinel")
        self.library = self.root / "gradle-library.jar"
        self.library.write_bytes(b"synthetic library-scope sentinel")
        self.wrapper = self.root / "gradle/wrapper/gradle-wrapper.properties"
        self.wrapper.parent.mkdir(parents=True)
        self.wrapper.write_bytes(b"exact source wrapper fixture\n")
        self.policy = {"evidence": str(self.root / "runtime-evidence"), "publicKey": str(self.root / "release.pub"),
                       "javaExecutable": str(self.java), "requiredTrustDomain": "release",
                       "keyring": str(self.root / "keyring.json"), "keysDirectory": str(self.root / "keys")}
        self.producer = {"commit": "c" * 40}
        self.state = SimpleNamespace(prior_ready_plans={}, producer=self.producer,
            expected_fixed={"versions": {"runtime-release": "0.8.0"}}, plan={"event": "pull_request"})
        self.replay = self.enterContext(mock.patch.object(worker, "_verified_product_state", return_value=self.state))
        self.enterContext(mock.patch.object(worker, "_runtime_worker_checkout"))
        self.environment = self.enterContext(mock.patch.object(worker, "_worker_process_environment", side_effect=lambda r,p,d,e:dict(e)))
        self.gradle = self.enterContext(mock.patch.object(worker, "_runtime_worker_environment", side_effect=AssertionError("no Gradle in P")))
        self.command = self.enterContext(mock.patch.object(worker, "_runtime_worker_command", side_effect=AssertionError("no Gradle command in P")))
        self.provision = self.enterContext(mock.patch.object(worker, "_provision_runtime_native_toolchain", side_effect=AssertionError("no compiler provisioning in P")))
        self.enterContext(mock.patch("native_wrappers.host_classifier", return_value="linux-x64"))
        self.enterContext(mock.patch.object(worker, "_prepare_runtime_phase", side_effect=self.prepare))
        self.enterContext(mock.patch.object(worker, "git_regular_blob_bytes", return_value=self.wrapper.read_bytes()))
        self.enterContext(mock.patch.object(gradle_bootstrap, "require_preprovisioned_gradle", return_value=self.root / "gradle-installation"))
        self.capture = self.enterContext(mock.patch.object(tooling, "verified_tooling_capture", side_effect=self.tool_owner))
        self.libraries = self.enterContext(mock.patch.object(gradle_bootstrap, "verified_runtime_package_libraries", side_effect=self.library_owner, create=True))
        self.native = self.enterContext(mock.patch("runtime_native_phase.execute_package", side_effect=self.operation, create=True))
        self.adapter = self.enterContext(mock.patch("runtime_adapter_phase.execute_package", side_effect=self.operation, create=True))
        self.finalize = self.enterContext(mock.patch.object(worker, "finalize_phase_object", side_effect=self.final_gate))
        self.late_tool_failure = False
        self.change_input = False
        self.change_java = False

    def prepare(self, state, identity, destination, *args):
        destination.mkdir(parents=True)
        write_canonical_json(destination / "inputs.json", {"original": "unchanged"})
        return {"from": "authenticated closure"}, {"from": "verified Contract"}

    @contextmanager
    def tool_owner(self, evidence, repository, key, **options):
        self.assertEqual("runtime-package", options["use"])
        self.assertEqual("release", options["required_trust_domain"])
        self.assertEqual(self.producer["commit"], options["policy_revision"])
        if evidence.name == "sdk-evidence":
            raise ValueError("wrong-purpose signed toolkit rejected by existing capture")
        self.events.append("tool-enter"); self.owners.add("tool")
        try:
            yield self.jar
        finally:
            self.events.append("tool-exit"); self.owners.remove("tool")
            if self.late_tool_failure:
                raise ValueError("late authenticated tooling mutation")

    @contextmanager
    def library_owner(self, repository, revision, installation, jar):
        self.assertIn("tool", self.owners)
        self.assertEqual(self.jar, jar)
        self.events.append("libraries-enter"); self.owners.add("libraries")
        try:
            yield (self.library,)
        finally:
            self.events.append("libraries-exit"); self.owners.remove("libraries")

    def operation(self, plan, properties, **options):
        self.events.append("operation")
        if plan["component"] in worker.NATIVE_TARGETS:
            self.assertEqual({"tool", "libraries"}, self.owners)
            self.assertEqual((self.library,), options["libraries"])
            self.assertEqual(self.jar, options["tooling_jar"])
            self.assertEqual(self.java, options["java_executable"])
        else:
            self.assertFalse(self.owners)
            self.assertNotIn("tooling_jar", options)
        stage = options["stage_root"]
        stage.mkdir(parents=True)
        (stage / "synthetic-output").write_bytes(b"only a mocked output gate fixture")
        if self.change_input:
            (self.destination / "inputs/inputs.json").write_bytes(b"changed")
        if self.change_java:
            self.java.write_bytes(b"changed")
        return {"command": [str(self.java), "RuntimePackageMain"] if plan["component"] in worker.NATIVE_TARGETS else [], "returnCode": 0}

    def final_gate(self, **options):
        self.events.append("output-gate")
        self.assertFalse(self.owners, "Producer owner exits precede receipt/object publication")
        destination = options["destination"]
        destination.mkdir(parents=True)
        (destination / "fixture.json").write_bytes(b"full gate fixture, not a product receipt\n")
        return {"fixture": True}

    def execute(self, component="macos-arm64", policy=True):
        instance = worker.PhaseInstanceId("runtime", component, "package", component)
        ready = {"schemaVersion": 1, "product": "runtime", "component": component, "phase": "package",
                 "target": component, "inputs": {}, "buildKey": "sha256:" + "a" * 64}
        self.state.prior_ready_plans = {instance: ready}
        return worker.execute_runtime_phase(self.root / "plan.json", self.root / "discovery", None,
            instance, self.destination, expected_build_key=ready["buildKey"], repository_root=self.root,
            environ={"JAVA_HOME": str(self.java.parents[1])},
            **({"runtime_package_tooling": self.policy} if policy else {}))

    def test_adapter_package_never_enters_gradle_tooling_or_compiler_boundary(self):
        self.assertEqual({"fixture": True}, self.execute("jvm", policy=False))
        self.assertEqual(["operation", "output-gate"], self.events)
        self.adapter.assert_called_once(); self.native.assert_not_called()
        self.capture.assert_not_called(); self.libraries.assert_not_called()
        self.gradle.assert_not_called(); self.command.assert_not_called(); self.provision.assert_not_called()
        self.assertTrue((self.destination / "package.log").is_file())
        self.assertFalse((self.destination / "gradle.log").exists())

    def test_native_keeps_both_scopes_through_execution_and_exits_before_publication(self):
        self.assertEqual({"fixture": True}, self.execute())
        self.assertEqual(["tool-enter", "libraries-enter", "operation", "libraries-exit", "tool-exit", "output-gate"], self.events)
        self.assertFalse(self.owners)
        self.native.assert_called_once(); self.adapter.assert_not_called()
        self.gradle.assert_not_called(); self.command.assert_not_called(); self.provision.assert_not_called()
        self.assertTrue((self.destination / "shard/fixture.json").is_file())

    def test_missing_package_authority_rejects_before_execution(self):
        with self.assertRaisesRegex(ValueError, "authenticated package tooling"):
            self.execute(policy=False)
        self.native.assert_not_called(); self.finalize.assert_not_called()
        self.capture.assert_not_called()

    def test_development_authority_and_wrong_signed_purpose_reject(self):
        self.policy["requiredTrustDomain"] = "development"
        with self.assertRaisesRegex(ValueError, "protected release"):
            with worker._runtime_package_tooling(self.root, self.producer["commit"], {}, self.policy):
                self.fail("development policy yielded")
        self.capture.assert_not_called()
        self.policy["requiredTrustDomain"] = "release"
        self.policy["evidence"] = str(self.root / "sdk-evidence")
        with self.assertRaisesRegex(ValueError, "wrong-purpose"):
            self.execute()
        self.native.assert_not_called(); self.finalize.assert_not_called()

    def test_late_original_input_mutation_fails_before_full_output_gate(self):
        self.change_input = True
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.execute()
        self.finalize.assert_not_called()
        self.assertFalse(self.owners)
        self.assertFalse((self.destination / "shard").exists())

    def test_late_tool_exit_failure_never_publishes_shard(self):
        self.late_tool_failure = True
        with self.assertRaisesRegex(ValueError, "late authenticated tooling"):
            self.execute()
        self.finalize.assert_not_called()
        self.assertFalse(self.owners)
        self.assertFalse((self.destination / "shard").exists())

    def test_late_java_mutation_never_publishes_shard(self):
        self.change_java = True
        with self.assertRaisesRegex(ValueError, "Java changed"):
            self.execute()
        self.finalize.assert_not_called()
        self.assertFalse(self.owners)
        self.assertFalse((self.destination / "shard").exists())


if __name__ == "__main__":
    unittest.main()
