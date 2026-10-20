"""Native metadata controller composition; full gates are tested separately."""

from contextlib import ExitStack, contextmanager, redirect_stderr
from copy import deepcopy
import io
import inspect
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from ci import sdk_native_metadata_workflow as workflow
from ci.tests import test_sdk_native_package_execution as fixture
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes, snapshot_regular_tree
from products.receipt import compute_build_key, write_output_manifest
from products.registry import NATIVE_TARGETS, PhaseInstanceId
from products.restore import finalize_phase_object, verify_phase_shard


class CompletedMetadataRecoveryScopeTest(unittest.TestCase):
    def test_state_replay_shares_admission_scope_and_clears_it_after_failure(self):
        from products.sdk_validation_inputs import _COLLECTION
        caches = []

        def planner(*args, **kwargs):
            cache = _COLLECTION.get()
            self.assertIsNotNone(cache)
            caches.append(cache)
            return {}

        def replay(*args, **kwargs):
            workflow.product_reuse._plan_with_sdk_tooling({}, None)
            workflow.product_reuse._plan_with_sdk_tooling({}, None)
            raise ValueError("stop after scope composition check")

        with patch.object(workflow.product_reuse, "_validate_plan", side_effect=replay), \
                patch.object(workflow.product_reuse, "plan_reuse_wave", side_effect=planner):
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, "scope composition"):
                    workflow.product_reuse._verified_product_state(None, None, None, None, {}, None)
                self.assertIsNone(_COLLECTION.get())
        self.assertIs(caches[0], caches[1])
        self.assertIs(caches[2], caches[3])
        self.assertIsNot(caches[0], caches[2])

    def test_private_recovery_reuses_one_scope_and_rejects_expired_or_changed_authority(self):
        # Control/lifetime test only; no mocked object is claimed as authenticated.
        from reuse_qualification import CompletedFrozenReuse
        from products.restore import verification_session
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary).resolve()
            source = root / "source.json"
            source.write_bytes(canonical_json_bytes({"fixture": "source"}))
            for name in ("java", "public.pub"):
                (root / name).write_bytes(b"fixture")
            (root / "evidence").mkdir()
            tooling = dict(evidence=str(root / "evidence"), publicKey=str(root / "public.pub"),
                javaExecutable=str(root / "java"), requiredTrustDomain="development", keyring=None, keysDirectory=None)
            context = dict(repository_root=root, plan_path=root / "plan", trusted_workflow_sha="a" * 40,
                token="fixture", environ=dict(CODEX_AGENT_RETAINED_SDK_INPUTS_SOURCE=str(source),
                    CODEX_AGENT_SDK_RUNTIME_VALIDATION_AUTHORIZATION='{"fixture":"authorization"}'))
            request = dict(versions={"sdk": "0.8.0"}, repositoryRevision="b" * 40)
            capability = object.__new__(CompletedFrozenReuse)
            phases = {}
            for name, value in (("check_request", None), ("check_consumer", None), ("_values", ({}, phases)),
                    ("sdk_original", {"spec": {"sdkInputs": {"source": {"fixture": "source"}, "runtimeSource": {}}}})):
                stack.enter_context(patch.object(CompletedFrozenReuse, name, return_value=value))
            stack.enter_context(patch.object(workflow.product_reuse, "_validate_plan", return_value={}))
            stack.enter_context(patch.object(workflow.product_reuse, "_consumer", return_value={"producer": {}}))
            restore = stack.enter_context(patch("products.restore.restore_object"))
            with verification_session():
                recovery = workflow.completed_validation_recovery(capability, request, tooling, context)
                self.assertIs(recovery, workflow.completed_validation_recovery(capability, request, tooling, context))
                identity = PhaseInstanceId("sdk", "python", "metadata", "desktop")
                self.assertIsNone(recovery["verify"](identity, (), {}))  # Missing originals never fetch/build.
                # Exercise the private original loader itself: fetch source only
                # after the object/receipt gate, and once per captured category.
                original = inspect.getclosurevars(recovery["records"]).nonlocals["original"]
                binary = PhaseInstanceId("sdk", "csharp", "binary", "desktop")
                phases[binary] = dict(buildKey="key", receiptSha256="receipt", objectSha256="object")
                producer = {"commit": "original", "tree": "original-tree"}
                envelope = dict(receiptBytes=b"fixture-receipt", receipt={"producer": producer})
                events = []

                def restored(obj, stage, **kwargs):
                    events.append("restore")
                    stage.mkdir(parents=True)
                    (stage / "output").write_bytes(b"fixture")
                    return dict(receiptBytes=envelope["receiptBytes"])

                restore.side_effect = restored
                with patch.object(CompletedFrozenReuse, "envelope", return_value=envelope), \
                        patch.object(CompletedFrozenReuse, "capture_object", side_effect=lambda *a, **kw: events.append("capture")), \
                        patch("sdk_handoff._ensure_observed_sdk_commit", side_effect=lambda *a: events.append("source")) as source_gate:
                    captured = original(binary)
                    self.assertIs(captured, original(binary))
                    self.assertEqual(["capture", "restore", "source"], events)
                    source_gate.assert_called_once_with(root, producer, "fixture")
                # Composition only: four qualified originals plus a new ordinary
                # host must call both existing full gates, never capture the new
                # host as if it belonged to the old qualification.
                from products.plan import sdk_validation_dependencies
                from products.sdk_validation import sdk_validation_paths
                dependencies = sdk_validation_dependencies(identity)
                package = PhaseInstanceId("sdk", "python", "package", "desktop")
                originals = {}
                for phase in (*dependencies, package):
                    receipt = dict(component=phase.component, target=phase.target, producer=producer, outputs=[])
                    raw = canonical_json_bytes(receipt)
                    originals[phase] = dict(receipt=receipt, receiptBytes=raw, receiptSha256=sha256_bytes(raw))
                    if phase.target != "windows-x64":
                        phases[phase] = dict(buildKey=phase, receiptSha256=sha256_bytes(raw), objectSha256="fixture")
                new_host = next(phase for phase in dependencies if phase.target == "windows-x64")
                request["sdkValidationEvidence"] = [dict(component="python", target=new_host.target,
                    receiptSha256=originals[new_host]["receiptSha256"],
                    **{name: "ordinary/" + name for name in sdk_validation_paths("python")})]
                admissions, captures = [], []
                proofs = {phase.target: Mock() for phase in dependencies}

                def provider(directory, records, **kwargs):
                    from products.sdk_validation_inputs import _COLLECTION
                    cache = _COLLECTION.get()
                    targets = {record["target"] for record in records}
                    self.assertEqual({"windows-x64"} if directory == root else
                                     set(NATIVE_TARGETS) - {"windows-x64"}, targets)
                    def verify(entry):
                        self.assertIsNotNone(cache)
                        self.assertIs(cache, _COLLECTION.get())
                        self.assertIn(entry["target"], targets)
                        admissions.append(entry["target"])
                        return proofs[entry["target"]]
                    return verify

                def restore_host(obj, stage, **kwargs):
                    phase = kwargs["build_key"]
                    captures.append(phase)
                    stage.mkdir(parents=True)
                    (stage / "fixture").write_bytes(b"fixture")
                    return dict(receiptBytes=originals[phase]["receiptBytes"])

                restore.side_effect = restore_host
                with patch("products.sdk_validation_inputs.sdk_validation_provider", side_effect=provider), \
                        patch.object(CompletedFrozenReuse, "envelope",
                                     side_effect=lambda record, raw=None: originals[record["buildKey"]]), \
                        patch.object(CompletedFrozenReuse, "capture_object"), \
                        patch("sdk_handoff._ensure_observed_sdk_commit"), \
                        patch("sdk_native_validation_workflow.capture_runtime_authorization"):
                    mixed = workflow.completed_validation_recovery(capability, request, tooling, context)
                    closure = inspect.getclosurevars(mixed["records"]).nonlocals
                    common = inspect.getclosurevars(closure["common_inputs"]).nonlocals["common"]
                    common.update({name: closure["private"] / name
                                   for name in ("compatibility_request", "runtime_stages", "staged_sdks")})
                    selected = tuple(originals[phase] for phase in dependencies)
                    expected = tuple(proofs[phase.target] for phase in dependencies)
                    # Parity borrows the same categories and runs its own full
                    # parity gates; recovery itself does not repeat admission.
                    records, borrowed = mixed["records"](identity, selected, originals[package])
                    self.assertEqual(4, len(records))
                    self.assertEqual(set(originals[phase]["receiptSha256"] for phase in dependencies), set(borrowed))
                    self.assertFalse(admissions)
                    scoped_verify = workflow.collection_admission_scope(mixed["verify"])
                    self.assertEqual(expected, scoped_verify(identity, selected, originals[package]))
                    self.assertEqual(expected, scoped_verify(identity, selected, originals[package]))
                    self.assertEqual([phase.target for phase in dependencies] * 2, admissions)
                    self.assertEqual({package, *(phase for phase in dependencies if phase != new_host)}, set(captures))
                    self.assertEqual(5, len(captures))  # No repeat originals, no new-host download.
                    self.assertEqual(root / "ordinary/runtimeAuthorization", mixed["authorizations"]["windows-x64"])
                    for phase in dependencies:
                        proofs[phase.target].receipt_value.assert_called_with(originals[phase]["receipt"], originals[package]["receipt"])
                    altered = [dict(selected[0], receiptBytes=b"wrong-original"), *selected[1:]]
                    with self.assertRaisesRegex(ValueError, "selected original"):
                        mixed["verify"](identity, altered, originals[package])
                context["environ"]["CODEX_AGENT_SDK_RUNTIME_VALIDATION_AUTHORIZATION"] = '{}'
                with self.assertRaisesRegex(ValueError, "changed its caller authority"):
                    recovery["verify"](identity, (), {})
            with self.assertRaisesRegex(ValueError, "outlived"):
                recovery["verify"](identity, (), {})
            with verification_session(), self.assertRaisesRegex(TypeError, "concrete completed authority"):
                workflow.completed_validation_recovery(object(), request, tooling, context)


