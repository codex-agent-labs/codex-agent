"""Native semantic controls come only from exact independently pinned bytes."""

from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from ci.sdk_campaign_native_semantic_policy import load_native_semantic_policy
from products.inventory import canonical_json_bytes, sha256_bytes


def _policy():
    return {"schemaVersion": 1, "family": "native", "controls": {
        "repository": "/tmp/repository",
        "compatibility_request": "/tmp/compatibility.json",
        "runtime_stages": "/tmp/runtime",
        "staged_sdks": "/tmp/sdks",
        "tooling_evidence": "/tmp/tooling.json",
        "tooling_public_key": "/tmp/tooling.pub",
        "java_executable": "/tmp/java",
        "policy_revision": "reviewed-revision",
        "required_trust_domain": "development",
        "tooling_keyring": None,
        "tooling_keys_directory": None,
    }}


class NativeSemanticPolicyTest(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "native.json"

    def load(self, policy, *, digest=None):
        raw = canonical_json_bytes(policy)
        self.path.write_bytes(raw)
        return load_native_semantic_policy(self.path, digest or sha256_bytes(raw))

    def test_exact_typed_controls_and_bytes(self):
        policy = _policy()
        controls, raw = self.load(policy)
        self.assertEqual(raw, canonical_json_bytes(policy))
        self.assertEqual(set(controls), set(policy["controls"]))
        self.assertEqual(controls["repository"], Path("/tmp/repository"))
        self.assertEqual(controls["tooling_keyring"], None)
        self.assertEqual(controls["required_trust_domain"], "development")
        release = deepcopy(policy)
        release["controls"].update(required_trust_domain="release",
            tooling_keyring="/tmp/keys.json", tooling_keys_directory="/tmp/keys")
        controls, _ = self.load(release)
        self.assertEqual(controls["tooling_keyring"], Path("/tmp/keys.json"))

    def test_independent_digest_and_canonical_bytes(self):
        policy = _policy()
        with self.assertRaises(ValueError):
            self.load(policy, digest="sha256:" + "0" * 64)
        self.path.write_bytes(canonical_json_bytes(policy) + b"\n")
        with self.assertRaises(ValueError):
            load_native_semantic_policy(self.path, sha256_bytes(self.path.read_bytes()))

    def test_extra_observation_missing_control_and_wrong_types_fail(self):
        for mutation in ("observed", "missing", "bool-schema", "bad-path", "bad-text", "half-keys"):
            with self.subTest(mutation=mutation):
                policy = _policy()
                control = policy["controls"]
                if mutation == "observed":
                    control["observedTooling"] = "/tmp/observed"
                elif mutation == "missing":
                    del control["runtime_stages"]
                elif mutation == "bool-schema":
                    policy["schemaVersion"] = True
                elif mutation == "bad-path":
                    control["tooling_evidence"] = "/tmp/../observed"
                elif mutation == "bad-text":
                    control["policy_revision"] = "reviewed\nrevision"
                else:
                    control.update(required_trust_domain="release", tooling_keyring="/tmp/keys")
                with self.assertRaises(ValueError):
                    self.load(policy)

    def test_symlinked_policy_path_fails(self):
        raw = canonical_json_bytes(_policy())
        self.path.write_bytes(raw)
        link = self.path.parent / "linked.json"
        link.symlink_to(self.path)
        with self.assertRaises(ValueError):
            load_native_semantic_policy(link, sha256_bytes(raw))
