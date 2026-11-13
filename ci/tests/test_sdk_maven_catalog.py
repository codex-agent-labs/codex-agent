"""Catalog storage only: signature authority mocked, no Maven admission claim."""

from copy import deepcopy
from pathlib import Path
import sys
import shutil
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import product_reuse as adapter
from ci import sdk_maven_evidence as carrier
from ci.tests import test_sdk_facade_capture as fixtures
from ci.products.inventory import regular_file_inventory, snapshot_regular_tree, write_canonical_json
from ci.tests import test_runtime_resumed_phase as resumed_fixture


class MavenCatalogTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CoreBinaryCaptureTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.call()  # Official HTTP/observer fixture is entirely mocked.
        self.root = self.fixture.work
        self.source = self.root / "carrier"
        self.record = carrier._record(self.fixture.receipt_bytes)
        snapshot_regular_tree(self.fixture.output, self.source / self.record["capture"], allow_empty=True)
        (self.source / self.record["receipt"]).write_bytes(self.fixture.receipt_bytes)
        write_canonical_json(self.source / carrier.REQUEST_NAME, [self.record])
        producer = self.fixture.producer
        self.index = {"repository": producer["repository"], "producer": producer,
            "context": {"kind": "pull-request", **{key: producer[key] for key in
                ("pullRequest", "commit", "tree", "runId", "runAttempt")}},
            "entries": [{**self.fixture.receipt, "receiptSha256": self.record["receiptSha256"]}]}
        self.observed = {"run": {"id": producer["runId"], "run_attempt": producer["runAttempt"],
            "path": producer["workflowPath"]},
            "testedCommit": {"sha": producer["commit"], "tree": {"sha": producer["tree"]}}}

    def layout(self, name, index=None):
        root = self.root / name / "contents"
        root.mkdir(parents=True)
        write_canonical_json(root / "product-index.json", self.index if index is None else index)
        (root / "product-index.sig").write_bytes(b"opaque mocked index signature")
        (root / "public-key.pub").write_bytes(b"opaque mocked observed key")
        snapshot_regular_tree(self.source, root / "sdk-maven-evidence", allow_empty=True)
        return root

    def read(self, root):
        with patch.object(adapter, "validate_product_index", side_effect=lambda value: value):
            return adapter._read_catalog_directory("same-pr", root, root.parent, None,
                repository=self.fixture.producer["repository"], pull_request=self.fixture.producer["pullRequest"],
                provenance_root=root.parent, workflow_run=self.observed)

    def test_exact_index_bound_carrier_survives_without_fabricating_objects_or_admission(self):
        root = self.layout("valid")
        result = self.read(root)
        self.assertEqual(root / "sdk-maven-evidence", result.sdk_maven_evidence_root)
        self.assertEqual([self.record], carrier.load_sdk_maven_evidence(result.sdk_maven_evidence_root))
        self.assertEqual({}, result.objects)
        self.assertNotIn("sdkMavenEvidence", result.request)
        self.assertEqual(regular_file_inventory(self.source, allow_empty=True),
            regular_file_inventory(result.sdk_maven_evidence_root, allow_empty=True))

    def test_every_index_identity_and_receipt_digest_is_required(self):
        for key, value in {"product": "runtime", "component": "sdk-ios", "phase": "package",
                "target": "android", "receiptSha256": "sha256:" + "f" * 64}.items():
            index = deepcopy(self.index)
            index["entries"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.read(self.layout(key, index))

    def test_extra_or_mutated_transport_is_rejected(self):
        for mode in ("extra", "zip"):
            root = self.layout(mode)
            if mode == "extra":
                (root / "sdk-maven-evidence/unrequested").write_bytes(b"extra")
            else:
                (root / "sdk-maven-evidence" / self.record["capture"] / "original-upload.zip").write_bytes(b"changed")
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.read(root)

    def test_discovery_and_advance_cli_forward_only_explicit_external_carriers(self):
        base = ["--plan", str(self.root / "plan"), "--destination", str(self.root / "output"),
                "--github-output", str(self.root / "github-output")]
        for command, extra in (("discover", []), ("advance-products", ["--discovery-root", str(self.root / "discovery")])):
            with self.subTest(command=command), patch.object(adapter, command.replace("-", "_")) as method:
                self.assertEqual(0, adapter.main([command, *base, *extra]))
                self.assertNotIn("sdk_maven_evidence_roots", method.call_args.kwargs)
                self.assertEqual(0, adapter.main([command, *base, *extra, "--sdk-maven-evidence", str(self.source)]))
                self.assertEqual((self.source,), method.call_args.kwargs["sdk_maven_evidence_roots"])

    def test_successive_storage_preserves_all_original_bytes_and_receipts(self):
        destination = self.root / "retained"
        before = regular_file_inventory(self.source, allow_empty=True)
        adapter._capture_maven_handoffs((self.source,), destination)
        adapter._capture_maven_handoffs((self.source,), destination)
        for number in ("0", "1"):
            self.assertEqual(before, regular_file_inventory(destination / number, allow_empty=True))
        self.assertEqual(before, regular_file_inventory(self.source, allow_empty=True))


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class MavenStateRetentionTest(unittest.TestCase):
    setUpClass = classmethod(resumed_fixture.RuntimeResumedPhaseTest.setUpClass.__func__)
    control_seams = classmethod(resumed_fixture.RuntimeResumedPhaseTest.control_seams.__func__)
    setUp = resumed_fixture.RuntimeResumedPhaseTest.setUp
    tearDown = resumed_fixture.RuntimeResumedPhaseTest.tearDown
    resume = resumed_fixture.RuntimeResumedPhaseTest.resume
    binary_shard = resumed_fixture.RuntimeResumedPhaseTest.binary_shard
    advance = resumed_fixture.RuntimeResumedPhaseTest.advance

    def test_contract_resume_and_product_advance_preserve_external_maven_bytes(self):
        fixture = MavenCatalogTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        source = self.discovery / "sdk-maven-evidence/0"
        snapshot_regular_tree(fixture.source, source, allow_empty=True)
        # Finish constructing this test's original discovery before its lifetime baseline.
        self.immutable = {**self.immutable,
            self.discovery: regular_file_inventory(self.discovery, allow_empty=True)}
        expected = regular_file_inventory(source, allow_empty=True)
        resumed = self.resume()
        self.assertEqual(expected, regular_file_inventory(resumed / "sdk-maven-evidence/0", allow_empty=True))
        shard, _ = self.binary_shard(resumed, "retention")
        destination = self.scratch / "advanced-retention"
        result = self.advance(resumed, shard, destination)
        self.assertTrue(result["fullReuse"])
        self.assertEqual(expected, regular_file_inventory(destination / "sdk-maven-evidence/0", allow_empty=True))
        self.assertFalse(any(row["product"] == "sdk" for row in result["phases"]))
