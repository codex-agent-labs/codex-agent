"""Original-plan checks over signed synthetic products; no hosted execution claim."""

import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes,
    publish_regular_tree as actual_publish_regular_tree, run_git, snapshot_regular_tree,
)
from ci.products.plan import (
    NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST,
    _contract_projection_from_request, plan_phase,
)
from ci.products.receipt import compute_build_key, output_inventory_digest, validate_phase_receipt, write_output_manifest
from ci.products.registry import PhaseInstanceId, phase_instance_dependencies
from ci.products.sdk_dotnet_toolchain import load_sdk_dotnet_profile_bytes
from ci.products.sdk_maven import MAVEN_GROUPS, package_sdk_maven, verify_sdk_maven_binary_predecessor
from ci.products.sdk_archive import NPM_COMPATIBILITY_PATH, verify_npm_sdk_compatibility
from ci.products.sdk_package import (
    _capture_validation_sources, _verify_native_validation_stage, _verify_plan,
    native_validation_content, native_metadata_content, verify_sdk_package_inputs, main as package_main,
)
from ci.products.selection import phase_git_inventory
from ci.tests import test_product_sdk_maven as maven_fixture
from ci.tests import test_product_sdk_native as native_fixture
from ci.tests import test_product_sdk_archive as javascript_fixture
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_csharp_restore_admission import execution as csharp_restore_execution
from ci.tests.test_product_native_chain import build_chain
from ci.tests.test_product_sdk_inputs import _request


VERSIONS = {"contract": "0.2.0", "sdk": "0.2.9", "runtime-release": "0.2.7",
            "runtime-compatibility": "0.2.0"}


class NativeMetadataContentTest(unittest.TestCase):
    """Strict deterministic join grammar, not a substitute for the full host gate."""

    def test_all_languages_join_exact_hosts_and_preserve_external_producers(self):
        from ci.products.registry import NATIVE_BINDINGS, NATIVE_TARGETS
        for component in NATIVE_BINDINGS:
            with self.subTest(component=component), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                contents = root / "contents"
                contents.mkdir()
                receipt = root / "package.json"
                producer = {"repository": "fixture/repository", "workflowPath": None, "commit": "a" * 40,
                            "tree": "b" * 40, "event": "local", "runId": None, "runAttempt": None, "pullRequest": None}
                outputs = [{"kind": "package", "relativePath": "outputs/package.zip", "bytes": 1,
                            "sha256": "sha256:" + "a" * 64}]
                def rebind():
                    write_receipt(receipt, product="sdk", component=component, phase="package", target="desktop",
                                  version="0.2.9", version_identity="0.2.9", upstream=[],
                                  context={"producer": producer}, outputs=outputs)
                rebind()
                names = ["claims.tsv", "compiler-evidence.tsv", "executed-tests.tsv", "installed.tsv", "test-program-source"]
                cases = []
                if component == "cpp":
                    names.append("package-negative-source.py")
                    cases = [{"caseId": case, "expectedExit": "zero" if case == "baseline" else "nonzero", "result": "passed"}
                             for case in sorted(("baseline", "tampered-0", "tampered-1", "tampered-2", "tampered-3",
                                                 "missing-sidecar", "missing-loader"))]
                values = {}
                for target in sorted(NATIVE_TARGETS):
                    values[target] = {"schemaVersion": 2, "kind": "sdk-native-validation-content", "component": component,
                        "packageOutputsDigest": output_inventory_digest(outputs),
                        "target": target, "sdkVersion": "0.2.9", **{key: "sha256:" + "b" * 64 for key in
                            ("contractDigest", "canonicalApiDigest", "canonicalCoverageDigest")},
                        "files": [{"relativePath": name, "bytes": 1, "sha256": "sha256:" + "c" * 64} for name in sorted(names)],
                        "packageNegativeCases": cases}
                    (contents / f"{target}.json").write_bytes(canonical_json_bytes(values[target]))
                before = receipt.read_bytes()
                first = canonical_json_bytes(native_metadata_content(contents, receipt, component))
                self.assertEqual(before, receipt.read_bytes())
                producer.update(commit="c" * 40, tree="d" * 40)
                rebind()
                self.assertNotEqual(before, receipt.read_bytes())
                self.assertEqual(first, canonical_json_bytes(native_metadata_content(contents, receipt, component)))
                outputs[0]["sha256"] = "sha256:" + "d" * 64
                rebind()
                with self.assertRaisesRegex(ValueError, "another exact package"):
                    native_metadata_content(contents, receipt, component)
                outputs[0]["sha256"] = "sha256:" + "a" * 64
                rebind()
                selected = contents / "linux-x64.json"
                original = values["linux-x64"]
                mutations = []
                for key, value in (("schemaVersion", True), ("component", "javascript"), ("target", "macos-x64"),
                                   ("schemaVersion", 1), ("packageOutputsDigest", "sha256:" + "d" * 64),
                                   ("sdkVersion", "0.2.8"), ("producer", producer), ("contractDigest", "sha256:" + "d" * 64),
                                   ("files", original["files"][:-1]), ("packageNegativeCases", [{"caseId": "fake"}])):
                    mutations.append({**original, key: value})
                mutations.append({**original, "files": [original["files"][0]] + original["files"]})
                for mutated in mutations:
                    selected.write_bytes(canonical_json_bytes(mutated))
                    with self.assertRaises(ValueError):
                        native_metadata_content(contents, receipt, component)
                selected.write_bytes(canonical_json_bytes(original))
                selected.rename(root / "missing-host.json")
                with self.assertRaises(ValueError):
                    native_metadata_content(contents, receipt, component)
                (root / "missing-host.json").rename(selected)
                (contents / "extra.json").write_bytes(b"{}\n")
                with self.assertRaises(ValueError):
                    native_metadata_content(contents, receipt, component)
                (contents / "extra.json").unlink()
                changed = copy.deepcopy(original)
                changed["files"][0]["sha256"] = "sha256:" + "d" * 64
                selected.write_bytes(canonical_json_bytes(changed))
                self.assertNotEqual(first, canonical_json_bytes(native_metadata_content(contents, receipt, component)))