class SdkNativeMetadataWorkflowTest(unittest.TestCase):
    name = staticmethod(fixture.SdkNativePackageExecutionTest.name)
    fixture = fixture.SdkNativePackageExecutionTest.fixture

    def setUp(self):
        fixture.SdkNativePackageExecutionTest.setUp(self)
        self.destination = self.root / "build/metadata"
        self.preparation = deepcopy(self.ready)
        self.ready = deepcopy(self.ready)
        self.ready["phase"] = "metadata"
        self.ready["buildKey"] = compute_build_key(**{name: self.ready[name] for name in
            ("product", "component", "phase", "target", "inputs")})
        self.instance = PhaseInstanceId("sdk", "python", "metadata", "desktop")
        self.selection["consumers"] = [{"product": "sdk", "component": "python",
                                        "phase": "metadata", "target": "desktop"}]
        for path, contents in {
                self.root / "caller-keyring.json": b"caller product policy\n",
                self.root / "tooling-public.pub": b"caller tooling key\n",
                self.root / "java": b"trusted java fixture\n",
        }.items():
            path.write_bytes(contents)
        (self.root / "caller-keys").mkdir()
        self.tooling_evidence = self.root / "tooling-evidence"
        self.tooling_evidence.mkdir()
        (self.tooling_evidence / "attestation.json").write_bytes(b"caller tooling evidence\n")
        self.tooling = {"evidence": str(self.tooling_evidence),
            "publicKey": str(self.root / "tooling-public.pub"), "javaExecutable": str(self.root / "java"),
            "requiredTrustDomain": "development", "keyring": None, "keysDirectory": None}
        self.arguments = {"component": "python", "expected_build_key": self.ready["buildKey"],
            "preparation_component": "python", "preparation_build_key": self.preparation["buildKey"],
            "preparation_state": self.preparation_state, "prepared_artifact_id": 72,
            "prepared_artifact_sha256": "sha256:" + "d" * 64,
            "sdk_inputs_artifact_id": 71, "sdk_inputs_artifact_sha256": "sha256:" + "b" * 64,
            "trusted_workflow_sha": "c" * 40, "keyring": self.root / "caller-keyring.json",
            "keys_directory": self.root / "caller-keys", "repository_root": self.root,
            "environ": {"CONTROL": "explicit environment"}, "token": "synthetic token",
            "tooling_evidence": self.tooling_evidence, "tooling_public_key": self.root / "tooling-public.pub",
            "java_executable": self.root / "java", "required_trust_domain": "development"}
        self.candidate = None

    def tearDown(self):
        fixture.SdkNativePackageExecutionTest.tearDown(self)

    @contextmanager
    def verified(self, *args, **kwargs):
        self.assertEqual((workflow.PhaseInstanceId("sdk", self.arguments["component"], "metadata", "desktop"),),
                         kwargs.pop("requested_scope"))
        self.assertEqual((self.plan_path, self.discovery, self.state), args)
        self.assertEqual({"artifact_id": 71, "artifact_sha256": self.arguments["sdk_inputs_artifact_sha256"],
            "trusted_workflow_sha": self.arguments["trusted_workflow_sha"],
            "keyring": self.arguments["keyring"], "keys_directory": self.arguments["keys_directory"],
            "repository_root": self.root, "environ": self.arguments["environ"],
            "token": self.arguments["token"], "sdk_validation_tooling": self.tooling}, kwargs)
        self.events.append("enter")
        self.live = True
        try:
            yield self.verified_inputs
            self.events.append("exit-check")
            if self.failure == "late-context":
                raise ValueError("late SDK authentication failure")
            changed = {
                "late-input": self.destination / "inputs/producer.json",
                "late-runtime": self.destination / f"runtime-stages/{NATIVE_TARGETS[0]}/package/outputs/original",
                "late-staged-sdk": self.destination / "staged-sdks/sdk",
                "late-sdk-input": self.destination / "sdk-inputs/sdk-compatibility-request.json",
                "late-capture": self.capture_path / "original/staged-sdks/sdk",
                "late-candidate": self.candidate / "phase-receipt.json" if self.candidate else self.destination,
            }
            if self.failure in changed:
                changed[self.failure].write_bytes(b"changed after admission\n")
            self.events.append("exited")
        finally:
            self.live = False

    def inspect(self, *args, **kwargs):
        self.assertEqual((workflow.PhaseInstanceId("sdk", self.arguments["preparation_component"],
                         self.preparation["phase"], self.preparation["target"]),),
                         kwargs.pop("requested_scope"))
        self.assertTrue(self.live)
        self.events.append("inspect")
        self.assertEqual((self.plan_path, self.discovery, self.preparation_state), args)
        self.assertEqual({"repository_root": self.root, "environ": self.arguments["environ"],
                          "sdk_validation_tooling": self.tooling,
                          "sdk_original_workflow_sha": self.arguments["trusted_workflow_sha"]}, kwargs)
        rows = [self.preparation]
        if self.failure == "missing-preparation":
            rows = []
        return {"readyPlans": rows}

    def capture(self, plan, destination, **kwargs):
        self.assertTrue(self.live)
        self.events.append("capture")
        self.capture_path = destination
        self.assertEqual(self.plan_path, plan)
        self.assertEqual(self.preparation, kwargs.pop("expected_phase_plan"))
        self.assertEqual({"artifact_id": 72, "artifact_sha256": self.arguments["prepared_artifact_sha256"],
            "trusted_workflow_sha": self.arguments["trusted_workflow_sha"], "repository_root": self.root,
            "environ": self.arguments["environ"], "token": self.arguments["token"]}, kwargs)
        path = destination / "original/staged-sdks/sdk"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"authenticated staged SDK fixture\n")
        return {"captureProducer": {**self.producer, "runAttempt": 9}
                if self.failure == "wrong-preparation-producer" else self.producer}

    def materialize(self, plan, discovery, state, instance, destination, **kwargs):
        self.assertTrue(self.live)
        self.events.append("materialize")
        self.assertEqual((self.plan_path, self.discovery, self.state, self.instance, self.destination / "inputs"),
                         (plan, discovery, state, instance, destination))
        self.assertEqual({"expected_build_key": self.ready["buildKey"], "repository_root": self.root,
            "environ": self.arguments["environ"], "sdk_validation_tooling": self.tooling,
            "sdk_original_workflow_sha": self.arguments["trusted_workflow_sha"],
            "materialized_scope": (PhaseInstanceId("contract", "contract", "metadata", "common"),
                                   *self.original_paths)}, kwargs)
        for identity, original in {**self.original_paths,
                PhaseInstanceId("contract", "contract", "metadata", "common"): self.contract}.items():
            target = destination / self.name(identity)
            snapshot_regular_tree(original["stage"], target / "stage")
            (target / "phase-receipt.json").write_bytes(original["receiptPath"].read_bytes())
        (destination / "producer.json").write_bytes(canonical_json_bytes(self.producer))
        (destination / "phase-plan.json").write_bytes(canonical_json_bytes(self.ready))
        return self.ready

    def metadata(self, plan, discovery, state, destination, **kwargs):
        self.assertTrue(self.live)
        self.events.append("metadata")
        self.assertEqual((self.plan_path, self.discovery, self.state, self.destination / "candidate"),
                         (plan, discovery, state, destination))
        self.assertEqual({"component": "python", "expected_build_key": self.ready["buildKey"],
            "compatibility_request": self.destination / "sdk-inputs/sdk-compatibility-request.json",
            "runtime_stages": self.destination / "runtime-stages",
            "staged_sdks": self.destination / "staged-sdks", "sdk_validation_tooling": self.tooling,
            "repository_root": self.root, "environ": self.arguments["environ"],
            "sdk_original_workflow_sha": self.arguments["trusted_workflow_sha"]}, kwargs)
        self.assertEqual({row["relativePath"] for row in regular_file_inventory(self.sdk)},
                         {row["relativePath"] for row in regular_file_inventory(self.destination / "sdk-inputs")})
        for identity, original in self.original_paths.items():
            self.assertEqual(regular_file_inventory(original["stage"]), regular_file_inventory(
                self.destination / "runtime-stages" / identity.component / identity.phase))
        if self.failure == "metadata":
            raise ValueError("existing five-host metadata caller rejected")
        stage = destination / "stage"
        (stage / "outputs").mkdir(parents=True)
        (stage / "outputs/metadata.json").write_bytes(b"synthetic admitted metadata output\n")
        write_output_manifest(stage, "sdk", "python", "metadata", "desktop", "0.3.0", {"metadata": "outputs"})
        self.candidate = destination / "worker/shard"
        producer = ({**self.producer, "runAttempt": self.producer["runAttempt"] + 1}
                    if self.failure == "wrong-producer" else self.producer)
        finalized = finalize_phase_object(stage_root=stage, phase_plan=self.ready, producer=producer,
            product_version="0.3.0", trust_domain="development", destination=self.candidate)
        return verify_phase_shard(self.candidate, self.instance) if self.failure != "wrong-result" else {
            **finalized, "receiptBytes": b"wrong"}

    def invoke(self, **changes):
        with patch.object(workflow.sdk_workflow, "verified_inputs", self.verified), \
                patch.object(workflow.product_reuse, "inspect_products", side_effect=self.inspect) as inspect, \
                patch.object(workflow.product_reuse, "capture_sdk_native_prepared_upload",
                             side_effect=self.capture) as capture, \
                patch.object(workflow.product_reuse, "materialize_product_predecessors",
                             side_effect=self.materialize) as materialize, \
                patch.object(workflow.product_reuse, "execute_sdk_metadata", side_effect=self.metadata) as metadata, \
                patch.object(workflow.product_reuse, "_runtime_worker_checkout",
                             side_effect=ValueError("tracked source changed after S858")
                             if self.failure == "late-source" else None) as checkout:
            self.inspect_mock, self.capture_mock = inspect, capture
            self.materialize_mock, self.metadata_mock, self.checkout_mock = materialize, metadata, checkout
            return workflow.execute(self.plan_path, self.discovery, self.state, self.destination,
                                    **{**self.arguments, **changes})

    def test_authenticates_preparation_runtime_and_s858_before_publishing_existing_metadata_shard(self):
        from products.sdk_validation_inputs import _COLLECTION
        caches = []
        def observe(delegate):
            def wrapped(*args, **kwargs):
                cache = _COLLECTION.get()
                self.assertIsNotNone(cache)
                caches.append(cache)
                return delegate(*args, **kwargs)
            return wrapped
        with patch.object(self, "verified", side_effect=observe(self.verified)), \
                patch.object(self, "inspect", side_effect=observe(self.inspect)), \
                patch.object(self, "materialize", side_effect=observe(self.materialize)), \
                patch.object(self, "metadata", side_effect=observe(self.metadata)):
            result = self.invoke()
        self.assertEqual(4, len(caches))
        self.assertTrue(all(cache is caches[0] for cache in caches))
        self.assertIsNone(_COLLECTION.get())
        self.assertEqual(["enter", "inspect", "capture", "materialize", "metadata",
                          "exit-check", "exited"], self.events)
        self.assertEqual(result, verify_phase_shard(self.destination / "shard", self.instance))
        self.assertEqual(b"authenticated staged SDK fixture\n",
                         (self.destination / "prepared-upload/original/staged-sdks/sdk").read_bytes())
        self.assertFalse(self.capture_path.exists())
        self.metadata_mock.assert_called_once()

    def test_same_apple_policy_reaches_all_replays_and_existing_metadata_controller(self):
        policy = fixture.caller_apple_policy(self.root / "caller")
        before = dict(policy)
        admissions = fixture.caller_metadata_admissions()
        capability = object()  # Forwarding fixture; no authority is inferred.

        def forwarded(delegate):
            def invoke(*args, **kwargs):
                self.assertIs(policy, kwargs.pop("sdk_apple_validation_policy"))
                self.assertIs(capability, kwargs.pop("completed_frozen"))
                for name, admission in admissions.items():
                    self.assertIs(admission, kwargs.pop(name))
                return delegate(*args, **kwargs)
            return invoke

        with patch.object(self, "verified", side_effect=forwarded(self.verified)) as verified, \
                patch.object(self, "inspect", side_effect=forwarded(self.inspect)) as inspect, \
                patch.object(self, "materialize", side_effect=forwarded(self.materialize)) as materialize, \
                patch.object(self, "metadata", side_effect=forwarded(self.metadata)) as metadata:
            result = self.invoke(sdk_apple_validation_policy=policy, completed_frozen=capability, **admissions)
        for replay in (verified, inspect, materialize, metadata):
            replay.assert_called_once()
            self.assertIs(policy, replay.call_args.kwargs["sdk_apple_validation_policy"])
            for name, admission in admissions.items():
                self.assertIs(admission, replay.call_args.kwargs[name])
                self.assertNotIn(name, result["receipt"])
        self.assertEqual(before, policy)
        self.assertNotIn("sdkAppleValidationPolicy", result["receipt"])
        self.assertNotIn("sdk_apple_validation_policy", result["receipt"])
        self.assertEqual(["enter", "inspect", "capture", "materialize", "metadata", "exit-check", "exited"], self.events)

    def test_selection_preparation_producer_contract_and_runtime_pairing_fail_before_metadata(self):
        for failure in ("unselected", "missing-preparation", "wrong-preparation-producer", "contract", "runtime"):
            with self.subTest(case=failure):
                self.destination = self.root / f"build/{failure}"
                self.failure = failure
                selection = deepcopy(self.selection)
                receipts = dict(self.receipt_bytes)
                if failure == "unselected":
                    self.selection["consumers"] = []
                elif failure == "contract":
                    self.selection["contractPayloadSha256"] = "sha256:" + "e" * 64
                elif failure == "runtime":
                    self.receipt_bytes[next(iter(self.receipt_bytes))] = b"wrong original receipt"
                try:
                    with self.assertRaises(ValueError):
                        self.invoke()
                    self.metadata_mock.assert_not_called()
                    self.assertFalse((self.destination / "shard").exists())
                finally:
                    self.selection.clear()
                    self.selection.update(selection)
                    self.receipt_bytes.clear()
                    self.receipt_bytes.update(receipts)

    def test_metadata_and_all_late_input_failures_never_publish_root_shard_or_carrier(self):
        for failure in ("metadata", "wrong-result", "wrong-producer", "late-context", "late-source", "late-input", "late-runtime",
                        "late-staged-sdk", "late-sdk-input", "late-capture", "late-candidate"):
            with self.subTest(case=failure):
                self.destination = self.root / f"build/{failure}"
                self.failure = failure
                try:
                    with self.assertRaises(ValueError):
                        self.invoke()
                    self.assertFalse((self.destination / "shard").exists())
                    self.assertFalse((self.destination / "prepared-upload").exists())
                finally:
                    self.plan_path.write_bytes(self.original_plan_bytes)

    def test_invalid_identity_overlap_and_tooling_pair_reject_before_context(self):
        for changes in ({"component": "javascript"}, {"preparation_component": "sdk-ios"},
                        {"tooling_keyring": self.root / "tooling-keyring.json"}):
            with self.subTest(changes=changes), patch.object(workflow.sdk_workflow, "verified_inputs") as verified:
                with self.assertRaises(ValueError):
                    self.invoke_without_context(**changes)
                verified.assert_not_called()
        for destination in (self.discovery / "nested", self.tooling_evidence / "nested", self.root.parent / "outside"):
            with self.subTest(destination=destination), patch.object(workflow.sdk_workflow, "verified_inputs") as verified:
                with self.assertRaises(ValueError):
                    self.invoke_without_context(destination=destination)
                verified.assert_not_called()

    def invoke_without_context(self, destination=None, **changes):
        return workflow.execute(self.plan_path, self.discovery, self.state,
            self.destination if destination is None else destination, **{**self.arguments, **changes})


