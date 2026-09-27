"""Local boundary tests; mocked replay is not hosted SDK acceptance."""

from contextlib import contextmanager
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, sha256_bytes, write_canonical_json,
)
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.products.signatures import (
    generate_development_key, verify_manifest_signature,
)
from ci.sdk_campaign_release_issuer import (
    prepare_sdk_release_index, sign_approved_sdk_release_index,
    stage_prepared_sdk_release_index,
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

    def _prepare(self, **changes):
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
        return prepare_sdk_release_index(self.root / "plan.json", self.root, **args)

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

    def test_no_secret_stage_rejects_development_catalog_and_signing_context(self):
        with self.assertRaises(ValueError):
            stage_prepared_sdk_release_index(canonical_json_bytes({
                "trustDomain": "development"}), self.root / "prepared")
        with patch.dict("os.environ", {"CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "signing-secret"):
                stage_prepared_sdk_release_index(b"{}\n", self.root / "prepared")
        self.assertFalse((self.root / "prepared").exists())


if __name__ == "__main__":
    unittest.main()
