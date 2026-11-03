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


if __name__ == "__main__":
    unittest.main()