class NativeValidationContentTest(unittest.TestCase):
    def test_content_excludes_run_receipt_compiled_and_cpp_exit_noise_but_retains_semantics(self):
        # Projection grammar/determinism fixture only, not bootstrap/host acceptance.
        for component in ("python", "csharp", "rust", "cpp", "dart"):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary).resolve()
                raw = root / "validation/outputs"
                originals = {
                    "contract/contract-manifest.json": canonical_json_bytes({key: "sha256:" + "a" * 64 for key in
                        ("contractDigest", "canonicalApiDigest", "canonicalCoverageDigest")}),
                    "validation-source/capability-claims.tsv": b"original claims fixture\n",
                    "validation-source/test-program-source": b"original source fixture\n",
                    "validation/outputs/capability/compiler-evidence.tsv": b"compiler evidence fixture\n",
                    "validation/outputs/capability/executed-tests.tsv": b"test\tpassed\n",
                    "validation/outputs/capability/test-program":
                        b"compiled program fixture\n" if component == "csharp" else b"original source fixture\n",
                    f"validation/outputs/installed/evidence/{component}/linux-x64.tsv": b"installed content fixture\n",
                    f"validation/outputs/installed/evidence/{component}/toolchain.tsv": b"tool\tversion\ncompiler\tfixture\n",
                    "validation/outputs/capability/raw.log": b"original run path/timing fixture\n",
                }
                if component == "csharp":
                    originals["validation/outputs/capability/dotnet-restore-execution.json"] = \
                        canonical_json_bytes(csharp_restore_execution("linux-x64"))
                if component == "cpp":
                    originals["validation-source/test_installed_package_tamper.py"] = b"original negative program\n"
                    cases = sorted(("baseline", "tampered-0", "tampered-1", "tampered-2", "tampered-3",
                                    "missing-sidecar", "missing-loader"))
                    originals["validation/outputs/package-negatives/package-tamper-results.tsv"] = (
                        "caseId\texpectedExit\tactualExitCode\tstatus\tlogPath\n" + "".join(
                            f"{case}\t{'zero' if case == 'baseline' else 'nonzero'}\t{0 if case == 'baseline' else 1}\tpassed\t{case}.log\n"
                            for case in cases)).encode()
                for relative, contents in originals.items():
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(contents)
                producer = {"repository": "fixture/repository", "workflowPath": None, "commit": "a" * 40,
                            "tree": "b" * 40, "event": "local", "runId": None, "runAttempt": None, "pullRequest": None}
                package = root / "receipts/sdk-package.json"
                write_receipt(package, product="sdk", component=component, phase="package", target="desktop",
                              version="0.2.9", version_identity="0.2.9", upstream=[], context={"producer": producer},
                              outputs=[{"kind": "package", "relativePath": "outputs/package.zip", "bytes": 1,
                                        "sha256": "sha256:" + "a" * 64}])
                roots = {"native-wrapper-installed": "outputs/installed", "native-wrapper-capability": "outputs/capability"}
                if component == "cpp":
                    roots["native-wrapper-package-negatives"] = "outputs/package-negatives"
                def rebind():
                    manifest = write_output_manifest(root / "validation", "sdk", component, "validation", "linux-x64", "0.2.9", roots)
                    write_receipt(root / "receipts/sdk-validation.json", product="sdk", component=component,
                                  phase="validation", target="linux-x64", version="0.2.9", version_identity="0.2.9",
                                  upstream=[], context={"producer": producer}, outputs=manifest["outputs"])
                rebind()
                first = canonical_json_bytes(native_validation_content(root, component, "linux-x64"))
                producer.update(commit="c" * 40, tree="d" * 40)
                (raw / "capability/raw.log").write_bytes(b"another run path/time\n")
                if component == "csharp":
                    (raw / "capability/test-program").write_bytes(b"different compiled execution envelope\n")
                    restore = csharp_restore_execution("linux-x64")
                    restore["stderrBase64"] = "cmF3Cg=="  # Exact retained raw bytes, not deterministic content.
                    (raw / "capability/dotnet-restore-execution.json").write_bytes(canonical_json_bytes(restore))
                (raw / f"installed/evidence/{component}/toolchain.tsv").write_bytes(b"different observed tool provenance\n")
                if component == "cpp":
                    table = raw / "package-negatives/package-tamper-results.tsv"
                    table.write_bytes(table.read_bytes().replace(b"\t1\tpassed", b"\t17\tpassed"))
                rebind()
                self.assertEqual(first, canonical_json_bytes(native_validation_content(root, component, "linux-x64")))
                for relative in ("validation-source/test-program-source", "validation-source/capability-claims.tsv",
                                 "validation/outputs/capability/compiler-evidence.tsv"):
                    path = root / relative
                    previous = path.read_bytes()
                    path.write_bytes(previous + b"meaningful input mutation\n")
                    if relative == "validation-source/test-program-source" and component != "csharp":
                        (raw / "capability/test-program").write_bytes(path.read_bytes())
                    rebind()
                    self.assertNotEqual(first, canonical_json_bytes(native_validation_content(root, component, "linux-x64")))
                    path.write_bytes(previous)
                    if relative == "validation-source/test-program-source" and component != "csharp":
                        (raw / "capability/test-program").write_bytes(previous)
                    rebind()
                with self.assertRaises(ValueError):
                    native_validation_content(root, component, "macos-arm64")
                if component == "cpp":
                    table = raw / "package-negatives/package-tamper-results.tsv"
                    original = table.read_bytes()
                    table.write_bytes(original.replace(b"baseline\tzero\t", b"baseline\tnonzero\t"))
                    rebind()
                    with self.assertRaisesRegex(ValueError, r"Unsuccessful C\+\+ negative content case"):
                        native_validation_content(root, component, "linux-x64")
                    table.write_bytes(original)
                    rebind()
                (raw / "capability/raw.log").write_bytes(b"unreceipted raw evidence\n")
                with self.assertRaises(ValueError):
                    native_validation_content(root, component, "linux-x64")


