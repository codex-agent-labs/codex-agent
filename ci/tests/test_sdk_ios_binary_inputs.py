"""iOS binary input controller tests with explicit mocked authority boundaries.

Real original receipt/stage files exercise pairing and lifetime checks. No
signature, native execution, product compilation or package admission is claimed.
"""

from contextlib import contextmanager, ExitStack
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ci import sdk_workflow as workflow
from ci.tests.product_chain_support import write_receipt
from ci.tests.test_product_plan import PRODUCER
from products import contract_projection
from products.inventory import regular_file_inventory, snapshot_regular_tree
from products.receipt import write_output_manifest
from products.registry import PhaseInstanceId
import sdk_apple_native


IOS = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")


class SdkIosBinaryInputsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-ios-binary-inputs-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.repository = self.work / "repository"
        self.repository.mkdir()
        self.discovery, self.state_root = (self.repository / name for name in ("discovery", "state"))
        self.discovery.mkdir()
        self.state_root.mkdir()
        self.destination = self.repository / "build/inputs"
        self.plan = self.repository / "plan.json"
        self.plan.write_bytes(b'{"synthetic":"mocked verified product replay"}\n')
        self.plan_bytes = self.plan.read_bytes()
        self.producer = deepcopy(PRODUCER)
        self.key = "sha256:" + "a" * 64
        self.ready = {"schemaVersion": 1, "product": "sdk", "component": "sdk-ios", "phase": "binary",
                      "target": "ios", "buildKey": self.key, "inputs": {}}
        self.evidence = {"expectedTrustDomain": "release", "attestation": "synthetic-original-attestation"}
        self.state = SimpleNamespace(prior_ready_plans={IOS: self.ready},
            rebased_request={"contractEvidence": self.evidence}, producer=self.producer,
            plan={"validationCommit": self.producer["commit"]}, expected_fixed={"versions": {"sdk": "0.2.9"}})
        self.originals = self.work / "original-contract"
        self.receipts = {}
        for phase in ("binary", "package", "validation", "metadata"):
            directory = self.originals / f"contract-contract-{phase}-common"
            stage = directory / "stage"
            (stage / "outputs").mkdir(parents=True)
            (stage / "outputs/synthetic.bin").write_bytes(b"synthetic original Contract bytes\x00\xff\n")
            manifest = write_output_manifest(stage, "contract", "contract", phase, "common", "0.2.0",
                {"contract-bundle" if phase == "metadata" else "fixture": "outputs"})
            receipt_path = directory / "phase-receipt.json"
            write_receipt(receipt_path, product="contract", component="contract", phase=phase, target="common",
                version="0.2.0", outputs=manifest["outputs"], upstream=[], context={"producer": self.producer})
            self.receipts[phase] = receipt_path.read_bytes()
        self.original_inventory = regular_file_inventory(self.originals)
        self.native_directory = self.work / "native"
        self.native_directory.mkdir()
        (self.native_directory / "synthetic-proof.json").write_bytes(b"synthetic native authority seam\n")
        self.native_producer = self.producer
        self.native_exit = None
        self.events = []
        self.options = {"expected_build_key": self.key, "native_uploads": {"synthetic": "caller upload map"},
            "trusted_workflow_sha": "c" * 40, "repository_root": self.repository,
            "environ": {"GITHUB_RUN_ID": "7"}, "token": "caller-token"}
        stack = self.enterContext(ExitStack())
        self.replay = stack.enter_context(patch.object(workflow.product_reuse, "_verified_product_state", return_value=self.state))
        self.policy = stack.enter_context(patch.object(workflow.product_reuse, "_release_trust", side_effect=self.capture_policy))
        self.materializer = stack.enter_context(patch.object(workflow.product_reuse, "_materialize_product_predecessors",
                                                            side_effect=self.materialize))
        self.capture = stack.enter_context(patch.object(workflow.product_reuse, "_capture_runtime_contract", side_effect=self.capture_contract))
        self.projection = stack.enter_context(patch.object(contract_projection, "verify_contract_component_projection", return_value=object()))
        self.native = stack.enter_context(patch.object(sdk_apple_native, "verified_sdk_apple_native_inputs", side_effect=self.native_inputs))
        self.finalizer = stack.enter_context(patch.object(workflow.product_reuse, "finalize_phase_object"))

    def tearDown(self):
        self.assertEqual(self.original_inventory, regular_file_inventory(self.originals))
        self.finalizer.assert_not_called()

    def capture_policy(self, root, revision, destination):
        self.assertEqual((self.repository, self.producer["commit"], self.destination / "policy"),
                         (root, revision, destination))
        keys = destination / "keys"
        keys.mkdir(parents=True)
        keyring = destination / "product-signing-keys.json"
        keyring.write_bytes(b"synthetic caller-pinned policy\n")
        (keys / "key.pub").write_bytes(b"synthetic public key\n")
        self.trust = SimpleNamespace(keyring=keyring, keys=keys)
        return self.trust

    def materialize(self, state, identity, destination, key, root):
        self.assertIs(self.state, state)
        self.assertEqual((IOS, self.destination / "predecessors", self.key, self.repository),
                         (identity, destination, key, root))
        snapshot_regular_tree(self.originals, destination)
        return self.ready

    def capture_contract(self, root, evidence, original, one_output, destination, trust):
        self.assertEqual((self.repository, self.evidence, self.destination, self.trust),
                         (root, evidence, destination, trust))
        records = {phase: original("contract", "contract", phase, "common") for phase in self.receipts}
        for phase, record in records.items():
            self.assertEqual(self.receipts[phase], record["receiptPath"].read_bytes())
        self.assertEqual(records["metadata"]["stage"] / "outputs/synthetic.bin",
                         one_output(records["metadata"], "contract-bundle"))
        handoff = destination / "contract-input"
        handoff.mkdir()
        stem = "codex-agent-contract-0.2.0"
        for name in (f"{stem}.zip", f"{stem}.attestation.json", f"{stem}.attestation.sig", "public-key.pub"):
            (handoff / name).write_bytes(b"synthetic captured authority bytes\n")
        receipts = handoff / "execution-closure/receipts"
        receipts.mkdir(parents=True)
        for phase, raw in self.receipts.items():
            (receipts / f"{phase}.json").write_bytes(raw)
        return (records["metadata"], "0.2.0", handoff,
                {"synthetic": "verified manifest seam"}, regular_file_inventory(handoff))

    @contextmanager
    def native_inputs(self, *args, **kwargs):
        self.events.append("native-enter")
        try:
            yield {"producer": self.native_producer, "directory": self.native_directory,
                   "captureRoot": self.native_directory}
            if self.native_exit == "mutate":
                (self.destination / "late-file").write_bytes(b"changed on native exit\n")
            elif self.native_exit == "reject":
                raise ValueError("synthetic native exit rejection")
        finally:
            self.events.append("native-exit")

    def inputs(self, **changes):
        return workflow.verified_ios_binary_inputs(self.plan, self.discovery, self.state_root, self.destination,
                                                   **{**self.options, **changes})

    def test_exact_binary_readiness_originals_policy_and_ios_projection_are_forwarded(self):
        with self.inputs() as value:
            self.assertEqual({"ready", "producer", "sdkVersion", "contract", "contractHandoff", "native",
                              "nativeCaptureRoot", "inputs"}, set(value))
            self.assertEqual(self.ready, value["ready"])
            self.assertEqual(self.producer, value["producer"])
            self.assertEqual("0.2.9", value["sdkVersion"])
            self.assertEqual(self.destination, value["inputs"])
            self.assertEqual(self.native_directory, value["native"])
            self.assertEqual(self.receipts["metadata"], value["contract"]["receiptPath"].read_bytes())
            self.assertEqual(["native-enter"], self.events)
            handoff = value["contractHandoff"]
            self.projection.assert_called_once_with(value["contract"]["stage"], value["contract"]["receiptPath"],
                handoff / "codex-agent-contract-0.2.0.attestation.json",
                handoff / "codex-agent-contract-0.2.0.attestation.sig", handoff / "public-key.pub",
                expected_trust_domain="release", expected_contract_version="0.2.0",
                required_components=("ios-arm64", "ios-simulator-arm64"),
                keyring=self.trust.keyring, keys_directory=self.trust.keys)
            before = regular_file_inventory(self.destination)
        self.assertEqual(before, regular_file_inventory(self.destination))
        self.assertEqual(["native-enter", "native-exit"], self.events)
        self.replay.assert_called_once_with(self.plan, self.discovery, self.state_root, self.repository,
            self.options["environ"], None, sdk_original_workflow_sha=self.options["trusted_workflow_sha"])
        self.native.assert_called_once_with(self.plan, uploads=self.options["native_uploads"],
            trusted_workflow_sha=self.options["trusted_workflow_sha"], repository_root=self.repository,
            environ=self.options["environ"], token=self.options["token"])

    def test_missing_or_wrong_elected_key_never_captures_authority(self):
        for missing in (False, True):
            if missing:
                self.state.prior_ready_plans.clear()
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, "not ready"):
                with self.inputs(expected_build_key="sha256:" + "d" * 64):
                    self.fail("unelected binary inputs yielded")
            self.policy.assert_not_called()
            self.materializer.assert_not_called()
            self.native.assert_not_called()
            self.assertFalse(self.destination.exists())

    def test_missing_release_contract_or_caller_policy_rejects_before_materialization(self):
        for evidence in (None, {"expectedTrustDomain": "development"}):
            self.state.rebased_request["contractEvidence"] = evidence
            with self.subTest(evidence=evidence), self.assertRaisesRegex(ValueError, "release Contract"):
                with self.inputs():
                    self.fail("non-release Contract authority yielded")
        self.policy.assert_not_called()
        self.state.rebased_request["contractEvidence"] = self.evidence
        self.policy.side_effect = None
        self.policy.return_value = None
        with self.assertRaisesRegex(ValueError, "Git-authoritative release policy"):
            with self.inputs():
                self.fail("absent caller policy yielded")
        self.materializer.assert_not_called()
        self.native.assert_not_called()

    def test_native_producer_must_equal_elected_original_attempt(self):
        self.native_producer = {**self.producer, "runAttempt": self.producer["runAttempt"] + 1}
        with self.assertRaisesRegex(ValueError, "native evidence differs from the elected producer"):
            with self.inputs():
                self.fail("cross-attempt native input yielded")
        self.assertEqual(["native-enter", "native-exit"], self.events)

    def test_projection_rejection_never_opens_native_context(self):
        self.projection.side_effect = ValueError("synthetic iOS Contract projection rejection")
        with self.assertRaisesRegex(ValueError, "projection rejection"):
            with self.inputs():
                self.fail("rejected projection yielded")
        self.native.assert_not_called()

    def test_projection_boundary_mutation_rejects_before_native_capture(self):
        # Mutation injection at an explicitly mocked authority boundary, not
        # a signature/projection acceptance claim.
        for target in ("policy", "predecessor"):
            self.destination = self.repository / "build" / f"projection-{target}"

            def mutate(stage, receipt_path, *args, **kwargs):
                path = self.trust.keyring if target == "policy" else receipt_path
                path.write_bytes(path.read_bytes() + b"changed during projection\n")
                return object()

            self.projection.side_effect = mutate
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "original inputs changed during use"):
                with self.inputs():
                    self.fail("projection-boundary mutation reached caller use")
            self.native.assert_not_called()
            self.assertEqual([], self.events)

    def test_original_plan_predecessor_handoff_policy_and_extra_file_mutations_reject(self):
        for target in ("plan", "predecessor", "handoff", "policy", "extra"):
            self.destination = self.repository / "build" / target
            try:
                with self.subTest(target=target), self.assertRaisesRegex(ValueError, "original inputs changed during use"):
                    with self.inputs() as value:
                        path = {"plan": self.plan, "predecessor": value["contract"]["receiptPath"],
                            "handoff": value["contractHandoff"] / "public-key.pub", "policy": self.trust.keyring,
                            "extra": self.destination / "unexpected-file"}[target]
                        path.write_bytes(b"changed during caller use\n")
            finally:
                self.plan.write_bytes(self.plan_bytes)
        self.assertFalse(any(self.destination.glob("shard*")))

    def test_native_exit_rejection_and_late_mutation_do_not_complete_context(self):
        for mode, message in (("reject", "native exit rejection"), ("mutate", "original inputs changed during use")):
            self.destination = self.repository / "build" / mode
            self.native_exit = mode
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, message):
                with self.inputs():
                    pass

    def test_occupied_destination_is_preserved_before_replay(self):
        self.destination.mkdir(parents=True)
        sentinel = self.destination / "original"
        sentinel.write_bytes(b"preserve existing inputs\n")
        before = regular_file_inventory(self.destination)
        with self.assertRaisesRegex(ValueError, "fresh destination"):
            with self.inputs():
                self.fail("occupied destination admitted")
        self.replay.assert_not_called()
        self.assertEqual(before, regular_file_inventory(self.destination))


if __name__ == "__main__":
    unittest.main()
