"""Phase 9.2/9.3 continuation: a new original stays reusable after source/publisher rotation.

Tiny synthetic fixtures only; no hosted acceptance or Apple semantic claim.
"""

from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from ci import sdk_ios_binary_recovery as recovery
from ci.tests import test_sdk_ios_package_upload as upload_fixture
import io
import zipfile
from products.inventory import regular_file_inventory, sha256_bytes
from ci.tests import test_sdk_ios_binary_recovery as recovery_fixture
import product_reuse
capture = upload_fixture.capture
from products.inventory import load_canonical_json_bytes
from products.registry import PhaseInstanceId
from products.selection import _inventory_owners, phase_inventory_paths


# Publisher that produced the new iOS package d1de146e in run 44833963449/1.
P_PUBLISHER = "6b9843249ac85b1c2746e18e324357686b761cd5"
# Any later, not-yet-known publisher after source rotation.
ROTATED = "c" * 40
P = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
V = (PhaseInstanceId("sdk", "sdk-ios", "validation", "ios-arm64"),
     PhaseInstanceId("sdk", "sdk-ios", "validation", "ios-simulator-arm64"))
M = PhaseInstanceId("sdk", "sdk-ios", "metadata", "ios")


def _reference(sha, *, ref="refs/heads/reuse-authority", path=None):
    return {"path": path or "codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@reuse-authority",
            "ref": ref, "sha": sha}


class PublisherRotationTest(unittest.TestCase):
    def test_new_package_publisher_is_admitted_after_rotation(self):
        # Same shape as the official run-attempt observation of 44833963449/1.
        run = {"referenced_workflows": [
            _reference(P_PUBLISHER, path="codex-agent-labs/codex-agent/.github/workflows/approved-reuse.yml@reuse-authority"),
            _reference(P_PUBLISHER),
            {"path": "codex-agent-labs/codex-agent/.github/workflows/runtime-toolchain-capture.yml@8477a946",
             "ref": "refs/pull/31/merge", "sha": "8477a94657c4b5e0bb9cf485962182e1e8b0a35f"},
        ]}
        self.assertEqual(P_PUBLISHER, product_reuse._runtime_prior_workflow_sha(run, ROTATED))
        self.assertEqual(P_PUBLISHER, product_reuse._runtime_prior_workflow_sha(run, P_PUBLISHER))

    def test_unreviewed_or_unprotected_publisher_is_still_rejected(self):
        for reference in (_reference("d" * 40), _reference(P_PUBLISHER, ref="refs/heads/untrusted"),
                          _reference(P_PUBLISHER, path="other/workflow@reuse-authority")):
            with self.subTest(reference=reference):
                self.assertIsNone(product_reuse._runtime_prior_workflow_sha(
                    {"referenced_workflows": [reference]}, ROTATED))


class RotatedPackageRecoveryTest(recovery_fixture.IosSuccessfulPackageRecoveryTest):
    """The next plan's exact-key P lookup (product_reuse.discover -> capture_prior_ios_binary)."""

    def capture(self, current=ROTATED):
        receipt = load_canonical_json_bytes(self.receipt_bytes)
        return recovery.capture_prior_ios_binary(self.plan_path, self.plan,
            {**self.producer, "runId": 72}, receipt["buildKey"], self.output, self.work,
            repository_root=self.root, environ={}, trusted_workflow_sha=current,
            token="synthetic-token", attempts=(self.run,), phase="package")

    def setUp(self):
        super().setUp()
        self.run["referenced_workflows"] = [_reference(P_PUBLISHER)]

    def test_failed_run_package_is_recovered_under_a_rotated_publisher(self):
        with self.gates():
            records = self.capture()
        self.assertEqual(1, len(records))
        self.assertEqual(("sdk", "sdk-ios", "package", "ios"),
                         tuple(records[0][key] for key in ("product", "component", "phase", "target")))
        saved = self.output / "sdk-ios/package/ios"
        # The original receipt/producer is preserved byte for byte; nothing is reissued.
        self.assertEqual(self.receipt_bytes, (saved / "original/shard/phase-receipt.json").read_bytes())
        transport = load_canonical_json_bytes((saved / "capture-transport.json").read_bytes())
        self.assertEqual(self.producer, transport["captureProducer"])

    def test_unreviewed_package_publisher_is_skipped_before_download(self):
        self.run["referenced_workflows"] = [_reference("d" * 40)]
        with self.gates(), patch.object(recovery, "_capture_ios_original") as capture:
            self.assertEqual([], self.capture())
        capture.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_expired_package_upload_is_not_selected(self):
        self.artifact["expired"] = True
        with self.gates(), patch.object(recovery, "_capture_ios_original") as capture:
            self.assertEqual([], self.capture())
        capture.assert_not_called()

    def test_forged_package_digest_is_rejected(self):
        original = deepcopy(self.artifact)
        self.artifact["digest"] = "sha256:" + "0" * 64
        with self.gates(), self.assertRaises(ValueError):
            self.capture()
        self.artifact = original
        self.assertFalse((self.output / "sdk-ios/package/ios").exists())


