"""Local boundary tests; mocked replay is not hosted SDK acceptance."""

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, sha256_bytes, write_canonical_json,
)
from products.index import SignedProductIndex
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.products.signatures import (
    generate_development_key, verify_manifest_signature,
)
from ci.sdk_campaign_release_issuer import (
    main, prepare_sdk_release_index, sign_approved_sdk_release_index,
    stage_prepared_sdk_release_index, verify_signed_sdk_release_index_against_official_replay,
)
from ci.tests.product_chain_support import output, write_receipt


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class SdkCampaignReleaseIssuerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-release-issuer-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.private_key, public_key, development = generate_development_key(self.root / "keys")
        self.keys = self.root / "release-keys"
        self.keys.mkdir()
        (self.keys / "release-test.pub").write_bytes(public_key.read_bytes())
        self.signing = {**development, "keyId": "release-test", "trustDomain": "release"}
        self.keyring = self.root / "keyring.json"
        write_canonical_json(self.keyring, {"schemaVersion": 1,
            "algorithm": "ssh-ed25519", "namespace": "codex-agent-product-v1",
            "trustDomain": "release", "activeKey": {"keyId": "release-test",
                "fingerprint": development["fingerprint"]}, "retiredKeys": []})
        self.repository = "owner/repository"
        self.producer = {"repository": self.repository,
            "workflowPath": ".github/workflows/product-validation.yml",
            "commit": "a" * 40, "tree": "b" * 40, "event": "pull_request",
            "runId": 3, "runAttempt": 1, "pullRequest": 31}
        self.context = {"kind": "pull-request", "pullRequest": 31,
            "commit": self.producer["commit"], "tree": self.producer["tree"],
            "runId": 3, "runAttempt": 1}
        self.path = "outputs/fixture.bin"
        self.receipts = {}
        for position, instance in enumerate(sorted(SDK_CAMPAIGN_INSTANCES)):
            receipt = write_receipt(self.root / f"receipt-{position}.json",
                product="sdk", component=instance.component, phase=instance.phase,
                target=instance.target, version="0.8.0", version_identity="0.8.0",
                outputs=[output("fixture", self.path, str(instance).encode())],
                upstream=[], context={"producer": self.producer})
            self.receipts[instance] = canonical_json_bytes(receipt)
        self.authority = self.root / "authority.json"
        write_canonical_json(self.authority, {"schemaVersion": 1, "product": "sdk",
            "sdkVersion": "0.8.0",
            "electionSha256": {name: sha256_bytes(name.encode()) for name in (
                "core-android", "native", "apple-js")},
            "semanticSha256": {name: sha256_bytes((name + "-semantic").encode())
                for name in ("core-android", "native", "apple-js")},
            "artifactPaths": [{"identity": {name: getattr(instance, name) for name in (
                "product", "component", "phase", "target")}, "relativePath": self.path}
                for instance in sorted(SDK_CAMPAIGN_INSTANCES)],
            "completedCatalogPin": {"producer": self.producer,
                "artifact_name": "catalog", "artifact_id": 1,
                "artifact_sha256": sha256_bytes(b"catalog"),
                "index_sha256": sha256_bytes(b"index"),
                "public_key_sha256": sha256_bytes(b"key"),
                "trusted_workflow_path": ".github/workflows/product-validation.yml",
                "trusted_job_name": "product-validation / sdk-catalog"}})

    def _prepare_options(self, **changes):
        args = dict(authority_file=self.authority, authority_artifact_id=7,
            authority_artifact_sha256=sha256_bytes(b"authority upload"),
            expected_authority_sha256=sha256_bytes(self.authority.read_bytes()),
            authority_workflow_sha="c" * 40,
            authority_workflow_path=".github/workflows/product-validation.yml",
            authority_job_name="product-validation / sdk-authority-upload",
            trusted_workflow_sha="c" * 40, election_files={}, semantic_files={},
            token="observation-only-token", environ={}, keyring_path=self.keyring,
            state_artifact_id=8, state_artifact_sha256=sha256_bytes(b"state"),
            state_wave=1, sdk_state_wave=1,
            keys_directory=self.keys,
            expected_keyring_sha256=sha256_bytes(self.keyring.read_bytes()),
            repository=self.repository, context=self.context, producer=self.producer)
        args.update(changes)
        return args

    def _prepare(self, **changes):
        return prepare_sdk_release_index(self.root / "plan.json", self.root,
            **self._prepare_options(**changes))

    def test_preparation_keeps_all_61_admissions_inside_held_official_replay(self):
        events = []

        @contextmanager
        def official(*_args, **_kwargs):
            events.append("held")
            yield ((self.receipts, object()), object())
            events.append("released")

        with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate_from_official_authority",
                   official):
            prepared = self._prepare()
        index = load_canonical_json_bytes(prepared)
        self.assertEqual(["held", "released"], events)
        self.assertEqual("release", index["trustDomain"])
        self.assertEqual(61, len(index["entries"]))
        self.assertEqual(self.signing, index["signing"])

        staged = self.root / "prepared"
        custody = stage_prepared_sdk_release_index(prepared, staged)
        self.assertEqual(staged / "product-index.json", custody)
        manifest = staged / "product-index.json"
        signature = sign_approved_sdk_release_index(manifest,
            expected_index_sha256=sha256_bytes(prepared), keyring_path=self.keyring,
            keys_directory=self.keys,
            expected_keyring_sha256=sha256_bytes(self.keyring.read_bytes()),
            private_key=self.private_key, environ={})
        detached = self.root / "product-index.sig"
        detached.write_bytes(signature)
        verify_manifest_signature(manifest, detached, self.keys / "release-test.pub", self.signing)
        self.assertEqual(prepared, manifest.read_bytes())
        with self.assertRaises(ValueError):
            stage_prepared_sdk_release_index(prepared, staged)

    def test_original_run_is_pinned_before_official_observation(self):
        @contextmanager
        def official(*_args, **_kwargs):
            yield ((self.receipts, object()), object())

        with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate_from_official_authority",
                   side_effect=official) as held:
            self._prepare(original_run_id=3, original_run_attempt=1)
            self.assertEqual(3, held.call_args.kwargs["original_run_id"])
            self.assertEqual(1, held.call_args.kwargs["original_run_attempt"])
            for changes in ({"original_run_id": 3},
                            {"original_run_id": 4, "original_run_attempt": 1}):
                with self.assertRaisesRegex(ValueError, "original run"):
                    self._prepare(**changes)
            self.assertEqual(1, held.call_count)

    def test_unpinned_inputs_fail_before_observation_and_raw_map_is_not_an_issuer(self):
        with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate_from_official_authority") as official:
            with self.assertRaisesRegex(ValueError, "protected pin"):
                self._prepare(expected_keyring_sha256=sha256_bytes(b"wrong"))
            with self.assertRaisesRegex(ValueError, "independent digest"):
                self._prepare(expected_authority_sha256=sha256_bytes(b"wrong"))
            official.assert_not_called()
        with self.assertRaisesRegex(ValueError, "exact observation options"):
            self._prepare(verified_receipts=self.receipts)

    def test_index_producer_must_equal_the_independently_pinned_authority(self):
        @contextmanager
        def official(*_args, **_kwargs):
            yield ((self.receipts, object()), object())

        another = {**self.producer, "runId": 4}
        another_context = {**self.context, "runId": 4}
        with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate_from_official_authority",
                   official), self.assertRaisesRegex(ValueError, "approved PR producer"):
            self._prepare(producer=another, context=another_context)

    def test_signer_rejects_development_catalog_wrong_pin_and_observation_token(self):
        manifest = self.root / "product-index.json"
        manifest.write_bytes(canonical_json_bytes({"trustDomain": "development"}))
        options = dict(expected_index_sha256=sha256_bytes(manifest.read_bytes()),
            keyring_path=self.keyring, keys_directory=self.keys,
            expected_keyring_sha256=sha256_bytes(self.keyring.read_bytes()),
            private_key=self.private_key, environ={})
        with self.assertRaises(ValueError):
            sign_approved_sdk_release_index(manifest, **options)
        with self.assertRaisesRegex(ValueError, "independent protected approval"):
            sign_approved_sdk_release_index(manifest, **{
                **options, "expected_index_sha256": sha256_bytes(b"other")})
        with self.assertRaisesRegex(ValueError, "observation token"):
            sign_approved_sdk_release_index(manifest, **{**options,
                "environ": {"GITHUB_TOKEN": "even-an-empty-variable-is-forbidden"}})
        with self.assertRaisesRegex(ValueError, "observation token"):
            sign_approved_sdk_release_index(manifest, **{**options,
                "environ": {"GITHUB_API_TOKEN": "observer"}})

    def test_no_secret_stage_rejects_development_catalog_and_signing_context(self):
        with self.assertRaises(ValueError):
            stage_prepared_sdk_release_index(canonical_json_bytes({
                "trustDomain": "development"}), self.root / "prepared")
        with patch.dict("os.environ", {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "signing-secret"):
                stage_prepared_sdk_release_index(b"{}\n", self.root / "prepared")
        self.assertFalse((self.root / "prepared").exists())

    def _cli_prepare_arguments(self):
        values = ["prepare", "--plan", str(self.root / "plan.json"),
            "--repository-root", str(self.root),
            "--authority-file", str(self.authority),
            "--authority-artifact-id", "7",
            "--authority-artifact-sha256", sha256_bytes(b"authority upload"),
            "--authority-workflow-sha", "c" * 40,
            "--authority-workflow-path", ".github/workflows/product-validation.yml",
            "--authority-job-name", "product-validation / sdk-authority-upload",
            "--trusted-workflow-sha", "c" * 40,
            "--state-artifact-id", "8",
            "--state-artifact-sha256", sha256_bytes(b"state"),
            "--state-wave", "1", "--sdk-state-wave", "1",
            "--keyring-path", str(self.keyring),
            "--keys-directory", str(self.keys),
            "--destination", str(self.root / "prepared")]
        for family in ("core-android", "native", "apple-js"):
            for kind in ("election", "semantic"):
                values.extend((f"--{kind}-{family}",
                    str(self.root / f"{kind}-{family}.json")))
        return values

    def test_split_cli_requires_external_pins_and_never_passes_token_to_signer(self):
        @contextmanager
        def official(*_args, **_kwargs):
            yield ((self.receipts, object()), object())

        with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate_from_official_authority",
                   official):
            prepared = self._prepare()
        arguments = self._cli_prepare_arguments() + [
            "--original-run-id", "3", "--original-run-attempt", "1"]
        with patch.dict(os.environ, {"GITHUB_TOKEN": "observation-only"}, clear=True), \
             patch("ci.sdk_campaign_release_issuer.prepare_sdk_release_index") as replay, \
             redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(arguments)
        replay.assert_not_called()
        prepare_environment = {"GITHUB_TOKEN": "observation-only",
            "CODEX_AGENT_SDK_AUTHORITY_APPROVED_SHA256": sha256_bytes(self.authority.read_bytes()),
            "CODEX_AGENT_PRODUCT_KEYRING_APPROVED_SHA256": sha256_bytes(self.keyring.read_bytes())}
        with patch.dict(os.environ, prepare_environment, clear=True), \
             patch("ci.sdk_campaign_release_issuer.prepare_sdk_release_index",
                   return_value=prepared) as replay, redirect_stdout(StringIO()) as printed:
            self.assertEqual(0, main(arguments))
        replay.assert_called_once()
        self.assertEqual("observation-only", replay.call_args.kwargs["token"])
        self.assertEqual(3, replay.call_args.kwargs["original_run_id"])
        self.assertEqual(1, replay.call_args.kwargs["original_run_attempt"])
        manifest = self.root / "prepared/product-index.json"
        self.assertEqual(prepared, manifest.read_bytes())
        self.assertEqual(str(manifest), json.loads(printed.getvalue())["preparedIndex"])

        sign_arguments = ["sign", "--prepared-index", str(manifest),
            "--destination", str(self.root / "signed"),
            "--keyring-path", str(self.keyring), "--keys-directory", str(self.keys)]
        approved = {"CODEX_AGENT_SDK_INDEX_APPROVED_SHA256": sha256_bytes(prepared),
            "CODEX_AGENT_PRODUCT_KEYRING_APPROVED_SHA256": sha256_bytes(self.keyring.read_bytes()),
            "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": self.private_key.read_text()}
        with patch.dict(os.environ, {**approved, "GH_TOKEN": ""}, clear=True), \
             redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(sign_arguments)
        self.assertFalse((self.root / "signed").exists())
        nested = list(sign_arguments)
        nested[nested.index("--destination") + 1] = str(self.root / "prepared/signed")
        with patch.dict(os.environ, approved, clear=True), \
             redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(nested)
        self.assertFalse((self.root / "prepared/signed").exists())
        with patch.dict(os.environ, {**approved,
                "CODEX_AGENT_SDK_INDEX_APPROVED_SHA256": sha256_bytes(b"wrong")}, clear=True), \
             redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(sign_arguments)
        self.assertFalse((self.root / "signed").exists())
        with patch.dict(os.environ, approved, clear=True), redirect_stdout(StringIO()):
            self.assertEqual(0, main(sign_arguments))
        self.assertEqual(prepared, (self.root / "signed/product-index.json").read_bytes())
        verify_manifest_signature(self.root / "signed/product-index.json",
            self.root / "signed/product-index.sig", self.keys / "release-test.pub", self.signing)
        verify_arguments = self._cli_prepare_arguments()
        verify_arguments[0] = "verify"
        destination_at = verify_arguments.index("--destination")
        del verify_arguments[destination_at:destination_at + 2]
        verify_arguments.extend(("--signed-index", str(self.root / "signed/product-index.json"),
            "--signature", str(self.root / "signed/product-index.sig")))
        verify_environment = {**prepare_environment,
            "CODEX_AGENT_SDK_INDEX_APPROVED_SHA256": sha256_bytes(prepared),
            "CODEX_AGENT_SDK_SIGNATURE_APPROVED_SHA256": sha256_bytes(
                (self.root / "signed/product-index.sig").read_bytes())}
        with patch.dict(os.environ, verify_environment, clear=True), \
             patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate_from_official_authority",
                   official), redirect_stdout(StringIO()) as verified:
            self.assertEqual(0, main(verify_arguments))
        self.assertEqual(sha256_bytes(prepared),
            json.loads(verified.getvalue())["verifiedIndexSha256"])

    def test_prepare_cli_rejects_optional_policy_without_protected_digest(self):
        policy = self.root / "tooling.json"
        policy.write_bytes(b"{}\n")
        args = self._cli_prepare_arguments() + ["--sdk-validation-tooling", str(policy)]
        environment = {"GITHUB_TOKEN": "observation-only",
            "CODEX_AGENT_SDK_AUTHORITY_APPROVED_SHA256": sha256_bytes(self.authority.read_bytes()),
            "CODEX_AGENT_PRODUCT_KEYRING_APPROVED_SHA256": sha256_bytes(self.keyring.read_bytes())}
        with patch.dict(os.environ, environment, clear=True), \
             patch("ci.sdk_campaign_release_issuer.prepare_sdk_release_index") as replay, \
             redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            main(args)
        replay.assert_not_called()

    def test_signed_index_rechecks_exact_originals_under_full_official_replay(self):
        receipts = self.receipts

        @contextmanager
        def official(*_args, **_kwargs):
            yield ((receipts, object()), object())

        with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate_from_official_authority",
                   official):
            prepared = self._prepare()
        manifest = self.root / "signed-product-index.json"
        manifest.write_bytes(prepared)
        signature = sign_approved_sdk_release_index(manifest,
            expected_index_sha256=sha256_bytes(prepared), keyring_path=self.keyring,
            keys_directory=self.keys,
            expected_keyring_sha256=sha256_bytes(self.keyring.read_bytes()),
            private_key=self.private_key, environ={})
        detached = self.root / "signed-product-index.sig"
        detached.write_bytes(signature)
        signed = SignedProductIndex(manifest, detached)
        options = self._prepare_options()
        with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate_from_official_authority",
                   official):
            index, raw = verify_signed_sdk_release_index_against_official_replay(
                signed, self.root / "plan.json", self.root,
                expected_index_sha256=sha256_bytes(prepared),
                expected_signature_sha256=sha256_bytes(signature), **options)
        self.assertEqual(61, len(index["entries"]))
        self.assertEqual(prepared, raw)

        with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate_from_official_authority") as replay:
            with self.assertRaisesRegex(ValueError, "independent protected approval"):
                verify_signed_sdk_release_index_against_official_replay(
                    signed, self.root / "plan.json", self.root,
                    expected_index_sha256=sha256_bytes(prepared),
                    expected_signature_sha256=sha256_bytes(b"wrong"), **options)
            replay.assert_not_called()
        with patch.dict(os.environ, {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": "secret"}), \
                patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate_from_official_authority") as replay:
            with self.assertRaisesRegex(ValueError, "signing-secret"):
                verify_signed_sdk_release_index_against_official_replay(
                    signed, self.root / "plan.json", self.root,
                    expected_index_sha256=sha256_bytes(prepared),
                    expected_signature_sha256=sha256_bytes(signature), **options)
            replay.assert_not_called()

        instance = min(SDK_CAMPAIGN_INSTANCES)
        changed = write_receipt(self.root / "changed-receipt.json", product="sdk",
            component=instance.component, phase=instance.phase, target=instance.target,
            version="0.8.0", version_identity="0.8.0",
            outputs=[output("fixture", self.path, b"changed original")], upstream=[],
            context={"producer": self.producer})
        receipts = {**receipts, instance: canonical_json_bytes(changed)}
        with patch("ci.sdk_campaign_catalog_producer.held_sdk_campaign_candidate_from_official_authority",
                   official), self.assertRaisesRegex(ValueError, "full official campaign replay"):
            verify_signed_sdk_release_index_against_official_replay(
                signed, self.root / "plan.json", self.root,
                expected_index_sha256=sha256_bytes(prepared),
                expected_signature_sha256=sha256_bytes(signature), **options)


if __name__ == "__main__":
    unittest.main()
