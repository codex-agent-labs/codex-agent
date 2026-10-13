"""Real object consumption and compact custody; native/Git transport is synthetic."""

from contextlib import ExitStack
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import reuse_qualification as native
from ci import sdk_ios_original_package as reader
from ci.tests.product_chain_support import reference, write_receipt
from products.inventory import canonical_json_bytes, sha256_bytes, sha256_file, snapshot_regular_tree
from products.receipt import write_output_manifest
from products.registry import PhaseInstanceId
from products.restore import _write_object


class CompletedAppleInputsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.producer = dict(repository=native.REPOSITORY, workflowPath=".github/workflows/ci.yml",
            commit="a" * 40, tree="b" * 40, event="pull_request", runId=7, runAttempt=1, pullRequest=31)
        self.records, self.receipts, self.objects = {}, {}, {}
        previous = None
        identities = [PhaseInstanceId("contract", "contract", phase, "common")
                      for phase in ("binary", "package", "validation", "metadata")]
        identities += [PhaseInstanceId("sdk", "sdk-ios", phase, "ios") for phase in ("binary", "package")]
        for identity in identities:
            fields = tuple(getattr(identity, key) for key in native._PHASE_FIELDS)
            base = self.root / "-".join(fields)
            stage = base / "stage"
            (stage / "outputs/evidence").mkdir(parents=True)
            (stage / "outputs/evidence/sdk-compatibility.json").write_bytes(
                canonical_json_bytes({"contract": {"digest": sha256_bytes(b"contract")}}))
            (stage / "outputs/payload").write_bytes(b"consumed exact product bytes")
            manifest = write_output_manifest(stage, *fields, "0.8.0", {"fixture": "outputs"})
            upstream = [] if previous is None else [reference(self.receipts[previous])]
            if identity.product == "sdk":
                upstream = [] if identity.phase == "binary" else [reference(self.receipts[identities[3]]),
                                                                  reference(self.receipts[identities[4]])]
            receipt = write_receipt(base / "receipt.json", product=identity.product, component=identity.component,
                phase=identity.phase, target=identity.target, version="0.8.0", version_identity="0.8.0",
                outputs=manifest["outputs"], upstream=upstream, context={"producer": self.producer})
            raw = canonical_json_bytes(receipt)
            body = base / "object.zip"
            _write_object(stage, raw, body)
            self.records[identity] = {**{key: getattr(identity, key) for key in native._PHASE_FIELDS},
                "buildKey": receipt["buildKey"], "receiptSha256": sha256_bytes(raw), "objectSha256": sha256_file(body)}
            self.receipts[identity], self.objects[identity] = receipt, body
            previous = identity
        self.package, self.contract = identities[-1], identities[0]
        self.selected = self.root / "selected.json"
        self.selected.write_bytes(canonical_json_bytes(self.receipts[self.package]))
        self.plan = self.root / "plan.json"
        self.plan.write_bytes(b"caller plan")
        original = dict(artifactId=71, artifactSha256=sha256_bytes(b"original package"), workflowSha="c" * 40)
        self.cap = native.CompletedFrozenReuse(
            {"expectedResult": {"phases": list(self.records.values())}}, list(self.receipts.values()),
            native._COMPLETED_FROZEN, revision=self.producer["commit"], sdk={
                "original": {**original, "artifactId": 70},
                "extension": {"spec": {"originals": [{**self.records[self.package], **original}]}}})
        self.captured = []

    def inputs(self, **options):
        return reader.verified_completed_ios_package(self.plan, self.selected, completed_frozen=self.cap,
            repository_root=self.root, environ={}, token="synthetic", trusted_workflow_sha="c" * 40, **options)

    def seams(self):
        stack = ExitStack()
        stack.enter_context(patch.object(reader.product_reuse, "_validate_plan",
            return_value={"validationCommit": self.producer["commit"], "remoteBuildAuthorized": True}))
        stack.enter_context(patch.object(reader.product_reuse, "_consumer",
            return_value={"kind": "ci", "producer": {**self.producer, "runId": 8}}))
        def capture(_cap, record, destination, **_):
            identity = PhaseInstanceId(*(record[field] for field in native._PHASE_FIELDS))
            self.captured.append(identity)
            shutil.copyfile(self.objects[identity], destination)
        stack.enter_context(patch.object(native.CompletedFrozenReuse, "capture_object", capture))
        for name in ("verified_original_ios_package", "verified_retained_ios_package"):
            stack.enter_context(patch.object(reader, name, side_effect=AssertionError("No historical replay")))
        return stack

    def test_consumes_only_two_objects_and_retains_no_bodies(self):
        retained = self.root / "retained"
        with self.seams(), self.inputs() as selected:
            self.assertEqual(self.selected.read_bytes(), selected["receiptBytes"])
            self.assertEqual({"package-receipt.json", "completed-package.json"},
                             {path.name for path in selected["completedCapture"].iterdir()})
            snapshot_regular_tree(selected["completedCapture"], retained)
            self.assertTrue((selected["stage"] / "outputs/payload").is_file())
        self.assertEqual([self.package, self.contract], self.captured)
        with self.seams(), self.inputs(retained=retained):
            pass
        self.assertEqual([self.package, self.contract] * 2, self.captured)
        (retained / "completed-package.json").write_bytes(b"forged marker")
        with self.seams(), self.assertRaisesRegex(ValueError, "controls differ"), self.inputs(retained=retained):
            pass
        self.assertEqual(4, len(self.captured))  # Reject before fetching anything.

    def test_missing_authority_tampered_body_and_context_mutation_fail(self):
        original = self.cap
        self.cap = object()
        with self.seams(), self.assertRaisesRegex(ValueError, "concrete native"), self.inputs():
            pass
        self.cap = original
        with self.seams(), self.assertRaisesRegex(ValueError, "inputs changed"), self.inputs() as selected:
            (selected["stage"] / "outputs/payload").write_bytes(b"changed after use")
        self.objects[self.package].write_bytes(b"corrupt product object")
        with self.seams(), self.assertRaises(ValueError), self.inputs():
            pass


if __name__ == "__main__":
    unittest.main()
