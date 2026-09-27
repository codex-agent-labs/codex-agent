"""Offline Phase-11 byte-forwarding checks; hosted S1048 pins remain external."""

from contextlib import contextmanager, redirect_stdout
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from ci import runtime_phase11_bytes as candidate
from ci.tests.test_products import phase_receipt
from products.inventory import (
    canonical_json_bytes, publish_regular_tree as actual_publish_regular_tree,
    regular_file_inventory, sha256_bytes,
)
from products.receipt import compute_build_key


_MANIFEST = b"original manifest\n"


class RuntimePhase11BytesTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.release = self.root / "protected-output"
        self.release.mkdir()
        receipt = phase_receipt("release")
        receipt.update(product="runtime", component="runtime-aggregate", phase="metadata", target="aggregate")
        receipt["buildKey"] = compute_build_key(
            product="runtime", component="runtime-aggregate", phase="metadata",
            target="aggregate", inputs=receipt["inputs"],
        )
        self.receipt_sha = sha256_bytes(canonical_json_bytes(receipt))
        self.build_key = receipt["buildKey"]
        metadata = self.release / "aggregate-input/metadata-receipt.json"
        metadata.parent.mkdir()
        metadata.write_bytes(canonical_json_bytes(receipt))
        self.payload = (self.release / "selected-inputs/predecessors/"
                        "runtime-runtime-aggregate-metadata-aggregate/stage/outputs")
        self.payload.mkdir(parents=True)
        (self.payload / "codex-agent-runtime-0.8.0-manifest.json").write_bytes(_MANIFEST)
        self.commit, self.tree, self.workflow = "a" * 40, "b" * 40, "c" * 40
        (self.release / "caller.json").write_bytes(canonical_json_bytes({
            "trustedSourceCommit": self.commit, "trustedSourceTree": self.tree,
            "trustedWorkflowSha": self.workflow,
        }))
        self.sidecars = self.root / "phase10-maven"
        self.sidecars.mkdir()
        (self.sidecars / "signature.asc").write_bytes(b"signature\n")
        self.policy = self.root / "product-policy"
        self.policy.mkdir()
        self.keyring = self.policy / "product-signing-keys.json"
        self.keyring.write_bytes(b"original keyring\n")
        self.keys = self.policy / "keys"
        self.keys.mkdir()
        (self.keys / "release.pub").write_bytes(b"original SSH public key\n")
        self.pgp_key = self.root / "pgp-public-key.asc"
        self.pgp_key.write_bytes(b"original PGP public key\n")
        self.destination = self.root / "candidate-input"

    def kwargs(self):
        return dict(
            expected_protected_inventory_sha256=candidate._tree_digest(self.release, allow_empty=True),
            expected_sidecar_inventory_sha256=candidate._tree_digest(self.sidecars),
            expected_metadata_receipt_sha256=self.receipt_sha,
            expected_build_key=self.build_key,
            expected_runtime_version="0.8.0",
            expected_manifest_sha256=sha256_bytes(_MANIFEST),
            expected_source_commit=self.commit,
            expected_source_tree=self.tree,
            expected_validation_tree=self.tree,
            expected_workflow_sha=self.workflow,
            landed_repository=self.root,
            keyring=self.keyring,
            expected_keyring_sha256=sha256_bytes(self.keyring.read_bytes()),
            keys_directory=self.keys,
            expected_keys_inventory_sha256=candidate._tree_digest(self.keys),
            pgp_public_key=self.pgp_key,
            expected_pgp_key_sha256=sha256_bytes(self.pgp_key.read_bytes()),
        )

    def cli_args(self, **changes):
        values = {"protected_output": self.release, "maven_sidecars": self.sidecars,
                  "destination": self.destination, **self.kwargs(), **changes}
        arguments = []
        for name, value in values.items():
            arguments.extend(["--" + name.replace("_", "-"), str(value)])
        return arguments

    def forward(self, _landed_trees=None, _cli=False, **changes):
        @contextmanager
        def verified(root, *, keyring, keys_directory):
            self.assertEqual(self.keyring.read_bytes(), keyring.read_bytes())
            self.assertEqual(regular_file_inventory(self.keys), regular_file_inventory(keys_directory))
            stage = root / "selected-inputs/predecessors/runtime-runtime-aggregate-metadata-aggregate/stage"
            yield {"originalPhases": {candidate._METADATA: {"stage": stage}},
                   "indexInputs": {"manifest": stage / "outputs/codex-agent-runtime-0.8.0-manifest.json"}}

        def verify(payload, manifest, sidecars, public_key, digest):
            self.assertEqual(b"original manifest\n", manifest.read_bytes())
            self.assertEqual(self.pgp_key.read_bytes(), public_key.read_bytes())
            self.assertEqual(digest, sha256_bytes(public_key.read_bytes()))
            self.assertEqual(regular_file_inventory(self.sidecars), regular_file_inventory(sidecars))
            return {"runtimeVersion": "0.8.0", "manifestSha256": sha256_bytes(manifest.read_bytes())}

        with patch.object(candidate, "_landed_tree",
                          side_effect=_landed_trees or (lambda _: self.tree)), \
                patch.object(candidate, "verified_runtime_aggregate_handoff", side_effect=verified) as full, \
                patch.object(candidate, "verify_runtime_phase10_maven", side_effect=verify) as maven:
            if _cli:
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(0, candidate.main(self.cli_args(**changes)))
                result = json.loads(output.getvalue())
            else:
                result = candidate.forward_verified_runtime_phase10_bytes(
                    self.release, self.sidecars, self.destination, **{**self.kwargs(), **changes},
                )
        full.assert_called_once()
        maven.assert_called_once()
        return result

    def test_forwards_only_original_bytes_plus_pinned_public_policy(self):
        result = self.forward()
        self.assertEqual("0.8.0", result["runtimeVersion"])
        self.assertEqual(regular_file_inventory(self.release, allow_empty=True),
                         regular_file_inventory(self.destination / "runtime-release", allow_empty=True))
        self.assertEqual(regular_file_inventory(self.sidecars),
                         regular_file_inventory(self.destination / "maven-sidecars"))
        self.assertEqual(self.keyring.read_bytes(),
                         (self.destination / "product-policy/product-signing-keys.json").read_bytes())
        self.assertEqual(self.pgp_key.read_bytes(),
                         (self.destination / "pgp-public-key.asc").read_bytes())

    def test_cli_requires_every_pin_and_copies_only_verified_bytes(self):
        with self.assertRaises(SystemExit) as missing:
            candidate.main(self.cli_args()[:-2])
        self.assertEqual(2, missing.exception.code)
        self.assertFalse(self.destination.exists())
        with patch.object(candidate, "_landed_tree", return_value=self.tree), \
                self.assertRaisesRegex(ValueError, "verifier key"):
            candidate.main(self.cli_args(expected_keyring_sha256=sha256_bytes(b"wrong keyring")))
        self.assertFalse(self.destination.exists())
        result = self.forward(_cli=True)
        self.assertEqual("runtime", result["product"])
        self.assertEqual(regular_file_inventory(self.release, allow_empty=True),
                         regular_file_inventory(self.destination / "runtime-release", allow_empty=True))
        self.assertEqual(regular_file_inventory(self.sidecars),
                         regular_file_inventory(self.destination / "maven-sidecars"))

    def test_retained_release_wrapper_preserves_original_and_current_context(self):
        retained = self.release / "retained-release"
        retained.mkdir()
        for name in ("aggregate-input", "selected-inputs"):
            (self.release / name).rename(retained / name)
        (self.release / "trust").mkdir()
        (self.release / "caller.json").write_bytes(canonical_json_bytes({
            "schemaVersion": 1, "target": "aggregate",
            "trustedSourceCommit": self.commit, "trustedSourceTree": self.tree,
            "trustedWorkflowSha": self.workflow,
            "transportProducer": {}, "authorizationReason": "fixture", "event": {},
            "environment": {}, "metadataReceiptSha256": self.receipt_sha,
            "releaseDirectory": "retained-release",
        }))
        selection = self.release / "selected-inputs/selection.json"
        selection.parent.mkdir(parents=True)
        selection.write_bytes(canonical_json_bytes({
            "target": "aggregate", "metadata": {
                "buildKey": self.build_key, "receiptSha256": self.receipt_sha,
            },
        }))
        self.forward()
        self.assertEqual(regular_file_inventory(self.release, allow_empty=True),
                         regular_file_inventory(self.destination / "runtime-release", allow_empty=True))

    def test_independent_byte_and_provenance_pins_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "independently selected bytes"):
            self.forward(expected_sidecar_inventory_sha256=sha256_bytes(b"other"))
        with self.assertRaisesRegex(ValueError, "caller provenance"):
            self.forward(expected_source_tree="d" * 40)
        with self.assertRaisesRegex(ValueError, "verifier key"):
            self.forward(expected_keyring_sha256=sha256_bytes(b"other"))
        with self.assertRaisesRegex(ValueError, "release identity"):
            self.forward(expected_runtime_version="0.8.1")
        with self.assertRaisesRegex(ValueError, "landed tree differs"):
            self.forward(expected_validation_tree="d" * 40)
        self.assertFalse(self.destination.exists())

    def test_landed_tree_requires_exact_checkout_root(self):
        with patch.object(candidate.subprocess, "run", return_value=SimpleNamespace(
            returncode=0, stdout=f"{self.root.parent}\n{self.tree}\n",
        )):
            with self.assertRaisesRegex(ValueError, "exact Git root"):
                candidate._landed_tree(self.root)

    def test_landed_tree_change_before_publication_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "landed tree changed during verification"):
            self.forward(_landed_trees=[self.tree, "d" * 40])
        self.assertFalse(self.destination.exists())

    def test_atomic_publication_is_last_material_step(self):
        real_publish = candidate.publish_regular_tree
        original = (self.sidecars / "signature.asc").read_bytes()

        def change_original_after_copy(source, destination, *, expected_inventory):
            real_publish(source, destination, expected_inventory=expected_inventory)
            (self.sidecars / "signature.asc").write_bytes(b"changed after copy\n")

        with patch.object(candidate, "publish_regular_tree", side_effect=change_original_after_copy):
            result = self.forward()
        self.assertEqual("runtime", result["product"])
        self.assertEqual(original, (self.destination / "maven-sidecars/signature.asc").read_bytes())

    def test_changed_verified_candidate_fails_before_publication(self):
        def mutate_before_copy(source, destination, *, expected_inventory):
            (source / "maven-sidecars/signature.asc").write_bytes(b"changed after verification\n")
            actual_publish_regular_tree(source, destination, expected_inventory=expected_inventory)

        with patch.object(candidate, "publish_regular_tree", side_effect=mutate_before_copy), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.forward()
        self.assertFalse(self.destination.exists())

    def test_verified_copy_mutation_fails_before_publication(self):
        @contextmanager
        def altered(root, *, keyring, keys_directory):
            stage = root / "selected-inputs/predecessors/runtime-runtime-aggregate-metadata-aggregate/stage"
            yield {"originalPhases": {candidate._METADATA: {"stage": stage}},
                   "indexInputs": {"manifest": stage / "outputs/codex-agent-runtime-0.8.0-manifest.json"}}

        def mutate(payload, manifest, sidecars, public_key, digest):
            (sidecars / "signature.asc").write_bytes(b"changed verified copy\n")
            return {"runtimeVersion": "0.8.0", "manifestSha256": sha256_bytes(_MANIFEST)}

        with patch.object(candidate, "_landed_tree", return_value=self.tree), \
                patch.object(candidate, "verified_runtime_aggregate_handoff", side_effect=altered), \
                patch.object(candidate, "verify_runtime_phase10_maven", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "Verified Runtime candidate bytes changed"):
            candidate.forward_verified_runtime_phase10_bytes(
                self.release, self.sidecars, self.destination, **self.kwargs(),
            )
        self.assertFalse(self.destination.exists())

    def test_transport_cannot_supply_verifier_policy_or_output_overwrite(self):
        transported = self.release / "transported-keyring.json"
        transported.write_bytes(self.keyring.read_bytes())
        with self.assertRaisesRegex(ValueError, "policy must be external"):
            self.forward(keyring=transported,
                         expected_protected_inventory_sha256=candidate._tree_digest(self.release, allow_empty=True))
        transported.unlink()
        self.forward()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.forward()


if __name__ == "__main__":
    unittest.main()