class NativeValidationStageInventoryTest(unittest.TestCase):
    def test_source_programs_bind_original_git_without_executing_or_rebuilding(self):
        programs = {"python": "tests/test_enum_parity.py", "csharp": "tests/CodexAgent.Tests/Program.cs",
                    "rust": "tests/enum_parity.rs", "cpp": "tests/value_parity_test.cpp",
                    "dart": "test/enum_parity_test.dart"}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            repo = root / "repository"
            repo.mkdir()
            run_git(repo, "init", "-q")
            for component, program in programs.items():
                for relative in (program, "parity/capability-claims.tsv", *(
                    ("tests/test_installed_package_tamper.py",) if component == "cpp" else ()
                )):
                    path = repo / "codex-agent-bindings" / component / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"original source; never execute\n")
            run_git(repo, "add", ".")
            run_git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@invalid",
                    "-c", "commit.gpgsign=false", "commit", "-qm", "original source")
            commit = run_git(repo, "rev-parse", "HEAD").strip()
            for component, program in programs.items():
                with self.subTest(component=component):
                    stage = root / component
                    raw = stage / "outputs/capability/test-program"
                    raw.parent.mkdir(parents=True)
                    raw.write_bytes(b"compiled DLL fixture\n" if component == "csharp" else b"original source; never execute\n")
                    (repo / "codex-agent-bindings" / component / program).write_bytes(b"uncommitted wrong source\n")
                    validation = {"component": component, "producer": {"commit": commit}}
                    output = root / (component + "-capture")
                    _capture_validation_sources(repo, validation, stage, output)
                    self.assertEqual(b"original source; never execute\n", (output / "validation-source/test-program-source").read_bytes())
                    if component == "cpp":
                        self.assertEqual(b"original source; never execute\n",
                                         (output / "validation-source/test_installed_package_tamper.py").read_bytes())
                    if component != "csharp":
                        raw.write_bytes(b"forged source program\n")
                        with self.assertRaisesRegex(ValueError, "original validation Git source"):
                            _capture_validation_sources(repo, validation, stage, root / (component + "-bad"))

    def test_exact_raw_kinds_paths_host_and_receipt_are_required(self):
        for component in ("python", "csharp", "rust", "cpp", "dart"):
            with self.subTest(component=component), tempfile.TemporaryDirectory() as temporary:
                stage = Path(temporary).resolve()
                roots = {"native-wrapper-installed": "outputs/installed",
                         "native-wrapper-capability": "outputs/capability"}
                if component == "cpp":
                    roots["native-wrapper-package-negatives"] = "outputs/package-negatives"
                for path in roots.values():
                    output = stage / path / "fixture.txt"
                    output.parent.mkdir(parents=True)
                    output.write_bytes(b"not semantic acceptance\n")
                if component == "csharp":
                    (stage / "outputs/capability/dotnet-restore-execution.json").write_bytes(
                        canonical_json_bytes(csharp_restore_execution("linux-x64")))
                manifest = write_output_manifest(stage, "sdk", component, "validation", "linux-x64", "0.2.9", roots)
                receipt = {**manifest}  # Only the narrow inventory checker is under test.
                _verify_native_validation_stage(stage, receipt, "linux-x64")
                for name in ("host", "receipt-output", "kind", "path", "extra", "symlink", "missing"):
                    with self.subTest(case=name):
                        snapshot = stage.parent / (stage.name + "-" + name)
                        try:
                            snapshot_regular_tree(stage, snapshot)
                            changed = copy.deepcopy(receipt)
                            if name == "host":
                                expected = "macos-arm64"
                            else:
                                expected = "linux-x64"
                            if name == "receipt-output":
                                changed["outputs"][0]["sha256"] = "sha256:" + "a" * 64
                            elif name in ("kind", "path"):
                                bad_roots = {**roots}
                                if name == "kind":
                                    bad_roots["wrong-kind"] = bad_roots.pop("native-wrapper-installed")
                                else:
                                    (snapshot / "outputs/installed").rename(snapshot / "outputs/wrong")
                                    bad_roots["native-wrapper-installed"] = "outputs/wrong"
                                changed = write_output_manifest(snapshot, "sdk", component, "validation",
                                                                "linux-x64", "0.2.9", bad_roots)
                            elif name == "extra":
                                (snapshot / "extra.txt").write_bytes(b"extra")
                            elif name == "symlink":
                                original = snapshot / "outputs/installed/fixture.txt"
                                original.unlink()
                                original.symlink_to(stage / "outputs/installed/fixture.txt")
                            elif name == "missing":
                                (snapshot / "outputs/installed/fixture.txt").unlink()
                            with self.assertRaises(ValueError):
                                _verify_native_validation_stage(snapshot, changed, expected)
                        finally:
                            shutil.rmtree(snapshot)


def contract_evidence(chain, root):
    contract = chain["contract"]
    payload = root / "outputs" / contract["payload"].name
    payload.parent.mkdir(parents=True)
    payload.write_bytes(contract["payload"].read_bytes())
    write_output_manifest(root, "contract", "contract", "metadata", "common", "0.2.0",
                          {"contract-bundle": "outputs"})
    return {"stageRoot": str(root), "phaseReceipt": str(contract["receipt"]),
            "attestation": str(contract["attestation"]),
            "attestationSignature": str(contract["signature"]),
            "publicKey": str(chain["context"]["public_key"]),
            "expectedTrustDomain": "development", "keyring": None, "keysDirectory": None}


def identity(receipt):
    return PhaseInstanceId(*(receipt[key] for key in ("product", "component", "phase", "target")))


