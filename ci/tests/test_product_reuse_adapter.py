from __future__ import annotations

import json
from contextlib import nullcontext, redirect_stderr
import io
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))

import product_reuse  # noqa: E402
import products.inventory as product_inventory  # noqa: E402
from products.inventory import canonical_json_bytes, sha256_bytes  # noqa: E402
from products.plan import plan_phase  # noqa: E402
from products.receipt import (  # noqa: E402
    output_inventory_digest,
    validate_phase_receipt,
    write_output_manifest,
)
from products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId, published_coordinate  # noqa: E402
from products.restore import (  # noqa: E402
    finalize_phase_object,
    store_local_object,
    transport_relative_path,
    verify_carrier,
    verify_phase_shard,
    write_carrier,
)
from products.selection import phase_git_inventory  # noqa: E402
from products.signatures import generate_development_key, sign_manifest  # noqa: E402


COMMIT = "a" * 40
TREE = "b" * 40
VERSIONS = {
    "contract": "0.2.0",
    "runtime-release": "0.2.0",
    "runtime-compatibility": "0.2.0",
    "sdk": "0.2.0",
}


def impact_plan(*, changed: list[str], full_requested: bool = False, event: str = "pull_request") -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "event": event,
        "repository": "codex-agent-labs/codex-agent",
        "pullRequest": 31 if event != "workflow_dispatch" else None,
        "baseCommit": "c" * 40,
        "headCommit": COMMIT,
        "validationCommit": COMMIT,
        "validationTree": TREE,
        "mergeReady": True,
        "remoteBuildAuthorized": True,
        "remoteBuildAuthorizationReason": "pull-request-final" if event == "pull_request" else "workflow-dispatch",
        "androidEvidenceRequired": False,
        "fullRequested": full_requested,
        "full": True,
        "unknownPaths": [],
        "changedPaths": changed,
        "lanes": {},
    }


class ProductReuseAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plan_path = self.root / "impact-plan.json"
        self.output = self.root / "github-output"
        self.destination = self.root / "reuse"

    def write_plan(self, value: dict[str, object]) -> None:
        self.plan_path.write_text(json.dumps(value), encoding="utf-8")

    def contract_advance_controls(self) -> dict[str, object]:
        root = self.root.resolve()
        plan = impact_plan(changed=["known.kt"])
        producer = product_reuse._consumer(
            plan, {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
        )["producer"]
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        closure = product_reuse._dependency_closure((contract,))
        authorities = [{
            **product_reuse._identity_record(instance),
            "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
            "outputSchemaVersion": 1,
        } for instance in closure]
        discovery = root / "discovery-controls"
        discovery.mkdir()
        request = {
            "schemaVersion": 1,
            "requestType": "reuse-wave",
            "repository": plan["repository"],
            "pullRequest": plan["pullRequest"],
            "repositoryRoot": str(root),
            "repositoryRevision": COMMIT,
            "artifactRoot": str(root / "build/product-reuse"),
            "requested": [product_reuse._identity_record(contract)],
            "versions": VERSIONS,
            "phaseAuthorities": authorities,
            "contractEvidence": None,
            "availableObjects": [],
            "catalogs": {
                "stable": [], "promotedMain": None, "samePr": None, "local": None,
            },
        }
        for name, value in (
            ("producer.json", producer),
            ("contract-reuse-request.json", request),
        ):
            (discovery / name).write_bytes(canonical_json_bytes(value))
        self.write_plan(plan)
        return {
            "root": root,
            "plan": plan,
            "producer": producer,
            "contract": contract,
            "authorities": authorities,
            "discovery": discovery,
            "request": request,
        }

    def contract_repository(self) -> tuple[Path, str, str]:
        repository = self.root.resolve() / "contract-repository"
        files = {
            "codex-agent-core/src/commonMain/kotlin/example.kt": "package example\n",
            "gradle/release/versions/contract.txt": "0.2.0\n",
            "gradle/release/versions/runtime.txt": "0.2.0\n",
            "gradle/release/versions/sdk.txt": "0.2.0\n",
        }
        for relative, value in files.items():
            path = repository / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
        subprocess.run(("git", "init", "-q"), cwd=repository, check=True)
        subprocess.run(
            ("git", "config", "user.email", "fixture@example.invalid"),
            cwd=repository,
            check=True,
        )
        subprocess.run(("git", "config", "user.name", "Fixture"), cwd=repository, check=True)
        subprocess.run(("git", "add", "."), cwd=repository, check=True)
        subprocess.run(("git", "commit", "-qm", "fixture"), cwd=repository, check=True)
        commit = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=repository, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        tree = subprocess.run(
            ("git", "rev-parse", "HEAD^{tree}"), cwd=repository, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        return repository, commit, tree

    @staticmethod
    def phase_object(
        root: Path,
        name: str,
        phase_plan: dict[str, object],
        producer: dict[str, object],
    ) -> tuple[dict[str, object], Path]:
        stage = root / f"{name}-stage"
        payload = stage / f"outputs/{name}.bin"
        payload.parent.mkdir(parents=True)
        payload.write_bytes(str(phase_plan["buildKey"]).encode())
        manifest = write_output_manifest(
            stage,
            phase_plan["product"],
            phase_plan["component"],
            phase_plan["phase"],
            phase_plan["target"],
            "0.2.0",
            {"artifact": "outputs"},
        )
        receipt = validate_phase_receipt({
            "schemaVersion": 1,
            "product": phase_plan["product"],
            "component": phase_plan["component"],
            "phase": phase_plan["phase"],
            "target": phase_plan["target"],
            "productVersion": "0.2.0",
            "buildKey": phase_plan["buildKey"],
            "inputs": phase_plan["inputs"],
            "outputs": manifest["outputs"],
            "producer": producer,
            "trustDomain": "development",
            "result": "success",
        })
        receipt_path = root / f"{name}-receipt.json"
        receipt_path.write_bytes(canonical_json_bytes(receipt))
        stored = store_local_object(stage, receipt_path, root / "remote-objects")
        return {
            "receipt": receipt,
            "receiptBytes": receipt_path.read_bytes(),
            "receiptSha256": stored["receiptSha256"],
            "objectSha256": stored["objectSha256"],
        }, stored["path"]

    @staticmethod
    def product_index_entry(envelope: dict[str, object]) -> dict[str, object]:
        receipt = envelope["receipt"]
        artifact = receipt["outputs"][0]
        return {
            "buildKey": receipt["buildKey"],
            "product": receipt["product"],
            "component": receipt["component"],
            "phase": receipt["phase"],
            "target": receipt["target"],
            "productVersion": receipt["productVersion"],
            "coordinate": published_coordinate(receipt["product"], receipt["component"]),
            "outputInventoryDigest": output_inventory_digest(receipt["outputs"]),
            "outputs": receipt["outputs"],
            "artifactName": artifact["relativePath"],
            "artifactSha256": artifact["sha256"],
            "receiptSha256": envelope["receiptSha256"],
        }

    def run_discover(self, plan: dict[str, object], **patches: object) -> dict[str, object]:
        self.write_plan(plan)
        selection = patches.pop("selection", mock.Mock(instances=(), unknown_paths=()))
        environment = patches.pop("environ", {})
        with mock.patch.object(product_reuse, "validate_remote_build_authorization"), \
                mock.patch.object(product_reuse, "validate_legacy_lane_projection"), \
                mock.patch.object(product_reuse, "_git_value", side_effect=(COMMIT, TREE)), \
                mock.patch.object(product_reuse, "classify_paths", return_value=selection), \
                (mock.patch.multiple(product_reuse, **patches) if patches else nullcontext()):
            return product_reuse.discover(
                self.plan_path, self.destination, self.output,
                repository_root=self.root, environ=environment,
            )

    def outputs(self) -> dict[str, str]:
        return dict(line.split("=", 1) for line in self.output.read_text().splitlines())

    def test_authorities_are_derived_and_native_profiles_fail_closed(self) -> None:
        contract = PhaseInstanceId("contract", "contract", "binary", "common")
        native = PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        with mock.patch.object(product_reuse, "tree_entries", return_value=[]), \
                mock.patch.object(product_reuse, "git_regular_blob_bytes") as read_blob:
            records, reason = product_reuse._authorities(self.root, COMMIT, (contract,))
            self.assertIsNone(reason)
            self.assertEqual([{
                **product_reuse._identity_record(contract),
                "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
                "outputSchemaVersion": 1,
            }], records)
            read_blob.assert_not_called()

            records, reason = product_reuse._authorities(self.root, COMMIT, (native,))
            self.assertIsNone(records)
            self.assertEqual("toolchain-profile-unavailable", reason)
            read_blob.assert_not_called()

    def test_malformed_present_authority_is_a_hard_failure(self) -> None:
        native = PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        profile = product_reuse.required_toolchain_profile(native)
        with mock.patch.object(
            product_reuse,
            "tree_entries",
            return_value=[(f"{product_reuse._PROFILE_ROOT}/{profile}.json", object())],
        ), mock.patch.object(
            product_reuse, "git_regular_blob_bytes", return_value=b"{}"
        ), self.assertRaises(ValueError):
            product_reuse._authorities(self.root, COMMIT, (native,))

    def test_native_profile_lookup_waits_until_contract_is_fully_reused(self) -> None:
        native = PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        contract_records = [{
            **product_reuse._identity_record(instance),
            "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
            "outputSchemaVersion": 1,
        } for instance in product_reuse._dependency_closure((
            PhaseInstanceId("contract", "contract", "metadata", "common"),
        ))]
        contract_result = {
            "schemaVersion": 1,
            "result": "complete",
            "fullReuse": True,
            "phases": [],
            "matrices": {"contract": [], "runtime": [], "sdk": []},
        }
        authorities = mock.Mock(side_effect=(
            (contract_records, None),
            (None, "toolchain-profile-unavailable"),
        ))
        wave = mock.Mock(return_value=contract_result)
        result = self.run_discover(
            impact_plan(changed=["native.kt"]),
            selection=mock.Mock(instances=(native,), unknown_paths=()),
            _authorities=authorities,
            _versions=mock.Mock(return_value=VERSIONS),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
            _wave_request=mock.Mock(return_value={}),
            plan_reuse_wave=wave,
            _contract_evidence=mock.Mock(return_value=object()),
        )
        self.assertEqual("toolchain-profile-unavailable", result["reason"])
        self.assertEqual(2, authorities.call_count)
        wave.assert_called_once()

    def test_native_request_emits_only_the_ready_contract_plan_without_profiles(self) -> None:
        native = PhaseInstanceId("runtime", "linux-x64", "binary", "linux-x64")
        contract_binary = PhaseInstanceId("contract", "contract", "binary", "common")
        contract_records = [{
            **product_reuse._identity_record(instance),
            "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
            "outputSchemaVersion": 1,
        } for instance in product_reuse._dependency_closure((
            PhaseInstanceId("contract", "contract", "metadata", "common"),
        ))]
        phase_plan = {
            "schemaVersion": 1,
            **product_reuse._identity_record(contract_binary),
            "buildKey": sha256_bytes(b"contract-build"),
            "inputs": {"authority": "planner-owned"},
        }

        def contract_wave(_request, *, build_plan_consumer):
            build_plan_consumer(contract_binary, phase_plan)
            return {
                "schemaVersion": 1,
                "result": "build-required",
                "fullReuse": False,
                "phases": [],
                "matrices": {"contract": [{}], "runtime": [], "sdk": []},
            }

        authorities = mock.Mock(return_value=(contract_records, None))
        result = self.run_discover(
            impact_plan(changed=["native.kt"]),
            selection=mock.Mock(instances=(native,), unknown_paths=()),
            _authorities=authorities,
            _versions=mock.Mock(return_value=VERSIONS),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
            _wave_request=mock.Mock(return_value={}),
            plan_reuse_wave=mock.Mock(side_effect=contract_wave),
            environ={"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
        )
        self.assertEqual("product-build-required", result["reason"])
        authorities.assert_called_once()
        self.assertEqual(
            canonical_json_bytes(phase_plan),
            (self.destination / "phase-plans/contract-contract-binary-common.json").read_bytes(),
        )

    def test_no_product_work_is_the_only_vacuous_full_reuse(self) -> None:
        result = self.run_discover(impact_plan(changed=["README.md"]))
        self.assertEqual("no-product-work", result["reason"])
        self.assertTrue(result["fullReuse"])
        self.assertFalse(result["targetJobsRequired"])
        self.assertEqual("false", self.outputs()["target_jobs_required"])
        persisted = json.loads((self.destination / "request.json").read_text())
        self.assertEqual([], persisted["requested"])

    def test_plan_full_does_not_broaden_the_product_selection(self) -> None:
        selected = PhaseInstanceId("contract", "contract", "binary", "common")
        selection = mock.Mock(instances=(selected,), unknown_paths=())
        result = self.run_discover(
            impact_plan(changed=["known.kt"], full_requested=False),
            selection=selection,
            _dependency_closure=mock.Mock(return_value=(selected,)),
            _authorities=mock.Mock(return_value=(None, "phase-authority-unavailable")),
            _versions=mock.Mock(return_value=VERSIONS),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
        )
        self.assertEqual([product_reuse._identity_record(selected)], result["requested"])
        self.assertTrue(result["targetJobsRequired"])

    def test_explicit_full_request_selects_every_registered_phase(self) -> None:
        contract_closure = tuple(
            instance for instance in PHASE_INSTANCE_IDS if instance.product == "contract"
        )
        result = self.run_discover(
            impact_plan(changed=["known.kt"], full_requested=True),
            selection=mock.Mock(instances=(), unknown_paths=()),
            _dependency_closure=mock.Mock(side_effect=lambda requested: (
                contract_closure if requested == (
                    PhaseInstanceId("contract", "contract", "metadata", "common"),
                ) else PHASE_INSTANCE_IDS
            )),
            _authorities=mock.Mock(return_value=([{
                **product_reuse._identity_record(instance),
                "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
                "outputSchemaVersion": 1,
            } for instance in contract_closure], None)),
            _versions=mock.Mock(return_value=VERSIONS),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
            plan_reuse_wave=mock.Mock(return_value={
                "schemaVersion": 1, "result": "build-required", "fullReuse": False,
                "phases": [], "matrices": {"contract": [{}], "runtime": [], "sdk": []},
            }),
        )
        self.assertEqual(len(PHASE_INSTANCE_IDS), len(result["requested"]))
        self.assertEqual("product-build-required", result["reason"])

    def test_unknown_path_selects_every_registered_phase(self) -> None:
        plan = impact_plan(changed=["unknown/new.file"])
        plan["unknownPaths"] = ["unknown/new.file"]
        contract_closure = tuple(
            instance for instance in PHASE_INSTANCE_IDS if instance.product == "contract"
        )
        result = self.run_discover(
            plan,
            selection=mock.Mock(instances=PHASE_INSTANCE_IDS, unknown_paths=("unknown/new.file",)),
            _dependency_closure=mock.Mock(side_effect=lambda requested: (
                contract_closure if requested == (
                    PhaseInstanceId("contract", "contract", "metadata", "common"),
                ) else PHASE_INSTANCE_IDS
            )),
            _authorities=mock.Mock(return_value=([{
                **product_reuse._identity_record(instance),
                "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
                "outputSchemaVersion": 1,
            } for instance in contract_closure], None)),
            _versions=mock.Mock(return_value=VERSIONS),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
            plan_reuse_wave=mock.Mock(return_value={
                "schemaVersion": 1, "result": "build-required", "fullReuse": False,
                "phases": [], "matrices": {"contract": [{}], "runtime": [], "sdk": []},
            }),
        )
        self.assertEqual(len(PHASE_INSTANCE_IDS), len(result["requested"]))

    def test_workflow_dispatch_never_discovers_remote_catalogs(self) -> None:
        selected = PhaseInstanceId("contract", "contract", "binary", "common")
        discover_catalogs = mock.Mock()
        result = self.run_discover(
            impact_plan(changed=["known.kt"], event="workflow_dispatch"),
            selection=mock.Mock(instances=(selected,), unknown_paths=()),
            _discover_catalogs=discover_catalogs,
        )
        self.assertEqual("workflow-dispatch-reuse-disabled", result["reason"])
        discover_catalogs.assert_not_called()

    def test_checkout_mismatch_fails_after_writing_safe_default_outputs(self) -> None:
        self.write_plan(impact_plan(changed=[]))
        with mock.patch.object(product_reuse, "validate_remote_build_authorization"), \
                mock.patch.object(product_reuse, "validate_legacy_lane_projection"), \
                mock.patch.object(product_reuse, "_git_value", return_value="d" * 40):
            with self.assertRaisesRegex(ValueError, "Checkout commit"):
                product_reuse.discover(
                    self.plan_path, self.destination, self.output,
                    repository_root=self.root, environ={},
                )
        self.assertEqual("true", self.outputs()["target_jobs_required"])
        self.assertEqual("false", self.outputs()["full_reuse"])

    def test_destination_rejects_leaf_and_parent_symlinks(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        leaf = self.root / "leaf"
        leaf.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unsafe parent"):
            product_reuse._prepare_destination(leaf, self.root)
        parent = self.root / "parent"
        parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unsafe parent"):
            product_reuse._prepare_destination(parent / "reuse", self.root)
        (outside / "existing").mkdir()
        nested = self.root / "nested"
        nested.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "unsafe parent"):
            product_reuse._prepare_destination(nested / "existing" / "reuse", self.root)
        with self.assertRaisesRegex(ValueError, "inside the repository"):
            product_reuse._prepare_destination(outside.parent / "elsewhere", outside)

    def test_matching_catalog_with_unexpected_member_is_rejected(self) -> None:
        catalog = self.root / "catalog.zip"
        index = {
            "schemaVersion": 1,
            "repository": "codex-agent-labs/codex-agent",
            "context": {
                "kind": "pull-request", "pullRequest": 31, "commit": COMMIT, "tree": TREE,
                "runId": 7, "runAttempt": 1,
            },
            "entries": [],
            "trustDomain": "development",
            "signing": {
                "algorithm": "ssh-ed25519", "namespace": "codex-agent-product-v1",
                "keyId": "development", "fingerprint": sha256_bytes(b"key"),
            },
            "producer": {
                "repository": "codex-agent-labs/codex-agent",
                "workflowPath": ".github/workflows/product-validation.yml",
                "commit": COMMIT, "tree": TREE, "event": "pull_request", "runId": 7,
                "runAttempt": 1, "pullRequest": 31,
            },
        }
        with zipfile.ZipFile(catalog, "w") as archive:
            archive.writestr("product-index.json", canonical_json_bytes(index))
            archive.writestr("product-index.sig", b"signature")
            archive.writestr("public-key.pub", b"key")
            archive.writestr("unexpected.txt", b"no")
        artifact = {
            "id": 7,
            "archive_download_url": "https://example.invalid/archive",
            "digest": sha256_bytes(catalog.read_bytes()),
        }
        with mock.patch.object(product_reuse, "download_artifact", return_value=catalog.read_bytes()), \
                mock.patch.object(product_reuse, "validate_product_index", return_value=index):
            with self.assertRaisesRegex(ValueError, "file set"):
                product_reuse._materialize_catalog(
                    "same-pr", artifact, "token", self.root / "materialized",
                    "codex-agent-labs/codex-agent", 31, None, {
                        "id": 7, "run_attempt": 1, "head_sha": COMMIT,
                    },
                )

    def test_catalog_discovery_is_source_ordered_and_downloads_one_artifact_per_index(self) -> None:
        artifacts = [
            {"id": 2, "name": "codex-agent-product-catalog-v1-stable-sdk-0.2.0", "expired": False},
            {"id": 5, "name": "codex-agent-product-catalog-v1-promoted-main-new", "expired": False},
            {"id": 4, "name": "codex-agent-product-catalog-v1-promoted-main-old", "expired": False},
            {"id": 7, "name": "codex-agent-product-catalog-v1-pull-request-31-new", "expired": False},
            {"id": 6, "name": "codex-agent-product-catalog-v1-pull-request-31-old", "expired": False},
        ]
        trust = product_reuse.ReleaseTrust(self.root / "keyring", self.root / "keys")

        def materialize(source: str, artifact: dict[str, object], *_: object) -> product_reuse.Catalog:
            return product_reuse.Catalog(source, {}, str(artifact["id"]), {}, {})

        with mock.patch.object(product_reuse, "paginated_items", return_value=artifacts) as listed, \
                mock.patch.object(product_reuse, "_same_pr_run", return_value={
                    "id": 7, "run_attempt": 1, "head_sha": COMMIT,
                }), \
                mock.patch.object(product_reuse, "_materialize_catalog", side_effect=materialize) as downloaded:
            catalogs = product_reuse._discover_catalogs(
                impact_plan(changed=["known.kt"]), self.root / "catalogs", trust,
                {
                    "GITHUB_TOKEN": "token", "GITHUB_API_URL": "https://api.github.test",
                    "GITHUB_REPOSITORY": "codex-agent-labs/codex-agent",
                },
                {
                    "contract": "0.2.0", "runtime-release": "0.2.0",
                    "runtime-compatibility": "0.2.0", "sdk": "0.2.0",
                },
            )
        self.assertEqual(
            [("stable", "2"), ("promoted-main", "5"), ("same-pr", "7")],
            [(catalog.source, catalog.index_sha256) for catalog in catalogs],
        )
        listed.assert_called_once()
        self.assertEqual(3, downloaded.call_count)

    def test_same_pr_catalog_requires_actual_successful_ci_run_and_matching_claims(self) -> None:
        artifact = {
            "workflow_run": {"id": 7, "head_sha": COMMIT},
        }
        good_run = {
            "id": 7, "run_attempt": 2, "status": "completed", "conclusion": "success",
            "event": "pull_request", "path": ".github/workflows/ci.yml", "head_sha": COMMIT,
            "pull_requests": [{"number": 31}],
        }
        with mock.patch.object(product_reuse, "api_json", return_value=good_run):
            self.assertEqual(
                good_run,
                product_reuse._same_pr_run(
                    artifact, "https://api.github.test", "codex-agent-labs/codex-agent", 31, "token",
                ),
            )
        for change in (
            {"conclusion": "failure"},
            {"path": ".github/workflows/untrusted.yml"},
            {"head_sha": "d" * 40},
            {"pull_requests": [{"number": 32}]},
        ):
            with self.subTest(change=change), mock.patch.object(
                product_reuse, "api_json", return_value={**good_run, **change},
            ):
                with self.assertRaisesRegex(ValueError, "allowed successful CI run"):
                    product_reuse._same_pr_run(
                        artifact, "https://api.github.test", "codex-agent-labs/codex-agent", 31, "token",
                    )

    def test_complete_result_is_reverified_before_jobs_can_be_skipped(self) -> None:
        selected = PhaseInstanceId("contract", "contract", "binary", "common")
        authorities = [{
            **product_reuse._identity_record(selected),
            "toolchainProfileDigest": sha256_bytes(b"toolchain"),
            "flagsDigest": sha256_bytes(b"flags"),
            "outputSchemaVersion": 1,
        }]
        reuse = {
            "schemaVersion": 1, "result": "complete", "fullReuse": True,
            "phases": [], "matrices": {"contract": [], "runtime": [], "sdk": []},
        }
        reverify = mock.Mock()
        result = self.run_discover(
            impact_plan(changed=["known.kt"]),
            selection=mock.Mock(instances=(selected,), unknown_paths=()),
            _dependency_closure=mock.Mock(return_value=(selected,)),
            _authorities=mock.Mock(return_value=(authorities, None)),
            _versions=mock.Mock(return_value={
                "contract": "0.2.0", "runtime-release": "0.2.0",
                "runtime-compatibility": "0.2.0", "sdk": "0.2.0",
            }),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
            plan_reuse_wave=mock.Mock(return_value=reuse),
            _reverify_complete=reverify,
            environ={"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
        )
        reverify.assert_called_once()
        self.assertEqual(
            {
                "kind": "ci",
                "producer": {
                    "repository": "codex-agent-labs/codex-agent",
                    "workflowPath": ".github/workflows/ci.yml",
                    "commit": COMMIT,
                    "tree": TREE,
                    "event": "pull_request",
                    "runId": 7,
                    "runAttempt": 2,
                    "pullRequest": 31,
                },
            },
            reverify.call_args.args[4],
        )
        self.assertEqual("verified-full-reuse", result["reason"])
        self.assertFalse(result["targetJobsRequired"])

    def test_partial_remote_reuse_is_preserved_as_an_exact_prefix_carrier(self) -> None:
        requested = PhaseInstanceId("contract", "contract", "metadata", "common")
        closure = product_reuse._dependency_closure((requested,))
        binary = PhaseInstanceId("contract", "contract", "binary", "common")
        package = PhaseInstanceId("contract", "contract", "package", "common")
        build_key = sha256_bytes(b"binary-plan")
        package_build_key = sha256_bytes(b"package-plan")
        receipt_digest = sha256_bytes(b"binary-receipt")
        object_digest = sha256_bytes(b"binary-object")
        phases = []
        for instance in closure:
            reused = instance == binary
            build = instance == package
            phases.append({
                **product_reuse._identity_record(instance),
                "buildKey": build_key if reused else package_build_key if build else None,
                "state": "reused" if reused else "build" if build else "waiting",
                "source": "same-pr" if reused else None,
                "transportSource": {
                    "kind": "same-pr",
                    "indexSha256": sha256_bytes(b"index"),
                    "artifactName": "contract.bin",
                    "artifactSha256": sha256_bytes(b"artifact"),
                } if reused else None,
                "receiptSha256": receipt_digest if reused else None,
                "objectSha256": object_digest if reused else None,
                "misses": [
                    {"source": source, "reason": "fixture-miss"}
                    for source in product_reuse.SOURCES
                ] if build else [
                    {"source": source, "reason": "fixture-miss"}
                    for source in product_reuse.SOURCES[:2]
                ] if reused else [],
            })
        result = {
            "schemaVersion": 1,
            "result": "build-required",
            "fullReuse": False,
            "phases": phases,
            "matrices": {"contract": [{
                **product_reuse._identity_record(package),
                "buildKey": package_build_key,
            }], "runtime": [], "sdk": []},
        }
        object_path = self.root / "binary.zip"
        catalog = product_reuse.Catalog(
            "same-pr", {}, sha256_bytes(b"index"), {}, {build_key: object_path},
        )
        receipt = {**product_reuse._identity_record(binary)}
        with mock.patch.object(
            product_reuse,
            "verify_object",
            return_value={"receipt": receipt},
        ), mock.patch.object(product_reuse, "write_carrier") as write:
            self.assertTrue(product_reuse._write_reused_carrier(
                result,
                (requested,),
                [catalog],
                self.root / "carrier",
                {"kind": "ci", "producer": {}},
                require_complete=False,
            ))
        normalized = write.call_args.args[1]
        self.assertEqual([phases[closure.index(binary)]], normalized["phases"])
        self.assertEqual((binary,), write.call_args.args[2])
        self.assertEqual({binary: object_path}, write.call_args.args[3])
        self.assertEqual("complete", normalized["result"])
        self.assertTrue(normalized["fullReuse"])

        contradictions = []
        wrong_completion = json.loads(json.dumps(result))
        wrong_completion["fullReuse"] = True
        contradictions.append(("contradicts", wrong_completion))
        wrong_matrix = json.loads(json.dumps(result))
        wrong_matrix["matrices"]["contract"] = []
        contradictions.append(("matrices", wrong_matrix))
        wrong_schema = json.loads(json.dumps(result))
        wrong_schema["schemaVersion"] = 2
        contradictions.append(("schemaVersion", wrong_schema))
        unknown_result_key = json.loads(json.dumps(result))
        unknown_result_key["unexpected"] = True
        contradictions.append(("fields are invalid", unknown_result_key))
        unknown_phase_key = json.loads(json.dumps(result))
        unknown_phase_key["phases"][0]["unexpected"] = True
        contradictions.append(("fields are invalid", unknown_phase_key))
        build_evidence = json.loads(json.dumps(result))
        build_evidence["phases"][closure.index(package)]["receiptSha256"] = receipt_digest
        contradictions.append(("materialized evidence", build_evidence))
        waiting_evidence = json.loads(json.dumps(result))
        waiting_evidence["phases"][2]["source"] = "stable"
        contradictions.append(("materialized evidence", waiting_evidence))
        missing_build_miss = json.loads(json.dumps(result))
        missing_build_miss["phases"][closure.index(package)]["misses"].pop()
        contradictions.append(("every lookup miss", missing_build_miss))
        reordered_build_misses = json.loads(json.dumps(result))
        reordered_build_misses["phases"][closure.index(package)]["misses"].reverse()
        contradictions.append(("every lookup miss", reordered_build_misses))
        duplicate_build_miss = json.loads(json.dumps(result))
        duplicate_build_miss["phases"][closure.index(package)]["misses"].append(
            duplicate_build_miss["phases"][closure.index(package)]["misses"][-1]
        )
        contradictions.append(("every lookup miss", duplicate_build_miss))
        missing_reuse_miss = json.loads(json.dumps(result))
        missing_reuse_miss["phases"][closure.index(binary)]["misses"].pop()
        contradictions.append(("source ordered", missing_reuse_miss))
        reordered_reuse_misses = json.loads(json.dumps(result))
        reordered_reuse_misses["phases"][closure.index(binary)]["misses"].reverse()
        contradictions.append(("source ordered", reordered_reuse_misses))
        duplicate_reuse_miss = json.loads(json.dumps(result))
        duplicate_reuse_miss["phases"][closure.index(binary)]["misses"].append(
            duplicate_reuse_miss["phases"][closure.index(binary)]["misses"][-1]
        )
        contradictions.append(("source ordered", duplicate_reuse_miss))
        for error, contradictory in contradictions:
            with self.subTest(error=error), mock.patch.object(
                product_reuse,
                "verify_object",
                return_value={"receipt": receipt},
            ), mock.patch.object(product_reuse, "write_carrier") as rejected_write:
                with self.assertRaisesRegex(ValueError, error):
                    product_reuse._write_reused_carrier(
                        contradictory,
                        (requested,),
                        [catalog],
                        self.root / "rejected-carrier",
                        {"kind": "ci", "producer": {}},
                        require_complete=False,
                    )
                rejected_write.assert_not_called()

    def test_partial_reuse_carrier_rejects_a_nonclosed_phase_set(self) -> None:
        requested = PhaseInstanceId("contract", "contract", "metadata", "common")
        closure = product_reuse._dependency_closure((requested,))
        package = PhaseInstanceId("contract", "contract", "package", "common")
        build_key = sha256_bytes(b"package-plan")
        receipt_digest = sha256_bytes(b"package-receipt")
        object_digest = sha256_bytes(b"package-object")
        phases = [{
            **product_reuse._identity_record(instance),
            "buildKey": build_key if instance == package else None,
            "state": "reused" if instance == package else "waiting",
            "source": "stable" if instance == package else None,
            "transportSource": {
                "kind": "stable",
                "indexSha256": sha256_bytes(b"index"),
                "artifactName": "contract.bin",
                "artifactSha256": sha256_bytes(b"artifact"),
            } if instance == package else None,
            "receiptSha256": receipt_digest if instance == package else None,
            "objectSha256": object_digest if instance == package else None,
            "misses": [],
        } for instance in closure]
        result = {
            "schemaVersion": 1,
            "result": "build-required",
            "fullReuse": False,
            "phases": phases,
            "matrices": {"contract": [], "runtime": [], "sdk": []},
        }
        catalog = product_reuse.Catalog(
            "stable", {}, sha256_bytes(b"index"), {}, {build_key: self.root / "package.zip"},
        )
        with mock.patch.object(
            product_reuse,
            "verify_object",
            return_value={"receipt": product_reuse._identity_record(package)},
        ), mock.patch.object(product_reuse, "write_carrier") as write:
            with self.assertRaisesRegex(ValueError, "dependency-closed"):
                product_reuse._write_reused_carrier(
                    result,
                    (requested,),
                    [catalog],
                    self.root / "carrier",
                    {"kind": "ci", "producer": {}},
                    require_complete=False,
                )
        write.assert_not_called()

    def test_reused_carrier_preserves_real_object_and_receipt_bytes(self) -> None:
        binary = PhaseInstanceId("contract", "contract", "binary", "common")
        resolved_root = self.root.resolve()
        stage = resolved_root / "stage"
        output = stage / "outputs/value.bin"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"value")
        write_output_manifest(
            stage, "contract", "contract", "binary", "common", "0.2.0",
            {"artifact": "outputs"},
        )
        plan = plan_phase(
            binary,
            inventory=[{"relativePath": "input.kt", "bytes": 1, "sha256": sha256_bytes(b"i")}],
            versions=VERSIONS,
            upstream_receipts=[],
            toolchain_profile_digest=product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            flags_digest=product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
        )
        consumer = product_reuse._consumer(
            impact_plan(changed=["input.kt"]),
            {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "1"},
        )
        shard = resolved_root / "shard"
        finalize_phase_object(
            stage_root=stage,
            phase_plan=plan,
            producer=consumer["producer"],
            product_version="0.2.0",
            trust_domain="development",
            destination=shard,
        )
        verified_shard = verify_phase_shard(shard, binary)
        descriptor = verified_shard
        source = {
            "kind": "same-pr",
            "indexSha256": sha256_bytes(b"index"),
            "artifactName": "value.bin",
            "artifactSha256": sha256_bytes(b"value"),
        }
        result = {
            "schemaVersion": 1,
            "result": "complete",
            "fullReuse": True,
            "phases": [{
                **product_reuse._identity_record(binary),
                "buildKey": descriptor["buildKey"],
                "state": "reused",
                "source": "same-pr",
                "transportSource": source,
                "receiptSha256": descriptor["receiptSha256"],
                "objectSha256": descriptor["objectSha256"],
                "misses": [
                    {"source": name, "reason": "fixture-miss"}
                    for name in product_reuse.SOURCES[:2]
                ],
            }],
            "matrices": {"contract": [], "runtime": [], "sdk": []},
        }
        catalog = product_reuse.Catalog(
            "same-pr", {}, source["indexSha256"], {}, {
                descriptor["buildKey"]: shard / descriptor["objectPath"],
            },
        )
        carrier = resolved_root / "carrier"
        self.assertTrue(product_reuse._write_reused_carrier(
            result, (binary,), [catalog], carrier, consumer, require_complete=False,
        ))
        verified_carrier = verify_carrier(carrier, (binary,), consumer)
        self.assertEqual(
            (shard / "phase-receipt.json").read_bytes(),
            verified_carrier["objects"][0]["receiptBytes"],
        )

    def test_contract_advance_rejects_mutated_request_and_producer_controls(self) -> None:
        fixture = self.contract_advance_controls()
        request_path = fixture["discovery"] / "contract-reuse-request.json"
        producer_path = fixture["discovery"] / "producer.json"
        cases = (
            ("schemaVersion", 2, "schemaVersion"),
            ("repository", "other/repository", "repository"),
            ("availableObjects", [{}], "availableObjects"),
            ("unexpected", True, "fields are invalid"),
        )
        for field, value, message in cases:
            with self.subTest(field=field):
                mutated = json.loads(json.dumps(fixture["request"]))
                mutated[field] = value
                request_path.write_bytes(canonical_json_bytes(mutated))
                with mock.patch.object(
                    product_reuse, "_validate_plan", return_value=fixture["plan"],
                ), mock.patch.object(
                    product_reuse,
                    "_authorities",
                    return_value=(fixture["authorities"], None),
                ), mock.patch.object(
                    product_reuse, "_versions", return_value=VERSIONS,
                ), self.assertRaisesRegex(ValueError, message):
                    product_reuse.advance_contract(
                        self.plan_path,
                        fixture["discovery"],
                        None,
                        [],
                        fixture["root"] / f"rejected-{field}",
                        fixture["root"] / f"output-{field}",
                        repository_root=fixture["root"],
                        environ={"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
                    )
                self.assertFalse((fixture["root"] / f"rejected-{field}").exists())
                self.assertEqual(
                    {"contract_complete": "false", "next_phase_required": "false"},
                    dict(
                        line.split("=", 1)
                        for line in (fixture["root"] / f"output-{field}").read_text().splitlines()
                    ),
                )
        request_path.write_bytes(canonical_json_bytes(fixture["request"]))

        mutated_producer = dict(fixture["producer"])
        mutated_producer["runAttempt"] = 3
        producer_path.write_bytes(canonical_json_bytes(mutated_producer))
        with mock.patch.object(
            product_reuse, "_validate_plan", return_value=fixture["plan"],
        ), self.assertRaisesRegex(ValueError, "current workflow run"):
            product_reuse.advance_contract(
                self.plan_path,
                fixture["discovery"],
                None,
                [],
                fixture["root"] / "rejected-producer",
                fixture["root"] / "output-producer",
                repository_root=fixture["root"],
                environ={"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
            )
        self.assertFalse((fixture["root"] / "rejected-producer").exists())

        producer_path.write_bytes(canonical_json_bytes(fixture["producer"]))
        (fixture["discovery"] / "contract-reuse-result.json").write_bytes(
            canonical_json_bytes({"stale": True})
        )
        with mock.patch.object(
            product_reuse, "_validate_plan", return_value=fixture["plan"],
        ), mock.patch.object(
            product_reuse, "_authorities", return_value=(fixture["authorities"], None),
        ), mock.patch.object(
            product_reuse, "_versions", return_value=VERSIONS,
        ), mock.patch.object(
            product_reuse, "plan_reuse_wave", return_value={"current": True},
        ), self.assertRaisesRegex(ValueError, "not reproducible"):
            product_reuse.advance_contract(
                self.plan_path,
                fixture["discovery"],
                None,
                [],
                fixture["root"] / "rejected-stale-result",
                fixture["root"] / "output-stale-result",
                repository_root=fixture["root"],
                environ={"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
            )
        self.assertFalse((fixture["root"] / "rejected-stale-result").exists())

    def test_contract_advance_control_files_are_canonical_regular_files(self) -> None:
        root = self.root.resolve()
        control = root / "control.json"
        control.write_text('{"value": 1}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "canonical"):
            product_reuse._canonical_control(control, "Control")

        target = root / "target.json"
        target.write_bytes(canonical_json_bytes({"value": 1}))
        linked = root / "linked.json"
        try:
            linked.symlink_to(target)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symbolic links are unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            product_reuse._canonical_control(linked, "Control")

    def test_contract_catalog_paths_rebase_without_weakening_path_rules(self) -> None:
        root = self.root.resolve()
        discovery = root / "discovery-rebase"
        discovery.mkdir()
        record = {
            "manifest": "catalog/index.json",
            "signature": "catalog/index.sig",
            "publicKey": "trust/key.pub",
            "keyring": None,
            "keysDirectory": None,
            "objects": [{"buildKey": sha256_bytes(b"key"), "objectPath": "objects/value.zip"}],
        }
        catalogs = {"stable": [], "promotedMain": None, "samePr": record, "local": None}
        rebased = product_reuse._rebase_catalog_paths(catalogs, discovery, root)
        self.assertEqual("discovery-rebase/catalog/index.json", rebased["samePr"]["manifest"])
        self.assertEqual(
            "discovery-rebase/objects/value.zip",
            rebased["samePr"]["objects"][0]["objectPath"],
        )

        for value in ("../index.json", "/index.json"):
            with self.subTest(value=value):
                mutated = json.loads(json.dumps(catalogs))
                mutated["samePr"]["manifest"] = value
                with self.assertRaisesRegex(ValueError, "normalized|relative POSIX"):
                    product_reuse._rebase_catalog_paths(mutated, discovery, root)
        mutated = json.loads(json.dumps(catalogs))
        mutated["local"] = {}
        with self.assertRaisesRegex(ValueError, "does not accept a local catalog"):
            product_reuse._rebase_catalog_paths(mutated, discovery, root)

    @unittest.skipUnless(shutil.which("ssh-keygen"), "ssh-keygen is required")
    def test_contract_advance_reuses_newly_unblocked_signed_catalog_object(self) -> None:
        repository, commit, tree = self.contract_repository()
        discovery = repository / "build/product-reuse"
        discovery.mkdir(parents=True)
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        binary = PhaseInstanceId("contract", "contract", "binary", "common")
        package = PhaseInstanceId("contract", "contract", "package", "common")
        validation = PhaseInstanceId("contract", "contract", "validation", "common")
        closure = product_reuse._dependency_closure((contract,))
        authorities = [{
            **product_reuse._identity_record(instance),
            "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
            "outputSchemaVersion": 1,
        } for instance in closure]

        def phase_plan(
            instance: PhaseInstanceId, upstream: list[dict[str, object]],
        ) -> dict[str, object]:
            return plan_phase(
                instance,
                inventory=phase_git_inventory(repository, commit, instance),
                versions=VERSIONS,
                upstream_receipts=upstream,
                toolchain_profile_digest=product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
                flags_digest=product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
            )

        remote_producer = {
            "repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/products.yml",
            "commit": commit,
            "tree": tree,
            "event": "pull_request",
            "runId": 7,
            "runAttempt": 1,
            "pullRequest": 31,
        }
        binary_plan = phase_plan(binary, [])
        binary_envelope, binary_object = self.phase_object(
            discovery, "remote-binary", binary_plan, remote_producer,
        )
        package_plan = phase_plan(package, [binary_envelope["receipt"]])
        impact = impact_plan(changed=["known.kt"])
        impact.update({
            "headCommit": commit,
            "validationCommit": commit,
            "validationTree": tree,
        })
        current_producer = product_reuse._consumer(
            impact, {"GITHUB_RUN_ID": "9", "GITHUB_RUN_ATTEMPT": "2"},
        )["producer"]
        package_stage = discovery / "fresh-package-stage"
        package_payload = package_stage / "outputs/package.zip"
        package_payload.parent.mkdir(parents=True)
        package_payload.write_bytes(b"fresh package")
        write_output_manifest(
            package_stage, "contract", "contract", "package", "common", "0.2.0",
            {"artifact": "outputs"},
        )
        package_shard = discovery / "fresh-package-shard"
        finalize_phase_object(
            stage_root=package_stage,
            phase_plan=package_plan,
            producer=current_producer,
            product_version="0.2.0",
            trust_domain="development",
            destination=package_shard,
        )
        package_receipt = verify_phase_shard(package_shard, package)["receipt"]
        validation_plan = phase_plan(validation, [package_receipt])
        validation_envelope, validation_object = self.phase_object(
            discovery, "remote-validation", validation_plan, remote_producer,
        )

        private_key, public_key, signing = generate_development_key(
            self.root.resolve() / "catalog-signing",
        )
        catalog_root = discovery / "catalog"
        catalog_root.mkdir()
        index = {
            "schemaVersion": 1,
            "repository": impact["repository"],
            "context": {
                "kind": "pull-request",
                "pullRequest": 31,
                "commit": commit,
                "tree": tree,
                "runId": 7,
                "runAttempt": 1,
            },
            "entries": sorted(
                (
                    self.product_index_entry(binary_envelope),
                    self.product_index_entry(validation_envelope),
                ),
                key=lambda value: value["buildKey"],
            ),
            "trustDomain": "development",
            "signing": signing,
            "producer": remote_producer,
        }
        manifest = catalog_root / "product-index.json"
        product_reuse.write_canonical_json(manifest, index)
        signature = sign_manifest(manifest, private_key, signing)
        transported_key = catalog_root / "development.pub"
        shutil.copyfile(public_key, transported_key)
        objects = sorted(
            (
                (binary_envelope["receipt"]["buildKey"], binary_object),
                (validation_envelope["receipt"]["buildKey"], validation_object),
            ),
        )
        catalog = {
            "manifest": manifest.relative_to(discovery).as_posix(),
            "signature": signature.relative_to(discovery).as_posix(),
            "publicKey": transported_key.relative_to(discovery).as_posix(),
            "keyring": None,
            "keysDirectory": None,
            "objects": [{
                "buildKey": build_key,
                "objectPath": object_path.relative_to(discovery).as_posix(),
            } for build_key, object_path in objects],
        }
        request = {
            "schemaVersion": 1,
            "requestType": "reuse-wave",
            "repository": impact["repository"],
            "pullRequest": 31,
            "repositoryRoot": str(repository),
            "repositoryRevision": commit,
            "artifactRoot": str(discovery),
            "requested": [product_reuse._identity_record(contract)],
            "versions": VERSIONS,
            "phaseAuthorities": authorities,
            "contractEvidence": None,
            "availableObjects": [],
            "catalogs": {
                "stable": [], "promotedMain": None, "samePr": catalog, "local": None,
            },
        }
        initial_plans = {}
        initial = product_reuse.plan_reuse_wave(
            request,
            build_plan_consumer=lambda instance, value: initial_plans.setdefault(instance, value),
        )
        initial_by_instance = {
            product_reuse._identity(phase): phase for phase in initial["phases"]
        }
        self.assertEqual("reused", initial_by_instance[binary]["state"])
        self.assertEqual("same-pr", initial_by_instance[binary]["source"])
        self.assertEqual("build", initial_by_instance[package]["state"])
        self.assertEqual("waiting", initial_by_instance[validation]["state"])
        self.assertEqual({package: package_plan}, initial_plans)

        for name, value in (
            ("contract-reuse-request.json", request),
            ("contract-reuse-result.json", initial),
            ("producer.json", current_producer),
        ):
            (discovery / name).write_bytes(canonical_json_bytes(value))
        initial_resolution = {
            "schemaVersion": 1,
            "result": "complete",
            "fullReuse": True,
            "phases": [initial_by_instance[binary]],
            "matrices": {"contract": [], "runtime": [], "sdk": []},
        }
        consumer = {"kind": "ci", "producer": current_producer}
        initial_carrier = write_carrier(
            discovery / "reused-carrier",
            initial_resolution,
            (binary,),
            {binary: binary_object},
            consumer,
        )
        initial_record = initial_carrier["objects"][0]
        initial_transport = (
            discovery / "reused-carrier" / transport_relative_path(
                initial_record["buildKey"],
                initial_record["receiptSha256"],
                initial_record["transportSha256"],
            )
        ).read_bytes()
        plan_path = repository / "impact-plan.json"
        plan_path.write_bytes(canonical_json_bytes(impact))
        destination = repository / "advanced"
        github_output_path = repository / "advance-output"
        with mock.patch.object(product_reuse, "validate_remote_build_authorization"), \
                mock.patch.object(product_reuse, "validate_legacy_lane_projection"):
            advanced = product_reuse.advance_contract(
                plan_path,
                discovery,
                None,
                [package_shard],
                destination,
                github_output_path,
                repository_root=repository,
                environ={"GITHUB_RUN_ID": "9", "GITHUB_RUN_ATTEMPT": "2"},
            )

        advanced_by_instance = {
            product_reuse._identity(phase): phase for phase in advanced["phases"]
        }
        self.assertEqual(
            {
                binary: ("retained", None),
                package: ("retained", None),
                validation: ("reused", "same-pr"),
                contract: ("build", None),
            },
            {
                instance: (phase["state"], phase["source"])
                for instance, phase in advanced_by_instance.items()
            },
        )
        verified = verify_carrier(
            destination / "reused-carrier", (binary, package, validation), consumer,
        )
        final_binary = verified["objects"][0]
        self.assertEqual(binary_envelope["receiptBytes"], final_binary["receiptBytes"])
        self.assertEqual(initial_record["transportSha256"], final_binary["transportSha256"])
        final_transport = (
            destination / "reused-carrier" / transport_relative_path(
                final_binary["buildKey"],
                final_binary["receiptSha256"],
                final_binary["transportSha256"],
            )
        ).read_bytes()
        self.assertEqual(initial_transport, final_transport)
        self.assertEqual(
            sha256_bytes(manifest.read_bytes()),
            advanced_by_instance[validation]["transportSource"]["indexSha256"],
        )
        carrier_by_instance = {
            product_reuse._identity(phase): phase
            for phase in verified["resolution"]["phases"]
        }
        self.assertEqual(
            initial_by_instance[binary]["transportSource"],
            carrier_by_instance[binary]["transportSource"],
        )
        self.assertEqual("phase-shard", carrier_by_instance[package]["source"])
        self.assertEqual(
            current_producer,
            carrier_by_instance[package]["transportSource"]["producer"],
        )
        self.assertTrue(
            (destination / "phase-plans/contract-contract-metadata-common.json").is_file()
        )

    def test_product_reuse_cli_dispatches_advance_and_fails_closed(self) -> None:
        arguments = [
            "advance-contract", "--plan", "plan.json",
            "--discovery-root", "discovery", "--state-root", "state",
            "--phase-shard", "one", "--phase-shard", "two",
            "--destination", "destination", "--github-output", "output",
        ]
        with mock.patch.object(product_reuse, "advance_contract") as advance:
            self.assertEqual(0, product_reuse.main(arguments))
        self.assertEqual(
            (
                Path("plan.json"), Path("discovery"), Path("state"),
                [Path("one"), Path("two")], Path("destination"), Path("output"),
            ),
            advance.call_args.args,
        )

        with mock.patch.object(
            product_reuse, "advance_contract", side_effect=ValueError("rejected"),
        ), redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit) as failure:
            product_reuse.main(arguments)
        self.assertEqual(2, failure.exception.code)
        self.assertIn("rejected", stderr.getvalue())

        with mock.patch.object(
            product_reuse, "advance_contract", side_effect=RuntimeError("programmer defect"),
        ), self.assertRaisesRegex(RuntimeError, "programmer defect"):
            product_reuse.main(arguments)

    def test_contract_advance_replays_the_request_and_preserves_a_fresh_shard(self) -> None:
        resolved_root = self.root.resolve()
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        closure = product_reuse._dependency_closure((contract,))
        binary = PhaseInstanceId("contract", "contract", "binary", "common")
        package = PhaseInstanceId("contract", "contract", "package", "common")
        authorities = [{
            **product_reuse._identity_record(instance),
            "toolchainProfileDigest": product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            "flagsDigest": product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
            "outputSchemaVersion": 1,
        } for instance in closure]
        plan = impact_plan(changed=["known.kt"])
        producer = {
            "repository": plan["repository"],
            "workflowPath": ".github/workflows/ci.yml",
            "commit": COMMIT,
            "tree": TREE,
            "event": "pull_request",
            "runId": 7,
            "runAttempt": 2,
            "pullRequest": 31,
        }
        binary_plan = plan_phase(
            binary,
            inventory=[{"relativePath": "input.kt", "bytes": 1, "sha256": sha256_bytes(b"i")}],
            versions=VERSIONS,
            upstream_receipts=[],
            toolchain_profile_digest=product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            flags_digest=product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
        )
        stage = resolved_root / "stage"
        output = stage / "outputs/value.bin"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"value")
        write_output_manifest(
            stage, "contract", "contract", "binary", "common", "0.2.0",
            {"artifact": "outputs"},
        )
        shard = resolved_root / "binary-shard"
        finalize_phase_object(
            stage_root=stage,
            phase_plan=binary_plan,
            producer=producer,
            product_version="0.2.0",
            trust_domain="development",
            destination=shard,
        )
        descriptor = verify_phase_shard(shard, binary)
        prior_phases = [{
            **product_reuse._identity_record(instance),
            "buildKey": binary_plan["buildKey"] if instance == binary else None,
            "state": "build" if instance == binary else "waiting",
            "source": None,
            "transportSource": None,
            "receiptSha256": None,
            "objectSha256": None,
            "misses": [
                {"source": source, "reason": "fixture-miss"}
                for source in product_reuse.SOURCES
            ] if instance == binary else [],
        } for instance in closure]
        prior = {
            "schemaVersion": 1,
            "result": "build-required",
            "fullReuse": False,
            "phases": prior_phases,
            "matrices": {"contract": [{
                **product_reuse._identity_record(binary),
                "buildKey": binary_plan["buildKey"],
            }], "runtime": [], "sdk": []},
        }
        discovery = resolved_root / "discovery"
        discovery.mkdir()
        request = {
            "schemaVersion": 1,
            "requestType": "reuse-wave",
            "repository": plan["repository"],
            "pullRequest": 31,
            "repositoryRoot": str(resolved_root),
            "repositoryRevision": COMMIT,
            "artifactRoot": str(resolved_root / "build/product-reuse"),
            "requested": [product_reuse._identity_record(contract)],
            "versions": VERSIONS,
            "phaseAuthorities": authorities,
            "contractEvidence": None,
            "availableObjects": [],
            "catalogs": {"stable": [], "promotedMain": None, "samePr": None, "local": None},
        }
        for name, value in (
            ("contract-reuse-request.json", request),
            ("contract-reuse-result.json", prior),
            ("producer.json", producer),
        ):
            (discovery / name).write_bytes(canonical_json_bytes(value))
        package_plan = plan_phase(
            package,
            inventory=[{"relativePath": "package.py", "bytes": 1, "sha256": sha256_bytes(b"p")}],
            versions=VERSIONS,
            upstream_receipts=[descriptor["receipt"]],
            toolchain_profile_digest=product_reuse.NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            flags_digest=product_reuse.NOT_APPLICABLE_FLAGS_DIGEST,
        )
        advanced_phases = []
        for instance in closure:
            if instance == binary:
                advanced_phases.append({
                    **product_reuse._identity_record(instance),
                    "buildKey": descriptor["buildKey"],
                    "state": "retained",
                    "source": None,
                    "transportSource": None,
                    "receiptSha256": descriptor["receiptSha256"],
                    "objectSha256": descriptor["objectSha256"],
                    "misses": [],
                })
            else:
                advanced_phases.append({
                    **product_reuse._identity_record(instance),
                    "buildKey": package_plan["buildKey"] if instance == package else None,
                    "state": "build" if instance == package else "waiting",
                    "source": None,
                    "transportSource": None,
                    "receiptSha256": None,
                    "objectSha256": None,
                    "misses": [
                        {"source": source, "reason": "fixture-miss"}
                        for source in product_reuse.SOURCES
                    ] if instance == package else [],
                })
        advanced = {
            "schemaVersion": 1,
            "result": "build-required",
            "fullReuse": False,
            "phases": advanced_phases,
            "matrices": {"contract": [{
                **product_reuse._identity_record(package),
                "buildKey": package_plan["buildKey"],
            }], "runtime": [], "sdk": []},
        }

        advanced_second = None

        def wave(value, *, build_plan_consumer):
            if not value["availableObjects"]:
                build_plan_consumer(binary, binary_plan)
                return prior
            if len(value["availableObjects"]) == 1:
                build_plan_consumer(package, package_plan)
                return json.loads(json.dumps(advanced))
            assert advanced_second is not None
            validation_plan = advanced_second[1]
            build_plan_consumer(validation_plan[0], validation_plan[1])
            return json.loads(json.dumps(advanced_second[0]))

        def reconcile(name, shards, *, state=None, planner=wave):
            destination = resolved_root / name
            output = resolved_root / f"{name}-output"
            with mock.patch.object(product_reuse, "_validate_plan", return_value=plan), \
                    mock.patch.object(product_reuse, "_authorities", return_value=(authorities, None)), \
                    mock.patch.object(product_reuse, "_versions", return_value=VERSIONS), \
                    mock.patch.object(product_reuse, "plan_reuse_wave", side_effect=planner):
                result = product_reuse.advance_contract(
                    self.plan_path,
                    discovery,
                    state,
                    shards,
                    destination,
                    output,
                    repository_root=resolved_root,
                    environ={"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
                )
            return result, destination, output

        self.write_plan(plan)
        result, destination, output = reconcile("advanced", [shard])
        self.assertEqual(advanced, result)
        self.assertEqual(
            canonical_json_bytes(package_plan),
            (destination / "phase-plans/contract-contract-package-common.json").read_bytes(),
        )
        verified = verify_carrier(
            destination / "reused-carrier",
            (binary,),
            {"kind": "ci", "producer": producer},
        )
        self.assertEqual(
            (shard / "phase-receipt.json").read_bytes(),
            verified["objects"][0]["receiptBytes"],
        )
        self.assertEqual("phase-shard", verified["resolution"]["phases"][0]["source"])
        self.assertEqual(list(product_reuse.SOURCES), [
            miss["source"] for miss in verified["resolution"]["phases"][0]["misses"]
        ])
        self.assertEqual(
            {"contract_complete": "false", "next_phase_required": "true"},
            dict(line.split("=", 1) for line in output.read_text().splitlines()),
        )

        package_stage = resolved_root / "package-stage"
        package_output = package_stage / "outputs/value.zip"
        package_output.parent.mkdir(parents=True)
        package_output.write_bytes(b"package")
        write_output_manifest(
            package_stage, "contract", "contract", "package", "common", "0.2.0",
            {"artifact": "outputs"},
        )
        package_shard = resolved_root / "package-shard"
        finalize_phase_object(
            stage_root=package_stage,
            phase_plan=package_plan,
            producer=producer,
            product_version="0.2.0",
            trust_domain="development",
            destination=package_shard,
        )
        package_descriptor = verify_phase_shard(package_shard, package)
        validation = PhaseInstanceId("contract", "contract", "validation", "common")
        validation_plan = {
            "schemaVersion": 1,
            **product_reuse._identity_record(validation),
            "buildKey": sha256_bytes(b"validation"),
            "inputs": {"planner": "owned"},
        }
        second_phases = []
        for instance in closure:
            retained_descriptor = descriptor if instance == binary else (
                package_descriptor if instance == package else None
            )
            second_phases.append({
                **product_reuse._identity_record(instance),
                "buildKey": retained_descriptor["buildKey"] if retained_descriptor else (
                    validation_plan["buildKey"] if instance == validation else None
                ),
                "state": "retained" if retained_descriptor else (
                    "build" if instance == validation else "waiting"
                ),
                "source": None,
                "transportSource": None,
                "receiptSha256": retained_descriptor["receiptSha256"] if retained_descriptor else None,
                "objectSha256": retained_descriptor["objectSha256"] if retained_descriptor else None,
                "misses": [
                    {"source": source, "reason": "fixture-miss"}
                    for source in product_reuse.SOURCES
                ] if instance == validation else [],
            })
        advanced_second = ({
            "schemaVersion": 1,
            "result": "build-required",
            "fullReuse": False,
            "phases": second_phases,
            "matrices": {"contract": [{
                **product_reuse._identity_record(validation),
                "buildKey": validation_plan["buildKey"],
            }], "runtime": [], "sdk": []},
        }, (validation, validation_plan))
        second_result, second_destination, _ = reconcile(
            "advanced-second", [package_shard], state=destination,
        )
        self.assertEqual(
            ["retained", "waiting", "retained", "build"],
            [phase["state"] for phase in second_result["phases"]],
        )
        second_carrier = verify_carrier(
            second_destination / "reused-carrier",
            (binary, package),
            {"kind": "ci", "producer": producer},
        )
        self.assertEqual(
            (package_shard / "phase-receipt.json").read_bytes(),
            second_carrier["objects"][1]["receiptBytes"],
        )

        with self.assertRaisesRegex(ValueError, "do not exactly match"):
            reconcile("missing-shard", [])
        self.assertFalse((resolved_root / "missing-shard").exists())

        rejected_cases = (
            ("duplicate", [shard, shard], "Duplicate Contract phase shard"),
            ("unexpected", [package_shard], "Unexpected Contract phase shard"),
        )
        for name, supplied_shards, message in rejected_cases:
            with self.subTest(shards=name), self.assertRaisesRegex(ValueError, message):
                reconcile(f"rejected-{name}", supplied_shards)
            self.assertFalse((resolved_root / f"rejected-{name}").exists())

        linked_shard = resolved_root / "linked-shard"
        try:
            linked_shard.symlink_to(shard, target_is_directory=True)
        except (NotImplementedError, OSError):
            linked_shard = None
        if linked_shard is not None:
            with self.assertRaisesRegex(ValueError, "unsafe"):
                reconcile("rejected-linked-shard", [linked_shard])
            self.assertFalse((resolved_root / "rejected-linked-shard").exists())

        wrong_trust_shard = resolved_root / "wrong-trust-shard"
        finalize_phase_object(
            stage_root=stage,
            phase_plan=binary_plan,
            producer=producer,
            product_version="0.2.0",
            trust_domain="release",
            destination=wrong_trust_shard,
        )
        with self.assertRaisesRegex(ValueError, "elected plan and producer"):
            reconcile("rejected-trust", [wrong_trust_shard])
        self.assertFalse((resolved_root / "rejected-trust").exists())

        def not_retained(value, *, build_plan_consumer):
            if not value["availableObjects"]:
                build_plan_consumer(binary, binary_plan)
                return prior
            rejected = json.loads(json.dumps(advanced))
            rejected["phases"][0]["state"] = "build"
            return rejected

        with self.assertRaisesRegex(ValueError, "supplied Contract object was not retained"):
            reconcile("rejected-retention", [shard], planner=not_retained)
        self.assertFalse((resolved_root / "rejected-retention").exists())

        missing_carrier_state = resolved_root / "missing-carrier-state"
        missing_carrier_state.mkdir()
        (missing_carrier_state / "contract-reuse-result.json").write_bytes(
            (destination / "contract-reuse-result.json").read_bytes()
        )
        with self.assertRaisesRegex(ValueError, "carrier"):
            reconcile(
                "rejected-missing-carrier", [package_shard], state=missing_carrier_state,
            )
        self.assertFalse((resolved_root / "rejected-missing-carrier").exists())

        unexpected_carrier = discovery / "reused-carrier"
        unexpected_carrier.mkdir()
        with self.assertRaisesRegex(ValueError, "Unexpected prior Contract carrier"):
            reconcile("rejected-unexpected-carrier", [shard])
        self.assertFalse((resolved_root / "rejected-unexpected-carrier").exists())

    def test_contract_advance_publishes_only_a_complete_snapshot(self) -> None:
        root = self.root.resolve()
        source = root / "source"
        source.mkdir()
        (source / "complete.txt").write_bytes(b"complete")
        destination = root / "published"

        def interrupted(_source: int, staged: int) -> None:
            partial = os.open(
                "partial.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=staged,
            )
            os.write(partial, b"partial")
            os.close(partial)
            raise ValueError("interrupted snapshot")

        with mock.patch.object(
            product_inventory, "_copy_directory_descriptor", side_effect=interrupted,
        ):
            with self.assertRaisesRegex(ValueError, "interrupted snapshot"):
                product_inventory.publish_regular_tree(source, destination)
        self.assertFalse(destination.exists())
        self.assertEqual([], list(root.glob(".published-snapshot-*")))

        product_inventory.publish_regular_tree(source, destination)
        self.assertEqual(b"complete", (destination / "complete.txt").read_bytes())
        self.assertFalse((destination / "partial.txt").exists())

    def test_contract_advance_publication_rejects_a_replaced_parent(self) -> None:
        root = self.root.resolve()
        source = root / "source-parent-race"
        source.mkdir()
        (source / "complete.txt").write_bytes(b"complete")
        parent = root / "parent"
        parent.mkdir()
        moved_parent = root / "moved-parent"
        outside = root / "outside"
        outside.mkdir()
        destination = parent / "published"
        real_copy = product_inventory._copy_directory_descriptor

        def replace_parent(source_descriptor: int, destination_descriptor: int) -> None:
            real_copy(source_descriptor, destination_descriptor)
            parent.rename(moved_parent)
            parent.symlink_to(outside, target_is_directory=True)

        with mock.patch.object(
            product_inventory, "_copy_directory_descriptor", side_effect=replace_parent,
        ), self.assertRaisesRegex(ValueError, "parent changed"):
            product_inventory.publish_regular_tree(source, destination)
        self.assertFalse((outside / "published").exists())
        self.assertEqual([], list(moved_parent.iterdir()))

    def test_contract_advance_publication_rejects_a_replaced_staging_entry(self) -> None:
        root = self.root.resolve()
        source = root / "source-staging-race"
        source.mkdir()
        (source / "complete.txt").write_bytes(b"complete")
        parent = root / "staging-parent"
        parent.mkdir()
        destination = parent / "published"
        real_rename = os.rename

        def replace_staging(source_name, destination_name, **kwargs) -> None:
            held_name = f"{source_name}-held"
            real_rename(source_name, held_name, **kwargs)
            staged = product_inventory._open_created_directory(
                kwargs["src_dir_fd"], source_name, 0o700, "replacement",
            )
            try:
                evil = os.open(
                    "evil", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=staged,
                )
                os.write(evil, b"evil")
                os.close(evil)
            finally:
                os.close(staged)
            real_rename(source_name, destination_name, **kwargs)

        with mock.patch.object(os, "rename", side_effect=replace_staging), \
                self.assertRaisesRegex(ValueError, "changed during publication"):
            product_inventory.publish_regular_tree(source, destination)
        self.assertFalse(destination.exists())
        self.assertEqual([], list(parent.iterdir()))

    def test_contract_advance_publication_rejects_staging_content_mutation(self) -> None:
        root = self.root.resolve()
        source = root / "source-content-race"
        source.mkdir()
        (source / "complete.txt").write_bytes(b"complete")
        parent = root / "content-parent"
        parent.mkdir()
        destination = parent / "published"
        real_rename = os.rename

        def mutate_staging(source_name, destination_name, **kwargs) -> None:
            descriptor = os.open(
                f"{source_name}/complete.txt",
                os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=kwargs["src_dir_fd"],
            )
            os.write(descriptor, b"evil")
            os.close(descriptor)
            real_rename(source_name, destination_name, **kwargs)

        with mock.patch.object(os, "rename", side_effect=mutate_staging), \
                self.assertRaisesRegex(ValueError, "contents changed during publication"):
            product_inventory.publish_regular_tree(source, destination)
        self.assertFalse(destination.exists())
        self.assertEqual([], list(parent.iterdir()))

    def test_contract_advance_publication_rejects_post_copy_mutation(self) -> None:
        root = self.root.resolve()
        source = root / "source-copy-race"
        source.mkdir()
        (source / "complete.txt").write_bytes(b"complete")
        destination = root / "copy-race-parent/published"
        real_copy = product_inventory._copy_directory_descriptor

        def mutate_after_copy(source_descriptor: int, staged_descriptor: int) -> None:
            real_copy(source_descriptor, staged_descriptor)
            descriptor = os.open(
                "complete.txt",
                os.O_WRONLY | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=staged_descriptor,
            )
            os.write(descriptor, b"evil")
            os.close(descriptor)

        with mock.patch.object(
            product_inventory, "_copy_directory_descriptor", side_effect=mutate_after_copy,
        ), self.assertRaisesRegex(ValueError, "do not match the source"):
            product_inventory.publish_regular_tree(source, destination)
        self.assertFalse(destination.exists())
        self.assertEqual([], list(destination.parent.iterdir()))

    def test_contract_advance_publication_preserves_directory_modes(self) -> None:
        root = self.root.resolve()
        source = root / "source-modes"
        source.mkdir()
        previous_umask = os.umask(0)
        try:
            nested = source / "nested"
            nested.mkdir(mode=0o777)
        finally:
            os.umask(previous_umask)
        (nested / "value").write_bytes(b"value")
        destination = root / "mode-parent/published"

        previous_umask = os.umask(0o022)
        try:
            product_inventory.publish_regular_tree(source, destination)
        finally:
            os.umask(previous_umask)
        self.assertEqual(0o777, stat.S_IMODE((destination / "nested").stat().st_mode))

    def test_incomplete_result_keeps_target_jobs_required(self) -> None:
        selected = PhaseInstanceId("contract", "contract", "binary", "common")
        authorities = [{
            **product_reuse._identity_record(selected),
            "toolchainProfileDigest": sha256_bytes(b"toolchain"),
            "flagsDigest": sha256_bytes(b"flags"),
            "outputSchemaVersion": 1,
        }]
        reuse = {
            "schemaVersion": 1, "result": "build-required", "fullReuse": False,
            "phases": [], "matrices": {"contract": [{}], "runtime": [], "sdk": []},
        }
        phase_plan = {
            "schemaVersion": 1,
            **product_reuse._identity_record(selected),
            "buildKey": sha256_bytes(b"build"),
            "inputs": {"exact": "planner-owned"},
        }

        def plan_wave(_request, *, build_plan_consumer):
            build_plan_consumer(selected, phase_plan)
            return reuse

        result = self.run_discover(
            impact_plan(changed=["known.kt"]),
            selection=mock.Mock(instances=(selected,), unknown_paths=()),
            _dependency_closure=mock.Mock(return_value=(selected,)),
            _authorities=mock.Mock(return_value=(authorities, None)),
            _versions=mock.Mock(return_value={
                "contract": "0.2.0", "runtime-release": "0.2.0",
                "runtime-compatibility": "0.2.0", "sdk": "0.2.0",
            }),
            _release_trust=mock.Mock(return_value=None),
            _discover_catalogs=mock.Mock(return_value=[]),
            plan_reuse_wave=mock.Mock(side_effect=plan_wave),
            environ={"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
        )
        self.assertEqual("product-build-required", result["reason"])
        self.assertTrue(result["targetJobsRequired"])
        self.assertEqual(
            canonical_json_bytes(phase_plan),
            (self.destination / "phase-plans/contract-contract-binary-common.json").read_bytes(),
        )
        self.assertEqual(
            product_reuse._consumer(
                impact_plan(changed=["known.kt"]),
                {"GITHUB_RUN_ID": "7", "GITHUB_RUN_ATTEMPT": "2"},
            )["producer"],
            json.loads((self.destination / "producer.json").read_text()),
        )


if __name__ == "__main__":
    unittest.main()
