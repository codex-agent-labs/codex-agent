"""Same-run Core metadata must be independently observed and re-admitted."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from ci import sdk_core_metadata_same_campaign as selected
from ci.products.inventory import sha256_bytes, snapshot_regular_tree, write_canonical_json
from ci.products.registry import SDK_FACADE_TARGETS


class SameCampaignCoreMetadataTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="same-campaign-core-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.discovery = self.root / "discovery"
        self.before = self.root / "before"
        self.after = self.root / "after"
        for path in (self.discovery, self.before, self.after):
            path.mkdir()
            (path / "record").write_bytes(b"fixed")
        self.receipt_path = self.root / "metadata-receipt.json"
        self.key = "sha256:" + "a" * 64
        self.producer = {"commit": "b" * 40}
        self.receipt = {"product": "sdk", "component": "sdk-core", "phase": "metadata",
                        "target": "common", "buildKey": self.key, "producer": self.producer}
        write_canonical_json(self.receipt_path, self.receipt)
        self.digest = sha256_bytes(self.receipt_path.read_bytes())
        self.outside = self.root / "outside"
        self.captures = self.outside / "evidence"
        self.captures.mkdir(parents=True)
        self.validations = {}
        for target in SDK_FACADE_TARGETS:
            capture = self.captures / target
            capture.mkdir()
            (capture / "record").write_bytes(b"original validation")
            receipt = self.root / (target + ".json")
            receipt.write_bytes(target.encode())
            self.validations[target] = {"captureRoot": str(capture),
                                        "validationReceipt": str(receipt)}
        self.fresh = self.outside / "policy.json"
        write_canonical_json(self.fresh, {"evidenceRoot": str(self.captures),
                              "records": [], "policy": {"validations": self.validations,
                              "toolingEvidence": "/tooling", "toolingPublicKey": "/key",
                              "javaExecutable": "/java", "toolingTrustDomain": "release",
                              "toolingKeyring": "/keyring", "toolingKeysDirectory": "/keys"}})

    def invoke(self, *, selected_object=None, fresh_records=None, collection=False,
               expected_artifact_id=7, expected_artifact_sha256="sha256:" + "d" * 64):
        if fresh_records is not None:
            value = selected.load_canonical_json_bytes(self.fresh.read_bytes())
            value["records"] = fresh_records
            write_canonical_json(self.fresh, value)

        @contextmanager
        def fresh(*args, **kwargs):
            yield self.fresh

        def capture(_plan, destination, **kwargs):
            self.assertEqual(self.digest, sha256_bytes(kwargs["metadata_receipt_path"].read_bytes()))
            destination.mkdir()
            (destination / "record").write_bytes(b"official metadata")

        def shard(path, instance):
            raw = (self.receipt_path.read_bytes() if instance.phase == "metadata"
                   else Path(self.validations[instance.target]["validationReceipt"]).read_bytes())
            return {"receipt": self.receipt if instance.phase == "metadata" else {"target": instance.target},
                    "receiptBytes": raw, "receiptSha256": sha256_bytes(raw),
                    "objectSha256": "sha256:" + "c" * 64}

        def write(_plan, destination, **kwargs):
            self.assertEqual(12, len(kwargs["records"]))
            self.assertEqual(self.outside, kwargs["evidence_root"])
            self.assertEqual(self.digest, kwargs["metadata_envelope"]["receiptSha256"])
            self.assertEqual(11, len(kwargs["validation_envelopes"]))
            write_canonical_json(destination, {"evidenceRoot": str(kwargs["evidence_root"]),
                                  "records": kwargs["records"], "policy": kwargs["policy"]})

        phase = {"state": "retained", "source": None, "transportSource": None,
                 "buildKey": self.key, "receiptSha256": self.digest,
                 "objectSha256": "sha256:" + "c" * 64}
        if selected_object is not None:
            phase.update(selected_object)
        state = SimpleNamespace(producer=self.producer,
            prior_by_instance={selected._METADATA: phase})
        with mock.patch.object(selected.product_reuse, "_product_materialization_paths",
                               return_value=(self.discovery, self.after, self.root / "unused")), \
             mock.patch.object(selected, "validate_phase_receipt", return_value=self.receipt), \
             mock.patch.object(selected, "_context", return_value={"repositoryRoot": "/original",
                                                                  "metadataRequest": "/original/request"}), \
             mock.patch.object(selected, "held_fresh_facade_metadata_policy", side_effect=fresh) as full_fresh, \
             mock.patch.object(selected, "held_captured_facade_metadata_policy", side_effect=fresh) as capture_only, \
             mock.patch.object(selected, "locate_original_facade_upload", return_value={
                 "artifact_id": 7, "artifact_sha256": "sha256:" + "d" * 64}) as locator, \
             mock.patch.object(selected, "capture_sdk_facade_metadata_upload", side_effect=capture) as captured, \
             mock.patch.object(selected, "verify_phase_shard", side_effect=shard), \
             mock.patch.object(selected, "write_facade_metadata_policy", side_effect=write) as writer, \
             mock.patch.object(selected, "FacadeMetadataAdmission", return_value=object()), \
             mock.patch.object(selected.product_reuse, "_validate_plan", return_value={}), \
             mock.patch.object(selected.product_reuse, "_consumer", return_value={"producer": self.producer}), \
             mock.patch.object(selected.product_reuse, "_verified_product_state", return_value=state) as verified:
            held = (selected.held_core_metadata_collection_policy if collection else
                    selected.held_same_campaign_core_metadata_policy)
            arguments = [self.root / "plan.json", self.discovery, self.before]
            if not collection:
                arguments.append(self.after)
            with held(*arguments,
                    self.receipt_path, expected_build_key=self.key,
                    expected_receipt_sha256=self.digest,
                    expected_artifact_id=expected_artifact_id,
                    expected_artifact_sha256=expected_artifact_sha256, replay_policy={},
                    original_context={}, trusted_workflow_sha="e" * 40,
                    repository_root=self.root, environ={}, token="token") as policy:
                self.assertTrue(policy.is_file())
                descriptor = selected.load_canonical_json_bytes(policy.read_bytes())
                self.assertEqual(12, len(descriptor["records"]))
                self.assertIn({"receiptSha256": self.digest, "captureRoot": "common"}, descriptor["records"])
                self.assertEqual(0 if collection else 1, full_fresh.call_count)
                self.assertEqual(1 if collection else 0, capture_only.call_count)
            return locator, captured, writer, verified

    def test_collection_uses_the_full_original_descriptor_before_state_exists(self):
        locator, captured, writer, verified = self.invoke(collection=True)
        locator.assert_called_once()
        captured.assert_called_once()
        writer.assert_not_called()  # The generic collector owns the mandatory full admission.
        verified.assert_not_called()  # Generic advance performs the new-state admission while held.

    def test_reviewed_retained_metadata_keeps_original_pins_and_full_admission(self):
        self.receipt["producer"] = {"commit": "f" * 40}
        write_canonical_json(self.receipt_path, self.receipt)
        self.digest = sha256_bytes(self.receipt_path.read_bytes())
        origin = {"producer": self.receipt["producer"], "artifact_id": 7,
            "artifact_sha256": "sha256:" + "d" * 64, "receipt_sha256": self.digest,
            "workflow_sha": "f" * 40,
            "context": {"repositoryRoot": "/original", "metadataRequest": "/original/request"}}
        with mock.patch.object(selected, "retained_core_origin", return_value=origin):
            for collection in (True, False):
                with self.subTest(collection=collection):
                    locator, capture, writer, verified = self.invoke(collection=collection)
                    self.assertEqual("f" * 40, locator.call_args.kwargs["trusted_workflow_sha"])
                    self.assertEqual("f" * 40, capture.call_args.kwargs["trusted_workflow_sha"])
                    self.assertEqual(0 if collection else 1, writer.call_count)
                    self.assertEqual(0 if collection else 1, verified.call_count)
                    (self.outside / "common/record").unlink()
                    (self.outside / "common").rmdir()
        for field in (None, "producer", "artifact_id", "artifact_sha256", "receipt_sha256", "context"):
            wrong = None if field is None else {**origin, field: None}
            with self.subTest(field=field), mock.patch.object(selected, "retained_core_origin", return_value=wrong), \
                    self.assertRaisesRegex(ValueError, "reviewed original"):
                self.invoke(collection=True)

    def test_post_collection_caller_cannot_omit_its_state(self):
        with self.assertRaisesRegex(ValueError, "requires its collected state"):
            with selected.held_same_campaign_core_metadata_policy(None, None, None, None, None):
                self.fail("Post-collection checks cannot be disabled")

    def test_binds_official_metadata_to_all_originals_and_current_state(self):
        locator, captured, writer, verified = self.invoke()
        locator.assert_called_once()
        captured.assert_called_once()
        writer.assert_called_once()
        verified.assert_called_once()
        self.assertIsNotNone(verified.call_args.kwargs["sdk_facade_metadata_admission"])

    def test_rejects_worker_upload_different_from_independent_success_pins(self):
        with self.assertRaisesRegex(ValueError, "successful worker pins"):
            self.invoke(expected_artifact_id=8)
        with self.assertRaisesRegex(ValueError, "successful worker pins"):
            self.invoke(expected_artifact_sha256="sha256:" + "f" * 64)

    def test_rejects_fresh_descriptor_as_reuse_authority_and_cross_pair(self):
        with self.assertRaisesRegex(ValueError, "cannot certify reuse"):
            self.invoke(fresh_records=[{"self": "certified"}])
        write_canonical_json(self.fresh, {"evidenceRoot": str(self.captures), "records": [],
            "policy": {"validations": self.validations, "toolingEvidence": "/tooling",
                       "toolingPublicKey": "/key", "javaExecutable": "/java",
                       "toolingTrustDomain": "release", "toolingKeyring": "/keyring",
                       "toolingKeysDirectory": "/keys"}})
        with self.assertRaisesRegex(ValueError, "differs from original upload"):
            self.invoke(selected_object={"objectSha256": "sha256:" + "f" * 64})

    def test_real_shards_and_concrete_admission_accept_twelve_capture_layout(self):
        from ci.tests.test_sdk_facade_metadata_admission import FacadeMetadataAdmissionTest
        fixture = FacadeMetadataAdmissionTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.records = [{"receiptSha256": fixture.envelope["receiptSha256"],
                            "captureRoot": fixture.f.retained.relative_to(fixture.root).as_posix()}]
        for envelope in fixture.predecessors:
            target = envelope["receipt"]["target"]
            capture = Path(fixture.policy["validations"][target]["captureRoot"])
            fixture.records.append({"receiptSha256": envelope["receiptSha256"],
                                    "captureRoot": capture.relative_to(fixture.root).as_posix()})
        fixture.records.sort(key=lambda row: row["receiptSha256"])
        self.assertEqual(12, len(fixture.records))
        fixture.make().verify_metadata(fixture.envelope, fixture.predecessors)
        self.assertEqual(["enter", "exit"], fixture.events)

    def test_helper_uses_real_shards_writer_and_concrete_admission(self):
        self.check_real_helper()

    def test_collection_descriptor_waits_for_the_concrete_full_admission(self):
        self.check_real_helper(collection=True)

    def test_collection_descriptor_does_not_bypass_full_reader_exit_failure(self):
        self.check_real_helper(collection=True, replay_failure=True)

    def check_real_helper(self, *, collection=False, replay_failure=False):
        from ci.tests.test_sdk_facade_metadata_admission import FacadeMetadataAdmissionTest
        fixture = FacadeMetadataAdmissionTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        outside = self.root / "held-originals"
        captures = outside / "evidence"
        captures.mkdir(parents=True)
        for target in SDK_FACADE_TARGETS:
            source = Path(fixture.policy["validations"][target]["captureRoot"])
            target_capture = captures / target
            snapshot_regular_tree(source, target_capture, allow_empty=True)
            fixture.policy["validations"][target]["captureRoot"] = str(target_capture)
        fresh = outside / "policy.json"
        fresh_policy = deepcopy(fixture.policy)
        del fresh_policy["originalContext"]
        write_canonical_json(fresh, {"evidenceRoot": str(captures),
                                     "records": [], "policy": fresh_policy})
        previous_metadata_capture = fixture.f.retained
        receipt_path = fixture.f.receipt_path
        receipt = fixture.envelope["receipt"]
        completed = SimpleNamespace(producer=receipt["producer"], prior_by_instance={
            selected._METADATA: {"state": "retained", "source": None, "transportSource": None,
                                 "buildKey": receipt["buildKey"],
                                 "receiptSha256": fixture.envelope["receiptSha256"],
                                 "objectSha256": fixture.envelope["objectSha256"]}})

        @contextmanager
        def held(*args, **kwargs):
            yield fresh

        def captured(_plan, destination, **kwargs):
            self.assertEqual(receipt_path.read_bytes(), kwargs["metadata_receipt_path"].read_bytes())
            snapshot_regular_tree(previous_metadata_capture, destination, allow_empty=True)
            fixture.f.retained = destination

        def git_value(_root, _operation, revision):
            return receipt["producer"]["tree" if revision == "HEAD^{tree}" else "commit"]

        @contextmanager
        def replay(**kwargs):
            self.assertEqual(receipt["producer"]["commit"], kwargs["policy_revision"])
            with fixture.replay(**{**kwargs, "policy_revision": "c" * 40}) as value:
                yield value
                if replay_failure:
                    raise ValueError("full reader exit rejected")

        writer = sys.modules[selected.write_facade_metadata_policy.__module__]
        original = sys.modules["sdk_facade_metadata_original"]
        with mock.patch.object(selected.product_reuse, "_product_materialization_paths",
                               return_value=(self.discovery, self.after, self.root / "unused")), \
             mock.patch.object(selected, "held_fresh_facade_metadata_policy", side_effect=held), \
             mock.patch.object(selected, "held_captured_facade_metadata_policy", side_effect=held), \
             mock.patch.object(selected, "locate_original_facade_upload", return_value={
                 "artifact_id": 123, "artifact_sha256": "sha256:" + "d" * 64}), \
             mock.patch.object(selected, "capture_sdk_facade_metadata_upload", side_effect=captured), \
             mock.patch.object(selected.product_reuse, "_verified_product_state", return_value=completed), \
             mock.patch.object(selected.product_reuse, "_git_value", side_effect=git_value), \
             mock.patch.object(writer, "_request_inventory",
                               side_effect=lambda path: {path: writer.sha256_file(path)}), \
             mock.patch.object(original, "verified_retained_sdk_facade_metadata",
                               side_effect=replay), \
             mock.patch.object(selected.product_reuse, "_validate_plan", return_value={
                 "remoteBuildAuthorized": True, "event": "pull_request",
                 "validationCommit": receipt["producer"]["commit"],
                 "validationTree": receipt["producer"]["tree"]}):
            hold = (selected.held_core_metadata_collection_policy if collection
                    else selected.held_same_campaign_core_metadata_policy)
            arguments = [Path(fresh_policy["plan"]), self.discovery, self.before]
            if not collection:
                arguments.append(self.after)
            with hold(*arguments, receipt_path, expected_build_key=receipt["buildKey"],
                    expected_receipt_sha256=fixture.envelope["receiptSha256"],
                    expected_artifact_id=123,
                    expected_artifact_sha256="sha256:" + "d" * 64,
                    replay_policy=fresh_policy, original_context=fixture.f.context,
                    trusted_workflow_sha="e" * 40, repository_root=fixture.root,
                    environ={}, token="explicit-caller-token") as descriptor:
                self.assertTrue(descriptor.is_file())
                if collection:
                    self.assertEqual([], fixture.events)
                    raw = selected.load_canonical_json_bytes(descriptor.read_bytes())
                    gate = selected.FacadeMetadataAdmission(Path(raw["evidenceRoot"]), raw["records"],
                        repository=fixture.root, policy_revision=receipt["producer"]["commit"], policy=raw["policy"])
                    if replay_failure:
                        with self.assertRaisesRegex(ValueError, "full reader exit rejected"):
                            gate.verify_metadata(fixture.envelope, fixture.predecessors)
                    else:
                        gate.verify_metadata(fixture.envelope, fixture.predecessors)
                self.assertEqual(["enter"] if replay_failure else ["enter", "exit"], fixture.events)


class CoreMetadataCollectionBridgeTest(unittest.TestCase):
    def test_bridge_binds_worker_pins_reuses_four_native_hosts_and_keeps_admission_held(self):
        from ci.tests.test_sdk_worker_collection import SdkWorkerCollectionTest
        from reuse_qualification import CompletedFrozenReuse
        f = SdkWorkerCollectionTest()
        f.setUp()
        self.addCleanup(f.doCleanups)
        _, ready, shard, verified, _ = f.shard('metadata', component='sdk-core', target='common')
        with tempfile.TemporaryDirectory() as outside:
            outside = Path(outside).resolve()
            tooling = outside / 'tooling.json'
            write_canonical_json(tooling, {'opaque': 'independent tooling seam'})
            caller = outside / 'caller.json'
            value = {'buildKey': ready['buildKey'], 'receiptSha256': verified['receiptSha256'],
                'artifactId': 7, 'artifactSha256': 'sha256:' + 'a' * 64,
                'originalContext': {'repositoryRoot': '/original', 'metadataRequest': '/original/request'},
                'sdkInputsArtifactId': 8, 'sdkInputsArtifactSha256': 'sha256:' + 'b' * 64,
                'toolingPolicy': str(tooling)}
            for case in ('valid', 'wrong-receipt', 'changed-caller', 'reader-failure',
                         'qualified', 'incomplete-native', 'qualified-changed-caller'):
                write_canonical_json(caller, {**value, **({'receiptSha256': 'sha256:' + 'c' * 64}
                                                        if case == 'wrong-receipt' else {})})
                events = []
                gate = object()
                qualified = case.startswith('qualified')
                cap = object.__new__(CompletedFrozenReuse) if qualified or case == 'incomplete-native' else None
                identities = [selected.PhaseInstanceId('sdk', 'sdk-core', 'package', 'common'),
                    *(selected.PhaseInstanceId('sdk', 'sdk-core', 'validation', t) for t in selected.SDK_FACADE_TARGETS)]
                def provision(plan, target, destination, **kwargs):
                    destination.write_bytes(b'pinned compiler fixture')
                    return destination
                def prepare(plan, discovery, state, requests, destination, **kwargs):
                    self.assertEqual(7, len(kwargs['native_compiler_archives']))
                    self.assertEqual(4, len(set(kwargs['native_compiler_archives'].values())))
                    self.assertEqual(value['buildKey'], kwargs['expected_build_key'])
                    write_canonical_json(destination, {'fixture': 'bootstrap'})
                @contextmanager
                def full(plan, discovery, state, receipt, **kwargs):
                    self.assertEqual(shard / 'phase-receipt.json', receipt)
                    self.assertEqual(value['artifactId'], kwargs['expected_artifact_id'])
                    self.assertEqual(value['artifactSha256'], kwargs['expected_artifact_sha256'])
                    self.assertEqual(value['originalContext'], kwargs['original_context'])
                    events.append('full-enter')
                    if case == 'reader-failure':
                        raise ValueError('original reader rejected')
                    try:
                        yield outside / 'full-policy.json'
                    finally:
                        events.append('full-exit')
                @contextmanager
                def admission(options):
                    self.assertEqual(outside / 'full-policy.json', options['sdk_facade_metadata_policy'])
                    events.append('admission-enter')
                    try:
                        yield {'sdk_facade_metadata_admission': gate}
                    finally:
                        events.append('admission-exit')
                with self.subTest(case=case), mock.patch.object(selected, 'provision', side_effect=provision) as native, \
                        mock.patch.object(selected, 'prepare', side_effect=prepare) as bootstrap, \
                        mock.patch.object(selected, 'held_core_metadata_collection_policy', side_effect=full), \
                        mock.patch.object(selected, 'metadata_admission_options', side_effect=admission), \
                        mock.patch.object(selected.product_reuse, '_verified_product_state',
                            return_value=SimpleNamespace(prior_by_instance={i: {} for i in identities})), \
                        mock.patch.object(CompletedFrozenReuse, 'envelope', return_value={} if qualified else None), \
                        mock.patch.object(selected.FacadeMetadataAdmission, 'from_completed_predecessors', return_value=gate) as fast:
                    def invoke():
                        with selected.held_collection_admission(caller, f.plan_path, f.discovery, f.discovery, shard,
                                trusted_workflow_sha='d' * 40, repository_root=f.repository, environ={}, token='fixture',
                                sdk_validation_tooling={'opaque': 'independent tooling seam'}, completed_frozen=cap) as actual:
                            self.assertIs(gate, actual)
                            events.append('advance')
                            if case in ('changed-caller', 'qualified-changed-caller'):
                                caller.write_bytes(caller.read_bytes() + b' ')
                    if case in ('valid', 'qualified', 'incomplete-native'):
                        invoke()
                        self.assertEqual(['advance'] if qualified else
                            ['full-enter', 'admission-enter', 'advance', 'admission-exit', 'full-exit'], events)
                    else:
                        with self.assertRaises(ValueError):
                            invoke()
                    if case == 'wrong-receipt':
                        native.assert_not_called()
                        bootstrap.assert_not_called()
                    else:
                        self.assertEqual(4, native.call_count)
                        bootstrap.assert_called_once()
                    self.assertEqual(int(qualified), fast.call_count)

    def test_generic_collection_holds_full_gate_and_keeps_failed_worker_fast_path(self):
        from ci import sdk_workflow as workflow
        import sdk_core_metadata_same_campaign as bridge
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            original = root / 'original'
            for name in ('product-resume-inputs', 'product-resume-state', 'runtime-state'):
                (original / name).mkdir(parents=True)
                (original / name / 'record').write_bytes(b'unchanged original')
            for failed in (False, True):
                events = []
                gate = object()
                row = {'product': 'sdk', 'component': 'sdk-core', 'phase': 'metadata', 'target': 'common',
                    'result': 'failure' if failed else 'success',
                    'shardDirectory': None if failed else 'rows/core-metadata/original/shard'}
                @contextmanager
                def full(*args, **kwargs):
                    events.append('enter')
                    try:
                        yield gate
                    finally:
                        events.append('exit')
                def advance(*args, **kwargs):
                    self.assertEqual((selected._METADATA,) if failed else (), kwargs['failed_instances'])
                    if failed:
                        self.assertNotIn('sdk_facade_metadata_admission', kwargs)
                        self.assertEqual([], events)
                    else:
                        self.assertIs(gate, kwargs['sdk_facade_metadata_admission'])
                        self.assertEqual(['enter'], events)
                    events.append('advance')
                    args[4].mkdir(parents=True)
                    return {'matrices': {'sdk': []}}
                with self.subTest(failed=failed), \
                        mock.patch.object(workflow.product_reuse, 'collect_runtime_workers', return_value={'rows': [row]}), \
                        mock.patch.object(workflow.product_reuse, 'advance_products', side_effect=advance), \
                        mock.patch.object(bridge, 'held_collection_admission', side_effect=full) as held:
                    workflow.collect(original, root / str(failed), root / ('output-' + str(failed)),
                        wave=14, family='core-metadata', trusted_workflow_sha='a' * 40,
                        repository_root=root, environ={}, token='fixture', core_metadata_caller=root / 'caller')
                self.assertEqual(['advance'] if failed else ['enter', 'advance', 'exit'], events)
                self.assertEqual(0 if failed else 1, held.call_count)
            with mock.patch.object(workflow.product_reuse, 'collect_runtime_workers') as collect, \
                    self.assertRaisesRegex(ValueError, 'exact family'):
                workflow.collect(original, root / 'wrong', root / 'wrong-output', wave=11,
                    family='core-binary', trusted_workflow_sha='a' * 40, repository_root=root,
                    environ={}, token='fixture', core_metadata_caller=root / 'caller')
            collect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
