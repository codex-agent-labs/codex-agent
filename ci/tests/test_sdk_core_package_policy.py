"""Same-campaign Core policy must not recover caller authority from binary bytes."""

import json
import os
from contextlib import contextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_core_package_policy as policy

canonical_json_bytes = policy.canonical_json_bytes
load_canonical_json_bytes = policy.load_canonical_json_bytes


_DIGEST = "sha256:" + "a" * 64


class CorePackagePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name).resolve(strict=True)
        self.root = base / "checkout"
        self.root.mkdir()
        self.discovery = self.root / "build/capture/original/product-resume-state"
        self.state = self.root / "build/capture/original/runtime-state"
        self.discovery.mkdir(parents=True)
        self.state.mkdir(parents=True)
        self.plan = self.root / "impact-plan.json"
        self.plan.write_bytes(b"plan\n")
        self.destination = base / "caller-policy"
        self.context = {"repositoryRoot": str(self.root),
                        "workerRoot": str(self.root / "build/sdk-core-maven-worker")}
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
        self.receipt_bytes = canonical_json_bytes(self.receipt)
        (closure / "metadata.json").write_bytes(self.receipt_bytes)
        self.verified = SimpleNamespace(
            producer={"runId": 1, "runAttempt": 1},
            capture_deferred_object=None, ensure_original_source=None,
            prior_ready_plans={policy._PACKAGE: {"buildKey": _DIGEST}},
            prior_by_instance={policy._BINARY: {"state": "retained"}},
            sources={policy._BINARY: self.root / "binary-object.zip",
                     policy._CONTRACT: self.root / "contract-object.zip"},
            prior_carrier_phases={policy._CONTRACT: {"buildKey": _DIGEST,
                "receiptSha256": _DIGEST, "objectSha256": _DIGEST}},
            rebased_request={"contractEvidence": self.source},
            completed_frozen=None,
        )

    def args(self, **changes):
        result = dict(plan=self.plan, discovery=self.discovery, state=self.state,
            destination=self.destination, expected_build_key=_DIGEST, binary_artifact_id=17,
            binary_artifact_sha256=_DIGEST,
            binary_original_context=canonical_json_bytes(self.context).decode().strip(),
            trusted_workflow_sha="b" * 40, repository_root=self.root, environ={})
        result.update(changes)
        return result

    def fake_restore(self, archive, destination, **kwargs):
        self.assertEqual(self.verified.sources[policy._CONTRACT], archive)
        self.assertEqual(_DIGEST, kwargs["object_sha256"])
        target = destination / "outputs/contract.zip"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"payload")
        return {"receiptBytes": self.receipt_bytes}

    def invoke(self, **changes):
        with (patch.object(policy.product_reuse, "_verified_product_state", return_value=self.verified) as replay,
              patch.object(policy.product_reuse, "restore_object", side_effect=self.fake_restore),
              patch.object(policy, "validate_phase_receipt", return_value=self.receipt),
              patch.object(policy, "verify_output_manifest_identity", return_value={"outputs": self.receipt["outputs"]}),
              patch.object(policy, "verify_contract_attestation") as attestation):
            result = policy.prepare(**self.args(**changes))
            self.assertEqual((policy._PACKAGE,), replay.call_args.kwargs['requested_scope'])
            if changes.get('completed_frozen') is not None:
                self.assertIs(changes['completed_frozen'], replay.call_args.kwargs['completed_frozen'])
            attestation.assert_called_once()
            return result

    def test_native_checkpoint_resolves_reviewed_original_without_current_upload(self):
        import reuse_qualification as native
        from ci.tests.test_products import phase_receipt
        from products.receipt import compute_build_key
        from products.inventory import sha256_bytes
        receipt = {**phase_receipt(), 'product': 'sdk', 'component': 'sdk-core',
                   'phase': 'binary', 'target': 'common'}
        receipt['buildKey'] = compute_build_key(**{name: receipt[name] for name in
            ('product', 'component', 'phase', 'target', 'inputs')})
        record = {**{name: receipt[name] for name in ('product', 'component', 'phase', 'target', 'buildKey')},
                  'receiptSha256': sha256_bytes(canonical_json_bytes(receipt)), 'objectSha256': _DIGEST}
        cap = native.CompletedFrozenReuse({'expectedResult': {'phases': [record]}}, [receipt],
            native._COMPLETED_FROZEN, revision=receipt['producer']['commit'])
        self.verified.prior_by_instance[policy._BINARY]['buildKey'] = receipt['buildKey']
        self.verified.prior_carrier_phases[policy._BINARY] = record
        origin = dict(producer=receipt['producer'], artifact_id=27,
                      artifact_sha256=_DIGEST, context=self.context)
        with patch.object(policy, 'locate_retained_core_binary_upload', return_value=origin) as locate:
            result = self.invoke(binary_artifact_id=None, binary_artifact_sha256=None,
                                 binary_original_context=None, completed_frozen=cap)
        self.assertEqual('27', result['binary-artifact-id'])
        self.assertEqual(_DIGEST, result['binary-artifact-sha256'])
        locate.assert_called_once_with(self.plan, self.root,
            expected_build_key=receipt['buildKey'], token='', environ={})

    def test_partial_original_and_unqualified_native_state_fail_before_replay(self):
        for arguments in ({'binary_artifact_id': None},
                          {'binary_artifact_sha256': None},
                          {'binary_artifact_id': None, 'binary_artifact_sha256': None,
                           'binary_original_context': None, 'completed_frozen': object()}):
            with self.subTest(arguments=arguments), \
                    patch.object(policy.product_reuse, '_verified_product_state') as replay, \
                    self.assertRaises(ValueError):
                policy.prepare(**self.args(**arguments))
            replay.assert_not_called()

    def test_plan_mutation_rejects_policy_publication(self):
        with (patch.object(policy.product_reuse, '_verified_product_state', return_value=self.verified),
              patch.object(policy.product_reuse, 'restore_object', side_effect=self.fake_restore),
              patch.object(policy, 'validate_phase_receipt', return_value=self.receipt),
              patch.object(policy, 'verify_output_manifest_identity', return_value={'outputs': self.receipt['outputs']}),
              patch.object(policy, 'verify_contract_attestation', side_effect=lambda *a, **k: self.plan.write_bytes(b'changed')),
              self.assertRaisesRegex(ValueError, 'plan or authenticated state changed')):
            policy.prepare(**self.args())
        self.assertFalse(self.destination.exists())

    def test_cli_keeps_plan_for_native_authentication_and_forwards_capability(self):
        capability = object()
        @contextmanager
        def native(arguments):
            self.assertEqual(self.plan, arguments['plan'])
            self.assertEqual(self.root / 'policy.json', arguments.pop('completed_frozen_policy'))
            yield {'completed_frozen': capability}
        arguments = []
        for name, value in self.args().items():
            if name == 'environ':
                continue
            name = {'discovery': 'discovery-root', 'state': 'state-root'}.get(name, name.replace('_', '-'))
            arguments.extend(('--' + name, str(value)))
        arguments.extend(('--completed-frozen-policy', str(self.root / 'policy.json')))
        with patch.object(policy, 'completed_frozen_options', side_effect=native), \
                patch.object(policy, 'prepare', return_value={}) as prepare:
            self.assertEqual(0, policy.main(arguments))
        self.assertIs(capability, prepare.call_args.kwargs['completed_frozen'])
        self.assertEqual(self.plan, prepare.call_args.kwargs['plan'])

    def test_combined_capture_and_policy_share_native_authority_and_withhold_failed_outputs(self):
        self._exercise_combined_capture()

    def test_worker_election_reuses_capture_authority_and_pins_policies_until_success(self):
        self._exercise_combined_capture(elect=True)

    def _exercise_combined_capture(self, *, elect=False):
        import reuse_qualification as native
        from ci.tests.test_sdk_checkpoint_core_issuer import CoreCheckpointIssuerTest
        fixture = CoreCheckpointIssuerTest(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        fixture.prepare(); fixture.add_new(); _, work = fixture.issue()
        fixture.promote(work); fixture.package_ready()
        f = fixture.f
        caller = f.root / "caller-plan.json"
        owner = f.root / "owner.json"
        completed = f.root / "completed.json"
        output = self.root.parent / "runner-output"
        completed.write_bytes(canonical_json_bytes({"schemaVersion": 1, "kind": "completed-frozen-reuse",
            "consumerCommit": "c" * 40, "verifierPolicySha256": _DIGEST,
            **f.policy["bootstrap"], "sdkCompletion": f.policy["bootstrap"]}))
        environment = {"GITHUB_REPOSITORY": native.REPOSITORY, "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_REF": "refs/pull/31/merge", "GITHUB_SHA": f.producer["commit"],
            "GITHUB_RUN_ID": str(f.producer["runId"]), "GITHUB_RUN_ATTEMPT": str(f.producer["runAttempt"]),
            "GITHUB_JOB": "sdk-core-package", "GITHUB_TOKEN": "synthetic", "GITHUB_OUTPUT": str(output)}
        faults = (None, "capture", "prepare", "late-plan", "late-owner")
        if elect: faults += ("matrix", "caller-policy", "prepared-policy", "capture-policy", "empty-election")
        tooling = f.root / "tooling.json"
        for fault in faults:
            with self.subTest(fault=fault):
                events = []; held = []
                capture_root = f.root / ("capture-" + str(fault))
                caller.write_text(f.spec["sourcePlan"])
                owner.write_bytes(canonical_json_bytes(f.policy))
                output.write_text(""); tooling.write_text("{}\n")
                argv = ["--plan", str(caller), "--capture-destination", str(capture_root),
                    "--capture-artifact-id", "2003", "--capture-artifact-sha256", _DIGEST,
                    "--capture-sdk-state-wave", "11", "--destination", str(self.destination),
                    "--repository-root", str(f.root), "--expected-build-key", _DIGEST,
                    "--trusted-workflow-sha", "c" * 40, "--github-output", str(output),
                    "--completed-frozen-policy", str(completed), "--sdk-checkpoint-owner", str(owner),
                    "--sdk-checkpoint", json.dumps(fixture.previous)]
                if elect:
                    argv += ["--elect-worker", "--binary-original-workflow-path", ".github/workflows/sdk-core-binary-validation.yml",
                        "--binary-original-job-name", "product-validation / sdk-core-binary-wave / sdk-core-binary-common",
                        "--sdk-validation-tooling", str(tooling)]
                def fetch(destination, **kwargs):
                    events.append("authenticate")
                    cap = fixture.c.capability(kwargs["_checkpoint"]); held.append(cap)
                    return cap, {}
                def capture(plan, destination, **kwargs):
                    events.append("capture")
                    self.assertIs(held[0], kwargs["completed_frozen"])
                    held[0].check_consumer(fixture.c.consumer)
                    self.assertEqual(caller, plan); self.assertEqual(capture_root, destination)
                    self.assertEqual(2003, kwargs["artifact_id"]); self.assertEqual(11, kwargs["sdk_state_wave"])
                    self.assertTrue(kwargs["allow_earlier_attempt"])
                    if fault == "capture": raise ValueError("capture failed")
                    if fault == "capture-policy": tooling.write_text('{"changed":true}\n')
                    for name in ("product-resume-state", "runtime-state"):
                        (destination / "original" / name).mkdir(parents=True)
                def prepare(**kwargs):
                    events.append("prepare")
                    self.assertIs(held[0], kwargs["completed_frozen"])
                    held[0].check_consumer(fixture.c.consumer)
                    self.assertEqual(caller, kwargs["plan"])
                    self.assertEqual(capture_root / "original/product-resume-state", kwargs["discovery"])
                    self.assertEqual(capture_root / "original/runtime-state", kwargs["state"])
                    self.assertNotIn("binary-artifact-id", output.read_text())
                    if fault == "prepare": raise ValueError("policy failed")
                    if fault == "late-plan": caller.write_text("{}\n")
                    if fault == "late-owner": owner.write_text("{}\n")
                    self.destination.mkdir(exist_ok=True)
                    (self.destination / "contract.json").write_text("{}\n")
                    (self.destination / "context.json").write_text("{}\n")
                    return {"binary-artifact-id": "2005", "binary-contract-evidence": str(self.destination / "contract.json"),
                        "binary-original-context": str(self.destination / "context.json")}
                def inspect(plan, discovery, state, **kwargs):
                    events.append("matrix")
                    self.assertIs(held[0], kwargs["completed_frozen"])
                    held[0].check_consumer(fixture.c.consumer)
                    self.assertEqual((policy._PACKAGE,), kwargs["requested_scope"])
                    self.assertNotIn("sdk_matrix=", output.read_text())
                    if fault == "matrix": raise ValueError("election failed")
                    if fault == "caller-policy": tooling.write_text('{"changed":true}\n')
                    if fault == "prepared-policy": (self.destination / "contract.json").write_text('{"changed":true}\n')
                    return {"readyPlans": [] if fault == "empty-election" else [dict(product="sdk", component="sdk-core",
                        phase="package", target="common", buildKey=_DIGEST)]}
                with fixture.boundaries(), patch.dict(os.environ, environment, clear=True), \
                        patch.object(policy.product_reuse, "_validate_plan", return_value=json.loads(f.spec["sourcePlan"])), \
                        patch.object(native, "fetch_completed_frozen", side_effect=fetch) as fetched, \
                        patch.object(policy.product_reuse, "capture_runtime_resume_upload", side_effect=capture), \
                        patch.object(policy, "prepare", side_effect=prepare), \
                        patch.object(policy.product_reuse, "inspect_products", side_effect=inspect):
                    before = len(f.downloads)
                    if fault in (None, "empty-election"):
                        self.assertEqual(0, policy.main(argv))
                    else:
                        with self.assertRaises(SystemExit) as rejected: policy.main(argv)
                        self.assertEqual(2, rejected.exception.code)
                    self.assertEqual(1, fetched.call_count)
                    self.assertEqual(1, len(f.downloads) - before)
                expected = ["authenticate", "capture"] + ([] if fault == "capture" else ["prepare"])
                if elect and fault not in ("capture", "prepare"): expected += ["matrix"]
                self.assertEqual(expected, events)
                successful = fault in (None, "empty-election")
                self.assertEqual(successful, "binary-artifact-id=2005\n" in output.read_text())
                self.assertEqual(elect and successful, "sdk_matrix=" in output.read_text())
                if elect and successful:
                    values = dict(line.split("=", 1) for line in output.read_text().splitlines())
                    self.assertEqual("false" if fault == "empty-election" else "true", values["sdk_workers_required"])
                    if fault is None:
                        self.assertEqual("ubuntu-24.04", json.loads(values["sdk_matrix"])["include"][0]["runner"])
                    fingerprints = {"SDK_VALIDATION_TOOLING": policy.sha256_bytes(tooling.read_bytes()),
                        "BINARY_CONTRACT_EVIDENCE": policy.sha256_bytes((self.destination / "contract.json").read_bytes()),
                        "BINARY_ORIGINAL_CONTEXT": policy.sha256_bytes((self.destination / "context.json").read_bytes()),
                        "BINARY_ORIGINAL_WORKFLOW_PATH": ".github/workflows/sdk-core-binary-validation.yml",
                        "BINARY_ORIGINAL_JOB_NAME": "product-validation / sdk-core-binary-wave / sdk-core-binary-common"}
                    self.assertEqual(policy.sha256_bytes(canonical_json_bytes(fingerprints)), values["policy_sha256"])
                with self.assertRaisesRegex(ValueError, "closed"): held[0].completed_phases()

    def test_worker_election_without_native_reuse_keeps_full_contract_policy_preparation(self):
        output = self.root.parent / "ordinary-output"; output.touch()
        args = self.args(); args.pop("environ"); args.pop("discovery"); args.pop("state")
        argv = [part for name, value in args.items() for part in ("--" + name.replace("_", "-"), str(value))]
        argv += ["--capture-destination", str(self.root / "build/capture"), "--capture-artifact-id", "91",
            "--capture-artifact-sha256", _DIGEST, "--capture-sdk-state-wave", "11", "--github-output", str(output),
            "--elect-worker", "--binary-original-workflow-path", ".github/workflows/sdk-core-binary-validation.yml",
            "--binary-original-job-name", "product-validation / sdk-core-binary-wave / sdk-core-binary-common"]
        def capture(plan, destination, **kwargs):
            self.assertEqual(self.plan, plan); self.assertEqual(self.root / "build/capture", destination)
            self.assertNotIn("completed_frozen", kwargs)
        ready = dict(product="sdk", component="sdk-core", phase="package", target="common", buildKey=_DIGEST)
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}, clear=True), \
                patch.object(policy.product_reuse, "capture_runtime_resume_upload", side_effect=capture) as captured, \
                patch.object(policy.product_reuse, "_verified_product_state", return_value=self.verified) as replay, \
                patch.object(policy.product_reuse, "restore_object", side_effect=self.fake_restore) as restored, \
                patch.object(policy, "validate_phase_receipt", return_value=self.receipt), \
                patch.object(policy, "verify_output_manifest_identity", return_value={"outputs": self.receipt["outputs"]}), \
                patch.object(policy, "verify_contract_attestation") as attestation, \
                patch.object(policy.product_reuse, "inspect_products", return_value={"readyPlans": [ready]}) as inspected:
            self.assertEqual(0, policy.main(argv))
        captured.assert_called_once(); replay.assert_called_once(); restored.assert_called_once(); attestation.assert_called_once()
        self.assertNotIn("completed_frozen", inspected.call_args.kwargs)
        self.assertEqual((policy._PACKAGE,), inspected.call_args.kwargs["requested_scope"])
        values = dict(line.split("=", 1) for line in output.read_text().splitlines())
        self.assertEqual("true", values["sdk_workers_required"]); self.assertEqual("17", values["binary-artifact-id"])
        self.assertEqual(b"payload", (self.destination / "contract-contract-metadata-common/stage/outputs/contract.zip").read_bytes())

    def test_incomplete_or_conflicting_capture_controls_fail_before_authentication(self):
        output = self.root.parent / "runner-output"
        args = ["--plan", str(self.plan), "--capture-destination", str(self.root / "capture"),
            "--capture-artifact-id", "17", "--capture-artifact-sha256", _DIGEST,
            "--destination", str(self.destination), "--repository-root", str(self.root),
            "--expected-build-key", _DIGEST, "--trusted-workflow-sha", "b" * 40,
            "--github-output", str(output)]
        for fault in ("partial", "both-sources", "orphan", "missing-output", "wrong-output", "overlap", "legacy-partial", "missing-route", "orphan-route", "election-without-capture"):
            with self.subTest(fault=fault):
                argv = list(args)
                if fault == "partial":
                    i = argv.index("--capture-artifact-id"); del argv[i:i+2]
                elif fault == "both-sources": argv += ["--discovery-root", str(self.discovery)]
                elif fault in ("orphan", "legacy-partial"):
                    for flag in ("--capture-destination", "--capture-artifact-id", "--capture-artifact-sha256"):
                        i = argv.index(flag); del argv[i:i+2]
                    argv += ["--discovery-root", str(self.discovery)]
                    if fault == "orphan": argv += ["--state-root", str(self.state), "--capture-state-wave", "0"]
                elif fault == "missing-output":
                    i = argv.index("--github-output"); del argv[i:i+2]
                elif fault == "wrong-output": argv[argv.index("--github-output")+1] = str(self.root / "wrong")
                elif fault == "overlap": argv[argv.index("--capture-destination")+1] = str(self.destination / "nested")
                elif fault == "missing-route": argv += ["--elect-worker"]
                elif fault == "orphan-route": argv += ["--binary-original-workflow-path", "path"]
                else:
                    for flag in ("--capture-destination", "--capture-artifact-id", "--capture-artifact-sha256"):
                        i = argv.index(flag); del argv[i:i+2]
                    argv += ["--discovery-root", str(self.discovery), "--state-root", str(self.state),
                        "--elect-worker", "--binary-original-workflow-path", "path", "--binary-original-job-name", "job"]
                with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output)}), \
                        patch.object(policy, "completed_frozen_options") as native, \
                        patch.object(policy, "prepare") as prepared, self.assertRaises(SystemExit) as rejected:
                    policy.main(argv)
                self.assertEqual(2, rejected.exception.code)
                native.assert_not_called(); prepared.assert_not_called()

    def test_original_contract_policy_is_external_and_independent_of_binary_object(self):
        result = self.invoke()
        evidence = load_canonical_json_bytes(Path(result["binary-contract-evidence"]).read_bytes())
        self.assertEqual(str(self.destination / "contract-contract-metadata-common/stage"), evidence["stageRoot"])
        self.assertEqual(str(self.destination / "contract-contract-metadata-common/phase-receipt.json"), evidence["phaseReceipt"])
        self.assertEqual(self.context, load_canonical_json_bytes(
            Path(result["binary-original-context"]).read_bytes()))
        self.assertFalse((self.root / "binary-object.zip").exists())
        self.assertNotIn(self.root, self.destination.parents)

    def test_reused_or_missing_current_binary_is_not_a_same_campaign_policy(self):
        for value in ("reused", "missing"):
            with self.subTest(value=value):
                self.verified.prior_by_instance[policy._BINARY]["state"] = value
                with self.assertRaisesRegex(ValueError, "retained binary"):
                    self.invoke()
        self.assertFalse(self.destination.exists())

    def test_incomplete_or_noncanonical_caller_context_fails_before_state_replay(self):
        for value in ('{}', json.dumps(self.context, indent=2), 'not-json'):
            with self.subTest(value=value):
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    self.invoke(binary_original_context=value)
        self.assertFalse(self.destination.exists())

    def test_missing_original_contract_evidence_fails_closed(self):
        self.verified.rebased_request["contractEvidence"] = None
        with self.assertRaisesRegex(ValueError, "authenticated release Contract"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_contract_payload_must_equal_the_authenticated_predecessor(self):
        handoff = self.discovery / "authenticated-contract/contract-input"
        (handoff / "codex-agent-contract-0.8.0.zip").write_bytes(b"different")
        with self.assertRaisesRegex(ValueError, "metadata differs"):
            self.invoke()
        self.assertFalse(self.destination.exists())

    def test_missing_official_binary_upload_is_rejected_before_replay(self):
        with self.assertRaises(ValueError):
            self.invoke(binary_artifact_id=0)
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
