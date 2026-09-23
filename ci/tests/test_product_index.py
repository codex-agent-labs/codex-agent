from __future__ import annotations

from pathlib import Path
import os
import shutil
import tempfile
import unittest
from unittest import mock

from ci.products.aggregate import validate_product_index
import ci.products.index as product_index
from ci.products.index import (
    IndexEntrySource,
    ReleaseIndexAdmission,
    release_attested_contract_admission,
    release_attested_runtime_aggregate_admission,
    release_attested_runtime_variant_admission,
    SignedProductIndex,
    build_product_index,
    verify_stable_index_history,
    write_signed_product_index,
)
from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    sha256_bytes,
    write_canonical_json,
)
from ci.products.receipt import compute_build_key, validate_phase_receipt
from ci.products.restore import store_local_object
from ci.tests import test_contract_bundle as contract_fixture
from ci.products.signatures import (
    generate_development_key,
    sign_manifest,
    verify_manifest_signature,
)


REPOSITORY = "owner/repository"
VERSION = "1.2.3"
COMMIT = "a" * 40
TREE = "b" * 40
DIGEST_A = sha256_bytes(b"a")
DIGEST_B = sha256_bytes(b"b")


def producer(trust_domain: str, pull_request: int = 31) -> dict[str, object]:
    return {
        "repository": REPOSITORY,
        "workflowPath": ".github/workflows/products.yml",
        "commit": COMMIT,
        "tree": TREE,
        "event": "pull_request" if trust_domain == "development" else "push",
        "runId": 7,
        "runAttempt": 1,
        "pullRequest": pull_request if trust_domain == "development" else None,
    }


def context(trust_domain: str, pull_request: int = 31) -> dict[str, object]:
    if trust_domain == "development":
        return {
            "kind": "pull-request",
            "pullRequest": pull_request,
            "commit": COMMIT,
            "tree": TREE,
            "runId": 7,
            "runAttempt": 1,
        }
    return {"kind": "stable", "tag": f"contract/v{VERSION}"}


def receipt(
    phase: str = "metadata",
    *,
    flags_digest: str = DIGEST_A,
    payload: bytes = b"artifact",
    trust_domain: str = "release",
    repository: str = REPOSITORY,
    pull_request: int = 31,
    version: str = VERSION,
    product: str = "contract",
    component: str = "contract",
    target: str = "common",
) -> tuple[bytes, str]:
    artifact_path = f"outputs/{component}-{phase}.zip"
    inventory = [{
        "relativePath": f"sources/{phase}.kt",
        "bytes": 1,
        "sha256": flags_digest,
    }]
    inputs = {
        "inventory": inventory,
        "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
        "versionIdentity": version,
        "upstreamArtifacts": [],
        "toolchainProfileDigest": DIGEST_A,
        "flagsDigest": flags_digest,
        "outputSchemaVersion": 1,
    }
    value = validate_phase_receipt({
        "schemaVersion": 1,
        "product": product,
        "component": component,
        "phase": phase,
        "target": target,
        "productVersion": version,
        "buildKey": compute_build_key(
            product=product,
            component=component,
            phase=phase,
            target=target,
            inputs=inputs,
        ),
        "inputs": inputs,
        "outputs": [{
            "kind": "artifact",
            "relativePath": artifact_path,
            "bytes": len(payload),
            "sha256": sha256_bytes(payload),
        }],
        "producer": {
            **producer(trust_domain, pull_request),
            "repository": repository,
        },
        "trustDomain": trust_domain,
        "result": "success",
    })
    return canonical_json_bytes(value), artifact_path


def source(
    phase: str = "metadata",
    *,
    flags_digest: str = DIGEST_A,
    payload: bytes = b"artifact",
    trust_domain: str = "release",
    repository: str = REPOSITORY,
    pull_request: int = 31,
    version: str = VERSION,
    product: str = "contract",
    component: str = "contract",
    target: str = "common",
) -> IndexEntrySource:
    contents, artifact_path = receipt(
        phase,
        flags_digest=flags_digest,
        payload=payload,
        trust_domain=trust_domain,
        repository=repository,
        pull_request=pull_request,
        version=version,
        product=product,
        component=component,
        target=target,
    )
    return IndexEntrySource(contents, artifact_path)


@unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
class ProductIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.keys = tempfile.TemporaryDirectory()
        cls.private_key, cls.public_key, cls.development_signing = generate_development_key(
            Path(cls.keys.name).resolve() / "keys"
        )
        cls.release_signing = {
            **cls.development_signing,
            "trustDomain": "release",
            "keyId": "release-test",
        }
        cls.release_keys = Path(cls.keys.name).resolve() / "release-keys"
        cls.release_keys.mkdir()
        shutil.copyfile(cls.public_key, cls.release_keys / "release-test.pub")
        cls.keyring = Path(cls.keys.name).resolve() / "product-signing-keys.json"
        write_canonical_json(cls.keyring, {
            "schemaVersion": 1,
            "namespace": "codex-agent-product-v1",
            "algorithm": "ssh-ed25519",
            "trustDomain": "release",
            "activeKey": {
                "keyId": "release-test",
                "fingerprint": cls.release_signing["fingerprint"],
            },
            "retiredKeys": [],
        })

    @classmethod
    def tearDownClass(cls) -> None:
        cls.keys.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.catalog_number = 0

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_stable_history_reads_the_exact_current_product_tag_namespaces(self) -> None:
        completed = mock.Mock(stdout=(
            f"{'c' * 40}\trefs/tags/contract/v1.2.3\n"
            f"{'d' * 40}\trefs/tags/runtime/v2.3.4\n"
        ))
        with mock.patch.object(product_index.subprocess, "run", return_value=completed) as run:
            self.assertEqual({
                "contract/v1.2.3": "c" * 40,
                "runtime/v2.3.4": "d" * 40,
            }, product_index._authoritative_stable_refs(REPOSITORY))
        self.assertEqual([
            "git", "ls-remote", "--refs", "--tags",
            f"https://github.com/{REPOSITORY}.git",
            "refs/tags/contract/v*", "refs/tags/runtime/v*", "refs/tags/sdk/v*",
        ], run.call_args.args[0])

        completed.stdout = f"{'c' * 40}\trefs/tags/contract/v1.2.3-rc.1\n"
        with mock.patch.object(product_index.subprocess, "run", return_value=completed), \
                self.assertRaisesRegex(ValueError, "canonical SemVer|invalid tag"):
            product_index._authoritative_stable_refs(REPOSITORY)

    def publish(
        self,
        trust_domain: str,
        manifest: Path,
        *,
        sources: list[IndexEntrySource] | None = None,
        prior: list[SignedProductIndex] | None = None,
        authoritative_tags: set[str] | None = None,
        context_value: dict[str, object] | None = None,
        producer_value: dict[str, object] | None = None,
        private_key: Path | None = None,
        public_key: Path | None = None,
        contract_objects=None,
        prior_contract_objects=None,
    ) -> dict[str, object]:
        signing = self.development_signing if trust_domain == "development" else self.release_signing
        history = None
        if trust_domain == "release":
            prior_sources = [] if prior is None else prior
            tags = authoritative_tags if authoritative_tags is not None else {
                load_canonical_json_bytes(item.manifest.read_bytes())["context"]["tag"]
                for item in prior_sources
            }
            with mock.patch.object(
                product_index,
                "_authoritative_stable_refs",
                return_value={tag: "c" * 40 for tag in tags},
            ):
                history = verify_stable_index_history(
                    prior_sources,
                    repository=REPOSITORY,
                    keyring_path=self.keyring,
                    keys_directory=self.release_keys,
                    contract_objects=prior_contract_objects,
                )
        return write_signed_product_index(
            [source(trust_domain=trust_domain)] if sources is None else sources,
            repository=REPOSITORY,
            context=context(trust_domain) if context_value is None else context_value,
            trust_domain=trust_domain,
            signing=signing,
            producer=producer(trust_domain) if producer_value is None else producer_value,
            stable_history=history,
            private_key=self.private_key if private_key is None else private_key,
            public_key=self.public_key if public_key is None else public_key,
            manifest_path=manifest,
            contract_objects=contract_objects,
        )

    def execution_source(self, name: str, *, execution_context="first", target_hash_salt=b""):
        root = self.root / name
        run = 7 if execution_context == "first" else 8
        phases = contract_fixture.ContractBundleTest()._product_phase_stages(
            root, execution_context=execution_context, target_hash_salt=target_hash_salt,
            producer={**producer("release"), "runId": run, "commit": str(run) * 40, "tree": str(run + 1) * 40},
            trust_domain="release",
        )
        contents = phases["binary_receipt_path"].read_bytes()
        stored = store_local_object(phases["binary_stage"], phases["binary_receipt_path"], root / "cache")
        transport = root / "transport.zip"
        shutil.copyfile(stored["path"], transport)
        return IndexEntrySource(contents, "outputs/execution/contract-execution.zip"), transport

    def test_signed_writer_forwards_native_comparison_authorities_to_the_same_builder(self):
        provider = mock.Mock()
        with mock.patch.object(product_index, "build_product_index", wraps=build_product_index) as builder:
            write_signed_product_index(
                [source(trust_domain="development")], repository=REPOSITORY,
                context=context("development"), trust_domain="development", signing=self.development_signing,
                producer=producer("development"), stable_history=None, private_key=self.private_key,
                public_key=self.public_key, manifest_path=self.root / "native-forwarding.json",
                native_runtime_objects={}, native_runtime_projection=provider,
            )
        self.assertEqual({}, builder.call_args.kwargs["native_runtime_objects"])
        self.assertIs(provider, builder.call_args.kwargs["native_runtime_projection"])
        provider.assert_not_called()  # No conflict/history means no unnecessary K/R verification.

    def test_stable_publication_authenticates_original_execution_objects_without_rewriting(self):
        first, first_object = self.execution_source("first-execution")
        second, second_object = self.execution_source("second-execution", execution_context="second")
        first_sha, second_sha = map(sha256_bytes, (first.receipt_bytes, second.receipt_bytes))
        tag = {"kind": "stable", "tag": f"contract/v{contract_fixture.VERSION}"}
        first_index = self.root / "first-index/product-index.json"
        first_index.parent.mkdir()
        self.publish("release", first_index, sources=[first], context_value=tag)
        signed = SignedProductIndex(first_index, first_index.with_suffix(".sig"))
        retained = [first_index, signed.signature, first_object, second_object]
        original = {path: path.read_bytes() for path in retained}
        second_index = self.root / "second-index/product-index.json"
        second_index.parent.mkdir()
        arguments = dict(sources=[second], prior=[signed], context_value=tag,
                         prior_contract_objects={first_sha: first_object},
                         contract_objects={second_sha: second_object})
        result = self.publish("release", second_index, **arguments)
        self.assertEqual(second_sha, result["index"]["entries"][0]["receiptSha256"])
        self.assertEqual(load_canonical_json_bytes(second.receipt_bytes)["outputs"], result["index"]["entries"][0]["outputs"])
        self.assertNotEqual(first_index.read_bytes(), second_index.read_bytes())
        self.assertEqual(original, {path: path.read_bytes() for path in retained})
        with self.assertRaises(ValueError):
            self.publish("release", first_index, **arguments)
        self.assertEqual(original, {path: path.read_bytes() for path in retained})

    def test_stable_execution_comparison_rejects_missing_wrong_changed_and_replaced_objects(self):
        first, first_object = self.execution_source("original-execution")
        second, second_object = self.execution_source("new-execution", execution_context="second")
        changed, changed_object = self.execution_source("changed-execution", target_hash_salt=b"changed-content")
        first_sha, second_sha, changed_sha = map(sha256_bytes, (first.receipt_bytes, second.receipt_bytes, changed.receipt_bytes))
        tag = {"kind": "stable", "tag": f"contract/v{contract_fixture.VERSION}"}
        first_index = self.root / "original-index/product-index.json"
        first_index.parent.mkdir()
        self.publish("release", first_index, sources=[first], context_value=tag)
        signed = SignedProductIndex(first_index, first_index.with_suffix(".sig"))
        references = {first_sha: first_object}
        with mock.patch.object(product_index, "_authoritative_stable_refs", return_value={tag["tag"]: "c" * 40}):
            history = verify_stable_index_history([signed], repository=REPOSITORY,
                keyring_path=self.keyring, keys_directory=self.release_keys, contract_objects=references)
        references[first_sha] = self.root / "not-the-original-object"
        arguments = dict(repository=REPOSITORY, context=tag, trust_domain="release",
                         signing=self.release_signing, producer=producer("release"), stable_history=history)
        # The retained reference map is immutable; paths are nevertheless verified afresh.
        build_product_index([second], **arguments, contract_objects={second_sha: second_object})
        cases = [([second], None), ([second], {second_sha: first_object}),
                 ([second], {second_sha: self.root / "expired-object"}),
                 ([changed], {changed_sha: changed_object})]
        for selected, objects in cases:
            with self.subTest(objects=objects), self.assertRaises((ValueError, OSError)):
                build_product_index(selected, **arguments, contract_objects=objects)
        before = first_object.read_bytes()
        first_object.write_bytes(b"corrupt after history verification")
        try:
            with self.assertRaises((ValueError, OSError)):
                build_product_index([second], **arguments, contract_objects={second_sha: second_object})
        finally:
            first_object.write_bytes(before)
        with mock.patch.object(product_index, "_authoritative_stable_refs", return_value={tag["tag"]: "c" * 40}), \
                self.assertRaisesRegex(ValueError, "current protected stable-tag inventory"):
            verify_stable_index_history([signed, signed], repository=REPOSITORY,
                keyring_path=self.keyring, keys_directory=self.release_keys, contract_objects={first_sha: first_object})

    def test_development_and_release_indexes_round_trip_and_identical_retry(self) -> None:
        for trust_domain in ("development", "release"):
            with self.subTest(trust_domain=trust_domain):
                manifest = self.root / trust_domain / "product-index.json"
                manifest.parent.mkdir()
                result = self.publish(trust_domain, manifest)
                signing = (
                    self.development_signing
                    if trust_domain == "development"
                    else self.release_signing
                )
                self.assertEqual("published", result["status"])
                self.assertEqual(canonical_json_bytes(result["index"]), manifest.read_bytes())
                self.assertEqual(
                    sha256_bytes(source(trust_domain=trust_domain).receipt_bytes),
                    result["index"]["entries"][0]["receiptSha256"],
                )
                verify_manifest_signature(
                    manifest,
                    manifest.with_suffix(".sig"),
                    self.public_key,
                    signing,
                )
                before = (manifest.read_bytes(), manifest.with_suffix(".sig").read_bytes())
                retry = self.publish(trust_domain, manifest)
                self.assertEqual("existing", retry["status"])
                self.assertEqual(
                    before,
                    (manifest.read_bytes(), manifest.with_suffix(".sig").read_bytes()),
                )

    def test_promoted_main_is_one_signed_immutable_index_pair(self) -> None:
        manifest = self.root / "promotion" / "product-index.json"
        manifest.parent.mkdir()
        promotion_context = {
            "kind": "promoted-main",
            "commit": COMMIT,
            "tree": TREE,
            "promotionRunId": 7,
            "promotionRunAttempt": 1,
        }

        first = write_signed_product_index(
            [source("binary"), source("metadata")],
            repository=REPOSITORY,
            context=promotion_context,
            trust_domain="release",
            signing=self.release_signing,
            producer=producer("release"),
            stable_history=None,
            private_key=self.private_key,
            public_key=self.public_key,
            manifest_path=manifest,
        )
        before = (manifest.read_bytes(), manifest.with_suffix(".sig").read_bytes())
        retry = write_signed_product_index(
            [source("metadata"), source("binary")],
            repository=REPOSITORY,
            context=promotion_context,
            trust_domain="release",
            signing=self.release_signing,
            producer=producer("release"),
            stable_history=None,
            private_key=self.private_key,
            public_key=self.public_key,
            manifest_path=manifest,
        )

        self.assertEqual("published", first["status"])
        self.assertEqual("existing", retry["status"])
        self.assertEqual(
            before,
            (manifest.read_bytes(), manifest.with_suffix(".sig").read_bytes()),
        )

        verify_manifest_signature(
            manifest,
            manifest.with_suffix(".sig"),
            self.public_key,
            self.release_signing,
        )

        with self.assertRaisesRegex(ValueError, "conflicts"):
            write_signed_product_index(
                [source("binary"), source("metadata", flags_digest=DIGEST_B)],
                repository=REPOSITORY,
                context=promotion_context,
                trust_domain="release",
                signing=self.release_signing,
                producer=producer("release"),
                stable_history=None,
                private_key=self.private_key,
                public_key=self.public_key,
                manifest_path=manifest,
            )
        self.assertEqual(
            before,
            (manifest.read_bytes(), manifest.with_suffix(".sig").read_bytes()),
        )

    def test_release_index_requires_exact_attested_contract_admission(self) -> None:
        original = source("metadata", trust_domain="development")
        receipt_path = self.root / "contract-metadata-receipt.json"
        receipt_path.write_bytes(original.receipt_bytes)
        verified_receipt = validate_phase_receipt(
            load_canonical_json_bytes(original.receipt_bytes),
        )
        with mock.patch(
            "ci.products.contract_attestation.verify_contract_attestation",
            return_value=({}, verified_receipt, {}),
        ) as verifier:
            admission = release_attested_contract_admission(
                original,
                payload=self.root / "contract.zip",
                metadata_receipt=receipt_path,
                attestation=self.root / "contract.attestation.json",
                signature=self.root / "contract.attestation.sig",
                public_key=self.public_key,
                keyring=self.keyring,
                keys_directory=self.release_keys,
            )
        self.assertEqual("release", verifier.call_args.kwargs["required_trust_domain"])
        admitted = IndexEntrySource(
            original.receipt_bytes, original.artifact_path, admission,
        )
        value = build_product_index(
            [admitted],
            repository=REPOSITORY,
            context={
                "kind": "promoted-main", "commit": COMMIT, "tree": TREE,
                "promotionRunId": 7, "promotionRunAttempt": 1,
            },
            trust_domain="release",
            signing=self.release_signing,
            producer=producer("release"),
            stable_history=None,
        )
        self.assertEqual(sha256_bytes(original.receipt_bytes), value["entries"][0]["receiptSha256"])
        self.assertNotIn("releaseAdmission", value["entries"][0])

        with self.assertRaisesRegex(ValueError, "trust domain"):
            build_product_index(
                [original],
                repository=REPOSITORY,
                context={
                    "kind": "promoted-main", "commit": COMMIT, "tree": TREE,
                    "promotionRunId": 7, "promotionRunAttempt": 1,
                },
                trust_domain="release",
                signing=self.release_signing,
                producer=producer("release"),
                stable_history=None,
            )

        changed = source(
            "metadata", trust_domain="development", flags_digest=DIGEST_B,
        )
        with self.assertRaisesRegex(ValueError, "trust domain"):
            build_product_index(
                [IndexEntrySource(changed.receipt_bytes, changed.artifact_path, admission)],
                repository=REPOSITORY,
                context={
                    "kind": "promoted-main", "commit": COMMIT, "tree": TREE,
                    "promotionRunId": 7, "promotionRunAttempt": 1,
                },
                trust_domain="release",
                signing=self.release_signing,
                producer=producer("release"),
                stable_history=None,
            )

    def _mock_nonmetadata_contract_admission(self):
        original = source("binary", trust_domain="development")
        metadata = source("metadata", trust_domain="development")
        metadata_path = self.root / "metadata-receipt.json"
        metadata_path.write_bytes(metadata.receipt_bytes)
        closure = self.root / "execution-closure"
        (closure / "receipts").mkdir(parents=True)
        selected_path = closure / "receipts/binary.json"
        selected_path.write_bytes(original.receipt_bytes)
        closure_value = {"files": [{
            "relativePath": "receipts/binary.json",
            "bytes": len(original.receipt_bytes),
            "sha256": sha256_bytes(original.receipt_bytes),
        }]}
        closure_bytes = canonical_json_bytes(closure_value)
        (closure / "contract-execution-closure.json").write_bytes(closure_bytes)
        verifier_result = (
            {},
            validate_phase_receipt(load_canonical_json_bytes(metadata.receipt_bytes)),
            {"executionClosureSha256": sha256_bytes(closure_bytes)},
        )
        arguments = {
            "payload": self.root / "contract.zip",
            "metadata_receipt": metadata_path,
            "attestation": self.root / "contract.attestation.json",
            "signature": self.root / "contract.attestation.sig",
            "public_key": self.public_key,
            "keyring": self.keyring,
            "keys_directory": self.release_keys,
        }
        return original, arguments, verifier_result, selected_path, closure_bytes

    def test_nonmetadata_contract_admission_rejects_wrong_identity_and_token_reuse(self) -> None:
        # This isolates index admission binding; the real signed four-phase closure
        # is covered by the Contract integration fixture.
        original, arguments, verifier_result, _, _ = self._mock_nonmetadata_contract_admission()
        with mock.patch(
            "ci.products.contract_attestation.verify_contract_attestation",
            return_value=verifier_result,
        ):
            admission = release_attested_contract_admission(original, **arguments)
            wrong_identity = source(
                "binary", trust_domain="development", product="sdk",
                component="contract", target="common",
            )
            with self.assertRaisesRegex(ValueError, "original Contract phase"):
                release_attested_contract_admission(wrong_identity, **arguments)
            with self.assertRaisesRegex(ValueError, "unadmitted development receipt"):
                release_attested_contract_admission(
                    source("binary", trust_domain="release"), **arguments,
                )

        changed = source("binary", trust_domain="development", flags_digest=DIGEST_B)
        with self.assertRaisesRegex(ValueError, "trust domain"):
            build_product_index(
                [IndexEntrySource(changed.receipt_bytes, changed.artifact_path, admission)],
                repository=REPOSITORY,
                context={
                    "kind": "promoted-main", "commit": COMMIT, "tree": TREE,
                    "promotionRunId": 7, "promotionRunAttempt": 1,
                },
                trust_domain="release",
                signing=self.release_signing,
                producer=producer("release"),
                stable_history=None,
            )

    def test_nonmetadata_contract_admission_rejects_post_verification_mutation(self) -> None:
        (original, arguments, verifier_result, selected_path,
         manifest_bytes) = self._mock_nonmetadata_contract_admission()
        manifest_path = self.root / "execution-closure/contract-execution-closure.json"

        for changed, error in (("receipt", "differs"), ("manifest", "closure changed")):
            with self.subTest(changed=changed):
                selected_path.write_bytes(original.receipt_bytes)
                manifest_path.write_bytes(manifest_bytes)

                def verified(*_args, **_kwargs):
                    if changed == "receipt":
                        selected_path.write_bytes(b"changed")
                    else:
                        manifest_path.write_bytes(canonical_json_bytes({"files": []}))
                    return verifier_result

                with mock.patch(
                    "ci.products.contract_attestation.verify_contract_attestation",
                    side_effect=verified,
                ), self.assertRaisesRegex(ValueError, error):
                    release_attested_contract_admission(original, **arguments)

    def test_release_index_accepts_exact_attested_runtime_variant_phase(self) -> None:
        target = "linux-x64"
        sources = {
            phase: source(
                phase, trust_domain="development", product="runtime",
                component=target, target=target,
            )
            for phase in ("binary", "package", "validation", "metadata")
        }
        paths = {}
        receipts = {}
        for phase, value in sources.items():
            path = self.root / f"{phase}-receipt.json"
            path.write_bytes(value.receipt_bytes)
            paths[phase] = path
            receipts[phase] = validate_phase_receipt(
                load_canonical_json_bytes(value.receipt_bytes),
            )
        selected = sources["package"]
        with mock.patch(
            "ci.products.runtime_attestation.verify_runtime_variant_attestation",
            return_value=({"target": target}, receipts, {}),
        ) as verifier:
            admission = release_attested_runtime_variant_admission(
                selected,
                payload=self.root / "variant.zip",
                binary_receipt=paths["binary"],
                package_receipt=paths["package"],
                validation_receipt=paths["validation"],
                metadata_receipt=paths["metadata"],
                validation_evidence=self.root / "validation.json",
                attestation=self.root / "variant.attestation.json",
                signature=self.root / "variant.attestation.sig",
                public_key=self.public_key,
                keyring=self.keyring,
                keys_directory=self.release_keys,
            )
        self.assertEqual("release", verifier.call_args.kwargs["required_trust_domain"])
        value = build_product_index(
            [IndexEntrySource(selected.receipt_bytes, selected.artifact_path, admission)],
            repository=REPOSITORY,
            context={
                "kind": "promoted-main", "commit": COMMIT, "tree": TREE,
                "promotionRunId": 7, "promotionRunAttempt": 1,
            },
            trust_domain="release",
            signing=self.release_signing,
            producer=producer("release"),
            stable_history=None,
        )
        self.assertEqual(sha256_bytes(selected.receipt_bytes), value["entries"][0]["receiptSha256"])

        other = source(
            "package", trust_domain="development", product="runtime",
            component=target, target=target, flags_digest=DIGEST_B,
        )
        with self.assertRaisesRegex(ValueError, "trust domain"):
            build_product_index(
                [IndexEntrySource(other.receipt_bytes, other.artifact_path, admission)],
                repository=REPOSITORY,
                context={
                    "kind": "promoted-main", "commit": COMMIT, "tree": TREE,
                    "promotionRunId": 7, "promotionRunAttempt": 1,
                },
                trust_domain="release", signing=self.release_signing,
                producer=producer("release"), stable_history=None,
            )

    def test_release_admission_is_opaque_and_binds_complete_outputs(self) -> None:
        with self.assertRaisesRegex(TypeError, "verifier-produced"):
            ReleaseIndexAdmission(object())

        original = source("metadata", trust_domain="development")
        value = load_canonical_json_bytes(original.receipt_bytes)
        value["outputs"].append({
            "kind": "artifact",
            "relativePath": "outputs/other.zip",
            "bytes": 5,
            "sha256": sha256_bytes(b"other"),
        })
        value["outputs"].sort(key=lambda output: output["relativePath"])
        contents = canonical_json_bytes(validate_phase_receipt(value))
        exact = IndexEntrySource(contents, original.artifact_path)
        receipt_path = self.root / "multi-output-receipt.json"
        receipt_path.write_bytes(contents)
        with mock.patch(
            "ci.products.contract_attestation.verify_contract_attestation",
            return_value=({}, validate_phase_receipt(value), {}),
        ):
            admission = release_attested_contract_admission(
                exact,
                payload=self.root / "contract.zip",
                metadata_receipt=receipt_path,
                attestation=self.root / "contract.attestation.json",
                signature=self.root / "contract.attestation.sig",
                public_key=self.public_key,
                keyring=self.keyring,
                keys_directory=self.release_keys,
            )
        arguments = {
            "repository": REPOSITORY,
            "context": {
                "kind": "promoted-main", "commit": COMMIT, "tree": TREE,
                "promotionRunId": 7, "promotionRunAttempt": 1,
            },
            "trust_domain": "release",
            "signing": self.release_signing,
            "producer": producer("release"),
            "stable_history": None,
        }
        for rejected in (
            IndexEntrySource(contents, "outputs/other.zip", admission),
            IndexEntrySource(contents, original.artifact_path, True),
        ):
            with self.subTest(artifact=rejected.artifact_path), self.assertRaisesRegex(
                ValueError, "trust domain",
            ):
                build_product_index([rejected], **arguments)

        changed = load_canonical_json_bytes(contents)
        changed["outputs"][0]["sha256"] = DIGEST_B
        with self.assertRaisesRegex(ValueError, "trust domain"):
            build_product_index([
                IndexEntrySource(
                    canonical_json_bytes(validate_phase_receipt(changed)),
                    original.artifact_path,
                    admission,
                ),
            ], **arguments)

        sdk = source(
            "package", trust_domain="development", product="sdk",
            component="python", target="desktop",
        )
        with self.assertRaisesRegex(ValueError, "trust domain"):
            build_product_index([sdk], **arguments)

    def test_release_index_requires_runtime_aggregate_attestation_closure(self) -> None:
        original = source(
            "metadata", trust_domain="development", product="runtime",
            component="runtime-aggregate", target="aggregate",
        )
        receipt_path = self.root / "aggregate-metadata-receipt.json"
        receipt_path.write_bytes(original.receipt_bytes)
        verified_receipt = validate_phase_receipt(
            load_canonical_json_bytes(original.receipt_bytes),
        )
        aggregate_verifier = mock.Mock(return_value=({}, verified_receipt, {}))
        closure_verifier = mock.Mock(return_value=({}, {}, []))
        variant_inputs = {"linux-x64": self.root / "input"}
        with mock.patch(
            "ci.products.runtime_aggregate.verify_runtime_aggregate_attestation",
            aggregate_verifier,
        ), mock.patch(
            "ci.products.runtime_aggregate.verify_runtime_aggregate_attestation_closure",
            closure_verifier,
        ):
            admission = release_attested_runtime_aggregate_admission(
                original,
                manifest=self.root / "runtime-manifest.json",
                metadata_receipt=receipt_path,
                attestation=self.root / "runtime.attestation.json",
                signature=self.root / "runtime.attestation.sig",
                public_key=self.public_key,
                variant_bundles=variant_inputs,
                variant_phase_receipts={"linux-x64": {}},
                variant_attestations=variant_inputs,
                variant_attestation_signatures=variant_inputs,
                variant_public_keys=variant_inputs,
                variant_validation_evidence=variant_inputs,
                adapter_receipts=[],
                keyring=self.keyring,
                keys_directory=self.release_keys,
                variant_keyring=self.keyring,
                variant_keys_directory=self.release_keys,
            )
        self.assertEqual("release", aggregate_verifier.call_args.kwargs["required_trust_domain"])
        self.assertEqual("release", closure_verifier.call_args.kwargs[
            "required_variant_trust_domain"
        ])
        value = build_product_index(
            [IndexEntrySource(original.receipt_bytes, original.artifact_path, admission)],
            repository=REPOSITORY,
            context={
                "kind": "promoted-main", "commit": COMMIT, "tree": TREE,
                "promotionRunId": 7, "promotionRunAttempt": 1,
            },
            trust_domain="release", signing=self.release_signing,
            producer=producer("release"), stable_history=None,
        )
        self.assertEqual("runtime-aggregate", value["entries"][0]["component"])

        with mock.patch(
            "ci.products.runtime_aggregate.verify_runtime_aggregate_attestation",
            return_value=({}, verified_receipt, {}),
        ), mock.patch(
            "ci.products.runtime_aggregate.verify_runtime_aggregate_attestation_closure",
            side_effect=ValueError("closure mismatch"),
        ), self.assertRaisesRegex(ValueError, "closure mismatch"):
            release_attested_runtime_aggregate_admission(
                original,
                manifest=self.root / "runtime-manifest.json",
                metadata_receipt=receipt_path,
                attestation=self.root / "runtime.attestation.json",
                signature=self.root / "runtime.attestation.sig",
                public_key=self.public_key,
                variant_bundles=variant_inputs,
                variant_phase_receipts={"linux-x64": {}},
                variant_attestations=variant_inputs,
                variant_attestation_signatures=variant_inputs,
                variant_public_keys=variant_inputs,
                variant_validation_evidence=variant_inputs,
                adapter_receipts=[],
                keyring=self.keyring,
                keys_directory=self.release_keys,
                variant_keyring=self.keyring,
                variant_keys_directory=self.release_keys,
            )

    def test_exact_schema_context_and_build_key_order(self) -> None:
        values = [
            source("metadata", trust_domain="development"),
            source("binary", trust_domain="development"),
        ]
        index = build_product_index(
            list(reversed(values)),
            repository=REPOSITORY,
            context=context("development"),
            trust_domain="development",
            signing=self.development_signing,
            producer=producer("development"),
            stable_history=None,
        )

        self.assertEqual(
            {"schemaVersion", "repository", "context", "entries", "trustDomain", "signing", "producer"},
            set(index),
        )
        self.assertEqual(
            sorted(entry["buildKey"] for entry in index["entries"]),
            [entry["buildKey"] for entry in index["entries"]],
        )
        self.assertEqual(
            "io.github.codex-agent-labs:codex-agent-core",
            index["entries"][0]["coordinate"],
        )
        self.assertEqual(
            {
                "buildKey", "product", "component", "phase", "target", "productVersion",
                "coordinate", "outputInventoryDigest", "outputs", "artifactName",
                "artifactSha256", "receiptSha256",
            },
            set(index["entries"][0]),
        )
        validate_product_index(index)

        local = {**producer("development"), "event": "local", "workflowPath": None,
                 "runId": None, "runAttempt": None, "pullRequest": None}
        with self.assertRaisesRegex(ValueError, "context/producer"):
            validate_product_index({**index, "producer": local})
        original = values[0]
        local_receipt = {**load_canonical_json_bytes(original.receipt_bytes), "producer": local}
        local_source = IndexEntrySource(canonical_json_bytes(local_receipt), original.artifact_path)
        with self.assertRaisesRegex(ValueError, "another context"):
            build_product_index(
                [local_source], repository=REPOSITORY, context=context("development"),
                trust_domain="development", signing=self.development_signing,
                producer=producer("development"), stable_history=None,
            )
        with self.assertRaises(ValueError):
            build_product_index(
                [local_source], repository=REPOSITORY, context=context("release"),
                trust_domain="release", signing=self.release_signing,
                producer=producer("release"), stable_history=None,
            )

        invalid_context = {**context("development"), "extra": True}
        with self.assertRaises(ValueError):
            build_product_index(
                values,
                repository=REPOSITORY,
                context=invalid_context,
                trust_domain="development",
                signing=self.development_signing,
                producer=producer("development"),
                stable_history=None,
            )
        wrong_producer = producer("development"); wrong_producer["runId"] = 8
        with self.assertRaisesRegex(ValueError, "context/producer"):
            build_product_index(
                values,
                repository=REPOSITORY,
                context=context("development"),
                trust_domain="development",
                signing=self.development_signing,
                producer=wrong_producer,
                stable_history=None,
            )

    def test_duplicate_artifact_and_receipt_mutations_fail(self) -> None:
        exact = source(trust_domain="development")
        with self.assertRaisesRegex(ValueError, "unique"):
            build_product_index(
                [exact, exact],
                repository=REPOSITORY,
                context=context("development"),
                trust_domain="development",
                signing=self.development_signing,
                producer=producer("development"),
                stable_history=None,
            )

        cases = [
            IndexEntrySource(exact.receipt_bytes, "outputs/missing.zip"),
            IndexEntrySource(exact.receipt_bytes + b" ", exact.artifact_path),
        ]
        mutated = load_canonical_json_bytes(exact.receipt_bytes)
        mutated["result"] = "failure"
        cases.append(IndexEntrySource(canonical_json_bytes(mutated), exact.artifact_path))
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                build_product_index(
                    [case],
                    repository=REPOSITORY,
                    context=context("development"),
                    trust_domain="development",
                    signing=self.development_signing,
                    producer=producer("development"),
                    stable_history=None,
                )

    def test_distinct_targets_may_share_a_phase_object_relative_artifact_name(self) -> None:
        first = source("validation", product="sdk", component="sdk-core", target="jvm",
                       trust_domain="development")
        second = source("validation", product="sdk", component="sdk-core", target="linux-x64",
                        trust_domain="development")
        index = build_product_index([first, second], repository=REPOSITORY,
            context=context("development"), trust_domain="development",
            signing=self.development_signing, producer=producer("development"), stable_history=None)
        entries = index["entries"]
        self.assertEqual({"jvm", "linux-x64"}, {entry["target"] for entry in entries})
        self.assertEqual(1, len({entry["artifactName"] for entry in entries}))
        self.assertIs(index, validate_product_index(index))

        duplicate_target = source("validation", product="sdk", component="sdk-core", target="jvm",
                                  flags_digest=DIGEST_B, trust_domain="development")
        with self.assertRaisesRegex(ValueError, "duplicate release assets"):
            build_product_index([first, duplicate_target], repository=REPOSITORY,
                context=context("development"), trust_domain="development",
                signing=self.development_signing, producer=producer("development"), stable_history=None)

    def test_release_trust_pull_request_index_is_sdk_only(self) -> None:
        sdk = source("package", product="sdk", component="sdk-core", target="common",
                     trust_domain="development")
        contract = source("package", trust_domain="development")
        sdk_index = build_product_index([sdk], repository=REPOSITORY,
            context=context("development"), trust_domain="development",
            signing=self.development_signing, producer=producer("development"), stable_history=None)
        contract_index = build_product_index([contract], repository=REPOSITORY,
            context=context("development"), trust_domain="development",
            signing=self.development_signing, producer=producer("development"), stable_history=None)
        release = {**sdk_index, "trustDomain": "release", "signing": self.release_signing}
        self.assertIs(release, validate_product_index(release))
        with self.assertRaisesRegex(ValueError, "only SDK campaign entries"):
            validate_product_index({**release, "entries": contract_index["entries"]})
        with self.assertRaisesRegex(ValueError, "receipt trust domain does not match"):
            build_product_index([sdk], repository=REPOSITORY,
                context=context("development"), trust_domain="release",
                signing=self.release_signing, producer=producer("development"), stable_history=None)

    def test_prior_stable_same_version_with_different_bytes_is_rejected(self) -> None:
        first = self.root / "first" / "product-index.json"
        first.parent.mkdir()
        self.publish("release", first)
        second = self.root / "second" / "product-index.json"
        second.parent.mkdir()

        with self.assertRaisesRegex(ValueError, "Stable product identity|conflicting output"):
            self.publish(
                "release",
                second,
                sources=[source(flags_digest=DIGEST_B, payload=b"different")],
                prior=[SignedProductIndex(first, first.with_suffix(".sig"))],
            )
        self.assertFalse(second.exists())
        self.assertFalse(second.with_suffix(".sig").exists())

        bypass = self.root / "bypass" / "product-index.json"
        bypass.parent.mkdir()
        with self.assertRaisesRegex(ValueError, "current protected stable-tag inventory"):
            self.publish(
                "release",
                bypass,
                sources=[source(flags_digest=DIGEST_B, payload=b"different")],
                authoritative_tags={f"contract/v{VERSION}"},
            )
        self.assertFalse(bypass.exists())

    def test_runtime_stable_version_rejects_different_aggregate_bytes(self) -> None:
        runtime_context = {"kind": "stable", "tag": f"runtime/v{VERSION}"}
        original = source(
            product="runtime",
            component="runtime-aggregate",
            target="aggregate",
            payload=b"runtime aggregate A",
        )
        first = self.root / "runtime-first" / "product-index.json"
        first.parent.mkdir()
        self.publish(
            "release",
            first,
            sources=[original],
            context_value=runtime_context,
        )

        changed = source(
            product="runtime",
            component="runtime-aggregate",
            target="aggregate",
            flags_digest=DIGEST_B,
            payload=b"runtime aggregate B",
        )
        second = self.root / "runtime-second" / "product-index.json"
        second.parent.mkdir()
        with self.assertRaisesRegex(ValueError, "Stable product identity|conflicting output"):
            self.publish(
                "release",
                second,
                sources=[changed],
                prior=[SignedProductIndex(first, first.with_suffix(".sig"))],
                context_value=runtime_context,
            )
        self.assertFalse(second.exists())
        self.assertFalse(second.with_suffix(".sig").exists())

    def test_receipt_trust_repository_stable_tag_and_signer_are_bound(self) -> None:
        cases = (
            {
                "trust_domain": "development",
                "sources": [source(trust_domain="release")],
            },
            {
                "trust_domain": "release",
                "sources": [source(repository="other/repository")],
            },
            {
                "trust_domain": "release",
                "context_value": {"kind": "stable", "tag": "sdk/v1.2.3"},
            },
        )
        for index, arguments in enumerate(cases):
            manifest = self.root / f"binding-{index}" / "product-index.json"
            manifest.parent.mkdir()
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.publish(arguments.pop("trust_domain"), manifest, **arguments)
            self.assertFalse(manifest.exists())

        wrong_private, _, _ = generate_development_key(self.root / "wrong-key")
        manifest = self.root / "wrong-signer" / "product-index.json"
        manifest.parent.mkdir()
        with self.assertRaisesRegex(ValueError, "fingerprint|signature|SSHSIG"):
            self.publish("release", manifest, private_key=wrong_private)
        self.assertFalse(manifest.exists())
        self.assertFalse(manifest.with_suffix(".sig").exists())

    def test_pull_request_receipts_and_stable_versions_are_exact(self) -> None:
        manifest = self.root / "cross-pr" / "product-index.json"
        manifest.parent.mkdir()
        with self.assertRaisesRegex(ValueError, "another context"):
            self.publish(
                "development",
                manifest,
                sources=[source(trust_domain="development", pull_request=32)],
            )

        prerelease = self.root / "prerelease" / "product-index.json"
        prerelease.parent.mkdir()
        with self.assertRaisesRegex(ValueError, "stable product identity"):
            self.publish(
                "release",
                prerelease,
                sources=[source(version="1.2.3-rc.1")],
                context_value={"kind": "stable", "tag": "contract/v1.2.3-rc.1"},
            )

    def test_stable_history_is_explicit_authenticated_and_immutable(self) -> None:
        with self.assertRaisesRegex(ValueError, "authenticated history"):
            build_product_index(
                [source()],
                repository=REPOSITORY,
                context=context("release"),
                trust_domain="release",
                signing=self.release_signing,
                producer=producer("release"),
                stable_history=None,
            )

        first = self.root / "history" / "product-index.json"
        first.parent.mkdir()
        self.publish("release", first)
        first.with_suffix(".sig").write_bytes(b"not a signature\n")
        signed_source = SignedProductIndex(first, first.with_suffix(".sig"))
        with mock.patch.object(
            product_index,
            "_authoritative_stable_refs",
            return_value={f"contract/v{VERSION}": "c" * 40},
        ), self.assertRaises(ValueError):
            verify_stable_index_history(
                [signed_source],
                repository=REPOSITORY,
                keyring_path=self.keyring,
                keys_directory=self.release_keys,
            )

        complete = self.root / "complete-history" / "product-index.json"
        complete.parent.mkdir()
        self.publish("release", complete)
        with mock.patch.object(
            product_index,
            "_authoritative_stable_refs",
            return_value={f"contract/v{VERSION}": "c" * 40},
        ), self.assertRaisesRegex(ValueError, "current protected stable-tag inventory"):
            verify_stable_index_history(
                [],
                repository=REPOSITORY,
                keyring_path=self.keyring,
                keys_directory=self.release_keys,
            )

    def test_differing_occupied_outputs_are_never_overwritten(self) -> None:
        for occupied in ("both", "manifest", "signature"):
            root = self.root / occupied
            root.mkdir()
            manifest = root / "product-index.json"
            signature = manifest.with_suffix(".sig")
            if occupied in {"both", "manifest"}:
                manifest.write_bytes(b"occupied manifest")
            if occupied in {"both", "signature"}:
                signature.write_bytes(b"occupied signature")
            before = {
                path: path.read_bytes()
                for path in (manifest, signature)
                if path.exists()
            }

            with self.subTest(occupied=occupied), self.assertRaisesRegex(ValueError, "conflicts"):
                self.publish("release", manifest)
            self.assertEqual(before, {path: path.read_bytes() for path in before})
            self.assertEqual(set(before), {path for path in (manifest, signature) if path.exists()})

    def test_identical_manifest_without_signature_is_recoverable(self) -> None:
        complete = self.root / "complete" / "product-index.json"
        complete.parent.mkdir()
        self.publish("release", complete)
        recovered = self.root / "recovered" / "product-index.json"
        recovered.parent.mkdir()
        recovered.write_bytes(complete.read_bytes())

        result = self.publish("release", recovered)

        self.assertEqual("published", result["status"])
        verify_manifest_signature(
            recovered,
            recovered.with_suffix(".sig"),
            self.public_key,
            self.release_signing,
        )

    def test_identical_signature_without_manifest_is_recoverable(self) -> None:
        complete = self.root / "signature-complete" / "product-index.json"
        complete.parent.mkdir()
        self.publish("release", complete)
        recovered = self.root / "signature-recovered" / "product-index.json"
        recovered.parent.mkdir()
        recovered.with_suffix(".sig").write_bytes(complete.with_suffix(".sig").read_bytes())

        result = self.publish("release", recovered)

        self.assertEqual("published", result["status"])
        verify_manifest_signature(
            recovered,
            recovered.with_suffix(".sig"),
            self.public_key,
            self.release_signing,
        )

    @unittest.skipIf(os.name == "nt", "POSIX descriptor-relative parent race")
    def test_parent_swap_cannot_redirect_publication(self) -> None:
        parent = self.root / "parent"
        parent.mkdir()
        moved = self.root / "moved"
        attacker = self.root / "attacker"
        attacker.mkdir()
        original = product_index._publish_output
        swapped = False

        def swap(*args: object, **kwargs: object) -> bool:
            nonlocal swapped
            if not swapped:
                swapped = True
                parent.rename(moved)
                parent.symlink_to(attacker, target_is_directory=True)
            return original(*args, **kwargs)

        with mock.patch("ci.products.index._publish_output", side_effect=swap), \
                self.assertRaisesRegex(ValueError, "parent changed"):
            self.publish("release", parent / "product-index.json")
        self.assertEqual([], list(attacker.iterdir()))
        self.assertEqual([], list(moved.iterdir()))

    def test_between_file_mutation_fails_final_pair_verification(self) -> None:
        parent = self.root / "between-files"
        parent.mkdir()
        original = product_index._publish_output
        calls = 0

        def mutate(*args: object, **kwargs: object) -> bool:
            nonlocal calls
            published = original(*args, **kwargs)
            calls += 1
            if calls == 1:
                (parent / "product-index.json").write_bytes(b"mutated\n")
            return published

        with mock.patch("ci.products.index._publish_output", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "final verification"):
            self.publish("release", parent / "product-index.json")

    @unittest.skipIf(os.name == "nt", "Windows held leaf denies the injected write")
    def test_mutation_after_final_manifest_read_is_detected(self) -> None:
        parent = self.root / "after-final-read"
        parent.mkdir()
        original = product_index._read_held_file
        calls = 0

        def mutate(descriptor: int, identity: os.stat_result, limit: int) -> bytes:
            nonlocal calls
            contents = original(descriptor, identity, limit)
            calls += 1
            if calls == 1:
                (parent / "product-index.json").write_bytes(b"mutated-after-read\n")
            return contents

        with mock.patch("ci.products.index._read_held_file", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "final verification"):
            self.publish("release", parent / "product-index.json")


if __name__ == "__main__":
    unittest.main()
