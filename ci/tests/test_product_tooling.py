"""Synthetic Git/CI/signing fixtures only; never hosted execution acceptance."""

from argparse import Namespace
import json
from pathlib import Path
from unittest import mock

from ci.receipt import create_receipt, INPUT_NAMES
from ci.products import inventory, tooling
from ci.products.inventory import regular_file_inventory
from ci.products.signatures import generate_development_key
from ci.products.tooling import JAR, build_development_tooling_attestation, verified_tooling_capture
from ci.tests.test_ci import GitFixture


class ToolingAttestationTest(GitFixture):
    def test_tooling_admission_policy_replans_without_changing_payload_keys(self):
        from ci.products.registry import PHASE_INSTANCE_IDS
        from ci.products.selection import classify_paths, phase_inventory_paths
        for path in ("ci/products/tooling.py", "ci/products/tooling_local.py"):
            self.assertEqual(set(PHASE_INSTANCE_IDS), set(classify_paths([path]).instances))
            for instance in PHASE_INSTANCE_IDS:
                self.assertEqual((), phase_inventory_paths([path], instance), (path, instance))

    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.original, self.plan_path, _ = self.make_plan("gradle/build-logic/src/main/kotlin/Tooling.kt")
        self.lane = self.root / "tooling-lane"
        jar = self.lane / JAR
        jar.parent.mkdir(parents=True)
        jar.write_bytes(b"synthetic original tooling, deliberately never executed\n")
        create_receipt(Namespace(
            plan=self.plan_path, lane="contracts", output=self.lane,
            workflow_path=".github/workflows/ci.yml", artifact_name="codex-agent-ci-contracts-fixture",
            run_id=101, run_attempt=2, runner=["os=synthetic-fixture", "arch=synthetic-fixture"],
            toolchain=["java=synthetic-fixture", "validationActions=build,metadata,test"],
            artifact=[f"{JAR}=release-tooling"], evidence=[],
        ))
        self.private, self.public, self.signing = generate_development_key(self.root / "keys")
        self.evidence = self.root / "external-tooling"

    def build(self, **overrides):
        args = dict(plan=self.plan_path, lane=self.lane, repository=self.root,
                    signing_metadata=self.signing, private_key=self.private,
                    public_key=self.public, output=self.evidence)
        args.update(overrides)
        return build_development_tooling_attestation(**args)

    def capture(self, **overrides):
        args = dict(evidence=self.evidence, repository=self.root, public_key=self.public,
                    required_trust_domain="development")
        args.update(overrides)
        return verified_tooling_capture(**args)

    def test_original_bytes_and_producer_preserved_in_private_verified_capture(self):
        original = regular_file_inventory(self.lane, allow_empty=True)
        plan = self.plan_path.read_bytes()
        self.build()
        before = regular_file_inventory(self.evidence, allow_empty=True)
        with self.capture() as jar:
            captured = jar
            self.assertEqual((self.lane / JAR).read_bytes(), jar.read_bytes())
            self.assertNotEqual(jar, self.lane / JAR)
        self.assertFalse(captured.exists())
        self.assertEqual(before, regular_file_inventory(self.evidence, allow_empty=True))
        self.assertEqual(original, regular_file_inventory(self.lane, allow_empty=True))
        self.assertEqual(plan, self.plan_path.read_bytes())
        self.assertEqual((self.lane / "lane-receipt.json").read_bytes(),
                         (self.evidence / "original/lane/lane-receipt.json").read_bytes())
        with self.assertRaises(ValueError):
            self.build()
        self.assertEqual(before, regular_file_inventory(self.evidence, allow_empty=True))

    def test_signature_payload_unknown_file_and_cross_key_tampering_fail_before_use(self):
        self.build()
        _, other_public, _ = generate_development_key(self.root / "other-keys")
        with self.assertRaises(ValueError), self.capture(public_key=other_public):
            self.fail("wrong key was admitted")
        for relative in ("release-tooling.attestation.json", "release-tooling.attestation.sig",
                         f"original/lane/{JAR}", "original/plan.json"):
            path = self.evidence / relative
            before = path.read_bytes()
            path.write_bytes(before + b"tamper")
            with self.subTest(relative=relative), self.assertRaises(ValueError), self.capture():
                self.fail("tampered original was admitted")
            path.write_bytes(before)
        extra = self.evidence / "extra"
        extra.write_text("not declared")
        with self.assertRaisesRegex(ValueError, "unexpected files"), self.capture():
            self.fail("extra file was admitted")

    def test_all_three_original_source_inventories_are_verified_against_git(self):
        for filename in INPUT_NAMES.values():
            lane_file = self.lane / filename
            plan_file = self.plan_path.parent / "inventories/contracts" / filename
            before = lane_file.read_bytes()
            lane_file.write_bytes(b"unrelated source\n")
            plan_file.write_bytes(lane_file.read_bytes())
            with self.subTest(filename=filename), self.assertRaisesRegex(ValueError, "source inventory mismatch"):
                self.build()
            self.assertFalse(self.evidence.exists())
            lane_file.write_bytes(before)
            plan_file.write_bytes(before)

    def test_development_cannot_claim_release_and_capture_cannot_be_mutated(self):
        with self.assertRaisesRegex(ValueError, "not development trust"):
            self.build(signing_metadata={**self.signing, "trustDomain": "release"})
        self.build()
        with self.assertRaisesRegex(ValueError, "not release trust"), self.capture(required_trust_domain="release"):
            self.fail("development evidence claimed release trust")
        before = regular_file_inventory(self.evidence, allow_empty=True)
        with self.assertRaisesRegex(ValueError, "changed during use"):
            with self.capture() as jar:
                jar.write_bytes(b"changed private executable")
        self.assertEqual(before, regular_file_inventory(self.evidence, allow_empty=True))

    def test_release_verification_requires_explicit_pinned_keyring_even_with_valid_signature(self):
        # Synthetic release-policy verification only, never protected signing or
        # hosted provenance acceptance. The public builder remains development-only.
        self.build()
        attestation = self.evidence / tooling.ATTESTATION
        value = json.loads(attestation.read_bytes())
        value["signing"]["trustDomain"] = "release"
        inventory.write_canonical_json(attestation, value)
        (self.evidence / tooling.SIGNATURE).unlink()
        tooling.sign_manifest(attestation, self.private, value["signing"])
        with self.assertRaisesRegex(ValueError, "caller-pinned"), \
                self.capture(required_trust_domain="release"):
            self.fail("signature without release policy was admitted")
        keys = self.root / "release-policy-keys"
        keys.mkdir()
        (keys / (self.signing["keyId"] + ".pub")).write_bytes(self.public.read_bytes())
        policy = self.root / "release-policy.json"
        record = {key: self.signing[key] for key in ("keyId", "fingerprint")}
        for retired in (False, True):
            inventory.write_canonical_json(policy, {
                "schemaVersion": 1, "namespace": self.signing["namespace"],
                "algorithm": self.signing["algorithm"], "trustDomain": "release",
                "activeKey": None if retired else record, "retiredKeys": [record] if retired else [],
            })
            with self.subTest(retired=retired), self.capture(required_trust_domain="release",
                                                            keyring=policy, keys_directory=keys) as jar:
                self.assertEqual((self.lane / JAR).read_bytes(), jar.read_bytes())
        (keys / (self.signing["keyId"] + ".pub")).write_bytes(b"wrong pinned key\n")
        with self.assertRaises(ValueError), self.capture(required_trust_domain="release",
                                                        keyring=policy, keys_directory=keys):
            self.fail("changed pinned policy was admitted")

    def test_duplicate_receipt_keys_symlinks_and_overlapping_output_fail_closed(self):
        receipt = self.lane / "lane-receipt.json"
        before = receipt.read_bytes()
        receipt.write_bytes(before.replace(b'{', b'{"result":"passed",', 1))
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            self.build()
        receipt.write_bytes(before)
        with self.assertRaisesRegex(ValueError, "overlaps"):
            self.build(output=self.lane / "nested")
        alias = self.lane / "alias"
        alias.symlink_to(self.lane / JAR)
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse(self.evidence.exists())

    def test_original_receipt_cannot_be_reissued_transport_or_wrong_artifact(self):
        receipt_path = self.lane / "lane-receipt.json"
        original = json.loads(receipt_path.read_bytes())
        for change in ("transport", "kind", "duplicate"):
            receipt = json.loads(json.dumps(original))
            if change == "transport":
                path = self.lane / "transport.json"
                path.write_bytes(b"synthetic retrieval record\n")
                receipt["evidence"].append({"relativePath": path.name, "kind": "transport-provenance",
                                            "sha256": inventory.sha256_bytes(path.read_bytes()).removeprefix("sha256:")})
            elif change == "kind":
                receipt["artifacts"][0]["kind"] = "not-release-tooling"
            else:
                receipt["artifacts"].append(dict(receipt["artifacts"][0]))
            receipt_path.write_text(json.dumps(receipt))
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.build()
            self.assertFalse(self.evidence.exists())
            if change == "transport":
                path.unlink()

    def test_source_inventory_mutation_during_signing_does_not_publish(self):
        path = self.plan_path.parent / "inventories/contracts" / next(iter(INPUT_NAMES.values()))
        sign = tooling.sign_manifest
        def mutate(*args, **kwargs):
            result = sign(*args, **kwargs)
            path.write_bytes(path.read_bytes() + b"changed source inventory\n")
            return result
        with mock.patch.object(tooling, "sign_manifest", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "changed during development attestation"):
            self.build()
        self.assertFalse(self.evidence.exists())

    def test_raw_empty_file_copy_is_explicit_and_default_product_rules_stay_strict(self):
        source = self.root / "empty-evidence"
        (source / "nested").mkdir(parents=True)
        (source / "nested/raw.stdout").write_bytes(b"")
        for windows in (False, True):
            for operation in (inventory.snapshot_regular_tree, inventory.publish_regular_tree):
                name = f"{operation.__name__}-{windows}"
                with self.subTest(windows=windows, operation=operation.__name__), \
                        mock.patch.object(inventory, "_is_windows", return_value=windows):
                    with self.assertRaisesRegex(ValueError, "empty"):
                        operation(source, self.root / f"strict-{name}")
                    destination = self.root / name
                    operation(source, destination, allow_empty=True)
                    self.assertEqual(b"", (destination / "nested/raw.stdout").read_bytes())
                    with self.assertRaises(ValueError):
                        operation(source, destination, allow_empty=True)
                    self.assertEqual(b"", (destination / "nested/raw.stdout").read_bytes())
