"""Release-index reuse of original native Runtime receipts; no hosted/native execution."""

from __future__ import annotations

import copy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import ci.products.reuse as reuse_module
from ci.products.index import (
    IndexEntrySource,
    release_attested_runtime_variant_admission,
    write_signed_product_index,
)
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    write_canonical_json,
)
from ci.products.receipt import validate_phase_receipt
from ci.products.restore import store_local_object
from ci.products.reuse import LookupSession, RemoteCatalog, ReuseLookupError
from ci.products.runtime_attestation import build_runtime_variant_attestation
from ci.products.runtime_variant import produce_runtime_variant
from ci.products.signatures import generate_development_key
from ci.tests.test_product_runtime_variant import (
    Fixture,
    TARGET,
    _attestation_paths,
    _write_metadata_receipt,
)


PHASES = ("binary", "package", "validation", "metadata")


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class NativeRuntimeReleaseReuseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="runtime-release-reuse-")
        cls.root = Path(cls.temporary.name).resolve()
        cls.private_key, cls.public_key, cls.development = generate_development_key(
            cls.root / "keys",
        )
        cls.release_signing = {
            **cls.development,
            "trustDomain": "release",
            "keyId": "runtime-release-fixture",
        }
        cls.release_keys = cls.root / "release-keys"
        cls.release_keys.mkdir()
        (cls.release_keys / "runtime-release-fixture.pub").write_bytes(
            cls.public_key.read_bytes(),
        )
        cls.keyring = cls.root / "product-signing-keys.json"
        write_canonical_json(cls.keyring, {
            "schemaVersion": 1,
            "namespace": cls.release_signing["namespace"],
            "algorithm": cls.release_signing["algorithm"],
            "trustDomain": "release",
            "activeKey": {
                "keyId": cls.release_signing["keyId"],
                "fingerprint": cls.release_signing["fingerprint"],
            },
            "retiredKeys": [],
        })

        cls.fixture = Fixture(
            cls.root / "variant-inputs",
            cls.private_key,
            cls.public_key,
            cls.development,
        )
        cls.variant = produce_runtime_variant(**cls.fixture.arguments())["bundlePath"]
        cls.receipt_paths = dict(cls.fixture.receipt_paths)
        cls.receipt_paths["metadata"] = _write_metadata_receipt(cls.fixture, cls.variant)
        cls.receipts = {
            phase: validate_phase_receipt(load_canonical_json_bytes(path.read_bytes()))
            for phase, path in cls.receipt_paths.items()
        }

        cls.runtime_stages = cls.root / "runtime-stages"
        cls.validation_evidence = (
            cls.runtime_stages
            / TARGET
            / "validation/outputs/native/desktop-runtime-linuxX64.json"
        )
        cls.validation_evidence.parent.mkdir(parents=True)
        cls.validation_evidence.write_bytes(cls.fixture.validation.read_bytes())

        cls.attestation_root = cls.root / "release-attestation"
        build_runtime_variant_attestation(
            cls.variant,
            cls.receipt_paths["binary"],
            cls.receipt_paths["package"],
            cls.receipt_paths["validation"],
            cls.receipt_paths["metadata"],
            cls.validation_evidence,
            cls.release_signing,
            cls.private_key,
            cls.public_key,
            cls.attestation_root,
            keyring=cls.keyring,
            keys_directory=cls.release_keys,
        )
        cls.attestation, cls.signature = _attestation_paths(
            cls.variant,
            cls.attestation_root,
        )
        cls.development_attestation_root = cls.root / "development-attestation"
        build_runtime_variant_attestation(
            cls.variant,
            cls.receipt_paths["binary"],
            cls.receipt_paths["package"],
            cls.receipt_paths["validation"],
            cls.receipt_paths["metadata"],
            cls.validation_evidence,
            cls.development,
            cls.private_key,
            cls.public_key,
            cls.development_attestation_root,
        )

        payloads = {
            "binary/libcodex_agent.so": b"runtime library\n",
            f"outputs/app-server/{cls.fixture.app_server.name}": cls.fixture.app_server.read_bytes(),
            "outputs/c-abi/codex-agent-c.zip": cls.fixture.c_abi.read_bytes(),
            "outputs/c-abi-reference/include/codex_agent.h": cls.fixture.header,
            "outputs/validation-runner/runner.zip": b"runner\n",
            "outputs/c-abi/reference.txt": b"reference\n",
            "outputs/native/validation.json": cls.fixture.validation.read_bytes(),
            "outputs/native/other.json": b"other\n",
            f"outputs/{cls.variant.name}": cls.variant.read_bytes(),
        }
        cache = cls.root / "objects"
        objects = {}
        sources = []
        admission_arguments = {
            "payload": cls.variant,
            "binary_receipt": cls.receipt_paths["binary"],
            "package_receipt": cls.receipt_paths["package"],
            "validation_receipt": cls.receipt_paths["validation"],
            "metadata_receipt": cls.receipt_paths["metadata"],
            "validation_evidence": cls.validation_evidence,
            "attestation": cls.attestation,
            "signature": cls.signature,
            "public_key": cls.public_key,
            "keyring": cls.keyring,
            "keys_directory": cls.release_keys,
        }
        for phase in PHASES:
            receipt = cls.receipts[phase]
            stage = cls.root / "object-stages" / phase
            stage.mkdir(parents=True)
            for output in receipt["outputs"]:
                contents = payloads[output["relativePath"]]
                if len(contents) != output["bytes"] or sha256_bytes(contents) != output["sha256"]:
                    raise AssertionError(f"Runtime {phase} fixture output differs from its receipt")
                path = stage / output["relativePath"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(contents)
            write_canonical_json(stage / "output-manifest.json", {
                "schemaVersion": 1,
                **{field: receipt[field] for field in (
                    "product", "component", "phase", "target", "productVersion",
                )},
                "outputs": receipt["outputs"],
            })
            stored = store_local_object(stage, cls.receipt_paths[phase], cache)
            objects[receipt["buildKey"]] = stored["path"]
            source = IndexEntrySource(
                cls.receipt_paths[phase].read_bytes(),
                receipt["outputs"][0]["relativePath"],
            )
            admission = release_attested_runtime_variant_admission(
                source,
                **admission_arguments,
            )
            sources.append(IndexEntrySource(
                source.receipt_bytes,
                source.artifact_path,
                admission,
            ))

        cls.catalog_root = cls.root / "catalog"
        cls.catalog_root.mkdir()
        cls.catalog_manifest = cls.catalog_root / "product-index.json"
        write_signed_product_index(
            sources,
            repository="owner/repository",
            context={
                "kind": "promoted-main",
                "commit": "c" * 40,
                "tree": "d" * 40,
                "promotionRunId": 19,
                "promotionRunAttempt": 2,
            },
            trust_domain="release",
            signing=cls.release_signing,
            producer={
                "repository": "owner/repository",
                "workflowPath": ".github/workflows/products.yml",
                "commit": "c" * 40,
                "tree": "d" * 40,
                "event": "push",
                "runId": 19,
                "runAttempt": 2,
                "pullRequest": None,
            },
            stable_history=None,
            private_key=cls.private_key,
            public_key=cls.public_key,
            manifest_path=cls.catalog_manifest,
        )
        cls.catalog = RemoteCatalog(
            cls.catalog_manifest,
            cls.catalog_manifest.with_suffix(".sig"),
            objects,
            keyring=cls.keyring,
            keys_directory=cls.release_keys,
        )
        cls.validation_digest = sha256_file(cls.receipt_paths["validation"])
        # Transported trust paths are intentionally bogus. Lookup must use only
        # the release catalog's caller-pinned keyring above.
        cls.runtime_evidence = {
            "target": TARGET,
            "stageRoot": str(cls.runtime_stages),
            "phaseReceipts": {
                phase: str(path) for phase, path in cls.receipt_paths.items()
            },
            "payload": str(cls.variant),
            "attestation": str(cls.attestation),
            "attestationSignature": str(cls.signature),
            "publicKey": str(cls.public_key),
            "keyring": str(cls.root / "transported-bogus-keyring.json"),
            "keysDirectory": str(cls.root / "transported-bogus-keys"),
        }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    @classmethod
    def session(cls, evidence=None, catalog=None) -> LookupSession:
        return LookupSession(
            repository="owner/repository",
            pull_request=31,
            promoted_main=cls.catalog if catalog is None else catalog,
            native_runtime_evidence=(
                {cls.validation_digest: ({}, cls.runtime_evidence)}
                if evidence is None else evidence
            ),
            restore_root=cls.root / "restore",
        )

    def test_release_catalog_reuses_all_original_native_runtime_phase_receipts(self) -> None:
        originals = {
            path: path.read_bytes()
            for path in (
                *self.receipt_paths.values(),
                self.variant,
                self.validation_evidence,
                self.attestation,
                self.signature,
                self.public_key,
            )
        }
        session = self.session()
        for phase in PHASES:
            with self.subTest(phase=phase):
                result = session.lookup("promoted-main", self.receipts[phase])
                self.assertIsNone(result.reason)
                self.assertEqual(self.receipt_paths[phase].read_bytes(), result.envelope["receiptBytes"])
                self.assertEqual(self.receipts[phase]["producer"], result.envelope["receipt"]["producer"])
        self.assertEqual(originals, {path: path.read_bytes() for path in originals})

    def test_release_catalog_rejects_missing_crosspaired_target_signature_and_key_authority(self) -> None:
        binary = self.receipts["binary"]
        changed = []
        changed.append(("missing", {}))

        wrong_target = copy.deepcopy(self.runtime_evidence)
        wrong_target["target"] = "linux-arm64"
        changed.append(("wrong-target", {self.validation_digest: ({}, wrong_target)}))

        crosspaired = copy.deepcopy(self.runtime_evidence)
        crosspaired["phaseReceipts"]["binary"] = crosspaired["phaseReceipts"]["metadata"]
        changed.append(("cross-paired-phase", {self.validation_digest: ({}, crosspaired)}))

        wrong_metadata = copy.deepcopy(self.runtime_evidence)
        wrong_metadata["phaseReceipts"]["metadata"] = wrong_metadata["phaseReceipts"]["binary"]
        changed.append(("cross-paired-metadata", {self.validation_digest: ({}, wrong_metadata)}))

        changed.append((
            "wrong-validation-map-key",
            {sha256_bytes(b"wrong validation receipt"): ({}, self.runtime_evidence)},
        ))

        development_signature = copy.deepcopy(self.runtime_evidence)
        development_attestation, development_signature_path = _attestation_paths(
            self.variant,
            self.development_attestation_root,
        )
        development_signature["attestation"] = str(development_attestation)
        development_signature["attestationSignature"] = str(development_signature_path)
        changed.append((
            "development-signature",
            {self.validation_digest: ({}, development_signature)},
        ))

        for name, evidence in changed:
            with self.subTest(name=name), self.assertRaisesRegex(
                ReuseLookupError,
                "matching object or index entry is corrupt",
            ):
                self.session(evidence=evidence).lookup("promoted-main", binary)

        bogus_keyring = self.root / "bogus-caller-keyring.json"
        bogus_keyring.write_bytes(canonical_json_bytes({}))
        bogus_keys = self.root / "bogus-caller-keys"
        bogus_keys.mkdir()
        with self.assertRaises(ValueError):
            self.session(catalog=RemoteCatalog(
                self.catalog.manifest,
                self.catalog.signature,
                self.catalog.objects,
                keyring=bogus_keyring,
                keys_directory=bogus_keys,
            ))

    def test_release_catalog_freezes_original_receipts_before_full_attestation_admission(self) -> None:
        original_metadata = self.receipt_paths["metadata"].read_bytes()
        with tempfile.TemporaryDirectory(prefix="runtime-release-swap-", dir=self.root) as temporary:
            root = Path(temporary).resolve()
            changed = copy.deepcopy(self.receipts["metadata"])
            changed["producer"] = {
                **changed["producer"],
                "commit": "e" * 40,
                "tree": "f" * 40,
                "runId": changed["producer"]["runId"] + 100,
            }
            changed_path = root / "metadata-receipt.json"
            write_canonical_json(changed_path, changed)
            changed_attestation_root = root / "attestation"
            build_runtime_variant_attestation(
                self.variant,
                self.receipt_paths["binary"],
                self.receipt_paths["package"],
                self.receipt_paths["validation"],
                changed_path,
                self.validation_evidence,
                self.release_signing,
                self.private_key,
                self.public_key,
                changed_attestation_root,
                keyring=self.keyring,
                keys_directory=self.release_keys,
            )
            changed_attestation, changed_signature = _attestation_paths(
                self.variant,
                changed_attestation_root,
            )
            real_admission = release_attested_runtime_variant_admission

            def swap_after_selection(source, **arguments):
                self.receipt_paths["metadata"].write_bytes(changed_path.read_bytes())
                return real_admission(
                    source,
                    **{
                        **arguments,
                        "attestation": changed_attestation,
                        "signature": changed_signature,
                    },
                )

            try:
                with mock.patch.object(
                    reuse_module,
                    "release_attested_runtime_variant_admission",
                    side_effect=swap_after_selection,
                ), self.assertRaisesRegex(
                    ReuseLookupError,
                    "matching object or index entry is corrupt",
                ) as failure:
                    self.session().lookup("promoted-main", self.receipts["binary"])
                self.assertIn("does not bind its exact payload and receipts", str(failure.exception.__cause__))
            finally:
                self.receipt_paths["metadata"].write_bytes(original_metadata)
        self.assertEqual(original_metadata, self.receipt_paths["metadata"].read_bytes())

    def alternative_policy(self, root: Path):
        private, public, development = generate_development_key(root / "key")
        signing = {**development, "trustDomain": "release", "keyId": self.release_signing["keyId"]}
        keys = root / "public-keys"
        keys.mkdir()
        (keys / f"{signing['keyId']}.pub").write_bytes(public.read_bytes())
        keyring = root / "keyring.json"
        write_canonical_json(keyring, {
            "schemaVersion": 1, "namespace": signing["namespace"], "algorithm": signing["algorithm"],
            "trustDomain": "release", "activeKey": {
                "keyId": signing["keyId"], "fingerprint": signing["fingerprint"],
            }, "retiredKeys": [],
        })
        return private, public, signing, keyring, keys

    def test_catalog_policy_swap_rejects_independently_valid_other_key_attestation(self) -> None:
        originals = {path: path.read_bytes() for path in (*self.receipt_paths.values(), self.variant)}
        with tempfile.TemporaryDirectory(prefix="native-unrelated-policy-") as temporary:
            root = Path(temporary).resolve()
            private, public, signing, keyring, keys = self.alternative_policy(root)
            attestation_root = root / "attestation"
            build_runtime_variant_attestation(
                self.variant, *(self.receipt_paths[phase] for phase in PHASES), self.validation_evidence,
                signing, private, public, attestation_root, keyring=keyring, keys_directory=keys)
            attestation, signature = _attestation_paths(self.variant, attestation_root)
            # B is independently valid for the exact original product/receipts.
            # Only the A-signed catalog prevents its use in this lookup session.
            release_attested_runtime_variant_admission(
                IndexEntrySource(self.receipt_paths["binary"].read_bytes(),
                                 self.receipts["binary"]["outputs"][0]["relativePath"]),
                payload=self.variant,
                **{f"{phase}_receipt": path for phase, path in self.receipt_paths.items()},
                validation_evidence=self.validation_evidence, attestation=attestation, signature=signature,
                public_key=public, keyring=keyring, keys_directory=keys)
            runtime = {**self.runtime_evidence, "attestation": str(attestation),
                       "attestationSignature": str(signature), "publicKey": str(public)}
            evidence = {self.validation_digest: ({}, runtime)}
            sessions = {phase: self.session(evidence) for phase in PHASES}
            caller_public = self.release_keys / f"{self.release_signing['keyId']}.pub"
            original_policy, original_public = self.keyring.read_bytes(), caller_public.read_bytes()
            try:
                self.keyring.write_bytes(keyring.read_bytes())
                caller_public.write_bytes(public.read_bytes())
                for phase, session in sessions.items():
                    with self.subTest(phase=phase), self.assertRaises(ReuseLookupError):
                        session.lookup("promoted-main", self.receipts[phase])
            finally:
                self.keyring.write_bytes(original_policy)
                caller_public.write_bytes(original_public)
        self.assertEqual(originals, {path: path.read_bytes() for path in originals})

    def test_late_policy_change_cannot_replace_private_native_admission_policy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="native-late-policy-") as temporary:
            _, public, _, keyring, _ = self.alternative_policy(Path(temporary).resolve())
            caller_public = self.release_keys / f"{self.release_signing['keyId']}.pub"
            original_policy, original_public = self.keyring.read_bytes(), caller_public.read_bytes()

            def late_swap(source, **arguments):
                self.assertNotEqual(self.keyring, arguments["keyring"])
                self.assertNotEqual(self.release_keys, arguments["keys_directory"])
                self.assertEqual(original_policy, arguments["keyring"].read_bytes())
                self.assertEqual(original_public, (
                    arguments["keys_directory"] / caller_public.name).read_bytes())
                try:
                    self.keyring.write_bytes(keyring.read_bytes())
                    caller_public.write_bytes(public.read_bytes())
                    return release_attested_runtime_variant_admission(source, **arguments)
                finally:
                    self.keyring.write_bytes(original_policy)
                    caller_public.write_bytes(original_public)

            session = self.session()
            with mock.patch.object(reuse_module, "release_attested_runtime_variant_admission",
                                   side_effect=late_swap) as gate:
                result = session.lookup("promoted-main", self.receipts["binary"])
            gate.assert_called_once()
            self.assertEqual(self.receipt_paths["binary"].read_bytes(), result.envelope["receiptBytes"])
            self.assertEqual(original_policy, self.keyring.read_bytes())
            self.assertEqual(original_public, caller_public.read_bytes())


if __name__ == "__main__":
    unittest.main()
