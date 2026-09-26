"""Original upload authentication with synthetic products; HTTP is the only mock."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from ci.tests import test_contract_ci_originals as fixture
from ci.tests.test_products import phase_receipt
from products.inventory import publish_regular_tree as actual_publish_regular_tree

adapter = fixture.product_reuse
TARGET = "linux-x64"


class RuntimeOriginalCiTest(unittest.TestCase):
    api = fixture.ContractOriginalCiCaptureTest.api

    def setUp(self):
        # Reuse the real original-CI run/attempt/commit/HTTP fixture, not a
        # mocked observer or shard verifier. No native execution is claimed.
        fixture.ContractOriginalCiCaptureTest.setUp(self)
        self.receipts = {}
        self.jobs = []
        from products.receipt import compute_build_key, write_output_manifest
        for index, phase in enumerate(fixture.PHASES, 101):
            stage = self.root / "runtime-stages" / phase
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/value.bin").write_bytes(f"synthetic {phase}\n".encode())
            write_output_manifest(stage, "runtime", TARGET, phase, TARGET, "0.2.0", {"binary": "outputs"})
            identity = {"product": "runtime", "component": TARGET, "phase": phase, "target": TARGET}
            inputs = phase_receipt()["inputs"]
            plan = {"schemaVersion": 1, **identity, "inputs": inputs,
                    "buildKey": compute_build_key(**identity, inputs=inputs)}
            upload = self.root / "runtime-uploads" / phase
            fixture.finalize_phase_object(stage_root=stage, phase_plan=plan, producer=self.producer,
                product_version="0.2.0", trust_domain="development", destination=upload / "shard")
            self.receipts[phase] = upload / "shard/phase-receipt.json"
            raw = fixture.archive_tree(upload)
            name = (f"codex-agent-runtime-worker-{TARGET}-{phase}-{TARGET}-"
                    f"{plan['buildKey'][7:]}-{self.producer['tree']}-attempt-2")
            self.artifacts[phase].update(name=name, digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw))
            self.archives[phase] = raw
            self.jobs.append({"id": index, "name": f"product-validation / runtime-{TARGET}-{phase}-{TARGET}",
                "run_id": 71, "head_sha": self.run["head_sha"], "status": "completed", "conclusion": "success",
                "started_at": "2026-09-06T10:00:00Z", "completed_at": "2026-09-06T10:30:00Z"})

    def capture(self, **changes):
        with mock.patch("reuse.api_request", side_effect=self.api(**changes)):
            return adapter.capture_runtime_original_ci_phases(self.receipts, self.output,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token")

    def test_original_uploads_and_receipts_are_retained_exactly(self):
        before = {phase: path.read_bytes() for phase, path in self.receipts.items()}
        result = self.capture()
        self.assertEqual(TARGET, result["target"])
        for phase in fixture.PHASES:
            retained = self.output / "phases" / phase
            self.assertEqual(self.archives[phase], (retained / "transport.zip").read_bytes())
            self.assertEqual(before[phase], (retained / "original/shard/phase-receipt.json").read_bytes())
            self.assertEqual(before[phase], self.receipts[phase].read_bytes())
        with self.assertRaisesRegex(ValueError, "must not exist"):
            self.capture()

    def test_successful_phase_jobs_remain_authentic_after_overall_run_failure(self):
        failed_run = {**self.run, "status": "completed", "conclusion": "failure"}
        originals = {phase: path.read_bytes() for phase, path in self.receipts.items()}
        result = self.capture(run=failed_run)
        self.assertEqual("failure", result["observed"][0]["run"]["conclusion"])
        for phase in fixture.PHASES:
            self.assertEqual(originals[phase],
                (self.output / "phases" / phase / "original/shard/phase-receipt.json").read_bytes())

    def test_failed_validation_keeps_only_authenticated_successful_prefix(self):
        failed_run = {**self.run, "status": "completed", "conclusion": "failure"}
        receipts = {phase: self.receipts[phase] for phase in ("binary", "package")}
        with mock.patch("reuse.api_request", side_effect=self.api(run=failed_run)):
            result = adapter.capture_runtime_original_ci_phases(receipts, self.output,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token")
        self.assertEqual({"binary", "package"}, set(result["artifacts"]))
        self.assertFalse((self.output / "phases/validation").exists())
        for phase, source in receipts.items():
            self.assertEqual(source.read_bytes(),
                (self.output / "phases" / phase / "original/shard/phase-receipt.json").read_bytes())
        with self.assertRaisesRegex(ValueError, "successful prefix"):
            adapter.capture_runtime_original_ci_phases({"binary": self.receipts["binary"],
                "validation": self.receipts["validation"]}, self.root / "invalid-prefix",
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token")

    def test_late_original_shard_mutation_cannot_publish(self):
        def mutate_before_copy(source, destination, **kwargs):
            (Path(source) / "phases/binary/original/shard/phase-receipt.json").write_bytes(
                b"changed after verification")
            actual_publish_regular_tree(source, destination, **kwargs)

        with mock.patch.object(adapter, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_failed_job_wrong_attempt_window_digest_and_workflow_reject(self):
        failed = copy.deepcopy(self.jobs)
        failed[2]["conclusion"] = "failure"
        window = copy.deepcopy(self.artifacts)
        window["metadata"]["created_at"] = "2026-09-06T11:00:00Z"
        wrong_pin = copy.deepcopy(self.run)
        wrong_pin["referenced_workflows"][0]["sha"] = "a" * 40
        for changes in ({"jobs": failed}, {"artifacts": window, "details": window},
                        {"run": wrong_pin}, {"archives": {**self.archives, "binary": b"changed"}}):
            with self.subTest(changes=list(changes)), self.assertRaises(ValueError):
                self.capture(**changes)
            self.assertFalse(self.output.exists())

    def test_wrong_receipt_and_missing_upload_reject_without_output(self):
        self.receipts["metadata"] = self.receipts["binary"]
        with self.assertRaisesRegex(ValueError, "phase identity"):
            self.capture()
        self.receipts["metadata"] = self.root / "runtime-uploads/metadata/shard/phase-receipt.json"
        missing = {phase: value for phase, value in self.artifacts.items() if phase != "metadata"}
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            self.capture(artifacts=missing)
        self.assertFalse(self.output.exists())

    def test_valid_but_different_receipt_is_not_laundered_by_the_upload(self):
        path = self.receipts["metadata"]
        value = fixture.load_canonical_json_bytes(path.read_bytes())
        value["productVersion"] = "0.2.1"
        path.write_bytes(fixture.canonical_json_bytes(value))
        with self.assertRaisesRegex(ValueError, "differs from the requested original receipt"):
            self.capture()
        self.assertFalse(self.output.exists())

    def test_mixed_original_run_attempts_keep_their_receipts(self):
        producer = {**self.producer, "runId": 72, "runAttempt": 3}
        prior = fixture.load_canonical_json_bytes(self.receipts["metadata"].read_bytes())
        plan = {key: prior[key] for key in ("schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        upload = self.root / "later-original"
        fixture.finalize_phase_object(stage_root=self.root / "runtime-stages/metadata", phase_plan=plan,
            producer=producer, product_version="0.2.0", trust_domain="development", destination=upload / "shard")
        self.receipts["metadata"] = upload / "shard/phase-receipt.json"
        raw = fixture.archive_tree(upload)
        self.archives["metadata"] = raw
        artifact = self.artifacts["metadata"]
        artifact.update(name=artifact["name"].removesuffix("attempt-2") + "attempt-3",
                        digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw),
                        workflow_run={"id": 72, "head_sha": self.run["head_sha"]})
        later_run = {**self.run, "id": 72, "run_attempt": 3}
        later_job = {**self.jobs[-1], "run_id": 72}
        original_api = self.api()
        prefix = f"https://api.github.com/repos/{fixture.REPOSITORY}/actions/runs/72"

        def request(url, token):
            if url == prefix + "/attempts/3":
                return json.dumps(later_run).encode()
            if url.startswith(prefix + "/attempts/3/jobs?"):
                return json.dumps({"jobs": [later_job]}).encode()
            if url.startswith(prefix + "/artifacts?"):
                return json.dumps({"artifacts": [artifact]}).encode()
            return original_api(url, token)

        with mock.patch("reuse.api_request", side_effect=request):
            result = adapter.capture_runtime_original_ci_phases(self.receipts, self.output,
                target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token")
        self.assertEqual(2, len(result["observed"]))
        self.assertEqual(self.receipts["metadata"].read_bytes(),
            (self.output / "phases/metadata/original/shard/phase-receipt.json").read_bytes())


class RuntimeRetainedOriginalTest(unittest.TestCase):
    api = fixture.ContractOriginalCiCaptureTest.api

    def setUp(self):
        RuntimeOriginalCiTest.setUp(self)
        from ci.tests import test_product_runtime_variant as variant
        from products.runtime_attestation import build_runtime_variant_attestation
        from products.signatures import generate_development_key
        self.private, self.public, signing = generate_development_key(self.root / "release-key")
        self.signing = {**signing, "trustDomain": "release", "keyId": "retained-fixture"}
        self.keys = self.root / "public-policy/keys"
        self.keys.mkdir(parents=True)
        (self.keys / "retained-fixture.pub").write_bytes(self.public.read_bytes())
        self.keyring = self.keys.parent / "keyring.json"
        policy = {"schemaVersion": 1, **{key: self.signing[key] for key in ("algorithm", "namespace", "trustDomain")},
                  "activeKey": {key: self.signing[key] for key in ("keyId", "fingerprint")}, "retiredKeys": []}
        self.keyring.write_bytes(fixture.canonical_json_bytes(policy))
        original = variant.Fixture(self.root / "native-original", self.private, self.public, signing)
        self.payload = variant.produce_runtime_variant(**original.arguments())["bundlePath"]
        self.receipts = {**original.receipt_paths, "metadata": variant._write_metadata_receipt(original, self.payload)}
        self.handoff = self.root / "release-handoff"
        build_runtime_variant_attestation(self.payload, *(self.receipts[phase] for phase in fixture.PHASES),
            original.validation, self.signing, self.private, self.public, self.handoff,
            keyring=self.keyring, keys_directory=self.keys, complete_handoff=True)

    def capture(self, **changes):
        arguments = dict(target=TARGET, trusted_workflow_sha=self.pin, token="not-a-real-token",
                         release_handoffs=(self.handoff,), keyring=self.keyring, keys_directory=self.keys)
        arguments.update(changes)
        return adapter.capture_runtime_original_ci_phases(self.receipts, self.output, **arguments)

    def test_complete_retired_release_reuses_without_network_or_signing(self):
        policy = fixture.load_canonical_json_bytes(self.keyring.read_bytes())
        policy["retiredKeys"] = [policy["activeKey"]]
        policy["activeKey"] = None
        self.keyring.write_bytes(fixture.canonical_json_bytes(policy))
        before = fixture.regular_file_inventory(self.handoff)
        with mock.patch("reuse.api_request", side_effect=AssertionError("network")), \
                mock.patch("products.runtime_attestation.sign_manifest", side_effect=AssertionError("sign")):
            result = self.capture()
        self.assertEqual([], result["observed"])
        self.assertEqual({}, result["artifacts"])
        self.assertEqual(dict.fromkeys(fixture.PHASES, 0), result["releaseAttestations"])
        self.assertEqual(before, fixture.regular_file_inventory(self.output / "release-handoffs/0"))
        self.assertEqual(before, fixture.regular_file_inventory(self.handoff))

    def test_private_release_policy_swap_cannot_publish(self):
        original = adapter.load_keyring
        caller_bytes = self.keyring.read_bytes()
        swapped = False

        def swap_after_private_copy(keyring, keys):
            nonlocal swapped
            result = original(keyring, keys)
            keyring, keys = Path(keyring), Path(keys)
            if not swapped and keys.parent == keyring.parent:
                value = fixture.load_canonical_json_bytes(keyring.read_bytes())
                value["retiredKeys"] = [value["activeKey"]]
                value["activeKey"] = None
                keyring.write_bytes(fixture.canonical_json_bytes(value))
                swapped = True
            return result

        with mock.patch.object(adapter, "load_keyring", side_effect=swap_after_private_copy), \
                mock.patch("reuse.api_request", side_effect=AssertionError("network")), \
                self.assertRaisesRegex(ValueError, "release policy differs from caller"):
            self.capture()
        self.assertTrue(swapped)
        self.assertEqual(caller_bytes, self.keyring.read_bytes())
        self.assertFalse(self.output.exists())

    def test_mixed_release_and_ci_preserves_originals_and_fetches_only_missing_phase(self):
        from products.receipt import write_output_manifest
        receipt = fixture.load_canonical_json_bytes(self.receipts["metadata"].read_bytes())
        stage = self.root / "new-metadata-stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs" / self.payload.name).write_bytes(self.payload.read_bytes())
        write_output_manifest(stage, "runtime", TARGET, "metadata", TARGET, receipt["productVersion"],
                              {"runtime-variant": "outputs"})
        upload = self.root / "new-metadata-upload"
        plan = {key: receipt[key] for key in ("schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        fixture.finalize_phase_object(stage_root=stage, phase_plan=plan, producer=self.producer,
            product_version=receipt["productVersion"], trust_domain="development", destination=upload / "shard")
        self.receipts["metadata"] = upload / "shard/phase-receipt.json"
        raw = fixture.archive_tree(upload)
        self.archives["metadata"] = raw
        self.artifacts["metadata"].update(digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw),
            name=f"codex-agent-runtime-worker-{TARGET}-metadata-{TARGET}-{receipt['buildKey'][7:]}-{self.producer['tree']}-attempt-2")
        with mock.patch("reuse.api_request", side_effect=self.api()) as http:
            result = self.capture()
        self.assertEqual({"metadata"}, set(result["artifacts"]))
        self.assertEqual(dict.fromkeys(("binary", "package", "validation"), 0), result["releaseAttestations"])
        downloaded = [call.args[0] for call in http.call_args_list if call.args[0].endswith("/zip")]
        self.assertEqual([self.artifacts["metadata"]["archive_download_url"]], downloaded)

    def test_invalid_retained_evidence_never_falls_back_to_ci(self):
        with mock.patch("reuse.api_request", side_effect=AssertionError("network")):
            for changes in ({"keyring": None}, {"keys_directory": None}, {"release_handoffs": ()},
                            {"target": "macos-x64"}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    self.capture(**changes)
                self.assertFalse(self.output.exists())
            (self.handoff / "unexpected").write_bytes(b"untrusted")
            with self.assertRaises(ValueError):
                self.capture()
            self.assertFalse(self.output.exists())
