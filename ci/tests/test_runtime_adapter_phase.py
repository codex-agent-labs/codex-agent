"""Adapter property routing only: no compiled products or authentication claim."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


CI_ROOT = Path(__file__).resolve().parents[1]
if str(CI_ROOT) not in sys.path:
    sys.path.insert(0, str(CI_ROOT))

from runtime_adapter_phase import preflight, properties, route
from products.registry import NATIVE_TARGETS, PHASE_INSTANCE_IDS, RUNTIME_ADAPTERS, required_toolchain_profile
from products.runtime_evidence import PINNED_NODE_VERSION


class RuntimeAdapterPhaseTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.handoff = self.root / "validated-handoff"
        self.handoff.mkdir()
        self.calls = []

    def plan(self, component, phase, target=None):
        return {"product": "runtime", "component": component, "phase": phase,
                "target": component if target is None else target, "productVersion": "0.2.9"}

    def predecessor(self, component, phase, target):
        self.calls.append((component, phase, target))
        stage = self.root / f"{component}-{phase}-{target}"
        stage.mkdir(exist_ok=True)
        return {"stage": stage, "receiptPath": self.root / f"{stage.name}-receipt.json",
                "receipt": {"product": "runtime", "component": component, "phase": phase,
                            "target": target, "productVersion": "0.2.1" if component in RUNTIME_ADAPTERS else "0.2.3"}}

    def expected(self, component, phase, prefix, version="0.2.1"):
        return {f"codexAgent.{prefix}Stage": str(self.root / f"{component}-{phase}-{component}"),
                f"codexAgent.{prefix}Version": version}

    def test_routes_cover_every_adapter_phase_with_exact_existing_host_labels(self):
        hosts = {
            "linux-arm64": ("ubuntu-24.04-arm", "Linux", "ARM64"),
            "linux-x64": ("ubuntu-24.04", "Linux", "X64"),
            "macos-arm64": ("macos-26", "macOS", "ARM64"),
            "macos-x64": ("macos-26-intel", "macOS", "X64"),
            "windows-x64": ("windows-2025", "Windows", "X64"),
        }
        identities = [item for item in PHASE_INSTANCE_IDS
                      if item.product == "runtime" and item.component in RUNTIME_ADAPTERS]
        self.assertEqual(25, len(identities))
        for identity in identities:
            with self.subTest(identity=identity):
                host = identity.target if identity.phase == "validation" and identity.target in hosts else "linux-x64"
                runner, runner_os, runner_arch = hosts[host]
                self.assertIsNone(required_toolchain_profile(identity))
                self.assertEqual({"runner": runner, "runnerOs": runner_os, "runnerArch": runner_arch,
                                  "toolchainProfile": None, "producerRole": None, "supervisor": None},
                                 route(self.plan(identity.component, identity.phase, identity.target)))
        self.assertEqual([], self.calls)

    def test_route_does_not_accept_caller_runner_or_native_profile_overrides(self):
        plan = self.plan("node-wasm", "validation", "linux-arm64")
        expected = route(plan)
        plan.update(runner="arbitrary", runnerOs="Windows", runnerArch="X64",
                    toolchainProfile="linux-arm64", producerRole="cross-builder", supervisor={"runner": "arbitrary"})
        self.assertEqual(expected, route(plan))
        self.assertEqual("ARM64", expected["runnerArch"])
        self.assertIsNone(expected["supervisor"])
        self.assertEqual([], self.calls)

    def test_route_rejects_non_adapter_and_invalid_phase_targets(self):
        for plan in ({}, {**self.plan("jvm", "binary"), "product": "sdk"},
                     self.plan("linux-arm64", "binary"), self.plan("runtime-aggregate", "metadata"),
                     self.plan("node-js", "binary", "linux-x64"), self.plan("jvm", "metadata", "macos-x64"),
                     self.plan("jvm", "validation", "node-js-binding"),
                     self.plan("node-wasm", "validation", "node-wasm-binding"),
                     self.plan("node-js", "validation", "linuxX64"), self.plan("jvm", "unknown")):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                route(plan)

    def installed_node(self):
        node = self.root / ("node.exe" if os.name == "nt" else "node")
        node.write_bytes(b"not executed: subprocess boundary is mocked\n")
        node.chmod(0o755)
        return node

    def test_node_preflight_runs_only_required_phases_with_exact_command_and_explicit_environment(self):
        node = self.installed_node()
        environment = {"PATH": str(self.root), "PREFLIGHT_FIXTURE": "explicit-only"}
        result = subprocess.CompletedProcess([], 0, f"v{PINNED_NODE_VERSION}\r\n".encode("ascii"))
        for identity in PHASE_INSTANCE_IDS:
            if identity.product != "runtime" or identity.component not in RUNTIME_ADAPTERS:
                continue
            required = identity.component != "jvm" and identity.phase in {"binary", "validation"}
            with self.subTest(identity=identity), mock.patch("runtime_adapter_phase.subprocess.run", return_value=result) as run:
                observed = preflight(self.plan(identity.component, identity.phase, identity.target),
                                     repository_root=self.root, environ=environment)
                self.assertEqual({"nodeExecutable": str(node), "nodeVersion": PINNED_NODE_VERSION} if required else {}, observed)
                if required:
                    run.assert_called_once_with([str(node), "--version"], cwd=self.root, env=environment,
                                                check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
                else:
                    run.assert_not_called()
        self.assertEqual({"PATH": str(self.root), "PREFLIGHT_FIXTURE": "explicit-only"}, environment)

    def test_node_preflight_missing_version_failure_and_timeout_never_accept(self):
        plan = self.plan("node-js", "validation", "node-js-binding")
        with mock.patch("runtime_adapter_phase.subprocess.run") as run:
            with self.assertRaisesRegex(ValueError, "installed Node"):
                preflight(plan, repository_root=self.root, environ={"PATH": str(self.root / "missing")})
            with self.assertRaisesRegex(ValueError, "Unsupported Runtime adapter"):
                preflight(self.plan("jvm", "validation", "node-js-binding"), repository_root=self.root, environ={})
            run.assert_not_called()
        self.installed_node()
        for exit_code, output in ((0, b"v24.17.0\n"), (1, f"v{PINNED_NODE_VERSION}\n".encode()),
                                  (0, b""), (0, b"\xff\x00"), (0, b"v24.18.0\nextra\n")):
            with self.subTest(exit_code=exit_code, output=output), mock.patch(
                "runtime_adapter_phase.subprocess.run", return_value=subprocess.CompletedProcess([], exit_code, output),
            ), self.assertRaises(ValueError):
                preflight(plan, repository_root=self.root, environ={"PATH": str(self.root)})
        for error in (FileNotFoundError("node disappeared"), subprocess.TimeoutExpired(["node", "--version"], 30)):
            with self.subTest(error=type(error)), mock.patch("runtime_adapter_phase.subprocess.run", side_effect=error), \
                    self.assertRaises(type(error)):
                preflight(plan, repository_root=self.root, environ={"PATH": str(self.root)})

    def test_binary_and_package_preserve_original_versions_for_all_adapters(self):
        for component in RUNTIME_ADAPTERS:
            with self.subTest(component=component):
                self.calls.clear()
                self.assertEqual({}, properties(self.plan(component, "binary"), predecessor=self.predecessor))
                self.assertEqual([], self.calls)
                self.assertEqual(self.expected(component, "binary", "runtimeBinary"),
                                 properties(self.plan(component, "package"), predecessor=self.predecessor))
                self.assertEqual([(component, "binary", component)], self.calls)

    def test_host_validation_uses_original_adapter_and_native_versions_on_every_host(self):
        for component in RUNTIME_ADAPTERS:
            for host in NATIVE_TARGETS:
                with self.subTest(component=component, host=host):
                    self.calls.clear()
                    self.assertEqual({**self.expected(component, "package", "runtimePackage"),
                                      **self.expected(host, "package", "runtimeNativePackage", "0.2.3")},
                                     properties(self.plan(component, "validation", host), predecessor=self.predecessor))
                    self.assertEqual([(component, "package", component), (host, "package", host)], self.calls)

    def test_node_binding_imports_only_original_js_package(self):
        self.assertEqual(self.expected("node-js", "package", "runtimePackage"),
                         properties(self.plan("node-js", "validation", "node-js-binding"),
                                    predecessor=self.predecessor))
        self.assertEqual([("node-js", "package", "node-js")], self.calls)

    def test_metadata_imports_only_exact_validated_handoff_not_release_maven(self):
        for component in RUNTIME_ADAPTERS:
            with self.subTest(component=component):
                self.calls.clear()
                self.assertEqual({"codexAgent.runtimeValidationHandoff": str(self.handoff)},
                                 properties(self.plan(component, "metadata"), predecessor=self.predecessor,
                                            validation_handoff=self.handoff))
                self.assertEqual([], self.calls)

    def test_unsupported_routes_and_missing_or_misplaced_handoff_fail_before_predecessor(self):
        invalid = [{}, {**self.plan("jvm", "binary"), "product": "sdk"},
                   self.plan("linux-x64", "binary"), self.plan("runtime-aggregate", "metadata"),
                   self.plan("jvm", "unknown"), self.plan("jvm", "package", "node-js"),
                   self.plan("node-js", "validation"), self.plan("jvm", "validation", "node-js-binding"),
                   self.plan("node-wasm", "validation", "node-js-binding"),
                   self.plan("node-js", "validation", "linuxX64"), self.plan("jvm", "metadata")]
        for plan in invalid:
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                properties(plan, predecessor=self.predecessor)
        with self.assertRaises(ValueError):
            properties(self.plan("jvm", "binary"), predecessor=self.predecessor, validation_handoff=self.handoff)
        self.assertEqual([], self.calls)

    def test_wrong_original_receipt_identity_or_version_is_not_substituted(self):
        for field, value in (("product", "sdk"), ("component", "node-js"), ("phase", "validation"),
                             ("target", "linux-x64"), ("productVersion", "not-a-version")):
            def wrong(*identity):
                result = self.predecessor(*identity)
                result["receipt"][field] = value
                return result
            with self.subTest(field=field), self.assertRaises(ValueError):
                properties(self.plan("jvm", "package"), predecessor=wrong)

    def test_missing_relative_and_symbolic_directories_fail_without_creation(self):
        link = self.root / "linked-handoff"
        link.symlink_to(self.handoff, target_is_directory=True)
        file = self.root / "not-directory"
        file.write_bytes(b"sentinel")
        for path in (self.root / "absent", Path("relative"), link, file,
                     self.handoff / ".." / self.handoff.name):
            with self.subTest(path=path), self.assertRaises(ValueError):
                properties(self.plan("jvm", "metadata"), predecessor=self.predecessor, validation_handoff=path)
        self.assertEqual([], self.calls)
        self.assertFalse((self.root / "absent").exists())
        self.assertEqual(b"sentinel", file.read_bytes())
        def missing(*identity):
            return {**self.predecessor(*identity), "stage": self.root / "missing-original"}
        with self.assertRaises(ValueError):
            properties(self.plan("node-js", "package"), predecessor=missing)


class RuntimeAdapterPackageTest(unittest.TestCase):
    def setUp(self):
        from products.receipt import write_output_manifest
        self.temporary = tempfile.TemporaryDirectory(prefix="adapter-package-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repo = Path(__file__).resolve().parents[1]
        self.revision = "1" * 40
        self.write_manifest = write_output_manifest

    def fixture(self, component):
        original = self.root / component / "original"
        kinds = ["adapter", "publication", "validation-runner"]
        if component == "node-js":
            kinds.append("binding-test-runner")
        for kind in kinds:
            path = original / "outputs" / kind / "nested" / "artifact"
            path.parent.mkdir(parents=True)
            path.write_bytes((component + kind).encode())
        self.write_manifest(original, "runtime", component, "binary", component, "0.8.1",
                            {kind: "outputs/" + kind for kind in kinds})
        plan = {"product": "runtime", "component": component, "phase": "package", "target": component}
        props = {"codexAgent." + key: value for key, value in plan.items()}
        props.update({"codexAgent.candidateCommit": self.revision, "codexAgent.runtimeVersion": "0.8.9",
                      "codexAgent.runtimeBinaryVersion": "0.8.1", "codexAgent.runtimeBinaryStage": str(original),
                      "codexAgent.contractVersion": "0.8.0"})
        return plan, props, original, kinds

    def invoke(self, plan, props, stage, manifest=None):
        from runtime_adapter_phase import execute_package
        with mock.patch("runtime_adapter_phase.git_regular_blob_bytes", return_value=b"0.8.9\n"):
            return execute_package(plan, props, repository_root=self.repo, revision=self.revision,
                stage_root=stage, verified_contract_manifest=manifest or
                {"contractVersion": "0.8.0", "components": ["common", plan["component"]]})

    def test_all_three_packages_copy_exact_fixed_original_roots_without_child_process(self):
        from products.inventory import regular_file_inventory
        from products.receipt import verify_output_manifest_identity
        for component in RUNTIME_ADAPTERS:
            with self.subTest(component=component):
                plan, props, original, kinds = self.fixture(component)
                before = regular_file_inventory(original)
                stage = self.root / component / "package"
                with mock.patch("runtime_adapter_phase.subprocess.run", side_effect=AssertionError("no process")):
                    self.assertEqual({"command": [], "returnCode": 0}, self.invoke(plan, props, stage))
                manifest = verify_output_manifest_identity(stage, "runtime", component, "package", component, "0.8.9")
                self.assertEqual(set(kinds), {row["kind"] for row in manifest["outputs"]})
                self.assertEqual(before, regular_file_inventory(original))
                for kind in kinds:
                    self.assertEqual(regular_file_inventory(original / "outputs" / kind),
                                     regular_file_inventory(stage / "outputs" / kind))
                (stage / "outputs/adapter/nested/artifact").write_bytes(b"private output")
                self.assertEqual(before, regular_file_inventory(original))

    def test_contract_version_source_compatibility_and_original_integrity_fail_before_copy(self):
        plan, props, original, _ = self.fixture("jvm")
        cases = [({**plan, "phase": "binary"}, props, None),
                 (plan, {**props, "codexAgent.candidateCommit": "2" * 40}, None),
                 (plan, {**props, "codexAgent.runtimeVersion": "0.9.0"}, None),
                 (plan, {**props, "codexAgent.runtimeBinaryVersion": "0.7.1"}, None),
                 (plan, {**props, "codexAgent.runtimeBinaryVersion": "0.8.1+metadata"}, None),
                 (plan, props, {"contractVersion": "0.7.0", "components": ["common", "jvm"]}),
                 (plan, props, {"contractVersion": "0.8.0", "components": ["common"]})]
        for index, (selected, values, contract) in enumerate(cases):
            stage = self.root / f"rejected-{index}"
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.invoke(selected, values, stage, contract)
            self.assertFalse(stage.exists())
        (original / "outputs/adapter/nested/artifact").write_bytes(b"changed original")
        with self.assertRaises(ValueError):
            self.invoke(plan, props, self.root / "tampered")
        self.assertFalse((self.root / "tampered").exists())

    def test_symbolic_input_and_existing_output_reject_and_late_original_mutation_is_detected(self):
        from products.inventory import snapshot_regular_tree
        plan, props, original, _ = self.fixture("jvm")
        alias = self.root / "alias"
        alias.symlink_to(original, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.invoke(plan, {**props, "codexAgent.runtimeBinaryStage": str(alias)}, self.root / "alias-out")
        existing = self.root / "existing"
        existing.mkdir()
        (existing / "sentinel").write_bytes(b"preserve")
        with self.assertRaises(FileExistsError):
            self.invoke(plan, props, existing)
        self.assertEqual(b"preserve", (existing / "sentinel").read_bytes())
        def mutate(source, destination):
            snapshot_regular_tree(source, destination)
            (original / "outputs/adapter/nested/artifact").write_bytes(b"late mutation")
        with mock.patch("runtime_adapter_phase.snapshot_regular_tree", side_effect=mutate), self.assertRaises(ValueError):
            self.invoke(plan, props, self.root / "late-out")
        self.assertFalse((self.root / "late-out/output-manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
