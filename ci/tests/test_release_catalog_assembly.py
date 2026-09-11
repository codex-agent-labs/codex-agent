"""Build-free catalog round trips over real signed synthetic originals."""

from dataclasses import replace
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci.tests import test_runtime_aggregate_handoff as fixture
import product_reuse as transport
from products.index import IndexEntrySource, release_attested_runtime_aggregate_admission, write_signed_product_index
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from products.restore import object_relative_path, store_local_object
from products.reuse import LookupSession, RemoteCatalog


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