class RotationKeepsPackageInputsTest(unittest.TestCase):
    # Files the Phase 9 V/reuse fixes are expected to touch.
    CHANGED = ("ci/sdk_ios_original_package.py", "ci/products/sdk_apple_content.py",
               "ci/product_reuse.py", "ci/hydrated_evidence.py", "ci/completed_sdk_reuse.py",
               "ci/reuse_qualification.py", "ci/sdk_ios_validation_workflow.py",
               "ci/products/sdk_apple_package_admission.py", "ci/sdk_apple_original_package_selection.py",
               ".github/actions/hydrated-evidence-cache/action.yml",
               ".github/actions/restore-reuse-qualification/action.yml")

    def test_v_and_reuse_control_changes_do_not_enter_p_v_or_m_keys(self):
        for path in self.CHANGED:
            with self.subTest(path=path):
                self.assertEqual(frozenset(), _inventory_owners(path))
        for instance in (P, *V, M):
            with self.subTest(instance=instance):
                self.assertEqual((), phase_inventory_paths(self.CHANGED, instance))

    def test_a_product_content_change_still_enters_the_key(self):
        # Negative control: the same check detects a genuine content input.
        owners = _inventory_owners("ci/products/sdk_apple_validation_content.py")
        self.assertTrue(owners)
        self.assertTrue(set(owners) & set(V))


