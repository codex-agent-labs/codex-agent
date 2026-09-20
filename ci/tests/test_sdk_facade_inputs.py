"""Real snapshot/ZIP/union boundaries; package/signature gates explicitly mocked.

These tests prove orchestration, not a genuine signed package or compilation.
Existing product tests own the cryptographic and package-semantic fixtures.
"""

from contextlib import redirect_stderr
from copy import deepcopy
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci.products import sdk_facade_inputs as inputs
from ci.products.contract import _write_contract_zip
from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, sha256_file
from ci.products.receipt import write_output_manifest
from ci.tests import test_sdk_facade_validation as fixtures
from ci.tests.product_chain_support import write_receipt


class FacadeInputsTest(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.FacadeValidationTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.root = self.f.root
        (self.f.package / "outputs/payload.bin").unlink()
        maven = self.f.package / "outputs/maven/io/github/codex-agent-labs/sdk.jar"
        maven.parent.mkdir(parents=True)
        maven.write_bytes(b"synthetic SDK package, mocked original admission")
        manifest = write_output_manifest(self.f.package, "sdk", "sdk-core", "package", "common", "0.8.7",
                                         {"maven": "outputs/maven"})
        self.receipt = self.root / "package.json"
        self.producer = {"repository": "fixture/repository", "workflowPath": None, "commit": "a" * 40,
            "tree": "b" * 40, "event": "local", "runId": None, "runAttempt": None, "pullRequest": None}
        write_receipt(self.receipt, product="sdk", component="sdk-core", phase="package", target="common",
            version="0.8.7", version_identity="0.8.7", outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
        self.package_value = load_canonical_json_bytes(self.receipt.read_bytes())
        self.binary_receipt = self.root / "binary.json"
        write_receipt(self.binary_receipt, product="sdk", component="sdk-core", phase="binary", target="common",
            version="0.8.7", version_identity="0.8.7", outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
        self.manifest = {"contractVersion": "0.8.2", "contractDigest": "sha256:" + "c" * 64,
            "components": {"jvm": {"sha256": "sha256:" + "d" * 64}}}
        self.payload_source = self.root / "payload-source"
        core = self.payload_source / "maven/io/github/codex-agent-labs/core.jar"
        core.parent.mkdir(parents=True)
        core.write_bytes(b"synthetic original Core bytes, mocked signed closure")
        (self.payload_source / "contract-manifest.json").write_bytes(canonical_json_bytes(self.manifest))
        self.payload = self.f.contract / "outputs/codex-agent-contract-0.8.2.zip"
        _write_contract_zip(self.payload_source, self.payload)
        write_output_manifest(self.f.contract, "contract", "contract", "metadata", "common", "0.8.2",
                              {"contract-bundle": "outputs"})
        self.projection = {**self.f.arguments["expected_contract_projection"], "bundleSha256": sha256_file(self.payload)}
        self.control = self.root / "control"
        self.control.mkdir()
        for name in ("metadata.json", "attestation.json", "signature.sig", "public.pub", "compatibility.json"):
            (self.control / name).write_bytes(b"{}\n")
        closure = self.control / inputs.CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        closure.mkdir()
        (closure / "fixture.txt").write_bytes(b"original closure mocked only at gate")
        self.evidence = {"stageRoot": str(self.f.contract), "phaseReceipt": str(self.control / "metadata.json"),
            "attestation": str(self.control / "attestation.json"), "attestationSignature": str(self.control / "signature.sig"),
            "publicKey": str(self.control / "public.pub"), "expectedTrustDomain": "development",
            "keyring": None, "keysDirectory": None}
        self.value = {"target": "jvm", "sdkVersion": "0.8.7", "runtimeVersion": "0.8.9", "contractVersion": "0.8.2",
            "repository": str(self.root), "packageStage": str(self.f.package), "packageReceipt": str(self.receipt),
            "binaryStage": str(self.f.package), "binaryReceipt": str(self.binary_receipt),
            "compatibilityRequest": str(self.control / "compatibility.json"),
            "binaryContractEvidence": deepcopy(self.evidence), "validationContractEvidence": deepcopy(self.evidence)}
        self.request = self.root / "request.json"
        self.request.write_bytes(canonical_json_bytes(self.value))
        self.destination = self.root / "prepared"
        self.enterContext(patch.object(inputs, "_request_inventory", side_effect=lambda request:
            {Path(request): sha256_file(Path(request))}))
        self.stage = self.enterContext(patch.object(inputs, "stage_sdk_inputs", side_effect=self.stage_inputs))
        self.loader = self.enterContext(patch.object(inputs, "load_sdk_compatibility_request", side_effect=self.load_inputs))
        self.package_gate = self.enterContext(patch.object(inputs, "verify_sdk_package_inputs", side_effect=self.verify_package))
        self.contract_gate = self.enterContext(patch.object(inputs, "_contract_projection_from_request",
            return_value=SimpleNamespace(receipt_value=lambda: deepcopy(self.projection))))
        self.bundle_gate = self.enterContext(patch.object(inputs, "verify_contract_bundle", side_effect=lambda path: deepcopy(self.manifest)))

    def stage_inputs(self, request, destination, *, request_directory):
        self.assertNotEqual(Path(request), Path(self.value["compatibilityRequest"]))
        self.assertEqual(Path(request).read_bytes(), Path(self.value["compatibilityRequest"]).read_bytes())
        self.assertEqual(self.control, request_directory)
        destination.mkdir()
        (destination / inputs.REQUEST_NAME).write_bytes(b"{}\n")
        (destination / inputs.COMPATIBILITY_NAME).write_bytes(canonical_json_bytes({
            "sdkVersion": "0.8.7", "contract": {"version": "0.8.2"}}))
        (destination / "runtime.json").write_bytes(canonical_json_bytes({"runtimeVersion": "0.8.9", "runtimeCompatibilityVersion": "0.8.0"}))
        (destination / self.payload.name).write_bytes(self.payload.read_bytes())

    def load_inputs(self, request):
        return {"runtime_manifest": request.parent / "runtime.json", "contract_payload": request.parent / self.payload.name,
                "required_trust_domain": "development"}

    def verify_package(self, repository, stage, receipt, request, **kwargs):
        self.assertEqual(self.root, repository)
        self.assertNotEqual(self.f.package, stage)
        self.assertEqual(self.package_value, load_canonical_json_bytes(receipt.read_bytes()))
        self.assertEqual(self.binary_receipt.read_bytes(), Path(kwargs["binary_receipt_path"]).read_bytes())
        self.assertNotEqual(str(self.f.contract), kwargs["binary_contract_evidence"]["stageRoot"])
        return deepcopy(self.package_value), receipt.read_bytes()

    def test_full_gates_precede_exact_union_and_preserve_original_bytes(self):
        before = regular_file_inventory(self.root, allow_empty=True)
        info = inputs.prepare_facade_validation_inputs(self.request, self.destination)
        self.package_gate.assert_called_once()
        self.contract_gate.assert_called_once()
        instance, versions, evidence = self.contract_gate.call_args.args
        self.assertEqual(("sdk", "sdk-core", "validation", "jvm"), tuple(getattr(instance, key) for key in ("product", "component", "phase", "target")))
        self.assertEqual("0.8.2", versions["contract"])
        self.assertNotEqual(str(self.f.contract), evidence["stageRoot"])
        self.assertEqual({"io/github/codex-agent-labs/sdk.jar", "io/github/codex-agent-labs/core.jar"},
                         {row["relativePath"] for row in regular_file_inventory(self.destination / "maven-repository")})
        self.assertEqual(info, load_canonical_json_bytes((self.destination / "inputs.json").read_bytes()))
        self.assertEqual(self.projection, info["contractProjection"])
        actual = [row for row in regular_file_inventory(self.root, allow_empty=True) if not row["relativePath"].startswith("prepared/")]
        self.assertEqual(before, actual)
        again = self.root / "again"
        inputs.prepare_facade_validation_inputs(self.request, again)
        self.assertEqual(regular_file_inventory(self.destination), regular_file_inventory(again))

    def test_either_authentication_failure_never_publishes(self):
        for gate in (self.package_gate, self.contract_gate):
            previous = gate.side_effect
            gate.side_effect = ValueError("original authentication failed")
            try:
                with self.subTest(gate=gate), self.assertRaisesRegex(ValueError, "authentication"):
                    inputs.prepare_facade_validation_inputs(self.request, self.destination)
                self.assertFalse(self.destination.exists())
            finally:
                gate.side_effect = previous

    def test_selected_contract_version_component_and_common_digest_mismatch_reject(self):
        for field in ("version", "component", "common"):
            selected = deepcopy(self.manifest)
            if field == "version": selected["contractVersion"] = "0.8.3"
            elif field == "common": selected["contractDigest"] = "sha256:" + "f" * 64
            else: selected["components"]["jvm"]["sha256"] = "sha256:" + "f" * 64
            self.bundle_gate.side_effect = [selected, deepcopy(self.manifest)]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "dependency version or target component"):
                inputs.prepare_facade_validation_inputs(self.request, self.destination)
            self.assertFalse(self.destination.exists())

    def test_overlap_existing_symlink_and_request_policy_shape_reject(self):
        for output in (self.f.package / "overlap", self.f.package, self.request):
            with self.subTest(output=output), self.assertRaises(ValueError):
                inputs.prepare_facade_validation_inputs(self.request, output)
        alias = self.root / "alias"
        alias.symlink_to(self.f.package, target_is_directory=True)
        with self.assertRaises(ValueError): inputs.prepare_facade_validation_inputs(self.request, alias / "child")
        for change in ({"target": "desktop"}, {"command": "untrusted"}, {"sdkVersion": "0.8.99"}):
            self.request.write_bytes(canonical_json_bytes({**self.value, **change}))
            with self.subTest(change=change), self.assertRaises(ValueError):
                inputs.prepare_facade_validation_inputs(self.request, self.destination)
            self.assertFalse(self.destination.exists())

    def test_late_original_and_private_mutations_reject_before_publication(self):
        for kind in ("original", "private", "policy"):
            original = self.receipt.read_bytes()
            def mutate(repository, stage, receipt, request, **kwargs):
                result = self.verify_package(repository, stage, receipt, request, **kwargs)
                if kind == "policy": self.request.write_bytes(b"{}\n")
                else: (self.receipt if kind == "original" else receipt).write_bytes(b"mutated\n")
                return result
            self.package_gate.side_effect = mutate
            try:
                with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "changed"):
                    inputs.prepare_facade_validation_inputs(self.request, self.destination)
                self.assertFalse(self.destination.exists())
            finally:
                self.receipt.write_bytes(original)
                self.request.write_bytes(canonical_json_bytes(self.value))

    def test_content_reauthenticates_prepared_tree_and_cli_has_disjoint_flags(self):
        inputs.prepare_facade_validation_inputs(self.request, self.destination)
        self.f.context["repositoryDirectory"] = str(self.destination / "maven-repository")
        self.f.capture("jvm")
        output = self.root / "content.json"
        arguments = dict(request=self.request, inputs=self.destination, evidence=self.f.evidence,
            gradle_wrapper=self.f.context["gradleWrapper"], consumer_directory=self.f.context["consumerDirectory"], output=output)
        content = inputs.write_facade_validation_content(**arguments)
        self.assertEqual(canonical_json_bytes(content), output.read_bytes())
        self.assertEqual(2, self.package_gate.call_count)
        (self.destination / "maven-repository/io/github/codex-agent-labs/sdk.jar").write_bytes(b"self-authored replacement")
        with self.assertRaisesRegex(ValueError, "reauthenticated"):
            inputs.write_facade_validation_content(**{**arguments, "output": self.root / "bad.json"})
        self.assertFalse((self.root / "bad.json").exists())
        for argv in (["prepare", "--request", str(self.request)],
                     ["prepare", "--request", str(self.request), "--destination", str(self.root / "x"), "--command", "false"],
                     ["content", "--request", str(self.request), "--destination", str(self.root / "x")]):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                inputs.main(argv)

    def test_content_publication_never_overwrites_a_late_arriving_file(self):
        inputs.prepare_facade_validation_inputs(self.request, self.destination)
        self.f.context["repositoryDirectory"] = str(self.destination / "maven-repository")
        self.f.capture("jvm")
        output = self.root / "content.json"
        link = inputs.os.link

        def competing_writer(source, destination, **kwargs):
            self.assertEqual(output, destination)
            output.write_bytes(b"independent writer must survive\n")
            return link(source, destination, **kwargs)

        with patch.object(inputs.os, "link", side_effect=competing_writer) as publication, \
                self.assertRaises(FileExistsError):
            inputs.write_facade_validation_content(request=self.request, inputs=self.destination,
                evidence=self.f.evidence, gradle_wrapper=self.f.context["gradleWrapper"],
                consumer_directory=self.f.context["consumerDirectory"], output=output)
        publication.assert_called_once()
        self.assertEqual(b"independent writer must survive\n", output.read_bytes())


if __name__ == "__main__":
    unittest.main()
