import tempfile
import io
import os
import shutil
import unittest
from contextlib import contextmanager, redirect_stderr
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ci import sdk_android_core14_caller as caller
from ci.products.inventory import (canonical_json_bytes, load_canonical_json_bytes,
    sha256_bytes, sha256_file, snapshot_regular_tree)
from ci.products.registry import SDK_FACADE_TARGETS
from ci.products.signatures import generate_development_key
import sdk_facade_original_inputs as original_inputs
import sdk_facade_metadata_original as original_metadata


class AndroidCore14CallerTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
    def test_reused_core_holds_signed_twelve_originals_through_android_admission(self):
        from ci.tests.test_sdk_facade_metadata_selection import FacadeMetadataSelectionTest

        fixture = FacadeMetadataSelectionTest(methodName="runTest")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        source = fixture.a
        selected = {"common": source.envelope,
                    **{value["receipt"]["target"]: value for value in source.predecessors}}
        digests = {target: envelope["receiptSha256"] for target, envelope in selected.items()}
        replay = deepcopy(source.policy)
        for record in replay["validations"].values():
            record.pop("captureRoot")
        captures = {Path(source.policy["validations"][target]["validationReceipt"]):
                    Path(source.policy["validations"][target]["captureRoot"])
                    for target in SDK_FACADE_TARGETS}
        archive = fixture.root / "android.tar.gz"
        archive.write_bytes(b"Git-pinned Android archive fixture")
        caller_key = fixture.root / "caller-pinned.pub"
        caller_key.write_bytes(fixture.catalog.public_key.read_bytes())
        context_manifest, context_signature, context_keyring = (fixture.root / name for name in
            ("signed-context.json", "signed-context.sig", "context-keyring.json"))
        for path in (context_manifest, context_signature, context_keyring):
            path.write_bytes(b"caller-owned test input")
        context_keys = fixture.root / "context-keys"
        context_keys.mkdir()
        metadata_transport = load_canonical_json_bytes(
            (source.f.retained / "capture-transport.json").read_bytes())["artifact"]
        original_locator = {"artifact_id": metadata_transport["id"],
            "artifact_sha256": metadata_transport["digest"]}
        catalog = replace(fixture.catalog, public_key=caller_key)
        android_key = "sha256:" + "b" * 64
        metadata_key = source.envelope["receipt"]["buildKey"]
        original_context = replay.pop("originalContext")
        state_row = {"state": "reused", "source": "same-pr",
            "transportSource": {"indexSha256": sha256_file(fixture.catalog.manifest)},
            "buildKey": metadata_key, "receiptSha256": digests["common"]}
        verified = SimpleNamespace(prior_by_instance={caller.PhaseInstanceId(
            "sdk", "sdk-core", "metadata", "common"): state_row},
            prior_ready_plans={caller._BINARY: {"product": "sdk", "component": "sdk-android",
                "phase": "binary", "target": "android", "buildKey": android_key}},
            plan={"validationCommit": "c" * 40})
        admissions = []

        @contextmanager
        def replay_original(**inputs):
            capture = Path(inputs["capture_root"])
            self.assertEqual(fixture.root, inputs["repository_root"])
            self.assertEqual(source.envelope["receiptBytes"], inputs["metadata_receipt_path"].read_bytes())
            self.assertEqual(set(SDK_FACADE_TARGETS), set(inputs["validations"]))
            self.assertEqual(original_context, inputs["original_context"])
            result = {"receipt": deepcopy(source.envelope["receipt"]),
                "receiptBytes": source.envelope["receiptBytes"],
                "receiptPath": inputs["metadata_receipt_path"], "capture": capture,
                "original": capture / "original",
                "stage": fixture.root / "build/product-stage/sdk/sdk-core/metadata/common",
                "transport": load_canonical_json_bytes((capture / "capture-transport.json").read_bytes())}
            source.events.append("enter")
            try:
                yield result
            finally:
                source.events.append("exit")

        def copy_original(plan, destination, *, validation_receipt_path=None,
                metadata_receipt_path=None, **kwargs):
            receipt = validation_receipt_path or metadata_receipt_path
            source_capture = source.f.retained if metadata_receipt_path else captures[Path(receipt)]
            snapshot_regular_tree(source_capture, destination, allow_empty=True)

        def verify_state(*args, **kwargs):
            admission = kwargs["sdk_facade_metadata_admission"]
            self.assertIsInstance(admission, caller.FacadeMetadataAdmission)
            admission.verify_metadata(source.envelope, source.predecessors)
            admissions.append(admission)
            return verified

        arguments = dict(plan=fixture.f.plan, discovery=fixture.root / "discovery",
            before_state=fixture.root / "before", after_state=fixture.root / "after",
            metadata_receipt=source.f.receipt_path, expected_build_key=android_key,
            expected_metadata_build_key=metadata_key,
            expected_metadata_receipt_sha256=digests["common"],
            replay_policy=replay, original_context=original_context,
            trusted_workflow_sha="e" * 40, repository_root=fixture.root,
            android_runtime_archive=archive, token="token", environ={},
            reused_catalog=catalog, reused_catalog_root=catalog.manifest.parent,
            reused_catalog_source="same-pr", reused_receipt_sha256=digests,
            reused_context_manifest=context_manifest, reused_context_signature=context_signature,
            reused_context_keyring=context_keyring, reused_context_keys_directory=context_keys)
        with (patch.object(original_inputs, "locate_original_facade_upload",
                           return_value={"artifact_id": 123, "artifact_sha256": "sha256:" + "d" * 64}),
              patch.object(caller, "locate_original_facade_upload",
                           return_value=original_locator),
              patch.object(caller, "verify_signed_original_core_context",
                           return_value=original_context) as signed_context,
              patch.object(original_metadata, "verified_retained_sdk_facade_metadata",
                           side_effect=replay_original),
              patch.object(original_inputs, "capture_sdk_facade_validation_upload", side_effect=copy_original),
              patch.object(original_inputs, "capture_sdk_facade_metadata_upload", side_effect=copy_original),
              patch.object(caller.product_reuse, "_verified_product_state", side_effect=verify_state),
              patch.object(caller, "git_regular_blob_bytes", return_value=b"pins"),
              patch.object(caller, "_properties", return_value={
                  "codexAgent.codexArchiveSha256": sha256_file(archive).split(":", 1)[1]})):
            self.assertEqual(android_key, caller.with_core14(**arguments)["buildKey"])
            self.assertEqual(metadata_transport["id"], signed_context.call_args.kwargs["expected_artifact_id"])
            self.assertEqual(1, len(admissions))
            oversized = fixture.root / "oversized-receipt.json"
            with oversized.open("wb") as output:
                output.truncate(16 * 1024 * 1024 + 1)
            with patch.object(caller, "locate_original_facade_upload",
                    side_effect=AssertionError("unbounded receipt reached original lookup")), \
                    self.assertRaisesRegex(ValueError, "File is too large"):
                caller.with_core14(**{**arguments, "metadata_receipt": oversized})
            with self.assertRaisesRegex(ValueError, "protected signed context"):
                caller.with_core14(**{**arguments, "original_context": {"foreign": "context"}})
            with patch.object(caller, "locate_original_facade_upload", return_value={
                    "artifact_id": metadata_transport["id"],
                    "artifact_sha256": "sha256:" + "0" * 64}):
                with self.assertRaisesRegex(ValueError, "another original upload"):
                    caller.with_core14(**arguments)
            wrong = {**digests, "jvm": "sha256:" + "0" * 64}
            with self.assertRaisesRegex(ValueError, "original receipt differs"):
                caller.with_core14(**{**arguments, "reused_receipt_sha256": wrong})
            _, foreign_key, _ = generate_development_key(fixture.root / "foreign-key")
            with self.assertRaises(ValueError):
                caller.with_core14(**{**arguments, "reused_catalog": replace(
                    catalog, public_key=foreign_key)})
            state_row["transportSource"]["indexSha256"] = "sha256:" + "0" * 64
            with self.assertRaisesRegex(ValueError, "signed reused election"):
                caller.with_core14(**arguments)
            self.assertEqual(2, len(admissions))

    def test_reused_cli_rejects_replay_controls_from_carrier_or_checkout(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            carrier, checkout = root / "carrier", root / "checkout"
            carrier.mkdir()
            checkout.mkdir()
            catalog, digests, key = (root / name for name in
                ("catalog.json", "digests.json", "caller.pub"))
            signed, signature, context_keyring = (root / name for name in
                ("signed.json", "signed.sig", "context-keyring.json"))
            context_keys = root / "context-keys"
            context_keys.mkdir()
            for path in (signed, signature, context_keyring):
                path.write_bytes(b"independent caller test input")
            catalog.write_bytes(canonical_json_bytes({}))
            digests.write_bytes(canonical_json_bytes({}))
            key.write_bytes(b"caller key")
            common = ["preflight", "--plan", str(root / "plan"),
                "--discovery-root", str(root / "discovery"),
                "--before-state-root", str(root / "before"),
                "--after-state-root", str(root / "after"),
                "--metadata-receipt", str(root / "receipt"),
                "--repository-root", str(checkout),
                "--android-runtime-archive", str(root / "archive"),
                "--expected-build-key", "sha256:" + "a" * 64,
                "--expected-metadata-build-key", "sha256:" + "b" * 64,
                "--expected-metadata-receipt-sha256", "sha256:" + "c" * 64,
                "--trusted-workflow-sha", "d" * 40,
                "--reused-catalog", str(catalog),
                "--reused-catalog-root", str(carrier),
                "--reused-catalog-source", "same-pr",
                "--reused-receipt-sha256", str(digests),
                "--reused-public-key", str(key),
                "--reused-context-manifest", str(signed),
                "--reused-context-signature", str(signature),
                "--reused-context-keyring", str(context_keyring),
                "--reused-context-keys-directory", str(context_keys)]
            with (patch.object(caller, "with_core14") as execute,
                  patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"})):
                for control in ("replay-policy", "original-context"):
                    for source in (carrier, checkout):
                        with self.subTest(control=control, source=source):
                            replay, context = root / "replay.json", root / "context.json"
                            if control == "replay-policy":
                                replay = source / "replay.json"
                            else:
                                context = source / "context.json"
                            replay.write_bytes(canonical_json_bytes({}))
                            context.write_bytes(canonical_json_bytes({}))
                            with redirect_stderr(io.StringIO()) as error:
                                with self.assertRaises(SystemExit):
                                    caller.main([*common, "--replay-policy", str(replay),
                                        "--original-context", str(context)])
                            self.assertIn("independent of retained carriers", error.getvalue())
                execute.assert_not_called()

    def test_reused_core_requires_signed_original_selection_and_matching_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            carrier = root / "carrier"
            carrier.mkdir()
            archive, receipt_path, descriptor = (root / name for name in
                ("android.tar.gz", "metadata-receipt.json", "policy.json"))
            manifest = carrier / "product-index.json"
            archive.write_bytes(b"pinned archive")
            manifest.write_bytes(b"signed index bytes")
            (root / "caller.pub").write_bytes(b"caller key")
            context_manifest, context_signature, context_keyring = (root / name for name in
                ("signed-context.json", "signed-context.sig", "context-keyring.json"))
            for path in (context_manifest, context_signature, context_keyring):
                path.write_bytes(b"caller-owned test input")
            context_keys = root / "context-keys"
            context_keys.mkdir()
            receipt_path.write_bytes(canonical_json_bytes({"selected": "original"}))
            policy = {"toolingEvidence": "evidence", "toolingPublicKey": "key",
                "javaExecutable": "java", "toolingTrustDomain": "release",
                "toolingKeyring": "keyring", "toolingKeysDirectory": "keys"}
            original_capture = root / "originals/common"
            original_capture.mkdir(parents=True)
            (original_capture / "capture-transport.json").write_bytes(canonical_json_bytes({
                "artifact": {"id": 123, "digest": "sha256:" + "d" * 64}}))
            descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": str(root / "originals"),
                "records": [], "policy": policy}))
            digests = {"common": sha256_bytes(receipt_path.read_bytes()), "native": "sha256:" + "f" * 64}
            key = "sha256:" + "b" * 64
            metadata_key = "sha256:" + "d" * 64
            catalog = caller.RemoteCatalog(manifest, root / "product-index.sig", {},
                public_key=root / "caller.pub")
            active = []

            @contextmanager
            def held(*args, **kwargs):
                self.assertEqual(kwargs["expected_receipt_sha256"], digests)
                self.assertEqual(kwargs["replay_policy"], {"validations": {},
                    "originalContext": {"original": "context"}})
                active.append(True)
                try:
                    yield descriptor
                finally:
                    active.pop()

            state_row = {"state": "reused", "source": "same-pr",
                "transportSource": {"indexSha256": sha256_file(manifest)},
                "buildKey": metadata_key, "receiptSha256": digests["common"]}
            verified = SimpleNamespace(prior_by_instance={caller.PhaseInstanceId(
                "sdk", "sdk-core", "metadata", "common"): state_row},
                prior_ready_plans={caller._BINARY: {"product": "sdk", "component": "sdk-android",
                    "phase": "binary", "target": "android", "buildKey": key}},
                plan={"validationCommit": "c" * 40})
            arguments = dict(plan=root / "plan", discovery=root / "discovery",
                before_state=root / "before", after_state=root / "after",
                metadata_receipt=receipt_path, expected_build_key=key,
                expected_metadata_build_key=metadata_key,
                expected_metadata_receipt_sha256=digests["common"],
                replay_policy={"validations": {}}, original_context={"original": "context"},
                trusted_workflow_sha="e" * 40, repository_root=root,
                android_runtime_archive=archive, token="token", environ={},
                reused_catalog=catalog, reused_catalog_root=carrier,
                reused_catalog_source="same-pr",
                reused_receipt_sha256=digests,
                reused_context_manifest=context_manifest, reused_context_signature=context_signature,
                reused_context_keyring=context_keyring, reused_context_keys_directory=context_keys)
            with (patch.object(caller, "held_original_facade_metadata_policy", held),
                  patch.object(caller, "locate_original_facade_upload",
                               return_value={"artifact_id": 123, "artifact_sha256": "sha256:" + "d" * 64}),
                  patch.object(caller, "verify_signed_original_core_context",
                               return_value={"original": "context"}),
                  patch.object(caller, "held_same_campaign_core_metadata_policy") as fresh,
                  patch.object(caller, "validate_phase_receipt", return_value={
                      "product": "sdk", "component": "sdk-core", "phase": "metadata",
                      "target": "common", "buildKey": metadata_key}),
                  patch.object(caller, "FacadeMetadataAdmission", return_value=object()),
                  patch.object(caller.product_reuse, "_validate_plan",
                      return_value={"validationCommit": "c" * 40}),
                  patch.object(caller.product_reuse, "_verified_product_state", return_value=verified),
                  patch.object(caller, "git_regular_blob_bytes", return_value=b"pins"),
                  patch.object(caller, "_properties", return_value={
                      "codexAgent.codexArchiveSha256": sha256_file(archive).split(":", 1)[1]})):
                self.assertEqual(caller.with_core14(**arguments)["buildKey"], key)
                self.assertFalse(active)
                fresh.assert_not_called()
                for pin in ({"expected_metadata_artifact_id": 123},
                            {"expected_metadata_artifact_sha256": "sha256:" + "d" * 64}):
                    with self.subTest(pin=pin), self.assertRaisesRegex(ValueError,
                            "Fresh Core upload pins cannot accompany reused Core metadata"):
                        caller.with_core14(**{**arguments, **pin})
                state_row["transportSource"]["indexSha256"] = "sha256:" + "0" * 64
                with self.assertRaisesRegex(ValueError, "signed reused election"):
                    caller.with_core14(**arguments)
                with self.assertRaisesRegex(ValueError, "twelve pinned receipts"):
                    caller.with_core14(**{**arguments, "reused_receipt_sha256": None})

    def test_preflight_and_execution_each_hold_concrete_core_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root / "android.tar.gz"
            archive.write_bytes(b"pinned Android archive")
            descriptor = root / "core-policy.json"
            policy = {"toolingEvidence": "evidence", "toolingPublicKey": "key",
                "javaExecutable": "java", "toolingTrustDomain": "release",
                "toolingKeyring": "keyring", "toolingKeysDirectory": "keys"}
            descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": "originals",
                "records": [{"receiptSha256": "sha256:" + "a" * 64,
                    "captureRoot": "common"}], "policy": policy}))
            active = []
            admissions = []
            original_context = {"repositoryRoot": "/original/core/checkout",
                "metadataRequest": "/original/core/private/metadata-request.json"}

            @contextmanager
            def held(*args, **kwargs):
                self.assertEqual(kwargs["original_context"], original_context)
                active.append(True)
                try:
                    yield descriptor
                finally:
                    active.pop()

            def verified(*args, **kwargs):
                self.assertTrue(active)
                admissions.append(kwargs["sdk_facade_metadata_admission"])
                return SimpleNamespace(prior_ready_plans={caller._BINARY: {"product": "sdk",
                    "component": "sdk-android", "phase": "binary", "target": "android",
                    "buildKey": "sha256:" + "b" * 64}},
                    plan={"validationCommit": "c" * 40})

            def execute(*args, **kwargs):
                self.assertTrue(active)
                self.assertIs(kwargs["sdk_facade_metadata_admission"], admissions[-1])
                return "executed"

            with (patch.object(caller, "held_same_campaign_core_metadata_policy", held),
                  patch.object(caller, "FacadeMetadataAdmission", return_value=object()),
                  patch.object(caller.product_reuse, "_validate_plan",
                      return_value={"validationCommit": "c" * 40}),
                  patch.object(caller.product_reuse, "_verified_product_state", side_effect=verified),
                  patch.object(caller, "git_regular_blob_bytes", return_value=b"pins"),
                  patch.object(caller, "_properties", return_value={
                      "codexAgent.codexArchiveSha256": sha256_file(archive).split(":", 1)[1]}),
                  patch.object(caller.sdk_maven_binary_workflow, "execute", side_effect=execute)):
                arguments = dict(plan=root / "plan", discovery=root / "discovery",
                    before_state=root / "before", after_state=root / "after",
                    metadata_receipt=root / "receipt", expected_build_key="sha256:" + "b" * 64,
                    expected_metadata_build_key="sha256:" + "d" * 64,
                    expected_metadata_receipt_sha256="sha256:" + "a" * 64,
                    expected_metadata_artifact_id=42,
                    expected_metadata_artifact_sha256="sha256:" + "f" * 64,
                    replay_policy={}, original_context=original_context, trusted_workflow_sha="e" * 40,
                    repository_root=root, android_runtime_archive=archive, token="token", environ={})
                self.assertEqual(caller.with_core14(**arguments)["buildKey"], arguments["expected_build_key"])
                self.assertFalse(active)
                self.assertEqual(caller.with_core14(**{**arguments, "expected_build_key": None})["buildKey"],
                    arguments["expected_build_key"])
                self.assertFalse(active)
                self.assertEqual(caller.with_core14(**arguments, destination=root / "output"), "executed")
                self.assertFalse(active)
                self.assertEqual(len(admissions), 3)
                with self.assertRaisesRegex(ValueError, "exact elected build key"):
                    caller.with_core14(**{**arguments, "expected_build_key": None}, destination=root / "output")

    def test_wrong_android_election_fails_while_core_is_held(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root / "android.tar.gz"
            archive.write_bytes(b"archive")
            descriptor = root / "policy.json"
            descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": "originals", "records": [],
                "policy": {"toolingEvidence": "evidence", "toolingPublicKey": "key",
                    "javaExecutable": "java", "toolingTrustDomain": "release",
                    "toolingKeyring": "keyring", "toolingKeysDirectory": "keys"}}))

            @contextmanager
            def held(*args, **kwargs):
                yield descriptor

            with (patch.object(caller, "held_same_campaign_core_metadata_policy", held),
                  patch.object(caller, "FacadeMetadataAdmission", return_value=object()),
                  patch.object(caller.product_reuse, "_validate_plan",
                      return_value={"validationCommit": "c" * 40}),
                  patch.object(caller.product_reuse, "_verified_product_state",
                      return_value=SimpleNamespace(prior_ready_plans={},
                          plan={"validationCommit": "c" * 40})),
                  patch.object(caller, "git_regular_blob_bytes", return_value=b"pins"),
                  patch.object(caller, "_properties", return_value={
                      "codexAgent.codexArchiveSha256": sha256_file(archive).split(":", 1)[1]}),
                  patch.object(caller.sdk_maven_binary_workflow, "execute") as execute):
                with self.assertRaisesRegex(ValueError, "Core-admitted election"):
                    caller.with_core14(root / "plan", root / "discovery", root / "before",
                        root / "after", root / "receipt", expected_build_key="sha256:" + "b" * 64,
                        expected_metadata_build_key="sha256:" + "d" * 64,
                        expected_metadata_receipt_sha256="sha256:" + "a" * 64,
                        expected_metadata_artifact_id=42,
                        expected_metadata_artifact_sha256="sha256:" + "f" * 64,
                        replay_policy={}, original_context={}, trusted_workflow_sha="e" * 40,
                        repository_root=root, android_runtime_archive=archive, token="token", environ={})
                self.assertIsNone(caller.with_core14(root / "plan", root / "discovery", root / "before",
                    root / "after", root / "receipt", expected_metadata_build_key="sha256:" + "d" * 64,
                    expected_metadata_receipt_sha256="sha256:" + "a" * 64,
                    expected_metadata_artifact_id=42,
                    expected_metadata_artifact_sha256="sha256:" + "f" * 64,
                    replay_policy={}, original_context={}, trusted_workflow_sha="e" * 40,
                    repository_root=root, android_runtime_archive=archive, token="token", environ={}))
                execute.assert_not_called()

    def test_cli_preflight_emits_only_elected_android_matrix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            policy, context, output = (root / name for name in
                ("replay.json", "context.json", "github-output"))
            policy.write_bytes(canonical_json_bytes({}))
            context.write_bytes(canonical_json_bytes({}))
            output.write_text("")
            argv = ["preflight", "--plan", str(root / "plan"),
                "--discovery-root", str(root / "discovery"),
                "--before-state-root", str(root / "before"),
                "--after-state-root", str(root / "after"),
                "--metadata-receipt", str(root / "receipt"),
                "--replay-policy", str(policy), "--original-context", str(context),
                "--repository-root", str(root), "--android-runtime-archive", str(root / "archive"),
                "--expected-build-key", "sha256:" + "a" * 64,
                "--expected-metadata-build-key", "sha256:" + "b" * 64,
                "--expected-metadata-receipt-sha256", "sha256:" + "c" * 64,
                "--trusted-workflow-sha", "d" * 40, "--github-output", str(output)]
            selected = {"product": "sdk", "component": "sdk-android", "phase": "binary",
                "target": "android", "buildKey": "sha256:" + "a" * 64}
            with (patch.object(caller, "with_core14", return_value=selected) as source,
                  patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"})):
                self.assertEqual(caller.main(argv), 0)
            self.assertEqual(source.call_args.kwargs["token"], "test-token")
            raw = output.read_text()
            self.assertIn('"runner":"ubuntu-24.04"', raw)
            self.assertIn("sdk_workers_required=true\n", raw)

    def test_cli_election_emits_zero_or_one_without_a_caller_supplied_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            policy, context, output = (root / name for name in
                ("replay.json", "context.json", "github-output"))
            policy.write_bytes(canonical_json_bytes({}))
            context.write_bytes(canonical_json_bytes({}))
            argv = ["elect", "--plan", str(root / "plan"),
                "--discovery-root", str(root / "discovery"),
                "--before-state-root", str(root / "before"),
                "--after-state-root", str(root / "after"),
                "--metadata-receipt", str(root / "receipt"),
                "--replay-policy", str(policy), "--original-context", str(context),
                "--repository-root", str(root), "--android-runtime-archive", str(root / "archive"),
                "--expected-metadata-build-key", "sha256:" + "b" * 64,
                "--expected-metadata-receipt-sha256", "sha256:" + "c" * 64,
                "--trusted-workflow-sha", "d" * 40, "--github-output", str(output)]
            selected = {"product": "sdk", "component": "sdk-android", "phase": "binary",
                "target": "android", "buildKey": "sha256:" + "a" * 64}
            with (patch.object(caller, "with_core14", side_effect=(None, selected)) as source,
                  patch.dict(os.environ, {"GITHUB_TOKEN": "test-token"})):
                self.assertEqual(caller.main(argv), 0)
                self.assertEqual(caller.main(argv), 0)
            self.assertEqual(source.call_args.kwargs["expected_build_key"], None)
            raw = output.read_text()
            self.assertIn('sdk_matrix={"include":[]}\n', raw)
            self.assertIn("sdk_workers_required=false\n", raw)
            self.assertIn('"buildKey":"sha256:' + "a" * 64 + '"', raw)
            self.assertIn("sdk_workers_required=true\n", raw)
            with redirect_stderr(io.StringIO()) as error:
                with self.assertRaises(SystemExit):
                    caller.main([*argv, "--expected-build-key", selected["buildKey"]])
            self.assertIn("elect derives the build key", error.getvalue())

    def test_package_replays_core_while_retaining_s858_and_original_binary_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            archive = root / "archive.tar.gz"
            archive.write_bytes(b"pinned")
            descriptor = root / "descriptor.json"
            descriptor.write_bytes(canonical_json_bytes({"evidenceRoot": "originals", "records": [],
                "policy": {"toolingEvidence": "evidence", "toolingPublicKey": "key",
                    "javaExecutable": "java", "toolingTrustDomain": "release",
                    "toolingKeyring": "keyring", "toolingKeysDirectory": "keys"}}))
            active = []

            @contextmanager
            def held(*args, **kwargs):
                active.append(True)
                try:
                    yield descriptor
                finally:
                    active.pop()

            def verified(*args, **kwargs):
                self.assertTrue(active)
                self.assertEqual(args[2], root / "wave15")
                return SimpleNamespace(prior_ready_plans={caller._PACKAGE: {
                    "product": "sdk", "component": "sdk-android", "phase": "package",
                    "target": "android", "buildKey": "sha256:" + "b" * 64}},
                    plan={"validationCommit": "c" * 40})

            def package(*args, **kwargs):
                self.assertTrue(active)
                self.assertIsNotNone(kwargs["sdk_facade_metadata_admission"])
                self.assertEqual(kwargs["sdk_inputs_artifact_id"], 71)
                self.assertEqual(kwargs["binary_artifact_id"], 72)
                self.assertEqual(kwargs["binary_contract_evidence"], {"original": "contract"})
                self.assertEqual(kwargs["binary_original_context"], {"original": "binary"})
                self.assertEqual(kwargs["binary_original_workflow_path"],
                    ".github/workflows/sdk-android-binary-validation.yml")
                self.assertEqual(kwargs["binary_original_job_name"],
                    "product-validation / sdk-android-binary-result / sdk-android-binary-android")
                return "package executed"

            with (patch.object(caller, "held_same_campaign_core_metadata_policy", held),
                  patch.object(caller, "FacadeMetadataAdmission", return_value=object()),
                  patch.object(caller.product_reuse, "_validate_plan",
                      return_value={"validationCommit": "c" * 40}),
                  patch.object(caller.product_reuse, "_verified_product_state", side_effect=verified),
                  patch.object(caller, "git_regular_blob_bytes", return_value=b"pins"),
                  patch.object(caller, "_properties", return_value={
                      "codexAgent.codexArchiveSha256": sha256_file(archive).split(":", 1)[1]}),
                  patch.object(caller.sdk_maven_package_workflow, "execute", side_effect=package)):
                args = dict(plan=root / "plan", discovery=root / "discovery",
                    before_state=root / "wave13", after_state=root / "wave14",
                    selected_state=root / "wave15", metadata_receipt=root / "receipt",
                    expected_build_key="sha256:" + "b" * 64,
                    expected_metadata_build_key="sha256:" + "d" * 64,
                    expected_metadata_receipt_sha256="sha256:" + "a" * 64,
                    expected_metadata_artifact_id=42,
                    expected_metadata_artifact_sha256="sha256:" + "f" * 64,
                    replay_policy={}, original_context={}, trusted_workflow_sha="e" * 40,
                    repository_root=root, android_runtime_archive=archive, token="token", environ={},
                    phase="package", sdk_inputs_artifact_id=71,
                    sdk_inputs_artifact_sha256="sha256:" + "f" * 64,
                    binary_artifact_id=72, binary_artifact_sha256="sha256:" + "1" * 64,
                    binary_contract_evidence={"original": "contract"},
                    binary_original_context={"original": "binary"},
                    binary_original_workflow_path=".github/workflows/sdk-android-binary-validation.yml",
                    binary_original_job_name="product-validation / sdk-android-binary-result / sdk-android-binary-android",
                    keyring=root / "keyring", keys_directory=root / "keys")
                self.assertEqual(caller.with_core14(**args)["phase"], "package")
                self.assertFalse(active)
                self.assertEqual(caller.with_core14(**args, destination=root / "output"),
                    "package executed")
                self.assertFalse(active)
                with self.assertRaisesRegex(ValueError, "independent S858 and binary inputs"):
                    caller.with_core14(**{**args, "binary_artifact_sha256": None})
                with self.assertRaisesRegex(ValueError, "independent S858 and binary inputs"):
                    caller.with_core14(**{**args, "binary_original_job_name": None})


if __name__ == "__main__":
    unittest.main()
