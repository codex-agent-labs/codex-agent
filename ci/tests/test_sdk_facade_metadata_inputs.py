"""Real metadata writer/receipt lineage, with original full readers mocked.

No fixture claims genuine observed workers, signatures, or compiler execution.
"""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_facade_metadata_inputs as inputs
from ci.tests import test_product_sdk_platform_metadata as metadata_fixture
from ci.tests import test_sdk_facade_inputs as request_fixture
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, snapshot_regular_tree
from products.plan import _upstream_record
from products.registry import SDK_FACADE_TARGETS


class FacadeMetadataInputsTest(unittest.TestCase):
    def setUp(self):
        self.f = metadata_fixture.PlatformMetadataWriterTest(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.r = request_fixture.FacadeInputsTest(methodName="runTest")
        self.r.setUp()
        self.addCleanup(self.r.doCleanups)
        self.records = {}
        self.plan = self.f.root / "plan.json"
        self.plan.write_bytes(b"{}\n")
        for index, target in enumerate(SDK_FACADE_TARGETS):
            request = self.f.root / (target + "-request.json")
            request.write_bytes(canonical_json_bytes({**self.r.value, "target": target,
                "repository": str(self.f.root), "packageStage": str(self.f.stages["package"]),
                "packageReceipt": str(self.f.receipts["package"])}))
            self.records[target] = {"validationReceipt": self.f.receipts[target], "facadeRequest": request,
                                    "artifactId": index + 1, "artifactSha256": "sha256:" + f"{index + 1:064x}"}
        self.active, self.events = set(), []
        self.exit_failure = None
        self.wrong_receipt = None
        self.reader = self.enterContext(patch.object(inputs, "verified_original_sdk_facade_validation", side_effect=self.original))

    @contextmanager
    def original(self, plan, receipt_path, **kwargs):
        target = load_canonical_json_bytes(receipt_path.read_bytes())["target"]
        self.assertEqual(self.plan, plan)
        record = self.records[target]
        self.assertEqual(record["artifactId"], kwargs["artifact_id"])
        self.assertEqual(record["artifactSha256"], kwargs["artifact_sha256"])
        self.assertEqual(record["facadeRequest"], kwargs["facade_request"])
        self.assertEqual("explicit-caller-token", kwargs["token"])
        self.assertEqual("e" * 40, kwargs["policy_revision"])
        self.assertEqual("development", kwargs["required_trust_domain"])
        self.events.append(("enter", target))
        self.active.add(target)
        with tempfile.TemporaryDirectory(prefix="mock-original-facade-") as temporary:
            root = Path(temporary).resolve()
            stage = root / "stage"
            snapshot_regular_tree(self.f.stages[target], stage)
            receipt = root / "receipt.json"
            raw = receipt_path.read_bytes()
            receipt.write_bytes(raw)
            capture = root / "capture"
            (capture / "original").mkdir(parents=True)
            (capture / "transport.zip").write_bytes(b"opaque original ZIP; official gate mocked")
            (capture / "original/gradle.log").write_bytes(b"")
            value = {"stage": stage, "receiptPath": receipt, "receiptBytes": raw,
                     "receipt": load_canonical_json_bytes(raw), "capture": capture,
                     "original": capture / "original", "transport": {"fixture": target}}
            if self.wrong_receipt == target:
                value["receipt"] = {**value["receipt"], "trustDomain": "release"}
            try:
                yield value
            finally:
                self.events.append(("exit", target))
                self.active.remove(target)
                if self.exit_failure == target:
                    raise ValueError("original reader exit rejected")

    def call(self, **changes):
        arguments = dict(plan=self.plan, validations=self.records,
            contract_digest=self.f.request["contractDigest"], component_digests=self.f.request["componentDigests"],
            repository_root=self.f.root, environ={}, token="explicit-caller-token", trusted_workflow_sha="f" * 40,
            tooling_evidence=self.f.root / "tooling", tooling_public_key=self.f.root / "key.pub",
            java_executable=self.f.root / "java", policy_revision="e" * 40, required_trust_domain="development")
        arguments.update(changes)
        return inputs.verified_facade_metadata_inputs(**arguments)

    def test_all_original_gates_live_through_exact_canonical_join_and_cleanup(self):
        mixed = load_canonical_json_bytes(self.f.receipts["jvm"].read_bytes())
        mixed["producer"]["commit"] = "c" * 40
        self.f.receipts["jvm"].write_bytes(canonical_json_bytes(mixed))
        raw = {target: self.f.receipts[target].read_bytes() for target in SDK_FACADE_TARGETS}
        with self.call() as value:
            self.assertEqual(set(SDK_FACADE_TARGETS), self.active)
            self.assertEqual(11, self.reader.call_count)
            self.assertEqual(list(SDK_FACADE_TARGETS), [row["target"] for row in value["expectedContent"]["validations"]])
            self.assertEqual(canonical_json_bytes(value["expectedContent"]), value["expectedContentBytes"])
            for target, record in value["validations"].items():
                self.assertEqual(raw[target], record["receiptBytes"])
                self.assertTrue((record["capture"] / "transport.zip").is_file())
            invocation = load_canonical_json_bytes(value["request"].read_bytes())
            self.assertEqual(self.f.request["componentDigests"], invocation["componentDigests"])
            self.assertEqual(self.f.receipts["package"].read_bytes(), value["package"]["receiptBytes"])
            request_path = value["request"]
        self.assertFalse(self.active)
        self.assertFalse(request_path.exists())
        self.assertEqual([("exit", target) for target in reversed(SDK_FACADE_TARGETS)], self.events[-11:])

    def test_exact_eleven_locators_and_receipt_identity_are_required_before_capture(self):
        for change in ("missing", "extra", "bool-id", "unprefixed-sha", "wrong-target"):
            records = deepcopy(self.records)
            if change == "missing": records.pop("jvm")
            elif change == "extra": records["common"] = records["jvm"]
            elif change == "bool-id": records["jvm"]["artifactId"] = True
            elif change == "unprefixed-sha": records["jvm"]["artifactSha256"] = "a" * 64
            else: records["jvm"]["validationReceipt"] = records["android"]["validationReceipt"]
            with self.subTest(change=change), self.assertRaises(ValueError), self.call(validations=records):
                pass
        self.reader.assert_not_called()

    def test_foreign_package_receipt_fails_before_original_readers(self):
        request_path = self.records["jvm"]["facadeRequest"]
        request = load_canonical_json_bytes(request_path.read_bytes())
        other = self.f.root / "other-package.json"
        package = deepcopy(self.f.originals["package"])
        package["producer"]["commit"] = "c" * 40
        other.write_bytes(canonical_json_bytes(package))
        request["packageReceipt"] = str(other)
        request_path.write_bytes(canonical_json_bytes(request))
        with self.assertRaisesRegex(ValueError, "different original package"), self.call():
            pass
        self.reader.assert_not_called()

    def test_independent_contract_expectations_and_full_reader_receipt_are_enforced(self):
        with self.assertRaisesRegex(ValueError, "Contract identity"), self.call(contract_digest="sha256:" + "e" * 64):
            pass
        self.assertFalse(self.active)
        self.wrong_receipt = "jvm"
        with self.assertRaisesRegex(ValueError, "different selected receipt"), self.call():
            pass
        self.assertFalse(self.active)

    def test_reader_exit_failure_prevents_successful_context_completion(self):
        self.exit_failure = "jvm"
        with self.assertRaisesRegex(ValueError, "reader exit rejected"):
            with self.call():
                self.assertEqual(11, len(self.active))
        self.assertFalse(self.active)

    def test_real_writer_rejects_wrong_original_package_upstream_even_with_same_content(self):
        metadata = metadata_fixture.metadata
        content = (self.f.stages["jvm"] / metadata._VALIDATION_PATH).read_bytes()
        upstream = _upstream_record(self.f.originals["package"])
        upstream["buildKey"] = "sha256:" + "e" * 64
        self.f.stage("jvm", metadata._VALIDATION_PATH, content, metadata._VALIDATION_KIND, upstream=[upstream])
        with self.assertRaisesRegex(ValueError, "package lineage"), self.call():
            pass
        self.assertFalse(self.active)

    def test_late_caller_private_capture_and_projection_mutations_fail(self):
        for change in ("locator", "components", "capture", "package", "content", "request", "extra-held"):
            records_before = deepcopy(self.records)
            components_before = deepcopy(self.f.request["componentDigests"])
            try:
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "changed"):
                    with self.call() as value:
                        if change == "locator": self.records["jvm"]["artifactId"] += 100
                        elif change == "components": self.f.request["componentDigests"]["jvm"] = "sha256:" + "e" * 64
                        elif change == "capture": (value["validations"]["jvm"]["capture"] / "transport.zip").write_bytes(b"changed")
                        elif change == "package": value["package"]["receiptPath"].write_bytes(b"changed")
                        elif change == "content": value["expectedContent"]["validations"].pop()
                        elif change == "extra-held": value["validations"]["extra"] = value["validations"]["jvm"]
                        else: value["request"].write_bytes(b"changed")
            finally:
                self.records = records_before
                self.f.request["componentDigests"] = components_before
            self.assertFalse(self.active)
