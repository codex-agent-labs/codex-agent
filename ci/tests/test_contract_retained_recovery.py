"""Retained Contract key/receipt admission; no hosted acceptance claimed."""

import copy
import shutil
import subprocess
import unittest
from unittest import mock

from ci.tests import test_contract_ci_originals as fixture
from ci.tests import test_product_reuse as planner_fixture
import contract_retained_recovery as recovery


class ContractRetainedRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.source = fixture.ContractOriginalCiCaptureTest()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.originals = self.source.root / "retained-originals"
        for phase, path in self.source.shards.items():
            shutil.copytree(path, self.originals / "original-phases" / phase)
        self.handoff = self.source.capture_root
        self.keys = {phase: fixture.load_canonical_json_bytes(path.read_bytes())["buildKey"]
                     for phase, path in self.source.receipts.items()}

    def test_exact_keys_admit_original_receipts_without_rewriting_them(self):
        original_bytes = {phase: path.read_bytes() for phase, path in self.source.receipts.items()}
        phases = recovery._verify_current_keys(self.originals, self.handoff, self.keys)
        self.assertEqual(original_bytes, {phase: value["receiptBytes"] for phase, value in phases.items()})
        changed = dict(self.keys, binary="sha256:" + "0" * 64)
        with self.assertRaisesRegex(ValueError, "current build key"):
            recovery._verify_current_keys(self.originals, self.handoff, changed)
        receipt = self.handoff / "execution-closure/receipts/metadata.json"
        receipt.write_bytes(self.source.receipts["binary"].read_bytes())
        with self.assertRaisesRegex(ValueError, "signed original receipt"):
            recovery._verify_current_keys(self.originals, self.handoff, self.keys)

    def test_ineligible_producer_fails_before_download(self):
        consumer = dict(self.source.producer, runId=72)
        plan = {"repository": consumer["repository"], "event": "pull_request",
                "remoteBuildAuthorized": True, "pullRequest": 31,
                "validationCommit": consumer["commit"], "validationTree": consumer["tree"]}
        original = copy.deepcopy(self.source.producer)
        original["pullRequest"] = 32
        with mock.patch.object(recovery.transport, "capture_contract_ci_artifact") as download:
            with self.assertRaisesRegex(ValueError, "same authorized PR"):
                recovery.capture_retained_contract(
                    self.source.root / "result", plan=plan, consumer_producer=consumer,
                    original_producer=original, expected_build_keys=self.keys, contract_version="0.8.0",
                    inputs_artifact_id=1, inputs_artifact_sha256="sha256:" + "1" * 64,
                    handoff_artifact_id=2, handoff_artifact_sha256="sha256:" + "2" * 64,
                    trusted_workflow_sha=self.source.pin, keyring=self.source.root / "keyring",
                    keys_directory=self.source.root / "keys", token="not-a-real-token")
            download.assert_not_called()

    def test_replay_computes_current_keys_and_preserves_original_carrier_bytes(self):
        builder = planner_fixture.ProductReuseTest()
        builder.root = self.source.root
        repository, revision = builder.reuse_wave_repository()
        instances = tuple(sorted(fixture.PhaseInstanceId("contract", "contract", phase, "common")
                                 for phase in recovery.PHASES))
        inputs = {planner_fixture.PhaseInstanceId(instance.product, instance.component, instance.phase, instance.target): {
            "inventory": planner_fixture.phase_git_inventory(repository, revision,
                planner_fixture.PhaseInstanceId(instance.product, instance.component, instance.phase, instance.target)),
            "versions": planner_fixture.VERSIONS,
            "toolchain_profile_digest": planner_fixture.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            "flags_digest": planner_fixture.NOT_APPLICABLE_FLAGS_DIGEST,
        } for instance in instances}
        chain = self.source.root / "current-chain"
        resolved, _, payload, metadata_receipt, closure = planner_fixture.contract_execution_chain(chain, inputs)
        captured = self.source.root / "authenticated-capture"
        handoff = captured / "release-upload/contract-input"
        planner_fixture.ProductReuseTest.setUpClass()
        self.addCleanup(planner_fixture.ProductReuseTest.tearDownClass)
        planner_fixture.build_contract_attestation(
            payload, metadata_receipt, builder.release_signing, builder.private_key, builder.public_key,
            handoff, execution_closure=closure, complete_handoff=True,
            keyring=builder.release_keyring, keys_directory=builder.release_keys)
        for instance in instances:
            envelope = next(value for key, value in resolved.items() if key.phase == instance.phase)
            receipt = envelope["receipt"]
            fixture.finalize_phase_object(
                stage_root=chain / instance.phase,
                phase_plan={"schemaVersion": 1, **recovery.transport._identity_record(instance),
                            "buildKey": receipt["buildKey"], "inputs": receipt["inputs"]},
                producer=receipt["producer"], product_version=receipt["productVersion"],
                trust_domain=receipt["trustDomain"],
                destination=captured / "originals/original-phases" / instance.phase)
        request = builder.reuse_wave_request(repository, revision)
        request["requested"] = [{"product": "contract", "component": "contract", "phase": "metadata", "target": "common"}]
        request["phaseAuthorities"] = [{**recovery.transport._identity_record(instance),
            "toolchainProfileDigest": planner_fixture.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            "flagsDigest": planner_fixture.NOT_APPLICABLE_FLAGS_DIGEST, "outputSchemaVersion": 1}
            for instance in instances]
        consumer = {"kind": "ci", "producer": dict(self.source.producer, runId=72)}
        output = self.source.root / "current-carrier"
        trust = {"keyring": builder.release_keyring, "keys_directory": builder.release_keys}
        result = recovery.replay_retained_contract(captured, request, output, consumer=consumer, **trust)
        carrier = recovery.transport.verify_carrier(output, instances, consumer)
        self.assertTrue(result["result"]["fullReuse"])
        self.assertEqual({phase: (chain / f"{phase}-receipt.json").read_bytes() for phase in recovery.PHASES},
                         {item["phase"]: item["receiptBytes"] for item in carrier["objects"]})
        changed = copy.deepcopy(request)
        changed["versions"]["contract"] = "0.2.1"
        with self.assertRaisesRegex(ValueError, "current computed phase keys"):
            recovery.replay_retained_contract(captured, changed, self.source.root / "miss", consumer=consumer, **trust)
        self.assertFalse((self.source.root / "miss").exists())
        # Exercise the real continuation recheck and ordinary path rebase.
        discovery = repository / "build/product-reuse"
        shutil.copytree(captured, discovery / "retained-contract/capture")
        current_consumer = {"kind": "ci", "producer": dict(consumer["producer"], commit=revision,
            repository=request["repository"],
            tree=subprocess.check_output(("git", "rev-parse", "HEAD^{tree}"), cwd=repository, text=True).strip())}
        current_request = {**request, "artifactRoot": str(discovery)}
        current = recovery.replay_retained_contract(discovery / "retained-contract/capture", current_request,
            discovery / "carrier", consumer=current_consumer, **trust)
        for name, document in (("contract-reuse-request.json", current["request"]),
                               ("contract-reuse-result.json", current["result"]),
                               ("producer.json", current_consumer["producer"])):
            fixture.product_reuse.write_canonical_json(discovery / name, document)
        plan = {"repository": request["repository"], "event": "pull_request", "remoteBuildAuthorized": True,
                "pullRequest": request["pullRequest"], "validationCommit": revision,
                "validationTree": current_consumer["producer"]["tree"]}
        release_trust = recovery.transport.ReleaseTrust(builder.release_keyring, builder.release_keys)
        with mock.patch.object(recovery.transport, "_validate_plan", return_value=plan), \
                mock.patch.object(recovery.transport, "_versions", return_value=request["versions"]), \
                mock.patch.object(recovery.transport, "_release_trust", return_value=release_trust):
            advanced = recovery.transport.advance_contract(
                repository / "plan.json", discovery, None, [], repository / "build/after-retained",
                repository / "outputs.txt", repository_root=repository,
                environ={"GITHUB_RUN_ID": "72", "GITHUB_RUN_ATTEMPT": str(current_consumer["producer"]["runAttempt"])})
        self.assertTrue(advanced["fullReuse"])
        signature = handoff / f"codex-agent-contract-{planner_fixture.VERSIONS['contract']}.attestation.sig"
        signature.write_bytes(b"tampered signature\n")
        with self.assertRaises(ValueError):
            recovery.replay_retained_contract(captured, request, self.source.root / "tampered", consumer=consumer, **trust)
        self.assertFalse((self.source.root / "tampered").exists())

    def test_scan_pairs_official_uploads_and_forwards_reviewed_original_policy(self):
        consumer = dict(self.source.producer, runId=72)
        plan = {"repository": consumer["repository"], "event": "pull_request",
                "remoteBuildAuthorized": True, "pullRequest": 31,
                "validationCommit": consumer["commit"], "validationTree": consumer["tree"]}
        request = {"artifactRoot": str(self.source.root), "versions": {"contract": fixture.VERSION}}
        probe = self.source.root / "probe"
        receipt = probe / "execution-closure/receipts/metadata.json"
        receipt.parent.mkdir(parents=True)
        shutil.copyfile(self.source.receipts["metadata"], receipt)
        raw = fixture.archive_tree(probe)
        digest = fixture.sha256_bytes(raw)
        tree = self.source.producer["tree"]
        uploads = [{"id": 700, "digest": digest, "expired": False,
                    "name": f"codex-agent-contract-attestation-inputs-{tree}"},
                   {"id": 701, "digest": digest, "expired": False,
                    "name": f"codex-agent-contract-release-handoff-{tree}"}]

        def download(*args, **kwargs):
            self.assertEqual((700, digest, uploads[0]["name"]), args[:3])
            kwargs["destination"].write_bytes(raw)

        def capture(destination, **kwargs):
            self.assertEqual(self.source.producer, kwargs["original_producer"])
            self.assertEqual(self.source.pin, kwargs["trusted_workflow_sha"])
            self.assertNotIn("expected_build_keys", kwargs)
            destination.mkdir()
            (destination / "authenticated.json").write_bytes(b"{}\n")

        def replay(captured_root, supplied_request, destination, **kwargs):
            self.assertEqual(request, supplied_request)
            destination.mkdir()
            (destination / "carrier.json").write_bytes(b"{}\n")
            return {"result": {"fullReuse": True}, "resolution": {}, "request": {
                **supplied_request, "availableObjects": [{"objectPath":
                    (captured_root / "authenticated.json").relative_to(self.source.root).as_posix()}]}}

        output = self.source.root / "selected"
        with mock.patch.object(recovery.transport, "_prior_failed_pr_attempts", return_value=(self.source.run,)), \
                mock.patch.object(recovery.transport, "paginated_items", return_value=uploads), \
                mock.patch.object(recovery.transport, "_download_contract_ci_upload", side_effect=download), \
                mock.patch.object(recovery, "capture_retained_contract", side_effect=capture), \
                mock.patch.object(recovery, "replay_retained_contract", side_effect=replay):
            selected = recovery.discover_retained_contract(
                output, plan=plan, consumer_producer=consumer, contract_request=request,
                trusted_workflow_sha=self.source.pin, keyring=self.source.root / "keyring",
                keys_directory=self.source.root / "keys", token="not-a-real-token")
        self.assertTrue(selected["result"]["fullReuse"])
        self.assertEqual(output / "carrier", selected["carrier"])
        selected_object = self.source.root / selected["request"]["availableObjects"][0]["objectPath"]
        self.assertTrue(selected_object.is_file())
        self.assertTrue((output / "selection.json").is_file())


if __name__ == "__main__":
    unittest.main()
