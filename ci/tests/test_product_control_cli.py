from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from ci.products.inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    sha256_bytes,
    write_canonical_json,
)
from ci.products.receipt import compute_build_key, write_output_manifest, write_phase_receipt
from ci.products.restore import object_relative_path


REPOSITORY = Path(__file__).resolve().parents[2]
DIGEST_A = sha256_bytes(b"a")
DIGEST_B = sha256_bytes(b"b")
COMMIT = "a" * 40
TREE = "b" * 40


class ProductControlCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.plan_relative_path = "codex-agent-core/src/jvmMain/kotlin/example/Value.kt"
        self.plan_source = self.root / self.plan_relative_path
        self.plan_source.parent.mkdir(parents=True)
        self.plan_source.write_bytes(b"a")
        subprocess.run(("git", "init", "-q"), cwd=self.root, check=True)
        subprocess.run(("git", "config", "user.email", "fixture@example.invalid"), cwd=self.root, check=True)
        subprocess.run(("git", "config", "user.name", "Fixture"), cwd=self.root, check=True)
        subprocess.run(("git", "add", self.plan_relative_path), cwd=self.root, check=True)
        subprocess.run(("git", "commit", "-qm", "first"), cwd=self.root, check=True)
        self.plan_revision = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=self.root, check=True, capture_output=True, text=True,
        ).stdout.strip()

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "-m", "ci.products", *arguments],
            cwd=REPOSITORY,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    @staticmethod
    def inventory() -> list[dict[str, object]]:
        return [{"relativePath": "source/value.kt", "bytes": 1, "sha256": DIGEST_A}]

    @classmethod
    def inputs(cls) -> dict[str, object]:
        inventory = cls.inventory()
        return {
            "inventory": inventory,
            "phaseInputDigest": sha256_bytes(canonical_json_bytes(inventory)),
            "versionIdentity": "0.2.0",
            "upstreamArtifacts": [],
            "toolchainProfileDigest": DIGEST_A,
            "flagsDigest": DIGEST_B,
            "outputSchemaVersion": 1,
        }

    @staticmethod
    def producer() -> dict[str, object]:
        return {
            "repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml",
            "commit": COMMIT,
            "tree": TREE,
            "event": "pull_request",
            "runId": 1,
            "runAttempt": 1,
            "pullRequest": 31,
        }

    def write_request(self, name: str, value: object) -> Path:
        path = self.root / name
        write_canonical_json(path, value)
        return path

    def stage_and_receipt(self) -> tuple[Path, Path, dict[str, object]]:
        stage = self.root / "stage"
        payload = stage / "outputs/value.bin"
        payload.parent.mkdir(parents=True)
        payload.write_bytes(b"value")
        write_output_manifest(
            stage,
            "sdk",
            "sdk-core",
            "package",
            "common",
            "0.2.0",
            {"package": "outputs"},
        )
        inputs = self.inputs()
        build_key = compute_build_key(
            product="sdk",
            component="sdk-core",
            phase="package",
            target="common",
            inputs=inputs,
        )
        receipt_root = self.root / "receipt"
        receipt_root.mkdir()
        receipt = write_phase_receipt(
            stage,
            receipt_root,
            "sdk",
            "sdk-core",
            "package",
            "common",
            "0.2.0",
            build_key,
            inputs,
            self.producer(),
            "development",
        )
        return stage, receipt_root / "phase-receipt.json", receipt

    def test_plan_stdout_and_file_outputs_are_identical_canonical_bytes(self) -> None:
        request = self.write_request("plan.json", {
            "schemaVersion": 1,
            "product": "contract",
            "component": "contract",
            "phase": "binary",
            "target": "common",
            "repositoryRoot": str(self.root),
            "repositoryRevision": self.plan_revision,
            "versions": {
                "contract": "0.2.0",
                "runtime-compatibility": "0.2.0",
                "runtime-release": "0.2.0",
                "sdk": "0.2.0",
            },
            "upstreamReceipts": [],
            "contractEvidence": None,
            "toolchainProfileDigest": DIGEST_A,
            "flagsDigest": DIGEST_B,
            "outputSchemaVersion": 1,
        })
        stdout = self.run_cli("plan", "--request", str(request), "--output", "-")
        output = self.root / "plan-output.json"
        stored = self.run_cli("plan", "--request", str(request), "--output", str(output))
        self.assertEqual(0, stdout.returncode, stdout.stderr)
        self.assertEqual(0, stored.returncode, stored.stderr)
        self.assertEqual(stdout.stdout, output.read_bytes())
        self.assertEqual(stdout.stdout, canonical_json_bytes(load_canonical_json_bytes(stdout.stdout)))
        first = load_canonical_json_bytes(stdout.stdout)
        self.plan_source.write_bytes(b"b")
        dirty = self.run_cli("plan", "--request", str(request), "--output", "-")
        self.assertEqual(0, dirty.returncode, dirty.stderr)
        self.assertEqual(first, load_canonical_json_bytes(dirty.stdout))
        subprocess.run(("git", "add", self.plan_relative_path), cwd=self.root, check=True)
        subprocess.run(("git", "commit", "-qm", "second"), cwd=self.root, check=True)
        request_value = load_canonical_json_bytes(request.read_bytes())
        request_value["repositoryRevision"] = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=self.root, check=True, capture_output=True, text=True,
        ).stdout.strip()
        write_canonical_json(request, request_value)
        changed = self.run_cli("plan", "--request", str(request), "--output", "-")
        self.assertEqual(0, changed.returncode, changed.stderr)
        second = load_canonical_json_bytes(changed.stdout)
        self.assertNotEqual(first["inputs"]["phaseInputDigest"], second["inputs"]["phaseInputDigest"])
        self.assertNotEqual(first["buildKey"], second["buildKey"])

        request_value["repositoryRevision"] = "HEAD"
        write_canonical_json(request, request_value)
        output.write_bytes(b"stale")
        invalid_revision = self.run_cli(
            "plan", "--request", str(request), "--output", str(output),
        )
        self.assertEqual(2, invalid_revision.returncode)
        self.assertFalse(output.exists())

    def test_receipt_cli_writes_only_the_exact_phase_receipt(self) -> None:
        stage = self.root / "receipt-stage"
        payload = stage / "outputs/value.bin"
        payload.parent.mkdir(parents=True)
        payload.write_bytes(b"value")
        write_output_manifest(
            stage, "sdk", "sdk-core", "package", "common", "0.2.0", {"package": "outputs"},
        )
        inputs = self.inputs()
        build_key = compute_build_key(
            product="sdk", component="sdk-core", phase="package", target="common", inputs=inputs,
        )
        request = self.write_request("receipt-request.json", {
            "schemaVersion": 1,
            "product": "sdk",
            "component": "sdk-core",
            "phase": "package",
            "target": "common",
            "productVersion": "0.2.0",
            "expectedBuildKey": build_key,
            "inputs": inputs,
            "producer": self.producer(),
            "trustDomain": "development",
        })
        receipt_root = self.root / "receipt-output"
        receipt_root.mkdir()
        result = self.run_cli(
            "receipt", "write-phase-receipt",
            "--stage-root", str(stage),
            "--receipt-root", str(receipt_root),
            "--request", str(request),
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(b"", result.stdout)
        receipt = receipt_root / "phase-receipt.json"
        self.assertEqual(receipt.read_bytes(), canonical_json_bytes(load_canonical_json_bytes(receipt.read_bytes())))

    def test_local_store_restore_and_miss_reports_are_exact(self) -> None:
        stage, receipt_path, receipt = self.stage_and_receipt()
        cache = self.root / "cache"
        stored = self.run_cli(
            "restore", "store-local",
            "--stage-root", str(stage),
            "--receipt", str(receipt_path),
            "--cache-root", str(cache),
            "--output", "-",
        )
        self.assertEqual(0, stored.returncode, stored.stderr)
        stored_value = load_canonical_json_bytes(stored.stdout)
        self.assertEqual("published", stored_value["status"])

        destination = self.root / "restored"
        restored = self.run_cli(
            "restore", "restore-local",
            "--build-key", receipt["buildKey"],
            "--receipt-sha256", stored_value["receiptSha256"],
            "--destination", str(destination),
            "--cache-root", str(cache),
            "--output", "-",
        )
        self.assertEqual(0, restored.returncode, restored.stderr)
        restored_value = load_canonical_json_bytes(restored.stdout)
        self.assertEqual(("hit", "local-hit"), (restored_value["status"], restored_value["reason"]))
        self.assertEqual(receipt, restored_value["receipt"])
        self.assertEqual(b"value", (destination / "outputs/value.bin").read_bytes())

        missing = self.run_cli(
            "restore", "restore-local",
            "--build-key", DIGEST_A,
            "--receipt-sha256", DIGEST_B,
            "--destination", str(self.root / "missing"),
            "--cache-root", str(cache),
            "--output", "-",
        )
        self.assertEqual(0, missing.returncode, missing.stderr)
        self.assertEqual(
            ("miss", "local-missing"),
            tuple(load_canonical_json_bytes(missing.stdout)[key] for key in ("status", "reason")),
        )

    def test_corrupt_local_object_is_reported_without_mutation(self) -> None:
        stage, receipt_path, receipt = self.stage_and_receipt()
        cache = self.root / "cache"
        stored = self.run_cli(
            "restore", "store-local", "--stage-root", str(stage), "--receipt", str(receipt_path),
            "--cache-root", str(cache), "--output", "-",
        )
        value = load_canonical_json_bytes(stored.stdout)
        archive = cache / object_relative_path(receipt["buildKey"], value["receiptSha256"])
        archive.chmod(0o644)
        archive.write_bytes(b"corrupt")
        result = self.run_cli(
            "restore", "restore-local",
            "--build-key", receipt["buildKey"],
            "--receipt-sha256", value["receiptSha256"],
            "--destination", str(self.root / "corrupt-destination"),
            "--cache-root", str(cache),
            "--output", "-",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        report = load_canonical_json_bytes(result.stdout)
        self.assertEqual(("miss", "local-corrupt"), (report["status"], report["reason"]))
        self.assertEqual(b"corrupt", archive.read_bytes())
        self.assertFalse((self.root / "corrupt-destination").exists())

    def test_transport_cli_keeps_retrieval_provenance_separate(self) -> None:
        stage, receipt_path, receipt = self.stage_and_receipt()
        cache = self.root / "cache"
        stored = self.run_cli(
            "restore", "store-local", "--stage-root", str(stage), "--receipt", str(receipt_path),
            "--cache-root", str(cache), "--output", "-",
        )
        stored_value = load_canonical_json_bytes(stored.stdout)
        request_value = {
            "schemaVersion": 1,
            "buildKey": receipt["buildKey"],
            "receiptSha256": stored_value["receiptSha256"],
            "objectSha256": stored_value["objectSha256"],
            "source": {
                "kind": "local",
                "cacheRelativePath": stored_value["cacheRelativePath"],
            },
            "consumer": {
                "kind": "local",
                "repository": "codex-agent-labs/codex-agent",
                "commit": COMMIT,
                "tree": TREE,
            },
        }
        request = self.write_request("transport.json", request_value)
        result = self.run_cli(
            "restore", "write-transport",
            "--request", str(request),
            "--cache-root", str(cache),
            "--output", "-",
        )
        self.assertEqual(0, result.returncode, result.stderr)
        report = load_canonical_json_bytes(result.stdout)
        self.assertEqual("published", report["status"])
        self.assertEqual(canonical_json_bytes(request_value), (cache / report["cacheRelativePath"]).read_bytes())
        self.assertEqual(receipt_path.read_bytes(), canonical_json_bytes(receipt))

    def test_unknown_and_noncanonical_requests_fail_with_exit_two_and_no_output(self) -> None:
        unknown = self.run_cli("unknown")
        self.assertEqual(2, unknown.returncode)

        request = self.root / "noncanonical.json"
        request.write_bytes(b'{ "schemaVersion": 1 }\n')
        output = self.root / "stale.json"
        output.write_bytes(b"stale")
        malformed = self.run_cli("plan", "--request", str(request), "--output", str(output))
        self.assertEqual(2, malformed.returncode)
        self.assertFalse(output.exists())

        receipt_root = self.root / "stale-receipt"
        receipt_root.mkdir()
        stale_receipt = receipt_root / "phase-receipt.json"
        stale_receipt.write_bytes(b"stale")
        malformed_receipt = self.run_cli(
            "receipt", "write-phase-receipt",
            "--stage-root", str(self.root / "unused-stage"),
            "--receipt-root", str(receipt_root),
            "--request", str(request),
        )
        self.assertEqual(2, malformed_receipt.returncode)
        self.assertFalse(stale_receipt.exists())

        external = self.root / "external-receipt"
        external.mkdir()
        external_receipt = external / "phase-receipt.json"
        external_receipt.write_bytes(b"external")
        linked = self.root / "linked-receipt"
        try:
            linked.symlink_to(external, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symbolic links are unavailable: {error}")
        unsafe_receipt = self.run_cli(
            "receipt", "write-phase-receipt",
            "--stage-root", str(self.root / "unused-stage"),
            "--receipt-root", str(linked),
            "--request", str(request),
        )
        self.assertEqual(2, unsafe_receipt.returncode)
        self.assertEqual(b"external", external_receipt.read_bytes())

        extra = self.run_cli("restore", "store-local", "--unknown")
        self.assertEqual(2, extra.returncode)

    def test_contract_consumer_rejects_malformed_versions_and_removes_stale_output(self) -> None:
        base = {
            "schemaVersion": 1,
            "product": "runtime",
            "component": "jvm",
            "phase": "binary",
            "target": "jvm",
            "repositoryRoot": str(self.root),
            "repositoryRevision": self.plan_revision,
            "upstreamReceipts": [],
            "contractEvidence": {
                "stageRoot": "missing-stage",
                "phaseReceipt": "missing-receipt",
                "publicKey": "missing-key",
                "expectedTrustDomain": "development",
                "keyring": None,
                "keysDirectory": None,
            },
            "toolchainProfileDigest": DIGEST_A,
            "flagsDigest": DIGEST_B,
            "outputSchemaVersion": 1,
        }
        malformed_versions = (
            {},
            [],
            {
                "contract": "0.2.0",
                "runtime-compatibility": "0.2.0",
                "runtime-release": "0.2.0",
                "sdk": "0.2.0",
                "extra": "0.2.0",
            },
        )
        for index, versions in enumerate(malformed_versions):
            request = self.write_request(f"bad-versions-{index}.json", {
                **base,
                "versions": versions,
            })
            output = self.root / f"stale-plan-{index}.json"
            output.write_bytes(b"stale")
            result = self.run_cli("plan", "--request", str(request), "--output", str(output))
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
