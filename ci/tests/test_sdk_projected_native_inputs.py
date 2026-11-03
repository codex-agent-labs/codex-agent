"""Signed synthetic projected Runtime inputs; never hosted acceptance evidence."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.c_abi import C_ABI_PACKAGE_MANIFEST, C_ABI_STAGED_EVIDENCE_PATH, TARGET_SPECS, _json_bytes
from ci.products.contract_projection import verify_contract_component_projection
from ci.products.inventory import canonical_json_bytes, load_json_bytes, regular_file_inventory, sha256_bytes, snapshot_regular_tree
from ci.products.receipt import write_output_manifest
from ci.products.runtime_validation_projection import project_native_validation_stage
from ci.products.sdk_native import INDEX_NAME, verify_staged_native_sdk_inputs
from ci.products.sdk_runtime_content import verify_native_runtime_validation_content
from ci.tests.test_product_native_chain import build_chain
from ci.tests.test_product_sdk_inputs import _request
from ci.tests.test_product_sdk_native import SDK_ROOT


class ProjectedNativeSdkInputsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="sdk-projected-native-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()

        def projected_manifest(stage, product, component, phase, target, version, roots, **kwargs):
            result = write_output_manifest(stage, product, component, phase, target, version, roots, **kwargs)
            if phase != "validation":
                return result
            # Explicit synthetic execution, projected before receipts/signatures;
            # this never transforms existing accepted evidence.
            raw = load_json_bytes((stage / f"outputs/c-abi/c-abi-package-{target}.json").read_bytes())
            project_native_validation_stage(
                stage, stage.parent / "package", cls.root / "diagnostics" / target,
                target=target, version=version,
                producer={"commit": raw["producerCommit"], "tree": raw["producerTree"]},
            )
            return load_json_bytes((stage / "output-manifest.json").read_bytes())

        with patch("ci.tests.product_chain_variants.write_output_manifest", side_effect=projected_manifest):
            cls.chain = build_chain(cls.root / "products", 71, include_bootstrap=True)
        cls.request = cls.root / "request.json"
        cls.request.write_bytes(canonical_json_bytes(_request(cls.chain["compatibility_args"])))
        cls.sdks = cls.root / "sdks"
        cls.sdks.mkdir()
        compatibility = cls.chain["compatibility"].read_bytes()
        (cls.sdks / "sdk-compatibility.json").write_bytes(compatibility)
        (cls.sdks / "sdk-runtime-root.pub").write_bytes(SDK_ROOT.read_bytes())
        records = []
        for evidence_target, spec in sorted(TARGET_SPECS.items()):
            target = spec.classifier.removeprefix("c-abi-")
            snapshot_regular_tree(cls.chain["variants"]["raw_sdks"][target]["verified_sdk"], cls.sdks / target)
            evidence = (cls.chain["variants"]["stages"] / target / "validation/outputs/c-abi"
                        / f"c-abi-package-{target}.json").read_bytes()
            (cls.sdks / target / C_ABI_STAGED_EVIDENCE_PATH).write_bytes(evidence)
            report = load_json_bytes(evidence)
            producer = cls.chain["context"]["producer"]
            records.append({"target": evidence_target, "classifier": target,
                            "archiveSha256": report["archiveSha256"], "evidenceSha256": sha256_bytes(evidence)[7:],
                            "libraryPath": spec.library_path, "librarySha256": report["librarySha256"],
                            "manifestSha256": sha256_bytes((cls.sdks / target / C_ABI_PACKAGE_MANIFEST).read_bytes())[7:],
                            "producerCommit": producer["commit"], "producerTree": producer["tree"]})
        index = {"schemaVersion": 2, "libraryVersion": "0.2.0", "runtimeProductVersion": "0.2.7",
                 "sdkVersion": "0.2.9", "sdkCompatibilitySha256": sha256_bytes(compatibility)[7:],
                 "producerCommit": "9" * 40, "producerTree": "8" * 40, "targets": records}
        (cls.sdks / INDEX_NAME).write_bytes(_json_bytes(index))

    def test_five_target_staging_uses_original_receipt_producers(self):
        receipts = self.chain["variants"]["variant_phase_receipts"]
        before = {target: paths["validation"].read_bytes() for target, paths in receipts.items()}
        inventory = regular_file_inventory(self.sdks)
        index = verify_staged_native_sdk_inputs(
            self.sdks, self.request, self.chain["variants"]["stages"], SDK_ROOT.read_bytes(),
        )
        for record in index["targets"]:
            original = load_json_bytes(before[record["classifier"]])
            self.assertEqual(original["producer"]["commit"], record["producerCommit"])
            self.assertEqual(original["producer"]["tree"], record["producerTree"])
        self.assertEqual(before, {target: paths["validation"].read_bytes() for target, paths in receipts.items()})
        self.assertEqual(inventory, regular_file_inventory(self.sdks))

    def test_staging_cli_uses_the_shared_authenticated_projection_once(self):
        from ci.products import sdk_native
        from ci.products.sdk_compatibility import produce_sdk_compatibility
        destination = self.root / "produced-sdks"
        runtime = self.chain["variants"]["stages"]
        before = regular_file_inventory(runtime)
        argv = ["--output", str(destination), "--request", str(self.request),
                "--runtime-stage-root", str(runtime), "--root-key", str(SDK_ROOT),
                "--compatibility", str(self.chain["compatibility"]),
                "--library-version", "0.2.0", "--runtime-product-version", "0.2.7",
                "--sdk-version", "0.2.9", "--producer-commit", "9" * 40, "--producer-tree", "8" * 40]
        with patch.object(sdk_native, "produce_sdk_compatibility", wraps=produce_sdk_compatibility) as gate:
            self.assertEqual(0, sdk_native.main(argv))
            gate.assert_called_once()
        self.assertEqual(regular_file_inventory(self.sdks), regular_file_inventory(destination))
        self.assertEqual(before, regular_file_inventory(runtime))
        identity = {key: load_json_bytes((self.sdks / INDEX_NAME).read_bytes())[key]
                    for key in ("libraryVersion", "runtimeProductVersion", "sdkVersion", "producerCommit", "producerTree")}
        for case, output, compatibility in (
                ("overwrite", destination, self.chain["compatibility"].read_bytes()),
                ("overlap", runtime / "new-output", self.chain["compatibility"].read_bytes()),
                ("wrong compatibility", self.root / "wrong-output", b"{}\n")):
            with self.subTest(case=case), self.assertRaises(ValueError):
                sdk_native.stage_native_sdk_inputs(output, self.request, runtime, SDK_ROOT.read_bytes(),
                    identity=identity, expected_compatibility=compatibility)
        self.assertFalse((self.root / "wrong-output").exists())
        self.assertEqual(regular_file_inventory(self.sdks), regular_file_inventory(destination))

    def test_signed_projection_keeps_source_and_execution_checks(self):
        chain, target = self.chain, "linux-x64"
        contract = chain["contract"]
        projection = verify_contract_component_projection(
            contract["payload"].parent.parent, contract["receipt"], contract["attestation"],
            contract["signature"], chain["context"]["public_key"], expected_trust_domain="development",
            expected_contract_version="0.2.0", required_components=("common", target),
        )
        variants = chain["variants"]
        arguments = dict(
            target=target, runtime_stage_root=variants["stages"],
            phase_receipts=variants["variant_phase_receipts"][target],
            variant_payload=variants["variant_bundles"][target],
            attestation=variants["variant_attestations"][target],
            signature=variants["variant_attestation_signatures"][target],
            public_key=variants["variant_public_keys"][target], contract_projection=projection,
            contract_payload=contract["payload"], required_trust_domain="development",
        )
        content, receipt = verify_native_runtime_validation_content(**arguments)
        self.assertEqual(receipt, arguments["phase_receipts"]["validation"].read_bytes())
        self.assertEqual(2, content["cAbi"]["schemaVersion"])
        self.assertNotIn("producerCommit", content["cAbi"])
        with patch("ci.products.runtime_validation_projection.verify_projected_c_abi_evidence",
                   side_effect=ValueError("projected package gate")):
            with self.assertRaisesRegex(ValueError, "projected package gate"):
                verify_native_runtime_validation_content(**arguments)

    def test_receipt_changed_after_signed_admission_cannot_supply_producer(self):
        from ci.products.sdk_compatibility import produce_sdk_compatibility

        receipt = self.chain["variants"]["variant_phase_receipts"]["linux-x64"]["validation"]
        original = receipt.read_bytes()
        def replace_receipt(**arguments):
            result = produce_sdk_compatibility(**arguments)
            changed = load_json_bytes(original)
            changed["producer"]["commit"] = "f" * 40
            receipt.write_bytes(canonical_json_bytes(changed))
            return result
        try:
            with patch("ci.products.sdk_native.produce_sdk_compatibility", side_effect=replace_receipt):
                with self.assertRaisesRegex(ValueError, "receipts changed during authentication"):
                    verify_staged_native_sdk_inputs(
                        self.sdks, self.request, self.chain["variants"]["stages"], SDK_ROOT.read_bytes(),
                    )
        finally:
            receipt.write_bytes(original)

    def test_completed_facts_are_byte_identical_to_full_five_target_gate(self):
        from ci.products.native_runtime_inputs import _completed_native_content, completed_native_runtime_provider
        from ci.products.sdk_runtime_content import _native_contract_identity
        chain, variants = self.chain, self.chain["variants"]
        contract = chain["contract"]
        for target in variants["variant_phase_receipts"]:
            projection = verify_contract_component_projection(
                contract["payload"].parent.parent, contract["receipt"], contract["attestation"],
                contract["signature"], chain["context"]["public_key"], expected_trust_domain="development",
                expected_contract_version="0.2.0", required_components=("common", target))
            content, receipt = verify_native_runtime_validation_content(
                target=target, runtime_stage_root=variants["stages"],
                phase_receipts=variants["variant_phase_receipts"][target],
                variant_payload=variants["variant_bundles"][target],
                attestation=variants["variant_attestations"][target],
                signature=variants["variant_attestation_signatures"][target],
                public_key=variants["variant_public_keys"][target], contract_projection=projection,
                contract_payload=contract["payload"], required_trust_domain="development")
            with self.subTest(target=target):
                self.assertEqual(canonical_json_bytes(content), canonical_json_bytes(_completed_native_content(
                    target, load_json_bytes(receipt), _native_contract_identity(projection, target),
                    content["componentId"], variants["stages"] / target / "validation")))
        for fake in ({"completed": True}, object(), None):
            with self.assertRaisesRegex(TypeError, "concrete completed"):
                completed_native_runtime_provider(fake, {}, plan={}, producer={}, trusted_workflow_sha="", token="")

    def test_completed_provider_binds_originals_and_reads_each_target_once(self):
        """Mock native/upload authority only; real report hashes, schemas and projection."""
        from contextlib import ExitStack, contextmanager
        import copy
        import io
        import zipfile
        import product_reuse
        import reuse_qualification as native
        from products.native_runtime_inputs import completed_native_runtime_provider
        from products.registry import PhaseInstanceId
        from products.contract_projection import verify_contract_component_projection
        from runtime_reference_archive import copy_reference_member
        chain, variants = self.chain, self.chain["variants"]
        contract = chain["contract"]
        targets = tuple(sorted(variants["variant_phase_receipts"]))
        projection = verify_contract_component_projection(
            contract["payload"].parent.parent, contract["receipt"], contract["attestation"],
            contract["signature"], chain["context"]["public_key"], expected_trust_domain="development",
            expected_contract_version="0.2.0", required_components=("common", *targets))
        envelopes, inventories, archives = {}, {}, {}
        for target in targets:
            for phase, path in variants["variant_phase_receipts"][target].items():
                raw = path.read_bytes()
                envelopes[PhaseInstanceId("runtime", target, phase, target)] = {
                    "receipt": load_json_bytes(raw), "receiptBytes": raw, "receiptSha256": sha256_bytes(raw)}
            stage = variants["stages"] / target / "validation"
            prefix = f"inputs/predecessors/runtime-{target}-validation-{target}/stage/"
            inventories[target] = [{**row, "relativePath": prefix + row["relativePath"]}
                                   for row in regular_file_inventory(stage)]
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                for row in inventories[target]:
                    archive.writestr(row["relativePath"], (stage / row["relativePath"][len(prefix):]).read_bytes())
            archives[target] = buffer.getvalue()
        cap = object.__new__(native.CompletedFrozenReuse)
        request = {"repositoryRoot": str(self.root), "versions": {"runtime-release": "0.2.7"}}
        phase_rows = {key: {"identity": key} for key in envelopes}
        sources = [{"receipt": envelopes[key]["receipt"]} for key in envelopes if key.phase == "metadata"]
        binding = load_json_bytes(chain["compatibility_args"]["runtime_attestation"].read_bytes())

        def signed(spec, work, root, token):
            prefix = work / "signed/aggregate-input/codex-agent-runtime-0.2.7"
            prefix.parent.mkdir(parents=True)
            Path(str(prefix) + "-manifest.json").write_bytes(chain["aggregate"].read_bytes())
            Path(str(prefix) + ".attestation.json").write_bytes(canonical_json_bytes(binding))
            return 1

        @contextmanager
        def opened(artifact, token):
            with zipfile.ZipFile(io.BytesIO(archives[artifact])) as archive:
                yield archive, None

        with ExitStack() as stack:
            for method, replacement in {
                "check_request": lambda *_: None, "check_consumer": lambda *_: None,
                "_values": lambda *_: ({"requalification": {}}, phase_rows),
                "envelope": lambda _, row, *args: envelopes[row["identity"]],
                "runtime_sources": lambda *_: sources,
                "original_files": lambda _, locator, receipt: inventories[locator],
            }.items():
                stack.enter_context(patch.object(native.CompletedFrozenReuse, method, replacement))
            signed_gate = stack.enter_context(patch.object(native, "_requalified_signed_checkpoint", side_effect=signed))
            observed = stack.enter_context(patch.object(product_reuse, "_authenticate_runtime_original_reference_source",
                side_effect=lambda plan, producer, source, **kw: (source["receipt"]["target"], None,
                    [{"jobs": [{"name": "product-validation / runtime-" + source["receipt"]["target"] +
                        "-metadata-" + source["receipt"]["target"]}]}], "fixture")))
            stack.enter_context(patch.object(product_reuse, "_runtime_original_locator", side_effect=lambda artifact, *args: artifact))
            stack.enter_context(patch("runtime_reference_archive.open_reference_archive", side_effect=opened))
            copied = stack.enter_context(patch("runtime_reference_archive.copy_reference_member", wraps=copy_reference_member))
            make = lambda: completed_native_runtime_provider(cap, request, plan={}, producer={}, trusted_workflow_sha="", token="")
            selected = [envelopes[PhaseInstanceId("runtime", target, "validation", target)] for target in targets]
            provider = make()
            for language in ("python", "rust"):
                proofs = provider(PhaseInstanceId("sdk", language, "package", "desktop"), selected, projection)
                self.assertEqual(list(targets), [proof.target for proof in proofs])
            self.assertEqual(1, signed_gate.call_count)
            self.assertEqual(5, observed.call_count)
            self.assertEqual(11, copied.call_count)  # Two reports/target plus one bootstrap sidecar.
            # Separate planners in one private operation reuse the same full
            # signature/original gate; a later operation must authenticate afresh.
            from products.restore import verification_session
            keys = self.root / "gradle/release/keys"
            keys.mkdir(parents=True, exist_ok=True)
            keyring = keys.parent / "product-signing-keys.json"
            keyring.write_bytes(b"fixture caller key policy")
            (keys / "fixture.pub").write_bytes(b"fixture public key")
            with verification_session():
                for _ in range(3):
                    shared = make()
                    shared(PhaseInstanceId("sdk", "python", "package", "desktop"), selected, projection)
                self.assertEqual(2, signed_gate.call_count)
                self.assertEqual(10, observed.call_count)
                self.assertEqual(22, copied.call_count)
                keyring.write_bytes(b"changed fixture caller policy")
                with self.assertRaisesRegex(ValueError, "changed.*authority"):
                    shared(PhaseInstanceId("sdk", "python", "package", "desktop"), selected, projection)
            with self.assertRaisesRegex(ValueError, "outlived"):
                shared(PhaseInstanceId("sdk", "python", "package", "desktop"), selected, projection)
            changed = copy.deepcopy(selected)
            changed[0]["receiptSha256"] = "sha256:" + "0" * 64
            with self.assertRaisesRegex(ValueError, "selected original"):
                provider(PhaseInstanceId("sdk", "python", "package", "desktop"), changed, projection)
            binding["variants"][0]["phaseReceipts"]["validation"] = "sha256:" + "0" * 64
            with self.assertRaisesRegex(ValueError, "signed phase"):
                make()(PhaseInstanceId("sdk", "python", "package", "desktop"), selected, projection)
            binding = load_json_bytes(chain["compatibility_args"]["runtime_attestation"].read_bytes())
            member = next(row for row in inventories[targets[0]] if "/outputs/c-abi/c-abi-package-" in row["relativePath"])
            member["sha256"] = "sha256:" + "0" * 64
            with self.assertRaisesRegex(ValueError, "qualified original and receipt"):
                make()(PhaseInstanceId("sdk", "python", "package", "desktop"), selected, projection)


if __name__ == "__main__":
    unittest.main()
