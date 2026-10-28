"""SDK Maven custody joins signed identity to original object bytes, not host proof."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ci.products.index import SignedProductIndex
from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory, sha256_bytes, snapshot_regular_tree
from ci.products.receipt import compute_build_key, output_inventory_digest, write_output_manifest
from ci.products.registry import PhaseInstanceId
from ci.products.restore import finalize_phase_object
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.sdk_phase10_maven_campaign import _PACKAGES, capture_sdk_phase10_maven_campaign
from ci.tests.test_products import phase_receipt, producer


class SdkPhase10MavenCampaignTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-maven-campaign-", dir="/private/tmp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.index = self.root / "product-index.json"
        self.signature = self.root / "product-index.sig"
        self.keyring = self.root / "keyring.json"
        self.keys = self.root / "keys"
        self.keys.mkdir()
        for path, data in ((self.index, b"index\n"), (self.signature, b"signature\n"),
                           (self.keyring, b"keyring\n"), (self.keys / "release.pub", b"public\n")):
            path.write_bytes(data)
        self.selections = {}
        self.shards = {}
        self.validated_plans = {}
        entries = []
        for instance in sorted(SDK_CAMPAIGN_INSTANCES):
            entry = {"product": instance.product, "component": instance.component,
                     "phase": instance.phase, "target": instance.target,
                     "productVersion": "0.8.0"}
            if instance in _PACKAGES:
                number = len(self.shards) + 1
                original = {**producer(), "workflowPath": ".github/workflows/ci.yml",
                    "commit": str(number) * 40, "tree": str(number + 3) * 40,
                    "runId": 100 + number}
                root = self.root / instance.component
                root.mkdir()
                self.validated_plans[root] = {"repository": original["repository"],
                    "validationCommit": original["commit"],
                    "validationTree": original["tree"], "event": "pull_request",
                    "pullRequest": original["pullRequest"], "remoteBuildAuthorized": True}
                source = root / "source"
                source.mkdir()
                output = source / "outputs/maven/payload.jar"
                output.parent.mkdir(parents=True)
                output.write_bytes(instance.component.encode())
                write_output_manifest(source, "sdk", instance.component, "package",
                                      instance.target, "0.8.0", {"maven": "outputs/maven"})
                inputs = phase_receipt()["inputs"]
                inputs["versionIdentity"] = "0.8.0"
                build_key = compute_build_key(product="sdk", component=instance.component,
                    phase="package", target=instance.target, inputs=inputs)
                shard = root / "shard"
                verified = finalize_phase_object(stage_root=source,
                    phase_plan={"schemaVersion": 1, "product": "sdk",
                        "component": instance.component, "phase": "package",
                        "target": instance.target, "buildKey": build_key, "inputs": inputs},
                    producer=original, product_version="0.8.0",
                    trust_domain="development", destination=shard)
                raw = verified["receiptBytes"]
                receipt = root / "receipt.json"
                receipt.write_bytes(raw)
                plan = root / "plan.json"
                plan.write_bytes(b"original plan\n")
                self.shards[instance] = shard
                self.selections[instance] = {
                    "plan": str(plan), "repositoryRoot": str(root), "receipt": str(receipt),
                    "receiptSha256": sha256_bytes(raw), "producer": original,
                    "producerSha256": sha256_bytes(canonical_json_bytes(original)),
                    "artifactId": len(self.shards),
                    "artifactSha256": sha256_bytes(instance.component.encode()),
                    "trustedWorkflowSha": "a" * 40,
                }
                entry.update(buildKey=build_key, receiptSha256=sha256_bytes(raw),
                    outputs=verified["receipt"]["outputs"],
                    outputInventoryDigest=output_inventory_digest(verified["receipt"]["outputs"]),
                    artifactName=verified["receipt"]["outputs"][0]["relativePath"],
                    artifactSha256=verified["receipt"]["outputs"][0]["sha256"])
            entries.append(entry)
        self.campaign = {"repository": "codex-agent-labs/codex-agent",
                         "trustDomain": "release", "context": {"kind": "pull-request", "pullRequest": 31},
                         "entries": entries}

    def _capture(self, _plan, destination, **options):
        instance = next(instance for instance, selection in self.selections.items()
                        if selection["receipt"] == str(options.get("receipt_path", options.get("package_receipt_path"))))
        snapshot_regular_tree(self.shards[instance], Path(destination) / "original/shard")
        (Path(destination) / "worker.log").write_bytes(b"")
        return {"artifact": {"id": options["artifact_id"], "digest": options["artifact_sha256"]},
                "captureProducer": self.selections[instance]["producer"]}

    def _validate_plan(self, path, root, *, expected_revision):
        selection = next(row for row in self.selections.values() if row["plan"] == str(path))
        self.assertEqual(Path(selection["repositoryRoot"]), Path(root))
        self.assertEqual(selection["producer"]["commit"], expected_revision)
        return self.validated_plans[Path(root)]

    def _run(self):
        with patch("ci.sdk_phase10_maven_campaign.verify_release_product_index",
                   return_value=(self.campaign, self.index.read_bytes())), \
             patch("ci.sdk_phase10_maven_campaign.product_reuse._validate_plan",
                   side_effect=self._validate_plan), \
             patch("ci.sdk_phase10_maven_campaign.capture_sdk_maven_upload", side_effect=self._capture), \
             patch("ci.sdk_phase10_maven_campaign.product_reuse.capture_sdk_ios_package_upload",
                   side_effect=self._capture):
            return capture_sdk_phase10_maven_campaign(
                SignedProductIndex(self.index, self.signature), self.root / "custody",
                expected_index_sha256=sha256_bytes(self.index.read_bytes()),
                expected_signature_sha256=sha256_bytes(self.signature.read_bytes()),
                keyring_path=self.keyring, keys_directory=self.keys,
                expected_keyring_sha256=sha256_bytes(self.keyring.read_bytes()),
                expected_keys_inventory_sha256=sha256_bytes(canonical_json_bytes(
                    regular_file_inventory(self.keys))),
                selections=self.selections, token="observation-token")

    def test_exact_three_originals_join_signed_index_without_signing(self):
        self.assertEqual(3, len({row["producer"]["commit"]
            for row in self.selections.values()}))
        result = self._run()
        self.assertEqual(3, len(result["packages"]))
        for instance, selection in self.selections.items():
            self.assertEqual(selection["producer"],
                load_canonical_json_bytes((self.root / "custody" / instance.component /
                    "phase-receipt.json").read_bytes())["producer"])
        self.assertTrue((self.root / "custody/sdk-ios/stage/outputs/maven/payload.jar").is_file())
        self.assertTrue((self.root / "custody/custody.json").is_file())
        self.assertEqual(b"", (self.root / "custody/sdk-core/capture/worker.log").read_bytes())
        self.assertEqual(self.index.read_bytes(),
            (self.root / "custody/campaign/product-index.json").read_bytes())

    def test_wrong_original_receipt_fails_before_observation(self):
        self.selections[next(iter(_PACKAGES))]["receiptSha256"] = sha256_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "protected receipt/producer"):
            self._run()
        self.assertFalse((self.root / "custody").exists())

    def test_wrong_signed_output_fails_before_publication(self):
        instance = next(iter(_PACKAGES))
        entry = next(row for row in self.campaign["entries"] if row["component"] == instance.component
                     and row["phase"] == "package")
        entry["artifactSha256"] = sha256_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "artifact disagrees"):
            self._run()
        self.assertFalse((self.root / "custody").exists())

    def test_wrong_official_artifact_digest_fails_before_publication(self):
        def wrong_artifact(plan, destination, **options):
            observed = self._capture(plan, destination, **options)
            observed["artifact"]["digest"] = sha256_bytes(b"different official upload")
            return observed
        with patch("ci.sdk_phase10_maven_campaign.verify_release_product_index",
                   return_value=(self.campaign, self.index.read_bytes())), \
             patch("ci.sdk_phase10_maven_campaign.product_reuse._validate_plan",
                   side_effect=self._validate_plan), \
             patch("ci.sdk_phase10_maven_campaign.capture_sdk_maven_upload", side_effect=wrong_artifact), \
             patch("ci.sdk_phase10_maven_campaign.product_reuse.capture_sdk_ios_package_upload",
                   side_effect=wrong_artifact):
            with self.assertRaisesRegex(ValueError, "official package transport"):
                capture_sdk_phase10_maven_campaign(
                    SignedProductIndex(self.index, self.signature), self.root / "custody",
                    expected_index_sha256=sha256_bytes(self.index.read_bytes()),
                    expected_signature_sha256=sha256_bytes(self.signature.read_bytes()),
                    keyring_path=self.keyring, keys_directory=self.keys,
                    expected_keyring_sha256=sha256_bytes(self.keyring.read_bytes()),
                    expected_keys_inventory_sha256=sha256_bytes(canonical_json_bytes(
                        regular_file_inventory(self.keys))),
                    selections=self.selections, token="observation-token")
        self.assertFalse((self.root / "custody").exists())

    def test_wrong_independently_pinned_producer_fails_before_observation(self):
        self.selections[next(iter(_PACKAGES))]["producerSha256"] = sha256_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "protected receipt/producer"):
            self._run()
        self.assertFalse((self.root / "custody").exists())

    def test_wrong_per_package_original_plan_or_commit_fails_before_publication(self):
        instance = sorted(_PACKAGES)[0]
        selected = self.selections[instance]
        validated = self.validated_plans[Path(selected["repositoryRoot"])]
        for field in ("validationCommit", "validationTree"):
            with self.subTest(field=field):
                old = validated[field]
                validated[field] = "f" * 40
                try:
                    with self.assertRaisesRegex(ValueError, "original plan differs"):
                        self._run()
                    self.assertFalse((self.root / "custody").exists())
                finally:
                    validated[field] = old

    def test_late_caller_approval_mutation_fails_before_publication(self):
        original = self._capture
        def mutate_after_capture(plan, destination, **options):
            observed = original(plan, destination, **options)
            instance = next(instance for instance, selection in self.selections.items()
                if selection["receipt"] == str(options.get("receipt_path", options.get("package_receipt_path"))))
            self.selections[instance]["trustedWorkflowSha"] = "b" * 40
            return observed
        with patch("ci.sdk_phase10_maven_campaign.verify_release_product_index",
                   return_value=(self.campaign, self.index.read_bytes())), \
             patch("ci.sdk_phase10_maven_campaign.product_reuse._validate_plan",
                   side_effect=self._validate_plan), \
             patch("ci.sdk_phase10_maven_campaign.capture_sdk_maven_upload",
                   side_effect=mutate_after_capture), \
             patch("ci.sdk_phase10_maven_campaign.product_reuse.capture_sdk_ios_package_upload",
                   side_effect=mutate_after_capture):
            with self.assertRaisesRegex(ValueError, "changed during custody"):
                capture_sdk_phase10_maven_campaign(
                    SignedProductIndex(self.index, self.signature), self.root / "custody",
                    expected_index_sha256=sha256_bytes(self.index.read_bytes()),
                    expected_signature_sha256=sha256_bytes(self.signature.read_bytes()),
                    keyring_path=self.keyring, keys_directory=self.keys,
                    expected_keyring_sha256=sha256_bytes(self.keyring.read_bytes()),
                    expected_keys_inventory_sha256=sha256_bytes(canonical_json_bytes(
                        regular_file_inventory(self.keys))),
                    selections=self.selections, token="observation-token")
        self.assertFalse((self.root / "custody").exists())

    def test_missing_independent_upload_pin_fails_before_observation(self):
        self.selections[next(iter(_PACKAGES))].pop("artifactSha256")
        with self.assertRaisesRegex(ValueError, "exact protected fields"):
            self._run()
        self.assertFalse((self.root / "custody").exists())

    def test_wrong_original_object_fails_before_publication(self):
        instance = next(iter(_PACKAGES))
        object_file = next(self.shards[instance].rglob("*.zip"))
        object_file.chmod(0o644)
        object_file.write_bytes(b"substituted")
        with self.assertRaises(ValueError):
            self._run()
        self.assertFalse((self.root / "custody").exists())

    def test_non_61_or_development_index_is_not_campaign_authority(self):
        self.campaign["trustDomain"] = "development"
        with self.assertRaisesRegex(ValueError, "release-signed all-62"):
            self._run()
        self.campaign["trustDomain"] = "release"
        self.campaign["entries"].pop()
        with self.assertRaisesRegex(ValueError, "release-signed all-62"):
            self._run()


if __name__ == "__main__":
    unittest.main()