requires_dotnet = unittest.skipUnless(shutil.which("dotnet"), ".NET SDK unavailable")


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class SdkPackagePlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-package-plan-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chain = build_chain(cls.root / "selected-products", 71, include_bootstrap=True)
        cls.older = build_chain(cls.root / "original-binary-contract", 72)
        cls.evidence = contract_evidence(cls.chain, cls.root / "contract-stage")
        cls.older_evidence = contract_evidence(cls.older, cls.root / "older-contract-stage")
        cls.request = cls.root / "request.json"
        cls.request.write_bytes(canonical_json_bytes(_request(cls.chain["compatibility_args"])))
        cls.repository = cls.root / "source-repository"
        cls.repository.mkdir()
        run_git(cls.repository, "init", "-q")
        for path, contents in {
            "gradle/release/versions/sdk.txt": "0.2.9\n",
            "codex-agent-bindings/csharp/fixture.cs": "// synthetic source input\n",
            "codex-agent-bindings/csharp/parity/capability-claims.tsv": "original synthetic claims\n",
            "codex-agent-bindings/csharp/tests/CodexAgent.Tests/Program.cs": "// original synthetic program\n",
            "codex-agent-runtime-android/fixture.kt": "// synthetic source input\n",
        }.items():
            output = cls.repository / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(contents)
        pinned_root = (Path(__file__).resolve().parents[2] /
                       "gradle/release/keys/sdk-runtime-root.pub").read_bytes()
        root_input = cls.repository / "gradle/release/keys/sdk-runtime-root.pub"
        root_input.parent.mkdir(parents=True, exist_ok=True)
        root_input.write_bytes(pinned_root)
        profile_path = "gradle/release/toolchains/sdk/csharp.json"
        profile_input = cls.repository / profile_path
        profile_input.parent.mkdir(parents=True, exist_ok=True)
        profile_input.write_bytes((Path(__file__).resolve().parents[2] / profile_path).read_bytes())
        run_git(cls.repository, "add", ".")
        run_git(cls.repository, "-c", "user.name=SDK fixture", "-c", "user.email=fixture@invalid",
                "-c", "commit.gpgsign=false", "commit", "-qm", "synthetic input fixture")
        cls.producer = {**cls.chain["context"]["producer"], "event": "local", "workflowPath": None,
                        "runId": None, "runAttempt": None, "pullRequest": None,
                        "commit": run_git(cls.repository, "rev-parse", "HEAD").strip(),
                        "tree": run_git(cls.repository, "rev-parse", "HEAD^{tree}").strip()}
        cls.upstream = {}
        for path in [cls.chain["contract"]["receipt"], cls.chain["aggregate_receipt"], *(
            path for phases in cls.chain["variants"]["variant_phase_receipts"].values() for path in phases.values()
        )]:
            value = load_canonical_json_bytes(path.read_bytes())
            cls.upstream[identity(value)] = value
        cls.projections = {}
        cls.native_projections = None
        cls.sdks = native_fixture.staged_sdks(cls.chain, cls.root / "sdks")
        helper = native_fixture.NativeSdkInputsTest()
        helper.chain, helper.sdks = cls.chain, cls.sdks
        helper.csharp_dll = (native_fixture.csharp_resource_fixture(
            cls.root, cls.chain["compatibility"].read_bytes(), pinned_root)
            if shutil.which("dotnet") else b"synthetic non-CLR plan fixture\n")
        cls.csharp_binary_stage = cls.root / "csharp-binary"
        binary_outputs = cls.csharp_binary_stage / "outputs/csharp"
        binary_outputs.mkdir(parents=True)
        for name, contents in {
            "CodexAgent.dll": helper.csharp_dll,
            "CodexAgent.pdb": b"synthetic PDB\n",
            "CodexAgent.xml": b"synthetic XML\n",
            "CodexAgent.deps.json": b"{}\n",
            "sdk-compatibility.json": cls.chain["compatibility"].read_bytes(),
            "sdk-runtime-root.pub": pinned_root,
        }.items():
            (binary_outputs / name).write_bytes(contents)
        binary_manifest = write_output_manifest(cls.csharp_binary_stage, "sdk", "csharp", "binary",
                                                "desktop", "0.2.9", {"csharp-binary": "outputs/csharp"})
        cls.csharp_binary_receipt = cls.root / "csharp-binary-receipt.json"
        write_receipt(cls.csharp_binary_receipt, product="sdk", component="csharp", phase="binary",
                      target="desktop", version="0.2.9", version_identity="0.2.9",
                      outputs=binary_manifest["outputs"], upstream=[], context={"producer": cls.producer})
        cls.bind(cls.csharp_binary_receipt, cls.upstream, cls.evidence)
        binary = load_canonical_json_bytes(cls.csharp_binary_receipt.read_bytes())
        cls.upstream[identity(binary)] = binary
        cls.native_stage, cls.native_receipt = helper.package(cls.root / "native")
        cls.bind(cls.native_receipt, cls.upstream, cls.evidence)

        component = "sdk-android"
        cls.binary_stage = cls.root / "binary"
        snapshot_regular_tree(maven_fixture._repository(cls.root, component, "0.2.9"),
                              cls.binary_stage / "outputs/maven")
        maven_fixture._write_binary_inventory(cls.binary_stage, component, "0.2.9")
        cls.maven_stage = cls.root / "maven"
        compatibility = cls.maven_stage / "outputs/evidence/sdk-compatibility.json"
        compatibility.parent.mkdir(parents=True)
        compatibility.write_bytes(cls.chain["compatibility"].read_bytes())
        package_sdk_maven(cls.binary_stage / "outputs/maven", cls.maven_stage / "outputs/maven",
                          compatibility, MAVEN_GROUPS[component], "0.2.9", component)
        for phase, stage in (("binary", cls.binary_stage), ("package", cls.maven_stage)):
            outputs = write_output_manifest(stage, "sdk", component, phase, "android", "0.2.9",
                                            {"maven": "outputs/maven", "evidence": "outputs/evidence"})["outputs"]
            receipt = cls.root / f"maven-{phase}-receipt.json"
            write_receipt(receipt, product="sdk", component=component, phase=phase, target="android",
                          version="0.2.9", version_identity="0.2.9", outputs=outputs, upstream=[],
                          context={"producer": cls.producer})
            if phase == "binary":
                original_contract = load_canonical_json_bytes(cls.older["contract"]["receipt"].read_bytes())
                cls.binary_receipt = receipt
                cls.bind(receipt, {identity(original_contract): original_contract}, cls.older_evidence)
            else:
                cls.maven_receipt = receipt
                binary = load_canonical_json_bytes(cls.binary_receipt.read_bytes())
                cls.bind(receipt, {**cls.upstream, identity(binary): binary}, cls.evidence)

        cls.node_stage = cls.chain["adapters"]["package_stages"]["node-js"]
        cls.node_receipt = next(record["receipt"] for record in cls.chain["adapters"]["adapter_receipts"]
                                if (record["component"], record["phase"], record["target"]) ==
                                ("node-js", "package", "node-js"))
        cls.javascript_stage = cls.root / "javascript"
        archive = cls.javascript_stage / "outputs/package/codex-agent-0.2.9.tgz"
        archive.parent.mkdir(parents=True)
        javascript_fixture._tar(archive, [
            (NPM_COMPATIBILITY_PATH, cls.chain["compatibility"].read_bytes()),
            ("package/package.json", b'{"name":"@codex-agent-labs/codex-agent","version":"0.2.9"}'),
            ("package/index.d.ts", b"export declare const reviewed: string;\n"),
            *((f"package/dist/{name}", (cls.node_stage / "outputs/adapter" / name).read_bytes())
              for name in ("runtime.js", "runtime.js.map")),
        ])
        compatibility = cls.javascript_stage / "outputs/evidence/sdk-compatibility.json"
        compatibility.parent.mkdir(parents=True)
        compatibility.write_bytes(cls.chain["compatibility"].read_bytes())
        verify_npm_sdk_compatibility(archive, compatibility,
                                     compatibility.with_name("sdk-compatibility-archive.json"), sdk_version="0.2.9")
        outputs = write_output_manifest(cls.javascript_stage, "sdk", "javascript", "package", "node", "0.2.9",
                                        {"package": "outputs/package", "evidence": "outputs/evidence"})["outputs"]
        cls.javascript_receipt = cls.root / "javascript-receipt.json"
        write_receipt(cls.javascript_receipt, product="sdk", component="javascript", phase="package", target="node",
                      version="0.2.9", version_identity="0.2.9", outputs=outputs, upstream=[],
                      context={"producer": cls.producer})
        node = load_canonical_json_bytes(cls.node_receipt.read_bytes())
        cls.bind(cls.javascript_receipt, {**cls.upstream, identity(node): node}, cls.evidence)

    @classmethod
    def bind(cls, path, upstream, evidence):
        receipt = load_canonical_json_bytes(path.read_bytes())
        instance = identity(receipt)
        projection = _contract_projection_from_request(instance, VERSIONS, evidence)
        selected = [upstream[item] for item in phase_instance_dependencies(instance)]
        from ci.products.plan import native_runtime_validation_dependencies
        from ci.products.sdk_runtime_content import verify_native_runtime_projection
        dependencies = native_runtime_validation_dependencies(instance)
        if dependencies and cls.native_projections is None:
            variants = cls.chain["variants"]
            cls.native_projections = tuple(verify_native_runtime_projection(
                target=item.target, runtime_stage_root=variants["stages"],
                phase_receipts=variants["variant_phase_receipts"][item.target],
                variant_payload=variants["variant_bundles"][item.target],
                attestation=variants["variant_attestations"][item.target],
                signature=variants["variant_attestation_signatures"][item.target],
                public_key=variants["variant_public_keys"][item.target],
                contract_projection=projection, contract_payload=cls.chain["contract"]["payload"],
                required_trust_domain="development",
            ) for item in dependencies)
        toolchain_digest = NOT_APPLICABLE_TOOLCHAIN_DIGEST
        if instance.component == "csharp" and instance.phase in {"binary", "package"}:
            profile = cls.repository / "gradle/release/toolchains/sdk/csharp.json"
            toolchain_digest = load_sdk_dotnet_profile_bytes(profile.read_bytes()).digest
        result = plan_phase(instance, inventory=phase_git_inventory(cls.repository, cls.producer["commit"], instance),
                            versions=VERSIONS, upstream_receipts=selected,
                            toolchain_profile_digest=toolchain_digest,
                            flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, contract_projection=projection,
                            native_runtime_projections=tuple(value for value in cls.native_projections if value.target in
                                {item.target for item in dependencies}) if dependencies else None)
        receipt.update(inputs=result["inputs"], buildKey=result["buildKey"], producer=cls.producer)
        path.write_bytes(canonical_json_bytes(validate_phase_receipt(receipt)))
        cls.projections[instance] = (selected, projection)

    def validation_receipt(self, root):
        # Original-plan fixture only: its output bytes are NOT full native proof.
        package = load_canonical_json_bytes(self.native_receipt.read_bytes())
        output = root / "outputs/fixture.txt"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"not behavior acceptance\n")
        manifest = write_output_manifest(root, "sdk", "csharp", "validation", "linux-x64", "0.2.9",
                                         {"fixture": "outputs"})
        receipt = root / "receipt.json"
        write_receipt(receipt, product="sdk", component="csharp", phase="validation", target="linux-x64",
                      version="0.2.9", version_identity="0.2.9", outputs=manifest["outputs"], upstream=[],
                      context={"producer": self.producer})
        self.bind(receipt, {**self.upstream, identity(package): package}, self.evidence)
        return receipt

    @requires_dotnet
    def test_native_validation_original_plan_is_bound_without_granting_behavior_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            validation = self.validation_receipt(root)
            original = validation.read_bytes()
            package, package_bytes = verify_sdk_package_inputs(
                self.repository, self.native_stage, self.native_receipt, self.request,
                runtime_stage_root=self.chain["variants"]["stages"], staged_sdks=self.sdks,
                binary_stage_root=self.csharp_binary_stage, binary_receipt_path=self.csharp_binary_receipt,
                validation_receipt_path=validation,
            )
            self.assertEqual("package", package["phase"])
            self.assertEqual(self.native_receipt.read_bytes(), package_bytes)
            self.assertEqual(original, validation.read_bytes())
            for name in ("coverage", "package", "source", "version", "component"):
                with self.subTest(name=name):
                    changed = load_canonical_json_bytes(original)
                    if name == "coverage":
                        contract = next(item for item in changed["inputs"]["upstreamArtifacts"]
                                        if item["product"] == "contract")
                        contract["contractProjection"]["canonicalCoverageDigest"] = "sha256:" + "e" * 64
                    elif name == "package":
                        predecessor = next(item for item in changed["inputs"]["upstreamArtifacts"]
                                           if item["product"] == "sdk")
                        predecessor["outputsDigest"] = "sha256:" + "e" * 64
                    elif name == "source":
                        changed["producer"]["tree"] = "e" * 40
                    elif name == "version":
                        changed["productVersion"] = "0.2.8"
                    else:
                        changed["component"] = "python"
                    changed["buildKey"] = compute_build_key(
                        product="sdk", component=changed["component"], phase="validation", target="linux-x64",
                        inputs=changed["inputs"],
                    )
                    validation.write_bytes(canonical_json_bytes(changed))
                    with self.assertRaises(ValueError):
                        package_main(self.native_cli_arguments() + ["--validation-receipt", str(validation)])
            validation.write_bytes(original)

    @requires_dotnet
    def test_validation_import_captures_original_stage_receipt_and_git_claims(self):
        # Only the raw capture seam is exercised: this fixture deliberately lacks
        # full bootstrap/behavior proof and cannot satisfy the Kotlin admission CLI.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            stage = root / "stage"
            for relative in ("installed/evidence.tsv", "capability/test-program"):
                path = stage / "outputs" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"synthetic raw execution output\n")
            restore_bytes = canonical_json_bytes(csharp_restore_execution("linux-x64"))
            (stage / "outputs/capability/dotnet-restore-execution.json").write_bytes(restore_bytes)
            manifest = write_output_manifest(stage, "sdk", "csharp", "validation", "linux-x64", "0.2.9", {
                "native-wrapper-installed": "outputs/installed",
                "native-wrapper-capability": "outputs/capability",
            })
            receipt = self.validation_receipt(root / "plan-fixture")
            value = load_canonical_json_bytes(receipt.read_bytes())
            value["outputs"] = manifest["outputs"]
            receipt.write_bytes(canonical_json_bytes(value))
            original = receipt.read_bytes()
            output = root / "captured"
            arguments = self.native_cli_arguments() + [
                "--validation-stage", str(stage), "--validation-receipt", str(receipt),
                "--validation-target", "linux-x64", "--validation-inputs-output", str(output),
            ]
            from ci.products.contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
            for protected in (
                self.chain["contract"]["attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY,
                self.chain["context"]["public_key"].parent,
            ):
                with self.subTest(protected=protected), self.assertRaisesRegex(ValueError, "overlaps an original input"):
                    package_main(arguments + ["--validation-content-output", str(protected / "new-content.json")])
                self.assertFalse(output.exists())
                self.assertFalse((protected / "new-content.json").exists())
            from ci.products.sdk_native import _stage_native_capability_inputs

            def fixture_handoff(arguments, runtime, sdks, prepared):
                _stage_native_capability_inputs(arguments, runtime, sdks, prepared)

            source = self.repository / "codex-agent-bindings/csharp/parity/capability-claims.tsv"
            original_source = source.read_bytes()
            try:
                source.write_bytes(b"uncommitted wrong claims\n")
                with patch("ci.products.sdk_native._stage_native_capability_inputs", side_effect=fixture_handoff):
                    self.assertEqual(0, package_main(arguments + ["--validation-content-output", str(root / "safe-content.json")]))
                self.assertEqual(original_source, (output / "validation-source/capability-claims.tsv").read_bytes())
                self.assertEqual(b"// original synthetic program\n", (output / "validation-source/test-program-source").read_bytes())
                self.assertEqual(original, (output / "receipts/sdk-validation.json").read_bytes())
                self.assertEqual((stage / "output-manifest.json").read_bytes(),
                                 (output / "validation/output-manifest.json").read_bytes())
                self.assertEqual(restore_bytes,
                    (output / "validation/outputs/capability/dotnet-restore-execution.json").read_bytes())
                self.assertEqual(original, receipt.read_bytes())
            finally:
                source.write_bytes(original_source)

            def mutated_handoff(*args):
                fixture_handoff(*args)
                (stage / "outputs/capability/test-program").write_bytes(b"mutated raw bytes\n")

            second = root / "second"
            with patch("ci.products.sdk_native._stage_native_capability_inputs", side_effect=mutated_handoff):
                with self.assertRaisesRegex(ValueError, "stage changed before publication"):
                    package_main(arguments[:-1] + [str(second)])
            self.assertFalse(second.exists())
            self.assertEqual(original, receipt.read_bytes())

    def verify_native(self, receipt=None):
        return verify_sdk_package_inputs(self.repository, self.native_stage, receipt or self.native_receipt,
                                         self.request, runtime_stage_root=self.chain["variants"]["stages"],
                                         staged_sdks=self.sdks, binary_stage_root=self.csharp_binary_stage,
                                         binary_receipt_path=self.csharp_binary_receipt)

    def native_cli_arguments(self):
        return ["verify-native", "--repository", str(self.repository), "--stage", str(self.native_stage),
                "--receipt", str(self.native_receipt), "--compatibility-request", str(self.request),
                "--runtime-stages", str(self.chain["variants"]["stages"]), "--staged-sdks", str(self.sdks),
                "--binary-stage", str(self.csharp_binary_stage),
                "--binary-receipt", str(self.csharp_binary_receipt),
                "--component", "csharp"]

    @requires_dotnet
    def test_native_cli_uses_complete_original_plan_without_rewriting_receipt(self):
        original = self.native_receipt.read_bytes()
        self.assertEqual(0, package_main(self.native_cli_arguments()))
        self.assertEqual(original, self.native_receipt.read_bytes())

    def test_plan_cli_requires_full_native_evidence_and_matches_original_receipt(self):
        from ci.products.plan import main as plan_main, native_runtime_validation_dependencies
        receipt = load_canonical_json_bytes(self.native_receipt.read_bytes())
        instance = identity(receipt)
        variants = self.chain["variants"]
        evidence = [{
            "target": item.target, "stageRoot": str(variants["stages"]),
            "phaseReceipts": {phase: str(path) for phase, path in variants["variant_phase_receipts"][item.target].items()},
            "payload": str(variants["variant_bundles"][item.target]),
            "attestation": str(variants["variant_attestations"][item.target]),
            "attestationSignature": str(variants["variant_attestation_signatures"][item.target]),
            "publicKey": str(variants["variant_public_keys"][item.target]),
            "keyring": None, "keysDirectory": None,
        } for item in native_runtime_validation_dependencies(instance)]
        request = {
            "schemaVersion": 1, **{key: receipt[key] for key in ("product", "component", "phase", "target")},
            "repositoryRoot": str(self.repository), "repositoryRevision": self.producer["commit"],
            "versions": VERSIONS, "upstreamReceipts": self.projections[instance][0],
            "contractEvidence": self.evidence, "runtimeValidationEvidence": None,
            "nativeRuntimeEvidence": evidence, "toolchainProfileDigest":
                load_sdk_dotnet_profile_bytes((self.repository / "gradle/release/toolchains/sdk/csharp.json").read_bytes()).digest,
            "flagsDigest": NOT_APPLICABLE_FLAGS_DIGEST, "outputSchemaVersion": 1,
        }
        original = self.native_receipt.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source, destination = root / "request.json", root / "plan.json"
            source.write_bytes(canonical_json_bytes(request))
            self.assertEqual(0, plan_main(["--request", str(source), "--output", str(destination)]))
            result = load_canonical_json_bytes(destination.read_bytes())
            self.assertEqual(receipt["inputs"], result["inputs"])
            self.assertEqual(receipt["buildKey"], result["buildKey"])
            for invalid in (None, evidence[:-1], list(reversed(evidence))):
                source.write_bytes(canonical_json_bytes({**request, "nativeRuntimeEvidence": invalid}))
                with patch("sys.stderr"), self.assertRaises(SystemExit) as failure:
                    plan_main(["--request", str(source), "--output", str(root / "rejected.json")])
                self.assertEqual(2, failure.exception.code)
                self.assertFalse((root / "rejected.json").exists())
        self.assertEqual(original, self.native_receipt.read_bytes())

    @requires_dotnet
    def test_native_capability_request_retains_full_signed_synthetic_closure(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / "capability-inputs"
            original = self.native_receipt.read_bytes()
            self.assertEqual(0, package_main(self.native_cli_arguments() + ["--validation-inputs-output", str(output)]))
            self.assertTrue((output / "bootstrap/bootstrap-content.json").is_file())
            # Byte/receipt closure only; synthetic claims do not establish Kotlin/host parity.
            self.assertEqual(original, self.native_receipt.read_bytes())

    @requires_dotnet
    def test_native_capability_pre_pin_and_late_copy_mutations_do_not_publish(self):
        from ci.products.sdk_native import _stage_native_capability_inputs
        from ci.products.sdk_inputs import INVENTORY_NAME, stage_sdk_inputs as actual_stage_sdk_inputs

        def mutate_handoff_before_join(request, destination, **kwargs):
            result = actual_stage_sdk_inputs(request, destination, **kwargs)
            manifest = Path(destination) / INVENTORY_NAME
            manifest.write_bytes(manifest.read_bytes() + b"changed before caller handoff join\n")
            return result

        def mutate_before_pin(arguments, runtime, sdks, prepared):
            _stage_native_capability_inputs(arguments, runtime, sdks, prepared)
            path = prepared / "contract/canonical-api.json"
            path.write_bytes(path.read_bytes() + b"changed after source verification\n")

        def mutate_before_copy(source, destination, **kwargs):
            path = Path(source) / "receipts/sdk-package.json"
            path.write_bytes(path.read_bytes() + b"changed after inventory check\n")
            actual_publish_regular_tree(source, destination, **kwargs)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            before_join, before_pin, before_copy = (root / name for name in
                                                   ("before-join", "before-pin", "before-copy"))
            with patch("ci.products.sdk_package.stage_sdk_inputs", side_effect=mutate_handoff_before_join), \
                    self.assertRaisesRegex(ValueError, "verified staging result"):
                package_main(self.native_cli_arguments() + ["--validation-inputs-output", str(before_join)])
            self.assertFalse(before_join.exists())
            with patch("ci.products.sdk_native._stage_native_capability_inputs",
                       side_effect=mutate_before_pin), \
                    self.assertRaisesRegex(ValueError, "authenticated source inventory"):
                package_main(self.native_cli_arguments() + ["--validation-inputs-output", str(before_pin)])
            self.assertFalse(before_pin.exists())
            with patch("ci.products.sdk_package.publish_regular_tree", side_effect=mutate_before_copy), \
                    self.assertRaisesRegex(ValueError, "pinned inventory"):
                package_main(self.native_cli_arguments() + ["--validation-inputs-output", str(before_copy)])
            self.assertFalse(before_copy.exists())

    def test_native_capability_output_cannot_mutate_original_input_trees(self):
        from ci.products.inventory import regular_file_inventory
        inputs = (self.chain["variants"]["stages"], self.sdks, self.native_stage)
        for original in inputs:
            before = regular_file_inventory(original)
            with self.subTest(original=original), self.assertRaisesRegex(ValueError, "overlaps an original input"):
                package_main(self.native_cli_arguments() + ["--validation-inputs-output", str(original / "new-handoff")])
            self.assertEqual(before, regular_file_inventory(original))

    @requires_dotnet
    def test_native_capability_handoff_uses_captured_request_during_source_swap(self):
        from ci.products.sdk_inputs import stage_sdk_inputs
        original = self.request.read_bytes()
        def stage_captured(request, output, **kwargs):
            self.assertNotEqual(request, self.request)
            self.assertEqual(original, Path(request).read_bytes())
            self.assertEqual(self.request.parent, kwargs["request_directory"])
            self.request.write_bytes(b"temporarily replaced untrusted request\n")
            try:
                return stage_sdk_inputs(request, output, **kwargs)
            finally:
                self.request.write_bytes(original)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / "capability-inputs"
            with patch("ci.products.sdk_package.stage_sdk_inputs", side_effect=stage_captured):
                self.assertEqual(0, package_main(self.native_cli_arguments() + ["--validation-inputs-output", str(output)]))
            self.assertEqual(original, self.request.read_bytes())
            self.assertTrue((output / "bootstrap/bootstrap-content.json").is_file())

    @requires_dotnet
    def test_native_cli_rejects_wrong_family_missing_inputs_and_changed_receipt(self):
        arguments = self.native_cli_arguments()
        with self.assertRaisesRegex(ValueError, "requested component"):
            package_main(arguments[:-1] + ["python"])
        with patch("sys.stderr"), self.assertRaises(SystemExit):
            package_main(arguments[:-2])
        forged = load_canonical_json_bytes(self.native_receipt.read_bytes())
        forged["producer"]["tree"] = "0" * 40
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "changed-receipt.json"
            path.write_bytes(canonical_json_bytes(forged))
            arguments[arguments.index("--receipt") + 1] = str(path)
            with self.assertRaisesRegex(ValueError, "commit/tree"):
                package_main(arguments)

    @requires_dotnet
    def test_native_complete_original_plan_and_dirty_working_copy(self):
        original = self.native_receipt.read_bytes()
        source = self.repository / "codex-agent-bindings/csharp/fixture.cs"
        contents = source.read_bytes()
        source.write_bytes(b"uncommitted content must not replace original Git blobs\n")
        try:
            value, raw = self.verify_native()
            self.assertEqual(raw, original)
            self.assertEqual(value["producer"], self.producer)
            self.assertEqual(self.native_receipt.read_bytes(), original)
        finally:
            source.write_bytes(contents)

    @requires_dotnet
    def test_original_package_uses_its_git_root_after_checkout_key_rotation(self):
        root = self.repository / "gradle/release/keys/sdk-runtime-root.pub"
        original = root.read_bytes()
        newer = self.chain["context"]["public_key"].read_bytes()
        self.assertNotEqual(original, newer)
        root.write_bytes(newer)
        try:
            package, receipt = self.verify_native()
            self.assertEqual("package", package["phase"])
            self.assertEqual(self.native_receipt.read_bytes(), receipt)
            self.assertEqual(newer, root.read_bytes())
        finally:
            root.write_bytes(original)

    def test_maven_binary_retains_older_contract_envelope_for_identical_content(self):
        self.assertEqual(self.chain["contract"]["payload"].read_bytes(), self.older["contract"]["payload"].read_bytes())
        self.assertNotEqual(self.chain["contract"]["receipt"].read_bytes(), self.older["contract"]["receipt"].read_bytes())
        originals = {path: path.read_bytes() for path in (self.binary_receipt, self.maven_receipt,
                     self.chain["contract"]["receipt"], self.older["contract"]["receipt"])}
        def swap_original_stage(*args):
            # A temporary live-source replacement must not change which package
            # the two independent leaf verifiers authenticate.
            self.assertNotEqual(Path(args[2]), self.maven_stage)
            self.assertNotEqual(Path(args[3]), self.maven_receipt)
            source = self.maven_stage / "outputs/evidence/sdk-compatibility.json"
            before = source.read_bytes()
            source.write_bytes(b"temporary untrusted replacement\n")
            self.maven_receipt.write_bytes(b"temporary untrusted receipt\n")
            try:
                return verify_sdk_maven_binary_predecessor(*args)
            finally:
                source.write_bytes(before)
                self.maven_receipt.write_bytes(originals[self.maven_receipt])
        with patch("ci.products.sdk_maven.verify_sdk_maven_binary_predecessor", side_effect=swap_original_stage):
            value, raw = verify_sdk_package_inputs(
                self.repository, self.maven_stage, self.maven_receipt, self.request,
                binary_stage_root=self.binary_stage, binary_receipt_path=self.binary_receipt,
                binary_contract_evidence=self.older_evidence,
            )
        self.assertEqual(raw, originals[self.maven_receipt])
        self.assertEqual(value["producer"], self.producer)
        self.assertTrue(all(path.read_bytes() == data for path, data in originals.items()))
        with self.assertRaises(ValueError):
            verify_sdk_package_inputs(
                self.repository, self.maven_stage, self.maven_receipt, self.request,
                binary_stage_root=self.binary_stage, binary_receipt_path=self.binary_receipt,
                binary_contract_evidence=self.evidence,
            )

    def test_rebound_self_consistent_input_claims_do_not_replace_original_plan(self):
        original = load_canonical_json_bytes(self.native_receipt.read_bytes())
        selected, projection = self.projections[identity(original)]
        for case in ("inventory", "flagsDigest", "toolchainProfileDigest", "outputSchemaVersion",
                     "upstream", "contract", "commit", "tree", "version"):
            with self.subTest(case=case):
                value = copy.deepcopy(original)
                inputs = value["inputs"]
                if case == "inventory":
                    from ci.products.inventory import sha256_bytes
                    inputs["inventory"] = []
                    inputs["phaseInputDigest"] = sha256_bytes(canonical_json_bytes([]))
                elif case in {"flagsDigest", "toolchainProfileDigest"}:
                    inputs[case] = "sha256:" + "7" * 64
                elif case == "outputSchemaVersion":
                    inputs[case] = 2
                elif case == "upstream":
                    inputs["upstreamArtifacts"].pop()
                elif case == "contract":
                    inputs["upstreamArtifacts"][0]["contractProjection"]["receiptSha256"] = "sha256:" + "7" * 64
                elif case in {"commit", "tree"}:
                    value["producer"][case] = "7" * 40
                else:
                    value["productVersion"] = inputs["versionIdentity"] = "0.2.10"
                value["buildKey"] = compute_build_key(**{key: value[key] for key in
                                                        ("product", "component", "phase", "target", "inputs")})
                if case == "outputSchemaVersion":
                    with self.assertRaisesRegex(ValueError, "Unsupported output schema"):
                        validate_phase_receipt(value)
                    continue
                validate_phase_receipt(value)
                with self.assertRaises(ValueError):
                    _verify_plan(self.repository, value, VERSIONS, selected, projection)

    def test_javascript_exact_aggregate_attested_node_receipt_and_original_plan(self):
        original = self.javascript_receipt.read_bytes()
        value, raw = verify_sdk_package_inputs(
            self.repository, self.javascript_stage, self.javascript_receipt, self.request,
            runtime_package_stage=self.node_stage, runtime_package_receipt=self.node_receipt,
        )
        self.assertEqual(raw, original)
        self.assertEqual(value["producer"], self.producer)
        self.assertEqual(original, self.javascript_receipt.read_bytes())
        # Same key/output content does not authorize substituting a producer's
        # original receipt in the aggregate's immutable attestation.
        wrong = load_canonical_json_bytes(self.node_receipt.read_bytes())
        wrong["producer"]["runId"] += 1
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "different-producer.json"
            path.write_bytes(canonical_json_bytes(validate_phase_receipt(wrong)))
            with self.assertRaisesRegex(ValueError, "authenticated Runtime aggregate"):
                verify_sdk_package_inputs(
                    self.repository, self.javascript_stage, self.javascript_receipt, self.request,
                    runtime_package_stage=self.node_stage, runtime_package_receipt=path,
                )

    @requires_dotnet
    def test_public_path_rejects_missing_upstream_and_wrong_family_inputs(self):
        value = load_canonical_json_bytes(self.native_receipt.read_bytes())
        value["inputs"]["upstreamArtifacts"].pop()
        value["buildKey"] = compute_build_key(**{key: value[key] for key in
                                                ("product", "component", "phase", "target", "inputs")})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "receipt.json"
            path.write_bytes(canonical_json_bytes(value))
            with self.assertRaisesRegex(ValueError, "original authenticated plan"):
                self.verify_native(path)
        with self.assertRaises(ValueError):
            verify_sdk_package_inputs(self.repository, self.native_stage, self.native_receipt, self.request)


if __name__ == "__main__":
    unittest.main()
