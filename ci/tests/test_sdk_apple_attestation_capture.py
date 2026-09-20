"""Real transport and structural carrier parsers, mocked HTTP/plan authority.

Opaque fixture signatures intentionally do not prove signature or semantic
admission; those gates are mandatory in the separate caller.
"""

from copy import deepcopy
import io
import json
import stat
import unittest
from unittest.mock import patch
import warnings
import zipfile

from ci import sdk_apple_attestation_capture as capture
from ci.tests import test_runtime_aggregate_upload as transport_fixtures
from ci.tests import test_sdk_apple_validation_inputs as carrier_fixtures
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes


EVIDENCE = "sdk-apple-validation-evidence"


class AppleAttestationCaptureTest(unittest.TestCase):
    def setUp(self):
        self.fixture = transport_fixtures.RuntimeAggregateUploadTest(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.carrier_fixture = carrier_fixtures.AppleValidationInputsTest(methodName="runTest")
        self.addCleanup(self.carrier_fixture.doCleanups)
        self.carrier_fixture.setUp()
        self.carriers = {}
        self.entries = []
        for target in ("ios-arm64", "ios-simulator-arm64"):
            entry = self.carrier_fixture.entry(target, target)
            self.entries.append(entry)
            root = self.carrier_fixture.root / f"carrier-{target}"
            records = carrier_fixtures.carrier.capture_sdk_apple_validation_evidence([entry], root)
            self.carriers[target] = (records[0]["receiptSha256"], self.files(root))
        self.configure("ios-arm64")

    @staticmethod
    def files(root):
        return {record["relativePath"]: (root / record["relativePath"]).read_bytes()
                for record in regular_file_inventory(root, allow_empty=True)}

    @staticmethod
    def upload_files(carrier_files):
        return {**{f"{EVIDENCE}/{name}": raw for name, raw in carrier_files.items()},
                "preparation-transport/original-upload.zip": b"original preparation transport\x00\xff",
                "validation-transport/original-upload.zip": b"original validation transport\x00\xff",
                "caller-policy/keyring.json": b"opaque caller policy: not authority\n",
                "caller.json": b"opaque caller provenance: not parsed by transport\n"}

    def configure(self, target):
        f = self.fixture
        self.target = target
        self.receipt_sha, files = self.carriers[target]
        f.files = self.upload_files(files)
        f.jobs[0]["name"] = f"product-validation / sdk-apple-validation-attestation-{target}"
        self.name_upload()
        f.archive()

    def name_upload(self):
        f = self.fixture
        f.artifact["name"] = (f"codex-agent-sdk-apple-validation-evidence-{self.target}-"
            f"{self.receipt_sha.removeprefix('sha256:')}-{f.producer['tree']}-attempt-2")

    def call(self, **changes):
        f = self.fixture
        with patch.object(capture.products, "_validate_plan", return_value=f.plan), \
                patch("reuse.api_request", side_effect=f.api):
            return capture.capture_apple_validation_attestation(f.plan_path, f.output, **{
                "target": self.target, "expected_receipt_sha256": self.receipt_sha,
                "artifact_id": 701, "artifact_sha256": f.artifact["digest"],
                "trusted_workflow_sha": f.pin, "repository_root": f.root,
                "environ": {"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"},
                "token": "synthetic-token", **changes})

    def test_both_targets_preserve_full_carrier_under_current_not_original_producer(self):
        f = self.fixture
        before = regular_file_inventory(self.carrier_fixture.root, allow_empty=True)
        for target in self.carriers:
            with self.subTest(target=target):
                self.configure(target)
                f.output = f.work / target
                plan_bytes = f.plan_path.read_bytes()
                result = self.call()
                self.assertEqual(f.producer, result["captureProducer"])
                self.assertNotEqual(self.carrier_fixture.producer, result["captureProducer"])
                self.assertEqual(self.receipt_sha, result["receiptSha256"])
                self.assertEqual(target, result["target"])
                self.assertEqual({"original", "original-upload.zip", "capture-transport.json"},
                                 {path.name for path in f.output.iterdir()})
                self.assertEqual(f.raw, (f.output / "original-upload.zip").read_bytes())
                self.assertEqual(f.files, self.files(f.output / "original"))
                self.assertEqual({EVIDENCE, "preparation-transport", "validation-transport", "caller-policy", "caller.json"},
                                 {path.name for path in (f.output / "original").iterdir()})
                self.assertEqual(plan_bytes, f.plan_path.read_bytes())
                inventory = regular_file_inventory(f.output, allow_empty=True)
                with self.assertRaisesRegex(ValueError, "must not exist"):
                    self.call()
                self.assertEqual(inventory, regular_file_inventory(f.output, allow_empty=True))
        self.assertEqual(before, regular_file_inventory(self.carrier_fixture.root, allow_empty=True))

    def test_wrong_observed_job_run_attempt_pin_window_and_upload_reject(self):
        f = self.fixture
        baseline = deepcopy((f.run, f.jobs, f.artifact, f.commit))
        for case in ("failed", "job", "run", "attempt", "tree", "pin", "window", "missing-window",
                     "name", "original-attempt", "digest", "expired", "artifact-run"):
            f.run, f.jobs, f.artifact, f.commit = deepcopy(baseline)
            if case == "failed": f.jobs[0]["conclusion"] = "failure"
            elif case == "job": f.jobs[0]["name"] += "-other"
            elif case == "run": f.run["id"] = 91
            elif case == "attempt": f.run["run_attempt"] = 1
            elif case == "tree": f.commit["tree"]["sha"] = "e" * 40
            elif case == "pin": f.run["referenced_workflows"][0]["sha"] = "d" * 40
            elif case == "window": f.artifact["created_at"] = "2026-09-11T09:15:00Z"
            elif case == "missing-window": del f.artifact["created_at"]
            elif case == "name": f.artifact["name"] += "-other"
            elif case == "original-attempt": f.artifact["name"] = f.artifact["name"].replace("attempt-2", "attempt-1")
            elif case == "digest": f.artifact["digest"] = "sha256:" + "d" * 64
            elif case == "expired": f.artifact["expired"] = True
            else: f.artifact["workflow_run"]["id"] = 91
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(f.output.exists())

    def test_carrier_must_match_exact_selected_receipt_target_and_single_record(self):
        f = self.fixture
        # Rename official upload too, so rejection reaches the real carrier gate.
        self.receipt_sha = "sha256:" + "d" * 64
        self.name_upload()
        with self.assertRaisesRegex(ValueError, "exact selected receipt"):
            self.call()
        self.configure("ios-arm64")
        self.target = "ios-simulator-arm64"
        f.jobs[0]["name"] = f"product-validation / sdk-apple-validation-attestation-{self.target}"
        self.name_upload()
        with self.assertRaisesRegex(ValueError, "exact selected receipt"):
            self.call()
        self.configure("ios-arm64")
        combined = self.carrier_fixture.root / "combined"
        carrier_fixtures.carrier.capture_sdk_apple_validation_evidence(self.entries, combined)
        f.files = self.upload_files(self.files(combined))
        f.archive()
        with self.assertRaisesRegex(ValueError, "exact selected receipt"):
            self.call()
        self.assertFalse(f.output.exists())

    def test_strict_carrier_schema_binding_and_layout_reject(self):
        f = self.fixture
        manifest_name = f"{EVIDENCE}/{carrier_fixtures.carrier.REQUEST_NAME}"
        for case in ("schema", "extra-root", "missing-signature", "changed-capture", "record-path"):
            self.configure("ios-arm64")
            if case in ("schema", "record-path"):
                manifest = json.loads(f.files[manifest_name])
                if case == "schema": manifest["schemaVersion"] = True
                else: manifest["records"][0]["evidenceRoot"] = "../escape"
                f.files[manifest_name] = canonical_json_bytes(manifest)
            elif case == "extra-root": f.files[f"{EVIDENCE}/extra.json"] = b"extra"
            elif case == "missing-signature":
                del f.files[next(name for name in f.files if name.endswith(".sig"))]
            else:
                f.files[next(name for name in f.files if name.endswith("/empty.log"))] = b"changed"
            f.archive()
            with self.subTest(case=case), self.assertRaises((ValueError, OSError)):
                self.call()
            self.assertFalse(f.output.exists())

    def test_protected_controller_companion_roots_are_exact_and_required(self):
        f = self.fixture
        roots = ("preparation-transport", "validation-transport", "caller-policy", "caller.json")
        for root in roots:
            for kind in ("missing", "wrong-kind"):
                self.configure("ios-arm64")
                f.files = {name: raw for name, raw in f.files.items()
                           if name != root and not name.startswith(root + "/")}
                if kind == "wrong-kind":
                    f.files[root + "/nested" if root == "caller.json" else root] = b"wrong kind"
                f.archive()
                with self.subTest(root=root, kind=kind), self.assertRaises((ValueError, OSError)):
                    self.call()
                self.assertFalse(f.output.exists())
        self.configure("ios-arm64")
        f.files["unexpected-companion/provenance"] = b"not allowed"
        f.archive()
        with self.assertRaisesRegex(ValueError, "result layout"):
            self.call()
        self.assertFalse(f.output.exists())
        # The former carrier-only upload would drop protected caller provenance.
        f.files = dict(self.carriers["ios-arm64"][1])
        f.archive()
        with self.assertRaisesRegex(ValueError, "result layout"):
            self.call()
        self.assertFalse(f.output.exists())

    def test_malicious_zip_or_tampered_download_never_publish(self):
        f = self.fixture
        for case in ("traversal", "absolute", "symlink", "duplicate", "tamper"):
            self.configure("ios-arm64")
            if case in ("traversal", "absolute"):
                f.files["../escape" if case == "traversal" else "/escape"] = b"unsafe"
                f.archive()
            elif case == "tamper": f.raw += b"changed after official digest"
            else:
                output = io.BytesIO()
                with warnings.catch_warnings(), zipfile.ZipFile(output, "w") as archive:
                    warnings.simplefilter("ignore", UserWarning)
                    for name, raw in f.files.items(): archive.writestr(name, raw)
                    if case == "duplicate": archive.writestr(f"{EVIDENCE}/{carrier_fixtures.carrier.REQUEST_NAME}", b"duplicate")
                    else:
                        link = zipfile.ZipInfo(f"{EVIDENCE}/originals/link")
                        link.create_system = 3
                        link.external_attr = (stat.S_IFLNK | 0o777) << 16
                        archive.writestr(link, "../../escape")
                f.raw = output.getvalue()
                f.artifact.update(digest=sha256_bytes(f.raw), size_in_bytes=len(f.raw))
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(f.output.exists())
            self.assertFalse((f.work / "escape").exists())

    def test_invalid_inputs_unauthorized_plan_and_output_overlap_fail_early(self):
        f = self.fixture
        for changes in ({"target": "ios"}, {"expected_receipt_sha256": "bad"},
                        {"artifact_id": True}, {"artifact_sha256": "bad"}, {"token": ""}):
            with self.subTest(changes=changes), patch.object(capture.products, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaises(ValueError):
                self.call(**changes)
            observe.assert_not_called()
        for event, authorized in (("workflow_dispatch", True), ("pull_request", False)):
            f.plan.update(event=event, remoteBuildAuthorized=authorized)
            with patch.object(capture.products, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()
        f.plan.update(event="pull_request", remoteBuildAuthorized=True)
        alias = f.work / "alias"
        alias.symlink_to(f.root, target_is_directory=True)
        for output in (f.root / "nested-output", f.plan_path, alias / "nested-output", f.work):
            f.output = output
            with patch.object(capture.products, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()

    def test_original_plan_and_private_carrier_mutation_never_publish(self):
        f = self.fixture
        loader = capture.load_sdk_apple_validation_evidence
        for selected in ("plan", "carrier", "caller-provenance"):
            def mutate(root):
                records = loader(root)
                if selected == "plan": f.plan_path.write_bytes(b"changed plan\n")
                elif selected == "carrier": (root / carrier_fixtures.carrier.REQUEST_NAME).write_bytes(b"changed carrier\n")
                else: (root.parent / "caller.json").write_bytes(b"changed retained provenance\n")
                return records
            f.plan_path.write_bytes(canonical_json_bytes(f.plan))
            with self.subTest(selected=selected), patch.object(capture, "load_sdk_apple_validation_evidence", side_effect=mutate), \
                    self.assertRaisesRegex(ValueError, "changed before publication"):
                self.call()
            self.assertFalse(f.output.exists())


if __name__ == "__main__":
    unittest.main()
