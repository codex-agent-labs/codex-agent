"""Completed semantic reuse with synthetic native/Git observations, never hosted acceptance."""
import copy
from contextlib import ExitStack, contextmanager
import io
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import product_reuse
import reuse_qualification as qualification
from products import inventory, reuse, restore
from products.inventory import canonical_json_bytes, load_canonical_json_bytes, sha256_bytes
from products.receipt import compute_build_key, validate_phase_receipt
from products.plan import _phase_version_identity
from products.registry import PhaseInstanceId, phase_instance_dependencies
from ci.tests.test_products import phase_receipt


FIELDS = ("product", "component", "phase", "target")
POLICY = "sha256:" + "a" * 64


class CompletedFrozenReuseTest(unittest.TestCase):
    def sdk_fixture(self):
        """Small synthetic transport around the real receipt shape, not hosted evidence."""
        original = load_canonical_json_bytes((Path(__file__).parent / "data/sdk-ios-qualification.json").read_bytes())
        spec = load_canonical_json_bytes((Path(__file__).parent / "data/sdk-completed-resume.json").read_bytes())
        receipt = original["receipt"]
        body = b"synthetic completed SDK object"
        original["objectSha256"] = sha256_bytes(body)
        phase = {**spec["completedPhase"], "objectSha256": sha256_bytes(body), "state": "retained",
                 "source": None, "transportSource": None, "misses": []}
        spec["completedPhase"]["objectSha256"] = phase["objectSha256"]
        member = "product-resume-state/prior-failed-sdk/sdk-ios/binary/ios/original/shard/" + restore.object_relative_path(
            phase["buildKey"], phase["receiptSha256"])
        js = {**phase, "component": "javascript", "phase": "package", "target": "node"}
        request = copy.deepcopy(self.spec["request"])
        request["repositoryRevision"] = spec["producer"]["commit"]
        request["availableObjects"].extend({**{field: row[field] for field in (*FIELDS, *qualification._OBJECT_FIELDS)},
            "objectPath": member.removeprefix("product-resume-state/")} for row in (phase, js))
        authority = {**{field: receipt[field] for field in FIELDS}, **{field: receipt["inputs"][field]
            for field in ("toolchainProfileDigest", "flagsDigest", "outputSchemaVersion")}}
        request["phaseAuthorities"].append(authority)
        result = copy.deepcopy(self.spec["expectedResult"])
        result["phases"].extend((phase, js))
        controls = {row["relativePath"]: (request if row["relativePath"].endswith("reuse-wave-request.json") else
            result if row["relativePath"].endswith("reuse-wave-result.json") else receipt) for row in spec["controls"]}
        spec["controls"] = [{"relativePath": path, "bytes": len(canonical_json_bytes(value)),
                             "sha256": sha256_bytes(canonical_json_bytes(value))} for path, value in controls.items()]
        proof = {"schemaVersion": 1, "kind": "completed-sdk-reuse", "issuerCommit": "b" * 40,
            "specSha256": sha256_bytes(canonical_json_bytes(spec)), "controls": controls,
            "source": {"synthetic": "resume locator"}, "original": {"synthetic": "original locator"},
            "member": {"relativePath": member, "bytes": len(body), "sha256": sha256_bytes(body)}}
        proof['sdkInputs'] = {'locator': {'synthetic': 'SDK input job'}, 'files': sorted([
            {'relativePath': path, 'bytes': 1, 'sha256': sha256_bytes(b'x')} for path in (
                'sdk-inputs/fixture', 'runtime-capture/plan/impact-plan.json',
                'runtime-capture/capture-transport.json')], key=lambda row: row['relativePath'])}
        return {"spec": spec, "original": original, "proof": proof}, phase, authority, body

    def test_completed_sdk_proof_requires_native_origin_exact_controls_and_current_inputs(self):
        sdk, phase, authority, _ = self.sdk_fixture()
        pins = dict(artifactId=71, artifactSha256=POLICY, runId=72, runAttempt=1,
                    signerCommit="b" * 40, sourceCommit="a" * 40)
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            root = Path(temporary).resolve()
            native = stack.enter_context(patch.object(qualification, "_authenticate_native_subject"))
            stack.enter_context(patch.object(qualification, "_fetch_qualification_archive", side_effect=lambda *a, **kw:
                ({}, {"completion.json": canonical_json_bytes(sdk["proof"]), "bundle.jsonl": b"synthetic"})))
            stack.enter_context(patch.object(inventory, "git_regular_blob_bytes", side_effect=lambda root, commit, path, **kw:
                canonical_json_bytes(sdk["spec"] if path == qualification._SDK_COMPLETED_SPEC else sdk["original"])))
            trees = stack.enter_context(patch.object(inventory, "tree_entries", return_value=()))
            stack.enter_context(patch.object(product_reuse, "_authorities", return_value=([authority], None)))
            source = stack.enter_context(patch.object(qualification, "_observe_completed_sdk_resume",
                return_value=({}, [], sdk["proof"]["source"])))
            stack.enter_context(patch.object(qualification, "_observe_completed_sdk_original",
                return_value=({}, [], sdk["proof"]["original"])))
            stack.enter_context(patch.object(qualification, "_observe_completed_sdk_inputs",
                return_value=({}, [], sdk["proof"]["sdkInputs"]["locator"])))
            def fetch():
                return qualification._fetch_completed_sdk(root / "native", pins, root=root,
                    revision="d" * 40, frozen=self.spec, token="fixture")
            self.assertEqual(sdk, fetch())
            native.assert_called_once()
            native.side_effect = ValueError("native rejected")
            with self.assertRaisesRegex(ValueError, "native rejected"):
                fetch()
            native.side_effect = None
            for mutate in (lambda p: p.update(schemaVersion=True),
                           lambda p: p["member"].update(sha256=POLICY),
                           lambda p: p["member"].update(relativePath="another/object.zip"),
                           lambda p: p['sdkInputs']['files'][0].update(relativePath='runtime-capture/original/body.zip'),
                           lambda p: p["controls"]["product-resume-state/reuse-wave-result.json"].update(fullReuse=False)):
                saved = copy.deepcopy(sdk["proof"])
                mutate(sdk["proof"])
                with self.assertRaises(ValueError):
                    fetch()
                sdk["proof"] = saved
            source.return_value = ({}, [], {"synthetic": "different successful job"})
            with self.assertRaisesRegex(ValueError, "admission source changed"):
                fetch()
            source.return_value = ({}, [], sdk["proof"]["source"])
            trees.side_effect = [(('changed-owned-file', ('100644', 'old')),),
                                 (('changed-owned-file', ('100644', 'new')),)]
            with patch("products.selection.phase_inventory_paths", return_value=['changed-owned-file']), \
                    self.assertRaisesRegex(ValueError, "owning inputs changed"):
                fetch()

    def test_completed_sdk_controls_seed_without_body_and_verify_consumed_member(self):
        import sdk_ios_binary_recovery as recovery
        sdk, phase, authority, body = self.sdk_fixture()
        spec = copy.deepcopy(self.spec)
        spec["expectedResult"]["phases"].append(phase)
        spec["request"]["phaseAuthorities"].append(authority)
        cap = qualification.CompletedFrozenReuse(spec, [*self.receipts.values(), sdk["original"]["receipt"]],
            qualification._COMPLETED_FROZEN, revision="d" * 40, originals=self.qualified["originals"], sdk=sdk)
        self.assertIn(phase["objectSha256"], cap.deferred_objects())
        producer = {**sdk["spec"]["producer"], "runId": sdk["spec"]["producer"]["runId"] + 1}
        original_artifact = {"id": sdk["original"]["artifactId"], "digest": sdk["original"]["artifactSha256"]}
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, 'w') as archive:
            archive.writestr(sdk["proof"]["member"]["relativePath"], body)
        @contextmanager
        def ranges(*args):
            with zipfile.ZipFile(io.BytesIO(zipped.getvalue())) as archive:
                yield archive, None
        with tempfile.TemporaryDirectory() as temporary, \
                patch.object(qualification, "_observe_completed_sdk_resume", return_value=({}, [], sdk["proof"]["source"])), \
                patch.object(qualification, "_observe_completed_sdk_original", return_value=(original_artifact, [], sdk["proof"]["original"])), \
                patch("runtime_reference_archive.open_reference_archive", side_effect=ranges) as opened:
            root = Path(temporary).resolve()
            records = recovery.capture_completed_ios_binary(root / "prior", root, completed_frozen=cap,
                plan={}, producer=producer, token="fixture")
            self.assertEqual(1, len(records))
            self.assertFalse((root / records[0]["objectPath"]).exists())
            self.assertEqual(3, len(inventory.regular_file_inventory(root / 'prior')))
            opened.assert_not_called()
            cap.capture_object(records[0], root / "consumed.zip", plan={}, producer=producer,
                               trusted_workflow_sha="a" * 40, token="fixture")
            self.assertEqual(body, (root / "consumed.zip").read_bytes())
            opened.assert_called_once()
            with self.assertRaisesRegex(ValueError, "exact proved identity"):
                cap.envelope({**records[0], "objectSha256": POLICY})

    def test_completed_sdk_issuer_hashes_original_transport_and_object_before_claim(self):
        sdk, _, _, body = self.sdk_fixture()
        controls, member = sdk["proof"]["controls"], sdk["proof"]["member"]["relativePath"]
        def archive(payload):
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as output:
                for path, value in controls.items():
                    output.writestr(path, canonical_json_bytes(value))
                output.writestr(member, payload)
            return data.getvalue()
        valid = archive(body)
        sdk["spec"].update(artifactBytes=len(valid), artifactSha256=sha256_bytes(valid))
        sources = {qualification._SDK_COMPLETED_SPEC: canonical_json_bytes(sdk["spec"]),
            'ci/tests/data/sdk-ios-qualification.json': canonical_json_bytes(sdk["original"]),
            'ci/tests/data/hosted-frozen-reuse.json': canonical_json_bytes(self.spec)}
        artifact = dict(name='synthetic-resume', id=71)
        def download(*args, **kwargs):
            self.assertEqual(sdk["spec"]["artifactSha256"], args[1])
            self.assertEqual(len(valid), kwargs['max_bytes'])
            kwargs['destination'].write_bytes(valid)
            return artifact, kwargs['destination']
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            stack.enter_context(patch.dict('os.environ', {'QUALIFICATION_ISSUER_SHA': 'b' * 40,
                'QUALIFICATION_ISSUER_REPOSITORY': qualification.REPOSITORY,
                'QUALIFICATION_ISSUER_PATH': qualification.ISSUER_WORKFLOW}))
            stack.enter_context(patch.object(qualification.subprocess, 'check_output', return_value='b' * 40 + '\n'))
            stack.enter_context(patch.object(qualification, '_compatible_verifier', return_value=True))
            stack.enter_context(patch.object(inventory, 'git_regular_blob_bytes',
                side_effect=lambda root, commit, path, **kw: sources[path]))
            root = Path(qualification.__file__).resolve().parents[1]
            stack.enter_context(patch.object(qualification, 'read_regular_file_bytes',
                side_effect=lambda path, **kw: sources[path.relative_to(root).as_posix()]))
            stack.enter_context(patch.object(qualification, '_observe_completed_sdk_resume',
                return_value=(artifact, [{'run': {'head_sha': 'a' * 40}}], sdk['proof']['source'])))
            stack.enter_context(patch.object(qualification, '_observe_completed_sdk_original',
                return_value=({}, [], sdk['proof']['original'])))
            stack.enter_context(patch.object(qualification, '_issue_sdk_input_members',
                return_value=sdk['proof']['sdkInputs']))
            downloaded = stack.enter_context(patch.object(product_reuse, '_download_contract_ci_upload', side_effect=download))
            work = Path(temporary).resolve() / 'proof'
            report = qualification.issue_completed_sdk(work, 'fixture')
            self.assertEqual(0, report['productPhasesExecuted'])
            self.assertEqual(len(body), report['verifiedObjectBytes'])
            self.assertEqual(['completion.json'], sorted(p.name for p in work.iterdir()))
            downloaded.assert_called_once()
            valid = archive(b'x' * len(body))
            with self.assertRaisesRegex(ValueError, 'admitted object differs'):
                qualification.issue_completed_sdk(work.parent / 'rejected', 'fixture')
            self.assertFalse((work.parent / 'rejected/completion.json').exists())

    def test_completed_checkpoint_routes_without_rehydrating_aggregate_or_resigning(self):
        import runtime_workflow
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cap, _ = self.fetched(root)
            inspected = {'result': self.spec['expectedResult'], 'readyPlans': []}
            ordinary = runtime_workflow.continuation_from_inspection(inspected, root / 'ordinary')
            self.assertTrue(ordinary['nativeAttestationMatrix']['include'])
            fast = runtime_workflow.continuation_from_inspection(inspected, root / 'completed', completed_frozen=cap)
            self.assertEqual([], fast['nativeAttestationMatrix']['include'])
            self.assertEqual(ordinary['aggregate'], fast['aggregate'])
            with self.assertRaisesRegex(ValueError, 'concrete completed'):
                runtime_workflow.continuation_from_inspection(inspected, root / 'untrusted', completed_frozen=True)
            for row in inspected['result']['phases']:
                if row['component'] == 'runtime-aggregate':
                    row['receiptSha256'] = POLICY
            with self.assertRaisesRegex(ValueError, 'exact proved identity'):
                runtime_workflow.continuation_from_inspection(inspected, root / 'changed', completed_frozen=cap)

    def setUp(self):
        self.spec = load_canonical_json_bytes((Path(__file__).parent / "data/hosted-frozen-reuse.json").read_bytes())
        self.spec["request"]["repositoryRevision"] = "d" * 40
        self.receipts = {}
        self.objects = {}
        for row in self.spec["expectedResult"]["phases"]:
            receipt = phase_receipt()
            receipt.update({field: row[field] for field in FIELDS})
            instance = PhaseInstanceId(*(row[field] for field in FIELDS))
            receipt["inputs"]["versionIdentity"] = _phase_version_identity(instance, self.spec["request"]["versions"])
            receipt["productVersion"] = self.spec["request"]["versions"]["runtime-release" if instance.product == "runtime" else "contract"]
            receipt["buildKey"] = compute_build_key(**{field: receipt[field] for field in FIELDS}, inputs=receipt["inputs"])
            validate_phase_receipt(receipt)
            self.receipts[instance] = receipt
            self.objects[instance] = str(instance).encode()
            row.update(buildKey=receipt["buildKey"], receiptSha256=sha256_bytes(canonical_json_bytes(receipt)),
                       objectSha256=sha256_bytes(self.objects[instance]))
        rows = self.spec["expectedResult"]["phases"]
        for field in ("availableObjects", "phaseAuthorities"):
            for row in self.spec["request"][field]:
                receipt = self.receipts[PhaseInstanceId(*(row[name] for name in FIELDS))]
                if field == "availableObjects":
                    row.update(buildKey=receipt["buildKey"], receiptSha256=sha256_bytes(canonical_json_bytes(receipt)),
                        objectSha256=sha256_bytes(self.objects[PhaseInstanceId(*(row[name] for name in FIELDS))]))
                else:
                    row.update({name: receipt["inputs"][name] for name in
                                ("flagsDigest", "toolchainProfileDigest", "outputSchemaVersion")})
        self.qualified = {"verifierPolicySha256": POLICY, "originals": [
            {"receipt": self.receipts[PhaseInstanceId(*(row[name] for name in FIELDS))],
             "identity": {"locator": {**{field: row[field] for field in FIELDS},
                                      "artifact": {"id": 71, "digest": POLICY}}},
             "receiptSha256": row["receiptSha256"], "objectSha256": row["objectSha256"],
             "originalFiles": [{"relativePath": "shard/" + restore.object_relative_path(row["buildKey"], row["receiptSha256"]),
                "bytes": len(self.objects[PhaseInstanceId(*(row[name] for name in FIELDS))]),
                "sha256": row["objectSha256"]}]}
            for row in rows if row["product"] == "runtime"]}
        self.proof = {"resultSha256": sha256_bytes(canonical_json_bytes(self.spec["expectedResult"])),
            "verificationPolicySha256": POLICY, "frozenPhases": 50, "selectedProductPhases": 0,
            "changedFrozenInventories": 0, "checkpoint": self.spec["signedCheckpoint"],
            "freshOriginalPhases": [{field: row[field] for field in (*FIELDS, "receiptSha256")}
                                    for row in rows if row["product"] == "runtime"]}

    def fetched(self, root, *, proof=None, authentication_error=None):
        captured = {"qualification.json": b"synthetic native subject", "bundle.jsonl": b"synthetic native bundle",
                    "proof.json": canonical_json_bytes(self.proof if proof is None else proof)}
        with ExitStack() as stack:
            stack.enter_context(patch.object(qualification, "_compatible_verifier", return_value=True))
            stack.enter_context(patch.object(qualification, "_fetch_qualification_archive",
                return_value=({"downloadedQualificationBytes": sum(map(len, captured.values()))}, captured)))
            native = stack.enter_context(patch.object(qualification, "_authenticate_bytes",
                return_value=self.qualified, side_effect=authentication_error))
            stack.enter_context(patch.object(inventory, "git_regular_blob_bytes", return_value=canonical_json_bytes(self.spec)))
            stack.enter_context(patch.object(inventory, "tree_entries", return_value=()))
            stack.enter_context(patch.object(product_reuse, "_authorities",
                return_value=(self.spec["request"]["phaseAuthorities"], None)))
            stack.enter_context(patch.object(product_reuse, "_versions", return_value=self.spec["request"]["versions"]))
            result = qualification.fetch_completed_frozen(root / "capture", consumer_commit="c" * 40,
                verifier_policy_sha256=POLICY, repository_root=root, revision="d" * 40,
                signer_commit="b" * 40, source_commit="a" * 40, artifact_id=71,
                artifact_sha256="sha256:" + "e" * 64, run_id=72, run_attempt=1, token="fixture")
            self.assertEqual(POLICY, native.call_args.kwargs["policy_sha256"])
            self.assertNotIn("compatible", native.call_args.kwargs)
            return result

    def test_exact_fifty_phase_planner_uses_no_body_or_projection_verifier(self):
        with tempfile.TemporaryDirectory() as temporary:
            cap, report = self.fetched(Path(temporary).resolve())
            self.assertEqual(50, len(cap.check_request(self.spec["request"])))
            self.assertEqual(0, report["productBodiesDownloaded"])
            envelopes, values = [], {}
            for row in self.spec["expectedResult"]["phases"]:
                instance = PhaseInstanceId(*(row[field] for field in FIELDS))
                receipt = self.receipts[instance]
                envelopes.append(cap.envelope(row, canonical_json_bytes(receipt)))
                values[instance] = {"inventory": receipt["inputs"]["inventory"],
                    "versions": self.spec["request"]["versions"], "flags_digest": receipt["inputs"]["flagsDigest"],
                    "toolchain_profile_digest": receipt["inputs"]["toolchainProfileDigest"], "output_schema_version": 1}
            with patch.object(reuse, "_plan", side_effect=AssertionError("repeated semantic planning")), \
                    patch.object(reuse, "verify_object", side_effect=AssertionError("unrelated product body")), \
                    patch.object(reuse, "verify_contract_execution_projection", side_effect=AssertionError("repeated execution")):
                result, _ = reuse.advance_reuse(tuple(values), values, envelopes,
                    reuse.LookupSession(repository=qualification.REPOSITORY, pull_request=31), completed_frozen=cap)
            self.assertTrue(result["fullReuse"])
            self.assertEqual(self.spec["expectedResult"]["phases"], result["phases"])
            self.assertFalse(any(result["matrices"].values()))
            unknown = {"product": "sdk", "component": "javascript", "phase": "validation", "target": "node"}
            self.assertIsNone(cap.envelope(unknown))

    def test_native_failure_and_plain_cached_flags_cannot_create_capability(self):
        with self.assertRaises(TypeError):
            qualification.CompletedFrozenReuse(self.spec, [], True, revision="d" * 40)
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(ValueError, "native rejected"):
            self.fetched(Path(temporary).resolve(), authentication_error=ValueError("native rejected"))
        with self.assertRaisesRegex(ValueError, "concrete native"):
            reuse.advance_reuse((), {}, [], reuse.LookupSession(repository=qualification.REPOSITORY,
                pull_request=31), completed_frozen={"fullReuse": True})

    def test_full_request_decoder_reuses_runtime_with_no_runtime_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cap, _ = self.fetched(root)
            request = {**copy.deepcopy(self.spec["request"]), "repositoryRoot": str(root), "artifactRoot": str(root)}
            originals = {root / row["objectPath"]: row for row in request["availableObjects"]}
            def ordinary_contract(path, **kwargs):
                row = originals[path]
                self.assertEqual("contract", row["product"], "Completed Runtime body was opened")
                identity = PhaseInstanceId(*(row[field] for field in FIELDS))
                return cap.envelope(row, canonical_json_bytes(self.receipts[identity]))
            with patch.object(reuse, "phase_git_inventory", side_effect=lambda _root, _revision, instance:
                    self.receipts[instance]["inputs"]["inventory"]), \
                    patch.object(reuse, "verify_object", side_effect=ordinary_contract) as body, \
                    patch.object(reuse.LookupSession, "register_contract_stage"), \
                    patch.object(reuse, "_plan", side_effect=AssertionError("Repeated completed phase planning")):
                result = reuse.plan_reuse_wave(request, completed_frozen=cap)
            self.assertEqual(4, body.call_count)
            self.assertEqual(self.spec["expectedResult"], result)

    def test_changed_or_incomplete_semantic_proof_fails(self):
        cases = [("resultSha256", "sha256:" + "0" * 64), ("verificationPolicySha256", "sha256:" + "0" * 64),
                 ("selectedProductPhases", 1), ("changedFrozenInventories", 1), ("frozenPhases", 49),
                 ("checkpoint", []), ("freshOriginalPhases", []), ("selectedProductPhases", False)]
        for field, value in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary, self.assertRaises(ValueError):
                self.fetched(Path(temporary).resolve(), proof={**self.proof, field: value})

    def test_current_candidates_catalogs_and_receipts_are_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            cap, _ = self.fetched(Path(temporary).resolve())
            for field in ("buildKey", "receiptSha256", "objectSha256"):
                request = copy.deepcopy(self.spec["request"])
                request["availableObjects"][0][field] = "sha256:" + "0" * 64
                with self.subTest(field=field), self.assertRaises(ValueError):
                    cap.check_request(request)
            request = copy.deepcopy(self.spec["request"])
            request["availableObjects"].append(request["availableObjects"][0])
            with self.assertRaisesRegex(ValueError, "duplicate"):
                cap.check_request(request)
            request = copy.deepcopy(self.spec["request"])
            request["catalogs"]["stable"] = [{"new": "candidate"}]
            with self.assertRaisesRegex(ValueError, "catalogs"):
                cap.check_request(request)
            row = self.spec["expectedResult"]["phases"][0]
            with self.assertRaisesRegex(ValueError, "receipt bytes"):
                cap.envelope(row, b"changed receipt")

    def test_reference_carrier_preserves_controls_without_opening_completed_bodies(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cap, _ = self.fetched(root)
            phase = next(row for row in self.spec["expectedResult"]["phases"] if row["product"] == "runtime")
            instance = PhaseInstanceId(*(phase[field] for field in FIELDS))
            receipt = self.receipts[instance]
            producer = {**receipt["producer"], "repository": qualification.REPOSITORY, "pullRequest": 31,
                        "event": "pull_request", "workflowPath": ".github/workflows/ci.yml"}
            consumer = {"kind": "ci", "producer": producer}
            phase = {**phase, "state": "reused", "source": "phase-shard", "transportSource": {
                "kind": "phase-shard", "descriptorSha256": "sha256:" + "e" * 64, "producer": receipt["producer"]}}
            resolution = {"schemaVersion": 1, "result": "complete", "fullReuse": True,
                          "phases": [phase], "matrices": {"contract": [], "runtime": [], "sdk": []}}
            with patch.object(restore, "_verified_object_snapshot", side_effect=AssertionError("body read")), \
                    patch.object(restore, "verify_object", side_effect=AssertionError("body read")):
                captured = restore.write_carrier(root / "carrier", resolution, (instance,),
                    {instance: root / "original/object.zip"}, consumer, object_root=root, completed_frozen=cap)
                self.assertEqual(receipt, captured["objects"][0]["receipt"])
                self.assertFalse((root / "original/object.zip").exists())
                self.assertEqual("original/object.zip", captured["objects"][0]["originalObjectPath"])
                restored = restore.verify_carrier(root / "carrier", (instance,), consumer,
                    object_root=root, completed_frozen=cap)
                self.assertEqual(captured, restored)
            with self.assertRaises((ValueError, FileNotFoundError)):
                restore.verify_carrier(root / "carrier", (instance,), consumer, object_root=root)
            with self.assertRaisesRegex(ValueError, "original PR scope"):
                restore.verify_carrier(root / "carrier", (instance,), {"kind": "ci", "producer": {
                    **producer, "pullRequest": 32}}, object_root=root, completed_frozen=cap)

    def test_only_proved_reference_bodies_and_aliases_are_deferred(self):
        from runtime_reference_transport import selected_reference_paths
        with tempfile.TemporaryDirectory() as temporary:
            cap, _ = self.fetched(Path(temporary).resolve())
            digest = next(iter(cap.deferred_objects()))
            rows = [{"relativePath": path, "bytes": 100, "sha256": sha}
                    for path, sha in (("product-resume-state/original.zip", digest),
                                      ("product-resume-state/alias.zip", digest),
                                      ("product-resume-state/concrete.zip", digest),
                                      ("product-resume-state/phase-receipt.json", POLICY),
                                      ("product-resume-state/new-sdk.zip", POLICY))]
            value = {"inventory": rows, "references": [row for row in rows if "concrete" not in row["relativePath"]]}
            self.assertEqual({row["relativePath"] for row in rows[2:]},
                             selected_reference_paths(value, completed_frozen=cap))
            self.assertEqual({row["relativePath"] for row in rows}, selected_reference_paths(value))
            with self.assertRaisesRegex(ValueError, "native completed"):
                selected_reference_paths(value, completed_frozen={"complete": True})

    def test_deferred_shard_and_fresh_locator_require_exact_proved_controls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cap, _ = self.fetched(root)
            row = next(row for row in self.spec["expectedResult"]["phases"] if row["product"] == "runtime")
            instance = PhaseInstanceId(*(row[field] for field in FIELDS))
            receipt = self.receipts[instance]
            record = {"schemaVersion": 1, **{field: row[field] for field in (*FIELDS, "buildKey", "receiptSha256", "objectSha256")},
                      "objectPath": restore.object_relative_path(row["buildKey"], row["receiptSha256"])}
            shard = root / "shard"
            shard.mkdir()
            inventory.write_canonical_json(shard / restore.PHASE_SHARD_NAME, record)
            inventory.write_canonical_json(shard / restore.PHASE_RECEIPT_NAME, receipt)
            with patch.object(restore, "verify_object", side_effect=AssertionError("body read")):
                verified = restore.verify_phase_shard(shard, instance, completed_frozen=cap)
                self.assertEqual(receipt, verified["receipt"])
            locator = {**{field: row[field] for field in FIELDS}, "artifact": {"id": 71, "digest": POLICY}}
            cap.require_original_locator(locator, receipt)
            with self.assertRaisesRegex(ValueError, "Fresh original locator"):
                cap.require_original_locator({**locator, "different": True}, receipt)
            with self.assertRaises((ValueError, FileNotFoundError)):
                restore.verify_phase_shard(shard, instance)
            (shard / "unexpected").write_bytes(b"unproved")
            with self.assertRaisesRegex(ValueError, "unexpected controls"):
                restore.verify_phase_shard(shard, instance, completed_frozen=cap)

    def test_completed_validation_reports_are_not_rehydrated_for_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cap, _ = self.fetched(root)
            phases = {PhaseInstanceId(*(row[field] for field in FIELDS)): row
                      for row in self.spec["expectedResult"]["phases"]}
            sources = {instance: root / str(number) for number, instance in enumerate(phases)}
            with patch.object(product_reuse, "restore_object", side_effect=AssertionError("redundant report materialization")):
                self.assertEqual([], product_reuse._materialize_runtime_validation_handoffs(
                    tuple(phases), phases, sources, root / "reports", root, completed_frozen=cap))
            self.assertFalse((root / "reports").exists())

    def test_deferred_consumption_fetches_one_bound_member_after_fresh_original_checks(self):
        import hydrated_evidence
        import runtime_reference_archive
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cap, _ = self.fetched(root)
            row = next(row for row in self.spec["expectedResult"]["phases"] if row["product"] == "runtime")
            instance = PhaseInstanceId(*(row[name] for name in FIELDS))
            member = "shard/" + restore.object_relative_path(row["buildKey"], row["receiptSha256"])
            payload = self.objects[instance]
            reads = []

            @contextmanager
            def archive(_artifact, _token):
                raw = io.BytesIO()
                with zipfile.ZipFile(raw, "w") as output:
                    output.writestr(member, payload)
                    output.writestr("unused-large-input", b"unrelated")
                raw.seek(0)
                with zipfile.ZipFile(raw) as original:
                    open_member = original.open
                    def read(entry, *args, **kwargs):
                        reads.append(entry.filename)
                        return open_member(entry, *args, **kwargs)
                    original.open = read
                    yield original, None

            producer = {"repository": qualification.REPOSITORY, "pullRequest": 31, "event": "pull_request"}
            # Factory fixture uses small synthetic locators. Native metadata
            # observations are mocked; member CRC/SHA verification is real.
            expected_locator = {**{name: row[name] for name in FIELDS}, "artifact": {"id": 71, "digest": POLICY}}
            with patch.object(product_reuse, "_authenticate_runtime_original_reference_source",
                    return_value=({}, {}, [{"jobs": [{}]}], "a" * 40)) as authenticate, \
                    patch.object(product_reuse, "_matching_ci_jobs", return_value=[{}]), \
                    patch.object(product_reuse, "_runtime_original_locator", return_value=expected_locator) as locator, \
                    patch.object(hydrated_evidence, "copy", return_value=False), \
                    patch.object(runtime_reference_archive, "open_reference_archive", side_effect=archive):
                options = dict(plan={}, producer=producer, trusted_workflow_sha="a" * 40, token="fixture")
                cap.capture_object(row, root / "object.zip", **options)
                self.assertEqual(payload, (root / "object.zip").read_bytes())
                self.assertEqual([member], reads)
                authenticate.assert_called_once()
                locator.return_value = {"changed": True}
                with self.assertRaisesRegex(ValueError, "Fresh original locator"):
                    cap.capture_object(row, root / "wrong-original.zip", **options)
                self.assertEqual([member], reads)
                locator.return_value = expected_locator
                payload = b"x" * len(payload)
                with self.assertRaisesRegex(ValueError, "immutable digest"):
                    cap.capture_object(row, root / "tampered-object.zip", **options)

    def test_resume_seeds_exact_original_controls_without_download_or_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cap, _ = self.fetched(root)
            producer = {"repository": qualification.REPOSITORY, "pullRequest": 31, "event": "pull_request"}
            def locator(_artifact, _workflow, instance, _job):
                return {**{name: getattr(instance, name) for name in FIELDS},
                        "artifact": {"id": 71, "digest": POLICY}}
            with patch.object(product_reuse, "_authenticate_runtime_original_reference_source",
                    return_value=({"id": 71, "digest": POLICY}, {}, [{"jobs": [{}]}], "a" * 40)) as authenticate, \
                    patch.object(product_reuse, "_matching_ci_jobs", return_value=[{}]), \
                    patch.object(product_reuse, "_runtime_original_locator", side_effect=locator), \
                    patch.object(product_reuse, "_download_contract_ci_upload", side_effect=AssertionError("body download")), \
                    patch.object(product_reuse, "safe_extract", side_effect=AssertionError("body extraction")):
                rows = product_reuse._capture_completed_runtime_controls({}, producer, root / "prior", root,
                    completed_frozen=cap, trusted_workflow_sha="a" * 40, token="fixture")
            self.assertEqual(46, authenticate.call_count)
            self.assertEqual(46, len(rows))
            self.assertFalse(list((root / "prior").rglob("*.zip")))
            for row in rows:
                source = root / row["objectPath"]
                shard = source.parents[4]
                result = restore.verify_phase_shard(shard, PhaseInstanceId(*(row[name] for name in FIELDS)),
                    completed_frozen=cap)
                self.assertEqual(row["receiptSha256"], result["receiptSha256"])

    def test_cli_policy_is_explicit_pinned_and_unchanged_through_use(self):
        with patch.object(qualification, "fetch_completed_frozen", side_effect=AssertionError("ambient authority")):
            with qualification.completed_frozen_options({}) as options:
                self.assertEqual({}, options)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cap, _ = self.fetched(root)
            plan_path, policy_path = root / "plan.json", root / "policy.json"
            plan_path.write_bytes(b"current plan")
            policy = dict(schemaVersion=1, kind="completed-frozen-reuse", consumerCommit="c" * 40,
                verifierPolicySha256=POLICY, artifactId=71, artifactSha256="sha256:" + "e" * 64,
                runId=72, runAttempt=1, signerCommit="b" * 40, sourceCommit="a" * 40)
            inventory.write_canonical_json(policy_path, policy)
            values = dict(plan=plan_path, repository_root=root, completed_frozen_policy=policy_path)
            consumer = {"kind": "ci", "producer": {"repository": qualification.REPOSITORY,
                "pullRequest": 31, "event": "pull_request"}}
            with patch.object(product_reuse, "_validate_plan", return_value={"validationCommit": "d" * 40}), \
                    patch.object(product_reuse, "_consumer", return_value=consumer), \
                    patch.object(qualification, "fetch_completed_frozen", return_value=(cap, {})) as fetch:
                with qualification.completed_frozen_options(values) as options:
                    self.assertIs(cap, options["completed_frozen"])
                    self.assertNotIn("completed_frozen_policy", values)
                self.assertEqual("c" * 40, fetch.call_args.kwargs["consumer_commit"])
                self.assertEqual(POLICY, fetch.call_args.kwargs["verifier_policy_sha256"])
                self.assertEqual("d" * 40, fetch.call_args.kwargs["revision"])
                with self.assertRaisesRegex(ValueError, "changed during use"):
                    with qualification.completed_frozen_options({**values, "completed_frozen_policy": policy_path}):
                        policy_path.write_bytes(b"changed caller policy")

    def test_sdk_join_requires_exact_completed_receipts_and_signed_checkpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            arguments = {}
            for row, argument in zip(self.spec["signedCheckpoint"],
                    ("runtime_manifest", "runtime_attestation", "runtime_attestation_signature"), strict=True):
                path = root / Path(row["relativePath"]).name
                raw = b"signature verification is the independent SDK gate: " + path.name.encode()
                path.write_bytes(raw)
                row.update(bytes=len(raw), sha256=sha256_bytes(raw))
                arguments[argument] = path
            for product, component, target in (("contract", "contract", "common"),
                                               ("runtime", "runtime-aggregate", "aggregate")):
                path = root / (product + "-metadata.json")
                receipt = self.receipts[PhaseInstanceId(product, component, "metadata", target)]
                inventory.write_canonical_json(path, receipt)
                arguments[product + "_metadata_receipt"] = path
            cap, _ = self.fetched(root)
            self.assertEqual(47, len(cap.sdk_receipts(arguments)))
            arguments["runtime_manifest"].write_bytes(b"changed signed manifest")
            with self.assertRaisesRegex(ValueError, "completed semantic checkpoint"):
                cap.sdk_receipts(arguments)

    def test_continuation_carries_frozen_references_and_digest_checks_other_objects(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            cap, _ = self.fetched(root)
            runtime = next(row for row in self.spec["expectedResult"]["phases"] if row["product"] == "runtime")
            fresh = dict(product="sdk", component="javascript", phase="metadata", target="node",
                buildKey=POLICY, receiptSha256="sha256:" + "b" * 64, objectSha256=sha256_bytes(b"new object"))
            runtime_id, fresh_id = (product_reuse._identity(row) for row in (runtime, fresh))
            current = root / "new-object.zip"
            current.write_bytes(b"new object")
            sources = {runtime_id: root / "absent-runtime.zip", fresh_id: current}
            captured = product_reuse._stage_completed_objects([runtime, fresh], sources, root / "state", cap)
            self.assertFalse(captured[runtime_id].exists())
            self.assertEqual(b"new object", captured[fresh_id].read_bytes())
            self.assertEqual(b"new object", current.read_bytes())
            current.write_bytes(b"tampered object")
            with self.assertRaisesRegex(ValueError, "digest"):
                product_reuse._stage_completed_objects([runtime, fresh], sources, root / "rejected", cap)


if __name__ == "__main__":
    unittest.main()
