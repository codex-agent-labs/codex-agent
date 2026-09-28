"""SDK Maven protected custody and token-free signer handoff."""

from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from ci.products.index import SignedProductIndex
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, regular_file_inventory,
    sha256_bytes, snapshot_regular_tree, write_canonical_json,
)
from ci.products.receipt import compute_build_key, output_inventory_digest, write_output_manifest
from ci.products.restore import finalize_phase_object
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.sdk_phase10_maven_caller import (
    prepare_sdk_phase10_maven_handoff, sign_sdk_phase10_maven_handoff,
)
from ci.tests.test_products import phase_receipt, producer


class SdkPhase10MavenCallerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="sdk-maven-caller-", dir="/private/tmp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.index = self.root / "product-index.json"
        self.signature = self.root / "product-index.sig"
        self.keyring = self.root / "keyring.json"
        self.keys = self.root / "keys"
        self.keys.mkdir()
        self.plan = self.root / "impact-plan.json"
        self.original_root = self.root / "original-source"
        self.original_root.mkdir()
        self.receipts = self.root / "receipts"
        self.receipts.mkdir()
        self.public = self.root / "publication-pgp-public-key.asc"
        self.signing_home = self.root / "gnupg"
        self.signing_home.mkdir()
        for path, data in ((self.index, b"index\n"), (self.signature, b"signature\n"),
                           (self.keyring, b"keyring\n"), (self.keys / "release.pub", b"public\n"),
                           (self.plan, b"plan\n"), (self.public, b"pgp public\n")):
            path.write_bytes(data)
        original = {**producer(), "workflowPath": ".github/workflows/ci.yml"}
        packages = []
        self.captures = {}
        self.campaign_entries = []
        for number, (component, target) in enumerate((
                ("sdk-core", "common"), ("sdk-android", "android"), ("sdk-ios", "ios")), 1):
            source = self.root / (component + "-source")
            source.mkdir()
            output = source / "outputs/maven/payload.jar"
            output.parent.mkdir(parents=True)
            output.write_bytes(component.encode())
            write_output_manifest(source, "sdk", component, "package", target,
                                  "0.8.0", {"maven": "outputs/maven"})
            inputs = phase_receipt()["inputs"]
            inputs["versionIdentity"] = "0.8.0"
            build_key = compute_build_key(product="sdk", component=component,
                phase="package", target=target, inputs=inputs)
            shard = self.root / (component + "-shard")
            verified = finalize_phase_object(stage_root=source,
                phase_plan={"schemaVersion": 1, "product": "sdk", "component": component,
                    "phase": "package", "target": target, "buildKey": build_key, "inputs": inputs},
                producer=original, product_version="0.8.0", trust_domain="development",
                destination=shard)
            receipt = verified["receiptBytes"]
            (self.receipts / (component + ".json")).write_bytes(receipt)
            capture = self.root / (component + "-capture")
            capture.mkdir()
            original_files = capture / "original"
            original_files.mkdir()
            snapshot_regular_tree(shard, original_files / "shard")
            if component != "sdk-ios":
                for directory in ("worker", "selection", "inputs", "sdk-inputs-original",
                                  "binary-contract-original", "binary-original"):
                    (original_files / directory).mkdir()
                    (original_files / directory / "marker").write_bytes(b"marker\n")
            (capture / "plan").mkdir()
            (capture / "plan/impact-plan.json").write_bytes(self.plan.read_bytes())
            archive = capture / "transport.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output_zip:
                for path in sorted(original_files.rglob("*")):
                    if path.is_file():
                        output_zip.write(path, path.relative_to(original_files).as_posix())
            artifact_digest = sha256_bytes(archive.read_bytes())
            artifact = {"id": number, "digest": artifact_digest,
                "name": f"codex-agent-sdk-worker-{component}-package-{target}-"
                        f"{build_key.removeprefix('sha256:')}-{original['tree']}-attempt-{original['runAttempt']}"}
            write_canonical_json(capture / "capture-transport.json", {
                "artifact": artifact, "captureProducer": original,
                "observed": [], "packageReceiptSha256": sha256_bytes(receipt)})
            self.captures[component] = (capture, verified)
            packages.append({"component": component, "target": target,
                "receiptSha256": sha256_bytes(receipt), "producer": original,
                "producerSha256": sha256_bytes(canonical_json_bytes(original)),
                "artifactId": number, "artifactSha256": artifact_digest,
                "trustedWorkflowSha": "a" * 40})
        for instance in sorted(SDK_CAMPAIGN_INSTANCES):
            entry = {"product": instance.product, "component": instance.component,
                     "phase": instance.phase, "target": instance.target,
                     "productVersion": "0.8.0"}
            if instance.component in self.captures and instance.phase == "package":
                receipt = self.captures[instance.component][1]["receipt"]
                entry.update(buildKey=receipt["buildKey"],
                    receiptSha256=sha256_bytes(self.captures[instance.component][1]["receiptBytes"]),
                    outputs=receipt["outputs"],
                    outputInventoryDigest=output_inventory_digest(receipt["outputs"]),
                    artifactName=receipt["outputs"][0]["relativePath"],
                    artifactSha256=receipt["outputs"][0]["sha256"])
            self.campaign_entries.append(entry)
        self.control = {"schemaVersion": 1,
            "signedIndexSha256": sha256_bytes(self.index.read_bytes()),
            "signatureSha256": sha256_bytes(self.signature.read_bytes()),
            "keyringSha256": sha256_bytes(self.keyring.read_bytes()),
            "keysInventorySha256": sha256_bytes(canonical_json_bytes(regular_file_inventory(self.keys))),
            "planSha256": sha256_bytes(self.plan.read_bytes()),
            "pgpPublicKeySha256": sha256_bytes(self.public.read_bytes()), "packages": packages}
        self.signed_index = {"repository": "codex-agent-labs/codex-agent",
            "trustDomain": "release", "context": {"kind": "pull-request", "pullRequest": 31},
            "entries": self.campaign_entries}
        self.control_path = self.root / "control.json"
        self._write_control()
        self.prepared = self.root / "prepared"
        self.signed = self.root / "signed"

    def _write_control(self):
        write_canonical_json(self.control_path, self.control)
        self.control_sha = sha256_bytes(self.control_path.read_bytes())

    def _capture(self, _index, destination, **options):
        destination = Path(destination)
        campaign = destination / "campaign"
        campaign.mkdir(parents=True)
        for source, name in ((self.index, "product-index.json"),
                             (self.signature, "product-index.sig"),
                             (self.keyring, "product-signing-keys.json")):
            (campaign / name).write_bytes(source.read_bytes())
        snapshot_regular_tree(self.keys, campaign / "keys")
        records = []
        for row in self.control["packages"]:
            component = row["component"]
            original = destination / component
            stage = original / "stage"
            restored_source = self.root / (component + "-source")
            snapshot_regular_tree(restored_source, stage)
            (original / "phase-receipt.json").write_bytes(
                (self.receipts / (component + ".json")).read_bytes())
            snapshot_regular_tree(self.captures[component][0], original / "capture")
            records.append({"component": component, "target": row["target"],
                "receiptSha256": row["receiptSha256"],
                "producerSha256": row["producerSha256"],
                "artifactId": row["artifactId"], "artifactSha256": row["artifactSha256"],
                "objectSha256": self.captures[component][1]["objectSha256"],
                "stageFiles": regular_file_inventory(stage)})
        write_canonical_json(destination / "custody.json", {"schemaVersion": 1,
            "product": "sdk", "signedIndexSha256": self.control["signedIndexSha256"],
            "signedIndexSignatureSha256": self.control["signatureSha256"],
            "packages": records})
        return {"packages": records}

    def _prepare(self):
        with patch("ci.sdk_phase10_maven_caller.capture_sdk_phase10_maven_campaign",
                   side_effect=self._capture):
            return prepare_sdk_phase10_maven_handoff(
                self.control_path, self.prepared,
                approved_control_sha256=self.control_sha,
                signed_index=SignedProductIndex(self.index, self.signature),
                keyring=self.keyring, keys_directory=self.keys,
                original_plan=self.plan, original_root=self.original_root,
                receipts_directory=self.receipts, pgp_public_key=self.public,
                token="observation-token")

    def _sign(self, digest, *, control_sha=None):
        def fake_sign(stage, receipt, sidecars, public, key_sha, home, fingerprint, passphrase):
            Path(sidecars).mkdir()
            (Path(sidecars) / "payload.asc").write_bytes(Path(receipt).read_bytes())
            return {"component": Path(stage).parent.name,
                    "sidecarFiles": regular_file_inventory(sidecars)}
        with patch("ci.sdk_phase10_maven_caller.verify_release_product_index",
                   return_value=(self.signed_index, self.index.read_bytes())), \
             patch("ci.sdk_phase10_maven_caller.produce_sdk_phase10_maven_sidecars",
                   side_effect=fake_sign):
            return sign_sdk_phase10_maven_handoff(
                self.prepared, self.signed,
                expected_preparation_sha256=digest,
                expected_control_sha256=self.control_sha if control_sha is None else control_sha,
                expected_pgp_key_sha256=self.control["pgpPublicKeySha256"],
                signing_home=self.signing_home, signing_fingerprint="A" * 40,
                passphrase="passphrase")

    def test_exact_three_packages_survive_token_free_signing(self):
        prepared = self._prepare()
        result = self._sign(prepared["preparationSha256"])
        self.assertEqual(3, len(result["packages"]))
        for row in self.control["packages"]:
            self.assertEqual((self.receipts / (row["component"] + ".json")).read_bytes(),
                (self.signed / "maven-sidecars" / row["component"] / "payload.asc").read_bytes())
        self.assertEqual(self.index.read_bytes(),
            (self.signed / "custody/campaign/product-index.json").read_bytes())

    def test_signed_campaign_repository_or_pr_cannot_disagree_with_originals(self):
        digest = self._prepare()["preparationSha256"]
        for field, value in (("repository", "other/repository"), ("pullRequest", 32)):
            with self.subTest(field=field):
                target = self.signed_index if field == "repository" else self.signed_index["context"]
                previous = target[field]
                target[field] = value
                try:
                    with self.assertRaisesRegex(ValueError, "held campaign"):
                        self._sign(digest)
                    self.assertFalse(self.signed.exists())
                finally:
                    target[field] = previous

    def test_unapproved_or_mutated_control_stops_before_capture(self):
        self.control["packages"][0]["artifactId"] = 999
        self._write_control()
        with patch("ci.sdk_phase10_maven_caller.capture_sdk_phase10_maven_campaign") as capture:
            with self.assertRaisesRegex(ValueError, "independent approval"):
                prepare_sdk_phase10_maven_handoff(
                    self.control_path, self.prepared,
                    approved_control_sha256=sha256_bytes(b"different"),
                    signed_index=SignedProductIndex(self.index, self.signature),
                    keyring=self.keyring, keys_directory=self.keys,
                    original_plan=self.plan, original_root=self.original_root,
                    receipts_directory=self.receipts, pgp_public_key=self.public,
                    token="token")
            capture.assert_not_called()

    def test_modified_preparation_or_token_stops_before_signing(self):
        digest = self._prepare()["preparationSha256"]
        with patch.dict("os.environ", {"GITHUB_TOKEN": "token"}):
            with self.assertRaisesRegex(ValueError, "observation token"):
                self._sign(digest)
        (self.prepared / "custody/sdk-core/stage/payload.bin").write_bytes(b"modified")
        with patch("ci.sdk_phase10_maven_caller.produce_sdk_phase10_maven_sidecars") as sign:
            with self.assertRaisesRegex(ValueError, "preparation inventory"):
                self._sign(digest)
            sign.assert_not_called()

    def test_self_consistent_custody_provenance_cannot_replace_independent_upload_pin(self):
        self._prepare()
        custody = self.prepared / "custody/custody.json"
        transport = self.prepared / "custody/sdk-core/capture/capture-transport.json"
        record = load_canonical_json_bytes(custody.read_bytes())
        observed = load_canonical_json_bytes(transport.read_bytes())
        changed_digest = sha256_bytes(b"forged upload")
        record["packages"][0]["artifactId"] = 999
        record["packages"][0]["artifactSha256"] = changed_digest
        observed["artifact"]["id"] = 999
        observed["artifact"]["digest"] = changed_digest
        write_canonical_json(custody, record)
        write_canonical_json(transport, observed)
        preparation = self.prepared / "preparation.json"
        control = load_canonical_json_bytes(preparation.read_bytes())
        control["preparedFiles"] = [entry for entry in regular_file_inventory(self.prepared)
            if entry["relativePath"] != "preparation.json"]
        write_canonical_json(preparation, control)
        with patch("ci.sdk_phase10_maven_caller.produce_sdk_phase10_maven_sidecars") as sign:
            with self.assertRaisesRegex(ValueError, "held package differs"):
                self._sign(sha256_bytes(preparation.read_bytes()))
            sign.assert_not_called()

    def test_preparation_cannot_choose_its_own_control_authority(self):
        digest = self._prepare()["preparationSha256"]
        with patch("ci.sdk_phase10_maven_caller.produce_sdk_phase10_maven_sidecars") as sign:
            with self.assertRaisesRegex(ValueError, "preparation inventory"):
                self._sign(digest, control_sha=sha256_bytes(b"unapproved control"))
            sign.assert_not_called()

    def test_secret_in_observation_process_fails(self):
        with patch.dict("os.environ", {"SIGNING_IN_MEMORY_KEY": "secret"}):
            with self.assertRaisesRegex(ValueError, "signing secrets"):
                self._prepare()
        self.assertFalse(self.prepared.exists())


if __name__ == "__main__":
    unittest.main()
