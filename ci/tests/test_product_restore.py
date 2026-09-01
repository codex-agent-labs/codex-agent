from __future__ import annotations

import copy
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile

import ci.products.restore as product_restore
from ci.products.inventory import canonical_json_bytes, sha256_bytes, write_canonical_json
from ci.products.receipt import compute_build_key, write_output_manifest
from ci.products.restore import (
    CacheObjectError,
    native_cache_root,
    object_relative_path,
    restore_local_object,
    restore_object,
    store_local_object,
    transport_relative_path,
    validate_transport,
    verify_object,
    write_transport,
)


DIGEST_A = sha256_bytes(b"a")
DIGEST_B = sha256_bytes(b"b")
OID_A = "a" * 40
OID_B = "b" * 40


class ProductRestoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.stage = self.root / "stage"
        (self.stage / "outputs").mkdir(parents=True)
        (self.stage / "outputs" / "artifact.bin").write_bytes(b"artifact")
        self.manifest = write_output_manifest(
            self.stage,
            "sdk",
            "sdk-core",
            "package",
            "common",
            "0.2.0",
            {"package": "outputs"},
        )
        inventory = [{"relativePath": "source.txt", "bytes": 1, "sha256": DIGEST_A}]
        inputs = {
            "inventory": inventory,
            "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
            "versionIdentity": "0.2.0",
            "upstreamArtifacts": [],
            "toolchainProfileDigest": DIGEST_A,
            "flagsDigest": DIGEST_B,
            "outputSchemaVersion": 1,
        }
        self.receipt = {
            "schemaVersion": 1,
            "product": "sdk",
            "component": "sdk-core",
            "phase": "package",
            "target": "common",
            "productVersion": "0.2.0",
            "buildKey": compute_build_key(
                product="sdk",
                component="sdk-core",
                phase="package",
                target="common",
                inputs=inputs,
            ),
            "inputs": inputs,
            "outputs": self.manifest["outputs"],
            "producer": self.producer(),
            "trustDomain": "development",
            "result": "success",
        }
        self.receipt_path = self.root / "phase-receipt.json"
        write_canonical_json(self.receipt_path, self.receipt)
        self.receipt_bytes = self.receipt_path.read_bytes()
        self.receipt_sha256 = sha256_bytes(self.receipt_bytes)
        self.cache = self.root / "cache"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def producer() -> dict[str, object]:
        return {
            "repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml",
            "commit": OID_A,
            "tree": OID_B,
            "event": "pull_request",
            "runId": 12,
            "runAttempt": 1,
            "pullRequest": 31,
        }

    def store(self) -> dict[str, object]:
        return store_local_object(self.stage, self.receipt_path, self.cache)

    @staticmethod
    def entries(path: Path) -> dict[str, bytes]:
        with zipfile.ZipFile(path) as archive:
            return {member.filename: archive.read(member) for member in archive.infolist()}

    @staticmethod
    def rewrite(
        source: Path,
        destination: Path,
        *,
        mutate: dict[str, bytes] | None = None,
        remove: set[str] = frozenset(),
        extra: dict[str, bytes] | None = None,
        duplicate: str | None = None,
        compression: int = zipfile.ZIP_STORED,
    ) -> None:
        entries = ProductRestoreTest.entries(source)
        entries.update(mutate or {})
        entries.update(extra or {})
        with warnings.catch_warnings(), zipfile.ZipFile(destination, "w", compression=compression) as archive:
            warnings.simplefilter("ignore")
            for name, contents in sorted(entries.items()):
                if name not in remove:
                    archive.writestr(name, contents)
                    if name == duplicate:
                        archive.writestr(name, contents)

    def remote_transport(self, source_kind: str = "stable", consumer_kind: str = "ci") -> dict[str, object]:
        source: dict[str, object] = {
            "kind": source_kind,
            "indexSha256": DIGEST_A,
            "artifactName": "outputs/product-object.zip",
            "artifactSha256": DIGEST_B,
        }
        consumer: dict[str, object] = {"kind": "ci", "producer": self.producer()}
        if consumer_kind == "local":
            consumer = {
                "kind": "local",
                "repository": "codex-agent-labs/codex-agent",
                "commit": OID_A,
                "tree": OID_B,
            }
        return {
            "schemaVersion": 1,
            "buildKey": self.receipt["buildKey"],
            "receiptSha256": self.receipt_sha256,
            "objectSha256": DIGEST_A,
            "source": source,
            "consumer": consumer,
        }

    def test_native_roots_and_receipt_qualified_paths_are_exact(self) -> None:
        home = Path("/users/test")
        self.assertEqual(
            Path("/override"),
            native_cache_root(environ={"CODEX_AGENT_PRODUCT_CACHE": "/override"}, home=home),
        )
        self.assertEqual(
            home / "Library/Caches/codex-agent/products",
            native_cache_root(environ={}, platform="darwin", home=home),
        )
        self.assertEqual(
            Path("/xdg/codex-agent/products"),
            native_cache_root(environ={"XDG_CACHE_HOME": "/xdg"}, platform="linux", home=home),
        )
        self.assertEqual(
            home / "AppData/Local/codex-agent/products",
            native_cache_root(environ={}, platform="win32", home=home),
        )
        expected_object = (
            f"v1/objects/sha256/{self.receipt['buildKey'][7:]}/{self.receipt_sha256[7:]}.zip"
        )
        self.assertEqual(expected_object, object_relative_path(self.receipt["buildKey"], self.receipt_sha256))
        self.assertEqual(
            f"v1/transports/sha256/{self.receipt['buildKey'][7:]}/{self.receipt_sha256[7:]}/{DIGEST_A[7:]}.json",
            transport_relative_path(self.receipt["buildKey"], self.receipt_sha256, DIGEST_A),
        )
        for invalid in ("relative", ""):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                native_cache_root(environ={"CODEX_AGENT_PRODUCT_CACHE": invalid}, home=home)
        with self.assertRaises(ValueError):
            object_relative_path("bad", self.receipt_sha256)

    def test_transport_unions_are_exact_and_do_not_rewrite_receipts(self) -> None:
        for source in ("stable", "promoted-main", "same-pr"):
            for consumer in ("ci", "local"):
                with self.subTest(source=source, consumer=consumer):
                    validate_transport(self.remote_transport(source, consumer))
        local = self.remote_transport(consumer_kind="local")
        local["source"] = {
            "kind": "local",
            "cacheRelativePath": object_relative_path(self.receipt["buildKey"], self.receipt_sha256),
        }
        validate_transport(local)
        result = write_transport(self.cache, local)
        self.assertEqual("published", result["status"])
        self.assertEqual(canonical_json_bytes(local), result["path"].read_bytes())
        self.assertEqual(self.receipt_bytes, self.receipt_path.read_bytes())
        self.assertEqual("existing", write_transport(self.cache, local)["status"])

        invalid_values = []
        extra = copy.deepcopy(local); extra["extra"] = True; invalid_values.append(extra)
        wrong_path = copy.deepcopy(local); wrong_path["source"]["cacheRelativePath"] = "v1/objects/nope"; invalid_values.append(wrong_path)
        fake_ci = copy.deepcopy(local); fake_ci["consumer"]["runId"] = 1; invalid_values.append(fake_ci)
        bad_oid = copy.deepcopy(local); bad_oid["consumer"]["commit"] = "ABC"; invalid_values.append(bad_oid)
        wrong_union = copy.deepcopy(local); wrong_union["source"]["artifactSha256"] = DIGEST_A; invalid_values.append(wrong_union)
        for invalid in invalid_values:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_transport(invalid)

    def test_object_round_trip_is_deterministic_and_preserves_receipt_bytes(self) -> None:
        first = self.store()
        self.assertEqual("published", first["status"])
        archive = first["path"]
        expected = [
            "phase-receipt.json",
            "stage/output-manifest.json",
            "stage/outputs/artifact.bin",
        ]
        with zipfile.ZipFile(archive) as value:
            self.assertEqual(expected, [member.filename for member in value.infolist()])
            self.assertEqual(self.receipt_bytes, value.read("phase-receipt.json"))
        verified = verify_object(
            archive,
            build_key=self.receipt["buildKey"],
            receipt_sha256=self.receipt_sha256,
            object_sha256=first["objectSha256"],
        )
        self.assertEqual(self.receipt_bytes, verified["receiptBytes"])
        restored = self.root / "restored"
        result = restore_object(
            archive,
            restored,
            build_key=self.receipt["buildKey"],
            receipt_sha256=self.receipt_sha256,
            object_sha256=first["objectSha256"],
        )
        self.assertEqual(self.receipt_bytes, result["receiptBytes"])
        self.assertEqual(b"artifact", (restored / "outputs/artifact.bin").read_bytes())
        self.assertFalse((restored / "stage").exists())
        self.assertFalse((restored / "phase-receipt.json").exists())
        self.assertEqual("existing", self.store()["status"])

    def test_identity_and_allow_list_mutations_fail_before_materialization(self) -> None:
        stored = self.store()
        archive = stored["path"]
        cases: dict[str, Path] = {}
        extra = self.root / "extra.zip"; self.rewrite(archive, extra, extra={"stage/extra": b"x"}); cases["extra"] = extra
        missing = self.root / "missing.zip"; self.rewrite(archive, missing, remove={"stage/outputs/artifact.bin"}); cases["missing"] = missing
        wrong_output = self.root / "wrong-output.zip"; self.rewrite(archive, wrong_output, mutate={"stage/outputs/artifact.bin": b"wrong"}); cases["output"] = wrong_output
        wrong_receipt = self.root / "wrong-receipt.zip"; self.rewrite(archive, wrong_receipt, mutate={"phase-receipt.json": self.receipt_bytes + b" "}); cases["receipt"] = wrong_receipt
        duplicate = self.root / "duplicate.zip"; self.rewrite(archive, duplicate, duplicate="stage/outputs/artifact.bin"); cases["duplicate"] = duplicate
        traversal = self.root / "traversal.zip"; self.rewrite(archive, traversal, extra={"../escape": b"x"}); cases["traversal"] = traversal
        for name, invalid in cases.items():
            destination = self.root / f"restore-{name}"
            with self.subTest(name=name), self.assertRaises(CacheObjectError):
                restore_object(
                    invalid,
                    destination,
                    build_key=self.receipt["buildKey"],
                    receipt_sha256=self.receipt_sha256,
                )
            self.assertFalse(destination.exists())
        with self.assertRaises(CacheObjectError):
            verify_object(
                archive,
                build_key=self.receipt["buildKey"],
                receipt_sha256=self.receipt_sha256,
                object_sha256=DIGEST_A,
            )

    def test_symlink_special_and_compression_bomb_members_are_rejected(self) -> None:
        stored = self.store()
        archive = stored["path"]
        entries = self.entries(archive)
        symlink = self.root / "symlink.zip"
        with zipfile.ZipFile(symlink, "w") as value:
            for name, contents in sorted(entries.items()):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = ((stat.S_IFLNK | 0o777) if name == "stage/outputs/artifact.bin" else (stat.S_IFREG | 0o644)) << 16
                value.writestr(info, contents)
        bomb = self.root / "bomb.zip"
        self.rewrite(
            archive,
            bomb,
            mutate={"stage/outputs/artifact.bin": b"x" * 100_000},
            compression=zipfile.ZIP_DEFLATED,
        )
        for invalid in (symlink, bomb):
            with self.subTest(invalid=invalid.name), self.assertRaises(CacheObjectError):
                verify_object(
                    invalid,
                    build_key=self.receipt["buildKey"],
                    receipt_sha256=self.receipt_sha256,
                )

    def test_corrupt_local_entry_is_a_repeatable_non_destructive_miss(self) -> None:
        path = self.cache / object_relative_path(self.receipt["buildKey"], self.receipt_sha256)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"not a zip")
        before = path.stat()
        destination = self.root / "corrupt-restore"
        for _ in range(2):
            result = restore_local_object(
                self.cache,
                self.receipt["buildKey"],
                self.receipt_sha256,
                destination,
            )
            self.assertEqual(("miss", "local-corrupt"), (result["status"], result["reason"]))
            self.assertFalse(destination.exists())
            self.assertEqual(b"not a zip", path.read_bytes())
            self.assertEqual(before.st_ino, path.stat().st_ino)
        self.assertEqual("local-corrupt", self.store()["status"])
        self.assertEqual(b"not a zip", path.read_bytes())

    def test_valid_different_immutable_object_is_a_hard_conflict(self) -> None:
        stored = self.store()
        path = stored["path"]
        entries = self.entries(path)
        path.unlink()
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, contents in sorted(entries.items()):
                archive.writestr(name, contents)
        occupied = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "conflicts"):
            self.store()
        self.assertEqual(occupied, path.read_bytes())

    def test_symlinked_cache_parent_and_archive_mutation_are_rejected(self) -> None:
        real_cache = self.root / "real-cache"
        real_cache.mkdir()
        linked_cache = self.root / "linked-cache"
        try:
            linked_cache.symlink_to(real_cache, target_is_directory=True)
        except OSError:
            return
        with self.assertRaises(ValueError):
            store_local_object(self.stage, self.receipt_path, linked_cache)

        stored = self.store()
        mutable = self.root / "mutable.zip"
        mutable.write_bytes(stored["path"].read_bytes())
        original = product_restore._open_safe_regular

        def open_then_append(path: Path, label: str):
            descriptor, metadata = original(path, label)
            if Path(path) == mutable:
                with mutable.open("ab") as output:
                    output.write(b"changed")
            return descriptor, metadata

        with mock.patch.object(
            product_restore,
            "_open_safe_regular",
            side_effect=open_then_append,
        ), self.assertRaises(CacheObjectError):
            verify_object(
                mutable,
                build_key=self.receipt["buildKey"],
                receipt_sha256=self.receipt_sha256,
            )

    def test_local_missing_hit_and_existing_destination_are_distinct(self) -> None:
        destination = self.root / "local-restore"
        missing = restore_local_object(
            self.cache,
            self.receipt["buildKey"],
            self.receipt_sha256,
            destination,
        )
        self.assertEqual(("miss", "local-missing"), (missing["status"], missing["reason"]))
        self.store()
        hit = restore_local_object(
            self.cache,
            self.receipt["buildKey"],
            self.receipt_sha256,
            destination,
        )
        self.assertEqual(("hit", "local-hit"), (hit["status"], hit["reason"]))
        sentinel = destination / "sentinel"
        sentinel.write_bytes(b"keep")
        with self.assertRaises(ValueError):
            restore_local_object(
                self.cache,
                self.receipt["buildKey"],
                self.receipt_sha256,
                destination,
            )
        self.assertEqual(b"keep", sentinel.read_bytes())


if __name__ == "__main__":
    unittest.main()
