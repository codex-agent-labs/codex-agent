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
) -> tuple[bytes, str]:
    artifact_path = f"outputs/contract-{phase}.zip"
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
        "product": "contract",
        "component": "contract",
        "phase": phase,
        "target": "common",
        "productVersion": version,
        "buildKey": compute_build_key(
            product="contract",
            component="contract",
            phase=phase,
            target="common",
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
) -> IndexEntrySource:
    contents, artifact_path = receipt(
        phase,
        flags_digest=flags_digest,
        payload=payload,
        trust_domain=trust_domain,
        repository=repository,
        pull_request=pull_request,
        version=version,
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
        )

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
