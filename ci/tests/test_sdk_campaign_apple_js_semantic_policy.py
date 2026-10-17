"""Apple/JavaScript semantic controls come solely from exact pinned bytes."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ci.sdk_campaign_apple_js_semantic_policy import load_apple_js_semantic_policy
from products.inventory import canonical_json_bytes


_DIGEST = "sha256:" + "a" * 64


def _policy():
    apple_policy = {key: f"/caller/apple/{key}" for key in (
        "plan", "attestationPublicKey", "keyring", "keysDirectory", "toolingEvidence",
        "toolingPublicKey", "javaExecutable", "toolingKeyring", "toolingKeysDirectory")}
    apple_policy.update(attestationTrustDomain="release", toolingTrustDomain="release")
    targets = ("ios-arm64", "ios-simulator-arm64")
    javascript = {key: f"/caller/js/{key}" for key in (
        "repository", "compatibility_request", "package_receipt", "validation_receipt",
        "metadata_receipt", "contract_stage", "contract_receipt", "runtime_package_stage",
        "runtime_package_receipt", "runtime_validation_stage", "runtime_validation_receipt",
        "original_consumer_directory", "tooling_evidence", "tooling_public_key",
        "java_executable", "tooling_keyring", "tooling_keys_directory")}
    javascript.update(policy_revision="a" * 40, required_trust_domain="release")
    return {"schemaVersion": 1, "family": "apple-js",
        "apple": {"handoffs": {target: f"/caller/handoffs/{target}" for target in targets},
            "package_capture": "/caller/captures/package", "sdk_capture": "/caller/captures/sdk",
            "metadata_evidence_root": "/caller",
            "metadata_evidence_records": {target: {"receiptSha256": "sha256:" + character * 64,
                "target": target, "evidenceRoot": f"handoffs/{target}"}
                for target, character in zip(targets, "ab")},
            "repository": "/caller/repository", "policy_revision": "b" * 40,
            "policy": apple_policy}, "javascript": javascript}


class AppleJavaScriptSemanticPolicyTest(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "policy.json"

    def load(self, policy):
        self.path.write_bytes(canonical_json_bytes(policy))
        return load_apple_js_semantic_policy(self.path)

    def test_exact_controls_and_original_bytes(self):
        source = _policy()
        apple, javascript, raw = self.load(source)
        self.assertEqual(raw, canonical_json_bytes(source))
        self.assertEqual(apple["handoffs"]["ios-arm64"], Path("/caller/handoffs/ios-arm64"))
        self.assertEqual(apple["policy"], source["apple"]["policy"])
        self.assertEqual(javascript["contract_stage"], Path("/caller/js/contract_stage"))
        self.assertEqual(javascript["required_trust_domain"], "release")

    def test_missing_extra_and_wrong_typed_controls_fail(self):
        mutations = (
            lambda p: p["apple"].pop("sdk_capture"),
            lambda p: p["apple"].__setitem__("observedReceipt", _DIGEST),
            lambda p: p["apple"]["metadata_evidence_records"].__setitem__("other", {}),
            lambda p: p["apple"]["metadata_evidence_records"]["ios-arm64"].__setitem__("target", "ios-simulator-arm64"),
            lambda p: p["apple"]["metadata_evidence_records"]["ios-arm64"].__setitem__("receiptSha256", "sha256:" + "b" * 64),
            lambda p: p["javascript"].__setitem__("package_receipt", True),
            lambda p: p["javascript"].__setitem__("package_envelope", {}),
            lambda p: p.__setitem__("schemaVersion", True),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                policy = deepcopy(_policy())
                mutation(policy)
                with self.assertRaises(ValueError):
                    self.load(policy)

    def test_paths_and_trust_pair_fail_closed(self):
        for field, bad in (("repository", "relative"),
                           ("contract_stage", "/caller/../observed"),
                           ("tooling_keyring", None)):
            with self.subTest(field=field):
                policy = _policy()
                policy["javascript"][field] = bad
                with self.assertRaises(ValueError):
                    self.load(policy)
        policy = _policy()
        policy["apple"]["policy"]["toolingTrustDomain"] = "development"
        with self.assertRaises(ValueError):
            self.load(policy)

    def test_noncanonical_duplicate_and_symlinked_policy_fail(self):
        raw = canonical_json_bytes(_policy())
        for contents in (raw + b"\n", b'{"schemaVersion":1,"schemaVersion":1}'):
            self.path.write_bytes(contents)
            with self.assertRaises(ValueError):
                load_apple_js_semantic_policy(self.path)
        self.path.write_bytes(raw)
        shortcut = Path(self.temporary.name) / "shortcut"
        shortcut.symlink_to(self.path.parent, target_is_directory=True)
        with self.assertRaises(ValueError):
            load_apple_js_semantic_policy(shortcut / self.path.name)
