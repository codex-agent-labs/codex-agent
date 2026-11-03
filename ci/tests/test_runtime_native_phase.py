"""Pure native argument mapping; callback sentinels are not artifact admission."""
import copy
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import runtime_native_phase
from products.registry import NATIVE_TARGETS, PHASE_INSTANCE_IDS
from products import contract_projection
from products.inventory import canonical_json_bytes, sha256_bytes, write_canonical_json
from products.receipt import compute_build_key, validate_receipt_inputs
from products.registry import PhaseInstanceId
from products.runtime_flags import load_runtime_binary_flags
from products.runtime_identity import verify_runtime_binary_plan
from products.selection import phase_git_inventory
from products.toolchain import PROFILE_SHAPES, PROFILE_TOOL_NAMES


REVISION = "1" * 40
FLAGS = "sha256:" + "2" * 64


class RuntimeNativePhaseTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="native-phase-properties-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def plan(self, component, phase):
        return {"schemaVersion": 1, "product": "runtime", "component": component,
                "phase": phase, "target": component, "buildKey": "sha256:" + "3" * 64,
                "inputs": {"flagsDigest": FLAGS}}

    def predecessor(self, component, phase, target):
        return {"stage": self.root / component / phase / "stage",
                "receiptPath": self.root / component / phase / "original-receipt.json",
                "receipt": {"schemaVersion": 1, "result": "success", "product": "runtime",
                            "component": component, "phase": phase, "target": target, "productVersion": "0.2.4"}}

    def output(self, component, phase, target, kind):
        self.assertEqual(component, target)
        return self.root / component / phase / "declared-original" / kind

    def report(self, component, target):
        self.assertEqual(component, target)
        return self.root / component / "validation" / "original-raw-report.json"

    def invoke(self, plan, **changes):
        return runtime_native_phase.properties(plan, **{
            "plan_path": self.root / "elected-plan.json", "revision": REVISION,
            "predecessor": self.predecessor, "output": self.output, "report": self.report,
            **changes,
        })

    def test_all_five_native_components_use_exact_existing_phase_properties(self):
        for component in NATIVE_TARGETS:
            for phase in ("binary", "package", "validation", "metadata"):
                with self.subTest(component=component, phase=phase):
                    predecessor = mock.Mock(side_effect=self.predecessor)
                    output = mock.Mock(side_effect=self.output)
                    report = mock.Mock(side_effect=self.report)
                    actual = self.invoke(self.plan(component, phase), predecessor=predecessor, output=output, report=report)
                    if phase == "binary":
                        expected = {"codexAgent.runtimeBinaryPlan": str(self.root / "elected-plan.json"),
                                    "codexAgent.runtimeBinaryFlagsDigest": FLAGS,
                                    "codexAgent.repositoryRevision": REVISION}
                        predecessor.assert_not_called()
                    elif phase in {"package", "validation"}:
                        previous = "binary" if phase == "package" else "package"
                        prefix = "runtimeBinary" if phase == "package" else "runtimePackage"
                        expected = {f"codexAgent.{prefix}Stage": str(self.root / component / previous / "stage"),
                                    f"codexAgent.{prefix}Version": "0.2.4"}
                        predecessor.assert_called_once_with(component, previous, component)
                    else:
                        expected = {
                            "codexAgent.runtimeVariantIdentity": str(self.output(component, "binary", component, "runtime-identity")),
                            "codexAgent.runtimeVariantCAbiArchive": str(self.output(component, "package", component, "c-abi")),
                            "codexAgent.runtimeVariantAppServerArchive": str(self.output(component, "package", component, "app-server")),
                            "codexAgent.runtimeVariantValidationEvidence": str(self.report(component, component)),
                            **{f"codexAgent.runtimeVariant{previous.title()}Receipt":
                               str(self.root / component / previous / "original-receipt.json")
                               for previous in ("binary", "package", "validation")},
                        }
                        self.assertEqual([mock.call(component, previous, component)
                                          for previous in ("binary", "package", "validation")], predecessor.call_args_list)
                        self.assertEqual([mock.call(component, "binary", component, "runtime-identity"),
                                          mock.call(component, "package", component, "c-abi"),
                                          mock.call(component, "package", component, "app-server")], output.call_args_list)
                        report.assert_called_once_with(component, component)
                    self.assertEqual(expected, actual)
                    if phase != "metadata":
                        output.assert_not_called()
                        report.assert_not_called()

    def test_wrong_phase_identity_schema_or_required_binary_fields_reject(self):
        original = self.plan("macos-arm64", "binary")
        for changes in ({"product": "sdk"}, {"component": "jvm", "target": "jvm"},
                        {"target": "macos-x64"}, {"phase": "aggregate"}, {"schemaVersion": True},
                        {"schemaVersion": 2}, {"buildKey": "wrong"}, {"inputs": []},
                        {"inputs": {}}, {"inputs": {"flagsDigest": "wrong"}}, {"extra": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.invoke({**original, **changes})
        for revision in ("HEAD", "1" * 39, "A" * 40, " " + REVISION):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                self.invoke(original, revision=revision)
        with self.assertRaises(ValueError):
            self.invoke(original, plan_path=Path("relative.json"))

    def test_missing_or_crosspaired_originals_never_fall_back_to_source_producers(self):
        plan = self.plan("linux-x64", "package")
        with self.assertRaisesRegex(ValueError, "missing original"):
            self.invoke(plan, predecessor=mock.Mock(side_effect=ValueError("missing original")))
        baseline = self.predecessor("linux-x64", "binary", "linux-x64")
        for field, value in (("product", "contract"), ("component", "macos-arm64"),
                             ("target", "macos-arm64"), ("phase", "package"),
                             ("result", "failure"), ("schemaVersion", True),
                             ("productVersion", "latest"), ("productVersion", "0.2.4+run.1")):
            changed = copy.deepcopy(baseline)
            changed["receipt"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.invoke(plan, predecessor=mock.Mock(return_value=changed))
        for field in ("stage", "receiptPath"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.invoke(plan, predecessor=mock.Mock(return_value={**baseline, field: Path("relative")}))

    def test_metadata_requires_original_declared_files_and_rejects_unsafe_path_values(self):
        plan = self.plan("windows-x64", "metadata")
        for bad in (None, "caller-string", Path("relative"), self.root / "child" / ".." / "original"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.invoke(plan, output=mock.Mock(return_value=bad))
            with self.subTest(report=bad), self.assertRaises(ValueError):
                self.invoke(plan, report=mock.Mock(return_value=bad))
        with self.assertRaisesRegex(ValueError, "missing original identity"):
            self.invoke(plan, output=mock.Mock(side_effect=ValueError("missing original identity")))
        self.assertNotIn("codexAgent.runtimePackageStage", self.invoke(plan))
        self.assertNotIn("codexAgent.desktopSupervisorDirectory", self.invoke(self.plan("linux-arm64", "binary")))

    def test_all_registry_native_routes_use_fixed_hosts_and_only_binary_profiles(self):
        hosts = {
            "macos-arm64": ("macos-26", "macOS", "ARM64"),
            "macos-x64": ("macos-26-intel", "macOS", "X64"),
            "linux-arm64": ("ubuntu-24.04-arm", "Linux", "ARM64"),
            "linux-x64": ("ubuntu-24.04", "Linux", "X64"),
            "windows-x64": ("windows-2025", "Windows", "X64"),
        }
        instances = [item for item in PHASE_INSTANCE_IDS
                     if item.product == "runtime" and item.component in NATIVE_TARGETS]
        self.assertEqual(20, len(instances))
        for instance in instances:
            with self.subTest(instance=instance):
                plan = self.plan(instance.component, instance.phase)
                before = copy.deepcopy(plan)
                route = runtime_native_phase.route(plan)
                host = instance.component if instance.phase in {"binary", "validation"} else "linux-x64"
                supervisor = None
                role = "builder" if instance.phase == "binary" else None
                if instance.component == "linux-arm64" and instance.phase == "binary":
                    host, role = "linux-x64", "cross-builder"
                    supervisor = {"runner": "ubuntu-24.04-arm", "runnerOs": "Linux",
                                  "runnerArch": "ARM64", "producerRole": "supervisor-builder"}
                label, os_name, arch = hosts[host]
                self.assertEqual({
                    "runner": label, "runnerOs": os_name, "runnerArch": arch,
                    "toolchainProfile": instance.component if instance.phase == "binary" else None,
                    "producerRole": role, "supervisor": supervisor,
                }, route)
                self.assertEqual(before, plan)

    def test_routing_rejects_other_registry_families_and_caller_control_fields(self):
        for instance in PHASE_INSTANCE_IDS:
            if instance.product == "runtime" and instance.component in NATIVE_TARGETS:
                continue
            plan = {**self.plan(instance.component, instance.phase),
                    "product": instance.product, "target": instance.target}
            with self.subTest(instance=instance), self.assertRaises(ValueError):
                runtime_native_phase.route(plan)
        plan = self.plan("linux-arm64", "binary")
        for extra in ("runner", "runnerOs", "runnerArch", "toolchainProfile", "producerRole", "supervisor"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                runtime_native_phase.route({**plan, extra: "caller-selected"})
        first = runtime_native_phase.route(plan)
        first["supervisor"]["runner"] = "caller-selected"
        self.assertEqual("ubuntu-24.04-arm", runtime_native_phase.route(plan)["supervisor"]["runner"])


class RuntimeNativeBinaryPlanTest(unittest.TestCase):
    """Real Git derivation; synthetic profiles/projections are not host or trust evidence."""

    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="native-worker-binary-plan-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name).resolve()
        checkout = Path(__file__).resolve().parents[2]
        abi = "codex-agent-runtime-desktop/native/c-api"
        for relative in (
            f"{abi}/abi-contract.json", f"{abi}/binary-flags.json",
            f"{abi}/include/codex_agent.h", f"{abi}/exports/macos.exports",
            f"{abi}/exports/linux.map", f"{abi}/exports/windows.def",
            "codex-agent-runtime-desktop/codex-app-server-distributions.json",
        ):
            destination = cls.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((checkout / relative).read_bytes())
        cls.profiles = {}
        for target in NATIVE_TARGETS:
            profile = cls.root / f"gradle/release/toolchains/runtime/{target}.json"
            write_canonical_json(profile, {
                "schemaVersion": 2, "id": target,
                "producers": [{
                    "role": role, "runner": {"os": os_name, "arch": arch},
                    "tools": [{"name": name, "identity": f"synthetic-{name}"}
                              for name in PROFILE_TOOL_NAMES[(target, role)]],
                } for role, os_name, arch in PROFILE_SHAPES[target]],
            })
            cls.profiles[target] = sha256_bytes(profile.read_bytes())
        def git(*arguments):
            return subprocess.run(["git", *arguments], cwd=cls.root, check=True,
                                  capture_output=True, text=True).stdout.strip()
        git("init", "-q")
        git("config", "user.email", "fixture@example.invalid")
        git("config", "user.name", "Synthetic native authority fixture")
        git("add", ".")
        git("commit", "-qm", "synthetic authorities; no observed host")
        cls.revision = git("rev-parse", "HEAD")
        cls.flags = load_runtime_binary_flags(cls.root / f"{abi}/binary-flags.json")
        cls.manifest = {
            "schemaVersion": 1, "product": "contract", "contractVersion": "0.2.0",
            "contractDigest": FLAGS, "canonicalApiDigest": FLAGS,
            "canonicalCoverageDigest": FLAGS, "protocolDigest": FLAGS, "capabilityCount": 1,
            "components": {target: {"mavenPaths": [f"maven/{target}"], "sha256": FLAGS}
                           for target in NATIVE_TARGETS}, "mavenFiles": [], "evidenceFiles": [],
        }

    def inputs(self, target):
        projection = contract_projection.VerifiedContractProjection({
            "schemaVersion": 1, "receiptSha256": FLAGS,
            "bundlePath": "outputs/codex-agent-contract-0.2.0.zip", "bundleSha256": FLAGS,
            "manifestSha256": sha256_bytes(canonical_json_bytes(self.manifest)),
            "contractVersion": "0.2.0", "contractDigest": FLAGS,
            "componentDigests": [{"component": target, "sha256": FLAGS}],
        }, contract_projection._VERIFIED)
        inventory = phase_git_inventory(self.root, self.revision, PhaseInstanceId("runtime", target, "binary", target))
        inputs = validate_receipt_inputs({
            "inventory": inventory, "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
            "versionIdentity": "0.2.0", "flagsDigest": self.flags[target].digest,
            "toolchainProfileDigest": self.profiles[target], "outputSchemaVersion": 1,
            "upstreamArtifacts": [{"product": "contract", "component": "contract", "phase": "metadata",
                                   "target": "common", "buildKey": FLAGS, "outputsDigest": FLAGS,
                                   "contractProjection": projection.receipt_value()}],
        })
        plan = {"schemaVersion": 1, "product": "runtime", "component": target,
                "phase": "binary", "target": target, "inputs": inputs}
        plan["buildKey"] = compute_build_key(product="runtime", component=target, phase="binary", target=target, inputs=inputs)
        return plan, {"repository_root": self.root, "revision": self.revision,
                      "contract_projection": projection, "verified_contract_manifest": self.manifest,
                      "runtime_version": "0.2.4"}

    def test_all_five_complete_plans_pass_the_real_settings_verifier_without_changing_election(self):
        for target in NATIVE_TARGETS:
            with self.subTest(target=target):
                plan, arguments = self.inputs(target)
                original = canonical_json_bytes(plan)
                with self.assertRaises(ValueError):
                    verify_runtime_binary_plan(self.root, self.revision, plan, self.manifest,
                                               expected_target=target, expected_runtime_version="0.2.4",
                                               expected_flags_digest=self.flags[target].digest)
                complete = runtime_native_phase.binary_plan(plan, **arguments)
                self.assertEqual(complete, runtime_native_phase.binary_plan(complete, **arguments))
                self.assertEqual(runtime_native_phase.route(plan), runtime_native_phase.route(complete))
                self.assertEqual(set(plan) | {"runtimeBinaryIdentity"}, set(complete))
                self.assertEqual(original, canonical_json_bytes(plan))
                self.assertEqual(plan, {key: complete[key] for key in plan})
                self.assertEqual(complete["runtimeBinaryIdentity"], verify_runtime_binary_plan(
                    self.root, self.revision, complete, self.manifest, expected_target=target,
                    expected_runtime_version="0.2.4", expected_flags_digest=self.flags[target].digest))
                self.assertEqual(plan["buildKey"], complete["runtimeBinaryIdentity"]["binaryBuildKey"])
                self.assertEqual("0.2.0", complete["runtimeBinaryIdentity"]["runtimeCompatibilityVersion"])
                self.assertNotIn("supervisor", complete)

    def test_wrong_projection_manifest_version_revision_phase_or_claimed_key_rejects(self):
        plan, arguments = self.inputs("macos-arm64")
        for changes in (
            {"contract_projection": arguments["contract_projection"].receipt_value()},
            {"contract_projection": self.inputs("macos-x64")[1]["contract_projection"]},
            {"verified_contract_manifest": {**self.manifest, "contractDigest": "sha256:" + "4" * 64}},
            {"runtime_version": "0.3.0"}, {"revision": "HEAD"}, {"revision": "0" * 40},
        ):
            with self.subTest(changes=changes), self.assertRaises((ValueError, subprocess.CalledProcessError)):
                runtime_native_phase.binary_plan(plan, **{**arguments, **changes})
        for changes in ({"phase": "package"}, {"buildKey": "sha256:" + "4" * 64},
                        {"runtimeBinaryIdentity": {}}, {"target": "macos-x64"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                runtime_native_phase.binary_plan({**plan, **changes}, **arguments)

    def test_coherent_wrong_flags_profile_and_changed_checkout_reject(self):
        plan, arguments = self.inputs("linux-arm64")
        for field in ("flagsDigest", "toolchainProfileDigest"):
            altered = copy.deepcopy(plan)
            altered["inputs"][field] = "sha256:" + "4" * 64
            altered["buildKey"] = compute_build_key(product="runtime", component="linux-arm64", phase="binary",
                                                     target="linux-arm64", inputs=altered["inputs"])
            with self.subTest(field=field), self.assertRaises(ValueError):
                runtime_native_phase.binary_plan(altered, **arguments)
        source = self.root / "codex-agent-runtime-desktop/native/c-api/include/codex_agent.h"
        original = source.read_bytes()
        try:
            source.write_bytes(original + b"\n/* unplanned checkout bytes */\n")
            with self.assertRaisesRegex(ValueError, "checkout bytes"):
                runtime_native_phase.binary_plan(plan, **arguments)
        finally:
            source.write_bytes(original)
