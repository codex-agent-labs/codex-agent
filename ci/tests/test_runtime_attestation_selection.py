"""Selection translation over real immutable objects; replay authority is a seam.

Existing predecessor/resume tests cover full replay. These checks neither mint
host evidence nor claim the mocked state admission is an authenticated CI run.
"""

from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from ci.tests import test_runtime_release_caller as fixture
from products.inventory import load_canonical_json_bytes, regular_file_inventory, snapshot_regular_tree
from products.restore import store_local_object
from products.registry import PhaseInstanceId
import product_reuse
from ci import runtime_release


TARGET = fixture.TARGET
PHASES = fixture.fixture.PHASES


class RuntimeAttestationCliTest(unittest.TestCase):
    def test_cli_routes_exact_selected_state_without_signing_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            event = Path(directory).resolve() / "event.json"
            event.write_text('{"number":31}\n')
            environment = {"GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": "pull_request",
                           "GITHUB_REPOSITORY": "owner/repo", "GITHUB_SHA": "a" * 40,
                           "GITHUB_RUN_ID": "12", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_TOKEN": "fixture"}
            args = []
            for name, value in {"repository-root": "trusted", "candidate-root": "candidate",
                                "plan": "plan.json", "destination": "output", "target": TARGET,
                                "expected-build-key": "sha256:" + "b" * 64,
                                "artifact-sha256": "sha256:" + "c" * 64,
                                "trusted-source-sha": "d" * 40, "trusted-workflow-sha": "e" * 40,
                                "validation-tree": "f" * 40, "artifact-id": "42", "state-wave": "3"}.items():
                args.extend(("--" + name, value))
            with patch.dict(runtime_release.os.environ, environment, clear=True), \
                    patch.object(runtime_release, "attest_runtime_state_ci") as caller:
                runtime_release.main(args)
            self.assertEqual((Path("trusted"), Path("candidate"), Path("plan.json"), Path("output")),
                             caller.call_args.args)
            actual = caller.call_args.kwargs
            self.assertEqual(3, actual["state_wave"])
            self.assertEqual(42, actual["artifact_id"])
            self.assertEqual(31, actual["transport_producer"]["pullRequest"])
            self.assertEqual("f" * 40, actual["transport_producer"]["tree"])
            self.assertEqual("sha256:" + "b" * 64, actual["expected_build_key"])
            aggregate_args = list(args)
            aggregate_args[aggregate_args.index("--target") + 1] = "aggregate"
            for target in product_reuse.NATIVE_TARGETS:
                aggregate_args.extend(("--variant-handoff", f"{target}=originals/{target}"))
            aggregate = Mock()
            # CLI routing only: the independently tested protected caller owns admission.
            with patch.dict(runtime_release.os.environ, environment, clear=True), \
                    patch.dict("sys.modules", {"runtime_aggregate_release": SimpleNamespace(
                        attest_runtime_aggregate_state_ci=aggregate)}):
                runtime_release.main(aggregate_args)
            self.assertEqual({target: Path("originals") / target for target in product_reuse.NATIVE_TARGETS},
                             aggregate.call_args.kwargs["variant_handoffs"])
            self.assertNotIn("target", aggregate.call_args.kwargs)
            self.assertEqual(caller.call_args.args, aggregate.call_args.args)
            self.assertEqual(actual["transport_producer"], aggregate.call_args.kwargs["transport_producer"])
            retained_args = list(args)
            retained_args[retained_args.index("--target") + 1] = "aggregate"
            retained_args += ["--release-handoff", "original-release"]
            with patch.dict(runtime_release.os.environ, environment, clear=True), \
                    patch.dict("sys.modules", {"runtime_aggregate_release": SimpleNamespace(
                        attest_runtime_aggregate_state_ci=aggregate)}):
                runtime_release.main(retained_args)
            self.assertEqual({}, aggregate.call_args.kwargs["variant_handoffs"])
            self.assertEqual((Path("original-release"),), aggregate.call_args.kwargs["release_handoffs"])
            from contextlib import redirect_stderr
            from io import StringIO
            for malformed in (aggregate_args[:-2], aggregate_args + ["--variant-handoff", "linux-x64=duplicate"],
                              args + ["--variant-handoff", "linux-x64=unexpected"],
                              args + ["--variant-handoff", "unknown=path"],
                              retained_args + ["--variant-handoff", "linux-x64=unexpected"],
                              retained_args + ["--release-handoff", "second-release"]):
                with self.subTest(arguments=malformed), redirect_stderr(StringIO()), \
                        patch.dict(runtime_release.os.environ, {}, clear=True), self.assertRaises(SystemExit) as error:
                    runtime_release.main(malformed)
                self.assertEqual(2, error.exception.code)


class RuntimeAttestationSelectionTest(unittest.TestCase):
    setUpClass = classmethod(fixture.RuntimeReleaseCallerTest.setUpClass.__func__)
    commit_policy = classmethod(fixture.RuntimeReleaseCallerTest.commit_policy.__func__)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="runtime-selection-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name).resolve()
        self.candidate = self.work / "candidate"
        fixture.trusted_repository(self.candidate)
        snapshot_regular_tree(self.keys, self.candidate / "gradle/release/keys")
        (self.candidate / "gradle/release/product-signing-keys.json").write_bytes(self.keyring.read_bytes())
        subprocess.run(["git", "add", "gradle/release"], cwd=self.candidate, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "candidate public policy fixture"], cwd=self.candidate,
                       check=True, capture_output=True)
        def git(argument):
            return subprocess.run(["git", "rev-parse", argument], cwd=self.candidate,
                                  check=True, capture_output=True, text=True).stdout.strip()
        self.producer = {**self.source.producer, "commit": git("HEAD"), "tree": git("HEAD^{tree}")}
        self.discovery = self.candidate / "build/discovery"
        self.discovery.mkdir(parents=True)
        snapshot_regular_tree(self.contract["attestation"].parent, self.discovery / "contract-trust")
        paths = {phase: self.discovery / "contract-trust" / self.contract[phase].name
                 for phase in ("attestation", "signature")}
        public = self.discovery / "public-key.pub"
        public.write_bytes(self.context["public_key"].read_bytes())
        evidence = {"expectedTrustDomain": "release", "attestation": str(paths["attestation"].relative_to(self.candidate)),
                    "attestationSignature": str(paths["signature"].relative_to(self.candidate)),
                    "publicKey": str(public.relative_to(self.candidate))}
        records, sources = {}, {}
        self.originals = {}
        for product, component, target in (("contract", "contract", "common"), ("runtime", TARGET, TARGET)):
            for phase in PHASES:
                instance = PhaseInstanceId(product, component, phase, target)
                if product == "contract":
                    receipt = self.chain["contract"]["execution_closure"] / "receipts" / f"{phase}.json"
                    stage = self.root / "chain/contract-source" / f"{phase}-stage"
                else:
                    receipt = self.receipts[phase]
                    key = next(key for key in self.context["phase_stages"] if
                               (key.product, key.component, key.phase, key.target) == (product, component, phase, target))
                    stage = self.context["phase_stages"][key]
                stored = store_local_object(stage, receipt, self.discovery / "objects")
                value = load_canonical_json_bytes(receipt.read_bytes())
                records[instance] = {**product_reuse._identity_record(instance), "buildKey": value["buildKey"],
                                     "receiptSha256": stored["receiptSha256"], "objectSha256": stored["objectSha256"]}
                sources[instance] = stored["path"]
                self.originals[instance] = receipt.read_bytes()
        self.metadata = PhaseInstanceId("runtime", TARGET, "metadata", TARGET)
        self.state = SimpleNamespace(producer=self.producer, prior_by_instance=records,
            sources=sources, prior_carrier_phases=records, rebased_request={"contractEvidence": evidence})
        self.output = self.candidate / "build/selected"

    def materialize(self, **changes):
        kwargs = dict(target=TARGET, expected_build_key=self.state.prior_by_instance[self.metadata]["buildKey"],
                      repository_root=self.candidate, environ={})
        kwargs.update(changes)
        with patch.object(product_reuse, "_verified_product_state", return_value=self.state) as replay:
            result = product_reuse.materialize_runtime_attestation_inputs(
                self.candidate / "not-read-plan.json", self.discovery, self.discovery, self.output, **kwargs)
            replay.assert_called_once()
        return result

    def test_completed_selection_restores_exact_eight_originals_without_a_ready_build(self):
        before = regular_file_inventory(self.discovery)
        selection = self.materialize()
        self.assertEqual(self.producer, selection["producer"])
        self.assertEqual(self.state.prior_by_instance[self.metadata], selection["metadata"])
        for phase, relative in selection["phaseReceipts"].items():
            self.assertEqual(self.originals[PhaseInstanceId("runtime", TARGET, phase, TARGET)],
                             (self.output / relative).read_bytes())
            self.assertTrue((self.output / "runtime" / TARGET / phase / "output-manifest.json").is_file())
        self.assertEqual(self.chain["variants"]["variant_bundles"][TARGET].read_bytes(),
                         (self.output / selection["variantPayload"]).read_bytes())
        self.assertEqual(before, regular_file_inventory(self.discovery))
        self.assertFalse(any(self.output.glob("predecessors/runtime-*/stage")))
        self.assertEqual(set(PHASES), set(selection["receiptSha256s"]))

    def test_wrong_key_missing_original_and_development_contract_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "complete retained closure"):
            self.materialize(expected_build_key="sha256:" + "0" * 64)
        binary = PhaseInstanceId("runtime", TARGET, "binary", TARGET)
        original = self.state.sources.pop(binary)
        with self.assertRaisesRegex(ValueError, "complete retained closure"):
            self.materialize()
        self.state.sources[binary] = original
        self.state.rebased_request["contractEvidence"]["expectedTrustDomain"] = "development"
        with self.assertRaisesRegex(ValueError, "release Contract"):
            self.materialize()
        self.assertFalse(self.output.exists())

    def test_completed_aggregate_restores_all_fifty_originals_without_building(self):
        aggregate = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        instances = product_reuse._dependency_closure((aggregate,))
        self.assertEqual(50, len(instances))
        for instance in instances:
            if instance in self.state.sources:
                continue
            if instance.component == "runtime-aggregate":
                stage = self.chain["root"] / "aggregate-stage"
                receipt = self.chain["aggregate_receipt"]
            else:
                key = next(key for key in self.context["phase_stages"]
                           if all(getattr(key, name) == getattr(instance, name)
                                  for name in ("product", "component", "phase", "target")))
                stage = self.context["phase_stages"][key]
                if instance.component in product_reuse.NATIVE_TARGETS:
                    receipt = self.chain["variants"]["variant_phase_receipts"][instance.target][instance.phase]
                else:
                    receipt = next(record["receipt"] for record in self.chain["adapters"]["adapter_receipts"]
                                   if all(record[name] == getattr(instance, name)
                                          for name in ("component", "phase", "target")))
            stored = store_local_object(stage, receipt, self.discovery / "objects")
            value = load_canonical_json_bytes(receipt.read_bytes())
            self.state.prior_by_instance[instance] = {
                **product_reuse._identity_record(instance), "buildKey": value["buildKey"],
                "receiptSha256": stored["receiptSha256"], "objectSha256": stored["objectSha256"]}
            self.state.sources[instance] = stored["path"]
            self.originals[instance] = receipt.read_bytes()
        before = regular_file_inventory(self.discovery)
        result = self.materialize(target="aggregate", expected_build_key=self.state.prior_by_instance[aggregate]["buildKey"])
        self.assertEqual(50, len(result["originals"]))
        self.assertEqual(self.chain["aggregate"].read_bytes(), (self.output / result["aggregateManifest"]).read_bytes())
        for record in result["originals"]:
            instance = PhaseInstanceId(*(record[name] for name in ("product", "component", "phase", "target")))
            self.assertEqual(self.originals[instance],
                             (self.output / record["directory"] / "phase-receipt.json").read_bytes())
        self.assertEqual(before, regular_file_inventory(self.discovery))

    def test_corrupt_original_object_never_publishes_a_selection(self):
        path = self.state.sources[self.metadata]
        path.chmod(0o600)
        path.write_bytes(path.read_bytes() + b"changed object")
        with self.assertRaises(ValueError):
            self.materialize()
        self.assertFalse(self.output.exists())

    def test_state_caller_binds_selection_to_real_retained_handoff_without_signing(self):
        import runtime_release
        from ci.tests.test_contract_release_context import contract_context
        from ci.tests.test_contract_release_capture import ObservedEnvironment

        _, event, values = contract_context()
        values["GITHUB_SHA"] = self.producer["commit"]
        environment = ObservedEnvironment(values)
        environment.forbid_secret = True
        plan = self.candidate / "impact.json"
        plan.write_bytes(b"{}\n")
        output = self.work / "signed-selected"

        def capture(_plan, destination, **kwargs):
            # Transport and replay admission are explicit seams in this test;
            # object restore, Contract/native signatures and contents are real.
            self.assertEqual(4, kwargs["state_wave"])
            original = destination / "original"
            snapshot_regular_tree(self.discovery, original / "product-resume-state")
            snapshot_regular_tree(self.discovery, original / "runtime-state")
            captured_plan = original / "product-resume-inputs/plan/impact-plan.json"
            captured_plan.parent.mkdir(parents=True)
            captured_plan.write_bytes(plan.read_bytes())

        with patch.object(runtime_release, "capture_runtime_resume_upload", side_effect=capture) as transport, \
                patch.object(product_reuse, "_verified_product_state", return_value=self.state) as replay, \
                patch("reuse.api_request", side_effect=AssertionError("HTTP beyond captured transport")), \
                patch("products.runtime_attestation.sign_manifest", side_effect=AssertionError("resigning")):
            runtime_release.attest_runtime_state_ci(
                self.repository, self.candidate, plan, output, target=TARGET,
                expected_build_key=self.state.prior_by_instance[self.metadata]["buildKey"],
                artifact_id=700, artifact_sha256="sha256:" + "a" * 64, state_wave=4,
                trusted_source_sha=self.pin, trusted_workflow_sha=self.source.pin,
                transport_producer=self.producer, event_payload=event, environment=environment,
                token="not-a-real-token", release_handoffs=(self.handoff,))
            transport.assert_called_once()
            replay.assert_called_once()
        self.assertEqual(regular_file_inventory(self.handoff), regular_file_inventory(output / "runtime-input"))
        selection = load_canonical_json_bytes((output / "selected-state.json").read_bytes())
        self.assertEqual(self.state.prior_by_instance[self.metadata], selection["metadata"])
        self.assertEqual(self.producer, selection["producer"])
        self.assertNotIn("variantPayload", selection)
        self.assertTrue((output / "selected-state-transport/original/runtime-state").is_dir())
        self.assertEqual(0, environment.secret_reads)


if __name__ == "__main__":
    unittest.main()
