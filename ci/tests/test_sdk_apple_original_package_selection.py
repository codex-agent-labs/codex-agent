"""Selected Apple original-source orchestration; official APIs and full gate are mocked."""

from contextlib import contextmanager, ExitStack
from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sdk_apple_original_package_selection as selection
from products.inventory import canonical_json_bytes, write_canonical_json
from products.receipt import write_output_manifest
from products.restore import finalize_phase_object
from tests.product_chain_support import write_receipt


class OriginalApplePackageSelectionTest(unittest.TestCase):
    def setUp(self):
        checkout = tempfile.TemporaryDirectory(prefix="apple-selection-checkout-")
        scratch = tempfile.TemporaryDirectory(prefix="apple-selection-scratch-")
        self.addCleanup(checkout.cleanup)
        self.addCleanup(scratch.cleanup)
        self.repo, self.scratch = Path(checkout.name).resolve(), Path(scratch.name).resolve()
        self.producer = {"repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 71, "runAttempt": 2, "pullRequest": 31}
        stage = self.repo / "fixture-stage"
        (stage / "outputs/apple").mkdir(parents=True)
        (stage / "outputs/apple/package.zip").write_bytes(b"synthetic original package")
        manifest = write_output_manifest(stage, "sdk", "sdk-ios", "package", "ios", "0.8.0",
                                         {"apple": "outputs/apple"})
        receipt_path = self.repo / "fixture-receipt.json"
        receipt = write_receipt(receipt_path, product="sdk", component="sdk-ios", phase="package",
            target="ios", version="0.8.0", version_identity="0.8.0", outputs=manifest["outputs"],
            upstream=[], context={"producer": self.producer})
        phase = {name: receipt[name] for name in (
            "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
        self.package_upload = self.repo / "fixture-package-upload"
        original = self.package_upload / "original"
        original.mkdir(parents=True)
        finalized = finalize_phase_object(stage_root=stage, phase_plan=phase,
            producer=self.producer, product_version="0.8.0", trust_domain="development",
            destination=original / "shard")
        self.raw = finalized["receiptBytes"]
        self.envelope = {"receipt": finalized["receipt"], "receiptBytes": self.raw,
            "receiptSha256": finalized["receiptSha256"], "objectSha256": finalized["objectSha256"]}
        write_canonical_json(original / "apple-package-execution.json", {
            "sdkInputsArtifact": {"artifactId": 811, "artifactSha256": "sha256:" + "8" * 64}})
        original_plan = b'{"synthetic":"original impact plan, not hosted evidence"}\n'
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("impact-plan.json", original_plan)
        self.plan_zip = buffer.getvalue()
        self.events = []
        self.validated_plan = {"remoteBuildAuthorized": True, "event": "pull_request"}

    def selector(self, **options):
        return selection.OriginalApplePackageSelector(self.scratch,
            repository_root=self.repo, trusted_workflow_sha="c" * 40,
            keyring=self.repo / "keyring.json", keys_directory=self.repo / "keys",
            tooling_evidence=self.repo / "tooling", tooling_public_key=self.repo / "tooling.pub",
            java_executable=self.repo / "java", policy_revision="d" * 40,
            required_trust_domain="development", environ={}, token="synthetic", **options)

    @contextmanager
    def mocked_original_gate(self, plan, receipt, **options):
        self.assertEqual(self.raw, Path(receipt).read_bytes())
        self.assertEqual(self.validated_plan, selection.product_reuse._validate_plan(plan, self.repo,
            expected_revision=self.producer["commit"]))
        self.assertTrue(options["ephemeral_capture"])
        self.assertEqual(self.producer["commit"], options["expected_plan_revision"])
        self.last_options = options
        self.events.append("full-gate-enter")
        try:
            yield {"original": self.package_upload / "original"}
        finally:
            self.events.append("full-gate-exit")

    def patch_sources(self):
        stack = ExitStack()
        stack.enter_context(patch.object(selection.product_reuse, "api_json", return_value={"synthetic": "original run"}))
        stack.enter_context(patch.object(selection.product_reuse, "_runtime_prior_workflow_sha", return_value="c" * 40))
        stack.enter_context(patch('sdk_handoff._ensure_observed_sdk_commit'))
        stack.enter_context(patch.object(selection.product_reuse, "_observe_ci_producer_jobs",
            return_value=[{"run": {"head_sha": self.producer["commit"]}, "jobs": []}]))
        stack.enter_context(patch.object(selection.product_reuse, "paginated_items", return_value=[]))
        stack.enter_context(patch.object(selection, "_original_upload", return_value=({"id": 701}, self.plan_zip)))
        stack.enter_context(patch.object(selection.product_reuse, "_validate_plan", return_value=self.validated_plan))
        stack.enter_context(patch.object(selection.product_reuse, "_consumer", return_value={"producer": self.producer}))
        stack.enter_context(patch.object(selection, "locate_original_apple_upload",
            return_value={"artifact_id": 801, "artifact_sha256": "sha256:" + "7" * 64}))
        for name in ("capture_sdk_ios_package_upload", "capture_sdk_inputs_upload"):
            stack.enter_context(patch.object(selection.product_reuse, name,
                side_effect=AssertionError("selector must not duplicate the full gate's body capture")))
        return stack

    def test_original_selection_defers_bodies_to_one_complete_gate(self):
        with self.patch_sources(), patch("ci.sdk_ios_original_package.verified_original_ios_package",
                self.mocked_original_gate):
            admission = self.selector()(self.envelope)
            self.assertIs(type(admission), selection.ApplePackageAdmission)
            self.assertEqual([], self.events)
            admission.verify(self.envelope)
        self.assertEqual(["full-gate-enter", "full-gate-exit"], self.events)

    def test_retired_reviewed_workflow_and_original_revision_reach_full_gate(self):
        original = "e" * 40
        with self.patch_sources(), patch.object(selection.product_reuse,
                "_runtime_prior_workflow_sha", return_value=original), patch(
                "ci.sdk_ios_original_package.verified_original_ios_package", self.mocked_original_gate):
            self.selector()(self.envelope).verify(self.envelope)
        self.assertEqual(original, self.last_options["trusted_workflow_sha"])

    def test_unreviewed_original_workflow_fails_before_source_capture(self):
        with self.patch_sources(), patch.object(selection.product_reuse,
                "_runtime_prior_workflow_sha", return_value=None), patch.object(selection.product_reuse,
                "_observe_ci_producer_jobs") as observe, self.assertRaisesRegex(ValueError, "reviewed producer workflow"):
            self.selector()(self.envelope)
        observe.assert_not_called()

    def test_authenticated_original_source_is_provisioned_before_historical_plan_validation(self):
        events=[]
        def provision(root, producer, token):
            self.assertEqual(self.repo, root)
            self.assertEqual(self.producer, producer)
            self.assertEqual('synthetic', token)
            events.append('source')
        def validate(*args, **kwargs):
            self.assertEqual(['source'], events)
            return self.validated_plan
        with self.patch_sources(), patch('sdk_handoff._ensure_observed_sdk_commit', side_effect=provision), \
                patch.object(selection.product_reuse, '_validate_plan', side_effect=validate):
            self.selector()(self.envelope)

    def test_original_reader_keeps_independent_caller_source_snapshot(self):
        source = {'artifactId': 711, 'artifactSha256': 'sha256:'+'1'*64,
                  'producer': dict(self.producer), 'workflowSha': '2'*40}
        expected = canonical_json_bytes(source)
        factory = self.selector(retained_sdk_inputs_source=source)
        source['artifactId'] = 999
        with self.patch_sources(), patch('ci.sdk_ios_original_package.verified_original_ios_package', self.mocked_original_gate):
            factory(self.envelope).verify(self.envelope)
        self.assertEqual(expected, canonical_json_bytes(self.last_options['retained_sdk_inputs_source']))

    def test_wrong_original_plan_producer_fails_before_package_gate(self):
        self.validated_plan = {"remoteBuildAuthorized": False, "event": "pull_request"}
        with self.patch_sources(), patch('ci.sdk_ios_original_package.verified_original_ios_package') as gate, \
                self.assertRaisesRegex(ValueError, "original plan|Original Apple plan"):
            self.selector()(self.envelope)
        gate.assert_not_called()

    def test_wrong_original_object_cannot_pass_full_gate_binding(self):
        wrong = {**self.envelope, 'objectSha256': 'sha256:' + 'f' * 64}
        with self.patch_sources(), patch('ci.sdk_ios_original_package.verified_original_ios_package', self.mocked_original_gate), \
                self.assertRaisesRegex(ValueError, 'shard differs'):
            self.selector()(wrong).verify(wrong)
        self.assertIn('full-gate-exit', self.events)

    def test_failure_when_full_gate_exits_cannot_become_admission(self):
        @contextmanager
        def failed_exit(*args, **kwargs):
            yield {'original': self.package_upload / 'original'}
            raise ValueError('full original gate rejected')
        with self.patch_sources(), patch('ci.sdk_ios_original_package.verified_original_ios_package', failed_exit), \
                self.assertRaisesRegex(ValueError, 'full original gate rejected'):
            self.selector()(self.envelope).verify(self.envelope)

    def test_non_package_envelope_rejected_before_observation(self):
        wrong = {**self.envelope, "receipt": {**self.envelope["receipt"], "phase": "binary"}}
        with patch.object(selection.product_reuse, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
            self.selector()(wrong)
        observe.assert_not_called()


class CallerOriginalSelectorContextTest(unittest.TestCase):
    """Synthetic authority fixtures only; no hosted Apple proof is asserted."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="apple-caller-context-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"synthetic current plan")
        self.keyring = self.root / "keyring.json"
        self.keyring.write_bytes(b"synthetic tracked keyring")
        self.keys = self.root / "keys"
        self.keys.mkdir()
        (self.keys / "release.pub").write_bytes(b"synthetic tracked key")
        self.tooling = self.root / "tooling"
        self.tooling.mkdir()
        (self.tooling / "receipt.json").write_bytes(b"synthetic tooling evidence")
        self.tooling_keyring = self.root / "tooling-keyring.json"
        self.tooling_keyring.write_bytes(b"synthetic tooling keyring")
        self.tooling_keys = self.root / "tooling-keys"
        self.tooling_keys.mkdir()
        (self.tooling_keys / "key.pub").write_bytes(b"synthetic tooling key")
        self.tooling_public = self.root / "tooling.pub"
        self.tooling_public.write_bytes(b"synthetic tooling public key")
        self.java = self.root / "java"
        self.java.write_bytes(b"synthetic Java executable")
        self.policy = {"plan": str(self.plan), "attestationPublicKey": None,
            "attestationTrustDomain": "release", "keyring": str(self.keyring),
            "keysDirectory": str(self.keys), "toolingEvidence": str(self.tooling),
            "toolingPublicKey": str(self.tooling_public), "javaExecutable": str(self.java),
            "toolingTrustDomain": "release", "toolingKeyring": str(self.tooling_keyring),
            "toolingKeysDirectory": str(self.tooling_keys)}
        self.revision, self.tree = "a" * 40, "b" * 40

    def _trust(self, _root, _revision, destination):
        keyring = destination / "trust/product-signing-keys.json"
        keys = destination / "trust/keys"
        keys.mkdir(parents=True)
        keyring.write_bytes(self.keyring.read_bytes())
        (keys / "release.pub").write_bytes((self.keys / "release.pub").read_bytes())
        return SimpleNamespace(keyring=keyring, keys=keys)

    def caller(self, **options):
        return selection.caller_original_apple_package_selector(self.plan, self.policy,
            repository_root=self.root, trusted_workflow_sha="c" * 40,
            environ={}, token="synthetic", **options)

    def mocked_current_authority(self):
        stack = ExitStack()
        stack.enter_context(patch.object(selection.product_reuse, "_validate_plan",
            return_value={"validationCommit": self.revision, "validationTree": self.tree}))
        stack.enter_context(patch.object(selection.product_reuse, "_git_value",
            side_effect=lambda _root, _command, selector:
                self.revision if selector == "HEAD^{commit}" else self.tree))
        stack.enter_context(patch.object(selection.product_reuse, "_release_trust", side_effect=self._trust))
        return stack

    def test_context_keeps_external_scratch_alive_through_selector_use(self):
        with self.mocked_current_authority(), self.caller() as factory:
            self.assertIs(type(factory), selection.OriginalApplePackageSelector)
            scratch = factory._scratch
            self.assertTrue(scratch.is_dir())
            self.assertFalse(self.root in scratch.parents)
            self.assertEqual(self.revision, factory._policy["policy_revision"])
        self.assertFalse(scratch.exists())

    def test_plan_mutation_during_reuse_fails_on_exit(self):
        with self.mocked_current_authority(), self.assertRaisesRegex(ValueError, "changed during reuse"):
            with self.caller():
                self.plan.write_bytes(b"mutated plan")

    def test_tooling_mutation_during_reuse_fails_on_exit(self):
        with self.mocked_current_authority(), self.assertRaisesRegex(ValueError, "changed during reuse"):
            with self.caller():
                (self.tooling / "receipt.json").write_bytes(b"mutated evidence")

    def test_policy_mutation_during_reuse_fails_on_exit(self):
        with self.mocked_current_authority(), self.assertRaisesRegex(ValueError, "changed during reuse"):
            with self.caller():
                self.policy["toolingTrustDomain"] = "development"

    def test_sdk_source_policy_mutation_during_reuse_fails_on_exit(self):
        source = {'artifactId': 711}
        with self.mocked_current_authority(), self.assertRaisesRegex(ValueError, 'changed during reuse'):
            with self.caller(retained_sdk_inputs_source=source):
                source['artifactId'] = 999

    def test_caller_keyring_must_match_current_git(self):
        self.keyring.write_bytes(b"untracked impostor keyring")
        with self.mocked_current_authority(), patch.object(selection.product_reuse,
                "_release_trust", side_effect=self._different_trust), \
                self.assertRaisesRegex(ValueError, "differ from current Git"):
            with self.caller():
                pass

    def _different_trust(self, _root, _revision, destination):
        trust = self._trust_copy(destination)
        trust.keyring.write_bytes(b"original Git keyring")
        return trust

    def _trust_copy(self, destination):
        keyring = destination / "trust/product-signing-keys.json"
        keys = destination / "trust/keys"
        keys.mkdir(parents=True)
        keyring.write_bytes(self.keyring.read_bytes())
        (keys / "release.pub").write_bytes((self.keys / "release.pub").read_bytes())
        return SimpleNamespace(keyring=keyring, keys=keys)


if __name__ == "__main__":
    unittest.main()