class PlanPackageProjectionTest(upload_fixture.SdkIosPackageUploadTest):
    """Plan/product-resume P capture: full outer SHA + member CRCs, only shard/ stored."""

    def projection(self, **changes):
        return self.call(compact_recovery=True, **changes)

    def test_projection_hashes_whole_upload_but_stores_only_the_shard(self):
        seen = []
        original = capture._prepare_cold_apple_workspace
        with patch.object(capture, "_reuse_contract_ci_upload", side_effect=AssertionError("whole download")), \
                patch.object(capture, "safe_extract", side_effect=AssertionError("full extraction")), \
                patch.object(capture, "_prepare_cold_apple_workspace",
                             side_effect=lambda *args: (seen.append(args[2]), original(*args))[1]):
            transport = self.projection()
        names = {row["relativePath"] for row in regular_file_inventory(self.output)}
        self.assertEqual({"capture-transport.json",
                          *("original/" + name for name in self.files if name.startswith("shard/"))}, names)
        self.assertEqual(self.receipt_bytes, (self.output / "original/shard/phase-receipt.json").read_bytes())
        self.assertEqual(self.producer, transport["captureProducer"])
        self.assertEqual(self.artifact["digest"], transport["artifact"]["digest"])
        # Capacity is sized from the shard spans, never the whole upload.
        self.assertEqual(1, len(seen))
        self.assertLess(seen[0], len(self.raw))
        # Every body byte was read (and hashed) exactly once, plus the directory read.
        self.assertGreaterEqual(self.range_bytes, len(self.raw))
        self.assertFalse(any(path.name == "projected-transport.zip" for path in self.work.rglob("*")))

    def test_corrupt_unselected_member_is_rejected_from_the_stream(self):
        member = "worker/stderr.bin"
        with zipfile.ZipFile(io.BytesIO(self.raw)) as archive:
            entry = archive.getinfo(member)
        raw = bytearray(self.raw)
        offset = entry.header_offset
        data = offset + 30 + int.from_bytes(raw[offset + 26:offset + 28], "little") + \
            int.from_bytes(raw[offset + 28:offset + 30], "little")
        raw[data] ^= 1
        self.raw = bytes(raw)
        self.artifact["digest"] = sha256_bytes(self.raw)
        with self.assertRaisesRegex(ValueError, "CRC or size"), \
                patch.object(capture, "clone_publish_regular_tree") as publish:
            self.projection()
        publish.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_forged_whole_digest_is_rejected(self):
        self.artifact["digest"] = "sha256:" + "0" * 64
        with self.assertRaises(ValueError), patch.object(capture, "clone_publish_regular_tree") as publish:
            self.projection()
        publish.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_body_replaced_after_directory_read_is_rejected(self):
        stream = capture._stream_upload_projection

        def replaced(*args, **kwargs):
            self.range_etag = '"replaced"'
            return stream(*args, **kwargs)

        with patch.object(capture, "_stream_upload_projection", side_effect=replaced), \
                self.assertRaisesRegex(ValueError, "range identity"):
            self.projection()
        self.assertFalse(self.output.exists())

    def test_insufficient_shard_capacity_stops_before_the_body(self):
        with patch.object(capture, "_prepare_cold_apple_workspace", side_effect=ValueError("capacity")), \
                patch.object(capture, "_stream_upload_projection") as body, \
                self.assertRaisesRegex(ValueError, "capacity"):
            self.projection()
        body.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_hosted_projection_runs_the_shard_sized_preflight(self):
        import runtime_reference_transport
        with patch.object(runtime_reference_transport, "apple_capture_preflight") as preflight:
            self.projection(environ={"GITHUB_RUN_ID": "unrelated-current-run", "GITHUB_ACTIONS": "true"})
        self.assertEqual("package-projection", preflight.call_args.kwargs["phase"])
        self.assertLess(preflight.call_args.args[2], len(self.raw))

    def test_full_worker_capture_still_downloads_and_preflights_the_whole_upload(self):
        import runtime_reference_transport
        with patch.object(runtime_reference_transport, "apple_capture_preflight") as preflight, \
                patch.object(capture, "_stream_upload_projection", side_effect=AssertionError("projection")):
            self.call(environ={"GITHUB_RUN_ID": "unrelated-current-run", "GITHUB_ACTIONS": "true"})
        self.assertEqual((len(self.raw),), preflight.call_args.args[2:])
        self.assertEqual("package", preflight.call_args.kwargs["phase"])
        self.assertEqual(self.raw, (self.output / "transport.zip").read_bytes())


