"""Build-free catalog round trips over real signed synthetic originals."""

from dataclasses import asdict, replace
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from ci.tests import test_runtime_aggregate_handoff as fixture
import product_reuse as transport
from products.index import IndexEntrySource, release_attested_runtime_aggregate_admission, write_signed_product_index
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from products.restore import object_relative_path, store_local_object
from products.reuse import LookupSession, RemoteCatalog, _dependency_closure, plan_reuse_wave
from products.registry import PhaseInstanceId, phase_instance_dependencies
from products.plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, native_runtime_validation_dependencies


class ReleaseCatalogAssemblyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.RuntimeAggregateHandoffTest.setUpClass()
        cls.addClassCleanup(fixture.RuntimeAggregateHandoffTest.doClassCleanups)
        original = fixture.RuntimeAggregateHandoffTest
        cls.source = original.source
        cls.carrier, cls.keyring, cls.keys = original.carrier, original.keyring, original.keys
        temporary = tempfile.TemporaryDirectory(prefix="catalog-originals-")
        cls.addClassCleanup(temporary.cleanup)
        cls.root = Path(temporary.name).resolve()
        cls.layout = cls.root / "layout"
        cls.layout.mkdir()
        receipt_path = cls.carrier / "aggregate-input/metadata-receipt.json"
        cls.raw = receipt_path.read_bytes()
        cls.receipt = load_canonical_json_bytes(cls.raw)
        manifest, arguments = cls.source.output_arguments()
        source = IndexEntrySource(cls.raw, cls.receipt["outputs"][0]["relativePath"])
        names = ("variant_bundles", "variant_phase_receipts", "variant_attestations",
                 "variant_attestation_signatures", "variant_public_keys", "variant_validation_evidence", "adapter_receipts")
        admission = release_attested_runtime_aggregate_admission(source,
            manifest=manifest, metadata_receipt=receipt_path,
            attestation=arguments["aggregate_attestation"], signature=arguments["aggregate_attestation_signature"],
            public_key=arguments["aggregate_public_key"], **{name: arguments[name] for name in names},
            keyring=cls.keyring, keys_directory=cls.keys, variant_keyring=cls.keyring, variant_keys_directory=cls.keys)
        cls.repository = cls.source.context["producer"]["repository"]
        write_signed_product_index([replace(source, release_admission=admission)], repository=cls.repository,
            context={"kind": "promoted-main", "commit": "c" * 40, "tree": "d" * 40,
                     "promotionRunId": 791, "promotionRunAttempt": 1},
            trust_domain="release", signing={**cls.source.context["signing"], "trustDomain": "release"},
            producer={**cls.source.context["producer"], "event": "push", "pullRequest": None,
                      "commit": "c" * 40, "tree": "d" * 40, "runId": 791, "runAttempt": 1},
            stable_history=None, private_key=cls.source.context["private_key"], public_key=cls.source.context["public_key"],
            manifest_path=cls.layout / "product-index.json")
        stage = cls.carrier / "selected-inputs/predecessors/runtime-runtime-aggregate-metadata-aggregate/stage"
        stored = store_local_object(stage, receipt_path, cls.root / "objects")
        cls.relative = object_relative_path(cls.receipt["buildKey"], stored["receiptSha256"])
        output = cls.layout / cls.relative
        output.parent.mkdir(parents=True)
        output.write_bytes(stored["path"].read_bytes())
        evidence = cls.layout / "runtime-aggregate-release-evidence"
        snapshot_regular_tree(cls.carrier, evidence / "handoffs/original", allow_empty=True)
        (evidence / "runtime-aggregate-release-evidence.json").write_bytes(canonical_json_bytes([
            {"receiptSha256": stored["receiptSha256"], "handoffRoot": "handoffs/original"}]))
        cls.before = regular_file_inventory(cls.layout, allow_empty=True)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="catalog-assembly-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()

    def stage(self, source=None, **changes):
        return transport.stage_release_catalog(self.layout if source is None else source, self.work / "emitted",
            **{"repository": self.repository, "source": "promoted-main", "keyring": self.keyring,
               "keys_directory": self.keys, **changes})

    def sdk_policy(self, default="0.2.7", *, phase_sources=False):
        repository = self.work / "sdk-policy"
        versions = repository / "gradle/release/versions"
        versions.mkdir(parents=True)
        (versions / "sdk.txt").write_bytes(b"0.2.9\n")
        # A Runtime-only patch must not change the SDK's selected dependency.
        (versions / "runtime.txt").write_bytes(b"0.2.8\n")
        (versions.parent / "sdk-default-runtime.txt").write_text(default + "\n", encoding="ascii")
        (versions.parent / "sdk-runtime-compatibility.json").write_bytes(canonical_json_bytes({
            "compatibleReleaseRange": ">=0.2.0 <0.3.0",
            "compatibleRuntimeCompatibilityRange": ">=0.2.0 <0.3.0"}))
        if phase_sources:
            for module in ("codex-agent-core", "codex-agent"):
                source = repository / module / "src/commonMain/kotlin/example.kt"
                source.parent.mkdir(parents=True)
                source.write_bytes(b"package synthetic\n")
        def git(*arguments):
            return subprocess.run(["git", *arguments], cwd=repository, check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()
        git("init", "-q")
        git("config", "user.name", "Synthetic SDK Selection")
        git("config", "user.email", "sdk-selection@example.invalid")
        git("add", "-A")
        git("commit", "-qm", "original synthetic SDK selection")
        return repository, git("rev-parse", "HEAD")

    def sdk_session(self, layout=None, *, include_carrier=True):
        layout = self.layout if layout is None else layout
        return LookupSession(repository=self.repository, pull_request=None,
            promoted_main=RemoteCatalog(layout / "product-index.json", layout / "product-index.sig",
                {self.receipt["buildKey"]: layout / self.relative}, keyring=self.keyring, keys_directory=self.keys),
            runtime_aggregate_evidence=({transport.sha256_bytes(self.raw):
                layout / "runtime-aggregate-release-evidence/handoffs/original"} if include_carrier else {}))

    def test_sdk_default_elects_original_release_not_current_runtime_patch(self):
        repository, revision = self.sdk_policy()
        policy_before = regular_file_inventory(repository / "gradle")
        session = self.sdk_session()
        identity = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        with patch("reuse.api_request", side_effect=AssertionError("SDK selection contacted CI")), \
                patch("products.index.sign_manifest", side_effect=AssertionError("SDK selection signed")):
            with session.sdk_default_runtime(repository_root=repository, repository_revision=revision,
                                             sdk_version="0.2.9") as selected:
                self.assertEqual(self.raw, selected["envelope"]["receiptBytes"])
                self.assertEqual("0.2.7", selected["envelope"]["receipt"]["productVersion"])
                self.assertEqual("promoted-main", selected["transportSource"]["kind"])
                self.assertEqual(self.raw, selected["handoff"]["receiptBytes"][identity])
                captured = selected["handoff"]["directory"]
                self.assertNotEqual(self.carrier, captured)
                self.assertEqual(regular_file_inventory(self.carrier, allow_empty=True),
                                 regular_file_inventory(captured, allow_empty=True))
            self.assertFalse(captured.exists())
        self.assertEqual(policy_before, regular_file_inventory(repository / "gradle"))
        self.assertEqual(self.before, regular_file_inventory(self.layout, allow_empty=True))

    def test_sdk_default_missing_exact_release_and_wrong_sdk_version_reject(self):
        repository, revision = self.sdk_policy(default="0.2.8")
        session = self.sdk_session()
        with self.assertRaisesRegex(ValueError, "Authenticated SDK default Runtime is unavailable"):
            with session.sdk_default_runtime(repository_root=repository, repository_revision=revision,
                                             sdk_version="0.2.9"):
                self.fail("A different released Runtime was selected")
        with self.assertRaisesRegex(ValueError, "original SDK version"):
            with session.sdk_default_runtime(repository_root=repository, repository_revision=revision,
                                             sdk_version="0.2.10"):
                self.fail("A caller SDK version replaced original Git policy")
        self.assertEqual(self.before, regular_file_inventory(self.layout, allow_empty=True))

    def test_sdk_default_requires_full_carrier_and_untampered_original_object(self):
        repository, revision = self.sdk_policy()
        with self.assertRaisesRegex(ValueError, "Authenticated SDK default Runtime is unavailable"):
            with self.sdk_session(include_carrier=False).sdk_default_runtime(
                    repository_root=repository, repository_revision=revision, sdk_version="0.2.9"):
                self.fail("An index and object alone substituted for full original evidence")
        copied = self.work / "tampered-catalog"
        snapshot_regular_tree(self.layout, copied, allow_empty=True)
        session = self.sdk_session(copied)
        # Tamper after the real signed catalog has been admitted, before selection.
        (copied / self.relative).write_bytes(b"not the original immutable object\n")
        with self.assertRaises(ValueError):
            with session.sdk_default_runtime(repository_root=repository, repository_revision=revision,
                                             sdk_version="0.2.9"):
                self.fail("A signed index authorized different original object bytes")
        self.assertEqual(self.before, regular_file_inventory(self.layout, allow_empty=True))

    def sdk_wave_request(self, requested=None):
        repository, revision = self.sdk_policy(phase_sources=True)
        artifacts = self.work / "wave-artifacts"
        snapshot_regular_tree(self.layout, artifacts / "catalog", allow_empty=True)
        snapshot_regular_tree(self.keys, artifacts / "policy/keys")
        (artifacts / "policy/keyring.json").write_bytes(self.keyring.read_bytes())
        requested = requested or PhaseInstanceId("sdk", "sdk-core", "package", "common")
        closure = _dependency_closure((requested,), sdk_runtime_external=True)
        return {
            "schemaVersion": 1, "requestType": "reuse-wave", "repository": self.repository,
            "pullRequest": None, "repositoryRoot": str(repository), "repositoryRevision": revision,
            "artifactRoot": str(artifacts), "requested": [asdict(requested)],
            "versions": {"contract": "0.2.0", "runtime-compatibility": "0.2.0",
                         "runtime-release": "0.2.8", "sdk": "0.2.9"},
            "sdkRuntimeSource": "released-default",
            "phaseAuthorities": [{**asdict(instance), "outputSchemaVersion": 1,
                "flagsDigest": NOT_APPLICABLE_FLAGS_DIGEST,
                "toolchainProfileDigest": NOT_APPLICABLE_TOOLCHAIN_DIGEST} for instance in closure],
            "contractEvidence": None, "runtimeValidationEvidence": [], "availableObjects": [],
            "runtimeAggregateReleaseEvidence": [{"receiptSha256": transport.sha256_bytes(self.raw),
                "handoffRoot": "catalog/runtime-aggregate-release-evidence/handoffs/original"}],
            "catalogs": {"stable": [], "samePr": None, "local": None, "promotedMain": {
                "manifest": "catalog/product-index.json", "signature": "catalog/product-index.sig",
                "publicKey": None, "keyring": "policy/keyring.json", "keysDirectory": "policy/keys",
                "contractAttestation": None, "contractAttestationSignature": None, "contractPublicKey": None,
                "objects": [{"buildKey": self.receipt["buildKey"],
                             "objectPath": "catalog/" + self.relative}]}}}

    def test_released_default_real_wave_restores_original_dependencies_without_runtime_work(self):
        request = self.sdk_wave_request()
        artifacts = Path(request["artifactRoot"])
        before = regular_file_inventory(artifacts, allow_empty=True)
        plans = {}
        restored = {}
        captures = []
        def consume_runtime(selected):
            self.assertEqual(self.raw, selected["envelope"]["receiptBytes"])
            self.assertEqual("promoted-main", selected["transportSource"]["kind"])
            handoff = selected["handoff"]
            self.assertEqual(regular_file_inventory(self.carrier, allow_empty=True),
                             regular_file_inventory(handoff["directory"], allow_empty=True))
            self.assertEqual(50, len(handoff["originalPhases"]))
            for identity, original in handoff["originalPhases"].items():
                raw = original["receiptPath"].read_bytes()
                self.assertEqual(handoff["receiptBytes"][identity], raw)
                self.assertEqual(original["receipt"], load_canonical_json_bytes(raw))
                self.assertTrue(original["stage"].is_dir())
            self.assertEqual(5, len(handoff["nativeRuntimeEvidence"]))
            for target, record in handoff["nativeRuntimeEvidence"].items():
                self.assertEqual(target, record["target"])
                self.assertTrue(Path(record["payload"]).is_file())
                self.assertEqual(self.keyring.read_bytes(), Path(record["keyring"]).read_bytes())
                for phase, path in record["phaseReceipts"].items():
                    identity = PhaseInstanceId("runtime", target, phase, target)
                    self.assertEqual(handoff["receiptBytes"][identity], Path(path).read_bytes())
            captures.append(handoff["directory"])
        def store_original(stage, receipt_path, cache):
            raw = receipt_path.read_bytes()
            receipt = load_canonical_json_bytes(raw)
            identity = PhaseInstanceId(**{name: receipt[name] for name in ("product", "component", "phase", "target")})
            restored[identity] = (raw, regular_file_inventory(stage))
            return store_local_object(stage, receipt_path, cache)
        # The wrapper observes actual object creation; it never supplies evidence or verifier success.
        with patch("products.reuse.store_local_object", side_effect=store_original) as stored, \
                patch("reuse.api_request", side_effect=AssertionError("released-default wave contacted CI")):
            result = plan_reuse_wave(request, build_plan_consumer=lambda identity, plan: plans.update({identity: plan}),
                                     sdk_runtime_consumer=consume_runtime)
        self.assertEqual(1, len(captures))
        self.assertFalse(captures[0].exists())
        sdk = PhaseInstanceId("sdk", "sdk-core", "package", "common")
        dependencies = {identity for identity in phase_instance_dependencies(sdk) if identity.product == "runtime"}
        self.assertEqual(dependencies, set(restored))
        self.assertEqual(len(dependencies), stored.call_count)
        for identity, (raw, inventory) in restored.items():
            original = self.carrier / "selected-inputs/predecessors" / "-".join(asdict(identity).values())
            self.assertEqual((original / "phase-receipt.json").read_bytes(), raw)
            self.assertEqual(regular_file_inventory(original / "stage"), inventory)
        self.assertEqual([], result["matrices"]["runtime"])
        self.assertFalse(any(row["product"] == "runtime" for row in result["phases"]))
        self.assertFalse(result["fullReuse"])
        contract = PhaseInstanceId("contract", "contract", "binary", "common")
        self.assertIn(contract, plans)
        self.assertTrue(plans[contract]["buildKey"].startswith("sha256:"))
        self.assertEqual("waiting", next(row["state"] for row in result["phases"]
                                         if all(row[name] == value for name, value in asdict(sdk).items())))
        self.assertEqual(before, regular_file_inventory(artifacts, allow_empty=True))
        self.assertEqual(self.before, regular_file_inventory(self.layout, allow_empty=True))

    def test_released_default_consumer_exception_prevents_wave_return_and_cleans_capture(self):
        request = self.sdk_wave_request()
        artifacts = Path(request["artifactRoot"])
        before = regular_file_inventory(artifacts, allow_empty=True)
        captures = []
        def reject(selected):
            captured = selected["handoff"]["directory"]
            self.assertTrue(captured.is_dir())
            self.assertEqual(self.raw, selected["envelope"]["receiptBytes"])
            captures.append(captured)
            raise RuntimeError("consumer refused original handoff")
        with self.assertRaisesRegex(RuntimeError, "consumer refused original handoff"):
            plan_reuse_wave(request, sdk_runtime_consumer=reject)
        self.assertEqual(1, len(captures))
        self.assertFalse(captures[0].exists())
        self.assertEqual(before, regular_file_inventory(artifacts, allow_empty=True))
        self.assertEqual(self.before, regular_file_inventory(self.layout, allow_empty=True))

    def test_released_default_noncallable_consumer_rejects_before_request_work(self):
        # Even request parsing must not precede this caller API check.
        with self.assertRaisesRegex(ValueError, "callable"):
            plan_reuse_wave({}, sdk_runtime_consumer="not-a-callback")

    def test_released_default_wave_rejects_unknown_mode_and_nonconsuming_phase(self):
        request = self.sdk_wave_request()
        request["sdkRuntimeSource"] = "newest-runtime"
        with self.assertRaisesRegex(ValueError, "Unsupported SDK Runtime dependency source"):
            plan_reuse_wave(request)
        request["sdkRuntimeSource"] = "released-default"
        request["requested"] = [asdict(PhaseInstanceId("contract", "contract", "binary", "common"))]
        with self.assertRaisesRegex(ValueError, "Runtime-consuming SDK phase"):
            plan_reuse_wave(request)

    def test_released_default_native_provider_keeps_release_policy_with_development_contract(self):
        """Routing only: current Contract and native projector boundaries are mocked explicitly."""
        sdk = PhaseInstanceId("sdk", "python", "package", "desktop")
        request = self.sdk_wave_request(sdk)
        artifacts = Path(request["artifactRoot"])
        request["contractEvidence"] = {
            "attestation": "current-contract/attestation.json",
            "attestationSignature": "current-contract/attestation.sig",
            "publicKey": "current-contract/development.pub",
            "expectedTrustDomain": "development", "keyring": None, "keysDirectory": None}
        stage = artifacts / "current-contract"
        stage.mkdir()
        for name in ("attestation.json", "attestation.sig", "development.pub"):
            (stage / name).write_bytes(b"explicit mocked current Contract boundary\n")
        before = regular_file_inventory(artifacts, allow_empty=True)
        current_projection = Mock()
        current_projection.restrict.return_value = current_projection
        current_projection.receipt_value.return_value = {"bundlePath": "current-contract.zip"}
        expected_dependencies = native_runtime_validation_dependencies(sdk)
        observations = []

        def native_projection(instance, receipts, records, projection, contract_payload, domain):
            self.assertEqual(sdk, instance)
            self.assertIs(current_projection, projection)
            self.assertEqual(stage / "current-contract.zip", contract_payload)
            self.assertEqual("release", domain)
            self.assertEqual([identity.target for identity in expected_dependencies],
                             [record["target"] for record in records])
            for receipt, record in zip(receipts, records, strict=True):
                self.assertEqual(receipt, load_canonical_json_bytes(Path(record["phaseReceipts"]["validation"]).read_bytes()))
                keyring, keys = Path(record["keyring"]), Path(record["keysDirectory"])
                self.assertNotEqual(artifacts / "policy/keyring.json", keyring)
                self.assertEqual(self.keyring.read_bytes(), keyring.read_bytes())
                self.assertEqual(regular_file_inventory(self.keys), regular_file_inventory(keys))
                observations.append((keyring, keys))
            return tuple(object() for _ in records)

        def exercise_providers(requested, inputs, available, session, **arguments):
            self.assertEqual((sdk,), requested)
            originals = {PhaseInstanceId(**{name: envelope["receipt"][name]
                         for name in ("product", "component", "phase", "target")}): envelope
                         for envelope in arguments["sdk_runtime_receipts"]}
            # Installed only after the real signed selector/carrier gates have completed.
            with patch.object(session, "contract_stage", return_value=stage), \
                    patch("products.reuse.verify_contract_component_projection", return_value=current_projection) as contract_gate, \
                    patch("products.reuse._native_runtime_projections_from_request", side_effect=native_projection) as native_gate:
                projection = arguments["contract_projection_provider"](sdk, {"receiptBytes": b"mock current Contract"})
                self.assertEqual("development", contract_gate.call_args.kwargs["expected_trust_domain"])
                result = arguments["native_runtime_projection_provider"](
                    sdk, tuple(originals[identity] for identity in expected_dependencies), projection)
                self.assertEqual(len(expected_dependencies), len(result))
                native_gate.assert_called_once()
            return {"routingOnly": True}, ()

        with patch("products.reuse.advance_reuse", side_effect=exercise_providers):
            self.assertEqual({"routingOnly": True}, plan_reuse_wave(request))
        self.assertEqual(len(expected_dependencies), len(observations))
        self.assertTrue(all(not keyring.exists() and not keys.exists() for keyring, keys in observations))
        self.assertEqual(before, regular_file_inventory(artifacts, allow_empty=True))
        self.assertEqual(self.before, regular_file_inventory(self.layout, allow_empty=True))

    def test_emitted_originals_round_trip_through_catalog_import_and_real_release_lookup(self):
        with patch("reuse.api_request", side_effect=AssertionError("catalog used original CI")), \
                patch("products.index.sign_manifest", side_effect=AssertionError("catalog re-signed")):
            self.stage()
            emitted = self.work / "emitted"
            self.assertEqual(self.before, regular_file_inventory(emitted, allow_empty=True))
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                for item in reversed(self.before):
                    archive.writestr(item["relativePath"], (emitted / item["relativePath"]).read_bytes())
            imported = self.work / "imported"
            policy = imported / "policy"
            snapshot_regular_tree(self.keys, policy / "keys")
            (policy / "keyring.json").write_bytes(self.keyring.read_bytes())
            trust = transport.ReleaseTrust(policy / "keyring.json", policy / "keys")
            with patch.object(transport, "download_artifact", return_value=buffer.getvalue()) as download:
                catalog = transport._materialize_catalog("promoted-main", {"id": 1}, "fixture", imported,
                    self.repository, None, trust)
            download.assert_called_once()
            evidence = catalog.runtime_aggregate_evidence_root
            records = transport.load_runtime_aggregate_release_evidence(evidence)
            session = LookupSession(repository=self.repository, pull_request=None,
                promoted_main=RemoteCatalog(imported / catalog.request["manifest"], imported / catalog.request["signature"],
                    catalog.objects, keyring=trust.keyring, keys_directory=trust.keys),
                runtime_aggregate_evidence={r["receiptSha256"]: evidence / r["handoffRoot"] for r in records})
            result = session.lookup("promoted-main", self.receipt)
            self.assertIsNone(result.reason)
            self.assertEqual(self.raw, result.envelope["receiptBytes"])
            self.assertEqual("development", result.envelope["receipt"]["trustDomain"])
        self.assertEqual(self.before, regular_file_inventory(self.layout, allow_empty=True))

    def test_missing_object_wrong_identity_and_output_alias_fail_without_publication(self):
        copied = self.work / "source"
        snapshot_regular_tree(self.layout, copied, allow_empty=True)
        (copied / self.relative).unlink()
        with self.assertRaisesRegex(ValueError, "every indexed"):
            self.stage(copied)
        self.assertFalse((self.work / "emitted").exists())
        with self.assertRaisesRegex(ValueError, "repository mismatch"):
            self.stage(repository="wrong/repository")
        with self.assertRaises(ValueError):
            transport.stage_release_catalog(self.layout, self.layout / "nested",
                repository=self.repository, source="promoted-main", keyring=self.keyring, keys_directory=self.keys)
        self.assertEqual(self.before, regular_file_inventory(self.layout, allow_empty=True))

    def test_late_source_mutation_rejects_before_atomic_publication(self):
        copied = self.work / "source"
        snapshot_regular_tree(self.layout, copied, allow_empty=True)
        gate = transport._verify_index_receipt
        def mutate(*args, **kwargs):
            gate(*args, **kwargs)
            (copied / "product-index.sig").write_bytes(b"changed original signature\n")
        with patch.object(transport, "_verify_index_receipt", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed before publication"):
            self.stage(copied)
        self.assertFalse((self.work / "emitted").exists())
        self.assertEqual(self.before, regular_file_inventory(self.layout, allow_empty=True))

    def promote(self, source, **changes):
        index = load_canonical_json_bytes((self.layout / "product-index.json").read_bytes())
        return transport.stage_promoted_aggregate_catalog(source, self.work / "promoted", **{
            "expected_build_key": self.receipt["buildKey"],
            "expected_receipt_sha256": transport.sha256_bytes(self.raw),
            "repository": self.repository, "context": index["context"], "producer": index["producer"],
            "keyring": self.keyring, "keys_directory": self.keys,
            "private_key": self.source.context["private_key"], **changes})

    def unsigned(self):
        source = self.work / "unsigned"
        snapshot_regular_tree(self.layout, source, allow_empty=True)
        (source / "product-index.json").unlink()
        (source / "product-index.sig").unlink()
        return source

    def test_promoted_aggregate_uses_existing_index_writer_and_preserves_all_original_bytes(self):
        source = self.unsigned()
        before = regular_file_inventory(source, allow_empty=True)
        with patch("reuse.api_request", side_effect=AssertionError("promotion contacted CI")), \
                patch("products.index.write_signed_product_index", wraps=write_signed_product_index) as writer:
            index = self.promote(source)
        writer.assert_called_once()
        self.assertEqual(self.raw, writer.call_args.args[0][0].receipt_bytes)
        emitted = self.work / "promoted"
        self.assertEqual(load_canonical_json_bytes((self.layout / "product-index.json").read_bytes()), index)
        for record in before:
            self.assertEqual((source / record["relativePath"]).read_bytes(),
                             (emitted / record["relativePath"]).read_bytes())
        self.assertEqual(before, regular_file_inventory(source, allow_empty=True))
        self.assertEqual(self.before, regular_file_inventory(self.layout, allow_empty=True))

    def test_promoted_aggregate_rejects_wrong_election_and_extra_files_before_signing(self):
        source = self.unsigned()
        with patch("products.index.write_signed_product_index", side_effect=AssertionError("invalid input signed")):
            with self.assertRaisesRegex(ValueError, "exact elected"):
                self.promote(source, expected_receipt_sha256="sha256:" + "f" * 64)
            with self.assertRaisesRegex(ValueError, "elected original"):
                self.promote(source, expected_build_key="sha256:" + "f" * 64)
            (source / "unexpected.txt").write_bytes(b"not an original catalog member\n")
            with self.assertRaisesRegex(ValueError, "unexpected original files"):
                self.promote(source)
        self.assertFalse((self.work / "promoted").exists())


class ReleaseCatalogCliTest(unittest.TestCase):
    def test_explicit_local_cli_routes_without_remote_or_signing(self):
        with patch.object(transport, "stage_release_catalog") as stage:
            self.assertEqual(0, transport.main(["stage-release-catalog", "--source-root", "originals",
                "--destination", "emitted", "--repository", "owner/repository", "--source", "promoted-main",
                "--keyring", "pinned.json", "--keys-directory", "public-keys"]))
        stage.assert_called_once_with(Path("originals"), Path("emitted"), repository="owner/repository",
                                      source="promoted-main", keyring=Path("pinned.json"), keys_directory=Path("public-keys"))


if __name__ == "__main__":
    unittest.main()
