"""SDK Phase-11 Maven forwarding retains Phase-10 signed bytes verbatim."""

from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from ci.products.inventory import (
    canonical_json_bytes, regular_file_inventory, sha256_bytes,
)
from ci.sdk_phase11_maven import forward_verified_sdk_phase10_maven
from ci.tests import test_sdk_phase10_maven_caller as fixture_module


class SdkPhase11MavenTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.SdkPhase10MavenCallerTest(
            methodName="test_exact_three_packages_survive_token_free_signing")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.landed = self.root / "landed"
        self.landed.mkdir()
        subprocess.run(["git", "init", "-q", str(self.landed)], check=True)
        subprocess.run(["git", "-C", str(self.landed), "-c", "user.name=SDK Test",
                        "-c", "user.email=sdk@example.invalid", "commit", "-q",
                        "--allow-empty", "-m", "landed fixture"], check=True)
        self.tree = subprocess.check_output(["git", "-C", str(self.landed),
            "rev-parse", "HEAD^{tree}"], text=True).strip()
        self.source_commit = "a" * 40
        self.fixture.signed_index["context"].update(
            commit=self.source_commit, tree=self.tree)
        self.fixture.index.write_bytes(canonical_json_bytes(self.fixture.signed_index))
        self.fixture.control["signedIndexSha256"] = sha256_bytes(
            self.fixture.index.read_bytes())
        self.fixture._write_control()
        self.preparation = self.fixture._prepare()["preparationSha256"]
        self.fixture._sign(self.preparation)
        self.signed = self.fixture.signed
        self.destination = self.root / "forwarded"
        self.pins = dict(landed_repository=self.landed,
            expected_signed_inventory_sha256=sha256_bytes(canonical_json_bytes(
                regular_file_inventory(self.signed))),
            expected_preparation_sha256=self.preparation,
            expected_control_sha256=self.fixture.control_sha,
            expected_pgp_key_sha256=self.fixture.control["pgpPublicKeySha256"],
            expected_signed_index_sha256=self.fixture.control["signedIndexSha256"],
            expected_sdk_version="0.8.0", expected_source_commit=self.source_commit,
            expected_source_tree=self.tree, expected_validation_tree=self.tree)

    def _forward(self, **changes):
        def verify_sidecars(stage, receipt, sidecars, public, key_sha):
            return {"component": Path(stage).parent.name,
                    "sidecarFiles": regular_file_inventory(sidecars)}
        with patch("ci.sdk_phase10_maven_caller.verify_release_product_index",
                   return_value=(self.fixture.signed_index, self.fixture.index.read_bytes())), \
             patch("ci.sdk_phase10_maven_caller.verify_sdk_phase10_maven",
                   side_effect=verify_sidecars):
            return forward_verified_sdk_phase10_maven(
                self.signed, self.destination, **{**self.pins, **changes})

    def test_exact_three_sidecar_sets_and_all_evidence_are_forwarded(self):
        original = regular_file_inventory(self.signed)
        result = self._forward()
        self.assertEqual(result["files"], original)
        self.assertEqual(regular_file_inventory(self.destination), original)
        self.assertEqual({"sdk-core", "sdk-android", "sdk-ios"},
            {item["component"] for item in result["uploadSources"]})
        for row in original:
            self.assertEqual((self.signed / row["relativePath"]).read_bytes(),
                             (self.destination / row["relativePath"]).read_bytes())

    def test_wrong_independent_inventory_stops_before_verification(self):
        with patch("ci.sdk_phase11_maven.verify_sdk_phase10_maven_handoff",
                   side_effect=AssertionError("verifier must not run")):
            with self.assertRaisesRegex(ValueError, "independent S1048 inventory"):
                self._forward(expected_signed_inventory_sha256=sha256_bytes(b"wrong"))
        self.assertFalse(self.destination.exists())

    def test_no_observation_or_signing_secret_enters_candidate_forwarder(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "token"}):
            with self.assertRaisesRegex(ValueError, "observation token"):
                self._forward()
        with patch.dict("os.environ", {"SIGNING_IN_MEMORY_KEY": "secret"}):
            with self.assertRaisesRegex(ValueError, "signing secret"):
                self._forward()
        self.assertFalse(self.destination.exists())

    def test_wrong_landed_tree_or_sdk_release_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "candidate landed tree"):
            self._forward(expected_source_tree="f" * 40,
                          expected_validation_tree="f" * 40)
        with self.assertRaisesRegex(ValueError, "approved source or SDK release"):
            self._forward(expected_sdk_version="0.8.1")
        self.assertFalse(self.destination.exists())

    def test_extra_symlink_and_late_mutation_never_publish(self):
        (self.signed / "unapproved-link").symlink_to("control.json")
        with self.assertRaises(ValueError):
            self._forward()
        (self.signed / "unapproved-link").unlink()
        from ci.sdk_phase11_maven import snapshot_regular_tree
        def mutate_after_snapshot(source, destination):
            snapshot_regular_tree(source, destination)
            sidecar = self.signed / "maven-sidecars/sdk-core/payload.asc"
            sidecar.write_bytes(sidecar.read_bytes() + b"late")
        with patch("ci.sdk_phase11_maven.snapshot_regular_tree",
                   side_effect=mutate_after_snapshot):
            with self.assertRaisesRegex(ValueError, "originals changed"):
                self._forward()
        self.assertFalse(self.destination.exists())


if __name__ == "__main__":
    unittest.main()
