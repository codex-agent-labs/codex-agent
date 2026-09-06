"""Original-plan checks over signed synthetic products; no hosted execution claim."""

import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, run_git, snapshot_regular_tree
from ci.products.plan import (
    NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST,
    _contract_projection_from_request, plan_phase,
)
from ci.products.receipt import compute_build_key, validate_phase_receipt, write_output_manifest
from ci.products.registry import PhaseInstanceId, phase_instance_dependencies
from ci.products.sdk_maven import MAVEN_GROUPS, package_sdk_maven, verify_sdk_maven_binary_predecessor
from ci.products.sdk_archive import NPM_COMPATIBILITY_PATH, verify_npm_sdk_compatibility
from ci.products.sdk_package import (
    _capture_validation_sources, _verify_native_validation_stage, _verify_plan,
    verify_sdk_package_inputs, main as package_main,
)
from ci.products.selection import phase_git_inventory
from ci.tests import test_product_sdk_maven as maven_fixture
from ci.tests import test_product_sdk_native as native_fixture
from ci.tests import test_product_sdk_archive as javascript_fixture
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_native_chain import build_chain
from ci.tests.test_product_sdk_inputs import _request


VERSIONS = {"contract": "0.2.0", "sdk": "0.2.9", "runtime-release": "0.2.7",
            "runtime-compatibility": "0.2.0"}


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


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH signing tool unavailable")
class SdkPackagePlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-package-plan-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.chain = build_chain(cls.root / "selected-products", 71)
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
        cls.sdks = native_fixture.staged_sdks(cls.chain, cls.root / "sdks")
        helper = native_fixture.NativeSdkInputsTest()
        helper.chain, helper.sdks = cls.chain, cls.sdks
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
        result = plan_phase(instance, inventory=phase_git_inventory(cls.repository, cls.producer["commit"], instance),
                            versions=VERSIONS, upstream_receipts=selected,
                            toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                            flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, contract_projection=projection)
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

    def test_native_validation_original_plan_is_bound_without_granting_behavior_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            validation = self.validation_receipt(root)
            original = validation.read_bytes()
            package, package_bytes = verify_sdk_package_inputs(
                self.repository, self.native_stage, self.native_receipt, self.request,
                runtime_stage_root=self.chain["variants"]["stages"], staged_sdks=self.sdks,
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
            def fixture_handoff(arguments, runtime, sdks, prepared):
                (prepared / "receipts").mkdir(parents=True)

            source = self.repository / "codex-agent-bindings/csharp/parity/capability-claims.tsv"
            original_source = source.read_bytes()
            try:
                source.write_bytes(b"uncommitted wrong claims\n")
                with patch("ci.products.sdk_native._stage_native_capability_inputs", side_effect=fixture_handoff):
                    self.assertEqual(0, package_main(arguments))
                self.assertEqual(original_source, (output / "validation-source/capability-claims.tsv").read_bytes())
                self.assertEqual(b"// original synthetic program\n", (output / "validation-source/test-program-source").read_bytes())
                self.assertEqual(original, (output / "receipts/sdk-validation.json").read_bytes())
                self.assertEqual((stage / "output-manifest.json").read_bytes(),
                                 (output / "validation/output-manifest.json").read_bytes())
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
                                         staged_sdks=self.sdks)

    def native_cli_arguments(self):
        return ["verify-native", "--repository", str(self.repository), "--stage", str(self.native_stage),
                "--receipt", str(self.native_receipt), "--compatibility-request", str(self.request),
                "--runtime-stages", str(self.chain["variants"]["stages"]), "--staged-sdks", str(self.sdks),
                "--component", "csharp"]

    def test_native_cli_uses_complete_original_plan_without_rewriting_receipt(self):
        original = self.native_receipt.read_bytes()
        self.assertEqual(0, package_main(self.native_cli_arguments()))
        self.assertEqual(original, self.native_receipt.read_bytes())

    def test_native_capability_request_rejects_signed_lifecycle_only_predecessor(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary).resolve() / "capability-inputs"
            original = self.native_receipt.read_bytes()
            with self.assertRaisesRegex(ValueError, "full C ABI bootstrap closure"):
                package_main(self.native_cli_arguments() + ["--validation-inputs-output", str(output)])
            self.assertFalse(output.exists())
            self.assertEqual(original, self.native_receipt.read_bytes())

    def test_native_capability_output_cannot_mutate_original_input_trees(self):
        from ci.products.inventory import regular_file_inventory
        inputs = (self.chain["variants"]["stages"], self.sdks, self.native_stage)
        for original in inputs:
            before = regular_file_inventory(original)
            with self.subTest(original=original), self.assertRaisesRegex(ValueError, "overlaps an original input"):
                package_main(self.native_cli_arguments() + ["--validation-inputs-output", str(original / "new-handoff")])
            self.assertEqual(before, regular_file_inventory(original))

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
            with patch("ci.products.sdk_package.stage_sdk_inputs", side_effect=stage_captured), \
                    self.assertRaisesRegex(ValueError, "full C ABI bootstrap closure"):
                package_main(self.native_cli_arguments() + ["--validation-inputs-output", str(output)])
            self.assertEqual(original, self.request.read_bytes())
            self.assertFalse(output.exists())

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
