"""Android package policy must be independent of retained binary authority."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_android_package_policy as android
from ci import sdk_core_package_policy as policy
from products.registry import PhaseInstanceId

_BINARY = PhaseInstanceId("sdk", "sdk-android", "binary", "android")
_PACKAGE = PhaseInstanceId("sdk", "sdk-android", "package", "android")


_DIGEST = "sha256:" + "a" * 64


class AndroidPackagePolicyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve(strict=True)
        self.root = base / "checkout"
        self.root.mkdir()
        self.discovery = self.root / "build/capture/original/product-resume-state"
        self.state = self.root / "build/capture/original/runtime-state"
        self.discovery.mkdir(parents=True)
        self.state.mkdir(parents=True)
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"plan\n")
        self.archive = base / "codex-arm64.tar.gz"
        self.archive.write_bytes(b"pinned Android archive")
        self.destination = base / "caller-policy"
        self.context = {"repositoryRoot": str(self.root),
                        "workerRoot": str(self.root / "build/sdk-android-maven-worker")}
        handoff = self.discovery / "authenticated-contract/contract-input"
        handoff.mkdir(parents=True)
        self.source = {}
        for name, filename in (("attestation", "codex-agent-contract-0.8.0.attestation.json"),
                               ("attestationSignature", "codex-agent-contract-0.8.0.attestation.sig"),
                               ("publicKey", "public-key.pub")):
            path = handoff / filename
            path.write_bytes(name.encode())
            self.source[name] = path.relative_to(self.root).as_posix()
        keyring = self.discovery / "keyring"
        keyring.write_bytes(b"keyring")
        self.source["keyring"] = keyring.relative_to(self.root).as_posix()
        key_dir = self.discovery / "keys"
        key_dir.mkdir()
        (key_dir / "active.pub").write_bytes(b"key")
        self.source["keysDirectory"] = key_dir.relative_to(self.root).as_posix()
        self.source["expectedTrustDomain"] = "release"
        (handoff / "codex-agent-contract-0.8.0.zip").write_bytes(b"payload")
        closure = handoff / "execution-closure/receipts"
        closure.mkdir(parents=True)
        self.receipt = {"product": "contract", "component": "contract", "phase": "metadata",
                        "target": "common", "productVersion": "0.8.0",
                        "outputs": [{"kind": "contract-bundle", "relativePath": "outputs/contract.zip"}]}
        self.receipt_bytes = policy.canonical_json_bytes(self.receipt)
        (closure / "metadata.json").write_bytes(self.receipt_bytes)
        self.verified = SimpleNamespace(
            producer={"runId": 1, "runAttempt": 1}, completed_frozen=None,
            capture_deferred_object=None, ensure_original_source=None,
            plan={"validationCommit": "b" * 40},
            prior_ready_plans={_PACKAGE: {"buildKey": _DIGEST}},
            prior_by_instance={_BINARY: {"state": "retained"}},
            sources={_BINARY: self.root / "binary-object.zip",
                     policy._CONTRACT: self.root / "contract-object.zip"},
            prior_carrier_phases={policy._CONTRACT: {"buildKey": _DIGEST,
                "receiptSha256": _DIGEST, "objectSha256": _DIGEST}},
            rebased_request={"contractEvidence": self.source},
        )

    def args(self, **changes):
        result = dict(plan=self.plan, discovery=self.discovery, state=self.state,
            destination=self.destination, expected_build_key=_DIGEST, binary_artifact_id=17,
            binary_artifact_sha256=_DIGEST,
            binary_original_context=policy.canonical_json_bytes(self.context).decode().strip(),
            android_runtime_archive=self.archive, trusted_workflow_sha="c" * 40,
            repository_root=self.root, environ={})
        result.update(changes)
        return result

    def fake_restore(self, archive, destination, **kwargs):
        if self.verified.completed_frozen is None:
            self.assertEqual(self.verified.sources[policy._CONTRACT], archive)
        self.assertEqual(_DIGEST, kwargs["object_sha256"])
        target = destination / "outputs/contract.zip"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"payload")
        return {"receiptBytes": self.receipt_bytes}

    def invoke(self, **changes):
        pinned = ("codexAgent.codexVersion=0.149.0\n"
                  "codexAgent.codexArchiveSha256=" + policy.sha256_file(self.archive)[7:] + "\n").encode()
        with (patch.object(policy.product_reuse, "_verified_product_state", return_value=self.verified) as replay,
              patch.object(policy, "git_regular_blob_bytes", return_value=pinned),
              patch.object(policy.product_reuse, "restore_object", side_effect=self.fake_restore),
              patch.object(policy, "validate_phase_receipt", return_value=self.receipt),
              patch.object(policy, "verify_output_manifest_identity", return_value={"outputs": self.receipt["outputs"]}),
              patch.object(policy, "verify_contract_attestation") as attestation):
            result = android.prepare(**self.args(**changes))
            self.assertEqual((_PACKAGE,), replay.call_args.kwargs['requested_scope'])
            if changes.get('completed_frozen') is not None:
                self.assertIs(changes['completed_frozen'], replay.call_args.kwargs['completed_frozen'])
            attestation.assert_called_once()
            return result

    def test_policy_binds_original_contract_archive_and_context_without_binary_object(self):
        result = self.invoke()
        evidence = policy.load_canonical_json_bytes(Path(result["binary-contract-evidence"]).read_bytes())
        self.assertEqual(str(self.destination / "contract-contract-metadata-common/stage"), evidence["stageRoot"])
        self.assertEqual(str(self.destination / "contract-contract-metadata-common/phase-receipt.json"), evidence["phaseReceipt"])
        self.assertEqual(self.context, policy.load_canonical_json_bytes(
            Path(result["binary-original-context"]).read_bytes()))
        self.assertEqual(str(self.archive), result["android-runtime-archive"])
        self.assertFalse((self.root / "binary-object.zip").exists())

    def test_native_capability_is_forwarded_to_scoped_existing_replay(self):
        # An opaque sentinel only verifies plumbing; production replay remains
        # responsible for concrete type, signatures, originals and current keys.
        self.invoke(completed_frozen=object())

    def test_native_binary_uses_exact_reviewed_original_without_fetching_it(self):
        from ci.tests.test_products import phase_receipt
        from products.receipt import compute_build_key
        receipt = {**phase_receipt(), 'product': 'sdk', 'component': 'sdk-android',
                   'phase': 'binary', 'target': 'android'}
        receipt['buildKey'] = compute_build_key(**{name: receipt[name] for name in
            ('product', 'component', 'phase', 'target', 'inputs')})
        raw = policy.canonical_json_bytes(receipt)
        record = {**{name: receipt[name] for name in ('product', 'component', 'phase', 'target', 'buildKey')},
                  'receiptSha256': policy.sha256_bytes(raw), 'objectSha256': _DIGEST}
        import reuse_qualification as native
        cap = native.CompletedFrozenReuse({'expectedResult': {'phases': [record]}}, [receipt],
            native._COMPLETED_FROZEN, revision=receipt['producer']['commit'])
        self.verified.prior_by_instance[_BINARY]['buildKey'] = receipt['buildKey']
        self.verified.prior_carrier_phases[_BINARY] = record
        # Original runner paths must survive even when today's checkout differs.
        context = {'repositoryRoot': '/home/runner/work/codex-agent/codex-agent',
                   'workerRoot': '/home/runner/work/codex-agent/codex-agent/build/sdk-android-maven-worker'}
        origin = dict(producer=receipt['producer'], artifact_id=27, artifact_sha256=_DIGEST,
                      receipt_sha256=policy.sha256_bytes(raw), context=context)
        arguments = dict(binary_artifact_id=None, binary_artifact_sha256=None,
                         binary_original_context=None, completed_frozen=cap)
        with patch.object(policy, 'locate_retained_core_binary_upload', return_value=origin) as locate:
            for wrong in (None, {**origin, 'receipt_sha256': 'sha256:' + 'f' * 64},
                          {**origin, 'producer': {**receipt['producer'], 'runId': 99}}):
                with self.subTest(origin=wrong):
                    locate.return_value = wrong
                    with self.assertRaisesRegex(ValueError, 'independently reviewed original'):
                        self.invoke(**arguments)
                    self.assertFalse(self.destination.exists())
            locate.return_value = origin
            result = self.invoke(**arguments)
        self.assertEqual('27', result['binary-artifact-id'])
        self.assertEqual(_DIGEST, result['binary-artifact-sha256'])
        self.assertEqual(context, policy.load_canonical_json_bytes(
            Path(result['binary-original-context']).read_bytes()))
        locate.assert_called_with(self.plan, self.root, expected_build_key=receipt['buildKey'],
            token='', environ={}, component='sdk-android', target='android')
        self.assertFalse(self.verified.sources[_BINARY].exists())

    def test_partial_origin_or_absent_native_authority_rejects_before_replay(self):
        absent = dict(binary_artifact_id=None, binary_artifact_sha256=None, binary_original_context=None)
        for changes in ({'binary_artifact_id': None}, {'binary_artifact_sha256': None},
                        {'binary_original_context': None}, absent, {**absent, 'completed_frozen': object()}):
            with self.subTest(changes=changes), patch.object(policy.product_reuse, '_verified_product_state') as replay:
                with self.assertRaises(ValueError):
                    android.prepare(**self.args(**changes))
                replay.assert_not_called()

    def test_android_cli_uses_shared_policy_and_optional_origin(self):
        arguments = []
        for name, value in self.args().items():
            if name in {'environ', 'binary_artifact_id', 'binary_artifact_sha256', 'binary_original_context'}:
                continue
            name = {'discovery': 'discovery-root', 'state': 'state-root'}.get(name, name.replace('_', '-'))
            arguments.extend(('--' + name, str(value)))
        with patch.object(policy, 'prepare', return_value={}) as prepare:
            self.assertEqual(0, android.main(arguments))
        self.assertEqual('sdk-android', prepare.call_args.kwargs['component'])
        self.assertEqual(self.archive, prepare.call_args.kwargs['android_runtime_archive'])
        self.assertIsNone(prepare.call_args.kwargs['binary_artifact_id'])

    def test_deferred_contract_uses_shared_reader_without_fetching_binary(self):
        from unittest.mock import Mock
        def capture(record, destination):
            self.assertEqual(self.verified.prior_carrier_phases[policy._CONTRACT], record)
            destination.write_bytes(b'authenticated deferred Contract object')
        self.verified.completed_frozen = object()
        self.verified.capture_deferred_object = Mock(side_effect=capture)
        self.invoke(completed_frozen=self.verified.completed_frozen)
        self.verified.capture_deferred_object.assert_called_once()
        self.assertFalse(self.verified.sources[_BINARY].exists())

    def test_reused_or_missing_current_binary_fails_closed(self):
        for value in ("reused", "missing"):
            with self.subTest(value=value):
                self.verified.prior_by_instance[_BINARY]["state"] = value
                with self.assertRaisesRegex(ValueError, "retained binary"):
                    self.invoke()
        self.assertFalse(self.destination.exists())

    def test_archive_and_caller_context_must_be_independent_and_exact(self):
        different = self.archive.parent / "different.tar.gz"
        different.write_bytes(b"wrong archive")
        with self.assertRaisesRegex(ValueError, "immutable candidate Git pin"):
            self.invoke(android_runtime_archive=different)
        with self.assertRaisesRegex(ValueError, "separate normalized caller file"):
            self.invoke(android_runtime_archive=self.plan)
        with self.assertRaisesRegex(ValueError, "same-campaign worker"):
            self.invoke(binary_original_context=policy.canonical_json_bytes({
                **self.context, "workerRoot": str(self.root / "build/other")}).decode().strip())
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            self.invoke(binary_original_context=json.dumps(self.context, indent=2))
        self.assertFalse(self.destination.exists())

    def test_missing_original_authority_or_contract_mismatch_fails(self):
        with self.assertRaises(ValueError):
            self.invoke(binary_artifact_id=0)
        self.verified.rebased_request["contractEvidence"] = None
        with self.assertRaisesRegex(ValueError, "authenticated release Contract"):
            self.invoke()
        self.verified.rebased_request["contractEvidence"] = self.source
        handoff = self.discovery / "authenticated-contract/contract-input"
        (handoff / "codex-agent-contract-0.8.0.zip").write_bytes(b"different")
        with self.assertRaisesRegex(ValueError, "metadata differs"):
            self.invoke()
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
