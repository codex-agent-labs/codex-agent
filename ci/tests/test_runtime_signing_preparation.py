"""Non-secret preparation orchestration; source/transport/replay are explicit mocks.

Real filesystem snapshots and the shared secret guard are exercised. Synthetic
selected bytes below are not signed product, hosted, or environment approval proof.
"""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_workflow as fixture
from ci import runtime_signing_preparation as preparation
from products.inventory import publish_regular_tree as actual_publish_regular_tree
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, sha256_bytes


SECRET = "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"


class RuntimeSigningPreparationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-preparation-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.trusted, self.candidate = self.root / "trusted", self.root / "candidate"
        self.trusted.mkdir()
        self.candidate.mkdir()
        self.plan = self.root / "impact-plan.json"
        self.plan_raw = b'{"original":"plan"}\n'
        self.plan.write_bytes(self.plan_raw)
        self.producer = {"repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/ci.yml",
            "event": "pull_request", "commit": "a" * 40, "tree": "b" * 40,
            "runId": 12, "runAttempt": 2, "pullRequest": 31}
        self.environment = {"GITHUB_EVENT_NAME": "pull_request"}
        self.env_patch = patch.dict("os.environ", {}, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.context = self.mock("verify_product_release_context", return_value=(
            self.trusted, self.producer, "c" * 40, {}, "synthetic authorized context seam"))
        self.capture = self.mock("capture_runtime_resume_upload", side_effect=self.capture_upload)
        self.trust = self.mock("_release_trust", side_effect=self.capture_policy)
        self.selector = self.mock("materialize_runtime_attestation_inputs", side_effect=self.select)
        self.aggregate = self.mock("materialize_runtime_aggregate_release_evidence", side_effect=self.retain)
        self.retained = True
        self.tooling = {"requiredTrustDomain": "release"}
        for name in ("evidence", "publicKey", "javaExecutable", "keyring", "keysDirectory"):
            path = self.root / "tooling" / name
            self.write(path, b"caller original tooling\n")
            self.tooling[name] = str(path)
        self.apple_policy = {"plan": str(self.plan), "attestationTrustDomain": "release",
                             "attestationPublicKey": None, "toolingTrustDomain": "release"}
        for name in ("keyring", "keysDirectory", "toolingEvidence", "toolingPublicKey", "javaExecutable",
                     "toolingKeyring", "toolingKeysDirectory"):
            path = self.root / "apple-policy" / name
            if name in ("keysDirectory", "toolingEvidence", "toolingKeysDirectory"):
                self.write(path / "original", b"caller Apple policy input\n")
            else:
                self.write(path, b"caller Apple policy input\n")
            self.apple_policy[name] = str(path)

    def mock(self, name, **kwargs):
        mocked = patch.object(preparation, name, **kwargs)
        value = mocked.start()
        self.addCleanup(mocked.stop)
        return value

    def write(self, path, raw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def capture_upload(self, _plan, destination, **kwargs):
        self.capture_root = destination
        self.write(destination / "original/product-resume-inputs/plan/impact-plan.json", self.plan_raw)
        self.write(destination / "original/product-resume-state/receipt.json", b"original state receipt\x00\xff")
        self.write(destination / "original/runtime-state/receipt.json", b"original advanced receipt\n")
        self.write(destination / "original/empty-diagnostic.log", b"")
        self.write(destination / "capture-transport.json", b"original observed transport\n")

    def capture_policy(self, _repository, _revision, destination):
        self.policy_root = destination
        self.write(destination / "keyring.json", b"original caller public policy\n")
        self.write(destination / "keys/public.pub", b"original caller public key\n")
        return SimpleNamespace(keyring=destination / "keyring.json", keys=destination / "keys")

    def select(self, _plan, _discovery, _state, destination, **kwargs):
        self.selected_root = destination
        self.selection = {"schemaVersion": 1, "target": kwargs["target"],
            "metadata": {"buildKey": kwargs["expected_build_key"]}, "producer": deepcopy(self.producer)}
        if kwargs["target"] != "aggregate":
            self.selection["releaseHandoffs"] = ["retained-release-handoffs/original"]
            self.write(destination / "retained-release-handoffs/original/attestation.sig", b"original signature\x00\xff")
        self.write(destination / "selection.json", canonical_json_bytes(self.selection))
        self.write(destination / "predecessors/phase-receipt.json", b"original selected receipt\n")
        self.write(destination / "predecessors/empty-stderr.log", b"")
        return deepcopy(self.selection)

    def retain(self, _plan, _discovery, _state, destination, **kwargs):
        if not self.retained:
            return None
        carrier = destination / "handoffs/original"
        self.write(carrier / "aggregate-input/attestation.sig", b"original aggregate signature\x00\xfe")
        self.write(carrier / "selected-state-transport/empty.log", b"")
        return carrier

    def invoke(self, destination=None, **changes):
        arguments = {"target": "linux-x64", "expected_build_key": fixture.KEY,
            "artifact_id": 42, "artifact_sha256": "sha256:" + "d" * 64, "state_wave": 4,
            "trusted_source_sha": "e" * 40, "trusted_workflow_sha": fixture.PIN,
            "transport_producer": self.producer, "event_payload": {"number": 31},
            "environment": self.environment, "token": "synthetic-token"}
        arguments.update(changes)
        return preparation.prepare_runtime_signing_inputs(self.trusted, self.candidate, self.plan,
            destination or self.root / "output", **arguments)

    def test_native_and_aggregate_forward_exact_original_bytes_without_signing(self):
        for target in (*preparation.NATIVE_TARGETS, "aggregate"):
            for supplied in (False, True):
                destination = self.root / f"output-{target}-{supplied}"
                optional = {"sdk_validation_tooling": self.tooling} if supplied else {}
                with self.subTest(target=target, supplied=supplied):
                    result = self.invoke(destination, target=target, **optional)
                    self.assertEqual({"schemaVersion": 1, "target": target, "expectedBuildKey": fixture.KEY,
                        "stateWave": 4, "producer": self.producer, "planSha256": sha256_bytes(self.plan_raw),
                        "stateArtifact": {"artifactId": 42, "artifactSha256": "sha256:" + "d" * 64},
                        "selectionSha256": sha256_bytes(canonical_json_bytes(self.selection))}, result)
                    self.assertEqual(result, load_canonical_json_bytes((destination / "preparation.json").read_bytes()))
                    self.assertEqual({"preparation.json", "selected-inputs", "selected-state-transport"}
                        | ({"release-handoff"} if target == "aggregate" else set()), {p.name for p in destination.iterdir()})
                    reference = load_canonical_json_bytes((destination / "selected-state-transport/reference.json").read_bytes())
                    self.assertEqual({"reference.json"}, {p.name for p in (destination / "selected-state-transport").iterdir()})
                    self.assertEqual(result["stateArtifact"], reference["stateArtifact"])
                    self.assertIn({"relativePath": "product-resume-inputs/plan/impact-plan.json",
                        "bytes": len(self.plan_raw), "sha256": sha256_bytes(self.plan_raw)}, reference["inventory"])
                    self.assertEqual(b"", (destination / "selected-inputs/predecessors/empty-stderr.log").read_bytes())
                    self.assertEqual(b"original selected receipt\n", (destination / "selected-inputs/predecessors/phase-receipt.json").read_bytes())
                    self.assertNotIn("sdk_validation_tooling", self.capture.call_args.kwargs)
                    self.assertNotIn("sdk_apple_validation_policy", self.capture.call_args.kwargs)
                    self.assertNotIn("sdk_apple_validation_policy", self.selector.call_args.kwargs)
                    if supplied:
                        self.assertIs(self.tooling, self.selector.call_args.kwargs["sdk_validation_tooling"])
                    else:
                        self.assertNotIn("sdk_validation_tooling", self.selector.call_args.kwargs)
                    if target == "aggregate":
                        self.assertNotIn("retained_release_keyring", self.selector.call_args.kwargs)
                        self.assertEqual(b"original aggregate signature\x00\xfe", (destination / "release-handoff/aggregate-input/attestation.sig").read_bytes())
                        if supplied:
                            self.assertIs(self.tooling, self.aggregate.call_args.kwargs["sdk_validation_tooling"])
                    else:
                        self.assertEqual(self.policy_root / "keyring.json", self.selector.call_args.kwargs["retained_release_keyring"])
                        self.assertEqual(b"original signature\x00\xff", (destination / "selected-inputs/retained-release-handoffs/original/attestation.sig").read_bytes())
                    self.assertFalse(self.selected_root.exists())
                    self.assertFalse(self.capture_root.exists())
                    self.assertEqual(self.plan_raw, self.plan.read_bytes())

    def test_aggregate_without_retained_carrier_has_no_invented_handoff(self):
        self.retained = False
        self.invoke(target="aggregate", state_wave=0)
        self.assertFalse((self.root / "output/release-handoff").exists())
        self.assertEqual(self.capture_root / "original/product-resume-state", self.aggregate.call_args.args[2])

    def test_apple_policy_native_and_aggregate_replay_receive_copy_never_serialized_authority(self):
        original = deepcopy(self.apple_policy)
        raw = canonical_json_bytes(original)
        for target in ("linux-x64", "aggregate"):
            destination = self.root / f"apple-{target}"
            self.selector.reset_mock()
            self.aggregate.reset_mock()
            result = self.invoke(destination, target=target, sdk_apple_validation_policy=self.apple_policy)
            forwarded = self.selector.call_args.kwargs["sdk_apple_validation_policy"]
            self.assertEqual(original, forwarded)
            self.assertIsNot(self.apple_policy, forwarded)
            self.assertNotIn("sdk_apple_validation_policy", self.capture.call_args.kwargs)
            if target == "aggregate":
                self.assertEqual(original, self.aggregate.call_args.kwargs["sdk_apple_validation_policy"])
                self.assertIsNot(self.apple_policy, self.aggregate.call_args.kwargs["sdk_apple_validation_policy"])
            self.assertEqual(original, self.apple_policy)
            self.assertNotIn("sdk_apple_validation_policy", result)
            for row in regular_file_inventory(destination, allow_empty=True):
                payload = (destination / row["relativePath"]).read_bytes()
                self.assertNotIn(raw, payload)
                self.assertNotIn(b"sdkAppleValidationPolicy", payload)
                self.assertNotIn(str(self.root / "apple-policy").encode(), payload)

    def test_malformed_or_development_apple_tooling_rejects_before_context(self):
        invalid = ([], {}, {**self.apple_policy, "extra": True},
                   {**self.apple_policy, "plan": "relative/plan"},
                   {**self.apple_policy, "attestationTrustDomain": "development"},
                   {**self.apple_policy, "toolingKeyring": None},
                   {**self.apple_policy, "toolingTrustDomain": "development",
                    "toolingKeyring": None, "toolingKeysDirectory": None})
        for policy in invalid:
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                self.invoke(sdk_apple_validation_policy=policy)
            self.context.assert_not_called()
            self.capture.assert_not_called()
            self.selector.assert_not_called()
        self.assertFalse((self.root / "output").exists())

    def test_apple_policy_output_overlap_rejects_without_changing_inputs(self):
        before = regular_file_inventory(self.root / "apple-policy", allow_empty=True)
        destinations = (Path(self.apple_policy["keyring"]),
                        Path(self.apple_policy["toolingEvidence"]) / "output",
                        Path(self.apple_policy["keysDirectory"]) / "output",
                        Path(self.apple_policy["toolingKeysDirectory"]) / "output")
        for destination in destinations:
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                self.invoke(destination, sdk_apple_validation_policy=self.apple_policy)
            self.capture.assert_not_called()
            self.selector.assert_not_called()
        self.assertEqual(before, regular_file_inventory(self.root / "apple-policy", allow_empty=True))

    def test_caller_apple_policy_mutation_during_selection_or_aggregate_replay_prevents_publication(self):
        original = deepcopy(self.apple_policy)
        for boundary in ("selection", "aggregate", "selection-copy", "aggregate-copy"):
            self.apple_policy = deepcopy(original)
            destination = self.root / f"apple-mutated-{boundary}"

            def select(*args, **kwargs):
                self.assertIsNot(self.apple_policy, kwargs["sdk_apple_validation_policy"])
                value = self.select(*args, **kwargs)
                if boundary == "selection":
                    self.apple_policy["toolingPublicKey"] = str(self.root / "changed.pub")
                elif boundary == "selection-copy":
                    kwargs["sdk_apple_validation_policy"]["toolingPublicKey"] = str(self.root / "changed.pub")
                return value

            def retain(*args, **kwargs):
                self.assertIsNot(self.apple_policy, kwargs["sdk_apple_validation_policy"])
                value = self.retain(*args, **kwargs)
                if boundary == "aggregate":
                    self.apple_policy["attestationTrustDomain"] = "development"
                elif boundary == "aggregate-copy":
                    kwargs["sdk_apple_validation_policy"]["attestationTrustDomain"] = "development"
                return value

            self.selector.side_effect = select
            self.aggregate.side_effect = retain
            with self.subTest(boundary=boundary), self.assertRaisesRegex(ValueError, "Apple policy changed"):
                self.invoke(destination, target="aggregate", sdk_apple_validation_policy=self.apple_policy)
            self.assertFalse(destination.exists())

    def test_secret_presence_even_empty_rejects_before_context_or_replay(self):
        for global_environment in (False, True):
            for value in ("", "not-a-real-key"):
                with self.subTest(global_environment=global_environment, value=value), patch.dict(
                        "os.environ", {SECRET: value} if global_environment else {}, clear=True):
                    environment = {} if global_environment else {SECRET: value}
                    with self.assertRaises(ValueError):
                        self.invoke(environment=environment)
                    self.context.assert_not_called()
                    self.capture.assert_not_called()
                    self.assertFalse((self.root / "output").exists())

    def test_malformed_tooling_policy_rejects_before_context_or_replay(self):
        for value in ([], {}, {**self.tooling, "unexpected": "value"},
                      {**self.tooling, "requiredTrustDomain": "development"},
                      {**self.tooling, "evidence": None}, {**self.tooling, "javaExecutable": "relative/java"}):
            with self.subTest(policy=value), self.assertRaises(ValueError):
                self.invoke(sdk_validation_tooling=value)
            self.context.assert_not_called()
            self.capture.assert_not_called()
        self.assertFalse((self.root / "output").exists())

    def test_wrong_selection_and_replay_mutations_never_publish(self):
        for mutation in ("producer", "target", "key", "selection-bytes", "plan", "capture", "policy"):
            self.plan.write_bytes(self.plan_raw)
            def changed(*args, **kwargs):
                value = self.select(*args, **kwargs)
                if mutation == "producer":
                    value["producer"]["runAttempt"] += 1
                elif mutation == "target":
                    value["target"] = "wrong"
                elif mutation == "key":
                    value["metadata"]["buildKey"] = "sha256:" + "f" * 64
                elif mutation == "selection-bytes":
                    self.write(self.selected_root / "selection.json", b"{}\n")
                else:
                    path = {"plan": self.plan, "capture": self.capture_root / "capture-transport.json",
                        "policy": self.policy_root / "keyring.json"}[mutation]
                    path.write_bytes(b"changed original\n")
                return value
            self.selector.side_effect = changed
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.invoke(self.root / f"rejected-{mutation}")
            self.assertFalse((self.root / f"rejected-{mutation}").exists())

    def test_retained_lookup_and_snapshot_mutation_reject_before_publication(self):
        for boundary in ("retained", "snapshot"):
            destination = self.root / f"late-{boundary}"
            def changed_retained(*args, **kwargs):
                value = self.retain(*args, **kwargs)
                if boundary == "retained":
                    self.write(self.selected_root / "predecessors/phase-receipt.json", b"changed original\n")
                return value
            original_snapshot = preparation.snapshot_regular_tree
            def changed_snapshot(*args, **kwargs):
                original_snapshot(*args, **kwargs)
                if boundary == "snapshot":
                    self.plan.write_bytes(b"changed plan\n")
            self.aggregate.side_effect = changed_retained
            with self.subTest(boundary=boundary), patch.object(preparation, "snapshot_regular_tree", side_effect=changed_snapshot):
                with self.assertRaises(ValueError):
                    self.invoke(destination, target="aggregate")
            self.assertFalse(destination.exists())

    def test_late_prepared_original_mutation_cannot_publish(self):
        destination = self.root / "late-copy"

        def mutate_before_copy(source, output, **kwargs):
            original = source / "selected-inputs/predecessors/phase-receipt.json"
            original.write_bytes(original.read_bytes() + b"late mutation\n")
            return actual_publish_regular_tree(source, output, **kwargs)

        with patch.object(preparation, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.invoke(destination)
        self.assertFalse(destination.exists())

    def test_output_overlap_existing_and_symbolic_ancestry_reject_before_capture(self):
        occupied = self.root / "occupied"
        occupied.mkdir()
        self.write(occupied / "sentinel", b"original\n")
        alias = self.root / "alias"
        alias.symlink_to(self.candidate, target_is_directory=True)
        for output in (self.trusted / "new", self.candidate / "new", self.plan, occupied, alias / "new"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                self.invoke(output)
            self.capture.assert_not_called()
        self.assertEqual(b"original\n", (occupied / "sentinel").read_bytes())


if __name__ == "__main__":
    unittest.main()