class SdkNativeMetadataCliTest(unittest.TestCase):
    def test_metadata_policy_cli_preserves_objects_and_context_lifetime(self):
        fixture.assert_metadata_cli_context(self, workflow, self.argv)

    def setUp(self):
        self.values = {name: Path("/synthetic") / name for name in
            ("plan", "discovery", "state", "destination", "preparation_state", "keyring", "keys_directory",
             "repository_root", "tooling_evidence", "tooling_public_key", "java_executable")}
        self.values.update(component="python", preparation_component="rust",
            expected_build_key="sha256:" + "a" * 64, preparation_build_key="sha256:" + "b" * 64,
            prepared_artifact_id=72, prepared_artifact_sha256="sha256:" + "c" * 64,
            sdk_inputs_artifact_id=71, sdk_inputs_artifact_sha256="sha256:" + "d" * 64,
            trusted_workflow_sha="e" * 40, required_trust_domain="development")
        names = {"discovery": "discovery-root", "state": "state-root",
                 "preparation_state": "preparation-state"}
        self.argv = [part for name, value in self.values.items()
                     for part in ("--" + names.get(name, name.replace("_", "-")), str(value))]

    def test_cli_forwards_only_fixed_inputs_and_environment_token(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "synthetic token"}, clear=True), \
                patch.object(workflow, "execute") as execute:
            self.assertEqual(0, workflow.main(self.argv))
            execute.assert_called_once_with(**self.values, tooling_keyring=None, tooling_keys_directory=None,
                                            environ=os.environ, token="synthetic token")

    def test_cli_canonical_apple_policy_forwarding_and_malformed_rejection(self):
        with tempfile.TemporaryDirectory(prefix="native-metadata-apple-cli-") as temporary:
            root = Path(temporary).resolve()
            path = root / "apple policy.json"
            policy = fixture.caller_apple_policy(root)
            raw = canonical_json_bytes(policy)
            path.write_bytes(raw)
            with patch.dict(os.environ, {"GITHUB_TOKEN": "caller token"}, clear=True), \
                    patch.object(workflow, "execute") as execute:
                self.assertEqual(0, workflow.main([*self.argv, "--sdk-apple-validation-policy", str(path)]))
                execute.assert_called_once_with(**self.values, tooling_keyring=None, tooling_keys_directory=None,
                    environ=os.environ, token="caller token", sdk_apple_validation_policy=policy)
                self.assertEqual(raw, path.read_bytes())
            for invalid in (b"{", b"[]\n", b"null\n", b'{ "plan": "noncanonical" }\n'):
                with self.subTest(invalid=invalid), patch.object(workflow, "execute") as execute, \
                        redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                    path.write_bytes(invalid)
                    workflow.main([*self.argv, "--sdk-apple-validation-policy", str(path)])
                self.assertEqual(2, failure.exception.code)
                execute.assert_not_called()

    def test_cli_rejects_partial_tooling_policy_and_unknown_flags(self):
        for argv in (self.argv + ["--tooling-keyring", "/keyring"], self.argv + ["--command", "anything"]):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                workflow.main(argv)
            self.assertEqual(2, raised.exception.code)


if __name__ == "__main__":
    unittest.main()
