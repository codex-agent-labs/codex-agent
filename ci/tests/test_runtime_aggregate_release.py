"""Real synthetic K/R signatures and CI26 shards; HTTP/state replay are seams.

No fixture below is protected-host, compiler or original CI execution evidence.
The selected-input leaf exercises the real full semantic and signing pipeline;
the public-entry test separately identifies its mocked transport/selector seam.
"""

import copy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci.tests import test_runtime_aggregate_original_ci as transport_fixture
from ci.tests.test_contract_release_context import contract_context, trusted_repository
from ci.tests.test_contract_release_capture import ObservedEnvironment, SECRET
from ci.tests.test_product_native_chain import build_chain
from ci import runtime_aggregate_release as caller
from products.aggregate import verify_runtime_aggregate_artifacts
from products.contract_attestation import build_contract_attestation
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes,
    publish_regular_tree as actual_publish_regular_tree, regular_file_inventory,
    sha256_bytes, sha256_file, snapshot_regular_tree,
    write_canonical_json as actual_write_canonical_json,
)
from products.registry import NATIVE_TARGETS
from products.runtime_attestation import build_runtime_variant_attestation
from products.signatures import generate_development_key


class RuntimeAggregateReleaseTest(unittest.TestCase):
    api = transport_fixture.RuntimeAggregateOriginalCiTest.api

    @classmethod
    def setUpClass(cls):
        transport_fixture.RuntimeAggregateOriginalCiTest.setUpClass.__func__(cls)
        private, public, signing = generate_development_key(cls.root / "aggregate-caller-key")
        cls.context = {"private_key": private, "public_key": public, "signing": signing, "producer": cls.base.producer}
        cls.chain = build_chain(cls.root / "full-chain", 71, context=cls.context, include_bootstrap=True)
        cls.repository = cls.root / "trusted-caller"
        trusted_repository(cls.repository)
        cls.keyring = cls.repository / "gradle/release/product-signing-keys.json"
        cls.keys = cls.repository / "gradle/release/keys"
        cls.keys.mkdir()
        (cls.keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        cls.policy = {"schemaVersion": 1, "algorithm": signing["algorithm"], "namespace": signing["namespace"],
            "trustDomain": "release", "activeKey": {name: signing[name] for name in ("keyId", "fingerprint")},
            "retiredKeys": []}
        cls.keyring.write_bytes(canonical_json_bytes(cls.policy))
        subprocess.run(["git", "add", "gradle/release"], cwd=cls.repository, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "synthetic public release policy"], cwd=cls.repository,
                       check=True, capture_output=True)
        cls.pin = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cls.repository, check=True,
                                 capture_output=True, text=True).stdout.strip()
        release_signing = {**signing, "trustDomain": "release"}
        contract = cls.chain["contract"]
        release_contract = cls.root / "release-contract"
        build_contract_attestation(contract["payload"], contract["receipt"], release_signing, private, public,
            release_contract, execution_closure=contract["execution_closure"], keyring=cls.keyring, keys_directory=cls.keys)
        cls.handoffs = {}
        variants = cls.chain["variants"]
        for target in NATIVE_TARGETS:
            handoff = cls.root / "release-variants" / target
            phases = variants["variant_phase_receipts"][target]
            build_runtime_variant_attestation(variants["variant_bundles"][target],
                *(phases[phase] for phase in caller._PHASES), variants["variant_validation_evidence"][target],
                release_signing, private, public, handoff, keyring=cls.keyring, keys_directory=cls.keys,
                complete_handoff=True)
            cls.handoffs[target] = handoff
        cls.selected = cls.root / "selected-originals"
        snapshot_regular_tree(release_contract, cls.selected / "contract-input")
        (cls.selected / "contract-input" / contract["payload"].name).write_bytes(contract["payload"].read_bytes())
        (cls.selected / "contract-input/public-key.pub").write_bytes(public.read_bytes())
        cls.selection = {"schemaVersion": 1, "target": "aggregate", "producer": cls.base.producer,
                         "contractVersion": "0.2.0", "contractHandoff": "contract-input", "originals": []}
        original_paths = {}
        for instance in caller._dependency_closure((caller._METADATA,)):
            identity = {name: getattr(instance, name) for name in ("product", "component", "phase", "target")}
            if instance.product == "contract":
                receipt_path = contract["execution_closure"] / f"receipts/{instance.phase}.json"
                stage = cls.chain["root"] / "contract-source" / f"{instance.phase}-stage"
            elif instance.component == "runtime-aggregate":
                receipt_path = cls.chain["aggregate_receipt"]
                stage = cls.chain["root"] / "aggregate-stage"
            else:
                key = next(key for key in cls.context["phase_stages"]
                           if all(getattr(key, name) == value for name, value in identity.items()))
                stage = cls.context["phase_stages"][key]
                receipt_path = (variants["variant_phase_receipts"][instance.target][instance.phase]
                    if instance.component in NATIVE_TARGETS else next(record["receipt"]
                        for record in cls.chain["adapters"]["adapter_receipts"]
                        if all(record[name] == identity[name] for name in ("component", "phase", "target"))))
            directory = "predecessors/" + "-".join(identity.values())
            snapshot_regular_tree(stage, cls.selected / directory / "stage")
            (cls.selected / directory / "phase-receipt.json").write_bytes(receipt_path.read_bytes())
            record = {**identity, "receiptSha256": sha256_file(receipt_path), "directory": directory}
            cls.selection["originals"].append(record)
            original_paths[(instance.component, instance.phase, instance.target)] = (stage, receipt_path)
            if instance == caller._METADATA:
                receipt = load_canonical_json_bytes(receipt_path.read_bytes())
                cls.build_key = receipt["buildKey"]
                cls.selection.update(metadata={**identity, "buildKey": cls.build_key,
                    "receiptSha256": record["receiptSha256"]}, aggregateStage=directory + "/stage",
                    aggregateReceipt=directory + "/phase-receipt.json",
                    aggregateManifest=directory + "/stage/outputs/" + cls.chain["aggregate"].name)
        (cls.selected / "selection.json").write_bytes(canonical_json_bytes(cls.selection))
        # External diagnostics may be empty; no product-stage rule is relaxed.
        (cls.selected / "empty-diagnostic.log").write_bytes(b"")
        # Replace only the synthetic upload fixtures BEFORE any test. All
        # receipts remain original build_chain outputs; the real shard producer
        # must reproduce them byte-for-byte, never rewrite their provenance.
        for identity, (stage, receipt_path) in original_paths.items():
            name = "-".join(identity)
            if name not in cls.original_artifacts:
                continue
            receipt = load_canonical_json_bytes(receipt_path.read_bytes())
            plan = {key: receipt[key] for key in ("schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs")}
            upload = cls.root / "full-original-uploads" / name
            transport_fixture.fixture.finalize_phase_object(stage_root=stage, phase_plan=plan,
                producer=receipt["producer"], product_version=receipt["productVersion"],
                trust_domain=receipt["trustDomain"], destination=upload / "shard")
            if (upload / "shard/phase-receipt.json").read_bytes() != receipt_path.read_bytes():
                raise AssertionError("Original synthetic phase receipt was rewritten")
            (upload / "empty-diagnostic.log").write_bytes(b"")
            raw = transport_fixture.fixture.archive_tree(upload)
            cls.original_archives[name] = raw
            cls.original_artifacts[name].update(
                name=f"codex-agent-runtime-worker-{name}-{receipt['buildKey'][7:]}-{cls.base.producer['tree']}-attempt-2",
                digest=sha256_bytes(raw), size_in_bytes=len(raw))

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="aggregate-caller-result-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.output = self.work / "result"
        self.artifacts = copy.deepcopy(self.original_artifacts)
        self.archives = dict(self.original_archives)
        self.jobs = copy.deepcopy(self.original_jobs)
        self.runs = {(71, 2): copy.deepcopy(self.base.run)}
        _, self.event, values = contract_context()
        values["GITHUB_SHA"] = self.base.producer["commit"]
        values[SECRET] = self.context["private_key"].read_text()
        self.environment = ObservedEnvironment(values)
        self.event["pull_request"]["base"]["sha"] = self.base.commit["parents"][0]["sha"]

    def arguments(self, **changes):
        arguments = dict(selected_root=self.selected, selection=copy.deepcopy(self.selection),
            expected_build_key=self.build_key, trusted_source_sha=self.pin, trusted_workflow_sha=self.base.pin,
            transport_producer=self.base.producer, event_payload=self.event, environment=self.environment,
            token="not-a-real-token", variant_handoffs=self.handoffs)
        return {**arguments, **changes}

    def invoke(self, **changes):
        def stream(artifact, token, destination, *, max_bytes):
            raw = self.api(artifact["archive_download_url"], token)
            self.assertLessEqual(len(raw), max_bytes)
            Path(destination).write_bytes(raw)
        with patch("product_reuse.download_artifact_to_file", side_effect=stream):
            return caller._attest_selected_runtime_aggregate(self.repository, self.output, **self.arguments(**changes))

    def output_arguments(self):
        selected = self.output / "selected-inputs"
        originals = caller._selected_originals(selected, self.selection, self.base.producer, self.build_key)
        def original(component, phase, target):
            return originals[("runtime", component, phase, target)]
        aggregate = original("runtime-aggregate", "metadata", "aggregate")
        args = caller.collect_finalized_inputs(aggregate["stage"], aggregate["receiptPath"], "0.2.0", original)
        manifest = args.pop("manifest")
        receipt = args.pop("metadata_receipt")
        handoff = selected / "contract-input"
        args.update(contract_payload=handoff / "codex-agent-contract-0.2.0.zip",
            contract_metadata_receipt=originals[("contract", "contract", "metadata", "common")]["receiptPath"],
            contract_attestation=handoff / "codex-agent-contract-0.2.0.attestation.json",
            contract_attestation_signature=handoff / "codex-agent-contract-0.2.0.attestation.sig",
            contract_public_key=handoff / "public-key.pub")
        for key, suffix in (("variant_attestations", ".attestation.json"),
                            ("variant_attestation_signatures", ".attestation.sig"),
                            ("variant_public_keys", None)):
            args[key] = {target: self.output / "variant-inputs" / target /
                         (args["variant_bundles"][target].stem + suffix if suffix else "public-key.pub")
                         for target in NATIVE_TARGETS}
        return manifest, dict(**args, aggregate_metadata_receipt=receipt,
            aggregate_attestation=self.output / "aggregate-input/codex-agent-runtime-0.2.7.attestation.json",
            aggregate_attestation_signature=self.output / "aggregate-input/codex-agent-runtime-0.2.7.attestation.sig",
            aggregate_public_key=self.output / "aggregate-input/public-key.pub", required_trust_domain="release",
            contract_keyring=self.keyring, contract_keys_directory=self.keys,
            variant_keyring=self.keyring, variant_keys_directory=self.keys,
            aggregate_keyring=self.keyring, aggregate_keys_directory=self.keys)

    def test_complete_signed_pipeline_preserves_all_originals_and_passes_full_release_verifier(self):
        before = regular_file_inventory(self.selected, allow_empty=True)
        handoffs = {target: regular_file_inventory(path) for target, path in self.handoffs.items()}
        with patch("reuse.api_request", side_effect=self.api), \
                patch.object(caller, "verify_native_runtime_presigning_content",
                             wraps=caller.verify_native_runtime_presigning_content) as native_gate:
            self.invoke()
        self.assertEqual(list(NATIVE_TARGETS), [call.args[0] for call in native_gate.call_args_list])
        self.assertEqual(1, self.environment.secret_reads)
        manifest, arguments = self.output_arguments()
        verified = verify_runtime_aggregate_artifacts(manifest, **arguments)
        self.assertEqual("0.2.7", verified["runtimeVersion"])
        self.assertEqual(before, regular_file_inventory(self.selected, allow_empty=True))
        self.assertEqual(before, regular_file_inventory(self.output / "selected-inputs", allow_empty=True))
        self.assertEqual(self.chain["aggregate"].read_bytes(),
                         (self.output / "aggregate-input" / self.chain["aggregate"].name).read_bytes())
        self.assertEqual(self.chain["aggregate_receipt"].read_bytes(),
                         (self.output / "aggregate-input/metadata-receipt.json").read_bytes())
        for target, inventory in handoffs.items():
            self.assertEqual(inventory, regular_file_inventory(self.output / "variant-inputs" / target))
            self.assertEqual(inventory, regular_file_inventory(self.handoffs[target]))
        self.assertEqual({"transport/original-ci-phases.json", "transport/original-ci-phases.sig"},
                         {record["relativePath"] for record in regular_file_inventory(self.output / "original-evidence")})
        self.assertFalse(any(self.context["private_key"].read_bytes() in path.read_bytes()
                             for path in self.output.rglob("*") if path.is_file()))

    def test_public_entry_selects_complete_retained_carrier_without_variant_or_signer_fallback(self):
        # Reuse the real full synthetic carrier fixture; current-state transport
        # and election are seams, not claims of hosted execution.
        direct = self.work / "direct-selection"
        snapshot_regular_tree(self.selected, direct, allow_empty=True)
        (direct / "empty-diagnostic.log").unlink()
        with patch("reuse.api_request", side_effect=self.api):
            self.invoke(selected_root=direct)
        candidate = self.work / "candidate"
        candidate.mkdir()
        plan = candidate / "plan.json"
        plan.write_bytes(b"synthetic current transport plan\n")
        output = self.work / "automatic-retained"
        args = self.arguments()
        args.pop("selected_root")
        args.pop("selection")
        args["variant_handoffs"] = {}
        def capture(_plan, destination, **arguments):
            path = destination / "original/product-resume-inputs/plan/impact-plan.json"
            path.parent.mkdir(parents=True)
            path.write_bytes(plan.read_bytes())
        def select(_plan, _discovery, _state, destination, **arguments):
            snapshot_regular_tree(self.selected, destination, allow_empty=True)
            return copy.deepcopy(self.selection)
        before = regular_file_inventory(self.output, allow_empty=True)
        with patch.object(caller, "capture_runtime_resume_upload", side_effect=capture), \
                patch.object(caller, "materialize_runtime_attestation_inputs", side_effect=select), \
                patch.object(caller, "materialize_runtime_aggregate_release_evidence", return_value=self.output) as retained, \
                patch("reuse.api_request", side_effect=AssertionError("retained aggregate queried original CI")):
            caller.attest_runtime_aggregate_state_ci(self.repository, candidate, plan, output,
                artifact_id=700, artifact_sha256="sha256:" + "a" * 64, state_wave=4, **args)
        retained.assert_called_once()
        self.assertEqual(before, regular_file_inventory(output / "retained-release", allow_empty=True))
        self.assertEqual(1, self.environment.secret_reads)

    def test_missing_crosspaired_or_mutated_originals_reject_before_secret(self):
        self.environment.forbid_secret = True
        missing = {key: value for key, value in self.handoffs.items() if key != "macos-arm64"}
        wrong = {**self.handoffs, "linux-x64": self.handoffs["windows-x64"]}
        selection = copy.deepcopy(self.selection)
        selection["originals"][0]["receiptSha256"] = "sha256:" + "0" * 64
        for arguments in ({"variant_handoffs": missing}, {"variant_handoffs": wrong}, {"selection": selection}):
            with self.subTest(arguments=list(arguments)), patch("reuse.api_request", side_effect=AssertionError("early HTTP")), \
                    self.assertRaises(ValueError):
                self.invoke(**arguments)
        header = self.selected / "predecessors/runtime-linux-x64-validation-linux-x64/stage/outputs/c-abi-reference/include/codex_agent.h"
        original = header.read_bytes()
        try:
            header.write_bytes(original + b"changed original")
            with patch("reuse.api_request", side_effect=AssertionError("HTTP before original admission")), \
                    self.assertRaises(ValueError):
                self.invoke()
        finally:
            header.write_bytes(original)
        self.assertEqual(0, self.environment.secret_reads)
        self.assertFalse(self.output.exists())

    def test_original_native_signature_and_captured_mutation_fail_before_secret(self):
        self.environment.forbid_secret = True
        signature = next(self.handoffs["macos-arm64"].glob("*.attestation.sig"))
        raw, mode = signature.read_bytes(), signature.stat().st_mode
        try:
            signature.chmod(0o600)
            signature.write_bytes(b"not the original signature\n")
            with patch("reuse.api_request", side_effect=AssertionError("unsigned native HTTP")), \
                    self.assertRaises((ValueError, subprocess.CalledProcessError)):
                self.invoke()
        finally:
            signature.write_bytes(raw)
            signature.chmod(mode)
        real_gate = caller.verify_runtime_aggregate_presigning_content
        def mutate_after_gate(**arguments):
            value = real_gate(**arguments)
            path = arguments["manifest"]
            path.chmod(0o600)
            path.write_bytes(path.read_bytes() + b"changed captured bytes\n")
            return value
        with patch("reuse.api_request", side_effect=self.api), \
                patch.object(caller, "verify_runtime_aggregate_presigning_content", side_effect=mutate_after_gate), \
                self.assertRaisesRegex(ValueError, "captured evidence changed"):
            self.invoke()
        self.assertEqual(0, self.environment.secret_reads)
        self.assertFalse(self.output.exists())

    def test_failed_last_original_job_cannot_sign_or_publish_after_valid_native_proofs(self):
        self.environment.forbid_secret = True
        self.jobs[-1]["conclusion"] = "failure"
        with patch("reuse.api_request", side_effect=self.api), \
                patch.object(caller, "build_runtime_aggregate_attestation", side_effect=AssertionError("premature signer")), \
                self.assertRaises(ValueError):
            self.invoke()
        self.assertEqual(0, self.environment.secret_reads)
        self.assertFalse(self.output.exists())

    def test_signed_policy_does_not_accept_an_unrelated_private_key(self):
        private, _, _ = generate_development_key(self.work / "unrelated-key")
        self.environment.values[SECRET] = private.read_text()
        with patch("reuse.api_request", side_effect=self.api), self.assertRaises((ValueError, subprocess.CalledProcessError)):
            self.invoke()
        self.assertEqual(1, self.environment.secret_reads)
        self.assertFalse(self.output.exists())

    def test_fresh_signed_aggregate_rechecks_prepared_bytes_before_publication(self):
        def mutate_after_signing(path, value):
            actual_write_canonical_json(path, value)
            (path.parent / "aggregate-input/late-injected").write_bytes(b"unverified\n")

        with patch("reuse.api_request", side_effect=self.api), \
                patch.object(caller, "write_canonical_json", side_effect=mutate_after_signing), \
                self.assertRaisesRegex(ValueError, "verified evidence changed before publication"):
            self.invoke()
        self.assertFalse(self.output.exists())

    def test_fresh_signed_aggregate_changed_before_copy_does_not_publish(self):
        def mutate_before_copy(source, destination, *, allow_empty, expected_inventory):
            next((source / "aggregate-input").glob("*.attestation.sig")).write_bytes(
                b"changed after verification\n")
            actual_publish_regular_tree(source, destination, allow_empty=allow_empty,
                                        expected_inventory=expected_inventory)

        with patch("reuse.api_request", side_effect=self.api), \
                patch.object(caller, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.invoke()
        self.assertFalse(self.output.exists())

    def test_git_trust_cannot_gain_an_unverified_file_before_baseline(self):
        original_trust = caller._release_trust

        def inject_after_trusted_capture(*args):
            trust = original_trust(*args)
            (trust.keyring.parent / "extra-policy-file").write_bytes(b"unverified\n")
            return trust

        with patch.object(caller, "_release_trust", side_effect=inject_after_trusted_capture), \
                patch("reuse.api_request", side_effect=AssertionError("HTTP before trust gate")), \
                self.assertRaisesRegex(ValueError, "pinned Git trust"):
            self.invoke()
        self.assertEqual(0, self.environment.secret_reads)
        self.assertFalse(self.output.exists())

    def test_fresh_signed_aggregate_rechecks_caller_before_publication(self):
        def mutate_caller(path, value):
            actual_write_canonical_json(path, value)
            path.write_bytes(b"{}\n")

        with patch("reuse.api_request", side_effect=self.api), \
                patch.object(caller, "write_canonical_json", side_effect=mutate_caller), \
                self.assertRaisesRegex(ValueError, "verified evidence changed before publication"):
            self.invoke()
        self.assertFalse(self.output.exists())

    def test_retained_aggregate_never_falls_back_and_destination_alias_preserves_originals(self):
        self.environment.forbid_secret = True
        args = self.arguments()
        args.pop("selected_root")
        args.pop("selection")
        with patch("reuse.api_request", side_effect=AssertionError("retained aggregate HTTP fallback")), \
                self.assertRaisesRegex(ValueError, "exactly one direct release carrier"):
            caller.attest_runtime_aggregate_state_ci(self.repository, self.work, self.work / "plan", self.output,
                artifact_id=700, artifact_sha256="sha256:" + "a" * 64, state_wave=4,
                release_handoffs=(self.work / "first", self.work / "second"), **args)
        before = regular_file_inventory(self.selected, allow_empty=True)
        with patch("reuse.api_request", side_effect=AssertionError("unsafe output HTTP")), \
                self.assertRaisesRegex(ValueError, "overlaps"):
            caller._attest_selected_runtime_aggregate(self.repository, self.selected / "nested-output", **self.arguments())
        self.assertEqual(before, regular_file_inventory(self.selected, allow_empty=True))
        self.assertEqual(0, self.environment.secret_reads)

    def test_retired_complete_release_is_forwarded_without_secret_or_original_ci(self):
        direct_selection = self.work / "direct-selection"
        snapshot_regular_tree(self.selected, direct_selection, allow_empty=True)
        # The producer's direct selection has no undeclared root diagnostic.
        # Empty original CI diagnostics remain in the exact external carrier.
        (direct_selection / "empty-diagnostic.log").unlink()
        with patch("reuse.api_request", side_effect=self.api):
            self.invoke(selected_root=direct_selection)
        original_inventory = regular_file_inventory(self.output, allow_empty=True)
        policy_bytes = self.keyring.read_bytes()
        self.keyring.write_bytes(canonical_json_bytes({**self.policy, "activeKey": None,
                                                       "retiredKeys": [self.policy["activeKey"]]}))
        subprocess.run(["git", "add", "gradle/release"], cwd=self.repository, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "retired synthetic policy"], cwd=self.repository,
                       check=True, capture_output=True)
        retired_pin = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repository,
                                     check=True, capture_output=True, text=True).stdout.strip()
        self.environment.forbid_secret = True
        previous_reads = self.environment.secret_reads
        try:
            with patch("reuse.api_request", side_effect=AssertionError("original CI during retained reuse")), \
                    patch.object(caller, "build_runtime_aggregate_attestation", side_effect=AssertionError("re-signing")):
                result = caller._attest_selected_runtime_aggregate(
                    self.repository, self.work / "reused", **self.arguments(
                        trusted_source_sha=retired_pin, variant_handoffs={}, release_handoff=self.output, token=None))
            self.assertEqual("retained-release", result["releaseDirectory"])
            self.assertEqual(original_inventory, regular_file_inventory(
                self.work / "reused/retained-release", allow_empty=True))
            self.assertEqual(original_inventory, regular_file_inventory(self.output, allow_empty=True))
            self.assertEqual(previous_reads, self.environment.secret_reads)
            late_copy = self.work / "late-copy"

            def mutate_before_copy(source, destination, *, allow_empty, expected_inventory):
                (source / "retained-release/caller.json").write_bytes(b"changed after verification\n")
                actual_publish_regular_tree(source, destination, allow_empty=allow_empty,
                                            expected_inventory=expected_inventory)

            with patch.object(caller, "publish_regular_tree", side_effect=mutate_before_copy), \
                    patch("reuse.api_request", side_effect=AssertionError("fallback after late mutation")), \
                    self.assertRaisesRegex(ValueError, "pinned inventory"):
                caller._attest_selected_runtime_aggregate(
                    self.repository, late_copy, **self.arguments(
                        trusted_source_sha=retired_pin, variant_handoffs={},
                        release_handoff=self.output, token=None))
            self.assertFalse(late_copy.exists())
            def mutate_forwarded_carrier(path, value):
                actual_write_canonical_json(path, value)
                (path.parent / "retained-release/late-injected").write_bytes(b"unverified\n")

            with patch.object(caller, "write_canonical_json", side_effect=mutate_forwarded_carrier), \
                    patch("reuse.api_request", side_effect=AssertionError("fallback after late mutation")), \
                    self.assertRaisesRegex(ValueError, "Retained aggregate changed before publication"):
                caller._attest_selected_runtime_aggregate(
                    self.repository, self.work / "late-mutated", **self.arguments(
                        trusted_source_sha=retired_pin, variant_handoffs={},
                        release_handoff=self.output, token=None))
            self.assertFalse((self.work / "late-mutated").exists())
            self.assertEqual(original_inventory, regular_file_inventory(self.output, allow_empty=True))
            self.assertEqual(previous_reads, self.environment.secret_reads)
            changed_selection = self.work / "changed-selection"
            snapshot_regular_tree(self.selected, changed_selection, allow_empty=True)
            changed_stage = changed_selection / self.selection["originals"][0]["directory"] / "stage"
            (changed_stage / "unreceipted-file").write_bytes(b"not selected original bytes\n")
            with patch("reuse.api_request", side_effect=AssertionError("fallback on mismatched selection")), \
                    self.assertRaisesRegex(ValueError, "selected original stage"):
                caller._attest_selected_runtime_aggregate(
                    self.repository, self.work / "rejected", **self.arguments(
                        selected_root=changed_selection, trusted_source_sha=retired_pin,
                        variant_handoffs={}, release_handoff=self.output, token=None))
            self.assertFalse((self.work / "rejected").exists())
            self.assertEqual(previous_reads, self.environment.secret_reads)
        finally:
            self.keyring.write_bytes(policy_bytes)
            subprocess.run(["git", "add", "gradle/release"], cwd=self.repository, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-qm", "restore synthetic policy"], cwd=self.repository,
                           check=True, capture_output=True)
            type(self).pin = subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.repository,
                                           check=True, capture_output=True, text=True).stdout.strip()

    def test_public_entry_preserves_exact_current_transport_and_passes_selected_identity(self):
        candidate = self.work / "candidate"
        candidate.mkdir()
        plan = candidate / "plan.json"
        plan.write_bytes(b"synthetic transport plan\n")
        transport_bytes = b"exact synthetic upload bytes\n"
        def capture(_plan, destination, **arguments):
            self.assertEqual(4, arguments["state_wave"])
            destination.mkdir()
            (destination / "transport.zip").write_bytes(transport_bytes)
            captured_plan = destination / "original/product-resume-inputs/plan/impact-plan.json"
            captured_plan.parent.mkdir(parents=True)
            captured_plan.write_bytes(plan.read_bytes())
        def select(_plan, _discovery, _state, destination, **arguments):
            self.assertEqual("aggregate", arguments["target"])
            self.assertEqual(self.build_key, arguments["expected_build_key"])
            snapshot_regular_tree(self.selected, destination, allow_empty=True)
            return copy.deepcopy(self.selection)
        args = self.arguments()
        args.pop("selected_root")
        args.pop("selection")
        with patch.object(caller, "capture_runtime_resume_upload", side_effect=capture) as captured, \
                patch.object(caller, "materialize_runtime_attestation_inputs", side_effect=select) as selected, \
                patch.object(caller, "materialize_runtime_aggregate_release_evidence", return_value=None), \
                patch("reuse.api_request", side_effect=self.api):
            caller.attest_runtime_aggregate_state_ci(self.repository, candidate, plan, self.output,
                artifact_id=700, artifact_sha256="sha256:" + "a" * 64, state_wave=4, **args)
        captured.assert_called_once()
        selected.assert_called_once()
        self.assertEqual(transport_bytes, (self.output / "selected-state-transport/transport.zip").read_bytes())
        self.assertEqual(regular_file_inventory(self.selected, allow_empty=True),
                         regular_file_inventory(self.output / "selected-inputs", allow_empty=True))
        self.assertEqual(1, self.environment.secret_reads)


if __name__ == "__main__":
    unittest.main()