class StreamedZipMembersTest(unittest.TestCase):
    def archive(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("shard/a", b"stored" * 100)
            archive.writestr("deflated/b", b"compressible " * 5000, compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr("empty", b"")
        raw = output.getvalue()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            return raw, archive.infolist(), archive.start_dir

    def feed(self, raw, entries, start_dir, step):
        members = capture._StreamedZipMembers(entries, start_dir, len(raw))
        for begin in range(0, len(raw), step):
            members.feed(begin, raw[begin:begin + step])
        members.close()

    def test_any_chunking_verifies_stored_deflated_and_empty_members(self):
        raw, entries, start_dir = self.archive()
        for step in (1, 3, 7, 64, 4096, len(raw)):
            with self.subTest(step=step):
                self.feed(raw, entries, start_dir, step)

    def test_any_changed_member_byte_is_rejected(self):
        raw, entries, start_dir = self.archive()
        for entry in entries[:2]:
            changed = bytearray(raw)
            offset = entry.header_offset
            data = offset + 30 + int.from_bytes(raw[offset + 26:offset + 28], "little") + \
                int.from_bytes(raw[offset + 28:offset + 30], "little")
            changed[data + 1] ^= 1
            with self.subTest(member=entry.filename), self.assertRaises((ValueError, __import__("zlib").error)):
                self.feed(bytes(changed), entries, start_dir, 5)

    def test_truncated_stream_is_rejected(self):
        raw, entries, start_dir = self.archive()
        members = capture._StreamedZipMembers(entries, start_dir, len(raw))
        members.feed(0, raw[:entries[1].header_offset + 40])
        with self.assertRaises(ValueError):
            members.close()


class HoldOnceAdmissionTest(unittest.TestCase):
    """ApplePackageAdmission.verify under consumer custody: one complete gate, held open."""

    def setUp(self):
        import products.sdk_apple_package_admission as admission
        import products.reuse as reuse
        import sdk_ios_original_package as original
        self.admission, self.reuse, self.original = admission, reuse, original
        temporary = __import__("tempfile").TemporaryDirectory(prefix="hold-once-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        for name in ("keys.json", "public", "java"):
            (root / name).write_bytes(name.encode())
        for name in ("keys", "tooling"):
            (root / name).mkdir()
            (root / name / "member").write_bytes(name.encode())
        self.policy = dict(repository_root=root, keyring=root / "keys.json", keys_directory=root / "keys",
            tooling_evidence=root / "tooling", tooling_public_key=root / "public", java_executable=root / "java",
            policy_revision="c" * 40, required_trust_domain="release", tooling_keyring=None,
            tooling_keys_directory=None)
        self.root = root
        self.raw = b"original receipt"
        self.selected = {"receiptBytes": self.raw, "receipt": {},
                         "receiptSha256": sha256_bytes(self.raw), "objectSha256": "sha256:" + "2" * 64}
        self.events, self.calls = [], []
        shard = root / "original/shard"
        shard.mkdir(parents=True)
        self.value = {"original": root / "original", "receiptBytes": self.raw, "receipt": {}}

    def subject(self):
        value = object.__new__(self.admission.ApplePackageAdmission)
        value._original = (Path("plan"), Path("receipt"), self.selected["receiptSha256"], {
            "artifact_id": 17, "artifact_sha256": "sha256:" + "2" * 64, "ephemeral_capture": True,
            "expected_plan_revision": "a" * 40})
        value._policy = self.policy
        return value

    @contextmanager
    def gate(self, plan, receipt, **arguments):
        self.calls.append(arguments["ephemeral_capture"])
        self.events.append("enter")
        yield self.value
        self.events.append("exit")

    def patches(self):
        shard = {"receiptBytes": self.raw, "receiptSha256": self.selected["receiptSha256"],
                 "objectSha256": self.selected["objectSha256"]}
        stack = __import__("contextlib").ExitStack()
        stack.enter_context(patch.object(self.reuse, "_validate_envelope",
                                         return_value=(self.admission._INSTANCE, self.selected)))
        stack.enter_context(patch.object(self.original, "verified_original_ios_package", self.gate))
        stack.enter_context(patch.object(self.admission, "verify_phase_shard", return_value=shard))
        stack.enter_context(patch.object(self.admission, "canonical_json_bytes",
            side_effect=lambda value: self.raw if value == {} else __import__("json").dumps(value).encode()))
        return stack

    def policy_identity(self, **changes):
        return self.admission.package_policy_identity(**{**{name: self.policy[name] for name in (
            "keyring", "keys_directory", "tooling_evidence", "tooling_public_key", "java_executable",
            "policy_revision", "required_trust_domain", "tooling_keyring", "tooling_keys_directory",
            "repository_root")}, **changes})

    def test_without_custody_each_admission_runs_its_ephemeral_gate(self):
        with self.patches():
            self.subject().verify(self.selected)
            self.subject().verify(self.selected)
        self.assertEqual([True, True], self.calls)
        self.assertEqual(["enter", "exit", "enter", "exit"], self.events)

    def test_custody_runs_one_complete_gate_and_holds_it_until_scope_exit(self):
        with self.patches():
            with self.admission.holding_original_packages() as hold:
                self.subject().verify(self.selected)
                self.subject().verify(self.selected)
                self.assertEqual(["enter"], self.events)
                reused = self.admission.held_original_package(hold, self.raw, artifact_id=17,
                    artifact_sha256="sha256:" + "2" * 64, policy=self.policy_identity)
                self.assertIs(self.value, reused)
            self.assertEqual(["enter", "exit"], self.events)
        self.assertEqual([False], self.calls)
        self.assertIsNone(self.admission.active_package_hold())

    def test_consumer_reuse_requires_exact_upload_policy_and_receipt(self):
        with self.patches(), self.admission.holding_original_packages() as hold:
            self.subject().verify(self.selected)
            for changes in ({"artifact_id": 18}, {"artifact_sha256": "sha256:" + "9" * 64}):
                arguments = {"artifact_id": 17, "artifact_sha256": "sha256:" + "2" * 64, **changes}
                self.assertIsNone(self.admission.held_original_package(hold, self.raw,
                    policy=self.policy_identity, **arguments))
            self.assertIsNone(self.admission.held_original_package(hold, self.raw, artifact_id=17,
                artifact_sha256="sha256:" + "2" * 64, policy=lambda: self.policy_identity(policy_revision="d" * 40)))
            (self.root / "keys/member").write_bytes(b"rotated key")
            self.assertIsNone(self.admission.held_original_package(hold, self.raw, artifact_id=17,
                artifact_sha256="sha256:" + "2" * 64, policy=self.policy_identity))
            self.assertIsNone(self.admission.held_original_package(hold, b"other receipt", artifact_id=17,
                artifact_sha256="sha256:" + "2" * 64, policy=self.policy_identity))

    def test_conflicting_second_admission_is_rejected(self):
        with self.patches(), self.admission.holding_original_packages():
            self.subject().verify(self.selected)
            other = self.subject()
            other._original = (*other._original[:3], {**other._original[3], "artifact_id": 99})
            with self.assertRaisesRegex(ValueError, "different upload or policy"):
                other.verify(self.selected)

    def test_failed_gate_is_never_held(self):
        @contextmanager
        def failing(plan, receipt, **arguments):
            raise ValueError("full gate failed")
            yield

        with self.patches(), patch.object(self.original, "verified_original_ios_package", failing), \
                self.admission.holding_original_packages() as hold:
            with self.assertRaisesRegex(ValueError, "full gate failed"):
                self.subject().verify(self.selected)
            self.assertEqual({}, hold["held"])

    def test_custody_cannot_nest(self):
        with self.admission.holding_original_packages(), self.assertRaises(ValueError):
            with self.admission.holding_original_packages():
                pass


from ci.tests import test_sdk_ios_validation_workflow as workflow_fixture


class HoldOnceWorkflowTest(unittest.TestCase):
    """Execution uses the state admission's held gate; exits still precede finalization."""
    setUp = workflow_fixture.SdkIosValidationWorkflowTest.setUp
    capture = workflow_fixture.SdkIosValidationWorkflowTest.capture
    originals = workflow_fixture.SdkIosValidationWorkflowTest.originals
    original_binary = workflow_fixture.SdkIosValidationWorkflowTest.original_binary
    replay = workflow_fixture.SdkIosValidationWorkflowTest.replay
    worker = workflow_fixture.SdkIosValidationWorkflowTest.worker
    checkout = workflow_fixture.SdkIosValidationWorkflowTest.checkout
    finalize = workflow_fixture.SdkIosValidationWorkflowTest.finalize
    execute = workflow_fixture.SdkIosValidationWorkflowTest.execute

    def materialize_policy(self):
        (self.root / "keys.json").write_bytes(b"keyring")
        (self.root / "keys").mkdir(exist_ok=True)
        (self.root / "keys/key.pub").write_bytes(b"key")
        (self.root / "tooling").mkdir(exist_ok=True)
        (self.root / "tooling/evidence").write_bytes(b"tooling")
        (self.root / "public").write_bytes(b"public")
        (self.root / "java").write_bytes(b"java")

    def held_state(self, artifact_id):
        def verified_state(*args, **options):
            import products.sdk_apple_package_admission as admission
            hold = admission.active_package_hold()
            self.assertIsNotNone(hold)
            receipt = self.root / "admission-receipt.json"
            receipt.write_bytes(b"original receipt")
            value = hold["stack"].enter_context(self.real_originals(self.plan, receipt, artifact_id=17))
            a = self.arguments
            policy = admission.package_policy_identity(keyring=a["keyring"], keys_directory=a["keys_directory"],
                tooling_evidence=a["tooling_evidence"], tooling_public_key=a["tooling_public_key"],
                java_executable=a["java_executable"], policy_revision=a["policy_revision"],
                required_trust_domain=a["required_trust_domain"], repository_root=self.root)
            hold["held"][sha256_bytes(b"original receipt")] = (
                (b"original receipt", artifact_id, a["package_artifact_sha256"], policy), value)
            return self.verified
        return verified_state

    def run_with(self, artifact_id):
        import products.sdk_apple_package_admission as admission
        self.materialize_policy()
        calls = []
        self.real_originals = real = self.originals

        def counted(plan, receipt, **arguments):
            calls.append(arguments)
            return real(plan, receipt, **arguments)

        self.originals = counted
        # The fixture's execute() patches _verified_product_state with this hook.
        self.verified_state = self.held_state(artifact_id)
        shard = {"receiptBytes": b"original receipt"}
        with patch.object(admission, "verify_phase_shard", return_value=shard), \
                patch.object(admission, "canonical_json_bytes",
                    side_effect=lambda value: b"original receipt" if value is self.receipt
                    else workflow_fixture.workflow.canonical_json_bytes(value)):
            result = self.execute()
        return result, calls

    def test_execution_reuses_the_held_gate_and_exits_before_finalization(self):
        result, calls = self.run_with(17)
        self.assertEqual([], calls)
        self.assertEqual({"fixture": "finalized"}, result["shard"])
        self.assertEqual(1, self.events.count("original-enter"))
        self.assertLess(self.events.index("original-exit"), self.events.index("finalize"))
        self.assertEqual(["original-exit", "checkout", "finalize"], self.events[-3:])

    def test_mismatched_hold_falls_back_to_the_full_original_gate(self):
        result, calls = self.run_with(99)
        self.assertEqual(1, len(calls))
        self.assertEqual(2, self.events.count("original-enter"))
        self.assertEqual({"fixture": "finalized"}, result["shard"])
        self.assertLess(max(i for i, e in enumerate(self.events) if e == "original-exit"),
                        self.events.index("finalize"))


class HoldKeepsSelectorScratchTest(unittest.TestCase):
    """Under custody the caller's original selector scratch outlives the reuse wave."""

    def run_wave(self, holding):
        import products.sdk_apple_package_admission as admission
        import sdk_apple_original_package_selection as selection
        events = []
        temporary = __import__("tempfile").TemporaryDirectory(prefix="selector-scratch-")
        self.addCleanup(temporary.cleanup)
        plan = Path(temporary.name).resolve() / "plan.json"
        plan.write_bytes(b"{}")

        @contextmanager
        def selector(*args, **kwargs):
            events.append("selector-enter")
            yield "factory"
            events.append("selector-exit")

        request = {"requested": [{"product": "sdk", "component": "sdk-ios", "phase": "validation",
                                  "target": "ios-arm64"}]}
        origin = {"plan_path": plan, "repository_root": Path(temporary.name), "trusted_workflow_sha": "a" * 40,
                  "environ": {}, "token": "token"}
        with patch.object(selection, "caller_original_apple_package_selector", selector), \
                patch.object(product_reuse, "_javascript_projection_provider", return_value=None), \
                patch.object(product_reuse, "_javascript_index_projection_provider", return_value=None), \
                patch.object(product_reuse, "plan_reuse_wave",
                             side_effect=lambda invocation, **kwargs: events.append(
                                 ("wave", kwargs.get("sdk_apple_package_admission_factory"))) or {"ok": True}):
            if holding:
                with admission.holding_original_packages():
                    product_reuse._plan_with_sdk_tooling(request, None, apple_policy={"plan": str(plan)},
                                                         apple_package_origin=origin)
                    events.append("wave-returned")
            else:
                product_reuse._plan_with_sdk_tooling(request, None, apple_policy={"plan": str(plan)},
                                                     apple_package_origin=origin)
                events.append("wave-returned")
        return events

    def test_without_custody_scratch_ends_with_the_wave(self):
        self.assertEqual(["selector-enter", ("wave", "factory"), "selector-exit", "wave-returned"],
                         self.run_wave(False))

    def test_custody_keeps_scratch_until_the_consumer_scope_exits(self):
        self.assertEqual(["selector-enter", ("wave", "factory"), "wave-returned", "selector-exit"],
                         self.run_wave(True))


class PackageReferenceRetentionTest(unittest.TestCase):
    """V keeps P by authenticated reference; P payload/extraction is never re-uploaded."""
    setUp = workflow_fixture.SdkIosValidationWorkflowTest.setUp
    capture = workflow_fixture.SdkIosValidationWorkflowTest.capture
    originals = workflow_fixture.SdkIosValidationWorkflowTest.originals
    original_binary = workflow_fixture.SdkIosValidationWorkflowTest.original_binary
    replay = workflow_fixture.SdkIosValidationWorkflowTest.replay
    worker = workflow_fixture.SdkIosValidationWorkflowTest.worker
    checkout = workflow_fixture.SdkIosValidationWorkflowTest.checkout
    finalize = workflow_fixture.SdkIosValidationWorkflowTest.finalize
    execute = workflow_fixture.SdkIosValidationWorkflowTest.execute
    verified_state = workflow_fixture.SdkIosValidationWorkflowTest.verified_state

    def test_v_retains_only_reference_members_and_bound_reference(self):
        workflow = workflow_fixture.workflow
        self.execute()
        retained = self.destination / "originals/package"
        names = {row["relativePath"] for row in workflow.regular_file_inventory(retained)}
        self.assertEqual({*workflow.PACKAGE_REFERENCE_MEMBERS, workflow.PACKAGE_REFERENCE_NAME}, names)
        for payload in ("transport.zip", "original/value.bin", "original/shard/v1/payload.zip"):
            self.assertFalse((retained / payload).exists())
        reference = json.loads((retained / workflow.PACKAGE_REFERENCE_NAME).read_bytes())
        self.assertEqual({"schemaVersion": 1,
                          "packageArtifact": {"artifactId": 17, "artifactSha256": "sha256:" + "2" * 64},
                          "packageReceiptSha256": sha256_bytes(b"original receipt"),
                          "packageBuildKey": "sha256:" + "6" * 64,
                          "packageProducer": self.package_producer}, reference)
        context = json.loads((self.destination / "context/execution-context.json").read_bytes())
        self.assertEqual(reference["packageArtifact"], context["packageArtifact"])
        # The SDK, binary and native captures are still retained byte for byte.
        for name in ("sdk", "binary", "native"):
            self.assertEqual(self.source_inventories[name], workflow.regular_file_inventory(
                self.destination / "originals" / name, allow_empty=True))

    def test_reference_not_bound_to_the_verified_capture_is_rejected(self):
        workflow = workflow_fixture.workflow
        transport = self.captures["package"] / "capture-transport.json"
        good = transport.read_bytes()
        for change in ({"artifact": {"id": 17, "digest": "sha256:" + "9" * 64}},
                       {"artifact": {"id": 99, "digest": "sha256:" + "2" * 64}},
                       {"packageReceiptSha256": "sha256:" + "8" * 64},
                       {"captureProducer": {"runId": 1}}):
            with self.subTest(change=change):
                value = json.loads(good)
                value.update(change)
                transport.write_bytes(workflow.canonical_json_bytes(value))
                if self.destination.exists():
                    __import__("shutil").rmtree(self.destination)
                self.events = []
                with self.assertRaisesRegex(ValueError, "package reference differs"):
                    self.execute()
                self.assertNotIn("finalize", self.events)
        transport.write_bytes(good)

    def test_mutated_retained_reference_fails_before_finalization(self):
        workflow = workflow_fixture.workflow
        original_finalize = self.finalize

        def finalize(**arguments):
            raise AssertionError("finalized")

        @contextmanager
        def mutate(plan, receipt, **arguments):
            with workflow_fixture.SdkIosValidationWorkflowTest.originals(self, plan, receipt, **arguments) as value:
                yield value
                (self.destination / "originals/package" / workflow.PACKAGE_REFERENCE_NAME).write_bytes(b"{}")

        self.originals = mutate
        self.finalize = finalize
        with self.assertRaises(ValueError):
            self.execute()


if __name__ == "__main__":
    unittest.main()
