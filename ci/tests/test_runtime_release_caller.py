"""Synthetic signed originals and mocked HTTP; never protected-host acceptance."""

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_original_ci as original_fixture
from ci.tests.test_runtime_original_ci import TARGET, fixture
from ci.products.registry import PhaseInstanceId
from ci.tests.test_contract_release_context import contract_context, trusted_repository
from ci.tests.test_contract_release_capture import ObservedEnvironment, SECRET
from ci.tests.test_product_native_chain import build_chain
from ci import runtime_release
from products.contract_attestation import build_contract_attestation
from products.runtime_attestation import build_runtime_variant_attestation, read_runtime_variant_handoff
from products.inventory import (
    canonical_json_bytes, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory,
)
from products.signatures import generate_development_key


class RuntimeReleaseCallerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = original_fixture.RuntimeOriginalCiTest()
        cls.source.setUp()
        cls.addClassCleanup(cls.source.doCleanups)
        cls.root = cls.source.root
        private, public, signing = generate_development_key(cls.root / "caller-keys")
        cls.context = {"private_key": private, "public_key": public, "signing": signing,
                       "producer": cls.source.producer}
        cls.chain = build_chain(cls.root / "chain", 71, context=cls.context)
        cls.repository = cls.root / "trusted-caller"
        trusted_repository(cls.repository)
        cls.keyring = cls.repository / "gradle/release/product-signing-keys.json"
        cls.keys = cls.repository / "gradle/release/keys"
        cls.keys.mkdir()
        cls.release_signing = {**signing, "trustDomain": "release"}
        (cls.keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        cls.policy = {"schemaVersion": 1, "algorithm": signing["algorithm"],
                      "namespace": signing["namespace"], "trustDomain": "release",
                      "activeKey": {key: signing[key] for key in ("keyId", "fingerprint")}, "retiredKeys": []}
        cls.keyring.write_bytes(canonical_json_bytes(cls.policy))
        cls.pin = cls.commit_policy()
        contract = cls.chain["contract"]
        trust = cls.root / "release-contract"
        build_contract_attestation(contract["payload"], contract["receipt"], cls.release_signing,
            private, public, trust, execution_closure=contract["execution_closure"],
            keyring=cls.keyring, keys_directory=cls.keys)
        cls.contract = {"stage": contract["payload"].parent.parent, "payload": contract["payload"],
                        "receipt": contract["receipt"], "public_key": public,
                        "attestation": trust / contract["attestation"].name,
                        "signature": trust / contract["signature"].name}
        variants = cls.chain["variants"]
        cls.receipts = variants["variant_phase_receipts"][TARGET]
        cls.handoff = cls.root / "retained-runtime"
        build_runtime_variant_attestation(variants["variant_bundles"][TARGET],
            *(cls.receipts[phase] for phase in fixture.PHASES), variants["variant_validation_evidence"][TARGET],
            cls.release_signing, private, public, cls.handoff,
            keyring=cls.keyring, keys_directory=cls.keys, complete_handoff=True)
        # Real shard verifier + fixed original attempt/job observer; only HTTP is mocked.
        for phase, receipt_path in cls.receipts.items():
            receipt = fixture.load_canonical_json_bytes(receipt_path.read_bytes())
            stage = cls.context["phase_stages"][PhaseInstanceId("runtime", TARGET, phase, TARGET)]
            upload = cls.root / "full-runtime-uploads" / phase
            plan = {key: receipt[key] for key in ("schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
            fixture.finalize_phase_object(stage_root=stage, phase_plan=plan, producer=receipt["producer"],
                product_version=receipt["productVersion"], trust_domain=receipt["trustDomain"], destination=upload / "shard")
            if (upload / "shard/phase-receipt.json").read_bytes() != receipt_path.read_bytes():
                raise AssertionError("Synthetic original receipt was rewritten")
            (upload / "empty-diagnostic.log").write_bytes(b"")
            raw = fixture.archive_tree(upload)
            cls.source.archives[phase] = raw
            cls.source.artifacts[phase].update(
                name=f"codex-agent-runtime-worker-{TARGET}-{phase}-{TARGET}-{receipt['buildKey'][7:]}-{receipt['producer']['tree']}-attempt-2",
                digest=fixture.sha256_bytes(raw), size_in_bytes=len(raw))

    @classmethod
    def commit_policy(cls):
        subprocess.run(["git", "add", "gradle/release"], cwd=cls.repository, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "fixture policy"], cwd=cls.repository, check=True, capture_output=True)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cls.repository,
                              check=True, capture_output=True, text=True).stdout.strip()

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-caller-result-")
        self.addCleanup(temporary.cleanup)
        self.destination = Path(temporary.name).resolve() / "result"
        _, self.event, env = contract_context()
        env.update(GITHUB_SHA=self.source.producer["commit"])
        env[SECRET] = self.context["private_key"].read_text()
        self.environment = ObservedEnvironment(env)
        self.event["pull_request"]["base"]["sha"] = self.source.commit["parents"][0]["sha"]

    def invoke(self, **changes):
        args = dict(target=TARGET, trusted_source_sha=self.pin, trusted_workflow_sha=self.source.pin,
            transport_producer=self.source.producer, event_payload=self.event, environment=self.environment,
            runtime_stage_root=self.chain["variants"]["stages"], phase_receipts=self.receipts,
            variant_payload=self.chain["variants"]["variant_bundles"][TARGET], contract=self.contract,
            contract_version="0.2.0", token="not-a-real-token")
        args.update(changes)
        return runtime_release.attest_runtime_variant_ci(self.repository, self.destination, **args)

    def test_original_ci_content_is_verified_before_signing_exact_payload(self):
        before = regular_file_inventory(self.chain["variants"]["stages"])
        with patch("reuse.api_request", side_effect=self.source.api()):
            self.invoke()
        self.assertEqual(1, self.environment.secret_reads)
        verified = read_runtime_variant_handoff(self.destination / "runtime-input", target=TARGET,
            keyring=self.keyring, keys_directory=self.keys)
        self.assertEqual(self.chain["variants"]["variant_bundles"][TARGET].read_bytes(),
                         verified["files"][verified["attestation"]["payload"]["fileName"]])
        expected = [record for record in before if record["relativePath"].startswith(
            (f"{TARGET}/package/", f"{TARGET}/validation/"))]
        self.assertEqual(expected, regular_file_inventory(self.destination / "runtime-stages"))
        self.assertEqual(before, regular_file_inventory(self.chain["variants"]["stages"]))
        for phase in fixture.PHASES:
            self.assertEqual(b"", (self.destination / "original-evidence/phases" / phase /
                                    "original/empty-diagnostic.log").read_bytes())
        self.assertFalse(any(self.context["private_key"].read_bytes() in path.read_bytes()
                             for path in self.destination.rglob("*") if path.is_file()))

    def test_verified_release_bytes_changed_before_copy_do_not_publish(self):
        def mutate_before_copy(source, destination, *, allow_empty, expected_inventory):
            (source / "caller.json").write_bytes(b"changed after verification\n")
            actual_publish_regular_tree(source, destination, allow_empty=allow_empty,
                                        expected_inventory=expected_inventory)

        with patch("reuse.api_request", side_effect=self.source.api()), \
                patch.object(runtime_release, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_retired_exact_handoff_needs_no_active_key_secret_or_http(self):
        original = self.keyring.read_bytes()
        self.keyring.write_bytes(canonical_json_bytes({**self.policy, "activeKey": None,
                                                       "retiredKeys": [self.policy["activeKey"]]}))
        retired_pin = self.commit_policy()
        try:
            before = regular_file_inventory(self.handoff)
            self.environment.forbid_secret = True
            with patch("reuse.api_request", side_effect=AssertionError("HTTP on complete reuse")), \
                    patch("products.runtime_attestation.sign_manifest", side_effect=AssertionError("resigning")):
                self.invoke(trusted_source_sha=retired_pin, release_handoffs=(self.handoff,), token=None)
            self.assertEqual(0, self.environment.secret_reads)
            self.assertEqual(before, regular_file_inventory(self.destination / "runtime-input"))
        finally:
            self.keyring.write_bytes(original)
            type(self).pin = self.commit_policy()

    def test_bad_semantics_or_context_never_reads_secret_or_publishes(self):
        self.environment.forbid_secret = True
        self.event["pull_request"]["draft"] = True
        with patch("reuse.api_request", side_effect=AssertionError("unauthorized HTTP")), self.assertRaises(ValueError):
            self.invoke()
        self.event["pull_request"]["draft"] = False
        header = self.chain["variants"]["stages"] / TARGET / "validation/outputs/c-abi-reference/include/codex_agent.h"
        original = header.read_bytes()
        try:
            header.write_bytes(original + b"tamper")
            with patch("reuse.api_request", side_effect=self.source.api()), self.assertRaises(ValueError):
                self.invoke()
        finally:
            header.write_bytes(original)
        self.assertFalse(self.destination.exists())
        self.assertEqual(0, self.environment.secret_reads)

    def test_uncovered_ci_phases_require_token_before_http_or_secret(self):
        self.environment.forbid_secret = True
        with patch("reuse.api_request", side_effect=AssertionError("unauthenticated observation")), \
                self.assertRaisesRegex(ValueError, "token for uncovered phases"):
            self.invoke(token=None)
        self.assertEqual(0, self.environment.secret_reads)
        self.assertFalse(self.destination.exists())

    def test_selected_receipt_bindings_cannot_be_crosspaired(self):
        self.environment.forbid_secret = True
        for changes in (
            {"expected_contract_receipt_sha256": "sha256:" + "0" * 64},
            {"expected_receipt_sha256s": {phase: "sha256:" + "0" * 64 for phase in fixture.PHASES}},
        ):
            with self.subTest(changes=changes), \
                    patch("reuse.api_request", side_effect=AssertionError("HTTP before selected receipt binding")), \
                    self.assertRaisesRegex(ValueError, "selected original"):
                self.invoke(**changes)
            self.assertFalse(self.destination.exists())
        self.assertEqual(0, self.environment.secret_reads)

    def test_retained_forwarding_uses_verified_bytes_not_a_later_source_read(self):
        real_read = runtime_release.read_runtime_variant_handoff
        changed = []

        def replace_after_verification(path, **kwargs):
            verified = real_read(path, **kwargs)
            payload = path / verified["attestation"]["payload"]["fileName"]
            changed.append((payload, payload.read_bytes()))
            payload.write_bytes(b"unverified replacement after reader returned")
            return verified

        def restore_before_original_recheck(path, **kwargs):
            # Model an ABA source swap: the final original-inventory check cannot
            # distinguish it; only forwarding the verified snapshot is safe.
            for payload, raw in changed:
                payload.write_bytes(raw)
            changed.clear()
            return regular_file_inventory(path, **kwargs)

        self.environment.forbid_secret = True
        with patch("reuse.api_request", side_effect=AssertionError("HTTP on complete reuse")), \
                patch.object(runtime_release, "read_runtime_variant_handoff", side_effect=replace_after_verification), \
                patch.object(runtime_release, "regular_file_inventory", side_effect=restore_before_original_recheck):
            self.invoke(release_handoffs=(self.handoff,), token=None)
        self.assertEqual(regular_file_inventory(self.handoff),
                         regular_file_inventory(self.destination / "runtime-input"))
        self.assertEqual(0, self.environment.secret_reads)


if __name__ == "__main__":
    unittest.main()
